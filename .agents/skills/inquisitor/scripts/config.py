"""The inquisitor's configuration, `~/.config/shared-skills/inquisitor.json`.

The script reads `login` and `lore`; the answer service also reads and saves
`answer_service` (answer-service spec: *The answer service's configuration
is a section of the inquisitor's configuration*), keeping every key it does
not write.

load() is owned by P2; save_answer_service() by P8a. Standard library only.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from common import NotBuilt, Refused, config_path
from formats import is_login, is_repository


@dataclass(frozen=True)
class LoreRepo:
    """One entry of `lore`: the local clone's path, and the owners or
    repositories (`owner/repo`) whose questions it holds lore for. repository is the clone's
    origin as `owner/repo`, read from the clone, or None when unreadable."""

    path: str
    owners: tuple[str, ...] = ()
    repos: tuple[str, ...] = ()
    repository: str | None = None


class Channel(TypedDict, total=False):
    """A Linear team or Discord channel subscription: `id`, and `repos` once
    setup has guessed them."""

    id: str
    repos: list[str]


class SurfaceConfig(TypedDict, total=False):
    """One surface's object in `answer_service`. relay names the surface's
    relay identity, the bot that posts for the person, as its skill takes
    it with `--identity`. On GitHub, subscriptions
    are `owner/repo` or `owner` strings; on Linear and Discord, Channel
    objects. `user` is the person's Discord user id, on Discord only."""

    relay: str
    subscriptions: list[Any]
    user: str


AnswerServiceConfig = dict[Literal["github", "linear", "discord"], SurfaceConfig]


@dataclass(frozen=True)
class Config:
    """The keys the script reads. raw is the whole file as parsed, so a save
    keeps keys nobody here writes."""

    login: str | None = None
    lore: tuple[LoreRepo, ...] = ()
    answer_service: AnswerServiceConfig = field(default_factory=lambda: {})
    raw: dict[str, Any] = field(default_factory=lambda: {})


_ORIGIN = re.compile(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)"
                     r"([^/\s]+/[^/\s]+?)(?:\.git)?/?")


def origin_repository(clone: Path) -> str | None:
    """The clone's `origin` remote as `owner/repo`, when it is a github.com
    URL in https, ssh:// or git@ form naming a well-formed repository;
    otherwise None, including when git fails."""
    try:
        done = subprocess.run(["git", "-C", str(clone), "remote", "get-url", "origin"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _ORIGIN.fullmatch(done.stdout.strip()) if done.returncode == 0 else None
    return m.group(1) if m and is_repository(m.group(1)) else None


def _strings(value: Any, check: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v for v in cast(list[Any], value) if isinstance(v, str) and check(v))


def load() -> Config:
    """The configuration, or an empty Config when the file is missing.
    Refuses (common.Refused) a file it cannot read, that is not JSON, or
    that holds no JSON object. A `login` off GitHub's login syntax is read
    as None; a `lore` entry without a string `path` is
    skipped, and owners and repositories off their syntax are dropped."""
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    except OSError as e:
        raise Refused(f"cannot read {path}: {e.strerror}") from e
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise Refused(f"{path} is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise Refused(f"{path} does not hold a JSON object")
    raw = cast(dict[str, Any], parsed)
    login = raw.get("login")
    lore: list[LoreRepo] = []
    entries: Any = raw.get("lore")
    for entry in cast(list[Any], entries) if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        e = cast(dict[str, Any], entry)
        clone = e.get("path")
        if not isinstance(clone, str) or not clone:
            continue
        clone = str(Path(clone).expanduser())
        lore.append(LoreRepo(path=clone, owners=_strings(e.get("owners"), is_login),
                             repos=_strings(e.get("repos"), is_repository),
                             repository=origin_repository(Path(clone))))
    service: Any = raw.get("answer_service")
    return Config(login=login if isinstance(login, str) and is_login(login) else None,
                  lore=tuple(lore),
                  answer_service=cast(AnswerServiceConfig, service) if isinstance(service, dict) else {},
                  raw=raw)


def save_answer_service(section: AnswerServiceConfig) -> None:
    """Write `answer_service`, keeping every other key, and never write a
    token or key into the file.

    TODO(P8a): build it (task 6.2)."""
    raise NotBuilt("P8a", "config.save_answer_service")
