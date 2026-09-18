"""LLM provider calls. Each returns the parsed JSON dict or raises ProviderError.

Provider chain (see app/interpreter/__init__.py):
    Gemini primary model -> Gemini fallback model (independent free-tier quota) -> Groq -> degraded.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from app.interpreter.prompt import RESPONSE_SCHEMA, SYSTEM_PROMPT, build_user_message

log = logging.getLogger(__name__)
# Never log outbound request lines: URLs and headers can carry credentials.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class ProviderError(Exception):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"non-JSON model output: {exc.msg}") from exc


async def _gemini_call(model: str, notes: list[str], battery: dict, timeout: float) -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY not set")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": build_user_message(notes, battery)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    headers = {"x-goog-api-key": key}  # header, never the URL: request URLs end up in logs
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(GEMINI_URL.format(model=model), headers=headers, json=body)
    if r.status_code != 200:
        raise ProviderError(f"gemini[{model}] HTTP {r.status_code}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError(f"gemini[{model}] response missing text") from exc
    return _extract_json(text)


async def gemini(notes: list[str], battery: dict, timeout: float = 8.0) -> dict:
    """Primary Gemini model."""
    return await _gemini_call(os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL, notes, battery, timeout)


async def gemini_fallback(notes: list[str], battery: dict, timeout: float = 12.0) -> dict:
    """Second Gemini model. Free-tier rate limits are per model, so this has its own quota."""
    model = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_GEMINI_FALLBACK_MODEL)
    if not model or model == (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL):
        raise ProviderError("no distinct GEMINI_FALLBACK_MODEL configured")
    return await _gemini_call(model, notes, battery, timeout)


async def groq(notes: list[str], battery: dict, timeout: float = 8.0) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ProviderError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    schema_hint = "Output JSON matching this schema exactly:\n" + json.dumps(RESPONSE_SCHEMA)
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + schema_hint},
            {"role": "user", "content": build_user_message(notes, battery)},
        ],
    }
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(GROQ_URL, headers=headers, json=body)
    if r.status_code != 200:
        raise ProviderError(f"groq HTTP {r.status_code}")
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("groq response missing content") from exc
    return _extract_json(text)
