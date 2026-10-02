#!/bin/sh
# Notices when a commit lands without a skill's trailer. Shared: each skill that
# enforces a trailer sources this from a wrapper of its own, which sets
#
#   COMMIT_TRAILER_SKILL   the skill's name, e.g. bug-hunter — names its state
#                          files, its environment prefix and its reports
#   COMMIT_TRAILER_KEY     the trailer key, e.g. Bug-hunter; its binding is
#                          <key>-Tree, minted by mint-trailer.sh
#   COMMIT_TRAILER_REPORT  a file defining commit_trailer_report, which builds
#                          the skill's own report text. It may also define
#                          commit_trailer_verify <sha> <value>, which replaces
#                          question 3 below for that skill: returns 0 valid, 1
#                          invalid with the reason on stdout, anything else
#                          "could not verify", reported as such. A callback
#                          that exits instead of returning has not answered.
#                          Under the file's own `set -e`, a non-zero return
#                          reads the same way: sh cannot tell it from an
#                          aborted command. The file runs without this hook's
#                          `set -u`
#
# Sourced, not executed, so $0 stays the wrapper: the submodule walk re-invokes
# $0 and has to come back through the wrapper's configuration.
#
# Usage (through the wrapper): <skill>/scripts/check-commit-trailer.sh [--host <platform>]
#
# BEFORE CHANGING ANY OF THIS, READ DECISIONS.md next to this file. Most of what
# looks like an obvious improvement here has been tried; the reason it was
# reverted is usually not visible from the line you would be editing.
#
# Runs AFTER a shell command and asks git what happened, rather than reading the
# command that ran. Three questions, all with exact answers:
#
#   1. Which commits were authored here since we last looked? The reflog is an
#      append-only record of everything that moved HEAD, so the answer is "the
#      entries added since last time, whose action authored a commit".
#   2. Does each carry the skill's trailer? git's own trailer parser
#      answers that, which is not the same as the message containing the text.
#   3. If that trailer is not a skip note, does its `<key>-Tree:` trailer
#      match the tree that actually landed? A trailer can be present and
#      still be a sentence someone recalled rather than one mint-trailer.sh
#      produced — see DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent.
#
#   --host claude   Claude Code, PostToolUse / matcher "Bash"   stderr
#   --host cursor   Cursor, postToolUse / matcher "Shell"       additional_context
#   (anything else) unknown host                                stderr
#
# KNOWN LIMITS, each deliberate and each explained in DECISIONS.md:
#
#   - Reflogs must be enabled. With `core.logAllRefUpdates=false` there is
#     nothing to read and this stays silent, unwarned.
#   - A hand-resolved conflict under the rebase *apply* backend arrives as
#     `rebase (pick):` and is not reported, being indistinguishable from a
#     plain replay.
#   - It looks at one repository: the one the command ran in, plus its
#     initialised submodules. `git -C /other/repo commit` moves a HEAD this
#     never examines.
#
# Fails open and fails quiet, with one exception — a git too old to read
# trailers, which would make every commit look checked forever.

set -u

SKILL=${COMMIT_TRAILER_SKILL:-}
KEY=${COMMIT_TRAILER_KEY:-}

# Every git read goes through this. The user's own config can otherwise
# contaminate stdout: `log.showSignature=true` — the standard companion to
# commit signing — prepends verification text to `git log --format` output even
# when an explicit format is given. Every commit then reads as trailered, so this
# hook goes silent forever, and the same contamination defeats the probe below,
# disarming the one failure it is supposed to shout about. Reading git means
# reading git, not git plus whatever the user configured.
#
# trailer.separators=: is the same guard for a different knob: this hook reads
# trailers with `%(trailers:key=...)`, which honors the user's own
# trailer.separators config. A repo configured without ":" in that set would
# make git stop recognizing "Bug-hunter: ..." as a trailer at all — every real
# commit then reads as unchecked, the opposite false negative from the signing
# case but the identical failure mode: the hook goes blind to its own signal.
g() { git -c log.showSignature=false -c trailer.separators=: "$@"; }

# These two are one guard, not two knobs: together they bound what a run with no
# usable cursor will judge. Kept deliberately tight. Loosening either turns the
# first run in an established repo into a report naming pre-existing commits and
# advising `git reset --soft` on them — a false alarm at the exact moment someone
# is deciding whether to keep this hook at all.
RECENT_SECONDS=120        # how fresh a commit must be to judge without a cursor
NO_BASELINE_WINDOW=20     # reflog entries to consider without a cursor
LOCK_STALE_MINUTES=1      # after this, an abandoned lock is reclaimed

# Which reflog actions mean "code was authored here, just now".
#
# This is a list of what to EXCLUDE, not what to include, and the inversion is
# deliberate. The include-list version kept springing leaks: iteration 2 had to
# add `commit (cherry-pick)` for a conflicted pick, iteration 3 found
# `rebase (continue)` still missing for a conflicted rebase — content that
# exists in no earlier commit, silently unchecked. An include-list of everything
# git might ever write can never be proven complete, and each gap fails silent.
#
# Excluded here are the actions that move HEAD onto content that already
# existed. Anything else counts as authoring, so a git verb nobody anticipated
# produces a visible false alarm rather than an invisible miss — the direction
# this whole check is meant to fail in.
#
# `commit (merge)` is excluded on purpose even though it is a commit: a merge is
# not authored work, and a conflicted merge is finished with one, so including
# it would report merges only when they went badly. `rebase (continue)` is NOT
# excluded, because that is a conflict resolution somebody typed.
REPLAY='^(checkout:|clone:|branch:|reset:|pull|merge |merge:|rebase:|rebase \(pick\):|rebase \(start\):|rebase \(finish\):|rebase \(abort\):|rebase \(reword\):|rebase \(squash\):|rebase \(fixup\):|rebase \(label\):|rebase \(onto\):|rebase \(merge\):|rebase \(reset\):|rebase \(edit\):|commit \(merge\):|stash|gc:|filter-branch:)'

HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      if [ $# -ge 2 ]; then HOST="$2"; shift 2; else shift; fi
      ;;
    --host=*) HOST="${1#--host=}"; shift ;;
    *) shift ;;
  esac
done

# Each value checked on its own: joined, an empty one hides behind the other.
# The skill name must start with a letter because it becomes a shell variable
# prefix below. Checked after --host so Cursor still gets its JSON, and before
# anything writes state.
cfg_bad=""
case "$SKILL" in ''|[!A-Za-z]*|*[!A-Za-z0-9-]*) cfg_bad=1 ;; esac
case "$KEY" in ''|*[!A-Za-z0-9-]*) cfg_bad=1 ;; esac
if [ -n "$cfg_bad" ]; then
  cfg_msg="commit-trailer: COMMIT_TRAILER_SKILL must be set to a letter followed by letters, digits and dashes, and COMMIT_TRAILER_KEY must be set to letters, digits and dashes; got '$SKILL' and '$KEY'"
  if [ "$HOST" = cursor ]; then
    printf '{"additional_context":"%s"}\n' \
      "$(printf '%s' "$cfg_msg" | LC_ALL=C tr '\n' ' ' | LC_ALL=C sed 's/["\\]/ /g; s/[[:cntrl:]]/ /g')"
    exit 0
  fi
  printf '%s\n' "$cfg_msg" >&2
  exit 2
fi
# bug-hunter -> BUG_HUNTER: the prefix of the two variables the submodule walk
# hands to its nested runs.
ENVP=$(printf '%s' "$SKILL" | tr 'a-z-' 'A-Z_')

# Everything this hook has to say goes into one buffer, and only the outermost
# run empties it. A nested run — the submodule walk re-invokes this script — is
# handed the same buffer and says nothing itself, because Cursor parses stdout
# as a single JSON document and a second object makes the whole payload
# unreadable, losing the report entirely in the case with the most to say.
eval "msgs=\${${ENVP}_MSGS:-}"
outermost=""
if [ -z "$msgs" ]; then
  outermost=1
  msgs="${TMPDIR:-/tmp}/$SKILL-msgs.$$"
  # Two things are load-bearing here. stderr is redirected first, because
  # redirections apply left to right and `>"$msgs" 2>/dev/null` lets the shell's
  # own "cannot create" diagnostic escape before /dev/null is in effect. And the
  # whole thing runs in a subshell, because `:` is a POSIX *special built-in*: a
  # redirection failure on one aborts a non-interactive shell outright, `||` and
  # all. Under dash — /bin/sh on Debian and Ubuntu, so most Linux sandboxes —
  # that killed the script before the guard below could run, leaving a blocking
  # exit 2 with an empty message on every command. A subshell contains it.
  ( : 2>/dev/null >"$msgs" ) || msgs=""
fi

# No buffer means nothing can be said. Stop before anything advances a cursor:
# the cursor is written before the report is emitted, so carrying on would mark
# these commits as seen and lose the report permanently.
[ -n "$msgs" ] || exit 0

say() {   # say <message>; may be multi-line
  [ -n "$msgs" ] && printf '%s\n' "$1" >>"$msgs"
  return 0
}

# Emptied once, by the outermost run only.
deliver() {
  [ -n "$msgs" ] && [ -s "$msgs" ] || return 0
  case "$HOST" in
    cursor)
      # One line, no quotes or backslashes: it has to survive being embedded in
      # a JSON string.
      printf '{"additional_context":"%s"}\n' \
        "$(LC_ALL=C tr '\n' ' ' < "$msgs" | LC_ALL=C sed 's/["\\]/ /g; s/[[:cntrl:]]/ /g')"
      ;;
    *)
      cat "$msgs" >&2
      ;;
  esac
  return 0
}

# Resolved before anything cds anywhere: the submodule walk re-invokes this
# script, and a relative $0 stops resolving the moment we move.
case "$0" in
  /*) self="$0" ;;
  *)  self="$PWD/$0" ;;
esac

payload=$(cat)

# Where to look. Hosts that report a working directory are believed; otherwise
# the hook's own cwd is the project.
#
# Newlines are stripped first so the whole payload is one record: awk's match()
# works per line, so a pretty-printed payload with a nested "cwd" matched twice
# and the extracted path came out as two lines — after which the hook silently
# fell back to its own cwd and watched the wrong repository. Flattened, match()
# finds the FIRST occurrence and a nested "cwd" cannot win. Splitting the payload on JSON punctuation would be simpler
# and is what an earlier version did — but it also splits the path value, so a
# directory named `svc,api` broke extraction and the hook silently fell back to
# its own cwd and reported a different repository.
cwd=$(
  printf '%s' "$payload" | tr -d '\n' | awk '
    match($0, /"cwd"[[:space:]]*:[[:space:]]*"/) {
      rest = substr($0, RSTART + RLENGTH)
      if (match(rest, /"/)) print substr(rest, 1, RSTART - 1)
    }
  '
)
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd" 2>/dev/null

# The whole per-repo check, as a function, so it runs once for the repo the
# command was in and again for each submodule underneath it. Every exit in here
# is a return — an exit would take the submodule walk down with it. Body left
# unindented on purpose: several of the strings below are multi-line report text,
# and indenting them would indent what the user reads.
check_repo() {
git_dir=$(g rev-parse --git-dir 2>/dev/null) || return 0
head=$(g rev-parse HEAD 2>/dev/null) || return 0   # a repo with no commits yet

state="$git_dir/$SKILL-head"
lock="$git_dir/$SKILL.lock"

# mkdir is atomic everywhere, so it serialises concurrent invocations — hosts do
# run tool calls in parallel. A SIGKILL skips the EXIT trap though, and an
# abandoned lock would otherwise disable this hook permanently and silently, so
# one that has been sitting there is reclaimed.
if ! mkdir "$lock" 2>/dev/null; then
  if [ -n "$(find "$lock" -maxdepth 0 -mmin +${LOCK_STALE_MINUTES} 2>/dev/null)" ]; then
    rmdir "$lock" 2>/dev/null
    mkdir "$lock" 2>/dev/null || return 0
  else
    return 0
  fi
fi
trap 'rmdir "$lock" 2>/dev/null' EXIT INT TERM

# The cursor is a *position* in the reflog, not a sha. A sha is not a cursor:
# the same one appears in the reflog many times, so `commit && checkout main`
# buries the new commit under an older entry that matches, and it is never seen
# again. The number of entries only ever grows as things happen.
count=$(g reflog show HEAD 2>/dev/null | wc -l | tr -d ' ')
[ -n "$count" ] || return 0

# An empty reflog is not the same as a disabled one: `git reflog expire` leaves a
# repo whose reflogs are perfectly healthy with nothing in them, and advising
# such a user to enable what is already enabled would waste the single notice
# this repository ever gets. The absence of the logs file is the real signal.
#
# No reflog means this check has nothing to read and will stay silent forever —
# and silent-and-broken must never be mistaken for silent-and-fine. Unlike the
# too-old-git case there is no activity signal to gate a warning on, so it would
# otherwise repeat on every command until someone uninstalled the hook. Say it
# once per repository instead, and say what to do: turning reflogs on is a single
# config command, so the user can opt in rather than be left guessing.
if [ "$count" -eq 0 ] && [ ! -e "$git_dir/logs/HEAD" ]; then
  told="$git_dir/$SKILL-noreflog"
  [ -f "$told" ] && return 0
  ( : 2>/dev/null >"$told" ) || return 0
  say "$SKILL: this repository keeps no reflog, so the check cannot tell which commits were made here and will stay silent. To use it, turn reflogs on: git config core.logAllRefUpdates true. To stop this hook instead: python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook $SKILL. This notice appears once per repository."
  return 2
fi

stored=$(cat "$state" 2>/dev/null || true)
last=${stored%% *}
last_head=${stored#* }
[ "$last_head" = "$stored" ] && last_head=""   # older format: count only
case "${last:-}" in
  ''|*[!0-9]*) last=""; last_head="" ;;   # absent, or written by an older version
esac

if [ -n "$last" ] && [ "$count" -eq "$last" ] && [ "$head" = "$last_head" ]; then
  # Nothing has moved HEAD since we last looked. The HEAD check matters as much
  # as the count: `git reflog expire` can drop exactly as many entries as were
  # added, landing the count back where it was with real work in between.
  return 0
elif [ -n "$last" ] && [ "$count" -gt "$last" ]; then
  window=$((count - last))
  by_recency=""
else
  # No baseline, or the reflog shrank under us (expiry, gc, a fresh clone over
  # the top). Either way the count is no longer a usable cursor, so fall back to
  # "what happened recently" rather than skipping the window entirely — a commit
  # made either side of a gc is still a commit nobody checked.
  window=$NO_BASELINE_WINDOW
  by_recency=1
fi

# Record the new position before saying anything, so nothing is reported twice.
# If it cannot be recorded — a read-only .git, a sandbox that denies writes —
# stay silent: without a memory, the same report would repeat on every command
# from here on. stderr is redirected first so the shell's own diagnostic about
# failing to create the file cannot escape.
tmp="$state.$$"
printf '%s %s\n' "$count" "$head" 2>/dev/null >"$tmp" || return 0
mv -f "$tmp" "$state" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 0; }

[ "$window" -gt 0 ] || return 0


# git prints an unsupported %(...) placeholder verbatim instead of failing, so on
# a git too old for trailers:key= every commit would look checked and this hook
# would be silent forever — indistinguishable from working. That one gets said
# out loud.
#
# Probe a key nothing will ever use. Probing the real key read HEAD's own trailer
# *value*, so a commit whose own trailer quoted the placeholder — i.e. any
# commit describing this very check — announced that git was too old, and
# swallowed the genuine findings in that window permanently.
probe=$(g log -1 --format="%(trailers:key=$KEY-probe-unused)" "$head" 2>/dev/null || true)
case "$probe" in
  *'%(trailers'*)
    say "$SKILL: this git cannot read commit trailers (%(trailers:key= is unsupported), so the check cannot tell a checked commit from an unchecked one. Upgrade git, or turn the hook off: python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook $SKILL"
    return 2
    ;;
esac

now=$(date +%s)
authored=$(
  g reflog show HEAD --format='%H%x09%ct%x09%gs' 2>/dev/null | head -n "$window" |
    LC_ALL=C awk -F'\t' -v now="$now" -v recent="$RECENT_SECONDS" -v by_recency="$by_recency" '
      # An entry with no action at all — git writes one when a worktree is
      # created — cannot be attributed to anything, so it is not authorship.
      # With an exclude-list, "unknown" defaults to counted, so this needs
      # saying explicitly.
      # No attempt is made to collapse an amended commit into one entry, and
      # that is deliberate. `git commit && git commit --amend` reports two, one
      # of them a sha the branch no longer holds. It looks untidy and it is
      # harmless: the advice stays correct and the surviving commit really is
      # unchecked.
      #
      # Two tidier versions were tried and both created silent misses, which is
      # the one outcome worse than an untidy report. Filtering to commits
      # reachable from HEAD swallowed `git commit && git checkout main`. Skipping
      # the entry before an amend swallowed an unrelated commit whenever an
      # excluded entry sat between them — `git commit && git rebase -i`. The
      # question this hook asks is "was content authored here", and neither
      # "does this sha survive" nor "what sits next to it" answers that.
      $3 != "" && $3 !~ /'"$REPLAY"'/ {
        # With a usable cursor, everything in the window happened since we last
        # looked. Without one, judge by age instead — a first run in an
        # established repo must not name a commit from last week and advise
        # rewriting it.
        if (by_recency == "" || (now - $2) <= recent) print $1
      }
    '
)
[ -n "$authored" ] || return 0

# git's own trailer parser, not a text search: a message that merely mentions
# the trailer has no such trailer, git matches trailer keys case-insensitively,
# and a trailer needs a value to be worth anything.
#
# A trailer that IS present is not automatically trusted, either. Any trailer
# that is not itself a skip note has to carry a <key>-Tree trailer bound
# to the tree that actually landed — see
# DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent
# for why a hand-typed trailer that merely matches the expected shape cannot
# produce this, why every non-skip shape needs it and not only "N bugs
# fixed" (an earlier draft scoped it that way and left "0 bugs found" as a
# one-word bypass), and why the check is scoped to plain commits only.
# Checks whether some reflog entry recorded a replay action landing on the
# given tree — used below to recognise a message-only amend of a cherry-pick
# or rebase replay. A message-only amend rewrites the reflog action to
# `commit (amend):` — the same laundering the merge-parent check two
# paragraphs down exists for, on the cherry-pick/rebase side instead of the
# merge side — so the action string alone cannot tell "amended a fresh
# commit" from "amended only the message of a replay". Amending a message
# never changes the tree (a tree is file content and mode, the message is
# not part of it), so a replay's tree reappearing unchanged under a later
# `commit (amend):` is exactly that case, confirmed against real cherry-pick
# and rebase repros, not inferred.
#
# Deliberately NOT limited to `$window`: by the time an agent amends a
# replayed commit's message, the hook has typically already run once on the
# replay itself (that run reported nothing, correctly, and advanced the
# cursor past it) — so the replay's own reflog entry is gone from every
# future window, by the cursor's own design. The one thing this check needs
# is exactly the one thing the cursor is built to stop re-reading. Reading
# the whole reflog here, not just the window, is what a window-scoped
# version got wrong when this was tried against a real rebase repro: it
# still reported an honest, unaltered replay as fabricated.
# Deliberately not `$REPLAY`: that list is the answer to a different
# question ("did this action author anything, at all") and specifically
# excludes checkout/reset/merge/etc — content that already existed. It does
# NOT exclude `cherry-pick:` or `rebase (pick):`, because those DO need a
# trailer of their own (carried forward, but present) — see the comment
# below on `was_plain_commit`. What this function needs is narrower still:
# only the actions confirmed, by real repro, to carry a *pre-existing* tree
# forward onto new history without re-authoring it.
CARRY='^(cherry-pick:|commit \(cherry-pick\):|rebase \(pick\):|rebase \(continue\):)'
landed_via_replay() {
  g reflog show HEAD --format='%H%x09%gs' 2>/dev/null |
    LC_ALL=C awk -F'\t' -v re="$CARRY" '$2 ~ re { print $1 }' |
    while IFS= read -r rsha; do
      [ "$(g rev-parse "${rsha}^{tree}" 2>/dev/null)" = "$1" ] && echo 1
    done | grep -q 1
}

# A skill may verify its own trailer instead of the <key>-Tree check, by
# defining commit_trailer_verify in its report file. Asked once, in a subshell
# for the same reason the report is built in one (see below). Absent, nothing
# below differs from the check without it.
#
# Every subshell that sources the file turns off `set -u` first. The file is
# the skill's code, not ours: under our `set -u` one unset read aborts it, and
# the abort's exit status differs by shell — 1 under bash, read as "invalid",
# 2 under dash. Both also discard what the file prints as it loads: here stdout
# is Cursor's JSON channel, and in the callback it would join the reason.
#
# Neither trusts the subshell's exit status alone. An `exit 0` in the file ends
# the subshell with 0 before anything after the `.` runs, which would read as
# "has a callback" and then as "valid". Each one prints a last line only once
# it has got to the end, and no last line means the file never got there.
#
# The callback's last line follows its own output, which can quote the trailer
# value, so a fixed marker could be forged by the value itself. This one is new
# on every run.
report_file=${COMMIT_TRAILER_REPORT:-}
verify_ext=""
if [ -n "$report_file" ] && [ -r "$report_file" ] &&
   [ "$( exec 2>/dev/null; set +u; . "$report_file" >/dev/null || exit 1
         command -v commit_trailer_verify >/dev/null 2>&1 && echo ok )" = ok ]; then
  verify_ext=1
fi
verify_done="commit-trailer-verify-status-$$-$(od -An -N8 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n'):"

# Runs the skill's verification for one commit and records a failure. Scoped
# like the tree check: plain commits and amends only, and never a tree some
# replay landed, because a cherry-pick or rebase carries an older trailer onto
# new content. A replay's tree is exempt whatever the skill answered, "could
# not verify" included; it is looked for only after a failure, because reading
# the whole reflog on every commit costs more than asking the skill.
verify_with_skill() {   # verify_with_skill <sha> <raw value>
  plain=$(g reflog show HEAD --format='%H%x09%gs' 2>/dev/null |
    head -n "$window" | awk -F'\t' -v s="$1" '
      $1==s && ($2 ~ /^commit: / || $2 ~ /^commit \(amend\): / || $2 ~ /^commit \(initial\): /) { print "1"; exit }
    ')
  [ "$plain" = "1" ] || return 0
  # Only the status line is an answer. Without it the callback or the file
  # exited, `set -e` included, and its exit status goes in the message only.
  verify_status=""
  verify_exit=0
  reason=$(
    exec 2>/dev/null
    set +u
    . "$report_file" >/dev/null || exit 3
    commit_trailer_verify "$1" "$2"
    printf '\n%s%s' "$verify_done" "$?"
  ) || verify_exit=$?
  case $reason in
    *"$verify_done"*)
      verify_status=${reason##*"$verify_done"}
      reason=${reason%"$verify_done"*} ;;
  esac
  reason=$(printf '%s' "$reason")
  case $verify_status in *[!0-9]*) verify_status="" ;; esac
  [ "$verify_status" = 0 ] && return 0
  actual_tree=$(g rev-parse "${1}^{tree}" 2>/dev/null || true)
  if [ -n "$actual_tree" ] && landed_via_replay "$actual_tree"; then
    return 0
  fi
  case $verify_status in
    1) ;;
    '') reason="could not be verified (the callback did not return, exit $verify_exit)${reason:+: $reason}" ;;
    *) reason="could not be verified (exit $verify_status)${reason:+: $reason}" ;;
  esac
  reason=$(printf '%s' "$reason" | tr '\n' ' ')
  rejected="${rejected}$(g log -1 --format='%h %s' "$1" 2>/dev/null) -- ${reason:-rejected}
"
}

unchecked=""
unminted=""
rejected=""
misplaced=""
for sha in $authored; do
  # A merge is never reported — `git reset --soft HEAD~1` on one drops the
  # second parent, so the remedy would be actively destructive. Excluding the
  # `commit (merge):` action is not enough: amending a merge to tidy its message
  # rewrites it as `commit (amend):`. Ask the commit how many parents it has
  # instead of trusting how the reflog spelled it.
  case "$(g log -1 --format='%P' "$sha" 2>/dev/null)" in
    *' '*) continue ;;
  esac
  # `,unfold` joins a wrapped trailer's indented continuation lines back into
  # one logical value — confirmed against a real repro: without it, a single
  # wrapped `Bug-hunter:` trailer and two genuinely separate `Bug-hunter:`
  # trailers print identically, one value per line, and there is no way to
  # tell them apart after the fact. Taking the last non-empty line then gives
  # the last *logical* trailer, which is what matters for two reasons at
  # once: it is what `--trailer`'s default `addIfDifferentNeighbor` produces
  # when a value is corrected by appending rather than replacing, and it
  # closes a real bypass — a false `Bug-hunter: skipped ...` listed before a
  # genuine `Bug-hunter: 1 iteration, 1 bug fixed` used to exempt the whole
  # commit, because the exemption test matched skip against the concatenation
  # of every value rather than the one that is actually authoritative.
  raw_value=$(g log -1 --format="%(trailers:key=$KEY,valueonly,unfold)" "$sha" 2>/dev/null |
    awk 'NF { v = $0 } END { print v }')
  value=$(printf '%s' "$raw_value" | tr -d '[:space:]')
  if [ -n "$value" ] && [ -n "$verify_ext" ]; then
    verify_with_skill "$sha" "$raw_value"
    continue
  fi
  if [ -n "$value" ]; then
    # Has a trailer. Only a skip note is exempt from the tree binding —
    # triage stopped before any loop ran, so there is no tree for a binding
    # to attest to. Every other shape ("N bugs fixed", "0 bugs found",
    # "aborted ...") is a claim that the loop ran over THIS tree, and needs
    # the same binding: scoping this to "claims a fix" instead of "isn't a
    # skip" is exactly the gap an earlier draft left — "0 bugs found" is a
    # smaller-sounding lie for the same silent bypass. Checking the raw
    # value, not the whitespace-stripped one, because the words matter here.
    case "$raw_value" in
      [Ss]kipped*) : ;;
      *)
        # Scoped to a plain commit or a message-only amend of one — never to
        # a cherry-pick or rebase replay, which legitimately carries an
        # older trailer (older tree binding and all) forward onto new
        # content. Confirmed against a real repro, not inferred: a clean
        # cherry-pick writes `cherry-pick:`, a conflicted one
        # `commit (cherry-pick):`, a clean rebase replay `rebase (pick):`,
        # a conflicted one `rebase (continue):` — none of those match.
        #
        # A sha can appear in the reflog more than once — the same content
        # gets a fresh entry every time HEAD lands on it again, including via
        # `checkout:` or a fast-forward `merge:` that never re-authors
        # anything. `git commit && git checkout main && git merge --ff-only
        # fix` gives the fix commit a `merge:` entry newer than the `commit:`
        # entry that actually created it — the case the cursor design exists
        # for (DECISIONS.md#the-cursor-is-a-position-in-the-reflog-not-a-sha).
        # Taking only the newest entry would read `merge:`, never match, and
        # silently skip the check on exactly the commit chain this file calls
        # "the most common agent chain there is" — so this scans every entry
        # for this sha in the window and asks whether ANY of them is a plain
        # commit or amend, not what the latest one happened to say.
        # `commit (initial):` is a root commit's reflog action — confirmed
        # against a real repro, not inferred — and was missing from this
        # list entirely: a root commit could carry a fabricated trailer and
        # never be checked, silent until its first amend (which does say
        # `commit (amend):`) suddenly reported the byte-identical trailer.
        was_plain_commit=$(g reflog show HEAD --format='%H%x09%gs' 2>/dev/null |
          head -n "$window" | awk -F'\t' -v s="$sha" '
            $1==s && ($2 ~ /^commit: / || $2 ~ /^commit \(amend\): / || $2 ~ /^commit \(initial\): /) { print "1"; exit }
          ')
        if [ "$was_plain_commit" = "1" ]; then
          tree_value=$(g log -1 --format="%(trailers:key=$KEY-Tree,valueonly,unfold)" "$sha" 2>/dev/null |
            awk 'NF { v = $0 } END { print v }' | tr -d '[:space:]')
          actual_tree=$(g rev-parse "${sha}^{tree}" 2>/dev/null || true)
          if [ -z "$tree_value" ] || [ -z "$actual_tree" ] || [ "$tree_value" != "$actual_tree" ]; then
            # Not fabricated outright if this exact tree is explained by a
            # replay somewhere in the reflog: see `landed_via_replay` above.
            if [ -z "$actual_tree" ] || ! landed_via_replay "$actual_tree"; then
              unminted="${unminted}$(g log -1 --format='%h %s' "$sha" 2>/dev/null)
"
            fi
          fi
        fi
        ;;
    esac
    continue
  fi
  unchecked="${unchecked}$(g log -1 --format='%h %s' "$sha" 2>/dev/null)
"
  # There is a trailer-shaped line in there, but git does not read it as one.
  # Saying so is the difference between a useful report and a baffling one.
  if g log -1 --format='%B' "$sha" 2>/dev/null | grep -qiE "^[[:space:]]*$KEY:"; then
    misplaced=1
  fi
done

[ -n "$unchecked" ] || [ -n "$unminted" ] || [ -n "$rejected" ] || return 0

count_unchecked=$(printf '%s' "$unchecked" | grep -c . || true)

# The report states facts and stops. It does not say what to do about them.
#
# This block used to construct git commands, and across eight review iterations
# in two runs it produced 28 findings — every one of them in the machinery for
# working out which command applied. Root commits, detached HEAD, submodules,
# rewritten history, non-contiguous commits, unquotable paths: six situations
# needing different advice, each needing a condition that distinguishes it from
# the other five.
#
# The mistake was the frame. check_repo runs cd'd into each repository it
# checks, while the agent reading this stands somewhere else entirely — so every
# command had to be computed from context this script cannot see: the reader's
# cwd, their branch, what HEAD is for them. The reader has all of it, and knows
# git. Telling it *which commits lack a trailer, and in which repository* is the
# part it cannot cheaply work out for itself; the rest was us guessing.
#
# What survives is context-free: the standard, and how git wants a trailer
# written. Neither depends on where the reader stands, which is the line.
#
# For naming only — never for a command. check_repo runs cd'd into each
# submodule, so this resolves in a frame the reader is not standing in.
repo_label=$(g rev-parse --show-toplevel 2>/dev/null ||
             g rev-parse --absolute-git-dir 2>/dev/null || true)

# What the report says is the skill's; the facts it is built from are these
# variables: unchecked, unminted (newline-separated "sha subject" lines),
# rejected ("sha subject -- reason" lines, only from commit_trailer_verify),
# misplaced, count_unchecked, repo_label. It sets REPORT.
#
# Built in a subshell because `.` is a special built-in, like `:` above: a
# syntax error in the file — or an exit in it — aborts a non-interactive dash
# outright, after the cursor has already moved past these commits. In here it
# takes down only the subshell, and the file's own variables stay out of ours.
# The trailing x keeps $() from eating the report's final newlines.
REPORT=""
if [ -n "$report_file" ] && [ -r "$report_file" ]; then
  REPORT=$(
    exec 2>/dev/null
    set +u
    . "$report_file" || exit 1
    command -v commit_trailer_report >/dev/null 2>&1 || exit 1
    REPORT=""
    commit_trailer_report
    [ -n "$REPORT" ] || exit 1
    printf '%sx' "$REPORT"
  ) || REPORT=""
  REPORT=${REPORT%x}
fi
if [ -z "$REPORT" ]; then
  REPORT="$SKILL: commits landed without a valid $KEY: trailer${repo_label:+ in $repo_label}, and this skill's report text could not be loaded from '${COMMIT_TRAILER_REPORT:-}'.

$(printf '%s' "$unchecked$unminted$rejected")"
fi

say "$REPORT"
return 2

return 0
}

status=0
check_repo || status=$?

# Submodules are their own repositories with their own HEADs, so a commit made
# inside one moves a reflog this run never looked at. Walk them with the same
# check: each gets its own cursor and lock, because each is its own repo.
#
# Depth is capped rather than unbounded. Submodule trees are acyclic, but this
# hook runs after every single command and a deep tree would multiply that cost.
# `git -C /somewhere/else` stays invisible, and stays a documented limit.
eval "depth=\${${ENVP}_DEPTH:-0}"
case "$depth" in *[!0-9]*|'') depth=0 ;; esac

# Submodule paths are read a line at a time from here rather than word-split.
subs_file="${TMPDIR:-/tmp}/$SKILL-subs.$$"
if [ "$depth" -lt 2 ]; then
  toplevel=$(g rev-parse --show-toplevel 2>/dev/null || true)
  real_top=$(cd "$toplevel" 2>/dev/null && pwd -P) || real_top=""
  if [ -n "$toplevel" ] && [ -n "$real_top" ] && [ -f "$toplevel/.gitmodules" ]; then
    # One path per line, never word-split: a submodule at `vendor/my lib` is
    # legal, and splitting on spaces silently checked nothing at all.
    # -z gives key\nvalue\0 per record, so the value is length-delimited rather
    # than found by searching for `.path `. No textual strip is correct here: a
    # submodule *name* can contain `.path ` (stripping to the first match breaks)
    # and so can a *path* (stripping to the last one breaks). Converting NUL to
    # newline leaves key and value on alternating lines, read as pairs below.
    g config --file "$toplevel/.gitmodules" -z --get-regexp '^submodule\..*\.path$' \
      2>/dev/null | tr '\0' '\n' > "$subs_file" || true

    # Guarded rather than given a fallback path: an earlier version substituted
    # /dev/null here, which meant `rm -f /dev/null` on the way out — harmless as
    # a normal user, and as root it unlinks the device for every process on the
    # machine. An empty .gitmodules is ordinary, so that path was routine.
    if [ -s "$subs_file" ]; then
    prev=""
    while IFS= read -r line; do
      sub=""
      case "$prev" in
        submodule.*.path)
          case "$line" in
            submodule.*.path)
              # Shaped like a key, so treated as one. A submodule whose path is
              # literally of this shape is skipped — documented, and much
              # cheaper than the alternative: testing the line as a path walked
              # into any directory that happened to be named like a config key,
              # reported its commits and wrote state into it.
              ;;
            *) sub="$line" ;;
          esac
          ;;
      esac
      prev="$line"
      [ -n "$sub" ] || continue

      # .gitmodules is an ordinary tracked file in any repository you clone, and
      # git's own path validation is not consulted here. A path of `..` walked
      # out of the project, ran the full check on a repo the command never
      # touched, wrote state into its .git, and printed its commit subjects into
      # the transcript. Stay inside the tree.
      case "$sub" in
        /*|.|..|../*|*/../*|*/..) continue ;;
      esac

      # The string check above is cheap and catches the obvious escapes, but it
      # cannot see through a symlink — and a tracked symlink plus a matching
      # .gitmodules entry is ordinary content in any repository you clone. Both
      # sides get resolved before comparing, because resolving only one silently
      # skips every real submodule whenever the project itself sits under a
      # symlinked path, and that failure direction is a silent miss.
      real_sub=$(cd "$toplevel/$sub" 2>/dev/null && pwd -P) || continue
      case "$real_sub" in
        "$real_top"/*) ;;
        *) continue ;;
      esac

      # An uninitialised submodule is an empty directory with nothing to check.
      [ -e "$toplevel/$sub/.git" ] || continue

      # Skip the spawn when nothing has happened in there since it last looked:
      # the same question check_repo asks, asked with a stat instead of a
      # process. This walk runs after *every* command, not just commits, so in
      # the steady state it is otherwise a process per submodule per `ls`.
      #
      # Gating on the parent's reflog instead would be wrong in the one way that
      # matters: committing inside a submodule does not move the parent's HEAD,
      # which is exactly the case this walk exists for.
      #
      # Anything unresolvable spawns anyway — a skipped check is a silent miss,
      # and the whole point of the gate is that it is only ever an optimisation.
      sub_git="$toplevel/$sub/.git"
      if [ -f "$sub_git" ]; then
        # A submodule's .git is a file: "gitdir: <path>", usually relative.
        gitdir=$(sed -n 's/^gitdir: *//p' "$sub_git" 2>/dev/null)
        case "$gitdir" in
          "") sub_git="" ;;
          /*) sub_git="$gitdir" ;;
          *)  sub_git="$toplevel/$sub/$gitdir" ;;
        esac
      fi
      # `find -newer`, not the shell's `-nt`: bash and dash both compare whole
      # seconds, so a commit made a fraction of a second after the last check
      # reads as "not newer" and gets skipped. That is a silent miss, and it
      # would happen only sometimes — the worst way for this to be wrong.
      #
      # A submodule with *live* submodules of its own is never skipped: this
      # spawn is the only thing that walks them, so skipping it on its own
      # reflog repeats the parent-gating mistake one level down — a commit in
      # `a/inner` does not move `a`'s HEAD either.
      #
      # "Live" and not merely "declared": `git submodule update --init` without
      # --recursive is the default flow and leaves a .gitmodules naming a path
      # that was never initialised, and `git rm` of the last one leaves the file
      # tracked but empty. Exempting on the file's presence alone bought a
      # process per command, forever, that could never find anything.
      has_live_nested=""
      if [ "$depth" -eq 0 ] && [ -f "$toplevel/$sub/.gitmodules" ]; then
        # One path per line, exactly as the parent walk above reads them: a
        # nested submodule at `deep dir` is legal, and word-splitting read it as
        # not live — so the parent spawn was skipped when only that nested repo
        # had moved. Same bug as the parent walk had, made again seventy lines
        # further down.
        nested_file="${TMPDIR:-/tmp}/$SKILL-nested.$$"
        if ( : 2>/dev/null >"$nested_file" ); then
          g config --file "$toplevel/$sub/.gitmodules" -z \
            --get-regexp '^submodule\..*\.path$' 2>/dev/null |
            tr '\0' '\n' >"$nested_file" || true
          nprev=""
          while IFS= read -r nline; do
            nested=""
            case "$nprev" in
              submodule.*.path)
                case "$nline" in
                  submodule.*.path) ;;
                  *) nested="$nline" ;;
                esac
                ;;
            esac
            nprev="$nline"
            [ -n "$nested" ] || continue
            [ -e "$toplevel/$sub/$nested/.git" ] || continue
            has_live_nested=1
            break
          done < "$nested_file"
          rm -f "$nested_file" 2>/dev/null
        else
          # Cannot tell, so do not skip: the gate is only ever an optimisation.
          has_live_nested=1
        fi
      fi

      if [ -n "$sub_git" ] &&
         [ -z "$has_live_nested" ] &&
         [ -f "$sub_git/$SKILL-head" ] &&
         [ -f "$sub_git/logs/HEAD" ] &&
         [ -z "$(find "$sub_git/logs/HEAD" -newer "$sub_git/$SKILL-head" 2>/dev/null)" ]; then
        continue
      fi

      sub_status=0
      printf '{"cwd":"%s"}' "$toplevel/$sub" |
        env "${ENVP}_DEPTH=$((depth + 1))" "${ENVP}_MSGS=$msgs" \
          sh "$self" --host "$HOST" 2>/dev/null || sub_status=$?
      [ "$sub_status" -eq 2 ] && status=2
    done < "$subs_file"
    fi
    rm -f "$subs_file" 2>/dev/null
  fi
fi

rm -f "$subs_file" 2>/dev/null

# Only the outermost run speaks, and only once. Cursor is told with exit 0
# because it reads the decision from stdout; everyone else needs exit 2 for the
# message on stderr to reach the agent at all.
if [ -n "$outermost" ]; then
  deliver
  # Exiting 2 with an empty message is a blocking error that says nothing. If
  # the buffer was never usable there is no report to act on, so fail open and
  # quiet like every other unreadable-state path here.
  [ -n "$msgs" ] && [ -s "$msgs" ] || status=0
  rm -f "$msgs" 2>/dev/null
  [ "$status" -eq 2 ] && [ "$HOST" = "cursor" ] && status=0
fi

exit "$status"