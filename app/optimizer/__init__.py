"""Optimizer entry point (plan §3).

Attempt order, every plan validated before it is returned:
  1. exact LP
  2. LP with a 0.02 safety margin on every bound (only if rounding pushed attempt 1 over a limit)
  3. lattice DP (only if the LP machinery itself is unavailable or both LP plans were rejected)
An LP that is *infeasible* is final: a continuous relaxation that has no solution has no
lattice solution either, so we do not waste time on the DP.
"""

from __future__ import annotations

import logging

from app.schemas import Infeasible
from app.validator import replay

log = logging.getLogger(__name__)

MARGIN = 0.02


def optimize(scenario: dict, directives: list[dict]) -> tuple[list[dict], str]:
    """Return (plan, solver_name). Raises Infeasible only when no valid plan exists."""
    notes: list[str] = []
    lp_available = True
    try:
        from app.optimizer.lp import solve_lp
    except Exception as exc:  # scipy missing or broken
        lp_available = False
        notes.append(f"lp unavailable: {type(exc).__name__}")
        log.error(notes[-1])

    if lp_available:
        for label, margin in (("lp", 0.0), ("lp-margin", MARGIN)):
            try:
                plan = solve_lp(scenario, directives, margin=margin)
            except Infeasible as exc:
                if margin == 0.0:
                    raise  # genuinely infeasible; nothing else can succeed
                notes.append(f"{label} infeasible: {exc}")
                continue
            except Exception as exc:  # numerical failure
                notes.append(f"{label} failed: {type(exc).__name__}")
                log.warning(notes[-1])
                continue
            errs = replay(scenario, directives, plan)
            if not errs:
                return plan, label
            notes.append(f"{label} plan rejected: {errs[:2]}")
            log.warning(notes[-1])

    from app.optimizer.dp import solve_dp

    for step in (1.0, 0.5):
        try:
            plan = solve_dp(scenario, directives, step=step)
        except Infeasible as exc:
            notes.append(f"dp(step={step}) infeasible: {exc}")
            continue
        errs = replay(scenario, directives, plan)
        if not errs:
            return plan, "dp"
        notes.append(f"dp(step={step}) plan rejected: {errs[:2]}")
    raise Infeasible("; ".join(notes))
