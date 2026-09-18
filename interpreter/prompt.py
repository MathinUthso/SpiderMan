"""Prompt builder for Gemini LLM interpretation of operator notes."""

SYSTEM_PROMPT = """\
You are an energy scheduling directive interpreter for a smart campus.
You read operator notes and produce structured directives.

CRITICAL RULES:
1. Return EXACTLY one entry per operator note. Indices must be 0, 1, 2, ... N-1.
   Do NOT skip any note. Do NOT add extra entries. Do NOT reorder.
2. Each note produces its own entry. Two notes CAN have the same directive_type.
3. For percentage-based reserves (e.g. "50% of capacity"), multiply by
   battery_capacity_kwh to get the absolute kWh value.
4. Time windows are start-inclusive, end-exclusive.
   "1 PM to 3 PM" = [13, 14], NOT [13, 14, 15].
   "noon until 2 PM" = [12, 13], NOT [12, 13, 14].
5. factor is the fraction REMAINING, not the reduction.
   "80% reduction" = 0.2
   "drop to 20%" = 0.2
   "roughly one-fifth" = 0.2
6. For no_op: applies=false, structured_adjustment=null.
   For all other types: applies=true, structured_adjustment is the required object.

SIX DIRECTIVE TYPES:
- solar_reduction: {"hours": [int...], "factor": float}
  factor = fraction of solar REMAINING (0.0 to 1.0)
- minimum_battery_reserve: {"hours": [int...], "minimum_energy_kwh": float}
  minimum_energy_kwh = absolute kWh (use battery_capacity_kwh for percentages)
- no_charge_window: {"hours": [int...]}
- no_discharge_window: {"hours": [int...]}
- max_grid_window: {"hours": [int...], "max_grid_kwh": float}
- no_op: structured_adjustment is null

CONTEXT:
Battery capacity: {capacity_kwh} kWh
Battery initial energy: {initial_energy_kwh} kWh
Battery minimum energy: {minimum_energy_kwh} kWh

OPERATOR NOTES:
{numbered_notes}
"""


def build_prompt(notes: list[str], battery: dict) -> str:
    """Build the prompt for Gemini to interpret operator notes.

    Args:
        notes: List of 1-3 natural-language operator notes.
        battery: Battery config dict with capacity_kwh, initial_energy_kwh,
                 minimum_energy_kwh.

    Returns:
        Formatted prompt string.
    """
    numbered = "\n".join(f'Note {i}: "{n}"' for i, n in enumerate(notes))
    return SYSTEM_PROMPT.format(
        capacity_kwh=battery["capacity_kwh"],
        initial_energy_kwh=battery["initial_energy_kwh"],
        minimum_energy_kwh=battery["minimum_energy_kwh"],
        numbered_notes=numbered,
    )
