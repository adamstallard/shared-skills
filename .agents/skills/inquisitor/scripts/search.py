"""Filter 1's search, used by the first call, and the `search` command that
runs it alone for the answer service (inquisitor spec: *Filter 1 searches
every place an answer is recorded* through *Only an answer with authority
stops a question* and its authority rules; *The search command runs filter
1 alone for the answer service*).

Owned by P4 (tasks 2.3, 2.3e). Standard library only.
"""

import datetime
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import config
import github
from branch_search import (Checks, Labelled, checkout, count_terms, gh_json, label_branch, read_branch,
                           question_terms, rank)
from common import VERSION, Refused, igor_run, print_json, service_state_dir
from contracts import CloneFreshness, Concerns, QuestionIn, SearchHit, SearchInput, SearchResult
from formats import is_login, is_repository
from private_files import read_private
from qtext import Question, question_text

CAP = 20
ISSUE_LIMIT = 300
QUOTE_MAX = 600
LORE_STATUS_WHY = {"provisional": "unreviewed", "deprecated": "retired"}
IGOR_NOTE = "runs as in an Igor's run because IGOR_RUN is set"


@dataclass(frozen=True)
class SearchArgs:
    """input: a SearchInput file, or `-` for standard input, the only way a
    question with a category may come."""

    input: str


# -- git reading -------------------------------------------------------------------

def _git(clone: Path, *args: str, stdin: str | None = None) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(clone), *args], input=stdin, capture_output=True,
                              text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def origin_repository(clone: Path) -> str | None:
    return config.origin_repository(clone)


def default_ref(clone: Path) -> str | None:
    """The clone's remote-tracking default branch, such as
    `refs/remotes/origin/main`, or None."""
    out = _git(clone, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if out and out.strip():
        return out.strip()
    for name in ("main", "master"):
        if _git(clone, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{name}") is not None:
            return f"refs/remotes/origin/{name}"
    return None


def read_tree(clone: Path, ref: str, prefixes: list[str]) -> dict[str, str] | None:
    """Every `.md` file under prefixes at ref, read with git's object
    store, never a checkout."""
    listing = _git(clone, "ls-tree", "-r", "-z", "--name-only", ref, "--", *prefixes)
    if listing is None:
        return None
    paths = [p for p in listing.split("\0") if p.endswith(".md")]
    files: dict[str, str] = {}
    for path in paths:
        text = _git(clone, "show", f"{ref}:{path}")
        if text is not None:
            files[path] = text
    return files


def last_fetch(clone: Path) -> str | None:
    """When a fetch, including the one inside `git pull` or `git clone`,
    last updated the clone's remote-tracking default branch, from its
    reflog, as ISO 8601 UTC; None when unknown."""
    ref = default_ref(clone)
    if ref is None:
        return None
    out = _git(clone, "log", "-g", "-n", "50", "--date=unix", "--format=%gd%x09%gs", ref)
    for line in (out or "").splitlines():
        selector, _, subject = line.partition("\t")
        m = re.search(r"@\{(\d+)\}$", selector)
        if m and subject.split(":")[0].split(" ")[0] in ("fetch", "pull", "clone"):
            when = datetime.datetime.fromtimestamp(int(m.group(1)), tz=datetime.timezone.utc)
            return when.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


# -- matching ---------------------------------------------------------------------

def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def best_paragraph(wanted: set[str], text: str) -> tuple[str, int]:
    """The paragraph matching the most wanted terms, and how many."""
    best, best_n = "", 0
    for p in paragraphs(text):
        n = count_terms(wanted, p)
        if n > best_n:
            best, best_n = p, n
    return best, best_n


def quote(text: str) -> str:
    return text if len(text) <= QUOTE_MAX else text[:QUOTE_MAX].rstrip() + " …"


# -- decision documents -------------------------------------------------------------

DOC_PREFIXES = ["openspec/specs", "openspec/changes"]


def doc_hits(files: dict[str, str], wanted: set[str], repository: str | None, label: str,
             why: str | None = None) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for path, text in sorted(files.items()):
        para, n = best_paragraph(wanted, text)
        if n == 0:
            continue
        hit: SearchHit = {"source": "decision-document", "label": "decision" if label == "decision" else "input",
                          "repository": repository, "where": path, "quote": quote(para), "terms": n}
        if why is not None:
            hit["why"] = why
        hits.append(hit)
    return hits


def work_branch_author_ok(top: Path, repository: str, checks: Checks, login: str | None) -> bool:
    """*A work-branch decision answers only its own work*: the pull request
    is not from a fork, and its author, or with no pull request the
    session's login, has write access. Always False offline."""
    if checks.offline:
        return False
    pr = _gh_in(top, ["pr", "view", "--json", "author,isCrossRepository"])
    if isinstance(pr, dict):
        p = cast(dict[str, Any], pr)
        if p.get("isCrossRepository") is not False:
            return False
        author = p.get("author")
        name = cast(dict[str, Any], author).get("login") if isinstance(author, dict) else None
        return isinstance(name, str) and checks.can_write(repository, name)
    session = github.session_login(login)
    return session is not None and checks.can_write(repository, session)


def _gh_in(directory: Path, args: list[str]) -> Any:
    try:
        done = subprocess.run(["gh", *args], cwd=directory, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def work_branch_docs(top: Path, ref: str) -> dict[str, str] | None:
    """The decision documents the current work's branch changed from the
    default branch, as committed on it; None when the two share no merge
    base the clone can find, as in a shallow clone."""
    base = _git(top, "merge-base", ref, "HEAD")
    if base is None:
        return None
    changed = _git(top, "diff", "-z", "--name-only", "--no-renames", "--diff-filter=AM", base.strip(), "HEAD", "--",
                   *DOC_PREFIXES)
    files: dict[str, str] = {}
    for path in (changed or "").split("\0"):
        if path.endswith(".md"):
            text = _git(top, "show", f"HEAD:{path}")
            if text is not None:
                files[path] = text
    return files


# -- issues -----------------------------------------------------------------------

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def decision_block(body: str) -> str:
    """An issue's decision block: its body before its first heading when
    that holds text, otherwise the first section whose heading starts with
    "Decision" (inquisitor spec:
    *Only four kinds of document are decision documents*)."""
    lines = body.replace("\r\n", "\n").split("\n")
    opening: list[str] = []
    for i, line in enumerate(lines):
        if _HEADING.match(line):
            break
        opening.append(line)
    else:
        i = len(lines)
    if "\n".join(opening).strip():
        return "\n".join(opening).strip()
    for j in range(i, len(lines)):
        m = _HEADING.match(lines[j])
        if m and m.group(1).strip().startswith("Decision"):
            section: list[str] = []
            for line in lines[j + 1:]:
                if _HEADING.match(line):
                    break
                section.append(line)
            return "\n".join(section).strip()
    return ""


def _login(author: Any) -> str | None:
    name = cast(dict[str, Any], author).get("login") if isinstance(author, dict) else None
    return name if isinstance(name, str) else None


def issue_hits(repository: str, wanted: set[str], checks: Checks) -> tuple[list[SearchHit], bool] | None:
    """Hits for each issue: its decision block, labelled by its author's
    write access, and its best-matching other text, as input. The second
    value says whether the list reached ISSUE_LIMIT, which leaves older
    issues unread. None when gh cannot read the issues."""
    issues = gh_json(["issue", "list", "--repo", repository, "--state", "all", "--limit", str(ISSUE_LIMIT),
                      "--json", "number,title,body,author,url,comments"])
    if not isinstance(issues, list):
        return None
    hits: list[SearchHit] = []
    for raw in cast(list[Any], issues):
        if not isinstance(raw, dict):
            continue
        issue = cast(dict[str, Any], raw)
        body = issue.get("body") if isinstance(issue.get("body"), str) else ""
        url = issue.get("url") if isinstance(issue.get("url"), str) else repository
        assert isinstance(body, str) and isinstance(url, str)
        block = decision_block(body)
        n = count_terms(wanted, block)
        if n:
            author = _login(issue.get("author"))
            ok = author is not None and is_login(author) and checks.can_write(repository, author)
            hit: SearchHit = {"source": "issue", "label": "decision" if ok else "input",
                              "repository": repository, "where": url, "quote": quote(block), "terms": n}
            if not ok:
                hit["why"] = "decision block by an author without write access"
            hits.append(hit)
        rest = body.replace(block, "", 1) if block else body
        candidates: list[tuple[str, str]] = [(url, f"{issue.get('title', '')}\n\n{rest}")]
        comments = issue.get("comments")
        for c in cast(list[Any], comments) if isinstance(comments, list) else []:
            if isinstance(c, dict):
                cd = cast(dict[str, Any], c)
                text, where = cd.get("body"), cd.get("url")
                if isinstance(text, str):
                    candidates.append((where if isinstance(where, str) else url, text))
        best: tuple[str, str, int] = ("", "", 0)
        for where, text in candidates:
            para, m = best_paragraph(wanted, text)
            if m > best[2]:
                best = (where, para, m)
        if best[2]:
            hits.append({"source": "issue", "label": "input", "repository": repository,
                         "where": best[0], "quote": quote(best[1]), "terms": best[2],
                         "why": "issue text"})
    return hits, len(cast(list[Any], issues)) >= ISSUE_LIMIT


# -- questions branches -------------------------------------------------------------

def branch_hits(labelled: list[Labelled], wanted: set[str], repository: str,
                work: Path | None) -> list[SearchHit]:
    """Questions-branch hits as filter 1 shows them. A decision whose pinned
    commit has not landed is labelled as not yet merged: it stays a decision
    in work whose branch holds the commit, and is input elsewhere."""
    hits: list[SearchHit] = []
    for h, n in rank(labelled, wanted):
        b = h.hit
        hit: SearchHit = {"source": "questions-branch", "label": b["label"], "repository": repository,
                          "where": b["path"],
                          "quote": quote(b["answer"] if b["answer"] is not None else b["question"]),
                          "terms": n, "path": b["path"], "question": b["question"],
                          "answer": b["answer"], "landed": b["landed"]}
        if "reason" in b:
            hit["reason"] = b["reason"]
            hit["why"] = b["reason"]
        if "filter" in b:
            hit["filter"] = b["filter"]
        if "said" in b:
            hit["said"] = b["said"]
        if b["label"] == "decision" and b["landed"] is False:
            held = (work is not None and h.pinned is not None
                    and _git(work, "merge-base", "--is-ancestor", h.pinned[1], "HEAD") is not None)
            hit["why"] = "not yet merged"
            if not held:
                hit["label"] = "input"
        hits.append(hit)
    return hits


# -- lore ---------------------------------------------------------------------------

def frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """A lore entry's top-level frontmatter keys, as raw text, and its body;
    None when it has no frontmatter."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    keys: dict[str, str] = {}
    current: str | None = None
    for line in text[4:end].split("\n"):
        m = re.match(r"([A-Za-z_][\w-]*):\s?(.*)$", line)
        if m:
            current = str(m.group(1))
            keys[current] = m.group(2).strip()
        elif current is not None:
            keys[current] += "\n" + line
    body = text[end + 4:].lstrip("-").lstrip("\n")
    return keys, body


def _unquote(value: str) -> str:
    v = value.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def lore_hits(files: dict[str, str], wanted: set[str], repository: str | None,
              scopes: set[str]) -> list[SearchHit]:
    """Matching lore entries in scope; any other entry is never shown,
    counted or mentioned (inquisitor spec: *Filter 1 hides every lore entry
    outside the question's scope*). Only an `active` entry is an answer."""
    hits: list[SearchHit] = []
    for path, text in sorted(files.items()):
        read = frontmatter(text)
        if read is None or "conditions" not in read[0]:
            continue
        keys, body = read
        if _unquote(keys.get("scope", "")) not in scopes:
            continue
        n = count_terms(wanted, "\n".join([keys.get("claim", ""), keys.get("conditions", ""), body]))
        if n == 0:
            continue
        status = _unquote(keys.get("status", ""))
        claim = _unquote(keys.get("claim", ""))
        shown = body.strip() if status == "deprecated" or not claim else claim
        hit: SearchHit = {"source": "lore-entry", "label": "decision" if status == "active" else "input",
                          "repository": repository, "where": path, "quote": quote(shown), "terms": n}
        if status != "active":
            hit["why"] = LORE_STATUS_WHY.get(status, "unreadable")
        hits.append(hit)
    return hits


def serving(lore: tuple[config.LoreRepo, ...], concerns: Concerns) -> list[config.LoreRepo]:
    """The configured lore repositories serving what the question concerns;
    every one when it concerns nothing."""
    repo, team = concerns.get("repository"), concerns.get("lore")
    if repo is not None:
        return [r for r in lore if repo in r.repos or repo.split("/")[0] in r.owners]
    if team is not None:
        return [r for r in lore if r.repository == team or team.split("/")[0] in r.owners]
    return list(lore)


def igor_lore_search(text: str, wanted: set[str]) -> list[SearchHit] | None:
    """Lore and questions-branch hits from `igor lore-search`, the question
    on standard input; None when it fails or its output holds no list of
    hits."""
    try:
        done = subprocess.run(["igor", "lore-search"], input=text, capture_output=True, text=True,
                              timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        parsed: Any = json.loads(done.stdout)
    except json.JSONDecodeError:
        return None
    items: Any = cast(dict[str, Any], parsed).get("hits") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return None
    hits: list[SearchHit] = []
    for raw in cast(list[Any], items):
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, Any], raw)
        where, said = item.get("where", item.get("path")), item.get("quote", item.get("answer"))
        if not isinstance(where, str):
            continue
        q = said if isinstance(said, str) else ""
        repo = item.get("repository")
        hit: SearchHit = {"source": "igor-lore-search",
                          "label": "decision" if item.get("label") == "decision" else "input",
                          "repository": repo if isinstance(repo, str) else None, "where": where,
                          "quote": quote(q), "terms": count_terms(wanted, f"{q}\n{item.get('question', '')}")}
        why = item.get("why", item.get("reason"))
        if isinstance(why, str):
            hit["why"] = why
        hits.append(hit)
    return hits


# -- filter 1 -----------------------------------------------------------------------

def _text(question: QuestionIn) -> str:
    return question_text(Question(kind=question["kind"], question=question["question"],
                                  options=tuple(question.get("options", []))))


def subscribed_clone(repository: str) -> Path:
    """The answer service's clone of a subscribed repository."""
    owner, name = repository.split("/")
    return service_state_dir() / "clones" / owner / name


def filter1(question: QuestionIn, service: bool) -> SearchResult:
    """Filter 1's results for one question. service: read only the answer
    service's clones as last fetched, run no git fetch, and read questions
    branches (through GitHub's API) and issues only of the repositories
    those clones hold. Outside an Igor's run (common.igor_run() is None) it
    reads the configured lore clones; in one it searches lore only through
    `igor lore-search`. A question with a category is searched on the
    machine only: no fetch and no GitHub call."""
    cfg = config.load()
    text = _text(question)
    wanted = question_terms(text)
    concerns = question["concerns"]
    repo, team = concerns.get("repository"), concerns.get("lore")
    offline = "category" in question
    run = igor_run()
    checks = Checks(offline=offline)
    hits: list[SearchHit] = []
    not_searched: list[str] = []
    clones: list[CloneFreshness] = []
    if run is not None:
        sys.stderr.write(f"inquisitor: {IGOR_NOTE}\n")

    work = checkout() if not service else None
    work_repo = origin_repository(work) if work is not None else None

    # The repository's decision documents, issues and questions branch, each
    # where this mode can reach it.
    if repo is not None:
        if run == "worker":
            if work is not None and work_repo == repo:
                hits += _worker_docs(work, repo, wanted)
            else:
                not_searched.append(f"decision documents of {repo}: the worker's working tree "
                                    "holds another repository")
            not_searched += [f"issues of {repo}: an Igor worker's search covers only its working tree",
                             f"questions branch of {repo}: an Igor worker's search covers only its "
                             "working tree beyond igor lore-search"]
        else:
            clone = subscribed_clone(repo) if service else (work if work_repo == repo else None)
            if clone is not None and not clone.exists():
                clone = None
            if service and clone is None:
                not_searched.append(f"{repo}: the answer service holds no clone of it")
            elif clone is None:
                not_searched.append(f"decision documents of {repo}: no local clone of it")
            else:
                ref = default_ref(clone)
                files = read_tree(clone, ref, DOC_PREFIXES) if ref else None
                if files is None:
                    not_searched.append(f"decision documents of {repo}: its default branch cannot be read")
                else:
                    hits += doc_hits(files, wanted, repo, "decision")
                if service:
                    clones.append({"path": str(clone), "repository": repo, "fetched": last_fetch(clone)})
            not_searched.append(f"decision records of {repo}: igor's scribe's record path "
                                "(igor PR #202) is not set")
            if offline:
                not_searched.append(f"issues of {repo}: the question has a category, so nothing "
                                    "off the machine is searched")
            elif not service or clone is not None:
                found = issue_hits(repo, wanted, checks)
                if found is None:
                    not_searched.append(f"issues of {repo}: gh could not read them")
                else:
                    hits += found[0]
                    if found[1]:
                        not_searched.append(f"issues of {repo} older than the newest {ISSUE_LIMIT}")
            # When the repository is also a lore repository the lore loop
            # below searches, its questions branch is searched there, once,
            # as a lore branch.
            configured = {lore.repository for lore in cfg.lore}
            served = {lore.repository for lore in serving(cfg.lore, concerns)}
            if run is None and repo not in served and not (service and clone is None):
                hits += _branch(repo, repo in configured, checks, wanted, work, not_searched)
            elif run is not None:
                not_searched.append(f"questions branch of {repo}: {IGOR_NOTE}; searched through "
                                    "igor lore-search")
    # Work-branch decision documents: the current change's own.
    if run != "worker" and work is not None and not service:
        ref = default_ref(work)
        if ref is not None:
            changed = work_branch_docs(work, ref)
            if changed:
                own = repo is not None and repo == work_repo and work_branch_author_ok(
                    work, repo, checks, cfg.login)
                hits += doc_hits(changed, wanted, work_repo, "decision" if own else "input",
                                 "this change's, not yet merged" if own
                                 else "on a work branch, which answers only its own work")

    # Lore.
    if run is not None:
        not_searched.append(f"configured lore clones: {IGOR_NOTE}; lore is searched through "
                            "igor lore-search")
        found = igor_lore_search(text, wanted)
        if found is None:
            not_searched.append("lore: igor lore-search failed, so no lore was searched")
        else:
            hits += found
    else:
        scopes = {"global"}
        if repo is not None:
            scopes.add("project:" + repo.split("/")[1])
        for lore in serving(cfg.lore, concerns):
            clone = Path(lore.path)
            name = lore.repository or lore.path
            clones.append({"path": lore.path, "repository": lore.repository, "fetched": last_fetch(clone)})
            ref = default_ref(clone)
            entries = read_tree(clone, ref, ["entries"]) if ref else None
            if entries is None:
                not_searched.append(f"lore entries of {name}: its default branch cannot be read")
            else:
                hits += lore_hits(entries, wanted, lore.repository, scopes)
            if service and repo is None and team is not None and lore.repository == team and entries is not None:
                docs = read_tree(clone, ref, DOC_PREFIXES) if ref else None
                hits += doc_hits(docs or {}, wanted, lore.repository, "decision")
            if lore.repository is None:
                not_searched.append(f"questions branch of {name}: its origin is not a GitHub repository")
            else:
                hits += _branch(lore.repository, True, checks, wanted, work, not_searched)
                not_searched.append(f"decision records of {lore.repository}: igor's scribe's record "
                                    "path (igor PR #202) is not set")

    hits.sort(key=lambda h: (h["label"] != "decision", -h["terms"]))
    return {"version": VERSION, "hits": hits[:CAP], "not_searched": not_searched,
            "clones": clones, "left_out": max(0, len(hits) - CAP)}


def _worker_docs(work: Path | None, repo: str, wanted: set[str]) -> list[SearchHit]:
    """An Igor worker's decision documents: those in its working tree.
    Those its branch changed, those left uncommitted, and all of them when
    no merge base is found, are shown as input."""
    if work is None:
        return []
    files: dict[str, str] = {}
    for prefix in DOC_PREFIXES:
        for p in sorted((work / prefix).rglob("*.md")):
            try:
                files[str(p.relative_to(work))] = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    ref = default_ref(work)
    branch = work_branch_docs(work, ref) if ref else None
    changed = set(files) if branch is None else set(branch)
    dirty = _git(work, "status", "--porcelain", "-z", "-uall", "--no-renames", "--", *DOC_PREFIXES) or ""
    changed |= {e[3:] for e in dirty.split("\0") if len(e) > 3}
    same = {p: t for p, t in files.items() if p not in changed}
    other = {p: t for p, t in files.items() if p in changed}
    return (doc_hits(same, wanted, repo, "decision")
            + doc_hits(other, wanted, repo, "input", "on a work branch, which answers only its own work"))


def _branch(repository: str, lore_branch: bool, checks: Checks, wanted: set[str],
            work: Path | None, not_searched: list[str]) -> list[SearchHit]:
    """One questions branch's hits, read through GitHub's API. A question
    with a category (checks.offline) asks GitHub nothing, so its search
    reads no questions branch."""
    if checks.offline:
        not_searched.append(f"questions branch of {repository}: the question has a category, "
                            "so nothing off the machine is searched")
        return []
    files = read_branch(repository)
    if files is None:
        not_searched.append(f"questions branch of {repository}: it cannot be read")
        return []
    labelled = label_branch(files, repository, lore_branch, checks)
    return branch_hits(labelled, wanted, repository, work)


# -- the search command -------------------------------------------------------------

_KINDS = ("picker", "post", "text")
_CATEGORIES = ("vulnerability", "secret", "personal")


def parse_question(raw: Any) -> QuestionIn:
    """A QuestionIn checked field by field, or Refused."""
    if not isinstance(raw, dict):
        raise Refused("question must be a JSON object")
    q = cast(dict[str, Any], raw)
    kind, text = q.get("kind"), q.get("question")
    if kind not in _KINDS or not isinstance(text, str):
        raise Refused("question needs kind (picker, post or text) and question text")
    concerns_raw = q.get("concerns")
    if not isinstance(concerns_raw, dict):
        raise Refused("question needs concerns, an object")
    concerns: Concerns = {}
    for key in ("repository", "lore", "asked_from"):
        value = cast(dict[str, Any], concerns_raw).get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not is_repository(value):
            raise Refused(f"concerns.{key} must be owner/repo")
        concerns[key] = value
    out: QuestionIn = {"kind": kind, "question": text, "concerns": concerns}
    options = q.get("options")
    if options is not None:
        if not isinstance(options, list) or not all(isinstance(o, str) for o in cast(list[Any], options)):
            raise Refused("options must be a list of strings")
        out["options"] = cast(list[str], options)
    files = q.get("files")
    if files is not None:
        if not isinstance(files, list) or not all(isinstance(f, str) for f in cast(list[Any], files)):
            raise Refused("files must be a list of strings")
        out["files"] = cast(list[str], files)
    category = q.get("category")
    if category is not None:
        if category not in _CATEGORIES:
            raise Refused("category must be vulnerability, secret or personal")
        out["category"] = category
    return out


def read_input(path: str) -> SearchInput:
    """A SearchInput from a file only its owner can read
    (private_files.read_private) or standard input; a question with
    a category only from standard input (inquisitor spec: *The search
    command takes its question as the first call does*)."""
    try:
        parsed: Any = json.loads(read_private(path))
    except json.JSONDecodeError as e:
        raise Refused(f"the input is not JSON: {e}") from e
    if not isinstance(parsed, dict) or cast(dict[str, Any], parsed).get("version") != VERSION:
        raise Refused(f"the input must be a JSON object with version {VERSION}")
    question = parse_question(cast(dict[str, Any], parsed).get("question"))
    if "category" in question and path != "-":
        raise Refused("a question with a category comes only on standard input, never in a file")
    return {"version": VERSION, "question": question}


def run(args: SearchArgs) -> int:
    """Print filter1(question, service=True) as JSON. Unlike the first call,
    it issues no pass token and writes no verdict record; it writes no file
    and fetches nothing."""
    print_json(filter1(read_input(args.input)["question"], service=True))
    return 0
