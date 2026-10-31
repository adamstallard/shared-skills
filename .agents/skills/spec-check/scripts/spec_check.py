#!/usr/bin/env python3
"""spec-check: the mechanical half of reviewing an OpenSpec change.

    spec_check.py check [<target>...] [--repo DIR] [--ref REF] [--base REF]
                        [--no-validate] [--json]
    spec_check.py sign --read subagent|self [--amended N] [--open N]
                       [--base REF] [--no-validate]
    spec_check.py verify-staged "Spec-check: <value>"   (message on stdin)
    spec_check.py verify-commit <sha> <value>

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
dependencies. Each refusal is an error. Without the CLI, a change archived
alone is reported as not run, and a stacked change gets an error.

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
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
DELTA = re.compile(r"^(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.I)
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
    # The peeled tree, not a commit: a commit's archive starts with a pax
    # header, so one with no file in it is a tar that tarfile cannot open.
    out = git(repo, "archive", "--format=tar", f"{treeish}^{{tree}}", "--", "openspec",
              check=False, binary=True)
    if out.returncode != 0:
        raise Fatal(f"cannot read openspec/ from {treeish}: "
                    f"{out.stderr.decode('utf-8', 'replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python before 3.12 has no filter argument
            tar.extractall(dest)


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
    heading, a requirement or a citation.

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
        self.stray = []       # (line, title) of each other `###` heading inside it
        # Set only on a requirement of the base a change is checked against
        # (the tree's specs, plus any dependencies): cap is the capability it
        # belongs to there. dep is the dependency that defined or renamed it,
        # or None for a requirement of the tree's own specs.
        self.cap = None
        self.dep = None
        # Its name where it was read from, when the base holds it under
        # another name, for example after a later dependency renames it.
        self.own = None
        # Set on a requirement read from an OpenSpec block (block_req): the
        # block's lines below its header, as block_body gives them.
        self.block = None

    def restated(self, name=None, cap=None, dep=None):
        """A copy for the base a change is checked against, under a new name
        if one is given. It shares its text and scenario lists with this
        requirement."""
        r = Req(self.path, self.line, name or self.name, None)
        r.text, r.scenarios = self.text, self.scenarios
        r.cap, r.dep, r.own = cap, dep, self.own or self.name
        r.block = self.block
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


# -- OpenSpec's delta reader ---------------------------------------------------
#
# A port of the reader `openspec archive` applies a delta with: OpenSpec
# 1.6.0, dist/core/parsers/requirement-blocks.js. spec-check reads every
# requirement header, delta and main spec through it, so the two agree on
# what a delta says (DECISIONS.md, "A stacked change declares what it builds
# on"). The functions keep OpenSpec's names. One addition: each block,
# removed name and renamed pair also carries the 1-based line it starts on,
# for findings.

REQUIREMENT_HEADER_REGEX = re.compile(r"^###\s*Requirement:\s*(.+)\s*$", re.I)
REQUIREMENTS_SECTION = re.compile(r"^##\s+Requirements\s*$", re.I)
TOP_LEVEL_SECTION = re.compile(r"^(##)\s+(.+)$")
SECTION_START = re.compile(r"^##\s+")
REMOVED_BULLET = re.compile(r"^\s*-\s*`?###\s*Requirement:\s*(.+?)`?\s*$")
RENAMED_FROM = re.compile(r"^\s*-?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$")
RENAMED_TO = re.compile(r"^\s*-?\s*TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$")


def normalize_requirement_name(name):
    return name.strip()


def normalize_line_endings(content):
    return re.sub(r"\r\n?", "\n", content)


class RequirementBlock:
    def __init__(self, header_line, name, raw, line):
        self.header_line, self.name, self.raw, self.line = header_line, name, raw, line


def extract_requirements_section(content):
    """The `## Requirements` section of a main spec, as OpenSpec splits it:
    {before, header_line, preamble, body_blocks, after}."""
    lines = normalize_line_endings(content).split("\n")
    req_header_index = next((i for i, l in enumerate(lines) if REQUIREMENTS_SECTION.match(l)), -1)
    if req_header_index == -1:
        before = content.rstrip()
        return {"before": before + "\n\n" if before else "", "header_line": "## Requirements",
                "preamble": "", "body_blocks": [], "after": "\n"}
    end_index = next((i for i in range(req_header_index + 1, len(lines))
                      if SECTION_START.match(lines[i])), len(lines))
    before = "\n".join(lines[:req_header_index])
    body = lines[req_header_index + 1:end_index]
    blocks, cursor, preamble = [], 0, []
    while cursor < len(body) and not REQUIREMENT_HEADER_REGEX.match(body[cursor]):
        preamble.append(body[cursor])
        cursor += 1
    while cursor < len(body):
        header_start = cursor
        m = REQUIREMENT_HEADER_REGEX.match(body[cursor])
        if not m:
            cursor += 1
            continue
        name = normalize_requirement_name(m.group(1))
        cursor += 1
        block_lines = [body[header_start]]
        while cursor < len(body) and not REQUIREMENT_HEADER_REGEX.match(body[cursor]) \
                and not SECTION_START.match(body[cursor]):
            block_lines.append(body[cursor])
            cursor += 1
        blocks.append(RequirementBlock(body[header_start], name, "\n".join(block_lines).rstrip(),
                                       req_header_index + header_start + 2))
    after = "\n".join(lines[end_index:])
    return {"before": before + "\n" if before.rstrip() else before,
            "header_line": lines[req_header_index], "preamble": "\n".join(preamble).rstrip(),
            "body_blocks": blocks, "after": after if after.startswith("\n") else "\n" + after}


def split_top_level_sections(content):
    """{title: (body, line of its first body line)} for each `## ` section.
    A later section with the same title replaces the earlier one's body and
    keeps the earlier one's position, as OpenSpec does."""
    lines = content.split("\n")
    indices = []
    for i, line in enumerate(lines):
        m = TOP_LEVEL_SECTION.match(line)
        if m:
            indices.append((m.group(2).strip(), i))
    result = {}
    for k, (title, index) in enumerate(indices):
        end = indices[k + 1][1] if k + 1 < len(indices) else len(lines)
        result[title] = ("\n".join(lines[index + 1:end]), index + 2)
    return result


def get_section_case_insensitive(sections, desired):
    """(body, line of its first body line, found) of the first section whose
    title is desired, ignoring case."""
    for title, (body, start) in sections.items():
        if title.lower() == desired.lower():
            return body, start, True
    return "", 0, False


def parse_requirement_blocks_from_section(section_body, body_start_line):
    if not section_body:
        return []
    lines = normalize_line_endings(section_body).split("\n")
    blocks, i = [], 0
    while i < len(lines):
        while i < len(lines) and not REQUIREMENT_HEADER_REGEX.match(lines[i]):
            i += 1
        if i >= len(lines):
            break
        header_line, start = lines[i], i
        m = REQUIREMENT_HEADER_REGEX.match(header_line)
        name = normalize_requirement_name(m.group(1))
        buf = [header_line]
        i += 1
        while i < len(lines) and not REQUIREMENT_HEADER_REGEX.match(lines[i]) \
                and not SECTION_START.match(lines[i]):
            buf.append(lines[i])
            i += 1
        blocks.append(RequirementBlock(header_line, name, "\n".join(buf).rstrip(), body_start_line + start))
    return blocks


def parse_removed_names(section_body, body_start_line):
    """[(name, line)]: requirement headers, and the bullet form
    "- `### Requirement: name`"."""
    if not section_body:
        return []
    names = []
    for i, line in enumerate(normalize_line_endings(section_body).split("\n")):
        m = REQUIREMENT_HEADER_REGEX.match(line) or REMOVED_BULLET.match(line)
        if m:
            names.append((normalize_requirement_name(m.group(1)), body_start_line + i))
    return names


def parse_renamed_pairs(section_body, body_start_line):
    """[(from, to, line of its FROM line)]. FROM, TO and `Requirement:` are
    matched with their case, as OpenSpec matches them in a rename line,
    unlike a block's header, which matches in any case."""
    if not section_body:
        return []
    pairs, current = [], {}
    for i, line in enumerate(normalize_line_endings(section_body).split("\n")):
        f = RENAMED_FROM.match(line)
        t = RENAMED_TO.match(line)
        if f:
            current["from"] = (normalize_requirement_name(f.group(1)), body_start_line + i)
        elif t:
            current["to"] = normalize_requirement_name(t.group(1))
            if current.get("from") and current["from"][0] and current.get("to"):
                pairs.append((current["from"][0], current["to"], current["from"][1]))
                current = {}
    return pairs


def parse_delta_spec(content):
    """{added, modified: [RequirementBlock], removed: [(name, line)],
    renamed: [(from, to, line)]} of one delta spec."""
    sections = split_top_level_sections(normalize_line_endings(content))
    plan = {}
    for key, title in (("added", "ADDED Requirements"), ("modified", "MODIFIED Requirements"),
                       ("removed", "REMOVED Requirements"), ("renamed", "RENAMED Requirements")):
        body, start, _ = get_section_case_insensitive(sections, title)
        read = {"removed": parse_removed_names,
                "renamed": parse_renamed_pairs}.get(key, parse_requirement_blocks_from_section)
        plan[key] = read(body, start)
    return plan


def parse_spec(rel, text):
    """Requirements in one spec.md, main or delta. A requirement header is
    one OpenSpec reads (REQUIREMENT_HEADER_REGEX), named as OpenSpec names
    it."""
    reqs, section, req, scen = [], None, None, None
    for n, raw, fenced in markdown_lines(text):
        h = None if fenced else REQUIREMENT_HEADER_REGEX.match(raw)
        if h:
            req = Req(rel, n, normalize_requirement_name(h.group(1)), section)
            reqs.append(req)
            scen = None
            continue
        m = None if fenced else HEADING.match(raw)
        if m:
            level, title = len(m.group(1)), m.group(2)
            if level == 2:
                d = DELTA.match(title)
                section = d.group(1).upper() if d else None
                req = scen = None
                continue
            s = SCENARIO.match(title) if level == 4 else None
            if s and req is not None:
                scen = Scenario(n, s.group(1).strip())
                req.scenarios.append(scen)
                continue
            if level == 3 and req is not None:
                # OpenSpec's block runs on to the next requirement header,
                # so what follows still belongs to the requirement here.
                # check_scenarios reports the heading itself.
                req.stray.append((n, title))
                scen = None
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


def block_body(raw):
    """An OpenSpec block's lines below its header: every line up to the next
    requirement header or `## ` line, subsections included, each without
    surrounding blank space, with runs of blank lines made one. Two versions
    of a requirement are the same when these match, case and emphasis
    included, as OpenSpec keeps them. The header line itself is left out."""
    lines = [line.strip() for line in normalize_line_endings(raw).split("\n")[1:]]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def block_req(rel, block, section):
    """parse_spec's reading of one OpenSpec block, at its own lines in
    rel, under OpenSpec's name for it."""
    found = parse_spec(rel, "\n" * (block.line - 1) + block.raw)
    r = found[0] if found else Req(rel, block.line, block.name, section)
    r.name, r.section, r.block = block.name, section, block_body(block.raw)
    return r


def spec_reqs(rel, text):
    """The requirements of one main spec that `openspec archive` matches a
    delta against: the blocks of its `## Requirements` section."""
    return [block_req(rel, b, None) for b in extract_requirements_section(text)["body_blocks"]]


def retired_names(text):
    """Names of the requirements one delta spec removes or renames away
    from, exactly as OpenSpec matches them."""
    plan = parse_delta_spec(text)
    return {n for n, _ in plan["removed"]} | {old for old, _, _ in plan["renamed"]}


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
        for line, title in r.stray:
            out.append(Finding(r.path, line, "error", "stray-heading",
                               f'"### {title}" inside requirement "{r.name}" is neither a '
                               "requirement nor a scenario: OpenSpec's validator gives the "
                               "scenarios after it to the heading, not the requirement, so the "
                               "spec fails validation (a main spec once its change is archived). "
                               "Remove the heading or make it plain text"))
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
        if retired_by_change and spec.name in retired_names(retired_by_change):
            return True
    return False


def capability(r):
    """The capability r belongs to: the one it was read under in the base,
    or for a requirement of a change, the directory of its delta spec."""
    if r.cap is not None:
        return r.cap
    parts = r.path.split("/")
    return parts[4] if len(parts) > 5 and parts[1:2] == ["changes"] and parts[3] == "specs" else None


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
        if r.section == "REMOVED":
            continue  # the change deletes its text, so it states no rule
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
        self._history = {}

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
        if len(parts) == depth + 3 and parts[depth] == "specs" and parts[-1] == "spec.md":
            text = read(p)
            if text is None:
                raise StackError(f"cannot read {p} {where}")
            dep.deltas[parts[depth + 1]] = text
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
ARCHIVE_TIMEOUT = 120
TASKS_DONE = "## 1. Tasks\n\n- [x] 1.1 Done\n"


def openspec_exe():
    """The OpenSpec CLI, or None when it is not on PATH."""
    return shutil.which("openspec")


class Item:
    """One entry of a delta for one capability, as OpenSpec reads it
    (parse_delta_spec): a rename, or a requirement it removes, modifies or
    adds. dep is the dependency it belongs to, or None for the stacked
    change's own."""

    def __init__(self, dep, cap, kind, name, new=None, req=None, block=None, line=None):
        self.dep, self.cap, self.kind, self.name, self.new = dep, cap, kind, name, new
        self.req, self.block, self.line = req, block, line

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
        """Its requirement's block below the header (block_body), for
        comparing; None for a rename or removal."""
        return self.req.block if self.req is not None else None

    def written(self):
        """The item as a delta writes it: a modification or addition is its
        block verbatim."""
        if self.kind == "RENAMED":
            return f"- FROM: `### Requirement: {self.name}`\n- TO: `### Requirement: {self.new}`\n"
        if self.kind == "REMOVED":
            return f"### Requirement: {self.name}\n"
        return self.block + "\n"


def read_delta(rel, text, dep=None, cap=None):
    """One delta spec's items, as OpenSpec reads them, in the order `openspec
    archive` applies them: renames, removals, modifications, additions."""
    plan = parse_delta_spec(text)
    items = [Item(dep, cap, "RENAMED", old, new, line=line) for old, new, line in plan["renamed"]]
    items += [Item(dep, cap, "REMOVED", name, line=line) for name, line in plan["removed"]]
    for kind in ("MODIFIED", "ADDED"):
        items += [Item(dep, cap, kind, b.name, req=block_req(rel, b, kind), block=b.raw, line=b.line)
                  for b in plan[kind.lower()]]
    return items


def items_of(dep):
    """dep's delta items (read_delta), per capability."""
    return {cap: read_delta(dep.spec_path(cap), text, dep, cap)
            for cap, text in sorted(dep.deltas.items())}


def delta_files(items):
    """{capability: delta spec text} holding items. When none of a
    capability's items was dropped, it gets its dependency's delta verbatim;
    otherwise its delta is rebuilt from the items kept, each block verbatim."""
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

    def __init__(self, src, parent):
        self.parent = parent
        self.root = tempfile.mkdtemp(prefix="scratch-", dir=parent)
        home, there = os.path.join(src, "openspec"), os.path.join(self.root, "openspec")
        os.makedirs(there)
        for name in sorted(os.listdir(home)) if os.path.isdir(home) else []:
            p = os.path.join(home, name)
            if name == "specs" and os.path.isdir(p):
                shutil.copytree(p, os.path.join(there, "specs"), ignore_dangling_symlinks=True)
            elif os.path.isfile(p):
                shutil.copyfile(p, os.path.join(there, name))

    def caps(self):
        """{capability: [Req]} of its specs: the requirements `openspec
        archive` matches a delta against (spec_reqs)."""
        found, specs = {}, os.path.join(self.root, "openspec", "specs")
        for cap in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
            path = os.path.join(specs, cap, "spec.md")
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    found[cap] = spec_reqs(f"openspec/specs/{cap}/spec.md", fh.read())
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
        env = dict(os.environ, OPENSPEC_TELEMETRY="0", DO_NOT_TRACK="1")
        try:
            r = subprocess.run([openspec_exe() or "openspec", "archive", name, "--yes", "--no-validate",
                                "--json"], cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=ARCHIVE_TIMEOUT, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            shutil.rmtree(home, ignore_errors=True)
            return [f"`openspec archive` could not run: {e}"]
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(os.path.join(self.root, "openspec", "changes", "archive"), ignore_errors=True)
        try:
            data = json.loads(r.stdout[r.stdout.index("{"):])
        except ValueError:
            data = {}
        if r.returncode == 0 and isinstance(data, dict) and data.get("archive"):
            return []
        status = data.get("status") if isinstance(data, dict) else None
        said = [s["message"] for s in status or [] if isinstance(s, dict) and s.get("message")]
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
        return said or tail[:1]


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
            elif r is not None and r.block == i.text():
                d.present.append(i)
            elif i.kind == "ADDED" and r is not None:
                d.third.append((i, r))
            elif i.kind in ("ADDED", "MODIFIED"):
                d.kept.append(i)
                # The dependency's version now stands under this name, so a later item
                # naming it is compared (r.block == i.text()) with this text, not the old one.
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


class Stack:
    """The base a stacked change is checked against: the specs of the tree
    being checked, with each open dependency's change archived into a
    scratch copy of them by `openspec archive`, after dropping what they
    already show (DECISIONS.md, "Why the real `openspec archive`, and only
    for open dependencies")."""

    def __init__(self, corpus):
        self.caps = {}       # capability -> [Req]
        for path, reqs in corpus.specs.items():
            self.caps.setdefault(path.split("/")[2], []).extend(reqs)
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
        for path in corpus.specs:
            for r in spec_reqs(path, corpus.texts[path]):
                tree.setdefault((path.split("/")[2], r.block), r)
        tags = {(cap, text): (dep, r) for cap, text, dep, r in self.tags}
        self.caps = {}
        for cap, reqs in scratch.caps().items():
            out = self.caps.setdefault(cap, [])
            for r in reqs:
                text = r.block
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
    out = {}
    for rel in sorted(corpus.changes.get(change, {})):
        parts = rel.split("/")
        if len(parts) == 6 and parts[3] == "specs" and parts[5] == "spec.md":
            out[parts[4]] = rel
    return out


def pending_here(dep, corpus):
    """Whether the tree being checked holds dep's change open, under the
    same name, with the same deltas: merged, but not yet archived there."""
    mine = {cap: corpus.texts[rel] for cap, rel in change_deltas(corpus, dep.change).items()}
    return bool(dep.deltas) and set(mine) == set(dep.deltas) and all(
        same_text(mine[c], dep.deltas[c]) for c in mine)


def unreadable_delta(dep):
    """A capability whose delta has text but no item spec-check can read,
    or None. Without this check, such a delta would be left out of the
    stack silently."""
    found = items_of(dep)
    return next((cap for cap, text in sorted(dep.deltas.items())
                 if text.strip() and not found.get(cap)), None)


def check_own(dep, listed, scratch, tree, unread, later):
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
        if not own.deltas:
            continue  # nothing of it could be missing
        cap = unreadable_delta(own)
        if cap:
            raise StackError(f"{dep.label} builds on {own.label}, whose delta for {cap} holds no "
                             "requirement header spec-check can read")
        if in_tree(own):
            missing = not_shown(own, tree, later(own))
            if missing:
                raise StackError(
                    f"{dep.label} builds on {own.label}, which has merged, but this branch does not "
                    f"hold its result ({'; '.join(missing)}). Merge main into your branch")
        elif decide(own, scratch.caps()).kept:
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


NO_OPENSPEC = ("the openspec CLI is not on PATH. A change with `Builds on:` lines is checked "
               "against its dependencies archived by `openspec archive`, so install OpenSpec "
               "(npm install -g @fission-ai/openspec) and run the check again")


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
    if deps and openspec_exe() is None:
        findings.append(Finding(path, deps[0].line, "error", "stack", NO_OPENSPEC))
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


# The refusals `openspec archive` gives for one delta spec (OpenSpec 1.6.0,
# dist/core/specs-apply.js, buildUpdatedSpec). Each names the capability;
# only REFUSAL also names one requirement of the delta.
REFUSAL = re.compile(r'^(\S+) (RENAMED|REMOVED|MODIFIED|ADDED) failed for header '
                     r'"### Requirement: (.*?)"(?: -|$)')
CAP_REFUSAL = re.compile(r"^(\S+?)(?::| validation failed -) ")
NO_SPEC = "target spec does not exist"
NO_OPERATIONS = re.compile(r"^Delta parsing found no operations for (\S+?)\. ")


def refusal_place(said, files):
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
        items = read_delta("", files[cap]) if cap in files else []
        hits = [(len(n), i.line, n) for i in items if i.kind == kind for n in (i.name, i.new)
                if n is not None and said.startswith(f'{cap} {kind} failed for header '
                                                     f'"### Requirement: {n}" - ')]
        if hits:
            _, line, name = max(hits, key=lambda h: h[0])
            return cap, line, name
        return cap, 0, name
    m = CAP_REFUSAL.match(said) or NO_OPERATIONS.match(said)
    cap = m.group(1) if m and m.group(1) in files else None
    if cap and NO_SPEC in said:
        first = next((i for i in read_delta("", files[cap]) if i.kind in ("RENAMED", "MODIFIED")), None)
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
    (refusal_place), quoting the CLI. copy is never the stack's base, so the
    duplicate and drift checks still read the specs before the change is
    applied."""
    rels = change_deltas(corpus, change)
    files = {cap: corpus.texts[rel] for cap, rel in rels.items()}
    proposal = corpus.texts.get(f"openspec/changes/{change}/proposal.md")
    out = []
    for said in copy.archive_files(change, files, proposal):
        cap, line, name = refusal_place(said, files)
        rel = rels.get(cap) or next(iter(rels.values()))
        what = f'"{name}" in {cap}' if name else (cap or "this change")
        if stacked:
            why = (f"`openspec archive` refuses this change on top of what it builds on: "
                   f"{said.rstrip('.')}; write this change against what it builds on now")
        else:
            why = (f"`openspec archive` would refuse this change on the specs it is checked "
                   f"against: {said.rstrip('.')}")
        out.append(Finding(rel, line, "error", "archive", f"{what}: {why}"))
    return out


def archive_alone(change, corpus):
    """([Finding], status) for a change with no `Builds on:` line: the change
    alone, archived into a scratch copy of the tree's specs (archive_own).
    Without the OpenSpec CLI the status says the archive was not run."""
    if openspec_exe() is None:
        return [], NOT_ARCHIVED
    with tempfile.TemporaryDirectory(prefix="spec-check-archive-") as tmp:
        refusals = archive_own(change, corpus, Scratch(corpus.root, tmp), stacked=False)
    return refusals, "refused" if refusals else "passed"


NOT_ARCHIVED = "not run: the openspec CLI is not on PATH"


def read_dep(repo, dep, corpus):
    """Reads dep from its pull request (load_dep) and marks it pending when
    it has merged but the tree still holds its change open. Raises
    StackError."""
    dep.info = pr_info(repo, dep)
    dep.archive = own_change(repo, dep, dep.info)
    load_dep(repo, dep, dep.info)
    dep.pending = dep.state == "MERGED" and pending_here(dep, corpus)


def stack_onto(change, corpus, repo, deps, findings, stack, complete, blocker, scratch):
    """build_stack's work, archiving into scratch."""
    path = f"openspec/changes/{change}/proposal.md"
    tree = {}  # what `openspec archive` would match a delta against in the tree (spec_reqs)
    for p in corpus.specs:
        tree.setdefault(p.split("/")[2], []).extend(spec_reqs(p, corpus.texts[p]))
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
            check_own(dep, listed, scratch, tree, unread, later)
            cap = unreadable_delta(dep)
            if cap:
                raise StackError(f"its delta for {cap} holds no requirement header spec-check can read")
            if in_tree(dep):
                missing = not_shown(dep, tree, later(dep))
                if missing:
                    raise StackError(f"#{dep.number} has merged, but this branch does not hold its "
                                     f"result ({'; '.join(missing)}). Merge main into your branch")
            else:
                d = decide(dep, scratch.caps())
                refused = scratch.archive(dep.change, d.kept, dep.proposal)
                if refused:
                    why = (f"its deltas do not fit the tree" +
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
        stack.loaded.append(dep)
        for cap, items in items_of(dep).items():
            for i in items:
                if i.kind == "RENAMED" and i.name != i.new:
                    stack.gone[(cap, i.name)] = (dep, f'renames to "{i.new}"')
                elif i.kind == "REMOVED":
                    stack.gone[(cap, i.name)] = (dep, "removes")
        listed.append(dep.change)
        if d is None:
            stop(dep, f"#{dep.number} has merged, and its result is already in the tree checked "
                      f"here: remove the `{dep.declaration}` line", "check")
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
            if any(r.block == text for r in now.get(cap, [])):
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
        if present and not applied and not d.third:
            stop(dep, f"every delta it holds is already in the tree checked here, so main's specs "
                      f"hold its result: remove the `{dep.declaration}` line", "check")
        elif present:
            stop(dep, "some of its deltas are already in the tree and were skipped (" +
                      "; ".join(present) + ")" +
                      ("; the rest were applied (" + "; ".join(applied) + ")" if applied else "") +
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
    for text in dep.history(repo, cap):
        for item in read_delta(dep.delta_path(cap), text):
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
        text = dep.deltas.get(cap)
        if text is None:
            continue
        r = next((i.req for i in read_delta(dep.spec_path(cap), text)
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
        # Read as OpenSpec reads it (read_delta). OpenSpec applies a change's
        # renames before its modifications, so a MODIFIED name may be the new
        # side of the change's own rename.
        mine = read_delta(rel, corpus.texts[rel])
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
                        for t in d.history(repo, cap) for o in read_delta(d.delta_path(cap), t))), None)
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
            m = re.fullmatch(r"openspec/changes/([^/]+)/specs/([^/]+)/spec\.md", f.get("path", ""))
            if m and m.group(1) != "archive" and m.group(2) in wanted:
                reads.append((pr["number"], pr.get("headRefOid", ""), m.group(1), m.group(2), m.group(0)))
    retiring = {}  # (cap, name) -> [(change, number)]
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


def run_checks(root, repo, base_ref, targets, validate, base_required=False, change=None):
    corpus = Corpus(root)
    changes, specs = resolve_targets(corpus, targets)
    base = Base(repo, base_ref, change)
    if not base.ok and base_required:
        raise Fatal(f"the base {base_ref!r} does not resolve to a commit")
    findings, statuses, archives = [], [], []
    stacks, declared = [], {}
    for change in changes:
        reqs = [r for rs in corpus.changes[change].values() for r in rs]
        check_scenarios(reqs, findings)
        stack, problems, complete = build_stack(change, corpus, repo, base)
        findings += problems
        if stack is None:
            check_duplicates(reqs, corpus, findings)
            refusals, archived = archive_alone(change, corpus)
            findings += refusals
        elif not complete:
            archived = NOT_ARCHIVED if openspec_exe() is None else "not run: see the stack error"
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
            archived = "refused" if stack.refusals else "passed"
        archives.append((change, archived))
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
    return changes, specs, findings, statuses, archives, stacks


def print_report(changes, specs, findings, statuses, archives, stacks, base_ref, source, as_json):
    errors = sum(1 for f in findings if f.severity == "error")
    checks = len(findings) - errors
    if as_json:
        print(json.dumps({
            "source": source, "base": base_ref, "changes": changes, "specs": specs,
            "errors": errors, "checks": checks,
            "findings": [f.as_dict() for f in findings],
            "openspec_validate": {k: v for k, v in statuses},
            "openspec_archive": {k: v for k, v in archives},
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
    for what, status in archives:
        print(f"openspec archive ({what}): {status}")
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
    with tempfile.TemporaryDirectory(prefix="spec-check-") as tmp:
        materialize(repo, tree, tmp, allow_empty=True)
        staged = Corpus(tmp)
        targets = [c for c in changes if c in staged.changes]
        targets += ["specs"] if specs and staged.specs else []
        if not targets:
            # Only deletions or archive moves: nothing open is left to check.
            print(f"{KEY}: \u2713 {tree[:12]} no open change or spec staged")
            return 0
        res = run_checks(tmp, repo, base_ref, targets, not args.no_validate,
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
    c.add_argument("--no-validate", action="store_true")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    g = sub.add_parser("sign", help="check the staged openspec change and print the trailer")
    g.add_argument("--read", required=True, choices=["subagent", "self"],
                   help="who did the consistency read")
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

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Fatal as e:
        print(f"spec-check: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
