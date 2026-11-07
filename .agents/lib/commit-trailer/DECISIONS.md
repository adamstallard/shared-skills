# commit-trailer — decisions

**Read this before changing anything here.** The code shows how the scripts
work. This file holds what the code can't show: most changes that look like
obvious improvements have been tried, and the reason each failed is not
visible from the line you would edit.

Each entry gives a decision, why it holds, and the alternatives rejected.
Before changing a mechanism, check its rejected alternatives and any entry
that solves a similar problem. Twice, a problem already solved in one place in
the code was solved again differently a few lines away, because the first
solution was recorded only beside its own code.

Terms used throughout:
- **The cursor** is the hook's stored position in the reflog, so each run
  judges only commits made since the last (*The cursor is a position in the
  reflog, not a sha*). **Cursor**, capitalised, is the Cursor editor, a host
  that reads the hook's output as JSON.
- **A family** is one skill's trailer with its binding, the proof that the
  skill ran (*One commit, several families*).
- **The fact variables** are the shell variables the check sets, such as the
  commits it found, for the skill's report function to read.

The incidents below happened under bug-hunter, the first skill to use these
scripts. Read `Bug-hunter:` as whichever trailer a skill configures, and "the
skill" as the skill whose wrapper sourced the check.

---

## One library, a thin wrapper per skill

**Decision.** The check, the mint and the commit assembly live here once. Each
skill that enforces a trailer keeps its own `scripts/check-commit-trailer.sh`
and `mint-trailer.sh`. They set the skill's name, trailer key and report file,
then source the library (the check) or run it (the mint). A skill with its own
commit script, such as bug-hunter's `commit-with-trailer.sh`, keeps its
interface and hands its family to `commit-with-trailers.sh` (see *One commit,
several families*).

**Why.** Code that changes has to change in one place. Two copies of the
reflog edge cases (750 lines when the library was split out) would drift, and
every entry below is a reason they would.

**Rejected.**
- One script registered as the hook by several skills, checking a list of
  trailers. `manage-skills` identifies a hook entry's owner by the script path
  in it, so uninstalling or disabling one skill would remove the other's hook.
- The wrapper `exec`ing the library. `$0` would become the library, and the
  submodule walk re-invokes `$0`, so the nested runs would lose the skill's
  configuration. The trace-based tests (`sh -x`) would also stop seeing the
  library's lines and pass vacuously.

**Consequences.**
- A skill folder copied without the rest of the clone has no library. Its
  wrappers say so on every run: a hook that fell silent would be broken and
  look like it is working, the one failure these scripts refuse.
- The state files, lock and environment variables are named from the skill
  (`<skill>-head`, `<skill>.lock`, `<SKILL>_DEPTH`), so two skills' hooks never
  share a cursor.
- A skip note is any value starting `skipped`, for every skill.

---

## The skill's report is built in a subshell

**Decision.** The library sources the skill's report file inside `$( … )`, with
a trailing sentinel so trailing newlines survive. When that fails or comes back
empty, it uses its own report.

**Why.** `.` is a special built-in: under dash, a syntax error in the sourced
file aborts the whole hook. By then the stored reflog position has moved past
the commits the report was about to name, so they would never be reported. In a subshell,
anything the file does (a syntax error, an `exit`, `set -e`, overwriting one of
the library's variables) takes down only the subshell.

**Rejected.** `! . "$report_file"` as the guard. bash returns non-zero and the
guard works; dash never returns. Found by bug-hunter; the regression test runs
only where dash is installed.

**Consequence.** A report function that prints to stdout has that text
captured into the report, rather than corrupting the JSON the Cursor editor
reads.

---

## Each configuration value is validated on its own

**Decision.** `COMMIT_TRAILER_SKILL` and `COMMIT_TRAILER_KEY` are checked
separately, after `--host` is parsed and before anything writes state. The
skill name must start with a letter.

**Why.** Checked as one joined string, an empty value hid behind the other: an
empty key meant no commit could ever carry the trailer, so every commit was
reported after every command. The skill name becomes a shell variable prefix
(`bug-hunter` → `BUG_HUNTER_DEPTH`), and a leading digit crashed the hook. The
check runs after `--host` so a Cursor host still gets JSON.

---

## Detect commits from git state, never from the command text

**Decision.** The hook reads the reflog. It never inspects the shell command
that ran.

**Why.** Pattern-matching `git commit` in the command, tried in two versions,
leaked on: a commit on the second line of a multi-command call,
`git -C ${REPO} commit`, `GIT_AUTHOR_NAME="Jane Doe" git commit`,
`timeout 120 git commit`, `env … git commit`, seven `-c key=value` pairs
before `commit` where the pattern allowed six, and a `\`-continued
invocation. Two review passes found fifteen holes, two of
them introduced by fixes to the others.

**Rejected.** A better regex. Matching text is a guess about what a shell will
do. Only the shell knows, and by the time it knows, git has recorded what
happened.

---

## The reflog action list excludes, it does not include

**Decision.** `REPLAY` names the actions that move HEAD onto content that
already existed. Any action not on it counts as authorship.

**Why.** An include-list cannot be proven complete, and every gap in it is a
silent miss. Tried, it leaked `commit (cherry-pick)` for a conflicted pick,
then `rebase (continue)` for a conflicted rebase: both hand-typed content, both
unreported. With an exclude-list, an action nobody anticipated produces a
visible false alarm instead.

**Rejected.** Adding to the include-list each time a gap appears. Three rounds
of that showed the list has no end.

**Where this stops applying.** Only to open-ended sets, such as git's actions
or the situations a command might meet. Where the bad set is closed by
definition, a reject-list is provably complete and an accept-list only guesses
at what is safe. The characters that cannot survive a single-quoted path are
exactly `'`, `"`, `\` and control characters, because single-quoting defines
that. An accept-list there excluded spaces, so ordinary repository paths
were treated as unquotable. Ask whether the set can be proven complete, not which way the list
points.

**Trap.** Never guess action strings. `rebase (label):` and `rebase (onto):`
were guessed, and git writes neither; the real ones are `rebase (merge):` and
`rebase (reset):`. Cursor bugbot proposed `rebase (skip):` and
`rebase (drop):`, which do not exist either: a skipped or dropped commit
produces no reflog entry. Get action strings from
`git reflog show HEAD --format='%gs'` on a real repro.

---

## `commit (merge)` is excluded; `rebase (continue)` is not

**Decision.** A merge is never reported, however its reflog entry is spelled:
the check is the commit's parent count, not the action string.

**Why.** A merge is not authored work, and a conflicted merge is finished with
a commit, so including the action would report merges only when they went
badly. The usual way to redo a reported commit, `git reset --soft HEAD~1`,
drops a merge's second parent, so a report on a merge would invite a
destructive fix. `rebase (continue)` is the opposite case:
a conflict resolution somebody typed, holding content in no earlier commit.

**Rejected.** Excluding by action string alone. Amending a merge to tidy its
message records it as `commit (amend):`, which slips straight through.

---

## The cursor is a position in the reflog, not a sha

**Decision.** The state is the reflog entry *count*, plus the HEAD it was
written at.

**Why.** A sha is not a cursor: the same one appears in the reflog many times.
With a sha, `git commit && git checkout main && git merge --ff-only` buried the
new commit under an older matching entry, and no later run reported it. The
count is paired with HEAD because `git reflog expire` can drop exactly as many
entries as were added, which lands the count back where it started.

**Rejected.**
- Matching the stored sha, for the reason above.
- `head -50` as a window bound. It silently dropped everything older, and the
  printed count agreed with the truncated list, so nothing signalled it.

---

## An amended commit is reported twice, on purpose

**Decision.** `git commit && git commit --amend` reports two commits, one of
them a sha the branch no longer holds. This is known and deliberately left.

**Why.** It is cosmetic: the report stays true, and the surviving commit
really is unchecked. Each attempt to tidy it produced a silent miss, the one
outcome worse than an untidy report.

**Rejected.**
- Filtering to commits reachable from HEAD. It swallowed
  `git commit && git checkout main` and `git commit && git rebase main`; the
  first is the exact case the cursor design exists for. Reachability answers
  "does this sha survive"; the question is "was content authored here".
- Skipping the reflog entry just older than an amend. Excluded entries
  routinely sit between the two, so the skip landed on an unrelated commit and
  dropped it. `git commit && git rebase -i` reported nothing at all.

---

## Fails open and quiet, with exactly one exception

**Decision.** Anything the hook cannot read, it says nothing about. The one
exception is a git too old for `%(trailers:key=)`, which is announced on every
run. A repository with no reflog gets a single notice, once (below), not a
warning on every run.

**Why.** A hook that nags on every command gets uninstalled, and then nothing
is checked at all. The exception is announced because that failure makes
*every* commit look checked forever: silence there is indistinguishable from
working.

**Rejected.** Warning about a disabled reflog (`core.logAllRefUpdates=false`).
There is no activity signal to gate it on, so it would fire on every command
forever; it is a documented limit instead. The no-reflog notice fires once per
repository, and only when `logs/HEAD` is absent. An empty reflog is not a
disabled one: `git reflog expire` leaves a healthy repository with an empty
reflog.

---

## Guards on a run with no cursor are deliberately tight

**Decision.** `RECENT_SECONDS=120` and `NO_BASELINE_WINDOW=20` are one guard,
not two knobs.

**Why.** Together they bound what a first run in an unfamiliar repository will
judge. Loosening either would make that run name pre-existing commits and
advise a reset on them: a false alarm at the moment someone is deciding whether
to keep the hook.

**Rejected.** Widening `RECENT_SECONDS` to cover a commit made at the start of
a long command, and raising the window so nothing is truncated. Both close real
misses, and both cost more in noise than the misses do. When the reflog
holds fewer entries than the stored count (after expiry, gc, or a fresh clone
over the top), the run is treated as having no cursor. That fallback depends
on this guard staying tight, and is safe only while it does.

---

## The submodule walk, and its gate

**Decision.** Each initialised submodule gets the same check: the script
re-invokes itself there, with a shared message buffer. A stat gate skips the
spawn when the submodule's reflog is no newer than its own cursor, unless the
submodule has a *live* nested submodule of its own: one that is initialised,
not merely named in a `.gitmodules`.

**Why.** A submodule is its own repository with its own HEAD; a commit inside
one moves a reflog the parent run never reads. The gate exists because the hook
runs after *every* command, and eight submodules cost about 300ms on `ls`.

**Rejected.**
- Gating on the *parent's* reflog. A commit in a submodule does not move the
  parent's HEAD, and that commit is the case the walk exists for.
- Gating a submodule only on its own reflog. That is the same mistake one level
  down: the spawn is the only thing that walks *its* submodules. A commit in
  `a/inner` moves neither `a`'s reflog nor the parent's, so once both were no
  newer than their cursors, the gate skipped `a` and the commit went unseen.
- Exempting any submodule that merely has a `.gitmodules`.
  `git submodule update --init` without `--recursive` leaves one naming nothing
  initialised, and `git rm` of the last submodule leaves it tracked and empty.
  Either would cost a spawn per command, forever, finding nothing.

**Trap.** The comparison uses `find -newer`, not the shell's `-nt`. bash and
dash both compare whole seconds, so a commit a fraction of a second after the
last check reads as "not newer" and is skipped: a silent miss that happens only
sometimes.

---

## A submodule path shaped like a config key is skipped

**Decision.** In `.gitmodules`, a line matching `submodule.*.path` is treated
as a key. A submodule whose *path* has that shape is therefore never walked.

**Why.** `git config -z` gives `key\nvalue\0`, and a valueless key gives
`key\0`, so the parser tracks the previous line to stay in sync. A value shaped
like a key is ambiguous in that encoding.

**Rejected.** Telling the two apart by testing whether the line resolves to a
directory containing `.git`. That walked into *any* directory named like
another submodule's config key: it reported a plain nested repository's commits
and wrote cursor state into its `.git`. A contrived silent skip is cheaper than
reports about repositories nobody declared.

---

## Containment, before anything else in the walk

**Decision.** A `.gitmodules` path is rejected unless it resolves, via `pwd -P`,
to somewhere inside the repository.

**Why.** `.gitmodules` is an ordinary tracked file in any repo you clone, and
git's own path validation is never consulted here. A path of `..` ran the full
check on a repository the command never touched, wrote state into its `.git`, and
printed its commit subjects into the agent transcript.

**Rejected.** A string check for `..` and absolute paths. It does not see through
a symlink, and a tracked `vendor/lib -> /outside/victim` is ordinary content.
Both sides must be resolved: resolving only one silently skips every legitimate
submodule whenever the project sits under a symlinked path, such as macOS
`/tmp` → `/private/tmp`.

---

## One message buffer for the whole run

**Decision.** Everything the run has to say goes into one file. Only the
outermost invocation empties it.

**Why.** Cursor parses stdout as a single JSON document. A nested run printing
its own object made the whole payload unreadable, losing the report in the case
with the most to report, with exit 0 and no other signal.

**Rejected.** Nested runs returning only an exit code. For stderr hosts that
throws away the shas and subjects, which are the whole of what the reader can
act on.

**Traps, each of which has bitten.**
- `: >"$f" 2>/dev/null` leaks the shell's own diagnostic, because redirections
  apply left to right. Put `2>/dev/null` first.
- `:` is a POSIX **special built-in**, so a redirection failure on it aborts a
  non-interactive shell outright, `||` and all. Under dash (`/bin/sh` on Debian
  and Ubuntu) that killed the script before the guard written for that case
  could run. Wrap it in a subshell.
- Never substitute `/dev/null` as a fallback path. It reached `rm -f /dev/null`,
  which as root unlinks the device for every process on the machine.
- The delivery pipeline runs under `LC_ALL=C`, and so does the reflog `awk`.
  `logs/HEAD` stores message bytes raw, and BWK awk treats an invalid byte as
  fatal, truncating the list after the cursor has advanced.

---

## Known gap: Cursor's JSON loses double quotes and backslashes

**The gap.** Text bound for Cursor is made safe for its JSON by replacing
every `"` and `\` with a space, not by escaping them. The library does this in
its delivery and config-error paths, which also replace control characters,
and each wrapper does it in its missing-library message. A report holding
either character reaches Cursor altered: the repository's path, a commit
subject, or trailer text a verifier echoes in its reason.

**Why it is left.** No reason is recorded beyond the decision itself: the
gap is accepted as it is.

---

## The report states facts and stops

**Decision.** The report names which commits lack a trailer and which
repository they are in. For the fix, it names a section of the skill's
SKILL.md and gives no command (*Each report names its skill's section*).

**Why.** A report that built remedy commands produced 28 review findings
across eight iterations in two runs, while the half that reads the reflog and
checks the trailer produced almost none. Every finding was in the machinery
for deciding *which* command applied: root commits, detached HEAD, submodules,
rewritten history, non-contiguous commits, unquotable paths.

The frame was wrong. `check_repo` runs cd'd into each repository it inspects,
and the agent reading the report stands somewhere else. Every command had to
be computed from context this script cannot see (the reader's cwd, their
branch, what HEAD is for them), while the reader has all of it and knows git.

**Rejected.** Emitting a command only when the situation is provably ordinary.
That beats emitting one unless something looks wrong, and it still failed: the
gate certified a two-commit repository as ordinary and handed it
`reset --soft HEAD~2`, which is fatal there.

**Where this stops applying.** This is not "never give an agent a command". A
*hook* cannot give one, because it runs in a frame the reader does not occupy.
A skill running in the reader's own context has no such problem.

---

## It observes; it does not prevent

**Decision.** The hook runs *after* a command and reports. It does not block.

**Why.** Blocking requires knowing a commit is about to happen, which requires
reading the command (*Detect commits from git state, never from the command
text*). Everything that makes detection exact depends on asking git what
already happened.

**Rejected.** A `PreToolUse` hook that blocks `git commit`, and a git
`pre-commit` hook. The first has the command-text problem. The second fights
git's index lock, since the skill writes files and commits, and a headless
hook lacks the conversation's context about what the change was meant to do.

**Consequence, accepted.** The commit exists by the time anyone knows, and
undoing it is left to the reader. This is the cause of *The report states
facts and stops*: `git reset --soft HEAD~1` is correct only when the newest
reported commit is HEAD, which it often is not.

**Trap: the prose must withhold the remedy too.** Deleting every computed
`git -C` command while keeping the closing sentence "re-commit with one — or
amend a trailer in if the check does not apply" keeps the same conditional
advice, in a form that reads as harmless boilerplate. Following it after
`git commit && git checkout main` writes a `Bug-hunter:` trailer onto an
unrelated, already-checked commit and rewrites its sha, while the reported
commit keeps none and, the cursor having advanced, is never reported again.
The same edit left three docs stale: `SKILL.md`'s overview, `README.md`'s
trade-off paragraph, and `SKILL.md`'s triage table saying "reset it back to
the index **as the report describes**". The last one was found a pass later
than the others. A stale `SKILL.md` is worse than an ordinary stale doc,
because it is in the agent's context and supplies the command the report
withholds.

**Nothing tests this.** Four passages asserted what the report contains, and
one edit falsified all four in silence. A test that generates a report and
checks every command the docs attribute to it was considered and not built;
this paragraph stands in for it. Treat "the report says X" in any doc as a
claim to re-check against the report, and grep those docs for it whenever the
report text changes.

**What the report may say.** The rule is not "no imperatives". Everything in
the report must be true wherever the reader stands. "Ask before rewriting a
pushed commit", the name of a SKILL.md section and the `disable-hook` command
all are. A remedy for the named commit is not.

---

## Each report names its skill's section

**Decision.** When commits lack a valid trailer, each skill's report has four
short parts:

1. The commits, and what is wrong with them: no trailer, a trailer line git
   does not read as one, or a trailer that fails verification.
2. "Ask before rewriting a pushed commit." Adding a missing trailer means
   amending or rebasing, which may rewrite published history.
3. "Fix it with the <skill> skill's *<section>* steps", naming no file path.
4. The one-line `disable-hook` command, given as a person's choice: a person
   who does not want the check turns it off, not the agent.

It restates nothing from SKILL.md: not where a trailer sits, nor the commit
script, nor the skip value, nor how a trailer is signed or minted (issue #38).

**Why.** The agent reads the report and then fixes the commit, so it needs the
skill's steps anyway, and SKILL.md is the copy that is kept true. A
self-contained report would repeat SKILL.md, drift from it, and run long. For
one reported commit whose `<hash> <subject>` line is 30 bytes, bug-hunter's
self-contained report measured 1,119 to 2,092 bytes depending on the case,
against 355 to 433 for this form; prose's and spec-check's measured 465 to 724
bytes, against 310 to 415.

**Which section.** Each report names its own skill's section: prose's
*Committing*, spec-check's *Commit*, and bug-hunter's *If you are an agent
about to commit*. bug-hunter's other candidate, *Step 9 — Report and commit*,
assumes a run has just happened. *If you are an agent about to commit* is
written for an agent that has not run one: it leads into triage, and triage
sends a commit with nothing to review to the skip value.

**Rejected.** Renaming the three sections to one shared name such as
*Committing*. bug-hunter's DECISIONS.md and reference.md link to its section
anchors, and a rename would break those links and any outside them. Naming
each skill's own section costs nothing and is cheap to change.

**Out of scope.** The worktrees skill's hooks, whose messages are short, and
spec-trace's hook, which speaks only once per repository, to ask whether to
adopt spec-trace.

---

## The trailer is minted from the tree, not recalled by the agent

**Decision.** Every `Bug-hunter:` trailer that is not a skip note
(`skipped at triage (...)`) must be paired with a `Bug-hunter-Tree:` trailer
whose value is the landed commit's tree hash: the value `scripts/mint-trailer.sh`
prints when run against the staged index just before `git commit`. That covers
`N bugs fixed`, `0 bugs found` and `aborted ...` alike. The hook checks the
binding only for a commit whose reflog action is `commit:`,
`commit (amend):` or `commit (initial):`. A mismatched or absent binding is
reported in its own paragraph, apart from a missing trailer.

**Why.** An agent fixed a genuine bug in another repository, wrote a real
regression test, watched it fail on the unfixed code for the predicted reason,
applied the fix and watched it pass: an honest red-then-green proof, done
entirely outside bug-hunter. It then ran
`git commit --trailer "Bug-hunter: 1 iteration, 1 bug fixed"`, because the
string matched the shape the skill documents. It was caught only because a
person asked "was this checked by bug-hunter?". A hook that asks only whether
a `Bug-hunter:` trailer exists cannot catch that: the trailer was real and
well-formed. Nothing observable from outside the agent distinguishes "this
ran" from "I recall what this looks like when it runs", except that the right
tree hash for a commit that does not exist yet comes only from running
`git write-tree` against the staged state at that moment. It cannot be
recalled; it has to be computed, every time.

**How the hook reads the trailers.**
- **The binding is checked for root commits.** `commit (initial):` is a root
  commit's reflog action (confirmed on a real repro). Without it in the list,
  a repository's first commit could carry a fabricated trailer and never be
  reported.
- **Only the last trailer of each key counts.** The hook reads
  `%(trailers:key=...,valueonly,unfold)` and takes the last line. `,unfold`
  joins a wrapped value's continuation lines into one line and leaves
  separate trailers on separate lines, so the last line is the last trailer,
  not a fragment of one. Without `,unfold`, a continuation line and a second
  `Bug-hunter:` trailer are indistinguishable.
  - For `Bug-hunter-Tree`, this keeps the documented repair working. `--trailer`'s
    default (`addIfDifferentNeighbor`) appends rather than replaces, so minting
    again and passing `--trailer` a second time leaves two lines. Joining every
    value, with no separator, made an 80-hex string that could never match.
  - For `Bug-hunter:`, it decides whether the commit is a skip. Tested against
    every value joined, a skip test that matched on a leading "skipped" let
    `skipped at triage (docs only)` followed by `1 iteration, 1 bug fixed`
    pass with no binding. The last trailer on a commit is the one a person
    reading it takes as authoritative, and it is the one the hook takes.
- **A message-only amend of a replay is not reported.** Amending a message
  never changes the tree, but it records the action as `commit (amend):`, the
  same laundering the merge parent-count check exists for. By the time of the
  amend, the hook has usually run on the replay itself and moved the cursor
  past it, so the hook searches the *whole* reflog for a replay action that
  landed this exact tree. Searching only the current window still reported a
  real replay followed by a message-only amend as fabricated.

**What the binding rules out, and what it does not.** It rules out
*recollection*: writing the trailer from having read the docs, with no command
run, which is the incident above. It does not rule out reconstructing the hash
after the commit exists. `git rev-parse HEAD^{tree}` prints the value
`mint-trailer.sh` would have, with no staging and no run of anything bug-hunter
ships. bug-hunter's README gives that command as the repair for an honest
binding gone stale, and it "repairs" a purely fabricated trailer exactly as
well. This is true of the mechanism itself: nothing computable from the hash
alone proves *when* it was computed. Closing it needs the deferred
delegation check below, not a sharper version of this one. bug-hunter's
`reference.md` and `README.md` state this limit plainly.

**Honest runs that can drift.** These are not bypasses:
- A pre-commit hook that reformats or restages files changes the tree after
  the mint reads it. The commit script runs the hook before minting (*The
  pre-commit hook runs before anything is bound*). For a commit made by hand,
  the repair in bug-hunter's `reference.md` and `README.md` still applies.
- `git commit -- <pathspec>` or `git commit -a` can land a tree other than the
  one minted, if anything else was staged, or tracked and unstaged, at the
  time. bug-hunter's `reference.md` and `README.md` say to avoid both.

**Deferred: verifying delegation itself.** A `SubagentStop` or
`PostToolUse`+`Task` hook could record real completions of bug-hunter's
Step 3 find pass and Step 5 refute pass, keyed on a run token in the subagent's
prompt. It is the only mechanism that would attest to *delegation* rather than
to *content*. It is not built, for concrete reasons:
- It cannot be tested from inside the session that builds it. Hooks load at
  session start (see `hook-development`'s docs), so a newly wired
  `SubagentStop` entry never fires for the session that wired it, and there is
  no way to drive a real repro before shipping.
- The transcript and tool-result shape it would key on must not be guessed.
  Reflog action strings come from real repros only, because four guessed ones
  (`rebase (label):`, `rebase (onto):`, `rebase (skip):`, `rebase (drop):`)
  do not exist in git. The same standard applies to a host payload that cannot
  be reproduced from here.
- `hook.json`'s manifest wires exactly one event per platform per skill. A
  second would mean extending `manage-skills`' installer, shared
  infrastructure with its own test suite that every installed skill goes
  through, to fix a gap in one skill, with a mechanism that cannot be verified
  before it ships.

If it is built, it does not replace this entry: it would attest that a
delegation happened, which this binding does not claim. They are two claims,
not two implementations of one.

**Consequence, accepted.** `git write-tree` is not a read. It writes a tree
object for the staged index into the repository's object store. Everything
else in this hook family only asks git questions; this is the one part that
writes. Nothing references the object until a commit lands on that exact
tree, so it is ordinary `git gc` litter, not a correctness problem. It is
noted here so that unexplained objects in `git count-objects` output have an
explanation.

**Rejected.**
- A marker file, or a self-reported run token, that the agent writes to say
  steps 1, 3 and 5 ran. bug-hunter's DECISIONS.md rejects this shape in *The
  hook is never told that a run is in progress*, for the same reason: a flag
  the checked party writes at will gets set out of habit, not honesty. The tree
  hash differs in kind: it is computed by `git write-tree`, not asserted.
  Before the commit exists, no value that looks right can be written from
  memory: any plausible hash, right or wrong, comes only from running that
  computation against some tree. After the commit exists, see *What the
  binding rules out*.
- Inferring "a fix happened" from the diff's shape, for example by requiring a
  test-shaped file among the changed paths whenever the trailer claims a fix.
  Rejected without being built: this file records the same class of guess
  (reflog actions, `.gitmodules`-key-shaped paths, command-text matching)
  producing a silent gap or a false alarm the moment a real repository did not
  match the guessed shape. A cross-language, cross-framework guess at "is this
  a test file" is that class of guess.
- Requiring the binding only on trailers that claim a fix, on the theory that
  a fabricated fix is the high-stakes lie and `0 bugs found` not worth the
  false-alarm risk. The stakes are whether the check can be sidestepped by
  choosing different words, and under that scope it could be. The agent in
  the incident above would stay unreported by writing
  `Bug-hunter: 1 iteration, 0 bugs found`, five characters from the fabricated
  trailer, with no mint and no script; and that sentence is *more* plausible
  for an agent that ran nothing. It is a one-word bypass of the whole check,
  not a narrower version of it.
- Requiring the binding on cherry-picks and rebase replays too. Cherry-picking
  or rebasing a commit that carries a valid trailer copies the message, trailer
  and now-stale binding both, onto a different tree, so every such replay would
  be a false alarm. Confirmed on a real repro: a clean cherry-pick's action is `cherry-pick:`, a
  conflicted one's `commit (cherry-pick):`, a clean rebase replay's
  `rebase (pick):`, a conflicted one's `rebase (continue):`. None matches the
  checked actions, so the cherry-pick, rebase and merge exemptions are
  untouched.

**Where this stops applying.** The binding attests only that
`scripts/mint-trailer.sh` ran against the tree that landed. It does not attest
that bug-hunter's Step 1 triage, Step 3 find pass or Step 5 refute pass
happened, or that the counts in the `Bug-hunter:` trailer are honest: an agent
that runs the mint once and writes whatever counts it likes still passes. It
closes one gap, a trailer whose *shape* is all that was produced. Whether the
delegation happened is the deferred mechanism's question.

**The remaining bypass, named.** A skip note is the one exemption, so writing
`Bug-hunter: skipped at triage (docs only)` on a commit that is not docs-only
is the cheapest evasion. This is accepted. A false skip note is visibly wrong
to a person reading `git log` beside the diff, as a plausible `0 bugs found`
is not. Two rules in bug-hunter's DECISIONS.md already cover it: the
announce-out-loud rule in *Every anti-evasion rule was added after it was
walked through*, and *Triage reads the diff, not a label*, under which a skip
comes from what the diff touches, never from the commit message. A binding
for skip notes has no tree to bind to: triage runs before anything is staged
for review. All it could attest is that triage ran, which is Step 1's
delegation, the deferred mechanism again.

---

## The rebase apply backend is not reported

**Decision.** `rebase (pick):` never counts as authorship.

**Why.** The default merge backend writes `rebase (continue):` when someone
resolves a conflict by hand, and that is reported. The apply backend
(`rebase.backend=apply`, `git rebase --apply`, and, without saying so,
`--whitespace=<mode>` or `-C<n>`) writes `rebase (pick):` for that same
hand-typed resolution, which is indistinguishable from a plain replay. Nothing
per-commit survives to tell the two apart.

**Rejected.** Excluding `rebase (pick):` less aggressively. Every ordinary
`git rebase main` would then re-report each replayed commit: repeated noise
nobody can act on, on the most common rebase there is, to cover an opt-in
backend.

---

## One commit, several families

**Decision.** `commit-with-trailers.sh` takes any number of trailer families
and makes one commit carrying all of them. A family is a key, a value and a
binding, of one of two kinds:
- *minted*: a `<Key>-Tree` line made here from the staged tree, by
  `mint-trailer.sh` or a skill's wrapper around it;
- *verified*: a value the skill signed earlier
  (`Prose: ✓ <12 hex tree>:<12 hex message>`), accepted only if the skill's own
  verifier, named as `--verified-value`'s first argument, says it still matches
  the staged tree and the message (see
  [A family whose value is its own binding](#a-family-whose-value-is-its-own-binding)).

For every family it refuses an empty subject, an empty or multi-line value,
and a failed or noisy mint, and it pins the trailer config. The order is:
validate everything, check every tool exists, run the pre-commit hook (*The
pre-commit hook runs before anything is bound*), run every verifier, run every
mint, commit. A stale binding in the last family stops the commit before
anything is minted.

**Why.** bug-hunter and prose each put a claim and its proof on the same
commit. With two scripts, each would run `git commit`, and the second would
have nothing left to commit; an amend in between would rewrite the commit the
first binding was minted for. One assembly step is the only order in which
both bindings are true of the commit that lands. And each guard in
bug-hunter's DECISIONS.md, *The commit is assembled by a script, not by hand*,
was found by a run, not by reading; a second script for prose would have to
find them again.

**Why a verifier, not a second mint kind.** prose's binding hashes the staged
tree *and the message*, and `prose check` makes it before the commit, when
prose has read the text. The library cannot recompute that without knowing
prose. So the extension point is an executable the family names. It runs with
the trailer line `<Key>: <value>` as its argument, from the caller's
directory, with the message on stdin: the subject, then a blank line and the
body if there is one, byte for byte as passed, no trailers. Exit 0 means it
matches. A minted family never takes a handed-in line: that would let a
recalled `Bug-hunter-Tree` through the extension point, the exact failure the
mint exists for.

**Keys are kept apart.** git treats two trailer keys as one when the shorter,
ignoring case, is a prefix of the longer, dash or not. So `Bug-hunter`
"exists" whenever `Bug-hunter-Tree` does, a family keyed `Bug-hunter-Tree`
would collide with bug-hunter's binding, and `Pro` and `Prose` are the same key
to every `ifexists` rule and `trailer.<key>.*` setting git applies. A family's
key may not be a prefix of another's, which also keeps every `<Key>-Tree`
binding apart. The commit itself does not depend on this, because of the pin
below. But a later amend with `--trailer` runs git's defaults again, and a key
inside another family's namespace would read as that family's binding.

**`trailer.ifexists=add` is pinned**, not git's default
`addIfDifferentNeighbor`. The default compares each new trailer with the one
before it, by that prefix match and by value ignoring case, and drops a match
as a duplicate. A family whose value equalled its own separate binding line
(`Demo: abc123`, `Demo-Sig: abc123`) lost the binding, exit 0. Every trailer
this script passes is wanted, so none is compared. `addIfDifferent` would be
worse: it compares with every trailer under that key. The one cost is that a
trailer passed twice lands twice: the same `--co-authored-by` twice, or a
trailer typed into the body and also passed.

**`trailer.where=end` is pinned** alongside `ifexists`, `ifmissing` and
`separators`. `where=start` loses no trailer, but it reverses the block, so a
family's binding sat above its key.

**A missing argument is not a value.** Each option takes a fixed number of
words, so when one vanishes (an empty variable left unquoted), the next word
is taken in its place. Before `--` that is the separator itself:
`--minted Bug-hunter $v -- ...` committed `Bug-hunter: --` with a real binding,
exit 0. When two vanish in a row it is the next option's name:
`--minted Bug-hunter $v --co-authored-by $c -- ...` committed
`Bug-hunter: --co-authored-by`, and so did the same line without `--`. So the
script's `takes` function, which consumes each option's words, refuses any
that is `--` or an option name: `--minted`, `--minted-by` (a minted family
whose minter is a skill's own wrapper), `--verified-value`,
`--co-authored-by`, `--message-file` or `--allow-empty`. Other free text
starting with `--` stays a legal value (`--dry-run fixed`).

**`--` before the subject is required.** Without it, a vanished value next to
an unquoted two-word subject balanced the count:
`--minted Bug-hunter $v $s "$b"`, with `$v` empty and `$s` `FEAT: x`,
committed `Bug-hunter: FEAT:` bound, subject `x`, exit 0. With `--` required,
every word before it is an option, a word an option takes, or `--`. A word
that vanished pulls `--` or an option name into an option, which is refused
above; a word that split lands where `--` or an option must be, which is
refused.

**A tool is a path.** A minter or verifier named with no slash is refused as
an argument error. The existence check reads the file in the current
directory, but the shell runs a bare name from `PATH`, so a verifier beside the
caller passed the check and then failed as a stale binding.

**Rejected.**
- Each skill calling the next skill's commit script. That nests one skill's
  interface in another's, and the order of nesting becomes a dependency.
- Families passed as `Key=value` strings or a config file. The value is free
  text; a separator inside it, or a file the agent writes, reopens the hand
  assembly this script exists to close. Options with a fixed number of words
  parse with no escaping.
- Verifying by re-running the skill's mint and comparing. Only the skill knows
  whether its binding can be recomputed at commit time; a verifier can do that
  itself or check something cheaper.
- A family with no binding kind. Every family is minted or verified; the only
  unbound trailer is `Co-Authored-By`, which asserts nothing a skill checks.
- A verified kind whose binding is a separate `<Key>-<suffix>` line, such as a
  `Prose-Sig` line beside `Prose:`. No skill needs one: prose carries its
  signature in its value (*A family whose value is its own binding*). To add
  it for a skill that does: parse it as `--verified <verifier> <Key> <value>
  <binding line>`; check the binding line (keyed `<Key>-<suffix>`, one line, a
  non-empty value, absent for a skip note and required otherwise); pass that
  line to the verifier and land it after the value; add `--verified` to the
  option names `takes` refuses; and test it, including a value equal to its
  own binding. `git log -S '--verified)' -- commit-with-trailers.sh` lists the
  commits holding an earlier implementation.

**Consequences.**
- bug-hunter's `commit-with-trailer.sh` is a thin wrapper, like the check and
  the mint, and its messages come from here. It refuses, exit 2, a Bug-hunter
  or Co-Authored-By value that is exactly `--` or one of the option names above
  (see *A missing argument is not a value*). Like the other wrappers, a copy of
  the skill without the clone around it has no library and says so, exit 1, so
  such a copy cannot commit at all, not even a `skipped` value.
- bug-hunter's `test_a_failed_mint_never_reaches_git_commit` and
  `test_a_noisy_mint_never_lands_a_multi_line_binding` put a stub mint beside a
  copy of that script, and copy the library beside it too, laid out as in the
  clone. Copied alone, the script finds no library, so the first test would
  fail, and the second would pass only because "library missing" is also
  exit 1. The alternative, giving the wrapper a mint path of its own, is the
  second copy *One library, a thin wrapper per skill* rejects.
- A verifier is trusted code, run with the caller's environment: the family
  names it, so the caller chose it.

**Where this stops applying.** A verifier sees the message as passed, not as
git stores it: git's cleanup trims trailing whitespace and collapses blank
lines, and `commit.cleanup` can do more. A skill that hashes the message must
mint and verify over the same raw form, or normalise both the same way.
Nothing here checks the stored message against the binding afterwards; that is
the skill's hook, if it has one. And a skill whose binding is neither a tree
hash nor checkable before the commit exists fits neither kind: it needs a third
kind, not a stretched verifier.

---

## The result block is printed by a script

**Decision.** A skill whose caller makes the commit ends with a result block,
which `result-block.sh` prints. The skill passes its name, whole trailer lines
after `--`, and its open decisions, one per line, from a file or stdin
(`--decisions -`). The script checks every line, numbers and counts the
decisions, and prints the block only once every check has passed. It is the
format's one definition. Each skill calls it through a wrapper that supplies
the trailer lines: bug-hunter's `caller-result.sh` mints `Bug-hunter-Tree`
first, and `prose check` prints its one line,
`Prose: ✓ <12 hex tree>:<12 hex message>`, the same way.

**Why.** A block the agent types, copying the mint's output into it, is hand
assembly, and bug-hunter's DECISIONS.md, *The commit is assembled by a script,
not by hand*, records how that fails: hand-typed trailers went wrong under
pressure, however the rule was worded. A hand-typed block that a caller's
program then parses fails in the same ways: a trailer retyped, a count that
does not match the lines, a tree line from an earlier mint.

**What it refuses, and why.**
- A trailer line that is not `Key: value`, whose key is not letters, digits
  and dashes starting with a letter, or whose value is empty. The caller
  passes the line to git as a trailer, and git would drop or misread it.
- A line break in a trailer line or a decision. git does not fold a
  multi-line trailer, and a caller reads the block line by line.
- A decision starting `===`. A caller would read it as a marker.
- A decisions file that is missing or unreadable, exit 1. Read as empty, it
  would tell the caller nothing is open, and the caller would commit.
- A missing argument: no trailer line, no `--`, or `--decisions` followed by
  `--` or nothing. An empty unquoted variable vanishes from the command line,
  and without these checks the next word would take its place, as in *A
  missing argument is not a value*.

Unlike `commit-with-trailers.sh`, this script lets keys be prefixes of one
another: `Bug-hunter` and `Bug-hunter-Tree` are one family by design. It
prints lines, and makes no commit for git's trailer rules to act on.

**Rejected.**
- **A documented format each skill prints itself.** Two skills printing one
  format are two copies, and they drift: a marker spelled differently, a count
  left off, a skip that still prints a tree line. And each copy is a place the
  agent assembles by hand.
- **Numbering left to the agent.** The count and the numbers would then be
  typed, and could disagree with the lines.
- **Decisions as arguments.** A decision holds free text (dashes, `·`,
  quotes), and there can be none or several; one per line in a file or a
  heredoc needs no quoting.

**Where this stops applying.** The script prints to stdout. The agent then
relays that into its reply, and a caller parsing the reply gets whatever the
relay kept. Each skill says to end with the output whole and unedited, and
nothing enforces it. The script checks the shape of a trailer line, not its
truth: a binding line is as good as the wrapper that minted it.

---

## Known gap: per-key trailer config outranks the pins

**The gap.** The commit pins `trailer.ifexists`, `ifmissing`, `separators` and
`where` for the one command, but those are git's general settings. A user's
per-key setting for a key this script writes outranks them:
`trailer.bug-hunter-tree.ifexists=replace`,
`trailer.bug-hunter-tree.ifexists=doNothing`,
`trailer.bug-hunter.ifmissing=doNothing`. Because git matches keys by prefix,
`replace` on the binding's key overwrote the `Bug-hunter:` line with the
binding, and `doNothing` dropped the binding. The script exits 0, and the hook
then reports a correctly run commit as unchecked or as carrying a fabricated
trailer.

**Why it is left.** It takes deliberate per-key config naming these exact
keys, and nobody has any. Nothing has ever hit it.

**The fix, if it is needed.** Pin the per-key setting too, for every key the
script writes (each family's key, its binding's key, and `Co-Authored-By`):
`-c trailer.<key>.ifexists=add -c trailer.<key>.ifmissing=add
-c trailer.<key>.where=end`. Check first that adding a `trailer.<key>.*`
section does not change how git matches that key: a section with no `.key`
value uses its name as the key.

---

## Known gap: an empty body beside a split subject after `--`

**The gap.** After the `--`, `commit-with-trailers.sh` takes exactly two words,
subject and body. A caller that leaves both unquoted, with the body empty and
a two-word subject (`-- $s $b` where `s="FEAT: x"`, `b=""`), hands it `FEAT:`
and `x`. The count balances, so the commit lands, exit 0, with subject `FEAT:`
and body `x`. The trailers and their bindings are still correct; only the
message is mangled.

**Why it is left.** No parser can tell those two words from a real subject and
body. The defence is quoting: pass `"$subject" "$body"`, as bug-hunter's
wrapper does.

**Where this stops applying.** Before the `--`, the same slip is refused: a
vanished or split word there lands where `--` or an option must be (see *A
missing argument is not a value*). With `--message-file` there is no subject
or body word to split (see *The message comes from a file*).

---

## The message comes from a file

**Decision.** `commit-with-trailers.sh --message-file <path> --` reads the
message from a file: the first line is the subject, the next line must be
blank, and the rest is the body. bug-hunter's wrapper takes `-F <file>` in
place of `<subject> <body>` and passes it through. prose's and bug-hunter's
SKILL.md show this form first; the two-word form also works.

**Why.** A multi-line message passed as shell arguments has to be quoted, and
agents get the quoting wrong: apostrophes need `'"'"'`, and `$`, backticks and
`--` inside a message change what the shell or a reader makes of the command.
Claude Code also refuses a command its guard cannot parse with confidence, and
on 2026-10-03 it refused commits here repeatedly on exactly that kind of
message. The message already exists as a file, because prose signs `msg.txt`.
Reading that same file means the text the verifier checks is the text prose
signed, with no retyping in between.

**Rejected.**
- *Teaching agents the quoting rules.* That fixes one shell, not the guard, and
  every new rule is one more thing to get wrong.
- *A heredoc into the script.* The message text is still inside the command,
  which is what the guard refuses; and stdin is already the verifiers' channel.
- *The option after `--`, in place of the two words.* The option goes before
  the `--`, with nothing after it, so a vanished path is refused like any
  vanished option word (`--message-file --` is a missing argument), and a stray
  word after the `--` is refused as "not both". The option written after the
  `--` (`-- --message-file <path>`, or `-- -F <path>`) is refused too, rather
  than committed as a subject. bug-hunter's wrapper likewise refuses any other
  dash-led word where the subject goes (`-Fmsg.txt`, `--message-file=…`), so a
  subject there cannot start with `-`.

**Where this stops applying.** The file is passed to git as `-m` paragraphs,
as the two-word form is, so git's comment-line stripping does not apply: a file
holding `#` lines commits them. Blank lines before the subject are dropped, as
git's cleanup and prose's signing drop them. Blank means spaces, tabs and CRs
only, as git and prose count it: a line of `\f` or U+00A0 is text, so it is
never dropped. As the subject, such a line is refused as empty, as in the
two-word form; git would accept it, but no real subject is only a form feed. A
first line followed by a non-blank second line is refused, because git would
read both as one subject.

---

## A skill may verify its own trailer

**Decision.** A skill's report file may define
`commit_trailer_verify <sha> <value>`. When it does, the hook calls it in place
of the `<Key>-Tree` check, for every plain commit or amend that carries the
skill's trailer, skip notes included. Returning 0 means valid; 1 means
invalid, with the reason on stdout; any other status is reported as "could not
be verified". A callback that exits instead of returning has not answered.
Failures go in the fact variable `rejected` (`sha subject -- reason` lines),
which the skill's report and the fallback report read. A skill that does not
define the function gets the `<Key>-Tree` check, as bug-hunter does.

**Why.** A skill signs the snapshot it worked on, and whatever reads the commit
verifies against that snapshot. prose's snapshot is the tree *and* the message
(`Prose: ✓ <12 hex tree>:<12 hex message>`), which the tree comparison cannot
check. A second copy of the reflog walk to host prose's own check is the drift
*One library, a thin wrapper per skill* exists to prevent.

**Kept from the tree check, on purpose.**
- The same scope: plain commits and amends only, never a replay, and never a
  tree some replay landed. A cherry-pick or rebase carries an older trailer
  onto new content, and would otherwise be reported as fabricated. Scope is
  decided before the answer is read: a message-only amend of a replay is exempt
  whether the callback said invalid or could not verify.
- The callback runs in a subshell with stderr closed, for the reason the report
  is built in one: under dash, a syntax error in a sourced file kills the hook
  after the cursor has moved.
- The file runs without the hook's `set -u`, in every subshell that sources it
  (the check for the callback, the callback, the report). Under `set -u`, an
  unset read aborted the callback before it returned. Under bash that is exit
  1, so a commit the skill accepts read as rejected with no reason; under dash,
  exit 2. In the check for the callback, the same abort silently fell back to
  the tree check.
- A status other than 0 or 1 is said out loud. A callback that was found but
  could not run to a return (no `python3`, an `exit`) must never read as a
  pass.
- What the file prints as it loads is discarded where it is sourced only to
  check for or call the callback. The check's stdout is the hook's own, which
  Cursor reads as one JSON object, and the callback's stdout is its reason,
  which must be only what the callback printed. The report's `$( … )` already
  captures it.
- The file's load must run to the end, and each subshell proves it did with a
  last line printed after the `.` and the call. An `exit` in the file, which
  *The skill's report is built in a subshell* allows for, ends the subshell
  with its own status. Without the last line, `exit 0` read as "has a
  callback" and then as "valid", so a verifier that never ran passed, even for
  a skill that defines no callback. In the check for the callback, no last
  line means "no callback": the tree check runs, as it does for a syntax error.
  In the callback, no last line means "could not be verified (the callback did
  not return, exit N)", whatever N is: an `exit 1`, or `set -e` stopping the
  callback, is not the callback saying "invalid". The same holds for a
  callback that calls `exit` itself. Under the file's own `set -e`, a
  callback's `return 1` also reads as "could not be verified", not
  "invalid": POSIX sh cannot tell an intended
  non-zero return from an aborted command, and calling the callback where
  errexit is off (`if`, `||`) would turn an abort into a pass. The commit is
  still reported; a report file that wants "invalid" to read as "invalid" does
  not use `set -e`.
- The callback's last line carries a marker new on every run. It follows the
  callback's own output, which can quote the trailer value. With a fixed
  marker, a value ending in `<marker>0` passed for a callback that echoed it
  and exited.

**Rejected.**
- A per-skill binding key, such as `COMMIT_TRAILER_BINDING=Prose-Sig` for a
  separate signature line. It would still compare a value to the tree, which is
  not what prose signs.
- Running the callback in a fresh `sh` instead of a subshell. It would keep all
  of the hook's shell state out of skill code, not only `set -u`; but the
  report function needs the hook's fact variables, so the callback and the
  report would run under two different contracts. `set +u` covers the one
  option the hook sets. If the hook ever sets another, revisit this.
- `trap 'exit 3' EXIT` in the subshell instead of a last line. The file is
  sourced after the trap is set and can replace it.
- The status through a temporary file, keeping it off the callback's stdout
  altogether. That is a file to create, clean up and fail on, for what a marker
  the value cannot contain already gives.
- Letting the skill see replays and decide for itself. Every skill would have to
  re-derive the replay rules this file already paid for.

**Where this stops applying.** The callback decides validity. It does not
change which commits are judged, how the cursor moves, or what counts as a
missing trailer. A skill whose check needs more than the sha and the trailer
value (the reflog, other commits) needs a different hook, not a longer
callback.

---

## A family whose value is its own binding

**Decision.** `commit-with-trailers.sh` takes
`--verified-value <verifier> <Key> <value>`: a family whose trailer value is
itself the binding, with no `<Key>-<suffix>` line. The verifier runs from the
caller's directory, with the message on stdin and the trailer line
`<Key>: <value>` as its argument. Every other guarantee holds: `takes`, the
required `--`, the prefix-key refusal, validation before side effects,
verifiers before mints, and the pinned trailer config. A skip note is not
verified.

**Why.** prose signs the snapshot it worked on, the staged tree and the
message, and puts the signature in its own value, `Prose: ✓ <tree>:<message>`.
One line carries the claim and its proof, so a reader cannot keep one and lose
the other. The commit script must still refuse a stale signature before
anything lands, because whatever commits verifies against the snapshot the
skill signed.

**Rejected.**
- A separate binding line beside prose's value (see *One commit, several
  families*), filled with a dummy. It lands a second trailer that means nothing
  and invites someone to "fix" it.
- A `--plain <Key> <value>` family with no check. It is a hand-assembled trailer
  with extra steps: nothing would refuse a signature minted over another tree.
- Having the library parse `✓ <tree>:<message>` itself. That is prose's format;
  the library would have to change whenever prose's does.

**Where this stops applying.** The verifier sees the message as passed, not as
git stores it (see *One commit, several families*). A skill whose value cannot
be checked before the commit exists does not fit this family either.

---

## Every installed skill's trailer, on one commit

**Decision.** Skills that sign commits with a trailer through this library
commit once, through `commit-with-trailers.sh`, with the trailer of every such
skill that is installed. Each skill's commit step forwards the others' values
as families, so an agent following any one skill's procedure lands every
trailer. A skill's SKILL.md points here for the rule rather than restating it;
it names only the skills whose values its own commit step forwards, and how to
tell each is installed.

The three skills:
- **bug-hunter's** commit step asks the `manage-skills` skill (`list`) whether
  prose is installed. If it is, it runs prose's two `check` calls on the final
  staged change and message, and passes the `Prose:` value to
  `commit-with-trailer.sh` as `--verified-value`, which forwards it here.
- **prose**, while bug-hunter is running, leaves the commit to bug-hunter's
  commit step. When the agent commits itself, it calls this script with both
  families.
- **spec-check**, on a commit that changes `openspec/`, passes its
  `Spec-check:` value as one more `--verified-value` family: to bug-hunter's
  `commit-with-trailer.sh` beside prose's, or to this script directly.
  bug-hunter's and prose's SKILL.md point to spec-check's for the step.

**Why.** Each skill's hook reports a commit missing its trailer. Following one
skill's procedure alone would commit without the others' trailers, and their
hooks would report it; combining them by hand means piecing a command together
from several documents. A later commit or amend cannot add the missing trailer
without breaking the first one's binding (*One commit, several families*).

**Installed** is what the `manage-skills` skill's `list` reports, not a
judgement and not a path check a skill repeats. `manage-skills` owns where
skills are installed, so a skill that asks it stays right when it adds a
platform. In a worker of Igor (an agent runner whose workers load the skills
from a pinned plugin), `list` reports the home directories, which are
empty there, not the pinned plugin the skills were loaded from. That is left as
it is, because Igor's commit steps use caller commits, where this check does
not run; revisit it if a worker commits itself.

**Rejected.**
- The glue in the `commit` skill. Adam does not use it, and an agent
  reaches each skill's own commit step whether or not `commit` is installed.
- A registry the library reads and runs. A skill's signing is not one command:
  prose's is a rewrite between two calls, which only the agent can do.
- Every skill's SKILL.md listing every other skill and why. The why is here;
  a SKILL.md carries only the commands its commit step runs.

**Where this stops applying.** Under bug-hunter's *caller commits*, nothing in
the skill commits: the caller does, and carries the families. A skill whose
binding fits neither family kind needs a third kind before it can join.

---

## The pre-commit hook runs before anything is bound

**Decision.** When the repository has a pre-commit hook and a value is bound,
the hook runs before any verifier or mint: validate, check tools, run the
hook, run verifiers, run mints, commit. `commit-with-trailers.sh` hands this to
`commit-with-hooks.sh`, which runs the hook through `run-pre-commit.sh` as
`git hook run --ignore-missing pre-commit` (honouring `core.hooksPath`, from
the top of the work tree), and then commits without running it again (*The
pre-commit hook runs once per commit*). With no hook, nothing runs early.

**Why.** Every binding is a hash of the staged tree, made before `git commit`.
A formatter in the pre-commit hook (prettier, black, lint-staged, the
pre-commit framework) can rewrite and restage files. Run by `git commit`, after
the bindings, it would land a tree nobody bound, and the hook would report an
honest commit as unminted. Running the hook first is the one ordering that
avoids this.

**How each hook is handled.**
- **No hook**: nothing runs early and nothing is printed.
- **Exits 0, index unchanged**: carry on.
- **Exits 0, index changed** (lint-staged, or any formatter that restages;
  detected by `git write-tree` before and after): carry on, and say so on
  stderr. Verifiers and mints run after it, over what it left staged, so the
  bindings are of the tree that lands.
- **Exits non-zero**: refuse, exit 1, before any verifier, mint or commit.
  The hook's output is already on stderr, followed by the advice to review
  its changes, stage what belongs, and try again. This covers a check that
  fails, and the pre-commit framework's formatter, which rewrites files,
  leaves the rewrite unstaged and fails ("files were modified by this hook").
- **Exits 0 after changing only the work tree**: nothing unstaged is
  committed, so every binding is still the tree that lands. Nothing to do.

**A value signed before the commit script ran goes stale.** A
`--verified-value` family (prose) was signed by its skill before the hook ran
here. If the hook changed the index, that signature no longer matches, and its
verifier refuses: correct, since it signed content that will not land. The
refusal says the pre-commit hook changed the staged files after the value was
made, so the agent knows to review the hook's changes and sign again rather
than retry blindly. A skill that signs before committing avoids this by
running `run-pre-commit.sh` itself first, then signing. The commit script then
finds the pass recorded and does not run the hook again (*The pre-commit hook
runs once per commit*).

**`run-pre-commit.sh` is the shared piece.** Exit 0 prints one word, `changed`
or `unchanged`; exit 1 prints nothing on stdout and the reason on stderr. The
commit script uses the word to choose its refusal message. `prose check` calls
it before listing and before signing, so the signature is made over the
formatted tree.

**Only when something is bound.** When every family's value is a skip note,
nothing is minted or verified, so the early run is skipped and `git commit`
runs the hook once, as in a plain commit.

**Older git.** `git hook run` arrived in git 2.36. On older git,
`run-pre-commit.sh` looks for a hook at
`git rev-parse --git-path hooks/pre-commit` (which honours `core.hooksPath`).
If there is an executable one, it refuses: the binding cannot be made after
it, and committing anyway is the failure this entry exists for. If there is
none, the commit goes ahead. Refusing outright on older git is rejected:
Ubuntu 22.04 ships 2.34, and a repository without a hook has nothing to fix.

**The hook's environment differs from a real commit's.** During `git commit`,
git sets `GIT_INDEX_FILE` (the index being committed) and `GIT_AUTHOR_NAME`,
`GIT_AUTHOR_EMAIL` and `GIT_AUTHOR_DATE` for the hook. `git hook run` sets
none of these (observed with git 2.54). Formatters and linters only read and
stage files, and without `GIT_INDEX_FILE` git uses the repository's index,
which is the one a plain `git commit` commits. A hook that reads the author
variables, or that behaves differently when `GIT_INDEX_FILE` is unset, might
behave differently in the early run. This has not been seen in practice.

**Only the commit script runs it.** `mint-trailer.sh` prints the staged tree
and nothing else; it does not run the hook, and neither does bug-hunter's
`mint-trailer.sh` or `caller-result.sh`. A mint that could rewrite the user's
files would be surprising, and the tree check catches a mismatch anyway. A
mint used on its own before a hand-run `git commit` is still exposed to the
formatter. A caller in bug-hunter's "caller commits" mode that commits through
`commit-with-trailers.sh` with its own families gets the early run. One that
passes the result block's `Bug-hunter-Tree` line to `git commit` itself does
not, and should call `run-pre-commit.sh` before the mint, as prose does.

**Rejected.**
- Running `$GIT_DIR/hooks/pre-commit` directly. It misses `core.hooksPath`,
  and whatever else `git hook` resolves for itself.
- Continuing after a failing hook when the index is unchanged. The commit
  would fail in `git commit` anyway, after the mints; refusing first says why.
- Re-minting after `git commit` and amending. That is a second commit for every
  commit, and the amend runs the hooks again.

---

## The pre-commit hook runs once per commit

**Decision.** When a value is bound and the repository has a `pre-commit` or
`commit-msg` hook, `commit-with-hooks.sh` runs both hooks itself and commits
with `git commit --no-verify`, so each runs once. `run-pre-commit.sh` does not
run the hook again in a state it already passed in, so a skill that runs it
before signing (`prose check`) and the commit that follows run it once between
them.

**Why.** Running the hook before binding (the entry above) and again in
`git commit` would run it twice per commit, and three times with prose running
it before signing. Repositories using husky typically run `tsc` and linters
there, which take seconds to minutes and only pass or fail, so every extra run
is pure cost. These skills are published as open source, where husky with
lint-staged is the common setup.

**Only when there is a hook.** `commit-with-trailers.sh` sources
`commit-with-hooks.sh` only when a value is bound and the repository has a
`pre-commit` or `commit-msg` hook: an executable file at
`git rev-parse --git-path hooks/<name>` (so `core.hooksPath` counts) or a
`hook.<name>.event` in config. Without one, the script makes a plain commit:
`git commit -m <subject> -m <body> --trailer ...` with the pinned trailer
settings, no message file, no record, no `--no-verify`. This keeps the main
path simple: a reader of `commit-with-trailers.sh` sees the plain commit, and
the hook handling is a separate module. A test checks the plain path's
`git commit` arguments.

**The message flow.**
1. The verifiers run on the message as passed, before any mint.
2. The script writes the message to `COMMIT_EDITMSG` the way
   `git commit -m … --trailer …` would: whitespace cleaned (`git stripspace`;
   left as passed when `commit.cleanup` is `verbatim`, as `-m` leaves it), then
   the trailers added by `git interpret-trailers --in-place --no-divider`, with
   the same pinned trailer settings. The file is `COMMIT_EDITMSG` because that
   is the file git passes to `commit-msg`, and some hooks read it by name.
3. `git hook run --ignore-missing commit-msg -- <that file>`. A non-zero exit
   refuses the commit with the hook's output.
4. If the hook changed the file, the verifiers run again on the changed
   message: the file minus the trailer lines the script added, each removed at
   its last occurrence anywhere in the file, then cleaned again. A prose
   signature over the old message is then refused, naming the commit-msg hook,
   rather than committed stale. A trailer the hook appends, such as
   `Signed-off-by` or Gerrit's `Change-Id`, is part of the changed message. If
   a line the script added is gone, the commit is refused: a binding the hook
   dropped would land unbound.
5. `git commit --no-verify -F <that file>`.

**What `--no-verify` skips.** Observed with git 2.54: `pre-commit` and
`commit-msg` only. `prepare-commit-msg` and `post-commit` still run, once
each; a test counts every hook. The script uses `--no-verify` only when it ran
both hooks itself: never for a commit whose values are all skip notes (nothing
ran early, so `git commit` runs every hook), and never on git before 2.36,
which cannot run `commit-msg` through `git hook run`.

**The pass record.** After the hook exits 0, `run-pre-commit.sh` writes
`$(git rev-parse --git-path commit-trailer/pre-commit-passed)`: the tree the
hook left staged, and the state it ran in. A later call skips the hook, prints
`unchanged`, exits 0 and says so on stderr when the staged tree and that state
both still match. The state is:
- **HEAD**, its branch and commit. A hook may check the branch (refuse commits
  to main), and after a commit lands the record no longer applies.
- **The hook file**, as `git rev-parse --git-path hooks/pre-commit` resolves it
  (so `core.hooksPath` counts): its path, executable bit and content hash. The
  path is made absolute so the record holds from any directory: a check run
  from the top spares a commit from a subdirectory. Editing the hook
  invalidates the record. It is a hash, not the mtime: a checkout or an editor
  that rewrites the same content does not need a rerun, and a same-second edit
  would keep the same mtime.
- **All git config, hashed.** A hook may read any key: git's own
  `pre-commit.sample` reads `hooks.allownonascii`, others read `user.email`.
  Keyed on `hook.*` alone, a pass made with `hooks.allownonascii=true` skipped
  the hook after it was set to false. It is a hash, not the values, because
  config can hold credentials and the record is a file in the git dir. Running
  the hook, `git commit` and the reads here write no config, so only a real
  config edit causes a rerun.
- **The unstaged changes**, as a hash of
  `git diff --no-relative --submodule=diff` (the whole work tree, from any
  directory). Hooks read the work tree (`tsc` checks files, not the index), and
  husky's real script, `.husky/pre-commit`, is a tracked file that the hook
  file `.husky/_/pre-commit` only sources. An edit to it, or to a config file a
  linter reads, changes this hash whether it is staged or not, unless git is
  told to ignore the file (see Limitations). `--submodule=diff` because plain
  `git diff` shows a dirty submodule as one `-dirty` line: a second edit inside
  it changed nothing, and a hook linting the submodule was skipped. An
  uninitialised submodule adds nothing.

A pre-commit hook defined in config (`hook.<name>.event`, git 2.54) is
recorded like a hook file. All config is in the state, so changing its
`hook.<name>.command` reruns it. The code that command runs (a script outside
the tree, `npx lint-staged`) is not in the state, so an edit there is a
limitation, below. Nothing is recorded when there is no hook. A failing run
deletes the record. Writing it is best effort: without it, the next call runs
the hook again.

**Where the record stops being safe.** Skipping the hook is correct only if
everything that can change its verdict is in the state. If something outside
the state changes so that the hook would now fail, the state still matches,
and the hook is skipped once when it should have failed; the next change to
anything in the state runs it again. That cost is accepted for things that
change rarely and that a person can cover by running the hook by hand: code a
hook runs from outside the repository, and ignored files a hook loads (see
Limitations). The cost is accepted for config-defined hooks too, rather than
leaving them unrecorded: such hooks are rare, and an edit to their script is
rarer.

**Rejected.**
- Running the hook twice and assuming it is idempotent. Correct, but it
  doubles the cost of a slow hook on every commit.
- `--no-verify` without running `commit-msg` here. A repository's
  `commit-msg` (commitlint, Gerrit's `Change-Id`) would silently stop running.
- Keying the record on the staged tree alone. An unstaged edit to
  `.husky/pre-commit` or to a linter's config, or a branch switch, would skip a
  hook whose verdict may have changed.
- Finding the added trailers in the message's last paragraph only. git puts
  trailers before trailing `#` lines (a body ending in `#42`), so they are not
  always in the last paragraph, and an edit by `commit-msg` was refused as a
  dropped trailer. Matching each added line wherever it is does not depend on
  where git places them.
- Hashing the file a config hook's command names. It is right only when the
  command is a single absolute path. `npx lint-staged`, `sh -c …`, arguments,
  `~` and paths relative to the hook's directory cannot be mapped to a file,
  and a wrong guess is the false skip the hash is meant to stop. So the code a
  config hook runs is not recorded at all.
- Running `commit-msg` from a `GIT_EDITOR` shim (`git commit --no-verify -e
  --no-status --cleanup=<mode>`, with `GIT_EDITOR` a script that runs
  `commit-msg` and re-verifies), to restore git's hook order. It costs more
  machinery for a setup not seen in practice; the order is a limitation below.

**Limitations.**
- **`commit-msg` runs before `prepare-commit-msg`.** `git commit` runs
  `prepare-commit-msg` first, then `commit-msg`. Under `--no-verify`,
  `prepare-commit-msg` still runs, but after the script's `commit-msg` run. A
  `commit-msg` that checks what a `prepare-commit-msg` adds (a ticket prefix
  from the branch name) refuses a message `git commit` would have accepted. An
  edit `prepare-commit-msg` makes is not seen by the verifiers.
- **`commit-msg`'s environment.** As with `pre-commit` (the entry above),
  `git hook run` does not set `GIT_INDEX_FILE`, the `GIT_AUTHOR_*` variables or
  `GIT_EDITOR=:`, which `git commit` sets for its hooks. A hook that reads them
  sees them unset.
- **Untracked and ignored-by-request files are not in the record.** A new
  untracked file that would break `tsc` does not invalidate a pass; it is not
  in the commit either. The same holds for a tracked file marked
  `skip-worktree` (sparse checkout) or `assume-unchanged`: `git diff` does not
  show its edits, because the user told git to ignore them. So does an ignored
  file the hook file sources, such as husky's `.husky/_/h`.
- **Code a hook runs from outside the repository is not in the record:** the
  script a config-defined hook's command names, or any program a hook calls.
  After editing one, run the hook by hand (`git hook run pre-commit`) or change
  what is staged.
- **Environment variables are not in the record.** A pass made with `HUSKY=0`,
  which makes husky's hooks exit 0 without running, is reused by a commit made
  without it.

---

## A skill may judge only commits that change some paths

**Decision.** A wrapper may set `COMMIT_TRAILER_PATHSPEC` to git pathspecs,
separated by spaces. The check then judges only a commit whose diff against
its parent (`git diff-tree --root`) changes a matching path. Every other
commit is skipped before its trailer is read, so it is never reported or
verified. When the variable is unset, every commit is judged. spec-check sets
`:(top)openspec`, with no trailing slash, so that a symlink named `openspec`
counts too; spec-check's DECISIONS.md says why.

**Why.** A skill whose trailer means something only for some files, such as
spec-check's for specs, would otherwise report every code-only commit, and a
report that is usually noise gets ignored.

**Rules this filter shares with the rest of the check:**
- A git failure counts as a match, so the commit is judged. A false report
  is visible; a skipped commit is not.
- Globbing is off while the pathspecs are split into words, so a `*` reaches
  git, not the shell.
- `:(top)` in a pathspec anchors it at the repository root. The hook may run
  from a subdirectory, and plain pathspecs are relative to it.

**Rejected.**
- **A callback the skill defines, like `commit_trailer_verify`.** Sourced
  skill code needs the subshell and status-marker guards that *A skill may
  verify its own trailer* describes. A pathspec is data and needs none.
- **Filtering in the skill's report.** By then the library has decided to
  report, and a skill cannot take that decision back from its report: when
  the skill's report is empty, the library prints its generic one instead.

---

## An empty commit, only when asked

**Decision.** The caller may pass `--allow-empty`: to the library, among its
options, or to bug-hunter's wrapper, as its very first argument. The library
then passes `--allow-empty` to `git commit`, whether git runs the commit hooks
or the library runs them itself (see *The pre-commit hook runs before anything
is bound*). Without it, git refuses a commit whose staged tree is its
parent's. An empty commit's families are bound like any other's: its tree is
its parent's tree, a minted `<Key>-Tree` line names that tree, and each
verifier checks its value against it.

**Why.** Some trailers record work that changes no file. spec-check's
consistency read is one. It runs once per review round, the agent's work
between two hand-backs to a person. When the read amends nothing and every
edit of the round is already pushed, its record has no commit to go on, and a
pushed commit is never rewritten (spec-check's DECISIONS.md, *One consistency
read per round*).

**Rejected.** Allowing empty commits always. An empty commit is almost always
a mistake, such as staging nothing by accident. git's refusal catches it, so
the refusal is given up only when the caller says so.

**Where this stops applying.** It permits an empty commit; it does not check
that the trailers are worth one. That is the caller's judgement.
