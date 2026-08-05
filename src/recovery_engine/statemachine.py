"""Case lifecycle state machine, Stages 0-4 (ARCHITECTURE.md Section 4.2).

A case is a long-lived, deadline-driven entity. This module walks it through:

  Stage 0  Intake & eligibility gate   (1-year window, ₹50L jurisdiction, forum)
  Stage 1  Contestability diagnosis     (engine; LIKELY-VALID -> honest decline)
  Stage 2  Targeted interview           (graph-ordered slots; leashed narrator)
  Stage 3  Route to filing (the fork)   (grievance first; then ombudsman)
  Stage 4  Draft + evidence pack + gate (validator + evidence-sufficiency)

The graph owns every structural decision — which slots to ask, when enough
levers fire to stop, whether to ship. The LLM only renders/parses inside Stage 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum, IntEnum
from typing import Callable, Optional

from .citations import CitationStore, default_store
from .engine import Findings, diagnose
from .grounds import ped
from .interview import PED_INTERVIEW
from .letter import Decline, Letter, draft
from .llm import from_env
from .narrator import Narrator, TurnLogEntry
from .parser.base import DocType
from .slots import Case, SlotSource
from .validator import Violation, validate
from .verdict import Verdict

JURISDICTION_LIMIT = 5_000_000  # ₹50 lakh (Section 3)
OMBUDSMAN_BINDING_LIMIT = 3_000_000  # ₹30 lakh (informational)
INSURER_RESPONSE_DAYS = 15
FORK_WAIT_DAYS = 30
MAX_REASKS = 2

# Answer source for Stage 2: (slot, question_text) -> raw answer or None.
AnswerProvider = Callable[[str, str], Optional[str]]


class Stage(IntEnum):
    INTAKE = 0
    DIAGNOSIS = 1
    INTERVIEW = 2
    ROUTE = 3
    DRAFT = 4


class FilingTarget(str, Enum):
    GRIEVANCE = "grievance"
    OMBUDSMAN = "ombudsman"


@dataclass
class Eligibility:
    status: str            # 'eligible' | 'not_yet' | 'ineligible'
    reasons: list[str] = field(default_factory=list)
    forum: Optional[str] = None


@dataclass
class Deadlines:
    as_of: date
    ombudsman_cliff: Optional[date] = None
    insurer_response_due: Optional[date] = None
    fork_wait_until: Optional[date] = None

    def days_to_cliff(self) -> Optional[int]:
        if self.ombudsman_cliff is None:
            return None
        return (self.ombudsman_cliff - self.as_of).days


@dataclass
class EvidenceGap:
    lever: str
    required_doc: DocType
    message: str


@dataclass
class SessionResult:
    stage_reached: Stage
    eligibility: Eligibility
    deadlines: Deadlines
    findings: Optional[Findings] = None
    filing: Optional[object] = None          # Letter | Decline
    filing_target: Optional[FilingTarget] = None
    violations: list[Violation] = field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = field(default_factory=list)
    turn_log: list[TurnLogEntry] = field(default_factory=list)

    @property
    def shippable(self) -> bool:
        return (
            isinstance(self.filing, Letter)
            and not self.violations
            and not self.evidence_gaps
        )


def _add_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29 Feb -> 28 Feb
        return d.replace(year=d.year + 1, day=28)


# The proof document a fired lever needs (Section 13.3).
_LEVER_EVIDENCE: dict[str, DocType] = {
    "diagnosis_post_incept": DocType.DISCHARGE_SUMMARY,
    "moratorium_met": DocType.POLICY_SCHEDULE,
    "ped_waiting_served": DocType.POLICY_SCHEDULE,
    "nexus_absent": DocType.DISCHARGE_SUMMARY,
    "not_asked": DocType.PROPOSAL_FORM,
    "agent_defense": DocType.PROPOSAL_FORM,
    "not_aware": DocType.DISCHARGE_SUMMARY,
}


def intake_gate(case: Case, as_of: date, in_court_or_forum: bool = False) -> Eligibility:
    """Stage 0: hard eligibility gates (Section 4.2)."""
    reasons: list[str] = []

    lob = case.value("line_of_business")
    if lob is None:
        return Eligibility("not_yet", ["line of business unknown"], None)
    if lob != "health":
        return Eligibility("ineligible", [f"line of business {lob!r} not yet supported"], lob)

    denial = case.value("denial_date")
    if denial is None:
        return Eligibility("not_yet", ["denial date unknown — cannot assess time bar"], lob)
    cliff = _add_one_year(denial)
    if as_of > cliff:
        reasons.append(f"denial dated {denial.isoformat()} is beyond the 1-year window")

    amount = case.value("claim_amount")
    if amount is not None and amount > JURISDICTION_LIMIT:
        reasons.append(f"claim {amount:.0f} exceeds ₹50L ombudsman jurisdiction")

    if in_court_or_forum:
        reasons.append("matter already before a court/consumer forum (disqualifies)")

    if reasons:
        return Eligibility("ineligible", reasons, lob)
    return Eligibility("eligible", ["within 1-year window; within jurisdiction; health"], lob)


def _deadlines(case: Case, as_of: date, final_reply_date: Optional[date] = None) -> Deadlines:
    denial = case.value("denial_date")
    cliff_anchor = final_reply_date or denial
    return Deadlines(
        as_of=as_of,
        ombudsman_cliff=_add_one_year(cliff_anchor) if cliff_anchor else None,
    )


def _run_interview(
    case: Case,
    narrator: Narrator,
    answers: AnswerProvider,
    citations: CitationStore,
) -> None:
    """Stage 2: ask the graph-ordered slots; stop once a STRONG lever fires."""
    for q in PED_INTERVIEW:
        if case.is_filled(q.slot):
            continue  # already parsed/known — never re-ask
        question = narrator.render_question(q, case)

        raw = answers(q.slot, question)
        parsed = None
        attempts = 0
        while raw is not None and attempts <= MAX_REASKS:
            outcome = narrator.parse_answer(q, raw, case)
            if outcome.ok:
                parsed = outcome.value
                break
            attempts += 1
            raw = answers(q.slot, question)  # bounded clarifier on the same slot

        narrator.log(q.slot, question, raw, parsed)
        if parsed is not None:
            case.set(q.slot, parsed, source=SlotSource.INTERVIEW)

        # Breadth is the graph's call: a dispositive lever ends the interview.
        if diagnose(case, citations).verdict == Verdict.STRONG:
            break


def _evidence_gaps(case: Case, findings: Findings, provided: set[DocType]) -> list[EvidenceGap]:
    """Stage 4 (Section 13.3): the top fired lever must have its proof document."""
    gaps: list[EvidenceGap] = []
    for lever_id in findings.fired_levers[:1]:  # gate the lead (strongest) lever
        predicate = ped.LEVERS[lever_id].predicate
        required = _LEVER_EVIDENCE.get(predicate)
        if required is not None and required not in provided:
            gaps.append(
                EvidenceGap(
                    lever_id,
                    required,
                    f"lever {lever_id} needs a {required.value} as proof before filing",
                )
            )
    return gaps


def run_session(
    case: Case,
    *,
    answers: Optional[AnswerProvider] = None,
    provided_docs: Optional[set[DocType]] = None,
    as_of: Optional[date] = None,
    grievance_failed: bool = False,
    in_court_or_forum: bool = False,
    final_reply_date: Optional[date] = None,
    citations: Optional[CitationStore] = None,
    narrator: Optional[Narrator] = None,
) -> SessionResult:
    """Walk a case through Stages 0-4. Deterministic given the inputs."""
    citations = citations or default_store()
    as_of = as_of or date.today()
    provided_docs = provided_docs or set()
    answers = answers or (lambda slot, q: None)
    # from_env() returns None when unconfigured, so the default narrator stays
    # fully deterministic unless LLM_PROVIDER/*_API_KEY are set (Section 14).
    narrator = narrator or Narrator("PED", llm=from_env())

    deadlines = _deadlines(case, as_of, final_reply_date)

    # Stage 0
    elig = intake_gate(case, as_of, in_court_or_forum)
    if elig.status != "eligible":
        return SessionResult(Stage.INTAKE, elig, deadlines)

    # Stage 1
    findings = diagnose(case, citations)
    if findings.verdict == Verdict.LIKELY_VALID:
        # Stage 2 may still rescue it — interview, then re-diagnose.
        _run_interview(case, narrator, answers, citations)
        findings = diagnose(case, citations)
    else:
        _run_interview(case, narrator, answers, citations)
        findings = diagnose(case, citations)

    if findings.verdict == Verdict.LIKELY_VALID:
        decline = draft(case, findings, citations)
        return SessionResult(
            Stage.DIAGNOSIS, elig, deadlines, findings=findings, filing=decline,
            turn_log=narrator.turns,
        )

    # Stage 3 — the fork
    target = FilingTarget.OMBUDSMAN if grievance_failed else FilingTarget.GRIEVANCE
    if target == FilingTarget.GRIEVANCE:
        deadlines.insurer_response_due = as_of + timedelta(days=INSURER_RESPONSE_DAYS)
        deadlines.fork_wait_until = as_of + timedelta(days=FORK_WAIT_DAYS)

    # Stage 4 — draft + evidence pack + gate
    filing = draft(case, findings, citations)
    violations = validate(case, findings, filing, citations)
    gaps = _evidence_gaps(case, findings, provided_docs)

    return SessionResult(
        Stage.DRAFT, elig, deadlines,
        findings=findings, filing=filing, filing_target=target,
        violations=violations, evidence_gaps=gaps, turn_log=narrator.turns,
    )
