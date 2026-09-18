"""Exact LP over 96 variables (grid, solar_used, charge, discharge per hour) via HiGHS.

Formulation is plan §3. After solving, simultaneous charge/discharge is netted, values
are rounded to 2 dp, and end-of-day neutrality is reconciled against rounding drift.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from app.schemas import Infeasible
from app.validator import effective_constraints

H = 24
INF = float("inf")


def _idx(h: int) -> tuple[int, int, int, int]:
    """Column indices (g, s, c, d) for hour h."""
    base = 4 * h
    return base, base + 1, base + 2, base + 3


def solve_lp(scenario: dict, directives: list[dict]) -> list[dict]:
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
    lo = [max(base_min, con["reserve"].get(h, 0.0)) for h in range(H)]

    n = 4 * H
    cost = np.zeros(n)
    bounds: list[tuple[float, float]] = [(0.0, 0.0)] * n
    for h in range(H):
        g, s, c, d = _idx(h)
        cost[g] = tar[h]
        bounds[g] = (0.0, con["grid_cap"].get(h, INF))
        bounds[s] = (0.0, eff[h])
        bounds[c] = (0.0, 0.0 if h in con["no_charge"] else mc)
        bounds[d] = (0.0, 0.0 if h in con["no_discharge"] else md)

    # Equalities: hourly balance (24 rows) + neutrality (1 row).
    a_eq = np.zeros((H + 1, n))
    b_eq = np.zeros(H + 1)
    for h in range(H):
        g, s, c, d = _idx(h)
        a_eq[h, [g, s, d, c]] = [1.0, 1.0, 1.0, -1.0]
        b_eq[h] = dem[h]
        a_eq[H, c] = 1.0
        a_eq[H, d] = -1.0
    b_eq[H] = 0.0

    # Inequalities: battery level bounds for every hour (2 rows each).
    a_ub = np.zeros((2 * H, n))
    b_ub = np.zeros(2 * H)
    for h in range(H):
        for k in range(h + 1):
            _, _, c, d = _idx(k)
            a_ub[2 * h, c], a_ub[2 * h, d] = 1.0, -1.0        # E_h <= cap
            a_ub[2 * h + 1, c], a_ub[2 * h + 1, d] = -1.0, 1.0  # E_h >= lo_h
        b_ub[2 * h] = cap - e0
        b_ub[2 * h + 1] = e0 - lo[h]

    res = linprog(cost, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0 or res.x is None:
        raise Infeasible(f"linprog status {res.status}: {res.message}")

    x = res.x
    ch = np.array([max(0.0, x[_idx(h)[2]]) for h in range(H)])
    ds = np.array([max(0.0, x[_idx(h)[3]]) for h in range(H)])
    su = np.array([max(0.0, x[_idx(h)[1]]) for h in range(H)])

    # 1. Net simultaneous charge/discharge (LP degeneracy; free with 100% efficiency).
    m = np.minimum(ch, ds)
    ch, ds = ch - m, ds - m

    # 2. Round battery flows and solar; grid is derived so balance holds exactly.
    ch = np.round(ch, 2)
    ds = np.round(ds, 2)
    su = np.minimum(np.round(su, 2), eff)

    # 3. Reconcile neutrality drift introduced by rounding.
    drift = round(float(ch.sum() - ds.sum()), 6)  # >0: ended above initial
    if abs(drift) > 1e-9:
        _reconcile(drift, ch, ds, con, mc, md, e0, lo, cap)

    plan: list[dict] = []
    e = e0
    for h in range(H):
        c, d = float(ch[h]), float(ds[h])
        s = float(su[h])
        g = dem[h] + c - d - s
        if g < 0:  # rounding pushed solar past need; trim solar instead
            s = max(0.0, s + g)
            g = 0.0
        g = round(g, 2)
        e = round(e + c - d, 2)
        if c > 0:
            action, mag = "charge", c
        elif d > 0:
            action, mag = "discharge", d
        else:
            action, mag = "idle", 0.0
        plan.append({
            "hour": h,
            "grid_kwh": g,
            "solar_used_kwh": round(s, 2) if s == round(s, 2) else s,
            "battery_action": action,
            "battery_kwh": round(mag, 2),
            "battery_energy_after_kwh": e,
        })
    return plan


def _reconcile(drift: float, ch: np.ndarray, ds: np.ndarray, con: dict,
               mc: float, md: float, e0: float, lo: list[float], cap: float) -> None:
    """Remove `drift` kWh of net charge (or add if negative) at the latest feasible hour."""
    for h in range(H - 1, -1, -1):
        if drift > 0:
            if ch[h] >= drift:
                ch[h] = round(ch[h] - drift, 2)
                return
            if h not in con["no_discharge"] and ds[h] + drift <= md + 1e-9:
                ds[h] = round(ds[h] + drift, 2)
                return
        else:
            need = -drift
            if h not in con["no_charge"] and ch[h] + need <= mc + 1e-9:
                ch[h] = round(ch[h] + need, 2)
                return
            if ds[h] >= need:
                ds[h] = round(ds[h] - need, 2)
                return
    # If nothing could absorb it the validator will reject and DP takes over.
