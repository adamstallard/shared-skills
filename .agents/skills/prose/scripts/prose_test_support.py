"""Shared helpers for prose's test files: throwaway repositories, a state
directory away from the user's, prose.py and compact.py compiled from
source, and builders for cold readers' reports.

Not a test file. Each test_*.py beside it imports what it uses from here.
"""

import contextlib
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "prose.py"
COMMIT_HOOK = HERE / "check-commit-trailer.sh"
HOOK_REPORT = HERE / "hook-report.sh"
POST_HOOK = HERE / "check-post.sh"
VERIFY_STAGED = HERE / "verify-staged.sh"
LIBRARY = HERE.parent.parent.parent / "lib" / "commit-trailer"
COMMIT_SCRIPT = LIBRARY / "commit-with-trailers.sh"
BUG_HUNTER_MINT = HERE.parent.parent / "bug-hunter" / "scripts" / "mint-trailer.sh"
TRAILER = r"^Prose: ✓ [0-9a-f]{12}:[0-9a-f]{12}(; cold read: [^;]+; understood: [^;]+)?$"
BUG_HUNTER_HOOK = HERE.parent.parent / "bug-hunter" / "scripts" / "check-commit-trailer.sh"
GATE = HERE / "require-first-call.sh"

# Pass tokens and session marks go to a throwaway state directory, never the
# user's, and no test inherits the session of the agent running it.
STATE = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = STATE
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

# Compiled from source rather than imported, so a stale .pyc can never stand
# in for the code under test (see test_comment_scan.py).
prose = types.ModuleType("prose_under_test")
prose.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), prose.__dict__)


# Reader goals for every listed file, which Repo.prose adds to a check.
ALL_FILES = ["--goals-for", "**", "read it"]


def block_trailer(stdout):
    """The trailer line in the result block that ends stdout; fails unless
    stdout ends with exactly that block, holding one trailer and nothing open."""
    lines = stdout.split("\n")
    if len(lines) < 5 or lines[-1] != "" or lines[-5] != "=== prose result ===" \
            or lines[-3:-1] != ["=== prose open decisions: 0 ===", "=== end prose ==="]:
        raise AssertionError(f"stdout does not end with prose's result block:\n{stdout[-400:]}")
    return lines[-4]


def pass_token(output):
    """The token a first call printed."""
    found = re.search(r"^Pass token: ([0-9a-f]{16})\.", output, re.M)
    if not found:
        raise AssertionError(f"no pass token in:\n{output[-600:]}")
    return found.group(1)


REPORTS = pathlib.Path(tempfile.mkdtemp())


def understood_lines(count):
    """One understood line, as a report holds it, for each item from 1 to count."""
    return "".join(f"Item {n}, understood: The code does this, always.\n"
                   for n in range(1, count + 1))


def cold_report(token, body="Item 1: read straight through.\n", name="", understood=1):
    """A cold reader's report for this token, as a file outside any test
    repository; its path. Its last lines are understood lines for the first
    `understood` items, none when that is 0."""
    # Named by the token's hash: a test may pass a token shaped like a path.
    path = REPORTS / ((name or hashlib.sha256(token.encode("utf-8")).hexdigest()) + ".txt")
    path.write_text(f"cold-read {token}\n\n{body}{understood_lines(understood)}",
                    encoding="utf-8")
    return str(path)


def matching(token, count=1, *lines, name=""):
    """A dispositions file for this token: lines, then 'Item <n>: matches' for
    each item from 1 to count; its path."""
    path = REPORTS / ((name or hashlib.sha256(token.encode("utf-8")).hexdigest())
                      + "-dispositions.txt")
    path.write_text("\n".join([f"dispositions {token}", *lines]
                              + [f"Item {n}: matches" for n in range(1, count + 1)]) + "\n",
                    encoding="utf-8")
    return str(path)


def cold_flags(token, count=1):
    """The signing call's flags for a report that reads each item from 1 to
    count straight through, and dispositions that find each understood line a
    match."""
    return ["--cold-read", cold_report(token, "".join(
        f"Item {n}: read straight through.\n" for n in range(1, count + 1)), understood=count),
        "--dispositions", matching(token, count)]


def straight_report(output):
    """The signing call's flags for the brief in output: a report that reads
    every item straight through, and dispositions answering each understood
    line with a match."""
    token = re.search(r"^  cold-read ([0-9a-f]{16})$", output, re.M).group(1)
    count = len(re.findall(r"^\d+\. (?:A code comment|A doc passage|The post below)", output,
                           re.M))
    return cold_flags(token, count)


def cold_read(call):
    """Runs call() with no flags. When that prints a brief, runs call again,
    passing it the flags for a report that reads every item straight through
    and dispositions that find every understood line a match. The last
    call's result."""
    first = call()
    if first.returncode != prose.COLD_READ_NEEDED:
        return first
    return call(*straight_report(first.stdout + first.stderr))


def run(args, cwd=None, stdin=None, env=None):
    return subprocess.run(
        args, cwd=cwd, input=stdin, capture_output=True, text=True, check=False, env=env,
    )


class Repo:
    """A throwaway repository."""

    def __init__(self):
        self.path = pathlib.Path(tempfile.mkdtemp())
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, stdin=None):
        result = run(["git"] + list(args), cwd=self.path, stdin=stdin)
        if result.returncode != 0:
            raise AssertionError(f"git {args} failed: {result.stderr}")
        return result.stdout

    def write(self, name, text):
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        self.git("add", name)

    def prose(self, *args, stdin=None, file_goals=True):
        """prose.py in this repository. A check that names no per-file goals
        gets ALL_FILES, so a test about something else is not refused for a
        doc without goals; file_goals=False leaves them out."""
        args = list(args)
        if file_goals and args[:1] == ["check"] \
                and not {"--goals-for", "--goals-file"} & set(args):
            args += ALL_FILES
        return run([sys.executable, str(SCRIPT)] + args, cwd=self.path, stdin=stdin)

    def two_calls(self, *args, stdin=None, file_goals=True):
        """The pass as SKILL.md runs it: the first call, then, when it issued a
        pass token, the signing call with that token and a cold reader's
        report. The signing call's result, or the first call's when that one
        was refused."""
        first = self.prose(*args, stdin=stdin, file_goals=file_goals)
        if first.returncode != 4:
            return first
        token = pass_token(first.stdout)
        return cold_read(lambda *cold: self.prose(*args, "--pass", token, *cold, stdin=stdin,
                                                  file_goals=file_goals))

    def trailers(self, message, *extra):
        """The one trailer line in the result block the signing call prints
        for this message, which is all it prints."""
        (self.path / ".msg").write_bytes(message.encode("utf-8"))
        result = self.two_calls("check", "-F", ".msg", "--goals", "review it", *extra)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        trailer = block_trailer(result.stdout)
        if result.stdout.count("\n") != 4:
            raise AssertionError(f"expected only the result block, got {result.stdout!r}")
        return trailer

    def commit(self, message=None, trailers=(), m_parts=None):
        """Commit, passing each trailer with --trailer. The one place the
        tests make a commit carrying prose's trailer."""
        if isinstance(trailers, str):
            trailers = [trailers]
        args = ["commit", "-q"]
        if m_parts is not None:
            for part in m_parts:
                args += ["-m", part]
        else:
            (self.path / ".msg").write_bytes(message.encode("utf-8"))
            args += ["-F", ".msg"]
        for trailer in trailers:
            args += ["--trailer", trailer]
        self.git(*args)

    def commit_script(self, subject, body, *families):
        """Commit through the shared commit script, as SKILL.md says to."""
        args = ["sh", str(COMMIT_SCRIPT), *families, "--", subject, body]
        return run(args, cwd=self.path)

    def verify(self, sha="HEAD"):
        return self.prose("verify-commit", sha)

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


# compact.py, compiled from source as prose.py is above, so a stale .pyc can
# never stand in for the code under test.
COMPACT = HERE / "compact.py"
compact = types.ModuleType("compact_under_test")
compact.__file__ = str(COMPACT)
exec(compile(COMPACT.read_text(encoding="utf-8"), str(COMPACT), "exec"), compact.__dict__)


def answers_file(brief_output):
    """The answers file a compaction brief names."""
    return pathlib.Path(re.search(r"^Answers file: (.*)$", brief_output, re.M).group(1))


def paragraphs(count, word="Rule"):
    """A current-state doc of count distinct paragraphs, about 60 bytes each."""
    return "# Doc\n\n" + "".join(f"{word} {n} holds, because reason {n} applies.\n\n"
                                 for n in range(count))


REPEAT = "The token expires two hours after the first call that issued it.\n\n"


def repeated(times=2, extra=""):
    """A doc holding one twelve-word sentence as many times as the times
    argument says: every copy after the first is a repetition passage, 64
    bytes."""
    return "# Doc\n\n" + extra + "".join(REPEAT + f"Filler paragraph {n} stands here.\n\n"
                                         for n in range(times))


@contextlib.contextmanager
def mock_attr(owner, name, value):
    old = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, old)
