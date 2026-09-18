"""Gemini 3.8 Flash client for directive interpretation."""

import json
import os
from google import genai
from .types import DirectiveInterpretation


_client = None


def get_client() -> genai.Client:
    """Get or create the Gemini client (lazy initialization)."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


def call_gemini(prompt: str) -> list[DirectiveInterpretation]:
    """Call Gemini 3.8 Flash with structured output.

    Args:
        prompt: The assembled prompt string.

    Returns:
        List of DirectiveInterpretation objects.

    Raises:
        RuntimeError: If API call fails or response cannot be parsed.
    """
    client = get_client()

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": list[DirectiveInterpretation],
                "temperature": 0.1,
            },
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}") from e

    # Parse response
    try:
        raw = response.text
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(f"Failed to parse Gemini response as JSON: {e}") from e

    # Validate with Pydantic
    try:
        directives = [DirectiveInterpretation.model_validate(item) for item in data]
    except Exception as e:
        raise RuntimeError(f"Failed to validate Gemini response: {e}") from e

    return directives
