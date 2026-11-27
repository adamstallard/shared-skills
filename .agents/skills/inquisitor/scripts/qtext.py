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

    item is its number among all the post's open-questions section items,
    counting from 1, or None for a sentence outside any section. deferred is True for
    an item of a section begun by a deferral label. lines are the extra
    lines after it (related-decision, person-required, concerns, tag), as
    written. raw is the markdown it was found in, link targets included,
    for the credential scan (*The credential scan reads raw markdown*): an
    item's lines, or a sentence's whole paragraph.
    """

    question: Question
    item: int | None
    deferred: bool
    lines: tuple[str, ...] = field(default=())
    raw: str = ""


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


# -- the questions in a post --------------------------------------------------

# The labels that begin an open-questions section, and, for
# _DEFERRAL_LABEL, a deferral section (inquisitor spec: *A
# question in a post is a listed item or a sentence ending in a question
# mark*), matched at the start of the label's reduced text, ignoring case.
_QUESTION_LABEL = re.compile(r"(?:open questions?|still open|questions?)\b", re.I)
_DEFERRAL_LABEL = re.compile(r"(?:not in this change|deferred|not done)\b", re.I)
_FENCE = re.compile(r"\s*(`{3,}|~{3,})")
_QUOTE = re.compile(r" {0,3}>")
_HEADING = re.compile(r" {0,3}#{1,6}(?:\s+(.*?))?(?:\s+#+)?\s*")
_BOLD_LABEL = re.compile(r"\s*(?:\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__):?\s*")
_ITEM = re.compile(r"(\s*)(?:[-*+]|\d{1,9}[.)])(?:\s+(.*))?")
# prose's signed footer, with or without its deferred cold read's note.
_FOOTER = re.compile(r"prose ✓ [0-9a-f]{6}(?: \(cold read deferred to the hand-back\))?")
_SENTENCE_MARK = re.compile(r"[.?!](?=\s|$)")
# A link's destination and title, which reduce_markup drops.
_LINK_TARGET = re.compile(r"\]\([^()\s]*(?:\([^()\s]*\)[^()\s]*)*(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")

Section = Literal["question", "deferral"]


def _label(text: str) -> Section | None:
    reduced = " ".join(reduce_markup(text).split())
    if _QUESTION_LABEL.match(reduced):
        return "question"
    if _DEFERRAL_LABEL.match(reduced):
        return "deferral"
    return None


def _mask(text: str) -> str:
    """text with an `x` in place of each `.`, `?` and `!` inside a code
    span, autolink, HTML tag, or link destination or title, so that no
    sentence ends inside markup. The length is kept. A backslash-escaped
    character opens nothing, as in _protect."""
    out = list(text)

    def blank(begin: int, end: int) -> None:
        for k in range(begin, end):
            if out[k] in ".?!":
                out[k] = "x"

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
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
                if text[k - 1] != "`" and (end >= n or text[end] != "`"):
                    close = k
                    break
                while k < n and text[k] == "`":
                    k += 1
            if close >= 0:
                blank(j, close)
                i = close + len(ticks)
            else:
                i = j
            continue
        if c == "<":
            m = _AUTOLINK.match(text, i) or _EMAIL_AUTOLINK.match(text, i) or _HTML_TAG.match(text, i)
            if m:
                blank(i, m.end())
                i = m.end()
                continue
        i += 1
    for m in _LINK_TARGET.finditer("".join(out)):
        blank(m.start(), m.end())
    return "".join(out)


@dataclass
class _Item:
    start: int
    indent: int
    lines: list[str]
    deferred: bool


def _paragraph_questions(lines: list[tuple[int, str]]) -> list[tuple[int, FoundQuestion]]:
    """The questions in one paragraph: each sentence whose reduced text ends
    in `?`. Any line but the first for which line_kind gives a kind is no
    part of any sentence. It goes to the last question ending on the line
    before it, or is dropped when none ends there (inquisitor spec: *A
    related-decision line is one URL on a line of its own*)."""
    content: list[tuple[int, str]] = []
    extra: dict[int, list[str]] = {}
    for n, (_, line) in enumerate(lines):
        if n > 0 and line_kind(line) is not None:
            if content:
                extra.setdefault(len(content) - 1, []).append(line)
            continue
        content.append(lines[n])
    if not content:
        return []
    raw = "\n".join(line for _, line in content)
    # Sentences are cut in the reduced paragraph, as the spec defines them.
    # reduce_markup of the masked paragraph lines up with that of the raw
    # one, with every `.`, `?` and `!` that sat in markup blanked, so a mark
    # in it is a real sentence end. Lengths that differ would be a bug in
    # _mask; the unmasked reduction is then used, and a `?` in markup may
    # end a question.
    reduced = reduce_markup(raw)
    marks = reduce_markup(_mask(raw))
    if len(marks) != len(reduced):
        marks = reduced
    pieces: list[tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_MARK.finditer(marks):
        pieces.append((start, m.end()))
        start = m.end()
    if reduced[start:].strip():
        pieces.append((start, len(reduced)))
    out: list[tuple[int, FoundQuestion]] = []
    last_on_line: dict[int, int] = {}
    for begin, end in pieces:
        sentence = " ".join(reduced[begin:end].split())
        if not sentence.endswith("?") or not marks[begin:end].rstrip().endswith("?"):
            continue
        offset = begin + len(reduced[begin:end]) - len(reduced[begin:end].lstrip())
        last_on_line[marks.count("\n", 0, end)] = len(out)
        first = min(reduced.count("\n", 0, offset), len(content) - 1)
        # The sentence is already reduced; escaping it makes question_text
        # reduce it to itself, so its text is the sentence as the spec
        # defines a question's text.
        out.append((content[first][0],
                    FoundQuestion(Question("post", _escape(sentence)), None, False, raw=raw)))
    for line, index in last_on_line.items():
        if line in extra:
            pos, q = out[index]
            out[index] = (pos, FoundQuestion(q.question, None, False, tuple(extra[line]), raw))
    return out


def _escape(text: str) -> str:
    """text with a backslash before each ASCII punctuation character, which
    reduce_markup turns back into that character, so that reduce_markup
    gives text back unchanged."""
    return "".join("\\" + c if c in _ESCAPABLE else c for c in text)


def _item_question(item: _Item, number: int) -> FoundQuestion:
    lines = tuple(line for line in item.lines[1:] if line_kind(line) is not None)
    text = "\n".join(item.lines)
    return FoundQuestion(Question("post", text), number, item.deferred, lines, text)


def find_questions(body: str) -> list[FoundQuestion]:
    """The questions in a post's body: each item of an open-questions
    section and each other sentence ending in `?`, none in code, `>` lines
    or prose's footer (inquisitor spec: *A question in a post is a listed
    item or a sentence ending in a question mark*). The post hook and the
    first call both call this; the answer service calls it on a bot's
    Linear or Discord message.

    A section starts at a heading, a bold label or a plain line ending in
    `:` whose text begins with a question or deferral label, and runs to the
    next heading or bold label. Section items are numbered from 1 through
    the whole post, deferred ones included; a list nested in an item, and lines
    continuing it, are part of that item. Every other paragraph, list item
    outside a section, heading and bold label is searched for sentences. The
    questions come in the order the body holds them."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and _FOOTER.fullmatch(lines[-1].strip()):
        lines.pop()

    found: list[tuple[int, FoundQuestion]] = []
    number = 0
    section: Section | None = None
    item: _Item | None = None
    paragraph: list[tuple[int, str]] = []
    blank_before = False
    fence: str | None = None
    # An indented code block: lines indented 4 or more after a blank line or
    # a block's end, outside any list.
    code_block = False
    in_list = False

    def end_paragraph() -> None:
        found.extend(_paragraph_questions(paragraph))
        paragraph.clear()

    def end_item() -> None:
        nonlocal item, number
        if item is not None:
            number += 1
            found.append((item.start, _item_question(item, number)))
            item = None

    for i, line in enumerate(lines):
        indented = line.expandtabs(4).startswith("    ")
        if code_block:
            if indented or not line.strip():
                continue
            code_block = False
        if fence is None and indented and not paragraph and item is None and not in_list:
            code_block = True
            continue
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and not stripped.lstrip(fence[0]):
                fence = None
            continue
        m = _FENCE.match(line)
        if m:
            end_paragraph()
            end_item()
            fence = m.group(1)
            blank_before = False
            in_list = False
            continue
        if not line.strip():
            end_paragraph()
            blank_before = True
            continue
        if _QUOTE.match(line):
            end_paragraph()
            end_item()
            blank_before = False
            in_list = False
            continue
        heading = _HEADING.fullmatch(line)
        bold = None if heading else _BOLD_LABEL.fullmatch(line)
        if heading or bold:
            end_paragraph()
            end_item()
            text = (heading.group(1) or "") if heading else (bold.group(1) or bold.group(2)) if bold else ""
            section = _label(text)
            in_list = False
            if section is None:
                found.extend(_paragraph_questions([(i, text)]))
            blank_before = False
            continue
        listed = _ITEM.fullmatch(line)
        if section is not None:
            if listed and (item is None or len(listed.group(1)) <= item.indent):
                end_paragraph()
                end_item()
                item = _Item(i, len(listed.group(1)), [listed.group(2) or ""], section == "deferral")
                blank_before = False
                continue
            if item is not None and (not blank_before or line[:1].isspace()):
                item.lines.append(line)
                blank_before = False
                continue
            end_item()
        in_list = bool(listed) or (in_list and line[:1].isspace())
        if not listed and line.rstrip().endswith(":"):
            label = _label(line.strip()[:-1])
            if label is not None:
                end_paragraph()
                section = label
                blank_before = False
                continue
        if listed:
            end_paragraph()
            paragraph.append((i, listed.group(2) or ""))
        else:
            paragraph.append((i, line))
        blank_before = False
    end_paragraph()
    end_item()
    found.sort(key=lambda pair: pair[0])
    return [q for _, q in found]
