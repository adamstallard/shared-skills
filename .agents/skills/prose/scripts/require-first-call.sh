#!/bin/sh
# prose's first-write gate, run before a tool call: blocks a session's first
# file write (Write, Edit, MultiEdit, NotebookEdit, any file) or GitHub post
# until prose's first call has printed the rules in that session. The work is
# in prose.py (hook-gate); this script only saves starting Python for a Bash
# command that names no gh. hook.json's matcher sends only file-writing tools,
# Bash and GitHub MCP tools here, so every other call goes to prose.py.
#
# It fails open: the message reaches the agent only when prose.py exits 2
# with one, so a missing python3, a crash or an unreadable state directory
# lets the call through, silently.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 0
payload=$(cat) || exit 0
case "$payload" in
  *gh*) ;;
  *'"tool_name":"Bash"'*|*'"tool_name": "Bash"'*) exit 0 ;;
esac
out=$(printf '%s' "$payload" | python3 "$here/prose.py" hook-gate 2>/dev/null)
code=$?
if [ "$code" -eq 2 ] && [ -n "$out" ]; then
  printf '%s\n' "$out" >&2
  exit 2
fi
exit 0
