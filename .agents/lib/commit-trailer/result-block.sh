#!/bin/sh
# Prints the result block a skill ends with when its caller makes the commit:
# the trailer lines to pass through, then the open decisions, numbered and
# counted. This file is the format's one definition; no skill types the block.
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file — in
# particular "The result block is printed by a script".
#
# Usage:
#   result-block.sh <skill> [--decisions <file>] -- <trailer line>...
#
#   skill        The skill's name, as in its marker lines. Letters, digits and
#                dashes.
#   --decisions  A file holding one open decision per line, or `-` for stdin.
#                Blank lines are skipped. Without it, nothing is open.
#   trailer line A whole `Key: value` line, passed through as is. At least one.
#
# Prints, and only once every check has passed:
#
#   === <skill> result ===
#   <trailer line>...
#   === <skill> open decisions: <N> ===
#   ① <decision>
#   ...
#   === end <skill> ===
#
# Checks:
# - A key starts with a letter and holds letters, digits and dashes; its value
#   is not empty. Surrounding whitespace on a trailer line is trimmed.
# - A trailer line or decision holding a line break is refused: git does not
#   fold a multi-line trailer, and a caller reads the block line by line.
# - A decision starting `===` is refused: the caller would read it as a marker.
# - A decisions file that is missing or unreadable is an error. Read as empty,
#   it would tell the caller nothing is open.
#
# Exit 2 for a bad argument or line, 1 for an unreadable decisions file. On
# either, nothing is printed to stdout.
set -eu

me=result-block

usage() {
  echo "usage: result-block.sh <skill> [--decisions <file>] -- <trailer line>..." >&2
  exit 2
}
refuse() { echo "$me: $*; no block printed" >&2; exit 2; }
fail() { echo "$me: $*; no block printed" >&2; exit 1; }

trim() {
  v=$1
  while :; do case $v in [[:space:]]*) v=${v#?} ;; *) break ;; esac; done
  while :; do case $v in *[[:space:]]) v=${v%?} ;; *) break ;; esac; done
  printf '%s' "$v"
}

nl=$(printf '\nx'); nl=${nl%x}

[ "$#" -ge 1 ] || usage
skill=$1; shift
case $skill in
  [A-Za-z]*) ;;
  *) refuse "the skill name '$skill' must start with a letter" ;;
esac
case $skill in *[!A-Za-z0-9-]*) refuse "the skill name '$skill' may hold only letters, digits and dashes" ;; esac

decisions=''
while [ "$#" -gt 0 ]; do
  case $1 in
    --decisions)
      [ "$#" -ge 2 ] || usage
      # An empty unquoted file variable vanishes and leaves `--` here. Named
      # as a missing file, it is not reported as a stray trailer line.
      case $2 in --|--decisions) refuse "--decisions is missing its file: '$2' was taken as one" ;; esac
      [ -n "$2" ] || refuse "--decisions was given an empty file name"
      decisions=$2
      shift 2 ;;
    --) shift; break ;;
    *) refuse "expected --decisions or '--' before the trailer lines, got '$1'" ;;
  esac
done
[ "$#" -gt 0 ] || refuse "no trailer line was given; the block exists to carry one"

out="=== $skill result ==="
for line in "$@"; do
  line=$(trim "$line")
  case $line in *"$nl"*) refuse "a trailer line contains a line break; a trailer is one line" ;; esac
  key=${line%%:*}
  case $line in
    *:*) ;;
    *) refuse "the trailer line '$line' is not 'Key: value'" ;;
  esac
  case $key in
    [A-Za-z]*) ;;
    *) refuse "the trailer key in '$line' must start with a letter" ;;
  esac
  case $key in *[!A-Za-z0-9-]*) refuse "the trailer key in '$line' may hold only letters, digits and dashes" ;; esac
  [ -n "$(trim "${line#*:}")" ] || refuse "the trailer line '$line' has an empty value"
  out="$out$nl$line"
done

# The number is added here, so the agent writes only each decision's text.
mark() {
  case $1 in
    1) printf '①' ;; 2) printf '②' ;; 3) printf '③' ;; 4) printf '④' ;;
    5) printf '⑤' ;; 6) printf '⑥' ;; 7) printf '⑦' ;; 8) printf '⑧' ;;
    9) printf '⑨' ;; 10) printf '⑩' ;; 11) printf '⑪' ;; 12) printf '⑫' ;;
    13) printf '⑬' ;; 14) printf '⑭' ;; 15) printf '⑮' ;; 16) printf '⑯' ;;
    17) printf '⑰' ;; 18) printf '⑱' ;; 19) printf '⑲' ;; 20) printf '⑳' ;;
    *) printf '(%s)' "$1" ;;
  esac
}

n=0
listed=''
read_decisions() {
  # `|| [ -n "$d" ]` keeps a last line that has no newline.
  while IFS= read -r d || [ -n "$d" ]; do
    d=$(trim "$d")
    [ -n "$d" ] || continue
    case $d in ===*) refuse "the decision '$d' starts with '===', which a caller reads as a marker" ;; esac
    n=$((n + 1))
    listed="$listed$nl$(mark "$n") $d"
  done
}
if [ "$decisions" = - ]; then
  read_decisions
elif [ -n "$decisions" ]; then
  # Checked first: a redirection that fails on a function call exits the shell
  # under some shells and not others, and neither says which file.
  [ -f "$decisions" ] && [ -r "$decisions" ] ||
    fail "the decisions file '$decisions' is missing or unreadable"
  read_decisions <"$decisions"
fi

out="$out$nl=== $skill open decisions: $n ===$listed$nl=== end $skill ==="
printf '%s\n' "$out"
