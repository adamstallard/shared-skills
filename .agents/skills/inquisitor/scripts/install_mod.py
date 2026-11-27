"""`install-mod` and `uninstall-mod` (answer-service spec: *The script
installs the answer mod*).

Owned by P9 (task 6.6a). Standard library only.
"""

from common import NotBuilt


def install() -> int:
    """Link ~/.claude/skills/inquisitor-answer-mod to the skill's
    answer-mod/ folder and ~/.local/bin/answer to its `answer` launcher.
    Where anything else is at either path, leave it unchanged and say so.

    TODO(P9): build it."""
    raise NotBuilt("P9", "install-mod")


def uninstall() -> int:
    """Remove only those two links.

    TODO(P9): build it."""
    raise NotBuilt("P9", "uninstall-mod")
