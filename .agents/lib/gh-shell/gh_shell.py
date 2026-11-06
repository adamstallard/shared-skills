"""How the agent-side hooks read a shell command, and gh's flags.

Shared by prose's posting hook (.agents/skills/prose/scripts/prose.py) and
spec-check's hand-back hook (.agents/skills/spec-check/scripts/handback.py),
so the two agree on what a command runs. Each hook imports it from this
directory of the shared-skills clone, found from the hook's own real path,
as the skills' commit scripts find ../lib/commit-trailer. Without it, prose's
posting hook blocks any command that may run gh, and spec-check's hand-back
hook judges nothing.

- _commands(command) splits a command into simple commands, or gives None
  for anything it cannot read exactly;
- _words(command) gives a plain command's words, or None;
- the tables give each gh verb's flags, as `gh <noun> <verb> --help` lists
  them.

Why it reads the shell the way it does: prose's DECISIONS.md, "The posting
hook reads an allow-list". Standard library only.
"""

import re

# Matches every tool of the GitHub MCP server, including a copy of the server
# bundled in a plugin, whose tools are named mcp__plugin_<plugin>_github__<tool>.
GITHUB_MCP = re.compile(r"^mcp__(?:plugin_.+_)?github__")
# The gh verbs that post text, each with the flags that carry it: close and
# reopen post their comment with --comment, the rest with --body.
BODY_FLAGS = ("--body", "-b", "--body-file", "-F")
COMMENT_FLAGS = ("--comment", "-c")
_BODY_VERBS = {verb: BODY_FLAGS for verb in ("create", "new", "edit", "comment", "review")}
GH_VERBS = {"pr": {**_BODY_VERBS, "revert": BODY_FLAGS, "close": COMMENT_FLAGS, "reopen": COMMENT_FLAGS},
            "issue": {**_BODY_VERBS, "close": COMMENT_FLAGS, "reopen": COMMENT_FLAGS}}
# Each verb's short flags that take a value and do not carry the text, from
# `gh <noun> <verb> --help`. gh's flag parser, pflag, reads a group of short
# flags, such as `-dc x` (`-d` then `-c`), one letter at a time. The first
# letter that takes a value swallows the
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
# title. prose's posting hook blocks a command holding a long flag in
# neither set, because it cannot tell whether the flag takes the next
# argument.
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
# read: commits, a saved draft (`--recover`), a template, an editor or the
# browser. Each entry is (long names, short letters), and prose's posting hook
# blocks a command holding any of them.
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
# a post verb. A closed list: a verb missing from it, such as merge (whose
# --body the hook does not read) or one gh adds later, is blocked as a post
# the hook cannot read. cobra takes the first word after the noun as the
# subcommand exactly as written, with no prefix matching, so the list holds
# each alias as gh spells it (ls, co).
NO_TEXT_VERBS = {
    "pr": {"list", "ls", "status", "checkout", "co", "checks", "diff", "view", "ready",
           "lock", "unlock", "update-branch"},
    "issue": {"list", "ls", "status", "delete", "develop", "lock", "unlock", "pin",
              "unpin", "transfer", "view"},
}


PLAIN = re.compile(r"[A-Za-z0-9_./:=@%+,#^-]")


def _words(command):
    """[(text, quoted)] for a command made only of plain words, or None.

    None when the shell would do more than join quoted parts. For bash that
    is an operator, a newline, an expansion, a glob, a backslash, or a
    double-quoted string holding $, a backtick or a backslash. For zsh it is
    also a word starting with an unquoted `=`, even after empty quotes
    (`''=x`), which zsh replaces with a command's path. Such a command is not
    one of the forms prose's posting hook accepts (prose's DECISIONS.md, "The
    posting hook reads an allow-list"), so the hook does not try to read it.
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


# Commands that treat their arguments and stdin as data, never as shell code,
# so a gh post named in them only mentions one. prose's posting hook blocks a
# gh named in any other command. The list is closed on purpose: any other
# command may run the text it is given (sh -c, eval, trap, env -S, ssh,
# xargs), and a list of those is never complete.
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
# Reserved words that end a compound command and run nothing. A command made
# only of these is no command, so `fi` beside a pipe runs nothing. A closer
# followed by another word is still a command: in `done sh`, sh runs. Not
# esac, whose case patterns are not read.
CLOSERS = {"fi", "done", "}"}
EXPANSION = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9#?$!@*-]|\{[A-Za-z_][A-Za-z0-9_]*\})")
REDIRECT = re.compile(r"&>>?|<<<|<<-|<<|<>|<&|<|>>|>&|>\||>")
METACHARS = " \t\n;&|()<>"


def _word(command, i):
    """(text, end, source) for the shell word starting at command[i], or None.

    text is the word after quote removal, with simple expansions ($NAME,
    ${NAME}, $1, $?) left out, since only literal text can name gh. source
    is the word as written, minus each backslash-newline outside single
    quotes, which both shells remove before reading the word: `i`, a
    backslash, a newline, then `f` is the word `if`, and a backslash and a
    newline alone are no word. None when the word holds anything that could
    run a command or that bash and zsh read differently: a command
    substitution, $'…', $"…", ${…} beyond a name, an unterminated quote, a
    leading `#`, or a `[` left open after the first character. bash reads
    such a `[` as an array subscript and reads on through it (`a[1<<EOF]=5`
    is not a heredoc to bash), where this reader would stop.
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
    redirections are left out of the words, and do not make a command fed.

    grouped is True when input may reach more than one simple command, so a
    caller cannot tell which command reads it; prose's posting hook then
    blocks any command not in DATA_COMMANDS. That is the case for a pipe into
    a subshell, a `$(`, or a reserved word that opens a compound command; an
    input redirection on a `(`…`)`, or on a command holding `}`, `done` or
    `fi`; and a `(` in a fed command.
    Heredoc bodies and comments are skipped, since the shell runs neither.
    None for anything whose reading differs between shells or could hide a
    command: what _word refuses, process substitution, a heredoc inside
    parentheses (bash 3.2 reads those its own way), a heredoc whose body
    would start inside an open `(`, an unquoted heredoc body that could run or join
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
