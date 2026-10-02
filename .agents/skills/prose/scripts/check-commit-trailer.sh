#!/bin/sh
# prose's commit hook. It reports each commit that lands without a Prose:
# trailer, or with one that fails verification: a `Prose: ✓ <tree>:<message>`
# value whose halves no longer match the commit, or a value of any other form.
#
# Usage: check-commit-trailer.sh [--host <platform>]
#
# The check itself is shared — ../../../lib/commit-trailer/check-commit-trailer.sh,
# with its own DECISIONS.md. This file configures it for prose and sources it.
# Sourcing keeps $0 pointing at this file, so when the library re-runs the
# check in each submodule, it runs this file again. The report's wording, and
# the verification the library calls back into, are in hook-report.sh.

# -P so the paths below, and any error naming them, are the clone's rather
# than an install symlink's.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/check-commit-trailer.sh"

if [ -z "$here" ] || [ ! -r "$lib" ]; then
  # Exiting silently here would leave a broken hook that looks like it works.
  msg="prose: the shared commit-trailer library is missing (expected at $lib), so commits are not being checked. prose must be installed as a symlink into a full shared-skills clone; run: python3 ~/.agents/skills/manage-skills/scripts/skills.py doctor"
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*)
      printf '{"additional_context":"%s"}\n' "$(printf '%s' "$msg" | LC_ALL=C sed 's/["\\]/ /g')"
      exit 0 ;;
  esac
  printf '%s\n' "$msg" >&2
  exit 2
fi

PROSE_SCRIPTS=$here
COMMIT_TRAILER_SKILL=prose
COMMIT_TRAILER_KEY=Prose
COMMIT_TRAILER_REPORT="$here/hook-report.sh"
. "$lib"
