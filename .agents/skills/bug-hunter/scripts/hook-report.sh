# bug-hunter's report text, sourced by the shared commit-trailer check
# (../../../lib/commit-trailer/check-commit-trailer.sh) when commits land
# without a valid Bug-hunter: trailer. The check supplies the facts — unchecked,
# unminted, misplaced, count_unchecked, repo_label — and this sets REPORT.
#
# The report says which commits and what is wrong with them. For the fix, it
# names a SKILL.md section rather than copying that section's steps: a copy
# here drifts from SKILL.md. It names none of the skill's files: SKILL.md
# gives each path from the skill's base directory, which the agent knows, and a
# path printed here would need quoting for a shell, which Cursor's channel
# cannot carry. See that library's DECISIONS.md, "The report states facts and
# stops" and "Each report names its skill's section".
#
# Body left unindented on purpose: the strings below are multi-line report text,
# and indenting them would indent what the user reads.
commit_trailer_report() {
REPORT=""

if [ -n "$unchecked" ]; then
# No condition such as "containing code" on the first line: a docs-only commit
# needs the trailer too, and a condition here reads as exempting it
# (../DECISIONS.md#a-skip-is-a-value-for-the-trailer-not-an-exemption-from-it).
REPORT="bug-hunter: $count_unchecked new commit(s) landed without a Bug-hunter: trailer${repo_label:+ in $repo_label}.

$(printf '%s' "$unchecked")
"
[ -n "$misplaced" ] && REPORT="${REPORT}
There is a Bug-hunter: line in there, but git does not read it as a trailer.
"
fi

if [ -n "$unminted" ]; then
count_unminted=$(printf '%s' "$unminted" | grep -c . || true)
REPORT="${REPORT}${REPORT:+
}bug-hunter: $count_unminted commit(s) carry a Bug-hunter: trailer with no Bug-hunter-Tree binding matching what landed${repo_label:+ in $repo_label}.

$(printf '%s' "$unminted")
"
fi

REPORT="${REPORT}
Ask before rewriting a pushed commit.
Fix it with the bug-hunter skill's *If you are an agent about to commit* steps.

A person who does not want this check can turn it off:
  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook bug-hunter"
}
