"""M3 narrator: leash guards, deterministic parsing, turn log (Section 10)."""

from __future__ import annotations

from datetime import date

from recovery_engine import Narrator
from recovery_engine.interview import PED_INTERVIEW_BY_SLOT
from recovery_engine.narrator import pre_send_ok
from recovery_engine.slots import Case, ProposalFilledBy


def _case():
    return Case("C").set("cited_condition", "diabetes mellitus")


def test_scripted_question_references_only_the_slot():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["first_diagnosis_date"]
    text = n.render_question(q, _case())
    assert "diabetes mellitus" in text
    assert pre_send_ok(text, q)


def test_pre_send_guard_rejects_advice():
    q = PED_INTERVIEW_BY_SLOT["aware_at_proposal"]
    assert not pre_send_ok("You should say you were not aware — were you aware?", q)


def test_pre_send_guard_rejects_second_question():
    q = PED_INTERVIEW_BY_SLOT["aware_at_proposal"]
    assert not pre_send_ok("Were you aware? Also, who is your agent?", q)


def test_pre_send_guard_rejects_off_topic():
    q = PED_INTERVIEW_BY_SLOT["aware_at_proposal"]
    assert not pre_send_ok("What is your policy number?", q)


def test_parse_bool_yes_no():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["was_condition_asked"]
    assert n.parse_answer(q, "Yes", _case()).value is True
    assert n.parse_answer(q, "no, it didn't", _case()).value is False


def test_parse_date_freeform():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["first_diagnosis_date"]
    assert n.parse_answer(q, "12/03/2022", _case()).value == date(2022, 3, 12)
    assert n.parse_answer(q, "diagnosed on 5 June 2021", _case()).value == date(2021, 6, 5)


def test_parse_enum_proposal_filled_by():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["proposal_filled_by"]
    assert n.parse_answer(q, "the agent did it", _case()).value == ProposalFilledBy.AGENT
    assert n.parse_answer(q, "I filled it myself", _case()).value == ProposalFilledBy.SELF


def test_continuity_bool_is_inverted():
    # "no gap" -> continuity_breaks == False
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["continuity_breaks"]
    out = n.parse_answer(q, "no, no gap at all", _case())
    assert out.value is False


def test_unparseable_answer_requests_reask():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["first_diagnosis_date"]
    out = n.parse_answer(q, "sometime a while ago", _case())
    assert not out.ok and out.needs_reask


class _InvertingLLM:
    """Stands in for a model that rephrases on-topic but flips the polarity."""

    available = True

    def __init__(self):
        self.calls = 0

    def complete(self, system, user, *, temperature=0.0, max_tokens=512):
        self.calls += 1
        return (
            "Have you had continuous coverage since the policy started, "
            "without any breaks in renewal?"
        )


def test_bool_questions_are_never_llm_rephrased():
    """Polarity-bearing questions must ship scripted, whatever the model says.

    The inverted rephrase passes pre_send_ok (its topic keywords match), so only
    the structural leash keeps a truthful "yes" from recording the opposite fact.
    """
    llm = _InvertingLLM()
    n = Narrator(llm=llm)
    q = PED_INTERVIEW_BY_SLOT["continuity_breaks"]

    text = n.render_question(q, _case())

    assert text == q.prompt.format(cited_condition="diabetes mellitus")
    assert llm.calls == 0, "bool questions must not reach the model at all"
    # The guard alone would have let the inversion through:
    assert pre_send_ok(llm.complete("", ""), q)


def test_non_bool_questions_still_reach_the_llm():
    class _Rephraser:
        available = True

        def complete(self, system, user, *, temperature=0.0, max_tokens=512):
            return "What date was diabetes mellitus first diagnosed on record?"

    n = Narrator(llm=_Rephraser())
    q = PED_INTERVIEW_BY_SLOT["first_diagnosis_date"]
    assert n.render_question(q, _case()) == (
        "What date was diabetes mellitus first diagnosed on record?"
    )


def test_bool_answers_are_still_llm_interpreted():
    """Only rendering is withheld for bools; interpretation stays LLM-assisted."""

    class _YesSayer:
        available = True

        def complete(self, system, user, *, temperature=0.0, max_tokens=512):
            return "yes"

    n = Narrator(llm=_YesSayer())
    q = PED_INTERVIEW_BY_SLOT["was_condition_asked"]
    # Defeats the deterministic yes/no lists, so it falls through to the model.
    out = n.parse_answer(q, "they absolutely did put that on the form", _case())
    assert out.ok and out.value is True


def test_turn_log_is_the_audit_trail():
    n = Narrator()
    q = PED_INTERVIEW_BY_SLOT["was_condition_asked"]
    text = n.render_question(q, _case())
    n.log(q.slot, text, "no", False)
    entry = n.turns[-1]
    assert entry.target_slot == "was_condition_asked"
    assert entry.parsed_value is False
    assert entry.active_ground == "PED"
