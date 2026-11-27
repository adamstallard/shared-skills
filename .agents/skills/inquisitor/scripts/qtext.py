"""A question's text and hash, inline markup, sentences, terms, and the
questions in a post's body.

One module, because the first call, the post hook, the log command, the
answer service and every reader of a questions branch must build a
question's text and hash the same way (inquisitor spec: *A question's text
and hash are built one way*).

Owned by build part P2 of the implementation plan, except find_questions, which P3 builds (task 2.5).
Standard library only.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from common import NotBuilt
from formats import is_repository

# The fixed line prefixes a question may carry after its first line, which
# its text and hash leave out (inquisitor spec: *A question's text and hash
# are built one way*). Each is matched on the line with its whitespace
# trimmed.
RELATED_PREFIX = "Related: "
CONCERNS_PREFIX = "Concerns: "
RECORDED_PREFIX = "Recorded: "
NOT_RECORDED_PREFIX = "Not recorded: "
PERSON_REQUIRED_FORMAT = "Inquisitor: a person must decide this (required by {skill})."
UNTAGGED_LINE = ("Inquisitor: no one with authority to decide this could be tagged; "
                 "name deciders in .inquisitor/reviewers.")

LineKind = Literal["related", "tag", "person-required", "concerns", "record"]


@dataclass(frozen=True)
class Question:
    """One question as asked, before its text is built.

    kind "picker": question is the picker's `question` field, options its
    options' labels. kind "post": question is a list item without its
    marker, or a sentence. kind "text": anything else, such as a whole
    Linear or Discord message, taken as one part.
    """

    kind: Literal["picker", "post", "text"]
    question: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoundQuestion:
    """A question find_questions found in a post's body.

    item is its number among the open-questions section's items, counting
    from 1, or None for a sentence outside any section. deferred is True for
    an item of a section begun by a deferral label. lines are the extra
    lines after it (related-decision, person-required, concerns, tag), as
    written.
    """

    question: Question
    item: int | None
    deferred: bool
    lines: tuple[str, ...] = field(default=())


# -- inline markup -------------------------------------------------------------

# Characters CommonMark lets a backslash escape: ASCII punctuation.
_ESCAPABLE = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
# An autolink: `<`, a scheme of 2 to 32 characters, `:`, and no space or `<`
# or `>` before the closing `>`; or an email address in angle brackets.
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*)>")
_EMAIL_AUTOLINK = re.compile(r"<([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                             r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*)>")
# An HTML tag as the spec defines one: `<`, an optional `/`, a name of
# letters and digits, then a space, `/` or `>`; the tag runs to its `>`.
_HTML_TAG = re.compile(r"</?[A-Za-z0-9]+(?:[ /][^>]*)?>")
# A protected run: text that markup reduction already produced and that the
# later passes must leave alone, held as a placeholder of private-use
# characters around its index.
_OPEN, _CLOSE = "\ue000", "\ue001"
_PLACEHOLDER = re.compile(_OPEN + r"(\d+)" + _CLOSE)
# A link's text may hold balanced brackets one level deep: `[see [1] here](url)`.
_LINK = re.compile(r"!?\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\([^()\s]*(?:\([^()\s]*\)[^()\s]*)*(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_EMPHASIS = [
    re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S),
    re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.S),
    re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S),
    re.compile(r"\*(?=[^\s*])(.+?)(?<=[^\s*])\*", re.S),
    re.compile(r"(?<!\w)_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)", re.S),
]


def _protect(text: str) -> tuple[str, list[str]]:
    """Reduce backslash escapes, code spans, autolinks and HTML tags, left to
    right as CommonMark reads them, putting each result behind a placeholder
    so that no later pass reads markup in it."""
    held: list[str] = []
    out: list[str] = []

    def hold(value: str) -> None:
        out.append(f"{_OPEN}{len(held)}{_CLOSE}")
        held.append(value)

    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in (_OPEN, _CLOSE):
            hold(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            hold(text[i + 1])
            i += 2
            continue
        if c == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            ticks = text[i:j]
            k = j
            close = -1
            while k < n:
                k = text.find(ticks, k)
                if k < 0:
                    break
                end = k + len(ticks)
                if (k == 0 or text[k - 1] != "`") and (end >= n or text[end] != "`"):
                    close = k
                    break
                while k < n and text[k] == "`":
                    k += 1
            if close < 0:
                hold(ticks)
                i = j
                continue
            inner = text[j:close].replace("\n", " ")
            if len(inner) >= 2 and inner[0] == " " and inner[-1] == " " and inner.strip(" "):
                inner = inner[1:-1]
            hold(inner)
            i = close + len(ticks)
            continue
        if c == "<":
            m = _AUTOLINK.match(text, i) or _EMAIL_AUTOLINK.match(text, i)
            if m:
                hold(m.group(1))
                i = m.end()
                continue
            m = _HTML_TAG.match(text, i)
            if m:
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out), held


def _restore(text: str, held: list[str]) -> str:
    return _PLACEHOLDER.sub(lambda m: held[int(m.group(1))], text)


def reduce_markup(text: str) -> str:
    """Inline markup reduced to its text (inquisitor spec: *Inline markup is
    reduced to its text one way*): a code span, emphasis, strong emphasis or
    `~~` strikethrough becomes its inner text; a link or image its link or
    alt text; an autolink its URL; a backslash escape the escaped character;
    an HTML tag nothing. Nothing else changes."""
    protected, held = _protect(text)
    while True:
        reduced = _LINK.sub(lambda m: m.group(1), protected)
        for pattern in _EMPHASIS:
            reduced = pattern.sub(lambda m: m.group(1), reduced)
        if reduced == protected:
            break
        protected = reduced
    return _restore(protected, held)


# -- the lines a question's text leaves out -----------------------------------

_LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
_RELATED = re.compile(r"Related: https?://\S+")
_TAG = re.compile(r"@" + _LOGIN)
_PERSON_REQUIRED = re.compile(r"Inquisitor: a person must decide this \(required by [^()\s]+\)\.")
_CONCERNS = re.compile(r"Concerns: (?:lore )?(\S+)")
_VISIBILITY = r"\((?:private|internal|public)\)"
_RECORDED = re.compile(RECORDED_PREFIX + r"(\S+) questions branch " + _VISIBILITY
                       + r"(?:, more visible than (\S+) " + _VISIBILITY + r", where this was asked)?")
# The reasons a `Not recorded: ` line may give (inquisitor spec: scenario
# *Not recorded gives a listed reason*).
NOT_RECORDED_LINES = frozenset(NOT_RECORDED_PREFIX + reason for reason in (
    "about your way of working", "only a security advisory may hold it", "it has a category",
    "no push access to its questions branch", "no team's lore repository serves it",
    "no GitHub login configured"))


def line_kind(line: str) -> LineKind | None:
    """Which of the left-out lines `line` is, matched trimmed, or None.

    - related: RELATED_PREFIX and one URL with no spaces.
    - tag: only one `@login` mention, or UNTAGGED_LINE.
    - person-required: PERSON_REQUIRED_FORMAT with a skill's name.
    - concerns: CONCERNS_PREFIX, an optional `lore `, and one `owner/repo`.
    - record: a line `vet`'s second call prints, `Recorded: ` in the form
      the spec gives, or one of NOT_RECORDED_LINES."""
    s = line.strip()
    if _RELATED.fullmatch(s):
        return "related"
    if _TAG.fullmatch(s) or s == UNTAGGED_LINE:
        return "tag"
    if _PERSON_REQUIRED.fullmatch(s):
        return "person-required"
    m = _CONCERNS.fullmatch(s)
    if m and is_repository(m.group(1)):
        return "concerns"
    m = _RECORDED.fullmatch(s)
    if (m and all(is_repository(r) for r in m.groups() if r)) or s in NOT_RECORDED_LINES:
        return "record"
    return None


# -- text and hash ------------------------------------------------------------

def _part(raw: str, drop_lines: bool, picker: bool = False) -> str:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if drop_lines:
        kept: tuple[LineKind | None, ...] = (None, "record") if not picker else (None,)
        lines = lines[:1] + [line for line in lines[1:] if line_kind(line) in kept]
    return " ".join(reduce_markup("\n".join(lines)).split())


def question_text(question: Question) -> str:
    """The question's text, in the spec's four steps. The parts are the
    question itself and, for a picker, each option's label. First, lines
    after a part's first line that line_kind names are dropped; option
    labels lose none, and a record line is dropped only from a picker
    question. Then markup is reduced, each run of whitespace becomes one
    space, each part is trimmed, and the parts are joined with one LF."""
    parts = [_part(question.question, True, question.kind == "picker")]
    if question.kind == "picker":
        parts.extend(_part(label, False) for label in question.options)
    return "\n".join(parts)


def question_hash(text: str) -> str:
    """SHA-256 of the text as UTF-8, lowercase hex. A lone surrogate, which
    JSON can carry but UTF-8 cannot, is encoded as its three bytes
    (surrogatepass), so every text hashes."""
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


# -- sentences and terms -------------------------------------------------------

_SENTENCE_END = re.compile(r"[.?!](?=\s|$)")


def sentences(paragraph: str) -> list[str]:
    """A paragraph's sentences (inquisitor spec: *A sentence and a question's
    terms are defined*), each trimmed: each runs to the first `.`, `?` or
    `!` that whitespace or the paragraph's end follows. Text after the last
    such mark is a last sentence of its own."""
    found: list[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(paragraph):
        piece = paragraph[start:m.end()].strip()
        if piece:
            found.append(piece)
        start = m.end()
    rest = paragraph[start:].strip()
    if rest:
        found.append(rest)
    return found


def _word_char(c: str) -> bool:
    category = unicodedata.category(c)
    return category.startswith("L") or category == "Nd"


def terms(text: str) -> set[str]:
    """A question's terms: the words of its text split at every character
    that is neither a Unicode letter nor a digit, lowercased."""
    words: set[str] = set()
    current: list[str] = []
    for c in text + " ":
        if _word_char(c):
            current.append(c)
        elif current:
            words.add("".join(current).lower())
            current = []
    return words


def find_questions(body: str) -> list[FoundQuestion]:
    """The questions in a post's body: each item of an open-questions
    section and each other sentence ending in `?`, none in code, `>` lines
    or prose's footer (inquisitor spec: *A question in a post is a listed
    item or a sentence ending in a question mark*). The post hook and the
    first call both call this; the answer service calls it on a bot's
    Linear or Discord message.

    TODO(P3): build it (task 2.5)."""
    raise NotBuilt("P3", "find_questions")
