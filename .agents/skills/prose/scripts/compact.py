"""Compaction: rule 8 ("what is, not how it got here") over a whole file.

Two parts, both standard library only:

- `due()`: the cheap triggers `prose check` runs on each changed doc. A doc
  agents read before working is due for compaction when it is over its size
  budget and was never compacted or has grown past its growth share since,
  or when it holds history markers.
- `brief()`, `verify()` and `review()`: `prose compact <file>` prints the
  brief a compactor subagent works from, `--verify` checks the result, and
  `--review` prints the brief for a reviewer of each removal and rewrite.

Read ../DECISIONS.md (*Compaction*) before changing a default here.
"""

import bisect
import collections
import contextlib
import difflib
import hashlib
import json
import os
import pathlib
import re
import shlex
import stat
import subprocess
import time
from typing import NamedTuple, Optional

try:
    import fcntl
except ImportError:  # Windows: the lock does nothing, see _snapshot_lock
    fcntl = None

HERE = pathlib.Path(__file__).resolve().parent
BRIEF = HERE.parent / "compact.md"

# The size above which a doc agents read before working is due for
# compaction, in bytes of the staged file (about 10,000 tokens).
DEFAULT_BUDGET = 40_000
# Once compacted, a doc over budget is due again when it has grown by this
# share, in percent, since its last compaction.
DEFAULT_GROWTH = 50
# A commit that shrinks a file by at least this share, in percent, counts as
# a compaction of it.
COMPACTED_SHARE = 10
# How far back, in commits that changed the file, to look for the last
# compaction.
HISTORY_DEPTH = 500

# The .gitattributes names a repository sets to override the defaults.
ATTR_DECLARE = "prose-compact"
ATTR_BUDGET = "prose-compact-budget"
ATTR_GROWTH = "prose-compact-growth"

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
    budget: int
    growth: int
    binary: bool = False


def _number(value, default):
    return int(value) if value is not None and re.fullmatch(r"[0-9]{1,12}", value) else default


def settings(paths, root):
    """{path: Settings} from the staged .gitattributes, falling back to the
    defaults. `prose-compact` declares a doc current-state, `-prose-compact`
    exempts one, and the two numeric attributes replace the budget and the
    growth share. Outside a repository, or when git fails, every path gets
    the defaults."""
    found = {path: {} for path in paths}
    names = [ATTR_DECLARE, ATTR_BUDGET, ATTR_GROWTH, "diff"]
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
        out[path] = Settings(current, _number(attrs.get(ATTR_BUDGET), DEFAULT_BUDGET),
                             _number(attrs.get(ATTR_GROWTH), DEFAULT_GROWTH),
                             attrs.get("diff") == "unset")
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
    """The text's lines with what is quoted rather than said blanked: fenced
    blocks, inline code, and text in double quotes or guillemets. A doc that
    names a marker, such as this skill's rules, is quoting it."""
    lines = _unfenced_code(text)
    joined = QUOTED.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), "\n".join(lines))
    return joined.split("\n")


def _unfenced_code_kept(text):
    """The text's lines with fenced blocks blanked and inline code kept.
    The history-marker scan reads it through _unfenced_code, which then
    blanks inline code too; gone_terms reads it directly, to find the code
    spans. --verify never uses it: it reads every heading-shaped line, code
    blocks included."""
    out, fence = [], None
    for line in text.split("\n"):
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            out.append("")
            continue
        opening = re.match(r"(`{3,}|~{3,})", stripped)
        if opening:
            fence = opening.group(1)
            out.append("")
            continue
        out.append(line)
    return out


def _unfenced_code(text):
    """The text's lines with fenced blocks and inline code blanked."""
    return [re.sub(r"`[^`]*`", "``", line) for line in _unfenced_code_kept(text)]


def history_markers(text):
    """[Marker] for each line a marker starts on, at most one per line. The
    patterns run over the whole masked text, so a marker that wrapped onto
    the next line is still found."""
    joined = "\n".join(masked_lines(text))
    best = {}  # line: (pattern rank, Marker)
    for rank, (name, pattern) in enumerate(MARKERS):
        for match in pattern.finditer(joined):
            start = match.start()
            if name == "previously" and DETERMINER.search(joined[max(0, start - 40):start]):
                continue
            number = joined.count("\n", 0, start) + 1
            if number in best and best[number][0] <= rank:
                continue
            words = " ".join(match.group(0).split()).strip(" .(*#")
            best[number] = (rank, Marker(number, name, words))
    return [best[number][1] for number in sorted(best)]


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
        result = subprocess.run(["git", "-c", "core.quotePath=false"] + args, cwd=root,
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


def last_compaction(path, root):
    """(commit, size after) for the newest non-merge commit reachable from
    HEAD that shrank path by COMPACTED_SHARE or more, or None. Read from blob
    sizes alone, so it needs no marker in the commit. Commits inside merged
    branches count: a compaction in a pull request that also grew the file
    nets less than a tenth on the merge, but its own commit still shows it."""
    out = _git(["log", "--no-merges", "-n", str(HISTORY_DEPTH), "--format=%x01%h",
                "--raw", "--no-abbrev", "--no-renames", "--", path], root)
    if not out:
        return None
    changes = []
    for chunk in out.split("\x01")[1:]:
        lines = chunk.strip("\n").split("\n")
        for line in lines[1:]:
            raw = re.match(r":\d+ \d+ ([0-9a-f]+) ([0-9a-f]+) M\t", line)
            if raw:
                changes.append((lines[0], raw.group(1), raw.group(2)))
    sizes = _sizes(sorted({blob for _, old, new in changes for blob in (old, new)}), root)
    for commit, old, new in changes:
        if old in sizes and new in sizes and \
                sizes[new] * 100 <= sizes[old] * (100 - COMPACTED_SHARE):
            return commit, sizes[new]
    return None


class Due(NamedTuple):
    path: str
    why: str


def _size_reason(path, size, head_oid, setting, root):
    """Why path is due by size, or None. head_oid is its blob at HEAD, or
    None; its size is read only when the file is over budget, and a size git
    cannot read, as in a partial clone offline, counts as unknown."""
    if size <= setting.budget:
        return None
    try:
        head = _size(head_oid, root) if head_oid else None
    except ValueError:
        head = None
    if head is not None and size * 100 <= head * (100 - COMPACTED_SHARE):
        return None  # this change is itself a compaction
    last = last_compaction(path, root)
    if last is None:
        return f"{size:,} bytes, over its budget of {setting.budget:,} and never compacted"
    commit, after = last
    if after == 0:
        # Emptied by its last compaction: any size over budget has grown
        # past every share.
        return (f"{size:,} bytes, over its budget of {setting.budget:,}; its last compaction "
                f"({commit}) left it empty")
    if size * 100 < after * (100 + setting.growth):
        return None
    grown = (size - after) * 100 // after
    return (f"{size:,} bytes, over its budget of {setting.budget:,} and grown {grown}% since "
            f"its last compaction ({commit}, {after:,} bytes); {setting.growth}% is allowed")


def is_binary(setting, data):
    """True when git treats the file as binary: by its `-diff` or `binary`
    attribute, or by a NUL byte in data, its staged blob."""
    return setting.binary or b"\0" in data


def _marker_reason(markers):
    shown = ", ".join(f"line {m.line} «{m.words}»" for m in markers[:3])
    more = f", and {len(markers) - 3} more" if len(markers) > 3 else ""
    return f"history markers in a current-state doc: {shown}{more}"


def due(paths, root):
    """[Due] for each staged path that is current-state, by default or by
    its declaration in .gitattributes, whatever its type, and due for
    compaction: by size, by history markers, or both. A binary file, by its
    `-diff` attribute or a NUL byte, is skipped. Reads the index, so it
    judges the change about to be committed; sizes and blobs are read by
    the ids `git ls-files -s` and `git ls-tree` list."""
    paths = [path for path in paths if path]
    found = settings(paths, root)
    current = [path for path in paths if found[path].current and not found[path].binary]
    if not current:
        return []
    try:
        index, head = index_entries(root), tree_entries(root, "HEAD")
    except ValueError:
        return []
    out = []
    for path in current:
        entries = index.get(path, [])
        if len(entries) != 1 or entries[0].stage != "0" or entries[0].mode not in REGULAR:
            continue  # deleted, unmerged, or not a file
        try:
            data = _blob(entries[0].oid, root)
        except ValueError:
            continue
        if is_binary(found[path], data):
            continue
        before = head.get(path)
        reasons = []
        size_reason = _size_reason(path, len(data), before[1] if before else None, found[path],
                                   root)
        if size_reason:
            reasons.append(size_reason)
        markers = history_markers(_lf(data.decode("utf-8", "surrogateescape")))
        if markers:
            reasons.append(_marker_reason(markers))
        if reasons:
            out.append(Due(path, "; ".join(reasons)))
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
# so its text is not searched. Its anchor still is.
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


def normalised(lines):
    """(text, starts) for [(line number, line)]: the lines normalised and
    joined by single spaces, so a phrase wrapped across lines reads as one,
    and [(offset in text, line number)] where each non-empty line begins.
    A bare CR, which git and the line split leave inside a line, is a line
    break here too, so the markers after it are dropped; each part keeps
    the number of the line it came from."""
    pieces, starts, offset = [], [], 0
    for number, line in lines:
        for part in line.split("\r"):
            piece = normalise_line(part)
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


def _find(source, lines, tags, texts):
    """[Reference] in one file's [(line number, line)]: each line holding one
    of tags, the `#anchor` strings, as written, and each place its normalised
    text holds one of texts
    ({normalised text: heading}), at the line the match starts on."""
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


def references(path, headings, wanted, text, root, referrers=None):
    """[Reference] for each place that names one of the headings (at least
    MIN_HEADING characters once normalised) in another file, or one of the
    anchors in wanted as `#anchor` in another file or in text, the file's
    own current text. The other files are the repository's tracked files,
    in the work tree and the index (none when root is None), and the
    referrers given."""
    texts = {}
    for heading in sorted(set(headings)):
        needle = normalised([(0, heading)])[0]
        if len(needle) >= MIN_HEADING:
            texts.setdefault(needle, heading)
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
                    keep(_find(source, lines, tags, texts))
    if referrers is not None:
        for name, file_path in referrers.files:
            keep(_find(name, _read_lines(name, file_path), tags, texts))
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


def _snapshot_path(where, state_home):
    key = hashlib.sha256(str(where.file).encode("utf-8", "surrogateescape")).hexdigest()[:24]
    return snapshot_dir(where.root, state_home) / key


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
    found = references(where.rel, heading_texts(text), anchors(text), "", where.root, referrers)
    snapshot = _snapshot_path(where, state_home)
    fields = {"path": str(where.file), "rel": where.rel, "root": where.root, "text": text,
              "saved": now}
    if start is not None:
        fields["before"] = start.oid
    with _snapshot_lock(snapshot.parent):
        _clear_drafts(snapshot)
        _write_snapshot(snapshot, fields)

    markers = history_markers(text)
    held = {}
    for ref in found:
        held.setdefault(ref.needle, []).append(ref.source)
    print("=== compaction brief ===")
    print(BRIEF.read_text(encoding="utf-8").rstrip("\n"))
    print(f"\nThe file: {where.file}")
    print(f"Size: {len(text.encode('utf-8')):,} bytes, {len(text.split()):,} words.")
    if markers:
        print(f"\nHistory markers the script found ({len(markers)}); there may be others:")
        for marker in markers[:40]:
            print(f"  line {marker.line}: «{marker.words}»")
    if held:
        print("\nHeadings other files name or link to, by their text or their `#anchor`. Keep "
              "each, with its exact text:")
        for needle, files in sorted(held.items()):
            print(f"  {needle}  (in {', '.join(sorted(set(files))[:3])})")
    print("=== end compaction brief ===")
    again = given.options()
    if given.paths_from == "-":
        again += "   (with the same list on stdin)"
    stage = f"git add {command_path(name)}\n  " if where.root is not None else ""
    print(f"\nGive a new subagent the brief above, exactly as printed. Then, as the required "
          f"last step, run:\n\n  {stage}{command} compact {command_path(name)} --verify{again}")
    if where.root is None and referrers is None:
        print("\nThe file is outside any git repository, so --verify checks only its own links "
              "unless you give it the files that might refer to it, after `--` or with "
              "--paths-from (SKILL.md, *Compaction*).")
    return BRIEF_PRINTED


class Report(NamedTuple):
    lines: list
    failures: list


def check_result(before, after, rel, root, budget=DEFAULT_BUDGET, referrers=None):
    """The verification report for a file compacted from before to after.
    Failures are what the result must fix. The other lines inform whoever
    checks the result for a lost conclusion: the reviewer, or a person."""
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
    elif share < COMPACTED_SHARE and size_after > budget:
        lines.append(f"It shrank by less than {COMPACTED_SHARE}% and is still over its budget of "
                     f"{budget:,} bytes, so the size trigger will fire again on its next change. "
                     f"If it is meant to be this long, give it its own budget in .gitattributes, "
                     f"such as '{rel} {ATTR_BUDGET}={size_after * 3 // 2}'.")

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
    found = references(rel, gone, removed, after, root, referrers)
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
    for marker in history_markers(after):
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


# A fence opens a line, after any list marker: "- ```yaml" opens one too.
FENCE = re.compile(r"(?:(?:[-*+]|[0-9]{1,9}[.)])[ \t]+)?(`{3,}|~{3,})")


def _paragraphs(text):
    """(paragraphs, the heading above each): the text split at blank lines,
    except blank lines inside fenced blocks, fenced blocks inside block quotes
    included."""
    paragraphs, headings, current, heading, fence = [], [], [], "", None
    for line in text.split("\n"):
        stripped = _unquoted(line).lstrip()
        if fence and stripped.startswith(fence):
            fence = None
        elif not fence and FENCE.match(stripped):
            fence = FENCE.match(stripped).group(1)
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
              "printed": time.time()}

    def change(fields):
        draft.write_text("\n".join(parts), encoding="utf-8")
        os.replace(draft, path)
        fields["review"] = review

    if not _update_snapshot(where, state_home, saved, change):
        raise ValueError(f"the snapshot of {name} changed while --review ran; run it again")
    print("=== compaction review brief ===")
    print(REVIEW_BRIEF.read_text(encoding="utf-8").rstrip("\n"))
    print(f"\nThe changes: {path}")
    print(f"The compacted file: {where.file}")
    print(f"The repository: {where.root}" if where.root else
          "The repository: none, since the file is outside one. Check claims against the old "
          "text only.")
    print(f"Changes: {len(found)}. Names gone: {len(dropped)}.")
    print("=== end compaction review brief ===")
    print("\nGive a new subagent the brief above, exactly as printed, on the same model as the "
          "compactor. Save its reply to a file; when its findings are answered, run:\n\n"
          f"  {command} compact {command_path(name)} --reviewed <reply file> "
          "[--dispositions <file>]")
    return BRIEF_PRINTED


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


def _note_in_snapshot(where, state_home, saved, key, oid, passed):
    """Add oid to, or with passed False remove it from, the snapshot's list
    under key ("verified" or "reviewed"). The lists say which blobs this
    compaction itself checked, which is what retires it (in started()): records
    are shared by every compaction that reaches the same content, the lists
    are not. A list of another shape counts as empty."""
    def change(current):
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


def verify(name, state_home, passes=None, given=Given(), stdin=None):
    """Check the compacted file against its snapshot; print the report.
    Returns VERIFIED or FAILED. Inside a repository, passes(root) is prose's
    pass directory, where a pass is recorded for the commit gate."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    referrers = _referrers(given, where, stdin)
    # Inside a repository the staged blob is checked, and the record is
    # named by its id as `git ls-files -s` lists it, which the gate reads.
    current = staged(where, "--verify") if where.root is not None else None
    after = current.text if current else _lf(where.file.read_text(encoding="utf-8"))
    budget = settings([where.rel], where.root)[where.rel].budget
    report = check_result(_lf(saved["text"]), after, where.rel, where.root, budget, referrers)
    print(f"prose compact: {where.rel}")
    for line in report.lines:
        print(line)
    record = None
    if current is not None and passes is not None:
        record = verified_dir(passes(where.root)) / current.oid
    if report.failures:
        if record is not None:
            try:
                record.unlink()
            except FileNotFoundError:
                pass
            _note_in_snapshot(where, state_home, saved, "verified", current.oid, False)
        print(f"\nFailed ({len(report.failures)}):")
        for failure in report.failures:
            print(f"  {failure}")
        print("\nFix these in the file, then run --verify again.")
        return FAILED
    if record is not None:
        _write_record(record, {"path": where.rel, "verified": time.time(),
                               "before": saved.get("before")})
        if not _note_in_snapshot(where, state_home, saved, "verified", current.oid, True):
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
ANSWER = re.compile(r"Change (\d+): (?:(fixed)|kept: (\S.*))")


def _lines(path, what):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{path}: could not read the {what}: {error}")


def reviewed(name, state_home, passes, reply, dispositions=""):
    """Check that the last review's reply answers every change, and that
    each `lost` or `false` finding has an answer: fixed, in a file that has
    changed since the review, or kept with a reason. Inside a repository,
    record the completed review for the staged blob. Returns VERIFIED."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    review_of = saved.get("review")
    if not isinstance(review_of, dict) or not isinstance(review_of.get("changes"), int):
        raise ValueError(f"no review of this compaction of {name}: run "
                         f"'compact {command_path(name)} --review' "
                         f"and give a reviewer its brief first")
    current = staged(where, "--reviewed") if where.root is not None else None
    verdicts, totals = {}, []
    findings = {}
    for line in _lines(reply, "reviewer's reply"):
        line = line.strip()
        if TOTALS.fullmatch(line):
            totals.append(tuple(map(int, TOTALS.fullmatch(line).groups())))
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
    counted = (sum(v.count("lost") for v in findings.values()),
               sum(v.count("false") for v in findings.values()))
    if totals != [counted]:
        raise ValueError(f"{reply}: needs one line 'Totals: {counted[0]} lost, {counted[1]} "
                         f"false', matching its verdicts")
    answers = {}
    if findings:
        if not dispositions:
            raise ValueError(f"the review found {counted[0]} lost and {counted[1]} false, in "
                             f"change{'s' if len(findings) > 1 else ''} "
                             f"{', '.join(map(str, sorted(findings)))}: answer each in a file of "
                             f"'Change <n>: fixed' or 'Change <n>: kept: <reason>' lines and "
                             f"pass it with --dispositions")
        for line in _lines(dispositions, "dispositions"):
            line = line.strip()
            if not line:
                continue
            match = ANSWER.fullmatch(line)
            if not match:
                raise ValueError(f"{dispositions}: not 'Change <n>: fixed' or 'Change <n>: kept: "
                                 f"<reason>': {line!r}")
            number = int(match.group(1))
            if number not in findings or number in answers:
                raise ValueError(f"{dispositions}: change {number} "
                                 + ("is answered twice" if number in answers else
                                    "has no lost or false finding to answer"))
            answers[number] = "fixed" if match.group(2) else "kept"
        unanswered = sorted(set(findings) - set(answers))
        if unanswered:
            raise ValueError(f"{dispositions}: no answer for change"
                             f"{'s' if len(unanswered) > 1 else ''} "
                             f"{', '.join(map(str, unanswered))}")
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
                       "false": counted[1]})
        if not _note_in_snapshot(where, state_home, saved, "reviewed", current.oid, True):
            raise ValueError(f"the snapshot of {name} changed while --reviewed ran, by a new "
                             f"step 1 or --abandon; if a compaction is still started, run "
                             f"--review and --reviewed again on it")
    print(f"Review of {where.rel} complete: {counted[0]} lost, {counted[1]} false, "
          f"{sum(a == 'fixed' for a in answers.values())} fixed, "
          f"{sum(a == 'kept' for a in answers.values())} kept.")
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


def _size(oid, root):
    out = _git(["cat-file", "-s", oid], root)
    if out is None or not out.strip().isdigit():
        raise ValueError(f"git could not read the size of blob {oid}")
    return int(out.strip())


def started(root, head=None, passes=None):
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
                    for path in (entry, entry.with_suffix(".review.md")):
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
        begun = started(root, tree, passes)
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
        if not any(_record(reviewed_dir(passes), oid, before) for before in starts):
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
            for path in (entry, entry.with_suffix(".review.md")):
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
