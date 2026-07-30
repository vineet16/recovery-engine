"""Hand-entered case fixtures (M1 has no parser — slots are entered directly)."""

from __future__ import annotations

from datetime import date

from recovery_engine import Case, ProposalFilledBy


def base(case_id: str = "C-TEST") -> Case:
    """Common parsed slots shared by every fixture."""
    return (
        Case(case_id)
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 250000)
        .set("denial_ground_text", "Claim repudiated for non-disclosure of pre-existing diabetes.")
        .set("cited_condition", "diabetes mellitus")
        .set("claimed_condition", "road traffic accident — fracture")
        .set("sum_insured", 500000)
        .set("ped_waiting_months", 36)
    )


def moratorium_strong() -> Case:
    """Long coverage → L1 fires (and L7). Verdict STRONG."""
    return (
        base("C-MORAT")
        .set("continuous_coverage_start", date(2019, 1, 1))
        .set("policy_inception_date", date(2019, 1, 1))
        .set("denial_date", date(2025, 1, 10))  # 72 months coverage
        .set("continuity_breaks", False)
        .set("fraud_proven", False)
    )


def diagnosis_strong() -> Case:
    """Short coverage, but condition diagnosed after inception → only L2 fires."""
    return (
        base("C-DX")
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("denial_date", date(2024, 12, 1))  # 6 months coverage
        .set("first_diagnosis_date", date(2024, 8, 1))  # after inception
    )


def not_asked_moderate() -> Case:
    """Short coverage, form did not ask → only L4 fires. Verdict MODERATE."""
    return (
        base("C-ASK")
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("denial_date", date(2024, 12, 1))
        .set("was_condition_asked", False)
    )


def agent_moderate() -> Case:
    return (
        base("C-AGENT")
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("denial_date", date(2024, 12, 1))
        .set("proposal_filled_by", ProposalFilledBy.AGENT)
        .set("disclosed_verbally", True)
    )


def not_aware_moderate() -> Case:
    return (
        base("C-AWARE")
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("denial_date", date(2024, 12, 1))
        .set("aware_at_proposal", False)
    )


def likely_valid() -> Case:
    """Everything cuts against the insured → nothing fires → decline."""
    return (
        base("C-VALID")
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("denial_date", date(2024, 12, 1))
        .set("was_condition_asked", True)
        .set("aware_at_proposal", True)
        .set("proposal_filled_by", ProposalFilledBy.SELF)
        .set("disclosed_verbally", False)
        .set("continuity_breaks", False)
        .set("fraud_proven", False)
    )
