"""`install-mod` and `uninstall-mod` (answer-service spec: *The script
installs the answer mod*).

`install-mod` makes two links: `~/.claude/skills/inquisitor-answer-mod`,
where Claude Code loads mods from, points to the skill's `answer-mod/`
folder, and `~/.local/bin/answer` points to that folder's `answer`
launcher. Anything else at either path is left as it is, and the command
says so. `uninstall-mod` removes only those two links.

Standard library only.
"""

import os
from pathlib import Path

from common import EXIT_REFUSED

MOD = Path(__file__).resolve().parent.parent / "answer-mod"
LAUNCHER = MOD / "answer"


def _links() -> list[tuple[Path, Path, str]]:
    """Each link: where it goes, what it points to, and its name in messages."""
    home = Path.home()
    return [
        (home / ".claude" / "skills" / "inquisitor-answer-mod", MOD, "the answer mod"),
        (home / ".local" / "bin" / "answer", LAUNCHER, "answer"),
    ]


def _is_ours(path: Path, target: Path) -> bool:
    """Whether `path` is a link that resolves to `target`, absolute or relative."""
    if not path.is_symlink():
        return False
    pointed = Path(os.readlink(path))
    if not pointed.is_absolute():
        pointed = path.parent / pointed
    return os.path.realpath(pointed) == os.path.realpath(target)


def _on_path(folder: Path) -> bool:
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and os.path.realpath(os.path.expanduser(entry)) == os.path.realpath(folder):
            return True
    return False


def install() -> int:
    """Makes both links where nothing else is; leaves anything else alone,
    saying so; says when ~/.local/bin is not on PATH."""
    status = 0
    for path, target, name in _links():
        if _is_ours(path, target):
            print(f"{name} is already installed: {path} links to {target}.")
            continue
        if path.is_symlink() or path.exists():
            print(f"{name} was not installed: {path} is something else, left as it is. Move it away and run install-mod again.")
            status = EXIT_REFUSED
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        print(f"Linked {path} to {target}.")
    bin_dir = Path.home() / ".local" / "bin"
    if not _on_path(bin_dir):
        print(f"{bin_dir} is not on PATH: add it to run answer by name, or run {bin_dir / 'answer'}.")
    return status


def uninstall() -> int:
    """Removes each path that is a link resolving to its target; anything else
    at either path stays."""
    for path, target, name in _links():
        if _is_ours(path, target):
            path.unlink()
            print(f"Removed {path}.")
        elif path.is_symlink() or path.exists():
            print(f"Left {path} as it is: it is not the link install-mod makes for {name}.")
    return 0
