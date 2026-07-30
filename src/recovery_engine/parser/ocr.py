"""Tier 2 — OCR for scanned PDFs (Section 8, tier 2).

The OCR engine sits behind a swappable `OCRBackend` protocol so AWS Textract
(primary on the AWS stack), Surya, PaddleOCR, or a cloud fallback can be dropped
in without touching the pipeline. `CannedOCR` is a deterministic backend for
tests. `TextractBackend` is the real adapter; boto3 is imported lazily so the
package has no hard AWS dependency.

Whatever the backend, output is normalised to `ParsedDoc` and fed through the
same schema extractor as Tier 1 — OCR word confidence scales field confidence,
so a blurry scan lands lower and is more likely to be routed to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .base import DocType, ParsedDoc, Tier


@dataclass
class OCRPage:
    text: str
    mean_confidence: float = 0.9  # 0..1 average word confidence


class OCRBackend(Protocol):
    def read(self, pdf: bytes) -> list[OCRPage]: ...


@dataclass
class CannedOCR:
    """Deterministic backend: returns pre-supplied pages. For tests/fixtures."""

    pages: list[OCRPage]

    def read(self, pdf: bytes) -> list[OCRPage]:
        return self.pages


class TextractBackend:
    """AWS Textract adapter. Real; not exercised in the test suite.

    Uses `analyze_document` and averages block confidences. boto3 is imported
    lazily so importing this module never requires the AWS SDK.
    """

    def __init__(self, region_name: str | None = None):
        self._region = region_name

    def read(self, pdf: bytes) -> list[OCRPage]:  # pragma: no cover - needs AWS
        import boto3  # lazy

        client = boto3.client("textract", region_name=self._region)
        resp = client.analyze_document(
            Document={"Bytes": pdf}, FeatureTypes=["FORMS", "TABLES"]
        )
        lines, confs = [], []
        for block in resp.get("Blocks", []):
            if block.get("BlockType") == "LINE":
                lines.append(block.get("Text", ""))
                confs.append(block.get("Confidence", 0.0) / 100.0)
        mean = sum(confs) / len(confs) if confs else 0.0
        return [OCRPage("\n".join(lines), mean)]


def load_ocr(pdf: bytes, doc_id: str, doctype: DocType, backend: OCRBackend) -> ParsedDoc:
    pages = backend.read(pdf)
    full_text, bounds, cursor = "", [], 0
    confs = []
    for page in pages:
        start = cursor
        full_text += page.text
        cursor += len(page.text)
        full_text += "\n"
        cursor += 1
        bounds.append((start, cursor))
        confs.append(page.mean_confidence)
    mean_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
    return ParsedDoc(
        doc_id=doc_id,
        doctype=doctype,
        tier=Tier.OCR,
        full_text=full_text,
        page_bounds=bounds or [(0, 0)],
        ocr_confidence=mean_conf,
    )
