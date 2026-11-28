"""The picker hook, run by scripts/check-ask.sh, and the post hook, run by
scripts/check-post.sh, each with Claude Code's PreToolUse payload on standard
input (inquisitor spec: *A hook blocks a picker question that was not
vetted*; *Questions in posts pass the same filters*; *The post hook vets
what the shared post reader returns*).

Each returns 0 to let the call through, or 2 to block it with its message
on stderr, which Claude Code shows the model. The picker hook fails open:
when it cannot read the call, the call goes through, and when it cannot
read the verdict records, only a credential in a question blocks it.
The post hook reads a payload that is not a JSON object as no call that
may post, and lets it through. It fails closed on every call that may post: anything it cannot check
blocks, since a published post cannot be taken back.

Standard library only.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from calls import read_records
from contracts import VerdictRecord
from credentials import matches_credentials
from qtext import (PERSON_REQUIRED_FORMAT, RELATED_PREFIX, UNTAGGED_LINE, FoundQuestion, Question,
                   find_questions, line_kind, mentions, question_hash, question_text,
                   reduce_markup)
from service.relay import RESERVED_PREFIXES

# The shared post reader lives in this repository's .agents/lib/gh-shell/,
# three folders above scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib" / "gh-shell"))
import post_reader  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "inquisitor.py"
FIRST_CALL_PICKER = f"python3 -I {SCRIPT} vet --questions <file|->"
FIRST_CALL_POST = f"python3 -I {SCRIPT} vet --post <file>"


def _field(record: VerdictRecord) -> str:
    """A verdict record's `field` value as `key: value` pairs, for a block
    message."""
    field = record.get("field")
    if not field:
        return ""
    pairs = cast(dict[str, str], field)
    return " (" + "; ".join(f"{key}: {value}" for key, value in pairs.items()) + ")"


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0]


# -- the picker hook -----------------------------------------------------------

def _picker_questions(payload: Any) -> list[Question] | None:
    """Each question of an AskUserQuestion call, or None when the payload
    is not one the hook can read."""
    if not isinstance(payload, dict):
        return None
    tool_input = cast(dict[str, Any], payload).get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    items = cast(dict[str, Any], tool_input).get("questions")
    if not isinstance(items, list):
        return None
    questions: list[Question] = []
    for item in cast(list[Any], items):
        if not isinstance(item, dict):
            return None
        q = cast(dict[str, Any], item)
        text = q.get("question")
        options = q.get("options", [])
        if not isinstance(text, str) or not isinstance(options, list):
            return None
        labels: list[str] = []
        for option in cast(list[Any], options):
            label = cast(dict[str, Any], option).get("label") if isinstance(option, dict) else None
            if not isinstance(label, str):
                return None
            labels.append(label)
        questions.append(Question("picker", text, tuple(labels)))
    return questions


def ask_problems(raw: str) -> list[str]:
    """Why the picker hook blocks the call: a line for each question that
    fails, then, when a verdict is missing or is anything but ask, the
    command to run. Empty to let the call through. A credential in a
    question or one of its options blocks whatever the records hold; only the checks that need the verdict
    records fail open, when the records cannot be read."""
    try:
        questions = _picker_questions(json.loads(raw))
    except ValueError:
        return []
    if not questions:
        return []
    texts = [question_text(q) for q in questions]
    problems: list[str] = []
    clean: list[tuple[str, str]] = []
    for n, (q, text) in enumerate(zip(questions, texts), 1):
        name = f"question {n} ({_first_line(text)!r})"
        if any(matches_credentials(part) for part in (q.question, *q.options)):
            problems.append(f"{name} holds a string shaped like a credential, its "
                            "related-decision line included: take it out")
        else:
            clean.append((name, text))
    try:
        records = read_records({question_hash(t) for _, t in clean}) if clean else {}
    except Exception:  # noqa: BLE001 - the record checks fail open
        records = None
    if records is None:
        return problems
    unvetted = False
    for name, text in clean:
        record = records.get(question_hash(text))
        if record is None:
            problems.append(f"{name} has no verdict from the last 2 hours: vet it, or vet it "
                            "again if its text changed after vetting")
        elif record["verdict"] != "ask":
            problems.append(f"{name}: its latest verdict is {record['verdict']}{_field(record)}, "
                            "so it is not asked")
        else:
            continue
        unvetted = True
    if unvetted:
        problems.append(f"Run the two calls on each question named: {FIRST_CALL_PICKER}, then "
                        "the second call it prints.")
    return problems


def run_ask(payload: str) -> int:
    """0 to let the call through, 2 to block it with the message on stderr.
    Fails open."""
    try:
        problems = ask_problems(payload)
    except Exception:  # noqa: BLE001 - the picker hook fails open
        return 0
    if not problems:
        return 0
    sys.stderr.write("inquisitor: blocked this picker call.\n"
                     + "".join(f"  - {p}\n" for p in problems))
    return 2


# -- the post hook -------------------------------------------------------------

LINEAR_ELSEWHERE = "ask it in an issue's description or a comment"


@dataclass(frozen=True)
class _Vetted:
    """One body's question with its hash."""

    found: FoundQuestion
    text: str
    hash: str


def _reserved(body: str) -> str | None:
    start = reduce_markup(body).lstrip()
    return next((p for p in RESERVED_PREFIXES if start.startswith(p)), None)


def _title_problems(post: post_reader.Post) -> list[str]:
    found = find_questions(post.body, in_code=True)
    if not found:
        return []
    where = (LINEAR_ELSEWHERE if post.surface == "linear"
             else "ask it in the post's body instead")
    return [f"{post.where}: the title {question_text(f.question)!r} holds a question, and "
            f"only a post's body is vetted: {where}" for f in found]


def _summary_problems(post: post_reader.Post) -> list[str]:
    return [f"{post.where}: Linear summary text holds the question "
            f"{question_text(f.question)!r}, and the answer service reads no such text: "
            f"{LINEAR_ELSEWHERE}" for f in find_questions(post.body)]


def _credential_problems(post: post_reader.Post, found: list[FoundQuestion]) -> list[str]:
    """vet's first call's credential scan, again just before the post goes
    out (inquisitor spec: *The credential scan reads raw markdown*): each
    question's raw markdown and its extra lines, such as its Related and
    tag lines, and every line of the body starting `Related:` or `@`."""
    problems = [f"{post.where}: the question {question_text(f.question)!r} holds a string shaped "
                "like a credential, link targets included: take it out"
                for f in found if matches_credentials("\n".join((f.raw, *f.lines)))]
    if any(line.strip().startswith((RELATED_PREFIX.strip(), "@")) and matches_credentials(line)
           for line in post.body.splitlines()):
        problems.append(f"{post.where}: a Related or tag line holds a string shaped like a "
                        "credential: take it out")
    return problems


_INTERRUPTS = re.compile(r"\s*(?:[-*+]|\d{1,9}[.)])(?:\s|$)|\s*#{1,6}(?:\s|$)|\s*(?:`{3,}|~{3,})"
                         r"|\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")


def _width(line: str) -> int:
    """How many columns of whitespace the line starts with, with a tab
    stop every 4 columns."""
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _item_span(lines: list[str], at: tuple[int, ...]) -> list[int]:
    """The lines of the list item that starts at at[0], as GitHub shows it.
    find_questions ends an item at a fence or a `>` line inside it, but a
    mention further into the item still tags the question, so the post hook
    finds the item's lines again here, leaning toward taking a line in. A
    line belongs while it is blank, indented at least 2 columns past the
    marker's indent, or continues a paragraph lazily. The item ends at a
    later item, heading, fence or thematic break (`---`) indented less than
    that, or at any line indented less than that after a blank line."""
    if not at:
        return []
    start = at[0]
    marker = _width(lines[start])
    span = [start]
    blank = False
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            blank = True
            span.append(i)
            continue
        if _width(line) >= marker + 2:
            span.append(i)
        elif blank or _INTERRUPTS.match(line):
            break
        else:
            span.append(i)
        blank = False
    return sorted(set(span) | set(at))


def _verdict_problem(post: post_reader.Post, q: _Vetted, record: VerdictRecord | None,
                     mentioned: set[int]) -> str | None:
    """Why one question blocks the post, or None. mentioned holds the
    index of each line of the post's body that mentions a user."""
    name = f"{post.where}: the question {_first_line(q.text)!r}"
    if record is None:
        return (f"{name} has no verdict from the last 2 hours: vet it with {FIRST_CALL_POST}, or "
                "again if it was vetted over 2 hours ago or its text changed")
    if "category" in record:
        return (f"{name} was recorded with the category {record['category']}, which no post may "
                "hold: ask the person directly, through the picker, or for a vulnerability in "
                "the repository's private security advisory")
    verdict = record["verdict"]
    found = q.found
    # The fixed untagged line is a tag line that tags no one (inquisitor spec:
    # *A question no one can decide is posted untagged*).
    # An item tags the login on each of its tag lines, and whom any other
    # line of its span mentions (inquisitor spec, Purpose: *A question
    # tags*), except that a mention on a Related, person-required or
    # Concerns line tags no one.
    body_lines = post.body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tagged = (any(line_kind(line) == "tag" and line.strip() != UNTAGGED_LINE
                  for line in found.lines)
              or any(i in mentioned
                     and line_kind(body_lines[i]) not in ("related", "person-required", "concerns")
                     for i in _item_span(body_lines, found.at)))
    if verdict == "ask":
        if found.deferred:
            return (f"{name} is listed under a deferral label with an ask verdict: a question "
                    "the post asks belongs under a question label such as \"Open questions\"")
    elif verdict == "deferred":
        if not found.deferred:
            return (f"{name} has a deferred verdict but is asked outside a deferral label such as "
                    "\"Not in this change\": it needs an ask verdict")
        if tagged:
            return f"{name} is listed as deferred but tags someone: it needs an ask verdict"
    elif verdict == "not asked":
        if not found.in_code:
            return (f"{name} was recorded not asked, which passes only in code or an HTML "
                    "comment, and here it is in running text: it needs an ask verdict")
    else:
        return f"{name}: its latest verdict is {verdict}{_field(record)}, so it is not asked"
    requires = record.get("requires")
    carried = [line.strip() for line in found.lines if line_kind(line) == "person-required"]
    if requires is not None and carried != [PERSON_REQUIRED_FORMAT.format(skill=requires)]:
        return (f"{name} needs its person-required line, exactly "
                f"{PERSON_REQUIRED_FORMAT.format(skill=requires)!r}, directly after it")
    if requires is None and carried:
        return (f"{name} carries a person-required line, but its verdict names no skill that "
                "requires it: take the line out")
    identity = record.get("identity")
    if identity is not None and not post.via_github_app:
        return (f"{name} was tagged for a post by the github-app identity {identity!r}: post it "
                f"through github-app's script, python3 <path>/github_app.py --identity "
                f"{identity} gh …")
    return None


def _body_problems(posts: list[post_reader.Post]) -> list[str]:
    problems: list[str] = []
    pending: list[tuple[post_reader.Post, _Vetted]] = []
    mentioned: dict[int, set[int]] = {}
    for post in posts:
        mentioned[id(post)] = {m.line for m in mentions(post.body, post.surface == "discord")}
        found = find_questions(post.body, in_code=True)
        problems += _credential_problems(post, found)
        for f in found:
            text = question_text(f.question)
            pending.append((post, _Vetted(f, text, question_hash(text))))
    if not pending:
        return problems
    records = read_records({q.hash for _, q in pending})
    if records is None:
        return problems + ["the verdict records cannot be read, and this post holds a question; "
                           "a published post cannot be taken back, so it is blocked"]
    for post, q in pending:
        problem = _verdict_problem(post, q, records.get(q.hash), mentioned[id(post)])
        if problem is not None:
            problems.append(problem)
    return problems


def post_problems(raw: str) -> list[str]:
    """Why the post hook blocks the call; empty to let it through."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    result = post_reader.read_posts(cast(dict[str, Any], payload), "claude")
    if isinstance(result, post_reader.Unreadable):
        return [result.why]
    if isinstance(result, post_reader.NoPost):
        return []
    problems: list[str] = []
    bodies: list[post_reader.Post] = []
    for post in result:
        if post.title:
            problems += _title_problems(post)
            continue
        prefix = _reserved(post.body)
        if prefix is not None:
            problems.append(f"{post.where}: it starts with {prefix.strip()!r}, a prefix only the "
                            "answer service's relay posts may start with")
        if post.summary_text:
            problems += _summary_problems(post)
        else:
            bodies.append(post)
    return problems + _body_problems(bodies)


def run_post(payload: str) -> int:
    """0 to let the post through, 2 to block it. Reads posts only through
    the shared post reader (.agents/lib/gh-shell/post_reader.py). A payload
    that is not a JSON object passes; on any other, an error blocks."""
    try:
        problems = post_problems(payload)
    except Exception as e:  # noqa: BLE001 - the post hook fails closed
        problems = [f"the hook failed ({type(e).__name__}: {e}), so the post cannot be checked"]
    if not problems:
        return 0
    sys.stderr.write("inquisitor: blocked this post.\n" + "".join(f"  - {p}\n" for p in problems))
    return 2
