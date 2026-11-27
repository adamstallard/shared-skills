"""The inquisitor's configuration, `~/.config/shared-skills/inquisitor.json`.

The script reads `login` and `lore`; the answer service also reads and saves
`answer_service` (answer-service spec: *The answer service's configuration
is a section of the inquisitor's configuration*), keeping every key it does
not write.

load() is owned by P2; save_answer_service() by P8a. Standard library only.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from common import NotBuilt


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


def load() -> Config:
    """The configuration, or an empty Config when the file is missing.

    TODO(P2): build it."""
    raise NotBuilt("P2", "config.load")


def save_answer_service(section: AnswerServiceConfig) -> None:
    """Write `answer_service`, keeping every other key, and never write a
    token or key into the file.

    TODO(P8a): build it (task 6.2)."""
    raise NotBuilt("P8a", "config.save_answer_service")
