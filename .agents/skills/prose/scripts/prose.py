#!/usr/bin/env python3
"""prose: list the prose in a commit, mint its trailer, and sign posted text.

Signing takes two calls. The first, with --goals, prints the rules and a pass
token, signs nothing and exits 4. The second, with --pass <token>, signs.
Both calls of `check` run the repository's pre-commit hook first, if it has one.

    prose.py start --goals <goals>
        Before writing. Prints the rules and opens the gate; issues no token.
    prose.py check -F <message file, or - for stdin> --goals <goals> [--amend]
        Before a commit, first call. Lists the prose, prints the rules and a token.
    prose.py check -F <message file, or - for stdin> --pass <token> [--amend]
        Second call. Prints the Prose: trailer. --amend: before `git commit --amend`.
    prose.py sign --goals <goals>
        Before posting, first call. Prints the rules and a token; reads no stdin.
    prose.py sign --pass <token> < text > signed
        Second call. Prints stdin's text with a signed footer.
    prose.py verify-staged <trailer line>     stdin: the message (the commit script's verifier)
    prose.py verify-commit <sha>              after a commit (the commit hook)
    prose.py verify-post                      stdin: posted text
    prose.py hook-post --host <platform>      the posting hook
    prose.py hook-gate                        the first-write gate

Standard library only. Read ../DECISIONS.md before changing what is hashed:
a change here invalidates every signature already minted.
"""

import argparse
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
from typing import Callable

HERE = pathlib.Path(__file__).resolve().parent
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
TRAILER = re.compile(r"✓ ([0-9a-f]{%d}):([0-9a-f]{%d})" % (HALF, HALF))
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
    """Each doc or spec path whose content the staged change alters.

    Read from `--raw`, because the text diff gives no header to a file git
    diffs as binary (UTF-16, a NUL byte, `-diff`), and `--raw` still names
    it. A pure rename or a mode change keeps the blob and is left out; a
    deleted doc is named by its old path."""
    raw = git(["diff", "--cached", "--raw", "-z", "--no-abbrev", "-M", "--no-relative",
               "--no-color", base], root)
    fields = raw.split("\0")
    found, index = [], 0
    while index < len(fields) and fields[index].startswith(":"):
        _, _, old_blob, new_blob, status = fields[index][1:].split(" ", 4)
        paths = fields[index + 1:index + (3 if status[:1] in "RC" else 2)]
        index += 1 + len(paths)
        if old_blob == new_blob:
            continue
        path = paths[0] if status[:1] == "D" else paths[-1]
        if is_doc(path):
            found.append(path)
    return found


def prose_in(root, base, read: Callable[[str], str]):
    """([(what, note)], [flag lines]) for the prose the staged change touches.

    A listing for the pass, not what the trailer hashes: the message, each doc
    or spec file the diff touches, and each code comment it adds to or edits.
    The flags are history-language warnings on those comments. base is the
    revision the diff is against, or None for the empty tree.
    """
    scan = scanner()
    items, flags = [("commit message", "")], []
    # This module's git(), not the scanner's: its surrogateescape decoding
    # keeps a path that is not UTF-8 usable by `read`. -M finds renames
    # whatever the user's config, so a pure rename lists nothing.
    # --submodule=short shows a submodule as one line; at a code-looking path
    # it is listed as "could not be read".
    base = base or _empty_tree(root)
    diff = git(scan.DIFF + ["-M", "--submodule=short", "--ignore-submodules=none",
                            "--cached", base], root)
    touched = _touched(scan, diff)
    for path in _changed_docs(root, base):
        touched.setdefault(path, set())
    for path, lines in sorted(touched.items()):
        parts = set(pathlib.PurePosixPath(path).parts)
        doc = is_doc(path)
        # A doc is skipped only in a vendored directory; code is skipped in
        # any of the scanner's SKIP_DIRS, build output included.
        if parts & (VENDORED if doc else scan.SKIP_DIRS):
            continue
        if doc:
            items.append((path, "changed"))
            continue
        if not scan.scannable(path) or not lines:
            continue
        try:
            source = read(path)
        except (OSError, Refused, UnicodeDecodeError):
            items.append((path, "could not be read"))
            continue
        # git does not treat a bare CR as a line end. Without this replacement,
        # comments_in would, and every later line number would drift from the
        # diff's.
        source = re.sub(r"\r(?!\n)", " ", source)
        comments = scan.comments_touching(path, source, lines)
        if comments is None:
            items.append((path, "did not parse"))
            continue
        if not comments:
            continue
        spans = [f"{c.start}" if c.start == c.end else f"{c.start}-{c.end}" for c in comments]
        items.append((f"{path}:{','.join(spans)}", "comment"))
        for comment in comments:
            for note in scan.history_notes(comment, scan.mask_examples(scan.strip_markers(comment))):
                flags.append(f"{path}:{note.line}  {note.headline}")
    return items, flags


# The sections rules.md must have, in this order, each matched against the
# start of its `## ` heading. The rules section holds `### <n>. <title>`
# subsections.
RULE_SECTIONS = ("Scope", "The pass", "The rules", "How agents cheat")
RULES_IN_FULL = 8


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


def verify_staged(line, message, root):
    """(ok, reason) for a trailer line `prose check` printed, against the
    staged tree and this message now. The commit script runs this just before
    it commits. A failing reason starts with `unrecognised`, `mismatch` or
    `tree`, as verify_commit's does."""
    found = re.fullmatch(r"%s: (%s)" % (KEY, TRAILER.pattern), line.strip())
    if not found:
        return False, f"unrecognised: {line.strip()}"
    tree_half, message_half = found.group(2), found.group(3)
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
    if not found:
        return False, f"unrecognised: {KEY}: {value}"
    tree_half, message_half = found.groups()
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
    """(simple commands, feeds stdin) for a shell command, or None when any
    part of it is beyond what this reads exactly.

    Each simple command is [(text, source)]: each word's text and source as
    _word gives them. A word that is only line continuations is no word.
    Redirections are left out. feeds stdin is True when the
    command holds a pipe or an input redirection anywhere. Which command
    reads it is not worked out: subshells, groups and line breaks make that
    easy to get wrong. Heredoc bodies and comments are skipped, since the
    shell runs neither. None for anything whose reading differs between
    shells or could hide a command: what _word refuses, process
    substitution, a heredoc inside parentheses (bash 3.2 reads those its own
    way) or whose body would start inside an open `(`, an unquoted heredoc
    body that could run or join lines, a heredoc with no end, a number
    before a redirection other than one ASCII digit, a comment holding
    quotes or operators, unbalanced parentheses.
    """
    commands, feeds, pending, depth, i, n = [[]], False, [], 0, 0, len(command)
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
            commands.append([])
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
            feeds = feeds or op.startswith("<")
            i = word[1]
        elif char in ";&|":
            end = i
            while end < n and command[end] in ";&|":
                end += 1
            feeds = feeds or ("|" in command[i:end] and command[i:end] != "||")
            commands.append([])
            i = end
        elif char in "()":
            depth += 1 if char == "(" else -1
            if depth < 0:
                return None
            commands.append([])
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
                commands[-1].append((text, source))
            i = end
    return None if pending or depth else ([words for words in commands if words], feeds)


def _posts_nothing(command, cwd):
    """True when the shell provably runs no gh post in this command.

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
    With a pipe or an input redirection anywhere, every command must be from
    DATA_COMMANDS, gh included, since any other may run what it reads.
    Anything _commands cannot read makes this False.
    """
    read = _commands(command)
    if read is None:
        return False
    commands, feeds = read
    for words in commands:
        while words and words[0][1] in RESERVED:
            words = words[1:]
        if all(source in CLOSERS for _, source in words):
            continue
        names = [text.lstrip("=").rsplit("/", 1)[-1] for text, _ in words]
        source = " ".join(source for _, source in words)
        if feeds or (GH_TEXT.search(source) and "gh" not in names):
            if names[0] not in DATA_COMMANDS:
                return False
        elif "gh" in names:
            plain = _words(source)
            if not plain or plain[0] != ("gh", False):
                return False
            if POST_WORDS.search(" ".join(text for text, _ in plain)) and _read_gh(plain, cwd):
                return False
    return True


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
    return [] if _posts_nothing(command, cwd) else [("gh", NOT_ALLOWED)]


def _read_gh(words, cwd):
    """[(where, text or Unreadable)] for a gh command given as plain words,
    words[0] being gh: the bodies it posts, or NOT_ALLOWED when its shape is
    not one the hook reads."""
    args = list(words[1:])
    while args and (args[0][0] in ("-R", "--repo") or args[0][0].startswith(("--repo=", "-R"))):
        args = args[2:] if args[0][0] in ("-R", "--repo") else args[1:]
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
        f"  python3 {HERE / 'prose.py'} sign --goals '<reader goals>'\n"
        f"  python3 {HERE / 'prose.py'} sign --pass <token> < body.md > signed.md\n"
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


def issue_pass(goals, kind, session, root=None):
    """A new token for these goals and this command ("check" or "sign"),
    recorded so one signing call of that command can spend it. With a
    session id, also marks the session."""
    now = time.time()
    passes = _private_dir(pass_dir(root))
    _prune(passes, PASS_LIFETIME, now)
    token = secrets.token_hex(8)
    # Written whole under another name, then renamed: a concurrent redeem
    # never reads half a token. Its name has no token's shape, so a redeem
    # never matches it.
    draft = passes / f".{token}.{os.getpid()}"
    with open(draft, "x", encoding="utf-8") as handle:
        json.dump({"goals": goals, "kind": kind, "issued": now}, handle)
    os.replace(draft, passes / token)
    mark_session(session, now)
    return token


AGAIN = "Run the command again with --goals in place of --pass; that prints the rules and a new token."


def redeem_pass(token, goals, kind, root=None):
    """The goals this token was issued for. Refused when the token is unknown,
    spent, expired, or was issued for other goals or the other command. It
    stays unspent."""
    path = pass_dir(root) / token if PASS_TOKEN.fullmatch(token) else None
    try:
        record = json.loads(path.read_text(encoding="utf-8")) if path else None
    except FileNotFoundError:
        record = None
    except (OSError, ValueError) as error:
        raise Refused(f"could not read pass token {token}: {error}")
    if not isinstance(record, dict) or not isinstance(record.get("goals"), list) \
            or not isinstance(record.get("issued"), (int, float)):
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
    return record["goals"]


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
    print("Do the pass on the draft by the rules above. Then sign the final text:\n", file=stream)
    for command in next_commands:
        print(f"  {command}", file=stream)
    print(file=stream)


def _prose_command():
    return f"python3 {shlex.quote(str(HERE / 'prose.py'))}"


def next_check(token, message_file, amend, repo):
    words = ["check", "-F", message_file] + (["--amend"] if amend else []) \
        + (["--repo", repo] if repo != "." else []) + ["--pass", token]
    command = f"{_prose_command()} {' '.join(shlex.quote(w) for w in words)}"
    return command + ("   (the final message on stdin)" if message_file == "-" else "")


def next_sign(token):
    return f"{_prose_command()} sign --pass {token} < body.md > signed.md   (body.md: the final text)"


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
    sub.add_parser("start", parents=[goal_args],
                   help="before writing: print the goals and the rules; signs nothing")
    p_check = sub.add_parser("check", parents=[passing],
                             help="list the staged prose; first call: the rules and a pass token; "
                                  "with --pass: the trailer")
    p_check.add_argument("-F", "--message-file", required=True,
                         help="the final commit message; - reads stdin")
    p_check.add_argument("--amend", action="store_true",
                         help="list against HEAD's parent, for git commit --amend")
    p_check.add_argument("--repo", default=".")
    p_staged = sub.add_parser("verify-staged", help="exit 0 when a trailer line matches the index and stdin's message")
    p_staged.add_argument("line")
    p_staged.add_argument("--repo", default=".")
    p_verify = sub.add_parser("verify-commit", help="recompute a landed commit's Prose trailer")
    p_verify.add_argument("sha")
    p_verify.add_argument("--repo", default=".")
    sub.add_parser("sign", parents=[passing],
                   help="first call: the rules and a pass token; with --pass: stdin with a signed footer")
    sub.add_parser("verify-post", help="exit 0 when stdin's footer matches its text")
    p_hook = sub.add_parser("hook-post", help="the posting hook: payload on stdin")
    p_hook.add_argument("--host", default="")
    sub.add_parser("hook-gate", help="the first-write gate: payload on stdin")
    args = parser.parse_args(argv)

    try:
        if args.command == "start":
            # A warm-up before writing: the goals and the rules, and the
            # session mark that opens the gate. No token: each text still
            # gets its own first call, with its own reader's goals.
            goals = parse_goals(args.goals)
            require_goals(goals, "first call")
            read_rules()
            print_goals(goals)
            print_rules()
            mark_session(_session(args))
            print("\nWrite by these rules. This signs nothing: before each commit or post,")
            print("run its own first call, with the goals of that text's reader:\n")
            print(f"  A commit: {_prose_command()} check -F msg.txt --goals '<goals>'")
            print(f"  A post:   {_prose_command()} sign --goals '<goals>'\n")
            return 0
        if args.command == "check":
            if args.message_file == "-":
                message = _read_stdin()
            else:
                # Bytes: read_text's universal newlines would hide a bare CR.
                message = pathlib.Path(args.message_file).read_bytes().decode("utf-8", errors=TEXT_ERRORS)
            goals = parse_goals(args.goals)
            if args.token:
                goals = redeem_pass(args.token, goals, "check", args.repo)
            else:
                require_goals(goals, "pass token")
            # Read first: a rules file that cannot be printed, or a missing
            # result block, stops the check before it prints anything.
            read_rules()
            result_block()
            items, flags, trailer = check(message, args.repo, args.amend, bool(args.token))
            if args.token:
                # The signing call prints only the result block. It is built
                # before the token is spent, so a block that cannot be built
                # leaves the token for the same call to run again.
                block = render_result([trailer])
                spend_pass(args.token, args.repo)
                print_result(block)
                return 0
            print_goals(goals, heading=MESSAGE_GOALS)
            print_check(items, flags)
            print()
            print_rules()
            token = issue_pass(goals, "check", _session(args), args.repo)
            print_pass(token, [next_check(token, args.message_file, args.amend, args.repo)])
            print_commit_how(args.amend, args.message_file)
            return PASS_ISSUED
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
            goals = parse_goals(args.goals)
            if not args.token:
                require_goals(goals, "pass token")
                read_rules()
                print_goals(goals, sys.stderr)
                print_rules(sys.stderr)
                token = issue_pass(goals, "sign", _session(args))
                print_pass(token, [next_sign(token)], sys.stderr)
                return PASS_ISSUED
            goals = redeem_pass(args.token, goals, "sign")
            signed = sign(_read_stdin())
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
                 "the message against them; the docs and comments below have their own readers:")

# The groups print_check lists items in, as (note, heading naming the
# group's reader). An item joins the group whose note matches its own; None
# takes every note not named here, which are the code files'.
READERS = (
    ("", "The commit message. Its reader is the reviewer, with the goals above."),
    ("changed",
     "Docs and specs. Each one's reader is someone reading this document to learn what "
     "it describes, who wasn't in the conversation that produced it: not the reviewer. "
     "Cut what only a reviewer of this change needs. Reread each changed passage inside "
     "its section, as that section's reader, before keeping it."),
    (None,
     "Code comments. Their reader is someone about to change this code, who wasn't in "
     "the conversation that produced it: not the reviewer."),
)


def print_check(items, flags=()):
    print(f"prose: {len(items)} piece(s) of prose in this commit. Do the pass over each as "
          f"its own reader, named above its group:")
    known = {note for note, _ in READERS if note is not None}
    for note, heading in READERS:
        group = [item for item in items
                 if item[1] == note or (note is None and item[1] not in known)]
        if not group:
            continue
        print("\n" + heading + "\n")
        for what, kind in group:
            print(f"  {what}" + (f"  ({kind})" if kind else ""))
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
