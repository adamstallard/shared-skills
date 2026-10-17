#!/usr/bin/env python3
"""Link tests to OpenSpec scenarios: each test names the scenario it checks with a tag.

A tag is `@scenario <capability>: <Scenario name>`, in a test file. Tags are
found with one `git grep` over every file under the root whose path
.gitignore doesn't match, tracked or not, except DEFAULT_EXCLUDES and the
patterns in IGNORE_FILE.
`check` fails on a scenario in openspec/specs that no test tags and the
baseline does not list, on a tag that names no scenario, and on a baseline
line that is now tagged or names no scenario. It checks that a tag exists,
not that its test runs or passes. Standard library only; needs git.

Why it is built this way, and what was tried and rejected: ../DECISIONS.md.
"""

import argparse
import difflib
import os
import re
import shlex
import subprocess
import sys

DEFAULT_BASELINE = "openspec/spec-trace-baseline.txt"
# Places where a tag never belongs to a test: documentation, and OpenSpec's own files. Git
# glob pathspecs, relative to the root, passed to git grep as excludes.
DEFAULT_EXCLUDES = ("**/*.md", "**/*.mdx", "**/*.rst", "**/*.adoc", "**/*.txt", "openspec/**")
# More paths to leave out, one git glob pattern per line, relative to the
# root; # comments and blank lines are skipped. Optional.
IGNORE_FILE = "openspec/spec-trace-ignore.txt"
# The longest IGNORE_FILE read, in characters. ignore_patterns reads one more, and
# stops the command if it gets it.
IGNORE_FILE_LIMIT = 65536

# What a repository has decided about spec-trace (adoption_state).
# UNKNOWN: the decision file holds something other than DECLINED_TEXT, or
# cannot be read (unknown_reason says which; adoption_state lists every case).
ADOPTED, DECLINED, UNDECIDED, UNKNOWN = "adopted", "declined", "undecided", "unknown"
# spec-trace's own decision file, which `decline` writes. OpenSpec's config.yaml
# is left alone, so declining works whether or not that file exists.
DECISION_FILE = "openspec/spec-trace.yaml"
DECLINED_TEXT = "adoption: declined"
# Characters adoption_state reads from DECISION_FILE at most; a longer file
# is UNKNOWN.
DECISION_FILE_LIMIT = 4096
WORKFLOWS = ".github/workflows"

REQUIREMENT = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SCENARIO = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
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


def fence_after(line, fence):
    """The open fence after this line, and whether this line opens or closes one.

    A fence closes only on a line of its own character, at least as long, and nothing else,
    so a ``` line inside a ~~~ example is part of the example: neither opens nor closes.
    """
    m = FENCE.match(line)
    if not m:
        return fence, False
    mark = m.group(1)
    if fence is None:
        return mark, True
    if mark[0] == fence[0] and len(mark) >= len(fence) and not m.group(2).strip():
        return None, True
    return fence, False


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
    fence = None
    removed = False
    with open(path, encoding="utf-8", errors="replace") as f:
        for number, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            fence, fence_line = fence_after(line, fence)
            if fence_line or fence:
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
    fence = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            fence, fence_line = fence_after(line, fence)
            if fence_line or fence:
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


def apply_delta(scenarios, changed, removed, renamed, restated, capability, change):
    """The scenarios as they will be once the change is archived."""
    kept = []
    for s in scenarios:
        if s.capability == capability:
            if s.requirement in removed:
                continue
            if s.requirement in renamed:
                # Under its new name the scenario exists only in the change, until the archive.
                s.requirement, s.change = renamed[s.requirement], change
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
                                            *parse_delta(path), capability, change)
    problems = assign_idents(scenarios)
    return scenarios, problems


class Refusal(Exception):
    """A command that reads tags cannot search the repository; args[0] says why."""


def git_env(root):
    """The environment for the git commands that search root, or None to inherit this one.

    Git exports GIT_DIR, without GIT_WORK_TREE, to hooks in a linked worktree and
    to `git rebase -x`. git -C root then takes root for the top of the work tree,
    so a .gitignore above root is not read. When git finds that same repository
    from root on its own, GIT_DIR is dropped; otherwise it is kept, because a
    separate git directory or a dotfiles setup depends on it.
    """
    git_dir = os.environ.get("GIT_DIR")
    if not git_dir or "GIT_WORK_TREE" in os.environ:
        return None
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
    try:
        found = subprocess.run(["git", "-C", root, "rev-parse", "--absolute-git-dir"],
                               capture_output=True, encoding="utf-8", errors="replace", env=env)
    except OSError:
        return None
    # git reads a relative GIT_DIR after -C, so it is relative to root.
    same = (found.returncode == 0 and os.path.realpath(found.stdout.rstrip("\n"))
            == os.path.realpath(os.path.join(root, git_dir)))
    return env if same else None


def require_work_tree(root, env=None):
    """Raise Refusal unless git runs and root is inside a git work tree."""
    try:
        result = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, encoding="utf-8", errors="replace", env=env)
    except OSError as e:
        raise Refusal(f"git could not be run ({e}). check, report and baseline find tags with "
                      "git grep, so they need git; state and decline do not.")
    if result.returncode != 0 or result.stdout.strip() != "true":
        said = result.stderr.strip() or result.stdout.strip()
        raise Refusal(f"{root} is not inside a git work tree" + (f" (git: {said})" if said else "")
                      + ". check, report and baseline find tags with git grep, so they need one; "
                      "state and decline do not.")


def ignore_patterns(root):
    """The patterns in IGNORE_FILE, or [] when there is none. Refusal when it cannot be read."""
    path = os.path.join(root, IGNORE_FILE)
    if not os.path.lexists(path):
        return []
    # utf-8-sig: a file saved on Windows may start with a byte order mark,
    # which would otherwise stay on the first pattern.
    text = read_regular_file(path, IGNORE_FILE_LIMIT, encoding="utf-8-sig")
    if text is None:
        raise Refusal(f"{IGNORE_FILE} cannot be read: it is not a regular file, or reading it failed.")
    if len(text) > IGNORE_FILE_LIMIT:
        raise Refusal(f"{IGNORE_FILE} is longer than {IGNORE_FILE_LIMIT} characters.")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def grep_command(root, patterns):
    """The git grep that finds every line holding a tag under root.

    --untracked adds files git would track: not yet added, and not ignored.
    -I skips binary files. The --no- options undo settings in the user's git
    config that would change the output's shape: paths relative to the top
    (grep.fullName), a column number (grep.column) or colour codes.
    --no-recurse-submodules undoes submodule.recurse, which git refuses
    alongside --untracked. --no-literal-pathspecs undoes GIT_LITERAL_PATHSPECS,
    which would read the excludes as plain paths, so none would apply. -F reads
    the pattern as text, whatever grep.patternType says.
    """
    excludes = [f":(exclude,glob){p}" for p in (*DEFAULT_EXCLUDES, *patterns)]
    return ["git", "--no-literal-pathspecs", "-C", root, "grep", "--untracked",
            "--no-recurse-submodules", "-I", "-n", "-z", "--no-color", "--no-column",
            "--no-full-name", "-F", "-e", "@scenario", "--", ".", *excludes]


def tag_lines(root):
    """Each line under root holding `@scenario`, as (path relative to root, line number, text),
    sorted. Refusal when git cannot search root."""
    env = git_env(root)
    require_work_tree(root, env)
    patterns = ignore_patterns(root)
    try:
        result = subprocess.run(grep_command(root, patterns), capture_output=True, env=env)
    except (OSError, ValueError) as e:  # ValueError: a NUL in a pattern
        raise Refusal(f"git grep could not be run ({e}).")
    if result.returncode == 1:
        return []  # no line matched
    if result.returncode != 0:
        said = result.stderr.decode("utf-8", "replace").strip()
        hint = f" Check the patterns in {IGNORE_FILE}." if patterns else ""
        raise Refusal(f"git grep failed: {said or f'exit {result.returncode}'}.{hint}")
    # With -z each match is `path NUL number NUL text LF`. A path may hold a
    # newline, so it ends only at its NUL; the text ends at the newline.
    out, found, i = result.stdout, [], 0
    while i < len(out):
        path_end = out.index(b"\0", i)
        number_end = out.index(b"\0", path_end + 1)
        text_end = out.find(b"\n", number_end + 1)
        text_end = len(out) if text_end == -1 else text_end
        found.append((out[i:path_end].decode("utf-8", "replace"), int(out[path_end + 1:number_end]),
                      out[number_end + 1:text_end].decode("utf-8", "replace").rstrip("\r")))
        i = text_end + 1
    return sorted(found)


class Tag:
    def __init__(self, path, line, capability, text, scenario=None, problem=None, choices=()):
        self.choices = choices  # for an ambiguous tag, the qualified tags it may mean
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
    for stop in ("*/", "-->"):
        if stop in rest:
            rest = rest[:rest.index(stop)]
    # For " and for a backtick: when the rest of the line holds an odd number of that quote,
    # the tag sits inside a quoted test name, and the first one closes the name. Quotes in
    # pairs are a comment's own text.
    for quote in ('"', "`"):
        if rest.count(quote) % 2:
            rest = rest[:rest.index(quote)]
    # An apostrophe is common in a comment, so a single quote closes a name only when a `,`,
    # a `)` or the line's end follows it.
    closing = re.search(r"'\s*(?:[,)]|$)", rest)
    if closing:
        rest = rest[:closing.start()]
    rest = norm(rest.replace("\uE001", "'").replace("\uE002", '"')).rstrip("',;{. ")
    while rest.endswith(")") and rest.count(")") > rest.count("("):
        rest = rest[:-1].rstrip("',;{. ")
    return rest


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


def repeats(scenarios):
    """Each scenario name that repeats within its capability, with its scenarios."""
    out = {}
    for s in scenarios:
        if s.ident != s.name:
            out.setdefault((s.capability, s.name), []).append(s)
    return out


def scan_tags(lines, scenarios, pending=()):
    """The tags in lines, which are (path, line number, text) as tag_lines gives them.

    Each tag either names a scenario or carries a problem: it names no
    capability, no scenario, or a name that is ambiguous. pending holds the
    scenarios open changes add; a tag naming one of them is left out.
    """
    index, waiting = name_index(scenarios), name_index(pending)
    repeated, repeated_waiting = repeats(scenarios), repeats(pending)
    tags = []
    for rel, number, line in lines:
        starts = list(TAG.finditer(line))
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(line)
            capability, rest = m.group(1), line[m.end():end]
            # Every reading of the tag, ranked for ties:
            #   3, a main scenario: the tag counts for it;
            #   2, a name repeated in the main specs: ambiguous;
            #   1, a scenario an open change adds: accepted, neither counted nor an error;
            #   0, a name repeated in an open change: ambiguous.
            # The longest match wins, so a tag is never counted for a shorter name its text
            # also starts with; on a tie the higher rank wins, so the main specs come first.
            readings = []
            found = resolve(capability, rest, index)
            if found:
                readings.append((len(found[0]), 3, found))
            for rank, table in ((2, repeated), (0, repeated_waiting)):
                bare = longest(rest, [name for cap, name in table if cap == capability])
                if bare is not None:
                    readings.append((len(bare), rank, (bare, table[(capability, bare)])))
            waits = resolve(capability, rest, waiting)
            if waits:
                readings.append((len(waits[0]), 1, waits))
            if readings:
                _, rank, (text, what) = max(readings, key=lambda r: r[:2])
                if rank == 3:
                    tags.append(Tag(rel, number, capability, text, scenario=what))
                elif rank != 1:  # a scenario an open change adds is neither covered nor an error
                    tags.append(Tag(rel, number, capability, text, problem="ambiguous",
                                    choices=[s.key for s in what]))
                continue
            text = shown(rest)
            if capability not in index:
                tags.append(Tag(rel, number, capability, text, problem="capability"))
            else:
                tags.append(Tag(rel, number, capability, text, problem="orphan"))
    return tags


def baseline_entry(raw):
    """The scenario a baseline line names, as `capability: name`, or None for a blank or # line.

    `check` and `baseline --prune` both read lines through this, so they agree on what each means.
    """
    line = norm(raw)
    if not line or line.startswith("#"):
        return None
    cap, sep, name = line.partition(":")
    return f"{cap.strip()}: {name.strip()}" if sep else line


def baseline_lines(path):
    """The baseline's lines, each with its line ending as written; `check` and `baseline --prune`
    both read the file through this.

    utf-8-sig: a file saved by an editor on Windows may start with a byte order mark, which
    would otherwise stay on the first line and make it name no scenario.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return f.readlines()


def read_baseline(path):
    entries = {}
    if not os.path.isfile(path):
        return entries
    for number, raw in enumerate(baseline_lines(path), 1):
        entry = baseline_entry(raw)
        if entry is not None:
            entries.setdefault(entry, number)
    return entries


def coverage(scenarios, tags):
    covered = {}
    for t in tags:
        if t.scenario is not None:
            covered.setdefault(t.scenario.key, []).append(t)
    return covered


# Ends the message for a tag that names no scenario or no capability: the tag may be
# text in a file that is not a test.
NOT_A_TEST = f"If the file is not a test, add a pattern for its path to {IGNORE_FILE}."


def tag_problem(t, scenarios):
    if t.problem == "ambiguous":
        # A log of this output saved in the repository is searched by the next run. The
        # choice lines never read as a tag, so they never count for a scenario; the echo
        # of the bad tag does read as one, but it is ambiguous again.
        lines = "\n".join(f"      {key}" for key in t.choices)
        return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' is ambiguous: that scenario name "
                f"appears under more than one requirement. Name the requirement too: write `@scenario` "
                f"followed by one of these lines:\n{lines}")
    if t.problem == "capability":
        caps = sorted({s.capability for s in scenarios})
        hint = difflib.get_close_matches(t.capability, caps, n=1)
        more = f" Did you mean '{hint[0]}'?" if hint else f" Capabilities: {', '.join(caps)}."
        return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' names no capability under "
                f"openspec/specs.{more} {NOT_A_TEST}")
    names = [s.ident for s in scenarios if s.capability == t.capability]
    hint = difflib.get_close_matches(t.text, names, n=1, cutoff=0.5)
    more = f" Did you mean '{hint[0]}'?" if hint else ""
    return (f"{t.where}: tag '@scenario {t.capability}: {t.text}' names no scenario in "
            f"openspec/specs/{t.capability}/spec.md.{more} If the scenario was renamed, change the "
            f"tag to its new name; if it was removed, delete the tag. {NOT_A_TEST}")


PRUNE_HINT = "Run `baseline --prune` to remove this line, and commit the result with the change."


def check(root, lines, baseline_path):
    scenarios, problems = load_scenarios(root)
    tags = scan_tags(lines, scenarios, pending_scenarios(root))
    covered = coverage(scenarios, tags)
    baseline = read_baseline(baseline_path)
    rel_baseline = os.path.relpath(baseline_path, root)
    keys = {s.key for s in scenarios}

    for s in scenarios:
        if s.key not in covered and s.key not in baseline:
            problems.append(
                f"{s.path}:{s.line}: no test tags scenario '{s.key}'. Tag the test that checks it with "
                f"`@scenario` followed by this line, or write that test:\n      {s.key}")
    problems += [tag_problem(t, scenarios) for t in tags if t.problem]
    for entry, number in sorted(baseline.items(), key=lambda e: e[1]):
        if entry in covered:
            where = ", ".join(t.where for t in covered[entry])
            problems.append(f"{rel_baseline}:{number}: '{entry}' is now tagged by {where}. {PRUNE_HINT}")
        elif entry not in keys:
            problems.append(f"{rel_baseline}:{number}: '{entry}' names no scenario in openspec/specs. "
                            f"{PRUNE_HINT}")

    if problems:
        for p in problems:
            print(p)
        print(f"\nspec-trace: {len(problems)} problem(s). {len(covered)} of {len(scenarios)} scenarios "
              f"are tagged; {len(baseline)} are in the baseline.")
        return 1
    print(f"spec-trace: ok. {len(covered)} of {len(scenarios)} scenarios are tagged; "
          f"{len(baseline)} untagged ones are in the baseline.")
    return 0


def tagged_scenarios(root, lines):
    """The main specs' scenarios and which of them tests tag. None, after printing
    load_scenarios' problems, when two scenarios share a name under one requirement:
    no tag or baseline line can tell those apart."""
    scenarios, problems = load_scenarios(root)
    if problems:
        for p in problems:
            print(p)
        return None
    return scenarios, coverage(scenarios, scan_tags(lines, scenarios, pending_scenarios(root)))


def write_baseline(root, lines, baseline_path):
    rel = os.path.relpath(baseline_path, root)
    if os.path.lexists(baseline_path):
        # A rewrite would add every scenario untagged today, exempting new ones that have no test.
        print(f"spec-trace: {rel} already exists, so baseline wrote nothing. Run `baseline --prune` "
              "to drop its lines that are now tagged or name no scenario, or delete the file first "
              "to write it from scratch.")
        return 2
    found = tagged_scenarios(root, lines)
    if found is None:
        return 1
    scenarios, covered = found
    untagged = sorted(s.key for s in scenarios if s.key not in covered)
    os.makedirs(os.path.dirname(baseline_path) or ".", exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as f:
        f.write("# Scenarios in openspec/specs that no test tagged when spec-trace was adopted.\n"
                "# spec-trace check fails on a line whose scenario a test now tags, or that names no\n"
                "# scenario: run `baseline --prune` to remove such lines. Never add one; a new scenario\n"
                "# gets a tagged test instead. Keep this file when no scenario is left in it: it\n"
                "# records that this repository adopted spec-trace.\n")
        for key in untagged:
            f.write(key + "\n")
    print(f"spec-trace: wrote {len(untagged)} untagged scenario(s) of {len(scenarios)} to {rel}.")
    return 0


def prune_baseline(root, lines, baseline_path):
    """Remove the baseline lines `check` fails on, keeping every other line as written. Never adds one."""
    rel = os.path.relpath(baseline_path, root)
    if not os.path.isfile(baseline_path):
        print(f"spec-trace: there is no baseline file at {rel}, so there is nothing to prune.")
        return 2
    found = tagged_scenarios(root, lines)
    if found is None:
        return 1
    scenarios, covered = found
    keys = {s.key for s in scenarios}
    kept, removed = [], []
    for number, raw in enumerate(baseline_lines(baseline_path), 1):
        entry = baseline_entry(raw)
        if entry in covered:
            where = ", ".join(t.where for t in covered[entry])
            removed.append(f"{rel}:{number}: removed '{entry}': now tagged by {where}.")
        elif entry is not None and entry not in keys:
            removed.append(f"{rel}:{number}: removed '{entry}': names no scenario in openspec/specs.")
        else:
            kept.append(raw)
    remain = sum(1 for raw in kept if baseline_entry(raw) is not None)
    if not removed:
        print(f"spec-trace: nothing to prune; {rel} is unchanged, with {remain} scenario line(s).")
        return 0
    with open(baseline_path, "w", encoding="utf-8", newline="") as f:
        f.writelines(kept)
    for line in removed:
        print(line)
    keep = (" Keep the file: it records that this repository adopted spec-trace."
            if not remain else "")
    print(f"spec-trace: pruned {len(removed)} line(s) from {rel}; {remain} scenario line(s) remain.{keep} "
          "Commit it with the change.")
    return 0


def cell(text):
    return text.replace("|", "\\|")


RUNNER_EXCLUDES_HINT = ("If any of these directories holds tests your test runner doesn't run, "
                        f"ask your agent to add it to {IGNORE_FILE}.")


def where_found(lines):
    """Print each directory holding a tag, with its count of files and tags, sorted by path.

    A tag counts wherever the search finds it, even in a file the test runner
    excludes. This list is how a person spots such a directory.
    """
    found = {}
    for rel, _, line in lines:
        count = len(TAG.findall(line))
        if count:
            files, tags = found.setdefault(os.path.dirname(rel) or ".", (set(), [0]))
            files.add(rel)
            tags[0] += count
    print("\n### Where tags were found\n")
    if not found:
        print("No tags were found.")
        return
    print("| Directory | Files | Tags |")
    print("| --- | --- | --- |")
    for folder in sorted(found):
        files, tags = found[folder]
        print(f"| {cell(folder)} | {len(files)} | {tags[0]} |")
    print(f"\n{RUNNER_EXCLUDES_HINT}")


def report(root, lines, include_changes):
    scenarios, problems = load_scenarios(root, include_changes)
    tags = scan_tags(lines, scenarios, () if include_changes else pending_scenarios(root))
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
    where_found(lines)
    bad = [tag_problem(t, scenarios) for t in tags if t.problem] + problems
    if bad:
        print("\n### Problems\n")
        for p in bad:
            print("- " + p.replace("\n", " ").replace("      ", " "))
    return 0


def git_top(root):
    """The top of the git repository holding root, or None outside one."""
    try:
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    # Only the newline goes: a folder name may end in a space.
    return (top.stdout.rstrip("\n") or None) if top.returncode == 0 else None


# spec_trace.py by name: test_spec_trace.py, the checker's own tests, does not count.
RUNS_CHECKER = re.compile(r"(?<![\w.-])spec_trace\.py")


# Characters runs_checker_in_ci reads from one workflow file at most. A mention
# of spec_trace.py past it is not seen; real workflows are a few kilobytes.
WORKFLOW_LIMIT = 1_000_000


def read_regular_file(path, limit, encoding="utf-8"):
    """Up to limit + 1 characters of path, or None when it is not a regular file
    (a link to one counts) or cannot be read. Only a regular file is opened,
    because a repository can commit a link to a FIFO, whose open blocks, or to
    a device such as /dev/zero, which never ends. limit bounds what a large
    regular file costs."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding=encoding, errors="replace") as f:
            return f.read(limit + 1)
    except OSError:
        return None


def runs_checker_in_ci(root):
    """Does a GitHub Actions workflow in root/.github/workflows name spec_trace.py?
    Only root's own workflows count: a workflow at the top of a monorepo that
    checks one project says nothing about another."""
    folder = os.path.join(root, WORKFLOWS)
    try:
        names = os.listdir(folder)
    except OSError:
        return False
    for name in names:
        if name.endswith((".yml", ".yaml")):
            text = read_regular_file(os.path.join(folder, name), WORKFLOW_LIMIT)
            if text and RUNS_CHECKER.search(text):
                return True
    return False


def says_declined(text):
    """Is DECLINED_TEXT the file's only line, ignoring blank lines, # comments
    and spacing around the colon?"""
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(lines) != 1:
        return False
    key, sep, value = lines[0].partition(":")
    return bool(sep) and key.strip() == "adoption" and value.strip() == "declined"


def adoption_state(root, baseline=DEFAULT_BASELINE):
    """ADOPTED, DECLINED, UNDECIDED or UNKNOWN for the repository at root, or
    None when root has no openspec/ directory: spec-trace does not apply there.

    ADOPTED: the baseline file, or a GitHub workflow in root/.github/workflows
    that runs spec_trace.py. The baseline stays once every scenario is tagged,
    as the record of adoption; the workflow counts too because --baseline can
    move the file where the hook, which passes no --baseline, does not look.
    IGNORE_FILE is not a sign of adoption. Adoption wins over a decision file
    left behind.
    DECLINED: DECISION_FILE says DECLINED_TEXT. UNKNOWN: DECISION_FILE exists
    but says anything else, is longer than DECISION_FILE_LIMIT, is not a
    regular file, or cannot be read; neither the hook nor `decline` acts on it.
    """
    if not os.path.isdir(os.path.join(root, "openspec")):
        return None
    if os.path.isfile(os.path.join(root, baseline)) or runs_checker_in_ci(root):
        return ADOPTED
    path = os.path.join(root, DECISION_FILE)
    if not os.path.lexists(path):
        return UNDECIDED
    # utf-8-sig: a file written by hand on Windows may start with a byte order mark.
    text = read_regular_file(path, DECISION_FILE_LIMIT, encoding="utf-8-sig")
    # The file holds one line. Past the limit, a cut-off read could drop a line
    # that makes it unknown, so a longer file is unknown.
    if text is None or len(text) > DECISION_FILE_LIMIT:
        return UNKNOWN
    return DECLINED if says_declined(text) else UNKNOWN


def unknown_reason(root):
    """Why adoption_state said UNKNOWN for root, as a sentence without its full stop."""
    path = os.path.join(root, DECISION_FILE)
    try:
        if not os.path.isfile(path):
            raise OSError
        with open(path, "rb"):
            pass
    except OSError:
        return f"spec-trace: {DECISION_FILE} cannot be read"
    return f"spec-trace: {DECISION_FILE} holds something other than `{DECLINED_TEXT}`"


def decline(root, baseline, dry_run):
    """Write DECISION_FILE, holding DECLINED_TEXT."""
    state = adoption_state(root, baseline)
    if state is None:
        print(f"spec-trace: {root} has no openspec/ directory, so there is nothing to decline.")
        return 2
    if state == ADOPTED:
        print("spec-trace: this repository has adopted spec-trace (it has the baseline file, "
              "or a workflow that runs spec_trace.py), so nothing was declined. "
              "To stop using it, remove those first, then run decline again.")
        return 1
    if state == UNKNOWN:
        print(f"{unknown_reason(root)}, so nothing was declined. "
              "Fix or delete it, then run decline again.")
        return 1
    if state == DECLINED:
        print(f"spec-trace: {DECISION_FILE} already declines spec-trace; nothing changed.")
        return 0
    if dry_run:
        print(f"spec-trace: would write {DECISION_FILE}:\n{DECLINED_TEXT}")
        return 0
    with open(os.path.join(root, DECISION_FILE), "w", encoding="utf-8") as f:
        f.write(DECLINED_TEXT + "\n")
    print(f"spec-trace: wrote {DECISION_FILE}, which declines spec-trace for this repository. "
          "Commit it, so no agent asks again.")
    return 0


# A spec under openspec/specs/ or in an open change, relative to the top of the
# repository. An archived change (openspec/changes/archive/<name>/specs/) has
# one more level, so it never matches.
SPEC_PATH = re.compile(r"openspec/(?:specs|changes/[^/]+/specs)/(?:[^/]+/)+spec\.md")


def same_folder(a, b):
    """Are a and b the same folder, however each is spelled? False when either is missing."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def hook_message(payload):
    """What the hook tells the agent after it writes a file, or None for silence.

    payload is the hook's input: Claude Code's PostToolUse (tool_input
    file_path), Cursor's postToolUse (tool_input file_path or path) or Cursor's
    afterFileEdit (file_path). The message goes out only when the file is an
    OpenSpec spec in a git repository that has neither adopted nor declined
    spec-trace. The repository is its git top level: a spec must sit in the
    top's own openspec/, and an openspec/ folder below the top (a test fixture,
    a project in a monorepo) is never asked about.
    """
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    found = []
    if isinstance(tool_input, dict):
        found += [tool_input.get("file_path"), tool_input.get("path")]
    found.append(payload.get("file_path"))
    path = next((p for p in found if isinstance(p, str) and p), None)
    if path is None:
        return None
    if not os.path.isabs(path):
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            return None
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    # The path stays as written, and each folder above an openspec/ in it is
    # compared with git's top by identity, not spelling. git prints the top
    # resolved (on macOS /var is a link to /private/var); resolving the written
    # path would also follow an openspec/ link into the folder it points at,
    # whose path no longer ends in openspec/.
    written = path.replace(os.sep, "/")
    candidates = [written[:i] or "/" for i in range(len(written))
                  if written.startswith("/openspec/", i)
                  and SPEC_PATH.fullmatch(written[i + 1:])]
    if not candidates:
        return None
    # git runs from the spec's folder, or the nearest one that exists, without
    # resolving links first, so it follows an openspec/ link. When openspec/
    # links outside the repository, git finds no top, or another repository's,
    # and the hook says nothing. That is deliberate: a spec-trace.yaml written
    # through that link would land outside this repository and not be committed
    # in it, so it would not stop this repository's agents asking. Running git
    # from a folder above openspec/ instead would make the hook ask there.
    folder = os.path.dirname(path)
    while not os.path.isdir(folder) and os.path.dirname(folder) != folder:
        folder = os.path.dirname(folder)
    top = git_top(folder)
    if top is None:
        return None
    root = next((c for c in candidates if same_folder(c, top)), None)
    if root is None or adoption_state(root) != UNDECIDED:
        return None
    script = os.path.abspath(__file__)
    run = f"python3 {shlex.quote(script)} --root {shlex.quote(root)}"
    return ("This repository uses OpenSpec but hasn't decided on spec-trace, which links each "
            "test to the OpenSpec scenario it checks. Ask the user whether to adopt it (you can "
            "do it: the baseline, the CI step and the AGENTS.md line, as the spec-trace skill "
            f"says) or decline it (`{run} decline`). Either answer is committed to the "
            "repository, so no agent asks again.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spec_trace.py", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current directory)")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                        help=f"baseline file, relative to the root (default: {DEFAULT_BASELINE})")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="fail on an untagged scenario, a stale tag or a stale baseline line")
    base = sub.add_parser("baseline", help="write every untagged scenario to a new baseline file")
    base.add_argument("--prune", action="store_true",
                      help="instead, remove the lines of the existing baseline whose scenario is now "
                           "tagged or no longer exists; never adds a line")
    rep = sub.add_parser("report", help="print a markdown table of scenarios and the tests that tag them")
    rep.add_argument("--include-changes", action="store_true",
                     help="also list scenarios from open changes in openspec/changes/*/specs")
    sub.add_parser("state", help="print adopted, declined, undecided or unknown: what this "
                                 "repository has decided about spec-trace (n/a without openspec/)")
    dec = sub.add_parser("decline", help=f"write {DECISION_FILE}, declining spec-trace for this repository")
    dec.add_argument("--dry-run", action="store_true",
                     help="print what would be written, and change nothing")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    baseline = os.path.join(root, args.baseline)
    if args.command == "state":
        state = adoption_state(root, args.baseline)
        print(state or "n/a")
        if state == UNKNOWN:
            print(f"{unknown_reason(root)}.",
                  file=sys.stderr)
        return 0
    if args.command == "decline":
        return decline(root, args.baseline, args.dry_run)
    try:
        lines = tag_lines(root)
    except Refusal as e:
        print(f"spec-trace: {e}")
        return 2
    if args.command == "check":
        return check(root, lines, baseline)
    if args.command == "baseline" and args.prune:
        return prune_baseline(root, lines, baseline)
    if args.command == "baseline":
        return write_baseline(root, lines, baseline)
    return report(root, lines, args.include_changes)


if __name__ == "__main__":
    sys.exit(main())
