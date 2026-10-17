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
import configparser
import difflib
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_BASELINE = "openspec/spec-trace-baseline.txt"
# Test globs set by hand, one per line, `!` before a glob to exclude: used in place of detection.
TESTS_FILE = "openspec/spec-trace-tests.txt"
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


def closing(pattern, i, open_, close):
    """The index of the bracket closing the one at i, or ValueError."""
    depth = 0
    for j in range(i, len(pattern)):
        if pattern[j] == open_:
            depth += 1
        elif pattern[j] == close:
            depth -= 1
            if not depth:
                return j
    raise ValueError(f"unclosed {open_} in {pattern}")


def split_top(body, sep):
    """body split at each sep outside brackets."""
    parts, depth, start = [], 0, 0
    for j, c in enumerate(body):
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
        elif c == sep and not depth:
            parts.append(body[start:j])
            start = j + 1
    return parts + [body[start:]]


EXTGLOB = {"?": "?", "*": "*", "+": "+", "@": ""}


def glob_regex(pattern):
    """A glob as regex source: **, *, ?, [...], {a,b} and the extglobs ?(), *(), +(), @()."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c in "?*+@!" and pattern.startswith("(", i + 1):
            if c == "!":
                raise ValueError(f"!(...) is not supported in {pattern}")
            end = closing(pattern, i + 1, "(", ")")
            alternatives = "|".join(glob_regex(a) for a in split_top(pattern[i + 2:end], "|"))
            out.append(f"(?:{alternatives}){EXTGLOB[c]}")
            i = end + 1
        elif c == "{":
            end = closing(pattern, i, "{", "}")
            out.append("(?:" + "|".join(glob_regex(a) for a in split_top(pattern[i + 1:end], ",")) + ")")
            i = end + 1
        elif c == "[" and pattern.find("]", i + 2) != -1:
            end = pattern.find("]", i + 2)
            body = pattern[i + 1:end]
            negate = body[:1] in ("!", "^")
            body = body[1:] if negate else body
            out.append("[" + ("^/" if negate else "") + body.replace("\\", "\\\\") + "]")
            i = end + 1
        elif pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def glob_to_regex(pattern):
    return re.compile("^" + glob_regex(pattern) + "$")


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


def read_tests_file(path):
    """The globs in a tests file: one per line, blank lines and # comments skipped."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def matcher(pattern):
    """A match function for a glob, or for a compiled regex searched in "/" + the path.

    The leading / is there because Jest matches its testRegex against an absolute path.
    """
    if isinstance(pattern, str):
        return glob_to_regex(pattern).match
    return lambda f: pattern.search("/" + f)


def test_files(root, includes, excludes=()):
    include, exclude = [matcher(p) for p in includes], [matcher(p) for p in excludes]
    return sorted(f for f in list_files(root)
                  if any(m(f) for m in include) and not any(m(f) for m in exclude))


# The test files each runner uses when its configuration names none, as each runner
# documents them; Vitest and Jest write these with extglobs.
VITEST_DEFAULT = ["**/*.{test,spec}.?(c|m)[jt]s?(x)"]
VITEST_DEFAULT_EXCLUDE = ["**/node_modules/**", "**/dist/**"]
JEST_DEFAULT = ["**/__tests__/**/*.?([mc])[jt]s?(x)", "**/?(*.)+(spec|test).?([mc])[jt]s?(x)"]
PYTEST_DEFAULT_FILES = ["test_*.py", "*_test.py"]
# The extensions a Vitest, Vite or Jest config file may have.
CONFIG_EXTS = ("ts", "mts", "cts", "js", "mjs", "cjs")


class Unreadable(Exception):
    """A runner's configuration spec-trace cannot read with confidence.

    args[0] says what could not be read and why; args[1], when given, names the file.
    """


JS_TOKEN = re.compile(r"""
    (?P<string>'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\$]|\\.|\$(?!\{))*`)
  | (?P<template>`)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<space>\s+)
  | (?P<word>[A-Za-z_$][\w$]*)
  | (?P<spread>\.\.\.)
  | (?P<slash>/)
  | (?P<other>.)
""", re.S | re.X)


def js_tokens(text):
    """A JavaScript config's tokens as (kind, text), without comments or spaces.

    A / outside a string or comment is a regex literal or a division, and a template with
    ${...} computes its text; neither is read, so either makes the whole file Unreadable.
    """
    tokens = []
    for m in JS_TOKEN.finditer(text):
        kind = m.lastgroup
        if kind in ("comment", "space"):
            continue
        line = text.count("\n", 0, m.start()) + 1
        if kind == "slash":
            raise Unreadable(f"the file, which has a regex literal or a division on line {line}")
        if kind == "template":
            raise Unreadable(f"the file, which has a template string with ${{...}} on line {line}")
        tokens.append((kind, m.group()))
    return tokens


def js_unescape(literal):
    """A string literal's value: each backslash escape is the character it escapes."""
    return re.sub(r"\\(.)", r"\1", literal[1:-1])


def js_settings(text, paths, refused=()):
    """The string values at each key path (e.g. ("test", "include")) of a JS config.

    Walks the tokens tracking object nesting by key. The path is made of the keys of the
    enclosing objects; an object or array with no key of its own, such as a call's
    argument, adds nothing to it. So `defineConfig({ test: { include: [...] } })` gives
    ("test", "include"), while `coverage: { include: [...] }` inside it does not. Raises Unreadable wherever a wanted
    value could hide: a value that is not a string literal or an array of them, a key on the
    way to one (`test`) whose value is not an object literal, a shorthand or spread at a
    level where a wanted key could be, a key set twice, and any key in `refused`.
    """
    tokens = js_tokens(text)
    prefixes = {p[:k] for p in paths for k in range(1, len(p))}
    found = {}
    stack = []  # the key that opened each enclosing { or [, or None
    i = 0
    while i < len(tokens):
        kind, tok = tokens[i]
        named = tuple(k for k in stack if k is not None)
        level = [p for p in paths | prefixes | set(refused) if p[:-1] == named]
        if kind in ("word", "string") and i + 1 < len(tokens) and tokens[i + 1][1] == ":":
            key = js_unescape(tok) if kind == "string" else tok
            path = named + (key,)
            if path in refused:
                raise Unreadable(f"{'.'.join(path)}, which spec-trace does not read")
            if path in paths:
                if path in found:
                    raise Unreadable(f"{'.'.join(path)}, which is set twice")
                found[path], i = js_value(tokens, i + 2, path)
                continue
            opens = i + 2 < len(tokens) and tokens[i + 2] in (("other", "{"), ("other", "["))
            if path in prefixes and not (opens and tokens[i + 2][1] == "{"):
                raise Unreadable(f"{'.'.join(path)}, which is not an object literal")
            if opens:
                stack.append(key)
                i += 3
                continue
            i += 2
            continue
        if level and kind == "spread":
            raise Unreadable(f"{'.'.join(named) or 'the config'}, which has a spread (...)")
        if level and kind == "word" and any(tok == p[-1] for p in level) \
                and i + 1 < len(tokens) and tokens[i + 1][1] in ",}":
            raise Unreadable(f"{'.'.join(named + (tok,))}, which is a shorthand property")
        if kind == "other" and tok in "{[":
            stack.append(None)
        elif kind == "other" and tok in "}]" and stack:
            stack.pop()
        i += 1
    return found


def js_value(tokens, i, path):
    """The strings of the value at tokens[i], and the index after it."""
    name = ".".join(path)
    if i < len(tokens) and tokens[i][0] == "string" and (i + 1 == len(tokens) or tokens[i + 1][1] in ",}"):
        return [js_unescape(tokens[i][1])], i + 1
    if i >= len(tokens) or tokens[i][1] != "[":
        raise Unreadable(f"{name}, which is computed rather than a list of string literals")
    values, i = [], i + 1
    while i < len(tokens) and tokens[i][1] != "]":
        kind, tok = tokens[i]
        if kind == "string":
            values.append(js_unescape(tok))
        elif tok != ",":
            raise Unreadable(f"{name}, which is computed rather than a list of string literals")
        i += 1
    return values, i + 1


def read_text(root, name):
    with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def first_existing(root, names):
    for name in names:
        if os.path.isfile(os.path.join(root, name)):
            return name
    return None


def checked_globs(globs, key):
    """globs, after checking spec-trace can match each one."""
    for glob in globs:
        try:
            glob_to_regex(glob)
        except (ValueError, re.error) as e:
            raise Unreadable(f"{key}, which has a glob spec-trace cannot match ({e})")
    return globs


def detect_vitest(root):
    name = first_existing(root, [f"{base}.config.{ext}" for base in ("vitest", "vite") for ext in CONFIG_EXTS])
    if name is None:
        return None
    try:
        workspace = first_existing(root, [f"vitest.workspace.{ext}" for ext in CONFIG_EXTS + ("json",)])
        if workspace:
            raise Unreadable(f"its projects, which {workspace} defines")
        text = read_text(root, name)
        if name.startswith("vite.") and not re.search(r"\btest\s*:", text):
            return None  # a Vite config with no test settings says nothing about Vitest
        settings = js_settings(text, {("test", "include"), ("test", "exclude")},
                               refused={("test", "projects"), ("test", "workspace"), ("test", "includeSource"),
                                        ("test", "dir"), ("test", "root"), ("root",)})
        include = settings.get(("test", "include"))
        exclude = checked_globs(settings.get(("test", "exclude"), VITEST_DEFAULT_EXCLUDE), "test.exclude")
        if include is not None:
            return name, f"{name} (test.include)", checked_globs(include, "test.include"), exclude
        return name, f"{name} (Vitest's default include)", VITEST_DEFAULT, exclude
    except Unreadable as e:
        raise Unreadable(e.args[0], name)


# Jest settings that change which files are tests or what a glob is relative to.
JEST_REFUSED = ("projects", "rootDir", "roots")


def detect_jest(root):
    name = first_existing(root, [f"jest.config.{ext}" for ext in CONFIG_EXTS + ("json",)])
    try:
        if name is not None and name.endswith(".json"):
            try:
                config = json.loads(read_text(root, name))
            except ValueError:
                raise Unreadable("its JSON")
        elif name is not None:
            settings = js_settings(read_text(root, name), {("testMatch",), ("testRegex",)},
                                   refused={(key,) for key in JEST_REFUSED})
            config = {key[0]: value for key, value in settings.items()}
        else:
            if not os.path.isfile(os.path.join(root, "package.json")):
                return None
            try:
                config = json.loads(read_text(root, "package.json")).get("jest")
            except (ValueError, AttributeError):
                return None
            if not isinstance(config, dict):
                return None
            name = "package.json"
        if not isinstance(config, dict):
            raise Unreadable("its settings, which are not an object")
        for key in JEST_REFUSED:
            if key in config:
                raise Unreadable(f"{key}, which spec-trace does not read")
        regex = config.get("testRegex")
        if regex:
            try:
                regexes = [re.compile(r) for r in ([regex] if isinstance(regex, str) else regex)]
            except (re.error, TypeError):
                raise Unreadable("testRegex, which is not a Python regular expression")
            return name, f"{name} (testRegex)", regexes, []
        match = config.get("testMatch")
        if match:
            if not isinstance(match, list) or not all(isinstance(g, str) for g in match):
                raise Unreadable("testMatch, which is not a list of globs")
            if any(g.startswith("!") for g in match):
                raise Unreadable("testMatch, which has a negated (!) entry")
            globs = checked_globs([g.replace("<rootDir>/", "") for g in match], "testMatch")
            return name, f"{name} (testMatch)", globs, []
        return name, f"{name} (Jest's default testMatch)", JEST_DEFAULT, []
    except Unreadable as e:
        raise Unreadable(e.args[0], name)


def detect_pytest(root):
    for name in ("pytest.toml", ".pytest.toml"):
        if os.path.isfile(os.path.join(root, name)):
            raise Unreadable("its settings, since spec-trace does not read this file", name)
    # pytest's own order. pytest.ini and .pytest.ini are read even with no [pytest] section;
    # the others only when they hold pytest settings.
    for name, section in (("pytest.ini", None), (".pytest.ini", None), ("pyproject.toml", None),
                          ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        if name == "pyproject.toml":
            options = pyproject_pytest(path)
            if options is None:
                continue
        else:
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read(path, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError) as e:
                raise Unreadable(f"its settings ({e})", name)
            if section is None:
                section = "pytest"
                if not parser.has_section(section):
                    return name, f"{name} (pytest's defaults)", pytest_globs([], []), []
            if not parser.has_section(section):
                continue
            options = dict(parser.items(section))
        globs = pytest_globs(words(options.get("testpaths", [])), words(options.get("python_files", [])))
        try:
            return name, f"{name} (pytest testpaths and python_files)", \
                checked_globs(globs, "testpaths and python_files"), []
        except Unreadable as e:
            raise Unreadable(e.args[0], name)
    return None


def words(value):
    """A pytest list setting: a list, or a string of whitespace-separated words."""
    if isinstance(value, list):
        return [w for v in value for w in str(v).split()]
    return str(value).split()


def pyproject_pytest(path):
    """[tool.pytest.ini_options] of a pyproject.toml, or None."""
    try:
        import tomllib
    except ImportError:
        tomllib = None
    if tomllib is None:
        with open(path, encoding="utf-8") as f:
            if "[tool.pytest" not in f.read():
                return None
        raise Unreadable(f"[tool.pytest.ini_options], since Python {sys.version.split()[0]} "
                         "has no tomllib (Python 3.11 or later does)", "pyproject.toml")
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            raise Unreadable(f"its settings ({e})", "pyproject.toml")
    pytest = data.get("tool", {}).get("pytest", {})
    if not isinstance(pytest, dict) or set(pytest) - {"ini_options"}:
        raise Unreadable("[tool.pytest], which spec-trace does not read", "pyproject.toml")
    options = pytest.get("ini_options")
    return options if isinstance(options, dict) else None


def pytest_globs(testpaths, files):
    files = files or PYTEST_DEFAULT_FILES
    dirs = [os.path.normpath(p).replace(os.sep, "/").strip("/") for p in testpaths] or ["."]
    dirs = ["" if d == "." else d for d in dirs]
    return [f"{d}/**/{f}" if d else f"**/{f}" for d in dirs for f in files]


def anywhere(root, name):
    """Whether a file of this name is in the repository, at any depth."""
    return any(f == name or f.endswith("/" + name) for f in list_files(root))


def detect_go(root):
    if anywhere(root, "go.mod"):
        return "go.mod", "go.mod (Go's *_test.go)", ["**/*_test.go"], []
    return None


def detect_rust(root):
    if anywhere(root, "Cargo.toml"):
        # Unit tests live in #[cfg(test)] modules inside src/, so every source file may hold one.
        return "Cargo.toml", "Cargo.toml (Rust's tests/ and src/)", ["**/tests/**/*.rs", "**/src/**/*.rs"], []
    return None


DETECTORS = (detect_vitest, detect_jest, detect_pytest, detect_go, detect_rust)
# A runner configuration below the root applies to its own directory. spec-trace does not read
# such a configuration, so the root's globs may miss the tests it names.
NESTED_CONFIG = re.compile(r"(?:^|/)(?:(?:vitest|vite|jest)\.config\.[a-z]+|vitest\.workspace\.[a-z]+"
                           r"|pytest\.ini|\.pytest\.ini|pytest\.toml|\.pytest\.toml)$")


class Detected:
    def __init__(self, sources, groups, troubles):
        # groups: one (includes, excludes) per runner; a runner's excludes apply to its own files only
        self.sources, self.groups, self.troubles = sources, groups, troubles


def detect_tests(root):
    """The test file globs the repository's runners name, where they came from, and any trouble.

    A runner whose configuration cannot be read with confidence contributes nothing and adds
    a trouble line; the others still count. With no runner read, the defaults apply.
    """
    sources, groups, failed = [], [], []
    for detect in DETECTORS:
        runner = detect.__name__.replace("detect_", "")
        try:
            found = detect(root)
        except Unreadable as e:
            failed.append((e.args[1] if len(e.args) > 1 else f"the {runner} configuration", e.args[0]))
            continue
        except Exception as e:  # noqa: BLE001 - a config spec-trace trips on is trouble, never a crash
            failed.append((f"the {runner} configuration", f"its settings ({type(e).__name__}: {e})"))
            continue
        if found:
            _, source, inc, exc = found
            sources.append(source)
            groups.append((inc, exc))
    for name in list_files(root):
        if "/" in name and NESTED_CONFIG.search(name):
            failed.append((name, "it, since spec-trace reads runner configurations only at the root"))
    if not sources:
        why = "" if failed else ", since no test runner configuration was found"
        sources, groups = [f"the defaults{why}"], [(DEFAULT_TESTS, [])]
    used = " ".join(g if isinstance(g, str) else g.pattern for inc, _ in groups for g in inc)
    troubles = [f"{name}: could not read {what}. Using instead: {used}. To set the test globs by hand, "
                f"list them in {TESTS_FILE}, one per line, or pass --tests."
                for name, what in failed]
    return Detected(sources, groups, troubles)


def detected_files(root, found):
    """Files that any runner's globs include and that runner does not exclude."""
    files = set()
    for includes, excludes in found.groups:
        files.update(test_files(root, includes, excludes))
    return sorted(files)


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


def scan_tags(root, files, scenarios, pending=()):
    index, waiting = name_index(scenarios), name_index(pending)
    repeated, repeated_waiting = repeats(scenarios), repeats(pending)
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


def tag_problem(t, scenarios):
    if t.problem == "ambiguous":
        lines = "\n".join(f"      @scenario {key}" for key in t.choices)
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


PRUNE_HINT = "Run `baseline --prune` to remove this line, and commit the result with the change."


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


def uncertain(troubles, command):
    """Print why `command` refuses while the test files are uncertain; True if it must."""
    if not troubles:
        return False
    for t in troubles:
        print(t)
    print(f"spec-trace: not writing the baseline while the test files are uncertain. Set the "
          f"test globs in {TESTS_FILE} or pass --tests, then run {command} again.")
    return True


def tagged_scenarios(root, files):
    """The main specs' scenarios and which of them tests tag. None, after printing
    load_scenarios' problems, when two scenarios share a name under one requirement:
    no tag or baseline line can tell those apart."""
    scenarios, problems = load_scenarios(root)
    if problems:
        for p in problems:
            print(p)
        return None
    return scenarios, coverage(scenarios, scan_tags(root, files, scenarios, pending_scenarios(root)))


def write_baseline(root, files, baseline_path, troubles=()):
    rel = os.path.relpath(baseline_path, root)
    if os.path.lexists(baseline_path):
        # A rewrite would add every scenario untagged today, exempting new ones that have no test.
        print(f"spec-trace: {rel} already exists, so baseline wrote nothing. Run `baseline --prune` "
              "to drop its lines that are now tagged or name no scenario, or delete the file first "
              "to write it from scratch.")
        return 2
    # While detection reports trouble, the fallback globs may miss real tests, and a baseline
    # written from them would exempt the scenarios those tests tag.
    if uncertain(troubles, "baseline"):
        return 2
    found = tagged_scenarios(root, files)
    if found is None:
        return 1
    scenarios, covered = found
    untagged = sorted(s.key for s in scenarios if s.key not in covered)
    os.makedirs(os.path.dirname(baseline_path) or ".", exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as f:
        f.write("# Scenarios in openspec/specs that no test tagged when spec-trace was adopted.\n"
                "# spec-trace check fails on a line whose scenario a test now tags, or that names no\n"
                "# scenario: run `baseline --prune` to remove such lines. Never add one; a new scenario\n"
                "# gets a tagged test instead.\n")
        for key in untagged:
            f.write(key + "\n")
    print(f"spec-trace: wrote {len(untagged)} untagged scenario(s) of {len(scenarios)} to {rel}.")
    return 0


def prune_baseline(root, files, baseline_path, troubles=()):
    """Remove the baseline lines `check` fails on, keeping every other line as written. Never adds one."""
    rel = os.path.relpath(baseline_path, root)
    if not os.path.isfile(baseline_path):
        print(f"spec-trace: there is no baseline file at {rel}, so there is nothing to prune.")
        return 2
    # While detection reports trouble, the fallback globs may count a file that is not a test,
    # and a tag in it would remove the line of a scenario that no test checks.
    if uncertain(troubles, "baseline --prune"):
        return 2
    found = tagged_scenarios(root, files)
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
    print(f"spec-trace: pruned {len(removed)} line(s) from {rel}; {remain} scenario line(s) remain. "
          "Commit it with the change.")
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

    ADOPTED: the baseline file, the hand-set globs file (TESTS_FILE), or a
    GitHub workflow in root/.github/workflows that runs spec_trace.py. The
    baseline alone is not enough: `check` passes without one, so a repository
    whose every scenario is tagged may delete it, and --baseline moves it.
    Adoption wins over a decision file left behind.
    DECLINED: DECISION_FILE says DECLINED_TEXT. UNKNOWN: DECISION_FILE exists
    but says anything else, is longer than DECISION_FILE_LIMIT, is not a
    regular file, or cannot be read; neither the hook nor `decline` acts on it.
    """
    if not os.path.isdir(os.path.join(root, "openspec")):
        return None
    if (os.path.isfile(os.path.join(root, baseline))
            or os.path.isfile(os.path.join(root, TESTS_FILE))
            or runs_checker_in_ci(root)):
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
              f"{TESTS_FILE}, or a workflow that runs spec_trace.py), so nothing was declined. "
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
    parser.add_argument("--tests", action="append", metavar="GLOB",
                        help="test file glob, relative to the root; repeat for several. Without it, "
                             "the globs come from the test runner's configuration (Vitest, Jest, "
                             "pytest, Go, Rust), else these defaults: " + " ".join(DEFAULT_TESTS))
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
    troubles = []
    if args.tests:
        source, manual = "--tests", args.tests
    elif os.path.isfile(os.path.join(root, TESTS_FILE)):
        source, manual = TESTS_FILE, read_tests_file(os.path.join(root, TESTS_FILE))
    else:
        source, manual = None, None
    if manual is not None:
        print(f"spec-trace: test files from {source}", file=sys.stderr)
        includes = [g for g in manual if not g.startswith("!")]
        excludes = [g[1:] for g in manual if g.startswith("!")]
        try:
            files = test_files(root, includes, excludes)
            # A glob that matches nothing finds none of the tags it was meant to, so
            # `baseline` would exempt those scenarios.
            unmatched = [g for g in includes if not test_files(root, [g])]
        except (ValueError, re.error) as e:
            print(f"spec-trace: bad glob in {source}: {e}")
            return 2
        if not includes or unmatched:
            print(f"spec-trace: no test files match {' '.join(unmatched) or '(no globs)'} "
                  f"from {source} under {root}.")
            return 2
    else:
        found = detect_tests(root)
        troubles = found.troubles
        files = detected_files(root, found)
        # On stderr, so `report` stays pasteable.
        print(f"spec-trace: test files from {'; '.join(found.sources)}", file=sys.stderr)
        for t in troubles:
            print(f"spec-trace: warning: {t}", file=sys.stderr)
        if not files:
            print(f"spec-trace: warning: no test files found; list the test globs in {TESTS_FILE} "
                  "or pass --tests.", file=sys.stderr)
    if args.command == "check":
        return check(root, files, baseline)
    if args.command == "baseline" and args.prune:
        return prune_baseline(root, files, baseline, troubles)
    if args.command == "baseline":
        return write_baseline(root, files, baseline, troubles)
    return report(root, files, args.include_changes)


if __name__ == "__main__":
    sys.exit(main())
