"""The state folder, the lock, the question on screen, discussion records,
closed questions and pending answers (answer-service spec: *Local state is
per machine, in the state folder*; *One answer service runs on each
machine*; *Reopening shows the question last on screen*; *A question with
a category leaves no readable record on disk*).

Owned by P8a (task 6.5). Standard library only.
"""

from common import NotBuilt
from service.protocol import (ContextRequest, ContextResponse, DiscussionRequest, DoneResponse, OpenRequest,
                              OpenResponse, PendingResponse, RefreshResponse, ReopenRequest,
                              ScreenRequest, SessionRequest)


def check_lock(session_id: str) -> bool:
    """Whether the lock names this session; every command but open calls
    this before acting. TODO(P8a): build it."""
    raise NotBuilt("P8a", "state.check_lock")


def open_service(request: OpenRequest) -> OpenResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "open")


def refresh(request: SessionRequest) -> RefreshResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "refresh")


def close(request: SessionRequest) -> DoneResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "close")


def append_discussion(request: DiscussionRequest) -> DoneResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "discussion.append")


def context(request: ContextRequest) -> ContextResponse:
    """The discussion's context (task 6.6): the question and its thread as
    quoted data, and the session's instructions: explain trade-offs without
    choosing, and the model may read and search files.
    TODO(P8a): build it."""
    raise NotBuilt("P8a", "context")


def set_screen(request: ScreenRequest) -> DoneResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "screen.set")


def pending(request: SessionRequest) -> PendingResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "pending.list")


def reopen(request: ReopenRequest) -> DoneResponse:
    """TODO(P8a): build it."""
    raise NotBuilt("P8a", "reopen")
