---
name: spec-check
description: >-
  Check an OpenSpec change for correctness and consistency before a person
  reviews it, so the reviewer judges only whether the rules are the right
  ones. Use when drafting or reviewing an OpenSpec change, before committing
  or opening a pull request that adds or changes anything under
  openspec/changes/ or openspec/specs/, when reviewing a spec pull request,
  or when asked to "check this spec", "cross-check the change" or "is this
  spec consistent". Runs mechanical checks with a script, has a
  fresh subagent read the change against every other spec, change and open
  pull request, and fixes findings in the spec itself. Commits that change
  openspec/ carry a Spec-check: trailer.
---

# spec-check

**A spec reviewer should spend their time on whether the rules are right, not
on holding every other spec in mind.** This skill does the holding: a script
checks what is mechanical, and a fresh subagent reads the change against
everything it must agree with. Readability is the `prose` skill's job; linking
tests to scenarios after implementation is a separate step.

- **Why it works this way:** [DECISIONS.md](DECISIONS.md). Read it before
  changing this file or the script.
- `$SC` below is this skill's `scripts/` directory, as an absolute path.

## When

- Before any commit, and before opening a pull request, that changes a path
  under `openspec/changes/` or `openspec/specs/`.
- When reviewing a spec pull request, yours or someone else's.
- When asked to check a spec.

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

**It needs OpenSpec 1.15.0 or later on PATH** (`npm install -g
@fission-ai/openspec`). It reads specs and deltas only through the CLI:
`openspec show --json` for their requirements, `openspec validate --strict
--json` for what a delta drops or misfiles, and `openspec archive --json` for
whether a change applies. Without that CLI, every check that needs a
requirement reports `not run: install OpenSpec 1.15.0 or later`, followed by
why the CLI on PATH cannot be used, such as `(this one is 1.14.3)`.
Citations, `Builds on:` lines and the `renamed-block` scan still run, and a
stacked change gets a `stack` error.

| Kind | Severity | What it means |
| --- | --- | --- |
| `no-scenario` | error | A requirement states a SHALL or MUST and has no scenario |
| `renamed-block` | error | A `###` heading under `## RENAMED Requirements` with anything under it besides FROM and TO lines. OpenSpec reads only FROM and TO lines there, so `openspec archive` drops the rest, and OpenSpec itself does not say so. Restate the requirement under `## MODIFIED Requirements` with its new name |
| `scenario-incomplete` | error | A scenario has no WHEN or no THEN |
| `duplicate` | error | A sentence of the rule also appears under another requirement, here or in another spec or change. Two requirements with one name may share sentences only when one is a MODIFIED requirement in the other's capability |
| `archive` | error | `openspec archive` refuses the change: an ADDED requirement whose name is already there, a RENAMED onto a name already taken, a MODIFIED that drops a scenario, or a requirement modified, removed or renamed that is not there. The error quotes the CLI. See [Archive refusals](#archive-refusals) |
| `purpose` | error, or check | Error: a delta creates a capability, one with no spec in main or in what the change builds on, and the Purpose `openspec archive` would give the new spec fails `openspec validate --strict`. When the delta's `## Purpose` is missing or empty, or would leave the spec unreadable, archive writes "TBD - created by archiving change ..." instead, and nobody replaces it. A `TBD` or `TODO` placeholder, or a Purpose under 50 characters, archive copies as written. Write what the capability is for under `## Purpose` in the delta. Check: a `## Purpose` in a delta for a capability that exists, which archive ignores, when it differs from the spec's. Runs with the archive, so without the CLI it is not run |
| `citation` | error, or check | A `path:line` with a `/` whose line is in neither the base branch nor the change is an error. Any other citation finding is a check: a bare name such as `config.py:50`, or a line only the change adds. Text in a code fence, and addresses such as `0.0.0.0:8080`, are skipped |
| `openspec-validate` | error, or check when validation passed; an INFO note is always a check | An issue `openspec validate --strict` reported, at OpenSpec's line and in its words. Among them: a section or text above the first `##` that the archive drops, a requirement under a misspelt or other section, and a `###` heading in a delta that is not a requirement header, which OpenSpec reports as an INFO note, so it is a check. To that last one spec-check adds where the rule goes: restated under MODIFIED when the specs already have its title, moved to ADDED when they do not |
| `openspec-show` | error, or check | `openspec show` cannot read a change's deltas or a main spec, so no requirement check read it. A main spec is a check when only changes are checked |
| `stack` | error, or check | Error: a `Builds on:` line that cannot be read or is listed twice; a change that names itself; the OpenSpec CLI missing from PATH, or older than 1.15.0; a pull request that holds no change of that name; a dependency that cannot be read, or whose deltas `openspec archive` refuses; a merged dependency whose result your branch does not hold; a dependency that builds on a change this one does not list before it, whose result your tree lacks. Check: a dependency whose result your tree already holds, so its line should be removed; one only partly there; one whose version a later dependency replaces without building on it; one whose pull request was closed without merging (see [Stacked changes](#stacked-changes)) |
| `drift` | error, or check | Error: a stacked change modifies, removes or renames a requirement that main plus its dependencies no longer define. Check, quoting both texts: a modified requirement keeps a sentence its dependency has since replaced, or a requirement a dependency adds is already in your tree with another text |

A **check** is a heuristic: judge it, and fix it or leave it. An `openspec
archive` or `openspec validate` result of "not run" means it was not
checked, never that it passed; say so in your report.

`--no-validate` skips the whole `openspec validate --strict` run, so its
result reads `not run (--no-validate)` and no `openspec-validate` finding
appears, including the ones about sections the archive drops. Every other
check still runs, the archive check included: only a missing or older CLI
skips the archive.

Citations are checked against the base branch: by default `origin/HEAD`, then
`origin/main`, then `main`. Pass `--base` when the change targets another
branch.

### Archive refusals

`check` copies the tree's specs into a temporary directory and archives the
checked change, and only that change, into the copy with the real `openspec
archive`. Each refusal is an `archive` error at the requirement it is about,
or at line 0 of the delta file when it is about the file as a whole. OpenSpec
stops at its first refusal, so fix it and run `check` again to see the next.
The tree itself is never touched.

A stacked change is archived on top of its dependencies rather than onto the
tree's specs alone (see [Stacked changes](#stacked-changes)).

Without OpenSpec 1.15.0 or later on PATH, a change with no `Builds on:`
line, which is archived alone, gets the line `openspec archive (<change>): not run`, saying why. A stacked change
gets a `stack` error instead.

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
chain, where this change builds on B and B builds on C, list both, in the
order they apply to main: C's line first, then B's. Leaving out C's line
is a `stack` error, unless your tree already holds C's result, as it does
once C has merged and you have merged main.

`check` then reads each dependency's change from its pull request's head
commit (with `gh pr view` and `git fetch`; nothing is checked out), and
handles it by its pull request's state:

- **Open, or closed without merging.** `check` copies your tree's specs
  into a temporary directory. In the order of the lines, it archives each
  such dependency into that copy with one run of the real `openspec
  archive`. First it drops the deltas the copy already shows: an addition
  there with the same text, a removal already absent, a modification with
  the same text, and a delta's renames when, read in order, every one is
  already done. When an addition is in your tree with another text, your
  tree's text is kept, and a `drift` check quotes both. A closed pull
  request also gets a `stack` check, since its change may never land.
- **Merged.** Its result is already in main, so it is never archived
  again. Instead, `check` looks for that result in your tree by
  requirement name: each requirement it adds or modifies must be there,
  with any text (main may have reworded it since), each it removes absent,
  and its renames, read in order, done. Another merged dependency, listed
  after this one or building on it, may have changed those names since. A
  name the later dependency removes or renames away need not be there, and
  a name the later dependency adds or renames onto need not be absent. When the
  result shows, a `stack` check says the line is stale: remove it. When it
  does not, a `stack` error names what is missing: merge main into your
  branch. One exception: a dependency that has merged but is still open in
  your tree, with the same deltas, because it is not archived yet, is
  handled as an open one.

Every check then runs against the result.

**Stacked changes need OpenSpec 1.15.0 or later on PATH,** since the
dependencies are read and archived with it. Without it, the change gets a
`stack` error.

**What stops the check.** Each of these is a `stack` error, never a pass:
a dependency that cannot be read; a pull request that holds no change of
the name on the line, which means the line names the wrong change or the
wrong pull request; a delta in which `openspec show` reads nothing; and
deltas `openspec archive` refuses, where the error quotes the CLI and names
the dependency. After any of these errors, the duplicate and drift checks do
not run for the change, and the error says so; the other checks still run.

**The change itself is archived last,** on top of its dependencies, as
[Archive refusals](#archive-refusals) describes. A refusal on a line where
a `drift` error already sits is not reported again.

**Remove the line once the dependency is in your tree.** When all of an
open or closed dependency's deltas are already in your specs, a `stack`
check says your tree already holds its result: remove the line. When only some
are, a check names which deltas were already there and which were
archived.

**Two dependencies that set the same requirement.** The one listed later
replaces the earlier one's version. When the later one does not build on
the earlier one, a check says the earlier version is left out: make sure
the later text includes what your change needs.

**A `drift` check** quotes a sentence your change kept from an earlier text
of the dependency's requirement, and the sentences the dependency has now
instead. If your change was written against the earlier text, restate the
requirement from the dependency's current text. If you kept the sentence on
purpose, leave it.

**The hint.** A `duplicate` error against a main requirement that an open
pull request removes or renames ends with the line to add, for example:
``add `Builds on: seat-files (adamstallard/igor#171)` to its proposal.md``. If
your change really applies on top of that pull request, add the line. If it
does not, the duplicate is real: state the rule once. The hint does not
clear the error; only the line does.

`sign` checks a stacked change the same way, so it needs `gh`, the
network and the OpenSpec CLI too.

## 2. The consistency read, by a fresh subagent

Start a subagent that did not write the change and give it
[consistency-read.md](consistency-read.md) as its brief, with its three
placeholders filled in: the change's directory, where to read it from (the
working tree, or the pull request's branch), and its base branch. Do not add your own summary of the
change: what you would say is what the read is checking.

The subagent reads the change against every spec on the base branch, every
open change, every open pull request touching the same specs, and the
repository's architecture docs, and reports findings with quotes from both
sides. For a stacked change it also reads each dependency's change and
treats main plus the dependencies as the base, as the brief says.

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

## Decisions and open questions

A change states each decision once, as it stands now, in design.md's
*Decisions* section, and each undecided item in its *Open Questions*. Both are
sections OpenSpec's instructions for design.md name; create design.md when the
change has none. When a decision changes, rewrite its entry: keep no record of
how it was amended. Git and pull request comments hold the history.
proposal.md stays OpenSpec's one or two pages of why and what.

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

After the last fix and the final `git add`, and after the consistency read:

```sh
python3 "$SC/spec_check.py" sign --read subagent --amended <n> --open <n>
```

It runs the mechanical checks on the staged tree and refuses when any error
remains. Otherwise it prints `Spec-check: ✓ <tree> ...`, a value bound to the
staged tree. Without OpenSpec 1.15.0 or later it still signs, and the value
says `show, validate and archive not run (install OpenSpec 1.15.0 or
later)`. `--amended` is how many amendments the read led to; `--open` is
how many open questions design.md now lists. For work in progress, skip
`sign` and write the value yourself: `skipped (<reason>)`.

Commit once, carrying every installed skill's trailer
([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
Pass the text after `Spec-check: ` as a `--verified-value` family. The
example goes through bug-hunter's commit script, `$BH`, with prose's scripts
directory as `$S`; bug-hunter's and prose's SKILL.md say where each is. After
the `--` come bug-hunter's own arguments: the message file, its `Bug-hunter:`
value, and the co-author.

```sh
"$BH" --verified-value "$S/verify-staged.sh" Prose "✓ 4d593e935186:9138830a72a2" \
      --verified-value "$SC/verify-staged.sh" Spec-check "✓ 4d593e935186 0 errors, 1 checks; validate passed; read by a fresh subagent; 3 amended, 1 open" -- \
  -F msg.txt "skipped at triage (spec only, no code)" "<co-author>"
```

Without bug-hunter, call the library directly with the same families:
`$SC/../../../lib/commit-trailer/commit-with-trailers.sh <families>
--co-authored-by "<co-author>" --message-file msg.txt --`.

Sign after prose's rewrite is staged: staging anything after signing changes
the tree, and the commit script refuses the stale value.

The commit hook reports a commit that changes `openspec/` without a valid
`Spec-check:` trailer. It never reports a commit that changes nothing under
`openspec/`.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec archive` and `openspec validate` results), who did the consistency read, the findings and
what each became (amended, open question, reported to another change), and
anything not checked.
