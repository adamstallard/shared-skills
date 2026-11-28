"""The shared post reader tells a hook what a tool call posts on a GitHub
issue or pull request, in a Discord message, or on Linear. It gives one of
three answers: the posts, no post, or that the call is unreadable. Hooks call
read_posts; the gh-post spec sets the rules.

The reader is default-deny. It reads a body only from the command lines
CANONICAL_FORMS lists, each a single simple command whose words are all
literal, run directly or through github-app's script, and from a GitHub
or Linear MCP tool's text fields. Any other call that could post is unreadable, unless every
command in its line provably sends no text.

It splits commands with gh_shell.py beside it. It tracks the variables that
name github-app's script with gh_shell's app_assignments and app_command and
handbacks.py's forget_scripts; it tracks those that name discord-bot's
script in this module. Standard library only.
"""

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from gh_shell import (
    APP_SCRIPT,
    CLOSERS,
    DATA_COMMANDS,
    NO_TEXT_VERBS,
    PYTHONS,
    RESERVED,
    VARIABLE,
    _commands,  # pyright: ignore[reportPrivateUsage]
    _word,  # pyright: ignore[reportPrivateUsage]
    app_assignments,
    app_command,
)
from handbacks import forget_scripts

# A shell word as gh_shell gives it: (text after quote removal, the word as
# written, quotes included).
Word = tuple[str, str]
Surface = Literal["github", "discord", "linear"]


@dataclass(frozen=True)
class Post:
    """One body the call sends. The field `where` is the body's label in the
    hooks' block messages, such as `gh pr comment --body-file c.md` or
    `comments[0].body` of a review. The field `surface` names the service it
    is posted to. The field `via_github_app` says whether github-app's script
    sends it."""

    where: str
    body: str
    surface: Surface = "github"
    via_github_app: bool = False


@dataclass(frozen=True)
class NoPost:
    """The call sends no post."""


@dataclass(frozen=True)
class Unreadable:
    """The call may send a post the reader cannot read; why says what stops
    it. The reader builds every one through _blocked, so why ends with
    CANONICAL_FORMS; prose's posting hook and the inquisitor skill's post
    hook print it when they block."""

    why: str


Result = list[Post] | NoPost | Unreadable

CANONICAL_FORMS = """\
The hook reads a post only in one of these forms, as the whole command line, every word \
plain text the shell does not expand (or run through github-app's script, \
`python3 <path>/github_app.py [--identity <name>] gh …`):
  gh pr comment <number> --body-file <file>      (or gh issue comment; or --body '<text>')
  gh pr create --title <title> --body-file <file>   (or gh issue create)
  gh pr edit <number> --body-file <file>          (or gh issue edit)
  gh pr review <number> --approve|--request-changes|--comment --body-file <file>
  gh pr close <number> --comment '<text>'         (or reopen; or gh issue close/reopen)
  gh api <endpoint> -X <POST|PATCH> --input <file.json>   (an issue, pull request, comment or \
review endpoint, written repos/<owner>/<repo>/…; the JSON's body, and a review's comments[].body)
  python3 <path>/discord_bot.py [--identity <name>] post|edit … --message-file <file>
Options beside the body: --title, --repo, --base, --head, --draft, --label, --assignee, \
--reviewer, --milestone, and for edit gh's --add-… and --remove-… options for reviewers, \
labels, assignees and projects and --remove-milestone, each written long with its value as \
the next word (--draft and --remove-milestone take none). A file must exist. Write the text to a file first, then post it with one of these commands on its own."""


def _blocked(why: str) -> Unreadable:
    return Unreadable(f"{why}\n\n{CANONICAL_FORMS}")


def _not_canonical(where: str) -> Unreadable:
    return _blocked(f"{where}: this call may post, and it is not one of the forms the hook "
                    "reads, so what it posts cannot be checked.")


def _fed_blocker(name: str) -> Unreadable:
    return _blocked(
        f"`{name}` reads a pipe or an input redirection (<, <<, <<<), so what it runs or posts "
        "cannot be checked. Only a data command (echo, cat, grep, head, python3 …), a gh pr or "
        "gh issue subcommand that takes no body, such as gh pr view, or a gh api read may read "
        "one.")


GROUPED = (
    "a pipe or an input redirection feeds a group, loop or subshell, so what it runs or posts "
    "cannot be checked unless every command in it is a data command (echo, cat, grep, head, "
    "python3 …).")


def _unassigned(name: str) -> Unreadable:
    return _blocked(
        f"`${name}` is not assigned github-app's or discord-bot's script path in this command, "
        "so the hook cannot tell which script runs. Assign the variable in the same command "
        f"({name}=<path>/github_app.py; python3 \"${name}\" gh …) or write the script's path.")


# -- what a line mentions, before it is split --------------------------------

# A word counts however the shell may join it (gh-post spec: a command's
# words count whether quoted or not): a word pattern lets quotes, `$`,
# backslashes and backslash-newlines sit between its letters, as in g''h,
# co$'m'ment or g\\h. The reader searches the raw line so, instead of
# rewriting it first: a rewrite guesses how quotes pair and where a
# backslash-newline joins, and some mix defeats every guess, such as an
# escaped backslash before a newline beside a real continuation.
SPLIT = r"(?:\\\n|[\\'\"$])*"


def _spelled(word: str) -> str:
    return SPLIT.join(re.escape(char) for char in word)


def _whole(*words: str) -> str:
    """A pattern matching any of words, spelled as _spelled allows, as a
    whole word: no letter, digit or `_` just before it, and none of those or
    `-` just after, so `--comment` matches but `--comments` does not."""
    return rf"(?<!\w)(?:{'|'.join(_spelled(word) for word in words)})(?![\w-])"


PR_VERBS = ("create", "new", "edit", "comment", "review", "revert", "close", "reopen")
ISSUE_VERBS = ("create", "new", "edit", "comment", "close", "reopen")
GH_WORD = re.compile(_whole("gh"))
PR_WORD = re.compile(_whole("pr"))
ISSUE_WORD = re.compile(_whole("issue"))
PR_VERB = re.compile(_whole(*PR_VERBS))
ISSUE_VERB = re.compile(_whole(*ISSUE_VERBS))
# `api` counts with no `/` or `.` beside it, so `gh repo view o/api` holds no
# gh api call.
API_WORD = re.compile(rf"(?<![\w/.]){_spelled('api')}(?![\w/.-])")
DISCORD_SCRIPT = "discord_bot.py"
DISCORD_MODULE = "discord_bot"
# A word ending in discord_bot.py (DISCORD_SCRIPT), or the word discord_bot
# itself, as `python3 -m discord_bot` names it.
DISCORD_WORD = re.compile(rf"{_spelled(DISCORD_SCRIPT)}(?![\w-])"
                          rf"|(?<![\w/.-]){_spelled(DISCORD_MODULE)}(?![\w./-])")
POST_OR_EDIT = re.compile(_whole("post", "edit"))


def _in_order(text: str, *patterns: re.Pattern[str]) -> bool:
    """Whether each pattern matches in text after the one before it. Taking
    the earliest match of each is enough, and keeps the scan linear: a
    single regex with `[\\s\\S]*` between the words backtracks in cubic
    time on a long line of gh and pr words with no verb."""
    at = 0
    for pattern in patterns:
        found = pattern.search(text, at)
        if not found:
            return False
        at = found.end()
    return True


def _post_words(text: str) -> bool:
    return _in_order(text, GH_WORD, PR_WORD, PR_VERB) \
        or _in_order(text, GH_WORD, ISSUE_WORD, ISSUE_VERB)


def _api_words(text: str) -> bool:
    return _in_order(text, GH_WORD, API_WORD)


def _discord_words(text: str) -> bool:
    """A word ending in discord-bot's script, then anywhere later its post or
    edit, which the gh-post spec counts as a gh post verb (*The gh post
    verbs are a closed list*)."""
    return _in_order(text, DISCORD_WORD, POST_OR_EDIT)


def _names_gh(text: str) -> bool:
    return bool(GH_WORD.search(text))


def _mentions(text: str) -> bool:
    """Whether text mentions a gh post verb other than a gh api call: gh pr
    or gh issue with a post verb, or discord-bot's post or edit."""
    return _post_words(text) or _discord_words(text)


def _substitutions(command: str) -> list[tuple[int, int]]:
    """The spans of the line's outermost command substitutions, `…` and
    $(…). The scan takes a backslash as the only escape and reads no quote,
    comment or heredoc: a scan that misreads one loses track of what is
    quoted, and a later substitution goes unseen. So a `)` or backtick in a
    quote, comment, heredoc or case pattern may end a span early;
    _joined_by_substitution tries each later end for such a span."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(command)
    while i < n:
        if command[i] == "\\":
            i += 2
        elif command[i] == "`" or command.startswith("$(", i):
            end = _substitution_end(command, i)
            spans.append((i, end))
            i = end
        else:
            i += 1
    return spans


def _substitution_end(command: str, start: int) -> int:
    """Where the substitution starting at start ends, counting parentheses
    and reading backslashes alone."""
    n = len(command)
    closer = "`" if command[start] == "`" else ")"
    depth, i = 0, start + 1
    while i < n:
        char = command[i]
        if char == "\\":
            i += 2
            continue
        if closer == "`":
            if char == "`":
                return i + 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


# A span holding a quote, a backtick, `#`, `<<` or `case` might end at a
# later `)` or backtick than the one the scan found.
UNSURE = re.compile(r"[`'\"#]|<<|\bcase\b")
MOST_ENDS = 64


def _joined_by_substitution(command: str) -> bool:
    """Whether a command substitution joins a word's letters, as in g$()h,
    g"$(true)"h or co`:`mment, and the line with each such substitution
    dropped mentions a gh post verb or a gh api call. gh_shell splits a word
    at its `$(`, so none of the simple commands it returns shows the joined
    word, and only this check catches it.

    A substitution joins letters when, past any quotes beside it, a letter,
    digit or `_` touches it, so `--body '$(x)'` and `-m "$(cat <<'EOF' …)"`
    join none. One holding a quote, a backtick, a comment, a heredoc or a
    case pattern may end at any later `)` (or backtick), so each such end
    with a letter after it is tried, as well as the end the scan found. Past
    MOST_ENDS tries, the function returns True without checking for a
    mention."""
    n = len(command)

    def letter_beside(at: int, step: int) -> bool:
        while 0 <= at < n and command[at] in "'\"":
            at += step
        return 0 <= at < n and (command[at].isalnum() or command[at] == "_")

    joined = [(start, end) for start, end in _substitutions(command)
              if letter_beside(start - 1, -1) or letter_beside(end, 1)]
    if not joined:
        return False
    sure = [span for span in joined if not UNSURE.search(command, span[0] + 1, span[1])]
    tries: list[list[tuple[int, int]]] = [sure]
    for start, end in joined:
        if (start, end) in sure:
            continue
        closer = "`" if command[start] == "`" else ")"
        ends = {end} | {k + 1 for k in range(start + 1, n)
                        if command[k] == closer and letter_beside(k + 1, 1)}
        tries.extend(sure + [(start, k)] for k in sorted(ends))
        if len(tries) > MOST_ENDS:
            return True
    for spans in tries:
        kept: list[str] = []
        at = 0
        for start, end in sorted(spans):
            if end <= at:
                continue
            kept.append(command[at:max(start, at)])
            at = end
        text = "".join(kept) + command[at:]
        if _mentions(text) or _api_words(text):
            return True
    return False


def runs_only_prose(command: str) -> bool:
    """Whether the line is one simple command that runs prose.py, so text in
    its arguments (such as a --goals value that mentions `gh pr create`) is
    not a post (gh-post spec: *A command that only runs prose's script sends
    no post*). Redirections are allowed; a substitution, a newline or a
    second command could run more."""
    if "`" in command or "$(" in command or "\n" in command:
        return False
    read = _commands(command)
    if read is None or len(read[0]) != 1:
        return False
    words = [text for text, _ in read[0][0][0]]
    program = words[1] if words[0] in PYTHONS and len(words) > 1 else words[0]
    return program == "prose.py" or program.endswith("/prose.py")


def literal(source: str) -> bool:
    """Whether a word, as written, is one the shell does not expand: no `$`,
    backtick or backslash outside single quotes, and no `*`, `?`, `[`, `{`
    or `~` outside quotes (gh-post spec: *A literal word is one the shell
    does not expand*). A word starting with an unquoted `=`, which zsh
    replaces with a command's path, is not literal either."""
    if re.match(r"(?:''|\"\")*=", source):
        return False
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


# -- one simple command, a github-app call read as the command it runs ------

@dataclass
class _Command:
    words: list[Word]
    fed: bool
    app: bool = False
    # The variable a `python3 "$G" gh …` names, when no command before it
    # assigned github-app's or discord-bot's script to it.
    unassigned: str | None = None
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
    *The reader reads posts sent through the github-app skill*)."""
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


def _strip_reserved(words: list[Word]) -> list[Word]:
    while words and words[0][1] in RESERVED:
        words = words[1:]
    return words


def _is_gh(words: list[Word]) -> bool:
    return bool(words) and words[0][0] == "gh" and literal(words[0][1])


def _is_api(words: list[Word]) -> bool:
    return _is_gh(words) and len(words) > 1 and words[1][0] == "api" \
        and literal(words[1][1])


def _read_file(text: str, cwd: str | None) -> str | None:
    """The text of the regular file at path text, or None; a relative path
    is resolved against cwd. `-` is
    standard input to gh and discord-bot, never a file. A device, pipe or
    directory is not read: gh would read from it what the hook cannot see."""
    if text == "-" or not text:
        return None
    target = pathlib.Path(text)
    if not target.is_absolute():
        target = pathlib.Path(cwd or ".") / target
    try:
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):  # ValueError: a NUL byte
        return None


# -- gh pr and gh issue ----------------------------------------------------

# The long options that carry a gh pr or gh issue command's text, or take it
# from somewhere the reader cannot see (commits, a template, an editor, a
# saved draft, the browser), and the short letters gh gives them. gh's flag
# parser, pflag, does not abbreviate long options, so each is matched whole.
TEXT_LONG = {"body", "body-file", "comment", "fill", "fill-first", "fill-verbose", "template",
             "editor", "web", "recover"}
TEXT_SHORT = set("bFcfTew")


def _sends_text(args: list[Word]) -> bool:
    """Whether a gh pr or gh issue command's arguments hold an option that
    carries text (gh-post spec: *A line whose simple commands send no text is
    no post*). A short group holding any such letter counts, though an
    earlier letter might take it as its value."""
    for text, _ in args:
        if text.startswith("--"):
            if text[2:].partition("=")[0] in TEXT_LONG:
                return True
        elif text.startswith("-") and TEXT_SHORT & set(text[1:]):
            return True
    return False


PR_ISSUE = {"pr": {"comment", "create", "edit", "review", "close", "reopen"},
            "issue": {"comment", "create", "edit", "close", "reopen"}}
VALUE_OPTIONS = {"--title", "--repo", "--base", "--head", "--label", "--assignee", "--reviewer",
                 "--milestone"}
# gh pr edit's and gh issue edit's options that add or remove a reviewer,
# label, assignee or project, each taking a value. --remove-milestone is left
# out: gh gives it no value, so _read_gh reads it as a flag. Were the reader
# to take the next word as its value, a body option there would go unread
# while gh sends the body.
EDIT_OPTIONS = {
    "pr": {"--add-reviewer", "--remove-reviewer", "--add-label", "--remove-label",
           "--add-assignee", "--remove-assignee", "--add-project", "--remove-project"},
    "issue": {"--add-label", "--remove-label", "--add-assignee", "--remove-assignee",
              "--add-project", "--remove-project"}}
REVIEW_MODES = {"--approve", "--request-changes", "--comment"}


def _gh_args(words: list[Word]) -> list[Word]:
    """words[1:] for a gh command, without a leading -R or --repo and its
    value, as gh_shell's _gh_args gives them."""
    args = words[1:]
    while args and (args[0][0] in ("-R", "--repo") or args[0][0].startswith(("--repo=", "-R"))):
        args = args[2:] if args[0][0] in ("-R", "--repo") else args[1:]
    return args


def _gh_text(words: list[Word]) -> Literal["none", "text", "unreadable"]:
    """Whether a gh command sends no text, may send text, or is unreadable,
    for a line that mentions a gh post verb. Only gh pr and gh issue are
    read: any other gh command, such as gh alias or gh release, is unreadable
    (gh-post spec: *A line whose simple commands send no text is
    no post*). A subcommand gh_shell's NO_TEXT_VERBS lists sends none, whatever its
    arguments; any other sends none when every word is literal and none
    carries text."""
    args = _gh_args(words)
    if not args or not literal(args[0][1]) or args[0][0] not in PR_ISSUE:
        return "unreadable"
    if len(args) < 2 or not literal(args[1][1]):
        return "unreadable"
    if args[1][0] in NO_TEXT_VERBS[args[0][0]]:
        return "none"
    if not all(literal(source) for _, source in words):
        return "unreadable"
    return "text" if _sends_text(args) else "none"


def _read_gh(words: list[Word], cwd: str | None, app: bool) -> Result:
    """The body a whole-line gh pr or gh issue command posts, read only in a
    canonical form (gh-post spec: *The canonical gh pr and gh issue posts are
    a closed list*)."""
    texts = [text for text, _ in words]
    if len(texts) < 3 or texts[1] not in PR_ISSUE:
        return _not_canonical("gh")
    noun, verb = texts[1], texts[2]
    where = f"gh {noun} {verb}"
    if verb not in PR_ISSUE[noun]:
        return _not_canonical(where)
    i = 3
    if verb != "create":
        if len(texts) < 4 or not texts[3].isdigit() or not texts[3].isascii():
            return _not_canonical(where)
        i = 4
    body_options = {"--comment"} if verb in ("close", "reopen") else {"--body", "--body-file"}
    bodies: list[tuple[str, str]] = []
    modes: list[str] = []
    while i < len(texts):
        option = texts[i]
        if verb == "review" and option in REVIEW_MODES:
            modes.append(option)
            i += 1
        elif option == "--draft" and verb == "create" \
                or option == "--remove-milestone" and verb == "edit":
            i += 1
        elif option in VALUE_OPTIONS or option in body_options or (
                verb == "edit" and option in EDIT_OPTIONS[noun]):
            if i + 1 >= len(texts):
                return _not_canonical(where)
            if option in body_options:
                bodies.append((option, texts[i + 1]))
            i += 2
        else:
            return _not_canonical(where)
    if len(bodies) != 1 or (verb == "review" and len(modes) != 1):
        return _not_canonical(where)
    option, value = bodies[0]
    if option != "--body-file":
        return [Post(f"{where} {option}", value, via_github_app=app)]
    body = _read_file(value, cwd)
    if body is None:
        return _blocked(f"{where} --body-file {value}: {value} could not be read as a file.")
    return [Post(f"{where} --body-file {value}", body, via_github_app=app)]


# -- gh api ----------------------------------------------------------------

NAME = r"(?!\.{1,2}/)[A-Za-z0-9_.-]+"
# The canonical gh api posts: each endpoint pattern with its one method
# (gh-post spec: *The canonical gh api posts are a closed list*).
API_POSTS = [(re.compile(rf"repos/{NAME}/{NAME}/{tail}"), method) for tail, method in (
    ("issues", "POST"), (r"issues/[0-9]+", "PATCH"), (r"issues/[0-9]+/comments", "POST"),
    (r"issues/comments/[0-9]+", "PATCH"), ("pulls", "POST"), (r"pulls/[0-9]+", "PATCH"),
    (r"pulls/[0-9]+/comments", "POST"), (r"pulls/comments/[0-9]+", "PATCH"),
    (r"pulls/[0-9]+/reviews", "POST"))]
REVIEWS = re.compile(rf"repos/{NAME}/{NAME}/pulls/[0-9]+/reviews")
# gh api's options a read may hold beside -X GET and -f: those that take a
# value, and switches. Each written alone, its value the next word.
READ_VALUES = {"--jq", "-q", "--template", "-t", "--cache", "--hostname", "--preview", "-p"}
READ_SWITCHES = {"--paginate", "--slurp", "--include", "-i", "--silent", "--verbose"}
PLACEHOLDER = re.compile(r"\{(?:owner|repo|branch)\}")
MUTATION = re.compile(r"(?<![_0-9A-Za-z])mutation(?![_0-9A-Za-z])", re.I)


def _api_read(words: list[Word]) -> bool:
    """Whether a gh api call is a read (gh-post spec: *A gh api call is a
    read only in a plain form*): its endpoint, `-X GET` as exactly those words, `-f`
    fields and read-only options, every word literal but for an endpoint's
    `?` and gh's placeholders. With no -X, gh sends a call with a field as
    POST, so such a call is a read only with no field; graphql, which gh
    always sends as POST, is a read when its one query holds no word
    mutation."""
    endpoints: list[Word] = []
    fields: list[str] = []
    methods: list[str] = []
    i = 2
    while i < len(words):
        text, source = words[i]
        if text in ("-X", "-f") or text in READ_VALUES:
            if i + 1 >= len(words) or not literal(words[i + 1][1]):
                return False
            value = words[i + 1][0]
            if text == "-X":
                methods.append(value if words[i + 1][1] == value else "")
            elif text == "-f":
                fields.append(value)
            i += 2
            continue
        if text in READ_SWITCHES:
            i += 1
            continue
        if text.startswith("-") or not literal(PLACEHOLDER.sub("", source).replace("?", "")):
            return False
        endpoints.append((text, source))
        i += 1
    if len(endpoints) != 1 or methods not in ([], ["GET"]):
        return False
    if endpoints[0] == ("graphql", "graphql"):
        queries = [f.partition("=")[2] for f in fields if f.partition("=")[0] == "query"]
        return len(queries) == 1 and not MUTATION.search(queries[0])
    return bool(methods) or not fields


class _Bad(Exception):
    pass


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise _Bad("it holds a key twice")
    return dict(pairs)


def _read_api(words: list[Word], cwd: str | None, app: bool) -> Result:
    """The bodies a whole-line gh api write posts, read only in a canonical
    form: `gh api <endpoint> -X <method> --input <file>`, in any order."""
    texts = [text for text, _ in words]
    rest = texts[2:]
    shown = " ".join(source for _, source in words)
    if len(rest) != 5 or not all(literal(source) for _, source in words):
        return _not_canonical(f"`{shown}`")
    method = file = endpoint = None
    i = 0
    while i < len(rest):
        if rest[i] in ("-X", "--input") and i + 1 < len(rest):
            if rest[i] == "-X" and method is None:
                method = rest[i + 1]
            elif rest[i] == "--input" and file is None:
                file = rest[i + 1]
            else:
                return _not_canonical(f"`{shown}`")
            i += 2
        elif endpoint is None and not rest[i].startswith("-"):
            endpoint = rest[i]
            i += 1
        else:
            return _not_canonical(f"`{shown}`")
    if endpoint is None or file is None or not any(
            pattern.fullmatch(endpoint) and method == want for pattern, want in API_POSTS):
        return _not_canonical(f"`{shown}`")
    where = f"gh api {endpoint} --input {file}"
    text = _read_file(file, cwd)
    if text is None:
        return _blocked(f"{where}: {file} could not be read as a file.")
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates)
        if not isinstance(data, dict):
            raise _Bad("it is not a JSON object")
        data = cast(dict[str, object], data)
        posts: list[Post] = []
        if "body" in data:
            if not isinstance(data["body"], str):
                raise _Bad("its body is not a string")
            posts.append(Post(f"{where} body", data["body"], via_github_app=app))
        if REVIEWS.fullmatch(endpoint) and "comments" in data:
            comments = data["comments"]
            if not isinstance(comments, list):
                raise _Bad("its comments are not a list")
            for k, item in enumerate(cast(list[object], comments)):
                body = cast(dict[str, object], item).get("body") \
                    if isinstance(item, dict) else None
                if not isinstance(body, str):
                    raise _Bad(f"comments[{k}].body is not a string")
                posts.append(Post(f"{where} comments[{k}].body", body, via_github_app=app))
        if not posts:
            raise _Bad("it holds no body")
        return posts
    except ValueError:
        return _blocked(f"{where}: {file} is not JSON.")
    except _Bad as bad:
        return _blocked(f"{where}: {file} cannot be read as a post: {bad}.")


# -- discord-bot -------------------------------------------------------------

DISCORD_QUIET = {"delete", "read", "thread", "check", "invite-url", "store-token",
                 "forget-token"}


def _read_discord(words: list[Word], cwd: str | None) -> Result:
    """The message a whole-line discord-bot call posts: none for a
    subcommand that posts no text; for post and edit, the file that the
    one `--message-file <file>` names, with no other option starting
    `--message` except `--message-id` (gh-post spec: *The reader reads
    discord-bot's post and edit only from a message file*)."""
    texts = [text for text, _ in words]
    if texts[0] in DISCORD_QUIET and literal(words[0][1]):
        return NoPost()
    if texts[0] not in ("post", "edit") or not all(literal(source) for _, source in words):
        return _not_canonical("discord-bot")
    where = f"discord-bot {texts[0]}"
    given = [k for k, text in enumerate(texts) if text == "--message-file"]
    if len(given) != 1 or given[0] + 1 >= len(texts) \
            or texts[given[0] + 1].startswith("-") or any(
                text.startswith("--message") and text != "--message-id"
                and not text.startswith("--message-id=")
                for k, text in enumerate(texts) if k != given[0]):
        return _not_canonical(where)
    file = texts[given[0] + 1]
    body = _read_file(file, cwd)
    if body is None:
        return _blocked(f"{where} --message-file {file}: {file} could not be read as a file.")
    return [Post(f"{where} --message-file {file}", body, "discord")]


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


def _whole_command(command: str) -> _Command | None:
    """The one simple command the line is: a gh call or a call of
    discord-bot's script, with nothing beside it but assignments of either
    script's path, and no redirection, pipe, subshell or substitution."""
    ops = _top_level(command)
    if ops is None or not ops <= {";", "&&"}:
        return None
    split = _commands(command)
    if split is None or split[1]:
        return None
    resolved = [c for c in _resolve(split[0]) if c.words]
    if len(resolved) != 1 or not (resolved[0].discord or _is_gh(resolved[0].words)):
        return None
    return resolved[0]


def gh_command(command: str) -> list[str] | None:
    """The arguments after `gh`, less any leading -R and its value, when
    the line is one whole gh command, run directly or through github-app's
    script; else None."""
    whole = _whole_command(command)
    if whole is None or whole.discord:
        return None
    return [text for text, _ in _gh_args(whole.words)]


def _names(words: list[Word]) -> list[str]:
    return [text.lstrip("=").rsplit("/", 1)[-1] for text, _ in words]


def _quiet_gh(words: list[Word]) -> bool:
    """Whether input is allowed to reach a gh command: a gh pr or gh issue
    subcommand in gh_shell's NO_TEXT_VERBS, or a gh api read (gh-post spec: *Input to a
    no-post line reaches only data commands*)."""
    if _is_api(words):
        return _api_read(words)
    args = _gh_args(words)
    return len(args) >= 2 and literal(args[0][1]) and literal(args[1][1]) \
        and args[1][0] in NO_TEXT_VERBS.get(args[0][0], ())


def _input_check(resolved: list[_Command], grouped: bool) -> Unreadable | None:
    """For a line that mentions no gh post verb: unreadable when input from
    a pipe or redirection in the line reaches several commands one of which
    names gh, or reaches a discord-bot
    call or a gh command that is not quiet (_quiet_gh)."""
    for command in resolved:
        words = _strip_reserved(command.words)
        if not words or not (command.fed or grouped):
            continue
        if "gh" not in _names(words) and not command.discord:
            continue
        if grouped:
            return _blocked(GROUPED)
        if command.discord or not _is_gh(words) or not _quiet_gh(words):
            return _fed_blocker(words[0][0] or words[0][1])
    return None


def read_command(command: str, cwd: str | None) -> Result:
    """What a Bash command line posts (gh-post spec)."""
    if not (_names_gh(command) or _discord_words(command) or "$(" in command
            or "`" in command) or runs_only_prose(command):
        return NoPost()
    if _joined_by_substitution(command):
        return _not_canonical("this command")
    split = _split(command)
    if split is None:
        # A word spelled with escapes, such as co$'\x6d'ment, passes
        # _mentions and _api_words unseen; the spec leaves it open. Blocking
        # every line that names gh and holds $'…' would block ordinary reads
        # such as `gh pr view 5 | tr $'\n' ' '`, which the spec says send no
        # post.
        if _mentions(command) or _api_words(command):
            return _not_canonical("this command")
        return NoPost()
    commands, grouped = split
    resolved = _resolve(commands)
    if not _mentions(command):
        # A gh api read is no gh post verb, so drop the reads and see whether
        # a gh api call is still left. A line holding `<<` keeps its whole
        # text, since the split commands leave heredoc bodies out.
        kept = [c for c in resolved
                if not (_is_api(_strip_reserved(c.words)) and _api_read(_strip_reserved(c.words)))]
        rest = command if "<<" in command else " ".join(
            source for c in kept for _, source in c.words)
        if not _api_words(rest):
            return _input_check(resolved, grouped) or NoPost()
    whole = _whole_command(command)
    if whole is not None:
        return _read_whole(whole, cwd)
    return _read_line(resolved, grouped)


def _read_whole(whole: _Command, cwd: str | None) -> Result:
    if whole.discord:
        return _read_discord(whole.words, cwd)
    if _is_api(whole.words):
        if _api_read(whole.words):
            return NoPost()
        return _read_api(whole.words, cwd, whole.app)
    kind = _gh_text(whole.words)
    if kind == "none":
        return NoPost()
    if kind == "unreadable":
        return _not_canonical(f"`{' '.join(source for _, source in whole.words)}`")
    return _read_gh(whole.words, cwd, whole.app)


def _discord_post(words: list[Word]) -> bool:
    """Whether a word that is discord_bot or ends in discord_bot.py comes
    before a word post or edit. Such a command counts as naming gh (gh-post
    spec: *A simple command holding a discord-bot post word counts as naming
    gh*)."""
    texts = [text for text, _ in words]
    return any((text == DISCORD_MODULE or text.endswith(DISCORD_SCRIPT))
               and {"post", "edit"} & set(texts[k + 1:]) for k, text in enumerate(texts))


def _read_line(resolved: list[_Command], grouped: bool) -> Result:
    """What a line other than one canonical command posts: no post when
    each simple command provably sends none; otherwise unreadable."""
    for command in resolved:
        words = _strip_reserved(command.words)
        if not words or all(source in CLOSERS for _, source in words):
            continue
        source = " ".join(src for _, src in words)
        if command.discord:
            if command.fed:
                return _fed_blocker(DISCORD_SCRIPT)
            if words[0][0] not in DISCORD_QUIET:
                return _not_canonical(f"`{DISCORD_SCRIPT} {source}`")
            continue
        names = _names(words)
        if grouped and names[0] not in DATA_COMMANDS:
            return _blocked(GROUPED)
        if command.fed and names[0] not in DATA_COMMANDS and not (
                _is_gh(words) and _quiet_gh(words)):
            return _fed_blocker(names[0] or words[0][1])
        if command.unassigned and ("gh" in names or {"post", "edit"} & set(names)):
            return _unassigned(command.unassigned)
        if names[0] in PYTHONS and DISCORD_SCRIPT in names or _discord_post(words):
            return _not_canonical(f"`{source}`")
        if "gh" not in names:
            if (_names_gh(source) or _discord_words(source)) and names[0] not in DATA_COMMANDS:
                return _not_canonical(f"`{words[0][1]}`")
            continue
        if not _is_gh(words):
            return _not_canonical(f"`{source}`")
        if _is_api(words):
            if not _api_read(words):
                return _not_canonical(f"`{source}`")
            continue
        if _gh_text(words) != "none":
            return _not_canonical(f"`{source}`")
    return NoPost()


# -- a tool call -----------------------------------------------------------

BODY_KEYS = {"body", "comment"}
GITHUB_MCP = re.compile(r"^mcp__(?:github|plugin_.+_github|claude_ai_GitHub)__")
LINEAR_MCP = re.compile(r"^mcp__(?:linear|plugin_.+_linear|claude_ai_Linear)__")
LINEAR_WRITES = ("save_", "create_", "update_", "submit_")
# The keys whose strings hold no text Linear shows (gh-post spec: *The
# no-text list names keys that hold no text*).
NO_TEXT_KEYS = frozenset((
    "id issue project initiative cycle team teamId parent parentId lead leadTeam addTeams "
    "removeTeams setTeams addInitiatives removeInitiatives setInitiatives labels pipeline "
    "stage releases rangeFromRelease rangeToRelease urlOrId commentId draftId user "
    "externalUserId githubTeamId removedIssueLinks commitSha state health type decision "
    "statusAction groupType startDateResolution targetDateResolution startDate targetDate "
    "startedAt completedAt createdAt color").split())


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


def _text_keys(value: object, key: str = "") -> set[str]:
    """The keys not on the no-text list that a string in value sits under: its
    nearest object key, so a string in a list takes the list's key."""
    if isinstance(value, str):
        return set() if key in NO_TEXT_KEYS else {key}
    found: set[str] = set()
    if isinstance(value, dict):
        for name, item in cast(dict[object, object], value).items():
            found |= _text_keys(item, str(name))
    elif isinstance(value, list):
        for item in cast(list[object], value):
            found |= _text_keys(item, key)
    return found


def _linear(tool: str, tool_input: object) -> Result:
    """A Linear MCP save_comment's body or save_issue's description (gh-post
    spec: *The reader reads a Linear MCP comment or issue description*). A
    save_issue holding `patch`, or `template` with no description text,
    takes its text from what Linear already holds, so it is unreadable."""
    if not isinstance(tool_input, dict):
        return NoPost()
    given = cast(dict[str, object], tool_input)
    key = {"save_comment": "body", "save_issue": "description"}.get(tool)
    if key is None:
        # Another write tool sends no post only when it holds no text (gh-post
        # spec: *Another Linear write tool sends no post only when it holds no
        # text*); a tool whose name starts with none of LINEAR_WRITES, such
        # as get_issue, sends none.
        keys: set[str] = _text_keys(given) if tool.startswith(LINEAR_WRITES) else set()
        if keys:
            return _blocked(f"Linear {tool}: {', '.join(sorted(keys))} may hold text the hook "
                            "cannot check.")
        return NoPost()
    text = given.get(key)
    if tool == "save_issue" and ("patch" in given or (
            "template" in given and not (isinstance(text, str) and text))):
        return _blocked(f"Linear {tool}: a patch or a template builds the description from "
                        "what Linear holds, so what it posts cannot be checked. Send the whole "
                        "description instead.")
    if text is None:
        return NoPost()
    if not isinstance(text, str):
        return _blocked(f"Linear {tool}: its {key} is not text.")
    return [Post(key, text, "linear")]


def read_posts(payload: dict[str, Any], host: str) -> Result:
    """What the hook payload's tool call posts. host is "claude" or
    "cursor", as prose's hook names it, since the two hosts send different
    payload shapes. A call that posts several bodies, such as a review with
    comments, gives one Post per body."""
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) else None
    if host == "cursor":
        if "command" in payload and "tool_name" not in payload:
            command = payload.get("command")
            return read_command(command if isinstance(command, str) else "", cwd)
        server = payload.get("mcp_server_name")
        server = server.lower() if isinstance(server, str) else ""
        tool_input: object = payload.get("tool_input")
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except ValueError:
                tool_input = {}
        if "github" in server:
            return _mcp(tool_input)
        if "linear" in server:
            name = payload.get("tool_name")
            return _linear(name if isinstance(name, str) else "", tool_input)
        return NoPost()
    tool = payload.get("tool_name")
    tool = tool if isinstance(tool, str) else ""
    tool_input = payload.get("tool_input") or {}
    if GITHUB_MCP.match(tool):
        return _mcp(tool_input)
    if LINEAR_MCP.match(tool):
        return _linear(LINEAR_MCP.sub("", tool), tool_input)
    if tool == "Bash" and isinstance(tool_input, dict):
        command = cast(dict[str, object], tool_input).get("command")
        return read_command(command if isinstance(command, str) else "", cwd)
    return NoPost()
