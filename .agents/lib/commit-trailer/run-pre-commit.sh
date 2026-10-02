#!/bin/sh
# Runs the repository's pre-commit hook now, before anything is bound to the
# staged tree, so a formatter in it rewrites the files before the binding is
# made rather than during `git commit`, after it.
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file — "The
# pre-commit hook runs before anything is bound".
#
# Usage: run-pre-commit.sh
#
# Call it after the final `git add` and before minting or signing anything.
# commit-with-trailers.sh calls it; a skill that signs the staged tree before
# the commit script runs (prose's `prose check`) calls it before signing.
#
# Exit 0: the hook passed, or there is none. stdout is one word:
#   unchanged  the staged tree is what it was before the hook ran, or the hook
#              already passed on this state and was not run again
#   changed    the hook changed the staged tree; bind what it left staged
#
# Runs the hook at most once per state. A pass is recorded in the git dir
# (commit-trailer/pre-commit-passed) with the tree it left staged and the
# state it ran in: HEAD, the hook file and its content, all git config
# (hashed) and the unstaged changes, submodules' included. A later call in
# that same state skips the hook. Environment variables are not part of it. So
# `prose check` runs it, signs, and the commit script does not run it again.
# A hook defined in config (hook.<name>.event) is recorded like a hook file.
# Code a hook runs from outside the repository (a config hook's script, or a
# gitignored file a hook loads) is not in the state: after editing it, run the
# hook by hand or change what is staged.
# Exit 1: the hook failed, the staged tree could not be read, or this git
#   cannot run the hook (older than 2.36) and there is a hook to run. stdout
#   is empty and the reason is on stderr.
#
# The hook's own output goes to stderr, as it does during `git commit`. It
# runs through `git hook run`, which honours core.hooksPath and runs the hook
# from the top of the work tree. Unlike during `git commit`, GIT_INDEX_FILE
# and the GIT_AUTHOR_* variables are not set; see DECISIONS.md.
set -eu

me=run-pre-commit
nl=$(printf '\nx'); nl=${nl%x}

staged_tree() {
  git write-tree 2>/dev/null || {
    echo "$me: git write-tree failed; is something unmerged, or is this not a git repository?" >&2
    exit 1
  }
}

# `git hook` arrived in 2.36. On an older git, refuse only when there is a
# hook to run: without one, there is nothing to run early.
version=$(git version)
version=${version#git version }
major=${version%%.*}
minor=${version#*.}
minor=${minor%%[!0-9]*}
case $major$minor in *[!0-9]*|'') major=0 minor=0 ;; esac
if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 36 ]; }; then
  hook=$(git rev-parse --git-path hooks/pre-commit)
  if [ -f "$hook" ] && [ -x "$hook" ]; then
    echo "$me: this git ($version) cannot run the pre-commit hook ($hook) before the trailers are bound; that needs git 2.36 or later" >&2
    exit 1
  fi
  echo unchanged
  exit 0
fi

# Absolute, so the record does not depend on the directory this runs from.
hook=$(git rev-parse --path-format=absolute --git-path hooks/pre-commit)
record=$(git rev-parse --git-path commit-trailer/pre-commit-passed)

# Everything besides the staged tree that can change the hook's verdict.
# Unstaged changes count because hooks read the work tree (tsc does), and
# husky's real script, .husky/pre-commit, is a tracked file the hook file
# only sources. HEAD counts because a hook may check the branch.
state() {
  echo "head $(git symbolic-ref -q HEAD || echo detached) $(git rev-parse -q --verify HEAD || echo none)"
  if [ -f "$hook" ]; then
    echo "hook $hook $( [ -x "$hook" ] && echo x) $(git hash-object --no-filters -- "$hook")"
  else
    echo "hook $hook none"
  fi
  # All of it, not just hook.*: a hook may read any key (pre-commit.sample
  # reads hooks.allownonascii). Hashed, because config can hold credentials.
  echo "config $(git config --list -z | git hash-object --stdin)"
  # --submodule=diff: plain git diff shows a dirty submodule as one "-dirty"
  # line, so a second edit inside it would not change the hash.
  echo "unstaged $(git diff --no-relative --no-ext-diff --no-textconv --no-color --binary --submodule=diff | git hash-object --stdin)"
}

# A pass is recorded whenever there is a hook to run: a hook file, or a hook
# defined in config, whose command state() covers by hashing all config.
before=$(staged_tree)
if { [ -f "$hook" ] && [ -x "$hook" ]; } ||
   git config --get-regexp '^hook\..*\.event$' '^pre-commit$' >/dev/null; then
  recorded=y
  if [ -f "$record" ] && [ "$(cat "$record")" = "tree $before$nl$(state)" ]; then
    echo "$me: the pre-commit hook already passed on this staged tree; not running it again" >&2
    echo unchanged
    exit 0
  fi
else
  recorded=n
fi

rm -f "$record"
status=0
git hook run --ignore-missing pre-commit >&2 </dev/null || status=$?
if [ "$status" -ne 0 ]; then
  echo "$me: the pre-commit hook failed (exit $status); its output is above. If it rewrote files, review the changes, \`git add\` what belongs in this commit, and try again" >&2
  exit 1
fi
after=$(staged_tree)

if [ "$recorded" = y ]; then
  # Best effort: without the record, the next call just runs the hook again.
  { mkdir -p "$(dirname "$record")" &&
    printf 'tree %s\n%s\n' "$after" "$(state)" >"$record.tmp" &&
    mv "$record.tmp" "$record"; } 2>/dev/null || rm -f "$record.tmp"
fi

if [ "$before" = "$after" ]; then
  echo unchanged
else
  echo "$me: the pre-commit hook changed the staged files; what it left staged is what gets bound and committed" >&2
  echo changed
fi
