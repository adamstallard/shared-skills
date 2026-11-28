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
SHORT_VALUES: dict[str, dict[str, str]]
LONG_FLAGS: dict[str, dict[str, tuple[set[str], set[str]]]]
COMMON_LONG: tuple[set[str], set[str]]
BODY_SOURCES: dict[str, dict[str, tuple[set[str], str]]]
NO_SOURCES: tuple[set[str], str]
SOURCE: str
NO_TEXT_VERBS: dict[str, set[str]]
DATA_COMMANDS: set[str]
GH_TEXT: re.Pattern[str]
RESERVED: set[str]
CLOSERS: set[str]
APP_SCRIPT: str
PYTHONS: set[str]
VARIABLE: re.Pattern[str]

def _words(command: str) -> list[tuple[str, bool]] | None: ...
def _word(command: str, i: int) -> tuple[str, int, str] | None: ...
def _commands(command: str) -> tuple[list[SimpleCommand], bool] | None: ...
def _gh_args(words: list[tuple[str, bool]]) -> list[tuple[str, bool]]: ...
def app_assignments(words: list[Word], scripts: set[str]) -> bool: ...
def app_command(words: list[Word], scripts: set[str]) -> list[Word] | None: ...
