"""Deterministic validation of LLM output (spec §8). Anything invalid degrades to no_op.

The LLM returns a flat record per note; this module assembles the exact
`structured_adjustment` shape per directive type and enforces every guardrail.
"""

from __future__ import annotations

import math
from typing import Any

from app.schemas import DirectiveType

ALLOWED = {t.value for t in DirectiveType}


def _no_op(i: int, why: str) -> dict:
    return {
        "note_index": i,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": why,
    }


def _hours(raw: Any) -> list[int] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: set[int] = set()
    for h in raw:
        if isinstance(h, bool) or not isinstance(h, (int, float)) or float(h) != int(h):
            return None
        h = int(h)
        if not 0 <= h <= 23:
            return None
        out.add(h)
    return sorted(out)


def _num(raw: Any, lo: float, hi: float) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    v = float(raw)
    if not math.isfinite(v) or v < lo - 1e-9 or v > hi + 1e-9:
        return None
    return min(max(v, lo), hi)


def _adjustment(t: str, rec: dict, battery: dict) -> dict | None:
    hours = _hours(rec.get("hours"))
    if hours is None:
        return None
    if t == "solar_reduction":
        f = _num(rec.get("factor"), 0.0, 1.0)
        return None if f is None else {"hours": hours, "factor": f}
    if t == "minimum_battery_reserve":
        r = _num(rec.get("minimum_energy_kwh"), 0.0, float(battery["capacity_kwh"]))
        return None if r is None else {"hours": hours, "minimum_energy_kwh": r}
    if t == "max_grid_window":
        g = _num(rec.get("max_grid_kwh"), 0.0, float("inf"))
        return None if g is None else {"hours": hours, "max_grid_kwh": g}
    if t in ("no_charge_window", "no_discharge_window"):
        return {"hours": hours}
    return None


def validate_llm_output(raw: Any, n_notes: int, battery: dict) -> list[dict]:
    """Return exactly n_notes directive entries in note_index order, all guardrails enforced."""
    records: dict[int, dict] = {}
    items = raw.get("interpretations") if isinstance(raw, dict) else raw
    if isinstance(items, list):
        for rec in items:
            if not isinstance(rec, dict):
                continue
            i = rec.get("note_index")
            if isinstance(i, bool) or not isinstance(i, (int, float)) or int(i) != i:
                continue
            i = int(i)
            if 0 <= i < n_notes and i not in records:  # first mapping wins; duplicates dropped
                records[i] = rec

    out: list[dict] = []
    for i in range(n_notes):
        rec = records.get(i)
        if rec is None:
            out.append(_no_op(i, "No valid interpretation was produced for this note; treated as not affecting the schedule."))
            continue
        t = rec.get("directive_type")
        expl = rec.get("explanation")
        expl = expl.strip() if isinstance(expl, str) and expl.strip() else ""
        if t not in ALLOWED:
            out.append(_no_op(i, "Unsupported directive type returned by the model; treated as no_op."))
            continue
        if t == "no_op":
            out.append(_no_op(i, expl or "This note does not affect today's energy schedule."))
            continue
        adj = _adjustment(t, rec, battery)
        if adj is None:
            out.append(_no_op(i, "Directive values failed validation; treated as no_op to avoid inventing constraints."))
            continue
        out.append({
            "note_index": i,
            "applies": True,
            "directive_type": t,
            "structured_adjustment": adj,
            "explanation": expl or f"Applies {t} for hours {adj['hours']}.",
        })
    return out
