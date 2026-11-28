"""The shared post reader tells a hook what a tool call posts on a GitHub
issue or pull request or in a Discord message. It gives one of three
answers: the posts, no post, or that a post's body cannot be read. Hooks
call read_posts; the gh-post spec's requirement *The shared post reader
reads a post's body from an allow-list* sets the rules.

It reads, by an allow-list:

- a GitHub MCP tool's `body` and `comment` strings;
- a `gh pr` or `gh issue` post that is the whole command line, its body from
  `--body`, `-b`, `--comment` or `-c` given as a word the shell does not
  expand, or from a `--body-file` or `-F` that exists;
- a `gh api` write to an issue or pull request endpoint, or a GraphQL
  mutation that posts text, its body given in the command or, when the call
  is the whole command line, read from a file;
- each of these run through github-app's script;
- a `post` or `edit` of discord-bot's script, read as a `gh issue comment`.

A line that mentions a post verb but is none of these is unreadable, unless
every command in it provably sends no post. It splits commands with
gh_shell.py beside it. It tracks the variables that name github-app's script
with gh_shell's app_assignments and app_command and handbacks.py's
forget_scripts, and tracks discord-bot's itself. Standard library only.
"""

import json
import pathlib
import posixpath
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from gh_shell import (
    APP_SCRIPT,
    BODY_SOURCES,
    CLOSERS,
    COMMON_LONG,
    DATA_COMMANDS,
    GH_TEXT,
    GH_VERBS,
    GITHUB_MCP,
    LONG_FLAGS,
    NO_SOURCES,
    NO_TEXT_VERBS,
    PYTHONS,
    RESERVED,
    SHORT_VALUES,
    SOURCE,
    VARIABLE,
    _commands,  # pyright: ignore[reportPrivateUsage]
    _gh_args,  # pyright: ignore[reportPrivateUsage]
    _word,  # pyright: ignore[reportPrivateUsage]
    _words,  # pyright: ignore[reportPrivateUsage]
    app_assignments,
    app_command,
)
from handbacks import forget_scripts

# A shell word as gh_shell gives it: (text after quote removal, the word as
# written, quotes included).
Word = tuple[str, str]


@dataclass(frozen=True)
class Post:
    """One body the call sends. The field `where` labels that body in the
    hooks' block messages, such as `gh pr comment --body-file c.md` or
    `comments[0].body` of a review. The field `surface` says where it is
    posted: "discord" for a message sent through discord-bot's script, else
    "github"."""

    where: str
    body: str
    surface: Literal["github", "discord"] = "github"


@dataclass(frozen=True)
class NoPost:
    """The call sends no post."""


@dataclass(frozen=True)
class Unreadable:
    """The call may send a post whose body the reader cannot read, and why.
    The inquisitor's post hook and prose's posting hook both block such a
    call."""

    why: str


Result = list[Post] | NoPost | Unreadable

ACCEPTED = (
    "The hook reads a gh post only when gh is the whole command, run directly or "
    "through github-app's script, with the body as --body '<text>' (single quotes, "
    "or double quotes with no $, backtick or backslash) or --body-file <a file that "
    "exists>; or a gh api write with its body in -f body='<text>', or in "
    "-F body=@<file> when gh api is the whole command; or discord-bot's post or edit, "
    "as the whole command, with --message '<text>' or --message-file <a file that "
    "exists>.")


def _not_allowed(where: str) -> Unreadable:
    return Unreadable(f"{where}: this command is not one of the forms the hook reads, so "
                      "what it posts cannot be checked. " + ACCEPTED)


FROM_STDIN = "the text comes from stdin, so it cannot be checked. " + ACCEPTED


def _fed_blocker(name: str) -> Unreadable:
    return Unreadable(
        f"`{name}` reads a pipe or an input redirection (<, <<, <<<), so what it "
        "runs or posts cannot be checked. Only a data command (echo, cat, grep, "
        "head, python3 …) or a gh subcommand that takes no body, such as gh pr "
        "view, may read one. " + ACCEPTED)


GROUPED = Unreadable(
    "a pipe or an input redirection feeds a group, loop or subshell, so what it "
    "runs or posts cannot be checked unless every command in it is a data "
    "command (echo, cat, grep, head, python3 …). " + ACCEPTED)


def _unassigned(name: str) -> Unreadable:
    return Unreadable(
        f"`${name}` is not assigned github-app's or discord-bot's script path in this "
        "command, so the hook cannot tell which script runs. Assign the variable in the "
        f"same command ({name}=<path>/github_app.py; python3 \"${name}\" gh …) or write "
        "the script's path. " + ACCEPTED)


# -- what a line mentions, before it is split --------------------------------

def _whole(words: str) -> str:
    """A pattern matching any of the `|`-joined alternatives in words as a
    whole word: no letter, digit or `_` just before it, and none of those or
    `-` just after, so `--comment` matches but `--comment-file` does not."""
    return rf"(?<!\w)(?:{words})(?![\w-])"


PR_VERBS = ("create", "new", "edit", "comment", "review", "revert", "close", "reopen")
ISSUE_VERBS = ("create", "new", "edit", "comment", "close", "reopen")
POST_WORDS = re.compile(
    _whole("gh") + r"[\s\S]*(?:" + _whole("pr") + r"[\s\S]*" + _whole("|".join(PR_VERBS))
    + "|" + _whole("issue") + r"[\s\S]*" + _whole("|".join(ISSUE_VERBS)) + ")")
GH_API_TEXT = re.compile(_whole("gh") + r"[\s\S]*" + _whole("api"))
DISCORD_SCRIPT = "discord_bot.py"
# A word ending in discord-bot's script, then anywhere later its post or
# edit: the spec's requirement *A command that mentions no gh post verb sends
# no post* counts these as gh post verbs.
DISCORD_TEXT = re.compile(r"discord_bot\.py(?![\w-])[\s\S]*" + _whole("post|edit"))


def _mentions(text: str) -> bool:
    """Whether text mentions a gh post verb other than a gh api call: gh pr
    or gh issue with a post verb, or discord-bot's post or edit."""
    return bool(POST_WORDS.search(text) or DISCORD_TEXT.search(text))


def runs_only_prose(command: str) -> bool:
    """Whether the line is one simple command that runs prose.py, so text in
    its arguments (such as a --goals value that mentions `gh pr create`) is
    not a post (gh-post
    spec: *A command that only runs prose's script sends no post*).
    Redirections are allowed; a substitution, a newline or a second command
    could run more."""
    if "`" in command or "$(" in command or "\n" in command:
        return False
    read = _commands(command)
    if read is None or len(read[0]) != 1:
        return False
    words = [text for text, _ in read[0][0][0]]
    program = words[1] if words[0] in PYTHONS and len(words) > 1 else words[0]
    return program == "prose.py" or program.endswith("/prose.py")


def _top_level(command: str) -> set[str] | None:
    """The control operators outside quotes in a line (`;`, `&&`, `(` …), or
    None when it holds a redirection, a heredoc or a word gh_shell cannot
    read. A line that is one whole command has no control operator, except a
    `;` or `&&` after an assignment of github-app's or discord-bot's script
    path."""
    ops: set[str] = set()
    i, n = 0, len(command)
    while i < n:
        char = command[i]
        if char in " \t\n":
            i += 1
        elif char == "#":
            end = command.find("\n", i)
            i = n if end == -1 else end
        elif char in "<>" or command.startswith("&>", i):
            return None
        elif char in ";&|()":
            end = i
            while end < n and command[end] in ";&|()":
                end += 1
            ops.add(command[i:end])
            i = end
        else:
            word = _word(command, i)
            if word is None:
                return None
            if command[word[1]:word[1] + 1] in ("<", ">"):
                return None
            i = word[1]
    return ops


def _unsubstitute(command: str) -> str | None:
    """The line with each unquoted `$(` read as a subshell's `(`, so its
    commands are split like any others (gh-post spec: *The reader splits a
    command line into simple commands*); None when a `$(` is inside double
    quotes, or the line holds a backtick outside single quotes or any `<<`
    (a heredoc or here-string), forms the reader reports as unreadable."""
    if "<<" in command:
        return None
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        char = command[i]
        if quote == "'":
            quote = None if char == "'" else quote
        elif char == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        elif char == "`":
            return None
        elif char == "$" and command.startswith("$(", i):
            if quote == '"':
                return None
            out.append(" ")
            i += 1
            continue
        elif quote == '"':
            quote = None if char == '"' else quote
        elif char in "'\"":
            quote = char
        out.append(char)
        i += 1
    return "".join(out)


# -- one simple command, with github-app's script read as what it runs ----

@dataclass
class _Command:
    words: list[Word]
    fed: bool
    app: bool = False
    # The variable a `python3 "$G" gh …` names, when no command before it
    # assigned github-app's or discord-bot's script to it.
    unassigned: str | None = None
    api: "Result | str | None" = field(default=None)
    # A call of discord-bot's script: words then hold its subcommand and
    # that subcommand's arguments.
    discord: bool = False


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _names_script(text: str, source: str, script: str) -> bool:
    """Whether a word names a script: its text is the script's file name or
    a path ending in it, and its source, closing quotes aside, ends with that
    name too, so a name spelled with an escape or a split quote, such as
    `discord_bot.p\\y`, does not count. gh_shell names github-app's script
    by the same rule."""
    return (text == script or text.endswith("/" + script)) \
        and source.rstrip("'\"").endswith(script)


def _discord_assignments(words: list[Word], scripts: set[str]) -> None:
    """Track in scripts the variables a command made only of assignments
    sets to discord-bot's script path, and drop those it sets to anything
    else, as app_assignments does for github-app's."""
    if not words or not all(ASSIGNMENT.match(source) for _, source in words):
        return
    for text, source in words:
        name, _, value = text.partition("=")
        if _names_script(value, source.partition("=")[2], DISCORD_SCRIPT):
            scripts.add(name)
        else:
            scripts.discard(name)


def _only_script_assignments(words: list[Word]) -> bool:
    return bool(words) and all(
        ASSIGNMENT.match(source) and any(
            _names_script(text.partition("=")[2], source.partition("=")[2], script)
            for script in (APP_SCRIPT, DISCORD_SCRIPT))
        for text, source in words)


def _discord_call(words: list[Word], scripts: set[str]) -> list[Word] | None:
    """discord-bot's subcommand and its arguments, for a simple command
    that runs the script with python or python3, by its path or a variable
    in scripts, past any --identity options; else None."""
    if len(words) < 3 or words[0][0].rsplit("/", 1)[-1] not in PYTHONS:
        return None
    text, source = words[1]
    variable = VARIABLE.fullmatch(source)
    if not (_names_script(text, source, DISCORD_SCRIPT) or (
            variable and not text and (variable.group(1) or variable.group(2)) in scripts)):
        return None
    i = 2
    while i < len(words) and (words[i][0] == "--identity"
                              or words[i][0].startswith("--identity=")):
        i += 2 if words[i][0] == "--identity" else 1
    return words[i:] if i < len(words) else None


def _resolve(commands: list[tuple[list[Word], bool]]) -> list[_Command]:
    """The simple commands, each call of github-app's script replaced by the
    command it runs, each call of discord-bot's script marked, and each
    command that only assigns either script's path dropped (gh-post spec:
    *The reader reads posts sent through the github-app skill and gh api*,
    *The reader reads discord-bot's post and edit as gh issue comment*)."""
    scripts: set[str] = set()
    discord: set[str] = set()
    resolved: list[_Command] = []
    for words, fed in commands:
        app_assignments(words, scripts)
        _discord_assignments(words, discord)
        if _only_script_assignments(words):
            continue
        lead = next((k for k, (_, src) in enumerate(words) if not ASSIGNMENT.match(src)),
                    len(words))
        run = app_command(words[lead:], scripts)
        if run:
            resolved.append(_Command(words[:lead] + run, fed, app=True))
            continue
        call = None if lead else _discord_call(words, discord)
        if call:
            resolved.append(_Command(call, fed, discord=True))
            continue
        texts = [text for text, _ in words]
        forget_scripts(texts, scripts)
        forget_scripts(texts, discord)
        command = _Command(words, fed)
        rest = words[lead:]
        if len(rest) >= 3 and rest[0][0].rsplit("/", 1)[-1] in PYTHONS and not rest[1][0]:
            variable = VARIABLE.fullmatch(rest[1][1])
            if variable and any(text in ("gh", "run", "post", "edit") for text, _ in rest[2:]):
                command.unassigned = variable.group(1) or variable.group(2)
        resolved.append(command)
    return resolved


# discord-bot's options for post and edit that take a value and carry no
# text, from its argparse parser. --message and --message-file carry the
# text and are read apart.
DISCORD_VALUES = {"post": {"--channel", "--thread", "--agent", "--session", "--project",
                           "--reply-to"},
                  "edit": {"--channel", "--thread", "--message-id"}}
DISCORD_SUBCOMMANDS = {"delete", "read", "thread", "check", "invite-url", "store-token",
                       "forget-token"}


def _read_discord(words: list[Word], cwd: str | None) -> list[Post] | Unreadable:
    """The message a call of discord-bot's script posts, read as gh issue
    comment reads its body: --message - and --message-file - as
    --body-file -, any other --message as --body and --message-file as
    --body-file. When the option repeats, argparse keeps the last value, so
    only that one is read; discord-bot refuses a call that gives both, and
    the reader reads whichever comes last. No message for a subcommand that posts no text,
    such as delete, read or thread."""
    plain = _words(" ".join(source for _, source in words))
    if not plain:
        return _not_allowed("discord-bot")
    verb = plain[0][0]
    if verb in DISCORD_SUBCOMMANDS:
        return []
    if verb not in DISCORD_VALUES:
        return _not_allowed("discord-bot")
    where = f"discord-bot {verb}"
    given: tuple[str, str] | None = None
    i = 1
    while i < len(plain):
        arg = plain[i][0]
        name, eq, value = arg.partition("=")
        if name in DISCORD_VALUES[verb]:
            i += 1 if eq else 2
            continue
        if name not in ("--message", "--message-file"):
            return _not_allowed(where)
        if not eq:
            if i + 1 >= len(plain):
                return _not_allowed(where)
            value = plain[i + 1][0]
            i += 1
        i += 1
        given = (name, value)
    if given is None:
        return []
    name, value = given
    if value == "-":
        return Unreadable(f"{where} {name} -: {FROM_STDIN}")
    if name == "--message":
        return [Post(f"{where} --message", value, "discord")]
    body = _read_file(value, cwd)
    if body is None:
        return Unreadable(f"{where} {name} {value}: {value} could not be read. " + ACCEPTED)
    return [Post(f"{where} {name} {value}", body, "discord")]


def _strip_reserved(words: list[Word]) -> list[Word]:
    while words and words[0][1] in RESERVED:
        words = words[1:]
    return words


def _is_gh(words: list[Word]) -> bool:
    return bool(words) and words[0] == ("gh", "gh")


def _is_api(words: list[Word]) -> bool:
    return _is_gh(words) and len(words) > 1 and words[1][0] == "api"


# -- gh pr and gh issue ----------------------------------------------------

def _body_flag(args: list[tuple[str, bool]], i: int, flags: tuple[str, ...], values: str = "",
               sources: str = "") -> tuple[str | None, str | None, int]:
    """(flag, text or None, index of the next arg) for args[i].

    flag is None when args[i] is not a body flag, and SOURCE when it holds a
    letter from sources, one that makes gh take the text from elsewhere.
    Reads `--body x`, `--body=x`, and the short forms of pflag, the Go flag
    library gh uses: `-b x`, `-bx`,
    `-b=x`, and a group such as `-db x`. values holds the verb's other short
    letters that take a value. In a group, the first letter that takes a
    value swallows the rest of the group as that value: in `-tb x`, `b` is
    the title's text, not the body flag."""
    arg = args[i][0]
    following = args[i + 1][0] if i + 1 < len(args) else None
    for name in flags:
        if name.startswith("--"):
            if arg == name:
                return name, following, i + 2
            if arg.startswith(name + "="):
                return name, arg[len(name) + 1:], i + 1
    if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
        shorts = {name[1] for name in flags if not name.startswith("--")}
        for position in range(1, len(arg)):
            letter, rest = arg[position], arg[position + 1:]
            if letter == "=":
                # pflag ends a group at `=`: `-d=t` is `--draft=t`.
                return None, None, i + 1
            if letter in shorts:
                if rest:
                    return f"-{letter}", (rest[1:] if rest.startswith("=") else rest), i + 1
                return f"-{letter}", following, i + 2
            if letter in sources:
                return SOURCE, None, i + 1
            if letter in values:
                return None, None, (i + 1 if rest else i + 2)
    return None, None, i + 1


def _read_file(text: str, cwd: str | None) -> str | None:
    """A file's text, the path relative to cwd, or None. No expanduser: bash
    leaves a quoted `~` as it is, and gh opens the path literally."""
    target = pathlib.Path(text)
    if not target.is_absolute():
        target = pathlib.Path(cwd or ".") / target
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):  # ValueError: a NUL byte
        return None


def _read_gh(words: list[tuple[str, bool]], cwd: str | None) -> list[Post] | Unreadable:
    """The bodies a gh command posts, given as gh_shell's _words gives it
    (words the shell only joins, with no expansion), words[0] being gh: none for a command that sends no text, or Unreadable when its shape
    is not one the reader reads."""
    args = _gh_args(words)
    if len(args) >= 2 and args[1][0] in NO_TEXT_VERBS.get(args[0][0], ()):
        return []
    if len(args) < 2 or args[1][0] not in GH_VERBS.get(args[0][0], {}):
        return _not_allowed("gh")
    noun, verb = args[0][0], args[1][0]
    flags, values = GH_VERBS[noun][verb], SHORT_VALUES[noun][verb]
    long_values = LONG_FLAGS[noun][verb][0] | COMMON_LONG[0]
    long_bools = LONG_FLAGS[noun][verb][1] | COMMON_LONG[1]
    long_sources, short_sources = BODY_SOURCES[noun].get(verb, NO_SOURCES)
    where = f"gh {noun} {verb}"
    found: list[Post] = []
    i = 2
    while i < len(args):
        arg = args[i][0]
        name = arg[2:].split("=", 1)[0]
        if arg.startswith("--") and "--" + name not in flags:
            if name in long_sources:
                return _not_allowed(where)
            if name in long_values:
                i += 1 if "=" in arg else 2
                continue
            if name in long_bools:
                i += 1
                continue
            return _not_allowed(where)
        flag, text, i = _body_flag(args, i, flags, values, short_sources)
        if flag == SOURCE:
            return _not_allowed(where)
        if flag is None or text is None:
            continue
        if flag in ("--body-file", "-F"):
            if text == "-":
                return Unreadable(f"{where} {flag} -: {FROM_STDIN}")
            body = _read_file(text, cwd)
            if body is None:
                return Unreadable(f"{where} {flag} {text}: {text} could not be read. " + ACCEPTED)
            found.append(Post(f"{where} {flag} {text}", body))
        else:
            found.append(Post(f"{where} {flag}", text))
    return found


# -- gh api ----------------------------------------------------------------

# gh api's flags, from `gh api --help` (gh 2.103): short letters that take a
# value, short switches, long flags that take a value, and long switches.
# API_LONG maps each long flag to the kind add() records its value under,
# "" for a value the reader ignores.
API_SHORT_VALUES = "FHXfpqt"
API_SHORT_SWITCHES = "i"
API_LONG = {"field": "F", "raw-field": "f", "method": "X", "header": "H", "input": "input",
            "cache": "", "hostname": "", "jq": "", "preview": "", "template": ""}
API_LONG_SWITCHES = {"allow-escape-sequences", "include", "paginate", "silent", "slurp",
                     "verbose", "help"}
# The GraphQL mutations that post text on an issue or pull request (gh-post
# spec: *The GraphQL mutations that post text are a closed list*).
MUTATIONS = {"addComment", "addPullRequestReview", "addPullRequestReviewComment",
             "addPullRequestReviewThread", "addPullRequestReviewThreadReply",
             "submitPullRequestReview", "createIssue", "createPullRequest", "updateIssue",
             "updateIssueComment", "updatePullRequest", "updatePullRequestReview",
             "updatePullRequestReviewComment"}
# An issue's or pull request's endpoint, by owner and name or by the
# repository's id.
ISSUE_ENDPOINT = re.compile(r"(?:repos/[^/]+/[^/]+|repositories/[^/]+)/(?:issues|pulls)(?:/|$)",
                            re.I)
PLACEHOLDER = re.compile(r"\{(?:owner|repo|branch)\}")
# The placeholders gh fills in a -F value: `{owner}`, `{repo}` and `{branch}`,
# and the older `:owner`, `:repo` and `:branch` (gh's own pattern).
# re.ASCII matches Go's \b, which knows only ASCII word characters.
FILLED = re.compile(r"\{(?:owner|repo|branch)\}|:(?:owner|repo|branch)\b", re.ASCII)
FIELD_KEY = re.compile(r"([^\[\]]*)((?:\[[^\[\]]*\])*)")


def literal(source: str, endpoint: bool = False) -> bool:
    """Whether a word, as written, is one the shell does not expand: no `$`,
    backtick or backslash outside single quotes, and no `*`, `?`, `[`, `{`
    or `~` outside quotes (gh-post spec: *A literal word is one the shell
    does not expand*). An endpoint may also hold `?` and gh's `{owner}`,
    `{repo}` and `{branch}` placeholders."""
    if endpoint:
        source = PLACEHOLDER.sub("", source).replace("?", "")
    quote: str | None = None
    for char in source:
        if quote == "'":
            quote = None if char == "'" else quote
        elif char in "\\`$":
            return False
        elif quote == '"':
            quote = None if char == '"' else quote
        elif char in "'\"":
            quote = char
        elif char in "*?[{~":
            return False
    return quote is None


@dataclass
class _Api:
    methods: list[str] = field(default_factory=lambda: [])
    fields: list[tuple[str, str]] = field(default_factory=lambda: [])  # (flag letter, key=value)
    inputs: list[str] = field(default_factory=lambda: [])
    headers: list[str] = field(default_factory=lambda: [])
    positional: list[int] = field(default_factory=lambda: [])


def _parse_api(texts: list[str]) -> _Api | None:
    """A gh api call's flags and positional arguments (their indices in
    texts), read as pflag reads them, or None for a flag gh api does not
    have or a flag missing its value."""
    call = _Api()

    def add(kind: str, value: str) -> None:
        if kind == "X":
            call.methods.append(value)
        elif kind in ("f", "F"):
            call.fields.append((kind, value))
        elif kind == "H":
            call.headers.append(value)
        elif kind == "input":
            call.inputs.append(value)

    i = 0
    while i < len(texts):
        arg = texts[i]
        if arg == "--":
            call.positional += range(i + 1, len(texts))
            break
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if name in API_LONG:
                if not eq:
                    if i + 1 >= len(texts):
                        return None
                    value, i = texts[i + 1], i + 1
                add(API_LONG[name], value)
            elif name not in API_LONG_SWITCHES:
                return None
        elif arg.startswith("-") and len(arg) > 1:
            position = 1
            while position < len(arg):
                letter, rest = arg[position], arg[position + 1:]
                if letter in API_SHORT_VALUES:
                    if rest:
                        value = rest[1:] if rest.startswith("=") else rest
                    elif i + 1 < len(texts):
                        value, i = texts[i + 1], i + 1
                    else:
                        return None
                    add(letter, value)
                    break
                if letter not in API_SHORT_SWITCHES:
                    return None
                if rest.startswith("="):
                    break
                position += 1
        else:
            call.positional.append(i)
        i += 1
    return call


def _endpoint_path(endpoint: str) -> str:
    """An endpoint as the path the server routes: no host, fragment, query,
    or leading or trailing `/`, percent-escapes decoded and `.` and `..`
    segments resolved. gh sends the path as written, and GitHub normalises
    it, so `repos/o/r/./%69ssues` reaches the issues endpoint."""
    full = re.match(r"https?://[^/]+/(?:api/v3/)?(.*)", endpoint, re.I)
    if full:
        endpoint = full.group(1)
    path = urllib.parse.unquote(endpoint.split("#", 1)[0].split("?", 1)[0])
    return posixpath.normpath("/" + path).strip("/")


def _segments(key: str) -> tuple[str, ...]:
    """A field's key as gh nests it: `comments[][body]` is
    ("comments", "[]", "body")."""
    match = FIELD_KEY.fullmatch(key)
    if not match:
        return (key,)
    inner = re.findall(r"\[([^\[\]]*)\]", match.group(2))
    return (match.group(1), *[part or "[]" for part in inner])


class _Filled:
    """A -F value holding a placeholder FILLED matches, such as {owner} or
    :owner."""


class _Missing(Exception):
    """A value the reader needs that the call does not give or the reader
    cannot read."""


def _field_value(kind: str, value: str, cwd: str | None, whole: bool) -> object:
    """What gh sends for one field's value: the text for -f; for -F, a
    file's text for `@<file>` and gh's types for true, false, null and
    integers."""
    if kind == "f":
        return value
    if value.startswith("@"):
        if value == "@-":
            raise _Missing(FROM_STDIN)
        if not whole:
            raise _Missing(f"{value[1:]} is read from a file, which the hook reads only when "
                           "gh api is the whole command. " + ACCEPTED)
        text = _read_file(value[1:], cwd)
        if text is None:
            raise _Missing(f"{value[1:]} could not be read. " + ACCEPTED)
        return text
    if FILLED.search(value):
        # gh fills the placeholder with the repository's owner, name or
        # branch. The reader cannot know those, so it cannot read a body
        # holding one.
        return _Filled()
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    if re.fullmatch(r"[-+]?[0-9]+", value):
        return int(value)
    return value


Leaves = list[tuple[tuple[str, ...], object]]


def _flatten(value: object, prefix: tuple[str, ...], leaves: Leaves) -> None:
    if isinstance(value, dict) and value:
        for key, item in cast(dict[object, object], value).items():
            _flatten(item, (*prefix, str(key)), leaves)
    elif isinstance(value, list) and value:
        for item in cast(list[object], value):
            _flatten(item, (*prefix, "[]"), leaves)
    else:
        leaves.append((prefix, cast(object, value)))


def _input_json(path: str, cwd: str | None, whole: bool) -> object:
    if path == "-":
        raise _Missing(FROM_STDIN)
    if not whole:
        raise _Missing(f"--input {path} is read from a file, which the hook reads only when "
                       "gh api is the whole command. " + ACCEPTED)
    text = _read_file(path, cwd)
    if text is None:
        raise _Missing(f"--input {path} could not be read. " + ACCEPTED)
    try:
        return json.loads(text)
    except ValueError:
        raise _Missing(f"--input {path} is not JSON. " + ACCEPTED) from None


def _body_text(value: object, where: str) -> list[str]:
    """A body's value as text: a string; nothing for null; anything else is
    unreadable."""
    if isinstance(value, str):
        return [value]
    if value is None:
        return []
    raise _Missing(f"{where} is not text. " + ACCEPTED)


def _read_api(words: list[Word], cwd: str | None, whole: bool) -> "Result | str":
    """What a gh api call sends: "read" for a read, Unreadable, or its posts
    (none for a write that sends no post). whole says whether the call is
    the whole command line, the only case in which a field or input is read
    from a file."""
    texts = [text for text, _ in words]
    label = "gh api"
    call = _parse_api(texts[2:])
    if call is None:
        return Unreadable(f"`{' '.join(src for _, src in words)}`: gh api's arguments could "
                          "not be read. " + ACCEPTED)
    endpoint_at = call.positional[0] + 2 if call.positional else -1
    for k, (_, source) in enumerate(words):
        if not literal(source, k == endpoint_at) or source.startswith("="):
            return Unreadable(f"`{' '.join(src for _, src in words)}`: the word `{source}` is "
                              "one the shell builds, so what the call sends cannot be checked. "
                              + ACCEPTED)
    if len(call.positional) != 1:
        return Unreadable(f"`{' '.join(src for _, src in words)}`: gh api takes one endpoint. "
                          + ACCEPTED)
    endpoint = texts[endpoint_at]
    label = f"gh api {endpoint}"
    path = _endpoint_path(endpoint)
    try:
        if path.lower() in ("graphql", "api/graphql"):
            return _read_graphql(call, label, cwd, whole, endpoint == "graphql")
        override = any(h.partition(":")[0].strip().lower() == "x-http-method-override"
                       for h in call.headers)
        method = call.methods[-1].upper() if call.methods else None
        writes = override or (method is not None and method != "GET") \
            or (method is None and bool(call.fields or call.inputs))
        if not writes:
            return "read"
        if not ISSUE_ENDPOINT.match(path):
            return []
        if "?" in endpoint:
            raise _Missing("the endpoint carries a query string, which GitHub may read too, "
                           "so what is posted cannot be checked. " + ACCEPTED)
        posts: list[Post] = []
        # With --input the file is the request's body, and gh adds the
        # fields to the URL's query string, which GitHub may read too.
        if call.inputs and call.fields:
            raise _Missing("fields beside --input go into the URL, so what is posted cannot "
                           "be checked. " + ACCEPTED)
        for kind, raw in call.fields:
            key, eq, value = raw.partition("=")
            text = _field_value(kind, value, cwd, whole) if eq else None
            if eq and _segments(key)[-1] == "body":
                posts += [Post(f"{label} -{kind} {key}", t)
                          for t in _body_text(text, f"{label} -{kind} {key}")]
        for path_given in call.inputs:
            leaves: Leaves = []
            _flatten(_input_json(path_given, cwd, whole), (), leaves)
            for at, value in leaves:
                if at and at[-1] == "body":
                    where = f"{label} --input {path_given} {'.'.join(at)}"
                    posts += [Post(where, t) for t in _body_text(value, where)]
        return posts
    except _Missing as missing:
        return Unreadable(f"{label}: {missing}")


# -- GraphQL ---------------------------------------------------------------

GRAPHQL_TOKEN = re.compile(
    r'(?P<skip>[\s,﻿]+|#[^\n\r]*)'
    r'|(?P<block>"""(?:\\"""|[\s\S])*?""")'
    r'|(?P<string>"(?:[^"\\\n\r]|\\["\\/bfnrt]|\\u[0-9A-Fa-f]{4})*")'
    r'|(?P<spread>\.\.\.)'
    r'|(?P<punct>[!$&():=@\[\]{|}])'
    r'|(?P<number>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)'
    r'|(?P<name>[_A-Za-z][_0-9A-Za-z]*)')

# A parsed GraphQL value: ("var", name), ("str", text), ("null", None),
# ("list", [values]), ("obj", [(name, value)]), or ("other", None).
Value = tuple[str, Any]
# A selection: ("field", name, arguments, selections), ("spread", name), or
# ("inline", selections).
Selection = tuple[Any, ...]


def _block_string(raw: str) -> str:
    """A GraphQL block string's value, by the spec's BlockStringValue."""
    lines = re.split(r"\r\n|\n|\r", raw.replace('\\"""', '"""'))
    indents = [len(line) - len(line.lstrip(" \t")) for line in lines[1:] if line.strip(" \t")]
    common = min(indents) if indents else 0
    lines = lines[:1] + [line[common:] for line in lines[1:]]
    while lines and not lines[0].strip(" \t"):
        lines.pop(0)
    while lines and not lines[-1].strip(" \t"):
        lines.pop()
    return "\n".join(lines)


class _Parser:
    """Reads a GraphQL document far enough to find each operation's kind,
    its variables' defaults, and its fields' arguments. Raises _Missing for
    anything it cannot read."""

    def __init__(self, text: str):
        self.tokens: list[tuple[str, str]] = []
        i = 0
        while i < len(text):
            match = GRAPHQL_TOKEN.match(text, i)
            if not match:
                raise _Missing("the GraphQL query could not be parsed. " + ACCEPTED)
            kind = match.lastgroup or ""
            if kind != "skip":
                self.tokens.append((kind, match.group()))
            i = match.end()
        self.at = 0

    def peek(self, value: str | None = None, kind: str | None = None) -> bool:
        if self.at >= len(self.tokens):
            return False
        token_kind, token = self.tokens[self.at]
        return (value is None or token == value) and (kind is None or token_kind == kind)

    def take(self, value: str | None = None, kind: str | None = None) -> str:
        if not self.peek(value, kind):
            raise _Missing("the GraphQL query could not be parsed. " + ACCEPTED)
        self.at += 1
        return self.tokens[self.at - 1][1]

    def document(self) -> tuple[list[tuple[str, dict[str, Value | None], list[Selection]]],
                                dict[str, list[Selection]]]:
        operations: list[tuple[str, dict[str, Value | None], list[Selection]]] = []
        fragments: dict[str, list[Selection]] = {}
        while self.at < len(self.tokens):
            if self.peek("{"):
                operations.append(("query", {}, self.selections()))
            elif self.peek("fragment"):
                self.take()
                name = self.take(kind="name")
                self.take("on")
                self.take(kind="name")
                self.directives()
                fragments[name] = self.selections()
            else:
                kind = self.take(kind="name")
                if kind not in ("query", "mutation", "subscription"):
                    raise _Missing("the GraphQL query could not be parsed. " + ACCEPTED)
                if self.peek(kind="name"):
                    self.take()
                defaults: dict[str, Value | None] = {}
                if self.peek("("):
                    self.take()
                    while not self.peek(")"):
                        self.take("$")
                        name = self.take(kind="name")
                        self.take(":")
                        self.type()
                        defaults[name] = None
                        if self.peek("="):
                            self.take()
                            defaults[name] = self.value()
                        self.directives()
                    self.take(")")
                self.directives()
                operations.append((kind, defaults, self.selections()))
        if not operations:
            raise _Missing("the GraphQL query holds no operation. " + ACCEPTED)
        return operations, fragments

    def type(self) -> None:
        if self.peek("["):
            self.take()
            self.type()
            self.take("]")
        else:
            self.take(kind="name")
        if self.peek("!"):
            self.take()

    def directives(self) -> None:
        while self.peek("@"):
            self.take()
            self.take(kind="name")
            if self.peek("("):
                self.arguments()

    def arguments(self) -> list[tuple[str, Value]]:
        self.take("(")
        found: list[tuple[str, Value]] = []
        while not self.peek(")"):
            name = self.take(kind="name")
            self.take(":")
            found.append((name, self.value()))
        self.take(")")
        return found

    def selections(self) -> list[Selection]:
        self.take("{")
        found: list[Selection] = []
        while not self.peek("}"):
            if self.peek(kind="spread"):
                self.take()
                if self.peek("on") or self.peek("@") or self.peek("{"):
                    if self.peek("on"):
                        self.take()
                        self.take(kind="name")
                    self.directives()
                    found.append(("inline", self.selections()))
                else:
                    found.append(("spread", self.take(kind="name")))
                    self.directives()
                continue
            name = self.take(kind="name")
            if self.peek(":"):
                self.take()
                name = self.take(kind="name")
            arguments = self.arguments() if self.peek("(") else []
            self.directives()
            inner = self.selections() if self.peek("{") else []
            found.append(("field", name, arguments, inner))
        self.take("}")
        return found

    def value(self) -> Value:
        if self.peek("$"):
            self.take()
            return ("var", self.take(kind="name"))
        if self.peek(kind="string"):
            return ("str", json.loads(self.take()))
        if self.peek(kind="block"):
            return ("str", _block_string(self.take()[3:-3]))
        if self.peek("["):
            self.take()
            items: list[Value] = []
            while not self.peek("]"):
                items.append(self.value())
            self.take("]")
            return ("list", items)
        if self.peek("{"):
            self.take()
            pairs: list[tuple[str, Value]] = []
            while not self.peek("}"):
                name = self.take(kind="name")
                self.take(":")
                pairs.append((name, self.value()))
            self.take("}")
            return ("obj", pairs)
        if self.peek("null"):
            self.take()
            return ("null", None)
        if self.peek(kind="number") or self.peek(kind="name"):
            self.take()
            return ("other", None)
        raise _Missing("the GraphQL query could not be parsed. " + ACCEPTED)


class _Bodies:
    """Finds every `body` argument, at any depth, in a mutation's
    arguments, resolving variables from the call's fields and input."""

    def __init__(self, leaves: Leaves, defaults: dict[str, Value | None], where: str):
        self.leaves, self.defaults, self.where = leaves, defaults, where

    def given(self, name: str) -> Leaves:
        return [(at, value) for at, value in self.leaves if at[:1] == (name,)]

    def body(self, value: Value) -> list[str]:
        kind, data = value
        if kind == "str":
            return [data]
        if kind == "null":
            return []
        if kind == "var":
            given = self.given(data)
            exact = [v for at, v in given if len(at) == 1]
            if exact:
                return _body_text(exact[-1], f"{self.where} variable ${data}")
            if given:
                raise _Missing(f"{self.where}: the body variable ${data} is not text. "
                               + ACCEPTED)
            default = self.defaults.get(data)
            if default is None:
                raise _Missing(f"{self.where}: the body variable ${data} is not given. "
                               + ACCEPTED)
            return self.body(default)
        raise _Missing(f"{self.where}: a body is not text. " + ACCEPTED)

    def walk(self, key: str | None, value: Value) -> list[str]:
        if key == "body":
            return self.body(value)
        kind, data = value
        if kind == "obj":
            return [text for name, item in data for text in self.walk(name, item)]
        if kind == "list":
            return [text for item in data for text in self.walk(None, item)]
        if kind == "var":
            given = self.given(data)
            if not given and self.defaults.get(data) is not None:
                return self.walk(None, self.defaults[data] or ("null", None))
            return [text for at, item in given if len(at) > 1 and at[-1] == "body"
                    for text in _body_text(item, f"{self.where} variable ${'.'.join(at)}")]
        return []


def _read_graphql(call: _Api, label: str, cwd: str | None, whole: bool,
                  nests: bool) -> "Result | str":
    """What a GraphQL call posts. nests says whether gh sends the fields
    other than query and operationName as the query's variables, which it
    does only for the endpoint written exactly `graphql`. For any other
    spelling it sends them beside the query, so any such field makes the
    call unreadable: one such as `variables[b]` sets the variables GitHub
    runs."""
    query: object = None
    leaves: Leaves = []
    for path_given in call.inputs:
        given = _input_json(path_given, cwd, whole)
        if isinstance(given, dict):
            given = cast(dict[str, object], given)
            query = given.get("query", query)
            _flatten(given.get("variables") or {}, (), leaves)
    # With --input, gh sends the file as the body and adds the fields to the
    # URL's query string, so which query or variables GitHub runs is unknown.
    if call.inputs and call.fields:
        raise _Missing("fields beside --input go into the URL, so the query GitHub runs "
                       "cannot be checked. " + ACCEPTED)
    for kind, raw in call.fields:
        key, eq, value = raw.partition("=")
        text = _field_value(kind, value, cwd, whole) if eq else None
        if key == "query":
            query = text
        elif key != "operationName":
            if not nests:
                raise _Missing(f"gh sends the field {key} beside the query, where it may set "
                               "the variables GitHub runs. " + ACCEPTED)
            leaves.append((_segments(key), text))
    if not isinstance(query, str):
        raise _Missing("the GraphQL query is not given as text. " + ACCEPTED)
    operations, fragments = _Parser(query).document()
    if not any(kind == "mutation" for kind, _, _ in operations):
        return "read"
    posts: list[Post] = []
    for kind, defaults, selections in operations:
        if kind != "mutation":
            continue
        for name, arguments in _top_fields(selections, fragments, 0):
            if name in MUTATIONS:
                where = f"{label} {name}"
                bodies = _Bodies(leaves, defaults, where)
                posts += [Post(f"{where} body", text) for argument, value in arguments
                          for text in bodies.walk(argument, value)]
    return posts


def _top_fields(selections: list[Selection], fragments: dict[str, list[Selection]],
                depth: int) -> list[tuple[str, list[tuple[str, Value]]]]:
    """A mutation's top-level fields, through fragments, as (name,
    arguments)."""
    if depth > 10:
        raise _Missing("the GraphQL query nests its fragments too deeply. " + ACCEPTED)
    found: list[tuple[str, list[tuple[str, Value]]]] = []
    for selection in selections:
        if selection[0] == "field":
            found.append((selection[1], selection[2]))
        elif selection[0] == "inline":
            found += _top_fields(selection[1], fragments, depth + 1)
        elif selection[1] in fragments:
            found += _top_fields(fragments[selection[1]], fragments, depth + 1)
        else:
            raise _Missing(f"the GraphQL fragment {selection[1]} is not defined. " + ACCEPTED)
    return found


# -- a whole command line --------------------------------------------------

def _split(command: str) -> tuple[list[tuple[list[Word], bool]], bool] | None:
    """The line as gh_shell's _commands splits it: (simple commands,
    grouped), grouped being True when input may reach more than one simple
    command. A line that does not split is tried again with each unquoted
    `$(` read as a subshell (_unsubstitute). None when the line holds a form
    the reader cannot split exactly."""
    read = _commands(command)
    if read is None and "$(" in command:
        unsubstituted = _unsubstitute(command)
        read = _commands(unsubstituted) if unsubstituted is not None else None
    return read


def _api(command: _Command, cwd: str | None, whole: bool) -> "Result | str":
    if command.api is None:
        command.api = _read_api(_strip_reserved(command.words), cwd, whole)
    return command.api


def _is_api_read(command: _Command, cwd: str | None, whole: bool) -> bool:
    words = _strip_reserved(command.words)
    return _is_api(words) and _api(command, cwd, whole) == "read"


def _as_result(found: "Result | str") -> Result:
    if isinstance(found, str):
        return NoPost()
    if isinstance(found, list) and not found:
        return NoPost()
    return found


def gh_command(command: str) -> list[str] | None:
    """The arguments after `gh`, less any leading -R and its value, when
    the line is one whole gh command, run directly or through github-app's
    script; else None."""
    whole = _whole_command(command)
    if whole is None or whole.discord:
        return None
    plain = _words(" ".join(source for _, source in whole.words))
    if not plain or plain[0] != ("gh", False):
        return None
    return [text for text, _ in _gh_args(plain)]


def _whole_command(command: str) -> _Command | None:
    """The one simple command the line is, when it is one whole command:
    a gh call or a call of discord-bot's script, with nothing beside it but
    assignments of either script's path, and no redirection, pipe, subshell
    or substitution."""
    ops = _top_level(command)
    if ops is None or not ops <= {";", "&&"}:
        return None
    split = _split(command)
    if split is None or split[1]:
        return None
    resolved = [c for c in _resolve(split[0]) if c.words]
    if len(resolved) != 1 or not (
            resolved[0].discord or _is_gh(resolved[0].words)):
        return None
    return resolved[0]


def read_command(command: str, cwd: str | None) -> Result:
    """What a Bash command line posts (gh-post spec)."""
    if not (GH_TEXT.search(command) or DISCORD_TEXT.search(command)) \
            or runs_only_prose(command):
        return NoPost()
    split = _split(command)
    if split is None:
        if _mentions(command) or GH_API_TEXT.search(command):
            return _not_allowed("gh")
        return NoPost()
    commands, grouped = split
    resolved = _resolve(commands)
    whole = _whole_command(command)
    if whole is not None:
        resolved = [whole]
    is_whole = whole is not None
    if not _mentions(command):
        if not GH_API_TEXT.search(command):
            return NoPost()
        # A gh api read is no gh post verb. Drop the reads from the line's
        # text; the line mentions a gh post verb only when `gh` followed by
        # `api` is still there.
        rest = command if "<<" in command else " ".join(
            source for c in resolved if not _is_api_read(c, cwd, is_whole)
            for _, source in c.words)
        if not GH_API_TEXT.search(rest):
            return NoPost()
    if whole is not None:
        if whole.discord:
            found = _read_discord(whole.words, cwd)
            return found if isinstance(found, Unreadable) or found else NoPost()
        if _is_api(whole.words):
            return _as_result(_api(whole, cwd, True))
        plain = _words(" ".join(source for _, source in whole.words))
        if not plain:
            return _not_allowed("gh")
        found = _read_gh(plain, cwd)
        return found if isinstance(found, Unreadable) or found else NoPost()
    return _read_line(resolved, grouped, cwd)


def _read_line(resolved: list[_Command], grouped: bool, cwd: str | None) -> Result:
    """What a line of several commands, or of one beside a redirection,
    posts: no post when each simple command sends none; the posts of a
    single gh api write when its fields read no file and no other command
    mentions a gh post verb; otherwise unreadable."""
    api_posts: list[list[Post]] = []
    mentions = 0
    for command in resolved:
        if command.discord:
            if command.fed:
                return _fed_blocker(DISCORD_SCRIPT)
            if _read_discord(command.words, cwd):
                return _not_allowed(f"`{DISCORD_SCRIPT} "
                                    f"{' '.join(src for _, src in command.words)}`")
            continue
        words = _strip_reserved(command.words)
        if all(source in CLOSERS for _, source in words):
            continue
        names = [text.lstrip("=").rsplit("/", 1)[-1] for text, _ in words]
        source = " ".join(src for _, src in words)
        api_read = _is_api(words) and _api(command, cwd, False) == "read"
        if _mentions(source) or (GH_API_TEXT.search(source) and not api_read):
            mentions += 1
        if grouped and names[0] not in DATA_COMMANDS:
            return GROUPED
        if command.fed and names[0] not in DATA_COMMANDS:
            plain = _words(source) if _is_gh(words) else None
            args = _gh_args(plain) if plain else []
            if not api_read and (len(args) < 2 or args[1][0] not in NO_TEXT_VERBS.get(
                    args[0][0], ())):
                return _fed_blocker(names[0])
        if command.unassigned and ("gh" in names or {"post", "edit"} & set(names)):
            return _unassigned(command.unassigned)
        if names[0] in PYTHONS and DISCORD_SCRIPT in names:
            return _not_allowed(f"`{source}`")
        if "gh" not in names:
            if (GH_TEXT.search(source) or DISCORD_TEXT.search(source)) \
                    and names[0] not in DATA_COMMANDS:
                return _not_allowed(f"`{words[0][1]}`")
            continue
        if not _is_gh(words):
            return _not_allowed(f"`{source}`")
        if _is_api(words):
            found = _api(command, cwd, False)
            if isinstance(found, Unreadable):
                return found
            if isinstance(found, list) and found:
                api_posts.append(found)
            continue
        plain = _words(source)
        if not plain:
            return _not_allowed(f"`{source}`")
        if POST_WORDS.search(" ".join(text for text, _ in plain)) and _read_gh(plain, cwd):
            return _not_allowed(f"`{source}`")
    if not api_posts:
        return NoPost()
    if len(api_posts) > 1 or mentions > 1:
        return Unreadable("a gh api post stands beside another command that mentions a gh "
                          "post verb, so the hook cannot tell which text is posted. " + ACCEPTED)
    return api_posts[0]


# -- a tool call -----------------------------------------------------------

BODY_KEYS = {"body", "comment"}


def body_fields(value: object, path: str = "") -> list[Post]:
    """A Post for every non-empty string under a key named body or comment,
    at any depth, in a GitHub MCP tool's input."""
    found: list[Post] = []
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            where = f"{path}.{key}" if path else str(key)
            if str(key).lower() in BODY_KEYS and isinstance(item, str) and item.strip():
                found.append(Post(where, item))
            else:
                found.extend(body_fields(item, where))
    elif isinstance(value, list):
        for index, item in enumerate(cast(list[object], value)):
            found.extend(body_fields(item, f"{path}[{index}]"))
    return found


def _mcp(tool_input: object) -> Result:
    return body_fields(tool_input) or NoPost()


def read_posts(payload: dict[str, Any], host: str) -> Result:
    """What the hook payload's tool call posts. host is "claude" or
    "cursor", as prose's hook names it, since the two hosts send different
    payload shapes. A call that posts several bodies,
    such as a review with comments, gives one Post per body."""
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) else None
    if host == "cursor":
        if "command" in payload and "tool_name" not in payload:
            command = payload.get("command")
            return read_command(command if isinstance(command, str) else "", cwd)
        server = payload.get("mcp_server_name")
        tool_input: object = payload.get("tool_input")
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except ValueError:
                tool_input = {}
        return _mcp(tool_input) if isinstance(server, str) and "github" in server.lower() \
            else NoPost()
    tool = payload.get("tool_name")
    tool = tool if isinstance(tool, str) else ""
    tool_input: object = payload.get("tool_input") or {}
    if GITHUB_MCP.match(tool):
        return _mcp(tool_input)
    if tool == "Bash" and isinstance(tool_input, dict):
        command = cast(dict[str, object], tool_input).get("command")
        return read_command(command if isinstance(command, str) else "", cwd)
    return NoPost()
