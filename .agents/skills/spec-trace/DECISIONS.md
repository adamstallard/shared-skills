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

## A missing `openspec/specs/` holds no scenarios; a missing `openspec/` is an error

**Decision.** When `openspec/` exists and `openspec/specs/` does not, the
main specs hold no scenarios. `check`, `report` and `baseline` run as usual,
and a tag naming an open change's scenario is accepted. When `openspec/`
itself is missing, those three commands exit 1 with
`no openspec/ under <root>`.

**Why.** A repository that adopts OpenSpec has `openspec/changes/<name>/`
and no `openspec/specs/` until it archives its first change. git records no
empty folder, so a clone cannot hold an empty `specs/` either. Such a
repository should be able to adopt spec-trace in the same change, and its
first CI run should pass.

Every command looks for `openspec/` under the root, which `--root` sets and
which is the current directory by default. spec-trace runs only in a
repository that uses OpenSpec, so a missing `openspec/` most likely means the
root is the wrong folder. A check that passed there would have checked
nothing.

**Rejected: refusing a missing `openspec/specs/`.** Every repository that
adopts both at once would fail CI until its first archive, or would have to
commit a placeholder file in `specs/` only to satisfy the checker.

## The baseline only shrinks

**Decision.** The baseline lists scenarios that no test tagged at adoption.
`check` fails on a scenario that is untagged and absent from the baseline,
and also on a baseline line whose scenario is now tagged or no longer exists.
`baseline --prune` removes those lines and keeps every other line as
written; it never adds one. When no scenario line is left, it keeps the
file and its comment header: the file is the record that the repository
adopted spec-trace (see *The agent asks whether to adopt it*, below). Plain
`baseline` writes the file only when there is none, and refuses (exit 2)
once it exists.

**Why.** A repository adopting this has hundreds of untagged scenarios, and
tagging them all first would block adoption. Failing on a stale line means
the line comes out in the same change that tags its scenario. The list can
only get shorter, and it always lists exactly the scenarios still untagged.
Writing the file again would add every scenario untagged today, so a new
scenario with no test would be exempt without anyone deciding it should be.
`--prune` reads lines with the same parser as `check`, so it removes exactly
the lines `check` fails on. With two parsers, it could keep a line `check`
fails on, or remove one that `check` reads as an exemption.

**Rejected: a baseline that tolerates stale lines.** A tagged scenario left
in the baseline stays exempt: if its only test is later deleted, `check`
still passes.
**Rejected: a `--force` flag on `baseline` to overwrite the file.** Deleting
the file does the same, and shows up plainly in the diff.
**Rejected: `check` removing stale lines itself.** CI runs `check`, and CI
must not edit files.

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

## Tags are found by searching the repository, not by finding test files

**Decision (Adam, 2026-10-16).** `check`, `report` and `baseline` find tags
with one `git grep` under `--root`:

```
git --no-literal-pathspecs -C <root> grep --untracked --no-recurse-submodules \
    -I -n -z --no-color --no-column --no-full-name -F -e @scenario -- . \
    ':(exclude,glob)**/*.md' ':(exclude,glob)**/*.mdx' ':(exclude,glob)**/*.rst' \
    ':(exclude,glob)**/*.adoc' ':(exclude,glob)**/*.txt' \
    ':(exclude,glob)openspec/**' [':(exclude,glob)<pattern>' for each line of the ignore file]
```

- `--untracked` adds files not yet added to git, so a test the agent has
  not staged still counts. It honours `.gitignore`, so other worktrees under
  an ignored `.claude/worktrees/`, `node_modules/` and build output are
  skipped. Nested repositories are skipped too. It also skips a file git
  tracks whose path `.gitignore` matches; see *A test whose path
  `.gitignore` matches is not supported*, below.
- `-I` skips binary files.
- The default exclusions are doc files (`*.md`, `*.mdx`, `*.rst`, `*.adoc`,
  `*.txt`) and everything under `openspec/`, where `@scenario` appears in
  prose and examples.
- `openspec/spec-trace-ignore.txt`, when present, adds one exclude per line:
  a git glob pattern relative to the root; `#` lines and blank lines are
  skipped. A pattern git rejects stops the command with git's error, exit 2.
- The `--no-` options undo user settings (`grep.fullName`, `grep.column`,
  colour) that would change the output's shape. `--no-recurse-submodules`
  undoes `submodule.recurse`, which git refuses alongside `--untracked`.
  `--no-literal-pathspecs` undoes `GIT_LITERAL_PATHSPECS`, under which the
  excludes would be read as plain paths and none would apply. `-F` reads the
  pattern as text whatever `grep.patternType` says.

Without git, or with `--root` outside a git work tree, these commands refuse
(exit 2). `state` and `decline` read no tags and work without git.

**Why.**
- **Finding test files meant reproducing each runner's selection from its
  configuration.** For Vitest and Jest that configuration is code, and every
  pass of bug-hunter (the skill that finds and proves bugs before a commit)
  found more configurations that the code misread. Its last run over the
  config-reading code fixed 22 bugs in 3 passes and still left 6, 3 of them
  regressions from its own fixes.
- **The places where a tag is not a test make a short, static list:** doc
  files and `openspec/`. A list of test files depends on every runner's
  configuration instead.
- **A tag outside a test counts only if it names a real scenario exactly.**
  Text that only looks like a tag, such as another tool's syntax, almost
  never matches a scenario's name exactly, so wrongly counting one is rare.
  The common case is text that names no scenario, and that fails `check`
  loudly as an orphan tag instead of passing quietly.
- **The skill already accepts this kind of limit:** it checks that a tag
  exists, not that its test runs or passes.

**Rejected: reading each runner's configuration** (Vitest, Jest, pytest, Go,
Rust), for the first reason above.
**Rejected: an allow-list JavaScript parser** for Vitest and Jest configs,
which reads only string literals and refuses anything else. Those configs are
code, and each bug-hunter pass found more configs that the parser misread.

**When to reconsider.** If a repository ever needs a long exclusion list that
keeps changing, finding tags this way has become as hard as finding tests.

## A test whose path `.gitignore` matches is not supported

**Decision (Adam, 2026-10-16).** A file git tracks whose path `.gitignore`
matches, such as a test committed under an ignored `build/`, is not
searched, because `git grep --untracked` leaves out every path
`.gitignore` matches, tracked or not. Its tags are skipped, so `check`
reports its scenarios as untagged, and the author moves the test. A
`--root` inside an ignored folder likewise finds no tags. A person's own ignore rules
(`.git/info/exclude`, `core.excludesFile`) count too, so a tracked test
they match is skipped only on that person's machine, and `check` there can
disagree with CI.

**Why.** A test in such a place is rare. Adam, who maintains this skill,
is "not worried about supporting putting a test in such a weird place".

**Rejected: a second `git grep` without `--untracked`, merged with the
first.** It would find those files, at the cost of a second search for a
layout nobody uses.

## A tag in a test the runner skips or excludes still counts

**Decision (Adam, 2026-10-16).** A tag counts wherever the search finds it,
even when its test is skipped or sits in a file the test runner's
configuration excludes. This is the same limit as a skipped test: spec-trace
checks that a tag exists, not that its test runs. Two things help a person
spot such files:
- `report` ends with *Where tags were found*: each directory holding tags,
  with its count of files and tags, sorted by path, and a line saying to add
  any directory the runner doesn't run to `openspec/spec-trace-ignore.txt`.
  `check` doesn't print it, because CI would repeat it on every run, and
  `baseline` doesn't, because a repository usually has no tags at adoption.
- SKILL.md's description, which lists the situations in which an agent
  loads the skill, includes editing a test runner's configuration to
  exclude test files, in a repository that has adopted spec-trace. The
  skill then tells the agent to add the same paths to
  `openspec/spec-trace-ignore.txt` in the same commit. At adoption, the
  agent shows the user `report`'s *Where tags were found* list, and tells
  them what `openspec/spec-trace-ignore.txt` is for.

**Rejected: a hook that notices an edit to a test runner's configuration.**
It would need a list of every runner's configuration file names, which is
never complete: the problem of finding test files again, in smaller form.

## Scenarios are read only through the OpenSpec CLI

**Decision.** spec-trace reads specs and deltas only through the public
commands of the OpenSpec CLI, 1.15.0 or later, as spec-check does:

- `openspec show <capability> --json --type spec` for each
  `openspec/specs/<capability>/spec.md` gives each requirement's name and
  its scenarios' names.
- `openspec show <change> --json --deltas-only` for each open change gives
  what each delta spec adds, modifies, removes and renames. `show` refuses a
  change whose proposal lacks "Why" or "What Changes", so the change's delta
  specs are copied into an empty temporary directory beside a stub proposal
  and read there. A main spec is read the same way, alone in an empty
  directory, so nothing else in the repository affects the reading.
- Each reading is kept for the run, keyed by the files' content. `check`
  reads the specs twice, once alone and once with open changes applied, and
  still runs `show` once per main spec and once per open change. Up to 8
  runs of `show` go at once.

spec-trace finds the files by listing directories:
`openspec/specs/<capability>/spec.md` and
`openspec/changes/<change>/specs/<capability>/spec.md`, one level deep, with
`changes/archive/` skipped. What each file holds is decided by `show` alone.

The same files decide which capabilities a tag may name. `check` and plain
`report` count one capability per main spec file. `report --include-changes`
also counts one per delta spec file of an open change. When a tag's
capability is counted but no scenario has the tag's name, the tag fails as
naming no scenario, never as naming no capability. When a tag's capability is
not counted, the tag fails as naming no capability. Its message says "under
openspec/specs" in `check` and plain `report`, and "in openspec/specs or an
open change" in `report --include-changes`, so it names every place searched.

That holds even for a capability with no scenario left after applying the
open changes, which `report --include-changes` judges tags against. A change
can remove a capability's only requirement. A change can also restate the
only requirement, and `show` can read the restatement with no scenario. So
the set of capabilities is never built from those scenarios: either case
would make a capability with a spec file look missing.

Without the CLI, or below 1.15.0, `check`, `report` and `baseline` (with or
without `--prune`) print `not run: install OpenSpec 1.15.0 or later`, with
the reason, and exit 2. `state`, `decline` and the hook read no spec, so they
work without the CLI.

A main spec that `show` cannot read fails `check` with OpenSpec's message,
and `baseline` writes nothing. Tags and baseline lines naming its capability
are not judged until it can be read: without its scenarios, calling them
wrong would tell the author to delete good tags. An open change that `show`
cannot read also fails `check`, as a problem of its own beside the tags it
breaks: a tag naming one of its scenarios fails as naming none.

`show` can read less from a delta spec than its author wrote, without an
error:
- **No requirement at all**, when the file's only section title is one
  OpenSpec does not know, such as `## ADDED Requirement` (singular).
- **A requirement with no scenario**, when the delta adds or modifies a
  requirement whose scenario headings `show` does not read, such as
  `#### Scenario: Fresh` with no text under it.

A tag naming a scenario written there then fails as naming no scenario. When
the delta was to bring in a new capability and `show` read none of its
requirements, `check` and plain `report` fail the tag as naming no capability
instead, since they count only main spec files as capabilities. Either message
points the author at the tag instead of the file. So when a tag names no
scenario, or no capability, and its capability has such a delta spec, the
tag's message says what `show` read in which file, and to run `openspec
validate <change> --type change`, which explains the cause. spec-trace says
this itself because it cannot count on spec-check being installed.

**Why.**
- **A hand-written reader drifts from OpenSpec.** One that matches a
  section by its prefix counts `## MODIFIED Requirements:`, a title OpenSpec
  ignores. It also has to know that OpenSpec drops a heading's closing `#`s
  from a scenario's name, and skips a scenario heading with no text under
  it. spec-check's hand-written readers kept producing bugs of this kind,
  which is why spec-check moved to the CLI first.
- **A tag must name a scenario exactly as archiving its change writes it
  into `openspec/specs/`.** Only OpenSpec's own reading says what that is.
- **One minimum for both skills.** `show --json` names requirements and
  scenarios from 1.14.0, but spec-check needs 1.15.0, so one install serves
  both.
- **Nothing `check` does is sound without the scenarios.** A partial run
  could still say whether a tag names a capability directory, but it could
  never pass, since it cannot tell whether any scenario is untagged. It
  would report some problems now and the rest once OpenSpec is installed.
  So these commands refuse whole.

**Rejected:**
- **Importing OpenSpec's parsers.** They sit outside the package's
  `exports`, so any release may move or change them.
- **A fallback reader for older CLIs.** It would run only on machines whose
  OpenSpec nobody tests against.

**Where it stops.**
- **A scenario heading with no text under it is not a scenario.** OpenSpec
  1.15.0 leaves it out of `show`, and `openspec validate --strict` does not
  report it. So no test needs to tag it, and neither OpenSpec nor
  spec-trace warns the author that it is not a scenario.
- **An ambiguous tag gets no note naming a misread delta.** In `report
  --include-changes`, a tag can fail as ambiguous, its scenario name
  repeating under two requirements, only because `show` read no requirement
  in a delta meant to remove one of them, such as one titled `## REMOVED
  Requirement` (singular). The message lists the two qualified tags and says nothing
  about the delta. `check` judges tags against the main specs, where the
  name does repeat, so only `report` is affected.
- **Nested capabilities are not read.** OpenSpec 1.15 reads
  `openspec/specs/<area>/<capability>/spec.md` as capability
  `<area>/<capability>`, but a tag's capability cannot hold a `/`, so
  spec-trace lists only one level.

## A scenario's line is a text search

**Decision.** `show --json` gives no line numbers. A scenario's line, which
`check` prints with an untagged scenario and with a repeated name, comes
from a plain text search for the names `show` gives, with no grammar of
OpenSpec's headers:

- A requirement is at the first line on which its name follows
  "Requirement:", compared ignoring case, backticks, `#`s and runs of space,
  and which no earlier requirement or scenario was given. When several lines
  match, a line starting with `###` wins over any other, such as a rename's
  FROM line. Among those, a line naming it exactly wins.
- A scenario is at the first line after its requirement's, before the next
  line starting with `## ` or `### `, that starts with `####`, names it with
  or without "Scenario:", and is not taken by another.
- Lines inside a code fence are skipped, since OpenSpec reads a fenced
  heading as text. A fence closes only on a line of its own character, at
  least as long, with nothing else on it, so a ```` ``` ```` line inside a
  `~~~` example does not end the example.
- A scenario the search cannot find is given its requirement's line. When
  neither is found, the line is 0 and the message names the file only.

**Why.** spec-check's locator first copied OpenSpec's header grammar, and one
bug-hunter run found 11 bugs, every one that copy disagreeing with OpenSpec
1.15. A search with no grammar has nothing to drift from. The names, which
decide what a tag counts for, come from `show`; a wrong guess here only puts
a message on the wrong line.

**Rejected:** keeping a copy of the header grammar as a best-effort locator,
for the reason above.

## The agent asks whether to adopt it, when scenarios are written

**Decision.** A hook runs after the agent writes or edits a `spec.md` under
`openspec/specs/` or `openspec/changes/<name>/specs/`. In a repository that
has neither adopted nor declined spec-trace, it tells the agent to ask the
user which. The answer is recorded in the repository: adopted is the
baseline file, or a GitHub workflow that runs `spec_trace.py`; declined is
spec-trace's own file, `openspec/spec-trace.yaml`, holding
`adoption: declined`, which `decline` writes. The hook is enabled by
default.

**Why.**
- **Adoption that waits for someone to remember never happens.** A
  repository can write OpenSpec scenarios for months with no tags, and
  nothing shows the gap growing.
- **Scenarios start needing tests when they are written**, so that is when
  the question is asked.
- **The answer lives in the repository**, so it reaches every agent and
  person on the team, and a committed answer stops the question for all of
  them.
- **The baseline file stays once every scenario is tagged,** as the record
  of adoption; `baseline --prune` keeps it, with its header, when its last
  scenario line goes.
- **A CI step that runs `spec_trace.py` marks adoption too,** because the
  `--baseline` option can put the baseline at a path the hook does not look
  at.
- **`openspec/spec-trace-ignore.txt` does not mark adoption.** It only
  changes where tags are searched for.
- **spec-trace treats the git top level as the repository.** The hook asks
  only about a spec in the top's own `openspec/`. A test fixture or a
  monorepo project with its own `openspec/` below the top is never asked
  about, so a repository that has answered is not asked again because of a
  fixture. A workflow counts only when it names `spec_trace.py` itself, so
  one that runs `test_spec_trace.py` does not.
- **The decline is in spec-trace's own file, not in OpenSpec's
  `config.yaml`.** Writing into OpenSpec's file would tie `decline` to that
  file. Without a `config.yaml`, `decline` would have to create one holding
  only its comment line, and such a file makes every `openspec` command warn,
  so `decline` would refuse instead. spec-trace's own file,
  `openspec/spec-trace.yaml`, can be written in any repository with
  `openspec/`.
- **A decision file (`openspec/spec-trace.yaml`) that says anything other
  than `adoption: declined` is `unknown`**, not undecided:
  the hook stays silent and `decline` refuses, so neither overwrites what
  someone wrote there.
- **Adoption wins over a decision file** left behind, so changing one's
  mind needs no command; the adopt steps delete the file for tidiness.
- **On by default**, like bug-hunter's and prose's hooks: installing the
  skill is the opt-in, the hook is silent outside OpenSpec repositories and
  in any repository that has answered, and it never blocks.
- **Cursor gets it through `postToolUse` with matcher `Write`, not
  `afterFileEdit`.** Cursor's hook docs give `afterFileEdit` no output, so a
  note from it would never reach the agent; `postToolUse` documents
  `additional_context`. Where `Write`'s `tool_input` holds the path is not
  documented, so the hook reads `file_path` or `path` from it. It also
  accepts a top-level `file_path`, the shape `afterFileEdit` sends, so a hook
  wired to that event by hand still finds the path. It is untried in Cursor.

**Rejected: a `# spec-trace: declined` line in `openspec/config.yaml`.** It
would make `decline` refuse in a repository without that file, and edit a
file another tool owns.
**Rejected: asking at install time.** Installing is per machine; adoption is
per repository.
**Rejected: a session-start hook.** It would fire in every session, not when
the question matters.
**Rejected: relying on the skill's description alone.** A model loads a skill
by judgement, so nothing makes sure the question is ever asked.

## A monorepo with an `openspec/` per package is only partly supported

**Decision (Adam, 2026-10-16).** spec-trace stays built around one
`openspec/` at the git top level. The path for an `openspec/` per package is
recorded below, to be built when a repository with that layout uses
spec-trace.

spec-trace keeps three things per `openspec/`: the baseline
(`openspec/spec-trace-baseline.txt`, the scenarios no test tags yet), the
optional ignore file (`openspec/spec-trace-ignore.txt`, paths the search for
tags leaves out), and the decision file (`openspec/spec-trace.yaml`, which records
a decline). A repository has adopted spec-trace when it has a baseline or a
GitHub workflow that runs `spec_trace.py`. Once adopted, the hook stops
asking.

**One `openspec/` at the top works.** Those files, and the CI step, are at
the top. The whole repository is searched for tags, so a tag can name any
capability, wherever its test is.

**An `openspec/` per package**, such as `packages/api/openspec/`, can be
checked one package at a time with `spec_trace.py --root packages/api check`.
Its baseline, ignore file and decision file are then the package's own, and
only files under `packages/api` are searched. Four things fall short:
- **The hook never asks about a package.** If it asked about every
  `openspec/` in a repository, it would also ask about test fixtures that
  hold one. So it asks only about the `openspec/` at the git top level; see
  *The agent asks whether to adopt it, when scenarios are written*, above.
- **A CI step doesn't mark a package adopted.** spec-trace looks for a
  workflow that runs `spec_trace.py` in `.github/workflows/` under `--root`,
  but workflows live at the top. So a package counts as adopted only through
  its baseline. If the hook did ask about packages, it would keep asking
  about one that a CI step had adopted.
- **A test outside the package can't tag its scenarios.** The search covers
  only files under `--root`, so an end-to-end test at the top is never
  read.
- **CI needs a `check` step per package.**

**The path, if a repository needs it:**
1. Treat each OpenSpec project as the unit: a directory whose `openspec/`
   holds a `config.yaml`, which `openspec init` creates and a fixture
   usually lacks. The hook asks about the project enclosing the spec it
   wrote, and the answer goes in that project's
   `openspec/spec-trace.yaml`.
2. Count a workflow at the top as adopting a project when it runs
   `spec_trace.py` with `--root` naming that project.
3. Add `check --all`, which finds every project and checks each, so CI needs
   one step.
4. Let a project's search reach files outside it, for shared end-to-end
   tests.

Step 1 replaces "only the top's `openspec/`" with a guess: an `openspec/`
holding a `config.yaml` is a project. A fixture that does hold a
`config.yaml` is asked about once; its answer is then recorded and the
question stops.

**Why not now.** No repository using spec-trace has an `openspec/` per
package. igor, the repository this skill was built for, has one at its top.
Building the path without such a repository would add that guess and its
tests for a layout nobody has.

## Known issues

- An orphan tag's text (a tag that names no scenario) is shown cut short when a single quote followed by a
  comma sits inside the name, as in `Says "hi" to 'Bob', twice`. Only the
  error message is affected; the tag is still reported.
