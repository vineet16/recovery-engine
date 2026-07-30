"""Per-case runtime validator V1-V5 (ARCHITECTURE.md Section 6.5).

The validator guarantees nothing is asserted that the slots and citation store
don't support. It runs after assembly and before delivery; a non-empty result
means the filing must not ship.

- V1 every legal assertion maps to a lever whose predicate is TRUE
- V2 every injected token resolves to a filled slot (no free-floating facts)
- V3 every regulation string is an exact constant from the versioned store
- V4 the draft asserts no lever stronger than the verdict supports
- V5 no STRONG/MODERATE lever -> no wrongful-repudiation letter
"""

from __future__ import annotations

from dataclasses import dataclass

from .citations import CitationStore, default_store
from .engine import Findings
from .grounds import ped
from .letter import Decline, Letter
from .slots import Case
from .verdict import Verdict


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.message}"


def validate(
    case: Case,
    findings: Findings,
    filing: Letter | Decline,
    citations: CitationStore | None = None,
) -> list[Violation]:
    citations = citations or default_store()
    violations: list[Violation] = []

    # V5 — gate on verdict. A LIKELY-VALID verdict must yield a Decline, and a
    # draftable verdict must not be silently downgraded to a Decline.
    if findings.verdict == Verdict.LIKELY_VALID:
        if isinstance(filing, Letter):
            violations.append(
                Violation("V5", "LIKELY-VALID verdict produced a wrongful-repudiation letter")
            )
        return violations  # nothing further to check on a decline
    if not findings.fired_levers:
        violations.append(Violation("V5", "no STRONG/MODERATE lever fired but a letter exists"))
    if isinstance(filing, Decline):
        # Draftable verdict but no letter — treat as a gate failure to surface.
        violations.append(
            Violation("V5", f"{findings.verdict.label} verdict but no letter was drafted")
        )
        return violations

    for a in filing.assertions:
        lever = ped.LEVERS.get(a.lever_id)

        # V1 — asserted lever must exist, be fired, and its predicate TRUE.
        if lever is None:
            violations.append(Violation("V1", f"assertion cites unknown lever {a.lever_id!r}"))
            continue
        if a.lever_id not in findings.fired_levers:
            violations.append(
                Violation("V1", f"lever {a.lever_id} asserted but not among fired levers")
            )
        elif not findings.predicate_true(lever.predicate):
            violations.append(
                Violation("V1", f"lever {a.lever_id} asserted but predicate {lever.predicate} is not TRUE")
            )

        # V2 — every injected token resolves to a filled slot.
        for tok in a.tokens:
            if not case.is_filled(tok):
                violations.append(
                    Violation("V2", f"lever {a.lever_id} injects unfilled/unknown slot {tok!r}")
                )

        # V3 — every regulation string is an exact constant from the store, and
        # its verbatim source appears in the rendered text.
        for rule_id in a.citations:
            try:
                cit = citations.resolve(rule_id, findings.relevant_date)
            except KeyError:
                violations.append(
                    Violation("V3", f"lever {a.lever_id} cites {rule_id!r} not in the store on the relevant date")
                )
                continue
            if not citations.has_exact_source(cit.source):
                violations.append(
                    Violation("V3", f"citation {rule_id} source is not a known constant")
                )
            if cit.source not in a.text:
                violations.append(
                    Violation("V3", f"lever {a.lever_id} does not embed the exact source string for {rule_id}")
                )

        # V4 — no lever stronger than the verdict supports.
        if lever is not None and not findings.verdict.allows(lever.strength):
            violations.append(
                Violation(
                    "V4",
                    f"lever {a.lever_id} ({lever.strength.name}) exceeds "
                    f"{findings.verdict.label} verdict",
                )
            )

    return violations
