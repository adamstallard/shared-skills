---
name: spec-check
description: >-
  Check an OpenSpec change for correctness and consistency before a person
  reviews it, so the reviewer judges only whether the rules are the right
  ones. Use when drafting or reviewing an OpenSpec change, before committing
  or opening a pull request that adds or changes anything under
  openspec/changes/ or openspec/specs/, when reviewing a spec pull request,
  or when asked to "check this spec", "cross-check the change" or "is this
  spec consistent". Runs mechanical checks with a script on every commit,
  has a fresh subagent read the change against every other spec, change and
  open pull request once per review round, and fixes findings in the spec
  itself. Commits that change openspec/ carry a Spec-check: trailer. It
  ships a GitHub workflow that runs the same checks in CI; also use it when
  asked to add that workflow to a repository, or to update the commit of
  this skill's repository that the workflow downloads the checker from.
---

# spec-check

**A spec reviewer should spend their time on whether the rules are right, not
on holding every other spec in mind.** This skill does the holding: a script
checks what is mechanical on every commit, and once per review round a fresh
subagent reads the change against everything it must agree with.
Readability is the `prose` skill's job; linking tests to scenarios after
implementation is a separate step.

- `$SC` below is this skill's `scripts/` directory, as an absolute path.

## When

- **The mechanical checks:** before any commit that changes a path under
  `openspec/changes/` or `openspec/specs/`.
- **The consistency read:** once per review round, before the round's last
  commit, the one you hand back. A review round is your work between two
  hand-backs to a person: a pull request opened or marked ready, a review
  requested, or telling a person the work is ready. A push does not end a
  round, and a draft pull request that requests no review is not a
  hand-back. Commits inside a round record the read as deferred and may be
  pushed (see [Commit](#commit)).
- When reviewing a spec pull request, yours or someone else's, or when asked
  to check a spec: both.

## 1. Mechanical checks

```sh
python3 "$SC/spec_check.py" check <change-name>        # one change, working tree
python3 "$SC/spec_check.py" check                      # every open change
python3 "$SC/spec_check.py" check specs                # openspec/specs
python3 "$SC/spec_check.py" check --ref origin/<branch> <change-name>   # a PR branch, no checkout
```

It reports `file:line: error|check [kind] message`, then the results of
`openspec archive` and `openspec validate --strict`, which it runs for you.
Exit 0: no errors. Exit 1: errors to fix. Exit 2: it could not run, and says
why.

Checking a change also checks the [decision records](#decision-records)
it bears on, as `sign` ([Commit](#commit)) does for each change a commit
stages, so `check` finds every record error that would make `sign` refuse.
A change bears on:

- the record of each capability it touches;
- each record whose *Paths* line names a file the branch has changed since
  it left the base branch;
- each record the branch edits, or whose `.spec-check-kept` file beside it
  the branch edits (described under
  [Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags)).

A commit that stages a record makes `sign` check every record. `check specs`
checks every record too, so run it before such a commit.

A shallow clone may not reach the commit where the branch left the base
branch. Then nothing can tell which lines of a record the branch changed, so
`check` and `sign` skip the `evolution` check on that record, with a `check`
finding saying so. `git fetch --unshallow` fixes it.

**spec_check.py needs OpenSpec 1.16.1 or later on PATH** (`npm install -g
@fission-ai/openspec`), and reads specs and deltas only through it:
`openspec show --json` for requirements, `openspec validate --strict --json`
for what a delta drops or misfiles, `openspec archive --json` for whether a
change applies. Without it, each check that needs a requirement reports
`not run: install OpenSpec 1.16.1 or later` and why, such as `(this one is
1.14.3)`; citations, the check that each `Builds on:` line can be read, and
the `renamed-block` scan still run.

| Kind | Severity | What it means |
| --- | --- | --- |
| `no-scenario` | error | A requirement states a SHALL or MUST and has no scenario |
| `renamed-block` | error | A `###` heading under `## RENAMED Requirements` holds more than FROM and TO lines. `openspec archive` drops the rest silently. Restate the requirement under `## MODIFIED Requirements` with its new name |
| `title-reuse` | error | Within one change, a title leaves (removed, or renamed away from) and the same exact title arrives (added, or renamed onto), as in a swap, a chain, or a rename plus a new requirement under the old title. spec-check doesn't support this. Choose another title, or split it into two changes, the second with a `Builds on:` line for the first (both can sit in one pull request). Titles compare exactly, so a near-duplicate differing only in case or spacing from a requirement that stays is not a `title-reuse` error; `openspec archive` refuses it, and it shows as an `archive` error |
| `scenario-incomplete` | error | A scenario has no WHEN or no THEN |
| `duplicate` | error | A sentence of the rule also appears under another requirement, here or in another spec or change. Two requirements with one name may share sentences only when one is a MODIFIED requirement in the other's capability |
| `archive` | error | `openspec archive` refuses the change: an ADDED requirement whose name is already there, a RENAMED onto a name already taken, a MODIFIED that drops a scenario, or a requirement modified, removed or renamed that is not there. The error quotes the CLI. See [Archive refusals](#archive-refusals) |
| `purpose` | error, or check | Error: a delta creates a capability (no spec in main or in what the change builds on), and the Purpose `openspec archive` would give the new spec fails `openspec validate --strict`: a missing, empty or unreadable `## Purpose` becomes "TBD - created by archiving change ...", which nobody replaces, and a `TBD` or `TODO` placeholder, or a Purpose under 50 characters, is copied as written. Write what the capability is for under `## Purpose` in the delta. Check: a delta's `## Purpose` for an existing capability differs from the spec's, which archive ignores. Runs with the archive, so not without the CLI |
| `citation` | error, or check | A `path:line` with a `/` whose line is in neither the base branch nor the change is an error. Any other citation finding is a check: a bare name such as `config.py:50`, or a line only the change adds. Text in a code fence, and addresses such as `0.0.0.0:8080`, are skipped |
| `openspec-validate` | error, or check | An issue `openspec validate --strict` reported, at its line and in its words, such as a section or text above the first `##` that the archive drops, or a requirement under a misspelt or other section. An ERROR is an error; a WARNING, an error when validation failed and a check when it passed; an INFO note, a check. To the INFO note for a `###` delta heading that is not a requirement header, spec-check adds where the rule goes: under MODIFIED when the specs have its title, else ADDED |
| `openspec-show` | error, or check | `openspec show` cannot read a change's deltas or a main spec, so no requirement check read it. A main spec is a check when only changes are checked |
| `stack` | error, or check | A `Builds on:` line or its dependency is wrong or stale. See [Stacked changes](#stacked-changes) for each case |
| `drift` | error, or check | A stacked change disagrees with what its dependencies now say. See [Stacked changes](#stacked-changes) |
| `evolution` | error | A line in the change's files, or a line the branch changes in a decision record, records history, not what holds now (see [Decisions and open questions](#decisions-and-open-questions)). It quotes the line. Text in a code fence, backticks or double quotes is skipped |
| `kept` | error, or check | An entry in a `.spec-check-kept` file is malformed, unasked or stale, or the file cannot be read, as [Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags) describes |
| `rationale` | check | A requirement in a change holds more than its SHALL statement and one *because* sentence. Move reasoning with evidence to a Rationale entry in the capability's decision record, and the rest to design.md (see [Decision records](#decision-records)) |
| `record` | error, or check | Error: a decision record departs from its form, such as a Rationale entry with no *Evidence*, or one whose title names no requirement in force or in an open change, or names one an open change removes or renames away (reported at the record and at the change's delta line); or a change holds its own `decisions.md`. A *Paths* entry the tree lacks is an error, or a check while an open change touches the capability, since its implementation may add it. Check: *Because* or *Lost because* runs past one sentence, or *Evidence* or *Lost because* links nothing |
| `config` | error | `openspec/spec-check.yaml`, which sets where decision records live, holds a line that is not `key: value`, a key other than `decision-records`, a second `decision-records` line (the first stays in force), or a record path that breaks the rules in *Decision records*. The rest of the file is still read; with no usable `decision-records` line, records are at the default `openspec/specs/<capability>/decisions.md` |

A **check** is a heuristic: judge it, and fix it or leave it. An `openspec
archive` or `openspec validate` result of "not run" never means it passed;
say so in your report.

`--no-validate` skips `openspec validate --strict`: its result reads
`not run (--no-validate)` and no `openspec-validate` finding appears, not
even about sections the archive drops. Every other check still runs,
including the archive, which only a missing or older CLI skips.

Citations are checked against the base branch: by default `origin/HEAD`, then
`origin/main`, then `main`. Pass `--base` when the change targets another
branch.

### Archive refusals

`check` copies the tree's specs into a temporary directory and archives the
checked change into the copy with the real `openspec archive`; the tree
itself is never touched. No other open change is archived with it, except
that a stacked change goes on top of its dependencies (see
[Stacked changes](#stacked-changes)). Each
refusal is an `archive` error at the requirement it is about, or at line 0
of the delta file when it is about the file as a whole. OpenSpec stops at
its first refusal, so fix it and run `check` again to see the next.

Without OpenSpec 1.16.1 or later, an unstacked change gets the line
`openspec archive (<change>): not run`, saying why; a stacked one, a `stack`
error.

## Stacked changes

A change is **stacked** when it applies on top of another open change, not on
main alone. Declare it when the change modifies, removes, renames or relies on
a requirement that another open change adds, renames or rewrites.

Write one line per dependency in `proposal.md`, right after its `#` title and
before `## Why`:

```markdown
# Lore search

Builds on: seat-files (adamstallard/igor#171)

## Why
...
```

The syntax is exactly `Builds on: <change> (<owner>/<repo>#<number>)`, alone
on its line with no markup: the change's directory name under
`openspec/changes/`, then its pull request in the same repository. When this
change builds on B and B on C, list C's line first, then B's, the order they
apply to main. You may delete C's line only once your tree holds C's result,
as it does after C merges and you merge main.

`check` and `sign` read each dependency from its pull request's head commit
(`gh pr view` and `git fetch`; nothing is checked out), so stacked changes
need `gh`, the network and OpenSpec 1.16.1 or later. By the pull request's
state:

- **Open, or closed without merging.** In line order, `check` archives each
  into a temporary copy of your tree's specs with one run of the real
  `openspec archive`, first dropping the deltas the copy already shows: an
  addition or modification with the same text, a removal already absent,
  and a delta's renames when, read in order, all are done. An addition
  already in your tree with another text keeps your tree's text, with a
  `drift` check.
- **Merged.** Its result is in main, so `check` never archives it again but
  looks for it in your tree by requirement name: each requirement it adds
  or modifies there, with any text (main may have reworded it), each it
  removes absent, and its renames, read in order, done. `check` allows
  for a later merged dependency, one listed after it or building on it: a
  name the later one removes or renames away need not be there, and a name
  it adds or renames onto need not be absent. A merged dependency
  whose change directory is still under `openspec/changes/` in your tree
  with the same deltas, not yet archived, is handled as an open one.

The change itself is archived last, and every check runs against the
result. A refusal on a line where a `drift` error
already sits is not reported again.

**`stack` errors.** Each blocks; none is a pass:
- a `Builds on:` line that cannot be read or is listed twice, or a change
  that names itself;
- the OpenSpec CLI missing from PATH, or older than 1.16.1;
- a dependency that cannot be read, or a delta in it where `openspec show`
  reads nothing;
- a pull request that holds no change of the name on the line: the line
  names the wrong change or the wrong pull request;
- deltas `openspec archive` refuses, where the error quotes the CLI and
  names the dependency;
- a merged dependency whose result your tree lacks, naming what is missing:
  merge main into your branch;
- a dependency that builds on a change this one does not list before it,
  whose result your tree lacks.

After any `stack` error, the duplicate and drift checks skip the change,
and the error says so; the other checks still run.

**`stack` checks:**
- a dependency whose result your tree already holds: remove its line;
- an open or closed dependency only partly there, naming which deltas were
  there and which were archived;
- two dependencies that set the same requirement, where the later, whose
  version wins, does not build on the earlier: make sure the later text
  includes what your change needs;
- a pull request closed without merging, since its change may never land.

**`drift`.** An error when your change modifies, removes or renames a
requirement that main plus its dependencies no longer define. A check,
quoting both texts, when a requirement a dependency adds is already in your
tree with another text, or when your change keeps a sentence from an earlier
text of the dependency's requirement: restate the requirement from the
dependency's current text, or leave a sentence you kept on purpose.

**The hint.** A `duplicate` error against a main requirement that an open
pull request removes or renames ends with the line to add, for example:
``add `Builds on: seat-files (adamstallard/igor#171)` to its proposal.md``.
Only that line clears the error. Add it if your change really applies on
top of that pull request; if not, the duplicate is real: state the rule
once.

## 2. The consistency read, by a fresh subagent

Once per round, at its end, each **due** change gets a read of the whole
change. A change is due when the branch adds or edits it, or edits the
decision record of a capability it touches, and it differs from its **last
read**: the newest commit in the branch's history whose `Spec-check:`
trailer records a read that names it (see [Commit](#commit)). A decision
record the branch edits, for a capability no open change touches, is due on
its own the same way, named by its path. To see what is due, run `sign
--read subagent` on the staged tree and throw the value away: it names
them, or says `no read due`. `--amended` and `--open` default to 0, so this
value says `0 amended, 0 open`. After the read, run it again with the counts (see
[Commit](#commit)) to sign the commit.

For each due change, start a general-purpose subagent (not Explore) that
did not write the change. Don't read [consistency-read.md](consistency-read.md)
yourself: a main loop that has read it tends to paste it, condensed, into the
prompt, and the subagent then works from your copy. Tell the subagent to
read that file, by its absolute path, as its brief and to follow it exactly,
and give the values of its five placeholders:

- the change's directory;
- where to read it from (the working tree, or the pull request's branch);
- its base branch;
- every file under the change's directory (`git ls-files
  openspec/changes/<change>`, or `git ls-tree -r --name-only <ref>
  openspec/changes/<change>`);
- the decision records it must agree with, as `python3 "$SC/spec_check.py"
  records <change>` prints them (add `--ref <ref>` for a branch): each
  touched capability's main record, and each record whose *Paths* match a
  file the branch changes; a record the branch edits is read with its diff
  against the merge base.

For a record due on its own, name the brief's *A record read on its own*
section and give that section's three values instead: the record's path,
where to read it from, and its base branch. The brief tells the subagent to
read each listed file whole. Add nothing else to the prompt: no pasted
files, and no summary of the change. A summary is your own reading, and the
subagent is there to read the change without yours.

The subagent reads the change against every spec on the base branch, the
listed records, every open change, every open pull request touching the
same specs, and the repository's architecture docs, quoting both sides of
each finding, including a rejected approach brought back or a recorded
constraint broken. For a stacked change, main plus
the dependencies is the base.

If no subagent can be started in this environment, do the read yourself from
the same brief, and say in your report and in the trailer (`--read self`)
that the author did it.

## 3. Fixing

- **Amend the spec itself.** Never answer a finding in a pull request comment:
  `gh pr view` shows the body without comments, and an implementer builds from
  the spec. Comment to think out loud; amend to decide.
- **A question only a person can decide** goes into design.md's *Open
  Questions*.
- **A conflict with another change or pull request** is reported, not edited:
  name it, quote both sides, and leave the other change alone.
- **A fact nobody has measured** becomes a task in tasks.md and an entry
  in design.md's *Open Questions*, and the requirement built on it says what
  happens when it turns out false.

Run the mechanical checks again after amending.

## Decision records

**A record holds only what a test can't express: a rule no test can check,
and the evidence for why a rule exists or why an alternative lost.**
Whatever a test can express is a requirement with a scenario, including a
rejection or constraint a test can check: to turn down an approach a test
could catch, add a scenario that fails if the approach is used, under the
requirement that approach would break. Create the record if the capability
has none. Later changes and their consistency reads read the record; they
never read an archived change's design.md, so nothing there binds them.

**Every entry needs evidence, never invented:** a failure (the bug or
incident itself, linked; a link to its regression test may follow), a
measurement (an experiment someone ran) or an outside fact. A test alone,
the requirement's own included, is never Evidence: it shows the rule is
enforced, not why it is needed. Every *Evidence* line
and every *Lost because* line ends in a link: a URL, an issue or pull
request, a commit, or a markdown link to a file. Reasoning without evidence,
however sound, is not an entry: it goes in the change's design.md or a pull
request description.

Each entry is stated as it stands now, with no history:

- **Constraint:** a rule the code must keep that no test can check, such as
  a cost policy or a choice of tool. Its *Because* line, required, gives the
  reason in one sentence. Its *Holds while* line names the condition that
  keeps it in force, so a later reader can tell when it no longer holds.
- **Rationale:** a reason for a requirement, in the record of that
  requirement's capability: what goes wrong without the requirement,
  including why an alternative its scenario guards against was turned down.
  A reason with evidence is a Rationale entry however short.
- **Rejected:** an alternative no test could catch, so no requirement guards
  against it. A broad class is fine ("Rejected: network calls of any
  kind"). *Lost because* is a reason a later reader can check, never a
  person or a preference.

A rejection a requirement guards against (the rejected approach would fail
that requirement's scenario) is written as that scenario. With evidence, its
reasoning and Evidence go in the requirement's Rationale entry, created if
there is none; without, the reasoning goes in the change's design.md or a
pull request description.

A requirement's optional *because* sentence, one plain line inside or right
after its SHALL statement, helps a reader. With no place for Evidence, it
never stands in for a Rationale entry, and may sit beside one.

**A record never repeats a requirement.** Cut a Constraint or Rejected
entry whose rule a requirement or scenario already states (any evidence it
has belongs in that requirement's Rationale entry); a Rationale entry names
its requirement and never restates the rule. Item 16 of the consistency
read's checklist (consistency-read.md) flags a repeat.

**Noise is cut:** reasoning that names who decided, states a preference, or
is a generic principle (keep it simple, and the like). Before cutting it,
the agent writing the change may ask whoever decided for evidence that would
make it a proper entry; item 17 of the checklist flags noise in the round
it appears, while that person can still be asked.

A pull request that finds a piece of an entry's evidence failed (its link
no longer resolves, or it is disproved) removes that piece. Delete an entry
when no sound evidence is left or it no longer holds: its *Holds while*
condition has ended, its *Lost because* no longer applies, or its
requirement is gone. Give each deletion's reason in the pull request
description and the commit message, never in the record or design.md, since
it is history. Rewording an entry is not a deletion: it needs no reason, and
the entry keeps its evidence.

```markdown
# <capability>: constraints, rejected alternatives and rationale

## Constraints
- **Constraint: <the rule, in the words a proposal would use>.**
  Because: <one sentence>.
  Evidence: <a failure, a measurement (value, how, date) or an outside fact>, <link>
  Holds while: <the condition under which it still holds>.
  Paths: <files or areas it governs>

## Rejected
- **Rejected: <the approach, named as someone would propose it>.**
  Facing: <the problem it tried to solve>.
  Lost because: <one sentence>, <link to the failure, measurement or outside fact>.
  Instead: <what was chosen>.
  Paths: <files or areas it governs>

## Rationale
- **Rationale: <the title of the requirement it explains>.**
  <the reasoning, on the lines after the bold line>
  Evidence: <a failure (the bug or incident itself, linked; its regression test may follow as a pointer), a measurement (an experiment someone ran) or an outside fact>, <link>
```

A Rationale entry's bold title ends in a period of its own. Less that
period, it equals the exact title of a requirement in force (in
`openspec/specs/`) that no open change removes or renames, one an open
change adds or modifies, or the new title an open change renames one to. So for a requirement
whose title ends in a period, the entry's title ends in two. An open change is any change folder under
`openspec/changes/` in the pull request branch's tree, including one whose
pull request has merged but which is not yet archived. `check` reports any
other title as an error, suggesting the exact title when one matches
ignoring case, spacing, backticks and a closing period; so when an open
change removes or renames away a requirement, delete its entry or retitle
it. A Rationale entry needs at least one *Evidence* line; all come last,
after the reasoning, which has no blank line inside it. In every kind of
entry, any labelled part (*Because*, *Evidence*, *Paths* and the rest) may
wrap onto indented lines, with no blank line before a continuation.

- **Paths**, required in Constraint and Rejected entries and absent from
  Rationale entries, is a comma-separated list of files, directories
  (`src/store/`) or globs (`src/**/*.go`).
  List the files where a change could break the rule or bring back the
  rejected approach: a branch that changes any of them has the entry checked
  and read with it (sections 1 and 2). Without Paths, an entry has no
  trigger and silently guards nothing.

- **Where.** The record is at `openspec/specs/<capability>/decisions.md`,
  unless `openspec/spec-check.yaml` says otherwise, in one line such as
  `decision-records: openspec/decisions/<capability>/decisions.md`. The
  path must be under `openspec/` and outside `openspec/changes/`;
  `<capability>` must fill a whole folder name in the path, and directly
  inside that folder comes a fixed file name, such as `decisions.md`. Every
  file the pattern matches is a record. spec-check refuses any symlink
  under `openspec/`, because it reads records from git trees, where a
  symlink holds only its target's name; keep the record a real file.
  A Constraint or Rejected entry is written out in full in the record of
  each capability it concerns, never linked, because a later change reads
  only the records of the capabilities it touches.

- **Edit it in the pull request.** A pull request that adds or changes a
  recorded decision edits the real record of each capability it concerns, beside the
  change's deltas; `check` refuses a `decisions.md` inside a change. Reviewers see the real diff, and two branches editing one
  entry conflict. Editing a record makes each open change
  with a delta spec for that capability due for a consistency read before
  review (section 2); with no such change, the record itself is due and is
  read on its own. `openspec archive` never touches a decisions.md, so
  archive the change as usual; the record stays where it is.

## Decisions and open questions

Write a decision as a testable requirement and scenario. Failing that,
write it as a [decision record](#decision-records) when evidence supports
it. Otherwise, write it either in design.md or in a pull request
description. design.md is archived with its change and never read again. It
never restates a record entry, though it may link to one.

design.md's *Decisions* section states each of the change's other decisions
once, as it stands now: design choices that are not record material, and
reasoning without the evidence a record entry needs. Its *Open Questions*
section holds each undecided item. OpenSpec's design.md instructions name
both sections; create design.md when the change has none. When a
decision changes, rewrite its *Decisions* entry and keep no trace of how it
was amended: git and pull request comments hold the history. proposal.md
holds no decisions either: it stays OpenSpec's one or two pages of Why and
What Changes.

An `evolution` error marks each line of a change's files, and each line a
branch changes in a decision record, that records history: an amendment
("amending decision 79"), a credit ("(Adam, 2026-10-21)", "Adam decided"),
an earlier draft, or a review round ("this push", "since review"). A
decision record skips the credit rules, since its Evidence names products,
standards and dated runs that would read as credits; a credit there is the
consistency read's job (item 17). The other history rules still apply to a
record, so "amended by Adam" still errors, because of "amended". Restate the
line as what holds now, or delete it. When you believe `check` flags a line
wrongly, don't reword it to get past the check: ask a person whether to fix
or keep it, as described in [Keeping a line the evolution check
flags](#keeping-a-line-the-evolution-check-flags).

## When to write a TLA+ model

Write one when a requirement is about concurrency, ordering, a crash between
two writes, or a protocol between processes. Other requirements do not get
one. This skill does not write models for you.

- **Where:** next to the spec, as
  `openspec/specs/<capability>/model/<Name>.tla` with `<Name>.cfg` for TLC.
- **Mapping:** each invariant's comment names the requirement it proves,
  by its exact `### Requirement:` title. A requirement the model cannot
  express says so in the spec.
- **CI:** run TLC on every model in the repository's CI:

  ```yaml
  - run: curl -sLO https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar
  - run: |
      for cfg in openspec/specs/*/model/*.cfg; do
        java -cp tla2tools.jar tlc2.TLC -workers auto -config "$cfg" "${cfg%.cfg}.tla" || exit 1
      done
  ```

## Commit

After the last fix and the final `git add`:

```sh
python3 "$SC/spec_check.py" sign --read deferred                            # inside a round
python3 "$SC/spec_check.py" sign --read subagent --amended <n> --open <n>   # the round's last commit
```

It runs the mechanical checks on the staged tree and refuses when any error
remains. Otherwise it prints `Spec-check: ✓ <tree> ...`, a value bound to the
staged tree, ending with what it records of the consistency read:

- `read deferred to the round's end`, from `--read deferred`, on a commit
  inside a round;
- `read by a fresh subagent: <change>, <change>; 3 amended, 1 open`, from
  `--read subagent`, on the commit that ends the round. It names every due
  change and the path of every record due on its own, and records that the
  read covered each at this tree. `--amended` counts the read's amendments;
  `--open`, the open questions the due changes' design.md files now list,
  added together. `--read self` writes `read by its author, no subagent:
  ...`;
- `no read due`, whichever `--read` is given, when no change is due.

An older value, `read by a fresh subagent; ...` with no names, counts as a
last read of every change its commit touched, when deciding which are due.

`evolution` errors a person chose to keep
([below](#keeping-a-line-the-evolution-check-flags)) are counted in the
value whatever the `--read`, and editing the kept file makes the change due
like any other edit.

Stage the read's amendments with the rest of the round's last commit,
which may be a code commit: while a change is due, `sign --read subagent`
signs a commit that changes nothing under `openspec/` and records the read
there. If the round's last commit is made but not pushed, undo it with
`git reset --soft HEAD~1`, do the read, and commit again. Never rewrite a pushed commit: commit the read's amendments as
a new commit signed with `--read subagent`, or, if it amends nothing, record
it on an empty commit, signed with nothing staged, as below.

**The hand-back checks.** A hand-back is `gh pr create` (not a draft, unless
it requests a review), `gh pr ready`, `gh pr edit --add-reviewer`, or the
GitHub MCP's equivalents. Each is judged at the pull request's head on
GitHub, so push the read before you hand back:
- A hook blocks one that names its pull request (`gh pr ready 7 -R o/r`,
  or its URL) while a change there was edited after its last read.
- After the call, the hook judges a command that holds just that one gh
  call and no `$`, backtick, glob, brace or leading `~` in any word, with
  no variable assigned but `GH_REPO`. Beside a hand-back that names its pull
  request by number or URL (`gh pr ready 12`), only `git`, `cd`, `echo`,
  `printf`, `true` or `sleep` may stand. Beside one that names none
  (`gh pr create`, or `gh pr ready` by branch), only `git push`, `git add`
  and `git commit` with plain options, `cd`, `true` or `sleep`. If a change
  is unread, the hook makes the pull request a draft again, withdraws the
  review requests the call made, and tells you. Any other form gets a
  note saying why it was not checked, without blocking; to have it checked, run `gh pr ...` alone or with only those programs beside it.
- Where the repository has spec-check's GitHub workflow, it does the same
  for every hand-back, however it was made.

Either way: do the read, commit with `--read subagent`, push, and hand back
again. Neither sees a hand-back in conversation, so before telling a person the
work is ready, run `sign --read subagent` with nothing staged. With nothing
staged and no read due, there is nothing to sign, so it refuses: it exits 1
saying `nothing waits for its consistency read` on stderr. That refusal is
the result you want. If it signs instead, a read is due: do it first.

**Setting up a repository.** When it has `.github/workflows/`, offer to add
spec-check's workflow: `python3 $SC/spec_check.py setup-ci` writes
`.github/workflows/spec-check.yml`, pinned to a commit on
shared-skills' main that holds the newest change to both this script and
the workflow template (`ci/spec-check.yml`), so that the workflow's steps
match the script each run downloads. When one of the two newest commits
that changed them is in the other's history, the pin is the later one.
When they came from branches merged separately, neither holds the other's
change, and the pin is the first commit on main's first-parent line whose
history holds both, usually the second merge.
setup-ci reads the pin and the template from GitHub, so gh must be
installed and signed in. Commit it, and suggest making the `spec-check` check required
in the base branch's protection rules.

When it has `openspec/config.yaml` and its agents write changes through
OpenSpec's /opsx skills, offer to merge the `rules:` block of
[opsx-rules.yaml](opsx-rules.yaml) into that file's `rules:` by hand.
OpenSpec shows them to the agent writing each artifact, even one that never
loads this skill; they advise, and the checks and the read enforce.

Without OpenSpec 1.16.1 or later, `sign` still signs an unstacked change,
and the value says `show, validate and archive not run (install OpenSpec
1.16.1 or later)`; it refuses a stacked one.
For work in progress, skip `sign` and write the value yourself: `skipped
(<reason>)`. A skip note records no read.

Commit once, carrying the trailer of every installed skill that asks for
one, such as Prose, Bug-hunter and Spec-check. Each trailer goes in as a
`--verified-value` family: the script that verifies it, its key, and its
value; for spec-check, the value is the text after `Spec-check: `. The
example goes through bug-hunter's commit script, `$BH`, with prose's scripts
directory as `$S`; bug-hunter's and prose's SKILL.md say where each is. After
the `--` come bug-hunter's own arguments: the message file, its `Bug-hunter:`
value, and the co-author.

```sh
"$BH" --verified-value "$S/verify-staged.sh" Prose "✓ 4d593e935186:9138830a72a2" \
      --verified-value "$SC/verify-staged.sh" Spec-check "✓ 4d593e935186 0 errors, 1 checks; validate passed; read by a fresh subagent: keep-action-log; 3 amended, 1 open" -- \
  -F msg.txt "skipped at triage (spec only, no code)" "<co-author>"
```

For the empty commit, pass `--allow-empty` first: `"$BH" --allow-empty
--verified-value ... -- -F msg.txt "skipped at triage (no change)"
"<co-author>"`.

Without bug-hunter, call the library directly with the same families (and
`--allow-empty` among its options for an empty commit):
`$SC/../../../lib/commit-trailer/commit-with-trailers.sh <families>
--co-authored-by "<co-author>" --message-file msg.txt --`.

Sign after prose's rewrite is staged: staging anything after signing changes
the tree, and the commit script refuses the stale value.

The commit hook reports a commit that changes `openspec/` without a valid
`Spec-check:` trailer, and never one that changes nothing under `openspec/`.

### Keeping a line the evolution check flags

The same words can describe behaviour ("Each new vote amends the
decision.", in a spec for a voting system), so an `evolution` error can be
wrong. When you believe one is, don't reword the line; a person decides.

1. Ask a person one question per line through your host's interactive
   picker (in Claude Code, the `AskUserQuestion` tool): show the line, the
   error, and why you think it is not history, with two options. "Fix it":
   restate the line as what holds now and restage. "Keep as is": the line
   stays as written.
2. Add an entry for each kept line to the kept file, and stage it: the
   change's `openspec/changes/<name>/.spec-check-kept`, or for a line in a
   decision record, `.spec-check-kept` beside the record (such as
   `openspec/specs/<capability>/.spec-check-kept`), whether or not an open
   change touches the capability. Committed with your branch, it shows a
   reviewer who runs `check` the line as kept, not as an error. An entry
   names the file, relative to the kept file's folder, and quotes the
   flagged line between `«` and `»`:

   ```text
   design.md: «The spec narrows the decision.» kept (asked): compares the spec with a decision, not history
   ```

   The quote is the whole line without its indent, copied from the file,
   since the error cuts long lines short; runs of spaces or tabs count as
   one space. The entry keeps every `evolution` error in that file whose
   line has that text, so it lapses only when the line changes. Blank lines in
   the kept file are skipped. `(asked)` is your statement
   that a person answered; the script cannot check it.
3. Sign. The kept errors no longer fail the run, and the value counts them:
   `Spec-check: ✓ <tree> 0 errors, 1 checks, 1 evolution kept; ...`, so
   the override shows in git.

A `kept` error is an entry not in that form, with no reason, or quoting
the same line as an earlier entry; one that matches an `evolution` error but
lacks `(asked)` (see *When you cannot ask*, below); or a kept file that
cannot be read. An entry whose line changed or is gone keeps nothing and is
a `kept` check, with or without `(asked)`: remove it, and if the new text is still flagged, ask about
it. `openspec archive` moves a change's kept file with the rest of the
change into `openspec/changes/archive/`, where spec-check does not read it.
Editing a record's kept file makes the same read due as editing the
record.

**When you cannot ask** (you are a subagent or a background job, or your
host has no picker), don't commit. Write each entry you would keep without
`(asked)`, as `<file>: «<line text>» kept: <reason>`, stage it, and run
`sign`: its refusal names each such entry with the errors it matches and
your reason. Leave the change staged and put that refusal, whole, in your
result. Whoever receives it asks the person, adds `(asked)` to each entry
kept, fixes the other lines and deletes their entries, and signs again.

## Current-state passes

When docs, or a pull request's body and title, may still describe an
earlier state, a hook prints `current-state pass due for: ...`, naming what
to rewrite. Rewrite each to the state as it now is without asking first;
ask a person only before dropping a conclusion, as `prose compact` does.

- **The implementation lands on a spec branch:** the commit hook prints it
  when a commit adds a file under a `src/` directory while the branch adds
  or edits an open change (on the base branch itself, every open change
  counts). Rewrite the change's
  proposal.md and design.md, and the pull request's body and title,
  wherever they say "specification only", or "will" for what is now built.
- **A change is archived:** the commit hook prints it when a commit moves
  the change into `openspec/changes/archive/`, as `openspec archive` does. This is a safety
  net behind item 15 of consistency-read.md, which already flags record
  material in design.md. Move anything still in the change's design.md that
  belongs in a decision record into the record of each capability it
  concerns, under the rules of any record edit (see *Decision records*):
  - a Rationale entry for reasoning about one requirement, with its
    Evidence;
  - a Constraint entry for a rule the code must keep that no test can
    check, with its Evidence. A principle behind several requirements is
    such a rule: each requirement's test checks only that requirement,
    never the principle itself. With evidence of its own, it is one
    Constraint entry, not a Rationale under each requirement. Without
    evidence of its own, it is not an entry. It may still be added as
    reasoning to the Rationale entry of each requirement that guards
    against what it rules out, beside the Evidence that entry already has;
    otherwise it is left out;
  - a Rejected entry, linking its evidence, for an alternative turned down
    that no requirement guards against. This includes a limit or trade-off
    the design accepts: the entry rejects the fix that would have removed
    it (for example "Rejected: preventing
    duplicate asks across machines", with "Instead: duplicates are
    accepted").

  Everything else stays in the archived design.md, such as how the design
  was reached, rollout steps, overviews of the code, open questions, and
  anything without Evidence or too slight for a later reader to act on. Then run `prose check` on each file you
  changed, and compact any it reports as due.
- **A pull request is handed back for review:** prose's hook prints it
  after the agent's hand-back, and the GitHub workflow as a notice when a
  hand-back leaves no change unread. Fix each doc the pull request changes,
  and its body and title, wherever it still describes work as unfinished or
  to come.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec archive` and `openspec validate` results), who did the consistency
read and which changes it covered, or that it is deferred to the round's
end, the findings and what each became (amended, open question, reported to
another change), and anything not checked.
