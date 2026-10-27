#!/usr/bin/env python3
"""prose: list the prose in a commit, mint its trailer, and sign posted text.

Signing takes two calls. The first, given the reader goals, prints the rules
and a pass token, signs nothing and exits 4. The second, with --pass <token>, signs.
Both calls of `check` run the repository's pre-commit hook first, if it has one.

    prose.py start --goals <goals> | --goals-file <file>
        Before writing. Prints the rules and opens the first-write gate (see
        hook-gate below); issues no token.
    prose.py check -F <message file, or - for stdin>
            --goals <goals> | --message-goals-file <file> [--amend]
            [--goals-for <pattern> <goals>]... [--goals-file <file>]
        Before a commit, first call. Lists the prose, each file under its own
        reader goals, and prints the rules and a token. --goals is the
        message's reader's. --message-goals-file gives them in a file instead:
        one or more goals per line, separated by ';', with no 'pattern:'
        prefix. Every changed doc or spec needs goals of its own, or check
        refuses it.
    prose.py check -F <message file, or - for stdin> --pass <token> [--amend]
            [--cold-read <report> [--dispositions <file>]]
        Second call. Prints the Prose: trailer. --amend: before `git commit --amend`.
        When it lists a changed comment or doc passage and no --cold-read is
        given, it prints a cold-read brief instead, signs nothing and exits 5.
        A report with findings needs --dispositions, answering each one.
    prose.py sign --goals <goals> | --goals-file <file>
        Before posting, first call. Prints the rules and a token; reads no stdin.
        start's and sign's goals file holds the goals --goals would, one or
        more per line, with no 'pattern:' prefix as check's goals file has,
        since neither command lists files.
    prose.py sign --pass <token> [--cold-read <report> [--dispositions <file>]] < text > signed
        Second call. Prints stdin's text with a signed footer, or, as check
        does, a cold-read brief on stderr, exiting 5.
    prose.py compact <file> [--verify] [--paths-from <file|-> [-0]] [-- <path>...]
    prose.py compact <file> --review
    prose.py compact <file> --reviewed <reply> [--dispositions <file>]
    prose.py compact <file> --abandon
        Compaction: prints the brief a compactor subagent works from and
        exits 4. --verify checks the compacted file against the copy
        `compact <file>` saved, exiting 0 when it passes and 1 when it fails.
        --review prints the brief for a reviewer of each removal and
        rewrite, and exits 4. --reviewed records the review as complete
        once its findings are answered; check refuses to sign a compaction
        without both the --verify and the --reviewed record. --abandon
        discards a compaction started on the file, so the commit gate
        treats it as ordinary again. `compact <file>` with no flag and every
        --verify take the files that might refer to the doc, after -- or
        listed in --paths-from.
    prose.py verify-staged <trailer line>     stdin: the message (the commit script's verifier)
    prose.py verify-commit <sha>              after a commit (the commit hook)
    prose.py verify-post                      stdin: posted text
    prose.py hook-post --host <platform>      the posting hook
    prose.py hook-gate                        the first-write gate

Standard library only. Read ../DECISIONS.md before changing what is hashed:
a change here invalidates every signature already minted.
"""

import argparse
import difflib
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import subprocess
import sys
import time
from typing import Callable, NamedTuple, Optional

HERE = pathlib.Path(__file__).resolve().parent
# The path this file was run by, with any link in it kept. The commands prose
# prints for its caller to run next name this, not HERE: a caller granted
# permission by path, or told where the skill is, needs the same path back,
# not the clone a link resolves to.
INVOKED = pathlib.Path(os.path.abspath(__file__)).parent / "prose.py"
# How text is decoded from bytes and encoded back for hashing.
TEXT_ERRORS = "surrogateescape"
RULES = HERE.parent / "rules.md"
# The shared commit-trailer library. This file calls its result block and
# its pre-commit runner; the library's commit script calls back into
# verify-staged.sh through its --verified-value option.
LIBRARY = HERE.parent.parent.parent / "lib" / "commit-trailer"
RESULT_BLOCK = LIBRARY / "result-block.sh"
RUN_PRE_COMMIT = LIBRARY / "run-pre-commit.sh"

KEY = "Prose"
MARK = "\u2713"
# Each half of the trailer, `✓ <tree>:<message>`, is this many hex digits.
HALF = 12
# The trailer's value. After a cold read it ends with counts, such as `; cold
# read: 5 findings, 3 fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`
# (DECISIONS: Every cold-read finding is answered before signing, and The cold
# reader says what it understood). This pattern only splits the counts out;
# counts_valid accepts them only in the forms cold_counts and understood_counts
# print. A value without the understood part is accepted too: commits signed
# before cold readers wrote understood lines carry none.
TRAILER = re.compile(r"✓ ([0-9a-f]{%d}):([0-9a-f]{%d})"
                     r"(?:; cold read: ([^;]*)(?:; understood: ([^;]*))?)?" % (HALF, HALF))
FOOTER_LENGTH = 6
FOOTER = re.compile(r"^prose ✓ ([0-9a-f]{%d})$" % FOOTER_LENGTH)

# Directories holding other people's docs. Build and output directories are
# left off: a doc in one may have been written in this repository.
VENDORED = {"node_modules", "vendor"}
DOC_SUFFIXES = {".adoc", ".asciidoc", ".markdown", ".md", ".mdx", ".rst"}
DOC_STEMS = {"CHANGELOG", "CONTRIBUTING", "README"}
SPEC_DIRS = {"openspec"}

# A line git reads as a trailer, which it rewrites as `token: value` when it
# adds trailers to that paragraph: `https://x` lands as `https: //x`.
GIT_TRAILER = re.compile(r"^([A-Za-z0-9-]+)[ \t]*:[ \t]*(.*)$")


class Refused(Exception):
    """A condition the caller has to fix; the message says how."""


def compactor():
    """compact.py, imported only by the commands that use it."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    import compact
    return compact


def scanner():
    """comment_scan, imported only by the commands that read a diff."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    import comment_scan
    return comment_scan


def git(args, cwd=None):
    """git with the reads pinned the way the commit-trailer library pins them."""
    result = subprocess.run(
        ["git", "-c", "log.showSignature=false", "-c", "trailer.separators=:",
         "-c", "core.quotePath=false", "-c", "i18n.logOutputEncoding=UTF-8"] + args,
        cwd=cwd, capture_output=True, check=False,
    )
    # Read as bytes and decoded here. Text mode would turn a bare CR into a
    # newline, and line numbers would then drift from git's. surrogateescape
    # keeps each byte that is not UTF-8 distinct, so editing one changes the
    # hash; wherever text is hashed, it is encoded back the same way
    # (TEXT_ERRORS).
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise Refused(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout.decode("utf-8", errors=TEXT_ERRORS)


# ---------------------------------------------------------------------------
# The commit message
# ---------------------------------------------------------------------------

def _clean(text):
    """The message as git's `whitespace` cleanup leaves it.

    Lines starting with `#` are kept, and so signed. `prose check` refuses
    such a line, because git's `strip` cleanup deletes it.
    """
    # ASCII blanks only, as git strips: a line of U+00A0 is not blank to git.
    lines = [line.rstrip(" \t\r") for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return out


def _paragraphs(lines):
    paragraphs, current = [], []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return paragraphs


# The line prefixes git's trailer parser counts as lines git wrote itself.
# `git cherry-pick -x` writes the second; a message holding it is signed with
# it, but it still decides where git puts the trailers it adds.
GIT_GENERATED = ("Signed-off-by: ", "(cherry picked from commit ")
# The characters git accepts as indenting a trailer's continuation line. git's
# isspace, unlike Python's str.isspace, is ASCII only, and a message line holds
# no CR or LF.
GIT_INDENT = (" ", "\t")


def _is_trailer_block(paragraph):
    """Whether git reads this paragraph as a trailer block, by trailer.c's
    rule: either every line is a trailer or continues one, or at least a
    quarter of the lines are trailers and one of them is a line git
    generates itself (GIT_GENERATED)."""
    trailers = others = continuations = 0
    recognised = False
    for line in reversed(paragraph):
        if line.startswith(GIT_GENERATED):
            trailers, continuations, recognised = trailers + 1, 0, True
        elif GIT_TRAILER.match(line):
            trailers, continuations = trailers + 1, 0
        elif line[:1] in GIT_INDENT:
            continuations += 1
        else:
            others, continuations = others + 1 + continuations, 0
    others += continuations
    return (recognised and trailers * 3 >= others) or bool(trailers and not others)


def _fold_empty_values(lines):
    """The lines of a trailer block as git rewrites them: a `Key:` line with
    no value, followed by an indented line, becomes one line,
    `Key: <that line, unindented>`."""
    out, index = [], 0
    while index < len(lines):
        line = lines[index]
        found = GIT_TRAILER.match(line)
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if found and not found.group(2) and following[:1] in GIT_INDENT:
            value = following.lstrip(" \t")
            out.append(f"{found.group(1)}: {value}")
            index += 2
            continue
        out.append(line)
        index += 1
    return out


def _joined(paragraphs):
    """The paragraphs as one text for hashing.

    When git reads the last paragraph as a trailer block, it is first put in
    the form git rewrites a block into when it adds trailers there: an
    empty-valued line joined with the indented line after it, and each
    trailer-shaped line written `token: value`, with only ASCII blanks
    trimmed. The title is never a trailer block, and git rewrites no other
    paragraph.
    """
    if len(paragraphs) > 1 and _is_trailer_block(paragraphs[-1]):
        last = [GIT_TRAILER.sub(r"\1: \2", line).rstrip(" \t")
                for line in _fold_empty_values(paragraphs[-1])]
        paragraphs = paragraphs[:-1] + [last]
    return "\n\n".join("\n".join(p) for p in paragraphs)


def message_body(text):
    """The message as `prose check` signs it: all of it, normalised for hashing."""
    return _joined(_paragraphs(_clean(text)))


def signed_bodies(text):
    """Each body a committed message may have been signed as.

    git adds trailers only at the end of the message: to its last paragraph
    when that is a trailer block, or as a new paragraph. So the signed text is
    the stored message minus some number of lines from the end of its last
    trailer block. The first body removes none; each next one removes one more
    trailer-shaped line, dropping the paragraph once it is empty.

    The search stops at an indented line: git never wraps the trailers it
    adds, so that line is text someone wrote, and it stays signed. It stops
    at any other line that is not trailer-shaped, and never reaches the title.
    """
    paragraphs = _paragraphs(_clean(text))
    yield _joined(paragraphs)
    if len(paragraphs) < 2 or not _is_trailer_block(paragraphs[-1]):
        return
    head, block = paragraphs[:-1], paragraphs[-1]
    while block and GIT_TRAILER.match(block[-1]):
        block = block[:-1]
        yield _joined(head + [block] if block else head)


# The characters `core.commentChar=auto` may pick.
AUTO_COMMENT_CHARS = "#;@!$%^&|:"


def comment_chars(root=None):
    """The list of prefixes git may treat as starting a comment line: `#`,
    or, when root is given, that repository's core.commentChar."""
    if root is None:
        return ["#"]
    try:
        # git config exits 1 when the key is unset, and git() raises that as
        # Refused.
        value = git(["config", "--get", "core.commentChar"], root).strip("\n")
    except Refused:
        return ["#"]
    # git reads `auto` in any case.
    if value.lower() == "auto":
        return list(AUTO_COMMENT_CHARS)
    return [value] if value else ["#"]


def refuse_comment_lines(text, root=None):
    """Refuse a message with a line starting with a comment character.

    `strip` cleanup deletes such a line, and git puts the trailers it adds
    before a comment line that ends the message. Let through, either would
    leave a stored message that does not hash like the text signed.
    """
    for char in comment_chars(root):
        if any(line.startswith(char) for line in _clean(text)):
            raise Refused(
                f"a line of the message starts with `{char}`, which git may delete or move "
                f"past the trailers, so the signature would not survive the commit. Reword "
                f"it so it does not start with `{char}`."
            )


def _body_hash(body):
    return hashlib.sha256(body.encode("utf-8", TEXT_ERRORS)).hexdigest()[:HALF]


def message_hash(message):
    """The message half of the trailer: the first 12 hex digits of the
    message body's SHA-256."""
    return _body_hash(message_body(message))


def committed_message_matches(message, message_half):
    """Whether a stored message, minus trailers added after the check, hashes
    to message_half."""
    return any(_body_hash(body) == message_half for body in signed_bodies(message))


def snapshot(message, root):
    """The trailer line for the staged tree and this message, without the
    refusals `check` applies first.

    The tree is what `git write-tree` makes of the index now, as the shared
    commit-trailer library's mint-trailer.sh reads it.
    """
    tree = git(["write-tree"], root).strip()
    return f"{KEY}: {MARK} {tree[:HALF]}:{message_hash(message)}"


# ---------------------------------------------------------------------------
# What counts as prose
# ---------------------------------------------------------------------------

def is_doc(path):
    # Trailing blanks come off first: a reader sees `notes.md ` as a .md file,
    # though pathlib does not.
    pure = pathlib.PurePosixPath(path.rstrip())
    if SPEC_DIRS & set(pure.parts[:-1]):
        return True
    return pure.suffix.lower() in DOC_SUFFIXES or pure.name.split(".")[0].upper() in DOC_STEMS


def _touched(scan, diff):
    """Map each file the diff touches to the line numbers it added.

    `added_lines` covers every file with added lines; the loop adds each
    deleted file, under its old path, with an empty set."""
    touched = scan.added_lines(diff)
    old, in_header = None, False
    for line in diff.split("\n"):
        if line.startswith("diff "):
            old, in_header = None, True
        elif in_header and line.startswith("--- "):
            target = scan.header_path(line[4:])
            old = None if target == "/dev/null" else re.sub(r"^a/", "", target)
        elif in_header and line.startswith("+++ "):
            if scan.header_path(line[4:]) == "/dev/null" and old is not None:
                touched.setdefault(old, set())
        elif line.startswith("@@"):
            in_header = False
    return touched


def _changed_docs(root, base):
    """{path: (deleted, link)} for each doc or spec whose content the staged
    change alters. link: what is staged there is a symlink or a submodule,
    whose one line is a target path or a commit, not prose.

    Read from `--raw`, because the text diff gives no header to a file git
    diffs as binary (UTF-16, a NUL byte, `-diff`), and `--raw` still names
    it. A pure rename or a permission change keeps the blob and is left out;
    a type change, such as a file made a symlink, is kept even when the blob
    is the same. A deleted doc is named by its old path."""
    # --ignore-submodules=none as in prose_in's diff: under a config that
    # ignores submodules, a bumped submodule would be missing here and read
    # as a doc.
    raw = git(["diff", "--cached", "--raw", "-z", "--no-abbrev", "-M", "--no-relative",
               "--no-color", "--ignore-submodules=none", base], root)
    fields = raw.split("\0")
    found, index = {}, 0
    while index < len(fields) and fields[index].startswith(":"):
        old_mode, new_mode, old_blob, new_blob, status = fields[index][1:].split(" ", 4)
        paths = fields[index + 1:index + (3 if status[:1] in "RC" else 2)]
        index += 1 + len(paths)
        # A mode's first two digits are its kind: 10 a file, 12 a symlink,
        # 16 a submodule.
        if old_blob == new_blob and old_mode[:2] == new_mode[:2]:
            continue
        path = paths[0] if status[:1] == "D" else paths[-1]
        if is_doc(path):
            found[path] = (status[:1] == "D", new_mode in ("120000", "160000"))
    return found


class Item(NamedTuple):
    """One listed piece of prose: what the listing shows, its note, and the
    file it is in, which is None for the commit message. spans are its
    (first, last) line pairs: each comment block, or each run of a doc's
    added lines, which a doc git diffs as binary has none of."""
    what: str
    note: str
    path: Optional[str]
    deleted: bool = False
    spans: tuple = ()


def _runs(numbers):
    """Sorted line numbers as (first, last) pairs of consecutive runs."""
    runs = []
    for number in sorted(numbers):
        if runs and number == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], number)
        else:
            runs.append((number, number))
    return tuple(runs)


def prose_in(root, base, read: Callable[[str], str]):
    """([Item], [flag lines]) for the prose the staged change touches.

    A listing for the pass, not what the trailer hashes: the message, each doc
    or spec file the diff touches, and each code comment it adds to or edits.
    The flags are history-language warnings on those comments. base is the
    revision the diff is against, or None for the empty tree.
    """
    scan = scanner()
    items, flags = [Item("commit message", "", None)], []
    # This module's git(), not the scanner's: its surrogateescape decoding
    # keeps a path that is not UTF-8 usable by `read`. -M finds renames
    # whatever the user's config, so a pure rename lists nothing.
    # --submodule=short shows a submodule as one line; at a code-looking path
    # it is listed as "could not be read".
    base = base or _empty_tree(root)
    diff = git(scan.DIFF + ["-M", "--submodule=short", "--ignore-submodules=none",
                            "--cached", base], root)
    touched = _touched(scan, diff)
    docs = _changed_docs(root, base)
    for path in docs:
        touched.setdefault(path, set())
    for path, lines in sorted(touched.items()):
        parts = set(pathlib.PurePosixPath(path).parts)
        doc = is_doc(path)
        # A doc is skipped only in a vendored directory; code is skipped in
        # any of the scanner's SKIP_DIRS, build output included.
        if parts & (VENDORED if doc else scan.SKIP_DIRS):
            continue
        if doc:
            deleted, link = docs.get(path, (False, False))
            # A symlink or submodule has no passage to read cold.
            items.append(Item(path, "changed", path, deleted, () if link else _runs(lines)))
            continue
        if not scan.scannable(path) or not lines:
            continue
        try:
            source = read(path)
        except (OSError, Refused, UnicodeDecodeError):
            items.append(Item(path, "could not be read", path))
            continue
        # git does not treat a bare CR as a line end. Without this replacement,
        # comments_in would, and every later line number would drift from the
        # diff's.
        source = re.sub(r"\r(?!\n)", " ", source)
        comments = scan.comments_touching(path, source, lines)
        if comments is None:
            items.append(Item(path, "did not parse", path))
            continue
        if not comments:
            continue
        spans = [f"{c.start}" if c.start == c.end else f"{c.start}-{c.end}" for c in comments]
        items.append(Item(f"{path}:{','.join(spans)}", "comment", path,
                          spans=tuple((c.start, c.end) for c in comments)))
        for comment in comments:
            for note in scan.history_notes(comment, scan.mask_examples(scan.strip_markers(comment))):
                flags.append(f"{path}:{note.line}  {note.headline}")
    return items, flags


# The sections rules.md must have, in this order, each matched against the
# start of its `## ` heading. The rules section holds `### <n>. <title>`
# subsections.
RULE_SECTIONS = ("Scope", "The pass", "The rules", "How agents cheat")
RULES_IN_FULL = 9


def _fenced_lines(lines):
    """[bool] of the same length as lines: whether each line sits inside a
    ``` or ~~~ fence, the opening and closing marker lines counted as inside.
    A line starting with a marker opens one; only that same marker closes it,
    so a ~~~ line inside a ``` fence is content, not a close."""
    states, fence = [], None
    for line in lines:
        marker = "```" if line.startswith("```") else "~~~" if line.startswith("~~~") else None
        if fence:
            states.append(True)
            if marker == fence:
                fence = None
        elif marker:
            states.append(True)
            fence = marker
        else:
            states.append(False)
    return states


def read_rules():
    """rules.md as (preamble, heading, rules, cheats): the text before the
    rules section, that section's heading line, the rules as (number, title,
    text), and the cheat-list section.

    Split by headings; a line inside a ``` or ~~~ fence is always content,
    never a heading. Refuses when the file is not UTF-8, when a section is
    missing, extra or out of order, or when the rules are not numbered 1, 2,
    3 and so on. A rules file the check cannot print in full must stop the
    check, not let it silently print less than the file holds.
    """
    try:
        text = RULES.read_text(encoding="utf-8")
    except OSError as error:
        raise Refused(f"the rules file is missing ({RULES}): {error.strerror or error}")
    except UnicodeDecodeError as error:
        raise Refused(f"the rules file is not valid UTF-8 ({RULES}): {error}")
    # The first "section" is the title and principle, before any `## `.
    lines = text.split("\n")
    sections = [["", []]]
    for line, fenced in zip(lines, _fenced_lines(lines)):
        if not fenced and line.startswith("## "):
            sections.append([line[3:].strip(), [line]])
        else:
            sections[-1][1].append(line)
    names = [name for name, _ in sections[1:]]
    title_lines = sections[0][1]
    if not any(l.startswith("# ") for l, fenced in zip(title_lines, _fenced_lines(title_lines))
               if not fenced) \
            or len(names) != len(RULE_SECTIONS) \
            or not all(name.startswith(want) for name, want in zip(names, RULE_SECTIONS)):
        raise Refused(f"{RULES} must have a title and principle, then exactly the sections "
                      + ", ".join(f"'## {want}'" for want in RULE_SECTIONS) + ", in that order, "
                      "each once, and no other '## ' section")
    rules_at, cheats_at = 3, 4
    preamble = "\n".join(line for _, lines in sections[:rules_at] for line in lines).strip("\n")
    rule_lines = sections[rules_at][1][1:]
    rules, rule = [], None
    for line, fenced in zip(rule_lines, _fenced_lines(rule_lines)):
        heading = None if fenced else re.match(r"^### (\d+)\. (\S.*?)\s*$", line)
        if heading:
            rule = [int(heading.group(1)), heading.group(2).strip(), [line]]
            rules.append(rule)
        elif not fenced and line.startswith("#"):
            raise Refused(f"{RULES}: unexpected heading in the rules section: {line}")
        elif rule is not None:
            rule[2].append(line)
        elif line.strip():
            raise Refused(f"{RULES}: text before the first rule ('### 1. …') in the rules "
                          f"section: {line}")
    if [r[0] for r in rules] != list(range(1, len(rules) + 1)) or len(rules) < RULES_IN_FULL:
        raise Refused(f"{RULES}: the rules must be '### 1. …', '### 2. …' and so on, "
                      f"at least {RULES_IN_FULL} of them")
    cheats = "\n".join(sections[cheats_at][1]).strip("\n")
    heading = sections[rules_at][1][0]
    return preamble, heading, [(n, title, "\n".join(lines).strip("\n")) for n, title, lines in rules], cheats


def print_rules(stream=None):
    """The rules as the first call prints them: everything up to the rules in
    full, rules 1 to RULES_IN_FULL in full, the rest as one-line checklist
    items, then the cheat list."""
    preamble, heading, rules, cheats = read_rules()
    print(preamble, file=stream)
    print("\n" + heading + "\n", file=stream)
    for number, title, text in rules[:RULES_IN_FULL]:
        print(text + "\n", file=stream)
    print("Also check each of these:\n", file=stream)
    for number, title, _ in rules[RULES_IN_FULL:]:
        print(f"  [ ] {number}. {title}", file=stream)
    print("\n" + cheats, file=stream)


# ---------------------------------------------------------------------------
# check / verify-commit
# ---------------------------------------------------------------------------

def _empty_tree(root):
    return git(["hash-object", "-t", "tree", "/dev/null"], root).strip()


def _revision(spec, root):
    """The commit spec names, or None when there is none (an unborn branch,
    the parent of a root commit)."""
    try:
        return git(["rev-parse", "--verify", "-q", f"{spec}^{{commit}}"], root).strip() or None
    except Refused:
        return None


def refuse_non_utf8_commit_encoding(root):
    """Refuse when commits here are stored in an encoding other than UTF-8.

    git stores the message's UTF-8 bytes under that encoding's label, and
    reading the commit converts them from it: the trailer's `✓` and any other
    non-ASCII text read back as different characters, so the commit hook
    cannot verify the commit.
    """
    try:
        value = git(["config", "--get", "i18n.commitEncoding"], root).strip()
    except Refused:
        return
    if value and value.lower() not in ("utf-8", "utf8"):
        raise Refused(
            f"i18n.commitEncoding is {value}; git labels the commit with it, and the message "
            f"then reads back as other text, so its signature would not survive. Unset it or "
            f"set it to UTF-8."
        )


def _is_noncharacter(cp):
    """Whether git's UTF-8 check rejects this code point, though Python accepts it."""
    return (cp & 0xFFFE) == 0xFFFE or 0xFDD0 <= cp <= 0xFDEF


def refuse_non_utf8_message(message):
    """Refuse a message holding bytes that are not UTF-8, or a noncharacter.

    git reads either as Latin-1 and rewrites it as UTF-8 when it stores the
    commit, so the stored message does not hash like the text checked.
    """
    try:
        message.encode("utf-8")
    except UnicodeEncodeError:
        raise Refused(
            "the commit message is not valid UTF-8; git rewrites it when it stores the "
            "commit, so its signature would not survive. Save it as UTF-8."
        )
    for char in message:
        if _is_noncharacter(ord(char)):
            raise Refused(
                f"the commit message holds the Unicode noncharacter U+{ord(char):04X}, which "
                f"git rewrites when it stores the commit, so the signature would not survive. "
                f"Remove it."
            )


def refuse_configured_trailers(root):
    """Refuse any trailer.* setting except trailer.separators set to `:`.

    Any other setting can make git commit --trailer rewrite the message
    after the check: other separators turn `Fixes #12` into `Fixes: 12`,
    `.key` renames tokens, `.command` adds trailers, `ifexists` deletes a
    line whose token prefixes an added one, and `where` moves the added
    trailers above an indented line.
    """
    # Read trailer.separators with plain git, not git() above, which pins it
    # and would hide the user's setting. It is judged by the value git
    # actually uses, so a global value the repository overrides with `:`
    # passes. Any other trailer.* key is refused if it is set at all, in any
    # scope.
    separators = subprocess.run(["git", "config", "--get", "trailer.separators"],
                                cwd=root, capture_output=True, check=False)
    if separators.returncode == 0:
        value = separators.stdout.decode("utf-8", errors="replace").rstrip("\n")
        if value != ":":
            raise Refused(
                f"trailer.separators is set to {value!r}; git commit --trailer then rewrites "
                f"the message after the check, so the signature would not survive. Unset it."
            )
    result = subprocess.run(["git", "config", "--get-regexp", r"^trailer\."],
                            cwd=root, capture_output=True, check=False)
    if result.returncode != 0:
        return
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        name, _, value = line.partition(" ")
        if name == "trailer.separators":
            continue
        raise Refused(
            f"{name} is set to {value!r}; git commit --trailer then rewrites the message "
            f"after the check, so the signature would not survive. Unset it."
        )


def refuse_bare_cr(message):
    """Refuse a CR that does not end a line.

    git keeps it inside the line and trims it off a trailer's value, while
    the signature reads it as a line break, so the two stop agreeing. A CR
    followed only by line ends is trimmed by both, so it is allowed.
    """
    if re.search(r"\r(?!\n)(?=[\s\S]*[^\r\n])", message):
        raise Refused(
            "the commit message holds a carriage return that does not end a line; git "
            "reads it differently from the signature, so the signature would not survive. "
            "Remove it."
        )


def run_pre_commit(root, signing):
    """Run the repository's pre-commit hook through the shared library, so a
    formatter rewrites the staged files before they are listed or signed.

    The library records a pass, so the commit script that follows does not
    run the hook again on the same state. With no hook, nothing runs and
    nothing is printed. See DECISIONS.md, *`prose check` runs the pre-commit
    hook first*.
    """
    if not RUN_PRE_COMMIT.is_file():
        raise Refused(
            f"the shared commit-trailer library has no run-pre-commit.sh (expected "
            f"{RUN_PRE_COMMIT}); update the shared-skills clone prose is installed from"
        )
    sys.stdout.flush()
    sys.stderr.flush()
    # The hook's output and the library's reasons go to stderr as they are
    # written; stdout carries only the one word.
    result = subprocess.run(["sh", str(RUN_PRE_COMMIT)], cwd=root, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, check=False)
    # Not always the hook's fault: an unmerged index fails here too.
    if result.returncode != 0:
        raise Refused("run-pre-commit.sh refused, for the reason above; nothing was signed. "
                      "Fix the cause, restage, and run this call again")
    if result.stdout.decode("utf-8", errors="replace").strip() == "changed":
        what = ("the trailer signs the files as it left them" if signing
                else "the prose below is read from the files as it left them")
        print(f"prose: the pre-commit hook changed the staged files; {what}", file=sys.stderr)


def check(message, root, amend=False, signing=False):
    """(items, flags, trailer line) for the staged change and this message.

    The listing's diff is against the commit's eventual first parent: HEAD,
    or with amend HEAD's first parent, since `git commit --amend` replaces
    HEAD. The trailer does not depend on it. The pre-commit hook runs after
    the message is accepted and before anything is listed or hashed.
    """
    refuse_non_utf8_commit_encoding(root)
    refuse_non_utf8_message(message)
    refuse_bare_cr(message)
    refuse_configured_trailers(root)
    refuse_comment_lines(message, root)
    if not message_body(message):
        raise Refused("the commit message is empty; write it first, then run the check on it")
    if amend:
        if _revision("HEAD", root) is None:
            raise Refused("--amend, but there is no commit to amend")
        base = _revision("HEAD^", root)
    else:
        base = _revision("HEAD", root)
    run_pre_commit(root, signing)
    items, flags = prose_in(root, base, lambda path: git(["show", f":0:{path}"], root))
    return items, flags, snapshot(message, root)


def cold_counts(fixed, kept):
    """What a commit's trailer value says of its cold read, after `; cold read: `."""
    total = fixed + kept
    if not total:
        return "no findings"
    return f"{total} finding{'' if total == 1 else 's'}, {fixed} fixed, {kept} kept"


def understood_counts(items, fixed, kept):
    """What a commit's trailer value says of the cold reader's understood
    lines, after `; understood: `: how many items; then, of the lines that
    did not match what the writer meant, how many were fixed and how many
    were kept."""
    return f"{items} item{'' if items == 1 else 's'}, {fixed} fixed, {kept} kept"


def counts_valid(counts, understood=None):
    """Whether counts and understood, a trailer value's cold-read and
    understood counts, are each None (the value has none) or in the one form
    cold_counts or understood_counts prints. Understood counts also need at
    least one item, and no more lines fixed and kept than items."""
    if understood is not None:
        found = re.fullmatch(r"([0-9]+) items?, ([0-9]+) fixed, ([0-9]+) kept", understood)
        if not found:
            return False
        items, fixed, kept = (int(group) for group in found.groups())
        if not items or fixed + kept > items or understood != understood_counts(items, fixed, kept):
            return False
    if counts is None or counts == "no findings":
        return True
    found = re.fullmatch(r"[0-9]+ findings?, ([0-9]+) fixed, ([0-9]+) kept", counts)
    return bool(found) and counts == cold_counts(int(found.group(1)), int(found.group(2)))


def verify_staged(line, message, root):
    """(ok, reason) for a trailer line `prose check` printed, against the
    staged tree and this message now. The commit script runs this just before
    it commits. A failing reason starts with `unrecognised`, `mismatch` or
    `tree`, as verify_commit's does."""
    found = re.fullmatch(r"%s: (%s)" % (KEY, TRAILER.pattern), line.strip())
    if not found:
        return False, f"unrecognised: {line.strip()}"
    tree_half, message_half = found.group(2), found.group(3)
    if not counts_valid(found.group(4), found.group(5)):
        return False, f"unrecognised: {line.strip()}"
    tree = git(["write-tree"], root).strip()
    if message_half != message_hash(message):
        return False, (
            f"mismatch: the {KEY}: trailer does not match the commit message; the message "
            f"changed after `prose check`, or the trailer did not come from it"
        )
    if not tree.startswith(tree_half):
        return False, (
            f"tree: the {KEY}: trailer does not match the staged files; they changed "
            f"after `prose check`"
        )
    return True, "checked"


def last_trailer(sha, key, root):
    """The last non-blank value of the commit's `key` trailers; "" when every
    one is blank, None when it has none.

    Each line is split at its first `:`, the only separator git() lets git
    use."""
    lines = git(["log", "-1", f"--format=%(trailers:key={key},unfold)", sha], root)
    values = [line.split(":", 1)[1].strip() for line in lines.split("\n") if ":" in line]
    if not values:
        return None
    filled = [value for value in values if value]
    return filled[-1] if filled else ""


def verify_commit(sha, root):
    """(ok, reason). The reason starts with its kind: missing,
    unrecognised, mismatch (the message half) or tree (only the tree half)."""
    sha = git(["rev-parse", "--verify", f"{sha}^{{commit}}"], root).strip()
    parents = git(["log", "-1", "--format=%P", sha], root).split()
    if len(parents) > 1:
        return True, "merge commit, not checked"
    # `missing` means git sees no Prose key at all. A key with a blank value
    # (empty, spaces, a no-break space) is unrecognised.
    value = last_trailer(sha, KEY, root)
    if value is None:
        return False, f"missing: no {KEY}: trailer"
    # `prose check` refuses a non-UTF-8 i18n.commitEncoding, so a commit under
    # another label was made with config the check did not see (`git -c` at
    # commit). Reading it converts the message from that label, or, where git
    # cannot convert, shows the bytes that other readers decode differently.
    encoding = git(["log", "-1", "--format=%e", sha], root).strip()
    if encoding and encoding.lower() not in ("utf-8", "utf8"):
        return False, (f"mismatch: the message is stored as {encoding}, and `prose check` "
                       f"signs only UTF-8 messages")
    found = TRAILER.fullmatch(value)
    if not found or not counts_valid(found.group(3), found.group(4)):
        return False, f"unrecognised: {KEY}: {value}"
    tree_half, message_half = found.group(1), found.group(2)
    message = git(["log", "-1", "--format=%B", sha], root)
    if not committed_message_matches(message, message_half):
        return False, (
            f"mismatch: the {KEY}: trailer does not match the commit's message; the message "
            f"changed after `prose check` (a git hook such as prepare-commit-msg may have "
            f"edited it), or the trailer did not come from it"
        )
    tree = git(["rev-parse", f"{sha}^{{tree}}"], root).strip()
    if not tree.startswith(tree_half):
        return False, (
            f"tree: the {KEY}: trailer matches the message but not the commit's files; "
            f"the staged files changed after `prose check`"
        )
    return True, "checked"


# ---------------------------------------------------------------------------
# Posted text
# ---------------------------------------------------------------------------

def _post_lines(text):
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def split_footer(text):
    """(body, footer hash or None). The body is normalised for hashing:
    line endings to LF, trailing blanks off each line and off the end."""
    lines = _post_lines(text)
    found = FOOTER.match(lines[-1]) if lines else None
    if found:
        lines = lines[:-1]
        while lines and not lines[-1]:
            lines.pop()
    return "\n".join(lines), (found.group(1) if found else None)


def footer_hash(body):
    return hashlib.sha256(body.encode("utf-8", TEXT_ERRORS)).hexdigest()[:FOOTER_LENGTH]


def sign(text):
    body, _ = split_footer(text)
    if not body.strip():
        raise Refused("nothing to sign: the text is empty")
    return f"{body}\n\nprose ✓ {footer_hash(body)}\n"


def verify_post(text):
    body, found = split_footer(text)
    if found is None:
        return False, "no `prose ✓ <hash>` footer on the last line"
    if found != footer_hash(body):
        return False, "the footer does not match the text above it (edited after signing?)"
    return True, "signed"


# ---------------------------------------------------------------------------
# The posting hook
# ---------------------------------------------------------------------------

# Matches every tool of the GitHub MCP server, including a copy of the server
# bundled in a plugin, whose tools are named mcp__plugin_<plugin>_github__<tool>.
GITHUB_MCP = re.compile(r"^mcp__(?:plugin_.+_)?github__")
BODY_KEYS = {"body", "comment"}
# The gh verbs that post text, each with the flags that carry it: close and
# reopen post their comment with --comment, the rest with --body.
BODY_FLAGS = ("--body", "-b", "--body-file", "-F")
COMMENT_FLAGS = ("--comment", "-c")
_BODY_VERBS = {verb: BODY_FLAGS for verb in ("create", "new", "edit", "comment", "review")}
GH_VERBS = {"pr": {**_BODY_VERBS, "revert": BODY_FLAGS, "close": COMMENT_FLAGS, "reopen": COMMENT_FLAGS},
            "issue": {**_BODY_VERBS, "close": COMMENT_FLAGS, "reopen": COMMENT_FLAGS}}
# Each verb's short flags that take a value and do not carry the text, from
# `gh <noun> <verb> --help`. gh's flag parser, pflag, reads a group such as
# `-dc x` letter by letter. The first letter that takes a value swallows the
# rest of the group as that value, or the next argument if nothing is left:
# in `-tb x`, `b` is the title's text.
_REPO = "R"
SHORT_VALUES = {
    "pr": {"create": "aBHlmprTt" + _REPO, "new": "aBHlmprTt" + _REPO, "edit": "Bmt" + _REPO,
           "comment": _REPO, "review": _REPO, "close": _REPO, "reopen": _REPO,
           "revert": "t" + _REPO},
    "issue": {"create": "almpTt" + _REPO, "new": "almpTt" + _REPO, "edit": "mt" + _REPO,
              "comment": _REPO, "review": _REPO, "close": "r" + _REPO, "reopen": _REPO},
}
# Each verb's long flags other than the body flags, from the same help, as
# (flags that take a value, boolean flags). pflag gives a value-taking long
# flag the next argument whatever it looks like: in `--title -t`, `-t` is the
# title. A long flag in neither set is refused, because the hook cannot tell
# whether it takes the next argument.
_COMMENT_BOOLS = {"create-if-none", "delete-last", "edit-last", "yes"}
_PR_CREATE = ({"assignee", "base", "head", "label", "milestone", "project", "reviewer", "title"},
              {"draft", "dry-run", "no-maintainer-edit"})
_ISSUE_CREATE = ({"assignee", "blocked-by", "blocking", "label", "milestone", "parent",
                  "project", "title", "type"},
                 set())
LONG_FLAGS = {
    "pr": {"create": _PR_CREATE, "new": _PR_CREATE,
           "edit": ({"add-assignee", "add-label", "add-project", "add-reviewer", "base",
                     "milestone", "remove-assignee", "remove-label", "remove-project",
                     "remove-reviewer", "title"}, {"remove-milestone"}),
           "comment": (set(), _COMMENT_BOOLS),
           "review": (set(), {"approve", "comment", "request-changes"}),
           "close": (set(), {"delete-branch"}), "reopen": (set(), set()),
           "revert": ({"title"}, {"draft"})},
    "issue": {"create": _ISSUE_CREATE, "new": _ISSUE_CREATE,
              "edit": ({"add-assignee", "add-blocked-by", "add-blocking", "add-label",
                        "add-project", "add-sub-issue", "milestone", "parent",
                        "remove-assignee", "remove-blocked-by", "remove-blocking",
                        "remove-label", "remove-project", "remove-sub-issue", "title", "type"},
                       {"remove-milestone", "remove-parent", "remove-type"}),
              "comment": (set(), _COMMENT_BOOLS), "review": (set(), set()),
              "close": ({"duplicate-of", "reason"}, set()), "reopen": (set(), set())},
}
COMMON_LONG = ({"repo"}, {"help"})
# Each verb's flags that make gh take the text from somewhere the hook cannot
# read: commits, a saved run, a template, an editor or the browser. Each entry
# is (long names, short letters), and any of them is refused.
_CREATE_SOURCES = ({"editor", "recover", "template", "web"}, "eTw")
_PR_CREATE_SOURCES = (_CREATE_SOURCES[0] | {"fill", "fill-first", "fill-verbose"}, "efTw")
_COMMENT_SOURCES = ({"editor", "web"}, "ew")
BODY_SOURCES = {
    "pr": {"create": _PR_CREATE_SOURCES, "new": _PR_CREATE_SOURCES,
           "comment": _COMMENT_SOURCES},
    "issue": {"create": _CREATE_SOURCES, "new": _CREATE_SOURCES,
              "comment": _COMMENT_SOURCES},
}
NO_SOURCES = (set(), "")
SOURCE = "source"
# gh subcommands that send no text, from `gh <noun> --help`: a gh read such
# as `gh pr list --search 'review-requested:@me'` is no post, though it names
# a post verb. A closed list, so merge (a known gap) and a verb gh adds later
# stay unread. cobra takes the first word after the noun as the subcommand,
# exactly as written.
NO_TEXT_VERBS = {
    "pr": {"list", "ls", "status", "checkout", "co", "checks", "diff", "view", "ready",
           "lock", "unlock", "update-branch"},
    "issue": {"list", "ls", "status", "delete", "develop", "lock", "unlock", "pin",
              "unpin", "transfer", "view"},
}


class Unreadable:
    """A body the hook cannot read from the command, and why."""

    def __init__(self, why):
        self.why = why


ACCEPTED = (
    "The hook reads a gh post only when gh is the whole command, with the body as "
    "--body '<text>' (single quotes, or double quotes with no $, backtick or "
    "backslash) or --body-file <a file that exists>. To post longer text, sign it "
    "into a file and pass that: prose.py sign --goals '...' prints the rules and a "
    "pass token; then prose.py sign --pass <token> < draft.md > signed.md, and "
    "gh ... --body-file signed.md.")
NOT_ALLOWED = Unreadable(
    "this command is not one of the forms the hook reads, so what it posts cannot be "
    "checked. " + ACCEPTED)
FROM_STDIN = Unreadable("the text comes from stdin, so it cannot be checked. " + ACCEPTED)


def body_fields(value, path=""):
    """[(where, text)] for every body-like string in an MCP tool's input."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{path}.{key}" if path else str(key)
            if str(key).lower() in BODY_KEYS and isinstance(item, str) and item.strip():
                found.append((where, item))
            else:
                found.extend(body_fields(item, where))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(body_fields(item, f"{path}[{index}]"))
    return found


def _body_flag(args, i, flags=BODY_FLAGS, values="", sources=""):
    """(flag, (text, kind) or None, index of the next arg) for args[i].

    flag is None when args[i] is not a body flag, and SOURCE when it holds a
    letter from sources, one that makes gh take the text from elsewhere.
    Reads `--body x`, `--body=x`, and pflag's short forms: `-b x`, `-bx`,
    `-b=x`, and a group such as `-db x`. values holds the verb's other short
    letters that take a value. In a group, the first letter that takes a
    value swallows the rest of the group as that value: in `-tb x`, `b` is
    the title's text, not the body flag."""
    arg, kind = args[i]
    for name in flags:
        if name.startswith("--"):
            if arg == name:
                return name, (args[i + 1] if i + 1 < len(args) else None), i + 2
            if arg.startswith(name + "="):
                return name, (arg[len(name) + 1:], kind), i + 1
    if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
        shorts = {name[1] for name in flags if not name.startswith("--")}
        for position in range(1, len(arg)):
            letter, rest = arg[position], arg[position + 1:]
            if letter == "=":
                # pflag ends a group at `=`: `-d=t` is `--draft=t`.
                return None, None, i + 1
            if letter in shorts:
                if rest:
                    return f"-{letter}", (rest[1:] if rest.startswith("=") else rest, kind), i + 1
                return f"-{letter}", (args[i + 1] if i + 1 < len(args) else None), i + 2
            if letter in sources:
                return SOURCE, None, i + 1
            if letter in values:
                return None, None, (i + 1 if rest else i + 2)
    return None, None, i + 1


# A command that mentions a gh post verb is read as a post unless
# _posts_nothing shows that the shell runs no gh post in it. A false match only
# blocks the command; a missed post lets text out unchecked.
POST_WORDS = re.compile(
    r"\bgh\b[\s\S]*\b(?:pr|issue)\b[\s\S]*\b(?:"
    + "|".join(sorted({verb for verbs in GH_VERBS.values() for verb in verbs})) + r")\b")
PLAIN = re.compile(r"[A-Za-z0-9_./:=@%+,#^-]")


def _words(command):
    """[(text, quoted)] for a command made only of plain words, or None.

    None when the shell would do more than join quoted parts. For bash that
    is an operator, a newline, an expansion, a glob, a backslash, or a
    double-quoted string holding $, a backtick or a backslash. For zsh it is
    also a word starting with an unquoted `=`, even after empty quotes
    (`''=x`), which zsh replaces with a command's path. Such a command is not
    one of the accepted forms, so the hook does not try to read it.
    """
    words, text, quoted, started, i = [], "", False, False, 0
    while i < len(command):
        char = command[i]
        if char in " \t":
            if started:
                words.append((text, quoted))
            text, quoted, started = "", False, False
            i += 1
        elif char == "'":
            close = command.find("'", i + 1)
            if close == -1:
                return None
            text, quoted, started, i = text + command[i + 1:close], True, True, close + 1
        elif char == '"':
            close = command.find('"', i + 1)
            if close == -1 or re.search(r"[$`\\]", command[i + 1:close]):
                return None
            text, quoted, started, i = text + command[i + 1:close], True, True, close + 1
        elif PLAIN.match(char) and not (char == "#" and not started) and not (char == "=" and not text):
            text, started, i = text + char, True, i + 1
        else:
            return None
    if started:
        words.append((text, quoted))
    return words


def runs_only_prose(command):
    """True when the command runs prose.py and nothing else, so text in its
    arguments (goals that mention `gh pr create`) is not a post.

    Operators and redirections are read outside quotes only, so goals may hold
    `;`. A command substitution anywhere, a newline, or any operator but a
    redirection makes it False: those could run another command.
    """
    if "`" in command or "$(" in command or "\n" in command:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return False
    if any(word in ("<", ">", ">>") for word in words):
        words = [w for i, w in enumerate(words) if w not in ("<", ">", ">>")
                 and (i == 0 or words[i - 1] not in ("<", ">", ">>"))]
    if not words or any(word and set(word) <= set("();<>|&") for word in words):
        return False
    program = words[1] if words[0] in ("python3", "python") and len(words) > 1 else words[0]
    return program == "prose.py" or program.endswith("/prose.py")


# Commands that treat their arguments and stdin as data, never as shell code,
# so a gh post named in them only mentions one. The list is closed on purpose:
# any other command may run the text it is given (sh -c, eval, trap, env -S,
# ssh, xargs), and a list of those is never complete.
#
# python3, node and git are listed although they can run gh: what they run is
# code handed to them on purpose (a script, -e, a git alias or rebase -x),
# which the hook does not read, as it does not read a script file. Leaving them
# out blocked ordinary scripts that only mention gh, the case this list is for.
# printf, test and [ are left out: their arguments look like data, yet bash 4+
# evaluates the array subscript in `printf -v 'a[$(…)]'` and
# `test -v 'a[$(…)]'`, so text that reads as data can run.
DATA_COMMANDS = {"echo", "cat", "tee", "grep", "egrep", "fgrep", "rg", "git",
                 "python", "python3", "node", "jq", "head", "tail", "wc", "sort", "uniq",
                 "cut", "tr", "ls", "cd", "true", "false"}
# Text names gh when gh is not followed by a word character or `-`: `gh-pages`
# and `gh_x` are other names. Nothing is excluded in front, since `${GH:-gh}`
# and `/usr/bin/gh` run gh.
GH_TEXT = re.compile(r"\bgh(?![\w-])")
# Reserved words that may come before a simple command and are not commands
# themselves, so the word after them is the command, checked like any other:
# in `if grep …` and `then gh …` the command is grep or gh. Not for,
# case, select, coproc, function, [[ or zsh's repeat, foreach, nocorrect and
# noglob, whose words are not a command or are run another way.
RESERVED = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "time"}
# Reserved words that end a compound command and run nothing, so `fi` beside
# a pipe is no command. Only a command made of nothing else: in `done sh`,
# sh runs. Not esac, whose case patterns are not read.
CLOSERS = {"fi", "done", "}"}
EXPANSION = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9#?$!@*-]|\{[A-Za-z_][A-Za-z0-9_]*\})")
REDIRECT = re.compile(r"&>>?|<<<|<<-|<<|<>|<&|<|>>|>&|>\||>")
METACHARS = " \t\n;&|()<>"


def _word(command, i):
    """(text, end, source) for the shell word starting at command[i], or None.

    text is the word after quote removal, with simple expansions ($NAME,
    ${NAME}, $1, $?) left out, since only literal text can name gh. source
    is the word as written, minus each backslash-newline outside single
    quotes, which both shells remove before reading the word: `i\\<newline>f`
    is `if`, and a lone `\\<newline>` is no word. None when the word holds
    anything that could run a command or that bash and zsh read differently:
    a command substitution, $'…', $"…", ${…} beyond a name, an unterminated
    quote, a leading `#`, or a `[` left open after the first character
    (`a[1<<EOF]=5` is not a heredoc to bash).
    """
    text, source, n, bracket = [], [], len(command), False
    while i < n and command[i] not in METACHARS:
        char, start = command[i], i
        if char == "'":
            close = command.find("'", i + 1)
            if close == -1:
                return None
            text.append(command[i + 1:close])
            i = close + 1
        elif char == '"':
            i += 1
            while True:
                if i >= n or command[i] == "`":
                    return None
                if command[i] == '"':
                    i += 1
                    break
                if command[i] == "\\":
                    if i + 1 >= n:
                        return None
                    if command[i + 1] == "\n":
                        source.append(command[start:i])
                        i += 2
                        start = i
                        continue
                    # In double quotes a backslash stays unless it escapes
                    # one of these: `<<"E\OF"` ends at a line `E\OF`.
                    if command[i + 1] not in '$`"\\':
                        text.append("\\")
                    text.append(command[i + 1])
                    i += 2
                elif command[i] == "$" and command[i + 1:i + 2] != '"':
                    found = EXPANSION.match(command, i)
                    if not found:
                        return None
                    i = found.end()
                else:
                    text.append(command[i])
                    i += 1
        elif char == "\\":
            if i + 1 >= n:
                return None
            if command[i + 1] == "\n":
                i += 2
                continue
            text.append(command[i + 1])
            i += 2
        elif char == "`":
            return None
        elif char == "$" and i + 1 < n and command[i + 1] not in METACHARS:
            found = EXPANSION.match(command, i)
            if not found:
                return None
            i = found.end()
        else:
            if char == "[" and set("".join(source)) - {"["}:
                bracket = True
            elif char == "]":
                bracket = False
            text.append(char)
            i += 1
        source.append(command[start:i])
    source = "".join(source)
    if bracket or source.startswith("#"):
        return None
    return "".join(text), i, source


def _heredoc_end(command, i, delimiter, quoted, strip_tabs):
    """The index just past a heredoc body starting at command[i], or None
    when it has no terminating line, or is unquoted and could run a command
    (a substitution) or join lines (a backslash)."""
    while i < len(command):
        end = command.find("\n", i)
        line = command[i:] if end == -1 else command[i:end]
        if (line.lstrip("\t") if strip_tabs else line) == delimiter:
            return len(command) if end == -1 else end + 1
        if end == -1 or (not quoted and re.search(r"\$\(|`|\\", line)):
            return None
        i = end + 1
    return None


def _commands(command):
    """(simple commands, grouped) for a shell command, or None when any part
    of it is beyond what this reads exactly.

    Each simple command is ([(text, source)], fed): each word's text and
    source as _word gives them, and whether the command reads a pipe or an
    input redirection (`<`, `<>`, `<&`, a heredoc, `<<<`). A pipe feeds the
    next command that has a word, across line breaks and comments, as both
    shells do. A word that is only line continuations is no word. Other
    redirections are left out. grouped is True when input may reach more
    than one simple command: a pipe into a subshell, a `$(`, or a reserved
    word that opens a compound command; an input redirection on a `(`…`)`,
    or on a command holding `}`, `done` or `fi`; or a `(` in a fed command.
    Heredoc bodies and comments are skipped, since the shell runs neither.
    None for anything whose reading differs between shells or could hide a
    command: what _word refuses, process substitution, a heredoc inside
    parentheses (bash 3.2 reads those its own way) or whose body would start
    inside an open `(`, an unquoted heredoc body that could run or join
    lines, a heredoc with no end, a number before a redirection other than
    one ASCII digit, a comment holding quotes or operators, unbalanced
    parentheses.
    """
    commands, fed, pending, depth, i, n = [[]], [False], [], 0, 0, len(command)
    piped = grouped = False

    def start():
        commands.append([])
        fed.append(False)

    while i < n:
        char = command[i]
        if char in " \t":
            i += 1
        elif char == "\n":
            if pending and depth:
                # A `(` still open: bash and zsh read the heredoc body only
                # after it closes, so the lines below are code.
                return None
            i += 1
            for heredoc in pending:
                i = _heredoc_end(command, i, *heredoc)
                if i is None:
                    return None
            pending = []
            start()
        elif char == "#":
            end = command.find("\n", i)
            end = n if end == -1 else end
            if re.search(r"[;&|()<>`$\\'\"]", command[i:end]):
                return None
            i = end
        elif char in "<>" or command.startswith("&>", i):
            op = REDIRECT.match(command, i).group()
            i += len(op)
            if command.startswith("(", i):
                return None
            while i < n and command[i] in " \t":
                i += 1
            word = _word(command, i)
            if word is None or not word[2]:
                return None
            if op in ("<<", "<<-"):
                source = word[2]
                if depth or "$" in source:
                    return None
                pending.append((word[0], any(q in source for q in "'\"\\"), op == "<<-"))
            if op.startswith("<"):
                fed[-1] = True
            i = word[1]
        elif char in ";&|":
            end = i
            while end < n and command[end] in ";&|":
                end += 1
            piped = piped or ("|" in command[i:end] and command[i:end] != "||")
            start()
            i = end
        elif char in "()":
            if char == "(" and (piped or fed[-1]):
                grouped = True
            depth += 1 if char == "(" else -1
            if depth < 0:
                return None
            start()
            i += 1
        else:
            word = _word(command, i)
            if word is None:
                return None
            text, end, source = word
            if command[end:end + 1] in ("<", ">") and source.isdigit():
                # Both shells read one ASCII digit as a descriptor. zsh reads
                # `12>` as the word 12, bash as descriptor 12, and neither
                # reads a non-ASCII digit as one.
                if not re.fullmatch("[0-9]", source):
                    return None
            elif text or source:
                if piped:
                    # `!` and `time` lead a pipeline's command; any other
                    # reserved word opens a compound command, all of it fed.
                    fed[-1] = True
                    if source in RESERVED - {"!", "time"}:
                        grouped = True
                    piped = source in ("!", "time")
                commands[-1].append((text, source))
            i = end
    if pending or depth:
        return None
    for words, reads in zip(commands, fed):
        if reads and (not words or any(source in CLOSERS for _, source in words)):
            grouped = True
    return [(words, reads) for words, reads in zip(commands, fed) if words], grouped


def _gh_args(words):
    """words[1:] for a gh command given as plain words, without a leading
    -R/--repo and its value."""
    args = list(words[1:])
    while args and (args[0][0] in ("-R", "--repo") or args[0][0].startswith(("--repo=", "-R"))):
        args = args[2:] if args[0][0] in ("-R", "--repo") else args[1:]
    return args


def _fed_blocker(name):
    """Why a command fed by a pipe or an input redirection blocks."""
    return Unreadable(
        f"`{name}` reads a pipe or an input redirection (<, <<, <<<), so what it "
        "runs or posts cannot be checked. Only a data command (echo, cat, grep, "
        "head, python3 …) or a gh subcommand that takes no body, such as gh pr "
        "view, may read one. " + ACCEPTED)


GROUPED = Unreadable(
    "a pipe or an input redirection feeds a group, loop or subshell, so what it "
    "runs or posts cannot be checked unless every command in it is a data "
    "command (echo, cat, grep, head, python3 …). " + ACCEPTED)


def _blocker(command, cwd):
    """None when the shell provably runs no gh post in this command, else
    the Unreadable that says why not.

    That holds when each simple command is one of:
    - a gh command given as plain words, gh first, that sends no text the
      hook checks: a label edit, `gh pr ready`, a close without a comment.
      A gh post with a body must be the whole command;
    - a command from DATA_COMMANDS, which may name gh in its arguments,
      quotes or heredoc, as data;
    - any other command that names no gh.
    Leading reserved words (RESERVED) are skipped first, and a command made
    only of closers (CLOSERS) is no command, both matched on the source, so
    a quoted 'if' is still the command.
    A command fed by a pipe or an input redirection must also be from
    DATA_COMMANDS, or a gh subcommand that takes no body (NO_TEXT_VERBS),
    since any other may run or post what it reads. When that input may reach a group, every command
    must be from DATA_COMMANDS, gh included (see _commands). Anything
    _commands cannot read blocks.
    """
    read = _commands(command)
    if read is None:
        return NOT_ALLOWED
    commands, grouped = read
    for words, fed in commands:
        while words and words[0][1] in RESERVED:
            words = words[1:]
        if all(source in CLOSERS for _, source in words):
            continue
        names = [text.lstrip("=").rsplit("/", 1)[-1] for text, _ in words]
        source = " ".join(source for _, source in words)
        if grouped and names[0] not in DATA_COMMANDS:
            return GROUPED
        if fed and names[0] not in DATA_COMMANDS:
            plain = _words(source)
            args = _gh_args(plain) if plain and plain[0] == ("gh", False) else []
            if len(args) < 2 or args[1][0] not in NO_TEXT_VERBS.get(args[0][0], ()):
                return _fed_blocker(names[0])
        if GH_TEXT.search(source) and "gh" not in names:
            if names[0] not in DATA_COMMANDS:
                return NOT_ALLOWED
        elif "gh" in names:
            plain = _words(source)
            if not plain or plain[0] != ("gh", False):
                return NOT_ALLOWED
            if POST_WORDS.search(" ".join(text for text, _ in plain)) and _read_gh(plain, cwd):
                return NOT_ALLOWED
    return None


def _posts_nothing(command, cwd):
    """True when the shell provably runs no gh post in this command (see
    _blocker)."""
    return _blocker(command, cwd) is None


def gh_bodies(command, cwd):
    """[(where, text or Unreadable)] for the post a Bash command makes.

    Nothing when the command mentions no gh post verb, or runs no gh post
    (see _posts_nothing). Otherwise the command must be one of the accepted
    forms (see ACCEPTED), or the post is reported unreadable.
    """
    if not POST_WORDS.search(command) or runs_only_prose(command):
        return []
    words = _words(command.strip())
    if words and words[0] == ("gh", False):
        return _read_gh(words, cwd)
    blocker = _blocker(command, cwd)
    return [] if blocker is None else [("gh", blocker)]


def _read_gh(words, cwd):
    """[(where, text or Unreadable)] for a gh command given as plain words,
    words[0] being gh: the bodies it posts, or NOT_ALLOWED when its shape is
    not one the hook reads."""
    args = _gh_args(words)
    if len(args) >= 2 and args[1][0] in NO_TEXT_VERBS.get(args[0][0], ()):
        return []
    if len(args) < 2 or args[1][0] not in GH_VERBS.get(args[0][0], {}):
        return [("gh", NOT_ALLOWED)]
    noun, verb = args[0][0], args[1][0]
    flags, values = GH_VERBS[noun][verb], SHORT_VALUES[noun][verb]
    long_values = LONG_FLAGS[noun][verb][0] | COMMON_LONG[0]
    long_bools = LONG_FLAGS[noun][verb][1] | COMMON_LONG[1]
    long_sources, short_sources = BODY_SOURCES[noun].get(verb, NO_SOURCES)
    where = f"gh {noun} {verb}"
    found = []
    i = 2
    while i < len(args):
        arg = args[i][0]
        name = arg[2:].split("=", 1)[0]
        if arg.startswith("--") and "--" + name not in flags:
            if name in long_sources:
                return [(where, NOT_ALLOWED)]
            if name in long_values:
                i += 1 if "=" in arg else 2
                continue
            if name in long_bools:
                i += 1
                continue
            return [(where, NOT_ALLOWED)]
        flag, value, i = _body_flag(args, i, flags, values, short_sources)
        if flag == SOURCE:
            return [(where, NOT_ALLOWED)]
        if flag is None or value is None:
            continue
        text, _ = value
        if flag in ("--body-file", "-F"):
            if text == "-":
                found.append((f"{where} {flag} -", FROM_STDIN))
                continue
            # No expanduser: bash leaves a quoted `~` as it is, and gh opens
            # the path literally.
            target = pathlib.Path(text)
            if not target.is_absolute():
                target = pathlib.Path(cwd or ".") / target
            try:
                found.append((f"{where} {flag} {text}", target.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, ValueError):  # ValueError: a NUL byte
                found.append((f"{where} {flag} {text}", Unreadable(
                    f"{text} could not be read. " + ACCEPTED)))
        else:
            found.append((f"{where} {flag}", text))
    return found


def posts_in(payload, host):
    """[(where, text or Unreadable)] this tool call would post."""
    if host == "cursor":
        if "command" in payload and "tool_name" not in payload:
            return gh_bodies(payload.get("command") or "", payload.get("cwd"))
        server = payload.get("mcp_server_name") or ""
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except ValueError:
                tool_input = {}
        return body_fields(tool_input) if "github" in server.lower() else []
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if GITHUB_MCP.match(tool):
        return body_fields(tool_input)
    if tool == "Bash" and isinstance(tool_input, dict):
        return gh_bodies(tool_input.get("command") or "", payload.get("cwd"))
    return []


def hook_post(raw, host):
    """(exit code, stdout, stderr) for one posting-hook call."""
    allow = (0, '{"permission":"allow"}\n' if host == "cursor" else "", "")
    try:
        payload = json.loads(raw)
    except ValueError:
        return allow
    if not isinstance(payload, dict):
        return allow
    problems = []
    for where, text in posts_in(payload, host):
        if isinstance(text, Unreadable):
            problems.append(f"{where}: {text.why}")
            continue
        ok, reason = verify_post(text)
        if not ok:
            problems.append(f"{where}: {reason}")
    if not problems:
        return allow
    message = (
        "prose: blocked, because this post does not end with a valid prose footer.\n"
        + "".join(f"  - {p}\n" for p in problems)
        + "Run the first call, which prints the rules and a pass token; do the prose pass "
        "over the text; then sign exactly the final text and post what it prints, unedited:\n"
        f"  {_prose_command()} sign --goals '<reader goals>'\n"
        f"  {_prose_command()} sign --pass <token> < body.md > signed.md\n"
    )
    if host == "cursor":
        flat = message.replace("\n", " ").strip()
        return 0, json.dumps({"permission": "deny", "user_message": flat, "agent_message": flat}) + "\n", ""
    return 2, "", message


# ---------------------------------------------------------------------------
# The pass token
# ---------------------------------------------------------------------------

# The exit status of a first call: it printed the rules and a pass token, and
# signed nothing. Errors exit 2.
PASS_ISSUED = 4
# A token signs once, within this many seconds of being issued.
PASS_LIFETIME = 2 * 60 * 60
# A session's first-call mark is deleted this long after it was last written.
SESSION_LIFETIME = 30 * 24 * 60 * 60
PASS_TOKEN = re.compile(r"[0-9a-f]{16}")
# Claude Code sets this for the commands its Bash tool runs; it equals the
# session_id in a hook's payload.
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def user_state_dir():
    """prose's directory in the user's state home. It holds the session
    marks, and the tokens of a call run outside any repository."""
    base = os.environ.get("XDG_STATE_HOME", "")
    if not os.path.isabs(base):
        base = os.path.join(os.path.expanduser("~"), ".local", "state")
    return pathlib.Path(base) / "prose"


def pass_dir(root=None):
    """Where the pass tokens live: prose/passes in the repository's git
    directory, which is never committed and goes with the clone; outside a
    repository, in the user's state home (DECISIONS: The rules are on screen
    before a signature)."""
    try:
        found = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root or ".",
                               capture_output=True, text=True, check=False)
    except OSError:
        found = None
    if found is not None and found.returncode == 0 and found.stdout.strip():
        return pathlib.Path(root or ".").resolve() / found.stdout.strip() / "prose" / "passes"
    return user_state_dir() / "passes"


def _private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _prune(directory, lifetime, now):
    """Delete the files in directory last written more than lifetime ago."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if now - entry.stat().st_mtime > lifetime:
                entry.unlink()
        except OSError:
            pass


def session_mark(session):
    """The file whose presence says a first call ran in this session."""
    name = session if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session) \
        else hashlib.sha256(session.encode("utf-8", TEXT_ERRORS)).hexdigest()
    return user_state_dir() / "sessions" / name


def mark_session(session, now=None):
    """Record that a first call ran in this session, which opens the gate."""
    if not session:
        return
    now = time.time() if now is None else now
    sessions = _private_dir(user_state_dir() / "sessions")
    _prune(sessions, SESSION_LIFETIME, now)
    session_mark(session).touch()


# What each kind of token signs, for the refusal when it is used for the other.
KINDS = {"check": "a commit", "sign": "a post"}


def issue_pass(goals, kind, session, root=None, rules=()):
    """A new token for these goals and this command ("check" or "sign"),
    recorded so one signing call of that command can spend it. rules are
    check's per-file GoalRules. With a session id, also marks the session."""
    now = time.time()
    passes = _private_dir(pass_dir(root))
    _prune(passes, PASS_LIFETIME, now)
    token = secrets.token_hex(8)
    # Written whole under another name, then renamed: a concurrent redeem
    # never reads half a token. Its name has no token's shape, so a redeem
    # never matches it.
    draft = passes / f".{token}.{os.getpid()}"
    with open(draft, "x", encoding="utf-8") as handle:
        json.dump({"goals": goals, "kind": kind, "issued": now,
                   "files": _rule_record(rules)}, handle)
    os.replace(draft, passes / token)
    mark_session(session, now)
    return token


AGAIN = "Run the command again with --goals in place of --pass; that prints the rules and a new token."


def _rule_record(rules):
    """GoalRules as a token records them: [pattern, [goal, ...]] each,
    sorted, since which rule a file gets does not depend on their order."""
    return sorted([rule.pattern, list(rule.goals)] for rule in rules)


def redeem_pass(token, goals, kind, root=None, rules=()):
    """(goals, GoalRules) this token was issued for. Refused when the token is
    unknown, spent, expired, or was issued for other goals or rules or the
    other command. It stays unspent."""
    path = pass_dir(root) / token if PASS_TOKEN.fullmatch(token) else None
    try:
        record = json.loads(path.read_text(encoding="utf-8")) if path else None
    except FileNotFoundError:
        record = None
    except (OSError, ValueError) as error:
        raise Refused(f"could not read pass token {token}: {error}")
    # A token issued before per-file goals has no "files"; it records none.
    files = record.get("files", []) if isinstance(record, dict) else None
    if not isinstance(record, dict) or not isinstance(record.get("goals"), list) \
            or not isinstance(record.get("issued"), (int, float)) \
            or not isinstance(files, list) \
            or not all(isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], str)
                       and isinstance(entry[1], list) for entry in files):
        raise Refused(f"pass token {token} is unknown or already used; each token signs once. {AGAIN}")
    if record.get("kind") != kind:
        raise Refused(f"pass token {token} was issued for {KINDS.get(record.get('kind'), 'another text')}, "
                      f"not {KINDS[kind]}. Each text gets its own first call, with the goals of its "
                      f"own reader. {AGAIN}")
    if time.time() - record["issued"] > PASS_LIFETIME:
        path.unlink(missing_ok=True)
        raise Refused(f"pass token {token} has expired; a token lasts "
                      f"{PASS_LIFETIME // 3600} hours. {AGAIN}")
    if goals and goals != record["goals"]:
        raise Refused(f"these goals differ from the ones pass token {token} was issued for: "
                      + "; ".join(record["goals"])
                      + ". Pass the same goals, or none. To change them, run the command "
                      "again with the new --goals in place of --pass.")
    if rules and _rule_record(rules) != sorted(files):
        raise Refused(f"these per-file reader goals differ from the ones pass token {token} was "
                      "issued for. Pass the same --goals-for and --goals-file, or none. To change "
                      "them, run the command again with them in place of --pass.")
    return record["goals"], [GoalRule(pattern, tuple(goals), "the first call")
                             for pattern, goals in files]


def spend_pass(token, root=None):
    """Delete the token, so it cannot sign again. Refused when another call
    spent it first."""
    try:
        (pass_dir(root) / token).unlink()
    except FileNotFoundError:
        raise Refused(f"pass token {token} is unknown or already used; each token signs once. {AGAIN}")


def print_pass(token, next_commands, stream=None):
    print(f"\nPass token: {token}. It signs once, within {PASS_LIFETIME // 3600} hours.\n",
          file=stream)
    print("Do the pass on the draft by the rules above. Then sign the final text; when it holds",
          file=stream)
    print("a changed comment, doc passage or post, this first prints a cold-read brief (step 5 of",
          file=stream)
    print("the pass):\n", file=stream)
    for command in next_commands:
        print(f"  {command}", file=stream)
    print(file=stream)


def _prose_command():
    return f"python3 {shlex.quote(str(INVOKED))}"


def next_check(token, message_file, amend, repo, report="", dispositions=""):
    words = ["check", "-F", message_file] + (["--amend"] if amend else []) \
        + (["--repo", repo] if repo != "." else []) + ["--pass", token] \
        + (["--cold-read", report] if report else []) \
        + (["--dispositions", dispositions] if dispositions else [])
    command = f"{_prose_command()} {' '.join(shlex.quote(w) for w in words)}"
    return command + ("   (the final message on stdin)" if message_file == "-" else "")


def next_sign(token, report="", dispositions=""):
    cold = (f" --cold-read {shlex.quote(report)}" if report else "") \
        + (f" --dispositions {shlex.quote(dispositions)}" if dispositions else "")
    return (f"{_prose_command()} sign --pass {token}{cold} < body.md > signed.md   "
            "(body.md: the final text)")


# ---------------------------------------------------------------------------
# The cold read
# ---------------------------------------------------------------------------

# The brief a cold reader gets: its only copy (DECISIONS: A cold read before
# signing).
COLD_READ = HERE.parent / "cold-read.md"
# The exit status of a signing call that printed a cold-read brief and signed
# nothing. The token stays unspent.
COLD_READ_NEEDED = 5
# Where the printed command tells the agent to save the cold reader's report,
# and its answer to each finding.
REPORT_FILE = "cold-read.txt"
DISPOSITIONS_FILE = "dispositions.txt"


class ColdItem(NamedTuple):
    """One text in a cold-read brief: where the reader finds it, its reader's
    goals, the file it is in ("" for a post), the text itself when it is in
    no file, and its (first, last) line pairs in the file (none for a post)."""
    where: str
    goals: tuple
    path: str = ""
    text: str = ""
    spans: tuple = ()


def _nonblank(text):
    return [line for line in text.replace("\r", "\n").split("\n") if line.strip()]


def _lines(span):
    first, last = span
    return f"line {first}" if first == last else f"lines {first}-{last}"


def _span_list(spans):
    return ", ".join(f"{first}" if first == last else f"{first}-{last}" for first, last in spans)


def cold_items(assigned):
    """Each changed comment block and doc passage the listing holds, as the
    cold reader takes them. The commit message is not read cold (Adam,
    2026-10-13), and a doc git diffs as binary has no passage to name."""
    found = []
    for item, rule in assigned:
        if item.path is None or item.deleted or not item.spans:
            continue
        _, _, goals = _goals_source(item, rule)
        if kind_of(item.path) == "comment":
            for span in item.spans:
                found.append(ColdItem(f"A code comment: {item.path}, {_lines(span)}, and the "
                                      "code it sits on.", tuple(goals), item.path, spans=(span,)))
        else:
            found.append(ColdItem(f"A doc passage: {item.path}, the changed lines "
                                  f"{_span_list(item.spans)}, each read in its section.",
                                  tuple(goals), item.path, spans=item.spans))
    return found


def cold_post(text, goals):
    """The post as a cold-read item."""
    body, _ = split_footer(text)
    return [ColdItem("The post below.", tuple(goals), "", body)]


def cold_read_header(token):
    """The line a cold reader's report starts with, binding it to one pass."""
    return f"cold-read {token}"


def dispositions_header(token):
    """The line a dispositions file starts with, binding it to the same pass."""
    return f"dispositions {token}"


def cold_read_brief(token, items, root=None):
    """cold-read.md, then the line the report starts with, then the items.
    root is the repository that the items' paths are relative to."""
    try:
        brief = COLD_READ.read_bytes().decode("utf-8").strip("\n")
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(f"cannot read the cold-read brief {COLD_READ}: {error}")
    lines = [brief, "", f"  {cold_read_header(token)}", ""]
    if root is not None:
        lines += [f"The files named below are in {pathlib.Path(root).resolve()}.", ""]
    lines += ["Items:"]
    for number, item in enumerate(items, start=1):
        lines += ["", f"{number}. {item.where}", "   Its reader's goals, most probable first:"]
        lines += [f"   - {goal}" for goal in item.goals]
        if item.text:
            lines += ["", "   ----"]
            lines += [f"   {line}".rstrip() for line in item.text.strip("\n").split("\n")]
            lines += ["   ----"]
    return "\n".join(lines)


def print_cold_read(token, items, next_command, stream=None, root=None):
    """Why nothing was signed, what to do, and the brief, between marker lines
    so the agent can pass it on unchanged."""
    brief = cold_read_brief(token, items, root)
    print(f"prose: {len(items)} text(s) here need a cold read before signing (step 5 of the "
          "pass). Nothing is signed, and the token is kept.\n", file=stream)
    print("Give a new agent, one that has not seen this conversation, everything between the "
          f"=== lines, unchanged and with nothing added. Save its report to {REPORT_FILE}, "
          "outside the commit. Fix the places it names, and restage. Then answer every finding "
          f"in {DISPOSITIONS_FILE}: its first line '{dispositions_header(token)}', then one "
          "line per finding, '<n>. fixed' once you changed the item it is in, or "
          "'<n>. kept (asked): <why>' once a person chose to keep it. Answer every item's "
          "understood line there too: 'Item <n>: matches' when it says what you meant, "
          "'Item <n>: fixed' once you changed the item so that it reads as you meant, or "
          "'Item <n>: kept (asked): <why>' once a person chose to keep it. Then run:\n",
          file=stream)
    print(f"  {next_command}\n", file=stream)
    print("=== cold-read brief ===", file=stream)
    print(brief, file=stream)
    print("=== end cold-read brief ===", file=stream)


# What a report and a dispositions file must look like, for their refusals.
REPORT_FORM = ("After its first line, a report holds only findings, each 'Finding <n>, item "
               "<item>, <stopped, reread or guessed>: «<the exact words>» <what was guessed or "
               "missing>', numbered from 1, with any more of it on indented lines below; "
               "'Item <item>: read straight through.' lines; and 'Item <item>, understood: "
               "<what the item says>' lines. Every item gets findings or the straight-through "
               "line, never both, and exactly one understood line. Ask the cold reader for its "
               "report in that form; don't reword it yourself.")
DISPOSITIONS_FORM = ("After its first line, a dispositions file holds one line per finding: "
                     "'<n>. fixed', or '<n>. kept (asked): <the reason, on one line>' once a "
                     "person chose to keep it; and one line per item, answering its understood "
                     "line: 'Item <n>: matches', 'Item <n>: fixed', or 'Item <n>: kept (asked): "
                     "<the reason, on one line>' once a person chose to keep it.")
FINDING = re.compile(r"Finding ([0-9]+), item ([0-9]+), (stopped|reread|guessed): "
                     r"«([^«»]*)»(.*)")
STRAIGHT = re.compile(r"Item ([0-9]+): read straight through\.?")
UNDERSTOOD = re.compile(r"Item ([0-9]+), understood: (.*\S.*)")
# kept without "(asked)" is read, so that its refusal can name the finding.
DISPOSITION = re.compile(r"([0-9]+)\. (?:(fixed)|kept( \(asked\))?:(.*))")
# The answer to an item's understood line. kept without "(asked)" is read too,
# so that its refusal can name the line.
UNDERSTOOD_ANSWER = re.compile(r"Item ([0-9]+): (?:(matches)|(fixed)|kept( \(asked\))?:(.*))")


class Finding(NamedTuple):
    number: int
    item: int
    quote: str
    missing: str


def item_changed(old, new, spans):
    """Whether an item differs in new from old, the text when its brief was
    printed: a line of it changed or removed, or a line added inside it or
    directly above or below it. spans are its (first, last) line pairs in
    old; with none, the whole text is the item, as for a post (DECISIONS:
    Every cold-read finding is answered before signing)."""
    if not spans:
        return old != new
    # Lines as git counts them, so the spans' numbers hold. No autojunk: it
    # would treat a doc's many blank lines as junk and report them changed.
    matcher = difflib.SequenceMatcher(None, old.split("\n"), new.split("\n"), autojunk=False)
    for tag, start, end, _, _ in matcher.get_opcodes():
        for first, last in spans:
            # start and end index old's lines from 0; an insert has start == end.
            if tag == "insert" and first - 1 <= start <= last:
                return True
            if tag in ("replace", "delete") and start < last and end >= first:
                return True
    return False


def _read_text(path, what):
    try:
        # utf-8-sig: an editor's byte order mark is not part of the first line.
        return pathlib.Path(path).read_bytes().decode("utf-8-sig", errors=TEXT_ERRORS)
    except OSError as error:
        raise Refused(f"cannot read the {what} {path}: {error.strerror or error}")


KEPT = "Nothing is signed, and the token is kept."


class ColdReport(NamedTuple):
    """A cold reader's report: its findings, and the text of each item's
    understood line, {item number: text}."""
    findings: list
    understood: dict


def read_cold_report(path, token, count):
    """The ColdReport at path, for a brief of count items. Refused unless its
    first non-blank line is the brief's header, every other line is in the
    brief's form (REPORT_FORM), and every item has one understood line."""
    lines = _nonblank(_read_text(path, "cold-read report"))
    header = cold_read_header(token)
    if not lines or lines[0].strip() != header:
        raise Refused(f"the cold-read report {path} does not start with '{header}', the line the "
                      f"brief asks the cold reader to write first. {KEPT}")
    if len(lines) < 2:
        raise Refused(f"the cold-read report {path} holds only its first line, and no report. "
                      f"{KEPT}")
    findings, straight, understood, last = [], [], [], None

    def refuse(problem):
        raise Refused(f"the cold-read report {path} {problem}. {REPORT_FORM} {KEPT}")

    for line in lines[1:]:
        found = FINDING.fullmatch(line.strip())
        through = STRAIGHT.fullmatch(line.strip())
        saw = UNDERSTOOD.fullmatch(line.strip())
        if found:
            number, item, _, quote, missing = found.groups()
            findings.append(Finding(int(number), int(item), quote, missing.strip()))
            last = "finding"
        elif through:
            straight.append(int(through.group(1)))
            last = None
        elif saw:
            understood.append([int(saw.group(1)), saw.group(2).strip()])
            last = "understood"
        elif line[:1].isspace() and last == "finding":
            previous = findings[-1]
            findings[-1] = previous._replace(missing=f"{previous.missing} {line.strip()}".strip())
        elif line[:1].isspace() and last == "understood":
            understood[-1][1] = f"{understood[-1][1]} {line.strip()}".strip()
        else:
            refuse(f"has a line prose cannot read: {line.strip()!r}")
    for index, finding in enumerate(findings, start=1):
        if finding.number != index:
            refuse(f"numbers finding {index} as {finding.number}; findings are numbered "
                   "from 1, in order")
        if not 1 <= finding.item <= count:
            refuse(f"puts finding {index} in item {finding.item}, but the brief has items 1 "
                   f"to {count}")
        if not finding.quote.strip():
            refuse(f"quotes no words in finding {index}")
        if not finding.missing:
            refuse(f"does not say, in finding {index}, what was guessed or missing")
    for item in range(1, count + 1):
        times = straight.count(item)
        with_findings = any(finding.item == item for finding in findings)
        if times > 1 or (times and with_findings):
            refuse(f"says item {item} was read straight through "
                   + ("twice" if times > 1 else "and also reports findings in it"))
        if not times and not with_findings:
            refuse(f"says nothing about item {item}")
    for item in straight + [item for item, _ in understood]:
        if not 1 <= item <= count:
            refuse(f"names item {item}, but the brief has items 1 to {count}")
    said = {}
    for item, text in understood:
        if item in said:
            refuse(f"says what it understood of item {item} twice")
        said[item] = text
    for item in range(1, count + 1):
        if item not in said:
            refuse(f"does not say what it understood of item {item}: every item gets one "
                   f"'Item {item}, understood: <what the item says>' line, whether it has "
                   "findings or was read straight through")
    return ColdReport(findings, said)


class Kept(NamedTuple):
    """A finding's answer when it was kept: the reason, and whether the
    dispositions file says a person was asked."""
    reason: str
    asked: bool


def read_dispositions(path, token, findings, items):
    """({finding number: None for fixed, or Kept}, {item number: "matches",
    "fixed" or Kept}): an answer to each finding, and to the understood line
    of each item number in items. Refused unless the file at path starts with this token's
    dispositions header and answers each of them exactly once."""
    lines = _nonblank(_read_text(path, "dispositions file"))
    header = dispositions_header(token)
    if not lines or lines[0].strip() != header:
        raise Refused(f"the dispositions file {path} does not start with '{header}', which "
                      f"binds it to this pass's cold read. {KEPT}")
    answers, numbers = {}, {finding.number for finding in findings}
    understood, wanted = {}, set(items)
    for line in lines[1:]:
        saw = UNDERSTOOD_ANSWER.fullmatch(line.strip())
        if saw:
            item, matches, fixed, asked, reason = (int(saw.group(1)), saw.group(2),
                                                   saw.group(3), saw.group(4), saw.group(5))
            if item not in wanted:
                raise Refused(f"the dispositions file {path} answers the understood line of "
                              f"item {item}, which the report does not have. {KEPT}")
            if item in understood:
                raise Refused(f"the dispositions file {path} answers the understood line of "
                              f"item {item} twice. {KEPT}")
            if not matches and not fixed and not reason.strip():
                raise Refused(f"the dispositions file {path} keeps the understood line of item "
                              f"{item} without a reason; write it after 'kept (asked):'. {KEPT}")
            understood[item] = matches or fixed or Kept(reason.strip(), bool(asked))
            continue
        found = DISPOSITION.fullmatch(line.strip())
        if not found:
            raise Refused(f"the dispositions file {path} has a line prose cannot read: "
                          f"{line.strip()!r}. {DISPOSITIONS_FORM} {KEPT}")
        number, fixed, asked, reason = (int(found.group(1)), found.group(2), found.group(3),
                                        found.group(4))
        if number not in numbers:
            raise Refused(f"the dispositions file {path} answers finding {number}, which the "
                          f"report does not have. {KEPT}")
        if number in answers:
            raise Refused(f"the dispositions file {path} answers finding {number} twice. {KEPT}")
        if not fixed and not reason.strip():
            raise Refused(f"the dispositions file {path} keeps finding {number} without a "
                          f"reason; write it after 'kept (asked):'. {KEPT}")
        answers[number] = None if fixed else Kept(reason.strip(), bool(asked))
    missing = sorted(numbers - set(answers))
    if missing:
        raise Refused(f"the dispositions file {path} does not answer finding"
                      f"{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))}; every "
                      f"finding is answered once, fixed or kept. {KEPT}")
    missing = sorted(wanted - set(understood))
    if missing:
        raise Refused(f"the dispositions file {path} does not answer the understood line of "
                      f"item{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))}; "
                      "every item's understood line is answered once: 'Item <n>: matches' when "
                      "it says what you meant, 'Item <n>: fixed' once you changed the item, or "
                      f"'Item <n>: kept (asked): <why>'. {KEPT}")
    return answers, understood


def check_cold_read(token, record, report, dispositions, current):
    """Refused unless the report answers the brief recorded for this token;
    every finding and every item's understood line has a disposition; each
    one marked fixed is in an item that has changed since the brief; and
    each one kept says a person was asked.
    current(path) gives a file's text as it is signed; a post's path is "",
    and current gives the post's text. A ColdResult."""
    brief = record.get("cold")
    if not brief:
        raise Refused(f"no cold-read brief was printed for pass token {token}, so there is no "
                      "report to check. Run the signing call without --cold-read to print one. "
                      + KEPT)
    paths, texts, spans = brief["items"], brief["texts"], brief["spans"]
    findings, understood = read_cold_report(report, token, len(paths))
    if not dispositions:
        raise Refused(f"the cold-read report has {len(findings)} finding(s) and "
                      f"{len(understood)} understood line(s), and each needs an answer: pass "
                      f"--dispositions <file>. {DISPOSITIONS_FORM} Its first line is "
                      f"'{dispositions_header(token)}'. {KEPT}")
    answers, said = read_dispositions(dispositions, token, findings, understood)
    now = {}

    def unchanged(item):
        path = paths[item - 1]
        if path not in now:
            now[path] = current(path)
        return not item_changed(texts[path], now[path], spans[item - 1])

    for finding in findings:
        if answers[finding.number] is None and unchanged(finding.item):
            raise Refused(f"finding {finding.number} is marked fixed, but item {finding.item}, in "
                          f"{paths[finding.item - 1] or 'the post'}, has not changed since the "
                          f"brief was printed. Fix it, or keep it with a reason. {KEPT}")
    for item, answer in sorted(said.items()):
        if answer == "fixed" and unchanged(item):
            raise Refused(f"the understood line of item {item} is marked fixed, but item {item}, "
                          f"in {paths[item - 1] or 'the post'}, has not changed since the brief "
                          f"was printed. Fix it, or keep it with a reason. {KEPT}")
    kept = [finding for finding in findings if answers[finding.number] is not None]
    unasked = [finding for finding in kept if not answers[finding.number].asked]
    kept_items = [item for item, answer in sorted(said.items()) if isinstance(answer, Kept)]
    unasked_items = [item for item in kept_items if not said[item].asked]
    if unasked or unasked_items:
        raise Refused(unasked_refusal(token, unasked, paths, answers, report, dispositions,
                                      [(item, understood[item], said[item])
                                       for item in unasked_items]))
    return ColdResult(len(findings) - len(kept), len(kept), len(said),
                      sum(answer == "fixed" for answer in said.values()), len(kept_items))


class ColdResult(NamedTuple):
    """A checked cold read: how many findings were fixed and how many kept;
    how many items it covered, and how many of their understood lines were
    fixed and how many kept."""
    fixed: int
    kept: int
    items: int
    understood_fixed: int
    understood_kept: int


def unasked_refusal(token, unasked, paths, answers, report, dispositions, items=()):
    """The refusal of findings and understood lines kept without a person
    being asked: each one, what to ask, and, for an agent that cannot ask,
    what to hand back (DECISIONS: Every cold-read finding is answered before
    signing). items holds (item number, understood line, Kept) for each
    understood line kept without a person asked."""
    kinds = [f"{count} {kind}(s)" for count, kind in ((len(unasked), "finding"),
                                                      (len(items), "understood line")) if count]
    lines = [f"{' and '.join(kinds)} are kept, and no person was asked about them. Nothing "
             f"is signed, and the token is kept: {token}, unspent, lasts {PASS_LIFETIME // 3600} "
             "hours from its first call.", ""]
    for finding in unasked:
        lines += [f"Finding {finding.number}, in {paths[finding.item - 1] or 'the post'}: "
                  f"«{finding.quote}»",
                  f"  The cold reader: {finding.missing}",
                  f"  Kept, because: {answers[finding.number].reason}"]
    for item, line, answer in items:
        lines += [f"Item {item}, in {paths[item - 1] or 'the post'}, understood: {line}",
                  f"  Kept, because: {answer.reason}"]
    lines += ["", "Ask a person about each, one question per finding or understood line, with "
              "two options: \"Keep as is\" makes its line '<n>. kept (asked): <reason>' (for an "
              "understood line, 'Item <n>: kept (asked): <reason>'); \"Fix it\" means rewrite "
              "the passage (and restage it, for a commit) and make its line '<n>. fixed' (or "
              "'Item <n>: fixed'). Then run the signing call again.",
              "If you cannot ask (a subagent, a background job, no picker), don't sign and don't "
              "commit: leave the change staged, and put this message in your result for "
              "whoever holds it, with the report "
              f"{pathlib.Path(report).resolve()}, the dispositions file "
              f"{pathlib.Path(dispositions).resolve()} and the token."]
    return "\n".join(lines)


def record_brief(token, items, texts, root=None):
    """Add the brief just printed to the token's record: each item's file ("" for
    a post) and line spans, and each file's text as the cold reader was given
    it, which a fixed finding's item is compared with. A brief printed again
    replaces it."""
    path = pass_dir(root) / token
    record = json.loads(path.read_text(encoding="utf-8"))
    record["cold"] = {"items": [item.path for item in items], "texts": texts,
                      "spans": [[list(span) for span in item.spans] for item in items]}
    draft = path.parent / f".{token}.{os.getpid()}"
    with open(draft, "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    os.replace(draft, path)


def staged_text(path, root):
    """The staged text of the file at path, or "" when none is staged."""
    try:
        return git(["show", f":0:{path}"], root)
    except Refused:
        return ""


def refuse_unbriefed(cold, record):
    """Refused when a file with a changed comment or doc passage now was in
    none of the recorded brief's items: it was staged after the brief, and no
    cold reader saw it. Fixes inside the files the brief named are allowed,
    since each token takes one cold read. A record with no brief is left to
    check_cold_read's refusal."""
    brief = record.get("cold")
    if not brief:
        return
    unread = sorted({item.path for item in cold} - set(brief["items"]))
    if unread:
        raise Refused(f"{', '.join(unread)} {'has' if len(unread) == 1 else 'have'} a changed "
                      "comment or doc passage that the cold-read brief did not name, so no cold "
                      "reader saw it. Run the signing call without --cold-read to print a new "
                      "brief that covers it, and pass that brief's report. " + KEPT)


def pass_record(token, root=None):
    """The record of a token redeem_pass has already accepted."""
    return json.loads((pass_dir(root) / token).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The first-write gate
# ---------------------------------------------------------------------------

# The file-writing tools. The gate blocks a session's first call to any of
# them, whatever the file (Adam, 2026-09-30).
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}


def gated_call(payload):
    """What this tool call writes that the gate stops, such as "this Write
    of README.md", or None: any file write, a gh post, or a GitHub MCP call
    with a body."""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        return "this gh post" if gh_bodies(command, payload.get("cwd")) else None
    if GITHUB_MCP.match(tool):
        return f"this post through {tool}" if body_fields(tool_input) else None
    if tool in FILE_TOOLS:
        path = tool_input.get(FILE_TOOLS[tool])
        return f"this {tool} of {path}" if isinstance(path, str) and path.strip() else f"this {tool}"
    return None


def hook_gate(raw):
    """(exit code, message) for one gate call: 2 and why, to block a
    session's first file write or post before a first call has run in it;
    otherwise 0. Any failure of the gate's own allows the call."""
    try:
        payload = json.loads(raw)
        session = payload.get("session_id") if isinstance(payload, dict) else None
        if not isinstance(session, str) or not session:
            return 0, ""
        # The mark first: a marked session does nothing else.
        try:
            session_mark(session).stat()
            return 0, ""
        except FileNotFoundError:
            pass
        what = gated_call(payload)
        if not what:
            return 0, ""
    except Exception:
        return 0, ""
    return 2, (
        f"prose: blocked {what}, this session's first file write or post, because prose's "
        "first call has not run in this session. Run it now, with the reasons a reader opens "
        "the text you are writing, most probable first. It prints the rules to write by:\n\n"
        f"  {_prose_command()} start --goals '<goal; goal>' --session {shlex.quote(session)}\n\n"
        "Then retry. This gate stays open for the rest of the session.\n"
    )


# ---------------------------------------------------------------------------
# Reader goals for each listed file
# ---------------------------------------------------------------------------

# The row of rules.md's reader table that gives each kind of listed file its
# default goals, named by the start of the row's first cell.
KIND_ROWS = {"comment": "Code comment", "readme": "README", "spec": "Spec", "doc": "Other doc"}


def kind_of(path):
    """The reader-table kind of a listed file: a spec, a README, another doc,
    or code, whose listed prose is its comments."""
    if not is_doc(path):
        return "comment"
    pure = pathlib.PurePosixPath(path.rstrip())
    if SPEC_DIRS & set(pure.parts[:-1]):
        return "spec"
    return "readme" if pure.name.split(".")[0].upper() == "README" else "doc"


def kind_default(kind):
    """(row label, who reads it, goals) from rules.md's reader table for this
    kind. Refused when the table has no such row: the default is printed from
    the table, so the table is its only copy."""
    want = KIND_ROWS[kind]
    lines = read_rules()[0].split("\n")
    for line, fenced in zip(lines, _fenced_lines(lines)):
        if fenced or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith(want) and parse_goals(cells[2]):
            return cells[0], cells[1], tuple(parse_goals(cells[2]))
    raise Refused(f"{RULES}: the reader table in '## The pass' has no '| {want} | <who> | "
                  f"<goal; goal> |' row, which gives the default reader goals for that kind of file")


class GoalRule(NamedTuple):
    """Reader goals for the listed files a pattern matches. where says who
    gave them: --goals-for, or the goals file and line."""
    pattern: str
    goals: tuple
    where: str


def _glob_regex(pattern):
    """(regex, directories only) for a gitignore-style pattern over
    repository-relative paths.

    `*` and `?` stay inside one path segment, `[...]` is a character class
    (`[!...]` negated), a backslash makes the next character literal, and `**` as a
    whole segment spans any number of segments. A leading `/` anchors the
    pattern at the root, as does a `/` in its middle; without one it matches
    at any depth (`*.md`). A trailing `/` means it matches directories only,
    and trailing blanks are dropped unless escaped. POSIX classes such as
    `[[:digit:]]` are not supported; `[0-9]` is."""
    body = _unpadded(pattern[1:] if pattern.startswith("/") else pattern)
    directory = body.endswith("/") and not body.endswith("\\/")
    core = body[:-1] if directory else body
    anchored = pattern.startswith("/") or "/" in core
    out = [] if anchored else ["(?:[^/]*/)*"]
    i = 0
    while i < len(core):
        char = core[i]
        if char == "\\" and i + 1 < len(core):
            out.append(re.escape(core[i + 1]))
            i += 2
            continue
        if char == "*":
            end = i
            while end < len(core) and core[end] == "*":
                end += 1
            whole = end - i >= 2 and (i == 0 or core[i - 1] == "/") \
                and (end == len(core) or core[end] == "/")
            if whole and end == len(core):
                out.append(".*")
            elif whole:
                out.append("(?:[^/]*/)*")
                end += 1
            else:
                out.append("[^/]*")
            i = end
            continue
        if char == "?":
            out.append("[^/]")
        elif char == "[":
            start = i + 1
            if core[start:start + 1] in ("!", "^"):
                start += 1
            close = core.find("]", start + 1 if core[start:start + 1] == "]" else start)
            if close == -1:
                out.append(re.escape(char))
            else:
                negated = start > i + 1
                members = core[start:close].replace("\\", "\\\\").replace("[", "\\[")
                out.append("(?!/)[" + ("^" if negated else "") + members + "]")
                i = close + 1
                continue
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out)), directory


def _unpadded(body):
    """The pattern without the trailing blanks gitignore ignores: those not
    escaped with a backslash."""
    return re.sub(r"(?<!\\)[ \t]+$", "", body)


def _literals(pattern):
    """How many characters of the pattern match only themselves: its length
    less the leading `/`, the wildcards and the character classes, with an
    escaped character counted once."""
    body = _unpadded(pattern[1:] if pattern.startswith("/") else pattern)
    body = re.sub(r"\\(.)", "x", body)
    return len(re.sub(r"\[[!^]?\]?[^\]]*\]|[*?]", "", body))


def _exact(rule, path):
    """True when the rule names this path itself, written plainly or with
    its glob characters escaped, with or without the trailing blanks that
    gitignore drops."""
    body = rule.pattern[1:] if rule.pattern.startswith("/") else rule.pattern
    return any(path in (form, re.sub(r"\\(.)", r"\1", form)) for form in (body, _unpadded(body)))


def _specificity(rule, path):
    """How specific a rule is for a path it matches: an exact path first,
    then the pattern with more literal characters."""
    return (_exact(rule, path), _literals(rule.pattern))


def matches(rule, path):
    """True when the rule names the path, or, as in gitignore, matches it or
    a directory above it. A directories-only pattern (`docs/`) matches only
    the directories above it."""
    if _exact(rule, path):
        return True
    regex, directories_only = _glob_regex(rule.pattern)
    parts = path.split("/")
    above = ["/".join(parts[:end]) for end in range(1, len(parts))]
    return any(regex.fullmatch(name) for name in above + ([] if directories_only else [path]))


def as_pattern(path):
    """A pattern that names exactly this path, as a refusal suggests it for a
    goals file: its glob characters, a colon before a blank, a leading `#`,
    `!` or blank, and a trailing blank are escaped, so the line reads back
    as this path."""
    escaped = re.sub(r"([\\*?\[]|:(?=[ \t]))", r"\\\1", path)
    escaped = re.sub(r"([ \t])$", r"\\\1", escaped)
    return "\\" + escaped if escaped[:1] in ("#", "!", " ", "\t") else escaped


def goal_rule(pattern, goals_text, where):
    """A GoalRule from one --goals-for or goals-file line; refused when the
    pattern or the goals are empty, or the pattern is a negation."""
    goals = parse_goals(goals_text)
    if not pattern.strip():
        raise Refused(f"{where}: an empty pattern. Give a path or a pattern such as 'docs/**'")
    if pattern.startswith("!"):
        raise Refused(f"{where}: '{pattern}' is a negation, which reader goals do not take. "
                      f"Give the files that need other goals a narrower pattern or their path")
    if not goals:
        raise Refused(f"{where}: no reader goals for '{pattern}'. List them, most probable "
                      f"first, separated by ';'")
    try:
        _glob_regex(pattern)
    except re.error as error:
        raise Refused(f"{where}: '{pattern}' cannot be read as a pattern ({error}). Fix it, "
                      f"or name the file by its path")
    return GoalRule(pattern, tuple(goals), where)


# The pattern runs to the first colon followed by a blank that no backslash
# escapes.
GOALS_LINE = re.compile(r"^((?:\\.|[^\\])+?):[ \t]+(\S.*)$")


def goals_file_lines(path):
    """(line number, line) for each line of a goals file that holds goals,
    stripped. Blank lines and lines starting with `#` are skipped."""
    try:
        # utf-8-sig: an editor's byte order mark is not part of the first line.
        text = pathlib.Path(path).read_bytes().decode("utf-8-sig")
    except OSError as error:
        raise Refused(f"could not read the goals file {path}: {error.strerror or error}")
    except UnicodeDecodeError as error:
        raise Refused(f"the goals file {path} is not valid UTF-8: {error}")
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if line and not line.startswith("#"):
            yield number, line


def read_goals_file(path):
    """The GoalRules in a goals file: one `pattern: goal; goal` line each,
    the pattern ending at the first colon followed by a space or tab, unless
    a backslash escapes the colon. Blank lines and lines starting with `#` are
    skipped."""
    rules = []
    for number, line in goals_file_lines(path):
        where = f"{path}:{number}"
        found = GOALS_LINE.match(line)
        if not found:
            raise Refused(f"{where}: expected 'pattern: goal; goal', got: {line}")
        rules.append(goal_rule(found.group(1), found.group(2), where))
    return rules


def text_goals(goals, goals_file, option="--goals-file"):
    """The reader goals of one text: the post `sign` is for, the text `start`
    precedes, or the message `check` signs. They come from --goals, or from a
    goals file holding what --goals would: one or more goals per line, separated by ';'. A line names no
    file, since the goals are for one text; blank and `#` lines are skipped,
    as in check's per-file goals file. Refused when both are given: goals are
    ordered, most probable first, and joining two lists would choose an order
    nobody gave. option is the file's option name, used only in the refusal."""
    if not goals_file:
        return parse_goals(goals)
    if goals.strip():
        raise Refused(f"reader goals were given twice, with --goals and {option}. Pass them "
                      "once, most probable first, with one of the two")
    found = parse_goals("\n".join(line for _, line in goals_file_lines(goals_file)))
    if not found:
        raise Refused(f"the goals file {goals_file} holds no reader goals. List the most probable "
                      f"reasons a reader opens this text, most probable first, one or more per line, "
                      f"separated by ';'")
    return found


def file_rules(goals_for, goals_file):
    """The GoalRules from the command line: each --goals-for in order, then
    the goals file's lines."""
    rules = [goal_rule(pattern, goals, "--goals-for") for pattern, goals in goals_for or ()]
    return rules + (read_goals_file(goals_file) if goals_file else [])


def assign_goals(items, rules):
    """([(item, rule or None)], [rules that match no listed file]).

    Each listed file gets the most specific rule that matches it, or None.
    Refused when two equally specific rules match one file with different
    goals: which one was meant cannot be told, and the fix is a narrower
    pattern or the file's exact path."""
    chosen, used = {}, set()
    for item in items:
        if item.path is None or item.path in chosen:
            continue
        found = [(_specificity(rule, item.path), index, rule)
                 for index, rule in enumerate(rules) if matches(rule, item.path)]
        used.update(index for _, index, _ in found)
        # A deleted doc has no reader, so no rule applies to it.
        if not found or item.deleted:
            chosen[item.path] = None
            continue
        best = max(rank for rank, _, _ in found)
        top = [rule for rank, _, rule in found if rank == best]
        if any(rule.goals != top[0].goals for rule in top):
            raise Refused(
                f"{item.path} matches equally specific reader goals that differ: "
                + "; ".join(f"'{rule.pattern}' ({rule.where})" for rule in top)
                + ". Give it its exact path, or one of them a narrower pattern")
        chosen[item.path] = top[0]
    assigned = [(item, chosen[item.path] if item.path is not None else None) for item in items]
    return assigned, [rule for index, rule in enumerate(rules) if index not in used]


def refuse_uncovered(assigned, unused=(), after_first_call=False):
    """Refused when a listed doc or spec has no reader goals. A deleted one
    has no reader, and code comments may go without: they get their kind's
    default. The refusal names the given goals that matched no listed file,
    since a typo there is the likeliest reason."""
    missing = [item.path for item, rule in assigned
               if item.path is not None and rule is None and not item.deleted
               and kind_of(item.path) != "comment"]
    if not missing:
        return
    if after_first_call:
        raise Refused(
            "these docs and specs had no reader goals when the first call ran: "
            + ", ".join(missing) + ". " + AGAIN.replace("--goals", "--goals and --goals-for"))
    suggestions = []
    for path in missing:
        label, who, goals = kind_default(kind_of(path))
        suggestions.append(f"  {as_pattern(path)}: {'; '.join(goals)}\n"
                           f"      (the default in the '{label}' row, read by {who})")
    raise Refused(
        "these docs and specs have no reader goals: " + ", ".join(missing) + ". A doc's "
        "reader is not the commit's reviewer. Name each one's goals, most probable first, "
        "with --goals-for <path or pattern> '<goal; goal>', or in a goals file passed as "
        "--goals-file <file>, one 'pattern: goal; goal' line each. The defaults for their "
        "kinds, from rules.md's reader table, as goals-file lines; adjust each to its "
        "document:\n\n" + "\n".join(suggestions) + "\n"
        + "".join(f"\n'{rule.pattern}' ({rule.where}) matches no listed file; is it a typo?"
                  for rule in unused))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

GOALS_HELP = (
    "the most probable reasons a reader opens this text, most probable first, "
    'separated by ";", e.g. --goals "review the fix; check it is safe to merge"'
)


def parse_goals(text):
    """The reader goals, in the order given. The script cannot judge them;
    requiring them makes listing them part of the command."""
    return [goal.strip() for goal in re.split(r"[;\n]", text or "") if goal.strip()]


def require_goals(goals, what):
    if not goals:
        raise Refused(
            f"no reader goals, so no {what}. List the most probable reasons a reader "
            f"opens this text, most probable first, then order and cut the text against "
            f'them and pass them: --goals "review the fix; check it is safe to merge"'
        )


def print_goals(goals, stream=None, heading="Reader goals, most probable first. Order and cut "
                                            "the text against them:"):
    print(heading + "\n", file=stream)
    for number, goal in enumerate(goals, start=1):
        print(f"  {number}. {goal}", file=stream)
    print(file=stream)


def _read_stdin():
    return sys.stdin.buffer.read().decode("utf-8", errors=TEXT_ERRORS)


def _session(args):
    return args.session or os.environ.get(SESSION_ENV, "")


def main(argv=None):
    # sign writes its input back out; surrogateescape makes those the same
    # bytes it read.
    sys.stdout.reconfigure(encoding="utf-8", errors=TEXT_ERRORS)
    parser = argparse.ArgumentParser(description="List, sign and verify prose.")
    sub = parser.add_subparsers(dest="command", required=True)
    # The first call passes --goals, and gets the rules and a pass token; the
    # signing call passes --pass <token> (DECISIONS: The rules are on screen
    # before a signature).
    # start, check and sign all take goals and mark the session; only check
    # and sign redeem a token, so start refuses --pass.
    goal_args = argparse.ArgumentParser(add_help=False)
    goal_args.add_argument("--goals", default="", help=GOALS_HELP)
    goal_args.add_argument("--session", default="",
                           help=f"the agent session to mark as having run a first call "
                                f"(default: ${SESSION_ENV})")
    passing = argparse.ArgumentParser(add_help=False, parents=[goal_args])
    passing.add_argument("--pass", dest="token", default="",
                         help="the token a first call printed: sign with it")
    passing.add_argument("--cold-read", dest="report", default="",
                         help="with --pass: the file holding the cold reader's report, which "
                              "a changed comment, doc passage or post needs")
    passing.add_argument("--dispositions", default="",
                         help="with --cold-read: the file answering each of the report's "
                              "findings, fixed or kept with a reason")
    # check's --goals-file holds per-file goals. start's and sign's holds the
    # goals of the one text each is for, so those goals can stay off the
    # command line as well.
    text_goals_file = argparse.ArgumentParser(add_help=False)
    text_goals_file.add_argument("--goals-file", default="",
                                 help="a file holding the goals --goals would, one or more per "
                                      "line, separated by ';'; blank and '#' lines are skipped")
    sub.add_parser("start", parents=[goal_args, text_goals_file],
                   help="before writing: print the goals and the rules; signs nothing")
    p_check = sub.add_parser("check", parents=[passing],
                             help="list the staged prose; first call: the rules and a pass token; "
                                  "with --pass: the trailer")
    p_check.add_argument("-F", "--message-file", required=True,
                         help="the final commit message; - reads stdin")
    p_check.add_argument("--amend", action="store_true",
                         help="list against HEAD's parent, for git commit --amend")
    p_check.add_argument("--repo", default=".")
    p_check.add_argument("--goals-for", nargs=2, action="append", default=[],
                         metavar=("PATTERN", "GOALS"),
                         help="the reader goals for each listed file PATTERN matches, as for "
                              "--goals; repeatable, and the most specific match wins")
    p_check.add_argument("--goals-file", default="",
                         help="a file of 'pattern: goal; goal' lines, read like --goals-for")
    # The message's goals, kept off the command line as start's and sign's
    # --goals-file keeps theirs. check's --goals-file holds per-file goals,
    # so the message's file has its own option.
    p_check.add_argument("--message-goals-file", default="",
                         help="in place of --goals: a file holding the message's goals, one or "
                              "more per line, separated by ';'; blank and '#' lines are skipped")
    p_staged = sub.add_parser("verify-staged", help="exit 0 when a trailer line matches the index and stdin's message")
    p_staged.add_argument("line")
    p_staged.add_argument("--repo", default=".")
    p_verify = sub.add_parser("verify-commit", help="recompute a landed commit's Prose trailer")
    p_verify.add_argument("sha")
    p_verify.add_argument("--repo", default=".")
    sub.add_parser("sign", parents=[passing, text_goals_file],
                   help="first call: the rules and a pass token; with --pass: stdin with a signed footer")
    sub.add_parser("verify-post", help="exit 0 when stdin's footer matches its text")
    p_hook = sub.add_parser("hook-post", help="the posting hook: payload on stdin")
    p_hook.add_argument("--host", default="")
    sub.add_parser("hook-gate", help="the first-write gate: payload on stdin")
    # allow_abbrev=False: an abbreviation such as --paths would make the
    # split at `--` below misread the option's value as the file.
    p_compact = sub.add_parser("compact", allow_abbrev=False,
                               help="print the brief that compacts a doc to what is current; "
                                    "with --verify, check the result",
                               epilog="Files that might refer to the doc go after --, for the "
                                      "first call and every --verify.")
    p_compact.add_argument("file")
    p_compact.add_argument("--verify", action="store_true",
                           help="check the compacted file against the copy the first call saved")
    p_compact.add_argument("--review", action="store_true",
                           help="print the brief for the reviewer who judges each removal and "
                                "rewrite against the copy the first call saved")
    p_compact.add_argument("--abandon", action="store_true",
                           help="discard a compaction started on the file, and its records, so "
                                "the commit gate treats the file as ordinary again")
    p_compact.add_argument("--reviewed", default="", metavar="REPLY",
                           help="record the review as complete: the file holding the reviewer's "
                                "reply, whose findings --dispositions answers")
    p_compact.add_argument("--dispositions", dest="compact_dispositions", default="",
                           metavar="FILE",
                           help="with --reviewed: 'Change <n>: fixed' or 'Change <n>: kept: "
                                "<reason>' for each change with a lost or false finding")
    p_compact.add_argument("--paths-from", default="", metavar="FILE",
                           help="a file listing more such paths, one per line; - reads stdin")
    p_compact.add_argument("-0", dest="nul", action="store_true",
                           help="with --paths-from: the paths are separated by NUL, as "
                                "rg -l0 and find -print0 write them")
    # Paths after `--` are split off before parsing and are the referrers:
    # argparse before Python 3.12 cannot give a positional list the paths
    # after `--` once an option such as --verify follows the file.
    argv = list(sys.argv[1:] if argv is None else argv)
    tail = []
    if argv[:1] == ["compact"] and "--" in argv:
        at = argv.index("--")
        argv, tail = argv[:at], argv[at + 1:]
        # With no file before `--`, the first path after it is the file, as
        # in `compact -- -notes.md`; it is passed after a `--` of its own.
        valued = {"--paths-from", "--reviewed", "--dispositions"}
        named = [arg for i, arg in enumerate(argv[1:], start=1)
                 if not arg.startswith("-") and argv[i - 1] not in valued]
        if not named and tail:
            argv, tail = argv + ["--", tail[0]], tail[1:]
    args = parser.parse_args(argv)
    # Referrers come only from after `--`, so a stray positional is an error
    # on every Python version.
    args.referrers = tail

    try:
        if getattr(args, "report", "") and not args.token:
            raise Refused("--cold-read goes with --pass, on the signing call")
        if getattr(args, "dispositions", "") and not getattr(args, "report", ""):
            raise Refused("--dispositions goes with --cold-read, the report its lines answer")
        if args.command == "start":
            # A warm-up before writing: the goals and the rules, and the
            # session mark that opens the gate. No token: each text still
            # gets its own first call, with its own reader's goals.
            goals = text_goals(args.goals, args.goals_file)
            require_goals(goals, "first call")
            read_rules()
            print_goals(goals)
            print_rules()
            mark_session(_session(args))
            print("\nWrite by these rules. This signs nothing: before each commit or post,")
            print("run its own first call, with the goals of that text's reader:\n")
            print(f"  A commit: {_prose_command()} check -F msg.txt --goals '<goals>' \\")
            print("              --goals-for '<doc path or pattern>' '<that doc's reader's goals>'")
            print(f"  A post:   {_prose_command()} sign --goals '<goals>'\n")
            return 0
        if args.command == "check":
            if args.message_file == "-":
                message = _read_stdin()
            else:
                # Bytes: read_text's universal newlines would hide a bare CR.
                message = pathlib.Path(args.message_file).read_bytes().decode("utf-8", errors=TEXT_ERRORS)
            goals = text_goals(args.goals, args.message_goals_file, "--message-goals-file")
            rules = file_rules(args.goals_for, args.goals_file)
            if args.token:
                goals, rules = redeem_pass(args.token, goals, "check", args.repo, rules)
            else:
                require_goals(goals, "pass token")
            # Read first: a rules file that cannot be printed, or a missing
            # result block, stops the check before it prints anything.
            read_rules()
            result_block()
            items, flags, trailer = check(message, args.repo, args.amend, bool(args.token))
            assigned, unused = assign_goals(items, rules)
            refuse_uncovered(assigned, unused, after_first_call=bool(args.token))
            compact = compactor()
            root = git(["rev-parse", "--show-toplevel"], args.repo).rstrip("\n")
            # A compaction is signed only when the bytes staged both passed
            # --verify and had their review completed with --reviewed
            # (DECISIONS: Compaction).
            pending = compact.unverified(root, args.amend, pass_dir(args.repo))

            if args.token:
                cold, result = cold_items(assigned), None
                # The cold read of a compacted file comes before its reviews,
                # so they check its fixes. While a compaction is unfinished,
                # a call without --cold-read still prints the brief; a call
                # with it, or with nothing to read cold, is refused.
                if pending and (args.report or not cold):
                    raise Refused("; ".join(pending))
                if args.report:
                    record = pass_record(args.token, args.repo)
                    refuse_unbriefed(cold, record)
                    result = check_cold_read(args.token, record,
                                             args.report, args.dispositions,
                                             lambda path: staged_text(path, args.repo))
                    understood = understood_counts(result.items, result.understood_fixed,
                                                   result.understood_kept)
                    trailer += (f"; cold read: {cold_counts(result.fixed, result.kept)}"
                                f"; understood: {understood}")
                elif cold:
                    record_brief(args.token, cold,
                                 {item.path: staged_text(item.path, args.repo) for item in cold},
                                 args.repo)
                    if pending:
                        print("prose: the signing call with --cold-read will refuse until each "
                              "of these is done; fix what the cold reader finds first, so the "
                              "review checks it:\n")
                        for line in pending:
                            print(f"  {line}")
                        print()
                    print_cold_read(args.token, cold, next_check(
                        args.token, args.message_file, args.amend, args.repo, REPORT_FILE,
                        DISPOSITIONS_FILE),
                        root=git(["rev-parse", "--show-toplevel"], args.repo).rstrip("\n"))
                    return COLD_READ_NEEDED
                # The signing call prints only the result block. It is built
                # before the token is spent, so a block that cannot be built
                # leaves the token for the same call to run again.
                block = render_result([trailer])
                spend_pass(args.token, args.repo)
                print_result(block)
                return 0
            print_goals(goals, heading=MESSAGE_GOALS)
            print_check(assigned, flags, unused,
                        "--message-goals-file" if args.message_goals_file else "--goals")
            # Every staged path, doc or not: a declaration in .gitattributes
            # makes any file current-state (DECISIONS: Compaction). The
            # triggers only advise, so a listing that fails skips them.
            try:
                staged_paths = compact.changed_paths(root, args.amend)
            except ValueError:
                staged_paths = []
            compact.print_due(compact.due(staged_paths, root), _prose_command())

            if pending:
                # With nothing in the commit to read cold, as when a compaction
                # only removed lines, the signing call prints no brief and
                # refuses.
                print("\nThe signing call can print its cold-read brief now, but signs only once each "
                      "of these is done:\n" if cold_items(assigned) else
                      "\nThe signing call will refuse until each of these is done:\n")
                for line in pending:
                    print(f"  {line}")
            print()
            print_rules()
            token = issue_pass(goals, "check", _session(args), args.repo, rules)
            print_pass(token, [next_check(token, args.message_file, args.amend, args.repo)])
            print_commit_how(args.amend, args.message_file)
            return PASS_ISSUED
        if args.command == "compact":
            compact = compactor()
            try:
                if sum(map(bool, (args.verify, args.review, args.reviewed, args.abandon))) > 1:
                    raise Refused("--verify, --review, --reviewed and --abandon are separate "
                                  "steps; run one at a time")
                if args.compact_dispositions and not args.reviewed:
                    raise Refused("--dispositions goes with --reviewed, the reply it answers")
                given = compact.Given(tuple(args.referrers), args.paths_from, args.nul)
                # A closed stdin is None; only --paths-from - needs it.
                stdin = sys.stdin.buffer if sys.stdin is not None else None
                if args.nul and not args.paths_from:
                    raise Refused("-0 goes with --paths-from, the list it separates")
                if (args.review or args.reviewed or args.abandon) and given.supplied():
                    raise Refused("--review, --reviewed and --abandon read no other files; give "
                                  "the paths to --verify")
                if args.abandon:
                    return compact.abandon(args.file, user_state_dir(), pass_dir)
                if args.reviewed:
                    return compact.reviewed(args.file, user_state_dir(), pass_dir, args.reviewed,
                                            args.compact_dispositions)
                if args.verify:
                    return compact.verify(args.file, user_state_dir(), pass_dir, given, stdin)
                if args.review:
                    return compact.review(args.file, user_state_dir(), _prose_command())
                return compact.brief(args.file, user_state_dir(), _prose_command(), given, stdin)
            except (ValueError, UnicodeDecodeError) as error:
                raise Refused(str(error))
        if args.command == "verify-staged":
            ok, reason = verify_staged(args.line, _read_stdin(), args.repo)
            print(reason)
            return 0 if ok else 1
        if args.command == "verify-commit":
            ok, reason = verify_commit(args.sha, args.repo)
            print(reason)
            return 0 if ok else 1
        if args.command == "sign":
            # stdout carries only the signed text, so a first call, which
            # signs nothing, prints to stderr and leaves stdout empty.
            goals = text_goals(args.goals, args.goals_file)
            if not args.token:
                require_goals(goals, "pass token")
                read_rules()
                print_goals(goals, sys.stderr)
                print_rules(sys.stderr)
                token = issue_pass(goals, "sign", _session(args))
                print_pass(token, [next_sign(token)], sys.stderr)
                return PASS_ISSUED
            goals, _ = redeem_pass(args.token, goals, "sign")
            text = _read_stdin()
            # Signed first, so an empty text is refused before any brief.
            signed = sign(text)
            if args.report:
                check_cold_read(args.token, pass_record(args.token), args.report,
                                args.dispositions, lambda _: split_footer(text)[0])
            else:
                cold = cold_post(text, goals)
                record_brief(args.token, cold, {"": cold[0].text})
                print_cold_read(args.token, cold,
                                next_sign(args.token, REPORT_FILE, DISPOSITIONS_FILE), sys.stderr)
                return COLD_READ_NEEDED
            spend_pass(args.token)
            print_goals(goals, sys.stderr)
            sys.stdout.write(signed)
            return 0
        if args.command == "verify-post":
            ok, reason = verify_post(_read_stdin())
            print(reason)
            return 0 if ok else 1
        if args.command == "hook-post":
            code, out, err = hook_post(_read_stdin(), args.host)
            sys.stdout.write(out)
            sys.stderr.write(err)
            return code
        if args.command == "hook-gate":
            # Its shell wrapper passes the message on only with exit 2, so
            # a crash here allows the call.
            code, message = hook_gate(_read_stdin())
            sys.stdout.write(message)
            return code
    except Refused as error:
        print(f"prose: {error}", file=sys.stderr)
        return 3 if args.command in ("verify-commit", "verify-staged") else 2
    except OSError as error:
        print(f"prose: {error}", file=sys.stderr)
        return 3 if args.command in ("verify-commit", "verify-staged") else 2
    return 2


def result_block():
    """The shared result-block script's path; refused when it is missing."""
    if not RESULT_BLOCK.is_file():
        raise Refused(
            f"the shared commit-trailer library is missing (expected {RESULT_BLOCK}); prose "
            f"must be installed as a symlink into a full shared-skills clone"
        )
    return RESULT_BLOCK


def render_result(trailer_lines):
    """The result block that ends a signing `prose check`, the only place the
    trailer is printed, as bytes. The shared script owns the block's format.
    It gets no --decisions: prose never has open decisions to report."""
    result = subprocess.run(
        ["sh", str(result_block()), "prose", "--"] + list(trailer_lines),
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise Refused(result.stderr.decode("utf-8", errors=TEXT_ERRORS).strip()
                      or f"result-block.sh exited {result.returncode}")
    return result.stdout


def print_result(block):
    sys.stdout.flush()
    sys.stdout.buffer.write(block)
    sys.stdout.flush()


MESSAGE_GOALS = ("Reader goals for the commit message, most probable first. Order and cut "
                 "the message against them; each file below has goals of its own:")


def _goals_source(item, rule, message_from="--goals"):
    """(group key, heading, goals) for a listed item: which reader goals it
    gets, and the line that names where they came from. message_from names
    the option that gave the message's goals."""
    if item.path is None:
        return ("message",), f"The commit message, read with the goals above ({message_from}):", ()
    if item.deleted:
        return ("deleted",), "Deleted, so no reader; nothing to rewrite:", ()
    if rule is None:
        kind = kind_of(item.path)
        label, who, goals = kind_default(kind)
        return (("default", kind),
                f"Reader goals by default, from the '{label}' row of rules.md's reader "
                f"table (read by {who}); --goals-for replaces them:", goals)
    if _specificity(rule, item.path)[0]:
        return ("exact", item.path), f"Reader goals for its exact path ({rule.where}):", rule.goals
    return (("pattern", rule),
            f"Reader goals from the pattern '{rule.pattern}' ({rule.where}):", rule.goals)


def print_check(assigned, flags=(), unused=(), message_from="--goals"):
    """The listing: each item under the reader goals it gets and where they
    came from, then the warnings. message_from names the option that gave
    the message's goals."""
    print(f"prose: {len(assigned)} piece(s) of prose in this commit. Do the pass over each "
          f"against the reader goals above it.")
    if any(item.path is not None and kind_of(item.path) != "comment" for item, _ in assigned):
        print("In a doc or spec, reread each changed passage inside its section, as that "
              "section's reader, before keeping it.")
    # One group per source of goals, in order of first use; each item goes
    # into the one group its own source names.
    groups = {}
    for item, rule in assigned:
        key, heading, goals = _goals_source(item, rule, message_from)
        groups.setdefault(key, (heading, goals, []))[2].append(item)
    for heading, goals, members in groups.values():
        print("\n" + heading + "\n")
        for number, goal in enumerate(goals, start=1):
            print(f"  {number}. {goal}")
        if goals:
            print()
        for item in members:
            print(f"  {item.what}" + (f"  ({item.note})" if item.note else ""))
    if unused:
        print("\nReader goals that match no listed file (a typo?):\n")
        for rule in unused:
            print(f"  '{rule.pattern}' ({rule.where})")
    if flags:
        print("\nFlags (warnings, not blocking):\n")
        for flag in flags:
            print(f"  {flag}")


def print_commit_how(amend, message_file):
    """How to commit with the trailer the signing call prints."""
    if amend:
        # The commit script makes a new commit; it cannot amend.
        print("Then amend with the Prose: line in the block it prints; never type it:\n")
        # The file the check read; stdin has none, so name what it must hold.
        named = ("<a file holding exactly the text checked>" if message_file == "-"
                 else shlex.quote(message_file))
        print(f'  git commit --amend -F {named} --trailer "<the Prose: line>"\n')
    else:
        print("Then commit through the commit script with the Prose: line in the block")
        print("it prints; never type it.\n")


if __name__ == "__main__":
    sys.exit(main())
