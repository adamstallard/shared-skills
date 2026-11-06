"""Reading cost: the text agents load before they work, measured.

Two parts, standard library only, with no git and no file access, so
compact.py and prose.py feed them what they read:

- `conditional_sections()`: the sections of a doc that a condition heads or
  introduces, such as "When the caller commits" or "If you are a subagent",
  large enough that moving one to a linked file would cut what every reader
  loads. A person decides each move; nothing here moves text.
- `skill_description()`: the `description:` of a SKILL.md's front matter,
  which a host loads in every session for every installed skill.

Read ../DECISIONS.md (*Compaction aims at reading cost*) before changing a
pattern or a limit here.
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Sequence

# A section smaller than this is not proposed for a move. The line that
# replaces it costs about 200 bytes, so a move of 1,000 bytes saves at
# least 800 bytes, about 200 tokens, on each read.
MOVE_MIN_BYTES = 1_000

# The Agent Skills specification, and Anthropic's API for uploaded skills,
# allow at most this many characters in a skill's description.
DESCRIPTION_LIMIT = 1_024

# The same lines as compact.HEADING, with the hashes captured for the level.
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
ITEM = re.compile(r"^([ \t]*)(?:[-*+]|[0-9]{1,9}[.)])[ \t]+")
LEAD_IN = re.compile(r"^[ \t]*(?:(?:[-*+]|[0-9]{1,9}[.)])[ \t]+)?(\*\*|__)(.+?)\1")

# What opens a section that only some readers need. Each alternative names
# a situation a reader can be in or not: a condition ("When", "If",
# "Unless", "Without"), another skill installed, a caller, setup and
# installation, trouble, an upgrade or migration, an operating system.
# "Before", "After", "Once" and "While" are left out: in a skill they order
# the steps every reader runs ("Before a commit", "After the last fix").
CONDITION = re.compile(
    r"(?:when(?:ever)?|if|unless|only (?:when|if)|without|in case)\b"
    r"|with\b[^.\n]{0,60}?\b(?:installed|enabled|configured)\b"
    r"|called (?:by|from)\b"
    r"|(?:first[- ]time )?set(?:ting)?[- ]?up\b"
    r"|(?:un)?install(?:ing|ation)?\b"
    r"|troubleshoot(?:ing)?\b"
    r"|upgrad(?:e|es|ing)\b"
    r"|migrat(?:e|es|ing|ion)\b"
    r"|on (?:windows|macos|linux)\b",
    re.I)
# Openings that look like a condition but hold for every reader: a heading
# that names the skill's trigger ("When", "When to use one") must be read to
# know whether the skill applies, and every reader of a skill is an agent.
NOT_CONDITION = re.compile(
    r"when[ \t]*[.:]?[ \t]*$|when to\b|if you(?:'re| are) an? (?:agent|assistant|ai|model)\b",
    re.I)
# Emphasis, quote marks and brackets before the first word. A backtick is
# not dropped: a section that opens on a code name ("`uninstall` removes")
# names a command, not a condition.
MARKUP = re.compile(r"^[\s*_>\"'«“(\[-]+")


class Candidate(NamedTuple):
    """A section that could move to a linked file."""
    start: int    # first line, from 1
    end: int      # last line
    kind: str     # "heading", "first sentence" or "lead-in": what states the condition
    title: str    # the section's heading, or the lead-in's bold words
    condition: str  # the words that state the condition, as the doc has them
    size: int     # bytes, UTF-8


def is_condition(text: str) -> bool:
    """True when text opens with a condition only some readers meet."""
    plain = MARKUP.sub("", text)
    return bool(CONDITION.match(plain)) and not NOT_CONDITION.match(plain)


def _size(lines: Sequence[str], start: int, end: int) -> int:
    """The bytes of lines[start:end], each with its line break."""
    return sum(len(line.encode("utf-8", "surrogateescape")) + 1 for line in lines[start:end])


def _trim(lines: Sequence[str], start: int, end: int) -> int:
    """end, moved back over blank lines, but never before start + 1."""
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _first_sentence(lines: Sequence[str], code: Sequence[bool], start: int, end: int) -> str:
    """The first paragraph's first line in lines[start:end], or "" when the
    first thing there is code, a list, a table, a quote, a heading or a
    lead-in: only a plain paragraph introduces a section, and a lead-in is
    read as one of its own."""
    for number in range(start, end):
        line = lines[number]
        if code[number]:
            return ""
        if not line.strip():
            continue
        stripped = line.lstrip()
        if HEADING.match(line) or ITEM.match(line) or LEAD_IN.match(line) \
                or stripped[:1] in ("|", ">"):
            return ""
        return stripped
    return ""


def _opens_block(lines: Sequence[str], code: Sequence[bool], number: int) -> bool:
    """True when lines[number] starts a block: it is the first line, or the
    line before it is blank, a heading or code, each of which ends a block."""
    if number == 0:
        return True
    before = lines[number - 1]
    return not before.strip() or code[number - 1] or bool(HEADING.match(before))


def _lead_in_end(lines: Sequence[str], code: Sequence[bool], start: int) -> int:
    """Where a lead-in starting at lines[start] ends: a paragraph's lead-in
    takes the lists, tables and code that follow it, up to the next plain
    paragraph at its own indent or a line that leaves its list item; a list
    item's takes its own continuation lines. A heading ends either."""
    item = ITEM.match(lines[start])
    own = _indent(lines[start])
    number = start + 1
    # The lead-in's own block runs to its first blank line.
    while number < len(lines) and lines[number].strip() and not code[number] \
            and not HEADING.match(lines[number]) and not ITEM.match(lines[number]):
        number += 1
    while number < len(lines):
        line = lines[number]
        if code[number] or not line.strip():
            number += 1
            continue
        if HEADING.match(line):
            break
        # A line straight after text continues that text's block, as a
        # list item's lazy continuation does, so the extent never ends there.
        if lines[number - 1].strip() and not code[number - 1] and not ITEM.match(line):
            number += 1
            continue
        indent = _indent(line)
        if item:
            if indent <= own:
                break
        elif indent < own or (indent == own and not ITEM.match(line)
                              and line.lstrip()[:1] not in ("|", ">")):
            break
        number += 1
    return _trim(lines, start, number)


def conditional_sections(text: str, code: Sequence[bool],
                         minimum: int = MOVE_MIN_BYTES) -> List[Candidate]:
    """[Candidate] for each section of text that a condition heads or
    introduces and that holds at least minimum bytes, in order. code[n] is
    True when line n (from 0) is fenced code or front matter, as compact.py's
    shared fence rule reads it. Three shapes count:

    - a heading that states a condition ("## When the caller commits");
    - a heading whose section opens with a paragraph that does ("## Modes",
      then "When the user asks ...");
    - a paragraph or list item that opens with bold words that do
      ("**Called by another skill.** ..."), with what hangs off it.

    A heading's section runs to the next heading of the same level or above.
    The doc's title, a level-1 heading before any other, is never a section.
    A candidate that shares a line with an earlier, wider one is dropped, so
    each line is proposed once."""
    lines = text.split("\n")
    if len(code) < len(lines):
        raise ValueError("code must mark every line of text")
    headings = [(number, len(match.group(1)), match.group(2))
                for number, line in enumerate(lines)
                if not code[number] and (match := HEADING.match(line))]
    found: List[Candidate] = []
    for index, (number, level, title) in enumerate(headings):
        if index == 0 and level == 1:
            continue
        end = next((later for later, deeper, _ in headings[index + 1:] if deeper <= level),
                   len(lines))
        end = _trim(lines, number, end)
        below = next((later for later, _, _ in headings[index + 1:]), end)
        if NOT_CONDITION.match(MARKUP.sub("", title)):
            continue  # every reader meets it, so its opening is no condition either
        if is_condition(title):
            found.append(Candidate(number + 1, end, "heading", title, title,
                                   _size(lines, number, end)))
            continue
        first = _first_sentence(lines, code, number + 1, min(below, end))
        if first and is_condition(first):
            found.append(Candidate(number + 1, end, "first sentence", title, first,
                                   _size(lines, number, end)))
    for number, line in enumerate(lines):
        if code[number]:
            continue
        match = LEAD_IN.match(line)
        if match is None or not is_condition(match.group(2)):
            continue
        if not ITEM.match(line) and not _opens_block(lines, code, number):
            continue
        end = _lead_in_end(lines, code, number)
        found.append(Candidate(number + 1, end, "lead-in", match.group(2).strip(),
                               match.group(2).strip(), _size(lines, number, end)))
    # The widest candidate at each start comes first, and any candidate that
    # shares a line with one already kept is dropped: each line is proposed
    # once, whatever the extents guessed above.
    found.sort(key=lambda candidate: (candidate.start, -candidate.end))
    kept: List[Candidate] = []
    for candidate in found:
        if kept and candidate.start <= kept[-1].end:
            continue
        kept.append(candidate)
    return [candidate for candidate in kept if candidate.size >= minimum]


# ---------------------------------------------------------------------------
# Skill descriptions
# ---------------------------------------------------------------------------

KEY = re.compile(r"^description[ \t]*:(.*)$")
# A block scalar's header: its style, then its chomping and indentation
# indicators in either order.
BLOCK = re.compile(r"[ \t]*([|>])(?:[+-]?([1-9])?|([1-9])[+-])[ \t]*(?:#.*)?$")


def front_matter(text: str) -> Optional[List[str]]:
    """The lines between a first line of `---` and the next `---`, or None
    when text has no front matter."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[:1] != ["---"]:
        return None
    for number in range(1, len(lines)):
        if lines[number].rstrip() == "---":
            return lines[1:number]
    return None


def _fold(lines: Sequence[str]) -> str:
    """Lines joined as YAML folds them: a line break between two lines
    becomes a space, and each blank line a line break."""
    out = ""
    for line in lines:
        if not line:
            out += "\n"
        elif out and not out.endswith("\n"):
            out += " " + line
        else:
            out += line
    return out


ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
           "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
           "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029"}
HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}


def _quoted(raw: str) -> str:
    """The text of the quoted YAML scalar that raw starts with, raw holding
    its continuation lines. A line break folds as in a plain scalar: to a
    space, or to one line break per blank line, the spaces around it
    dropped. Double quotes take backslash escapes, and a backslash ending a
    line joins it to the next with nothing between; single quotes double
    themselves."""
    mark, body = raw[0], raw[1:]
    out, number = "", 0
    while number < len(body):
        char = body[number]
        if char == mark:
            if mark == "'" and body[number + 1:number + 2] == "'":
                out += "'"
                number += 2
                continue
            break
        if char == "\n":
            out = out.rstrip(" \t")
            blanks = 0
            number += 1
            while number < len(body) and body[number] in " \t\n":
                blanks += body[number] == "\n"
                number += 1
            out += "\n" * blanks if blanks else " "
            continue
        if char == "\\" and mark == '"' and number + 1 < len(body):
            escaped = body[number + 1]
            number += 2
            if escaped == "\n":
                while number < len(body) and body[number] in " \t":
                    number += 1
            elif escaped in HEX_ESCAPES:
                digits = body[number:number + HEX_ESCAPES[escaped]]
                try:
                    out += chr(int(digits, 16))
                except ValueError:
                    out += "\\" + escaped
                    continue
                number += len(digits)
            else:
                out += ESCAPES.get(escaped, "\\" + escaped)
            continue
        out += char
        number += 1
    return out


def skill_description(text: str) -> Optional[str]:
    """The `description:` value of text's front matter, as a YAML reader
    would load it, without trailing line breaks; None when there is none.
    Reads the shapes skills use: a plain or quoted value on the key's line
    and the indented lines after it, and a `>` or `|` block."""
    lines = front_matter(text)
    if lines is None:
        return None
    for number, line in enumerate(lines):
        match = KEY.match(line)
        if match is None:
            continue
        rest = match.group(1)
        more: List[str] = []
        # The value's lines are indented; any line at the left margin, the
        # next key, a comment or a `...`, ends it. Comment lines before the
        # value's first line are skipped, even at the left margin: they are
        # not part of the value.
        started = bool(rest.strip()) and not rest.strip().startswith("#")
        for later in lines[number + 1:]:
            if not started and later.lstrip().startswith("#"):
                continue
            if later.strip() and later[:1] not in (" ", "\t"):
                break
            started = started or bool(later.strip())
            more.append(later)
        while more and not more[-1].strip():
            more.pop()
        block = BLOCK.fullmatch(rest)
        if block:
            body = list(more)
            given = block.group(2) or block.group(3)
            indent = int(given) if given else min(
                (len(later) - len(later.lstrip(" ")) for later in body if later.strip()),
                default=0)
            body = [later[indent:] if later.strip() else "" for later in body]
            joined = "\n".join(body) if block.group(1) == "|" else _fold(body)
            return joined.rstrip("\n")
        # A value may start on the line after the key, after blank lines and
        # comments, which hold none of it.
        if rest.strip().startswith("#"):
            rest = ""
        while not rest.strip() and more:
            rest = more.pop(0)
            if rest.strip().startswith("#"):
                rest = ""
        if not rest.strip():
            return None  # `description:` alone is null
        if rest.strip()[:1] in ("'", '"'):
            return _quoted("\n".join([rest.strip()] + more)).rstrip("\n")
        value = _fold([rest.strip()] + [later.strip() for later in more])
        # A plain scalar ends at a comment.
        return re.sub(r"[ \t]+#.*$", "", value).rstrip("\n")
    return None


class Description(NamedTuple):
    path: str
    size: int        # bytes, UTF-8
    characters: int
    text: str


def measure(path: str, description: str) -> Description:
    """The Description of the skill at path: its text, bytes and characters."""
    return Description(path, len(description.encode("utf-8", "surrogateescape")),
                       len(description), description)


def over_limit(description: Description) -> bool:
    return description.characters > DESCRIPTION_LIMIT
