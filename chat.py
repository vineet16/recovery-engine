"""Interactive Stage 0-4 session — the conversation, not just the output.

`demo.py` scripts the answers and prints the turn log afterwards. This runs the
same `run_session()` against a live human: real PDFs are parsed first, the graph
picks which slots are still missing, and the narrator asks only for those. The
turn log at the end shows what each freeform answer coerced to, so the "typed,
source-anchored slots" claim is auditable rather than asserted.

With an LLM configured, note which questions get rephrased and which do not:
dates and enums are reworded, yes/no questions are always verbatim, because a
rephrase can invert their polarity (see `_POLARITY_BEARING_KINDS` in narrator.py).

  python chat.py            # contested policy: the interview decides the case
  python chat.py --strong   # long-standing policy: documents alone win it

Blank answer = "I don't know"; the graph moves on rather than pressing.
Set LLM_PROVIDER/*_API_KEY to let the narrator rephrase and interpret freeform
answers (see README). Without a key it is fully deterministic.
"""

from __future__ import annotations

import sys
from datetime import date

sys.path.insert(0, "src")

from recovery_engine import run_session  # noqa: E402
from recovery_engine.letter import Decline  # noqa: E402
from recovery_engine.llm import from_env  # noqa: E402
from recovery_engine.llm.base import ChatError  # noqa: E402
from recovery_engine.narrator import Narrator  # noqa: E402
from recovery_engine.parser import DocType, SourceDoc, parse_documents  # noqa: E402
from recovery_engine.parser.fixtures import (  # noqa: E402
    denial_letter_pdf,
    policy_schedule_pdf,
)

RULE = "=" * 78
_TTY = sys.stdout.isatty()  # keep escapes out of piped/recorded transcripts
DIM = "\033[2m" if _TTY else ""
BOLD = "\033[1m" if _TTY else ""
RESET = "\033[0m" if _TTY else ""

# A recently-bought policy: the documents alone cannot clear the moratorium, so
# the case genuinely turns on the interview. --strong uses a 2018 policy, where
# the parse wins it outright and the graph asks almost nothing.
CONTESTED = dict(inception="01/06/2024", coverage_start="01/06/2024",
                 denial="01/06/2025", as_of=date(2025, 6, 15))
LONGSTANDING = dict(inception="01/03/2018", coverage_start="01/03/2018",
                    denial="20/02/2025", as_of=date(2025, 3, 1))


def parse_the_documents(scenario: dict):
    docs = [
        SourceDoc("denial.pdf", DocType.DENIAL_LETTER,
                  pdf_bytes=denial_letter_pdf(denial_date=scenario["denial"],
                                              cited_condition="diabetes mellitus")),
        SourceDoc("policy.pdf", DocType.POLICY_SCHEDULE,
                  pdf_bytes=policy_schedule_pdf(inception=scenario["inception"],
                                                coverage_start=scenario["coverage_start"])),
    ]
    print(f"{RULE}\nReading your documents…\n{'-' * 78}")
    report = parse_documents(docs)
    for slot, ef in sorted(report.fields.items()):
        val = ef.value.isoformat() if hasattr(ef.value, "isoformat") else ef.value
        print(f"  {slot:26} = {str(val):26} {DIM}@{ef.confidence:.2f} "
              f"[{ef.anchor.document} p{ef.anchor.page}]{RESET}")
    if report.reviews:
        print(f"  {DIM}{len(report.reviews)} field(s) queued for human review{RESET}")
    print(f"\n{DIM}Everything above came from the PDFs. Anything the case still needs,\n"
          f"the graph will ask for — and only that.{RESET}\n")
    return report.case


def interactive_answers(case):
    """AnswerProvider: (slot, question) -> raw answer or None.

    The loop re-calls this with the same question when a parse fails, so track
    attempts per slot to soften the re-ask instead of repeating verbatim.
    """
    seen: dict[str, int] = {}

    def ask(slot: str, question: str):
        seen[slot] = seen.get(slot, 0) + 1
        if seen[slot] > 1:
            # Formats verified against narrator._freeform_date — a month/year
            # like "09/2024" does NOT parse, so don't suggest it.
            print(f"{DIM}   (didn't catch that — try 15/09/2024, "
                  f"15 September 2024, or 2024-09-15; Enter to skip){RESET}")
        else:
            print(f"{BOLD}?{RESET} {question}")
        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            print(f"{DIM}   → skipped{RESET}\n")
            return None
        print()  # breathing room between turns when this is on screen
        return raw

    return ask


def narrator_status(llm) -> str:
    """Probe the client so a silently-failing key can't masquerade as LLM-assisted.

    `render_question` swallows ChatError and falls back to the scripted prompt —
    correct behaviour, but it means a dead key looks identical to a working one.
    Say which it is, out loud, before the interview starts.
    """
    if llm is None:
        return "deterministic (no API key configured)"
    label = f"{llm._config.provider}/{llm._config.model}"
    try:
        llm.complete("Reply with one word.", "Say hello.", max_tokens=8)
    except ChatError as exc:
        return (f"deterministic — {label} configured but UNREACHABLE "
                f"({str(exc).splitlines()[0][:70]}); scripted prompts in use")
    return f"LLM-assisted ({label})"


def report(res) -> None:
    print(f"{RULE}\nWhat the graph decided\n{'-' * 78}")
    print(f"  Stage reached  : {res.stage_reached.name}")
    print(f"  Eligibility    : {res.eligibility.status} "
          f"({'; '.join(res.eligibility.reasons)})")
    print(f"  Verdict        : {res.findings.verdict.label}   "
          f"levers {res.findings.fired_levers or '—'}")
    if res.filing_target:
        print(f"  Files with     : {res.filing_target.value}")
    if res.deadlines and res.deadlines.ombudsman_cliff:
        print(f"  Ombudsman cliff: {res.deadlines.ombudsman_cliff} "
              f"({res.deadlines.days_to_cliff()} days left)")
    print(f"  Ships          : {res.shippable}")
    # shippable also requires zero evidence gaps, so an unexplained False here
    # reads as a bug when it is actually §13.3 doing its job.
    for gap in res.evidence_gaps:
        print(f"  {DIM}└ blocked: {gap.message}{RESET}")

    if res.turn_log:
        print(f"\n{DIM}Audit trail — every question asked, and what it recorded:{RESET}")
        for t in res.turn_log:
            val = t.parsed_value.isoformat() if hasattr(t.parsed_value, "isoformat") \
                else t.parsed_value
            print(f"  {DIM}[{t.target_slot}]{RESET} {t.raw_answer!r} → {val!r}")

    if res.filing is None:
        print("\nNo filing produced.")
        return
    kind = "Honest decline" if isinstance(res.filing, Decline) else "Filing"
    print(f"\n{RULE}\n{kind}\n{'-' * 78}")
    print(res.filing.render())
    if res.violations:
        print(f"\n{DIM}Gate violations: {res.violations}{RESET}")


def main() -> None:
    scenario = LONGSTANDING if "--strong" in sys.argv else CONTESTED
    case = parse_the_documents(scenario)

    llm = from_env()
    print(f"{DIM}Narrator: {narrator_status(llm)}{RESET}\n")

    res = run_session(
        case,
        answers=interactive_answers(case),
        provided_docs={DocType.DISCHARGE_SUMMARY, DocType.POLICY_SCHEDULE},
        as_of=scenario["as_of"],
        narrator=Narrator("PED", llm=llm),
    )
    report(res)


if __name__ == "__main__":
    main()
