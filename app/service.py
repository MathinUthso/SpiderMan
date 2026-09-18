"""Pipeline glue: interpret → guardrails → optimize → validate → totals → response."""

from __future__ import annotations

import itertools
import logging
import time

from app.interpreter import interpret
from app.optimizer import optimize
from app.schemas import Infeasible, OptimizeRequest, OptimizeResponse
from app.validator import replay, totals_from_plan

log = logging.getLogger(__name__)


def _demote(d: dict) -> dict:
    return {
        "note_index": d["note_index"],
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": (
            f"Read as {d['directive_type']} {d['structured_adjustment']}, but it cannot be satisfied together "
            "with the other constraints of this scenario, so it was not applied."
        ),
    }


def solve_with_relaxation(scenario: dict, directives: list[dict]) -> tuple[list[dict], list[dict], str, list[int]]:
    """Optimize; if the directives are jointly infeasible, drop the fewest possible (latest notes
    first) and say so in the response instead of failing the whole request.

    Organizer scenarios are guaranteed feasible, so infeasibility means a note was misread. A valid
    200 that is honest about what was not applied always scores at least as well as a 422, which
    forfeits the entire case including the interpretations that were right.
    """
    try:
        plan, solver = optimize(scenario, directives)
        return directives, plan, solver, []
    except Infeasible:
        pass
    active = [d["note_index"] for d in directives if d.get("applies")]
    for k in range(1, len(active) + 1):
        for dropped in sorted(itertools.combinations(active, k), key=lambda c: [-i for i in c]):
            trial = [_demote(d) if d["note_index"] in dropped else d for d in directives]
            try:
                plan, solver = optimize(scenario, trial)
            except Infeasible:
                continue
            log.warning("directives infeasible together; not applied: notes %s", list(dropped))
            return trial, plan, solver, list(dropped)
    raise Infeasible("scenario is infeasible even with no operator directives applied")


def build_summary(directives: list[dict], plan: list[dict], solver: str, degraded: bool, dropped: list[int]) -> str:
    applied = [d for d in directives if d.get("applies")]
    parts: list[str] = []
    if degraded:
        parts.append("Operator notes could not be interpreted by the language model; the base schedule is returned.")
    elif applied:
        kinds = ", ".join(sorted({d["directive_type"] for d in applied}))
        parts.append(f"Applied {len(applied)} operator directive(s) ({kinds}) before scheduling.")
    else:
        parts.append("No operator note affected the schedule.")
    if dropped:
        parts.append(f"Note(s) {dropped} could not be satisfied together with the other constraints and were not applied.")
    charge_hours = [p["hour"] for p in plan if p["battery_action"] == "charge"]
    discharge_hours = [p["hour"] for p in plan if p["battery_action"] == "discharge"]
    if charge_hours and discharge_hours:
        parts.append(
            f"The battery charges in {len(charge_hours)} hour(s) (first at hour {charge_hours[0]}) and discharges in "
            f"{len(discharge_hours)} hour(s) (first at hour {discharge_hours[0]}), shifting energy toward expensive "
            "hours and returning to its initial level by hour 23."
        )
    else:
        parts.append("The battery is not cycled; demand is met from solar and grid directly.")
    parts.append("Grid cost is minimised subject to energy balance, battery limits and every applied directive.")
    return " ".join(parts)


async def run_pipeline(req: OptimizeRequest) -> OptimizeResponse:
    t0 = time.perf_counter()
    scenario = req.model_dump(mode="json")

    directives, degraded = await interpret(req.operator_notes, scenario["battery"])
    t1 = time.perf_counter()

    directives, plan, solver, dropped = solve_with_relaxation(scenario, directives)
    errs = replay(scenario, directives, plan)
    if errs:  # optimize() already validated; this is belt-and-braces
        raise RuntimeError(f"plan failed final replay: {errs[:3]}")
    totals = totals_from_plan(scenario, plan)
    t2 = time.perf_counter()

    log.info(
        "scenario=%s interpret=%.2fs optimize=%.2fs solver=%s degraded=%s dropped=%s cost=%.2f",
        req.scenario_id, t1 - t0, t2 - t1, solver, degraded, dropped, totals["total_cost_bdt"],
    )
    return OptimizeResponse(
        scenario_id=req.scenario_id,
        directive_interpretation=directives,
        hourly_plan=plan,
        plan_summary=build_summary(directives, plan, solver, degraded, dropped),
        **totals,
    )
