"""Typed, source-anchored slot model (ARCHITECTURE.md Section 4.1 "Schema", Section 8).

Every fact that enters the graph is a `Slot`: a typed value welded to its
provenance `(value, confidence, document, page, span)`. Nothing free-floating
ever reaches a filing. For M1 the parser does not exist yet, so slots are
hand-entered (source = HAND_ENTERED); M2 replaces that with anchored extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Callable, Optional


class SlotSource(str, Enum):
    PARSED = "parsed"          # anchored extraction from a document (M2+)
    INTERVIEW = "interview"    # user-confirmed answer from the leashed LLM (M3+)
    HAND_ENTERED = "hand"      # M1 fixtures / manual entry


class ProposalFilledBy(str, Enum):
    SELF = "self"
    AGENT = "agent"
    OTHER = "other"


@dataclass(frozen=True)
class Anchor:
    """Where a parsed value came from. Required for PARSED slots."""

    document: str
    page: Optional[int] = None
    span: Optional[tuple[int, int]] = None


@dataclass
class Slot:
    name: str
    value: Any
    source: SlotSource
    confidence: float = 1.0
    anchor: Optional[Anchor] = None

    @property
    def is_known(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class SlotSpec:
    """Schema for one slot: type + plausibility gate (Section 8).

    Off-type or out-of-range values fail loudly instead of propagating.
    """

    name: str
    py_type: type
    interview: bool = False  # collected in Stage 2 rather than parsed
    validate: Optional[Callable[[Any], bool]] = None

    def check(self, value: Any) -> None:
        if value is None:
            return  # "unknown" is always allowed; never guessed
        if not isinstance(value, self.py_type):
            raise TypeError(
                f"slot {self.name!r} expected {self.py_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if self.validate and not self.validate(value):
            raise ValueError(f"slot {self.name!r} out of plausibility range: {value!r}")


def _positive(x: Any) -> bool:
    return x >= 0


def _plausible_months(x: Any) -> bool:
    return 0 <= x <= 600  # up to 50 years


# --- PED / non-disclosure ground slot schema (Section 6.2) -------------------
# Parsed slots are extracted and never asked; interview slots are user-confirmed.

SLOT_SPECS: dict[str, SlotSpec] = {
    # Parsed slots
    "line_of_business": SlotSpec("line_of_business", str),
    "insurer_name": SlotSpec("insurer_name", str),
    "claim_amount": SlotSpec("claim_amount", (int, float), validate=_positive),
    "denial_date": SlotSpec("denial_date", date),
    "denial_ground_text": SlotSpec("denial_ground_text", str),
    "cited_condition": SlotSpec("cited_condition", str),
    "policy_inception_date": SlotSpec("policy_inception_date", date),
    "continuous_coverage_start": SlotSpec("continuous_coverage_start", date),
    "ped_waiting_months": SlotSpec("ped_waiting_months", int, validate=_plausible_months),
    "claimed_condition": SlotSpec("claimed_condition", str),
    "sum_insured": SlotSpec("sum_insured", (int, float), validate=_positive),
    # Interview slots (leashed LLM collects; M3). Hand-entered in M1.
    "first_diagnosis_date": SlotSpec("first_diagnosis_date", date, interview=True),
    "aware_at_proposal": SlotSpec("aware_at_proposal", bool, interview=True),
    "proposal_filled_by": SlotSpec("proposal_filled_by", ProposalFilledBy, interview=True),
    "was_condition_asked": SlotSpec("was_condition_asked", bool, interview=True),
    "disclosed_verbally": SlotSpec("disclosed_verbally", bool, interview=True),
    "continuity_breaks": SlotSpec("continuity_breaks", bool, interview=True),
    "fraud_proven": SlotSpec("fraud_proven", bool, interview=True),
    # Nexus (Section 7). The graph is M5; until then this is an explicit,
    # human-supplied ruling rather than a computed result.
    "nexus_absent": SlotSpec("nexus_absent", bool, interview=True),
}


@dataclass
class Case:
    """A long-lived case (Section 4.2). M1 only holds the typed slot bag."""

    case_id: str
    slots: dict[str, Slot] = field(default_factory=dict)

    def set(
        self,
        name: str,
        value: Any,
        *,
        source: SlotSource = SlotSource.HAND_ENTERED,
        confidence: float = 1.0,
        anchor: Optional[Anchor] = None,
    ) -> "Case":
        spec = SLOT_SPECS.get(name)
        if spec is None:
            raise KeyError(f"unknown slot {name!r} (not in PED schema)")
        spec.check(value)
        if source is SlotSource.PARSED and value is not None and anchor is None:
            raise ValueError(f"parsed slot {name!r} must carry a source anchor")
        self.slots[name] = Slot(name, value, source, confidence, anchor)
        return self

    def get(self, name: str) -> Optional[Slot]:
        return self.slots.get(name)

    def value(self, name: str, default: Any = None) -> Any:
        slot = self.slots.get(name)
        if slot is None or not slot.is_known:
            return default
        return slot.value

    def is_filled(self, name: str) -> bool:
        slot = self.slots.get(name)
        return slot is not None and slot.is_known
