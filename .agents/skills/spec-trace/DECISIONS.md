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
`openspec/specs/*/spec.md`. A tag naming a scenario that an open change in
`openspec/changes/` adds, under an ADDED or MODIFIED requirement, is
accepted, neither counted nor reported. `report --include-changes` applies
each open change's delta to the main specs, for a local view: an ADDED or MODIFIED
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
is ambiguous, goes through that one match. When a repeated scenario name is
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
is cut at a double quote, a backtick and a comment closer, but not at every
single quote, since names contain apostrophes. In a single-quoted test name
the display text therefore kept `', async () =>` after the name, and a
repeated name there was reported as a renamed scenario instead of as
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
