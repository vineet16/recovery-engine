"""Apply the extraction schema to a page-anchored document (Section 8).

Deterministic: for each slot rule, scan the text, coerce to the slot's type,
gate on plausibility, and keep the highest-confidence match. Off-type or
out-of-range values are dropped (never propagated); a slot with no match stays
"unknown" rather than being guessed.
"""

from __future__ import annotations

from ..slots import Anchor
from .base import ExtractedField, ExtractionResult, ParsedDoc
from .schema import RULES

# A primary match at or above this confidence stops us trying weaker patterns.
_PRIMARY_STOP = 0.85


def extract_fields(doc: ParsedDoc) -> ExtractionResult:
    result = ExtractionResult(doc=doc)
    for rule in RULES:
        if rule.doctypes is not None and doc.doctype not in rule.doctypes:
            continue
        best: ExtractedField | None = None
        for pattern, base_conf in rule._compiled:
            for m in pattern.finditer(doc.full_text):
                raw = m.groupdict().get("v")
                if not raw:
                    continue
                try:
                    value = rule.coerce(raw)
                    rule.check_plausible(value)
                except (ValueError, TypeError):
                    continue  # off-type / out-of-range: drop, don't propagate
                conf = round(base_conf * doc.ocr_confidence, 4)
                start, end = m.span("v")
                anchor = Anchor(document=doc.doc_id, page=doc.page_of(start), span=(start, end))
                cand = ExtractedField(rule.slot, value, conf, anchor, raw.strip(), doc.tier)
                if best is None or cand.confidence > best.confidence:
                    best = cand
            if best is not None and best.confidence >= _PRIMARY_STOP:
                break
        if best is not None:
            result.fields[rule.slot] = best
    return result
