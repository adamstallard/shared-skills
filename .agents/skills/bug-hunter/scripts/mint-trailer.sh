#!/bin/sh
# Prints the one line a commit message cannot get from memory: the tree hash
# of whatever is staged right now, as a ready-to-pass Bug-hunter-Tree trailer.
#
# Run this AFTER the final `git add` and BEFORE `git commit` — the value is
# only good for the tree it was minted against:
#
#   git add fix.py test_fix.py
#   git commit -m "Handle empty input in the parser" -m "Body text here." \
#     --trailer "Bug-hunter: 1 iteration, 1 bug fixed" \
#     --trailer "$(scripts/mint-trailer.sh)"
#
# Needed alongside any Bug-hunter: trailer except a skip. "0 bugs found" and
# "aborted ..." both mean the loop ran over this tree, same as "N bugs
# fixed" does — only "skipped ..." means triage stopped before any loop ran,
# with nothing for a tree to attest to.
#
# The minting is shared — ../../../lib/commit-trailer/mint-trailer.sh, whose
# DECISIONS.md explains "The trailer is minted from the tree, not recalled by
# the agent". Read that before changing either file.

# -P so the paths below, and any error naming them, are the clone's rather
# than an install symlink's.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/mint-trailer.sh"
if [ -z "$here" ] || [ ! -r "$lib" ]; then
  echo "mint-trailer: the shared commit-trailer library is missing (expected at $lib); bug-hunter must be installed as a symlink into a full shared-skills clone" >&2
  exit 1
fi
exec sh "$lib" Bug-hunter
