"""Run the team-authored edge-case pack against the app in-process.

Usage:
  python scripts/check_edge_pack.py --malformed            # 12 malformed inputs, no LLM needed
  python scripts/check_edge_pack.py --edge --delay 4       # 33 edge cases through the live LLM, paced
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.validator import replay  # noqa: E402

PACK = ROOT / "testcases" / "GridWise_Edge_Case_Test_Pack_Merged.json"


def same(got: dict, exp: dict) -> bool:
    if got["directive_type"] != exp["directive_type"] or got["applies"] != exp["applies"]:
        return False
    g, e = got["structured_adjustment"], exp["structured_adjustment"]
    if g is None or e is None:
        return g is e
    if g.get("hours") != e.get("hours"):
        return False
    return all(abs(float(g.get(k, -1)) - float(e[k])) <= 0.01
               for k in ("factor", "minimum_energy_kwh", "max_grid_kwh") if k in e)


def run_malformed(client: TestClient, cases: list[dict]) -> None:
    print(f"--- malformed inputs ({len(cases)}) ---")
    for c in cases:
        inp = c["input"]
        if isinstance(inp, str):
            r = client.post("/optimize-energy", content=inp.encode(), headers={"content-type": "application/json"})
        else:
            r = client.post("/optimize-energy", json=inp)
        crashed = r.status_code >= 500
        print(f"[{'CRASH' if crashed else 'ok   '}] {c['id']} HTTP {r.status_code} | issue: {str(c.get('issue'))[:70]}")
        print(f"         expected: {str(c.get('expected_behavior'))[:110]}")


def run_edge(client: TestClient, cases: list[dict], delay: float) -> None:
    print(f"--- edge cases ({len(cases)}), {delay}s pacing ---")
    notes_ok = notes_total = plans_ok = 0
    for c in cases:
        r = client.post("/optimize-energy", json=c["input"])
        if r.status_code != 200:
            print(f"[HTTP {r.status_code}] {c['id']} {c.get('edge_case_focus', '')[:80]} | {r.text[:120]}")
            time.sleep(delay)
            continue
        out = r.json()
        got, exp = out["directive_interpretation"], c.get("expected_directive_interpretation")
        if not isinstance(exp, list):  # some cases only specify behaviour, not an interpretation
            errs = replay(c["input"], got, out["hourly_plan"])
            plans_ok += not errs
            print(f"[{'OK  ' if not errs else 'MISS'}] {c['id']} {c.get('edge_case_focus', '')[:70]}  (no expected interpretation; plan {'valid' if not errs else 'INVALID'})")
            print(f"        got: {[(g['directive_type'], g['structured_adjustment']) for g in got]}")
            time.sleep(delay)
            continue
        errs = replay(c["input"], got, out["hourly_plan"],
                      {k: out[k] for k in ("total_grid_kwh", "total_cost_bdt", "peak_grid_kwh")})
        plans_ok += not errs
        hits = [same(g, e) for g, e in zip(got, exp)] if len(got) == len(exp) else [False] * len(exp)
        notes_ok += sum(hits)
        notes_total += len(exp)
        degraded = "could not be interpreted" in out["plan_summary"]
        tag = "OK  " if all(hits) and not errs else "MISS"
        print(f"[{tag}] {c['id']} {c.get('edge_case_focus', '')[:78]}{'  (DEGRADED: no LLM answer)' if degraded else ''}")
        if not all(hits):
            for g, e, h in zip(got, exp, hits):
                if not h:
                    print(f"        n{e['note_index']} got={g['directive_type']} {g['structured_adjustment']}")
                    print(f"           exp={e['directive_type']} {e['structured_adjustment']}")
                    print(f"           note: {c['input']['operator_notes'][e['note_index']][:120]}")
        if errs:
            print(f"        PLAN INVALID: {errs[:2]}")
        time.sleep(delay)
    print(f"\nnotes matched {notes_ok}/{notes_total} | valid plans {plans_ok}/{len(cases)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--malformed", action="store_true")
    ap.add_argument("--edge", action="store_true")
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--start", type=int, default=1, help="1-based index of the first edge case to run")
    args = ap.parse_args()
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    client = TestClient(app, raise_server_exceptions=False)
    if args.malformed or not args.edge:
        run_malformed(client, pack["malformed_input_cases"])
    if args.edge:
        run_edge(client, pack["directive_interpretation_edge_cases"][args.start - 1:], args.delay)


if __name__ == "__main__":
    main()
