#!/bin/sh
# Prints the result block that ends a "caller commits" run: the Bug-hunter
# trailer, the Bug-hunter-Tree binding minted here over what is staged now,
# and the open decisions. The agent supplies the value and the decisions;
# nothing in the block is typed by hand.
#
# The format belongs to the shared library,
# ../../../lib/commit-trailer/result-block.sh. BEFORE CHANGING EITHER FILE,
# READ that library's DECISIONS.md "The result block is printed by a script",
# and ../DECISIONS.md "A caller that commits gets the result, not the commit".
#
# Usage:
#   caller-result.sh <bug-hunter-value> [--decisions <file>]
#
#   bug-hunter-value Everything after "Bug-hunter: " — what
#                    commit-with-trailer.sh's third argument would have been.
#                    A value starting with "skipped" (either case of the s)
#                    mints nothing, so its block has no tree line.
#   --decisions      One open decision per line, without its number, or `-`
#                    for stdin. Omit it when nothing is open.
#
# Run it AFTER the final `git add`: the binding is good only for the tree
# staged when it is minted, and the caller must commit exactly that tree.
#
# Exit 2 for a bad argument. Exit 1 when the library is missing, or when the
# mint fails or prints anything but a one-line binding. Either way, nothing is
# printed to stdout.
set -eu

usage() {
  echo "usage: caller-result.sh <bug-hunter-value> [--decisions <file>]" >&2
  exit 2
}

# Without the count check, an unquoted value would split into several words
# and the block would carry only the first.
case $# in
  1) ;;
  3) [ "$2" = --decisions ] || usage ;;
  *) usage ;;
esac
value=$1
# Without this check, an empty unquoted value would vanish and `--decisions`
# would be printed as the Bug-hunter value.
case $value in --|--decisions) echo "caller-result.sh: the Bug-hunter value is missing: '$value' was taken as it" >&2; exit 2 ;; esac

# -P resolves an install symlink, so the paths below, and any error naming
# them, point into the clone.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/result-block.sh"
if [ -z "$here" ] || [ ! -r "$lib" ]; then
  echo "caller-result.sh: the shared commit-trailer library is missing (expected at $lib); bug-hunter must be installed as a symlink into a full shared-skills clone. No block printed" >&2
  exit 1
fi

nl=$(printf '\nx'); nl=${nl%x}
trimmed=$value
while :; do case $trimmed in [[:space:]]*) trimmed=${trimmed#?} ;; *) break ;; esac; done
while :; do case $trimmed in *[[:space:]]) trimmed=${trimmed%?} ;; *) break ;; esac; done
# Checked before the mint, so a bad value mints nothing. The library checks
# the same again, for every skill.
case $trimmed in
  '') echo "caller-result.sh: the Bug-hunter value is empty; no block printed" >&2; exit 2 ;;
  *"$nl"*) echo "caller-result.sh: the Bug-hunter value contains a line break; a trailer is one line. No block printed" >&2; exit 2 ;;
esac

if [ "$#" -eq 3 ]; then set -- --decisions "$3"; else set --; fi

case $trimmed in
  [Ss]kipped*)
    exec sh "$lib" bug-hunter "$@" -- "Bug-hunter: $trimmed" ;;
esac

# Kept in an assignment of its own: inside another command's arguments, a
# failing $(...) does not trip `set -e`.
tree=$(sh "$here/mint-trailer.sh") || {
  echo "caller-result.sh: mint-trailer.sh failed; no block printed" >&2
  exit 1
}
# A zero exit is not enough: git can succeed while writing to stderr, and a
# mint that captured it would return several lines with the hash last. The
# line-break check comes first because grep matches any one line.
case $tree in *"$nl"*) tree_ok=n ;; *) tree_ok=y ;; esac
[ "$tree_ok" = y ] && printf '%s' "$tree" | grep -Eqx 'Bug-hunter-Tree: ([0-9a-f]{40}|[0-9a-f]{64})' || {
  echo "caller-result.sh: mint-trailer.sh printed something other than one Bug-hunter-Tree line; no block printed:" >&2
  printf '%s\n' "$tree" >&2
  exit 1
}
exec sh "$lib" bug-hunter "$@" -- "Bug-hunter: $trimmed" "$tree"
