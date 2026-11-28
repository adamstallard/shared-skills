"""`log`, which writes and pushes every log and miss file but those an Igor
writes itself, and `misses`, which lists misses for a review (inquisitor
spec: *A log file and a miss file have one format* and the `log` command's
requirements).

Owned by build part P5 of the implementation plan (tasks 2.4, 2.9). Standard library only.
"""

import dataclasses
import datetime
import json
import re
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, cast

import branches
import config
import github
from common import NotBuilt, Refused, VERSION, igor_run, print_json
from contracts import LogResult, MissesResult, MissOut
from credentials import matches_credentials
from formats import (Answer, HandledFile, HashOnlyMiss, LogFile, MissFile, QuestionsBranchFile,
                     Unreadable, is_answer_link, is_asked_in, is_login, is_recorded_in,
                     is_repository, log_name, miss_hash, parse, render, slug)
from private_files import read_private
from qtext import Question, question_text


@dataclass(frozen=True)
class LogArgs:
    """input: a private contracts.LogInput file. service: the option only
    the answer service passes; it allows handled files, hash-only miss
    files, reply-id miss names and Linear or Discord answer links, and keeps
    nothing pending. asked_from: the answer service's `asked_from`
    (service only). hash_only: write a hash-only miss file (service only).
    confirm_visible: the person confirmed sending the record somewhere more
    visible than its source."""

    input: str
    service: bool = False
    asked_from: str | None = None
    hash_only: bool = False
    confirm_visible: bool = False


@dataclass(frozen=True)
class MissesArgs:
    """repository or lore: whose questions branch to list; filter: only
    misses against that filter."""

    repository: str | None = None
    lore: str | None = None
    filter: str | None = None


# -- shared with cite and lore -------------------------------------------------

_RANK = {"private": 0, "internal": 1, "public": 2}
CLOSING_HEADINGS = ("## Rephrased question", "## Discussion", "## Answer")
_GITHUB_REPO = re.compile(r"https://github\.com/([^/]+/[^/]+)/(?:issues|pull)/[0-9]+")
_RE_LINE = re.compile(r"Re: \S+")


def today() -> str:
    """Today's date in UTC, as yyyy-mm-dd."""
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def random_hex() -> str:
    """Six random lowercase hex digits, for a file's name."""
    return secrets.token_hex(3)


class Visibility:
    """Repository visibilities, each read from GitHub at most once per
    command. An unreadable one counts as private for where something comes
    from and as public for where it goes (inquisitor spec: *An unreadable
    visibility counts against sharing*)."""

    def __init__(self) -> None:
        self._seen: dict[str, github.Visibility | None] = {}

    def of(self, repository: str) -> github.Visibility | None:
        if not is_repository(repository):
            return None
        if repository not in self._seen:
            self._seen[repository] = github.visibility(repository)
        return self._seen[repository]

    def source_rank(self, repository: str | None) -> int:
        """A source's rank: private 0, internal 1, public 2; unknown 0."""
        value = self.of(repository) if repository else None
        return _RANK[value] if value else 0

    def destination_rank(self, repository: str) -> int:
        """A destination's rank; unknown 2."""
        value = self.of(repository)
        return _RANK[value] if value else 2

    def name(self, repository: str) -> str:
        value = self.of(repository)
        return value if value else "visibility unreadable"


def link_repository(url: str) -> str | None:
    """The repository a github.com issue or pull request URL points into;
    None for any other URL, such as a Linear or Discord one, which callers
    count as a private thread."""
    m = _GITHUB_REPO.match(url)
    return m.group(1) if m and is_repository(m.group(1)) else None


def file_rank(branch_repository: str, file: QuestionsBranchFile | Unreadable,
              vis: Visibility) -> int:
    """A questions-branch file's visibility rank: that of the most private
    of the branch's repository, the file's `repository` and `asked_from`, and the
    repository a GitHub `asked_in` points into; a Linear or Discord
    `asked_in`, or an unreadable file, counts as private (inquisitor spec:
    *A log or miss file is as private as its more private repository*)."""
    if isinstance(file, Unreadable):
        return 0
    ranks = [vis.source_rank(branch_repository)]
    if isinstance(file, (LogFile, MissFile)):
        for repository in (file.repository, file.asked_from):
            if repository is not None:
                ranks.append(vis.source_rank(repository))
        if file.asked_in is not None:
            linked = link_repository(file.asked_in)
            ranks.append(vis.source_rank(linked) if linked else 0)
    return min(ranks)


def _git_top(cwd: Path) -> Path | None:
    try:
        done = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None


def current_repository() -> str | None:
    """The repository holding the current work: the origin of the git
    working tree the command runs in, or None outside one."""
    top = _git_top(Path.cwd())
    return config.origin_repository(top) if top else None


# -- the questions-branch adapter ------------------------------------------------
# Every call this module makes into the branches module, which reads and
# writes questions branches through GitHub's API, goes through the
# functions below.

def branch_files(repository: str) -> list[branches.BranchFile] | None:
    """Every file on repository's questions branch, oldest first, or None
    when the branch cannot be read."""
    return branches.list_files(repository)


def push_to_branch(repository: str, path: str, content: str, as_inquisitor: bool,
                   service: bool) -> branches.PushResult:
    """Push one file to repository's questions branch, its commit's message
    `inquisitor: log <path>`."""
    return branches.push_file(repository, path, content, as_inquisitor, service)


def read_branch(repository: str) -> list[branches.BranchFile]:
    """branch_files, refusing when the branch cannot be read."""
    files = branch_files(repository)
    if files is None:
        raise Refused(f"cannot read the questions branch of {repository}")
    return files


def load_json(path: str) -> dict[str, Any]:
    """The JSON object, with `"version": 1`, in an input file that only its
    owner can read (private_files.read_private refuses any other)."""
    text = read_private(path)
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise Refused(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise Refused(f"{path} does not hold a JSON object")
    obj = cast(dict[str, Any], data)
    if obj.get("version") != VERSION:
        raise Refused(f"{path} does not hold \"version\": {VERSION}")
    return obj


def opt_str(obj: dict[str, Any], key: str, where: str) -> str | None:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise Refused(f"{where}'s {key} is not a string")
    return value


def req_str(obj: dict[str, Any], key: str, where: str) -> str:
    value = opt_str(obj, key, where)
    if not value:
        raise Refused(f"{where} has no {key}")
    return value


def opt_obj(obj: dict[str, Any], key: str, where: str) -> dict[str, Any] | None:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise Refused(f"{where}'s {key} is not an object")
    return cast(dict[str, Any], value)


def check_repository(value: str, what: str) -> str:
    if not is_repository(value):
        raise Refused(f"{what} {value!r} is not in the form owner/repo")
    return value


# -- log -------------------------------------------------------------------------

def _account(value: str, what: str) -> str:
    """A login, or an App's `<slug>[bot]`."""
    if not is_login(value.removesuffix("[bot]")):
        raise Refused(f"{what} {value!r} is not a GitHub login")
    return value


def _date(value: str, what: str) -> str:
    try:
        ok = datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        ok = False
    if not ok:
        raise Refused(f"{what} {value!r} is not a yyyy-mm-dd date")
    return value


def _surface(url: str) -> Literal["github", "linear", "discord"]:
    if url.startswith("https://discord.com/"):
        return "discord"
    if url.startswith("https://linear.app/"):
        return "linear"
    return "github"


def _check_question(question: str) -> str:
    if not question.strip():
        raise Refused("the input holds no question")
    for line in question.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line in CLOSING_HEADINGS:
            raise Refused(f"the question holds the line {line!r}, which would be read as a "
                          "closing section; reword the question and log it again")
    return question


def _drop_re_line(text: str) -> str:
    """The answer without a relay post's last `Re: ` line."""
    lines = text.rstrip().split("\n")
    if lines and _RE_LINE.fullmatch(lines[-1].strip()):
        lines.pop()
    return "\n".join(lines)


@dataclass
class _Plan:
    """What one log call writes."""

    branch: str
    lore_branch: bool
    path: str = ""
    file: QuestionsBranchFile | None = None
    as_inquisitor: bool = False
    taken: bool = False
    sources: list[tuple[str, str | None]] = field(default_factory=lambda: [])


class _Log:
    def __init__(self, args: LogArgs, data: dict[str, Any]) -> None:
        self.args = args
        self.data = data
        self.cfg = config.load()
        self.vis = Visibility()
        self.today = today()
        self._session: tuple[str | None] | None = None
        self._files: list[branches.BranchFile] | None = None
        branch = opt_obj(data, "branch", "the input") or {}
        repo = opt_str(branch, "repository", "branch")
        lore = opt_str(branch, "lore", "branch")
        if (repo is None) == (lore is None):
            raise Refused("branch names neither or both of repository and lore")
        self.branch = check_repository(repo or lore or "", "branch's repository")
        self.lore_branch = lore is not None
        if self.lore_branch and not any(r.repository == self.branch for r in self.cfg.lore):
            raise Refused(f"{self.branch} is no configured lore repository, so no team's lore "
                          "repository serves the question and it is not logged")

    # -- lookups

    def session(self) -> str | None:
        if self._session is None:
            self._session = (github.session_login(self.cfg.login),)
        return self._session[0]

    def service_login(self) -> str:
        login = self.session()
        if login is None:
            raise Refused("no GitHub login configured, or gh is not logged in as it")
        return login

    def files(self) -> list[branches.BranchFile]:
        if self._files is None:
            self._files = read_branch(self.branch)
        return self._files

    def log_file(self, name: str, what: str) -> LogFile:
        path = f"questions/{name}"
        for f in self.files():
            if f.path == path:
                parsed = parse(path, f.content, self.lore_branch)
                if isinstance(parsed, LogFile):
                    return parsed
                raise Refused(f"{what} {name!r} is not a readable question file")
        raise Refused(f"{what} {name!r} is not on the questions branch of {self.branch}")

    def on_branch(self, path: str) -> bool:
        return any(f.path == path for f in self.files())

    # -- planning one log call

    def plan(self) -> _Plan:
        args, data = self.args, self.data
        kind = data.get("kind")
        if kind not in ("question", "answer", "miss", "handled"):
            raise Refused(f"kind {kind!r} is none of question, answer, miss and handled")
        if not args.service:
            if kind == "handled" or "handled" in data or "closes" in data:
                raise Refused("a handled file, or a handled or closes key, is written only "
                              "through the answer service's option")
            if args.hash_only:
                raise Refused("a hash-only miss file is written only through the answer "
                              "service's option")
            if args.asked_from is not None:
                raise Refused("--asked-from is the answer service's, with its option")
        elif kind != "handled" and ("handled" in data or "closes" in data):
            raise Refused("only a handled file holds a handled or closes key")
        if args.hash_only and kind != "miss":
            raise Refused("--hash-only writes a miss file; the input's kind is not miss")
        plan = _Plan(branch=self.branch, lore_branch=self.lore_branch)
        if kind == "handled":
            return self.handled(plan)
        if kind == "miss" and args.hash_only:
            return self.hash_only(plan)
        return self.readable(plan, kind)

    def handled(self, plan: _Plan) -> _Plan:
        closes = req_str(self.data, "closes", "the input")
        self.log_file(closes, "closes")
        handled = _date(opt_str(self.data, "handled", "the input") or self.today, "handled")
        name = log_name(self.today, "handled", random_hex())
        plan.file = HandledFile(name=name, handled=handled, closes=closes)
        plan.path = f"questions/{name}"
        return plan

    def miss_name(self, miss: dict[str, Any]) -> tuple[str, str]:
        name = opt_obj(miss, "name", "miss")
        if name is None:
            raise Refused("miss has no name")
        kind = req_str(name, "kind", "miss's name")
        value = req_str(name, "value", "miss's name")
        if kind in ("github", "linear", "discord"):
            if not self.args.service:
                raise Refused("a miss file is named by a reply's id only through the answer "
                              "service's option")
        elif kind == "file":
            if not value.startswith("questions/"):
                raise Refused("a file miss's name is not a path under questions/")
            self.log_file(value.removeprefix("questions/"), "the miss's file")
        elif kind == "message":
            if not is_asked_in(value):
                raise Refused(f"the miss's message URL {value!r} takes none of the forms given")
        else:
            raise Refused(f"miss name kind {kind!r} is none of github, linear, discord, file "
                          "and message")
        return f"misses/{miss_hash(cast(Any, kind), value)}.md", value

    def hash_only(self, plan: _Plan) -> _Plan:
        miss = opt_obj(self.data, "miss", "the input")
        if miss is None:
            raise Refused("a miss input has no miss")
        plan.path, _ = self.miss_name(miss)
        digest = plan.path.removeprefix("misses/").removesuffix(".md")
        plan.file = HashOnlyMiss(hash=digest)
        plan.as_inquisitor = True
        plan.taken = self.on_branch(plan.path)
        return plan

    def readable(self, plan: _Plan, kind: Literal["question", "answer", "miss"]) -> _Plan:
        args, data = self.args, self.data
        question = _check_question(req_str(data, "question", "the input"))
        asked = _date(opt_str(data, "asked", "the input") or self.today, "asked")
        repository = opt_str(data, "repository", "the input")
        if repository is not None:
            check_repository(repository, "repository")
        if not self.lore_branch:
            if repository is not None and repository != self.branch:
                raise Refused(f"a question about {repository} goes to its own questions branch, "
                              f"not {self.branch}'s")
            repository = self.branch
        asked_in = opt_str(data, "asked_in", "the input")
        if asked_in is not None and not is_asked_in(asked_in):
            raise Refused(f"asked_in {asked_in!r} takes none of the forms given")
        if args.service:
            if args.asked_from is None:
                raise Refused("the answer service passes --asked-from with its option")
            asked_from: str | None = check_repository(args.asked_from, "--asked-from")
        else:
            asked_from = None

        answer_in = opt_obj(data, "answer", "the input")
        miss_in = opt_obj(data, "miss", "the input")
        if kind == "answer" and answer_in is None:
            raise Refused("an answer input has no answer")
        if kind == "miss" and miss_in is None:
            raise Refused("a miss input has no miss")
        if kind != "answer" and answer_in is not None or kind != "miss" and miss_in is not None:
            raise Refused(f"a {kind} input holds another kind's answer or miss")
        if kind == "question":
            if asked_in is None or _surface(asked_in) != "github":
                raise Refused("a question is logged unanswered only when asked in a GitHub post, "
                              "with that post's URL as asked_in; log any other once answered")

        miss_path = ""
        message: str | None = None
        if miss_in is not None:
            miss_path, value = self.miss_name(miss_in)
            if miss_in["name"]["kind"] == "message":
                # The asking message is the thread the question was asked
                # in: part of the record's source. A Linear or Discord one is
                # also the miss file's asked_in, when the input gives none.
                if asked_in is None and _surface(value) != "github":
                    asked_in = value
                message = value
            if miss_in["name"]["kind"] == "file":
                logged = self.log_file(value.removeprefix("questions/"), "the miss's file")
                repository, asked = logged.repository, logged.asked
                asked_from = asked_from or logged.asked_from

        answers: tuple[str, ...] = ()
        link: str | None = None
        if answer_in is not None:
            link = opt_str(answer_in, "answer_link", "answer")
            if link is not None and not is_answer_link(link):
                raise Refused(f"answer_link {link!r} takes none of the forms given")
            if link is not None and _surface(link) != "github" and not args.service:
                raise Refused("a Linear or Discord answer_link is the answer service's, with "
                              "its option")
            answers = self.answers(answer_in, repository)
            if asked_from is None and answers:
                asked_from = min((self.log_file(n, "answers").asked_from or "" for n in answers),
                                 key=self.vis.source_rank)
        if asked_from is None:
            asked_from = current_repository()
            if asked_from is None:
                raise Refused("cannot tell which repository holds the current work, so the file "
                              "would have no asked_from")
        check_repository(asked_from, "asked_from")

        # The record's source: the repository asked from and each thread.
        plan.sources = [(asked_from, asked_from)]
        for url in (asked_in, link, message):
            if url is not None and all(url != what for what, _ in plan.sources):
                plan.sources.append((url, link_repository(url)))
        destination = self.vis.destination_rank(self.branch)
        wider = [what for what, repo in plan.sources if self.vis.source_rank(repo) < destination]
        confirmed = False
        if wider:
            if not args.confirm_visible or kind == "question":
                raise Refused(
                    f"the questions branch of {self.branch} ({self.vis.name(self.branch)}) is "
                    f"more visible than {wider[0]}, where the question was asked or answered; "
                    "it is logged there only once the person answering confirms that")
            confirmed = True
            asked_from = self.branch

        def written(url: str | None) -> str | None:
            """url, or None where the file may not hold it: in a record
            confirmed for a more visible branch, or where url points into
            somewhere more private than the branch (a Linear or Discord
            URL counts as private)."""
            if url is None or confirmed:
                return None
            linked = link_repository(url)
            if linked is None:
                return url if self.vis.of(self.branch) == "private" else None
            return url if destination <= self.vis.source_rank(linked) else None

        if kind == "miss":
            assert miss_in is not None
            if asked_in is not None and _surface(asked_in) == "github":
                asked_in = None
            return self.miss(plan, miss_in, miss_path, question, asked, repository, asked_from,
                             written(asked_in), confirmed)
        name = log_name(self.today, slug(question_text(Question(kind="post", question=question))),
                        random_hex())
        plan.path = f"questions/{name}"
        answer = None
        if answer_in is not None:
            answer = self.answer(answer_in, link, written, answers, repository, plan.path,
                                 confirmed)
        plan.file = LogFile(name=name, asked=asked, question=question, repository=repository,
                            asked_from=asked_from, asked_in=written(asked_in), answer=answer)
        return plan

    def answers(self, answer_in: dict[str, Any], repository: str | None) -> tuple[str, ...]:
        raw = answer_in.get("answers")
        if raw is None:
            return ()
        if not isinstance(raw, list) or not raw:
            raise Refused("answer's answers is not a list of file names")
        names: list[str] = []
        for item in cast(list[Any], raw):
            if not isinstance(item, str):
                raise Refused("answer's answers is not a list of file names")
            named = self.log_file(item, "answers names")
            if named.answer is not None:
                raise Refused(f"answers names {item}, which already holds an answer")
            if named.repository != repository:
                raise Refused(f"answers names {item}, whose repository key differs from this "
                              "file's; files with different repository keys get one answer "
                              "file each")
            if item not in names:
                names.append(item)
        return tuple(names)

    def answer(self, answer_in: dict[str, Any], link: str | None,
               written: Callable[[str | None], str | None], answers: tuple[str, ...],
               repository: str | None, own_path: str, confirmed: bool) -> Answer:
        args = self.args
        authority = answer_in.get("authority")
        if authority not in ("decision", "input"):
            raise Refused("answer's authority is neither decision nor input")
        given_by = _account(req_str(answer_in, "answered_by", "answer"), "answered_by")
        bot = False
        if link is not None and _surface(link) == "github":
            comment = github.comment(link)
            if comment is None:
                raise Refused(f"GitHub does not return the comment {link}, so the answer is not "
                              "logged")
            text = comment.text
            if args.service:
                answered_by = self.service_login()
            else:
                bot = comment.author_type == "Bot" or comment.login.endswith("[bot]")
                answered_by = comment.login + ("[bot]" if bot and not comment.login.endswith("[bot]")
                                               else "")
        else:
            text = req_str(answer_in, "text", "answer")
            answered_by = self.service_login() if args.service else given_by
        if confirmed:
            text = _drop_re_line(text)
        concerns = repository or self.branch
        decision = authority == "decision" and not bot
        if decision and link is None and not args.service:
            decision = answered_by == self.session()
        if decision:
            decision = github.write_access(concerns, answered_by) is True
        recorded_in = opt_str(answer_in, "recorded_in", "answer")
        if recorded_in is not None and not is_recorded_in(recorded_in):
            raise Refused(f"recorded_in {recorded_in!r} is neither a link nor a path from the "
                          "repository's root")
        kept_link = written(link)
        if recorded_in is None:
            recorded_in = kept_link or own_path
        elif recorded_in.startswith("https://") and written(recorded_in) is None:
            # written gives None for a URL that would leak here. Such a
            # recorded_in, a comment's URL or an issue's, is replaced by
            # own_path: the file being written stands as the answer's
            # record. The https:// test tells a URL from a path from the
            # repository's root, which can never start that way.
            recorded_in = own_path
        rephrased = opt_str(answer_in, "rephrased", "answer")
        discussion = opt_str(answer_in, "discussion", "answer")
        if (rephrased is None) != (discussion is None):
            raise Refused("answer gives one of rephrased and discussion without the other")
        return Answer(answered_by=answered_by, authority="decision" if decision else "input",
                      recorded_in=recorded_in, text=text, answer_link=kept_link,
                      answers=answers, rephrased=rephrased, discussion=discussion)

    def miss(self, plan: _Plan, miss_in: dict[str, Any], path: str, question: str, asked: str,
             repository: str | None, asked_from: str, asked_in: str | None,
             confirmed: bool) -> _Plan:
        flt = miss_in.get("filter")
        if flt not in ("1", "2", "3", "4"):
            raise Refused("miss's filter is not \"1\", \"2\", \"3\" or \"4\"")
        said = req_str(miss_in, "said", "miss")
        if self.args.service:
            said_by: str | None = self.service_login()
        else:
            given = opt_str(miss_in, "said_by", "miss")
            said_by = _account(given, "said_by") if given is not None else None
        asked_by = opt_str(miss_in, "asked_by", "miss")
        if asked_by is not None:
            _account(asked_by, "asked_by")
        plan.path = path
        plan.file = MissFile(hash=path.removeprefix("misses/").removesuffix(".md"), asked=asked,
                             filter=flt, said=said,
                             question=question, said_by=said_by,
                             asked_by=None if confirmed else asked_by,
                             repository=repository, asked_from=asked_from, asked_in=asked_in)
        plan.taken = self.on_branch(path)
        return plan


def _result(status: Literal["pushed", "pending", "taken", "failed"], path: str | None,
            why: str | None = None) -> LogResult:
    result: LogResult = {"version": VERSION, "status": status, "path": path}
    if why is not None:
        result["why"] = why
    return result


def field_text(file: object) -> str:
    """Every string a questions-branch file holds, unescaped, one per line.
    The credential scan reads these, not the rendered file, which writes a
    line break before a token as `\\n`: the letter n then hides the token
    from the patterns, which match only at the start of a word."""
    if isinstance(file, str):
        return file
    if isinstance(file, tuple):
        return "\n".join(field_text(v) for v in cast(tuple[object, ...], file))
    if dataclasses.is_dataclass(file):
        return "\n".join(field_text(getattr(file, f.name)) for f in dataclasses.fields(file))
    return ""


def push(repository: str, path: str, file: QuestionsBranchFile,
         as_inquisitor: bool, service: bool) -> LogResult:
    """Push one file, printing nothing, and give its LogResult."""
    try:
        content = render(file)
    except ValueError as e:
        raise Refused(f"the file cannot be written as UTF-8: {e}") from e
    if matches_credentials(field_text(file)) or matches_credentials(content):
        raise Refused(f"{path} would hold a string matching the credential patterns, so it is "
                      "not written")
    pushed = push_to_branch(repository, path, content, as_inquisitor, service)
    if pushed.pushed:
        return _result("pushed", path)
    if pushed.taken:
        return _result("taken", path)
    if pushed.pending and not service:
        return _result("pending", path, pushed.why or "the push failed")
    return _result("failed", None, pushed.why or "the push failed")


def run(args: LogArgs) -> int:
    """Plan one file and push it, printing a contracts.LogResult. A miss
    file whose name is taken prints "taken" and pushes nothing."""
    if igor_run() is not None:
        raise NotBuilt("P5", "log in an Igor's run, which waits on what igor issue #247 lists "
                       "(tasks.md task 0.12)")
    log = _Log(args, load_json(args.input))
    plan = log.plan()
    assert plan.file is not None
    if plan.taken:
        print_json(_result("taken", plan.path))
        return 0
    print_json(push(plan.branch, plan.path, plan.file, plan.as_inquisitor,
                    args.service))
    return 0


# -- misses ----------------------------------------------------------------------

def _miss_out(branch: str, path: str, miss: MissFile) -> MissOut:
    out: MissOut = {"branch": branch, "path": path, "filter": miss.filter, "said": miss.said,
                    "asked": miss.asked, "question": miss.question}
    for key in ("said_by", "asked_by", "repository", "asked_from", "asked_in"):
        value = getattr(miss, key)
        if value is not None:
            out[key] = value
    return out


def run_misses(args: MissesArgs) -> int:
    """List the miss files, only those against --filter when given: those on
    the questions branch of --repository and of --lore, or of the current
    work's repository when neither is given."""
    if args.filter is not None and args.filter not in ("1", "2", "3", "4"):
        raise Refused("--filter is 1, 2, 3 or 4")
    cfg = config.load()
    wanted: list[tuple[str, bool]] = []
    if args.repository is not None:
        wanted.append((check_repository(args.repository, "--repository"), False))
    if args.lore is not None:
        wanted.append((check_repository(args.lore, "--lore"), True))
    if not wanted:
        here = current_repository()
        if here is None:
            raise Refused("name --repository or --lore: the command runs in no repository")
        wanted.append((here, any(r.repository == here for r in cfg.lore)))
    result: MissesResult = {"version": VERSION, "misses": [], "hash_only": {}, "unreadable": [],
                            "not_read": []}
    for repository, lore_branch in wanted:
        files = branch_files(repository)
        if files is None:
            result["not_read"].append(repository)
            continue
        for f in files:
            if not f.path.startswith("misses/"):
                continue
            parsed = parse(f.path, f.content, lore_branch)
            if isinstance(parsed, HashOnlyMiss):
                result["hash_only"][repository] = result["hash_only"].get(repository, 0) + 1
            elif isinstance(parsed, MissFile):
                if args.filter is None or parsed.filter == args.filter:
                    result["misses"].append(_miss_out(repository, f.path, parsed))
            else:
                result["unreadable"].append(f"{repository}:{f.path}")
    print_json(result)
    return 0

