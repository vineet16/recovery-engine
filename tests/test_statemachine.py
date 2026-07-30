"""M3 lifecycle: Stages 0-4 for the PED ground (ARCHITECTURE.md Section 4.2)."""

from __future__ import annotations

from datetime import date

from recovery_engine import FilingTarget, Letter, Stage, run_session
from recovery_engine.letter import Decline
from recovery_engine.parser.base import DocType
from recovery_engine.slots import Case


def eligible_base(case_id="C-SM") -> Case:
    """Health, in-window, short coverage — not contestable until the interview."""
    return (
        Case(case_id)
        .set("line_of_business", "health")
        .set("insurer_name", "Acme Health Insurance Co. Ltd.")
        .set("claim_amount", 250000)
        .set("cited_condition", "diabetes mellitus")
        .set("claimed_condition", "appendectomy")
        .set("denial_date", date(2025, 6, 1))
        .set("policy_inception_date", date(2024, 6, 1))
        .set("continuous_coverage_start", date(2024, 6, 1))
        .set("ped_waiting_months", 36)
    )


def answers_from(mapping):
    return lambda slot, question: mapping.get(slot)


AS_OF = date(2025, 6, 15)


# --- Stage 0: eligibility gate ----------------------------------------------

def test_stage0_blocks_over_jurisdiction():
    case = eligible_base().set("claim_amount", 6_000_000)
    res = run_session(case, as_of=AS_OF)
    assert res.stage_reached == Stage.INTAKE
    assert res.eligibility.status == "ineligible"
    assert any("jurisdiction" in r for r in res.eligibility.reasons)


def test_stage0_blocks_out_of_window():
    case = eligible_base().set("denial_date", date(2023, 1, 1))
    res = run_session(case, as_of=AS_OF)
    assert res.eligibility.status == "ineligible"
    assert any("1-year window" in r for r in res.eligibility.reasons)


def test_stage0_blocks_matter_in_forum():
    res = run_session(eligible_base(), as_of=AS_OF, in_court_or_forum=True)
    assert res.eligibility.status == "ineligible"


def test_stage0_not_yet_when_denial_date_unknown():
    case = eligible_base()
    del case.slots["denial_date"]
    res = run_session(case, as_of=AS_OF)
    assert res.eligibility.status == "not_yet"


# --- Full Stage 0-4 happy path ----------------------------------------------

def test_interview_rescues_case_and_ships_letter():
    case = eligible_base()
    # Diagnosed after inception -> L2 fires once the interview supplies the date.
    answers = answers_from({"first_diagnosis_date": "01/09/2024"})
    res = run_session(
        case,
        answers=answers,
        provided_docs={DocType.DISCHARGE_SUMMARY},
        as_of=AS_OF,
    )
    assert res.stage_reached == Stage.DRAFT
    assert isinstance(res.filing, Letter)
    assert res.filing_target == FilingTarget.GRIEVANCE
    assert res.shippable, (res.violations, res.evidence_gaps)
    assert "L2" in res.findings.fired_levers


def test_interview_stops_once_strong_lever_fires():
    case = eligible_base()
    res = run_session(
        case,
        answers=answers_from({"first_diagnosis_date": "01/09/2024"}),
        provided_docs={DocType.DISCHARGE_SUMMARY},
        as_of=AS_OF,
    )
    asked = [t.target_slot for t in res.turn_log]
    assert asked == ["first_diagnosis_date"]  # breadth stopped at the dispositive fact


def test_missing_proof_document_blocks_shipping():
    case = eligible_base()
    res = run_session(
        case,
        answers=answers_from({"first_diagnosis_date": "01/09/2024"}),
        provided_docs=set(),  # no discharge summary
        as_of=AS_OF,
    )
    assert res.evidence_gaps
    assert not res.shippable
    assert res.evidence_gaps[0].required_doc == DocType.DISCHARGE_SUMMARY


def test_weak_facts_end_in_honest_decline():
    case = eligible_base()
    answers = answers_from({
        "first_diagnosis_date": "01/01/2024",  # before inception -> L2 does not fire
        "was_condition_asked": "yes",
        "aware_at_proposal": "yes",
        "proposal_filled_by": "myself",
        "disclosed_verbally": "no",
        "continuity_breaks": "no gap",
    })
    res = run_session(case, answers=answers, as_of=AS_OF)
    assert res.stage_reached == Stage.DIAGNOSIS
    assert isinstance(res.filing, Decline)


def test_ombudsman_target_after_grievance_failed():
    case = eligible_base()
    res = run_session(
        case,
        answers=answers_from({"first_diagnosis_date": "01/09/2024"}),
        provided_docs={DocType.DISCHARGE_SUMMARY},
        as_of=AS_OF,
        grievance_failed=True,
    )
    assert res.filing_target == FilingTarget.OMBUDSMAN


def test_deadlines_ombudsman_cliff_is_one_year():
    res = run_session(
        eligible_base(),
        answers=answers_from({"first_diagnosis_date": "01/09/2024"}),
        provided_docs={DocType.DISCHARGE_SUMMARY},
        as_of=AS_OF,
    )
    assert res.deadlines.ombudsman_cliff == date(2026, 6, 1)
    assert res.deadlines.days_to_cliff() > 0
