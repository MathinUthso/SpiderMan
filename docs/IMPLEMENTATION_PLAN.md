# GridWise — Implementation Plan (round-night triage)

Written 21:55 local. **Round ends 23:00.** Everything below is ordered by points-per-minute.
Spec: `docs/GRIDWISE_SPEC.md`. Pitfalls: `docs/TRAPS.md`. Read `docs/AGENTS.md` before touching code.

## 0. Owners

| Who | Owns | Files |
|---|---|---|
| Jonayed | API, optimizer, validator, pipeline, Docker, Render | `app/` (all except `interpreter/prompt.py`), `Dockerfile`, `render.yaml` |
| Teammate 1 | Interpreter prompt + paraphrase robustness | `app/interpreter/prompt.py`, `app/interpreter/providers.py` |
| Teammate 2 | Test cases + edge cases | `tests/`, `testcases/` |
| Teammate 3 | 3-minute video | outside repo |
| Everyone | README sections for their part | `README.md` |

Rule: never edit another owner's files. Coordinate through the two contracts in §2.

## 1. Architecture (one FastAPI service)

```
POST /optimize-energy
  → schemas.py      pydantic request validation            (400 on bad shape)
  → interpreter/    LLM: Gemini Flash → Groq fallback → degraded  (§4)
  → guardrails.py   deterministic checks on LLM output      (fixed, not owned by T1)
  → optimizer/lp.py HiGHS LP, exact                          (dp.py = fallback + test oracle)
  → validator.py    replay plan against directives + rules   (assert before responding)
  → totals from the serialized hourly_plan
  → 200 JSON (7 required fields)
GET /health → {"status":"ok"}   (exactly this, nothing else)
```

```
app/
  main.py            routes, error handlers (no stack traces in responses)
  schemas.py         Request/Response pydantic models, enums
  service.py         pipeline glue: interpret → guardrails → optimize → validate → respond
  interpreter/
    __init__.py      interpret(notes, battery) -> list[Directive]      ← CONTRACT A
    prompt.py        system prompt + few-shots                          (T1)
    providers.py     gemini(), groq(): same schema, same prompt         (T1)
    guardrails.py    validate_llm_output() -> list[Directive] | raise
  optimizer/
    lp.py            optimize(scenario, directives) -> Plan             ← CONTRACT B
    dp.py            same signature, lattice DP (step 0.5)
  validator.py       replay(scenario, directives, plan) -> list[str] errors
  cache.py           in-memory dict keyed by sha256(scenario_id+notes+battery)
tests/
  test_public_cases.py   all 10 cases: valid + cost == reference (±0.01)
  test_validator.py      known-bad plans are rejected
  test_guardrails.py     malformed LLM JSON never reaches optimizer
Dockerfile · render.yaml · requirements.txt · .env.example · README.md
```

## 2. Contracts (frozen — do not change signatures)

**A. Interpreter** — `interpret(notes: list[str], battery: dict) -> list[Directive]`
- Returns exactly `len(notes)` entries, `note_index` 0..n-1 ascending.
- `Directive = {note_index, applies, directive_type, structured_adjustment, explanation}` per spec §10.2.
- Battery dict is passed so "50% of capacity" resolves to a number (SAMPLE-03).
- May raise `InterpreterUnavailable`; service then uses the degraded path (§4). Never raises anything else.

**B. Optimizer** — `optimize(scenario: dict, directives: list[Directive]) -> Plan`
- `Plan = list[24 × {hour, grid_kwh, solar_used_kwh, battery_action, battery_kwh, battery_energy_after_kwh}]`, rounded to 2 dp.
- Raises `Infeasible` only if constraints truly conflict (spec promises they won't; service returns 422).

## 3. LP formulation (`optimizer/lp.py`)

Variables per hour h: `g_h` grid, `s_h` solar used, `c_h` charge, `d_h` discharge (96 vars, all ≥ 0).
```
min  Σ tariff_h · g_h
s.t. g_h + s_h + d_h − c_h = demand_h                     (balance, eq)
     s_h ≤ eff_solar_h        eff = solar·factor in solar_reduction hours
     c_h ≤ max_charge   (0 in no_charge_window hours)
     d_h ≤ max_discharge (0 in no_discharge_window hours)
     g_h ≤ max_grid_kwh (in max_grid_window hours)
     E_h = E0 + Σ_{k≤h}(c_k − d_k);  max(base_min, reserve_h) ≤ E_h ≤ capacity
     E_23 = E0                                                (neutrality)
```
`scipy.optimize.linprog(method="highs")`. Post-processing, in order:
1. Net simultaneous charge/discharge: `m=min(c,d); c-=m; d-=m` (LP degeneracy, harmless with 100% efficiency).
2. Round `c, d, s` to 2 dp; recompute `g_h = demand + c − d − s`, clamp ≥0, round.
3. **Rounding reconciliation**: recompute E chain from rounded c/d; `drift = E_23 − E0`; if `|drift| > 0`, subtract it from the last hour with headroom on the same action, recompute that hour's `g`. Then `battery_action` = charge/discharge/idle from the sign, `battery_kwh = 0` when idle.
4. Run `validator.replay()`; if any error, fall back to `dp.py`; if that fails too, 422.

Why LP over DP alone: exact for non-lattice hidden inputs (e.g. factor 0.33). Why DP too: independent oracle in tests (TRAPS verified it reproduces all 10 references) and a no-scipy fallback.

## 4. Interpreter v1 (`interpreter/`)

- One call per request with all 1–3 notes; response schema enforces `directive_type ∈ 6 enums`, hours int 0–23, factor 0–1.
- Gemini `gemini-3.8-flash` (or `2.5-flash`), structured output, timeout **8 s** → on error/429/timeout: Groq `openai/gpt-oss-120b`, JSON mode, timeout **6 s** → on error: **degraded** (all notes `no_op`, `plan_summary` states "operator notes could not be interpreted; base schedule returned"). Always 200. Total worst case ≈ 15 s < 30 s limit.
- Guardrails (deterministic, fixed): enum check, one entry per note, indices exact, hours unique+ascending+in range, factor ∈ [0,1], reserve ≤ capacity and ≥ 0, grid cap ≥ 0 finite, `no_op ⇔ applies=false ⇔ adjustment=null`, shape per type. Any failure → treat that note as `no_op` (conservative: wrong no_op loses 5 pts; wrong directive loses 5 + invalidates the case).
- Cache: `sha256(scenario_id + json(notes) + json(battery))` → interpretation. Judge retries cost 0 calls.
- Prompt teaches rules, not phrasings: end-exclusive windows (both "noon" directions), factor = fraction remaining ("20%"/"one-fifth"/"80% reduction" → 0.2), percent reserve × capacity, prefer `no_op` over guessing. 4–6 few-shots **re-worded** from public notes.
- T1 hardening after v1: paraphrase set (3 rewrites × 18 public notes), clock formats, energy-adjacent distractors.

## 5. Failure policy

| Condition | Response |
|---|---|
| Malformed JSON / missing fields / ≠24 hours / notes ∉ 1..3 | 400 `{"error": "..."}` |
| Both LLM providers fail | 200, degraded interpretation, flagged in `plan_summary` |
| LP infeasible and DP infeasible | 422 `{"error": "infeasible directives"}` |
| Any unhandled exception | 500 `{"error": "internal error"}` — never a traceback |

Log provider, latency, cache hit. Never log keys or full prompts.

## 6. Deploy

- **Render** free web service, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check path `/health`. Existing cron pinger every 5 min to prevent spin-down.
- Env var **names** (documented, values never committed): `GEMINI_API_KEY`, `GROQ_API_KEY`, `LLM_TIMEOUT_S=8`, `LOG_LEVEL`.
- **Dockerfile**: `python:3.12-slim` (not 3.14 — scipy wheels + boot time), non-root, `EXPOSE 8000`, `CMD uvicorn ... --host 0.0.0.0 --port ${PORT:-8000}`.
- **GHCR**: `docker build -t ghcr.io/cord1ess/gridwise:v1 .` → `docker push`. Make the package **public after the deadline** alongside the repo. README gives `docker run -p 8000:8000 -e GEMINI_API_KEY=... ghcr.io/cord1ess/gridwise:v1`.
- Verify from **outside** (phone hotspot / curl from another machine): `/health`, then one public case.

## 7. Time boxes (owner → deliverable). T = minutes to 23:00

| T | Jonayed | T1 | T2 | T3 |
|---|---|---|---|---|
| 65→52 | skeleton, schemas, `/health`, validator, `lp.py` + reconciliation | read §4, draft prompt + few-shots | pytest harness for 10 public cases | storyboard: problem → LLM→guardrails→optimizer → run/test |
| 52→40 | `interpreter/` v1 (providers, guardrails, cache), wire `service.py` | plug prompt into v1, run 10 cases | edge tests: cap==demand, reserve<base, surplus solar, 2 same-type notes | record voice-over draft |
| 40→28 | **all 10 cases green locally** (cost ±0.01 + validator) → Dockerfile → GHCR push | paraphrase set, fix misses | add paraphrase cases to harness | screen capture of a live request |
| 28→15 | Render deploy, env vars, cron pinger, external curl test | README §LLM/guardrails | README §tests + expected result | cut to ≤3:00, upload |
| 15→5 | README §run/Docker/env/limits, final external check | — | full test run, report | link in submission |
| 5→0 | **submission form**; repo stays private until deadline, then public + GHCR public | — | — | — |

If behind at T=40: skip Groq fallback (keep degraded path), skip DP fallback (keep as test only). Never skip the validator gate or the Dockerfile.

## 8. Definition of done (pre-submit)

- [ ] `/health` → exactly `{"status":"ok"}`, reachable externally
- [ ] 10/10 public cases: validator clean, cost within 0.01 of reference
- [ ] One entry per note, indices 0..n−1; `no_op` ⇒ `applies=false` + `null`
- [ ] Totals recomputed from serialized `hourly_plan`; peak reported, never optimized
- [ ] Forced-failure test: bad Gemini key → Groq → degraded, still 200
- [ ] Docker image pulls and reaches `/health` with the README command
- [ ] README: quickstart, env var names, model/provider, LLM role, guardrails, solver, sample curl, limitations, credits
- [ ] No `.env`, keys, or tracebacks anywhere (`git log -p | grep -i key`)
- [ ] Video ≤ 3:00 accessible

## 9. Known risks

- Free-tier cold start vs 60-s health rule → cron pinger + slim image + lazy-import nothing heavy at boot.
- Gemini free RPM (~15) under judge bursts → cache + Groq + one retry with backoff; queued <30 s is a pass.
- Rounding drift on neutrality → §3 step 3; validator catches any miss.
- Non-binding public grid caps (TRAPS T7b) → T2's synthetic binding-cap test is the only coverage; do not skip it.
