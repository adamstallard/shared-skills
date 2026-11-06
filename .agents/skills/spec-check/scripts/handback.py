#!/usr/bin/env python3
"""spec-check's hand-back hook, run before and after a tool call.

    handback.py --host <platform>      payload on stdin

Whether it runs before or after the call comes from the payload's
hook_event_name, or else from whether the payload holds the call's output.

A review round ends at a hand-back to a person, and its consistency read must
be recorded by then (DECISIONS.md, "One consistency read per round"). A
hand-back is:

- `gh pr create`, unless it is a draft or a dry run; with a reviewer, even as
  a draft;
- `gh pr ready`, unless it is `--undo`;
- `gh pr edit --add-reviewer`;
- the GitHub MCP server's `create_pull_request`, unless it is a draft, and its
  `update_pull_request` with `draft: false` or with reviewers.

The hook judges the pull request, never a directory: it asks GitHub for the
pull request's head, fetches it into a cache, and finds the changes unread
there with spec_check.unread_at, from the trailers on the pull request's own
commits.

- Before the call (pre), a hand-back that names its pull request by URL,
  by `-R`/`GH_REPO` with a number or branch, or by the MCP's owner, repo
  and number is judged, and blocked while a change is unread.
- After the call (post), one GitHub MCP call that hands back is judged, and
  so is a shell command on an allowlist:
  - the shared command reader parses all of it, refusing no part;
  - it holds exactly one gh call, and that call is a hand-back;
  - no word in it expands, and no variable is assigned but GH_REPO before
    the gh;
  - every other command in it is git, cd, echo, printf, true or sleep. When
    the hand-back names no pull request by number or URL (a create, or a
    ready or edit by branch), only git push, git add and git commit with
    plain options, cd, true and sleep. gh may print nothing there, and
    another command's output would then be the only pull request printed.
  The one pull request the call printed (its URL, gh's "Pull request
  owner/repo#N is" line, or the MCP result's html_url) is then the
  hand-back's. If a change is unread there, the pull request is made a draft
  again, the reviewers the call requested are removed, and the agent is told
  to read, sign and hand back again. A form off the allowlist is skipped,
  never misread. When it holds a hand-back, the agent gets a note, never a
  block, naming what broke the list and the plain form to use.

Anything else is not judged here: the GitHub workflow (ci/spec-check.yml) is
the check that holds, where a repository has one. In Claude Code, exit 2
with the reason on stderr blocks before the call and tells the agent after
it. Cursor gets a JSON permission before, and additional_context after.

Standard library only. Read DECISIONS.md next to SKILL.md before changing this.
"""

import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec_check as sc  # noqa: E402

# The shared command reader, found as the commit-trailer library is: from this
# file's real path in the clone.
READER = HERE.parent.parent.parent / "lib" / "gh-shell"
# A command that may hand a pull request back. Only these are read.
HANDBACK_WORDS = re.compile(r"\bgh\b[\s\S]*\bpr\b[\s\S]*\b(?:create|new|ready|edit)\b")
# A shell variable assignment before a command, such as GH_REPO=o/r.
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# What gh prints for a pull request it created, edited or marked ready: its
# URL alone on a line, or "Pull request owner/repo#N is ...", after gh's
# symbol (a check mark or `!`). Both start the line, as gh prints them, so an
# indented line of git's, such as a commit body in `git log`, is not read.
# The URL may be a local path too: in tests, a local repository plays
# GitHub, and its pull requests' URLs are paths.
PR_URL_LINE = re.compile(r"^((?:https?://|/)\S+?/pull/\d+)/?[ \t\r]*$", re.M)
PR_STATE_LINE = re.compile(r"^[^\w\n]{0,4}Pull request ([\w.-]+/[\w.-]+)#(\d+) is\b", re.M)
# gh's error when a pull request already exists for the branch: the URL after
# it names a pull request the call did not hand back.
EXISTING_PR = re.compile(r"already exists:?\s*\n\s*\S+/pull/\d+/?[ \t\r]*$", re.M)
# The colour codes gh puts around its symbols when made to colour its output.
COLOUR = re.compile(r"\x1b\[[0-9;]*m")
# A pull request's URL: the repository's URL, then /pull/<number>, and any
# page of it (/files).
PR_URL = re.compile(r"^(?P<repo>.+?)/pull/(?P<number>\d+)(?:/\S*)?$")
GITHUB_MCP = re.compile(r"^mcp__(?:plugin_.+_)?github__")
# The programs that may stand beside a hand-back that names its pull request
# by number or URL, for the command to be judged after the call. A program
# not listed leaves the command unjudged.
ALONGSIDE = {"git", "cd", "echo", "printf", "true", "sleep"}
# Beside a hand-back that names no pull request (a create, or a ready or edit
# by branch), gh may print nothing and leave another command's output as the
# only pull request printed. So only commands that never print one may stand
# there: (program, its first argument), None meaning any.
UNNAMED_ALONGSIDE = {("git", "push"), ("git", "add"), ("git", "commit"), ("cd", None),
                     ("true", None), ("sleep", None)}
# The options those git commands may take there: (switches, options that take
# the next word, letters a short cluster may hold, letters that may end one
# and take a value). Any other option may print a diff (`add -p`,
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
# Shells whose -c word is a command, for spotting a hand-back to note.
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
# Text naming a pull request as the hook reads one (a URL, or gh's state
# line). An echo or printf beside the hand-back that prints it would put it in
# the output the hook reads for the hand-back's own pull request.
NAMES_PR = re.compile(r"/pull/\d|Pull request [\w.-]+/[\w.-]+#\d")
SKILL_STEPS = ("Do the consistency read (spec-check's SKILL.md, section 2), commit with "
               "`spec_check.py sign --read subagent`, push, and hand back again. "
               "A draft pull request is not a hand-back.")


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


def load_reader():
    """The shared command reader as a module, or None when it is missing."""
    sys.path.insert(0, str(READER))
    try:
        import gh_shell
    except ImportError:
        return None
    return gh_shell

# -- reading gh's flags ----------------------------------------------------

def gh_flags(reader, verb, args):
    """({flag: [values]}, [positional]) for `gh pr <verb>` args after the verb.

    Long flags are keyed `--name` and short ones `-x`. Which flags take a value
    comes from the shared tables of gh's help (SHORT_VALUES, LONG_FLAGS and the
    body flags), so the two hooks read gh's flags alike. A flag none of
    these lists as taking a value is read as a switch; unlike prose's posting
    hook, this one does not refuse an unknown long flag. pflag's forms are
    read: `--name value`,
    `--name=value`, `-x value`, `-xvalue` and a group such as `-dr x`, where
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
    """([Handback], sole, reason) for a shell command: each gh command in it
    that hands back; that hand-back alone when the command can be judged after
    it runs, else None; and, when it cannot be, why, if a hand-back is in it.

    sole is an allowlist, not a guess at what may hide a gh: it is set only
    when the reader reads the whole command; the command runs exactly one gh,
    a hand-back; every other command in it is one of ALONGSIDE, or of
    UNNAMED_ALONGSIDE when the hand-back names no pull request by number or
    URL; no word in it expands; and no variable is assigned, but
    GH_REPO=<plain> before the gh.
    Then whatever pull request the command printed is that hand-back's. Any
    other form is skipped, never misread, since a misread takes back the
    wrong pull request. reason names what broke the allowlist first, for the
    note the agent is given; it is None when no hand-back is seen anywhere in
    the command, even inside another program's words. reason is a pair:
    that text, and whether the narrower list was the one broken. With no
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
    """[(word, word)] for a command the shell reader refuses only for what
    expands to itself here, such as a `~/`, a backslash in double quotes or a
    letter outside ASCII; None when it holds an expansion: a variable, a
    command, a brace or a glob."""
    if expands(source):
        return None
    try:
        return [(w, w) for w in shlex.split(source)]
    except ValueError:
        return None


def expands(source):
    """Whether the shell would read source otherwise than shlex: `$` or a
    backtick outside single quotes, even after a backslash in double quotes;
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
    """The directory the hook was called in, where gh runs `gh pr view`."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        roots = payload.get("workspace_roots")
        cwd = roots[0] if isinstance(roots, list) and roots and isinstance(roots[0], str) \
            else os.getcwd()
    return cwd if os.path.isdir(cwd) else os.path.expanduser("~")


# -- judging a pull request ---------------------------------------------------

def cache_dir():
    """Where fetched pull requests are kept: one bare repository per
    repository URL."""
    root = os.environ.get("SPEC_CHECK_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "spec-check")
    return pathlib.Path(root) / "pulls"


def store_for(remote):
    """A bare repository fetching from remote, made the first time. It is a
    partial clone without file contents, which the judgement never reads."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", sc.remote_slug(remote) or "repo")
    path = cache_dir() / f"{slug}-{hashlib.sha256(remote.encode()).hexdigest()[:12]}.git"
    if path.is_dir():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=".new-", dir=path.parent))
    for args in (("init", "-q", "--bare"), ("config", "core.repositoryformatversion", "1"),
                 ("config", "extensions.partialClone", "origin"),
                 ("config", "remote.origin.url", remote),
                 ("config", "remote.origin.promisor", "true"),
                 ("config", "remote.origin.partialclonefilter", "blob:none")):
        sc.git(str(tmp), *args)
    try:
        tmp.rename(path)
    except OSError:  # another hook made it first
        shutil.rmtree(tmp, ignore_errors=True)
    return path


def view(selector, repo, cwd):
    """gh's view of a pull request, or None when gh cannot show it."""
    args = ["pr", "view", selector, "--json", "number,url,headRefOid,baseRefName,isDraft"]
    if repo:
        args += ["-R", repo]
    try:
        pr = json.loads(sc.gh(cwd, *args))
    except (sc.StackError, ValueError):
        return None
    if not isinstance(pr, dict) or not all(isinstance(pr.get(k), str)
                                           for k in ("url", "headRefOid", "baseRefName")):
        return None
    return pr if PR_URL.match(pr["url"]) else None


def unread(pr):
    """The changes unread at a pull request's head, from its own commits; None
    when its commits cannot be fetched."""
    m = PR_URL.match(pr["url"])
    number = m.group("number")
    store = str(store_for(m.group("repo")))
    head_ref, base_ref = f"refs/spec-check/pull/{number}", f"refs/spec-check/base/{number}"
    def fetch(*refspecs):
        # gh's token fetches a private repository, as `gh repo clone` would.
        return sc.git(store, "-c", "credential.helper=",
                      "-c", f"credential.helper=!{shlex.quote(sc.GH)} auth git-credential",
                      "fetch", "-q", "--no-tags", "--filter=blob:none", "origin", *refspecs,
                      check=False, env=dict(os.environ, GIT_TERMINAL_PROMPT="0")).returncode == 0

    if not fetch(f"+refs/heads/{pr['baseRefName']}:{base_ref}"):
        return None
    # The head commit itself first: refs/pull/<n>/head can lag a new pull
    # request.
    if not fetch(f"+{pr['headRefOid']}:{head_ref}") \
            and not fetch(f"+refs/pull/{number}/head:{head_ref}"):
        return None
    head = pr["headRefOid"]
    if sc.git(store, "cat-file", "-e", f"{head}^{{commit}}", check=False).returncode != 0:
        # The viewed head could not be fetched by its id, as when the head moved
        # since gh looked: judge the pull request's ref, what is there now.
        head = head_ref
    if not sc.git(store, "ls-tree", "-d", "--name-only", head, "--", "openspec/changes",
                  check=False).stdout.strip():
        return []
    return sc.unread_at(store, head, base_ref)


def judge(selector, repo, cwd):
    """(pull request, [unread change]) for a pull request, or None when it
    cannot be judged."""
    pr = view(selector, repo, cwd)
    if pr is None:
        return None
    changes = unread(pr)
    return None if changes is None else (pr, changes)


# -- before the call ----------------------------------------------------------

def before(reader, payload, host):
    """[message line] for each named hand-back that would leave a change
    unread."""
    lines = []
    handbacks, _, _ = handbacks_in(reader, payload, host)
    for handback in handbacks:
        if not handback.named():
            continue
        judged = judge(handback.selector, handback.repo, where(payload))
        if judged and judged[1]:
            pr, changes = judged
            lines.append(f"{handback.what}: {', '.join(changes)} in {pr['url']} "
                         f"(head {pr['headRefOid'][:12]}) changed after its last "
                         "consistency read.")
    return lines


# -- after the call -----------------------------------------------------------

# A command that exits nonzero gets PostToolUseFailure, with its output in
# error, in Claude Code.
AFTER_EVENTS = {"PostToolUse", "PostToolUseFailure", "postToolUse", "afterShellExecution",
                "afterMCPExecution"}
OUTPUT_KEYS = ("tool_response", "tool_output", "output", "result_json", "error")


def output_of(payload):
    """The text a call printed, as the host reports it: a string, or an
    object, or a string holding a JSON object (Cursor's tool_output), with
    stdout, stderr or output."""
    for key in OUTPUT_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                return value
            value = parsed if isinstance(parsed, dict) else value
            if isinstance(value, str):
                return value
        if isinstance(value, dict):
            return "\n".join(v for k, v in value.items()
                             if k in ("stdout", "stderr", "output") and isinstance(v, str))
    return ""


def mcp_pull_requests(payload):
    """The URL of the pull request an MCP call reports: the html_url (or url)
    of the result, which may be a JSON object or text holding one."""
    value = next((payload[k] for k in OUTPUT_KEYS if k in payload), None)
    found = []

    def visit(item):
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except ValueError:
                return
            visit(item)
        elif isinstance(item, dict):
            for key in ("html_url", "url"):
                if isinstance(item.get(key), str) and PR_URL.match(item[key]):
                    found.append(item[key])
                    return
            for key in ("content", "text", "result"):
                if key in item:
                    visit(item[key])
        elif isinstance(item, list):
            for x in item:
                visit(x)
    visit(value)
    return found


def printed_pull_requests(text):
    """[(selector, repo)] for each pull request gh reports in its output,
    except one it names because it already exists for the branch."""
    text = EXISTING_PR.sub("", COLOUR.sub("", text))
    found = [(url, None) for url in PR_URL_LINE.findall(text)]
    found += [(number, repo) for repo, number in PR_STATE_LINE.findall(text)]
    return list(dict.fromkeys(found))


def undo(pr, handback, cwd):
    """Take a hand-back back: a draft again, and the reviewers the call
    requested removed. [what was done or failed]."""
    done, url = [], pr["url"]
    if not pr.get("isDraft") and handback.kind in ("create", "ready"):
        try:
            sc.gh(cwd, "pr", "ready", url, "--undo")
            done.append("it is a draft again")
        except sc.StackError as e:
            done.append(f"making it a draft failed ({e}): run `gh pr ready {url} --undo`")
    if handback.reviewers:
        who = ",".join(handback.reviewers)
        try:
            sc.gh(cwd, "pr", "edit", url, "--remove-reviewer", who)
            done.append(f"the review request to {', '.join(handback.reviewers)} is withdrawn")
        except sc.StackError as e:
            done.append(f"withdrawing the review request failed ({e}): run "
                        f"`gh pr edit {url} --remove-reviewer {who}`")
    return done


def note_for(reason, narrow=False):
    """The note an agent is given when the hook did not judge its hand-back;
    narrow when it names no pull request and the narrower list applies."""
    return (f"spec-check: did not check this hand-back, because {reason}. The hook "
            "checks a hand-back after it runs only when the command holds that one "
            "gh call and nothing beside it but git, cd, echo, printf, true or sleep, "
            "with no $, backticks, globs, braces or leading ~ in any word, and no "
            "variable assigned but GH_REPO before gh. "
            + ("A hand-back that names no pull request by number or URL (a create, "
               "or a ready or edit by branch) may have only git push, git add, git "
               "commit, cd, true or sleep beside it. " if narrow else "")
            + "To have it checked, run "
            "`gh pr ...` on its own, or with only those programs beside it. Where the "
            "repository has spec-check's GitHub workflow, it still checks the pull "
            "request.")


def after(reader, payload, host):
    """[message line] for the pull request a call handed back with a change
    unread, taken back; or a note for a hand-back the hook did not judge."""
    _, handback, reason = handbacks_in(reader, payload, host)
    if handback is None:
        if reason:
            raise Note(note_for(*reason))
        return []
    kind, _, _ = call_of(payload, host)
    if kind == "mcp":
        printed = [(url, None) for url in mcp_pull_requests(payload)]
        if not printed and handback.named():
            printed = [(handback.selector, handback.repo)]
    else:
        printed = printed_pull_requests(output_of(payload))
    # One gh call reports one pull request; more cannot be told apart, and
    # one other than the pull request the call named is not its. Each is
    # compared as GitHub names it, since the same number in another
    # repository is another pull request.
    numbers = {number_of(s) for s, _ in printed}
    named = number_of(handback.selector) if handback.selector else None
    if len(numbers) != 1 or (named and re.fullmatch(r"[0-9]+", named)
                             and numbers != {named}):
        return []
    cwd = where(payload)
    viewed = [view(s, r, cwd) for s, r in printed]
    if None in viewed or len({pr["url"] for pr in viewed}) != 1:
        return []
    pr = viewed[0]
    if handback.selector:
        if handback.repo or PR_URL.match(handback.selector):
            own = view(handback.selector, handback.repo, cwd)
            if own is None or own["url"] != pr["url"]:
                return []
    changes = unread(pr)
    if not changes:
        return []
    if pr.get("isDraft") and not handback.reviewers:
        return []  # a draft that requested nobody was not handed back
    done = undo(pr, handback, cwd)
    return [f"{pr['url']} was handed back while {', '.join(changes)} changed after its "
            f"last consistency read (head {pr['headRefOid'][:12]}); "
            + "; ".join(done or ["nothing could be undone"]) + "."]


class Note(Exception):
    """A hand-back the hook did not judge: told to the agent, never blocking."""


def event_of(payload):
    """"pre" or "post": when the hook runs, relative to the call."""
    name = payload.get("hook_event_name")
    if isinstance(name, str) and name:
        return "post" if name in AFTER_EVENTS else "pre"
    return "post" if any(k in payload for k in OUTPUT_KEYS) else "pre"


def hook(raw, host, reader=None):
    """(exit code, stdout, stderr) for one hook call."""
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    event = event_of(payload) if isinstance(payload, dict) else "pre"
    allow = (0, '{"permission":"allow"}\n' if host == "cursor" and event == "pre" else "", "")
    if not isinstance(payload, dict):
        return allow
    reader = reader or load_reader()
    try:
        lines = before(reader, payload, host) if event == "pre" else after(reader, payload, host)
    except sc.Fatal:
        return allow
    except Note as note:
        if host == "cursor":
            return 0, json.dumps({"additional_context": str(note)}) + "\n", ""
        name = payload.get("hook_event_name")
        return 0, json.dumps({"hookSpecificOutput": {
            "hookEventName": name if isinstance(name, str) and name else "PostToolUse",
            "additionalContext": str(note)}}) + "\n", ""
    if not lines:
        return allow
    if event == "pre":
        message = ("spec-check: blocked this hand-back for review.\n"
                   + "".join(f"  - {line}\n" for line in lines) + SKILL_STEPS + "\n")
    else:
        message = ("spec-check: took back a hand-back for review.\n"
                   + "".join(f"  - {line}\n" for line in lines) + SKILL_STEPS + "\n")
    if host == "cursor":
        flat = message.replace("\n", " ").strip()
        if event == "pre":
            return 0, json.dumps({"permission": "deny", "user_message": flat,
                                  "agent_message": flat}) + "\n", ""
        return 0, json.dumps({"additional_context": flat}) + "\n", ""
    return 2, "", message


def main(argv):
    host = "claude"
    for i, arg in enumerate(argv):
        if arg == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
        elif arg.startswith("--host="):
            host = arg.split("=", 1)[1]
    code, out, err = hook(sys.stdin.read(), host)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
