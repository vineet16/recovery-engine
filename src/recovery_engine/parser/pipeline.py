"""Parse pipeline (Section 8): documents -> anchored fields -> a typed Case.

Orchestrates the tiers deterministic-first (digital before OCR), gates on
confidence, reconciles across documents, and emits a Case whose slots are all
PARSED + source-anchored — plus a review queue for anything below threshold,
mismatched, or unparseable. Below-threshold facts never enter the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..slots import Case, SlotSource
from .base import DocType, ExtractedField, ExtractionResult, ReviewItem, Tier
from .digital import load_digital
from .extract import extract_fields
from .ocr import CannedOCR, OCRBackend, OCRPage, load_ocr
from .reconcile import reconcile

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class SourceDoc:
    doc_id: str
    doctype: DocType
    pdf_path: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    ocr_pages: Optional[list[OCRPage]] = None  # forces OCR tier with canned text


@dataclass
class ParseReport:
    case: Case
    fields: dict[str, ExtractedField]          # accepted, entered the graph
    reviews: list[ReviewItem]                   # human-verification queue
    per_doc: list[ExtractionResult] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.reviews


def _load(doc: SourceDoc, ocr_backend: Optional[OCRBackend]):
    # Explicit canned OCR (tests / known scans) wins.
    if doc.ocr_pages is not None:
        return load_ocr(b"", doc.doc_id, doc.doctype, CannedOCR(doc.ocr_pages)), None

    data = doc.pdf_bytes
    if data is None and doc.pdf_path is not None:
        with open(doc.pdf_path, "rb") as fh:
            data = fh.read()
    if data is None:
        return None, ReviewItem(doc.doc_id, "no document content supplied")

    parsed = load_digital(data, doc.doc_id, doc.doctype)
    if parsed is not None:
        return parsed, None

    # No text layer -> Tier 2 if a backend is configured.
    if ocr_backend is not None:
        return load_ocr(data, doc.doc_id, doc.doctype, ocr_backend), None
    return None, ReviewItem(
        doc.doc_id, "image-only PDF and no OCR backend configured (Tier 2)"
    )


def parse_documents(
    docs: list[SourceDoc],
    *,
    case_id: str = "C-PARSED",
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ocr_backend: Optional[OCRBackend] = None,
) -> ParseReport:
    per_doc: list[ExtractionResult] = []
    reviews: list[ReviewItem] = []
    candidates: dict[str, list[ExtractedField]] = {}

    for doc in docs:
        parsed, load_review = _load(doc, ocr_backend)
        if load_review is not None:
            reviews.append(load_review)
        if parsed is None:
            continue
        res = extract_fields(parsed)
        per_doc.append(res)
        reviews.extend(res.reviews)
        for slot, ef in res.fields.items():
            candidates.setdefault(slot, []).append(ef)

    accepted, mismatch_reviews = reconcile(candidates)
    reviews.extend(mismatch_reviews)

    case = Case(case_id)
    entered: dict[str, ExtractedField] = {}
    for slot, ef in accepted.items():
        if ef.confidence < confidence_threshold:
            reviews.append(
                ReviewItem(
                    slot,
                    f"low confidence {ef.confidence:.2f} < {confidence_threshold:.2f}",
                    [ef],
                )
            )
            continue
        try:
            case.set(
                slot, ef.value,
                source=SlotSource.PARSED,
                confidence=ef.confidence,
                anchor=ef.anchor,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reviews.append(ReviewItem(slot, f"rejected on entry: {exc}", [ef]))
            continue
        entered[slot] = ef

    return ParseReport(case=case, fields=entered, reviews=reviews, per_doc=per_doc)
