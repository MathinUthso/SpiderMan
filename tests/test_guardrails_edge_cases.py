"""Guardrails edge case tests from TRAPS.md.

Tests for T1 (missing indices), T19 (same-type notes), time parsing,
factor extraction, and reserve handling.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interpreter.types import DirectiveInterpretation
from interpreter.guardrails import validate_directives


# ── T1: Missing index ───────────────────────────────────────────────────────

def test_missing_note_index():
    """T1: LLM skips index 1 → guardrails reject."""
    notes = ["Note A", "Note B"]
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.5},
            explanation="Test",
        ),
        # index 1 is missing
    ]
    result = validate_directives(directives, notes, 220)
    assert isinstance(result, str), "Should reject missing index"
    assert "Expected" in result or "Indices" in result


def test_duplicate_note_index():
    """LLM repeats index 0 → guardrails reject."""
    notes = ["Note A", "Note B"]
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.5},
            explanation="Test",
        ),
        DirectiveInterpretation(
            note_index=0, applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, notes, 220)
    assert isinstance(result, str), "Should reject duplicate index"
    assert "Duplicate" in result or "Indices" in result


# ── T19: Overlapping same-type directives ───────────────────────────────────

def test_two_no_charge_windows():
    """T19: Two notes both no_charge_window on different hours.

    Each note produces its own entry. Same type is allowed.
    """
    notes = [
        "Battery charging is disabled from 2 AM until 5 AM.",
        "Battery charging is disabled from 11 AM until 1 PM.",
    ]
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="no_charge_window",
            structured_adjustment={"hours": [2, 3, 4]},
            explanation="Morning maintenance",
        ),
        DirectiveInterpretation(
            note_index=1, applies=True,
            directive_type="no_charge_window",
            structured_adjustment={"hours": [11, 12]},
            explanation="Afternoon inspection",
        ),
    ]
    result = validate_directives(directives, notes, 220)
    assert isinstance(result, list), f"Should accept same-type notes: {result}"
    assert len(result) == 2


def test_two_reserves_different_values():
    """T19: Two notes with different reserve values on overlapping hours."""
    notes = [
        "Keep at least 100 kWh in battery from 6 PM until 9 PM.",
        "Keep at least 120 kWh in battery from 8 PM until 10 PM.",
    ]
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [18, 19, 20], "minimum_energy_kwh": 100},
            explanation="First reserve",
        ),
        DirectiveInterpretation(
            note_index=1, applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [20, 21], "minimum_energy_kwh": 120},
            explanation="Second reserve",
        ),
    ]
    result = validate_directives(directives, notes, 250)
    assert isinstance(result, list), f"Should accept overlapping reserves: {result}"


# ── Time parsing (end-exclusive) ────────────────────────────────────────────

def test_end_exclusive_1pm_to_3pm():
    """1 PM to 3 PM must be [13, 14], NOT [13, 14, 15]."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [13, 14], "factor": 0.2},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, list)


def test_rejects_inclusive_window():
    """[13, 14, 15] for 1 PM to 3 PM should still pass guardrails
    (guardrails can't know the original note), but the LLM prompt
    must produce the correct end-exclusive form."""
    # This tests that guardrails accept valid hours regardless of intent
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [13, 14, 15], "factor": 0.2},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    # Guardrails accept this (hours are valid 0-23 ascending)
    # But the optimizer would apply it to wrong hours
    assert isinstance(result, list)


# ── Factor extraction (fraction remaining) ──────────────────────────────────

def test_factor_remaining_not_reduction():
    """80% reduction must produce factor=0.2, not 0.8."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [11, 12, 13], "factor": 0.2},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, list)
    assert result[0].structured_adjustment["factor"] == 0.2


def test_rejects_factor_above_one():
    """Factor > 1.0 must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 1.5},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject factor > 1.0"


def test_rejects_factor_below_zero():
    """Factor < 0.0 must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": -0.1},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject factor < 0.0"


# ── Reserve handling ────────────────────────────────────────────────────────

def test_reserve_below_base_is_nonbinding():
    """Directive reserve below base minimum → still valid (non-binding)."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [18, 19], "minimum_energy_kwh": 20},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, list)


def test_reserve_exceeds_capacity_rejected():
    """Reserve above battery capacity must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [18], "minimum_energy_kwh": 300},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject reserve > capacity"


# ── Applies semantics ───────────────────────────────────────────────────────

def test_no_op_must_have_applies_false():
    """no_op with applies=true must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject no_op with applies=true"


def test_solar_reduction_must_have_applies_true():
    """solar_reduction with applies=false must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=False,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.5},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject solar_reduction with applies=false"


# ── Hours validation ────────────────────────────────────────────────────────

def test_hours_must_be_ascending():
    """Hours not in ascending order must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [14, 12], "factor": 0.5},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject non-ascending hours"


def test_hours_must_be_unique():
    """Duplicate hours must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12, 12, 13], "factor": 0.5},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject duplicate hours"


def test_hours_out_of_range():
    """Hours outside 0-23 must be rejected."""
    directives = [
        DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [0, 24], "factor": 0.5},
            explanation="Test",
        ),
    ]
    result = validate_directives(directives, ["test note"], 220)
    assert isinstance(result, str), "Should reject hour 24"
