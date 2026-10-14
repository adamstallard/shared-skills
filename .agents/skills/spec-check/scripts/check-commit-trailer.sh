#!/bin/sh
# spec-check's commit hook. It reports each commit that changes a path under
# openspec/ and lands without a Spec-check: trailer, or with one whose tree no
# longer matches the commit. A commit that changes nothing under openspec/ is
# never judged.
#
# Usage: check-commit-trailer.sh [--host <platform>]
#
# The check itself is shared: ../../../lib/commit-trailer/check-commit-trailer.sh,
# with its own DECISIONS.md. This file configures it for spec-check and sources
# it. Sourcing keeps $0 pointing at this file, so when the library re-runs the
# check in each submodule, it runs this file again. The report's wording, and
# the verification the library calls back into, are in hook-report.sh.

# -P resolves an install symlink to the clone. The library is found at
# ../../../lib from the clone's copy of this file, and is not beside the
# symlink in ~/.agents/skills, so without -P it is never found.
here=$(CDPATH= cd -P -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || here=""
lib="$here/../../../lib/commit-trailer/check-commit-trailer.sh"

if [ -z "$here" ] || [ ! -r "$lib" ]; then
  # Exiting silently here would leave a broken hook that looks like it works.
  msg="spec-check: the shared commit-trailer library is missing (expected at $lib), so commits are not being checked. spec-check must be installed as a symlink into a full shared-skills clone; run: python3 ~/.agents/skills/manage-skills/scripts/skills.py doctor"
  case " $* " in
    *" --host cursor "*|*" --host=cursor "*)
      printf '{"additional_context":"%s"}\n' "$(printf '%s' "$msg" | LC_ALL=C sed 's/["\\]/ /g')"
      exit 0 ;;
  esac
  printf '%s\n' "$msg" >&2
  exit 2
fi

SPEC_CHECK_SCRIPTS=$here
COMMIT_TRAILER_SKILL=spec-check
COMMIT_TRAILER_KEY=Spec-check
COMMIT_TRAILER_PATHSPEC=':(top)openspec/'
COMMIT_TRAILER_REPORT="$here/hook-report.sh"
. "$lib"
