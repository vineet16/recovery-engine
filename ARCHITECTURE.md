# Recovery Engine — Architecture Specification

> Working name: **Recovery Engine**. Domain pack #1: **Indian health insurance claim-denial recovery**.
> This document is the design specification and the source of truth for the build.

## Status: what is built vs. what is specified

This spec describes the whole system. **The repository implements M1–M3 only** —
the slice §15 designates as the first usable one. Read it as a design document
with a deliberate line drawn through it, not as a description of shipped code.

| | Milestones | State |
|---|---|---|
| **Built** | M1 deterministic core · M2 tiered parser · M3 narrator + Stage 0–4 | Working, 56 tests |
| **Specified, not built** | M4 Nexus graph · M5 eval layers · M6 lifecycle hardening · M7 freshness agent + precedent store · M8 grounds 2–4 | Design only |

Section-by-section mapping of spec → code is in
[README.md](README.md#whats-implemented); the deferral rationale is in
[README.md](README.md#deliberately-out-of-scope-later-milestones).

---

## 1. Purpose & thesis

Build a system that takes a policyholder's **rejected insurance claim** and produces a **legally precise, evidence-grounded grievance / ombudsman filing** that forces the insurer to settle — delivered as an effortless conversational experience, with zero human drafting on the happy path.

**Architectural thesis (non-negotiable):** This is a *deterministic graph* system. A rule engine decides the law; the LLM only *narrates* (renders questions, drafts prose from fixed templates); a validator guarantees nothing is asserted that the documents and regulations don't support. This is a structural replacement for RAG in a cross-referential, regulated document domain — a general kernel, pointed here at a consumer legal-recovery problem.

The competitive edge is **reliability + auditability**, not features. A hallucinated citation is not a typo — it burns the user's one credible shot in front of a Grievance Redressal Officer (GRO). The whole architecture exists to make that impossible.

---

## 2. Non-negotiable principles (anti-patterns to reject)

1. **No vector store in the extraction or filing path.** User documents are parsed into *typed, source-anchored fields*, never embedded for semantic recall. (A vector store is permitted in exactly one place — the precedent library — as a research/enrichment aid feeding human curation, never as the path by which a fact enters a filing. See §13.4.)
2. **The LLM never decides the law.** It has exactly two bounded jobs: (a) render the question for the slot the graph selected; (b) interpret a freeform answer into that slot's schema. Everything structural — which ground is active, which slots to collect, which levers fire, what the letter asserts — is the graph's.
3. **Every asserted fact is welded to a source.** Each extracted value carries `(value, confidence, document, page, span)`. Each legal claim maps to a fired lever + a versioned citation. Nothing free-floating ever ships.
4. **Law is effective-date-versioned.** Citations are scoped `(rule, effective_from, effective_to, source)`. The engine selects the version valid at the *relevant date of the case*, not today.
5. **No autonomous mutation of the rulepack or citation store.** The regulatory-freshness agent *detects and proposes*; a human ratifies; updates are versioned.
6. **Decline doomed cases honestly.** If no strong/moderate lever fires, the engine does not draft a wrongful-repudiation letter — it explains why the denial is likely valid. This protects win-rate integrity and earns user trust.

---

## 3. Domain context (the enforcement rail)

The system's output lands in a real, binding rail. This context drives the state machine and deadlines.

- **Escalation path:** internal grievance with insurer's GRO → wait 30 days (or receive unsatisfactory reply) → Insurance Ombudsman (Bima Lokpal).
- **Ombudsman properties:** free; self-represented (no lawyer provision); must decide within ~90 days; binding on the insurer up to ₹30 lakh; jurisdiction up to ₹50 lakh; award ignored → insurer pays ₹5,000/day.
- **Hard deadlines:** insurer must respond to grievance within 15 days; ombudsman complaint must be filed **within 1 year** of the insurer's final reply. Missing the 1-year cliff silently kills a winnable case.
- **Why grievance-stage matters most:** a well-drafted grievance letter that cites the exact clause + regulation + fact triplet signals to the GRO that the repudiation *loses on escalation*, triggering "settle now" — most wins happen here, before the ombudsman is ever invoked.

---

## 4. System architecture

### 4.1 The kernel (six layers)

```
Parser  →  Schema  →  Rule Engine  →  Findings Store  →  Narrator  →  Validator
(typed,    (typed     (levers +       (verdict +          (leashed    (grounding +
 anchored   slots)     decision        fired levers +      LLM: Qs +   citation +
 extraction)           logic)          citations)          drafts)     arithmetic gate)
```

### 4.2 The interactive shell — case lifecycle state machine

A case is a **long-lived stateful entity** (multi-week), driven by deadlines. Stages:

- **Stage 0 — Intake & eligibility gate.** Ingest documents (denial letter = primary, policy, bills, proposal form). Parse core fields. Hard gates: within 1 year of denial? amount ≤ ₹50L? not already in court/consumer forum (disqualifies)? line-of-business dispatch (health / motor / life → selects taxonomy + forum). Output: eligible / not-yet-eligible / ineligible.
- **Stage 1 — Contestability diagnosis.** Classify denial ground; run that ground's decision logic; produce verdict (STRONG / MODERATE / LIKELY-VALID). If LIKELY-VALID → decline with honest explanation.
- **Stage 2 — Targeted interview.** Ground-specific slot-filling. The graph owns the slot list and order; the leashed LLM renders questions and parses answers. Adaptivity allowed on *depth* (rephrase, one bounded clarifier on the same slot), never on *breadth* (no new topics, no advice). Misclassification signal → return control to graph → reclassify.
- **Stage 3 — Route to filing (the fork).** No internal grievance yet → generate grievance letter, start 30-day timer, re-engage user. Grievance done & failed → generate ombudsman complaint.
- **Stage 4 — Draft + evidence pack + gate.** Generate filing from fired-lever templates; assemble required-document checklist; run evidence-sufficiency check; run validator + pre-delivery eval gate. Ship only on pass.

**Deadline engine** runs across all stages: 15-day insurer response, 30-day fork wait, 1-year ombudsman cliff → notifications + re-engagement. This is a core surface, not a nicety.

---

## 5. Denial-ground taxonomy

The classifier must recognize **all** grounds from day one (a ground can't be routed until recognized). Deep slot-schemas are built in **volume order**; the rest ship as *stubs* (classify + generic question set + generic filing) so nothing falls through.

Full taxonomy (health): PED / non-disclosure · waiting-period (initial / PED / specific-disease) · room-rent proportionate deduction · "not medically necessary" · specific exclusion invoked · sub-limit cap · late intimation · documentation deficiency · policy lapse / non-payment · reasonable-&-customary deduction · day-care / <24hr dispute · misrepresentation / fraud allegation.

**Build order (deep schemas):** 1) PED / non-disclosure, 2) waiting-period, 3) room-rent deduction, 4) medical-necessity. These cover the bulk of volume. All others: stubs first.

Classifier accuracy is the early priority — while most grounds are stubs, correct *ground detection* matters more than any single deep script.

---

## 6. Reference ground: PED / non-disclosure (fully specified)

This is the reference implementation. Every other ground replicates this shape.

### 6.1 Legal levers (health)

- **L1 — Moratorium bar (bright line).** After **60 months continuous coverage**, no health claim is contestable on non-disclosure/misrepresentation grounds except **proven fraud** and permanent exclusions. Reduced from 8y to 5y effective **1 April 2024**; source: **IRDAI Master Circular on Health Insurance Business, ref IRDAI/HLT/CIR/MISC/77/05/2024, dated 29 May 2024**. Strongest possible position.
- **L2 — Not actually pre-existing (workhorse).** Cited condition first diagnosed *after* policy inception → cannot be a PED → non-disclosure factually impossible.
- **L3 — No nexus.** Claimed treatment unrelated to cited condition → repudiating this claim over that condition is unsustainable. (See §7.)
- **L4 — Not material / not asked.** Material facts = those *sought in the proposal form* (IRDAI definition). Not asked, or trivial/borderline → no duty / fails materiality.
- **L5 — Burden & awareness.** Insurer must prove deliberate suppression *and* insured's knowledge at proposal time. Undiagnosed/unknown condition ≠ knowing non-disclosure. Burden is on the insurer.
- **L6 — Agent-filled form.** Agent filled the proposal and omitted disclosed information → non-disclosure defense weakens.
- **L7 — PED waiting served.** PED waiting now capped at **36 months**. If served, even a genuine PED is payable regardless of disclosure.

### 6.2 Slot schema

**Parsed slots** (extracted; never asked): `line_of_business` · `insurer_name` · `claim_amount` · `denial_date` · `denial_ground_text` · `cited_condition` · `policy_inception_date` · `continuous_coverage_start` · `ped_waiting_months` · `claimed_condition` · `sum_insured` + `enhancement_dates`.

**Interview slots** (leashed LLM collects): `first_diagnosis_date` (feeds L2 — highest-value single fact) · `aware_at_proposal` (L5) · `proposal_filled_by` ∈ {self, agent, other} (L6) · `was_condition_asked` (L4) · `disclosed_verbally` (L6) · `continuity_breaks` (L1 — a break resets the moratorium clock).

Every slot: typed, with plausibility range where applicable. Parsed slots carry source-span anchors; interview slots are user-confirmed.

### 6.3 Decision logic (deterministic predicates)

```
moratorium_met        = (denial_date − continuous_coverage_start ≥ 60 months)
                        AND no continuity_breaks AND fraud not proven
diagnosis_post_incept = first_diagnosis_date > policy_inception_date
ped_waiting_served    = coverage_duration ≥ ped_waiting_months
nexus_absent          = no typed path (cited_condition ↔ claimed_condition) in nexus graph
not_asked             = was_condition_asked == false
agent_defense         = proposal_filled_by != self AND disclosed_verbally == true
```

**Verdict:**
- **STRONG** if ANY of `moratorium_met`, `diagnosis_post_incept`, `ped_waiting_served`, `nexus_absent` (each ≈ dispositive alone).
- **MODERATE** if `not_asked`, `agent_defense`, or not-aware (strong support; best combined).
- **LIKELY-VALID** otherwise → decline to draft; explain honestly.

### 6.4 Assertion templates (clause + regulation + fact triplets)

Each fired lever emits a fixed template with slots injected. Examples:

- `moratorium_met` → *"Continuous coverage has subsisted since {continuous_coverage_start}; as on {denial_date} this exceeds the 60-month moratorium. Per IRDAI Master Circular IRDAI/HLT/CIR/MISC/77/05/2024, a claim may not be contested on non-disclosure grounds post-moratorium absent proof of fraud, which has neither been alleged nor established. The repudiation is therefore unsustainable."*
- `diagnosis_post_incept` → *"The cited condition {cited_condition} was first diagnosed on {first_diagnosis_date}, subsequent to inception on {policy_inception_date}. A condition first diagnosed after inception cannot constitute a pre-existing disease."*
- `nexus_absent` → *"The claim pertains to {claimed_condition}, which bears no pathological nexus to {cited_condition}. Repudiation of an unrelated claim is unsustainable."*
- `not_asked` → *"Material facts are those sought in the proposal form. The form did not seek disclosure regarding {cited_condition}; accordingly no duty of disclosure arose."*

### 6.5 Validator rules (per case, runtime)

- **V1** — every legal assertion maps to a lever whose predicate is TRUE. No fired lever → no sentence.
- **V2** — every date/condition/amount token resolves to a filled slot; zero free-floating facts.
- **V3** — every regulation string comes from the versioned citation store (fixed constants), never LLM-generated.
- **V4** — the draft may not assert a lever stronger than the verdict supports.
- **V5** — no STRONG/MODERATE lever → no wrongful-repudiation letter generated.

---

## 7. Nexus subsystem — medical-relatedness graph

`nexus_absent` is not a table lookup; relatedness is transitive (diabetes → nephropathy → renal failure → dialysis). Model it as a **graph**.

- **Nodes:** conditions/procedures resolved to **ICD-10** codes (India's official standard).
- **Edges:** clinically-typed — *direct complication*, *shared etiology*, *recognized comorbidity*, *risk factor* — each carrying a source.
- **Query:** typed path between `cited_condition` and `claimed_condition` within N hops? Path → related (lever doesn't fire). No path → unrelated (lever fires). Unresolvable/unknown → **uncertain → human**, and the human ruling adds a curated edge.
- **Pipeline:** (1) LLM resolves messy input → ICD code + confidence (never judges relatedness); (2) deterministic graph query decides nexus; (3) graph grows from authoritative seeds (ICD comorbidity structure, Charlson/Elixhauser indices, standard complication maps) enriched with **actual ombudsman rulings** on relatedness — the compounding, precedent-backed asset.

LLM role is bounded to ICD normalization + *proposing* candidate edges for human curation. The graph decides; the LLM never does. Output is auditable — show the pathological path or its absence.

---

## 8. Parser subsystem — deterministic, tiered, anchored

**Principle:** extract *specific typed fields at known locations into a schema*, not "what does this policy say?". Every field has a type, plausibility range, and expected location. Off-type/out-of-range → fail, don't propagate.

**Tiers (deterministic-first):**
1. **Digital-native PDFs** (most policy schedules, many letters): detect text layer → **pdfplumber / PyMuPDF**, locate clause/table structurally. No model. Exact by construction. Always try first.
2. **Scanned PDFs:** OCR — **AWS Textract** (forms/tables) primary on the AWS stack; **Surya** (open-source layout+OCR) and **PaddleOCR** (broad language) as alternatives; Google Document AI / Azure Document Intelligence as fallback if Indian layouts underperform.
3. **Handwritten** (discharge summaries, older forms): vision-LLM transcription *into schema* — extraction + confidence + source span only, never interpretation. Low-confidence → human.
4. **Policy-wording clause extraction** (PED-waiting, moratorium, exclusions): schema-driven by clause type + layout patterns → typed fields. **Not** freeform RAG.

**Guarantees:**
- Every extracted slot: `(value, confidence, document, page, span)`. Below threshold → human verification before entering the graph. Missing/uncertain → "unknown," never a guess.
- **Cross-document reconciliation:** facts appearing in multiple places (inception date, sum insured) must agree; mismatch → flag for review.
- **Prefer structured sources over OCR** where available (DigiLocker, digitally-issued PDFs, e-insurance accounts). Architect so a structured pull always beats parsing a scan; OCR burden shrinks as digitization spreads.

---

## 9. Rule engine & versioned citation store

- **Rule engine:** per ground, evaluates the predicate set (§6.3) over filled slots → fired levers → verdict. Pure, deterministic, unit-testable in isolation.
- **Citation store:** every entry scoped `(rule_id, text, effective_from, effective_to, source, last_verified)`. Engine selects the version valid at the case's **relevant date** (e.g., a 2023 denial uses the 8-year moratorium; post-1-April-2024 uses 60 months). Cases straddling the boundary auto-select correctly.
- Citations are **constants**, injected into templates — never generated.

---

## 10. Narrator — the leashed LLM

Two jobs only: **render** the question for the graph-selected slot; **interpret** the freeform answer into that slot's schema.

- Adaptivity: depth not breadth. May rephrase; may ask one bounded clarifier on the *same* slot. May not introduce topics, questions, or advice.
- Pre-send guard: every generated question references only the active slot and carries no advice/new-ask; fail → regenerate or fall back to scripted default phrasing.
- Answer parsing: maps to a slot or triggers a re-ask (cap ~2, then "unknown" / human).
- Turn log: `(active_ground, target_slot, generated_question, raw_answer, parsed_value)` — this *is* the audit trail.

---

## 11. Validation & evaluation (two distinct layers)

**Layer A — Pre-delivery gate (per case, at Stage 4, before user sees anything):**
- Citation verification — every regulation string re-matched exact against the live store.
- Arithmetic recompute — months-elapsed for moratorium/waiting recomputed independently; must equal what the letter asserts (catches off-by-one date bugs).
- Slot-grounding audit — every token re-resolves to a document span or user-confirmed slot.
- Bounded adversarial critic — separate LLM pass instructed only to *flag* unsupported claims (flags, never rewrites); flags on high-value STRONG cases → human.

**Layer B — Offline eval harness (ongoing):**
- Golden set of real denials with expert labels (ground, levers, verdict, ideal letter).
- Instrument each stage separately: classifier accuracy · per-slot extraction accuracy · lever precision/recall · verdict accuracy · win rate. (Separate instrumentation avoids the multi-variable attribution trap.)
- Every rulepack change is regression-tested against the golden set.
- Real GRO/ombudsman outcomes label cases retrospectively → feed golden set + lever calibration.

---

## 12. Regulatory-freshness agent

Detection + proposal + human ratification. **Never auto-applies.**

- Scheduled crawl of structured sources: IRDAI circulars / master-circular pages, gazette notifications, Council for Insurance Ombudsmen.
- Diff against the known document set; where a change touches a rulepack rule, emit a **structured change proposal** (old citation → new, effective date, affected levers).
- Human legal reviewer ratifies → versioned rulepack update.
- Agent also maintains `last_verified` timestamps and flags staleness. Its job is keeping verification current, not mutating law.

---

## 13. Cross-cutting subsystems

**13.1 Data model & DPDP compliance (design from day one).** Processing health records, identity, policy data of vulnerable users = sensitive personal data under India's DPDP Act. Consent capture, data minimization, encryption at rest, retention limits, erasure rights are preconditions, not later hardening. Bake into the case-store schema now.

**13.2 Deadline tracking & re-engagement.** 15-day insurer response · 30-day grievance fork · 1-year ombudsman cliff. Deadline-driven notifications; missing a window is a silent case-killer and a primary drop-off point.

**13.3 Evidence-sufficiency detection (before drafting).** A lever needs its proof. If `diagnosis_post_incept` is the play, a dated diagnostic report is required. Detect the gap and tell the user exactly what to obtain before filing. Filing STRONG without the proof document is worse than not filing.

**13.4 Precedent store.** Curated ombudsman awards keyed by ground + lever. Persuasive (not strictly binding); lets letters cite "in award {ref}, the Ombudsman held…"; feeds the nexus graph; calibrates lever strength. **This is the one place a vector store is legitimate** — semantic recall over award text to surface similar fact patterns — feeding human curation, never the user's filing path directly.

**13.5 Fraud / abuse guard.** The STRONG/VALID gate handles honest weak cases; someone will submit a doctored diagnosis date to manufacture `diagnosis_post_incept`. Attestation + anomaly checks. Do not generate filings on fraudulent premises (liability + win-rate poison).

**13.6 Human-escalation queue.** All "route to human" points (uncertain nexus, low-confidence extraction, critic flags, high-value STRONG) → one queue, prioritized by claim value + uncertainty. Its volume *is* the unit economics of the flat-fee wedge — instrument human-touch rate obsessively.

**13.7 Vernacular / multi-language.** Users and documents span Hindi + regional languages — affects both the conversational shell and OCR. Design in, don't bolt on.

**13.8 User-facing explainability.** Show the user *why* they'll likely win — the audit trail is simultaneously the trust feature and the conversion driver, not just a regulatory artifact.

---

## 14. Tech stack

- **Backend:** Python, FastAPI. **Datastores:** PostgreSQL (case store, typed slots, citation store, precedent metadata), Redis (queues, deadline timers). **Infra:** Docker, AWS (EC2/S3).
- **Parsing:** pdfplumber / PyMuPDF (digital), AWS Textract / Surya / PaddleOCR (scanned), vision-LLM (handwritten).
- **Graph:** nexus graph — start in Postgres (adjacency) or a graph DB if traversal complexity grows.
- **LLM:** provider-abstracted (narrator + bounded ICD normalization + adversarial critic). Keep the LLM interface thin and swappable.
- **Vector store:** precedent library only (§13.4).

---

## 15. Build sequence (milestones)

1. **M0 — Skeleton & data model.** Case store schema (DPDP-aware), typed-slot model with source anchors, versioned citation store. Stub taxonomy (classify + generic).
2. **M1 — PED ground, end-to-end, deterministic core.** Rule engine + levers L1–L7, decision logic, assertion templates, validator V1–V5. No parsing/LLM yet — feed hand-entered slots. Prove the graph produces a correct letter.
3. **M2 — Parser tier 1 + 2.** Digital-native + Textract extraction with anchoring, confidence gating, cross-doc reconciliation. Feed real documents into M1.
4. **M3 — Narrator + Stage 2 interview.** Leashed LLM slot-filling with guards + turn log. Full Stage 0→4 flow for PED.
5. **M4 — Nexus graph v1.** ICD resolution + seed graph + query; uncertain→human.
6. **M5 — Eval layers.** Pre-delivery gate (citation/arithmetic/grounding/critic) + offline harness with golden set.
7. **M6 — Lifecycle hardening.** Deadline engine, evidence-sufficiency, escalation queue, fraud guard.
8. **M7 — Regulatory-freshness agent + precedent store.**
9. **M8 — Grounds 2–4 deep** (waiting-period, room-rent, medical-necessity) by replicating the PED pattern.

Ship M1–M3 as the first usable slice (PED, self-serve, one ground, real letter). Everything after hardens and broadens.

---

## 16. Explicit non-goals

- No RAG/vector store touching user documents or the filing path.
- No LLM deciding legal outcomes, choosing questions, or generating citations.
- No autonomous rulepack/citation edits.
- No contingency-fee logic in the wedge build (flat-fee/transparent only; success-fee is a later, separate module).
- No multi-line dispatch build yet beyond the Stage-0 hook (health only; motor/life are later packs on this same kernel).
