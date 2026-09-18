"""Guardrail normalisation, provider chain and graceful-infeasible behaviour — all without network."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.interpreter as interp
import app.service as service
from app.interpreter.guardrails import validate_llm_output
from app.interpreter.prompt import RESPONSE_SCHEMA, build_user_message
from app.interpreter.providers import ProviderError
from app.main import app
from app.validator import replay

BATTERY = {"capacity_kwh": 200.0, "minimum_energy_kwh": 40.0}
CASES = json.loads((Path(__file__).resolve().parents[1] / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")
                   .read_text(encoding="utf-8"))["cases"]


def one(rec: dict) -> dict:
    return validate_llm_output({"interpretations": [rec]}, 1, BATTERY)[0]


# ---------- guardrails ----------

def test_single_value_slot_maps_to_spec_field_names() -> None:
    assert one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [12, 13], "value": 0.25,
                "explanation": "x"})["structured_adjustment"] == {"hours": [12, 13], "factor": 0.25}
    assert one({"note_index": 0, "applies": True, "directive_type": "minimum_battery_reserve", "hours": [18], "value": 90,
                "explanation": "x"})["structured_adjustment"] == {"hours": [18], "minimum_energy_kwh": 90.0}
    assert one({"note_index": 0, "applies": True, "directive_type": "max_grid_window", "hours": [19], "value": 155,
                "explanation": "x"})["structured_adjustment"] == {"hours": [19], "max_grid_kwh": 155.0}


def test_number_in_the_wrong_slot_is_recovered() -> None:
    """The exact production failure on SAMPLE-01: right type and hours, factor written elsewhere."""
    d = one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [12, 13],
             "max_grid_kwh": 0.25, "minimum_energy_kwh": 0.25, "explanation": "x"})
    assert d["directive_type"] == "solar_reduction" and d["structured_adjustment"] == {"hours": [12, 13], "factor": 0.25}


def test_conflicting_misplaced_numbers_are_not_guessed() -> None:
    d = one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [12],
             "max_grid_kwh": 0.25, "minimum_energy_kwh": 0.5, "explanation": "x"})
    assert d["directive_type"] == "no_op"


def test_applies_is_normalised_not_trusted() -> None:
    for applies in (False, None, "yes"):
        d = one({"note_index": 0, "applies": applies, "directive_type": "no_charge_window", "hours": [14, 15], "explanation": "x"})
        assert d["applies"] is True and d["structured_adjustment"] == {"hours": [14, 15]}


def test_stray_hour_24_is_dropped_not_fatal() -> None:
    d = one({"note_index": 0, "applies": True, "directive_type": "minimum_battery_reserve", "hours": list(range(25)),
             "value": 30, "explanation": "x"})
    assert d["structured_adjustment"]["hours"] == list(range(24))


def test_percentage_and_share_forms_are_normalised_but_increases_are_rejected() -> None:
    assert one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [9], "value": 25,
                "explanation": "x"})["structured_adjustment"]["factor"] == 0.25
    assert one({"note_index": 0, "applies": True, "directive_type": "minimum_battery_reserve", "hours": [9], "value": 0.5,
                "explanation": "x"})["structured_adjustment"]["minimum_energy_kwh"] == 100.0
    assert one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [9], "value": 1.5,
                "explanation": "x"})["directive_type"] == "no_op"


def test_rejected_record_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        one({"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": ["noon"], "value": 0.2, "explanation": "x"})
    assert any("rejected note 0" in r.message for r in caplog.records)


def test_prompt_is_identical_for_int_and_float_battery_values() -> None:
    assert build_user_message(["n"], {"capacity_kwh": 220, "minimum_energy_kwh": 40}) == \
        build_user_message(["n"], {"capacity_kwh": 220.0, "minimum_energy_kwh": 40.0})


def test_schema_has_exactly_one_numeric_slot() -> None:
    props = RESPONSE_SCHEMA["properties"]["interpretations"]["items"]["properties"]
    assert [k for k, v in props.items() if v.get("type") == "number"] == ["value"]


# ---------- provider chain ----------

def _chain(monkeypatch: pytest.MonkeyPatch, *behaviours) -> list[str]:
    calls: list[str] = []

    def make(name, behaviour):
        async def call(notes, battery, timeout):
            calls.append(name)
            if isinstance(behaviour, Exception):
                raise behaviour
            if behaviour == "hang":
                await asyncio.sleep(30)
            return behaviour
        return call

    monkeypatch.setattr(interp, "PROVIDERS", tuple((f"p{i}", make(f"p{i}", b), 0.2) for i, b in enumerate(behaviours)))
    monkeypatch.setattr(interp, "cache_get", lambda *a: None)
    monkeypatch.setattr(interp, "cache_put", lambda *a: None)
    return calls


GOOD = {"interpretations": [{"note_index": 0, "applies": True, "directive_type": "no_charge_window", "hours": [2, 3], "explanation": "x"}]}


def test_chain_falls_through_failures_and_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _chain(monkeypatch, ProviderError("HTTP 429"), "hang", GOOD)
    directives, degraded = asyncio.run(interp.interpret(["n"], BATTERY))
    assert calls == ["p0", "p1", "p2"] and degraded is False
    assert directives[0]["directive_type"] == "no_charge_window"


def test_all_providers_failing_degrades_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    _chain(monkeypatch, ProviderError("x"), RuntimeError("boom"))
    directives, degraded = asyncio.run(interp.interpret(["a", "b"], BATTERY))
    assert degraded is True and [d["directive_type"] for d in directives] == ["no_op", "no_op"]


def test_budget_stops_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _chain(monkeypatch, "hang", "hang", GOOD)
    monkeypatch.setenv("INTERPRET_BUDGET_S", "1.1")
    _, degraded = asyncio.run(interp.interpret(["n"], BATTERY))
    assert degraded is True and "p2" not in calls


# ---------- graceful infeasibility ----------

def test_infeasible_directives_return_200_and_say_what_was_not_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    inp = dict(CASES[1]["input"], operator_notes=["cap", "hold"])
    impossible = [
        {"note_index": 0, "applies": True, "directive_type": "max_grid_window",
         "structured_adjustment": {"hours": [19], "max_grid_kwh": 10.0}, "explanation": "x"},
        {"note_index": 1, "applies": True, "directive_type": "no_charge_window",
         "structured_adjustment": {"hours": [2, 3]}, "explanation": "x"},
    ]

    async def fake(notes, battery):
        return [dict(d) for d in impossible], False

    monkeypatch.setattr(service, "interpret", fake)
    r = TestClient(app, raise_server_exceptions=False).post("/optimize-energy", json=inp)
    assert r.status_code == 200, r.text
    out = r.json()
    kept = {d["note_index"]: d for d in out["directive_interpretation"]}
    assert kept[0]["directive_type"] == "no_op" and "not applied" in kept[0]["explanation"]
    assert kept[1]["directive_type"] == "no_charge_window", "the satisfiable directive must survive"
    assert replay(inp, out["directive_interpretation"], out["hourly_plan"]) == []
    assert "not applied" in out["plan_summary"]


# ---------- API leniency ----------

@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    return TestClient(app, raise_server_exceptions=False)


def test_trailing_slash_head_and_content_type_are_tolerated(client: TestClient) -> None:
    assert client.get("/health/").status_code == 200
    assert client.head("/health").status_code == 200
    body = json.dumps(CASES[0]["input"]).encode()
    assert client.post("/optimize-energy/", content=body, headers={"content-type": "text/plain"}).status_code == 200


def test_invalid_bodies_are_400_never_500(client: TestClient) -> None:
    for body in (b"", b"{nope", b"[1,2]", b'"text"', json.dumps({"scenario_id": "x"}).encode()):
        r = client.post("/optimize-energy", content=body, headers={"content-type": "application/json"})
        assert r.status_code == 400 and "error" in r.json(), body
