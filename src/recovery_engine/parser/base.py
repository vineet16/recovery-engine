"""Core parser types (ARCHITECTURE.md Section 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..slots import Anchor


class DocType(str, Enum):
    DENIAL_LETTER = "denial_letter"   # primary evidence
    POLICY_SCHEDULE = "policy_schedule"
    BILL = "bill"
    PROPOSAL_FORM = "proposal_form"
    DISCHARGE_SUMMARY = "discharge_summary"
    OTHER = "other"


class Tier(int, Enum):
    STRUCTURED = 0     # DigiLocker / digitally-issued pulls (preferred; not M2)
    DIGITAL = 1        # digital-native PDF text layer
    OCR = 2            # scanned PDF via OCR provider
    HANDWRITING = 3    # vision-LLM transcription (later)


@dataclass
class ParsedDoc:
    """A document reduced to page-anchored text before field extraction."""

    doc_id: str
    doctype: DocType
    tier: Tier
    full_text: str
    page_bounds: list[tuple[int, int]]  # (start, end) char offset of each page
    ocr_confidence: float = 1.0         # mean OCR word confidence (Tier 2)

    def page_of(self, offset: int) -> int:
        for i, (start, end) in enumerate(self.page_bounds):
            if start <= offset < end:
                return i
        return max(0, len(self.page_bounds) - 1)


@dataclass
class ExtractedField:
    """One typed value welded to its source (Section 8 guarantee)."""

    slot: str
    value: Any
    confidence: float
    anchor: Anchor
    raw_text: str
    tier: Tier

    def __repr__(self) -> str:  # compact, useful in review dumps
        return (
            f"ExtractedField({self.slot}={self.value!r} @{self.confidence:.2f} "
            f"{self.anchor.document}:p{self.anchor.page})"
        )


@dataclass
class ReviewItem:
    """A field routed to a human before it may enter the graph (Section 13.6)."""

    slot: str
    reason: str
    candidates: list[ExtractedField] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Per-document output: the fields found plus anything needing review."""

    doc: ParsedDoc
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    reviews: list[ReviewItem] = field(default_factory=list)
