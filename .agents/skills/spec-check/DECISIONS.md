# spec-check — decisions

`spec-check` does the part of spec review that needs every other spec in
mind, so the person reviewing judges only whether the rules are right. It
serves the spec stage of review: a change's specification is reviewed and
approved before any code for it is written, and that review is where a
reviewer's time goes. It has two parts: a script, `scripts/spec_check.py`,
and a consistency read done by a fresh subagent. The script's `check`
subcommand runs the mechanical checks, and `sign` runs them on the staged tree
and prints the commit trailer. A session hook (`scripts/handback.py`) and a
GitHub workflow keep a pull request from being handed back for review while
a change in it was edited after its last consistency read.
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

Two items came later, once decisions moved to design.md (see *Decisions live
in design.md*): decisions that contradict or repeat each other (item 12), and
a decision not needed to build the change (item 13). Three more came with
decision records (see *Decision records per capability*): a change that
brings back a rejected approach or breaks a recorded constraint (item 14),
a rejection or constraint named only in design.md (item 15), and a record
entry that repeats a requirement (item 16). Item 17 came with the rule that
record entries rest on evidence (see *Record entries are grounded*). It
flags reasoning or an entry that does any of these:
- names a person as its reason;
- records who decided or amended a decision, or when;
- states a preference;
- claims a fact without Evidence;
- only restates its requirement.

Every consistency read covers items 12 to 17, so no script checks decisions
or record entries for what those items cover. That stays true after
`prose compact` (the prose skill's command that shortens docs) shortens a
change's docs: whether a compaction kept every conclusion is checked by
`prose compact`'s own review. The evolution check does read a change's
records, but only for history wording (see *Document-evolution text is an
error*).

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

A change's own decision record skips the two credit rules. Its Evidence
names products, standards and dated runs ("Chrome chose a stricter parser",
"(Linux, 2024-05-01)"), which a credit rule cannot tell from a person or a
ruling date (see *Record entries are grounded*). The other history rules
apply to a record as to any change file. History in a record that only a
credit rule would catch, because it names who or when ("reversed by Adam
on 2026-10-21", "decided on 2026-10-21"), passes the script and is left to
the consistency read's item 17.

The finding quotes the line. Text in a code fence, a code span or double
quotes is skipped, since a spec about a checker quotes what it checks for.
Every line of a change's files is read, not only the lines a branch
changed. The specs under `openspec/specs` are not read: they are the
archived result of earlier changes, which no author is reviewing now.

**A person keeps a false `evolution` error.** Each change can hold a
`.spec-check-kept` file, committed with it, which `check` and `sign` both
read. An entry names a file relative to the change and quotes the flagged
line's text: `design.md: «The spec narrows the decision.» kept (asked):
<reason>`. The agent writes an entry only after a person chose "Keep as is"
in a question the agent asked through its host's interactive picker (in
Claude Code, `AskUserQuestion`). The entry clears every `evolution` error in
that file whose line has the quoted text, compared after runs of whitespace
are made one space. The spec text stays as written, and the trailer counts
the errors the file cleared (`1 evolution kept`), so the override shows in
git. The quote ends at the first `» kept`, so a line holding `» kept:` or
`» kept (asked):` cannot be kept. That limit is accepted: lifting it would
need an escape syntax in the entry form.

An entry that is malformed, gives no reason, or quotes the same line as an
earlier entry is a `kept` error.

An entry that matches no `evolution` error is a `kept` check asking for its
removal, whether or not it has `(asked)`. Its line changed or is gone, so
the person's answer no longer covers it. It is a check, not an error,
because it keeps nothing.

An entry that matches an error but lacks `(asked)` is a `kept` error. An
agent that cannot ask, such as a subagent, writes its entries without
`(asked)`. `sign` then refuses and names each such entry with the errors it
matches. The agent passes that message to whoever started it, who asks the
person. The prose skill uses the same `kept (asked)` wording when a person
keeps a passage its reviewer flagged, so an agent learns one convention.
The script cannot check that a person answered: `(asked)` is the agent's
statement.

The file is part of the change, so `openspec archive` moves it into
`openspec/changes/archive/<date>-<name>/` with the change's other files,
and spec-check never reads an archived change. `openspec validate --strict`
accepts it.

**Within a review round** (*One consistency read per round*), the
`evolution` check runs on every commit, since it is mechanical. An unkept
error refuses a commit whose read is deferred, just as it refuses the
round's last commit. The kept count goes after the check count on every value, whatever
its read clause says: `0 errors, 2 checks, 1 evolution kept; validate
passed; read deferred to the round's end`. The read clause is unchanged,
so `sign`, `ci` and the hand-back hook find a round's read on a commit
whose value counts kept lines. The kept file is one of the change's files,
so editing it, even alone, makes the change due for a read again. Reading
it costs the reader one short file, and a separate rule for it would let a
kept file change after the read with no reader seeing it.

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
  a decision verb ("Adam decided"), so it works in any repository. The word
  is not a name when it is in a heading, or in a list of common pronouns,
  determiners, conjunctions, prepositions and adverbs ("Also ruled out by
  scenarios"). An unlisted word draws an error. Treating every capitalised
  word ending in -ly as an adverb was rejected: it would also skip names
  such as "Anatoly". A missed credit passes silently, while a person can
  keep a false error (*A person keeps a false `evolution` error*, above).
- **A kept file outside the commit**, passed to `sign` as `--kept <file>`.
  `check` does not read it, so a reviewer, or a reviewing agent, running
  `check` on the branch sees each kept line as an error again, and may fix
  a line a person kept.
- **Entries keyed by line number** (`design.md:5035`). Any line added or
  removed above a kept line makes the entry stale.
- **An inline marker in the spec**, such as an HTML comment beside the
  line. It puts tooling noise in text people read.

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

## One consistency read per round

**Decision.** The mechanical checks run before every commit. The
consistency read runs once per review round. A **review round** is the
agent's work between two hand-backs to a person for review. A push ends
nothing: commits inside a round, pushed or not, carry `read deferred to the
round's end`, and pushing them warns about nothing. The read runs before the
hand-back that ends the round, and the round's last commit carries it, as
`read by a fresh subagent: <change>, ...; N amended, M open`. That trailer
is the record of the read. A change's **last read** is the newest commit,
among the branch's last 1,000, whose `Spec-check:` value names it and is
bound to that commit's own tree.

A change is **due** when the branch adds or edits it (its files differ from
the merge base with the base branch) and any of its files differs from its
last read's tree. Only the branch's own history is searched. On the base
branch itself the merge base is HEAD, which would leave nothing due, so
there every open change counts as the branch's own. Each read is of the
whole change. A `Spec-check:` value written before this rule existed,
`read by ...` with no names, counts as a read of every change its commit
touched, which is what each commit's read covered then.

- `sign` computes the names, from what is due, rather than taking them from
  the agent: the read covers every due change, or the value says `no read
  due`.
- A read that led to amendments is recorded on the commit holding them, so
  the amendments count as read. Reading them again would never end.
- `sign --read subagent` signs a code-only commit while a change is due, so
  the round's last commit can carry the read whatever it changes.
- A change on the base branch that this branch does not touch is not due,
  even when it changed after its own last read: its own pull request read
  it.

**Why.** In two long sessions, agents in review rounds re-reading large
documents were about 69% of spend, and spec-check's consistency reads were
13% of one session's spend and 19% of the other's. A read on every commit read the same change again for each
small fix. The record lives in git, in the trailer that already binds the
mechanical checks to the tree, so another agent, another worktree or a
reviewer finds it with no state of its own. A trailer whose tree is not its
commit's records nothing, so a value copied from another commit cannot
excuse a read.

**Why a hand-back and not a push.** Agents here push after almost every
commit, so that work survives a crash. A round ended at each push would
make each commit a round's last, and every one of them would need a read:
the per-commit cost this rule exists to cut. A hand-back is when a person
starts to read, so it is when the read must be done. The first design
(pull request #51) ended a round at a push too, and detecting a push
(`@{push}`, `push.default`, a push to the base branch, merges) was where
most of its bugs were.

The benchmark in the next section supports reading once per round: each
round-end read caught every problem planted in the round's edits, so
deferring the read to the round's end missed none of them. The saving
depends on how many commits a round holds. igor PR #216 had 40 commits with
a read and about 27 pushes; shared-skills PR #25 had 54 and about 53, so
rounds ended at pushes would have saved a third of #216's reads and almost
none of #25's. How many hand-backs either had was not counted.

**Two checks enforce it, and both judge the pull request, not a
directory.** Each asks GitHub for the pull request's head and reads the
`Spec-check:` trailers on its own commits, so the answer is the same for a
local agent, a person and an Igor (an agent run by igor, see *It fits igor
best*). A change is unread when it is due at that head. A hand-back is:
- `gh pr create`, unless `--draft` or `--dry-run`. With `--reviewer` it is
  a hand-back even as a draft, since it requests a review;
- `gh pr ready`, unless `--undo`;
- `gh pr edit --add-reviewer`;
- the GitHub MCP server's `create_pull_request` without `draft: true`, and
  its `update_pull_request` with `draft: false` or with `reviewers`.

A draft pull request that requests no review is not a hand-back.

- **The GitHub workflow is the guarantee**, where a repository uses Actions
  (`ci/spec-check.yml`, written by `spec_check.py setup-ci`). On
  `opened`, `reopened`, `ready_for_review` and `review_requested`, a pull
  request with an unread change fails the `spec-check` check, is made a
  draft again, and loses the review request. On `synchronize` the check
  only fails, so a round's pushes before its read do not flip the pull
  request back and forth, and a required check holds the merge until the
  read lands. It runs `spec_check.py ci` fetched at a pinned commit, as
  spec-trace's CI step does. The judgement reads only git, so it needs no
  OpenSpec CLI. It sees every hand-back however it was made: the agent's
  gh, the web page, another client, and an Igor's own posts. A fork's pull
  request gets a read-only token, so there the check fails and cannot make
  it a draft.
- **The session hook is fast feedback**, and where a repository has no
  Actions it is the only check, best effort (`scripts/check-handback.sh`,
  run before and after the tool call):
  - **Before the call**, a hand-back that names its pull request without
    needing a directory to find it is judged, and blocked while a change is
    unread. Named means by URL, by `-R` or `GH_REPO` with a number or
    branch, or by the MCP's owner, repo and number.
  - **After the call**, one GitHub MCP call that hands back is judged, and
    so is a shell command on an allowlist:
    - the shared command reader parses all of it, refusing no part;
    - it holds exactly one gh call, and that call is a hand-back;
    - no word in it expands (`$`, a backtick, a glob, a brace, or a `~` at
      a word's start, though `~/` passes), and no variable is assigned but
      `GH_REPO=<plain>` before the gh;
    - every other command in it starts with `git`, `cd`, `echo`, `printf`,
      `true` or `sleep`. When the hand-back names no pull request by number
      or URL (a create, or a ready or edit by branch), the list is
      narrower: `git push`, `git add` and `git commit` with plain options,
      `cd`, `true` and `sleep` (see *Why a hand-back that names no pull
      request gets a narrower list*).

    The one pull request the call printed is then the hand-back's: its URL,
    gh's `Pull request owner/repo#N is` line, or the MCP result's
    `html_url`. One handed back with a change unread is made a draft again
    (`gh pr ready --undo`), the reviewers the call requested are removed,
    and the agent is told to read, sign, push and hand back again. The hook
    also runs after a command that fails (Claude Code's
    `PostToolUseFailure`), since the hand-back may have gone through. The
    URL gh prints when a pull request already exists for the branch is not
    one the call handed back, and is never taken back.
  - **A hand-back off the allowlist gets a note, never a block.** Nothing
    is undone. The agent is told, as additional context after the call,
    that the hook did not check this hand-back, and why: the note names the
    program not on the list (`timeout`, `tee`, `bash`), quotes the word that
    expands, or names the variable assigned or the second gh call. It gives
    the allowlist and the plain form (run `gh pr ...` on its own, or with
    only those programs beside it), and says the GitHub workflow still
    checks the pull request. The note is given only when the command holds a
    hand-back. To find one, the hook reads each gh word, also one among
    another program's words, and the string after a shell's `-c`. An
    ordinary command gets no note.
  - **Also not judged**, and left to the workflow where there is one: a
    hand-back that printed no single pull request, as with output sent to
    `/dev/null`, or printed one other than the one it named.
  - **What the output is read as.** A URL alone at the start of a line, or
    gh's `Pull request owner/repo#N is` line after its symbol, once colour
    codes are taken out. An indented line, such as a commit body in
    `git log`, is not gh's. Every pull request printed is looked up on
    GitHub, and they must all be one; a named hand-back's must be that one,
    so another repository's pull request with the same number is never
    taken back. An `echo` or `printf` whose words hold such a URL or line,
    and `printf -v` (zsh runs commands in its variable name), are off the
    allowlist.
  - The pull request's commits are fetched into a cache, one bare partial
    clone per repository with no file contents
    (`~/.cache/spec-check/pulls/`), since the judgement reads only trees
    and trailers. The head commit is fetched by its id, and only then by
    `refs/pull/<n>/head`, which GitHub makes a moment after the pull
    request. git fetches with gh's token, so a private repository works as
    `gh repo clone` does.
  - The shell is read with the command reader prose's posting hook uses
    (`.agents/lib/gh-shell/gh_shell.py`), only to tell whether a command
    hands back and which pull request it names; never to work out the
    directory gh runs in (see *Why directory placement was abandoned*).
    What a hand-back is, and which pull request it names, is read by
    `.agents/lib/gh-shell/handbacks.py`, which prose's hooks share, so the
    two skills agree on what a hand-back is.
- **Both checks act after the fact.** A pull request created ready, or a
  review requested, notifies GitHub's watchers before the post-call hook or
  the workflow can take it back. A reviewer may get the notification of a
  hand-back that is a draft again a moment later. Blocking before the call
  is possible only when the call names its pull request.
- **What neither catches.** A hand-back made in conversation, with no gh
  command, such as telling a person the work is ready. Without a workflow,
  a hand-back through `gh api`, another client or the web page. For these,
  the reviewer still sees `read deferred to the round's end` on the head
  commit's trailer.

**Why directory placement was abandoned.** The first version of the hook
judged the local branch where gh would run, working out that directory from
the command text: each `cd` and `pushd`, runners such as `bash -c` and
`env -C`, CDPATH, heredocs. Two bug-hunter runs found 29 bugs in it, and
every iteration of both found new shell forms that moved gh somewhere the
hook did not look: `builtin cd`, `\cd`, `cd>/dev/null`, `env -iC`, a
heredoc fed to bash, `cd -P` through a symlink. The forms have no end. The
pull request itself is what is handed back, and GitHub names it exactly.

**Why one gh call, and no other.** The rejected alternative judged every
command that might hand back, and worked out which of the pull requests it
printed was the hand-back's. A bug-hunter run found 13 bugs in those rules
over three iterations. One fix, which skipped a pull request another gh
command named, hid the very pull request handed back in
`gh pr checks 7 && gh pr ready`. With one gh call, and that call a
hand-back, whatever pull request the command printed is that call's, and
no rule is needed to tell them apart. A command the hook does not judge is
uncommon in an agent's hand-backs, and the workflow judges it whatever the
command was.

**Why the post-call check is an allowlist.** The hook is fast feedback
for an honest agent; the workflow is the guarantee. The rejected
alternative listed what may hide a gh (shells, interpreters, wrappers,
`env -S` inside a word), and a bug-hunter run found another such program
in each of its three iterations. Any program can run a gh with no gh in
its words, so that list never ends, and a form it misses is misread: the
hook takes back whichever pull request was printed, which may be the wrong
one. An allowlist fails the other way. A form it does not list is skipped,
never misread, and the note tells the agent how to make it judged. The
forms an agent uses to hand back (`git push && gh pr create`,
`cd repo && gh pr ready 12`) are on it.

**Why a hand-back that names no pull request gets a narrower list.** When
its own gh prints nothing (a failed `gh pr create`, or a ready by branch),
a pull request another listed command printed would be the only one in the
output, and would be taken for the hand-back's: `git show -s --format=%b`,
a git alias or `rebase -x` that runs gh, `printf '%s/pull/%s\n' ...`. A
hand-back that names its number or URL is safe, since the pull request
printed must be the one it named. So beside one that names nothing, only
commands that never print a pull request may stand: `git push`,
`git add`, `git commit`, `cd`, `true` and `sleep`. `git -c` and every
other git subcommand are left out. Those three take only options that
print no diff and run no command (`commit -m`, `-a`, `--amend`; `push -u`,
`--force-with-lease`; `add -A`), so `git add -p`, `git commit -v` or
`--dry-run`, and `git push --exec` are off. When the narrower list is the
one broken, the note names it. The other option considered was to confirm
the pull request on GitHub (its author and creation time, or its requested
reviewers) before taking it back. The narrower list needs no further call
to GitHub, and a form it leaves out gets the note, never a wrong
take-back.

**Known gap.** `git commit` and `git push` run the repository's own hooks
(pre-commit, commit-msg, pre-push), which could call gh or print a pull
request's URL; the hook would then read that pull request as the listed
hand-back's. A gh hidden on purpose, by an agent working against the
check, is out of scope. The workflow covers both.

**It fits igor best.** In igor, a hand-back is an explicit, recorded
event: an Igor's handback comment, carrying igor's handback marker. An Igor
posts through its own code, which spec-check's session hook never sees, but
the workflow does: an Igor's pull request marked ready or sent for review
is judged like anyone's. This may make igor's own loop-side check (igor
issue #149) unnecessary. spec-check builds nothing igor-side.

**Every hand-back this detection finds also starts a current-state
pass:** prose's hook reads the agent's call after it runs, and the workflow
reads GitHub's `opened`, `reopened`, `ready_for_review` and
`review_requested` events (see *Events start a current-state pass*).

**A read with nothing to commit lands on an empty commit.** The read has
to be on a commit, and when every edit of the round is already pushed and
the read amends nothing, there is nothing to commit. A pushed commit is
never rewritten, so the read goes on an empty commit, made through the
shared commit script's `--allow-empty` (the commit-trailer library's
DECISIONS.md, *An empty commit, only when asked*). Its `Spec-check:` value
is still bound to the tree, which is the parent's. #51 never needed one: its
round ended at a push, so the last commit was still unpushed and could be
committed again with `git reset --soft`.

**Rejected:**
- **Ending a round at a push** (pull request #51). See *Why a hand-back and
  not a push*.
- **A state file under `.git/`.** It is per clone: another machine, or a
  reviewer, would read everything again, and nothing in the history would
  show that a read happened.
- **Main's spec changes making every open change due.** A spec change on
  main came through its own pull request, whose read held it against the
  open pull requests, this one included. Each read of this change reads
  main's specs whole anyway.
- **A gh reader of spec-check's own.** prose's already reads every form the
  agent's shell may take, and two readers would disagree about the same
  command. So prose's reader moved into `.agents/lib/gh-shell/`, which both
  hooks import from the clone, as the shell scripts find
  `.agents/lib/commit-trailer/`.
- **Loading `prose.py` by path for its reader.** It tied spec-check to
  private names in another skill's script, and ran all of prose's module
  code on every hand-back command.
- **Judging the local branch where gh runs.** See *Why directory placement
  was abandoned*. Judging every directory a `cd` might reach, and blocking
  when one could not be followed, still missed forms each iteration.
- **Judging only before the call.** A `gh pr create` names no pull request
  before it runs; only its output does.
- **Telling apart the pull requests a command printed.** See *Why one gh
  call, and no other*.
- **Looking up the branch's pull request when nothing was printed**, as
  after `gh pr create > /dev/null`. It needs the directory gh ran in.
- **Treating every command that names gh as running it**, as prose's
  posting hook does. A missed post publishes unchecked text; a missed
  hand-back leaves `deferred` on the head commit for the reviewer to see,
  and the workflow catches it where there is one. The false blocks cost
  more here than the misses.
- **Making the pull request a draft again on every push with an unread
  change.** Pushes inside a round are expected before the read; flipping
  the pull request on each would notify watchers each time. The failed
  check holds the merge instead.

---

## Events start a current-state pass

**Decision.** A current-state pass rewrites texts that may still describe
an earlier state, such as a design that says "will" for what is now built.
On each event below, a hook in the agent's session prints `current-state
pass due for: ...`, naming the texts, and the agent rewrites them to
describe the state as it now is, without asking first. It asks a person
only before deleting a conclusion, such as a decision or its reason; this is
the same rule `prose compact` follows ("just do it; ask on loss").

| Event | Detected as | The pass |
|---|---|---|
| The implementation is pushed onto a spec branch (gate two of the two-gate workflow, where a specification is approved first and its implementation is then pushed onto the same branch) | the commit hook sees a commit add a file under a `src/` directory while the branch adds or edits an open change (a change folder not yet archived). The branch's changes are found by comparing with the point where it left the base branch, its merge base. On the base branch itself, every open change counts | the change's proposal.md and design.md, and the pull request's body and title, for wording such as "specification only", or "will" for what is now built |
| A change is archived | the commit hook sees one commit delete `openspec/changes/<name>/` and add `openspec/changes/archive/<date>-<name>/`, as `openspec archive` does | the reasoning in the change's design.md that no requirement or record entry holds, moved into the decision record of each capability it changes, at the configured location: a Rationale entry for reasoning about one requirement; a Constraint entry for a rule the code must keep that no test can check, with its Evidence, including a principle behind several requirements, not repeated as Rationale under each (a principle with no evidence becomes Rejected entries for what it rules out); a Rejected entry for an alternative turned down, including the fix not taken behind an accepted limit or trade-off. What fits none of these (how the design was reached, rollout or migration steps, overviews of the code, open questions), and anything still without Evidence or too slight for a later reader to decide anything with, stays in the archived design.md and is never folded. In shared-skills, also into the DECISIONS.md of each skill it affects that keeps one; then `prose check` on each file changed, compacting any it reports as due |
| A pull request is handed back for review | a hand-back, as *One consistency read per round* detects it: prose's hook, after the agent's `gh` or GitHub MCP call that hands back; or spec-check's GitHub Actions workflow, which prints a `::notice::` when every change already has its consistency read, so the hand-back stands | prose's single-pass rule holds doc rewrites back to one pass at the end, before a person reads them; this is that pass: any doc the pull request changes, or its body, that still describes work as unfinished or to come |

**Why.** Keeping proposals, designs and pull request bodies current had
slipped: in the igor repository, pull request #216's body sat stale for six
review rounds. An agent does a pass when something tells it to at
the moment it is due.

- The commit hook, which the agent host runs after each shell command
  (not a git hook), finds the first two events through the commit-trailer
  library's `commit_trailer_notice` callback, which sees every new commit,
  including those that change nothing under `openspec/` (the library's
  DECISIONS.md, *A skill may print notices about a commit*). A shell `grep`
  of the paths the commit adds spares starting Python for other commits.
- Each commit that adds `src/` files prints the gate-two pass again, since
  each may build more of what the change says "will" happen.
- An amend prints only the passes its replaced commit would not have
  printed. The replaced commit is found from HEAD's reflog. A pass for the
  same change or archive is not asked for again when the amend adds no
  `src/` file the replaced commit lacked, so folding a pass's own edits into the commit, or
  dropping a file from it, asks for nothing. To know what the replaced
  commit printed, it is judged as its own hook judged it: by the base-branch
  rule when the base branch's reflog records it committed there, otherwise
  by the branch rule (only open changes the branch adds or edits). The
  branch rule counts fewer passes as already printed, so using it when
  unsure makes the amend print more: a pass the replaced commit may not
  have printed is printed now rather than lost. With no reflog entry for it, the
  branch rule is used.
- **An archive is the pair `openspec archive` makes.** The archive pass is
  asked for only when one commit deletes `openspec/changes/<name>/` and adds
  `openspec/changes/archive/<date>-<name>/`, or `archive/<name>/` with the
  name kept as is, as `openspec archive` does for a name that already starts
  with a date. Moving folders that are already archived changes, kept
  elsewhere in the repository or already under `openspec/changes/archive/`,
  deletes no open change folder (one directly under `openspec/changes/`
  other than `archive/`), so it is not archiving and asks for nothing.
  Archiving a change that was never committed as open asks for nothing
  either, since no commit deletes its folder; the two-gate workflow never
  does this, as its spec is committed first.
- Whether a commit is on the base branch is read from the commit, not from
  HEAD: it is when the local base branch, or the base ref (such as
  `origin/main`), holds it. The hook
  runs after the whole command, so `git commit && git checkout main` leaves
  HEAD elsewhere, and after `git push origin HEAD:main` from another branch
  only the remote's copy holds the commit.

**Known limits.**
- **A rebase continued after a conflict on the gate-two commit asks for the
  pass again,** as does a cherry-pick of it. The library treats the reflog
  actions `rebase (continue)` and `cherry-pick` as new commits and passes
  them to the callback, and the replayed commit
  adds the same `src/` files against its new parent. It is not fixed because
  the original commit is not in the reflog, so pairing the replay with it
  would mean guessing, by subject or patch-id. The repeat is one advisory
  notice, and doing the pass again is cheap.
- **Amending a cherry-picked, reverted or `git am` commit on the base
  branch asks for the pass again.** The replaced commit counts as made on
  the base branch only when that branch's reflog records an action starting
  with `commit`; these log `cherry-pick:`, `revert:` or `am`, so it is judged
  by the branch rule and its pass looks unprinted. To avoid it, commit there
  rather than amend. An agent that already did the pass for that change can
  skip the repeat.
- **A commit reset away in the same command may never get its pass.** The
  replaced commit is judged by whether it was ever committed on the base
  branch, not whether the branch held it when its hook ran. So
  `git commit && git reset --hard HEAD~1` in one command on the base branch,
  then `git reset --hard <that commit>` and an amend, may show no pass at
  all. The commit's hook ran after the reset, when the base branch no longer
  held it, so it used the branch rule and printed nothing. The amend finds
  the commit in the base branch's reflog and counts the pass as printed. No
  test has proved this case; it is reasoned from the code.
- **"On the base branch" is judged at commit time.** A commit made on
  another branch and pushed to main in a later, separate command gets no
  gate-two notice: when the hook judges the commit, neither the base ref nor
  the local base branch holds it. The library finds new commits in HEAD's
  reflog, and a push adds no entry there for the hook to see. Committing and pushing in one command gets the notice.
- The archive pass is printed for the commit that archives, in the clone
  where it is made. A merge that brings an archive in is not that commit,
  and prints nothing.
- The hand-back pass is prose's to print in the session, since the
  single-pass rule is prose's, and prose may be installed where spec-check is
  not. The workflow's notice is for a hand-back made outside such a
  session, such as by a person on GitHub or from a clone without prose.

---

## The read is of the whole change, and the reader finds what is related

**Decision.** Each round's read covers the whole change, and the reader
searches the specs, open changes, pull requests and architecture docs for
what relates to it, as the brief says. Neither a script-built reading pack
nor a read of only what changed since the last read is used.

**Why.** Both were built and benchmarked against the brief before them
(2026-11-01), and neither earned its place.

The benchmark: four rounds from real history, each a sandbox whose last read
is the round's start and whose working tree is the round's end: igor PR
#216 from `974d106` to `83d01a1` and from `8600ffe` to `3cd96d3`, and
shared-skills PR #25 from `9f93f19` to `1d19e58` and from `dfa9f36` to
`3576599`. Into each, six contradictions were planted: five in the round's
edits, against main's specs, the unchanged change or its decisions, and one
already present at the last read. Each sandbox was read once by each brief:
this one, one reading a pack built from the whole change, and one reading a
pack of only what changed since the last read. No pull requests were read:
the sandboxes have no remote.

| Round | This brief: tokens, caught | Whole-change pack | Incremental pack |
|---|---|---|---|
| #216, 974d106 | 99k, 6/6 | 256k, 5/6 | 161k, 5/6 |
| #216, 8600ffe | 222k, 6/6 | 246k, 6/6 | 133k, 5/6 |
| #25, 9f93f19 | 72k, 5/6 | 228k, 6/6 | 119k, 6/6 |
| #25, dfa9f36 | 87k, 5/6 | 297k, 6/6 | 84k, 5/6 |
| Total | 481k, 22/24 | 1,028k, 23/24 | 497k, 21/24 |

Every brief caught all 20 problems planted in the rounds' edits. Of the four
present at the last read, this brief caught two, the whole-change pack
three, and the incremental pack one. This brief's readers did not read
every spec in full: they searched, at 72k to 222k tokens. Single runs, with
planted problems, so the figures are a sign, not a measure.

**Rejected:**
- **A reading pack built by a script** (`spec_check.py pack`): the
  requirement paragraphs, scenarios and decisions elsewhere that share a
  name or IDF-weighted terms with the change. Built from the whole change,
  it cost twice this brief's tokens for one more catch; the readers it
  replaced were already searching, not reading everything.
- **Reading only what changed since the last read.** It cost what this
  brief did (3% more over the four rounds) and caught the fewest problems
  already present at the last read: one of four, which its pack happened to
  quote.

---

## The reader reads every file of the change whole

**Decision.** The read is done by a general-purpose subagent, not Explore.
Its brief lists every file of the change and tells it to read each whole,
every line, paging long files with the Read tool, never skimming, grepping
or sampling: a problem may sit anywhere in a long delta spec. The files are
listed, not pasted into the brief.

**Why.** A second benchmark (2026-11-02) used the same four rounds and
planted problems as the one above, two runs per round and brief, so eight
reads per brief:

| Brief | Tokens per read | Problems in the round's edits (of 40) | Already there at the last read (of 8) |
|---|---|---|---|
| A: today's brief, general-purpose | 150k | 39, 1 partly | 2 |
| B: A with the change's files pasted in | 147k | 40 | 3 |
| C: Explore, told to read each listed file whole | 206k | 38, 2 partly | 6 |
| D: general-purpose, told to read each listed file whole | 267k | 39, 1 partly | 7 |

The first comparison had a confound: C changed both the agent and the
wording, so its 6 of 8 could have come from either. D kept A's agent and
took C's wording, and caught 7 of 8 against A's 2 of 8 (Fisher's exact
test, one-sided, about 0.02). The wording does it. Problems in the round's
edits were caught by every brief, so the gain is all in what was already
there, which a reader of only the familiar parts misses.

The cost is about 78% more tokens per read (267k against 150k). Reading
once per review round (see *One consistency read per round*) is what pays
for it.

**Rejected:**
- **Explore** (C). It cost 37% more than A for one fewer catch than D, and
  one of its eight reads said it had not read every line: the wording does
  not hold it.
- **Pasting the change into the brief** (B). It saved no tokens, and its
  readers skimmed what they were handed.

Single runs per cell, with planted problems: the figures are a sign, not a
measure.

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

## Decision records per capability

**Decision** (issue #56). A behavioural rejection or constraint is an
ordinary requirement, with a scenario the rejected approach would fail,
under the requirement that approach would break. A requirement holds its
rule: its SHALL statement plus at most one *because* sentence, with any
evidence linked. What a requirement cannot hold goes in a decision record,
one per capability: constraints and rejected alternatives that no test can
check, and, in a Rationale entry named after a requirement, reasoning
longer than that requirement's *because* sentence; each is stated as it
stands now, in the form SKILL.md, *Decision records*, gives. Decision
records work in any repository that uses spec-check.

spec-check:
- **reads the record's location** from `openspec/spec-check.yaml`
  (`decision-records: <path holding <capability>>`), by default
  `openspec/specs/<capability>/decisions.md`, beside the spec, so an agent
  reading a spec sees the record in the same folder;
- **checks a record's form** (`record`): its title, its sections, every part
  of every entry, each path in *Paths*, and that each Rationale entry names
  a requirement;
- **flags a requirement with more** than its statement and one sentence
  (`rationale`, a check), and the consistency read's item 6 asks for the
  rest to move to the record;
- **gives the reader** the record of every capability the change touches
  and every record whose *Paths* match a file the branch changes
  (`spec_check.py records`), and the reader reports a change that brings
  back a rejected approach or breaks a constraint (item 14), names one in
  design.md that no record holds (item 15), or keeps a record entry whose
  rule a requirement already states (item 16);
- **folds a change's record into the main one at archive**
  (`spec_check.py archive`), since OpenSpec does not.

**Why.** Rejected alternatives and constraints lived in files no check
reads: a skill's DECISIONS.md here, and archived `design.md` files in
igor, another repository that uses spec-check. So
nothing flagged a change that brought one back. A rule a test can check
belongs where spec-trace, the skill that links tests to scenarios, ties it
to a test; the rest needs a fixed place
and form, so a script can check it and a reader can be handed it.

**A record never repeats a requirement.** A Constraint or Rejected entry
whose rule a requirement or scenario already states is cut. A reason that
fits in one sentence becomes the requirement's *because* sentence; longer
reasoning goes in a `## Rationale` entry, `- **Rationale: <requirement
title>.**`, followed by the reasoning on its own lines and any number of
`Evidence:` lines. The entry never restates the rule. Why: two statements
of one rule drift apart, and the reader of a later change cannot tell
which one holds. The requirement and its scenario are the statement a test
checks, so that one stays. A Rationale entry's title must name a
requirement in force (in main's specs, plus those of the changes the
change builds on), or one the change adds, modifies or renames to. `check`
reports any other as an error, since reasoning for a requirement that is
gone explains nothing; it skips the check when `openspec show` cannot read
those requirements, and for a main record whose capability has no spec,
which instead gets a check saying the capability has no spec. For the same
reason, take a requirement with a Rationale entry in a main record, or in
the record of a dependency folded in first: a change that removes or
renames that requirement gets a `record` error until the change's own
record retires the entry or, for a rename, carries it over as a
Rationale entry titled with the new name. A carried-over entry replaces
the old one in place at archive, so the record keeps one entry per
requirement. `records` names a Rationale entry whose requirement
the change's delta adds, modifies, removes or renames, so the reader
checks that the reasoning still holds. The
repeat itself is the consistency read's to find (item 16). Rejected: a
mechanical check of text overlap between entries and requirements. The
same rule is worded differently in each place, so matching words would
both miss repeats and flag entries that only share terms.

**What OpenSpec does with a record**, measured on 1.16.0 and 1.15.0 in a
scratch project: `openspec validate --all --strict` passes with a record
at `openspec/specs/<capability>/decisions.md` or at
`openspec/decisions/<capability>.md`, and neither is read as a spec or a
capability, even when it holds a requirement header; `list` and `show`
ignore both, and so does a `specs/<capability>/` folder holding a record
alone. `openspec archive` leaves a main record unchanged, and ignores a
change's `specs/<capability>/decisions.md`: the file stays only in the
archived copy. `OpenSpecIgnoresDecisionRecordsTests` pins all of this, so a
release that starts reading a record fails spec-check's tests. spec-trace
reads only each capability's `spec.md` (`scripts/spec_trace.py`, where it
joins `spec.md` to each capability's folder), so it needs no change.

**The configuration.** One key, read with a few lines of standard-library
code rather than a YAML parser, since spec-check installs with no
dependencies. The path must hold `<capability>` once, as a folder of its
own, sit under `openspec/` (the only directory `check --ref` and `sign`
read from git) but not under `openspec/changes/`, and end in a fixed `.md`
file name other than `spec.md`.
An unknown key, a malformed line or an unusable path is a `config` error,
so `sign` refuses; the default location is used meanwhile, so the other
checks still run.
**The location ends in a fixed file name inside a `<capability>` folder:**
the default `openspec/specs/<capability>/decisions.md`,
or for example `openspec/decisions/<capability>/decisions.md`. Every file it
matches is a record, and nothing under `openspec/changes/` is ever a main
record. A location whose file name holds `<capability>` is a `config`
error. Why: such a location, like `openspec/specs/<capability>.md`, also
matches ordinary docs, and no rule tells a record from a doc reliably.
The two rules tried, by title and by whether the capability has a spec,
between them misread three cases: a nested capability's record was hidden
and then written over; a doc turned into a malformed record when its
capability was created; and a malformed record passed `sign`. Rejected for
that reason:
`openspec/decisions/<capability>.md`, the alternative measured in issue
#56. A location naming `spec.md` or `openspec/changes/` in other letter
case is refused too, since macOS's default filesystem ignores letter case.
For the same reason, a file whose path differs from the record's only in
letter case, which is not read as a record, stops the fold rather than
being written over.

**No symlink under openspec/.** spec-check refuses every symlink that is
`openspec` itself or under it, wherever it points, at one gate. The gate
looks only at the tree being judged: the checkout or staged tree for
`check`, `sign`, `records` and `archive`, which exit 2 naming each link;
the pull request's head for `ci` and the hand-back hook, which take the
hand-back back or block it, as for an unread change. No linked layout is
supported. Why: no repository using spec-check has such a link, and every
attempt to handle one, in any form, brought new bugs. Resolving links let
one record have several paths. Judging them by where they stood let a
link's record be judged in some places and skipped in others. A tree read from
git does not hold what a link outside `openspec/` points to, so check and
sign disagreed.

**Record entries are grounded.** Every entry gives a later reader
something to decide with. A Constraint is a rule no test can check, with
Evidence that is a failure, a measurement or an outside fact; a Rationale
entry states what goes wrong without its requirement, with Evidence for any
fact it claims; a Rejected entry's *Lost because* is a reason a later reader
can check. A principle that is a judgment call is recorded as the Rejected
entries for what it rules out, which a later change can retire with its own
reason. Reasoning that names who decided, states a preference or only
restates its requirement is noise, and a generic principle never goes in a
record. The consistency read flags all of this (item 17) in the round it
appears, and
the archive pass leaves anything still unevidenced in the archived
design.md. Why: an entry is read many times, by people who were not there;
a rule backed only by who decided it either fossilizes, since nobody can
tell whether it still holds, or gets ignored; and evidence is cheapest to
get while the person who decided is still present, not at archive.
Rejected: optional Evidence on a Constraint, which lets a preference pass
as a rule; a link to the decision counting as Evidence, which points at who
decided rather than why it holds; an Evidence-free "stated policy" kind,
the same preference under another name; a `check` pattern for attribution
wording in records, including the evolution check's credit rules, which
records skip, since a pattern cannot tell a person from a product, a
standard or a group ("per Unicode", "Chrome chose…", "(Linux, 2024-05-01)"),
so it errors on the very evidence the bar asks for (the same reason the
undefined-term check was rejected: "A program cannot tell a term from any
other word"). Accepted limit, for the same reason: history in a record
that only a credit rule would catch, because it names who or when, passes
the script and is left to item 17, since a rule that caught "Adam narrowed
the scope" would also catch "Safari reversed the default", and one that
caught "decided on 2026-10-21" would also catch a dated run; the other
history rules still apply to records. A process rule for people, such as
who reviews what, has no evidence a later reader could check, so it belongs
in an agent's memory or the team's notes, not in a spec or record.

**Record titles match exactly.** A record entry names a requirement, and
matches a main entry, only by its exact title: the bold title less its
closing period, with surrounding space trimmed. `openspec archive` trims a
requirement's name the same way and compares names with no other
normalisation, so case and spacing count. An entry for a requirement whose
title ends in a period writes its bold title with two periods. This holds everywhere titles
match: the fold at archive, carry-overs and retirements, the check that a
removed or renamed requirement's Rationale entry is retired or carried
over, the rule that a Rationale title names a requirement, and a
dependency's renames when its record folds first. On a miss, the error
suggests the exact title when one requirement or entry matches ignoring
case, spacing, backticks and a closing period. That loose match only feeds
the suggestion; it never counts as a match.
Why: matching exactly as the archive does means spec-check and OpenSpec
always agree on what a title names. Rejected: matching loosely, ignoring
case, spacing, backticks and a closing period. The archive removes or
renames only the exact name and skips any other as already applied, so a
loose match let spec-check retire a Rationale entry from a requirement
that stayed, or carry one to a requirement the archive never renamed.
Three gates tried to close that gap (refusing titles that shared a loose
key within a change, against main, and on removals that missed) and each
review found another way through.

**No title reused within one change.** `check` and `sign` refuse, as a
`title-reuse` error, a change in which one exact title both leaves
(removed or renamed from) and arrives (added or renamed to): a swap, a
chain, or a rename plus a new requirement under the old title. Plain
renames and removals pass, and so does a rename that changes only case,
whose record entry is carried over like any other. A near-duplicate
differing in case or spacing from a requirement that stays is left to
`openspec archive`, which refuses a requirement whose name differs from an
existing one only in case or spacing. Why: with one title naming two requirements in one change,
a record entry under it could belong to either, and every attempt to
carry Rationale entries through it lost one at archive or forced a record
that `check` refused however the author wrote it. Splitting into two stacked changes, which can
share a pull request, gives each title one meaning per change.

`check` reports every refusal the fold would meet,
such as a malformed main record, or a location such as
`openspec/<capability>/decisions.md` putting the record of a capability
named `changes` under `openspec/changes/`.

igor's `openspec/spec-check.yaml` still holds `decisions-first: enforce`
from the rejected decisions-first rule (*Decisions live in design.md*), so
that key is a `config` check asking for its removal, never an error.

**A change's own record stays at `specs/<capability>/decisions.md`**,
wherever the main record is configured to be: beside the delta it goes
with, where issue #56 puts it. It uses the record's form, and adds one
section, `## Retired`, whose entries are bold lines alone naming main
entries to remove. A Rationale entry is matched by its requirement's
title, so a change's Rationale entry replaces the main one for the same
requirement. An
entry whose kind and exact title match a main entry replaces it in
place; any other is added at the end of its section. A record left with no
entry is deleted. So a record holds no history: an amendment replaces the
entry, and a retirement removes it.

**The fold runs around `openspec archive`.** `spec_check.py archive
<change> -- <openspec archive arguments>` computes every folded record
first, refuses with nothing archived when one cannot be folded (a change
record out of form, a retirement of an entry the main record lacks, a main
record out of form), then runs `openspec archive`. It writes the records
only once the change has left `openspec/changes/`, however `openspec
archive` ended, so records are never folded for an archive that did not
happen. The fold must match what
OpenSpec did, and an answer to one of its prompts, such as declining the
spec updates, is invisible to spec-check: so `archive` always passes
`--yes` (once, when the user has not), and OpenSpec never prompts. With
`--skip-specs`, OpenSpec leaves the main specs alone, and the records are
left alone with them. `check` reports the same
refusals on the change beforehand, as `record` errors. For a stacked change,
`check` folds each dependency's own record into a copy of the main records
first, in `Builds on:` order, leaving out a merged one, whose record is
already folded, just as `check` archives the dependencies' deltas before
the change's.
Without that, a change retiring an entry its dependency adds was refused
though it would archive cleanly after the dependency. `records` lists each
dependency's own record, read from its pull request. `archive` refuses a
change while a change it builds on is still open in the tree: archived
first, its entries would fold in after the stacked change's, and an entry
the stacked change replaced would come back without a word. A dependency
whose pull request has merged while its change folder is still in the
tree counts as not yet archived, whether it holds only records or deltas
too.

A dependency's records are judged exactly like its deltas. An open
dependency's records are held, meaning the tree already has what they
add, only when folding them onto the main records, with the records of the
dependencies listed before it folded in, changes nothing; its deltas are
held only when the specs so far already show them. That one result decides
both stale-line checks ("already in the tree: remove the line" and "some
of its deltas are already in the tree"). It also decides whether a change
that a dependency builds on, and that this change does not list, must be
listed. A merged
dependency's records are judged like its requirements, by presence and
never replayed: each entry it adds or replaces must be in the tree's main
record by kind and title, with any text, and each it retires must be gone,
or check says to merge main. That error also names the other way a merged
dependency's records go missing: archived with plain `openspec archive`,
which never folds them, and then they are folded by hand. When a
dependency's record cannot fold, the stacked change's record for that
capability is not folded either, since every refusal that record met
would follow from the dependency's failed fold. `archive` refuses a change whose `Builds on:` lines it
cannot read, since it cannot tell what must archive first.

**What is an error and what a check.** A departure from the form is an
error: the record is read by a script, and the fold rewrites it. *Evidence*
or *Lost because* with no link, and *Because* or *Lost because* holding
more than one sentence, are checks: telling a link or a sentence from
other text is a guess. A path in *Paths* that the tree lacks is an error in
a main record and a check in a change's own: a spec-stage change names
files its implementation adds, as a citation of a line only the change adds
is a check (*A citation fails only where it cannot be wrong*). A main
record whose capability has no spec is a check.

**The rationale check counts sentences.** A sentence holding an RFC 2119
keyword (SHALL, MUST, MAY, SHOULD, REQUIRED, RECOMMENDED, OPTIONAL) states
the rule. A list item continues the statement it hangs from, so only the
sentences after an item's first count. A sentence that is only a link, or
starts `Evidence:` or `See`, links evidence. More than one other sentence
is a check. It runs on a change's added and modified requirements only. Of
the 138 requirements in igor's main specs at `7117a88`, 84 hold more than
one such sentence: the rationale this decision moves out, and too many to
show on every `check specs`.

**Rounds and the evolution check.** A change's own record is one of its
files, so editing it makes the change due for a read, and the `evolution`
check reads it, with the change's kept file (`.spec-check-kept`) covering
it like any other file. A main record's edit makes no change due, for the reason a main
spec's does not (*One consistency read per round*), and the `evolution`
check does not read main records, as it does not read main specs: what
reaches them came through a change that was checked.

**Rejected:**
- **A change editing the main record directly.** The record would say a
  constraint holds before the change that brings it lands, and the reader
  of every other change would be held to it.
- **The rationale check on main specs.** 84 checks on every `check specs`
  in igor, about text no change is editing.
- **Finding rejected alternatives in design.md with a pattern.** OpenSpec's
  design.md has no fixed place for them, and telling a rejected approach
  from a described one is the reader's judgment (item 15).
- **Writing the folded records into the scratch copy `check` archives
  into.** `check` folds in memory, the dependencies' records first, which
  finds every refusal without a file to write.

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
0 of that file. Without OpenSpec 1.16.0 or later, the archive is reported
"not run", like every check that needs the CLI. The tree is never touched.

**Why.** Each of these passes `openspec validate`, which reads a change on
its own, and fails only when the change is archived, after review. The CLI
is the definition of what it refuses, as for stacked changes (see *Why the
real `openspec archive`*). Archiving only the
checked change keeps one open change's deltas from failing another's check:
which lands first is not known.

OpenSpec stops at its first refusal, so one run shows at most one.

`check` reads the archive's result from `archive --json`. It reads
`openspec --version` first and treats a CLI older than 1.16.0, or one whose
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
commands of the OpenSpec CLI, 1.16.0 or later:

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

Below 1.16.0, or with no CLI, every check that needs a requirement reports
`not run: install OpenSpec 1.16.0 or later`: the scenario, duplicate and
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
  the archive drops. Only 1.15.0 and later report both.
- **1.15.0 as the minimum.** Its fence reader lacks CommonMark's rule that a
  backtick fence's info string may not hold a backtick, so a line such as
  ```` ```npm test``` ```` opens a fence in 1.15.0's reader and hides every requirement
  after it from the archive. spec-check reads fences as 1.16.0 does, so on
  1.15.0 its title-reuse gate and record folds could judge requirements
  the archive never applies.
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
- **A section or requirement written inside a code fence.** OpenSpec 1.16.0
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
`Spec-check: ✓ <tree> <summary>`. The summary ends with the round's read:
deferred, the changes read, or `no read due` (see *One consistency read per
round*). The commit script runs `verify-staged.sh`
before committing, and the commit hook runs `verify-commit` after. Both
compare the value's tree with the tree that lands. A value starting `skipped` binds
nothing.

**Why.** A trailer typed from memory can look right. One bound to the tree
proves the checks ran on what landed, and an edit staged after signing breaks
it. This is the commit-trailer library's design
([its DECISIONS.md](../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent)).

Without OpenSpec 1.16.0 or later, `sign` still signs, and the value names
everything that did not run in place of the validate result: `show,
validate and archive not run (install OpenSpec 1.16.0 or later)`. A reader
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
`:(top)openspec`. `sign` lists the staged paths with the same pathspec, to
decide whether the commit needs a trailer and what to check. The pathspec
matches a folder, file or symlink named `openspec` at the root, and every path
under it, but not a path such as `openspec-notes/`. A commit that changes nothing there is
never judged, with or without a trailer.

**Why.** A code-only commit has nothing to check, and a report on it would
teach readers to ignore the report.

**Rejected:**
- **Filtering inside this skill's report.** The library has already decided
  to report by then, and an empty report falls back to the library's
  generic one.
- **A callback the library calls per commit.** A pathspec is data, so it
  needs none of the subshell and marker machinery a sourced callback does.
- **`:(top)openspec/`, with the slash.** It matches only paths under a
  folder, so a commit that only adds or retargets an `openspec` symlink
  would never be judged, and so never meet spec-check's refusal of a
  symlink under `openspec/` (*No symlink under openspec/*).

**Limit:** only `openspec/` at the repository root counts, which is where
OpenSpec puts it.

---

## The hooks are enabled by default

**Decision.** `hook.json` says `"default": "enabled"`, for the commit hook
and the hand-back hooks alike: manage-skills switches a skill's hooks
together.

**Why.** Several organizations install from this repository, each with its
own repositories, so the default must suit a repository that uses OpenSpec and
one that does not:
- Installing spec-check is itself the opt-in. Nobody gets the hooks without
  asking for the skill.
- In a repository without OpenSpec, neither hook speaks: the commit hook
  judges only commits that change `openspec/`, and the hand-back hook only a
  pull request with an open change.
- The commit hook never blocks. The hand-back hook acts only on a hand-back
  that would leave a change unread, and a draft that requests no review is
  never a hand-back.
- Off by default, an installed spec-check would leave the spec stage
  unchecked, and nothing would say so.

**Rejected:** off by default. It suits a hook that reports on every commit,
which neither does.
