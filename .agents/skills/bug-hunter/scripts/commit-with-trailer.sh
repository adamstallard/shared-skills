#!/bin/sh
# Assembles a bug-hunter commit correctly, so there is no hand-typed path left
# to get wrong. Replaces constructing `git commit -m ... --trailer ...` by
# hand, which is the single most common way this skill's trailer goes missing
# (typed into the message body instead of passed as a flag — see SKILL.md
# "Pass the trailer as a flag. Never type it into the message.").
#
# This file keeps bug-hunter's interface. It passes the Bug-hunter family,
# minted by mint-trailer.sh next to this file, to the shared library
# ../../../lib/commit-trailer/commit-with-trailers.sh, which makes the commit,
# together with any other skill's --verified-value family passed here.
# BEFORE CHANGING EITHER FILE, READ that library's DECISIONS.md, and
# ../DECISIONS.md "The commit is assembled by a script, not by hand".
#
# Usage:
#   commit-with-trailer.sh -F <message-file> <bug-hunter-value> [co-authored-by]
#   commit-with-trailer.sh --verified-value <verifier> <Key> <value>... -- \
#       -F <message-file> <bug-hunter-value> [co-authored-by]
#
#   The same, with the message as two words instead of a file (still supported):
#   commit-with-trailer.sh [--verified-value ... --] <subject> <body> <bug-hunter-value> [co-authored-by]
#
#   -F <message-file> The message: its first line is the subject, the next line
#                    must be blank, and the rest is the body. Prefer it: the
#                    message is never quoted on the command line. prose's
#                    msg.txt is this file. Read by the library's
#                    --message-file option.
#
#   --verified-value <verifier> <Key> <value>
#                    Another skill's trailer, carried on the same commit (e.g.
#                    prose's `Prose:`). Repeatable. Passed through unchanged to
#                    the library, which validates it, runs <verifier> before
#                    anything is minted, and refuses the whole commit if it no
#                    longer matches. Why every installed skill's trailer goes
#                    on one commit: the library's DECISIONS.md, "Every
#                    installed skill's trailer, on one commit".
#   --               Ends the families. Required after them, so a family word
#                    that vanished (an empty unquoted variable) or a forgotten
#                    `--` is refused instead of shifting the subject, body or
#                    value into the wrong place. Allowed with no family.
#
#   subject          First line of the commit message, in the repository's own
#                    convention.
#   body             Message body. May be empty (""). Do not put trailers here.
#   bug-hunter-value Everything after "Bug-hunter: ", e.g.:
#                       "1 iteration, 1 bug fixed"
#                       "0 bugs found"
#                       "aborted after iteration 1 (...)"
#                       "skipped at triage (docs-only, no code changed)"
#                     A value starting with "skipped" (case-insensitive) is
#                     never minted — triage stopped before any loop ran, so
#                     there is no tree binding to attest to. Every other value
#                     is a claim that the loop ran over the currently staged
#                     tree, and gets a Bug-hunter-Tree trailer minted fresh,
#                     right now, against that exact tree.
#   co-authored-by   Optional. The value for a Co-Authored-By trailer, e.g.
#                       "Claude Opus 5 (1M context) <noreply@anthropic.com>"
#                     Omit (or pass whitespace) to leave that trailer out.
#
# A trailer value is one line. Surrounding whitespace on arguments 3 and 4 is
# trimmed (a heredoc's trailing newline is fine); an empty subject, an empty
# Bug-hunter value or a line break inside either value is refused before
# anything runs — git does not fold a multi-line --trailer, and the unindented
# second line ends the trailer block for every trailer after it. The minted
# Bug-hunter-Tree line is held to the same rule. A value that is exactly `--`
# or one of the library's option names (--minted, --minted-by,
# --verified-value, --co-authored-by) is also refused, as a missing argument.
# A subject that is one of those names is refused too. The only option this
# script takes is --verified-value: it adds the Bug-hunter family and the
# Co-Authored-By trailer itself, and any other word in front would be read as
# the subject.
#
# Before minting, the library runs the repository's pre-commit hook, if it
# has one, so a formatter there rewrites the staged files before the tree is
# bound, not during `git commit` after (the library's DECISIONS.md, "The
# pre-commit hook runs before anything is bound"). A skip note binds nothing
# and skips that.
#
# Exit 2 for a bad argument. Exit 1 when the shared library is missing, when
# the pre-commit hook fails or cannot be run first (an unmerged index, or a
# hook on git older than 2.36), when the commit-msg hook rejects the message
# or removes the binding, when a verifier refuses its value, or when the mint
# fails, cannot be found, or prints anything but a one-line tree binding.
# Either way, no commit is made.
#
# Stages nothing itself — what to stage is a judgement call this script does
# not make. Run your `git add` first, then call this.
#
# Example:
#   scripts/commit-with-trailer.sh -F msg.txt \
#     "1 iteration, 1 bug fixed" \
#     "Claude Opus 5 (1M context) <noreply@anthropic.com>"
#
#   With prose's trailer too (its value from prose's second `check` call on
#   the same msg.txt):
#   scripts/commit-with-trailer.sh \
#     --verified-value ~/.agents/skills/prose/scripts/verify-staged.sh \
#       Prose "✓ 4d593e935186:9138830a72a2" -- \
#     -F msg.txt "1 iteration, 1 bug fixed"
set -eu

me=commit-with-trailer.sh
usage() {
  echo "usage: commit-with-trailer.sh [--verified-value <verifier> <Key> <value>]... [--] -F <message-file> <bug-hunter-value> [co-authored-by]" >&2
  echo "       commit-with-trailer.sh [--verified-value <verifier> <Key> <value>]... [--] <subject> <body> <bug-hunter-value> [co-authored-by]" >&2
  exit 2
}
refuse() { echo "$me: $*; nothing committed" >&2; exit 2; }

# Quotes its argument as one single-quoted shell word, as the library does:
# POSIX sh has no arrays, so the families are kept as a string of these words.
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

families=''
while [ "$#" -gt 0 ]; do
  case $1 in
    --verified-value)
      [ "$#" -ge 4 ] || usage
      families="$families $(q "$1") $(q "$2") $(q "$3") $(q "$4")"
      shift 4 ;;
    --) shift; break ;;
    *)
      [ -z "$families" ] && break
      refuse "expected --verified-value or '--' after a --verified-value family, got '$1'" ;;
  esac
done

case ${1-} in --minted|--minted-by|--co-authored-by|--verified-value|--)
  refuse "'$1' in place of the subject: this script takes only --verified-value families, and adds the Bug-hunter and Co-Authored-By trailers itself" ;;
esac
# Any other dash-led word where the subject goes is taken as a misspelt file
# option (-Fmsg.txt, --message-file=msg.txt, --file), not committed as the
# subject. A real subject starting with `-` is refused with it.
case ${1-} in -F) ;; -?*)
  refuse "'$1' in place of the subject: give the message file as -F <file>, two words, or the message as <subject> <body>, with a subject that does not start with '-'" ;;
esac
[ "$#" -ge 3 ] && [ "$#" -le 4 ] || usage
# -F <file> takes the place of <subject> <body>: the same number of words, so
# the counts above hold for both forms.
from_file=n
[ "$1" = -F ] && from_file=y

# -P resolves an install symlink, so the paths below, and any error naming
# them, point into the clone.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/commit-with-trailers.sh"
if [ -z "$here" ] || [ ! -r "$lib" ]; then
  echo "commit-with-trailer.sh: the shared commit-trailer library is missing (expected at $lib); bug-hunter must be installed as a symlink into a full shared-skills clone. Nothing committed" >&2
  exit 1
fi

subject=$1 body=$2 value=$3 co=${4-}
args="--minted-by $(q "$here/mint-trailer.sh") Bug-hunter $(q "$value")$families"
[ -n "$co" ] && args="$args --co-authored-by $(q "$co")"
if [ "$from_file" = y ]; then
  # $body holds the file's path here; the library reads and checks the file.
  eval "set -- $args"
  exec sh "$lib" "$@" --message-file "$body" --
fi
eval "set -- $args"
exec sh "$lib" "$@" -- "$subject" "$body"
