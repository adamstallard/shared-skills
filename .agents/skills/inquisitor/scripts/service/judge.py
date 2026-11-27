"""The model's judgements of incoming messages: record_verdict's checks,
the two turns, filter 1 through `search`, and the automatic replies the
code posts by itself (tasks 6.6, 6.10; answer-service spec: *The model's
judgements reach the service's code only through record_verdict*).

Owned by P8b; automatic posts go out through relay.py (P8c).
Standard library only.
"""

from common import NotBuilt
from service.protocol import TurnEndRequest, TurnEndResponse, VerdictRequest, VerdictResponse


def verdict(request: VerdictRequest) -> VerdictResponse:
    """Accept or refuse one record_verdict call. TODO(P8b): build it."""
    raise NotBuilt("P8b", "judge.verdict")


def turn_end(request: TurnEndRequest) -> TurnEndResponse:
    """TODO(P8b): build it."""
    raise NotBuilt("P8b", "judge.turn-end")
