"""End-to-end demo across M1-M3.

  M1  hand-entered slots  -> diagnosis -> filing -> validator gate
  M2  real PDFs           -> tiered anchored parse -> Case -> filing
  M3  full Stage 0-4      -> eligibility, interview, fork, evidence gate

Run: python demo.py   (from the repo root)
"""

from __future__ import annotations

import sys
from datetime import date

sys.path.insert(0, "src")

from recovery_engine import Case, ProposalFilledBy, run, run_session  # noqa: E402
from recovery_engine.parser import DocType, SourceDoc, parse_documents  # noqa: E402
from recovery_engine.parser.base import DocType as DT  # noqa: E402
from recovery_engine.parser.fixtures import (  # noqa: E402
    denial_letter_pdf,
    policy_schedule_pdf,
)

RULE = "=" * 78


def m1_strong() -> None:
    case = (
        Case("DEMO-M1")
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 312000)
        .set("cited_condition", "hypertension")
        .set("claimed_condition", "appendectomy")
        .set("sum_insured", 500000)
        .set("ped_waiting_months", 36)
        .set("continuous_coverage_start", date(2018, 3, 1))
        .set("policy_inception_date", date(2018, 3, 1))
        .set("denial_date", date(2025, 2, 20))
    )
    res = run(case)
    print(RULE, "\nM1 — deterministic core (moratorium, STRONG)\n", "-" * 78, sep="")
    print(f"Verdict {res.findings.verdict.label}  levers {res.findings.fired_levers}  "
          f"gate {'PASS' if res.shippable else res.violations}")
    print(res.filing.render())


def m2_parse() -> None:
    docs = [
        SourceDoc("denial.pdf", DT.DENIAL_LETTER, pdf_bytes=denial_letter_pdf()),
        SourceDoc("policy.pdf", DT.POLICY_SCHEDULE, pdf_bytes=policy_schedule_pdf()),
    ]
    report = parse_documents(docs)
    print(RULE, "\nM2 — tiered anchored parse of real PDFs\n", "-" * 78, sep="")
    for slot, ef in sorted(report.fields.items()):
        print(f"  {slot:28} = {ef.value!r:24} @{ef.confidence:.2f}  "
              f"[{ef.anchor.document}:p{ef.anchor.page}]")
    print(f"  review queue: {len(report.reviews)} item(s)")


def m3_session() -> None:
    case = (
        Case("DEMO-M3")
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 250000)
        .set("cited_condition", "diabetes mellitus")
        .set("claimed_condition", "appendectomy")
        .set("ped_waiting_months", 36)
        .set("denial_date", date(2025, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("continuous_coverage_start", date(2024, 6, 1))
    )
    # A scripted policyholder: the condition was first diagnosed after inception.
    answers = {"first_diagnosis_date": "01/09/2024"}
    res = run_session(
        case,
        answers=lambda slot, q: answers.get(slot),
        provided_docs={DocType.DISCHARGE_SUMMARY},
        as_of=date(2025, 6, 15),
    )
    print(RULE, "\nM3 — full Stage 0-4 lifecycle (interview rescues the case)\n", "-" * 78, sep="")
    print(f"  Stage reached : {res.stage_reached.name}")
    print(f"  Eligibility   : {res.eligibility.status} ({'; '.join(res.eligibility.reasons)})")
    print(f"  Verdict       : {res.findings.verdict.label}  levers {res.findings.fired_levers}")
    print(f"  Filing target : {res.filing_target.value}")
    print(f"  Ombudsman cliff: {res.deadlines.ombudsman_cliff} "
          f"({res.deadlines.days_to_cliff()} days left)")
    print(f"  Ships?         : {res.shippable}")
    print("  Interview turns:")
    for t in res.turn_log:
        print(f"    Q[{t.target_slot}]: {t.generated_question}")
        print(f"      -> {t.raw_answer!r} parsed as {t.parsed_value!r}")


if __name__ == "__main__":
    m1_strong()
    m2_parse()
    m3_session()
