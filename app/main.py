"""FastAPI application: GET /health and POST /optimize-energy (spec §6)."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.optimizer import lp as _warm_scipy  # noqa: F401  (pay the scipy import at boot, not on the first request)
from app.schemas import Infeasible, OptimizeRequest, OptimizeResponse
from app.service import run_pipeline

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gridwise")

app = FastAPI(title="GridWise LLM", docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(req: OptimizeRequest) -> OptimizeResponse:
    return await run_pipeline(req)


@app.exception_handler(RequestValidationError)
async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Spec: 400 for malformed JSON or structurally invalid requests.
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors()[:5]
    )
    return JSONResponse(status_code=400, content={"error": "invalid request", "detail": detail})


@app.exception_handler(Infeasible)
async def _infeasible(_: Request, exc: Infeasible) -> JSONResponse:
    log.warning("infeasible: %s", exc)
    return JSONResponse(status_code=422, content={"error": "infeasible directives"})


@app.exception_handler(Exception)
async def _internal(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "internal error"})
