"""What every module of the inquisitor script shares: the JSON version, the
error a command that is not built raises, and the paths the specs fix.

Standard library only.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

# Every JSON object a command prints, or the answer service's core answers,
# carries "version": VERSION. branch-search, miss-check and file-answer are a
# contract with igor (tasks 2.3b to 2.3d), so changing their shape means a new
# version and igor's agreement.
VERSION = 1

# Exit codes. 0: done. 1: refused, the message says why. 2: usage error
# (argparse). 3: the command, or the part of it asked for, is not built.
EXIT_REFUSED = 1
EXIT_NOT_BUILT = 3


class NotBuilt(Exception):
    """Raised by a stub. part names the build part that owns it, as the
    implementation plan numbers them: P1 to P9, with P8 split into P8a to
    P8d."""

    def __init__(self, part: str, what: str) -> None:
        super().__init__(f"{what} is not built (owned by {part})")
        self.part = part
        self.what = what


class Refused(Exception):
    """A command refusing its input. Every command raises it before writing
    anything; the CLI prints the message to stderr as is and exits
    EXIT_REFUSED."""


def config_path() -> Path:
    """`~/.config/shared-skills/inquisitor.json` (inquisitor spec, Purpose)."""
    return Path.home() / ".config" / "shared-skills" / "inquisitor.json"


def state_home() -> Path:
    """`${XDG_STATE_HOME:-$HOME/.local/state}`."""
    value = os.environ.get("XDG_STATE_HOME")
    return Path(value) if value else Path.home() / ".local" / "state"


def verdicts_dir() -> Path:
    """Where the second call keeps verdict records (inquisitor spec: *The two
    calls' files and records stay private*)."""
    return state_home() / "inquisitor" / "verdicts"


def service_state_dir() -> Path:
    """The answer service's state folder (answer-service spec: *The state
    folder is under the XDG state home*)."""
    return state_home() / "inquisitor" / "answer-service"


def igor_run() -> str | None:
    """`worker` or `igor` when IGOR_RUN has exactly that value, else None
    (inquisitor spec: *The script tells an Igor's run by IGOR_RUN*)."""
    value = os.environ.get("IGOR_RUN")
    return value if value in ("worker", "igor") else None


def print_json(obj: Any) -> None:
    """Print one JSON object on one line to stdout."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=False) + "\n")


def refuse(message: str) -> NoReturn:
    raise Refused(message)
