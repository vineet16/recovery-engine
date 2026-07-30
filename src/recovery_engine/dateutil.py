"""Deterministic date arithmetic. Isolated so the pre-delivery gate (Section 11
Layer A) can recompute months independently and catch off-by-one bugs."""

from __future__ import annotations

from datetime import date


def months_between(start: date, end: date) -> int:
    """Whole calendar months from `start` to `end` (negative if end < start)."""
    if end < start:
        return -months_between(end, start)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months
