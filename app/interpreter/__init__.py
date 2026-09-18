"""CONTRACT A: interpret(notes, battery) -> (directives, degraded).

Provider chain: cache -> Gemini -> Gemini fallback model -> Groq -> degraded (all no_op).
Never raises, and never spends more than INTERPRET_BUDGET_S in total, so a slow or failing
provider cannot push the request past the judge's 30-second limit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from app.cache import get as cache_get, put as cache_put
from app.interpreter.guardrails import validate_llm_output
from app.interpreter.providers import ProviderError, gemini, gemini_fallback, groq

log = logging.getLogger(__name__)

# (name, call, per-call timeout in seconds)
PROVIDERS = (("gemini", gemini, 8.0), ("gemini-fallback", gemini_fallback, 12.0), ("groq", groq, 8.0))


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


async def interpret(notes: list[str], battery: dict) -> tuple[list[dict], bool]:
    cached = cache_get(notes, battery)
    if cached is not None:
        return cached, False

    per_call_cap = _env_float("LLM_TIMEOUT_S", 12.0)
    deadline = time.monotonic() + _env_float("INTERPRET_BUDGET_S", 22.0)

    for name, call, call_timeout in PROVIDERS:
        remaining = deadline - time.monotonic()
        if remaining < 1.0:
            log.warning("interpretation budget exhausted before provider %s", name)
            break
        timeout = min(call_timeout, per_call_cap, remaining)
        t0 = time.perf_counter()
        try:
            # wait_for bounds the WHOLE call; httpx timeouts alone apply per phase, not in total.
            raw = await asyncio.wait_for(call(notes, battery, timeout), timeout=timeout)
        except ProviderError as exc:
            log.warning("provider %s failed: %s", name, exc)
            continue
        except asyncio.TimeoutError:
            log.warning("provider %s timed out after %.1fs", name, timeout)
            continue
        except Exception as exc:  # network errors, anything unexpected
            log.warning("provider %s error: %s", name, type(exc).__name__)
            continue
        directives = validate_llm_output(raw, len(notes), battery)
        log.info("provider %s ok in %.2fs", name, time.perf_counter() - t0)
        cache_put(notes, battery, directives)
        return directives, False

    log.error("all providers failed; returning degraded interpretation")
    return validate_llm_output([], len(notes), battery), True
