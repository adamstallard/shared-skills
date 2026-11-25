The inquisitor is a skill that stops an agent's needless questions to a
person. Before asking, the agent runs each question through four filters:
filter 1, already answered (it searches for an earlier answer); filter 2,
deferrable; filter 3, not a real question; filter 4, cheap to reverse
(inquisitor spec: *Every question passes four filters before a person sees
it*). Hooks on Claude Code's question picker and on GitHub posts block a
question that has not been through them.

## Proving the filters ran

A hook can't judge whether a question has merit; only the agent can. So the
design makes skipping the filters fail, and leaves the verdicts to review.
As the prose skill proves its pass ran with a first call that prints its
rules and a second that signs the result, the inquisitor's script takes
questions in two calls (inquisitor spec: *Two calls prove the filters ran*).
The first call issues a token for the second, holding hashes, never text:
each question's and, for a picker question, its first option's, the
recommended answer.

The calls prove that the filters were printed and the search ran before each
verdict, not that the agent judged well. A hook checks each question's
latest record, and when it can't read the records, the picker hook fails
open and the post hook fails closed (inquisitor spec: *A hook blocks a
picker question that was not vetted*; *Questions in posts pass the same
filters*): an unfiltered picker question at worst reaches the person, while
a post's unchecked question might be a vulnerability.

The verdict records live in the user's state folder (this design's *Hooks
and verdict records*). Apart from them, the hooks keep no record of any
question. The question log files (*Where the logs live*) are the lasting
records; for a vulnerability question, the lasting record is the
repository's private security advisory.

**Ruled out by a scenario** (inquisitor spec: *A hook blocks a picker question
that was not vetted*):

- **The skill's description alone,** with no hook: a model loads a skill by
  judgement (scenario *An unvetted question is blocked*).

## Questions in posts

**The order with prose:** prose's pass, then vet the rewritten body, then
sign with prose (scenario *Signing after vetting keeps the post vetted*).
Lines the question's hash leaves out, such as the tag and concerns lines
(inquisitor spec: *A question's text and hash are built one way*), need no
vetting, but go in before prose signs, since any edit after signing means
signing again.

## Where the logs live

**Rule:** inquisitor spec, *A question is pushed to the questions branch of
what it concerns*; *A question is written at the privacy of what it
concerns*; *Every answer is recorded and every asked question logged*; *No
record goes somewhere more visible than its source*.

The inquisitor decision record's *Rationale: A question is pushed to the
questions branch of what it concerns* gives why no review is needed and why
the files are not committed with the work.

- **About a collective:** keeping the files off the lore repository's
  default branch leaves that branch holding only the reviewed lore entries
  Igor gives agents. The files hold no `conditions`, the key that marks a
  lore entry, so neither the search nor Igor reads one as an entry.
  Promotion to lore: inquisitor spec, *An answer that generalizes is
  proposed as lore*.

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

The search reads lore from the clone's remote-tracking default branch, such
as `origin/main` (inquisitor spec: *A lore entry is read from the
remote-tracking default branch*), never the working tree, which could be on
another branch, or a local branch, which could hold an unreviewed edit. Filter 1 dates
each clone from that branch's reflog (inquisitor spec: *Filter 1 names what
it did not search and how fresh each clone is*), so the date and the content
come from one ref, and the date is when the clone last received a change to
that branch: not when the branch last moved on GitHub, and not a later fetch
that brought nothing new.

The `.inquisitor/reviewers` file is committed and decided in review, so
every teammate's agent tags the same person.

Visibility, of a lore repository or of the repository a question concerns,
is read with `gh repo view --json visibility` on the clone's `origin`, which
gives `PRIVATE`, `INTERNAL` or `PUBLIC`. Write access
is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Each check fails closed (inquisitor
spec: *An unreadable visibility counts against sharing*; *A permission that
cannot be read is no write access*).

The configured `login` is checked by running `gh api user` as the person
(inquisitor spec: *A configured login counts only when gh is logged in as
it*), so nobody can claim a maintainer's login by typing it into their own
file.

## The answer service

The answer service gives a person one place to answer the questions asked of
them on GitHub, Linear and Discord. A relay identity, the person's own bot on
each surface, posts each answer in the question's thread, and an answer file
on a questions branch records it. The rules are in the `answer-service`
spec, whose Purpose says what it leaves to the answer mod. The
decisions are in this file's sections from *Answer-service configuration, setup and relay
identities* to *Linking log files to threads, and handbacks*.

### What the answer service posts

Only the answer service starts a post with a reserved prefix (answer-service
spec: *Relay posts start with a reserved prefix*); *The post
hook blocks a reserved prefix on GitHub* gives why.

**Rule:** answer-service spec, *A relay post is posted by a host command,
unvetted* (task 0.18); *The Linear relay's token stays in memory*; *A GitHub
or Linear relay post names its question in a Re line*. The command runs with
no shell because the person's answer and drafts built from a thread's
untrusted text reach it.

### What the answer service does by itself

The answer service runs the four filters on incoming questions, so the
person sees only the questions that need them. Its automatic replies,
posted without the person, raise two risks, and the spec answers each:

- **A thread's text reaches the model that judges it.** So the model writes
  no word of an automatic post, and a crafted question can at worst choose
  which fixed reply or which record is posted. The asking agent acts on an
  `Inquisitor: ` reply only when a miss file backs it (the inquisitor decision
  record's *Rationale: An Inquisitor reply is acted on only with its
  miss file*). The asking agent already ran filters 2 to 4 itself, so a backed reply is a second judgment, by the person's answer service, that the question can wait, that one option has merit or that the choice is cheap to reverse (*What an asking
  agent does with an automatic reply*).
- **A record can be more private than the thread:** answer-service spec, *A
  recorded answer is posted by itself only when no more private than its
  thread*.

## Tracing scenarios to tests

Tasks 4.2 and 4.3 set which scenarios get a tagged test and which are
expected gaps. A skipped test would not do for a gap: spec-trace counts a
skipped test's tag as coverage, which would hide the gap. Nor can
spec-trace's baseline, `openspec/spec-trace-baseline.txt`, exempt a gap,
since it takes no new lines once this change adopts spec-trace.

## Decisions

Each entry states the decision and its reasons, and labels each alternative
not taken that a test can check as ***Ruled out by a scenario:*** the spec
holds the rule as a requirement, with a scenario the alternative would fail;
the entry gives only the reason, and names that requirement and scenario.

### Asking a person

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

**The hand-back is spec-check's:** the word means what spec-check's skill
defines, so it names one moment across the skills. Unlike spec-check's
review round, which only a hand-back ends, the inquisitor's round also ends
at each end of the agent's turn, so it has its own name: a question round.

**Unlike a deferred question,** which the current work does not need
answered and so is listed as not done and never asked, a question waiting for
the round's end is one the work needs: the work goes on, on an assumption the
answer may overturn.

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

#### bug-hunter's Step 9 recommendations go through the filters

**Rule:** inquisitor spec, *A question another skill requires skips filters
2 and 4*, which leaves these recommendations out. bug-hunter's Step 9 asks the person about its recommendations one
at a time. Running them through all four filters means fewer reach a
person; exempting them would invite each skill to claim an exemption of its
own.

#### A prepared question can be answered "yes"

**Rule:** inquisitor spec, *A question that is asked is prepared for a quick
answer*. The recommended answer comes first so that most questions can be
answered "yes". The picker hook need not check the order: reordering options
after vetting changes the question's text, which the hook blocks as
unvetted.

#### With a person present, ask through the picker

**Rule:** inquisitor spec, *Where the host has a picker, an agent asks
through it, never in its reply*.

**Why:** the picker hook then sees every question, and the starting agent,
which is talking to the person, can batch a subagent's questions with its
own.

#### What counts as a question in a post

**Rule:** inquisitor spec, *A question in a post is a listed item or a
sentence ending in a question mark*. Its section labels are those under
which agents list open questions. *Questions in posts* gives the order with
prose's pass and signature. The rule lives in one function, so it is cheap
to change if it misjudges posts.

#### When no candidate can decide

**Rule:** inquisitor spec, *A question no candidate can decide turns to the
session's login*.

**Why:** the configured login is tagged only on a post going out as
another account, since tagging the account a post goes out as would ask
the person their own question.

### Hooks and verdict records

*Proving the filters ran* gives the reasoning for these hooks and records,
and the alternatives not taken.

#### The hooks are on once the skill is installed

**Rule:** inquisitor spec, *The hooks are on once the skill is installed,
and spend no record*. Installing is the opt-in, as it is for prose's blocking hooks.

#### Files passed to the two calls stay private

**Rule:** inquisitor spec, *The two calls' files and records stay private*;
*Some questions are recorded by hash only*.
Outside any repository, the files can't be committed.

#### Verdict records live in the user's state folder

**Rule:** inquisitor spec, *The two calls' files and records stay private*.
The records sit beside prose's session marks. They hold no question's text (inquisitor spec: *The second call
records all its verdicts or none*), so they are the hooks' state, not a
personal question log.

#### An `ask` record drops the option's label

**Rule:** inquisitor spec, *The two calls' files and records stay private*.
The labels are part of the question's text, which no record holds. So the
verdict records cannot show later whether the person took the
recommendation: a cost the rule accepts.

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
for days.

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

#### The hooks check the related-decision line for credentials

**Rule:** inquisitor spec, *A related-decision line is one URL on a line of
its own*.

**Why:** no vetting sees the line.

### The shared post reader

#### Questions in posts pass the filters, on GitHub only

**No hook checks a question in a Linear or Discord message; only the
skill's instructions cover it,** since both hooks share prose's post
reader, which reads GitHub posts only.

#### One post reader, shared by both hooks

**Rule:** gh-post spec, *The shared post reader reads a post's body from an
allow-list*. The
reader is an allow-list because a general command parser reads some commands
differently from bash, and each difference can let a post through unread; on
a line that mentions a gh post verb, an allow-list blocks every form outside
it, so a difference fails closed. A
second copy of the reader would add a second set of differences.

#### Posts sent through the github-app skill's script

**Rule:** gh-post spec, *The reader reads posts sent through the github-app
skill and gh api*.

**Why:** prose's rules read a post only from a simple command whose command
is `gh`. To them, the script's call is `gh` in another command's text, which is
unreadable, so every post sent as a GitHub App would be refused.

#### The reader reads gh api writes, REST and GraphQL

**Rule:** gh-post spec, *The reader reads a gh api write to an issue or pull
request*; *A gh api write read from a file is read only as a whole command
line*; *The reader reads GraphQL posts and blocks an unreadable body sent
to issues or pull requests*.

**Why:** without these rules, a `gh api` comment would skip both hooks.

Both hooks read a file, given by `@<file>` or `--input`, before the line
runs. An earlier command on the line, such as `printf 'unsigned' > c.md`,
could then replace a signed body with one the hooks never saw, as it could
a `--body-file`; for GraphQL it could also swap the query for another
mutation. So such a write is read only as the whole command line. A field
given in the command cannot be rewritten.

#### A gh api call counts only when it can write

**Rule:** gh-post spec, *A gh api call is a read only as a plain gh command*;
*A gh api call writes by its method, fields, input or a mutation*.

**Why:** a read posts nothing, so counting it would block, for every prose
user, lines such as `gh api … | python3 -c …`. With no method given, the reader
counts `--input` as a write without working out which method gh would use,
so it fails closed.

#### A hook payload that is not JSON passes the post hook

**Rule:** inquisitor spec, *The post hook vets what the shared post reader
returns*.

**Why:** the host, not the agent, writes the hook's input, so a payload
that is not JSON means the host is broken, never that an agent crafted a
post. Blocking such payloads would block every Bash and GitHub MCP call
until the host is fixed.

#### The post hook blocks a reserved prefix on GitHub

**Rule:** inquisitor spec, *The post hook vets what the shared post reader
returns*; answer-service spec, *Relay posts start with a reserved
prefix*.

**Why:** anything holding a relay identity could post `User says: `, which
marks a question answered on every machine.

### Logs and privacy

#### Collective questions go on lore's `questions` branch

***Ruled out by a scenario:*** igor's `igor-state` branch, which holds
igor's runtime state (inquisitor spec: *A question is pushed to the
questions branch of what it concerns*, scenario *An organization's
question goes to its lore repository*). **Why:** the lore repository's branch keeps questions not important
enough to become lore, so nobody asks them again.

#### A way-of-working question gets no log

**Rule:** inquisitor spec, *A way-of-working answer goes to the person's
memory, not a log*. Agents already read that memory, and a committed
`CLAUDE.md` would apply one person's way of working to every agent in that
repository.

#### Nothing goes somewhere more visible than its source

**Rule:** inquisitor spec, *No record goes somewhere more visible than its
source*; *The answerer's confirmation can send a record somewhere more
visible*. Shown where the record will go, the person approves the wording's
privacy when they answer, so a picker question is pushed only once it is
answered.

#### Three categories are recorded by hash only

**Rule:** inquisitor spec, *Some questions are recorded by hash only*.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### The secret scan is only a backstop

**Rule:** inquisitor spec, *The credential patterns are a closed list of
token shapes*. The scan catches only the token shapes it lists, so it backs
up, never replaces, the category judgement that keeps a secret out of a log
file. Its patterns include the two credentials this change gives the answer
service's code, which a person could paste into an answer: a Linear key and
a Discord relay's bot token.

#### Weaknesses stay out of public text until disclosure

**Rule:** inquisitor spec, *A weakness is not described in public text
before its advisory is published*; *Before publication, a weakness's test
and description reach only the private fork*.

**Why:** the risk is describing the weakness, in any words, so whether the
text states a question or its answer is the wrong test.

### Which answers count, and citations

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

#### The `log` command reads its inputs and the linked comments itself

**Rule:** inquisitor spec, *The log command records a linked GitHub
comment's own text*; *The log command refuses a question holding a closing
section's heading*.

**Why** it refuses a question holding a line `## Rephrased question`,
`## Discussion` or `## Answer`: a reader takes those lines from a log file's
end, so an untrusted question ending in forged rephrasing lines would read
back as a shorter question, and a writer's answer would be recorded against
a different text and hash.

#### Citations go to the lore repository's questions branch

**Rule:** inquisitor spec, *A lore entry that stops a question gets a
citation file*; *A citation file has one format*. A question with a category
gets none, since the cited entry would show what it was about.

### Lore and misses

#### Filter 1 searches lore in every session

**Why:** the search is how lessons reach plain Claude Code sessions, which no
Igor injects lore into.

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

#### An Igor worker asks only through its Igor

**Rule:** inquisitor spec, *A session with no person in it asks in a post, a
handback or nowhere*; *A worker's question about a more private repository
is asked on that repository's questions branch*; *A later run gets only the
answer to its Igor's question on a more private repository*; answer-service
spec, *The preview says when an answer also reaches a more visible item's
run*.

**Why** a later run reads that one file's answer: the worker needs the
answer to go on.

#### Filter 1 in an Igor's run searches through `igor lore-search`

**Why** only the lore repository the Igor injects from: the Igor checks a
cited entry, reported by id alone, against that lore repository; another
one's search could find an entry the Igor refuses, or one it takes for a
different entry with that id.

#### Every questions-branch file names where it was asked from

**Rule:** inquisitor spec, *A log file and a miss file have one format*,
scenario *A file an Igor pushes names where it was asked from* (#216's
decision 42); *A log or miss file is as private as its more private
repository*.

**Why** no worker writes it: a worker steered by its item could write a
public `repository` on a file about a private repository; `asked_from`
still names the private one, so the question cannot be laundered. Outside a
run, the writer of `asked_from`, the script or the answer service, already
sets `repository`, so setting `asked_from` too gives it no new way to
mislead.

#### A person's answer to a handback

**Rule:** inquisitor spec, *An Igor pushes a handback answer only for a
question its record holds*.

**Why:** matching by the Igor's handback record, not by the comment's
text, stops a worker steered by text in its item from attaching a
person's real comment to a question it does not answer.

#### A later run names the answered file from the Igor's record

**Rule:** inquisitor spec, *A later Igor run names the answered file only
from the Igor's record*.

**Why:** anyone who can edit a comment can change its text, so the run never
reads a file's name from the comment. The random suffix makes a name unique,
so a second file matching the record can only be a planted look-alike. The
slug of the question's words in a file's name reveals nothing more, since the
file holds the question's text on a questions branch no more visible than the
question.

### Answer-service configuration, setup and relay identities

#### Discord is in the first version, through discord-bot

**Discord is in the first version, through the `discord-bot` skill of
shared-skills PR #1, merged,** because the skill's bot can post for the
person without any process running beside the session: its script
makes its API calls on each run and exits.

#### An answer given through the answer service counts by its answer file

**Rule:** inquisitor spec, *An agent logs a bot's comment only as input*;
answer-service spec, *An answer is recorded by a new log file*; *A
questions-branch answer file records the answer as given*. Because an
answer counts by its answer file, not by who wrote the comment, no committed
file lists a person's bots, and counting an answer never needs to know
which App wrote a comment.

### Running the answer service

#### The answer mod ships inside the inquisitor skill

**Why:** the answer mod, a Claude Code mod, does nothing without the
inquisitor, and the answer service cannot be used without some UI.
Shipping one with the skill makes the answer-service spec concrete, and
gives anyone writing another UI a model. So the inquisitor's script
installs it, not manage-skills, which installs the repository's top-level
skills and mods.

#### Which cross-machine cases are accepted

**A case between two machines of the same person whose worst outcome is a
question shown twice or asked again is accepted, and gets no rule of its
own.** "Asked again" means an asking agent asks a question again because one
machine has not yet seen what the other recorded, and
"shown twice" means the person sees one question twice; either costs the
person only a second look. A case that could record a wrong answer, close a question wrongly,
leak private content or lose an answer is still raised for a decision. The
answer-service decision record's *Rejected: A TLA+ model of the answer
service's owed pushes and automatic posts* lists the further crash and two-machine outcomes accepted without a rule of their own.

#### One answer service runs on each machine

**The answer service's lock file makes one session the sole writer of its machine's state:** one state folder holds the machine's
owed pushes, pending answers and poll positions, and two answer services
would poll, post and push twice.

#### A discussion runs in the session's own conversation

**Why:** the person opened the conversation to talk the question through, and
the model reads before it replies, while a picker would hide the answer
service's screen. So a question the model asks back is the one exception to
the rule that an agent asks only through the picker.

#### The model hands its judgements to the code through record_verdict

**The code puts each message to judge into the session's conversation as a prompt of its own, holding the message as quoted data, at times when the model is not answering the person; the model then answers through `record_verdict`.** Whether a mod can prompt its own model is still open (task 0.37).

The approved prototype, build v0.2-9, shows that a mod can fill the prompt
box and register a tool for its model to call, as `record_verdict` is, but
not that a mod can prompt its own model, so task 0.37 stays open.

### Relaying answers

#### The thread is the durable record of an answer

**Rule:** answer-service spec, *The thread is the durable record of an
answer*; *The thread is read again before a question is shown and before a
post*; *Relay posts start with a reserved prefix*; *A GitHub or Linear
relay post names its question in a Re line*. Because each machine reads the
thread again before it posts, two of the person's machines answering one question both post only when neither machine's read before posting finds the other's post.

**Why:** the thread is the one place every machine, and the asker, can read.
A crash after a post but before its id is saved loses no question state: the
next read of the thread finds the post.

#### `User says: ` answers, `User asks: ` asks the asker

The prefixes exist because "waiting for the asker" is read from the thread,
which needs a mark every machine, and every surface, can read there.

#### A relay post gets no prose pass and no vetting

**Why:** a relay post is the person's words. A prose rewrite would post words
the person did not confirm, and the filters guard a person's time against an
agent's questions, not the person's own words.

#### The person can ask the asker

**Asking back is mostly for people's questions:** an Igor's worker asks in its
handback comment and is gone, so a reply reaches whichever worker next takes
the item.

#### A questions-branch question is answered by a new log file

**Rule:** answer-service spec, *An answer is recorded by a new log file*;
inquisitor spec, *A file on a questions branch never changes once pushed*.
An answer to a file whose `asked_in` links a post is both relayed and
pushed so that neither the asker reading the thread nor an agent searching
the branch misses it.

#### An answer file records the question the person saw

**Rule:** answer-service spec, *A questions-branch answer file records the
answer as given*; *The preview shows where an answer will be recorded*.
Recording the log file's own question instead would let a log file whose
`asked_in` points at an unrelated message get the person's answer
recorded, as a decision, against words they never saw.

#### An answer file names every file it answers

The inquisitor spec's *An answer file names every unanswered file it
answers* sets the rule. Naming files gives every machine the same answer,
while answering whichever files hold the same words would give machines
holding different files different answers.

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

#### Who may answer a named file

**Rule:** inquisitor spec, *A named file's answer is the newest answer file
naming it*.

**Why** its `answered_by` must be a person the question tags, when it tags
one: the question was put to that person.

#### `answer_link` and `asked_in` are withheld where they would leak

**Rule:** inquisitor spec, *The log command withholds a link where it would
leak*; *A log or miss file is as private as its more private repository*;
*The answerer's confirmation can send a record somewhere more visible*;
answer-service spec, *The preview warns before a record goes somewhere
more visible*; *A recorded answer is posted by itself only when no
more private than its thread*.

**Why:** the URL would point the readers of a more visible questions branch
into a more private thread. A Discord URL holds the server's and channel's
ids, a Linear URL the workspace and issue key, and a github.com link into
a more private repository leaks the same way. An answer's text can leak
from a private thread too, which is why an answer file goes somewhere more
visible than its thread only with the person's confirmation.

#### An answer that cannot reach its thread is kept pending

**Rule:** answer-service spec, *An answer that cannot reach its thread is
kept pending*; *A pending answer returns to the queue once its channel
works again*; *A pending answer that no check returns waits for the person*. A
failed post keeps its answer pending rather than leaving the question as it
was, which would drop the answer the person typed.

#### The push order for a questions-branch answer

**Rule:** answer-service spec, *A questions-branch answer's file is pushed
after its post*; *An answer whose thread is unreachable here is logged at
once*; inquisitor spec, *The answer service's files are never kept pending*.
Were the `log` command to keep a pending copy too, a passing failure would
give two answer files: the service's retry would push one, and the next
`log` call the copy. And after the `log` command reported a refusal as final, its pending copy would still be pushed.

#### What the answer service posts by itself

**Rule:** answer-service spec, *A recorded answer posted by itself links
filter 1's hit and quotes no answer*; *An automatic post's text is fixed by
the answer service* (*What the answer service does by itself* gives why).
A log file's answer is a whole comment, which could hold @-mentions that
would notify people again on GitHub, or a `Recorded in: ` line of its own.

*Ruled out by a scenario:* a recorded answer in a sentence the model writes,
which a crafted thread could steer (answer-service spec: *A clear filter 2 to
4 failure gets its fixed reply by itself*, scenario *A thread's text cannot
choose the words posted*); and quoting the answer with its mentions
neutralised, which needs a
rule per surface (answer-service spec: *A recorded answer posted by itself
links filter 1's hit and quotes no answer*, scenario *A recorded answer is
posted by itself*).

#### No automatic post repeats one in its chain of replies

**Why:** checking only the post a reply answered would let an agent that
kept replying get filter 2's text, then filter 4's, then filter 2's again
with no person seeing it.

### Incoming questions, declining and handled files

#### Which questions count as an agent's

**Rule:** answer-service spec, *An agent's question comes from a bot account
or a log file*; *A relayed question is a person's question*.

Only an agent's question gets an `Inquisitor: ` reply posted by itself, so a
question in doubt counts as a person's: no person then gets an `Inquisitor: `
reply posted by itself.

#### A question another skill requires carries a line the answer service matches

**Rule:** inquisitor spec, *A question another skill requires carries a
person-required line*; *The second call checks a requiring skill, and the
post hook its line*; answer-service spec, *A question with a person-required
line gets no filter 2 to 4 reply*.

**Why:** the asking agent skips filters 2 and 4 for such a question. It
has already run filter 3, knowing which options the requiring skill lets it
take itself; the answer service cannot see those options. If the answer
service applied filters 2 to 4, it could close by itself a question only a
person may decide. For the same reason, the person's own decline for the
inquisitor posts no such reply either: the requiring skill wants the
person's answer. The line starts
`Inquisitor: ` like the service's own fixed texts, but sits after the
question, since the post hook blocks a GitHub post starting `Inquisitor: `,
a prefix reserved for the service. The script prints it, so its wording
never varies and finding it needs no judgement. Whether surfaces return it
unchanged: the answer-service decision record's *Rationale: A question with
a person-required line gets no filter 2 to 4 reply*.

#### What an asking agent does with an automatic reply

**Rule:** inquisitor spec, *An Inquisitor reply is acted on only with its
miss file*; *A reply's miss file is looked for on the branch its
question's concerns line names*; *Every miss file is named by one hash*; *A
hash-only miss file shows nothing but that it exists*; *An answer service's
automatic reply is a verdict, not a person's answer*; answer-service spec,
*A concerns line settles what an agent's question concerns*; *A miss more
visible than its thread is pushed as a hash-only file*.

A reply's miss file is named by the reply's own message id because the name
is only a lookup key, and the file authorizes one thing, a particular reply,
which its id identifies exactly. No question text is hashed, so nothing a
surface or a posting skill changes in a message's text can break the lookup.
Were the agent and the service each to judge what the
question concerns, they could judge different repositories: the agent would
find no file and take the reply as input, while the service listed the
question as handled, so nobody would answer it. Second, an agent that also looked for the miss file on its thread's repository would act on a miss backed by a writer in that repository, who may have no write access to what the question concerns, though a
logged decision needs that access. Naming the repository on the concerns
line removes both failures. A crafted thread can already steer `place`,
the `record_verdict` field naming what a question concerns, to any place on
the list the service's code lets the model choose from, so a
crafted concerns line reaches nowhere new.

A readable miss file is used, not a hash-only one, wherever privacy allows,
for its value as a log.

#### Two reasons to decline

**Rule:** answer-service spec, *The person can decline to answer*;
*Declining for the inquisitor posts the picked filter's reply*.

The two reasons are "nothing to answer" (reason 1) and "for the inquisitor" (reason 2). Reason 1 is named "nothing to answer" to keep clear of filter 3's text, "not a real question". The person can still answer on the surface by hand.

#### Declining with nothing to answer closes only that question

**Rule:** answer-service spec, *The person can decline to answer*; *Later
messages after an answer or a decline are new questions*.

A reason 1 decline is held in each machine's own state folder, so if it
stopped later messages counting, a follow-up would count on one machine and
not on another.

#### The answer service writes a handled file on every close of a questions-branch file

**Rule:** answer-service spec, *A handled file closes a questions-branch
question*; *A handled file is pushed once its close takes effect*;
inquisitor spec, *Only an answer service writes a handled file*; *A log
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

A close that cites a record, a filter 1 decline or a `Recorded answer: `
post, takes the question out of the person's queue whether or not the
asking agent's own filter 1 would count that record: the record is then in
the thread, and an asker that cannot count it and asks again reaches the
queue as a new question.

#### Closing works by exact identity, never by matching

**Rule:** answer-service spec, *A handled file closes a questions-branch
question*; *A decline with nothing posted closes a thread copy on this
machine only*.

Matching on a question's words, on a topic repository, which each machine's
model judges for itself, or on clocks can give two machines different
answers; exact identity cannot disagree.

#### Reopening a declined question

**Rule:** answer-service spec, *Only a thread copy declined with nothing
posted is reopened*.

After a post, the thread, which every machine reads, records how the
question was handled. A thread copy stays reopenable after a handled file
closes its questions-branch file, since that file is closed on every machine
for good and the thread copy is separate from it.

#### Agreeing to a recorded answer is a filter 1 decline

**Rule:** answer-service spec, *Agreeing to a shown recorded answer is a
filter 1 decline*.

The record exists and filter 1 found it, so an answer log file pointing to
it adds nothing; a later searching agent is stopped by the record only if
its own filter 1 can read and count it.

#### Misses the answer service logs

**Rule:** answer-service spec, *The answer service logs its misses on the
questions branch of what the question concerns*; *A miss records who judged
it and where it was asked from*; *A miss holds the repository its question
concerns*; *A Linear or Discord question is placed by
what it concerns*; *A miss or citation file's push is owed and retried as a
handled file's is*; inquisitor spec, *A log file and a miss file have one
format*.

The fixed `said` of an automatic miss lets a review of misses tell the
service's judgement from a person's word. Where a miss file names in
`asked_by` the account that posted the question, a review of misses can
show which asker keeps asking what it should have filtered.
`asked_by` reveals nothing new: the account already shows on the question
in its thread.

A miss's push is recorded as owed before its post since once the post is
out the thread shows the question handled and nothing else would bring a
lost miss back.

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**Rule:** answer-service spec, *A log file follows the thread message its
asked_in links*; inquisitor spec, *A log file and a miss file have one
format*.

A link names one message, so every machine pairs the same file with the
same message.

#### A link this machine never reads is not followed

**Rule:** answer-service spec, *A log file with no followed link is judged
on its own*; *An Igor's log file follows its own handback comment*.

An Igor's log file follows its handback only on an item this machine
already reads: reading any other item would let the file's `asked_from`,
which whoever pushes the file writes, choose which repository the service
reads with the person's credentials. On GitHub the handback must also be
in the repository `asked_from` names, where an Igor posts it, so a file
cannot attach itself to a handback on another repository's item.

#### A log file without `asked_in` is never merged

**Rule:** answer-service spec, *A log file with no followed link is judged
on its own*.

Merging only spares the person seeing one question twice, which costs them
a second look, while any merge rule can pair a message with another asker's
file in the same words, so that the person's decline, which closes a
question unanswered, or their answer lands on that asker's question.

#### Whom a bot's question reaches

**Rule:** answer-service spec, *Whom a message reaches is set by its
mentions*.

A bot question with a tag line or a mention reaches one person, so two
people cannot give a bot conflicting answers. An untagged one, such as
an agent's Linear question, reaches the subscribers with write access to
the repository it is placed in, rather than no one: an untagged question does not mean no one can decide it, since the script may find no tagging candidate with write access when another subscriber has it,
and an agent's thread may have no person in it to notice the question.
A question placed in no repository reaches no one, though its thread may
have no person in it either: with no repository to check write access
to, showing it to every subscriber of its channel would show people
questions they may not be able to decide.

#### Each Igor log file follows its own handback comment

**Rule:** answer-service spec, *An Igor's log file follows its own handback
comment*; inquisitor spec, *A questions-branch log file links where its
question was asked*.

Linking the handback comment means one answer never closes two handbacks'
files, and the answer-service rule that only an item's newest handback is shown needs no other mechanism.

### OpenSpec and spec-trace

#### A skill with no spec lists its edits as tasks

A change that edits a skill with no spec, as this one edits github-app and
bug-hunter, lists the edit as a task, since a skill gets its spec only in
a change of its own, as shared-skills issue #57 plans.

#### spec-trace's template skips the questions branch in this change's merge

**Rule:** tasks 5.6 and 5.9. shared-skills PR #101, which makes spec-trace's
template skip the branch, names the inquisitor in its README and SKILL.md
as the reason. Landing in this change's merge, the
skip arrives with the inquisitor's README (task 5.6), which says the
template skips the branch; #101 merged earlier would name a skill not yet
shipped, and merged later would leave that README describing a skip the
template lacks.

## Open Questions

### Facts measured before building

The task each bullet names measures its fact before anything is built.
Each bullet says what the spec does if the fact is false, or, where the
bullet only asks the question, its task in tasks.md says it.

- **Does the picker hook work?** (tasks 0.1 to 0.3) If a `PreToolUse`
  hook does not fire on `AskUserQuestion`, or its exit 2 does not block
  the picker, the skill's instructions alone cover the picker, and the
  README says so. If the tool's input holds no `questions[].question` and
  `questions[].options[].label`, the spec's definition of a picker question's text is rewritten to what
  the input holds.
- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, wherever the agent lacks push access, every
  answer in a post and every issue's decision block (an inquisitor spec
  term) counts as input,
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

Tasks 0.11, 0.13, 0.14, 0.29 and 0.33 measure the rest: whether GitHub
gives review authors and logs re-requests, whether an advisory's
private-fork pull request can merge before publication, whether an Igor
worker can post, whether the Igor can run `branch-search` and read a
collaborator's permission, and whether the Discord token pattern matches
a real token. Each task says what follows if its fact is false.

### Facts the answer service relies on

**Tasks 0.6, 0.15 to 0.21, 0.23, 0.25, 0.28, 0.30, 0.31, 0.34, 0.35, 0.37, 0.38 and 0.39 in tasks.md measure facts the answer service relies on, such as how each surface returns a message's text, how GitHub tells a bot's comment (0.21), how Claude Code restricts a session's tools (0.34) and whether a mod can prompt its own model (0.37). Each task says what the spec does if its measurement shows the fact false.**

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would need that surface's API to vouch for the message's author,
  and a map from the author to a GitHub login: igor issue #160's configuration
  entry keyed by the Discord user id, or a file in the lore repository. A
  later change would choose. Without it, an answer typed directly on such a
  surface counts only through a decision document, such as the scribe's
  record; one typed in the answer service and relayed there counts through its
  answer file.

