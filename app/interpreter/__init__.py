"""CONTRACT A: interpret(notes, battery) -> (directives, degraded).

Provider chain: cache -> Gemini -> Groq -> degraded (all no_op). Never raises.
"""

from __future__ import annotations

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
        try:
            raw = await call(notes, battery)
        except ProviderError as exc:
            log.warning("provider %s failed: %s", name, exc)
            continue
        except Exception as exc:  # timeouts, network, anything unexpected
            log.warning("provider %s error: %s", name, type(exc).__name__)
            continue
        directives = validate_llm_output(raw, len(notes), battery)
        log.info("provider %s ok in %.2fs", name, time.perf_counter() - t0)
        cache_put(notes, battery, directives)
        return directives, False

    log.error("all providers failed; returning degraded interpretation")
    return validate_llm_output([], len(notes), battery), True
