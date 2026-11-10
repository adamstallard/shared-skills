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
  itself. Commits that change openspec/ carry a Spec-check: trailer.
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

Checking a change, by name or as one of every open change, also checks the
decision records under `openspec/specs/` (see
[Decision records](#decision-records)) that the change bears on. `sign`,
which signs a commit (see [Commit](#commit)), checks the same records for
each change under `openspec/changes/` that the commit stages:

- the record of each capability the change touches;
- each record whose *Paths* line, which lists the files the record governs,
  names a file the branch has changed since it left the base branch;
- each record the branch edits, or whose kept file the branch edits (the
  `.spec-check-kept` file beside the record; see
  [Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags)).

`check` and `sign` cover the same records, so one run of `check` finds every
record error that would make `sign` refuse the change's commit. A commit
that stages a record makes `sign` check every record, so before such a
commit run `check specs` too.

A shallow clone may hold too little history to reach the commit where the
branch left the base branch. Then no one can tell which lines of a record the
branch changed. So `check` and `sign` skip the `evolution` check, which flags
lines that record history, on that record, and report a finding of severity
`check` saying so. Run `git fetch --unshallow` to fetch the full history so
the record's changed lines are checked.

**spec_check.py needs OpenSpec 1.16.1 or later on PATH** (`npm install -g
@fission-ai/openspec`), and reads specs and deltas only through it:
`openspec show --json` for requirements, `openspec validate --strict --json`
for what a delta drops or misfiles, `openspec archive --json` for whether a
change applies. Without it, each check that needs a requirement reports
`not run: install OpenSpec 1.16.1 or later` and why, such as `(this one is
1.14.3)`. Citations, the check that each `Builds on:` line can be read, and
the `renamed-block` scan still run, and a stacked change gets a `stack`
error.

| Kind | Severity | What it means |
| --- | --- | --- |
| `no-scenario` | error | A requirement states a SHALL or MUST and has no scenario |
| `renamed-block` | error | A `###` heading under `## RENAMED Requirements` with anything under it besides FROM and TO lines. `openspec archive` drops the rest without saying so. Restate the requirement under `## MODIFIED Requirements` with its new name |
| `title-reuse` | error | Within one change, one exact title is both removed or renamed from and added or renamed to, as in a swap, a chain, or a rename plus a new requirement under the old title. spec-check doesn't support reusing a title within one change. Split it into two changes, the second with a `Builds on:` line for the first (both can sit in one pull request), or choose another title. A near-duplicate differing in case or spacing from a requirement that stays is left to `openspec archive`, which refuses a name that differs from an existing one only in case or spacing |
| `scenario-incomplete` | error | A scenario has no WHEN or no THEN |
| `duplicate` | error | A sentence of the rule also appears under another requirement, here or in another spec or change. Two requirements with one name may share sentences only when one is a MODIFIED requirement in the other's capability |
| `archive` | error | `openspec archive` refuses the change: an ADDED requirement whose name is already there, a RENAMED onto a name already taken, a MODIFIED that drops a scenario, or a requirement modified, removed or renamed that is not there. The error quotes the CLI. See [Archive refusals](#archive-refusals) |
| `purpose` | error, or check | Error: a delta creates a capability (no spec in main or in what the change builds on), and the Purpose `openspec archive` would give the new spec fails `openspec validate --strict`. A missing or empty `## Purpose`, or one that would leave the new spec unreadable, becomes "TBD - created by archiving change ...", which nobody replaces; a `TBD` or `TODO` placeholder, or a Purpose under 50 characters, is copied as written and fails the same way. Write what the capability is for under `## Purpose` in the delta. Check: a delta's `## Purpose` for an existing capability differs from the spec's; archive ignores it. Runs with the archive, so not without the CLI |
| `citation` | error, or check | A `path:line` with a `/` whose line is in neither the base branch nor the change is an error. Any other citation finding is a check: a bare name such as `config.py:50`, or a line only the change adds. Text in a code fence, and addresses such as `0.0.0.0:8080`, are skipped |
| `openspec-validate` | error, or check | An ERROR is an error; a WARNING is an error when validation failed, a check when it passed; an INFO note is a check. An issue `openspec validate --strict` reported, at OpenSpec's line and in its words: for example a section or text above the first `##` that the archive drops, a requirement under a misspelt or other section, or (an INFO note) a `###` heading in a delta that is not a requirement header. To that note spec-check adds where the rule goes: under MODIFIED when the specs already have its title, under ADDED when they do not |
| `openspec-show` | error, or check | `openspec show` cannot read a change's deltas or a main spec, so no requirement check read it. A main spec is a check when only changes are checked |
| `stack` | error, or check | A `Builds on:` line or its dependency is wrong or stale. See [Stacked changes](#stacked-changes) for each case |
| `drift` | error, or check | A stacked change disagrees with what its dependencies now say. See [Stacked changes](#stacked-changes) |
| `evolution` | error | A line in the change's files, or a line the branch changes in a decision record, records history, not what holds now (see [Decisions and open questions](#decisions-and-open-questions)). It quotes the line. Text in a code fence, backticks or double quotes is skipped. A decision record skips the rules for credits to a person or a date; the other history rules still apply to it, so "amended by Adam" still errors there, under the amendment rule |
| `kept` | error, or check | An entry in a change's `.spec-check-kept` file is malformed, unasked or stale, or the file cannot be read. See [Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags) |
| `rationale` | check | A requirement in a change holds more than its SHALL statement and one *because* sentence. Move reasoning with evidence to a Rationale entry in the capability's decision record, and the rest to design.md (see [Decision records](#decision-records)) |
| `record` | error, or check | Error: a decision record departs from its form (including a Rationale entry with no *Evidence*); a Rationale entry names no requirement in force or in an open change; a record keeps a Rationale entry for a requirement an open change removes or renames away (reported at the record and at the change's delta line); or a change holds a `decisions.md` of its own. A path in *Paths* that the tree lacks is an error, and a check while an open change touches the capability, since its implementation may add it. Check: *Because* or *Lost because* holds more than one sentence, or *Evidence* or *Lost because* links nothing |
| `config` | error | `openspec/spec-check.yaml`, which sets where decision records live, holds a line that is not `key: value`, a key other than `decision-records`, a second `decision-records` line (the first stays in force), or a record path that breaks the rules in *Decision records*. Each is an error that fails the run, and spec-check reads the rest of the file without that line; with no usable `decision-records` line, records are read at the default `openspec/specs/<capability>/decisions.md` |

A **check** is a heuristic: judge it, and fix it or leave it. An `openspec
archive` or `openspec validate` result of "not run" means it was not
checked, never that it passed; say so in your report.

`--no-validate` skips the `openspec validate --strict` run: its result reads
`not run (--no-validate)` and no `openspec-validate` finding appears, not
even about sections the archive drops. Every other check still runs,
including the archive, which only a missing or older CLI skips.

Citations are checked against the base branch: by default `origin/HEAD`, then
`origin/main`, then `main`. Pass `--base` when the change targets another
branch.

### Archive refusals

`check` copies the tree's specs into a temporary directory and archives the
checked change, and only that change, into the copy with the real `openspec
archive`; a stacked change goes on top of its dependencies (see
[Stacked changes](#stacked-changes)). The tree itself is never touched. Each
refusal is an `archive` error at the requirement it is about, or at line 0
of the delta file when it is about the file as a whole. OpenSpec stops at
its first refusal, so fix it and run `check` again to see the next.

Without OpenSpec 1.16.1 or later on PATH, an unstacked change gets the line
`openspec archive (<change>): not run`, saying why; a stacked one gets a
`stack` error.

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
`openspec/changes/`, then its pull request in the same repository. For a
chain, where this change builds on B and B builds on C, list both in the
order they apply to main: C's line first, then B's. You may leave out C's
line only once your tree holds C's result, as it does after C merges and you
merge main.

`check` and `sign` read each dependency from its pull request's head commit
(`gh pr view` and `git fetch`; nothing is checked out), so stacked changes
need `gh`, the network and OpenSpec 1.16.1 or later. Each dependency is
handled by its pull request's state:

- **Open, or closed without merging.** In line order, `check` archives each
  into a temporary copy of your tree's specs with one run of the real
  `openspec archive`, first dropping the deltas the copy already shows: an
  addition or modification with the same text, a removal already absent,
  and a delta's renames when, read in order, all are done. An addition
  already in your tree with another text keeps your tree's text, with a
  `drift` check.
- **Merged.** Its result is in main, so it is never archived again; `check`
  looks for it in your tree by requirement name. Each requirement it adds
  or modifies must be there, with any text (main may have reworded it), each
  it removes absent, and its renames, read in order, done. When a later merged
  dependency, listed after it or building on it, removes or renames away
  one of those names, the name need not be there; when the later one adds
  or renames onto it, it need not be absent. A merged dependency whose
  change directory is still under `openspec/changes/` in your tree with the
  same deltas, not yet archived, is handled as an open one.

The change itself is archived last, on top of its dependencies, and every
check runs against the result. A refusal on a line where a `drift` error
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

After any `stack` error, the duplicate and drift checks do not run for the
change, and the error says so; the other checks still run.

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
text of the dependency's requirement. If your change was written against the
earlier text, restate the requirement from the dependency's current text. If
you kept the sentence on purpose, leave it.

**The hint.** A `duplicate` error against a main requirement that an open
pull request removes or renames ends with the line to add, for example:
``add `Builds on: seat-files (adamstallard/igor#171)` to its proposal.md``.
Add it if your change really applies on top of that pull request; if not,
the duplicate is real: state the rule once. Only the line clears the error.

## 2. The consistency read, by a fresh subagent

Once per round, at its end, each **due** change gets a read of the whole
change. A change is due when the branch adds or edits it, or edits the
decision record of a capability it touches, and it differs from its **last
read**: the newest commit in the branch's history whose `Spec-check:`
trailer records a read that names it (see [Commit](#commit)). A decision
record the branch edits, for a capability no open change touches, is due on
its own the same way, named by its path. To see what is due, run `sign --read subagent` on the staged tree:
the value it prints names them, or says `no read due`. Nothing commits that
value, so throw it away; without `--amended` and `--open` it says `0
amended, 0 open`. After the read, run it again with those counts (see
[Commit](#commit)) to sign the commit.

For each due change, start a general-purpose subagent (not Explore) that
did not write the change. Don't read [consistency-read.md](consistency-read.md)
yourself: a main loop that has read it tends to paste it, condensed, into the
prompt, and the subagent then works from your copy. Write the subagent a prompt that tells it to read that file, by
its absolute path, as its brief, and to follow the brief exactly. The prompt
also gives the values of the brief's five placeholders: the change's directory,
where to read it from (the working tree, or the pull request's branch), its
base branch, every file under the change's directory (`git ls-files
openspec/changes/<change>`, or `git ls-tree -r --name-only <ref>
openspec/changes/<change>`), and the decision records it must agree with,
as `python3 "$SC/spec_check.py" records <change>` prints them (add `--ref
<ref>` for a branch): each touched capability's main record, and each record
whose *Paths* match a file the branch changes; a record the branch edits is
read with its diff against the merge base. For a record due on its own,
the prompt names the brief's *A record read on its own* section and gives
the subagent that section's three values instead: the record's path, where to read
it from, and its base branch. The brief tells the subagent to read each
listed file whole. Add nothing else to the prompt: no pasted files, and no
summary of the change. A summary is your own reading of the change, and the
subagent is there to read it without yours.

The subagent reads the change against every spec on the base branch, the
decision records listed, every open change, every open pull request
touching the same specs, and the repository's architecture docs, quoting
both sides of each finding. It reports a change that brings back a rejected
approach or breaks a recorded constraint. For a
stacked change, main plus the dependencies is the base.

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

**A record holds only what a test can't express: the evidence for why a
rule exists, or why an alternative lost.** Whatever a test can express is a
requirement with a scenario, including a rejection or constraint a test can
check: its scenario is one the rejected approach would fail, under the
requirement it would break. Each record entry carries evidence a test
can't: a Constraint for a rule no test can check (a cost policy, a choice
of tool), a Rejected entry for an alternative no requirement guards
against, and a Rationale entry for why a requirement exists. Each entry is
stated as it stands now, with no history.

**Rationale is admitted by evidence, not length.** A reason with evidence
(a failure, a measurement or an outside fact) is a Rationale entry,
however short. A requirement's *because* sentence is a plain one-line
reason for orientation. It has no place for Evidence, so it is never the
justification, and a requirement may keep it beside a Rationale entry.

**A record never repeats a requirement.** Cut an entry whose rule a
requirement or scenario already states; a Rationale entry names its
requirement and never restates the rule. The consistency read's item 16
flags a repeat.

**Every entry gives a later reader something to decide with:**

- A Constraint is a rule the code must keep that no test can check, with
  Evidence: a failure, a measurement or an outside fact, never invented. A
  rule a test can check is a requirement with a scenario.
- A Rationale entry states the consequence: what goes wrong without its
  requirement. Its Evidence is required: a failure, which is the bug or
  incident itself, linked, with its regression test as a further pointer;
  a measurement (an experiment someone ran); or an outside fact. Purely logical reasoning with none of these is not a
  Rationale entry; it stays in the change's design.md, archived with it. A
  test alone, the requirement's own test included, is never Evidence: it
  shows the rule is enforced, not why it is needed. Each Evidence line ends
  in a link: a URL, an issue or pull request, a commit, or a markdown link
  to a file.
- A rejection that a requirement guards against (one its scenario would
  fail) is written as that requirement's Rationale, with its Evidence. A
  Rejected entry is only for an alternative no requirement guards against,
  and its *Lost because* is a reason a later reader can check, never a
  person or a preference, linking evidence: a failure, a measurement or an
  outside fact. A broad class is fine ("Rejected: network calls of any
  kind"). A judgment call that no requirement guards against and that has
  no evidence is struck. An entry that no longer holds is deleted from the
  record.
- Reasoning that only restates the requirement, names who decided, or
  states a preference is noise, and a generic principle (keep it simple,
  and the like) never goes in a record. The consistency read flags these
  (item 17) in the round they appear, while the person who decided can
  still give the evidence.

```markdown
# <capability>: constraints, rejected alternatives and rationale

## Constraints
- **Constraint: <the rule, in the words a proposal would use>.**
  Because: <one sentence>.
  Evidence: <a failure, a measurement (value, how, date) or an outside fact>, <link>
  Holds while: <the condition that would retire it>.
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

A Rationale entry's title must name a requirement in force, or one an open
change adds, modifies or renames to. The title, less the entry's closing
period, must equal the requirement's exact title, so an entry for a
requirement whose title ends in a period writes two periods. An open change is any under `openspec/changes/`
on the branch, including one merged but not yet archived. `check` reports
any other title as an error, suggesting the exact title when one matches
ignoring case, spacing, backticks and a closing period. An entry naming a
requirement an open change removes or renames away is an error until the
record deletes it or retitles it to the new name.
A Rationale entry needs at least one *Evidence* line; more may follow, and they come last: an
indented line right after an Evidence line continues that line. The reasoning has no blank line inside it.

*Paths* is a comma-separated list of files, directories (`src/store/`) or
globs (`src/**/*.go`). Any labelled part may wrap onto indented lines,
with no blank line between the part and its continuation.

- **Where.** The record is at `openspec/specs/<capability>/decisions.md`,
  unless `openspec/spec-check.yaml` says otherwise, in one line:
  `decision-records: openspec/decisions/<capability>/decisions.md`. The
  path must be under `openspec/`, outside `openspec/changes/`, with
  `<capability>` as a folder of its own and a fixed `.md` file name after
  it; every file it matches is a record. spec-check refuses any symlink
  under `openspec/`.
- **Edit it in the pull request.** A pull request that changes a decision
  edits that record directly, beside its change's deltas; a change holds
  no copy of its own, and `check` refuses a `decisions.md` inside one.
  Reviewers see the real diff, and two branches editing one entry conflict
  as any file does. `check` reads the lines the branch changes for
  history, and editing a record makes the change touching its capability
  due for a read, or the record itself when no open change touches it.
  `openspec archive` never touches a decisions.md, so archive with it
  as usual.

## Decisions and open questions

Record material goes only in the decision record of each capability it
concerns, never in design.md: a constraint no test can check, an alternative turned down, or a reason
for a requirement, when it has evidence (see
[Decision records](#decision-records), which says which kind of entry
each becomes; a turned-down alternative that a requirement guards against
is that requirement's Rationale entry). Create the record if the
capability has none. Later changes and
their consistency reads read the record; design.md is archived with its
change and never read again. design.md does not restate a record entry,
though it may link to one.

design.md's *Decisions* section states each of the change's other
decisions once, as it stands now: design choices that are not record
material, and reasoning without the evidence a record entry needs. Its
*Open Questions* section holds each undecided item.
*Decisions* and *Open Questions* are both sections OpenSpec's
instructions for design.md name; create design.md when the
change has none. When a decision changes, rewrite its entry: keep no record of
how it was amended. Git and pull request comments hold the history.
proposal.md stays OpenSpec's one or two pages of why and what.

`check` gives an `evolution` error on each line of a change's files that
records history: an amendment ("amending decision 79"), a credit ("(Adam,
2026-10-21)", "Adam decided"), an earlier draft, or a review round ("this
push", "since review"). It reads the lines a branch changes in a decision
record the same way. A decision record skips the credit
rules, since its Evidence names products, standards and dated runs; a credit
there is the consistency read's job (item 17), and the other history rules
still apply, so "amended by Adam" still errors. Restate the line
as what holds now, or delete it. A line it flags wrongly is never reworded; see
[Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags).

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
  change, and the path of every record due on its own, and records that the read covered each one at this tree.
  `--amended` counts the read's amendments; `--open`, the open questions
  the due changes' design.md files now list, added together.
  `--read self` writes `read by its author, no subagent: ...`;
- `no read due`, whichever `--read` is given, when no change is due.

An older value, `read by a fresh subagent; ...` with no names, counts as a
last read of every change its commit touched, when deciding which are due.

`evolution` errors a person chose to keep are cleared by the change's
`.spec-check-kept` file ([below](#keeping-a-line-the-evolution-check-flags)),
and the value counts them after the checks, `0 errors, 2 checks, 1
evolution kept; ...`, whatever the `--read`. Editing the kept file makes
the change due like any other edit.

Stage the read's amendments with the rest of the round's last commit.
While a change is due, `sign --read subagent` also signs a commit that
changes nothing under `openspec/`, such as a code commit, and records the
read there. When every edit of the round is committed and the last commit
is not pushed, undo it with `git reset --soft HEAD~1`, do the read, and
commit again. Never rewrite a pushed commit: commit the read's amendments as a new
commit signed with `--read subagent`, or, if it amends nothing, record it
on an empty commit, signed with nothing staged, as below.

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
  review requests the call made, and tells you. Any other form is not
  checked, and the hook adds a note saying why, without blocking: to have
  it checked, run `gh pr ...` alone or with only those programs beside it.
- Where the repository has spec-check's GitHub workflow, it does the same
  for every hand-back, however it was made.

Either way: do the read, commit with `--read subagent`, push, and hand back
again. Neither sees a hand-back made in conversation: before telling a person
the work is ready, run `sign --read subagent` with nothing staged, and check
that it exits 1 saying `nothing waits for its consistency read` on
stderr.

**Setting up a repository.** When it has `.github/workflows/`, offer to add
spec-check's workflow: `python3 $SC/spec_check.py setup-ci` writes
`.github/workflows/spec-check.yml`, pinned to a pushed commit of this
script. Commit it, and suggest making the `spec-check` check required in the
base branch's protection rules.

When it has `openspec/config.yaml` and its agents write changes through
OpenSpec's /opsx skills, offer to merge the `rules:` block of
[opsx-rules.yaml](opsx-rules.yaml) into that file by hand, adding to any
`rules:` it already has. OpenSpec shows those rules to the agent writing
each artifact, even one that never loads this skill; they are advice, and
the checks and the consistency read still enforce.

Without OpenSpec 1.16.1 or later, `sign` still signs an unstacked change,
and the value says `show, validate and archive not run (install OpenSpec
1.16.1 or later)`. A stacked change gets a `stack` error instead, so `sign`
refuses it.
For work in progress, skip `sign` and write the value yourself: `skipped
(<reason>)`. A skip note records no read.

Commit once, carrying the trailer of every skill installed that asks for
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

   The quote is the whole line without its indent; copy it from the file,
   since the error cuts long lines short. Runs of spaces or tabs count as
   one space. The entry keeps every `evolution` error in that file whose
   line has that text, so it lapses only when the line itself changes.
   Blank lines between entries are skipped. `(asked)` is your statement
   that a person answered; the script cannot check it.
3. Sign. The kept errors no longer fail the run, and the value counts them:
   `Spec-check: ✓ <tree> 0 errors, 1 checks, 1 evolution kept; ...`, so
   the override shows in git.

A `kept` error is an entry that is not in that form, gives no reason, or
quotes the same line as an earlier entry; an entry that matches an
`evolution` error but lacks `(asked)` (see *When you cannot ask*, below); or
a kept file that cannot be read. An entry whose line changed or is gone
keeps nothing and is a `kept` check, with or without `(asked)`: remove it,
and if the line's new text is still flagged, ask the person about the new
text. `openspec archive` moves a change's kept file with the rest of the
change into `openspec/changes/archive/`, where spec-check does not read it.
Editing a record's kept file makes the same read due as editing the
record.

**When you cannot ask** (you are a subagent or a background job, or your
host has no picker), `sign` will refuse, so don't commit. Write each entry
you would keep without `(asked)`, as `<file>: «<line text>» kept:
<reason>`, stage it, and run `sign` anyway: its refusal names each such
entry with the errors it matches and your reason. Leave the change staged
and put that refusal, whole, in your result. Whoever receives it asks the
person, adds `(asked)` to each entry kept, fixes the other lines and
deletes their entries, and signs again.

## Current-state passes

When docs, or a pull request's body and title, may still describe an
earlier state, a hook prints `current-state pass due for: ...`, naming what
to rewrite. Do the pass without asking first: rewrite each named text to
describe the state as it now is. Ask a person only before dropping a
conclusion, as `prose compact` does.

- **The implementation lands on a spec branch.** The commit hook prints it
  for a commit that adds a file under a `src/` directory while the branch
  adds or edits an open change; on the base branch itself, every open
  change counts.
  Rewrite the change's proposal.md and design.md, and the pull request's
  body and title, wherever they say "specification only", or "will" for
  what is now built.
- **A change is archived.** The commit hook prints it for a commit that
  moves a change into `openspec/changes/archive/`, as `openspec archive`
  does. This is a safety net: the consistency read's checklist (item 15
  in consistency-read.md) already flags record material in design.md.
  Anything still in the change's design.md that should have been in a
  decision record moves out of design.md into the record of each
  capability it concerns, editing each record directly under the same rules as any
  record edit (see *Decision records*):
  - a Rationale entry for reasoning about one requirement, with its
    Evidence; reasoning with none stays in the archived design.md;
  - a Constraint entry for a rule the code must keep that no test can
    check, with its Evidence, including a principle behind several
    requirements (don't repeat it as Rationale under each); a principle with
    no evidence goes into the Rationale, beside that entry's Evidence, of
    each requirement that guards against what it rules out, or is left
    out;
  - a Rejected entry for an alternative that was turned down and that no
    requirement guards against, linking its evidence, including the
    fix not taken behind an accepted limit or trade-off (for example
    "Rejected: preventing duplicate asks across machines", with "Instead:
    duplicates are accepted").

  What fits none of these (how the design was reached, rollout or migration
  steps, overviews that describe the code, open questions), and anything
  still without Evidence or too slight for a later reader to decide
  anything with, stays in the archived design.md. Then run `prose check` on
  each file you changed, and compact any it reports as due.
- **A pull request is handed back for review.** prose's hook prints it
  after the agent's hand-back, and the GitHub workflow as a notice when a
  hand-back leaves no change unread. Do the final pass over each doc the
  pull request changes, and its body and title: fix any that still
  describes work as unfinished or to come.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec archive` and `openspec validate` results), who did the consistency
read and which changes it covered, or that it is deferred to the round's
end, the findings and what each became (amended, open question, reported to
another change), and anything not checked.
