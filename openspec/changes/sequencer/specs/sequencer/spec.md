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
  An item's **number** is its issue or pull request number.
- **The order's issue** is the one issue whose body holds the whole order.
- **A change** is an OpenSpec change: a directory under `openspec/changes/`
  other than `archive/`. **An open change** is one on the default branch or
  on an open pull request's head. A change **belongs to** the
  lowest-numbered open pull request whose diff against its base adds or
  changes a file in the change's directory, and the order places the
  change where it places that pull request.
- **A change's requirement** is a requirement that the change's delta adds,
  or renames onto a new name, and that no spec on the default branch holds.
- **An explicit link** is a GitHub "blocked by" relation, a `Depends on`
  line in a body, or a `Builds on:` line in a change's `proposal.md`, as *Explicit links order the items they connect*
  defines.
- **An edge** is a rule's finding that one item comes after another, with
  its **reason**. **A cycle** is a set of items whose edges lead from each
  back to itself. **A merge wait**, set by *Pull requests that change the
  same files merge one after another*, is not an edge.
- **The inputs hash** is a hash of everything the script read to compute
  an order, which `order` prints. It leaves out the order text the script
  itself published and the stored checked pairs and code edges, so that
  publishing does not change it. It does hash the cycle overrides, since
  an override changes the order an edges file was computed against.
- **The model step** applies the one rule that needs a model: a change
  whose code will call another change's code is built after it.
- **The inquisitor's** *Title* names a requirement of the inquisitor spec.
- **A Sequencer Igor** is an Igor in the Sequencer role; **an Igor's work
  triage** is the step where an Igor chooses which items to take.
- **A relay App**, **a relay file**, **a lore repository**, **the team's
  lore repository** and **the inquisitor's configuration** are the
  inquisitor spec's terms.

## ADDED Requirements

### Requirement: The order holds every open pull request and the issues linked to the work

The order SHALL hold each open pull request, and each open issue that an
explicit link or a pull request's closing reference connects to another
item, and no other issue; the order's issue is never an item.

#### Scenario: An issue linked to nothing is not ordered

- **WHEN** an open issue has no explicit link to or from another issue or
  pull request, and no open pull request closes it
- **THEN** the order does not hold it, and its body gets no block

#### Scenario: A blocked issue is ordered

- **WHEN** open issue #12's body has the line `Depends on #9`
- **THEN** the order holds both #12 and #9

#### Scenario: The order's issue is never ordered

- **WHEN** the order's issue is #40, and #12's body has the line
  `Depends on #40`
- **THEN** the order does not hold #40, and #40's body gets no item block

### Requirement: An issue an open pull request closes takes that pull request's place

Where open pull requests close an issue by GitHub's closing references,
the issue SHALL share the position of the lowest-numbered of those opened
by accounts with write access, and its block SHALL name that pull request.
Every edge to or from the issue SHALL apply to that pull request instead.
A closing reference from an author without write access SHALL neither move
an issue nor bring one into the order.

#### Scenario: A spec pull request and its issue share a place

- **WHEN** open pull request #50 closes issue #43, and #50 is third in the
  order
- **THEN** #43 is third too, and its block says it is closed by #50

#### Scenario: An issue two pull requests close follows the lower-numbered

- **WHEN** #50 and #57 both close issue #43
- **THEN** #43 shares #50's place, and its block names #50

#### Scenario: A closed-by issue's own link moves onto its pull request

- **WHEN** #50 closes issue #43, and #43's body says `Depends on #61`
- **THEN** #50 comes after #61, and #43 shares #50's place

#### Scenario: An outside author's closing reference moves nothing

- **WHEN** `zed`, without write access, opens #48 saying `Fixes #43`, and
  #50, opened by a writer, also closes #43
- **THEN** #43 shares #50's place, not #48's, and gains no place from #48
  alone

### Requirement: Each change is read from the head of the pull request it belongs to

Where several open pull requests' heads hold one change's directory, the
script SHALL read the change, and compute its hash for *A checked pair is
kept while both its changes are unchanged*, from the head of the
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
take no edge or copy duty from that change's files, and the order's issue
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

#### Scenario: A copy duty inside a cycle follows the cycle's order

- **WHEN** #82 and #90 both modify *Claims expire after an hour*, they form
  a cycle ordered by rule, and then a writer's `#90 first` overrides it
- **THEN** the order's issue first says #90 owes the copy, and after the
  override says #82 owes it

### Requirement: Explicit links order the items they connect

An item SHALL come after each item that a GitHub "blocked by" relation or a
`Depends on` line in its body says it waits on, and a change's pull request
after each pull request its `proposal.md`'s `Builds on:` lines name in this
repository. A `Depends on` line SHALL be a body line, outside code fences,
starting `Depends on ` and followed by `#<number>` references separated by
commas or `and`.

#### Scenario: A Depends on line orders two issues

- **WHEN** #12's body holds the line `Depends on #9 and #10`
- **THEN** #12 comes after #9 and #10, with the reasons `after #9: depends
  on it` and `after #10: depends on it`

#### Scenario: A Depends on line with commas orders each item it names

- **WHEN** #12's body holds the line `Depends on #9, #10, #11`
- **THEN** #12 comes after #9, #10 and #11

#### Scenario: A Builds on line orders a stacked change

- **WHEN** #64's change's `proposal.md` says
  `Builds on: inquisitor (adamstallard/shared-skills#25)`, in the
  repository adamstallard/shared-skills
- **THEN** #64 comes after #25, with the reason `after #25: builds on it`

#### Scenario: A blocked-by relation orders two items

- **WHEN** GitHub records #14 as blocked by #11
- **THEN** #14 comes after #11, with the reason `after #11: blocked by it`

#### Scenario: A Depends on line in a code fence is ignored

- **WHEN** the only `Depends on #9` in #12's body is inside a code fence
- **THEN** it gives no edge

### Requirement: Only edges set by writers count

An edge SHALL count only when every item whose text sets it was opened by an
account with write access: both changes' pull requests for an edge from
changes' files or the model step, and the item holding the `Depends on`
or `Builds on:` line, or the blocked item, for an explicit link. The order's issue SHALL
list each other edge as not counted, naming the author.

#### Scenario: A Depends on line from an outside author is not counted

- **WHEN** issue #120, opened by `zed` who has no write access, says
  `Depends on #95`
- **THEN** #120 gains no edge after #95, #95 gains no rank from it, and the
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

Among the items whose predecessors are all placed, the lowest-numbered SHALL
go next, and a cycle SHALL count as one item numbered as its lowest member.
No caller, an Igor's Sequencer role included, SHALL ask a person about a
place this tiebreak or a cycle's rule decides.

#### Scenario: Two unrelated items are placed by number

- **WHEN** no edge connects #20 and #17
- **THEN** #17 comes before #20, and neither block gives a reason for that
  place

#### Scenario: A cycle is placed by its lowest member

- **WHEN** #40 and #44 form a cycle, and #42 is connected to neither
- **THEN** the cycle comes before #42, placed as if numbered #40

#### Scenario: An unordered pair raises no question

- **WHEN** a Sequencer Igor reads an order in which no edge connects #20
  and #17
- **THEN** no question about their order is posted or asked

### Requirement: A cycle's members are ordered by rule

The order SHALL place a cycle's members together at one place, lowest number
first, marked `ordered by rule since <time>` with the time the publish that
first listed the cycle ran, or just `ordered by rule` before any publish
has listed it, and place each item that comes after any member after
all of them. A member placed before another member it has an edge after
SHALL say so in its reason.

#### Scenario: Two changes that cite each other are ordered by number

- **WHEN** #82's change cites a requirement #85's adds, and #85's cites one
  #82's adds, and no override is recorded
- **THEN** the order places #82 then #85 at one place, marked
  `ordered by rule since <time>`, and #82's reason says
  `` before #85 by rule, though it cites #85's `<title>` ``
- **AND** #91, which cites #85, comes after both

#### Scenario: A cycle found in CI asks no one

- **WHEN** a CI run finds a cycle between #82 and #85
- **THEN** it posts no question, and the order's issue lists the cycle as
  ordered by rule

### Requirement: A cycle override is kept and followed

The order's issue SHALL keep a list of cycle overrides, each naming the
member a person with write access put first and linking their comment or,
for one that `publish --decide` recorded, naming the `--by` login and the
time. The order SHALL put that member first and the rest by number, and its
reason SHALL give the same link, or login and time.

#### Scenario: An override puts a higher number first

- **WHEN** a person with write access put #85 first, in a cycle where #82
  and #85 cite each other's requirements
- **THEN** #85 comes first, with the reason
  `` before #82, though it cites #82's `<title>`: chosen at <link to the comment> ``,
  and #82 comes after it

#### Scenario: An override recorded in a session names who chose and when

- **WHEN** an agent runs `publish --decide '#85 first' --by maya`
- **THEN** the overrides list #85 first, chosen by `maya`, with the time it
  was recorded

### Requirement: A cycle override is read from the order's issue

A run SHALL read a comment on the order's issue, after any `User says: `
prefix, as an override when it was posted after the cycle's
`ordered by rule since` time and its text starts with
`#<n> first`, `#<n>` being one of the cycle's members, and an account with
write access posted it or it is a relayed answer from such a person (the
inquisitor's *A relayed answer counts as its person's own comment*).

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

#### Scenario: A relayed answer overrides the rule

- **WHEN** `alice-relay`, `alice`'s relay App, comments `User says: #85
  first` on the order's issue after the cycle was listed, and `alice` has
  write access
- **THEN** the next run adds the override, linking that comment

### Requirement: A relay file is read through the inquisitor's reader from the configured lore repository

The `lore` key of `.github/sequencer.json` SHALL name the team's lore
repository; the script SHALL read relay files there as the inquisitor's *A
relay file is read as last fetched, through the API without a clone, or as
igor last applied it* says, and count each as its *A reader counts a relay
file only when its person made its last change* says. It SHALL read none
where the caller's inquisitor configuration names another as the team's.

#### Scenario: A session with a lore clone reads it

- **WHEN** a session whose inquisitor configuration has a clone of
  `acme/lore`, the repository `.github/sequencer.json` names, runs the
  script
- **THEN** it reads `relays/alice.yaml` as that clone's remote-tracking
  branch last fetched it

#### Scenario: CI reads the relay file through the API

- **WHEN** a CI run, which has no clone of `acme/lore`, needs
  `relays/alice.yaml`
- **THEN** it reads the file and its newest commit through GitHub's API at
  the default branch's head

#### Scenario: A Sequencer Igor reads the relay file igor last applied

- **WHEN** the lore repository's newest commit adds `alice-relay` to
  `relays/alice.yaml`, and igor has not applied it
- **THEN** a Sequencer Igor's `order` does not count `alice-relay`

#### Scenario: A configured lore repository that is not the team's is not read

- **WHEN** `.github/sequencer.json` names `acme/lore`, and the session's
  inquisitor configuration serves this repository from `acme/team-lore`
- **THEN** the script reads no relay file, and the order's issue says
  relayed answers were not read

### Requirement: Relayed answers wait on the inquisitor's tasks 0.21 and 0.22

Relayed answers, and the relay-file reading they need, SHALL be built only
once the inquisitor's tasks 0.21 and 0.22 are measured.

#### Scenario: Before the measurements, no relayed answer counts

- **WHEN** the inquisitor's task 0.21 is not yet measured, and
  `alice-relay` comments `User says: #85 first` on the order's issue
- **THEN** the comment overrides no cycle

### Requirement: Without the lore repository, only direct answers count

With no `lore` key, or no access to the repository it names, the script
SHALL count only comments that accounts with write access posted
themselves, and the order's issue SHALL say
`Relayed answers were not read: <reason>.`

#### Scenario: A private lore repository without its token

- **WHEN** a CI run cannot read the private lore repository that
  `.github/sequencer.json` names
- **THEN** a `User says: ` comment overrides no cycle, a direct comment
  still does, and the order's issue says relayed answers were not read

### Requirement: The workflow reads the lore repository with its own token, or a private one's secret

The workflow SHALL read the lore repository with the token GitHub gives each
run, needing no setup when that repository is public. Only for a private
one SHALL it use the secret `SEQUENCER_LORE_TOKEN`, a read-only token,
which `setup-ci --lore <owner>/<repo>` adds with `gh secret set` from
standard input after writing `lore` into `.github/sequencer.json`.

#### Scenario: A public lore repository needs no secret

- **WHEN** `setup-ci --lore acme/lore` runs, and `acme/lore` is public
- **THEN** `.github/sequencer.json` has `"lore": "acme/lore"`, no secret is
  added, and the workflow reads relay files there with its own token

#### Scenario: Setup adds the token for a private lore repository

- **WHEN** `setup-ci --lore acme/lore` runs, and `acme/lore` is private
- **THEN** `.github/sequencer.json` has `"lore": "acme/lore"`, and the
  repository holds the secret `SEQUENCER_LORE_TOKEN` read from standard
  input

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
for each pair of open changes, the backticked names that both changes'
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

An edges file SHALL name every pair of changes the model step checked. The
order's issue SHALL record each checked pair, with any edge found and one
hash of each change's files. A later run SHALL count the pair checked, and
keep its edge, while both hashes match. `publish` SHALL refuse an edges
file whose inputs hash differs from that of what it reads.

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

#### Scenario: Edges computed against changed inputs are refused

- **WHEN** the model step computed edges from an `order` run before a
  merge, and the merge changed the inputs
- **THEN** `publish` refuses that edges file and publishes nothing from it

#### Scenario: Edges computed against the same inputs are taken

- **WHEN** the order was published again after the model step's `order`
  run, but no input has changed
- **THEN** `publish` takes the edges

### Requirement: The order says plainly what it did not check

The order's issue SHALL say `Build dependencies between changes' code were
not checked.` when no model step has checked any pair of open changes, and
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

Given the same repository state, the same recorded code edges and the same
access to the lore repository, the script
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
write access to the repository, and otherwise publish nothing and name
the issue and its author. Nothing of the order SHALL go in a comment, because `gh issue view`
shows a body without its comments.

#### Scenario: The first publish creates the order's issue

- **WHEN** the script publishes in a repository with no open issue labelled
  `sequencer`
- **THEN** it opens one, labelled `sequencer`, whose body holds the order

#### Scenario: Two order issues stop the publish

- **WHEN** two open issues are labelled `sequencer`
- **THEN** the script edits nothing and names both issues

#### Scenario: An order issue opened without write access is refused

- **WHEN** the one open issue labelled `sequencer` was opened by an
  account without write access to the repository
- **THEN** the script reads none of the cycle overrides or stored code
  edges in its body, edits nothing, and names the issue and its author

### Requirement: Text from a pull request or the model is written inert

The script SHALL write each string taken from an issue, a pull request, a
change's files or the model step, such as a reason, a requirement's title or
a file path, as inline code delimited by a backtick run longer than any in
it, with its line breaks as spaces, so mentions, links and markers in it
render inert. It SHALL refuse a string holding `<!-- sequencer:end -->`.

#### Scenario: A mention in a model's reason does not notify

- **WHEN** a model-step edge's reason is `calls claim() @maya see
  https://example.com`
- **THEN** the block shows that reason inside inline code, and GitHub
  notifies no one and renders no link

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

- **WHEN** #90 is fifth of twelve and waits on #82
- **THEN** #90's body holds a block saying it is fifth of twelve, that it
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
  body's last line, though that footer's hash no longer matches the text
  above it, which the script allows

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

### Requirement: A spec pull request is reviewed before the implementations that build on it

A spec pull request is one whose diff against its base changes only files
under `openspec/`. Where a reviewer awaits both a spec pull request and a
pull request that comes after it through edges, the spec pull request
SHALL rank ahead of it for that reviewer's next review.

#### Scenario: A spec is offered before the code that waits on it

- **WHEN** a reviewer awaits #82, which changes only files under
  `openspec/`, and #95, a code pull request whose body says
  `Depends on #82`
- **THEN** the order's issue names #82, not #95, as that reviewer's next
  review

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
of the repository's `.github/sequencer.json` except its author. With no
such list (no file, no key or an empty list), it SHALL await each
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
model step. A secret, such as a private lore repository's token or the
API key, only adds to that order.

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
SHALL label the order's issue `sequencer: check code` whenever it publishes
an order with a pair of changes unchecked. `publish` SHALL remove that
label when it publishes model-step edges that leave no pair unchecked, and
keep it when it refuses them.

#### Scenario: An unchecked order is labelled for an Igor

- **WHEN** a repository that chose an Igor publishes an order in which #82
  and #90 are unchecked
- **THEN** the order's issue carries the label `sequencer: check code`

#### Scenario: Publishing the model step's edges removes the label

- **WHEN** a Sequencer Igor's dispatched run publishes model-step edges
  that check every pair of open changes
- **THEN** the script removes the label `sequencer: check code`

### Requirement: A Sequencer Igor runs the model step on the labelled issue

When the issue labelled `sequencer: check code` asks for the model step, a
Sequencer Igor SHALL run it and hand its edges to the workflow, which publishes
them with `publish --code-edges` under the same checks as any caller's and
no input that only an Igor gives; what Igor builds to claim that issue and
run the model step is adamstallard/igor#231's.

#### Scenario: A stale result from an Igor leaves the label on

- **WHEN** a Sequencer Igor hands over edges computed before a merge that
  changed the inputs
- **THEN** the workflow's `publish` refuses them, and the label
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

### Requirement: An Igor's worker runs the model step on the order its Igor passes

An Igor's worker SHALL be able to run the model step in its own session on
the `order --json` output its Igor passes it, since a worker has no GitHub
credential of its own, and write an edges file. A `publish` that another process runs SHALL accept and apply an
edges file a worker wrote, while the inputs are unchanged.

#### Scenario: A worker's edges are published through the workflow

- **WHEN** an Igor passes its worker `order --json` output, the worker runs
  the model step and writes an edges file, and the Igor hands that file to
  the workflow before any input changes
- **THEN** the workflow's `publish` takes the edges

### Requirement: A Sequencer Igor publishes only through the workflow

A Sequencer Igor SHALL edit no body itself. It SHALL publish by dispatching
the workflow (`workflow_dispatch`), passing any edges file as the run's
input, so that its publishes share the workflow's concurrency group, and
dispatch again when that run is cancelled before it publishes. Its `order`
SHALL take only data that any caller could pass.

#### Scenario: A Sequencer Igor's publish waits for a running workflow run

- **WHEN** a Sequencer Igor publishes edges while a workflow run for a
  merge is still running
- **THEN** its dispatched run starts only after that run finishes, and the
  Igor edits no body itself

#### Scenario: A cancelled dispatch is sent again

- **WHEN** a Sequencer Igor's dispatched run is pending, and a comment's
  run queues in the same concurrency group, which cancels the older
  pending run
- **THEN** the Igor dispatches the workflow again with the same edges file

#### Scenario: A Sequencer Igor reads the order CI publishes

- **WHEN** a Sequencer Igor runs `order --json` against the inputs the CI
  workflow last published from, reading the same relay files
- **THEN** the positions it reads are the ones in the order's issue

### Requirement: The script prints the order for callers without editing anything

`order` SHALL print the order, each item's position, its edges with reasons,
the cycles, the copy duties, the shared names for the model step
and the hash of the inputs, as JSON with `--json`, and SHALL write to no
issue or pull request; `publish` SHALL be the only command that edits.

#### Scenario: An Igor reads positions without editing

- **WHEN** an Igor's work triage runs `order --json`
- **THEN** it gets each item's position, and no body, label or comment in
  the repository changes
