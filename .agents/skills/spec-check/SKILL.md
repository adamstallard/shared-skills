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
Readability is the `prose` skill's job; linking
tests to scenarios after implementation is a separate step.

- **Why it works this way:** [DECISIONS.md](DECISIONS.md). Read it before
  changing this file or the script.
- `$SC` below is this skill's `scripts/` directory, as an absolute path.

## When

- **The mechanical checks:** before any commit that changes a path under
  `openspec/changes/` or `openspec/specs/`.
- **The consistency read:** once per review round, at its end. A review
  round is your work between two hand-backs to a person for review: a pull
  request opened or marked ready, a review requested, or telling a person
  the work is ready. A push does not end a round. Do the read before the
  round's last commit, the one you will hand back. Commits before it record
  the read as deferred, and may be pushed (see [Commit](#commit)). A draft
  pull request that requests no review is not a hand-back.
- When reviewing a spec pull request, yours or someone else's: both.
- When asked to check a spec: both.

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
| `evolution` | error | A line in the change's files records how the change got to its shape, not what holds now: an amendment, a credit to a person or a date, an earlier draft, or a review round. It quotes the line. Text in a code fence, backticks or double quotes is skipped. Only a person can keep a line it flags wrongly, in the change's `.spec-check-kept` file: see [Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags) |
| `kept` | error, or check | Error: an entry in a change's `.spec-check-kept` file that is not in the entry form, gives no reason, or quotes the same line as an earlier entry; an entry that matches an `evolution` error but lacks `(asked)`, the mark that a person was asked; or a kept file that cannot be read. Check: an entry that matches no `evolution` error, because its line changed or is gone. Remove the entry |

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

Once per round, at its end, each **due** change gets a read of the whole
change. A change is due when the branch adds or edits it and it differs
from its **last read**: the newest commit in the branch's history whose
`Spec-check:` trailer records a read that names it (see [Commit](#commit)).
To see which changes are due before you read them, run `sign --read
subagent` on the staged tree: the value it prints names them, or says `no
read due`. Run it again after the read, with the read's counts, to sign the
commit.

For each due change, start a general-purpose subagent (not Explore) that
did not write the change and give it [consistency-read.md](consistency-read.md)
as its brief, with its four placeholders filled in: the change's directory,
where to read it from (the working tree, or the pull request's branch), its
base branch, and the list of every file under the change's directory
(`git ls-files openspec/changes/<change>`, or `git ls-tree -r --name-only
<ref> openspec/changes/<change>`). Keep the brief's instruction to read
each listed file whole, every line, paging long files with the Read tool,
never skimming, grepping or sampling: a problem may sit anywhere in a long
delta spec. Do not paste the files into the brief, and do not add your own
summary of the change: what you would say is what the read is checking.

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

`check` gives an `evolution` error on each line of a change's files that
records history: an amendment ("amending decision 79"), a credit ("(Adam,
2026-10-21)", "Adam decided"), an earlier draft, or a review round ("this
push", "since review"). Restate the line as what holds now, or delete it.
Don't reword a line that is not history to get past the check: a person
keeps it instead (see
[Keeping a line the evolution check flags](#keeping-a-line-the-evolution-check-flags)).

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
  `--read subagent`, on the commit that ends the round. It names every
  change that is due, and records that the read covered each one at this
  tree. `--amended` is how many amendments the
  read led to; `--open` is how many open questions the due changes'
  design.md files now list, added together.
  `--read self` writes `read by its author, no subagent: ...`;
- `no read due`, whichever `--read` is given, when no change is due.

A value from before rounds, `read by a fresh subagent; ...` with no names,
records a read of every change its commit touched.

The `evolution` errors a person chose to keep are cleared by the change's
`.spec-check-kept` file ([below](#keeping-a-line-the-evolution-check-flags)),
staged like the rest of the change. The value then counts them after the
checks, `0 errors, 2 checks, 1 evolution kept; ...`, whichever `--read` is
given. The kept file is one of the change's files, so editing it makes the
change due like any other edit.

The round's last commit carries the read, so do the read before that
commit, and stage its amendments with the rest. `sign --read subagent`
also signs a commit that changes nothing under `openspec/`, such as a code
commit, while a change is due: its read is recorded there. When every edit of
the round is already committed and the last commit is not pushed, undo it
with `git reset --soft HEAD~1`, do the read, and commit again with
`--read subagent`. Never rewrite a pushed commit. If the last commit is
pushed and the read amends nothing, record the read on an empty commit: sign
with nothing staged, and pass `--allow-empty` as the first argument to
bug-hunter's commit script, or among the library's options, as in the
example below.

**The hand-back checks.** A hand-back is `gh pr create` (not a draft, unless
it requests a review),
`gh pr ready`, `gh pr edit --add-reviewer`, or the GitHub MCP's equivalents.
Each is judged at the pull request's head on GitHub, so push the read before
you hand back:
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
  review requests the call made, and tells you. A hand-back in any other
  form is not checked: the hook adds a note saying why, without blocking.
  To have it checked, run `gh pr ...` on its own, or with only those
  programs beside it.
- Where the repository has spec-check's GitHub workflow, it does the same
  for every hand-back, however it was made.

Either way: do the read, commit with `--read subagent`, push, and hand back
again. Neither sees a hand-back made in conversation: before telling a person
the work is ready, run `sign --read subagent` with nothing staged, and check
that it exits 1 saying `no change waits for its consistency read` on
stderr.

**Setting up a repository.** When it has `.github/workflows/`, offer to add
spec-check's workflow: `python3 $SC/spec_check.py setup-ci` writes
`.github/workflows/spec-check.yml`, pinned to a pushed commit of this
script. Commit it, and suggest making the `spec-check` check required in the
base branch's protection rules.

Without OpenSpec 1.15.0 or later, `sign` still signs, and the value says
`show, validate and archive not run (install OpenSpec 1.15.0 or later)`.
For work in progress, skip `sign` and write the value yourself: `skipped
(<reason>)`. A skip note records no read.

Commit once, carrying every installed skill's trailer
([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
Pass the text after `Spec-check: ` as a `--verified-value` family. The
example goes through bug-hunter's commit script, `$BH`, with prose's scripts
directory as `$S`; bug-hunter's and prose's SKILL.md say where each is. After
the `--` come bug-hunter's own arguments: the message file, its `Bug-hunter:`
value, and the co-author.

```sh
"$BH" --verified-value "$S/verify-staged.sh" Prose "✓ 4d593e935186:9138830a72a2" \
      --verified-value "$SC/verify-staged.sh" Spec-check "✓ 4d593e935186 0 errors, 1 checks; validate passed; read by a fresh subagent: keep-action-log; 3 amended, 1 open" -- \
  -F msg.txt "skipped at triage (spec only, no code)" "<co-author>"
```

For a read that amends nothing, with every edit already committed, the
same call with `--allow-empty` first makes an empty commit carrying the
trailers: `"$BH" --allow-empty --verified-value ... -- -F msg.txt
"skipped at triage (no change)" "<co-author>"`.

Without bug-hunter, call the library directly with the same families:
`$SC/../../../lib/commit-trailer/commit-with-trailers.sh <families>
--co-authored-by "<co-author>" --message-file msg.txt --`.

Sign after prose's rewrite is staged: staging anything after signing changes
the tree, and the commit script refuses the stale value.

### Keeping a line the evolution check flags

The same words can describe behaviour ("Each new vote amends the
decision.", in a spec for a voting system), so an `evolution` error can be
wrong. When you believe one is, don't reword the line; a person decides.

1. Ask a person one question per line through your host's interactive
   picker (in Claude Code, the `AskUserQuestion` tool): show the line, the
   error, and why you think it is not history, with two options. "Fix it":
   restate the line as what holds now and restage. "Keep as is": the line
   stays as written.
2. Add an entry for each kept line to the change's kept file,
   `openspec/changes/<name>/.spec-check-kept`, and stage it. It is part of
   the change, so `check` reads it too, and a reviewer who runs `check` on
   your branch sees the line as kept, not as an error. An entry names the
   file, relative to the change, and quotes the flagged line's text between
   `«` and `»`:

   ```text
   design.md: «The spec narrows the decision.» kept (asked): compares the spec with a decision, not history
   ```

   The quote is the whole line as the file has it, without its indent. The
   error cuts a long line short, so copy the line from the file. Spacing
   does not matter: runs of spaces or tabs count as one space. The
   entry keeps every `evolution` error in that file whose line has that
   text, so it survives edits elsewhere and lapses only when the line
   itself changes. Blank lines between entries are skipped. `(asked)` is
   your statement that a person answered; the script cannot check it.
3. Sign. The kept errors no longer fail the run, and the value counts them:
   `Spec-check: ✓ <tree> 0 errors, 1 checks, 1 evolution kept; ...`, so
   the override shows in git.

An entry that is not in that form, gives no reason, or quotes the same
line as an earlier entry is a `kept` error. An entry whose line changed or
is gone keeps nothing and is a `kept` check, with or without `(asked)`.
Remove the entry. If the line's new text is still flagged, ask the person
about the new text. An entry that
matches but lacks `(asked)` is a `kept` error (see *When you cannot ask*,
below). `openspec archive` moves the file with the rest of the change into
`openspec/changes/archive/`, where spec-check does not read it.

**When you cannot ask** (you are a subagent or a background job, or your
host has no picker), `sign` will refuse, so don't commit. Write each entry
you would keep without `(asked)`, as `<file>: «<line text>» kept:
<reason>`, stage it, and run `sign` anyway, to get its refusal. The refusal
names each such entry with the errors it matches and your reason. Leave the
change staged and put that message, whole, in your result. Whoever receives
it asks the person, adds `(asked)` to each entry the person keeps, fixes
the text of the others and deletes their entries, and signs again.

The commit hook reports a commit that changes `openspec/` without a valid
`Spec-check:` trailer. It never reports a commit that changes nothing under
`openspec/`.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec archive` and `openspec validate` results), who did the consistency
read and which changes it covered, or that it is deferred to the round's
end, the findings and what
each became (amended, open question, reported to another change), and
anything not checked.
