# GridWise LLM — Consolidated Specification

**BUP CSE Fest 2026 · Hackathon · Online Preliminary Round**
Smart Campus Energy Optimization Challenge — LLM-Assisted Operator Directive Interpretation

> Single-source reference consolidating the Problem Statement (9pp), the Participant Guide & Evaluation Rubric (11pp), and the Public Sample Cases JSON (10 cases).
>
> **Precedence:** The Problem Statement is canonical for challenge behavior, schemas, directives, guardrails, battery/energy rules, and optimization validity. The Participant Guide is canonical for deployment, repository policy, submission, scoring, penalties, and tie-breakers. Where they appear to disagree on the former, the Problem Statement wins.

---

## 1. Round Facts

| Item | Value |
|---|---|
| Round | Online Preliminary |
| Window | 7:00 PM – 11:00 PM (4 hours) |
| Challenge type | LLM-assisted energy scheduling and optimization |
| Required service | Deployed **public** HTTP API (one service, not multiple deployments) |
| Health endpoint | `GET /health` |
| Main endpoint | `POST /optimize-energy` |
| Planning horizon | 24 hourly intervals (hours 0–23) |
| Operator notes | 1–3 natural-language notes per scenario |
| Response format | Structured JSON |
| LLM | **Mandatory** in the `operator_notes` interpretation path |
| Data | All scenarios/notes are synthetic. No live campus, utility, billing, or personal data. |

---

## 2. The Scenario

BUP operates a smart campus powered by three sources: grid electricity (priced per hour), rooftop solar, and a battery energy storage system. Demand, solar availability, and tariff all vary across the day. The next 24 hours of demand, solar, and tariff are **given** in the request.

Additionally, campus operators send short natural-language notes describing temporary operating conditions affecting the same 24-hour window. The service must understand those notes, convert relevant ones into structured directives, apply them to the optimization, and return a valid low-cost plan.

---

## 3. Mandated Architecture

```
operator_notes (free text)
        │
        ▼
  ┌───────────┐   LLM / language-capable generative model
  │    LLM    │   → structured directive JSON
  └───────────┘
        │  (untrusted structured data)
        ▼
  ┌───────────┐   Deterministic validation:
  │ GUARDRAILS│   type ∈ 6 allowed, note mapping, hours 0–23 unique
  │           │   ascending, numeric ranges, applies semantics
  └───────────┘
        │  (validated, typed constraints)
        ▼
  ┌───────────┐   LP / DP / CP solver
  │ OPTIMIZER │   → minimize grid cost subject to constraints
  └───────────┘
        │
        ▼
  directive_interpretation + hourly_plan
```

**Quoted rules:**

- *"The LLM understands human language; deterministic code validates the interpretation; the optimizer performs the mathematical scheduling."*
- **CORE IDEA:** *"Human notes are not directly trusted as math. They are first converted to a fixed structured format, checked by guardrails, and only then applied to the optimization model."*
- **LLM REQUIREMENT:** *"The language model must be part of the operator-note interpretation path. Using an LLM only for `plan_summary`, documentation, or cosmetic text does not satisfy this requirement."*
- *"LLM output must be treated as untrusted structured data until deterministic validation passes."*
- **SAFE FAILURE:** *"If the LLM returns malformed or unsupported structured output, the service must handle it in a controlled way. The service must not silently invent a new directive type or crash."*

### 3.1 What each layer may and may not do

| Approach | Policy |
|---|---|
| Language-capable generative model | **Required** for interpreting `operator_notes`. Its structured interpretation must be part of the path producing optimization constraints. |
| Deterministic pre/post-processing | **Allowed** for normalization, JSON validation, guardrails, and applying structured directives. May **not** replace the language-model interpretation step. |
| Optimization libraries / solvers | **Allowed** — LP, DP, constraint solving, or other practical methods. |
| External model API or local model | **Allowed.** Team chooses provider/model but must meet reliability + latency requirements and document the identifier used. |
| Hard-coded phrase matching as sole interpreter | **Not compliant.** Hidden notes paraphrase; the LLM must be in the interpretation path. |
| AI used only for `plan_summary` / documentation | **Does not satisfy** the LLM requirement. |

---

## 4. Supported Directive Types

Exactly six. No others are accepted, and hidden cases will not require unpublished types.

| `directive_type` | Meaning | Required `structured_adjustment` |
|---|---|---|
| `solar_reduction` | Reduce usable solar during specific hours | `{"hours":[...], "factor": number}` |
| `minimum_battery_reserve` | Keep battery energy at/above a level | `{"hours":[...], "minimum_energy_kwh": number}` |
| `no_charge_window` | Battery charging unavailable | `{"hours":[...]}` |
| `no_discharge_window` | Battery discharging unavailable | `{"hours":[...]}` |
| `max_grid_window` | Grid import may not exceed an amount | `{"hours":[...], "max_grid_kwh": number}` |
| `no_op` | Note does not affect the schedule | `null` |

### 4.1 Two conventions that must be exact

**Time windows are start-inclusive, end-exclusive.**
`"1 PM to 3 PM"` → `[13, 14]` — **not** `[13,14,15]`.

**`factor` is the fraction REMAINING, not the reduction.**
`"80% reduction"` → `factor = 0.2`. `"drop to 20%"` → `factor = 0.2`. `"roughly one-fifth of normal"` → `factor = 0.2`.

### 4.2 Directive effect on the math

| Directive | Deterministic effect |
|---|---|
| `solar_reduction` | `effective_solar[h] = original_solar[h] * factor` for each listed hour |
| `minimum_battery_reserve` | `battery_energy_after_kwh[h] >= max(base minimum_energy_kwh, directive minimum_energy_kwh)` |
| `no_charge_window` | battery charge amount `= 0` in listed hours |
| `no_discharge_window` | battery discharge amount `= 0` in listed hours |
| `max_grid_window` | `grid_kwh[h] <= max_grid_kwh` in listed hours |
| `no_op` | No change to the optimization model |

### 4.3 Simple worked examples

| Operator note | Expected interpretation |
|---|---|
| "Solar output will drop to about 20% from 1 PM to 3 PM." | `solar_reduction`; hours `[13,14]`; factor `0.2` |
| "Do not charge the battery between 2 PM and 4 PM." | `no_charge_window`; hours `[14,15]` |
| "Keep at least 120 kWh in reserve from 6 PM until 9 PM." | `minimum_battery_reserve`; hours `[18,19,20]`; 120 kWh |
| "The cafeteria menu changes tomorrow." | `no_op` |

### 4.4 Operator-note clauses

- Every note produces **exactly one** `directive_interpretation` entry, returned in `note_index` order `0, 1, … N-1`.
- Only the six directive types above are accepted.
- Relevant notes must be **applied to the optimization** before scheduling.
- Irrelevant notes use `applies = false`, `directive_type = "no_op"`, `structured_adjustment = null`.
- The same directive may appear in different wording in hidden cases.
- The LLM must not invent demand, solar, tariff, battery limits, or unsupported directive types.
- **A schedule that interprets a note correctly but does not apply it is still incorrect.**
- For every non-`no_op` directive, `applies` must be `true`. `no_op` is the **only** type allowed with `applies = false`.
- Every `hours` array must contain unique integers 0–23 in ascending order.
- Organizer valid scoring scenarios are feasible and will not require mutually contradictory hard directives.

---

## 5. API Contract

Endpoint names must match **exactly**. The judge harness exercises only these two.

| Endpoint | Requirement |
|---|---|
| `GET /health` | HTTP 200 with JSON containing `status = "ok"` when ready |
| `POST /optimize-energy` | Accept one scenario JSON object; return one interpretation + optimization-plan JSON object |

### 5.1 HTTP response codes

| Code | Meaning |
|---|---|
| 200 | Successful health or optimization response |
| 400 | Malformed JSON or structurally invalid request |
| 422 | *Optional:* semantically invalid but well-formed request |
| 500 | Controlled internal error. **Do not expose secrets or raw stack traces.** |

### 5.2 Health response

```json
{ "status": "ok" }
```

---

## 6. Request Schema

`hours` must contain exactly 24 entries for hours 0–23. `operator_notes` must contain 1–3 non-empty natural-language strings, each referring to the same 24-hour scenario.

### 6.1 Top level

| Field | Type | Requirement |
|---|---|---|
| `scenario_id` | string | Unique synthetic scenario identifier |
| `operator_notes` | array[1..3] of string | Natural-language notes to interpret |
| `hours` | array[24] | Hourly demand, solar availability, tariff |
| `battery` | object | Capacity, starting energy, reserve, hourly limits |

### 6.2 Hour entry

| Field | Type | Meaning |
|---|---|---|
| `hour` | integer | Unique integer 0–23 |
| `demand_kwh` | number | Campus demand that must be supplied this hour |
| `solar_kwh` | number | **Base** solar available *before* operator-note adjustments |
| `tariff_bdt_per_kwh` | number | Grid price this hour |

### 6.3 Battery object

| Field | Meaning |
|---|---|
| `capacity_kwh` | Maximum energy storable |
| `initial_energy_kwh` | Energy at the start of hour 0 |
| `minimum_energy_kwh` | Base reserve the battery must never go below |
| `max_charge_kwh_per_hour` | Max energy addable in one hour |
| `max_discharge_kwh_per_hour` | Max energy removable in one hour |

### 6.4 Example request

```json
{
  "scenario_id": "GRID-101",
  "operator_notes": [
    "Solar output will drop to about 20% from 1 PM to 3 PM.",
    "Do not charge the battery between 2 PM and 4 PM.",
    "The cafeteria menu changes tomorrow."
  ],
  "hours": [
    {"hour": 0, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
    "... 22 more hourly entries ...",
    {"hour": 23, "demand_kwh": 200, "solar_kwh": 0, "tariff_bdt_per_kwh": 9}
  ],
  "battery": {
    "capacity_kwh": 500,
    "initial_energy_kwh": 200,
    "minimum_energy_kwh": 50,
    "max_charge_kwh_per_hour": 100,
    "max_discharge_kwh_per_hour": 100
  }
}
```

---

## 7. LLM Interpretation Guardrails

LLM output is **untrusted structured data** until deterministic validation passes.

| Guardrail | Requirement |
|---|---|
| Allowed types | `directive_type` must be one of the six in §4 |
| Note mapping | `note_index` must identify an existing note; each note appears **once** |
| Hours | Every listed hour a unique integer 0–23, ascending order |
| Solar factor | For `solar_reduction`, `0 <= factor <= 1` inclusive |
| Battery reserve | Finite, non-negative, **not exceeding battery capacity** |
| Grid cap | `max_grid_kwh` finite and non-negative |
| No invention | May not change base demand, tariff, or battery parameters unless a supported directive explicitly allows it |
| Final replay | Completed schedule is replayed after optimization to verify every extracted directive was actually followed |
| `applies` semantics | `no_op` ⇒ `applies=false` + `null`. Every other directive ⇒ `applies=true` + matching shape |
| Feasible judge scenarios | Valid scoring scenarios have feasible ground truth, no contradictory hard directives |

---

## 8. Battery & Energy Rules

The judge **independently replays** the final schedule hour by hour using effective solar and all operator directives.

### 8.1 Battery state transitions

```
charge:     E_after = E_before + battery_kwh
discharge:  E_after = E_before - battery_kwh
idle:       E_after = E_before   and   battery_kwh = 0
```

### 8.2 Battery bounds

```
minimum_energy_kwh <= E_after <= capacity_kwh
```

An active `minimum_battery_reserve` directive may raise the minimum above the base for those hours.

### 8.3 Hourly rate limits

```
if action = charge:     battery_kwh <= max_charge_kwh_per_hour
if action = discharge:  battery_kwh <= max_discharge_kwh_per_hour
```

### 8.4 Solar usage

```
0 <= solar_used_kwh <= effective_solar_kwh   (for that hour)
```

Unused solar is **curtailed**. Grid export is **not** part of this challenge.

### 8.5 Energy balance (every hour)

```
grid_kwh + solar_used_kwh + battery_discharge_kwh = demand_kwh + battery_charge_kwh
```

### 8.6 End-of-day battery neutrality

```
final battery_energy_after_kwh (hour 23) = initial_energy_kwh
```

> **WHY THIS RULE EXISTS:** *"The starting battery may shift energy between hours, but it cannot be consumed as a free one-time source by ending the day at a lower state of charge."*

### 8.7 Not specified anywhere (verified against all 10 reference plans)

- **No charge/discharge efficiency or round-trip loss** — transfers are exactly 1:1.
- **No battery degradation, ramp limits, or cycle costs.**
- **No simultaneous charge+discharge** — `battery_action` is exactly one of three states.

---

## 9. Optimization Objective

After applying all valid directive adjustments, minimize total grid electricity cost:

```
total_cost_bdt = SUM( grid_kwh[h] * tariff_bdt_per_kwh[h] )   for h = 0..23
```

Lower cost is better, **but a low-cost schedule is invalid if it breaks any energy, battery, or operator-directive rule.**

---

## 10. Response Schema

### 10.1 Top-level fields (all 7 required)

| Field | Type | Requirement |
|---|---|---|
| `scenario_id` | string | Must match the request `scenario_id` |
| `directive_interpretation` | array | One entry per operator note |
| `hourly_plan` | array[24] | One entry per hour 0–23 |
| `total_grid_kwh` | number | Sum of `grid_kwh` across all 24 hours |
| `total_cost_bdt` | number | Calculated total grid cost |
| `peak_grid_kwh` | number | Maximum hourly `grid_kwh` in the returned plan |
| `plan_summary` | string | Short human-readable explanation of the strategy |

### 10.2 Directive interpretation entry

| Field | Requirement |
|---|---|
| `note_index` | Zero-based index of the corresponding `operator_notes` entry |
| `applies` | `true` for every applicable non-`no_op`; `false` **only** for `no_op` |
| `directive_type` | One of the six in §4; `no_op` required when `applies=false` |
| `structured_adjustment` | Exact object required by §4, or `null` **only** for `no_op` |
| `explanation` | Short explanation. **Not** matched byte-for-byte |

### 10.3 Hourly plan entry

| Field | Allowed value / meaning |
|---|---|
| `hour` | Integer 0–23 |
| `grid_kwh` | Non-negative grid energy purchased this hour |
| `solar_used_kwh` | Solar used; cannot exceed effective solar |
| `battery_action` | Exactly one of `charge`, `discharge`, `idle` |
| `battery_kwh` | Non-negative magnitude. **Must be 0 when `idle`** |
| `battery_energy_after_kwh` | Battery energy immediately after this hour |

### 10.4 Example interpretation fragment

> ⚠️ **This example in the official Problem Statement shows only `note_index` 0 and 2 for a 3-note request — it omits index 1. Do not copy its shape.** The binding rule is one entry per note, all indices present, ascending. See TRAPS §T1.

```json
"directive_interpretation": [
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
    "explanation": "Solar availability is reduced during panel cleaning."
  },
  {
    "note_index": 2,
    "applies": false,
    "directive_type": "no_op",
    "structured_adjustment": null,
    "explanation": "This note does not affect today's energy schedule."
  }
]
```

---

## 11. Validation & Hidden Evaluation

Hidden evaluation checks **both** language understanding and energy optimization. Do not assume only `total_cost_bdt` or free text is checked.

### 11.1 Interpretation checks

- Correctly identify whether each note applies or is `no_op`.
- Return the correct directive type.
- Extract correct hours and numeric values within tolerance.
- Remain robust when the same directive is paraphrased.
- One entry per note in `note_index` order, no missing/duplicate mappings.
- Match the required `structured_adjustment` shape for the chosen type.
- Use `applies = false` only for `no_op`.

### 11.2 Downstream application checks

- Judge recomputes effective solar after `solar_reduction`.
- Judge verifies reserve, no-charge, no-discharge, and grid-cap directives **directly against `hourly_plan`**.
- **Correct extraction without correct downstream application does not pass the case.**

### 11.3 GridWise consistency checks

- `hourly_plan` contains exactly 24 unique hours, 0–23.
- Required numeric values finite and non-negative.
- Battery transitions, capacity, minimum energy, rate limits valid.
- Solar usage never exceeds effective available solar.
- Energy-balance equation holds every hour.
- Final battery energy equals initial battery energy.
- `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh` match values recalculated from `hourly_plan`.

### 11.4 Hidden language variation

All three of these mean the **same** `solar_reduction` (hours `[13,14]`, factor `0.2`):

- "PV production will drop to about 20% between 13:00 and 15:00."
- "Panel washing from one until three will leave roughly one-fifth of normal solar output."
- "Expect an 80% reduction in rooftop solar during the 1-3 PM maintenance window."

> **NO BYTE-FOR-BYTE MATCHING:** Equivalent valid optimal schedules may differ. The judge evaluates structured interpretation, directive application, schedule validity, and recalculated cost — not exact JSON equality with one reference plan.

### 11.5 Numeric tolerance

Absolute tolerance **0.01 kWh / 0.01 BDT** unless the official judge package specifies stricter.

---

## 12. Scoring — 100 Points, Automated

| # | Category | Points |
|---|---|---|
| 1 | LLM Directive Interpretation | **25** |
| 2 | Directive Application & Constraint Correctness | **25** |
| 3 | Optimization Quality | **10** |
| 4 | API Contract & Schema | **10** |
| 5 | Performance & Reliability | **10** |
| 6 | Deployment & Docker Fallback | **10** |
| 7 | Documentation & Local Reproducibility | **10** |
| | **TOTAL** | **100** |

The 3-minute video carries **no base points** — tie-break only.

### 12.1 Category breakdowns

**LLM Directive Interpretation (25)**
5 relevance/`no_op` + 5 `directive_type` + 5 affected hours + 5 numeric values/required shape + 5 paraphrase robustness across related hidden notes.

**Directive Application & Constraint Correctness (25)**
10 organizer-ground-truth directive application + 5 hourly energy balance/effective-solar validity + 5 battery transitions/bounds/rate limits + 5 action consistency/end-of-day neutrality/non-negative values.

**Optimization Quality (10)**
Cost-quality over optimization hidden cases. **Invalid cases receive zero optimization credit.**

```
quality_ratio = min(1, organizer_optimal_cost / recalculated_team_cost)
Optimization Quality = 10 × average(quality_ratio) across all optimization hidden cases
```
If both optimal and team cost are within tolerance of 0 → `quality_ratio = 1`.

**API Contract & Schema (10)**
2 endpoints/status behavior + 2 request validation + 3 `directive_interpretation` schema/order/types + 3 `hourly_plan`/top-level schema and `scenario_id` echo.

**Performance & Reliability (10)**
2 health readiness + 3 p95 latency + 3 valid-request stability/failure rate + 2 controlled malformed/provider-failure handling and secret safety.

**Deployment & Docker Fallback (10)**
3 live endpoint reachability + 4 working pullable Docker image reaching `/health` via documented command + 2 clean startup/reproducibility + 1 no judge debugging required.

**Documentation & Local Reproducibility (10)**
3 clean local quickstart from fresh environment + 2 environment/config/model-provider docs + 2 public-sample test procedure and expected result + 1 LLM/guardrail/optimizer architecture explanation + 1 Docker pull/run fallback instructions + 1 dependencies, limitations, secret-handling guidance.

> **SCORING PRINCIPLE:** *"The system is judged as a pipeline: understand the note, validate the structured directive, apply it to the optimization, return a valid schedule, and then optimize cost. A cheap schedule built on a wrong or ignored directive does not score as a correct solution."*

---

## 13. Operational Thresholds

| Metric | Standard |
|---|---|
| Health readiness | `GET /health` returns `{"status":"ok"}` **within 60 seconds** of service start |
| Per-request timeout | `POST /optimize-energy` must complete **within 30 seconds**; beyond = failure |
| p95 latency | ≤5s → 3/3 pts · >5–15s → 2/3 · >15–30s → 1/3 · >30s → 0/3 + failures |
| Failure rate | Valid requests must not return 5xx, invalid JSON, or no response |
| Malformed input | Controlled error or safe failure; no crash, no invented directive |
| Secret handling | No keys/tokens/secrets/sensitive stack traces in repo, logs, or responses |
| Numeric tolerance | 0.01 kWh / 0.01 BDT |

---

## 14. Penalties & Critical Violations

| Violation | Penalty |
|---|---|
| **LLM absent from interpretation path, or AI used only for `plan_summary`/docs** | **Fails mandatory requirement; NOT ELIGIBLE for the final preliminary shortlist** |
| Relevant note interpreted incorrectly or marked `no_op` | Interpretation credit lost for that note/case |
| Applicable ground-truth directive not reflected in `hourly_plan` | Case invalid for directive-application scoring; **no optimization credit** |
| Energy-balance failure or unmet hourly demand | Case invalid; no optimization credit |
| Battery bound/transition/rate violation | Case invalid; no optimization credit |
| Effective-solar overuse or impossible/negative values | Case invalid; no optimization credit |
| `no_charge`/`no_discharge`/reserve/`max_grid` violation | Case invalid; no optimization credit |
| End-of-day battery not returned to initial level | Case invalid; no optimization credit |
| Reported totals disagree with `hourly_plan`, or repeated critical invalidity | Recalculation/scoring deduction; repeated failures may **block qualification eligibility** |

> **GROUND TRUTH BEFORE COST:** The judge first checks the organizer ground-truth directive, its downstream application, and normal GridWise constraints. **Only then** is optimization quality scored.

Note the asymmetry: every penalty except the first is *case-scoped*. The LLM-absence penalty is **global and disqualifying**.

---

## 15. Deliverables

| # | Item | Requirement |
|---|---|---|
| 1 | **Working public endpoint** | Base URL reachable by judge for `GET /health` and `POST /optimize-energy`. No login, dashboard, manual approval, VPN, or private network. |
| 2 | **GitHub repository** | Created **after question reveal**; private during event; **made public after the submission deadline** for evaluation |
| 3 | **README & configuration** | Self-contained; setup/run, model/provider or local model identifier, env-var **names** (never values), solver/library usage, sample request/response |
| 4 | **Docker fallback image** | Pullable registry reference with exact tag/digest; exposes documented port; binds `0.0.0.0`; **no baked-in secrets**; one verified `docker run` command |
| 5 | **3-minute video** | MP4 or accessible link, ≤3:00. Problem, architecture overview, LLM → guardrails → optimizer flow, how to run/test. Production editing not required. **Tie-break only, no base points.** |

### 15.1 README must include

Source setup · environment-variable **names** · model/provider · LLM role · guardrails · optimizer/solver · exact run command · health & API curl examples · public-sample test command · dependencies · known limitations · secret-handling guidance. **No secret values.**

### 15.2 Deployment rules

- Any reachable platform is fine — judged on behavior, accessibility, reproducibility, not provider.
- The LLM used must be **available during judging**. Team owns keys, quota, rate limits, provider availability.
- No long training/fine-tuning during evaluation.
- LLM output must pass the deterministic guardrails before reaching the optimizer.
- README must give a copy-paste local quickstart from a clean environment: clone/pull → configure env-var names → install or pull image → start → call `/health` → run at least one public sample.
- Test both endpoints from **outside** your dev environment before submitting.

> **EXTERNAL MODEL RESPONSIBILITY:** *"Judges are not expected to repair an unavailable dependency."* A local or backup model is allowed if it still satisfies the Problem Statement.

### 15.3 Security & repository policy

- Never commit API keys, tokens, `.env` files, passwords, or secrets.
- Never expose secrets, tokens, raw prompts containing secrets, stack traces, or sensitive values in logs or responses.
- Use only synthetic challenge data.
- AI coding assistants and public libraries/frameworks/SDKs are permitted, but **core architecture and logic should be the team's own work**. Credit all external tools/dependencies in README.

---

## 16. Hidden Tests & Tie-Breakers

### 16.1 Hidden test properties

- Exact hidden case list, wording, distribution, and expected answers are **not published**.
- Each valid hidden scenario follows the Problem Statement with 1–3 synthetic notes; each note maps to exactly one supported type or `no_op`.
- Hidden notes may paraphrase with different wording, whole-hour time expressions, percentages, or equivalent numeric descriptions. **Do not hard-code public phrases.**
- Hidden cases vary demand, solar, tariff, battery state, reserve/rate limits, and directive combinations.
- Valid scoring scenarios are feasible, no mutually contradictory hard directives.
- Equivalent valid optimal schedules are accepted.

### 16.2 Tie-break order

| Priority | Tie-breaker |
|---|---|
| 1 | 3-minute Architecture & Solution Video |
| 2 | Directive Application & Constraint Correctness |
| 3 | LLM Directive Interpretation |
| 4 | Optimization Quality |
| 5 | API/schema validity |
| 6 | Reliability and deployment stability |
| 7 | Documentation & local reproducibility |
| 8 | Exceptional engineering / verification |

### 16.3 Recommended priority order

1. Exact API & JSON Contract
2. LLM Operator-Note Interpretation
3. Deterministic Guardrails
4. Directive Application & Energy Correctness
5. Optimization Quality
6. Reliability, Deployment & Docker Fallback
7. Documentation & Local Reproducibility
8. 3-minute Video (tie-break readiness only)

---

## 17. Public Sample Cases — Data Reference

**Pack meta:** version 2.0, 10 cases, endpoint `POST /optimize-energy`.

> *"These are public examples only and are not hidden judge cases."*
> *"Do not hard-code public note wording, case IDs, numeric values, or reference schedules. Hidden notes may paraphrase the same directive."*
> *"The `expected_output` for each case is one valid optimal reference result. Another schedule may also be accepted if it satisfies the same directive ground truth and all GridWise constraints and achieves equivalent optimal cost within the official tolerance."*

### 17.1 Case index

| Case | Label | Notes → directives | Ref cost (BDT) | Total grid | Peak grid |
|---|---|---|---|---|---|
| SAMPLE-01 | Solar cleaning + distractor | `solar_reduction` [12,13] f=0.25 · `no_op` | 38,365 | 2,692.5 | 175 |
| SAMPLE-02 | — | `no_charge_window` [2,3,4] | 42,885 | 2,915 | 180 |
| SAMPLE-03 | — | `minimum_battery_reserve` [18,19,20] = 100 | 35,480 | 2,430 | 205 |
| SAMPLE-04 | — | `no_discharge_window` [18,19] | 40,495 | 2,645 | 225 |
| SAMPLE-05 | — | `max_grid_window` [18,19,20] ≤155 | 33,950 | 2,430 | 175 |
| SAMPLE-06 | — | `solar_reduction` [10,11] f=0.5 · `no_charge_window` [14,15] · `no_op` | 34,090 | 2,395 | 175 |
| SAMPLE-07 | — | `minimum_battery_reserve` [18,19,20,21]=90 · `max_grid_window` [19,20] ≤180 | 38,550 | 2,560 | 185 |
| SAMPLE-08 | — | `no_charge_window` [11,12] · `no_discharge_window` [17,18] | 37,665 | 2,490 | 210 |
| SAMPLE-09 | — | `solar_reduction` [11,12,13] f=0.2 · `no_op` | 34,873 | 2,504 | 170 |
| SAMPLE-10 | — | `minimum_battery_reserve` [18,19,20,21]=80 · `max_grid_window` [19,20,21] ≤190 · `no_op` | 41,620 | 2,715 | 190 |

### 17.2 Battery configurations

| Case | capacity | initial | minimum | max_charge | max_discharge |
|---|---|---|---|---|---|
| SAMPLE-01 | 220 | 110 | 40 | 50 | 50 |
| SAMPLE-02 | 200 | 70 | 30 | 55 | 55 |
| SAMPLE-03 | 200 | 120 | 40 | 50 | 50 |
| SAMPLE-04 | 230 | 130 | 40 | 55 | 55 |
| SAMPLE-05 | 240 | 120 | 30 | 60 | 60 |
| SAMPLE-06 | 220 | 100 | 35 | 50 | 50 |
| SAMPLE-07 | 250 | 150 | 40 | 60 | 60 |
| SAMPLE-08 | 210 | 105 | 35 | 50 | 50 |
| SAMPLE-09 | 240 | 120 | 40 | 60 | 60 |
| SAMPLE-10 | 260 | 140 | 40 | 65 | 65 |

⚠️ In **all 10** public cases `max_charge == max_discharge`. Hidden cases may break this symmetry — never assume one rate.

### 17.3 Every public operator note verbatim

**SAMPLE-01**
- "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast." → `solar_reduction` [12,13] f=0.25
- "The sports office moved next month's registration deadline." → `no_op`

**SAMPLE-02**
- "The battery charger will be isolated from 2 AM until 5 AM for electrical maintenance." → `no_charge_window` [2,3,4]

**SAMPLE-03**
- "Keep at least 50% of the battery capacity stored in the battery from 6 PM until 9 PM for emergency operations." → `minimum_battery_reserve` [18,19,20] = **100** (50% × capacity 200)

**SAMPLE-04**
- "For protection testing, the battery must not discharge from 6 PM until 8 PM." → `no_discharge_window` [18,19]

**SAMPLE-05**
- "From 6 PM until 9 PM, campus grid import must not exceed 155 kWh in any hour because the feeder is operating under a temporary limit." → `max_grid_window` [18,19,20] ≤155

**SAMPLE-06**
- "Cloud cover during panel inspection will leave about half of the forecast solar output from 10 AM until noon." → `solar_reduction` [10,11] f=0.5
- "The charging circuit will be unavailable from 2 PM until 4 PM." → `no_charge_window` [14,15]
- "The library is extending book-return hours next week." → `no_op`

**SAMPLE-07**
- "Keep at least 90 kWh in the battery from 6 PM until 10 PM for emergency services." → `minimum_battery_reserve` [18,19,20,21] = 90
- "The evening transformer limit is 180 kWh of grid import from 7 PM until 9 PM." → `max_grid_window` [19,20] ≤180

**SAMPLE-08**
- "Battery charging is disabled from 11 AM until 1 PM while technicians inspect the charger." → `no_charge_window` [11,12]
- "Do not discharge the battery from 5 PM until 7 PM during relay testing." → `no_discharge_window` [17,18]

**SAMPLE-09**
- "Expect an 80% reduction in rooftop solar between 11 AM and 2 PM because of inverter work." → `solar_reduction` [11,12,13] f=0.2
- "The student affairs office will publish club notices tomorrow." → `no_op`

**SAMPLE-10**
- "The data center requires at least 80 kWh to remain in the battery from 6 PM until 10 PM." → `minimum_battery_reserve` [18,19,20,21] = 80
- "Grid intake must stay at or below 190 kWh from 7 PM until 10 PM while the substation is constrained." → `max_grid_window` [19,20,21] ≤190

### 17.4 Paraphrase families observed

| Directive | Public phrasings used |
|---|---|
| `solar_reduction` | "wash the rooftop solar panels… treated as roughly 25% of the forecast" · "cloud cover… about half of the forecast solar output" · "expect an 80% reduction… because of inverter work" |
| `no_charge_window` | "battery charger will be **isolated**" · "charging circuit will be **unavailable**" · "battery charging is **disabled**" |
| `no_discharge_window` | "battery **must not discharge**" · "**do not discharge** the battery" |
| `minimum_battery_reserve` | "keep at least **50% of the battery capacity**" · "keep at least 90 kWh" · "requires at least 80 kWh to remain" |
| `max_grid_window` | "grid import **must not exceed**" · "the evening **transformer limit is**" · "grid intake must **stay at or below**" |
| `no_op` | sports registration deadline · library book-return hours · student club notices · seminar room booking |

### 17.5 Verified data properties

- All input `demand_kwh`, `solar_kwh`, `tariff_bdt_per_kwh` values are multiples of 0.5 (in practice integers/multiples of 5).
- Tariffs observed span **4 to 34 BDT/kWh**.
- Reference plans use **fractional** values (e.g. `grid_kwh: 152.5`, `solar_used_kwh: 42.5`) — an integer-only optimizer cannot reproduce optimal cost.
- **Zero solar curtailment** in all 10 reference plans (effective solar fully consumed).
- Battery transfers are exactly 1:1 — **100% efficiency confirmed** across all 240 plan hours.
- All 10 reference schedules **pass every constraint check** in §8 and §11.3 (independently verified).

### 17.6 Pack usage instructions

- Read the full Problem Statement and Participant Guide before using the pack.
- POST each `case.input` to `POST /optimize-energy`.
- Compare `directive_interpretation` against public reference semantics. Free-text wording need not match byte-for-byte.
- Replay returned `hourly_plan` against interpreted directives, effective solar, battery rules, energy balance, end-of-day neutrality.
- Equivalent optimal schedules are accepted.

---

## 18. Pre-Submit Checklist

- [ ] `GET /health` reachable, returns `{"status":"ok"}`
- [ ] `POST /optimize-energy` reachable **externally**, accepts 1–3 notes with exact schema
- [ ] Exactly one `directive_interpretation` entry per note, in `note_index` order; `no_op` ⇒ `applies=false` + `null`; all others ⇒ `applies=true` + exact shape
- [ ] LLM output deterministically guardrailed before optimization; hours unique ascending 0–23; numerics valid; invalid model output cannot silently invent constraints
- [ ] `hourly_plan` obeys ground-truth directives + energy balance + effective solar + battery + rate limits + grid cap + end-of-day neutrality
- [ ] `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh` match recalculation from `hourly_plan`
- [ ] README self-contained with clean local quickstart, env-var names, model/provider, LLM role, guardrails, solver, dependencies, run command, `/health` test, sample curl, known limitations, no committed secrets
- [ ] Repo created after reveal, private during, public after deadline; endpoint reachable through judging window; fallback/video links accessible
- [ ] Docker image with exact pullable tag/digest; documented pull/run works; `/health` ready; port exposed; no baked secrets
- [ ] 3-minute video accessible, explains problem, architecture, LLM → guardrails → optimizer pipeline, run/test procedure

---

## 19. Quick Reference Card

```
ENDPOINTS      GET /health -> {"status":"ok"}
               POST /optimize-energy

DIRECTIVES     solar_reduction          {hours, factor}
               minimum_battery_reserve  {hours, minimum_energy_kwh}
               no_charge_window         {hours}
               no_discharge_window      {hours}
               max_grid_window          {hours, max_grid_kwh}
               no_op                    null

CONVENTIONS    "1 PM to 3 PM"  -> [13, 14]        (end-exclusive)
               "80% reduction" -> factor 0.2      (fraction REMAINING)
               "50% of capacity" -> 0.5 * capacity_kwh from request

BALANCE        grid + solar_used + discharge = demand + charge
BOUNDS         max(base_min, reserve) <= E_after <= capacity
NEUTRALITY     E_after[23] == initial_energy_kwh
OBJECTIVE      min SUM(grid_kwh[h] * tariff[h])

LIMITS         health ready < 60s | request < 30s | p95 <= 5s
TOLERANCE      0.01 kWh / 0.01 BDT

SCORING        25 interpretation | 25 application | 10 optimization
               10 API | 10 perf | 10 deploy | 10 docs
               opt_ratio = min(1, organizer_optimal / your_cost)

FATAL          LLM not in interpretation path => no shortlist
```

---

*Consolidated from the official BUP CSE Fest 2026 preliminary document pack. See `TRAPS.md` for the adversarial analysis of hidden pitfalls.*
