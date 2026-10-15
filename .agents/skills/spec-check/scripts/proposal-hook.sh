#!/bin/sh
# spec-check's proposal hook, run after the agent writes or edits a file. When
# the file is an OpenSpec proposal (openspec/changes/<name>/proposal.md) in a
# repository that has not decided on the decisions-first rule (it has no
# openspec/spec-check.yaml), it tells the agent to ask the user whether to
# enforce it. Otherwise it prints nothing.
#
# Usage: proposal-hook.sh --host claude|cursor   (hook payload on stdin)
#
# The work is in spec_check.py (proposal-hook). This script exists so that a
# payload naming no proposal.md never starts Python. It never blocks
# and fails open: any error, including a missing python3, means silence.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 0
payload=$(cat) || exit 0
case "$payload" in
  *proposal.md*) ;;
  *) exit 0 ;;
esac
printf '%s' "$payload" | python3 "$here/spec_check.py" proposal-hook "$@" 2>/dev/null
exit 0
