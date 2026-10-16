#!/bin/sh
# spec-check's verifier for the shared commit script's --verified-value option:
#
#   commit-with-trailers.sh --verified-value <this file> Spec-check "<value>" ... --message-file msg.txt --
#
# The commit script runs it just before it commits, with the trailer line
# `Spec-check: <value>` as its only argument and the message on stdin. It
# exits 0 when the value's tree is the staged tree, or when the value is a
# `skipped (...)` note, which binds no tree. Any other exit refuses the commit,
# with the reason on stdout. See
# ../../../lib/commit-trailer/commit-with-trailers.sh.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P) || exit 3
exec python3 "$here/spec_check.py" verify-staged "$@"
