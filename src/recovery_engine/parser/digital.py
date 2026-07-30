"""Tier 1 — digital-native PDF extraction (Section 8, tier 1).

Detect a text layer with PyMuPDF; if present, extract structurally. Exact by
construction, no model. Always tried first. A PDF with no meaningful text layer
returns None so the pipeline can fall back to OCR (Tier 2).
"""

from __future__ import annotations

from typing import Optional

import fitz  # PyMuPDF

from .base import DocType, ParsedDoc, Tier

# Below this many non-whitespace characters we treat the PDF as image-only.
_DIGITAL_MIN_CHARS = 20


def _read_bytes(source: "SourceLike") -> bytes:
    if isinstance(source, bytes):
        return source
    with open(source, "rb") as fh:
        return fh.read()


def load_digital(pdf: "bytes | str", doc_id: str, doctype: DocType) -> Optional[ParsedDoc]:
    data = _read_bytes(pdf)
    with fitz.open(stream=data, filetype="pdf") as book:
        page_texts = [page.get_text("text") for page in book]

    non_ws = sum(len(t.strip()) for t in page_texts)
    if non_ws < _DIGITAL_MIN_CHARS:
        return None  # no usable text layer -> defer to OCR

    full_text, bounds, cursor = "", [], 0
    for text in page_texts:
        start = cursor
        full_text += text
        cursor += len(text)
        full_text += "\n"
        cursor += 1
        bounds.append((start, cursor))

    return ParsedDoc(
        doc_id=doc_id,
        doctype=doctype,
        tier=Tier.DIGITAL,
        full_text=full_text,
        page_bounds=bounds,
        ocr_confidence=1.0,
    )


# for type hints only
SourceLike = "bytes | str"
