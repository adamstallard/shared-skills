"""Reading an input file only when it is private, and writing records at
mode 0600 in a private directory (inquisitor spec: *The two calls' files and
records stay private*; *The log command takes its input in a private
file*; *The search command takes its question as the first call does*).

Owned by P2. Standard library only.
"""

from pathlib import Path

from common import NotBuilt


def read_private(path: str) -> str:
    """The text of the file at path, or of standard input when path is '-'. Refuses (common.Refused,
    saying to write the file with mode 0600 in a private directory such as
    one `mktemp -d` makes) a file inside a git working tree, one its group
    or others can read, or one whose directory they can read.

    TODO(P2): build it."""
    raise NotBuilt("P2", "read_private")


def write_private(path: Path, text: str) -> None:
    """Write text at mode 0600, creating its directory at mode 0700.

    TODO(P2): build it."""
    raise NotBuilt("P2", "write_private")
