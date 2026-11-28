"""The two calls that prove the four filters ran (`vet`), and the verdict
records that the picker hook and the post hook read (inquisitor spec: *Two calls prove the filters ran*; *The
second call records all its verdicts or none*; *The two calls' files and
records stay private*; *Some questions are recorded by hash only*).

The first call keeps, under the token it issues, each question's hash and
what the second call needs to check and record a verdict: its kind, what it
concerns, its files, its category, and for a picker the hash of its first
option's label. It keeps no question's text. Token files sit at mode 0600 in
`<state home>/inquisitor/tokens/`; verdict records, one file per hash
holding its latest verdict, in common.verdicts_dir().

tasks.md's tasks 2.1 and 2.2. Standard library only.
"""

import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, cast

import config
import github
import search
from common import VERSION, Refused, igor_run, print_json, state_home, verdicts_dir
from contracts import (Category, Concerns, QuestionIn, SearchResult, SecondCallLine, VerdictName,
                       VerdictRecord)
from credentials import matches_credentials
from formats import is_repository
from private_files import read_private, write_private
from qtext import (NOT_RECORDED_PREFIX, PERSON_REQUIRED_FORMAT, RECORDED_PREFIX, RELATED_PREFIX,
                   FoundQuestion, Question, find_questions, question_hash, question_text,
                   reduce_markup)

# A verdict, and the token that leads to it, last 2 hours (inquisitor spec:
# *The second call records all its verdicts or none*; *The two calls' files
# and records stay private*).
LIFE = 2 * 60 * 60

CATEGORIES: tuple[Category, ...] = ("vulnerability", "secret", "personal")
VERDICTS: tuple[VerdictName, ...] = ("answered", "deferred", "decided", "ask", "not asked")
_KINDS = ("picker", "post", "text")
_HASH = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[0-9a-f]{32}")
_SKILL = re.compile(r"[a-z0-9-]+")
_URL = re.compile(r"https?://\S+")

FILTERS = """\
Run the four filters, in order, on each question below. Ask only a question none of them stops.
1. Already answered: an earlier answer with authority settles it. Cite it and act on it. Verdict
   `answered`, field `citation`.
2. Deferrable: the current work does not need the answer. List it as not done, and file an issue
   under a deferral label if it outlives the work. Verdict `deferred`, field `where`.
3. Not a real question: fewer than two options have merit, or it is rhetorical. Take the option
   you recommend, or rewrite it as a statement. Verdict `decided`, field `where`.
4. Cheap to reverse: two or more options have merit, but switching later is cheap. Choose one.
   Verdict `decided`, field `where`.
Otherwise the verdict is `ask`, with fields `recommended` (for a picker, its first option's label)
and `changes` (what each other answer would change), and optionally `related`, the URL of a related
earlier decision among its filter 1 hits, and `requires`, the skill that requires a person to
decide it, which skips filters 2 and 4.
A question another installed skill requires a person to decide skips filters 2 and 4.
A question marked as found only by reading code and HTML as text may instead get the verdict
`not asked`, with no field, when the post does not ask it: it is code, or text GitHub hides.
Then run the second call, the verdicts in a private file or on standard input:
  inquisitor.py vet --pass <token> --verdicts <file|->
  {"version": 1, "verdicts": [{"question": 1, "verdict": "ask", "field": {...}}]}"""


class _TokenQuestion(TypedDict):
    """plain_only: true for a question in a post found only when code and
    HTML are read as text (the plain reading), not when they are hidden as
    GitHub hides them (the hiding reading). The second call accepts `not asked`
    only for such a question, and only when it has no category."""

    hash: str
    kind: str
    concerns: Concerns
    files: list[str]
    category: str | None
    first_option: str | None
    plain_only: NotRequired[bool]


class _Token(TypedDict):
    version: int
    issued: float
    questions: list[_TokenQuestion]


@dataclass(frozen=True)
class VetArgs:
    """The first call takes questions (a QuestionsInput file, or `-` for
    standard input) or post (a post's body, a markdown file), with
    repository or lore naming what the post's questions concern. The second
    call takes pass_token and verdicts (a VerdictsInput file, or `-`)."""

    questions: str | None = None
    post: str | None = None
    repository: str | None = None
    lore: str | None = None
    pass_token: str | None = None
    verdicts: str | None = None


def tokens_dir() -> Path:
    return state_home() / "inquisitor" / "tokens"


def run(args: VetArgs) -> int:
    """First call: print the four filters' instructions and filter 1's
    results for each question, issue a token, record nothing. Second call:
    check and record every verdict or none, printing, for each `ask`
    verdict, a record line if it is a picker question and a person-required
    line if it names a requiring skill (contracts.SecondCallLine)."""
    first = args.questions is not None or args.post is not None
    second = args.pass_token is not None or args.verdicts is not None
    if first == second or (args.questions is not None and args.post is not None):
        raise Refused("vet takes --questions or --post (the first call), or --pass and "
                      "--verdicts (the second call)")
    if second:
        if args.pass_token is None or args.verdicts is None:
            raise Refused("the second call takes both --pass and --verdicts")
        return _second_call(args.pass_token, args.verdicts)
    if args.questions is not None:
        if args.repository is not None or args.lore is not None:
            raise Refused("--repository and --lore go with --post; a questions file gives each "
                          "question's concerns")
        return _first_call(_read_questions(args.questions), [])
    assert args.post is not None
    found, questions = _read_post(args.post, args.repository, args.lore)
    return _first_call(questions, found)


# -- the first call -------------------------------------------------------------

def _parse_json(text: str, what: str) -> dict[str, Any]:
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise Refused(f"{what} is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise Refused(f"{what} does not hold a JSON object")
    obj = cast(dict[str, Any], parsed)
    if obj.get("version") != VERSION:
        raise Refused(f'{what} must hold "version": {VERSION}')
    return obj


def _concerns(value: Any, n: int) -> Concerns:
    if not isinstance(value, dict):
        raise Refused(f"question {n}: concerns must be an object")
    raw = cast(dict[str, Any], value)
    out: Concerns = {}
    for key in raw:
        if key not in ("repository", "lore", "asked_from"):
            raise Refused(f"question {n}: concerns holds an unknown key {key!r}")
        v = raw[key]
        if not isinstance(v, str) or not is_repository(v):
            raise Refused(f"question {n}: concerns' {key} must be owner/repo")
    if "repository" in raw and "lore" in raw:
        raise Refused(f"question {n}: a question concerns a repository or a collective's lore "
                      "repository, not both")
    if "repository" in raw:
        out["repository"] = raw["repository"]
    if "lore" in raw:
        out["lore"] = raw["lore"]
    if "asked_from" in raw:
        out["asked_from"] = raw["asked_from"]
    return out


def _strings(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast(list[Any], value)):
        raise Refused(f"{what} must be a list of strings")
    return cast(list[str], value)


def _read_questions(path: str) -> list[QuestionIn]:
    """The questions input's questions, checked. It refuses a question with
    a category unless path is `-`, standard input."""
    obj = _parse_json(read_private(path), "the questions input")
    items: Any = obj.get("questions")
    if not isinstance(items, list) or not items:
        raise Refused('the questions input must hold a non-empty "questions" list')
    out: list[QuestionIn] = []
    for n, raw in enumerate(cast(list[Any], items), 1):
        if not isinstance(raw, dict):
            raise Refused(f"question {n} must be an object")
        q = cast(dict[str, Any], raw)
        kind = q.get("kind")
        text = q.get("question")
        if kind not in _KINDS:
            raise Refused(f"question {n}: kind must be picker, post or text")
        if not isinstance(text, str) or not text.strip():
            raise Refused(f"question {n}: question must be non-empty text")
        item: QuestionIn = {"kind": kind, "question": text, "concerns": _concerns(q.get("concerns", {}), n)}
        if kind == "picker":
            options = _strings(q.get("options"), f"question {n}: a picker question's options")
            if not options:
                raise Refused(f"question {n}: a picker question needs its options")
            item["options"] = options
        elif "options" in q:
            raise Refused(f"question {n}: only a picker question has options")
        if "files" in q:
            item["files"] = _strings(q["files"], f"question {n}: files")
        if "category" in q:
            category = q["category"]
            if category not in CATEGORIES:
                raise Refused(f"question {n}: the category must be vulnerability, secret or "
                              f"personal, not {category!r}")
            if path != "-":
                raise Refused(f"question {n} has a category: pass it, and every other question of "
                              "the same picker call, on standard input (--questions -), never in a "
                              "file")
            item["category"] = category
        out.append(item)
    for n, item in enumerate(out, 1):
        if _holds_credential(item):
            raise Refused(f"question {n} holds a string shaped like a credential; give a question "
                          "that needs one the category secret, and write the credential into no "
                          "question")
    return out


def _holds_credential(item: QuestionIn) -> bool:
    parts = [item["question"], *item.get("options", []), *item.get("files", [])]
    return any(matches_credentials(p) for p in parts)


def _working_repository() -> str | None:
    """The repository holding the current work: the working tree's origin."""
    return config.origin_repository(Path.cwd())


def _concerns_line(found: FoundQuestion) -> Concerns | None:
    for line in found.lines:
        words = line.split()
        if len(words) == 2 and words[0] == "Concerns:" and is_repository(words[1]):
            return {"repository": words[1]}
        if len(words) == 3 and words[:2] == ["Concerns:", "lore"] and is_repository(words[2]):
            return {"lore": words[2]}
    return None


def _read_post(path: str, repository: str | None,
               lore: str | None) -> tuple[list[FoundQuestion], list[QuestionIn]]:
    """The questions find_questions finds in the post, and each as the first
    call takes it. What a question concerns comes from its own
    `Concerns: owner/repo` or `Concerns: lore owner/repo` line, else from
    --repository or --lore, else from the working tree's origin; with none
    of these it concerns nothing."""
    for value, flag in ((repository, "--repository"), (lore, "--lore")):
        if value is not None and not is_repository(value):
            raise Refused(f"{flag} must be owner/repo")
    if repository is not None and lore is not None:
        raise Refused("give --repository or --lore, not both")
    body = read_private(path)
    found = find_questions(body, in_code=True)
    default: Concerns = ({"repository": repository} if repository else {"lore": lore} if lore
                         else {})
    if not default:
        here = _working_repository()
        if here:
            default = {"repository": here}
    questions: list[QuestionIn] = []
    for n, f in enumerate(found, 1):
        raw = "\n".join((f.raw, *f.lines))
        if matches_credentials(raw):
            where = f"item {f.item}" if f.item is not None else "a sentence outside any list"
            raise Refused(f"question {n} of the post ({where}) holds a string shaped like a "
                          "credential, link targets included; take it out of the post")
        concerns = _concerns_line(f) or dict(default)
        questions.append({"kind": "post", "question": f.question.question,
                          "concerns": cast(Concerns, concerns)})
    # Each line starting `Related:` or `@`, after any indent, is scanned,
    # wherever it is (inquisitor spec: *The credential scan reads raw
    # markdown*). One that follows a statement rather than a question
    # belongs to no question, so the scan above misses it. The test is the
    # line's start, not qtext.line_kind, which reads a line holding a
    # credential as neither a Related nor a tag line.
    for line in body.splitlines():
        if line.strip().startswith((RELATED_PREFIX.strip(), "@")) and matches_credentials(line):
            raise Refused("a Related or tag line of the post holds a string shaped like a "
                          "credential; take it out of the post")
    return found, questions


def _plain_only(found: FoundQuestion | None) -> bool:
    """Whether `not asked` is open to the question: whether find_questions
    set in_code on it. in_code marks a question only the plain reading
    found, the reading that takes code and HTML as text (inquisitor spec:
    *Questions in a post are found by two readings*). qtext's _backstop
    also sets it on a question made from a `?` that ends no question of
    either reading, and in_code holds no way to tell the two kinds apart,
    so `not asked` is open to a backstop question too, though the spec
    (*Only a question the hiding reading misses may be not asked*) opens it
    only to the first kind."""
    return found is not None and found.in_code


def _first_option(label: str) -> str:
    return question_hash(" ".join(reduce_markup(label).split()))


def _describe(n: int, q: QuestionIn, digest: str, found: FoundQuestion | None) -> str:
    concerns = q["concerns"]
    about = (f"concerns {concerns['repository']}" if "repository" in concerns
             else f"concerns lore {concerns['lore']}" if "lore" in concerns
             else "about one person's way of working")
    head = f"Question {n} ({q['kind']}, {about}"
    if found is not None and found.item is not None:
        head += f", item {found.item}"
        if found.deferred:
            head += ", listed as deferred: it needs a `deferred` verdict"
    if _plain_only(found):
        head += ", found only reading code and HTML as text: `not asked` is open to it"
    if "category" in q:
        return f"{head}, category {q['category']}): hash {digest}"
    text = question_text(Question(q["kind"], q["question"], tuple(q.get("options", []))))
    return f"{head}): {text.splitlines()[0] if text else ''}"


def _hit_lines(result: SearchResult) -> list[str]:
    lines: list[str] = []
    if not result["hits"]:
        lines.append("  Filter 1 found nothing.")
    for hit in result["hits"]:
        label = hit["label"] if "why" not in hit else f"{hit['label']}: {hit['why']}"
        repo = f"{hit['repository']} " if hit["repository"] else ""
        lines.append(f"  [{label}] {repo}{hit['where']} ({hit['source']}, {hit['terms']} terms)")
        quote = " ".join(hit["quote"].split())
        if quote:
            lines.append(f"    \"{quote}\"")
    if result["left_out"]:
        lines.append(f"  {result['left_out']} more hits left out by the cap of 20.")
    for item in result["not_searched"]:
        lines.append(f"  Not searched: {item}")
    for clone in result["clones"]:
        lines.append(f"  Clone {clone['path']} last fetched {clone['fetched'] or 'at an unknown time'}")
    return lines


def _first_call(questions: list[QuestionIn], found: list[FoundQuestion]) -> int:
    if not questions:
        print("The post holds no question; there is nothing to vet and no token.")
        print_json({"version": VERSION, "token": None, "questions": []})
        return 0
    here = _working_repository()
    kept: list[_TokenQuestion] = []
    shown: list[dict[str, Any]] = []
    out = [FILTERS, ""]
    if igor_run():
        out.append(f"Running as in an Igor's run, because IGOR_RUN is {igor_run()}.")
        out.append("")
    for n, q in enumerate(questions, 1):
        concerns = q["concerns"]
        if "asked_from" not in concerns and here and ("repository" in concerns or "lore" in concerns):
            concerns["asked_from"] = here
        options = tuple(q.get("options", []))
        found_q = found[n - 1] if found else None
        digest = question_hash(question_text(found_q.question if found_q
                                             else Question(q["kind"], q["question"], options)))
        result = search.filter1(q, service=False)
        out.append(_describe(n, q, digest, found_q))
        out.extend(_hit_lines(result))
        out.append("")
        kept.append({"hash": digest, "kind": q["kind"], "concerns": concerns,
                     "files": q.get("files", []), "category": q.get("category"),
                     "first_option": _first_option(options[0]) if options else None,
                     "plain_only": _plain_only(found_q)})
        entry: dict[str, Any] = {"question": n, "hash": digest, "kind": q["kind"], "search": result}
        if found_q is not None:
            entry["item"] = found_q.item
            entry["deferred"] = found_q.deferred
            entry["plain_only"] = _plain_only(found_q)
        shown.append(entry)
    token = secrets.token_hex(16)
    _clean_tokens()
    write_private(tokens_dir() / f"{token}.json",
                  json.dumps(_Token(version=VERSION, issued=time.time(), questions=kept)))
    out.append(f"Token: {token} (valid for 2 hours)")
    print("\n".join(out))
    print_json({"version": VERSION, "token": token, "questions": shown})
    return 0


def _clean_tokens() -> None:
    """Delete token files issued more than 2 hours ago, spent or not."""
    try:
        entries = list(tokens_dir().iterdir())
    except OSError:
        return
    now = time.time()
    for path in entries:
        if not re.fullmatch(r"[0-9a-f]{32}\.json(?:\.spent)?", path.name):
            continue
        try:
            if now - path.stat().st_mtime > LIFE:
                path.unlink()
        except OSError:
            pass


# -- the second call --------------------------------------------------------------

def _load_token(token: str) -> tuple[Path, _Token]:
    if not _TOKEN.fullmatch(token):
        raise Refused("that is not a token the first call issues; run the first call again")
    path = tokens_dir() / f"{token}.json"
    if (tokens_dir() / f"{token}.json.spent").exists():
        raise Refused("that token was spent by an earlier second call; run the first call again")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused("unknown or expired token: run the first call again") from None
    except (OSError, json.JSONDecodeError) as e:
        raise Refused(f"cannot read the token's file: {e}; run the first call again") from e
    if not isinstance(data, dict):
        raise Refused("the token's file is damaged; run the first call again")
    loaded = cast(_Token, data)
    if time.time() - loaded["issued"] > LIFE:
        raise Refused("the token was issued more than 2 hours ago: run the first call again")
    return path, loaded


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


_FIELDS: dict[str, tuple[str, ...]] = {
    "answered": ("citation",), "deferred": ("where",), "decided": ("where",),
    "ask": ("recommended", "changes"), "not asked": (),
}


# The token's keys that _record copies into a verdict record, beside the
# question's hash. Questions sharing a text share one record, so they must
# agree on these. first_option stays out because a picker's first option
# is never recorded (*The two calls' files and records stay private*).
# plain_only stays out because it is never recorded either, and because
# comparing it would refuse the same text in running text and in code.
_RECORDED = ("kind", "concerns", "files", "category")


def _check_verdicts(obj: dict[str, Any], token: _Token, from_file: bool) -> list[tuple[int, dict[str, Any]]]:
    items: Any = obj.get("verdicts")
    if not isinstance(items, list):
        raise Refused('the verdicts input must hold a "verdicts" list')
    count = len(token["questions"])
    seen: dict[int, dict[str, Any]] = {}
    for raw in cast(list[Any], items):
        if not isinstance(raw, dict):
            raise Refused("each verdict must be an object")
        v = cast(dict[str, Any], raw)
        n = v.get("question")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= count:
            raise Refused(f"verdict for question {n!r}: the token's first call took questions 1 "
                          f"to {count} only")
        if n in seen:
            raise Refused(f"question {n} has two verdicts")
        verdict = v.get("verdict")
        if verdict not in VERDICTS:
            raise Refused(f"question {n}: the verdict must be answered, deferred, decided, ask or "
                          "not asked")
        question = token["questions"][n - 1]
        if verdict == "not asked":
            if not question.get("plain_only") or question["category"] is not None:
                raise Refused(f"question {n}: only a question in a post that the first call found "
                              "only by reading code and HTML as text may be `not asked`")
            if set(v) - {"question", "verdict"}:
                raise Refused(f"question {n}: `not asked` carries no field, related or requires")
            seen[n] = v
            continue
        field: Any = v.get("field")
        if not isinstance(field, dict):
            raise Refused(f"question {n}: the verdict {verdict} needs its field")
        f = cast(dict[str, Any], field)
        names = _FIELDS[verdict]
        if set(f) != set(names) or not all(_text(f[k]) for k in names):
            raise Refused(f"question {n}: the verdict {verdict} needs its field, "
                          + " and ".join(f"`{k}`" for k in names) + ", and nothing else")
        for key in ("related", "requires"):
            if key in v and verdict != "ask":
                raise Refused(f"question {n}: only an `ask` names {key}")
        related = v.get("related")
        if related is not None and (not isinstance(related, str) or not _URL.fullmatch(related)):
            raise Refused(f"question {n}: related must be one URL with no spaces")
        requires = v.get("requires")
        if requires is not None and (not isinstance(requires, str) or not _SKILL.fullmatch(requires)):
            raise Refused(f"question {n}: requires must name a skill in lowercase letters, digits "
                          f"and -, not {requires!r}")
        if any(matches_credentials(s) for s in [*map(str, f.values()), str(related or "")]):
            raise Refused(f"question {n}: the verdict holds a string shaped like a credential; "
                          "write the credential into no verdict field")
        if question["category"] is not None and from_file:
            raise Refused(f"question {n} has a category: give the verdicts on standard input "
                          "(--verdicts -), never in a file")
        if (verdict == "ask" and question["kind"] == "picker" and question["first_option"]
                and _first_option(f["recommended"]) != question["first_option"]):
            raise Refused(f"question {n}: the recommended answer must be the picker's first "
                          "option; put that option first and run the first call again")
        seen[n] = v
    # A text keeps one record, so questions sharing a text must agree on
    # everything recorded: the whole verdict entry (verdict, field, related,
    # requires), and the token's _RECORDED keys.
    by_hash: dict[str, dict[str, Any]] = {}
    for n, v in sorted(seen.items()):
        question = token["questions"][n - 1]
        same = {"verdict": {k: x for k, x in v.items() if k != "question"},
                "question": {k: question[k] for k in _RECORDED}}
        if by_hash.setdefault(question["hash"], same) != same:
            raise Refused(f"question {n} has the same text as an earlier question but another "
                          "verdict, concerns, files or category; one text keeps one record, so "
                          "reword one of them")
    missing = [n for n in range(1, count + 1) if n not in seen]
    if missing:
        raise Refused("questions left without a verdict: " + ", ".join(map(str, missing))
                      + "; give each a verdict, or run the first call again without it")
    return sorted(seen.items())


def _team_lore(cfg: config.Config, asked_from: str | None) -> str | None:
    """The team's lore repository for a collective's question asked from
    asked_from: the first configured lore repository naming that repository,
    else the first naming its owner, else None (inquisitor spec: *The team's
    lore repository is the most specific one that serves*)."""
    if not asked_from:
        return None
    owner = asked_from.split("/")[0]
    for repo in cfg.lore:
        if asked_from in repo.repos:
            return repo.repository
    for repo in cfg.lore:
        if owner in repo.owners:
            return repo.repository
    return None


def record_line(question: _TokenQuestion, cfg: config.Config) -> str:
    """The record line of a question asked in the session (inquisitor spec:
    *A question asked in the session shows where its answer will be
    recorded*): the first reason not to record that applies, in the order
    its scenario *Not recorded gives a listed reason* lists them, else where
    the record goes."""
    concerns = question["concerns"]
    if "repository" not in concerns and "lore" not in concerns:
        return NOT_RECORDED_PREFIX + "about your way of working"
    if question["category"] == "vulnerability":
        return NOT_RECORDED_PREFIX + "only a security advisory may hold it"
    if question["category"] is not None:
        return NOT_RECORDED_PREFIX + "it has a category"
    asked_from = concerns.get("asked_from")
    branch = concerns.get("repository") or _team_lore(cfg, asked_from)
    login = github.session_login(cfg.login)
    if branch is not None and login is not None and github.write_access(branch, login) is not True:
        return NOT_RECORDED_PREFIX + "no push access to its questions branch"
    if branch is None:
        return NOT_RECORDED_PREFIX + "no team's lore repository serves it"
    if login is None:
        return NOT_RECORDED_PREFIX + "no GitHub login configured"
    to = github.visibility(branch) or "public"
    line = f"{RECORDED_PREFIX}{branch} questions branch ({to})"
    if asked_from and asked_from != branch:
        source = github.visibility(asked_from) or "private"
        if github.more_visible(to, source):
            line += f", more visible than {asked_from} ({source}), where this was asked"
    return line


def _record(question: _TokenQuestion, v: dict[str, Any], now: float) -> VerdictRecord:
    verdict = cast(VerdictName, v["verdict"])
    record: VerdictRecord = {"version": VERSION, "hash": question["hash"], "verdict": verdict,
                             "time": now}
    if verdict == "not asked":
        return record
    if question["category"] is not None:
        record["category"] = cast(Category, question["category"])
        return record
    kind = cast(Literal["picker", "post", "text"], question["kind"])
    field = dict(cast(dict[str, str], v["field"]))
    if verdict == "ask" and kind == "picker":
        field.pop("recommended", None)
    record["kind"] = kind
    record["field"] = field
    if "related" in v:
        record["related"] = v["related"]
    if "requires" in v:
        record["requires"] = v["requires"]
    record["concerns"] = question["concerns"]
    if question["files"]:
        record["files"] = question["files"]
    return record


def _keep_identities(records: list[VerdictRecord]) -> None:
    """For each new record whose verdict is `ask`, copy in the github-app
    identity of the old record holding the same hash. The `tag` command
    writes that identity when it adds a tag line to an App's post, and
    while a record holds it, the post may go out only as that App
    (inquisitor spec: *A tag made for an App's post blocks a plain gh
    post*). Vetting the post again as `ask` keeps the tag line, so it keeps
    the identity; only a new run of `tag` changes it. Any other verdict
    puts no tag line in the post, and a question with a category is never
    tagged, being recorded by hash only, so those new records get no
    identity. When the old records cannot be read, this refuses; the
    second call calls it before spending its token, so it records nothing
    and the token stays usable."""
    hashes = {r["hash"] for r in records}
    old = read_records(hashes)
    if old is None:
        raise Refused("cannot read the verdict records, so a tag's recorded identity could be "
                      "lost; nothing is recorded")
    for record in records:
        previous = old.get(record["hash"])
        identity = previous.get("identity") if previous is not None else None
        if identity is not None and "category" not in record and record["verdict"] == "ask":
            record["identity"] = identity


def _second_call(token: str, verdicts_path: str) -> int:
    path, loaded = _load_token(token)
    obj = _parse_json(read_private(verdicts_path), "the verdicts input")
    checked = _check_verdicts(obj, loaded, verdicts_path != "-")
    now = time.time()
    records = [(loaded["questions"][n - 1], v, _record(loaded["questions"][n - 1], v, now))
               for n, v in checked]
    _keep_identities([record for _, _, record in records])
    cfg = config.load() if any(v["verdict"] == "ask" and q["kind"] == "picker"
                               for q, v, _ in records) else config.Config()
    lines: list[SecondCallLine] = []
    out: list[str] = []
    for (n, v), (question, _, _) in zip(checked, records):
        out.append(f"Question {n}: {v['verdict']} recorded.")
        if v["verdict"] != "ask":
            continue
        line: SecondCallLine = {"question": n, "hash": question["hash"]}
        if question["kind"] == "picker":
            line["record_line"] = record_line(question, cfg)
            out.append(f"  Put this line last in the question, exactly: {line['record_line']}")
        if "requires" in v:
            line["person_required_line"] = PERSON_REQUIRED_FORMAT.format(skill=v["requires"])
            out.append("  Put this line after the question (and any related-decision line), "
                       f"exactly: {line['person_required_line']}")
        lines.append(line)
    spent = path.with_name(path.name + ".spent")
    try:
        os.rename(path, spent)
    except FileNotFoundError:
        raise Refused("that token was spent by an earlier second call; run the first call "
                      "again") from None
    # Every record is written beside its place first and moved there only
    # once all are written, so a failed write leaves no record changed.
    # Questions sharing a text agree on their record (_check_verdicts), so
    # each text gets one record.
    unique = {record["hash"]: record for _, _, record in records}
    pending = [(verdicts_dir() / f".pending-{token}-{digest}", record)
               for digest, record in unique.items()]
    try:
        for temp, record in pending:
            write_private(temp, json.dumps(record))
    except BaseException:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)
        os.rename(spent, path)
        raise
    for temp, record in pending:
        os.replace(temp, verdicts_dir() / f"{record['hash']}.json")
    print("\n".join(out))
    print_json({"version": VERSION, "lines": lines})
    return 0


# -- the records ---------------------------------------------------------------------

def read_records(hashes: set[str]) -> dict[str, VerdictRecord] | None:
    """The latest record for each hash asked for, as {} when the records
    directory is missing. Any record over 2 hours old, the life of a
    verdict, is deleted, whichever hash it holds; no younger record and no
    other file is. None when the directory cannot be listed, a record asked
    for cannot be read, or an old record cannot be deleted. Both hooks and
    `tag` call this."""
    directory = verdicts_dir()
    try:
        entries = list(directory.iterdir())
    except FileNotFoundError:
        return {}
    except OSError:
        return None
    now = time.time()
    found: dict[str, VerdictRecord] = {}
    for path in entries:
        if not (path.suffix == ".json" and _HASH.fullmatch(path.stem)):
            continue
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            stamp: Any = cast(dict[str, Any], data)["time"] if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError, KeyError, UnicodeDecodeError):
            if path.stem in hashes:
                return None
            continue
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
            if path.stem in hashes:
                return None
            continue
        if now - stamp > LIFE:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return None
            continue
        if path.stem in hashes:
            found[path.stem] = cast(VerdictRecord, data)
    return found
