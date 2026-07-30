# Recovery Engine — M1–M3 (PED / non-disclosure)

Deterministic graph engine for Indian health-insurance claim-denial recovery.
A **rule engine decides the law**, **templates narrate**, and a **validator
guarantees grounding** — a hallucinated citation is structurally impossible.
This repo implements **Milestones 1–3** of `ARCHITECTURE.md`: the PED /
non-disclosure ground, end-to-end — deterministic core (M1), tiered document
parsing (M2), and the leashed narrator + Stage 0–4 lifecycle (M3).

## Pipeline

```
 documents ──► parse_documents() ──► Case (typed, anchored slots)
   (PDF)         parser/                     │
                 (Tier 1 digital,            ▼
                  Tier 2 OCR)         run_session()  ── Stage 0 eligibility gate
                                        statemachine   ── Stage 1 diagnose()  ─ engine.py + grounds/ped
                                                        ── Stage 2 interview   ─ narrator.py (leashed LLM)
                                                        ── Stage 3 route (fork)
                                                        ── Stage 4 draft()+validate()+evidence gate
```

The M1 core is also usable directly: `recovery_engine.run(case)` does
`diagnose → draft → validate` and returns a `Result` whose `.shippable` is true
only when the pre-delivery gate finds zero violations. The M3 entry point is
`recovery_engine.run_session(case, answers=..., provided_docs=..., as_of=...)`,
returning a `SessionResult`.

## What's implemented

| Spec section | Here |
|---|---|
| §4.1 typed, source-anchored slots | `slots.py` (`Slot`, `Anchor`, `SLOT_SPECS`, type + plausibility gates) |
| §6.1 levers L1–L7 | `grounds/ped.py` (`LEVERS`) |
| §6.3 deterministic predicates + verdict | `grounds/ped.py` `evaluate()`, `engine.py` `diagnose()` |
| §6.4 assertion templates (clause+reg+fact) | `letter.py` |
| §6.5 validator V1–V5 | `validator.py` |
| §9 versioned citation store | `citations.py` (date-scoped, `resolve(rule, relevant_date)`) |
| §2.6 honest decline on doomed cases | `letter.Decline` + V5 |
| §8 tiered, anchored parser (Tier 1 digital, Tier 2 OCR) | `parser/` (`digital.py`, `ocr.py`, `extract.py`, `schema.py`) |
| §8 confidence gating + cross-doc reconciliation + review queue | `parser/pipeline.py`, `parser/reconcile.py` |
| §14 thin, swappable LLM (OpenRouter/Groq) | `llm/` (`openai_compat.py`) — optional; deterministic without a key |
| §10 leashed narrator: render + interpret, guards, turn log | `narrator.py`, `interview.py` |
| §4.2 Stage 0–4 lifecycle + §13.2 deadlines + §13.3 evidence-sufficiency | `statemachine.py` |

**Effective-date-versioned law (§2.4/§9):** a 2023 denial is judged under the
8-year moratorium; a post-1-April-2024 denial under 60 months. The engine picks
the version in force at the case's *relevant date* (the denial date), not today.

## Run

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python demo.py        # M1 letter, M2 parse, M3 full lifecycle
.venv/bin/python -m pytest -q   # 51 tests
```

### Enabling the LLM (optional, M3)

The narrator runs deterministically with no key. To let it rephrase questions and
interpret genuinely freeform answers, set:

```bash
export LLM_PROVIDER=groq            # or openrouter
export LLM_API_KEY=sk-...           # or GROQ_API_KEY / OPENROUTER_API_KEY
export LLM_MODEL=llama-3.3-70b-versatile   # optional override
```

The LLM output is always re-validated through the deterministic coercion — it can
never smuggle a value past the schema, and it never decides the law.

## Deliberately out of scope (later milestones)

Nexus graph (M5 — L3 currently requires an explicit human ruling, never a guess),
offline eval harness / golden set (M5), regulatory-freshness agent + precedent
store (M7), grounds 2–4 deep schemas (M8). Tier-2 OCR ships as a swappable
interface with a fake backend for tests and a real (unexercised) Textract adapter;
Tiers 3–4 (handwriting vision-LLM, clause extraction) are not built. Non-PED
grounds are not yet stubbed.

## Notes on citations

Citation constants live in `citations.py`. The 2024 Master Circular
(`IRDAI/HLT/CIR/MISC/77/05/2024`) is the anchor. Pre-2024 and general-principle
entries are flagged `provisional=True` — honest placeholders awaiting human
legal ratification (§2.5/§12); they are not autonomously mutated.
