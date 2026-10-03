# bug-hunter — decisions

**Read this before changing anything in this skill** — `scripts/`, or the rules
in `SKILL.md`. Not because it explains how either works; the code and the rules
do that. Because most of what looks like an obvious improvement here has already
been tried, and the reason it was reverted is not visible from the line you would
be editing.

Every entry is a decision, why it was made, and what was tried and rejected. The
rejected column is the load-bearing one: twice in this file's history a solved
problem was re-solved differently a few lines away, because the record of the
first solution lived at the first site only.

**The hook and mint mechanics are shared** with other skills, and their
decisions live with them, in
[`.agents/lib/commit-trailer/DECISIONS.md`](../../lib/commit-trailer/DECISIONS.md):
reading git state rather than commands, the reflog cursor, the submodule walk,
and why the trailer is minted from the tree. What stays here is bug-hunter's
own: two decisions about its hook's behaviour, then the skill's rules.

---

## A skip is a value for the trailer, not an exemption from it

**Decision.** Two texts reach an agent that never invokes this skill: the
frontmatter `description`, before it decides, and the hook's report, after the
commit lands. Both state that a skip is a trailer value, and neither states the
trailer requirement in a form conditional on the commit containing code.

**Why.** On 2026-09-11 one session made three doc-only commits to a backend repo
— an OpenSpec proposal, its design and spec, and a prose correction, zero code —
each with a bare `git commit -m`, no trailer. The hook fired after each. The
agent read it, reasoned correctly that a doc-only commit has nothing to hunt,
and moved on. Three times, the third after two reports saying so.

Every doc in this skill already had the right answer. `SKILL.md` said a skip
commits through the script "as in Step 9"; the triage table gave the amend; Step
9 carried a worked `"$BH" "DOCS(Readme): fix typo" "" "skipped at triage (docs
only, no executable code)"`. **The agent read none of it, and that is not a
reading failure.** A doc-only commit never invokes this skill, so `SKILL.md` was
never in its context — the only two texts that were are the ones above.

The `description` said `Skips docs, specs, tests, and work-in-progress commits`.
That is the whole basis on which an agent decides whether this skill applies to
the commit it is about to make, and read at that moment it says: not this one.

The report then closed with *Every commit containing code should go through the
bug-hunter skill, and record what happened in a Bug-hunter: trailer.* The
trailer clause is subordinate to "containing code", so a doc-only commit
falsifies the antecedent and the sentence exempts the trailer along with the
hunt. The agent's no-op was that sentence read correctly. Restating the rule
louder somewhere it was already stated would have changed nothing; both edits
are to text that was actually in front of it.

**What this cost, and why it is not a documentation nit.** A trailer that says
`skipped at triage (docs only)` and no trailer at all are the same commit to
everyone except the audit — `git log --invert-grep --grep='Bug-hunter:'` cannot
tell "considered, nothing to review" from "never checked", so a repo that
accumulates the first stops being able to see the second.

**Rejected: having the hook classify the diff** and print `3 of these changed
only documentation`, or amend the trailer itself. Beyond *The report states facts
and stops* above — the command-constructing half produced 28 findings across
eight iterations, and a post-commit hook cannot know the named sha is the
reader's HEAD — a classifier in the hook is a second copy of `reference.md`'s
skip-category table, living in a file that cannot import it. Two copies of that
table drift, which is what this file's opening is about. Listing the categories
in the sentence and letting the reader place its own commit costs no machinery
and cannot disagree with the table, only go stale against it.

**Rejected: lower-friction skip path in the script.** There is nothing to
lower — a skip is three arguments, mints nothing, stages nothing. *The commit is
assembled by a script, not by hand* already built that path for this exact
habit, the "trivial docs commit" arriving with `-m` composed. This incident is
upstream of it: the agent had no reason to think the script applied at all.

**Where this stops applying.** This does not license remedies in the hook's
report. What went in is the standard — unconditional, context-free, naming no
sha and no repair — which is the same line *The report states facts and stops*
drew for trailer placement. The remedy for a commit that already landed stays
in `SKILL.md`'s triage table, which runs in the reader's own frame. Nor is it a
general rule that every doc gets the same sentence: the two edited here are the
only ones read by an agent that has not invoked the skill.

---

## The hook is never told that a run is in progress

**Decision.** Nothing marks "a bug-hunter run is in flight". A commit that lands
mid-run is reported exactly like any other commit without a trailer.

**Why.** A marker file was sketched for this and deferred, and the reason on
record was only sequencing — new code, so its own run. That is not a reason, so
this entry is the real one, worked out afterwards.

The marker would be a file the *agent* writes to tell the hook not to report the
agent. Every other thing this hook trusts is asked of git, which records what
happened rather than what someone intended; the marker would be the single input
supplied by the party being checked, and the failure mode is not a bug but a
habit — a flag that suppresses a report is a flag that gets set early, and the
skill's whole history here is of exceptions being widened until the rule is gone.

**Rejected, and once already deleted.** The `Bug-hunter: run in progress, N
iterations so far` trailer, removed in `6551f4a` with the note that an invented
exception "does provide a documented reason to do the thing the rule forbids,
which is how every other rule here has been walked around". The marker file is
that same exception moved from the message into a dotfile, where it is less
visible rather than more.

**What it would have bought, honestly.** Nothing. `SKILL.md` already says the
commit waits for the run, so a commit landing mid-run is a rule being broken and
reporting it is correct, not a false alarm. The distinction the marker would
draw — *mid-run* versus *skipped entirely* — is one the reader does not need,
because the response to both is the same.

**Where this stops applying.** If a run were ever attested by something the agent
cannot write at will — a signature, or a record git itself keeps — the objection
is about forgeability, not about the feature, and it would not apply.

---
# The skill's rules

Everything above is about `scripts/`. What follows is about `SKILL.md`: why its
rules say what they say. The wording is load-bearing in a way the rule alone does
not show, and each of these is a revert.

## Every anti-evasion rule was added after it was walked through

**Decision.** `SKILL.md` states the evasion rules under one heading, with the
evidence for each compressed to a clause. The evidence is here.

**What was walked through.**
- *Enumerating the moments a run is owed.* An agent finished a loop, committed,
  and asked whether to start the next one — not on the list, functionally
  identical, and asked exactly when the user was most likely to say no. Replaced
  with a property of the code: if code has been written since the last pass that
  came back clean, a pass is owed.
- *Announcing in the future tense.* "That's running next unless you want to stop
  here" · "I'll kick that off if you're happy with it". Each ends the turn with
  the check not running, which hands the decision back as plainly as asking.
- *Interim reports.* A report between iterations made an unfinished run look
  finished and invited stopping early.
- *Deferring the report*, or asking whether one was wanted. The answer to a
  question nobody wanted asked is usually no.
- *Prose instead of the format.* Reads fine; not scannable, countable, or
  comparable to the last run.
- *Committing mid-run.* Sixteen times, before the rule below existed.

**Rejected.** Stating the rules separately, one per situation. An agent looking
for a way out of a check reliably finds the seam between separately-stated rules;
they are one heading because the evasions were one behaviour.

**Where this stops applying.** These are rules about the agent's own conduct, not
about the user. A user asking for a commit is an instruction and needs no licence
from this skill.

## An iteration that fixed something is never the last one

**Decision.** A run stops after a pass that finds nothing — never after one that
finds and fixes.

**Why, measured here.** Iteration 1 found 8 and fixed 6; iteration 2 found 7
more, two of them created by iteration 1's own fixes. Separately, a state where
all 32 tests passed still held 11 bugs, one of them silent on the most common way
an agent commits. A fix is new code, written minutes ago under time pressure by
someone who was just thinking about a different problem, so stopping straight
after writing one stops where the change is least reviewed.

**Rejected.** Treating "I fixed four bugs" as an ending. It is a different claim
from "this code is clean", and only the second was ever wanted.

**Where this stops applying.** The three-iteration cap overrides it, and that
collision is deliberate rather than an oversight: a run whose third iteration
fixed something ends anyway, on an iteration this rule says can never be the
last. The pass it owes is not cancelled, it is handed to the user as a root
cause with a new run behind option 1 — see *There is no fourth iteration; the
abort reports root causes*.

## The commit waits for the run, and the iteration counter resets

**Decision.** One commit at the end of a run, never one per iteration. A *run* is
up to three iterations; whatever the user asks for next starts a new run at
iteration 1.

**Why.** Three commits were made mid-run claiming "1 iteration, 5 bugs fixed" and
"2 iterations, 11 bugs fixed", and the very next iteration found four bugs in
those fixes each time. A commit says "this is done"; mid-run, it is not. The
reset exists because without it the count climbed to "7 iterations, 45 found",
which reads as though the cap had been ignored and hides that each run got its
own clean decision point.

**Rejected, and deleted once already.** The `Bug-hunter: run in progress` trailer
— the same exception in another form as the marker file, and refused for the same
reason. See *The hook is never told that a run is in progress*.

**The real distinction, which is not an escape.** The rule is about the change
under review. A commit touching any file the run is reviewing waits; a genuinely
separate change — different files, its own triage, its own trailer — is its own
commit. That test is checkable; "it felt unrelated" is not.

## There is no fourth iteration; the abort reports root causes

**Decision.** Three iterations is the whole budget. When the third ends with
something still unresolved, the run ends in the Step 9 report with one numbered
root cause per unresolved thing and the same three choices on each — a new run at
iteration 1 scoped to that cause, write it down as a known gap, or skip. Never a
fourth iteration, and never an offer of one.

**Why.** Adam: *"We don't do 4th iterations in bug-hunter."* An open "want
another pass?" at the cap is the future-tense announce this file already records
under *Every anti-evasion rule was added after it was walked through*, arriving
at the moment the user is most likely to say no, and it makes a fixed budget
read as an opening offer. The three choices are the same information with the
decision made answerable: each is an action, the user picks one per cause, and
nothing evaporates because nobody was asked.

**The remainder is a root cause of a different kind, and the report says which.**
Step 6's root cause is about *place* — the real cause sits outside the change
under review, so fixing it there would exceed the scope. The abort's remainder is
about *budget* — the cause sits squarely inside the change under review and the
pass that would have found it does not exist. They are not the same thing and the
report labels each (`kind: scope` / `kind: budget`), because the user is weighing
a different question in each: whether to spend a larger change on something
outside the diff, versus whether to keep looking inside it. What they share is
only the shape of the answer, which is why one set of choices covers both.

**Rejected.**
- **A fourth iteration when the third fixed something.** The argument is
  identical at four, and at five: a run that ends on a fix always leaves an
  unreviewed remainder, so every cap has this edge and moving the cap only moves
  the edge. What actually closes it is a *new run* — cold finder, fresh budget,
  scoped to the remainder — which the reset above already makes the correct
  shape.
- **Reporting the remainder and moving on.** That is choice 3 taken on the
  user's behalf, which `SKILL.md`'s own closing line already names as the same
  failure as never running the skill at all. An accurate description of
  something nobody was asked to decide is not a report, it is a shrug with
  detail.
- **Calling the new run a "4th pass"** in the report, the reply, or the trailer.
  It is iteration 1 of a new run. Counting it onward from three is exactly what
  the reset exists to stop — the count that once climbed to "7 iterations, 45
  found" started as one honest continuation.
- **Exempting the remainder from the pass-is-owed rule** instead of re-homing
  it. "No pass is owed here, the budget ran out" is an invented exception, and
  this file's record is that an invented exception is a documented reason to do
  the thing the rule forbids. The pass is owed; what ran out is the budget for
  taking it inside this run.

**Where this stops applying.** This bounds the *agent's* budget, not the user's.
A user who asks for another pass gets one without argument — that is an
instruction, and it starts a new run at iteration 1 like any other new work.

## A question is asked when the user sees it, not when an agent writes it

**Decision.** The user's decisions — the user's list in `SKILL.md`'s *Whose
decision it is* — count as asked only when they are in a reply the user
reads or a picker the user answers. An agent that receives a report from an
agent it spawned has received Step 9's input, not discharged Step 9: it asks
every open decision in its next reply, before anything else, through its own
picker. The report carries this itself — a headline count of open decisions
and, on any text-form report, a footer addressed to whoever holds it — and the
Step 3 background rule now says what happens when the pass comes back.

**Why.** The skill is written in one voice, to "you", and every rule about the
report assumes your reply is the user's screen: *in the reply the user can
see*, *a run that ends with an unasked question has not ended*, *use the host's
picker*. Delegate the run to a sub-agent and each of those is satisfied one hop
short. The sub-agent writes the report in its reply — to the coordinator. It
would use the picker, but a sub-agent's picker does not reach the user, so it
falls back to text, and the text looks exactly like a question that has been
asked. The coordinator receives a finished-looking report and does what a
finished report invites: it summarises. Two shapes of this, both with a capable
coordinator that had read `SKILL.md` and run the hunt correctly:

- an abort relayed as a status line — *the run aborted* — with the numbered
  causes and their three options nowhere in the reply, so the user had to ask
  what they were meant to decide;
- a capped run's root causes arriving from a backgrounded pass while the
  coordinator was mid-way through other work, and sitting in its context across
  turns until the user found them.

Neither is a reading failure, and neither is evasion. The text saying otherwise
was in `SKILL.md`, read thousands of tokens earlier, and nothing in front of the
coordinator at the moment it decided what to do with the report said the
decision was still open. That is the same shape as *A skip is a value for the
trailer, not an exemption from it*: the fix goes in the text that is provably in
front of the agent when it fails, which here is the report itself. Hence the
footer — the report tells its holder that printing it has asked nobody — and
the headline count, which makes "it aborted" a visibly incomplete summary of a
line that says `3 to decide`.

The picker is why this is more than prose. It is the one mechanism in the skill
that is structural — a turn with a picker open cannot end until the user
answers — and it was already mandated. It failed to fire because it sat with
the wrong agent: the one running the skill had no picker to the user, and the
one with the picker did not know the question was still its to ask. The rule
moves the picker to the hop that has one; it does not add a mechanism.

**Rejected.**
- **A host hook that blocks the turn while a decision is owed** — a `Stop`
  hook scanning for the footer, or similar. It is the genuinely structural
  version, and it is the one thing here that depends on a particular harness.
  Other people's agents run this skill, and the reasoning in *The trailer is
  minted from the tree* about hooks that cannot be tested from the session
  that wires them applies unchanged.
- **A file of owed decisions** the run writes into the tree. The user is not a
  reader of the working tree, so it reaches nobody; and it is the agent writing
  a marker to itself, which *The hook is never told that a run is in progress*
  already declines.
- **Forbidding delegation of the run.** The architecture belongs to whoever
  invokes the skill, and the skill delegates its own steps; a rule against
  running it inside an agent would be ignored by exactly the setups it was
  written for.
- **Stating the rule more loudly in `SKILL.md` alone.** It was already there
  three times, and the agent that failed had read all three. Restating a rule
  where it was already stated changed nothing the last time either (*A skip is
  a value for the trailer*). What went into `SKILL.md` is the distinction that
  was missing — reached an agent versus reached the user — and the checklist
  line, which is the one part of `SKILL.md` an agent carries forward as its own
  artifact.
- **Letting the runner pick a default** — write every open cause down (choice
  2) when nobody can be asked. That is a choice made on the user's behalf, and
  *There is no fourth iteration* records why an accurate record of something
  nobody decided is not a report.
- **Asking about more.** Pulling the agent's own decisions — whether to run,
  iterate, commit a clean run — into the picker would make the picker
  something the user learns to click through, and the decisions that matter
  would be skimmed along with the ones that do not. The two lists exist so the
  boundary is checkable rather than felt.

**Where this stops applying.** Only to the user's list. It does not license
asking whether to run, whether to iterate, or whether to commit a run that
ended clean with nothing open — the anti-evasion rules stand. The footer is for
the text form: a report whose questions went through the user's picker in the
same reply drops it. And nothing here verifies anything — an agent that reads
the footer and summarises anyway has no hook behind it, and the deferred
delegation-verification mechanism would not catch it either, since it would
attest that a pass ran, not that its output reached anyone.

## The full suite is a gate on the run, not on the iteration

**Decision.** The full suite runs twice a run: at Step 2 for the baseline, and
once more immediately before the Step 9 report. An intermediate iteration's Step 7
runs the new regression tests plus whatever existing tests cover the files the fix
touched.

**Why.** Contract item 4 is a claim about what gets reported and committed —
nothing leaves the run without the closing full run, so it is still checked before
anyone is told the code is clean. What changed is how many times it is checked on
the way there. A three-iteration run used to pay for four full suites and now pays
for two — the last iteration's was always the closing gate; the two before it
gated work nobody outside the run can see yet. On a project whose suite takes
minutes that was the largest fixed cost in the loop. The signal an intermediate
iteration actually needs is narrow: a fix breaking something is nearly always a
fix breaking something near itself, minutes after it was written.

**Rejected.** The full suite every iteration, which is what this replaces. It pays
for breadth at the moment the breadth is least likely to fire, and the run pays
again at the end regardless. Also rejected: dropping the intermediate run to the
*new tests alone*. Then a fix that breaks a neighbour survives to the closing
gate, where three iterations of fixes sit in the tree at once and nothing says
which one did it — the targeted run is bought precisely to keep that attribution
cheap.

**Consequence, accepted.** A break in a file no iteration touched surfaces later
than it used to — at the closing gate rather than the iteration that caused it.
The response is unchanged (fix the fix, or revert it and report it unresolved),
and the run does not end until it holds.

**Where this stops applying.** It assumes the closing gate really runs before the
report, which is the whole of its safety — a run that reports without it has
dropped contract item 4, not economised on it. It also assumes the project can
select a subset cheaply. Where it cannot — no selection, or a suite whose only
meaningful signal is end-to-end — the targeted run *is* the full run and nothing
here changes.

## A refuter judges findings, not proposals

**Decision.** Findings go to the refuter; design decisions go to the user.

**Why.** A refuter is told to default to skepticism, which is correct for "is
this bug real" and wrong for anything else — pointed at a proposed design change,
that disposition defends whatever exists today. It cost eight iterations here: a
proposal to stop emitting git commands was refuted on a plausible argument, and
the machinery it defended went on to produce 28 findings before the proposal was
adopted anyway.

**Where this stops applying.** One question about fixes is factual rather than
evaluative — *do any of these fight each other?* — and does belong with the
refuter, because a conflict found there costs a sentence and found afterwards
costs both fixes.

## Documentation written in the same session is not evidence of intent

**Decision.** A refuter's brief says which spec, design or task text predates the
change under review, and the refuter checks provenance — `git log -S "<phrase>" --
<file>`, `git diff`, `git blame` — before treating any passage as a deliberate
decision. Text that exists in no commit refutes nothing.

**Why.** Iteration 1 of a run fixed three findings; one added an in-pass circuit
breaker to a scheduled backfill job, bounding the blast radius of a systemic
failure. The implementer then documented that fix in the project's OpenSpec
`design.md` and `tasks.md` — same session, uncommitted. Iteration 2's find pass
found a real gap in the new breaker: it counted only *thrown* transport failures,
so the same failure class escaped it whenever it arrived shaped as an HTTP 200 with
an empty result, and an alternating-failure outage never accumulated enough
*consecutive* throws to trip it. Both were reproduced, with tests observed red.

The refuter assigned to that finding quoted the implementer's own fresh
`design.md` sentence — "reset the moment any call is answered … a no-result is
equally good proof the upstream is alive" — plus the matching `tasks.md` line, and
ruled it REFUTED as "a deliberate, documented design choice … the code correctly
implements what was specified, including the specific reasoning the finder is now
second-guessing." Nothing in that verdict's wording or confidence distinguishes it
from a refutation on the merits, which is what makes it expensive: a proven finding
was dropped for the one reason that cannot be checked by reading the code. It was
caught by asking git instead — `git log -1 --format=%h -S "equally good proof" --
<design.md>` returned nothing, because the sentence existed in no commit, only as
an unstaged `+` line written minutes earlier. With the "intentional" leg void, the
finding stood, and was fixed.

A second, generalizable error rode along in the same verdict: it quoted a spec rule
governing a *different decision* than the finding was about — what to write for a
row that was attempted, versus whether to keep attempting further rows — and
treated it as dispositive. Hence the second rule in `reference.md`: a passage
refutes a finding only when it governs the same decision.

**Rejected.** Keeping spec and design docs out of the refuter's brief altogether.
That gives up the refutation this step is most valuable for — a finding that
asserts something the code never promised, killed by the contract saying so — to
fix a dating problem. Also rejected: telling the refuter to discount documentation
generally, which is the same loss by degrees. What the refuter lacked was not
skepticism, it was the timestamp, and supplying that is cheaper than blinding it.

**Not a claim that refuters can no longer be fooled.** This closes one failure
mode — circular intent, where the change under review is quoted back as its own
justification. A refuter can still be wrong about reachability, about what a caller
guarantees, or about what a genuinely committed spec means.

**Where this stops applying.** Only to doc text authored in the same session as the
code, or otherwise uncommitted and in flight. Refuting a finding against genuinely
pre-existing, committed spec is exactly what a refuter is for, and nothing here is
a licence to discount it: a committed contract saying the behavior is intended is a
real refutation, and provenance checked once and found to predate the change settles
the question rather than reopening it.

## Step 6 resumes the finder; the refuters and the next find pass stay cold

**Decision.** Within an iteration, Step 6 does not spawn a fresh fixer by
default. It resumes that iteration's Step 3 finder via `SendMessage`, passing
the surviving findings, the refuter verdicts, and Step 5's fix-conflict notes.
A fresh `Agent` call — strongest available model, full brief — is the fallback,
used only when that finder is no longer reachable (errored, session ended, or
it belongs to an earlier iteration).

**Why.** Nothing mutates the source between Find and Fix: Step 4 only adds test
files, Step 5 only reads. The finder has already read every changed file in
full, traced each candidate's reachability, and run the candidates — the most
expensive context in the loop, and exactly what a cold fixer spends its first
tokens rebuilding. There is no independence to protect here: the fixer was
never a check on the finder — it is handed the surviving findings as facts to
fix, and the refuters have already done the checking.

**Consequence, accepted.** A finder fixing its own findings is anchored on the
framing it built — it may defend its diagnosis rather than notice a simpler
fix. Two things bound that: Step 6's prevention question ("is there a better
approach?") is asked either way, and Step 8 guarantees the fixes get a fresh
pair of eyes — the next iteration's finder is cold by this entry's own scope
rule, and a run never ends on an iteration that fixed something.

**Rejected.** Spawning a fresh strongest-model fixer every time, which is what
the earlier wording implied — it re-billed the finder's whole investigation for
no independence gain. Also rejected: retiring the byte-stable prompt prefix
rule shared between Steps 3 and 6 as obsolete. It still governs the fallback
path and the Step 3 spawns themselves, which repeat every iteration.

**Where this stops applying.** This is within-iteration reuse only, and it does
not extend in either direction:

- **Not to Step 5's refuters.** Their entire value is independence — an agent
  that has not seen the finder's reasoning (see *A refuter judges findings, not
  proposals*). Resuming the finder as a refuter, or letting one refuter see
  another's reasoning, destroys the step to save its cost. Every refuter stays
  fresh, every time, no exceptions.
- **Not to the next iteration's Step 3 finder.** Step 6 rewrites the files, so
  a resumed finder's context describes code that no longer exists — findings
  against a stale version are worthless (Step 3's own backgrounding rule), and
  the record in *An iteration that fixed something is never the last one* is
  that iteration 2 finds bugs iteration 1's fixes created, which only a fresh
  read of the fixed code catches.

## Triage applies to the hook's own reports

**Decision.** A hook report is an input to triage, not an instruction to run the
whole skill.

**Why.** It sets the price of a false alarm. A hook that fires wrongly and costs
a thirty-minute run is one people uninstall; one that costs ten seconds of triage
plus an amended trailer is one people tolerate while it gets fixed.

**Not a licence.** It does not make a wrong report harmless — repeated misfires
are a bug in the hook to be fixed, not a cost to absorb. It stops one wrong
report from costing a working session, and nothing more.

## The trailer rule is stated inline, not only pointed at

**Decision.** `SKILL.md` states at the commit step that the trailer is passed as
`--trailer` and never typed into the message. `reference.md` keeps the
explanation, the shapes table and the worked examples.

**Why.** Two commits in one week landed with a hand-written `Bug-hunter:` line
and no trailer git could see, and the hook reported both. One was the main
agent, one an independently-run subagent on an unrelated fix; both were repaired
after the fact with `git commit --amend --trailer`. `reference.md` already said
all of this, correctly — neither agent had opened it, because `SKILL.md`'s
commit step only pointed at it, and a pointer gets followed after the mistake
rather than before. By the time an agent reaches the commit it has the whole
message composed in its head and runs `git commit -m` with the line already in
it. Nothing in the main flow said that step had a sharp edge, so nothing
interrupted that.

**Rejected.** Copying the trailer-placement section into `SKILL.md`. What failed
was not a missing explanation but a rule that was absent from the flow, and two
copies of a table drift apart — the failure this file's opening is about. What
went inline is the rule, the verify command, and the repair; the *why* stays
here in one place.

**Measured, because the received account was wrong.** "A blank line before it
makes it a new paragraph" is not the failure — a `Bug-hunter:` line alone in the
last paragraph parses fine, blank line and all. The shapes that actually lose it
are anything landing after it in a later paragraph (the mandated
`Co-Authored-By` footer is the common one), a prose line beside it in the same
paragraph, and an unindented wrap. `reference.md` asserted the blank-line
version and is corrected. Run the shapes against a scratch repo before writing
this kind of claim down.

**Where this stops applying.** Only to rules an agent *executes* at a named step,
where getting one wrong produces a wrong artifact. Procedure — how to drive a
test red, how to shape a report — stays in `reference.md`. Inlining that class
too is how `SKILL.md` becomes the document nobody finishes.

## The mint script is located with a two-target fallback, not one hardcoded path

**Decision.** Every instruction that names `mint-trailer.sh` tries
`~/.agents/skills/bug-hunter/scripts/mint-trailer.sh` first and falls back to
`~/.claude/skills/bug-hunter/scripts/mint-trailer.sh` — a two-line
`MINT=...; [ -x "$MINT" ] || MINT=...` in both code examples, and both paths
named in the prose mention.

**Why.** Adam watched agents struggle to find the script at the commit step.
The docs hardcoded the `~/.agents/skills` path alone, but `manage-skills`
installs every skill into two independent targets (`~/.agents/skills` for
cross-tool agents, `~/.claude/skills` for Claude Code) and its own docs warn
that a real install can populate only one — its examples hedge every path with
an explicit `# or` between the two for exactly this reason. An agent whose
install only populated `~/.claude/skills/bug-hunter` was sent to a path that
does not exist, with no fallback, and had to guess. Both targets symlink the
whole skill directory, so the script sits at the same relative location under
each — the fallback is safe by construction.

**Rejected.** Searching the filesystem as the primary instruction — the two
documented targets cover every install `manage-skills` produces, and a search
is slower and vaguer than two known paths. A one-line "if neither exists,
search under both" escape hatch stays in `reference.md` for installs made by
some other mechanism.

**Where this stops applying.** This is only about *locating* the script. The
minting mechanism — `git write-tree` over the staged index, run after the last
`git add`, output passed as `--trailer` — is unchanged, and so is the rule that
only the path to the script is absolute, never the git command it runs.

## The commit is assembled by a script, not by hand

**Decision.** `SKILL.md`'s commit step names one command —
`scripts/commit-with-trailer.sh -F msg.txt <Bug-hunter value>
[<Co-Authored-By value>]`, or with the message as `<subject> <body>` in place
of `-F msg.txt` — for every commit this skill makes, skips included.
The hook's report names the same script wherever it used to show a
`git commit … --trailer …` example. `--trailer` and `mint-trailer.sh` are still
the mechanism; `reference.md` now documents them as what the script does, not
as what the agent types.

**Why.** The previous two entries were each a response to the same failure —
a `Bug-hunter:` line typed into the message body — and each was correct: the
rule went inline, in bold, with the exact command shown twice, and the mint
step got a path that resolves. Agents kept typing the trailer into `-m` anyway,
several times in one evening, in a session with `SKILL.md` loaded. So the
failure is not ignorance of the rule. It is assembly under time pressure: a
"trivial docs commit" arrives with the message already composed, `-m` is the
habit, and the trailer goes where the `Co-Authored-By` footer goes — the body.
A rule that says "assemble it differently" competes with that habit at the
moment the habit is strongest and attention is lowest, and it loses some
fraction of the time no matter how it is worded.

A script removes the assembly. The trailer value is an argument, and the only
way to supply it is the right way; the skip-or-mint decision is read off that
value rather than remembered; the `Co-Authored-By` — the footer that actually
pushes a hand-written trailer out of the block — is an argument too; and the
two-target lookup happens once, for the wrapper, because it finds
`mint-trailer.sh` next to itself. What is left to get wrong is the one thing
that was never the problem: which path the skill is installed at.

The hook names the script for a different reason. Its report is the one text an
agent provably reads at the moment of failure — every one of the repaired
commits was repaired because the report said so — and its own example was a
hand-built `git commit -m … --trailer …`. An agent acting on the report re-did
the assembly step, by hand, that had just gone wrong. Naming the script there
stays inside *The report states facts and stops*: a placeholder call with a path
under `~` is context-free in exactly the way the old example was, and the text
describes how this skill commits, not what to do with the named sha.

**Rejected.**
- Stronger prose, or a third example. Two bold statements and two examples had
  already failed on the same agent in the same session; this file's opening is
  about not re-solving a solved problem the same way a few lines away.
- Having the script stage as well as commit. What to stage is a judgement
  (*Committing*: never `git add -A`), and folding it in would make a
  correctness tool decide scope.
- Having the hook print the exact repair for the reported commit. That is the
  remedy machinery *The report states facts and stops* removed, and the reason
  it was removed — the hook cannot see the reader's HEAD — is unchanged.
- Keeping the hand-typed `git commit … --trailer` form in `SKILL.md` beside
  the script "for when the script is not installed". A second documented way
  is the one that gets used under pressure, and both install targets carry
  the script whenever they carry the skill.

**Found by running this skill over the script before it landed.** Four
reproduced, one refuted; each is a rule the script now enforces rather than a
one-off patch:

- **A `$(...)` inside another command's argument list is not covered by
  `set -e`.** `set -- "$@" --trailer "$("$mint")"` carried on when the mint
  failed, because `set` itself returned 0, and handed `git commit` an empty
  `--trailer ""` — which git 2.54 refuses and every earlier git with `--trailer`
  (Apple's 2.50.1 on this machine included) accepted, landing the commit with
  its binding missing or its block split. Capture to a variable with `|| exit`
  first; never let a failing-capable substitution ride inside `set --`.
- **The values are validated before anything with a side effect runs.** An
  empty or whitespace-only value became `Bug-hunter:` with nothing after it,
  which git reads as no trailer. A line break inside argument 3 *or* 4 landed
  an unindented continuation that ended the trailer block for everything after
  it — the freshly minted binding included — with the wrapper exiting 0 and the
  hook then advising "use the wrapper". Both are refused with exit 2; trailing
  whitespace is trimmed rather than refused, because a heredoc-built value ends
  in a newline and git trims it anyway. *Rejected:* indenting the continuation
  so git reads one folded trailer — a legitimate shape the hook already
  `unfold`s, but a more generous contract with more surface, and a two-line
  reason belongs in the report, not the trailer.
- **The commit pins `trailer.ifexists`, `trailer.ifmissing` and
  `trailer.separators` for that one command.** git matches trailer tokens by
  prefix, so `Bug-hunter-Tree` "already exists" whenever `Bug-hunter` does: a
  user's `ifexists=replace` made the mint overwrite the `Bug-hunter` trailer,
  `doNothing` dropped the mint, `ifmissing=doNothing` dropped all three. The
  write side of the same principle the hook's `g()` applies with
  `log.showSignature=false`: git means git, not git plus the user's config.
- **Refuted, and why:** a skip value with a leading space (`" skipped …"`)
  missed the `[Ss]kipped*` test and got minted. Cosmetic — the binding is a
  true statement about the landed tree, the hook and the audit ignore it, and
  the input is a typo. The trim above removes it incidentally; no code exists
  for it on purpose.

The second pass, over those fixes, found two more of the same kind — a value
the script trusted without looking at it:

- **The subject is checked for emptiness too.** `git commit -m ""` is refused
  by git; `git commit -m "" --trailer "Bug-hunter: …"` is not, because the
  trailer makes the message non-empty — and then the trailer *is* the title
  paragraph, so git reads no trailer at all. The wrapper had turned a refusal
  git would have made into a landed, unchecked commit. Refused with exit 2; the
  trim is used for the test only, and the subject reaches `-m` as given.
- **The value the script mints is held to the same standard as the two it is
  handed.** `mint-trailer.sh` captured `git write-tree 2>&1`, so anything git
  said on stderr while succeeding — `GIT_TRACE=1`, a `core.fsmonitor` hook
  path from another machine — arrived ahead of the hash, and the wrapper passed
  that two-line value straight to `--trailer`. It now requires exactly one line
  of `Bug-hunter-Tree: <hex>` and exits 1 otherwise, naming what it got. The
  `2>&1` itself was the cause, in a committed sibling this change did not
  originally touch — reported rather than fixed in that pass, and fixed as its
  own follow-up (see below).

The third pass, over those two guards, came back clean. Its one candidate —
a `#`-first subject under a user's `commit.cleanup=strip`, which git deletes
after the wrapper accepted it — was refuted: plain `git commit -m "#123 …"` is
refused by git under that setting, so nobody who has both ever reaches this
script. No guard was added; a `-c commit.cleanup=whitespace` pin would be the
shape if one ever is, since `core.commentChar` makes any textual check a
guess.

**Where this stops applying.** The script creates a commit; it does not amend
one. Adding a trailer to a commit that already landed — the triage table, a
hook report on a local commit — stays `git commit --amend --no-edit --trailer
"…"`, because amend is exactly the case where "which commit is HEAD for the
reader" matters and that judgement belongs to the reader. Nor does this change
what the binding attests to: an agent that calls the script with counts it
invented still passes, as *The trailer is minted from the tree* already says.
And the `commit` skill's own path when bug-hunter is not installed has no
script to call and keeps `--trailer`.

**Both root causes the run reported were fixed as a follow-up, same day.**
`mint-trailer.sh` now captures `git write-tree`'s stdout and stderr
separately — a temp file for stderr, read back only for the failure message —
so a successful write-tree can no longer leak anything onto the same line as
the hash, regardless of `GIT_TRACE` or a stale `core.fsmonitor` path. And the
hook's `g()` now pins `trailer.separators=:` alongside `log.showSignature=false`,
closing the read-side half of the trailer-config problem the write-side pin
above only ever covered half of: a repo configured without `:` in that set no
longer blinds the hook to a real, correctly-bound trailer. Both are exercised
by their own tests (`test_mint_trailer_does_not_leak_stderr_into_a_successful_binding`,
`test_a_nondefault_trailer_separators_config_does_not_blind_it`), not just
described here.

## A run writes to the code under review, never to this skill's own files

**Decision.** What a run learns — an approach reverted, a finding refuted, a gap
the user chose to accept — is knowledge about the codebase under review, and it
is recorded there. This skill's `DECISIONS.md` is about this skill's design; a
run touches it, or any other file of the skill's, only when the skill is itself
the code under review. Stated in `SKILL.md`'s *Never* list, at Step 9's
write-down, and in the header, which no longer sends Step 6 here before a fix.
Where in the codebase: its stated convention (`AGENTS.md`, `CLAUDE.md`,
`CONTRIBUTING.md`) first, then a home it already has, then a comment at the
site for a rejection about one site, and a new file only when none of those
exist — `DECISIONS.md` beside a `SKILL.md`, `docs/decisions.md` elsewhere. Step
5's refuter brief and Step 6's pre-fix read name the same record.

**Why.** `SKILL.md` said "add it to the skill's `DECISIONS.md` (create one if
there is none)", and its header sent Step 6 to this file "before writing a fix".
Both sentences were written while this skill was developed by running it on
itself, where the code under review and the skill are one directory and "the
skill's `DECISIONS.md`" and "the codebase's record" name the same file. Pointed
at anything else, the two meanings split, and the sentences resolve to the wrong
one: a run over an ordinary TypeScript project reverted two approaches, and the
agent following Step 9 proposed creating a `DECISIONS.md` for it — a note about
that project's behaviour, headed for a file about how bug-hunter works, where
nobody debugging that project would read it. The project's own `AGENTS.md`
already said rejected alternatives belong in an OpenSpec change's `design.md`,
and its source recorded one-site rejections as comments in a settled idiom.
Neither passage led there; the user had to ask what the agent meant.

The defect is one of kind, not of a missing fallback. Seventy lines below, option
2 had a placement chain for accepted gaps — a spec's Open Questions, an existing
change, `docs/`, the closest README — and the chain was fine; what it lacked was
the first stop, the codebase's stated convention, and any notion of a comment at
the site, which for a rejected implementation approach is where the record is
read: by the person about to make the opposite choice, standing at that line.

**Rejected.**
- Reading it as a gap and adding a chain under "the skill's `DECISIONS.md`, or
  the codebase's equivalent". The phrase presumes a referent most subjects lack,
  and it keeps the wrong default; the addendum is what gets skipped under
  pressure.
- One chain for both kinds of record. They differ in reader: a rejection is read
  by someone about to make the opposite choice, which is why it can live at the
  site; a gap is read by whoever picks it up later, who is standing nowhere in
  particular. One lookup, two lists of homes.
- A root `DECISIONS.md` as the fallback for any codebase. That imports this
  repository's convention into someone else's; `docs/decisions.md` sits beside
  the `docs/open-questions.md` option 2 already creates.
- Moving the chain to `reference.md` and pointing at it. Placement is a rule an
  agent executes at a named step, and getting it wrong produced a wrong
  artifact; per *The trailer rule is stated inline, not only pointed at*, the
  rule is inline and `reference.md` keeps the shapes.

**Where this stops applying.** When the subject under review is this skill, it
is the codebase, and every rule above lands here: a run over `scripts/` or
`SKILL.md` writes its reverts to this file, as this file's history shows. Nothing
here changes what an entry contains — the decision, why, what was tried and
rejected, and where it stops applying — only where it goes.

---

## A caller that commits gets the result, not the commit

**Decision.** A brief that says "caller commits" runs the whole skill and stops
at Step 9 before the commit. The run leaves the change staged, prints the
report, and ends with a fixed result block that `scripts/caller-result.sh`
mints and prints: the `Bug-hunter:` and `Bug-hunter-Tree:` lines, then the open
decisions with a count. The caller commits, passing the two lines through as trailers.

**Why.** Some callers build commits themselves — Igor
(adamstallard/igor#139) creates them through GitHub's API after an LLM step and
never runs `git commit` locally. The skill already had the pieces: Step 9's
"commit or leave it for review", and the hand-off footer for a run inside
another agent. What it lacked was a contract a program can rely on: a trigger,
a place to stop, and output in a shape a parser reads.

The mint moves with the commit, not ahead of it. A skill signs the snapshot it
worked on, and whatever creates the commit makes its tree equal that snapshot —
the same rule the commit script follows, where minting and committing happen
at the same moment. Here they are two moments, so the caller carries the
obligation the script used to discharge.

Open decisions go into the block because a headless run has no picker that
reaches anyone. *A question is asked when the user sees it* already says a
report that reached an agent has asked nobody; the block makes that hand-off
explicit and parseable.

**A script prints the block; the agent never types it.** `scripts/caller-result.sh`
takes the `Bug-hunter:` value and the open decisions, runs the mint itself
(none for a skip), and prints the block through the shared library's
`result-block.sh`, the format's one definition. The first version of this mode
had the agent write the block by hand, copying the mint's output into it. That
is the assembly *The commit is assembled by a script, not by hand* removed:
hand-typed trailers went wrong under pressure however the rule was worded, and
a block a program parses fails the same way — a line retyped, a count off by
one, a tree line from an earlier mint. Decided by Adam, 2026-09-27, for every
skill that ends this way, which is why the format lives in the library.

**Rejected.**
- **A prompt-only convention in the caller** — "run bug-hunter, but don't
  commit, and print the trailer". It drifts: each caller words it differently,
  and nothing in this skill says where to stop, when to mint, or what to print.
  It also fights Step 9, whose commit step is written to be hard to skip; a
  caller's sentence against that text loses some of the time, the same way
  prose lost to the habit in *The commit is assembled by a script*.
- **Reusing report-only mode.** It leaves the change for a person to review
  and prints nothing a program can take. It mints nothing, so the caller would
  have to mint itself — recalling the step the binding exists to make
  unrecallable.
- **Answering open decisions by default when nobody can be asked.** A choice
  made on the user's behalf; *A question is asked when the user sees it*
  rejects it for the same reason.
- **The block written by hand from a documented format.** The first version
  of this mode. See the paragraph above.

**Where this stops applying.** Only when the brief says so. A run inside
another agent with no such phrase commits as usual — the `commit` skill relies
on that. The mode moves the commit and nothing else: triage, the loop, the
full-suite gate and the report are unchanged, and a caller cannot use it to
skip them. The binding attests to the tree at the mint; it says nothing about
a commit whose tree differs, which the hook reports as it would any other.
The script ends at its own output: the agent still relays that output into
its reply, and a caller parsing the reply gets whatever the relay kept. SKILL.md
says to end with it whole and unedited; nothing enforces it.

---

## Other skills' trailers ride on this skill's commit

**Decision (Adam, 2026-10-01).** Step 9 commits once with every installed
trailer skill's value, under the shared library's rule
([Every installed skill's trailer, on one commit](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
When prose is installed, Step 9 runs its two `check` calls and passes the
`Prose:` value to `commit-with-trailer.sh`.

**The script's argument rule.** Leading `--verified-value <verifier> <Key>
<value>` families, any number, passed to the library unchanged, which
validates them; then `--`, required after a family; then the four positional
arguments as before. Why each part:
- **Only `--verified-value`.** The script adds the Bug-hunter family and
  `Co-Authored-By` itself. A `--minted` or `--minted-by` family would be a
  second mint path the script does not vouch for, and `--co-authored-by` a
  second way to pass the fourth argument. Any other word in front is read as
  the subject, so the library's option names are refused there, exit 2.
- **`--` required after a family.** Each family takes three words, so an empty
  unquoted variable inside one, or a forgotten `--`, shifts the subject, body
  and value one place. Requiring `--` refuses that, as the library does for
  its own options.
- **`--` allowed with no family,** so the separator means the same in both
  forms; a subject of exactly `--` is refused.

**Rejected.** The library's other options passed through as well: nothing
needs them, and each is a way to land a family this skill did not mint.

---

## Triage reads the diff, not a label

**Decision.** Triage classifies a change by what its diff touches —
formatting only, a pure rename or move, only docs, tests or specs, git's own
revert or merge — and reviews everything else. Nothing in this skill asks for
a commit message first or reads a subject prefix. Decided by Adam, 2026-10-01.

**Why.** The public skills impose no commit convention, and
triage built one in: agents were told to write the message first with an honest
label (`WIP:`, `STYLE:`, `CHORE(move):`, `DOCS:` and so on) so triage could use
it as a skip signal. The label was never decisive. "A label only skips if the
diff agrees with it" meant the diff already made every call; the label was a
hint that cost a convention in every repository that ran the skill.

**The exception: work in progress.** It is the one intent a diff can't show —
half-finished logic looks exactly like finished logic. So a checkpoint is
skipped only when the user asked for one in the conversation, never because a
subject says so. It still defers rather than exempts: the code is reviewed when
it lands in a commit that is not a checkpoint.

**Rejected.**
- **Labels as an optional hint.** Any label triage reads is a convention agents
  learn to write, and a repository with a different one gets wrong skips or
  reviews it can't explain. The hint added nothing the diff didn't already
  decide.
