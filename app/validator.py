"""Independent replay of a plan against GridWise rules and applied directives (spec §9, §11).

This is deliberately written without reference to the optimizer so that a bug in one
cannot hide a bug in the other.
"""

from __future__ import annotations

from typing import Any

TOL = 0.01


def effective_constraints(scenario: dict, directives: list[dict]) -> dict[str, Any]:
    """Fold applied directives into per-hour constraint tables."""
    eff_solar = {h["hour"]: float(h["solar_kwh"]) for h in scenario["hours"]}
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    grid_cap: dict[int, float] = {}
    reserve: dict[int, float] = {}
    for d in directives:
        if not d.get("applies") or d.get("directive_type") == "no_op":
            continue
        adj = d["structured_adjustment"]
        t = d["directive_type"]
        hours = adj["hours"]
        if t == "solar_reduction":
            for h in hours:
                eff_solar[h] *= float(adj["factor"])
        elif t == "no_charge_window":
            no_charge |= set(hours)
        elif t == "no_discharge_window":
            no_discharge |= set(hours)
        elif t == "max_grid_window":
            for h in hours:
                grid_cap[h] = min(grid_cap.get(h, float("inf")), float(adj["max_grid_kwh"]))
        elif t == "minimum_battery_reserve":
            for h in hours:
                reserve[h] = max(reserve.get(h, 0.0), float(adj["minimum_energy_kwh"]))
    return {
        "eff_solar": eff_solar,
        "no_charge": no_charge,
        "no_discharge": no_discharge,
        "grid_cap": grid_cap,
        "reserve": reserve,
    }


def replay(scenario: dict, directives: list[dict], plan: list[dict],
           totals: dict[str, float] | None = None) -> list[str]:
    """Return a list of violations (empty means valid)."""
    errs: list[str] = []
    if len(plan) != 24 or sorted(p["hour"] for p in plan) != list(range(24)):
        return ["hourly_plan must contain exactly hours 0..23"]
    plan = sorted(plan, key=lambda p: p["hour"])
    b = scenario["battery"]
    dem = {h["hour"]: float(h["demand_kwh"]) for h in scenario["hours"]}
    tar = {h["hour"]: float(h["tariff_bdt_per_kwh"]) for h in scenario["hours"]}
    c = effective_constraints(scenario, directives)
    e = float(b["initial_energy_kwh"])
    cost = grid_total = peak = 0.0
    for p in plan:
        h = p["hour"]
        g, s, act, bk = float(p["grid_kwh"]), float(p["solar_used_kwh"]), p["battery_action"], float(p["battery_kwh"])
        for name, v in (("grid_kwh", g), ("solar_used_kwh", s), ("battery_kwh", bk)):
            if v < -TOL or v != v or v in (float("inf"), float("-inf")):
                errs.append(f"h{h}: {name} must be finite and non-negative")
        ch = bk if act == "charge" else 0.0
        ds = bk if act == "discharge" else 0.0
        if act == "idle" and abs(bk) > TOL:
            errs.append(f"h{h}: idle with battery_kwh={bk}")
        if act not in ("charge", "discharge", "idle"):
            errs.append(f"h{h}: unknown battery_action {act}")
        if abs(g + s + ds - (dem[h] + ch)) > TOL:
            errs.append(f"h{h}: energy balance off by {g + s + ds - dem[h] - ch:.4f}")
        if s > c["eff_solar"][h] + TOL:
            errs.append(f"h{h}: solar_used {s} > effective solar {c['eff_solar'][h]:.4f}")
        if ch > float(b["max_charge_kwh_per_hour"]) + TOL:
            errs.append(f"h{h}: charge {ch} exceeds max charge rate")
        if ds > float(b["max_discharge_kwh_per_hour"]) + TOL:
            errs.append(f"h{h}: discharge {ds} exceeds max discharge rate")
        if h in c["no_charge"] and ch > TOL:
            errs.append(f"h{h}: charge during no_charge_window")
        if h in c["no_discharge"] and ds > TOL:
            errs.append(f"h{h}: discharge during no_discharge_window")
        if h in c["grid_cap"] and g > c["grid_cap"][h] + TOL:
            errs.append(f"h{h}: grid {g} exceeds cap {c['grid_cap'][h]}")
        e = e + ch - ds
        if abs(e - float(p["battery_energy_after_kwh"])) > TOL:
            errs.append(f"h{h}: battery_energy_after_kwh {p['battery_energy_after_kwh']} != replayed {e:.4f}")
        lo = max(float(b["minimum_energy_kwh"]), c["reserve"].get(h, 0.0))
        if e < lo - TOL:
            errs.append(f"h{h}: battery {e:.4f} below minimum {lo}")
        if e > float(b["capacity_kwh"]) + TOL:
            errs.append(f"h{h}: battery {e:.4f} above capacity")
        cost += g * tar[h]
        grid_total += g
        peak = max(peak, g)
    if abs(e - float(b["initial_energy_kwh"])) > TOL:
        errs.append(f"end-of-day battery {e:.4f} != initial {b['initial_energy_kwh']}")
    if totals:
        for k, v in (("total_cost_bdt", cost), ("total_grid_kwh", grid_total), ("peak_grid_kwh", peak)):
            if k in totals and abs(float(totals[k]) - v) > TOL:
                errs.append(f"{k} {totals[k]} != recomputed {v:.4f}")
    return errs


def totals_from_plan(scenario: dict, plan: list[dict]) -> dict[str, float]:
    """Recompute the three reported totals from the serialized plan."""
    tar = {h["hour"]: float(h["tariff_bdt_per_kwh"]) for h in scenario["hours"]}
    grid = [float(p["grid_kwh"]) for p in plan]
    return {
        "total_grid_kwh": round(sum(grid), 2),
        "total_cost_bdt": round(sum(float(p["grid_kwh"]) * tar[p["hour"]] for p in plan), 2),
        "peak_grid_kwh": round(max(grid), 2),
    }
