#!/bin/sh
# prose's posting hook, run before a tool call: blocks a GitHub, Discord or
# Linear post whose body does not end with a valid prose footer. The work is in
# prose.py (hook-post). Every payload goes to Python: a shell pattern on the
# JSON text misses a gh the shell joins, such as g''h or one split by a
# backslash-newline.
#
# Usage: check-post.sh [--host <platform>]   payload on stdin
# Cursor blocks the action when a permission hook prints no valid JSON, so
# with --host cursor every path that allows the action prints Cursor's allow
# JSON.
allow() {
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*) printf '{"permission":"allow"}\n' ;;
  esac
  exit 0
}
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || allow "$@"
exec python3 "$here/prose.py" hook-post "$@"
