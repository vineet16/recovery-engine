"""Synthetic PDF fixtures for M2 (tests + demo).

Generates digital-native and image-only PDFs with known, controllable content so
the tiered parser can be exercised end-to-end without shipping real (sensitive)
policyholder documents. These are test scaffolding, not production data.
"""

from __future__ import annotations

import fitz


def _text_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    return doc.tobytes()


def denial_letter_pdf(
    *,
    insurer: str = "Acme Health Insurance Co. Ltd.",
    claim_amount: str = "3,12,000",
    denial_date: str = "20/02/2025",
    cited_condition: str = "hypertension",
) -> bytes:
    return _text_pdf(
        [
            insurer,
            "Claims Department",
            "",
            "SUBJECT: Repudiation of Health Insurance Claim",
            "",
            f"Claim Amount: Rs. {claim_amount}",
            f"Date of Repudiation: {denial_date}",
            "",
            "Dear Policyholder,",
            "We regret to inform you that your health insurance claim has been",
            f"repudiated on grounds of non-disclosure of {cited_condition}, a",
            "pre-existing condition not declared at the time of proposal.",
            "",
            "Grievance Redressal Officer",
        ]
    )


def policy_schedule_pdf(
    *,
    insurer: str = "Acme Health Insurance Co. Ltd.",
    sum_insured: str = "5,00,000",
    inception: str = "01/03/2018",
    coverage_start: str = "01/03/2018",
    ped_waiting_months: int = 36,
) -> bytes:
    return _text_pdf(
        [
            insurer,
            "Health Insurance — Policy Schedule",
            "",
            f"Sum Insured: Rs. {sum_insured}",
            f"Policy Inception Date: {inception}",
            f"Continuously insured since: {coverage_start}",
            f"Pre-existing Disease Waiting Period: {ped_waiting_months} months",
        ]
    )


def image_only_pdf(text_lines: list[str]) -> bytes:
    """A scanned-style PDF: text rasterised to an image, no text layer.

    load_digital() returns None for this, forcing the OCR tier.
    """
    tmp = fitz.open()
    page = tmp.new_page()
    y = 72
    for line in text_lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    pix = page.get_pixmap(dpi=150)

    out = fitz.open()
    opage = out.new_page(width=pix.width, height=pix.height)
    opage.insert_image(opage.rect, pixmap=pix)
    return out.tobytes()
