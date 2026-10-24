#!/bin/sh
# Makes a bug-hunter commit, so no agent assembles `git commit -m ...
# --trailer ...` by hand. Typing that command by hand is the most common way
# this skill's trailer goes missing: the `Bug-hunter:` line ends up in the
# message body instead of being passed as a flag (SKILL.md, Step 9, "Commit
# through the script.").
#
# This script is a thin wrapper. The commit itself is made by the shared
# library ../../../lib/commit-trailer/commit-with-trailers.sh, which takes
# generic "families" (a family is an option such as --minted-by or
# --verified-value plus the words that option takes, and adds one trailer).
# This script keeps bug-hunter's own shorter interface, shown under Usage,
# because bug-hunter's SKILL.md Step 9, reference.md and the report printed by
# bug-hunter's hook (hook-report.sh) all tell agents to run it in that form.
# It turns those arguments into a --minted-by family for the Bug-hunter
# trailer, naming mint-trailer.sh beside this file as the minter that binds
# the trailer to the staged tree. It passes that family to the library, with
# any --verified-value families given here.
#
# BEFORE CHANGING THIS SCRIPT OR THE LIBRARY, READ the library's decision
# record, ../../../lib/commit-trailer/DECISIONS.md, and this skill's
# ../DECISIONS.md, "The commit is assembled by a script, not by hand".
#
# Usage:
#   commit-with-trailer.sh -F <message-file> <bug-hunter-value> [co-authored-by]
#   commit-with-trailer.sh --verified-value <verifier> <Key> <value> \
#       [--verified-value <verifier> <Key> <value>]... -- \
#       -F <message-file> <bug-hunter-value> [co-authored-by]
#   (each family is exactly four words; repeat the whole family for each
#   skill)
#
#   The same, with the message as two shell arguments instead of a file:
#   commit-with-trailer.sh [--verified-value ... --] <subject> <body> <bug-hunter-value> [co-authored-by]
#
#   -F <message-file> The commit message: its first line is the subject, the
#                    next line must be blank, and the rest is the body. Prefer
#                    it to <subject> <body>: the message never has to be quoted
#                    on the command line. prose signs this same file. This
#                    script passes the path on as the library's --message-file
#                    option, and the library reads the file and checks its
#                    layout.
#
#   --verified-value <verifier> <Key> <value>
#                    Another skill's trailer, carried on the same commit, such
#                    as prose's `Prose:`. Repeatable. This script passes the
#                    four words to the library unchanged. Before the commit,
#                    the library runs <verifier> on the staged files and the
#                    message, and refuses the whole commit if the verifier
#                    says the value no longer matches them. Every installed
#                    skill's trailer goes on one commit: the library's
#                    DECISIONS.md, "Every installed skill's trailer, on one
#                    commit", says why.
#   --               Ends the families. Required after them, so that a missing
#                    word in a family (an empty unquoted variable vanishes
#                    from the command line) is refused instead of shifting the
#                    subject, body or value into the wrong place: the family
#                    then takes the following word, such as the `--`, as its
#                    last, and the loop below refuses the word after that,
#                    unless that word is `--` or `--verified-value`. In that
#                    case the library refuses instead, because the
#                    swallowed `--` is now one of the family's words. With no
#                    family it may be given or left out, which is why usage()
#                    prints it as [--].
#
#   subject          First line of the commit message, in the repository's own
#                    convention.
#   body             Message body. May be empty (""). Do not put trailers here.
#   bug-hunter-value Everything after "Bug-hunter: ", e.g.:
#                       "1 iteration, 1 bug fixed"
#                       "0 bugs found"
#                       "aborted after iteration 1 (...)"
#                       "skipped at triage (docs-only, no code changed)"
#                     A value starting with "skipped" (either case of the s)
#                     gets no tree binding: triage stopped before any loop
#                     ran, so there is nothing to attest to. Every other value
#                     claims the loop ran over the staged files, and gets a
#                     Bug-hunter-Tree trailer: the hash of the git tree object
#                     for the files staged when the commit is made.
#   co-authored-by   Optional. The value for a Co-Authored-By trailer, e.g.
#                       "<Co-Authored-By value from your attribution instructions>"
#                     Your host may give you a co-author line for commits; in
#                     Claude Code it is in the attribution instructions, and
#                     names the current model. Leave the argument out if you
#                     have none.
#
# Checks this script makes, each refused with exit 2 before anything runs:
# - after --verified-value families, the next word must be `--` or another
#   family;
# - the subject (the first word after the families) must not be `--` or an
#   option name (--minted, --minted-by, --verified-value, --co-authored-by);
#   this script takes no option but --verified-value, and adds the Bug-hunter
#   and Co-Authored-By trailers itself;
# - the subject must not start with `-` at all, unless it is exactly `-F`, so
#   a misspelt file option (-Fmsg.txt, --message-file=msg.txt) is not committed
#   as the subject. This script cannot tell such a typo from a real subject
#   that starts with `-`, so it refuses both;
# - three or four words must follow the families.
#
# Checks the library makes, also with exit 2 before anything runs (see its
# header for the full list):
# - it trims surrounding whitespace from every trailer value, so a value
#   that ends in a newline, such as one read from a heredoc, is fine. It
#   leaves out a Co-Authored-By value that is empty after trimming, so
#   passing only whitespace omits that trailer;
# - it refuses an empty subject, an empty Bug-hunter value, and a line break
#   inside any trailer value. git reads trailers only from a block of
#   `Key: value` lines at the end of the message. git does not indent the
#   second line of a multi-line --trailer value, and that unindented line
#   would end the block, so git would no longer read the trailers after it as
#   trailers;
# - where an option's argument should be, it refuses `--` or an option name
#   (--minted, --minted-by, --verified-value, --co-authored-by,
#   --message-file): it takes that word as a sign the argument is missing.
#   Accepted as the argument, it would shift every later word into the wrong
#   place.
#
# The pre-commit hook. The library binds the commit's values (it mints the
# Bug-hunter-Tree line and runs each verifier) just before calling
# `git commit`, and git normally runs the repository's pre-commit hook inside
# `git commit`, after that binding. A formatter in the hook could then change
# the staged files, so that the commit would no longer match its binding.
#
# The library treats a value starting with "skipped" in any family as a skip
# note, whichever skill passed it, and a skip note binds nothing. A commit
# binds something when any value it carries, the Bug-hunter value or a
# --verified-value family's, is not a skip note; that decides whether the
# library runs the hooks early.
#
# When the commit binds something and the repository has a pre-commit or
# commit-msg hook, the library takes over running them. It runs the
# pre-commit hook, if there is one, before binding. It runs commit-msg
# itself, so that it can check the binding again if that hook changes the
# message. It then commits with `git commit --no-verify`, so that git runs
# neither hook a second time. With nothing to bind, git runs the hooks during
# `git commit` as usual. Why: the library's DECISIONS.md, "The pre-commit
# hook runs before anything is bound".
#
# Running a hook outside `git commit` needs `git hook run`, which arrived in
# git 2.36. On older git, when the commit binds something:
# - with a pre-commit hook, the library refuses with exit 1;
# - with only a commit-msg hook, it commits without --no-verify, and git runs
#   that hook during `git commit`. Nothing then re-checks the binding before
#   the commit lands: if that hook changed the message, a value bound to the
#   message, such as prose's, would no longer match it.
#
# Exit 2 for a bad argument. Exit 1 when the shared library is missing, when
# the pre-commit hook fails or cannot be run first (an unmerged index, or a
# hook on git older than 2.36), when the commit-msg hook rejects the message
# or removes the binding, when a verifier refuses its value, or when the mint
# fails, cannot be found, or prints anything but a one-line tree binding.
# Whichever of the two codes it exits with, no commit is made.
#
# Stages nothing itself: what to stage is a judgement call this script does
# not make. Run your `git add` first, then call this.
#
# Examples, with the script's path shortened: run it from inside the project,
# with the path written out in full, as SKILL.md Step 9 says.
#   scripts/commit-with-trailer.sh -F msg.txt \
#     "1 iteration, 1 bug fixed" \
#     "<Co-Authored-By value from your attribution instructions>"
#
#   With prose's trailer too. The Prose value here is a sample: pass the one
#   prose's second `check` call printed for the same msg.txt. <prose scripts>
#   is the scripts directory prose's SKILL.md names, wherever prose is
#   installed:
#   scripts/commit-with-trailer.sh \
#     --verified-value <prose scripts>/verify-staged.sh \
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
