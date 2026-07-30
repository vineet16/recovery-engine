"""End-to-end M1 demo: hand-entered slots -> diagnosis -> filing -> gate.

Run: python demo.py   (from the repo root)
"""

from __future__ import annotations

import sys
from datetime import date

sys.path.insert(0, "src")

from recovery_engine import Case, ProposalFilledBy, run  # noqa: E402


def show(title: str, case: Case) -> None:
    res = run(case)
    print("=" * 78)
    print(title)
    print("-" * 78)
    print(f"Verdict: {res.findings.verdict.label}   Fired levers: {res.findings.fired_levers}")
    print(f"Pre-delivery gate: {'PASS' if res.shippable else 'BLOCKED ' + str(res.violations)}")
    print("-" * 78)
    print(res.filing.render())
    print()


def strong_moratorium() -> Case:
    return (
        Case("DEMO-1")
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 312000)
        .set("denial_ground_text", "Repudiated: non-disclosure of pre-existing hypertension.")
        .set("cited_condition", "hypertension")
        .set("claimed_condition", "appendectomy")
        .set("sum_insured", 500000)
        .set("ped_waiting_months", 36)
        .set("continuous_coverage_start", date(2018, 3, 1))
        .set("policy_inception_date", date(2018, 3, 1))
        .set("denial_date", date(2025, 2, 20))
    )


def likely_valid() -> Case:
    return (
        Case("DEMO-2")
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 90000)
        .set("denial_ground_text", "Repudiated: non-disclosure of pre-existing diabetes.")
        .set("cited_condition", "diabetes mellitus")
        .set("claimed_condition", "diabetic nephropathy")
        .set("sum_insured", 300000)
        .set("ped_waiting_months", 36)
        .set("continuous_coverage_start", date(2024, 1, 1))
        .set("policy_inception_date", date(2024, 1, 1))
        .set("denial_date", date(2024, 10, 1))
        .set("was_condition_asked", True)
        .set("aware_at_proposal", True)
        .set("proposal_filled_by", ProposalFilledBy.SELF)
    )


if __name__ == "__main__":
    show("CASE 1 — moratorium bar (STRONG, ships a grievance letter)", strong_moratorium())
    show("CASE 2 — weak facts (LIKELY-VALID, honest decline)", likely_valid())
