"""Filing assembly (Section 6.4) + validator V1-V5 (Section 6.5)."""

from __future__ import annotations

import copy
from datetime import date

from recovery_engine import (
    Decline,
    Letter,
    Verdict,
    default_store,
    diagnose,
    draft,
    run,
    validate,
)
from recovery_engine.letter import Assertion
import _cases


# --- Assembly ---------------------------------------------------------------

def test_strong_case_produces_clean_letter():
    res = run(_cases.diagnosis_strong())
    assert isinstance(res.filing, Letter)
    assert res.shippable, res.violations
    text = res.filing.render()
    assert "diabetes mellitus" in text
    assert "cannot constitute a pre-existing disease" in text


def test_moratorium_letter_embeds_exact_citation():
    res = run(_cases.moratorium_strong())
    text = res.filing.render()
    assert "IRDAI/HLT/CIR/MISC/77/05/2024" in text
    assert res.shippable, res.violations


def test_likely_valid_yields_decline_not_letter():
    res = run(_cases.likely_valid())
    assert isinstance(res.filing, Decline)
    assert res.shippable  # a correct decline is a valid outcome
    assert "unable to draft" in res.filing.render()


def test_letter_orders_levers_strongest_first():
    res = run(_cases.moratorium_strong())
    ids = [a.lever_id for a in res.filing.assertions]
    # L1 (STRONG) precedes any MODERATE lever.
    assert ids[0] == "L1"


# --- Validator: clean pass --------------------------------------------------

def test_valid_pipeline_has_no_violations():
    for builder in (
        _cases.moratorium_strong,
        _cases.diagnosis_strong,
        _cases.not_asked_moderate,
        _cases.agent_moderate,
        _cases.not_aware_moderate,
        _cases.likely_valid,
    ):
        res = run(builder())
        assert res.violations == [], f"{builder.__name__}: {res.violations}"


# --- Validator: tamper vectors ---------------------------------------------

def _codes(violations):
    return {v.rule for v in violations}


def test_v3_catches_fabricated_citation():
    case = _cases.diagnosis_strong()
    findings = diagnose(case)
    letter = draft(case, findings)
    letter.assertions[0].citations.append("FAKE_REG")  # hallucinated citation
    vs = validate(case, findings, letter)
    assert "V3" in _codes(vs)


def test_v2_catches_unfilled_token():
    case = _cases.diagnosis_strong()
    findings = diagnose(case)
    letter = draft(case, findings)
    letter.assertions[0].tokens.append("continuity_breaks")  # never filled here
    vs = validate(case, findings, letter)
    assert "V2" in _codes(vs)


def test_v1_catches_lever_not_fired():
    case = _cases.diagnosis_strong()
    findings = diagnose(case)
    letter = draft(case, findings)
    letter.assertions.append(
        Assertion("L1", "Fabricated moratorium claim.", [], [])
    )
    vs = validate(case, findings, letter)
    assert "V1" in _codes(vs)


def test_v4_catches_lever_stronger_than_verdict():
    # Build a genuine STRONG L1 letter, then force the verdict down to MODERATE.
    case = _cases.moratorium_strong()
    findings = diagnose(case)
    letter = draft(case, findings)
    downgraded = copy.copy(findings)
    downgraded.verdict = Verdict.MODERATE
    vs = validate(case, downgraded, letter)
    assert "V4" in _codes(vs)


def test_v5_catches_letter_on_likely_valid():
    case = _cases.likely_valid()
    findings = diagnose(case)
    # Force a letter to exist despite the LIKELY-VALID verdict.
    bogus = Letter(case.case_id, Verdict.LIKELY_VALID, [], case=case)
    vs = validate(case, findings, bogus)
    assert "V5" in _codes(vs)
