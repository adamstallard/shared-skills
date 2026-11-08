#!/bin/sh
# prose's hook after a tool call: when the call handed a pull request back for
# review, tells the agent the current-state pass that is due. The work is in
# prose.py (hook-handback); this script exits without starting Python for a
# payload that cannot be a hand-back. Its patterns must match at least what
# handbacks.py's HANDBACK_WORDS and GitHub MCP tool names match.
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
