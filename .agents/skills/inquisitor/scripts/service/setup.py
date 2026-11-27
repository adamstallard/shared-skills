"""Setup: the person's login, relay checks, subscriptions, the Linear key in
the keychain, each channel's guessed repos, the questions-branch push check
and suggested rule, and the optional lore repository (task 6.2).

Owned by P8a. Standard library only.
"""

from common import NotBuilt
from service.protocol import (GuessResponse, SessionRequest, SetupCreateLoreRequest,
                              SetupGuessRequest, SetupSaveRequest, SetupStatusResponse,
                              DoneResponse)


def status(request: SessionRequest) -> SetupStatusResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "setup.status")


def save(request: SetupSaveRequest) -> SetupStatusResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "setup.save")


def guess_repos(request: SetupGuessRequest) -> GuessResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "setup.guess-repos")


def create_lore(request: SetupCreateLoreRequest) -> DoneResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "setup.create-lore")
