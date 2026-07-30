"""Cross-document reconciliation (Section 8).

Facts appearing in more than one document (inception date, sum insured, insurer)
must agree. Agreement -> keep the highest-confidence anchor. Disagreement -> flag
for review and keep the slot out of the graph (never silently pick one).
"""

from __future__ import annotations

from datetime import date

from .base import ExtractedField, ReviewItem

_AMOUNT_TOL = 1.0  # rupees


def _equivalent(a, b) -> bool:
    if isinstance(a, date) and isinstance(b, date):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= _AMOUNT_TOL
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def reconcile(
    candidates_by_slot: dict[str, list[ExtractedField]],
) -> tuple[dict[str, ExtractedField], list[ReviewItem]]:
    accepted: dict[str, ExtractedField] = {}
    reviews: list[ReviewItem] = []

    for slot, cands in candidates_by_slot.items():
        if not cands:
            continue
        best = max(cands, key=lambda f: f.confidence)
        disagreeing = [c for c in cands if not _equivalent(c.value, best.value)]
        if disagreeing:
            reviews.append(
                ReviewItem(
                    slot=slot,
                    reason=(
                        f"cross-document mismatch: "
                        + ", ".join(
                            f"{c.value!r}@{c.anchor.document}" for c in cands
                        )
                    ),
                    candidates=list(cands),
                )
            )
            continue  # do not enter a mismatched fact into the graph
        accepted[slot] = best

    return accepted, reviews
