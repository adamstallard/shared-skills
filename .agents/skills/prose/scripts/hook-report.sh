# prose's report text and trailer verification, sourced by the shared
# commit-trailer check (../../../lib/commit-trailer/check-commit-trailer.sh).
# The check sets the variables unchecked, rejected, misplaced, count_unchecked
# and repo_label, and commit_trailer_report turns them into REPORT. Those that
# may be unset are read with a default: the library runs under set -u, and a
# library version without the verify callback never sets rejected.
#
# The report states facts and suggests no git commands (the library's
# DECISIONS.md, "The report states facts and stops").
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
REPORT="${REPORT}prose: $count_unchecked new commit(s) landed without a Prose: trailer${repo_label:+ in $repo_label}.

$(printf '%s' "$unchecked")
"
[ -n "${misplaced:-}" ] && REPORT="${REPORT}
There is a Prose: line in there, but git does not read it as a trailer. It has
to sit in the last paragraph, beside any other trailers. Committing through
commit-with-trailers.sh lets git place it.
"
REPORT="${REPORT}
Every commit carries one Prose: ✓ <tree>:<message> line: every commit has a
message a reviewer reads. prose check prints it, from the staged files and the
final message.
"
fi

if [ -n "${rejected:-}" ]; then
count_rejected=$(printf '%s' "$rejected" | grep -c . || true)
REPORT="${REPORT}
prose: $count_rejected commit(s) carry a Prose: trailer that does not hold${repo_label:+ in $repo_label}.

$(printf '%s' "$rejected")

A Prose: trailer is valid only as prose check printed it, for the files and
message that landed. Staging a change or editing the message after the check
breaks it. Run both calls again: prose check -F <message file> --goals '<goals>'
prints the rules and a pass token; the same command with --pass <token> in
place of --goals prints the line to commit with.
"
fi

REPORT="${REPORT}
Rewriting a commit that is already pushed rewrites published history — ask
before doing that.

To stop this check entirely:

  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook prose"
}
