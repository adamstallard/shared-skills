"""The formats of questions-branch files: log files (question, answer and
handled files), miss files (readable and hash-only) and citation files.

Every writer and reader goes through this module, so a file has one format
wherever it is written (inquisitor spec: *A log file and a miss file have
one format*; *A citation file has one format*). The golden files under
fixtures/formats/ are the format as the specs give it: each is a file's
path on a questions branch with `.golden` added, so that prose and other
tools that check .md docs leave it as it is. render() of each dataclass below must equal its golden file byte for
byte, and parse() of the golden file, read at its path without `.golden`,
must give the dataclass back.

Owned by build part P2 of the implementation plan. Standard library only.
"""

import datetime
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Surface = Literal["github", "linear", "discord"]
Authority = Literal["decision", "input"]


@dataclass(frozen=True)
class Answer:
    """The answer part of an answer file. text is the answer's lines without
    their quote marks. rephrased and discussion are set together, when
    the person answered a rephrased version of the question in the answer
    service."""

    answered_by: str
    authority: Authority
    recorded_in: str
    text: str
    answer_link: str | None = None
    answers: tuple[str, ...] = ()
    rephrased: str | None = None
    discussion: str | None = None


@dataclass(frozen=True)
class LogFile:
    """A question or answer file, `questions/<date>-<slug>-<hex>.md`.

    question holds the question's lines as logged, its tag, related-decision,
    person-required and concerns lines included. repository is None on a
    collective's file; asked_from is None only in a file written during an
    Igor's run, before the Igor sets it.
    """

    name: str
    asked: str
    question: str
    repository: str | None = None
    asked_from: str | None = None
    asked_in: str | None = None
    answer: Answer | None = None


@dataclass(frozen=True)
class HandledFile:
    """A handled file: only `handled` (yyyy-mm-dd, UTC) and `closes` (the
    closed file's name without its directory), and no body."""

    name: str
    handled: str
    closes: str


@dataclass(frozen=True)
class MissFile:
    """A readable miss file, `misses/<hash>.md`. filter is "1" to "4".
    said_by is None in a miss reported by an Igor's worker or by
    the Igor's own inquisitor run; asked_by
    is None for a question with no thread, and in a worker's miss."""

    hash: str
    asked: str
    filter: Literal["1", "2", "3", "4"]
    said: str
    question: str
    said_by: str | None = None
    asked_by: str | None = None
    repository: str | None = None
    asked_from: str | None = None
    asked_in: str | None = None


@dataclass(frozen=True)
class HashOnlyMiss:
    """A hash-only miss file: empty frontmatter, no body (inquisitor spec: *A
    hash-only miss file shows nothing but that it exists*)."""

    hash: str


@dataclass(frozen=True)
class CitationFile:
    """`citations/<date>-<hex>` on a lore repository's questions branch.
    run is set only when an Igor pushes it from a run."""

    name: str
    entry: str
    date: str
    run: str | None = None


@dataclass(frozen=True)
class Unreadable:
    """A questions-branch file that does not read as its format says.
    Callers show it only as input labelled unreadable, and post nothing from
    it, its name included."""

    path: str
    why: str


QuestionsBranchFile = LogFile | HandledFile | MissFile | HashOnlyMiss | CitationFile


# -- names ------------------------------------------------------------------

_DATE = r"\d{4}-\d{2}-\d{2}"
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_LOG_NAME = re.compile(rf"({_DATE})-({_SLUG})-([0-9a-f]{{6}})\.md")
_MISS_NAME = re.compile(r"([0-9a-f]{64})\.md")
_CITATION_NAME = re.compile(rf"({_DATE})-[0-9a-f]{{6}}")
SLUG_MAX = 40


def slug(question_text: str) -> str:
    """The slug of a log file's name: lowercase, each run of characters
    other than a-z and 0-9 made one `-`, at most 40 characters, no `-` at
    either end, or `question` when nothing is left."""
    dashed = re.sub(r"[^a-z0-9]+", "-", question_text.lower())
    return dashed[:SLUG_MAX].strip("-") or "question"


def log_name(date: str, slug_text: str, suffix: str) -> str:
    """`<date>-<slug>-<suffix>.md`. The caller passes `handled` as the slug
    of a handled file."""
    return f"{date}-{slug_text}-{suffix}.md"


def miss_hash(kind: Literal["github", "linear", "discord", "file", "message"], value: str) -> str:
    """The hash naming `misses/<hash>.md`: SHA-256 of kind, LF, value
    (inquisitor spec: *Every miss file is named by one hash*). For a miss on
    a reply an answer service posted, kind is the reply's platform and
    value the reply's id (on GitHub, its node_id). For any other miss whose
    question has a log file on the branch, kind is `file` and value that
    file's path; with no log file, kind is `message` and value the URL of
    the message that asked it."""
    return hashlib.sha256(f"{kind}\n{value}".encode("utf-8")).hexdigest()


def _valid_date(value: str) -> bool:
    if not re.fullmatch(_DATE, value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _log_name_ok(name: str) -> bool:
    m = _LOG_NAME.fullmatch(name)
    return bool(m) and len(m.group(2)) <= SLUG_MAX and _valid_date(m.group(1))


# -- the forms keys must take ------------------------------------------------

_LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
_REPO_NAME = r"[A-Za-z0-9._-]{1,100}"
_GITHUB_ITEM = rf"https://github\.com/({_LOGIN})/({_REPO_NAME})/(?:issues|pull)/[0-9]+"
_GITHUB_COMMENT = re.compile(
    _GITHUB_ITEM + r"#(?:issuecomment-[0-9]+|pullrequestreview-[0-9]+|discussion_r[0-9]+)")
_GITHUB_BODY = re.compile(_GITHUB_ITEM)
_DISCORD = re.compile(r"https://discord\.com/channels/[0-9]+/[0-9]+/[0-9]+")
_LINEAR_ISSUE = r"https://linear\.app/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?/issue/[A-Z][A-Z0-9]*-[0-9]+"
_LINEAR_COMMENT = re.compile(_LINEAR_ISSUE + r"#comment-[0-9a-f]{8}")
_LINEAR_BODY = re.compile(_LINEAR_ISSUE)
_PINNED = re.compile(r"(.+)@[0-9a-f]{40}")


def is_login(value: str) -> bool:
    """Whether value has GitHub's login syntax, which callers check before a
    login reaches any API call (inquisitor spec: *A candidate or login that
    cannot be checked is skipped*): 1 to 39 letters, digits and hyphens, with no two hyphens
    together and none first or last."""
    return re.fullmatch(_LOGIN, value) is not None


def _repo_ok(owner: str, name: str) -> bool:
    return (re.fullmatch(_LOGIN, owner) is not None
            and re.fullmatch(_REPO_NAME, name) is not None and name not in (".", ".."))


def is_repository(value: str) -> bool:
    """`<owner>/<repo>`, as the spec's scenario *The forms a repository key
    and an answer_link must take* sets it: owner in login syntax, repo 1 to
    100 letters, digits, `.`, `_` and `-`, and not `.` or `..`."""
    parts = value.split("/")
    return len(parts) == 2 and _repo_ok(parts[0], parts[1])


def _github_ok(pattern: re.Pattern[str], value: str) -> bool:
    m = pattern.fullmatch(value)
    return bool(m) and _repo_ok(m.group(1), m.group(2))


def is_answer_link(value: str) -> bool:
    """A github.com comment or review URL, or the URL of a Linear comment
    or Discord message that an answer service's relay posted, in the forms
    the spec gives."""
    return (_github_ok(_GITHUB_COMMENT, value) or _DISCORD.fullmatch(value) is not None
            or _LINEAR_COMMENT.fullmatch(value) is not None)


def is_asked_in(value: str) -> bool:
    """An `asked_in` in the forms *Where an asked_in may be written* gives:
    an answer_link form; or, for a question in an item's own body, the URL
    of that GitHub issue or pull request, or that Linear issue's slugless
    URL."""
    return (is_answer_link(value) or _github_ok(_GITHUB_BODY, value)
            or _LINEAR_BODY.fullmatch(value) is not None)


def is_recorded_in(value: str) -> bool:
    """A `recorded_in`: an answer_link form, or a path from the repository's
    root, optionally `@<40 hex>`, with no leading `/`, no empty, `.` or `..`
    segment, none starting with `-`, and no control character or line or
    paragraph separator, which could start a line of its own when the value
    is printed or posted."""
    if is_answer_link(value):
        return True
    m = _PINNED.fullmatch(value)
    path = m.group(1) if m else value
    if not path or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in path):
        return False
    return all(seg not in ("", ".", "..") and not seg.startswith("-") for seg in path.split("/"))


# -- writing -----------------------------------------------------------------

def _printable(c: str) -> bool:
    """Whether c is in YAML 1.2's printable set, leaving out tab, LF and CR,
    which _quote escapes itself."""
    o = ord(c)
    return (0x20 <= o <= 0x7E or o == 0x85 or 0xA0 <= o <= 0xD7FF or 0xE000 <= o <= 0xFFFD
            or 0x10000 <= o <= 0x10FFFF)


def _quote(value: str) -> str:
    """A YAML double-quoted scalar that reads back as value."""
    out: list[str] = []
    for c in value:
        if 0xD800 <= ord(c) <= 0xDFFF:
            raise ValueError("a lone surrogate is no Unicode character")
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif not _printable(c) or c in "\u0085\u2028\u2029":
            out.append(f"\\u{ord(c):04x}" if ord(c) <= 0xFFFF else f"\\U{ord(c):08x}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def _frontmatter(pairs: list[tuple[str, str | None]]) -> list[str]:
    return [f"{key}: {_quote(value)}" for key, value in pairs if value is not None]


def _lines(text: str) -> list[str]:
    """text's lines with line ends made LF and blank lines at its start and
    end dropped."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _one_line(text: str) -> str:
    return " ".join(text.split())


def render(file: QuestionsBranchFile) -> str:
    """The file's content: UTF-8 text with LF line ends, frontmatter values
    double-quoted, keys in one fixed order. Raises ValueError for text that
    UTF-8 cannot encode, such as a lone surrogate."""
    text = _render(file)
    text.encode("utf-8")
    return text


def _render(file: QuestionsBranchFile) -> str:
    if isinstance(file, CitationFile):
        return "".join(line + "\n" for line in _frontmatter(
            [("entry", file.entry), ("date", file.date), ("run", file.run)]))
    if isinstance(file, HashOnlyMiss):
        return "---\n---\n"
    if isinstance(file, HandledFile):
        head = _frontmatter([("handled", file.handled), ("closes", file.closes)])
        return "\n".join(["---", *head, "---"]) + "\n"
    if isinstance(file, MissFile):
        head = _frontmatter([
            ("repository", file.repository), ("asked_from", file.asked_from),
            ("asked", file.asked), ("asked_in", file.asked_in), ("asked_by", file.asked_by),
            ("filter", file.filter), ("said", file.said), ("said_by", file.said_by)])
        body = ["## Question", *_lines(file.question)]
        return "\n".join(["---", *head, "---", *body]) + "\n"
    answer = file.answer
    pairs: list[tuple[str, str | None]] = [
        ("repository", file.repository), ("asked_from", file.asked_from),
        ("asked", file.asked), ("asked_in", file.asked_in)]
    body = ["## Question", *_lines(file.question)]
    if answer is not None:
        pairs += [("answered_by", answer.answered_by), ("authority", answer.authority),
                  ("recorded_in", answer.recorded_in), ("answer_link", answer.answer_link),
                  ("answers", " ".join(answer.answers) if answer.answers else None)]
        if answer.rephrased is not None and answer.discussion is not None:
            body += ["## Rephrased question", _one_line(answer.rephrased),
                     "## Discussion", _one_line(answer.discussion)]
        body.append("## Answer")
        # An empty answer, such as an approving review with no text, is one
        # bare `>`, so the file still ends in a quote line and reads back.
        body += [f"> {line}" if line else ">" for line in _lines(answer.text)] or [">"]
    return "\n".join(["---", *_frontmatter(pairs), "---", *body]) + "\n"


# -- reading -----------------------------------------------------------------

class _Bad(Exception):
    """A file off its format; the message says why."""


_KEY_LINE = re.compile(r"([a-z_]+): \"(.*)\"")
_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "/": "/", "0": "\0", "r": "\r"}


def _unquote(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == '"':
            raise _Bad("an unescaped quote inside a value")
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= len(raw):
            raise _Bad("a value ends in a backslash")
        e = raw[i + 1]
        if e in _ESCAPES:
            out.append(_ESCAPES[e])
            i += 2
        elif e in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[e]
            digits = raw[i + 2:i + 2 + width]
            if not re.fullmatch(rf"[0-9a-fA-F]{{{width}}}", digits):
                raise _Bad("a malformed escape in a value")
            point = int(digits, 16)
            if point > 0x10FFFF or 0xD800 <= point <= 0xDFFF:
                raise _Bad("an escape in a value names no Unicode character")
            out.append(chr(point))
            i += 2 + width
        else:
            raise _Bad("an unknown escape in a value")
    return "".join(out)


def _keys(lines: list[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for line in lines:
        m = _KEY_LINE.fullmatch(line)
        if not m:
            raise _Bad("a frontmatter line is not a key and a double-quoted value")
        if m.group(1) in keys:
            raise _Bad(f"the key {m.group(1)} appears twice")
        keys[m.group(1)] = _unquote(m.group(2))
    return keys


def _split(content: str) -> tuple[dict[str, str], list[str]]:
    """The frontmatter's keys and the body's lines."""
    if content.startswith("\ufeff") or "\r" in content:
        raise _Bad("it is not UTF-8 text with LF line ends")
    if not content.endswith("\n"):
        raise _Bad("it does not end with a line end")
    lines = content[:-1].split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        raise _Bad("it has no frontmatter between two --- lines")
    end = lines.index("---", 1)
    return _keys(lines[1:end]), lines[end + 1:]


def _only(keys: dict[str, str], allowed: set[str], required: set[str]) -> None:
    extra = sorted(set(keys) - allowed)
    if extra:
        raise _Bad(f"it holds a key its kind of file may not: {extra[0]}")
    missing = sorted(required - set(keys))
    if missing:
        raise _Bad(f"it lacks the key {missing[0]}")


def _check_forms(keys: dict[str, str]) -> None:
    for key in ("repository", "asked_from"):
        if key in keys and not is_repository(keys[key]):
            raise _Bad(f"its {key} is not in the form owner/repo")
    if "asked_in" in keys and not is_asked_in(keys["asked_in"]):
        raise _Bad("its asked_in is not in a form an asked_in may take")
    if "answer_link" in keys and not is_answer_link(keys["answer_link"]):
        raise _Bad("its answer_link is not in a form an answer_link may take")
    if "recorded_in" in keys and not is_recorded_in(keys["recorded_in"]):
        raise _Bad("its recorded_in is neither a link nor a path from the repository's root")
    for key in ("asked", "handled"):
        if key in keys and not _valid_date(keys[key]):
            raise _Bad(f"its {key} is not a yyyy-mm-dd date")


def _question_body(body: list[str]) -> list[str]:
    if not body or body[0] != "## Question":
        raise _Bad("its body does not start with ## Question")
    rest = body[1:]
    while rest and not rest[-1].strip():
        rest.pop()
    return rest


_LOG_KEYS = {"repository", "asked_from", "asked", "asked_in", "answered_by", "authority",
             "recorded_in", "answer_link", "answers"}
_ANSWER_KEYS = {"answered_by", "authority", "recorded_in", "answer_link", "answers"}
_MISS_KEYS = {"repository", "asked_from", "asked", "asked_in", "asked_by", "filter", "said",
              "said_by"}


def _parse_log(name: str, content: str, lore_branch: bool) -> LogFile | HandledFile:
    keys, body = _split(content)
    if "handled" in keys:
        _only(keys, {"handled", "closes"}, {"handled", "closes"})
        _check_forms(keys)
        m = _LOG_NAME.fullmatch(name)
        if m is None or m.group(2) != "handled":
            raise _Bad("a handled file's slug is not handled")
        if not _log_name_ok(keys["closes"]):
            raise _Bad("its closes is not a question file's name")
        if body:
            raise _Bad("a handled file has a body")
        return HandledFile(name=name, handled=keys["handled"], closes=keys["closes"])
    required: set[str] = {"asked", "asked_from"} if lore_branch else {"asked", "asked_from", "repository"}
    if "authority" in keys:
        required |= {"answered_by", "authority", "recorded_in"}
    _only(keys, _LOG_KEYS if "authority" in keys else _LOG_KEYS - _ANSWER_KEYS, required)
    _check_forms(keys)
    lines = _question_body(body)
    answer: Answer | None = None
    if "authority" in keys:
        authority = keys["authority"]
        if authority not in ("decision", "input"):
            raise _Bad("its authority is neither decision nor input")
        quoted: list[str] = []
        while lines and lines[-1].startswith(">"):
            line = lines.pop()
            quoted.insert(0, line[2:] if line.startswith("> ") else line[1:])
        if not quoted or not lines or lines[-1] != "## Answer":
            raise _Bad("it holds authority, and its body does not end in ## Answer and quote lines")
        lines.pop()
        rephrased = discussion = None
        if len(lines) >= 4 and lines[-4] == "## Rephrased question" and lines[-2] == "## Discussion":
            rephrased, discussion = lines[-3], lines[-1]
            del lines[-4:]
        answers = tuple(keys["answers"].split(" ")) if "answers" in keys else ()
        if any(not _log_name_ok(a) for a in answers):
            raise _Bad("its answers holds something other than question files' names")
        answer = Answer(answered_by=keys["answered_by"],
                        authority="decision" if authority == "decision" else "input",
                        recorded_in=keys["recorded_in"], text="\n".join(quoted),
                        answer_link=keys.get("answer_link"), answers=answers,
                        rephrased=rephrased, discussion=discussion)
    return LogFile(name=name, asked=keys["asked"], question="\n".join(lines),
                   repository=keys.get("repository"), asked_from=keys.get("asked_from"),
                   asked_in=keys.get("asked_in"), answer=answer)


def _parse_miss(digest: str, content: str) -> MissFile | HashOnlyMiss:
    keys, body = _split(content)
    if not keys:
        if body:
            raise _Bad("a miss file with no keys has a body")
        return HashOnlyMiss(hash=digest)
    _only(keys, _MISS_KEYS, {"asked", "asked_from", "filter", "said"})
    _check_forms(keys)
    flt = keys["filter"]
    if flt not in ("1", "2", "3", "4"):
        raise _Bad("its filter is not 1, 2, 3 or 4")
    lines = _question_body(body)
    return MissFile(hash=digest, asked=keys["asked"],
                    filter="1" if flt == "1" else "2" if flt == "2" else "3" if flt == "3" else "4",
                    said=keys["said"], question="\n".join(lines), said_by=keys.get("said_by"),
                    asked_by=keys.get("asked_by"), repository=keys.get("repository"),
                    asked_from=keys.get("asked_from"), asked_in=keys.get("asked_in"))


def _parse_citation(name: str, date: str, content: str) -> CitationFile:
    if content.startswith("\ufeff") or "\r" in content or not content.endswith("\n"):
        raise _Bad("it is not UTF-8 text with LF line ends")
    keys = _keys(content[:-1].split("\n"))
    _only(keys, {"entry", "date", "run"}, {"entry", "date"})
    if keys["date"] != date:
        raise _Bad("its date is not the date in its name")
    if not keys["entry"] or not keys.get("run", "x"):
        raise _Bad("its entry or run is empty")
    return CitationFile(name=name, entry=keys["entry"], date=keys["date"], run=keys.get("run"))


def parse(path: str, content: str, lore_branch: bool) -> QuestionsBranchFile | Unreadable:
    """Read a questions-branch file by its path (`questions/…`,
    `misses/…` or `citations/…`). lore_branch says whether the branch is a
    lore repository's, where a log file may lack `repository`. Anything off
    the format is Unreadable (inquisitor spec: *A log file is read by its
    frontmatter and its body's end*; *A questions-branch file named outside
    the format is unreadable*; *A log file's repository keys and links are
    checked before use*)."""
    directory, _, name = path.partition("/")
    try:
        if directory == "questions" and _log_name_ok(name):
            return _parse_log(name, content, lore_branch)
        if directory == "misses" and (m := _MISS_NAME.fullmatch(name)):
            return _parse_miss(m.group(1), content)
        if directory == "citations" and (m := _CITATION_NAME.fullmatch(name)) and _valid_date(m.group(1)):
            return _parse_citation(name, m.group(1), content)
    except _Bad as bad:
        return Unreadable(path=path, why=str(bad))
    return Unreadable(path=path, why="its name is outside the questions branch's format")
