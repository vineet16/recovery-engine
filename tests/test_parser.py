"""M2 parser: tiered, anchored extraction -> Case (ARCHITECTURE.md Section 8)."""

from __future__ import annotations

from datetime import date

from recovery_engine import diagnose, draft, validate
from recovery_engine.parser import DocType, SourceDoc, parse_documents
from recovery_engine.parser.fixtures import (
    denial_letter_pdf,
    image_only_pdf,
    policy_schedule_pdf,
)
from recovery_engine.parser.ocr import OCRPage
from recovery_engine.slots import SlotSource


def _strong_docs():
    return [
        SourceDoc("denial.pdf", DocType.DENIAL_LETTER, pdf_bytes=denial_letter_pdf()),
        SourceDoc("policy.pdf", DocType.POLICY_SCHEDULE, pdf_bytes=policy_schedule_pdf()),
    ]


def test_tier1_extracts_anchored_typed_fields():
    report = parse_documents(_strong_docs())
    c = report.case
    assert c.value("denial_date") == date(2025, 2, 20)
    assert c.value("policy_inception_date") == date(2018, 3, 1)
    assert c.value("continuous_coverage_start") == date(2018, 3, 1)
    assert c.value("ped_waiting_months") == 36
    assert c.value("claim_amount") == 312000.0
    assert c.value("sum_insured") == 500000.0
    assert "hypertension" in c.value("cited_condition").lower()


def test_parsed_slots_are_source_anchored():
    report = parse_documents(_strong_docs())
    slot = report.case.get("denial_date")
    assert slot.source == SlotSource.PARSED
    assert slot.anchor is not None
    assert slot.anchor.document == "denial.pdf"
    assert slot.anchor.span is not None


def test_parsed_case_flows_into_the_graph():
    # The whole point of M2: real documents feed the M1 engine.
    report = parse_documents(_strong_docs())
    findings = diagnose(report.case)
    filing = draft(report.case, findings)
    assert not validate(report.case, findings, filing)  # ships clean
    assert "L1" in findings.fired_levers  # 2018 coverage clears the moratorium


def test_image_only_pdf_without_ocr_is_flagged_not_guessed():
    scan = image_only_pdf(["Date of Repudiation: 20/02/2025"])
    report = parse_documents(
        [SourceDoc("scan.pdf", DocType.DENIAL_LETTER, pdf_bytes=scan)]
    )
    assert report.reviews  # routed to human, nothing silently extracted
    assert not report.case.is_filled("denial_date")


def test_ocr_tier_reads_scanned_text_with_scaled_confidence():
    pages = [
        OCRPage("Date of Repudiation: 20/02/2025", mean_confidence=0.8),
        OCRPage("non-disclosure of diabetes.", mean_confidence=0.8),
    ]
    report = parse_documents(
        [SourceDoc("scan.pdf", DocType.DENIAL_LETTER, ocr_pages=pages)]
    )
    assert report.case.value("denial_date") == date(2025, 2, 20)
    slot = report.case.get("denial_date")
    assert slot.confidence < 0.9  # OCR confidence scaled it down


def test_cross_document_mismatch_is_flagged():
    docs = [
        SourceDoc("denial.pdf", DocType.DENIAL_LETTER, pdf_bytes=denial_letter_pdf()),
        SourceDoc(
            "policy.pdf",
            DocType.POLICY_SCHEDULE,
            pdf_bytes=policy_schedule_pdf(inception="01/03/2018"),
        ),
        SourceDoc(
            "policy2.pdf",
            DocType.POLICY_SCHEDULE,
            pdf_bytes=policy_schedule_pdf(inception="15/09/2019"),
        ),
    ]
    report = parse_documents(docs)
    assert any(r.slot == "policy_inception_date" for r in report.reviews)
    # mismatched fact stays out of the graph
    assert not report.case.is_filled("policy_inception_date")


def test_low_confidence_field_routed_to_review():
    pages = [OCRPage("Date of Repudiation: 20/02/2025", mean_confidence=0.5)]
    report = parse_documents(
        [SourceDoc("scan.pdf", DocType.DENIAL_LETTER, ocr_pages=pages)],
        confidence_threshold=0.7,
    )
    # denial_date base 0.9 * 0.5 = 0.45 < 0.7 -> review, not in graph
    assert any(r.slot == "denial_date" for r in report.reviews)
    assert not report.case.is_filled("denial_date")


def test_out_of_type_value_does_not_propagate():
    # A garbled amount must not enter as a number.
    pages = [OCRPage("Claim Amount: Rs. ABC,000", mean_confidence=0.95)]
    report = parse_documents(
        [SourceDoc("scan.pdf", DocType.DENIAL_LETTER, ocr_pages=pages)]
    )
    assert not report.case.is_filled("claim_amount")
