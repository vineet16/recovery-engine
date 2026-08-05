"""The leashed narrator (ARCHITECTURE.md Section 10).

Two jobs only: **render** the question for the graph-selected slot, and
**interpret** a freeform answer into that slot's schema. It may rephrase (depth),
never introduce a topic or advice (breadth). Guards enforce the leash; every turn
is logged, and that log *is* the audit trail.

The LLM is optional. With no client, rendering uses the scripted prompt and
parsing is deterministic. With a client, the LLM may rephrase (subject to the
pre-send guard) and interpret genuinely freeform answers — but the result is
always re-validated through the deterministic coercion, so the model never
smuggles a value past the schema.

Rephrasing is additionally withheld from yes/no questions, whose polarity the
model can invert without tripping any on-topic guard; see
`_POLARITY_BEARING_KINDS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from .interview import SlotQuestion
from .llm.base import ChatError, LLMClient
from .parser.schema import DATE_RE, coerce_date
from .slots import SLOT_SPECS, Case

_ADVICE_MARKERS = (
    "you should", "i recommend", "we recommend", "i advise", "i suggest",
    "you must", "you ought", "in my opinion", "my advice", "you could try",
)
_YES = {"yes", "y", "yeah", "yep", "correct", "true", "right", "sure", "did", "i did", "i was", "i am"}
_NO = {"no", "n", "nope", "nah", "false", "never", "didn't", "did not", "i didn't", "wasn't", "i wasn't"}

_MONTH_FIRST_FORMATS = ("%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y")

# Yes/no questions are never LLM-rephrased: their meaning lives in their polarity,
# and a rephrase can invert it while staying perfectly on-topic. Observed: "has
# there been any gap or break in your renewals?" came back as "have you had
# continuous coverage ... without any breaks?" — same subject, opposite sense, so
# a truthful "yes" would record continuity_breaks=True for an unbroken policy and
# silently drop the L1 moratorium lever. `pre_send_ok` cannot catch this (topic
# keywords match either way), so the leash here is structural, not heuristic.
# Dates and enums carry no polarity and are still rephrased for depth; answer
# *interpretation* stays LLM-assisted for every kind, since the policyholder
# always saw the scripted wording.
_POLARITY_BEARING_KINDS = frozenset({"bool"})


@dataclass
class TurnLogEntry:
    active_ground: str
    target_slot: str
    generated_question: str
    raw_answer: Optional[str]
    parsed_value: Any


@dataclass
class ParseOutcome:
    value: Any
    ok: bool
    needs_reask: bool = False
    detail: str = ""


def pre_send_ok(text: str, q: SlotQuestion) -> bool:
    """Guard: the question stays on its slot, asks one thing, gives no advice."""
    low = text.lower()
    if any(m in low for m in _ADVICE_MARKERS):
        return False
    if text.count("?") != 1:
        return False  # exactly one question, one slot
    return any(k in low for k in q.topic_keywords)


def _freeform_date(raw: str) -> Optional[date]:
    s = raw.strip()
    try:
        return coerce_date(s)
    except ValueError:
        pass
    for fmt in _MONTH_FIRST_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.search(DATE_RE, s)
    if m:
        try:
            return coerce_date(m.group(0))
        except ValueError:
            return None
    return None


def _freeform_bool(raw: str) -> Optional[bool]:
    low = raw.strip().lower()
    if low in _YES:
        return True
    if low in _NO:
        return False
    # leading token
    first = re.split(r"[\s,.!]", low, maxsplit=1)[0]
    if first in _YES:
        return True
    if first in _NO:
        return False
    if "no gap" in low or "continuous" in low or "without" in low:
        return False
    return None


class Narrator:
    def __init__(self, ground: str = "PED", llm: Optional[LLMClient] = None):
        self.ground = ground
        self.llm = llm if (llm is not None and getattr(llm, "available", False)) else None
        self.turns: list[TurnLogEntry] = []

    # --- render ------------------------------------------------------------
    def render_question(self, q: SlotQuestion, case: Case) -> str:
        cited = case.value("cited_condition") or "the cited condition"
        scripted = q.prompt.format(cited_condition=cited)

        text = scripted
        if self.llm is not None and q.kind not in _POLARITY_BEARING_KINDS:
            try:
                candidate = self._llm_rephrase(scripted, q)
                if candidate and pre_send_ok(candidate, q):
                    text = candidate
            except ChatError:
                text = scripted  # fall back to scripted default phrasing

        if not pre_send_ok(text, q):  # scripted itself must pass
            text = scripted
        return text

    def _llm_rephrase(self, scripted: str, q: SlotQuestion) -> str:
        system = (
            "You rephrase a single interview question for an insurance-claim "
            "assistant. Rules: keep the exact same meaning; ask about ONE thing "
            "only; do NOT give advice, opinions, or any additional question; do "
            "NOT introduce new topics. Return only the rephrased question."
        )
        return self.llm.complete(system, scripted, temperature=0.3, max_tokens=120).strip()

    # --- interpret ---------------------------------------------------------
    def parse_answer(self, q: SlotQuestion, raw: str, case: Case) -> ParseOutcome:
        value = self._deterministic_parse(q, raw)
        if value is None and self.llm is not None:
            value = self._llm_extract(q, raw)  # re-validated below
        if value is None:
            return ParseOutcome(None, ok=False, needs_reask=True, detail="unparsed")

        if q.invert_bool and isinstance(value, bool):
            value = not value
        try:
            spec = SLOT_SPECS.get(q.slot)
            if spec is not None:
                spec.check(value)
        except (TypeError, ValueError) as exc:
            return ParseOutcome(None, ok=False, needs_reask=True, detail=str(exc))
        return ParseOutcome(value, ok=True)

    def _deterministic_parse(self, q: SlotQuestion, raw: str) -> Any:
        if q.kind == "bool":
            return _freeform_bool(raw)
        if q.kind == "date":
            return _freeform_date(raw)
        if q.kind == "enum" and q.enum_map:
            low = raw.strip().lower()
            for key, val in q.enum_map.items():
                if key in low:
                    return val
        return None

    def _llm_extract(self, q: SlotQuestion, raw: str) -> Any:
        """Ask the LLM to normalise a freeform answer, then re-coerce it.

        The LLM output is never trusted directly: it is fed straight back through
        the deterministic parser, so only a schema-valid value can survive.
        """
        if q.kind == "bool":
            system = "Answer strictly 'yes', 'no', or 'unknown'. No other words."
        elif q.kind == "date":
            system = "Extract the single date. Reply as DD/MM/YYYY only, or 'unknown'."
        else:
            system = "Reply with exactly one of: self, agent, other, unknown."
        try:
            out = self.llm.complete(system, raw, temperature=0.0, max_tokens=16).strip()
        except ChatError:
            return None
        if out.lower().startswith("unknown"):
            return None
        return self._deterministic_parse(q, out)

    # --- logging -----------------------------------------------------------
    def log(self, slot: str, question: str, raw: Optional[str], parsed: Any) -> None:
        self.turns.append(TurnLogEntry(self.ground, slot, question, raw, parsed))
