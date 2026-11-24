## Purpose

The sequencer recommends the order in which a repository's open work is
specified, implemented, reviewed and merged. Its script computes the order
with no model, from the repository's open pull requests and issues and,
where they exist, its open OpenSpec changes. One rule, that a change whose
code calls another change's code is built after it, needs a model, and
runs only where one is available. The script publishes the order in one
issue's body and a block in each ordered item's body, and names each
reviewer's next review. It orders a cycle by a fixed rule, which a
person can override, and asks no one. It recommends and never merges.

These terms hold throughout this spec:

- **The script** is the skill's script. **A caller** is whatever runs it:
  an agent in a session, the skill's CI workflow, or an Igor, one of the AI
  teammates of adamstallard/igor, whose Sequencer role adamstallard/igor#231
  specifies.
- **An item** is an open issue or open pull request that the order holds.
  An item's **number** is its issue or pull request number, and its
  **repository** is the `owner/repo` name of the repository that holds it.
- One item is **opened earlier** than another when GitHub's creation time
  for it is earlier. Where the times are equal, the earlier is the one
  whose repository's name sorts first, then the one with the lower number;
  within one repository, that is the lower number.
- **The order's issue** is the one issue whose body holds the whole order.
- **A change** is an OpenSpec change: a directory under `openspec/changes/`
  other than `archive/`. **An open change** is one on the default branch or
  on an open pull request's head. A change **belongs to** the
  earliest-opened open pull request whose diff against its base adds or
  changes a file in the change's directory, and the order places the
  change where it places that pull request.
- **A change's requirement** is a requirement that the change's delta adds,
  or renames onto a new name, and that no spec on the default branch holds.
- **An explicit link** is a GitHub "blocked by" relation, a `Depends on`
  line in a body, or a `Builds on:` line in a change's `proposal.md`, as *Explicit links order the items they connect*
  and *A Depends on line names items by number, with or without their
  repository* define.
- **A pull request is tied to an issue** when GitHub's closing
  references say it closes the issue, or a line in its body names the issue
  as `Part of #<number>` or after one of GitHub's closing keywords
  (`close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
  `resolves`, `resolved`, in any case). The script reads closing keywords
  itself because GitHub gives no closing reference to a pull request whose
  base is not the default branch. Such a line follows every rule of a
  `Depends on` line, with its own words in place of `Depends on `.
- **An outside item** is an issue or pull request in another repository
  that an explicit link names.
- **An edge** is a rule's finding that one item comes after another, with
  its **reason**. **A cycle** is a set of items whose edges lead from each
  back to itself. **A merge wait**, set by *Pull requests that change the
  same files merge one after another*, is not an edge.
- **A writer** is an account with write access to the repository that
  holds the item or comment in question. Where task 0.6 finds that the
  workflow's token cannot read permissions, the script instead counts
  the author of an issue, pull request or comment as a writer when
  GitHub's `author_association` on that item is OWNER, MEMBER or
  COLLABORATOR, which also counts some accounts with only read access. It
  does so for every caller, so that every caller counts the same writers.
- **A change's hash** is a hash of every file under the change's
  directory, read from the head the change is read from, which `order`
  prints for each open change.
- **An edges file** is the model step's output: the pairs of changes it
  checked, each with the two changes' hashes from the `order` run it read,
  and the edges it found.
- **The model step** applies the one rule that needs a model: a change
  whose code will call another change's code is built after it. **A pair
  of changes** is two changes that each belong to an open pull request.
- **A Sequencer Igor** is an Igor in the Sequencer role; **an Igor's work
  triage** is the step where an Igor chooses which items to take.

## ADDED Requirements

### Requirement: The order holds every open pull request and the issues linked to the work

The order SHALL hold each open pull request, each open issue that an
explicit link connects to another item, each open issue that an open pull
request a writer opened is tied to, and no other issue; the order's issue is never an
item.

#### Scenario: An issue linked to nothing is not ordered

- **WHEN** an open issue has no explicit link to or from another issue or
  pull request, and no open pull request is tied to it
- **THEN** the order does not hold it, and its body gets no block

#### Scenario: A blocked issue is ordered

- **WHEN** open issue #12's body has the line `Depends on #9`
- **THEN** the order holds both #12 and #9

#### Scenario: The order's issue is never ordered

- **WHEN** the order's issue is #40, and #12's body has the line
  `Depends on #40`
- **THEN** the order does not hold #40, and #40's body gets no item block

### Requirement: An issue takes the place of an open pull request tied to it

Where open pull requests that writers opened are tied to an issue, the
issue SHALL share the position of the earliest opened of them, and its
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

### Requirement: Only a writer's tie to an issue in this repository counts

A tie from a pull request no writer opened SHALL neither place an issue
nor bring it into the order, since anyone can open a pull request, and a
tie to another repository's issue SHALL place nothing.

#### Scenario: A tie to another repository's issue moves nothing

- **WHEN** #64's body holds the line `Part of octo/lib#7`, and nothing else
  ties #64 to an issue
- **THEN** `octo/lib#7` gets no place, and #64's line in the order's issue
  does not say `tied to no issue`

#### Scenario: An outside author's closing reference moves nothing

- **WHEN** `zed`, without write access, opens #48 saying `Fixes #43`, and
  #50, opened by a writer, also closes #43
- **THEN** #43 shares #50's place, not #48's, and gains no place from #48
  alone

### Requirement: A pull request tied to no issue is listed

Each open pull request tied to no issue, counting ties that move nothing,
SHALL say so on its line in the order's issue. The script SHALL add no
`Closes` or `Part of` line to any body.

#### Scenario: A pull request tied to no issue is listed

- **WHEN** draft pull request #64 closes no issue and names none in a
  `Part of` or `Closes` line, though issue #43 is the work it does
- **THEN** #64 is listed although it is a draft: its line in the order's
  issue says `tied to no issue`, and no body gains a `Closes` or
  `Part of` line

### Requirement: Each change is read from the head of the pull request it belongs to

Where several open pull requests' heads hold one change's directory, the
script SHALL read the change, and compute its hash, from the head of the
pull request it belongs to, as the terms above define, and ignore the
other copies.

#### Scenario: A stacked pull request's older copy is ignored

- **WHEN** #25 adds the change `inquisitor`, so the change belongs to #25,
  and #64, stacked on #25, carries an older copy of
  `openspec/changes/inquisitor/`
- **THEN** the script reads and hashes `inquisitor` from #25's head, and
  #64's copy sets no edge and no hash

### Requirement: A change already on the default branch is not placed

A change on the default branch that belongs to no open pull request SHALL
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
SHALL apply no rule that reads a change's files,
and the order's issue SHALL say requirements' dependencies were not
checked, and why.

#### Scenario: A missing CLI checks no requirement

- **WHEN** `openspec` is not on the path, and two open pull requests hold
  changes
- **THEN** no edge comes from a change's files, and the order's issue says
  requirements' dependencies were not checked, because OpenSpec is not
  installed

#### Scenario: A change is read without checking out its head

- **WHEN** the script reads #90's change from #90's head
- **THEN** it reads fetched files, and the working tree and `HEAD` are as
  they were

#### Scenario: An old CLI checks no requirement

- **WHEN** the script runs where `openspec --version` prints `1.14.3`, and
  two open pull requests hold changes
- **THEN** no edge comes from a change's files, and the order's issue says
  `Dependencies between requirements were not checked: OpenSpec 1.16.1 or
  later is not installed (this one is 1.14.3).`

### Requirement: A change the OpenSpec CLI refuses is listed as not checked

Where the OpenSpec CLI runs on a change but refuses it, the script SHALL
take nothing from that change's files, and the order's issue
SHALL list the change as not checked, with the CLI's reason, and name each
pair it forms with another open change as unchecked.

#### Scenario: A change the CLI refuses is not counted as checked

- **WHEN** `openspec show --json` refuses #93's change, and #82 and #90
  hold changes it reads
- **THEN** the order's issue lists #93's change as not checked, quoting the
  CLI's reason, and names #82 and #93, and #90 and #93, as unchecked pairs

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

- **WHEN** #91's `design.md` names *An open condition never ends a running
  service*, which #82's change adds
- **THEN** #91 comes after #82, with the reason
  `` after #82: cites its `An open condition never ends a running service` ``

#### Scenario: A requirement already in force orders nothing

- **WHEN** #91 names a requirement that the default branch's specs hold
- **THEN** that citation gives no edge

### Requirement: Two changes that modify one requirement owe a copy, which sets no order

Where two open changes both modify one requirement of one capability, the
order's issue SHALL say that the later of the two in the order must add the
earlier one's new scenarios to its own copy of the requirement before it
archives; this finding SHALL add no edge, because archiving replaces a
requirement with the archiving change's whole copy. Inside a cycle, the
later is the later in the cycle's order, by rule or by override.

#### Scenario: The second to archive owes the copy

- **WHEN** #82 and #90 both modify *Claims expire after an hour*, and #82
  comes first in the order
- **THEN** the order's issue says #90 must add #82's new scenarios of
  *Claims expire after an hour* to its copy before it archives, and neither
  item gains an edge from it

#### Scenario: The copy owed inside a cycle follows the cycle's order

- **WHEN** #82 and #90 both modify *Claims expire after an hour*, they form
  a cycle ordered by rule, and then a writer's `#90 first` overrides it
- **THEN** the order's issue first says #90 owes the copy, and after the
  override says #82 owes it

### Requirement: Explicit links order the items they connect

An item SHALL come after each item that a GitHub "blocked by" relation or a
`Depends on` line in its body says it waits on, and a change's pull request
after each pull request its `proposal.md`'s `Builds on:` lines name in this
repository.

#### Scenario: A Depends on line orders two issues

- **WHEN** #12's body holds the line `Depends on #9 and #10`
- **THEN** #12 comes after #9 and #10, with the reasons `after #9: depends
  on it` and `after #10: depends on it`

#### Scenario: A Builds on line orders a stacked change

- **WHEN** #64's change's `proposal.md` says
  `Builds on: inquisitor (adamstallard/shared-skills#25)`, in the
  repository adamstallard/shared-skills
- **THEN** #64 comes after #25, with the reason `after #25: builds on it`

#### Scenario: A blocked-by relation orders two items

- **WHEN** GitHub records #14 as blocked by #11
- **THEN** #14 comes after #11, with the reason `after #11: blocked by it`

### Requirement: A Depends on line names items by number, with or without their repository

A `Depends on` line SHALL be a body line, outside code fences, starting
`Depends on ` and followed by `#<number>` or `<owner>/<repo>#<number>`
references separated by commas or `and`, where `<owner>` holds only
letters, digits and `-`, and `<repo>` only those, `.` and `_`; other text
is no reference, here or in a `Builds on:` line's parentheses. A
reference that names this repository in full SHALL be read as its
`#<number>`.

#### Scenario: A Depends on line with commas orders each item it names

- **WHEN** #12's body holds the line `Depends on #9, #10, #11`
- **THEN** #12 comes after #9, #10 and #11

#### Scenario: A reference naming this repository in full orders like a short one

- **WHEN** #12's body, in the repository adamstallard/shared-skills, holds
  the line `Depends on adamstallard/shared-skills#9`
- **THEN** #12 comes after #9, with the reason `after #9: depends on it`

#### Scenario: A reference with a mention in it is no reference

- **WHEN** #12's body holds the line `Depends on @org/team#1`
- **THEN** it gives no edge, is not listed as not counted, and the
  order's issue writes no `@org/team`

#### Scenario: A Depends on line in a code fence is ignored

- **WHEN** the only `Depends on #9` in #12's body is inside a code fence
- **THEN** it gives no edge

### Requirement: A link to another repository's item is listed as not counted

An explicit link naming an outside item SHALL set no edge, make no item
wait and bring no issue into the order. The order's issue SHALL list
it as not counted, on the line of the item that has the link or, where the
order does not hold that item, in its list of edges not counted, and SHALL
write the outside item as plain `<owner>/<repo>#<number>` text, which
GitHub turns into a link. The script SHALL make no request to an outside
item's repository.

#### Scenario: A Depends on line naming another repository is listed and orders nothing

- **WHEN** pull request #12's body holds the line
  `Depends on #9 and octo/lib#7`
- **THEN** #12 comes after #9, and #12's line in the order's issue says
  `not counted: depends on octo/lib#7, in another repository`, where
  GitHub shows `octo/lib#7` as a link, as it does on every such line

#### Scenario: A blocked-by relation to another repository's issue is listed

- **WHEN** GitHub records pull request #14 as blocked by the issue
  `octo/lib#7`
- **THEN** #14's line says
  `not counted: blocked by octo/lib#7, in another repository`

#### Scenario: A Builds on line naming another repository is listed

- **WHEN** #64's change's `proposal.md` says
  `Builds on: claims (octo/lib#31)`, in the repository
  adamstallard/shared-skills
- **THEN** #64's line says
  `not counted: builds on octo/lib#31, in another repository`

#### Scenario: A link to another repository's item makes no item wait

- **WHEN** pull request #12's body says `Depends on octo/lib#7`, the issue
  `octo/lib#7` is open, no edge connects #12 and pull request #15, and
  #12 was opened earlier
- **THEN** #12 comes before #15, and #12's block names no wait

#### Scenario: An issue whose only link names another repository is not ordered

- **WHEN** open issue #12's only explicit link is the body line
  `Depends on octo/lib#7`, and no open pull request is tied to #12
- **THEN** the order does not hold #12, and the order's issue lists
  `#12: depends on octo/lib#7, in another repository` as not counted

#### Scenario: The script makes no request about another repository's item

- **WHEN** pull request #12's body says `Depends on octo/lib#7`
- **THEN** the script makes no request about `octo/lib#7`, gives it no
  position, and lists the link whether `octo/lib#7` is open or closed

### Requirement: Only edges set by writers count

An edge SHALL count only when a writer opened every item whose text sets
it. For an edge from changes' files or the model step, those items are both
changes' pull requests; for a `Depends on` or `Builds on:` line, the item
holding the line; for a blocked-by relation, the blocked item. The order's
issue SHALL list the edges that do not count, each with the account that
opened the item setting it.

#### Scenario: A Depends on line from an outside author is not counted

- **WHEN** issue #120, opened by `zed` who has no write access, says
  `Depends on #95`
- **THEN** #120 gains no edge after #95, that line counts in no reviewer's ranking, and the
  order's issue lists `#120 after #95` as not counted, opened by `zed`

#### Scenario: A citation set by an outside author's title is not counted

- **WHEN** `zed`, without write access, opens #121, whose change adds a
  requirement titled as a sentence in #82's `design.md`
- **THEN** #82 does not come after #121, and the order's issue lists that
  edge as not counted, opened by `zed`

### Requirement: Pull requests that change the same files merge one after another

Where two open pull requests change a file in common, the later of them in
the order SHALL get a merge wait on the earlier, with a reason naming the
files in common. A merge wait SHALL move neither pull request in the order
and count in no reviewer's ranking, so each later pull request rebases
once, onto the one merged before it.

#### Scenario: Overlapping pull requests get a merge wait

- **WHEN** #30 and #33 both change `src/claims.py`, and no edge connects
  them
- **THEN** #33 stays after #30, where the tiebreak placed it, and #33's
  block says `` merges after #30: both change `src/claims.py`; rebase once
  onto it ``

#### Scenario: A merge wait counts in no reviewer's ranking

- **WHEN** #28 and #30 both await a reviewer, one item comes after #28 through
  an edge, none comes after #30 through an edge, and #33 has a merge wait
  on #30
- **THEN** the order's issue names #28 as that reviewer's next review

### Requirement: Items no rule orders keep the order they were opened in

Among the items that come after no unplaced item through an edge, the one
opened earliest SHALL go next, and a cycle SHALL count as one item opened when its
earliest-opened member was.
No caller, an Igor's Sequencer role included, SHALL ask a person about a
place this tiebreak or a cycle's rule decides.

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

#### Scenario: An unordered pair raises no question

- **WHEN** a run publishes an order in which no edge connects #20 and #17
- **THEN** it posts no question about their order

### Requirement: A cycle's members are ordered by rule

The order SHALL place a cycle's members together at one place, earliest
opened first, marked `ordered by rule since <time>` with the time the publish that
first listed the cycle ran, or just `ordered by rule` before any publish
has listed it, and place each item that comes after any member after
all of them. A member placed before another member it has an edge after
SHALL say so in its reason.

#### Scenario: Two changes that cite each other are ordered by when they were opened

- **WHEN** #82's change cites a requirement #85's adds, and #85's cites one
  #82's adds, #82 was opened earlier, and no override is recorded
- **THEN** the order places #82 then #85 at one place, marked
  `ordered by rule since <time>`, and #82's reason says
  `` before #85 by rule, though it cites #85's `<title>` ``
- **AND** #91, which cites #85, comes after both

#### Scenario: A cycle not yet published has no time

- **WHEN** `order` runs before any publish has listed the cycle of #82 and
  #85
- **THEN** it prints the cycle as `ordered by rule`, with no time

#### Scenario: A cycle found in CI asks no one

- **WHEN** a CI run finds a cycle between #82 and #85
- **THEN** it posts no question, and the order's issue lists the cycle as
  ordered by rule

### Requirement: A cycle override is kept and followed

The order's issue SHALL keep a list of cycle overrides, each naming the
member a person with write access put first and linking their comment or,
for one that `publish --decide` recorded, naming the `--by` login and the
time. The order SHALL put that member first and the rest earliest opened
first, and its reason SHALL give the same link, or login and time.

#### Scenario: An override puts a later-opened member first

- **WHEN** a person with write access put #85 first, in a cycle where #82
  and #85 cite each other's requirements and #82 was opened earlier
- **THEN** #85 comes first, with the reason
  `` before #82, though it cites #82's `<title>`: chosen at <link to the comment> ``,
  and #82 comes after it

#### Scenario: An override recorded in a session names who chose and when

- **WHEN** an agent runs `publish --decide '#85 first' --by maya`
- **THEN** the overrides list #85 first, chosen by `maya`, with the time it
  was recorded

### Requirement: A cycle override is read from the order's issue

A run SHALL read a comment on the order's issue as an override when a
person's own account with write access posted it, not an App, after the cycle's
`ordered by rule since` time, and its text starts with `#<n> first`,
`#<n>` being one of the cycle's members.

#### Scenario: A writer's comment overrides the rule

- **WHEN** a person with write access comments `#85 first` on the order's
  issue after the cycle of #82 and #85 was listed
- **THEN** the next run adds the override, linking that comment, and
  places #85 first

#### Scenario: A comment from someone without write access overrides nothing

- **WHEN** a person without write access comments `#85 first` after the
  cycle of #82 and #85 was listed
- **THEN** the cycle stays ordered by rule

#### Scenario: A comment on an item's thread overrides nothing

- **WHEN** a person with write access comments `#85 first` on #82's thread,
  not on the order's issue
- **THEN** no run reads it, and the cycle stays ordered by rule

#### Scenario: A comment older than the cycle overrides nothing

- **WHEN** a person with write access commented `#85 first` on the order's
  issue before the cycle of #85 and #90 was listed
- **THEN** that comment leaves the cycle ordered by rule

#### Scenario: A comment an App posts overrides nothing

- **WHEN** a GitHub App with write access posts `#85 first` on the order's
  issue
- **THEN** the cycle stays ordered by rule

### Requirement: A session records a cycle override only as that person

In a session, `publish --decide '#<n> first' --by <login>` SHALL add an
override a person gave in the session to the cycle overrides, and SHALL
refuse, editing nothing, unless `gh` is logged in as that login and it
has write access.

#### Scenario: A session choice in another person's name is refused

- **WHEN** `gh` is logged in as `li`, and an agent runs
  `publish --decide '#85 first' --by maya`
- **THEN** the script edits nothing and says `gh` is not logged in as
  `maya`

#### Scenario: A session choice by a person without write access is refused

- **WHEN** `gh` is logged in as `zed`, who has no write access, and an
  agent runs `publish --decide '#85 first' --by zed`
- **THEN** the script edits nothing and says `zed` has no write access

### Requirement: The model step orders changes whose code calls each other's code

A change whose code will call code another open change adds SHALL come after
that change, as the model step finds. To help it, the script SHALL print,
for each pair of changes, the backticked names that both changes'
`tasks.md` files hold. The script SHALL take the model step's edges only
between items in the order, each with a reason, and refuse the whole set
when any edge names something else or has no reason.

#### Scenario: The script points the model step at shared names

- **WHEN** #82's `tasks.md` adds a function `claim_item()`, and #90's
  `tasks.md` calls `claim_item()`
- **THEN** the script prints `claim_item()` as a name both #82 and #90's
  tasks hold

#### Scenario: A model-step edge naming no item is refused

- **WHEN** the model step's edges include one after #400, and #400 is not
  in the order
- **THEN** the script publishes none of that set's edges, and says which
  edge it refused

#### Scenario: A model-step edge with no reason is refused

- **WHEN** the model step's edges include #90 after #82 with an empty
  reason
- **THEN** the script publishes none of that set's edges, and says which
  edge it refused

### Requirement: A checked pair is kept while both its changes are unchanged

An edges file SHALL name every pair of changes the model step checked.
`publish` SHALL first drop each pair whose two changes are not both still
in the order with the hashes the file gives, and take the rest, with any
edge found. The order's issue SHALL
record each pair taken with those hashes, and a later run SHALL count the
pair checked, and keep its edge, while both hashes match.

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

#### Scenario: An unrelated change keeps a file's edges

- **WHEN** the model step checked #82 and #90 and found #90 after #82, and
  before `publish` runs, issue #120 gains a comment, #95's change is
  revised and #77 merges
- **THEN** `publish` takes the edge between #82 and #90, and drops each
  pair the file gives that holds #95 or #77

### Requirement: The order says plainly what it did not check

The order's issue SHALL say `Build dependencies between changes' code were
not checked.` when no model step has checked any pair of changes, and
name the unchecked pairs when it checked only some; it SHALL never present
an unchecked pair as checked. Where no open change exists, it SHALL say
`Dependencies between requirements were not checked: no open OpenSpec
change.`

#### Scenario: A CI run with no credential says code was not checked

- **WHEN** the workflow runs with no model step, and no recorded code edge
  is kept
- **THEN** the order's issue says `Build dependencies between changes' code
  were not checked.`

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

### Requirement: Every place a rule decides gives its reason

Each item placed after another by an edge SHALL show the edge's reason,
naming the other item and, where a requirement set the edge, the
requirement's title, in the order's issue and in the item's block.

#### Scenario: A reason names the rule and the requirement

- **WHEN** #90 comes after #82 because it modifies #82's *Claims expire
  after an hour*
- **THEN** both the order's issue and #90's block say
  `` after #82: modifies its `Claims expire after an hour` ``

### Requirement: The same inputs give the same order whoever runs the script

Given the same repository state and the same stored checked pairs and code
edges, the script
SHALL produce byte-identical order text, whichever caller runs it and
wherever.

#### Scenario: A session and CI agree

- **WHEN** an agent's session and the CI workflow run the script against the
  same commit, items and recorded code edges
- **THEN** both produce the same text for the order's issue and every block

### Requirement: The whole order lives in one issue's body

The script SHALL keep the whole order in the body of the open issue labelled
`sequencer`, creating that issue when none is open and publishing nothing
when more than one is. It SHALL use such an issue only when its author has
write access to the issue's repository or is `github-actions[bot]`, which
only a workflow run's token posts as, and otherwise publish nothing and name
the issue and its author. Nothing of the order SHALL go in a comment.

#### Scenario: The first publish creates the order's issue

- **WHEN** the script publishes in a repository with no open issue labelled
  `sequencer`
- **THEN** it opens one, labelled `sequencer`, whose body holds the order

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
- **THEN** the script reads none of the cycle overrides or stored code
  edges in its body, edits nothing, and names the issue and its author

### Requirement: The script's text opens with a heading

The line after each `<!-- sequencer:begin -->` marker SHALL be a heading:
`## Order` in the order's issue, and `## Sequencer` in an item's block,
because the inquisitor skill (#25) takes an issue's text before its first
heading as a decision its author made.

#### Scenario: The order is never read as a decision

- **WHEN** the script writes the order's issue body
- **THEN** the line after `<!-- sequencer:begin -->` is `## Order`

#### Scenario: A block in an issue with no heading is not read as a decision

- **WHEN** #43 enters the order, and its body is one paragraph with no
  heading
- **THEN** its new block's line after `<!-- sequencer:begin -->` is
  `## Sequencer`, so only the paragraph comes before the body's first
  heading

### Requirement: Text from a pull request or the model is written inert

The script SHALL write each string taken from an issue, a pull request, a
change's files, the model step or a reviewer source, such as a reason or a
login, as inline code: delimited by a backtick run longer than any in
it, padded with a space where it starts or ends with a backtick, and with
its line breaks as spaces, so mentions, links and markers in it render
inert; an outside item's reference is the one exception. It SHALL refuse
a string holding `<!-- sequencer:end -->`.

#### Scenario: A mention in a model's reason does not notify

- **WHEN** a model-step edge's reason is `calls claim() @maya see
  https://example.com`
- **THEN** the block shows that reason inside inline code, and GitHub
  notifies no one and renders no link

#### Scenario: Backticks and line breaks stay inside the code

- **WHEN** a reason is ``x` `` followed by a line break and `@maya`
- **THEN** the block shows it as one code span, delimited by two backticks
  and holding the text x, a backtick, a space and @maya, and GitHub
  notifies no one

#### Scenario: A string holding the end marker is refused

- **WHEN** a model-step edge's reason holds `<!-- sequencer:end -->`
- **THEN** `publish` refuses that edges set, and publishes none of its
  edges

#### Scenario: A requirement title holding the end marker sets no edge

- **WHEN** #82's change adds a requirement whose title holds
  `<!-- sequencer:end -->`, and #90's change modifies it
- **THEN** that requirement sets no edge, #82's other requirements still
  do, and the order's issue names #82's change as holding the sequencer's
  end marker

### Requirement: Each item's body carries a block giving its place

Each item SHALL carry, in its own body and never in a comment, one block
giving its position in the order, what it waits on with each reason, and a
link to the order's issue.

#### Scenario: A pull request's block names its place and waits

- **WHEN** #90 is in the fifth of twelve places and waits on #82
- **THEN** #90's body holds a block saying it is in the fifth of twelve
  places, that it
  waits on #82 with the reason, and linking the order's issue

### Requirement: The script edits only the text between its markers

The order's issue body and each block SHALL lie between the lines
`<!-- sequencer:begin -->` and `<!-- sequencer:end -->`, and the script
SHALL change nothing in a body outside them. It SHALL add a new block
just before the body's last line when that line starts with `prose ✓`,
so that the signed footer the prose skill puts at the end of posted text
stays last, and at the body's end otherwise.

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

### Requirement: A block is rewritten only when the order or its reasons change

The script SHALL edit a body only when the text between its markers would
change, and that text SHALL hold no date or time but these fixed ones: when
a cycle was first listed, and when a `publish --decide` override was
recorded.

#### Scenario: An unchanged order edits nothing

- **WHEN** the daily run finds the same order and reasons as the last
  publish
- **THEN** the script makes no edit to any body

### Requirement: An item that leaves the order loses its block

When an item leaves the order, by closing, merging or ceasing to be linked,
the script SHALL remove its block, markers included, and leave the rest of
its body as it was.

#### Scenario: A merged pull request's block is removed

- **WHEN** #82 merges
- **THEN** the next publish removes #82's block, and the order does not
  hold #82

### Requirement: An item the script cannot edit is named, not skipped silently

Where the script cannot edit an item's body, the order's issue SHALL name
the item as having no block, saying why.

#### Scenario: A body the token cannot edit is reported

- **WHEN** editing #95's body fails with a permission error
- **THEN** the order still places #95, and the order's issue says #95 has no
  block because the edit was refused

### Requirement: The order's issue names each reviewer's next review

The order's issue SHALL name, for each reviewer, the open pull request,
neither a draft nor authored by them, that they should review next: of
those awaiting their review, the one with the most items after it through
edges, followed directly or not, and on a tie the one earlier in the
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
  awaits #82 and #84, and only one item comes after #84, directly
- **THEN** #82 counts two items after it, and is that reviewer's next
  review

#### Scenario: A draft is not offered for review

- **WHEN** #93 is a draft requesting review from a reviewer
- **THEN** #93 is not that reviewer's next review

### Requirement: A pull request awaits a reviewer until they review its current head

A pull request SHALL stop awaiting a reviewer once that reviewer submits
a review of any kind on its current head commit, as the review's
`commit_id` in GitHub's pull request reviews API shows. When a push
changes its head, it SHALL await that reviewer again.

#### Scenario: A review of the current head takes a pull request off the queue

- **WHEN** `maya` submits a review of #97 whose `commit_id` is #97's head
  commit
- **THEN** #97 no longer awaits `maya`, and is not her next review

#### Scenario: A push after a review puts the pull request back on the queue

- **WHEN** `maya` reviewed #97 at its head commit, and a later push gives
  #97 a new head commit
- **THEN** #97 awaits `maya` again

### Requirement: Reviewers come from the repository's config, else from GitHub's requests, else CODEOWNERS

A non-draft pull request SHALL await every login in the `reviewers` list
of `.github/sequencer.json` on the default branch, except its author. With no
such list, it SHALL await each
reviewer it has requested on GitHub, including one GitHub dropped from
the list on their review. Having requested no one, it SHALL await the
owners CODEOWNERS gives its changed files. Every caller SHALL take
reviewers this way, except as *Only a dry run takes a reviewer list*
allows.

#### Scenario: A configured list makes each pull request await each reviewer

- **WHEN** `.github/sequencer.json` lists the reviewers `maya` and `li`,
  and `li` authored #97
- **THEN** #97 awaits `maya`'s review, and every other non-draft open pull
  request awaits both

#### Scenario: A pull request requesting no one falls back to CODEOWNERS

- **WHEN** `.github/sequencer.json` does not exist, #96 requests no
  reviewer, and CODEOWNERS gives `@maya` the files it changes
- **THEN** #96 is awaiting `@maya`'s review

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

### Requirement: The workflow recomputes the order on each event that can change it

The workflow SHALL run the script when an issue is opened, edited, closed
or commented on; when a pull request is opened, edited, marked ready for
review, reviewed, or closed, merged or not; when a push reaches an open
pull request's branch; when a Sequencer Igor dispatches it; and once a
day. All its runs SHALL share one
concurrency group, so no two of them edit a body at once.

#### Scenario: Two quick merges run one after the other

- **WHEN** two pull requests merge a second apart
- **THEN** the second run starts only after the first has finished

#### Scenario: An override comment reorders the work

- **WHEN** a person with write access comments `#85 first` on the order's
  issue about a listed cycle
- **THEN** a run starts on that comment and places #85 first

#### Scenario: A pull request closed without merging leaves the order

- **WHEN** #88 is closed without merging
- **THEN** a run starts on that event and removes #88's block

### Requirement: The workflow's deterministic part needs no secret

The workflow SHALL compute and publish an order with no secret but the
token GitHub gives each run, whichever way the repository chose to run the
model step.

#### Scenario: A repository with no secrets gets an order

- **WHEN** a repository holding no secret runs the workflow
- **THEN** it publishes the order, saying build dependencies between
  changes' code were not checked

### Requirement: The repository chooses how the model step runs

`setup-ci` SHALL write the workflow for one of three ways of running the
model step, which the repository chooses: not at all; through the API key
the repository holds as the secret `ANTHROPIC_API_KEY`; or by an Igor.

#### Scenario: The default runs no model step

- **WHEN** `setup-ci` runs with no choice given
- **THEN** the workflow it writes runs no model step

### Requirement: With an API key, the model step is one API call with no tools

Where the repository chose its API key, `publish --model api` SHALL run the
model step, only while a pair of writers' changes is unchecked, as one
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

- **WHEN** an outside account's comment triggers a run, and every pair of
  writers' changes is checked
- **THEN** the script makes no API call

#### Scenario: A reply that does not parse checks nothing

- **WHEN** the model's reply is prose rather than the edges' structure
- **THEN** the script takes no edge from it, and the order says build
  dependencies between changes' code were not checked

#### Scenario: A missing key leaves code unchecked

- **WHEN** a repository that chose its API key holds no `ANTHROPIC_API_KEY`
- **THEN** the order is published, saying build dependencies between
  changes' code were not checked

### Requirement: With an Igor, the workflow labels the order's issue for the model step

Where the repository chose an Igor, `publish`, as the workflow runs it,
SHALL keep the order's issue labelled `sequencer: check code` exactly while
the order it publishes leaves unchecked a pair of changes whose pull requests writers opened.

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
file, as a Sequencer Igor sends after running the model step on the issue
labelled `sequencer: check code`, and publish it with `publish --code-edges`
under the checks any caller's edges file gets and in the same concurrency
group.

#### Scenario: A dispatched edges file is published

- **WHEN** a `workflow_dispatch` run carries an edges file whose changes
  are unchanged
- **THEN** the run publishes its edges, in the workflow's concurrency group

#### Scenario: A dispatched pair whose change was revised leaves the label on

- **WHEN** a dispatched run carries a pair holding #90, and a push revised
  #90's change after the model step read it
- **THEN** the workflow's `publish` drops that pair, and the label
  `sequencer: check code` stays on the order's issue

### Requirement: The workflow runs no code from a pull request

The workflow SHALL run only the script, from the shared-skills commit that
`setup-ci` writes into the template, reading pull requests' files as
data, and SHALL NOT check out or run code from a pull request's head.

#### Scenario: A fork's pull request cannot run code with the token

- **WHEN** a pull request from a fork changes `.github/workflows/` and adds
  a script
- **THEN** the run reads the pull request's change files as data and runs
  none of its code

### Requirement: The model step needs only the order's printed output

The model step SHALL need nothing but `order --json` output, which SHALL
include the open changes' files, so an agent with no GitHub credential,
such as an Igor's worker, can run it and write an edges file, which
`publish`, run elsewhere, applies.

#### Scenario: An edges file written without GitHub access is published

- **WHEN** an agent with no GitHub credential runs the model step on
  `order --json` output and writes an edges file, and the workflow
  publishes that file while the changes it checked are unchanged
- **THEN** `publish` takes the edges

### Requirement: Data names an item by its repository and number

`order --json`, an edges file, and the checked pairs and code edges the
order's issue stores SHALL name each item, and each change's pull request,
by its repository and its number together. Text the script publishes
SHALL write an item as `#<number>`. `publish` SHALL refuse an edges file
that names an item by number alone.

#### Scenario: order --json names an item by repository and number

- **WHEN** a caller runs `order --json` in the repository
  adamstallard/shared-skills, and the order holds #82
- **THEN** the output names that item by the repository
  `adamstallard/shared-skills` and the number 82

#### Scenario: A stored code edge names both items by repository and number

- **WHEN** `publish` stores the model step's edge of #90 after #82 in the
  order's issue, in the repository adamstallard/shared-skills
- **THEN** the stored edge names each of the two by the repository
  `adamstallard/shared-skills` and its number, and the order's line for
  #90 says `after #82`

#### Scenario: An edges file naming an item by number alone is refused

- **WHEN** an edges file's edge names its two items as 90 and 82, with no
  repository
- **THEN** `publish` publishes none of that file's edges, and says which
  edge it refused

### Requirement: The script prints the order for callers without editing anything

`order` SHALL print the order, each item's position, its edges with
reasons, the links to outside items, the cycles, the copies owed, the
names each pair of changes' `tasks.md` files both hold, for the model step,
and each change's hash, as JSON with `--json`, and SHALL write to no
issue or pull request; `publish` SHALL be the only command that edits.

#### Scenario: An Igor reads positions without editing

- **WHEN** an Igor's work triage runs `order --json`
- **THEN** it gets each item's position, the open changes' files and each
  change's hash, and no body, label or comment in the repository changes
