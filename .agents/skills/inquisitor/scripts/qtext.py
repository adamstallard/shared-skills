"""A question's text and hash, inline markup, sentences, terms, and the
questions in a post's body.

One module, because vet's first call, the post hook, the log command, the
answer service and every reader of a questions branch must build a
question's text and hash the same way (inquisitor spec: *A question's text
and hash are built one way*). One markdown parser serves question_text and
find_questions alike: _classify tells what kind of line each line of a
post is, and _reduce reads inline markup once, left to right.

Standard library only.
"""

import bisect
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
    an item of a section whose label defers it, such as "Not in this
    change". lines are the extra lines after it (related-decision,
    person-required, concerns, tag), as written. raw is the markdown it was
    found in, link targets included: an item's lines, or a sentence's whole
    paragraph. The post hook scans raw for credentials, which a link target
    can hold (*The credential scan reads raw markdown*). in_code is True for
    a sentence only find_questions(body, in_code=True) adds, which the
    hiding reading does not find: GitHub may show it as code, or not show it.
    """

    question: Question
    item: int | None
    deferred: bool
    lines: tuple[str, ...] = field(default=())
    raw: str = ""
    in_code: bool = False


# -- inline markup -------------------------------------------------------------

# Characters CommonMark lets a backslash escape: ASCII punctuation.
_ESCAPABLE = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
# Where any inline markup may begin; every other character is plain text.
_SPECIAL = re.compile(r"[\\`<*_~!&\[\]]")
# An entity GitHub shows as `?`.
_QUESTION_ENTITY = re.compile(r"&(?:#0*63|#[xX]0*3[fF]|quest);")
# An autolink: `<`, a scheme of 2 to 32 characters, `:`, and no space or `<`
# or `>` before the closing `>`; or an email address in angle brackets.
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*)>")
_EMAIL_AUTOLINK = re.compile(r"<([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                             r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*)>")
# An HTML tag on one line: `<name`, attributes, an optional `/` and `>`;
# or `</name>`. It stays as written, and no bracket or quote in it is
# markup. Unlike CommonMark's, a quoted value here holds no `<`, so each
# match attempt stops at the next `<` and the pass stays linear.
_HTML_TAG = re.compile(
    r"<[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:[ \t]*=[ \t]*(?:[^ \t\n\"'=<>`]+|'[^'\n<]*'|\"[^\"\n<]*\"))?)*[ \t]*/?>"
    r"|</[A-Za-z][A-Za-z0-9-]*[ \t]*>")


def _punct(c: str) -> bool:
    """c is punctuation as CommonMark reads it: a Unicode P or S character."""
    return unicodedata.category(c)[0] in "PS"


def _flanks(outside: str, inside: str) -> bool:
    """Whether a delimiter run flanks toward `inside`, by CommonMark's rule:
    inside is no whitespace, and is no punctuation unless outside is
    whitespace or punctuation. To test whether a run can open, inside is
    the character after it and outside the one before; to test whether it
    can close, the other way round. The caller passes a space for the
    text's start or end."""
    return not inside.isspace() and (not _punct(inside) or outside.isspace() or _punct(outside))


@dataclass
class _Delim:
    """A run of `*`, `_` or `~~` that may open or close emphasis. slot is
    its index in the output slots; length is the run's length as written;
    count is how many of its characters no match has used yet."""

    char: str
    slot: int
    length: int
    count: int
    can_open: bool
    can_close: bool


@dataclass
class _Bracket:
    """A `[` or `![` that may begin a link's or image's text. bottom is the
    number of delimiters before it. epoch is the number of links made
    before it: a link holds no link, so a `[` from before the latest link
    begins no link, though a `![` still begins an image."""

    slot: int
    image: bool
    bottom: int
    epoch: int


class _Reducer:
    """One left-to-right pass over a text, CommonMark's way: code spans,
    autolinks and escapes as they are met; link and image
    brackets on a stack, matched at each `]`; emphasis delimiters on a
    stack, matched at the end or when a link's text closes. Every lookup is
    a stack top, a bisect or a scan that later scans never repeat, so the
    pass takes time linear in the text's length, times a log factor for
    the bisects.

    The output is slots: (text, source offset of its first character).
    An HTML tag is text: it stays as written."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.texts: list[str] = []
        self.srcs: list[int] = []
        self.delims: list[_Delim] = []
        self.brackets: list[_Bracket] = []
        self.epoch = 0
        self._ticks: dict[int, list[int]] | None = None
        self._parens: dict[int, int] | None = None
        # The last search for `-->` started at _comment_from and found it at
        # _comment_close; -1 there means none follows _comment_from.
        self._comment_from = -1
        self._comment_close = -1
        self._run()

    def _emit(self, s: str, src: int) -> int:
        self.texts.append(s)
        self.srcs.append(src)
        return len(self.texts) - 1

    def _run(self) -> None:
        text = self.text
        n = len(text)
        i = 0
        plain = 0  # start of the plain text not yet emitted

        def flush(upto: int) -> None:
            if upto > plain:
                self._emit(text[plain:upto], plain)

        while True:
            m = _SPECIAL.search(text, i)
            if m is None:
                break
            i = m.start()
            c = text[i]
            if c == "\\":
                if i + 1 < n and text[i + 1] in _ESCAPABLE:
                    flush(i)
                    self._emit(text[i + 1], i + 1)
                    i += 2
                    plain = i
                else:
                    i += 1
            elif c == "`":
                j = i
                while j < n and text[j] == "`":
                    j += 1
                close = self._closing_ticks(j, j - i)
                if close < 0:
                    i = j
                    continue
                flush(i)
                inner = text[j:close].replace("\n", " ")
                src = j
                if len(inner) >= 2 and inner[0] == " " and inner[-1] == " " and inner.strip(" "):
                    inner = inner[1:-1]
                    src += 1
                self._emit(inner, src)
                i = close + (j - i)
                plain = i
            elif c == "<":
                auto = _AUTOLINK.match(text, i) or _EMAIL_AUTOLINK.match(text, i)
                if auto:
                    flush(i)
                    self._emit(auto.group(1), i + 1)
                    i = auto.end()
                    plain = i
                else:
                    # Raw HTML stays in the plain text, unread.
                    i = self._raw_html_end(i)
            elif c in "*_~":
                j = i
                while j < n and text[j] == c:
                    j += 1
                before = text[i - 1] if i > 0 else " "
                after = text[j] if j < n else " "
                can_open = _flanks(before, after)
                can_close = _flanks(after, before)
                if c == "_":
                    can_open, can_close = (can_open and (not can_close or _punct(before)),
                                           can_close and (not can_open or _punct(after)))
                if c == "~" and j - i != 2:
                    can_open = can_close = False
                if can_open or can_close:
                    flush(i)
                    slot = self._emit(text[i:j], i)
                    self.delims.append(_Delim(c, slot, j - i, j - i, can_open, can_close))
                    plain = j
                i = j
            elif c == "&":
                entity = _QUESTION_ENTITY.match(text, i)
                if entity:
                    flush(i)
                    self._emit("?", i)
                    i = entity.end()
                    plain = i
                else:
                    i += 1
            elif c == "!":
                if i + 1 < n and text[i + 1] == "[":
                    flush(i)
                    slot = self._emit("![", i)
                    self.brackets.append(_Bracket(slot, True, len(self.delims), self.epoch))
                    i += 2
                    plain = i
                else:
                    i += 1
            elif c == "[":
                flush(i)
                slot = self._emit("[", i)
                self.brackets.append(_Bracket(slot, False, len(self.delims), self.epoch))
                i += 1
                plain = i
            else:  # "]"
                if not self.brackets:
                    i += 1
                    continue
                opener = self.brackets.pop()
                end = -1
                if opener.image or opener.epoch == self.epoch:
                    end = self._link_tail(i + 1)
                if end < 0:
                    i += 1
                    continue
                flush(i)
                self._emphasis(opener.bottom)
                self.texts[opener.slot] = ""
                if not opener.image:
                    self.epoch += 1
                i = end
                plain = i
        flush(n)
        self._emphasis(0)

    def _closing_ticks(self, start: int, length: int) -> int:
        """Where the first run of exactly `length` backticks at or after
        start begins, or -1. Runs are found once per text and looked up by
        bisect."""
        if self._ticks is None:
            runs: dict[int, list[int]] = {}
            for m in re.finditer(r"`+", self.text):
                runs.setdefault(m.end() - m.start(), []).append(m.start())
            self._ticks = runs
        starts = self._ticks.get(length)
        if not starts:
            return -1
        k = bisect.bisect_left(starts, start)
        return starts[k] if k < len(starts) else -1

    def _raw_html_end(self, i: int) -> int:
        """The end of the HTML tag or comment starting at i, or i + 1 when
        none starts there. A comment is `<!-->`, `<!--->`, or `<!--` up to
        the next `-->`; no stretch of the text is searched for `-->` twice."""
        text = self.text
        if text.startswith("<!--", i):
            if text.startswith(">", i + 4) or text.startswith("->", i + 4):
                return i + 5 if text[i + 4] == ">" else i + 6
            if self._comment_close < i + 4:
                if self._comment_close == -1 and self._comment_from >= 0:
                    return i + 1
                self._comment_from = i + 4
                self._comment_close = text.find("-->", i + 4)
                if self._comment_close < 0:
                    return i + 1
            return self._comment_close + 3
        m = _HTML_TAG.match(text, i)
        return m.end() if m else i + 1

    def _matching_parens(self) -> dict[int, int]:
        """Each `(` that a `)` closes before any whitespace, mapped to that
        `)`'s offset; a backslash-escaped parenthesis counts as neither."""
        pairs: dict[int, int] = {}
        open_at: list[int] = []
        text = self.text
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
                i += 2
                continue
            if c == "(":
                open_at.append(i)
            elif c == ")":
                if open_at:
                    pairs[open_at.pop()] = i
            elif c.isspace():
                open_at.clear()
            i += 1
        return pairs

    def _link_tail(self, p: int) -> int:
        """The end of a link's `(destination "title")` starting at p, or -1:
        a destination with no whitespace and balanced parentheses, then
        optionally whitespace and a title in `"` or `'`, then optional
        whitespace and `)`."""
        text = self.text
        n = len(text)
        if p >= n or text[p] != "(":
            return -1
        q = self._space(p + 1)
        start = q
        while 0 <= q < n:
            c = text[q]
            if c == "\\" and q + 1 < n and text[q + 1] in _ESCAPABLE:
                q += 2
            elif c == "(":
                if self._parens is None:
                    self._parens = self._matching_parens()
                close = self._parens.get(q)
                if close is None:
                    return -1
                q = close + 1
            elif c == ")" or c.isspace():
                break
            else:
                q += 1
        if q < 0 or q >= n:
            return -1
        if text[q] == ")":
            return q + 1
        # A title needs a destination and whitespace before it.
        if q == start:
            return -1
        q = self._space(q)
        if 0 <= q < n and text[q] in "\"'":
            quote = text[q]
            q += 1
            while q < n and text[q] != quote:
                if text[q] == "\n" and self._space(q) < 0:
                    return -1
                q += 2 if text[q] == "\\" and q + 1 < n and text[q + 1] in _ESCAPABLE else 1
            if q >= n:
                return -1
            q = self._space(q + 1)
        return q + 1 if 0 <= q < n and text[q] == ")" else -1

    def _space(self, q: int) -> int:
        """Past the whitespace at q, or -1 when it holds a blank line,
        which ends a paragraph."""
        text = self.text
        lines = 0
        while q < len(text) and text[q].isspace():
            if text[q] == "\n":
                lines += 1
                if lines > 1:
                    return -1
            q += 1
        return q

    def _emphasis(self, bottom: int) -> None:
        """Match the delimiters from index bottom on, left to right: each
        closer takes the nearest opener of its character that CommonMark's
        rule of three allows, two characters each when both have two, and
        the delimiters between them become text. Then drop every delimiter
        from index bottom on.

        The rule of three: when either run can both open and close, the
        two runs' lengths must not sum to a multiple of 3, unless both
        are multiples of 3. Openers wait in buckets by character, length
        modulo 3 and whether they can close, so the nearest allowed opener
        is the latest top among at most six buckets."""
        stack: list[_Delim] = []
        buckets: dict[tuple[str, int, bool], list[int]] = {}

        def truncate(size: int) -> None:
            del stack[size:]
            for indices in buckets.values():
                while indices and indices[-1] >= size:
                    indices.pop()

        def nearest(d: _Delim) -> int:
            both = d.can_open
            best = -1
            for (char, mod, closes), indices in buckets.items():
                if char != d.char or not indices or indices[-1] <= best:
                    continue
                if ((both or closes) and (mod + d.length) % 3 == 0
                        and not (mod == 0 and d.length % 3 == 0)):
                    continue
                best = indices[-1]
            return best

        for d in self.delims[bottom:]:
            if d.can_close:
                while d.count > 0:
                    k = nearest(d)
                    if k < 0:
                        break
                    o = stack[k]
                    use = 2 if o.count >= 2 and d.count >= 2 else 1
                    o.count -= use
                    d.count -= use
                    self.texts[o.slot] = o.char * o.count
                    self.texts[d.slot] = d.char * d.count
                    truncate(k + 1 if o.count else k)
            if d.count > 0 and d.can_open:
                buckets.setdefault((d.char, d.length % 3, d.can_close), []).append(len(stack))
                stack.append(d)
        del self.delims[bottom:]


def _reduce(text: str) -> tuple[str, list[int]]:
    """text with its inline markup reduced, and for each character of the
    result its offset in text."""
    r = _Reducer(text)
    origin: list[int] = []
    for s, src in zip(r.texts, r.srcs):
        origin.extend(range(src, src + len(s)))
    return "".join(r.texts), origin


def reduce_markup(text: str) -> str:
    """Inline markup reduced to its text (inquisitor spec: *Inline markup is
    reduced to its text one way*): a code span, emphasis, strong emphasis or
    `~~` strikethrough becomes its inner text; a link or image its link or
    alt text; an autolink its URL; a backslash escape the escaped character;
    an entity for `?` (`&#63;`, `&quest;`) a `?`. Nothing else changes: an
    HTML tag stays as written."""
    return "".join(_Reducer(text).texts)


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


# -- the lines of a post --------------------------------------------------------

# The labels that begin an open-questions section, and, for
# _DEFERRAL_LABEL, a deferral section (inquisitor spec: *A
# question in a post is a listed item or a sentence ending in a question
# mark*), matched at the start of the label's reduced text, ignoring case.
_QUESTION_LABEL = re.compile(r"(?:open questions?|still open|questions?)\b", re.I)
_DEFERRAL_LABEL = re.compile(r"(?:not in this change|deferred|not done)\b", re.I)
_FENCE = re.compile(r"\s*(`{3,}|~{3,})")
# A setext heading's underline, under a paragraph.
_SETEXT = re.compile(r" {0,3}(?:-+|=+)[ \t]*")
_NUMBER = re.compile(r"^\d{1,9}[.)]\s+")
_QUOTE = re.compile(r" {0,3}>")
_ITEM = re.compile(r"(\s*)(?:[-*+]|\d{1,9}[.)])(?:\s+(.*))?")


def _marker_length(text: str) -> int:
    """The length of the list marker text starts with: `-`, `*`, `+`, or
    digits and `.` or `)`."""
    digits = len(text) - len(text.lstrip("0123456789"))
    return digits + 1 if digits else 1
# A thematic break: three or more `*`, `-` or `_`, spaces and tabs between.
_BREAK = re.compile(r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})")
# prose's signed footer, with or without its deferred cold read's note.
_FOOTER = re.compile(r"prose ✓ [0-9a-f]{6}(?: \(cold read deferred to the hand-back\))?")

Section = Literal["question", "deferral"]


def _label(text: str) -> Section | None:
    """The section a label's text begins, matched on its reduced text after
    any leading number such as `1.`, or None."""
    reduced = _NUMBER.sub("", " ".join(reduce_markup(text).split()))
    if _QUESTION_LABEL.match(reduced):
        return "question"
    if _DEFERRAL_LABEL.match(reduced):
        return "deferral"
    return None


def _heading(line: str) -> str | None:
    """An ATX heading's text, without its closing `#`s, or None: up to
    three spaces, one to six `#`, then whitespace or the line's end."""
    s = line.lstrip(" ")
    if len(line) - len(s) > 3:
        return None
    hashes = len(s) - len(s.lstrip("#"))
    if not 1 <= hashes <= 6:
        return None
    rest = s[hashes:]
    if rest and not rest[0].isspace():
        return None
    rest = rest.strip()
    closing = rest.rstrip("#")
    if closing != rest and (not closing or closing[-1].isspace()):
        rest = closing.rstrip()
    return rest


def _bold_label(line: str) -> str | None:
    """A bold label's text, or None: a line wholly `**`- or `__`-bold,
    which may end in a colon after the bold. Its inner text starts and ends
    with no whitespace and holds a character other than `*`, `_` and
    whitespace. The line is wholly bold when it
    reduces to what its inner text reduces to: then the outer marks pair
    with each other, not with a mark inside."""
    s = line.strip()
    if s.endswith(":"):
        s = s[:-1]
    for mark in ("**", "__"):
        if s.startswith(mark) and s.endswith(mark):
            inner = s[2:-2]
            if (inner.strip("*_ \t") and not inner[0].isspace() and not inner[-1].isspace()
                    and reduce_markup(s) == reduce_markup(inner)):
                return inner
    return None


_LineType = Literal["blank", "fence", "quote", "break", "heading", "bold", "item", "colon", "plain"]


@dataclass(frozen=True)
class _Line:
    """One line of a post, as _classify sorts it. text is a heading's or
    bold label's text, or a list item's text after its marker; indent is a
    list item's leading whitespace; column the column its text starts at,
    tabs expanded; fence a fence's marker; section the label a colon line
    or heading or bold label names, if any."""

    type: _LineType
    text: str = ""
    indent: int = 0
    fence: str = ""
    section: Section | None = None
    column: int = 0


def _classify(line: str) -> _Line:
    """What a post's line is, by itself. Whether it sits in code or
    continues a list item depends on the lines before it, which
    find_questions tracks."""
    if not line.strip():
        return _Line("blank")
    m = _FENCE.match(line)
    # A backtick fence's line holds no other backtick; ```a``` is a code span.
    if m and not (m.group(1)[0] == "`" and "`" in line[m.end():]):
        return _Line("fence", fence=m.group(1))
    if _QUOTE.match(line):
        return _Line("quote")
    if _BREAK.fullmatch(line):
        return _Line("break")
    text = _heading(line)
    if text is not None:
        return _Line("heading", text, section=_label(text))
    text = _bold_label(line)
    if text is not None:
        return _Line("bold", text, section=_label(text))
    m = _ITEM.fullmatch(line)
    if m:
        # The text starts after the marker and its spaces, or one column
        # after the marker when nothing or 5 or more spaces follow it.
        marker = len(line[:len(line) - len(line.lstrip()) + _marker_length(line.lstrip())].expandtabs(4))
        column = len(line[:m.start(2)].expandtabs(4)) if m.group(2) is not None else marker + 1
        if column - marker > 4:
            column = marker + 1
        return _Line("item", m.group(2) or "", len(m.group(1)), column=column)
    reduced = reduce_markup(line).rstrip()
    if reduced.endswith(":"):
        section = _label(reduced[:-1])
        if section is not None:
            return _Line("colon", line, section=section)
    return _Line("plain", line)


# -- the questions in a post --------------------------------------------------

def _width(line: str) -> int:
    """The columns of whitespace line starts with, tabs expanded."""
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _closes(line: str, fence: str) -> bool:
    """line closes a fence opened with fence: it holds only fence's
    character, at least as many of them."""
    stripped = line.strip()
    return stripped.startswith(fence) and not stripped.lstrip(fence[0])


def _opener(line: str) -> str | None:
    """The fence that line opens, alone or as a list item's text
    (`- ```sh`), or None."""
    if not (_FENCE.match(line) or _ITEM.match(line)):
        return None
    kind = _classify(line)
    return kind.fence if kind.type == "fence" else _item_fence(kind)


def _item_fence(kind: _Line) -> str | None:
    """The fence a list item's text opens, as in `- ```sh`."""
    if kind.type != "item":
        return None
    inner = _classify(kind.text)
    return inner.fence if inner.type == "fence" else None


def _fence_closes(lines: list[str]) -> list[int]:
    """For each line, the first later line that would close a fence it
    opens, or -1. One pass runs from the last line up. For each fence
    character it keeps the closing lines below the current one that are
    longer than every closing line between them and it, so each lookup is
    a bisection."""
    out = [-1] * len(lines)
    stacks: dict[str, tuple[list[int], list[int]]] = {"`": ([], []), "~": ([], [])}
    for i in range(len(lines) - 1, -1, -1):
        opened = _opener(lines[i])
        if opened is not None:
            where, negs = stacks[opened[0]]
            k = bisect.bisect_right(negs, -len(opened)) - 1
            if k >= 0:
                out[i] = where[k]
        stripped = lines[i].strip()
        if len(stripped) >= 3 and stripped[0] in stacks and not stripped.lstrip(stripped[0]):
            where, negs = stacks[stripped[0]]
            while negs and -negs[-1] <= len(stripped):
                where.pop()
                negs.pop()
            where.append(i)
            negs.append(-len(stripped))
    return out


class _MinTable:
    """The least of values[lo..hi] in constant time, from a sparse table."""

    def __init__(self, values: list[int]) -> None:
        self.levels = [values]
        width = 1
        while 2 * width <= len(values):
            prev = self.levels[-1]
            self.levels.append([min(prev[x], prev[x + width]) for x in range(len(prev) - width)])
            width *= 2

    def least(self, lo: int, hi: int) -> int:
        k = (hi - lo + 1).bit_length() - 1
        level = self.levels[k]
        return min(level[lo], level[hi - (1 << k) + 1])


@dataclass
class _Item:
    start: int
    indent: int
    lines: list[str]
    deferred: bool
    # The index in the post of each of lines.
    at: list[int]


# A found question, as four fields:
# - the line it starts on;
# - the lines it holds: a sentence's first line and the line of its
#   closing `?`, or every line an item holds;
# - where a sentence's closing `?` is: the `?`'s line, and its count among
#   that line's marks (_marks); (-1, 0) for an item;
# - the question.
_Found = tuple[int, tuple[int, ...], tuple[int, int], FoundQuestion]


def _marks(text: str) -> list[int]:
    """Where text holds a `?` or a character reference for one, in order.
    Escaping a fence's backticks, dropping a list marker or a heading's
    `#`s changes no line's count of these, so a count made on a line as a
    reading changed it names the same mark on the line as written, which
    _backstop counts on."""
    return sorted([k for k, c in enumerate(text) if c == "?"]
                  + [m.start() for m in _QUESTION_ENTITY.finditer(text)])


def _paragraph_questions(lines: list[tuple[int, str]], literal: bool = False) -> list[_Found]:
    """The questions in one paragraph: each sentence of its reduced text
    that ends in a `?`, where a mark ends a sentence as _sentence_end
    says. Any line but the first that line_kind names is no part of any
    sentence. It goes to the last question ending on the nearest line before
    it that line_kind does not name, or to none when none ends there (inquisitor spec: *A related-decision
    line is one URL on a line of its own*). Each question's raw is the
    whole paragraph, those lines included, so the credential scan reads
    every line. A literal paragraph, code read as text, keeps its markup
    as GitHub shows it."""
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
    whole = "\n".join(line for _, line in lines)
    starts = [0]
    for _, line in content[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def line_of(offset: int) -> int:
        return bisect.bisect_right(starts, offset) - 1

    marks: dict[int, list[int]] = {}

    def closing(offset: int) -> tuple[int, int]:
        n = line_of(offset)
        if n not in marks:
            marks[n] = _marks(content[n][1])
        return content[n][0], bisect.bisect_right(marks[n], offset - starts[n])

    reduced, origin = (raw, list(range(len(raw)))) if literal else _reduce(raw)
    out: list[_Found] = []
    last_on_line: dict[int, int] = {}
    begin = 0
    for end in range(len(reduced)):
        c = reduced[end]
        if c not in ".?!" or end < begin:
            continue
        if not _sentence_end(reduced, origin, end):
            continue
        piece = reduced[begin:end + 1]
        start = begin + len(piece) - len(piece.lstrip())
        begin = end + 1
        if c != "?":
            continue
        # Marks right after a question's `?`, as in `??` or `?!?`, start no sentence.
        while begin < len(reduced) and reduced[begin] in ".?!":
            begin += 1
        last_on_line[line_of(origin[end])] = len(out)
        # The sentence is already reduced; escaping it makes question_text
        # reduce it to itself, so its text is the sentence as the spec
        # defines a question's text.
        sentence = " ".join(piece.split())
        question = Question("post", _escape(sentence))
        first = content[line_of(origin[start])][0]
        held = (first, content[line_of(origin[end])][0])
        out.append((first, held, closing(origin[end]), FoundQuestion(question, None, False, raw=whole)))
    for line, index in last_on_line.items():
        if line in extra:
            pos, held, mark, q = out[index]
            out[index] = (pos, held, mark, FoundQuestion(q.question, None, False, tuple(extra[line]), whole))
    return out


_CLOSING = frozenset(")]}\"'\u201d\u2019\u00bb*_~")
_FOOTNOTE = re.compile(r"\[\^[^\]\s]{1,32}\]")


def _sentence_end(reduced: str, origin: list[int], end: int) -> bool:
    """The mark at reduced[end] ends its sentence: markup was dropped right
    after it, such as the closing backtick of `` `a?` ``; or it is a `?` and
    no letter, digit or `_` follows it (`?!`, `?",`, `?—`, `?|`, `?<br>`);
    or whitespace or the end follows it, after any closing punctuation,
    leftover `*`, `_` or `~` and a footnote mark such as `[^1]`."""
    after = end + 1
    n = len(reduced)
    if after < n and origin[after] != origin[end] + 1:
        return True
    if reduced[end] == "?":
        return after >= n or not (reduced[after].isalnum() or reduced[after] == "_")
    while after < n and reduced[after] in _CLOSING:
        after += 1
    m = _FOOTNOTE.match(reduced, after)
    if m:
        after = m.end()
    return after >= n or reduced[after].isspace()


def _escape(text: str) -> str:
    """text with a backslash before each ASCII punctuation character, which
    reduce_markup turns back into that character, so that reduce_markup
    gives text back unchanged."""
    return "".join("\\" + c if c in _ESCAPABLE else c for c in text)


def _item_question(item: _Item, number: int) -> FoundQuestion:
    lines = tuple(line for line in item.lines[1:] if line_kind(line) is not None)
    text = "\n".join(item.lines)
    return FoundQuestion(Question("post", text), number, item.deferred, lines, text)


def find_questions(body: str, in_code: bool = False) -> list[FoundQuestion]:
    """The questions in a post's body: each item of an open-questions
    section and each other sentence ending in `?`, none in code, `>` lines
    or prose's footer (inquisitor spec: *A question in a post is a listed
    item or a sentence ending in a question mark*). The post hook and vet's
    first call both call this; the answer service calls it on a bot's
    Linear or Discord message.

    A section starts at a heading (ATX or setext), a bold label or a plain line ending in
    `:` whose text begins with a question or deferral label, and runs to the
    next heading or bold label. Section items are numbered from 1 through
    the whole post, deferred ones included; a list nested in an item, and lines
    continuing it, are part of that item. Every other paragraph and list
    item outside a section, and every heading and label line, a section's
    own included, is searched for sentences. The questions come in the
    order the body holds them.

    The markdown is read twice (inquisitor spec: *Questions in a post are
    found by two readings*). The hiding reading hides closed code fences,
    indented code blocks and HTML comments that fill whole lines. The plain
    reading reads those lines as literal text, and begins no section. Both
    reduce all other inline markup alike. Without in_code, only the hiding
    reading's questions come back: the answer service asks for those.

    With in_code, as vet's first call and the post hook ask, more come back,
    each with in_code set:
    - each sentence the plain reading finds whose hash no hiding-reading
      question has, nor a sentence of a hiding-reading section item;
    - for each `?` with no letter or digit after it that closes no question
      of either reading, outside `>` and related/tag lines, a sentence
      ending there (_backstop), so no markup misread hides it from vetting.
    Sentences with the same hash come back once."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and _FOOTER.fullmatch(lines[-1].strip()):
        lines.pop()

    found = _read(lines, False, True)
    if not in_code:
        return [q for _, _, _, q in found]
    seen = {_hash(q) for _, _, _, q in found}
    seen.update(_item_sentences(found, _read(lines, False, False)))
    plain = _read(lines, True, False)
    closed = {mark for _, _, mark, _ in found} | {mark for _, _, mark, _ in plain}
    union: list[tuple[int, FoundQuestion]] = []
    sentence_hashes: set[str] = set()
    for start, _, _, q in found:
        if q.item is None:
            key = _hash(q)
            if key in sentence_hashes:
                continue
            sentence_hashes.add(key)
        union.append((start, q))
    for start, _, _, q in plain + _backstop(lines, closed):
        key = _hash(q)
        if key in seen:
            continue
        seen.add(key)
        union.append((start, FoundQuestion(q.question, None, False, q.lines, q.raw, True)))
    union.sort(key=lambda entry: entry[0])
    return [q for _, q in union]


def _item_sentences(found: list[_Found], loose: list[_Found]) -> set[str]:
    """The hashes of the section items' sentences: each sentence of loose,
    the hiding reading with sections off, lying wholly on one item's lines
    and found in that item's text, in order. A sentence only partly on the
    item's lines is not the item's: with sections off, a line after an
    item can read differently, such as code read as text. Nor is one
    missing from the item's text, which markup across the item's
    paragraphs can hide it from."""
    owner: dict[int, int] = {}
    texts: list[str] = []
    for _, held, _, q in found:
        if q.item is not None:
            for line in held:
                owner[line] = len(texts)
            texts.append(question_text(q.question))
    cursor = [0] * len(texts)
    out: set[str] = set()
    for _, held, _, q in loose:
        k = owner.get(held[0], -1)
        if k < 0 or any(owner.get(line, -1) != k for line in held):
            continue
        text = question_text(q.question)
        at = texts[k].find(text, cursor[k])
        if at >= 0:
            cursor[k] = at + len(text)
            out.add(question_hash(text))
    return out


def _backstop(lines: list[str], closed: set[tuple[int, int]]) -> list[_Found]:
    """A sentence for each `?` that no letter or digit follows on the line
    as written, which is every `?` that might end a sentence, and that
    closes no question either reading found, outside `>` lines and the
    lines line_kind names. It starts after the line's previous such `?`,
    or after a later `.` or `!` that whitespace follows, or else at the
    line's start. So markup either reading misread hides no question."""
    out: list[_Found] = []
    for i, line in enumerate(lines):
        if _QUOTE.match(line) or line_kind(line) is not None:
            continue
        begin = 0
        for ordinal, at in enumerate(_marks(line), 1):
            entity = _QUESTION_ENTITY.match(line, at)
            after = entity.end() if entity else at + 1
            # Only a letter or digit right after it keeps it in a word: a
            # `_`, `*` or `~` there may close emphasis GitHub reduces.
            if after < len(line) and line[after].isalnum():
                continue
            if (i, ordinal) not in closed:
                start = begin
                for k in range(at - 1, begin - 1, -1):
                    if line[k] in ".!" and line[k + 1].isspace():
                        start = k + 1
                        break
                sentence = " ".join((line[start:at] + "?").split())
                question = Question("post", _escape(sentence))
                out.append((i, (i, i), (i, ordinal), FoundQuestion(question, None, False, raw=line)))
            begin = after
    return out


def _hash(q: FoundQuestion) -> str:
    return question_hash(question_text(q.question))


def _comment_ends(lines: list[str]) -> list[int]:
    """For each line that opens an HTML comment filling whole lines, the
    line that closes it, or -1: the line starts with `<!--`, after
    whitespace, and only whitespace follows the first `-->` after that on
    its line. CommonMark also takes `<!-->` and `<!--->` for a comment.
    One pass from the end finds each line's nearest closing line."""
    out = [-1] * len(lines)
    # The nearest later line holding `-->`, if nothing but whitespace
    # follows its first `-->`; otherwise -1.
    nearest = -1
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("<!--"):
            rest = stripped[4:]
            if rest.startswith(">") or rest.startswith("->"):
                out[i] = i if rest in (">", "->") else -1
            elif "-->" in rest:
                out[i] = i if rest.index("-->") == len(rest) - 3 else -1
            else:
                out[i] = nearest
        if "-->" in lines[i]:
            nearest = i if not lines[i].split("-->", 1)[1].strip() else -1
    return out


def _read(lines: list[str], plain: bool, sections: bool) -> list[_Found]:
    """The questions in a post's lines, by find_questions' hiding reading,
    or with plain by its plain reading; with sections, an open-questions
    section's items are items, otherwise sentences.

    Both readings find the same code blocks and comments. The hiding
    reading skips their lines; the plain reading reads them as text, in
    paragraphs of their own, so text outside them reads alike in both."""
    found: list[_Found] = []
    number = 0
    section: Section | None = None
    item: _Item | None = None
    paragraph: list[tuple[int, str]] = []
    blank_before = False
    fence: str | None = None
    # An indented code block: lines indented 4 or more after a blank line
    # (or at the post's start), outside any paragraph, item or list.
    code_block = False
    in_list = False
    # The text columns of the open list items, innermost last.
    columns: list[int] = []
    # A fence hides lines only when both hold:
    # - it is placed under 4 columns into its context: the top level, or a
    #   list item's text;
    # - a later line closes it; in a list, before any line less indented
    #   than the fence.
    # Any other fence line is text.
    closes = _fence_closes(lines)
    widths = _MinTable([_width(line) if line.strip() else 1 << 30 for line in lines] or [0])
    comment_ends = _comment_ends(lines)
    # The last line of the HTML comment being read.
    comment_end = -1

    # Fence lines read as text. Once a fence line is text, the line that
    # would have closed it is read as text too, though it might open a
    # fence of its own, and so on down the chain: reading it as an opener
    # could hide lines that GitHub shows as text.
    demoted = [False] * len(lines)

    def hides(i: int, least: int) -> bool:
        """The fence line i opens is closed before a line indented less than
        least, and line i was not itself read as text by an earlier
        demotion (demote)."""
        close = closes[i]
        return (not demoted[i] and close >= 0
                and (least == 0 or widths.least(i + 1, close) >= least))

    def demote(i: int) -> None:
        while i >= 0 and not demoted[i]:
            demoted[i] = True
            i = closes[i]

    def escaped(text: str, fence: str) -> str:
        """text with the backticks of the fence it starts with escaped, so
        they open no code span that could hide the lines after it."""
        return text.replace("`", "\\`", len(fence)) if fence[0] == "`" else text

    # The paragraph is code or comment lines, read literally.
    literal = [False]

    def keep(i: int, text: str) -> None:
        """In the plain reading, read line i, a code or comment line, as
        the literal text GitHub shows; the hiding reading skips it."""
        if plain:
            paragraph.append((i, text))
            literal[0] = True

    def lazy(i: int) -> bool:
        """Line i, indented 4 or more under a paragraph line, continues the
        paragraph as text, though it holds a whole comment."""
        return bool(paragraph) and _width(lines[i]) >= 4

    def end_paragraph() -> None:
        found.extend(_paragraph_questions(paragraph, literal[0]))
        paragraph.clear()
        literal[0] = False

    def end_item() -> None:
        nonlocal item, number
        if item is not None:
            number += 1
            found.append((item.start, tuple(item.at), (-1, 0), _item_question(item, number)))
            item = None

    # A heading's, bold label's or colon label's text, searched for a
    # question, with the left-out lines (line_kind) directly after it, which
    # are that question's extra lines.
    heading: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if i <= comment_end:
            continue
        if heading:
            if line_kind(line) is not None:
                heading.append((i, line))
                continue
            found.extend(_paragraph_questions(heading))
            heading.clear()
        indented = line.expandtabs(4).startswith("    ")
        if code_block:
            if indented or not line.strip():
                if line.strip():
                    keep(i, line)
                else:
                    end_paragraph()
                continue
            code_block = False
            end_paragraph()
        if (fence is None and indented and not paragraph and item is None and not in_list
                and (blank_before or i == 0)):
            code_block = True
            keep(i, line)
            continue
        if fence is not None:
            if _closes(line, fence):
                fence = None
                end_paragraph()
            else:
                keep(i, line)
            continue
        if comment_ends[i] >= 0 and not lazy(i):
            # GitHub hides the comment, and it ends a paragraph.
            end_paragraph()
            comment_end = comment_ends[i]
            for k in range(i, comment_end + 1):
                keep(k, lines[k])
            end_paragraph()
            blank_before = True
            continue
        if paragraph and item is None and not in_list and _SETEXT.fullmatch(line):
            # A setext heading: the paragraph above is its text.
            section = _label(" ".join(text for _, text in paragraph))
            heading.extend(paragraph)
            paragraph.clear()
            in_list = False
            blank_before = False
            continue
        kind = _classify(line)
        stripped = line.strip()
        if kind.type == "item":
            ordinal = line.lstrip()[:_marker_length(line.lstrip()) - 1]
            # Only a bullet or `1.` item with text starts a list inside a paragraph.
            if paragraph and not in_list and item is None and (not kind.text or ordinal not in ("", "1")):
                kind = _Line("plain", line)
        if not (in_list or item is not None):
            columns.clear()
        # A line after a blank line belongs to the innermost item its indent reaches.
        depth = _width(line) if kind.type == "item" or (stripped and blank_before) else None
        while depth is not None and columns and columns[-1] > depth:
            columns.pop()
        list_column: int = columns[-1] if columns else 0
        if kind.type == "fence":
            width = _width(line)
            listed_in: bool = in_list or item is not None
            context = list_column if listed_in and width >= list_column else 0
            if not (width < context + 4 and hides(i, width if listed_in else 0)):
                demote(i)
                line = escaped(line, kind.fence)
                kind = _Line("plain", line)
        # A fence on a list item's marker line, as in `- ```sh`.
        marker_fence: str | None = None
        if kind.type == "item":
            columns.append(kind.column)
            opened = _item_fence(kind)
            if opened is not None:
                if hides(i, kind.column):
                    marker_fence = opened
                else:
                    demote(i)
                    kind = _Line("item", escaped(kind.text, opened), kind.indent, column=kind.column)
                    line = escaped(line, opened)
        if kind.type == "fence":
            end_paragraph()
            end_item()
            fence = str(kind.fence)
            keep(i, line)
            end_paragraph()
            blank_before = False
            in_list = in_list and line[:1].isspace()
            continue
        if kind.type == "blank":
            end_paragraph()
            blank_before = True
            continue
        # A break, heading or label indented to an open item's text is in that item.
        lead = len(line) - len(line.lstrip())
        in_item: bool = item is not None and lead >= item.indent + 2
        if kind.type == "quote" or (kind.type == "break" and not in_item):
            end_paragraph()
            end_item()
            blank_before = False
            in_list = in_list and line[:1].isspace()
            continue
        if kind.type in ("heading", "bold") and not in_item:
            end_paragraph()
            end_item()
            section = kind.section
            in_list = in_list and line[:1].isspace()
            heading.append((i, kind.text))
            blank_before = False
            continue
        listed = kind.type == "item"
        if section is not None and sections:
            if listed and (item is None or kind.indent <= item.indent):
                end_paragraph()
                end_item()
                item = _Item(i, kind.indent, [kind.text], section == "deferral", [i])
                blank_before = False
                in_list = True
                fence = marker_fence
                continue
            if item is not None and (not blank_before or line[:1].isspace()):
                if blank_before:
                    # An empty line keeps the paragraph break in the item's
                    # text, so no link or title spans it.
                    item.lines.append("")
                item.lines.append(line)
                item.at.append(i)
                if marker_fence is not None:
                    fence = marker_fence
                # After a break only an indented line continues the item.
                blank_before = kind.type == "break"
                continue
            end_item()
        # An indented line, or a lazy one with no blank line before it, stays in the list.
        in_list = listed or (in_list and (line[:1].isspace() or not blank_before))
        if kind.type == "colon":
            end_paragraph()
            section = kind.section
            heading.append((i, line))
            blank_before = False
            continue
        if listed:
            end_paragraph()
            fence = marker_fence
            if marker_fence is None:
                paragraph.append((i, kind.text))
            else:
                keep(i, kind.text)
                end_paragraph()
        else:
            paragraph.append((i, line))
        blank_before = False
    found.extend(_paragraph_questions(heading))
    end_paragraph()
    end_item()
    found.sort(key=lambda pair: pair[0])
    return found
