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

import difflib
import hashlib
import html
import json
import os
import pathlib
import re
import shlex
import subprocess
import time
import urllib.parse
from typing import NamedTuple, Optional

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

# How long a snapshot from `prose compact <file>` waits for `--verify`.
SNAPSHOT_LIFETIME = 7 * 24 * 60 * 60

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


def _number(value, default):
    return int(value) if value is not None and re.fullmatch(r"[0-9]{1,12}", value) else default


def settings(paths, root):
    """{path: Settings} from the staged .gitattributes, falling back to the
    defaults. `prose-compact` declares a doc current-state, `-prose-compact`
    exempts one, and the two numeric attributes replace the budget and the
    growth share. Outside a repository, or when git fails, every path gets
    the defaults."""
    found = {path: {} for path in paths}
    names = [ATTR_DECLARE, ATTR_BUDGET, ATTR_GROWTH]
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
        out[path] = Settings(current, _number(attrs.get(ATTR_BUDGET), DEFAULT_BUDGET),
                             _number(attrs.get(ATTR_GROWTH), DEFAULT_GROWTH))
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
    """The text's lines with fenced blocks blanked and inline code kept."""
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


def _code_blanked(text):
    """The text with fenced blocks and inline code replaced by spaces, every
    offset kept, so a link shown as an example is not read as one."""
    lines = text.split("\n")
    kept = _unfenced_code_kept(text)
    blanked = "\n".join(re.sub(r"[^\n]", " ", line) if new != line else line
                        for line, new in zip(lines, kept))
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), blanked)


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

def _git(args, root, stdin=None):
    """git's stdout, or None when it fails."""
    try:
        result = subprocess.run(["git", "-c", "core.quotePath=false"] + args, cwd=root,
                                input=stdin, capture_output=True, check=False)
    except OSError:
        return None
    return result.stdout.decode("utf-8", "surrogateescape") if result.returncode == 0 else None


def _sizes(objects, root):
    """{object name: size in bytes} for blobs and `<rev>:<path>` names."""
    if not objects:
        return {}
    out = _git(["cat-file", "--batch-check=%(objectsize)"], root,
               ("\n".join(objects) + "\n").encode("utf-8", "surrogateescape"))
    if out is None:
        return {}
    sizes = {}
    for name, line in zip(objects, out.split("\n")):
        if re.fullmatch(r"[0-9]+", line):
            sizes[name] = int(line)
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


def _size_reason(path, size, setting, root):
    """Why path is due by size, or None."""
    if size <= setting.budget:
        return None
    head = _sizes([f"HEAD:{path}"], root).get(f"HEAD:{path}")
    if head is not None and size * 100 <= head * (100 - COMPACTED_SHARE):
        return None  # this change is itself a compaction
    last = last_compaction(path, root)
    if last is None:
        return f"{size:,} bytes, over its budget of {setting.budget:,} and never compacted"
    commit, after = last
    if size * 100 < after * (100 + setting.growth):
        return None
    grown = (size - after) * 100 // after
    return (f"{size:,} bytes, over its budget of {setting.budget:,} and grown {grown}% since "
            f"its last compaction ({commit}, {after:,} bytes); {setting.growth}% is allowed")


def _marker_reason(markers):
    shown = ", ".join(f"line {m.line} «{m.words}»" for m in markers[:3])
    more = f", and {len(markers) - 3} more" if len(markers) > 3 else ""
    return f"history markers in a current-state doc: {shown}{more}"


def due(paths, root):
    """[Due] for each staged path that is a current-state doc due for
    compaction: by size, by history markers, or both. Reads the index, so
    it judges the change about to be committed."""
    paths = [path for path in paths if path]
    found = settings(paths, root)
    current = [path for path in paths if found[path].current]
    sizes = _sizes([f":{path}" for path in current], root)
    out = []
    for path in current:
        size = sizes.get(f":{path}")
        if size is None:
            continue  # deleted, or not a blob
        reasons = []
        size_reason = _size_reason(path, size, found[path], root)
        if size_reason:
            reasons.append(size_reason)
        text = _git(["cat-file", "blob", f":{path}"], root)
        markers = history_markers(text) if text is not None else []
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
# Headings and links
# ---------------------------------------------------------------------------

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
# An inline link's target, or a reference definition's, either of which may
# be wrapped in <>, and then may hold spaces.
LINK = re.compile(r"\]\(\s*(?:<([^>\n]*)>|([^)\s>]*))(?:\s+\"[^\"]*\")?\s*\)"
                  r"|^\s*\[[^\]]+\]:\s*(?:<([^>\n]*)>|(\S+))(?:\s|$)", re.M)


def link_target(match):
    """A LINK match's target, percent-decoded as GitHub decodes it."""
    return urllib.parse.unquote(next((group for group in match.groups() if group), ""))


# SETEXT matches a setext heading's underline. NOT_SETEXT_TEXT matches a
# line that cannot start the text above an underline: a list item,
# quotation, table row, HTML or indented code.
SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
NOT_SETEXT_TEXT = re.compile(
    r"^(?: {4}|\t)|^\s*(?:[-+*>|<]|[0-9]+[.)])(?:\s|$)|^ {0,3}<[A-Za-z/!?]")


def _plain_heading(raw):
    """A heading's text as GitHub renders it: inline and reference links
    reduced to their text, backticks and emphasis markers removed, and HTML
    entities decoded. An underscore or asterisk with no partner, as in
    MAX_SIZE, PROSE_* or "use _ as", is text, and GitHub keeps an underscore
    in the anchor."""
    parts = re.split(r"(`[^`]*`)", raw)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])", r"\1", parts[index])
    parts = re.split(r"(`[^`]*`)", _emphasis_removed("".join(parts)))
    for index in range(0, len(parts), 2):
        parts[index] = html.unescape(parts[index])
    for index in range(1, len(parts), 2):
        parts[index] = parts[index][1:-1]
    return "".join(parts).strip()


def _emphasis_removed(text):
    """text without the * and _ runs that open or close emphasis, each paired
    with a partner as CommonMark pairs them, simplified: a run opens when
    text follows it and closes when text precedes it, and an underscore run
    neither opens nor closes inside a word. Code spans are left alone."""
    masked = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), text)
    drop = set()
    for char in "*_":
        stack = []
        for match in re.finditer(re.escape(char) + "+", masked):
            before = masked[match.start() - 1] if match.start() else " "
            after = masked[match.end()] if match.end() < len(masked) else " "
            opens, closes = not after.isspace(), not before.isspace()
            if char == "_":
                opens, closes = opens and not before.isalnum(), closes and not after.isalnum()
            if closes and stack:
                drop.update(range(*stack.pop()))
                drop.update(range(*match.span()))
            elif opens:
                stack.append(match.span())
    return "".join(c for index, c in enumerate(text) if index not in drop)


def _without_front_matter(lines):
    """The lines with a leading YAML front matter block blanked, so its
    closing --- is not read as a setext underline."""
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                return [""] * (index + 1) + lines[index + 1:]
    return lines


def heading_texts(text):
    """The text of each heading, ATX or setext, outside fenced blocks,
    without its Markdown. A setext heading is the whole paragraph above its
    underline, unless the paragraph is a list item, quotation, table, HTML
    block or indented code."""
    out, fence, paragraph = [], None, []
    for line in _without_front_matter(text.split("\n")):
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            continue
        opening = re.match(r"(`{3,}|~{3,})", stripped)
        if opening:
            fence = opening.group(1)
            paragraph = []
            continue
        match = HEADING.match(line)
        if match:
            out.append(_plain_heading(match.group(2)))
            paragraph = []
            continue
        if SETEXT.match(line):
            if paragraph and _setext_text(paragraph):
                out.append(_plain_heading(" ".join(part.strip() for part in paragraph)))
            paragraph = []
            continue
        paragraph = paragraph + [line] if line.strip() else []
    return out


def _setext_text(paragraph):
    """True when a setext underline below these lines makes them a heading."""
    return not NOT_SETEXT_TEXT.match(paragraph[0]) and not SETEXT.match(paragraph[0])


def slug(heading):
    """GitHub's anchor for a heading's text, before duplicates are numbered."""
    lowered = heading.lower()
    return re.sub(r" ", "-", re.sub(r"[^\w\- ]", "", lowered))


def anchors(text):
    """Every anchor the file's headings give, duplicates numbered as GitHub
    numbers them."""
    seen, out = {}, set()
    for heading in heading_texts(text):
        base = slug(heading)
        count = seen.get(base, 0)
        out.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return out


class Link(NamedTuple):
    source: str
    anchor: str


MARKDOWN_SUFFIXES = (".md", ".mdx", ".markdown")


def _cited_file(source, cited, root):
    """The repository path a bare `<path>#anchor` in source names: the cited
    path taken from source's directory, then from each parent up to the
    root, the first that exists. None when none does."""
    directory = pathlib.PurePosixPath(source).parent
    while True:
        resolved = os.path.normpath(os.path.join(str(directory), cited)).replace(os.sep, "/")
        if not resolved.startswith("../") and resolved != ".." and \
                (pathlib.Path(root) / resolved).is_file():
            return resolved
        if str(directory) in ("", "."):
            return None
        directory = directory.parent


def links_into(path, root):
    """[Link] for each link to a heading of path in the repository's tracked
    text files, the file's own `#anchor` links included. In Markdown, a
    link's target resolves from the linking file's directory, or from the
    repository root when it starts with /, as GitHub resolves it. Anywhere
    else, such as a code comment, a bare `<path>#anchor` resolves from the
    citing file's directory or the nearest parent where the path exists."""
    name = pathlib.PurePosixPath(path).name
    # Needles for the files worth reading. A name with a space is often
    # percent-encoded in a link. A reference definition to one of the file's
    # own headings, such as "[x]: #anchor", holds no "](#", so it has needles
    # of its own.
    needles = {f"{name}#", f"{urllib.parse.quote(name)}#", "](#", "]: #", "]: <#"}
    listed = _git(["grep", "-I", "-l", "-z", "-F"]
                  + [arg for needle in sorted(needles) for arg in ("-e", needle)], root)
    if listed is None:
        return []
    found = []
    for source in filter(None, listed.split("\0")):
        try:
            text = (pathlib.Path(root) / source).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.extend(links_in(source, text, path, root))
    return found


def links_in(source, text, path, root):
    """[Link] for each link in source, whose text is given, to a heading of
    path, resolved as links_into resolves them."""
    rel = pathlib.PurePosixPath(path)
    bare = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*" + re.escape(rel.name) + r")#([\w-]+)")
    found, spans = [], []
    if source.lower().endswith(MARKDOWN_SUFFIXES):
        # Inline code and fenced blocks in Markdown show a path or link
        # as an example; they link nowhere.
        text = _code_blanked(text)
        for match in LINK.finditer(text):
            spans.append(match.span())
            target = link_target(match)
            if "#" not in target or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            file_part, anchor = target.split("#", 1)
            if not file_part:
                resolved = source
            elif file_part.startswith("/"):
                # GitHub resolves a leading / from the repository root.
                resolved = os.path.normpath(file_part.lstrip("/")).replace(os.sep, "/")
            else:
                resolved = os.path.normpath(os.path.join(
                    str(pathlib.PurePosixPath(source).parent), file_part)).replace(os.sep, "/")
            if resolved == str(rel) and anchor:
                found.append(Link(source, anchor))
    for match in bare.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        if root is not None and _cited_file(source, match.group(1), root) == str(rel):
            found.append(Link(source, match.group(2)))
    return found


def _cites(root, name, heading):
    """True when a line of name holds heading and is not itself a heading.
    In Markdown a line starting with # may be a heading, which is not a
    citation. Outside Markdown a # starts a comment, so every line counts."""
    if not name.lower().endswith(MARKDOWN_SUFFIXES):
        return True
    try:
        lines = (pathlib.Path(root) / name).read_text(encoding="utf-8", errors="replace") \
            .split("\n")
    except OSError:
        return True
    for index, line in enumerate(lines):
        if heading not in line:
            continue
        underlined = index + 1 < len(lines) and SETEXT.match(lines[index + 1])
        if not HEADING.match(line) and not underlined:
            return True
    return False


def cited_headings(path, headings, root):
    """{heading: [file]} for each heading of at least 16 characters that a
    tracked file other than path names word for word, as code comments cite
    a decision by its title. A shorter heading, such as "Why" or "Open",
    matches unrelated text. A line that is itself a heading, as when two
    docs share a heading, is not a citation."""
    out = {}
    for heading in headings:
        if len(heading) < 16:
            continue
        listed = _git(["grep", "-I", "-l", "-z", "-F", "-e", heading], root)
        files = [name for name in (listed or "").split("\0")
                 if name and name != path and _cites(root, name, heading)]
        if files:
            out[heading] = files
    return out


# ---------------------------------------------------------------------------
# `prose compact <file>`
# ---------------------------------------------------------------------------

def _root_of(file_path):
    out = _git(["rev-parse", "--show-toplevel"], str(file_path.parent))
    return out.strip() if out else None


def snapshot_dir(file_path, state_home):
    """Where the snapshot of the file before compaction waits: prose/compact
    in its repository's git directory, or in prose's state home outside one."""
    common = _git(["rev-parse", "--git-common-dir"], str(file_path.parent))
    if common and common.strip():
        return (file_path.parent / common.strip()).resolve() / "prose" / "compact"
    return state_home / "compact"


def _snapshot_path(file_path, state_home):
    key = hashlib.sha256(str(file_path).encode("utf-8", "surrogateescape")).hexdigest()[:24]
    return snapshot_dir(file_path, state_home) / key


class Target(NamedTuple):
    file: pathlib.Path
    root: Optional[str]
    rel: str


def target(name):
    """The file to compact, its repository root (None outside one) and its
    path inside the repository."""
    file_path = pathlib.Path(name).resolve()
    if not file_path.is_file():
        raise ValueError(f"{name}: no such file")
    root = _root_of(file_path)
    rel = str(file_path.relative_to(pathlib.Path(root).resolve())) if root else file_path.name
    return Target(file_path, root, rel)


def _guarded(found):
    """The headings the result must keep: those other files link to or cite."""
    links, cited = found
    return sorted({link.anchor for link in links}), cited


def brief(name, state_home, command):
    """Save the file as it is now, and print the compactor's brief. Returns
    BRIEF_PRINTED."""
    where = target(name)
    text = where.file.read_text(encoding="utf-8")
    now = time.time()
    directory = snapshot_dir(where.file, state_home)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in directory.iterdir():
        try:
            if now - entry.stat().st_mtime > SNAPSHOT_LIFETIME:
                entry.unlink()
        except OSError:
            pass
    links = links_into(where.rel, where.root) if where.root else []
    cited = cited_headings(where.rel, heading_texts(text), where.root) if where.root else {}
    snapshot = _snapshot_path(where.file, state_home)
    draft = snapshot.with_name(f".{snapshot.name}.{os.getpid()}")
    draft.write_text(json.dumps({"path": str(where.file), "text": text, "saved": now}),
                     encoding="utf-8")
    os.replace(draft, snapshot)

    markers = history_markers(text)
    linked, _ = _guarded((links, cited))
    print("=== compaction brief ===")
    print(BRIEF.read_text(encoding="utf-8").rstrip("\n"))
    print(f"\nThe file: {where.file}")
    print(f"Size: {len(text.encode('utf-8')):,} bytes, {len(text.split()):,} words.")
    if markers:
        print(f"\nHistory markers the script found ({len(markers)}); there may be others:")
        for marker in markers[:40]:
            print(f"  line {marker.line}: «{marker.words}»")
    if linked:
        print("\nHeadings other files link to. Keep each, with its exact text, so its anchor "
              "still resolves:")
        for anchor in linked:
            print(f"  #{anchor}")
    if cited:
        print("\nHeadings other files name word for word. Keep each, with its exact text:")
        for heading, files in sorted(cited.items()):
            print(f"  {heading}  (in {', '.join(files[:3])})")
    print("=== end compaction brief ===")
    print(f"\nGive a new subagent the brief above, exactly as printed; then run:\n\n"
          f"  {command} compact {shlex.quote(name)} --verify")
    return BRIEF_PRINTED


class Report(NamedTuple):
    lines: list
    failures: list


def check_result(before, after, rel, root, budget=DEFAULT_BUDGET):
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

    have = anchors(after)
    if root:
        links = links_into(rel, root)
        # A link already broken before the compaction is not its doing, and
        # the compactor cannot mend it by keeping a heading. A link from
        # another file is excused when its anchor was already missing. One
        # of the file's own links is excused only when the old file already
        # had it, since the compaction may have added it.
        had = anchors(before)
        linked_before = {link.anchor for link in links_in(rel, before, rel, root)}
        stale = [link for link in links if link.anchor not in had
                 and (link.source != rel or link.anchor in linked_before)]
        broken = [link for link in links if link.anchor not in have and link not in stale]
        lines.append(f"Links into this file: {len(links)} checked, {len(broken)} broken"
                     + (f", {len(stale)} already broken before" if stale else "") + ".")
        for link in broken:
            failures.append(f"{link.source} links to #{link.anchor}, which no heading gives now")
        old_headings, new_headings = heading_texts(before), set(heading_texts(after))
        gone = [heading for heading in old_headings if heading not in new_headings]
        for heading, files in sorted(cited_headings(rel, gone, root).items()):
            failures.append(f"the heading '{heading}' is gone, and {', '.join(files[:3])} "
                            f"names it")
    else:
        own, had, linked_before = _own_anchors(after), anchors(before), set(_own_anchors(before))
        stale = [anchor for anchor in own if anchor not in had and anchor in linked_before]
        broken = [anchor for anchor in own if anchor not in have and anchor not in stale]
        lines.append(f"Not in a git repository: only the file's own links were checked "
                     f"({len(own)}, {len(broken)} broken"
                     + (f", {len(stale)} already broken before" if stale else "") + ").")
        for anchor in broken:
            failures.append(f"the file links to #{anchor}, which no heading gives now")

    gone_headings = [h for h in heading_texts(before) if h not in set(heading_texts(after))]
    if gone_headings:
        lines.append(f"Headings removed or renamed ({len(gone_headings)}): "
                     + "; ".join(gone_headings[:30]) + (" ..." if len(gone_headings) > 30 else ""))
    dropped = gone_terms(before, after)
    if dropped:
        lines.append(f"Names that are gone ({len(dropped)}); the reviewer checks each: "
                     + ", ".join(term for _, term in dropped[:60])
                     + (" ..." if len(dropped) > 60 else ""))
    for marker in history_markers(after):
        failures.append(f"history marker left at line {marker.line}: «{marker.words}»")
    return Report(lines, failures)


def _own_anchors(text):
    """The anchor of each `#anchor` link in text, outside code."""
    targets = [link_target(match) for match in LINK.finditer(_code_blanked(text))]
    return [target[1:] for target in targets if target.startswith("#")]


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
    kept = set(heading_texts(after))
    for heading in heading_texts(before):
        if heading not in kept and heading not in seen:
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


def _paragraphs(text):
    """(paragraphs, the heading above each): the text split at blank lines,
    except blank lines inside fenced blocks."""
    paragraphs, headings, current, heading, fence = [], [], [], "", None
    for line in text.split("\n"):
        stripped = line.lstrip()
        if fence and stripped.startswith(fence):
            fence = None
        elif not fence and re.match(r"(`{3,}|~{3,})", stripped):
            fence = re.match(r"(`{3,}|~{3,})", stripped).group(1)
        if not fence and not line.strip():
            if current:
                paragraphs.append("\n".join(current))
                headings.append(heading)
                current = []
            continue
        match = HEADING.match(line) if not fence else None
        if match and not current:
            heading = match.group(2)
        elif not fence and current and SETEXT.match(line) and _setext_text(current):
            heading = " ".join(part.strip() for part in current)
        current.append(line)
    if current:
        paragraphs.append("\n".join(current))
        headings.append(heading)
    return paragraphs, headings


def changes(before, after):
    """[Change] between the two texts, paragraph by paragraph, ignoring
    rewrapping: each removed, rewritten or added run of paragraphs, with the
    heading it sits under in the old text."""
    old, old_headings = _paragraphs(before)
    new, new_headings = _paragraphs(after)
    flat = lambda paragraph: " ".join(paragraph.split())
    matcher = difflib.SequenceMatcher(None, [flat(p) for p in old], [flat(p) for p in new],
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


def review(name, state_home):
    """Write what the compaction removed and rewrote to a file, and print the
    reviewer's brief, which names it. Returns BRIEF_PRINTED."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    after = where.file.read_text(encoding="utf-8")
    found = changes(saved["text"], after)
    dropped = gone_terms(saved["text"], after)
    path = _snapshot_path(where.file, state_home).with_suffix(".review.md")
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
    path.write_text("\n".join(parts), encoding="utf-8")
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
          "compactor.")
    return BRIEF_PRINTED


def _load_snapshot(where, name, state_home):
    try:
        return json.loads(_snapshot_path(where.file, state_home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"no snapshot of {name} from the last {SNAPSHOT_LIFETIME // 86400} "
                         f"days: run 'compact {name}' first, before the file is changed")


def verify(name, state_home):
    """Check the compacted file against its snapshot; print the report.
    Returns VERIFIED or FAILED."""
    where = target(name)
    saved = _load_snapshot(where, name, state_home)
    after = where.file.read_text(encoding="utf-8")
    budget = settings([where.rel], where.root)[where.rel].budget
    report = check_result(saved["text"], after, where.rel, where.root, budget)
    print(f"prose compact: {where.rel}")
    for line in report.lines:
        print(line)
    if report.failures:
        print(f"\nFailed ({len(report.failures)}):")
        for failure in report.failures:
            print(f"  {failure}")
        print("\nFix these in the file, then run --verify again.")
        return FAILED
    print("\nVerified. Ask the person before committing if the compactor listed a conclusion "
          "it would drop.")
    return VERIFIED
