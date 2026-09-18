"""Optimizer entry point: exact LP first, validator-gated, lattice DP as fallback (plan §3)."""

from __future__ import annotations

import logging

from app.schemas import Infeasible
from app.validator import replay

log = logging.getLogger(__name__)


def optimize(scenario: dict, directives: list[dict]) -> tuple[list[dict], str]:
    """Return (plan, solver_name). Plan is validated before it is returned."""
    errors: list[str] = []
    try:
        from app.optimizer.lp import solve_lp

        plan = solve_lp(scenario, directives)
        errs = replay(scenario, directives, plan)
        if not errs:
            return plan, "lp"
        errors.append(f"lp plan rejected by validator: {errs[:3]}")
        log.warning(errors[-1])
    except Infeasible as exc:
        errors.append(f"lp infeasible: {exc}")
        log.warning(errors[-1])
    except Exception as exc:  # scipy missing, numerical failure, etc.
        errors.append(f"lp failed: {type(exc).__name__}")
        log.warning(errors[-1])

    from app.optimizer.dp import solve_dp

    try:
        plan = solve_dp(scenario, directives, step=1.0)
    except Infeasible as exc:
        raise Infeasible("; ".join(errors + [f"dp infeasible: {exc}"])) from exc
    errs = replay(scenario, directives, plan)
    if errs:
        raise Infeasible("; ".join(errors + [f"dp plan rejected: {errs[:3]}"]))
    return plan, "dp"
