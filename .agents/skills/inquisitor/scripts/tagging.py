"""`tag`: whom a posted question tags (inquisitor spec: *A question in a post
tags one person who can decide, if there is one*; *A question no candidate
can decide turns to the session's login*; *A post goes out as a GitHub App
only through github-app's commands*; *A candidate or login that cannot be
checked is skipped*).

tasks.md's task 2.6. Standard library only.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlparse

import config
import github
from calls import read_records
from common import VERSION, Refused, print_json
from contracts import TagResult, VerdictRecord
from formats import is_login, is_repository
from qtext import UNTAGGED_LINE

_HASH = re.compile(r"[0-9a-f]{64}")
# A github-app identity's name, as its script takes it with --identity.
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class TagArgs:
    """hash: the vetted question's hash, whose verdict record gives its
    related earlier decision, what it concerns and its files. identity: the
    `--identity` of the github-app command the post goes through, which
    makes the post an App's; None for any other post. posting_as exists
    only for run to refuse, since inquisitor.py still passes it: only an
    identity makes a post an App's."""

    hash: str
    posting_as: str | None = None
    identity: str | None = None


def person_in_session() -> bool:
    """Whether a person is in the session (inquisitor spec, Purpose):
    CLAUDE_CODE_SESSION_ATTENDED is `1`."""
    return os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "1"


def reviewers(repository: str) -> list[str] | None:
    """The lines of `.inquisitor/reviewers` on the repository's default
    branch, or None when there is no such file or it cannot be read."""
    if not is_repository(repository):
        return None
    try:
        done = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw",
             f"repos/{repository}/contents/.inquisitor/reviewers"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def _decision_repository(url: str, fallback: str) -> str:
    """The repository a github.com decision URL points into, else fallback."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if parsed.netloc == "github.com" and len(parts) >= 2 and is_repository("/".join(parts[:2])):
        return "/".join(parts[:2])
    return fallback


def candidates(record: VerdictRecord, target: str) -> Iterator[str]:
    """The tagging candidates in order, each a login in GitHub's syntax:
    the approver of the related earlier decision, the logins listed in the
    reviewers file of what the question concerns, then the author of the
    last commit to each file it concerns."""
    related = record.get("related")
    if related:
        approver = github.decision_approver(_decision_repository(related, target), related)
        if approver and is_login(approver):
            yield approver
    for login in reviewers(target) or []:
        if is_login(login):
            yield login
    for path in record.get("files", []):
        author = github.last_commit_author(target, path)
        if author and is_login(author):
            yield author


def choose(record: VerdictRecord, identity: str | None) -> TagResult:
    concerns = record.get("concerns", {})
    target = concerns.get("repository") or concerns.get("lore")
    if target is None:
        raise Refused("this question is about one person's way of working, which is never posted")
    for login in candidates(record, target):
        if github.write_access(target, login) is True:
            return {"version": VERSION, "action": "tag", "line": f"@{login}"}
    login = github.session_login(config.load().login)
    attended = person_in_session()
    if login is None:
        return {"version": VERSION, "action": "picker" if attended else "untagged",
                "line": None if attended else UNTAGGED_LINE}
    if github.write_access(target, login) is not True:
        return {"version": VERSION, "action": "untagged", "line": UNTAGGED_LINE}
    if identity is not None:
        return {"version": VERSION, "action": "tag", "line": f"@{login}"}
    if attended:
        return {"version": VERSION, "action": "picker", "line": None}
    return {"version": VERSION, "action": "untagged", "line": UNTAGGED_LINE}


def run(args: TagArgs) -> int:
    """Print a contracts.TagResult."""
    if not _HASH.fullmatch(args.hash):
        raise Refused("--hash must be a question's hash, 64 lowercase hex characters")
    if args.identity is not None and not _IDENTITY.fullmatch(args.identity):
        raise Refused("--identity must name a github-app identity")
    if args.posting_as is not None:
        raise Refused("tag takes --identity, the github-app identity a post goes through, "
                      "not the login it goes out as")
    records = read_records({args.hash})
    if records is None:
        raise Refused("cannot read the verdict records")
    record = records.get(args.hash)
    if record is None or record["verdict"] != "ask":
        raise Refused("no `ask` verdict recorded for this hash in the last 2 hours; run the two "
                      "calls on the question first")
    if "category" in record:
        raise Refused("a question with a category goes in no post: ask the person directly, or "
                      "in the repository's private security advisory")
    print_json(choose(record, args.identity))
    return 0
