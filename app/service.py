"""Pipeline glue: interpret → guardrails → optimize → validate → totals → response."""

from __future__ import annotations

import logging
import time

from app.interpreter import interpret
from app.optimizer import optimize
from app.schemas import OptimizeRequest, OptimizeResponse
from app.validator import replay, totals_from_plan

log = logging.getLogger(__name__)


def build_summary(directives: list[dict], plan: list[dict], solver: str, degraded: bool) -> str:
    applied = [d for d in directives if d.get("applies")]
    parts: list[str] = []
    if degraded:
        parts.append("Operator notes could not be interpreted by the language model; the base schedule is returned.")
    elif applied:
        kinds = ", ".join(sorted({d["directive_type"] for d in applied}))
        parts.append(f"Applied {len(applied)} operator directive(s) ({kinds}) before scheduling.")
    else:
        parts.append("No operator note affected the schedule.")
    charge_hours = [p["hour"] for p in plan if p["battery_action"] == "charge"]
    discharge_hours = [p["hour"] for p in plan if p["battery_action"] == "discharge"]
    if charge_hours and discharge_hours:
        parts.append(
            f"Battery charges in hours {charge_hours[0]}-{charge_hours[-1]} and discharges in hours "
            f"{discharge_hours[0]}-{discharge_hours[-1]} to shift load toward cheaper tariffs, "
            "returning to its initial level by hour 23."
        )
    parts.append(f"Schedule minimises grid cost ({solver} solver) while using all available effective solar.")
    return " ".join(parts)


async def run_pipeline(req: OptimizeRequest) -> OptimizeResponse:
    t0 = time.perf_counter()
    scenario = req.model_dump(mode="json")

    directives, degraded = await interpret(req.operator_notes, scenario["battery"])
    t1 = time.perf_counter()

    plan, solver = optimize(scenario, directives)
    errs = replay(scenario, directives, plan)
    if errs:  # optimize() already validated; this is belt-and-braces
        raise RuntimeError(f"plan failed final replay: {errs[:3]}")
    totals = totals_from_plan(scenario, plan)
    t2 = time.perf_counter()

    log.info(
        "scenario=%s interpret=%.2fs optimize=%.2fs solver=%s degraded=%s cost=%.2f",
        req.scenario_id, t1 - t0, t2 - t1, solver, degraded, totals["total_cost_bdt"],
    )
    return OptimizeResponse(
        scenario_id=req.scenario_id,
        directive_interpretation=directives,
        hourly_plan=plan,
        plan_summary=build_summary(directives, plan, solver, degraded),
        **totals,
    )
