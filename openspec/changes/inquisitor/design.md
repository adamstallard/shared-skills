The inquisitor is a skill that stops an agent's needless questions to a
person. Before asking, the agent runs each question through four filters:
filter 1, already answered (it searches for an earlier answer); filter 2,
deferrable; filter 3, not a real question; filter 4, cheap to reverse
(inquisitor spec: *Every question passes four filters before a person sees
it*). Hooks on Claude Code's question picker and on GitHub posts block a
question that has not been through them.
*Terms used throughout*, under *Decisions*, defines Igor, the picker, the two
calls, a verdict and the answer session.

## Proving the filters ran

A hook can't judge whether a question has merit; only the agent can. So the
design makes skipping the filters fail, and leaves the verdicts to review.
As the prose skill proves its pass ran with a first call that prints its
rules and a second that signs the result, the inquisitor makes two script calls:

1. `inquisitor.py vet --questions q.json`, given the picker's `questions`
   array, or `vet --post body.md`, given a post's body, prints the four
   filters, runs filter 1's search for each question, prints the hits, and
   issues a token holding hashes, never text: each question's and, for a
   picker question, its first option's.
2. `inquisitor.py vet --pass <token> --verdicts v.json` records one verdict
   per question, keyed by the SHA-256 of its text.

The calls prove that the filters were printed and the search ran before each
verdict, not that the agent judged well. A hook checks each question's
latest record, and when it can't read the records, the picker hook fails
open and the post hook fails closed (inquisitor spec: *A hook blocks a
picker question that was not vetted*; *Questions in posts pass the same
filters*): an unfiltered picker question at worst reaches the person, while
a post's unchecked question might be a vulnerability.

The records live in the user's state folder, shared by every session under
one HOME, since a session spans repositories and a hook's working directory
can differ from `vet`'s (*Hooks and verdict records*). Apart from them, the
hooks keep no record of any question, one about a vulnerability included.
The question log files (*Where the logs live*) are the lasting records; for a
vulnerability question it is the repository's private security advisory.

**Ruled out by a scenario** (inquisitor spec: *A hook blocks a picker question
that was not vetted*):

- **The skill's description alone,** with no hook: a model loads a skill by
  judgement (scenario *An unvetted question is blocked*).

### What the hook relies on, not yet measured

Three facts about Claude Code are unmeasured (tasks 0.1 to 0.3): a
`PreToolUse` hook fires on `AskUserQuestion`; exit 2 blocks it and its
stderr reaches the model; and the tool's input carries
`questions[].question` and `questions[].options[].label`. If the first two
are false, the skill's instructions alone cover the picker, and the README
says so. If the input's shape differs, the question's text is redefined from
what the input holds.

### What task 0.12 measured

**An Igor worker can't run this skill, so the implementation builds
everything except Igor-worker mode.** Task 0.12 measured it on
2026-10-20, against igor's main branch and the branches of igor PRs #174
(pinned skills), #175 (a worker as its own Unix user) and #216 (the igor
change this one aligns with, *Alignment with igor PR #216*); the evidence
is the inquisitor decision record's *Rationale: In an Igor's run, filter 1
searches through igor*. One gap is left: under `igor run`, which runs an Igor
on a developer's own machine, the worker's HOME may hold the developer's `gh`
login, which would post as the person. Task 0.14 measures whether a worker
can reach it.

A worker reports to its Igor through its output or an outbox; igor PR #175
chooses which channel each kind of report, such as its citations, takes.
Once igor lets a worker run the skill's script (igor issue #247),
the script's rules for an Igor's run apply (inquisitor spec: *The script
tells an Igor's run by IGOR_RUN*; *In an Igor's run, filter 1 searches
through igor*).

## Questions in posts

prose's posting hook reads a `gh` post's body from an allow-list of command
forms, and the body fields of GitHub MCP tools (`body_fields` in
`.agents/skills/prose/scripts/prose.py`). The library `.agents/lib/gh-shell/`
(shared-skills PR #55) already holds a command splitter and gh's flag tables,
which spec-check's hand-back hook also reads. This change moves the rest of
prose's reader, the part that finds a post's body, into that library for both
post hooks; the `gh-post` spec states its rules. prose's tests change only
where the reader does, and each change has its entry under *The shared post
reader*.

**The order with prose:** prose's pass, then vet the rewritten body, then
sign with prose (scenario *Signing after vetting keeps the post vetted*).
An edit to a vetted question means vetting it again. A hook finds a
question's verdict by the question's hash, which leaves out some lines, such
as the tag and concerns lines (inquisitor spec: *A question's text and hash
are built one way*). Those lines need no vetting, but go in before prose
signs, since any edit after signing means signing again.

A rhetorical question in a post is vetted like any other (inquisitor spec:
*Filters 3 and 4 have the agent decide the question itself*; *A rhetorical
question outside a post is rewritten with nothing recorded*).

## Where the logs live

**Rule:** inquisitor spec, *A question is pushed to the questions branch of
what it concerns*; *A question is written at the privacy of what it
concerns*; *Every answer is recorded and every asked question logged*; *No
record goes somewhere more visible than its source*.

The inquisitor decision record's *Rationale: A question is pushed to the
questions branch of what it concerns* gives why no review is needed and why
the files are not committed with the work.

- **About one repository, a lore repository included:** repository
  questions need no lore repository and no igor.
- **About a collective:** keeping the files off the lore repository's
  default branch leaves that branch holding only the reviewed lore entries
  Igor gives agents. The files hold no `conditions`, the key that marks a
  lore entry, so neither the search nor Igor reads one as an entry.
  Promotion to lore: inquisitor spec, *An answer that generalizes is
  proposed as lore*.
- **About one person's way of working:** no log (*A way-of-working question
  gets no log*).
- **In one of the three categories:** inquisitor spec, *Some questions are
  recorded by hash only*. In an Igor's run, igor keeps the category's
  name, never the text, in an operator-only file on its host, and moves the session
  logs that hold the text next to that file (igor PR #216's decisions 88, 89,
  97 and 98).

A file is taken at its word for who it names (*A file is trusted for who it
names*).

A worker, and an inquisitor run the Igor starts itself, push nothing
(inquisitor spec: *No worker or Igor-started run pushes to a questions
branch*; *An Igor's run reports the questions-branch files it would push*).
The Igor refuses a reported file holding an answer, so a worker steered by
untrusted text in its item can't write a person's answer. A file that cannot
be pushed: inquisitor spec, *A file the script cannot push stays pending*;
*The answer session's files are never kept pending*.

The spec's *A log file and a miss file have one format* holds the files'
path, name, keys and encoding; *Any other answer is input, kept only in its
log file* and *A lore entry that stops a question gets a citation file* say
where an `input` answer and a citation go. The credential scan is only a
backstop (*The secret scan is only a backstop*).

**Ruled out by a scenario** (inquisitor spec: *A question is pushed to the
questions branch of what it concerns*, scenario *A question about a
repository goes to its questions branch*):

- **A personal log under `~/.config/shared-skills/inquisitor/`:** it keeps a
  question's private context where only one person finds it, when the
  question should instead be written without that context or not asked.
- **The git directory:** never pushed, so an agent on another machine would
  ask again.
- **A directory of question files committed with the work,** for the reasons in that
  *Rationale* entry.

## Configuration

The inquisitor spec's Purpose and the answer-session spec's *The answer
session's configuration is a section of the inquisitor's configuration*
define the keys of `~/.config/shared-skills/inquisitor.json`:

```json
{
  "login": "adamstallard",
  "lore": [
    {"path": "/Users/me/src/team-lore", "owners": ["adamstallard"]},
    {"path": "/Users/me/src/api-lore", "repos": ["adamstallard/api"]}
  ],
  "answer_session": {
    "github": {"relay": "adam-relay", "subscriptions": ["octo/api"]},
    "linear": {"relay": "adam-relay", "subscriptions": ["ENG"]},
    "discord": {"relay": "adam-relay", "user": "123456789012345678",
                "subscriptions": ["987654321098765432"]}
  }
}
```

The search reads lore from the clone's remote-tracking default branch, such
as `origin/main` (inquisitor spec: *A lore entry is read from the
remote-tracking default branch*), never the working tree or a local branch,
which could be on another branch or hold an unreviewed edit. The date that
filter 1 gives for each clone (inquisitor spec: *Filter 1 names what it did not
search and how fresh each clone is*) is read from the branch's reflog, so
the date and the content come from one ref. Neither the skill's own fetch,
which brings only the `questions` branch, nor `FETCH_HEAD`, which that fetch
rewrites, gives this date. So the date is when the clone last received a
change to that branch: not when the branch last moved on GitHub, and not a
later fetch that brought nothing new.

Reviewers are listed in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line, decided there in review,
so every teammate's agent tags the same person.

Visibility, of a lore repository or of the repository a question concerns,
is read with `gh repo view --json visibility` on the clone's `origin`, which
gives `PRIVATE`, `INTERNAL` or `PUBLIC`. Write access
is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Whether that call works for a caller without
push access is unmeasured (task 0.4). Each check fails closed (inquisitor
spec: *An unreadable visibility counts against sharing*; *A permission that
cannot be read is no write access*).

The configured `login` is checked by running `gh api user` as the person
(inquisitor spec: *A configured login counts only when gh is logged in as
it*), so nobody can claim a maintainer's login by typing it into their own
file.

## The answer session

The answer session gives a person one place to answer the questions asked of
them on GitHub, Linear and Discord. A relay identity, the person's own bot on
each surface, posts each answer in the question's thread, and an answer file
on a questions branch records it. The session's interface is a Claude Code
mod built from the
approved prototype build v0.1-33 (*The UI is built from prototype build
v0.1-33*). A UI approved by use is not specified, so nothing here describes
how it looks; the spec governs what the UI does and posts, and wins where
v0.1-33 differs (*How the approved prototype meets the spec*). The rules are
in the `answer-session` spec, and the decisions
in the sections from *Answer-session configuration, setup and relay
identities* to *Linking log files to threads, and handbacks*.

### What the answer session posts, and what it logs

Only the answer session starts a post with a reserved prefix (answer-session
spec: *Relay posts start with a reserved prefix*); *The post
hook blocks a reserved prefix on GitHub* gives why, and what enforces it.

**Rule:** answer-session spec, *A relay post is posted by a host command,
unvetted* (task 0.18); *The Linear relay's token stays in memory*; *A GitHub
or Linear relay post names its question in a Re line*. The command runs with
no shell because the person's answer and drafts built from a thread's
untrusted text reach it.

A relay post counts for nothing in filter 1 (*An answer given through the
answer session counts by its answer file*).
The thread's state is still read from relay posts, so a post with a reserved
prefix that the answer session did not make would mislead the answer
session about that thread. Any agent on the person's machine can make such
a post: on Linear or Discord through the relay's own skill, which nothing
checks (answer-session spec: *A reserved prefix outside the answer session
is checked only on GitHub*), and on GitHub or Linear with a printed relay
token. The person is accountable for every such post (*The person answers
for what their relay posts*). The answer-session decision record accepts
the printed-token path in *Constraint: While github-app or linear-app hands a relay
identity's token to a command that can print it, any agent on the person's
machine can print that token and post `User says: ` with a plain HTTP call
no post hook sees*.

### What the answer session does by itself

The answer session runs all four filters on every incoming question, so the
person sees only what needs them. Posting without the person raises two
risks, and the spec answers each:

- **A thread's text reaches the model that judges it.** So the model writes
  no word of an automatic post, and a crafted question can at worst choose
  which fixed reply or which record is posted. The asking agent acts on a
  filter 3 or 4 reply only when a miss file backs it (the inquisitor decision
  record's *Rationale: An Inquisitor reply is acted on only with its
  miss file*). The asking agent already ran both filters itself, so a backed
  reply is a second judgment, by the person's answer session, that one
  option has merit or that the choice is cheap to reverse (*What an asking
  agent does with an automatic reply*).
- **A record can be more private than the thread:** answer-session spec, *A
  recorded answer is posted by itself only when no more private than its
  thread*.

## Tracing scenarios to tests

Every scenario but the expected gaps below gets a tagged test. Where a
scenario is about the script or a hook, the test runs it. Where it is about
what the agent does (asking through the picker, batching, handing a question
back, choosing a lesson's scope), the test checks that SKILL.md states the
rule, and its name says so.

**Expected gaps.** A scenario that only igor's unbuilt work, such as `igor
lore-search`, can make pass gets no tagged test until igor builds it. A
scenario whose rule waits on a measuring task, such as task 0.21 or 0.31,
gets none until that task is measured and the rule built. A
skipped test would not do, since spec-trace counts a skipped test's tag as
coverage. Task 4.2, which writes the tests, lists each expected gap here by
name, and task 4.3 tags it once igor provides what it needs. The change is
archived only after every gap is tagged (*The change is archived only after
every expected gap is tagged*). A gap cannot be exempted through
spec-trace's baseline, `openspec/spec-trace-baseline.txt`, which takes no new
lines after adoption.

## Decisions

Each entry states the decision and its reasons, and labels each alternative
not taken or cost taken on:

- ***Ruled out by a scenario:*** an alternative a test can check. The spec
  holds the rule as a requirement, with a scenario the alternative would
  fail; the entry gives only the reason, and names that requirement and
  scenario. A reason with evidence goes in the decision record as that
  requirement's *Rationale* entry.
- ***Recorded:*** an entry in a capability's decision record,
  `openspec/specs/<capability>/decisions.md`, which this pull request edits
  directly: an alternative no test can check under *Rejected*; a cost taken
  on, or a constraint no test can check, under *Constraints*; a requirement's
  evidenced reason under *Rationale*. The label names the record and entry.

Terms used throughout, as the specs define them:

- **igor** is a separate project of AI teammates (adamstallard/igor). **An
  Igor** is one of those teammates, and its **worker** is the agent it
  starts to do an item. An Igor **injects** lore: it puts `active` lore
  entries into its workers' context unasked.
- **Lore** is a team's lessons for agents, kept as entries in a **lore
  repository** (*Lore repositories are configured as local clones*). A
  repository's **questions branch**, its orphan branch `questions`, holds
  the question and miss files about it (*Where the logs live*).
- **The picker** is Claude Code's question tool, `AskUserQuestion`, which
  shows a person a question with options to choose from.
- **The first call** and **the second call** are the two runs of the
  skill's script for a set of questions. The first runs filter 1's search;
  the second records a **verdict** for each question: `answered`,
  `deferred` (filter 2 put it off), `decided` (filter 3 or 4 chose), or
  `ask` (a person must answer it). The skill's two hooks, **the picker
  hook** and **the post hook** (for GitHub posts), let a question through
  only on a fresh verdict (*Two calls prove the filters ran*).
- **A category** marks a sensitive question: `vulnerability`, `secret` or
  `personal`. The skill's records keep such a question by hash only
  (*Three categories are recorded by hash only*).
- **A miss** is a question that a person said, or an answer session
  clearly judged, need not have been asked. A **miss file** records it.
- **The answer session** is where a person answers questions put to them
  on GitHub, Linear and Discord. A **relay identity**, a bot, posts each
  answer for them, starting `User says: `. On GitHub it is a GitHub App.
- **Gate one** is the repository's owner's approval of this change's spec,
  in a pull request holding only the spec. **Gate two** is the
  implementation, built on the same branch after that approval.

### Asking a person

#### The Igor inquisitor role is out of scope

**The Igor inquisitor role, an Igor that brings surviving questions to a team
discussion, is out of scope; igor #211 tracks and governs it.** The role would
take over the questions behind items an Igor hands back, ask a blocked Igor's
question for it, keep a budget of posts per channel, and route an Igor's
handback comment. Under igor #211's decision 9, in a team without the role
nothing posts that comment to a discussion, batches it or tags anyone, and
nothing in this change does either. The filters a blocked Igor runs on its
own question are this skill's.

#### A deferred question stays visible

**Rule:** inquisitor spec, *Every question passes four filters before a
person sees it*; *Two calls prove the filters ran*. A person who wants the
answer now says so. The `deferred` verdict names where the question will be
listed, not a link, because that post may not exist yet.

#### A question that blocks no step waits for the round's end

**Rule:** inquisitor spec, *A round's questions are asked together at its
end*; *A question that blocks no step is asked at the round's end, saying
what the agent assumed*; *A question round ends at a hand-back or at the end
of the agent's turn*.

**Why:** each question asked mid-round interrupts the person, while at a
hand-back they turn to the work anyway, so the round's questions cost one
read. Because the question names the assumption, the rework an answer causes
is bounded by one round.

**Why, with a person in the session, every end of the agent's turn ends a
round:** ending the turn hands the person control, so held questions would
sit unseen while they are there; without a pull request there is no
hand-back at all.

**The hand-back is spec-check's,** so one word means one moment across the
skills. The inquisitor spec gives one example of a hand-back and cites
spec-check's rule for the full list, so the list is kept in one place. The
round also ends at each end of the agent's turn, which spec-check's review
round, ended only by a hand-back, does not, so it has its own name: a
question round.

**Unlike a deferred question,** which the current work does not need
answered and so is listed as not done and never asked, a question waiting for
the round's end is one the work needs: the work goes on, on an assumption the
answer may overturn. The agent vets it again at the round's end, since a
verdict the script records lasts 2 hours and an answer may have been recorded since.

*Ruled out by a scenario:* asking each surviving question as it arises
(scenario *A blocking question is asked at once, and the others wait*); and
ending a round at each push, since a push hands the person nothing to read,
so its questions would interrupt them as mid-round ones do (scenario *A push
ends no round*).

#### A question another skill requires goes through filters 1 and 3 only

**Rule:** inquisitor spec, *A question another skill requires skips filters
2 and 4*. It keeps filters 1 and 3 so that the inquisitor still screens the
questions other skills generate, which is what it is for. Such questions
include bug-hunter's Step 0 stop, where bug-hunter asks which of a file's
diverging staged and unstaged edits to keep. For a prose finding, filter 3's
one option of merit is usually fixing the passage, which is what prose
wants.

**Why filters 2 and 4 stay skipped:** a deferral cannot unblock a step the
requiring skill holds, such as prose's signing or bug-hunter's Step 0 stop.
A cheap reversal does not override a choice the skill reserves for a person,
such as adopting spec-trace. Filter 3 never settles a real choice, since it
acts only when one option alone has merit. Filter 4 acts when two options
have merit; under the same limit it could take only the one the skill lets
the agent take, so it would always fix a prose finding that keeping had
merit for too.

*Ruled out by a scenario:* exempting such a question from filter 3 too
(scenario *A prose finding with only a fix of merit is fixed, not asked*);
and filter 3 taking an option the skill reserves (scenario *Filter 3 takes no
option the requiring skill reserves for a person*).

#### bug-hunter's Step 9 recommendations go through the filters

**Rule:** inquisitor spec, *A question another skill requires skips filters
2 and 4*. bug-hunter's Step 9 asks the person about its recommendations one
at a time. Running them through all four filters means fewer reach a
person; exempting them would invite each skill to claim an exemption of its
own. Task 5.7 changes
bug-hunter's SKILL.md so that Step 9 runs each recommendation through the
filters before asking. The task's table of starting rules is input to its
design, not decided behaviour: its implementer sets the final rules, which
are reviewed with the implementation. The spec fixes only that each
recommendation passes the four filters. Nothing in bug-hunter changes before
the inquisitor skill exists.

#### A prepared question can be answered "yes"

**Rule:** inquisitor spec, *A question that is asked is prepared for a quick
answer*. The recommended answer comes first so that most questions can be
answered "yes". The picker hook need not check the order: reordering options
after vetting changes the question's text, which the hook blocks as
unvetted.

#### With a person present, ask through the picker

**Rule:** inquisitor spec, *Where the host has a picker, an agent asks
through it, never in its reply*; *A question with a category is asked only
of the person or in its advisory*. On a host with no picker, the reply may
carry a question with a category since it, like the picker, reaches only the
person.

**Why:** the picker hook then sees every question, and the starting agent,
which is talking to the person, can batch a subagent's questions with its
own.

*Ruled out by a scenario:* a hook at the end of the agent's turn that reads
questions in its reply: the person has already read the reply when it runs
(scenario *A question goes through the picker*).

#### What counts as a question in a post

**Rule:** inquisitor spec, *A question in a post is a listed item or a
sentence ending in a question mark*. Its section labels are those under
which agents list open questions. *Questions in posts* gives the order with
prose's pass and signature. The rule lives in one function, so it is cheap
to change if it misjudges posts.

*Ruled out by a scenario:* letting any colon line starting "Open" begin a
section, which would turn the commands under "Open a terminal and run:" into
questions (scenario *A colon line that names no questions begins nothing*).

#### The post hook passes a deferred question only untagged and listed

**Rule:** inquisitor spec, *Questions in posts pass the same filters*. The
post hook passes a deferred question only as an item under a deferral
label, in any post. A new issue gets no exception: the answer session
leaves only such items out when it shows a post's questions, so a
deferred question in a new issue's running text would be shown to the
issue's assignee as put to them. The question must be untagged because
tagging someone asks them, which needs an `ask`.

#### One person who can decide is tagged

**Rule:** inquisitor spec, *A question in a post tags one person who can
decide, if there is one*; *A tag line names the person a posted question
tags*. Only a person with write access can decide. The tag goes on a line of
its own because the script finds whom to tag only at the second call: a tag
inside the vetted text would change that text's hash and make the post hook
block the post until both calls ran again.

#### The configured login names the person

**Rule:** inquisitor spec, *A configured login counts only when gh is logged
in as it* (reason under *Configuration*).

*Ruled out by a scenario:* taking the login from `gh api user` run as the
identity the post goes out as: as a GitHub App it gives no user, and as the
person it gives their own login, so the post would tag the account posting
it (scenario *An agent posting as a GitHub App keeps the configured login*).

#### When no candidate can decide

**Rule:** inquisitor spec, *A question no candidate can decide turns to the
session's login*. The login is tagged only on a post going out as someone
else, since tagging the account a post goes out as would ask the person
their own question. On a post going out as the configured login, the
picker asks instead, or, with no person in the session, the post tags no one.

### Hooks and verdict records

*Proving the filters ran* gives the reasoning for these hooks and records,
and the alternatives not taken; *What the hook relies on, not yet measured*
says what happens if a `PreToolUse` hook cannot block the picker.

#### The hooks are on once the skill is installed

**Rule:** inquisitor spec, *The hooks are on once the skill is installed,
and spend no record*. Installing is the opt-in, as it is for prose's blocking hooks.

#### Files passed to the two calls stay private

**Rule:** inquisitor spec, *The two calls' files and records stay private*;
*Some questions are recorded by hash only*.
Outside any repository, the files can't be committed.

*Ruled out by a scenario:* putting the files straight in the system's
temporary directory, such as `/tmp` (inquisitor spec: *The two calls' files and records stay private*, scenario
*A questions file others can read is refused*; the inquisitor decision
record's Rationale entry for that requirement gives why).

#### Verdict records live in the user's state folder

**Rule:** inquisitor spec, *The two calls' files and records stay private*.
The records sit beside prose's session marks. They hold no question's text (inquisitor spec: *The second call
records all its verdicts or none*), so they are the hooks' state, not a
personal question log.

#### An `ask` record drops the option's label

**Rule:** inquisitor spec, *The two calls' files and records stay private*.
The labels are part of the question's text, which no record holds. Nothing
else records which option the person chose, so the records cannot show
later whether they took the recommendation: a cost the rule accepts.

#### Verdict records are shared under one HOME

**Rule:** inquisitor spec, *A hook blocks a picker question that was not
vetted*, scenario *A verdict recorded in another repository counts*.
The hooks check only that the filters ran on that text, not where. The cost
accepted: a verdict reached in one repository lets the question through in
another, whose decisions the first repository's filter 1 search did not
cover.

#### Every verdict record expires after 2 hours

**Rule:** inquisitor spec, *The two calls' files and records stay private*.
No hook accepts a record that old, so deleting it only when a call or hook
next reads the records removes nothing a hook would accept. On an idle
machine, where nothing reads the records, an expired record can stay on disk
for days. A post edited more than 2 hours after
an `ask`, or listing a question deferred more than 2 hours earlier, is vetted
again, which costs one pair of calls.

**Why:** a lasting record of a categorized question would be either personal
or public: on the person's machine, a personal question log, which the skill
rules out; with the questions, a public sign that such a question was asked,
and when. An uncategorized `deferred` record could have lasted until the
question is listed, sparing a second vetting, but the agent may leave a
sensitive question uncategorized, and its plain hash could be guessed for as
long as the record lasts.

#### A hook spends no verdict record

**Rule:** inquisitor spec, *The hooks are on once the skill is installed,
and spend no record*. When one question blocks a call, the agent vets that question alone and calls again,
and the call's other questions need no vetting again.

#### The related-decision line is left out of the hash

**Rule:** inquisitor spec, *A question's text and hash are built one way*;
*Two calls prove the filters ran*; *A
related-decision line is one URL on a line of its own*.
The related decision turns up in the first call's search, so the agent adds
the line after the second call with no further vetting. Since no vetting
sees the line, the hooks check it for credential patterns.

#### What each hook does when it can't read

**Rule:** inquisitor spec, *A hook blocks a picker question that was not
vetted*; *Questions in posts pass the same filters*; *The post hook vets
what the shared post reader returns*. The reason is under *Proving the
filters ran*.

#### The host's transcripts are outside the skill's records

**Rule:** inquisitor spec, *Some questions are recorded by hash only*,
scenario *The three categories and their records*. The 2-hour expiry, too,
covers only the skill's own records: the host's transcripts are outside its
control.

### The shared post reader

#### Questions in posts pass the filters, on GitHub only

**The post hook enforces the filters for GitHub posts only, sent through `gh`
or a GitHub MCP tool, as prose's posting hook covers GitHub only.** A question
in a Linear or Discord message is covered by the skill's instructions alone.

#### One post reader, shared by both hooks

**Rule:** gh-post spec, *The shared post reader reads a post's body from an
allow-list*. Every rule the reader gains therefore applies to prose's hook
too. spec-check's hand-back hook uses the same library's splitter and flag
tables (shared-skills PR #55), but none of the post reader's rules. The
reader is an allow-list because a general command parser reads some commands
differently from bash, and each difference can let a post through unread; on
a line that mentions a gh post verb, an allow-list blocks every form outside
it, so a difference fails closed. A
second copy of the reader would add a second set of differences.

*Ruled out by a scenario:* calling prose's copy from the inquisitor, which
fails whenever prose is not installed (gh-post spec: *The shared post reader
reads a post's body from an allow-list*, scenario *Both post hooks read a post
through the shared reader*).

#### Which commands the reader judges, and which are unreadable

**Rule:** gh-post spec, *A command that mentions no gh post verb sends no
post*; *A command that only runs prose's script sends no post*; *A line
whose simple commands send no text is no post*; *Input to a no-post line
reaches only data commands*; *Any other line that mentions a gh post verb
is unreadable*; *The reader reads a gh pr or gh issue post only as a whole
command line*; *A gh pr or gh issue body comes from a plain option value or
an existing file*. A `gh pr` or `gh issue` command can take its body from a
file, which an earlier command in the line could rewrite, so it is read only
as the whole command line.

**Why:** prose's reader on main already keeps these rules. The reader adds
two for both hooks, each below: it reads posts sent through the github-app
script, which prose's hook blocks today, and it reads `gh api` writes,
which prose's hook ignores today, counting a call only when it can write.
A line that mentions no gh post verb passes unread: the gh-post decision
record's *Rationale: A command that mentions no gh post verb sends no post*
gives the hooks' scope and its evidence.

*Ruled out by a scenario:* letting a command through when `gh` appears only
inside quotes (gh-post spec: *Any other line that mentions a gh post verb is
unreadable*, scenario *A gh post run through another shell is unreadable*).

#### Posts sent through the github-app skill's script

**Rule:** gh-post spec, *The reader reads posts sent through the github-app
skill and gh api*. Task 5.5 makes each example in the github-app skill's
`SKILL.md` set `G` in the same command or write the script's path.

**Why:** prose's rules read a post only from a simple command whose command
is `gh`. To them, the script's call is `gh` in another command's text, which is
unreadable, so every post sent as a GitHub App would be refused. Only a path
ending in `/github_app.py` is read, since the reader cannot know what any other
script posts. A line running `python3 $G` with `G` unassigned is blocked, since the
reader cannot tell which script it runs; that costs only a rewrite.

*Ruled out by a scenario:* blocking every `gh api` call through the script
(gh-post spec: *The reader reads posts sent through the github-app skill and
gh api*, scenario *A gh api call through the github-app script is judged as a
direct one*), and blocking the script after any other command (scenario *A gh
api body given in the command is read in a longer line*, which holds for the
script in place of `gh`).

#### The reader reads gh api writes, REST and GraphQL

**Rule:** gh-post spec, *The reader reads a gh api write to an issue or pull
request*; *A gh api write read from a file is read only as a whole command
line*; *The reader reads GraphQL posts and blocks an unreadable body sent
to issues or pull requests*.

**Why:** without these rules, a `gh api` comment would skip both hooks.
Reads and writes that send no text, such as label edits, still pass. A
GraphQL mutation is a write like a REST one. A write to an endpoint other
than an issue's or pull request's, or a mutation off the reader's list,
such as release notes or a discussion comment, passes unread, as `gh
release` and `gh discussion` do. The hooks guard issue, pull request and
comment posts, so text sent elsewhere passes unread whichever gh command
sends it.

Both hooks read a file, given by `@<file>` or `--input`, before the line
runs. An earlier command on the line, such as `printf 'unsigned' > c.md`,
could then replace a signed body with one the hooks never saw, as it could
a `--body-file`; for GraphQL it could also swap the query for another
mutation. So such a write is read only as the whole command line. A field
given in the command cannot be rewritten.

*Ruled out by a scenario:* reporting every GraphQL mutation as unreadable,
which blocks writes that send no text (gh-post spec: *The reader reads
GraphQL posts and blocks an unreadable body sent to issues or pull
requests*, scenario *A write with no body sends no post*).

#### A gh api call counts only when it can write

**Rule:** gh-post spec, *A gh api call is a read only as a plain gh command*;
*A gh api call writes by its method, fields, input or a mutation*.

**Why:** a read posts nothing, so counting it would block, for every prose
user, lines such as `gh api … | python3 -c …`. The
gh-post decision record's *Rationale: A gh api call writes by its method,
fields, input or a mutation* gives why the rule follows gh's own choice of
method. `--input` counts as a parameter
whatever gh does with it, failing closed; task 1.3 checks gh's behaviour. A
word the shell builds, `xargs` or `sh -c` could add a field the reader never
sees, and a built method or endpoint might be anything, so the reader
counts only literal words (gh-post spec: *A literal word is one the shell
does not expand*).

*Ruled out by a scenario:* counting every `gh api` call as a possible post
(gh-post spec: *A command that mentions no gh post verb sends no post*,
scenario *A gh api read piped into a script is no post*).

#### A hook payload that is not JSON passes the post hook

**Rule:** inquisitor spec, *The post hook vets what the shared post reader
returns*.

**Why:** the host, not the agent, writes the hook's input, so a payload
that is not JSON means the host is broken, never that an agent crafted a
post. Blocking such payloads would block every Bash and GitHub MCP call
until the host is fixed.

#### The post hook blocks a reserved prefix on GitHub

**Rule:** inquisitor spec, *The post hook vets what the shared post reader
returns*; answer-session spec, *Relay posts start with a reserved
prefix*.

**Why:** anything holding a relay identity could post `User says: `, which
marks a question answered on every machine. So only the answer session may
start a post with a reserved prefix, and it posts through a host command,
which no tool hook sees (*A relay post is posted by a host command,
unvetted*). In the answer session's own session the model has no tool that
posts (*The session's model has no shell, no writing tool and no web
fetch*).

### Logs and privacy

#### Every asked question is logged with what it concerns

**Rule:** inquisitor spec, *Every answer is recorded and every asked question
logged*; *A question is written at the privacy of what it concerns*.
Logged with what it concerns, a question's answer is found by the next agent
instead of being asked again. No question log is kept anywhere personal,
beyond a file pending its push (*Where the logs live*). Only the skill's
instructions keep an agent from asking a question that concerns no
repository, collective or person's way of working; nothing enforces it, and
outside any repository filter 1 then searches only global lore (*Outside
any repository, a question that concerns nothing sees only global lore*).

#### Collective questions go on lore's `questions` branch

**Not on igor's `igor-state` branch,** which holds igor's runtime state
(inquisitor spec: *A question is pushed to the questions branch of what it
concerns*). The lore repository's branch keeps questions not important
enough to become lore, so nobody asks them again; nothing on it is given to
agents as lore, and it has the lore's privacy and access. *Where the logs
live* gives the reasoning and how an answer is promoted.

#### A way-of-working question gets no log

**Rule:** inquisitor spec, *A way-of-working answer goes to the person's
memory, not a log*. Agents already read that memory, and a committed
`CLAUDE.md` would apply one person's way of working to every agent in that
repository.

#### Nothing goes somewhere more visible than its source

**Rule:** inquisitor spec, *Nothing about a repository goes somewhere more
visible*; *An unreadable visibility counts against sharing*; *No record goes
somewhere more visible than its source*, which defines a record's source;
*A question asked in the session shows where its answer will be recorded*;
*The answerer's confirmation can send a record somewhere more visible*;
*A lore pull request goes to no lore repository more
visible than its source*; answer-session spec, *The preview shows where an
answer will be recorded*. *Configuration* gives how visibility is read.

Shown where the record will go, the person answering gives an informed
approval of the wording's privacy, which is why a picker question is pushed
only once it is answered. The approval matters beyond privacy: a confirmed
miss file is what lets the asking agent act on the answer session's
automatic `Inquisitor: ` reply (*What an asking agent does with an
automatic reply*). A confirmed file holds no link into its
source, so it is exactly as visible as its branch, and a miss leaves out
`asked_by`, which would publish the asker's account from the private thread.
Nobody can confirm the record of a question nobody has answered.

#### Three categories are recorded by hash only

**Rule:** inquisitor spec, *Some questions are recorded by hash only*; *A
question with a category is asked only of the person or in its advisory*.
The post hook blocks such a question since a post would keep its text where
the thread's readers see it. Filter 1 searches nothing off the machine for
it, so its text never reaches GitHub's search.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### The secret scan is only a backstop

**Rule:** inquisitor spec, *No credential goes into a log file or a
question*; *The credential patterns are a closed list of token shapes*; *The
credential scan reads raw markdown*. The scan catches known token shapes only: a `DB_PASSWORD=…`
passes it. The patterns include the two kinds of credential this change puts
within the session model's reach: a Linear key and a Discord relay's bot
token.

The post hook scans again just before posting because a token added to a
link target after vetting leaves the reduced text, and so the hash,
unchanged.

#### Weaknesses stay out of public text until disclosure

**Rule:** inquisitor spec, *A weakness is not described in public text
before its advisory is published*; *Before publication, a weakness's test
and description reach only the private fork*.

**Why:**
- The risk is describing the weakness, in any words, so whether the text
  states a question or its answer is the wrong test.
- Before publication, a public fix points straight at the weakness, and
  its regression test is a working exploit. A fix made in the advisory's
  temporary private fork stays private until its commits become public
  with the advisory, as long as the fork's pull request cannot merge
  earlier; task 0.13 measures whether it can.
- The rule ends at publication (the inquisitor decision record's
  *Rationale: A weakness is not described in public text before its
  advisory is published*).
- Until task 0.13 shows that the fork's pull request merges only at
  publication, the person who will publish the advisory can vouch that it
  will, letting the agent commit the regression test in the fork and describe
  the weakness in a fork commit's message, which reveals less than the
  test.

*Ruled out by a scenario:* keeping only the vulnerability question and its
answer out of public text, for the first reason above (inquisitor
spec: *A weakness is not described in
public text before its advisory is published*, scenario *A fix after
publication is described normally*).

### Which answers count, and citations

#### Only an answer with authority stops a question

**Rule:** inquisitor spec, *Only an answer with authority stops a question*;
*A hit that is not an answer is shown as labelled, quoted input*. The
entries below give the reasons for its conditions.

#### An answer recorded on a work branch counts for other work once it lands

**Rule:** inquisitor spec, *An answer recorded on a work branch counts for
other work once it lands*.

**Why:** the log file recording the answer is on the questions branch at
once, where every agent finds it, but the decision document it pins sits
on work that may never merge.

#### An agent's own choice is not logged

**Rule:** inquisitor spec, *An agent's own choice goes in the work's
decision document or its report*.

**Why:** a logged choice would stop later agents from judging the question
again when something around it has changed, and the only way to remove it
would be for a person to read a question and answer that no person should
have to read.

#### An answer without authority stays in its log file

**Rule:** inquisitor spec, *Any other answer is input, kept only in its log
file*.

**Why** never in a decision document: on the current work's branch a
decision document counts as an answer, so the agent's own write would turn
input into a decision.

#### No file on a questions branch changes once pushed

**Rule:** inquisitor spec, *A file on a questions branch never changes once
pushed*.

**Why:** a file then says one thing for good, and a reader can tell a file
changed after its push, which counts for nothing, from one as pushed.

#### A file is trusted for who it names

**Rule:** inquisitor spec, *A questions-branch decision counts only
unchanged and by write access*.

*Why a commit's signature is no check of authorship:*
`openspec/specs/inquisitor/decisions.md`, *Rationale: A questions-branch
decision counts only unchanged and by write access*.

Three rules limit what a file can say, whoever pushes it: a worker logs no answer,
the Igor refuses a worker's file that claims more than a worker may, and the
`log` command fetches a linked GitHub comment's own text.

#### A questions-branch decision counts by write access to what it names

**Rule:** inquisitor spec, *A logged decision needs write access to what its
question concerns*; *A permission that cannot be read is no write access*;
for the `repository` and `asked_from` keys, *A log file and a miss file have
one format*.

*Ruled out by a scenario* (inquisitor spec: *A logged decision needs write
access to what its question concerns*, scenario *A file about a repository other than the one it was asked from needs write access to it*): checking the
lore repository's writers for every file, which lets a lore writer decide for
a repository they cannot change; and a design in which `repository` names
where a collective's question was asked, so that equal `repository` and
`asked_from` mark a collective's question: that design would judge a file
about the Igor's own item's repository by the lore repository's writers.

#### A logged answer is the person's own words

**Rule:** inquisitor spec, *A person's answer is recorded in their words or
not at all*; *The log command records a linked GitHub comment's own text*;
*A log file is read by its frontmatter and its body's end*. igor PR #216
records the writer side of this rule as its decisions 67 and 70.

#### A log file's answer is written as quote lines

**Why:** every answer line starts with `>`, so a whole comment fits, even one
holding a `## Answer` line of its own.

*Ruled out by a scenario* (inquisitor spec: *A log file and a miss file have
one format*, scenario *A whole comment fits as the answer*): joining the
comment onto one line, which changes a comment holding list items; and a frontmatter key counting the answer's lines, which the quote
marks make needless.

#### The `log` command reads its inputs and the linked comments itself

**Rule:** inquisitor spec, *The log command records a linked GitHub
comment's own text*; *The log command refuses a question holding a closing
section's heading*.

The inquisitor decision record's *Rationale: The log command takes its input
in a private file* gives why inputs go in a 0600 file, never arguments.

**Why** it refuses a question holding a line `## Rephrased question`,
`## Discussion` or `## Answer`: a reader takes those lines from a log file's
end, so an untrusted question ending in forged rephrasing lines would read
back as a shorter question, and a writer's answer would be recorded against
a different text and hash.

*Ruled out by a scenario:* escaping those lines: a reworded question reads the
same to a person, and an escape is one more form every reader must undo
(inquisitor spec: *The log command refuses a question holding a closing
section's heading*, scenario *A question holding a closing section's heading
is refused*).

#### An answer typed on another surface counts only through a decision document

**Rule:** inquisitor spec, *Any other answer is input, kept only in its log
file*, until a decision document that *Only an answer with authority stops
a question* counts records it.

A linked answer is only a github.com comment or review, since only there does the `log` command fetch the comment's own text, so an answer typed
directly on Linear or Discord can't be one. An answer typed in the answer
session and relayed to Linear or Discord counts through its answer file (*An
answer given through the answer session counts by its answer file*).

#### Citations go to the lore repository's questions branch

**Rule:** inquisitor spec, *A lore entry that stops a question gets a
citation file*; *A citation file has one format*. The inquisitor decision
record's *Rationale: A lore entry that stops a question gets a citation
file* gives why it exists and why none goes to a more visible lore
repository. A question with a category gets none, since the cited entry
would show what it was about. igor PR #216 points to this change's citation
format, since the inquisitor and an Igor both write citation files and
igor's review reads them all. The run's id in a citation is opaque; the Igor
records it in the run's row of its execution ledger on its `igor-state`
branch, not with the transcript, and igor's review shows each citation's run
and item (igor PR #216's decision 10).

*Ruled out by a scenario:* a `cites` field in the log file, which a stopped
question lacks (inquisitor spec: *A lore entry that stops a question gets a
citation file*, scenario *Only the citation file names the lore entry*);
counting raw search hits, which records no reason (scenario *A lore entry the
search shows but that stops nothing gets no citation*); and a hash of the
question in the citation, which the count does not need (inquisitor spec: *A
citation file has one format*, scenario *A citation from a session outside an
Igor's run holds no run id*, which gives its only keys, `entry` and `date`).

#### Questions-branch commits are machine records

**Rule:** inquisitor spec, *A question is pushed to the questions branch of
what it concerns*, with its reason in the inquisitor decision record's
*Rationale* entry of that title. igor PR #153 would have an Igor push only
commits carrying prose's and bug-hunter's trailers, which citation commits
lack. Whether #153 exempts them is #153's to settle; igor issue #247 asks
it to.

#### A citation's commit names no person

**Rule:** inquisitor spec, *A citation file has one format*, scenario *A
citation's commit names no person*: its author and date say nothing about
who asked.

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Constraint: GitHub's
events API shows each citation push's pusher and time to anyone who can see
the lore repository*.

### Lore and misses

#### Lore repositories are configured as local clones

The spec's Purpose holds the keys (`lore`, `path`, `owners`, `repos`) and
defines *lore repository* as the one holding the entries, which igor PR #216
calls the *destination repository* (#216's decision 66). igor's specs use
the same words for a different repository: under igor
PR #208 an Igor's configuration lives in one repository, which may name another
holding the entries, and igor calls the first the lore repository. In this
change the term always means the one holding the entries.

*Ruled out by a scenario:* refusing two lore repositories that list the same
owner, which can serve it for different projects (inquisitor spec: *Filter 1
searches every place an answer is recorded*, scenario *Two lore repositories
serving one owner are both searched*).

#### Filter 1 searches lore in every session

**Why:** the search is how lessons reach plain Claude Code sessions, which no
Igor injects lore into.

#### Lore search is as fresh as the last fetch

**Rule:** inquisitor spec, *A lore entry is read from the remote-tracking
default branch*; *Filter 1 names what it did not search and how fresh each
clone is*. Filter 1 fetches only the `questions` branch, so it does not find
a lore entry merged since the person's last fetch.

#### Scope hides an entry; status only labels it

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Rationale: Filter 1
hides every lore entry outside the question's scope*.

#### Filter 1 searches igor's scribe's records where #202 puts them

**Rule:** inquisitor spec, *A lore decision record counts*; *Filter 1
searches every place an answer is recorded*; *Only an answer with authority
stops a question*. igor's scribe is the Igor role that records a
discussion's decisions. The inquisitor's decision record, *Rationale: A lore
decision record counts*, gives why filter 1 reads both the repository the
question concerns and the lore repository. The spec names no path of its
own, only whichever path #202 sets (*igor-dependent rules state the end
state*); *Open Questions* tracks it.

#### A general answer is proposed as a provisional lore entry

**Rule:** inquisitor spec, *An answer that generalizes is proposed as lore*;
*During an Igor's run, the Igor proposes the run's lore entries*.

**Why** unasked: a pull request is itself a proposal, and closing it is
cheap. **Why** the Igor opens a run's: there the script pushes nothing to a
lore repository, and the Igor already pushes the run's other files.

#### Lessons from misses are drafted on request and land by scope

**Rule:** inquisitor spec, *Lessons from misses land by their scope*. A
lesson for shared-skills must be general because question and miss logs can
hold private content, which stays with the repositories it concerns.

### Igor workers and Igor runs

#### The script tells an Igor's run by `IGOR_RUN`

**Rule:** inquisitor spec, *The script tells an Igor's run by IGOR_RUN*; *An
Igor worker's search covers only its working tree beyond lore*; *The
repository a question concerns defaults to the current work's*. igor PR #216
sets the variable (at 59e7561). A question with a category raises igor's
flag on the whole execution on the item, not one worker's part of it (igor
PR #216's decision 22).

*Recorded:* why the script prints that it runs as in an Igor's run
whenever it acts on the variable, in
`openspec/specs/inquisitor/decisions.md`, *Rationale: The script tells an
Igor's run by IGOR_RUN*.

*Ruled out by a scenario:* treating every session with no person in it as
possibly in an Igor's run (inquisitor spec: *The script tells an Igor's run by
IGOR_RUN*, scenario *A headless session without IGOR_RUN searches lore*).

#### An Igor worker asks only through its Igor

**Rule:** inquisitor spec, *A session with no person in it asks in a post, a
handback or nowhere*; *A worker's question about a more private repository
is asked on that repository's questions branch*; *A later run gets only the
answer to its Igor's question on a more private repository*; answer-session
spec, *The preview says when an answer also reaches a more visible item's
run*. The Igor posts the handback comment (igor #211).

**Why** the worker posts nothing: the inquisitor's decision record,
*Rationale: A session with no person in it asks in a post, a handback or
nowhere*. igor gives a worker no credential that can post, so a `gh` login a
worker can still reach breaks igor's rule; the worker does not use it, and
task 0.14 reports it.

**Why** a later run reads that one file's answer: the worker needs the
answer to go on.

#### Filter 1 in an Igor's run searches through `igor lore-search`

`igor lore-search` is specified by igor PR
[#216](https://github.com/adamstallard/igor/pull/216) (its decisions 23, 49
and 52), whose decisions igor issue
[#215](https://github.com/adamstallard/igor/issues/215) also holds. #216
amends igor's lore-firing spec: lore is injected into the worker's prompt
as before, a worker may now also be offered a search tool, and a run's
search returns only entries whose scope covers the worker's role, as
injection does, marking an in-scope entry that is not `active` as not lore,
so the worker does not take it as decided.

**Why** a worker searches at all: the inquisitor decision record's
*Rationale: In an Igor's run, filter 1 searches through igor*.

**Why** only the lore repository the Igor injects from: the Igor checks a
cited entry, reported by id alone, against that lore repository; another
one's search could find an entry the Igor refuses, or one it takes for a
different entry with that id.

**Why** both searches match alike: the same entries then rank alike inside
and outside a run.

#### The Igor reads questions branches by running the script

**Rule:** inquisitor spec, *The Igor reads questions branches with the
script*; *The script searches a questions branch and prints labelled hits as
JSON*. Passing the JSON over `igor lore-search`'s channel means one channel
carries everything from outside the working tree. The JSON is the contract
between shared-skills and igor, and task 2.3b's test holds it steady. The
inquisitor decision record's *Rationale: The Igor reads questions branches
with the script* gives why the Igor runs the script and the worker does not.

#### Questions-branch files and `project:` entries in a run's search

igor PR #216 sets the scope rules for lore entries (its decisions 44, 53
and 54), and the inquisitor spec only cites them. For a questions-branch
file, the script's `branch-search` applies the inquisitor's own run rules:
a file about another repository is input, and a file the item's
visibility hides is left out (inquisitor spec: *The script searches a
questions branch and prints labelled hits as JSON*). The script applies
them because igor holds no copy of the inquisitor's rules (*The Igor reads
questions branches with the script*).

**Why** a file about another repository is input in a run: *Every
questions-branch file names where it was asked from* gives the reason.

#### Every questions-branch file names where it was asked from

**Rule:** inquisitor spec, *A log file and a miss file have one format*,
scenario *A file an Igor pushes names where it was asked from* (#216's
decision 42); *A log or miss file is as private as its more private
repository*.

**Why** no worker writes it: a worker steered by its item could write a
public `repository` on a file about a private repository; `asked_from`
still names the private one, so the question cannot be laundered. Outside a
run, the writer of `asked_from`, the script or the answer session, already
sets `repository`, so setting `asked_from` too gives it no new way to
mislead.

**Why** a collective's question names where it was asked: it concerns no
repository, but its visibility and its team's lore repository still come from
the work that raised it (spec: *A collective's question is bounded by the repository it was asked from*).

**Why** a run's file may name another repository (inquisitor spec: *The
repository a question concerns defaults to the current work's*; #216's
decision 33): during a run such a file is only input (*Questions-branch
files and `project:` entries in a run's search*), so a steered worker makes
no answer count.

#### The flag a worker raises for a question with a category

**Rule:** inquisitor spec, *A session with no person in it holds back a
question with a category*. The Igor writes the words only into its
operator-only file on its host (#216's decision 89), never into the
execution ledger, the state branch, a comment or a label. The Igor moves the
run's session logs, which hold the question's text, next to that
operator-only file (#216's decisions 88, 89, 97 and 98), and writes no other
copy of the run's text. How the Igor stores the flag is #216's (decisions
92, 97 and 100).

*Ruled out by a scenario:* a word per question, which tells the Igor how many
questions of each category stopped the run; and only the stopped questions'
categories in a fixed order, which leaves out one met but not stopped on
(scenario *The flag lists each category once and marks the stopped
questions'*).

#### A flagged run asks nothing and pushes nothing

**Rule:** inquisitor spec, *A flagged run's handback comment asks no
question*; *No log file records a flagged run's question*. A flagged run
pushes nothing to the `questions` branch, citations included, and its
question stays on the Igor's host. The Igor's handoff, the operator file
that holds the question, and how the item is released are igor PR #216's
(decisions 73, 75, 76, 79 to 85, 88, 89, 95, 97, 98, 100 and 101 at
59e7561); this change reads nothing from that file.

#### The Igor pushes the questions-branch files its worker reports

igor PR #216's requirement *An Igor publishes the questions-branch files its
worker reports* holds these rules for both changes. The Igor pushes only an
unanswered question file or a miss file, each only at a path not already on
the branch (decision 21); every file passes igor PR #217's credential
matcher, which matches known secrets' values such as the seat token
(decision 28); and it reads the lore repository's visibility at every push
(decision 37). #216 pushes only to the team's lore repository's questions
branch; igor issue #247 asks it also to push a file about a repository to
that repository's questions branch. #216 also pushes a worker's file for a
person's answer to a handback as an unanswered question; igor issue #247
asks the Igor to write the answer into it.

#### A person's answer to a handback

**Rule:** inquisitor spec, *An Igor pushes a handback answer only for a
question its record holds*; *A later Igor run names the answered file only
from the Igor's record*. The Igor picks the question a person's comment
answers by the question's hash, built as the inquisitor spec's *A
question's text and hash are built one way* says, in its record of the
handback, never by matching the comment's current text. #216's decision 41
takes the questions from that record, and its decision 59 keeps the
record.

**Why:** a worker steered by its item could otherwise pair a real comment
with another question, and anyone who can edit the comment could change its
text.

#### A worker logs no answer

**Why** a worker writes none: it reads no comment, so any answer it wrote
would be its own paraphrase, and it could not check the writer's access to
set `authority`.

#### A later run names the answered file from the Igor's record

**Rule:** inquisitor spec, *A later Igor run names the answered file only
from the Igor's record*. That record is the hashed record of handback
questions that igor PR #216, still open, is asked to keep in its decision
59; a builder relies on it only once #216 merges with decision 59 in it.

**Why:** anyone who can edit a comment can change its text, so the run never
reads a file's name from the comment. The random suffix makes a name unique,
so a second file matching the record can only be a planted look-alike. The
slug of the question's words in a file's name reveals nothing more, since the
file holds the question's text on a questions branch no more visible than the
question.

*Ruled out by a scenario:* naming the files a search found by their words,
or reading the name from the comment's text (inquisitor spec: *A later Igor
run names the answered file only from the Igor's record*, scenario *A later
run finds the file by the Igor's record*); and dropping the slug (scenario
*Where a file goes and how its slug is made*).

#### igor PR #216 holds every rule for a run's citations

**Rule:** inquisitor spec, *No worker or Igor-started run pushes to a
questions branch*. igor has a worker edit and its Igor publish, and a worker
holds only its seat's token, the one credential igor leaves in its
environment. In brief, the
Igor pushes a run's citations only when the run publishes, a handback comment
counting, as bookkeeping that needs no action from the role's `allow` list
(the closed set of actions, such as `comment` or `pr`, igor's role
configuration grants a role), and only of
existing `active` entries in the role's scope. The channel a worker reports
them through, output or outbox, is igor PR #175's, which runs a worker as a
separate Unix user.

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Rationale: A lore
entry that stops a question gets a citation file*.

#### igor-dependent rules state the end state

The rule this heading names is in no spec: it is the Constraint named on
the *Recorded:* line below. What igor must provide is in igor issue
#247's body. A rule describes no igor behaviour from before the igor
change it needs, but a clause guarding against misuse in igor's end state is written, such
as:
- an answer to a question the handback record does not hold is not pushed;
- an `igor lore-search` call that fails searches no lore;
- a post carrying igor's handback marker, which a real handback, sent
  through no tool, never is, is vetted like any other (the inquisitor
  record's *Rationale: Questions in posts pass the same filters*).

*Recorded:* in the inquisitor and answer-session decision records,
*Constraint: Each rule that depends on igor states what holds once the igor
change it needs lands, …*.

#### Alignment with igor PR #216

**The spec states igor PR #216's rules where they touch this change, and
points to the rest,** such as the Igor's `authority` and `answered_by` for a
handback answer. igor issue #247 lists where this change
departs from #216.

### Answer-session configuration, setup and relay identities

#### Setup is part of the answer session

**Rule:** answer-session spec, *Setup opens on an incomplete
configuration*. How setup looks is not specified: task 6.1 designs it from
the approved prototype's patterns.

#### A failed relay check turns off only its channel

**Rule:** answer-session spec, *Setup checks each relay identity before its
channels are used*.

#### Setup checks direct pushes, and can create a lore repository

**Rule:** answer-session spec, *Setup checks each questions branch takes the
person's direct pushes*; *Setup suggests a rule guarding each questions
branch*; *Setup can create a lore repository*.

*Recorded:* the answer-session decision record's *Rationale: Setup
suggests a rule guarding each questions branch*, and the inquisitor
record's *Constraint: A `questions` branch is guarded against rewriting
and deletion only where an admin of its repository sets the rule setup
suggests*.

The `lore` command copies igor's entry format when it proposes an entry,
and a test pinned to an igor commit checks that copy (task 2.8).

#### Discord is in the first version, through discord-bot

**Discord is in the first version, through the `discord-bot` skill of
shared-skills PR #1, merged,** because the skill's bot can post for the
person without any service running beside the session: its script
makes its API calls on each run and exits.

#### On Discord one identity both reads and relays

**Rule:** answer-session spec, *The answer session reads with the person's
credentials, except on Discord*; the answer-session decision record's
*Rationale* entry of that title gives the reason and its evidence.

*Ruled out by a scenario:* a second Discord identity reading as the person
(scenario *Discord is read by its relay*).

#### The Discord relay needs the Message Content intent

**Rule:** answer-session spec, *Setup checks each relay identity before its
channels are used*; the answer-session decision record's *Rationale* entry
of that title gives why, with the evidence.

#### Only the prefixes are reserved, not the identity

*Ruled out by a scenario:* keeping a relay identity for the answer session
alone (answer-session spec: *Relay posts start with a reserved prefix*,
scenario *A relay identity's post without a prefix is not read*).

#### An answer given through the answer session counts by its answer file

**Rule:** inquisitor spec, *An agent logs a bot's comment only as input*;
answer-session spec, *An answer is recorded by a new log file*; *A
questions-branch answer file records the answer as given*. Because an
answer counts by its answer file, not by who wrote the comment, no committed
file lists a person's bots, and no reader has to learn which App wrote a
comment.

*Ruled out by a scenario:* counting a `User says: ` comment by its author
(inquisitor spec: *An agent logs a bot's comment only as input*,
scenario *A User says comment with no answer file is input*); and counting
every answer relayed off GitHub as input (answer-session spec: *A
questions-branch answer file records the answer as given*, scenario *A log
file of a Discord-relayed answer is a decision*).

### Running the answer session

#### The answer session polls, only while it is open

**Rule:** answer-session spec, *The answer session polls only while it is
open*; *The answer session reads with the person's credentials, except
on Discord*; *Local state is per machine, in the state folder*; *The
answer session's filter 1 reads only subscribed and lore repositories*;
*The poll reads every GitHub question source*.

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Rationale: The
poll reads every GitHub question source* and *Rationale: The answer
session polls only while it is open*, and a *Rationale* entry for each
other requirement the **Rule:** line names, except *Local state is per
machine, in the state folder*, whose reasons follow.

#### Local state is per machine, in the state folder

**The state folder holds working state, not a record: the thread and the
questions branches stay the records.** A discussion record is deleted once
its question is settled (answer-session spec: *Local state is per machine,
in the state folder*), so the state folder is not the personal question
log that *Every asked question is logged with what it concerns* rules out.

#### Which cross-machine cases are accepted

**A case between two machines of the same person whose worst outcome is a
question shown twice or asked again, or a post repeated, is accepted, and
gets no rule of its own.** "Asked again" means an asking agent asks a question again because one
machine has not yet seen what the other recorded, and
"shown twice" means the person sees one question twice; either costs the
person only a second look, and an entry cited twice only adds to igor's
count. A case that could record a wrong answer, close a question wrongly,
leak private content or lose an answer is still raised for a decision.

#### One answer session runs on each machine

**The lock makes one session the sole writer of its machine's state:** one state folder holds the machine's
owed pushes, pending answers and poll positions, and two answer sessions
would poll, post and push twice. The session holding the lock checks it by
its session id, not its name, because every session the `answer` command
starts is named `Answers`.

#### Two commands open the answer session

**Rule:** answer-session spec, *Two commands open an answer session*;
*Setup installs the answer command*. `/answer` opens the answer session in
whichever layout the session is in.

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Constraint: Nothing is designed or built for the answer session outside Claude Code's fullscreen layout*.

#### A discussion runs in the session's own conversation

**Why:** the person opened the conversation to talk the question through, and
the model reads before it replies, while a picker would hide the answer
session's screen. So a question the model asks back is the one exception to
the rule that an agent asks only through the picker.

#### The session's model has no shell, no writing tool and no web fetch

**Rule:** answer-session spec, *The session's model has no shell, no
writing tool and no web fetch*; *A relay post is posted by a host command,
unvetted*; *A discussion runs in the session's own conversation*; *The
person answers for what their relay posts*. The answer-session decision
record's *Rationale* entry of the first title gives the threat, why hooks
cannot stop a model with a shell, and why web fetch is left out.

If task 0.34 finds no control that Claude Code itself enforces, the design
would fall back to hooks, and the change cannot be built as written.

Since the session's code posts each confirmed answer, the person's
confirmation, not a hook, is what lets an answer out. Coding, testing and
committing happen in other Claude Code sessions. The prototype has shown
that a mod can fill the prompt box and register a tool the model calls by
name.

#### Claude drafts a reply only into the prompt box

**Rule:** answer-session spec, *Claude's draft goes to the prompt box,
never to a post*; *A relay post is posted by a host command, unvetted*;
*The preview warns when a filter 1 record is more private than the
thread*. The answer-session decision record's *Rationale* entry of the
first title gives the reason a subagent's call is refused, and the
evidence.

Since the person confirms whatever Claude drafts, a filter 1 decline's
draft may fill in the record's URL. The `agentId` refusal keeps out a
forked side conversation, such as the one that guesses the next prompt,
which could drop an unasked draft in the prompt box, possibly over what
the person is typing.

**Beyond the model writing each draft for the more public of the thread's
and the repository's readers, a draft's privacy is the person's to
judge:** they read each draft before confirming it and decide
whether its wording suits where it posts. The answer session checks a
draft only as it checks every relay post, scanning it for credentials.

#### The model hands its judgements to the code through record_verdict

**Rule:** answer-session spec, *The model's judgements reach the session's
code only through record_verdict*; the answer-session decision record's
Rationale entry of that title gives why.

**The code puts each message to judge into the session's conversation as a
prompt of its own, holding the message as quoted data, while the model is
not answering the person.** The model judges it in two turns, because
filter 1's search, the script's `search` command, needs the question's
category and place. In the first turn the model sets `question`,
`category`, and the place fields that the spec's *record_verdict's fields
are a closed list* gives the question. The code then runs `search` and
puts filter 1's hits before the model as a second prompt, on which it sets
`filter` and `hit`. That scenario also says how the code reads a turn
with several `record_verdict` calls, or none.

**If task 0.37 finds a mod cannot prompt its own model unattended, work on
the mod stops, and the answer session is designed as a standalone UI,
prototyped for the owner's approval.** The approved prototype, build
v0.1-33, shows a mod filling the prompt box and registering a tool, but not
prompting its own model.

#### The UI is built from prototype build v0.1-33

**The mod is built from prototype build v0.1-33 alone, approved by use,**
tagged `answer-session-ui-approved-v0.1-33` on shared-skills (commit fc3c35f;
`ui-approved-v0.1-33` in the repository's owner's prototype repository). It
contains all of v0.1-30, the whole UI approved by use, declining and the list
of questions answered or handled for the person included (tag
`answer-session-ui-approved-v0.1-30`, commit c9c6eb5; `ui-approved-v0.1-30`),
so one base serves. v0.1-33 adds only:

- the thread's replies since the question;
- filter 1's recorded answer beside the question, for a questions-branch
  question as well as a thread's;
- corrected wording and placement of the notice for a post held back because
  a reply arrived in the thread since the person last read it.

The replies and the recorded answer each appear in the one fixed place the
tagged build shows them. The approval covers the whole build, including the
asker withdrawing their question in the thread (the prototype's twelfth
sample question) and the held-back post's notice, which the build's pre-tag
notes list as still to try. The tag `answer-session-ui-approved` (f964903)
lacks the declining screens and is not a base.

#### How the approved prototype meets the spec

Task 6.1's rules, which apply *The answer session*'s rule that the spec wins:

- (a) The mod keeps the approved screens' layout and interaction: the band,
  which is the mod's panel above the prompt box, the keys, the prompt-box flow
  and the declining screens. It may change them to wire real data, not
  restyle or reorganise them.
- (b) Wherever the prototype disagrees with the spec, the spec wins; task 6.1
  lists the known cases.
- (c) A screen the spec needs and the base build lacks is designed at
  implementation from the prototype's existing patterns, in no new visual
  style; task 6.1 lists these screens, which ship with no prototype approved
  by use.
- (d) The screens v0.1-33 added to v0.1-30 are taken as that build has them.

#### Some answer-session details are decided at implementation

**These are decided at implementation. When each choice is made, it becomes
a requirement with a scenario if a test can check it, and otherwise a
decision-record entry with evidence; this section links to it, and task 6.11
lists them:**

- how a question's options are parsed from its thread;
- an asker's reply revising the options.

### Relaying answers

#### The thread is the durable record of an answer

**Rule:** answer-session spec, *The thread is the durable record of an
answer*; *The thread is read again before a question is shown and before a
post*; *Relay posts start with a reserved prefix*; *A GitHub or Linear
relay post names its question in a Re line*. Because each machine reads the
thread again before it posts, two of the person's machines answering one
question both post only when each posts before reading the other's post.

**Why:** the thread is the one place every machine, and the asker, can read.
A crash after a post but before its id is saved loses nothing: the next read
of the thread finds the post.

#### `User says: ` answers, `User asks: ` asks the asker

"User" is literal in both prefixes, never the person's name. The prefixes
exist because "waiting for the asker" is read from the thread, which needs a
mark every machine, and every surface, can read there.

#### A relay post gets no prose pass and no vetting

**Why:** a relay post is the person's words. A prose rewrite would post words
the person did not confirm, and the filters guard a person's time against an
agent's questions, not the person's own words.

#### Discord relay posts: no header, mentions that ping

**Rule:** answer-session spec, *An answer is relayed as the person's words*
(the answer-session decision record's *Rationale* entry of that title
covers the header). With mention rewriting on, an `@name` in the answer
pings that member, as in a comment of the person's own.

*Ruled out by a scenario* (answer-session spec: *An answer is relayed as the
person's words*): mention rewriting off, which only stopped a quoted record's
@-mentions notifying again, and no post quotes one (scenario *A Discord relay
post has no header and pings whom the person names*); and failing setup on
`memberSearch: false`, since the warning at each post tells the person
(answer-session spec: *Setup checks each relay identity before its channels
are used*, scenario *Refused member search does not fail setup*).

#### The person can ask the asker

**Asking back is mostly for people's questions:** an Igor's worker asks in its
handback comment and is gone, so a reply reaches whichever worker next takes
the item.

#### Editing a relay post

**Rule:** answer-session spec, *A relay post can be edited where it was
posted*; *An edit to a questions-branch answer pushes a new log file*. An
edited automatic post starts `User says: ` because the person confirmed its
new text. An edit pushes a new log file because a questions-branch file
never changes, and the branch would otherwise keep the first answer; *The
newest answer counts* says which file counts.

#### A rephrased answer carries its rephrasing

**Rule:** answer-session spec, *A questions-branch answer file records the
answer as given*.

*Ruled out by a scenario:* new frontmatter keys for the rephrasing, since
every frontmatter value is one quoted line and a question's text is not
(inquisitor spec: *A log file and a miss file have one format*, scenario *A
rephrased question's log file holds the rephrasing*).

#### A questions-branch question is answered by a new log file

**Rule:** answer-session spec, *An answer is recorded by a new log file*;
inquisitor spec, *A file on a questions branch never changes once pushed*.
An answer to a file whose `asked_in` links a post is both relayed and
pushed so that neither the asker reading the thread nor an agent searching
the branch misses it.

#### An answer file records the question the person saw

**Rule:** answer-session spec, *A questions-branch answer file records the
answer as given*; *The preview shows where an answer will be recorded*.
Recording the log file's own question instead would let a log file whose
`asked_in` points at an unrelated message get the person's answer
recorded, as a decision, against words they never saw.

#### An answer file names every file it answers

The inquisitor spec's *An answer file names every unanswered file it
answers* sets the rule. Naming files gives every machine the same answer,
while answering whichever files hold the same words would give machines
holding different files different answers. igor PR #216 is asked to refuse
a worker's file holding `answers`, so that only the Igor, the agent igor
runs, adds the key, never a worker it starts: igor, as #216 specifies it,
pushes only what the Igor writes. *Open Questions* carries that request.

*Ruled out by a scenario:* keeping hash matching beside `answers`, which
gives machines different answers (inquisitor spec: *A named file's answer is the newest answer file naming it*, scenario *An answer naming one file
does not answer another with the same question*).

#### The newest answer counts

**Rule:** inquisitor spec, *A file is as new as the commit that added it,
and supersedes only if it would count*. If a file that would not count
could supersede, a person without write access, whose answer to a handback
an Igor logs as `input`, would undo a maintainer's answer.

#### `answers` decides a named file's answer; the search groups by hash

**Rule:** inquisitor spec, *A named file's answer is the newest answer file
naming it*; *Among files with the same question, only the newest answer
counts*; *A replaced answer file stops counting even in its own hash
group*.

**Why both:** a later asker has no file of its own to name, so the search can
find earlier answers only by hash. A replaced answer file stops counting in
its hash group too, or the person's changed answer would not be the only
one that counts.

**Why** a replaced file still supersedes the older files in its hash group:
the person's newer answer marks the older ones in that wording stale, so
asking again is safer than reviving one, even when that leaves the group with
no answer that counts.

*Ruled out by a scenario:* the older files in a replaced file's hash group
counting again (inquisitor spec: *A replaced answer file stops counting even
in its own hash group*, scenario *The newest answer naming a file counts*).

#### A named file's answer must be the person's own

**Rule:** inquisitor spec, *A named file's answer is the newest answer file
naming it*; answer-session spec, *The person's answer to a named file is
their own*.

**Why:** the question was put to the person it tags. A file that tags no
one has no such person, so an account with write access to what it
concerns answers it.

*Ruled out by a scenario* (inquisitor spec: *An untagged file's answer
from an account with write access counts*): answering a file that tags no
one only by a matching hash in filter 1's search, never through
`answers`.

#### A named file stays shown until its answer counts

*Ruled out by a scenario* (inquisitor spec: *A log file named only by an
input answer file is unanswered*): letting any answer file, an `input`
one included, stop the file it names being shown as unanswered.

#### `answer_link` and `asked_in` are withheld where they would leak

**Rule:** inquisitor spec, *The log command withholds a link where it would
leak*; *A log or miss file is as private as its more private repository*;
*The answerer's confirmation can send a record somewhere more visible*;
answer-session spec, *The preview warns before a record goes somewhere
more visible*; *A recorded answer is posted by itself only when no
more private than its thread*.

**Why:** the URL would point the readers of a more visible questions branch
into a more private thread. A Discord URL holds the server's and channel's
ids, a Linear URL the workspace and issue key, and a github.com link into
a more private repository leaks the same way. An answer's text can leak
from a private thread too, which is why an answer file goes somewhere more
visible than its thread only with the person's confirmation.

*Ruled out by a scenario:* always writing the URL, accepting the leak
(inquisitor spec: *The log command withholds a link where it would leak*,
scenario *A GitHub link into a more private repository is left out*).

#### An answer that cannot reach its thread is kept pending

**Rule:** answer-session spec, *An answer that cannot reach its thread is
kept pending*; *A pending answer whose channel was off returns to the
queue*; *A pending answer that no check returns waits for the person*; *Only the
person is told an answer is pending*. A failed post keeps its answer
pending rather than leaving the question as it was, which would drop the
answer the person typed.

**Pending answers are kept in a separate pending list that reuses the main
queue's screens,** so the list needs no prototype of its own.

*Ruled out by a scenario:* returning to the queue, when the answer session
next opens, a pending answer that no check returns (answer-session spec: *A pending answer that no
check returns waits for the person*, scenario *A text refused for its length stays
pending after a recheck*); and an "Answered on another machine, not relayed"
notice on other machines, offering to relay, edit or answer afresh, even only
for a file linked by `asked_in` (answer-session spec: *Only the person is told
an answer is pending*, scenario *Another machine asks again while an answer is
pending*).

#### The push order for a questions-branch answer

**Rule:** answer-session spec, *A questions-branch answer's file is pushed
after its post*; *An answer whose thread is unreachable here is logged at
once* and the requirements beside them; inquisitor spec, *The answer
session's files are never kept pending*. The file follows the post so
that no thread is left answered with no file. Recording the owed push
before the post means a crash after the post's URL is saved does not lose
the answer file.
Checking the thread first lets the person see a new message before
anything is pushed.

*Ruled out by a scenario:* each of these:
- pushing every answer file on confirmation, which leaves a file for an
  answer held back or dropped before posting (answer-session spec: *An answer
  whose thread is unreachable here is logged at once*, scenario *An answer
  held back by a new message pushes no file*);
- pushing the file of an answer whose thread cannot be read only once it is
  relayed (same requirement, scenario *An answer to a questions-branch
  question is logged at once*);
- pushing no file when a refused post turned the channel off, though a file
  is pushed when the channel was already off (same scenario);
- a dropped pending answer pushing a handled file (answer-session spec: *A
  handled file closes a questions-branch question*, scenario *Dropping a
  pending answer pushes no handled file*);
- the `log` command keeping a pending copy of a file the answer session
  pushes, beside the session's own retry (inquisitor spec: *The answer
  session's files are never kept pending*, scenario *A file the answer
  session cannot push leaves no pending copy*).

Were the `log` command to keep a pending copy too, a passing failure would
give two answer files: the session's retry would push one, and the next
`log` call the copy. After a refusal the person was told was final, the
copy would still be pushed.

#### What the answer session posts by itself

**Rule:** answer-session spec, *A recorded answer posted by itself links
filter 1's hit and quotes no answer*; *An automatic post's text is fixed by
the answer session* (*What the answer session does by itself* gives why).
A log file's answer is a whole comment, which could hold @-mentions that
would notify people again on GitHub, or a `Recorded in: ` line of its own.

*Ruled out by a scenario:* a recorded answer in a sentence the model writes,
which a crafted thread could steer (answer-session spec: *Filters 2 to 4 judge
every incoming question*, scenario *A thread's text cannot choose the words
posted*); and quoting the answer with its mentions neutralised, which needs a
rule per surface (answer-session spec: *A recorded answer posted by itself
links filter 1's hit and quotes no answer*, scenario *A recorded answer is
posted by itself*).

#### No automatic post repeats one in its chain of replies

**Why:** checking only the post a reply answered would let an agent that
kept replying get filter 2's text, then filter 4's, then filter 2's again
with no person seeing it.

#### A post the person chose says so

**Why:** the line `The person chose this filter.` tells a reader of the
thread that a person, not the answer session, chose the filter.

### Incoming questions, declining and handled files

#### Which questions count as an agent's

**Rule:** answer-session spec, *An agent's question comes from a bot account
or a log file*; *A relayed question is a person's question*.

Only an agent's question gets an automatic `Inquisitor: ` reply, so any
doubt counts a question as a person's: no person then gets a reply nobody
wrote. An agent's question posted with a person's own credentials counts as
a person's since the answer session cannot tell the two apart.

#### Filter 1 runs on every incoming question not placed `other`

**Rule:** answer-session spec, *Filter 1 runs on every incoming question not placed `other`*;
*Filter 1's answer by itself to an agent's question logs a miss*.

#### Filters 2 to 4 judge every incoming question

**Rule:** answer-session spec, *Filters 2 to 4 judge every incoming
question*; *A clear filter 2 to 4 failure gets its fixed reply by
itself*; *Filters 2 to 4 only suggest a verdict on other questions*; *An
automatic post's text is fixed by the answer session*.

*Ruled out by a scenario:* only suggesting a verdict, so the person handles
every deferrable or cheap agent's question by hand (answer-session spec:
*A clear filter 2 to 4 failure gets its fixed reply by itself*, scenario
*A deferrable agent's question is handled for the person*).

#### A question another skill requires carries a line the answer session matches

**Rule:** inquisitor spec, *A question another skill requires carries a
person-required line*; *The second call checks a requiring skill, and the
post hook its line*; answer-session spec, *A question with a person-required
line gets no filter 2 to 4 reply*.

**Why:** the asking agent skips filters 2 and 4 for such a question. It
has already run filter 3, knowing which options the requiring skill lets it
take itself; the answer session cannot see those options. If the answer
session applied filters 2 to 4, it could close by itself a question only a
person may decide. For the same reason, the person's own decline for the
inquisitor posts no such reply either: the requiring skill wants the
person's answer. The line starts
`Inquisitor: ` like the session's own fixed texts, but sits after the
question, since the post hook blocks a GitHub post starting `Inquisitor: `,
a prefix reserved for the session. The script prints it, so its wording
never varies and finding it needs no judgement. Whether surfaces return it
unchanged: the answer-session decision record's *Rationale: A question with
a person-required line gets no filter 2 to 4 reply*.

*Ruled out by a scenario:* keeping the automatic reply on such questions
(answer-session spec: *A question with a person-required line gets no filter 2
to 4 reply*, scenario *A question spec-trace requires reaches the person*);
and applying filter 3 again to them (scenario *A marked question that seems
to fail filter 3 reaches the person*).

#### What an asking agent does with an automatic reply

**Rule:** inquisitor spec, *An Inquisitor reply is acted on only with its
miss file*; *A reply's miss file is looked for on the branch its
question's concerns line names*; *Every miss file is named by one hash*; *A
hash-only miss file shows nothing but that it exists*; *An answer session's
automatic reply is a verdict, not a person's answer*; answer-session spec,
*A concerns line settles what an agent's question concerns*; *A miss more
visible than its thread is pushed as a hash-only file*.

The inquisitor decision record's *Rationale: An Inquisitor reply is acted on
only with its miss file* says why.

A reply's miss file is named by the reply's own message id because the name
is only a lookup key, and the file authorizes one thing, a particular reply,
which its id identifies exactly. No question text is hashed, so nothing a
surface or a posting skill changes in a message's text can break the lookup.
The agent looks again three times since the session pushes the file just
after the reply. Were the agent and the session each to judge what the
question concerns, they could judge different repositories: the agent would
find no file and take the reply as input, while the session listed the
question as handled, so nobody would answer it. And an agent that also
looked on its thread's repository would act on a miss backed by a writer
there, who may have no write access to what the question concerns, though a
logged decision needs that access. Naming the repository on the concerns
line removes both failures. The session takes the line only when it names a
place on the list the session's code already lets the model choose from (its
verdict's `place`) and one the person can write to. A crafted thread can
already steer `place` to any place on that list, so a crafted concerns line
reaches nowhere new.

A hash-only miss file still shows who pushed it and when (answer-session
decision record: *Constraint: GitHub's events API shows the pusher and push
time of each hash-only miss file…*). A
readable miss stays the form wherever privacy allows one, for its value as a
log. Where the session has no questions branch for either form, it posts no
reply by itself, so an agent never acts on a bare reply. A decline that
posts nothing gets no hash-only miss file: the file would back no reply, and
with no reply to name it, it would be named by a hash of the asking
message's URL, which anyone who knows that URL could compute.

*Ruled out by a scenario:* naming a reply's miss file by the asking comment
and the filter. Where one comment asks several questions, a forged reply to
one of them would get the same name as the session's real reply to another
under the same filter (inquisitor spec: *Every miss
file is named by one hash*, scenario *A forged reply names no miss file*).

An agent pushes no citation for a lore entry a `Recorded answer: ` reply
names, since the answer session pushed any that was due, so one question
gives one citation.

#### Two reasons to decline

**Rule:** answer-session spec, *The person can decline to answer*;
*Declining for the inquisitor posts the picked filter's reply*.

The second reason, that the inquisitor should have handled the question,
applies to people's questions too, since the person chose it. How the confirmation looks is prototyped (task 6.9). The person can
still answer on the surface by hand. Reason 1 is named "nothing to answer"
to keep clear of filter 3's text, "not a real question".

*Ruled out by a scenario:* the session's model asking the person which filter
should have stopped the question, and why, since the person picks the filter
and confirms its reply instead (answer-session spec: *Declining for
the inquisitor posts the picked filter's reply*, scenario *The inquisitor's
reply is posted once the person confirms it*).

#### Messages that are not questions are ignored

**Rule:** answer-session spec, *Messages judged clearly not questions are
ignored*; *Filter 3 also offers that the agent shouldn't have asked*; *Only
a thread copy declined with nothing posted is reopened*.

"Rhetorical" is not a category: an asking agent rewrites a message that is
not really a question as a statement, so an agent's rhetorical message gets
no post.

A non-question the answer session's own judgement let through logs no miss
when declined under reason 1, since no asker erred. One the asking agent
should not have written gets filter 3's "the agent shouldn't have asked",
which posts nothing, since filter 3's fixed text tells the agent to take an
option with merit, which a non-question lacks.

*Ruled out by a scenario:* filter 3's automatic reply on a rhetorical message,
or a rhetorical fixed text of its own: filter 3 is for a real question that
did not need asking, and the decline reasons and filters 2 to 4 cover a
question that needs no answer (answer-session spec: *Filter 3 also offers that
the agent shouldn't have asked*, scenario *The agent shouldn't have asked
posts nothing*).

#### Declining with nothing to answer closes only that question

**Rule:** answer-session spec, *The person can decline to answer*; *Later
messages after an answer or a decline are new questions*.

A reason 1 decline is held in each machine's own state folder, so if it
stopped later messages counting, a follow-up would count on one machine and
not on another.

*Ruled out by a scenario:* a threaded reply reopening the declined question on
one machine, or dropping a reply that arrives after its question closed
(answer-session spec: *Later messages after an answer or a decline are new
questions*, scenario *A later message in an answered or declined thread is a
new question*).

#### The answer session writes a handled file on every close of a questions-branch file

**Rule:** answer-session spec, *A handled file closes a questions-branch
question*; *A handled file is pushed once its close takes effect*;
inquisitor spec, *Only an answer session writes a handled file*; *A log
file and a miss file have one format*.

Without a handled file, a machine that never read the thread copy would
show the file again. A machine's first poll of a channel reads only its
last 14 days, so a machine first polling more than 14 days after the
question was asked never reads the thread copy, the same question in the
thread the file's `asked_in` links.

A handled file adds no question text: the closed file's name, which it
repeats, is already on the same branch. So it never carries a private item's
question into igor's lore search, and shows nothing the closed file does not.
For a question with a category, the hash it names the closed file by hides
nothing on the branch, where the closed file sits beside it under its
readable name.
An Igor worker could still forge a handled file and report it for its Igor to
push; igor refusing to push one is asked of igor PR #216, and is open on its
side.

A close that cites a record, a filter 1 decline or a `Recorded answer: `
post, takes the question out of the person's queue whether or not the
asking agent's own filter 1 would count that record: the record is then in
the thread, and an asker that cannot count it and asks again reaches the
queue as a new question.

**A reader takes a handled file, which names no person, as the answer
session's,** as it takes an answer file at its word. A writer
can therefore push a handled file that closes a question the person then
never sees, a cost the inquisitor decision record's Constraint on guarding
a `questions` branch accepts.

*Ruled out by a scenario:* the asking agent marking its own file handled, or
deciding the close, which would need proof of the post's author
(inquisitor spec: *Only an answer session writes a handled file*, scenario *An
asking agent writes no handled file*). Also ruled out, by scenario *A handled
file's keys* (inquisitor spec: *A log file and a miss file have one format*):
copying the question's text and the original's `asked_from` into a handled
file, which nothing needs; and two keys that served only matching, which
closing by exact file name replaces: `repository`, and a key limiting a
reason 1 decline's close to the copy declined.

#### Closing works by exact identity, never by matching

**Rule:** answer-session spec, *A handled file closes a questions-branch
question*; *A decline with nothing posted closes a thread copy on this
machine only*.

Matching on a question's words, on a topic repository, which each machine's
model judges for itself, or on clocks can give two machines different
answers; exact identity cannot disagree.
A file a handled file closed is still unanswered, so an answer given to its
thread copy, where that copy is open, still pushes a log file answering it.

*Ruled out by a scenario* (answer-session spec: *A handled file closes a
questions-branch question*): each matching rule above, by question hash, by
any relay post naming the same question, by the repository a question concerns, or by the
handled day or commit time against when a copy was asked (scenario *A handled
file closes only the file it names*); and one handled file per topic
repository (scenario *Two questions-branch files get two handled files*).

#### Reopening a declined question

**Rule:** answer-session spec, *Only a thread copy declined with nothing
posted is reopened*.

After a post, the thread, which every machine reads, records how the
question was handled. A thread copy stays reopenable after a handled file
closes its questions-branch file, since that file is closed on every machine
for good and the thread copy is separate from it.

A reopened decline keeps its miss because a miss file never changes, and
nothing records that the person took the decline back. Misses feed *Lessons
from misses are drafted on request and land by scope*, so a miss is not held
back on the chance of a reopening.

*Ruled out by a scenario:* reopening a question on this machine whatever its
thread shows (answer-session spec: *Only a thread copy declined with nothing
posted is reopened*, scenario *A question declined with a post is not
reopened*).

#### A person's cite pushes a citation file

**Rule:** answer-session spec, *A person's cite of an active entry in scope
pushes a citation file*; *A miss or citation file's push is owed and retried
as a handled file's is*.

#216 counts as a citation only an agent's record that a lore entry answered
a question; igor issue #247 asks it to count a person's cite too.

*Ruled out by a scenario:* pushing a decline's citation only when its miss is
pushed (answer-session spec: *A person's cite of an active entry in scope
pushes a citation file*). When two machines decline one question, each
pushes a citation, so the entry is cited twice: an accepted case under
*Which cross-machine cases are accepted*.

#### Agreeing to a recorded answer is a filter 1 decline

**Rule:** answer-session spec, *Agreeing to a shown recorded answer is a
filter 1 decline*.

The record exists and filter 1 found it, so an answer log file pointing to
it adds nothing; a later searching agent is stopped by the record only if
its own filter 1 can read and count it. Agreeing logs a miss on a person's
question too, since the person chose the filter themselves.

*Ruled out by a scenario* (answer-session spec: *Agreeing to a shown
recorded answer is a filter 1 decline*): the session refusing agreement to
a record more private than the thread, which keeps the record's URL out of
that thread; instead the person agrees after the warning any filter 1 reply
with a more private record gets (scenario *Agreeing in a thread on a
questions-branch question pushes no answer file*);
giving agreeing its own record and `said`, the miss file's key for what the
person said, rather than the decline's (scenario *Agreeing on a question with
no thread is a filter 1 decline*); and logging a miss only when an agent
asked, since a decline logs one on any question.

#### Misses the answer session logs

**Rule:** answer-session spec, *The answer session logs its misses on the
questions branch of what the question concerns*; *A miss records who judged
it and where it was asked from*; *A miss holds the repository its question
concerns*; *A Linear or Discord question is placed by
what it concerns*; *A miss or citation file's push is owed and retried as a
handled file's is*; inquisitor spec, *A log file and a miss file have one
format*.

The fixed `said` of an automatic miss lets a review of misses tell the
session's judgement from a person's word. Where a miss file names in
`asked_by` the account that posted the question, a review of misses can
show which asker keeps asking what it should have filtered.
`asked_by` reveals nothing new: the account already shows on the question
in its thread. A miss on questions-branch files takes their most private
`asked_from` and the `repository` they share, so it is as private as they
are and about the same thing; files naming different repositories get no
miss, since they leave no one `repository` to take.

A miss's push is recorded as owed before its post since once the post is
out the thread shows the question handled and nothing else would bring a
lost miss back.

*Ruled out by a scenario:* keeping misses in the state folder, which would
make it a personal question log (answer-session spec: *The answer session
logs its misses on the questions branch of what the question concerns*,
scenario *A miss goes to the questions branch*).

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**Rule:** answer-session spec, *A log file follows the thread message its
asked_in links*; inquisitor spec, *A log file and a miss file have one
format*.

A link names one message, so every machine pairs the same file with the
same message. Why a Discord or Linear URL has one form: *Recorded:*
inquisitor record, *Rationale: A log file and a miss file have one format*.
Task 0.23 has still to compare GitHub's URL forms.

*Ruled out by a scenario:* judging every log file on its own, so the person
sees each question twice (answer-session spec: *A log file follows the thread
message its asked_in links*, scenario *A questions-branch file follows the
message it links*).

#### A link this machine never reads is not followed

**Rule:** answer-session spec, *A log file with no followed link is judged
on its own*; *An Igor's log file follows its own handback comment*.

An Igor's log file follows its handback only on an item this machine
already reads: reading any other item would let the file's `asked_from`,
which whoever pushes the file writes, choose which repository the session
reads with the person's credentials. On GitHub the handback must also be
in the repository `asked_from` names, where an Igor posts it, so a file
cannot attach itself to a handback on another repository's item. A Linear
issue sits in no repository, so there the only check is that this machine
reads the issue.

*Ruled out by a scenario:* showing the file nowhere on that machine, so the
person would never see the question there (answer-session spec: *A log file
with no followed link is judged on its own*, scenario *A log file linking a
message this machine has not read is shown on its own*).

#### A log file without `asked_in` is never merged

**Rule:** answer-session spec, *A log file with no followed link is judged
on its own*.

Merging only spares the person seeing one question twice, which costs them
a second look, while any merge rule can pair a message with another asker's
file in the same words, so that the person's decline, which closes a
question unanswered, or their answer lands on that asker's question.

*Ruled out by a scenario:* merging such a file with a thread message asking
the same question, whatever extra conditions the merge rule adds
(answer-session spec: *A log file with no followed link is
judged on its own*, scenario *A log file with no asked_in is shown on its
own*).

#### A bot's question reaches only the first person it mentions

**Rule:** answer-session spec, *Whom a message reaches is set by its
mentions*.

So each bot question has one owner: two people cannot give a bot
conflicting answers. The order an Igor mentions people in, set by igor
issue #229, is in the answer-session record's *Rationale: A handback that
mentions no one goes to the item's assignee*. The first-mention rule
applies as written whatever order an Igor uses until igor's specs state
#229's order (*igor-dependent rules state the end state*).

*Ruled out by a scenario:* a handback reaching the assignee unless it
mentions only others, which gives a bot question more than one owner
(answer-session spec: *Whom a message reaches is set by its mentions*,
scenario *A bot's message reaches only the first person it mentions*).

#### igor's handback marker

**Rule:** answer-session spec, *A handback is an Igor's comment holding
igor's marker*.

The marker is needed because an Igor posts other comments on the item too.
The post hook does not read the marker (the inquisitor record's
*Rationale: Questions in posts pass the same filters*).

Why a Linear comment counts too is in the answer-session record's
*Rationale: A handback is an Igor's comment holding igor's marker*. Linear
marks an app user's comment (task 0.16); which app user is an Igor's is
still to be measured, by task 0.38.

*Ruled out by a scenario:* counting every comment by an `igor-` App as a
handback (answer-session spec: *A handback is an Igor's comment holding
igor's marker*, scenario *An Igor comment without the handback marker is not a
handback*).

#### Only an item's newest handback is shown

**Rule:** answer-session spec, *Only an item's newest handback is shown*.

Only the newest handback is shown because it says where the Igor is blocked
now. A newer one is posted only after the person hands the item back to the
Igor without answering the older one.

*Ruled out by a scenario:* an answer naming only the oldest unanswered log
file, whose question no longer says where the Igor is blocked (answer-session
spec: *Only an item's newest handback is shown*, scenario *A newer handback
passes over an older unanswered one*).

#### A handback that mentions no one reaches the assignee

**Rule:** answer-session spec, *A handback that mentions no one goes to the
item's assignee*; *Whom a message reaches is set by its mentions*. The
assignee is the person who handed the item to the Igor; the evidence is in
the answer-session decision record's *Rationale: A handback that mentions
no one goes to the item's assignee*.

#### Each Igor log file follows its own handback comment

**Rule:** answer-session spec, *An Igor's log file follows its own handback
comment*; inquisitor spec, *A questions-branch log file links where its
question was asked*.

Linking the handback comment means one answer never closes two handbacks'
files, and the newest-handback rule needs no other mechanism. The Igor
writes `asked_in`, not the worker, because the comment exists only once the
Igor posts it.

*Ruled out by a scenario* (answer-session spec: *An Igor's log file follows
its own handback comment*): linking the log file to the assigned item, which
two handbacks on one item would share, or posting the answer on the item
(scenario *An Igor's log file follows its handback comment*); and linking its
own handback only while an earlier one is unanswered, less simple for no
further guarantee (scenario *A later Igor question on an answered item
follows its handback comment*).

### OpenSpec, prototypes and scenario tracing

#### OpenSpec for new work in shared-skills

**New work in shared-skills goes through OpenSpec, except UI, which is
prototyped and then built directly; this change adopts OpenSpec, spec-check
and spec-trace for the repository.** `AGENTS.md` states the arrangement,
decision records included. An existing skill gets its spec in a change of its
own, skill by skill, as shared-skills issue #57 plans; a change that edits a
skill with no spec, as this one edits github-app and bug-hunter (tasks 5.5,
5.7 and 5.8), lists the edit as a task. This change's reasoning that no test can
check is in the decision records of `inquisitor`, `answer-session` and
`gh-post`; there is no `.agents/skills/inquisitor/DECISIONS.md`.

#### spec-trace's template skips the questions branch in this change's merge

**Task 5.9 brings shared-skills PR #101's commit onto this change's own
branch with the implementation, so spec-trace's workflow template, which
other repositories copy, skips pushes to a `questions` branch starting with
the merge that ships the inquisitor.** This repository's own workflow already
skips it. A `questions`
branch holds none of the project's files, so a workflow that checks them on
push fails there. #101's README and SKILL.md text gives the inquisitor as the
reason for the skip. Landing in this change's merge, the skip arrives with
the inquisitor's README (task 5.6), which says the template skips the branch;
#101 merged earlier would name a skill not yet shipped, and merged later
would leave that README describing a skip the template lacks.

#### The change is archived only after every expected gap is tagged

**Archiving waits for task 4.3 to tag every expected gap, beside task 7.0's
wait for igor PR #216 to merge, since archiving writes the scenarios into
the directory where spec-trace's CI fails on an untagged one.**

## Open Questions

### Facts measured before building

The task each bullet names measures its fact before anything is built (tasks 0.1 to
0.3 are under *What the hook relies on, not yet measured*). Each bullet says
what the spec does if the fact is false. Task 0.12 is measured (*What task
0.12 measured*). Task 0.11 asks whether GitHub's API gives a comment's or
review's text and author, which *The log command takes answered_by from the
linked comment* relies on. Of these, only an issue comment's author is
measured, and tasks.md records how. If GitHub gives no author for a review
or a review comment, that requirement needs another source for
`answered_by` before it is built. The spec names none, since GitHub
documents the same `author` field for both (the inquisitor record's
*Rationale: The log command records a linked GitHub comment's own text*).

- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, wherever the agent lacks push access, every
  answer in a post and every issue's decision block (the start of its body
  before its first heading, or its first section whose heading starts with
  "Decision", which the spec counts as a decision document) counts as input,
  and a post's question tags no one. The task also asks whether the read
  works when `<login>` is an App's `<slug>[bot]`. If not, a pull request
  or issue that a github-app App authored never has an author with write
  access, so the decisions committed on its branch and its decision block
  count only as input.
- **Can the script learn which login a post goes out as?** (task 0.7) A post
  sent with the github-app skill goes out with a token only the posting
  command holds, which hides it from the script. If not, the script treats
  every post as going out as the configured login, and with a person in the
  session it asks through the picker where it would have tagged them.
- **Can the script tell whether a person is in the session, and whether a
  headless session can post?** (task 0.9) If it can't tell whether a person is
  there, the session counts as having no one. If it can't tell whether a
  headless session that is not an Igor worker can post, that session counts as
  unable to post and asks nowhere. Whether the script runs in an Igor's run is
  not part of this fact: it reads `IGOR_RUN`. Task 0.9 checks that igor sets
  `IGOR_RUN` as igor PR #216 specifies, once igor builds it.
- **Can the script find the approver of the pull request that added a
  decision?** (task 0.8) A spec or decision record file leads through blame and a
  commit to a pull request and its reviews. If not, the script skips the
  tagging order's first candidate.
- **Can the script find the GitHub login of the last person to commit to a
  file?** (task 0.5) Git records a name and an email, not a login. If not, the
  script skips the tagging order's third candidate.
- **Can the agent open, and write in, a repository's private security
  advisory?** (task 0.10) That needs private vulnerability reporting enabled,
  or an admin or security-manager role. If not, an agent asking a
  vulnerability question records the question and its answer nowhere. It
  uses the answer only in the code of the fix that repairs the
  vulnerability, and tells the person only that a vulnerability question
  is blocking, without the question's text.
- **Can the private fork's pull request be merged before the advisory is
  published?** (task 0.13) The spec's weakness requirements give what each
  result means. Until it is measured, a fork commit's message describes the
  weakness, and a regression test goes in the fork, only on the word of the
  person publishing the advisory; without it, the advisory's text holds the
  full description.
- **Can an Igor worker post?** (task 0.14) igor's task-execution requirement
  keeps every credential but its seat's out of the worker's environment, but a
  `gh` login in the worker's home directory is in neither its environment nor
  its working tree. If a worker can post, it still asks only through its
  Igor, and the credential in its reach is reported to igor as a breach of
  that requirement.
- **Does the Discord bot token pattern match a real token?** (task 0.33)
  The credential patterns' Discord shape has no measurement behind it. If
  the relay's real token does not match, the pattern is changed to the
  shape measured.

### Facts the answer session relies on

**Tasks 0.16 to 0.21, 0.23, 0.25, 0.28, 0.30, 0.31, 0.34, 0.35, 0.37 and 0.39 measure facts the answer session relies on. Each task,
in tasks.md, says what the spec does if its measurement goes against it.
Tasks 0.18 and 0.19, which check that a command the mod runs reaches no tool
hook and that a mod keeps polling while idle or in the background, stop
building if they fail, until the repository's owner decides; so does task
0.34 if Claude Code cannot restrict the session's tools. Task 0.37 checks
that a mod can submit a prompt of its own and have the model answer it
unattended; if it cannot, building the mod stops, and the answer session
is designed as a standalone UI and prototyped for the owner's approval. The
rules that wait on
task 0.21, which tasks.md's task 0.21 lists, are not built until it is
measured, and the repository's owner decides then what to build for them.**

Task 0.25 records how each surface reports two kinds of refusal of a relay
post: one for its text, such as its length, and one for lack of permission.
A refusal the session cannot sort into either kind waits for the person.

- **Do Linear and Discord return a posted line's words unchanged?** (task
  0.28) The answer session finds a person-required line and a concerns line
  by their fixed wording after reducing markup. If a surface changes the words, such as by escaping the parentheses, the
  session matches the form task 0.28 records instead. Task 0.28 is still to
  run, on both surfaces: task 0.23 measured a Linear comment's text, not
  this line, and `openspec/specs/answer-session/decisions.md` gives its
  result under *Rationale: A question with a person-required line gets no
  filter 2 to 4 reply*.
- **How does Claude Code restrict a session's tools?** (task 0.34) The
  answer session needs its session's model limited to its conversation,
  `propose_reply`, `record_verdict` and Read, Grep and Glob, enforced by
  Claude Code through permission settings, a startup option such as `--allowedTools`, or a
  mod's own control, never by a hook. If Claude Code offers no such
  control, the design falls back to hooks and the change cannot be built as
  written: the repository's owner decides what to build. *The session's
  model has no shell, no writing tool and no web fetch* and the `answer`
  command's line in *Setup installs the answer command* wait on task
  0.34.
- **Does the `answer` command's line work?** (task 0.30) It relies on
  `CLAUDE_CODE_NO_FLICKER=1` giving the fullscreen layout, on `claude
  --name`, and on a prompt argument running a slash command. If one fails,
  the command line in the answer-session spec's *Setup installs the answer
  command* is changed to what the measurement shows works, before the
  command is built.
- **Does a GitHub comment's `node_id` identify it wherever it is read?**
  (task 0.31) A miss file backing a GitHub reply is named by the reply's
  `node_id`, which the session takes from its post's response and the
  asking agent from the comment it reads. If GitHub's REST or GraphQL API
  lacks it, a kind of comment has none, or an edit changes it, the GitHub id
  that names a miss file is changed, before miss files are named on GitHub,
  to one the measurement shows works.
- **What marks an Igor's handback?** (tasks 0.6 and 0.38) igor PR #216
  has not yet given the form of the marker on igor's handback comments;
  task 0.6 records it once #216 does. Task 0.38 finds what tells an Igor's
  Linear app user from every other Linear app user, as the `igor-` slug
  prefix tells an Igor's App on GitHub; if nothing does, no Linear comment
  is a handback. *A handback is an Igor's comment holding igor's marker*
  waits on task 0.6 on both surfaces, on task 0.21 on GitHub, since the
  prefix needs the comment's App (next bullet), and on task 0.38 on
  Linear.
- **Which App wrote a comment** is measured by both task 0.21 here and igor PR
  #216's task 4.8. The rules that need it wait on task 0.21, which lists
  them.

### What other changes must provide

- **github-app and linear-app still hand a relay identity's token to
  commands that can print it.** adamstallard/shared-skills#96's body
  states what github-app must change, and #112's what linear-app must. Until each does, *The README
  warns that a relay's token can be printed* keeps its warning for that
  skill.

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would need that surface's API to vouch for the message's author,
  and a map from the author to a GitHub login: igor issue #160's configuration
  entry keyed by the Discord user id, or a file in the lore repository. A
  later change would choose. Without it, an answer typed directly on such a
  surface counts only through a decision document, such as the scribe's
  record; one typed in the answer session and relayed there counts through its
  answer file.

### Left to implementation

- **Task 6.11's details are chosen at implementation,** and each becomes a
  requirement with a scenario, or a decision-record entry with evidence,
  when it is made. *Some answer-session details are decided at
  implementation* lists them and what is decided around them.
