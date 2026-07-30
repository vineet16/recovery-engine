"""Extraction schema (ARCHITECTURE.md Section 8).

Each parsed slot has typed extraction rules: labelled regex patterns (ranked by
reliability), a coercion to the slot's Python type, and a plausibility gate
(reused from SLOT_SPECS). Off-type or out-of-range values fail the field rather
than propagate. This is schema-driven extraction, not freeform RAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Optional

from ..slots import SLOT_SPECS, ProposalFilledBy
from .base import DocType

# --- coercions --------------------------------------------------------------

_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%d %B %Y", "%d %b %Y",
    "%Y-%m-%d",
)

# Reusable date sub-pattern (kept loose; coercion is the real gate).
DATE_RE = r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}"


def coerce_date(raw: str) -> date:
    s = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date: {raw!r}")


def coerce_amount(raw: str) -> float:
    s = re.sub(r"[₹,\s]|Rs\.?|INR", "", raw, flags=re.IGNORECASE)
    return float(s)


def coerce_int(raw: str) -> int:
    return int(raw.strip())


def coerce_str(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().rstrip(".,")


def coerce_lob(raw: str) -> str:
    return raw.strip().lower()


@dataclass
class SlotRule:
    slot: str
    patterns: list[tuple[str, float]]  # (regex source, base confidence)
    coerce: Callable[[str], Any]
    doctypes: Optional[set[DocType]] = None  # restrict search; None = any
    _compiled: list[tuple[re.Pattern, float]] = field(default_factory=list, repr=False)

    def compile(self) -> "SlotRule":
        self._compiled = [
            (re.compile(src, re.IGNORECASE | re.DOTALL), conf) for src, conf in self.patterns
        ]
        return self

    def check_plausible(self, value: Any) -> None:
        spec = SLOT_SPECS.get(self.slot)
        if spec is not None:
            spec.check(value)  # raises on off-type / out-of-range


def _p(*patterns: tuple[str, float]) -> list[tuple[str, float]]:
    return list(patterns)


# --- the rulebook -----------------------------------------------------------
# `(?P<v>...)` marks the value group in every pattern.

_RULES: list[SlotRule] = [
    SlotRule(
        "insurer_name",
        _p((r"(?P<v>[A-Z][A-Za-z&.]+(?:\s+[A-Z][A-Za-z&.]+){0,4}\s+"
            r"(?:Health\s+)?(?:General\s+)?Insurance\s+Co(?:mpany)?\.?"
            r"(?:\s+Ltd\.?|\s+Limited)?)", 0.8),),
        coerce_str,
    ),
    SlotRule(
        "line_of_business",
        _p((r"(?P<v>health)\s+insurance", 0.9),),
        coerce_lob,
    ),
    SlotRule(
        "claim_amount",
        _p(
            (r"claim(?:ed)?\s+amount\s*[:\-]?\s*(?:₹|Rs\.?|INR)?\s*(?P<v>[\d,]+(?:\.\d+)?)", 0.9),
            (r"amount\s+(?:claimed|of\s+claim)\s*[:\-]?\s*(?:₹|Rs\.?|INR)?\s*(?P<v>[\d,]+)", 0.8),
        ),
        coerce_amount,
        {DocType.DENIAL_LETTER, DocType.BILL},
    ),
    SlotRule(
        "sum_insured",
        _p((r"sum\s+insured\s*[:\-]?\s*(?:₹|Rs\.?|INR)?\s*(?P<v>[\d,]+(?:\.\d+)?)", 0.9),),
        coerce_amount,
    ),
    SlotRule(
        "denial_date",
        _p(
            (rf"(?:date\s+of\s+(?:repudiation|denial|rejection)|repudiated\s+on|dated)"
             rf"\s*[:\-]?\s*(?P<v>{DATE_RE})", 0.9),
        ),
        coerce_date,
        {DocType.DENIAL_LETTER},
    ),
    SlotRule(
        "policy_inception_date",
        _p(
            (rf"(?:policy\s+inception(?:\s+date)?|date\s+of\s+commencement|commencement\s+date)"
             rf"\s*[:\-]?\s*(?P<v>{DATE_RE})", 0.9),
        ),
        coerce_date,
    ),
    SlotRule(
        "continuous_coverage_start",
        _p(
            (rf"(?:continuous(?:ly)?\s+(?:covered|insured)\s+since|coverage\s+start(?:\s+date)?|"
             rf"first\s+enrol(?:l)?ment(?:\s+date)?|inception\s+of\s+first\s+policy)"
             rf"\s*[:\-]?\s*(?P<v>{DATE_RE})", 0.9),
        ),
        coerce_date,
    ),
    SlotRule(
        "ped_waiting_months",
        _p(
            (r"pre-?existing\s+disease[^\d]{0,40}?waiting\s+period[^\d]{0,20}?(?P<v>\d{1,3})\s*months?", 0.9),
            (r"PED\s+waiting[^\d]{0,20}?(?P<v>\d{1,3})\s*months?", 0.8),
        ),
        coerce_int,
    ),
    SlotRule(
        "cited_condition",
        _p(
            (r"non-?disclosure\s+of\s+(?:pre-?existing\s+)?(?:disease\s+of\s+|condition\s+of\s+)?"
             r"(?P<v>[A-Za-z][A-Za-z ]{2,40}?)\s*(?:[.,]|which|that|$)", 0.8),
            (r"pre-?existing\s+(?:disease|condition)\s+of\s+(?P<v>[A-Za-z][A-Za-z ]{2,40}?)\s*[.,]", 0.75),
        ),
        coerce_str,
        {DocType.DENIAL_LETTER},
    ),
    SlotRule(
        "claimed_condition",
        _p(
            (r"(?:final\s+diagnosis|diagnosis|treated\s+for)\s*[:\-]?\s*(?P<v>[A-Za-z][A-Za-z /]{2,50}?)\s*(?:[.\n]|$)", 0.8),
        ),
        coerce_str,
        {DocType.BILL, DocType.DISCHARGE_SUMMARY, DocType.DENIAL_LETTER},
    ),
    SlotRule(
        "denial_ground_text",
        _p(
            (r"(?P<v>[^.\n]*\b(?:repudiat|reject|deni(?:ed|al)|declin)[A-Za-z]*\b[^.\n]*\.)", 0.7),
        ),
        coerce_str,
        {DocType.DENIAL_LETTER},
    ),
]

RULES: list[SlotRule] = [r.compile() for r in _RULES]
