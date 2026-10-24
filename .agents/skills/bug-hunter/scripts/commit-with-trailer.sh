#!/bin/sh
# Makes a bug-hunter commit, so no agent assembles `git commit -m ...
# --trailer ...` by hand. Typing that command by hand is the most common way
# this skill's trailer goes missing: the `Bug-hunter:` line ends up in the
# message body instead of being passed as a flag (SKILL.md, Step 9, "Commit
# through the script.").
#
# This script is a thin wrapper. The commit itself is made by the shared
# library ../../../lib/commit-trailer/commit-with-trailers.sh (relative to
# this file's real directory; see the comment above `here=` below), which
# takes generic "families". A family is an option such as --minted-by or
# --verified-value plus the words that option takes. Each family adds one
# skill's trailer; a --minted-by family also adds its `<Key>-Tree` binding
# line.
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
#                    next line must be blank, and the rest is the body. A file
#                    holding only a subject line is accepted. Prefer -F to
#                    <subject> <body>: the message never has to be quoted on
#                    the command line. prose's trailer value is bound to this
#                    file's text, so pass the file prose checked. This script
#                    passes the path on as the library's --message-file
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
#   --               Ends the families. The brackets in usage()'s [--] mark
#                    it optional, but it may be left out only when no family
#                    is given. It is required after a family so that a family
#                    missing a word is refused rather than committed with
#                    words in the wrong places. A word goes
#                    missing when an empty unquoted variable in the caller's
#                    command vanishes; the family then takes the following
#                    word, often the `--`, in its place. For example, if the
#                    caller wrote --verified-value V Prose $VALUE and $VALUE
#                    was empty, this script receives
#                      --verified-value V Prose -- -F msg.txt "0 bugs found"
#                    and the loop below reads `--verified-value`, `V`,
#                    `Prose` and `--` as the family's four words. It then
#                    expects `--` or another family, sees `-F`, and refuses.
#
#   subject          First line of the commit message, in the repository's own
#                    convention.
#   body             Message body. May be empty (""). Do not put trailers here.
#   bug-hunter-value Everything after "Bug-hunter: ", e.g.:
#                       "1 iteration, 1 bug fixed"
#                       "0 bugs found"
#                       "aborted after iteration 1 (...)"
#                       "skipped at triage (docs-only, no code changed)"
#                     The library gives no tree binding to a value starting
#                     with "skipped" or "Skipped": triage, bug-hunter's first
#                     step,
#                     decided not to hunt, so its find-prove-fix loop never
#                     ran and there is nothing to attest to. Every other
#                     value claims the loop ran over the staged files, and
#                     gets a Bug-hunter-Tree trailer: the hash of the git tree
#                     object for the files staged when the commit is made.
#   co-authored-by   Optional. The value for a Co-Authored-By trailer. As a
#                    placeholder for it, SKILL.md writes
#                       "<Co-Authored-By value from your attribution instructions>"
#                     Your host may give you a co-author line for commits; in
#                     Claude Code it is in the attribution instructions, and
#                     names the current model. Leave the argument out if you
#                     have none.
#
# Checks this script makes, each refused with exit 2 before anything runs:
# - after --verified-value families, the next word must be `--` or another
#   family;
# - the first word after the families, which is `-F` or the subject, must not
#   be `--` or one of the library's option names: --minted-by,
#   --verified-value, --co-authored-by, or --minted (a library family this
#   script never passes). A `--` lands here when a caller writes `-- --`: the
#   first ends the families, and the second is this word. This check only
#   gives a clearer message than the next bullet's check, which would refuse
#   all of these anyway, as words starting with `-`. Its message says that
#   this script takes only --verified-value families, and adds the Bug-hunter
#   and Co-Authored-By trailers itself;
# - that word must not be `-` followed by more characters, unless it is
#   exactly `-F`, so a misspelt file option (-Fmsg.txt,
#   --message-file=msg.txt) is not committed as the subject. This script
#   cannot tell such a typo from a real subject that starts with `-`, so it
#   refuses both. A lone `-` is let through as a subject;
# - three or four words must follow the families: `-F <file>` or
#   `<subject> <body>` (two words either way), the Bug-hunter value, and the
#   optional co-authored-by value.
#
# The library trims surrounding whitespace from every trailer value, so a
# value that ends in a newline, such as one read from a heredoc, is fine. It
# leaves out a Co-Authored-By value that is empty after trimming, so passing
# only whitespace omits that trailer.
#
# Checks the library makes, also refusing with exit 2 before anything runs
# (its header has the full list):
# - it refuses an empty subject, an empty Bug-hunter value, and a line break
#   inside any trailer value (why a line break: below the list);
# - where an option's argument should be, it refuses `--` or an option name
#   (--minted, --minted-by, --verified-value, --co-authored-by,
#   --message-file). Through this script, the Bug-hunter value, the
#   co-authored-by value and the -F path each become an option's argument on
#   the library's command line, so a caller who passes one of them as exactly
#   `--` or an option name is refused. That is intended: no real value or path
#   is either word. The library's header gives its own reason for the check.
#
# Why a line break in a trailer value is refused: git reads trailers only
# from a block of `Key: value` lines at the end of the message. A line that
# continues a value must be indented, and git does not indent the second
# line of a multi-line --trailer value. That unindented line ends the block,
# so git would no longer read the trailers after it as trailers.
#
# Skip notes. The library treats a value starting with "skipped" or
# "Skipped" as a skip note, in any family: the Bug-hunter family this script
# builds, or a --verified-value family. A skip note binds nothing:
# no tree is minted for it, and its verifier does not run. A commit binds
# something when the Bug-hunter value or any --verified-value family's value
# is not a skip note: one non-skip value is enough. The Co-Authored-By value
# never binds. Whether a commit binds something decides whether the library
# runs the hooks itself: see the next paragraph.
#
# The pre-commit hook. The library binds the commit's values (it mints the
# Bug-hunter-Tree line and runs each verifier) just before calling
# `git commit`, and git normally runs the repository's pre-commit hook inside
# `git commit`, after that binding. A formatter in the hook could then change
# the staged files, so that the commit would no longer match its binding.
#
# When the commit binds something and the repository has a pre-commit or
# commit-msg hook, the library takes over running them. It runs the pre-commit
# hook, if there is one, before binding, unless a recorded earlier pass of the
# hook matches. Each pass is recorded in the git directory with the staged tree
# and the state the hook ran in: HEAD, the hook file, git config and unstaged
# changes. A pass matches when all of these are the same now. The record is
# written by run-pre-commit.sh, a second script in the library's directory that
# commit-with-trailers.sh uses to run the hook; prose's calls run the hook
# through it too, so a commit made right after them finds the pass recorded and
# does not run the hook twice. After binding, the library runs commit-msg
# itself, on the final message with the trailers in it. If that hook changes
# the message, the library runs the verifiers again on the changed message, and
# refuses if the hook removed or changed a trailer line the library added. It
# then commits with `git commit --no-verify`, so that git runs neither hook a
# second time. With nothing to bind, git runs the hooks during `git commit` as
# usual. Why: the library's DECISIONS.md, "The pre-commit hook runs before
# anything is bound".
#
# When it takes over, the library first writes the staged tree
# (`git write-tree`) as a baseline, then runs the pre-commit hook (if there is
# one, and it has not already passed), then writes the tree again and
# compares. If the hook changed the staged tree, as a formatter that restages
# its rewrites does, the library says so, and then:
# - when bug-hunter's value is the only one that binds (it is not a skip note,
#   and every other skill's value, if any was passed, is a skip note), the
#   commit goes ahead with the hook's staged changes, and the Bug-hunter-Tree
#   line is minted from the changed files. That is intended: the line records
#   which tree landed, not that the hunt saw the hook's changes;
# - with another skill's value bound, such as prose's, that value was made
#   from the files before the change, so its verifier refuses and the commit
#   is not made. The library's message says the hook changed the files.
# A hook that changes only the working tree changes nothing staged, and its
# edits are not committed. After prose's calls the hook normally does not run
# here at all: they recorded its pass, so it runs only when the staged files
# or their state changed after those calls.
#
# Since the library writes the tree first whenever it takes over, even for a
# commit-msg hook alone, an unmerged index makes it refuse with exit 1 before
# it runs `git commit`: git cannot write a tree from an unmerged index. (When
# the library does not take over, git itself refuses such a commit, with its
# own exit code.)
#
# Running a hook outside `git commit` needs `git hook run`, which arrived in
# git 2.36. On older git, when the commit binds something:
# - with a pre-commit hook, the library refuses with exit 1;
# - with only a commit-msg hook, it commits without --no-verify, and git runs
#   that hook during `git commit`. Nothing then re-checks the binding before
#   the commit lands: if that hook changed the message, a value bound to the
#   message, such as prose's, would no longer match it.
#
# Exit codes. 0 means the commit was made; any other code means no commit
# was made.
# - 2: a bad argument.
# - 1: any of these:
#   - the shared library is missing;
#   - the pre-commit hook fails;
#   - the library cannot take over running the hooks, when it needs to:
#     on git older than 2.36 with a pre-commit hook, or with an unmerged
#     index (both explained above). On older git with only a commit-msg
#     hook, it commits instead;
#   - the commit-msg hook rejects the message, or removes a trailer line the
#     library added, such as Bug-hunter-Tree;
#   - a verifier refuses its value, including when the library checks it
#     again after the commit-msg hook changed the message;
#   - the mint fails, cannot be found, or prints anything but a one-line
#     tree binding.
# - git's own code: the library runs `git commit` last, so when git refuses
#   the commit (with nothing staged, or a hook that git itself ran fails), its
#   exit code is passed on. That code is usually 1 as well, so a caller cannot
#   tell git's refusal from the library's by the code; treat any non-zero code
#   as "no commit", and read the message for the reason.
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

# Skills are installed as links: a skills folder, such as ~/.claude/skills,
# which the manage-skills skill fills, holds a link to each skill's directory
# inside a clone of the shared-skills repository. `cd -P` into this file's
# directory, which is scripts/ inside the skill's linked directory, resolves
# every link along the path, that directory link included, so the paths built
# from $here below ($lib, and the mint-trailer.sh path), and any error naming
# them, point into the clone. That matters because the library is found by a
# path relative to this file's real location, and the library exists only
# inside the clone. If only this file were linked, not its directory, the link
# would not be resolved: `dirname "$0"` gives the directory the link sits in,
# and `cd -P` resolves links among directories, not a link to a file. $here
# would then be the link's directory, the library would not be found there, and
# the script would exit 1 saying so. `CDPATH=` stops cd from finding the
# directory through $CDPATH: when cd does, it prints the path, and that output
# would be captured into $here along with pwd -P's. If cd fails, $here is left
# empty, and the check below reports the library missing.
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
