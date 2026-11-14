The sequencer is a skill that recommends the order in which a repository's
open work is specified, implemented, reviewed and merged. Shared-skills
issue #43 and adamstallard/igor#231 hold the discussion behind it.

Terms used throughout, as the spec defines them:

- **An item** is an open issue or pull request the order holds. **The
  order's issue** is the one issue whose body holds the whole order.
- **An edge** is a rule's finding that one item comes after another, with
  its reason. The rules that set edges are **modifies** (a change that
  modifies a requirement another change adds comes after it), **cites** (a
  change that names another change's requirement comes after it),
  **explicit links** (GitHub's "blocked by" relations and `Depends on #n`
  lines) and the model step's rule, below.
- **A copy duty** sets no edge. Where two changes modify one requirement,
  whichever archives second must add the other's new scenarios to its own
  copy of the requirement, since archiving replaces the requirement with
  the archiving change's whole copy.
- **A cycle** is a set of items whose edges lead from each back to itself.
- **A merge wait** is not an edge either: where two pull requests change a
  file in common, the later in the order waits for the earlier to merge.
- **The model step** applies the one rule that needs a model: a change
  whose code will call another change's code is built after it.
- **A caller** is whatever runs the script: an agent in a session, the CI
  workflow, or an Igor, one of the AI teammates of adamstallard/igor.
- **Gate one** is approving a change's spec, in a pull request holding
  only the spec; **gate two** is its implementation, built on the same
  branch after that approval.

## Context

Agents work out "what next, what to review, what merges first" by hand in
each session. adamstallard/igor#204 shows the cost: one archive order for 23
changes, the order in which their OpenSpec changes are archived into the
main specs, took about a week of edits. Under the two-gate workflow that
one order is also, with few exceptions, the order to build, review and
merge in.

## Goals / Non-Goals

**Goals:** one deterministic order, whoever computes it; a reason for each
place a rule decides; an order kept in issue and pull request bodies, which
`gh issue view` and `gh pr view` print without comments; review effort
pointed at what unblocks the most; questions of judgement left to a person.

**Non-Goals:** merging; choosing a cycle's order; what Igor builds for its
Sequencer role (igor#231); the spec-checker's dry archive, which archives
every open change in the order into a scratch copy of the default branch
to prove the order applies, and which igor#231's decision 7 gives to Igor's
spec-checker.

## How the script runs

The script is `.agents/skills/sequencer/scripts/sequencer.py`. It has three
commands:

- `order [--json] [--reviewers <login>,...]` computes the order and
  prints it, with a hash of its inputs and, for each pair of open changes,
  the backticked names that appear in both changes' `tasks.md` files, to
  help the model step. `--reviewers` tries a reviewer list in place of the
  configured one. It edits nothing.
- `publish [--code-edges FILE | --model api] [--decide '#<n> first' --by <login>]`
  computes the order and edits the order's issue and the items' bodies. It
  takes the model step's edges from `FILE`, which carries the inputs hash
  `order` printed, or from one API call with `--model api`, and records a
  person's choice in a cycle given with `--decide`, naming that person with
  `--by`.
- `setup-ci [--model-step none|api-key|igor] [--lore <owner>/<repo>] [--force]`
  writes the workflow template, and with `--lore` names the team's lore
  repository in `.github/sequencer.json`.

In a session, the agent runs `order`, applies the model step to the
printed changes and names, writes its edges to a file, and runs `publish
--code-edges` with it. The CI workflow runs `publish` on each trigger,
as `publish --model api` where the repository chose to run the model step
on its own API key. Where it chose an Igor, `publish` labels the
order's issue, and a Sequencer Igor runs the model step and publishes its
edges through the same script.

## Decisions

Each entry states the decision and its reasons. An alternative not taken
that a test can check is marked ***Ruled out by a scenario***, naming the
requirement whose scenario it would fail. The capability's decision record,
`openspec/specs/sequencer/decisions.md`, holds three kinds of entry: a
constraint no test can check, an alternative no requirement guards against,
and a requirement's reason that rests on evidence (a failure, a measurement
or an outside fact). A reason with no such evidence stays here, in
design.md.

### A skill, with Igor's role as one caller

**The rules and the script live in a shared-skills skill; Igor's Sequencer
role is one caller of it,** as Igor's inquisitor role calls the inquisitor
skill (igor#231, decision 9). Igor adds what only a running Igor can do:
builders claiming work in the order, and gate two waiting on the changes
before it.

### The script is Python

**The script is Python, checked by `pyright --strict`,** since it is glue
over `gh`, `git` and the OpenSpec CLI, and data work on what they return.

### The rules are read from the changes' files, with no model

**Modifies, cites, copy duties and cycles come from the open changes' files,
read through the OpenSpec CLI, and the same inputs give the same text.** A
deterministic order means any two callers agree, and a reviewer can check
a reason against the files it names.

- *Ruled out by a scenario:* a model choosing the rule-decided places
  (*The same inputs give the same order whoever runs the script*).

A citation is a requirement's full title appearing verbatim in another
change's files. Titles in this repository's specs are whole sentences, so
a verbatim match rarely fires by chance, and spec authors already cite a
requirement by its title in italics. A copy duty sets no edge, because
either of the two changes may archive first, as long as the second carries
the first one's new scenarios. The script names the change that owes the
copy: the later of the two in the order.

### Cycles go to a person

**A cycle is reported as a question and its place left unchosen,** because
whichever member archives first cites a requirement not yet in force, and
only a person may accept that gap. Once a person
chooses, the chosen member's reason links the answer.

**The order's issue body keeps the list of decided cycles, and the
sequencer checks that list before asking,** as the inquisitor's filter 1,
already answered, checks for an earlier answer. So a decided cycle is not
asked again.

**Only an agent session asks a cycle's question; CI lists the cycle in the
order's issue and asks nothing.** In a session, the agent asks through the
picker, the host's question tool, and records the answer with `publish
--decide`. A session's ask is marked in the order's issue with its time, and lapses after 7 days
unanswered, so a question asked in a session that ended without an answer
is asked again by a later one.

A run with no model can judge no free-text answer, so each question offers
its members as options labelled `#<n> first`. Every run, CI's included,
counts a comment on the order's issue that starts with one of those labels
and was posted after the cycle was first listed. The comment counts when an
account with write access posted it, or when it is a relayed answer.

A relayed answer is a `User says: ` comment that a person's relay App, the
GitHub App their answer session posts through, posted for them. Which Apps
are a person's is read from their relay file, `relays/<login>.yaml` in the
team's lore repository, the repository of shared answers the inquisitor
uses. `.github/sequencer.json` names that repository, so every caller reads
the same one, through GitHub's API under the inquisitor's *A reader counts
a relay file only when its person made its last change*. A public lore
repository is read with the workflow's own token, a private one with a
read-only token `setup-ci` stores as a secret. Without access to the lore
repository, only direct comments count, and the order's issue says so.
Relayed answers are counted only once the inquisitor's task 0.21 has
measured whether GitHub's API names the App that wrote a comment.

The decided cycles are kept in the order's issue rather than in a committed
file, as the inquisitor keeps a repository's answers, because the order's
issue has no branch to commit a file to.

- *Ruled out by a scenario:* choosing by number or age (*A cycle is asked
  about, never chosen*).

### The model step runs only where a model is available

**The model step runs in a session through the agent running the skill, and
in CI only where the repository opts in.** The deterministic part always
runs and needs no secret. The order says plainly which pairs of changes
the model step did not check, and never treats them as checked; a change
the OpenSpec CLI refuses counts as unchecked too. The names both changes'
`tasks.md` files hold point the model at the pairs worth reading. In CI,
the model step is one API call with no tools, and the script validates its
reply; the decision record's Rationale for *With an API key, the model step
is one API call with no tools* says why. Every string the script takes from
a pull request or the model is written as inline code, so a reason that
text in a pull request steered the model into writing can @-mention no
one.

- *Ruled out by a scenario:* requiring a model for every run (*The
  workflow's deterministic part needs no secret*).
- *Ruled out by a scenario:* presenting unchecked code dependencies as
  checked (*The order says plainly what it did not check*).

### One issue holds the order; each item holds its own block

**The whole order is in one issue's body, and each item's body holds a block
giving its place, between markers the script owns, never in a comment**
(igor#231, decision 1). The decision record's Rationale for *The whole
order lives in one issue's body* says why not a comment. A block is rewritten only when the order or its reasons change
(igor#231, decision 2). The
script touches nothing outside its markers, so a person may keep their own
text in the same body. The prose skill ends each body it signs with a
`prose ✓` footer, a hash of the text above it, and prose's hook reads the
footer as the body's last line. A new block goes just above that footer
so it stays last. The block changes the text the footer hashes, so a
footer already in the body stops matching it. That is harmless, because
prose's hook never checks the hash of a footer already posted.

- *Ruled out by a scenario:* keeping the order in comments (*The whole
  order lives in one issue's body*).
- *Ruled out by a scenario:* stamping each block with the date of the last
  run (*A block is rewritten only when the order or its reasons change*).

### Explicit links and overlapping files, in every repository

**Explicit links and overlapping files order work in every repository,
whether or not it has OpenSpec changes,** since an OpenSpec repository
still has issues with no change yet and code pull requests that overlap. A
repository without OpenSpec gets its order from them alone, and the order
says dependencies between requirements were not checked. Overlapping files
give merge waits: each later pull request waits for the earlier one that
shares its files, and rebases once, onto it, rather than after every
merge. A merge wait follows the order the other rules and the
tiebreak give, and never changes it.

### Reviewers

**The order's issue names each reviewer's next review, ranking first the
pull request that the most items come after,** because reviewing it
unblocks the most work. Reviewers are the
`reviewers` list in the repository's `.github/sequencer.json`; with none,
everyone each pull request has requested on GitHub, including anyone
GitHub dropped from its request list when they submitted a review; and
when it has requested no one, the CODEOWNERS file. Every caller takes reviewers through this chain,
and `publish` accepts no reviewer list of its own, so an Igor's Sequencer
role and the CI workflow publish the same issue body for the same inputs. A draft is not offered
for review, since its author has not handed it over yet.

A spec pull request ranks ahead of the pull requests that come after it.
Ranking by how many items come after each pull request already gives
that order: every item after a later pull request is also after the
spec, and the spec has that pull request after it too, so the spec's
count is always higher. *A spec pull request is reviewed before the
implementations that build on it* states the order outright, so that a
later change to the ranking keeps it. A pull request leaves a reviewer's
queue once they review its current head, which each review's
`commit_id`, the commit it was made on, shows, and returns when a push
moves the head.

### Which issues the order holds

**The order holds every open pull request, and only the issues that an
explicit link, or a closing reference such as a pull request's `Fixes #n`,
connects to another item.** Every
open issue in a large repository would otherwise get a block, most with no
rule placing them.

### Items no rule orders go lowest number first, unasked

**Among items no rule orders, the lowest number goes first, and nobody is
asked, for every caller, Igor's Sequencer included.** The order needs a
deterministic tiebreak, nearly every pair of items is unordered, and a
wrong guess is cheap to reverse.

- *Ruled out by a scenario:* asking a person about each unordered pair
  (*Items no rule orders keep the order they were opened in*).

### The order's issue is found by its label

**The order's issue is the one open issue labelled `sequencer`.** `publish`
creates it when none is open, and refuses, naming both, when there are
two. A person with write access, or `igor init` running under such a
person's login, can also make one by adding the label, and no
configuration names it. The script refuses a labelled issue whose author
lacks write access; the decision record's Rationale for *The whole order
lives in one issue's body* says why.

### Code edges outlast runs with no model

**The order's issue body stores each model-step edge with one hash for each
of the two changes it joins, of that change's files, and a later run keeps
the edge while both hashes match.** These per-change hashes keep the order
steady between a Sequencer Igor's runs where the repository hands it the
model step. A CI run with no model, after a merge, keeps the code edges
the Igor found for the changes the merge left unchanged.

**An edges file also carries the inputs hash, a hash of everything `order`
read to compute the order it was built from, and `publish` refuses the
file when the inputs it reads hash differently.** This stops a result
computed before a merge from overwriting the order computed after it. Any
change to the inputs, such as a newly opened issue, makes a file stale, and
the model step runs again on the new order. Both hashes adopt igor#231's
hash recommendation for every caller.

### Three ways Igor uses the skill

**An Igor uses the skill in three ways, and the skill expects of each only
what it expects of any caller:**

- An Igor's worker may run the skill in its own session, as any agent
  does. A worker's session has no person in it, so it asks a judgement
  question in its handback comment, the comment in which its Igor hands
  the item back to a person, as the inquisitor's *A session with no person
  in it asks in a post, a handback or nowhere* says.
- An Igor in the Sequencer role, a Sequencer Igor, calls the script,
  which takes reviewers as *Reviewers* above says for any caller. Igor's work triage, the step
  where an Igor chooses which items to take, reads positions from
  `order --json`.
- Where a repository hands the model step to an Igor, `publish`, run by
  the workflow, labels the order's issue `sequencer: check code`. A
  Sequencer Igor then runs the model step and publishes its edges through
  the script.

What Igor builds for these, such as claiming the labelled issue, editing a
body from its loop and gating gate two on the order, is igor#231's.

### It recommends and never merges

**The sequencer recommends a merge order and never merges, approves or
closes anything.** Under the repository's workflow (AGENTS.md), a person
approves each pull request's specification and its implementation, and
merging belongs with that approval; the sequencer only orders work.

- *Ruled out by a scenario:* merging the first approved pull request (*The
  sequencer recommends a merge order and never merges*).

### Judgement questions go through the inquisitor

**A question of judgement goes through the inquisitor skill as a question
the sequencer requires a person to decide** (#43). The inquisitor has four
filters, which stop a question before a person sees it: 1, already
answered; 2, deferrable; 3, not a real question; 4, cheap to reverse. A
question another skill requires a person to decide skips filters 2 and 4
(the inquisitor's *A question another skill requires skips filters 2 and
4*), since those let an agent defer or decide the question itself. Filter 3
never stops a cycle's question either: the sequencer lets only a person
choose any of a cycle's members (*A cycle is asked about, never chosen*),
and filter 3, which has the agent take a question's one option of merit
itself, never takes an option the requiring skill reserves for a person. In a
session the question is asked through the picker. CI asks nothing. Until it
is answered, the order leaves that place unchosen.

### The CI workflow

**`setup-ci` writes the workflow template and never overwrites a copy
already there; `--force` replaces it** (#43), as spec-check's `setup-ci`
does. The template triggers on every event that can change the order:
issues opened, edited, closed or commented on; pull requests opened,
edited, marked ready, reviewed or closed, merged or not; pushes to an open
pull request's branch; and a daily run. All share one `concurrency` group,
so no two workflow runs edit the same body at once.

The template uses `pull_request_target`, and reads each pull request's
change files through `git fetch` of its head and the OpenSpec CLI, never
running them. `openspec/specs/sequencer/decisions.md` gives the reasons
for both choices: *Rejected: Running the workflow on `pull_request`*, and
the Rationale for *The workflow runs no code from a pull request*. The
repository's choice of model step is written into the template by
`setup-ci --model-step`, so changing it is a reviewed change to the
workflow file.

- *Ruled out by a scenario:* overwriting a customised workflow (*The setup
  command writes the CI workflow and never overwrites it*).
- *Ruled out by a scenario:* checking out a pull request's head with a write
  token (*The workflow runs no code from a pull request*).

## Risks / Trade-offs

- **A wrong edge from a verbatim title match.** A short title could appear
  in another change's prose by chance. The reason names the title, so a
  reviewer sees it at once.
- **A large repository's first publish edits many bodies.** Each item gets
  one edit, and later runs edit only blocks whose text changes.

## Open Questions

- **Whether edges from authors without write access count.** Anyone who
  can open a pull request or an issue can steer the order: a requirement
  title copying a sentence in another change makes that change cite it, a
  citation back makes a cycle that leaves that change unplaced until a
  person chooses, and issues saying
  `Depends on #<n>` raise #n in every reviewer's queue.
- **How an ask without a picker is answered.** An Igor worker asks in its
  handback comment, where the person answers on the item's thread, which
  no run reads, and its Igor cannot record the answer with `publish
  --decide` under the person's login. Such an ask never decides the cycle.
- **Whether a cycle question is logged.** Through the inquisitor, each
  asked question is logged as a file in its repository or the team's lore
  repository, and the inquisitor lists no exemption for the sequencer's;
  this change keeps the answer only in the order's issue.
- **A Sequencer Igor's publish racing the workflow's.** The decision
  record accepts the later write; igor#231 says two runs must not race to
  edit one body.

Tasks 0.1 to 0.4 measure four facts before building. The last bullet is a
fact the inquisitor's task 0.21 measures, which relayed answers wait on.

### Facts measured before building

Each bullet says what the spec does if the fact is false.

- **GitHub's "blocked by" relations can be read through its API with the
  workflow's token** (task 0.1). If not, the order reads only `Depends on`
  lines and says that blocked-by relations were not read.
- **A `pull_request_target` run's token can edit the body of a pull request
  from a fork** (task 0.2). If not, a fork's pull request is placed but gets
  no block, which *An item the script cannot edit is named, not skipped
  silently* covers.
- **`openspec show --json` gives each delta's operation and title for a
  change read outside a checkout** (task 0.3), as spec-check relies on. If
  it needs a checkout, the script writes each head's change files, read
  with `git show`, into a scratch directory laid out as an `openspec/`
  tree and runs the CLI there.
- **A run on a review of a fork's pull request can edit bodies** (task
  0.4). Reviews trigger through `pull_request_review`, which for a fork's
  pull request may get a read-only token. If so, that run publishes
  nothing, and the next run with a write token, at the latest the daily
  one, publishes the order.
- **GitHub's API names the App that wrote a comment** (the inquisitor's
  task 0.21). Relayed answers are not counted, and no lore token is set
  up, until it is measured. If GitHub does not, the repository's owner
  decides what to build, as that task says.
