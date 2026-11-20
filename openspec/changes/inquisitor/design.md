The inquisitor is a skill that stops an agent's needless questions to a
person. Before asking, the agent runs each question through four filters:
filter 1, already answered (it searches for an earlier answer); filter 2,
deferrable; filter 3, not a real question; filter 4, cheap to reverse (*Four
filters stop questions before a person*). Hooks on Claude Code's question
picker and on GitHub posts block a question that has not been through them.
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
   issues a token holding each question's hash and, for a picker question,
   its first option's hash, which the second call checks the recommended
   answer against, never their text.
2. `inquisitor.py vet --pass <token> --verdicts v.json` records one verdict
   per question, keyed by the SHA-256 of its text.

The calls prove that the filters were printed and the search ran before each
verdict, not that the agent judged well. A hook allows a question when its
latest record is an `ask` less than 2 hours old; the post hook also passes a
`deferred` one in the places filter 2 defers to (spec: *Two calls prove the filters
ran*).

The records live in the user's state folder, shared by every session under
one HOME, since a session spans repositories and a hook's working directory
can differ from `vet`'s (*Hooks and verdict records*). Apart from them, the
hooks keep no record of any question, one about a vulnerability included.
The question log files (*Where the logs live*) are the lasting records; for a
vulnerability question it is the repository's private security advisory.

When a hook can't read the records, the picker hook lets the question through
and the post hook blocks a post that holds one. An unfiltered picker question
at worst reaches the person; a post's unchecked question might be a
vulnerability, and a published one can't be taken back.

**Ruled out by a scenario** (inquisitor spec: *A hook blocks a picker question
that was not vetted*):

- **The skill's description alone,** with no hook: a model loads a skill by
  judgement (scenario *An unvetted question is blocked*).
- **Records kept per clone,** as prose keeps its pass tokens in the git
  directory: a `vet` run in another repository or clone would record where
  the hook never looks, and a verdict is about the text, not the clone or
  worker (scenario *A verdict recorded in another repository counts*).

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

From that measurement, the Igor-worker rules assume a worker with no
inquisitor configuration, no GitHub credential (that one gap aside), no
picker and no hooks, that reads only its working tree,
its outbox and what its Igor passes it. It reports to its Igor through its
output or an outbox; igor PR #175 chooses which channel each kind of report,
such as its citations, takes. Once igor lets a worker run the skill's script
(*What igor must provide*), the worker searches lore through `igor
lore-search`, and the script knows it is in a run by `IGOR_RUN` (*Igor
workers and Igor runs*).

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
sign with prose. prose's footer holds no question, so signing leaves the body
vetted. An edit after vetting means vetting again; after signing, signing
again too.

`vet --post` finds a rhetorical question in a post too. Filter 3 stops it, the
agent rewrites it as a statement, and its `decided` verdict names the post as
where the choice is recorded: the rewritten statement is the whole choice, and
it is in the post.
Outside a post, the agent rephrases a rhetorical question as a statement and
records nothing.

## Where the logs live

**Every repository has an orphan branch named `questions`, its questions
branch, which holds a file for every question about that repository, and for
every miss, a question a person said did not need asking. A question's file
is pushed there directly, with no pull request.** The inquisitor decision record's
*Rationale: A question is pushed to the questions branch of what it
concerns* gives why no review is needed and why the files are not committed
with the work. The question is worded, before it is asked, to reveal nothing more private
than what it concerns (spec: *A question is written
at the privacy of what it concerns*), so its log can sit beside what it
concerns.

- **About one repository, a lore repository included:** a file on that
  repository's questions branch. Repository questions need no lore
  repository and no igor.
- **About a collective:** a file on the questions branch of
  the team's lore repository. Keeping the files off the default branch
  leaves that branch holding only the reviewed lore entries Igor gives
  agents. The files hold no `conditions`, the key that marks a lore entry,
  so neither the search nor Igor reads one as an entry. An answer worth
  giving agents as lore is promoted by a pull request adding a lore entry with the status
  `provisional`; the question's file stays.
- **About one person's way of working:** no log (*A way-of-working question
  gets no log*).
- **In one of the three categories** (`vulnerability`, `secret`,
  `personal`): no log. Of this skill's records only the hooks' verdict record
  holds it, as a hash. In an Igor's run, igor keeps the category words, never
  the text, in an operator-only file on its host, and moves the session logs
  that hold the text next to that file (igor PR #216's decisions 88, 89, 97
  and 98).

**A question asked in a GitHub post is logged when asked; one asked only in
the picker, or in a Linear or Discord thread, is logged once answered, with
its answer. So is a post's question whose questions branch is more
visible than its thread or the repository it was asked from, once a person
answers it and confirms the record there.** The person answering first sees where the record
will go (*Nothing goes somewhere more visible than its source*), and an
unanswered picker question is not logged at all: the agent's report says so.
A thread is its question's own record until the answer comes.

A file is taken at its word for who it names (*A file is trusted for who it
names*).

A worker pushes nothing, and neither does an inquisitor run the Igor starts
itself with no worker: each reports its files, and the Igor checks them and
pushes them, refusing one holding an answer, so a worker steered by untrusted text in its
item can't write a person's answer. An agent that cannot push, for want of credentials
or of write access to the repository, keeps the file pending and reports it.
The answer session keeps none, since it records each push it owes and
retries that push itself.

The spec's *A log file and a miss file have one format* holds the files'
path, name, keys and encoding. An answer with `input` authority, which
cannot stop a question, goes only into a log file. A lore entry that stops a
question gets a citation file (*Citations go to the lore repository's
questions branch*). Every log file, miss file and question in a post is
scanned for credential patterns, as a backstop only (*The secret scan is
only a backstop*).

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

`~/.config/shared-skills/inquisitor.json` holds the lore repositories, the
GitHub login of the person running the session, and the answer session's
section, `answer_session`, whose keys the `answer-session` spec defines:

```json
{
  "login": "adamstallard",
  "lore": [
    {"path": "/Users/me/src/team-lore", "owners": ["adamstallard"]},
    {"path": "/Users/me/src/api-lore", "repos": ["adamstallard/api"]}
  ],
  "answer_session": {
    "github": {"relay": "adam-relay", "subscriptions": ["adamstallard", "BrightID/aura"]},
    "linear": {"relay": "adam-relay", "subscriptions": ["ENG"]},
    "discord": {"relay": "adam-relay", "user": "123456789012345678",
                "subscriptions": ["987654321098765432"]}
  }
}
```

`path` is a local clone; `owners` and `repos` list what the lore repository
serves. The search reads the clone's remote-tracking default branch, such as
`origin/main`, and the `questions` branch with `git show`, never the working
tree or a local branch, which could be on another branch or hold an
unreviewed edit. It reports when a fetch last updated that default branch,
read from the branch's reflog, so the date and the content come from one ref;
a clone with no such entry, such as a fresh one, reports "unknown". Neither
the skill's own fetch, which brings only the `questions` branch, nor
`FETCH_HEAD`, which that fetch rewrites, gives this date. So the date is
when the clone last received a change to that branch: not when the branch
last moved on GitHub, and not a later fetch that brought nothing new.

Reviewers are listed in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line, decided there in review,
so every teammate's agent tags the same person.

Visibility, of a lore repository or of the repository a question concerns,
is read with `gh repo view --json visibility` on the clone's `origin`, which
gives `PRIVATE`, `INTERNAL` or `PUBLIC`, ranked in that order. Write access
is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Whether that call works for a caller without
push access is unmeasured (task 0.4). Each check fails closed:
- an unread visibility of the repository the question concerns counts as
  private;
- an unread visibility of a lore repository, or of a post's target, counts
  as public;
- an unread permission counts as no write access, so a question never tags a
  person who might be unable to decide it.

The configured `login` counts only when it equals the account `gh` is logged
in as, read by running `gh api user` as the person, so nobody can claim a
maintainer's login by typing it into their own file.

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

### Polling while open, with the person's credentials

The answer session polls, and only while it is open (the answer-session
decision record's *Rationale: The answer session polls only while it is
open* gives the reason), catching up on
what came while it was closed. The answer-session decision
record's *Rationale: The answer session polls GitHub's notifications and
comments* gives why polling notifications is cheap. Task 0.15 checks that,
and that a mention subscribes the person to its thread, so later replies
there, the relay's included, arrive as notifications.

A relay identity may do other work, but only the answer session starts a
post with one of the four reserved prefixes, `User says: `, `User asks: `,
`Recorded answer: ` and `Inquisitor: `. Anything holding the relay identity
could post `User says: `, which marks a question answered on every machine.
So the skill's
instructions reserve the prefixes, and the inquisitor's post hook enforces
them on GitHub in every session (*The post hook blocks a reserved prefix on
GitHub*). In the answer session's own Claude Code session the model has no
tool that posts (*The session's model has no shell, no writing tool and no
web fetch*). In any other session nothing enforces the prefixes on Linear
and Discord.

### Local state, one writer per machine

No TLA+ model is written of the pushes the answer session owes after a post,
or of its lock, which makes one session per machine the only writer of that
machine's state. The record gives the reasons.

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Rejected: A TLA+
model of the answer session's owed pushes and lock*.

### What the answer session posts, and what it logs

The answer session's Claude Code mod posts a relay post itself as a host
command, never a tool call of the session's model (task 0.18). On GitHub
and Discord it runs the relay identity's skill as an argument vector with
no shell, its text in a file or on standard input, because the person's
answer and drafts built from a thread's untrusted text reach the command.
On Linear, where linear-app has no post command, it sends its own HTTP
request, holding the token linear-app's `token` command prints only in
memory, never in a command's arguments, which any user of the machine can
read. A relay post on
Linear or GitHub names its question with a last `Re: <URL>` line, so a
thread holding several questions keeps a state for each; in a review thread
a post answering the comment that starts the thread leaves it out. On
Discord a relay post replies to its question.

A relay post counts for nothing in filter 1 (*An answer given through the
answer session counts by its answer file*).
The thread's state is still read from relay posts, which is sound only while
nothing but the answer session starts a post with a reserved prefix. Until
github-app refuses to hand out a relay's token, any agent on the machine can
post through the App where no hook sees it, a gap the answer-session decision record accepts (*Constraint:
Until github-app refuses `token`, `run`, `credential get` and `wire`*).

### What the answer session does by itself

The answer session runs all four filters on every incoming question, so the
person sees only what needs them. Posting without the person raises two
risks, and the spec answers each:

- **A thread's text reaches the model that judges it.** So the model writes
  no word of an automatic post, and a crafted question can at worst choose
  which fixed reply or which record is posted. Filter 3's and 4's replies tell the asking agent to decide the question
  itself. The agent acts on one only when a miss file backs it, which a
  crafted thread cannot supply; it already ran both filters, so the reply is
  a second judgment that one option has merit or that the choice is cheap to
  reverse (*What an asking agent does with an automatic reply*).
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the thread;
  otherwise the person sees it and decides.

### The session's model

The person chats with the model in the session's conversation, about the
question on screen and its answer; the answer session's panel sits at the
bottom of the screen, above the prompt box, and the rest of the screen is
that conversation. The model may ask the person
in its reply (*A discussion runs in the session's own conversation*). It has
only its conversation, read-only file tools that read and search files, and
`propose_reply`, the answer session's tool that drafts a reply into the
prompt box. It cannot
post, run a command, write a file or fetch a URL. The answer session's own
code does every post, `log` call and push, and every fetch from a surface.
Coding, testing and committing happen in other Claude Code sessions. The
prototype has shown that a mod can fill the prompt box and register a tool
the model calls by name.

## Tracing scenarios to tests

Every scenario but the expected gaps below gets a tagged test. Where a
scenario is about the script or a hook, the test runs it. Where it is about
what the agent does (asking through the picker, batching, handing a question
back, choosing a lesson's scope), the test checks that SKILL.md states the
rule, and its name says so.

**Expected gaps.** A scenario that only igor's unbuilt work, such as `igor
lore-search`, can make pass gets no tagged test until igor builds it. A
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

#### Four filters stop questions before a person

**Every question an agent is about to put to a person passes four filters
first.** The rule covers any agent in any task, not only spec review or
OpenSpec, and the skill is useful locally with nothing from Igor.

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

**A deferral stays visible: filter 2 lists the question as not done in the
current work, files it as an issue if it outlives the work, and a person who
wants the answer now says so.** The `deferred` verdict names where the
question will be listed, such as "this PR's description", not a link, because
that post may not exist yet.

#### A question that blocks no step waits for the round's end

**Only a question that blocks the step the agent is on is asked at once.
Every other surviving question waits for the end of the question round and is
asked with the round's other questions.** Meanwhile the agent goes on with
the answer it recommends, and the question says the work assumes it. A round
ends at a hand-back to a person as spec-check defines one, or when the agent
ends its turn or its run (spec: *A question round ends at a hand-back or at
the end of the agent's turn*).

**Why:** each question asked mid-round interrupts the person, while at a
hand-back they turn to the work anyway, so the round's questions cost one
read. Because the question names the assumption, "yes" confirms work done and
any other answer says what to redo; the rework is bounded by one round.

**With a person in the session, every end of the agent's turn ends a round,
pull request or not.** Ending the turn hands the person control, so held
questions would sit unseen while they are there; without a pull request there
is no hand-back at all.

**The hand-back is spec-check's,** so one word means one moment across the
skills; the inquisitor spec cites spec-check's rule with one example, keeping
its list of what counts in one place. The round also ends at each end of the
agent's turn, which spec-check's review round does not, so it has its own
name: a question round.

**Unlike a deferred question,** which the current work does not need
answered and so is listed as not done and never asked, a question waiting for
the round's end is one the work needs: the work goes on, on an assumption the
answer may overturn. The agent vets it again at the round's end, since a
verdict lasts 2 hours and an answer may have been recorded since.

*Ruled out by a scenario:* asking each surviving question as it arises
(inquisitor spec: *A round's questions are asked together at its end*,
scenario *A blocking question is asked at once, and the others wait*); and
ending a round at each push, which spec-check's SKILL.md rejects for its
review rounds too, since agents push after almost every commit (*A question
round ends at a hand-back or at the end of the agent's turn*, scenario *A
push ends no round*).

#### A question another skill requires goes through filters 1 and 3 only

**The agent puts a question that another installed skill requires a person
to decide through filter 1 (already answered) and filter 3 (not a real
question), and skips filters 2 and 4,** so the inquisitor still screens the
questions other skills generate, which is what it is for. Such questions
include a prose cold-read finding the agent would keep, spec-trace's
adopt-or-decline, and bug-hunter's Step 0 stop, where bug-hunter asks which
of a file's diverging staged and unstaged edits to keep.

When only one option has merit, filter 3 has the agent take it: for a prose
finding, that is usually fixing the passage, which is what prose wants.
Filter 3 takes only an option the requiring skill lets the agent take
itself. When the one option with merit is one the skill allows only with a
person's answer, such as prose keeping a finding as `kept (asked)`, the
question is asked.

**Why filters 2 and 4 stay skipped:** a deferral cannot unblock a step the
requiring skill holds, such as prose's signing or bug-hunter's Step 0 stop.
A cheap reversal does not override a choice the skill reserves for a person,
such as adopting spec-trace. Filter 3 never settles a real choice, since it
acts only when one option alone has merit. Filter 4 acts when two options
have merit; under the same limit it could take only the one the skill lets
the agent take, so it would always fix a prose finding that keeping had
merit for too.

*Ruled out by a scenario:* exempting such a question from filter 3 too
(inquisitor spec: *A question another skill requires skips filters 2 and 4*,
scenario *A prose finding with only a fix of merit is fixed, not asked*);
and filter 3 taking an option the skill reserves (scenario *Filter 3 takes no
option the requiring skill reserves for a person*).

#### bug-hunter's Step 9 recommendations go through the filters

**bug-hunter's Step 9 recommendations, which it asks the person about one at
a time, go through the four filters like any other question, so fewer reach a
person,** rather than each skill making its own exceptions. Task 5.7 changes
bug-hunter's SKILL.md so that Step 9 runs each recommendation through the
filters before asking. The task's table of starting rules is input to its
design, not decided behaviour: its implementer sets the final rules, which
are reviewed with the implementation. The spec fixes only that each
recommendation passes the four filters. Nothing in bug-hunter changes before
the inquisitor skill exists.

#### A prepared question can be answered "yes"

**A surviving question states the recommended answer, first in the picker,
so most questions can be answered "yes".** The picker hook need not check the
order: reordering options after vetting changes the question's text, which
the hook blocks as unvetted.

#### With a person present, ask through the picker

**With a person in the session, on a host with a picker, an agent never asks
in its reply, except in an answer session's discussion; a subagent hands its
surviving questions back to the agent that started it.** On a host with no
picker, the agent asks in its reply once the script's two calls vet the
question, a `vulnerability`, `secret` or `personal` question included, since
the reply, like the picker, reaches only the person.

**Why:** the picker hook then sees every question, and the starting agent,
which is talking to the person, can batch a subagent's questions with its
own.

*Ruled out by a scenario:* a hook at the end of the agent's turn that reads
questions in its reply: the person has already read the reply when it runs
(inquisitor spec: *Where the host has a picker, an agent asks through it,
never in its reply*, scenario *A question goes through the picker*).

#### How a session with no person asks

**A session with no person in it never uses the picker, which is for a person
to read.** It posts its question if it can, as a scheduled agent does; an Igor
worker, which holds no credential that can post, asks in its handback
comment; a session that can do neither asks nowhere, stops only if the work
needs the answer, and reports the question. Task 0.9 measures how a session
tells whether it has a person; one that cannot tell counts as having none, so
a picker is never opened with nobody to answer it.

It never asks or posts a `secret` or `personal` question, and asks a
`vulnerability` question only in the repository's private security advisory.
It stops the work that needs the answer and reports only that a question of
that category is blocking, with no text; during an Igor's run the worker
raises igor's flag instead (*The flag a worker raises for a question with a
category*). A way-of-working question it holds back as well, stopping only if
the work needs the answer and reporting that the question waits for the
person (spec: *A session with no person in it holds back a question with a
category*).

#### A question's audience is no wider than its subject

**A question goes only where its audience is no wider than what it concerns,
in every channel, Linear and Discord included.** Where the place would be
wider, or the agent cannot tell, it asks through the picker. With no person
in the session, where the place would be wider it posts in the repository the
question concerns, or, for a collective's question, in the
repository holding the current work. Where it cannot tell, it posts nothing
and says so.

#### What counts as a question in a post

**A question in a post is each list item in an open-questions section, and
each other sentence ending in a question mark, as the spec's *A question in a
post is a listed item or a sentence ending in a question mark* defines.** A
section begins only at a heading, bold label or plain colon line whose label
names questions or a deferral, such as "Open questions:" or "Deferred:",
where agents list open questions; a deferred question listed there passes on
its `deferred` verdict. A section ends only at the next heading or bold
label. *Questions in posts* gives the order with prose's pass and signature.
The rule lives in one function, so it is cheap to change if it misjudges
posts.

*Ruled out by a scenario:* letting any colon line starting "Open" begin a
section, which would turn the commands under "Open a terminal and run:" into
questions (inquisitor spec: *A question in a post is a listed item or a
sentence ending in a question mark*, scenario *A colon line that names no
questions begins nothing*).

#### A deferred question passes only untagged, listed or in a new issue

**A `deferred` verdict less than 2 hours old passes the post hook only for a
question that itself tags no one and is an item of an open-questions section
or in a post that creates an issue, even when another part of that issue tags
someone; anywhere else the question needs an `ask` verdict.** These are the
two places filter 2 defers to: the list of what is not done, in whatever post
reports the work, and an issue when the question outlives the work. Tagging
someone asks them, which needs an `ask`.

#### One person who can decide is tagged

**A question in a post tags the first candidate the script finds with write
access to what the question concerns,** since only a person with write access
can decide. The spec's *A question in a post tags one person who can decide,
if there is one* sets the order: the approver of the related earlier decision
the second call recorded, then a login in `.inquisitor/reviewers`, then the
last committer of the files involved. The tag goes on a line of its own,
which the question's hash leaves out, as it leaves out the related-decision
line: the script finds whom to tag only at the second call, so a tag inside
the vetted text would change that text's hash and make the post hook block
the post until both calls ran again (spec: *A tag line names the person a posted question tags*).

#### The configured login names the person

**The person running the session is the configured GitHub login only when
`gh`, run as the person and never with a GitHub App's token, is logged in as
that account** (reason under *Configuration*).

*Ruled out by a scenario:* taking the login from `gh api user` run as the
identity the post goes out as: as a GitHub App it gives no user, and as the
person it gives their own login, a self-tag that notifies no one (inquisitor
spec: *A configured login counts only when gh is logged in as it*, scenario
*An agent posting as a GitHub App keeps the configured login*).

#### When no candidate can decide

**With no candidate holding write access, the script turns to the session's
configured login, and tags it only when it has write access and the post goes
out as someone else,** since a self-tag sends no notification. Where the post
goes out as the configured login, or no login is configured, a session with a
person in it asks through the picker instead, and one with no person tags no
one. When the configured login lacks write access, the question tags no one,
even with a person in the session. A question that tags no one is posted with
a line saying no one with authority to decide could be found (spec: *A
question no candidate can decide turns to the session's login*).

### Hooks and verdict records

*Proving the filters ran* gives the reasoning for these hooks and records,
and the alternatives not taken; *What the hook relies on, not yet measured*
says what happens if a `PreToolUse` hook cannot block the picker.

#### The hooks are on once the skill is installed

**The skill's hooks are enabled by default: installing the skill is the
opt-in,** as it is for prose's blocking hooks.

#### Two calls prove the filters ran

**The skill's script takes each set of questions in two calls, as prose's two
calls prove its pass ran, so no verdict exists without filter 1's search.**

#### Files passed to the two calls stay private

**The files an agent passes to the two calls go in a private directory made
with `mktemp -d`, outside any repository, each with mode 0600; the script
refuses a file its group or others can read, or whose directory they can.**
The script takes a question with a category, and its verdict, only on
standard input, never in a file. Outside any repository, the files can't be
committed.

*Ruled out by a scenario:* the system's temporary directory, such as `/tmp`,
where a file with the usual mode is readable by every user of the host
(inquisitor spec: *The two calls' files and records stay private*, scenario
*A questions file others can read is refused*).

#### Verdict records live in the user's state folder

**The hooks' records live in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`, beside prose's session
marks.** They hold hashes, verdicts, verdict fields and times, never a
question's text, so they are the hooks' state, not a personal question log.
A record identifies its question by the plain SHA-256 of its text.

#### An `ask` record drops the option's label

**A picker `ask` record keeps, for each option other than the one the agent
recommends, the agent's own words from its verdict on what that option would
change, but no option's label,** since the labels are part of the question's
text, which no record holds. Nothing else records which option the person
chose, so the records cannot show later whether they took the
recommendation: a cost the rule accepts.

#### Verdict records are shared under one HOME

**Every session, hook and script call run under the same HOME shares one set
of verdict records,** so one session's verdict on a text lets another session
ask that text, through the picker or in a post, without vetting it again. The
hooks check only that the filters ran on that text, not where, so a verdict
reached in one repository lets the question through in another, whose
decisions that run's filter 1 did not search.

#### Every verdict record expires after 2 hours

**Every verdict record expires 2 hours after it was made, whatever its
verdict or category, and the next call or hook to read the records deletes
it.** Each hook treats a record 2 hours old or older as missing, so deleting
it removes nothing a hook would accept. On an idle machine, where nothing
reads the records, an expired record can stay on disk for days. A post edited more than 2 hours after
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

**The picker hook and the post hook spend no verdict record.** When one
question blocks a call, the agent vets that question alone and calls again,
and the call's other questions need no vetting again.

#### The related-decision line is left out of the hash

**The hooks match a question's text without its related-decision line,**
`Related: ` and one URL with no spaces, on a line of its own (spec: *A
related-decision line is one URL on a line of its own*). The related decision
turns up in the first call's search; the agent names it at the second call,
which records it with the verdict, and adds the line afterwards with no
further vetting. Since no vetting sees the line, both hooks block a
related-decision line holding a credential pattern.

#### What each hook does when it can't read

**The picker hook lets a question through when it can't read its input or
its records. The post hook lets through input that is not JSON; it blocks a
`gh` command whose body it can't read, and a post holding a question when it
can't read its verdict records** (spec: *The post hook vets what the shared
post reader returns*). The reason is under *Proving the filters ran*.

#### The host's transcripts are outside the skill's records

**The skill's rules on its records, hash only for a question with a category
and the 2-hour expiry, cover only its own records.** The host's transcripts
are outside its control.

### The shared post reader

#### Questions in posts pass the filters, on GitHub only

**The post hook enforces the filters for GitHub posts only, sent through `gh`
or a GitHub MCP tool, as prose's posting hook covers GitHub only.** A question
in a Linear or Discord message is covered by the skill's instructions alone.

#### One post reader, shared by both hooks

**Both post hooks read every post through `.agents/lib/gh-shell/`, so every
rule the reader gains applies to prose's hook too.** spec-check's hand-back
hook uses the same library's splitter and flag tables (shared-skills PR #55),
but none of the post reader's rules. The `gh-post` spec states the rules,
including the finer points of reading a line, such as heredocs, comments and
line continuations. The reader is an allow-list because a general command
parser reads some commands differently from bash, and each difference can let
a post through unread; an allow-list blocks every form outside it, so a
difference fails closed. A second copy of the reader would add a second set
of differences.

*Ruled out by a scenario:* calling prose's copy from the inquisitor, which
fails whenever prose is not installed (gh-post spec: *The shared post reader
reads a post's body from an allow-list*, scenario *Both post hooks read a post
through the shared reader*).

#### Which commands the reader judges, and which are unreadable

**The reader judges only a command line that mentions a gh post verb, and
reads it through an allow-list. It finds the line to be one of three things:
a post it reads; no post, because no simple command in it sends text; or
unreadable. Both post hooks block an unreadable line. A gh alias or extension
is unreadable on every line.** The `gh-post` spec states the rules: *A command
that mentions no gh post verb sends no post*, *The reader reads only gh's own
top-level commands*, *A command that only runs prose's script sends no post*,
*A line whose simple commands send no text is no post* and *Any other line
that mentions a gh post verb is unreadable*. A `gh pr` or `gh issue` post is
readable only as the whole command line, as in prose's reader, since an
earlier command in the line could rewrite a body file it reads. An unquoted
body of one plain word, such as `gh pr comment 5 --body hi`, `-bhi` or
`--body=hi`, reads as `hi`, as in prose's reader today; one holding `$`, a
backtick, `*`, `?`, `[`, `{`, `~` or `\` is unreadable, since the shell may
change it before `gh` sees it.

**Why:** these are prose's reader's rules, plus two that prose's hook gains
too: the alias rule; and the write rule (*A gh api
call counts only when it can write*). An allow-list fails closed: a form it
cannot read, such as `sh -c '…'` or `eval '…'` around a gh post, is blocked,
never let through unread. Evidence: the gh-post decision record's
*Rationale: The reader reads only gh's own top-level commands*.

*Ruled out by a scenario:* letting a command through when `gh` appears only
inside quotes (gh-post spec: *Any other line that mentions a gh post verb is
unreadable*, scenario *A gh post run through another shell is unreadable*).

#### Code given on the command line beside a gh post verb

**On a line that mentions a gh post verb, an interpreter (`python3`, `node`,
`perl`, `ruby` and the like) with a code flag anywhere among its words, such as `python3 -W ignore -c` or `node -pe`, makes
the line unreadable. There `git` stays a data command only when the first
word after `git` is a subcommand on a fixed allowlist of ones that take no
code, and no option such as `-c` gives code to run, so `git -C . status` is
unreadable.** The `gh-post` spec states the rules: *An interpreter given a
code flag makes a post-verb line unreadable*, *Only allowlisted git is a data
command beside a gh post verb* and, for a program read from a pipe or
heredoc, *Input to a no-post line reaches only data commands*.

**Why:** each can run a post the reader never sees. A program piped into
`python`, `python3` or `node` is read from that input, and telling which
script runs would mean reading the interpreter's options, so any input
reaching one makes the line unreadable.
Looking for the code flag anywhere means an option with a value, such as
`-W ignore`, cannot hide it. A list of commands that run text as code is
never complete, and git alone has many (`git config alias.p '!…' && git p`,
`git difftool -x`, `git filter-branch --tree-filter`); a list of git
subcommands that take no code on the command line is complete, since git's
subcommands are a fixed set whose options can be checked by hand. What a repository's configuration makes an
allowlisted subcommand run is an accepted gap, recorded below. prose's hook
blocks these forms too, `python3 - <<'EOF'`, `node -e` and git aliases
included.

*Recorded:* `openspec/specs/gh-post/decisions.md`, *Constraint: An
allowlisted git subcommand can run any program the repository's
configuration names, and the reader does not read that configuration*.

#### Posts sent through the github-app skill's script

**A post sent through the github-app skill's script is read as the `gh`
command it runs, when the script's path ends in `/github_app.py` and is
either written out in full or held in a `$G` that the line assigns first, and
its line is judged as the same line with that `gh` command made directly and
no `G` assignment; a
line that mentions a gh post verb and runs `python3 $G` with `G` unassigned is
unreadable.** The `gh-post`
spec's *The reader reads posts sent through the github-app skill and gh api*
states the forms. Task 5.5 makes each example in the github-app skill's
`SKILL.md` set `G` in the same command or write the script's path.

**Why:** prose's rules read a post only from a simple command whose command
is `gh`. To them, the script's call is `gh` in another command's text, which is
unreadable, so every post sent as a GitHub App would be refused. Judged as the
same call made directly, a `gh api` read through the script passes, as it does
when made directly. A command such as `cd` may also come before the script
wherever it may come before `gh`. An earlier command still makes the line
unreadable for a `gh pr` or `gh issue` post, or for a `gh api` write that
reads a field from a file, since it could change what is posted. Only a path
ending in `/github_app.py` is read, since the reader cannot know what any other
script posts. A line running `python3 $G` with `G` unassigned is blocked, since the
reader cannot tell which script it runs; that costs only a rewrite.

*Ruled out by a scenario:* blocking every `gh api` call through the script
(gh-post spec: *The reader reads posts sent through the github-app skill and
gh api*, scenario *A gh api call through the github-app script is judged as a
direct one*), and blocking the script after any other command (scenario *A gh
api call through the github-app script after cd is read*).

#### The reader reads gh api writes, REST and GraphQL

**A `gh api` write returns the body and title the reader reads from it, and is
unreadable when it has a field, title or `body` the reader can't read, or
sends a `body` to an endpoint or mutation the reader does not read; any other
`gh api` call sends no post. A write taking a field from a file is read only
as the whole command line; one with every field in the command is read within
a longer line too.** The `gh-post` spec states the rules: *The reader reads a
gh api write to an issue or pull request*, *A gh api write read from a file is
read only as a whole command line* and *The reader reads GraphQL posts and
blocks a gh api write it can't read*, which lists the thirteen mutations that
post text and makes any query the reader cannot parse unreadable.

**Why:** otherwise a `gh api` comment would skip both hooks, while reads and
writes that send no text, such as label edits, pass. A GraphQL mutation is a
write like a REST one. The hook reads a file, given by `@<file>` or
`--input`, before the line runs, so an earlier command on the line, such as
`printf 'unsigned' > c.md`, can replace a signed body with one the hook never
saw, as it can a `--body-file`; a field given in the command cannot be
rewritten.

*Ruled out by a scenario:* reporting every GraphQL mutation as unreadable,
which blocks writes that send no text (scenario *A GraphQL mutation with no
body sends no post*).

#### A gh api call counts only when it can write

**A `gh api` call is a possible post unless it is a simple command whose
command is `gh`, or the github-app skill's form of one, with every word
literal, that cannot write. It writes when it is a REST call whose last
method is not `GET`, or that gives no method and has a field or `--input`, or
that sets `X-HTTP-Method-Override`; or a GraphQL call whose query holds a
mutation or cannot be read.** The `gh-post` spec's *A gh api call is a read
only as a plain gh command* and *A gh api call writes by its method, fields,
input or a mutation* state the rules.

**Why:** a read posts nothing, so counting it would block, for every prose
user, lines such as `gh api … | python3 -c …`. The
gh-post decision record's *Rationale: A gh api call writes by its method,
fields, input or a mutation* gives why the rule follows gh's own choice of
method. `--input` counts as a parameter
whatever gh does with it, failing closed; task 1.3 checks gh's behaviour. A
word the shell builds, `xargs` or `sh -c` could add a field the reader never
sees, and a built method or endpoint might be anything, hence the
literal-words rule.

*Ruled out by a scenario:* counting every `gh api` call as a possible post
(gh-post spec: *A command that mentions no gh post verb sends no post*,
scenario *A gh api read piped into a script is no post*).

#### A post's title is read and vetted

**The reader returns an issue's or pull request's title with its body: the
inquisitor's hook vets a question in it, and prose's hook checks only that it
is readable,** since a one-line title can't carry a footer; a call with a title
and no body passes prose's hook. A title built by the shell, such as `--title
"$(git log -1 --format=%s)"`, or a title edit chained to another command, such
as `cd x && gh pr edit 3 --title 'Rename?'`, is unreadable, since the reader
reads a `gh pr` or `gh issue` post only as a whole command line (gh-post spec:
*The reader reads a gh pr or gh issue post only as a whole command line*).

#### The post hook blocks a reserved prefix on GitHub

**The inquisitor's post hook blocks a tool-call post on GitHub whose body
starts with a reserved prefix** (reserved for the reason *Polling while open,
with the person's credentials* gives). Before comparing, it reduces the body
as a question in a post is reduced for its hash (inline markup becomes its
text, whitespace is joined), then drops leading whitespace, so ` User says: `
and `**User says:**` are blocked too.

**Why:** only the answer session may start a post with a reserved prefix,
and it posts through no tool call (*A relay post is posted by a host
command, unvetted*).

#### No exemption for an Igor's handback

**The post hook vets a post carrying igor's handback marker like any other.**

**Why:** a marker any agent can add would let a post bypass vetting, and an
exemption would help no real handback: an Igor posts its handbacks through
its own code, which the hook never sees.

*Ruled out by a scenario:* recognising a handback by the marker and an `igor-`
App author together, since no real handback reaches the hook (inquisitor spec:
*An Igor's handback comment is no post, but the post hook vets what it sees*,
scenario *An Igor's handback comment is not batched or tagged*, whose last
clause has the post hook vet a `gh` post carrying the marker).

### Logs and privacy

#### Every asked question is logged with what it concerns

**Every question asked is logged with what it concerns, a repository or the
team's lore repository, at the privacy that place's maintainers set, so the
next agent finds the answer instead of asking again.** No question log is
kept anywhere personal, beyond a file pending its push (*Where the logs
live*). The skill's instructions tell
the agent not to ask a question that concerns none of these: a repository,
a collective, or one person's way of working; nothing enforces
it. Such a
question, if asked, is logged nowhere, and in a post it tags no one. The spec
names the questions that get no log file.

#### Collective questions go on lore's `questions` branch

**A collective's question goes on the team lore repository's
orphan `questions` branch, not on igor's `igor-state` branch, which holds
igor's runtime state.** The branch keeps questions not important enough to
become lore, so nobody asks them again; nothing on it is given to agents as
lore, and it has the lore's privacy and access. *Where the logs live* gives
the reasoning and how an answer is promoted.

#### A way-of-working question gets no log

**One person's way-of-working question, such as "should I keep working while
you're away?", is not logged,** because agents already read where its answer
goes: that person's agent memory or user-level `CLAUDE.md`. The answer never
goes into a committed `CLAUDE.md`, which would apply one person's way of
working to every agent in that repository.

#### Nothing goes somewhere more visible than its source

**Nothing goes to a place more visible than its source unless the person
answering confirms it; visibility is ranked private, internal (visible to a
whole enterprise), then public, and an unreadable visibility counts the
cautious way** (*Configuration* gives how visibility is read). A record's
source is the thread its question was asked or its answer given in, a Linear
or Discord thread counting as private, and for a collective's question
also the repository it was asked from.

**The person answering is shown where the question and its answer will be
recorded, and how visible that place is, before they answer:** in the picker
by the question's record line, which the second call prints and the agent
puts last in the question, and in the answer session by the preview. Answering is then an informed approval of the
wording's privacy, which is why a picker question is pushed only once it is
answered.

**That approval can widen.** With a warning that names the more private
source, a Discord thread, a Linear thread or a private or internal GitHub repository, the
person may send an answer's log file, or a decline's miss file, somewhere
more visible. A confirmed miss file is what lets the asking agent act on the
decline's reply (*What an asking agent does with an automatic reply*). The file then holds no
link into the source and names its own branch's repository as `asked_from`,
so it is exactly as visible as its branch. A miss sent there leaves out
`asked_by`, which would publish the asker's account from the private thread. A session with no person in it has
nobody to confirm, so there the ranking stands. Nor can anyone confirm the
record of a question nobody has answered, so a post's question whose
questions branch is more visible than its source is pushed only once a
person answers it and confirms.

The script also opens no lore pull request to a lore repository more visible
than the question's repository, which covers promoting an answer from a
questions branch.

#### Records are written at the question's privacy

**A question, a miss's record of what the person said, and an agent's own
choice are written at the privacy of what the question concerns: more private
context is generalised or left out.** A question that cannot stand without
that context is not asked, and is never filed in a more private place to keep
it. A person's answer is never generalised: it is recorded in their own words
or not at all, and then the question stays open.

#### Three categories are recorded by hash only

**A `vulnerability`, `secret` or `personal` question is kept in none of the
skill's records in readable form. The filters still run on it, and the agent
may still ask it, but only of the person (through the picker, or in its reply
on a host with none) or, for a `vulnerability`, in the repository's private
security advisory** (spec: *A question with a category
is asked only of the person or in its advisory*). The post hook blocks every post holding a question whose latest verdict
record has a category, since a post would keep the text where the thread's
readers see it (spec: *Some questions are recorded by hash only*). The script
records the hash, verdict, time and category, which the picker hook matches
against. Filter 1 searches for such a question only in
files on the machine, never in GitHub's issues, so its text never reaches
GitHub's search. A vulnerability's lasting record is its fix and the
repository's private security advisory.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### The secret scan is only a backstop

**The script refuses a log file, miss file or question in a post matching the
credential patterns, but the scan catches known token shapes only: a
`DB_PASSWORD=…` passes it.** So the agent never puts a credential into a
question, an answer or a verdict field, and a question that needs one gets
the `secret` category. The patterns include the two kinds of credential this
change puts within the session model's reach: a Linear key and a Discord
relay's bot token. That token's pattern bounds each
part to Discord's shape, 24 or more characters, then 6, then 27 or more, so
dotted text such as `1.15.0` or `spec.md.bak` is not refused.

The scan reads raw markdown, link targets included, while the hash uses the
reduced text, in which `[docs](https://x/?token=ghp_…)` becomes `docs`. The
post hook scans each question's raw markdown again just before posting, so a
token added to a link target after vetting, which leaves the hash unchanged,
is caught.

#### Weaknesses stay out of public text until disclosure

**Until a weakness's security advisory is published, nothing the agent writes
where people outside the advisory can read it describes the weakness or how to
exploit it; the fix's code may land publicly.** A fix's regression test is a
working exploit, so it lands only in the advisory's private fork, or publicly
after publication. Task 0.13 measures whether GitHub can merge the fork's pull
request before the advisory is published; the spec says what the test and the
fork's commit messages may do under each result, and before it is measured.

**Why:**
- The risk is describing the weakness, in any words, so whether the text
  states a question or its answer is the wrong test.
- The risk exists only while the fix is public and the advisory is not. A
  fix made in the advisory's temporary private fork, whose commits become
  public with the advisory, is not public first, unless the fork's pull
  request can merge first.
- The rule ends at publication, so a fix's commit message can then say why
  the fix was made (the inquisitor decision record's *Rationale: A weakness
  is not described in public text before its advisory is published*).
- Until task 0.13 shows that the fork's pull request merges only at
  publication, the person who will publish the advisory can vouch that it
  will, letting the agent commit the regression test in the fork and describe
  the weakness in a fork commit's message, which reveals less than the
  test.

*Ruled out by a scenario:* keeping only the vulnerability question and its
answer out of public text, for the first and third reasons above (inquisitor
spec: *A weakness is not described in
public text before its advisory is published*, scenario *A fix after
publication is described normally*).

### Which answers count, and citations

#### Only an answer with authority stops a question

**Filter 1 stops a question only with an answer that has authority; every
other hit is shown to the agent as labelled input.** The spec's requirement
of this name lists the kinds; the entries below give the reasons for their
conditions.

#### A decision on the current work's branch answers that work

The spec's *A work-branch decision answers only its own work* sets the
conditions: the branch is in the repository itself, not a fork, and the pull
request's author, or with no pull request the person running the session,
has write access.

**Why:** without those conditions, an outside contributor could commit a
decision that stops the agent's questions. Pushing a branch to the repository
itself already needs write access; a fork's branch does not.

#### An answer recorded on a work branch counts for other work once it lands

**A log file whose answer is recorded in a decision document on a work
branch pins that document to a commit, and counts for other work only once
the commit has landed on the default branch.** The file itself is on the
questions branch at once, where every agent finds it, but the work it
belongs to may never merge. A squash or rebase merge never makes the pinned
commit an ancestor of the default branch, so a merged pull request whose
document is on the default branch counts as landed too.

#### An agent's own choice is not logged

**An agent's choice under filter 3 or 4 goes into the work's decision
document where one fits, and otherwise only into the agent's report; no file
for it is pushed to a questions branch.** A logged choice would stop later
agents from judging the question again when something around it has changed,
and the only way to remove it would be for a person to read a question and
answer that no person should have to read. A later agent runs filters 3 and 4 afresh.

#### An answer without authority stays in its log file

An `input` answer never goes into a decision document, because on the
current work's branch a decision document counts as an answer, so the
agent's own write would turn input into a decision.

#### No file on a questions branch changes once pushed

A later answer is a new file holding the question and the answer, so a file
says one thing for good, and a reader can tell a file changed after its
push, which counts for nothing, from one as pushed.

#### A file is trusted for who it names

**The spec trusts the person an answer file names in `answered_by` and a miss
file in `said_by`, and checks only that the named person has write access to what the question
concerns. Nothing in the skill verifies authorship.**

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Constraint: Nothing
in the skill verifies who wrote a questions-branch file* and *Rationale: A
questions-branch decision counts only unchanged and by write access*.

Three rules limit what a file can say, whoever pushes it: a worker logs no answer,
the Igor refuses a worker's file that claims more than a worker may, and the
`log` command fetches a linked GitHub comment's own text.

#### A questions-branch decision counts by write access to what it names

**A questions-branch file holding `repository` is about that one
repository, and counts as a decision only from a writer of it; a file
holding no `repository` is about a collective, and counts
from a writer of the lore repository.** `repository` always names the
repository the question is about, and only a file about one repository
holds it; `asked_from` names where the question was asked (*Every
questions-branch file names where it was asked from*). A reader never
compares the two keys, so a file whose keys are equal, such as an Igor's
question about its own item's repository, counts by write access to that
repository. A lore writer's answer about a repository they cannot write, such
as `o/api`, is input, even on the lore repository's questions branch. A
permission that cannot be read counts as no authority.

*Ruled out by a scenario* (inquisitor spec: *A logged decision needs write
access to what its question concerns*, scenario *A file about a repository other than the one it was asked from needs write access to it*): checking the
lore repository's writers for every file, which lets a lore writer decide for
a repository they cannot change; and a design in which `repository` names
where a collective's question was asked, so that equal `repository` and
`asked_from` mark a collective's question: that design would judge a file
about the Igor's own item's repository by the lore repository's writers.

#### A logged answer is the person's own words

**A person's answer is recorded word for word, never as an agent's
paraphrase, by every writer: the skill's script, the answer session and an Igor.** The answer text a worker or agent
passes with a link only identifies which comment holds the answer.
Frontmatter `authority` decides whether a log file is answered, so a `##
Answer` line inside a question's text changes nothing. igor PR #216 records
the writer side of this rule as its decisions 67 and 70.

#### A log file's answer is written as quote lines

**Why:** every answer line starts with `>`, so a whole comment fits, even one
holding a `## Answer` line of its own.

*Ruled out by a scenario* (inquisitor spec: *A log file and a miss file have
one format*, scenario *A whole comment fits as the answer*): joining the
comment onto one line, which changes a comment holding list items; and a frontmatter key counting the answer's lines, which the quote
marks make needless.

#### The `log` command reads its inputs and the linked comments itself

The command does not check who passed an `answer_link`: it
fetches a linked GitHub comment itself and records that comment's own text.

**Why** inputs go in a 0600 file, never arguments: a question's text and its
answer passed as arguments are readable by every user of a shared host.

**Why** it refuses a question holding a line `## Rephrased question`,
`## Discussion` or `## Answer`: a reader takes those lines from a log file's
end, so an untrusted question ending in forged rephrasing lines would read
back as a shorter question, and a writer's answer would be recorded against
a different text and hash. The agent rewords such a question.

*Ruled out by a scenario:* escaping those lines: a reworded question reads the
same to a person, and an escape is one more form every reader must undo
(inquisitor spec: *The log command refuses a question holding a closing
section's heading*, scenario *A question holding a closing section's heading
is refused*).

#### An answer typed on another surface counts only through a decision document

A linked answer is only a github.com comment or review, since only there does the `log` command fetch the comment's own text, so an answer typed
directly on Linear or Discord can't be one. An answer typed in the answer
session and relayed to Linear or Discord counts through its answer file (*An
answer given through the answer session counts by its answer file*).

#### Citations go to the lore repository's questions branch

**A lore entry that stops a question gets a citation file on that lore
repository's `questions` branch, holding nothing about the question,** so
even a private question gets one. A categorized question gets none, since the
cited entry would show what it was about. A stopped question is not asked, so
it gets no log file, and its citation is its only record. No log file names a
lore entry by its id either: an answered log file's `recorded_in`, which says
where the answer is recorded, is a path or URL, never a lore entry. This
change defines the one citation format, and igor PR #216 points to it, since
the inquisitor and an Igor both write citation files and igor's review reads
them all. The run's id in a citation is opaque; the Igor records it in the
run's row of its execution ledger on its `igor-state` branch, not with the
transcript, and igor's review shows each citation's run and item (igor
PR #216's decision 10).

**Why:** igor's review, which prunes and promotes lore entries, counts each
entry's citations in one place beside its fire count, and needs nothing about
the question.

*Ruled out by a scenario:* a `cites` field in the log file, which a stopped
question lacks (inquisitor spec: *A lore entry that stops a question gets a
citation file*, scenario *Only the citation file names the lore entry*);
counting raw search hits, which records no reason (scenario *A lore entry the
search shows but that stops nothing gets no citation*); and a hash of the
question in the citation, which the count does not need (inquisitor spec: *A
citation file has one format*, scenario *A citation from a session outside an
Igor's run holds no run id*, which gives its only keys, `entry` and `date`).

#### Questions-branch commits are machine records

The script makes a questions branch's commits itself, with no agent's `git
commit`, so prose's and bug-hunter's checks never see these commits, which carry no trailer (inquisitor spec: *A
question is pushed to the questions branch of what it concerns*). Exempting
an Igor's citation commits from
igor PR #153's trailers is #153's to settle (*What igor must provide*).

#### A citation's commit names no person

Its fixed author and day-only date say nothing about who asked.

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

Filter 1 fetches only the `questions` branch, and reads each clone's default
branch as last fetched, so it does not find a lore entry merged since the
person's last fetch (spec: *A lore entry is read from the remote-tracking
default branch*).

#### Scope hides an entry; status only labels it

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Rationale: Filter 1
hides every lore entry outside the question's scope*.

#### A project scope matches the repository's short name

The requirement that sets this match is *Filter 1 hides every lore entry
outside the question's scope*; the inquisitor's decision record gives its
reason under that requirement's title.

#### Filter 1 searches igor's scribe's records where #202 puts them

**Filter 1 searches the decision records that igor's scribe, the Igor role
that records a discussion's decisions, keeps at the path igor PR #202 sets,
both in the repository the question concerns and in the lore repository.**
A decision record that carries a status, such as a MADR, counts as an answer
only when its status is `accepted`; any other status is shown as input,
wherever filter 1 reads decision records. The inquisitor's decision record,
*Rationale: A lore decision record counts*, gives why filter 1 reads both
places. The spec names no path of its own, only whichever path #202 sets
(*igor-dependent rules state the end state*); *Open Questions* tracks it.

#### A general answer is proposed as a provisional lore entry

The agent opens the pull request without asking first, since a pull request
is itself a proposal and closing it is cheap. During an Igor's run, the run
puts the entry in its report, as it does its question and miss files, and the
Igor opens the pull request, since there the script pushes nothing to a lore
repository and the Igor already pushes the run's other files.

#### A proposed entry's id follows igor's id rules

**Why** the Igor stops on "id taken": igor reports a collision outside the
run's scope only as "id taken", which does not say what holds the id. If an
entry holds it, another id would do; if a rejected candidate, a file under the
lore repository's `rejected/`, holds it, the entry may not be proposed at all.
The Igor cannot tell which, so it proposes nothing.

#### Lessons from misses are drafted on request and land by scope

Misses change the skill only through lessons sent by pull request or memory
edit, never automatically. shared-skills gets only a generalized lesson,
since question and miss logs can hold private content and stay with the
repositories they concern.

### Igor workers and Igor runs

#### The script tells an Igor's run by `IGOR_RUN`

Despite its name, Igor-worker mode is how the script runs in any Igor's run,
including one the Igor starts itself with no worker. Only the `IGOR_RUN`
value `worker` limits filter 1's sources other than lore to the worker's
working tree. igor PR #216 sets the variable (at ba154a0). A plain headless
session such as `claude -p` has no such variable and searches lore as usual
(scenario *A headless session without IGOR_RUN searches lore*). The script
matches `IGOR_RUN`'s exact name and value (the inquisitor's decision record,
*Rationale: The script tells an Igor's run by IGOR_RUN*).

**During an Igor's run, the repository of the run's item is the one a question
concerns when the agent cannot tell which it is about.** A question with a
category raises igor's flag on the whole execution on the item, not one
worker's part of it (igor PR #216's decision 22).

**The script says so whenever it acts on the variable,** because a repository
can set it in a person's session, through committed Claude Code settings or
an `.envrc`; lore would then go unsearched and nothing logged to a lore
repository, and without the message the person could not tell why.

*Ruled out by a scenario:* treating every session with no person in it as
possibly in an Igor's run (inquisitor spec: *The script tells an Igor's run by
IGOR_RUN*).

#### An Igor worker asks only in its handback comment

The Igor posts the handback comment (igor #211). The worker opens no post and
calls no picker, even if task 0.14 finds a `gh` login in its reach.

**Why:** igor gives a worker no credential that can post (the inquisitor's
decision record, *Rationale: A session with no person in it asks in a post,
a handback or nowhere*). A `gh` login a worker can still reach would breach
igor's rule, so the worker does not use it, and task 0.14 reports it.

#### Filter 1 in an Igor's run searches through `igor lore-search`

`igor lore-search` is specified by igor PR
[#216](https://github.com/adamstallard/igor/pull/216) (its decisions 23, 49
and 52), whose decisions igor issue
[#215](https://github.com/adamstallard/igor/issues/215) also holds. #216
amends igor's lore-firing spec: lore still reaches the worker unbidden, the
ban on offering a worker a search tool, which rested only on a worker not
needing one, is lifted, and a run's search applies firing's scope rule and
labels an in-scope non-`active` entry as not lore.

**Why** a worker searches at all: an entry holding a person's answer can be
missing from the lore igor injects (the inquisitor decision record's
*Rationale: In an Igor's run, filter 1 searches through igor* gives why).

**Why** only the lore repository the Igor injects from: the Igor checks a
cited entry, reported by id alone, against that lore repository; another
one's search could find an entry the Igor refuses, or one it takes for a
different entry with that id.

**Why** both searches match alike: the same entries then rank alike inside
and outside a run.

#### The Igor reads questions branches by running the script

**During an Igor's run, the Igor searches the item's repository's questions
branch and its lore repository's by running the inquisitor script's
`branch-search`, and passes the JSON it prints to the worker over the
channel `igor lore-search` uses.** One channel then carries everything from
outside the working tree. The JSON is the contract between shared-skills and igor, and task 2.3b's test holds it steady. The inquisitor decision
record's *Rationale: The Igor reads questions branches with the script*
gives why the Igor runs the script and the worker does not.

#### Questions-branch files and `project:` entries in a run's search

The scope rules for lore entries are igor PR #216's (decisions 44, 53 and
54); the spec points to them. For a questions-branch file the script applies
this change's two run rules itself, on a file about another repository and
on visibility, given the run's item (*The Igor reads questions
branches by running the script*). A `project:X` entry is hidden in a run whose item's
repository is more visible than X's repository (decisions 53 and 54), so the spec's
scenario of a `project:` entry inside an Igor sets the item's repository no
more visible than X, or it would test nothing.

**Why** visibility limits what a run sees: a worker could otherwise repost
what it read about a private repository into a more public item.

**Why** a file about another repository is input in a run: *Every
questions-branch file names where it was asked from* gives the reason.

#### Every questions-branch file names where it was asked from

**Every questions-branch log and miss file but a handled or hash-only one
holds
`asked_from`, the repository the question was asked from. Outside an Igor's
run the script writes it. During a run the script writes none: the Igor
sets it after its format check, and refuses a worker's file that already
has one (#216's decision 42).** This change owns the file format, so
`asked_from` is among its keys, and readers judge visibility as #216 does,
from the more private of the keys a file holds.

**Why** no worker writes it: a worker steered by its item could write a
public `repository` on a file about a private repository; `asked_from`
still names the private one, so the question cannot be laundered. Outside a
run, the writer of `asked_from`, the script or the answer session, already
sets `repository`, so setting `asked_from` too gives it no new way to
mislead.

**Why** a collective's question names where it was asked: it concerns no
repository, but its visibility and its team's lore repository still come from
the work that raised it (spec: *A collective's question is bounded by the repository it was asked from*).

**Why** a run's file can name another repository: the item's repository is
only the default for a question the agent cannot place, and a question
clearly about another repository is filed with it, as #216's decision 33
allows. During a run such a file is only input (*Questions-branch files and
`project:` entries in a run's search*), so a steered worker makes no answer
count.

#### The flag a worker raises for a question with a category

The flag holds two lists: each category met in the run, as one of the three
words, and a marking of those that belong to the questions the run stopped
on. It holds no question or answer, and the lists never say which stopped
question had which category. The Igor accepts a word only when it is exactly
one of the three, and writes the words only into its operator-only file on
its host (#216's decision 89), never into the execution ledger, the state
branch, a comment or a label. The Igor moves the run's session logs, which
hold the question's text, next to that operator-only file (#216's decisions
88, 89, 97 and 98), and writes no other copy of the run's text. Each worker
run reports its own flag, and so does each model step igor PR #153 runs
after the worker (#216's decisions 60 and 64).
How the Igor stores the flag is #216's (decisions 92, 97 and 100).

*Ruled out by a scenario:* a word per question, which tells the Igor how many
questions of each category stopped the run; and only the stopped questions'
categories in a fixed order, which leaves out one met but not stopped on
(scenario *The flag lists each category once and marks the stopped
questions'*).

#### A flagged run asks nothing and pushes nothing

A flagged run is one whose worker reported the flag, or that ended without
the worker's completed report (#216's decisions 19 and 38). It pushes nothing
to the `questions` branch, citations included, and its question stays on the
Igor's host. The Igor's handoff, the operator file that holds the question,
and how the item is released are igor PR #216's (decisions 73, 75, 76, 79 to
85, 88, 89, 95, 97, 98, 100 and 101 at d3b7740); this change reads nothing
from that file.

#### The Igor pushes the questions-branch files its worker reports

igor PR #216's requirement *An Igor publishes the questions-branch files its
worker reports* holds these rules for both changes, save one it must still
adopt (*What igor must provide*): the Igor pushes a file about a repository
to that repository's questions branch. It pushes one about a collective to
the team's lore repository's. It pushes only an unanswered question file or a miss file, each
only at a path not already on the branch (decision 21); every file
passes igor PR #217's credential matcher, which matches known secrets'
values such as the seat token (decision 28); and it reads the lore
repository's visibility at every push (decision 37). This change also needs
a person's answer to a handback pushed, which #216 does not handle as this
change has it (*What igor must provide*).

#### A person's answer to a handback

**The Igor pushes a handback answer's log file only when its question matches
a question the Igor posted in the handback comment that the person's comment
answers.** A question matches when its hash, after this change's reduction,
is in the Igor's record of the handback (*A later run names the answered file
from the Igor's record*; #216's decision 41), never by the comment's current
text.

**Why:** a worker steered by its item could otherwise pair a real comment
with another question, and anyone who can edit the comment could change its
text.

#### A worker logs no answer

**Why** a worker writes none: it reads no comment, so any answer it wrote
would be its own paraphrase, and it could not check the writer's access to
set `authority`.

#### A later run names the answered file from the Igor's record

The Igor keeps one record of each handback: the hashed record of handback
questions that igor PR #216, still open, is asked to keep in its decision 59;
a builder relies on it only once #216 merges with decision 59 in it. For each question it
posted, the record holds the 6-hex-digit suffix and date from the name of the
log file it pushed, and the question's hash, but no question text. The run
finds the file by the suffix and date.

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

**During an Igor's run the agent pushes no citation itself; igor PR #216's
lore-firing requirement *An Igor publishes the citations its worker reports*
holds every rule for a run's citations,** since igor has a worker edit and
its Igor publish, and a worker holds only its seat's token, the one
credential igor leaves in its environment. In brief, the
Igor pushes a run's citations only when the run publishes, a handback comment
counting, as bookkeeping that needs no action from the role's `allow` list
(the closed set of actions, such as `comment` or `pr`, igor's role
configuration grants a role), and only of
existing `active` entries in the role's scope. The channel a worker reports
them through, output or outbox, is igor PR #175's, which runs a worker as a
separate Unix user.

The citation count igor's review shows is not exact, since no citation goes
where it would show a more private question exists.

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Rationale: A lore
entry that stops a question gets a citation file*.

#### igor-dependent rules state the end state

The rule this heading names is the inquisitor decision record's entry
that the *Recorded:* line below names. What igor must provide is listed
under *Open Questions*. A clause that guards against misuse in igor's end
state is still written, such as:
- a log file with no matching record of the handback writes no `answers`;
- an `igor lore-search` call that fails searches no lore;
- a handback-marked post is vetted like any other (*No exemption for an
  Igor's handback*).

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Constraint: A rule that
depends on igor states its end state, …*.

#### Alignment with igor PR #216

**The spec states igor PR #216's rules where they touch this change, and
points to the rest,** such as the Igor's `authority` and `answered_by` for a
handback answer. *What igor must provide* lists where this change
departs from #216.

### Answer-session configuration, setup and relay identities

#### Setup is part of the answer session

**Setup runs inside the answer session: in place of the queue while the
top-level `login` or the `answer_session` section is missing or no surface in it has both a `relay` and
a subscription, and again on `/answer setup`.** How setup looks is prototyped,
not specified.

#### A failed relay check turns off only its channel

**A relay check that fails turns off only the channel it checked; the
person's other channels stay on.** Where no check can read a relay identity's
right to post, the first refused post turns the channel off (spec: *Setup
checks each relay identity before its channels are used*).

#### Setup checks direct pushes, and can create a lore repository

**Setup checks that each `questions` branch takes the person's direct push,
and asks for no protection of the branch.**

*Recorded:* `openspec/specs/inquisitor/decisions.md`, *Constraint: Anyone
with write access to a repository can rewrite or delete its unprotected
`questions` branch*.

**Setup can create a lore repository, as a step the person may skip, for a
team that wants its collective's questions recorded.** It creates
only what the inquisitor owns: the repository, at the visibility the person
picks, its clone and the person's configuration entry. It writes nothing in
igor's entry format, so the step needs no igor. The `lore` command does copy
igor's entry format when it proposes an entry, and a test pinned to an igor
commit checks that copy (task 2.8).

#### Discord is in the first version, through discord-bot

**Discord is in the first version, through the `discord-bot` skill of
shared-skills PR #1, merged,** because it gives each role a named bot
identity with no service to run.

#### On Discord one identity both reads and relays

**The answer session reads GitHub and Linear with the person's own `gh`
login and Linear key.** On Discord the relay identity both reads and
posts, in the channels it has been added to; the answer-session decision
record's *Rationale: The answer session reads with the person's credentials,
except on Discord* gives the reason and its evidence.

*Ruled out by a scenario:* a second Discord identity reading as the person
(answer-session spec: *The answer session reads with the
person's credentials, except on Discord*, scenario *Discord is read by its
relay*).

#### The Discord relay needs the Message Content intent

**The Discord relay needs Discord's privileged Message Content intent.** The
answer-session decision record's *Rationale: Setup checks each relay
identity before its channels are used* gives why, with the evidence.

#### Only the prefixes are reserved, not the identity

*Ruled out by a scenario:* keeping a relay identity for the answer session
alone: the prefix marks a relay post, and nothing reads a relay identity's
other posts (answer-session spec: *Relay posts start with a reserved prefix*,
scenario *A relay identity's post without a prefix is not read*).

#### An answer given through the answer session counts by its answer file

**A relay post counts for nothing in filter 1, on GitHub, Linear or Discord:
an answer the person gave in the answer session counts through the answer
file the session pushes.** The
session pushes it to the questions branch of what the question concerns, so
an answer to a repository question counts as a decision whichever surface it
was given on. No committed file lists a person's bots, and no reader has to
learn which App wrote a comment. The relay post's URL is the file's
`answer_link`, which off GitHub is never fetched.

*Ruled out by a scenario:* counting a `User says: ` comment by its author
(inquisitor spec: *An agent logs a bot's comment or a message off GitHub only as input*,
scenario *A User says comment with no answer file is input*); and counting
every answer relayed off GitHub as input (answer-session spec: *A
questions-branch answer file records the answer as given*, scenario *A log
file of a Discord-relayed answer is a decision*).

#### github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity

**github-app's `token`, `run`, `credential get` and `wire` commands are to
refuse an identity marked as a relay, so a relay's token reaches no program
but `gh`, whose posts the post hooks see.** This change asks github-app for that and ships
without it.

**Why:** a relay App's `User says: ` post marks a question answered for the
person and the asker, so nothing should post through it unseen.

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Constraint: The
inquisitor's GitHub post hook and the refusals asked of github-app for a relay
identity guard against accidents, not against an agent set on forging a
relayed answer, which can read a relay's credentials from the keychain and
post with `curl`* and *Constraint: Until github-app refuses `token`, `run`,
`credential get` and `wire` for a relay identity, any agent on the person's
machine can print a relay App's token and post `User says: ` with a plain HTTP
call no post hook sees, and the README says so*. Task 5.2 writes that README
section.

### Running the answer session

#### The answer session polls, only while it is open

**The answer session polls about every 60 seconds, only while open, and uses
no webhooks** (*Polling while open, with the person's credentials*).
At each poll it fetches the questions branch of every subscribed repository
and configured lore repository, and each subscribed repository's default
branch, a subscribed repository's into a clone of its own that the state
folder keeps and a lore repository's into its configured clone; filter 1 searches decision
documents only there, and names any other repository's as not searched,
since the session holds no clone of it. Unless task 0.15 shows notifications
report every GitHub message the session needs, it also reads each subscribed
repository's new issues and pull requests, their comments, reviews and
review-thread comments, and the review requests and assignments naming the
person, so a question of any source is found if notifications miss it.

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Rationale: Until
notifications are measured, the poll reads every GitHub question source*
and *Rationale: The answer session polls only while it is open*.

#### Local state is per machine, in the state folder

**The state folder holds working state, not a record: the thread and the
questions branches stay the records.** A discussion record, the folder's copy of
the person's discussion of a question with the session's model, is deleted
once its question is answered, handled or closed. So the state folder is not
the personal question log that *Every asked question is logged with what it
concerns* rules out.

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

**The lock makes one session the sole writer of its machine's state**
(*Local state, one writer per machine*): one state folder holds the machine's
owed pushes, pending answers and poll positions, and two answer sessions
would poll, post and push twice. The session holding the lock checks it by
its session id, not its name, because every session the `answer` command
starts is named `Answers`.

#### Two commands open the answer session

**The answer session opens with `/answer` in any session, or with the
`answer` terminal command that setup installs; no environment variable opens
it,** because a session an app starts from its session list, with no
terminal, cannot set one. `answer` starts Claude Code in its fullscreen
layout, with the tool restriction task 0.34 finds; `/answer` opens the
answer session in whichever layout the session is in, and only where Claude
Code restricts that session's tools (*The session's model has no shell, no
writing tool and no web fetch*).

*Recorded:* `openspec/specs/answer-session/decisions.md`, *Constraint: Nothing is designed or built for the answer session outside Claude Code's fullscreen layout*.

#### A discussion runs in the session's own conversation

**Why:** the person opened the conversation to talk the question through, and
the model reads before it replies, while a picker would hide the answer
session's screen. So a question the model asks back is the one exception to
the rule that an agent asks only through the picker.

#### The session's model has no shell, no writing tool and no web fetch

**In the session where the answer session is open, the model has only its
conversation, `propose_reply` and read-only file tools, and Claude Code, not
a hook, enforces that.** The threat is a crafted message in a subscribed
channel steering the model into posting, or recording a decision, as the
person. The answer-session decision record's *Rationale: The session's model
has no shell, no writing tool and no web fetch* gives why hooks cannot stop a
model with a shell, and why web fetch is left out. Whatever the model is
steered to do, the most it can do is draft a reply the person sees before
anything is sent.

**The answer session's own code does every post, `log` call and push, and
every fetch from a surface.** It posts each confirmed answer as a host
command (*What the answer session posts, and what it logs*), so the person's
confirmation, not a hook, is what lets an answer out.

**Which tools, and how the thread reaches the model, are still open** (*Open
Questions*). Task 0.34 measures how Claude Code restricts a session's tools.
If it offers no control that Claude Code itself enforces, the design would
fall back to hooks, and the change cannot be built as written.

**No hook checks where a relay post goes, and the person is accountable for
what any agent posts as their relay** (answer-session spec: *The person
answers for what their relay posts*). An agent in another session may post
as a relay without a prefix; such a post does not count as the person's
answer, but it appears under an identity tied to them, and a hook sees the
post and where it goes, but not which thread its text came from, so it
cannot tell whether private text is leaking.

#### Claude drafts a reply only into the prompt box

**Claude's draft lands in the prompt box for the person to edit and confirm,
and posts nothing.** Since the person confirms whatever Claude drafts, when
they decline under filter 1 the draft may fill in the URL of the record that
answers the question.

**`propose_reply` refuses any call carrying an `agentId`, and takes a call
without one as the main conversation's.** The spec takes it that Claude Code
sets `agentId` on every tool call made outside the main conversation, by a
subagent or by a side conversation Claude Code forks; task 0.26 checks both.
A forked side conversation, such as the one that guesses the next prompt,
could otherwise drop an unasked draft in the prompt box, possibly over what
the person is typing. The answer-session decision record's *Rationale: Claude's
draft goes to the prompt box, never to a post* gives the reason a
subagent's call is refused, and the evidence.

**The model writes each draft for whichever is more public: the thread's
readers or the readers of the question's repository** (answer-session spec:
*Claude's draft goes to the prompt box, never to a post*). **Beyond that, a
draft's privacy is the person's to judge:** they read each draft before
confirming it and decide whether its wording suits where it posts. The
answer session checks a draft only as it checks every relay post, scanning
it for credentials (answer-session spec: *A relay post is posted by a host
command, unvetted*). For a filter 1 decline, the preview also warns when the
record the draft links to is more private than the thread (answer-session
spec: *The preview warns when a filter 1 record is more private than the
thread*).

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

The thread is fetched again before each relay post, so an answer relayed from
another machine is posted twice only when both post before either fetches. On GitHub, recognising a relay post by
the App that wrote it is built only once task 0.21 is measured (answer-session spec: *Relay
posts start with a reserved prefix*); until then no relay posts on GitHub,
and this section does not apply there. A relay post names its question by its
`Re: ` line on GitHub and Linear, and by replying to it on Discord.

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

The answer session posts with discord-bot's mention rewriting on, which makes
an `@name` in the answer ping that member, as in a comment of the person's
own. After each relay post or edit, which can drop a ping, the person sees
discord-bot's warnings, such as for an `@name` that pinged no one. An
automatic `Recorded answer: ` post links its record and quotes none of it, so
no relay post repeats a record's @-mentions. The relay posts with no header,
which is discord-bot's default (the answer-session decision record's
*Rationale: An answer is relayed as the person's words*).

*Ruled out by a scenario* (answer-session spec: *An answer is relayed as the
person's words*): mention rewriting off, which only stopped a quoted record's
@-mentions notifying again, and no post quotes one (scenario *A Discord relay
post has no header and pings whom the person names*); and failing setup on
`memberSearch: false`, since the warning at each post tells the person
(scenario *Refused member search does not fail setup*).

#### The person can ask the asker

**Asking back is mostly for people's questions:** an Igor's worker asks in its
handback comment and is gone, so a reply reaches whichever worker next takes
the item.

#### Editing a relay post

Editing an automatic post turns it into the person's words, starting
`User says: `, because the person confirmed its new text. An edit pushes a
new log file, since a questions-branch file never changes and the branch
would otherwise keep the first answer; *The newest answer counts* says
which file counts.

#### A rephrased answer carries its rephrasing

The answer file's answer is the relay post's whole text, its `Rephrased
question: ` and `Discussion: ` lines included, and the file's
`## Rephrased question` and `## Discussion` sections hold the same two
texts.

*Ruled out by a scenario:* new frontmatter keys for the rephrasing, since
every frontmatter value is one quoted line and a question's text is not
(scenario *A rephrased question's log file holds the rephrasing*).

#### A questions-branch question is answered by a new log file

**Why:** the questions branch never changes a file once pushed. Where the
file's `asked_in` links a post that also asked the question, the answer is
both relayed and pushed, so neither the asker reading the thread nor an
agent searching the branch misses it.

#### An answer file records the question the person saw

**An answer to a linked message records the message's question as the person
saw it, not the question the log file holds,** because otherwise a log file
whose `asked_in` points at an unrelated message would get the person's
answer recorded, as a decision, against words they never saw. The preview
shows the person where that question will be recorded before they confirm
(*Nothing goes somewhere more visible than its source*).

#### An answer file names the file it answers

**An answer file names the one file it answers in `answers`, because
answering every file with the same question is matching on words, which
exact identity replaces.** igor PR #216 is asked to refuse a worker's file
holding `answers`, so that the Igor adds the key itself and #216 pushes only
what the Igor writes; *Open Questions* carries that request.

*Ruled out by a scenario:* keeping hash matching beside `answers`, which
gives machines different answers (inquisitor spec: *A named file's answer is the newest answer file naming it*, scenario *An answer naming one file
does not answer another with the same question*).

#### The newest answer counts

**A file is as new as the commit that added it, in the branch's commit
order** (spec: *A file is as new as the commit that added it, and supersedes
only if it would count*). If a file that would not count could supersede,
a person without write access, whose answer to a handback an Igor logs as
`input`, would undo a maintainer's answer.

#### `answers` decides a named file's answer; the search groups by hash

**Why both:** a later asker has no file of its own to name, so the search can
find earlier answers only by hash. An answer file is *replaced* when a newer
answer file names the same questions-branch file in `answers`. A replaced
answer file stops counting even in its own hash group, or the person's
changed answer would not be the only one that counts.

**Why** a replaced file still supersedes the older files in its hash group:
the person's newer answer marks the older ones in that wording stale, so
asking again is safer than reviving one, even when that leaves the group with
no answer that counts.

*Ruled out by a scenario:* the older files in a replaced file's hash group
counting again (inquisitor spec: *A replaced answer file stops counting even
in its own hash group*, scenario *The newest answer naming a file counts*).

#### A named file's answer must be the person's own

An answer file answers a named file only when its `answered_by` is the
person that file's question tags, since the question was put to that
person. A file that tags no one gives no person to compare with, so any
account with write access to what its question concerns may answer it.

*Ruled out by a scenario* (answer-session spec: *The person's answer to a
named file is their own*): letting a file that tags no one be answered
only by a matching hash in filter 1's search, never through `answers`
(scenario *A file that tags no one is answered by an
account with write access*).

#### A named file stays shown until its answer counts

*Ruled out by a scenario:* letting any answer file hide the file it names
(answer-session spec: *An unanswered log file holds no answer the person
gave*, scenario *A log file named only by an input answer file is
unanswered*).

#### `answer_link` and `asked_in` are withheld where they would leak

**Why:** the URL would point the readers of a more visible questions branch
into a more private thread. A Discord URL holds the server's and channel's
ids, a Linear URL the workspace and issue key, and a github.com link into
a more private repository leaks the same way. A file that holds a Linear or
Discord `asked_in` counts as private.

An answer's text leaks as its link does. So where the questions branch is
more visible than the thread an answer was given in, an answer file is
written only once the person confirms the preview's warning, and then with
no link into the thread: the relay post's last line, `Re: ` and a URL into
the thread, is dropped from its answer. Without that confirmation neither
the answer nor its file goes out; the person can reword it to suit the more visible place, and then
confirms (answer-session spec: *No answer file goes
somewhere more visible than its thread unconfirmed*).

Into a Linear or Discord thread, whose readers the session cannot check, the
session posts a recorded answer automatically only when its record is in a
public repository; a more private one is shown and posted only once the person
agrees after a warning, as for a record more private than a GitHub thread.

*Ruled out by a scenario:* always writing the URL, accepting the leak
(inquisitor spec: *The log command withholds a link where it would leak*,
scenario *A GitHub link into a more private repository is left out*).

#### An answer that cannot reach its thread is kept pending

A failed post keeps its answer pending rather than leaving the question as it
was, which would drop the answer the person typed.

**Pending answers are kept in a separate pending list that reuses the main
queue's screens,** which spares the list a prototype round. A pending answer
returns to the queue when setup's recheck of its channel passes. An answer no
check brings back, such as one refused for its text, can stay on the list
indefinitely, since the person can always post, edit or drop it. The
person's other machines read only the thread and show the question again
(*Which cross-machine cases are accepted*).

*Ruled out by a scenario:* returning an answer no check brings back to the
queue at the next opening (answer-session spec: *A pending answer no check
returns waits for the person*, scenario *A text refused for its length stays
pending after a recheck*); and an "Answered on another machine, not relayed"
notice on other machines, offering to relay, edit or answer afresh, even only
for a file linked by `asked_in` (answer-session spec: *Only the person is told
an answer is pending*, scenario *Another machine asks again while an answer is
pending*).

#### The push order for a questions-branch answer

**The answer session checks the thread, records the owed push, posts, then
pushes the answer file with the post's link as its `answer_link`.** The file
follows the post, its push retried at each poll and opening, so no thread is
left answered with no file. Recording the owed push before the post means a
crash between them does not lose the answer file. Checking the thread first
lets the person see a new message before anything is pushed. An answer
pushed at once, while its channel is off or not subscribed here, is recorded
as an owed push too, with no post's link, so a push that fails for a passing
reason is retried like any other.

A retry stops when another answer file on the branch already counts as the
person's answer and names the same questions-branch file, but only if this
machine first saw that file at a fetch after recording the owed push. So the
machine's own earlier file, pushed at once while the answer's channel was off
(*An answer whose thread is unreachable here is logged at once*), cannot
cancel the push of the edited answer's file: if "Use Postgres" was pushed at
once and the person's edit "Use SQLite" is posted later but its push fails,
the "Use Postgres" file does not drop the retry.

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
- accepting a thread answered with no file (answer-session spec: *A
  questions-branch answer's file is pushed after its post*, scenario *An
  owed push survives a crash*);
- any machine pushing an answer file for a relay post it finds without one
  (same requirement, scenario *A machine that owes no push pushes no file
  for a relay post*);
- a dropped pending answer pushing a handled file (answer-session spec: *A
  handled file closes a questions-branch question*, scenario *Dropping a
  pending answer pushes no handled file*);
- the `log` command keeping a pending copy of a file the answer session
  pushes, beside the session's own retry (answer-session spec: *The answer
  session's owed push is its only retry*, scenarios *A push that failed for
  a moment leaves one answer file* and *A push refused for lack of access
  is never pushed later*).

**The answer session's retry is the only one for its files.** Were the
`log` command to keep a pending copy too, a passing failure would give two
answer files: the session's retry would push one, and the next `log` call
the copy. After a refusal the person was told was final, the copy would
still be pushed. The `log` command learns that the answer session is
calling it from an option only the session passes. An ordinary agent keeps
the pending copy, since it has no other retry.

#### What the answer session posts by itself

**No automatic post holds a word the session's model wrote, or quotes an
answer** (*What the answer session does by itself* gives why). A log file's
answer is a whole comment, which could hold @-mentions that would notify
people again on GitHub, or a `Recorded in: ` line of its own. An automatic
post's text is fixed but for the record's URL, so it gets no prose pass and
no vetting.

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

**Only an agent's question gets an automatic `Inquisitor: ` reply, so any
doubt counts a question as a person's: no person then gets a reply nobody
wrote.** The answer-session spec defines both kinds. A questions-branch log
file counts as an agent's.
An agent's question posted with a person's own credentials counts as a
person's, since the answer session cannot tell the two apart. A relayed
question, a `User asks: ` or `User says: ` post by a bot account, is a
person's, though which person cannot be proved.

#### Filter 1 runs on every incoming question

**Filter 1 runs before the person sees any question, a person's or a relayed
one included.** Filter 1's answer by itself to an agent's question logs a
miss, because the asking agent's own filter 1 should have found the record.

#### Filters 2 to 4 judge every incoming question

**The session's model fails a question on filter 2, 3 or 4 only when the case
is clear, and replies by itself only with that filter's fixed text, and only
on an agent's question.**

*Ruled out by a scenario:* only suggesting a verdict, so the person handles
every deferrable or cheap agent's question by hand (answer-session spec:
*Filters 2 to 4 judge every incoming question*, scenario *A deferrable agent's
question is handled for the person*).

#### A question another skill requires carries a line the answer session matches

**A posted question that another skill requires a person to decide carries
the person-required line, `Inquisitor: a person must decide this (required
by <skill>).`, which the second call prints and the agent copies exactly; the
answer session finds it by its fixed wording and always shows such a question
to the person, never replying with filters 2 to 4,** even when the person
declines it, since the requiring skill wants the person's own answer. Filter 1
still applies, as it does for the asking agent. The inquisitor spec's *A
question another skill requires carries a person-required line* and the
`answer-session` spec's *A question with a person-required line gets no
filter 2 to 4 reply* state the rules. On GitHub the post hook checks that the
line is there on each such question, names the right skill, and is on no other
question; elsewhere nothing checks it.

**Why:** the asking agent skips filters 2 and 4 for such a question. It
has already run filter 3, knowing which options the requiring skill lets it
take itself; the answer session cannot see those options. If the answer
session applied filters 2 to 4, it could close by itself a question only a
person may decide. The line is visible text, since Linear and
Discord have no hidden comments. It starts `Inquisitor: ` like the session's
own fixed texts, but sits after the question, since a post starting
`Inquisitor: ` is blocked on GitHub as a reserved prefix. The script prints
it, so its wording never varies and finding it needs no judgement.

The answer session matches the line's fixed wording after reducing it as a
question's text is, and ignores the skill it names, so markup a surface adds
does not stop a match; task 0.28 checks that Linear and Discord return the
line's words unchanged.

*Ruled out by a scenario:* keeping the automatic reply on such questions
(answer-session spec: *A question with a person-required line gets no filter 2
to 4 reply*, scenario *A question spec-trace requires reaches the person*);
and applying filter 3 again to them (scenario *A marked question that seems
to fail filter 3 reaches the person*).

#### A reply to an automatic post is a new question

**A reply to an automatic post is judged by the filters again, like a reply
to any relay post, and a repeat within its chain of replies goes to the
person** (*No automatic post repeats one in its chain of replies*).

#### What an asking agent does with an automatic reply

**An agent acts on an `Inquisitor: ` reply, one the answer session posted by itself included, only when a miss file backs it.** The reply's own text and author
count for nothing: commenting on a public repository is open to anyone, so
without the file anyone could post `Inquisitor: filter 4` and have an agent
decide a maintainer's question. Pushing to the questions branch takes write
access. A readable miss file names in `said_by` who stands behind the reply,
and the agent checks that account's write access, since a readable miss can
be pushed for someone else, as an Igor pushes its worker's.

**Where privacy would withhold a readable miss, the session pushes a
hash-only miss file.** A miss file that backs a reply, readable or not, is
named by a hash of the surface and that reply's own message id: the name is
only a lookup key, and the file authorizes one thing, a particular reply,
which its id identifies exactly. The session posts the reply, takes its id
from the surface, then pushes the file; the asking agent hashes the id of
the reply it sees and makes one path lookup, whichever kind the session
wrote. No question text is hashed, so nothing a surface or a posting skill
changes in a message's text can break the lookup. A forged `Inquisitor: `
post is another message with another id, so no file matches it. An earlier design named the file by the asking message
and the filter; where one comment holds several questions, a forged reply
about another of them, naming the same filter, would have matched. The agent
looks on the questions branch of what its question concerns. For a collective's question asked on Linear or Discord, it also
looks on every lore repository in its configuration. The asking agent picks
a lore repository from the repository it works in, while the session picks
by its model's judgement. A file on a branch the agent never checked would
leave the reply input while the session listed the question as handled. The
reply's id names one file, so a match on any branch is that reply's miss.
Finding none, the agent looks three more times, a minute apart, since the
session pushes the file just after the reply. A hash-only miss file has empty frontmatter and no
body, so it shows nothing but the time of its push and who pushed it. A hash-only file holds no `said_by`: being on the branch is its authority, since only an account
with push access can put it there, and only an answer session writes one. For a collective's question that
branch is the lore repository's, whose writers are who decides such a
question. A readable miss stays the form wherever privacy allows one, for
its value as a log. Where the session has no questions branch to push a miss file of either form
to, the
session posts no reply by itself and shows the person the question, so an
agent never acts on a bare reply.

An agent pushes no citation for a lore entry a `Recorded answer: ` reply
names, since the answer session pushed any that was due, so one question
gives one citation.

#### Two reasons to decline

**The person declines under one of two reasons, nothing to answer or the
inquisitor should have handled it; under the second, the person, not the
session's model, picks the filter and sees the exact post before it goes
out.** The answer-session spec holds both reasons and what each posts, logs
and closes. The second applies to people's and agents' questions alike,
since the person chose it. How the confirmation looks is prototyped (task
6.9). The person can still answer on the surface by hand. Reason 1 is named
"nothing to answer" to keep clear of filter 3's text, "not a real question".

*Ruled out by a scenario:* the session's model asking the person which filter
should have stopped the question, and why, since the person picks the filter
and confirms its reply instead (answer-session spec: *Declining for
the inquisitor posts the picked filter's reply*, scenario *The inquisitor's
reply is posted once the person confirms it*).

#### Messages that are not questions are ignored

**Only messages of the answer session's first two sources, one mentioning
the person and one mentioning their relay or replying to a relay post, are
judged for being questions. A non-question from the other two sources, a
review request or assignment and a questions-branch file, reaches the queue
unjudged.** "Rhetorical" is not a category: an asking agent rewrites a message
that is not really a question as a statement, so an agent's rhetorical
message gets no post.

A non-question that reaches the queue is declined under reason 1 when the
answer session's own judgement let it through, logging no miss since no asker
erred. When the asking agent should not have written it, it is declined under
filter 3's "the agent shouldn't have asked", which logs a miss against the
asking agent and posts nothing, since filter 3's fixed text tells the agent
to take an option with merit, which a non-question lacks. The question as the session shows it from its thread, a thread
copy (spec: *A thread copy is a question shown from a thread*), can later be
reopened, and the miss is kept even then (*Reopening a declined question*).

*Ruled out by a scenario:* filter 3's automatic reply on a rhetorical message,
or a rhetorical fixed text of its own: filter 3 is for a real question that
did not need asking, and the decline reasons and filters 2 to 4 cover a
question that needs no answer (answer-session spec: *Filter 3 also offers that
the agent shouldn't have asked*, scenario *The agent shouldn't have asked
posts nothing*).

#### Declining with nothing to answer closes only that question

**A reason 1 decline closes only the declined question; every later message
in its thread that a source names is a new question on every machine.** The
decline is held in each machine's own state folder, so if it stopped later
messages counting, a follow-up would count on one machine and not on
another. A decline under the second reason resolves its question too: its
post, or this machine's close where nothing was posted, marks it handled, so
a later message is a new matter.

*Ruled out by a scenario:* a threaded reply reopening the declined question on
one machine, or dropping a reply that arrives after its question closed
(answer-session spec: *Later messages after an answer or a decline are new
questions*, scenario *A later message in an answered or declined thread is a
new question*).

#### The answer session writes a handled file on every close of a questions-branch file

**Whenever a decline, a recorded answer or an `Inquisitor: ` reply takes out
of the queue a question a questions-branch file holds, a handled file naming
that file is pushed; without it, the file would stay unanswered and be shown again.** A machine's first poll of a channel reads only its last 14 days, so a
machine first polling more than 14 days after the question was asked never
reads the thread copy, the same question in the thread the file's `asked_in`
links, and would show the file as new.

The answer session writes the handled file itself, since an asking agent
could not tell who wrote the closing post.

A handled file adds no question text: the closed file's name, which it
repeats, is already on the same branch. So it never carries a private item's
question into igor's lore search, and shows nothing the closed file does not.
An Igor worker could still forge a handled file and report it for its Igor to
push; igor refusing to push one is asked of igor PR #216, and is open on its
side.

A close that cites a record, a filter 1 decline or a `Recorded answer: `
post, takes the question out of the person's queue whether or not the
asking agent's own filter 1 would count that record: the record is then in
the thread, and an asker that cannot count it and asks again reaches the
queue as a new question.

**A reader takes a handled file, which names no person, as the answer
session's,** as it takes an answer file at its word. The
inquisitor decision record's Constraint on a rewritable `questions` branch
gives what that costs.

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

**Closing never compares question hashes, the repositories questions concern,
or times: a
handled file closes only the file its `closes` key names, and a thread copy
closes only by the relay posts in its thread, or on one machine by a decline
with nothing posted.** Matching on a question's words, on a topic
repository, which each machine's model judges for itself, or on clocks can give two machines different
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

**Only a thread copy declined with nothing posted can be reopened, and only
on the machine that declined it,** even after a handled file closes the
questions-branch file. After a post, the thread, which every machine reads,
records how the question was handled, and the person changes that by editing
the post. A handled file closes the file it names on every machine, for good;
a thread copy is separate from that file.

A decline under the second reason that posts nothing on a thread copy, such as
filter 3's "the agent shouldn't have asked", is the one reopenable decline
that logs a miss. If the person reopens the question, the miss stays: a miss
file never changes, and nothing records that the person took the decline
back. Misses feed *Lessons from misses are drafted on request and land by
scope*, so a miss is not held back on the chance of a reopening.

*Ruled out by a scenario:* reopening a question on this machine whatever its
thread shows (answer-session spec: *Only a thread copy declined with nothing
posted is reopened*, scenario *A question declined with a post is not
reopened*).

#### A person's cite pushes a citation file

**A person's cite follows the rule of filter 1's own citation and igor
PR #216's: a citation file only for an `active` entry in scope, and one per
question.** A citation file's push, the answer session's own included, is
recorded as owed and retried as a miss's is (*Misses the answer session
logs*). Widening #216's definition of a citation is under *What igor must
provide*.

*Ruled out by a scenario:* pushing a decline's citation only when its miss is
pushed (answer-session spec: *A filter 1 decline cites its lore entry once*,
scenario *A decline's citation is pushed when no readable miss is*). When two
machines decline one question, each pushes a citation, so the entry is cited
twice, which *Which cross-machine cases are accepted* accepts.

#### Agreeing to a recorded answer is a filter 1 decline

**Agreeing to a shown recorded answer is a reason 2 decline with filter 1
naming that record, on every question, so the decline path does the rest
and no answer log file is pushed.** The record exists and filter 1 found it,
so a log file pointing to it adds nothing; a later searching agent is
stopped by the record only if its own filter 1 can read and count it.
A reason 2 decline logs a miss on any question, since the person chose
the filter themselves, so agreeing logs one on a person's question too.

*Ruled out by a scenario* (answer-session spec: *Agreeing to a shown recorded
answer is a filter 1 decline*): withholding agreement for a record more
private than the thread, where the preview's warning lets the person decide
(scenario *Agreeing to a more private record posts it after a warning*);
giving agreeing its own record and `said`, the miss file's key for what the
person said, rather than the decline's (scenario *Agreeing on a question with
no thread is a filter 1 decline*); and no miss on an agent's question
(scenario *Agreeing logs a miss on any question*).

#### Misses the answer session logs

**The answer session pushes each miss straight to the questions branch of
what the question concerns, whether or not the asker logged the question.**
The fixed `said` of an automatic miss lets a review of misses tell the session's judgement from a
person's word. A readable miss file names in `asked_by` the account that
posted the question, since which asker keeps asking what it should have
filtered is what a reader of misses wants first, and the key reveals nothing
new, since the account already shows on the question in its thread. A hash-only miss file holds no such key. Where
questions-branch files hold the question, its miss or answer file copies the
most private `asked_from` among them, and their `repository` if they hold one, so it is
as private as they are and about the same thing; files naming different
repositories get no miss. A miss or answer file with no such file names its
GitHub thread's repository in `asked_from`. A Linear or Discord thread has no
repository, so there `asked_from` names the repository the question concerns, and for a
collective's question the lore repository serving it. For any question
asked there, the session's model judges from the question and its thread
what it concerns and which configured lore repository serves it; when it
cannot tell which lore repository, the only configured one serves it. A
question placed in neither way has no place: its miss would have no branch,
so it gets no automatic reply, and its answer is posted and not recorded (answer-session spec: *A Linear or Discord question is placed
by what it concerns*).

A miss's push, like a handled file's, is recorded as owed before the post
that leads to it and retried at each poll and opening, since once the post
is out the thread shows the question handled and nothing else would bring a
lost miss back.

*Ruled out by a scenario:* keeping misses in the state folder, which would
make it a personal question log (answer-session spec: *The answer session
logs its misses on the questions branch of what the question concerns*,
scenario *A miss goes to the questions branch*).

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**A log file follows the thread message its `asked_in` links by that exact
link, because a link names one message, so every machine pairs the same file
with the same message.** The asking agent, which writes `asked_in`, and the
answer session, which builds the URL from what it polls, write a Discord or
Linear URL in the one form the inquisitor spec's scenario *Where an asked_in may be written* gives
(*Recorded:* inquisitor record, *Rationale: A log file and a miss file have
one format*). Task 0.23 has still to compare GitHub's URL forms.

*Ruled out by a scenario:* judging every log file on its own, so the person
sees each question twice (answer-session spec: *A log file follows the thread
message its asked_in links*, scenario *A questions-branch file follows the
message it links*).

#### A link this machine never reads is not followed

**A log file whose `asked_in` links a message in a channel this machine does
not subscribe to or has off, or on a surface it has off or cannot read, is
shown on its own. An Igor worker's log file whose handback comment is on an
issue or pull request in the repository its `asked_from` names still follows
that comment, even on a machine that does not read its item (*Each Igor log
file follows its own handback comment*).**

*Ruled out by a scenario:* showing the file nowhere on that machine, so the
person would never see the question there (answer-session spec: *A log file
with no followed link is judged on its own*, scenario *A log file linking a
message this machine does not read is shown on its own*).

#### A log file without `asked_in` is never merged

**A log file with no `asked_in` is always its own question, never paired with a thread message by matching
text.** Merging only avoids a duplicate, which is low priority, while any
merge rule can pair a message with another asker's file in the same words,
so that a decline or an answer lands on that asker's question.

*Ruled out by a scenario:* merging such a file with a thread message asking
the same question, whatever extra conditions the merge rule adds
(answer-session spec: *A log file with no followed link is
judged on its own*, scenario *A log file with no asked_in is shown on its
own*).

#### A bot's question reaches only the first person it mentions

**A bot's message reaches only the first person it mentions, so each bot
question has one owner: two people cannot give a bot conflicting answers.** The answer-session decision record's *Rationale: Whom a message reaches is set
by its mentions* gives the order an Igor mentions people in. The first-mention rule has no interim form for the time igor's specs
leave that order unstated (*igor-dependent rules state the end state*).

*Ruled out by a scenario:* a handback reaching the assignee unless it
mentions only others, which gives a bot question more than one owner
(answer-session spec: *Whom a message reaches is set by its mentions*,
scenario *A bot's message reaches only the first person it mentions*).

#### igor's handback marker

**A handback is an `igor-` App's comment holding a fixed marker igor gives its
handbacks, because an Igor posts other comments on the item too, and text
the Igor quotes from its item cannot produce the marker.** igor chooses its
form, and task 0.6 records it. The post hook does not read the marker (*No
exemption for an Igor's handback*).

*Ruled out by a scenario:* counting every comment by an `igor-` App as a
handback (answer-session spec: *A handback is an igor- App's comment holding
igor's marker*, scenario *An Igor comment without the handback marker is not a
handback*).

#### Only an item's newest handback is open

**Only an item's newest handback is open; older ones are passed over by a
reading rule each machine applies alone, writing nothing.** A newer handback
follows only once the person returns the item to the Igor without answering
the older one, so the case is rare, and the newest says where the Igor is
blocked now.

*Ruled out by a scenario:* an answer naming only the oldest unanswered log
file, whose question no longer says where the Igor is blocked (answer-session
spec: *Only an item's newest handback is shown*, scenario *A newer handback
passes over an older unanswered one*).

#### A handback that mentions no one reaches the assignee

**A handback that mentions no one reaches the item's assignee; one that
mentions people reaches only the first, as any bot's message does.** So on
an item assigned to the person, a handback that mentions people reaches them
only if they are mentioned first. One that mentions no one, on an item
assigned to no one, is shown to whoever is next assigned it. igor issue #229
states both the assignee rule and the first-mention rule.

#### Each Igor log file follows its own handback comment

**Each Igor worker's log file links, in `asked_in`, the handback comment that
asks its question, so one answer never closes two handbacks' files and the
newest-handback rule needs no other mechanism.** The Igor writes `asked_in`, not the worker, because
the comment exists only once the Igor posts it. A later Igor question on an
item whose earlier question is answered follows the new handback comment,
which reaches the person as a new message in an answered thread, and an
answer to a file shown apart from its handback is relayed to that handback.

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

#### How the three specs are laid out

**Each spec opens with a `## Purpose`, and each requirement states one rule,
or two that only make sense together, in under 500 characters; its scenarios
hold the examples and cases, and this file the reasons.** The inquisitor's
Purpose defines the terms its spec uses throughout; any other term is
defined once, in the requirement that sets its rule, and earlier
requirements may use it. A Purpose is not normative, so a definition that
carries a rule, such as a default, a "never", a closed list or a condition,
also has that rule stated in a requirement.

**Why:** `openspec archive` takes a new spec's Purpose only from the delta's
`## Purpose` (spec-check, PR #50), and `openspec validate --strict` fails any
requirement over 500 characters. Splitting a requirement is the last resort:
detail moves first to scenarios, then reasons move here, then the text is
compacted, and only a requirement still too long is split, along its own
rule boundaries.

#### The change is archived only after every expected gap is tagged

**Archiving waits for task 4.3 to tag every expected gap, beside task 7.0's
wait for igor PR #216 to merge, since archiving writes the scenarios into
the directory where spec-trace's CI fails on an untagged one.**

## Open Questions

- **Which read-only tools exactly does the answer session's model get?**
  Reading and searching files, such as Claude Code's Read, Grep and Glob, is
  decided; whether any other read-only tool joins them is not (answer-session
  spec: *The session's model has no shell, no writing tool and no web
  fetch*).
- **How does the session's code show a thread's contents to the model?** The
  spec attaches the question and its thread's replies to each discussion
  message as quoted data (*A discussion runs in the session's own
  conversation*); whether the session also gives the model a read-only tool
  of its own for the thread is open.
- **Should a decline that posts nothing push a hash-only miss file?** Such
  a miss, on a Linear or Discord question whose branch is more visible, is
  named by a hash of the private message's URL, not of a reply's id, so
  anyone who can guess that URL can confirm on the branch that the question
  was declined, and when (inquisitor spec: *Every miss file is named by one
  hash*). The answer-session record's Constraint on hash-only miss files
  says the name does not identify the thread, which this case contradicts.
  The file backs no reply. The choice is to push none, or to widen the
  accepted cost.
- **How does the script commit to a questions branch without an agent's
  trailer checks seeing it?** *Questions-branch commits are machine
  records* says prose's and bug-hunter's checks never see these commits,
  but those checks read the HEAD reflog of the repository an agent runs
  `log` in. That holds only if the script commits without moving any HEAD
  there, such as with `git commit-tree` and `git update-ref` or in a
  separate clone; no requirement says so yet.

### Facts measured before building

Tasks 0.4 to 0.14 and 0.33 measure these facts before anything is built (tasks 0.1 to
0.3 are under *What the hook relies on, not yet measured*). Each bullet says
what the spec does if the fact is false. Task 0.12 is measured (*What task
0.12 measured*). Task 0.11 is measured for an issue comment only; its
result is in the inquisitor decision record's *Rationale: The log command
records a linked GitHub comment's own text*.

- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, wherever the agent lacks push access, every
  answer in a post and every issue's decision block (the start of its body
  before its first heading, or its first section whose heading starts with
  "Decision", which the spec counts as a decision document) counts as input,
  and a post's question tags no one.
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
  its working tree. If a worker can post, it still asks only in its handback
  comment, and the credential in its reach is reported to igor as a breach of
  that requirement.
- **Does the Discord bot token pattern match a real token?** (task 0.33)
  The credential patterns' Discord shape has no measurement behind it. If
  the relay's real token does not match, the pattern is changed to the
  shape measured.

### Facts the answer session relies on

**Tasks 0.15 to 0.21, 0.23, 0.25, 0.26, 0.28, 0.30, 0.31 and 0.34 measure facts the answer session relies on. Each task,
in tasks.md, says what the spec does if its measurement goes against it.
Tasks 0.18 and 0.19, which check that a command the mod runs reaches no tool
hook and that a mod keeps polling while idle or in the background, instead
stop building until the repository's owner decides. The rules that wait on
task 0.21, which tasks.md's task 0.21 lists, are not built until it is
measured, and what to build for them is decided then.** The other tasks cover
GitHub's notifications endpoint, how Linear and Discord show mentions and replies and mark a bot's message,
how the Linear relay posts a comment, how setup checks a relay's
access to each channel, and whether an asking agent's recorded `asked_in` URL
is the one the answer session reads.

Task 0.25 records how each surface reports two kinds of refusal of a relay
post: one for its text, such as its length, and one for lack of permission.
A refusal the session cannot sort into either kind waits for the person (the
answer-session spec's *A refusal the session cannot place waits for the
person*). Task 0.26 records whether a forked conversation's or a subagent's
`propose_reply` call can arrive without an `agentId`. Either way the rule
stands: such a call's draft only lands in the prompt box, where the person
sees it before anything is sent (*Claude drafts a reply only into the prompt
box*).

- **Do Linear and Discord return a posted line's words unchanged?** (task
  0.28) The answer session finds a person-required line by its fixed wording
  after reducing markup. If a surface changes the words, such as by escaping the parentheses, the
  session matches the form task 0.28 records instead. Task 0.28 is still to
  run, on both surfaces; for a Linear comment, task 0.23 already found the
  words come back unchanged (the answer-session record's *Rationale: A
  question with a person-required line gets no filter 2 to 4 reply*).
- **How does Claude Code restrict a session's tools?** (task 0.34) The
  answer session needs its session's model limited to its conversation,
  `propose_reply` and read-only file tools, enforced by Claude Code through
  permission settings, a startup option such as `--allowedTools`, or a
  mod's own control, never by a hook. If Claude Code offers no such
  control, the design falls back to hooks and the change cannot be built as
  written: the repository's owner decides what to build. *The session's
  model has no shell, no writing tool and no web fetch*, the `answer`
  command's line in *Two commands open an answer session*, and whether
  `/answer` can open in a session started without the restriction all wait
  on it.
- **Does the `answer` command's line work?** (task 0.30) It relies on
  `CLAUDE_CODE_NO_FLICKER=1` giving the fullscreen layout, on `claude
  --name`, and on a prompt argument running a slash command. If one fails,
  the command line in the answer-session spec's *Two commands open an answer
  session* is changed to what the measurement shows works, before the
  command is built.
- **Does a GitHub comment's `node_id` identify it wherever it is read?**
  (task 0.31) A miss file backing a GitHub reply is named by the reply's
  `node_id`, which the session takes from its post's response and the
  asking agent from the comment it reads. If GitHub's REST or GraphQL API
  lacks it, a kind of comment has none, or an edit changes it, the GitHub id
  that names a miss file is changed, before miss files are named on GitHub,
  to one the measurement shows works.
- **Which App wrote a comment** is measured by both task 0.21 here and igor PR
  #216's task 4.8. The rules that need it wait on task 0.21, which lists
  them.

### What igor must provide

The archive and Igor-worker mode wait on igor. What follows was read from
igor PR #216 at head 59e7561 (2026-10-24), which records #216's decisions up
to its 149.

- **Igor-worker mode waits for igor to build its search command.** A worker
  can't run this skill (*What task 0.12 measured*), so filter 1 in a worker
  calls igor's read-only `igor lore-search`, which igor PR #216 specifies and
  igor has not built. #216's task 4.5 measures whether a worker can give the
  command its standard input; if not, #216 gives it another way to take the
  text, and this change adopts it. igor must also let a worker run the skill's
  script, which today means a role's `commands` lists it. The spec's rule that
  a failed command searches no lore stays as a guard.
- **Task 4.3 and the archive wait for igor to build `igor lore-search` and
  let a worker run the script** (*The change is archived
  only after every expected gap is tagged*). Task 7.0 also waits for igor
  PR #216 to merge and for igor PR #202 to set the path of the scribe's
  records.
- **igor PR #216, with igor issue
  [#215](https://github.com/adamstallard/igor/issues/215),** amends igor's
  lore-firing spec, holds every rule for an Igor's citations, and has not
  merged. This change relies on it for:
  - *An Igor publishes the citations its worker reports*, a worker's citation
    report carrying no category, and its review counting citations on the
    lore repository's `questions` branch (its decisions 8 and 32).
  - Its id check reporting an out-of-scope collision during a run only as "id
    taken" (its decision 6); the Igor proposes no such entry and says so.
  - *Transcripts and outcomes are captured to the state branch*, in its
    task-execution spec: the flag for a question with a category, the
    categories it lists, and the Igor's handling of it (its decisions 92 and
    97).
  - *An Igor publishes the questions-branch files its worker reports*: which
    files the Igor pushes and when (its decisions 20, 21, 24 and 26), a
    handback's answer included when a worker re-works the item, and the
    checks under *A flagged run asks nothing and pushes nothing* (its decision
    38), *The Igor pushes the questions-branch files its worker reports* (28
    and 37), *A person's answer to a handback* (30 and 41) and *Every
    questions-branch file names where it was asked from* (42).
    A file's `repository` may name any repository, whether or not the run's
    role works it (its decision 33).
  - *An Igor runs its worker's lore searches*, called by a worker and by the
    Igor's own inquisitor run. It matches plain text, ranks and caps hits as
    filter 1 does, and labels each question file an answer, input,
    unanswered or a miss (its decision 23). It searches the lore repository's
    decision records at the path igor PR #202 sets too, counting an `accepted`
    one as this change does. For a questions-branch file it passes on the label
    `branch-search` gives, in place of the authority checks its decision 34
    has igor run.
  - What the Igor checks before it pushes a questions-branch file, the
    destination's visibility among them (its decisions 37 and 42).
  - Its `graceful-handoff` and `work-triage` deltas: igor's side of a flagged
    run, its handoff, its host file and the release of a held item.
- **#216's push condition should judge a file by the more private of
  whichever of `repository` and `asked_from` it holds.** Its push condition that
  the destination is no more visible "than the repository its `repository`
  key names" applies only to a file holding one. Its *Lore reaches the worker
  unbidden, beside a search it may run* cites this change's rule (#216 calls
  this change #25, its pull request in shared-skills) that a file whose
  `repository` names a repository other than the item's is input; that needs
  no rewording, since a file about a collective holds no `repository` and so
  never names another repository.
- **#216 should say that no worker writes `asked_from`, not that only an
  Igor does.** Its decision 42's sentence "Under #25 only an Igor writes the
  key", and its lore-firing spec's "which only the Igor writes", should read:
  a worker never writes the key; in a run the Igor sets it (*Every
  questions-branch file names where it was asked from*). #216's protection,
  refusing a worker's file holding the key, is unchanged.
- **#216's Igor must write the answer into the file a worker reports for a
  handback answer.** #216's lore-firing spec (lines 484-489 at 59e7561) has
  the Igor write the comment's text "in place of the answer line the worker
  wrote" only for a file holding `authority: decision` or `input`, and its
  decision 21 pushes a file with no answer as it is. This change's worker
  writes only the question and `answer_link`, no answer and no `authority` (*A
  worker logs no answer*). #216 should recognise that file, write the answer
  from the linked comment, and set `authority` and `answered_by`, a bot
  account's comment being `input`; otherwise it
  pushes the file as an unanswered question and the answer is lost.
- **#216's Igor must open the lore pull request for an entry its run
  reports** (*A general answer is proposed as a provisional lore entry*). The
  Igor applies this change's rules for a proposed entry's path, fields, id
  and visibility, and on "id taken" proposes nothing and says so.
- **#216 must keep its decision 62:** an Igor whose App's slug lacks the
  `igor-` prefix refuses to start. The answer session tells a handback by
  that prefix (*igor's handback marker*).
- **igor must push a worker's repository questions to the questions branch
  of the repository each concerns,** as it pushes a worker's collective
  questions to the team's lore repository's. igor's own specs, #216's
  lore-firing delta among them, must change to match.
- **The Igor must push no file, unanswered or answered, to a questions
  branch more visible than the handback's item** (inquisitor spec: *An
  unanswered question goes nowhere more visible than its source*). A
  worker can ask an organization question from a private repository's item
  while the lore repository is public. The handback comment is then the
  question's only record. Only the answer session pushes a file to that
  branch, and only an answer the person confirmed there; nobody confirms an
  answer typed in a comment.
- **The Igor must run the script's `branch-search` on the item's
  repository's questions branch and its lore repository's, and return the
  JSON to the worker over the channel `igor lore-search` uses** (*The Igor
  reads questions branches by running the script*). igor copies none of
  those branches' matching, file format or authority rules, and runs the
  version of the script its workers run. #216 should drop two things `branch-search`
  now does: the authority checks, and the visibility rule that its *An Igor
  runs its worker's lore searches* applies to questions-branch files. Its
  checks before a push stay.
  Task 0.29 measures whether the Igor's host has Python and the skill for
  the Igor's own process, and what its token can read.
- **#216 should drop its decisions 45, 77 and 78,** under which an Igor
  reads relay files. No relay file exists: the Igor logs a bot account's
  comment on a handback, a `User says: ` one included, as `input`, and the
  answer session's answer file, which names the Igor's log file in
  `answers`, is what counts.
- **The Igor must run the script's `miss-check` for its worker,** on the repository, surface and id of the reply the worker read in its item's thread, each time the worker asks for the check, since a worker looks again for a missing file as any agent does, with its own credentials and in the
  version its workers run, and return the JSON
  over the channel `igor lore-search` uses (*The Igor checks a reply's miss
  file for its worker*). A worker holds no credential and fetches no
  questions branch, and `branch-search` never shows a hash-only miss file,
  so a worker cannot itself check the file that backs an `Inquisitor: `
  reply. With the check, *An Inquisitor reply is acted on only with a
  writer's miss file* covers a worker as it covers any agent, an automatic
  filter 3 or 4 reply included; no rule is specific to an Igor.
- **The Igor should write its own answer file for a handback only when the
  answer session pushed none.** Otherwise one answer has two answer files.
- **#216 should refuse a worker's miss file holding `said_by`, and any
  hash-only miss file a worker reports,** since either would let a steered worker
  lend authority to an `Inquisitor: ` reply that anyone posted.
- **#216 should refuse a worker's file holding `handled` or `closes`,** as it
  refuses one holding `asked_from`. #216 pushes any worker file with no
  `authority` as an unanswered question file, so a worker steered by item
  text could otherwise close, on every machine and for good, whichever file a
  planted `closes` names.
- **#216's Igor should keep its decision 59's record of each handback** (*A
  later run names the answered file from the Igor's record*). Without
  the record, a later run writes no `answers`.
- **#216's Igor should write `asked_in`** in a worker's log file as the URL of
  the handback comment that asks it, once it has posted that comment. In
  each answer file it writes, it adds `answers`, naming the log file that
  file answers, and it refuses a worker's file holding `answers`. Without
  `answers`, the answer session keeps showing the answered file as unanswered.
- **#216 should give every handback comment a fixed marker** (*igor's
  handback marker*).
- **#216 should widen its definition of a citation to include a person's
  cite.** #216 counts only an agent's record that a lore entry answered a
  question so that no person was asked. Here a person's cite of an `active`
  entry in scope pushes a citation too, as does a decline under "the
  inquisitor should have handled it" with filter 1 naming such an entry (*A
  person's cite pushes a citation file*).
- **How an Igor runs the inquisitor skill itself** is only partly set. igor
  PR #216's `task-execution` spec sets `IGOR_RUN=igor` in that run's
  environment, and the script then searches lore only through `igor
  lore-search` and pushes nothing, reporting each file it would push and each
  entry it would propose to the Igor. #216's task 3.6 waits for igor #211 to
  say how the Igor starts that run. Open: which other sources that run's
  filter 1 covers, how the report reaches the Igor, and whether the run can
  read GitHub.
- **igor must say how `igor lore-search` identifies the Igor's own
  inquisitor run.** #216 takes the run and role from the channel a request
  arrives on, which only that run's worker can reach (its lore-firing spec),
  and the Igor's own run has no worker.
- **igor's specs must state the order in which each Igor mentions people,**
  set in igor issue [#229](https://github.com/adamstallard/igor/issues/229),
  which is open. No igor spec states it, yet *A bot's question reaches only
  the first person it mentions* relies on it.
- **igor PR #153, signed publishing,** would have an Igor whose role lists
  prose or bug-hunter push only commits that went through those skills and
  carry their trailers. Citation commits carry none, so #153 should exempt an
  Igor's commits to a lore repository's `questions` branch. That is #153's to
  settle.
- **igor PR #202 must say where the scribe's records live,** in the repository
  a question concerns and in the lore repository, since filter 1 searches them
  there. Two of #202's open points decide when an answer typed directly on
  another surface can count through a scribe's record:
  - #202 has not settled how the scribe recognises an approval given off
    GitHub. An answer typed directly on another surface counts only through a
    decision document (*An answer typed on another surface counts only through
    a decision document*).
  - #202's spec puts a decision about several repositories in the lore
    repository. Filter 1 reads the lore repository's decision records where
    #202 puts them (task 7.0).
### What other changes must provide

- **The github-app skill's `token`, `run`, `credential get` and `wire`
  commands must refuse an identity marked as a relay.** Issue
  adamstallard/shared-skills#96 tracks it. Its spec, in a pull request
  stacked on this one, starts once this change's spec is approved, and its
  implementation follows this change's. This change does not wait for it:
  the entry *github-app refuses `token`, `run`, `credential get` and `wire`
  for a relay identity*, above, says why and what stays open meanwhile.

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

