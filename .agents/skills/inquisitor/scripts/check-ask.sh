#!/bin/sh
# The inquisitor's picker hook, run before an AskUserQuestion call in Claude
# Code: blocks a question that `inquisitor.py vet`'s two calls did not record
# as ask. The work is in inquisitor.py (hook-ask). It fails open: only
# Python's exit 2, a block, stops the call; anything else, a crash
# included, lets it through.
#
# Usage: check-ask.sh   payload on stdin
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 0
python3 -I "$here/inquisitor.py" hook-ask
[ $? -eq 2 ] && exit 2
exit 0
