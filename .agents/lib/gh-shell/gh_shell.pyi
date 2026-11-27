# Types for gh_shell.py, which is untyped, so that code under the strict
# check of .agents/pyrightconfig.json can import it. Only the names that code
# uses are declared; add one here when it needs another. Kept by whoever
# builds the shared post reader (post_reader.py).

import re

Word = tuple[str, str]
SimpleCommand = tuple[list[Word], bool]

GITHUB_MCP: re.Pattern[str]
BODY_FLAGS: tuple[str, ...]
COMMENT_FLAGS: tuple[str, ...]
GH_VERBS: dict[str, dict[str, tuple[str, ...]]]
DATA_COMMANDS: set[str]

def _words(command: str) -> list[tuple[str, bool]] | None: ...
def _commands(command: str) -> tuple[list[SimpleCommand], bool] | None: ...
def app_assignments(words: list[Word], scripts: set[str]) -> bool: ...
def app_command(words: list[Word], scripts: set[str]) -> list[Word] | None: ...
