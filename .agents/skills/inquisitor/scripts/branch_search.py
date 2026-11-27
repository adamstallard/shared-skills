"""The questions-branch commands an Igor, an AI teammate of the igor
project, runs for its worker, the agent it starts to work one item (an
issue or pull request): `branch-search`,
`miss-check` and `file-answer`. Their JSON is a contract with igor (tasks
2.3b to 2.3d): a test compares each command's output field for field with
its stored copy in fixtures/json/.

The labelling of a questions branch's files lives here too, and filter 1,
the search that looks for an earlier answer to a question (search.py),
imports it, so both label a file the same way (inquisitor spec: *A
questions-branch decision counts only unchanged and by write access*
through *In an Igor's run, a file about another repository is input*).

Owned by build part P4 of the implementation plan. Standard library only.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import branches
import github
from common import VERSION, Refused, print_json, state_home
from contracts import BranchHit, BranchSearchResult, FileAnswerResult, MissCheckResult
from formats import (HandledFile, HashOnlyMiss, LogFile, MissFile, Unreadable, is_login,
                     is_repository, miss_hash, parse)
from qtext import Question, line_kind, question_hash, question_text, terms

# Words too common to say what a question is about: a hit matching only
# these matches nothing. Filter 1's matching is plain text (inquisitor spec:
# *Filter 1 matches terms as plain text and caps its hits*); which words
# count is the implementation's choice.
STOPWORDS = frozenset("""
a about after all also an and any are as at be been before being but by can could did do
does doing for from had has have how i if in into is it its may me might must my no not of
on or our over should so than that the their them then there these they this those to too
under up us was we were what when where which while who whom why will with would you your
""".split())


def question_terms(text: str) -> set[str]:
    """The terms filter 1 matches: the question's terms (qtext.terms)
    without STOPWORDS."""
    return terms(text) - STOPWORDS


def count_terms(wanted: set[str], text: str) -> int:
    """How many of the terms in `wanted` appear in `text`, each counted once."""
    return len(wanted & terms(text))


# -- git and gh helpers ----------------------------------------------------------

def _run(args: list[str], stdin: str | None = None, timeout: float = 60) -> str | None:
    """A command's stdout, or None when it fails or cannot start."""
    try:
        done = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def gh_json(args: list[str]) -> Any:
    """`gh <args>`'s stdout read as JSON, or None when gh fails or prints
    something else."""
    out = _run(["gh", *args])
    if out is None:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def cache_clone(repository: str) -> Path:
    """A bare repository under the state home holding repository's fetched
    questions branch, created when missing."""
    owner, name = repository.split("/")
    clone = state_home() / "inquisitor" / "branches" / owner / name
    if not (clone / "HEAD").exists():
        clone.mkdir(parents=True, exist_ok=True)
        if _run(["git", "init", "-q", "--bare", str(clone)]) is None:
            raise Refused(f"cannot create a git repository at {clone}")
    return clone


def is_lore_repository(repository: str, configured: set[str]) -> bool:
    """Whether repository is a lore repository: one the configuration names,
    or one whose default branch holds `entries/`."""
    if repository in configured:
        return True
    listing = gh_json(["api", f"repos/{repository}/contents/entries"])
    return isinstance(listing, list)


# -- labelling a branch's files ----------------------------------------------------

_GITHUB_REPO = re.compile(r"https://github\.com/([^/]+/[^/]+)/")
_RANK = {"private": 0, "internal": 1, "public": 2}


@dataclass
class Checks:
    """What labelling asks GitHub, cached for one command. offline is set
    for a question with a category: nothing is then asked, so every
    permission and visibility reads as unknown, and an unknown permission
    counts as no write access."""

    offline: bool = False
    _access: dict[tuple[str, str], bool] = field(default_factory=lambda: {})
    _vis: dict[str, github.Visibility | None] = field(default_factory=lambda: {})

    def can_write(self, repository: str | None, login: str) -> bool:
        """Write access. An unreadable permission, a malformed repository and
        a login off GitHub's login syntax, such as an App's `<slug>[bot]`,
        count as none (inquisitor spec: *A permission
        that cannot be read is no write access*)."""
        if self.offline or repository is None or not is_repository(repository) or not is_login(login):
            return False
        key = (repository, login)
        if key not in self._access:
            self._access[key] = github.write_access(repository, login) is True
        return self._access[key]

    def visibility(self, repository: str) -> github.Visibility | None:
        if self.offline or not is_repository(repository):
            return None
        if repository not in self._vis:
            self._vis[repository] = github.visibility(repository)
        return self._vis[repository]


def file_visibility(f: LogFile | MissFile | Unreadable, branch_repo: str,
                    checks: Checks) -> github.Visibility:
    """The most private of: branch_repo, which holds the file; the file's
    `repository` and `asked_from`; and where its GitHub `asked_in` points. A
    Linear or Discord `asked_in`, an unreadable file and any visibility
    that cannot be read count as private (inquisitor spec: *A log or miss
    file is as private as its more private repository*)."""
    if isinstance(f, Unreadable):
        return "private"
    repos = [branch_repo, f.repository, f.asked_from]
    if f.asked_in is not None:
        m = _GITHUB_REPO.match(f.asked_in)
        if not m:
            return "private"
        repos.append(m.group(1))
    found: list[github.Visibility] = []
    for repo in repos:
        if repo is None:
            continue
        vis = checks.visibility(repo)
        if vis is None:
            return "private"
        found.append(vis)
    return min(found, key=lambda v: _RANK[v])


def _tags(question: str) -> list[str] | None:
    """The logins a logged question's tag lines name, or None when it tags
    no one."""
    logins = [line.strip()[1:] for line in question.split("\n")[1:]
              if line_kind(line) == "tag" and line.strip().startswith("@")]
    return logins or None


def _group_hash(question: str) -> str:
    """The hash grouping a branch's log files: the text under `## Question`
    reduced as qtext.question_text reduces a post's question (inquisitor
    spec: *Among files with the
    same question, only the newest answer counts*)."""
    return question_hash(question_text(Question(kind="post", question=question)))


def _match_text(question: str) -> str:
    """A logged question's text as filter 1 matches it: without its tag,
    concerns, related-decision and person-required lines."""
    return question_text(Question(kind="post", question=question))


def _body_text(content: str) -> str:
    """An unreadable file's text to match: the lines after any frontmatter,
    without `## ` headings, so the format's own words match nothing."""
    lines = content.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[0] == "---" and "---" in lines[1:]:
        lines = lines[lines.index("---", 1) + 1:]
    return "\n".join(line for line in lines if not line.startswith("## "))


@dataclass
class Labelled:
    """One file's hit, before matching. text: what its terms are matched
    against. order: its place in the branch's commit order."""

    hit: BranchHit
    text: str
    order: int
    pinned: tuple[str, str] | None = None


Landed = Literal[True, False] | None


def _pinned(recorded_in: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"(.+)@([0-9a-f]{40})", recorded_in)
    return (m.group(1), m.group(2)) if m and not recorded_in.startswith("https://") else None


def landed_check(clone: Path | None, repository: str, path: str, commit: str, checks: Checks) -> bool:
    """Whether a pinned commit has landed (inquisitor spec: *An answer
    recorded on a work branch counts for other work once it lands*): an
    ancestor of the default branch, or in a merged pull request, with the
    repository's default branch holding the document. False when the script
    cannot tell."""
    if checks.offline:
        return False
    if clone is not None and _origin(clone) == repository:
        if branches.landed(clone, commit) is True:
            return True
    else:
        meta = gh_json(["api", f"repos/{repository}"])
        default = cast(dict[str, Any], meta).get("default_branch") if isinstance(meta, dict) else None
        if isinstance(default, str):
            cmp = gh_json(["api", f"repos/{repository}/compare/{commit}...{default}"])
            if isinstance(cmp, dict) and cast(dict[str, Any], cmp).get("status") in ("ahead", "identical"):
                return True
    pulls = gh_json(["api", f"repos/{repository}/commits/{commit}/pulls"])
    merged = isinstance(pulls, list) and any(
        isinstance(p, dict) and cast(dict[str, Any], p).get("merged_at") for p in cast(list[Any], pulls))
    return merged and gh_json(["api", f"repos/{repository}/contents/{path}"]) is not None


def _origin(clone: Path) -> str | None:
    out = _run(["git", "-C", str(clone), "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", out.strip()) if out else None
    return m.group(1) if m else None


def label_branch(files: list[branches.BranchFile], branch_repo: str, lore_branch: bool,
                 checks: Checks, item: str | None = None, item_private: bool = False,
                 clone: Path | None = None) -> list[Labelled]:
    """Every file of a questions branch that filter 1 may show, labelled as
    the inquisitor spec's authority rules label it, in branch order.
    Citation, handled and hash-only miss files are never shown. Given an
    Igor run's item, a file about another repository is input and a file
    more private than the item is left out."""
    parsed = [parse(f.path, f.content, lore_branch) for f in files]
    if item is not None:
        # A file more private than the item is dropped before any rule
        # reads it, so that it neither lends its answer to a file it names
        # nor supersedes another file.
        item_vis = "private" if item_private else checks.visibility(item)
        kept = [i for i, f in enumerate(parsed)
                if not isinstance(f, (LogFile, MissFile, Unreadable))
                or not github.more_visible(item_vis, file_visibility(f, branch_repo, checks))]
        files = [files[i] for i in kept]
        parsed = [parsed[i] for i in kept]

    def concerned(f: LogFile) -> str | None:
        return f.repository or (branch_repo if lore_branch else None)

    def would_count(i: int) -> bool:
        f = parsed[i]
        if not isinstance(f, LogFile) or f.answer is None or f.answer.authority != "decision":
            return False
        if bool(getattr(files[i], "changed", False)):
            return False
        if item is not None and f.repository is not None and f.repository != item:
            return False
        return checks.can_write(concerned(f), f.answer.answered_by)

    counts = [would_count(i) for i in range(len(parsed))]
    by_name = {f.name: i for i, f in enumerate(parsed) if isinstance(f, LogFile)}

    # A named file's answer is the newest counting answer file that names
    # it, when that answer file's answered_by is tagged by the named file's
    # question or, if that question tags no one, can write to what the named
    # file concerns.
    named_answer: dict[int, int] = {}
    for i, f in enumerate(parsed):
        if not counts[i] or not isinstance(f, LogFile) or f.answer is None:
            continue
        for name in f.answer.answers:
            t = by_name.get(name)
            if t is None or t == i:
                continue
            target = parsed[t]
            assert isinstance(target, LogFile)
            tags = _tags(target.question)
            ok = (f.answer.answered_by in tags if tags is not None
                  else checks.can_write(concerned(target), f.answer.answered_by))
            if ok:
                named_answer[t] = i  # later files overwrite: the newest wins
    replaced = {i for i, f in enumerate(parsed)
                if counts[i] and isinstance(f, LogFile) and f.answer is not None
                and any(by_name.get(n) in named_answer and named_answer[by_name[n]] != i
                        and named_answer[by_name[n]] > i for n in f.answer.answers)}

    # Hash groups: among the answer files that would count, and the
    # unanswered files that took a named answer (placed where that answer
    # file is), only the newest counts.
    newness: dict[int, int] = {}
    for i, f in enumerate(parsed):
        if not isinstance(f, LogFile):
            continue
        if counts[i]:
            newness[i] = i
        elif f.answer is None and i in named_answer:
            newness[i] = named_answer[i]
    groups: dict[str, list[int]] = {}
    for i in newness:
        f = parsed[i]
        assert isinstance(f, LogFile)
        groups.setdefault(_group_hash(f.question), []).append(i)
    superseded: set[int] = set()
    for members in groups.values():
        newest = max(newness[i] for i in members)
        superseded |= {i for i in members if newness[i] != newest}

    out: list[Labelled] = []
    for i, f in enumerate(parsed):
        path = files[i].path
        if isinstance(f, (HandledFile, HashOnlyMiss)) or not isinstance(f, (LogFile, MissFile, Unreadable)):
            continue
        if isinstance(f, Unreadable):
            out.append(Labelled({"path": path, "question": "", "answer": None, "label": "input",
                                 "reason": "unreadable", "landed": None}, _body_text(files[i].content), i))
            continue
        if isinstance(f, MissFile):
            out.append(Labelled({"path": path, "question": f.question, "answer": None,
                                 "label": "input", "reason": "miss", "landed": None,
                                 "filter": f.filter, "said": f.said}, _match_text(f.question), i))
            continue
        source = f.answer
        if source is None and i in named_answer:
            answer_file = parsed[named_answer[i]]
            assert isinstance(answer_file, LogFile)
            source = answer_file.answer
        hit: BranchHit = {"path": path, "question": f.question,
                          "answer": source.text if source is not None else None,
                          "label": "input", "landed": None}
        pinned = _pinned(source.recorded_in) if source is not None else None
        if source is None:
            hit["reason"] = "unanswered"
        elif source.authority == "input":
            hit["reason"] = "input"
        elif f.answer is not None and not counts[i]:
            hit["reason"] = "unconfirmed"
        elif i in superseded or i in replaced:
            hit["reason"] = "superseded"
        elif item is not None and f.repository is not None and f.repository != item:
            hit["reason"] = "unconfirmed"
        else:
            hit["label"] = "decision"
        if pinned is not None:
            repo = concerned(f) or branch_repo
            hit["landed"] = landed_check(clone, repo, pinned[0], pinned[1], checks)
        out.append(Labelled(hit, _match_text(f.question), i, pinned))
    return out


def rank(hits: list[Labelled], wanted: set[str]) -> list[tuple[Labelled, int]]:
    """The hits matching at least one wanted term: those labelled decision
    first, then by terms matched, branch order among ties."""
    scored = [(h, count_terms(wanted, h.text)) for h in hits]
    kept = [(h, n) for h, n in scored if n > 0]
    kept.sort(key=lambda p: (p[0].hit["label"] != "decision", -p[1], p[0].order))
    return kept


# -- the commands ------------------------------------------------------------------

@dataclass(frozen=True)
class BranchSearchArgs:
    """repository: the questions branch's repository. item: the repository
    of the item an Igor's run works on; given, the search applies that run's
    rules. linear: the item is a Linear issue, so it counts as private. The
    question comes on standard input."""

    repository: str
    item: str | None = None
    linear: bool = False


@dataclass(frozen=True)
class MissCheckArgs:
    repository: str
    surface: Literal["github", "linear", "discord"]
    id: str


@dataclass(frozen=True)
class FileAnswerArgs:
    """date and suffix: a questions-branch file name's `yyyy-mm-dd` and 6
    lowercase hex digits."""

    repository: str
    date: str
    suffix: str


def _configured_lore() -> set[str]:
    import config
    try:
        return {r.repository for r in config.load().lore if r.repository}
    except Refused:
        return set()


def _branch(repository: str) -> tuple[Path, list[branches.BranchFile]]:
    """Fetch repository's questions branch into its cache clone and list its
    files, refusing (exit 1, nothing printed) when that fails."""
    if not is_repository(repository):
        raise Refused(f"{repository!r} is not an owner/repo")
    clone = cache_clone(repository)
    if not branches.fetch(clone, repository):
        raise Refused(f"cannot fetch the questions branch of {repository}")
    files = branches.list_files(clone, repository)
    if files is None:
        raise Refused(f"cannot read the questions branch of {repository}")
    return clone, files


def run_branch_search(args: BranchSearchArgs) -> int:
    """Print a contracts.BranchSearchResult; print nothing and exit 1 when
    the branch cannot be fetched."""
    if args.item is not None and not is_repository(args.item):
        raise Refused(f"{args.item!r} is not an owner/repo")
    question = sys.stdin.read()
    clone, files = _branch(args.repository)
    lore_branch = is_lore_repository(args.repository, _configured_lore())
    labelled = label_branch(files, args.repository, lore_branch, Checks(), item=args.item,
                            item_private=args.linear, clone=clone)
    wanted = question_terms(question_text(Question(kind="text", question=question)))
    result: BranchSearchResult = {"version": VERSION, "repository": args.repository,
                                  "hits": [h.hit for h, _ in rank(labelled, wanted)]}
    print_json(result)
    return 0


def run_miss_check(args: MissCheckArgs) -> int:
    """Print a contracts.MissCheckResult without asking GitHub anyone's
    permission (github.write_access), since only someone with write access
    could have pushed a file to the branch."""
    _, files = _branch(args.repository)
    path = f"misses/{miss_hash(args.surface, args.id)}.md"
    backed = False
    for f in files:
        if f.path == path:
            read = parse(f.path, f.content, False)
            backed = isinstance(read, HashOnlyMiss) or (isinstance(read, MissFile)
                                                         and read.said_by is not None)
    result: MissCheckResult = {"version": VERSION, "backed": backed}
    print_json(result)
    return 0


def run_file_answer(args: FileAnswerArgs) -> int:
    """Print a contracts.FileAnswerResult: the named file's answer, as the
    newest counting answer file naming it decides it, or null."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date) or not re.fullmatch(r"[0-9a-f]{6}", args.suffix):
        raise Refused("the date must be yyyy-mm-dd and the suffix 6 lowercase hex digits")
    clone, files = _branch(args.repository)
    pattern = re.compile(rf"questions/{re.escape(args.date)}-[a-z0-9-]+-{args.suffix}\.md")
    matching = [i for i, f in enumerate(files) if pattern.fullmatch(f.path)]
    if len(matching) != 1:
        raise Refused(f"{len(matching)} files on the questions branch of {args.repository} "
                      f"have that date and suffix; exactly one must")
    target = files[matching[0]]
    lore_branch = is_lore_repository(args.repository, _configured_lore())
    answer = named_answer_of(files, target.path, args.repository, lore_branch, Checks(), clone)
    result: FileAnswerResult = {"version": VERSION, "answer": answer}
    print_json(result)
    return 0


def named_answer_of(files: list[branches.BranchFile], path: str, branch_repo: str,
                    lore_branch: bool, checks: Checks, clone: Path | None = None) -> str | None:
    """The answer that the newest counting answer file naming the file at
    path gives it (inquisitor spec: *A named file's answer is the newest
    answer file naming it*). None when there is none, or when the file holds
    its own answer."""
    labelled = label_branch(files, branch_repo, lore_branch, checks, clone=clone)
    target = parse(path, next(f.content for f in files if f.path == path), lore_branch)
    if not isinstance(target, LogFile) or target.answer is not None:
        return None
    for h in labelled:
        if h.hit["path"] == path:
            return h.hit["answer"]
    return None
