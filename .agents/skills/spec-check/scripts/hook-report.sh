# spec-check's report text and trailer verification, sourced by the shared
# commit-trailer check (../../../lib/commit-trailer/check-commit-trailer.sh).
# The check sets unchecked, rejected, misplaced, count_unchecked and
# repo_label, and commit_trailer_report turns them into REPORT. Those that may
# be unset are read with a default, because the library runs under set -u.
#
# The report says which commits and what is wrong with them, then names
# SKILL.md's *Commit* section instead of restating it, and names none of the
# skill's files (the library's DECISIONS.md, "Each report names its skill's section").
#
# The function bodies are not indented: the strings below are multi-line
# report text, and indenting them would indent what the user reads.

# Called by the library for each commit or amend carrying a Spec-check:
# trailer, in place of its <key>-Tree check. spec_check.py prints the reason;
# its exit status is the library's contract: 0 valid, 1 invalid, anything
# else unverifiable.
commit_trailer_verify() {
python3 "${SPEC_CHECK_SCRIPTS:-.}/spec_check.py" verify-commit "$1" "$2"
}

commit_trailer_report() {
REPORT=""

if [ -n "${unchecked:-}" ]; then
REPORT="spec-check: $count_unchecked new commit(s) changed openspec/ without a Spec-check: trailer${repo_label:+ in $repo_label}.

$(printf '%s' "$unchecked")
"
[ -n "${misplaced:-}" ] && REPORT="${REPORT}
There is a Spec-check: line in there, but git does not read it as a trailer.
"
fi

if [ -n "${rejected:-}" ]; then
count_rejected=$(printf '%s' "$rejected" | grep -c . || true)
REPORT="${REPORT}${REPORT:+
}spec-check: $count_rejected commit(s) carry a Spec-check: trailer that does not hold${repo_label:+ in $repo_label}.

$(printf '%s' "$rejected")
"
fi

# One more line, asking for setup, when the repository has an openspec/ at its
# top but no openspec/spec-check.yaml, which records whether it enforces the
# decisions-first rule. The proposal hook and `check` ask the agent the same
# question; this line reaches whoever reads the report, in case neither did.
#
# A repository with no openspec/ at its top gets no line, because there is
# nothing to set up: a commit deleting openspec/ is reported without it. The
# proposal hook is silent there too.
#
# The top comes from git, not from the current directory. The library runs
# this cd'd into the directory the hook's input names, which may be a
# subdirectory, and again cd'd into each submodule, whose own top is the one
# meant.
top=$(git rev-parse --show-toplevel 2>/dev/null) || top=""
if [ -n "$top" ] && [ -d "$top/openspec" ] &&
   [ "$(python3 "${SPEC_CHECK_SCRIPTS:-.}/spec_check.py" state --repo "$top" 2>/dev/null)" = undecided ]; then
REPORT="${REPORT}
This repository has not decided on spec-check's decisions-first rule: ask your agent to set up spec-check in this repository.
"
fi

REPORT="${REPORT}
Ask before rewriting a pushed commit.
Fix it with the spec-check skill's *Commit* steps.

A person who does not want this check can turn it off:
  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook spec-check"
}
