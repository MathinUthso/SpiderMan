"""Pydantic models for directive interpretation."""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class DirectiveInterpretation(BaseModel):
    """Single directive interpretation from the LLM."""

    note_index: int = Field(ge=0, description="Zero-based index of the operator note")
    applies: bool = Field(
        description="true for applicable directives, false only for no_op"
    )
    directive_type: Literal[
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    ]
    structured_adjustment: Optional[dict] = Field(
        default=None,
        description="Required object for non-no_op types, null only for no_op",
    )
    explanation: str = Field(description="Short explanation of the interpretation")


VALID_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}
