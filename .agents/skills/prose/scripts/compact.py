"""Compaction: rule 8 ("what is, not how it got here") over a whole file.

Three parts, all standard library only:

- `passages()`: the bloat detectors. They flag passages a compaction should
  answer for: history, repetition, amendment notes, long rejected
  alternatives, stale references, narrative words and filler.
- `due()`: the cheap triggers `prose check` runs on each changed doc. A doc
  agents read often is due for compaction when, since its last compaction,
  its flagged text has grown by both a set share of the file and a set
  number of bytes, or the doc has grown by both a set share and a set number
  of bytes.
- `brief()`, `verify()` and `review()`: `prose compact <file>` prints the
  brief a compactor subagent works from, listing every flagged passage;
  `--verify` checks the result, including the compactor's answer for each
  passage; and `--review` prints the brief for a reviewer of each removal,
  rewrite and kept passage.

Read ../DECISIONS.md (*Compaction*) before changing a default here.
"""

import bisect
import collections
import contextlib
import difflib
import getpass
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import stat
import subprocess
import tempfile
import time
from typing import NamedTuple, Optional

try:
    import fcntl
except ImportError:  # Windows: the lock does nothing, see _snapshot_lock
    fcntl = None

HERE = pathlib.Path(__file__).resolve().parent
BRIEF = HERE.parent / "compact.md"

# A doc agents read often is due for compaction when the passages the
# detectors flag hold at least this many bytes more than they did at its last
# compaction (about 250 tokens, paid on every read)...
DEFAULT_FLAGGED = 1_000
# ... and those added bytes are at least this share, in percent, of the
# file's current size, since a compaction's cost grows with the whole file.
DEFAULT_FLAGGED_SHARE = 10
# Once compacted, it is also due when it has grown by this share, in
# percent, since its last compaction.
DEFAULT_GROWTH = 50
# ... and only when it has also grown by at least this many bytes, so a
# small doc is not due for a few added lines.
DEFAULT_GROWTH_BYTES = 2_000
# A doc that its name, place, read-first link or declaration does not make
# read often is read often when commits since its last compaction imply at
# least this many reads of it.
DEFAULT_READS = 20
# A commit that shrinks a file by at least this share, in percent, counts as
# a compaction of it.
COMPACTED_SHARE = 10
# How far back, in commits that changed the file, to look for the last
# compaction.
HISTORY_DEPTH = 500
# How many commits back from HEAD the read count looks, so the trigger stays
# cheap on every commit.
READS_DEPTH = 300

# The .gitattributes names a repository sets to override the defaults.
ATTR_DECLARE = "prose-compact"
ATTR_GROWTH = "prose-compact-growth"
ATTR_GROWTH_BYTES = "prose-compact-growth-bytes"
ATTR_FLAGGED = "prose-compact-flagged"
ATTR_FLAGGED_SHARE = "prose-compact-flagged-share"
ATTR_READS = "prose-compact-reads"
ATTR_ATTRIBUTION = "prose-compact-attribution"

# Exit codes of `prose compact`: the brief was printed (the step is the
# caller's to do), the result passed, the result failed a check.
BRIEF_PRINTED = 4
VERIFIED = 0
FAILED = 1


# ---------------------------------------------------------------------------
# Which files are current-state docs
# ---------------------------------------------------------------------------

# Names that are current-state docs agents read before working, wherever they
# sit. Compared without case.
DEFAULT_NAMES = {"decisions.md", "skill.md", "agents.md", "claude.md"}


def default_current(path):
    """True when, with no `prose-compact` attribute, path is a current-state
    doc agents read before working: a DECISIONS.md, SKILL.md, AGENTS.md or
    CLAUDE.md; an architecture doc; or an OpenSpec spec, proposal or design
    that is not archived."""
    pure = pathlib.PurePosixPath(path)
    name = pure.name.lower()
    if name in DEFAULT_NAMES:
        return True
    if name.startswith("architecture") and name.endswith(".md"):
        return True
    parts = pure.parts
    if "openspec" not in parts:
        return False
    rest = parts[parts.index("openspec") + 1:]
    if rest[:1] == ("specs",):
        return name == "spec.md"
    if rest[:1] == ("changes",) and "archive" not in rest:
        return len(rest) == 3 and name in ("proposal.md", "design.md")
    return False


class Settings(NamedTuple):
    current: bool
    growth: int
    binary: bool = False
    declared: bool = False      # `prose-compact`: read often, whatever its name
    flagged: int = DEFAULT_FLAGGED
    reads: int = DEFAULT_READS
    drop_attribution: bool = False  # `prose-compact-attribution=drop`
    exempt: bool = False        # `-prose-compact`
    growth_bytes: int = DEFAULT_GROWTH_BYTES
    flagged_share: int = DEFAULT_FLAGGED_SHARE


def _number(value, default):
    return int(value) if value is not None and re.fullmatch(r"[0-9]{1,12}", value) else default


def settings(paths, root):
    """{path: Settings} from the staged .gitattributes, falling back to the
    defaults. `prose-compact` declares a doc read often, `-prose-compact`
    exempts one, the numeric attributes replace the growth share, the
    bytes of growth, the flagged bytes, the flagged share and the reads
    needed, and `prose-compact-attribution=drop`
    has the compactor drop "who decided" credits. Outside a repository, or
    when git fails, every path gets the defaults."""
    found = {path: {} for path in paths}
    names = [ATTR_DECLARE, ATTR_GROWTH, ATTR_GROWTH_BYTES, ATTR_FLAGGED, ATTR_FLAGGED_SHARE,
             ATTR_READS, ATTR_ATTRIBUTION, "diff"]
    if paths and root is not None:
        try:
            result = subprocess.run(
                ["git", "check-attr", "--cached", "-z", "--stdin"] + names,
                cwd=root, input=("\0".join(paths) + "\0").encode("utf-8", "surrogateescape"),
                capture_output=True, check=False)
        except OSError:
            result = None
        if result is not None and result.returncode == 0:
            fields = result.stdout.decode("utf-8", "surrogateescape").split("\0")
            for index in range(0, len(fields) - 2, 3):
                path, name, value = fields[index:index + 3]
                if path in found and value != "unspecified":
                    found[path][name] = value
    out = {}
    for path, attrs in found.items():
        declared = attrs.get(ATTR_DECLARE)
        current = default_current(path) if declared is None else declared != "unset"
        # `-diff`, or `binary`, which sets it, is how a repository tells git
        # a file is binary.
        out[path] = Settings(current, _number(attrs.get(ATTR_GROWTH), DEFAULT_GROWTH),
                             attrs.get("diff") == "unset",
                             declared is not None and declared != "unset",
                             _number(attrs.get(ATTR_FLAGGED), DEFAULT_FLAGGED),
                             _number(attrs.get(ATTR_READS), DEFAULT_READS),
                             attrs.get(ATTR_ATTRIBUTION) == "drop", declared == "unset",
                             _number(attrs.get(ATTR_GROWTH_BYTES), DEFAULT_GROWTH_BYTES),
                             _number(attrs.get(ATTR_FLAGGED_SHARE), DEFAULT_FLAGGED_SHARE))
    return out


# ---------------------------------------------------------------------------
# History markers
# ---------------------------------------------------------------------------

DATE = r"(?:19|20)[0-9]{2}-[01][0-9]-[0-3][0-9]"

# Each is (name, pattern). Measured on 26 docs from this repository and
# igor, listed in ../DECISIONS.md (*Compaction*): these fire on narrative a
# compaction removes, and not on a decision's attribution ("(Adam,
# 2026-10-24)"), a measurement's date, or a rejected alternative stated on
# its own.
MARKERS = [
    ("dated revision", re.compile(
        r"\b(?:revised|updated|amended|corrected|superseded|replaced|dropped|removed|"
        r"reversed|reverted|changed|renamed)\s+(?:on\s+|in\s+)?\(?" + DATE, re.I)),
    ("dated span", re.compile(r"\b(?:until|from|before)\s+" + DATE, re.I)),
    # Case matters here: a label is capitalised. Ignoring case would match a
    # sentence that wraps just before a lowercase "edit:".
    ("history label", re.compile(
        r"(?:^|[.(][ \t]*|\*\*|#[ \t]*)(?:History|Update|Updated|Revised|Superseded|Edit|Edited)"
        r"(?::|\s+(?:on\s+)?" + DATE + r")", re.M)),
    ("previously", re.compile(r"\bpreviously\b", re.I)),
    ("formerly", re.compile(r"\b(?:formerly|originally|hitherto)\b", re.I)),
    ("was changed", re.compile(
        r"\b(?:was|were|has been|have been|had been)\s+(?:changed|replaced|renamed|revised|"
        r"reversed|switched)\s+(?:to|by|with|from|in favou?r of)\b", re.I)),
]

# `previously` is adjectival after a determiner ("a previously issued
# token"), which describes data, not the doc's past.
DETERMINER = re.compile(
    r"(?:\b(?:a|an|the|any|all|some|its|their|every|each|no)|'s|’s)\s+$", re.I)


class Marker(NamedTuple):
    line: int
    name: str
    words: str


# A quotation in double quotes or guillemets, which may wrap onto one more
# line, as quotations in wrapped Markdown do.
QUOTED = re.compile(r"\"[^\"\n]*(?:\n[^\"\n]*)?\"|“[^”\n]*(?:\n[^”\n]*)?”|«[^»\n]*(?:\n[^»\n]*)?»")


def masked_lines(text):
    """The text's lines with what is quoted rather than said blanked, as the
    bloat detectors read them (_mask): fenced blocks, YAML front matter,
    inline code, and text in double quotes or guillemets. Quoted text is
    blanked because a doc that names a marker, such as this skill's rules,
    is quoting it, not using it."""
    return _mask(_lf(text)).split("\n")


def _unfenced_code_kept(text):
    """The text's lines with fenced blocks blanked and inline code kept.
    gone_terms calls this to find code spans, and _unfenced_code calls it
    and then blanks inline code too. --verify's heading check does not call
    it: that check reads every heading-shaped line, code blocks included."""
    lines = text.split("\n")
    return ["" if code else line for line, code in zip(lines, _fenced(lines))]


def _indent(text):
    """The width of text's leading whitespace, a tab counted as four."""
    return len(text[:len(text) - len(text.lstrip())].expandtabs(4))


# A list marker with a block quote after it, as in "- > text".
LIST_QUOTE = re.compile(r"^[ \t]*(?:[-*+]|[0-9]{1,9}[.)])[ \t]+(?=>)")


def _opens(unquoted):
    """(fence, column) when unquoted, a line without its quote markers,
    opens a fenced block: the fence's characters and the column they start
    at, after any indentation and list marker; else None. A fence after a
    list marker and a quote marker, "- > ```sh", opens at the column left
    once both markers are removed. Its closer, "  > ```", sits at the same
    column once its quote marker is removed, so it closes the block."""
    unquoted = _unquoted(LIST_QUOTE.sub("", unquoted, count=1))
    opening = FENCE.match(unquoted.lstrip())
    return (opening.group(1), _indent(unquoted) + opening.start(1)) if opening else None


def _closes(fence, unquoted):
    """True when unquoted, a line without its quote markers, closes the
    fenced block fence, as _opens gave it: the fence's character alone, at
    least as many as opened it, indented at most three columns more than
    the opener. "```python" inside a ``` block is code, and so is a ``` line
    indented four more, as in a docstring's example. _fenced and
    _paragraphs both close fences here, so they agree."""
    marker, column = fence
    return _indent(unquoted) - column <= 3 and bool(
        re.fullmatch(re.escape(marker[0]) + "{%d,}[ \t]*" % len(marker), unquoted.lstrip()))


def _fenced(lines):
    """[bool] for each line: True when it opens, closes or sits in a fenced
    block. A fence may open after a list marker or inside a block quote, as
    _paragraphs reads it, so every scanner agrees on what is code."""
    out, fence = [], None
    for line in lines:
        unquoted = _unquoted(line)
        if fence:
            if _closes(fence, unquoted):
                fence = None
            out.append(True)
            continue
        fence = _opens(unquoted)
        out.append(bool(fence))
    return out


def _unfenced_code(text):
    """The text's lines with fenced blocks and inline code blanked."""
    return [re.sub(r"`[^`]*`", "``", line) for line in _unfenced_code_kept(text)]


def _marker_hits(joined):
    """(rank, name, offset, words) for each history marker in joined, a
    masked text. The offset is the marker's first word, past the full stop,
    bracket, emphasis or `#` a label's pattern starts with, so it falls in
    the marker's own sentence."""
    for rank, (name, pattern) in enumerate(MARKERS):
        for match in pattern.finditer(joined):
            found = match.group(0)
            start = match.start() + len(found) - len(found.lstrip(".(*# \t"))
            if name == "previously" and DETERMINER.search(joined[max(0, start - 40):start]):
                continue
            yield rank, name, start, " ".join(match.group(0).split()).strip(" .(*#")


def history_markers(text, exempt=()):
    """[Marker] for each line a marker starts on, at most one per line. The
    patterns run over the whole masked text, so a marker that wrapped onto
    the next line is still found. A marker starting inside one of exempt,
    [(start, end)] offsets into text, is left out."""
    joined = "\n".join(masked_lines(text))
    best = {}  # line: (pattern rank, Marker)
    for rank, name, start, words in _marker_hits(joined):
        if any(low <= start < high for low, high in exempt):
            continue
        number = joined.count("\n", 0, start) + 1
        if number in best and best[number][0] <= rank:
            continue
        best[number] = (rank, Marker(number, name, words))
    return [best[number][1] for number in sorted(best)]


# ---------------------------------------------------------------------------
# Bloat detectors
# ---------------------------------------------------------------------------
#
# Each detector flags passages, sentences or whole paragraphs, that a
# compaction should answer for: remove, rewrite shorter, or keep with a
# reason. They are simple patterns, predictable over cleverness: a false flag
# costs the compactor one `kept:` line. Fenced code, inline code and quoted
# text are skipped, as by the history-marker scan.

class Passage(NamedTuple):
    start: int    # first line, from 1
    end: int      # last line
    kinds: tuple  # the detectors that flagged it, in KINDS order
    text: str     # as the file has it
    note: str = ""


KINDS = ("history", "repetition", "amendment", "rejected", "stale reference", "narrative",
         "filler")

AMENDMENT = re.compile(
    r"\b(?:amended|superseded|withdrawn)\s+(?:by|in|on)\b"
    r"|\bwithdrawn\b"
    r"|\bas (?:first|originally|initially) (?:written|drafted|proposed|stated|specified)\b"
    r"|\b(?:amendment|erratum|errata)\b", re.I)

NARRATIVE = re.compile(
    r"\b(?:initially|at first|originally|turned out|ended up|back then|used to be)\b"
    r"|\b(?:we|I|they)\s+(?:first\s+|then\s+|later\s+)?(?:tried|attempted)\b"
    r"|\bpreviously\b", re.I)

# Prose's rule 9 cuts filler and throat-clearing, and its list of how agents
# cheat names a "Note:" line added in place of a rewrite.
FILLER = re.compile(
    r"(?:^|(?<=[.!?]\s)|(?<=^[-*+]\s))(?:\*\*|_)?(?:Note|NB|Clarification|Important)(?:\*\*|_)?:"
    r"|\b(?:it is|it's) (?:worth|important to) (?:noting|note|mentioning|mention|remembering)\b"
    r"|\bit should be noted\b|\bnote that\b|\bneedless to say\b|\bit goes without saying\b"
    r"|\bas (?:mentioned|noted|described|discussed|stated|explained) (?:above|earlier|before)\b"
    r"|(?:^|(?<=[.!?]\s))(?-i:In other words)\b|\bbasically\b|\bessentially\b", re.I | re.M)

REJECTED = re.compile(r"^[ \t]*(?:[-*+]|[0-9]{1,9}[.)])?[ \t]*(?:\*\*|__)?Rejected\b")
LABEL_ONLY = re.compile(r"[ \t]*(?:\*\*|__)?Rejected[.:]?(?:\*\*|__)?[.:]?[ \t]*")
ITEM = re.compile(r"^[ \t]*(?:[-*+]|[0-9]{1,9}[.)])[ \t]+")
SENTENCE_END = re.compile(r"[.!?][)\]*_\"”»']*\s+")
SENTENCE_START = re.compile(r"[A-Z`*(\"«“\[_]")

# Repetition, as spec-check's duplicate check: a sentence of at least
# REPEAT_WORDS words stated twice, once normalised; or any run of
# OVERLAP_WORDS words two sentences share.
REPEAT_WORDS = 10
OVERLAP_WORDS = 8

BACKTICKS = re.compile(r"`+")
FUNCTION = re.compile(r"([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)*)\([^()]*\)")
PATH_SPAN = re.compile(r"[\w.-]*(?:/[\w.-]+)+/?")


def _code_spans(text):
    """[(start, end)] of each inline code span in text, as CommonMark reads
    one: a run of backticks opens it and the next run of exactly as many
    closes it. A span may wrap onto one more line, as quotations may, never
    across a blank one; a run with no close is literal backticks."""
    out, pos = [], 0
    while True:
        opening = BACKTICKS.search(text, pos)
        if opening is None:
            return out
        pos = opening.end()
        # The span ends by the end of the next line.
        first = text.find("\n", pos)
        limit = len(text) if first < 0 else text.find("\n", first + 1)
        limit = len(text) if limit < 0 else limit
        closing = BACKTICKS.search(text, pos, limit)
        while closing is not None and len(closing.group(0)) != len(opening.group(0)):
            closing = BACKTICKS.search(text, closing.end(), limit)
        if closing is not None:
            out.append((opening.start(), closing.end()))
            pos = closing.end()


def _mask(text, inline_code=True, fill=" ", quotes=True):
    """text with what is quoted rather than said blanked to spaces, each line
    keeping its length, so offsets into it are offsets into text: fenced
    blocks, YAML front matter, with inline_code, inline code, and, with
    quotes, text in double quotes or guillemets. With fill "x", inline code
    and quotations are filled with "x" instead of spaces. That is the
    structure view: a line holding only code still belongs to its
    paragraph, and a sentence can start with code or a quotation."""
    out, lines = [], text.split("\n")
    # Front matter is a first line of `---` and a closing one; a lone `---`
    # on the first line is a horizontal rule.
    end = next((n for n in range(1, len(lines)) if lines[n].strip() == "---"), None) \
        if lines[:1] == ["---"] else None
    end = -1 if end is None else end
    # Fences are read after the front matter, so a fence-like line in it
    # opens nothing.
    code = [False] * (end + 1) + _fenced(lines[end + 1:])
    for number, line in enumerate(lines):
        out.append(" " * len(line) if number <= end or code[number] else line)
    joined = "\n".join(out)
    if inline_code:
        # A code span may wrap onto one more line, never across a blank one.
        pieces, last = [], 0
        for start, end in _code_spans(joined):
            pieces += [joined[last:start], re.sub(r"[^\n]", fill, joined[start:end])]
            last = end
        joined = "".join(pieces) + joined[last:]
    if not quotes:
        return joined
    return QUOTED.sub(lambda m: re.sub(r"[^\n]", fill, m.group(0)), joined)


class _Unit(NamedTuple):
    start: int  # offset in the text
    end: int


def _blocks(masked):
    """[_Unit] for each paragraph, list item, heading and table row of the
    masked text. A list item's continuation lines belong to it."""
    out, start, pos = [], None, 0
    for line in masked.split("\n"):
        end = pos + len(line)
        alone = HEADING.match(line) or line.lstrip().startswith("|")
        if not line.strip() or alone or ITEM.match(line):
            if start is not None:
                out.append(_Unit(start, last))
                start = None
            if alone:
                out.append(_Unit(pos, end))
            elif line.strip():
                start, last = pos, end
        else:
            if start is None:
                start = pos
            last = end
        pos = end + 1
    if start is not None:
        out.append(_Unit(start, last))
    return out


def _sentences(text, masked, block):
    """[_Unit] for each sentence of block: split after a full stop, question
    or exclamation mark outside code and quotes, before a capital letter,
    code span or opening mark. masked is the structure view (_mask with
    fill "x"), where code and quotations are not whitespace."""
    out, start = [], block.start
    for match in SENTENCE_END.finditer(masked, block.start, block.end):
        if match.end() < block.end and SENTENCE_START.match(text, match.end()):
            out.append(_Unit(start, match.end()))
            start = match.end()
    out.append(_Unit(start, block.end))
    return [unit for unit in out if text[unit.start:unit.end].strip()]


def _normal_words(text):
    """The words of text as repetition compares them: case folded, code
    marks and emphasis dropped, and punctuation at the ends of each word."""
    words = re.sub(r"[`*_]", "", text.casefold()).split()
    return [word.strip(".,;:!?()[]\"'«»“”") for word in words if word.strip(".,;:!?()[]\"'«»“”")]


def _tracked(root):
    out = _git(["ls-files", "-z"], root)
    return set(filter(None, (out or "").split("\0")))


# The last tracked set _lookup read, its size then, and what it built from it.
_LOOKUP = [None, -1, None]


def _lookup(tracked):
    """(folders, by_name) for the tracked set: every folder holding a
    tracked file, and {last part of a path: [tracked file or folder]}, so a
    name is compared only with the paths that end in the same part. Built
    once for the same set, which due() passes for every doc it checks."""
    if _LOOKUP[0] is tracked and _LOOKUP[1] == len(tracked):
        return _LOOKUP[2]
    folders = set()
    for name in tracked:
        cut = name.rfind("/")
        while cut > 0 and name[:cut] not in folders:
            folders.add(name[:cut])
            cut = name.rfind("/", 0, cut)
    by_name = {}
    for item in tracked | folders:
        by_name.setdefault(item[item.rfind("/") + 1:], []).append(item)
    _LOOKUP[:] = [tracked, len(tracked), (folders, by_name)]
    return folders, by_name


def _stale(spans, path, root, tracked):
    """The code spans, of [(offset, span)], that name a path, flag or
    function the repository no longer has. A path is checked only when its
    first directory is one the repository has, at its root or beside the
    doc, so a path in another repository a doc describes is not flagged; it
    is stale when no tracked file or directory has it, from the root, from
    the doc's directory, or as the end of a tracked path. A flag or a
    function call is stale when no tracked file other than a Markdown file
    or the doc itself holds it."""
    if root is None:
        return []
    folders, by_name = _lookup(tracked)
    here = str(pathlib.PurePosixPath(path).parent)

    def local(name):
        return os.path.normpath(os.path.join(here, name))

    def ours(name):
        first = name.split("/", 1)[0]
        return first in folders or local(first) in folders

    def known(name):
        """True when a tracked file or folder is name, or ends with it
        after a `/`."""
        return any(item == name or item.endswith("/" + name)
                   for item in by_name.get(name[name.rfind("/") + 1:], ()))

    def exists(name):
        name = name.rstrip("/")
        return known(name) or known(local(name))

    found, needles = [], {}
    for offset, span in spans:
        span = " ".join(span.split())  # a span may wrap onto a second line
        if " " not in span and not re.search(r"[<>*?{}$~\\]|^/|^\.git/|://", span):
            target = re.sub(r"(?:#.*|:[0-9]+(?:-[0-9]+)?)$", "", span)
            if "/" in target and PATH_SPAN.fullmatch(target) and ours(target) \
                    and not exists(target):
                found.append((offset, span))
                continue
        flag = FLAG.match(span)
        if flag:
            needles.setdefault(flag.group(0), []).append((offset, span))
            continue
        call = FUNCTION.fullmatch(span)
        if call:
            needles.setdefault(call.group(1).rsplit(".", 1)[-1] + "(", []).append((offset, span))
    if needles:
        # Set against the user's config, as in _grep, so each output line is
        # the matched text alone, with no line number or column before it.
        args = ["git", "-c", "core.quotePath=false", "-c", "grep.lineNumber=false",
                "-c", "grep.column=false", "-c", "color.grep=never", "grep", "--cached", "-h",
                "-o", "-I", "-F", "--no-color"]
        for needle in sorted(needles):
            args += ["-e", needle]
        args += ["--", ".", ":(exclude)*.md", ":(exclude)*.MD", f":(exclude,literal){path}"]
        try:
            result = subprocess.run(args, cwd=root, capture_output=True, check=False)
        except OSError:
            result = None
        # git grep exits 1 when nothing matched; anything else is a failure,
        # and a check that could not run flags nothing.
        if result is not None and result.returncode in (0, 1):
            held = set(result.stdout.decode("utf-8", "surrogateescape").split("\n"))
            for needle, places in needles.items():
                if needle not in held:
                    found.extend(places)
    return sorted(found)


def passages(text, path="", root=None, tracked=None):
    """[Passage] for every passage the detectors flag in text, the file at
    path in the repository at root (None outside one, which skips the
    stale-reference check), in order. Passages that overlap are merged, so
    each line belongs to at most one."""
    text = _lf(text)
    # The patterns read masked, where code and quotations are spaces; the
    # paragraphs and sentences are read from structure, where they are not.
    masked, structure = _mask(text), _mask(text, fill="x")
    starts = [0] + [index + 1 for index, char in enumerate(text) if char == "\n"]
    blocks = _blocks(structure)
    sentences = [unit for block in blocks for unit in _sentences(text, structure, block)]
    sentence_starts = [unit.start for unit in sentences]
    hits = {}  # (start, end): [kinds], note

    def flag(unit, kind, note=""):
        entry = hits.setdefault((unit.start, unit.end), [[], ""])
        if kind not in entry[0]:
            entry[0].append(kind)
        if note and not entry[1]:
            entry[1] = note

    def sentence_at(offset):
        index = bisect.bisect_right(sentence_starts, offset) - 1
        if index >= 0 and offset < sentences[index].end:
            return sentences[index]
        return None

    def line_of(offset):
        return bisect.bisect_right(starts, offset)

    def pattern_hits(kind, pattern, veto=None):
        for match in pattern.finditer(masked):
            if veto and veto(match):
                continue
            unit = sentence_at(match.start())
            if unit is not None:
                flag(unit, kind)

    for _, _, offset, _ in _marker_hits(masked):
        unit = sentence_at(offset)
        if unit is not None:
            flag(unit, "history")

    def determiner(match):
        return match.group(0).lower() == "previously" and \
            DETERMINER.search(masked[max(0, match.start() - 40):match.start()])

    pattern_hits("amendment", AMENDMENT)
    pattern_hits("narrative", NARRATIVE, determiner)
    pattern_hits("filler", FILLER)

    # Repetition: a whole sentence again, or a long run of words again. The
    # words are read masked, so code and quotations repeat nothing.
    seen, shingles = {}, {}
    for index, unit in enumerate(sentences):
        if HEADING.match(text[unit.start:unit.end]):
            continue
        words = _normal_words(masked[unit.start:unit.end])
        key = " ".join(words)
        if len(words) >= REPEAT_WORDS and key in seen:
            flag(unit, "repetition", f"same as line {line_of(sentences[seen[key]].start)}")
            continue
        seen.setdefault(key, index)
        earlier = None
        for at in range(len(words) - OVERLAP_WORDS + 1):
            run = " ".join(words[at:at + OVERLAP_WORDS])
            first = shingles.setdefault(run, index)
            if first != index and earlier is None:
                earlier = first
        if earlier is not None:
            flag(unit, "repetition", f"overlaps line {line_of(sentences[earlier].start)}")

    # Long rejected alternatives: a "Rejected" paragraph or item, or each
    # item of a list a "Rejected" label opens, holding more than its first
    # sentence, which names the alternative, and one sentence of reason; or
    # a "Rejected" section, whose heading names it, of more than one
    # sentence.
    def long(units, allowed=2):
        return sum(len(_sentences(text, structure, unit)) for unit in units) > allowed

    def close(section):
        if section and long(section, 1):
            flag(_Unit(section[0].start, section[-1].end), "rejected")

    section, under_label = None, False
    for block in blocks:
        body = masked[block.start:block.end]
        heading = HEADING.match(body)
        if heading:
            close(section)
            section = [] if re.match(r"(?:\*\*|__)?Rejected\b", heading.group(1)) else None
            under_label = False
            continue
        if section is not None:
            section.append(block)
            continue
        item = ITEM.match(body)
        if REJECTED.match(body):
            if not item and LABEL_ONLY.fullmatch(body):
                under_label = True
            elif long([block]):
                flag(block, "rejected")
            continue
        if under_label and item:
            if long([block]):
                flag(block, "rejected")
            continue
        under_label = False
    close(section)

    # Stale references: a path, flag or function in a code span that the
    # repository no longer has.
    # Read as _mask reads them: code spans first, then quotations outside
    # them, so a quote mark inside code pairs with nothing.
    plain = _mask(text, inline_code=False, quotes=False)
    # Code as "x", quotations as spaces: a span whose first backtick is a
    # space here sits inside a quotation.
    unquoted = QUOTED.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                          _mask(text, fill="x", quotes=False))
    spans = [(start, plain[start:end].strip("`")) for start, end in _code_spans(plain)
             if unquoted[start] != " "]
    spans = [(start, span) for start, span in spans if span.strip()]
    if spans and root is not None:
        for offset, _ in _stale(spans, path, root, _tracked(root) if tracked is None else tracked):
            unit = sentence_at(offset)
            if unit is not None:
                flag(unit, "stale reference")
    return _merge(text, hits, starts)


def _merge(text, hits, starts):
    """[Passage] for hits, {(start, end): [kinds, note]}, overlapping ones
    merged, each trimmed of the whitespace around it."""
    merged = []
    for (start, end), (kinds, note) in sorted(hits.items()):
        if merged and start < merged[-1][1]:
            last = merged[-1]
            last[1] = max(last[1], end)
            last[2] += [kind for kind in kinds if kind not in last[2]]
            last[3] = last[3] or note
        else:
            merged.append([start, end, list(kinds), note])
    out = []
    for start, end, kinds, note in merged:
        raw = text[start:end]
        start += len(raw) - len(raw.lstrip())
        end = start + len(raw.strip())
        out.append(Passage(bisect.bisect_right(starts, start), bisect.bisect_right(starts, end - 1),
                           tuple(kind for kind in KINDS if kind in kinds), text[start:end], note))
    return out


def flagged_bytes(found):
    """The bytes the passages found take up."""
    # surrogateescape gives back the bytes a doc that is not UTF-8 was read
    # from, as its size in due() counts them.
    return sum(len(p.text.encode("utf-8", "surrogateescape")) for p in found)


def flagged_share(text, found):
    """The share of text, in percent of its bytes, that the passages found
    take up."""
    size = len(text.encode("utf-8", "surrogateescape"))
    return flagged_bytes(found) * 100 / size if size else 0.0


# ---------------------------------------------------------------------------
# The triggers
# ---------------------------------------------------------------------------

def _lf(text):
    """text with CRLF line ends as LF, so every check reads the same lines on
    every platform; None stays None."""
    return text.replace("\r\n", "\n") if text is not None else None


def _git(args, root, stdin=None):
    """git's stdout, or None when it fails."""
    try:
        # Pinned as prose.py pins them: a user's trailer.separators without
        # ":" would hide every Prose: trailer from the reads here.
        result = subprocess.run(["git", "-c", "core.quotePath=false",
                                 "-c", "trailer.separators=:"] + args, cwd=root,
                                input=stdin, capture_output=True, check=False)
    except OSError:
        return None
    return result.stdout.decode("utf-8", "surrogateescape") if result.returncode == 0 else None


def _sizes(objects, root, strict=False):
    """{object name: size in bytes} for blobs and `<rev>:<path>` names. A
    name git does not find is left out. Anything else git could not answer
    is left out too, or with strict raises ValueError.

    cat-file reads one name per line, so a name holding a newline is first
    resolved to its object name on its own; otherwise it would become two
    lines and shift every size after it onto the wrong name."""
    if not objects:
        return {}

    def failed(why):
        if strict:
            raise ValueError(why)

    batch = {}  # the name cat-file is given: the names it stands for
    for name in objects:
        if "\n" not in name:
            batch.setdefault(name, []).append(name)
            continue
        try:
            result = subprocess.run(["git", "rev-parse", "--verify", "--quiet", name], cwd=root,
                                    capture_output=True, check=False)
        except OSError as error:
            failed(f"git rev-parse could not run: {error}")
            continue
        sha = result.stdout.decode("ascii", "replace").strip()
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha):
            batch.setdefault(sha, []).append(name)
        elif result.returncode != 1:
            failed(f"git rev-parse could not read {name!r}")
    if not batch:
        return {}
    keys = list(batch)
    out = _git(["cat-file", "--batch-check=%(objectsize)"], root,
               ("\n".join(keys) + "\n").encode("utf-8", "surrogateescape"))
    if out is None:
        failed("git cat-file could not read the sizes")
        return {}
    lines = out.split("\n")
    if lines[-1:] == [""]:
        lines.pop()
    if len(lines) != len(keys):
        failed("git cat-file gave a size for some names and not others")
        return {}
    sizes = {}
    for key, line in zip(keys, lines):
        if re.fullmatch(r"[0-9]+", line):
            sizes.update((name, int(line)) for name in batch[key])
        elif not line.endswith(" missing"):
            failed(f"git cat-file could not read {batch[key][0]!r}: {line}")
    return sizes


class SizeHistory(NamedTuple):
    # (commit, size after, blob after) of the last compaction, or None
    last: Optional[tuple]
    added: Optional[tuple]  # (commit, size) of the oldest version seen, or None
    # False when a size the search needed was missing, as in a partial
    # clone: whether a compaction came before is then unknown.
    complete: bool = True


def reviewed_blob(passes, oid):
    """True when prose's pass directory, passes, holds a completed-review
    record for the blob oid, as --reviewed writes one: that blob is the
    result of a compaction. Records live in the shared git directory and
    outlive the snapshot, which is deleted once the compaction is
    committed."""
    if passes is None:
        return False
    try:
        fields = json.loads((reviewed_dir(passes) / oid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(fields, dict)


def size_history(path, root, passes=None):
    """The last compaction of path: the newest non-merge commit reachable
    from HEAD whose Prose: trailer lists path after `compacted:`, or that
    shrank it by COMPACTED_SHARE or more, or whose resulting blob has a
    completed-review record in passes, prose's pass directory (a compaction
    that kept its flagged passages may cut less); and the
    version its newest add made, or the oldest the log reaches when the
    file has more than HISTORY_DEPTH changes. Only commits since that add
    count: a file deleted and added again starts a new history. Commits inside merged
    branches count: a compaction in a pull request that also grew the file
    nets less than a tenth on the merge, but its own commit still shows
    it."""
    # Topological order, so no commit is read before a newer one that
    # changed the file, whatever their dates.
    out = _git(["log", "--no-merges", "--topo-order", "-n", str(HISTORY_DEPTH),
                "--format=%x01%h%x02%(trailers:key=Prose,valueonly,unfold,separator=%x03)%x02",
                "--raw", "--no-abbrev", "--no-renames", "--", f":(literal){path}"], root)
    # A log that failed, as in a treeless clone that may not fetch, says
    # nothing about earlier compactions, unless HEAD lacks the file, as
    # before the first commit: a file HEAD lacks was never compacted.
    if out is None:
        return SizeHistory(None, None, not _in_head(path, root))
    # A shallow clone's boundary commits have no parents here, so the log
    # shows the file as added by one, and misses what came before.
    boundaries = _shallow_boundaries(root)
    if not out:
        return SizeHistory(None, None, not boundaries or not _in_head(path, root))
    changes, oldest, marked = [], None, set()
    for chunk in out.split("\x01")[1:]:
        commit, _, rest = chunk.partition("\x02")
        values, _, rest = rest.partition("\x02")
        if any(path in compacted_paths_in(value) for value in values.split("\x03")):
            # Its Prose: trailer records it as a compaction of path, whatever
            # it cut: the record every clone sees.
            marked.add(commit)
        lines = [commit] + rest.strip("\n").split("\n")
        kinds = set()
        for line in lines[1:]:
            raw = re.match(r":\d+ \d+ ([0-9a-f]+) ([0-9a-f]+) ([ADM])\t", line)
            if raw and raw.group(3) == "D":
                # Deleted in HEAD: the doc staged now is a new file, with
                # no history of its own yet.
                return SizeHistory(None, None, True)
            if raw:
                kinds.add(raw.group(3))
                if raw.group(3) == "M":
                    changes.append((lines[0], raw.group(1), raw.group(2)))
                oldest = (lines[0], raw.group(2))
        # The newest add starts the file's present life: what came before
        # it, as before a deletion, was another file at the same path.
        if "A" in kinds:
            break
    sizes = _sizes(sorted({blob for _, old, new in changes for blob in (old, new)}
                          | ({oldest[1]} if oldest else set())), root)
    last, complete = None, True
    for commit, old, new in changes:
        if new in sizes and (commit in marked or reviewed_blob(passes, new)):
            last = (commit, sizes[new], new)
            break
        if new not in sizes or old not in sizes:
            # Whether this change was a compaction cannot be told, so
            # neither can which one was the last.
            complete = False
            break
        if sizes[new] * 100 <= sizes[old] * (100 - COMPACTED_SHARE):
            last = (commit, sizes[new], new)
            break
    if last is None and oldest and any(sha.startswith(oldest[0]) for sha in boundaries):
        complete = False
    added =(oldest[0], sizes[oldest[1]]) if oldest and oldest[1] in sizes else None
    return SizeHistory(last, added, complete)


# The part of a Prose: trailer value that names the files the commit
# compacted, each verified and reviewed with `prose compact`.
COMPACTED = re.compile(r"; compacted: (.+)$")


def compacted_paths_in(value):
    """The paths a Prose: trailer value lists after `; compacted: `."""
    found = COMPACTED.search(value or "")
    return found.group(1).split(", ") if found else []


def listable(path):
    """True when path can be listed after `compacted: ` and read back the
    same: no separator, semicolon, line break or edge space in it."""
    return bool(path) and path == path.strip() and not re.search(r", |;|[\r\n]", path)


def compacted_paths(root, amend, passes):
    """The staged paths whose compaction, started in this work tree, is
    verified and reviewed for the staged blob, sorted: what the signing call
    lists in its trailer after `compacted: `. Paths that cannot be listed
    are left out; their compaction is then known only to this clone.

    With amend, a path HEAD's own Prose: trailer lists stays listed while
    its staged blob is still HEAD's. That is the compaction being amended:
    any check run against HEAD since may have deleted its snapshot, so the
    snapshot can no longer vouch for it."""
    if root is None:
        return []
    base = "HEAD^" if amend else "HEAD"
    try:
        tree, index = tree_entries(root, base), index_entries(root)
        stored = {}
        begun = started(root, tree, passes, stored)
        head = tree_entries(root, "HEAD") if amend else {}
    except ValueError:
        return []
    out = set()
    if amend:
        values = _git(["log", "-1", "--format=%(trailers:key=Prose,valueonly,unfold,"
                       "separator=%x03)", "HEAD"], root) or ""
        for path in {path for value in values.rstrip("\n").split("\x03")
                     for path in compacted_paths_in(value)}:
            entries, held, old = index.get(path, []), head.get(path), tree.get(path)
            if len(entries) == 1 and entries[0].stage == "0" and entries[0].mode in REGULAR \
                    and held is not None and held[1] == entries[0].oid \
                    and (old is None or old[1] != entries[0].oid) and listable(path):
                out.add(path)
    for path, starts in begun.items():
        entries = index.get(path, [])
        if len(entries) != 1 or entries[0].stage != "0" or entries[0].mode not in REGULAR:
            continue
        old, oid = tree.get(path), entries[0].oid
        if (old is not None and old[1] == oid) or not listable(path):
            continue
        if any(_record(verified_dir(passes), oid, before)
               and _review_covers(reviewed_dir(passes), oid, before,
                                  _answers_for(stored.get((path, before)), oid))
               for before in starts):
            out.add(path)
    return sorted(out)


def _in_head(path, root):
    """True when HEAD's tree holds path; False when it does not, or when
    there is no HEAD yet."""
    return bool(_git(["ls-tree", "-z", "--full-tree", "HEAD", "--", path], root))


def _shallow_boundaries(root):
    """The full ids of a shallow clone's boundary commits; none when the
    clone is complete."""
    path = _git(["rev-parse", "--git-path", "shallow"], root)
    if not path or not path.strip():
        return set()
    try:
        text = (pathlib.Path(root) / path.strip()).read_text(encoding="ascii")
    except (OSError, ValueError):
        return set()
    return set(text.split())


def last_compaction(path, root):
    """(commit, size after, blob after) for the last compaction of path, or
    None."""
    return size_history(path, root).last


class Due(NamedTuple):
    path: str
    why: str


def _growth_reason(size, history, setting):
    """Why a doc of size bytes is due by growth, or None: since its last
    compaction it has grown by its growth share and by at least its growth
    bytes. A doc never compacted has no growth to measure; its flagged
    passages decide."""
    if history.last is None:
        return None
    commit, after = history.last[:2]
    if size - after < setting.growth_bytes:
        return None
    if after == 0:
        return f"{size:,} bytes; its last compaction ({commit[:12]}) left it empty" if size else None
    if size * 100 < after * (100 + setting.growth):
        return None
    grown = (size - after) * 100 // after
    return (f"{size:,} bytes, grown {grown}% ({size - after:,} bytes) since its last compaction "
            f"({commit[:12]}, {after:,} bytes); {setting.growth}% and "
            f"{setting.growth_bytes:,} bytes are allowed")


def is_binary(setting, data):
    """True when git treats the file as binary: by its `-diff` or `binary`
    attribute, or by a NUL byte in data, its staged blob."""
    return setting.binary or b"\0" in data


# What makes a doc read often by its place in the repository.
ALWAYS_READ = {"claude.md", "agents.md", "skill.md"}
# A link a SKILL.md or AGENTS.md asks to have read first, or read before
# something, in the same paragraph or list item. A link to read before
# changing the skill does not count, so its target is not read often by
# place.
# A link between "read" and "first" counts as one character, so the full
# stop in its target, as in "x.md", does not end the sentence.
READ_FIRST = re.compile(r"\bread\b(?:\[[^\]\n]*\]\([^)\n]*\)|[^.]){0,40}?\b(?:first\b|before\b"
                        r"(?![ \t\n]+(?:chang|edit|modif|updat|touch)))", re.I)
LINK = re.compile(r"\[[^\]\n]*\]\(<?([^)\s>]+)>?(?:[ \t]+\"[^\"]*\")?\)")
# Trailers that imply a read of the skill they name.
READ_TRAILERS = re.compile(r"^(bug-hunter|prose|spec-check)[ \t]*:", re.I | re.M)


def _batch_blobs(oids, root):
    """{oid: text} for blobs, read by one `git cat-file --batch`."""
    if not oids:
        return {}
    try:
        result = subprocess.run(["git", "cat-file", "--batch"], cwd=root,
                                input=("\n".join(oids) + "\n").encode(), capture_output=True,
                                check=False)
    except OSError:
        return {}
    out, data, pos = {}, result.stdout, 0
    for oid in oids:
        end = data.find(b"\n", pos)
        header = data[pos:end].split()
        if len(header) != 3 or header[1] != b"blob":
            pos = end + 1
            continue
        size = int(header[2])
        out[oid] = _lf(data[end + 1:end + 1 + size].decode("utf-8", "surrogateescape"))
        pos = end + 1 + size + 1
    return out


def read_first_links(root, index):
    """{tracked path: the SKILL.md or AGENTS.md that links it as read first}
    for every link a tracked SKILL.md or AGENTS.md makes in a paragraph or
    list item that asks to read it first or before something."""
    sources = {path: entries[0].oid for path, entries in index.items()
               if pathlib.PurePosixPath(path).name.lower() in ("skill.md", "agents.md")
               and len(entries) == 1 and entries[0].mode in REGULAR}
    texts = _batch_blobs(sorted(set(sources.values())), root)
    out = {}
    for source, oid in sorted(sources.items()):
        text = texts.get(oid)
        if text is None:
            continue
        masked = _mask(text)
        here = pathlib.PurePosixPath(source).parent
        for block in _blocks(_mask(text, fill="x")):
            body = masked[block.start:block.end]
            if not READ_FIRST.search(body):
                continue
            # The link is read from the text itself, since masking blanks a
            # quoted title; one that starts in code or a quotation is not a link.
            for match in LINK.finditer(text, block.start, block.end):
                if masked[match.start()] == " ":
                    continue
                target = match.group(1).split("#", 1)[0]
                if not target or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                    continue
                path = os.path.normpath(str(here / target))
                if path in index:
                    out.setdefault(path, source)
    return out


def _skill_of(path, skills):
    """The SKILL.md of the nearest directory above path that has one."""
    parent = pathlib.PurePosixPath(path).parent
    while True:
        candidate = str(parent / "SKILL.md") if str(parent) != "." else "SKILL.md"
        if candidate in skills:
            return candidate
        if str(parent) in (".", "/", ""):
            return None
        parent = parent.parent


def implied_reads(root, index, links, stops):
    """{doc: reads}: how many of the READS_DEPTH commits behind HEAD imply
    a read of each doc. stops gives each doc's last compaction commit, or
    None; only commits newer than it count. With None, the count runs from
    the commit that added the doc, which counts, as size_history finds it.
    A doc HEAD lacks has no reads. These rules map each commit to the reads
    it implies; they are declared, not inferred:
    - a commit changing a file in a skill's directory reads that skill's
      SKILL.md and the files it links as read first;
    - a Bug-hunter:, Prose: or Spec-check: trailer reads that skill's
      SKILL.md;
    - a Spec-check: trailer also reads the main specs and the open changes."""
    out = {doc: 0 for doc in stops}
    if not stops:
        return out
    done, added = set(), {}
    for doc, stop in stops.items():
        if stop is None:
            if not _in_head(doc, root):
                done.add(doc)
            else:
                oldest = size_history(doc, root).added
                if oldest:
                    added[doc] = oldest[0]
    if len(done) == len(stops):
        return out
    # Trailers only: a subject such as "spec-check: ..." is not one.
    # No merges: a merge's body is its pull request's title, which git
    # reads as a trailer when it looks like one ("spec-check: ...").
    log = _git(["log", "--no-merges", "--topo-order", "-n", str(READS_DEPTH),
                "--format=%x01%H%n%(trailers:only,unfold)%x02",
                "--name-only", "HEAD"], root)
    if not log:
        return out
    skills = {path for path in index if pathlib.PurePosixPath(path).name == "SKILL.md"}
    first_of = {}
    for target, source in links.items():
        first_of.setdefault(source, set()).add(target)
    specs = {path for path in index
             if (path.startswith("openspec/specs/") and path.endswith("/spec.md"))
             or (path.startswith("openspec/changes/") and not path.startswith(
                 "openspec/changes/archive/") and path.endswith(".md"))}
    for chunk in log.split("\x01")[1:]:
        commit, _, rest = chunk.partition("\n")
        body, _, files = rest.partition("\x02")
        for doc, stop in stops.items():
            if stop and commit.startswith(stop):
                done.add(doc)
        if len(done) == len(stops):
            break
        reads = set()
        for name in filter(None, files.split("\n")):
            skill = _skill_of(name, skills)
            if skill:
                reads.add(skill)
                reads |= first_of.get(skill, set())
        for trailer in READ_TRAILERS.findall(body):
            name = trailer.lower()
            reads |= {path for path in skills
                      if path == f"{name}/SKILL.md" or path.endswith(f"/{name}/SKILL.md")}
            if name == "spec-check":
                reads |= specs
        for doc in stops:
            if doc not in done and doc in reads:
                out[doc] += 1
        # The commit that added a doc is the oldest one that reads it.
        for doc, first in added.items():
            if commit.startswith(first):
                done.add(doc)
    return out


def _often(path, setting, links):
    """Why path is read often by its place or a declaration, or None."""
    name = pathlib.PurePosixPath(path).name.lower()
    if setting.declared:
        return "declared prose-compact in .gitattributes"
    if name in ALWAYS_READ:
        return f"every {pathlib.PurePosixPath(path).name} is read before work"
    parts = pathlib.PurePosixPath(path).parts
    if parts[:2] == ("openspec", "changes") and "archive" not in parts and len(parts) == 4 \
            and name in ("proposal.md", "design.md"):
        return "an open OpenSpec change's " + name[:-3]
    if path in links:
        return f"{links[path]} links it to be read first"
    return None


def _flagged_due(added, size, setting):
    """Whether added flagged bytes make a doc of size bytes due: at least
    its flagged-bytes setting, and at least its flagged share of size."""
    return added >= setting.flagged and added * 100 >= size * setting.flagged_share


def _flagged_reason(found, size, baseline, setting):
    kinds = collections.Counter(kind for passage in found for kind in passage.kinds)
    shown = ", ".join(f"{count} {kind}" for kind, count in
                      sorted(kinds.items(), key=lambda item: KINDS.index(item[0])))
    flagged = flagged_bytes(found)
    added = flagged - baseline
    since = (f", {baseline:,} of them at its last compaction; {added:,} bytes "
             f"({added * 100 // max(size, 1)}%) added since" if baseline else "")
    return (f"{flagged:,} bytes ({flagged * 100 // max(size, 1)}%) in {len(found)} flagged "
            f"passage{'' if len(found) == 1 else 's'} ({shown}){since}; due at "
            f"{setting.flagged_share}% of the file and {setting.flagged:,} bytes more than at "
            "its last compaction")


def _baseline(path, history, root, tracked):
    """The bytes flagged in path as its last compaction left it: 0 when it
    was never compacted, so all its flagged text counts; None when that is
    unknown, as when a partial clone lacks the history it needs."""
    if not history.complete:
        return None
    if history.last is None:
        return 0
    try:
        data = _blob(history.last[2], root)
    except ValueError:
        return None
    return flagged_bytes(passages(_lf(data.decode("utf-8", "surrogateescape")), path, root,
                                  tracked))


def due(paths, root, passes=None):
    """[Due] for each staged path that is read often and due for
    compaction. It is due when the flagged bytes added since its last
    compaction (all of them when it was never compacted) reach both its
    flagged-bytes setting and its flagged share of the file's current size,
    or when it has grown by both its growth
    share and its growth bytes since then. Its last compaction is found as
    size_history says; a staged blob that is itself a compaction is not
    due. The trigger looks only at candidates: paths that are current-state,
    by default or by their declaration in .gitattributes, or linked from a
    SKILL.md or AGENTS.md to be read first, and not exempt. A candidate due
    by flagged text or growth is reported only when it is read often. A binary file, by its
    `-diff` attribute or a NUL byte, is skipped. Reads the index, so it
    judges the change about to be committed; sizes and blobs are read by
    the ids `git ls-files -s` and `git ls-tree` list. Read counts come
    last, and only for a doc otherwise due, since they read the log.

    No git call here fetches a blob a partial clone lacks: a history blob
    missing counts as unknown, so the trigger never waits on the network."""
    with _no_lazy_fetch():
        return _due(paths, root, passes)


@contextlib.contextmanager
def _no_lazy_fetch():
    """Every git call made inside reads only the objects already here."""
    old = os.environ.get("GIT_NO_LAZY_FETCH")
    os.environ["GIT_NO_LAZY_FETCH"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("GIT_NO_LAZY_FETCH", None)
        else:
            os.environ["GIT_NO_LAZY_FETCH"] = old


def _due(paths, root, passes):
    paths = [path for path in paths if path]
    if not paths:
        return []
    found = settings(paths, root)
    try:
        index, head = index_entries(root), tree_entries(root, "HEAD")
    except ValueError:
        return []
    links = read_first_links(root, index)
    tracked = set(index)
    pending = []
    for path in paths:
        setting = found[path]
        if setting.exempt or setting.binary or not (setting.current or path in links):
            continue
        entries = index.get(path, [])
        if len(entries) != 1 or entries[0].stage != "0" or entries[0].mode not in REGULAR:
            continue  # deleted, unmerged, or not a file
        try:
            data = _blob(entries[0].oid, root)
        except ValueError:
            continue
        if is_binary(setting, data):
            continue
        before = head.get(path)
        try:
            head_size = _size(before[1], root) if before else None
        except ValueError:
            head_size = None
        if reviewed_blob(passes, entries[0].oid) or (
                head_size is not None and len(data) * 100 <= head_size * (100 - COMPACTED_SHARE)):
            continue  # this change is itself a compaction
        text = _lf(data.decode("utf-8", "surrogateescape"))
        flagged = passages(text, path, root, tracked)
        history = size_history(path, root, passes)
        reasons = []
        # The flagged bytes added can be no more than all the flagged bytes,
        # so the baseline, which reads history, is looked up only when all
        # the flagged bytes would make the doc due.
        if flagged and _flagged_due(flagged_bytes(flagged), len(data), setting):
            baseline = _baseline(path, history, root, tracked)
            if baseline is not None and _flagged_due(flagged_bytes(flagged) - baseline,
                                                     len(data), setting):
                reasons.append(_flagged_reason(flagged, len(data), baseline, setting))
        grown = _growth_reason(len(data), history, setting)
        if grown:
            reasons.append(grown)
        if reasons:
            pending.append((path, setting, history, reasons))
    out, counted = [], {}
    unplaced = {path: (history.last[0] if history.last else None)
                for path, setting, history, _ in pending if not _often(path, setting, links)}
    if unplaced:
        counted = implied_reads(root, index, links, unplaced)
    for path, setting, history, reasons in pending:
        often = _often(path, setting, links)
        if often is None:
            reads = counted.get(path, 0)
            if reads < setting.reads:
                continue
            often = (f"{reads} reads implied by commits since "
                     + ("its last compaction" if history.last else "it was added")
                     + f"; {setting.reads} make it read often")
        out.append(Due(path, f"read often ({often}); " + "; ".join(reasons)))
    return out


def print_due(found, command):
    """Print the section of `prose check`'s first-call output that lists
    the docs due for compaction."""
    if not found:
        return
    print("\nCompaction (do it in a separate commit in this pull request; SKILL.md, "
          "*Compaction*):\n")
    for item in found:
        print(f"  compaction due for {item.path}: {item.why}")
    print(f"\n  Commit this change first, then for each file run: {command} compact <file>")


# ---------------------------------------------------------------------------
# Headings and the references to them
# ---------------------------------------------------------------------------
#
# --verify is differential and deliberately blunt: a heading or anchor the
# compaction removed counts as still referenced when its text, normalised,
# appears anywhere in another searched file, or its `#slug` appears anywhere
# in a searched file or the file itself. Normalising is plain string
# clean-up, no parsing: case folded; backticks, `*` and `_` dropped; every
# run of whitespace made one space; and so is each line break, together with
# any comment or quote markers (`#`, `//`, `*`, `>`) that start the next
# line, so a citation wrapped inside a comment reads as one line. An incidental
# mention only keeps a heading, so over-blocking is accepted.

# A closing run of `#` needs whitespace before it, so "C#" keeps its `#`.
# Up to three spaces may come before the `#`s, and a space or a tab after
# them, as in CommonMark; four spaces make an indented code line.
HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
# A heading whose normalised text is shorter than this, such as "Why" or
# "Open", would match ordinary prose everywhere and could never be removed,
# so its text counts only beside a name for the doc (_cited). Its anchor
# always counts.
MIN_HEADING = 16
# What starts a line and is dropped with the line break before it: the
# indent, then any run of comment or quote markers.
LINE_MARKERS = re.compile(r"^[ \t]*(?:(?:#+|//+|\*+|>+)[ \t]*)*")


def normalise_line(line):
    """line as --verify compares text: its leading comment or quote markers
    dropped, case folded (so "STRASSE" matches "Straße"), backticks, `*` and
    `_` dropped, and each run of whitespace made one space."""
    line = re.sub(r"[`*_]", "", LINE_MARKERS.sub("", line).casefold())
    return " ".join(line.split())


# What starts a line and is dropped before a short heading's citation is
# looked for: the indent, then any run of `#`, `//` or `>` markers, or of
# `*` followed by a space, as a bullet or a comment's margin. They go so
# that normalised() can join a sentence wrapped across comment or quote
# lines. A `*` with no space after it opens emphasis and stays; the
# matching ignores it.
CITE_LINE_MARKERS = re.compile(r"^[ \t]*(?:(?:#+|//+|>+)[ \t]*|\*+[ \t]+)*")
# Where a sentence ends: `.`, `!` or `?`, any closing marks, then whitespace.
# A dot inside a name, as in `SKILL.md`, is followed by no space. The dot of
# an abbreviation such as "e.g." ends none, and nor does the dot after a
# one- or two-digit number, as in a numbered list's `1.`, even where one
# ends a sentence: a sentence read too long only keeps a heading.
CITE_SENTENCE_END = re.compile(
    r"(?<!\b[eE]\.g)(?<!\b[iI]\.e)(?<!\b[vV]s)(?<!\b[cC]f)(?<!\b[eE]tc)"
    r"(?<!\b\d)(?<!\b\d\d)"
    r"[.!?][)\]*_\"”»'`]*\s+")
# A letter or digit: what may not touch a doc's name or a short heading's
# text for it to count as whole words. `_` is not one, so `_Never_`, in
# Markdown's underscore emphasis, counts.
CITE_WORD = r"[^\W_]"


def cite_line(line):
    """line as a short heading's citation is looked for in it: its leading
    comment or quote markers dropped and each run of whitespace made one
    space, with its case kept."""
    return " ".join(CITE_LINE_MARKERS.sub("", line).split())


def _skill_dir(rel, root, file):
    """The directory of the nearest SKILL.md at or above the doc's
    directory, or None. Inside a repository, only directories below root
    count: the root's own name is wherever it was cloned. Outside one, any
    directory above file, the doc's absolute path, counts."""
    if root is not None:
        parent = pathlib.PurePosixPath(rel).parent
        while str(parent) not in (".", "", "/"):
            if (pathlib.Path(root) / parent / "SKILL.md").is_file():
                return parent
            parent = parent.parent
        return None
    if file is None:
        return None
    for parent in pathlib.Path(file).parents:
        if (parent / "SKILL.md").is_file():
            return parent
    return None


def doc_names(rel, root, file=None):
    """The regex that finds a name for the doc at rel, ignoring case: its
    path, its file name, or, for a doc inside a skill, that skill's name as
    "<skill>'s" or "the <skill> skill", the name in backticks or not. The
    skill is the directory _skill_dir finds; outside a repository, file,
    the doc's absolute path, is where its search starts. A name counts only
    as a whole: no letter, digit, `.` or `-` may touch it, so `SKILL.md`
    is not found in `x.SKILL.md` and "prose's" is not in "dense-prose's"."""
    pure = pathlib.PurePosixPath(rel)
    names = [re.escape(rel), re.escape(pure.name)]
    skill_dir = _skill_dir(rel, root, file)
    if skill_dir is not None and skill_dir.name:
        skill = re.escape(skill_dir.name)
        names += [rf"`?{skill}`?['’]s", rf"the `?{skill}`? skill"]
    return re.compile(rf"(?i)(?<!{CITE_WORD}|[.-])(?:" + "|".join(names)
                      + rf")(?!{CITE_WORD}|-)")


# The markup a heading and its citation may each carry or drop: code-span
# backticks, and `*` or `_` emphasis. Between a heading's words, a citation
# may hold any run of it beside the whitespace.
CITE_MARKUP_GAP = r"[`*_]*\s+[`*_]*"


def rendered_words(heading):
    """A heading's words as rendered: its backticks and `*` dropped, and each
    `_` at a word's edge, so `_Why_` reads as Why but my_doc keeps its `_`."""
    text = re.sub(rf"(?<!{CITE_WORD})_+|_+(?!{CITE_WORD})", "",
                  heading.replace("`", "").replace("*", ""))
    return text.split()


def short_heading_pattern(heading):
    """The regex that finds a short heading's words, with their case and
    without their markup, as whole words. Between two words the text may
    hold whitespace and any backticks, `*` or `_`. Markup before the first
    word or after the last is outside the match, so the pattern for the
    heading Never matches the text `*Never*`. None for a heading with no
    words."""
    words = rendered_words(heading)
    if not words:
        return None
    return re.compile(rf"(?<!{CITE_WORD})" + CITE_MARKUP_GAP.join(map(re.escape, words))
                      + rf"(?!{CITE_WORD})")


def _cited(source, lines, names, patterns):
    """[Reference] for each place in one file's [(line number, line)] where
    a short heading's text, as patterns ({heading: regex}) finds it, is on
    the same line or in the same sentence as a name for the doc, as names
    finds one. Sentences do not cross a blank line. A heading's text that
    lies wholly inside a name for the doc, as "FAQ" in "docs/FAQ.md", is
    part of that name, not a citation."""
    found = []

    def citations(text):
        """The (start, heading) of each short heading's text in text that is
        cited there: text holds a name for the doc, and the heading's text
        is not inside one."""
        spans = [match.span() for match in names.finditer(text)]
        if not spans:
            return []
        return [(match.start(), heading) for heading, pattern in patterns.items()
                for match in pattern.finditer(text)
                if not any(start <= match.start() and match.end() <= end
                           for start, end in spans)]

    def scan(text, starts):
        offsets = [offset for offset, _ in starts]
        at = 0
        for end in [match.end() for match in CITE_SENTENCE_END.finditer(text)] + [len(text)]:
            for start, heading in citations(text[at:end]):
                line = starts[bisect.bisect_right(offsets, at + start) - 1][1]
                found.append(Reference(source, line, heading))
            at = end

    paragraph = []
    for number, line in lines + [(0, "")]:
        text = cite_line(line)
        if text:
            found += [Reference(source, number, heading) for _, heading in citations(text)]
            paragraph.append((number, line))
        elif paragraph:
            scan(*normalised(paragraph, cite_line))
            paragraph = []
    return found


def normalised(lines, normalise=normalise_line):
    """(text, starts) for [(line number, line)]: the lines normalised and
    joined by single spaces, so a phrase wrapped across lines reads as one,
    and [(offset in text, line number)] where each non-empty line begins.
    A bare CR, which git and the line split leave inside a line, is a line
    break here too, so the markers after it are dropped; each part keeps
    the number of the line it came from."""
    pieces, starts, offset = [], [], 0
    for number, line in lines:
        for part in line.split("\r"):
            piece = normalise(part)
            if piece:
                starts.append((offset, number))
                pieces.append(piece)
                offset += len(piece) + 1
    return " ".join(pieces), starts


def heading_texts(text):
    """The text of every ATX heading line, as HEADING reads one: up to three
    spaces, one to six `#`, then a space or tab. Setext headings are not read.
    A line in a code block counts too. In the old text that only makes
    --verify block more; in the new text, a removed heading whose line is
    left in a code block counts as kept, so its anchor is not searched for."""
    # A byte-order mark before the first line, and a bare CR as a line end,
    # are both read as Markdown reads them, so no heading hides behind them.
    lines = re.split(r"\r\n|\r|\n", text[1:] if text.startswith("\ufeff") else text)
    return [match.group(1) for match in map(HEADING.match, lines) if match]


def slug(heading):
    """An approximation of GitHub's anchor for a heading's text, before
    duplicates are numbered: lowercase, punctuation other than `-` and `_`
    dropped, spaces as `-`. Links, emphasis and entities are not rendered
    first, so it can differ from GitHub's; before and after are slugged
    alike."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def heading_anchors(text):
    """[(anchor, heading text)] for each of the file's headings that gives
    an anchor, duplicates numbered as GitHub numbers them."""
    seen, out = {}, []
    for heading in heading_texts(text):
        base = slug(heading)
        count = seen.get(base, 0)
        if base:
            out.append((base if count == 0 else f"{base}-{count}", heading))
        seen[base] = count + 1
    return out


def anchors(text):
    """Every anchor the file's headings give, duplicates numbered as GitHub
    numbers them."""
    return {anchor for anchor, _ in heading_anchors(text)}


def gone_headings(before, after):
    """The heading texts of before that after has fewer of, each once, in
    order of first use. Counted, not just looked up, so removing one of two
    headings with the same text counts as removing it."""
    kept = collections.Counter(heading_texts(after))
    old = heading_texts(before)
    counts = collections.Counter(old)
    return [h for h in dict.fromkeys(old) if counts[h] > kept[h]]


class Reference(NamedTuple):
    source: str
    line: int
    needle: str


def _grep(where, root):
    """{path: [(line number, line)]} for every line of every tracked file;
    where is [] for the work tree or ["--cached"] for the index. git grep
    reads them, with an empty pattern that every line matches, so the
    matching is done here, on normalised text."""
    # Set against the user's config, so each record is always
    # path\0line\0content: no column field, no colour codes.
    # Every tracked file is read as text, binary or not, and submodules are
    # not this repository's files. A failure is an error, never "no
    # references": anything git grep writes to stderr is one, whatever its
    # exit code, since it exits 0 or 1 by whether something matched even
    # when it could not read a file.
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-c", "grep.column=false",
             "-c", "color.grep=never", "-c", "color.ui=never", "-c", "submodule.recurse=false",
             "-c", "advice.sparseIndexExpanded=false",
             "grep", "--no-color", "--no-recurse-submodules", "-n", "-a", "-z", "-F", "-e", ""]
            + where,
            cwd=root, capture_output=True, check=False)
    except OSError as error:
        raise ValueError(f"git grep could not run: {error}")
    message = result.stderr.decode("utf-8", "replace").strip()
    if result.returncode not in (0, 1) or message:
        raise ValueError(f"git grep failed: {message}")
    # Each record is path NUL number NUL line, ended by a newline. Read field
    # by field: a path may hold a newline, and split at newlines it would be
    # cut in two and its tail taken for another file, even the doc itself.
    stdout, out, pos = result.stdout.decode("utf-8", "surrogateescape"), {}, 0
    while pos < len(stdout):
        first = stdout.find("\0", pos)
        second = stdout.find("\0", first + 1) if first >= 0 else -1
        if second < 0 or not stdout[first + 1:second].isdigit():
            raise ValueError("git grep wrote output that could not be read: "
                             f"{stdout[pos:pos + 80]!r}")
        end = stdout.find("\n", second + 1)
        end = len(stdout) if end < 0 else end
        out.setdefault(stdout[pos:first], []).append(
            (int(stdout[first + 1:second]), stdout[second + 1:end].removesuffix("\r")))
        pos = end + 1
    return out


def _find(source, lines, tags, texts, cited=None):
    """[Reference] in one file's [(line number, line)], each at the line
    where its match starts. Three kinds are found:
    - a line holding one of tags, the `#anchor` strings, as written;
    - a place where the file's normalised text holds one of texts, a dict
      {normalised text: heading};
    - a short heading's citation that _cited finds, given cited as
      (doc names regex, {heading: regex})."""
    found = [Reference(source, number, tag) for number, line in lines for tag in tags
             if tag in line]
    if texts:
        joined, starts = normalised(lines)
        offsets = [offset for offset, _ in starts]
        for needle, heading in texts.items():
            at = joined.find(needle)
            while at >= 0:
                found.append(Reference(source, starts[bisect.bisect_right(offsets, at) - 1][1],
                                       heading))
                at = joined.find(needle, at + 1)
    if cited and cited[1]:
        found += _cited(source, lines, *cited)
    return found


class Given(NamedTuple):
    """The files that might refer to the doc, as the caller gave them: paths
    after `--`, and a list file (`-` for stdin) of one path per line, or of
    NUL-separated paths with nul."""
    paths: tuple = ()
    paths_from: str = ""
    nul: bool = False

    def supplied(self):
        return bool(self.paths or self.paths_from)

    def options(self):
        """The command-line options that give the same referrers again."""
        out = ""
        if self.paths_from:
            source = "-" if self.paths_from == "-" else command_path(self.paths_from)
            out += f" --paths-from {source}" + (" -0" if self.nul else "")
        if self.paths:
            # After `--` nothing is read as an option, so plain quoting is enough.
            out += " -- " + " ".join(shlex.quote(path) for path in self.paths)
        return out


def read_paths_from(data, nul):
    """The paths in a --paths-from list, read as bytes: NUL-separated with
    nul, else one per line, with a CR before the newline dropped. Empty
    entries are skipped."""
    if nul:
        parts = data.split(b"\0")
    elif b"\0" in data:
        raise ValueError("the list of paths holds NUL bytes, as rg -l0 and find -print0 write "
                         "them; add -0")
    else:
        parts = [part[:-1] if part.endswith(b"\r") else part for part in data.split(b"\n")]
    return [os.fsdecode(part) for part in parts if part]


class Referrers(NamedTuple):
    files: list      # [(name as reported, pathlib.Path)]
    sources: list    # where they came from, as the report names it
    empty: str = ""  # a --paths-from list that held no paths, as the report names it


def referrer_files(paths, doc, root=None, sources=None, empty=""):
    """Referrers for the given paths, each a file named explicitly. A
    directory is refused: the caller lists the files in it that it means, as a
    search finds them. The doc itself is dropped. A file inside root is
    reported by its path from root, as git grep reports a tracked one.
    sources names where the paths came from for the report; by default, the
    paths themselves. The doc is recognised as the same file, by device and
    inode, so another spelling of it, a different case on a case-insensitive
    file system or a hard link, is dropped too."""
    files, own = [], os.stat(doc)
    base = pathlib.Path(root).resolve() if root else None
    for given in paths:
        try:
            found = os.stat(given)
        except (FileNotFoundError, NotADirectoryError):
            raise ValueError(f"{given}: no such file, among the paths to search")
        except OSError as error:
            raise ValueError(f"{given}: could not read it: {error.strerror}")
        if stat.S_ISDIR(found.st_mode):
            raise ValueError(
                f"{given}: a directory; name the files in it that might refer to the doc, as a "
                f"search lists them: rg -l <name> {command_path(given)} | prose compact --verify "
                f"<file> --paths-from -, or find {command_path(given)} -name '*.md' -print0 | "
                f"prose compact --verify <file> --paths-from - -0")
        if not stat.S_ISREG(found.st_mode):
            raise ValueError(f"{given}: not a regular file, among the paths to search")
        if os.path.samestat(found, own):
            continue
        name = given
        if base is not None:
            try:
                name = str(pathlib.Path(given).absolute().parent.resolve().joinpath(
                    pathlib.Path(given).name).relative_to(base))
            except ValueError:
                pass
        files.append((name, pathlib.Path(given)))
    return Referrers(files, list(paths) if sources is None else list(sources), empty)


def _read_lines(name, path):
    """[(line number, line)] of a given file, or an error naming it."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{name}: could not read it: {error.strerror}")
    return list(enumerate(_lf(data.decode("utf-8", "surrogateescape")).split("\n"), start=1))


def references(path, headings, wanted, text, root, referrers=None, file=None):
    """[Reference] for each place that names one of the headings in another
    file, or that holds one of the anchors in wanted as `#anchor`, in
    another file or in the doc itself. path is the doc's path as `git
    ls-files` lists it (or as given, outside a repository), and text is
    the doc's own current text. A heading of at least MIN_HEADING
    characters once normalised is named by its normalised text anywhere; a
    shorter one by its words, case kept and markup ignored
    (short_heading_pattern), on the same line or in the same sentence as a
    name for the doc (doc_names). The other files are the
    repository's tracked files, in the work tree and the index (none when
    root is None), and the referrers given. file is the doc's absolute
    path, which doc_names needs outside a repository."""
    texts, short = {}, {}
    for heading in sorted(set(headings)):
        needle = normalised([(0, heading)])[0]
        if len(needle) >= MIN_HEADING:
            texts.setdefault(needle, heading)
        elif (pattern := short_heading_pattern(heading)) is not None:
            short[heading] = pattern
    cited = (doc_names(path, root, file), short)
    tags = sorted(f"#{anchor}" for anchor in wanted)
    found = _find(path, list(enumerate(text.split("\n"), start=1)), tags, {})
    # Every file is read even when nothing is looked for, so the report's
    # list of what was searched is true, and an unreadable file is an error.
    # The same place found twice, as in the work tree and the index, or in
    # a tracked file also given as a referrer, is reported once.
    seen = set()

    def keep(refs):
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                found.append(ref)

    if root is not None:
        # The work tree and the index are both searched, so a tracked file
        # that is not checked out, such as one outside a sparse checkout,
        # still counts.
        for where in ([], ["--cached"]):
            for source, lines in _grep(where, root).items():
                if source != path:
                    keep(_find(source, lines, tags, texts, cited))
    if referrers is not None:
        for name, file_path in referrers.files:
            keep(_find(name, _read_lines(name, file_path), tags, texts, cited))
    return found


def searched(root, referrers):
    """The report's line saying what was searched for references."""
    parts = ["the file's own links"]
    if root is not None:
        # A submodule is listed as one entry, mode 160000, but git grep does
        # not search inside it, so it is not counted as a file searched. Each
        # path is counted once, though a conflict lists it at several stages.
        modes = {}
        for record in (_git(["ls-files", "-s", "-z"], root) or "").split("\0"):
            meta, _, name = record.partition("\t")
            if name:
                modes[name] = meta.split(" ", 1)[0]
        # git grep skips symlinks, mode 120000, too, so they are not counted.
        submodules = sum(1 for mode in modes.values() if mode == "160000")
        count = len(modes) - submodules - sum(1 for mode in modes.values() if mode == "120000")
        parts.append(f"the repository's {count:,} tracked file{'' if count == 1 else 's'}, in the work tree and the "
                     f"index"
                     + (f", not its {submodules:,} submodule{'' if submodules == 1 else 's'}"
                        if submodules else ""))
    if referrers is not None:
        shown = ", ".join(referrers.sources[:5]) + (" ..." if len(referrers.sources) > 5 else "")
        count = len(referrers.files)
        text = f"{count:,} given file{'' if count == 1 else 's'}"
        if referrers.sources:
            text += f" from {shown}"
            if referrers.empty:
                text += f" ({referrers.empty} was empty)"
        elif referrers.empty:
            text += " (the list was empty)"
        parts.append(text)
    line = "Searched for references: " + "; ".join(parts) + "."
    if root is None and referrers is None:
        line += (" Not in a git repository and no paths given, so references from other files "
                 "were not checked: give the files that might refer to it after `--` or with "
                 "--paths-from.")
    elif root is None:
        line += " Not in a git repository: only these were read."
    return line


# ---------------------------------------------------------------------------
# `prose compact <file>`
# ---------------------------------------------------------------------------

def _root_of(file_path):
    """The repository root above file_path, or None when `git rev-parse`
    fails there, by its exit code alone: its messages are not read."""
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                cwd=str(file_path.parent), capture_output=True, check=False)
    except OSError:
        return None
    root = result.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    return root if result.returncode == 0 and root else None


def _git_dir(root):
    """The repository's common git directory, which is never committed."""
    common = _git(["rev-parse", "--git-common-dir"], root)
    if not common or not common.strip():
        raise ValueError(f"{root}: git could not name its git directory")
    return (pathlib.Path(root) / common.strip()).resolve()


def snapshot_dir(root, state_home):
    """Where the snapshot of a file before compaction waits: prose/compact
    in its repository's git directory, or in prose's state home outside one."""
    return _git_dir(root) / "prose" / "compact" if root else state_home / "compact"


# How long a saved brief is kept: as long as a pass token, since a cold-read
# brief is of no use once its token has expired. Old briefs are deleted only
# when a later one is saved.
BRIEF_LIFETIME = 2 * 60 * 60


def brief_dir(root, state_home):
    """Where each brief printed for a subagent is also saved: prose/briefs
    in the repository's git directory, or in prose's state home outside one."""
    return _git_dir(root) / "prose" / "briefs" if root else state_home / "briefs"


def save_brief(directory, kind, text, now=None):
    """Write text to a new file in directory, named for its kind, and return
    its path. Briefs older than BRIEF_LIFETIME are deleted first, as old pass
    tokens are."""
    now = time.time() if now is None else now
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in list(directory.iterdir()):
        try:
            if now - entry.stat().st_mtime > BRIEF_LIFETIME:
                entry.unlink()
        except OSError:
            pass
    path = directory / f"{kind}-{secrets.token_hex(6)}.md"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w",
                   encoding="utf-8") as handle:
        handle.write(text + "\n")
    return path


def print_brief(marker, text, directory, kind, stream=None):
    """Print text between marker's lines, then the path of the file it is
    also saved in, which the agent gives the subagent instead of retyping the
    text. A brief that cannot be saved is still printed, and the `Brief
    file:` line says it was not saved, instead of naming a path."""
    try:
        where = str(save_brief(directory, kind, text))
    except (OSError, ValueError) as error:
        where = f"not saved ({error}); give the subagent the text between the === lines"
    print(f"=== {marker} ===", file=stream)
    print(text, file=stream)
    print(f"=== end {marker} ===", file=stream)
    print(f"Brief file: {where}", file=stream)


HANDOFF = ("Give a new subagent only the brief file's path, telling it to read that file and "
           "follow it. Don't copy the text into its prompt: a retyped brief can drop or repeat "
           "lines.")


def _snapshot_path(where, state_home):
    key = hashlib.sha256(str(where.file).encode("utf-8", "surrogateescape")).hexdigest()[:24]
    return snapshot_dir(where.root, state_home) / key


def answers_dir():
    """The directory for compactors' answers files: one only this user can
    use, in the system's temporary directory. The compactor is a subagent,
    and a harness may refuse its writes into the repository's git
    directory, where the rest of a compaction's state lives; outside the
    work tree, the file is never staged. Raises ValueError when the path is
    taken by something other than a private directory of this user's."""
    user = str(os.getuid()) if hasattr(os, "getuid") else \
        re.sub(r"[^\w.-]", "_", getpass.getuser())
    directory = pathlib.Path(tempfile.gettempdir()) / f"prose-answers-{user}"
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as error:
        raise ValueError(f"{directory}: could not make the directory for the answers file: "
                         f"{error.strerror}")
    found = os.lstat(directory)
    # Without os.getuid, as on Windows, a directory's mode bits say nothing
    # of who may use it (Windows reports 0o777 or 0o555), so only its type
    # is checked.
    if not stat.S_ISDIR(found.st_mode) or (hasattr(os, "getuid") and (
            found.st_mode & 0o077 or found.st_uid != os.getuid())):
        raise ValueError(f"{directory}: not a directory only you can use, so it cannot hold "
                         f"the answers file; remove it and run the first call again")
    return directory


def _answers_file(fields):
    """The answers file step 1 named in its brief, as its snapshot fields
    record it, or None for a snapshot that records none. A recorded path
    not ending in `.passages.txt` also gives None. This file is deleted
    when the compaction retires, on the first `prose check` after its
    commit lands (started()), and by --abandon, so a damaged snapshot must
    not name some other file for them to delete."""
    named = fields.get("answers_file") if isinstance(fields, dict) else None
    return pathlib.Path(named) if isinstance(named, str) and \
        named.endswith(".passages.txt") else None


PASSAGE_ANSWER = re.compile(r"Passage (\d+): (?:(rewritten|removed)|kept: (\S.*))")


def read_answers(lines, count):
    """({number: (answer, reason)}, [problem]) for an answers file's lines,
    against count flagged passages."""
    answers, problems = {}, []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = PASSAGE_ANSWER.fullmatch(line)
        if not match:
            problems.append(f"not 'Passage <n>: rewritten', 'Passage <n>: removed' or "
                            f"'Passage <n>: kept: <reason>': {line!r}")
            continue
        number = int(match.group(1))
        if not 1 <= number <= count:
            problems.append(f"passage {number} is not one of the {count} flagged")
        elif number in answers:
            problems.append(f"passage {number} is answered twice")
        else:
            answers[number] = (match.group(2) or "kept", match.group(3) or "")
    missing = [n for n in range(1, count + 1) if n not in answers]
    if missing:
        problems.append(f"no answer for passage{'s' if len(missing) > 1 else ''} "
                        f"{', '.join(map(str, missing))}")
    return answers, problems


def _passage_list(saved):
    """The flagged passages a snapshot recorded, as Passage."""
    out = []
    for item in saved.get("passages") or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            out.append(Passage(int(item.get("start", 0)), int(item.get("end", 0)),
                               tuple(item.get("kinds") or ()), item["text"],
                               str(item.get("note") or "")))
    return out


def _kept_spans(text, found):
    """[(start, end)] of each place text holds one of the passages found,
    word for word, with any whitespace between its words."""
    out = []
    for passage in found:
        words = passage.text.split()
        if words:
            pattern = re.compile(r"\s+".join(map(re.escape, words)))
            out += [match.span() for match in pattern.finditer(text)]
    return out


def check_passages(before, after, found, lines):
    """(report lines, failures) for the compactor's answers, lines (None
    when it wrote no file), to the passages found in before. A passage
    answered removed or rewritten passes when the new text holds its text,
    normalised, fewer times than the old text did: at least one fewer for
    each passage of that same text so answered. Otherwise it needs a
    `kept:` answer. Text is normalised as
    --verify compares headings."""
    if not found:
        return [], []
    if lines is None:
        return [], [f"no answers for the {len(found)} flagged passage"
                    f"{'' if len(found) == 1 else 's'}: the compactor writes one line for each to "
                    f"the answers file the brief names; if it wrote them elsewhere, give that "
                    f"file with --answers <file>"]
    answers, failures = read_answers(lines, len(found))
    old = normalised(list(enumerate(before.split("\n"), start=1)))[0]
    new = normalised(list(enumerate(after.split("\n"), start=1)))[0]
    counts, gone, cut = collections.Counter(), collections.Counter(), []
    for number, passage in enumerate(found, start=1):
        answer = answers.get(number, ("", ""))[0]
        counts[answer] += 1
        needle = normalised(list(enumerate(passage.text.split("\n"), start=1)))[0]
        if needle and answer not in ("", "kept"):
            gone[needle] += 1
            cut.append((number, passage, answer, needle))
    # Passages with the same text share one count: each answered removed or
    # rewritten takes one copy out of the file.
    for number, passage, answer, needle in cut:
        if new.count(needle) > max(old.count(needle), gone[needle]) - gone[needle]:
            failures.append(f"passage {number} (lines {passage.start}-{passage.end}, "
                            f"{', '.join(passage.kinds)}) is answered {answer} but is still in "
                            f"the file word for word; rewrite or remove it, or answer "
                            f"'Passage {number}: kept: <reason>'")
    report = [f"Flagged passages: {len(found)}; answered {counts['rewritten']} rewritten, "
              f"{counts['removed']} removed, {counts['kept']} kept."]
    return report, failures


class Entry(NamedTuple):
    mode: str
    oid: str
    stage: str


REGULAR = ("100644", "100755")
OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def index_entries(root, rel=None):
    """{path: [Entry]} as `git ls-files -s -z` lists the index, every stage
    of a conflict included; with rel, only that path. A failure is an
    error."""
    out = _git(["ls-files", "-s", "-z"] + (["--", f":(literal){rel}"] if rel is not None else []),
               root)
    if out is None:
        raise ValueError("git ls-files could not list the index")
    found = {}
    for record in filter(None, out.split("\0")):
        meta, tab, name = record.partition("\t")
        fields = meta.split(" ")
        if not tab or len(fields) != 3 or not OID.fullmatch(fields[1]):
            raise ValueError(f"git ls-files wrote a line that could not be read: {record[:80]!r}")
        found.setdefault(name, []).append(Entry(*fields))
    return found


def tree_entries(root, rev):
    """{path: (mode, oid)} for every file in rev's tree, as
    `git ls-tree -r -z --full-tree` lists it; {} when rev does not exist,
    as before the first commit. Any other failure is an error."""
    try:
        exists = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{tree}}"],
                                cwd=root, capture_output=True, check=False)
    except OSError as error:
        raise ValueError(f"git could not run: {error}")
    # --quiet exits 1, saying nothing, only when the rev does not exist; any
    # other failure is an error, never "no base".
    if exists.returncode == 1 and not exists.stderr.strip():
        return {}
    if exists.returncode != 0:
        raise ValueError(f"git could not read {rev}: "
                         f"{exists.stderr.decode('utf-8', 'replace').strip()}")
    # No -l: asking for sizes reads every blob, which a partial clone may not
    # hold and would fetch, or fail on offline. A size is read by oid, and
    # only where one is needed.
    out = _git(["ls-tree", "-r", "-z", "--full-tree", rev], root)
    if out is None:
        raise ValueError(f"git ls-tree could not list {rev}")
    found = {}
    for record in filter(None, out.split("\0")):
        meta, tab, name = record.partition("\t")
        fields = meta.split()
        if not tab or len(fields) != 3 or not OID.fullmatch(fields[2]):
            raise ValueError(f"git ls-tree wrote a line that could not be read: {record[:80]!r}")
        found[name] = (fields[0], fields[2])
    return found


def _blob(oid, root):
    """The bytes of the blob oid. A failure is an error."""
    try:
        result = subprocess.run(["git", "cat-file", "blob", oid], cwd=root, capture_output=True,
                                check=False)
    except OSError as error:
        raise ValueError(f"git cat-file could not run: {error}")
    if result.returncode != 0:
        raise ValueError(f"git could not read blob {oid}: "
                         f"{result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


class Staged(NamedTuple):
    oid: str
    text: str


def staged(where, step):
    """The file's staged blob and its text, LF line ends. Refused unless
    the file is a regular file in the index at stage 0 and the work tree
    matches the index, since what is checked is what will be committed."""
    entries = index_entries(where.root, where.rel).get(where.rel, [])
    if len(entries) != 1 or entries[0].stage != "0":
        raise ValueError(f"{where.rel}: not in the index as one file (unmerged?); resolve it, "
                         f"then run {step} again")
    entry = entries[0]
    if entry.mode not in REGULAR:
        raise ValueError(f"{where.rel}: the index holds it as mode {entry.mode}, not a regular "
                         f"file; a symlink holds no prose to compact")
    # git diff and git add do not see a file marked assume-unchanged (a
    # lowercase tag) or skip-worktree (S), so its edits would go unchecked
    # and unstaged.
    tags = _git(["ls-files", "-v", "-z", "--", f":(literal){where.rel}"], where.root)
    if tags is None:
        raise ValueError("git ls-files could not read the file's flags")
    for record in filter(None, tags.split("\0")):
        tag = record[:1]
        if tag == "S" or tag.islower():
            mark, flag = ("skip-worktree", "--no-skip-worktree") if tag == "S" else \
                ("assume-unchanged", "--no-assume-unchanged")
            # With core.ignoreStat set, git add marks the file again, so
            # the usual remedy would loop.
            again = _git(["config", "--type=bool", "core.ignoreStat"], where.root)
            add = (f"; core.ignoreStat is true, so stage it with "
                   f"git -c core.ignoreStat=false add {command_path(where.name)} before clearing "
                   f"the mark") if (again or "").strip() == "true" else ""
            raise ValueError(f"{where.rel} is marked {mark}, so its changes cannot be seen; "
                             f"clear the mark (git update-index {flag} "
                             f"{command_path(where.name)}) first{add}, then run {step} again")
    try:
        # --no-textconv and --no-ext-diff: a diff driver could make the two
        # read the same when their bytes differ.
        result = subprocess.run(["git", "diff", "--quiet", "--no-textconv", "--no-ext-diff",
                                 "--", f":(literal){where.rel}"],
                                cwd=where.root, capture_output=True, check=False)
    except OSError as error:
        raise ValueError(f"git diff could not run: {error}")
    if result.returncode == 1:
        raise ValueError(f"{where.rel} has changes that are not staged. Stage the file "
                         f"(git add {command_path(where.name)}), then run {step} again")
    if result.returncode != 0:
        raise ValueError(f"git diff failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    try:
        text = _blob(entry.oid, where.root).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{where.rel} as staged is not UTF-8 text (byte {error.start}); "
                         f"compaction reads prose, so a binary file has nothing to compact")
    return Staged(entry.oid, _lf(text))


class Target(NamedTuple):
    file: pathlib.Path
    root: Optional[str]
    rel: str
    name: str = ""  # as the caller spelt it, for the commands printed back


def target(name):
    """The file to compact, its repository root (None outside one) and its
    path inside the repository. Inside a repository the path must be one
    `git ls-files` lists, spelt exactly as it lists it."""
    file_path = pathlib.Path(name).absolute()
    # The directory is resolved and the name kept, so a tracked symlink is
    # checked by the path git lists, not by its target's.
    file_path = file_path.parent.resolve() / file_path.name
    if not file_path.is_file():
        raise ValueError(f"{name}: no such file")
    root = _root_of(file_path)
    if not root:
        return Target(file_path, None, file_path.name, name)
    try:
        rel = str(file_path.relative_to(pathlib.Path(root).resolve()))
    except ValueError:
        rel = ""
    listed = _git(["ls-files", "-z", "--", f":(literal){rel}"], root) if rel else ""
    if rel not in (listed or "").split("\0"):
        raise ValueError(f"{name}: not a tracked file; give its path as `git ls-files` lists it")
    return Target(file_path, root, rel, name)


def command_path(name):
    """name as a printed command can take it: quoted for the shell, and
    behind `./` when it starts with `-`, so no command reads it as an
    option."""
    if name.startswith("-"):
        name = "./" + name
    return shlex.quote(name)


def _referrers(given, where, stdin):
    """Referrers for what the caller gave, or None when it gave nothing."""
    if not given.supplied():
        return None
    paths = list(given.paths)
    if given.paths_from:
        try:
            if given.paths_from == "-" and stdin is None:
                raise ValueError("--paths-from - reads stdin, which is closed")
            data = stdin.read() if given.paths_from == "-" else \
                pathlib.Path(given.paths_from).read_bytes()
        except OSError as error:
            raise ValueError(f"{given.paths_from}: could not read the list of paths: "
                             f"{error.strerror}")
        listed = read_paths_from(data, given.nul)
        where_from = "the list on stdin" if given.paths_from == "-" else \
            f"the list in {given.paths_from}"
        return referrer_files(listed + paths, where.file, where.root,
                              ([where_from] if listed else []) + paths,
                              "" if listed else where_from)
    return referrer_files(paths, where.file, where.root)


def brief(name, state_home, command, given=Given(), stdin=None):
    """Save the file as it is now, and print the compactor's brief. Returns
    BRIEF_PRINTED."""
    where = target(name)
    referrers = _referrers(given, where, stdin)
    # Inside a repository the snapshot is the staged blob, and its id is
    # what the commit gate matches against the base's.
    start = staged(where, "the first call") if where.root is not None else None
    if start is not None:
        # A compaction starts from the committed file. From an uncommitted
        # edit, the gate would refuse to commit that edit alone, since it
        # differs from the base and has no records: commit it first.
        head = tree_entries(where.root, "HEAD").get(where.rel)
        if head is None or head[1] != start.oid:
            raise ValueError(f"{where.rel} as staged differs from HEAD's; commit the change you "
                             f"were making first (SKILL.md, *Compaction*), then run the first "
                             f"call on the committed file")
    text = start.text if start else _lf(where.file.read_text(encoding="utf-8"))
    now = time.time()
    # Snapshots do not expire: a compaction stays started until it retires
    # on commit (in started()) or is abandoned. Each is named for its file's path,
    # so there is one per file.
    directory = snapshot_dir(where.root, state_home)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    found = references(where.rel, heading_texts(text), anchors(text), "", where.root, referrers,
                       where.file)
    # Every detector runs, with no threshold: a person's request to compact
    # a file gets every passage answered, as a due doc does.
    flagged = passages(text, where.rel, where.root)
    setting = settings([where.rel], where.root)[where.rel]
    snapshot = _snapshot_path(where, state_home)
    answers = answers_dir() / (snapshot.name + ".passages.txt")
    fields = {"path": str(where.file), "rel": where.rel, "root": where.root, "text": text,
              "saved": now, "passages": [dict(p._asdict(), kinds=list(p.kinds)) for p in flagged],
              "answers_file": str(answers)}
    if start is not None:
        fields["before"] = start.oid
    with _snapshot_lock(snapshot.parent):
        _clear_drafts(snapshot)
        _write_snapshot(snapshot, fields)
        # Answers to an earlier start's passages would answer the wrong ones.
        try:
            answers.unlink()
        except FileNotFoundError:
            pass

    markers = history_markers(text)
    held = {}
    for ref in found:
        held.setdefault(ref.needle, []).append(ref.source)
    lines = [BRIEF.read_text(encoding="utf-8").rstrip("\n"), f"\nThe file: {where.file}",
             f"Size: {len(text.encode('utf-8')):,} bytes, {len(text.split()):,} words."]
    if markers:
        lines.append(f"\nHistory markers the script found ({len(markers)}); there may be others:")
        lines += [f"  line {marker.line}: «{marker.words}»" for marker in markers[:40]]
    if held:
        lines.append("\nHeadings other files name or link to, by their text or their `#anchor`. "
                     "Keep each, with its exact text:")
        lines += [f"  {needle}  (in {', '.join(sorted(set(files))[:3])})"
                  for needle, files in sorted(held.items())]
    lines.append("\nCredits: " + (
        "drop each \"who decided\" credit, such as \"(Adam, 2026-10-24)\"; this file's "
        "prose-compact-attribution=drop says so." if setting.drop_attribution else
        "keep each \"who decided\" credit, such as \"(Adam, 2026-10-24)\", where the "
        "document gives one."))
    lines.append(f"\nAnswers file: {answers}")
    if flagged:
        lines.append(f"\nFlagged passages ({len(flagged)}). Answer every one in the answers file, "
                     f"one line each, as compact.md says:")
        for number, passage in enumerate(flagged, start=1):
            note = f"; {passage.note}" if passage.note else ""
            lines.append(f"\nPassage {number}, lines {passage.start}-{passage.end}, "
                         f"{', '.join(passage.kinds)}{note}:")
            lines += ["    " + line for line in passage.text.split("\n")]
    else:
        lines.append("\nFlagged passages: none. Leave the answers file unwritten.")
    print_brief("compaction brief", "\n".join(lines), brief_dir(where.root, state_home),
                "compaction")
    again = given.options()
    if given.paths_from == "-":
        again += "   (with the same list on stdin)"
    stage = f"git add {command_path(name)}\n  " if where.root is not None else ""
    print(f"\n{HANDOFF} Then, as the required last step, run:\n\n  {stage}{command} compact {command_path(name)} --verify{again}")
    if flagged:
        print("\nIf the compactor's reply has an `Answers: <file>` line, add `--answers <file>` "
              "to --verify.")
    if where.root is None and referrers is None:
        print("\nThe file is outside any git repository, so --verify checks only its own links "
              "unless you give it the files that might refer to it, after `--` or with "
              "--paths-from (SKILL.md, *Compaction*).")
    return BRIEF_PRINTED


class Report(NamedTuple):
    lines: list
    failures: list


def check_result(before, after, rel, root, referrers=None, kept=(), file=None):
    """The verification report for a file compacted from before to after.
    Failures are what the result must fix. The other lines inform whoever
    checks the result for a lost conclusion: the reviewer, or a person.
    kept lists the flagged passages the compactor kept with a reason. A
    history marker inside the text of one of them is not a failure, since
    the reviewer judges that reason; a marker elsewhere on the same line
    still fails. file is the doc's absolute path, for references."""
    lines, failures = [], []
    size_before, size_after = len(before.encode("utf-8")), len(after.encode("utf-8"))
    words_before, words_after = len(before.split()), len(after.split())
    share = (size_before - size_after) * 100 / size_before if size_before else 0
    lines.append(f"Size: {size_before:,} -> {size_after:,} bytes ({-share:+.0f}%), "
                 f"{words_before:,} -> {words_after:,} words.")
    if not after.strip():
        failures.append("the file is empty")
    if size_after > size_before:
        failures.append("the file grew")

    gone = gone_headings(before, after)
    # Each removed heading's anchor is searched even when a kept heading
    # gives the same anchor, so a rename that keeps the anchor still blocks.
    # A heading that occurs several times and lost an occurrence gives every
    # anchor it had: which of them now leads elsewhere cannot be told.
    # Erring toward blocking, as everywhere in --verify.
    removed = (anchors(before) - anchors(after)) | {slug(h) for h in gone if slug(h)} | {
        anchor for anchor, heading in heading_anchors(before) if heading in gone}
    # Only a heading or anchor the compaction removed is looked for, so a
    # reference already broken before is not its doing.
    found = references(rel, gone, removed, after, root, referrers, file)
    lines.append(searched(root, referrers))
    lines.append(f"References to removed headings: {len(found)}.")
    for ref in found:
        what = f"links to {ref.needle}" if ref.needle.startswith("#") else f"names '{ref.needle}'"
        failures.append(f"{ref.source}:{ref.line} {what}, a heading the compaction removed")

    if gone:
        lines.append(f"Headings removed or renamed ({len(gone)}): "
                     + "; ".join(gone[:30]) + (" ..." if len(gone) > 30 else ""))
    dropped = gone_terms(before, after)
    if dropped:
        lines.append(f"Names that are gone ({len(dropped)}); the reviewer checks each: "
                     + ", ".join(term for _, term in dropped[:60])
                     + (" ..." if len(dropped) > 60 else ""))
    for marker in history_markers(after, _kept_spans(after, kept)):
        failures.append(f"history marker left at line {marker.line}: «{marker.words}»")
    return Report(lines, failures)


# What gone_terms looks for, beside code spans and headings: a command-line
# flag, a CONSTANT_NAME, and a path or file name.
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]+")
CONSTANT = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
PATH = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.-]+|\b[\w-]+\.(?:md|py|sh|json|ya?ml|toml|ts|js|go|rs)\b")


def gone_terms(before, after):
    """[(kind, term)] for each code span, flag, constant, path and heading in
    before that after no longer contains anywhere, in order of first use.
    A removed name is the cheapest sign of a removed conclusion, so the
    reviewer gets this list."""
    found, seen = [], set()
    # Compared with whitespace collapsed, so a name the new text wraps
    # across a line still counts as present.
    flat = " ".join(after.split())

    def add(kind, term):
        term = " ".join(term.split())
        if term and term not in seen and term not in flat:
            seen.add(term)
            found.append((kind, term))

    # A heading is compared by its text without Markdown, as heading_texts
    # gives it, since that is how a reader or a citing comment names it.
    for heading in gone_headings(before, after):
        if heading not in seen:
            seen.add(heading)
            found.append(("heading", heading))
    for line in _unfenced_code(before):
        for pattern, kind in ((FLAG, "flag"), (CONSTANT, "constant"), (PATH, "path")):
            for match in pattern.finditer(line):
                add(kind, match.group(0).rstrip("."))
    for span in re.findall(r"`([^`\n]+(?:\n[^`\n]+)?)`", "\n".join(_unfenced_code_kept(before))):
        add("code", span)
    return [(kind, f"`{term}`" if kind == "code" else term) for kind, term in found]


class Change(NamedTuple):
    number: int
    kind: str
    heading: str
    old: list
    new: list


# The `>` markers that put a line inside a block quote, each with up to
# three spaces before it and one after. A fence or indented code inside a
# quote is still code.
QUOTE_MARKERS = re.compile(r"^(?:[ \t]{0,3}> ?)*")


def _unquoted(line):
    """line without the block-quote markers that start it."""
    return QUOTE_MARKERS.sub("", line, count=1)


# A fence opens a line, after any list marker: "- ```yaml" opens one too. A
# run of backticks with another backtick after it on the line is inline
# code, not a fence, as in CommonMark: "```a `` b``` is ..." opens nothing.
FENCE = re.compile(r"(?:(?:[-*+]|[0-9]{1,9}[.)])[ \t]+)?(`{3,}(?=[^`]*$)|~{3,})")


def _paragraphs(text):
    """(paragraphs, the heading above each): the text split at blank lines,
    except blank lines inside fenced blocks, fenced blocks inside block quotes
    included."""
    paragraphs, headings, current, heading, fence = [], [], [], "", None
    for line in text.split("\n"):
        unquoted = _unquoted(line)
        if fence and _closes(fence, unquoted):
            fence = None
        elif not fence:
            fence = _opens(unquoted)
        if not fence and not line.strip():
            if current:
                paragraphs.append("\n".join(current))
                headings.append(heading)
                current = []
            continue
        match = HEADING.match(line) if not fence else None
        if match and not current:
            heading = match.group(1)
        current.append(line)
    if current:
        paragraphs.append("\n".join(current))
        headings.append(heading)
    return paragraphs, headings


def changes(before, after):
    """[Change] between the two texts, paragraph by paragraph: each removed,
    rewritten or added run of paragraphs, with the heading it sits under in
    the old text. Rewrapping prose is not a change: a paragraph is compared
    with its whitespace collapsed. A paragraph that holds a fence, or a line
    indented four or more spaces or a tab, inside a block quote or not, is
    compared exactly, since there indentation is meaning: code, YAML, a
    nested list."""
    old, old_headings = _paragraphs(before)
    new, new_headings = _paragraphs(after)

    def key(paragraph):
        lines = [_unquoted(line) for line in paragraph.split("\n")]
        if any(FENCE.match(line.lstrip()) or line.startswith(("    ", "\t"))
               for line in lines):
            return paragraph
        return " ".join(paragraph.split())

    matcher = difflib.SequenceMatcher(None, [key(p) for p in old], [key(p) for p in new],
                                      autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"delete": "removed", "replace": "rewritten", "insert": "added"}[tag]
        heading = old_headings[i1] if i1 < len(old_headings) else \
            (new_headings[j1] if j1 < len(new_headings) else "")
        out.append(Change(len(out) + 1, kind, heading, old[i1:i2], new[j1:j2]))
    return out


REVIEW_BRIEF = HERE.parent / "compact-review.md"


def review(name, state_home, command="prose.py"):
    """Write what the compaction removed and rewrote to a file, and print the
    reviewer's brief, which names it. Returns BRIEF_PRINTED."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    current = staged(where, "--review") if where.root is not None else None
    after = current.text if current else _lf(where.file.read_text(encoding="utf-8"))
    found = changes(_lf(saved["text"]), after)
    dropped = gone_terms(_lf(saved["text"]), after)
    path = _snapshot_path(where, state_home).with_suffix(".review.md")
    parts = [f"# What the compaction of {where.rel} changed\n"]
    if dropped:
        parts.append("## Names in the old file that the new one no longer has\n")
        parts.extend(f"- {kind}: {term}" for kind, term in dropped)
        parts.append("")
    # The reviewer judges the answers --verify passed for this blob, as the
    # snapshot stores them; the live answers file is not read.
    answered = _stored_answers(saved, current.oid if current else "")
    kept = _kept_passages(saved, answered)
    if kept:
        parts.append("## Flagged passages kept\n")
        for number, passage, reason in kept:
            note = f"; {passage.note}" if passage.note else ""
            parts.append(f"### Passage {number}, lines {passage.start}-{passage.end}, "
                         f"{', '.join(passage.kinds)}{note}\n\nReason given: {reason}\n")
            parts.append("\n".join("    " + line for line in passage.text.split("\n")) + "\n")
    for change in found:
        parts.append(f"## Change {change.number}: {change.kind}, under "
                     f"\"{change.heading or '(the top)'}\"\n")
        if change.old:
            parts.append("### Before\n\n" + "\n\n".join(change.old) + "\n")
        if change.new:
            parts.append("### After\n\n" + "\n\n".join(change.new) + "\n")
    # Written only under the lock, after the snapshot is found to be the
    # one loaded, so a --review of an older compaction finishing late cannot
    # replace a newer one's changes. The draft exists only while the lock is
    # held, so any draft another step finds was left by a killed one.
    draft = path.with_name(f".{path.name}.{os.getpid()}")
    # The snapshot notes the review: the blob it was of, and how many
    # changes the reviewer must answer, which --reviewed checks its reply
    # against.
    review = {"oid": current.oid if current else None, "changes": len(found),
              "kept": [number for number, _, _ in kept],
              "judged": _kept_answers(answered), "printed": time.time()}

    def change(fields):
        draft.write_text("\n".join(parts), encoding="utf-8")
        os.replace(draft, path)
        fields["review"] = review

    if not _update_snapshot(where, state_home, saved, change):
        raise ValueError(f"the snapshot of {name} changed while --review ran; run it again")
    print_brief("compaction review brief", "\n".join([
        REVIEW_BRIEF.read_text(encoding="utf-8").rstrip("\n"), f"\nThe changes: {path}",
        f"The compacted file: {where.file}",
        f"The repository: {where.root}" if where.root else
        "The repository: none, since the file is outside one. Check claims against the old "
        "text only.",
        f"Changes: {len(found)}. Names gone: {len(dropped)}. Flagged passages kept: "
        f"{len(kept)}."]),
        brief_dir(where.root, state_home), "compaction-review")
    print(f"\n{HANDOFF} Run it on the same model as the compactor. Save its reply to a file; "
          "when its findings are answered, run:\n\n"
          f"  {command} compact {command_path(name)} --reviewed <reply file> "
          "[--dispositions <file>]")
    return BRIEF_PRINTED


def _read_answers(saved, given=""):
    """(path, bytes) of the compactor's answers: the file given with
    --answers, or else the one the brief named, its bytes None when the
    compactor wrote none there. Only --verify reads it; the later steps
    read the copy it stores. A file given that cannot be read is an
    error."""
    path = pathlib.Path(given) if given else _answers_file(saved)
    if path is None:
        return None, None
    try:
        return path, path.read_bytes()
    except FileNotFoundError:
        if given:
            raise ValueError(f"{given}: no such file, given with --answers")
        return path, None
    except OSError as error:
        raise ValueError(f"{path}: could not read the answers to the flagged passages: "
                         f"{error.strerror}")


def _stored_answers(saved, blob):
    """The copy of the answers that --verify passed for blob, the staged
    blob's id ("" outside a repository), as the snapshot stores it; None
    when it stores none."""
    return _answers_for(saved.get("answers"), blob)


def _answers_for(copies, blob):
    """copies[blob] when copies is a snapshot's {blob: answers}, else None."""
    return copies.get(blob) if isinstance(copies, dict) else None


def _answer_map(saved, lines):
    """{"<n>": [answer, reason]} for the answers in lines, to the passages
    saved lists."""
    answers, _ = read_answers(lines or [], len(_passage_list(saved)))
    return {str(number): list(answer) for number, answer in answers.items()}


def _kept_answers(answered):
    """{"<n>": reason} for each passage a stored copy of the answers keeps."""
    if not isinstance(answered, dict):
        return {}
    return {number: answer[1] for number, answer in answered.items()
            if isinstance(answer, list) and answer[:1] == ["kept"] and len(answer) > 1}


def _unjudged(answered, judged):
    """The numbers of the passages that answered, a stored copy of the
    answers, keeps, and that judged, a review's {"<n>": reason}, did not
    judge with the same reason."""
    judged = judged if isinstance(judged, dict) else {}
    return sorted((number for number, reason in _kept_answers(answered).items()
                   if judged.get(number) != reason), key=int)


def _kept_passages(saved, answered):
    """[(number, Passage, reason)] for each flagged passage kept in
    answered, a stored copy of the answers."""
    found = _passage_list(saved)
    return [(int(number), found[int(number) - 1], reason)
            for number, reason in sorted(_kept_answers(answered).items(),
                                         key=lambda item: int(item[0]))
            if 1 <= int(number) <= len(found)]


@contextlib.contextmanager
def _snapshot_lock(directory):
    """Hold the lock on the snapshot directory, so steps of one compaction
    run at once never write over each other's changes to a snapshot. Only
    where fcntl exists (macOS, Linux); on Windows it does nothing, and
    steps run at once may overwrite each other's changes."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(directory / ".lock", "a", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _clear_drafts(snapshot):
    """Delete this snapshot's drafts: files named `.<name>.*`, where name
    is the snapshot's file name, which its review file's name starts
    with. Called under the lock; every draft of the snapshot or its
    review file is written and renamed under it, so a draft found here was
    left by a killed step. Without fcntl (Windows) there is no lock, and a
    step running at the same time may lose its draft and exit 2."""
    for draft in snapshot.parent.glob(f".{snapshot.name}.*"):
        try:
            draft.unlink()
        except FileNotFoundError:
            pass


def _write_snapshot(path, fields):
    """Write a snapshot whole, by rename, so no reader sees half of one."""
    draft = path.with_name(f".{path.name}.{os.getpid()}")
    draft.write_text(json.dumps(fields), encoding="utf-8")
    os.replace(draft, path)


def _update_snapshot(where, state_home, loaded, change):
    """Apply change to the snapshot as it is now, under the lock, and save
    it. Returns False, changing nothing, when the snapshot is no longer the
    one loaded: a new step 1 replaced it, or it is gone."""
    snapshot = _snapshot_path(where, state_home)
    with _snapshot_lock(snapshot.parent):
        try:
            current = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(current, dict) \
                or current.get("saved") != loaded.get("saved") \
                or current.get("before") != loaded.get("before"):
            return False
        change(current)
        _write_snapshot(snapshot, current)
    loaded.clear()
    loaded.update(current)
    return True


def _note_in_snapshot(where, state_home, saved, key, oid, passed, answered=None, blob=""):
    """Add oid to, or with passed False remove it from, the snapshot's list
    under key ("verified" or "reviewed"). The lists say which blobs this
    compaction itself checked, which is what retires it (in started()): records
    are shared by every compaction that reaches the same content, the lists
    are not. A list of another shape counts as empty. With key "verified",
    the snapshot also stores answered, the answers it passed, keyed by
    blob. oid and blob are the same staged blob, but oid is None where no
    record is kept and changes no list, while blob is "" outside a
    repository. Every later step and the gate read that stored copy in
    place of the answers file. When --verify did not pass, the copy for
    blob is forgotten."""
    def change(current):
        if key == "verified":
            copies = current.get("answers")
            copies = dict(copies) if isinstance(copies, dict) else {}
            copies.pop(blob, None)
            if passed:
                copies[blob] = answered
            current["answers"] = copies
        if oid is None:
            return
        listed = current.get(key)
        oids = [item for item in (listed if isinstance(listed, list) else [])
                if isinstance(item, str) and item != oid]
        if passed:
            oids.append(oid)
        current[key] = oids
    return _update_snapshot(where, state_home, saved, change)


def _load_snapshot(where, name, state_home):
    """The snapshot `compact <file>` saved, however old."""
    try:
        saved = json.loads(_snapshot_path(where, state_home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if not isinstance(saved, dict) or not isinstance(saved.get("text"), str):
        raise ValueError(f"no snapshot of {name}: run 'compact {command_path(name)}' first, "
                         f"before the file is changed")
    return saved


def verify(name, state_home, passes=None, given=Given(), stdin=None, answers=""):
    """Check the compacted file against its snapshot; print the report.
    Returns VERIFIED or FAILED. Inside a repository, passes(root) is prose's
    pass directory, where a pass is recorded for the commit gate. answers
    is the answers file given with --answers; without it, the one the
    brief named is read."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    referrers = _referrers(given, where, stdin)
    # Inside a repository the staged blob is checked, and the record is
    # named by its id as `git ls-files -s` lists it, which the gate reads.
    current = staged(where, "--verify") if where.root is not None else None
    after = current.text if current else _lf(where.file.read_text(encoding="utf-8"))
    path, data = _read_answers(saved, answers)
    try:
        answered = None if data is None else data.decode("utf-8").split("\n")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: could not read the answers to the flagged passages: {error}")
    found = _passage_list(saved)
    kept = [found[number - 1] for number, (answer, _) in
            read_answers(answered or [], len(found))[0].items() if answer == "kept"]
    report = check_result(_lf(saved["text"]), after, where.rel, where.root, referrers, kept,
                          where.file)
    extra, failures = check_passages(_lf(saved["text"]), after, found, answered)
    report = Report(report.lines + extra, report.failures + failures)
    print(f"prose compact: {where.rel}")
    for line in report.lines:
        print(line)
    record = None
    if current is not None and passes is not None:
        record = verified_dir(passes(where.root)) / current.oid
    oid = current.oid if record is not None else None
    if report.failures:
        if record is not None:
            try:
                record.unlink()
            except FileNotFoundError:
                pass
        _note_in_snapshot(where, state_home, saved, "verified", oid, False,
                          blob=current.oid if current else "")
        print(f"\nFailed ({len(report.failures)}):")
        for failure in report.failures:
            print(f"  {failure}")
        print("\nFix these in the file, then run --verify again.")
        return FAILED
    if record is not None:
        _write_record(record, {"path": where.rel, "verified": time.time(),
                               "before": saved.get("before")})
    if not _note_in_snapshot(where, state_home, saved, "verified", oid, True,
                             _answer_map(saved, answered), current.oid if current else ""):
        raise ValueError(f"the snapshot of {name} changed while --verify ran, by a new "
                         f"step 1 or --abandon; if a compaction is still started, run "
                         f"--verify again on it")
    print("\nVerified. Ask the person before committing if the compactor listed a conclusion "
          "it would drop.")
    return VERIFIED


# ---------------------------------------------------------------------------
# A completed review
# ---------------------------------------------------------------------------

VERDICT = re.compile(r"Change (\d+): (superseded|folded in|lost|holds|false)\b")
TOTALS = re.compile(r"Totals: (\d+) lost, (\d+) false")
ANSWER = re.compile(r"(Change|Passage) (\d+): (?:(fixed)|kept: (\S.*))")
PASSAGE_VERDICT = re.compile(r"Passage (\d+): (justified|unjustified)\b")


def _lines(path, what):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{path}: could not read the {what}: {error}")


def reviewed(name, state_home, passes, reply, dispositions=""):
    """Check that the last review's reply answers every change, and that
    each `lost` or `false` finding has an answer: fixed, in a file that has
    changed since the review, or kept with a reason. Inside a repository,
    record the completed review for the staged blob, with the passages
    marked fixed, which the gate requires the stored answers no longer to
    keep.
    Returns VERIFIED."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    review_of = saved.get("review")
    if not isinstance(review_of, dict) or not isinstance(review_of.get("changes"), int):
        raise ValueError(f"no review of this compaction of {name}: run "
                         f"'compact {command_path(name)} --review' "
                         f"and give a reviewer its brief first")
    current = staged(where, "--reviewed") if where.root is not None else None
    verdicts, totals = {}, []
    findings, kept = {}, review_of.get("kept") if isinstance(review_of.get("kept"), list) else []
    # Each passage kept in the answers --verify passed for the staged blob
    # must have been judged by this review, with the same reason. A passage
    # kept since the review, or one whose reason was rewritten, was not.
    answered = _stored_answers(saved, current.oid if current else "")
    if answered is None and _passage_list(saved):
        raise ValueError(f"--verify has not passed {where.rel} as staged, so its answers to the "
                         f"flagged passages are unchecked; run 'compact {command_path(name)} "
                         f"--verify' first, then --reviewed again")
    unseen = _unjudged(answered, review_of.get("judged"))
    if unseen:
        raise ValueError(f"the answers --verify passed for the staged file keep passage"
                         f"{'s' if len(unseen) > 1 else ''} {', '.join(unseen)}, which the "
                         f"review did not judge with that reason; run 'compact "
                         f"{command_path(name)} --review' again, give a reviewer the new brief, "
                         f"then run --reviewed with that reply")
    judged, unjustified = set(), set()
    for line in _lines(reply, "reviewer's reply"):
        line = line.strip()
        if TOTALS.fullmatch(line):
            totals.append(tuple(map(int, TOTALS.fullmatch(line).groups())))
            continue
        if line.startswith("Passage "):
            match = PASSAGE_VERDICT.match(line)
            if not match:
                raise ValueError(f"{reply}: a line the review brief's form does not allow: "
                                 f"{line!r}")
            number = int(match.group(1))
            if number not in kept:
                raise ValueError(f"{reply}: passage {number} is not one the compactor kept")
            judged.add(number)
            if match.group(2) == "unjustified":
                unjustified.add(number)
            continue
        if not line.startswith("Change "):
            continue
        match = VERDICT.match(line)
        if not match:
            raise ValueError(f"{reply}: a line the review brief's form does not allow: {line!r}")
        number, verdict = int(match.group(1)), match.group(2)
        if not 1 <= number <= review_of["changes"]:
            raise ValueError(f"{reply}: change {number} is not one of the review's "
                             f"{review_of['changes']} changes")
        verdicts.setdefault(number, []).append(verdict)
        if verdict in ("lost", "false"):
            findings.setdefault(number, []).append(verdict)
    missing = [n for n in range(1, review_of["changes"] + 1) if n not in verdicts]
    if missing:
        raise ValueError(f"{reply}: no verdict for change{'s' if len(missing) > 1 else ''} "
                         f"{', '.join(map(str, missing))}; the reviewer answers every change")
    unjudged = [n for n in kept if n not in judged]
    if unjudged:
        raise ValueError(f"{reply}: no verdict for kept passage{'s' if len(unjudged) > 1 else ''} "
                         f"{', '.join(map(str, unjudged))}; the reviewer judges every kept "
                         f"passage's reason")
    counted = (sum(v.count("lost") for v in findings.values()),
               sum(v.count("false") for v in findings.values()))
    if totals != [counted]:
        raise ValueError(f"{reply}: needs one line 'Totals: {counted[0]} lost, {counted[1]} "
                         f"false', matching its verdicts")
    answers = {}
    wanted = {("Change", n) for n in findings} | {("Passage", n) for n in unjustified}
    if wanted:
        if not dispositions:
            parts = []
            if findings:
                parts.append(f"{counted[0]} lost and {counted[1]} false, in "
                             f"change{'s' if len(findings) > 1 else ''} "
                             f"{', '.join(map(str, sorted(findings)))}")
            if unjustified:
                parts.append(f"an unjustified reason for kept passage"
                             f"{'s' if len(unjustified) > 1 else ''} "
                             f"{', '.join(map(str, sorted(unjustified)))}")
            raise ValueError(f"the review found {' and '.join(parts)}: answer each in a file of "
                             f"'Change <n>: fixed', 'Change <n>: kept: <reason>', "
                             f"'Passage <n>: fixed' or 'Passage <n>: kept: <reason>' lines and "
                             f"pass it with --dispositions")
        for line in _lines(dispositions, "dispositions"):
            line = line.strip()
            if not line:
                continue
            match = ANSWER.fullmatch(line)
            if not match:
                raise ValueError(f"{dispositions}: not 'Change <n>: fixed', 'Change <n>: kept: "
                                 f"<reason>', 'Passage <n>: fixed' or 'Passage <n>: kept: "
                                 f"<reason>': {line!r}")
            key = (match.group(1), int(match.group(2)))
            what = f"{key[0].lower()} {key[1]}"
            if key not in wanted or key in answers:
                raise ValueError(f"{dispositions}: {what} "
                                 + ("is answered twice" if key in answers else
                                    "has no finding to answer" if key[0] == "Change" else
                                    "was not found unjustified"))
            answers[key] = "fixed" if match.group(3) else "kept"
        unanswered = sorted(wanted - set(answers))
        if unanswered:
            raise ValueError(f"{dispositions}: no answer for "
                             + ", ".join(f"{kind.lower()} {n}" for kind, n in unanswered))
    # A kept passage is fixed only by answering it removed or rewritten,
    # which --verify then checks against the file.
    fixed = {str(n) for (kind, n), answer in answers.items()
             if kind == "Passage" and answer == "fixed"}
    still = sorted(set(fixed) & set(_kept_answers(answered)), key=int)
    if still:
        raise ValueError(f"passage{'s' if len(still) > 1 else ''} {', '.join(still)} "
                         f"{'are' if len(still) > 1 else 'is'} marked fixed but the answers "
                         f"--verify passed for the staged file still keep {'them' if len(still) > 1 else 'it'}; "
                         f"remove or shorten the passage, update its answer, run --verify, "
                         f"then --reviewed again")
    # The review must have seen what is staged. With nothing fixed, the
    # staged blob is the one reviewed. With a finding fixed, the staged blob
    # is a later one, and the review was of the compacted file, not of the
    # copy from before the compaction.
    # Outside a repository there is no blob to compare, so it is not checked.
    if current is not None:
        if "fixed" not in answers.values():
            if current.oid != review_of.get("oid"):
                raise ValueError(f"{where.rel} as staged is not the file the reviewer read; run "
                                 f"--review again on it, give a reviewer the new brief, then "
                                 f"run --reviewed with that reply")
        elif current.oid == review_of.get("oid"):
            raise ValueError(f"a finding is marked fixed, but {where.rel} as staged is the "
                             f"file the reviewer read; fix it, stage it, run --verify, then "
                             f"run --reviewed again")
        elif review_of.get("oid") == saved.get("before"):
            raise ValueError(f"the review read {where.rel} before it was compacted, so there "
                             f"was nothing to fix; run --review again on the compacted file")
    if current is not None and passes is not None:
        _write_record(reviewed_dir(passes(where.root)) / current.oid,
                      {"path": where.rel, "reviewed": time.time(), "before": saved.get("before"),
                       "review_of": review_of.get("oid"), "lost": counted[0],
                       "false": counted[1], "judged": review_of.get("judged") or {},
                       "fixed": sorted(fixed, key=int)})
        if not _note_in_snapshot(where, state_home, saved, "reviewed", current.oid, True):
            raise ValueError(f"the snapshot of {name} changed while --reviewed ran, by a new "
                             f"step 1 or --abandon; if a compaction is still started, run "
                             f"--review and --reviewed again on it")
    print(f"Review of {where.rel} complete: {counted[0]} lost, {counted[1]} false, "
          f"{sum(a == 'fixed' for a in answers.values())} fixed, "
          f"{sum(a == 'kept' for a in answers.values())} kept; "
          f"{len(kept)} kept passage{'' if len(kept) == 1 else 's'} judged, "
          f"{len(unjustified)} unjustified.")
    return VERIFIED


# ---------------------------------------------------------------------------
# The commit gate
# ---------------------------------------------------------------------------
#
# A pass of --verify and a completed review are each recorded under prose's
# pass directory, named by the staged blob's id as `git ls-files -s` lists
# it. `prose check` refuses to sign while a file `prose compact` was started
# on is staged with a blob other than the base's and lacks either record for
# its staged blob with `before` equal to the compaction's start, until the
# compaction retires on commit or is abandoned.

def verified_dir(passes):
    """Where the records of passes of --verify live: a directory inside
    prose's pass directory. prose deletes the files there older than two
    hours, the life of a pass token, but leaves directories alone, so the
    records stay as long as the snapshots they were made for."""
    return passes / "compacted"


def reviewed_dir(passes):
    """Where the records of completed reviews live, beside verified_dir."""
    return passes / "reviewed"


def _write_record(record, fields):
    directory = record.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    draft = record.with_name(f".{record.name}.{os.getpid()}")
    draft.write_text(json.dumps(fields), encoding="utf-8")
    os.replace(draft, record)


def _record(directory, oid, start):
    """True when directory holds a record for oid whose before is start."""
    try:
        fields = json.loads((directory / oid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(fields, dict) and fields.get("before") == start


def _review_covers(directory, oid, start, answered):
    """True when directory holds a completed review of oid from start that
    meets two conditions against answered, the answers --verify passed for
    oid. It judged every passage those answers keep, with the same reason.
    And none of the passages it marked fixed is still kept in them."""
    try:
        fields = json.loads((directory / oid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    fixed = fields.get("fixed") if isinstance(fields, dict) else None
    return isinstance(fields, dict) and fields.get("before") == start \
        and not _unjudged(answered, fields.get("judged")) \
        and not set(fixed if isinstance(fixed, list) else ()) & set(_kept_answers(answered))


def _size(oid, root):
    out = _git(["cat-file", "-s", oid], root)
    if out is None or not out.strip().isdigit():
        raise ValueError(f"git could not read the size of blob {oid}")
    return int(out.strip())


def started(root, head=None, passes=None, answered=None):
    """{path: {the blob ids compactions started from}} for every snapshot
    taken in this work tree, root, however old. Linked work trees share the
    git directory, so each snapshot names its own work tree's root.

    A finished compaction retires here: when head, the base commit's tree
    as tree_entries gives it, holds a blob for the file that this snapshot's
    own --verify and --reviewed passed, with both records still standing,
    the compaction is committed as checked, so its snapshot and review file are
    deleted and it gates nothing more. That needs no step after the commit:
    the next prose check, on any later commit, does it."""
    out, here = {}, os.path.realpath(root)
    try:
        entries = list(snapshot_dir(root, None).iterdir())
    except FileNotFoundError:
        return out
    except OSError as error:
        raise ValueError(f"could not read the compaction snapshots: {error}")
    for entry in entries:
        if entry.name.startswith(".") or entry.suffix:
            continue
        # A snapshot that cannot be read may be of a file this commit
        # compacts, so it is an error. One gone since the listing was
        # abandoned or retired, and gates nothing. One that is not JSON of
        # the expected shape is not a snapshot: snapshots are written whole,
        # by rename, so bad JSON is never a half-written one.
        try:
            data = entry.read_bytes()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError(f"could not read the compaction snapshot {entry}: "
                             f"{error.strerror}")
        try:
            fields = json.loads(data.decode("utf-8"))
        except ValueError:
            continue
        if not (isinstance(fields, dict) and isinstance(fields.get("rel"), str)
                and isinstance(fields.get("before"), str)
                and isinstance(fields.get("root"), str)
                and os.path.realpath(fields["root"]) == here):
            continue
        rel, before = fields["rel"], fields["before"]
        held = (head or {}).get(rel)
        # Retired only by a blob this compaction itself checked, as its own
        # snapshot lists, and whose records still stand: a record alone may
        # come from another compaction of the same start.
        def mine(key):
            return held is not None and isinstance(fields.get(key), list) \
                and held[1] in fields[key]
        if held is not None and passes is not None and held[1] != before \
                and mine("verified") and mine("reviewed") \
                and _record(verified_dir(passes), held[1], before) \
                and _record(reviewed_dir(passes), held[1], before):
            try:
                with _snapshot_lock(entry.parent):
                    # Read again under the lock: a new step 1 on the file
                    # may have replaced the snapshot since the read above,
                    # and that new compaction must keep gating.
                    try:
                        again = entry.read_bytes()
                    except FileNotFoundError:
                        again = None
                    if again is not None and again != data:
                        try:
                            newer = json.loads(again.decode("utf-8"))
                        except ValueError:
                            newer = None
                        out.setdefault(rel, set()).add(before)
                        if isinstance(newer, dict) and isinstance(newer.get("before"), str):
                            out[rel].add(newer["before"])
                        continue
                    for path in (entry, entry.with_suffix(".review.md"),
                                 _answers_file(fields)):
                        if path is None:
                            continue
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                    _clear_drafts(entry)
            except OSError as error:
                raise ValueError(f"could not retire the compaction snapshot {entry}: "
                                 f"{error.strerror}")
            continue
        out.setdefault(rel, set()).add(before)
        if answered is not None:
            # The answers this compaction's --verify passed, {blob: answers},
            # which the gate checks its review judged.
            answered[(rel, before)] = fields.get("answers")
    return out


def unverified(root, amend, passes):
    """The refusals for the staged files a compaction was started on, in
    this work tree and not yet retired (see started()), whose staged blob differs
    from the base's (HEAD's, or its parent's with amend) and lacks a record
    of a passing --verify, or of a completed review, from the compaction's
    start. Nothing else is gated, and the gate reads no history: a
    compaction gates its file until it retires or is abandoned. Symlinks,
    mode 120000, hold no prose and are skipped."""
    if root is None:
        return []
    base = "HEAD^" if amend else "HEAD"
    try:
        tree, index = tree_entries(root, base), index_entries(root)
        # Retire against the base, not HEAD: with amend, HEAD is the commit
        # being replaced, so a checked copy there is about to go.
        stored = {}
        begun = started(root, tree, passes, stored)
    except ValueError as error:
        return [f"could not tell which staged files were compacted ({error}); fix that, then "
                f"sign again"]
    out = []
    for path, starts in sorted(begun.items()):
        entries = index.get(path, [])
        if not entries:
            continue
        # The path as typed from here, so the printed command runs where
        # prose check ran; each refusal also names the way out for a
        # compaction that was started and is not going to be finished.
        quoted = command_path(os.path.relpath(os.path.join(os.path.realpath(root), path),
                                              os.path.realpath(os.getcwd())))
        drop = f"; or, to drop this compaction, `prose compact --abandon {quoted}`"
        if len(entries) != 1 or entries[0].stage != "0":
            out.append(f"{path} is unmerged, so whether it was compacted cannot be told; resolve "
                       f"it first{drop}")
            continue
        old = tree.get(path)
        if entries[0].mode not in REGULAR or (old is not None and entries[0].oid == old[1]):
            continue
        oid = entries[0].oid
        if not any(_record(verified_dir(passes), oid, before) for before in starts):
            out.append(f"{path} was compacted but not verified; run "
                       f"`prose compact --verify {quoted}`{drop}")
        if not any(_review_covers(reviewed_dir(passes), oid, before,
                                  _answers_for(stored.get((path, before)), oid))
                   for before in starts):
            out.append(f"{path} was compacted but its review was not completed; run "
                       f"`prose compact --review {quoted}`, answer the reviewer's findings, then "
                       f"`prose compact --reviewed <reply> {quoted}`{drop}")
    return out


def abandon(name, state_home, passes=None):
    """Discard the compaction started on the file: its snapshot, the review
    file beside it, and, inside a repository, the --verify and review
    records made for it, so the commit gate treats the file as ordinary
    again. Raises ValueError when no compaction was started on it. Returns
    VERIFIED, the success exit code."""
    try:
        where = target(name)
    except ValueError:
        # target() refuses a file that is not there. A file deleted from the
        # work tree, its compacted copy still staged, is still gated, so the
        # target is built from the path alone; a file that is there failed
        # target() for another reason, which stands.
        file_path = pathlib.Path(name).absolute()
        file_path = file_path.parent.resolve() / file_path.name
        if file_path.exists():
            raise
        # git runs in the nearest directory that still exists, since the
        # file's own may be gone with it.
        nearest = file_path.parent
        while not nearest.is_dir() and nearest != nearest.parent:
            nearest = nearest.parent
        root = _root_of(nearest / "_")
        if root is None:
            raise
        try:
            rel = str(file_path.relative_to(pathlib.Path(root).resolve()))
        except ValueError:
            raise ValueError(f"{name}: not inside the repository")
        where = Target(file_path, root, rel, name)
    directory = snapshot_dir(where.root, state_home)
    own = _snapshot_path(where, state_home)
    # The snapshot named for this path, and inside a repository any other
    # one this work tree took of the same file. The name comes from the
    # path with symlinks in its directory resolved (realpath), and a
    # directory that is gone cannot be resolved as it was, so a file deleted with its directory may name
    # its snapshot differently; matching the path and the work tree's root
    # finds it anyway.
    # Under the lock, so a step updating the snapshot at the same time
    # cannot write it back after it is deleted.
    with _snapshot_lock(directory):
        found = {}
        try:
            entries = list(directory.iterdir())
        except FileNotFoundError:
            entries = []
        except OSError as error:
            raise ValueError(f"could not read the compaction snapshots: {error}")
        here = os.path.realpath(where.root) if where.root is not None else None
        for entry in entries:
            if entry.name.startswith(".") or entry.suffix:
                continue
            try:
                fields = json.loads(entry.read_bytes().decode("utf-8"))
            except OSError as error:
                raise ValueError(f"could not read the compaction snapshot {entry}: "
                                 f"{error.strerror}")
            except ValueError:
                continue
            if not isinstance(fields, dict):
                continue
            if entry == own or (here is not None and fields.get("rel") == where.rel
                                and isinstance(fields.get("root"), str)
                                and os.path.realpath(fields["root"]) == here):
                found[entry] = fields
        if not found:
            raise ValueError(f"{name}: no compaction was started on it, so there is nothing to "
                             f"abandon")
        for entry in found:
            for path in (entry, entry.with_suffix(".review.md"), _answers_file(found[entry])):
                if path is None:
                    continue
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            _clear_drafts(entry)
        # The records of this file's compaction, matched by its path and the
        # blob it started from. A record is named by its staged blob and holds
        # the path of whichever file wrote it last, so it can serve another
        # file with the same content, or this file in another work tree. The
        # gate reads a record only for a snapshot whose start is the record's
        # `before`, so a record is kept while any surviving snapshot starts
        # from that blob.
        removed = 0
        if where.root is not None and passes is not None:
            starts = {fields.get("before") for fields in found.values()
                      if isinstance(fields.get("before"), str)}
            surviving = set()
            for entry in (directory.iterdir() if directory.exists() else []):
                if entry.name.startswith(".") or entry.suffix:
                    continue
                try:
                    fields = json.loads(entry.read_bytes().decode("utf-8"))
                except (OSError, ValueError):
                    # A snapshot that cannot be read might need any record.
                    surviving = starts
                    break
                if not isinstance(fields, dict):
                    continue
                if not isinstance(fields.get("before"), str):
                    # A snapshot of an unknown shape might need any record.
                    surviving = starts
                    break
                surviving.add(fields["before"])
            starts = starts - surviving
            for records in (verified_dir(passes(where.root)), reviewed_dir(passes(where.root))):
                try:
                    items = list(records.iterdir())
                except FileNotFoundError:
                    continue
                for record in items:
                    try:
                        fields = json.loads(record.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if isinstance(fields, dict) and fields.get("path") == where.rel \
                            and isinstance(fields.get("before"), str) \
                            and fields["before"] in starts:
                        record.unlink()
                        removed += 1
    print(f"Abandoned the compaction of {where.rel}: removed its snapshot"
          + (f" and {removed} record{'' if removed == 1 else 's'}" if removed else "")
          + ". The commit gate treats it as an ordinary file again.")
    return VERIFIED


def changed_paths(root, amend):
    """Every path whose staged entry differs from the base's (HEAD's, or its
    parent's with amend), deletions left out."""
    base = "HEAD^" if amend else "HEAD"
    tree, index = tree_entries(root, base), index_entries(root)
    return sorted(path for path, entries in index.items()
                  if path not in tree or any(entry.oid != tree[path][1] for entry in entries))
