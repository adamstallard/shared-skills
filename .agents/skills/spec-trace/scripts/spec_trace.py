#!/usr/bin/env python3
"""Link tests to OpenSpec scenarios: each test names the scenario it checks with a tag.

A tag is `@scenario <capability>: <Scenario name>`, written in a test. `check` fails on:
- a scenario in openspec/specs that no tag names and the baseline file does not list;
- a tag that names no capability or no scenario, or names a repeated scenario name
  without its requirement;
- a baseline line whose scenario is now tagged, or no longer exists;
- two scenarios with the same name under one requirement, which no tag could tell apart.
It checks that a tag exists, not that its test runs or passes.

Tags are found with one `git grep` over every file under the root that .gitignore doesn't
match, tracked or not, except DEFAULT_EXCLUDES and the patterns in IGNORE_FILE. A tag
counts in any file the search reaches, not only in a test.

Standard library only. check, report and baseline need git; state and decline do not.
Why it is built this way, and what was rejected: ../DECISIONS.md.
"""

import argparse
import difflib
import os
import re
import shlex
import subprocess
import sys

DEFAULT_BASELINE = "openspec/spec-trace-baseline.txt"
# Paths never searched for tags: documentation, whose tag-shaped examples are not tests,
# and OpenSpec's own files. Git glob pathspecs relative to the root, which grep_command
# passes to git grep as excludes.
DEFAULT_EXCLUDES = ("**/*.md", "**/*.mdx", "**/*.rst", "**/*.adoc", "**/*.txt", "openspec/**")
# Optional. More paths to leave out of the search: one git glob pattern per line,
# relative to the root. Blank lines and lines starting with # are skipped.
IGNORE_FILE = "openspec/spec-trace-ignore.txt"
# The longest IGNORE_FILE accepted, in characters. ignore_patterns reads one character
# more; when it gets that character, the command refuses and exits 2.
IGNORE_FILE_LIMIT = 65536

# What a repository has decided about spec-trace, as adoption_state returns it. Its
# docstring says what puts a repository in each state.
ADOPTED, DECLINED, UNDECIDED, UNKNOWN = "adopted", "declined", "undecided", "unknown"
# spec-trace's own decision file, which `decline` writes. spec-trace never edits
# OpenSpec's config.yaml, so declining works in a repository that has none.
DECISION_FILE = "openspec/spec-trace.yaml"
DECLINED_TEXT = "adoption: declined"
# The longest DECISION_FILE accepted, in characters; adoption_state treats a longer
# one as UNKNOWN.
DECISION_FILE_LIMIT = 4096
WORKFLOWS = ".github/workflows"

REQUIREMENT = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SCENARIO = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
TAG = re.compile(r"@scenario\s+([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:")
# Where a tag's scenario name may end: at the end of the line, or before a closing quote,
# a comment closer (`*/` or `-->`), a `)`, `,` or `;`, or the `{` that opens a test's body.
# A period ends it only when a space, a quote, `)`, a comment closer or the line's end
# follows: a tag reading "Foo." names Foo, and one reading "Foo.bar" names Foo.bar.
TAG_END = re.compile(r"\s*(?:$|[\"'`),;{]|\*/|-->|\.(?:\s|$|[\"'`)]|\*/|-->))")
# A backslash-escaped quote inside a quoted test name is part of the name, never its end.
# longest() replaces each one with NOT_AN_END, a private-use character TAG_END never
# matches, to find where a name may end.
ESCAPED_QUOTES = ("\\'", '\\"')
NOT_AN_END = "\uE000"
# Joins a requirement and a scenario name in a qualified tag, `<Requirement> / <Scenario>`.
# A scenario whose name repeats within its capability can be tagged only this way.
QUALIFIER = " / "


def fence_after(line, fence):
    """Track Markdown code fences: the fence open after this line, and whether this line
    opens or closes one. The spec parsers skip fenced lines, so a scenario heading inside
    an example is not a scenario.

    A fence closes only on a line of the same character, at least as long, with nothing
    after it. Any other fence line inside it, such as ``` in a ~~~ example, is content.
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
        self.ident = name  # the name a tag uses; assign_idents qualifies a repeated one

    @property
    def key(self):
        return f"{self.capability}: {self.ident}"


def parse_spec(path, rel, capability, change=None):
    """The scenarios in one spec file, each with the requirement heading above it.

    Fenced lines are skipped. In a change's delta spec (change given), a REMOVED section's
    scenarios are left out.
    """
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
    """The requirement names a change's delta spec removes, renames (a dict, old name to
    new) and restates (adds or modifies)."""
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
    """The scenarios as they will be once the change is archived.

    Only scenarios in the given capability change. A removed requirement's scenarios are
    dropped, a renamed one's take its new name, and a restated one's are replaced by the
    change's own scenarios, which the caller passes as changed.
    """
    kept = []
    for s in scenarios:
        if s.capability == capability:
            if s.requirement in removed:
                continue
            if s.requirement in renamed:
                # The new name exists only in the change until it is archived, so the
                # scenario now belongs to the change. scan_tags neither counts a tag naming it
                # as coverage nor reports that tag as an error.
                s.requirement, s.change = renamed[s.requirement], change
            if s.requirement in restated:
                continue
        kept.append(s)
    return kept + changed


def assign_idents(scenarios):
    """Set ident to `<requirement> / <name>` for each scenario whose name repeats within
    its capability.

    Returns a message for each scenario that still shares an ident with an earlier one:
    the same name under the same requirement, which no tag can tell apart.
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
    """git cannot search the repository for tags. args[0] is the reason; main prints it
    and exits 2."""


def git_env(root):
    """The environment for the git commands that search root: this process's environment
    without GIT_DIR, or None to inherit this process's environment unchanged.

    Git exports GIT_DIR, without GIT_WORK_TREE, to hooks in a linked worktree and to
    `git rebase -x`. With it, `git -C root` takes root for the top of the work tree, and
    does not read a .gitignore above root, so files that .gitignore ignores would be
    searched for tags. GIT_DIR is dropped only when git, run from
    root without it, finds the same git directory. Otherwise it is kept: a separate git
    directory or a dotfiles setup needs it.
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
    # git applies -C before it reads GIT_DIR, so a relative GIT_DIR is relative to root.
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
    """The patterns in IGNORE_FILE, without blank and # lines; [] when there is no file.

    Raises Refusal when the file is not a regular file, cannot be read, or is longer than
    IGNORE_FILE_LIMIT.
    """
    path = os.path.join(root, IGNORE_FILE)
    if not os.path.lexists(path):
        return []
    # utf-8-sig drops a byte order mark, which some Windows editors write. Left in, it
    # would become part of the first pattern.
    text = read_regular_file(path, IGNORE_FILE_LIMIT, encoding="utf-8-sig")
    if text is None:
        raise Refusal(f"{IGNORE_FILE} cannot be read: it is not a regular file, or reading it failed.")
    if len(text) > IGNORE_FILE_LIMIT:
        raise Refusal(f"{IGNORE_FILE} is longer than {IGNORE_FILE_LIMIT} characters.")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def grep_command(root, patterns):
    """The git grep command that prints every line under root holding `@scenario`.

    --untracked also searches files not yet added, unless .gitignore matches them. -I
    skips binary files. -n and -z give the line numbers and NUL separators that tag_lines
    parses. Don't remove the options below: each one overrides a setting that a user's
    git config or environment may hold.
    - --no-full-name, --no-column, --no-color: grep.fullName (paths from the top of the
      repository), grep.column and colour settings would change the output tag_lines
      parses.
    - --no-recurse-submodules: with submodule.recurse set, git refuses --untracked.
    - --no-literal-pathspecs: GIT_LITERAL_PATHSPECS would read each exclude as a plain
      path, so none would apply.
    - -F: reads `@scenario` as plain text, whatever grep.patternType says.
    """
    excludes = [f":(exclude,glob){p}" for p in (*DEFAULT_EXCLUDES, *patterns)]
    return ["git", "--no-literal-pathspecs", "-C", root, "grep", "--untracked",
            "--no-recurse-submodules", "-I", "-n", "-z", "--no-color", "--no-column",
            "--no-full-name", "-F", "-e", "@scenario", "--", ".", *excludes]


def tag_lines(root):
    """Every line under root holding `@scenario`, as sorted (path relative to root, line
    number, text) tuples.

    Raises Refusal when git cannot run, root is not in a git work tree, IGNORE_FILE cannot
    be used, or git grep fails.
    """
    env = git_env(root)
    require_work_tree(root, env)
    patterns = ignore_patterns(root)
    try:
        result = subprocess.run(grep_command(root, patterns), capture_output=True, env=env)
    except (OSError, ValueError) as e:  # ValueError: a pattern in IGNORE_FILE holds a NUL
        raise Refusal(f"git grep could not be run ({e}).")
    if result.returncode == 1:
        return []  # git grep exits 1 when no line matches
    if result.returncode != 0:
        said = result.stderr.decode("utf-8", "replace").strip()
        hint = f" Check the patterns in {IGNORE_FILE}." if patterns else ""
        raise Refusal(f"git grep failed: {said or f'exit {result.returncode}'}.{hint}")
    # With -z, git grep prints each match as `path NUL number NUL text LF`. A path can hold
    # a newline, so it ends only at its NUL; the text ends at the newline.
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
        self.choices = choices  # for an ambiguous tag: the qualified keys it could mean
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
    """text with each backslash-escaped quote replaced by one character: quote_to, or the
    quote itself when quote_to is None.

    longest() makes two copies of a tag's text: one with each escape turned back into a
    plain quote, to compare with the names, and one with NOT_AN_END in place of each
    escape, to find where a name may end. Each escape becomes one
    character in both, so the copies stay the same length, and a name's length points at
    the same place in each.
    """
    for escaped in ESCAPED_QUOTES:
        text = text.replace(escaped, quote_to or escaped[1])
    return text


def shown(rest):
    """The text of a tag that names no scenario or no capability, cut where the tag most
    likely ends, for its error message.

    With no name to match, where the tag ends is a guess from quotes, comment closers and
    trailing punctuation.
    """
    # Hide each kind of escaped quote behind its own placeholder, so the cuts below never
    # take it for a closing quote. The last step puts the quotes back.
    held = {"\\'": "\uE001", '\\"': "\uE002"}
    for escaped, mark in held.items():
        rest = rest.replace(escaped, mark)
    for stop in ("*/", "-->"):
        if stop in rest:
            rest = rest[:rest.index(stop)]
    # When the rest of the line holds an odd number of " or of backticks, the tag sits inside
    # a test name quoted with that character, and its first occurrence closes the name. An even
    # number is taken as quotes in a comment's own text.
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
    """The longest of names that the tag's text starts with and that a TAG_END follows,
    or None.

    Every name is tried, and the longest match wins. A tag for "Claim precedes work, always"
    also starts with "Claim precedes work" and a comma, which is a tag end, so the shorter
    name matches too.
    """
    rest = norm(rest)
    text = unescape(rest, None)  # compared with the names
    ends = unescape(rest, NOT_AN_END)  # searched for a tag end; an escaped quote is never one
    best = None
    for name in names:
        if text.startswith(name) and TAG_END.match(ends, len(name)):
            if best is None or len(name) > len(best):
                best = name
    return best


def resolve(capability, rest, index):
    """(ident, scenario) for the scenario in index that a tag names, chosen by longest(),
    or None."""
    idents = index.get(capability, {})
    ident = longest(rest, idents)
    return (ident, idents[ident]) if ident is not None else None


def name_index(scenarios):
    index = {}
    for s in scenarios:
        caps = index.setdefault(s.capability, {})
        caps[s.ident] = s
        # The qualified name always resolves. The bare name is in the index only when it
        # is unique, because ident is the qualified name otherwise.
        caps.setdefault(f"{s.requirement}{QUALIFIER}{s.name}", s)
    return index


def pending_scenarios(root):
    """The scenarios that open changes add, restate, or move to a renamed requirement.

    A tag may name one of them before its change is archived; scan_tags neither counts
    nor rejects such a tag.
    """
    return [s for s in load_scenarios(root, include_changes=True)[0] if s.change]


def repeats(scenarios):
    """{(capability, name): scenarios} for each name that repeats within its capability.
    scan_tags reports a bare tag for one of these names as ambiguous."""
    out = {}
    for s in scenarios:
        if s.ident != s.name:
            out.setdefault((s.capability, s.name), []).append(s)
    return out


def scan_tags(lines, scenarios, pending=()):
    """The tags in lines, the (path, line number, text) tuples tag_lines returns.

    Each Tag names a main scenario or carries a problem: "capability" (no such
    capability), "orphan" (no such scenario) or "ambiguous" (a repeated name without its
    requirement). A tag naming a scenario in pending (one that an open change adds,
    restates or moves to a renamed requirement) gets no Tag: it is neither counted nor an
    error.
    """
    index, waiting = name_index(scenarios), name_index(pending)
    repeated, repeated_waiting = repeats(scenarios), repeats(pending)
    tags = []
    for rel, number, line in lines:
        starts = list(TAG.finditer(line))
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(line)
            capability, rest = m.group(1), line[m.end():end]
            # Every reading of the tag, with its rank:
            #   3, a main scenario: the tag counts for it;
            #   2, a name repeated in the main specs: ambiguous;
            #   1, a scenario an open change adds: neither counted nor an error;
            #   0, a name repeated in an open change: ambiguous.
            # The longest matched name wins, so a tag never counts for a shorter name its
            # text also starts with. On a tie the higher rank wins: the main specs first.
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
                elif rank != 1:  # rank 1, a scenario an open change adds, gets no Tag
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
    """The scenario a baseline line names, as `capability: name` with its spacing
    normalised, or None for a blank or # line.

    `check` and `baseline --prune` both read lines through this, so they agree on what each
    line names.
    """
    line = norm(raw)
    if not line or line.startswith("#"):
        return None
    cap, sep, name = line.partition(":")
    return f"{cap.strip()}: {name.strip()}" if sep else line


def baseline_lines(path):
    """The baseline file's lines, each with its line ending as written, so `baseline --prune`
    writes back the lines it keeps unchanged. `check` reads the file through this too.

    utf-8-sig drops a byte order mark, which some Windows editors write. Left in, it would
    make the first line name no scenario, and `--prune` would delete that line.
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


# Ends the message for a tag that names no scenario or no capability. The search reads
# files that are not tests, and tag-shaped text in one, such as an example in an HTML
# doc or a docstring, fails this way.
NOT_A_TEST = f"If the file is not a test, add a pattern for its path to {IGNORE_FILE}."


def tag_problem(t, scenarios):
    if t.problem == "ambiguous":
        # The choice lines leave out `@scenario` so that no line of this message could make a
        # scenario count as tested. spec-trace never saves its output, but if a person saved
        # it to a file in the repository, the next run would search that file. There, the
        # echo of the bad tag would fail as ambiguous again, and count for no scenario.
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
    """The main specs' scenarios, and coverage(): the tags naming each one.

    Returns None, after printing load_scenarios' problems, when two scenarios share a name
    under one requirement: no tag or baseline line could tell them apart.
    """
    scenarios, problems = load_scenarios(root)
    if problems:
        for p in problems:
            print(p)
        return None
    return scenarios, coverage(scenarios, scan_tags(lines, scenarios, pending_scenarios(root)))


def write_baseline(root, lines, baseline_path):
    rel = os.path.relpath(baseline_path, root)
    if os.path.lexists(baseline_path):
        # Never rewrite a baseline. A rewrite would list every scenario untagged today, so it
        # would exempt each scenario added since adoption that has no test.
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
    """Remove the baseline lines `check` fails on: those whose scenario is now tagged, and
    those that name no scenario. Every other line, comments included, stays as written.
    Never adds a line."""
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
    """Print a table of each directory holding a tag, with how many files and tags it
    holds, sorted by path.

    A tag counts wherever the search finds it, even in a file the test runner never runs.
    This table is how a person spots such a directory, to add it to IGNORE_FILE.
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
    """The top of the git work tree holding root; None outside one, or when git cannot run
    or takes over 5 seconds."""
    try:
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    # Only the newline goes: a folder name may end in a space.
    return (top.stdout.rstrip("\n") or None) if top.returncode == 0 else None


# A mention of spec_trace.py itself. test_spec_trace.py, the checker's own tests, does not
# match, so a workflow that only runs those tests is not adoption.
RUNS_CHECKER = re.compile(r"(?<![\w.-])spec_trace\.py")


# The most characters runs_checker_in_ci searches in one workflow file. A mention of
# spec_trace.py past it is missed; real workflows are a few kilobytes.
WORKFLOW_LIMIT = 1_000_000


def read_regular_file(path, limit, encoding="utf-8"):
    """Up to limit + 1 characters of path, so a caller can tell when the file is longer
    than limit; None when path is not a regular file (a link to one counts) or cannot be
    read.

    Only a regular file is opened, because a repository can commit a link to a FIFO, and
    opening a FIFO blocks until something writes to it. limit bounds what a large regular
    file costs.
    """
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
    """What the repository at root has decided about spec-trace: ADOPTED, DECLINED,
    UNDECIDED or UNKNOWN. None when root has no openspec/ directory: spec-trace does not
    apply there.

    - ADOPTED: root has the baseline file, or a workflow in root/.github/workflows that
      runs spec_trace.py. The baseline file stays after its last scenario is tagged, as
      the record of adoption. The workflow counts because --baseline can put the file
      where the agent hook (hook_message), which calls this with the default path, does
      not look. IGNORE_FILE
      alone is not adoption. Adoption wins over any DECISION_FILE.
    - DECLINED: DECISION_FILE holds DECLINED_TEXT.
    - UNKNOWN: DECISION_FILE holds anything else, is longer than DECISION_FILE_LIMIT, is
      not a regular file, or cannot be read. The hook stays silent, and `decline` refuses.
    - UNDECIDED: none of these.
    """
    if not os.path.isdir(os.path.join(root, "openspec")):
        return None
    if os.path.isfile(os.path.join(root, baseline)) or runs_checker_in_ci(root):
        return ADOPTED
    path = os.path.join(root, DECISION_FILE)
    if not os.path.lexists(path):
        return UNDECIDED
    # utf-8-sig drops a byte order mark, which some Windows editors write.
    text = read_regular_file(path, DECISION_FILE_LIMIT, encoding="utf-8-sig")
    # A file longer than the limit is UNKNOWN. A cut-off read might miss a second line,
    # and a second line makes the file UNKNOWN.
    if text is None or len(text) > DECISION_FILE_LIMIT:
        return UNKNOWN
    return DECLINED if says_declined(text) else UNKNOWN


def unknown_reason(root):
    """Why adoption_state returned UNKNOWN for root: a sentence without its full stop, for
    the caller to finish."""
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
    """Write DECISION_FILE, holding DECLINED_TEXT, in an UNDECIDED repository, and return
    the exit code.

    Changes nothing, and says why, when the repository has no openspec/ (exit 2), is
    ADOPTED or UNKNOWN (exit 1), or is already DECLINED (exit 0), or with dry_run.
    """
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


# A spec under openspec/specs/ or in an open change, as a path relative to the top of the
# repository. An archived change's spec, under openspec/changes/archive/<name>/specs/, has
# one more folder before specs/, so it never matches.
SPEC_PATH = re.compile(r"openspec/(?:specs|changes/[^/]+/specs)/(?:[^/]+/)+spec\.md")


def same_folder(a, b):
    """Are a and b the same folder, however each is spelled? False when either is missing."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def hook_message(payload):
    """What the hook tells the agent after it writes a file, or None for silence.

    There is a message only when the file is an OpenSpec spec in the openspec/ folder at
    the top of a git repository, and that repository is UNDECIDED. An openspec/ folder
    below the top, such as a test fixture or a project in a monorepo, is never asked about.

    payload is the hook's input. Claude Code's PostToolUse puts the path in tool_input's
    file_path. Cursor's docs don't say where postToolUse puts it, so tool_input's path is
    read too. A top-level file_path, the shape of Cursor's afterFileEdit, is read as well:
    the skill's hook.json does not wire that event, but a person might by hand.
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
    # Keep the path as written. Each folder in it that holds an openspec/, a candidate
    # root, is compared with git's top by identity (same_folder), not by spelling. git prints the top with links
    # resolved: on macOS, /var is a link to /private/var. Resolving the written path instead
    # would also follow an openspec/ that is a link, and the result would no longer end in
    # openspec/.
    written = path.replace(os.sep, "/")
    candidates = [written[:i] or "/" for i in range(len(written))
                  if written.startswith("/openspec/", i)
                  and SPEC_PATH.fullmatch(written[i + 1:])]
    if not candidates:
        return None
    # Run git from the spec's folder, or the nearest folder above it that exists, without
    # resolving links, so git follows an openspec/ that is a link. If that link points
    # outside the repository, git finds no top or another repository's, and the hook stays
    # silent on purpose. In that case `decline` would write spec-trace.yaml through the link,
    # outside this repository, so the decision could not be committed here and agents
    # would keep asking. Don't run git from the folder above openspec/ instead: it would
    # find this repository, and the hook would ask a question no answer can settle.
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
