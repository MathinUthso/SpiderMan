"""Lattice dynamic program over battery energy. Exact when all quantities sit on the lattice.

Used as an independent oracle in tests and as the runtime fallback if the LP path fails.
"""

from __future__ import annotations

from app.schemas import Infeasible
from app.validator import effective_constraints

H = 24


def solve_dp(scenario: dict, directives: list[dict], step: float = 0.5) -> list[dict]:
    b = scenario["battery"]
    hours = sorted(scenario["hours"], key=lambda x: x["hour"])
    dem = [float(x["demand_kwh"]) for x in hours]
    tar = [float(x["tariff_bdt_per_kwh"]) for x in hours]
    con = effective_constraints(scenario, directives)
    eff = [con["eff_solar"][h] for h in range(H)]
    e0 = float(b["initial_energy_kwh"])
    cap = float(b["capacity_kwh"])
    base_min = float(b["minimum_energy_kwh"])
    mc = float(b["max_charge_kwh_per_hour"])
    md = float(b["max_discharge_kwh_per_hour"])

    # Lattice anchored at e0 so the start/end state is always representable.
    k_lo = -int(e0 // step)
    k_hi = int((cap - e0) // step)
    level = lambda k: e0 + k * step  # noqa: E731

    dp: dict[int, float] = {0: 0.0}
    back: list[dict[int, tuple[int, float, float]]] = []  # k_after -> (k_before, delta, grid)
    for h in range(H):
        lo = max(base_min, con["reserve"].get(h, 0.0))
        gcap = con["grid_cap"].get(h, float("inf"))
        dmin = 0.0 if h in con["no_discharge"] else -md
        dmax = 0.0 if h in con["no_charge"] else mc
        kmin_d, kmax_d = int(-((-dmin) // step)), int(dmax // step)
        nxt: dict[int, float] = {}
        bk: dict[int, tuple[int, float, float]] = {}
        for k, cost in dp.items():
            for kd in range(kmin_d, kmax_d + 1):
                k2 = k + kd
                if k2 < k_lo or k2 > k_hi:
                    continue
                e_after = level(k2)
                if e_after < lo - 1e-9 or e_after > cap + 1e-9:
                    continue
                delta = kd * step
                need = dem[h] + delta
                if need < -1e-9:
                    continue
                s = min(eff[h], need)
                g = need - s
                if g > gcap + 1e-9:
                    continue
                nc = cost + g * tar[h]
                if nc < nxt.get(k2, float("inf")) - 1e-12:
                    nxt[k2] = nc
                    bk[k2] = (k, delta, g)
        if not nxt:
            raise Infeasible(f"no feasible battery state at hour {h}")
        dp = nxt
        back.append(bk)

    if 0 not in dp:
        raise Infeasible("end-of-day neutrality unreachable on lattice")

    # Reconstruct.
    plan: list[dict] = []
    k = 0
    for h in range(H - 1, -1, -1):
        k_prev, delta, g = back[h][k]
        need = dem[h] + delta
        s = min(eff[h], need)
        e_after = level(k)
        if delta > 0:
            action, mag = "charge", delta
        elif delta < 0:
            action, mag = "discharge", -delta
        else:
            action, mag = "idle", 0.0
        plan.append({
            "hour": h,
            "grid_kwh": round(g, 2),
            "solar_used_kwh": round(s, 2),
            "battery_action": action,
            "battery_kwh": round(mag, 2),
            "battery_energy_after_kwh": round(e_after, 2),
        })
        k = k_prev
    plan.reverse()
    return plan
