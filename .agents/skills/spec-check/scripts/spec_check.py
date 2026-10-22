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

A change whose proposal.md has `Builds on: <change> (<owner>/<repo>#<number>)`
lines is checked against the specs of the tree being checked with those
changes applied. Each is read from its pull request with gh and git, which
needs the network; a dependency that cannot be read is an error, never
skipped.

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
import urllib.parse

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


def git(repo, *args, check=True, binary=False, stdin=None, env=None):
    result = subprocess.run(
        ["git", "-C", repo, "-c", "log.showSignature=false", *args],
        capture_output=True, input=stdin, text=not binary, env=env,
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
        # Set only on a requirement of the base a change is checked against
        # (the tree's specs, plus any dependencies): cap is the capability it
        # belongs to there. dep is the dependency that defined or renamed it,
        # or None for a requirement of the tree's own specs.
        self.cap = None
        self.dep = None

    def restated(self, name=None, cap=None, dep=None):
        """A copy for the base a change is checked against, under a new name
        if one is given. It shares its text and scenario lists with this
        requirement."""
        r = Req(self.path, self.line, name or self.name, None)
        r.text, r.scenarios = self.text, self.scenarios
        r.cap, r.dep = cap, dep
        return r

    def where(self, line=None):
        at = f"{self.path}:{line or self.line}"
        return f"{at} in {self.dep.slug}#{self.dep.number}" if self.dep else at

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
RENAMED_TO = re.compile(r"\bTO:\s*`?\s*#*\s*Requirement:\s*(.+?)\s*`?\s*$")


def renamed_pairs(text):
    """(old name, new name, line of the FROM line) for each rename in one
    delta spec."""
    pairs, section, old = [], None, None
    for n, raw, fenced in markdown_lines(text):
        if fenced:
            continue
        m = HEADING.match(raw)
        if m and len(m.group(1)) == 2:
            d = DELTA.match(m.group(2))
            section, old = (d.group(1).upper() if d else None), None
            continue
        if section != "RENAMED":
            continue
        f = RENAMED_FROM.search(raw)
        if f:
            old = (f.group(1).strip(), n)
            continue
        t = RENAMED_TO.search(raw)
        if t and old:
            pairs.append((old[0], t.group(1).strip(), old[1]))
            old = None
    return pairs


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
                    for r in self.specs[rel]:
                        r.cap = cap
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
        retired_by_change = corpus.texts.get(f"openspec/changes/{parts[2]}/specs/{spec.cap}/spec.md")
        if retired_by_change and spec.name.lower() in retired_names(retired_by_change):
            return True
    return False


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
            # A MODIFIED requirement restates the one it modifies, so copies
            # under one requirement name are expected.
            others = [(o, ol) for o, ol in places
                      if o is not r and o.name.lower() != r.name.lower()
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


# -- stacked changes -------------------------------------------------------------

# A change that applies on top of another open change says so in its
# proposal.md, one line per dependency, in the order they apply to main:
#
#     Builds on: seat-files (adamstallard/igor#171)
#
# It is then checked against the specs of the tree being checked, with each
# dependency's delta applied (DECISIONS.md, "A stacked change declares what it
# builds on").
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
        self.proposal = None  # its proposal.md text at that commit
        self.head_archive = None  # the archive directory there, when that commit archives it
        self._history = {}

    def delta_path(self, cap):
        return f"openspec/changes/{self.change}/specs/{cap}/spec.md"

    def history(self, repo, cap):
        """The earlier texts of its delta for cap, newest first, from the
        HISTORY_DEPTH latest commits touching it in the history of the commit
        it was read from."""
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


def read_text(path):
    """A file's text on disk, or None if it cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def has_commit(repo, sha):
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def archives_of(names, change):
    """The archive directories among names that hold a change of this name,
    newest first."""
    return sorted((n for n in names if re.fullmatch(ARCHIVED + re.escape(change), n)), reverse=True)


def archived_as(names, change):
    """The newest archive directory among names named for change, or None.
    It goes by the name alone, so it only guesses: it names a possible
    archive in an error message, and archive_of_dep decides."""
    return next(iter(archives_of(names, change)), None)


def same_text(a, b):
    """Whether two texts match, ignoring line endings and surrounding blank
    space."""
    return a is not None and b is not None and \
        "\n".join(a.splitlines()).strip() == "\n".join(b.splitlines()).strip()


def archive_of_dep(names, dep, read):
    """The archive directory among names that holds dep's own change, or
    None. A directory counts when it is named for the change and its
    proposal.md has the same text as the proposal at dep's pull request's
    head; read(directory) gives that proposal.md. A change name can be
    reused after an older change of that name was archived, so the name
    alone does not tell."""
    return next((d for d in archives_of(names, dep.change)
                 if same_text(read(d), dep.proposal)), None)


def archive_names(repo, treeish):
    out = git(repo, "ls-tree", "--name-only", treeish, "--", "openspec/changes/archive/", check=False)
    return [p.rsplit("/", 1)[-1] for p in out.stdout.splitlines()] if out.returncode == 0 else []


def pr_info(repo, dep):
    """gh's view of the dependency's pull request. Raises StackError."""
    try:
        info = json.loads(gh(repo, "pr", "view", str(dep.number), "--repo", dep.slug, "--json",
                             "state,headRefName,headRefOid,isCrossRepository"))
    except ValueError as e:
        raise StackError(f"gh gave unreadable output for #{dep.number}: {e}") from e
    if not isinstance(info, dict):
        raise StackError(f"gh gave unreadable output for #{dep.number}")
    return info


def load_dep(repo, dep, info):
    """Reads the dependency's change from its pull request's head commit,
    fetching it first if it is not here. info is pr_info's result. When that
    commit archives the change instead, sets tree, proposal and
    head_archive, and no deltas. Raises StackError."""
    remote = remote_for(repo, dep.slug)
    if remote is None:
        raise StackError(f"no git remote here fetches from {dep.slug}; a change can build only "
                         "on a change in its own repository")
    if info.get("state") == "CLOSED":
        raise StackError(f"pull request #{dep.number} was closed without merging")
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
    dep.tree = oid
    prefix = f"openspec/changes/{dep.change}/"
    paths = git(repo, "ls-tree", "-r", "--name-only", oid, "--", prefix).stdout.splitlines()
    if not paths:
        there = archived_as(archive_names(repo, oid), dep.change)
        if not there:
            raise StackError(f"#{dep.number}'s branch has no open change {dep.change}")
        dep.head_archive = there
        dep.proposal = show_text(repo, oid, f"openspec/changes/archive/{there}/proposal.md")
        return
    for p in paths:
        parts = p.split("/")
        if len(parts) == 6 and parts[3] == "specs" and parts[5] == "spec.md":
            text = show_text(repo, oid, p)
            if text is None:
                raise StackError(f"cannot read {p} from #{dep.number}'s head commit")
            dep.deltas[parts[4]] = text
        elif p == prefix + "proposal.md":
            dep.proposal = show_text(repo, oid, p)
            own, _ = builds_on(dep.proposal or "", p)
            dep.builds_on = [(d.change, d.label) for d in own]


class Stack:
    """The base a stacked change is checked against: the specs of the tree
    being checked, with each dependency's delta applied in the listed order.
    Each delta is applied as `openspec archive` would: renames, then
    removals, then modifications, then additions."""

    def __init__(self, corpus):
        self.caps = {}       # capability -> [Req]
        for path, reqs in corpus.specs.items():
            self.caps.setdefault(path.split("/")[2], []).extend(reqs)
        self.gone = {}       # (capability, lowercased name) -> (Dep, what it did)
        self.deps = []       # the dependencies applied

    def find(self, cap, name):
        return next((r for r in self.caps.get(cap, []) if r.name.lower() == name.lower()), None)

    def base(self):
        return [r for reqs in self.caps.values() for r in reqs]

    def apply(self, dep):
        """Applies dep's delta. Raises StackError when it does not apply."""
        problems = []
        for cap, text in sorted(dep.deltas.items()):
            path, cur = dep.delta_path(cap), self.caps.setdefault(cap, [])

            def at(name):
                return next((i for i, r in enumerate(cur) if r.name.lower() == name.lower()), None)

            reqs = parse_spec(path, text)
            for old, new, _ in renamed_pairs(text):
                i = at(old)
                if i is None:
                    problems.append(f'it renames "{old}" in {cap}, which is not there')
                    continue
                cur[i] = cur[i].restated(name=new, cap=cap, dep=dep)
                self.gone[(cap, old.lower())] = (dep, f'renames to "{new}"')
            for r in reqs:
                if r.section != "REMOVED":
                    continue
                i = at(r.name)
                if i is None:
                    problems.append(f'it removes "{r.name}" from {cap}, which is not there')
                    continue
                del cur[i]
                self.gone[(cap, r.name.lower())] = (dep, "removes")
            for r in reqs:
                if r.section != "MODIFIED":
                    continue
                i = at(r.name)
                if i is None:
                    problems.append(f'it modifies "{r.name}" in {cap}, which is not there')
                    continue
                cur[i] = r.restated(cap=cap, dep=dep)
            for r in reqs:
                if r.section != "ADDED":
                    continue
                if at(r.name) is not None:
                    problems.append(f'it adds "{r.name}" to {cap}, which is already there')
                    continue
                cur.append(r.restated(cap=cap, dep=dep))
        if problems:
            raise StackError("it does not apply on top of main" +
                             (" and the dependencies listed before it" if self.deps else "") +
                             ": " + "; ".join(problems))
        self.deps.append(dep)


def build_stack(change, corpus, repo, base):
    """(Stack or None, [Finding], complete) for one change. The stack is None
    only when the proposal has no `Builds on:` line at all, readable or not.
    complete is False when the stack is not what the change builds on: a
    line could not be read, the change names itself, a dependency could not
    be read or applied, or its archive is on the base branch but not in the
    tree. A dependency archived in the tree is an error that leaves complete
    True, because the tree's specs already hold its result."""
    path = f"openspec/changes/{change}/proposal.md"
    deps, findings = builds_on(corpus.texts.get(path, ""), path)
    if not deps and not findings:
        return None, [], True
    stack, complete = Stack(corpus), not findings
    here = [d for d in os.listdir(os.path.join(corpus.root, "openspec", "changes", "archive"))] \
        if os.path.isdir(os.path.join(corpus.root, "openspec", "changes", "archive")) else []
    on_base = archive_names(repo, base.ref) if base.ok else []
    listed = []

    def stop(dep, why):
        findings.append(Finding(path, dep.line, "error", "stack", f"{dep.label}: {why}"))
        return findings[-1]

    blocker = findings[0] if findings else None
    for dep in deps:
        if dep.change == change:
            blocker = stop(dep, "a change cannot build on itself")
            complete = False
            listed.append(dep.change)
            continue
        if not complete:
            listed.append(dep.change)
            continue
        try:
            info = pr_info(repo, dep)
            load_dep(repo, dep, info)
        except StackError as e:
            why = str(e)
            here_dir, base_dir = archived_as(here, dep.change), archived_as(on_base, dep.change)
            if here_dir or base_dir:
                why += (f"; an archived change of that name exists "
                        f"(openspec/changes/archive/{here_dir or base_dir}): if it is this one, "
                        + ("" if here_dir else f"rebase onto {base.ref}, then ")
                        + f"remove the `{dep.declaration}` line")
            blocker = stop(dep, why)
            complete = False
            listed.append(dep.change)
            continue
        # An archive is the dependency's only when its pull request has
        # merged and the archive's proposal.md is the one the pull request
        # has (archive_of_dep): a change name can be reused.
        merged = info.get("state") == "MERGED"
        here_dir = merged and archive_of_dep(here, dep, lambda d: read_text(os.path.join(
            corpus.root, "openspec", "changes", "archive", d, "proposal.md")))
        if here_dir:
            stop(dep, f"archived as openspec/changes/archive/{here_dir}, so main's specs already "
                      f"hold its result: remove the `{dep.declaration}` line")
            listed.append(dep.change)
            continue
        base_dir = merged and archive_of_dep(on_base, dep, lambda d: show_text(
            repo, base.ref, f"openspec/changes/archive/{d}/proposal.md"))
        if base_dir:
            blocker = stop(dep, f"archived on {base.ref}, but not in the tree checked here: rebase onto "
                      f"{base.ref}, then remove the `{dep.declaration}` line")
            complete = False
            listed.append(dep.change)
            continue
        try:
            if dep.head_archive:
                raise StackError(
                    f"#{dep.number}'s branch has no open change {dep.change}; it is archived there "
                    f"as {dep.head_archive}, so once #{dep.number} merges, main holds its result: "
                    f"then remove the `{dep.declaration}` line")
            missing = [label for name, label in dep.builds_on
                       if name not in listed and not archived_as(here, name)]
            if missing:
                raise StackError(
                    f"{dep.label} builds on " + " and ".join(missing) +
                    "; list " + ("each" if len(missing) > 1 else "it") +
                    f" in its own `Builds on:` line before {dep.change}'s line")
            stack.apply(dep)
        except StackError as e:
            blocker = stop(dep, str(e))
            complete = False
        listed.append(dep.change)
    if not complete:
        blocker.message += ("; duplicate and drift checks did not run for this change, which "
                            "is checked against main plus every dependency or not at all")
    return stack, findings, complete


def stale_sentences(r, current, repo):
    """Sentences of r, the stacked change's version of a requirement, that
    the dependency has since replaced. Each earlier text of the dependency's
    requirement is compared with its current text. A sentence of r counts
    when the earlier text has it, the current text does not, and the current
    text has a sentence the earlier one lacks and r lacks too: r kept the old
    wording and missed the new one. A sentence the dependency only dropped
    is not drift, because a stack is often made by moving a rule out of the
    dependency into the stacked change."""
    dep, now = current.dep, {normalize(t) for _, t in units(current)}
    have = {normalize(t) for _, t in units(r)}
    stale = set()
    for text in dep.history(repo, current.cap):
        for old in parse_spec(dep.delta_path(current.cap), text):
            if old.name.lower() != current.name.lower():
                continue
            then = {normalize(t) for _, t in units(old)}
            if now - then - have:
                stale |= (then - now) & have
    return [(line, t) for line, t in units(r)
            if normalize(t) in stale and len(normalize(t).split()) >= DUPLICATE_MIN_WORDS]


def check_drift(change, corpus, stack, repo, out):
    """Each requirement the stacked change modifies, removes or renames must
    be in main plus its dependencies, and a modified one must not keep text
    its dependency has since replaced."""
    for rel, reqs in corpus.changes[change].items():
        parts = rel.split("/")
        if len(parts) != 6:
            continue
        cap = parts[4]
        # OpenSpec applies a change's renames before its modifications, so a
        # MODIFIED name may be the new side of the change's own rename.
        own_renames = {new.lower(): old for old, new, _ in renamed_pairs(corpus.texts[rel])}
        touched = [(r.line, r.name, "modifies" if r.section == "MODIFIED" else "removes", r)
                   for r in reqs if r.section in ("MODIFIED", "REMOVED")]
        touched += [(line, old, "renames", None)
                    for old, _, line in renamed_pairs(corpus.texts[rel])]
        for line, name, verb, r in touched:
            renamed_from = own_renames.get(name.lower()) if verb == "modifies" else None
            current = stack.find(cap, renamed_from or name)
            if current is None and renamed_from:
                continue  # the change's "renames" entry in touched reports the old name
            if current is None:
                gone = stack.gone.get((cap, name.lower()))
                if gone:
                    why = f"which {gone[0].label} {gone[1]}"
                else:
                    defined = next((d for d in stack.deps if any(
                        o.name.lower() == name.lower()
                        for t in d.history(repo, cap) for o in parse_spec(d.delta_path(cap), t))), None)
                    why = (f"which an earlier version of {defined.label} defined and its current one "
                           "does not" if defined else "which neither main nor its dependencies define")
                out.append(Finding(rel, line, "error", "drift", f'{verb} "{name}" in {cap}, {why}; '
                                   "write this change against what it builds on now"))
                continue
            if verb != "modifies" or current.dep is None:
                continue
            stale = stale_sentences(r, current, repo)
            if stale:
                first = stale[0][1]
                more = f" (and {len(stale) - 1} more)" if len(stale) > 1 else ""
                out.append(Finding(rel, stale[0][0], "error", "drift",
                                   f'"{name}" keeps "{first[:60]}..."{more}, from an earlier text '
                                   f"{current.dep.label} gave it, which now reads differently; "
                                   f"restate it from {current.dep.change}'s current text"))


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
                wanted.setdefault(cap, set()).add(name.lower())
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
            m = re.fullmatch(r"openspec/changes/([^/]+)/specs/([^/]+)/spec\.md", f.get("path", ""))
            if m and m.group(1) != "archive" and m.group(2) in wanted:
                reads.append((pr["number"], pr.get("headRefOid", ""), m.group(1), m.group(2), m.group(0)))
    retiring = {}  # (cap, lowercased name) -> [(change, number)]
    for number, oid, change, cap, path in reads[:HINT_READS]:
        try:
            text = gh(repo, "api", "-H", "Accept: application/vnd.github.raw",
                      f"repos/{slug}/contents/{urllib.parse.quote(path)}?ref={oid}")
        except StackError:
            continue
        for name in retired_names(text) & wanted[cap]:
            retiring.setdefault((cap, name), []).append((change, number))
    for f in findings:
        if not f.retirable:
            continue
        change, matched = f.retirable
        lines = []
        for cap, name in matched:
            for dep_change, number in retiring.get((cap, name.lower()), []):
                line = f"Builds on: {dep_change} ({slug}#{number})"
                if dep_change != change and dep_change not in declared.get(change, ()) \
                        and line not in lines:
                    lines.append(line)
                    retired = name
        if lines:
            f.message += (f'. An open pull request removes or renames "{retired}": if this change '
                          "applies on top of it, add " + " or ".join(f"`{l}`" for l in lines) +
                          " to its proposal.md (spec-check's SKILL.md, \"Stacked changes\")")


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
    stacks, declared = [], {}
    for change in changes:
        reqs = [r for rs in corpus.changes[change].values() for r in rs]
        if state == ENFORCE:
            check_decisions(change, corpus, headings, findings)
        check_scenarios(reqs, findings)
        stack, problems, complete = build_stack(change, corpus, repo, base)
        findings += problems
        if stack is None:
            check_duplicates(reqs, corpus, findings)
        elif complete:
            deps = {d.change for d in stack.deps}
            declared[change] = deps
            if stack.deps:
                stacks.append((change, stack.deps))
            check_duplicates(reqs, corpus, findings, stack.base(), deps)
            check_drift(change, corpus, stack, repo, findings)
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
    add_hints(repo, findings, declared)
    return changes, specs, findings, statuses, state, stacks


def print_report(changes, specs, findings, statuses, state, stacks, base_ref, source, as_json):
    errors = sum(1 for f in findings if f.severity == "error")
    checks = len(findings) - errors
    if as_json:
        print(json.dumps({
            "source": source, "base": base_ref, "changes": changes, "specs": specs,
            "errors": errors, "checks": checks, "decisions_first": state,
            "findings": [f.as_dict() for f in findings],
            "openspec_validate": {k: v for k, v in statuses},
            "builds_on": {c: [{"change": d.change, "repo": d.slug, "number": d.number,
                               "commit": d.tree} for d in deps] for c, deps in stacks},
        }, indent=2))
        return errors
    for f in findings:
        print(f.text())
    if findings:
        print()
    for change, deps in stacks:
        print(f"{change} builds on " + ", then ".join(
            f"{d.change} ({d.slug}#{d.number} at {d.tree[:12]})" for d in deps) +
            "; checked against main plus " + ("it" if len(deps) == 1 else "them"))
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
