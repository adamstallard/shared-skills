"""What counts as handing a pull request back for review, read from a hook's
tool call.

Shared by spec-check's hand-back hook (.agents/skills/spec-check/scripts/
handback.py), which blocks a hand-back, or takes it back by making the pull
request a draft again and removing the reviewers the call requested, while
an OpenSpec change has had no consistency read
since its last edit; and prose's posting hook
(.agents/skills/prose/scripts/prose.py), which cold-reads a pull request
body only at a hand-back and, after one, prints a reminder of the
current-state pass: rewriting any doc, body or title the pull request
changes that still describes work as unfinished or to come.
Each hook imports it from this directory of the shared-skills clone. The
functions here take the gh_shell module, beside this file, as their `reader`
argument, to split shell commands; with no reader (None), a shell command
holds no hand-back.

A hand-back is:

- `gh pr create`, unless it is a draft or a dry run; with a reviewer, even as
  a draft;
- `gh pr ready`, unless it is `--undo`;
- `gh pr edit --add-reviewer`;
- the GitHub MCP server's `create_pull_request`, unless it is a draft, and its
  `update_pull_request` with `draft: false` or with reviewers.

Standard library only.
"""

import json
import os
import re
import shlex

# A cheap first test: only a command this matches is split and read for a
# hand-back.
HANDBACK_WORDS = re.compile(r"\bgh\b[\s\S]*\bpr\b[\s\S]*\b(?:create|new|ready|edit)\b")
# A shell variable assignment before a command, such as GH_REPO=o/r.
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# A pull request's URL: the repository's URL, then /pull/<number>, and any
# page of it (/files).
PR_URL = re.compile(r"^(?P<repo>.+?)/pull/(?P<number>\d+)(?:/\S*)?$")
GITHUB_MCP = re.compile(r"^mcp__(?:plugin_.+_)?github__")
# The programs that may stand beside a hand-back that names its pull request
# by number or URL, for a hook to read the command's output after the call
# and tell which pull request was handed back. A program not listed leaves
# the command unread.
ALONGSIDE = {"git", "cd", "echo", "printf", "true", "sleep"}
# Beside a hand-back that names no pull request (a create, or a ready or edit
# by branch), gh may print nothing and leave another command's output as the
# only pull request printed. So only commands that never print one may stand
# there: (program, its first argument), None meaning any.
UNNAMED_ALONGSIDE = {("git", "push"), ("git", "add"), ("git", "commit"), ("cd", None),
                     ("true", None), ("sleep", None)}
# The options those git commands may take there, as a tuple of four:
# switches; options that take the next word as their value; the letters a
# cluster of short switches such as -aq may hold; and the letters that may end
# such a cluster and take a value, as -am does. Any other option may print a diff (`add -p`,
# `commit -v`, `--dry-run`) or run a command (`push --exec`), so it is off.
GIT_OPTIONS = {
    "add": ({"-A", "--all", "-u", "--update", "--"}, set(), "Au", None),
    "commit": ({"-a", "--all", "-q", "--quiet", "-s", "--signoff", "--amend",
                "--no-edit", "--allow-empty", "-n", "--no-verify"},
               {"-m", "--message", "-F", "--file"}, "aqsn", "mF"),
    "push": ({"-u", "--set-upstream", "-q", "--quiet", "-f", "--force",
              "--force-with-lease", "--tags", "--follow-tags", "--no-verify", "--"},
             set(), "uqf", None),
}
# Shells whose -c word is a command. A hand-back found inside one is only
# named in the note the agent gets, never judged.
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
# Text naming a pull request in a command's output (a URL, or gh's state
# line), which is where a hook reads which pull request was handed back. An
# echo or printf beside the hand-back that prints such text would be misread
# as the hand-back's own pull request.
NAMES_PR = re.compile(r"/pull/\d|Pull request [\w.-]+/[\w.-]+#\d")


class Handback:
    """One hand-back a tool call makes.

    what: how it is named in messages. kind: create, ready or review.
    selector: the pull request named (number, URL or branch), or None. repo:
    `-R` or GH_REPO's owner/repo. reviewers: the reviewers it requests."""

    def __init__(self, what, kind, selector=None, repo=None, reviewers=()):
        self.what, self.kind, self.selector, self.repo = what, kind, selector, repo
        self.reviewers = list(reviewers)

    def named(self):
        """Whether the pull request can be found before the call, without
        knowing which directory gh runs in."""
        return self.selector is not None and (
            bool(PR_URL.match(self.selector)) or bool(self.repo))



# -- reading gh's flags ----------------------------------------------------

def gh_flags(reader, verb, args):
    """({flag: [values]}, [positional]) for `gh pr <verb>` args after the verb.

    Long flags are keyed `--name` and short ones `-x`. Which flags take a value
    comes from the shared tables of gh's help (SHORT_VALUES, LONG_FLAGS and the
    body flags, plus COMMON_LONG), so the two hooks read gh's flags alike. A
    flag none of these lists as taking a value is read as a switch: this
    function does not refuse an unknown long flag, as prose's posting hook
    does. pflag's forms are read: `--name value`, `--name=value`, `-x value`, `-xvalue` and a group such as `-dr x`, where
    the first letter that takes a value swallows the rest of the group."""
    long_values = reader.LONG_FLAGS["pr"].get(verb, (set(), set()))[0] | reader.COMMON_LONG[0] \
        | {"body", "body-file"}
    short_values = reader.SHORT_VALUES["pr"].get(verb, "R") + "bF"
    flags, positional, i = {}, [], 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional += args[i + 1:]
            break
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if eq:
                flags.setdefault("--" + name, []).append(value)
            elif name in long_values:
                flags.setdefault("--" + name, []).append(args[i + 1] if i + 1 < len(args) else "")
                i += 1
            else:
                flags.setdefault("--" + name, []).append("true")
        elif arg.startswith("-") and len(arg) > 1:
            for position in range(1, len(arg)):
                letter, rest = arg[position], arg[position + 1:]
                if letter == "=":
                    break
                if letter in short_values:
                    if rest:
                        value = rest[1:] if rest.startswith("=") else rest
                    else:
                        value = args[i + 1] if i + 1 < len(args) else ""
                        i += 1
                    flags.setdefault("-" + letter, []).append(value)
                    break
                flags.setdefault("-" + letter, []).append(
                    rest[1:] if rest.startswith("=") else "true")
                if rest.startswith("="):
                    break
        else:
            positional.append(arg)
        i += 1
    return flags, positional


def switch(flags, *names):
    """Whether a boolean flag is on: its last value, under any of its names."""
    values = [v for name in names for v in flags.get(name, [])]
    return bool(values) and values[-1].lower() not in ("false", "0", "f")


def value(flags, *names):
    """A flag's last value under any of its names, or None."""
    values = [v for name in names for v in flags.get(name, [])]
    return values[-1] if values else None


def classify(reader, words):
    """The Handback a `gh` command given as plain words makes, or None."""
    args = [text for text, _ in words[1:]]
    repo, args = strip_repo(args, None)
    if not args or args[0] != "pr":
        return None
    repo, rest = strip_repo(args[1:], repo)
    if not rest:
        return None
    args = ["pr", *rest]
    verb = args[1]
    flags, positional = gh_flags(reader, verb, args[2:])
    repo = value(flags, "--repo", "-R") or repo
    selector = positional[0] if positional else None
    if verb in ("create", "new"):
        reviewer = value(flags, "--reviewer", "-r")
        if switch(flags, "--dry-run") or (switch(flags, "--draft", "-d") and not reviewer):
            return None
        return Handback(f"gh pr {verb}", "create", None, repo,
                        names(flags, "--reviewer", "-r"))
    if verb == "ready":
        return None if switch(flags, "--undo") else Handback("gh pr ready", "ready", selector,
                                                             repo)
    if verb == "edit" and value(flags, "--add-reviewer"):
        return Handback("gh pr edit --add-reviewer", "review", selector, repo,
                        names(flags, "--add-reviewer"))
    return None


def names(flags, *keys):
    """Every comma-separated value a repeatable flag was given."""
    return [n.strip() for key in keys for v in flags.get(key, []) for n in v.split(",")
            if n.strip()]


def strip_repo(args, repo):
    """(repo, args) with any -R/--repo flags at the front of args taken off:
    gh reads them before `pr` and between `pr` and its verb."""
    while args and (args[0] in ("-R", "--repo") or args[0].startswith(("--repo=", "-R"))):
        if args[0] in ("-R", "--repo"):
            repo, args = (args[1] if len(args) > 1 else repo), args[2:]
        else:
            repo, args = args[0].split("=", 1)[1] if "=" in args[0] else args[0][2:], args[1:]
    return repo, args




# -- what a call hands back --------------------------------------------------

def handbacks_in_command(reader, command):
    """([Handback], sole, reason) for a shell command.

    - [Handback]: each gh command in it that hands back.
    - sole: that hand-back, when it is the only one and a hook can read the
      command's output after it runs to tell which pull request it handed
      back; else None.
    - reason: why sole is None, when a hand-back is in the command.

    sole is set by an allowlist, not by guessing what may hide a gh: only
    when the reader reads the whole command; the command runs exactly one gh,
    a hand-back; every other command in it is one of ALONGSIDE, or of
    UNNAMED_ALONGSIDE when the hand-back names no pull request by number or
    URL; no word in it expands; and no variable is assigned, except
    GH_REPO=<plain> before the gh.
    Then whatever pull request the command printed is that hand-back's. Any
    other form is skipped, never misread, since a misread takes back the
    wrong pull request. reason names what broke the allowlist first, for the
    note the agent is given; it is None when no hand-back is seen anywhere in
    the command, even inside another program's words. reason is a pair:
    that text, and whether UNNAMED_ALONGSIDE was the list broken. With no
    shared reader, nothing is found and no reason is given."""
    if not HANDBACK_WORDS.search(command) or reader is None:
        return [], None, None
    read = reader._commands(command)
    if read is None:
        try:
            quoted = shlex.split(command, posix=False)
        except ValueError:
            quoted = command.split()
        word = next((w for w in quoted if expands(w)), None)
        reason = (f"the word `{word}` expands" if word
                  else "the shell reader cannot read the command whole")
        return [], None, ((reason, False)
                          if handback_anywhere(reader, loose_words(command)) else None)
    found, gh_calls, reasons, hidden, beside = [], 0, [], False, []
    for words, _ in read[0]:
        while words and words[0][1] in reader.RESERVED:
            words = words[1:]
        hidden = hidden or handback_anywhere(reader, [text for text, _ in words])
        reasons += [f"the word `{src}` expands" for _, src in words if expands(src)][:1]
        repo = None
        while words and ASSIGNMENT.match(words[0][1]):
            name, _, assigned = words[0][0].partition("=")
            if name == "GH_REPO" and assigned:
                repo = assigned
            else:
                reasons.append(f"`{words[0][1]}` assigns a variable")
            words = words[1:]
        if not words:
            reasons.append("a variable is assigned with no command after it")
            continue
        source = " ".join(src for _, src in words)
        program = words[0][0]
        if program == "printf" and len(words) > 1 and words[1][0].startswith("-v"):
            reasons.append("`printf -v` assigns a variable, in which zsh runs commands")
        elif program in ("echo", "printf") and NAMES_PR.search(" ".join(t for t, _ in words[1:])):
            reasons.append(f"`{words[0][1]}` prints a pull request's URL or state, "
                           "which would be read as the hand-back's")
        if program != "gh":
            beside.append(words)
            if repo is not None:
                reasons.append(f"`GH_REPO={repo}` comes before `{words[0][1]}`, not gh")
            if words[0][0] not in ALONGSIDE:
                reasons.append(f"`{words[0][1]}` is not one of the programs listed")
            continue
        gh_calls += 1
        plain = reader._words(source) or plain_words(source)
        if plain is None:
            reasons.append(f"the gh call `{source}` cannot be read as plain words")
            continue
        handback = classify(reader, plain)
        if handback:
            handback.repo = handback.repo or repo
            found.append(handback)
    if gh_calls > 1:
        reasons.append(f"the command runs {gh_calls} gh calls")
    narrow = False
    if gh_calls == 1 and len(found) == 1 and not reasons and not names_its_pr(found[0]):
        for words in beside:
            if not on_unnamed_list([text for text, _ in words]):
                reasons.append(f"`{' '.join(src for _, src in words)}` stands beside a "
                               "hand-back that names no pull request")
                narrow = True
                break
    sole = found[0] if gh_calls == 1 and len(found) == 1 and not reasons else None
    reason = reasons[0] if sole is None and reasons and (found or hidden) else None
    return found, sole, (reason and (reason, narrow))


def on_unnamed_list(texts):
    """Whether a command may stand beside a hand-back that names no pull
    request: one of UNNAMED_ALONGSIDE, and for git only GIT_OPTIONS."""
    if (texts[0], None) in UNNAMED_ALONGSIDE:
        return True
    if texts[0] != "git" or len(texts) < 2 or (texts[0], texts[1]) not in UNNAMED_ALONGSIDE:
        return False
    switches, valued, letters, ending = GIT_OPTIONS[texts[1]]
    args, i = texts[2:], 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return "--" in switches
        if arg in valued:
            i += 2
            continue
        if any(arg.startswith(v + "=") for v in valued if v.startswith("--")):
            pass
        elif arg.startswith("--force-with-lease=") and "--force-with-lease" in switches:
            pass
        elif arg.startswith("--"):
            if arg not in switches:
                return False
        elif arg.startswith("-") and len(arg) > 1:
            body = arg[1:]
            cut = next((k for k, c in enumerate(body) if ending and c in ending), None)
            if any(c not in letters for c in body[:cut]):
                return False
            if cut is not None and cut == len(body) - 1:
                i += 1  # the value is the next word
        i += 1
    return True


def names_its_pr(handback):
    """Whether a hand-back names its pull request by number or URL."""
    selector = handback.selector or ""
    return bool(re.fullmatch(r"[0-9]+", selector) or PR_URL.match(selector))


def loose_words(command):
    """The words of a command the shell reader refuses, split as plainly as
    shlex can, or on blanks; only for spotting a hand-back to name in a
    note, never for judging one."""
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def handback_anywhere(reader, texts, depth=2):
    """Whether a `gh` word among texts starts a hand-back, or a word after a
    `-c` holds one (`bash -c "gh pr create"`): what a note names, never what
    is judged."""
    for i, text in enumerate(texts):
        if (text == "gh" or text.endswith("/gh")) \
                and classify(reader, [(t, t) for t in texts[i:]]):
            return True
        if depth and i and texts[i - 1] == "-c" and "gh" in text \
                and any(t.rsplit("/", 1)[-1] in SHELLS for t in texts[:i - 1]) \
                and handback_anywhere(reader, loose_words(text), depth - 1):
            return True
    return False


def plain_words(source):
    """[(word, word)] for a command the shell reader refuses only for text
    the shell leaves as written, such as a `~/`, a backslash in double quotes
    or a letter outside ASCII; None when it holds an expansion: a variable, a
    command, a brace or a glob."""
    if expands(source):
        return None
    try:
        return [(w, w) for w in shlex.split(source)]
    except ValueError:
        return None


def expands(source):
    """Whether the shell would read source otherwise than shlex: `$` or a
    backtick outside single quotes, even after a backslash in double quotes,
    where it is counted as expanding to stay on the safe side;
    outside any quotes, a brace, a glob, zsh's leading `=`, a carriage return
    (shlex splits on it, the shell keeps it in a word), or a `~` that begins a
    word or follows `=` or `:` (as bash expands `x=~root` and `x=a:~root`). A `~/` is let through:
    it only ever names a file, such as --body-file's, never a pull request,
    a repository or a reviewer, so its expansion cannot change a judgement."""
    quote, unquoted, i = None, [], 0
    while i < len(source):
        c = source[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\" and i + 1 < len(source):
            if quote == '"' and source[i + 1] in "$`":
                return True
            i += 1
            unquoted.append("x") if quote is None else None
        elif quote is None and c == "\r":
            return True
        elif quote is None and c == "~" and (not unquoted or unquoted[-1].isspace()
                                             or unquoted[-1] in "=:") \
                and source[i + 1:i + 2] != "/":
            return True
        elif quote == '"':
            if c in "$`":
                return True
            quote = None if c == '"' else quote
        elif c in "'\"":
            quote = c
        else:
            unquoted.append(c)
        i += 1
    return bool(re.search(r"[$`{}*?\[]|(?:^|\s)=", "".join(unquoted)))


def number_of(selector):
    """A pull request's number, as gh reads it, from a number (007 is 7) or a
    URL; any other selector as given."""
    m = PR_URL.match(selector)
    number = m.group("number") if m else selector
    return str(int(number)) if re.fullmatch(r"[0-9]+", number) else number


def handbacks_in_mcp(tool, tool_input):
    """[Handback] for a GitHub MCP tool call."""
    if not isinstance(tool_input, dict):
        return []
    repo = None
    if isinstance(tool_input.get("owner"), str) and isinstance(tool_input.get("repo"), str):
        repo = f"{tool_input['owner']}/{tool_input['repo']}"
    reviewers = tool_input.get("reviewers")
    reviewers = [r for r in reviewers if isinstance(r, str)] if isinstance(reviewers, list) \
        else []
    if tool == "create_pull_request":
        if tool_input.get("draft") is True and not reviewers:
            return []
        return [Handback(f"MCP {tool}", "create", None, repo, reviewers)]
    if tool == "update_pull_request":
        number = tool_input.get("pullNumber", tool_input.get("pull_number"))
        if tool_input.get("draft") is False or reviewers:
            return [Handback(f"MCP {tool}", "ready" if tool_input.get("draft") is False
                             else "review", str(number) if number is not None else None,
                             repo, reviewers)]
    return []


def call_of(payload, host):
    """(kind, tool, tool_input) of a hook payload: kind is "shell", "mcp" or
    None."""
    if host == "cursor" and "command" in payload and "tool_name" not in payload:
        return "shell", None, {"command": payload.get("command")}
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            tool_input = {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return None, None, None
    if host == "cursor" and isinstance(payload.get("mcp_server_name"), str):
        return ("mcp", tool, tool_input) if "github" in payload["mcp_server_name"].lower() \
            else (None, None, None)
    if GITHUB_MCP.match(tool):
        return "mcp", GITHUB_MCP.sub("", tool), tool_input
    if tool in ("Bash", "Shell"):
        return "shell", None, tool_input
    return None, None, None


def handbacks_in(reader, payload, host):
    """([Handback], sole, reason) for one hook payload, as
    handbacks_in_command gives them; for an MCP call, its one hand-back."""
    kind, tool, tool_input = call_of(payload, host)
    if kind == "mcp":
        found = handbacks_in_mcp(tool, tool_input)
        return found, (found[0] if len(found) == 1 else None), None
    if kind == "shell" and isinstance(tool_input.get("command"), str):
        return handbacks_in_command(reader, tool_input["command"])
    return [], None, None


def where(payload):
    """The directory the hook was called in. A hook that looks up a pull
    request runs `gh pr view` there."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        roots = payload.get("workspace_roots")
        cwd = roots[0] if isinstance(roots, list) and roots and isinstance(roots[0], str) \
            else os.getcwd()
    return cwd if os.path.isdir(cwd) else os.path.expanduser("~")
