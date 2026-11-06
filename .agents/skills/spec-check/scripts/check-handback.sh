#!/bin/sh
# spec-check's hand-back hook, run before and after a tool call: blocks, or
# takes back, a pull request handed back for review while a change at its head
# is unread. The work is in handback.py; this script only saves starting
# Python for a payload that cannot be a hand-back. Its patterns must match
# at least what handback.py's HANDBACK_WORDS and GitHub MCP tool names match,
# or a hand-back would be let through unjudged.
#
# Usage: check-handback.sh [--host <platform>]   payload on stdin
# Cursor blocks the action when a permission hook prints no valid JSON, so
# every path that allows the action before it runs prints Cursor's allow JSON.
allow() {
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*)
      case "$payload" in
        *'"postToolUse"'*|*'"afterShellExecution"'*|*'"afterMCPExecution"'*) ;;
        *) printf '{"permission":"allow"}\n' ;;
      esac ;;
  esac
  exit 0
}
payload=
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || allow "$@"
payload=$(cat)
case "$payload" in
  *pull_request*) ;;
  *gh*)
    case "$payload" in
      *create*|*new*|*ready*|*edit*) ;;
      *) allow "$@" ;;
    esac ;;
  *) allow "$@" ;;
esac
printf '%s' "$payload" | exec python3 "$here/handback.py" "$@"
