"""The picker hook and the post hook, run by scripts/check-ask.sh and
scripts/check-post.sh with Claude Code's PreToolUse payload on standard
input (inquisitor spec: *A hook blocks a picker question that was not
vetted*; *Questions in posts pass the same filters*; *The post hook vets
what the shared post reader returns*).

Each returns 0 to let the call through, or 2 to block it with its message
on stderr, which Claude Code shows the model. The picker hook fails open:
when it cannot read the call or the verdict records, the call goes
through. The post hook lets through a payload that is not a JSON object,
and fails closed on any call that may post: anything it cannot check
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
                   find_questions, line_kind, question_hash, question_text, reduce_markup)
from qtext import _LOGIN  # pyright: ignore[reportPrivateUsage]
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
    fails, then the command to run. Empty to let the call through."""
    try:
        questions = _picker_questions(json.loads(raw))
    except ValueError:
        return []
    if not questions:
        return []
    texts = [question_text(q) for q in questions]
    records = read_records({question_hash(t) for t in texts})
    if records is None:
        return []
    problems: list[str] = []
    for n, (q, text) in enumerate(zip(questions, texts), 1):
        name = f"question {n} ({_first_line(text)!r})"
        if any(matches_credentials(part) for part in (q.question, *q.options)):
            problems.append(f"{name} holds a string shaped like a credential, its "
                            "related-decision line included: take it out")
            continue
        record = records.get(question_hash(text))
        if record is None:
            problems.append(f"{name} has no verdict from the last 2 hours: vet it, or vet it "
                            "again if its text changed after vetting")
        elif record["verdict"] != "ask":
            problems.append(f"{name}: its latest verdict is {record['verdict']}{_field(record)}, "
                            "so it is not asked")
    if problems:
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


# A mention as the answer-service spec counts one (*A mention names a user
# outside code, quotes and links*): `@login`, not inside a word, a path or
# an email, and not a team's `@org/team`. A `_` beside it, as emphasis
# puts there, does not stop the match. Discord's user mention, `<@id>` or
# `<@!id>`, counts on every surface; `<@&id>` names a role, which counts as
# none.
_MENTION = re.compile(r"(?<![A-Za-z0-9@/])@" + _LOGIN + r"(?![A-Za-z0-9-]|/[A-Za-z0-9])"
                      r"|<@!?\d+>")
# A code span: a backtick run no backslash escapes, closed by a run of the
# same length.
_CODE_SPAN = r"(?<![\\`])(`+)(?!`).*?(?<!`)\1(?!`)"
# Code spans and HTML comments in one pass, so the one opening first wins,
# as in markdown. `<!-->` and `<!--->` open no comment.
_HIDDEN = re.compile(_CODE_SPAN + r"|(?<!\\)<!--(?!-?>).*?-->")
_SPAN_ONLY = re.compile(_CODE_SPAN)
# A link: a destination with no space unless in angle brackets, then an
# optional quoted title. A link is removed with its text; `[a](b c)` is no
# link, so it stays and a mention in it counts.
_LINK = re.compile(r"""(?<!\\)\[[^\]]*\]\(\s*(?:<[^>]*>|[^\s()]*)(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)""")
# Where a span or an inline comment cannot continue: a blank line or a
# list item's start.
_BLOCK_START = re.compile(r"\s*$|\s*(?:[-*+]|\d{1,9}[.)])(?:\s|$)")


def _shown(text: str, discord: bool) -> str:
    """text with each code span, HTML comment and link replaced by a
    space, since a mention in one names no one. Discord has no HTML
    comments and no such links, so there only code spans go."""
    if discord:
        return _SPAN_ONLY.sub(" ", text)
    return _LINK.sub(" ", _HIDDEN.sub(" ", text))


def _mentions(text: str, discord: bool = False) -> bool:
    """Whether a question's own lines mention a user, which tags that
    person as a tag line does (inquisitor spec, Purpose: *A question
    tags* a person when its tag line, list item or sentence mentions
    them). The lines question_text leaves out, such as Related, tag and
    Concerns lines, are skipped, but record lines are read; so are `>`
    lines. Every kept line is read two ways, alone and joined with the
    other lines of its block, and a mention either reading finds counts:
    the post hook errs toward blocking. Fenced code blocks are not
    recognized, so a mention in one counts too."""
    lines = text.split("\n")
    kept = [line for n, line in enumerate(lines)
            if (n == 0 or line_kind(line) in (None, "record"))
            and not line.lstrip().startswith(">")]
    blocks: list[list[str]] = [[]]
    for line in kept:
        if _BLOCK_START.match(line) and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    readings = kept + [" ".join(block) for block in blocks]
    return any(_MENTION.search(_shown(reading, discord)) for reading in readings)


def _verdict_problem(post: post_reader.Post, q: _Vetted, record: VerdictRecord | None) -> str | None:
    """Why one question blocks the post, or None."""
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
    tagged = (any(line_kind(line) == "tag" and line.strip() != UNTAGGED_LINE
                  for line in found.lines)
              or _mentions(found.question.question, post.surface == "discord"))
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
    for post in posts:
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
        problem = _verdict_problem(post, q, records.get(q.hash))
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
