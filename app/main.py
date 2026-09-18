"""FastAPI application: GET /health and POST /optimize-energy (spec §6)."""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv

# Load .env BEFORE anything reads the environment, so the documented local quickstart
# (copy .env.example -> .env, run uvicorn) really does enable the language model.
# Real environment variables (Render, docker -e) always win over the file.
load_dotenv(override=False)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.optimizer import lp as _warm_scipy  # noqa: E402,F401  (pay the scipy import at boot, not on the first request)
from app.schemas import Infeasible, OptimizeRequest, OptimizeResponse  # noqa: E402
from app.service import run_pipeline  # noqa: E402

_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").strip().upper(), logging.INFO)
logging.basicConfig(level=_level if isinstance(_level, int) else logging.INFO)
log = logging.getLogger("gridwise")

app = FastAPI(title="GridWise LLM", docs_url=None, redoc_url=None)
app.router.redirect_slashes = False  # answer /path/ directly instead of a 307 some clients do not follow

if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")):
    log.warning("no LLM API key configured: operator notes will NOT be interpreted (degraded mode)")


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/health/", methods=["GET", "HEAD"], include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _bad_request(detail: str) -> JSONResponse:
    # Spec: 400 for malformed JSON or structurally invalid requests.
    return JSONResponse(status_code=400, content={"error": "invalid request", "detail": detail})


@app.post("/optimize-energy", response_model=OptimizeResponse)
@app.post("/optimize-energy/", response_model=OptimizeResponse, include_in_schema=False)
async def optimize_energy(request: Request):
    # The body is parsed by hand so a missing or unusual Content-Type header can never
    # cost a valid request; only the JSON itself decides.
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return _bad_request("body is not valid JSON")
    try:
        req = OptimizeRequest.model_validate(payload)
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors()[:5]
        )
        return _bad_request(detail)
    return await run_pipeline(req)


@app.exception_handler(Infeasible)
async def _infeasible(_: Request, exc: Infeasible) -> JSONResponse:
    log.warning("infeasible: %s", exc)
    return JSONResponse(status_code=422, content={"error": "infeasible scenario"})


@app.exception_handler(Exception)
async def _internal(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "internal error"})
