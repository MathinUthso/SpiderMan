"""Optimizer paths that the 10 public cases cannot exercise (docs/TRAPS.md T7b, T13, T14, T18, T19).

Every scenario is synthetic and asserts that the plan is validator-clean; where the data sits on
an integer lattice the LP cost must also equal the exact DP oracle.
"""

from __future__ import annotations

import random

import pytest

from app.optimizer import optimize
from app.optimizer.dp import solve_dp
from app.schemas import Infeasible
from app.validator import replay, totals_from_plan


def scenario(demand=100.0, solar=None, tariff=None, **battery) -> dict:
    bat = {"capacity_kwh": 200.0, "initial_energy_kwh": 100.0, "minimum_energy_kwh": 20.0,
           "max_charge_kwh_per_hour": 50.0, "max_discharge_kwh_per_hour": 50.0}
    bat.update(battery)
    solar = solar or [0.0] * 24
    tariff = tariff or [5.0] * 8 + [10.0] * 9 + [30.0] * 4 + [8.0] * 3
    dem = demand if isinstance(demand, list) else [demand] * 24
    return {"scenario_id": "T", "operator_notes": ["x"], "battery": bat,
            "hours": [{"hour": h, "demand_kwh": dem[h], "solar_kwh": solar[h], "tariff_bdt_per_kwh": tariff[h]} for h in range(24)]}


def directive(i: int, t: str, **adj) -> dict:
    return {"note_index": i, "applies": True, "directive_type": t, "structured_adjustment": adj, "explanation": "t"}


def solve(scen: dict, dirs: list[dict]) -> tuple[list[dict], float]:
    plan, _ = optimize(scen, dirs)
    assert replay(scen, dirs, plan) == []
    return plan, totals_from_plan(scen, plan)["total_cost_bdt"]


def test_binding_grid_cap_is_enforced_and_costs_money() -> None:
    # Hour 16 is cheap and sits right before the expensive evening (17-20). Capping its grid import
    # forces a 40 kWh discharge the optimizer would never choose, with no time to recharge, so that
    # energy is missing from the peak. (A cap inside a flat-tariff peak is NOT binding on cost: the
    # optimizer just spreads the discharge — the same trap the public sample caps fall into.)
    scen = scenario()
    _, free = solve(scen, [])
    cap = [directive(0, "max_grid_window", hours=[16], max_grid_kwh=60.0)]
    plan, capped = solve(scen, cap)
    assert plan[16]["grid_kwh"] <= 60.0 + 1e-9
    assert plan[16]["battery_action"] == "discharge" and plan[16]["battery_kwh"] >= 40.0 - 1e-9
    assert capped > free + 100.0, "a binding cap must raise the cost; equal cost means it was ignored"
    assert abs(capped - totals_from_plan(scen, solve_dp(scen, cap, step=1.0))["total_cost_bdt"]) <= 0.01


def test_infeasible_cap_raises_infeasible() -> None:
    with pytest.raises(Infeasible):
        optimize(scenario(), [directive(0, "max_grid_window", hours=[19], max_grid_kwh=10.0)])


def test_asymmetric_charge_and_discharge_rates() -> None:
    scen = scenario(max_charge_kwh_per_hour=15.0, max_discharge_kwh_per_hour=70.0)
    plan, cost = solve(scen, [])
    assert max(p["battery_kwh"] for p in plan if p["battery_action"] == "charge") <= 15.0 + 1e-9
    assert max(p["battery_kwh"] for p in plan if p["battery_action"] == "discharge") <= 70.0 + 1e-9
    assert abs(cost - totals_from_plan(scen, solve_dp(scen, [], step=1.0))["total_cost_bdt"]) <= 0.01


def test_surplus_solar_with_full_battery_is_curtailed() -> None:
    solar = [0.0] * 9 + [400.0] * 6 + [0.0] * 9
    scen = scenario(demand=80.0, solar=solar, initial_energy_kwh=200.0)
    plan, _ = solve(scen, [])
    used = sum(p["solar_used_kwh"] for p in plan)
    assert used < sum(solar) - 100, "solar far above demand + battery headroom must be curtailed, not used"


def test_zero_demand_hours_and_flat_tariff() -> None:
    dem = [0.0 if h in (2, 3, 4) else 90.0 for h in range(24)]
    solve(scenario(demand=dem, tariff=[7.0] * 24), [])


def test_two_notes_of_same_type_take_the_stricter_value() -> None:
    scen = scenario()
    dirs = [directive(0, "max_grid_window", hours=[18, 19], max_grid_kwh=90.0),
            directive(1, "max_grid_window", hours=[19, 20], max_grid_kwh=70.0),
            directive(2, "minimum_battery_reserve", hours=[10, 11], minimum_energy_kwh=120.0)]
    plan, _ = solve(scen, dirs)
    assert plan[18]["grid_kwh"] <= 90.0 + 1e-9 and plan[19]["grid_kwh"] <= 70.0 + 1e-9 and plan[20]["grid_kwh"] <= 70.0 + 1e-9
    assert plan[10]["battery_energy_after_kwh"] >= 120.0 - 1e-9


def test_no_discharge_inside_reserve_window() -> None:
    dirs = [directive(0, "minimum_battery_reserve", hours=[17, 18, 19], minimum_energy_kwh=90.0),
            directive(1, "no_discharge_window", hours=[18, 19])]
    plan, _ = solve(scenario(), dirs)
    assert all(plan[h]["battery_action"] != "discharge" for h in (18, 19))


def test_reserve_below_base_minimum_does_not_lower_the_floor() -> None:
    scen = scenario(minimum_energy_kwh=60.0)
    plan, _ = solve(scen, [directive(0, "minimum_battery_reserve", hours=list(range(24)), minimum_energy_kwh=5.0)])
    assert min(p["battery_energy_after_kwh"] for p in plan) >= 60.0 - 1e-9


def test_battery_that_cannot_move() -> None:
    plan, _ = solve(scenario(max_charge_kwh_per_hour=0.0, max_discharge_kwh_per_hour=0.0), [])
    assert all(p["battery_action"] == "idle" and p["battery_kwh"] == 0 for p in plan)


def test_non_round_inputs_never_need_the_dp_fallback() -> None:
    """Regression: independently rounded hourly flows used to drift past limits on ~17% of inputs."""
    rng = random.Random(2026)
    for _ in range(80):
        cap = round(rng.uniform(60, 480), 3)
        bmin = round(rng.uniform(0, 0.3 * cap), 3)
        scen = scenario(
            demand=[round(rng.uniform(20, 240), 3) for _ in range(24)],
            solar=[round(max(0.0, 1 - abs(h - 12) / 6) * rng.uniform(0, 300), 3) for h in range(24)],
            tariff=[round(rng.uniform(1, 40), 2) for _ in range(24)],
            capacity_kwh=cap, minimum_energy_kwh=bmin, initial_energy_kwh=round(rng.uniform(bmin, cap), 3),
            max_charge_kwh_per_hour=round(rng.uniform(5, 80), 3), max_discharge_kwh_per_hour=round(rng.uniform(5, 80), 3),
        )
        dirs = [directive(0, "solar_reduction", hours=[11, 12, 13], factor=rng.choice([0.2, 0.333, 0.667]))]
        plan, solver = optimize(scen, dirs)
        assert solver in ("lp", "lp-margin"), f"fell back to {solver}"
        assert replay(scen, dirs, plan) == []
