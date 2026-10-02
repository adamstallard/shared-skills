#!/bin/sh
# bug-hunter's hook: reports commits that land without a Bug-hunter: trailer,
# or with one whose Bug-hunter-Tree binding does not match what landed.
#
# Usage: check-commit-trailer.sh [--host <platform>]
#
# The check itself is shared — ../../../lib/commit-trailer/check-commit-trailer.sh,
# with its own DECISIONS.md. This file configures it for bug-hunter and sources
# it, so $0 stays this file and the submodule walk comes back through here.
# The report's wording is in hook-report.sh.

# -P so the paths below, and any error naming them, are the clone's rather
# than an install symlink's.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/check-commit-trailer.sh"

if [ -z "$here" ] || [ ! -r "$lib" ]; then
  # Silence here would be a hook that is broken and looks like it is working.
  msg="bug-hunter: the shared commit-trailer library is missing (expected at $lib), so commits are not being checked. bug-hunter must be installed as a symlink into a full shared-skills clone; run: python3 ~/.agents/skills/manage-skills/scripts/skills.py doctor"
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*)
      printf '{"additional_context":"%s"}\n' "$(printf '%s' "$msg" | LC_ALL=C sed 's/["\\]/ /g')"
      exit 0 ;;
  esac
  printf '%s\n' "$msg" >&2
  exit 2
fi

COMMIT_TRAILER_SKILL=bug-hunter
COMMIT_TRAILER_KEY=Bug-hunter
COMMIT_TRAILER_REPORT="$here/hook-report.sh"
. "$lib"
