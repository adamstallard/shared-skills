# bug-hunter's report text, sourced by the shared commit-trailer check
# (../../../lib/commit-trailer/check-commit-trailer.sh) when commits land
# without a valid Bug-hunter: trailer. The check supplies the facts — unchecked,
# unminted, misplaced, count_unchecked, repo_label — and this sets REPORT.
#
# The report states facts and stops: no commands, since the hook cannot see
# where the reader is standing. See that library's DECISIONS.md.
#
# Body left unindented on purpose: the strings below are multi-line report text,
# and indenting them would indent what the user reads.
commit_trailer_report() {
NOTE=""
[ -n "$misplaced" ] && NOTE="
There is a Bug-hunter: line in there, but git does not read it as a trailer. It
has to sit in the last paragraph, beside any other trailers, and it needs a
value. Two ways to lose it: a blank line before it starts a new paragraph, and a
wrapped line whose continuation is not indented.

Rather than placing it by hand, let git place it. This skill's own commit
script takes the value as an argument and passes it as --trailer, so it lands
in the trailer block whatever the body looks like. Write the message (subject,
a blank line, body) to msg.txt, then:

  ~/.agents/skills/bug-hunter/scripts/commit-with-trailer.sh -F msg.txt '1 iteration, 1 bug fixed'

(under ~/.claude/skills/bug-hunter/scripts/ if only that target is installed).
The file keeps the message off the command line, so nothing in it needs
quoting. A last argument is the Co-Authored-By value, placed the same way, so
the two cannot drift into separate paragraphs; any value that is not a skip
note also gets its Bug-hunter-Tree binding minted against what is staged.
"

REPORT=""

if [ -n "$unchecked" ]; then
  # State the standard unconditionally. The previous wording — "every commit
  # containing code should go through the bug-hunter skill, and record what
  # happened in a Bug-hunter: trailer" — made the trailer clause subordinate to
  # "containing code", so a docs-only commit falsified the antecedent and read
  # as exempt from the whole sentence. Three of them in one session were
  # reported, read correctly that way, and left alone
  # (../DECISIONS.md#a-skip-is-a-value-for-the-trailer-not-an-exemption-from-it).
  # The categories are listed rather than detected: classifying the diff here
  # would be a second copy of reference.md's table, and copies drift.
  REPORT="${REPORT}bug-hunter: $count_unchecked new commit(s) landed without being checked${repo_label:+ in $repo_label}.

$(printf '%s' "$unchecked")
$NOTE
Every commit records what happened in a Bug-hunter: trailer — not only the ones
containing code. A commit with nothing to review is exempt from the hunt, never
from the trailer: docs, specs, tests, formatting, a pure rename or move, a
revert, a merge, or work in progress all take the value
\"skipped at triage (<reason>)\", which needs no review pass and no tree binding.
"
fi

if [ -n "$unminted" ]; then
  count_unminted=$(printf '%s' "$unminted" | grep -c . || true)
  # A separate paragraph, not folded into the message above: the failure here
  # is a different one — a trailer that exists, parses, and claims fixed bugs,
  # but carries no Bug-hunter-Tree binding matching what was actually
  # committed. That is exactly what a hand-typed trailer produces, and
  # exactly what running scripts/mint-trailer.sh after staging cannot fail to
  # produce, so the two are distinguishable only by checking the tree.
  REPORT="${REPORT}
bug-hunter: $count_unminted commit(s) carry a Bug-hunter: trailer with no Bug-hunter-Tree binding matching what actually landed${repo_label:+ in $repo_label}.

$(printf '%s' "$unminted")

A Bug-hunter: trailer that is not a skip note has to be paired with a
Bug-hunter-Tree trailer bound to the tree that lands. This skill's commit
script (scripts/commit-with-trailer.sh, under ~/.agents/skills/bug-hunter/scripts/
or ~/.claude/skills/bug-hunter/scripts/) produces that as part of creating the
commit, by running scripts/mint-trailer.sh against what is staged at that
moment. A trailer typed from memory can match the expected wording; it cannot
produce this binding.
"
fi

REPORT="${REPORT}
A trailer belongs in the last paragraph of the message, and a wrapped one must
indent its continuation lines; passing --trailer lets git place it, which is
that whole class of mistake gone. This skill's commit step is one command, not
a hand-built git commit: commit-with-trailer.sh -F msg.txt <Bug-hunter value>
[<Co-Authored-By value>], with the message in msg.txt, under
~/.agents/skills/bug-hunter/scripts/ or ~/.claude/skills/bug-hunter/scripts/. Rewriting a commit that is already pushed
rewrites published history — ask before doing that.

To stop this check entirely:

  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook bug-hunter"

}
