#!/bin/sh
# prose's hook after a tool call: when the call handed a pull request back for
# review, tells the agent that the current-state pass is due (fixing the title
# and docs that still describe work as unfinished); when it created one whose
# body has no link line, says to add link lines. The work is in prose.py
# (hook-handback); this script exits without starting Python for a payload
# that can be neither. Its patterns must match at least what handbacks.py's
# HANDBACK_WORDS and GitHub MCP tool names match: a call they miss gets no
# note, and nothing reports it.
#
# Usage: handback-notice.sh [--host <platform>]   payload on stdin
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 0
payload=$(cat)
case "$payload" in
  *pull_request*) ;;
  *gh*)
    case "$payload" in
      *create*|*new*|*ready*|*edit*) ;;
      *) exit 0 ;;
    esac ;;
  *) exit 0 ;;
esac
printf '%s' "$payload" | exec python3 "$here/prose.py" hook-handback "$@"
