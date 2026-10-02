#!/bin/sh
# Makes one commit that carries the trailers of one or more skills, so no
# skill's trailer is ever typed by hand. Each skill passes a family: a
# `<Key>: <value>` trailer, plus what ties the value to this commit — a binding
# line minted here, or for --verified-value the value itself.
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file — in
# particular "One commit, several families" and "The trailer is minted from the
# tree, not recalled by the agent".
#
# Usage:
#   commit-with-trailers.sh <family>... [--co-authored-by <value>]... -- <subject> <body>
#
# A family is one of:
#   --minted <Key> <value>
#       Bound by a `<Key>-Tree: <tree hash>` line, which mint-trailer.sh (next
#       to this file) mints from the staged index during this run.
#   --minted-by <minter> <Key> <value>
#       The same, but <minter> mints the line. <minter> is an executable, run
#       with <Key> as its only argument, that must print exactly
#       `<Key>-Tree: <hex>`.
#   --verified-value <verifier> <Key> <value>
#       Bound by the value itself, e.g. `Prose: ✓ 0123abcd4567:89abcdef0123`,
#       with no binding line. The value is accepted only if <verifier>
#       confirms it still matches. The verifier runs from the caller's
#       directory, so it sees the index about to be committed. Its only
#       argument is the trailer line `<Key>: <value>`; its stdin is the
#       message: the subject, then, if the body is not empty, a blank line and
#       the body. The message is exactly as passed here, with no trailers and
#       no trailing newline. Exit 0 means it still matches; anything else
#       refuses the whole commit. When the repository has a pre-commit hook,
#       this script runs it before the verifiers, so a hook that changes the
#       staged files makes the value stale: sign after running
#       run-pre-commit.sh (next to this file). If the commit-msg hook changes
#       the message, the verifier runs again on the changed message, minus
#       the trailer lines this script added.
#
# A value starting with "skipped" (either case of the s) is a skip note, and is
# never bound. A --minted family mints nothing for it, and a --verified-value
# family's verifier does not run for it.
#
# Argument rules:
# - Every value is one line. Surrounding whitespace on values is trimmed. The
#   subject is checked for emptiness after trimming, but passed to git as
#   given.
# - Keys hold letters, digits and dashes, and start with a letter.
# - No key may be a prefix of another, ignoring case: git treats such keys as
#   one (`Pro` and `Prose`). So `<Key>-Tree` belongs to <Key>.
# - A <minter> or <verifier> is a path containing a slash (`./verify`, not
#   `verify`).
# - --co-authored-by adds `Co-Authored-By: <value>` after the families; an
#   empty value is left out.
# - No word an option takes may be `--` or an option name (--minted,
#   --minted-by, --verified-value, --co-authored-by). That is refused as a
#   missing argument, not accepted as a value.
# - The `--` before <subject> is required.
#
# Order of steps. A failure at any step commits nothing:
# 1. validate every argument (exit 2)
# 2. check that every minter and verifier exists (exit 1)
# 3. only if a value is bound and the repository has a pre-commit or
#    commit-msg hook: run pre-commit now, through commit-with-hooks.sh (exit 1
#    if it fails, or cannot be run first: an unmerged index, git < 2.36)
# 4. run every verifier (exit 1 on a refusal)
# 5. run every mint (exit 1 on failure, or on output other than a one-line
#    binding)
# 6. git commit. On the hook path (step 3), commit-with-hooks.sh runs
#    commit-msg itself and commits with --no-verify, so no hook runs twice.
# Stages nothing: run your `git add` first.
set -eu

me=commit-with-trailers
lib_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P)

usage() {
  echo "usage: commit-with-trailers.sh <family>... [--co-authored-by <value>]... -- <subject> <body>" >&2
  echo "  family: --minted <Key> <value> | --minted-by <minter> <Key> <value> | --verified-value <verifier> <Key> <value>" >&2
  exit 2
}
refuse() { echo "$me: $*; nothing committed" >&2; exit 2; }
fail() { echo "$me: $*; nothing committed" >&2; exit 1; }

trim() {
  v=$1
  while :; do case $v in [[:space:]]*) v=${v#?} ;; *) break ;; esac; done
  while :; do case $v in *[[:space:]]) v=${v%?} ;; *) break ;; esac; done
  printf '%s' "$v"
}

# Quotes its argument as one single-quoted shell word. POSIX sh has no arrays,
# so the lists below are strings of these words, replayed with `eval set --`.
q() {
  r='' s=$1
  while :; do
    case $s in
      *\'*) r="$r${s%%\'*}'\\''"; s=${s#*\'} ;;
      *) break ;;
    esac
  done
  printf "'%s%s'" "$r" "$s"
}

nl=$(printf '\nx'); nl=${nl%x}
one_line() { # <what> <value>
  case $2 in *"$nl"*) refuse "$1 contains a line break; a trailer is one line" ;; esac
}
is_skip() { case $1 in [Ss]kipped*) return 0 ;; esac; return 1; }

# -- 1. parse and validate; nothing below this section runs on a bad argument

families=''   # four words per family: kind tool key value
binds=n       # y once any value is not a skip note
keys=' '      # every key so far, lowercased, space-separated
co_authors='' # quoted --trailer words
nfam=0

add_key() {
  k=$1
  case $k in
    [A-Za-z]*) ;;
    *) refuse "trailer key '$k' must start with a letter" ;;
  esac
  case $k in *[!A-Za-z0-9-]*) refuse "trailer key '$k' may hold only letters, digits and dashes" ;; esac
  lk=$(printf '%s' "$k" | tr '[:upper:]' '[:lower:]')
  # git treats two keys as one when either is a prefix of the other, with or
  # without a dash. Refusing that also keeps each family's key clear of every
  # other family's <Key>-* binding.
  for other in $keys; do
    case $lk in "$other"*) collides=y ;; *) collides=n ;; esac
    case $other in "$lk"*) collides=y ;; esac
    [ "$collides" = n ] ||
      refuse "trailer key '$k' collides with another family's key: git treats two keys as one when either is a prefix of the other"
  done
  keys="$keys$lk "
}

# takes <n> <option> <words...>: checks that <option> got its <n> words, and
# that none of them is `--` or another option's name.
#
# Why: an empty, unquoted variable disappears from the command line. Without
# this check, the option would take the next word as its value, and the commit
# would land with that word as a trailer value, validly bound, exit 0.
takes() {
  n=$1 opt=$2; shift 2
  [ "$#" -ge "$n" ] || usage
  while [ "$n" -gt 0 ]; do
    case $1 in --|--minted|--minted-by|--verified-value|--co-authored-by)
      refuse "$opt is missing an argument: '$1' was taken as one of them" ;;
    esac
    shift; n=$((n - 1))
  done
}

while [ "$#" -gt 0 ]; do
  case $1 in
    --minted)
      takes 2 "$@"
      kind=minted tool="$lib_dir/mint-trailer.sh" key=$2 value=$3
      shift 3 ;;
    --minted-by)
      takes 3 "$@"
      kind=minted-by tool=$2 key=$3 value=$4
      shift 4 ;;
    --verified-value)
      takes 3 "$@"
      kind=verified-value tool=$2 key=$3 value=$4
      shift 4 ;;
    --co-authored-by)
      takes 1 "$@"
      co=$(trim "$2"); shift 2
      one_line "the Co-Authored-By value" "$co"
      [ -n "$co" ] && co_authors="$co_authors --trailer $(q "Co-Authored-By: $co")"
      continue ;;
    --) shift; break ;;
    -*) echo "$me: unknown option $1" >&2; usage ;;
    # The `--` is required so that a missing or split word shows up here, as
    # a stray word, and is refused. Without it, an empty unquoted value plus a
    # two-word unquoted subject would parse cleanly: the subject's first word
    # would become the value, and its second word the subject.
    *) refuse "expected an option or '--' before the subject, got '$1'" ;;
  esac
  add_key "$key"
  # A bare name would be checked in the current directory but run from PATH,
  # so the file that passed the check might not be the one that runs.
  case $kind:$tool in minted:*|*/*) ;; *) refuse "the $key tool '$tool' must be a path (e.g. ./$tool), not a bare name" ;; esac
  value=$(trim "$value")
  [ -n "$value" ] || refuse "the $key value is empty"
  one_line "the $key value" "$value"
  families="$families $(q "$kind") $(q "$tool") $(q "$key") $(q "$value")"
  is_skip "$value" || binds=y
  nfam=$((nfam + 1))
done

[ "$#" -eq 2 ] || usage
[ "$nfam" -gt 0 ] || refuse "no trailer family was given; this script exists to add one"
subject=$1
body=$2
# Why an empty subject is refused: with an empty body as well, the trailers
# would become the message's first paragraph, which git never reads as
# trailers. git itself does not refuse a trailers-only message as empty.
[ -n "$(trim "$subject")" ] || refuse "the subject is empty"

# -- 2. every tool exists

eval "set -- $families"
while [ "$#" -gt 0 ]; do
  kind=$1 tool=$2 key=$3
  shift 4
  if [ "$kind" = minted ]; then
    [ -r "$tool" ] || fail "mint-trailer.sh is missing from the library ($tool)"
  else
    case $kind in verified-value) role=verifier ;; *) role=minter ;; esac
    [ -f "$tool" ] && [ -x "$tool" ] || fail "the $key $role is not an executable file ($tool)"
  fi
done

# -- 3. hooks. Only a repository that has one takes the hook path, in
# commit-with-hooks.sh; everything else commits as plain `git commit` does.

# Whether git would run hook <name>: a file at hooks/<name> (core.hooksPath
# honoured), or one defined in config (hook.<n>.event, git 2.54).
has_hook() {
  h=$(git rev-parse --git-path "hooks/$1") || return 1
  { [ -f "$h" ] && [ -x "$h" ]; } ||
    git config --get-regexp '^hook\..*\.event$' "^$1\$" >/dev/null
}

with_hooks=n
stale_why='' # set by the hook path when pre-commit changed the staged files
if [ "$binds" = y ] && { has_hook pre-commit || has_hook commit-msg; }; then
  [ -r "$lib_dir/commit-with-hooks.sh" ] ||
    fail "commit-with-hooks.sh is missing from the library ($lib_dir/commit-with-hooks.sh)"
  with_hooks=y
  . "$lib_dir/commit-with-hooks.sh"
  hooks_before_binding
fi

# -- 4. verifiers: a binding minted earlier must still match

message=$subject
[ -n "$body" ] && message="$subject$nl$nl$body"

# verify <message> <why it may be stale, or empty>
verify() {
  # Named before the replay: `set --` below holds the families and nothing
  # else, so $1 and $2 are never the message and reason.
  verify_message=$1 verify_why=$2
  eval "set -- $families"
  while [ "$#" -gt 0 ]; do
    kind=$1 tool=$2 key=$3 value=$4
    shift 4
    is_skip "$value" && continue
    # The value is its own binding: the verifier checks the trailer line.
    [ "$kind" = verified-value ] || continue
    line="$key: $value"
    printf '%s' "$verify_message" | "$tool" "$line" >&2 && continue
    [ -n "$verify_why" ] &&
      fail "the $key binding no longer matches the staged tree and message (its verifier refused: $line): $verify_why after the value was made; review what the hook changed, then make the $key value again and commit"
    fail "the $key binding no longer matches the staged tree and message (its verifier refused: $line); re-mint it after the final \`git add\`"
  done
}
verify "$message" "$stale_why"

# -- 5. mints, and the argument list for git

args="-m $(q "$subject")"
[ -n "$body" ] && args="$args -m $(q "$body")"

eval "set -- $families"
while [ "$#" -gt 0 ]; do
  kind=$1 tool=$2 key=$3 value=$4
  shift 4
  args="$args --trailer $(q "$key: $value")"
  is_skip "$value" && continue
  case $kind in
    verified-value) continue ;;
    # Keep each mint in an assignment of its own. Inside another command's
    # arguments, a failing $(...) does not trip `set -e`.
    minted) tree=$(sh "$tool" "$key") || fail "mint-trailer.sh failed for $key" ;;
    *) tree=$("$tool" "$key") || fail "the $key minter failed ($tool)" ;;
  esac
  # A zero exit is not enough. git can succeed while writing to stderr, and a
  # minter that captures stderr too returns several lines with the hash last.
  case $tree in *"$nl"*)
    echo "$me: the $key minter printed more than one line (git wrote to stderr during write-tree?); nothing committed:" >&2
    printf '%s\n' "$tree" >&2
    exit 1 ;;
  esac
  printf '%s' "$tree" | grep -Eq "^$key-Tree: ([0-9a-f]{40}|[0-9a-f]{64})\$" ||
    fail "the $key minter printed something other than a $key-Tree binding: $tree"
  args="$args --trailer $(q "$tree")"
done
args="$args$co_authors"

# Pins git's trailer settings for this one command, so every trailer passed
# here lands, in order.
#
# Don't remove a pin. What each one prevents:
# - trailer.ifexists=add: git matches trailer keys by prefix, so it treats
#   `Bug-hunter-Tree` as a repeat of `Bug-hunter`. Any other value, including
#   git's default, can replace or drop a binding.
# - trailer.ifmissing=add: with doNothing, no trailer lands at all.
# - trailer.where=end: with start, the trailers land in reverse order.
# Each case has a test in CommitFamiliesTests.
if [ "$with_hooks" = y ]; then hooks_commit; fi # same pins; never returns
eval "set -- $args"
exec git -c trailer.ifexists=add -c trailer.ifmissing=add \
    -c trailer.separators=: -c trailer.where=end commit "$@"
