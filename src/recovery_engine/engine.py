"""Rule engine (ARCHITECTURE.md Sections 4.1, 6.3, 9).

Pure and deterministic: evaluate the ground's predicates over filled slots ->
fired levers -> verdict. This is the Findings Store: verdict + fired levers +
the citations they rely on. The LLM never runs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .citations import CitationStore, default_store
from .grounds import ped
from .slots import Case
from .verdict import Verdict


@dataclass
class Findings:
    case_id: str
    verdict: Verdict
    fired_levers: list[str]                         # e.g. ["L1", "L5"]
    evaluation: ped.Evaluation
    relevant_date: date

    @property
    def support(self) -> dict[str, Any]:
        return self.evaluation.support

    def predicate_true(self, key: str) -> bool:
        r = self.evaluation.predicates.get(key)
        return bool(r and r.fired)


def _relevant_date(case: Case) -> date:
    """The case's relevant date drives citation version selection (Section 9).

    For a repudiation dispute this is the denial date — a 2023 denial is judged
    under the law in force in 2023.
    """
    d = case.value("denial_date")
    if d is None:
        raise ValueError("cannot diagnose without denial_date (relevant date)")
    return d


def diagnose(case: Case, citations: CitationStore | None = None) -> Findings:
    """Stage 1 contestability diagnosis for the PED ground (Section 4.2)."""
    citations = citations or default_store()
    relevant_date = _relevant_date(case)
    ev = ped.evaluate(case, citations, relevant_date)

    fired: list[str] = []
    # Preserve lever id order L1..L7 for stable, strongest-first assembly.
    for lever_id in ("L1", "L2", "L3", "L7", "L4", "L6", "L5"):
        lever = ped.LEVERS[lever_id]
        if ev.predicates[lever.predicate].fired:
            fired.append(lever_id)

    if any(ev.predicates[k].fired for k in ped.STRONG_PREDICATES):
        verdict = Verdict.STRONG
    elif any(ev.predicates[k].fired for k in ped.MODERATE_PREDICATES):
        verdict = Verdict.MODERATE
    else:
        verdict = Verdict.LIKELY_VALID

    return Findings(
        case_id=case.case_id,
        verdict=verdict,
        fired_levers=fired,
        evaluation=ev,
        relevant_date=relevant_date,
    )
