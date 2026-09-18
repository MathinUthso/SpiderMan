"""CONTRACT A: interpret(notes, battery) -> (directives, degraded).

Provider chain: cache -> Gemini HTTP -> Groq -> degraded (all no_op). Never raises.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.cache import get as cache_get, put as cache_put
from app.interpreter.guardrails import validate_llm_output
from app.interpreter.providers import ProviderError, gemini, groq

log = logging.getLogger(__name__)

PROVIDERS = (("gemini", gemini), ("groq", groq))


async def interpret(notes: list[str], battery: dict) -> tuple[list[dict], bool]:
    cached = cache_get(notes, battery)
    if cached is not None:
        return cached, False

    for name, call in PROVIDERS:
        t0 = time.perf_counter()
        raw = None
        for attempt in (1, 2):
            try:
                raw = await call(notes, battery)
                break
            except ProviderError as exc:
                log.warning("provider %s failed (attempt %d): %s", name, attempt, exc)
                # One quick retry only for rate limits / server errors; never for timeouts or bad output.
                if attempt == 1 and ("HTTP 429" in str(exc) or "HTTP 5" in str(exc)):
                    await asyncio.sleep(1.0)
                    continue
                break
            except Exception as exc:  # timeouts, network, anything unexpected
                log.warning("provider %s error: %s", name, type(exc).__name__)
                break
        if raw is None:
            continue
        directives = validate_llm_output(raw, len(notes), battery)
        log.info("provider %s ok in %.2fs", name, time.perf_counter() - t0)
        cache_put(notes, battery, directives)
        return directives, False

    log.error("all providers failed; returning degraded interpretation")
    return validate_llm_output([], len(notes), battery), True
