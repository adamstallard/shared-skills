#!/usr/bin/env python3
"""spec-check: the mechanical half of reviewing an OpenSpec change.

    spec_check.py check [<target>...] [--repo DIR] [--ref REF] [--base REF]
                        [--decisions-heading TEXT]... [--no-validate] [--json]
    spec_check.py setup [--repo DIR] [--decline] [--dry-run]
    spec_check.py state [--repo DIR]
    spec_check.py sign --read subagent|self [--amended N] [--open N]
                       [--base REF] [--decisions-heading TEXT]... [--no-validate]
    spec_check.py verify-staged "Spec-check: <value>"   (message on stdin)
    spec_check.py verify-commit <sha> <value>
    spec_check.py proposal-hook --host claude|cursor   (hook payload on stdin)

A target is a change name, a change directory (openspec/changes/<name>), or
`specs` for every spec under openspec/specs. With no target, every open change
is checked. `--ref` reads openspec/ from a git ref instead of the working tree,
so a pull request's branch is checked without checking it out.

check exits 0 with no errors, 1 with errors, 2 when it cannot run. Findings
marked `check` are heuristics for a person or agent to judge; they never fail.

Standard library only. Read DECISIONS.md next to SKILL.md before changing this.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

DECISIONS_HEADINGS = ["Decisions"]

# The repository's answer to whether proposals must open with their
# decisions. Only setup writes it, as one line: `decisions-first: enforce` or
# `decisions-first: off`. It is spec-check's own file: the script never reads
# or edits OpenSpec's config (DECISIONS.md, "Each repository's
# decisions-first answer lives in spec-check's own file").
DECISION_FILE = "openspec/spec-check.yaml"
DECISION_LINE = re.compile(r"^decisions-first:[ \t]*(enforce|off)[ \t]*$")
# The states, as `state` prints them and `check --json` reports them.
ENFORCE, OFF, UNDECIDED, INVALID = "enforce", "off", "undecided", "invalid"

KEY = "Spec-check"

NORMATIVE = re.compile(r"\b(SHALL|MUST)\b")
WHEN = re.compile(r"(\*\*WHEN\*\*|^\s*[-*]?\s*WHEN\b)", re.M)
THEN = re.compile(r"(\*\*THEN\*\*|^\s*[-*]?\s*THEN\b)", re.M)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
DELTA = re.compile(r"^(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.I)
REQUIREMENT = re.compile(r"^Requirement:\s*(.*)$")
SCENARIO = re.compile(r"^Scenario:\s*(.*)$")

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


def git(repo, *args, check=True, binary=False, stdin=None):
    result = subprocess.run(
        ["git", "-C", repo, "-c", "log.showSignature=false", *args],
        capture_output=True, input=stdin, text=not binary,
    )
    if check and result.returncode != 0:
        err = result.stderr if not binary else result.stderr.decode("utf-8", "replace")
        raise Fatal(f"git {' '.join(args)} failed: {err.strip()}")
    return result


# -- reading openspec/ -----------------------------------------------------

def materialize(repo, treeish, dest, allow_empty=False):
    """Writes treeish's openspec/ under dest. With allow_empty, a tree that has
    none gets an empty one: sign must sign a commit that deletes openspec/."""
    has = git(repo, "ls-tree", "--name-only", treeish, "--", "openspec", check=False)
    if allow_empty and has.returncode == 0 and not has.stdout.strip():
        os.makedirs(os.path.join(dest, "openspec"))
        return
    # The decision file is left out: tree_decision reads it from the tree,
    # and a link there must become a finding, not a link to extract.
    # The peeled tree, not a commit: a commit's archive starts with a pax
    # header, so one with no file in it is a tar that tarfile cannot open.
    out = git(repo, "archive", "--format=tar", f"{treeish}^{{tree}}", "--", "openspec",
              f":(exclude){DECISION_FILE}", check=False, binary=True)
    if out.returncode != 0:
        raise Fatal(f"cannot read openspec/ from {treeish}: "
                    f"{out.stderr.decode('utf-8', 'replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python before 3.12 has no filter argument
            tar.extractall(dest)
    # An openspec/ holding only the decision file archives as nothing.
    os.makedirs(os.path.join(dest, "openspec"), exist_ok=True)


FENCE = re.compile(r"(`{3,}|~{3,})")
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
    heading, a decision, a label or a citation.

    It follows CommonMark as far as fences need:
    - A fence may be indented up to three spaces past the content column of
      the list item it sits in, and may open on the item's own marker line.
    - It closes only with a bare fence of its own character, at least as long.
    - A line indented less than the content column of the fence's list item
      ends that item, and the fence with it.
    - A lazy continuation line keeps its list item open, but a fence line is
      never lazy: it interrupts the paragraph, as in CommonMark.
    - Blockquote markers (`>`) are set aside before any of this. A fence
      remembers how many it opened inside, and inside it only that many are
      stripped, so a `>` prompt in a code example stays code."""
    items = []      # content columns of the open list items, outermost first
    # The open fence: (character, length, content column of its list item or
    # 0, blockquote depth).
    fence = None
    prose = False   # whether the line before was paragraph text
    for n, raw in enumerate(text.splitlines(), 1):
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
        self.text = []        # (line number, text) before the first scenario
        self.scenarios = []   # Scenario

    @property
    def body(self):
        return "\n".join(t for _, t in self.text)


class Scenario:
    def __init__(self, line, name):
        self.line, self.name, self.lines = line, name, []


def parse_spec(rel, text):
    """Requirements in one spec.md, main or delta."""
    reqs, section, req, scen = [], None, None, None
    for n, raw, fenced in markdown_lines(text):
        m = None if fenced else HEADING.match(raw)
        if m:
            level, title = len(m.group(1)), m.group(2)
            if level == 2:
                d = DELTA.match(title)
                section = d.group(1).upper() if d else None
                req = scen = None
                continue
            r = REQUIREMENT.match(title) if level == 3 else None
            if r:
                req = Req(rel, n, r.group(1).strip(), section)
                reqs.append(req)
                scen = None
                continue
            s = SCENARIO.match(title) if level == 4 else None
            if s and req is not None:
                scen = Scenario(n, s.group(1).strip())
                req.scenarios.append(scen)
                continue
            if level <= 3:
                req = scen = None
            else:
                scen = None
            continue
        if scen is not None:
            scen.lines.append(raw)
        elif req is not None:
            req.text.append((n, raw))
    return reqs


RENAMED_FROM = re.compile(r"FROM:\s*`?\s*#*\s*Requirement:\s*(.+?)\s*`?\s*$")


def retired_names(text):
    """Names of the requirements one delta spec removes or renames away from."""
    names, section = set(), None
    for _, raw, fenced in markdown_lines(text):
        if fenced:
            continue
        m = HEADING.match(raw)
        if m and len(m.group(1)) == 2:
            d = DELTA.match(m.group(2))
            section = d.group(1).upper() if d else None
            continue
        if section == "REMOVED" and m and len(m.group(1)) == 3:
            r = REQUIREMENT.match(m.group(2))
            if r:
                names.add(r.group(1).strip().lower())
        elif section == "RENAMED":
            r = RENAMED_FROM.search(raw)
            if r:
                names.add(r.group(1).strip().lower())
    return names


class Corpus:
    """Everything under openspec/ at one root: main specs and open changes."""

    def __init__(self, root):
        self.root = root
        base = os.path.join(root, "openspec")
        if not os.path.isdir(base):
            raise Fatal(f"no openspec/ directory in {root}")
        self.specs = {}     # rel path -> [Req]
        self.changes = {}   # change name -> {rel path -> [Req]}
        self.texts = {}     # rel path -> text, every markdown file read
        specs_dir = os.path.join(base, "specs")
        for cap in sorted(os.listdir(specs_dir)) if os.path.isdir(specs_dir) else []:
            for rel in self._markdown(os.path.join("openspec", "specs", cap)):
                if rel.endswith("spec.md"):
                    self.specs[rel] = parse_spec(rel, self.texts[rel])
        changes_dir = os.path.join(base, "changes")
        for name in sorted(os.listdir(changes_dir)) if os.path.isdir(changes_dir) else []:
            if name == "archive" or not os.path.isdir(os.path.join(changes_dir, name)):
                continue
            files = {}
            for rel in self._markdown(os.path.join("openspec", "changes", name)):
                if "/specs/" in rel and rel.endswith("spec.md"):
                    files[rel] = parse_spec(rel, self.texts[rel])
            self.changes[name] = files

    def _markdown(self, rel_dir):
        found = []
        for dirpath, dirnames, filenames in os.walk(os.path.join(self.root, rel_dir)):
            dirnames.sort()
            for f in sorted(filenames):
                if f.endswith(".md"):
                    full = os.path.join(dirpath, f)
                    rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                    with open(full, encoding="utf-8", errors="replace") as fh:
                        self.texts[rel] = fh.read()
                    found.append(rel)
        return found

    def files_of(self, change):
        prefix = f"openspec/changes/{change}/"
        return [p for p in self.texts if p.startswith(prefix)]

    def all_reqs(self):
        for path, reqs in self.specs.items():
            for r in reqs:
                yield r
        for files in self.changes.values():
            for reqs in files.values():
                for r in reqs:
                    yield r


# -- findings ----------------------------------------------------------------

class Finding:
    def __init__(self, path, line, severity, kind, message):
        self.path, self.line, self.severity = path, line, severity
        self.kind, self.message = kind, message

    def text(self):
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.severity} [{self.kind}] {self.message}"

    def as_dict(self):
        return {"path": self.path, "line": self.line, "severity": self.severity,
                "kind": self.kind, "message": self.message}


def check_scenarios(reqs, out):
    for r in reqs:
        if r.section in ("REMOVED", "RENAMED"):
            continue
        if NORMATIVE.search(r.body) and not r.scenarios:
            out.append(Finding(r.path, r.line, "error", "no-scenario",
                               f'requirement "{r.name}" states a SHALL or MUST and has no scenario'))
        for s in r.scenarios:
            body = "\n".join(s.lines)
            missing = [w for w, rx in (("WHEN", WHEN), ("THEN", THEN)) if not rx.search(body)]
            if missing:
                out.append(Finding(r.path, s.line, "error", "scenario-incomplete",
                                   f'scenario "{s.name}" has no {" or ".join(missing)}'))


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
    """Whether one of a and b is a main-spec requirement that the other's
    change removes or renames, in its delta file for that requirement's
    capability. Such a pair is not reported as a duplicate: the change
    replaces the old requirement, even when the rule moves to another
    capability."""
    for spec, delta in ((a, b), (b, a)):
        parts = delta.path.split("/")
        if not spec.path.startswith("openspec/specs/") or parts[1:2] != ["changes"]:
            continue
        cap = spec.path.split("/")[2]
        retired_by_change = corpus.texts.get(f"openspec/changes/{parts[2]}/specs/{cap}/spec.md")
        if retired_by_change and spec.name.lower() in retired_names(retired_by_change):
            return True
    return False


def check_duplicates(targets, corpus, out):
    index = {}
    for r in corpus.all_reqs():
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
            # A MODIFIED requirement restates the one it modifies, so copies
            # under one requirement name are expected.
            others = [(o, ol) for o, ol in places
                      if o is not r and o.name.lower() != r.name.lower()
                      and not retires(corpus, r, o)]
            if others:
                o, ol = others[0]
                more = f" and {len(others) - 1} more" if len(others) > 1 else ""
                out.append(Finding(r.path, line, "error", "duplicate",
                                   f'this rule is also stated in "{o.name}" at {o.path}:{ol}{more}; '
                                   "state it once and refer to it"))


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


def decisions_heading_ok(title, headings):
    t = title.strip().strip("*").strip().lower()
    return any(t.startswith(h.lower()) for h in headings)


def check_decisions(change, corpus, headings, out):
    path = f"openspec/changes/{change}/proposal.md"
    if path not in corpus.texts:
        out.append(Finding(path, 0, "error", "decisions-first", "the change has no proposal.md"))
        return
    for n, raw, fenced in markdown_lines(corpus.texts[path]):
        m = None if fenced else HEADING.match(raw)
        if not m or len(m.group(1)) < 2:
            continue
        if not decisions_heading_ok(m.group(2), headings):
            names = " or ".join(f'"{h}"' for h in headings)
            out.append(Finding(path, n, "error", "decisions-first",
                               f'the proposal opens with "{m.group(2)}"; it must open with a '
                               f"section headed {names}: the decisions the reviewer is asked to make, "
                               "then what is still open"))
        elif not has_decisions(corpus.texts[path], n, len(m.group(1))):
            out.append(Finding(path, n, "error", "decisions-first",
                               "the decisions section lists no decisions; list each as an item"))
        return
    out.append(Finding(path, 0, "error", "decisions-first", "the proposal has no sections"))


DECISION_ITEM = re.compile(r"^(\d+[.)]|[-*])\s+")
# What starts the "still open" part: "Still open", "Open questions", "Open
# items", "Open issues" or "Open", as a whole label. It is bold, ends in a
# colon, or is all the line says, so "Open issues close after ninety days" is a
# decision, not the label.
OPEN_LABEL = re.compile(
    r"^([*_]{0,2})\s*(still\s+open|open\s+(?:questions?|items?|issues?)|open)(?![A-Za-z0-9])"
    r"\s*([:?.]?)\s*([*_]{0,2})\s*([:?.]?)\s*(.*)$",
    re.I)


def is_open_label(text):
    """Whether the text is the "still open" label: wrapped in emphasis (bold
    or italic), followed by a colon, or all the text says ("Still open.")."""
    m = OPEN_LABEL.match(text.strip())
    if not m:
        return False
    wrapped = bool(m.group(1) and m.group(4))
    colon = ":" in (m.group(3) + m.group(5))
    return wrapped or colon or not m.group(6)


def has_decisions(text, start, level):
    """Whether the decisions section lists at least one decision. start is the
    line number of the section's heading, and level is its depth. A decision
    is a list item at the left margin that comes before the section ends and
    before the "still open" label."""
    for n, raw, fenced in markdown_lines(text):
        if n <= start or fenced:  # a list item in a fence is quoted text
            continue
        h = HEADING.match(raw)
        if h and (len(h.group(1)) <= level or is_open_label(h.group(2))):
            return False
        item = DECISION_ITEM.match(raw)
        if item:
            return not is_open_label(raw[item.end():])
        # Only an unindented line can be the label; an indented line is part
        # of the text above it.
        if not raw[:1].isspace() and is_open_label(raw):
            return False
    return False


def run_validate(root, change):
    """`openspec validate --strict`, as findings plus a status line."""
    exe = shutil.which("openspec")
    if not exe:
        return [], "not run: the openspec CLI is not on PATH"
    args = [exe, "validate", "--strict", "--json", "--no-interactive"]
    args += [change, "--type", "change"] if change else ["--specs"]
    env = dict(os.environ, OPENSPEC_TELEMETRY="0", DO_NOT_TRACK="1")
    try:
        res = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=120, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], f"not run: {e}"
    try:
        start = res.stdout.index("{")
        data = json.loads(res.stdout[start:])
    except ValueError:
        tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["no output"]
        return [], f"not read: exit {res.returncode}, {tail[0]}"
    found = []
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
            # Under --strict a warning fails validation too; an INFO note never does.
            level = issue.get("level")
            sev = "error" if level == "ERROR" or (level == "WARNING" and res.returncode != 0) else "check"
            line = issue.get("line") if where.endswith(".md") and isinstance(issue.get("line"), int) else 0
            found.append(Finding(p, line, sev, "openspec-validate", message))
    status = "passed" if res.returncode == 0 else f"failed with {len(found)} issue(s)"
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


def run_checks(root, repo, base_ref, targets, headings, validate, base_required=False, change=None):
    corpus = Corpus(root)
    changes, specs = resolve_targets(corpus, targets)
    base = Base(repo, base_ref, change)
    if not base.ok and base_required:
        raise Fatal(f"the base {base_ref!r} does not resolve to a commit")
    findings, statuses = [], []
    state, problem = read_decision(root) if change is None else tree_decision(repo, change)
    if changes and state == UNDECIDED:
        findings.append(Finding(DECISION_FILE, 0, "check", "decisions-first", UNDECIDED_NOTE))
    elif changes and state == INVALID:
        findings.append(Finding(DECISION_FILE, 0, "check", "decisions-first",
                                f"{problem}; decisions-first was not checked"))
    for change in changes:
        reqs = [r for rs in corpus.changes[change].values() for r in rs]
        if state == ENFORCE:
            check_decisions(change, corpus, headings, findings)
        check_scenarios(reqs, findings)
        check_duplicates(reqs, corpus, findings)
        check_citations(corpus.files_of(change), corpus, base, findings)
        if validate:
            v, status = run_validate(root, change)
            findings += v
            statuses.append((change, status))
    if specs:
        reqs = [r for rs in corpus.specs.values() for r in rs]
        check_scenarios(reqs, findings)
        check_duplicates(reqs, corpus, findings)
        check_citations(sorted(p for p in corpus.texts if p.startswith("openspec/specs/")),
                        corpus, base, findings)
        if validate:
            v, status = run_validate(root, None)
            findings += v
            statuses.append(("openspec/specs", status))
    return changes, specs, findings, statuses, state


def print_report(changes, specs, findings, statuses, state, base_ref, source, as_json):
    errors = sum(1 for f in findings if f.severity == "error")
    checks = len(findings) - errors
    if as_json:
        print(json.dumps({
            "source": source, "base": base_ref, "changes": changes, "specs": specs,
            "errors": errors, "checks": checks, "decisions_first": state,
            "findings": [f.as_dict() for f in findings],
            "openspec_validate": {k: v for k, v in statuses},
        }, indent=2))
        return errors
    for f in findings:
        print(f.text())
    if findings:
        print()
    for what, status in statuses:
        print(f"openspec validate --strict ({what}): {status}")
    if not statuses:
        print("openspec validate --strict: not run (--no-validate)")
    scope = ", ".join(changes + (["openspec/specs"] if specs else [])) or "nothing"
    print(f"spec-check: {errors} error(s), {checks} check(s) in {scope}; "
          f"read from {source}; citations checked against {base_ref}")
    return errors


def cmd_check(args):
    repo = repo_root(args.repo)
    base_ref = args.base or default_base(repo)
    headings = args.decisions_heading or DECISIONS_HEADINGS
    if args.ref:
        with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
            materialize(repo, args.ref, tmp)
            res = run_checks(tmp, repo, base_ref, args.targets, headings, not args.no_validate,
                             bool(args.base), args.ref)
    else:
        res = run_checks(repo, repo, base_ref, args.targets, headings, not args.no_validate,
                         bool(args.base))
    source = args.ref or "the working tree"
    errors = print_report(*res, base_ref, source, args.json)
    return 1 if errors else 0


def repo_root(path):
    out = git(path or ".", "rev-parse", "--show-toplevel", check=False)
    if out.returncode != 0:
        raise Fatal(f"not in a git repository: {os.path.abspath(path or '.')}")
    return out.stdout.strip()


# -- setup -----------------------------------------------------------------

UNDECIDED_NOTE = (
    "this repository has not decided on the decisions-first rule, so no proposal "
    "was checked for it. Ask the user whether to enforce it (spec_check.py setup) "
    f"or turn it off (spec_check.py setup --decline); the answer goes in {DECISION_FILE}, "
    "so it is asked once per repository")


def write_plain(path, text):
    """Writes text to path as a new plain file. It is written under a fresh
    random name beside path, then moved into place. A link at path is
    replaced rather than written through, and since the temporary name is
    new each time, no link can be waiting there either, as one could at a
    fixed name committed to the repository."""
    folder = os.path.dirname(path)
    try:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".spec-check.", suffix=".tmp")
    except OSError as e:
        raise Fatal(f"cannot write in {folder}: {e.strerror}") from e
    try:
        umask = os.umask(0)
        os.umask(umask)
        os.fchmod(fd, 0o666 & ~umask)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if isinstance(e, OSError):
            raise Fatal(f"cannot write {path}: {e.strerror}") from e
        raise


def read_decision(home):
    """(state, problem) from home's openspec/spec-check.yaml on disk. A link
    is refused rather than followed, as in a git tree."""
    path = os.path.join(home, DECISION_FILE)
    if not os.path.lexists(path):
        return UNDECIDED, None
    if os.path.islink(path):
        return INVALID, f"{DECISION_FILE} is a symlink, not a plain file"
    if not os.path.isfile(path):
        return INVALID, f"{DECISION_FILE} is not a plain file"
    try:
        with open(path, "rb") as fh:
            return parse_decision(fh.read())
    except OSError as e:
        return INVALID, f"{DECISION_FILE} cannot be read ({e.strerror})"


def tree_decision(repo, treeish):
    """(state, problem) from openspec/spec-check.yaml in a git tree, read
    with git and never through a link: a link, a submodule or a directory is
    a problem to report, not something to resolve."""
    out = git(repo, "ls-tree", "-z", treeish, "--", DECISION_FILE, check=False)
    entry = out.stdout.split("\0", 1)[0]
    if out.returncode != 0 or not entry.endswith("\t" + DECISION_FILE):
        return UNDECIDED, None
    mode, kind, sha = entry.split("\t", 1)[0].split(" ")
    if mode == "120000":
        return INVALID, f"{DECISION_FILE} is a symlink, not a plain file"
    if kind != "blob":
        what = "a submodule" if kind == "commit" else "a directory"
        return INVALID, f"{DECISION_FILE} is {what}, not a plain file"
    return parse_decision(git(repo, "cat-file", "blob", sha, binary=True).stdout)


def parse_decision(data):
    """(state, problem) from the decision file's bytes."""
    try:
        lines = [l.strip() for l in data.decode("utf-8").splitlines() if l.strip()]
    except UnicodeDecodeError:
        lines = []
    m = DECISION_LINE.match(lines[0]) if len(lines) == 1 else None
    if m:
        return m.group(1), None
    return INVALID, (f"{DECISION_FILE} must hold one line, `decisions-first: enforce` "
                     "or `decisions-first: off`")


def cmd_setup(args):
    # The repository's top, as check, sign and the commit hook read it.
    home = repo_root(args.repo)
    if not os.path.isdir(os.path.join(home, "openspec")):
        raise Fatal(f"no openspec/ in {home}; run `openspec init` first")
    value = OFF if args.decline else ENFORCE
    path = os.path.join(home, DECISION_FILE)
    if os.path.isdir(path) and not os.path.islink(path):
        raise Fatal(f"{path} is a directory; remove it, then run setup again")
    line = f"decisions-first: {value}\n"
    if read_decision(home)[0] == value:
        print(f"spec-check setup: {DECISION_FILE} already says `{line.strip()}`")
        return 0
    if args.dry_run:
        sys.stdout.write(f"--- {DECISION_FILE}\n{line}")
        print(f"spec-check setup: would record `{line.strip()}` in {DECISION_FILE}")
        return 0
    write_plain(path, line)
    print(f"spec-check setup: recorded `{line.strip()}` in {DECISION_FILE}. "
          "Commit it, so nobody's agent asks again.")
    if value == ENFORCE:
        print("spec-check setup: to show the rule to agents drafting a proposal, add it to "
              "OpenSpec's config under rules: proposal: (optional; `check` enforces it "
              "either way). spec-check's SKILL.md, \"Setting up a repository\", has the lines.")
    return 0


def cmd_state(args):
    state, problem = read_decision(repo_root(args.repo))
    print(state)
    if problem:
        print(problem, file=sys.stderr)
    return 0


# -- the proposal hook ---------------------------------------------------------

# A proposal, under an openspec/ directory at any depth; archived changes
# (openspec/changes/archive/<name>/) have one more level, so they never match.
# Wherever the proposal is, the decision read is the repository top's.
PROPOSAL_PATH = re.compile(r"/openspec/changes/[^/]+/proposal\.md$")


def proposal_hook_message(payload):
    """What the proposal hook tells the agent, or None to stay silent.

    payload is a PostToolUse hook's input, from Claude Code or Cursor. The
    path is tool_input's file_path (Claude Code), or path or target_file:
    Cursor does not document its Write tool's input, so all three are read."""
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    found = []
    if isinstance(tool_input, dict):
        found += [tool_input.get(k) for k in ("file_path", "path", "target_file")]
    path = next((p for p in found if isinstance(p, str) and p), None)
    if path is None:
        return None
    if not os.path.isabs(path):
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            return None
        path = os.path.join(cwd, path)
    path = os.path.normpath(path).replace(os.sep, "/")
    m = PROPOSAL_PATH.search(path)
    if not m:
        return None
    out = subprocess.run(["git", "-C", path[:m.start()] or "/", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, timeout=5)
    top = out.stdout.strip()
    # check, sign and the commit hook read only the top's openspec/, so a
    # proposal under a nested one is judged by the top's decision. When the
    # top has no openspec/, the hook says nothing.
    if (out.returncode != 0 or not top or not os.path.isdir(os.path.join(top, "openspec"))
            or read_decision(top)[0] != UNDECIDED):
        return None
    script = os.path.abspath(__file__)
    run = f"python3 {shlex.quote(script)} setup --repo {shlex.quote(top)}"
    return ("This repository has not decided on spec-check's decisions-first rule. "
            f"Before finishing this proposal, ask the user whether to enforce it (`{run}`) "
            f"or turn it off (`{run} --decline`), then follow spec-check's SKILL.md, "
            "\"Setting up a repository\".")


def cmd_proposal_hook(args):
    """Never blocks and fails open: any error means silence."""
    try:
        message = proposal_hook_message(json.loads(sys.stdin.read()))
    except Exception:  # noqa: BLE001 - a hook that crashes must stay quiet
        return 0
    if not message:
        return 0
    if args.host == "claude":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": message}}))
    elif args.host == "cursor":
        print(json.dumps({"additional_context": message}))
    else:
        print(message, file=sys.stderr)
    return 0


# -- the trailer -----------------------------------------------------------

VALUE = re.compile(r"^✓ ([0-9a-f]{12})(?: |$)")


def is_skip(value):
    return value.strip()[:7].lower() == "skipped"


def staged_targets(repo):
    out = git(repo, "diff", "--cached", "--name-only", "--no-renames", "--", ":(top)openspec/")
    paths = out.stdout.splitlines()
    changes, specs = set(), False
    for p in paths:
        parts = p.split("/")
        if parts[1:2] == ["specs"]:
            specs = True
        elif parts[1:2] == ["changes"] and len(parts) > 3 and parts[2] != "archive":
            changes.add(parts[2])
    return paths, sorted(changes), specs


def cmd_sign(args):
    repo = repo_root(args.repo)
    paths, changes, specs = staged_targets(repo)
    if not paths:
        print("spec-check sign: nothing staged under openspec/, so this commit needs no "
              "Spec-check trailer", file=sys.stderr)
        return 1
    tree = git(repo, "write-tree").stdout.strip()
    base_ref = args.base or default_base(repo)
    headings = args.decisions_heading or DECISIONS_HEADINGS
    with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
        materialize(repo, tree, tmp, allow_empty=True)
        staged = Corpus(tmp)
        targets = [c for c in changes if c in staged.changes]
        targets += ["specs"] if specs and staged.specs else []
        if not targets:
            # Only deletions or archive moves: nothing open is left to check.
            print(f"{KEY}: \u2713 {tree[:12]} no open change or spec staged")
            return 0
        res = run_checks(tmp, repo, base_ref, targets, headings, not args.no_validate,
                         bool(args.base), tree)
    errors = print_report(*res, base_ref, "the staged tree", False)
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
    reader = "a fresh subagent" if args.read == "subagent" else "its author, no subagent"
    print(f"\n{KEY}: \u2713 {tree[:12]} 0 errors, {len(res[2])} checks; validate {validate}; "
          f"read by {reader}; {args.amended} amended, {args.open} open")
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="spec_check.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="mechanical checks over changes or specs")
    c.add_argument("targets", nargs="*")
    c.add_argument("--repo")
    c.add_argument("--ref", help="read openspec/ from this git ref, not the working tree")
    c.add_argument("--base", help="the ref citations are checked against (default: origin/HEAD, origin/main, main)")
    c.add_argument("--decisions-heading", action="append",
                   help="a heading the proposal may open with (repeatable; matched as a prefix)")
    c.add_argument("--no-validate", action="store_true")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("setup", help=f"record in {DECISION_FILE} that this repository enforces "
                                     "the decisions-first rule, or with --decline that it does not")
    s.add_argument("--repo", help="a directory in the repository (default: the working directory)")
    s.add_argument("--decline", action="store_true",
                   help="record that this repository does not enforce the rule")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_setup)

    st = sub.add_parser("state", help="print enforce, off, undecided or invalid: what "
                                      f"{DECISION_FILE} says about the decisions-first rule")
    st.add_argument("--repo", help="a directory in the repository (default: the working directory)")
    st.set_defaults(fn=cmd_state)

    ph = sub.add_parser("proposal-hook", help="the hook run after a file is written")
    ph.add_argument("--host", default="")
    ph.set_defaults(fn=cmd_proposal_hook)

    g = sub.add_parser("sign", help="check the staged openspec change and print the trailer")
    g.add_argument("--read", required=True, choices=["subagent", "self"],
                   help="who did the consistency read")
    g.add_argument("--amended", type=int, default=0, help="amendments the read led to")
    g.add_argument("--open", type=int, default=0, help="open questions left in the proposal")
    g.add_argument("--repo")
    g.add_argument("--base")
    g.add_argument("--decisions-heading", action="append")
    g.add_argument("--no-validate", action="store_true")
    g.set_defaults(fn=cmd_sign)

    v = sub.add_parser("verify-staged")
    v.add_argument("line")
    v.set_defaults(fn=cmd_verify_staged)

    vc = sub.add_parser("verify-commit")
    vc.add_argument("sha")
    vc.add_argument("value")
    vc.set_defaults(fn=cmd_verify_commit)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Fatal as e:
        print(f"spec-check: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
