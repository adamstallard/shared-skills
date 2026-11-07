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

# Called by the library for each new commit, whatever its trailer: prints
# `current-state pass due for: ...` when the commit adds a file under a src/
# directory on a branch with an open change (gate two of the two-gate
# workflow), or archives a change. When openspec is a symlink, pass-due
# prints one line saying no notice is given, for a commit that changes the
# symlink or adds a src/ file. The git reads spare starting Python for a
# commit whose openspec is a real folder, or absent, when its tree has no
# openspec/changes/ or the commit adds no src/ file and no archive. While
# openspec is a symlink, Python starts for every commit.
commit_trailer_notice() {
case $(git ls-tree --full-tree "$1" -- openspec 2>/dev/null) in
  120000\ *) python3 "${SPEC_CHECK_SCRIPTS:-.}/spec_check.py" pass-due "$1"; return 0 ;;
esac
git cat-file -e "$1:openspec/changes" 2>/dev/null || return 0
git -c core.quotePath=false diff-tree --no-commit-id --name-only --no-renames \
  --diff-filter=A -r --root "$1" 2>/dev/null |
  grep -qE '(^|/)src/|^openspec/changes/archive/' || return 0
python3 "${SPEC_CHECK_SCRIPTS:-.}/spec_check.py" pass-due "$1"
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

REPORT="${REPORT}
Ask before rewriting a pushed commit.
Fix it with the spec-check skill's *Commit* steps.

A person who does not want this check can turn it off:
  python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook spec-check"
}
