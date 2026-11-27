"""The credential patterns: a closed list of token shapes (inquisitor spec:
*The credential patterns are a closed list of token shapes*). The script's
`vet` command, the picker hook, the post hook and the log command all scan
with this one function, over raw markdown with link targets included (*The
credential scan reads raw markdown*).

Each prefix pattern (GitHub, Anthropic, Slack, Linear) counts only at the
start of a word and with at least one token character after it, so prose
naming a prefix, such as `ghp_` in backticks, is no token. The Discord
pattern's bounds are the spec's; task 0.33 found that they match
discord-bot's real token, whose parts are 26, 6 and 38 characters.

Owned by build part P2 of the implementation plan. Standard library only.
"""

import re

_START = r"(?<![A-Za-z0-9_-])"
_B64 = r"[A-Za-z0-9_-]"
CREDENTIAL_PATTERN = re.compile("|".join([
    # A private key's -----BEGIN line: PEM, OpenSSH, encrypted and PGP keys.
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----",
    # GitHub tokens.
    _START + r"(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]",
    _START + r"github_pat_[A-Za-z0-9_]",
    # Anthropic API keys.
    _START + r"sk-ant-[A-Za-z0-9_-]",
    # AWS access key IDs.
    r"(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}(?![A-Za-z0-9])",
    # Slack tokens: xox, a letter, then -.
    _START + r"xox[A-Za-z]-[A-Za-z0-9-]",
    # Linear API keys.
    _START + r"lin_(?:api|oauth)_[A-Za-z0-9]",
    # Discord bot tokens: three base64 parts of 24 or more, exactly 6, and
    # 27 or more characters, separated by dots.
    _START + _B64 + r"{24,}\." + _B64 + r"{6}\." + _B64 + r"{27,}(?![A-Za-z0-9_-])",
]))


def matches_credentials(text: str) -> bool:
    """Whether text holds any of the credential patterns."""
    return CREDENTIAL_PATTERN.search(text) is not None
