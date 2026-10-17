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

The checker, `scripts/spec_trace.py`, is one Python 3 file, and needs
nothing else but git. It reads text, so the tag works in any language's test
files.

## What it does not check

It checks that a tag exists for each scenario. It does **not**
run the test, so it doesn't know whether the test passes; the repository's
own test run does that. It also can't tell whether the tagged test really
checks what the scenario says: that is for the person reviewing the test.

A tag counts even when its test is skipped, or sits in a file your test
runner excludes. For excluded files, add the path to
`openspec/spec-trace-ignore.txt` (see [Where it looks for
tags](#where-it-looks-for-tags)). `report` ends with a list of the
directories where it found tags, which is how to spot such files.

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
  (`openspec/spec-trace-baseline.txt`), or a GitHub workflow that runs
  `spec_trace.py`.
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
   `baseline --prune` removes such lines and never adds one. Running
   `baseline` again is refused once the file exists: it would add every
   scenario untagged today, exempting new scenarios that have no test. Keep
   the file once every scenario is tagged: it records that the repository
   adopted spec-trace.

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

`actions/checkout` leaves a git clone, which the checker needs to find
tags.

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
request, and then *Where tags were found*: each directory holding tags, with
its count of files and tags. `check` requires tags only for scenarios in
`openspec/specs/`.

**While implementing an open change.** A change's scenarios stay in
`openspec/changes/` until the change is archived, and its tests are written
before that, whether the code comes in the spec's pull request or, where a
spec is reviewed before its code, in a later one. Until the archive, `check`
and plain `report` can't see those scenarios, and CI won't flag a missing
test.

`report --include-changes` builds the table from the specs as they will be
once every open change is archived. It applies each change in memory, and
changes no file: an added requirement joins its spec, a modified one
replaces the requirement of the same name, a removed one goes, and a renamed
one takes its new name. Each of the change's scenarios is marked
`(change: <name>)`, including the unchanged scenarios of a requirement it
modifies or renames. `none` in the Tests column means no test tags that
scenario yet:

```markdown
### work-claiming (3 of 5 tagged)

| Scenario | Tests |
| --- | --- |
| Claim precedes work | tests/claim.test.ts:1 |
| Stale claim expires (change: claim-expiry) | tests/claim.test.ts:5 |
| Fresh claim holds (change: claim-expiry) | none |
| Release on finish (change: claim-expiry) | tests/claim.test.ts:3 |
| Release on crash (change: claim-expiry) | none |
```

Run `report --include-changes` while writing the change's tests, and again
before calling the work done: each `none` row of the change still needs a
test. A tag that names a scenario the change removes or renames is listed
below the tables, under `### Problems`: change it to the scenario's new
name, or delete it.

When you open the implementation pull request, paste the change's part of
the output into the body, so the reviewer sees which test covers each
scenario. For each capability the change touches, that is the `###` heading,
the `| Scenario | Tests |` and `| --- | --- |` lines, and the change's rows.

`report --include-changes` always exits 0, so it can't fail a build; CI runs
`check`.

## Where it looks for tags

spec-trace searches every file under the repository root whose path
`.gitignore` doesn't match, tracked or not, with one `git grep`. So
`check`, `report` and `baseline` need git and must run in a git clone. `state` and `decline` work without
git. The search leaves out:

- files `.gitignore` matches, even ones git tracks, and binary files and
  nested repositories. A test committed under an ignored path is not
  supported: move it;
- doc files: `*.md`, `*.mdx`, `*.rst`, `*.adoc` and `*.txt`;
- everything under `openspec/`.

Tags belong in tests, but a tag in any other file counts too. Text that
only looks like a tag, such as another tool's syntax, almost never names one
of your scenarios exactly, so `check` fails on it as a tag that names no
scenario. When that happens in a file that is not a test, such as a vendored
library or an HTML doc, list the path in `openspec/spec-trace-ignore.txt`:
one git glob pattern per line, relative to the repository root, with `#` for
comments.

```text
# Not tests: a vendored library, and docs that show tags as examples.
vendor/**
docs/*.html
```

If git rejects a pattern, every command that reads tags stops with git's
error and exit code 2.

## When `check` fails

Each problem is printed with its file and line and the fix:

- **No test tags a scenario.** Tag the test that checks it with `@scenario`
  followed by the printed `capability: name` line, or write that test.
- **A tag names no scenario.** The scenario was renamed or removed. Update or
  delete the tag; the message suggests the closest name. If the file is not
  a test, list it in `openspec/spec-trace-ignore.txt` instead.
- **A baseline line is now tagged, or names no scenario.** Run
  `spec_trace.py baseline --prune`, and commit the pruned baseline with the
  change that tagged the scenario or removed it.

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
