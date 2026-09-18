"""Tests for all 10 public sample cases.

These tests verify that the guardrails correctly validate LLM output
for each public case. They use hand-crafted DirectiveInterpretation
objects that match the expected interpretation.

Run with: python -m pytest tests/test_interpreter.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interpreter.types import DirectiveInterpretation
from interpreter.guardrails import validate_directives


# ── Public case definitions ─────────────────────────────────────────────────

PUBLIC_CASES = [
    {
        "id": "SAMPLE-01",
        "notes": [
            "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast.",
            "The sports office moved next month's registration deadline.",
        ],
        "battery_capacity": 220,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [12, 13], "factor": 0.25},
            },
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
            },
        ],
    },
    {
        "id": "SAMPLE-02",
        "notes": [
            "The battery charger will be isolated from 2 AM until 5 AM for electrical maintenance.",
        ],
        "battery_capacity": 200,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [2, 3, 4]},
            },
        ],
    },
    {
        "id": "SAMPLE-03",
        "notes": [
            "Keep at least 50% of the battery capacity stored in the battery from 6 PM until 9 PM for emergency operations.",
        ],
        "battery_capacity": 200,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": [18, 19, 20], "minimum_energy_kwh": 100},
            },
        ],
    },
    {
        "id": "SAMPLE-04",
        "notes": [
            "For protection testing, the battery must not discharge from 6 PM until 8 PM.",
        ],
        "battery_capacity": 230,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": [18, 19]},
            },
        ],
    },
    {
        "id": "SAMPLE-05",
        "notes": [
            "From 6 PM until 9 PM, campus grid import must not exceed 155 kWh in any hour because the feeder is operating under a temporary limit.",
        ],
        "battery_capacity": 240,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [18, 19, 20], "max_grid_kwh": 155},
            },
        ],
    },
    {
        "id": "SAMPLE-06",
        "notes": [
            "Cloud cover during panel inspection will leave about half of the forecast solar output from 10 AM until noon.",
            "The charging circuit will be unavailable from 2 PM until 4 PM.",
            "The library is extending book-return hours next week.",
        ],
        "battery_capacity": 220,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [10, 11], "factor": 0.5},
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [14, 15]},
            },
            {
                "note_index": 2,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
            },
        ],
    },
    {
        "id": "SAMPLE-07",
        "notes": [
            "Keep at least 90 kWh in the battery from 6 PM until 10 PM for emergency services.",
            "The evening transformer limit is 180 kWh of grid import from 7 PM until 9 PM.",
        ],
        "battery_capacity": 250,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": [18, 19, 20, 21], "minimum_energy_kwh": 90},
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [19, 20], "max_grid_kwh": 180},
            },
        ],
    },
    {
        "id": "SAMPLE-08",
        "notes": [
            "Battery charging is disabled from 11 AM until 1 PM while technicians inspect the charger.",
            "Do not discharge the battery from 5 PM until 7 PM during relay testing.",
        ],
        "battery_capacity": 210,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [11, 12]},
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": [17, 18]},
            },
        ],
    },
    {
        "id": "SAMPLE-09",
        "notes": [
            "Expect an 80% reduction in rooftop solar between 11 AM and 2 PM because of inverter work.",
            "The student affairs office will publish club notices tomorrow.",
        ],
        "battery_capacity": 240,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [11, 12, 13], "factor": 0.2},
            },
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
            },
        ],
    },
    {
        "id": "SAMPLE-10",
        "notes": [
            "The data center requires at least 80 kWh to remain in the battery from 6 PM until 10 PM.",
            "Grid intake must stay at or below 190 kWh from 7 PM until 10 PM while the substation is constrained.",
        ],
        "battery_capacity": 260,
        "expected": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": [18, 19, 20, 21], "minimum_energy_kwh": 80},
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [19, 20, 21], "max_grid_kwh": 190},
            },
        ],
    },
]


def make_directives(case: dict) -> list[DirectiveInterpretation]:
    """Create DirectiveInterpretation objects from expected dict."""
    return [
        DirectiveInterpretation(
            note_index=e["note_index"],
            applies=e["applies"],
            directive_type=e["directive_type"],
            structured_adjustment=e.get("structured_adjustment"),
            explanation=f"Test case {case['id']}",
        )
        for e in case["expected"]
    ]


# ── Tests ───────────────────────────────────────────────────────────────────

def test_all_public_cases():
    """Verify guardrails accept correct interpretations for all 10 cases."""
    for case in PUBLIC_CASES:
        directives = make_directives(case)
        result = validate_directives(
            directives, case["notes"], case["battery_capacity"]
        )
        assert isinstance(result, list), (
            f"{case['id']}: guardrails rejected valid interpretation: {result}"
        )
        assert len(result) == len(case["expected"]), (
            f"{case['id']}: expected {len(case['expected'])} entries, got {len(result)}"
        )


def test_sample_01_solar_reduction():
    """SAMPLE-01: solar_reduction [12,13] f=0.25 + no_op."""
    case = PUBLIC_CASES[0]
    directives = make_directives(case)
    result = validate_directives(directives, case["notes"], case["battery_capacity"])
    assert isinstance(result, list)
    assert result[0].directive_type == "solar_reduction"
    assert result[0].structured_adjustment["hours"] == [12, 13]
    assert result[0].structured_adjustment["factor"] == 0.25
    assert result[1].directive_type == "no_op"
    assert result[1].applies is False


def test_sample_03_percentage_reserve():
    """SAMPLE-03: 50% of 200 kWh = 100 kWh."""
    case = PUBLIC_CASES[2]
    directives = make_directives(case)
    result = validate_directives(directives, case["notes"], case["battery_capacity"])
    assert isinstance(result, list)
    assert result[0].structured_adjustment["minimum_energy_kwh"] == 100


def test_sample_06_multi_note():
    """SAMPLE-06: 3 notes, mixed types."""
    case = PUBLIC_CASES[5]
    directives = make_directives(case)
    result = validate_directives(directives, case["notes"], case["battery_capacity"])
    assert isinstance(result, list)
    assert len(result) == 3
    types = [d.directive_type for d in result]
    assert "solar_reduction" in types
    assert "no_charge_window" in types
    assert "no_op" in types


def test_sample_09_80_percent_reduction():
    """SAMPLE-09: 80% reduction = factor 0.2."""
    case = PUBLIC_CASES[8]
    directives = make_directives(case)
    result = validate_directives(directives, case["notes"], case["battery_capacity"])
    assert isinstance(result, list)
    assert result[0].structured_adjustment["factor"] == 0.2
    assert result[0].structured_adjustment["hours"] == [11, 12, 13]
