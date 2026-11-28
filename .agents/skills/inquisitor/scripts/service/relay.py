"""Previews and relay posts: the four reserved prefixes, the `Re: ` line,
editing in place, reading the thread before each post, deleting an
automatic post when another relay post was posted first, pending answers, and the records
each post pushes through the `log` and `cite` commands (tasks 6.4, 6.6).

Owned by P8c. Standard library only.
"""

from common import NotBuilt
from service.protocol import PostRequest, PostResponse, PreviewRequest, PreviewResponse

RESERVED_PREFIXES = ("User says: ", "User asks: ", "Recorded answer: ", "Inquisitor: ")


def preview(request: PreviewRequest) -> PreviewResponse:
    """TODO(P8c): build it."""
    raise NotBuilt("P8c", "preview")


def post(request: PostRequest) -> PostResponse:
    """TODO(P8c): build it."""
    raise NotBuilt("P8c", "post")
