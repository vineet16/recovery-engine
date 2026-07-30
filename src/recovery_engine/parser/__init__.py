"""Parser subsystem (ARCHITECTURE.md Section 8).

Deterministic, tiered, source-anchored extraction of *specific typed fields at
known locations into a schema* — never "what does this policy say?" and never a
vector store (principle Section 2.1). Every field carries
`(value, confidence, document, page, span)`; below-threshold or mismatched
fields go to human review, never into the graph as a guess.

M2 implements Tier 1 (digital-native PDFs) fully and Tier 2 (OCR) behind a
swappable provider interface with a fake backend for tests. Tiers 3-4
(handwriting vision-LLM, clause extraction) are later work.
"""

from .base import (
    DocType,
    ExtractedField,
    ExtractionResult,
    ParsedDoc,
    ReviewItem,
    Tier,
)
from .pipeline import ParseReport, SourceDoc, parse_documents

__all__ = [
    "DocType",
    "Tier",
    "ExtractedField",
    "ExtractionResult",
    "ParsedDoc",
    "ReviewItem",
    "SourceDoc",
    "ParseReport",
    "parse_documents",
]
