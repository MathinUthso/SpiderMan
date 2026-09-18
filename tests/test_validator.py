"""E2: hand-broken plans are rejected by the replay validator."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app.validator import replay

CASE = json.loads(
    (Path(__file__).resolve().parents[1] / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")
    .read_text(encoding="utf-8")
)["cases"][2]  # SAMPLE-03: has a minimum_battery_reserve directive
SCEN, DIRS, PLAN = CASE["input"], CASE["expected_output"]["directive_interpretation"], CASE["expected_output"]["hourly_plan"]


def _broken(**changes: dict) -> list[dict]:
    plan = copy.deepcopy(PLAN)
    for hour, fields in changes.items():
        plan[int(hour)].update(fields)
    return plan


def test_reference_is_clean() -> None:
    assert replay(SCEN, DIRS, PLAN) == []


def test_neutrality_violation() -> None:
    errs = replay(SCEN, DIRS, _broken(**{"23": {"battery_action": "idle", "battery_kwh": 0, "grid_kwh": 105.0}}))
    assert any("end-of-day" in e or "battery_energy_after" in e for e in errs)


def test_idle_with_nonzero_kwh() -> None:
    errs = replay(SCEN, DIRS, _broken(**{"0": {"battery_action": "idle", "battery_kwh": 5}}))
    assert any("idle" in e for e in errs)


def test_reserve_violation_detected() -> None:
    # Reference SAMPLE-03 is idle at h20 with 100 kWh (exactly the reserve). Discharging 50 there
    # keeps balance (grid -50) and every base rule, but breaks the 100 kWh reserve directive.
    assert PLAN[20]["battery_action"] == "idle"
    p = copy.deepcopy(PLAN)
    p[20].update({"battery_action": "discharge", "battery_kwh": 50,
                  "battery_energy_after_kwh": PLAN[20]["battery_energy_after_kwh"] - 50,
                  "grid_kwh": PLAN[20]["grid_kwh"] - 50})
    for h in range(21, 24):  # propagate the lower state so only the reserve rule fails
        p[h]["battery_energy_after_kwh"] = PLAN[h]["battery_energy_after_kwh"] - 50
    errs = replay(SCEN, DIRS, p)
    assert any("below minimum" in e for e in errs), errs


def test_totals_mismatch_detected() -> None:
    errs = replay(SCEN, DIRS, PLAN, {"total_cost_bdt": 1.0})
    assert any("total_cost_bdt" in e for e in errs)
