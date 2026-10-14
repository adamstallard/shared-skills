#!/usr/bin/env python3
"""spec-check: the mechanical half of reviewing an OpenSpec change.

    spec_check.py check [<target>...] [--repo DIR] [--ref REF] [--base REF]
                        [--decisions-heading TEXT]... [--no-validate] [--json]
    spec_check.py setup [--repo DIR] [--dry-run]
    spec_check.py sign --read subagent|self [--amended N] [--open N]
                       [--base REF] [--decisions-heading TEXT]... [--no-validate]
    spec_check.py verify-staged "Spec-check: <value>"   (message on stdin)
    spec_check.py verify-commit <sha> <value>

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
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

DECISIONS_HEADINGS = ["Decisions"]

RULE_TEXT = (
    "Open with the decisions the reviewer is asked to make, each with the "
    "alternative it rejects; then what is still open; then everything else."
)
RULE_MARKER = "# spec-check: decisions first"

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
# A bare name (no slash) missing from the base is an error only when its
# extension is one of these. Any other bare name might be an address, such as
# redis.cache:6379, so a missing one is a check for a person to judge. Names
# ending in a digit or a host suffix (0.0.0.0:8080, example.com:443) are
# skipped.
FILE_EXTS = set("""py pyi ts tsx js jsx mjs cjs go rs java kt kts rb php c h cc cpp hpp cs
swift m mm sh bash zsh fish md mdx rst txt yaml yml json jsonc toml ini cfg conf sql
html css scss less vue svelte tla cfg proto graphql gql tf hcl ex exs erl hs ml scala
lua pl r dart gradle xml csv lock env""".split())
HOST_SUFFIXES = set("""com org net io dev ai app co uk us de eu fr jp cn ru in au ca local
localhost internal lan home arpa edu gov mil int info biz me tv cloud xyz site online
tech""".split())

BACKTICK = re.compile(r"`([^`\n]+)`")
BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,}$")
BOLD_WORDS = re.compile(r"^[A-Za-z][A-Za-z' -]{1,48}[A-Za-z]$")
NOT_TERMS = {"when", "then", "and", "given", "or", "but", "not", "note",
             "breaking", "rejected", "still open", "shall", "must", "shall not",
             "must not", "should", "may", "none", "all", "only", "every"}

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
    out = git(repo, "archive", "--format=tar", treeish, "--", "openspec",
              check=False, binary=True)
    if out.returncode != 0:
        raise Fatal(f"cannot read openspec/ from {treeish}: "
                    f"{out.stderr.decode('utf-8', 'replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python before 3.12 has no filter argument
            tar.extractall(dest)


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
    reqs, section, req, scen, fenced = [], None, None, None, False
    for n, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
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
    for raw in text.splitlines():
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


def check_terms(targets, corpus, change, out):
    """Backticked or bold terms in a change's requirements that nothing defines."""
    elsewhere = [corpus.texts[path] for path in corpus.specs]
    for f in ("proposal.md", "design.md"):
        p = f"openspec/changes/{change}/{f}"
        if p in corpus.texts:
            elsewhere.append(corpus.texts[p])
    headings = [r.name for r in corpus.all_reqs()]
    headings += [s.name for r in corpus.all_reqs() for s in r.scenarios]
    names = set(corpus.changes) | {p.split("/")[2] for p in corpus.specs}
    haystack = "\n".join(elsewhere + headings).lower()
    seen = set()
    for r in targets:
        if r.section in ("REMOVED", "RENAMED"):
            continue
        for n, t in r.text:
            candidates = [m for m in BACKTICK.findall(t) if IDENT.match(m)]
            # A bold label followed by a colon defines what follows it.
            candidates += [m.group(1).strip() for m in BOLD.finditer(t)
                           if not m.group(1).strip().endswith(":")
                           and not t[m.end():].startswith(":")
                           and BOLD_WORDS.match(m.group(1).strip())]
            for term in candidates:
                low = term.lower()
                if low in NOT_TERMS or low in names or low in seen:
                    continue
                if re.search(r"(?<![\w-])" + re.escape(low) + r"(?![\w-])", haystack):
                    continue
                seen.add(low)
                out.append(Finding(r.path, n, "check", "undefined-term",
                                   f'"{term}" is used here and appears nowhere in openspec/specs '
                                   "or this change's proposal or design; "
                                   "define it before it is used, or say what it refers to"))


class Base:
    """Files on the change's base branch, read through git."""

    def __init__(self, repo, ref):
        self.repo, self.ref = repo, ref
        self._names = None
        self._lines = {}
        self.ok = git(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}",
                      check=False).returncode == 0

    def names(self):
        if self._names is None:
            out = git(self.repo, "ls-tree", "-r", "--name-only", self.ref)
            self._names = out.stdout.splitlines()
        return self._names

    def line_count(self, path):
        if path not in self._lines:
            out = git(self.repo, "show", f"{self.ref}:{path}", check=False, binary=True)
            if out.returncode != 0:
                self._lines[path] = None
            else:
                data = out.stdout
                self._lines[path] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        return self._lines[path]


def check_citations(paths, corpus, base, out):
    for path in paths:
        for n, raw in enumerate(corpus.texts[path].splitlines(), 1):
            for m in CITATION.finditer(raw):
                cited, first, last = m.group(1), int(m.group(2)), m.group(3)
                cited = cited[2:] if cited.startswith("./") else cited
                ext = cited.rsplit(".", 1)[-1].lower()
                if not ext[:1].isalpha():
                    continue
                bare = "/" not in cited
                if bare and ext in HOST_SUFFIXES:
                    continue
                severity = "error" if not bare or ext in FILE_EXTS else "check"
                line = int(last) if last else first
                if not base.ok:
                    # No base to read, as in a repository with no commits yet.
                    out.append(Finding(path, n, "check", "citation",
                                       f"{m.group(0)}: not checked; {base.ref} does not resolve"))
                    continue
                resolved = cited
                if base.line_count(cited) is None and "/" not in cited:
                    matches = [p for p in base.names() if p.rsplit("/", 1)[-1] == cited]
                    if len(matches) == 1:
                        resolved = matches[0]
                    elif len(matches) > 1:
                        out.append(Finding(path, n, "check", "citation",
                                           f"{m.group(0)}: {len(matches)} files on {base.ref} are named "
                                           f"{cited}; cite it by its path"))
                        continue
                count = base.line_count(resolved)
                if count is None:
                    out.append(Finding(path, n, severity, "citation",
                                       f"{m.group(0)}: {cited} does not exist on {base.ref}"))
                elif line > count or first < 1:
                    out.append(Finding(path, n, "error", "citation",
                                       f"{m.group(0)}: {resolved} has {count} lines on {base.ref}"))


def decisions_heading_ok(title, headings):
    t = title.strip().strip("*").strip().lower()
    return any(t.startswith(h.lower()) for h in headings)


def check_decisions(change, corpus, headings, out):
    path = f"openspec/changes/{change}/proposal.md"
    if path not in corpus.texts:
        out.append(Finding(path, 0, "error", "decisions-first", "the change has no proposal.md"))
        return
    fenced = False
    for n, raw in enumerate(corpus.texts[path].splitlines(), 1):
        if raw.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        m = None if fenced else HEADING.match(raw)
        if not m or len(m.group(1)) < 2:
            continue
        if not decisions_heading_ok(m.group(2), headings):
            names = " or ".join(f'"{h}"' for h in headings)
            out.append(Finding(path, n, "error", "decisions-first",
                               f'the proposal opens with "{m.group(2)}"; it must open with a '
                               f"section headed {names}: the decisions the reviewer is asked to make, "
                               "each with the alternative it rejects, then what is still open"))
        else:
            check_alternatives(path, corpus.texts[path].splitlines(), n, len(m.group(1)), out)
        return
    out.append(Finding(path, 0, "error", "decisions-first", "the proposal has no sections"))


DECISION_ITEM = re.compile(r"^(\d+[.)]|[-*])\s+")
# What starts the "still open" part: "Still open", "Open questions", "Open
# items", "Open issues" or "Open", as a whole label. It is bold, ends in a
# colon, or is all the line says, so "Open issues close after ninety days" is a
# decision, not the label.
OPEN_LABEL = re.compile(
    r"^(\*\*|__)?\s*(still\s+open|open\s+(?:questions?|items?|issues?)|open)\b\s*(:)?\s*(\*\*|__)?(:)?",
    re.I)


def is_open_label(text):
    m = OPEN_LABEL.match(text.strip())
    if not m:
        return False
    whole_bold = bool(m.group(1) and m.group(4))
    colon = bool(m.group(3) or m.group(5))
    return whole_bold or colon or not text.strip()[m.end():].strip()


def check_alternatives(path, lines, start, level, out):
    """Each decision in the section names the alternative it rejects.

    A decision is a list item at the left margin, up to the section's end or a
    line that starts what is still open. It names an alternative when its text
    says "reject" in any form, as `*Rejected:* ...` does.
    """
    items = []  # [line number, text]
    for n in range(start + 1, len(lines) + 1):
        raw = lines[n - 1]
        h = HEADING.match(raw)
        if h and (len(h.group(1)) <= level or is_open_label(h.group(2))):
            break
        item = DECISION_ITEM.match(raw)
        if item and is_open_label(raw[item.end():]):
            break
        if item:
            items.append([n, raw])
        # Only an unindented line can be the label. An indented line continues
        # the decision above it, whatever it says.
        elif not raw[:1].isspace() and is_open_label(raw):
            break
        elif items:
            items[-1][1] += "\n" + raw
    if not items:
        out.append(Finding(path, start, "error", "decisions-first",
                           "the decisions section lists no decisions; list each as an item "
                           "that names the alternative it rejects"))
    for n, text in items:
        if not re.search(r"\breject", text, re.I):
            out.append(Finding(path, n, "error", "decision-alternative",
                               "this decision names no alternative it rejects; add "
                               "\"*Rejected:* <the alternative>, <why>\""))


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


def run_checks(root, repo, base_ref, targets, headings, validate, base_required=False):
    corpus = Corpus(root)
    changes, specs = resolve_targets(corpus, targets)
    base = Base(repo, base_ref)
    if not base.ok and base_required:
        raise Fatal(f"the base {base_ref!r} does not resolve to a commit")
    findings, statuses = [], []
    for change in changes:
        reqs = [r for rs in corpus.changes[change].values() for r in rs]
        check_decisions(change, corpus, headings, findings)
        check_scenarios(reqs, findings)
        check_duplicates(reqs, corpus, findings)
        check_terms(reqs, corpus, change, findings)
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
    return changes, specs, findings, statuses


def print_report(changes, specs, findings, statuses, base_ref, source, as_json):
    errors = sum(1 for f in findings if f.severity == "error")
    checks = len(findings) - errors
    if as_json:
        print(json.dumps({
            "source": source, "base": base_ref, "changes": changes, "specs": specs,
            "errors": errors, "checks": checks,
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
                             bool(args.base))
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

def add_rule(text, nl="\n"):
    """The config with the decisions-first rule under rules: proposal:.

    Returns (new text, what happened). Edits text, never re-serialises it, so
    comments and layout survive. Refuses flow style rather than guess at it.
    """
    if RULE_MARKER in text or RULE_TEXT in text:
        return text, "present"
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += nl
    top = re.compile(r"^rules:[ \t]*(#.*)?$")
    rules_at = next((i for i, l in enumerate(lines) if top.match(l.rstrip("\r\n"))), None)
    item = f'{RULE_MARKER}{nl}- "{RULE_TEXT}"{nl}'

    def indented(block, pad):
        return "".join(pad + l if l.strip() else l for l in block.splitlines(keepends=True))

    if rules_at is None:
        if any(re.match(r"^rules:", l) for l in lines):
            raise Fatal("openspec/config.yaml has `rules:` with an inline value; "
                        "add the rule under rules: proposal: by hand")
        sep = "" if not lines or lines[-1].strip() == "" else nl
        return "".join(lines) + sep + f"rules:{nl}  proposal:{nl}" + indented(item, "    "), "added"

    # The rules block: every following line that is blank, a comment, or indented.
    end = rules_at + 1
    while end < len(lines):
        l = lines[end]
        if l.strip() == "" or l.startswith((" ", "\t")) or l.lstrip().startswith("#"):
            end += 1
            continue
        break
    while end > rules_at + 1 and (lines[end - 1].strip() == "" or
                                 not lines[end - 1].startswith((" ", "\t"))):
        end -= 1  # trailing blanks and column-0 comments belong after the block
    children = [i for i in range(rules_at + 1, end)
                if re.match(r"^[ \t]+[A-Za-z_][\w-]*:", lines[i])
                and not lines[i].lstrip().startswith("#")]
    child_pad = re.match(r"^[ \t]*", lines[children[0]]).group(0) if children else "  "
    children = [i for i in children
                if re.match(r"^[ \t]*", lines[i]).group(0) == child_pad]
    prop = next((i for i in children if re.match(r"^[ \t]+proposal:", lines[i])), None)
    if prop is None:
        new = child_pad + "proposal:" + nl + indented(item, child_pad * 2)
        lines.insert(rules_at + 1, new)
        return "".join(lines), "added"
    if not re.match(r"^[ \t]+proposal:[ \t]*(#[^\r\n]*)?\r?\n$", lines[prop]):
        raise Fatal("openspec/config.yaml has `proposal:` with an inline value; "
                    "add the rule to it by hand")
    # The proposal list: the lines after `proposal:` that are indented deeper
    # than it, or that start with `-` at the same indent as `proposal:`.
    last, item_pad = prop, None
    i = prop + 1
    while i < end:
        l = lines[i]
        pad = re.match(r"^[ \t]*", l).group(0)
        if l.strip() == "" or l.lstrip().startswith("#"):
            i += 1
            continue
        if len(pad) > len(child_pad) or (pad == child_pad and l.lstrip().startswith("- ")):
            if l.lstrip().startswith("- ") and item_pad is None:
                item_pad = pad
            last = i
            i += 1
            continue
        break
    lines.insert(last + 1, indented(item, item_pad if item_pad is not None else child_pad * 2))
    return "".join(lines), "added"


def cmd_setup(args):
    repo = repo_root(args.repo)
    path = os.path.join(repo, "openspec", "config.yaml")
    if not os.path.isfile(path):
        raise Fatal(f"no {path}; run `openspec init` first")
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    # The lines added take the ending most lines have; existing lines keep theirs.
    nl = "\r\n" if text.count("\r\n") * 2 > text.count("\n") else "\n"
    new, what = add_rule(text, nl)
    if what == "present":
        print("spec-check setup: the decisions-first rule is already in openspec/config.yaml")
        return 0
    if args.dry_run:
        sys.stdout.write(new)
        return 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("spec-check setup: added the decisions-first rule to openspec/config.yaml "
          "under rules: proposal:. `openspec instructions proposal` shows it to the agent "
          "that drafts a proposal, inside <rules>.")
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
                         bool(args.base))
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

    s = sub.add_parser("setup", help="add the decisions-first rule to openspec/config.yaml")
    s.add_argument("--repo")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_setup)

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
