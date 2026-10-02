# The hook path of commit-with-trailers.sh, sourced by it only when a value is
# bound and the repository has a pre-commit or commit-msg hook. Without hooks
# the commit script commits with a plain `git commit -m ... --trailer ...`, and
# none of this runs.
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file — "The
# pre-commit hook runs before anything is bound" and "The pre-commit hook runs
# once per commit".
#
# Not run on its own: it uses the commit script's variables (families, args,
# subject, body, lib_dir, nl) and functions (fail, q, verify).
#
# hooks_before_binding: runs pre-commit now, through run-pre-commit.sh, so a
#   formatter rewrites the staged files before anything is bound to them.
#   Sets stale_why for the verifiers. On git older than 2.36, which cannot run
#   commit-msg here, sets with_hooks=n so the plain path commits.
# hooks_commit: writes the message, trailers included, to COMMIT_EDITMSG,
#   runs commit-msg on it, and commits with `git commit --no-verify -F`, so
#   neither hook runs twice. Does not return.

hooks_before_binding() {
  [ -r "$lib_dir/run-pre-commit.sh" ] ||
    fail "run-pre-commit.sh is missing from the library ($lib_dir/run-pre-commit.sh)"
  # run-pre-commit.sh has printed why: the hook failed, the index could not
  # be read, or git is too old to run the hook first. Not all are the hook's.
  hook_state=$(sh "$lib_dir/run-pre-commit.sh") ||
    fail "run-pre-commit.sh refused, for the reason above"
  [ "$hook_state" = changed ] && stale_why="the pre-commit hook changed the staged files"
  # Before 2.36 there is no `git hook run`, so commit-msg cannot be run here;
  # run-pre-commit.sh has already refused if there was a pre-commit hook.
  version=$(git version)
  version=${version#git version }
  major=${version%%.*}
  minor=${version#*.}
  minor=${minor%%[!0-9]*}
  case $major$minor in *[!0-9]*|'') major=0 minor=0 ;; esac
  if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 36 ]; }; then
    with_hooks=n
  fi
  return 0
}

hooks_commit() {
  # The trailer arguments, and every trailer line they add, from the plain
  # path's argument list.
  trailers='' added=''
  eval "set -- $args"
  while [ "$#" -gt 0 ]; do
    case $1 in
      -m) shift 2 ;;
      --trailer) trailers="$trailers --trailer $(q "$2")"; added="$added$2$nl"; shift 2 ;;
      *) fail "internal: unexpected git argument '$1'" ;;
    esac
  done

  # The message file, written the way `git commit -m ... --trailer ...`
  # writes it: whitespace cleaned, then the trailers added by
  # interpret-trailers. COMMIT_EDITMSG, because it is the file git passes to
  # commit-msg, and some hooks read it by name. `git commit -F` reads it
  # before writing it again.
  msg_file=$(git rev-parse --git-path COMMIT_EDITMSG)
  case $msg_file in /*) ;; *) msg_file="$(pwd -P)/$msg_file" ;; esac
  # Joined as `-m <subject> -m <body>` joins them: each given a final newline
  # if it lacks one, with a newline between. Under verbatim nothing cleans it
  # after.
  joined=$(line_end "$subject"; [ -z "$body" ] || { printf '\n'; line_end "$body"; }; echo x)
  printf '%s' "${joined%x}" | clean >"$msg_file" ||
    fail "could not write the message to $msg_file"
  # The same pinned trailer settings as the plain path's git commit.
  eval "set -- $trailers"
  git -c trailer.ifexists=add -c trailer.ifmissing=add \
      -c trailer.separators=: -c trailer.where=end \
      interpret-trailers --in-place --no-divider "$@" "$msg_file" ||
    fail "git interpret-trailers could not add the trailers"

  # The commit-msg hook, on the file git commit will read.
  built=$(cat "$msg_file")
  status=0
  git hook run --ignore-missing commit-msg -- "$msg_file" >&2 </dev/null || status=$?
  [ "$status" -eq 0 ] ||
    fail "the commit-msg hook rejected the message (exit $status); its output is above"
  if [ "$(cat "$msg_file")" != "$built" ]; then
    # The message as a verifier is given it: the hook's version, minus the
    # trailer lines added here, each removed at its last occurrence wherever
    # it is (git may place trailers before trailing `#` lines), then cleaned
    # again so the blank lines left behind collapse.
    edited=$(clean <"$msg_file" | ADDED=$added awk '
      BEGIN { n = split(ENVIRON["ADDED"], want, "\n") - 1 }
      { line[NR] = $0 }
      END {
        for (j = 1; j <= n; j++) {
          found = 0
          for (i = NR; i >= 1; i--)
            if (!gone[i] && line[i] == want[j]) { gone[i] = 1; found = 1; break }
          if (!found) { print want[j]; exit 1 }
        }
        for (i = 1; i <= NR; i++) if (!gone[i]) print line[i]
      }') || fail "the commit-msg hook removed or changed a trailer line this script added: $edited"
    edited=$(printf '%s\n' "$edited" | clean)
    verify "$edited" "the commit-msg hook changed the message"
  fi

  # --no-verify skips only pre-commit and commit-msg, and both have just run,
  # so git commit would only run them a second time. prepare-commit-msg and
  # post-commit still run (git 2.54, tested in CommitFamiliesTests).
  exec git commit --no-verify -F "$msg_file"
}

# Cleans a message as `git commit -m` does: whitespace, unless commit.cleanup
# is verbatim, which keeps the message as passed.
clean() {
  if [ "$(git config commit.cleanup || :)" = verbatim ]; then cat; else git stripspace; fi
}
line_end() { case $1 in *"$nl") printf '%s' "$1" ;; *) printf '%s\n' "$1" ;; esac; }
