"""D3/D4: hit the FastAPI app in-process with the 10 public cases and validate every response.

Usage: python scripts/check_api.py            (uses .env if present; without keys -> degraded path, still 200)
       python scripts/check_api.py --no-llm   (forces degraded path to test resilience)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
if "--no-llm" in sys.argv:
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["GROQ_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.validator import replay  # noqa: E402

CASES = ROOT / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
REQUIRED = {"scenario_id", "directive_interpretation", "hourly_plan", "total_grid_kwh", "total_cost_bdt", "peak_grid_kwh", "plan_summary"}


def main() -> int:
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
    print("health OK")

    r = client.post("/optimize-energy", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400, f"malformed JSON -> {r.status_code}"
    r = client.post("/optimize-energy", json={"scenario_id": "x", "operator_notes": [], "hours": [], "battery": {}})
    assert r.status_code == 400, f"structurally invalid -> {r.status_code}"
    print("400 handling OK")

    data = json.loads(CASES.read_text(encoding="utf-8"))
    failed = 0
    for case in data["cases"]:
        inp = case["input"]
        r = client.post("/optimize-energy", json=inp)
        if r.status_code != 200:
            print(f"[FAIL] {inp['scenario_id']} HTTP {r.status_code}: {r.text[:200]}")
            failed += 1
            continue
        out = r.json()
        missing = REQUIRED - set(out)
        errs = replay(inp, out["directive_interpretation"], out["hourly_plan"],
                      {k: out[k] for k in ("total_grid_kwh", "total_cost_bdt", "peak_grid_kwh")})
        n_ok = len(out["directive_interpretation"]) == len(inp["operator_notes"]) and \
            [d["note_index"] for d in out["directive_interpretation"]] == list(range(len(inp["operator_notes"])))
        ref = case["expected_output"]["total_cost_bdt"]
        good = not missing and not errs and n_ok and out["scenario_id"] == inp["scenario_id"]
        failed += not good
        tag = "OK  " if good else "FAIL"
        print(f"[{tag}] {inp['scenario_id']} cost={out['total_cost_bdt']:.2f} (ref {ref}) missing={missing or '-'} errs={errs[:2] or '-'}")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
