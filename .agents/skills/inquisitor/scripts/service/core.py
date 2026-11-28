"""`inquisitor.py service`: read one protocol.Request on standard input,
answer one protocol.Response on standard output.

Owned by P0. Standard library only.
"""

import json
import sys
from collections.abc import Callable
from typing import Any, cast

from common import VERSION, NotBuilt, Refused
from service import judge, relay, setup, sources, state

Handler = Callable[[Any], Any]

HANDLERS: dict[str, Handler] = {
    "open": state.open_service,
    "refresh": state.refresh,
    "close": state.close,
    "discussion.append": state.append_discussion,
    "context": state.context,
    "screen.set": state.set_screen,
    "pending.list": state.pending,
    "reopen": state.reopen,
    "setup.status": setup.status,
    "setup.save": setup.save,
    "setup.guess-repos": setup.guess_repos,
    "setup.create-lore": setup.create_lore,
    "poll": sources.poll,
    "judge.verdict": judge.verdict,
    "judge.turn-end": judge.turn_end,
    "preview": relay.preview,
    "post": relay.post,
}


def error(message: str) -> dict[str, object]:
    return {"version": VERSION, "ok": False, "error": message}


def answer(text: str) -> dict[str, object]:
    """The response to one request's text."""
    try:
        request = json.loads(text)
    except ValueError:
        return error("the request is not JSON")
    if not isinstance(request, dict):
        return error("the request is not a JSON object")
    request = cast(dict[str, Any], request)
    command = request.get("command")
    handler = HANDLERS.get(command) if isinstance(command, str) else None
    if handler is None:
        return error(f"unknown command: {command!r}")
    try:
        return cast(dict[str, object], handler(request))
    except NotBuilt as e:
        return error(str(e))
    except Refused as e:
        return error(str(e))


def main() -> int:
    sys.stdout.write(json.dumps(answer(sys.stdin.read()), ensure_ascii=False) + "\n")
    return 0
