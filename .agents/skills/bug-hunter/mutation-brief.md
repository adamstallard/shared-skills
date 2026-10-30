You are checking whether the tests would notice if the code below were
wrong. You make small deliberate changes to it, one at a time, called
mutants, and run its tests against each. A mutant the tests fail on is
killed; one they pass on survived, and shows behaviour no test pins. You
did not write this code, which is why you were asked: its author tests
what they meant it to do, and cannot see what it does that no test checks.

The functions to mutate, each with its file, its line range, and the lines
the change under review touched in it:
<functions, e.g. src/conditions.ts:40-96 observes (changed: 52-60, 88)>
The throwaway copy of the repository, where every mutant lives: <copy path>
The focused test command, run from the copy: <focused command>
The full-suite command, run from the copy: <full-suite command>
The gh shim directory: <shim directory>
The file the shim logs to: <log path>
Your mutant cap: <cap, e.g. 20>

## Never

- Edit, run anything in, or run git against any directory but the copy.
  The real working tree is someone's uncommitted work. If the copy's path
  is missing, or `git -C <copy path> rev-parse --show-toplevel` does not
  print it, stop and report that; never fall back to another directory.
- Run a test command without the shim first on PATH. Some suites call the
  real `gh`, and a mutant can turn a test's harmless call into a write to
  GitHub.
- Install anything, push, or commit.
- Leave a mutant applied when you report. If a revert does not leave the
  copy clean, stop running mutants and report `copy clean: no`.

Run every test command from the copy, in this form:

  cd <copy path> && PATH="<shim directory>:$PATH" GH_SHIM_LOG="<log path>" <command>

Stop any run that takes longer than three times what the same command
took on the unmutated copy, or 60 seconds, whichever is longer. Use your
tool's own time limit, or `timeout` where it is installed (macOS has
none). A
mutant that hangs a test counts as killed (timeout).

## 1. The unmutated run

Run the focused command on the copy before changing anything. Rerun each
test that fails, alone, in the test runner's serial mode if it has one
(`--runInBand`, `-p 1`, `--workers=1`). A test that then passes is flaky;
one that fails again is failing. Record both lists. A failing test kills
no mutant. If the focused command itself cannot run, stop and report that.

Then check the copy is clean: `git -C <copy path> diff --quiet` exits 0,
and `git -C <copy path> ls-files --others --exclude-standard` prints
nothing. The copy holds the change under review as staged content, so
`git status` lists it; these two commands compare the files with that
staged content instead, which is how you tell each mutant has been
reverted.

## 2. List the mutants before running any

For each function, apply every operator below that fits it, each change as
its own mutant:

1. **relational and boundary:** `<` ↔ `<=`, `>` ↔ `>=`, `===` ↔ `!==`, or
   the language's equivalents.
2. **logical:** `&&` ↔ `||`, `??` → `||`.
3. **negation:** negate a condition.
4. **arithmetic:** `+` ↔ `-`, `*` ↔ `/`, drop a `+ 1` or `- 1`.
5. **statement deletion:** delete a statement or call, including a push,
   an assignment, or a guard's early return.
6. **return value:** replace what is returned with null or undefined, an
   empty string, array or object, `true` ↔ `false`, or a constant.
7. **null guard:** remove one, such as `a?.b` → `a.b`, or the language's
   equivalent.
8. **literal:** change a string literal only where it is compared, used as
   a key or identifier, or is user-visible output a spec defines; change a
   numeric constant only where it is a limit or boundary in logic.

Never mutate these, because their tests rightly do not pin them: logging;
metrics and monitoring counters; sleeps, timeouts and deadlines; capacity
or size hints; caches and memoization; configuration flags; type-only
code; and log or error-message wording no spec defines.

Skip a mutant that plainly cannot change behaviour, and write down why.

**The cap.** On any one line, at most one mutant per operator. In all, at
most your cap. When the list is longer, keep mutants on changed lines
first, then the rest of the function. Within each of those two groups,
keep operators in this order: relational, logical, statement deletion,
return value, then negation, arithmetic, null guard and literal. Report how many you dropped.

## 3. Run each mutant

One at a time:

1. Make the one edit in the copy.
2. Run the focused command. Killed if any test that passed on the
   unmutated copy now fails, or the build or typecheck the command runs
   fails, or the run times out.
3. If a flaky test is the only one that failed, the mutant is
   `needs serial rerun`, not killed. Name the test.
4. If it survived the focused command, run the full-suite command with the
   mutant still applied. Before the first such run, revert the mutant, run
   the full suite once on the unmutated copy and record its flaky and
   failing tests as in section 1, then apply the mutant again. Killed if
   anything fails that passed on the unmutated copy, by the same rule for
   flaky tests; otherwise it survived.
5. Revert the edit: `git -C <copy path> checkout -- <file>`. Then the copy
   must be clean again, by the check in section 1, before the next mutant.

## 4. Judge each survivor

For each survivor, say what behaviour is unpinned: what a caller could get
from the mutant that it would not get from the real code, or what a test
would have to check to notice. Then say whether it is equivalent, meaning
no test that calls the code through its public entry points could ever
tell it from the real code, and why: `yes`, `no`, or `unsure`. A mutant
that changes only code no caller or entry point reaches is equivalent and
also dead code: say which code that is, and why nothing reaches it.

## 5. Report

Begin your report with the line `mutation report`, then one entry per
mutant in the order run:

  M<n> <file>:<line> <function> <operator>
    `<original>` → `<mutated>`
    killed by <test name> | killed: timeout | killed: build failed |
    needs serial rerun (<flaky test>) | survived

A survivor adds three lines:

    unpinned: <what no test checks>
    equivalent: yes | no | unsure — <why>
    dead code: no | yes — <the code nothing reaches, and why>

Then:

  skipped: <one line per skipped mutant: file:line, operator, why>
  dropped by the cap: <count>
  flaky: <tests> · failing on the unmutated copy: <tests>
  per operator: <operator> <mutants> mutants, <killed> killed, <survived> survived; one line each
  gh calls refused: <the number of lines in the log file>
  copy clean: yes | no — <what the check in section 1 printed after the last revert>

## 6. If you are resumed for serial reruns

You may later be sent mutants marked `needs serial rerun`, yours or
another subagent's, while no other mutation run is going. For each one:
make its edit and run only its flaky test, alone and in serial mode. It
is killed if that test fails again. If it passes, the mutant survived the
command that flagged it: after the focused command, carry on from step 4
of section 3; after the full suite, it survived, and you judge it as in
section 4. Revert before the next one. Report each in the form of section 5,
under the line `serial reruns`.
