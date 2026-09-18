"""E3: malformed or invented LLM output never reaches the optimizer as a constraint."""

from __future__ import annotations

from app.interpreter.guardrails import validate_llm_output

BATTERY = {"capacity_kwh": 200, "minimum_energy_kwh": 40}


def _one(rec: dict, n: int = 1) -> dict:
    return validate_llm_output({"interpretations": [rec]}, n, BATTERY)[0]


def test_invented_type_becomes_no_op() -> None:
    d = _one({"note_index": 0, "applies": True, "directive_type": "shutdown_grid", "hours": [1], "explanation": "x"})
    assert d["directive_type"] == "no_op" and d["applies"] is False and d["structured_adjustment"] is None


def test_hours_normalised_and_bounded() -> None:
    d = _one({"note_index": 0, "applies": True, "directive_type": "no_charge_window", "hours": [15, 14, 14], "explanation": "x"})
    assert d["structured_adjustment"] == {"hours": [14, 15]}
    d = _one({"note_index": 0, "applies": True, "directive_type": "no_charge_window", "hours": [24], "explanation": "x"})
    assert d["directive_type"] == "no_op"


def test_factor_range_enforced() -> None:
    d = _one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [13], "factor": 1.4, "explanation": "x"})
    assert d["directive_type"] == "no_op"
    d = _one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [13], "factor": 0.2, "explanation": "x"})
    assert d["structured_adjustment"] == {"hours": [13], "factor": 0.2}


def test_reserve_capped_at_capacity() -> None:
    d = _one({"note_index": 0, "applies": True, "directive_type": "minimum_battery_reserve", "hours": [18], "minimum_energy_kwh": 999, "explanation": "x"})
    assert d["directive_type"] == "no_op"


def test_missing_duplicate_and_extra_indices() -> None:
    raw = {"interpretations": [
        {"note_index": 1, "applies": False, "directive_type": "no_op", "explanation": "a"},
        {"note_index": 1, "applies": True, "directive_type": "no_charge_window", "hours": [2], "explanation": "dup"},
        {"note_index": 7, "applies": True, "directive_type": "no_charge_window", "hours": [2], "explanation": "extra"},
    ]}
    out = validate_llm_output(raw, 3, BATTERY)
    assert [d["note_index"] for d in out] == [0, 1, 2]
    assert all(d["directive_type"] == "no_op" for d in out)


def test_applies_false_normalized_to_true() -> None:
    d = _one({"note_index": 0, "applies": False, "directive_type": "no_charge_window", "hours": [5], "explanation": "x"})
    assert d["directive_type"] == "no_charge_window"
    assert d["applies"] is True
    assert d["structured_adjustment"] == {"hours": [5]}


def test_garbage_input_yields_all_no_op() -> None:
    for raw in (None, "text", 42, {"interpretations": "nope"}, []):
        out = validate_llm_output(raw, 2, BATTERY)
        assert len(out) == 2 and all(d["directive_type"] == "no_op" for d in out)
