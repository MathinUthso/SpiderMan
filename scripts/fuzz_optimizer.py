"""Randomised stress test of the optimizer.

Group A: integer-lattice scenarios -> LP cost must equal the exact DP (step=1) cost.
Group B: fractional scenarios (awkward factors, 3-dp inputs) -> LP plan must survive the validator
         without needing the DP fallback, and nothing may raise anything except Infeasible.

Usage: python scripts/fuzz_optimizer.py [--a 120] [--b 400] [--seed 7]
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.optimizer import optimize  # noqa: E402
from app.optimizer.dp import solve_dp  # noqa: E402
from app.optimizer.lp import solve_lp  # noqa: E402
from app.schemas import Infeasible  # noqa: E402
from app.validator import replay, totals_from_plan  # noqa: E402


def window(rng: random.Random) -> list[int]:
    a = rng.randint(0, 22)
    return list(range(a, min(24, a + rng.randint(1, 6))))


def scenario(rng: random.Random, integer: bool) -> tuple[dict, list[dict]]:
    q = (lambda x: float(int(x))) if integer else (lambda x: round(x, rng.choice([0, 1, 3])))
    cap = q(rng.uniform(40, 200 if integer else 500))
    bmin = q(rng.uniform(0, 0.4 * cap))
    init = rng.choice([bmin, cap, q(rng.uniform(bmin, cap))])
    init = min(max(init, bmin), cap)
    battery = {
        "capacity_kwh": cap, "initial_energy_kwh": init, "minimum_energy_kwh": bmin,
        "max_charge_kwh_per_hour": rng.choice([0.0, q(rng.uniform(1, 80))]) if rng.random() < 0.1 else q(rng.uniform(5, 80)),
        "max_discharge_kwh_per_hour": rng.choice([0.0, q(rng.uniform(1, 80))]) if rng.random() < 0.1 else q(rng.uniform(5, 80)),
    }
    flat = rng.random() < 0.1
    hours = []
    for h in range(24):
        sun = max(0.0, 1 - abs(h - 12) / 6) * rng.uniform(0, 320)
        hours.append({
            "hour": h,
            "demand_kwh": 0.0 if rng.random() < 0.05 else q(rng.uniform(20, 260)),
            "solar_kwh": 0.0 if rng.random() < 0.15 else (float(int(sun / 2) * 2) if integer else q(sun)),
            "tariff_bdt_per_kwh": 7.0 if flat else q(rng.uniform(1, 40)) if not integer else float(rng.randint(1, 12)),
        })
    dirs: list[dict] = []
    for i in range(rng.randint(0, 3)):
        t = rng.choice(["solar_reduction", "minimum_battery_reserve", "no_charge_window", "no_discharge_window", "max_grid_window"])
        adj: dict = {"hours": window(rng)}
        if t == "solar_reduction":
            adj["factor"] = rng.choice([0.0, 0.5, 1.0]) if integer else rng.choice([0.0, 0.2, 0.25, 0.333, 0.667, 0.9, 1.0])
        elif t == "minimum_battery_reserve":
            adj["minimum_energy_kwh"] = q(rng.uniform(0, cap))
        elif t == "max_grid_window":
            adj["max_grid_kwh"] = q(rng.uniform(0, 300))
        dirs.append({"note_index": i, "applies": True, "directive_type": t, "structured_adjustment": adj, "explanation": "fuzz"})
    return {"scenario_id": "FUZZ", "operator_notes": ["x"] * max(1, len(dirs)), "hours": hours, "battery": battery}, dirs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=int, default=120)
    ap.add_argument("--b", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    stats: Counter = Counter()
    problems: list[str] = []
    t0 = time.perf_counter()

    for group, n, integer in (("A", args.a, True), ("B", args.b, False)):
        for k in range(n):
            scen, dirs = scenario(rng, integer)
            tag = f"{group}{k}"
            # 1. raw LP on its own: does its plan pass the validator without the DP safety net?
            lp_plan = None
            try:
                lp_plan = solve_lp(scen, dirs)
                errs = replay(scen, dirs, lp_plan)
                if errs:
                    stats["lp_plan_invalid"] += 1
                    if len(problems) < 12:
                        problems.append(f"{tag}: raw LP plan INVALID -> {errs[:2]} | battery={scen['battery']}")
            except Infeasible:
                stats["lp_infeasible"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["lp_crash"] += 1
                if len(problems) < 12:
                    problems.append(f"{tag}: LP CRASH {type(exc).__name__}: {str(exc)[:120]}")
            # 2. the public entry point must only ever raise Infeasible
            try:
                plan, solver = optimize(scen, dirs)
                stats[f"optimize_ok_{solver}"] += 1
                cost = totals_from_plan(scen, plan)["total_cost_bdt"]
                odd = sum(1 for p in plan for f in ("grid_kwh", "solar_used_kwh", "battery_kwh", "battery_energy_after_kwh")
                          if abs(p[f] - round(p[f], 2)) > 1e-9)
                if odd:
                    stats["plans_with_gt2dp_values"] += 1
            except Infeasible:
                stats["optimize_infeasible"] += 1
                cost = None
            except Exception as exc:  # noqa: BLE001
                stats["optimize_CRASH"] += 1
                cost = None
                if len(problems) < 12:
                    problems.append(f"{tag}: optimize() CRASH {type(exc).__name__}: {str(exc)[:120]}")
            # 3. exact oracle on the integer lattice
            if integer:
                try:
                    dp_cost = totals_from_plan(scen, solve_dp(scen, dirs, step=1.0))["total_cost_bdt"]
                except Infeasible:
                    dp_cost = None
                if (cost is None) != (dp_cost is None):
                    stats["feasibility_disagreement"] += 1
                    if len(problems) < 12:
                        problems.append(f"{tag}: LP feasible={cost is not None} but DP feasible={dp_cost is not None}")
                elif cost is not None and abs(cost - dp_cost) > 0.011:
                    stats["cost_mismatch"] += 1
                    if len(problems) < 12:
                        problems.append(f"{tag}: LP cost {cost} != DP oracle {dp_cost} (diff {cost - dp_cost:+.2f})")
                else:
                    stats["oracle_agree"] += 1

    print(f"ran A={args.a} B={args.b} in {time.perf_counter() - t0:.1f}s (seed {args.seed})")
    for k, v in sorted(stats.items()):
        print(f"  {k:28} {v}")
    print("PROBLEMS:" if problems else "no problems found")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
