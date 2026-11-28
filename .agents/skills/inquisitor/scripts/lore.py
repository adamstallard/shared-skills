"""`lore`: open a lore pull request adding a new entry, a promotion from a
questions branch, or a lesson from misses (the inquisitor spec's
requirements from *An answer that generalizes is proposed as lore* to *A
proposed lore entry's path, fields and id follow igor's rules*).

The entry's path, id rule and required fields are copied from igor's lore
store at IGOR_COMMIT (`src/entry.ts`, `openspec/specs/lore-store/spec.md`);
test_lore.py holds that commit's rules and checks this module against them.

Owned by build part P5 of the implementation plan (tasks 2.7, 2.8). Standard library only.
"""

import base64
import datetime
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

import config
from common import VERSION, NotBuilt, Refused, igor_run, print_json
from credentials import matches_credentials
from formats import LogFile, MissFile, parse
from log_command import (Visibility, check_repository, file_rank, load_json,
                         read_branch)

# The igor commit whose lore store the constants from here to REJECTED_DIR
# copy. ID_PATTERN is igor's id rule (`ID_PATTERN` in igor's src/entry.ts).
IGOR_COMMIT = "7d969cd6ab7820e143c2802a9ead44b3a91332b0"
ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
SCOPE_PATTERN = r"^(global|role:[a-z0-9][a-z0-9-]*|project:[a-z0-9][a-z0-9-]*)$"
STATUSES = ("provisional", "active", "deprecated")
REQUIRED_FIELDS = ("id", "claim", "scope", "status", "conditions", "provenance", "supersedes")
DERIVED_FIELDS = ("support",)
ENTRIES_DIR = "entries"
# Where a lore repository keeps rejected candidates (inquisitor spec: *A
# rejected candidate is not proposed again*).
REJECTED_DIR = "rejected"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class LoreArgs:
    """input: a private contracts.LoreInput file. confirm_visible: the
    person confirmed the entry for a lore repository more visible than its
    source."""

    input: str
    confirm_visible: bool = False


class LoreResult(TypedDict):
    """What `lore` prints: the pull request's URL and the entry's path."""

    version: int
    url: str
    path: str


# -- igor's entry rules ------------------------------------------------------------

def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _date_ok(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def entry_errors(fm: dict[str, Any]) -> list[str]:
    """Every way fm breaks igor's frontmatter schema, as `field: problem`,
    following validateFrontmatter in igor's src/entry.ts."""
    errors: list[str] = []
    for name in DERIVED_FIELDS:
        if name in fm:
            errors.append(f"{name}: is derived from provenance and must not be stored")
    if not _nonempty(fm.get("id")):
        errors.append("id: is required")
    elif not re.fullmatch(ID_PATTERN, cast(str, fm["id"])):
        errors.append("id: must be a kebab-case slug")
    if not _nonempty(fm.get("claim")):
        errors.append("claim: is required")
    scope = fm.get("scope")
    if not _nonempty(scope):
        errors.append("scope: is required")
    elif not re.fullmatch(SCOPE_PATTERN, cast(str, scope)):
        errors.append("scope: must be global, role:<name>, or project:<name>")
    status = fm.get("status")
    if not _nonempty(status):
        errors.append("status: is required")
    elif status not in STATUSES:
        errors.append(f"status: must be one of {', '.join(STATUSES)}")
    conditions = fm.get("conditions")
    if not isinstance(conditions, dict):
        errors.append("conditions: must be an object")
    else:
        cond = cast(dict[str, Any], conditions)
        if not _nonempty(cond.get("prose")):
            errors.append("conditions.prose: is required and must be non-empty")
        paths = cond.get("paths")
        # igor treats only a missing key as absent; a null fails its check.
        if "paths" in cond and (not isinstance(paths, list) or not paths
                                  or not all(_nonempty(p) for p in cast(list[Any], paths))):
            errors.append("conditions.paths: must be a non-empty array of non-empty strings")
    provenance = fm.get("provenance")
    if not isinstance(provenance, list) or not provenance:
        errors.append("provenance: must be a non-empty array")
    else:
        for i, item in enumerate(cast(list[Any], provenance)):
            if not isinstance(item, dict):
                errors.append(f"provenance[{i}]: must be an object")
                continue
            p = cast(dict[str, Any], item)
            if not _nonempty(p.get("author")):
                errors.append(f"provenance[{i}].author: is required")
            if not _date_ok(p.get("at")):
                errors.append(f"provenance[{i}].at: must be an ISO date (YYYY-MM-DD)")
            if "url" in p and not _nonempty(p["url"]):
                errors.append(f"provenance[{i}].url: must be a non-empty string when present")
    reviewed = fm.get("reviewed")
    if "reviewed" not in fm:
        if status == "active":
            errors.append("reviewed: is required when status is active")
    elif not isinstance(reviewed, dict):
        errors.append("reviewed: must be an object")
    else:
        r = cast(dict[str, Any], reviewed)
        if not _nonempty(r.get("by")):
            errors.append("reviewed.by: is required")
        if not _date_ok(r.get("at")):
            errors.append("reviewed.at: must be an ISO date (YYYY-MM-DD)")
    supersedes = fm.get("supersedes")
    if not isinstance(supersedes, list):
        errors.append("supersedes: must be an array (empty is fine)")
    elif not all(_nonempty(s) for s in cast(list[Any], supersedes)):
        errors.append("supersedes: must contain only entry ids")
    return errors


def _json(value: Any) -> str:
    """value as one line of JSON, a dict or list as a JSON flow collection,
    which YAML reads back the same. Non-ASCII characters are escaped, and
    so is DEL, which YAML 1.2 allows nowhere raw in a document. Raises
    ValueError for NaN or Infinity, which JSON has no form for."""
    return json.dumps(value, ensure_ascii=True, allow_nan=False).replace("\x7f", "\\u007f")


# yaml, which igor reads entries with, refuses an implicit key over 1024
# characters.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,1023}")
# Plain names YAML reads as something other than a string.
_YAML_WORDS = {"null", "true", "false", "yes", "no", "on", "off", "y", "n"}


def _keys(value: Any) -> list[str]:
    """Every key in value's nested dicts and lists, as strings. run()
    refuses any that is not a plain name."""
    if isinstance(value, dict):
        d = cast(dict[Any, Any], value)
        return [k for key, v in d.items() for k in (str(key), *_keys(v))]
    if isinstance(value, list):
        return [k for item in cast(list[Any], value) for k in _keys(item)]
    return []


def _strings(value: Any) -> list[str]:
    """Every string in value, keys included, through nested dicts and
    lists."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        d = cast(dict[Any, Any], value)
        return [s for k, v in d.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, list):
        return [s for item in cast(list[Any], value) for s in _strings(item)]
    return []


def render_entry(fm: dict[str, Any], body: str) -> str:
    """The entry file: frontmatter, igor's required fields first, each a
    plain-name key and a JSON-encoded value; then the body. Raises
    ValueError for NaN or Infinity."""
    ordered = {k: fm[k] for k in (*REQUIRED_FIELDS, "reviewed") if k in fm}
    ordered.update({k: v for k, v in fm.items() if k not in ordered})
    text = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return "\n".join(["---", *(f"{k}: {_json(v)}" for k, v in ordered.items()), "---",
                      text]) + "\n"


# -- the command ----------------------------------------------------------------------

def run_gh(args: list[str]) -> tuple[int, str, str]:
    """Run `gh`; its exit code, stdout and stderr. Tests replace it."""
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)
    return done.returncode, done.stdout, done.stderr


def _source_rank(kind: str, source: dict[str, Any], vis: Visibility) -> tuple[int, str]:
    """The source's visibility rank and a name for it."""
    if kind == "new":
        repository = source.get("repository")
        if not isinstance(repository, str):
            raise Refused("a new entry's source names no repository")
        check_repository(repository, "source's repository")
        return vis.source_rank(repository), repository
    refs: list[Any]
    if kind == "promotion":
        refs = [source.get("file")]
    else:
        raw = source.get("misses")
        refs = cast(list[Any], raw) if isinstance(raw, list) and raw else []
        if not refs:
            raise Refused("a lesson's source names no miss files")
    cfg = config.load()
    ranks: list[tuple[int, str]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise Refused("a source file is not {repository, path}")
        r = cast(dict[str, Any], ref)
        repository, path = r.get("repository"), r.get("path")
        if not isinstance(repository, str) or not isinstance(path, str):
            raise Refused("a source file is not {repository, path}")
        check_repository(repository, "source file's repository")
        if kind == "lesson" and not path.startswith("misses/"):
            raise Refused(f"{path} is not a miss file")
        files = read_branch(repository)
        found = next((f for f in files if f.path == path), None)
        if found is None:
            raise Refused(f"{path} is not on the questions branch of {repository}")
        lore_branch = any(c.repository == repository for c in cfg.lore)
        parsed = parse(path, found.content, lore_branch)
        if kind == "promotion" and not (isinstance(parsed, LogFile) and parsed.answer):
            raise Refused(f"{path} holds no answer to promote")
        if kind == "lesson" and not isinstance(parsed, MissFile):
            raise Refused(f"{path} is not a readable miss file")
        ranks.append((file_rank(repository, parsed, vis), f"{repository}:{path}"))
    return min(ranks)


def _gh_json(args: list[str], payload: dict[str, object] | None = None) -> tuple[Any, str]:
    """Run `gh api` with args, sending payload as its JSON input. Gives the
    parsed answer ({} when empty, None on failure) and gh's error text."""
    with tempfile.TemporaryDirectory() as tmp:
        if payload is not None:
            sent = Path(tmp) / "input.json"
            sent.write_text(json.dumps(payload), encoding="utf-8")
            args = [*args, "--input", str(sent)]
        code, out, err = run_gh(["api", *args])
    if code != 0:
        return None, err.strip() or f"gh exited {code}"
    try:
        return json.loads(out) if out.strip() else {}, ""
    except json.JSONDecodeError:
        return None, "gh's answer is not JSON"


def _field(obj: Any, *keys: str) -> Any:
    """obj[keys[0]][keys[1]]..., or None where a level is not an object."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = cast(dict[str, Any], obj).get(key)
    return obj


def _exists(lore: str, path: str, ref: str) -> bool:
    """Whether path is on ref of lore, refusing when GitHub cannot tell."""
    found, err = _gh_json([f"repos/{lore}/contents/{path}?ref={ref}"])
    if found is not None:
        return True
    if "404" in err or "Not Found" in err:
        return False
    raise Refused(f"cannot tell whether {lore} holds {path}: {err}")


def _open_pull_request(lore: str, entry_id: str, content: str, title: str, body: str) -> str:
    """Create the branch, the entry's commit and the pull request through
    GitHub's API. With no local clone, no git hook runs that could change
    or block the commit."""
    if not any(entry.repository == lore for entry in config.load().lore):
        raise Refused(f"{lore} is no configured lore repository, so the lesson is told, not "
                      "proposed")
    repo, err = _gh_json([f"repos/{lore}"])
    base = _field(repo, "default_branch")
    if not isinstance(base, str):
        raise Refused(f"cannot read {lore}'s default branch: {err}")
    ref, err = _gh_json([f"repos/{lore}/git/ref/heads/{base}"])
    sha = _field(ref, "object", "sha")
    if not isinstance(sha, str):
        raise Refused(f"cannot read the head of {lore}'s {base}: {err}")
    for directory, why in ((ENTRIES_DIR, "an entry there holds it; pick another id"),
                           (REJECTED_DIR, "a rejected candidate holds it, so it is not "
                                          "proposed again")):
        if _exists(lore, f"{directory}/{entry_id}.md", sha):
            raise Refused(f"the id {entry_id} is taken: {why}")
    path = f"{ENTRIES_DIR}/{entry_id}.md"
    branch = f"inquisitor/lore-{entry_id}"
    made, err = _gh_json(["-X", "POST", f"repos/{lore}/git/refs"],
                         {"ref": f"refs/heads/{branch}", "sha": sha})
    if made is None and "already exists" in err:
        # A branch left by a proposal that failed part-way or was closed
        # unmerged (deferred) is reused. One whose pull request is open is
        # still proposed, and one whose pull request was merged was
        # accepted, so neither is proposed again.
        owner = lore.split("/")[0]
        pulls, err = _gh_json([f"repos/{lore}/pulls?head={owner}:{branch}&state=all&per_page=100"])
        if not isinstance(pulls, list):
            raise Refused(f"cannot read {lore}'s pull requests from {branch}: {err}")
        for pull in cast(list[Any], pulls):
            if _field(pull, "state") == "open":
                raise Refused(f"the entry is already proposed: {_field(pull, 'html_url')}")
        for pull in cast(list[Any], pulls):
            if _field(pull, "merged_at"):
                raise Refused(f"the entry was accepted in {_field(pull, 'html_url')}, so it is "
                              "not proposed again")
        made, err = _gh_json(["-X", "PATCH", f"repos/{lore}/git/refs/heads/{branch}"],
                             {"sha": sha, "force": True})
    if made is None:
        raise Refused(f"cannot create the branch {branch} on {lore}: {err}")
    put, err = _gh_json(["-X", "PUT", f"repos/{lore}/contents/{path}"],
                        {"message": f"lore: propose {path}", "branch": branch,
                         "content": base64.b64encode(content.encode("utf-8")).decode()})
    if put is None:
        raise Refused(f"cannot commit {path} to {branch} on {lore}: {err}")
    pull, err = _gh_json(["-X", "POST", f"repos/{lore}/pulls"],
                         {"title": title, "head": branch, "base": base, "body": body})
    url = _field(pull, "html_url")
    if not isinstance(url, str):
        raise Refused(f"cannot open the pull request on {lore}: {err}")
    return url


def _body(kind: str, fm: dict[str, Any]) -> str:
    what = {"new": "a new entry", "promotion": "an answer promoted from a questions branch",
            "lesson": "a lesson drawn from misses"}[kind]
    conditions = cast(dict[str, Any], fm["conditions"])
    lines = [f"Proposes {what} as a `provisional` lore entry.", "",
             "To review: deleting the file rejects the entry for good, editing it amends it, "
             "merging accepts it, and closing without merging defers it.", "",
             f"- Claim: {fm['claim']}", f"- Conditions: {conditions['prose']}"]
    for item in cast(list[dict[str, Any]], fm["provenance"]):
        source = f" ({item['url']})" if item.get("url") else ""
        lines.append(f"- Provenance: {item['author']}, {item['at']}{source}")
    return "\n".join(lines) + "\n"


def run(args: LoreArgs) -> int:
    """Open the pull request. During an Igor's run it raises NotBuilt: the
    entry goes into the run's report once igor PR #216 gives its form."""
    if igor_run() is not None:
        raise NotBuilt("P5", "lore in an Igor's run, which writes the entry into the run's "
                       "report once igor PR #216 gives its form (tasks.md task 0.12)")
    data = load_json(args.input)
    kind = data.get("kind")
    if kind not in ("new", "promotion", "lesson"):
        raise Refused(f"kind {kind!r} is none of new, promotion and lesson")
    lore = data.get("lore")
    entry_id = data.get("id")
    fm_raw = data.get("frontmatter")
    body = data.get("body")
    source = data.get("source")
    if not isinstance(lore, str) or not isinstance(entry_id, str) or not isinstance(body, str):
        raise Refused("the input lacks lore, id or body")
    check_repository(lore, "lore")
    if re.fullmatch(ID_PATTERN, entry_id) is None:
        raise Refused(f"the id {entry_id!r} breaks igor's id rule, {ID_PATTERN}")
    if not isinstance(fm_raw, dict) or not isinstance(source, dict):
        raise Refused("the input's frontmatter or source is not an object")
    fm = dict(cast(dict[str, Any], fm_raw))
    if fm.setdefault("id", entry_id) != entry_id:
        raise Refused("the frontmatter's id is not the input's id")
    if fm.setdefault("status", "provisional") != "provisional":
        raise Refused("a proposed entry's status is provisional")
    fm.setdefault("supersedes", [])
    bad_key = next((k for k in _keys(fm)
                    if not _KEY.fullmatch(k) or k.lower() in _YAML_WORDS), None)
    if bad_key is not None:
        raise Refused(f"the frontmatter key {bad_key!r} is not a plain name")
    if any("\0" in text for text in (*_strings(fm), body)):
        # GitHub takes no NUL in the pull request's title, built from the
        # claim, and a NUL in any other field or the body is no readable
        # text either.
        raise Refused("the entry holds a control character, NUL")
    errors = entry_errors(fm)
    if errors:
        raise Refused("the entry breaks igor's lore store schema: " + "; ".join(errors))
    vis = Visibility()
    rank, name = _source_rank(kind, cast(dict[str, Any], source), vis)
    if vis.destination_rank(lore) > rank:
        if not args.confirm_visible:
            raise Refused(f"{lore} ({vis.name(lore)}) is more visible than {name}, the entry's "
                          "source; it is proposed there only once the person confirms the "
                          "generalized entry")
        if any(cast(dict[str, Any], p).get("url") for p in cast(list[Any], fm["provenance"])):
            raise Refused(f"an entry for {lore}, more visible than its source, holds no "
                          "provenance link into that source")
    try:
        content = render_entry(fm, body)
    except ValueError as e:
        raise Refused(f"the entry holds a number JSON cannot write: {e}") from e
    title, pr_body = f"LORE: {fm['claim']}", _body(kind, fm)
    # The scan reads the decoded values, not render_entry's output, which
    # writes a line break before a token as `\n`: the letter n then hides
    # the token from the patterns.
    if any(matches_credentials(text) for text in (*_strings(fm), body, title, pr_body)):
        raise Refused("the entry holds a string matching the credential patterns")
    try:
        for text in (*_strings(fm), body, title, pr_body):
            text.encode("utf-8")
    except UnicodeEncodeError as e:
        raise Refused(f"the entry cannot be written as UTF-8: {e}") from e
    url = _open_pull_request(lore, entry_id, content, title, pr_body)
    result: LoreResult = {"version": VERSION, "url": url, "path": f"{ENTRIES_DIR}/{entry_id}.md"}
    print_json(result)
    return 0
