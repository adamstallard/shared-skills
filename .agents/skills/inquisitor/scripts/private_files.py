"""Reading an input file only when it is private, and writing records at
mode 0600 in a private directory (inquisitor spec: *The two calls' files and
records stay private*; *The log command takes its input in a private
file*; *The search command takes its question as the first call does*).

Owned by build part P2 of the implementation plan. Standard library only.
"""

import os
import stat
import sys
import tempfile
from pathlib import Path

from common import Refused

HOW = ("write it with mode 0600 in a private directory outside any git working tree, "
       "such as one `mktemp -d` makes")


def _in_git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in path.parents)


def read_private(path: str) -> str:
    """The text of the file at path, or of standard input when path is '-'.
    Refuses (common.Refused, saying to write the file with mode 0600 in a
    private directory such as one `mktemp -d` makes) a file inside a git
    working tree, one its group or others can read, or one whose directory
    they can read. A symbolic link is judged by the file it points to."""
    if path == "-":
        return sys.stdin.read()
    real = Path(os.path.realpath(path))
    try:
        mode = real.stat().st_mode
        dir_mode = real.parent.stat().st_mode
    except OSError as e:
        raise Refused(f"cannot read {path}: {e.strerror}") from e
    if not stat.S_ISREG(mode):
        raise Refused(f"{path} is not a regular file; {HOW}")
    if mode & 0o044:
        raise Refused(f"{path} can be read by its group or others; {HOW}")
    if dir_mode & 0o044:
        raise Refused(f"the directory holding {path} can be read by its group or others; {HOW}")
    if _in_git_tree(real):
        raise Refused(f"{path} is inside a git working tree; {HOW}")
    try:
        return real.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Refused(f"cannot read {path} as UTF-8 text: {e}") from e


def _make_private_dir(directory: Path) -> None:
    """Create directory and any missing parent at mode 0700, and make
    directory itself 0700 if it already exists. Another writer creating one
    of them at the same moment is no error."""
    missing: list[Path] = []
    d = directory
    while not d.exists():
        missing.append(d)
        d = d.parent
    for d in reversed(missing):
        try:
            d.mkdir(mode=0o700)
        except FileExistsError:
            pass
        os.chmod(d, 0o700)
    os.chmod(directory, 0o700)


def write_private(path: Path, text: str) -> None:
    """Write text at mode 0600 in a directory at mode 0700, creating the
    directory and any missing parent. The file is replaced whole, never left half
    written."""
    _make_private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
