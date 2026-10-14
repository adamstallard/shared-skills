#!/usr/bin/env python3
"""Link tests to OpenSpec scenarios: each test names the scenario it checks with a tag.

A tag is `@scenario <capability>: <Scenario name>`, anywhere in a test file.
`check` fails on a scenario in openspec/specs that no test tags and the
baseline does not list, on a tag that names no scenario, and on a baseline
line that is now tagged or names no scenario. It checks that a tagged test
exists, not that it passes. Standard library only.

Why it is built this way, and what was tried and rejected: ../DECISIONS.md.
"""

import argparse
import difflib
import os
import re
import subprocess
import sys

DEFAULT_BASELINE = "openspec/spec-trace-baseline.txt"
DEFAULT_TESTS = [
    "**/test/**",
    "**/tests/**",
    "**/__tests__/**",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
    "**/test_*.py",
]
SKIP_DIRS = {".git", "node_modules"}

REQUIREMENT = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SCENARIO = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
TAG = re.compile(r"@scenario\s+([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:")
# A tag ends at the end of its line, or where one of these follows the name:
# a closing quote, a comment closer, punctuation that ends an argument, or the
# `{` that opens a test's body.
# A period ends it too when it ends a sentence, so "Foo." is Foo but "Foo.bar" is not.
TAG_END = re.compile(r"\s*(?:$|[\"'`),;{]|\*/|-->|\.(?:\s|$|[\"'`)]|\*/|-->))")
# A quote escaped inside a quoted test name is part of the name, never its end.
ESCAPED_QUOTES = ("\\'", '\\"')
NOT_AN_END = "\uE000"
# The separator between a requirement and a scenario, for a scenario whose
# name repeats within its capability.
QUALIFIER = " / "


def norm(text):
    return " ".join(text.split())


class Scenario:
    def __init__(self, capability, requirement, name, path, line, change=None):
        self.capability = capability
        self.requirement = requirement
        self.name = name
        self.path = path
        self.line = line
        self.change = change
        self.ident = name  # qualified by assign_idents when the name repeats

    @property
    def key(self):
        return f"{self.capability}: {self.ident}"


def parse_spec(path, rel, capability, change=None):
    """Scenarios in one spec file. A change's delta skips its REMOVED section."""
    scenarios = []
    requirement = ""
    in_fence = False
    removed = False
    with open(path, encoding="utf-8", errors="replace") as f:
        for number, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if re.match(r"^##(\s|$)", line):
                removed = change is not None and line[2:].strip().upper().startswith("REMOVED")
                continue
            if removed:
                continue
            m = REQUIREMENT.match(line)
            if m:
                requirement = norm(m.group(1))
                continue
            m = SCENARIO.match(line)
            if m:
                scenarios.append(Scenario(capability, requirement, norm(m.group(1)), rel, number, change))
    return scenarios


RENAME = re.compile(r"^\s*-\s*(FROM|TO):\s*`?\s*###\s+Requirement:\s*(.+?)\s*`?\s*$")


def parse_delta(path):
    """A change's delta: requirements it removes, renames (old to new), and adds or modifies."""
    removed, renamed, restated = set(), {}, set()
    section = ""
    old = None
    in_fence = False
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if re.match(r"^##(\s|$)", line):
                section = line[2:].strip().upper()
                continue
            m = REQUIREMENT.match(line)
            if m and section.startswith("REMOVED"):
                removed.add(norm(m.group(1)))
            elif m and (section.startswith("ADDED") or section.startswith("MODIFIED")):
                restated.add(norm(m.group(1)))
            m = RENAME.match(line)
            if m and section.startswith("RENAMED"):
                if m.group(1) == "FROM":
                    old = norm(m.group(2))
                elif old is not None:
                    renamed[old] = norm(m.group(2))
                    old = None
    return removed, renamed, restated


def apply_delta(scenarios, changed, removed, renamed, restated, capability):
    """The scenarios as they will be once the change is archived."""
    kept = []
    for s in scenarios:
        if s.capability == capability:
            if s.requirement in removed:
                continue
            s.requirement = renamed.get(s.requirement, s.requirement)
            if s.requirement in restated:
                continue
        kept.append(s)
    return kept + changed


def assign_idents(scenarios):
    """Qualify a name that repeats within a capability with its requirement.

    Returns the problems: scenarios that even the requirement cannot tell apart.
    """
    by_name = {}
    for s in scenarios:
        by_name.setdefault((s.capability, s.name), []).append(s)
    for group in by_name.values():
        if len(group) > 1:
            for s in group:
                s.ident = f"{s.requirement}{QUALIFIER}{s.name}"
    problems = []
    seen = {}
    for s in scenarios:
        if s.key in seen:
            first = seen[s.key]
            problems.append(
                f"{s.path}:{s.line}: scenario '{s.name}' repeats under requirement "
                f"'{s.requirement}' ({first.path}:{first.line}), so no tag can tell them apart. "
                "Rename one of them in the spec.")
        else:
            seen[s.key] = s
    return problems


def load_scenarios(root, include_changes=False):
    specs = os.path.join(root, "openspec", "specs")
    if not os.path.isdir(specs):
        raise SystemExit(f"spec-trace: no openspec/specs under {root}")
    scenarios = []
    for capability in sorted(os.listdir(specs)):
        path = os.path.join(specs, capability, "spec.md")
        if os.path.isfile(path):
            scenarios += parse_spec(path, f"openspec/specs/{capability}/spec.md", capability)
    if include_changes:
        changes = os.path.join(root, "openspec", "changes")
        for change in sorted(os.listdir(changes)) if os.path.isdir(changes) else []:
            if change == "archive":
                continue
            cdir = os.path.join(changes, change, "specs")
            for capability in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
                path = os.path.join(cdir, capability, "spec.md")
                if os.path.isfile(path):
                    rel = f"openspec/changes/{change}/specs/{capability}/spec.md"
                    scenarios = apply_delta(scenarios, parse_spec(path, rel, capability, change),
                                            *parse_delta(path), capability)
    problems = assign_idents(scenarios)
    return scenarios, problems


def glob_to_regex(pattern):
    out = []
    i = 0
    braces = 0
    while i < len(pattern):
        close = pattern.find("]", i + 2) if pattern[i] == "[" else -1
        if close != -1:
            body = pattern[i + 1:close]
            negate = body.startswith("!")
            body = body[1:] if negate else body
            out.append("[" + ("^/" if negate else "") + body.replace("\\", "\\\\") + "]")
            i = close + 1
        elif pattern[i] == "{":
            out.append("(?:")
            braces += 1
            i += 1
        elif pattern[i] == "}" and braces:
            out.append(")")
            braces -= 1
            i += 1
        elif pattern[i] == "," and braces:
            out.append("|")
            i += 1
        elif pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    if braces:
        raise ValueError(f"unclosed {{ in {pattern}")
    return re.compile("^" + "".join(out) + "$")


def list_files(root):
    """Repository files as POSIX paths relative to root, honouring .gitignore where git can."""
    try:
        # With -C root, ls-files lists only root's subtree, as paths relative to
        # root, which is what the globs are matched against.
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return walk_files(root)
    # dict.fromkeys: a file in a merge conflict is listed once per stage.
    files = [name for name in dict.fromkeys(out.decode("utf-8", "replace").split("\0"))
             if name and not any(part in SKIP_DIRS for part in name.split("/"))]
    return [f for f in files if os.path.isfile(os.path.join(root, f))]


def walk_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # A nested repository or worktree is somebody else's tree.
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                             and not os.path.exists(os.path.join(dirpath, d, ".git")))
        for name in sorted(filenames):
            files.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return files


def test_files(root, globs):
    patterns = [glob_to_regex(g) for g in globs]
    return sorted(f for f in list_files(root) if any(p.match(f) for p in patterns))


class Tag:
    def __init__(self, path, line, capability, text, scenario=None, problem=None):
        self.path = path
        self.line = line
        self.capability = capability
        self.text = text
        self.scenario = scenario
        self.problem = problem

    @property
    def where(self):
        return f"{self.path}:{self.line}"


def unescape(text, quote_to):
    """text with each escaped quote replaced by one character.

    longest() makes two copies of a tag's text this way: one with the real quotes, and one
    with a placeholder that never ends a tag. One character per escape keeps both copies the
    same length, so a name's length indexes the same place in each.
    """
    for escaped in ESCAPED_QUOTES:
        text = text.replace(escaped, quote_to or escaped[1])
    return text


def shown(rest):
    """The tag's text as written, for a message, when it names no scenario."""
    # Each escaped quote becomes its own placeholder, so neither is taken for a closing quote.
    held = {"\\'": "\uE001", '\\"': "\uE002"}
    for escaped, mark in held.items():
        rest = rest.replace(escaped, mark)
    for stop in ('"', "`", "*/", "-->"):
        if stop in rest:
            rest = rest[:rest.index(stop)]
    closing = re.search(r"'\s*[,)]", rest)
    if closing:
        rest = rest[:closing.start()]
    rest = rest.replace("\uE001", "'").replace("\uE002", '"')
    return norm(rest).rstrip("'),;{. ")


def longest(rest, names):
    """The longest of names that the tag's text starts with, followed by a tag end."""
    rest = norm(rest)
    text = unescape(rest, None)  # what the name says
    ends = unescape(rest, NOT_AN_END)  # where it may end: an escaped quote never ends it
    best = None
    for name in names:
        if text.startswith(name) and TAG_END.match(ends, len(name)):
            if best is None or len(name) > len(best):
                best = name
    return best


def resolve(capability, rest, index):
    """The scenario a tag names: the longest identity its text starts with, then a tag end."""
    idents = index.get(capability, {})
    ident = longest(rest, idents)
    return (ident, idents[ident]) if ident is not None else None


def name_index(scenarios):
    index = {}
    for s in scenarios:
        caps = index.setdefault(s.capability, {})
        caps[s.ident] = s
        # A qualified name may always be written; a bare one only when it is unique.
        caps.setdefault(f"{s.requirement}{QUALIFIER}{s.name}", s)
    return index


def pending_scenarios(root):
    """Scenarios that open changes add or restate: a tag may name one before the archive."""
    return [s for s in load_scenarios(root, include_changes=True)[0] if s.change]


def scan_tags(root, files, scenarios, pending=()):
    index = name_index(scenarios)
    waiting = name_index(pending)
    repeated = {(s.capability, s.name) for s in scenarios if s.ident != s.name}
    tags = []
    for rel in files:
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            starts = list(TAG.finditer(line))
            for i, m in enumerate(starts):
                end = starts[i + 1].start() if i + 1 < len(starts) else len(line)
                capability, rest = m.group(1), line[m.end():end]
                found = resolve(capability, rest, index)
                bare = longest(rest, [name for cap, name in repeated if cap == capability])
                # The longer match wins, so a tag for a repeated name is never counted
                # for a shorter, unique name its text also starts with.
                if bare is not None and (found is None or len(bare) > len(found[0])):
                    tags.append(Tag(rel, number, capability, bare, problem="ambiguous"))
                    continue
                if found:
                    tags.append(Tag(rel, number, capability, found[0], scenario=found[1]))
                    continue
                if resolve(capability, rest, waiting):
                    continue  # names a scenario an open change adds: neither covered nor an error
                text = shown(rest)
                if capability not in index:
                    tags.append(Tag(rel, number, capability, text, problem="capability"))
                else:
                    tags.append(Tag(rel, number, capability, text, problem="orphan"))
    return tags


def read_baseline(path):
    entries = {}
    if not os.path.isfile(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for number, raw in enumerate(f, 1):
            line = norm(raw)
            if line and not line.startswith("#"):
                cap, sep, name = line.partition(":")
                if sep:
                    line = f"{cap.strip()}: {name.strip()}"
                entries.setdefault(line, number)
    return entries


def coverage(scenarios, tags):
    covered = {}
    for t in tags:
        if t.scenario is not None:
            covered.setdefault(t.scenario.key, []).append(t)
    return covered


def tag_problem(t, scenarios):
    if t.problem == "ambiguous":
        options = [s for s in scenarios if s.capability == t.capability and s.name == t.text]
        lines = "\n".join(f"      @scenario {s.key}" for s in options)
        return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' is ambiguous: that scenario name "
                f"appears under more than one requirement. Name the requirement too, as one of:\n{lines}")
    if t.problem == "capability":
        caps = sorted({s.capability for s in scenarios})
        hint = difflib.get_close_matches(t.capability, caps, n=1)
        more = f" Did you mean '{hint[0]}'?" if hint else f" Capabilities: {', '.join(caps)}."
        return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' names no capability under "
                f"openspec/specs.{more}")
    names = [s.ident for s in scenarios if s.capability == t.capability]
    hint = difflib.get_close_matches(t.text, names, n=1, cutoff=0.5)
    more = f" Did you mean '{hint[0]}'?" if hint else ""
    return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' names no scenario in "
            f"openspec/specs/{t.capability}/spec.md.{more} If the scenario was renamed, change the "
            "tag to its new name; if it was removed, delete the tag.")


def check(root, files, baseline_path):
    scenarios, problems = load_scenarios(root)
    tags = scan_tags(root, files, scenarios, pending_scenarios(root))
    covered = coverage(scenarios, tags)
    baseline = read_baseline(baseline_path)
    rel_baseline = os.path.relpath(baseline_path, root)
    keys = {s.key for s in scenarios}

    for s in scenarios:
        if s.key not in covered and s.key not in baseline:
            problems.append(
                f"{s.path}:{s.line}: no test tags scenario '{s.key}'. Add this line to the test that "
                f"checks it, or write that test:\n      @scenario {s.key}")
    problems += [tag_problem(t, scenarios) for t in tags if t.problem]
    for entry, number in sorted(baseline.items(), key=lambda e: e[1]):
        if entry in covered:
            where = ", ".join(t.where for t in covered[entry])
            problems.append(f"{rel_baseline}:{number}: '{entry}' is now tagged by {where}. "
                            "Remove this line from the baseline.")
        elif entry not in keys:
            problems.append(f"{rel_baseline}:{number}: '{entry}' names no scenario in openspec/specs. "
                            "Remove this line from the baseline.")

    if problems:
        for p in problems:
            print(p)
        print(f"\nspec-trace: {len(problems)} problem(s). {len(covered)} of {len(scenarios)} scenarios "
              f"are tagged; {len(baseline)} are in the baseline.")
        return 1
    print(f"spec-trace: ok. {len(covered)} of {len(scenarios)} scenarios are tagged; "
          f"{len(baseline)} untagged ones are in the baseline.")
    return 0


def write_baseline(root, files, baseline_path):
    scenarios, problems = load_scenarios(root)
    if problems:
        for p in problems:
            print(p)
        return 1
    tags = scan_tags(root, files, scenarios, pending_scenarios(root))
    covered = coverage(scenarios, tags)
    untagged = sorted(s.key for s in scenarios if s.key not in covered)
    os.makedirs(os.path.dirname(baseline_path) or ".", exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as f:
        f.write("# Scenarios in openspec/specs that no test tags yet. spec-trace check fails when a\n"
                "# line here is tagged or names no scenario, so this list only shrinks.\n")
        for key in untagged:
            f.write(key + "\n")
    print(f"spec-trace: wrote {len(untagged)} untagged scenario(s) of {len(scenarios)} to "
          f"{os.path.relpath(baseline_path, root)}.")
    return 0


def cell(text):
    return text.replace("|", "\\|")


def report(root, files, include_changes):
    scenarios, problems = load_scenarios(root, include_changes)
    tags = scan_tags(root, files, scenarios, () if include_changes else pending_scenarios(root))
    covered = coverage(scenarios, tags)
    print(f"{len(covered)} of {len(scenarios)} scenarios are tagged by a test.")
    for capability in sorted({s.capability for s in scenarios}):
        group = [s for s in scenarios if s.capability == capability]
        count = sum(1 for s in group if s.key in covered)
        print(f"\n### {capability} ({count} of {len(group)} tagged)\n")
        print("| Scenario | Tests |")
        print("| --- | --- |")
        for s in group:
            name = s.ident + (f" (change: {s.change})" if s.change else "")
            where = "<br>".join(t.where for t in covered.get(s.key, [])) or "none"
            print(f"| {cell(name)} | {cell(where)} |")
    bad = [tag_problem(t, scenarios) for t in tags if t.problem] + problems
    if bad:
        print("\n### Problems\n")
        for p in bad:
            print("- " + p.replace("\n", " ").replace("      ", " "))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spec_trace.py", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current directory)")
    parser.add_argument("--tests", action="append", metavar="GLOB",
                        help="test file glob, relative to the root; repeat for several. "
                             "Replaces the defaults: " + " ".join(DEFAULT_TESTS))
    parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                        help=f"baseline file, relative to the root (default: {DEFAULT_BASELINE})")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="fail on an untagged scenario, a stale tag or a stale baseline line")
    sub.add_parser("baseline", help="write every untagged scenario to the baseline file")
    rep = sub.add_parser("report", help="print a markdown table of scenarios and the tests that tag them")
    rep.add_argument("--include-changes", action="store_true",
                     help="also list scenarios from open changes in openspec/changes/*/specs")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    globs = args.tests or DEFAULT_TESTS
    baseline = os.path.join(root, args.baseline)
    try:
        files = test_files(root, globs)
        # A glob that matches nothing finds none of the tags it was meant to, so
        # `baseline` would exempt those scenarios.
        unmatched = [g for g in args.tests or [] if not test_files(root, [g])]
    except (ValueError, re.error) as e:
        print(f"spec-trace: bad --tests glob: {e}")
        return 2
    if unmatched:
        print(f"spec-trace: no test files match {' '.join(unmatched)} under {root}.")
        return 2
    if not files:
        print("spec-trace: warning: no test files match the default patterns; pass --tests GLOB "
              "if this repository keeps its tests elsewhere.", file=sys.stderr)
    if args.command == "check":
        return check(root, files, baseline)
    if args.command == "baseline":
        return write_baseline(root, files, baseline)
    return report(root, files, args.include_changes)


if __name__ == "__main__":
    sys.exit(main())
