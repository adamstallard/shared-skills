#!/bin/sh
# prose's posting hook, run before a tool call: blocks a GitHub post whose
# body does not end with a valid prose footer. The work is in prose.py
# (hook-post); this script only saves starting Python for a payload that
# cannot be a post.
#
# Usage: check-post.sh [--host <platform>]   payload on stdin
# Cursor blocks the action when a permission hook prints no valid JSON, so
# every path that allows the action prints Cursor's allow JSON.
allow() {
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*) printf '{"permission":"allow"}\n' ;;
  esac
  exit 0
}
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || allow "$@"
payload=$(cat)
case "$payload" in
  *gh*|*mcp__*|*mcp_server_name*) ;;
  *) allow "$@" ;;
esac
printf '%s' "$payload" | exec python3 "$here/prose.py" hook-post "$@"
