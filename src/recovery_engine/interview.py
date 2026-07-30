"""Interview plan for the PED ground (ARCHITECTURE.md Sections 6.2, 2 principle).

The graph owns the slot list and its order — highest-value fact first
(first_diagnosis_date feeds L2). The narrator only renders and parses; it never
adds a topic. Depth adaptivity (rephrase, one clarifier) is allowed; breadth is
not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .slots import ProposalFilledBy


@dataclass(frozen=True)
class SlotQuestion:
    slot: str
    kind: str                       # 'bool' | 'date' | 'enum'
    prompt: str                     # scripted default; references only this slot
    topic_keywords: tuple[str, ...] # pre-send guard: question must be on-topic
    enum_map: Optional[dict[str, Any]] = None
    invert_bool: bool = False       # answer "yes" maps to False (e.g. continuity)


_FILLED_BY = {
    "myself": ProposalFilledBy.SELF,
    "self": ProposalFilledBy.SELF,
    "me": ProposalFilledBy.SELF,
    "i filled": ProposalFilledBy.SELF,
    "on my own": ProposalFilledBy.SELF,
    "agent": ProposalFilledBy.AGENT,
    "broker": ProposalFilledBy.AGENT,
    "advisor": ProposalFilledBy.AGENT,
    "adviser": ProposalFilledBy.AGENT,
    "someone else": ProposalFilledBy.OTHER,
    "family": ProposalFilledBy.OTHER,
    "other": ProposalFilledBy.OTHER,
}


# Ordered highest-value first (Section 6.2). {cited_condition} is injected from a
# parsed slot; the narrator supplies a neutral fallback if it is unknown.
PED_INTERVIEW: list[SlotQuestion] = [
    SlotQuestion(
        "first_diagnosis_date", "date",
        "When was {cited_condition} first diagnosed? Please give the date on the "
        "earliest medical record you have.",
        ("diagnos", "first", "date", "when"),
    ),
    SlotQuestion(
        "was_condition_asked", "bool",
        "Did the proposal form specifically ask whether you had {cited_condition} "
        "or a related condition?",
        ("proposal form", "ask", "form"),
    ),
    SlotQuestion(
        "aware_at_proposal", "bool",
        "At the time you bought this policy, were you already aware that you had "
        "{cited_condition}?",
        ("aware", "know", "at the time"),
    ),
    SlotQuestion(
        "proposal_filled_by", "enum",
        "Who filled in the proposal form — you, an agent, or someone else?",
        ("proposal form", "filled", "who"),
        enum_map=_FILLED_BY,
    ),
    SlotQuestion(
        "disclosed_verbally", "bool",
        "Did you tell the agent or insurer about {cited_condition} verbally, even "
        "if it was not written on the form?",
        ("verbally", "tell", "told", "disclos"),
    ),
    SlotQuestion(
        "continuity_breaks", "bool",
        "Since this coverage began, has there been any gap or break in your "
        "renewals?",
        ("gap", "break", "renewal", "continuous"),
    ),
]

PED_INTERVIEW_BY_SLOT = {q.slot: q for q in PED_INTERVIEW}
