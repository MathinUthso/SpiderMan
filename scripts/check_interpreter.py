"""C6: run the 10 public cases through the live interpreter and compare to expected directives.

Usage: python scripts/check_interpreter.py   (reads .env for GEMINI_API_KEY / GROQ_API_KEY)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.interpreter import interpret  # noqa: E402

CASES = ROOT / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def same(got: dict, exp: dict) -> bool:
    if got["directive_type"] != exp["directive_type"] or got["applies"] != exp["applies"]:
        return False
    g, e = got["structured_adjustment"], exp["structured_adjustment"]
    if g is None or e is None:
        return g is e
    if g["hours"] != e["hours"]:
        return False
    for k in ("factor", "minimum_energy_kwh", "max_grid_kwh"):
        if k in e and abs(float(g.get(k, -1)) - float(e[k])) > 0.01:
            return False
    return True


async def main() -> int:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    total = ok = 0
    lat: list[float] = []
    for case in data["cases"]:
        inp = case["input"]
        t0 = time.perf_counter()
        got, degraded = await interpret(inp["operator_notes"], inp["battery"])
        lat.append(time.perf_counter() - t0)
        for g, e, note in zip(got, case["expected_output"]["directive_interpretation"], inp["operator_notes"]):
            total += 1
            hit = same(g, e)
            ok += hit
            mark = "OK " if hit else "MISS"
            print(f"[{mark}] {inp['scenario_id']} n{g['note_index']} got={g['directive_type']} {g['structured_adjustment']}")
            if not hit:
                print(f"       exp={e['directive_type']} {e['structured_adjustment']}\n       note: {note}")
        if degraded:
            print(f"       !! {inp['scenario_id']} DEGRADED (all providers failed)")
    lat.sort()
    print(f"\nnotes matched: {ok}/{total}   latency p50={lat[len(lat)//2]:.2f}s max={lat[-1]:.2f}s")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
