# Recovery Engine — M1–M3 (PED / non-disclosure)

Deterministic graph engine for Indian health-insurance claim-denial recovery.
A **rule engine decides the law**, **templates narrate**, and a **validator
guarantees grounding** — a hallucinated citation is structurally impossible.
This repo implements **Milestones 1–3** of [ARCHITECTURE.md](ARCHITECTURE.md): the
PED / non-disclosure ground, end-to-end — deterministic core (M1), tiered document
parsing (M2), and the leashed narrator + Stage 0–4 lifecycle (M3). M4–M8 are
specified in that document but deliberately not built; see
[Deliberately out of scope](#deliberately-out-of-scope-later-milestones).

## Why this exists

I have not had a claim denied myself. This began with the data.

Reading through Indian insurance-claims data, one number did not go away: **over a
third of health-insurance claims are rejected.**<!-- TODO(vineet): add the precise
source + year here — IRDAI Annual Report or equivalent. A reviewer may check it. -->
A doctor friend working in a government hospital confirmed the pattern from the
other side of the counter, and added that it falls hardest on people with the least
room to absorb it — Ayushman Bharat cardholders, for whom a rejected claim is not a
reimbursement delay but a bill they cannot pay.

What I found when I looked for the remedy was worse than the denial rate. A cottage
industry of claim-recovery firms charges **up to 20% of the claim amount** to
contest a rejection — for a process that is already free. The insurer's own
Grievance Redressal Officer costs nothing. The Insurance Ombudsman after that costs
nothing. People are paying a fifth of what they are owed for access to a remedy
they already have.

They pay it because free is not the same as usable. The policyholder is usually
right, the regulation is usually on their side, and they lose anyway — because they
cannot assemble the argument in the form a Grievance Redressal Officer needs to see
it: the specific clause, the regulation that overrides it, the date arithmetic, in
writing, citable. That is not a legal problem. It is a document-assembly problem
wearing a legal costume.

So the thesis this repo tests: **if a policyholder can put the correct citation in
front of the insurer, most denials do not survive it** — and the ones that do can go
to the Ombudsman, which is also free. That is a hypothesis, not a measured result;
the offline eval harness that would put a number on it is M5, and is not built.

And it is the entire reason this is a deterministic engine rather than a chatbot. If
the argument that reaches the GRO contains one invented citation, the user has spent
their single credible shot — and they are in a worse position than if they had never
written. A wrong answer is not a degraded answer here. It is an actively harmful one.
Hence: the rule engine decides the law, templates narrate, and a validator refuses to
ship anything the documents and regulations do not support.

**Scope note.** The motivation above is broader than what this repo covers. The
engine targets **IRDAI-regulated private health insurance** — the Grievance
Redressal Officer → Insurance Ombudsman rail, under the 2024 IRDAI Master Circular.
Ayushman Bharat (PM-JAY) runs on a different rail entirely: the National Health
Authority's grievance machinery, not the Ombudsman, and the moratorium and
waiting-period levers here do not map onto it. PM-JAY is domain pack #2 — the same
kernel, a different enforcement rail — and it is not built. Claiming otherwise would
be the exact failure mode this architecture exists to prevent.

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

See [docs/REPO_GRAPH.md](docs/REPO_GRAPH.md) for the module dependency graph and a
"where to change X" index — the map to consult before editing.

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
.venv/bin/python -m pytest -q   # 56 tests, no network required
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

**Yes/no questions are never LLM-rephrased.** Their meaning lives in their
polarity, and a rephrase can invert it while staying perfectly on topic: asked to
rewrite *"has there been any gap or break in your renewals?"*, the model reliably
returns *"have you had continuous coverage, without any breaks?"* — same subject,
opposite sense. A truthful "yes" would then record `continuity_breaks=True` for an
unbroken policy and silently drop the L1 moratorium lever from the letter. The
on-topic guard cannot catch this (the keywords match either way), so the leash on
bool slots is structural rather than heuristic — see `_POLARITY_BEARING_KINDS` in
`narrator.py`. Dates and enums carry no polarity and are still rephrased; answer
*interpretation* stays LLM-assisted for every kind, since the policyholder always
saw the scripted wording.

## Deliberately out of scope (later milestones)

Nexus graph (M4 — L3 currently requires an explicit human ruling, never a guess),
offline eval harness / golden set (M5), lifecycle hardening beyond the deadline
and evidence gates (M6), regulatory-freshness agent + precedent store (M7),
grounds 2–4 deep schemas (M8). Tier-2 OCR ships as a swappable
interface with a fake backend for tests and a real (unexercised) Textract adapter;
Tiers 3–4 (handwriting vision-LLM, clause extraction) are not built. Non-PED
grounds are not yet stubbed.

## Notes on citations

Citation constants live in `citations.py`. The 2024 Master Circular
(`IRDAI/HLT/CIR/MISC/77/05/2024`) is the anchor. Pre-2024 and general-principle
entries are flagged `provisional=True` — honest placeholders awaiting human
legal ratification (§2.5/§12); they are not autonomously mutated.
