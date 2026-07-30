"""PED / non-disclosure ground — the fully specified reference implementation
(ARCHITECTURE.md Section 6). Levers L1-L7, deterministic predicates (Section
6.3), and the parametric inputs the assertion templates consume.

This module is pure and deterministic: no LLM, no I/O. It takes a Case plus a
CitationStore and returns which predicates are TRUE, with the supporting
arithmetic exposed for the validator to independently recompute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..citations import CitationStore
from ..dateutil import months_between
from ..slots import Case, ProposalFilledBy
from ..verdict import Strength


@dataclass(frozen=True)
class Lever:
    id: str
    name: str
    strength: Strength
    predicate: str  # key into the predicate result set


# Section 6.1. STRONG levers are each dispositive alone; MODERATE levers are
# strong support, best combined.
LEVERS: dict[str, Lever] = {
    "L1": Lever("L1", "Moratorium bar", Strength.STRONG, "moratorium_met"),
    "L2": Lever("L2", "Not actually pre-existing", Strength.STRONG, "diagnosis_post_incept"),
    "L3": Lever("L3", "No nexus", Strength.STRONG, "nexus_absent"),
    "L7": Lever("L7", "PED waiting served", Strength.STRONG, "ped_waiting_served"),
    "L4": Lever("L4", "Not material / not asked", Strength.MODERATE, "not_asked"),
    "L6": Lever("L6", "Agent-filled form", Strength.MODERATE, "agent_defense"),
    "L5": Lever("L5", "Burden & awareness", Strength.MODERATE, "not_aware"),
}

# Predicate -> lever, for reverse lookup.
LEVER_BY_PREDICATE: dict[str, Lever] = {lv.predicate: lv for lv in LEVERS.values()}

STRONG_PREDICATES = ("moratorium_met", "diagnosis_post_incept", "ped_waiting_served", "nexus_absent")
MODERATE_PREDICATES = ("not_asked", "agent_defense", "not_aware")


@dataclass
class PredicateResult:
    key: str
    value: Optional[bool]  # None == cannot be evaluated (missing slots)
    detail: str

    @property
    def fired(self) -> bool:
        return self.value is True


@dataclass
class Evaluation:
    predicates: dict[str, PredicateResult]
    support: dict[str, Any] = field(default_factory=dict)  # exposed arithmetic

    def fired_predicates(self) -> list[str]:
        return [k for k, r in self.predicates.items() if r.fired]


def _need(case: Case, *names: str) -> bool:
    return all(case.is_filled(n) for n in names)


def evaluate(case: Case, citations: CitationStore, relevant_date: date) -> Evaluation:
    """Evaluate every PED predicate over the filled slots (Section 6.3).

    `relevant_date` selects the citation version (Section 9) — the moratorium and
    PED-waiting-cap values are date-versioned law, not constants.
    """
    p: dict[str, PredicateResult] = {}
    support: dict[str, Any] = {"relevant_date": relevant_date}

    moratorium_months = citations.resolve("MORATORIUM", relevant_date).value
    ped_cap_months = citations.resolve("PED_WAITING_CAP", relevant_date).value
    support["moratorium_months"] = moratorium_months
    support["ped_cap_months"] = ped_cap_months

    # --- L1: moratorium bar -------------------------------------------------
    if _need(case, "continuous_coverage_start", "denial_date"):
        coverage_months = months_between(
            case.value("continuous_coverage_start"), case.value("denial_date")
        )
        support["coverage_months"] = coverage_months
        breaks = bool(case.value("continuity_breaks", False))
        fraud = bool(case.value("fraud_proven", False))
        met = coverage_months >= moratorium_months and not breaks and not fraud
        detail = (
            f"{coverage_months} months continuous coverage vs {moratorium_months}-month "
            f"moratorium; continuity_breaks={breaks}; fraud_proven={fraud}"
        )
        p["moratorium_met"] = PredicateResult("moratorium_met", met, detail)
    else:
        p["moratorium_met"] = PredicateResult(
            "moratorium_met", None, "missing coverage_start/denial_date"
        )

    # --- L2: not actually pre-existing --------------------------------------
    if _need(case, "first_diagnosis_date", "policy_inception_date"):
        dx = case.value("first_diagnosis_date")
        inc = case.value("policy_inception_date")
        val = dx > inc
        p["diagnosis_post_incept"] = PredicateResult(
            "diagnosis_post_incept",
            val,
            f"first diagnosis {dx.isoformat()} vs inception {inc.isoformat()}",
        )
    else:
        p["diagnosis_post_incept"] = PredicateResult(
            "diagnosis_post_incept", None, "missing first_diagnosis_date/inception"
        )

    # --- L7: PED waiting served (capped at 36 months) -----------------------
    if _need(case, "continuous_coverage_start", "denial_date", "ped_waiting_months"):
        coverage_months = support["coverage_months"]
        policy_waiting = case.value("ped_waiting_months")
        effective_waiting = min(policy_waiting, ped_cap_months)
        support["effective_ped_waiting"] = effective_waiting
        val = coverage_months >= effective_waiting
        p["ped_waiting_served"] = PredicateResult(
            "ped_waiting_served",
            val,
            f"{coverage_months} months coverage vs effective PED waiting "
            f"{effective_waiting} (policy {policy_waiting}, cap {ped_cap_months})",
        )
    else:
        p["ped_waiting_served"] = PredicateResult(
            "ped_waiting_served", None, "missing coverage/ped_waiting_months"
        )

    # --- L3: no nexus -------------------------------------------------------
    # The nexus graph is M5; until it exists a fired L3 requires an explicit,
    # human-supplied ruling. Absent that, the lever cannot fire (never guessed).
    if case.is_filled("nexus_absent"):
        val = bool(case.value("nexus_absent"))
        p["nexus_absent"] = PredicateResult(
            "nexus_absent", val, "human-supplied nexus ruling (graph pending M5)"
        )
    else:
        p["nexus_absent"] = PredicateResult(
            "nexus_absent", None, "no nexus ruling; graph not yet built (M5)"
        )

    # --- L4: not material / not asked ---------------------------------------
    if case.is_filled("was_condition_asked"):
        val = case.value("was_condition_asked") is False
        p["not_asked"] = PredicateResult(
            "not_asked", val, f"was_condition_asked={case.value('was_condition_asked')}"
        )
    else:
        p["not_asked"] = PredicateResult("not_asked", None, "missing was_condition_asked")

    # --- L6: agent-filled form ----------------------------------------------
    if _need(case, "proposal_filled_by", "disclosed_verbally"):
        filled_by = case.value("proposal_filled_by")
        disclosed = bool(case.value("disclosed_verbally"))
        val = filled_by != ProposalFilledBy.SELF and disclosed
        p["agent_defense"] = PredicateResult(
            "agent_defense",
            val,
            f"proposal_filled_by={filled_by.value}; disclosed_verbally={disclosed}",
        )
    else:
        p["agent_defense"] = PredicateResult(
            "agent_defense", None, "missing proposal_filled_by/disclosed_verbally"
        )

    # --- L5: burden & awareness (not aware) ---------------------------------
    if case.is_filled("aware_at_proposal"):
        val = case.value("aware_at_proposal") is False
        p["not_aware"] = PredicateResult(
            "not_aware", val, f"aware_at_proposal={case.value('aware_at_proposal')}"
        )
    else:
        p["not_aware"] = PredicateResult("not_aware", None, "missing aware_at_proposal")

    return Evaluation(predicates=p, support=support)
