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

Ask your agent to *"adopt spec-trace in this repo"*, or do it by hand from the
repository root:

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
and renamed requirements applied. `check` never reads open changes.

Test files are found by default under `test/`, `tests/` and `__tests__/`, and
by the names `*_test.*`, `*.test.*`, `*.spec.*` and `test_*.py`. Pass
`--tests GLOB` (repeatable) to use your own patterns instead; `**`, `*`, `?`,
`{a,b}` and `[...]` work. If a pattern is malformed or matches no file, the
command stops with exit code 2 instead of treating the scenarios its files
would tag as untagged. Files git ignores, `node_modules/` and nested
repositories are skipped.

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
