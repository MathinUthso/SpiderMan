# GridWise LLM — Traps, Tricks & Confusion Analysis

**Adversarial re-read of the official document pack.** Every finding below was verified against the actual documents or computed from the sample data. Findings are ordered by how much they cost you.

Legend: 🔴 fatal/disqualifying · 🟠 loses whole categories · 🟡 loses points · 🔵 wastes time or misleads

---

## Tier 1 — Fatal

### 🔴 T1. The official response example is *wrong* — it omits a note

**Problem Statement §10.4** gives this as the model response fragment:

```json
"directive_interpretation": [
  { "note_index": 0, ... "solar_reduction" ... },
  { "note_index": 2, ... "no_op" ... }
]
```

The matching example request in **§7.4 has three notes** (solar drop, do-not-charge, cafeteria menu). The response example shows **only indices 0 and 2 — index 1 (`no_charge_window`) is missing entirely.**

This directly contradicts the binding rule stated five separate times elsewhere: *"Every operator note must produce exactly one `directive_interpretation` entry"* in `note_index` order `0,1,…N-1`, and *"each note must appear once."*

**Why it's dangerous:** developers copy the example, not the prose. Building your response shape from §10.4 produces missing mappings, which the Guide classifies as *"schema/interpretation failures."* It damages **both** the 25-pt Interpretation score and the 3 API-schema points for `directive_interpretation` schema/order.

**Defence:** assert `len(interpretations) == len(operator_notes)` and `indices == list(range(n))` before you ever return. Treat §10.4 as an illustration of two *entry shapes*, not of a complete array.

---

### 🔴 T2. `plan_summary` is the disqualification bait

`plan_summary` is a **required response field** and is the one field that's natural-language prose. The obvious build is: regex/rules for the real logic, LLM for the pretty sentence.

That exact architecture is named and punished:

> **Violation:** "Required LLM absent from operator-note interpretation path, **or AI used only for `plan_summary`/documentation**"
> **Penalty:** "Fails the mandatory challenge requirement; **not eligible for the final preliminary shortlist**"

**Note the asymmetry:** every *other* penalty in that table is case-scoped ("affected hidden case invalid", "credit lost for the affected note"). This one is global and removes you from the shortlist **regardless of your 100-point score.** You could score 97 and not qualify.

They also say they'll verify by inspection, not just behavior: *"Automated and artifact verification may inspect the repository/architecture to confirm that a language-capable generative model directly produces the structured operator-note interpretation used by the optimizer."* Your repo and your video are both evidence.

**Defence:** the LLM must emit the `directive_interpretation` that the optimizer consumes. Make that flow obvious in code structure, README, and video. Don't bury it behind so many fallbacks that a reviewer can't find it.

---

### 🔴 T3. Regex on the public phrasings passes locally, dies hidden

The sample pack warns: *"Do not hard-code public note wording, case IDs, numeric values, or reference schedules."* The Guide rules phrase-matching-as-sole-interpreter **"Not compliant."**

The public data deliberately shows the *same* directive under rotating vocabulary — I extracted these families:

| Directive | Public wordings (all → same type) |
|---|---|
| `no_charge_window` | charger will be **isolated** · charging circuit **unavailable** · charging is **disabled** |
| `max_grid_window` | grid import **must not exceed** · the evening **transformer limit is** · grid intake must **stay at or below** |
| `minimum_battery_reserve` | keep at least **50% of the battery capacity** · keep at least 90 kWh · **requires at least** 80 kWh **to remain** |
| `solar_reduction` | **wash the panels** → 25% of forecast · **cloud cover** → about half · **inverter work** → 80% reduction |

And §11.4 shows three phrasings of one identical directive where the *trigger noun changes every time* (panel washing / PV production / inverter work) and the number is expressed three ways (20% / one-fifth / 80% reduction).

**5 of the 25 interpretation points are allocated specifically to "paraphrase robustness across related hidden notes."** It's measured directly.

**Worst property:** this failure is invisible before submission. A regex suite tuned on 10 public cases scores 10/10 locally and collapses on unseen vocabulary with no warning.

---

## Tier 2 — Category-killers

### 🟠 T4. End-of-day neutrality silently invalidates *everything* — measured

This is the single highest-expected-loss trap in the challenge, because the natural heuristic fails it **100% of the time**.

I implemented a reasonable greedy ("use solar, discharge when tariff is above median, charge when below") and ran it against all 10 cases:

| Case | Greedy cost | True optimal | Cost ratio | Final battery | Initial | Valid? |
|---|---|---|---|---|---|---|
| SAMPLE-01 | 41,145 | 38,365 | 0.932 | 140.0 | 110 | ❌ |
| SAMPLE-02 | 46,350 | 42,885 | 0.925 | 140.0 | 70 | ❌ |
| SAMPLE-03 | 37,370 | 35,480 | 0.949 | 140.0 | 120 | ❌ |
| SAMPLE-04 | 42,560 | 40,495 | 0.951 | 150.0 | 130 | ❌ |
| SAMPLE-05 | 36,870 | 33,950 | 0.921 | 150.0 | 120 | ❌ |
| SAMPLE-06 | 37,345 | 34,090 | 0.913 | 135.0 | 100 | ❌ |
| SAMPLE-07 | 41,270 | 38,550 | 0.934 | 160.0 | 150 | ❌ |
| SAMPLE-08 | 39,830 | 37,665 | 0.946 | 135.0 | 105 | ❌ |
| SAMPLE-09 | 38,623 | 34,873 | 0.903 | 160.0 | 120 | ❌ |
| SAMPLE-10 | 45,245 | 41,620 | 0.920 | 170.0 | 140 | ❌ |

**The cost looks fine — ~0.93 ratio, i.e. ~9/10 optimization points.** But neutrality fails in **all ten**, so the true score is:

- Optimization Quality: **0/10** (*"Invalid cases receive zero optimization credit"*)
- Directive Application: loses the 5 pts for *"action consistency/end-of-day neutrality"*

A 7% cost gap you'd shrug at actually costs ~15 points. And because the penalty is binary per case, **being slightly wrong costs the same as being wildly wrong.**

**Defence:** make final battery `== initial_energy_kwh` a *hard constraint inside* the optimizer (a DP terminal state or LP equality), never a post-hoc patch. Assert it before returning.

---

### 🟠 T5. "Correct interpretation, unapplied directive" — the pipeline gap

Stated three separate ways across the pack:

> *"A schedule that interprets a note correctly but does not apply it is still incorrect."*
> *"Correct extraction without correct downstream application does not pass the case."*
> *"The judge replays the plan using the true hidden directive, not only the team-reported interpretation."*

**The subtle part:** the judge uses **its own ground-truth directive** to replay your plan, not yours. Two independent consequences:

1. If you interpret correctly but a bug drops the constraint before the solver → interpretation points earned, application points lost, case invalid, no optimization credit.
2. **If you interpret *wrongly* and then apply your wrong interpretation faithfully, you still fail the replay** — because it's checked against the organizer's truth. There is no "internally consistent" partial credit on the schedule side.

Interpretation (25) and Application (25) are scored **separately and independently**. Getting one right does not shield the other.

**Defence:** after optimizing, re-validate `hourly_plan` against the parsed directives *in a separate code path from the one that built it*. Independent replay catches the "constraint got dropped" class of bug.

---

### 🟠 T6. Reserve binds only on the *listed hours* — and the reference plans exploit it

The rule: `battery_energy_after_kwh[h] >= max(base_min, directive_min)` **for each listed hour.**

I traced what the reference plans do immediately *after* a reserve window:

| Case | Reserve | Window | E after last window hour | E in the very next hour |
|---|---|---|---|---|
| SAMPLE-03 | 100 | [18,19,20] | 100 (h20) | **50** (h21) ← below reserve |
| SAMPLE-07 | 90 | [18,19,20,21] | 90 (h21) | 90 (h22) |
| SAMPLE-10 | 80 | [18,19,20,21] | 80 (h21) | **75** (h22) ← below reserve |

So the reserve is a **per-hour floor on the end-of-hour level, not a sticky commitment.** Dumping the battery the moment the window closes is legal and is what the optimal plans do.

**Two symmetric errors, both costly:**
- Over-applying (holding reserve after the window, or applying it to hours before it) → feasible but **more expensive** → loses optimization points.
- Under-applying (checking `E_before` instead of `E_after`, or off-by-one on the window) → **invalid case**, zero credit.

Also note: the floor is `max(base, directive)` — a hidden case could give a directive reserve **below** the base `minimum_energy_kwh`, making it a non-binding no-op. Blindly *replacing* the base with the directive value would then illegally lower your floor. All 3 public reserve directives are binding (100/90/80 vs base 40), so **public data never exercises this branch.**

---

### 🟠 T7. `max_grid_window` caps are *binding* — grid alone cannot meet demand

In every public `max_grid_window` case the cap is below demand in the capped hours, forcing solar/battery to cover the gap:

| Case | Cap | Demands in capped hours | Gap must come from battery/solar |
|---|---|---|---|
| SAMPLE-05 | 155 | 205, 215, 205 | 50, 60, 50 |
| SAMPLE-07 | 180 | 225, 215 | 45, 35 |
| SAMPLE-10 | 190 | 230, 220, **190** | 40, 30, **0** |

Two traps stacked:

1. **It's a feasibility constraint, not a preference.** Your solver must *plan ahead* — the battery has to arrive at hour 18 with enough charge, which couples back across the whole day. A myopic hour-by-hour solver hits the cap with an empty battery and produces an infeasible or invalid plan.
2. **SAMPLE-10 hour 21 has cap == demand exactly (190 == 190).** A strict `<` comparison instead of `<=` spuriously rejects a valid plan. The spec says "may not exceed" / "stay at or below" — inclusive.

**Worse in combination:** SAMPLE-07 and SAMPLE-10 put a `max_grid_window` **on top of** a `minimum_battery_reserve` over overlapping evening hours. The cap says *"discharge the battery to stay under the limit"*; the reserve says *"don't discharge below this level."* Both are hard. Satisfying them jointly requires arriving at the window with enough energy to do both — a global scheduling decision, not a local one. This is the intended difficulty spike.

---

### 🟠 T7b. All three `max_grid_window` caps are **non-binding** — the directive is untestable on public data

This is the single most dangerous finding in the pack, and it *inverts* part of T7.

I re-solved SAMPLE-05, 07 and 10 with the grid cap **deleted entirely**. The optimal cost is identical, and the unconstrained optimum already complies with the cap:

| Case | Cap | With cap | Cap removed | Δ |
|---|---|---|---|---|
| SAMPLE-05 | 155 | 33,950 | 33,950 | **0** |
| SAMPLE-07 | 180 | 38,550 | 38,550 | **0** |
| SAMPLE-10 | 190 | 41,620 | 41,620 | **0** |

The binding constraints are the battery discharge rate and neutrality — the cap never activates. **A team that parses `max_grid_window` and then silently drops it scores 10/10 on every public case.** The bug is invisible locally and surfaces only on hidden cases, where the cap may well bind.

Same for **SAMPLE-08's `no_charge_window` [11,12]: worth exactly 0 BDT** (37,665 either way). So **4 of the 14 applicable public directives have zero cost impact** (S-05 cap, S-07 cap, S-08 no-charge, S-10 cap).

This also means the SAMPLE-05 rationale is **factually wrong**. It claims the cap *"requires the optimizer to prepare sufficient battery energy beforehand."* No preparation is required. SAMPLE-07 and SAMPLE-10's rationales similarly overstate ("two simultaneous hard directives… must satisfy both") when the cap half is slack.

**Defence:** unit-test `max_grid_window` against a *synthetic* case with a cap you know binds (e.g. cap below demand with an empty battery). The public pack cannot validate this code path.

---

### 🟠 T7c. Ignoring **every** directive produces a *cheaper* plan → cost-only scoring would award 1.0

Directives only ever *add* cost. I measured the price of each case's full directive set:

| Case | True constrained optimum | Ignoring all directives | Directive cost | `min(1, opt/team)` |
|---|---|---|---|---|
| SAMPLE-01 | 38,365 | 34,600 | 3,765 | **1.000** |
| SAMPLE-02 | 42,885 | 42,660 | 225 | **1.000** |
| SAMPLE-03 | 35,480 | 34,960 | 520 | **1.000** |
| SAMPLE-04 | 40,495 | 39,295 | 1,200 | **1.000** |
| SAMPLE-05 | 33,950 | 33,950 | 0 | **1.000** |
| SAMPLE-06 | 34,090 | 31,630 | 2,460 | **1.000** |
| SAMPLE-07 | 38,550 | 37,830 | 720 | **1.000** |
| SAMPLE-08 | 37,665 | 36,965 | 700 | **1.000** |
| SAMPLE-09 | 34,873 | 27,830 | 7,043 | **1.000** |
| SAMPLE-10 | 41,620 | 41,010 | 610 | **1.000** |

Because `quality_ratio = min(1, organizer_optimal / your_cost)` and a cheating plan is *cheaper*, the ratio exceeds 1 and clamps to a perfect 1.0 in all ten cases.

**Why this matters to you:** it confirms the published formula is **not** what stops cheating — validity gating is, and it's applied *first* (*"GROUND TRUTH BEFORE COST"*). So if your cost comes out **below** the organizer's optimum, that is not a triumph, it's a **red flag that you dropped a constraint**. Use it as a self-test: a suspiciously cheap plan means a missing directive.

---

## Tier 3 — Point-losers

### 🟡 T8. The two documents disagree slightly on `/health`

- **Problem Statement:** *"Return HTTP 200 with a JSON object **containing** `status = "ok"`"* → extra fields permitted.
- **Participant Guide** (twice): *"`/health` returns `{"status":"ok"}`"* → shown as the exact literal.

A judge harness doing exact-dict comparison would reject `{"status":"ok","version":"1.2","model":"..."}`. The Problem Statement is canonical and more permissive, but the Guide's phrasing is what a checker gets written from.

**Defence:** return exactly `{"status": "ok"}` and nothing else. There is no upside to extra fields here — put diagnostics on a different route.

---

### 🟡 T9. `peak_grid_kwh` is a reporting field masquerading as an objective

The objective is **cost only**: `total_cost_bdt = Σ(grid_kwh[h] × tariff[h])`. But `peak_grid_kwh` is a required output, is named in the consistency checks, and "peak shaving" is what energy-domain intuition screams.

Nothing rewards minimizing it. The reference plans don't: I checked, and each one touches its peak in exactly **one** hour — no flattening. Any effort spent shaving peaks raises your cost and *lowers* your optimization ratio.

**Defence:** compute `peak = max(grid_kwh)` from the final plan and report it. Never optimize it. (Only `max_grid_window` constrains grid per-hour, and only in its listed hours.)

---

### 🟡 T10. Totals must be recomputed *from* the plan, not accumulated

> *"`hourly_plan` is the source of truth for totals and validity."*
> Penalty: *"Reported totals disagree with `hourly_plan` … Recalculation/scoring deduction; repeated failures may block qualification eligibility."*

If you accumulate totals inside the solver and then round, clamp, or adjust `hourly_plan` afterwards, the two drift apart. Note this is one of the few penalties that escalates to **blocking qualification** on repetition.

**Defence:** serialize `hourly_plan` first, then derive all three of `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh` by iterating the serialized array. Round the plan values *before* summing, so your arithmetic matches the judge's on identical inputs.

### 🟡 T10b. SAMPLE-06 cannot detect an inverted `solar_reduction` factor

The `factor`-means-*remaining* convention (T/spec §4.1) is the most commonly inverted rule in the challenge. I tested using `1 − factor` by mistake:

| Case | Factor | Correct optimum | With inverted factor | Detectable? |
|---|---|---|---|---|
| SAMPLE-01 | 0.25 | 38,365 | 35,825 | yes (−2,540) |
| SAMPLE-09 | 0.2 | 34,873 | 28,802 | yes (−6,071) |
| **SAMPLE-06** | **0.5** | **34,090** | **34,090** | **NO — identical** |

SAMPLE-06's factor is exactly 0.5, and `1 − 0.5 = 0.5`. A team that happens to test on SAMPLE-06 gets a perfect result while holding the convention backwards.

**Defence:** always test the inversion on a factor ≠ 0.5. Note also that inverting makes plans look *cheaper* — see T7c: cheaper than the reference means a bug.

---

### 🟡 T10c. The base `minimum_energy_kwh` applies to **every** hour — the spec never quite says so

Problem Statement §9.2 reads: *"`minimum_energy_kwh <= E_after <= capacity_kwh`. If a `minimum_battery_reserve` directive is active, its reserve may be higher than the base minimum for those hours."* It never explicitly states the base minimum binds in **all 24 hours** rather than only at hour 23 or only inside reserve windows.

Ground truth is all-hours — that's the only reading under which all 10 references are optimal (verified). The ambiguity is worth real money if you get it wrong:

| Case | Correct optimum | Base minimum ignored | Understated by |
|---|---|---|---|
| SAMPLE-09 | 34,873 | 34,393 | **480** |
| SAMPLE-02 | 42,885 | 42,435 | **450** |
| SAMPLE-05 | 33,950 | 33,590 | **360** |
| SAMPLE-06 | 34,090 | 33,750 | **340** |
| SAMPLE-01 | 38,365 | 38,045 | **320** |
| SAMPLE-08 | 37,665 | 37,445 | **220** |
| SAMPLE-04 | 40,495 | 40,375 | **120** |
| SAMPLE-03 / 07 / 10 | — | — | 0 (reserve dominates) |

**The cruel structure:** the three cases that *have* a reserve directive (03/07/10) are exactly the three where the base minimum is non-binding — so they can't catch this bug. And the seven that can catch it have no reserve directive to draw your attention to reserve logic at all.

---

### 🟡 T10d. `peak_grid_kwh` is not invariant across equally-optimal plans

`total_grid_kwh` is uniquely determined at optimal cost in all 10 cases, but `peak_grid_kwh` is **not**. Two cases admit a fully-valid alternate plan at *identical* cost and identical total grid, with a higher peak:

- **SAMPLE-01:** reference peak 175; an alternate optimum has h13 grid = 187.5 → peak **187.5**. (h13 grid is free in [152.5, 187.5].)
- **SAMPLE-09:** reference peak 170; an alternate optimum has h13 grid = 187 → peak **187.0**. (h13 free in [127, 187].)

The reference happens to be the *minimum*-peak representative. A judge comparing your `peak_grid_kwh` against the reference value would reject valid equal-cost submissions — but the spec only requires `peak_grid_kwh` to be **self-consistent with your own plan**, and `equivalence_note` accepts equal-cost alternatives.

**Defence:** nothing to fix, but don't be alarmed if your peak differs from the public reference at matching cost — that's legal. Just make sure it matches *your* plan (T10). If you want to hedge against a naive judge, break optimal-cost ties toward the lower peak; it costs nothing.

---

### 🟡 T10e. Multiple optimal schedules exist in **every** case — tie-heavy by construction

Every case has 3–7 hours where `grid_kwh` can vary across a range at unchanged optimal cost (e.g. SAMPLE-04 h1 ∈ [55,145] with reference 90; SAMPLE-01 h0 ∈ [40,100] with reference 90). Battery throughput varies enormously at identical cost — SAMPLE-10 ranges [670, 2450] kWh.

The flexibility clusters on **tariff-tie hours**, and ties are pervasive: every case has 5–7 groups of equal tariffs (SAMPLE-01: tariff 6 at h{0,1,5}, tariff 5 at h{2,3,4}, tariff 14 at h{9,13,15}). SAMPLE-06 even ties the evening peak (tariff 27 at both h18 and h20).

**Defence:** never diff your schedule against the reference plan hour-by-hour when self-testing — compare **cost** (and validity). Matching the reference's exact action sequence is neither required nor achievable in general.

---

### 🟡 T11. Float dust from `factor` multiplication

`effective_solar = solar × factor` can produce values that aren't representable. The 0.01 tolerance protects you *if the judge applies it symmetrically*, but a strict `solar_used <= effective_solar` check fails on `52.000000000000007 <= 52.0`.

In the public data these products happen to land exactly (170×0.25=42.5, 230×0.2=46.0, 260×0.2=52.0 — all exact in IEEE754), so **this trap is latent in public data and may fire only on hidden numbers.** That's the worst kind: untestable locally.

**Defence:** round outputs to 2 decimals; compare with an epsilon (1e-6) internally; and clamp `solar_used = min(solar_used, effective_solar)` on the way out so you can never exceed by dust.

---

### 🟡 T12. `idle` must carry `battery_kwh == 0`

`battery_action` is exactly one of `charge`/`discharge`/`idle`, and *"`battery_kwh` … Must be 0 when idle."* A solver that emits `{"battery_action":"charge","battery_kwh":0}` for a do-nothing hour is technically inconsistent with the enum's intent, and *"action consistency"* is explicitly named in the 5-point Application sub-criterion.

**Defence:** derive the label from the signed delta with a tolerance — `|δ|<1e-6 → idle, 0` ; `δ>0 → charge` ; `δ<0 → discharge, |δ|`. Never emit a nonzero magnitude with `idle`, or a zero magnitude with a directional action.

---

## Tier 4 — Misleading patterns in the public data

These are *regularities in the 10 public cases that the spec never promises.* Every one is a place where local success teaches a false lesson. This is the most under-appreciated category.

| # | Pattern — true in all 10 public cases | Why it misleads |
|---|---|---|
| 🔵 **T13** | `max_charge == max_discharge` (50/50, 55/55, 60/60, 65/65) | Two *separate* fields exist in the schema. Hidden cases can make them asymmetric; code that reads one rate for both breaks silently. |
| 🔵 **T14** | **Zero solar curtailment** — effective solar is 100% consumed in all 10 references | The spec explicitly says *"Unused solar is curtailed."* If a hidden case has surplus solar with a full battery, you **must** curtail. A solver that assumes "all solar is always usable" produces an unsatisfiable balance equation. |
| 🔵 **T15** | Tariff peaks at **hour 19** and bottoms at **hour 2–3** in *all ten* cases (range 4–34) | Invites hardcoded "charge at night, discharge at 6–8 PM" logic. Hidden cases vary tariff; the spec only says values vary. Also note SAMPLE-01 h1 *discharges* at tariff 6 then *charges* at tariff 5 — optimal play is non-monotonic and defeats simple threshold rules. |
| 🔵 **T16** | Battery is never initially at `minimum` or at `capacity` | Boundary-condition bugs (division by zero on headroom, negative available range) never surface locally. |
| 🔵 **T17** | Every reserve directive is strictly **above** base minimum | The `max(base, directive)` branch where the directive is *lower* is never exercised. See T6. |
| 🔵 **T18** | `demand > 0` in every hour of every case | A zero-demand hour (plausible hidden edge) can break solvers that divide by demand or assume grid > 0. |
| 🔵 **T19** | Only 8 of 10 cases have a `no_op`; max 3 notes, and **no case has two notes of the same directive type** | Two overlapping `no_charge_window`s, or two reserves with different values on overlapping hours, would need union/max merging logic you've never tested. The spec permits 1–3 notes with no distinctness guarantee. |
| 🔵 **T20** | **No solar in any night hour** (h0–h5, h20–h23 are 0 in all 10 cases) | Solar is nonzero only h6–h17. Code that implicitly assumes "night = no solar" is untested against a hidden case with different generation. |
| 🔵 **T21** | `initial_energy_kwh == capacity/2` in exactly 4 of 10 (S-01, 05, 08, 09) | Just close enough to look like a rule. It isn't — S-02 is 70/200, S-07 is 150/250. |
| 🔵 **T22** | The two nastiest directive interactions are **absent**: no `no_discharge` inside a reserve window, and no grid cap inside a `no_discharge` window | These are the combinations that could create genuine infeasibility pressure. The pack gives you **no example to test conflict handling against**, while promising hidden cases won't be contradictory. Only reserve × grid-cap overlaps appear (S-07 h[19,20], S-10 h[19,20,21]). |
| 🔵 **T23** | The JSON uses non-ASCII punctuation (em-dash U+2014, middot U+00B7) in `_meta` | On Windows, `open(path)` without `encoding='utf-8'` gives mojibake (`â€"`, `Â·`). An environment trap, not a data error — but it will corrupt your test harness output. |

### 🔵 T19b. An end-inclusive off-by-one is **invisible in 4 specific places**

Reading windows as end-*inclusive* (the most likely interpretation error) changes the optimum in most cases — so it's usually detectable:

| Case | Correct | End-inclusive | Δ |
|---|---|---|---|
| SAMPLE-09 | 34,873 | 36,849 | +1,976 |
| SAMPLE-06 | 34,090 | 35,740 | +1,650 |
| SAMPLE-01 | 38,365 | 39,730 | +1,365 |
| SAMPLE-04 | 40,495 | 41,285 | +790 |
| SAMPLE-08 | 37,665 | 38,415 | +750 |
| SAMPLE-03 | 35,480 | 35,880 | +400 |
| SAMPLE-05 | 33,950 | 34,030 | +80 |
| SAMPLE-02 | 42,885 | 42,960 | +75 |
| SAMPLE-07 | 38,550 | 38,590 | +40 |
| SAMPLE-10 | 41,620 | 41,635 | +15 |

Note how small the margin gets: **SAMPLE-10 is only 15 BDT and SAMPLE-07 only 40 BDT** — a gap easily dismissed as rounding noise. And per-directive, the extra hour is *completely free* (+0) in four places: S-06's `no_charge` [14,15]→16, S-07's reserve [18–21]→22, S-08's `no_charge` [11,12]→13, and S-10's cap [19–21]→22.

**Defence:** assert the window arithmetic directly against the note text in unit tests, rather than inferring correctness from cost.

**Verified:** solar *does* exceed demand in SAMPLE-06 (h11–13) and SAMPLE-09 (h10–14) — e.g. SAMPLE-09 h12 has 260 kWh solar against 180 kWh demand. At SAMPLE-09 h10 the reference sets `solar_used=180 > demand=165`, `grid=0`, and charges the 15 kWh surplus into the battery. So surplus solar already appears, but it is always fully absorbable. **Curtailment is never yet forced** — T14 remains untested territory.

---

## What I verified computationally

So you know which claims here are measured rather than reasoned:

1. **All 10 reference schedules are fully valid** — I replayed every one against energy balance, effective solar, battery bounds, rate limits, state transitions, all four window directives, neutrality, and the three reported totals. **10/10 pass**, zero discrepancies. The spec is internally consistent and my reading of it matches the organizers'.

2. **All 10 reference costs are genuinely optimal.** I wrote an independent DP over battery levels discretized at 2.5 kWh (all input values are multiples of 5; plans use multiples of 2.5) with neutrality as a terminal constraint. It reproduced **all ten reference costs to the cent**:

   | | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 |
   |---|---|---|---|---|---|---|---|---|---|---|
   | Reference | 38365 | 42885 | 35480 | 40495 | 33950 | 34090 | 38550 | 37665 | 34873 | 41620 |
   | My DP | 38365 | 42885 | 35480 | 40495 | 33950 | 34090 | 38550 | 37665 | 34873 | 41620 |

   **Consequence:** the published costs are trustworthy optimization targets — if you don't match them, you're losing points, not disagreeing with a sloppy reference. And a correct DP/LP is *sufficient* for full marks; no exotic technique needed.

3. **Battery efficiency is exactly 100%** — verified across all 240 plan-hours that `E_after = E_before ± battery_kwh` with zero residual. No round-trip loss, no degradation, no ramp limits. Do **not** add efficiency modeling the spec doesn't ask for; it would make your plans differ from ground truth.

4. **Reference plans use fractional values** (e.g. `grid_kwh: 152.5`, `solar_used_kwh: 42.5`). An integer-only solver cannot reach optimal cost. All values are multiples of 0.5.

5. **Greedy fails neutrality 10/10** — the measured table in T4.

6. **Sensitivity tests, each re-solved with one rule removed or broken.** All figures below are from my own solver and were independently reproduced by a second, exact-rational simplex implementation:
   - Grid caps non-binding: Δ0 in all 3 cases (T7b)
   - SAMPLE-08 `no_charge` non-binding: Δ0 (T7b)
   - Ignoring all directives is cheaper in 9/10, equal in 1 → ratio clamps to 1.0 everywhere (T7c)
   - Base minimum ignored: understates cost 120–480 BDT in 7 cases (T10c)
   - Neutrality dropped: understates cost 280–970 BDT in all 10 (T4)
   - Factor inverted: detectable except SAMPLE-06 (T10b)
   - End-inclusive windows: +15 to +1,976 BDT (T19b)

7. **Forced endgame.** `h23` charge is pinned to *exactly* the max charge rate in **9 of 10** cases (only SAMPLE-02 has slack, [40,55]) — the battery is drained into the evening peak and neutrality must be restored at the rate limit in h22–h23. SAMPLE-03/04/08 additionally force a full-rate **discharge** at h21, and SAMPLE-10 forces a discharge of ≥5 kWh at h22 (tariff 11) — counterintuitive, and exactly what a greedy "stop discharging after the peak" rule misses.

8. **Inputs are 100% integers** (all 240 demand, solar, and tariff values). Demand and solar are multiples of 5; **tariffs are not** (4,6,7,8,9,11,… all appear). Only **two** cases have any non-integer in the reference plan, and the sole half-integer in the entire pack is SAMPLE-01 h13 (`grid 152.5`, `solar_used 42.5`). All 240 `battery_kwh` and all 240 `battery_energy_after_kwh` values are integers — so a **step-5 battery lattice reaches the exact optimum in all 10 cases** (verified). Fractional values enter only through the grid/solar split of reduced solar.

---

## Priority defence checklist

Ordered by expected points saved:

1. **Neutrality as a hard in-solver constraint**, asserted before returning (T4)
2. **LLM visibly produces `directive_interpretation`** — architecture, README, video (T2, T3)
3. **One entry per note, indices `0..n-1`, asserted** — ignore §10.4's shape (T1)
4. **Base `minimum_energy_kwh` enforced in all 24 hours**, floor = `max(base, directive)` (T10c, T6)
5. **Independent post-optimization replay** of the plan against parsed directives (T5)
6. **Unit-test grid caps and `no_charge` on synthetic binding cases** — public data cannot exercise them (T7b)
7. **Treat "cheaper than the reference" as a bug signal, not a win** (T7c)
8. **Reserve applies to `E_after` of listed hours only** — release it after the window (T6)
9. **Inclusive comparisons** (`<=`, `>=`) on grid caps and reserves (T7)
10. **Test factor inversion on a factor ≠ 0.5** (T10b)
11. **Totals recomputed from the serialized plan**, after rounding (T10)
12. **Exact `{"status":"ok"}`** on `/health` (T8)
13. **Report but never optimize `peak_grid_kwh`**; break cost ties toward lower peak (T9, T10d)
14. **Read `max_charge` and `max_discharge` separately; support curtailment; don't hardcode the hour-19 peak** (T13–T15)
15. **Derive `idle`/`charge`/`discharge` from a tolerance-checked delta** (T12)
16. **Round outputs to 2dp, clamp `solar_used` to effective solar** (T11)
17. **Self-test on cost + validity, never by diffing the reference schedule** (T10e)
18. **Open the JSON with `encoding='utf-8'`** (T23)

---

## The meta-trap

The scoring shape is the real trick, and it's easy to misread:

```
Correctness (interpretation + application)  50 pts
Optimization quality                       10 pts
Everything else (API/perf/deploy/docs)     40 pts
```

Cost optimization — the part that *looks* like the hard algorithmic challenge and where teams instinctively spend their four hours — is worth **10 points, and it is gated**: every point of it requires the case to already be valid under the organizer's ground-truth directives.

Meanwhile **40 points sit in API contract, performance, deployment, and documentation** — work that is entirely under your control, has no hidden test set, and cannot be lost to a paraphrase you didn't anticipate.

Optimal strategy in a 4-hour window: get a *valid* plan for every case first (a correct DP is enough to also be optimal, per finding #2), lock down the schema and the deploy, write the README — and only then tune. A valid, slightly-expensive schedule with a clean deployment beats a brilliant optimizer behind a broken contract by a wide margin.

---

*Companion to `GRIDWISE_SPEC.md`. All findings verified against the official pack or computed from `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`.*
