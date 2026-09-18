"""Orchestrator: prompt -> Gemini -> guardrails -> validated directives."""

from .prompt import build_prompt
from .client import call_gemini
from .guardrails import validate_directives
from .types import DirectiveInterpretation


def interpret_operators(
    notes: list[str],
    battery: dict,
) -> tuple[list[DirectiveInterpretation] | None, str | None]:
    """Interpret operator notes into structured directives.

    Args:
        notes: List of 1-3 natural-language operator notes.
        battery: Battery config dict with capacity_kwh, initial_energy_kwh,
                 minimum_energy_kwh, max_charge_kwh_per_hour,
                 max_discharge_kwh_per_hour.

    Returns:
        On success: (list of DirectiveInterpretation, None)
        On failure: (None, error message string)
    """
    # 1. Build prompt
    prompt = build_prompt(notes, battery)

    # 2. Call Gemini
    try:
        raw_directives = call_gemini(prompt)
    except Exception as e:
        return None, f"LLM call failed: {str(e)}"

    # 3. Run guardrails
    result = validate_directives(
        raw_directives, notes, battery["capacity_kwh"]
    )

    if isinstance(result, str):
        return None, result

    # 4. Return validated directives
    return result, None
