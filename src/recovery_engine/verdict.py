"""Verdict and lever-strength ordering (ARCHITECTURE.md Section 6.3)."""

from __future__ import annotations

from enum import IntEnum


class Strength(IntEnum):
    """Lever strength, ordered so it can be compared against a Verdict (V4)."""

    MODERATE = 1
    STRONG = 2


class Verdict(IntEnum):
    LIKELY_VALID = 0  # decline to draft; explain honestly (principle Section 2.6)
    MODERATE = 1
    STRONG = 2

    @property
    def label(self) -> str:
        return {0: "LIKELY-VALID", 1: "MODERATE", 2: "STRONG"}[int(self)]

    def allows(self, strength: Strength) -> bool:
        """V4: a draft may not assert a lever stronger than the verdict supports."""
        return int(strength) <= int(self)
