"""Recovery Engine — Indian health insurance claim-denial recovery.

M1: PED / non-disclosure ground, end-to-end deterministic core. A rule engine
decides the law; templates narrate; a validator guarantees grounding. See
ARCHITECTURE.md for the full specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .citations import CitationStore, default_store
from .engine import Findings, diagnose
from .letter import Decline, Letter, draft
from .narrator import Narrator
from .slots import Case, ProposalFilledBy, SlotSource
from .statemachine import (
    Eligibility,
    FilingTarget,
    SessionResult,
    Stage,
    intake_gate,
    run_session,
)
from .validator import Violation, validate
from .verdict import Verdict

__all__ = [
    "Case",
    "ProposalFilledBy",
    "SlotSource",
    "CitationStore",
    "default_store",
    "Findings",
    "diagnose",
    "Letter",
    "Decline",
    "draft",
    "Verdict",
    "Violation",
    "validate",
    "Result",
    "run",
    # M3 — narrator + lifecycle
    "Narrator",
    "run_session",
    "SessionResult",
    "Stage",
    "Eligibility",
    "FilingTarget",
    "intake_gate",
]


@dataclass
class Result:
    findings: Findings
    filing: Union[Letter, Decline]
    violations: list[Violation]

    @property
    def shippable(self) -> bool:
        return not self.violations


def run(case: Case, citations: CitationStore | None = None) -> Result:
    """Diagnose -> draft -> validate. The happy-path pipeline (Stages 1-4).

    A filing ships only if `violations` is empty (the pre-delivery gate).
    """
    citations = citations or default_store()
    findings = diagnose(case, citations)
    filing = draft(case, findings, citations)
    violations = validate(case, findings, filing, citations)
    return Result(findings=findings, filing=filing, violations=violations)
