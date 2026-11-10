"""Build the `slim` candidate variant of spec-check from a copy of the skill.

    python3 -I build_variants.py <skill-dir> <out-dir>

Copies <skill-dir> (bench/ left out) to <out-dir>/slim. Its SKILL.md keeps
what checking and fixing a change needs. The parts only some runs need move
word for word to a new reference.md, which SKILL.md points to: the full
findings table (SKILL.md keeps one line per kind), the TLA+ note, the part
of *Commit* from "An older value" on, and these sections, by heading:
*Archive refusals*, *Stacked changes*, *Keeping a line the evolution check
flags* and *Current-state passes*.

Sections are found by their headings, outside code fences, not by line
number, so the build keeps working when their text changes. It stops with
an error when a heading it moves is gone or appears twice.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys

COMPACT_TABLE = """\
| Kind | Severity | What it means |
| --- | --- | --- |
| `no-scenario` | error | A requirement states a SHALL or MUST and has no scenario |
| `scenario-incomplete` | error | A scenario has no WHEN or no THEN |
| `duplicate` | error | A sentence of the rule also appears under another requirement |
| `archive` | error | `openspec archive` refuses the change; the error quotes the CLI |
| `renamed-block`, `title-reuse` | error | A RENAMED block holds more than FROM and TO; or one title is both removed and added within the change |
| `purpose` | error, or check | A new capability's `## Purpose` would fail validation; or a delta's Purpose for an existing capability differs from the spec's |
| `citation` | error, or check | A `path:line` that is in neither the base branch nor the change |
| `openspec-validate`, `openspec-show` | error, or check | What `openspec validate --strict` reports, or a file `openspec show` cannot read |
| `stack`, `drift` | error, or check | A `Builds on:` line, or a stacked change, is wrong or stale |
| `evolution` | error | A line records history, not what holds now (see [Decisions and open questions](#decisions-and-open-questions)) |
| `kept` | error, or check | A `.spec-check-kept` entry is malformed, unasked or stale |
| `rationale` | check | A requirement holds more than its SHALL statement and one *because* sentence |
| `record` | error, or check | A decision record departs from its form (see [Decision records](#decision-records)), names no requirement, or a change holds a `decisions.md` |
| `config` | error | `openspec/spec-check.yaml` is malformed |

Each message says what to do. [reference.md](reference.md) has the full
table, with every case of each kind.
"""

POINTERS = """\
Read [reference.md](reference.md) when you need it:

- *Archive refusals* and *Stacked changes*: an `archive`, `stack` or `drift`
  finding, or a change that applies on top of another open change (a
  `Builds on:` line in proposal.md).
- *Commit, continued*: before you commit, hand back a pull request, or set
  up a repository's CI; it holds the trailer, the hand-back checks and the
  commit command.
- *Keeping a line the evolution check flags*: an `evolution` error you
  believe is wrong.
- *Current-state passes*: when a hook prints `current-state pass due for`.
- *When to write a TLA+ model*: a requirement about concurrency, ordering,
  a crash between two writes, or a protocol between processes.

"""

HEADING = re.compile(r"^(#{2,3}) (.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


class BuildError(Exception):
    pass


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of each ## or ### heading outside fences."""
    out: list[tuple[int, int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = HEADING.match(line)
        if m and not fenced:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def span(lines: list[str], title: str) -> tuple[int, int]:
    """[start, end) of the section headed `title`, up to the next heading of
    the same or a higher level."""
    hs = headings(lines)
    found = [(n, h) for n, h in enumerate(hs) if h[2] == title]
    if len(found) != 1:
        raise BuildError(f"SKILL.md has {len(found)} headings {title!r}, not one")
    n, (start, level, _) = found[0]
    end = next((i for i, lv, _ in hs[n + 1:] if lv <= level), len(lines))
    return start, end


def table_span(lines: list[str]) -> tuple[int, int]:
    """[start, end) of the findings table under "1. Mechanical checks"."""
    start, end = span(lines, "1. Mechanical checks")
    rows = [i for i in range(start, end) if lines[i].startswith("| Kind |")]
    if len(rows) != 1:
        raise BuildError("no single findings table under '1. Mechanical checks'")
    stop = rows[0]
    while stop < end and lines[stop].startswith("|"):
        stop += 1
    return rows[0], stop


def slim(skill_md: str) -> tuple[str, str]:
    """The slim SKILL.md and its reference.md."""
    lines = skill_md.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    table = table_span(lines)
    archive = span(lines, "Archive refusals")
    stacked = span(lines, "Stacked changes")
    tla = span(lines, "When to write a TLA+ model")
    commit = span(lines, "Commit")
    keeping = span(lines, "Keeping a line the evolution check flags")
    current = span(lines, "Current-state passes")
    tail = next((i for i in range(commit[0], keeping[0]) if lines[i].startswith("An older value")),
                None)
    if tail is None:
        raise BuildError("no paragraph starting 'An older value' in Commit")
    commit_rest = (tail, keeping[0])

    def text(s: tuple[int, int]) -> str:
        return "".join(lines[s[0]:s[1]])

    ref = ("# spec-check: reference\n\nThe parts of [SKILL.md](SKILL.md) that only some runs "
           "need.\n\n## Findings, every case\n\n" + text(table) + "\n"
           + text(archive).replace("### Archive refusals", "## Archive refusals", 1)
           + text(stacked) + text(tla) + "## Commit, continued\n\n" + text(commit_rest)
           + text(keeping).replace("### Keeping a line", "## Keeping a line", 1)
           + text(current))
    for anchor in ("#decision-records", "#decisions-and-open-questions", "#commit"):
        ref = ref.replace(f"]({anchor})", f"](SKILL.md{anchor})")

    moved = {i for s in (archive, stacked, tla, commit_rest, keeping, current)
             for i in range(*s)}
    out: list[str] = []
    for i, line in enumerate(lines):
        if i == table[0]:
            out.append(COMPACT_TABLE)
        if i == commit_rest[0]:
            out.append(POINTERS)
        if table[0] <= i < table[1] or i in moved:
            continue
        out.append(line)
    skill = "".join(out)
    for anchor in ("#stacked-changes", "#keeping-a-line-the-evolution-check-flags",
                   "#archive-refusals"):
        skill = skill.replace(f"]({anchor})", f"](reference.md{anchor})")
    return skill, ref


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python3 -I build_variants.py <skill-dir> <out-dir>")
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]) / "slim"
    try:
        skill, ref = slim((src / "SKILL.md").read_text())
    except BuildError as e:
        sys.exit(f"build_variants: {e}")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__", "bench"))
    (out / "SKILL.md").write_text(skill)
    (out / "reference.md").write_text(ref)
    print(out)


if __name__ == "__main__":
    main()
