# Recovery Engine — M1 (PED / non-disclosure)

Deterministic graph engine for Indian health-insurance claim-denial recovery.
A **rule engine decides the law**, **templates narrate**, and a **validator
guarantees grounding** — a hallucinated citation is structurally impossible.
This repo implements **Milestone 1** of `ARCHITECTURE.md`: the PED /
non-disclosure ground, end-to-end, deterministic, with hand-entered slots. No
parser and no LLM yet (those are M2/M3).

## Pipeline

```
Case (typed slots)  →  diagnose()  →  draft()   →  validate()
   slots.py            engine.py      letter.py    validator.py
                       + grounds/ped  + citations
```

`diagnose → draft → validate` is wrapped by `recovery_engine.run(case)`, which
returns a `Result` whose `.shippable` is true only when the pre-delivery gate
finds zero violations.

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

**Effective-date-versioned law (§2.4/§9):** a 2023 denial is judged under the
8-year moratorium; a post-1-April-2024 denial under 60 months. The engine picks
the version in force at the case's *relevant date* (the denial date), not today.

## Run

```bash
python demo.py          # two worked cases: a STRONG letter and an honest decline
python -m pytest -q     # 23 tests
```

## Deliberately out of scope for M1

Parser/OCR (M2), leashed-LLM narrator (M3), nexus graph (M5 — L3 currently
requires an explicit human ruling, never a guess), eval harness (M5), deadline
engine / evidence-sufficiency / fraud guard (M6), regulatory-freshness agent and
precedent store (M7), grounds 2–4 (M8). Non-PED grounds are not yet even stubbed.

## Notes on citations

Citation constants live in `citations.py`. The 2024 Master Circular
(`IRDAI/HLT/CIR/MISC/77/05/2024`) is the anchor. Pre-2024 and general-principle
entries are flagged `provisional=True` — honest placeholders awaiting human
legal ratification (§2.5/§12); they are not autonomously mutated.
