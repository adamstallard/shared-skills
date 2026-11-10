#!/usr/bin/env python3
"""spec-check's hand-back hook, run before and after a tool call.

    handback.py --host <platform>      payload on stdin

Whether it runs before or after the call comes from the payload's
hook_event_name, or else from whether the payload holds the call's output.

A review round ends at a hand-back to a person, and its consistency read must
be recorded by then. The shared .agents/lib/gh-shell/handbacks.py decides
what is a hand-back and which pull request it names.

The hook judges the pull request, never a directory: it asks GitHub for the
pull request's head, fetches it into a cache, and finds the changes unread
there with spec_check.unread_at, from the trailers on the pull request's own
commits.

- Before the call (pre), a hand-back that names its pull request by URL,
  by `-R`/`GH_REPO` with a number or branch, or by the MCP's owner, repo
  and number is judged, and blocked while a change is unread.
- After the call (post), one GitHub MCP call that hands back is judged, and
  so is a shell command on an allowlist:
  - the shared command reader parses every word of the command;
  - it holds exactly one gh call, and that call is a hand-back;
  - no word in it expands, and no variable is assigned, except GH_REPO
    before the gh;
  - every other command in it is git, cd, echo, printf, true or sleep. When
    the hand-back names no pull request by number or URL (a create, or a
    ready or edit by branch), only git push, git add and git commit with
    plain options, cd, true and sleep: gh may print nothing there, so echo
    or printf could print the only pull request the hook would see.
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

Standard library only.
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
# What counts as a hand-back is read by handbacks.py, in the same directory as
# the reader; prose's posting hook imports it too. Without it, this hook
# judges nothing.
sys.path.insert(0, str(READER))
try:
    from handbacks import (  # noqa: E402
        PR_URL,
        call_of,
        handbacks_in,
        number_of,
        on_unnamed_list,
        plain_words,
        where,
    )
    HANDBACKS_MISSING = False
except ImportError:
    HANDBACKS_MISSING = True
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
SKILL_STEPS = ("Do the consistency read (spec-check's SKILL.md, section 2), commit with "
               "`spec_check.py sign --read subagent`, push, and hand back again. "
               "A draft pull request is not a hand-back.")



def load_reader():
    """The shared command reader as a module, or None when it is missing."""
    sys.path.insert(0, str(READER))
    try:
        import gh_shell
    except ImportError:
        return None
    return gh_shell

# -- judging a pull request ---------------------------------------------------

def cache_dir():
    """Where fetched pull requests are kept: one bare repository per
    repository URL."""
    root = os.environ.get("SPEC_CHECK_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "spec-check")
    return pathlib.Path(root) / "pulls"


def store_for(remote):
    """A bare repository fetching from remote, made the first time. It is a
    partial clone without file contents. The judgement reads one file's
    contents, the decision-records configuration, which git then fetches
    on demand."""
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
    """Why handing back a pull request would leave its head unread, judged
    from the pull request's own commits as fetched from GitHub: the changes
    unread there, or the symlinks under openspec/
    there, which spec-check does not support; "" when nothing is unread;
    None when its commits cannot be fetched."""
    m = PR_URL.match(pr["url"])
    number = m.group("number")
    store = str(store_for(m.group("repo")))
    head_ref, base_ref = f"refs/spec-check/pull/{number}", f"refs/spec-check/base/{number}"
    # gh's token fetches a private repository, as `gh repo clone` would, and
    # git never prompts. The same settings reach the fetch git makes on its
    # own for a file's contents the judgement reads.
    # Added after any settings the environment already gives git this way.
    try:
        n = max(int(os.environ.get("GIT_CONFIG_COUNT", "0")), 0)
    except ValueError:
        n = 0
    git_env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT=str(n + 2),
                   **{f"GIT_CONFIG_KEY_{n}": "credential.helper", f"GIT_CONFIG_VALUE_{n}": "",
                      f"GIT_CONFIG_KEY_{n + 1}": "credential.helper",
                      f"GIT_CONFIG_VALUE_{n + 1}": f"!{shlex.quote(sc.GH)} auth git-credential"})

    def fetch(*refspecs):
        return sc.git(store, "fetch", "-q", "--no-tags", "--filter=blob:none", "origin",
                      *refspecs, check=False, env=git_env).returncode == 0

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
    links = sc.openspec_links(store, head)
    if links:
        return sc.links_problem(links)
    if not sc.git(store, "ls-tree", "-d", "--name-only", head, "--", "openspec",
                  check=False).stdout.strip():
        return ""
    saved = dict(os.environ)
    os.environ.update(git_env)
    try:
        changes = sc.unread_at(store, head, base_ref)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return f"{', '.join(changes)} changed after its last consistency read" if changes else ""


def judge(selector, repo, cwd):
    """(pull request, why it is unread, or "") for a pull request, or None
    when it cannot be judged."""
    pr = view(selector, repo, cwd)
    if pr is None:
        return None
    why = unread(pr)
    return None if why is None else (pr, why)


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
            pr, why = judged
            lines.append(f"{handback.what}: in {pr['url']} (head {pr['headRefOid'][:12]}), "
                         f"{why}.")
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
    why = unread(pr)
    if not why:
        return []
    if pr.get("isDraft") and not handback.reviewers:
        return []  # a draft that requested nobody was not handed back
    done = undo(pr, handback, cwd)
    return [f"{pr['url']} (head {pr['headRefOid'][:12]}) was handed back, but {why}; "
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
    if HANDBACKS_MISSING:
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
