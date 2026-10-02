# commit-trailer — decisions

**Read this before changing anything here.** Not because it explains how the
scripts work; the code does that. Because most of what looks like an obvious
improvement has already been tried, and the reason it was reverted is not
visible from the line you would be editing.

Every entry is a decision, why it was made, and what was tried and rejected. The
rejected column is the load-bearing one: twice in this file's history a solved
problem was re-solved differently a few lines away, because the record of the
first solution lived at the first site only.

These scripts were bug-hunter's before they were shared, so the incidents below
are bug-hunter's: read `Bug-hunter:` as whichever trailer a skill configures,
and "the skill" as the skill whose wrapper sourced the check.

---

## One library, a thin wrapper per skill

**Decision.** The check, the mint and the commit assembly live here once. Each
skill that enforces a trailer keeps its own `scripts/check-commit-trailer.sh`
and `mint-trailer.sh`, which set the skill's name, trailer key and report file
and then source (check) or run (mint) the library; a skill with its own commit
script (bug-hunter's `commit-with-trailer.sh`) keeps its interface and hands
its family to `commit-with-trailers.sh` — see *One commit, several families*.

**Why.** Code that changes has to change in one place: two copies of 750 lines
of reflog edge cases drift, and every entry below is a reason they would.

**Rejected.**
- One script registered as the hook by several skills, checking a list of
  trailers. `manage-skills` identifies a hook entry's owner by the script path
  in it, so uninstalling or disabling one skill would remove the other's hook.
- The wrapper `exec`ing the library. `$0` would become the library, and the
  submodule walk re-invokes `$0` — losing the skill's configuration on the
  nested runs. The trace-based tests (`sh -x`) would also stop seeing the
  library's lines and pass vacuously.

**Consequences.**
- A skill folder copied without the rest of the clone has no library. The
  wrappers say so, out loud, on every run — a hook that fell silent would be
  broken and look like it is working, the one failure this family refuses.
- The state files, lock and environment variables are named from the skill
  (`<skill>-head`, `<skill>.lock`, `<SKILL>_DEPTH`), so bug-hunter's are
  unchanged and two skills' hooks never share a cursor.
- A skip note is any value starting `skipped`, for every skill.

---

## The skill's report is built in a subshell

**Decision.** The library sources the skill's report file inside `$( … )`, with
a trailing sentinel so trailing newlines survive, and falls back to its own
report when that fails or comes back empty.

**Why.** `.` is a special built-in: under dash a syntax error in the sourced
file aborts the whole hook, and the cursor has already moved past the commits
it was about to name, so they are never reported. In a subshell, anything the
file does — a syntax error, an `exit`, `set -e`, overwriting one of the
library's variables — takes down only the subshell.

**Rejected.** `! . "$report_file"` as the guard. bash returns non-zero and the
guard works; dash never returns. Found by bug-hunter; the regression test runs
only where dash is installed.

**Consequence.** A report function that prints to stdout has that text
captured into the report rather than corrupting Cursor's JSON.

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

**Decision.** The hook reads the reflog. It never inspects the shell command that
ran.

**Why.** Two earlier versions pattern-matched `git commit` in the command before
it ran. Between them they leaked on: a commit on the second line of a
multi-command call, `git -C ${REPO} commit`, `GIT_AUTHOR_NAME="Jane Doe" git
commit`, `timeout 120 git commit`, `env … git commit`, seven `-c` pairs instead
of six, and a `\`-continued invocation. Fifteen holes across two review passes,
two of them introduced by fixes to the others.

**Rejected.** Improving the regex. Matching text is a guess about what a shell
will do; the shell is the only thing that knows, and by the time it knows, git
already recorded what happened.

---

## The reflog action list excludes, it does not include

**Decision.** `REPLAY` names the actions that move HEAD onto content that already
existed. Anything not on it counts as authorship.

**Why.** The include-list version kept springing silent leaks: `commit
(cherry-pick)` for a conflicted pick, then `rebase (continue)` for a conflicted
rebase — both hand-typed content, both invisible. An include-list of everything
git might ever write cannot be proven complete, and every gap fails silent. With
an exclude-list, an unanticipated verb produces a visible false alarm instead.

**Rejected.** Adding to the include list each time a gap appeared. Three rounds of
that established it was an infinite list.

**Where this stops applying.** Only to sets that are open-ended — git's verbs,
the situations a command might meet. It does *not* apply where the bad set is
closed by definition. The characters that cannot survive a single-quoted path are
exactly `'`, `"`, `\` and control characters, because single-quoting defines
that; there a reject-list is provably complete and an accept-list is merely
guessing at what is safe. Inverting it there produced a filter that excluded
spaces and sent ordinary repositories to prose. The question is never "which
direction is the list" — it is "can this set be proven complete".

**Trap.** Do not guess action strings. `rebase (label):` and `rebase (onto):` were
guessed and git writes neither; the real ones are `rebase (merge):` and `rebase
(reset):`. Cursor bugbot later proposed `rebase (skip):` and `rebase (drop):`,
which also do not exist — a skipped or dropped commit produces no reflog entry at
all. Get action strings from `git reflog show HEAD --format='%gs'` on a real
repro, never from inference.

---

## `commit (merge)` is excluded; `rebase (continue)` is not

**Decision.** A merge is never reported, however its reflog entry is spelled —
the check is the commit's parent count, not the action string.

**Why.** A merge is not authored work, and a *conflicted* merge is finished with a
commit — so including the action would report merges only when they went badly.
`git reset --soft HEAD~1` on a merge drops the second parent, so the remedy would
be actively destructive. `rebase (continue)` is the opposite case: that is a
conflict resolution somebody typed, containing content in no earlier commit.

**Rejected.** Excluding by action string alone. Amending a merge to tidy its
message rewrites it as `commit (amend):`, which slips straight through.

---

## The cursor is a position in the reflog, not a sha

**Decision.** State is the reflog entry *count*, plus the HEAD it was written at.

**Why.** A sha is not a cursor: the same one appears in the reflog many times, so
`git commit && git checkout main && git merge --ff-only` buried the new commit
under an older matching entry and it was never reported again, on any later run.
The count also has to be paired with HEAD, because `git reflog expire` can drop
exactly as many entries as were added and land the count back where it started.

**Rejected.** Matching the stored sha. Also rejected: `head -50` as a window
bound, which silently dropped everything older while the printed count agreed
with the truncated list, so nothing signalled it.

---

## An amended commit is reported twice, on purpose

**Decision.** `git commit && git commit --amend` reports two commits, one of them
a sha the branch no longer holds. This is known and deliberately unfixed.

**Why.** It is cosmetic — the advice stays correct and the surviving commit really
is unchecked. Two attempts to tidy it each produced a *silent miss*, which is the
one outcome worse than an untidy report.

**Rejected, twice.**
- Filtering to commits reachable from HEAD. Swallowed `git commit && git checkout
  main` and `git commit && git rebase main` — the first being the exact case the
  cursor design exists for. Reachability answers "does this sha survive"; the
  question is "was content authored here".
- Skipping the reflog entry immediately older than an amend. Excluded entries sit
  between them routinely, so the flag landed on an unrelated commit and dropped
  it. `git commit && git rebase -i` reported nothing at all.

---

## Fails open and quiet, with exactly one exception

**Decision.** Anything the hook cannot read, it says nothing about. The single
exception is a git too old for `%(trailers:key=)`, which is announced.

**Why.** A hook that nags on every command gets uninstalled, and then nothing is
checked at all. The exception exists because that failure makes *every* commit
look checked forever — silence there is indistinguishable from working.

**Rejected.** Warning about a disabled reflog (`core.logAllRefUpdates=false`).
There is no activity signal to gate it on, so it would fire on every command
forever. It is a documented limit instead. The no-reflog *notice* that does exist
fires once per repository and only when `logs/HEAD` is genuinely absent — an
empty reflog is not a disabled one, and `git reflog expire` leaves a healthy repo
with an empty one.

---

## Guards on a run with no cursor are deliberately tight

**Decision.** `RECENT_SECONDS=120` and `NO_BASELINE_WINDOW=20` are one guard, not
two knobs.

**Why.** Together they bound what a first run in an unfamiliar repo will judge.
Loosening either turns that run into a report naming pre-existing commits and
advising a reset on them — a false alarm at the exact moment someone is deciding
whether to keep the hook.

**Rejected.** Widening `RECENT_SECONDS` to cover a commit made at the start of a
long command, and raising the window so nothing is truncated. Both are real
misses; both were judged cheaper than the noise the fix would create. A fix that
depends on this guard staying tight (routing a shrunk reflog through the
no-baseline path) is only safe while it does.

---

## The submodule walk, and its gate

**Decision.** Each initialised submodule gets the same check, re-invoking this
script with a shared message buffer. A stat gate skips the spawn when the
submodule's reflog is no older than its own cursor — unless it has a *live*
nested submodule of its own.

**Why.** A submodule is its own repository with its own HEAD; a commit inside one
moves a reflog the parent run never looks at. The gate exists because this hook
runs after *every* command, and eight submodules cost ~300ms on `ls`.

**Rejected.**
- Gating on the *parent's* reflog. A commit in a submodule does not move the
  parent's HEAD, which is the case the walk exists for.
- Gating a submodule purely on its own reflog. That is the same mistake one level
  down: the spawn is the only thing that walks *its* submodules, so a commit in
  `a/inner` was invisible once each level had settled.
- Exempting any submodule that merely has a `.gitmodules`. `git submodule update
  --init` without `--recursive` leaves one naming nothing initialised, and `git
  rm` of the last submodule leaves it tracked and empty — a spawn per command
  forever, finding nothing.

**Trap.** The comparison uses `find -newer`, not the shell's `-nt`: bash and dash
both compare whole seconds, so a commit a fraction of a second after the last
check reads as "not newer" and is skipped. That is a silent miss that happens
only sometimes.

---

## A submodule path shaped like a config key is skipped

**Decision.** In `.gitmodules`, a line matching `submodule.*.path` is treated as
a key. A submodule whose *path* is literally of that shape is therefore never
walked.

**Why.** `git config -z` gives `key\nvalue\0`, and a valueless key gives
`key\0` — so the parser tracks the previous line to stay in sync. A value shaped
like a key is genuinely ambiguous in that encoding.

**Rejected.** Disambiguating by testing whether the line resolves to a directory
containing `.git`. That walked into *any* directory named like another
submodule's config key — reporting a plain nested repository's commits and
writing cursor state into its `.git`. Trading a contrived silent skip for
spurious reports about repositories nobody declared is the wrong direction.

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

**Decision.** Everything the run has to say goes into one file; only the outermost
invocation empties it.

**Why.** Cursor parses stdout as a single JSON document, so a nested run printing
its own object made the entire payload unreadable — losing the report in the case
with the most to report, with exit 0 and no other signal.

**Rejected.** Making nested runs return only an exit code. For stderr hosts that
throws away the shas and subjects, which are the entire actionable content.

**Traps, all of which have bitten.**
- `: >"$f" 2>/dev/null` leaks the shell's own diagnostic: redirections apply left
  to right. Put `2>/dev/null` first.
- `:` is a POSIX **special built-in**, so a redirection failure on one aborts a
  non-interactive shell outright, `||` and all. Under dash — `/bin/sh` on Debian
  and Ubuntu — that killed the script before the guard written for that case
  could run. Wrap it in a subshell.
- Never substitute `/dev/null` as a fallback path. It reached `rm -f /dev/null`,
  which as root unlinks the device for every process on the machine.
- The delivery pipeline runs under `LC_ALL=C`, and so does the reflog `awk`:
  `logs/HEAD` stores message bytes raw, and BWK awk treats an invalid byte as
  fatal, truncating the list while the cursor has already advanced.

---

## The report states facts and stops

**Decision.** It names which commits lack a trailer and which repository they are
in, and says nothing about what to do. No git commands.

**Why.** The block that constructed commands produced 28 findings across eight
review iterations in two runs, while the half that reads the reflog and checks
the trailer produced almost none. Every one of those findings was in the
machinery for deciding *which* command applied: root commits, detached HEAD,
submodules, rewritten history, non-contiguous commits, unquotable paths.

The mistake was the frame. `check_repo` runs cd'd into each repository it
inspects; the agent reading the report stands somewhere else. Every command had
to be computed from context this script cannot see — the reader's cwd, their
branch, what HEAD is for them — while the reader has all of it and knows git.

**Rejected.** Emitting a command "only when the situation is provably ordinary".
That is a better rule than emit-unless-something-looks-wrong, and it still failed:
the gate certified a two-commit repository as ordinary and handed it
`reset --soft HEAD~2`, which is fatal.

**Where this stops applying.** This is not "never give an agent a command". It is
that a *hook* cannot, because it runs in a frame the reader does not occupy. A
skill running in the reader's own context has no such problem.

## It observes; it does not prevent

**Decision.** The hook runs *after* a command and reports. It does not block.

**Why.** Blocking requires knowing a commit is about to happen, which requires
reading the command — see the first entry. Everything that made detection exact
depends on asking git what already happened.

**Rejected.** A `PreToolUse` hook that blocks `git commit`, and a git
`pre-commit` hook. The first is the command-text problem; the second fights git's
index lock, since this skill writes files and commits, and a headless hook loses
the conversation context about what the change was meant to do.

**Consequence, accepted.** The commit exists by the time anyone knows. Undoing it
is left to the reader — see *The report states facts and stops* above, whose
whole cause is this: `git reset --soft HEAD~1` is only correct when the newest
reported commit is actually HEAD, which it often is not.

**Trap.** Removing the computed commands is not finished until the *prose* goes
too. The first attempt deleted every `git -C` and left the closing sentence
"re-commit with one — or amend a trailer in if the check does not apply", which
is the same conditional advice in a form that reads as harmless boilerplate.
Following it after `git commit && git checkout main` writes a `Bug-hunter:`
trailer onto an unrelated, already-checked commit and rewrites its sha, while
the reported commit keeps none and — the cursor having advanced — is never
reported again. Three docs went stale by the same edit — `SKILL.md`'s overview,
`README.md`'s trade-off paragraph, and, found only on the pass *after* this
entry was first written, `SKILL.md`'s triage table saying "reset it back to the
index **as the report describes**". That is worse than an ordinary stale doc:
`SKILL.md` is in the agent's context, so it supplies the command the report
deliberately withheld.

**Nothing tests any of this.** Four passages asserted what the report contains
and one edit falsified all four in silence. A test that generates a report and
checks every command the docs attribute to it was considered and not built —
this paragraph is the mitigation. Treat "the report says X" in any doc as a
claim you must re-read the report to keep true, and grep the four docs for it
whenever the report text changes.

**The line, since it is not "no imperatives".** Trailer placement stayed in the
report. It is context-free — where a trailer goes in a message is true wherever
the reader stands. A remedy is not.

---

## The trailer is minted from the tree, not recalled by the agent

**Decision.** Any `Bug-hunter:` trailer that is not itself a skip note
(`skipped at triage (...)`) must be paired with a `Bug-hunter-Tree:` trailer
whose value is the landed commit's tree hash — the same value
`scripts/mint-trailer.sh` prints when run against the staged index right
before `git commit`. That covers `N bugs fixed`, `0 bugs found`, and
`aborted ...` alike. The hook checks this only for a commit whose reflog
action is a plain `commit:` or `commit (amend):`; a mismatch or an absent
binding is reported, in its own paragraph, distinct from a missing trailer.

**Revised once, before this was ever committed.** The first version of this
scoped the requirement to trailers claiming `N bugs fixed`, on the theory that
claiming a fix was the high-stakes lie and `0 bugs found` a lower-stakes one
not worth the false-alarm risk of covering. Reviewed before shipping: the
theory was wrong about what the stakes are. The stakes are not the
fabrication's payload, they are whether the check can be sidestepped by
choosing different words — and it could be, trivially. The exact incident
this entry exists for is an agent that ran nothing and wrote a trailer; under
the fix-only scope, the trailer it needed to write to stay silent was
`Bug-hunter: 1 iteration, 0 bugs found` — five characters different from the
fabricated one, no mint, no script, hook quiet, and a *more* plausible
sentence for an agent that ran nothing to reach for, not less. That is not a
narrower version of the same protection; it is a one-word bypass of all of it.
Scoping to "not a skip" instead of "claims a fix" is what survived.

**Revised again, found by dogfooding this skill on this exact change, after
it had already landed on `main`.** Running Step 3 against the diff above —
late, because the delegated find-pass agent took long enough that the commit
happened first — surfaced five real, reproduced gaps in what had already
shipped:

- **A root commit was never checked.** `commit (initial):` is a root
  commit's own reflog action, confirmed against a real repro, and it was
  missing from the list this hook treats as "a plain commit, check the
  binding" — so a repository's very first commit could carry a fabricated
  trailer and stay silent forever. Fixed by adding it alongside `commit:`
  and `commit (amend):`.
- **A message-only amend of a cherry-pick or rebase replay was reported as
  fabricated.** Amending a message never touches the tree, but it does
  rewrite the reflog action to `commit (amend):` — the same laundering the
  merge-parent check already exists for, on the other side of the
  cherry-pick/merge line. By the time the amend happens the hook has
  typically already run once on the replay itself and moved the cursor past
  it, so the fix has to search the *whole* reflog for a replay action that
  landed this exact tree, not just the current window — a window-scoped
  version of this same check, tried first, still reported a real, honest
  repro as fabricated.
- **Two `Bug-hunter-Tree` trailers concatenated into a value that could never
  match anything.** `--trailer`'s default (`addIfDifferentNeighbor`) appends
  rather than replaces, so the exact repair this file's own README
  recommends — mint again, pass `--trailer` a second time — left two lines,
  and the extraction at the time joined every value with no separator into
  an 80-hex-character string. The documented repair could not repair itself.
  Fixed by reading the *last* logical value instead (see the next point for
  why "logical" has to mean something specific here).
- **A wrapped trailer's continuation line and a second, distinct
  `Bug-hunter:` trailer are indistinguishable in `%(trailers:...,valueonly)`
  output** — both come out as one value per line, with nothing marking where
  one trailer ends and the next begins. `,unfold` resolves this: it joins a
  wrapped value's own continuation lines back into one line, and leaves
  genuinely separate trailers on separate lines, so "the last line" is now
  the last *trailer*, not an arbitrary fragment of one. This is also what
  made the previous bug fixable correctly rather than just differently
  wrong.
- **A false `skipped ...` note, listed before a genuine fix-claim trailer on
  the same commit, exempted the fix-claim from ever needing a binding.** The
  skip test ran against the concatenation of every `Bug-hunter:` value on the
  commit, and matched if that concatenation merely *started with* "skipped"
  — so `skipped at triage (docs only)` followed by `1 iteration, 1 bug
  fixed` passed silently. Reading only the last logical `Bug-hunter:` value
  (same `,unfold` mechanism) closes this the same way it fixed the tree
  trailer: the last trailer on a commit is the one a human reading it would
  take as authoritative, and now it is also the one the hook takes.

One thing surfaced by the same pass was named, not fixed, because there is
nothing to fix: **the "producing a plausible wrong one is no easier than
producing the real one" claim below, under *Rejected*, is true only looking
forward from before the commit exists.** Looking backward from after it
exists, `git rev-parse HEAD^{tree}` prints the exact value `mint-trailer.sh`
would have, with no staging and no run of anything this skill ships — which
is exactly the command this file's own README recommends as the repair for
an honest binding gone stale. That command is correct advice for its stated
purpose and, read differently, a working bypass: it "repairs" a purely
fabricated trailer exactly as well as it repairs a real one. This is not a
new bypass introduced by anything above — it was always true of the
mechanism, just not written down. What this binding rules out is
*recollection*: producing the trailer's text from having read this file,
with no command run at all, which is the actual incident this mechanism
exists for. It does not rule out a deliberate, after-the-fact reconstruction
of the correct hash, because nothing computable from the hash alone can
prove *when* it was computed. See *the remaining bypass, named rather than
left for someone to find*, below, and the same reasoning: closing this
fully needs the deferred delegation-verification mechanism, not a sharper
version of this one. `reference.md` and `README.md` are written to state
this plainly rather than imply a stronger guarantee than the mechanism has.

A separate pair of hazards the same pass found are not bypasses at all, just
ways an honest run can drift: a repository whose pre-commit hooks reformat
or re-stage files changes the tree *after* the mint reads it; and `git
commit -- <pathspec>` or `git commit -a` can land a different tree than the
one just minted, if anything else was staged or unstaged-but-tracked at the
time. Both are now named in `reference.md` and `README.md`, with the repair
for the first and the avoidance for the second, rather than left to be
rediscovered as a false "fabrication" report. The first was then thought to
have no fix; the commit script has since closed it by running the hook before
minting (*The pre-commit hook runs before anything is bound*), and the repair
remains for a commit made by hand.

**Why.** A real incident, not a hypothetical: an agent fixed a genuine bug in
a different repo, wrote a real regression test, watched it fail on the
unfixed code for the predicted reason, applied the fix, watched it pass — an
honest, correct red-then-green proof, done entirely outside this skill — and
then ran `git commit --trailer "Bug-hunter: 1 iteration, 1 bug fixed"` because
the string matched the shape this file documents. It was caught only because a
human happened to ask "was this checked by bug-hunter?" The existing hook
could not have caught it on its own: it asks whether a `Bug-hunter:` trailer
exists, not whether anything behind it ran, and the fabricated trailer was a
real, well-formed git trailer. Nothing observable from outside the agent's own
head distinguishes "this ran" from "I recall what this looks like when it
runs" — except that producing the *right* tree hash for a commit that does not
exist yet requires actually running `git write-tree` against the actual staged
state at that moment. That is not something to recall; it is something to
compute, freshly, every time.

**What was considered and deferred: verifying delegation itself**, via a
`SubagentStop` or `PostToolUse`+`Task` hook that records real completions of
Step 3's find pass and Step 5's refute pass, keyed on a run token in the
subagent's own prompt. That is the only mechanism that would attest to
*delegation* rather than to *content*, and it was set aside for concrete
reasons, not philosophical ones:

- It cannot be tested from inside the session that builds it. Hooks load at
  session start (see `hook-development`'s own docs), so a newly wired
  `SubagentStop` entry never fires for the session that just wired it — there
  is no way to drive a real repro before shipping it.
- The transcript and tool-result shape it would need to key off is not
  something to guess at. This file's own history is explicit that reflog
  action strings must come from a real repro, never inference — three
  invented action strings (`rebase (label):`, `rebase (onto):`,
  `rebase (skip):`, `rebase (drop):`) never existed in real git. The same
  standard applies to a host payload this session has no way to produce a
  real repro of.
- `hook.json`'s manifest wires exactly one event per platform per skill today.
  Adding a second would mean extending `manage-skills`' installer — shared
  infrastructure every installed skill goes through, with its own test suite —
  to fix a gap in one skill, on a mechanism that cannot be verified working
  before it ships.

If it is ever built, it does not make this entry redundant: it attests that a
*delegation* happened, which this mechanism cannot and does not claim. The two
are different claims, not two implementations of the same one.

**Consequence, accepted.** `git write-tree` is not a read. It materialises a
tree object for the staged index into the repository's object store — every
other thing in this hook family only asks git questions, and this is the one
part of it that writes. The object is unreferenced by anything until a real
commit lands on that exact tree, so it is ordinary `git gc` litter, not a
correctness problem — but it is a real departure from the surrounding design,
worth knowing rather than discovering by reading `git count-objects` output
one day and wondering where it came from.

**Rejected.**
- A marker file, or a self-reported run-token, the agent writes to say "steps
  1/3/5 ran" — this is the same shape already rejected in *The hook is never
  told that a run is in progress*, and for the same reason: a flag the
  checked party writes at will is a flag that gets set out of habit, not
  honesty. The tree hash is different in kind, not just in packaging: it is
  not asserted, it is computed by `git write-tree`, and producing a plausible
  *wrong* one is no easier than producing the real one — both require running
  the same computation against some tree. That is true only before the
  commit exists; see *revised again* above for what it does not rule out
  once the commit has already landed.
- Inferring "a fix happened" from diff shape — for example, requiring a
  test-shaped file among the changed paths whenever the trailer claims a fix.
  Rejected before being built: this file is a long record of exactly this
  class of guess (reflog verbs, `.gitmodules`-key-shaped paths, command-text
  matching) each producing a silent gap or a false alarm the moment a real
  repository did not match the guessed shape. A cross-language, cross-
  framework guess at "is this a test file" is that same class of guess.
- Scoping the requirement to trailers that claim a fix, rather than to
  everything except a skip. This is the reverted first draft — see *Revised
  once* above — kept here only so the next person does not re-derive it as an
  improvement.
- Requiring the binding on cherry-picks and rebase replays too, rather than
  exempting them by reflog action. This is what would have created new false
  alarms instead: cherry-picking or rebasing a commit that already carries a
  valid trailer copies the message — trailer and its now-stale binding both
  — onto a different tree, and `test_a_cherry_pick_is_reported` already
  treats that shape as fine. Confirmed against a real repro rather than
  inferred, per the standard above: a clean cherry-pick's reflog action is
  `cherry-pick:`, a conflicted one is `commit (cherry-pick):`, a clean rebase
  replay is `rebase (pick):`, a conflicted one is `rebase (continue):` — none
  of those match `commit:` or `commit (amend):`, so scoping to those two left
  the entire existing cherry-pick/rebase/merge exemption logic untouched.

**Where this stops applying.** This attests only that `scripts/mint-trailer.sh`
ran against the tree that actually landed. It does not, and cannot from inside
this mechanism, attest that Step 1's triage, Step 3's find pass, or Step 5's
refute pass happened, or that the counts in the `Bug-hunter:` trailer are
honest — an agent that runs the mint script once and then writes whatever
counts it likes still passes. The gap this closes is specifically: a trailer
whose *shape* is the only thing that was ever produced. Closing the deeper gap
— did the delegation itself happen — is the deferred mechanism above, and this
one does not substitute for it.

**The remaining bypass, named rather than left for someone to find.**
`skipped*` is the one exemption left, which makes writing
`Bug-hunter: skipped at triage (docs only)` on a commit that is not docs-only
the cheapest evasion available now that "0 bugs found" no longer is. This is
accepted, not overlooked: a false skip note is visibly wrong to a human
reading `git log` next to the diff, in a way a plausible-looking "0 bugs
found" was not, and it is already covered by two things — the
announce-out-loud rule under *Every anti-evasion rule was added after it was
walked through*, and triage's rule that a skip comes from what the diff
touches, never from the commit message (bug-hunter's DECISIONS.md, *Triage
reads the diff, not a label*). A binding could be demanded for
skip notes too, but there is no tree to bind a skip to — triage, by design,
runs before anything is staged for review — so the only thing left to attest
to would be that triage itself ran, which is Step 1's delegation, and that is
the deferred mechanism above, not this one.

---

## The rebase apply backend is not reported

**Decision.** `rebase (pick):` never counts as authorship.

**Why.** The default merge backend writes `rebase (continue):` when you resolve a
conflict by hand, and that is reported. The apply backend — `rebase.backend=apply`,
`git rebase --apply`, and silently `--whitespace=<mode>` or `-C<n>` — writes
`rebase (pick):` for that same hand-typed resolution, which is indistinguishable
from a plain replay. Nothing per-commit survives to tell the two apart.

**Rejected.** Excluding `rebase (pick):` less aggressively. Every ordinary `git
rebase main` would then re-report each replayed commit — repeat, unactionable
noise on the most common rebase there is, to cover an opt-in backend.

---

---

## One commit, several families

**Decision.** `commit-with-trailers.sh` takes any number of trailer families and
makes one commit carrying all of them. A family is a key, a value and a binding,
of one of two kinds: *minted* here from the staged tree (`<Key>-Tree`, by
`mint-trailer.sh` or a skill's wrapper around it), or *verified* — a value the
skill signed earlier (`Prose: ✓ <12 hex tree>:<12 hex message>`), accepted only
if the skill's own verifier, named as `--verified-value`'s first argument, says
it still matches the staged tree and the message (see
[A family whose value is its own binding](#a-family-whose-value-is-its-own-binding)).
Everything bug-hunter's script already refused, it refuses for every family: an
empty subject, an empty or multi-line value, a failed or noisy mint, and it
pins the trailer config. Order is validate all, check every tool exists, run
the pre-commit hook (see *The pre-commit hook runs before anything is bound*),
run every verifier, run every mint, commit — so a stale binding in the last
family stops the commit before anything is minted.

**Why.** bug-hunter and prose each put a claim and its proof on the same
commit. Two scripts would each run `git commit`, and the second one has nothing
left to commit; an amend in between rewrites the tree-bound commit the first
binding was minted for. One assembly step is the only order in which both
bindings are true of the commit that lands. And the guards in bug-hunter's
*The commit is assembled by a script, not by hand* were each found by a run,
not by reading: a second script for prose would have to find them again.

**Why a verifier, not a second mint kind.** prose's binding hashes the staged
tree *and the message*, and is minted by `prose check` before the commit, when
prose has read the text; the library cannot recompute that without knowing
prose. So the extension point is an executable the family names: run with the
trailer line `<Key>: <value>` as its argument, from the caller's directory,
with the message on stdin — the subject, then a blank line and the body if
there is one, byte for byte as passed, no trailers. Exit 0 means it matches. A minted family never
takes a handed-in line: that would let a recalled `Bug-hunter-Tree` through the
extension point, which is the exact failure the mint exists for.

**Keys are kept apart.** git treats two trailer keys as one when the shorter,
ignoring case, is a prefix of the longer — dash or not. So `Bug-hunter`
"exists" whenever `Bug-hunter-Tree` does, a family keyed `Bug-hunter-Tree` would
collide with bug-hunter's binding, and `Pro` and `Prose` are the same key to
every `ifexists` rule and `trailer.<key>.*` setting git applies. A family's key
may not be a prefix of another's, which also keeps every `<Key>-Tree` binding
apart. The commit itself does not depend on this — see the pin below — but a
later amend with `--trailer` runs git's defaults again, and a key inside
another family's namespace reads as that family's binding.

`trailer.ifexists=add` is pinned, not git's default `addIfDifferentNeighbor`.
The default compares each new trailer with the one before it, by that prefix
match and by value ignoring case, and drops it as a duplicate. It was found
with the since-removed `--verified` family: a value that matched its own
binding line (`Demo: abc123`, `Demo-Sig: abc123`) lost the binding, exit 0.
Every trailer this script passes is wanted, so none is compared.
`addIfDifferent` would be worse: it compares with every trailer under that
key. The one cost is that a trailer passed twice lands twice — the same `--co-authored-by` twice, or a trailer
typed into the body and also passed.

**A missing argument is not a value.** Each option takes a fixed number of
words, so when one vanishes — an empty variable left unquoted — the next word
is taken in its place. Before `--` that is the separator itself, and
`--minted Bug-hunter $v -- ...` committed `Bug-hunter: --` with a real binding,
exit 0. When two vanish in a row it is the next option's name:
`--minted Bug-hunter $v --co-authored-by $c -- ...` committed
`Bug-hunter: --co-authored-by`, and so did the same line without `--`. So no
word an option takes may be `--`, `--minted`, `--minted-by`,
`--verified-value` or `--co-authored-by`. Other free text starting with `--`
stays a legal value (`--dry-run fixed`).

And `--` before the subject is required, not optional. Without it, a vanished
value next to an unquoted two-word subject balanced the count:
`--minted Bug-hunter $v $s "$b"`, with `$v` empty and `$s` `FEAT: x`,
committed `Bug-hunter: FEAT:` bound, subject `x`, exit 0. With `--` required,
every word between the options is an option, a word an option takes, or `--`;
a word that vanished pulls `--` or an option name into an option (refused
above), and a word that split lands where `--` or an option must be (refused).

**A tool is a path.** A minter or verifier named with no slash is refused as
an argument error: the existence check reads the file in the current
directory, but the shell runs a bare name from `PATH`, so a verifier beside the
caller passed the check and then failed as a stale binding.

`trailer.where=end` is pinned alongside `ifexists`, `ifmissing` and
`separators`: `where=start` did not lose a trailer, but it reversed the block,
so a family's binding sat above its key.

**Rejected.**
- Each skill calling the next skill's commit script. That nests one skill's
  interface in another's, and the order of nesting becomes a dependency.
- Families passed as `Key=value` strings or a config file. The value is
  free text; a separator inside it, or a file the agent writes, reopens the
  hand-assembly this script exists to close. Fixed-arity options parse with no
  escaping.
- Verifying by re-running the skill's mint and comparing. Only the skill knows
  whether its binding can be recomputed at commit time; a verifier can do that
  itself or check something cheaper.
- A family with no binding kind. Every family is minted or verified; the only
  unbound trailer is `Co-Authored-By`, which asserts nothing a skill checks.

**Consequences.**
- bug-hunter's `commit-with-trailer.sh` is a thin wrapper, like the check and
  mint: its arguments and exit codes are unchanged, except that a Bug-hunter
  or Co-Authored-By value that is exactly `--` or one of the option names above
  is now refused, exit 2 (see *A missing argument is not a value*); its
  messages now come from here. Like theirs, a copy of the skill without the
  clone around it has no library and says so, exit 1 — which means such a
  copy can no longer commit even a `skipped` value, which it could before.
- Two of bug-hunter's tests, `test_a_failed_mint_never_reaches_git_commit` and
  `test_a_noisy_mint_never_lands_a_multi_line_binding`, put a stub mint beside
  a copy of that script. They now copy the library beside it too, laid out as
  in the clone: copied alone, the script found no library, so the first failed
  and the second passed only because "library missing" is also exit 1. The one
  change to existing tests this needed, chosen by Adam over giving the wrapper
  a mint path of its own — which is the second copy the first entry rejects.
- A verifier is trusted code, run with the caller's environment: the family
  names it, so the caller chose it.

**Where this stops applying.** The message a verifier sees is the one passed in,
not the one git stores: git's cleanup trims trailing whitespace and collapses
blank lines, and `commit.cleanup` can do more. A skill that hashes the message
must mint and verify over the same raw form, or normalise both the same way.
Nothing here checks the stored message against the binding afterwards — that is
the skill's hook, if it has one. And a skill whose binding is neither a tree
hash nor checkable before the commit exists does not fit either kind; it needs
a third, not a stretched verifier.

**`--verified` removed, 2026-09-30.** The first verified kind, `--verified
<verifier> <Key> <value> <binding line>`, took the binding as a separate
`<Key>-<suffix>` line: prose's old `Prose-Sig`. prose, its only user, moved to
`--verified-value`, and nothing else called it. Decided by Adam.

To bring it back for a skill that needs a separate binding line: restore its
parsing and its binding-line checks (keyed `<Key>-<suffix>`, one line, a
non-empty value, absent for a skip note and required otherwise), pass that
line to the verifier and land it after the value, add `--verified` back to the
option names `takes` refuses, and restore its tests, including the value equal
to its own binding. `git log -S '--verified)' -- commit-with-trailers.sh`
lists the commit that added it and the one that removed it.

---

## The result block is printed by a script

**Decision.** A skill whose caller makes the commit ends with a result block,
and `result-block.sh` prints it. The skill passes its name, whole trailer lines
after `--`, and its open decisions, one per line, from a file or stdin
(`--decisions -`). The script checks every line, numbers and counts the
decisions, and prints the block only once every check has passed. It is the
format's one definition. Each skill calls it through a wrapper that supplies
the trailer lines: bug-hunter's `caller-result.sh` mints `Bug-hunter-Tree`
first, and prose's `prose check` prints its one line, `Prose: ✓ <12 hex
tree>:<12 hex message>`, the same way.

**Why.** The first version of bug-hunter's caller-commits mode had the agent
type the block, copying the mint's output into it. That is hand assembly, and
bug-hunter's *The commit is assembled by a script, not by hand* records how it
fails: hand-typed trailers went wrong under pressure, however the rule was
worded. A block a program parses fails the same way — a trailer retyped, a
count that does not match the lines, a tree line from an earlier mint.
Decided by Adam, 2026-09-27.

**What it refuses, and why each.**
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
  missing argument is not a value* above.

Unlike `commit-with-trailers.sh`, keys here may be prefixes of one another:
`Bug-hunter` and `Bug-hunter-Tree` are one family by design. This script
prints lines; it makes no commit for git's trailer rules to act on.

**Rejected.**
- **A documented format each skill prints itself.** Two skills printing one
  format is two copies, and they drift: a marker spelled differently, a count
  left off, a skip that still prints a tree line. And each copy is a place the
  agent assembles by hand.
- **Numbering left to the agent.** The count and the numbers would then be
  typed, and could disagree with the lines.
- **Decisions as arguments.** A decision holds free text — dashes, `·`,
  quotes — and there can be none or several; one per line in a file or a
  heredoc needs no quoting.

**Where this stops applying.** The script prints to stdout; the agent then
relays that into its reply, and a caller parsing the reply gets whatever the
relay kept. Each skill says to end with the output whole and unedited, and
nothing enforces it. The script checks the shape of a trailer line, not its
truth: a binding line is as good as the wrapper that minted it.

---

## Known gap: per-key trailer config outranks the pins

**The gap.** The commit pins `trailer.ifexists`, `ifmissing`, `separators` and
`where` for the one command, but those are git's general settings. A user's
per-key setting for a key this script writes — `trailer.bug-hunter-tree.ifexists=replace`,
`trailer.bug-hunter-tree.ifexists=doNothing`, `trailer.bug-hunter.ifmissing=doNothing`
— outranks them. Because git matches keys by prefix, `replace` on the binding's key overwrote the `Bug-hunter:` line with the
binding, and `doNothing` dropped the binding. The script exits 0 and the hook
then reports a correctly run commit as unchecked or as a fabricated trailer.
Observed with both the old single-family wrapper and this library.

**Why it is left.** It takes deliberate per-key config naming these exact keys,
and nobody has any; the old wrapper had the same exposure and nothing ever hit
it. Decided by Adam, 2026-09-26, when this library landed.

**The fix, if it is ever needed.** Pin the per-key setting too, for every key
the script writes — each family's key, its binding's key, and
`Co-Authored-By`: `-c trailer.<key>.ifexists=add -c trailer.<key>.ifmissing=add
-c trailer.<key>.where=end`. Check first that a `trailer.<key>.*` section git
did not have before does not change how it matches that key — a section with
no `.key` value uses its name as the key.

---

## Known gap: an empty body beside a split subject after `--`

**The gap.** After the `--`, `commit-with-trailers.sh` takes exactly two words,
subject and body. A caller that leaves both unquoted, with the body empty and
the subject two words — `-- $s $b` where `s="FEAT: x"`, `b=""` — hands it
`FEAT:` and `x`. The count balances, so the commit lands, exit 0, with subject
`FEAT:` and body `x`. The trailers and their bindings are still correct: only
the message is mangled.

**Why it is left.** Nothing distinguishes those two words from a real subject
and body; no parser can tell them apart. The defence is quoting: pass
`"$subject" "$body"`, as bug-hunter's wrapper does. Found by the bug-hunter run
over the `takes` fix, 2026-09-26.

**Where this stops applying.** Before the `--` the same slip is refused: a
vanished or split word there lands where `--` or an option must be (see *A
missing argument is not a value*). If the interface ever takes the subject and
body some other way — a file, stdin — this gap goes with it.

---

## A skill may verify its own trailer

**Decision.** A skill's report file may define `commit_trailer_verify <sha>
<value>`. When it does, the hook calls it, in place of the `<Key>-Tree` check,
for every plain commit or amend that carries the skill's trailer, skip notes
included. Returning 0 is valid; 1 is invalid, with the reason on stdout;
anything else is reported as "could not be verified". A callback that exits
instead of returning has not answered. Failures go in a new fact
variable, `rejected` (`sha subject -- reason` lines), which the skill's report
and the fallback report read. A skill that does not define the function gets
exactly the old check: bug-hunter's suite passes unmodified.

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
  (the check for the callback, the callback, the report). Under `set -u` an
  unset read aborted the callback before it returned: exit 1 under bash, so a
  commit the skill accepts read as rejected with no reason, and exit 2 under
  dash. And in the check for the callback, the same abort silently fell back to
  the tree check.
- A status other than 0 or 1 is said out loud. A callback that was found but
  could not run to a return — no `python3`, an `exit` — must never read as a
  pass.
- What the file prints as it loads is discarded where it is sourced only to
  check for or call the callback. The check's stdout is the hook's own, which
  Cursor reads as one JSON object, and the callback's is its reason, which must
  be only what the callback printed. The report's `$( … )` already captures it.
- The file's load must run to the end, and each subshell proves it did with a
  last line printed after the `.` and the call. An `exit` in the file, which
  *The skill's report is built in a subshell* already allows for, ends the
  subshell with its own status: `exit 0` read as "has a callback" and then as
  "valid", so a verifier that never ran passed, even for a skill that defines
  no callback. In the check for the callback, no last line means "no
  callback": the tree check runs, as it does for a syntax error and as it did
  before the callback existed. In the callback, no last line means "could not
  be verified (the callback did not return, exit N)", whatever N is: an
  `exit 1`, or `set -e` stopping the callback, is not the callback saying
  "invalid". The same holds for a callback that calls `exit` itself. Under the
  file's own `set -e`, a callback's `return 1` reads that way too: POSIX sh
  cannot tell an intended non-zero return from an aborted command, and calling
  the callback where errexit is off (`if`, `||`) would turn an abort into a
  pass. The commit is still reported; a report file that wants "invalid" to
  read as "invalid" does not use `set -e`.
- The callback's last line carries a marker new on every run. It follows the
  callback's own output, which can quote the trailer value, and with a fixed
  marker a value ending in `<marker>0` passed for a callback that echoed it and
  exited.

**Rejected.**
- A per-skill binding key, such as `COMMIT_TRAILER_BINDING=Prose-Sig` for
  prose's old separate signature line. It would still compare a value to the
  tree, which is not what prose signs.
- Running the callback in a fresh `sh` instead of a subshell. It would keep all
  of the hook's shell state out of skill code, not only `set -u`; but the
  report function needs the hook's fact variables, so the callback and the
  report would run under two different contracts. `set +u` covers the one
  option the hook sets. If the hook ever sets another, revisit this.
- `trap 'exit 3' EXIT` in the subshell instead of a last line. The file is
  sourced after the trap is set and can replace it.
- The status through a temporary file, keeping it off the callback's stdout
  altogether. A file to create, clean up and fail on, for what a marker the
  value cannot contain already gives.
- Letting the skill see replays and decide for itself. Every skill would have to
  re-derive the replay rules this file already paid for.

**Where this stops applying.** The callback decides validity; it does not change
which commits are judged, how the cursor moves, or what counts as a missing
trailer. A skill whose check needs more than the sha and the trailer value — the
reflog, other commits — needs a different hook, not a longer callback.

---

## A family whose value is its own binding

**Decision.** `commit-with-trailers.sh` takes `--verified-value <verifier>
<Key> <value>`: a family whose trailer value is itself the binding, with no
`<Key>-<suffix>` line. The verifier runs from the caller's directory, with the
message on stdin and the trailer line `<Key>: <value>` as its argument. Every
other guarantee holds: `takes`, the required `--`, the prefix-key refusal, validation before side effects, verifiers before mints,
the pinned trailer config. A skip note is not verified.

**Why.** prose signs the snapshot it worked on — the staged tree and the message
— and puts the signature in its own value, `Prose: ✓ <tree>:<message>`. One line
carries the claim and its proof, so a reader cannot keep one and lose the other.
The commit script must still refuse a stale signature before anything lands,
because whatever commits verifies against the snapshot the skill signed.

**Rejected.**
- Passing prose through `--verified` (since removed; see *One commit, several
  families*) with a dummy binding line. It lands a second trailer that means
  nothing and invites someone to "fix" it.
- A `--plain <Key> <value>` family with no check. It is a hand-assembled trailer
  with extra steps: nothing would refuse a signature minted over another tree.
- Having the library parse `✓ <tree>:<message>` itself. That is prose's format;
  the library would have to change whenever prose's does.

**Where this stops applying.** The verifier sees the message as passed, not as
git stores it (see *One commit, several families*). A skill whose value cannot
be checked before the commit exists does not fit this family either.

---

## Every installed skill's trailer, on one commit

**Decision (Adam, 2026-10-01).** Skills that sign commits with a trailer through
this library commit once, through `commit-with-trailers.sh`, with the trailer of
every such skill that is installed. Each skill's commit step forwards the
others' values as families, so an agent following any one skill's procedure
lands every trailer. A skill's SKILL.md points here for the rule rather than
restating it; it names only the skills whose values its own commit step
forwards, and how to tell each is installed.

Today that is two skills:
- **bug-hunter's** commit step asks the `manage-skills` skill (`list`)
  whether prose is installed. If it is, it runs prose's two
  `check` calls on the final staged change and message, and passes the
  `Prose:` value to `commit-with-trailer.sh` as `--verified-value`, which
  forwards it here.
- **prose**, while bug-hunter is running, leaves the commit to bug-hunter's
  commit step. When the agent commits itself, it calls this script with both
  families.

**Why.** Each skill's hook reports a commit missing its trailer. Before this,
following bug-hunter's procedure alone committed without `Prose:`, and prose's
hook reported it afterwards; combining the two meant piecing a command together
from two documents. A later commit or amend cannot add the missing trailer
without breaking the first one's binding (*One commit, several families*).

**Installed** is what the `manage-skills` skill's `list` reports, not a
judgement and not a path check a skill repeats: `manage-skills` owns where
skills are installed, so a skill that asks it stays right when it adds a
platform. (Adam, 2026-10-01.)

**Rejected.**
- The glue in the `commit` skill. Adam does not use it, and an agent reaches
  each skill's own commit step whether or not `commit` is installed.
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
the top of the work tree); see *The pre-commit hook runs once per commit*.
With no hook, nothing runs early. Decided by Adam, 2026-09-30.

**Why.** Every binding is a hash of the staged tree, made before `git commit`.
`git commit` then runs the pre-commit hook, and a formatter there (prettier,
black, lint-staged, the pre-commit framework) can rewrite and restage files.
The commit then lands a tree nobody bound, and an honest commit is reported as
unminted afterwards. bug-hunter's README called this unavoidable ("there is no
ordering that avoids this"); running the hook first is that ordering.

**How each hook is handled.**
- **No hook**: nothing runs early and nothing is printed; behaviour is as
  before.
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
refusal then says the pre-commit hook changed the staged files after the value
was made, so the agent knows to review the hook's changes and sign again
rather than retry blindly. A skill that signs before committing avoids this by
running `run-pre-commit.sh` itself first, then signing; the commit script then
finds the pass recorded and does not run the hook again (see *The pre-commit
hook runs once per commit*).

**`run-pre-commit.sh` is the shared piece.** Exit 0 prints one word, `changed`
or `unchanged`; exit 1 prints nothing on stdout and the reason on stderr. The
commit script uses the word to choose its refusal message. prose's `prose
check` calls it before listing and before signing, so the signature is made
over the formatted tree.

**`git commit` no longer runs the hook a second time.** Superseded by *The
pre-commit hook runs once per commit*: the script runs `commit-msg` itself and
commits with `--no-verify`.

**Only when something is bound.** When every family's value is a skip note,
nothing is minted or verified, so the early run is skipped and `git commit`
runs the hook once, as it always did.

**Older git.** `git hook run` arrived in git 2.36. On older git,
`run-pre-commit.sh` looks for a hook at `git rev-parse --git-path
hooks/pre-commit` (which honours `core.hooksPath`). If there is an executable
one, it refuses: the binding cannot be made after it, and committing anyway is
the failure this entry exists for. If there is none, nothing changes. Refusing
outright on older git was rejected: Ubuntu 22.04 ships 2.34, and a repository
without a hook has nothing to fix.

**The hook's environment differs from a real commit's.** During `git commit`,
git sets `GIT_INDEX_FILE` (the index being committed) and `GIT_AUTHOR_NAME`,
`GIT_AUTHOR_EMAIL` and `GIT_AUTHOR_DATE` for the hook. `git hook run` sets
none of these (observed with git 2.54). Formatters and linters only read and
stage files, and without `GIT_INDEX_FILE` git uses the repository's index,
which is the one a plain `git commit` commits. A hook that reads the author
variables, or that behaves differently when `GIT_INDEX_FILE` is unset, may
behave differently in the early run. Not seen in practice; `git commit` still
runs it with the full environment afterwards.

**Only the commit script runs it.** `mint-trailer.sh` prints the staged tree
and nothing else; it does not run the hook, and neither does bug-hunter's
`mint-trailer.sh` or `caller-result.sh`. A mint that could rewrite the user's
files would be surprising, and the tree check is what catches a mismatch
anyway. Used standalone before a hand-run `git commit`, a mint still has the
old gap. A caller in bug-hunter's "caller commits" mode that commits through
`commit-with-trailers.sh` with its own families gets the early run; one that
passes the result block's `Bug-hunter-Tree` line to `git commit` itself does
not, and should call `run-pre-commit.sh` before the mint, as prose does.

**Rejected.**
- `git commit --no-verify` after the early run, at the time. It skips
  `commit-msg` as well. Since adopted, with the script running `commit-msg`
  itself: *The pre-commit hook runs once per commit*.
- Running `$GIT_DIR/hooks/pre-commit` directly. Misses `core.hooksPath`, and
  whatever else `git hook` resolves for itself.
- Continuing after a failing hook when the index is unchanged. The commit
  would fail in `git commit` anyway, after the mints; refusing first says why.
- Re-minting after `git commit` and amending. A second commit for every commit,
  and the amend runs the hooks again.

## The pre-commit hook runs once per commit

**Decision.** When a value is bound and the repository has a `pre-commit` or
`commit-msg` hook, `commit-with-hooks.sh` runs both hooks itself and commits
with `git commit --no-verify`, so each runs once. `run-pre-commit.sh` does not
run the hook again in a state it already passed in, so a skill that runs it
before signing (`prose check`) and the commit that follows run it once between
them. Decided by Adam, 2026-09-30.

**Only when there is a hook.** `commit-with-trailers.sh` sources
`commit-with-hooks.sh` only when a value is bound and the repository has a
`pre-commit` or `commit-msg` hook: an executable file at
`git rev-parse --git-path hooks/<name>` (so `core.hooksPath` counts) or a
`hook.<name>.event` in config. Without one, the script commits exactly as it
did before this entry: `git commit -m <subject> -m <body> --trailer ...` with
the pinned trailer settings, no message file, no record, no `--no-verify`.
Why: keep the main path simple, so a reader of `commit-with-trailers.sh` sees
the plain commit, and the hook handling is a separate module. Decided by Adam,
2026-10-01. A test checks the plain path's `git commit` arguments.

**Why.** Running the hook before binding (the entry above) made it run twice
per commit: once in the script, once in `git commit`. With prose running it
before signing, three times. Repositories using husky typically run `tsc` and
linters there, which take seconds to minutes and only pass or fail, so every
extra run is pure cost. These skills are being open-sourced, where husky with
lint-staged is the common setup.

**The message flow.**
1. The verifiers run on the message as passed, before any mint, as before.
2. The script writes the message to `COMMIT_EDITMSG` the way `git commit -m
   … --trailer …` would: whitespace cleaned (`git stripspace`; left as
   passed when `commit.cleanup` is `verbatim`, as `-m` leaves it), then the
   trailers added by `git interpret-trailers --in-place --no-divider`, with
   the same pinned trailer settings. `COMMIT_EDITMSG` because it is the file
   git passes to `commit-msg`, and some hooks read it by name.
3. `git hook run --ignore-missing commit-msg -- <that file>`. A non-zero exit
   refuses the commit with the hook's output.
4. If the hook changed the file, the verifiers run again on the changed
   message: the file minus the trailer lines the script added, each removed
   at its last occurrence anywhere in the file, then cleaned again. So a prose signature over the old message is refused,
   naming the commit-msg hook, rather than committed stale. A trailer the hook
   appends, such as `Signed-off-by` or Gerrit's `Change-Id`, is part of the
   changed message. If a line the script added is gone, the commit is refused:
   a binding the hook dropped would land unbound.
5. `git commit --no-verify -F <that file>`.

**What `--no-verify` skips.** Observed with git 2.54: it skips `pre-commit`
and `commit-msg` only. `prepare-commit-msg` and `post-commit` still run, once
each; a test counts every hook. The script uses `--no-verify` only when it ran
both hooks itself: never for a skip-notes-only commit (nothing ran early, so
`git commit` runs every hook as before) and never on git before 2.36, which
cannot run `commit-msg` through `git hook run`.

**The pass record.** After the hook exits 0, `run-pre-commit.sh` writes
`$(git rev-parse --git-path commit-trailer/pre-commit-passed)`: the tree the
hook left staged, and the state it ran in. A later call skips the hook, prints
`unchanged`, exits 0 and says so on stderr when the staged tree and that state
both still match. The state is:
- **HEAD**, its branch and commit. A hook may check the branch (refuse
  commits to main), and after a commit lands the record no longer applies.
- **The hook file**, as `git rev-parse --git-path hooks/pre-commit` resolves
  it (so `core.hooksPath` counts), made absolute so the record holds from any
  directory (a check run from the top spares a commit from a subdirectory): its path, executable bit and content hash.
  Editing the hook invalidates the record. A hash, not the mtime: a checkout
  or an editor that rewrites the same content does not need a rerun, and a
  same-second edit would keep the same mtime.
- **All git config, hashed.** A hook may read any key: git's own
  `pre-commit.sample` reads `hooks.allownonascii`, others read `user.email`.
  Keying on
  `hook.*` alone let a pass made with `hooks.allownonascii=true` skip the hook
  after it was set to false. A hash, not the values, because config can hold
  credentials and the record is a file in the git dir. Running the hook,
  `git commit` and the reads here write no config, so only a real config edit
  causes a rerun.
- **The unstaged changes**, as a hash of `git diff --no-relative
  --submodule=diff` (the whole work tree, from any directory). Hooks read the
  work tree (`tsc` checks files, not the index), and husky's real script,
  `.husky/pre-commit`, is a tracked file that the hook file `.husky/_/pre-commit`
  only sources. An edit to it, or to a config file a linter reads, changes this
  hash whether it is staged or not, unless git is told to ignore the file (see
  Limitations). `--submodule=diff` because plain `git diff` shows a dirty
  submodule as one `-dirty` line, so a second edit inside it changed nothing
  and a hook linting the submodule was skipped. An uninitialised submodule
  adds nothing.

A pre-commit hook defined in config (`hook.<name>.event`, git 2.54) is
recorded like a hook file. All config is in the state, so changing its
`hook.<name>.command` reruns it; the code that command runs (a script outside
the tree, `npx lint-staged`) is not, so an edit there is a limitation, below.
Nothing is recorded when there is no hook. A failing run deletes the record.
Writing it is best effort: without it, the next call runs the hook again.

**Where the record stops being safe.** Skipping the hook is correct only if
everything that can change its verdict is in the state. When something outside
the state changes in a way that would make the hook fail, the state still
matches, and the hook is skipped when it should have failed. That happens once:
the next change to anything in the state runs the hook again. The cost is
accepted for things that change rarely and that a person can cover by running
the hook by hand: code a hook runs from outside the repository, and ignored
files a hook loads. See Limitations. Decided by Adam, 2026-10-01, reversing the
first version, which never recorded a hook defined in config: such hooks are
rare, and an edit to their script is rarer.

**Rejected.**
- Running the hook twice and assuming it is idempotent (the previous entry's
  position). Correct, but it doubles the cost of a slow hook on every commit.
- `--no-verify` without running `commit-msg` ourselves. A repository's
  `commit-msg` (commitlint, Gerrit's `Change-Id`) would silently stop running.
- Keying the record on the staged tree alone. An unstaged edit to
  `.husky/pre-commit` or to a linter's config, or a branch switch, would skip a
  hook whose verdict may have changed.
- Finding the added trailers in the message's last paragraph only. git puts
  trailers before trailing `#` lines (a body ending in `#42`), so they are not
  always in the last paragraph, and an edit by `commit-msg` was refused as a
  dropped trailer. Matching each added line wherever it is does not depend on
  where git places them.
- Hashing the file a config hook's command names (2026-10-01). It is right
  only when the command is a single absolute path. `npx lint-staged`, `sh -c
  …`, arguments, `~` and paths relative to the hook's directory cannot be
  mapped to a file. Guessing wrong is the false skip it is meant to stop, so
  config hooks are not recorded at all.

**Limitations.**
- **`commit-msg` now runs before `prepare-commit-msg`.** `git commit` runs
  `prepare-commit-msg` first, then `commit-msg`; under `--no-verify`
  `prepare-commit-msg` still runs, but after the script's `commit-msg` run. A
  `commit-msg` that checks what a `prepare-commit-msg` adds (a ticket prefix
  from the branch name) refuses a message `git commit` would have accepted. And
  an edit `prepare-commit-msg` makes is not seen by the verifiers, as before.
  Rejected fix: run `commit-msg` from a `GIT_EDITOR` shim (`git commit
  --no-verify -e --no-status --cleanup=<mode>`, with `GIT_EDITOR` a script that
  runs `commit-msg` and re-verifies). It restores git's exact order, at the
  cost of more machinery for a setup not seen in practice. (Adam, 2026-10-01:
  keep as a limitation.)
- **`commit-msg`'s environment.** As with `pre-commit` (the entry above),
  `git hook run` does not set `GIT_INDEX_FILE`, the `GIT_AUTHOR_*` variables or
  `GIT_EDITOR=:`, which `git commit` sets for its hooks. A hook that reads them
  sees them unset.
- **Untracked and ignored-by-request files are not in the record.** A new
  untracked file that would break `tsc` does not invalidate a pass; it is not
  in the commit either. The same holds for a tracked file marked
  `skip-worktree` (sparse checkout) or `assume-unchanged`: `git diff` does not
  show its edits, because the user told git to ignore them. So does an
  ignored file the hook file sources, such as husky's `.husky/_/h`.
- **Code a hook runs from outside the repository is not in the record:** the
  script a config-defined hook's command names, or any program a hook calls.
  After editing one, run the hook by hand (`git hook run pre-commit`) or
  change what is staged.
- **Environment variables are not in the record.** A pass made with
  `HUSKY=0`, which makes husky's hooks exit 0 without running, is reused by a
  commit made without it.
