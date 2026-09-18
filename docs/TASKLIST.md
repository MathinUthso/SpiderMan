# Task list — derived from IMPLEMENTATION_PLAN.md

Tick as you go. `[J]` Jonayed · `[T1]` interpreter · `[T2]` tests · `[T3]` video. Target finish: **22:45**.

## A. Skeleton [J]
- [ ] A1 `requirements.txt` (fastapi, uvicorn, pydantic, scipy, numpy, httpx)
- [ ] A2 `app/__init__.py`, `app/schemas.py` — request/response models, enums, 24-hour + 1–3 note validation
- [ ] A3 `app/main.py` — `GET /health` exact body, `POST /optimize-energy`, 400/422/500 handlers with no tracebacks
- [ ] A4 `app/validator.py` — replay: balance, eff-solar, bounds, rates, windows, cap, neutrality, totals
- [ ] A5 `.env.example` with variable names only

## B. Optimizer [J]
- [ ] B1 `app/optimizer/lp.py` — HiGHS LP per plan §3
- [ ] B2 net charge/discharge, 2-dp rounding, neutrality reconciliation
- [ ] B3 `app/optimizer/dp.py` — lattice DP (step 0.5) same signature
- [ ] B4 `optimize()` wrapper: LP → validate → DP fallback → Infeasible
- [ ] B5 script: run 10 public cases through optimizer with reference directives; all cost ±0.01, validator clean

## C. Interpreter v1 [J → T1]
- [ ] C1 `app/interpreter/guardrails.py` — all deterministic checks; bad note → no_op
- [ ] C2 `app/interpreter/prompt.py` — rules-first system prompt + 5 re-worded few-shots, JSON schema
- [ ] C3 `app/interpreter/providers.py` — `gemini()` structured output 8 s; `groq()` JSON mode 6 s
- [ ] C4 `app/interpreter/__init__.py` — `interpret()` contract A, provider chain, degraded path
- [ ] C5 `app/cache.py` — sha256 key → interpretation
- [ ] C6 [T1] run 10 public cases through interpreter; fix prompt until 18/18 notes match
- [ ] C7 [T1] paraphrase set: 3 rewrites × 18 notes, clock formats, energy-adjacent distractors

## D. Pipeline [J]
- [ ] D1 `app/service.py` — interpret → guardrails → optimize → validate → totals → response
- [ ] D2 `plan_summary` generated deterministically from directives + plan (LLM not needed here)
- [ ] D3 end-to-end: 10 public cases via HTTP, all green
- [ ] D4 forced-failure test: bad GEMINI key → Groq → degraded → still 200

## E. Tests [T2]
- [ ] E1 `tests/test_public_cases.py` — 10 cases: validator clean + cost ±0.01 vs reference
- [ ] E2 `tests/test_validator.py` — hand-broken plans rejected (neutrality, cap, reserve, idle≠0)
- [ ] E3 `tests/test_guardrails.py` — malformed/invented/duplicate-index LLM JSON → safe no_op
- [ ] E4 edge cases: cap == demand, reserve < base min, surplus solar forcing curtailment, two same-type notes, asymmetric charge/discharge rates, zero-demand hour
- [ ] E5 paraphrase cases from C7 into harness

## F. Deploy [J]
- [ ] F1 `Dockerfile` python:3.12-slim, non-root, EXPOSE 8000, `--host 0.0.0.0 --port ${PORT:-8000}`
- [ ] F2 local `docker build` + `docker run` → `/health` ok
- [ ] F3 `docker push ghcr.io/cord1ess/gridwise:v1`
- [ ] F4 `render.yaml`; Render web service; env vars set; health path `/health`
- [ ] F5 cron pinger pointed at Render URL
- [ ] F6 external curl: `/health` + one public case from a different network

## G. README [all]
- [ ] G1 [J] quickstart (clone → env → install → run → curl), Docker pull/run, env var names, solver, limitations, credits
- [ ] G2 [T1] LLM role, model/provider IDs, guardrails explanation
- [ ] G3 [T2] test command + expected output
- [ ] G4 sample request/response pasted

## H. Video [T3]
- [ ] H1 storyboard: problem → LLM→guardrails→optimizer → run/test
- [ ] H2 record with a live request against the deployed URL
- [ ] H3 ≤ 3:00, uploaded, link accessible without login

## I. Submission [J]
- [ ] I1 `git log -p | grep -iE "api_key|secret|token"` returns nothing sensitive
- [ ] I2 submission form: endpoint URL, repo URL, GHCR image ref, video link
- [ ] I3 after deadline: repo public, GHCR package public
