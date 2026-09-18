"""B5: run the 10 public cases through the optimizer using the reference directives.

Usage: python scripts/check_optimizer.py
Passes when every case is validator-clean and within 0.01 BDT of the reference cost.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.optimizer import optimize  # noqa: E402
from app.optimizer.dp import solve_dp  # noqa: E402
from app.validator import replay, totals_from_plan  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "testcases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def main() -> int:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    failed = 0
    print(f"{'case':10} {'ref':>10} {'lp':>10} {'dp':>10} {'ms':>6}  status")
    for case in data["cases"]:
        scenario = case["input"]
        directives = case["expected_output"]["directive_interpretation"]
        ref = case["expected_output"]["total_cost_bdt"]
        t0 = time.perf_counter()
        plan, solver = optimize(scenario, directives)
        ms = (time.perf_counter() - t0) * 1000
        errs = replay(scenario, directives, plan, totals_from_plan(scenario, plan))
        cost = totals_from_plan(scenario, plan)["total_cost_bdt"]
        dp_cost = totals_from_plan(scenario, solve_dp(scenario, directives, step=2.5))["total_cost_bdt"]
        ok = not errs and abs(cost - ref) <= 0.01 and abs(dp_cost - ref) <= 0.01
        failed += not ok
        status = "OK" if ok else f"FAIL {errs[:2]}"
        print(f"{scenario['scenario_id']:10} {ref:10.2f} {cost:10.2f} {dp_cost:10.2f} {ms:6.0f}  {status} [{solver}]")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
