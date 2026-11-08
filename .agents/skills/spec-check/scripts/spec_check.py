#!/usr/bin/env python3
"""spec-check: the mechanical half of reviewing an OpenSpec change.

    spec_check.py check [<target>...] [--repo DIR] [--ref REF] [--base REF]
                        [--no-validate] [--json]
    spec_check.py sign --read subagent|self|deferred [--amended N] [--open N]
                       [--base REF] [--no-validate]
    spec_check.py verify-staged "Spec-check: <value>"   (message on stdin)
    spec_check.py verify-commit <sha> <value>
    spec_check.py ci [--event FILE] [--repo DIR]
    spec_check.py setup-ci [--repo DIR] [--sha SHA] [--force]
    spec_check.py records <change> [--repo DIR] [--ref REF] [--base REF]
    spec_check.py archive <change> [--repo DIR] [-- <openspec archive arguments>]

A change's committed `.spec-check-kept` file clears the `evolution` errors a
person chose to keep, for check and sign alike: one entry per line,
`<file>: «<line text>» kept (asked): <reason>` (SKILL.md, "Keeping a line
the evolution check flags").

A target is a change name, a change directory (openspec/changes/<name>), or
`specs` for every spec under openspec/specs. With no target, every open change
is checked. `--ref` reads openspec/ from a git ref instead of the working tree,
so a pull request's branch is checked without checking it out.

A change whose proposal.md has `Builds on: <change> (<owner>/<repo>#<number>)`
lines is checked against a scratch copy of the tree's specs, into which
`openspec archive` has archived each open dependency. A merged dependency is
never archived: its result must already show in the tree. Each dependency is
read from its pull request with gh and git, which needs the network, and the
OpenSpec CLI must be on PATH. A dependency that cannot be read, judged or
archived is an error, never skipped.

Every checked change is also archived into a scratch copy of the specs by
`openspec archive`: alone, or for a stacked change, on top of its
dependencies. Each refusal is an error.

Specs and deltas are read only through the OpenSpec CLI, 1.15.0 or later:
`openspec show --json` for their requirements, `openspec validate --strict
--json` for what a delta drops, `openspec archive --json` for whether a
change applies. Without it, every check that needs a requirement is
reported as not run, and a stacked change gets an error.

check exits 0 with no errors, 1 with errors, 2 when it cannot run. Findings
marked `check` are heuristics for a person or agent to judge; they never fail.

sign runs check on the staged tree and, when no error remains, prints the
`Spec-check:` trailer value bound to that tree. `--read` says what the value
records of the consistency read: `subagent` or `self` for a read done this
round, `deferred` for a commit before the round's end. sign searches the
branch's git history for each change's last read to name the changes that
are due, and ends the value with `no read due` when none is.

ci is the GitHub workflow's check of a pull request event ($GITHUB_EVENT_PATH):
it fails when a change is unread at the pull request's head and, when the
event handed the pull request back for review, makes it a draft again and
withdraws the review request. setup-ci writes that workflow into a
repository, pinned to a commit of this file. verify-staged and
verify-commit check a `Spec-check:` value against the staged tree or a
commit: the shared commit library (.agents/lib/commit-trailer) calls the
first before it commits, and the commit hook the second after.

Each capability's decision record (its constraints and rejected
alternatives) is at the path openspec/spec-check.yaml gives as
`decision-records: <path with <capability>>`, by default
openspec/specs/<capability>/decisions.md; a change's own record is its
specs/<capability>/decisions.md. check gives each record format checks,
and each requirement of a change a `rationale` check when its text holds
more than its statement and one sentence. records prints the records a
change's consistency read is given: main records, and the records of the
changes it builds on. archive runs `openspec archive` and then folds the
change's records into the main records, since OpenSpec ignores records.

Standard library only. Read DECISIONS.md next to SKILL.md before changing this.
"""

from __future__ import annotations

import argparse
import bisect
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse

KEY = "Spec-check"

NORMATIVE = re.compile(r"\b(SHALL|MUST)\b")
WHEN = re.compile(r"(\*\*WHEN\*\*|^\s*[-*]?\s*WHEN\b)", re.M)
THEN = re.compile(r"(\*\*THEN\*\*|^\s*[-*]?\s*THEN\b)", re.M)

# path:line or path:line-line. The lookbehind keeps it from starting inside a
# URL or a longer token.
CITATION = re.compile(
    r"(?<![\w/.@:-])((?:\./)?(?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z0-9]{1,8})"
    r":(\d+)(?:[-–](\d+))?(?![\w])"
)
# Names that end like a host are addresses, not files: example.com:443, and the
# first segment of an image such as ghcr.io/acme/web.api:2.
HOST_SUFFIXES = set("""com org net io dev ai app co uk us de eu fr jp cn ru in au ca local
localhost internal lan home arpa edu gov mil int info biz me tv cloud xyz site online
tech""".split())

DUPLICATE_MIN_WORDS = 10


class Fatal(Exception):
    """Cannot run at all: exit 2."""


def git(repo, *args, check=True, binary=False, stdin=None, env=None):
    result = subprocess.run(
        # core.quotePath=false: paths are printed as they are, not escaped,
        # so a path with non-ASCII letters matches its own name.
        ["git", "-C", repo, "-c", "log.showSignature=false", "-c", "core.quotePath=false", *args],
        capture_output=True, input=stdin, text=not binary, env=env,
        # A file name that is not UTF-8 comes through raw: kept, never a crash.
        errors=None if binary else "surrogateescape",
    )
    if check and result.returncode != 0:
        err = result.stderr if not binary else result.stderr.decode("utf-8", "replace")
        raise Fatal(f"git {' '.join(args)} failed: {err.strip()}")
    return result


# -- reading openspec/ -----------------------------------------------------

def materialize(repo, treeish, dest, allow_empty=False):
    """Writes treeish's openspec/ under dest. With allow_empty, a tree that has
    none gets an empty one: sign must sign a commit that deletes openspec/."""
    refuse_links(openspec_links(repo, treeish))
    has = git(repo, "ls-tree", "--name-only", treeish, "--", "openspec", check=False)
    if allow_empty and has.returncode == 0 and not has.stdout.strip():
        os.makedirs(os.path.join(dest, "openspec"))
        return
    # The peeled tree, not a commit: a commit's archive starts with a pax
    # header, so one with no file in it is a tar that tarfile cannot open.
    out = git(repo, "archive", "--format=tar", f"{treeish}^{{tree}}", "--", "openspec",
              check=False, binary=True)
    if out.returncode != 0:
        raise Fatal(f"cannot read openspec/ from {treeish}: "
                    f"{out.stderr.decode('utf-8', 'replace').strip()}")
    extract(out.stdout, dest, treeish)


def extract(data, dest, treeish):
    """Extracts a tar from git archive under dest."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python before 3.12 has no filter argument
            tar.extractall(dest)
        except tarfile.TarError as e:  # such as a link to an absolute path
            raise Fatal(f"cannot extract openspec/ from {treeish}: {e}") from e


FENCE = re.compile(r"(`{3,}|~{3,})")


def normalize_line_endings(content):
    return re.sub(r"\r\n?", "\n", content)

LIST_MARKER = re.compile(r"([-+*]|\d{1,9}[.)])( +)(?=\S)")
QUOTE_MARKER = re.compile(r" {0,3}> ?")


def strip_quotes(line, limit=None):
    """line without its leading blockquote markers, at most limit of them,
    and how many were removed."""
    depth = 0
    while limit is None or depth < limit:
        m = QUOTE_MARKER.match(line)
        if not m:
            break
        line, depth = line[m.end():], depth + 1
    return line, depth


def opens_fence(body):
    """The (character, length) of the fence that the line `body` opens, or
    None. A backtick
    fence's info string may hold no backtick, as in CommonMark."""
    m = FENCE.match(body)
    if not m or (m.group(1)[0] == "`" and "`" in body[m.end():]):
        return None
    return m.group(1)[0], len(m.group(1))


def markdown_lines(text):
    """Each line of a markdown text as (line number, line, in a code fence).
    Fence lines themselves count as inside. Every scan of a proposal or spec
    reads through this, so text quoted in a fence is never taken for a
    header, a section or a citation.

    Lines are split as OpenSpec splits them: at "\n" once line endings are
    normalized, so a line number here is OpenSpec's. str.splitlines() would
    also split at form feeds and Unicode line separators.

    It follows CommonMark as far as fences need:
    - A fence may be indented up to three spaces past the content column of
      the list item it sits in, and may open on the item's own marker line.
    - It closes only with a bare fence of its own character, at least as long.
    - A line indented less than the content column of the fence's list item
      ends that item, and the fence with it.
    - A lazy continuation line keeps its list item open, but a fence line is
      never lazy: it interrupts the paragraph, as in CommonMark.
    - Blockquote markers (`>`) are set aside before any of this. A fence
      records how many blockquote levels it opened in, and only that many
      `>` markers are stripped from its lines, so a `>` prompt in a code
      example stays code."""
    items = []      # content columns of the open list items, outermost first
    # The open fence: (character, length, content column of its list item or
    # 0, blockquote depth).
    fence = None
    prose = False   # whether the line before was paragraph text
    # OpenSpec drops a leading byte-order mark, as a Windows editor writes.
    lines = normalize_line_endings(text).removeprefix("\ufeff").split("\n")
    if lines[-1] == "":
        lines.pop()  # the text ends with a newline, which starts no line
    for n, raw in enumerate(lines, 1):
        line = raw.expandtabs(4)
        if fence is not None:
            line, depth = strip_quotes(line, fence[3])
            body = line.lstrip(" ")
            indent = len(line) - len(body)
            if (body and indent < fence[2]) or depth < fence[3]:
                fence = None  # its list item or blockquote ended, and the fence with it
                line, depth = strip_quotes(raw.expandtabs(4))
                body = line.lstrip(" ")
                indent = len(line) - len(body)
            else:
                m = FENCE.match(body)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                        and not body[m.end():].strip() and indent - fence[2] <= 3:
                    fence = None
                yield n, raw, True
                continue
        else:
            line, depth = strip_quotes(line)
            body = line.lstrip(" ")
            indent = len(line) - len(body)
        if not body:
            prose = False
            yield n, raw, False
            continue
        marker = LIST_MARKER.match(body)
        opener = opens_fence(body)
        # A lazy paragraph line stays in its list item. Any other line closes
        # the items it is indented less than.
        if not (prose and not marker and not opener):
            while items and indent < items[-1]:
                items.pop()
        column = items[-1] if items else 0
        if marker and indent - column <= 3:
            spaces = len(marker.group(2))
            content = indent + len(marker.group(1)) + (spaces if spaces <= 4 else 1)
            items.append(content)
            inner = opens_fence(body[marker.end():])
            if inner:  # a fence opened on the item's marker line
                fence = (inner[0], inner[1], content, depth)
                prose = False
                yield n, raw, True
                continue
            prose = True
            yield n, raw, False
            continue
        if opener and 0 <= indent - column <= 3:
            fence = (opener[0], opener[1], column, depth)
            prose = False
            yield n, raw, True
            continue
        prose = True
        yield n, raw, False


class Req:
    def __init__(self, path, line, name, section):
        self.path, self.line, self.name, self.section = path, line, name, section
        # (line number, text) of each line of its text, as `openspec show`
        # gives it, with a blank entry where the file has blank lines
        # between two of them (make_req).
        self.text = []
        self.scenarios = []   # Scenario
        # Set only on a requirement of the base a change is checked against
        # (the tree's specs, plus any dependencies): cap is the capability it
        # belongs to there. dep is the dependency that defined or renamed it,
        # or None for a requirement of the tree's own specs.
        self.cap = None
        self.dep = None
        # Its name where it was read from, when the base holds it under
        # another name, for example after a later dependency renames it.
        self.own = None
        # What it says: its text and each scenario's name and text, as
        # `openspec show` reads them, and the fenced lines of its block,
        # which `show` leaves out and the archive writes. Two versions of a
        # requirement are the same when these match.
        self.content = None
        # Its lines as the file writes them, from its header to the next
        # section or requirement header, or None when its header was not
        # found. A delta rebuilt from it keeps what `openspec show` leaves
        # out, as the archive would.
        self.block = None

    def restated(self, name=None, cap=None, dep=None):
        """A copy for the base a change is checked against, under a new name
        if one is given. It shares its text and scenario lists with this
        requirement."""
        r = Req(self.path, self.line, name or self.name, None)
        r.text, r.scenarios = self.text, self.scenarios
        r.cap, r.dep, r.own = cap, dep, self.own or self.name
        r.content = self.content
        return r

    def where(self, line=None):
        at = f"{self.path}:{line or self.line}" if (line or self.line) else self.path
        return f"{at} in {self.dep.slug}#{self.dep.number}" if self.dep else at

    @property
    def body(self):
        return "\n".join(t for _, t in self.text)


class Scenario:
    def __init__(self, line, name):
        self.line, self.name, self.lines = line, name, []


# -- the OpenSpec CLI ----------------------------------------------------------
#
# spec-check reads specs and deltas only through the OpenSpec CLI's public
# commands (DECISIONS.md, "spec-check reads OpenSpec only through its CLI"):
# `openspec show --json` for the requirements a spec or delta holds,
# `openspec validate --strict --json` for what a delta drops or misfiles,
# and `openspec archive --json` for whether a change applies. `show --json`
# names requirements and scenarios from 1.14.0, and from 1.15.0 `validate`
# reports the text the archive drops, so 1.15.0 is the minimum. Without it,
# every check that needs a requirement is reported as not run.

OPENSPEC_SINCE = (1, 15, 0)
NEEDS_OPENSPEC = "install OpenSpec 1.15.0 or later"
CLI_TIMEOUT = 120
# `openspec show` refuses a change whose proposal.md lacks "Why" or "What
# Changes", so a change's deltas are read beside this one instead of its own.
STUB_PROPOSAL = ("## Why\n\nRead by spec-check for its deltas.\n\n"
                 "## What Changes\n\n- Its deltas.\n")
SHOWN_CHANGE = "spec-check-read"
_versions = {}   # CLI path -> its version match, or None
_shown = {}      # show's key -> (data, None) or (None, what OpenSpec said)


def openspec_exe():
    """The OpenSpec CLI, or None when it is not on PATH."""
    return shutil.which("openspec")


def openspec_missing():
    """None when the CLI on PATH is OPENSPEC_SINCE or later; otherwise why
    spec-check cannot use it, starting with NEEDS_OPENSPEC. A CLI whose
    version cannot be read is not used."""
    exe = openspec_exe()
    if exe is None:
        return f"{NEEDS_OPENSPEC} (the openspec CLI is not on PATH)"
    if exe not in _versions:
        try:
            r = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=CLI_TIMEOUT)
            out = r.stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        _versions[exe] = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", out)
    m = _versions[exe]
    if m is None:
        return f"{NEEDS_OPENSPEC} (`openspec --version` printed no version)"
    if tuple(map(int, m.groups())) < OPENSPEC_SINCE:
        return f"{NEEDS_OPENSPEC} (this one is {m.group(0)})"
    return None


def not_run():
    """The status of a check that needs the CLI, when it is missing."""
    return f"not run: {openspec_missing()}"


def openspec_json(root, *args):
    """(exit code or None, the JSON object the CLI printed or None, its last
    line of output) for one run of the CLI in root."""
    env = dict(os.environ, OPENSPEC_TELEMETRY="0", DO_NOT_TRACK="1")
    try:
        r = subprocess.run([openspec_exe() or "openspec", *args], cwd=root, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=CLI_TIMEOUT, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, None, f"`openspec {args[0]}` could not run: {e}"
    try:
        data = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        data = None
    tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
    return r.returncode, data if isinstance(data, dict) else None, tail[0]


def cli_said(data, tail):
    """The messages of the CLI's JSON status list, or its last line."""
    status = data.get("status") if isinstance(data, dict) else None
    said = [s["message"] for s in status or [] if isinstance(s, dict) and s.get("message")]
    return "; ".join(said) or tail


def show(kind, name, files):
    """`openspec show <name> --json --type <kind>`, over files ({path under
    the root: text}) written into an empty directory, so that nothing else
    is read; for a change, its deltas only. (data, None), or (None, what the
    CLI said). Each reading is kept for the run, by content."""
    key = (kind, name, tuple(sorted(files.items())))
    if key not in _shown:
        with tempfile.TemporaryDirectory(prefix="spec-check-show-") as tmp:
            os.makedirs(os.path.join(tmp, "openspec"))
            for rel, text in files.items():
                full = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(text)
            args = ["show", name, "--json", "--type", kind, "--no-interactive"]
            rc, data, tail = openspec_json(tmp, *(args + ["--deltas-only"] if kind == "change" else args))
        listed = data.get("deltas" if kind == "change" else "requirements") if data else None
        _shown[key] = (data, None) if rc == 0 and isinstance(listed, list) else (None, cli_said(data, tail))
    return _shown[key]


# -- finding lines -----------------------------------------------------------
#
# `openspec show --json` gives no line numbers. A finding's line is found by
# searching the file's text for the names the CLI gives: a plain, tolerant
# text search with no header grammar of its own (DECISIONS.md, "A finding's
# line is a text search"). A wrong guess only misplaces a finding, and a
# name it cannot find gives line 0, so the finding names the file only.


def key(text):
    """text as the search compares it: case, backticks, #s and runs of
    space ignored."""
    return " ".join(re.sub(r"[`#]", " ", text).lower().split())


def after_label(raw, label):
    """What follows the first `label` in raw, ignoring case, or None."""
    at = raw.lower().find(label)
    return None if at < 0 else raw[at + len(label):]


# OpenSpec's own test for a requirement header. Only requirement_above and
# Lines.block use it: what the archive keeps of a stray heading turns on it.
REQUIREMENT_HEADER = re.compile(r"^###\s*Requirement:\s*\S", re.I)


class Lines:
    """The lines of one file, searched for what `openspec show` names. The
    searches skip lines in code fences; block() keeps them."""

    def __init__(self, text):
        every = list(markdown_lines(text))
        self.lines = [(n, raw) for n, raw, fenced in every if not fenced]
        self.every = every
        self.used = set()

    def header(self, name, side=None):
        """The line naming requirement name after "Requirement:", not
        already given to an earlier name, or 0. With side "FROM" or "TO", only a line holding that
        word; otherwise only a line holding neither. A line starting with
        "###" wins over any other, such as an indented example of one, and
        then a line naming it exactly over one naming it as key() does, so
        two names OpenSpec tells apart keep their own lines."""
        want, found = key(name), []
        for n, raw in self.lines:
            rest = after_label(raw, "requirement:")
            if rest is None or n in self.used or key(rest) != want:
                continue
            head = raw.lower()[:raw.lower().find("requirement:")]
            sides = [w for w in ("from:", "to:") if w in head]
            if sides != ([side.lower() + ":"] if side else []):
                continue
            exact = re.sub(r"[ \t]+#+[ \t]*$", "", rest).strip() == name.strip()
            found.append((not raw.startswith("###"), not exact, n))
        if not found:
            return 0
        n = min(found)[2]
        self.used.add(n)
        return n

    def block_end(self, start):
        """The first line after line start that starts with "## " or "### "
        (a section, or the next requirement), or one past the last line."""
        return next((n for n, raw in self.lines if n > start and raw.startswith(("## ", "### "))),
                    self.lines[-1][0] + 1 if self.lines else start + 1)

    def after(self, start, want, end, scenario=False):
        """The first line after line start, and before line end, whose text
        is want; for a scenario, a "####" line naming it, with or without
        "Scenario:". 0 if none."""
        for n, raw in self.lines:
            if n <= start or n >= end:
                continue
            if not scenario:
                if raw.strip() == want.strip():
                    return n
            elif raw.startswith("####"):
                title = raw.lstrip("#")
                title = after_label(title, "scenario:") if "scenario:" in title.lower() else title
                if key(title) == key(want):
                    return n
        return 0

    def requirement_above(self, line):
        """Whether a requirement header, as OpenSpec matches one, is above
        line within its section, which a "## " line starts; None when line
        is 0 and nothing can be said."""
        if not line:
            return None
        for n, raw in reversed(self.lines):
            if n >= line:
                continue
            if SECTION_START.match(raw):
                return False
            if REQUIREMENT_HEADER.match(raw):
                return True
        return False

    def block(self, start):
        """The lines from line start, a requirement header, up to the next
        "## " line or requirement header outside a fence, as the file
        writes them, each as (line, in a code fence); None when line start
        is not a requirement header."""
        if not any(n == start and REQUIREMENT_HEADER.match(raw) for n, raw in self.lines):
            return None
        out = []
        for n, raw, fenced in self.every:
            if n < start:
                continue
            if n > start and not fenced and (SECTION_START.match(raw) or REQUIREMENT_HEADER.match(raw)):
                break
            out.append((raw, fenced))
        while out and not out[-1][0].strip():
            out.pop()
        return out


def make_req(rel, lines, data, section):
    """A Req for one requirement of `openspec show`'s JSON, its lines found
    in lines. Every search stays between its header and the next "## " or
    "### " line, so a line of another requirement is not taken for one of
    this one."""
    name = str(data.get("name") or "")
    r = Req(rel, lines.header(name), name, section)
    text = str(data.get("text") or "")
    end = lines.block_end(r.line) if r.line else 0
    at = prev = r.line
    for t in text.split("\n") if text else []:
        n = lines.after(at, t, end)
        if n:
            if r.text and n > prev + 1:
                r.text.append((n - 1, ""))  # the file has a paragraph break here
            at = prev = n
        r.text.append((n or at, t))
    scenarios = [s for s in data.get("scenarios") or [] if isinstance(s, dict)]
    last = r.line  # each scenario is searched for after the one before it
    for s in scenarios:
        sname = str(s.get("name") or "")
        found = lines.after(last, sname, end, scenario=True)
        last = found or last
        sc = Scenario(found or r.line, sname)
        sc.lines = str(s.get("rawText") or "").split("\n")
        r.scenarios.append(sc)
    # `openspec show` leaves fenced code out, and `openspec archive` writes
    # it, so the fenced lines of the block it writes are part of what it says.
    block = lines.block(r.line) if r.line else None
    r.block = [raw for raw, _ in block] if block is not None else None
    fences = tuple(raw.rstrip() for raw, fenced in block or [] if fenced)
    r.content = (text, tuple((str(s.get("name") or ""), str(s.get("rawText") or "")) for s in scenarios),
                 fences)
    return r


def read_spec(rel, text, cap):
    """([Req], None) for a main spec as `openspec show` reads it, or ([],
    what the CLI said when it cannot read it)."""
    data, err = show("spec", cap, {f"openspec/specs/{cap}/spec.md": text})
    if err:
        return [], err
    lines = Lines(text)
    reqs = [make_req(rel, lines, d, None) for d in data["requirements"] if isinstance(d, dict)]
    for r in reqs:
        r.cap = cap
    return reqs, None


ARCHIVE_ORDER = {"RENAMED": 0, "REMOVED": 1, "MODIFIED": 2, "ADDED": 3}


def read_deltas(files, dep=None):
    """({capability: [Item]}, None) for one change's delta specs (files:
    {capability: (rel path, text)}) as `openspec show` reads them, each
    capability's items in the order `openspec archive` applies them:
    renames, removals, modifications, additions. (None, what the CLI said)
    when it cannot read them."""
    if not files:
        return {}, None
    data, err = show("change", SHOWN_CHANGE, {
        **{f"openspec/changes/{SHOWN_CHANGE}/specs/{cap}/spec.md": text
           for cap, (_, text) in files.items()},
        f"openspec/changes/{SHOWN_CHANGE}/proposal.md": STUB_PROPOSAL})
    if err:
        return None, err
    lines = {cap: Lines(text) for cap, (_, text) in files.items()}
    out = {cap: [] for cap in files}
    for d in data["deltas"]:
        if not isinstance(d, dict):
            continue
        cap, kind = d.get("spec"), str(d.get("operation") or "").upper()
        if cap not in files or kind not in ARCHIVE_ORDER:
            continue
        if kind == "RENAMED":
            ren = d.get("rename") if isinstance(d.get("rename"), dict) else {}
            old, new = str(ren.get("from") or ""), str(ren.get("to") or "")
            out[cap].append(Item(dep, cap, kind, old, new, line=lines[cap].header(old, "FROM")))
            continue
        data_req = d.get("requirement") if isinstance(d.get("requirement"), dict) else {}
        if kind == "REMOVED":
            name = str(data_req.get("name") or "")
            out[cap].append(Item(dep, cap, kind, name, line=lines[cap].header(name)))
            continue
        r = make_req(files[cap][0], lines[cap], data_req, kind)
        out[cap].append(Item(dep, cap, kind, r.name, req=r, line=r.line))
    for items in out.values():
        items.sort(key=lambda i: ARCHIVE_ORDER[i.kind])
    return out, None


def retired_names(cap, text):
    """Names of the requirements one delta spec for cap removes or renames
    away from, as `openspec show` reads it."""
    items, err = read_deltas({cap: ("", text)})
    return set() if err else {i.name for i in items[cap] if i.kind in ("REMOVED", "RENAMED")}


def delta_rel(rel):
    """The capability of a change's delta spec, as `openspec archive` finds
    one: openspec/changes/<change>/specs/<capability>/spec.md, where the
    capability may be nested, such as area/cap; never a sibling such as
    v2-spec.md; otherwise None."""
    parts = rel.split("/")
    if len(parts) >= 6 and parts[:2] == ["openspec", "changes"] and parts[2] != "archive" \
            and parts[3] == "specs" and parts[-1] == "spec.md":
        return "/".join(parts[4:-1])
    return None


def spec_cap(rel):
    """The capability of a main spec, openspec/specs/<capability>/spec.md,
    which may be nested, such as area/cap; otherwise None."""
    parts = rel.split("/")
    if len(parts) >= 4 and parts[:2] == ["openspec", "specs"] and parts[-1] == "spec.md":
        return "/".join(parts[2:-1])
    return None


class Corpus:
    """Everything under openspec/ at one root: main specs and open changes,
    their requirements read with `openspec show` when the CLI is usable."""

    def __init__(self, root, requirements=True):
        # requirements: whether to read requirements with `openspec show`;
        # without, every spec and change has none and only texts are read.
        self.root = root
        base = os.path.join(root, "openspec")
        refuse_links(openspec_links(root))
        if not os.path.isdir(base):
            raise Fatal(f"no openspec/ directory in {root}")
        self.missing = openspec_missing() if requirements else NEEDS_OPENSPEC
        # Where each capability's main decision record is, as
        # openspec/spec-check.yaml says, and what is wrong with that file.
        self.template, self.config_findings = read_config(root)
        self.records = {}       # main record rel path -> text
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            if rel_dir == "openspec":
                dirnames[:] = [d for d in dirnames if d != "changes"]
            dirnames.sort()
            for f in sorted(filenames):
                rel = f"{rel_dir}/{f}"
                if record_cap(self.template, rel) is None or not os.path.isfile(os.path.join(dirpath, f)):
                    continue  # not a record, or not a regular file, such as a FIFO
                with open(os.path.join(dirpath, f), encoding="utf-8", errors="replace") as fh:
                    self.records[rel] = fh.read()
        self.specs = {}     # rel path -> [Req]
        self.changes = {}   # change name -> {rel path -> [Req]}
        self.items = {}     # change name -> {capability -> [Item]}
        self.texts = {}     # rel path -> text, every markdown file read
        self.unread = {}    # rel path, or a change's name -> what `openspec show` said
        specs_dir = os.path.join(base, "specs")
        for name in sorted(os.listdir(specs_dir)) if os.path.isdir(specs_dir) else []:
            for rel in self._markdown(os.path.join("openspec", "specs", name)):
                cap = spec_cap(rel)
                if cap is None:
                    continue
                reqs, err = read_spec(rel, self.texts[rel], cap) if not self.missing else ([], None)
                self.specs[rel] = reqs
                if err:
                    self.unread[rel] = err
        changes_dir = os.path.join(base, "changes")
        for name in sorted(os.listdir(changes_dir)) if os.path.isdir(changes_dir) else []:
            if name == "archive" or not os.path.isdir(os.path.join(changes_dir, name)):
                continue
            rels = {}
            for rel in self._markdown(os.path.join("openspec", "changes", name)):
                cap = delta_rel(rel)
                if cap is not None:
                    rels[cap] = rel
            items, err = read_deltas({cap: (rel, self.texts[rel]) for cap, rel in rels.items()}) \
                if not self.missing else ({cap: [] for cap in rels}, None)
            if err:
                self.unread[name] = err
                items = {cap: [] for cap in rels}
            self.items[name] = items
            self.changes[name] = {rel: [i.req for i in items[cap] if i.req is not None]
                                  for cap, rel in rels.items()}

    def _markdown(self, rel_dir):
        found = []
        for dirpath, dirnames, filenames in os.walk(os.path.join(self.root, rel_dir)):
            dirnames.sort()
            for f in sorted(filenames):
                if f.endswith(".md"):
                    full = os.path.join(dirpath, f)
                    rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                    if not os.path.isfile(full):
                        continue  # such as a FIFO, which open would wait on
                    with open(full, encoding="utf-8", errors="replace") as fh:
                        self.texts[rel] = fh.read()
                    found.append(rel)
        return found

    def files_of(self, change):
        prefix = f"openspec/changes/{change}/"
        return [p for p in self.texts if p.startswith(prefix)]

    def retired(self, change, cap):
        """Names change's delta for cap removes or renames away from."""
        return {i.name for i in self.items.get(change, {}).get(cap, [])
                if i.kind in ("REMOVED", "RENAMED")}

    def all_reqs(self, base=None, skip=()):
        """Every requirement: those in the list base (by default, the specs
        under openspec/specs), then those of every open change not named in
        skip."""
        if base is None:
            base = [r for reqs in self.specs.values() for r in reqs]
        yield from base
        for name, files in self.changes.items():
            if name not in skip:
                for reqs in files.values():
                    yield from reqs


# -- findings ----------------------------------------------------------------

class Finding:
    def __init__(self, path, line, severity, kind, message):
        self.path, self.line, self.severity = path, line, severity
        self.kind, self.message = kind, message
        # Set on a duplicate finding in a change: (the change's name,
        # [(capability, name)] of each requirement under openspec/specs that
        # the duplicate matched). add_hints looks for an open pull request
        # that retires one of them.
        self.retirable = None
        # Set on an evolution finding: the flagged line, stripped, which a
        # kept entry quotes.
        self.quote = None
        # Set on a kept entry that matches an evolution error but lacks
        # `(asked)`: the text sign prints in its refusal, for the agent to
        # pass to whoever started it, who asks a person.
        self.handback = None

    def text(self):
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.severity} [{self.kind}] {self.message}"

    def as_dict(self):
        return {"path": self.path, "line": self.line, "severity": self.severity,
                "kind": self.kind, "message": self.message}


def stray_advice(cap, title, known, section=None, above=True):
    """What to write instead of a stray `### <title>` heading in a delta
    for cap, which OpenSpec's validator reports and ignores. known: the
    (capability, name) pairs of the specs the change is checked against, or
    None when they could not be read; with them the advice says which delta
    section the rule goes in. section: the delta section it is in. above:
    whether a requirement is above it in that section (Lines.
    requirement_above), or None when that is not known."""
    # OpenSpec's note quotes the heading with any closing #s, which are not
    # part of its name.
    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
    head = f'"### Requirement: {title}"'
    added = (f"write it as {head}" if section == "ADDED" and above is False
             else f'move it to "## ADDED Requirements" as {head}')
    modified = (f"restate it as {head}" if section == "MODIFIED" and above is False
                else f'restate it as {head} under "## MODIFIED Requirements"')
    if known is None:
        where = (f"{modified} if the specs already have \"{title}\", "
                 f"or {added} if they do not")
    else:
        # A MODIFIED block names a requirement the specs have, and an ADDED
        # one a requirement they lack; the archive refuses either otherwise.
        where = modified if (cap, title) in known else added
    if above:
        why = ("`openspec archive` keeps it inside the requirement above it, so a later change to "
               "that requirement replaces or removes it. ")
    elif above is False:
        why = "No requirement is above it in its section, so `openspec archive` drops it. "
    else:
        why = ""
    return f"{why}To keep it as a rule, {where}; otherwise make it plain text"


def check_scenarios(reqs, out):
    for r in reqs:
        if NORMATIVE.search(r.body) and not r.scenarios:
            out.append(Finding(r.path, r.line, "error", "no-scenario",
                               f'requirement "{r.name}" states a SHALL or MUST and has no scenario'))
        for s in r.scenarios:
            body = "\n".join(s.lines)
            missing = [w for w, rx in (("WHEN", WHEN), ("THEN", THEN)) if not rx.search(body)]
            if missing:
                out.append(Finding(r.path, s.line, "error", "scenario-incomplete",
                                   f'scenario "{s.name}" has no {" or ".join(missing)}'))


SECTION_START = re.compile(r"^##\s")
RENAMED_SECTION = re.compile(r"^##\s+RENAMED\s+Requirements\s*$", re.I)
LEVEL3 = re.compile(r"^###(?!#)\s*(.*?)\s*$")
RENAMED_FROM = re.compile(r"^\s*[-*+]?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$")
RENAMED_TO = re.compile(r"^\s*[-*+]?\s*TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$")


def check_renamed_blocks(rel, text, out):
    """A line scan, not a reading of the delta. Under "## RENAMED
    Requirements" OpenSpec reads only FROM and TO lines, so `openspec
    archive` drops a requirement written out there, and neither `openspec
    show` nor `openspec validate` says so (DECISIONS.md, "spec-check reads
    OpenSpec only through its CLI").
    Each `### ` heading in that section with anything under it but FROM and
    TO lines is an error."""
    inside, head, under = False, None, False

    def flush():
        if head and under:
            n, title = head
            out.append(Finding(rel, n, "error", "renamed-block",
                               f'"### {title}" is written out under "## RENAMED Requirements", where '
                               "OpenSpec reads only FROM and TO lines, so `openspec archive` drops "
                               "what is under it. To change a requirement's text, restate it under "
                               '"## MODIFIED Requirements" with its new name'))

    for n, raw, fenced in markdown_lines(text):
        if not fenced and SECTION_START.match(raw):
            flush()
            inside, head = bool(RENAMED_SECTION.match(raw)), None
            continue
        if not inside:
            continue
        m = None if fenced else LEVEL3.match(raw)
        if m:
            flush()
            head, under = (n, m.group(1)), False
        elif head and raw.strip() and (fenced or not (RENAMED_FROM.match(raw) or RENAMED_TO.match(raw))):
            under = True
    flush()


def units(req):
    """The requirement's sentences and list items, with their lines."""
    paras, cur, start = [], [], 0
    for n, t in req.text:
        stripped = t.strip()
        item = re.match(r"^([-*]|\d+[.)])\s+", stripped)
        if not stripped or item:  # a blank line or a list item ends a paragraph
            if cur:
                paras.append((start, " ".join(cur)))
            cur = []
            if not stripped:
                continue
            stripped = stripped[item.end():]
        if not cur:
            start = n
        cur.append(stripped)
    if cur:
        paras.append((start, " ".join(cur)))
    for line, para in paras:
        for sentence in re.split(r"(?<=[.;!?])\s+(?=[A-Z`*(\"])", para):
            yield line, sentence


def normalize(sentence):
    s = re.sub(r"[*_]", "", sentence.lower())
    return re.sub(r"\s+", " ", s).strip(" .;")


def retires(corpus, a, b):
    """Whether one of a and b is a requirement of the base (the specs, plus
    any dependencies) that the change holding the other removes or renames.
    The removal must be in that change's delta file for the base
    requirement's capability; the restated rule may sit in any capability.
    Such a pair is not reported as a duplicate, because the change replaces
    the base requirement. A removal by a change that is not a declared
    dependency does not count. A declared dependency's removal needs no
    test here: the requirement is already gone from the base (class
    Stack)."""
    for spec, delta in ((a, b), (b, a)):
        parts = delta.path.split("/")
        if spec.cap is None or delta.cap is not None or parts[1:2] != ["changes"]:
            continue
        if spec.name in corpus.retired(parts[2], spec.cap):
            return True
    return False


def capability(r):
    """The capability r belongs to: the one it was read under in the base,
    or for a requirement of a change, the directory of its delta spec."""
    if r.cap is not None:
        return r.cap
    return delta_rel(r.path)


def restates(a, b):
    """Whether one of a and b is a MODIFIED requirement restating the other:
    the same name, as OpenSpec matches names, in the same capability. Only
    such a pair may share sentences. An ADDED requirement, or one in another
    capability, that repeats a rule under the same name is a duplicate."""
    cap = capability(a)
    return (a.name == b.name and "MODIFIED" in (a.section, b.section)
            and cap is not None and cap == capability(b))


def check_duplicates(targets, corpus, out, base=None, skip=()):
    """base and skip are as Corpus.all_reqs takes them. A stacked change is
    checked against the specs plus its dependencies, so its dependencies'
    own changes are left out of the open changes: they are part of base
    already."""
    index = {}
    for r in corpus.all_reqs(base, skip):
        for line, sentence in units(r):
            key = normalize(sentence)
            if len(key.split()) >= DUPLICATE_MIN_WORDS:
                index.setdefault(key, []).append((r, line))
    target_ids = {id(r) for r in targets}
    for key, places in index.items():
        if len(places) < 2:
            continue
        for r, line in places:
            if id(r) not in target_ids:
                continue
            others = [(o, ol) for o, ol in places
                      if o is not r and not restates(r, o)
                      and not retires(corpus, r, o)]
            if others:
                o, ol = others[0]
                more = f" and {len(others) - 1} more" if len(others) > 1 else ""
                f = Finding(r.path, line, "error", "duplicate",
                            f'this rule is also stated in "{o.name}" at {o.where(ol)}{more}; '
                            "state it once and refer to it")
                parts = r.path.split("/")
                if r.cap is None and parts[1:2] == ["changes"]:
                    f.retirable = (parts[2], [(o.cap, o.name) for o, _ in others
                                              if o.cap is not None and o.dep is None])
                out.append(f)


SUBMODULE = "submodule"  # a path inside a submodule: unreadable, not missing


def count_lines(data):
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def tree_line_count(repo, treeish, path, hops=0):
    """Lines in path in a git tree, following symlinks as the file system
    would. None when there is no such file, and SUBMODULE when the path runs
    into a submodule, whose files the parent repository does not hold. `git show <tree>:<path>` alone
    reads a symlink as its target's name and cannot pass through a linked
    directory."""
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        prefix = "/".join(parts[:i])
        # -z: names unquoted, so one with spaces or non-ASCII still matches
        out = git(repo, "ls-tree", "-z", treeish, "--", prefix, check=False)
        entry = out.stdout.split("\0", 1)[0]
        if out.returncode != 0 or not entry.endswith("\t" + prefix):
            return None
        mode = entry.split(" ", 1)[0]
        if mode == "160000" and i < len(parts):
            return SUBMODULE  # git keeps no copy of a submodule's files
        if mode == "120000":  # a symlink
            target = git(repo, "show", f"{treeish}:{prefix}", check=False).stdout
            joined = posixpath.normpath(posixpath.join(
                posixpath.dirname(prefix), target, *parts[i:]))
            if hops >= 8 or target.startswith("/") or joined.startswith(".."):
                return None
            return tree_line_count(repo, treeish, joined, hops + 1)
    out = git(repo, "show", f"{treeish}:{path}", check=False, binary=True)
    return count_lines(out.stdout) if out.returncode == 0 else None


class Base:
    """Files on the change's base branch, read through git."""

    def __init__(self, repo, ref, change=None):
        # change: the tree the change is read from, as a git tree-ish, or
        # None for the working tree.
        self.repo, self.ref, self.change = repo, ref, change
        self._names = None
        self._lines = {}
        self.ok = git(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}",
                      check=False).returncode == 0

    def names(self):
        if self._names is None:
            out = git(self.repo, "ls-tree", "-r", "--name-only", self.ref)
            self._names = out.stdout.splitlines()
        return self._names

    def change_line_count(self, path):
        """Lines in the change's own copy of path, or None if it has none."""
        if self.change is None:
            full = os.path.join(self.repo, path)
            if not os.path.isfile(full):
                return None
            with open(full, "rb") as fh:
                data = fh.read()
        else:
            return tree_line_count(self.repo, self.change, path)
        return count_lines(data)

    def change_names(self):
        if self.change is None:
            out = git(self.repo, "ls-files", "--cached", "--others", "--exclude-standard")
        else:
            out = git(self.repo, "ls-tree", "-r", "--name-only", self.change)
        return out.stdout.splitlines()

    def line_count(self, path):
        if path not in self._lines:
            self._lines[path] = tree_line_count(self.repo, self.ref, path)
        return self._lines[path]


def check_citations(paths, corpus, base, out):
    """Each `path:line` in the files, checked against the base and the change.

    The one rule: a citation is an error only when it has a `/` and its line is
    in neither the base nor the change's own copy. That is the only case the
    script can be sure of. Every other finding, such as a bare name that
    matches no file or several, is a check (DECISIONS.md, "A citation fails only
    where it cannot be wrong").
    """
    for path in paths:
        for n, raw, fenced in markdown_lines(corpus.texts[path]):
            if fenced:  # quoted output, such as a stack trace, cites nothing
                continue
            for m in CITATION.finditer(raw):
                finding = judge_citation(m, base)
                if finding:
                    out.append(Finding(path, n, finding[0], "citation", f"{m.group(0)}: {finding[1]}"))


def judge_citation(m, base):
    """(severity, message) for one citation, or None when it holds."""
    cited, first, last = m.group(1), int(m.group(2)), m.group(3)
    cited = cited[2:] if cited.startswith("./") else cited
    line = int(last) if last else first
    ext = cited.rsplit(".", 1)[-1].lower()
    head = cited.split("/", 1)[0]
    if not ext[:1].isalpha() or ext in HOST_SUFFIXES and "/" not in cited:
        return None  # an address or a version, such as 0.0.0.0:8080
    if "/" in cited and re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", head) and \
            head.rsplit(".", 1)[-1] in HOST_SUFFIXES:
        return None  # an image, such as ghcr.io/acme/web.api:2
    if not base.ok:
        # No base to read, as in a repository with no commits yet.
        return "check", f"not checked; {base.ref} does not resolve"

    def holds(count):
        return isinstance(count, int) and 1 <= first and line <= count

    if "/" in cited:
        on_base, own = base.line_count(cited), base.change_line_count(cited)
        if holds(on_base) or (on_base == SUBMODULE and holds(own)):
            return None
        if SUBMODULE in (on_base, own):
            return "check", f"{cited} is inside a submodule, which this check cannot read"
        if holds(own):
            what = "adds" if on_base is None else "extends"
            return "check", f"{cited} is not like this on {base.ref}; this change {what} it"
        if on_base is None and own is None:
            return "error", f"{cited} does not exist on {base.ref} or in this change"
        if on_base is None:
            return "error", f"{cited} does not exist on {base.ref}, and has {own} lines in this change"
        extra = f", and {own} in this change" if own is not None and own != on_base else ""
        return "error", f"{cited} has {on_base} lines on {base.ref}{extra}"

    # A bare name: every file whose name, without its directory, is the cited
    # name, on the base or in the change.
    named = sorted({p for p in base.names() + base.change_names()
                    if p.rsplit("/", 1)[-1] == cited})
    if not named:
        return "check", f"no file named {cited} on {base.ref} or in this change"
    if len(named) > 1:
        return "check", f"{len(named)} files are named {cited}; cite it by its path"
    found = named[0]
    if holds(base.line_count(found)) or holds(base.change_line_count(found)):
        return None
    return "check", f"{found}, the one file named {cited}, has no line {line}"


# -- document-evolution text -----------------------------------------------------

# A change states what is true now; git and pull request comments hold how
# it got there (DECISIONS.md, "Decisions live in design.md"). Each entry is
# (name, pattern, what the phrase does, veto). A veto is matched against the
# text left of the hit and suppresses it, as the vetoes in the prose skill's
# scripts/comment_scan.py do for code comments. EVOLUTION_DETERMINER is the
# one veto: a determiner
# directly before the hit, as in `a previously rejected rule` (behaviour);
# in `the rule previously said` (history) nothing vetoes it. Behaviour text
# uses `supersedes`, `reversible` and `no longer` freely, so a verb here
# fires only beside a decision ("amends decision 4"), a person, a date, or a
# word naming the document's own drafts or rounds ("an earlier draft", "this
# push"). Three kinds of hit need no such word: `amendment`, `amended
# by/on/in`, and the bare adverbs `previously` and `originally`. Behaviour
# text in the measured changes did not use the first two; the adverbs are
# held back by the veto and by EVOLUTION_PARTICIPLE. DECISIONS.md, "Document-evolution text
# is an error", has what the patterns were measured on.

EVOLUTION_DETERMINER = re.compile(
    r"(?:\b(?:a|an|the|any|all|some|its|their|every|each|no|one)|'s|’s)[\s-]+$", re.I)
# A veto reads only this many characters left of the hit. Reading the whole
# text left of each hit took quadratic time on a long line with many hits.
EVOLUTION_LOOKBACK = 80
# Headings often capitalise every word ("#### Scenario: Claim confirmed"),
# so a capitalised word before a decision verb there is rarely a name. The
# person-decided pattern does not fire up to the end of this match.
EVOLUTION_HEADING = re.compile(r"[ \t]*#+[^:]*:?\s*")
# A past participle right after `previously` is almost always adjectival in a
# spec ("a candidate previously rejected is not proposed again").
EVOLUTION_PARTICIPLE = re.compile(r"\s+\w+(?:ed|en|wn)\b", re.I)
# The person-decided pattern takes any capitalised word before a decision
# verb as a name ("Adam decided"), unless the word is listed here. Names
# cannot be listed, since the check runs in any repository. The common words
# that can stand before such a verb without naming anyone can be: pronouns,
# determiners, conjunctions, prepositions and adverbs ("Also ruled out by
# scenarios"). A word left off still draws an error.
# Don't treat every capitalised word ending in -ly as an adverb instead of
# listing adverbs: that would skip names such as "Anatoly". A missed credit
# passes silently, while a person can keep a false error in the change's
# kept file (apply_kept).
# Each entry goes into the pattern unescaped, as a regex fragment.
EVOLUTION_NOT_NAMES = (
    # pronouns
    "I", "It", "He", "She", "They", "We", "You", "Me", "Him", "Us", "Them",
    "Who", "Whom", "Whoever", "Which", "What", "Whatever", "Nobody", "Somebody",
    "Someone", "Everyone", "Everybody", "Anyone", "Anybody", "Everything",
    "Something", "Nothing", "Anything", "Itself", "Themselves", "Others",
    # determiners and quantifiers ("An?" matches "A" and "An")
    "The", "An?", "This", "That", "These", "Those", "Its", "Their", "His", "Her",
    "Our", "My", "Your", "Each", "Every", "Both", "All", "None", "One", "Any",
    "Some", "No", "Neither", "Either", "Few", "Many", "Most", "Several", "Such",
    "Other", "Another", "Whose",
    # conjunctions, prepositions and question words
    "And", "But", "Or", "Nor", "Yet", "So", "If", "Unless", "Because", "Although",
    "Though", "As", "Since", "When", "Whenever", "Where", "While", "After",
    "Before", "Until", "Once", "Than", "Whether", "Why", "How",
    # adverbs
    "Also", "Then", "Later", "Earlier", "Still", "Never", "Only", "Just", "Even",
    "Again", "Instead", "Therefore", "Now", "Here", "There", "Already", "Soon",
    "First", "Next", "Last", "Often", "Always", "Sometimes", "Rarely", "Seldom",
    "Early", "Ever", "Together", "Otherwise", "Likewise", "Meanwhile", "Moreover",
    "Furthermore", "However", "Nevertheless", "Nonetheless", "Indeed", "Perhaps",
    "Maybe", "Rather", "Quite", "Almost", "Not", "Today", "Thereby", "Thus", "Hence",
    # common adverbs in -ly
    "Finally", "Eventually", "Initially", "Recently", "Currently", "Usually",
    "Normally", "Typically", "Generally", "Additionally", "Similarly",
    "Alternatively", "Consequently", "Accordingly", "Subsequently", "Ultimately",
    "Newly", "Fully", "Mostly", "Simply", "Merely", "Properly", "Partly",
    "Clearly", "Explicitly", "Implicitly", "Automatically",
)
_DATE = r"\d{4}-\d{2}-\d{2}"
_RULING = r"(?:decisions?|rulings?)"
_EARLIER = r"(?:(?:the|an?|its|this|that|their|#\d+['’]s|\w+['’]s)\s+)?" \
           r"(?:(?:earlier|previous|prior|original|first|old|later|last)\s+)?"
_RULED = (r"(?i:decided|approved|ruled|agreed|amended|reversed|narrowed|widened|"
          r"loosened|tightened|overruled|settled|chose|chosen|recorded)")

EVOLUTION_PATTERNS = [
    ("amended",
     re.compile(r"\b(?:amend(?:s|ed|ing)?|revers(?:es|ed|ing)|supersed(?:es|ed|ing)|"
                r"replac(?:es|ed|ing)|narrow(?:s|ed|ing)|widen(?:s|ed|ing)|"
                r"overrul(?:es|ed|ing)|revis(?:es|ed|ing)|withdr(?:aws|ew|awn)|"
                r"retract(?:s|ed|ing)?)\s+(?:by\s+|on\s+|in\s+)?" + _EARLIER + _RULING + r"\b"
                r"|\bamended\s+(?:by|on|in)\b|\bamendments?\b", re.I),
     "records how a decision was amended", None),
    ("attribution",
     re.compile(r"\(\s*@?[A-Z][\w.-]*,\s*(?:" + _DATE + r"|$)" +
                r"|\b" + _RULED + r"\s+by\s+@?[A-Z][a-z]\w*\b"
                r"|\b" + _RULED + r"\b[^.;]{0,40}?\bon\s+" + _DATE +
                r"|\b(?i:" + _RULING + r")\s+[\d, ]+(?:(?:and|to)\s+\d+\s+)?on\s+" + _DATE +
                r"|\b(?i:recorded)\s+(?:on\s+)?" + _DATE),
     "credits a decision to a person or a date", None),
    ("person-decided",
     re.compile(r"(?<![\w@])@?(?!(?:" + "|".join(EVOLUTION_NOT_NAMES) + r")\b)"
                r"[A-Z][a-z]+\s+(?:decided|ruled|approved|agreed|chose|confirmed|accepted|adopted|"
                r"narrowed|widened|amended|reversed|overruled|settled)\b"),
     "credits a decision to a person", EVOLUTION_DETERMINER),
    ("previously",
     re.compile(r"\b(?:previously|originally|formerly|hitherto)\b", re.I),
     "narrates an earlier state of the document", EVOLUTION_DETERMINER),
    ("earlier-draft",
     re.compile(r"\b(?:earlier|previous|prior|older|original|first|former)\s+"
                r"(?:drafts?|wording|phrasing)\b"
                r"|\b(?:earlier|previous|prior|older|original|first|former|last|next)\s+"
                r"(?:versions?|revisions?)\s+of\s+(?:this|the)\s+(?:change|spec|proposal|design|"
                r"document|requirement|rule|decision|section)\b"
                r"|\b(?:this|the\s+next|the\s+previous|the\s+last|a\s+later|an\s+earlier)\s+"
                r"revision\b"
                r"|\b(?:change|proposal|spec|design)['’]s\s+(?:next|previous|last|first)\s+"
                r"revision\b", re.I),
     "refers to another draft of the document", None),
    ("was-changed",
     re.compile(r"\b(?:the|this|that)\s+(?:decision|requirement|rule|scenario|section|wording|"
                r"text|entry|proposal|design|spec)\s+(?:was|were|has\s+been|had\s+been)\s+"
                r"(?:changed|amended|reversed|narrowed|widened|reworded|rewritten|revised|"
                r"dropped|tightened|loosened|relaxed)\b"
                r"|\b(?:it|this)\s+(?:was|has\s+been|had\s+been)\s+(?:amended|reworded|"
                r"rewritten|revised)\b", re.I),
     "narrates a change to the document", None),
    ("review-round",
     re.compile(r"\bthis\s+(?:push|round|review\s+round)\b"
                r"|\bsince\s+(?:the\s+(?:last|previous|first)\s+)?review\b"
                r"|\b(?:after|in|during|since)\s+(?:the\s+)?(?:first|second|third|last|"
                r"previous|latest|earlier)\s+(?:review|round)\b"
                r"|\b(?:first|second|third|fourth|fifth|last|latest|later|next|previous|earlier)"
                r"\s+(?:(?:to|and)\s+\w+\s+)?(?:consistency\s+reads?|review\s+rounds?)\b", re.I),
     "dates the text against a review round a later reader cannot see", None),
]

# Text quoted in backticks or double quotes is an example, not the document
# speaking: a spec about a checker quotes the phrases it checks for.
# Code spans are paired by a scan in evolution_mask, not by one regex. A
# regex such as (`+).*?\1 can start at the second backtick of a ``` run and
# pair it with a lone backtick later, and it backtracks in cubic time on a
# long run with no closer.
EVOLUTION_BACKTICKS = re.compile(r"`+")
EVOLUTION_QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")
# Masked text keeps its width, so positions hold, but is neither a space nor
# a word: a veto or a pattern never reads across it as if the quoted words
# were gone ("The `claim` previously held" keeps "The" away from the hit).
EVOLUTION_MASK = "\u2063"
EVOLUTION_QUOTE_MAX = 160


def evolution_mask(line: str) -> str:
    r"""line with its code spans and double-quoted text masked. As in
    CommonMark, a run of backticks opens a code span only when a later run
    of exactly its length closes it, and a run with no closer is literal
    text. Outside a span, a backslash makes the one backtick after it
    literal. For example, in \```x`` the first backtick is escaped, so the
    run of two after it opens a span, and the final run of two closes it.
    Inside a span a backslash is plain text, so a closer is never escaped.

    Each line is masked on its own. A code span wrapped across two lines is
    therefore read as prose, and can give a false error on the second
    line."""
    runs = [(m.start(), m.end()) for m in EVOLUTION_BACKTICKS.finditer(line)]
    by_length: dict[int, list[int]] = {}
    for i, (start, end) in enumerate(runs):
        by_length.setdefault(end - start, []).append(i)
    chars = list(line)
    i = 0
    while i < len(runs):
        start, end = runs[i]
        slashes = 0
        while start - slashes > 0 and line[start - slashes - 1] == "\\":
            slashes += 1
        if slashes % 2:
            start += 1  # the escaped backtick is literal
        later = by_length.get(end - start, [])
        k = bisect.bisect_right(later, i)
        if start == end or k == len(later):
            i += 1
            continue
        j = later[k]
        chars[start:runs[j][1]] = EVOLUTION_MASK * (runs[j][1] - start)
        i = j + 1
    masked = "".join(chars)
    return EVOLUTION_QUOTED.sub(lambda m: EVOLUTION_MASK * len(m.group(0)), masked)


def evolution_match(line: str) -> tuple[int, int, str] | None:
    """(start, end, what it does) of the first pattern that fires on one
    line of prose, quotes already masked, or None."""
    heading = EVOLUTION_HEADING.match(line) if line.lstrip().startswith("#") else None
    for name, pattern, why, veto in EVOLUTION_PATTERNS:
        for m in pattern.finditer(line):
            before = line[max(0, m.start() - EVOLUTION_LOOKBACK):m.start()]
            if veto is not None and veto.search(before):
                continue
            if name == "person-decided" and heading and m.start() <= heading.end():
                continue
            if m.group(0).lower() == "previously" and EVOLUTION_PARTICIPLE.match(line, m.end()):
                continue
            return m.start(), m.end(), why
    return None


def evolution_hits(text: str) -> list[tuple[int, str, str, str]]:
    """(line number, phrase, what it does, line) for each line of the
    markdown text that records how the document changed, outside code fences
    and quotes. One hit per line: the first pattern that fires."""
    hits: list[tuple[int, str, str, str]] = []
    for n, raw, fenced in markdown_lines(text):
        if fenced:
            continue
        # The mask keeps positions, so the phrase is read from the line as
        # written, quotes included.
        hit = evolution_match(evolution_mask(raw))
        if hit:
            hits.append((n, raw[hit[0]:hit[1]].strip(), hit[2], raw.strip()))
    return hits


def check_evolution(paths: list[str], corpus: Corpus, out: list[Finding]) -> None:
    """An error on each line of the change's files that records how the
    document got to its shape rather than what is true now. A person can
    keep a false one through the change's kept file (apply_kept)."""
    for path in paths:
        text: str = corpus.texts[path]
        for n, phrase, why, line in evolution_hits(text):
            quote = line if len(line) <= EVOLUTION_QUOTE_MAX \
                else line[:EVOLUTION_QUOTE_MAX - 1] + "…"
            f = Finding(path, n, "error", "evolution",
                        f'"{phrase}" {why}; state what holds now and leave the history '
                        f'to git: {quote}')
            f.quote = line
            out.append(f)


# -- kept evolution errors ---------------------------------------------------------

# A change's kept file, committed with it, holds the evolution errors a person
# chose to keep. Each entry quotes the flagged line's text rather than its
# number, so it survives edits elsewhere in the file and lapses only when the
# line itself changes. The quote ends at the first `» kept`, so a line whose
# text holds `» kept:` or `» kept (asked):` cannot be quoted.
KEPT_FILE = ".spec-check-kept"
KEPT_ENTRY = re.compile(r"^(?P<file>[^«]+?): «(?P<text>.+?)» kept(?P<asked> \(asked\))?:"
                        r"(?P<reason>.*)$")
KEPT_FORM = "`<file>: «<line text>» kept (asked): <reason>`"


def kept_text(text: str) -> str:
    """text with each run of whitespace made one space and the ends stripped:
    an entry matches a line whatever its spacing."""
    return " ".join(text.split())


def apply_kept(change: str, corpus: Corpus, own: list[Finding]) -> list[str]:
    """Read the change's kept file, if it has one, against own, the change's
    findings. Each entry clears every evolution error in its file whose line
    text equals its quote, after whitespace is normalised (kept_text); the
    cleared findings leave own. These add a `kept` finding and clear
    nothing:
    - an unreadable file, or an entry that is malformed, gives no reason or
      repeats an earlier entry: an error;
    - an entry that matches no evolution error, with or without `(asked)`:
      a check asking for its removal;
    - an entry that matches but lacks `(asked)`: an error carrying the
      text sign prints in its refusal (Finding.handback).
    Returns one report line per cleared finding,
    `<path>:<line>: kept (asked) [evolution] <reason>`, which check and
    sign print and count. `(asked)` is the agent's statement that a person
    approved the entry; nothing here can check it."""
    prefix = f"openspec/changes/{change}/"
    rel = prefix + KEPT_FILE
    full = os.path.join(corpus.root, *rel.split("/"))
    if not os.path.lexists(full):
        return []
    try:
        with open(full, encoding="utf-8") as f:
            # Split as markdown_lines splits a spec: at "\n" only, after a
            # leading byte-order mark is dropped. str.splitlines() would also
            # split at a form feed or a Unicode line separator, cutting an
            # entry that quotes a line holding one; a kept byte-order mark
            # would become part of the first entry's file name.
            lines = normalize_line_endings(f.read()).removeprefix("\ufeff").split("\n")
    except (OSError, UnicodeDecodeError) as e:
        own.append(Finding(rel, 0, "error", "kept", f"cannot read the kept file: {e}"))
        return []
    errors: dict[tuple[str, str], list[Finding]] = {}
    for f in own:
        if f.severity == "error" and f.kind == "evolution" and f.quote is not None:
            errors.setdefault((f.path[len(prefix):], kept_text(f.quote)), []).append(f)
    seen: dict[tuple[str, str], int] = {}
    cleared: list[tuple[Finding, str]] = []
    for n, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        m = KEPT_ENTRY.match(raw.strip())
        if not m:
            own.append(Finding(rel, n, "error", "kept", f"the entry is not {KEPT_FORM}"))
            continue
        name, text = m.group("file").strip(), kept_text(m.group("text"))
        key = (name, text)
        reason = m.group("reason").strip()
        matched = errors.get(key, [])
        if key in seen:
            own.append(Finding(rel, n, "error", "kept",
                               f"the entry quotes the same line of {name} as line {seen[key]}"))
            continue
        seen[key] = n
        if not reason:
            own.append(Finding(rel, n, "error", "kept", "the entry gives no reason"))
        elif not matched:
            # Checked before `(asked)`: an entry that keeps nothing is not
            # handed to a person to approve.
            own.append(Finding(rel, n, "check", "kept",
                               f"«{text}» matches no evolution error in {name}: the line "
                               f"changed or is gone, so remove the entry"))
        elif not m.group("asked"):
            f = Finding(rel, n, "error", "kept",
                        "the entry has no `(asked)`, so no person approved keeping the line")
            f.handback = "\n".join([f"{rel}:{n}: {name}: «{text}»"] +
                                   [f"    {e.path}:{e.line}: {e.message}" for e in matched] +
                                   [f"    reason: {reason}"])
            own.append(f)
        else:
            cleared += [(e, reason) for e in matched]
    gone = {id(e) for e, _ in cleared}
    own[:] = [f for f in own if id(f) not in gone]
    return [f"{e.path}:{e.line}: kept (asked) [evolution] {reason}"
            for e, reason in sorted(cleared, key=lambda c: (c[0].path, c[0].line))]


# -- decision records -------------------------------------------------------------

# What a requirement cannot hold lives in a decision record, one per
# capability: constraints and rejected alternatives that no test can check,
# and rationale longer than a requirement's one *because* sentence
# (DECISIONS.md, "Decision records per capability"). OpenSpec reads none of
# it: `validate`, `list`, `show` and `archive` all ignore a decisions.md,
# beside a spec or in a change (OpenSpecIgnoresDecisionRecordsTests pins
# that). So spec-check checks a record's form, gives the consistency read
# the records a change must agree with, and folds a change's record into
# the main one when the change archives.

CONFIG_FILE = "openspec/spec-check.yaml"
RECORDS_KEY = "decision-records"
CAPABILITY_SLOT = "<capability>"
DEFAULT_RECORD = f"openspec/specs/{CAPABILITY_SLOT}/decisions.md"
# A change's own record, relative to the change. Fixed: it sits beside the
# delta spec it goes with, wherever the main record is configured to be.
CHANGE_RECORD = "decisions.md"
CONFIG_LINE = re.compile(r"^(?P<key>[A-Za-z][\w-]*)[ \t]*:(?:[ \t]+(?P<value>.*?))?[ \t]*$")
# The key the decisions-first rule used, which no spec-check reads any more.
RETIRED_KEYS = {"decisions-first"}


def parse_config(text):
    """(record template, [(line, severity, message)]) from the text of
    openspec/spec-check.yaml. The file is a small subset of YAML: one
    `key: value` per line, `#` comments and blank lines. A template that is
    missing or unusable falls back to DEFAULT_RECORD, with an error for an
    unusable one."""
    template, problems, seen = DEFAULT_RECORD, [], set()
    for n, raw in enumerate(normalize_line_endings(text).removeprefix("\ufeff").split("\n"), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = CONFIG_LINE.match(line)
        if not m:
            problems.append((n, "error", f"not a `key: value` line spec-check reads: {line.strip()}"))
            continue
        key, value = m.group("key"), (m.group("value") or "")
        # A comment after the value, outside quotes.
        if value[:1] in ("'", '"'):
            close = value.find(value[0], 1)
            rest = value[close + 1:].strip() if close > 0 else "x"
            if close < 0 or (rest and not rest.startswith("#")):
                problems.append((n, "error", f"the value of {key} is not one quoted string"))
                continue
            value = value[1:close]
        else:
            value = re.sub(r"[ \t]+#.*$", "", value).strip()
        if key in RETIRED_KEYS:
            problems.append((n, "check", f"spec-check no longer reads {key}; delete the line"))
            continue
        if key != RECORDS_KEY:
            problems.append((n, "error", f"spec-check reads no key {key!r}; the one key is "
                                         f"{RECORDS_KEY}"))
            continue
        if key in seen:
            problems.append((n, "error", f"{key} is set twice"))
            continue
        seen.add(key)
        why = template_problem(value)
        if why:
            problems.append((n, "error", f"{key}: {why}; using {DEFAULT_RECORD}"))
        else:
            template = value
    return template, problems


def template_problem(value):
    """Why a decision-record template cannot be used, or None."""
    if not value:
        return "no path given"
    if value.count(CAPABILITY_SLOT) != 1:
        return f"the path must hold {CAPABILITY_SLOT} once: {value}"
    parts = value.split("/")
    if "\\" in value or value.startswith("/") or any(p in ("", ".", "..") for p in parts):
        return f"not a plain path relative to the repository: {value}"
    # Compared ignoring case, since a filesystem that ignores case (macOS's
    # default) treats Spec.md as spec.md and Changes/ as changes/.
    if parts[0] != "openspec" or len(parts) < 2 or parts[1].casefold() == "changes":
        return f"the path must be under openspec/, and not under openspec/changes/: {value}"
    if not value.endswith(".md") or parts[-1].casefold() == "spec.md":
        return f"the path must name a .md file other than spec.md: {value}"
    head, tail = value.split(CAPABILITY_SLOT)
    if not head.endswith("/") or not tail.startswith("/"):
        return (f"{CAPABILITY_SLOT} must be a folder of its own, with a fixed file name after it, "
                f"such as openspec/decisions/{CAPABILITY_SLOT}/decisions.md: {value}")
    return None


def read_config(root):
    """(record template, [Finding]) from the root's openspec/spec-check.yaml.
    No file means the default."""
    full = os.path.join(root, *CONFIG_FILE.split("/"))
    if not os.path.lexists(full):
        return DEFAULT_RECORD, []
    try:
        if os.path.islink(full) or not os.path.isfile(full):
            raise OSError("not a plain file")
        with open(full, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        return DEFAULT_RECORD, [Finding(CONFIG_FILE, 0, "error", "config",
                                        f"cannot read it ({e}); using {DEFAULT_RECORD}")]
    template, problems = parse_config(text)
    return template, [Finding(CONFIG_FILE, n, sev, "config", msg) for n, sev, msg in problems]


def record_path(template, cap):
    return template.replace(CAPABILITY_SLOT, cap)


def record_cap(template, rel):
    """The capability whose main record rel is under template, or None."""
    head, tail = template.split(CAPABILITY_SLOT)
    # A change's files are never main records, though a template such as
    # openspec/<capability>/decisions.md would otherwise match one.
    if rel.casefold().startswith("openspec/changes/"):
        return None
    if rel.startswith(head) and rel.endswith(tail) and len(rel) > len(head) + len(tail):
        cap = rel[len(head):len(rel) - len(tail)]
        if all(p not in ("", ".", "..") for p in cap.split("/")):
            return cap
    return None


def change_record_cap(rel):
    """The capability of a change's own record,
    openspec/changes/<change>/specs/<capability>/decisions.md, or None."""
    parts = rel.split("/")
    if len(parts) >= 6 and parts[:2] == ["openspec", "changes"] and parts[2] != "archive" \
            and parts[3] == "specs" and parts[-1] == CHANGE_RECORD:
        return "/".join(parts[4:-1])
    return None


RECORD_TITLE = re.compile(r"^#[ \t]+(?P<cap>.+?):[ \t]+constraints and rejected alternatives[ \t]*$",
                          re.I)
RECORD_SECTIONS = {"constraints": "Constraint", "rejected": "Rejected", "rationale": "Rationale",
                   "retired": None}
SECTION_OF = {"Constraint": "Constraints", "Rejected": "Rejected", "Rationale": "Rationale"}
RECORD_SECTION = re.compile(r"^##[ \t]+(?P<name>.*?)[ \t]*$")
RECORD_ENTRY = re.compile(r"^[-*][ \t]+\*\*(?P<kind>Constraint|Rejected|Rationale):[ \t]*(?P<title>.+?)\*\*[ \t]*$")
RECORD_PART = re.compile(r"^[ \t]+(?P<label>[A-Z][a-z]*(?: [a-z]+)?):(?:[ \t]+(?P<value>.*?))?[ \t]*$")
RECORD_PARTS = {
    "Constraint": ("Because", "Evidence", "Holds while", "Paths"),
    "Rejected": ("Facing", "Lost because", "Instead", "Paths"),
    # A Rationale entry's reasoning is the lines after its bold line, with
    # no label; any number of Evidence lines may follow it.
    "Rationale": ("Evidence",),
}
# Parts that end with a link: a URL, a markdown link, an issue or pull
# request (#12, owner/repo#12) or a commit.
LINKED_PARTS = ("Evidence", "Lost because")
LINK = re.compile(r"https?://\S+|\[[^\]\n]*\]\([^)\n]*\)|(?<![\w&])(?:[\w.-]+/[\w.-]+)?#\d+\b"
                  r"|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
ONE_SENTENCE_PARTS = ("Because", "Lost because")
PATH_GLOB = re.compile(r"[*?\[]")


class RecordEntry:
    def __init__(self, line, kind, title, section):
        self.line, self.kind, self.title, self.section = line, kind, title, section
        self.parts = {}     # label -> [line, value]
        self.lines = []     # the entry's lines as the file writes them
        self.reasoning = ""  # a Rationale entry's reasoning
        self.evidence = []  # a Rationale entry's Evidence lines, as [line, value]

    @property
    def key(self):
        return (self.kind, record_key(self.title))

    def paths(self):
        return [p for p in (split_paths(self.parts["Paths"][1]) if "Paths" in self.parts else [])]


def record_key(title):
    """A title as entries are matched by it: case, spacing, backticks and a
    closing period ignored."""
    return " ".join(title.replace("`", "").split()).rstrip(".").casefold()


def split_paths(value):
    return [p.strip().strip("`").strip() for p in value.split(",") if p.strip().strip("`").strip()]


class Record:
    """A decision record as spec-check reads it: its title's capability, its
    entries in order, and every way it departs from the form."""

    def __init__(self):
        self.cap = None
        self.title_line = 0
        self.title_raw = None
        self.entries = []   # RecordEntry, in file order
        self.problems = []  # (line, message): each an error


def parse_record(text, change=False):
    """A Record from a record's text. change: whether it is a change's own
    record, which may also hold a `## Retired` section naming main-record
    entries the change removes."""
    rec = Record()
    section, entry, part, seen_sections, after_blank = None, None, None, set(), False
    for n, raw, fenced in markdown_lines(text):
        if not raw.strip():
            part, after_blank = None, True
            continue
        blank_before, after_blank = after_blank, False
        if fenced:
            rec.problems.append((n, "a code fence is not part of a decision record"))
            continue
        if rec.title_line == 0:
            m = RECORD_TITLE.match(raw)
            rec.title_line = n
            if m:
                rec.cap = m.group("cap").strip().strip("`")
                rec.title_raw = raw.rstrip()
            else:
                rec.problems.append((n, "the first line must be "
                                        "`# <capability>: constraints and rejected alternatives`"))
            if m or raw.startswith("# "):
                continue
        m = RECORD_SECTION.match(raw)
        if m:
            name = m.group("name").casefold()
            entry = part = None
            if name not in RECORD_SECTIONS or (name == "retired" and not change):
                allowed = "`## Constraints`, `## Rejected`, `## Rationale`" + \
                    (" or `## Retired`" if change else "")
                rec.problems.append((n, f"a decision record has no section {raw.strip()!r}; "
                                        f"its sections are {allowed}"))
                section = "?"
                continue
            if name in seen_sections:
                rec.problems.append((n, f"`{raw.strip()}` appears twice"))
            seen_sections.add(name)
            section = name
            continue
        m = RECORD_ENTRY.match(raw)
        if m:
            part = None
            kind, title = m.group("kind"), m.group("title").strip()
            entry = RecordEntry(n, kind, title, section)
            entry.lines.append(raw.rstrip())
            if section is None:
                rec.problems.append((n, "an entry above `## Constraints`, `## Rejected` or "
                                        "`## Rationale`"))
            elif section != "?" and RECORD_SECTIONS[section] not in (None, kind):
                rec.problems.append((n, f"a {kind} entry under `## {section.title()}`; "
                                        f"it goes under `## {SECTION_OF[kind]}`"))
            if not title.rstrip("."):
                rec.problems.append((n, "the entry names nothing after its label"))
            rec.entries.append(entry)
            if kind == "Rationale" and section != "retired":
                part = "reasoning"
            continue
        m = RECORD_PART.match(raw)
        if m and entry is not None and entry.kind == "Rationale" and part == "reasoning" \
                and m.group("label") != "Evidence":
            m = None  # a reasoning line that starts with a word and a colon
        if entry is not None and m and m.group("label") in RECORD_PARTS["Constraint"] + \
                RECORD_PARTS["Rejected"]:
            label = m.group("label")
            entry.lines.append(raw.rstrip())
            if section == "retired":
                rec.problems.append((n, "an entry under `## Retired` is its bold line alone"))
            elif label not in RECORD_PARTS[entry.kind]:
                rec.problems.append((n, f"a {entry.kind} entry has no part {label!r}; its parts "
                                        f"are " + ", ".join(RECORD_PARTS[entry.kind])))
            elif entry.kind == "Rationale":
                entry.evidence.append([n, m.group("value") or ""])
            elif label in entry.parts:
                rec.problems.append((n, f"{label} appears twice in this entry"))
            else:
                entry.parts[label] = [n, m.group("value") or ""]
            part = label
            continue
        if entry is not None and part == "reasoning" and raw[:1] in (" ", "\t"):
            entry.lines.append(raw.rstrip())
            entry.reasoning = (entry.reasoning + " " + raw.strip()).strip()
            continue
        if entry is not None and part is not None and raw[:1] in (" ", "\t"):
            entry.lines.append(raw.rstrip())  # a part's value, wrapped
            if entry.kind == "Rationale" and part == "Evidence" and entry.evidence:
                entry.evidence[-1][1] = (entry.evidence[-1][1] + " " + raw.strip()).strip()
            elif part in entry.parts:
                entry.parts[part][1] = (entry.parts[part][1] + " " + raw.strip()).strip()
            continue
        indented = entry is not None and raw[:1] in (" ", "\t")
        if indented and section == "retired":
            rec.problems.append((n, "an entry under `## Retired` is its bold line alone"))
            continue
        rec.problems.append((n, "not part of an entry: a decision record holds only its title, "
                                "its sections and their entries" +
                                ("; a blank line ends the text before it, so this line belongs "
                                 "to nothing" if indented and blank_before else "")))
    if rec.title_line == 0:
        rec.problems.append((0, "the record is empty"))
    for e in rec.entries:
        if e.section == "retired":
            continue
        if e.kind == "Rationale":
            if not e.reasoning:
                rec.problems.append((e.line, "the Rationale entry has no reasoning: write it on "
                                             "the lines after its bold line"))
            for n, value in e.evidence:
                if not value.strip():
                    rec.problems.append((n, "Evidence: is empty"))
            continue
        for label in RECORD_PARTS[e.kind]:
            if label not in e.parts:
                rec.problems.append((e.line, f"the {e.kind} entry has no {label}: line"))
            elif not e.parts[label][1].strip():
                rec.problems.append((e.parts[label][0], f"{label}: is empty"))
    seen = {}
    for e in rec.entries:
        k = (e.section == "retired",) + e.key
        if k in seen:
            rec.problems.append((e.line, f"the same {e.kind} entry as line {seen[k]}"))
        else:
            seen[k] = e.line
        other = (not k[0],) + e.key
        if other in seen and seen[other] != e.line:
            rec.problems.append((e.line, f"keeps and retires the same {e.kind} entry, as line "
                                         f"{seen[other]} does; write it once"))
    return rec


def path_matches(pattern, path):
    """Whether a Paths item names path: the file itself, a directory above
    it, or a glob that matches it (`*` within a name, `**` across names)."""
    pattern = pattern.strip("/") if not PATH_GLOB.search(pattern) else pattern.rstrip("/")
    if not PATH_GLOB.search(pattern):
        return path == pattern or path.startswith(pattern + "/")
    rx = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif pattern[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif pattern[i] == "?":
            rx, i = rx + "[^/]", i + 1
        else:
            rx, i = rx + re.escape(pattern[i]), i + 1
    rx += "(?:/.*)?"  # a glob naming directories names what is under them
    return re.fullmatch(rx, path) is not None


def sentence_count(text):
    return len(sentences(text))


SENTENCE_END = re.compile(r"(?<=[.!?])[\"'’”)\]*_]*\s+(?=[A-Z0-9`*\"“(\[_])")
ABBREVIATION = re.compile(r"(?:\b(?:e\.g|i\.e|etc|vs|cf|approx|incl|resp|Fig|No))\.$", re.I)


def sentences(text):
    """The sentences of a run of text, split after `.`, `!` or `?` before a
    capital, a digit or opening markup; never after an abbreviation such as
    `e.g.`."""
    out = []
    for piece in SENTENCE_END.split(" ".join(text.split())):
        if out and ABBREVIATION.search(out[-1]):
            out[-1] += " " + piece
        elif piece:
            out.append(piece)
    return out


def check_record(rel, text, base, out, change=False, cap=None, requirements=None):
    """Format checks on one record. A path in Paths that the tree being
    checked lacks is an error in a main record and a check in a change's
    own, whose implementation may add it. requirements: the titles of the
    requirements a Rationale entry may name, or None when they cannot be
    told. Returns the Record."""
    rec = parse_record(text, change)
    for n, msg in rec.problems:
        out.append(Finding(rel, n, "error", "record", msg))
    if cap is not None and rec.cap is not None and rec.cap != cap:
        out.append(Finding(rel, rec.title_line, "error", "record",
                           f"the title names {rec.cap!r}, and the record is {cap!r}'s"))
    names = None
    allowed = None if requirements is None else {record_key(r) for r in requirements}
    for e in rec.entries:
        if e.section == "retired":
            continue
        linked = [(label, e.parts[label]) for label in LINKED_PARTS if label in e.parts] + \
            [("Evidence", ev) for ev in e.evidence]
        for label, (n, value) in linked:
            if value.strip() and not LINK.search(value):
                out.append(Finding(rel, n, "check", "record",
                                   f"{label}: links nothing; end it with a link to the failure, "
                                   "measurement or outside fact (a URL, #<issue> or a commit)"))
        if e.kind == "Rationale" and allowed is not None and record_key(e.title) not in allowed:
            out.append(Finding(rel, e.line, "error", "record",
                               f'Rationale: "{e.title.rstrip(".")}" names no requirement of '
                               f"{cap or rec.cap}; name " +
                               ("a requirement in force, or one this change adds or modifies,"
                                if change else "a requirement of its main spec") +
                               " by its title"))
        for label in ONE_SENTENCE_PARTS:
            if label in e.parts and sentence_count(e.parts[label][1]) > 1:
                out.append(Finding(rel, e.parts[label][0], "check", "record",
                                   f"{label}: holds {sentence_count(e.parts[label][1])} sentences; "
                                   "the form gives it one"))
        for p in e.paths():
            if names is None:
                names = tree_paths(base)
            if not any(path_matches(p, f) for f in names):
                sev = "check" if change else "error"
                why = ("this change's implementation may add it" if change
                       else "fix the path, or retire the entry")
                out.append(Finding(rel, e.parts["Paths"][0], sev, "record",
                                   f"Paths: {p} matches nothing in the tree; {why}"))
    return rec


def tree_paths(base):
    """Every file in the tree being checked: the working tree, a ref or the
    staged tree, as Base reads it. Directories are found from these."""
    if getattr(base, "_tree_paths", None) is None:
        base._tree_paths = [p for p in base.change_names() if p]
    return base._tree_paths


def change_records(corpus, change):
    """{capability: rel path} of the change's own records."""
    out = {}
    for rel in corpus.files_of(change):
        cap = change_record_cap(rel)
        if cap is not None:
            out[cap] = rel
    return out


def change_requirements(change, corpus, known, cap):
    """The titles a Rationale entry in change's own record for cap may name:
    the requirements of cap the change is checked against (known, as
    {(capability, title)}), with those the change adds, modifies or renames
    to, less those it removes or renames away. None when they cannot be
    told: known is None, or `openspec show` could not read the change's
    deltas or cap's main spec."""
    if known is None or corpus.missing or change in corpus.unread \
            or f"openspec/specs/{cap}/spec.md" in corpus.unread:
        return None
    names = {n for c, n in known if c == cap}
    for i in corpus.items.get(change, {}).get(cap, []):
        if i.kind in ("ADDED", "MODIFIED"):
            names.add(i.name)
        elif i.kind == "REMOVED":
            names.discard(i.name)
        elif i.kind == "RENAMED":
            names.discard(i.name)
            names.add(i.new)
    return names


def check_change_records(change, corpus, base, out, deps=(), known=None):
    """Format checks on a change's own records, and every refusal folding
    them into the main records at archive would meet (fold_change), with a
    stacked change's dependencies' records in deps folded in first. deps
    is None when the stack could not be built, and then only the format is
    checked. known: {(capability, title)} of the requirements the change
    is checked against, which a Rationale entry may name, or None."""
    _, refusals = fold_change(change, corpus, deps) if deps is not None else ({}, [])
    own = set(change_records(corpus, change).values())
    # A refusal over a dependency's record is reported at its `Builds on:`
    # line in the proposal, not at a file of this change's.
    out += [f for f in refusals if f.path not in own]
    for cap, rel in sorted(change_records(corpus, change).items()):
        rec = check_record(rel, corpus.texts[rel], base, out, change=True, cap=cap,
                           requirements=change_requirements(change, corpus, known, cap))
        # A refusal over the change record's own form repeats check_record;
        # one over the main record, or over the path the change record would
        # be folded into, does not.
        out += [f for f in refusals if f.path == rel
                and not (rec.problems and re.search(r"^cannot fold into \S+: line \d+:", f.message))]


def stack_records(stack, complete):
    """The dependencies whose own records a stacked change's records are
    folded onto, in order: those not merged, and merged ones the tree still
    holds open. () for an unstacked change, None when the stack could not
    be built."""
    if stack is None:
        return ()
    if not complete:
        return None
    return [d for d in stack.loaded if d.state != "MERGED" or d.pending]


def check_main_records(corpus, base, out):
    caps = {spec_cap(p) for p in corpus.specs}
    for rel in sorted(corpus.records):
        cap = record_cap(corpus.template, rel)
        spec = f"openspec/specs/{cap}/spec.md"
        # A Rationale entry's title is checked against its capability's
        # main spec, unless OpenSpec is unavailable or could not read it.
        names = None if corpus.missing or spec in corpus.unread else \
            {r.name for r in corpus.specs.get(spec, [])}
        check_record(rel, corpus.records[rel], base, out, cap=cap, requirements=names)
        if cap not in caps:
            out.append(Finding(rel, 0, "check", "record",
                               f"no spec in openspec/specs/ is {cap!r}, the capability this "
                               "record belongs to"))


# -- rationale in a requirement ---------------------------------------------------

# A requirement holds its rule: its SHALL statement plus at most one
# *because* sentence (DECISIONS.md, "Decision records per capability"). A
# sentence with no RFC 2119 keyword is not the statement, and only one may
# stand beside it. A list item continues the statement it hangs from, so
# only the sentences after an item's first count. A sentence that is only
# a link, or begins `Evidence:` or `See`, links evidence and is not counted.
RULE_WORD = re.compile(r"\b(SHALL|MUST|MAY|SHOULD|REQUIRED|RECOMMENDED|OPTIONAL)\b")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+")
EVIDENCE = re.compile(r"^(?:Evidence:|See\b)", re.I)


def rationale_sentences(body):
    """The sentences of a requirement's text that are neither its statement
    nor linked evidence."""
    units = []  # (is a list item, text)
    for para in re.split(r"\n[ \t]*\n", body):
        cur, item = "", False
        for line in para.split("\n"):
            if LIST_ITEM.match(line):
                if cur:
                    units.append((item, cur))
                cur, item = LIST_ITEM.sub("", line, count=1), True
                continue
            cur = (cur + " " + line.strip()).strip()
        if cur:
            units.append((item, cur))
    out = []
    for item, text in units:
        ss = sentences(text)
        for s in ss[1:] if item else ss:
            if RULE_WORD.search(s):
                continue
            if EVIDENCE.match(s) or not LINK.sub("", s).strip(" .,;:()"):
                continue
            out.append(s)
    return out


def check_rationale(reqs, corpus, out):
    """A check on each requirement whose text holds more than one sentence
    beside its statement."""
    for r in reqs:
        extra = rationale_sentences(r.body)
        if len(extra) > 1:
            cap = delta_rel(r.path) or spec_cap(r.path) or "<capability>"
            where = r.path.rsplit("/", 1)[0] + "/" + CHANGE_RECORD if delta_rel(r.path) \
                else record_path(corpus.template, cap)
            out.append(Finding(r.path, r.line, "check", "rationale",
                               f'requirement "{r.name}" holds {len(extra)} sentences beside its '
                               f'SHALL statement; keep the rule and at most one *because* '
                               f'sentence, and move the rest to {where}'))


# -- folding a change's records at archive --------------------------------------

def fold_record(cap, main_text, change_text):
    """(the main record's new text, or None to delete it; [message] of what
    stops the fold). Each entry of the change's record replaces the main
    entry of the same kind and title, in place, or is added at the end of
    its section; each entry under its `## Retired` removes one."""
    problems = []
    main = parse_record(main_text) if main_text is not None else None
    if main is not None and main.problems:
        problems += [f"the main record, line {n}: {m}" for n, m in main.problems]
    ours = parse_record(change_text, change=True)
    problems += [f"line {n}: {m}" for n, m in ours.problems]
    if problems:
        return None, problems
    entries = list(main.entries) if main else []
    for e in ours.entries:
        at = next((i for i, m in enumerate(entries) if m.key == e.key), None)
        if e.section == "retired":
            if at is None:
                problems.append(f"line {e.line}: retires a {e.kind} entry {e.title!r} that the "
                                "main record does not hold")
            else:
                del entries[at]
        elif at is None:
            entries.append(e)
        else:
            entries[at] = e
    if problems:
        return None, problems
    if not entries:
        return None, []
    title = main.title_raw if main and main.title_raw else \
        f"# {cap}: constraints and rejected alternatives"
    lines = [title]
    for kind, heading in SECTION_OF.items():
        of_kind = [e for e in entries if e.kind == kind]
        if of_kind:
            lines += ["", f"## {heading}"]
            for i, e in enumerate(of_kind):
                lines += ([""] if i else []) + e.lines
    return "\n".join(lines) + "\n", []


def fold_change(change, corpus, deps=()):
    """({main record rel: new text, or None to delete it}, [Finding]) for
    every record of the change, folded into the main records with each
    dependency's own record in deps folded in first, in that order, as a
    stacked change is checked against main plus its dependencies."""
    proposal = f"openspec/changes/{change}/proposal.md"
    base, findings, failed = fold_deps(corpus, deps, proposal)
    folded = {}
    for cap, rel in sorted(change_records(corpus, change).items()):
        main_rel = record_path(corpus.template, cap)
        if record_cap(corpus.template, main_rel) is None:
            findings.append(Finding(rel, 0, "error", "record",
                                    f"cannot fold into {main_rel}: the configured location puts "
                                    f"{cap}'s record where no main record can be"))
            continue
        if cap in failed:
            # Folded onto a base without the dependency's record, this
            # record would meet refusals that only follow from the
            # dependency record's failed fold.
            continue
        if main_rel not in corpus.records and os.path.lexists(os.path.join(corpus.root, *main_rel.split("/"))):
            # On a filesystem that ignores case, a location differing only in
            # case from a file there names that file, which the walk reads
            # under its own name; folding would write over it.
            findings.append(Finding(rel, 0, "error", "record",
                                    f"cannot fold into {main_rel}: a file is there that is not "
                                    "read as a record; check the case of the configured location"))
            continue
        text, problems = fold_record(cap, base.get(main_rel), corpus.texts[rel])
        for p in problems:
            findings.append(Finding(rel, 0, "error", "record", f"cannot fold into {main_rel}: {p}"))
        # A change record with no entry, for a capability with no main record,
        # changes nothing.
        if not problems and (text is not None or main_rel in base):
            folded[main_rel] = text
    return folded, findings


def fold_deps(corpus, deps, proposal):
    """({main record rel: text}, [Finding], {capability}): the main records
    with each dependency's own records in deps folded in, in order; a
    refusal for each record that cannot fold, at its `Builds on:` line in
    proposal; and the capabilities where one failed, which nothing after it
    folds onto, since every refusal it met would follow from the first."""
    base, findings, failed = dict(corpus.records), [], set()
    for dep in deps:
        for cap, text in sorted(dep.records.items()):
            if cap in failed:
                continue
            main_rel = record_path(corpus.template, cap)
            new, problems = fold_record(cap, base.get(main_rel), text)
            for p in problems:
                findings.append(Finding(proposal, dep.line, "error", "record",
                                        f"cannot fold {dep.label}'s record into {main_rel} "
                                        f"first: {p}"))
            if problems:
                failed.add(cap)
            else:
                if new is None:
                    base.pop(main_rel, None)
                else:
                    base[main_rel] = new
    return base, findings, failed


def changed_files(repo, base_ref, ref=None):
    """The files the branch changes against its merge base with base_ref:
    of ref, or of the working tree (staged, unstaged and untracked) with
    none. None when there is no merge base."""
    head = ref or "HEAD"
    out = git(repo, "merge-base", base_ref, head, check=False)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    mb = out.stdout.split()[0]
    if ref:
        names = git(repo, "diff", "--name-only", "--no-renames", mb, ref).stdout.splitlines()
    else:
        names = git(repo, "diff", "--name-only", "--no-renames", mb).stdout.splitlines()
        names += git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    return sorted(set(n for n in names if n))


REQUIREMENT_TITLE = re.compile(r"^###\s*Requirement:\s*(.+?)\s*$", re.I)


def delta_titles(corpus, change, cap):
    """The record keys of the requirement titles change's delta for cap
    names, read from its text: `records` reads no requirements with
    `openspec show`."""
    rel = change_deltas(corpus, change).get(cap)
    out = set()
    for _, raw, fenced in markdown_lines(corpus.texts.get(rel, "")) if rel else []:
        m = None if fenced else (REQUIREMENT_TITLE.match(raw) or RENAMED_FROM.match(raw)
                                 or RENAMED_TO.match(raw))
        if m:
            out.add(record_key(m.group(1)))
    return out


def records_for(change, corpus, changed, deps=()):
    """[(record, why)]: the main record of each capability the change
    touches; each dependency's own records in deps, as `<path> in
    <owner/repo>#<n>`, with the main record of each capability the
    dependency touches; then each main record one of whose Paths matches a
    changed file."""
    caps = set(change_deltas(corpus, change)) | set(change_records(corpus, change))
    out, seen = [], set()
    for cap in sorted(caps):
        rel = record_path(corpus.template, cap)
        if rel in corpus.records:
            # A Rationale entry for a requirement the change rewrites is
            # named, so the reader checks the reasoning still holds.
            touched = delta_titles(corpus, change, cap)
            covered = [e.title.rstrip(".") for e in parse_record(corpus.records[rel]).entries
                       if e.kind == "Rationale" and record_key(e.title) in touched]
            out.append((rel, f"the change touches {cap}" + "".join(
                f'; its Rationale for "{t}" covers a requirement the change changes'
                for t in covered)))
            seen.add(rel)
    for dep in deps:
        for cap in sorted(dep.records):
            out.append((f"{dep.dir}/specs/{cap}/{CHANGE_RECORD} in {dep.slug}#{dep.number}",
                        f"the record of {dep.label}, which this change builds on"))
        for cap in sorted(set(dep.records) | set(dep.deltas)):
            rel = record_path(corpus.template, cap)
            if rel in corpus.records and rel not in seen:
                out.append((rel, f"{dep.label}, which this change builds on, touches {cap}"))
                seen.add(rel)
    for rel in sorted(corpus.records):
        if rel in seen:
            continue
        rec = parse_record(corpus.records[rel])
        hit = next(((p, f) for e in rec.entries for p in e.paths() for f in changed or []
                    if path_matches(p, f)), None)
        if hit:
            out.append((rel, f"its Paths {hit[0]} matches {hit[1]}"))
    return out


# -- stacked changes -------------------------------------------------------------

# A change that applies on top of another open change says so in its
# proposal.md, one line per dependency, in the order they apply to main:
#
#     Builds on: seat-files (adamstallard/igor#171)
#
# It is then checked against the specs of the tree being checked, with each
# open dependency's delta archived into a copy of them and each merged one
# looked for in them (DECISIONS.md, "A stacked change declares what it builds
# on").
BUILDS_ON = re.compile(
    r"^Builds on:[ \t]+([A-Za-z0-9][A-Za-z0-9._-]*)[ \t]+"
    r"\(([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([0-9]+)\)[ \t]*$")
# Anything that looks like an attempt at the line, so a near miss is an error
# rather than a line silently ignored.
BUILDS_ON_LIKE = re.compile(r"^[\s>*_+-]*builds\s+on\b[\s*_]*:", re.I)
BUILDS_ON_SYNTAX = "Builds on: <change> (<owner>/<repo>#<number>)"
ARCHIVED = r"\d{4}-\d{2}-\d{2}-"   # OpenSpec archives a change as <date>-<name>

# The GitHub CLI. Tests point this at a fake, so that no test reaches GitHub.
GH = os.environ.get("SPEC_CHECK_GH") or "gh"
GH_TIMEOUT = 60
# The hint (add_hints) suggests a `Builds on:` line for a duplicate. It lists
# at most HINT_PRS open pull requests and reads at most HINT_READS of their
# delta files.
HINT_READS = 20
HINT_PRS = 100
# How many of the latest commits touching a dependency's delta the drift
# check reads for its earlier texts.
HISTORY_DEPTH = 50


class StackError(Exception):
    """A dependency that cannot be read or applied."""


class Dep:
    """One `Builds on:` line, and once loaded, the dependency's change."""

    def __init__(self, change, slug, number, line):
        self.change, self.slug, self.number, self.line = change, slug, int(number), line
        self.label = f"{change} ({slug}#{number})"
        self.declaration = f"Builds on: {self.label}"
        self.tree = None      # the commit its change was read from
        self.deltas = {}      # capability -> delta spec text
        self.builds_on = []   # (change, label) its own proposal declares
        self.own_deps = []    # the same, as Dep
        self.proposal = None  # its proposal.md text at that commit
        self.archive = None   # the pull request's own archive directory, when it archives the change
        self.dir = f"openspec/changes/{change}"  # where its change was read from at that commit
        self.state = None     # its pull request's state, as gh reports it: OPEN, MERGED or CLOSED
        # True when its pull request has merged but the tree being checked
        # still holds its change open, with these same deltas. The change is
        # not yet archived into the tree's specs, so it is applied like an
        # open one.
        self.pending = False
        self.items = None     # {capability: [Item]} of its deltas, as read_dep reads them
        self.records = {}     # capability -> its change's own decision record text
        self._history = {}
        self._history_items = {}

    def delta_path(self, cap):
        """Where its delta for cap is as an open change. The commits before
        an archive held it there, so history reads this path."""
        return f"openspec/changes/{self.change}/specs/{cap}/spec.md"

    def spec_path(self, cap):
        """Where its delta for cap is at the commit it was read from, which
        is what a citation of it names."""
        return f"{self.dir}/specs/{cap}/spec.md"

    def history(self, repo, cap):
        """The earlier texts of its delta for cap, newest first, from the
        HISTORY_DEPTH latest commits touching it in the history of the
        commit it was read from."""
        if cap not in self._history:
            path = self.delta_path(cap)
            shas = git(repo, "log", "--format=%H", f"--max-count={HISTORY_DEPTH}", self.tree,
                       "--", path, check=False).stdout.split()
            texts = []
            for sha in shas:
                text = show_text(repo, sha, path)
                if text is not None and text != self.deltas.get(cap):
                    texts.append(text)
            self._history[cap] = texts
        return self._history[cap]

    def history_items(self, repo, cap):
        """[[Item]] of each earlier text of its delta for cap (history), as
        `openspec show` reads it; a text it cannot read has none."""
        if cap not in self._history_items:
            found = []
            for text in self.history(repo, cap):
                items, _ = read_deltas({cap: (self.delta_path(cap), text)})
                found.append((items or {}).get(cap, []))
            self._history_items[cap] = found
        return self._history_items[cap]


def builds_on(text, path):
    """The `Builds on:` lines of one proposal, as ([Dep], [Finding])."""
    deps, problems = [], []
    for n, raw, fenced in markdown_lines(text):
        if fenced or not BUILDS_ON_LIKE.match(raw):
            continue
        m = BUILDS_ON.match(raw)
        if not m:
            problems.append(Finding(path, n, "error", "stack",
                                    f"cannot read this line; write it as `{BUILDS_ON_SYNTAX}`, "
                                    "at the start of a line, one dependency per line"))
            continue
        dep = Dep(m.group(1), m.group(2), m.group(3), n)
        if any(d.label == dep.label for d in deps):
            problems.append(Finding(path, n, "error", "stack", f"{dep.label} is listed twice"))
            continue
        deps.append(dep)
    return deps, problems


def gh(repo, *args):
    """gh's output, or raises StackError with what went wrong. Bytes that are
    not UTF-8, as in a file read through `gh api`, are replaced."""
    try:
        r = subprocess.run([GH, *args], cwd=repo, capture_output=True,
                           timeout=GH_TIMEOUT, env=dict(os.environ, GH_PROMPT_DISABLED="1"))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise StackError(f"gh could not run: {e}") from e
    out, err = (b.decode("utf-8", "replace") for b in (r.stdout, r.stderr))
    if r.returncode != 0:
        why = (err or out).strip().splitlines()
        raise StackError(f"`gh {' '.join(args[:2])}` failed: {why[-1] if why else f'exit {r.returncode}'}")
    return out


def remote_slug(url):
    """owner/repo from a remote URL, lowercased: https, ssh and scp-like
    forms, and a plain path ending in owner/repo(.git)."""
    u = url.strip().rstrip("/")
    u = u[:-4] if u.endswith(".git") else u
    parts = [p for p in re.split(r"[/:]", u) if p]
    return "/".join(parts[-2:]).lower() if len(parts) >= 2 else ""


def remote_for(repo, slug):
    """The git remote here that fetches from slug, preferring origin."""
    out = git(repo, "remote", "-v", check=False).stdout
    names = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] == "(fetch)" and remote_slug(fields[1]) == slug.lower():
            names.append(fields[0])
    return "origin" if "origin" in names else (names[0] if names else None)


def show_text(repo, treeish, path):
    """A file's text in a git tree, or None if it cannot be read. Bytes that
    are not UTF-8 are replaced, as Corpus reads files on disk."""
    out = git(repo, "show", f"{treeish}:{path}", check=False, binary=True)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def has_commit(repo, sha):
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def archives_of(names, change):
    """The archive directories among names that hold a change of this name,
    newest first."""
    return sorted((n for n in names if re.fullmatch(ARCHIVED + re.escape(change), n)), reverse=True)


def pr_info(repo, dep):
    """gh's view of the dependency's pull request. Raises StackError."""
    try:
        info = json.loads(gh(repo, "pr", "view", str(dep.number), "--repo", dep.slug, "--json",
                             "state,headRefName,headRefOid,isCrossRepository,files"))
    except ValueError as e:
        raise StackError(f"gh gave unreadable output for #{dep.number}: {e}") from e
    if not isinstance(info, dict):
        raise StackError(f"gh gave unreadable output for #{dep.number}")
    return info


# gh pr view lists at most this many of a pull request's files, and
# GitHub's files API at most PR_FILES_MAX. With a full list, a change the
# list does not show is not in the pull request.
GH_FILES = 100
PR_FILES_MAX = 3000


def change_in(paths, change):
    """(found, where) for a change in a pull request's file list: where is
    the archive directory the list adds, or None for its open directory.
    An archive comes first: a pull request that archives a change also
    lists the files it deleted from the open directory."""
    own = archives_of({p.split("/")[3] for p in paths
                       if p.startswith("openspec/changes/archive/") and p.count("/") >= 4}, change)
    if own:
        return True, own[0]
    return any(p.startswith(f"openspec/changes/{change}/") for p in paths), None


def own_change(repo, dep, info):
    """Where the pull request holds dep's change: None for its open
    directory, or the name of the archive directory the pull request itself
    adds. Read from the pull request's own file list, so an archive of the
    same name that its branch inherited from main never counts. gh pr view
    lists only the first GH_FILES files, so when its list has that many and
    shows neither directory, the full list is read from GitHub's files API.
    Raises StackError when the pull request holds no change of that name,
    or its full list cannot be read."""
    paths = [f.get("path", "") for f in info.get("files") or [] if isinstance(f, dict)]
    found, where = change_in(paths, dep.change)
    if not found and len(paths) >= GH_FILES:
        short = f"gh lists only the first {GH_FILES} of #{dep.number}'s files"
        try:
            paths = gh(repo, "api", "--paginate",
                       f"repos/{dep.slug}/pulls/{dep.number}/files?per_page=100",
                       "--jq", ".[].filename").splitlines()
        except StackError as e:
            raise StackError(f"{short}, and its full list cannot be read: {e}") from e
        found, where = change_in(paths, dep.change)
        if not found and len(paths) >= PR_FILES_MAX:
            raise StackError(f"{short}, and GitHub lists only the first {PR_FILES_MAX}, none of "
                             f"them under openspec/changes/{dep.change}/ or an archive of it")
    if not found:
        raise StackError(f"#{dep.number} holds no change {dep.change}: none of its files is under "
                         f"openspec/changes/{dep.change}/ or an archive of it")
    return where


def read_change(dep, read, prefix, paths, where):
    """Fills dep's deltas and proposal from the files of its change under
    prefix (paths), each read with read(path). Raises StackError."""
    depth = prefix.count("/")
    if not paths:
        raise StackError(f"#{dep.number}'s change {dep.change} is not at {prefix} {where}")
    for p in paths:
        parts = p.split("/")
        if len(parts) >= depth + 3 and parts[depth] == "specs" and parts[-1] == "spec.md":
            text = read(p)
            if text is None:
                raise StackError(f"cannot read {p} {where}")
            dep.deltas["/".join(parts[depth + 1:-1])] = text
        elif len(parts) >= depth + 3 and parts[depth] == "specs" and parts[-1] == CHANGE_RECORD:
            text = read(p)
            if text is None:
                raise StackError(f"cannot read {p} {where}")
            dep.records["/".join(parts[depth + 1:-1])] = text
        elif p == prefix + "proposal.md":
            dep.proposal = read(p)
            own, _ = builds_on(dep.proposal or "", p)
            dep.builds_on = [(d.change, d.label) for d in own]
            dep.own_deps = own


def fetch_head(repo, dep, info):
    """Its pull request's head commit, fetched first if it is not here.
    info is pr_info's result. Raises StackError."""
    remote = remote_for(repo, dep.slug)
    if remote is None:
        raise StackError(f"no git remote here fetches from {dep.slug}; a change can build only "
                         "on a change in its own repository")
    oid = info.get("headRefOid") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise StackError(f"gh gave no head commit for #{dep.number}")
    if not has_commit(repo, oid):
        # The branch by name, then GitHub's ref for the pull request, which
        # outlives a deleted branch and also serves one from a fork.
        refs = [] if info.get("isCrossRepository") else [f"refs/heads/{info.get('headRefName')}"]
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        for ref in refs + [f"refs/pull/{dep.number}/head"]:
            git(repo, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", remote, ref,
                check=False, env=env)
            if has_commit(repo, oid):
                break
        else:
            raise StackError(f"cannot fetch #{dep.number}'s head commit {oid[:12]} from {remote}")
    return oid


def load_dep(repo, dep, info):
    """Reads the dependency's change from its pull request's head commit
    (fetch_head): from its open directory, or from the archive directory
    the pull request adds (dep.archive). Raises StackError."""
    oid = dep.tree = fetch_head(repo, dep, info)
    dep.state = info.get("state")
    if dep.archive:
        dep.dir = f"openspec/changes/archive/{dep.archive}"
    prefix = dep.dir + "/"
    paths = git(repo, "ls-tree", "-r", "--name-only", oid, "--", prefix).stdout.splitlines()
    read_change(dep, lambda p: show_text(repo, oid, p), prefix, paths,
                f"in #{dep.number}'s head commit")


def plain(r):
    """A requirement's text, on one line, for quoting in a message."""
    return " ".join(t.strip() for _, t in r.text if t.strip())


# A stacked change's base is built by archiving its open dependencies with
# the OpenSpec CLI in a scratch copy of the specs (DECISIONS.md, "Why the real
# `openspec archive`, and only for open dependencies"), so the CLI is
# required for one.
TASKS_DONE = "## 1. Tasks\n\n- [x] 1.1 Done\n"


class Item:
    """One entry of a delta for one capability, as `openspec show` reads it
    (read_deltas): a rename, or a requirement it removes, modifies or adds.
    dep is the dependency it belongs to, or None for the stacked change's
    own."""

    def __init__(self, dep, cap, kind, name, new=None, req=None, line=None):
        self.dep, self.cap, self.kind, self.name, self.new = dep, cap, kind, name, new
        self.req, self.line = req, line

    @property
    def what(self):
        return {"RENAMED": f'renames "{self.name}" to "{self.new}" in {self.cap}',
                "REMOVED": f'removes "{self.name}" from {self.cap}',
                "MODIFIED": f'modifies "{self.name}" in {self.cap}',
                "ADDED": f'adds "{self.name}" to {self.cap}'}[self.kind]

    @property
    def missing(self):
        """What the tree lacks while this is not in it."""
        if self.kind == "RENAMED":
            return f'its rename of "{self.name}" to "{self.new}" in {self.cap}'
        if self.kind == "REMOVED":
            return f'its removal of "{self.name}" from {self.cap}'
        return f'"{self.name}" in {self.cap}'

    def text(self):
        """What its requirement says (Req.content), for comparing; None for
        a rename or removal."""
        return self.req.content if self.req is not None else None

    def written(self):
        """The item as a delta writes it: its lines as its file writes them
        (Req.block), or else rebuilt from what `openspec show` read."""
        if self.kind == "RENAMED":
            return f"- FROM: `### Requirement: {self.name}`\n- TO: `### Requirement: {self.new}`\n"
        if self.kind == "REMOVED":
            return f"### Requirement: {self.name}\n"
        if self.req.block:
            return "\n".join(self.req.block) + "\n"
        text, scenarios, _ = self.req.content
        parts = [f"### Requirement: {self.name}", "", text]
        for name, raw in scenarios:
            parts += ["", f"#### Scenario: {name}", "", raw]
        return "\n".join(parts) + "\n"


def items_of(dep):
    """dep's delta items, per capability, as read_dep read them."""
    return dep.items or {}


def delta_files(items):
    """{capability: delta spec text} holding items. When none of a
    capability's items was dropped, it gets its dependency's delta verbatim;
    otherwise its delta is rebuilt from the items kept (Item.written)."""
    by_cap = {}
    for i in items:
        by_cap.setdefault(i.cap, []).append(i)
    files = {}
    for cap, its in by_cap.items():
        dep = its[0].dep
        if len(its) == len(items_of(dep).get(cap, [])):
            files[cap] = dep.deltas[cap]
            continue
        parts = []
        for kind in ("RENAMED", "REMOVED", "MODIFIED", "ADDED"):
            written = [i.written() for i in its if i.kind == kind]
            if written:
                parts.append(f"## {kind} Requirements\n\n" + "\n".join(written))
        files[cap] = "\n".join(parts)
    return files


class Scratch:
    """openspec/specs and OpenSpec's config files, copied into a temporary
    directory under parent, where dependencies are archived with the real
    `openspec archive`. Never the tree being checked."""

    def __init__(self, src, parent, specs=True):
        self.parent = parent
        self.root = tempfile.mkdtemp(prefix="scratch-", dir=parent)
        self.warnings = []  # the warnings of the last archive that succeeded
        home, there = os.path.join(src, "openspec"), os.path.join(self.root, "openspec")
        os.makedirs(there)
        if not specs:
            os.makedirs(os.path.join(there, "specs"))
        for name in sorted(os.listdir(home)) if os.path.isdir(home) else []:
            p = os.path.join(home, name)
            if name == "specs" and os.path.isdir(p):
                if specs:
                    shutil.copytree(p, os.path.join(there, "specs"), ignore_dangling_symlinks=True)
            elif os.path.isfile(p):
                shutil.copyfile(p, os.path.join(there, name))

    def caps(self):
        """{capability: [Req]} of its specs, as `openspec show` reads them
        (read_spec). A spec it cannot read has none."""
        found, specs = {}, os.path.join(self.root, "openspec", "specs")
        for dirpath, dirnames, filenames in os.walk(specs):
            dirnames.sort()
            if "spec.md" in filenames and dirpath != specs:
                rel = os.path.relpath(os.path.join(dirpath, "spec.md"), self.root).replace(os.sep, "/")
                with open(os.path.join(dirpath, "spec.md"), encoding="utf-8", errors="replace") as fh:
                    found[spec_cap(rel)], _ = read_spec(rel, fh.read(), spec_cap(rel))
        return found

    def archive(self, name, items, proposal=None):
        """Archives items as change name with `openspec archive`. None when
        it succeeds; otherwise what the CLI said. A refused archive leaves the
        specs as they were, because `openspec archive` writes nothing until
        every capability's delta has applied."""
        said = self.archive_files(name, delta_files(items), proposal) if items else []
        return "; ".join(said) or None

    def archive_files(self, name, files, proposal=None):
        """Archives files ({capability: delta spec text}, written verbatim)
        as change name with `openspec archive`. [] when it succeeds;
        otherwise each message the CLI gave. A refused archive leaves the
        specs as they were, because `openspec archive` writes nothing until
        every capability's delta has applied."""
        if not files:
            return []
        home = os.path.join(self.root, "openspec", "changes", name)
        shutil.rmtree(home, ignore_errors=True)
        for cap, text in files.items():
            os.makedirs(os.path.join(home, "specs", cap))
            with open(os.path.join(home, "specs", cap, "spec.md"), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(home, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(proposal or "## Why\n\nA dependency of a stacked change.\n")
        with open(os.path.join(home, "tasks.md"), "w", encoding="utf-8") as fh:
            fh.write(TASKS_DONE)
        rc, data, tail = openspec_json(self.root, "archive", name, "--yes", "--no-validate", "--json")
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(os.path.join(self.root, "openspec", "changes", "archive"), ignore_errors=True)
        if rc == 0 and data is not None and isinstance(data.get("archive"), dict):
            said = data["archive"].get("warnings")
            self.warnings = [w for w in said if isinstance(w, str)] if isinstance(said, list) else []
            return []
        status = data.get("status") if data is not None else None
        said = [s["message"] for s in status or [] if isinstance(s, dict) and s.get("message")]
        return said or [tail]


def in_tree(dep):
    """Whether dep is judged as merged: merged, and not still open in the
    tree waiting to be archived."""
    return dep.state == "MERGED" and not dep.pending


def rename_ends(renames):
    """(the names one delta's renames end on, the names they move away
    from), reading the renames in order, as OpenSpec applies them. X to Y
    then Y to Z ends on Z and moves away from X and Y. A swap through a
    temporary name (X to T, Y to X, T to Y) ends on X and Y and moves away
    from T."""
    end, left = {}, set()
    for i in renames:
        end[i.new] = end.pop(i.name, i.name)
        left.add(i.name)
    return set(end), left - set(end)


def renames_done(renames, names):
    """Whether names (one capability's requirement names) already show one
    delta's renames, every pair of them, read in order. They are not done
    when they would still apply cleanly in order, each from a name that is
    there to one that is not. A swap through a temporary name applies
    cleanly to the names as they stand before the swap, although the names
    it ends on are already all there. Otherwise they are done when the names they end on
    are all there and the names they move away from are all absent
    (rename_ends)."""
    if not renames:
        return True
    now = set(names)
    for i in renames:
        if i.name not in now or i.new in now:
            break
        now.remove(i.name)
        now.add(i.new)
    else:
        return False
    end, left = rename_ends(renames)
    return end <= set(names) and not left & set(names)


class Decision:
    """How an open dependency's items stand against the specs so far:
    present (already there), kept (to archive), and third: additions the
    specs already hold with another text, a third version beside the
    tree's and the dependency's, as (item, the specs' requirement)."""

    def __init__(self):
        self.present, self.kept, self.third = [], [], []


def decide(dep, caps):
    """Splits an open dependency's items by whether caps ({capability:
    [Req]}, the specs so far) already shows them, by content (DECISIONS.md,
    "Whether the specs hold an open dependency is read from its content"):
    an addition is there when the requirement is, with the same text, and
    is the specs' own version when it is there with another text; a removal
    is there when the requirement is absent; a modification when the text
    is the same; one delta's renames when renames_done says so. Names match
    exactly, as OpenSpec matches them. The renames kept move their names
    before the other items are read, as the archive applies them first."""
    d = Decision()
    for cap, items in items_of(dep).items():
        names = {r.name: r for r in caps.get(cap, [])}
        renames = [i for i in items if i.kind == "RENAMED"]
        if renames_done(renames, names):
            d.present += renames
        else:
            d.kept += renames
            for i in renames:
                if i.name in names and i.new not in names:
                    names[i.new] = names.pop(i.name)
        for i in items:
            r = names.get(i.name)
            if i.kind == "REMOVED":
                (d.kept if r is not None else d.present).append(i)
                names.pop(i.name, None)
            elif r is not None and r.content == i.text():
                d.present.append(i)
            elif i.kind == "ADDED" and r is not None:
                d.third.append((i, r))
            elif i.kind in ("ADDED", "MODIFIED"):
                d.kept.append(i)
                # The dependency's version now stands under this name, so a later item
                # naming it is compared (r.content == i.text()) with this text, not the old one.
                names[i.name] = i.req
    return d


def not_shown(dep, caps, later):
    """What of a merged dependency's result caps (the tree being checked)
    does not show, as [what it lacks], judged by content and never by
    replaying it (DECISIONS.md, "A merged dependency is judged, never
    replayed"): each requirement it adds or modifies is there by name,
    with any text, since main may have reworded it since; each it removes
    is absent; and for its renames, read in order, the names they end on
    are there and the names they move away from are absent (rename_ends).
    later is the merged dependencies that come after it: a name one of them
    removes or renames away need not be there, and a name one of them adds
    or renames onto need not be absent."""
    gone, back = set(), set()
    for d in later:
        for cap, items in items_of(d).items():
            for i in items:
                if i.kind in ("REMOVED", "RENAMED"):
                    gone.add((cap, i.name))
                if i.kind in ("ADDED", "RENAMED"):
                    back.add((cap, i.new if i.kind == "RENAMED" else i.name))
    missing = []
    for cap, items in items_of(dep).items():
        names = {r.name for r in caps.get(cap, [])}

        def there(name):
            return name in names or (cap, name) in gone

        def absent(name):
            return name not in names or (cap, name) in back

        renames = [i for i in items if i.kind == "RENAMED"]
        end, left = rename_ends(renames)
        if not (all(there(n) for n in end) and all(absent(n) for n in left)):
            missing += [i.missing for i in renames]
        for i in items:
            if i.kind in ("ADDED", "MODIFIED") and not there(i.name):
                missing.append(i.missing)
            elif i.kind == "REMOVED" and not absent(i.name):
                missing.append(i.missing)
    return missing


def records_not_shown(dep, corpus, later=()):
    """What of a merged dependency's own decision records the tree's main
    records do not show, as [what it lacks], judged like not_shown by
    presence, never by text: each entry it adds or replaces is in the main
    record by kind and title; each it retires is absent. An entry a later
    merged dependency retires need not be there, and one a later one adds
    need not be absent."""
    gone, back = set(), set()
    for d in later:
        for cap, text in d.records.items():
            for e in parse_record(text, change=True).entries:
                (gone if e.section == "retired" else back).add((cap, e.key))
    missing = []
    for cap, text in sorted(dep.records.items()):
        main = corpus.records.get(record_path(corpus.template, cap))
        held = {e.key for e in parse_record(main).entries} if main is not None else set()
        for e in parse_record(text, change=True).entries:
            if e.section == "retired":
                if e.key in held and (cap, e.key) not in back:
                    missing.append(f"its retirement of {e.kind} {e.title!r} from {cap}'s record")
            elif e.key not in held and (cap, e.key) not in gone:
                missing.append(f"{e.kind} {e.title!r} in {cap}'s record")
    return missing


def record_entries(text):
    """A record's entries as records_held compares them: kind, title and
    lines, in no order, since a record may hold its sections in either order
    and the fold writes Constraints first. [] for no record."""
    if text is None:
        return []
    return sorted((e.key, tuple(line.rstrip() for line in e.lines)) for e in parse_record(text).entries)


def records_held(dep, corpus, base):
    """Whether an open dependency's own decision records are already held,
    by content, in base ({main record rel: text}: the main records with the
    records of the dependencies listed before it folded in), as decide
    judges its deltas against the specs so far: folding each one in changes
    nothing. A record that cannot fold is not held."""
    for cap, text in sorted(dep.records.items()):
        before = base.get(record_path(corpus.template, cap))
        after, problems = fold_record(cap, before, text)
        if problems or record_entries(after) != record_entries(before):
            return False
    return True


def merge_main(merged, missing, records_missing):
    """The error for a merged dependency whose result the branch lacks;
    merged is the words naming it, ending in "has merged"."""
    why = (f"{merged}, but this branch does not hold its result "
           f"({'; '.join(missing)}). Merge main into your branch")
    if records_missing:
        why += ("; if main already holds its change archived and still lacks those record "
                "entries, it was archived with plain `openspec archive`, which never folds "
                "decision records: fold its archived specs/<capability>/decisions.md into the main "
                "record by hand, or archive with `spec_check.py archive`")
    return why


class Stack:
    """The base a stacked change is checked against: the specs of the tree
    being checked, with each open dependency's change archived into a
    scratch copy of them by `openspec archive`, after dropping what they
    already show (DECISIONS.md, "Why the real `openspec archive`, and only
    for open dependencies")."""

    def __init__(self, corpus):
        self.caps = {}       # capability -> [Req]
        for path, reqs in corpus.specs.items():
            self.caps.setdefault(spec_cap(path), []).extend(reqs)
        self.gone = {}       # (capability, name) -> (Dep, what it did)
        self.deps = []       # the dependencies with at least one item archived
        self.loaded = []     # every listed dependency read, archived or already in the tree
        self.tags = []       # (capability, normalized text, Dep, its Req) for each text archived
        self.refusals = []   # [Finding] for the stacked change's own archive (archive_own)

    def find(self, cap, name):
        return next((r for r in self.caps.get(cap, []) if r.name == name), None)

    def base(self):
        return [r for reqs in self.caps.values() for r in reqs]

    def settle(self, scratch, corpus):
        """Reads the scratch specs as the base. A requirement holding a
        text a dependency archived is that dependency's, so messages cite
        its delta; one holding a text of the tree's specs is the tree's."""
        tree = {}
        for path, reqs in corpus.specs.items():
            for r in reqs:
                tree.setdefault((spec_cap(path), r.content), r)
        tags = {(cap, text): (dep, r) for cap, text, dep, r in self.tags}
        self.caps = {}
        for cap, reqs in scratch.caps().items():
            out = self.caps.setdefault(cap, [])
            for r in reqs:
                text = r.content
                if (cap, text) in tags:
                    dep, theirs = tags[(cap, text)]
                    out.append(theirs.restated(name=r.name, cap=cap, dep=dep))
                elif (cap, text) in tree:
                    out.append(tree[(cap, text)].restated(name=r.name, cap=cap))
                else:
                    out.append(r.restated(cap=cap))


def same_text(a, b):
    """Whether two texts match, ignoring line endings and surrounding blank
    space."""
    return "\n".join(a.splitlines()).strip() == "\n".join(b.splitlines()).strip()


def change_deltas(corpus, change):
    """{capability: rel path} of change's delta specs in corpus, as `openspec
    archive` finds them: openspec/changes/<change>/specs/<capability>/spec.md
    only, never a sibling such as v2-spec.md. Every reader of a stacked
    change's deltas goes through this."""
    return {delta_rel(rel): rel for rel in sorted(corpus.changes.get(change, {}))}


def pending_here(dep, corpus):
    """Whether the tree being checked holds dep's change open, under the
    same name, with the same deltas: merged, but not yet archived there."""
    mine = {cap: corpus.texts[rel] for cap, rel in change_deltas(corpus, dep.change).items()}
    if not dep.deltas:
        # A change holding only decision records: open here when every
        # record it adds is here too.
        mine = {cap: corpus.texts[rel] for cap, rel in change_records(corpus, dep.change).items()}
        return bool(dep.records) and set(mine) == set(dep.records) and all(
            same_text(mine[c], dep.records[c]) for c in mine)
    return set(mine) == set(dep.deltas) and all(
        same_text(mine[c], dep.deltas[c]) for c in mine)


def unreadable_delta(dep):
    """A capability whose delta has text but nothing `openspec show` reads,
    or None. Without this check, such a delta would be left out of the
    stack silently."""
    found = items_of(dep)
    return next((cap for cap, text in sorted(dep.deltas.items())
                 if text.strip() and not found.get(cap)), None)


def check_own(dep, listed, scratch, tree, unread, later, corpus, so_far):
    """Raises StackError when dep's proposal builds on a change that this
    change does not list before it (listed) and whose result the specs do
    not hold, or that cannot be read (unread: label -> StackError). A merged
    one must show in the tree being checked (not_shown, tree); an open or
    closed one must already be held, by content, in the specs so far
    (decide against scratch), or be listed before dep. later(dep) is the
    merged dependencies after dep. Nothing is applied."""
    for own in dep.own_deps:
        if own.change in listed:
            continue
        if own.label in unread:
            raise StackError(f"{dep.label} builds on {own.label}, which this change does not list "
                             f"before it and which cannot be read: {unread[own.label]}; add its "
                             f"`Builds on:` line before {dep.change}'s")
        if not own.deltas and not own.records:
            continue  # nothing of it could be missing
        cap = unreadable_delta(own)
        if cap:
            raise StackError(f"{dep.label} builds on {own.label}, whose delta for {cap} holds "
                             "nothing `openspec show` reads")
        if in_tree(own):
            records = records_not_shown(own, corpus, later(own))
            missing = not_shown(own, tree, later(own)) + records
            if missing:
                raise StackError(merge_main(f"{dep.label} builds on {own.label}, which has merged",
                                            missing, records))
        elif decide(own, scratch.caps()).kept or not records_held(own, corpus, so_far()):
            raise StackError(f"{dep.label} builds on {own.label}, which this change does not list "
                             f"before it, whose result the tree does not hold yet; add its `Builds on:` "
                             f"line before {dep.change}'s")


def rests_on(dep, deps):
    """The names of the changes dep builds on, directly or through another
    of deps."""
    by_name, seen, todo = {d.change: d for d in deps}, set(), [dep]
    while todo:
        for name, _ in todo.pop().builds_on:
            if name not in seen:
                seen.add(name)
                if name in by_name:
                    todo.append(by_name[name])
    return seen


def build_stack(change, corpus, repo, base):
    """(Stack or None, [Finding], complete) for one change. The stack is None
    only when the proposal has no `Builds on:` line at all, readable or not.

    Each dependency's deltas are read from its pull request's branch. In the
    order listed, a merged one is judged against the tree being checked
    (not_shown) and never applied: a check that its line is stale when the
    tree shows its result, an error saying to merge main when it does not.
    An open or closed one, or a merged one the tree still holds open, is
    compared with the scratch specs (decide): what they already show is
    dropped, and the rest is archived into them by one `openspec archive`
    run. All already there is a check that the `Builds on:` line is stale;
    some there and some not is a check naming each; a requirement it adds
    that the specs hold with another text is a drift check showing both. An
    unreadable dependency, a pull request that holds no change of that name,
    deltas the archive refuses, a missing openspec CLI, and a change the
    dependency builds on that this change does not list before it and whose
    result the specs lack (check_own) are errors. Once the stack is
    complete, the change itself is archived into a copy of the scratch
    specs (archive_own); its refusals wait in stack.refusals.

    complete is False when the stack is not what the change builds on: a
    line could not be read, the change names itself, the CLI is missing,
    or a dependency could not be read, judged or archived."""
    path = f"openspec/changes/{change}/proposal.md"
    deps, findings = builds_on(corpus.texts.get(path, ""), path)
    if not deps and not findings:
        return None, [], True
    stack, complete = Stack(corpus), not findings
    blocker = findings[0] if findings else None
    if deps and corpus.missing:
        findings.append(Finding(path, deps[0].line, "error", "stack",
                                f"not run: {corpus.missing}. A change with `Builds on:` lines is "
                                "checked against its dependencies archived by `openspec archive` "
                                "(npm install -g @fission-ai/openspec)"))
        findings[-1].message += ("; duplicate and drift checks did not run for this change, which "
                                 "is checked against main plus every dependency or not at all")
        return stack, findings, False
    with tempfile.TemporaryDirectory(prefix="spec-check-stack-") as tmp:
        scratch = Scratch(corpus.root, tmp)
        stack, findings, complete = stack_onto(change, corpus, repo, deps, findings, stack,
                                               complete, blocker, scratch)
        if complete:
            stack.settle(scratch, corpus)
            stack.refusals = archive_own(change, corpus, Scratch(scratch.root, tmp), stacked=True)
    return stack, findings, complete


# The refusals `openspec archive` gives for one delta spec (OpenSpec 1.15.0,
# dist/core/specs-apply.js, buildUpdatedSpec). Each names the capability;
# only REFUSAL also names one requirement of the delta.
REFUSAL = re.compile(r'^(\S+) (RENAMED|REMOVED|MODIFIED|ADDED) failed for header '
                     r'"### Requirement: (.*?)"(?: -|$)')
CAP_REFUSAL = re.compile(r"^(\S+?)(?::| validation failed -) ")
NO_SPEC = "target spec does not exist"
NO_OPERATIONS = re.compile(r"^Delta parsing found no operations for (\S+?)\. ")


def refusal_place(said, items):
    """(capability or None, line, requirement name or None) of one refusal
    of a change's own archive (archive_own). The line is that of the requirement
    the refusal is about, or 0 when it is about the capability's delta as a
    whole. A refusal that a capability has no spec names no requirement.
    It is placed at the delta's first rename or modification, since
    OpenSpec allows those only on a spec that exists. For a stacked change,
    check_drift reports an error at that line too, so run_checks drops the
    refusal there."""
    m = REFUSAL.match(said)
    if m:
        # The CLI quotes the name unescaped, and a name may itself hold
        # `" -`, so the regex's name can be cut short. The name is the
        # longest of the delta's own names that the message quotes in full.
        cap, kind, name = m.groups()
        hits = [(len(n), i.line, n) for i in items.get(cap, []) if i.kind == kind for n in (i.name, i.new)
                if n is not None and said.startswith(f'{cap} {kind} failed for header '
                                                     f'"### Requirement: {n}" - ')]
        if hits:
            _, line, name = max(hits, key=lambda h: h[0])
            return cap, line, name
        return cap, 0, name
    m = CAP_REFUSAL.match(said) or NO_OPERATIONS.match(said)
    cap = m.group(1) if m and m.group(1) in items else None
    if cap and NO_SPEC in said:
        first = next((i for i in items[cap] if i.kind in ("RENAMED", "MODIFIED")), None)
        if first:
            return cap, first.line, first.name
    return cap, 0, None


def archive_own(change, corpus, copy, stacked):
    """[Finding] for the change itself, archived verbatim with `openspec
    archive` into copy (DECISIONS.md, "Every change is archived into a
    scratch copy"). For a stacked change, copy is a copy of the scratch
    specs with its open dependencies archived; otherwise it is a copy of the
    tree's specs. Each refusal is an archive error in the delta file of the
    capability it names, at the requirement it is about or at line 0
    (refusal_place), quoting the CLI. copy is never the specs the stack's
    duplicate and drift checks read (Stack.caps), so those checks still read
    the specs before the change is applied.

    check_purposes runs before the archive: after it, every capability the
    change creates would already have a spec in copy. Its findings come
    after the refusals in the list returned."""
    rels = change_deltas(corpus, change)
    files = {cap: corpus.texts[rel] for cap, rel in rels.items()}
    proposal = corpus.texts.get(f"openspec/changes/{change}/proposal.md")
    purposes = check_purposes(change, corpus, rels, copy)
    out = []
    for said in copy.archive_files(change, files, proposal):
        cap, line, name = refusal_place(said, corpus.items.get(change, {}))
        rel = rels.get(cap) or next(iter(rels.values()))
        what = f'"{name}" in {cap}' if name else (cap or "this change")
        if stacked:
            why = (f"`openspec archive` refuses this change on top of what it builds on: "
                   f"{said.rstrip('.')}; write this change against what it builds on now")
        else:
            why = (f"`openspec archive` would refuse this change on the specs it is checked "
                   f"against: {said.rstrip('.')}")
        out.append(Finding(rel, line, "error", "archive", f"{what}: {why}"))
    return out + purposes


# `openspec archive` (OpenSpec 1.15.0 and 1.16.0, dist/core/specs-apply.js,
# buildUpdatedSpec) uses a delta's `## Purpose` only when the delta creates
# the spec, and ignores it for a spec that exists. When a new spec's delta
# has no Purpose, an empty one, or one that would leave the spec unreadable,
# archive writes "TBD - created by archiving change <change>. Update Purpose
# after archive.", and nobody goes back to replace it. OpenSpec builds that
# sentence from PURPOSE_PLACEHOLDER_PREFIX and PURPOSE_PLACEHOLDER_SUFFIX in
# dist/core/validation/constants.js.
#
# The three strings after MIN_PURPOSE_LENGTH are the starts of the archive
# warning and validate messages that check_purposes matches, as OpenSpec
# 1.16.0 prints them. If OpenSpec rewords one, check_purposes stops
# reporting that case, with no error of its own.
#
# OpenSpec's MIN_PURPOSE_LENGTH, from the same file. It appears only in
# messages: validate decides whether a Purpose is too brief.
MIN_PURPOSE_LENGTH = 50
UNREADABLE_PURPOSE = " - delta Purpose ignored (it would leave the new spec unreadable)"
PLACEHOLDER_PURPOSE = "Purpose section is still a placeholder"
BRIEF_PURPOSE = "Purpose section is too brief"


def mask_html_comments(text):
    """text with each `<!-- ... -->` blanked out, line breaks kept, as
    OpenSpec's maskHtmlComments does: `--!>` also closes a comment, and one
    never closed runs to the end of the text."""
    out, at = [], 0
    while True:
        start = text.find("<!--", at)
        if start < 0:
            return "".join(out) + text[at:]
        out.append(text[at:start])
        ends = [e + n for e, n in ((text.find("-->", start + 4), 3), (text.find("--!>", start + 4), 4))
                if e >= 0]
        end = min(ends) if ends else len(text)
        out.append(re.sub(r"[^\n]", " ", text[start:end]))
        at = end


# OpenSpec's fence rule for the Purpose (dist/core/parsers/code-fence.js):
# any indentation opens or closes a fence, with no list-item or blockquote
# handling. markdown_lines follows CommonMark instead, and must not be used
# to read a Purpose: the two disagree on a fence in a list item closed at
# column 0.
#
# Every pattern here uses JavaScript's character classes, not Python's:
# - JS_SPACE is JavaScript's \s, which is also what its trim() strips.
#   Python's \s and strip() differ: they leave out a byte-order mark, and
#   take in \x1c-\x1f and \x85.
# - JavaScript's `.` stops at U+2028 and U+2029, so `.*` is written
#   `[^\n\r\u2028\u2029]*`.
# - OpenSpec's case-insensitive /i folds ASCII letters only, so
#   OPENSPEC_PURPOSE spells out both cases. Python's re.I would also take
#   `ſ` for `s`.
JS_SPACE = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
            "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")
_S = f"[{JS_SPACE}]"
OPENSPEC_FENCE = re.compile(rf"^{_S}*(`{{3,}}|~{{3,}})([^\n\r\u2028\u2029]*)")
OPENSPEC_FENCE_CLOSE = re.compile(rf"^{_S}*(`{{3,}}|~{{3,}}){_S}*$")
OPENSPEC_PURPOSE = re.compile(rf"^##{_S}+[Pp][Uu][Rr][Pp][Oo][Ss][Ee]{_S}*$")
OPENSPEC_SECTION = re.compile(rf"^##{_S}+")


def openspec_fence_mask(lines):
    """For each line, whether OpenSpec's buildCodeFenceMask counts it inside
    a fenced block, fence lines included."""
    mask, active = [], None
    for line in lines:
        if active is None:
            m = OPENSPEC_FENCE.match(line)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                active = (m.group(1)[0], len(m.group(1)))
            mask.append(active is not None)
            continue
        mask.append(True)
        m = OPENSPEC_FENCE_CLOSE.match(line)
        if m and m.group(1)[0] == active[0] and len(m.group(1)) >= active[1]:
            active = None
    return mask


def delta_purpose(text):
    """(line of the `## Purpose` header or 0, its body or None) for one spec
    or delta, as OpenSpec's extractPurposeSection reads it.

    The header and the section's end are found with code fences and HTML
    comments blanked out, and so is whether the section holds any prose:
    with none, the body is None. The body returned is the section's lines
    as written, comments and fences included, so that two Purposes compare
    as archive compares them. A byte-order mark before `## Purpose` on the
    first line hides the header, as it does from OpenSpec."""
    original = normalize_line_endings(text).split("\n")
    masked = mask_html_comments("\n".join(original)).split("\n")
    fenced = openspec_fence_mask(masked)
    start = next((i for i, line in enumerate(masked)
                  if not fenced[i] and OPENSPEC_PURPOSE.match(line)), None)
    if start is None:
        return 0, None
    end = next((i for i in range(start + 1, len(masked))
                if not fenced[i] and OPENSPEC_SECTION.match(masked[i])), len(masked))
    if not "\n".join(masked[i] for i in range(start + 1, end) if not fenced[i]).strip(JS_SPACE):
        return start + 1, None
    return start + 1, "\n".join(original[start + 1:end]).strip(JS_SPACE)


def existing_purpose(path):
    """The Purpose body of the spec at path (delta_purpose), or None when it
    has none or cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return delta_purpose(fh.read())[1]
    except OSError:
        return None


def check_purposes(change, corpus, rels, copy):
    """[Finding] of kind `purpose` for change's delta specs ({capability:
    rel path}), judged against copy before the change is archived into it
    (DECISIONS.md, "A new capability's Purpose is checked in its delta").

    A capability is created by the change when copy has no spec for it. Its
    delta is an error unless `openspec archive` would carry its `## Purpose`
    into the new spec and `openspec validate --strict` would accept it
    there. Both are asked of the real CLI: the change's deltas for the new
    capabilities are archived into an empty specs directory, and the specs
    it writes are validated.

    When copy already has a spec for the capability, from main or a
    dependency, archive ignores the delta's Purpose. A check says so, unless
    the two bodies are the same after JavaScript's trim(): archive does not
    warn about that case."""
    out, created = [], {}
    for cap, rel in rels.items():
        line, body = delta_purpose(corpus.texts[rel])
        prose = body is not None
        target = os.path.join(copy.root, "openspec", "specs", cap, "spec.md")
        if not os.path.lexists(target):
            created[cap] = (rel, line, prose)
        elif prose and os.path.isfile(target) and body != existing_purpose(target):
            # A spec.md that is not a file makes archive refuse the change,
            # which archive_own reports; there is no Purpose to point to.
            where = (f"edit openspec/specs/{cap}/spec.md directly"
                     if f"openspec/specs/{cap}/spec.md" in corpus.specs
                     else "edit it in the change this one builds on that creates it")
            out.append(Finding(rel, line, "check", "purpose",
                               f"{cap} already exists, so `openspec archive` will ignore this "
                               f"`## Purpose`: it reads a delta's Purpose only when it creates "
                               f"the capability. To change {cap}'s Purpose, {where}"))
    if not created:
        return out
    judged = {}  # capability -> ([archive's warnings], [validate's messages on its Purpose])
    unread = {}  # capability -> what validate said when its output could not be read
    groups = [sorted(created)]
    while groups:
        caps = groups.pop()
        probe = Scratch(corpus.root, copy.parent, specs=False)
        if probe.archive_files(change, {cap: corpus.texts[created[cap][0]] for cap in caps}):
            # archive_own reports the refusal. It may be about one delta
            # only, so each capability is tried alone.
            if len(caps) > 1:
                groups += [[cap] for cap in caps]
            continue
        _, data, tail = openspec_json(probe.root, "validate", "--specs", "--strict", "--json",
                                      "--no-interactive")
        items = {i.get("id"): i for i in (data or {}).get("items", []) if isinstance(i, dict)}
        for cap in caps:
            if data is None:
                unread[cap] = tail
                continue
            issues = items.get(cap, {}).get("issues", [])
            judged[cap] = (probe.warnings, [str(i.get("message", "")) for i in issues
                                            if isinstance(i, dict) and i.get("path") == "overview"])
    for cap, tail in sorted(unread.items()):
        rel, line, _ = created[cap]
        out.append(Finding(rel, line, "check", "purpose",
                           f"{change} creates {cap}, and whether `openspec archive` would give it a "
                           f"real Purpose was not checked: `openspec validate` said {tail}"))
    placeholder = f'"TBD - created by archiving change {change}. Update Purpose after archive."'
    for cap, (warnings, issues) in sorted(judged.items()):
        rel, line, prose = created[cap]
        if any(w.startswith(cap + UNREADABLE_PURPOSE) for w in warnings):
            why = (f"`openspec archive` would not use its `## Purpose`, because carried into the "
                   f"new spec it would leave that spec unreadable (an HTML comment, a heading or "
                   f"an unclosed code fence in it), and would write the placeholder {placeholder} "
                   f"instead")
        elif any(m.startswith(PLACEHOLDER_PURPOSE) for m in issues):
            if not line:
                why = (f"its delta has no `## Purpose` that `openspec archive` reads, so archive would write the "
                       f"placeholder {placeholder} as its Purpose")
            elif not prose:
                why = (f"its `## Purpose` is empty, so `openspec archive` would write the placeholder "
                       f"{placeholder} as its Purpose")
            else:
                why = ("its `## Purpose` is a placeholder (a `TBD` or `TODO` marker, or the sentence "
                       "`openspec archive` writes), which archive would copy into the new spec")
        elif any(m.startswith(BRIEF_PURPOSE) for m in issues):
            why = (f"its `## Purpose` is under {MIN_PURPOSE_LENGTH} characters: `openspec archive` "
                   f"would carry it into the new spec, and `openspec validate --strict` would report "
                   f"it there as too brief")
        else:
            continue
        out.append(Finding(rel, line, "error", "purpose",
                           f"{change} creates {cap}, and {why}. Write what {cap} is for under "
                           f"`## Purpose` in this delta, in {MIN_PURPOSE_LENGTH} characters or "
                           f"more: archive takes a new capability's Purpose only from its delta"))
    return out


def archive_alone(change, corpus):
    """([Finding], status) for a change with no `Builds on:` line: the change
    alone, archived into a scratch copy of the tree's specs (archive_own).
    Without an OpenSpec CLI of OPENSPEC_SINCE or later, the status says the
    archive was not run."""
    if corpus.missing:
        return [], f"not run: {corpus.missing}"
    with tempfile.TemporaryDirectory(prefix="spec-check-archive-") as tmp:
        refusals = archive_own(change, corpus, Scratch(corpus.root, tmp), stacked=False)
    return refusals, "refused" if any(f.kind == "archive" for f in refusals) else "passed"


def read_dep(repo, dep, corpus):
    """Reads dep from its pull request (load_dep) and marks it pending when
    it has merged but the tree still holds its change open. Raises
    StackError."""
    dep.info = pr_info(repo, dep)
    dep.archive = own_change(repo, dep, dep.info)
    load_dep(repo, dep, dep.info)
    items, err = read_deltas({cap: (dep.spec_path(cap), text) for cap, text in dep.deltas.items()}, dep)
    if err:
        raise StackError(f"`openspec show` cannot read its deltas: {err}")
    dep.items = items
    dep.pending = dep.state == "MERGED" and pending_here(dep, corpus)


def stack_onto(change, corpus, repo, deps, findings, stack, complete, blocker, scratch):
    """build_stack's work, archiving into scratch."""
    path = f"openspec/changes/{change}/proposal.md"
    tree = {}  # the tree's requirements, by capability
    for p, reqs in corpus.specs.items():
        tree.setdefault(spec_cap(p), []).extend(reqs)
    listed = []

    def stop(dep, why, severity="error", kind="stack"):
        findings.append(Finding(path, dep.line, severity, kind, f"{dep.label}: {why}"))
        return findings[-1]

    # Every dependency, and every change one builds on, is read first: a
    # merged one is judged with the merged ones that come after it.
    unread, pool = {}, {}  # label -> StackError; change name -> Dep
    for dep in deps:
        if dep.change == change or not complete:
            continue
        try:
            read_dep(repo, dep, corpus)
            pool.setdefault(dep.change, dep)
        except StackError as e:
            unread[dep.label] = e
    readable = [d for d in deps if d.change != change and d.label not in unread]
    own_read = {}
    for dep in readable:
        for k, own in enumerate(dep.own_deps):
            same = next((d for d in readable if d.label == own.label), None) or own_read.get(own.label)
            if same is not None:
                dep.own_deps[k] = same
                continue
            if own.label in unread:
                continue
            try:
                read_dep(repo, own, corpus)
                own_read[own.label] = own
                pool.setdefault(own.change, own)
            except StackError as e:
                unread[own.label] = e

    def later(dep):
        """The merged dependencies after dep: listed after it, or built on
        it."""
        after = readable[readable.index(dep) + 1:] if dep in readable else []
        everyone = list(pool.values())
        return [d for d in everyone if d is not dep and in_tree(d)
                and (d in after or dep.change in rests_on(d, everyone))]

    def so_far():
        """The main records with the records of the open dependencies read
        so far folded in, as stack_records folds them."""
        return fold_deps(corpus, [x for x in stack.loaded if not in_tree(x)], path)[0]

    put = []  # (Dep, capability, normalized text, description) of each text archived
    for dep in deps:
        if dep.change == change:
            blocker = stop(dep, "a change cannot build on itself")
            complete = False
            listed.append(dep.change)
            continue
        if not complete:
            listed.append(dep.change)
            continue
        d = None
        try:
            if dep.label in unread:
                raise unread[dep.label]
            check_own(dep, listed, scratch, tree, unread, later, corpus, so_far)
            cap = unreadable_delta(dep)
            if cap:
                raise StackError(f"its delta for {cap} holds nothing `openspec show` reads")
            if in_tree(dep):
                records = records_not_shown(dep, corpus, later(dep))
                missing = not_shown(dep, tree, later(dep)) + records
                if missing:
                    raise StackError(merge_main(f"#{dep.number} has merged", missing, records))
            else:
                d = decide(dep, scratch.caps())
                refused = scratch.archive(dep.change, d.kept, dep.proposal)
                if refused:
                    why = ("its deltas do not fit the tree" +
                           (" (with the dependencies listed before it applied)" if stack.deps else "") +
                           f": `openspec archive` refused them: {refused}")
                    missing = [label for name, label in dep.builds_on if name not in listed]
                    if missing:
                        why += (f". {dep.label} builds on " + " and ".join(missing) +
                                ", which this change does not list before it: if those are not "
                                f"in the tree, add their `Builds on:` lines before {dep.change}'s")
                    raise StackError(why)
        except StackError as e:
            blocker = stop(dep, str(e))
            complete = False
            listed.append(dep.change)
            continue
        # Judged before it joins the dependencies listed so far.
        records_new = d is not None and not records_held(dep, corpus, so_far())
        stack.loaded.append(dep)
        for cap, items in items_of(dep).items():
            for i in items:
                if i.kind == "RENAMED" and i.name != i.new:
                    stack.gone[(cap, i.name)] = (dep, f'renames to "{i.new}"')
                elif i.kind == "REMOVED":
                    stack.gone[(cap, i.name)] = (dep, "removes")
        listed.append(dep.change)
        if d is None:
            stop(dep, f"#{dep.number} has merged, and its result is already in the tree "
                      f"checked here: remove the `{dep.declaration}` line", "check")
            continue
        if d.kept:
            stack.deps.append(dep)
        # When a dependency listed later overwrites a text an earlier one
        # archived, without building on that earlier one, the earlier
        # version drops out of the base with no error, so a check says so.
        # After each archive run, every text archived so far is looked for
        # in the scratch specs by text, not by name.
        now = scratch.caps()
        hits = {}  # earlier label -> (earlier Dep, [what it did])
        for entry in list(put):
            earlier, cap, text, what = entry
            if any(r.content == text for r in now.get(cap, [])):
                continue
            put.remove(entry)
            if earlier.change not in rests_on(dep, deps):
                hits.setdefault(earlier.label, (earlier, []))[1].append(what)
        for earlier, whats in hits.values():
            stop(earlier, f"{dep.label}, listed after {earlier.label}, sets again what {earlier.change} "
                          f"did ({'; '.join(whats)}) without building on it, so {earlier.change}'s version "
                          f"is left out: check that {dep.change}'s text includes what this change needs "
                          f"from {earlier.change}", "check")
        for i in d.kept:
            if i.kind in ("ADDED", "MODIFIED"):
                put.append((dep, i.cap, i.text(), i.what))
                stack.tags.append((i.cap, i.text(), dep, i.req))
        if dep.state == "CLOSED":
            stop(dep, f"#{dep.number} was closed without merging, so its change may never land", "check")
        for item, r in d.third:
            stop(dep, f'it adds "{item.name}" to {item.cap}, which the tree already holds with another '
                      f'text, so the tree\'s text is kept. The tree: "{plain(r)}" '
                      f'{dep.change}: "{plain(item.req)}"', "check", "drift")
        present = [i.what for i in d.present]
        applied = [i.what for i in d.kept]
        if (present or dep.records) and not applied and not d.third and not records_new:
            held = ("every delta and decision record it holds" if present and dep.records else
                    "every decision record it holds" if dep.records else "every delta it holds")
            stop(dep, f"{held} is already in the tree checked here, so main's specs "
                      f"hold its result: remove the `{dep.declaration}` line", "check")
        elif present:
            stop(dep, "some of its deltas are already in the tree and were skipped (" +
                      "; ".join(present) + ")" +
                      ("; the rest were applied (" + "; ".join(applied) + ")" if applied else "") +
                      ("; its decision records are not, and are folded in"
                       if records_new and not applied else "") +
                      ("; the tree holds its own version of " +
                       "; ".join(f'"{i.name}" in {i.cap}' for i, _ in d.third) + ", which was kept"
                       if d.third else ""),
                 "check")
    if not complete:
        blocker.message += ("; duplicate and drift checks did not run for this change, which "
                            "is checked against main plus every dependency or not at all")
    return stack, findings, complete


def stale_sentences(r, dep, cap, current, repo):
    """(line, sentence, [the dependency's new sentences]) for each sentence
    of r, the stacked change's version of a requirement, whose wording dep
    has changed. current is dep's requirement as its delta for cap states
    it now. Each earlier text of that requirement in dep's history is
    compared with current. A sentence of r counts when an earlier text has
    it, current does not, and current has a sentence that both the earlier
    text and r lack: r kept the old wording and may have missed the new
    one. A sentence the dependency only dropped is not counted, because a
    stack is often made by moving a rule out of the dependency into the
    stacked change. This is a heuristic, so check_drift reports it as a
    check for the author to judge."""
    now = {normalize(t): t for _, t in units(current)}
    have = {normalize(t) for _, t in units(r)}
    name = current.own or current.name  # its name in dep's delta
    stale = {}  # normalized sentence r kept -> sentences dep's current text added
    for items in dep.history_items(repo, cap):
        for item in items:
            old = item.req
            if old is None or old.name != name:
                continue
            then = {normalize(t) for _, t in units(old)}
            gained = [now[k] for k in now if k not in then and k not in have]
            if gained:
                for k in (then - set(now)) & have:
                    stale.setdefault(k, [])
                    stale[k] += [t for t in gained if t not in stale[k]]
    return [(line, t, stale[normalize(t)]) for line, t in units(r)
            if normalize(t) in stale and len(normalize(t).split()) >= DUPLICATE_MIN_WORDS]


def archived_req(stack, cap, name):
    """(Dep, its requirement) for the last dependency read whose delta for
    cap adds or modifies the requirement named name, or (None, None).
    check_drift calls it when the tree already holds a requirement as the
    dependency states it: no archive run put that text in, so stack.tags
    does not name the dependency for it.
    A requirement that no dependency touches is main's own and gets no
    drift check."""
    for dep in reversed(stack.loaded):
        r = next((i.req for i in items_of(dep).get(cap, [])
                  if i.req is not None and i.name == name), None)
        if r is not None:
            return dep, r
    return None, None


def check_drift(change, corpus, stack, repo, out):
    """Each requirement the stacked change modifies, removes or renames must
    be in main plus its dependencies; one that is not is an error. A
    modified one that keeps a sentence its dependency has since replaced
    gets a check, which shows both texts and never fails the run. The
    sentence check also covers a dependency whose result the tree already
    holds, found through archived_req."""
    for cap, rel in change_deltas(corpus, change).items():
        # Read as `openspec show` reads it (read_deltas). OpenSpec applies a
        # change's renames before its modifications, so a MODIFIED name may
        # be the new side of the change's own rename.
        mine = corpus.items.get(change, {}).get(cap, [])
        own_renames = {i.new: i.name for i in mine if i.kind == "RENAMED"}
        touched = [(i.line, i.name, "modifies" if i.kind == "MODIFIED" else "removes", i.req)
                   for i in mine if i.kind in ("MODIFIED", "REMOVED")]
        touched += [(i.line, i.name, "renames", None) for i in mine if i.kind == "RENAMED"]
        for line, name, verb, r in touched:
            renamed_from = own_renames.get(name) if verb == "modifies" else None
            current = stack.find(cap, renamed_from or name)
            if current is None and renamed_from:
                continue  # the change's "renames" entry in touched reports the old name
            if current is None:
                gone = stack.gone.get((cap, name))
                if gone:
                    why = f"which {gone[0].label} {gone[1]}"
                else:
                    defined = next((d for d in stack.deps if any(
                        o.name == name and o.kind != "RENAMED"
                        for its in d.history_items(repo, cap) for o in its)), None)
                    why = (f"which an earlier version of {defined.label} defined and its current one "
                           "does not" if defined else "which neither main nor its dependencies define")
                out.append(Finding(rel, line, "error", "drift", f'{verb} "{name}" in {cap}, {why}; '
                                   "write this change against what it builds on now"))
                continue
            if verb != "modifies":
                continue
            dep, theirs = (current.dep, current) if current.dep else archived_req(stack, cap, current.name)
            if dep is None:
                continue
            for line, kept, new in stale_sentences(r, dep, cap, theirs, repo):
                out.append(Finding(rel, line, "check", "drift",
                                   f'"{name}" keeps "{kept}", which an earlier text of '
                                   f"{dep.label} had and its current text does not. "
                                   f"Its current text has instead: " +
                                   " / ".join(f'"{t}"' for t in new) +
                                   f". If this change was written against the earlier text, "
                                   f"restate it from {dep.change}'s current text"))


def add_hints(repo, findings, declared):
    """Appends a suggested `Builds on:` line to each duplicate of a
    requirement under openspec/specs, when an open pull request in this
    repository has a change that removes or renames that requirement. With
    the line added, the requirement is gone from the base, so the duplicate
    is no longer reported. One `gh pr list` and at
    most HINT_READS file reads per run. Any failure leaves the plain error."""
    wanted = {}
    for f in findings:
        if f.retirable:
            for cap, name in f.retirable[1]:
                wanted.setdefault(cap, set()).add(name)
    if not wanted:
        return
    try:
        slug = json.loads(gh(repo, "repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
        prs = json.loads(gh(repo, "pr", "list", "--repo", slug, "--state", "open",
                            "--limit", str(HINT_PRS), "--json", "number,headRefOid,files"))
    except (StackError, ValueError, KeyError, TypeError):
        return
    reads = []
    for pr in prs if isinstance(prs, list) else []:
        for f in pr.get("files") or []:
            m = re.fullmatch(r"openspec/changes/([^/]+)/specs/(.+)/spec\.md", f.get("path", ""))
            if m and m.group(1) != "archive" and m.group(2) in wanted:
                reads.append((pr["number"], pr.get("headRefOid", ""), m.group(1), m.group(2), m.group(0)))
    retiring = {}  # (cap, name) -> [(change, number)]
    for number, oid, change, cap, path in reads[:HINT_READS]:
        try:
            text = gh(repo, "api", "-H", "Accept: application/vnd.github.raw",
                      f"repos/{slug}/contents/{urllib.parse.quote(path)}?ref={oid}")
        except StackError:
            continue
        for name in retired_names(cap, text) & wanted[cap]:
            retiring.setdefault((cap, name), []).append((change, number))
    for f in findings:
        if not f.retirable:
            continue
        change, matched = f.retirable
        lines = []
        for cap, name in matched:
            for dep_change, number in retiring.get((cap, name), []):
                line = f"Builds on: {dep_change} ({slug}#{number})"
                if dep_change != change and dep_change not in declared.get(change, ()) \
                        and line not in lines:
                    lines.append(line)
                    retired = name
        if lines:
            f.message += (f'. An open pull request removes or renames "{retired}": if this change '
                          "applies on top of it, add " + " or ".join(f"`{l}`" for l in lines) +
                          " to its proposal.md (spec-check's SKILL.md, \"Stacked changes\")")


# OpenSpec's note on a `### ` heading in a delta that is not a requirement
# header. spec-check adds what to write instead (stray_advice).
STRAY = re.compile(r'^Header "### (.*)" in (ADDED|MODIFIED) Requirements is not a '
                   r'"### Requirement:" header', re.I)


def run_validate(root, change, known=None):
    """`openspec validate --strict`, as findings plus a status line. Each
    issue is relayed with OpenSpec's own line and message. known is as
    stray_advice takes it."""
    missing = openspec_missing()
    if missing:
        return [], f"not run: {missing}"
    args = ["validate", "--strict", "--json", "--no-interactive"]
    args += [change, "--type", "change"] if change else ["--specs"]
    rc, data, tail = openspec_json(root, *args)
    if rc is None:
        return [], f"not run: {tail}"
    if data is None:
        return [], f"not read: exit {rc}, {tail}"
    found = []
    texts = {}  # rel path -> Lines of a delta with a stray heading, or None
    for item in data.get("items", []):
        for issue in item.get("issues", []):
            where, message = issue.get("path", ""), issue.get("message", "")
            if change:
                home = f"openspec/changes/{change}"
                p = f"{home}/specs/{where}" if where.endswith(".md") else home
            else:
                # In --specs mode the path is a place inside the spec, and the
                # item's id is the capability.
                p = f"openspec/specs/{item.get('id', '')}/spec.md"
            if where and not where.endswith(".md"):
                message = f"{message} (at {where})"
            stray = STRAY.match(message) if change and where.endswith(".md") else None
            if stray:
                if p not in texts:
                    try:
                        with open(os.path.join(root, p), encoding="utf-8", errors="replace") as fh:
                            texts[p] = Lines(fh.read())
                    except OSError:
                        texts[p] = None
                at = issue.get("line") if isinstance(issue.get("line"), int) else 0
                above = texts[p].requirement_above(at) if texts[p] else None
                message = (f"{message} " + stray_advice(where.rsplit("/", 1)[0], stray.group(1), known,
                                                        stray.group(2).upper(), above))
            # Under --strict a warning fails validation too; an INFO note never does.
            level = issue.get("level")
            sev = "error" if level == "ERROR" or (level == "WARNING" and rc != 0) else "check"
            line = issue.get("line") if where.endswith(".md") and isinstance(issue.get("line"), int) else 0
            found.append(Finding(p, line, sev, "openspec-validate", message))
    status = "passed" if rc == 0 else f"failed with {len(found)} issue(s)"
    return found, status


def default_base(repo):
    # origin/HEAD can name a branch a prune deleted, so every candidate must resolve.
    head = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    first = [head.stdout.strip()] if head.returncode == 0 and head.stdout.strip() else []
    for ref in first + ["origin/main", "origin/master", "main", "master"]:
        if git(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", check=False).returncode == 0:
            return ref
    return "HEAD"


def resolve_targets(corpus, targets):
    changes, specs = [], False
    for t in targets or sorted(corpus.changes):
        t = t.rstrip("/")
        if t in ("specs", "openspec/specs"):
            specs = True
            continue
        name = t.split("/")[-1] if t.startswith(("openspec/changes/", "./openspec/changes/")) else t
        if name not in corpus.changes:
            raise Fatal(f"no open change named {name!r} under openspec/changes/")
        changes.append(name)
    return changes, specs


def run_checks(root, repo, base_ref, targets, validate, base_required=False, change=None):
    corpus = Corpus(root)
    changes, specs = resolve_targets(corpus, targets)
    base = Base(repo, base_ref, change)
    if not base.ok and base_required:
        raise Fatal(f"the base {base_ref!r} does not resolve to a commit")
    findings, statuses, archives = list(corpus.config_findings), [], []
    stacks, declared, kept = [], {}, []
    main_names = {(spec_cap(p), r.name) for p, rs in corpus.specs.items() for r in rs}
    for change in changes:
        reqs = [r for rs in corpus.changes[change].values() for r in rs]
        own = []
        for cap, rel in change_deltas(corpus, change).items():
            check_renamed_blocks(rel, corpus.texts[rel], own)
        if change in corpus.unread:
            rel = next(iter(change_deltas(corpus, change).values()), f"openspec/changes/{change}")
            own.append(Finding(rel, 0, "error", "openspec-show",
                               f"`openspec show` cannot read this change's deltas: "
                               f"{corpus.unread[change]}"))
        check_scenarios(reqs, own)
        check_rationale(reqs, corpus, own)
        check_evolution(corpus.files_of(change), corpus, own)
        kept += apply_kept(change, corpus, own)
        stack, problems, complete = build_stack(change, corpus, repo, base)
        findings += own + problems
        # The specs the change is checked against, which run_validate uses
        # to advise on a heading it does not recognize, and which give the
        # requirements a Rationale entry may name: main's, or
        # main plus the dependencies once the stack is built; unknown when it
        # could not be.
        if stack is None:
            known = main_names
        elif complete:
            known = {(cap, r.name) for cap, rs in stack.caps.items() for r in rs}
        else:
            known = None
        check_change_records(change, corpus, base, findings, stack_records(stack, complete), known)
        if stack is None:
            check_duplicates(reqs, corpus, findings)
            refusals, archived = archive_alone(change, corpus)
            findings += refusals
        elif not complete:
            archived = f"not run: {corpus.missing}" if corpus.missing else "not run: see the stack error"
        else:
            deps = {d.change for d in stack.deps}
            declared[change] = deps
            if stack.deps:
                stacks.append((change, stack.deps))
            check_duplicates(reqs, corpus, findings, stack.base(), deps)
            check_drift(change, corpus, stack, repo, findings)
            # A requirement check_drift already reports is not reported twice.
            # A refusal at line 0 is about a whole delta file, never one
            # requirement, so nothing check_drift says covers it.
            said = {(f.path, f.line) for f in findings
                    if f.severity == "error" and f.kind == "drift"}
            findings += [f for f in stack.refusals if not f.line or (f.path, f.line) not in said]
            archived = "refused" if any(f.kind == "archive" for f in stack.refusals) else "passed"
        archives.append((change, archived))
        check_citations(corpus.files_of(change), corpus, base, findings)
        if validate:
            v, status = run_validate(root, change, known)
            findings += v
            statuses.append((change, status))
    if specs:
        reqs = [r for rs in corpus.specs.values() for r in rs]
        check_scenarios(reqs, findings)
        check_duplicates(reqs, corpus, findings)
        check_citations(sorted(p for p in corpus.texts if p.startswith("openspec/specs/")),
                        corpus, base, findings)
        check_main_records(corpus, base, findings)
        if validate:
            v, status = run_validate(root, None)
            findings += v
            statuses.append(("openspec/specs", status))
    # A main spec `openspec show` cannot read has no requirements to check,
    # and none for a change to be checked against.
    for rel, why in sorted(corpus.unread.items()):
        if rel.startswith("openspec/specs/"):
            findings.append(Finding(rel, 0, "error" if specs else "check", "openspec-show",
                                    f"`openspec show` cannot read this spec, so no requirement "
                                    f"check read it: {why}"))
    add_hints(repo, findings, declared)
    shown = f"not run: {corpus.missing}" if corpus.missing else "read"
    return changes, specs, findings, statuses, archives, stacks, shown, kept


def print_report(changes, specs, findings, statuses, archives, stacks, shown, kept, base_ref,
                 source, as_json):
    errors = sum(1 for f in findings if f.severity == "error")
    checks = len(findings) - errors
    if as_json:
        print(json.dumps({
            "source": source, "base": base_ref, "changes": changes, "specs": specs,
            "errors": errors, "checks": checks, "evolution_kept": len(kept),
            "findings": [f.as_dict() for f in findings],
            "kept": kept,
            "openspec_show": shown,
            "openspec_validate": {k: v for k, v in statuses},
            "openspec_archive": {k: v for k, v in archives},
            "builds_on": {c: [{"change": d.change, "repo": d.slug, "number": d.number,
                               "commit": d.tree} for d in deps] for c, deps in stacks},
        }, indent=2))
        return errors
    for f in findings:
        print(f.text())
    for line in kept:
        print(line)
    if findings or kept:
        print()
    for change, deps in stacks:
        print(f"{change} builds on " + ", then ".join(
            f"{d.change} ({d.slug}#{d.number} at {d.tree[:12]})" for d in deps) +
            "; checked against main plus " + ("it" if len(deps) == 1 else "them"))
    if shown != "read":
        print(f"requirement checks (openspec show): {shown}")
    for what, status in archives:
        print(f"openspec archive ({what}): {status}")
    for what, status in statuses:
        print(f"openspec validate --strict ({what}): {status}")
    if not statuses:
        print("openspec validate --strict: not run (--no-validate)")
    scope = ", ".join(changes + (["openspec/specs"] if specs else [])) or "nothing"
    count = f", {len(kept)} evolution kept" if kept else ""
    print(f"spec-check: {errors} error(s), {checks} check(s){count} in {scope}; "
          f"read from {source}; citations checked against {base_ref}")
    return errors


def cmd_check(args):
    repo = repo_root(args.repo)
    base_ref = args.base or default_base(repo)
    if args.ref:
        with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
            materialize(repo, args.ref, tmp)
            res = run_checks(tmp, repo, base_ref, args.targets, not args.no_validate,
                             bool(args.base), args.ref)
    else:
        res = run_checks(repo, repo, base_ref, args.targets, not args.no_validate,
                         bool(args.base))
    source = args.ref or "the working tree"
    errors = print_report(*res, base_ref, source, args.json)
    return 1 if errors else 0


def repo_root(path):
    out = git(path or ".", "rev-parse", "--show-toplevel", check=False)
    if out.returncode != 0:
        raise Fatal(f"not in a git repository: {os.path.abspath(path or '.')}")
    return out.stdout.strip()


# -- the trailer -----------------------------------------------------------

VALUE = re.compile(r"^✓ ([0-9a-f]{12})(?: |$)")


def is_skip(value):
    return value.strip()[:7].lower() == "skipped"


def staged_targets(repo):
    out = git(repo, "diff", "--cached", "--name-only", "--no-renames", "--", ":(top)openspec")
    paths = out.stdout.splitlines()
    changes, specs = set(), False
    for p in paths:
        parts = p.split("/")
        if parts[1:2] == ["specs"]:
            specs = True
        elif parts[1:2] == ["changes"] and len(parts) > 3 and parts[2] != "archive":
            changes.add(parts[2])
    return paths, sorted(changes), specs


# -- rounds: where the last consistency read was ---------------------------
#
# A consistency read runs once per review round, before the hand-back to a
# person that ends it (DECISIONS.md, "One consistency read per round"); a push
# ends nothing. handback.py, the hand-back hook, judges a hand-back with
# unread_at: it blocks one that names its pull request, and takes back an
# allowlisted one after the call, while a change is unread. The read's
# record is the
# Spec-check: trailer of the round's last commit:
# `read by a fresh subagent: <change>, <change>; ...` names the changes it
# read, at that commit's tree. A commit inside a round says `read deferred to
# the round's end`. A value written before this rule existed, `read by a
# fresh subagent; ...` with no names, read every change its commit touched.

READ_FIELD = re.compile(r"; read by (?:a fresh subagent|its author, no subagent)(?:: ([^;]*))?;")
DEFERRED = "read deferred to the round's end"
NO_READ_DUE = "no read due"
# How many commits of history are searched for a change's last read. A read
# older than this is not found, so the change counts as never read and is
# due again.
READ_HISTORY = 1000


def touched_changes(repo, sha):
    """The open changes one commit changes a file of: against its first parent,
    so a merge counts what it brought in; a root commit, against nothing."""
    parent = git(repo, "rev-parse", "-q", "--verify", f"{sha}^1", check=False)
    against = [parent.stdout.strip(), sha] if parent.returncode == 0 else ["--root", sha]
    out = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", *against,
              "--", ":(top)openspec/changes/", check=False).stdout.splitlines()
    return {p.split("/")[2] for p in out if p.count("/") >= 3 and p.split("/")[2] != "archive"}


def read_record(repo, sha, tree, value):
    """The changes covered by the consistency read that a trailer value
    records, or None when it records no read. A value not bound to its commit's tree
    records nothing."""
    m = VALUE.match(value.strip())
    if not m or not tree.startswith(m.group(1)):
        return None
    r = READ_FIELD.search(value)
    if not r:
        return None
    if r.group(1) is None:
        return touched_changes(repo, sha)
    return {c.strip() for c in r.group(1).split(",") if c.strip()}


def last_reads(repo, head, names):
    """{change: (commit, tree)}: for each change in names, the newest commit
    in head's history, within READ_HISTORY commits, whose Spec-check:
    trailer records a read of it. A change with no such commit is left out."""
    want, found = set(names), {}
    if not want:
        return found
    out = git(repo, "log", "--topo-order", f"--max-count={READ_HISTORY}",
              "--format=%H%x00%T%x00%(trailers:key=Spec-check,valueonly,separator=%x1f)%x1e",
              head, "--", check=False)
    if out.returncode != 0:
        return found
    for rec in out.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, tree, values = (rec.split("\x00", 2) + ["", ""])[:3]
        for value in values.split("\x1f"):
            covered = read_record(repo, sha, tree, value) if value.strip() else None
            for c in sorted((covered or set()) & want - set(found)):
                found[c] = (sha, tree)
        if len(found) == len(want):
            break
    return found


def blob_ids(repo, treeish, prefix):
    """{path: blob id} of every file under prefix in a git tree."""
    out = git(repo, "ls-tree", "-r", treeish, "--", prefix, check=False)
    ids = {}
    for line in out.stdout.splitlines() if out.returncode == 0 else []:
        meta, _, path = line.partition("\t")
        ids[path] = meta.split()[2]
    return ids


def merge_base_tree(repo, head, base_ref):
    """The tree of head's merge base with base_ref, or None."""
    out = git(repo, "merge-base", head, base_ref, check=False)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return git(repo, "rev-parse", f"{out.stdout.split()[0]}^{{tree}}").stdout.strip()


def openspec_links(where, treeish=None):
    """Every symlink in the tree being judged that is openspec or under it,
    sorted (DECISIONS.md, "No symlink under openspec/"). With treeish, from
    git's modes in that tree of the repository at where; without, from the
    files at where, as a checkout or a tree written out from git."""
    if treeish is not None:
        out = git(where, "ls-tree", "-r", "-z", treeish, "--", "openspec", check=False).stdout
        return sorted(e.split("\t", 1)[1] for e in out.split("\0") if e.startswith("120000 "))
    base = os.path.join(where, "openspec")
    if os.path.islink(base):
        return ["openspec"]
    found = []
    for dirpath, dirnames, filenames in os.walk(base):  # never follows a link
        for name in dirnames + filenames:
            if os.path.islink(os.path.join(dirpath, name)):
                found.append(os.path.relpath(os.path.join(dirpath, name), where).replace(os.sep, "/"))
    return sorted(found)


def links_problem(links):
    return (f"spec-check doesn't support symlinks under openspec/: {', '.join(links)}; "
            "replace each with a real folder or file")


def refuse_links(links):
    """Raises Fatal naming each symlink under openspec/ in links."""
    if links:
        raise Fatal(links_problem(links))


def due_reads(repo, head, base_ref, names, files_now):
    """[(change, last read or None)] for each change in names that the branch
    adds or edits and that differs from its last read. A change the branch
    leaves as it was at the merge base of head and base_ref is not due; with
    no merge base (or base_ref HEAD), every change counts as the branch's.
    files_now(prefix) gives {path: blob id} of the state being judged."""
    reads = last_reads(repo, head, names)
    start = None if base_ref == "HEAD" else merge_base_tree(repo, head, base_ref)
    due = []
    for c in sorted(names):
        prefix = f"openspec/changes/{c}/"
        now = files_now(prefix)
        if start is not None and blob_ids(repo, start, prefix) == now:
            continue
        since = reads.get(c)
        if since is None or blob_ids(repo, since[1], prefix) != now:
            due.append((c, since))
    return due


def open_changes(repo, treeish):
    """The open changes in a git tree: openspec/changes/<name>/, not archive."""
    return {p.split("/")[2] for p in blob_ids(repo, treeish, "openspec/changes/")
            if p.count("/") >= 3 and p.split("/")[2] != "archive"}


def unread_at(repo, commit, base_ref):
    """The due changes at a commit: what handing it back would leave unread.
    Each is an open change there that the branch adds or edits, against its
    merge base with base_ref, and that differs from its last read in the
    commit's own history."""
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    refuse_links(openspec_links(repo, tree))
    return [c for c, _ in due_reads(repo, commit, base_ref, open_changes(repo, tree),
                                    lambda prefix: blob_ids(repo, tree, prefix))]


def current_branch(repo):
    """HEAD's branch name, or None when HEAD is detached."""
    # Not --short, which says heads/<name> when a tag has the same name.
    ref = git(repo, "symbolic-ref", "-q", "HEAD", check=False).stdout.strip()
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None


def branch_of(repo, ref):
    """The branch a ref names: <b> for refs/heads/<b>, or for a remote's copy
    of it, refs/remotes/<remote>/<b>; None for anything else."""
    full = ref if ref.startswith("refs/") else git(
        repo, "rev-parse", "--symbolic-full-name", ref, check=False).stdout.strip()
    if full.startswith("refs/heads/"):
        return full[len("refs/heads/"):]
    for r in git(repo, "remote", check=False).stdout.split():
        if full.startswith(f"refs/remotes/{r}/"):
            return full[len(f"refs/remotes/{r}/"):]
    return None


def on_base_branch(repo, base_ref):
    """Whether HEAD's branch is base_ref's branch: base_ref names it, or names
    a remote's copy of it."""
    branch = current_branch(repo)
    return branch is not None and base_ref != "HEAD" and branch_of(repo, base_ref) == branch


def cmd_sign(args):
    repo = repo_root(args.repo)
    if args.read == "deferred" and (args.amended or args.open):
        print("spec-check sign: --amended and --open count what a read led to; a deferred read "
              "has none", file=sys.stderr)
        return 1
    paths, changes, specs = staged_targets(repo)
    tree = git(repo, "write-tree").stdout.strip()
    refuse_links(openspec_links(repo, tree))
    base_ref = args.base or default_base(repo)
    # On the base branch itself the merge base would be HEAD, leaving nothing
    # due. Base "HEAD" turns that filter off, so every open change counts as
    # the branch's own.
    due_base = "HEAD" if on_base_branch(repo, base_ref) else base_ref
    head = "HEAD" if git(repo, "rev-parse", "-q", "--verify", "HEAD", check=False).returncode == 0 \
        else None
    open_now = open_changes(repo, tree)
    due = due_reads(repo, head, due_base, open_now, lambda prefix: blob_ids(repo, tree, prefix)) \
        if head else [(c, None) for c in sorted(open_now)]
    reading = args.read in ("subagent", "self")
    if not paths and not (reading and due):
        print("spec-check sign: nothing staged under openspec/, and no change waits for its "
              "consistency read, so this commit needs no Spec-check trailer", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
        materialize(repo, tree, tmp, allow_empty=True)
        staged = Corpus(tmp)
        targets = [c for c in changes if c in staged.changes]
        if reading:
            targets += [c for c, _ in due if c in staged.changes and c not in targets]
        # A main decision record, or the file that says where they are, is
        # checked with the specs.
        # A staged deletion is not in the staged tree, so it is judged by its
        # path alone.
        specs = specs or any(
            p == CONFIG_FILE or p in staged.records
            or (record_cap(staged.template, p) is not None
                and not os.path.lexists(os.path.join(tmp, *p.split("/"))))
            for p in paths)
        targets += ["specs"] if specs and (staged.specs or staged.records) else []
        if not targets:
            bad = [f for f in staged.config_findings if f.severity == "error"]
            if bad and CONFIG_FILE in paths:
                for f in bad:
                    print(f.text())
                print("\nspec-check sign: not signed. Fix the errors and sign again.",
                      file=sys.stderr)
                return 1
            # Only deletions or archive moves: nothing open is left to check.
            print(f"{KEY}: \u2713 {tree[:12]} no open change or spec staged")
            return 0
        res = run_checks(tmp, repo, base_ref, targets, not args.no_validate,
                         bool(args.base), tree)
    errors = print_report(*res, base_ref, "the staged tree", False)
    unasked = [f.handback for f in res[2] if f.handback]
    if unasked:
        print("\nThese kept entries keep an evolution error that no person approved:")
        for text in unasked:
            print(f"  {text}")
        print("Do not commit. Leave the change staged and put this message, whole, in your "
              "result. Whoever receives it asks a person about each entry, adds `(asked)` to "
              "each one the person keeps, fixes the text of the others and deletes their "
              "entries, and signs again.")
    if errors:
        print("\nspec-check sign: not signed. Fix the errors and sign again, or commit "
              "work in progress with `Spec-check: skipped (<reason>)`.", file=sys.stderr)
        return 1
    statuses = [st for _, st in res[3]]
    if not statuses:
        validate = "not run"
    elif all(st == "passed" for st in statuses):
        validate = "passed"
    elif any(st.startswith("not") for st in statuses):
        validate = "not run"
    else:
        validate = "failed"
    if res[6] != "read":
        # Without the CLI, nothing that reads a requirement ran: say all of it.
        validate = f"show, validate and archive not run ({NEEDS_OPENSPEC})"
    else:
        validate = f"validate {validate}"
    if not due:
        read = NO_READ_DUE
    elif args.read == "deferred":
        read = DEFERRED
    else:
        reader = "a fresh subagent" if args.read == "subagent" else "its author, no subagent"
        read = (f"read by {reader}: {', '.join(c for c, _ in due)}; "
                f"{args.amended} amended, {args.open} open")
    kept = res[7]
    counts = f"0 errors, {len(res[2])} checks" + (f", {len(kept)} evolution kept" if kept else "")
    print(f"\n{KEY}: \u2713 {tree[:12]} {counts}; {validate}; {read}")
    return 0


def tree_matches(value, tree):
    m = VALUE.match(value.strip())
    if not m:
        return False, (f"the value is neither a skip note nor `✓ <tree> ...` as "
                       f"spec_check.py sign prints it: {value.strip()!r}")
    if not tree.startswith(m.group(1)):
        return False, (f"it was signed over tree {m.group(1)}, and the tree is {tree[:12]}: "
                       "something was staged after signing")
    return True, ""


def cmd_verify_staged(args):
    line = args.line
    prefix = f"{KEY}:"
    if not line.startswith(prefix):
        print(f"expected a `{KEY}: <value>` line, got {line!r}")
        return 2
    sys.stdin.read()  # the message; this trailer binds the tree only
    value = line[len(prefix):].strip()
    if is_skip(value):
        return 0
    try:
        tree = git(".", "write-tree").stdout.strip()
    except Fatal as e:
        print(e)
        return 3
    ok, why = tree_matches(value, tree)
    if not ok:
        print(why)
    return 0 if ok else 1


def cmd_verify_commit(args):
    if is_skip(args.value):
        return 0
    out = git(".", "rev-parse", f"{args.sha}^{{tree}}", check=False)
    if out.returncode != 0:
        print(f"cannot read the tree of {args.sha}")
        return 3
    ok, why = tree_matches(args.value, out.stdout.strip())
    if not ok:
        print(why)
    return 0 if ok else 1


# -- current-state passes ------------------------------------------------

# How every line starts that a hook prints when an event may leave docs
# describing an earlier state. The agent does the pass without asking (SKILL.md, *Current-state
# passes*); DECISIONS.md, "Events start a current-state pass".
PASS_DUE = "current-state pass due for:"
# A path under a src/ directory, at the top or deeper, as in packages/x/src/.
SRC_PATH = re.compile(r"(?:^|/)src/")
# The date `openspec archive` puts before a change's name.
ARCHIVE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
SHOWN_SRC = 3
# The pass a hand-back starts: the final pass of prose's single-pass rule.
# The workflow prints this; prose's hook prints its own wording of the same
# pass after an agent's hand-back.
HANDBACK_PASS = (f"{PASS_DUE} each doc the pull request changes, and its body and title. "
                 "It was handed back for review: flag and fix any that still describes "
                 "work as unfinished or to come.")


def added_paths(repo, sha):
    """The paths a commit adds, against its first parent, renames read as an
    addition and a deletion."""
    return changed_paths(repo, sha, "A")


def changed_paths(repo, sha, status):
    """The paths a commit changes with a git status letter (A, D, ...) against
    its first parent, renames read as an addition and a deletion."""
    out = git(repo, "diff-tree", "--no-commit-id", "--name-only", "--no-renames",
              f"--diff-filter={status}", "-r", "-z", "--root", sha, check=False)
    return [p for p in out.stdout.split("\0") if p] if out.returncode == 0 else []


def amended_from(repo, sha):
    """The commit an amend replaced, from HEAD's reflog: the entry before the
    `commit (amend):` entry that made sha; None for any other commit."""
    out = git(repo, "reflog", "show", "--format=%H%x09%gs", "HEAD", check=False)
    entries = [line.split("\t", 1) for line in out.stdout.splitlines()] \
        if out.returncode == 0 else []
    for i, entry in enumerate(entries):
        if len(entry) == 2 and entry[0] == sha and entry[1].startswith("commit (amend):") \
                and i + 1 < len(entries):
            return entries[i + 1][0]
    return None


def made_on(repo, sha, branch):
    """Whether branch's reflog records sha as committed on it."""
    out = git(repo, "reflog", "show", "--format=%H%x09%gs", f"refs/heads/{branch}",
              check=False)
    return out.returncode == 0 and any(
        line.split("\t", 1)[0] == sha and line.split("\t", 1)[-1].startswith("commit")
        for line in out.stdout.splitlines())


def passes_due(repo, sha, base_ref, branch_ref=None, branch=None):
    """The `current-state pass due for:` lines a commit starts: one for each
    change it archives, and one for each open change of the branch when it
    adds a file under a src/ directory. base_ref is "HEAD" for a commit on
    the base branch. branch_ref is the base ref as given, before cmd_pass_due
    replaced it with "HEAD", and branch is the base branch's name; both are
    used only to judge an amend's replaced commit."""
    passes = commit_passes(repo, sha, base_ref)
    amended = amended_from(repo, sha) if passes else None
    if amended:
        # An amend asks only for passes the commit it replaced did not ask
        # for: the same pass, with no src/ file it lacked, is not asked for
        # again. The replaced commit is judged as its own hook judged it: by
        # the base-branch rule when that branch's reflog records it committed
        # there, else by the narrower branch rule, so that when unsure, a
        # pass it may not have printed is printed now rather than lost.
        on_base = branch_ref is None or branch_ref == "HEAD" or (
            branch is not None and made_on(repo, amended, branch))
        earlier = {key: srcs for key, srcs, _ in
                   commit_passes(repo, amended, "HEAD" if on_base else branch_ref)}
        passes = [(key, srcs, line) for key, srcs, line in passes
                  if key not in earlier or not srcs <= earlier[key]]
    return [line for _, _, line in passes]


def commit_passes(repo, sha, base_ref):
    """[(key, set of added src/ paths, line)] for one commit, judged alone:
    the key names the pass, ("archive", folder) or ("change", name)."""
    added = added_paths(repo, sha)
    passes = []
    # An archive is the pair `openspec archive` makes in one commit: the
    # change's folder deleted, and archive/<date>-<name>/ added, or
    # archive/<name>/ when the name already starts with a date. Moving
    # archive folders that already exist deletes no change, and is not
    # archiving.
    removed = {p.split("/")[2] for p in changed_paths(repo, sha, "D")
               if p.startswith("openspec/changes/") and p.count("/") >= 3} - {"archive"}
    folders = sorted({p.split("/")[3] for p in added
                      if p.startswith("openspec/changes/archive/") and p.count("/") >= 4})
    for folder in folders:
        name = folder if folder in removed else ARCHIVE_DATE.sub("", folder)
        if name not in removed:
            continue
        passes.append((("archive", folder), set(), (
            f"{PASS_DUE} the DECISIONS.md of each skill the change {name} affects. "
            f"It is archived as openspec/changes/archive/{folder}: fold its reasoning "
            "into those files, rewriting older reasoning rather than appending to it, "
            "then run prose check on each and compact any it reports as due.")))
    src = [p for p in added if SRC_PATH.search(p)]
    if not src:
        return passes
    tree = git(repo, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
    start = None if base_ref == "HEAD" else merge_base_tree(repo, sha, base_ref)
    shown = ", ".join(src[:SHOWN_SRC]) + (f" and {len(src) - SHOWN_SRC} more"
                                          if len(src) > SHOWN_SRC else "")
    for c in sorted(open_changes(repo, tree)):
        prefix = f"openspec/changes/{c}/"
        now = blob_ids(repo, tree, prefix)
        if start is not None and blob_ids(repo, start, prefix) == now:
            continue  # not this branch's change
        docs = [f"{prefix}{f}" for f in ("proposal.md", "design.md") if f"{prefix}{f}" in now]
        targets = docs + ["the pull request's body and title"]
        listed = targets[0] if len(targets) == 1 else \
            ", ".join(targets[:-1]) + ", and " + targets[-1]
        passes.append((("change", c), set(src), f"{PASS_DUE} {listed}. The implementation is on the branch of the open change {c} "
                     f"({shown} added): rewrite wording such as \"specification only\", or "
                     "\"will\" for what is now built."))
    return passes


def cmd_pass_due(args):
    repo = repo_root(args.repo)
    # The full id: HEAD's reflog, read for an amend, names commits in full.
    out = git(repo, "rev-parse", "-q", "--verify", f"{args.sha}^{{commit}}", check=False)
    if out.returncode != 0:
        raise Fatal(f"no commit {args.sha}")
    sha = out.stdout.strip()
    base_ref = args.base or default_base(repo)
    # On the base branch every open change counts as the branch's, as
    # spec_check.py's sign command counts them, so the hook and sign agree.
    # base_ref "HEAD" marks that case below; holders stays empty when it is
    # given as HEAD already.
    # Judged by the commit, not HEAD: the hook runs after the whole command,
    # and `git commit && git checkout main` leaves HEAD on another branch.
    # The commit is on the base branch when the local base branch or base_ref
    # holds it: after `git push origin HEAD:main`, only the remote's copy
    # does.
    branch_ref = base_ref
    branch = branch_of(repo, base_ref) if base_ref != "HEAD" else None
    holders = [base_ref] + ([f"refs/heads/{branch}"] if branch else []) \
        if base_ref != "HEAD" else []
    if any(git(repo, "merge-base", "--is-ancestor", sha, ref, check=False).returncode == 0
           for ref in holders):
        base_ref = "HEAD"
    for line in passes_due(repo, sha, base_ref, branch_ref, branch):
        print(line)
    return 0


# -- the GitHub workflow ---------------------------------------------------

# The pull_request actions that hand a pull request back for review. On any
# other action (a push) the workflow fails the check with a change unread,
# but leaves the pull request as it is.
CI_HANDBACKS = ("opened", "reopened", "ready_for_review", "review_requested")
CI_TEMPLATE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "ci",
                           "spec-check.yml")
CI_PIN = "<SPEC_CHECK_SHA>"


def cmd_ci(args):
    path = args.event or os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise Fatal("ci reads a pull_request event: pass --event or set GITHUB_EVENT_PATH")
    try:
        with open(path, encoding="utf-8") as fh:
            event = json.load(fh)
        pr, action = event["pull_request"], event.get("action")
        head, base, url = pr["head"]["sha"], pr["base"]["ref"], pr["html_url"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Fatal(f"{path} is not a pull_request event: {e}") from e
    repo = repo_root(args.repo)
    draft = pr.get("draft") is True
    if draft and action != "review_requested":
        print("spec-check: a draft pull request is not handed back for review.")
        return 0
    if git(repo, "cat-file", "-e", f"{head}^{{commit}}", check=False).returncode != 0:
        raise Fatal(f"the pull request's head {head} is not in this clone: check it out with "
                    "fetch-depth: 0")
    base_ref = next((ref for ref in (f"refs/remotes/origin/{base}", f"refs/heads/{base}")
                     if git(repo, "rev-parse", "-q", "--verify", ref, check=False).returncode == 0),
                    None)
    if base_ref is None:
        raise Fatal(f"the base branch {base} is not in this clone: check it out with "
                    "fetch-depth: 0")
    links = openspec_links(repo, head)
    if links:
        # A symlink under openspec/ means no change can be judged read
        # (DECISIONS.md, "No symlink under openspec/"). So the hand-back
        # (marking the pull request ready, or requesting a reviewer) is undone
        # in the block below, as for an unread change; without that, the pull
        # request would reach review while the link stays.
        print(f"::error::{links_problem(links)} (head {head[:12]}); push, and hand back again.")
    else:
        unread = unread_at(repo, head, base_ref)
        if not unread:
            print(f"spec-check: no OpenSpec change is unread at {head[:12]}.")
            if action in CI_HANDBACKS:
                print(f"::notice::{HANDBACK_PASS}")
            return 0
        print(f"::error::spec-check: {', '.join(unread)} changed after its last consistency read "
              f"(head {head[:12]}). Do the read (spec-check's SKILL.md, section 2), commit with "
              "`spec_check.py sign --read subagent`, push, and hand back again.")
    if action in CI_HANDBACKS:
        undo = []
        if not draft:
            undo.append(["pr", "ready", url, "--undo"])
        who = event.get("requested_reviewer") or {}
        team = event.get("requested_team") or {}
        owner = (event.get("repository") or {}).get("owner") or {}
        if action == "review_requested" and isinstance(who.get("login"), str):
            undo.append(["pr", "edit", url, "--remove-reviewer", who["login"]])
        elif action == "review_requested" and isinstance(team.get("slug"), str) \
                and isinstance(owner.get("login"), str):
            undo.append(["pr", "edit", url, "--remove-reviewer",
                         f"{owner['login']}/{team['slug']}"])
        for command in undo:
            try:
                gh(repo, *command)
                print(f"spec-check: ran gh {' '.join(command)}")
            except StackError as e:
                print(f"::warning::spec-check: could not take the hand-back back ({e}); the "
                      "workflow needs pull-requests: write, which a fork's pull request "
                      "does not get.")
    return 1


def cmd_setup_ci(args):
    repo = repo_root(args.repo)
    dest = os.path.join(repo, ".github", "workflows", "spec-check.yml")
    if os.path.exists(dest) and not args.force:
        print(f"spec-check setup-ci: {dest} exists; pass --force to replace it",
              file=sys.stderr)
        return 1
    sha = args.sha
    if sha is None:
        # The clone holding this file, through any install symlink.
        clone = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.realpath(__file__))))))
        sha = git(clone, "log", "-1", "--format=%H", "--",
                  ".agents/skills/spec-check/scripts/spec_check.py",
                  check=False).stdout.strip()
        if not sha or not git(clone, "branch", "-r", "--contains", sha,
                              check=False).stdout.strip():
            print("spec-check setup-ci: the newest commit of spec_check.py in this clone "
                  "is not pushed, so GitHub cannot serve it; pass --sha with a pushed "
                  "commit of adamstallard/shared-skills", file=sys.stderr)
            return 1
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        print("spec-check setup-ci: --sha takes a full 40-character commit SHA, never a "
              "branch", file=sys.stderr)
        return 1
    with open(CI_TEMPLATE, encoding="utf-8") as fh:
        text = fh.read().replace(CI_PIN, sha)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"spec-check: wrote {os.path.relpath(dest, repo)}, pinned to {sha}. Commit it, and "
          "make the `spec-check` check required in the base branch's protection rules.")
    return 0


# -- decision records: the reader's list, and the fold at archive ----------------

def cmd_records(args):
    """Print the decision records the consistency read of a change is given,
    main records and the records of the changes it builds on: one path per
    line with why, or `none`."""
    repo = repo_root(args.repo)
    base_ref = args.base or default_base(repo)

    def run(root):
        corpus = Corpus(root, requirements=False)
        changes, _ = resolve_targets(corpus, [args.change])
        if not changes:
            raise Fatal("records takes a change's name")
        (change,) = changes
        changed = changed_files(repo, base_ref, args.ref)
        found = records_for(change, corpus, changed, record_deps(repo, change, corpus))
        for rel, why in found:
            print(f"{rel}  ({why})")
        if not found:
            print("none")
        if changed is None:
            print(f"spec-check records: no merge base with {base_ref}, so no record was matched "
                  "by its Paths", file=sys.stderr)
        return 0

    if args.ref:
        with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
            materialize(repo, args.ref, tmp)
            return run(tmp)
    return run(repo)


def record_deps(repo, change, corpus):
    """The dependencies a change's `Builds on:` lines name whose own records
    are not yet in main: each read from its pull request, as check reads
    it. A merged one is left out once the tree no longer holds its change
    open, since its records were folded when it archived. One that cannot
    be read is named on stderr and left out."""
    path = f"openspec/changes/{change}/proposal.md"
    deps, _ = builds_on(corpus.texts.get(path, ""), path)
    found = []
    for dep in deps:
        try:
            info = pr_info(repo, dep)
            dep.archive = own_change(repo, dep, info)
            load_dep(repo, dep, info)
        except StackError as e:
            print(f"spec-check records: cannot read {dep.label}, so its records are not listed: "
                  f"{e}", file=sys.stderr)
            continue
        # A merged one the tree still holds open has not archived yet, so its
        # records are not in main: check folds them in (stack_records).
        if dep.state != "MERGED" or dep.change in corpus.changes:
            found.append(dep)
    return found


def cmd_archive(args):
    """`openspec archive` the change, then fold its decision records into the
    main ones, which OpenSpec leaves alone. Nothing is archived when a record
    cannot be folded."""
    repo = repo_root(args.repo)
    corpus = Corpus(repo, requirements=False)
    changes, _ = resolve_targets(corpus, [args.change])
    if not changes:
        raise Fatal("archive takes a change's name")
    (change,) = changes
    path = f"openspec/changes/{change}/proposal.md"
    deps, unread = builds_on(corpus.texts.get(path, ""), path)
    if unread:
        for f in unread:
            print(f.text())
        print(f"\nspec-check archive: nothing archived. Fix {change}'s `Builds on:` lines, so "
              "the changes it builds on are known, and run it again.", file=sys.stderr)
        return 1
    if any(d.change == change for d in deps):
        print(f"spec-check archive: nothing archived. {change}'s proposal names itself in a "
              "`Builds on:` line; a change cannot build on itself.", file=sys.stderr)
        return 1
    open_deps = [d for d in deps if d.change in corpus.changes]
    if open_deps:
        names = ", ".join(d.change for d in open_deps)
        print(f"spec-check archive: {change} builds on {names}, still open here; archive "
              f"{names} first, so their decision records fold in before {change}'s",
              file=sys.stderr)
        return 1
    folded, findings = fold_change(change, corpus)
    findings = [f for f in corpus.config_findings if f.severity == "error"] + findings
    if findings:
        for f in findings:
            print(f.text())
        print("\nspec-check archive: nothing archived. Fix the records and run it again.",
              file=sys.stderr)
        return 1
    missing = openspec_missing()
    if missing:
        raise Fatal(missing)
    # Always --yes: an answer to one of OpenSpec's prompts, such as declining
    # the spec updates, is invisible here, and the fold must match what
    # OpenSpec did.
    yes = [] if {"-y", "--yes"} & set(args.openspec_args) else ["--yes"]
    rc = subprocess.run([openspec_exe(), "archive", change, *yes, *args.openspec_args],
                        cwd=repo, stdin=subprocess.DEVNULL).returncode
    if rc != 0:
        return rc
    if os.path.isdir(os.path.join(repo, "openspec", "changes", change)):
        print(f"spec-check archive: openspec archive left {change} in place, so its decision "
              "records were not folded", file=sys.stderr)
        return 1
    if "--skip-specs" in args.openspec_args:
        # OpenSpec left the main specs alone, so their records stay as they are.
        if folded:
            print(f"spec-check: --skip-specs left the main specs alone, so {change}'s decision "
                  "records were not folded either")
        return 0
    for rel, text in sorted(folded.items()):
        full = os.path.join(repo, *rel.split("/"))
        if text is None:
            if os.path.lexists(full):
                os.remove(full)
            print(f"spec-check: {rel} has no entry left; removed it")
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"spec-check: folded {change}'s decision record into {rel}")
    return 0


def main(argv=None):
    # A file name that is not UTF-8 reaches messages as git() reads it, with
    # its bytes escaped. A stream whose error handler already writes them
    # back as bytes, such as surrogateescape, keeps doing so; a strict one
    # shows them escaped, never a crash.
    for stream in (sys.stdout, sys.stderr):
        if getattr(stream, "errors", None) == "strict" and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    p = argparse.ArgumentParser(prog="spec_check.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="mechanical checks over changes or specs")
    c.add_argument("targets", nargs="*")
    c.add_argument("--repo")
    c.add_argument("--ref", help="read openspec/ from this git ref, not the working tree")
    c.add_argument("--base", help="the ref citations are checked against (default: origin/HEAD, origin/main, main)")
    c.add_argument("--no-validate", action="store_true")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    g = sub.add_parser("sign", help="check the staged openspec change and print the trailer")
    g.add_argument("--read", required=True, choices=["subagent", "self", "deferred"],
                   help="who did the round's consistency read, or deferred inside a round")
    g.add_argument("--amended", type=int, default=0, help="amendments the read led to")
    g.add_argument("--open", type=int, default=0, help="open questions left in design.md")
    g.add_argument("--repo")
    g.add_argument("--base")
    g.add_argument("--no-validate", action="store_true")
    g.set_defaults(fn=cmd_sign)

    v = sub.add_parser("verify-staged")
    v.add_argument("line")
    v.set_defaults(fn=cmd_verify_staged)

    vc = sub.add_parser("verify-commit")
    vc.add_argument("sha")
    vc.add_argument("value")
    vc.set_defaults(fn=cmd_verify_commit)

    pd = sub.add_parser("pass-due", help="the current-state passes a commit starts (the "
                                          "commit hook)")
    pd.add_argument("sha")
    pd.add_argument("--repo")
    pd.add_argument("--base")
    pd.set_defaults(fn=cmd_pass_due)

    ci = sub.add_parser("ci", help="the GitHub workflow's check of a pull request event")
    ci.add_argument("--event", help="the event JSON (default: $GITHUB_EVENT_PATH)")
    ci.add_argument("--repo")
    ci.set_defaults(fn=cmd_ci)

    su = sub.add_parser("setup-ci", help="write the GitHub workflow into a repository")
    su.add_argument("--repo")
    su.add_argument("--sha", help="the shared-skills commit to pin (default: this clone's "
                                   "newest pushed commit of spec_check.py)")
    su.add_argument("--force", action="store_true")
    su.set_defaults(fn=cmd_setup_ci)

    r = sub.add_parser("records", help="the decision records a change's consistency read is given")
    r.add_argument("change")
    r.add_argument("--repo")
    r.add_argument("--ref", help="read openspec/ from this git ref, not the working tree")
    r.add_argument("--base", help="the branch the change targets (default: origin/HEAD, origin/main, main)")
    r.set_defaults(fn=cmd_records)

    a = sub.add_parser("archive", help="openspec archive a change, then fold its decision records")
    a.add_argument("change")
    a.add_argument("--repo")
    a.set_defaults(fn=cmd_archive)

    # archive passes what follows its `--` to openspec archive untouched.
    argv = list(sys.argv[1:] if argv is None else argv)
    passed = []
    if argv[:1] == ["archive"] and "--" in argv:
        at = argv.index("--")
        argv, passed = argv[:at], argv[at + 1:]
    args = p.parse_args(argv)
    args.openspec_args = passed
    try:
        return args.fn(args)
    except Fatal as e:
        print(f"spec-check: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
