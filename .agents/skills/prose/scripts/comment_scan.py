#!/usr/bin/env python3
"""Finds the comments in source files, for `prose check`.

Two jobs: lexing (where a comment starts and ends, and which slashes and
hashes are inside a string), and matching the history-language patterns that
`prose check` prints as warnings on the comments a change touches. Each rule
below comes from a real miss, and a test pins it. Standard library only.
"""

import ast
import io
import pathlib
import re
import subprocess
import sys
import tokenize

# Extensions where `//` starts a line comment, `/* */` delimits a block, and
# `"` / `'` / `` ` `` are the string delimiters. One hand-written lexer covers
# all of them because the three things this scanner has to get right - where a
# comment starts, where it ends, and which slashes are inside a string - are
# spelled the same way in every one.
FAMILY_C = {
    ".c", ".cc", ".cjs", ".cpp", ".cs", ".dart", ".go", ".h", ".hpp", ".java",
    ".js", ".jsx", ".kt", ".kts", ".less", ".m", ".mjs", ".mm", ".php", ".rs",
    ".scala", ".scss", ".swift", ".ts", ".tsx",
}

# JavaScript and TypeScript, where `/.../` can be a regex literal holding a
# `//` that starts no comment.
REGEX_LITERALS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}

# Extensions where a `"""` or `'''` fence opens one multi-line string: Kotlin,
# Scala, Swift and Dart raw strings, Java text blocks, C# raw string literals.
# Everywhere else `"""` is an empty string next to a quote, and reading it as a
# fence would swallow real code - so this is keyed on the extension rather than
# guessed. A fence left out of this set has its body lexed as code, which turns
# a `//` in an embedded URL or snippet into a comment that is not there.
TRIPLE_QUOTED = {".cs", ".dart", ".java", ".kt", ".kts", ".scala", ".swift"}

# The subset whose fence honours a backslash, so a `\"""` inside the string is
# content rather than the close: Java text blocks, Swift multi-line strings,
# Dart's ordinary `'''` (its `r'''` is checked at the call site). Kotlin and
# Scala raw strings and C# raw literals have no escapes - a `\` right before
# the close is the string's last character - and honouring one there would run
# the string to the end of the file and lose every comment below it.
TRIPLE_ESCAPES = {".dart", ".java", ".swift"}

# Extensions where `@"` opens a verbatim string: multi-line, no backslash
# escapes, `""` for one quote. Objective-C's `@"..."` is an ordinary escaped
# string, which is why this is not every language that spells a string with
# an `@` in front.
VERBATIM_AT = {".cs"}

# Extensions where a lone `'` is usually a lifetime tick (`&'a str`), not a
# quote. Reading it as a quote opens a string that runs to the end of the line
# and eats any trailing `//` comment with it. In JS a `'` is a real string
# quote, which is why this is per-extension too.
LIFETIME_TICK = {".rs"}

# Extensions where `r"..."` and `r#"..."#` open a raw string: no escapes,
# closed by a `"` plus as many `#` as opened it, free to span lines. Read as
# an ordinary string, a `\` before its close takes a trailing comment with it
# and its second line is lexed as code, where a `//` is a comment that is not
# there. A `"` right after an `r` is this string unless the `r` ends an
# identifier - the same one-character lookback Dart's `r'''` uses.
RAW_HASHED = {".rs"}

# Extensions where `r'...'` and `r"..."` open a single-line raw string: no
# escapes, closed by the first matching quote, never spanning a line. Read
# with escapes, `r'\'` runs to the end of the line and takes a trailing
# comment with it. The same `r` lookback as `RAW_HASHED` applies, with no
# `#` allowed: Dart has no hashed fence, and `bar'x'` is an ordinary string.
RAW_LINE = {".dart"}

# Python gets its own path: `tokenize` and `ast` ship with the interpreter and
# know the language exactly, which beats a hand lexer on f-strings, raw strings
# and the three-quote forms.
FAMILY_PYTHON = {".py", ".pyi"}

# Languages where `#` starts a comment but no lexer here knows their strings.
# Only a line that is nothing but a comment is read, because a `#` after code
# may be inside a string, `$#` or `${#x}`. A heredoc line starting with `#` is
# read as a comment too; that mistake only ever adds to what is listed.
FAMILY_HASH = {
    ".bash", ".pl", ".ps1", ".r", ".rb", ".sh", ".toml", ".yaml", ".yml", ".zsh",
}
HASH_NAMES = {"Dockerfile", "Makefile"}

SCANNED = FAMILY_C | FAMILY_PYTHON | FAMILY_HASH

# A byte-order mark is encoding metadata, not source. `ast` refuses a file that
# still carries one even though the interpreter runs it happily, so it comes off
# before anything parses.
BOM = chr(0xFEFF)

# Directories holding code nobody here wrote, or a build's copy of code that is
# already scanned at its source. Comment discipline is for authored code, and a
# comment in a vendored bundle or a CDK asset copy is not prose anyone wrote here.
SKIP_DIRS = {
    ".git", ".next", ".nuxt", ".output", ".svelte-kit", ".terraform", ".tox",
    ".venv", "Pods", "__generated__", "__pycache__", "build", "cdk.out",
    "coverage", "dist", "generated", "node_modules", "out", "site-packages",
    "target", "vendor", "venv",
}


# ---------------------------------------------------------------------------
# History language
# ---------------------------------------------------------------------------
#
# Each entry is (name, pattern, what the phrase does, veto). `veto` is matched
# against the text to the left of the hit and suppresses it; that is how the
# adjectival `a previously issued token` is told from the narrating `it
# previously issued a token` without a variable-width lookbehind. (Backticks
# there are load-bearing, and this file is the scanner's own smallest test: an
# example phrase has to be masked, or the note fires on the code that defines
# it.)
#
# The bar for adding a pattern: measured, and specific enough that a reader
# still trusts the note. `used to`, `previous`, `legacy` and `replaced` are all
# in here only in a narrowed form, because bare they fired 850, 385, 458 and 228
# times over a corpus of ~3000 real source files, mostly on code that
# has no history problem at all.

DETERMINER = re.compile(
    r"(?:\b(?:a|an|the|any|all|some|its|their|our|his|her|every|each|no|more|"
    r"most|few|both|one|two|three|four|five|several)|'s|’s)[\s-]+$",
    re.IGNORECASE,
)

HISTORY_PATTERNS = [
    (
        "used-to",
        # A subject in front of it, or the `used to be` form. Bare `used to` is
        # dominated by the reduced passive - "the key used to build the cache" -
        # which is purpose, not history, and no veto separates the two.
        re.compile(
            r"\b(?:it|this|that|these|those|we|they|there|which|who|doc|docs|"
            r"docstring|javadoc|jsdoc|comment|paragraph|note|code|method|"
            r"function|field|flag|helper|test|version|name)\s+used to\b"
            r"|\bused to be\b",
            re.IGNORECASE,
        ),
        "narrates what the code did before",
        None,
    ),
    (
        "no-longer",
        re.compile(r"\bno longer\b", re.IGNORECASE),
        "may be describing the code by what it stopped doing",
        None,
    ),
    (
        "previously",
        re.compile(r"\bpreviously\b", re.IGNORECASE),
        "narrates a past state of the code",
        DETERMINER,
    ),
    (
        "formerly",
        re.compile(r"\b(?:formerly|hitherto)\b", re.IGNORECASE),
        "names a past state of the code",
        None,
    ),
    (
        "earlier-version",
        re.compile(
            r"\b(?:earlier|older|previous|original|first|initial)\s+"
            r"(?:version|revision|iteration|draft|cut)\s+of\s+(?:this|the|it)\b",
            re.IGNORECASE,
        ),
        "reviews a draft of the code or of the comment itself",
        None,
    ),
    (
        "old-thing",
        # The noun list is the whole guard: `the old value`, `the old price` and
        # `the previous row` are ordinary talk about data this code handles now,
        # and only the code's own past is in scope.
        re.compile(
            r"\b(?:old|previous|original|former|legacy)\s+"
            r"(?:approach|implementation|impl|version|behaviou?r|design|logic|"
            r"code|way|scheme|mechanism|system|pattern|method|comment|"
            r"docstring|javadoc|name)\b",
            re.IGNORECASE,
        ),
        "compares the code to an earlier version of itself",
        None,
    ),
    (
        "replaced",
        re.compile(
            r"\b(?:this|which|it|that)\s+(?:replaced|replaces|superseded|supersedes)\b"
            r"|\breplaces?\s+the\s+(?:old|previous|earlier|original|former)\b"
            r"|\b(?:renamed from|moved from|split out of|superseded by)\b",
            re.IGNORECASE,
        ),
        "defines the code by what it displaced",
        None,
    ),
    (
        "we-changed",
        re.compile(
            r"\b(?:we|i|this|it|that)\s+(?:have\s+|has\s+|had\s+)?"
            r"(?:changed|switched|migrated|rewrote|rewritten|refactored|"
            r"renamed|dropped)\b",
            re.IGNORECASE,
        ),
        "recounts a change instead of describing the result",
        None,
    ),
    (
        "before-this",
        re.compile(
            r"\b(?:before this (?:change|commit|pr|fix|refactor|version)"
            r"|prior to this"
            r"|as of the .{0,20}(?:refactor|rewrite|migration)"
            r"|since the .{0,20}(?:refactor|rewrite|migration)"
            r"|back when|at one point|at some point we|historically)\b",
            re.IGNORECASE,
        ),
        "dates the code against an event a future reader cannot see",
        None,
    ),
    (
        "originally",
        re.compile(r"\boriginally\b", re.IGNORECASE),
        "narrates the code's first form",
        None,
    ),
    (
        "instead-of-old",
        re.compile(r"\binstead of (?:the )?(?:old|previous|former|earlier)\b", re.IGNORECASE),
        "contrasts the code with a version that no longer exists",
        None,
    ),
]


def scannable(path):
    """Whether comments in this file can be found at all."""
    pure = pathlib.PurePosixPath(path.rstrip())
    return pure.suffix.lower() in SCANNED or pure.name in HASH_NAMES


class Comment:
    """One comment: where it is, how it was written, and its prose.

    `is_module` is carried from the extractor rather than inferred downstream.
    A line number cannot stand in for it: a module docstring sits on line 4 of
    any file with a shebang and an encoding line, and line 2 of a file whose
    first line is `def f():` belongs to a function.
    """

    def __init__(self, path, start, end, style, lines, own_line, is_module):
        self.path = path
        self.start = start
        self.end = end
        self.style = style
        self.lines = lines
        self.own_line = own_line
        self.is_module = is_module


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _skip_quoted(source, index, line, quote, escapes=True):
    """Step past a `'...'` or `"..."` literal, returning (index, line).

    An unterminated literal stops at the newline rather than eating the rest of
    the file: every language here treats a raw newline inside one as an error,
    and swallowing the remainder would hide every comment below it. Without
    `escapes` a backslash is an ordinary character, which is a raw string's
    only difference from a plain one - the newline bound still holds.
    """
    index += 1
    while index < len(source):
        char = source[index]
        if escapes and char == "\\":
            if source[index + 1:index + 2] == "\n":
                line += 1
            index += 2
            continue
        if char == "\n":
            return index, line
        index += 1
        if char == quote:
            return index, line
    return index, line


def _is_char_literal(source, index):
    """Whether the `'` at `index` opens a char literal rather than a lifetime.

    Rust spells both with one tick. A char literal is either escaped (`'\\n'`)
    or exactly one character wide (`'x'`); a lifetime (`&'a str`, `'static`) is
    neither, and has no closing tick at all. Both tests slice rather than index,
    so a tick as the last character of the file is a plain `False`.
    """
    return source[index + 1:index + 2] == "\\" or source[index + 2:index + 3] == "'"


def _raw_hashes(source, index):
    """How many `#` open the raw string whose quote is at `index`, or None.

    Walks back over the `#`s to the `r`, past an optional `b` or `c`, and asks
    whether the character before that could continue an identifier: in
    `bar"x"` the `r` ends a name and the string is an ordinary one. Every look
    is guarded on the position rather than sliced negative, because
    `source[-1:0]` is empty but `source[-2:-1]` is the file's last character.
    """
    at = index - 1
    while at >= 0 and source[at] == "#":
        at -= 1
    if at < 0 or source[at] != "r":
        return None
    hashes = index - 1 - at
    at -= 1
    if at >= 0 and source[at] in "bc":
        at -= 1
    if at >= 0 and (source[at].isalnum() or source[at] == "_"):
        return None
    return hashes


def _skip_raw(source, index, line, line_start, hashes):
    """Step past a Rust raw string, returning (index, line, line_start).

    The close is a `"` followed by exactly as many `#` as opened the string,
    so a `"` inside an `r#"..."#` is content. An unterminated one eats the
    remainder, the bargain `_skip_triple` strikes: it loses comments rather
    than inventing them, and a raw string with no close does not compile.
    """
    close = source.find('"' + "#" * hashes, index + 1)
    end = len(source) if close == -1 else close + 1 + hashes
    body = source[index:end]
    if "\n" in body:
        line += body.count("\n")
        line_start = index + body.rfind("\n") + 1
    return end, line, line_start


def _skip_triple(source, index, line, line_start, escapes):
    """Step past a triple-quoted string, returning (index, line, line_start).

    With `escapes`, a backslash takes the next character with it, so a fence
    with a backslash in front is content and the string closes at the next
    bare fence. An unterminated
    fence eats the remainder, the same bargain the unterminated block comment
    strikes: it loses comments rather than inventing them, and a fence with no
    close is a syntax error in every language that has one.
    """
    fence = source[index:index + 3]
    total = len(source)
    close = index + 3
    while close < total and source[close:close + 3] != fence:
        close += 2 if escapes and source[close] == "\\" else 1
    end = total if close >= total else close + 3
    body = source[index:end]
    if "\n" in body:
        line += body.count("\n")
        line_start = index + body.rfind("\n") + 1
    return end, line, line_start


def _skip_verbatim(source, index, line, line_start):
    """Step past a C# `@"..."` verbatim string, returning (index, line, line_start).

    `_skip_quoted` reads one wrong on every count: it stops at the first
    newline where a verbatim string may span lines, it treats a backslash as
    an escape where it is a plain character, and it never sees a doubled quote
    as one quote - so the verbatim string holding a single quote (an at-sign
    and then four quotes) would instead be read as a triple-quote fence with
    no close, taking every comment below it.
    """
    index = source.index('"', index) + 1
    total = len(source)
    while index < total:
        char = source[index]
        if char == '"':
            if source[index + 1:index + 2] == '"':
                index += 2
                continue
            return index + 1, line, line_start
        if char == "\n":
            line += 1
            line_start = index + 1
        index += 1
    return index, line, line_start


def extract_c_family(source, suffix=""):
    """Comment tuples for a C-family source string.

    Regex cannot do this job: `"http://example.com"` and `url.split('//')` both
    carry a `//` that starts no comment, and telling those from a real comment
    needs the string state a scan keeps and a pattern does not.

    Template literals are followed through `${...}` interpolation with a brace
    stack, so a `//` inside an interpolation reads as the comment it is and a
    `}` inside a nested object literal does not end the interpolation early.

    `suffix` selects the quote rules that differ between these languages
    instead of being shared by all of them: a triple-quote fence
    (`TRIPLE_QUOTED`, escaped or not per `TRIPLE_ESCAPES`), an `@"` verbatim
    string (`VERBATIM_AT`), a tick that is a lifetime rather than a quote
    (`LIFETIME_TICK`), an `r#"..."#` raw string (`RAW_HASHED`) and a
    single-line `r'...'` raw string (`RAW_LINE`). Applying any of them
    everywhere would break the languages that do not have it, so the caller
    passes the extension and the lexer looks it up.
    """
    found = []
    index, total, line, mode = 0, len(source), 1, "code"
    interpolation = []
    line_start = 0
    triple = suffix in TRIPLE_QUOTED
    escapes = suffix in TRIPLE_ESCAPES
    verbatim = suffix in VERBATIM_AT
    tick = suffix in LIFETIME_TICK
    raw_hashed = suffix in RAW_HASHED
    raw_line = suffix in RAW_LINE
    regex = suffix in REGEX_LITERALS
    while index < total:
        char = source[index]
        if mode == "template":
            if char == "\\":
                if source[index + 1:index + 2] == "\n":
                    line += 1
                    line_start = index + 2
                index += 2
                continue
            if char == "\n":
                line += 1
                index += 1
                line_start = index
                continue
            if char == "`":
                mode = "code"
            elif char == "$" and source[index + 1:index + 2] == "{":
                interpolation.append(0)
                mode = "code"
                index += 2
                continue
            index += 1
            continue
        if char == "\n":
            line += 1
            index += 1
            line_start = index
            continue
        opens_verbatim = source[index + 1:index + 2] == '"' or source[index + 1:index + 3] == '$"'
        if verbatim and char == "@" and opens_verbatim:
            index, line, line_start = _skip_verbatim(source, index, line, line_start)
            continue
        if triple and source[index:index + 3] in ('"""', "'''"):
            # Dart's `r'''` is the raw form of its escaped `'''`, told apart
            # only by the letter in front.
            raw = suffix == ".dart" and source[index - 1:index] == "r"
            index, line, line_start = _skip_triple(
                source, index, line, line_start, escapes and not raw
            )
            continue
        if char in "\"'":
            if char == "'" and tick and not _is_char_literal(source, index):
                index += 1
                continue
            hashes = _raw_hashes(source, index) if raw_hashed and char == '"' else None
            if hashes is not None:
                index, line, line_start = _skip_raw(source, index, line, line_start, hashes)
                continue
            raw = raw_line and _raw_hashes(source, index) == 0
            index, line = _skip_quoted(source, index, line, char, escapes=not raw)
            continue
        if char == "`":
            mode = "template"
            index += 1
            continue
        if char == "{" and interpolation:
            interpolation[-1] += 1
            index += 1
            continue
        if char == "}" and interpolation:
            if interpolation[-1] == 0:
                interpolation.pop()
                mode = "template"
            else:
                interpolation[-1] -= 1
            index += 1
            continue
        if char == "/" and source[index + 1:index + 2] == "/":
            end = source.find("\n", index)
            end = total if end == -1 else end
            own = not source[line_start:index].strip()
            found.append((line, line, "line", [source[index:end]], own, False))
            index = end
            continue
        if char == "/" and source[index + 1:index + 2] == "*":
            close = source.find("*/", index + 2)
            end = total if close == -1 else close + 2
            block = source[index:end]
            own = not source[line_start:index].strip()
            found.append(
                (line, line + block.count("\n"), "block", block.split("\n"), own, False)
            )
            if block.count("\n"):
                line += block.count("\n")
                line_start = index + block.rfind("\n") + 1
            index = end
            continue
        if char == "/" and regex:
            close = _regex_close(source, line_start, index)
            if close is not None:
                index = close + 1
                continue
        index += 1
    return found


# Where a `/` opens a regular expression rather than dividing: after one of
# these, `=>`, or one of the keywords. Kept small, because a regex opened by
# mistake can swallow a real `//` comment later on the line.
REGEX_AFTER = set("(,=:[!&|?{;")
REGEX_KEYWORD = re.compile(r"(?<![\w$.])(?:return|typeof|case|throw|yield|await)$")


def _regex_close(source, line_start, index):
    """The index of the `/` closing a regex literal opened at index, or None
    when the `/` does not open one or nothing closes it on the same line."""
    before = source[line_start:index].rstrip()
    if not before or not (before[-1] in REGEX_AFTER or before.endswith("=>")
                          or REGEX_KEYWORD.search(before)):
        return None
    # `count! / 2`: a `!` right after an operand is TypeScript's non-null
    # assertion, and the `/` divides.
    if before[-1] == "!" and len(before) > 1 and (before[-2].isalnum() or before[-2] in "_$)]>\"'`"):
        return None
    in_class = False
    at = index + 1
    while at < len(source) and source[at] != "\n":
        char = source[at]
        if char == "\\":
            at += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            return at
        at += 1
    return None


def extract_python(source):
    """Comments and docstrings from Python, using the interpreter's own lexer.

    `tokenize` is what makes an f-string's `#` or a triple quote inside a raw
    string a non-event, and `ast` is the only honest way to say which string
    literal is a docstring rather than a bare expression. Either can raise on a
    file that does not parse; `comments_touching` turns that into None, because
    returning no comments would read as a file without any.

    A line here is what Python calls a line: text between `\\n`. `str.split`
    and an `io.StringIO` reader agree on that, where `str.splitlines` also
    breaks on a form feed, `\\x1c` and `\\u2028` - characters the language treats
    as ordinary. Splitting on those invents lines the tokenizer cannot see, so
    every number below the first one is off and a string literal carrying one
    reads as unterminated.
    """
    found = []
    lines = source.split("\n")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            own = not lines[row - 1][:column].strip()
            found.append((row, row, "line", [token.string], own, False))
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if not isinstance(first.value.value, str):
            continue
        found.append(
            (first.lineno, first.end_lineno, "docstring",
             _string_only(lines[first.lineno - 1:first.end_lineno], first.value),
             True, isinstance(node, ast.Module))
        )
    return found


def _string_only(lines, node):
    """A docstring's lines without code sharing its first or last line, as
    in `class E(Exception): \"\"\"Doc.\"\"\"`. Code before it becomes blanks,
    so columns hold. ast's columns count UTF-8 bytes."""
    lines = list(lines)
    lines[-1] = lines[-1].encode()[:node.end_col_offset].decode(errors="replace")
    head = lines[0].encode()
    before = head[:node.col_offset].decode(errors="replace")
    if before.strip():
        lines[0] = " " * len(before) + head[node.col_offset:].decode(errors="replace")
    return lines


def extract_hash_own_line(source):
    """Own-line `#` comments, for languages without a lexer here.

    A `#!` on the first line is an interpreter line, not a comment.
    """
    found = []
    for number, text in enumerate(source.split("\n"), start=1):
        stripped = text.lstrip()
        if not stripped.startswith("#"):
            continue
        if number == 1 and stripped.startswith("#!"):
            continue
        found.append((number, number, "line", [text], True, False))
    return found


def comments_in(path, source):
    """Every comment in one file, with consecutive line comments merged.

    A run of `//` or `#` lines with nothing else on them is one comment to the
    person reading it, so it is one block here too.

    The byte-order mark comes off here, and line endings are reduced to `\\n`
    here, because this is the one place every read passes through - a file off
    disk, a blob out of `git show`, a string handed straight in - so a new
    source of text cannot arrive without both being handled.

    The reduction is universal newlines, the translation `open()` applies when
    the interpreter itself reads a file: `\\r\\n` and a bare `\\r` are line ends,
    a form feed is not. Every extractor below then counts `\\n` and nothing
    else, which is the same line model the languages use. `str.splitlines` is
    the wrong tool for this one - it also breaks on `\\x0c`, `\\x1c` and
    `\\u2028`, which invents lines the tokenizer cannot see and puts every
    number below the first one off.
    """
    suffix = pathlib.PurePosixPath(path.rstrip()).suffix.lower()
    if source.startswith(BOM):
        source = source[1:]
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    if suffix in FAMILY_PYTHON:
        raw = extract_python(source)
    elif suffix in FAMILY_C:
        raw = extract_c_family(source, suffix)
    elif suffix in FAMILY_HASH or pathlib.PurePosixPath(path.rstrip()).name in HASH_NAMES:
        raw = extract_hash_own_line(source)
    else:
        return []
    raw.sort(key=lambda item: (item[0], item[1]))
    merged = []
    for start, end, style, lines, own, module in raw:
        previous = merged[-1] if merged else None
        joinable = (
            previous is not None
            and style == "line"
            and previous.style == "line"
            and own
            and previous.own_line
            and start == previous.end + 1
        )
        if joinable:
            previous.end = end
            previous.lines.extend(lines)
            continue
        merged.append(Comment(path, start, end, style, list(lines), own, module))
    return merged


# ast.parse raises the last two on a file too deeply nested to parse.
PARSE_ERRORS = (SyntaxError, tokenize.TokenError, IndentationError, ValueError,
                RecursionError, MemoryError)


def comments_touching(path, source, changed):
    """The comments a diff added to or edited, or None if the file did not parse.

    `changed` is the set of post-image line numbers the diff added. A comment
    counts when any of its lines is in it. None, rather than an empty list, so
    a caller cannot mistake an unreadable file for one without comments.
    """
    try:
        comments = comments_in(path, source)
    except PARSE_ERRORS:
        return None
    return [
        comment for comment in comments
        if set(range(comment.start, comment.end + 1)) & changed
    ]

# ---------------------------------------------------------------------------
# Prose
# ---------------------------------------------------------------------------

# One marker set per style, never the union of all three. The same characters
# mean different things depending on what opened the comment: `*` leads a
# block comment's continuation line and also a reStructuredText bullet, `#`
# opens a Python comment and also a markdown heading. Stripping the union
# would reduce a docstring's `* item` and `# Heading` to bare prose.
MARKERS = {
    "line": re.compile(r"^(\s*)(//+|#+)\s?"),
    "block": re.compile(r"^(\s*)(/\*+|\*+/|\*)\s?"),
}
TRAILING = re.compile(r"\s*\*/\s*$")
OPEN_QUOTE = re.compile(r"^(\s*)[rRbBuUfF]{0,2}(\"\"\"|''')")
CLOSE_QUOTE = re.compile(r"(\"\"\"|''')\s*$")


def strip_markers(comment):
    """The comment's prose, with the syntax that made it a comment removed."""
    marker = MARKERS.get(comment.style)
    out = []
    for raw in comment.lines:
        line = raw if marker is None else marker.sub(r"\1", raw)
        if comment.style == "block":
            line = TRAILING.sub("", line)
        elif comment.style == "docstring":
            line = CLOSE_QUOTE.sub("", OPEN_QUOTE.sub(r"\1", line))
        out.append(line)
    return out


FENCE = re.compile(r"^\s*(```|~~~)")
DOCTEST = re.compile(r"^\s*(>>>|\.\.\.)\s")
# The sigil is required: a tag is `@example` or `{@code`, never bare prose.
# With the sigil optional, the pattern would also match a sentence opening with
# the word "Code" or an `Example:` label, and would blank everything down to
# the next blank line, hiding any history phrase in it.
EXAMPLE_TAG = re.compile(r"^\s*(?:\{@|@)(?:example|code|snippet)\b", re.IGNORECASE)
ANOTHER_TAG = re.compile(r"^\s*[@{]?@\w+")
# A code span may wrap - a backticked phrase in a docstring routinely does - so
# this is matched over the whole block rather than line by line, and must not
# cross a blank line, which is a different paragraph.
CODE_SPAN = re.compile(r"`[^`\n]*(?:\n[^\S\n]*[^`\n]*)?`")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)


def blank_out(match):
    """The match, with every character but a newline turned into a space."""
    return "".join(" " if char != "\n" else "\n" for char in match.group(0))


def mask_examples(lines):
    """Blank the parts of a comment that are code rather than prose.

    A history flag must not fire on a docstring's own worked example, a
    backticked identifier, or a URL with a version in its path. Lines are kept
    as blanks rather than dropped, so every reported line number still lines up
    with the file.
    """
    masked = []
    fence = None
    in_example = False
    for line in lines:
        opening = FENCE.match(line)
        if fence is not None:
            masked.append("")
            if opening and opening.group(1) == fence:
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            masked.append("")
            continue
        if EXAMPLE_TAG.match(line):
            in_example = True
            masked.append("")
            continue
        if in_example:
            if line.strip() and not ANOTHER_TAG.match(line):
                masked.append("")
                continue
            in_example = False
        if DOCTEST.match(line):
            masked.append("")
            continue
        masked.append(URL.sub(" ", line))
    return CODE_SPAN.sub(blank_out, "\n".join(masked)).split("\n")


# ---------------------------------------------------------------------------
# History flags
# ---------------------------------------------------------------------------

class Note:
    def __init__(self, path, line, kind, headline, detail, quote, where=""):
        self.path = path
        self.line = line
        self.kind = kind
        self.headline = headline
        self.detail = detail
        self.quote = quote
        self.where = where


HISTORY_DETAIL = (
    "A comment reads as if the code were written today. Ask what wrong belief the "
    "sentence was preventing: if there is one, restate it in the present tense as a "
    "warning about the code as it is; if the reasoning is worth keeping, move it to "
    "wherever this repo already records rejected designs and leave a one-line "
    "pointer; otherwise delete the sentence."
)

RUNTIME_CAVEAT = (
    "This phrase is also how code describes a runtime state transition - \"the order "
    "is no longer unpaid\" - which is present-tense fact and fine. Most hits on it "
    "are that, not history."
)

def history_notes(comment, prose):
    notes = []
    for index, line in enumerate(prose):
        for name, pattern, why, veto in HISTORY_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if veto is not None and veto.search(line[:match.start()]):
                continue
            detail = HISTORY_DETAIL
            if name == "no-longer":
                detail = f"{RUNTIME_CAVEAT} {HISTORY_DETAIL}"
            notes.append(
                Note(
                    comment.path,
                    comment.start + index,
                    f"history:{name}",
                    f'"{match.group(0).strip()}" {why}.',
                    detail,
                    line.strip(),
                )
            )
            break
    return notes


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def git(args, cwd=None):
    # `quotePath=false` keeps a non-ASCII path raw. Quoted, `+++
    # "b/r\303\251sum\303\251.py"` has a suffix of `.py"`, fails the extension
    # test, and the file leaves the run without a word on stderr. The setting
    # stops there: a `"`, a `\` or a control character in a name stays
    # C-quoted whatever the config says, and `unquote_path` in the header
    # parse is what handles those - this flag alone does not.
    #
    # Decoding matches `read_text` in the file modes: a stray latin-1 byte in
    # a comment is one replacement character, not a traceback out of the diff
    # or a file that vanishes from the staged run while the same file on disk
    # scans fine.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false"] + args,
        cwd=cwd, capture_output=True, check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(f"git {' '.join(args)} failed")
    # Decoded from bytes rather than read in text mode: text mode would turn a
    # bare CR into a newline and shift every later line number from git's count.
    return result.stdout.decode("utf-8", errors="replace")


# `added_lines` reads the default shape of a unified diff, and every one of
# these flags pins one thing a user's config can reshape: `diff.external`
# (difftastic and friends) replaces the text wholesale, `color.ui=always`
# threads escape codes through it, `diff.relative` names paths from the
# caller's directory when every reader here wants the tree top, and
# `diff.mnemonicPrefix` / `diff.noprefix` / `diff.srcPrefix` move the `b/`
# that the header parse strips. Each one, unpinned, empties the run or drops
# files from it with at most a stderr line to say so.
DIFF = [
    "diff", "--no-ext-diff", "--no-color", "--no-relative",
    "--src-prefix=a/", "--dst-prefix=b/", "--unified=0",
]


# The C-style quoting `git diff` wraps round a header path that holds a `"`,
# a `\` or a control character. `core.quotePath=false` does not reach these -
# it only stops the quoting of bytes above 0x7f - so a non-ASCII name arrives
# raw inside the quotes and the octal branch only ever meets a control
# character, which is why `chr` on the value is enough.
QUOTED_ESCAPE = re.compile(r'\\([abfnrtv"\\]|[0-7]{1,3})')
QUOTED_CHARS = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
    '"': '"', "\\": "\\",
}


def unquote_path(target):
    """A diff header path with git's C-style quoting undone.

    Only a target wrapped in `"` is quoted. An unwrapped one is returned as it
    is: git prints a plain name verbatim, and unescaping a backslash in one
    would point at a file that is not there.
    """
    if len(target) < 2 or target[0] != '"' or target[-1] != '"':
        return target
    return QUOTED_ESCAPE.sub(
        lambda match: QUOTED_CHARS.get(match.group(1)) or chr(int(match.group(1), 8)),
        target[1:-1],
    )


def header_path(rest):
    """The path in a `---` or `+++` header line, given the line minus its
    first four characters. git ends the line with a tab when the name holds a
    space; only that tab comes off, since a name may itself end in a space."""
    return unquote_path(rest[:-1] if rest.endswith("\t") else rest)


def added_lines(diff):
    """Map every file in a unified diff to the line numbers it added.

    The scanner lexes the whole post-image file and uses these numbers only to
    pick out the comments the diff touched. The diff text alone cannot say
    which lines are comments: a `+` line in the middle of a block comment
    gives no way to know it is inside one, and a string literal three lines
    above the hunk is what decides whether a `//` opens a comment at all.

    A `---` or `+++` line is a header only inside the block a `diff ` line
    opens, before its first `@@`. Every hunk line carries a one-character
    prefix, so an added line whose text begins `++ ` prints as `+++ ...`; read
    as a header it names a phantom file, every later `+` line in the hunk
    labels itself against that name, and the real file - if no `+` line came
    before - is never registered at all.

    A file is registered at its header, not at its first `+` line: with no
    context lines, a deletion-only file has no `+` line but is still touched,
    and its empty set of added lines says it added no comment.
    """
    per_file = {}
    path = None
    in_header = False
    new_line = 0
    # git breaks a diff on `\n` alone. `str.splitlines` also breaks on a form
    # feed and its other terminators, which numbers every added line after
    # one of them one too high; `comments_in` makes the same argument for
    # the source text.
    for line in diff.split("\n"):
        if line.startswith("diff "):
            in_header = True
            path = None
            continue
        if in_header and not line.startswith("@@"):
            if line.startswith("+++ "):
                target = header_path(line[4:])
                if target != "/dev/null":
                    path = re.sub(r"^b/", "", target)
                    per_file.setdefault(path, set())
            continue
        if line.startswith("@@"):
            in_header = False
            match = re.search(r"\+(\d+)", line)
            new_line = int(match.group(1)) if match else 0
            continue
        if path is None:
            continue
        if line.startswith("\\"):
            # `\ No newline at end of file` annotates the line above it and
            # belongs to neither image. Counted as a line of the post-image it
            # pushes every `+` line after it in the hunk one number too high,
            # and a comment the diff wrote then labels itself untouched.
            continue
        if line.startswith("+"):
            per_file.setdefault(path, set()).add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        else:
            per_file.setdefault(path, set())
            new_line += 1
    return per_file


def worktree_root(root):
    """The top of the working tree that `root` sits in.

    `git diff` names every path from the top of the tree whatever directory it
    was run in, so a reader that joins those paths onto the caller's directory
    finds nothing at all the moment the caller is one level down. `git show`
    resolves them itself and needs none of this.
    """
    return pathlib.Path(git(["rev-parse", "--show-toplevel"], root).strip())


def diff_read_side(revisions):
    """The revision holding the diff's post-image, or None for the worktree.

    `git diff A..B` and `git diff A...B` both compare against B, while a bare
    `git diff A` compares A against the files on disk. Reading the wrong side
    lexes the pre-image while holding post-image line numbers, which mislabels
    every comment it does not lose outright. A git ref cannot contain `..`, so
    splitting on the separator is exact rather than a guess.
    """
    for separator in ("...", ".."):
        if separator in revisions:
            return revisions.split(separator, 1)[1].strip() or "HEAD"
    return None


def read_from_tree(tree):
    """A reader for paths a diff named, resolved against the top of the tree."""
    return lambda path: (tree / path).read_text(encoding="utf-8", errors="replace")


def diff_targets(mode, revisions, root):
    """(path, source, changed-lines) for every scannable file a diff touched."""
    if mode == "staged":
        diff = git(DIFF + ["--cached"], root)
        read = lambda path: git(["show", f":{path}"], root)
    elif mode == "unstaged":
        diff = git(DIFF, root)
        read = read_from_tree(worktree_root(root))
    else:
        diff = git(DIFF + [revisions], root)
        end = diff_read_side(revisions)
        if end is None:
            read = read_from_tree(worktree_root(root))
        else:
            read = lambda path: git(["show", f"{end}:{path}"], root)
    for path, lines in sorted(added_lines(diff).items()):
        if not scannable(path):
            continue
        if SKIP_DIRS & set(pathlib.PurePosixPath(path).parts):
            continue
        try:
            yield path, read(path), lines
        except (OSError, SystemExit, UnicodeDecodeError):
            continue

