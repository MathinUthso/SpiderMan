# GridWise LLM — Smart Campus Energy Optimization

BUP CSE Fest 2026 · Hackathon · Online Preliminary. One HTTP service that reads operator notes with a language model, validates the extracted directives deterministically, and returns a cost-optimal, constraint-valid 24-hour energy schedule.

```
operator_notes ──► LLM (Gemini Flash → Groq fallback) ──► deterministic guardrails ──► LP optimizer (HiGHS)
                                                                                           │
                       response ◄── totals from plan ◄── independent replay validator ◄───┘
```

---

## Quickstart (clean machine, copy-paste)

Everything below is a single copy-paste block. Total time: ~2 minutes.

### Step 1 — Clone

```bash
git clone <repo-url> gridwise && cd gridwise
```

### Step 2 — Check Python version

```bash
python --version        # must be 3.11 or higher
```

If you see `Python 3.10.x` or lower, install Python 3.11+ from https://python.org first.

### Step 3 — Create virtual environment

```bash
python -m venv .venv

# Linux / macOS:
source .venv/bin/activate

# Windows (PowerShell):
.venv\Scripts\activate
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Configure API keys

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your keys:

```
GEMINI_API_KEY=your_google_ai_studio_key_here
GROQ_API_KEY=your_groq_key_here
```

Leave the other values as-is. **Never commit `.env` to git.**

> Both keys are optional. If both are missing, the service still works — every note is treated as `no_op` and the base schedule is returned. You will lose interpretation points, but the service stays up.

### Step 6 — Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Wait for: `INFO:     Uvicorn running on http://0.0.0.0:8000`

### Step 7 — Verify health (new terminal)

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"ok"}
```

### Step 8 — Run a public sample

```bash
python -c "
import json, urllib.request
case = json.load(open('testcases/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json'))['cases'][0]
req = urllib.request.Request('http://localhost:8000/optimize-energy',
    data=json.dumps(case['input']).encode(),
    headers={'Content-Type': 'application/json'})
resp = json.load(urllib.request.urlopen(req))
print('scenario:', resp['scenario_id'])
print('cost:', resp['total_cost_bdt'])
print('directives:', len(resp['directive_interpretation']))
print('plan hours:', len(resp['hourly_plan']))
print('battery at h23:', resp['hourly_plan'][-1]['battery_energy_after_kwh'])
"
```

Expected output:
```
scenario: SAMPLE-01
cost: 38365.0
directives: 2
plan hours: 24
battery at h23: 110
```

### Step 9 (optional) — Run the full test suite

```bash
python -m pytest -q
```

---

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/health` | `{"status":"ok"}` when ready |
| `POST` | `/optimize-energy` | Request/response exactly as the Problem Statement §7 / §10 |

HTTP codes: `200` success · `400` malformed JSON or structurally invalid request · `422` directives infeasible · `500` controlled internal error (no stack traces).

---

## Environment Variables

Names only — values are never committed.
## Environment variables 

| Name | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Primary LLM (Google AI Studio free tier) | — |
| `GROQ_API_KEY` | Fallback LLM (different vendor) | — |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.5-flash-lite` |
| `GROQ_MODEL` | Groq model id | `openai/gpt-oss-120b` |
| `LLM_TIMEOUT_S` | Per-provider timeout (seconds) | `8` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `PORT` | Listen port (Render injects this) | `8000` |

If both keys are missing or both providers fail, the service still answers `200`: every note is reported as `no_op`, the base schedule is returned, and `plan_summary` says so. It never crashes and never invents a directive.

---

## Architecture

**1. LLM interpretation (`app/interpreter/`).** All 1–3 notes go to the model in one call together with the battery parameters (so "50% of capacity" resolves to a number). The prompt teaches the rules — end-exclusive hour windows, `factor` = fraction of solar *remaining*, percentage reserves × capacity, `no_op` for anything that does not change today's schedule — with re-worded few-shot examples rather than the public phrasings. Gemini is called via the REST API with a JSON response schema whose `directive_type` is an enum of the six allowed values; Groq is the cross-vendor fallback in JSON mode. Identical scenarios are cached in memory.

**2. Deterministic guardrails (`app/interpreter/guardrails.py`).** LLM output is untrusted until it passes: allowed type only; exactly one entry per note with indices `0..N-1`; hours unique, ascending, `0–23`; `0 ≤ factor ≤ 1`; `0 ≤ reserve ≤ capacity`; grid cap finite and non-negative; `no_op ⇔ applies=false ⇔ structured_adjustment=null`; exact object shape per type. Any failure on a note degrades that note to `no_op` — the service never invents a constraint.

**3. Optimizer (`app/optimizer/`).** Linear program over 96 variables (grid, solar used, charge, discharge per hour), solved with HiGHS via `scipy.optimize.linprog`. Constraints: hourly energy balance, effective solar after `solar_reduction`, battery bounds with `max(base minimum, reserve)`, charge/discharge rate limits, `no_charge`/`no_discharge` windows, `max_grid` caps, and end-of-day neutrality. Post-processing nets simultaneous charge/discharge, rounds to 2 dp and reconciles rounding drift so the battery ends exactly at its initial level. A lattice DP (`dp.py`) is the independent oracle in tests and the runtime fallback if the LP path fails.

**4. Validator (`app/validator.py`).** Every plan is replayed hour by hour against all rules and directives *before* it is returned; `total_grid_kwh`, `total_cost_bdt` and `peak_grid_kwh` are recomputed from the serialized plan.

---

## Docker

### Build locally

```bash
docker build -t gridwise .
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -e GROQ_API_KEY=your_key \
  gridwise
curl http://localhost:8000/health
```

### Pre-built image (if available)

```bash
docker pull ghcr.io/cord1ess/gridwise:v1
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -e GROQ_API_KEY=your_key \
  ghcr.io/cord1ess/gridwise:v1
```

Image: `python:3.12-slim`, non-root user, `EXPOSE 8000`, binds `0.0.0.0`, no baked-in secrets.

---

## Tests & Verification

```bash
# 45 tests: public cases, validator, guardrails, API contract
python -m pytest -q

# 10/10 public cases: cost == reference ±0.01, validator clean
python scripts/check_optimizer.py

# Full HTTP path with LLM forced to fail -> still valid 200s
python scripts/check_api.py --no-llm

# Live LLM: 18/18 public notes must match (needs .env with API keys)
python scripts/check_interpreter.py
```

---

## Deployment

Render free web service (`render.yaml`): `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`. An external cron job pings `/health` every 5 minutes so the free instance never spins down. `scipy` is imported at boot so the first request is not slow.

---

## Known Limitations

- Free-tier LLM rate limits (~15 RPM on Gemini). Mitigated by one call per request, caching, and the Groq fallback; sustained bursts beyond both quotas fall back to the degraded (all `no_op`) path rather than failing.
- Paraphrase robustness is bounded by the prompt; it is tested on the public notes plus re-worded variants, not on the hidden set.
- The DP fallback is exact only for quantities on a 1 kWh lattice; the LP is exact for any real inputs and is the normal path.

---

## Dependencies & Credits

FastAPI, Uvicorn, Pydantic, SciPy (HiGHS), NumPy, httpx, python-dotenv, pytest. Language models: Google Gemini (`gemini-3.5-flash-lite`) and Groq (`openai/gpt-oss-120b`). Core architecture, optimizer, validator and guardrails are the team's own work; AI coding assistants were used during development.

---

## Secret Handling

Keys live only in environment variables / `.env` (git-ignored). Nothing secret is logged or returned; error responses are generic.
