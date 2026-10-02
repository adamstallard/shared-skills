#!/bin/sh
# Prints the one line a commit message cannot get from memory: the tree hash
# of whatever is staged right now, as a ready-to-pass --trailer value.
#
# Usage: mint-trailer.sh <key>      prints "<key>-Tree: <tree hash>"
#
# Shared: each skill that enforces a trailer calls this through a wrapper of
# its own that supplies the key (bug-hunter's passes Bug-hunter).
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file — in
# particular "The trailer is minted from the tree, not recalled by the agent".
#
# Run this AFTER the final `git add` and BEFORE `git commit` — the value is
# only good for the tree it was minted against. Never type the value by hand,
# and never copy one from another commit or another run — it has to be this
# run, against this exact staged tree, or the companion hook cannot tell it
# apart from one that was only ever typed to look right.
#
# Writes a tree object into this repository's object store (that is what
# `git write-tree` does) — unreferenced and harmless, cleaned up by the next
# `git gc` like any other unreachable object, but this is the one thing in
# this hook family that is not a pure read of git state.
set -eu

key=${1:-}
case "$key" in
  ''|*[!A-Za-z0-9-]*)
    echo "mint-trailer: usage: mint-trailer.sh <key>, a trailer key of letters, digits and dashes" >&2
    exit 2 ;;
esac

# stdout and stderr are captured separately, not merged (2>&1) — under
# GIT_TRACE=1 or a stale core.fsmonitor hook, git can print to stderr on an
# otherwise-successful write-tree, and a merged capture would fold that text
# into $tree ahead of the hash, corrupting the value this script exists to
# get right. Stderr is only read back for the failure message.
tree_err=$(mktemp) || {
  echo "mint-trailer: could not create a temp file for git's stderr" >&2
  exit 1
}
trap 'rm -f "$tree_err"' EXIT

if ! tree=$(git write-tree 2>"$tree_err"); then
  printf 'mint-trailer: git write-tree failed - are you in a git repository with something staged? (%s)\n' "$(cat "$tree_err")" >&2
  exit 1
fi

printf '%s-Tree: %s\n' "$key" "$tree"
