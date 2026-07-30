"""Effective-date-versioned law (ARCHITECTURE.md Sections 2.4, 9).

Same coverage-start; crossing the 1-April-2024 boundary flips the moratorium
period from 96 months (8y) to 60 months, and that flips whether L1 fires.
"""

from __future__ import annotations

from datetime import date

from recovery_engine import diagnose, default_store
import _cases


def _case_with_denial(denial: date):
    return (
        _cases.base("C-VER")
        .set("continuous_coverage_start", date(2019, 1, 1))
        .set("policy_inception_date", date(2019, 1, 1))
        .set("ped_waiting_months", 120)  # keep L7 out of the way
        .set("denial_date", denial)
    )


def test_pre_2024_uses_eight_year_moratorium():
    f = diagnose(_case_with_denial(date(2024, 1, 1)))  # 60 months coverage
    assert f.support["moratorium_months"] == 96
    assert not f.predicate_true("moratorium_met")  # 60 < 96


def test_post_2024_uses_sixty_month_moratorium():
    f = diagnose(_case_with_denial(date(2024, 5, 1)))  # 64 months coverage
    assert f.support["moratorium_months"] == 60
    assert f.predicate_true("moratorium_met")  # 64 >= 60


def test_citation_store_resolves_by_relevant_date():
    store = default_store()
    assert store.resolve("MORATORIUM", date(2023, 6, 1)).value == 96
    assert store.resolve("MORATORIUM", date(2024, 6, 1)).value == 60
    assert store.resolve("PED_WAITING_CAP", date(2024, 6, 1)).value == 36
