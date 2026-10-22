# spec-check — decisions

`spec-check` does the part of spec review that needs every other spec in
mind, so the person reviewing judges only whether the rules are right. It
serves the spec stage of review: a change's specification is reviewed and
approved before any code for it is written, and that review is where a
reviewer's time goes. It has two parts: a script, `scripts/spec_check.py`,
and a consistency read done by a fresh subagent. The script's `check`
subcommand runs the mechanical checks, `sign` runs them on the staged tree
and prints the commit trailer, and `setup` records whether the repository
enforces the decisions-first rule.
This file is why it works the way it does.

Each entry: the decision, why, and what was rejected.

---

## Why the skill exists, and what it is checked against

**Decision.** The checklist in [consistency-read.md](consistency-read.md) is
built from one run. Four OpenSpec changes were drafted, and a fresh agent
cross-checked each against the rest of the corpus. The cross-checks made 44
amendments, in eleven kinds: contradictions inside a change and with other
specs, changes or open pull requests; a rule stated twice; a SHALL with no
scenario; an undefined term; rationale in requirement text; stale citations;
unhandled hazards; a workflow interaction that voided a change; an unmeasured
fact stated as known; and evidence shown as checked when its source did not
exist. The script takes the kinds a program can detect, and the subagent's
consistency read takes the rest, undefined terms among them (see *Undefined
terms are left to the consistency read*).

**Why.** Those are the mistakes a careful author made. A checklist from
first principles would rank them by guesswork.

---

## A skill plus a script, not a script alone

**Decision.** The script checks what is mechanical. The skill directs the
consistency read, the fixing and the commit.

**Why.** Most of the 44 amendments were judgment: whether two rules can both
hold, whether a hazard is handled, whether a fact was measured. Of the eleven
kinds, only a SHALL with no scenario, a rule stated twice and stale
citations can be decided by a program. The script also checks one thing
outside them: that the proposal opens with its decisions. A script alone would pass the
specs that needed the most work.

**Rejected.**
- **Repeating what `openspec validate --strict` checks.** The script runs it
  and shows its result instead. The one overlap is a requirement with no
  scenario: validate reports it with no line number, and the script needs it
  to say where.
- **A heuristic for "every SHALL sentence has a scenario".** Counting
  normative sentences against scenarios flags nearly every real requirement:
  one scenario often tests several sentences. That judgment is the
  subagent's (checklist item 4).

---

## A citation fails only where it cannot be wrong

**Decision (Adam, 2026-10-13).** A citation is an error only when it has a `/`
and the cited line is in neither the base branch nor the change's own copy of
the file: the file is missing from both, or both are shorter than the line.
Every other citation finding is a check, which never fails the run: a bare
name such as `config.py:50`, whether it matches no file or several, and a
line that only the change adds. Text in a code fence, including a fence inside a
list item or a blockquote, is never read as a citation. Fences follow
CommonMark, with a fence's indent counted from the content column of the list
item it sits in. A cited path is read the way the file system would read it:
through symlinks. A path into a submodule cannot be read from the parent
repository, so a citation there is at most a check.

**Why.** `sign` refuses while any error remains, so a false error stops a
correct spec from being committed. Six passes of bug-hunter, the skill that
hunts for bugs before a commit, each found the next case where guessing at
citations misread ordinary spec text. The cases were of four kinds:
- an IP address, a service address (`redis.cache:6379`) or an image name
  read as a file;
- a quoted stack trace read as a citation;
- a citation of code the change's implementation adds, wrongly called
  broken (the implementation is committed on the spec's branch once the
  spec is approved, so the base never has it);
- a bare name that matched a different file than the one meant.

Each narrower guess fixed one input and broke another. A path with a `/` that
neither tree has, at that line, is the one citation the script can be sure is
broken.

**The decisions section is read with the same caution: only an
unmistakable label ends it.** Each list item is a decision until the "still
open" label, and a label guessed wrongly would leave decisions unchecked or
call open questions decisions. The label counts only
as a whole label: a heading, a bold or italic label, a line ending in a
colon, or a line saying nothing else. An indented line continues the
decision above it, whatever it says.

**Rejected:**
- An allowlist of file extensions deciding which bare names are files. Each
  version of the list had a gap the next pass found. A list of host
  suffixes survives only to skip addresses such as `example.com:443`, which
  are never files.
- Treating every citation as a check. That would drop the error for a
  citation copied from another branch, whose line no longer exists here.

---

## A stacked change declares what it builds on

**Decision (Adam, 2026-10-21).** A change that applies on top of another open
change says so in its `proposal.md`, one line per dependency, right after
the title:

```markdown
Builds on: seat-files (adamstallard/igor#171)
```

The syntax is exactly `Builds on: <change> (<owner>/<repo>#<number>)`, alone
on its line. Several lines list a chain in the order it applies to main.
`check` and `sign` then read each dependency's change from its pull
request's head commit. They apply the dependencies' deltas to the specs of
the tree being checked, in memory, one dependency after another in the
listed order. Within each delta they apply renames, then removals, then
modifications, then additions, as `openspec archive` does. Every check on
the stacked change then runs against that combined state.

A declaration brings two more kinds of error:
- `stack`: a line that cannot be read, a dependency that cannot be fetched
  or does not apply, or a dependency already archived. An archived
  dependency is an error, not something skipped quietly, so that the stale
  line is removed: main already holds that dependency's result. When the
  combined state cannot be built, the duplicate and drift checks do not run
  for the change, and the error says so. The other checks, such as
  `no-scenario` and `citation`, do not depend on it and still run.
- `drift`: the stacked change modifies, removes or renames a requirement
  that main plus its dependencies no longer define, or keeps a sentence the
  dependency has since replaced (see *Why drift reads the dependency's
  history*).

**An archive counts as the dependency only when its proposal matches.** The
dependency is archived when its pull request has merged and an archive
directory of its name holds the same `proposal.md` as the pull request's
head. A change name can be reused after an older change of that name was
archived, and the older change's proposal differs. A merged change not yet
archived is read from its pull request, like an open one.

**Why.** igor PR #216 (change `lore-search`) builds on igor PR #171 (change
`seat-files`), which renames a `task-execution` requirement and rewrites it.
Once #216's delta restated #171's new requirement, `check` reported
duplicates on #216: sentences of #171's new requirement are also in main's
old requirement, which only #171 removes. The duplicate check excuses such a
pair only when the change being checked removes or renames the old
requirement itself. A removal by another change does not count, even with
both changes in one tree, and #216 had no way to say that it applies on top
of #171. In igor, stacking is normal: igor issue #204 sets the order in
which about twenty open changes are archived.

**Why a line in the proposal.** It sits in the change that depends, so a
reviewer reading the proposal sees what it rests on, and the change's checks
depend on nothing outside the change and the pull requests it names. Its
form is fixed so that a near miss (`**Builds on:**`, a bare `#171`, a list
item) is a `stack` error rather than a line silently ignored.

**Why the dependency is read from its pull request.** The pull request is
where its current text is, and where its author keeps changing it. A copy
in the stacked branch would go stale silently, which is exactly what the
drift check exists to catch. Reading the head commit with `git show` checks
nothing out. When the branch is gone, as after a merge, GitHub's
`refs/pull/<n>/head` still has it.

**Why drift reads the dependency's history.** The stacked change's MODIFIED
text is a full restatement, so nothing in it records which version of the
dependency it was written against. The mechanical sign that the dependency
has moved on is a replacement the stacked change missed. The check compares
three texts of the requirement: an earlier one from the history of the
dependency's delta, the dependency's current one, and the stacked change's.
A sentence of the stacked text is drift when the earlier text had it, the
current text has dropped it, and the current text has also gained a
sentence the stacked text lacks.

A sentence the dependency only dropped is not drift. A stack is often made
by moving a rule out of the dependency into the stacked change, so that
sentence is in the dependency's history and now belongs to the stacked
change. The check reads at most the fifty latest commits that touched the
delta, which bounds the work on a long-lived branch; drift against an older
text is not reported.

**A hint between declaring and guessing.** Without the line, a duplicate
against a main requirement that an open pull request removes or renames
ends with the exact line to add. It stays an error until the line is added:
the hint guesses, as the rejected inference below would, and only the
author knows whether the change builds on that pull request. The lookup is
one `gh pr list` and at most twenty file reads per run. Without `gh`, or
when GitHub cannot be reached, the hint is left out and the plain error
stands.

**Rejected:**
- **A repository-wide order file.** igor already keeps the archive order in
  an issue, #204, and a second copy would drift from it. It would also make a
  change's checks depend on a file outside the change.
- **Inferring the stack from open pull requests**, with no declaration. It
  guesses: two open changes may retire the same requirement, and a change
  may duplicate a rule by mistake while another pull request happens to
  remove it. Inference survives only as the hint.
- **Deciding "archived" from the archive directory's name.** Three rules
  were tried that combined the name with something else: the pull request's
  state, then also whether the change was still open in the tree. Each
  misread a state that bug-hunter then found. An open pull request beside an
  older archive of the same name read as archived; so did a merged change
  not yet archived; so did a stacked branch cut before the merge, whose tree
  never holds the dependency's open change. Only the proposal's text
  identifies the change.

---

## Undefined terms are left to the consistency read

**Decision** (Adam, 2026-10-15). The script does not look for undefined
terms. The consistency read does (checklist item 5: "A term used before it
is defined, or defined nowhere"), whether or not the writer set the term in
bold or backticks.

**Why.** A program cannot tell a term from any other word unless the writer
marks it, and OpenSpec has no way to mark a defined term. The rejected check
below used bold and backticks as the mark, but writers use them for other
things. In igor, the repository whose specs this skill was built from (see
*Why the skill exists*), bold marks almost only WHEN, THEN and AND, and
backticks mark code and config names. So most of what the check read was not
a term: it had to skip those keywords, and guess which backticked words were
code. And it never saw the unmarked new terms, which are the ones a writer
assumes everyone knows.

**Rejected:** a check that took each backticked or bold term in a
requirement and reported the term when it appeared nowhere in the specs or
the change's proposal or design. It is worth reconsidering only if OpenSpec
gains a way to mark a defined term.

---

## The consistency read is a fresh subagent

**Decision.** A subagent that did not write the change does the read, from a
fixed brief. The author does it only where no subagent can be started, and
the trailer says so (`read by its author, no subagent`).

**Why.** An agent cannot judge its own spec cold: it reads what it meant, not
what it wrote. In the run above, the 44 amendments came from fresh readers
cross-checking changes their authors had submitted as finished.

**The brief is fixed** and the author adds no summary. A summary is the
author's reading of the change, which is the reading under test.

**`--json title,body,comments`, never `--comments`.** `gh issue view N
--comments` and `gh pr view N --comments` print only the comments, with no
title or body, when output is not a terminal, which is how an agent runs
them. A reader using them sees the discussion and misses the decision.

---

## Findings go into the spec, not into comments

**Decision.** A finding is fixed by amending the spec. A question only a
person can decide goes into the proposal's decisions section as an open
question. A conflict with another change or pull request is reported, not
edited.

**Why.** The spec is what `openspec validate` checks, what an implementer
builds from, and what a reviewer approves. `gh pr view` shows the body
without the comments, so a decision left in a comment is invisible to the
default read, and the change looks reviewable when it is not.

**Rejected:** editing another change to resolve a conflict. That change has
its own author and reviewer, and an edit from outside lands in a review
nobody is doing.

---

## Proposals open with their decisions

**Decision.** A proposal opens with the decisions the reviewer is asked to
make; then what is still open; then everything else. In a repository that
enforces this rule, the script fails a proposal whose first section is not a
decisions section, or whose decisions section lists no decisions, and the
agent puts the rule in `openspec/config.yaml`. OpenSpec prints config rules
to the agent drafting a proposal (verified with OpenSpec 1.6.0: they appear
inside `<rules>` in `openspec instructions proposal`).

**Why.** At the spec stage, the reviewer's job is the decisions.

**Rejected:** a decisions section anywhere in the proposal. OpenSpec's own
template opens with "Why", and a reviewer reads in order.

**A decision names a rejected alternative only when it has one** (Adam,
2026-10-14). Where a real alternative was considered and turned down, the
decision says what it was and why. Nothing checks for one. Not every
decision has a real alternative. Requiring one invites weak ones written to
fill the slot, which add to the reader's work.

**Rejected:** requiring every decision to name a rejected alternative, which
the script once checked by searching each decision for the word "reject". A
search like that cannot judge a decision anyway: it finds the word, not a
real alternative.

---

## Each repository's decisions-first answer lives in spec-check's own file

**Decision (Adam, 2026-10-14).** Each repository decides whether its
proposals must open with their decisions, and `openspec/spec-check.yaml`
records the answer in one line: `decisions-first: enforce` or
`decisions-first: off`. With no file, the repository has not decided. Only
`setup` writes the file: `setup` writes `enforce`, `setup --decline` writes
`off`.

`check` and `sign` read the file from where they read the change: the
working tree, the `--ref` branch, or the staged files. From a git tree they
read it with git and never follow a link. With `enforce`, a proposal that
does not open with its decisions is an error. With `off`, it is not checked.
Undecided, no proposal is checked, and the run adds one finding of severity
`check` saying how to enforce or turn off the rule. A file that holds
anything else, or a link, directory or submodule in its place, gets one
`check` naming the problem, and decisions-first is not checked. `check
--json` reports the state as `decisions_first`.

**Why its own file.** Recording a decision should not depend on reading or
writing a file OpenSpec owns. When the decision was kept as marker comments
in `openspec/config.yaml`, telling the states apart meant parsing a file teams
edit by hand, and each round of bug-hunting found another layout it misread:
a commented-out rule, a rewording below a comment, a `config.yml`. Reading it
from a git tree for `sign` meant resolving links by hand, through symlinks
and into submodules, and each of those found another case too. A file only
`setup` writes, holding one of two lines, has no such cases. Anything else in
it is reported, never guessed at.

**Why the check follows the decision.** A team that turned the rule off chose
not to follow it, and failing their proposals for it would overrule that
choice. An undecided repository has not chosen either; failing its proposals
would decide for it, and saying nothing would leave it undecided for good. A
`check` never fails a run, so the question is raised without stopping work.

**Why in the repository.** Installing a skill happens once per machine; the
decision belongs to the repository. Committed there, it is shared: every
agent on the team reads it, and none asks again.

**The script never edits OpenSpec's config.** Editing a file it does not
own, as text, in YAML it cannot parse, caused most of the bugs found while
building this: a rule appended after a document end, a second `rules:` key
that makes OpenSpec ignore the whole file, a write that failed half way, a
config that was a link. The agent's own edit tools follow links and
understand YAML. So when the user chooses to enforce the rule, the agent adds
it to `openspec/config.yaml` (or `config.yml`), under the existing `rules:`
→ `proposal:`, and shows the user the change. On a decline, it looks for the
rule and asks before removing it. SKILL.md, "Setting up a repository", says
how.

**The rule in OpenSpec's config is best-effort.** It only helps the agent
drafting a proposal; `check` enforces the rule from `spec-check.yaml` either
way. Where the agent cannot edit the config, it gives the user the lines and
says adding them is optional.

**Rejected:**
- **Marker comments in `openspec/config.yaml` as the record**, read back to
  decide the state. That is the design above that kept misreading layouts.
- **The script editing OpenSpec's config as text.** See above.
- **Following links to read OpenSpec's config from a git tree**, the way the
  file system would, while the answer was kept there. Each kind of link (out of `openspec/`, into a submodule, out
  of a submodule) needed its own resolution code and turned up the next case.
- **Asking at install time.** The installer cannot know which repositories a
  person will work in, and an answer kept on one machine leaves every
  teammate's agent asking again.

---

## The proposal hook asks before a proposal is finished

**Decision.** Besides the commit hook, a proposal hook runs after the agent
writes or edits a file:
`PostToolUse` on `Write`, `Edit` and `MultiEdit` in Claude Code, and
`postToolUse` on `Write` in Cursor. If the file is
`openspec/changes/<name>/proposal.md`, at any depth, inside a git repository
whose top has an `openspec/` but no `openspec/spec-check.yaml`, the hook tells
the agent to ask the user whether to enforce or turn off the rule, giving
both commands for the repository top. Otherwise it prints nothing. It never
blocks, and any error means silence.

A proposal under a nested `openspec/` is judged by the top's decision,
because `check`, `sign` and the commit hook read only the top's `openspec/`.
A decision recorded beside a nested one would be read by nothing.

**Why.** The moment to settle the rule is while a proposal is being drafted,
before anyone reviews it. A hook fires at that moment every time.

**Rejected:**
- **Relying on the skill's description alone.** The description says to use
  the skill when drafting a change, but a model decides by judgement whether
  to load a skill, so the description alone does not reliably fire.
- **A session-start hook.** It would fire in every session, in every
  repository, whether or not anyone is writing a proposal.

**In Cursor, `postToolUse` on `Write`, not `afterFileEdit`** (Adam,
2026-10-14). Cursor's documentation gives `postToolUse` an
`additional_context` output, which reaches the agent, and gives
`afterFileEdit` no output at all. It does not document the Write tool's
input, so the hook reads the path from `file_path`, `path` or `target_file`.
The hook has not been tried in Cursor itself.

---

## TLA+ is guidance, not automation

**Decision.** The skill says when a requirement gets a TLA+ model and how it
maps to requirements and CI. It does not write models.

**Why.** Only requirements about concurrency, ordering, crashes between
writes or protocols between processes get a model. A model is worth only as
much as its correspondence to the spec, and choosing what to abstract is the
design work itself. A generated model would check whatever the generator
understood.

---

## The trailer is bound to the tree

**Decision.** `sign` runs the mechanical checks on the staged tree and prints
`Spec-check: ✓ <tree> <summary>`. The commit script runs `verify-staged.sh`
before committing, and the commit hook runs `verify-commit` after. Both
compare the value's tree with the tree that lands. A value starting `skipped` binds
nothing.

**Why.** A trailer typed from memory can look right. One bound to the tree
proves the checks ran on what landed, and an edit staged after signing breaks
it. This is the commit-trailer library's design
([its DECISIONS.md](../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent)).

**The value carries the binding** (`--verified-value`), rather than a separate
`Spec-check-Tree:` line (`--minted`). bug-hunter's commit script forwards
`--verified-value` families unchanged, so Bug-hunter, Prose and Spec-check
land on one commit through one call, with no change to bug-hunter.

**The signing refuses on errors.** A `✓` over a change with errors would read
as passed. Work in progress commits with a skip note.

**Rejected:** binding the message too, as prose does. The checks read the
spec, not the commit message.

---

## Only commits that change `openspec/` are judged

**Decision.** The commit hook sets the library's `COMMIT_TRAILER_PATHSPEC` to
`:(top)openspec/`. A commit that changes nothing there is never judged, with
or without a trailer.

**Why.** A code-only commit has nothing to check, and a report on it would
teach readers to ignore the report.

**Rejected:**
- **Filtering inside this skill's report.** The library has already decided
  to report by then, and an empty report falls back to the library's
  generic one.
- **A callback the library calls per commit.** A pathspec is data, so it
  needs none of the subshell and marker machinery a sourced callback does.

**Limit:** only `openspec/` at the repository root counts, which is where
OpenSpec puts it.

---

## The hooks are enabled by default

**Decision.** `hook.json` says `"default": "enabled"`, for both hooks: the
commit hook and the proposal hook. A skill's hooks are switched on and off
together.

**Why.** Several organizations install from this repository, each with its
own repositories, so the default must suit a repository that uses OpenSpec and
one that does not:
- Installing spec-check is itself the opt-in. Nobody gets either hook without
  asking for the skill.
- In a repository without OpenSpec, neither hook speaks. The commit hook
  judges only commits that change `openspec/`. The proposal hook speaks only
  after a proposal is written, and only until the repository decides.
- Neither blocks.
- Off by default, an installed spec-check would leave the spec stage
  unchecked, and nothing would say so.

**Rejected:** off by default. It suits a hook that reports on every commit,
which neither of these does.
