"""LLM provider calls. Each returns the parsed JSON dict or raises ProviderError.

Owner: Teammate 1 (model choice, request tuning). Keep signatures stable.

Provider chain: google-genai SDK (primary) → raw HTTP (fallback) → Groq → degraded.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from app.interpreter.prompt import RESPONSE_SCHEMA, SYSTEM_PROMPT, build_user_message

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class ProviderError(Exception):
    pass


def _timeout(default: float) -> float:
    try:
        return float(os.getenv("LLM_TIMEOUT_S", default))
    except ValueError:
        return default


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


async def _gemini_sdk(notes: list[str], battery: dict) -> dict:
    """Primary Gemini call using google-genai SDK with structured output."""
    try:
        from google import genai
    except ImportError:
        raise ProviderError("google-genai SDK not installed")

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY not set")

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    user_msg = build_user_message(notes, battery)

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=user_msg,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": dict,
            "temperature": 0,
        },
    )

    raw = response.text
    if not raw:
        raise ProviderError("gemini SDK returned empty response")
    return _extract_json(raw)


async def _gemini_http(notes: list[str], battery: dict) -> dict:
    """Fallback Gemini call using raw HTTP (no SDK dependency)."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY not set")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": build_user_message(notes, battery)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    async with httpx.AsyncClient(timeout=_timeout(8.0)) as client:
        r = await client.post(GEMINI_URL.format(model=model), params={"key": key}, json=body)
    if r.status_code != 200:
        raise ProviderError(f"gemini HTTP {r.status_code}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("gemini response missing text") from exc
    return _extract_json(text)


async def gemini(notes: list[str], battery: dict) -> dict:
    """Gemini provider: try SDK first, fallback to HTTP."""
    try:
        return await _gemini_sdk(notes, battery)
    except Exception as exc:
        log.warning("gemini SDK failed, trying HTTP: %s", exc)
    return await _gemini_http(notes, battery)


async def groq(notes: list[str], battery: dict) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ProviderError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
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
    async with httpx.AsyncClient(timeout=_timeout(6.0)) as client:
        r = await client.post(GROQ_URL, headers=headers, json=body)
    if r.status_code != 200:
        raise ProviderError(f"groq HTTP {r.status_code}")
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("groq response missing content") from exc
    return _extract_json(text)
