#!/bin/sh
# The inquisitor's post hook, run before a Bash call or a GitHub or Linear
# MCP call in Claude Code: blocks a post holding a question that
# `inquisitor.py vet`'s two calls did not pass. The work is in inquisitor.py
# (hook-post). Every payload goes to Python, with no shell pattern first:
# one on the JSON text misses a gh the shell joins, such as g''h. It fails
# closed: a published post cannot be taken back, so when Python cannot give
# its answer, 0 or 2, the call is blocked.
#
# Usage: check-post.sh   payload on stdin
fail() {
  echo "inquisitor: blocked this call, since the post hook failed ($1) and what it posts cannot be checked." >&2
  exit 2
}
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || fail "its folder cannot be found"
python3 -I "$here/inquisitor.py" hook-post
status=$?
case $status in
  0|2) exit $status ;;
esac
fail "exit $status"
