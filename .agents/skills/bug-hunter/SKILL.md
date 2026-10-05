---
name: bug-hunter
description: >-
  Catch bugs in code that was just written, before it is committed. Run this
  before every `git commit` that contains code you or the user just wrote —
  "commit this", "commit my changes", "let's commit", "wrap this up and commit"
  all mean run this first. Also use when the user says "bug check this",
  "prevent bugs", or "find bugs before I commit". If another skill makes
  your commits and runs this one before each of them, let it.
  Finds candidate bugs in the staged change, proves each one with a
  regression test that actually fails, refutes the weak ones, fixes what
  survives, and re-verifies. Docs, specs, tests and work-in-progress commits
  skip the hunt, not this skill — they still commit through its script,
  carrying a `Bug-hunter: skipped` trailer. When a caller's brief says
  "caller commits", run in full but do not commit: leave the change staged and
  return the trailer lines and any open decisions for the caller to use. Do
  not use for reviewing someone else's PR or reviewer comments — use a code
  review for that.
---

# Bug Hunter

**A claim with no failing test is a guess.** Everything this skill reports is
proven by a test observed red before the fix and green after; everything it
cannot prove is dropped. That is the whole idea, and the reason its output is
worth reading.

It edits the working tree, adds test files, and by default commits.

- **How to do each step** — [reference.md](reference.md). Read it before Steps
  4–7, before writing a report, and before committing.
- **Why any of this is the way it is** — [DECISIONS.md](DECISIONS.md). Read it
  before changing this file or `scripts/`. It is about this skill; the record
  Step 6 reads before a fix is the codebase's own.

## The contract

1. Every fixed bug has a regression test that was **observed red** on the
   unfixed code and green after the fix.
2. Every candidate that cannot be driven red, or that a second opinion
   refutes, is **dropped** — and its test is deleted, never left failing.
3. Anything real but out of scope or untestable is **reported, not fixed**.
4. The full test suite ends no worse than it started.

## Workflow checklist

```
- [ ] Step 0: Scope the change — staged diff only
- [ ] Step 1: Triage — is this commit worth reviewing at all?
- [ ] Step 2: Baseline — run the suite before touching anything
- [ ] Step 3: Find candidates (strong model, reachability required)
- [ ] Step 4: Prove — write the test, run it, demand a matching red
- [ ] Step 5: Refute — a second opinion tries to kill each proven bug
- [ ] Step 6: Fix (resume this iteration's finder, prevention question, scope-confined)
- [ ] Step 7: Verify — new tests green; the full suite once, before Step 9
- [ ] Step 8: Iterate — back to back, up to 3, without asking; never a 4th
- [ ] Step 9: Report once at the end; ask the user each open decision (picker — written is not asked); then commit (with prose's trailer when prose is installed) or leave it for review — or, under "caller commits", end with `scripts/caller-result.sh`'s block
```

Never run this from inside a git `pre-commit` hook. It writes files, adds
tests, and commits — all of which fight git's index lock. It runs **before**
the commit is created, and the commit happens at Step 9.

A companion hook watches for commits that never came through here: after each
command it asks git whether HEAD moved and whether the new commit carries a
`Bug-hunter:` trailer. So **the trailer is the only marker that matters** — no
environment variable, nothing to remember, and the record lives in the commit
itself where `git log` can audit it.

The hook also asks a second question of any trailer that is not itself a skip
note — `0 bugs found` and `aborted ...` included, not only ones reporting a
fix: does a `Bug-hunter-Tree` trailer match the tree that actually landed? That
binding is what [`scripts/mint-trailer.sh`](scripts/mint-trailer.sh) produces
when run against the real staged tree, right before the commit — see [Step
9](#step-9--report-and-commit) for how, and
[the shared library's DECISIONS.md](../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent)
for why. A `Bug-hunter:` trailer can be a real git trailer with exactly the
right wording and still be a sentence recalled from having read this file,
rather than one produced by running any part of it — that is the one shape
the string-presence check cannot catch, and the one this binding is for.

A commit that lands without a `Bug-hunter:` trailer at all gets named
in a report, with the repository it is in, and nothing else: the hook cannot see
where you are standing, and the commit it names is often not your HEAD.

---

## If you are an agent about to commit

If another skill makes your commits and runs this skill before each of them,
let that skill start from "commit this"; still run for "bug check this". If
this turn already stated a commit subject, use that subject unchanged. Only add
trailers.

**Run this skill before every commit you create that contains code.** Not when
asked for it by name — every time. "Commit this", "commit my changes", "wrap up
and commit", or your own decision to commit after finishing a task all mean:
stage the change, run this skill, then commit. Triage (Step 1) is what decides
whether a given commit is worth reviewing, so running it always is cheap when it
does not apply.

### Do not evade this skill

One heading, not five rules, because an agent looking for a way out of a check
reliably finds the seam between separately-stated rules. Every line here was
added after it was walked through — the record is in
[DECISIONS.md](DECISIONS.md#every-anti-evasion-rule-was-added-after-it-was-walked-through).

**1. Say which one you are doing, out loud, every time.** One line in the reply
the user can see: **"running bug-hunter on N files"**, or **"skipping bug-hunter
— <reason>"**. Not in your reasoning — in the reply. Skipping while saying
nothing looks exactly like running it and finding nothing. A stated skip can be
overruled in four words; an unstated one is a decision you made for them. If you
skip, the commit carries the trailer too — `commit-with-trailer.sh -F msg.txt
"skipped — <reason>"`, as in [Step 9](#step-9--report-and-commit). Both, not either.
Under *caller commits*, the skip goes to the result script instead
([When the caller commits](#when-the-caller-commits)).

**2. Never ask permission to run it.** The trigger is a property of the code, not
a moment: **if code has been written since the last pass that came back clean, a
pass is owed.** Before a commit, between iterations, after a fix the user asked
for, after a refactor, after a commit that already landed — not separate cases,
all "code was written". **A list of moments invites hunting for the moment that
is not on it.**

**3. Announcing only counts if you have already started.** *"That's running next
unless you want to stop here"* · *"I'll kick that off if you're happy with it"* ·
*"the fixes need their own pass — want me to run it?"* Each ends the turn with
the check not running, which hands back the decision as plainly as asking would.
**If you are describing a run in the future tense, you have not started it, and
that is the bug.**

**4. Iterations run back to back, and the report is owed.** Up to three, no
check-in between them, and no interim report — a report between iterations
invites stopping early and makes an unfinished run look finished. See Steps 8
and 9.

**Three is the budget, not an opening offer. There is no fourth iteration.**
*"want me to run one more pass?"* · *"iteration 3's own fixes never got
reviewed — shall I do a 4th?"* Both hand back a decision the budget already
made, at the moment the user is most likely to say no. A run that caps out ends
in the root-causes report (Step 9) and one choice per cause, where the first
choice is a **new run at iteration 1** scoped to that cause. That is not rule 2
suspended: a pass over iteration 3's fixes really is owed, and it is still owed
— what ran out is the budget for taking it *inside this run*, which is why it
becomes a new run and why which cause gets it is the user's call. Nor is it rule
3 reversed: inside the budget a pass is owed and you start it without asking;
at the cap the run is over, and what is left is a decision, offered as options
rather than as an open question.

**5. These are not reasons.** Every one has been used, by a capable model, to
skip this skill on a commit that then shipped a bug:

- *the change is small* — one-line changes are wrong all the time
- *I am confident in this code* — so was every author of every bug this has found
- *the user is waiting / we are moving fast* — that is the moment quality gets
  traded away, which is the moment this exists for
- *the session is long and this is expensive* — a run that finds nothing is
  cheap, triage stops most commits before the expensive part, and the long
  passes run in the background anyway (Step 3)
- *I already ran it on related code earlier* — you did not run it on this
- *this is the skill's own machinery, not real code* — it is real code, and the
  worst bugs in this skill's own history have been in exactly that machinery
- *the user is clearly watching and would object if they minded* — they are
  watching the output, not the absence of it

Creating bugs and moving on because checking was inconvenient is the specific
behaviour this skill exists to stop. Doing it *to* this skill is not irony, it is
just the bug.

**Whose call the cost is.** A full run is minutes; a bad one is half an hour.
Whoever installed this already weighed a slower commit against a bug reaching
main. An agent that quietly decides the check is too slow today has not made an
engineering judgement — it has overridden that decision on behalf of someone not
in the room, in the direction that happens to be less work. If the cost genuinely
matters right now, say so in one sentence and let them choose.

### Whose decision it is

Two short lists, because both failures live at the boundary between them:
asking about the first trains the user to skim, and deciding the second for
them is choice 3 taken silently.

**Yours, never asked.** Whether to run and when; whether a candidate is proven,
refuted or dropped; how to fix a proven bug inside the change; whether to
iterate, up to the cap; running the suite; committing a run that ended clean
with nothing open — except under *caller commits*, where the commit is the
caller's.

**The user's, always asked.** What to act on: each root cause and each
recommendation (fix now / write it down / skip), each unresolved entry of an
abort, whether a commit goes ahead when something reported-not-fixed changes
what it means (report-only mode), and the Step 0 stop — which of a file's
diverging staged and unstaged edits to keep.

**When you do ask, use the host's interactive picker**: any question with
discrete options goes through it, one question per decision, in severity order,
never buried in prose at the end of a long report. Plain text is the fallback
for hosts without a picker, not the default. The picker is also the one thing
here that is structural rather than advisory — a turn with a picker open cannot
end until the user answers — which is why the next rule matters.

**Asked means the user saw it.** A question is asked when it is in a reply the
user reads or a picker they answer — not when an agent wrote it down. If this
skill runs in an agent that reports to another agent, its Step 9 report and its
questions reach *that agent*, and nothing has been asked yet: the hop moves the
picker, it does not discharge the question. So:

- **If you spawned an agent to run this**, its report is your Step 9 input, not
  your Step 9 output. Every entry on the user's list goes in front of the
  user in your **next reply, before anything else** — through your picker, one
  question per decision, or the report's numbered block verbatim where there is
  none. *"The run aborted"* or *"it found three root causes"* with no options
  under it is relaying *about* the report instead of delivering it; if you are
  writing that sentence, that is the bug. Holding the decision across a turn
  while other work finishes is choice 3, made for them — the other work waits,
  or the reply carries both.
- **If you are the agent running this for another agent**, you have no picker
  that reaches the user. Print the whole report in its format — not a summary
  of it — with the hand-off footer
  ([reference.md](reference.md#the-hand-off-footer)) that tells whoever holds
  it what is still theirs to ask. Say plainly which decisions are open and
  that you could not ask them. Under *caller commits*, the result block's
  decisions list replaces the footer ([When the caller commits](#when-the-caller-commits)).

**A run has not ended until its questions are in front of the user**, whichever
agent gets them there.

## Step 0 — Scope

The change under review is the **staged** diff:

```bash
git diff --cached --stat
git diff --cached
```

Read the whole file for each changed file, not just the hunks — a bug is
usually in the interaction between new code and the code around it.

**If any file appears in both the staged and the unstaged diff, stop.** You
would be reasoning about the index while testing the working tree, and they
disagree. Tell the user which files diverge and ask them to stage or revert
those edits. **Never `git stash`** to work around this — the user has
uncommitted work and this skill is about to write files on top of it.

Unstaged changes in *other* files are fine. Note them in the report.

Do not hunt for bugs in specs, documentation, or existing tests. Changes to
those files are still context worth reading.

## Step 1 — Triage

**Triage decides from the diff, not from the commit message.** For a diff of
up to about 300 changed lines, **triage it yourself**, in the loop you are
already in: a sub-agent costs more to start than reading a diff that size.
Delegate a larger diff to a single fast pass on a **small, cheap model**. Either
way, the pass gets the file list, the diff, and whether the user asked for a
checkpoint (below). Ask for one of `REVIEW` or
`SKIP` plus a one-line reason. Do not ask for a commit message first, and do
not read a subject prefix as a signal — this skill imposes no commit
convention ([reference.md](reference.md#what-triage-skips)).

`SKIP` when the diff shows:

- Nothing outside docs, specs, tests, lockfiles, generated or vendored files
  changed.
- The change is purely formatting, renames, moves, or comments — no behavior
  is different.
- It is git's own revert or merge.

**Work in progress is the one skip a diff can't show.** `SKIP` it only when
the user asked, in this conversation, for a checkpoint or a work-in-progress
save — or said the same thing in other words (`tmp`, `save point`, `squash
me`). A checkpoint defers the check, never exempts the code: its behavior
changes are reviewed when they land in a commit that is not a checkpoint.

`REVIEW` for everything else. **When unsure, review.** A small diff is not a
reason to skip; plenty of one-line changes are wrong. "Looks simple" is never
a valid skip reason.

If the user explicitly asked for this skill, run it regardless of triage.

On `SKIP`, print the report (Step 9) with the skip reason and stop hunting.
**`SKIP` is a value for the trailer, not an exemption from it** — the commit
still goes through `commit-with-trailer.sh` with
`skipped at triage (<reason>)` as its third argument ([Step
9](#step-9--report-and-commit)). Skipping the hunt is the cheap half; skipping
the commit script is what puts an unchecked commit in front of the hook.
Under *caller commits*, the same value goes to the result script instead
([When the caller commits](#when-the-caller-commits)).

### A hook report is an input to triage, not an instruction to run

The companion hook reports commits that landed without a trailer. Look at what
actually landed — this is what keeps a false alarm cheap, and
[DECISIONS.md](DECISIONS.md#triage-applies-to-the-hooks-own-reports) is why:

| what the reported commit is | response |
|---|---|
| docs, formatting, a rename, a revert — any skip category | `git commit --amend --no-edit --trailer "Bug-hunter: skipped at triage (<reason>)"` |
| not new work at all — the hook misfired on a branch switch, a replay, a commit that predates the hook | the same amend, with `Bug-hunter: not new work (<what it actually was>)`, and say the hook misfired |
| real code | get the change back in front of you and run the full loop, then record the trailer |

The report gives you the sha and the repository and stops, deliberately, because
it cannot see where you are standing. **Check where that sha sits relative to
your HEAD before acting on it.** The amends above assume it *is* your HEAD, which
is often false: `git commit` then `git checkout main` is the case this hook
exists for, and there they land on the wrong commit.

## Step 2 — Baseline

Run the project's test suite, typecheck, or build — whatever it already has —
and record the result. If something is already failing, note it as the
baseline. You are not responsible for pre-existing failures, but you must not
add to them, and you must not mistake one for a bug you found. This is running a
command and writing down what it printed: **run it yourself**. Never start a
sub-agent to run a command; starting one costs more than reading its output.
Keep only the summary lines of a long output.

## Step 3 — Find candidates

Delegate to a subagent using the **strongest available model**. Its job is to
find plausible scenarios the code does not appear to handle.

Every candidate must come with:

- **The scenario** — what situation the code does not handle.
- **Reachability** — a real caller, entry point, input, or state that gets
  there. Trace it. A candidate whose trigger cannot be named is not a
  candidate.
- **Concrete input** — the specific value, sequence, or condition.
- **The wrong outcome** — what actually happens, and what should have.

**Observe it before reporting it.** Run the thing — call the function, execute
the script, `curl` the endpoint, whatever is cheapest — with the concrete input,
and record what came back. Reading code is how you find a candidate; running it
is how you know. Report the command and the result next to each candidate. This
is the single highest-leverage habit in this skill: a finder that runs its own
candidates reports almost no false positives, and one that only reasons reports
plenty. If a candidate genuinely cannot be observed without building something,
say so and let Step 4 decide.

**Not candidates.** Style, naming, formatting, preferences, "consider
extracting this", missing comments, defensive checks for conditions that
cannot occur, or hypotheticals with no caller. Report none of these. The value
of this skill is that everything it prints is real.

### Run this pass in the background and keep working

This is the long step. **Launch it in the background and get on with something
else** — the find pass and the refute pass only read, so nothing stops you doing
other work while they run. Waiting at an idle prompt is where most of the "this
is too expensive" feeling comes from, and it is recoverable.

Safe meanwhile: unrelated files, documentation, answering the user, planning.
Not safe:

- **Do not touch the files under review.** Findings against a version that no
  longer exists are worthless. If the other work needs an edit there, the run is
  invalid — wait, or restart it against the new state.
- **Do not commit.** The commit waits for the whole run, always. Backgrounding is
  for spending the wait well, not for shipping while the check is in flight.
- **Do not guess at the result.** You know nothing until the pass reports back.
  Never write up findings you have not received, and if the user asks in the
  meantime, say it is still running.

Steps 4, 6 and 7 write files, so they run in the foreground. It is the reading
passes that parallelise.

**When the pass reports back, the run is the next thing.** Its return is Step 4
starting — or, after the last iteration, Step 9 — not a notification to file
while the other work finishes. Finish the edit you are in the middle of, then
pick the run back up. If what came back ends the run, the report and every
question in it go out in that same turn's reply
([Whose decision it is](#whose-decision-it-is)). A result that arrives during
other work and sits in your context is how a run quietly never ends.

## Steps 4–7 — Prove, Refute, Fix, Verify

**Read [reference.md](reference.md#steps-47-in-detail) before doing any of
these.** It carries the procedure; below is only the part you cannot get wrong.

**Step 4 — Prove.** Write the regression test, run it against the *unfixed* code,
and require it to fail **for the predicted reason** — not an import error, not a
missing fixture. A candidate that cannot be driven red is dropped and its test
deleted. Never leave a failing or discarded test in the tree. This is the whole
contract: without an observed red, a finding is a guess. **Do not delegate this**
— Step 3 hands over the concrete input and the expected wrong outcome, so writing
one test in the project's existing framework is translation, not investigation;
write and run it in the loop you are already in, and a **small, cheap model** is
sufficient. The red is the check, and it is empirical.

**Step 5 — Refute.** A *separate* agent that has not seen the finder's reasoning
tries to kill each proven bug — unreachable, guarded upstream, intentional, or
asserting something the code never promised. Only survivors get fixed; refuted
findings are dropped and their tests deleted. Use a **capable model** — this is
judgment, not mechanics, so do not tier it down the way Steps 2, 4 and 7 are; it
does not need the strongest available either, which Steps 3 and 6 do.

**Refuters run concurrently.** Each one judges its own finding and must not see
the others' reasoning, so there is nothing to serialize — **launch them all at
once** rather than one per bug in turn. The one question that waits is the
cross-finding one below, which needs the surviving set.

**A refuter judges findings, never proposals.** It is told to default to
skepticism, which is right for "is this bug real" and wrong for anything else:
pointed at a proposed design change, its disposition defends whatever exists
today ([DECISIONS.md](DECISIONS.md#a-refuter-judges-findings-not-proposals) —
it cost eight iterations). So: findings to the refuter, **design decisions to the
user** via Step 9's picker. The one question about fixes that belongs here is
factual rather than evaluative — *do any of these fixes fight each other?* Give
it the codebase's record of rejected approaches too — the same files Step 6
reads — so it can say whether a finding re-treads ground already recorded as
rejected.

**Tell the refuter which spec text predates the change.** A refuter cannot see
when a document was written, so it reads spec, design and task text as
pre-existing intent — and documentation authored in the same session as the code
is not that. It is the implementer describing what they just wrote, and it has
killed a reproduced finding as "a deliberate, documented design choice". So the
brief names the committed spec separately from the in-flight text, and the refuter
checks provenance — `git log -S "<phrase>" -- <file>`, `git diff`, `git blame` —
before treating any passage as a decision. **A sentence that exists in no commit
refutes nothing**; the procedure is in
[reference.md](reference.md#step-5--refute), the incident in
[DECISIONS.md](DECISIONS.md#documentation-written-in-the-same-session-is-not-evidence-of-intent).

**Step 6 — Fix.** **Resume this iteration's Step 3 finder via `SendMessage`** —
it already read the files, traced reachability, and ran the candidates, and
nothing has changed them since — passing it the surviving findings, the refuter
verdicts, and Step 5's fix-conflict notes. Spawn a fresh agent on the
**strongest available model** only if that finder is no longer reachable; the
mechanics are in [reference.md](reference.md#step-6--fix).

**Read the codebase's record of rejected approaches first, if it keeps one** —
a `DECISIONS.md`, an ADR directory, the `design.md` of the OpenSpec change that
covers this code; the same places Step 9
[writes to](#write-down-what-was-rejected-before-you-commit). Check two things:
whether this approach is already recorded as rejected, and — for any lesson you
are about to apply — whether its recorded *scope* covers your case. A lesson
applied outside its scope is a fresh bug wearing the authority of an old fix.

Then answer: *is there a better approach that would have prevented bugs like this
from ever happening?* Prefer simpler code, simpler architecture, fewer moving
parts. Confine the fix to the change under review; if the real cause sits outside
it, that is a root cause for Step 9, not something to fix in passing.

**Step 7 — Verify.** Every new test passes. **The full suite runs once per run,
not once per iteration** — at Step 2 for the baseline, and again immediately
before the Step 9 report, which nothing ships without. In between, run the new
regression tests plus whatever existing tests cover the files the fix touched;
that is what catches a fix breaking its neighbours while it is still cheap to
attribute. **Never modify, weaken, delete or skip an existing test to reach
green.** If a pre-existing test now fails, the fix broke it — fix the fix, or
revert it and report it unresolved. Running tests and comparing counts to the
baseline is running commands: **do it yourself**, as in Step 2.

## Step 8 — Iterate

**A run and an iteration are different things, and the counter resets.**

- An **iteration** is one Step 3 → Step 7 pass over the current state of the
  change, including the fixes just written.
- A **run** is up to three iterations. It ends when an iteration comes back
  clean, or at the abort — three iterations that each found something, followed
  by the root-causes report and one decision per cause (Step 9), **never a
  fourth iteration**. **The full suite belongs to the run, not to the
  iteration**: whichever ending applies, run it before the report and hold the
  report until it is no worse than the Step 2 baseline.
- **Whatever the user then asks for starts a new run at iteration 1.** Applying a
  root cause, taking a recommendation, building something they picked: that is
  new code, and new code gets its own three-iteration budget.

So a long session is a sequence of short runs, not one endless run. Count and
report within the run — `Bug-hunter: 2 iterations, 3 bugs fixed` means this run,
not this week.

**An iteration that fixed something is never the last one.** Stop only after a
pass that **finds nothing**. A fix is new code written minutes ago by someone who
was just thinking about a different problem, so stopping straight after writing
one stops where the change is least reviewed — "I fixed four bugs" and "this code
is clean" are different claims, and only the second is what anyone wanted. The
measurements behind that are in
[DECISIONS.md](DECISIONS.md#an-iteration-that-fixed-something-is-never-the-last-one).

**If an iteration still yields bugs**, before writing more fixes, ask why the
previous pass missed them. Is the finding approach looking in the wrong place? Is
the code's design the reason bugs keep appearing here? Rethink the approach, then
continue. If the answer is a design change larger than the change under review,
take it to Step 9 as a root cause and let the user decide.

### The abort is an ending, not a request for more budget

When the third iteration finishes and something is still unresolved, **the run is
over**. Do not run a fourth iteration and do not offer one. Everything still open
becomes a numbered root cause in the Step 9 report, each with its three choices
attached — and choice 1 is a **new run at iteration 1**, scoped to that one
cause. That is not a fourth iteration renamed: the counter resets for new work,
so a fresh finder reading the fixed code gets a fresh three-iteration budget.

**The commonest unresolved cause is the run's own remainder.** Iteration 3 fixed
something, so by this step's own rule it cannot be the last iteration — and it
is, because the budget is spent. Iteration 3's fixes are code written minutes ago
that no finder pass has ever read. Report it as a root cause in those words:
*iteration 3's fixes never got a finder pass — the budget ended before one
could run*, naming what those fixes touched.

**That is a different kind of cause from Step 6's, and the report says which.**
Step 6's root cause is about **place** — the real cause sits outside the change
under review, so fixing it there would exceed the scope. The remainder is about
**budget** — the cause sits squarely inside the change under review, and the pass
that would have found it does not exist. Do not conflate them; the user is
weighing a different thing in each case. Both get the same three choices, because
the shape of the decision is the same either way. The shape of the entry is in
[reference.md](reference.md#when-the-run-aborts); the incident behind this rule,
and why a fourth iteration is not the fix, are in
[DECISIONS.md](DECISIONS.md#there-is-no-fourth-iteration-the-abort-reports-root-causes).

## Step 9 — Report and commit

**Every run ends with the report. Always, unasked, in the reply the user can
see.** A run ends when an iteration comes back clean or when the third one
aborts — those are the only two endings, and both print it. Never ask whether the
user wants one, and never defer one to "next time": that is the same evasion as
asking permission to run the check. If a run happened, its report is owed.

**Prose is not the report.** Print the format — headline counts, root causes,
per-iteration findings, result — and put any commentary around it, not instead of
it. One report per run, covering every pass. No interim reports (Step 8).

**Anything still open goes in this report, with its question attached.** A
decision the user has not been given cannot be made, and a run that ends with an
unasked question has not ended.

**A run that aborted reports one root cause per unresolved thing, and asks about
each.** Step 6's out-of-scope causes and the run's own unreviewed remainder are
both entries, each labelled as the kind it is (Step 8), each carrying the three
choices below through the picker. Describing the gap accurately and stopping
there is not the report — an accurate description of something nobody was asked
to decide is choice 3 taken on the user's behalf.

**The full report format, with a worked example and the rules for each section,
is in [reference.md](reference.md#the-report). Read it before writing one.** The
commit itself — what to stage, the trailer, splitting — is in
[reference.md](reference.md#committing).

**Commit through the script. Never assemble `git commit -m … --trailer …` by
hand — not for a fix, not for a skip, not for a one-line docs change.** Scope:
first letter capital when inventing; reuse `git log` tokens as-is. Stage
everything first, then, standing in the project:

```bash
BH=~/.agents/skills/bug-hunter/scripts/commit-with-trailer.sh
[ -x "$BH" ] || BH=~/.claude/skills/bug-hunter/scripts/commit-with-trailer.sh
"$BH" -F msg.txt "1 iteration, 1 bug fixed" "Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

`msg.txt` holds the message: the subject, a blank line, then the body (never a
trailer in it). Write it to a file so the message never has to be quoted on the
command line; prose's pass uses the same file. Then come the `Bug-hunter:`
value and, optionally, the `Co-Authored-By` value. The message as two words,
`"<subject>" "<body>"` in place of `-F msg.txt`, still works. Each trailer is
passed as `--trailer`, so where it lands is git's problem; and for any value that
is not `skipped …` the script runs `mint-trailer.sh` against the tree staged at
that instant and adds the `Bug-hunter-Tree` binding — the one line a hand-typed
commit cannot produce, and the one the hook checks. It runs the repository's
pre-commit hook before minting, so a formatter there cannot change the tree
after it is bound; if the hook fails, nothing is committed — review what it
changed, stage what belongs, and run the script again. The path *to the script* is
absolute because `scripts/` is relative to this directory, not to your project;
the git it runs is not. Verify with `git log -1 --format='%(trailers:key=Bug-hunter)'`;
while the commit is still local, `git commit --amend --no-edit --trailer "…"` is
the repair. The mechanics the script wraps, and what the binding does and does
not attest to: [reference.md](reference.md#committing),
[DECISIONS.md](DECISIONS.md#the-commit-is-assembled-by-a-script-not-by-hand).

**When prose is installed, the same commit carries its `Prose:` trailer.**
Skills that sign commits through the shared library commit once, with every
installed skill's trailer
([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
To learn whether prose is installed, ask the `manage-skills` skill (its
`list`): prose is installed when its row says `installed`. prose's SKILL.md
gives its scripts directory, written `$S` below.

If it is, after the last fix and the final `git add`, write the message (subject,
a blank line, body) to `msg.txt`, unstaged, and:

1. Run prose's first call. It lists the prose in the change and prints the
   rules and a pass token:
   `python3 "$S/prose.py" check -F msg.txt --goals "review the fix; check it is safe to merge"`
2. Rewrite the listed comments, docs and message by those rules; restage.
3. Run the second call, which prints the `Prose:` trailer:
   `python3 "$S/prose.py" check -F msg.txt --pass <token>`
4. Commit once, passing the text after `Prose: ` as a family before `--`:

```bash
"$BH" --verified-value "$S/verify-staged.sh" Prose "✓ 4d593e935186:9138830a72a2" -- \
  -F msg.txt "1 iteration, 1 bug fixed" "Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

The message is `msg.txt` itself, the file prose signed. Stage and edit nothing between the
second call and the commit: the script runs prose's verifier first and refuses
the commit if the tree or the message changed. A skip gets the prose pass too.

**A prose pass that touches only comments, docs or the message needs no new
hunt.** The `Bug-hunter-Tree` binding is minted at commit time, over the tree
that lands, so it covers the rewrite. If the pass changes code, code was
written since the last clean pass, and a hunt is owed.

Three things are required every run, and they are the ones agents drop first:

- **The headline counts.** Iterations, fixed, refuted, reported — and, whenever
  anything is open, how many decisions the user owes.
- **Root causes above the findings**, numbered so the user can say "do ①". A
  cause buried under a dozen symptoms is a cause nobody acts on.
- **A `why not` on every finding that was not fixed.** "Reported" with no reason
  is a shrug.

**A skipped run is one line, and it is worth printing.**

```
🔍 bug-hunter · skipped at triage — docs only, no executable code
```

That is the whole *report* — it is not the whole job. Knowing the check ran and
why it stopped is useful, and at one line it costs nothing to skim. The commit
is still made the same way as any other (under *caller commits*, handed back
the same way — [When the caller commits](#when-the-caller-commits)), and the same sentence is the third
argument to the script above:
`"$BH" -F msg.txt "skipped at triage (docs only, no executable code)"`, with
`msg.txt` holding `Fix a typo in the README`.
Keep no-op output proportional — the expensive thing is never a short line
saying nothing happened, it is a long report demanding work that does not need
doing.

### Write down what was rejected, before you commit

A run that reverted a fix, refuted a finding, or chose one approach over another
has produced knowledge that does not survive in the diff — the diff shows what
the code is, never what it stopped being. That knowledge is about the code under
review, and it goes **where this codebase keeps rejected approaches**. This
skill's own `DECISIONS.md` is about this skill — a run writes to it only when
the skill is the code under review:

1. **Its stated convention first.** An `AGENTS.md`, `CLAUDE.md` or
   `CONTRIBUTING.md` that says where decisions go settles it.
2. **Then a home it already has**: a `DECISIONS.md` or ADR directory, the
   `design.md` of an OpenSpec change that covers this code, a decisions section
   in an architecture doc.
3. **A rejection about one site — one fix, one function — goes in a comment at
   that site**, in the codebase's own idiom: present tense, a warning rather
   than a history. That is where the next person tempted back to it will be
   standing.
4. **Create only when none of those exist**: `DECISIONS.md` beside a skill's
   `SKILL.md`; `docs/decisions.md` anywhere else.

An entry says four things: the decision, why, **what was tried and rejected**,
and **where the lesson stops applying**. That last field is not optional; a
lesson recorded without its boundary gets applied outside it. A comment at the
site carries the same in a sentence — the alternative, and what breaks when it
is taken. The shape of each: [reference.md](reference.md#where-a-record-goes).

Three reverts in this skill's own history — recorded in its `DECISIONS.md`
because there the skill *was* the code under review — exist only because they
were written down within minutes of happening. Nothing else would have kept them.

### The commit waits for the run, exactly as the report does

One commit at the end, after the last iteration — not one per iteration. The
fixes from an unfinished run are unverified by definition; a commit says "this is
done", and mid-run it isn't. Work in progress lives in the working tree between
iterations, which is what the abort clause already assumes.

**There is no exception**, and an earlier draft invented one. What an invented
exception provides is a documented reason to do the thing the rule forbids, which
is how every other rule here has been walked around
([DECISIONS.md](DECISIONS.md#the-commit-waits-for-the-run-and-the-iteration-counter-resets)).

What does need saying, because it is a real distinction rather than an escape:
**the rule is about the change under review.** A commit that touches any file the
run is reviewing waits for the run. A genuinely separate change — different
files, its own triage, its own trailer — is its own commit and is not covered.
That test is checkable; "it felt unrelated" is not.

### When the caller commits

**If the brief says "caller commits", the run is the same; only the commit
moves.** A caller that builds its own commits — through an API, in a pipeline,
anywhere this skill does not run `git commit` — says so in the brief:
*caller commits: return the result, do not commit.* Steps 0–8 run as written,
and every rule under *Do not evade this skill* still applies. Step 9 ends
differently:

1. **Do not commit.** Leave the change staged: everything the run reviewed,
   every fix and test it added, and every record it wrote under *Write down
   what was rejected*.
2. **Print the report**, as in any run.
3. **Run the result script last, after the final `git add`.** It mints the
   binding over what is staged and prints the whole block. Its arguments are
   the `Bug-hunter:` value — what the commit script's third argument would
   have been — and the open decisions, one per line, without numbers:

```bash
BR=~/.agents/skills/bug-hunter/scripts/caller-result.sh
[ -x "$BR" ] || BR=~/.claude/skills/bug-hunter/scripts/caller-result.sh
"$BR" "1 iteration, 1 bug fixed" --decisions - <<'EOF'
refund state is rebuilt on every read — 1 fix it now · 2 write it down · 3 skip
EOF
```

   With nothing open, drop `--decisions` and the heredoc. A skip passes its
   `skipped at triage (<reason>)` value and mints nothing.
4. **End the reply with the script's output, whole and unedited.** The caller
   parses it and passes the trailer lines through unchanged:

```
=== bug-hunter result ===
Bug-hunter: 1 iteration, 1 bug fixed
Bug-hunter-Tree: <the hash the script minted>
=== bug-hunter open decisions: 1 ===
① refund state is rebuilt on every read — 1 fix it now · 2 write it down · 3 skip
=== end bug-hunter ===
```

**Never type the block.** The script is the only way to make it, for the same
reason commits go through `commit-with-trailer.sh`: hand-assembled trailers
went wrong until a script took the assembly away
([DECISIONS.md](DECISIONS.md#a-caller-that-commits-gets-the-result-not-the-commit)).
The binding signs the snapshot the run worked on; the caller commits exactly
that tree, or the binding is false. So nothing is staged after the script
runs. If something must be, run the script again.

**Open decisions go to the caller, in that block, never through a picker.**
Nobody can answer a picker in a headless run. The block replaces the hand-off
footer: the caller acts on it — asks a person, lists the decisions in its pull
request, or holds the commit. Choosing for the user is still not yours: an
open decision is never answered 2 or 3 because nobody could be asked. Format
detail and a worked example: [reference.md](reference.md#the-caller-commits-result).

### Then ask, one recommendation at a time

Whenever the report carries a recommendation — a root cause, a finding too large
for the change under review, or anything an abort left unresolved — **stop and
ask the user what to do with it. Each one separately.** Do not apply them
silently, and do not decide on their behalf that they are out of scope. A
recommendation is where a small change prevents a class of bugs rather than one
instance of one.

**Use the host's interactive picker if it has one**, one question per
recommendation, in severity order. Offer only the options that honestly apply:
"implement it now" belongs there when you have a fix you would defend, and when
you do not, say so and offer the other two. Padding the menu with an option you
have no confidence in is how a run ends with a hopeful patch on a problem nobody
understood. A worked example is in
[reference.md](reference.md#asking-about-a-recommendation).

**If the report reached you from an agent you spawned, the asking is yours.**
Its picker could not reach the user and its text asked nobody; see [Whose
decision it is](#whose-decision-it-is) — next reply, before anything else.

Take the answers per item — "1 for ①, 2 for ②" is a normal reply, and so is
"all 1". If the user answers once for everything, that applies to everything.

**1 — fix it now.** Apply the change, then **start the loop over it immediately,
without asking again.** The user already said yes; asking "shall I now check the
fix?" is asking the same question twice and invites a no the second time. A
root-cause fix is the code most in need of checking, not least: written in one
pass, minutes after the analysis, usually touching more than the original change
did — that breadth is what made it a root cause. Every time this skill has
skipped that pass, the next run found something. Say what the fix will touch
before starting it, then apply, loop, and report once at the end.

For a cause the abort left unreviewed rather than unfixed, there is nothing to
apply and **the pass itself is option 1**: a new run at iteration 1, scoped to
that cause — the fixes iteration 3 wrote, and the files they touched. Say
`1 — new run` rather than `fix it now` when that is what the option is, and
never count it as a fourth iteration, in the report or in the trailer.

**2 — write it down.** Record it as a known, accepted gap where this codebase
already keeps them — the same lookup as
[Write down what was rejected](#write-down-what-was-rejected-before-you-commit),
stated convention first and a new file last, but the home is the one for open
questions rather than decisions: a spec's Open Questions or Roads Not Taken
section, an existing OpenSpec change, a `docs/` or ADR entry, a
`DECISIONS.md`-style file if the thing under review keeps one, then the closest
README. Only if none of those exist, create `docs/open-questions.md`. One entry:
the cause, which findings it produced, the recommendation, the odds, and the
date. Commit it with the rest of the change. A recommendation that lives only in
a terminal report is gone when the tab closes, which is choice 3 with extra
steps.

**3 — skip.** Nothing happens. Still name it in the report so the run's record is
complete, and do not raise it again in this session.

What is not on the list is deciding for them. Reporting a cause, moving on, and
letting it evaporate — when the user would have said "fix it" — is the same
failure as never running this skill at all. Relaying that a cause exists, with
no options under it, is the same thing one hop later.

## Never

- Run inside a git `pre-commit` hook.
- `git stash`, amend, or rebase.
- Weaken, skip, or delete an **existing** test to reach green.
- Leave a failing or discarded test in the tree.
- Report a bug with no failing test, or a style opinion of any kind.
- Apply a refactor larger than the change under review.
- Write to this skill's own files — `DECISIONS.md` included — unless they are
  the change under review.
- End a reply holding a decision from the user's list. Written is not asked;
  relayed to you is not relayed to them.
