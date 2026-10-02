#!/bin/sh
# prose's verifier for the shared commit script's --verified-value option:
#
#   commit-with-trailers.sh --verified-value <this file> Prose "<value>" ... -- <subject> <body>
#
# The script runs it just before it commits, with the trailer line
# `Prose: <value>` as its only argument and the message on stdin. It exits 0
# when the line still matches the staged tree and the message; any other exit
# refuses the commit, and the reason is on stdout. See
# ../../../lib/commit-trailer/commit-with-trailers.sh.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P) || exit 3
exec python3 "$here/prose.py" verify-staged "$@"
