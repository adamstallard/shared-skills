# spec-trace — decisions

**Read this before changing `scripts/spec_trace.py`.** Each entry is a
decision, why it was made, and what was tried and rejected.

---

## The test names the scenario; the spec never names the test

**Decision.** The link is a tag in the test file,
`@scenario <capability>: <Scenario name>`. Specs carry no pointer to tests.

**Why.**
- **The tag moves with the test.** A test that is renamed, moved to another
  file or split keeps its tag. A path written in the spec would break on each
  of those, and nothing in the spec's own review would notice.
- **The spec stays short.** Reviewing the spec is the slow part of the work,
  and a list of test paths under every scenario adds lines that reviewer must
  read and that say nothing about what must be true.
- **A spec line would drift.** A pointer in the spec is checked only when the
  spec is edited. The tag sits next to the code it describes, and `check`
  reads every tag on every run.

**Rejected: a test path or test name under each scenario in the spec.** It
makes the spec longer, and it breaks whenever a test file is renamed or
moved.

## Only the main specs are checked

**Decision.** `check` requires tags only for scenarios in
`openspec/specs/*/spec.md`. A tag may also name a scenario that exists only in
an open change in `openspec/changes/`: one the change adds under an ADDED or
MODIFIED requirement, or one under a requirement the change renames, written
with the requirement's new name. Such a tag is accepted, neither counted nor
reported. A bare name that repeats within the change is ambiguous, as in the
main specs. `report --include-changes` applies each open change's delta to the main specs, for a local view: an ADDED or MODIFIED
requirement replaces the one of that name, REMOVED drops it, and RENAMED
renames it. Merging a change's scenarios in without applying its delta would
list a modified scenario twice, once from the main spec and once from the
change, and a bare tag naming it would then fail as ambiguous.

**Why.** A repository that reviews a spec before its code (igor, the
repository this skill was built for, does) opens a pull request holding only
a proposed spec change, with no implementation and no tests, and it must pass
CI. Scenarios move into
`openspec/specs/` when the change is archived, which is after its
implementation and tests exist. From then on, `check` requires their tags.
A change can be archived in a commit after its implementation merges, as
igor's are, so the tests are written before their scenarios reach
`openspec/specs/`. Accepting tags for an open change's scenarios lets the
pull request that writes a test tag it.

**Rejected: requiring tags for open changes' scenarios.** It would fail every
spec-only pull request.
**Rejected: treating a tag for an open change's scenario as an orphan.** The
implementation pull request could then not tag its tests, and the tags would
have to go into the archive commit.

## The baseline only shrinks

**Decision.** The baseline lists scenarios that no test tagged at adoption.
`check` fails on a scenario that is untagged and absent from the baseline,
and also on a baseline line whose scenario is now tagged or no longer exists.

**Why.** A repository adopting this has hundreds of untagged scenarios, and
tagging them all first would block adoption. Failing on a stale line means
the line comes out in the same change that tags its scenario. The list can
only get shorter, and it always lists exactly the scenarios still untagged.

**Rejected: a baseline that tolerates stale lines.** A tagged scenario left
in the baseline stays exempt: if its only test is later deleted, `check`
still passes.

## It checks that a tag exists, not that the test passes

**Decision.** `check` reads text. It does not run tests or parse a test
framework.

**Why.** The repository's own test run already fails on a failing test, and
running tests a second time per framework would make the checker depend on
every language it supports. Whether the tagged test really checks the
scenario's WHEN and THEN is a judgment, made when the tag is reviewed.

## A scenario is its capability and its name; a repeated name adds the requirement

**Decision.** A scenario's identity is `<capability>: <Scenario name>`, with
runs of whitespace collapsed and case kept. When a scenario name appears more
than once in one capability, every scenario with that name is identified as
`<capability>: <Requirement name> / <Scenario name>`, in tags and in the
baseline. A bare tag for such a name fails as ambiguous and lists the
qualified tags. The qualified form is accepted for any scenario. Two
scenarios with the same name under the same requirement fail `check`, since
no tag can tell them apart.

**Why.** igor's specs held 468 scenarios when this was written, and one name
repeated: `task-execution` has "An ordinary run is unaffected" under two
requirements. Qualifying only the repeated names keeps every other tag short.
Requiring the qualifier for those names means a tag never quietly counts for
the wrong scenario.

**Rejected: always including the requirement.** Every tag would grow by a
requirement name, often a long sentence, to handle one case in 468.
**Rejected: counting a bare tag for every scenario with that name.** One test
would then cover two scenarios that say different things.

## A tag's name is the longest scenario name it starts with

**Decision.** The text after `<capability>:` is matched against the known
scenario names. The longest one that the text starts with wins, provided the
line ends there or one of these follows: a quote, `)`, `,`, `;`, `{`, `*/`,
`-->`, or a period followed by a space, the end of the line, a quote, `)`,
`*/` or `-->`. Every decision about a tag, which scenario it names and whether it
is ambiguous, goes through that one match, over the main specs and the open
changes together; on a tie, the main specs win. Matching the main specs first
would go wrong when an open change adds "Claim precedes work, always" and
the main specs have "Claim precedes work": a tag naming the change's
scenario would be counted as covering the main one. When a repeated scenario name is
a longer match than any unique one, the tag is ambiguous. Without that rule,
in a spec where "Item assigned, on Linear" appears under two requirements and
"Item assigned" under one, a bare tag for "Item assigned, on Linear" would
count for "Item assigned". The text shown in an error message is cut
separately and never decides anything.

**Why.** A tag inside a test name is followed by the rest of the line,
`', async () => {`, so the name can't run to the end of the line. Ending the
name at the first quote fails too: scenario names contain apostrophes ("The
worker's ..."). Matching against known names handles both. The rule about
what follows keeps a tag for "Claim precedes work twice" from counting for
"Claim precedes work". A period counts only before a space or the end of the
line or a closer, so a tag can end a sentence, as in a Python docstring
ending `work."""`, while `Foo.bar` never matches `Foo`.

**Rejected: deciding ambiguity from the displayed text.** The display text
is cut by rules of its own: at a comment closer, and at a quote that a `,`,
a `)` or the line's end follows. Those rules guess where a test name ends.
When ambiguity was decided from that text, a guess that left
`', async () =>` after a repeated name meant the text matched no repeated
name exactly, so the tag failed as naming no scenario instead of as
ambiguous.

**Where it stops applying.** A tag whose scenario was removed or renamed
still counts for a shorter scenario its text starts with, when a tag end
follows that shorter name: with "A conflict is resolved" in the spec, a stale
tag for "A conflict is resolved, not regenerated" counts for it. Likewise,
once a scenario "Foo. More prose" is removed, its stale tag counts for a
scenario "Foo". Reporting these would mean refusing
any text after a name, which a tag inside a test name always has. igor has
no such pair of names, so this was accepted.

## An escaped quote is part of the name

**Decision.** `\'` and `\"` in a tag are read as `'` and `"`, and an escaped
quote never ends the tag.

**Why.** igor's tests use single-quoted names, where an apostrophe is
written `\'`, and 28 of its scenario names contain one. Unescaping alone is
not enough: `'` ends a tag, so `A person\'s command` would then count for a
scenario named `A person`.

## Test file globs that match nothing stop the command

**Decision.** Globs support `**`, `*`, `?`, `{a,b}` and `[...]`. When a
`--tests` glob is malformed or matches no file, `check`, `baseline` and
`report` exit 2 and write nothing. Each glob is tested on its own. When the
default globs match nothing, the command warns and carries on.

**Why.** A glob that matches nothing finds no tags, so the scenarios only its
files would tag look untagged, `baseline` writes them, and `check` then
passes without reading those files. A glob that matches nothing usually
comes from a typo or from glob syntax the checker doesn't know. A second glob
that does match would hide the first from a check of all of them together,
which is why each is tested alone. The default globs matching nothing is
different: a repository with specs and no tests yet can still adopt with a
full baseline.

## Test files come from git when it is available

**Decision.** Files are listed with `git ls-files --cached --others
--exclude-standard`, so ignored files are skipped. Outside a git repository
the tree is walked, skipping `.git`, `node_modules` and any directory holding
a `.git` entry.

**Why.** A local clone can hold other worktrees under an ignored directory,
such as `.claude/worktrees/`, each with a full copy of the tests. Scanning
them would count their tags, including tags for scenarios that the branch
being checked doesn't have.

## A code fence closes only with its own kind of line

**Decision.** Headings inside a code fence are not read, in a spec or in a
change's delta. A fence opened with backticks or tildes closes only on a
line of the same character, at least as long, with nothing else on it.

**Why.** A spec that shows a Markdown example puts it in a `~~~` fence when
the example itself holds a ```` ``` ```` fence. Closing on any fence line
would end the example at that inner line, read the example's headings as
real ones, and then skip the rest of the file as fenced.

## Test globs come from the test runner's configuration file

**Decision.** Without `--tests`, the test file globs are read from the
repository's test runner configuration: Vitest's `test.include` and
`test.exclude`, Jest's `testMatch` or `testRegex`, pytest's `testpaths` and
`python_files`, and for Go and Rust their fixed layouts. A runner whose
configuration names no globs gets that runner's own default. The file is
read as text: a JavaScript config yields its globs only when they are
string literals, found by walking the object keys (`test` then `include`, so
`coverage.include` is not mistaken for them). Anything computed, such as
`include: dirs.map(...)`, is reported, not guessed: see the next entry.
`openspec/spec-trace-tests.txt` replaces detection, and `--tests` wins over
both.

**Why.** The runner's configuration is what decides which files are tests,
so reading it keeps spec-trace from reading a helper file as a test or
missing a test the runner runs. The source is printed every time, because a
wrong guess is otherwise invisible: it shows up only as scenarios that look
untagged.

**Rejected: parsing the test script in package.json.** It is usually just
`vitest run` or `jest`, which names no files; the configuration file does.
**Rejected: running the runner to list its tests** (`vitest list`, `pytest
--collect-only`). It needs the repository's dependencies installed, which
spec-trace's CI step does not have.

**Where it stops applying.** Rust's unit tests live in `#[cfg(test)]`
modules inside ordinary source files, which no glob can tell apart, so every
`.rs` file under `src/` is read. Jest's `<rootDir>` is taken to be the
repository root. `testRegex` is searched in the file's path with a `/` put
in front, since Jest matches it against an absolute path: a pattern such as
`/__tests__/` then matches a top-level `__tests__` directory too.

## A configuration that cannot be read is reported, and blocks the baseline

**Decision.** A detector that cannot read its runner's configuration with
confidence contributes no globs and prints a warning: the file, what it
could not read, the globs used instead, and how to set them by hand. The
other runners' globs still count; with none, the defaults apply. `baseline`
exits 2 while any such warning stands, unless the globs are set by hand.

**Why.** A wrong guess at the test files shows up only as scenarios that
look untagged, and `baseline` would write them into the baseline, where they
stay exempt even though a test tags them. Reporting costs a warning;
guessing hides a tag for as long as the guess stands, since `check` runs
with the same wrong globs and never sees the test that would flag the line. These cases are treated as unreadable
rather than parsed:
- in a JavaScript config: a regex literal (a `/` outside strings and
  comments), a template string with `${...}`, a computed, shorthand or spread
  value, or a `test` setting that is not an object literal;
- settings that change which files are tests or where globs start: Vitest's
  projects, workspaces, `includeSource`, `root` and `test.dir`, and Jest's
  `projects`, `rootDir` and `roots`;
- a negated Jest `testMatch` entry;
- `pytest.toml`, pytest's native `[tool.pytest]` table, and `pyproject.toml`
  on Python before 3.11, which has no `tomllib`;
- a Vitest, Jest or pytest configuration below the repository root, which
  applies to its own directory.

Any other error while reading a configuration becomes the same kind of
warning, never a crash. Each runner's excludes apply to its own globs only,
so Vitest excluding `backend/**` does not hide pytest's tests there.

**Rejected: a full JavaScript parser.** Reading these configs exactly means
evaluating them: a parser still cannot know what `dirs.map(...)` or an
imported setting yields. Refusing every construct outside a small, known set
gives the same warnings with far less code, and nothing it doesn't know can
slip through as a guess.

## The test globs can be set by hand, in a file next to the baseline

**Decision.** `openspec/spec-trace-tests.txt`, when present, lists the test
globs, one per line, `!` to exclude and `#` for comments. It replaces
detection. `--tests` still wins over it.

**Why.** A repository whose configuration spec-trace cannot read needs a
setting that CI and every agent pick up without a flag. Next to the
baseline, it is in the one directory spec-trace already owns, and a plain
list of globs needs no parser.

## Known issues

- An orphan tag's text (a tag that names no scenario) is shown cut short when a single quote followed by a
  comma sits inside the name, as in `Says "hi" to 'Bob', twice`. Only the
  error message is affected; the tag is still reported.
