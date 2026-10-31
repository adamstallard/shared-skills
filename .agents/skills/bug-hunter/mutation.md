# bug-hunter — mutation testing

The mutation procedure, from Step 3 to Step 9. [SKILL.md](SKILL.md) says
when it runs and sends you here; read this file before starting any
mutant, and follow it. The subagents' own brief is
[mutation-brief.md](mutation-brief.md). Why each part:
[DECISIONS.md](DECISIONS.md#mutants-are-made-by-agents-in-a-throwaway-copy).

A mutant is one small deliberate change to the code, such as a `<` made
`<=` or a statement deleted. The tests kill it by failing; one they pass
on survived, and marks behaviour no test checks.

## When mutation runs

**Once per run, on the functions the change touches, within one cap.**

- **Iteration 1** mutates the functions the staged change touches that
  have tests, chosen by the focused selection below.
- **A later iteration** mutates only when the last iteration's fixes
  touched functions that have tests, and then only those functions.
- **The cap is 40 mutants a run**, shared by all its iterations, unless the
  user or the project's `AGENTS.md` sets another. A later iteration gets
  what earlier ones left; with none left, it mutates nothing and the
  report says so.

With no test for a function, every mutant would survive and say only that
the tests are missing, so it is not mutated. When that leaves nothing, the
report says `mutation  skipped — no tests cover the changed functions`.
Mutation runs only when Step 1's triage says `REVIEW`.

Fresh mutation subagents do it, in the background beside the finder, on a
**capable model**, never the code's author, at most three at once. Each
gets [mutation-brief.md](mutation-brief.md) exactly as written, with its
placeholders filled. **Never mutate source in the real tree**, and never
improvise a mutant outside this procedure: an improvised mutant once ran
`git config` in a real working tree.

## Running the mutants

Each mutation subagent works from [mutation-brief.md](mutation-brief.md),
handed over exactly as written; everything here is what the run does
around it.

**1. Choose the focused tests and the recheck.** Each target function
gets its own focused command: the tests that exercise that function, not
the test file that holds them. Every mutant runs it, so a whole file of
hundreds of tests costs minutes per mutant. Find the tests whose names or
bodies mention the function, with `git grep -n -w <function>` over the
test files, and select them with the runner's own selection:

| runner | focused command |
|---|---|
| pytest | `pytest tests/test_parser.py -k "parse_header or header"` |
| unittest | `python3 -m unittest tests.test_parser -k parse_header` |
| jest | `npx jest src/parser.test.ts -t "parseHeader"`, or `npx jest --findRelatedTests src/parser.ts` when the file holds little else |
| go | `go test ./parser -run 'TestParseHeader'` |

When no test mentions the function, select the tests that mention the
functions in its own source file that call it. Use the whole test file only when the runner
cannot select within it, and say so in the report. Where the project
offers no obvious selection, choose by hand and name the command in the
report; a general rule for it is an open question
([DECISIONS.md](DECISIONS.md#mutants-are-made-by-agents-in-a-throwaway-copy)).
A selection that runs no test is not a focused command: widen it, or
leave the function out and say so.

**The time budget.** Each run of a command against a mutant is stopped
at three times what the same command took on the unmutated copy, or 30
seconds, whichever is longer. A mutant that exceeds it counts as killed,
and is reported as `killed: timeout` and counted in the `timeout` column
of the report's per-operator table
([reference.md](reference.md#the-report)), so a reader can count it as
killed or leave it out. The brief carries the rule; nothing
needs filling in.

**The recheck.** A mutant that survives the focused tests is rerun
against every test file that mentions its file, not the full suite. For
each file a subagent mutates (item 2 groups them), search the repository's test files for
the file's name and for the path the language imports it by. For
`src/conditions.ts`, `-e /conditions` matches imports such as
`./conditions` and `../src/conditions`, which leave out the extension:

```bash
git grep -l -F -e conditions.ts -e /conditions -- '*.test.ts'
```

For `pkg/conditions.py`, the same search is
`git grep -l -F -e conditions.py -e pkg.conditions -- 'test_*.py'`. A
search that matches too many files costs only test time. When the
searches find no test file beyond those the focused command runs, the
recheck command is `none`, and a mutant that survives the focused tests
is a survivor. Otherwise the recheck command runs every test file the
searches found, the focused ones included. Why not the full suite:
[DECISIONS.md](DECISIONS.md#a-survivor-is-rechecked-against-the-tests-that-name-its-file).

**2. Split the work.** Group the target functions by file, and give each
mutation subagent one group or more, at most three subagents at once,
counting any still running from an earlier iteration. Share the run's
remaining cap out in proportion to each group's changed lines.

**3. Make one throwaway copy per subagent**, outside the real tree, from
the project's root:

```bash
set -eu
REAL=$(git rev-parse --show-toplevel)
TMP=$(mktemp -d)
TMP=$(cd "$TMP" && pwd -P)    # resolved: on macOS /var is a link
COPY="$TMP/repo"
git clone --quiet --no-checkout "$REAL" "$COPY"
git -C "$COPY" fetch --quiet "$REAL" HEAD
git -C "$COPY" reset --quiet FETCH_HEAD
git -C "$COPY" remote remove origin
rsync -a --delete --exclude=/.git --exclude=/node_modules "$REAL"/ "$COPY"/
if [ -d "$REAL/node_modules" ]; then ln -s "$REAL/node_modules" "$COPY/node_modules"; fi
git -C "$COPY" add -A
echo "copy: $COPY"
```

Run it as one tool call, and keep `set -eu` and the separate `mktemp` line.
Where `mktemp -d` fails and prints nothing, `cd ""` succeeds and leaves
you in the project, so a combined `TMP=$(cd "$(mktemp -d)" && pwd -P)`
would put the copy inside the real tree, and deleting the copy afterwards
would delete the project. With them, the first failure stops the block.
In a repository with submodules it stops at `git add -A`, because the
copied submodule's `.git` file points at a directory the clone lacks. Skip
mutation there, delete the temp directory and everything in it, and say so
in the report.

The clone gives the copy its own `.git`, so a git command that a test or a
mutant runs, a `git config` included, changes only the copy. Removing
`origin` keeps a `git push` from reaching the real repository. `rsync`
then lays the working tree over it, untracked files included, so the
copy's tests see what the Step 2 baseline saw, and `git add -A` stages that
state: the brief's check that the copy is clean compares the files with
it.

Adjust the block to the project's dependency directories. Each one the
tests only read, such as `node_modules` or `.venv`, is excluded from
`rsync` and linked, as `node_modules` is above, so it is not copied. Never
link a directory the tests write, such as a build output or a cache: left
out of the excludes, `rsync` copies it, and the tests write the copy's.

Not `git worktree add`: a worktree shares the real repository's config,
hooks and refs, so a mutant's `git config` or commit would land in the
real one. Not a plain `cp -R` either: when the real tree is itself a
worktree, its `.git` is a file pointing at the shared repository, and the
copy would point there too.

**4. Fill the brief** for each subagent: its functions, with line ranges,
changed lines from `git diff --cached -U0`, and each one's focused
command; the `copy:` path the block printed; the recheck command; the shim directory,
`<base directory>/scripts/gh-shim`, where `<base directory>` is this
skill's own directory, the one holding SKILL.md, which Claude Code names
on its "Base directory for this skill:" line; the log file,
`gh-calls.log` in the directory above the `copy:` path, outside the copy so
`git add` never stages it; and its cap. Add nothing else. Told what the
code is meant to do, a subagent would judge survivors by that intent
instead of by what the tests check.

The shim is a `gh` that refuses every call with exit 1 and logs it. It
catches only a `gh` found on `PATH`: a test that runs `gh` by absolute
path, or another networked CLI, gets through; whether to cover other CLIs
is an open question.

**5. Collect the results.** As each report arrives, check its last line
says `copy clean: yes`, then send its survivors to the finder of the
iteration in progress ([Survivors that arrive during Steps
4–7](#survivors-that-arrive-during-steps-47)). If it says
`no`, the copy may still hold a mutant: resume that subagent to revert it,
and use none of its results until it reports the copy clean. When every
subagent has reported, resume them one at a time via `SendMessage`,
each with its own mutants marked `needs serial rerun`, so each rerun has
no other test run beside it: run none in the real tree meanwhile. Send each subagent only its own mutants: its
recheck command covers only its own files. Send the
survivors those reruns turn up to the finder too. Delete each
subagent's copy once its serial reruns are done, and the proof copy ([The proof copy](#the-proof-copy)) once
no survivor still needs a test, each by the directory above the `copy:`
path it printed. First check that
directory is not the
project and does not hold it, since a shell variable from item 3 is gone
by now. `rm -rf` on it removes the links, not what they point at.

**6. Count for the report.** Add up, across subagents and iterations:
mutants, functions, killed, killed by timeout, survivors killed by new or
strengthened tests, dead code removed, stale survivors, and survivors
ignored as equivalent; and per operator,
the same counts plus survivors that led to findings and dead code kept as a
recommendation.

## Judging a survivor

**A survivor is a lead, never a finding.** Send each one to the finder via
`SendMessage`, whether it is still running or has reported. For each, the
finder answers one of four: a candidate, reported only once it has observed
a real wrong outcome in the real code, like any other; a gap, where the code
is right and no test checks it, naming the existing test the mutation report
calls weak if there is one; equivalent, where no test could tell the mutant
from the real code; or dead code, saying which kind and why.

- **Provably dead** code is unreachable by construction, such as code after
  an unconditional return or a branch the types or a linter show
  impossible; an unexported function with no reference anywhere in the
  repository; or a value never read. It skips the refuter and goes to
  Step 6 for removal.
- **Judged dead** is any other dead-code claim, and Step 5 checks it.
- **A survivor in a check at a trust boundary**, where outside data enters,
  is a gap, never dead code: the check exists to reject data the repository
  does not control, so the survivor means no test sends it that bad input.
- **Exported or public code with no caller in the repository** is neither
  provably nor judged dead: its callers are searched for
  ([below](#exported-code-with-no-caller-in-the-repository)). A caller
  found makes it a gap, with a test of its public contract. None found
  makes it a Step 9 recommendation, asking the one thing only the user may
  know: whether anything outside the repository uses it. It is never
  removed without the user's yes.

A gap gets a test, not a fix ([Step 4](#step-4--a-test-for-a-survivor)).
Equivalent survivors are ignored and counted in the report.

## Survivors that arrive during Steps 4–7

**Mutants never hold up the hunt.** Steps 4–7 start on the finder's own
candidates as soon as it reports, while the mutants still run. Each
survivor joins the iteration in progress when it arrives, and is judged
against the code as it is then, fixes included:

1. **Send it to the finder of the iteration in progress**, never an
   earlier iteration's: that finder has read the code as it now stands.
   Say the code may have changed since the mutant ran, and ask for the
   answer against the current code.
2. **A candidate goes through Steps 4–7 like any other.** Its test runs on
   the current code, so one that a fix already covers passes, and is
   dropped with its test deleted. Before a proven one is fixed, a fresh
   agent asks Step 5's fix-conflict question about it on its own, against
   the fixes already written. It is fixed in the iteration it is proven
   in, and that iteration has then found something, so another is owed.
3. **A gap's test is proven by applying the mutant to the current code**,
   in the proof copy. If the mutant's `<original>` text no longer exists in
   its function there, a fix rewrote that code, and the survivor is stale:
   drop it, delete any test written for it, and count it as `stale`. The
   fix touched that function, so the next iteration mutates it again; in
   iteration 3, that fix is already part of the `budget` cause for the
   iteration's unreviewed fixes.
4. **A dead-code answer is checked against the current code** too, by
   Step 5 or by the fixer.

**An iteration is clean only when** its finder's candidates found nothing,
every mutation subagent running during it has reported, and every survivor
sent to it is answered with no bug proven. One that found something does
not wait for the mutants: the next iteration starts, and their survivors
go to its finder.

**Only the commit and the Step 9 report wait**, for every mutation
subagent to report, every survivor to be answered, those from serial
reruns included, and every caller search to return.

### The proof copy

The subagents' copies are busy while they run, and hold the code as it
was when they were made, so survivor tests are proven in one more copy:
the proof copy. Make it with the block in [Running the
mutants](#running-the-mutants), item 3, when the first survivor test needs
proving. Before each proof, bring it up to the current code, as one
tool call, with `<proof copy>` written out from the `copy:` line it
printed:

```bash
set -eu
REAL=$(git rev-parse --show-toplevel)
PROOF="<proof copy>"
[ "$(git -C "$PROOF" rev-parse --show-toplevel)" = "$PROOF" ] || exit 1
rsync -a --delete --exclude=/.git --exclude=/node_modules "$REAL"/ "$PROOF"/
git -C "$PROOF" add -A
```

Adjust the excludes to match the ones the copy was made with.

## Step 4 — A test for a survivor

For a survivor the finder called a gap: the code is right, and no test
notices when it is changed. The test checks what the survivor's `unpinned`
line names, through the code's public entry points. What crosses a
boundary the code owns counts as behaviour: a return value, an output, an
error, the arguments of a call to an external process or service. Private
state, and calls between the function's own helpers, do not.

For a check at a trust boundary, the test sends in the bad input the check
exists to reject, such as a malformed payload or a value out of range, and
asserts that it is rejected. For exported code that a search found a
caller of, the test checks the contract that caller relies on.

**Strengthen an existing test, or write a new one.** Where the mutation
report's `weak test` line names an existing test that runs the mutated code
but checks nothing that would notice, you may add assertions to that test
instead of writing a new one. Only add: never change, loosen or remove an
assertion it already has. Never delete it either, even if it asserts
nothing, since it still catches a crash. The proof is the same either way.

1. Write it in the real tree, as any Step 4 test, and run it: green.
2. Bring the proof copy up to the current code ([The proof
   copy](#the-proof-copy)). Find the mutant's `<original>` text in its
   function there; if it is gone, the survivor is stale ([Survivors that
   arrive during Steps 4–7](#survivors-that-arrive-during-steps-47)).
3. In the proof copy, make the mutant's edit (`<original>` → `<mutated>`)
   and run the test: red, failing on what the `unpinned` line names.
4. Revert the edit (`git -C <proof copy> checkout -- <file>`), so the
   proof copy is clean again by the brief's check.

| Result | Action |
|---|---|
| Green on the real code, red on the mutant | Keep it, for Step 5's refuter to review. It is staged with the commit this run checks. |
| Red on the real code | The test is wrong, or the code is. Repair the test once. Still red on the real code: send it to the finder as a candidate, since it may be a bug. |
| Green on the mutant | Repair it once. Still green: the survivor is equivalent, ignored and counted. |

Never edit the real tree's source to see the red: the mutant exists only in
the proof copy.

## Step 5 — Survivor tests and dead code

Launch these refuters with the others, one per item, each fresh. A survivor
test or a dead-code claim is a factual claim, like a finding, so the
skeptical default fits it: the refuter is asked whether something is true
of the code, not whether a design should change.

**A survivor test**, new or strengthened. Give the refuter the test, the
code under test, its callers, and the spec, split into committed and
in-flight text as in
[reference.md](reference.md#step-5--refute); not the finder's reasoning. It asks: does this
test assert what the code *should* do, by the spec and by what the callers
rely on, or only what it does now? A test green on the real code pins
today's behaviour, so if the finder took a bug for a gap, the test pins the
bug.

| Verdict | Action |
|---|---|
| Asserts intended behaviour | Keep it. |
| Asserts behaviour the spec or a caller contradicts | Delete the test, or remove the assertions added to a strengthened one. Send the survivor to the finder as a lead, as in Step 3; a candidate it reports goes through Steps 4–7 like any other. |

**Judged-dead code**: anything the finder called dead except three kinds,
each settled without a refuter. Provably dead code goes to Step 6 for
removal; a check at a trust boundary is a gap ([Judging a survivor](#judging-a-survivor)); and
exported or public code has its callers searched for
([below](#exported-code-with-no-caller-in-the-repository)). Give the refuter the code, the
repository and the survivor. It tries to show the code is live, by this
checklist. The last two items catch code the finder failed to see was a
boundary check or exported:

- an error path that real systems produce and the tests don't exercise;
- dynamic use: reached by name, through configuration, or on another
  platform;
- a deliberate defensive check at a trust boundary, where outside data
  enters;
- exported or public API, which a caller outside the repository could use.

| Verdict | Action |
|---|---|
| No item applies | Step 6 removes it. |
| An error path or dynamic use | The survivor is a gap. Step 4 writes its test, which a fresh refuter then reviews as above. |
| A trust-boundary check | The survivor is a gap. Step 4 writes a test that sends in the bad input the check guards against, which a fresh refuter then reviews as above. |
| Exported or public API | Search for the code's callers, as below. |

## Exported code with no caller in the repository

Search before anyone is asked, and run the search yourself, in the main
loop, as Step 2 runs the baseline: it is a few commands, not judgement.
The owners to search are your own account, `gh api user --jq .login`, and
each organisation you belong to, `gh api user/orgs --jq '.[].login'`.
Search each for the name:

```bash
gh search code "<name>" --owner <org> --limit 20
```

Search the repository's own configuration too: package manifests' entry
points and exports, plugin and route lists, CI and deployment files. A hit
counts only when it uses this code, such as an import from this package,
not when it is another symbol with the same name. Note what was searched,
for the question below. If `gh` cannot search, the code still goes to
Step 9, and the question says that no search ran, instead of claiming one
found nothing.

| Result | Action |
|---|---|
| A caller found | The code is live, and the survivor is a gap. Step 4 writes a test of its public contract, and a fresh refuter reviews it as above. Nobody is asked. |
| No caller found | A Step 9 recommendation ([reference.md](reference.md#asking-about-a-recommendation)). The search cannot rule out a private caller it cannot reach, or one nobody knows of, so the code is never removed without the user's yes. |

## Step 6 — Removing dead code

Whoever writes the fixes also removes dead code: what the finder called
provably dead, what Step 5's refuter found no live path to, and exported
code the user said in Step 9 to remove. Never a check at a trust boundary,
and never exported or public code without that yes.

The fixer removes only that code, and runs the tests that cover the file:
every one stays green, or the removal is reverted and reported unresolved.
Each removal is staged with the commit this run checks and listed in the
report.

## At the cap

Once iteration 3 has found something, the iteration ends when its Step 7
does, without waiting for more survivors to be answered. The report still
waits for every mutation subagent to report, so that no survivor is lost;
then put the leftovers in the root-causes report as `budget` entries ([reference.md](reference.md#when-the-run-aborts)):

- one entry for the survivors the finder had not answered, listing each
  mutant;
- one for each survivor answered as a candidate but not yet proven, with
  its concrete input and wrong outcome.

Never a fourth iteration for them, and never drop one silently.
