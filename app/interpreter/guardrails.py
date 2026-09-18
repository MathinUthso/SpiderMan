"""Deterministic validation of LLM output (spec §8). Anything invalid degrades to no_op.

The LLM returns a flat record per note with one numeric slot (`value`); this module assembles the
exact `structured_adjustment` shape per directive type and enforces every guardrail. The model
decides WHAT a note means; this module only normalises structure and rejects what is invalid.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from app.schemas import DirectiveType

log = logging.getLogger(__name__)

ALLOWED = {t.value for t in DirectiveType}
VALUE_FIELD = {
    "solar_reduction": "factor",
    "minimum_battery_reserve": "minimum_energy_kwh",
    "max_grid_window": "max_grid_kwh",
}
NUMERIC_SLOTS = ("value", "factor", "minimum_energy_kwh", "max_grid_kwh")


def _no_op(i: int, why: str) -> dict:
    return {
        "note_index": i,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": why,
    }


def _hours(raw: Any) -> list[int] | None:
    """Unique ascending ints in 0..23. Non-integers reject the list; an hour outside the day
    (typically a stray 24 for "all day") is dropped rather than discarding the whole directive."""
    if not isinstance(raw, list) or not raw:
        return None
    out: set[int] = set()
    for h in raw:
        if isinstance(h, bool) or not isinstance(h, (int, float)) or float(h) != int(h):
            return None
        h = int(h)
        if 0 <= h <= 23:
            out.add(h)
        else:
            log.warning("guardrails: dropped out-of-range hour %s", h)
    return sorted(out) or None


def _finite(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    v = float(raw)
    return v if math.isfinite(v) else None


def _num(raw: Any, lo: float, hi: float) -> float | None:
    v = _finite(raw)
    if v is None or v < lo - 1e-9 or v > hi + 1e-9:
        return None
    return min(max(v, lo), hi)


def _pick_value(t: str, rec: dict) -> float | None:
    """The record's single number. Preference: the spec-named field, then `value`, then - only if
    every other numeric slot agrees on one number - that number (the model put it in the wrong slot)."""
    named = _finite(rec.get(VALUE_FIELD[t]))
    if named is not None:
        return named
    generic = _finite(rec.get("value"))
    if generic is not None:
        return generic
    others = {v for k in NUMERIC_SLOTS if (v := _finite(rec.get(k))) is not None}
    if len(others) == 1:
        log.warning("guardrails: %s value recovered from a misplaced numeric field: %s", t, json.dumps(rec, default=str)[:300])
        return others.pop()
    return None


def _adjustment(t: str, rec: dict, battery: dict) -> dict | None:
    hours = _hours(rec.get("hours"))
    if hours is None:
        return None
    if t in ("no_charge_window", "no_discharge_window"):
        return {"hours": hours}
    if t not in VALUE_FIELD:
        return None
    v = _pick_value(t, rec)
    if v is None:
        return None
    capacity = float(battery["capacity_kwh"])
    if t == "solar_reduction":
        # A percentage such as 25 instead of the fraction 0.25. Values in (1, 2) are NOT salvaged:
        # 1.4 or 1.5 means "solar rises to 140-150%", which no supported directive can express.
        if 2.0 <= v <= 100.0:
            log.warning("guardrails: solar factor %s read as a percentage", v)
            v = v / 100.0
        f = _num(v, 0.0, 1.0)
        return None if f is None else {"hours": hours, "factor": round(f, 6)}
    if t == "minimum_battery_reserve":
        if 0.0 < v < 1.0 and capacity >= 10.0:  # a share of capacity such as 0.5 instead of kWh
            log.warning("guardrails: reserve %s read as a share of capacity %s", v, capacity)
            v = v * capacity
        r = _num(v, 0.0, capacity)
        return None if r is None else {"hours": hours, "minimum_energy_kwh": round(r, 6)}
    g = _num(v, 0.0, float("inf"))
    return None if g is None else {"hours": hours, "max_grid_kwh": round(g, 6)}


def validate_llm_output(raw: Any, n_notes: int, battery: dict) -> list[dict]:
    """Return exactly n_notes directive entries in note_index order, all guardrails enforced.

    On any validation failure the affected note degrades to no_op rather than crashing, so the
    pipeline always produces a valid response and never invents a constraint.
    """
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
            log.warning("guardrails: no record returned for note %d", i)
            out.append(_no_op(i, "No valid interpretation was produced for this note; treated as not affecting the schedule."))
            continue
        t = rec.get("directive_type")
        expl = rec.get("explanation")
        expl = expl.strip() if isinstance(expl, str) and expl.strip() else ""
        if t not in ALLOWED:
            log.warning("guardrails: unsupported directive_type for note %d: %r", i, t)
            out.append(_no_op(i, "Unsupported directive type returned by the model; treated as no_op."))
            continue
        if t == "no_op":
            out.append(_no_op(i, expl or "This note does not affect today's energy schedule."))
            continue
        # `applies` is normalised to true for every valid non-no_op directive rather than trusted.
        adj = _adjustment(t, rec, battery)
        if adj is None:
            # Model output only (never secrets): keep rejects diagnosable from the service logs.
            log.warning("guardrails: rejected note %d record: %s", i, json.dumps(rec, default=str)[:500])
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
