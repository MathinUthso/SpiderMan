"""E1: every public case is validator-clean and cost-optimal through the optimizer and the API."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.optimizer import optimize
from app.optimizer.dp import solve_dp
from app.validator import replay, totals_from_plan

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["input"]["scenario_id"] for c in CASES])
def test_optimizer_matches_reference(case: dict) -> None:
    scenario, directives = case["input"], case["expected_output"]["directive_interpretation"]
    plan, _ = optimize(scenario, directives)
    assert replay(scenario, directives, plan) == []
    assert abs(totals_from_plan(scenario, plan)["total_cost_bdt"] - case["expected_output"]["total_cost_bdt"]) <= 0.01


@pytest.mark.parametrize("case", CASES, ids=[c["input"]["scenario_id"] for c in CASES])
def test_dp_oracle_agrees(case: dict) -> None:
    scenario, directives = case["input"], case["expected_output"]["directive_interpretation"]
    plan = solve_dp(scenario, directives, step=2.5)
    assert replay(scenario, directives, plan) == []
    assert abs(totals_from_plan(scenario, plan)["total_cost_bdt"] - case["expected_output"]["total_cost_bdt"]) <= 0.01


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Force the degraded path so the API test is deterministic and needs no network.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.parametrize("case", CASES, ids=[c["input"]["scenario_id"] for c in CASES])
def test_api_contract(client: TestClient, case: dict) -> None:
    inp = case["input"]
    r = client.post("/optimize-energy", json=inp)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["scenario_id"] == inp["scenario_id"]
    assert [d["note_index"] for d in out["directive_interpretation"]] == list(range(len(inp["operator_notes"])))
    for d in out["directive_interpretation"]:
        assert (d["directive_type"] == "no_op") == (d["applies"] is False) == (d["structured_adjustment"] is None)
    assert len(out["hourly_plan"]) == 24
    totals = {k: out[k] for k in ("total_grid_kwh", "total_cost_bdt", "peak_grid_kwh")}
    assert replay(inp, out["directive_interpretation"], out["hourly_plan"], totals) == []
    assert isinstance(out["plan_summary"], str) and out["plan_summary"]


def test_malformed_json_is_400(client: TestClient) -> None:
    r = client.post("/optimize-energy", content=b"{nope", headers={"content-type": "application/json"})
    assert r.status_code == 400 and "error" in r.json()


def test_structurally_invalid_is_400(client: TestClient) -> None:
    r = client.post("/optimize-energy", json={"scenario_id": "x", "operator_notes": [], "hours": [], "battery": {}})
    assert r.status_code == 400
