# AGENTS.md — AI Agent Instructions

## Project Context
GridWise LLM for BUP CSE Fest 2026 Hackathon.
LLM interprets operator notes → guardrails validate → optimizer solves.

## Before Writing Code
1. Read `docs/GRIDWISE_SPEC.md` — this is the canonical spec
2. Read `docs/TRAPS.md` — adversarial pitfalls that cause silent failures
3. Read `docs/optimizationMath.md.md` — optimization formula

## Anti-Hallucination Rules
1. **Never assume a library exists** — check package.json, requirements.txt, or imports first
2. **Never guess API schemas** — refer to spec §6 (request) and §10 (response)
3. **Never hardcode public sample values** — hidden cases differ
4. **Never skip validation** — LLM output is untrusted until guardrails pass
5. **When uncertain, STOP and ask** — do not guess

## Escape Hatch: When You're Stuck
- Re-read the relevant spec section
- Check TRAPS.md for known pitfalls
- Run existing tests to see what passes/fails
- Write a minimal test to verify your assumption
- If still uncertain: state what you don't know and ask

## Code Conventions
- Python 3.11+
- Type hints on all public functions
- Docstrings on modules and classes
- Round outputs to 2 decimal places
- Use `<=` / `>=` for constraints (inclusive, not strict)

## Verification Checklist
Before marking any task complete:
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `POST /optimize-energy` returns valid JSON with all 7 required fields
- [ ] `directive_interpretation` has exactly one entry per operator note
- [ ] `hourly_plan` has exactly 24 entries, hours 0-23
- [ ] Battery neutrality: `E_after[23] == initial_energy_kwh`
- [ ] Energy balance holds every hour
- [ ] No secrets in code, logs, or responses

## Forbidden
- Do not commit API keys, tokens, or .env files
- Do not expose secrets in logs or error responses
- Do not use LLM only for plan_summary (disqualifying)
- Do not hardcode public note phrasing
