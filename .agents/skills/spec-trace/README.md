# spec-trace

Links each test to the OpenSpec scenario it checks, and fails CI when a
scenario has no test or a test names a scenario that no longer exists.

In a repository that uses [OpenSpec](https://github.com/Fission-AI/OpenSpec),
each spec in `openspec/specs/<capability>/spec.md` lists requirements, and
each requirement has `#### Scenario:` blocks saying WHEN something happens,
THEN what must be true. spec-trace makes the test carry the link: a tag in
the test file names the scenario.

```ts
// @scenario work-claiming: Claim precedes work
it("takes the claim before invoking the worker", async () => { ... });
```

The specs are never edited to point at tests, so they don't grow.

The checker, `scripts/spec_trace.py`, is one Python 3 file with no
dependencies. It reads text, so the tag works in any language's test files.

## What it does not check

It checks that a test file carries a tag for each scenario. It does **not**
run the test, so it doesn't know whether the test passes; the repository's
own test run does that. It also can't tell whether the tagged test really
checks what the scenario says: that is for the person reviewing the test.

## The tag

`@scenario <capability>: <Scenario name>`, in a comment above the test or in
the test's name. `<capability>` is the directory under `openspec/specs/`, and
the name is copied from the spec's `#### Scenario:` line. A test may carry
several tags, and several tests may tag one scenario.

When a scenario name appears under two requirements in one spec, the tag
names the requirement too:
`@scenario <capability>: <Requirement name> / <Scenario name>`.

## Adopting it in a repository

Your agent asks the first time it writes scenarios in a repository that uses
OpenSpec. When the agent writes or edits a `spec.md` in the `openspec/`
folder at the top of a git repository, under `openspec/specs/` or
`openspec/changes/`, spec-trace's hook checks whether the repository has
adopted spec-trace or declined it. If it has done neither, the hook tells
the agent to ask you. You can also ask it yourself: *"adopt spec-trace in
this repo"* or *"decline spec-trace in this repo"*.

The answer lives in the repository, so once it is committed, every agent on
the team stops asking:

- **Adopted:** the repository has the baseline file
  (`openspec/spec-trace-baseline.txt`), a GitHub workflow that
  runs `spec_trace.py`, or `openspec/spec-trace-tests.txt`.
- **Declined:** `openspec/spec-trace.yaml` holds the line
  `adoption: declined`. `spec_trace.py decline` writes it (`--dry-run` shows
  what it would write). OpenSpec's own `config.yaml` is not touched. To adopt
  after declining, follow the adopt steps and delete `spec-trace.yaml`, so
  the repository doesn't say both. A `spec-trace.yaml` left behind after
  adopting does no harm: adoption wins.

`spec_trace.py state` prints `adopted`, `declined` or `undecided`. It prints
`unknown` when `spec-trace.yaml` holds anything else or cannot be read; the
hook then stays silent, and `decline` refuses until the file is fixed or
deleted.

The hook is on when spec-trace is installed. It is silent outside OpenSpec
repositories and in any repository that has answered, and it never blocks.
In Cursor the hook is wired to `postToolUse`, but nobody has yet checked
that its note reaches the agent there. To turn it off, run
`python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook spec-trace`;
manage-skills' README has the details.

To adopt by hand, from the repository root:

1. **Write the baseline**, the list of scenarios no test tags yet:

   ```bash
   python3 ~/.agents/skills/spec-trace/scripts/spec_trace.py baseline
   ```

   It writes `openspec/spec-trace-baseline.txt`. Commit it. Every scenario
   added to `openspec/specs/` from then on needs a tagged test, and the
   baseline only shrinks: `check` fails on a line whose scenario is now
   tagged, so the line comes out in the same change that adds the tag.

2. **Add the CI step** below.

3. **Tell agents and contributors.** One line in AGENTS.md or CLAUDE.md: tests
   tag the OpenSpec scenario they check with
   `@scenario <capability>: <Scenario name>`, see the spec-trace skill.

### CI

A GitHub Actions workflow, for example `.github/workflows/spec-trace.yml`:

```yaml
name: spec-trace
on: [push, pull_request]
jobs:
  spec-trace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Every scenario in openspec/specs is tagged by a test
        env:
          # A full commit SHA of adamstallard/shared-skills, never a branch.
          SPEC_TRACE_SHA: <40-character commit SHA>
        run: |
          curl -fsSL "https://raw.githubusercontent.com/adamstallard/shared-skills/$SPEC_TRACE_SHA/.agents/skills/spec-trace/scripts/spec_trace.py" -o "$RUNNER_TEMP/spec_trace.py"
          python3 "$RUNNER_TEMP/spec_trace.py" check
```

The SHA pins the exact checker your CI runs. A branch name would let a
change to shared-skills fail your CI, or pass it, without any change in your
repository.

**To update the pin**, take the newest commit that touches the checker,
`git -C <shared-skills clone> log -1 --format=%H -- .agents/skills/spec-trace/scripts/spec_trace.py`,
put it in `SPEC_TRACE_SHA`, and run the new checker locally with `check`
before pushing.

## Day to day

```bash
python3 ~/.agents/skills/spec-trace/scripts/spec_trace.py check    # what CI runs
python3 ~/.agents/skills/spec-trace/scripts/spec_trace.py report   # table of scenarios and their tests
```

`report` prints a markdown table per capability, ready to paste into a pull
request. `report --include-changes` shows the specs as the open changes in
`openspec/changes/` will leave them once archived: added, modified, removed
and renamed requirements applied. `check` requires tags only for scenarios in
`openspec/specs/`.

Test files are the ones your test runner's configuration names: Vitest's
`test.include`, Jest's `testMatch` or `testRegex`, pytest's `testpaths` and
`python_files`, Go's `*_test.go`, or Rust's `tests/` and `src/`. Each command
prints which source it used, for example `spec-trace: test files from
vitest.config.ts (Vitest's default include)`. With no runner configuration
the defaults apply: `test/`, `tests/`, `__tests__/`, `*_test.*`, `*.test.*`,
`*.spec.*` and `test_*.py`.

If spec-trace cannot read a configuration with confidence, for example
because its globs are computed in code, it warns on stderr, names the file
and what it could not read, and says which globs it used instead. While such
a warning stands, `baseline` refuses to write: the globs used instead may
miss real tests, and the scenarios those tests tag would look untagged and
be written into the baseline, exempt from then on.

To set the globs yourself, list them in `openspec/spec-trace-tests.txt`, one
per line (`!` before a glob excludes, `#` starts a comment). That file
replaces detection everywhere, CI included. `--tests GLOB` (repeatable) wins
over both, for one run. `**`, `*`, `?`, `{a,b}`, `[...]` and extglobs such as
`?(x)` work. If a glob you set, in that file or with `--tests`, is malformed
or matches no file, the command stops with exit code 2. If it carried on, the
tests that glob was meant to find would go unread, and the scenarios they tag
would look untagged. Files git ignores,
`node_modules/` and nested repositories are skipped.

## When `check` fails

Each problem is printed with its file and line and the fix:

- **No test tags a scenario.** Add the printed tag to the test that checks
  it, or write that test.
- **A tag names no scenario.** The scenario was renamed or removed. Update or
  delete the tag; the message suggests the closest name.
- **A baseline line is now tagged, or names no scenario.** Delete the line.

`check` requires a tag only for scenarios in `openspec/specs/`, so a pull
request that only proposes a spec passes. A test may already tag a scenario
that an open change adds; `check` accepts that tag. Archiving the change
moves its scenarios into `openspec/specs/`, and from then on each needs a
tagged test.

## Tests

```bash
python3 .agents/skills/spec-trace/scripts/test_spec_trace.py
```

Why it works this way: [DECISIONS.md](DECISIONS.md).
