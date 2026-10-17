---
name: spec-trace
description: >-
  Link tests to OpenSpec scenarios: each test names the scenario it checks
  with an `@scenario <capability>: <Scenario name>` tag, and a checker fails
  CI on a scenario no test tags or a tag that names no scenario. Use when
  writing or changing a test in a repository that has openspec/specs/, when
  archiving an OpenSpec change, when a spec-trace CI step fails, or when the
  user asks to "trace tests to specs", "tag the scenario", "which tests cover
  this spec" or to adopt or decline spec-trace in a repository, or when its
  hook says the repository has not decided.
---

# spec-trace

A test names the OpenSpec scenario it checks, with a tag in the test file:

```ts
// @scenario work-claiming: Claim precedes work
it("takes the claim before invoking the worker", async () => { ... });
```

`scripts/spec_trace.py check` fails when a scenario in `openspec/specs/` has
no tag and isn't in the repository's baseline, or when a tag names no
scenario. CI runs it; nothing runs it on commit, so run `check` yourself
after tagging.

```bash
T="<base directory>/scripts/spec_trace.py"
```

`<base directory>` is the directory that holds this SKILL.md. Claude Code
shows it on a "Base directory for this skill:" line just before this file's
text. Write the path out in full. Don't use `~/.agents/skills/spec-trace`
instead: that install may be missing, or be a different version of the
script from this one.

## The tag

`@scenario <capability>: <Scenario name>`, anywhere in a test file: a comment
above the test, or inside the test's name.

- `<capability>` is the directory name under `openspec/specs/`.
- `<Scenario name>` is the text after `#### Scenario:` in that spec, as
  written. Case counts; runs of spaces don't.
- A test may carry several tags, one per line or several on a line. A
  scenario may be tagged by several tests.
- **A name that repeats within one capability** is written with its
  requirement: `@scenario <capability>: <Requirement name> / <Scenario name>`.
  A bare tag for such a name fails as ambiguous, and the failure lists the
  tags to choose from.
- The tag ends at the end of its line, or where a quote, `)`, `,`, `;`, `{`,
  `*/`, `-->` or a sentence's closing period follows the name. Inside a quoted
  test name, write an apostrophe the way the language escapes it (`\'`): an
  escaped quote is part of the name and never ends the tag.

Tag a test only when it checks that scenario's WHEN and THEN. A tag on a test
that merely touches the area makes the scenario look covered when it isn't.

**Never edit a spec to point at a test.** The spec stays as it is; the test
carries the link.

## Commands

Run from the repository root:

```bash
python3 $T check             # exit 1 on any problem, each named with file:line and its fix
python3 $T report            # markdown table per capability: scenario, tests that tag it
python3 $T report --include-changes   # the same, with open changes applied: what an implementation has left to test
python3 $T baseline          # write every untagged scenario to a new baseline file; refused once one exists
python3 $T baseline --prune  # remove the baseline lines check fails on; never adds one
python3 $T state             # adopted, declined, undecided or unknown; n/a without openspec/
python3 $T decline           # write openspec/spec-trace.yaml, declining it for the repository
```

**Which files are tests.** Without `--tests`, the globs come from the
repository's test runner configuration:

| Runner | Read from |
| --- | --- |
| Vitest | `test.include` and `test.exclude` in `vitest.config.*` or `vite.config.*`, else Vitest's default include |
| Jest | `testMatch` or `testRegex` in `jest.config.*` or the `jest` key of `package.json`, else Jest's default `testMatch` |
| pytest | `testpaths` and `python_files` in `pytest.ini`, `.pytest.ini`, `pyproject.toml`, `tox.ini` or `setup.cfg`, else pytest's default `test_*.py` and `*_test.py` |
| Go | `*_test.go`, when a `go.mod` exists anywhere in the repository |
| Rust | every `.rs` file under `tests/` and `src/`, when a `Cargo.toml` exists anywhere |

With no such configuration the defaults apply: `test/`, `tests/`,
`__tests__/`, `*_test.*`, `*.test.*`, `*.spec.*` and `test_*.py`. Every
command prints the source it used on stderr, as `spec-trace: test files from
...`.

A configuration spec-trace cannot read with confidence prints a warning
naming the file, what it could not read, and the globs used instead: the
other runners' globs, or the defaults. Examples are a computed or shorthand
`include`, Vitest projects or `includeSource`, a `root` or `rootDir` setting,
Jest `projects`, a regex literal anywhere in the file, a negated Jest
`testMatch` entry, `pytest.toml`, `pyproject.toml` on Python before 3.11,
and any runner configuration below the repository root. While there is such
a warning, `baseline` and `baseline --prune` refuse to write (exit 2).

**Setting the globs by hand.** When detection warns or picks the wrong
files, list the globs in `openspec/spec-trace-tests.txt`, one per line, with
`!` before a glob to exclude and `#` for comments. When that file exists it
replaces detection, in CI as well. `--tests GLOB` (repeatable) wins over
both. A glob may use `**`, `*`,
`?`, `{a,b}`, `[...]` and the extglobs `?(...)`, `*(...)`, `+(...)` and
`@(...)`. When a glob from `--tests` or `openspec/spec-trace-tests.txt` is
malformed or matches no file, every command exits 2 and writes nothing.

`--baseline PATH` moves the baseline from `openspec/spec-trace-baseline.txt`.

## What `check` fails on, and the fix

| Failure | Fix |
| --- | --- |
| `no test tags scenario 'cap: Name'` | Add the printed tag to the test that checks it. If no test checks it, write one. Never add the scenario to the baseline. |
| `tag ... names no scenario` | The scenario was renamed: change the tag to the new name (the message suggests the closest). It was removed: delete the tag. |
| `tag ... is ambiguous` | Use one of the qualified tags the message lists. |
| `baseline ... is now tagged` | Run `python3 $T baseline --prune`, and commit the pruned baseline with the change that added the tag. |
| `baseline ... names no scenario` | Run `python3 $T baseline --prune`, and commit the pruned baseline with the change that renamed or removed the scenario. |

The baseline only shrinks: lines come out as tests get tagged, and no line is
ever added after adoption. `baseline --prune` only removes lines. Plain
`baseline` refuses (exit 2) once the file exists, because writing it again
would add every scenario untagged today.

`check` confirms that a test file carries the tag. It does not run the test
and cannot tell whether the test checks what the scenario says. The
repository's own test run covers passing; the review covers whether the tag
is honest.

## Implementing and archiving a change

`check` requires a tag only for scenarios in `openspec/specs/`, so a
pull request that only proposes a spec needs no tags. A tag may already name
a scenario that an open change in `openspec/changes/` adds: `check` accepts it
without requiring it. So tag the tests in the pull request that writes them.

**While implementing an open change,** run
`python3 $T report --include-changes`. `check` can't show which of the
change's scenarios still lack a test, because they reach `openspec/specs/`
only at the archive. The command prints the table for the specs as they will
be once every open change is archived; it applies the changes in memory and
writes no file. Rows marked `(change: <name>)` are that change's scenarios:
every scenario of a requirement it adds, modifies or renames, unchanged ones
included. `none` in the Tests column means no test tags that row's scenario
yet.

- Tag a test for each of your change's `none` rows before you say the work
  is done.
- For each tag that the output's `### Problems` section, below the tables,
  says names no scenario, change the tag to the scenario's current name, or
  delete it if the scenario is gone. Most such tags name a scenario the
  change removes or renames.
- Before opening the implementation pull request, paste your change's part
  of the output into its body, so the reviewer sees which test covers each
  scenario. For each capability the change touches, that is the `###`
  heading, the `| Scenario | Tests |` and `| --- | --- |` lines, and the
  change's rows. It is already markdown.

Don't add `report --include-changes` to CI: it always exits 0, so it can't
fail a build. CI runs `check`.

Archiving moves a change's scenarios into `openspec/specs/`, and from then on
`check` requires a tag for each one. So before the archive lands, every
scenario it adds must have a tagged test. A scenario under a requirement it
renames needs one too when its name repeats in the capability: its tag
carries the requirement's name, so the old tag no longer matches. Run
`check` to confirm.

## Adopting or declining it in a repository

spec-trace's hook runs after you write or edit a `spec.md` under
`openspec/specs/` or `openspec/changes/<name>/specs/` at the top of a git
repository. When the repository has neither adopted nor declined
spec-trace, it adds a note telling you to ask the user. When you get that
note, or the user asks, ask the user whether to adopt it or decline it, and
do what they choose. Don't decide for them.

To see where a repository stands, run `python3 $T state`. It prints
`adopted`, `declined`, `undecided` or `unknown`; ask the user only when it
says `undecided`. On `unknown` it says why, on stderr:
- `openspec/spec-trace.yaml` holds something other than `adoption: declined`:
  show the user the file and ask what it should say.
- It cannot be read, for example because it is a folder or a broken link:
  tell the user what is at that path and ask whether to delete it.

**To adopt:**

1. From the repository root, run `python3 $T baseline`. It writes
   `openspec/spec-trace-baseline.txt` listing every scenario no test tags
   yet.
2. Add the CI step from this skill's [README](README.md#ci). It fetches
   `spec_trace.py` pinned to a full commit SHA of shared-skills.
3. Add one line to the repository's AGENTS.md or CLAUDE.md, in its own voice,
   saying that a test tags the OpenSpec scenario it checks with
   `@scenario <capability>: <Scenario name>`, and pointing at this skill.
4. If `openspec/spec-trace.yaml` exists, delete it. Adoption wins over it,
   but the repository should not say both.

Show the user the new and changed files before committing them.

**To decline:** run `python3 $T decline`. It writes `openspec/spec-trace.yaml`
holding `adoption: declined`, and changes nothing else; `--dry-run` shows
what it would write. Commit the file.

Either way, the commit is what stops every agent on the team from asking
again. The commit touches `openspec/`. If the repository has a commit hook
that requires a trailer on such commits (spec-check's `Spec-check:`, for
example), add the trailer that hook asks for.

Tagging existing tests is optional at adoption. Tag one where it plainly
checks a scenario's WHEN and THEN. If you tag tests after step 1 wrote the
baseline, run `python3 $T baseline --prune`, so
`openspec/spec-trace-baseline.txt` lists exactly the scenarios still
untagged.

After changing the script, run its tests from the root of your
shared-skills clone:

```bash
python3 .agents/skills/spec-trace/scripts/test_spec_trace.py
```
