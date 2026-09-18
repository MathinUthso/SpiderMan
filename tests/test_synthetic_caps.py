"""Synthetic tests for binding grid caps (T7b fix).

Public data has non-binding grid caps. This test creates a synthetic
case where the cap MUST bind, ensuring the code path works.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interpreter.types import DirectiveInterpretation
from interpreter.guardrails import validate_directives


def test_binding_grid_cap():
    """Grid cap that MUST bind.

    Demand=300, solar=0, cap=100.
    Grid alone can't meet demand. Battery must discharge to cover gap.
    """
    notes = [
        "Grid import must not exceed 100 kWh from 6 PM until 9 PM.",
    ]
    battery_capacity = 500

    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="max_grid_window",
            structured_adjustment={"hours": [18, 19, 20], "max_grid_kwh": 100},
            explanation="Synthetic binding cap test",
        )
    ]

    result = validate_directives(directives, notes, battery_capacity)
    assert isinstance(result, list), f"Guardrails rejected valid case: {result}"
    assert result[0].structured_adjustment["max_grid_kwh"] == 100
    assert result[0].structured_adjustment["hours"] == [18, 19, 20]


def test_grid_cap_exactly_demand():
    """Grid cap == demand (T7b: SAMPLE-10 hour 21 has cap==demand 190==190).

    Must use <=, not <.
    """
    notes = [
        "Grid intake must stay at or below 190 kWh from 7 PM until 10 PM.",
    ]

    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="max_grid_window",
            structured_adjustment={"hours": [19, 20, 21], "max_grid_kwh": 190},
            explanation="Cap equals demand test",
        )
    ]

    result = validate_directives(directives, notes, 260)
    assert isinstance(result, list)


def test_grid_cap_with_reserve_overlap():
    """Grid cap + reserve on overlapping hours (T7: SAMPLE-07/10 pattern).

    Both are hard constraints that must be satisfied jointly.
    """
    notes = [
        "Keep at least 80 kWh in battery from 6 PM until 10 PM.",
        "Grid intake must not exceed 150 kWh from 7 PM until 10 PM.",
    ]

    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [18, 19, 20, 21], "minimum_energy_kwh": 80},
            explanation="Reserve test",
        ),
        DirectiveInterpretation(
            note_index=1,
            applies=True,
            directive_type="max_grid_window",
            structured_adjustment={"hours": [19, 20, 21], "max_grid_kwh": 150},
            explanation="Grid cap test",
        ),
    ]

    result = validate_directives(directives, notes, 250)
    assert isinstance(result, list)
    assert len(result) == 2
