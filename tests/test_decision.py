"""Decision logic + verdict (ARCHITECTURE.md Section 6.3)."""

from __future__ import annotations

from recovery_engine import Verdict, diagnose
from recovery_engine.dateutil import months_between
from datetime import date

import _cases


def test_moratorium_fires_strong():
    f = diagnose(_cases.moratorium_strong())
    assert f.verdict == Verdict.STRONG
    assert "L1" in f.fired_levers
    assert f.predicate_true("moratorium_met")


def test_diagnosis_post_inception_only_lever():
    f = diagnose(_cases.diagnosis_strong())
    assert f.verdict == Verdict.STRONG
    assert f.fired_levers == ["L2"]
    assert not f.predicate_true("moratorium_met")


def test_not_asked_is_moderate():
    f = diagnose(_cases.not_asked_moderate())
    assert f.verdict == Verdict.MODERATE
    assert f.fired_levers == ["L4"]


def test_agent_defense_is_moderate():
    f = diagnose(_cases.agent_moderate())
    assert f.verdict == Verdict.MODERATE
    assert f.fired_levers == ["L6"]


def test_not_aware_is_moderate():
    f = diagnose(_cases.not_aware_moderate())
    assert f.verdict == Verdict.MODERATE
    assert f.fired_levers == ["L5"]


def test_likely_valid_declines():
    f = diagnose(_cases.likely_valid())
    assert f.verdict == Verdict.LIKELY_VALID
    assert f.fired_levers == []


def test_continuity_break_defeats_moratorium():
    case = _cases.moratorium_strong()
    case.set("continuity_breaks", True)
    f = diagnose(case)
    assert not f.predicate_true("moratorium_met")


def test_fraud_defeats_moratorium():
    case = _cases.moratorium_strong()
    case.set("fraud_proven", True)
    f = diagnose(case)
    assert not f.predicate_true("moratorium_met")


def test_ped_waiting_served_capped_at_36():
    # Policy states a 48-month PED waiting, but the cap is 36; 40 months coverage
    # therefore serves it.
    case = (
        _cases.base("C-CAP")
        .set("continuous_coverage_start", date(2021, 1, 1))
        .set("policy_inception_date", date(2021, 1, 1))
        .set("denial_date", date(2024, 5, 1))  # 40 months
    )
    case.set("ped_waiting_months", 48)
    f = diagnose(case)
    assert f.predicate_true("ped_waiting_served")
    assert f.support["effective_ped_waiting"] == 36


def test_months_between_off_by_one():
    assert months_between(date(2019, 1, 1), date(2025, 1, 10)) == 72
    assert months_between(date(2024, 6, 1), date(2024, 12, 1)) == 6
    assert months_between(date(2024, 6, 15), date(2024, 12, 1)) == 5  # day < day
