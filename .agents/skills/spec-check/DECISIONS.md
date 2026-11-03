# spec-check — decisions

`spec-check` does the part of spec review that needs every other spec in
mind, so the person reviewing judges only whether the rules are right. It
serves the spec stage of review: a change's specification is reviewed and
approved before any code for it is written, and that review is where a
reviewer's time goes. It has two parts: a script, `scripts/spec_check.py`,
and a consistency read done by a fresh subagent. The script's `check`
subcommand runs the mechanical checks, and `sign` runs them on the staged tree
and prints the commit trailer.
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
citations can be decided by a program. A script alone would pass the
specs that needed the most work. Beyond those kinds, the script also runs
`openspec archive` on the change, to catch what OpenSpec would refuse at
archive time (see *Every change is archived into a scratch copy*).

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

**Rejected:**
- An allowlist of file extensions deciding which bare names are files. Each
  version of the list had a gap the next pass found. A list of host
  suffixes survives only to skip addresses such as `example.com:443`, which
  are never files.
- Treating every citation as a check. That would drop the error for a
  citation copied from another branch, whose line no longer exists here.

---

## Document-evolution text is an error

**Decision.** `check` gives an `evolution` error on each line of a checked
change's files that records how the change got to its shape rather than what
holds now:
- an amendment: "amending decision 79", "superseded by decision 12";
- a credit naming who decided or when: "(Adam, 2026-10-21)", "Adam decided",
  "decided by Adam", "decisions 21 and 22 on 2026-10-20";
- "previously" or "originally", an earlier draft, the next revision;
- a review round: "this push", "since review", "the second consistency read".

The finding quotes the line. Text in a code fence, a code span or double
quotes is skipped, since a spec about a checker quotes what it checks for.
Every line of a change's files is read, not only the lines a branch
changed. The specs under `openspec/specs` are not read: they are the
archived result of earlier changes, which no author is reviewing now.

**A person keeps a false `evolution` error.** `sign --kept <file>` takes one
line per finding, `<path>:<line> kept (asked): <reason>`. The agent writes a
line only after a person chose "Keep as is" in a question the agent asked
through its host's interactive picker (in Claude Code, `AskUserQuestion`). A kept finding no longer fails the
run, the spec text stays as written, and the trailer counts the kept lines
(`1 evolution kept`), so the override shows in git. `sign` refuses the file
when a line names no current `evolution` error, names one twice, has no
reason, or lacks `(asked)`. An agent that cannot ask, such as a subagent,
writes the line without `(asked)`. `sign` then refuses and names each such
line, and the agent passes that message to whoever started it, who asks the
person. The prose skill keeps a cold reader's finding the same way, with
the same `kept (asked)` line. The script cannot check that a person
answered: `(asked)` is the agent's statement.

**Limits.** Each line is read on its own, so a code span wrapped across two
lines reads as prose, and its second line can draw a false error. An
indented code block also reads as prose, as it does for every other check
that reads lines through `markdown_lines`.

**Why an error.** A finding of `check` severity never fails the run, so it
asks whoever runs spec-check to judge it. History is never worth keeping in
a change: it should simply be removed before a person reviews the change. An error makes the agent remove
it, and only a person can let a line through.

Behaviour uses the same words: a newer file supersedes an older one, a
candidate previously rejected is not proposed again, the agent decided. So
most patterns fire only beside a decision, a person, a date, or a word
naming the document's own drafts or review rounds ("an earlier draft",
"this push"). The bare "previously" and "originally" fire alone, unless a
determiner precedes them ("a previously rejected rule"). The patterns were
measured on two kinds of text:
- About 25,000 lines of open changes: the `inquisitor` change in this
  repository's pull request #25; in
  the igor repository (adamstallard/igor), the six changes open on its main
  branch and the changes in four of its spec pull requests. The patterns
  flagged 292 lines, of which 2 were not history.
- igor's 5,000 lines of main specs, which describe settled behaviour and so
  show how often behaviour text is flagged. The patterns flagged 1 line
  there, and it was history.

So a false error is rare, and the override covers it.

**Why its own patterns, not prose's.** prose's history patterns, in its
`comment_scan.py`, catch a code comment narrating the code's past: "the old
implementation", "we refactored". A change's history is about decisions,
people, dates and review rounds, and none of prose's patterns covers those.
The three that carry over ("previously", "originally", an earlier draft) are
adapted here. So is prose's veto: no hit when a word such as "a" or "the"
sits right before "previously", as in "a previously rejected rule". spec-check
uses only the standard library and installs without prose, so it cannot
import them.

**Rejected:**
- **A warning.** It asks whoever runs the check to review each line, when
  the line should just be fixed.
- **Rewording a false positive until the pattern misses it.** The words were
  right; rewording them to suit a regex makes the spec worse and hides that
  a person was needed. The override keeps the text and records the person's
  call.
- **The bare words**: `supersedes`, `replaces`, `reversed`, `was changed`,
  `no longer`. In the `inquisitor` change's specs they describe behaviour on
  31 lines, and each of those would fire.
- **A list of people's names.** A credit is found as a capitalised word before
  a decision verb ("Adam decided"), excluding pronouns, determiners and
  headings, so it works in any repository.

---

## A stacked change declares what it builds on

**Decision (Adam, 2026-10-21; on 2026-10-24: the severities, reading an
open dependency's presence from the specs' content, the real `openspec
archive`, judging merged dependencies without replaying them, and archiving
the stacked change itself).** A change that applies
on top of another open change says so in its `proposal.md`, one line per
dependency, right after the title:

```markdown
Builds on: seat-files (adamstallard/igor#171)
```

The syntax is exactly `Builds on: <change> (<owner>/<repo>#<number>)`, alone
on its line. Several lines list a chain in the order it applies to main.
`check` and `sign` then read each dependency's change from its pull
request's branch. They copy the checked tree's `openspec/specs` and
OpenSpec's config files, never `changes/`, into a temporary directory. Then,
in the listed order, they take each open dependency, drop the delta items
that the copy already shows, and archive the rest into the copy with one run
of the real `openspec archive <change> --yes --no-validate`. A merged
dependency is never archived: it is looked for in the tree by requirement
name (see
*A merged dependency is judged, never replayed*). Every check on the
stacked change then runs against the specs in the copy (see *Why the real
`openspec archive`*). Because the archive runs the OpenSpec CLI, the CLI is
required: a change with a `Builds on:` line, checked where `openspec` is not
on PATH, gets a blocking `stack` error, never a pass.

A declaration brings two more kinds of finding:
- `stack`, about the dependencies. It is an error for:
  - a line that cannot be read, or a change that names itself;
  - a dependency that cannot be read, or a pull request that holds no
    change of the declared name;
  - deltas `openspec archive` refuses (the error quotes the CLI's message
    and names the dependency);
  - a merged dependency whose result the tree does not show;
  - a delta with text but no requirement header the script can read, so
    that no dependency is left out silently;
  - a missing OpenSpec CLI.

  When the combined state cannot be built, the duplicate and drift checks
  do not run for the change, and the error says so. The other checks, such
  as `no-scenario` and `citation`, do not depend on it and still run. A
  dependency whose deltas are all already in the tree, or a merged one
  whose result shows there, gets a non-blocking check instead, telling the
  author to remove the line. An open one whose deltas are partly there gets
  a check naming each delta.
- `drift`, about the stacked change. It is an error when the stacked change
  modifies, removes or renames a requirement that main plus its
  dependencies no longer define, or when `openspec archive` refuses the
  stacked change itself on top of them. It is a non-blocking check, quoting
  both texts, when a modified requirement keeps a sentence the dependency
  has since replaced, or when the tree already holds a requirement a
  dependency adds, with another text (see *Why sentence drift is a check*).

**Whether the specs hold an open dependency is read from its content.**
For a dependency whose pull request is open or closed without merging, the
only question is which of its deltas the specs so far (the tree plus the
open dependencies listed before it) already show, and the specs answer it
directly. Each delta item, read from its pull request's branch, is
compared with them, and only what is not already there is archived:
- **ADDED:** already there when the specs have that requirement with that
  text. With another text, it is dropped and the tree's text kept, with a
  non-blocking drift check quoting both.
- **REMOVED:** already there when the requirement is absent.
- **RENAMED:** one delta's renames are read in order, as OpenSpec applies
  them, and are kept unless that reading shows every pair already done.
  When every rename applies in turn, each from a name that is there to one
  that is not, they are not done. A swap through a temporary name (X to T,
  Y to X, T to Y) applies that way to the specs as they stand before the
  swap, though X and Y are both there before and after. Otherwise the renames are done when the
  names they end on are there and the names they leave behind are absent,
  so a chain (X to Y, then Y to Z) is done when the specs show Z alone.
  Kept renames move their names before the other items are read, as the
  archive applies renames first.
- **MODIFIED:** already there when the specs' text is the dependency's.
  Otherwise it is kept and archived (see *A modified requirement is
  decided by its pull request's state*).

Each open dependency then ends in one of three states:
- every delta already there and none the tree holds with another text: a
  check that the `Builds on:` line is stale;
- none there: all archived;
- some there and some not: the missing ones archived, and a check naming
  each delta and which state it is in.

Names match exactly, as OpenSpec matches them, so a rename that only
changes case is read as one, in the drift check, the duplicate check's
exemptions and the hints too. "The same text" means the whole block below
the header, as OpenSpec replaces it, subsections and case included; only
line endings and blank space around lines are ignored. A requirement block's
header matches in any case, as OpenSpec's `/^###\s*Requirement:/i` does, in
specs and in deltas alike. A reader that took only `### Requirement:` would
drop a dependency written with `### requirement:` from the stack, silently.
The bullet forms, a REMOVED bullet and a rename's FROM and TO lines, match
with their case, as OpenSpec matches them.

`openspec archive` refuses what does not fit: a requirement modified or
removed that is not there, a rename whose old name is missing or whose new
name is taken. Each refusal is a blocking `stack` error that quotes the
CLI and names the dependency.

**The stacked change itself is archived too,** after its open dependencies,
into a second copy of the temporary specs, as every change is (see *Every
change is archived into a scratch copy*). Its refusals are `archive` errors,
like any change's. This second copy is used only for the refusals: the
duplicate and drift checks still read the specs before the stacked change is
applied. A refusal is left out only when a drift error already sits on its
line, so a requirement is not reported twice; an error of any other kind on
that line does not hide it. A refusal saying a capability has no spec names
no requirement, so it is placed at the first rename or modification in that
capability's delta. The drift check reports an error on that line too, so the
refusal is not repeated there.

A dependency's own proposal may build on a change that the stacked change
does not list before it. If that change's pull request cannot be read, it
is an error. A merged one must show in the tree, by the rules for merged
dependencies below, or it is an error saying to merge main. An open or
closed one must already be held, by content, in the specs so far, with
nothing of it left to archive; otherwise it is an error saying to list it
before the dependency. Without these, the stack would leave out what the
dependency rests on, and a duplicate of it would pass.

**A merged dependency is judged, never replayed** (Adam, 2026-10-24). A
dependency whose pull request has merged is never archived into the
temporary specs, and no later dependency is taken back out to judge it. Its
result is already in main, so the only question is whether the branch
being checked holds it, and that is read from the tree's requirements by
name:
- each requirement it adds or modifies is there by name, with any text,
  since main may have reworded it since (Adam's decision, 2026-10-24);
- each requirement it removes is absent;
- its renames, read in order, are done: the names they end on are there and
  the names they leave behind are absent.

A later merged dependency, one listed after this one or building on it, may
have changed those names since. A name the later one removes or renames
away need not be there (Adam's decision, 2026-10-24), and a name it adds or
renames onto need not be absent, so a fully merged stack passes whichever
of its dependencies are listed. When the tree shows all of a merged
dependency's result, the dependency gets a non-blocking check that its
`Builds on:` line is stale. When any of it is missing, it is a blocking
error that names what is missing and says the branch does not hold the
merged dependency's result: merge main into the branch.

The one exception is a dependency merged into main but not yet archived
there: when the tree still holds its change open with the same deltas, the
archive that updates the specs is still to come, so it is handled as an
open one and archived. igor merges a change and archives it later, in the
order its issue #204 sets, so without this exception every change stacked
on it would fail in between.

**A modified requirement is decided by its pull request's state.** When
the tree's text of a requirement a dependency modifies differs from the
dependency's, one fact settles it: whether the dependency's pull request
has merged, from one `gh pr view <n> --json state`.
- **Open, or closed without merging:** the difference is expected, since
  the dependency has not reached main. Its text is archived into the
  checked state, quietly. A closed pull request also gets its own
  non-blocking check.
- **Merged:** the requirement only has to be there by name. Main may have
  reworded it since, and Adam accepts that the author then gets only the
  stale-line check.

An open dependency listed later may replace text that an earlier one put
in, without building on the earlier one, directly or through another
listed dependency. The earlier text would then be left out with nothing to
show it, so it gets a non-blocking check. The check compares texts, not
names: after each archive run, any text an earlier dependency archived that
no longer appears in that capability is reported.

**Why the real `openspec archive`, and only for open dependencies**
(Adam, 2026-10-24). The first design replayed OpenSpec's archive by hand,
in memory: renames, then removals, modifications and additions. Every
bug-hunter iteration over it found another sequence it misread: a rename
chain in one delta, a shift (Y to Z, then X to Y), a removal undone by a
later re-add, a rename onto a name an earlier dependency removed. Each fix
added a rule, and the rules were a second, partial definition of what
OpenSpec does. The CLI is the definition, so open dependencies are
archived with it, once each, and its refusals are the errors.

Merged dependencies went the same way. To judge an earlier dependency
against the specs as they stood before a later merged one, the script
took the later one back out by hand, reversing its renames, additions and
removals, and decided whether a later dependency set a requirement again
by replaying the later ones with and without it. That was a hand-written
reversal of the archive, and the next bug-hunter run found nine more
problems in it, mostly from those two pieces: a merged stack listed in
part failing, a swap read as done, the CLI run many times per dependency.
A merged dependency's result is already in main, so there is nothing to
replay: the branch either holds it or is behind main, and the content of
the tree says which. Both pieces were removed.

The content rules above still decide what an open dependency adds that the
specs already hold, since only what is not there is archived. The cost is
a requirement: the OpenSpec CLI must be on PATH wherever a stacked change
is checked. A run without it is an error, not a silent pass, since a
stacked change checked against main alone reports false duplicates and
misses real ones.

The tree's specs, the dependencies' deltas and the stacked change's own
delta are all read with `openspec show --json` (see *spec-check reads
OpenSpec only through its CLI*), so a requirement's name and text are what
OpenSpec reads. Two versions of a requirement are the same when OpenSpec
reads the same text and scenarios from both and their fenced code matches,
since `show` leaves fenced code out and the archive writes it.

When none of a capability's delta items is dropped as already there, the
archive gets the dependency's delta file for it verbatim. Otherwise the
archive gets a delta rebuilt from the kept items. Each item is written as
the dependency's delta file writes it: its lines from its header to the next
requirement header or section (see *A finding's line is a text search*).

**Why the pull request's state, and not the text it was written against.**
The design before this one inferred, for every differing modification,
which text the dependency had replaced. It rebuilt that base from the
dependency's branch, the changes it builds on and their archives, and
called anything else a third version. Every bug-hunter run over it found
new states it misread (a reverted rewording, an unrelated open change, a
rename-only dependency, a stale copy), and two let a real duplicate pass.
The pull request's state is one fact GitHub reports reliably. A merged
dependency whose result the branch lacks means the stacked change rests on
something the branch does not hold yet. That is an error, because a
non-blocking warning would bury it among routine checks. A merged
dependency whose text main has reworded since is not an error: the
requirement is there, main's text is the one to build on, and the
stale-line check tells the author so.

The pull request must still hold the change: its file list must touch
`openspec/changes/<change>/`, or an archive directory of it that the pull
request itself adds, and then the deltas are read from there. `gh pr view`
lists only a pull request's first 100 files. When a list of 100 files shows
neither, the list is read in full from GitHub's files API. If that cannot
be read, or stops at the API's limit of 3,000 files without showing the
change, the `Builds on:` line is an error.

**Why content and not history.** The earlier designs asked whether a
dependency had been archived. They read it from archive directories, then
from merge commits and archive events in git history. Three bug-hunter runs
each found about seven git states the rule misread:
- reverts of a merge or of an archive;
- a change name reused after its archive;
- squash merges, and merges still in progress;
- a pull request merged into another pull request's branch;
- a stale local base ref;
- file lists cut short, or listing deleted files.

Two of them let a real problem pass `sign`. Whether a dependency was
archived was never the question; whether the tree holds its result was,
and the content answers that whatever path the history took.

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

**Why sentence drift is a check.** A requirement the stacked change edits
that its dependencies no longer define is certain to be wrong, so it stays
an error. A kept sentence is not: the rule below cannot tell a sentence the
author missed from one the author chose to keep while dropping the
dependency's new one. So it is a check that never fails the run, and it
shows the kept sentence beside the dependency's new ones for the author to
judge.

**Why drift reads the dependency's history.** The stacked change's MODIFIED
text is a full restatement, so nothing in it records which version of the
dependency it was written against. The mechanical sign that the dependency
has moved on is a replacement the stacked change missed. The check compares
three texts of the requirement: an earlier one from the history of the
dependency's delta, the dependency's current one, and the stacked change's.
A sentence of the stacked text is reported when the earlier text had it,
the current text has dropped it, and the current text has also gained a
sentence the stacked text lacks.

A sentence the dependency only dropped is not reported. A stack is often made
by moving a rule out of the dependency into the stacked change, so that
sentence is in the dependency's history and now belongs to the stacked
change. The check reads at most the fifty latest commits that touched the
delta, which bounds the work on a long-lived branch; a sentence kept from an
older text is not reported.

**A hint between declaring and guessing.** Without the line, a duplicate
against a main requirement that an open pull request removes or renames
ends with the exact line to add. It stays an error until the line is added:
the hint guesses, as the rejected inference below would, and only the
author knows whether the change builds on that pull request. The lookup is
one `gh pr list` and at most twenty file reads per run. Without `gh`, or
when GitHub cannot be reached, the hint is left out and the plain error
stands.

**Left for a later spec-check change.** Three gaps remain in the checks
that run on every change, outside what archiving a stacked change covers:
- a requirement block holding a `###` subheading that is not a requirement
  header gets a false `no-scenario` error;
- a change with no `Builds on:` line that ADDs a name main already has is
  not reported;
- the duplicate check's same-name exemption holds across capabilities, so
  the same requirement name in two capabilities excuses a duplicate.

**Rejected:**
- **A repository-wide order file.** igor already keeps the archive order in
  an issue, #204, and a second copy would drift from it. It would also make a
  change's checks depend on a file outside the change.
- **Inferring the stack from open pull requests**, with no declaration. It
  guesses: two open changes may retire the same requirement, and a change
  may duplicate a rule by mistake while another pull request happens to
  remove it. Inference survives only as the hint.
- **Deciding "archived" from archive directories, or from git history.**
  Every such rule misread some state of the repository; see *Why content
  and not history*.
- **Replaying OpenSpec's archive by hand**, including taking a later
  merged dependency back out to judge an earlier one, and replaying later
  dependencies with and without an item to decide whether it was set
  again. See *Why the real `openspec archive`, and only for open
  dependencies*.
- **Archiving merged dependencies.** Their result is already in main; see
  *A merged dependency is judged, never replayed*.
- **Inferring the text a dependency's modification was written against.**
  See *Why the pull request's state, and not the text it was written
  against*.

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
person can decide goes into design.md's *Open Questions*. A conflict with another change or pull request is reported, not
edited.

**Why.** The spec is what `openspec validate` checks, what an implementer
builds from, and what a reviewer approves. `gh pr view` shows the body
without the comments, so a decision left in a comment is invisible to the
default read, and the change looks reviewable when it is not.

**Rejected:** editing another change to resolve a conflict. That change has
its own author and reviewer, and an edit from outside lands in a review
nobody is doing.

---

## Decisions live in design.md

**Decision.** A change states each decision once, as it stands now, in
design.md's *Decisions*, and each undecided item in its *Open Questions*,
both sections OpenSpec's instructions for design.md name. No record is kept
of how a decision was amended: git and pull request comments hold that.
The reviewer judges where a decision sits; the `check` command
gives an error on a line that records how one was amended
(*Document-evolution text is an error*).

**Why.** OpenSpec keeps a proposal to one or two pages of why and what, and
puts decisions and their rationale in design.md. Reviews of this repository's
changes read the specs first, then design.md, then proposal.md, so a review can fail fast on
the specs. A proposal that collects rulings grows without bound: one reached
275 KB by appending rulings and amendment notes.

**Rejected:**
- **Decisions first:** a proposal opening with a `## Decisions` list, checked
  by the script where a repository chose to enforce it in
  `openspec/spec-check.yaml`, with a `setup` command to record the choice and
  a proposal hook asking for it. It rested on a reviewer reading the proposal
  in order, which is not how reviews happen here, and it put decisions where
  OpenSpec does not.
- **Keeping an amendment history beside each decision.** It is what made the
  proposal above reach 275 KB, and git already keeps it.

---

## Every change is archived into a scratch copy

**Decision.** `check` copies the tree's specs into a temporary directory and
archives the checked change, and only that change, into the copy with the
real `openspec archive <change> --yes --no-validate`. Each refusal is an
`archive` error at the requirement it is about, quoting the CLI: an ADDED
requirement whose name is already there, a RENAMED onto a taken name, a
MODIFIED that drops a scenario the requirement holds, and a requirement
modified, removed or renamed that is not there. A refusal about a delta file
as a whole, such as two sections naming one requirement, is reported at line
0 of that file. Without OpenSpec 1.15.0 or later, the archive is reported
"not run", like every check that needs the CLI. The tree is never touched.

**Why.** Each of these passes `openspec validate`, which reads a change on
its own, and fails only when the change is archived, after review. The CLI
is the definition of what it refuses, as for stacked changes (see *Why the
real `openspec archive`*). Archiving only the
checked change keeps one open change's deltas from failing another's check:
which lands first is not known.

OpenSpec stops at its first refusal, so one run shows at most one.

`check` reads the archive's result from `archive --json`. It reads
`openspec --version` first and treats a CLI older than 1.15.0, or one whose
version it cannot read, as a missing one, naming the version to install. An
older CLI's errors, such as "unknown option '--json'", are never read as a
refusal of the change.

**Rejected:**
- **Archiving each capability separately.** It would show one refusal per
  capability, but still only one within a capability, where the requirements
  interact, and it costs a run per capability on every check.
- **An error without the CLI.** That is right for a stacked change, whose
  other checks are wrong without its dependencies. Here the other checks
  still hold, so "not run" says exactly what is missing.
- **Skipping the archive under spec-check's `--no-validate`.** That flag
  skips the whole `openspec validate --strict` run and nothing else. The
  archive is a check of its own, and only a missing CLI skips it. The
  `--no-validate` in the `openspec archive` command above is a different
  flag, OpenSpec's own: it stops `archive` running OpenSpec's validation
  before it applies the change. spec-check never passes its own flag through.

---

## A new capability's Purpose is checked in its delta

**Decision.** When a change creates a capability, its delta must carry a
`## Purpose` that `openspec archive` will write into the new spec, or
`check` reports a `purpose` error on that delta. A capability is new when
the specs the change is archived onto, main's or main plus its
dependencies, have no spec for it. Whether the Purpose is usable is asked of
the real CLI: the new capabilities' deltas are archived into an empty specs
directory, and the result is validated with `openspec validate --strict`.
The error follows OpenSpec: a missing, empty or placeholder Purpose, one
under 50 characters (OpenSpec's `MIN_PURPOSE_LENGTH`), or one archive
refuses as unreadable. A `## Purpose` in a delta for a capability that
already exists is a `purpose` check, since archive ignores it. The one
exception is a Purpose whose text, trimmed, is the spec's own: archive does
not warn about that one, and neither does `check`.

**Why.** Archive seeds a new spec's Purpose from the delta and nowhere
else. Without one it writes "TBD - created by archiving change <x>. Update
Purpose after archive.", and nobody goes back: adamstallard/igor, a repository built with OpenSpec,
had 11 specs stuck on it. Once archived, the placeholder is reported by `openspec validate
--strict` on the main spec, which fires on every change in the repository
and names none of them. In the delta, the finding lands on the one change
that causes it, while its author is still writing it.

Whether there is an error is decided by the CLI alone: archive writes the
new spec's Purpose, and `validate --strict` judges it. So the rule errors
exactly where the spec archive would write fails strict validation.
`delta_purpose` is a port of OpenSpec's `extractPurposeSection` and its
fence mask, written with JavaScript's character classes. It decides only what the CLI does not say:
the line a finding sits on, which reason the error gives, and whether an
existing capability's Purpose differs from the delta's. If the port drifts
from OpenSpec, a message gives the wrong reason or a check is wrong; no
error changes.

**Rejected:**
- **Checking the main specs for the placeholder.** That is what `validate
  --strict` already does, after the damage, and on every change.
- **Reading the existing-capability check from archive's own warning.**
  Archive warns only when the spec has a Purpose that differs, and only when
  the whole change applies: a capability whose spec has no Purpose, or a
  refusal on another capability, would lose a true check.
- **Finding the Purpose with `markdown_lines`**, spec-check's CommonMark
  line reader. OpenSpec closes a fence at any indentation; CommonMark ends
  a fence opened in a list item when the item ends. For a fence in a list
  item closed at column 0, CommonMark then reads the rest of the file as
  fenced, so each Purpose would run on into its requirements, and two equal
  Purposes would compare as different.

---

## A same-name pair is exempt only as a modification

**Decision.** `check_duplicates` skips a pair of requirements sharing a
sentence only when they have the same name and one of them is a MODIFIED
requirement in the same capability as the other. Text under a REMOVED
requirement is never compared: the change deletes it, so it states no rule.
A change that moves a requirement to another capability, quoting the old
text in its removal, passes.

**Why.** A MODIFIED requirement restates the one it modifies, so its
sentences are expected to repeat. Skipping every same-name pair let an ADDED
requirement, or one in another capability, repeat a rule word for word under
the same name and pass.

---

## spec-check reads OpenSpec only through its CLI

**Decision.** spec-check reads specs and deltas only through the public
commands of the OpenSpec CLI, 1.15.0 or later:

- `openspec show --json` gives each requirement's name, text and scenarios:
  `--type spec` for a main spec, `--deltas-only` for a change. A change's
  deltas are read beside a stub proposal in an empty directory, since `show`
  refuses a change whose own proposal lacks "Why" or "What Changes".
- `openspec validate --strict --json` reports what a delta drops or
  misfiles, and spec-check relays each issue with OpenSpec's own line and
  message: a misspelt section title, a requirement above the first `##` or
  under another section, a section or text above the first `##` that the
  archive does not carry, and a `###` heading that is not a requirement
  header.
- `openspec archive --json`, into a scratch copy, says whether a change
  applies, alone or on top of what it builds on.

`show --json` gives no line numbers, so a finding's line comes from a plain
text search for the names `show` gives (see *A finding's line is a text
search*). What a delta holds is decided by `show` alone.

Each relayed issue keeps OpenSpec's level. Under `--strict` an ERROR or a
WARNING fails validation, so it is an error. An INFO note, such as the one on
a stray heading, never fails it, so it is a check, and the advice spec-check
adds to it does not change that.

Below 1.15.0, or with no CLI, every check that needs a requirement reports
`not run: install OpenSpec 1.15.0 or later`: the scenario, duplicate and
drift checks, the archive and validation. A stacked change gets a `stack`
error, since its other checks are wrong without its dependencies. The checks
that read no requirement still run: citations, `Builds on:` lines and the
RENAMED scan below.

spec-check adds to OpenSpec's output in two places only:

- **Advice on a stray heading.** OpenSpec notes a `###` heading in a delta
  that is not a requirement header and ignores it, while the archive keeps it
  inside the requirement above, where a later change to that requirement
  replaces or removes it. spec-check adds where the rule goes. A MODIFIED
  `### Requirement:` must name a requirement the specs have, and an ADDED
  one a requirement they lack, or the archive refuses it. So the advice is
  to restate the rule under MODIFIED when the specs the change is checked
  against (main, plus any dependencies) already have its title, and to move
  it to ADDED when they do not. When a stacked change's dependencies could
  not be read, it gives both, with the condition.
- **A requirement written out under `## RENAMED Requirements`.** OpenSpec
  reads only FROM and TO lines there, so the archive renames the
  requirement, keeps the specs' text, and drops the text written there.
  Neither `show` nor `validate` says so. A line scan finds it: each `###`
  heading in that section, outside a code fence, with anything under it
  besides FROM and TO lines is a `renamed-block` error. A heading over only
  FROM and TO lines is a rename written under a heading, and passes. The fix
  is to restate the requirement under `## MODIFIED Requirements` with its
  new name.

**Why.**

- **Hand-written readers drifted.** spec-check carried a port of OpenSpec
  1.6.0's delta reader, and walkers of its own for sections, fences and
  stray headings. Each round of review found another place where they read
  a delta differently from OpenSpec, or from each other. Meanwhile OpenSpec
  1.14 and 1.15 changed what it reads: when a delta has two sections with
  the same title, such as two `## ADDED Requirements`, both are now
  applied, and `## ` lines inside a fence no longer split a delta. Every
  finding the walkers made about those cases became wrong.
- **A fallback runs exactly where nothing checks it.** A reader kept for
  CLIs too old to ask would run only on machines whose OpenSpec nobody
  tests against.
- **OpenSpec now says it itself.** From 1.14.0 `show --json` names
  requirements and scenarios, and from 1.15.0 `validate` reports, with
  lines, each section and text the archive does not carry.

**Rejected:**

- **Importing OpenSpec's parsers.** They sit outside the package's
  `exports`, which list only its entry point, so any release may move or
  change them.
- **1.14.0 as the minimum.** Its `validate` reports a requirement under a
  section it does not read, but not a section or preamble of plain text that
  the archive drops. Only 1.15.0 reports both.
- **Keeping spec-check's own section and fence findings beside OpenSpec's.**
  Where OpenSpec reports a case, its report is the definition; a second
  report of it would only disagree with it.

**Where it stops.** These are gaps OpenSpec leaves and no narrow line scan
can find, so spec-check reports nothing more for them:

- **Text under a `###` heading that is not a requirement header.** `openspec
  show` ends the requirement's text at the heading, while the archive keeps
  the heading and what follows inside the requirement. So the scenario,
  duplicate and drift checks do not see that text, and a dependency that
  changes only that text reads as already in the tree. OpenSpec's note on
  the heading, with spec-check's advice, is the only finding.
- **A header with no space after its hashes.** `show` reads `###Requirement:`
  as a header in a delta but not in a main spec, and the archive copies the
  header into the spec as written. So once a dependency's such requirement
  is archived into the scratch specs, spec-check no longer sees it there,
  and a stacked change that modifies it gets a `drift` error saying no one
  defines it.
- **A section or requirement written inside a code fence.** OpenSpec 1.15.0
  reads every fenced line as text, in `show`, `validate` and the archive, so
  a `## ` line or `### Requirement:` header inside a fence is never a
  section or a header. If an author fences one by mistake, nothing reports
  it: spec-check reads fenced lines as OpenSpec does.

---

## A finding's line is a text search

**Decision.** A finding's line is found by searching the file's text for the
names `openspec show --json` gives, with no grammar of OpenSpec's headers:

- A requirement is at the first line, not taken by another, on which its
  name follows "Requirement:", compared ignoring case, backticks, `#`s and
  runs of space.
- When several lines match, a line starting with `###` wins over any other,
  such as an example quoted in a requirement's text. Among those, a line
  naming it exactly wins over one that matches only with case and the rest
  ignored, so two names OpenSpec tells apart keep their own lines.
- A rename is at its FROM line, the line that also holds `FROM:`.
- A requirement's text and scenarios are searched between its line and the
  next line starting with `## ` or `### `, each scenario after the one
  before it, on lines starting with `####`, with or without "Scenario:".
- A name the search cannot find gives line 0, and the finding names the
  file only.
- Where OpenSpec trims a header more than this search does, a finding can
  name the wrong line. Take a spec with `### Requirement: Foo ##` followed by
  a no-break space, and later `### Requirement: Foo`. OpenSpec reads both
  names as "Foo", but only the second header names "Foo" exactly, so the
  first requirement gets the second one's line. Matching OpenSpec's
  trimming would be the grammar this decision drops.

Two questions are about what the archive writes rather than where a name
is, and they use OpenSpec's one test for a requirement header,
`^###\s*Requirement:\s*\S`, ignoring case:

- The stray-heading advice asks whether a requirement header comes between
  the `## ` line that starts the section and the stray heading. A looser test
  told the author the archive keeps text that it drops.
- A requirement's lines, from its header to the next `## ` line or
  requirement header, are kept as the file writes them. A dependency
  delta rebuilt from some of its items writes those lines, so it keeps
  what `openspec show` leaves out, such as fenced code and the text under
  a stray heading, as the archive would. Fenced code also counts when two
  versions of a requirement are compared.

**Why.** The locator first matched OpenSpec's header grammar: optional
bullets, `FROM:`/`TO:` prefixes, a backtick closed only when one opened,
closing `#` runs, block ends. One bug-hunter run found 11 bugs, and every
one was that copy of the grammar disagreeing with OpenSpec 1.15 on some form
of header. That is the drift the CLI-only decision removed from reading
requirements, kept in a smaller place. A search with no grammar has nothing
to drift from, and a wrong guess only puts a finding on the wrong line.

**Rejected:** keeping the grammar as a best-effort locator. Each form
OpenSpec accepts and the copy does not is another wrong line, found one
review at a time.

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

Without OpenSpec 1.15.0 or later, `sign` still signs, and the value names
everything that did not run in place of the validate result: `show,
validate and archive not run (install OpenSpec 1.15.0 or later)`. A reader
of the trailer then knows that no requirement was checked, and how to fix
that.

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

## The hook is enabled by default

**Decision.** `hook.json` says `"default": "enabled"` for the commit hook.

**Why.** Several organizations install from this repository, each with its
own repositories, so the default must suit a repository that uses OpenSpec and
one that does not:
- Installing spec-check is itself the opt-in. Nobody gets the hook without
  asking for the skill.
- In a repository without OpenSpec, the hook does not speak: it judges only
  commits that change `openspec/`.
- It never blocks.
- Off by default, an installed spec-check would leave the spec stage
  unchecked, and nothing would say so.

**Rejected:** off by default. It suits a hook that reports on every commit,
which this one does not.
