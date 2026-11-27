"""GitHub lookups through `gh`, each returning a value or None when it
cannot tell.

None never means "no": each caller applies its requirement's rule for an
unknown, such as *An unreadable visibility counts against sharing* or *A
permission that cannot be read is no write access* (inquisitor spec). No
function here passes a login or repository to GitHub before checking its
syntax with formats.is_login or formats.is_repository; one off the syntax
gives None with no call made.

Owned by P2. tasks.md's task 0.4 measured that a caller without push access
gets 403 `Must have push access to view collaborator permission.`, which
write_access gives as None, and that an App's `<slug>[bot]` always reads
`none`. Standard library only.
"""

import json
import os
import re
import subprocess
import urllib.parse
from dataclasses import dataclass
from typing import Any, Literal, cast

from formats import is_answer_link, is_repository, is_login

Visibility = Literal["private", "internal", "public"]


@dataclass(frozen=True)
class Comment:
    """A GitHub comment's or review's own text and author. login ends
    `[bot]` for an App's comment (tasks.md task 0.11); author_type is GitHub's
    `User` or `Bot`."""

    url: str
    text: str
    login: str
    author_type: str
    node_id: str


def run_gh(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run `gh` with args; its exit code, stdout and stderr. A gh that
    cannot start gives exit 127. Tests replace this function."""
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)
    return done.returncode, done.stdout, done.stderr


def _json(args: list[str], env: dict[str, str] | None = None) -> Any:
    code, out, _ = run_gh(args, env)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _get(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = cast(dict[str, Any], obj).get(key)
    return obj


def _split_repository(repository: str) -> tuple[str, str] | None:
    if not is_repository(repository):
        return None
    owner, name = repository.split("/")
    return owner, name


def _login_of(author: Any) -> str | None:
    """A GraphQL author's login, `[bot]` added for a Bot, whose GraphQL login
    lacks it (tasks.md task 0.11)."""
    login = _get(author, "login")
    if not isinstance(login, str):
        return None
    return login + "[bot]" if _get(author, "__typename") == "Bot" else login


def gh_login() -> str | None:
    """The login `gh api user` gives, read with the person's own stored gh
    credentials (GH_TOKEN and GITHUB_TOKEN left out, so an App's token in
    the environment does not answer), or None when gh cannot tell."""
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    login = _get(_json(["api", "user"], env), "login")
    return login if isinstance(login, str) and is_login(login) else None


def session_login(configured: str | None) -> str | None:
    """The configured login when gh is logged in as it, else None
    (inquisitor spec: *A configured login counts only when gh is logged in
    as it*). GitHub logins ignore case, so the comparison does too."""
    if configured is None or not is_login(configured):
        return None
    actual = gh_login()
    return configured if actual is not None and actual.lower() == configured.lower() else None


def write_access(repository: str, login: str) -> bool | None:
    """Whether login can push to repository, from
    `gh api repos/<owner>/<repo>/collaborators/<login>/permission`'s
    `user.permissions.push`; None when it cannot tell, as when the account
    gh is logged in as lacks push access (403) or the login does not exist (404). A login off
    GitHub's syntax, an App's `<slug>[bot]` included, gives None with no
    call made."""
    if _split_repository(repository) is None or not is_login(login):
        return None
    push = _get(_json(["api", f"repos/{repository}/collaborators/{login}/permission"]),
                "user", "permissions", "push")
    return push if isinstance(push, bool) else None


def visibility(repository: str) -> Visibility | None:
    """The repository's visibility from `gh repo view --json visibility`,
    or None when unreadable."""
    if _split_repository(repository) is None:
        return None
    value = _get(_json(["repo", "view", repository, "--json", "visibility"]), "visibility")
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if lowered == "private":
        return "private"
    if lowered == "internal":
        return "internal"
    if lowered == "public":
        return "public"
    return None


_RANK: dict[Visibility, int] = {"private": 0, "internal": 1, "public": 2}


def more_visible(a: Visibility | None, b: Visibility | None) -> bool:
    """Whether a place of visibility a is more visible than one of
    visibility b. An unknown a counts as public and an unknown b as private
    (inquisitor spec: *An unreadable visibility counts against sharing*)."""
    return _RANK[a or "public"] > _RANK[b or "private"]


_COMMENT_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/(issues|pull)/([0-9]+)"
                          r"#(issuecomment-|pullrequestreview-|discussion_r)([0-9]+)")
_HTML_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/(?:issues|pull)/([0-9]+)#")


def comment(url: str) -> Comment | None:
    """The comment or review a github.com answer_link names, read with the
    gh login the script runs under, or None when GitHub does not return it,
    or returns one on another repository or issue than the URL names."""
    m = _COMMENT_URL.fullmatch(url)
    if not m or not is_answer_link(url):
        return None
    repository, _, number, kind, ident = m.groups()
    if kind == "issuecomment-":
        path = f"repos/{repository}/issues/comments/{ident}"
    elif kind == "pullrequestreview-":
        path = f"repos/{repository}/pulls/{number}/reviews/{ident}"
    else:
        path = f"repos/{repository}/pulls/comments/{ident}"
    data = _json(["api", path])
    login, kind_of, node_id = _get(data, "user", "login"), _get(data, "user", "type"), _get(data, "node_id")
    html = _HTML_URL.match(str(_get(data, "html_url")))
    if not (isinstance(login, str) and isinstance(kind_of, str) and isinstance(node_id, str) and html):
        return None
    if html.group(1).lower() != repository.lower() or html.group(2) != number:
        return None
    body = _get(data, "body")
    return Comment(url=url, text=body if isinstance(body, str) else "", login=login,
                   author_type=kind_of, node_id=node_id)


def last_commit_author(repository: str, path: str) -> str | None:
    """The `author.login` of the newest commit to path (tasks.md task 0.5), or None
    for a commit naming no GitHub account, or when it cannot be read."""
    if _split_repository(repository) is None:
        return None
    query = urllib.parse.quote(path, safe="/")
    commits = _json(["api", f"repos/{repository}/commits?path={query}&per_page=1"])
    if not isinstance(commits, list) or not commits:
        return None
    login = _get(cast(list[Any], commits)[0], "author", "login")
    return login if isinstance(login, str) else None


_PR_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/pull/([0-9]+)(?:[/#?].*)?")
_BLOB_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/blob/([^/#?]+)/([^#?]+)"
                       r"(?:\?plain=1)?(?:#L([0-9]+)(?:-L([0-9]+))?)?")

_APPROVER_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(states: APPROVED, last: 1) { nodes { author { __typename login } } }
    }
  }
}"""

_BLAME_QUERY = """
query($owner: String!, $name: String!, $ref: String!, $path: String!) {
  repository(owner: $owner, name: $name) {
    object(expression: $ref) {
      ... on Commit {
        blame(path: $path) {
          ranges {
            startingLine
            endingLine
            commit {
              committedDate
              associatedPullRequests(first: 5) {
                nodes {
                  merged
                  reviews(states: APPROVED, last: 1) { nodes { author { __typename login } } }
                }
              }
            }
          }
        }
      }
    }
  }
}"""


def _graphql(query: str, fields: dict[str, str]) -> Any:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in fields.items():
        args += ["-F" if key == "number" else "-f", f"{key}={value}"]
    return _json(args)


def _approver(reviews: Any) -> str | None:
    nodes = _get(reviews, "nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    return _login_of(_get(cast(list[Any], nodes)[-1], "author"))


def decision_approver(repository: str, decision: str) -> str | None:
    """The approver of the pull request that added a related earlier
    decision, or None when it cannot be found (tasks.md task 0.8).

    decision is the related-decision line's URL. A pull request's URL names
    that pull request. A file's `blob` URL, optionally with a `#L<n>` or
    `#L<n>-L<m>` anchor, names the newest commit blame gives for those
    lines, or for the whole file, and the merged pull request that
    commit belongs to. The approver is the author of that pull request's
    latest approving review; a Bot's login gets `[bot]`. Any other URL,
    such as an issue's, which no pull request added, gives None.
    The repository argument goes unused, since the URL names its own."""
    del repository
    m = _PR_URL.fullmatch(decision)
    if m:
        target = _split_repository(m.group(1))
        if target is None:
            return None
        data = _graphql(_APPROVER_QUERY, {"owner": target[0], "name": target[1], "number": m.group(2)})
        return _approver(_get(data, "data", "repository", "pullRequest", "reviews"))
    m = _BLOB_URL.fullmatch(decision)
    if not m:
        return None
    target = _split_repository(m.group(1))
    if target is None:
        return None
    path = urllib.parse.unquote(m.group(3))
    data = _graphql(_BLAME_QUERY, {"owner": target[0], "name": target[1], "ref": m.group(2),
                                   "path": path})
    ranges = _get(data, "data", "repository", "object", "blame", "ranges")
    if not isinstance(ranges, list):
        return None
    first = int(m.group(4)) if m.group(4) else None
    last = int(m.group(5)) if m.group(5) else first
    newest: Any = None
    for r in cast(list[Any], ranges):
        start, end = _get(r, "startingLine"), _get(r, "endingLine")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if first is not None and last is not None and (end < first or start > last):
            continue
        date = _get(r, "commit", "committedDate")
        if isinstance(date, str) and (newest is None or date > _get(newest, "committedDate")):
            newest = _get(r, "commit")
    pulls = _get(newest, "associatedPullRequests", "nodes")
    if not isinstance(pulls, list):
        return None
    for pull in cast(list[Any], pulls):
        if _get(pull, "merged") is True:
            return _approver(_get(pull, "reviews"))
    return None
