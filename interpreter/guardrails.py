"""Deterministic guardrails for LLM directive interpretation."""

from .types import DirectiveInterpretation, VALID_DIRECTIVE_TYPES


def validate_directives(
    directives: list[DirectiveInterpretation],
    notes: list[str],
    battery_capacity: float,
) -> list[DirectiveInterpretation] | str:
    """Validate LLM output against all guardrails.

    Returns validated list on success, or error message string on failure.
    """
    n = len(notes)

    # Check 1: correct count
    if len(directives) != n:
        return f"Expected {n} entries, got {len(directives)}"

    # Check 2: sequential indices 0..N-1
    indices = [d.note_index for d in directives]
    if indices != list(range(n)):
        return f"Indices must be {list(range(n))}, got {indices}"

    # Check 3: no duplicate indices
    if len(set(indices)) != n:
        return f"Duplicate note_index values found: {indices}"

    for d in directives:
        # Check 4: directive_type allowed
        if d.directive_type not in VALID_DIRECTIVE_TYPES:
            return f"Invalid directive_type: {d.directive_type}"

        # Check 5: applies semantics
        if d.directive_type == "no_op":
            if d.applies is not False:
                return f"no_op must have applies=false, got applies={d.applies}"
            if d.structured_adjustment is not None:
                return f"no_op must have structured_adjustment=null"
        else:
            if d.applies is not True:
                return f"{d.directive_type} must have applies=true, got applies={d.applies}"
            if d.structured_adjustment is None:
                return f"{d.directive_type} requires structured_adjustment"

        # Skip remaining checks for no_op
        if d.directive_type == "no_op":
            continue

        adj = d.structured_adjustment
        if not isinstance(adj, dict):
            return f"structured_adjustment must be a dict for {d.directive_type}"

        # Check 6: hours present
        if "hours" not in adj:
            return f"Missing 'hours' in structured_adjustment for {d.directive_type}"

        hours = adj["hours"]
        if not isinstance(hours, list) or len(hours) == 0:
            return f"hours must be a non-empty list for {d.directive_type}"

        # Check 7: hours are unique integers 0-23, ascending
        if not all(isinstance(h, int) for h in hours):
            return f"All hours must be integers for {d.directive_type}"
        if hours != sorted(set(hours)):
            return f"hours must be unique integers in ascending order for {d.directive_type}"
        if not all(0 <= h <= 23 for h in hours):
            return f"hours must be in range 0-23 for {d.directive_type}"

        # Type-specific checks
        if d.directive_type == "solar_reduction":
            if "factor" not in adj:
                return "Missing 'factor' in solar_reduction"
            factor = adj["factor"]
            if not isinstance(factor, (int, float)):
                return f"factor must be a number, got {type(factor)}"
            if not (0.0 <= factor <= 1.0):
                return f"factor must be 0.0-1.0, got {factor}"

        elif d.directive_type == "minimum_battery_reserve":
            if "minimum_energy_kwh" not in adj:
                return "Missing 'minimum_energy_kwh' in minimum_battery_reserve"
            val = adj["minimum_energy_kwh"]
            if not isinstance(val, (int, float)):
                return f"minimum_energy_kwh must be a number, got {type(val)}"
            if val < 0:
                return f"minimum_energy_kwh must be >= 0, got {val}"
            if val > battery_capacity:
                return f"minimum_energy_kwh ({val}) exceeds battery capacity ({battery_capacity})"

        elif d.directive_type == "max_grid_window":
            if "max_grid_kwh" not in adj:
                return "Missing 'max_grid_kwh' in max_grid_window"
            val = adj["max_grid_kwh"]
            if not isinstance(val, (int, float)):
                return f"max_grid_kwh must be a number, got {type(val)}"
            if val < 0:
                return f"max_grid_kwh must be >= 0, got {val}"

        # no_charge_window and no_discharge_window: no extra fields needed

    return directives
