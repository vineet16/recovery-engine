"""Assertion templates + filing assembly (ARCHITECTURE.md Sections 6.4, 4.2).

Each fired lever emits a fixed clause+regulation+fact triplet with slots
injected. In M1 this deterministic template renderer stands in for the narrator
(the leashed LLM is M3); the structure — which sentences exist, in what order,
citing what — is owned entirely by the graph, never the model.

A LIKELY-VALID verdict yields a Decline, not a letter (principle Section 2.6 /
validator V5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .citations import CitationStore, default_store
from .engine import Findings
from .grounds import ped
from .slots import Case
from .verdict import Verdict


def _fmt_date(d: date) -> str:
    return d.strftime("%-d %B %Y")


def _fmt_amount(x: float) -> str:
    return f"₹{x:,.0f}"


@dataclass
class Assertion:
    """One legal sentence, welded to its lever, slots, and citations.

    `tokens` are the slot names whose values were injected; `citations` are the
    rule_ids relied on. The validator checks both (V1-V3).
    """

    lever_id: str
    text: str
    tokens: list[str]
    citations: list[str] = field(default_factory=list)


# --- Per-lever templates ----------------------------------------------------
# Each returns the rendered Assertion. Verbatim reg strings come from the store.

def _cite(citations: CitationStore, rule_id: str, relevant_date: date) -> str:
    return citations.resolve(rule_id, relevant_date).source


def _t_moratorium(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    months = f.support["moratorium_months"]
    src = _cite(cs, "MORATORIUM", f.relevant_date)
    text = (
        f"Continuous coverage has subsisted since "
        f"{_fmt_date(case.value('continuous_coverage_start'))}; as on "
        f"{_fmt_date(case.value('denial_date'))} this exceeds the {months}-month "
        f"moratorium. Per {src}, a claim may not be contested on non-disclosure "
        f"grounds post-moratorium absent proof of fraud, which has neither been "
        f"alleged nor established. The repudiation is therefore unsustainable."
    )
    return Assertion("L1", text, ["continuous_coverage_start", "denial_date"], ["MORATORIUM"])


def _t_diagnosis(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    text = (
        f"The cited condition {case.value('cited_condition')} was first diagnosed "
        f"on {_fmt_date(case.value('first_diagnosis_date'))}, subsequent to "
        f"inception on {_fmt_date(case.value('policy_inception_date'))}. A condition "
        f"first diagnosed after inception cannot constitute a pre-existing disease."
    )
    return Assertion(
        "L2", text, ["cited_condition", "first_diagnosis_date", "policy_inception_date"], []
    )


def _t_nexus(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    text = (
        f"The claim pertains to {case.value('claimed_condition')}, which bears no "
        f"pathological nexus to {case.value('cited_condition')}. Repudiation of an "
        f"unrelated claim is unsustainable."
    )
    return Assertion("L3", text, ["claimed_condition", "cited_condition"], [])


def _t_ped_served(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    src = _cite(cs, "PED_WAITING_CAP", f.relevant_date)
    cap = f.support["ped_cap_months"]
    coverage = f.support["coverage_months"]
    text = (
        f"The policy's pre-existing-disease waiting period of "
        f"{case.value('ped_waiting_months')} months (which may not exceed {cap} "
        f"months per {src}) stood served as on {_fmt_date(case.value('denial_date'))}, "
        f"{coverage} months of continuous coverage having elapsed since "
        f"{_fmt_date(case.value('continuous_coverage_start'))}. A claim for a "
        f"served-waiting condition is payable irrespective of disclosure."
    )
    return Assertion(
        "L7", text,
        ["ped_waiting_months", "denial_date", "continuous_coverage_start"],
        ["PED_WAITING_CAP"],
    )


def _t_not_asked(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    src = _cite(cs, "MATERIALITY", f.relevant_date)
    text = (
        f"Material facts are those sought in the proposal form (per {src}). The form "
        f"did not seek disclosure regarding {case.value('cited_condition')}; "
        f"accordingly no duty of disclosure arose."
    )
    return Assertion("L4", text, ["cited_condition"], ["MATERIALITY"])


def _t_agent(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    text = (
        f"The proposal form was completed by the {case.value('proposal_filled_by').value}, "
        f"not the insured, and the material information was disclosed verbally at the "
        f"time of proposal. Where an intermediary fills the proposal and omits "
        f"disclosed information, the non-disclosure defence does not lie against the "
        f"insured."
    )
    return Assertion("L6", text, ["proposal_filled_by"], [])


def _t_not_aware(case: Case, f: Findings, cs: CitationStore) -> Assertion:
    src = _cite(cs, "BURDEN_OF_PROOF", f.relevant_date)
    text = (
        f"The insured was not aware of the cited condition "
        f"{case.value('cited_condition')} at the time of proposal. Per {src}, an "
        f"undiagnosed or unknown condition cannot amount to knowing non-disclosure."
    )
    return Assertion("L5", text, ["cited_condition"], ["BURDEN_OF_PROOF"])


_TEMPLATES: dict[str, Callable[[Case, Findings, CitationStore], Assertion]] = {
    "L1": _t_moratorium,
    "L2": _t_diagnosis,
    "L3": _t_nexus,
    "L7": _t_ped_served,
    "L4": _t_not_asked,
    "L6": _t_agent,
    "L5": _t_not_aware,
}


@dataclass
class Decline:
    """Honest non-draft for a LIKELY-VALID verdict (principle Section 2.6)."""

    case_id: str
    reason_lines: list[str]

    @property
    def is_decline(self) -> bool:
        return True

    def render(self) -> str:
        head = (
            "We are unable to draft a wrongful-repudiation filing for this case.\n"
            "On the facts provided, no strong or moderate legal lever fires, which "
            "means the denial is likely valid. Drafting a filing anyway would burn "
            "your one credible shot before the Grievance Redressal Officer.\n\n"
            "What we checked (PED / non-disclosure ground):"
        )
        return head + "\n" + "\n".join(f"  - {ln}" for ln in self.reason_lines)


@dataclass
class Letter:
    """Grievance-stage filing (Stage 3 fork default, Section 4.2)."""

    case_id: str
    verdict: Verdict
    assertions: list[Assertion]
    case: Case = field(repr=False, default=None)  # type: ignore[assignment]

    @property
    def is_decline(self) -> bool:
        return False

    def render(self) -> str:
        c = self.case
        lines = [
            "To,",
            "The Grievance Redressal Officer,",
            f"{c.value('insurer_name')}",
            "",
            f"Subject: Grievance against repudiation of claim "
            f"({_fmt_amount(c.value('claim_amount'))}) — denial dated "
            f"{_fmt_date(c.value('denial_date'))}",
            "",
            "Dear Sir/Madam,",
            "",
            f"I write regarding the repudiation of my health insurance claim on the "
            f"stated ground of pre-existing disease / non-disclosure. The repudiation "
            f"is legally unsustainable for the following reasons:",
            "",
        ]
        for i, a in enumerate(self.assertions, 1):
            lines.append(f"{i}. {a.text}")
            lines.append("")
        lines += [
            "In the circumstances, I request that the claim be admitted and settled "
            "in full within 15 days of this grievance, failing which I reserve the "
            "right to approach the Insurance Ombudsman.",
            "",
            "Yours faithfully,",
            "[Policyholder]",
        ]
        return "\n".join(lines)


def draft(case: Case, findings: Findings, citations: CitationStore | None = None):
    """Assemble the filing from fired-lever templates (Stage 4, Section 4.2).

    Returns a `Letter` for STRONG/MODERATE verdicts, else a `Decline`. Levers are
    rendered strongest-first in the order the engine fired them.
    """
    citations = citations or default_store()

    if findings.verdict == Verdict.LIKELY_VALID:
        reasons = []
        for lid in ("L1", "L2", "L3", "L7", "L4", "L6", "L5"):
            pr = findings.evaluation.predicates[ped.LEVERS[lid].predicate]
            status = "did not fire" if pr.value is False else "could not be assessed"
            reasons.append(f"{ped.LEVERS[lid].name} ({lid}): {status} — {pr.detail}")
        return Decline(findings.case_id, reasons)

    assertions = [_TEMPLATES[lid](case, findings, citations) for lid in findings.fired_levers]
    return Letter(findings.case_id, findings.verdict, assertions, case=case)
