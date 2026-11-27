"""The credential patterns: a closed list of token shapes (inquisitor spec:
*The credential patterns are a closed list of token shapes*). The second
call, both hooks and the log command scan with this one function, over raw
markdown with link targets included (*The credential scan reads raw
markdown*).

Owned by P2. Standard library only.
"""

from common import NotBuilt


def matches_credentials(text: str) -> bool:
    """Whether text holds any of the credential patterns.

    TODO(P2): build it."""
    raise NotBuilt("P2", "matches_credentials")
