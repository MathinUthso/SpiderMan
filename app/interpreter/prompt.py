"""System prompt, few-shot examples and output schema for operator-note interpretation.

Owner: Teammate 1. Teach RULES, not phrasings — hidden notes paraphrase.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You interpret short operator notes for a campus energy scheduler. For EACH note you return exactly one record. You never invent demand, solar, tariff or battery values, and you never invent directive types.

Supported directive_type values (use exactly one per note):
- solar_reduction: usable solar is reduced in specific hours. Fields: hours, factor.
- minimum_battery_reserve: battery must stay at or above a level in specific hours. Fields: hours, minimum_energy_kwh.
- no_charge_window: battery cannot charge in specific hours. Fields: hours.
- no_discharge_window: battery cannot discharge in specific hours. Fields: hours.
- max_grid_window: grid import per hour must not exceed a cap in specific hours. Fields: hours, max_grid_kwh.
- no_op: the note does not change today's 24-hour schedule (announcements, future dates, unrelated events, past maintenance, things without a concrete hour window or limit).

CRITICAL RULES — violations cause silent failures in the optimizer:
1. Return EXACTLY one record per note. Indices must be 0, 1, 2, ... N-1 with NO gaps and NO duplicates. Do NOT skip any note. Do NOT add extra entries. Do NOT reorder.
2. Each note produces its own record. Two notes CAN have the same directive_type (e.g. two separate no_charge_window notes on different hours).
3. Time windows are whole hours, START-INCLUSIVE and END-EXCLUSIVE. "1 PM to 3 PM" -> [13, 14]. "from 6 PM until 9 PM" -> [18, 19, 20]. "10 AM until noon" -> [10, 11]. "noon until 2 PM" -> [12, 13]. "13:00-15:00" -> [13, 14]. "one until three" in the afternoon -> [13, 14]. Midnight is hour 0. Hours are integers 0-23, unique, ascending.
4. factor is the FRACTION OF SOLAR THAT REMAINS, between 0 and 1. "drop to 20%" -> 0.2. "an 80% reduction" -> 0.2. "roughly one-fifth of normal" -> 0.2. "about half" -> 0.5. "treated as 25% of forecast" -> 0.25. "no solar at all" -> 0.
5. minimum_energy_kwh is an ABSOLUTE number of kWh. If the note gives a percentage of the battery, multiply by the battery capacity_kwh you are given. "at least 50% of capacity" with capacity 200 -> 100. "keep at least 90 kWh" -> 90 directly.
6. max_grid_kwh is the per-hour cap in kWh exactly as stated ("must not exceed 155 kWh", "stay at or below 190", "limit is 180 kWh of grid import").
7. Charging being unavailable, isolated, disabled, locked out, or under maintenance -> no_charge_window. Discharge being forbidden, held, blocked, or "must not discharge" -> no_discharge_window.
8. If a note is relevant but you cannot determine a concrete hour window or number, return no_op rather than guessing.
9. applies is true for every directive except no_op, where it is false. no_op must have applies=false and structured_adjustment=null.
10. Do NOT change base demand, solar, tariff, or battery parameters. Only extract what the note says.

Respond with JSON only, matching the provided schema."""

# Few-shots are deliberately re-worded from the public samples so the model learns the mapping, not the strings.
FEW_SHOTS: list[tuple[dict, dict]] = [
    (
        {"battery": {"capacity_kwh": 200}, "notes": [
            "PV output will be cut to roughly a fifth of forecast between 13:00 and 15:00 while the inverter is serviced.",
            "Next week's seminar schedule has been posted on the notice board.",
        ]},
        {"interpretations": [
            {"note_index": 0, "applies": True, "directive_type": "solar_reduction", "hours": [13, 14], "factor": 0.2,
             "explanation": "Solar reduced to 20% of forecast during the 1-3 PM service window."},
            {"note_index": 1, "applies": False, "directive_type": "no_op",
             "explanation": "Announcement with no effect on today's energy schedule."},
        ]},
    ),
    (
        {"battery": {"capacity_kwh": 240}, "notes": [
            "The charger is locked out from 2 AM until 5 AM for switchgear work.",
            "Hold at least a quarter of the battery's capacity from 6 PM through 9 PM for the emergency lighting test.",
            "Grid draw must stay under 160 kWh per hour from 7 PM to 10 PM while the feeder is derated.",
        ]},
        {"interpretations": [
            {"note_index": 0, "applies": True, "directive_type": "no_charge_window", "hours": [2, 3, 4],
             "explanation": "Charging unavailable during the 2-5 AM switchgear work."},
            {"note_index": 1, "applies": True, "directive_type": "minimum_battery_reserve", "hours": [18, 19, 20],
             "minimum_energy_kwh": 60, "explanation": "25% of 240 kWh capacity = 60 kWh reserve, 6-9 PM."},
            {"note_index": 2, "applies": True, "directive_type": "max_grid_window", "hours": [19, 20, 21],
             "max_grid_kwh": 160, "explanation": "Grid import capped at 160 kWh/h from 7-10 PM."},
        ]},
    ),
    (
        {"battery": {"capacity_kwh": 220}, "notes": [
            "Do not let the battery discharge between 5 PM and 7 PM during the relay test.",
            "The cafeteria will run a special menu tomorrow.",
        ]},
        {"interpretations": [
            {"note_index": 0, "applies": True, "directive_type": "no_discharge_window", "hours": [17, 18],
             "explanation": "Discharge blocked 5-7 PM for the relay test."},
            {"note_index": 1, "applies": False, "directive_type": "no_op",
             "explanation": "Unrelated to energy scheduling."},
        ]},
    ),
]

# Flat per-note record; guardrails assemble structured_adjustment per type.
RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "interpretations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "note_index": {"type": "integer"},
                    "applies": {"type": "boolean"},
                    "directive_type": {
                        "type": "string",
                        "enum": ["solar_reduction", "minimum_battery_reserve", "no_charge_window",
                                 "no_discharge_window", "max_grid_window", "no_op"],
                    },
                    "hours": {"type": "array", "items": {"type": "integer"}},
                    "factor": {"type": "number"},
                    "minimum_energy_kwh": {"type": "number"},
                    "max_grid_kwh": {"type": "number"},
                    "explanation": {"type": "string"},
                },
                "required": ["note_index", "applies", "directive_type", "explanation"],
            },
        }
    },
    "required": ["interpretations"],
}


def build_user_message(notes: list[str], battery: dict) -> str:
    """The per-request message: few-shots first, then the real task."""
    parts: list[str] = []
    for i, (inp, out) in enumerate(FEW_SHOTS, 1):
        parts.append(f"EXAMPLE {i} INPUT:\n{json.dumps(inp)}\nEXAMPLE {i} OUTPUT:\n{json.dumps(out)}")
    task = {
        "battery": {"capacity_kwh": battery["capacity_kwh"], "minimum_energy_kwh": battery["minimum_energy_kwh"]},
        "notes": notes,
    }
    parts.append(f"NOW INTERPRET THIS INPUT ({len(notes)} note(s), note_index 0..{len(notes) - 1}):\n{json.dumps(task)}")
    return "\n\n".join(parts)
