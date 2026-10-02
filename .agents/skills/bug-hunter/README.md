# bug-hunter

Catches bugs in code that was just written, **before** it gets committed —
instead of waiting for a PR bot to find them after you push. Most of the commits
it sees will be written by an agent, and that's the case it's built for.

The difference from every other automated bug hunter: **it has to prove the bug
before it reports it.** Every finding gets a regression test that is run against
the unfixed code and observed to fail for the predicted reason. Anything that
can't be driven red is dropped and its test deleted. So when it prints a bug,
there is a failing test behind it, and when it prints "clean", that means
something.

## What it does

1. **Triages** the staged change with a cheap model, from the diff alone —
   docs-only, formatting, renames and reverts are skipped, and so is a
   checkpoint you ask for, so it doesn't hound you on every checkpoint commit.
2. **Finds** candidate bugs with a strong model. Each one has to name a real
   caller and a concrete input that reaches it. Style opinions are banned.
3. **Proves** each candidate with a regression test that fails now and will
   keep failing if the bug ever comes back.
4. **Refutes** — a second, independent agent tries to kill each finding
   (unreachable, guarded upstream, intentional). Only survivors get fixed.
5. **Fixes** with a strong model that first has to ask *"is there a better
   approach that would have prevented this class of bug entirely?"* and prefers
   the simpler one.
6. **Verifies** the new tests pass and your existing suite is no worse.
7. **Iterates** up to three times, then commits — or, if it is still finding
   things at three, stops and hands you a report on why this piece of work keeps
   producing bugs. Three is the whole budget and it never asks you for a fourth
   iteration. Anything still unresolved comes back as a numbered root cause with
   three options on it: a fresh run scoped to that one cause, write it down as a
   known gap, or skip it.

Things it finds but can't test (concurrency, config, security posture) and
things that are bigger than the change in front of it get **reported, not
fixed**. It won't quietly refactor your codebase.

## Setup

Nothing to configure. Installing the skill also turns on a hook that **notices
any commit that lands without having been checked**, on both Claude Code and
Cursor:

```
bug-hunter ships a hook, enabled by default:
  Reports any commit that lands without having been through bug-hunter.
  bug-hunter [claude hook]: enabled on PostToolUse
  bug-hunter [cursor hook]: enabled on postToolUse
  turn it off with:  skills.py disable-hook bug-hunter
```

Restart Cursor to pick it up.

The hook exists because an instruction in a `CLAUDE.md` is advisory — an agent
can skip it, and does exactly when you're in a hurry.

### How it notices

After each command it asks git a few questions: did `HEAD` move, does the new
commit carry a `Bug-hunter:` trailer, and — unless that trailer is a skip note
— does a second trailer, `Bug-hunter-Tree`, match what actually landed? It
never reads the command that was run.

So **the trailer is the whole mechanism.** No environment variable, nothing to
remember, and whether a commit was checked is recorded in the commit itself:

```bash
git log --invert-grep --grep='Bug-hunter:' --oneline   # commits that skipped it
```

**Why the second trailer.** A `Bug-hunter:` line is just text — an agent that
has seen this file once can type `1 iteration, 1 bug fixed` from memory, with
no run behind it, and the hook has no way to tell that apart from a real one
just by reading it. `Bug-hunter-Tree` is different: it's a hash the skill's
own `scripts/mint-trailer.sh` computes from whatever is actually staged, right
before the commit, and the hook recomputes the same hash from the commit that
landed and compares. Producing the right value for a commit that doesn't
exist yet means actually running that computation — there's no "recall it
from having read the docs" version of a tree hash. The skill's own commit
script, `scripts/commit-with-trailer.sh`, mints it as part of creating the
commit, so you don't need to do anything for it — but if you ever write a
`Bug-hunter:` trailer by hand, pair it with `Bug-hunter-Tree`, or leave the
`Bug-hunter:` line out and just explain why in prose instead.

**The trade-off:** it observes rather than intercepts, so the commit exists by the
time you hear about it. The report names the commits and the repository and stops
there — it doesn't tell you how to undo anything, because the commit it names is
frequently not your current HEAD (you committed, then switched branches) and a
canned `reset` or `--amend` would land on the wrong one. Your agent has the sha
and knows git. Nothing gets past it, but nothing is prevented either. If you want
a commit *stopped*, that belongs in CI, where the trailer can be required to
merge.

### Turning it off

Ask your agent to "turn off the bug-hunter hook", or:

```bash
python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook bug-hunter
```

**The choice sticks** — reinstalling skills later won't switch it back on. To
install the skill without the hook in the first place, use
`install --no-hook bug-hunter`.

The skill itself still works with the hook off — call it by name whenever you
want it.

### Two more things

**It fails open, and it's quiet.** A missing or broken hook script lets commits
through rather than locking you out of your repo, and a repo it can't read is one
it says nothing about. `skills.py doctor` is what catches a silently broken hook.
The first command it sees in a repo only records where `HEAD` is — it never
judges history it didn't watch land — and a checkout, reset, rebase or pull moves
`HEAD` without being new work, so none of those are reported either.

**It is not a git `pre-commit` hook.** This skill writes files, adds test files,
and creates a commit — all of it fights git's index lock from inside a
`pre-commit` hook, and a headless hook loses the conversation context about what
the change was *meant* to do, which is where most false positives come from.

## What gets skipped

Triage decides from the diff alone. It doesn't read your commit message, and
it doesn't ask for any commit convention — write subjects however your
repository does.

| The diff shows | Reviewed? |
|---|---|
| Formatting only | no |
| A pure rename or move | no |
| Only docs, tests or specs | no |
| git's own revert or merge | no |
| Anything else | **yes** |

Work in progress is the one thing a diff can't show, so it comes from you: ask
for a checkpoint ("save a checkpoint", "commit this as WIP") and that commit is
skipped. A checkpoint defers the check; it doesn't exempt the code, which still
gets reviewed when it lands in a commit that isn't a checkpoint.

## Using it

Say any of:

> "bug check this before I commit"
> "run bug-hunter"
> "find bugs in what we just wrote, but don't commit"

### Settings

| What | How |
|---|---|
| Fix and commit | Default |
| Fix but leave it uncommitted for review | Ask for it — "just report", "don't commit" |
| Hand the commit to a program that commits itself | Say "caller commits" in the brief — it leaves the change staged and ends with `scripts/caller-result.sh`'s block: the trailer lines and open decisions |
| Record that a commit deliberately skipped it | Commit through `scripts/commit-with-trailer.sh`, passing `skipped at triage (<why>)` as the trailer value |
| Force a review triage would have skipped | Ask for the skill by name |

## Reading the report

It prints one every run, including when it skips, so you can always tell it
fired and what it did:

```
🔍 bug-hunter · 1 iteration · 1 fixed · 1 refuted · 1 unproven

  triage    REVIEW — new logic in the payments reducer
  scope     3 files  +84/-12
  baseline  pytest 412 ✓

── iteration 1 ───────────────────  3 found · 2 proven · 1 survived · 1 fixed

  ✓ FIXED     refunding a partially-captured charge double-counts the fee
              where   reducer.py:88
              test    tests/test_reducer.py::test_partial_capture_refund_fee
              fix     take the fee from the capture record instead of
                      recomputing it, so the two can never disagree
  ✗ REFUTED   null customer dereference
              why     guarded by the schema before it reaches here
  ○ UNPROVEN  pagination overrun
              why     the test did not fail — already handled

── iteration 2 ──────────────────────────────────────  0 proven bugs · clean

── result ───────────────────────────────────────────────────────────────────

  suite     pytest 414 ✓ (was 412)
  commit    9f2ab41  Correct the fee on partial-capture refunds
```

- **⚪ unproven** and **🚫 refuted** are the skill doing its job. A run that
  reports three candidates and fixes none is a *good* run.
- **⚠️ Reported, not fixed** is the section to actually read. That's where the
  concerns it deliberately declined to solve go.
- **`N to decide`** in the headline is how many root causes are waiting on you.
  They sit at the top of the report, numbered, with three options each. If an
  agent relayed the report to you, it should be asking you those — one at a
  time, through its picker — not summarising them.

## Troubleshooting

**"Stop — these files have both staged and unstaged changes."** You partially
staged a file. The skill reasons about the staged version but tests the file on
disk, and they disagree, so it refuses to guess. Stage the rest or revert it. It
will never `git stash` your work to get around this.

**It skipped my commit.** The diff touched only docs, tests, specs or
formatting, was a pure rename or move, or you asked for a checkpoint. Ask for
the skill by name to force a review.

**It reviewed a commit whose subject said `WIP`.** Triage doesn't read the
subject. To skip a work-in-progress commit, ask for a checkpoint in the
conversation.

**It aborted after three iterations.** It kept finding new bugs each pass, so it
stopped and left everything uncommitted. The report explains what about this
task keeps producing bugs, and recommends a larger change only when that change
has a high chance of working. It will not ask you for a fourth iteration —
instead you get one entry per unresolved root cause and pick per entry: a fresh
run scoped to that cause, write it down, or skip. One of those entries is often
the run's own last fixes, which the budget ended before anything could review.

**My agent said the run aborted, or found root causes, and didn't ask me
anything.** Those decisions are yours, and the report says so to whoever is
holding it. When you run this through a coordinating agent that spawns
sub-agents, the report lands in the coordinator's context first, and it is meant
to put each root cause in front of you in its next reply — one question at a
time, through its picker. Ask it for the root-causes block — the numbered
entries with three options each — and pick per entry.

**It's slow.** It delegates several passes to strong models and runs your suite
repeatedly. It is meant for commits with real logic in them — triage exists so
it isn't paying that cost on checkpoint commits.

**It told me a commit wasn't checked and I don't want to redo it.** Record why,
rather than leaving it blank: while the commit is still local and still your
HEAD, `git commit --amend --no-edit --trailer "Bug-hunter: skipped at triage
(<reason>)"`. A commit with nothing to review — docs, formatting, a rename, a
revert — is exempt from the hunt, not from the trailer, so this *is* the whole
response for one of those; there is no run to redo. The check reports each
commit once, so ignoring it is possible, but then nothing records that the
decision was ever made and the commit stays on the un-checked list that
`git log --invert-grep --grep='Bug-hunter:'` prints.

**It told me a commit has a `Bug-hunter:` trailer but no matching
`Bug-hunter-Tree`.** That's a different problem from a missing trailer: the
trailer is real, but nothing produced the binding that shows a run actually
touched this exact tree — usually because it was typed by hand instead of
going through this skill's own committing step. If the run genuinely happened
and the reported commit is still your HEAD, `git commit --amend --trailer
"Bug-hunter-Tree: $(git rev-parse HEAD^{tree})"` repairs it in place, and it's
safe to run again if it doesn't take the first time — a second `--trailer`
appends rather than replaces, and the hook reads the last one. If it didn't
happen, treat this the same as an unchecked commit.

Read plainly, that repair command computes the exact same hash
`scripts/mint-trailer.sh` would have — which means it also "repairs" a
trailer that was pure fabrication, with nothing behind it at all. That's a
real, accepted limit on what this binding proves, not an oversight: see
*The trailer is minted from the tree, not recalled by the agent* in
`DECISIONS.md`. Reach for this repair when a run genuinely happened and the
mint step was just missed or mistimed — not as a way to make a report go
away.

**It told me an honest commit is unminted, and I staged everything before
minting.** Two shapes of this are a workflow bug, not a fabricated trailer:

- A pre-commit hook that reformats or re-stages files changes the index
  *after* the mint ran, when the commit was made by hand with a mint taken
  beforehand. `scripts/commit-with-trailer.sh` avoids this: it runs the
  pre-commit hook first and mints after it (see the shared library's
  DECISIONS.md, *The pre-commit hook runs before anything is bound*). For a
  commit made by hand, re-run `mint-trailer.sh` once the commit exists and
  its hooks have already fired, then apply the repair above.
- `git commit -- <pathspec>` or `git commit -a` can land a different tree
  than the one you minted, if anything else was staged, or unstaged-but-
  tracked, at the time. Stage exactly what this commit should contain, mint,
  then commit with no pathspec and no `-a` — the binding is for the whole
  index, not a subset of it.

---

## Tests

The hook's decision logic is covered by regression tests. Run them after touching
the script, from the root of your shared-skills clone:

```bash
python3 .agents/skills/bug-hunter/scripts/test_hook.py
python3 .agents/skills/bug-hunter/scripts/test_caller_result.py
```
