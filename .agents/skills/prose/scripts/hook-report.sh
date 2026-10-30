# prose's report text and trailer verification, sourced by the shared
# commit-trailer check (../../../lib/commit-trailer/check-commit-trailer.sh).
# The check sets the variables unchecked, rejected, misplaced, count_unchecked
# and repo_label, and commit_trailer_report turns them into REPORT. Those that
# may be unset are read with a default: the library runs under set -u, and an
# older library, from before commit_trailer_verify existed, never sets rejected.
#
# The report says which commits and what is wrong with them, then names
# SKILL.md's *Committing* section instead of restating it, and names none of
# the skill's files (the library's DECISIONS.md, "Each report names its skill's section").
#
# The function bodies are not indented: the strings below are multi-line
# report text, and indenting them would indent what the user reads.

# Called by the library for each commit or amend (not a rebase or other
# replay) carrying a Prose: trailer, in place of its <key>-Tree check. prose.py prints the reason; its exit status
# is the library's contract: 0 valid, 1 invalid (either half of the trailer
# does not match), anything else unverifiable.
commit_trailer_verify() {
python3 "${PROSE_SCRIPTS:-.}/prose.py" verify-commit "$1"
}

commit_trailer_report() {
REPORT=""

if [ -n "${unchecked:-}" ]; then
REPORT="prose: $count_unchecked new commit(s) landed without a Prose: trailer${repo_label:+ in $repo_label}.

$(printf '%s' "$unchecked")
"
[ -n "${misplaced:-}" ] && REPORT="${REPORT}
There is a Prose: line in there, but git does not read it as a trailer.
"
fi

if [ -n "${rejected:-}" ]; then
count_rejected=$(printf '%s' "$rejected" | grep -c . || true)
REPORT="${REPORT}${REPORT:+
}prose: $count_rejected commit(s) carry a Prose: trailer that does not hold${repo_label:+ in $repo_label}.

$(printf '%s' "$rejected")
"
fi

REPORT="${REPORT}
Ask before rewriting a pushed commit.
Fix it with the prose skill's *Committing* steps.

A person who does not want this check can turn it off:
  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook prose"
}
