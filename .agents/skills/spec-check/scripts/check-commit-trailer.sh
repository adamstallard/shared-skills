#!/bin/sh
# spec-check's commit hook. The agent host runs it after each shell command,
# so it sees commits after they land, and reports to the agent; it blocks
# nothing. It judges each commit that changes `openspec` at the repository
# root, whether a folder, a file or a symlink, or any path under it. It reports
# one without a Spec-check: trailer, or with one whose tree no longer matches
# the commit. Every other commit is never judged.
#
# Usage: check-commit-trailer.sh [--host <platform>]
#
# --host names the agent host that runs the hook, claude or cursor, and sets
# how a report is delivered; the library lists the hosts in its header.
#
# The check itself is shared: ../../../lib/commit-trailer/check-commit-trailer.sh.
# This file configures it for spec-check and sources
# it, rather than running it. Sourcing keeps $0 pointing at this file, so when
# the library re-runs the check in each submodule, it runs this file again,
# with spec-check's settings. Run directly, the library would check each
# submodule without them. hook-report.sh holds the
# report's wording and commit_trailer_verify, the function the library calls
# to verify a Spec-check: value.

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
COMMIT_TRAILER_PATHSPEC=':(top)openspec'
COMMIT_TRAILER_REPORT="$here/hook-report.sh"
. "$lib"
