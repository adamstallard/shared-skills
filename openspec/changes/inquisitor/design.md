The inquisitor is a skill that stops an agent's needless questions to a
person. Before asking, the agent runs each question through four filters:
filter 1, already answered (it searches for an earlier answer); filter 2,
deferrable; filter 3, not a real question; filter 4, cheap to reverse (*Four
filters stop questions before a person*, under *Decisions*). Hooks on
Claude Code's question picker and on GitHub posts block a question that has
not been through them. *Terms used throughout*, after the introduction to
*Decisions*, defines Igor, the picker, the two calls, a verdict and the
answer session. Adam (adamstallard) owns this repository and decides this
change.

## Proving the filters ran

A hook can't judge whether a question has merit; only the agent can. So the
design makes skipping the filters fail, and leaves the agent's verdicts to
review. It copies the two script calls the prose skill uses to prove its
rewrite pass ran (`.agents/skills/prose/DECISIONS.md`, *The rules are on
screen before a signature*):

1. `inquisitor.py vet --questions q.json`, given the picker's `questions`
   array, or `vet --post body.md`, given a post's body, prints the four
   filters, runs filter 1's search for each question, prints the hits, and
   issues a token holding the questions' hashes, never their text.
2. `inquisitor.py vet --pass <token> --verdicts v.json` records one verdict
   per question, keyed by the SHA-256 of its text.

So the calls prove the filters were printed and the search ran before each
verdict, not that the agent judged well. A hook allows a question when its
latest record is a fresh `ask`; the spec's *Two calls prove the filters ran*
and the entries under *Hooks and verdict records* hold the details.

The records live in `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`,
where prose keeps its session marks, for the same reason: a session spans
repositories, and a hook's working directory can differ from the one `vet`
ran in (prose's DECISIONS.md, *The gate blocks a session's first file
write*). They are the hooks' state, not a question log. Everything under one
HOME shares them, concurrent Igor workers included, since a verdict is about
the text, not the worker. Every record expires after 2 hours, so the skill
keeps no lasting record of any question, a vulnerability included. A
vulnerability's lasting record is the repository's private security advisory.

When a hook can't read the records, the picker hook lets the question
through and the post hook blocks a post that holds one. A picker question
publishes nothing, so at worst one unfiltered question reaches the person.
A post's unchecked question might be a categorized vulnerability, and a
published vulnerability can't be taken back.

**Rejected:**

- **A signed footer in the question,** as prose signs a post: the person
  reads the question in the picker, where a hash is noise.
- **The hook running the filters itself:** a hook is a script with no model,
  so it can't tell whether two options both have merit.
- **The skill's description alone,** with no hook: a model decides by
  judgement whether to load a skill, which is why *A picker hook makes
  agents run the filters* asks for a hook.
- **Records in the repository's git directory,** where prose keeps its pass
  tokens: a `vet` run in another repository would leave its records where
  the hook never looks.
- **Per-clone records,** as prose keeps its tokens: a verdict is about the
  text, not the clone or worker.

### What the hook relies on, not yet measured

Three facts about Claude Code are unmeasured (tasks 0.1 to 0.3): a
`PreToolUse` hook fires on `AskUserQuestion`; exit 2 blocks it and its
stderr reaches the model; and the tool's input carries
`questions[].question` and `questions[].options[].label`. If the first two
are false, the skill's instructions alone cover the picker, and the README
says so. If the input's shape differs, the question's text is redefined from
what the input holds.

### What task 0.12 measured

**An Igor worker can't run this skill** (measured 2026-10-20), read against
igor's main branch and the branches of igor PRs #174 (pinned skills), #175
(a worker as its own Unix user) and #216. The first bullet is measured from
igor's code; the second is read from #174's and #175's specs, since neither
is built yet.
- **Today:** a worker's Bash permission is only its role's `commands`
  (igor's `src/execute.ts`, line 1607, at 8478aec), so the skill's script
  runs only if a role lists it, and Read is refused outside the working
  tree. HOME is that of the user the Igor runs as, so `inquisitor.json` and
  a `gh` login are there only if a developer set them up, as under `igor
  run`, which runs an Igor on a developer's own machine, where `gh` would
  act as the person. Under `serve`, igor's mode as a deployed service, igor's
  deployment guide tells the operator not to log `gh` in as the service
  user, since a worker allowed to run `gh` could use that login (igor's
  `docs/deployment.md`, lines 112 to 115); task 0.14 measures whether a
  worker can.
- **After #174 and #175:** skills load only from `/opt/igor/skills`, and
  #174's task 5.1 installs only prose, bug-hunter and spec-trace. The lore
  checkout is mode 0750, which the worker can't read (#175's `design.md` at
  908c149, the row for "the Igor's home, lore checkout, `/etc/igor`"). The
  worker's home has no `inquisitor.json` and no `gh` login. Its only
  settings source is the empty user settings file igor writes for it
  (`--setting-sources user`), so it loads no hooks. The run is headless, so
  there is no `AskUserQuestion`.
- **Either way,** igor passes the worker no lore repository. Besides the
  item, the issue or pull request the worker works, fenced in its user
  message, the worker gets its system prompt,
  `workerSystemPrompt` (igor's `src/execute.ts`, line 161, at 8478aec): the
  role's name, the actions and commands its run may take, the role's
  standing instructions and the active lore entries the Igor injects. The
  Igor injects only the entries that fit the worker's token budget, so
  injected lore alone is not enough for filter 1.

So the spec's Igor-worker rules assume a worker with no inquisitor
configuration, no `gh` login or other GitHub credential, no picker and no
hooks, that can read only its working tree, its outbox and what its Igor
passes it. Besides its output, a worker could report to its Igor through
an outbox. igor PR #175 chooses which of the two channels a worker reports
through, such as for its citations. The worker
searches lore through `igor lore-search` (*Filter 1 in an Igor's run
searches through `igor lore-search`*), and the script knows it is in a run
by `IGOR_RUN` (*The script tells an Igor's run by `IGOR_RUN`*).

## Questions in posts

prose's posting hook reads the body of a `gh` post from a short allow-list
of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an
allow-list*). shared-skills PR #55 moves the part that splits a command
line into commands, and gh's flag tables, to `.agents/lib/gh-shell/`, where
spec-check's hand-back hook reads them too. This change moves the rest of
the reader, which finds a post's body, into the same library for both post
hooks; the `gh-post` spec states its rules. prose's tests are
unchanged except where the reader changes:
- **It reads two more forms of post.** The github-app skill tells agents to
  post through its script, `python3 <github-app script> gh pr|issue …`;
  under prose's rules alone that is unreadable, so every post an agent
  sends as a GitHub App would be refused. A `gh api` comment whose body
  comes from a body field or `--input` passes prose's rules unread, so it
  would skip both hooks. Every `gh pr` or `gh issue` post is readable
  only when it is the whole command line. A `gh api` write that takes a
  field from a file, by `@<file>` or `--input`, is readable only when it
  is the whole command line too, because an earlier command in the line
  could rewrite the file. A `gh api` write whose fields are all given in
  the command is read in a longer line as well.
- **It reports code given on the command line as unreadable on a line that
  mentions a gh post verb,** as it does `sh -c`: an interpreter, such as
  `python3`, `node`, `perl` or `ruby`, with a code flag such as `-c` or
  `-e` anywhere among its words, whatever the code runs, and `python3`
  reading its program from a heredoc or a pipe. On such a line `git`
  passes only with a subcommand on a fixed allowlist and no option that
  gives code to run. Each can run a post the reader never sees.
- **It reads a title,** so a question in a title is vetted as one in the
  body is. A title built by the shell, such as `--title "$(git log -1
  --format=%s)"`, or a title edit chained to another command, such as `cd
  x && gh pr edit 3 --title 'Rename?'`, is unreadable. prose's
  `DECISIONS.md` lets the chained edit pass (its paragraph "Titles are not
  checked"); task 1.3 updates that paragraph. A footer can't go on a
  one-line title, so prose's hook checks only that a title is readable, and
  lets a call with a title and no body through.
- **It blocks a `gh` alias or extension,** such as `gh co` or `gh dash`,
  wherever it appears, since an alias such as `c` for `pr comment` would
  send a post the reader takes for none.
- **It reads an unquoted body of one plain word,** such as `gh pr comment 5
  --body hi`, `-bhi` or `--body=hi`, as the body `hi`, as prose's reader
  does today. An unquoted body holding `$`, a backtick, `*`, `?`, `[`, `{`,
  `~` or `\` is unreadable, since the shell may change it before `gh` sees
  it.

A plain or bold line ending in a colon begins an open-questions section only
when its label names questions, such as "Open questions:". Agents often list
their open questions under such a line, and a deferred question listed there
passes on its `deferred` verdict. Outside an open-questions section, "Open a
terminal and run:" names no questions, so the commands after it need no
verdicts. A section ends only at
the next heading or bold label, so a plain colon line inside one ends
nothing.

The post hook allows a `deferred` question only when it tags no one and sits
where filter 2 puts a deferral: an open-questions or deferral section, or a
new issue. A question that tags someone asks that person for an answer, so
it needs an `ask` verdict however it was deferred.

**The order with prose:** do prose's pass, vet the rewritten body, then sign
it with prose. The footer prose appends holds no question, so signing leaves
the body vetted. An edit after vetting means vetting again; an edit after
signing means signing again too.

A subagent returns its question to whoever started it rather than opening
the picker: the session's person is talking to the starting agent, which can
batch the subagent's questions with its own.

`vet --post` finds a rhetorical question in a post too. Nobody needs to choose
an answer to it, so filter 3 stops it, and the agent rewrites it as a
statement. Its `decided` verdict names the post as where the choice is
recorded, since the statement in the post is the whole of the choice. A
rhetorical question outside a post, one the agent would have put to the picker
or in its report, it just rephrases as a statement and records nothing; the
`decided` verdict naming the post is for posts only.

## Where the logs live

**A question's log goes with what it concerns, at that place's privacy.**
The question is written for that privacy before it is asked (the spec's *A
question is written at the privacy of what it concerns*), so its log can sit
beside it.

- **A question about one repository:** a file under `.inquisitor/questions/`
  in that repository, committed with the work, so every agent on the team
  finds it, as `openspec/config.yaml` is found. A question about a change
  belongs in that change's history, so the file merges with it.
- **A question about an organization or project:** a file on the `questions`
  orphan branch of the team's lore repository, pushed directly. No review is
  needed, since a question's authority comes from who answered it, and the
  default branch stays uncluttered, holding only the lore entries Igor gives
  agents. The files hold no `conditions`, the frontmatter key that marks a
  lore entry, so neither the search nor Igor reads one as a lore entry.

  Anyone who can push may write any `answered_by`, and GitHub takes a commit's
  author login from the author email, which the committer sets. So a file
  there whose `authority` is `decision` needs a proven writer: a linked GitHub
  comment by `answered_by`, or a signature on the adding commit that GitHub
  verifies for `answered_by`'s account. The agent commits from the person's session, so after a one-time
  signing setup the person never signs an answer by hand. A file there never
  changes once pushed; a later answer is a new file. So a proof made on the
  commit that added a file covers everything the file says.

  An Igor worker holds no credential for the lore repository, so its Igor
  pushes the files the worker reports. The Igor accepts an answered file
  only when its `answer_link` points to a person's comment answering the
  Igor's handback question on the run's item (igor PR #216's decision 41),
  and checks every file with igor PR #217's credential matcher (#216's
  decision 28). Filter 1 then counts it as a decision only when that
  comment's author, or the person whose relay App posted it (the GitHub
  App that posts their answers; *Terms used throughout*), is
  `answered_by` and has write access. So a worker steered by text it read
  can't forge a person's answer.

  An answer worth giving agents as lore is promoted by a pull request adding
  a `provisional` entry; the question's file stays on its branch. Nothing
  goes to a lore repository more visible than the repository the question
  concerns.
- **A question about one person's way of working:** no log (below, in
  *Decisions*: *A way-of-working question gets no log*).
- **A question in one of the three categories** (`vulnerability`, `secret`,
  `personal`): no log. Of this skill's records, only the hooks' verdict
  record holds it, as a hash. In an Igor's run, igor keeps the category
  words, never the question's text, in an operator-only file on its host,
  with the session logs that hold the text moved beside it (igor PR #216's
  decisions 88, 89, 97 and 98).

The spec's *A log file and a miss file have one format* holds the files'
path, name, keys and encoding.

An answer logged with `input` authority, which can't stop a question, goes
only into the question's log file, never into a decision document (below,
in *Decisions*: *An answer without authority stays in its log file*).

A lore entry that stops a question gets a citation file, which igor's review
counts (*Citations go to the lore repository's questions branch*). A
citation holds nothing about the question, so even a private question gets
one. A categorized question gets none, since the cited entry would show
what it was about.

Every log file and miss file, and every question in a post, is scanned for
the credential patterns. The scan is only a backstop, since it knows only
token shapes: the agent keeps credentials out of questions and answers, and
a question that needs one gets the `secret` category.

**Rejected:**

- **A personal log under `~/.config/shared-skills/inquisitor/`** for a
  question about a public repository or about no repository: a question
  whose context was private would be kept, with that context, where only one
  person finds it. The question is instead written without that context, or
  not asked.
- **One file that every question appends to:** two branches that each append
  a line conflict when they merge, every time.
- **The git directory:** it is never committed, so the next agent on another
  machine would ask again.

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
unreviewed edit. The search reports when a fetch in this clone last updated
the default branch it searched, read from that branch's reflog, so the date
and the content searched come from the same ref; a clone whose reflog has no
such entry, such as a fresh one, reports "unknown". Two other sources would
give the wrong date. The skill's own fetch brings only the `questions`
branch, so its time says nothing about the default branch. `FETCH_HEAD` is
wrong too, since the skill's fetch rewrites it. The date is not when the branch
last moved on GitHub, and a fetch that brings nothing new writes no entry.

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

The configured `login` counts only when it equals the account `gh` is
logged in as, read running as the person, so nobody can claim a
maintainer's login by typing it into their own file. Run with an App's
token, `gh api user` gives no user. Run with the person's `gh` login, it
returns the person, which is why the script can confirm the configured login
but can't tell which login a post sent with the github-app skill's token
goes out as (task 0.7).

## The answer session

The answer session gives a person one place to answer the questions asked of
them on GitHub, Linear and Discord. A relay identity, a bot of the person's
own on each surface, posts each answer in the question's thread, and that
post is the answer's record. Its interface is a Claude Code mod, built from
the approved prototype build v0.1-33 (*The UI is built from prototype build
v0.1-33*). A UI approved by use is not specified, so nothing here describes
how it looks. The spec governs what the UI does and posts: where v0.1-33
does otherwise the spec wins, and screens the spec needs that v0.1-33 lacks
follow its patterns. The rules are in the `answer-session` spec, and the
decisions in the sections from *Answer-session configuration, setup and
relay identities* to *Linking log files to threads, and handbacks*.

### Polling while open, with the person's credentials

A webhook needs a public HTTPS server, and Discord's push a permanent
connection: either is a service to run, which nothing else in this skill
needs. So the answer session polls, only while it is open. Task 0.15 checks
that GitHub's notifications endpoint behaves as documented: a conditional
request that finds nothing new is answered `304` without counting against
the rate limit, `X-Poll-Interval` says how long to wait, and a mention
subscribes the person to its thread, so later replies there, to the relay
included, arrive as notifications too.

A relay identity may do other work, but only the answer session starts a
post with one of the four reserved prefixes, `User says: `, `User asks: `,
`Recorded answer: ` and `Inquisitor: `. Anything holding the relay identity
could post `User says: `, which marks a question answered on every machine
and, on GitHub, counts as the person's own answer to filter 1. So the
skill's instructions reserve the prefixes, and on GitHub the post hook
blocks a tool-call post starting with one, which never blocks the answer
session, whose posts reach no tool hook. On Linear and Discord, tool calls
in the holder, the session whose answer session holds the lock, cannot post
at all (*The model's own Linear and Discord posts are blocked*); in any
other session, nothing enforces the prefixes there.

### Local state, one writer per machine

There is no TLA+ model. Adam's rule asks for one where several processes
share state, and the lock is the only place that happens here. One person
uses the answer session, the lock makes one session per machine the only
writer of that machine's state, and the state shared across machines is the
threads, which each write appends to and each read re-fetches. The
interleavings left are two sessions racing for the lock, which an atomic
create or replace settles, and a take-over during a post, which the check
before each post settles.

### What the answer session posts, and what it logs

The mod posts a relay post by running the relay identity's skill as a host
command, not a tool call of the session's model, so no post hook sees it;
task 0.18 measures that. The command runs as an argument vector with no
shell, its text in a file or on standard input, because the person's answer
and drafts built from a thread's untrusted text reach it. A relay post on
Linear, or on GitHub outside a review thread, names its question with a last
`Re: <URL>` line, so that a thread holding several questions keeps a state
for each; on Discord a relay post replies to its question.

The relay file is YAML, matching the lore repository's other configuration,
under `relays/` in the lore repository holding the entries (igor PR #216's
decision 66). It lists the person's relay identities, one list per surface.
Only the `github` list proves anything, since only GitHub tells a reader who
wrote a comment. One file per
person, as igor's `seats/<id>.yaml`, lets the person's own pull request add
it, and its path, unlike a key in a shared file, names whose it is.

*Rejected:* a key of `igor.config.yaml`, since igor refuses any key it does
not read; and `inquisitor.json`, which is per person and on their machine,
where no other reader sees it.

The notice workflow, `relay-notice.yml`, warns a person of a pull request
that changes their relay file. Once merged, someone else's change would
stop the file counting (*Who last changed a relay file ties it to its
person*). It also warns them when someone else pushes to their own open
pull request, a push that counts as theirs once it merges. No reader of
relay files depends on the notice.

The pending-answer list reuses the approved queue's screens, so it needs no
prototype round of its own.

The tie between a relay App and its person holds only because nothing else
posts through that App unseen. github-app's `token` command breaks that: it
prints an App's token to any agent on the machine, which could then post
with a plain HTTP call no hook sees. Refusing it for a relay identity guards
against accidents, not a determined forger (*github-app refuses `token`,
`run`, `credential get` and `wire` for a relay identity*).

### What the answer session does by itself

The answer session runs all four filters on every incoming question, so the
person sees only what needs them. Posting without the person raises two
risks, and the spec answers each:

- **A thread's text reaches the model that judges it.** So the model writes
  no word of an automatic post, and a crafted question can at worst choose
  which fixed reply or which record is posted. Even that matters, since
  filter 3's and 4's replies tell the asking agent to decide the question
  itself. A crafted thread could then have an agent decide a question no
  person saw. So the agent acts by itself only on filter 2's reply, which
  only defers, or on one the person chose (*What an asking agent does with
  an automatic reply*).
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the thread;
  otherwise the person sees it and decides.

### The session's model

The model may ask the person in its reply in a discussion (*A discussion runs
in the session's own conversation*). The model posts nothing; its draft goes into the
prompt box. On GitHub the post hooks vet any post it tries; on Linear and
Discord, linear-app's and discord-bot's post hooks block it (*The model's
own Linear and Discord posts are blocked*). The
model's tools reach what the person's own commands can, the keychain holding
the Linear key included, as in any session. The answer session adds no guard
against that: it is the same exposure as the person's `gh` login. The
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
skipped test would not do: spec-trace counts a skipped test's tag as
coverage. Task 4.2, which writes the tests, lists each expected gap here by
name, and task 4.3 tags it once igor provides what it needs. The change is
archived only after every gap is tagged, since archiving moves its scenarios
under `openspec/specs/`, where spec-trace's CI fails on an untagged one
(*The change is archived only after every expected gap is tagged*). A gap
cannot be exempted through spec-trace's baseline,
`openspec/spec-trace-baseline.txt`, because the baseline takes no new lines
after adoption.

## Decisions

Each entry states the decision, its reasons and the alternatives rejected.

Terms used throughout, as the specs define them:

- **igor** is a separate project of AI teammates (adamstallard/igor). **An
  Igor** is one of those teammates, and its **worker** is the agent it
  starts to do an item. An Igor **injects** lore: it puts `active` lore
  entries into its workers' context unasked.
- **Lore** is a team's lessons for agents, kept as entries in a **lore
  repository** (*Lore repositories are configured as local clones*). A lore repository's
  **questions branch** holds question and miss files beside the entries.
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
  answer for them, starting `User says: `. On GitHub it is a GitHub App,
  the person's **relay App**, which their **relay file**,
  `relays/<login>.yaml` in the team's lore repository, lists. A **relayed
  answer** is a GitHub comment starting `User says: ` whose author is a
  person's relay App.
- **Gate one** is Adam's approval of this change's spec, in a pull request
  holding only the spec. **Gate two** is the implementation, built on the
  same branch after that approval.

### Asking a person

#### Four filters stop questions before a person

**Every question an agent is about to put to a person passes four filters
first.** The rule covers any agent in any task, not only spec review or
OpenSpec, and the skill is useful locally with nothing from Igor.

#### The Igor inquisitor role is out of scope

**The Igor inquisitor role, an Igor that brings surviving questions to a team
discussion, is out of scope; igor #211 tracks and governs it.** The role would
take over the questions behind items an Igor hands back, ask a blocked Igor's
question for it, received through the blocked item, keep a budget of posts per
channel, and route an Igor's handback comment. Under igor #211's decision 9,
in a team without the role nothing posts that comment to a discussion, batches
it or tags anyone, and nothing in this change does either. The filters a
blocked Igor runs on its own question are this skill's.

#### A deferred question stays visible

**A deferral stays visible: filter 2 lists the question as not done in the
current work, and also files it as an issue if it outlives the work, and a person
who wants the answer now says so.** The `deferred` verdict names where the
question will be listed, such as "this PR's description", not a link, because
that post may not exist yet.

#### A question that blocks no step waits for the round's end

**Only a question that blocks the step the agent is on is asked at once.
Every other question that survives the filters waits for the end of the
question round, and is asked then with the round's other questions.** In the
meantime the agent goes on with the answer it recommends, and the question
says the work assumes that answer. A round ends at a hand-back to a person
as spec-check defines one, or when the agent ends its turn or its run (spec:
*A question round ends at a hand-back or at the end of the agent's
turn*).

**Why:** each question asked mid-round interrupts the person. A hand-back
is when the person turns to the work anyway, so the round's questions cost
one read there. Because the question names the assumption, "yes" confirms
work already done, and any other answer says what to redo. The rework a
rejected assumption costs is bounded by one round.

**A pull request does not postpone a round to its hand-back: with a person
in the session, every end of the agent's turn ends a round too.** Ending the
turn hands the person control, so they read the reply then; questions held
until the pull request is handed back would sit unseen while the person is
there. Without a pull request there is no hand-back, so the end of a turn is
the only place a round can end.

**The hand-back is spec-check's,** so one word means one moment across the
skills. shared-skills PR #55 defines it in spec-check, and the spec cites #55's rule and
gives one example instead of copying #55's list of what counts as a
hand-back, so that list is kept in one place. The inquisitor's round also
ends at each end of the agent's turn, which spec-check's review round does
not, so it has a name of its own: a question round.

**How this differs from filter 2:** a deferred question is one the current
work does not need answered, so it is listed as not done and never asked in
the round. A question waiting for the round's end is one the work does need
answered: the work goes on, but on an assumption the answer may overturn.

**The agent vets the question again at the round's end.** A verdict record
lasts 2 hours, and an answer may have been recorded since the question
arose.

*Rejected:* asking every surviving question as soon as it arises, which
interrupts the person once per question. Ending a round at each push, which
shared-skills PR #55 rejects too: agents push after almost every commit, so every
question would still be asked almost at once.

#### bug-hunter's Step 9 recommendations go through the filters

**bug-hunter's Step 9 recommendations, which it asks the person about one at
a time, go through the inquisitor skill's four filters like any other
question, so fewer reach a person.** Task 5.7 changes bug-hunter's SKILL.md
so that Step 9 runs each recommendation through the filters before asking.
The task's table of starting rules is input to its design, not decided
behaviour: its implementer sets the final rules, and Adam reviews them with
the implementation. The spec fixes only that each recommendation passes the
four filters. Nothing in
bug-hunter changes before the inquisitor skill exists.

**Why:** every skill's questions go through one set of filters, rather than
each skill making its own exceptions.

*Rejected:* changing bug-hunter's Step 9 rules on their own, ahead of the
inquisitor skill: that would be a rule of bug-hunter's own that skips the
shared filters.

#### A prepared question can be answered "yes"

**A surviving question states the recommended answer, first in the picker,
so most questions can be answered "yes".** The picker hook need not check the
order: reordering options after vetting changes the question's text, which
the hook blocks as unvetted.

#### With a person present, ask through the picker

**With a person in the session, on a host with a picker, an agent never asks
in its reply; a subagent hands its surviving questions back to the agent that
started it.** On a host with no picker, the agent asks in its reply once the
two calls vet the question. An answer session's discussion is an exception
(*A discussion runs in the session's own conversation*).

**Why:** the picker hook then sees every question. The starting agent is the
one talking to the person, and can batch a subagent's questions with its own
(*Questions in posts*).

*Rejected:* a hook at the end of the agent's turn that reads questions in its
reply: the person has already read the reply when it runs.

#### How a session with no person asks

**A session with no person in it never uses the picker, which is for a person
to read.** It posts its question if it can, such as a scheduled agent; an Igor
worker, which holds no credential that can post, asks in its handback comment;
a session that can do neither asks nowhere, stops only if the work needs the
answer, and reports the question. Task 0.9 measures how a session tells
whether it has a person.

A session with no person in it never asks or posts a `secret` or `personal`
question, and asks a `vulnerability` question only in the repository's
private security advisory. It stops the work that needs the answer and
reports only that a question of that category is blocking, with no text.
During an Igor's run, the worker raises igor's flag in place of that report
(*The flag a worker raises for a question with a category*). A way-of-working question is held
back the same way: the session stops only if the work needs the answer, and
reports that the question waits for the person (spec: *A session with no
person in it holds back a question with a category*).

**Why:** counting an unclear session as having no person means a picker is
never opened with nobody to answer it.

#### A question's audience is no wider than its subject

**A question goes only where its audience is no wider than what it concerns,
in every channel, Linear and Discord included.** Where the place would be
wider, or the agent cannot tell, it asks through the picker. With no person
in the session, where the place would be wider it posts in the repository the
question concerns, or, for an organization's or project's question, in the
repository holding the current work. Where it cannot tell, it posts nothing
and says so.

#### What counts as a question in a post

**A question in a post is each list item in an open-questions section, and
each other sentence ending in a question mark, as the spec's *A question in a
post is a listed item or a sentence ending in a question mark* defines once.**
A section of questions begins only at a heading, bold label or plain colon
line whose label names questions or a deferral, as the spec's scenarios list.
A post is vetted after prose's pass and before prose signs it; *Questions in
posts* gives the reasoning for colon lines and for that order.

**Why:** the rule lives in one function, so it is cheap to change.

*Rejected:* letting any colon line starting with "Open" begin a section: "Open
a terminal and run:" would turn its commands into questions.

#### A deferred question passes only untagged, listed or in a new issue

**A `deferred` verdict less than 2 hours old passes the post hook only for a
question that itself tags no one and is an item of an open-questions section or
in a post that creates an issue, even when another part of that issue tags
someone; anywhere else the question needs an `ask` verdict.** Filter 2 defers a
question to one of two places: a list of what is not done, or an issue when the
question outlives the work. An open-questions section is where the agent writes
that list, in whatever post reports the work, and a new issue is the second
place. The hook lets a deferral through in those places only.

**Why:** tagging someone asks them, which needs an `ask` (*Questions in
posts*). A deferral expires like any record (*Every verdict record expires
after 2 hours*).

#### One person who can decide is tagged

**A question in a post tags the first candidate the script finds with write
access to what the question concerns.** The spec's *A question in a post
tags one person who can decide, if there is one* sets the tagging order: the
approver of the related earlier decision the second call recorded, then a
login in
`.inquisitor/reviewers`, then the last committer of the files involved.

**Why:** only a person with write access can decide.

#### The configured login names the person

**The person running the session is the configured GitHub login only when
`gh` is logged in as that account.**

**Why:** checking it against the person's own `gh` login, never a GitHub
App's token, stops anyone claiming a maintainer's login by typing it into
their own configuration.

*Rejected:* taking the login from `gh api user` where the agent posts: as a
GitHub App it gives no user, and as the person it gives their own login, so
the agent would tag itself.

#### When no candidate can decide

**With no candidate holding write access, the script turns to the session's
configured login, and tags it only when it has write access and the post goes
out as someone else.** With a person in the session and no login
configured, the agent asks through the picker. When the configured login
lacks write access, the question tags no one, even with a person in the
session. With no person in the session, a post going out as the configured
login tags no one. A question that tags no one is posted with a line saying
no one with authority to decide could be found (spec *A question no
candidate can decide turns to the session's login*).

**Why:** a self-tag sends no notification, so where the post goes out as that
login, a session with a person in it asks through the picker instead.

### Hooks and verdict records

*Proving the filters ran* gives the reasoning for these hooks and records, and
the alternatives rejected: the skill's description alone, a hook that runs the
filters itself, a signed footer inside the question, records in the
repository's git directory, and per-clone records as prose keeps its tokens.

#### A picker hook makes agents run the filters

**A hook on Claude Code's question picker (`AskUserQuestion`) makes an agent
run the inquisitor before it asks.** *What the hook relies on, not yet
measured* says what happens if tasks 0.1 to 0.3 show that a `PreToolUse` hook
cannot block the picker.

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
standard input, never in a file. Every other question in the same picker
call, with its verdict, goes on standard input with it, uncategorized ones
included.

**Why:** in a shared temporary directory such as `/tmp`, a file with the
usual mode, and the question's text in it, is readable by every user of the
host. Outside any repository, the files can't be committed.

*Rejected:* the system's temporary directory, for that reason.

#### Verdict records live in the user's state folder

**The hooks' records live in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`, beside prose's session
marks.** They hold hashes, verdicts, verdict fields and times, never a
question's text, so they are the hooks' state, not a personal question log.

#### An `ask` record drops the option's label

**A picker `ask` record keeps, for each option other than the one the agent
recommends, the agent's own words from its verdict on what that option would
change, but no option's label,** since the labels
are part of the question's text, which no record holds.

**Accepted:** the records can't show later whether the person took the
recommendation.

#### Verdict records are shared under one HOME

**Everything that runs with the same HOME shares one set of verdict records,
Igor workers included,** so one worker's verdict on a text lets another
worker ask that text.

**Why:** a verdict is about the question's text, not the worker.

#### Records hash a question with plain SHA-256

**A verdict record identifies its question by the plain SHA-256 of its text.**

**Accepted:** a short sensitive question could be guessed from its hash, but
only for 2 hours, since every record is deleted then, whether or not the
agent gave the question a category.

*Rejected:* an HMAC with a per-HOME key, which would stop that guessing: the
2-hour limit already keeps the exposure brief.

#### Every verdict record expires after 2 hours

**Every verdict record is deleted 2 hours after it was made, whatever its
verdict or category.** Each hook accepts a record only while it is less
than 2 hours old and treats an older one as missing, so deleting a record at
2 hours removes nothing a hook would still accept. A post
edited more than 2 hours after an `ask`, or listing a question deferred more
than 2 hours earlier, is vetted again, which costs only one pair of calls.

**Why** a `deferred` record without a category expires as well: a deferral
asks nothing, so its record could have been kept until the question is
listed, sparing a second vetting. But the agent may leave a sensitive
question uncategorized, and its plain hash could then be guessed for as long
as the record lasts (*Records hash a question with plain SHA-256*).

**Why:** a lasting record of a categorized question would be either personal
or public. Kept on the person's machine, it would be a personal question log,
which the skill rules out. Kept with the questions, it would show in a public
repository that such a question was asked, and when.

#### A hook spends no verdict record

**The picker hook and the post hook spend no verdict record.** When one
question blocks a call, the agent vets that question alone and calls again,
and the call's other questions need no vetting again.

#### The related-decision line is left out of the hash

**The hooks match a question's text without its related-decision line.** That
line is `Related: ` and one URL with no spaces, on a line of its own (spec *A
related-decision line is one URL on a line of its own*). The related decision
turns up in the first call's search; the agent names it at the second call,
which records it with the verdict, and adds the line after that call with no
further vetting. No vetting sees the line. That is why both hooks block a
related-decision line holding a credential pattern.

**Accepted:** the agent links only a decision that everyone who can read the
question can read, and no hook checks that.

#### What each hook does when it can't read

**The picker hook lets a question through when it can't read its input or
its records. The post hook lets through input that is not JSON; it blocks a
`gh` command whose body it can't read, and a post holding a question when it
can't read its verdict records** (spec *The post hook vets what the shared
post reader returns*).

**Why:** an unfiltered picker question publishes nothing, but a published
vulnerability can't be taken back (*Proving the filters ran*).

#### The host's transcripts are outside the skill's records

**The skill's rules on its records, hash only for a question with a category
and the 2-hour expiry, cover only its own records.** The host's transcripts,
such as Claude Code's under `~/.claude/projects/`, are outside its control.

**Accepted:** those transcripts hold a question asked through the picker in
full.

### The shared post reader

#### Questions in posts pass the filters, on GitHub only

**The post hook enforces the filters for GitHub posts only, sent through `gh`
or a GitHub MCP tool, as prose's posting hook covers GitHub only.** A question
in a Linear or Discord message is covered by the skill's instructions alone.

#### One post reader, shared by both hooks

**prose's posting hook and the inquisitor's post hook read every post through
one library, `.agents/lib/gh-shell/`, so every rule the reader gains applies to
prose's hook too.** spec-check's hand-back hook reads command lines through
the same library (shared-skills PR #55), so a line the post hooks find
unreadable is unreadable to it as well, and no second copy of the reader
drifts from the first. The `gh-post` spec states its rules, taking the finer
points of reading a line, such as heredocs, comments and line continuations,
from prose's `DECISIONS.md`. *Questions in posts* gives the reasoning, and
which prose tests change.

*Rejected:* a copy of prose's reader in the inquisitor: prose's parser had
about 25 places where it misread commands before it was cut to an allow-list.
*Rejected:* calling prose's copy from the inquisitor: it would fail whenever
prose is not installed.

#### Which commands the reader judges, and which are unreadable

**The reader judges only a command line that mentions a gh post verb, and
reads it through an allow-list. It finds the line to be one of three things:
a post it reads; no post, because no simple command in it sends text; or
unreadable. Both post hooks block an unreadable line. A gh alias or extension
is unreadable on every line.** The `gh-post` spec states the rules: *A command that mentions
no gh post verb sends no post*, *The reader reads only gh's own top-level
commands*, *A command that only runs prose's script sends no post*, *A line
whose simple commands send no text is no post* and *Any other line that
mentions a gh post verb is unreadable*.

**Why:** these are prose's reader's rules, apart from the alias rule and
counting `gh api` as a mention (*The post reader's open costs*). An
allow-list fails closed: a form it cannot read, such as `sh -c '…'` or
`eval '…'` around a gh post, is blocked, never let through unread. The reader
cannot read what an alias or extension runs: with `c` aliased to `pr
comment`, `gh c 5 -b 'User says: yes'` names no gh post verb, so passing it
would forge a relayed answer past both hooks' block (*The post hook blocks a
reserved prefix on GitHub*). prose's hook gains the alias rule too.

**Accepted:** gh's default alias `gh co` and read-only extensions such as
`gh dash` are blocked for every prose user.

*Rejected:* letting a command through when `gh` appears in it only inside
quotes: `sh -c 'gh pr comment …'` would then post unread.

#### Code given on the command line beside a gh post verb

**On a line that mentions a gh post verb, an interpreter with a code flag
anywhere among its words, such as `python3 -W ignore -c` or `node -pe`, makes
the line unreadable, whatever the code runs. On such a line `git` stays a
data command only when the first word after `git` is a subcommand on a fixed
allowlist of ones that take no code to run, and no option gives code to run,
such as `-c`. So `git -C . status` is unreadable there, since `-C` is not an
allowlisted subcommand.** The
`gh-post` spec states the rules: *An interpreter given a code flag makes a
post-verb line unreadable*, *Only allowlisted git is a data command beside a
gh post verb* and, for a program read from a pipe or heredoc, *Input to a
no-post line reaches only data commands*.

**Why:** each of these can run a post the reader never sees. A program piped
into `python`, `python3` or `node` is read from that input, and telling which
script runs would mean reading the interpreter's options, so any input
reaching one makes the line unreadable. Finding the code
flag without reading the interpreter's options means an option that takes a
value, such as `-W ignore`, cannot hide it. A list of git forms that run code
is never complete, as prose's `DECISIONS.md` says (`git config alias.p '!…' &&
git p`, `git difftool -x`, `git filter-branch --tree-filter`); a list of
subcommands that never take code is. prose's hook calls the same reader, so it
blocks these forms too. prose's `DECISIONS.md` today calls a script handed
to another interpreter (`python3 - <<'EOF'`, `node -e`) and git aliases
outside its hook's reach, so task 1.3 removes that claim.

**Accepted:** `git commit` and `git push` run the repository's git hooks,
which can run anything; that is outside this reader.

#### Posts sent through the github-app skill's script

**A post sent through the github-app skill's script is read as the `gh`
command it runs, when the script's path ends in `/github_app.py` and is
written out or a `$G` the line assigns first; a line that mentions a gh post
verb and runs `python3 $G` with `G` unassigned is unreadable.** The `gh-post`
spec's *The reader reads posts sent through the github-app skill and gh api*
states the forms. Task 5.5 makes each example in the github-app skill's
`SKILL.md` set `G` in the same command or write the script's path.

**Why:** otherwise every `gh pr` or `gh issue` post an agent sends as a GitHub
App would be blocked. A `gh api` call through the script, a read included, is
unreadable and so blocked (*The post reader's open costs*).
The reader cannot know what any other script posts. An unset `$G` posts
nothing in Claude Code, where each command starts a fresh shell, but could in
a host whose shell keeps variables, such as Cursor; blocking it costs only a
rewrite.

#### The reader reads gh api writes, REST and GraphQL

**A `gh api` write returns the body and title the reader reads from it, and is
unreadable when it has a field, title or `body` the reader can't read, or
sends a `body` to an endpoint or mutation the reader does not read; any other
`gh api` call sends no post. A write that takes a field from a file, by
`@<file>` or `--input`, is readable only when it is the whole command line.** The
`gh-post` spec states the rules: *The reader reads a gh api write to an issue
or pull request*, *A gh api write read from a file is read only as a whole
command line* and *The reader reads GraphQL posts and blocks a gh api write
it can't read*, which lists the thirteen mutations that post text and makes
any query the reader cannot parse unreadable.

**Why:** otherwise a `gh api` comment would skip both hooks unread, while
reads and writes that send no text, such as label edits, pass. A GraphQL
mutation is a write like a REST one, so the same rule applies. An earlier
command in the line, such as `printf 'unsigned' > c.md`, can rewrite the file
a write reads, as prose's `DECISIONS.md` says of `--body-file`; a field given
in the command cannot be rewritten, so such a write may stand in a longer
line.

*Rejected:* reporting every GraphQL mutation as unreadable: it would block
writes that send no text, which the REST rule lets through.

#### A post's title is read and vetted

**The reader returns an issue's or pull request's title with its body: the
inquisitor's hook vets a question in it, and prose's hook checks only that it
is readable.**

**Why:** otherwise a question in a title goes out unvetted. *Questions in
posts* says why prose's hook checks only readability.

#### The post hook blocks a reserved prefix on GitHub

**The inquisitor's post hook blocks a tool-call post on GitHub whose body
starts with a reserved prefix.** Before it compares, the hook reduces the
body as a question in a post is reduced for its hash: inline markup becomes
its text, and whitespace is joined. It then drops leading whitespace. So
` User says: ` and `**User says:**` are blocked too.
The last paragraph of the overview's *Polling while open, with the person's
credentials* gives the reasoning for reserving the prefixes.

**Why:** the answer session posts through a host command that no tool hook
sees, so a tool-call post with a reserved prefix is never the answer
session's. A `User says: ` comment from the person's relay App proves their
answer, and that App may do other work, so the block stops an agent holding
the App from forging an answer through `gh`.

**Accepted:** outside the holder, nothing checks a reserved prefix on Linear
or Discord. A forged `User says: ` there would mark its question answered in
every answer session, but filter 1 would never count it as the person's
answer, since a relayed answer on those surfaces proves nothing; the skill's
instructions are the only guard.

*Rejected:* reducing the body as a comment is reduced for comparison with a
recorded answer (*A linked comment holds the answer only when the texts are
equal*): that drops a leading `User says: `, so the block would never see the
prefix it blocks.

#### No exemption for an Igor's handback

**The post hook vets a post carrying igor's handback marker like any other.**

**Why:** a marker any agent can add would let a post bypass vetting, and an
exemption would help no real handback: an Igor posts its handbacks through
its own code, which the hook never sees.

*Rejected:* recognising a handback by the marker and an `igor-` App author
together, since no real handback reaches the hook.

### Logs and privacy

#### Every asked question is logged with what it concerns

**Every question asked is logged with what it concerns, a repository or the
team's lore repository, at the privacy that place's maintainers set, so the
next agent finds the answer instead of asking again.** The agent does not ask
a question that concerns no repository, no organization or project, and not
one person's way of working. The skill's instructions say so, and nothing
enforces it. If the agent asks such a question anyway, it is logged nowhere.
If it asks one in a post, the post tags no one. No question log is kept anywhere personal. The spec names the questions
that get no log file; *Where the logs live* gives the reasoning.

*Rejected:* a personal log under the home directory: it would keep a
question, with its private context, where only one person finds it.

#### A repository's questions are committed with the work

**One repository's question is a file under `.inquisitor/questions/`,
committed with the work, not on a branch of its own.** For another
repository, the agent opens a pull request with the file without asking
first, since the current work's commits can't carry a file there. Each file's
name has a random suffix, so two branches that each log a question never
write the same file.

**Why:** a change's questions belong in its history, and merge with it.

**Accepted:** until the work merges, its log file is invisible to parallel
work, so an agent on another branch may ask the same question again. A file
pushed to the lore questions branch has no such cost: the next fetch finds it.

#### Organization questions go on lore's `questions` branch

**An organization's or project's question goes on the orphan `questions`
branch of the team's lore repository, not igor's `igor-state` branch, which
holds igor's runtime state.** It holds questions not important enough to
become lore but worth keeping so nobody asks them again. Nothing on it is
given to agents as lore, and it has the lore's privacy and access. Promoting
an answer to lore is a pull request adding a `provisional` entry to the
default branch, and the question's file stays on the questions branch.
*Where the logs live* gives the reasoning.

#### A way-of-working question gets no log

**One person's way-of-working question, such as "should I keep working while
you're away?", is not logged,** because agents already read where its answer
goes: that person's agent memory or user-level `CLAUDE.md`. The answer never
goes into a committed `CLAUDE.md`. Every agent in that repository reads a
committed one, so it would apply one person's way of working to everyone.

#### prose's pass skips `.inquisitor/`

**prose's pass skips files under `.inquisitor/`** (task 5.6). A log or miss
file quotes a question as asked, and what a person said, word for word;
prose's rewrite would change it.

#### Nothing goes somewhere more visible than its source

**Nothing goes to a place more visible than what it concerns, ranked
private, internal (visible to a whole enterprise), then public, and an
unreadable visibility counts the cautious way.** The script's refusal to open
a lore pull request to a more visible lore repository also covers pushing a
question to its questions branch and promoting an answer from there.

**Why:** a question's record keeps the privacy of what it concerns. Each
default makes the cautious choice, so nothing is sent somewhere that might be
more visible. So a log file's `asked_in`, the URL of the post where its
question was asked, is withheld when that post is private, unless the lore
repository is private too. *Configuration* gives how visibility is read.

#### Records are written at the question's privacy

**A question, a miss's record of what the person said, and an agent's own
choice are written at the privacy of what the question concerns: more private
context is generalised or left out.** A question that cannot stand without
that context is not asked, and is never filed in a more private place to keep
it. A person's answer is never generalised: it is recorded in their own words
or not at all, and then the question stays open.

**Why:** writing at the question's privacy covers everything recorded about
it, and a person's answer, kept in their own words, can't be generalised.

#### Three categories are recorded by hash only

**A `vulnerability`, `secret` or `personal` question is kept in none of the
skill's records in readable form. The filters still run on it, and the agent
may still ask it, but only through the picker or, for a `vulnerability`, the
repository's private security advisory.** A post would keep the question's
text where the thread's readers see it, so such a question is never asked in
a post (spec: *A question with a category is asked only through the picker or
its advisory*). The post hook therefore blocks every post holding a question
whose latest verdict record has a category (spec: *Some questions are recorded
by hash only*). The script records its hash, verdict, time and category, because
the picker hook matches a question's exact text against its latest verdict.
Filter 1 searches for such a question only in files on the machine, never
in GitHub's issues, so its text
never reaches GitHub's search. A vulnerability's lasting record is its fix
and the repository's private security advisory.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### The secret scan is only a backstop

**The script refuses a log file, miss file or question in a post matching the
credential patterns, but the scan catches known token shapes only: a
`DB_PASSWORD=…` passes it.** So the agent never puts a credential into a
question, an answer or a verdict field. The patterns include the two
credentials this change puts within the session model's reach: Linear's keys,
since the discussion's model runs with the person's tools and can read their
Linear key from the keychain, and a Discord relay's bot token. That token's
pattern bounds each part to Discord's shape, 24 or more characters, then 6,
then 27 or more, so dotted text such as `1.15.0` or `spec.md.bak` is not
refused. *Where the logs live* gives the reasoning.

The scan reads raw markdown, link targets included, while the hash uses the
reduced text, since a token in `[docs](https://x/?token=ghp_…)` reduces to
`docs`. The post hook scans each question's raw markdown again just before
posting, so a token added to a link target after vetting, which leaves the
hash unchanged, is caught.

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
- The risk exists only while the fix is public and the advisory is not.
  GitHub's private advisories come with a temporary private fork, whose
  commits become public with the advisory, so a fix made there is not public
  before the advisory is. That holds only if the fork's pull request can't
  merge first, which task 0.13 measures.
- A blanket rule would leave a fix's commit message useless even after
  disclosure. That breaks rule 14 in the prose skill's `rules.md`: a commit
  message's body says why.
- A fork pull request merged before publication would put the regression test,
  a working exploit, on a public branch early.
- Until task 0.13 shows that the fork's pull request merges only at
  publication, the person who will publish the advisory can tell the agent
  that it will. That statement lets the agent commit the regression test in
  the fork. It also lets a fork commit's message describe the weakness, since
  the description reveals less than the test, which is a working exploit.

*Rejected:* keeping a vulnerability question and its answer out of a fix's
commit messages, pull request text and comments: the weakness can be described
in other words, and the rule would leave the commit message useless after
disclosure.

### Which answers count, and citations

#### Only an answer with authority stops a question

**Filter 1 stops a question only with an answer that has authority; every
other hit is shown to the agent as labelled input.** The spec's requirement
of this name lists the kinds; the entries below give the reasons for their
conditions.

#### A decision on the current work's branch answers that work

The spec's *A work-branch decision answers only its own work* sets the
conditions. A `decision` or `agent` log entry on that branch counts only under
those same conditions (*A log entry counts only where its branch allows*). No
signature is required.

**Why:** without those conditions, an outside contributor could commit a decision that
stops the agent's questions. Pushing a branch to the repository itself
already needs write access; a fork's branch does not.

#### A logged decision counts only where its branch allows and its author has access

The spec's *A log entry counts only where its branch allows* says where.

**Why:** `authority` is a field anyone can write, so the file alone proves
nothing.

#### An agent's choice counts only in the work it belongs to

An `authority: agent` file on a `questions` branch is pushed so later agents
see the context, though it never stops a question. It is never sent to
another repository by pull request.

#### An answer without authority stays in its log file

An `input` answer never goes into a decision document, because on the
current work's branch a decision document counts as an answer, so the
agent's own write would turn input into a decision.

#### An agent logs `decision` only for an answer it can prove

A signature on a commit made in the person's session proves only an answer
the person gave in that session.

#### No file on a questions branch changes once pushed

A later answer is a new file holding the question and the answer, so the
proof on its own adding commit covers everything it says.

#### A questions-branch decision needs a proven writer

The spec's *A questions-branch file's writer is proven by its comment or its
signature* holds the two proofs. The signature needs a one-time
commit-signing setup on the person's machine; the agent commits from their
session, so they never sign an answer by hand. In a project set up for a
GitHub App, the github-app skill commits as the bot, unsigned, so there an
agent's questions-branch `decision` needs the comment-link proof. The answer
session's answer files are the exception: it commits them as the person,
signed (*Setup checks questions-branch commits are the person's*).

**Why:** anyone who can push can write any `answered_by`, and GitHub takes a
commit's author login from the author email, which the committer sets.

*Rejected:* matching the commit's author login to `answered_by`: anyone with
push access can forge it.
*Rejected:* treating every `questions`-branch file as input: the branch could
then never settle a question.

#### A questions-branch decision counts by write access to what it names

**A questions-branch file holding `repository` is about that one
repository, and counts as a decision only from a writer of it; a file
holding no `repository` is about an organization or project, and counts
from a writer of the lore repository.** `repository` always names the
repository the question is about, and only a file about one repository
holds it; `asked_from` names where the question was asked (*Every
questions-branch file names where it was asked from*). A reader never
compares the two keys, so a file whose keys are equal, such as an Igor's
question about its own item's repository, counts by write access to that
repository.
Authority to instruct never exceeds authority over the artifact the
instruction is about, as igor states it (igor PR #202's decision 11, and
igor's rule for directed interaction). A writer of the lore repository may
have no say over `o/api`, so their answer about `o/api` is input, wherever
the file holding it sits. A permission that cannot be read counts as no
authority, as every write-access check here fails closed.

*Rejected:* checking the lore repository's writers for every
questions-branch file, which would let a lore writer decide for a
repository they cannot change.
*Rejected:* `repository` naming where an organization's question was
asked, with readers comparing it to `asked_from` to tell the cases apart.
A file about the Igor's own item's repository would then have equal keys
and count by the lore repository's writers, as an organization's does.

#### A signature GitHub may have made counts for no one

**Why:** GitHub signs a commit it makes itself, such as one from its web
editor or its contents API. If GitHub verified such a commit for an account
that did not make it, anyone with push access could make a commit that proves
another person's answer or relay file. Task 0.22 checks that, and records how
a reader tells a signature GitHub made from the person's own.

#### A logged answer is the person's own words

**A person's answer is recorded word for word, never as an agent's
paraphrase, by every writer: the skill's script, the answer session and an
Igor.** The answer text a worker or agent passes with a link only identifies
which comment holds the answer. Frontmatter `authority` decides whether a log
file is answered, so a `## Answer` line inside a question's text changes
nothing. igor PR #216 records the writer side of this rule as its decisions
67 and 70.

**Why:** readers confirm a comment-linked answer by comparing texts, so one
rule must bind writers and readers alike.

#### A log file's answer is written as quote lines

**Why:** every answer line starts with `>`, so a whole comment fits, even one
holding a `## Answer` line of its own.

*Rejected:* joining the comment onto one line: it breaks the equality test
between a comment and its recorded answer for a comment with list items.
*Rejected:* a frontmatter key counting the answer's lines: the quote marks
make it needless.

#### The `log` command reads its inputs and the linked comments itself

The command does not check who passed an `answer_link` or an `asked_in`: who
passed a link proves nothing about who wrote the answer, and any proof of the
writer comes from the linked comment or the commit's signature.

**Why** inputs go in a 0600 file, never arguments: a question's text and its
answer passed as arguments are readable by every user of a shared host.

**Why** it refuses a question holding a line `## Rephrased question`,
`## Discussion` or `## Answer`: a reader takes those lines from a log file's
end, so an untrusted question ending in forged rephrasing lines would read
back as a shorter question, and a writer's answer would be recorded against
a different text and hash. The agent rewords such a question.

*Rejected:* escaping those lines: a reworded question reads the same to a
person, and an escape is one more form every reader must undo.

#### A linked comment holds the answer only when the texts are equal

No model judges the comparison; the spec's *A linked comment holds the answer
only when the reduced texts are equal* gives the full reduction.

*Rejected:* counting a comment that contains the answer: it let "merge it."
match "Do not merge it.".

#### An answer typed on another surface counts only through a decision document

A linked answer is only a github.com comment or review, so an answer typed
directly on Linear or Discord can't be one. An answer the person typed in the
answer session, which the session then relayed to Linear or Discord, is not
typed there: it counts through its commit's signature (*Questions-branch
answers relayed on Linear or Discord*).

**Why:** only GitHub tells a reader who wrote a comment.

#### Citations go to the lore repository's questions branch

**A lore entry that stops a question gets a citation file on that lore
repository's `questions` branch, holding nothing about the question.** A
stopped question is not asked, so it gets no log file, and its citation is
its only record. No log file names a lore entry by its id either: the
`recorded_in` key of an answered log file, which says where the answer is
recorded, is a path or URL and never a lore entry. This change defines the
one citation format, and igor PR #216 points to it, since the inquisitor
and an Igor both write citation files and igor's review reads them all. The run's id in a citation is
opaque; the Igor records it in the run's row of its execution ledger on its
`igor-state` branch, not with the transcript, and igor's review shows each
citation's run and item (igor PR #216's decision 10).

**Why:** igor's review, which prunes and promotes lore entries, counts each
entry's citations in one place beside its fire count, and needs nothing
about the question, so a private question gets a citation too.

*Rejected:* a `cites` field in the question's log file: a question that
filter 1 stops gets no log file.
*Rejected:* counting raw search hits instead of citations: no reason is
recorded.
*Rejected:* a hash of the question in the citation: the count needs nothing
about the question.

#### Questions-branch commits are machine records

That branch is never checked out, so prose's and bug-hunter's checks never
see these commits; at archive, their `DECISIONS.md` files say so. igor
PR #153, igor's signed-publishing change, should exempt an Igor's citation
commits from the trailers it requires on an Igor's commits; that is #153's
to settle.

#### A citation's commit names no person

Its fixed author, day-only date and lack of signature say nothing about who
asked. `git -c commit.gpgsign=false` keeps a person's signing setup for the
writer proof from signing a citation with their key.

**Accepted:** GitHub's events API still records each push's pusher and time,
visible to anyone who can see the lore repository. That repository is never
more visible than the question's.

### Lore and misses

#### Lore repositories are configured as local clones

The spec's Purpose holds the keys (`lore`, `path`, `owners`, `repos`) and
defines *lore repository* as the one holding the entries, which igor PR #216
calls the *destination repository* (#216's decision 66). Relay files and the
questions branch live beside the entries, so the inquisitor reads both there.
igor's specs use the same words for a different repository. Under igor
PR #208 an Igor's configuration lives in one repository, which may name
another holding the entries, and igor calls the first one the lore
repository. In this change the term always means the one holding the
entries. *Configuration* gives an example file.

*Rejected:* refusing two lore repositories that list the same owner: they can
serve it for different projects.

#### Filter 1 searches lore in every session

**Why:** the search is how lessons reach plain Claude Code sessions, which no
Igor injects lore into.

#### Lore search is as fresh as the last fetch

Filter 1 fetches only the `questions` branch, and reads each clone's default
branch as last fetched.

**Accepted:** an entry merged since the person's last fetch is not found.

#### Scope hides an entry; status only labels it

**Why:** igor treats scope as visibility, so an out-of-scope entry is one the
asker may not see. Status only labels an entry because a search is not
injection: the agent asks for a search's results, while igor injects entries
unasked. igor promises that no unreviewed lesson is injected into a worker
before it merges. Showing labelled `provisional` and `deprecated` entries in a
search injects nothing, so it keeps that promise.
igor PR #216 decides the same on igor's side.

#### A project scope matches the repository's short name

That is igor's rule (`scopeMatches` in igor's `src/firing.ts`).

**Accepted:** a project whose repositories have other names needs a mapping
file in the lore repository, read by igor and the inquisitor alike, which
this change does not build.

#### Filter 1 searches igor's scribe's records where #202 puts them

**Filter 1 searches the decision records that igor's scribe keeps at the path
igor PR #202 sets, both in the repository the question concerns and in the
lore repository.** The scribe is the Igor role that records a discussion's
decisions. *Open Questions*
tracks that path. A decision record that carries a status, such as a MADR,
counts as an answer only when its status is `accepted`; any other status is
shown as input. That holds wherever filter 1 reads decision records, the lore
repository's included.

**Why:** #202's decision 5 puts a record in the repository the decision
concerns, or in the team's lore repository when it spans repositories, so
filter 1 reads both. A rule that depends on igor is specified in its end
state.

*Rejected:* a fixed `docs/decisions/` until #202 settles the path: an interim
design for an igor dependency while igor has no users.

#### A general answer is proposed as a provisional lore entry

The agent opens the pull request without asking first. During an Igor's run,
the run puts the entry in its report, as it does its question and miss files,
and the Igor opens the pull request.

**Why:** a pull request is itself a proposal, and closing it is cheap.

**Why** the Igor opens it in a run: there the script pushes nothing to a lore
repository, and the Igor already pushes the run's other files.

#### A proposed entry's id follows igor's id rules

**Why** the Igor stops on "id taken": igor reports a collision outside the
run's scope only as "id taken", which does not say what holds the id. If an
entry holds it, another id would do. If a rejected candidate, a file under the
lore repository's `rejected/`, holds it, the entry may not be proposed at all. The Igor cannot tell which, so it proposes nothing.

#### Lessons from misses are drafted on request and land by scope

Misses change the skill only through lessons sent by pull request or memory
edit, never automatically.

**Why** shared-skills gets only a generalized lesson: question and miss logs
can hold private content, so they stay with the repositories they concern.

*Rejected:* the script refusing a lesson that quotes a logged question: a
lesson in general terms never does.

### Igor workers and Igor runs

#### The script tells an Igor's run by `IGOR_RUN`

Despite its name, Igor-worker mode is how the script runs in any Igor's run,
including one the Igor starts itself with no worker. Only the `IGOR_RUN`
value `worker` limits filter 1's sources other than lore to the worker's
working tree. igor PR #216 sets the
variable (at ba154a0). A plain headless session such as `claude -p` has no
such variable and searches lore as usual. The script matches `IGOR_RUN`'s
exact name, because igor PR #171 adds `IGOR_RUN_TOKEN`, a seat's token,
which a prefix match would take for a run marker. It also matches the exact
value, so any other value marks no run.

**During an Igor's run, the repository of the run's item is the one a question
concerns when the agent cannot tell which it is about.** A question with a
category raises igor's flag on the run that met it. For that flag, the run is
the whole execution on the item, not one worker's part of it (igor PR #216's
decision 22). So a categorized question met by any worker flags the item's
whole run.

**Why** the script says so whenever it acts on the variable: a repository can
set it in a person's session, through committed Claude Code settings or an
`.envrc`. Lore would then go unsearched and nothing would be logged to a lore
repository, and without the message the person could not tell why.

*Rejected:* treating every session with no person in it as possibly in an
Igor's run: a plain headless session would lose its lore search.

#### Task 0.12: an Igor worker cannot run the skill

**Measured on 2026-10-20: an Igor worker cannot run this skill, with a lore
clone and `inquisitor.json` in reach, on igor's main branch or once igor
PRs #174 and #175 land as specified.** So gate two builds everything except
Igor-worker mode. *What task 0.12 measured* gives the evidence.

#### An Igor worker asks only in its handback comment

The Igor posts the handback comment (igor #211). The worker opens no post and
calls no picker, even if task 0.14 finds a `gh` login in its reach.

**Why:** a worker holds no credential that can post: igor's requirement *The
worker is given an explicit environment holding no credential but its
seat's* gives it only its seat's token.

**Why** a handback with no artifact logs no repository question: the Igor
publishes a log file about the item's repository only with an artifact, such
as a pull request.

#### Filter 1 in an Igor's run searches through `igor lore-search`

`igor lore-search` is specified by igor PR
[#216](https://github.com/adamstallard/igor/pull/216) (its decisions 23, 49
and 52), whose decisions igor issue
[#215](https://github.com/adamstallard/igor/issues/215) also holds. #216
amends igor's lore-firing spec: lore still reaches the worker unbidden, the
ban on offering a worker a search tool, which rested only on a worker not
needing one, is lifted, and a run's search applies firing's scope rule and
labels an in-scope non-`active` entry as not lore.

**Why** a worker searches at all: igor injects active in-scope entries only
while they fit the worker's token budget, so one holding a person's answer
can be missing from its context.

**Why** only the lore repository the Igor injects from: the Igor checks a
cited entry, reported by id alone, against that lore repository; another
one's search could find an entry the Igor refuses, or one it takes for a
different entry with that id.

**Why** both searches match alike: the same entries then rank alike inside
and outside a run.

#### Questions-branch files and `project:` entries in a run's search

These scope rules are igor PR #216's (decisions 25, 27, 42, 44, 53 and 54);
the spec points to them. A `project:X` entry is hidden in a run whose item's
repository is more visible than X (#216's decisions 53 and 54). So the spec's
scenario of a `project:` entry inside an Igor sets the item's repository no
more visible than X; otherwise the entry would be hidden and the scenario
would test nothing.

**Why** visibility limits what a run sees: a worker could otherwise repost
what it read about a private repository into a more public item.

**Why** a file about another repository is input in a run: proofs show who
answered, not that the answer belongs to the item's repository.

#### Every questions-branch file names where it was asked from

**Every questions-branch log and miss file but a handled one holds
`asked_from`, the repository the question was asked from. Outside an Igor's
run the script writes it. During a run the script writes none: the Igor
sets it after its format check, and refuses a worker's file that already
has one (#216's decision 42).** This change owns the file format, so
`asked_from` is among the keys that format allows, and its readers judge visibility as #216 does, from
the more private of the keys a file holds.

**Why** no worker writes it: a worker steered by its item could write a
public `repository` on a file about a private repository; `asked_from`
still names the private one, so the question cannot be laundered. The
script or the answer session writing `asked_from` outside a run opens no
new way to mislead a reader, since that writer sets `repository` too.

**Why** an organization's question names where it was asked rather than a
repository it concerns: it concerns none, but its visibility and its team's
lore repository still come from the work that raised it (spec: *An
organization's question is bounded by the repository it was asked from*).

**Why** a run's file can name another repository: the item's repository is
only the default for a question the agent cannot place, and a question
clearly about another repository is filed with it, as #216's decision 33
allows; `asked_from` keeps where it was asked. During a run such a file is
only input (*Questions-branch files and `project:` entries in a run's
search*), so a worker steered into naming another repository makes no
answer count.

#### The flag a worker raises for a question with a category

The flag holds two lists: each category met in the run, as one of the three
words, and a marking of those that belong to the questions the run stopped
on. It holds no question or answer. The lists are unpaired: they never say
which stopped question had which category, and have no per-question format. The
Igor writes the category words only into its operator-only file on its host
(#216's decision 89), never into the execution ledger, the state branch, a
comment or a label, and writes no transcript of the run, since a transcript
would hold the question. The Igor accepts a word only when it is exactly one of the three. Each
worker run reports its own flag, including the model steps igor PR #153 runs
after the worker (#216's decisions 60 and 64). How the Igor stores the flag is
#216's (decisions 92, 97 and 100).

*Rejected:* a word per question, which would tell the Igor how many questions
of each category stopped the run; and listing only the stopped questions'
categories in a fixed order (no reason recorded).

#### A flagged run asks nothing and pushes nothing

A flagged run is one whose worker reported the flag, or that ended without
the worker's completed report (#216's decisions 19 and 38). It pushes nothing
to the `questions` branch, citations included, and its question stays on the
Igor's host. The Igor's handoff, the operator file that holds the question,
and how the item is released are igor PR #216's (decisions 73, 75, 76, 79 to 85, 88, 89, 95, 97, 98, 100 and
101 at d3b7740); this change reads nothing from that file.

#### The Igor pushes the questions-branch files its worker reports

igor PR #216's requirement *An Igor publishes the questions-branch files its
worker reports* holds these rules for both changes: it pushes only a file
holding no answer, one with `authority: agent` and `answered_by: agent`, or
a miss file, at a path not already on the branch (decision 21); every file
passes igor PR #217's credential matcher, which matches known secrets'
values such as the seat token (decision 28); and it reads the lore
repository's visibility at every push (decision 37). This change also needs
a person's answer to a handback pushed, which #216 does not handle as this
change has it (*What igor must provide*).

#### A person's answer to a handback

**The Igor pushes a handback answer's log file only when its question matches
a question the Igor posted in the handback comment that the person's comment
answers.** The match uses the question hashes in the Igor's record of the
handback (*A later run names the answered file from the Igor's record*), never
the comment's current text: a question matches when its hash, after the
reduction this change applies before hashing, is in the record (#216's
decision 41).

**Why:** a worker steered by its item could otherwise pair a real comment
with another question, and anyone who can edit the comment could change its
text.

#### A worker logs no answer

In a repository's `.inquisitor/questions/`, an agent outside Igor-worker mode
logs the answer by running the skill's script there, since no answer session
writes there and the Igor does not edit the artifact.

**Why** a worker writes none: a worker reads no comment, so any answer it wrote would be its own
paraphrase, and it could not check the writer's access to set `authority`.

*Rejected:* a worker writing the answer for the Igor or a person to rewrite.

#### An Igor reads relay files as of igor PR #208's applied commit

**Why:** #208 applies only commits passing igor's startup checks, so a
refused commit's relay files never count, just as no relay file counts whose
last change can't be shown to be its person's. The check of who last changed
a relay file reads that commit too. For a lore repository #208 never
fetches, as under `igor run`, the relay check cannot run, so the Igor pushes
a `User says: ` answer as `input`; a person's answer in their own comment
counts regardless (#216's decision 78).

#### A later run names the answered file from the Igor's record

The Igor keeps one record of each handback. For each question it posted, the
record holds the 6-hex-digit suffix and date from the name of the log file it
pushed, and the question's hash; it holds no question text. The run finds the
file by the suffix and date.

**Why:** anyone who can edit a comment can change its text, so the run never
reads a file's name from the comment. The random suffix makes a name unique,
so a second file matching the record can only be a planted look-alike.

**Accepted:** the slug in a file's name carries some of the question's words;
the record holds none.

*Rejected:* naming the files a search found by their words; reading the
file's name from the handback comment's text; dropping the slug from file
names.

#### igor PR #216 holds every rule for a run's citations

**During an Igor's run the agent pushes no citation itself; igor PR #216's
lore-firing requirement *An Igor publishes the citations its worker reports*
holds every rule for a run's citations.** In brief, the Igor pushes a run's
citations only when the run publishes, a handback comment counting, as
bookkeeping outside the role's `allow` list, and only of existing `active`
entries in the role's scope. The channel a worker reports them through,
output or outbox, is igor PR #175's, which runs a worker as a separate Unix
user.

igor's review count of an entry's citations is a lower bound, and says so;
when every Igor push of its workers' citations failed, it shows "not
checked" instead (#216's decision 32).

**Why:** igor has a worker edit and its Igor publish, and a worker holds only
its seat's token. The count is a lower bound because no citation goes to a
more visible lore repository; and a count after every Igor push failed would
show none for every entry only Igors cited.

#### igor-dependent rules state the end state

**A rule that depends on igor states its end state, with no clause for an igor
state before a change lands; what igor must provide is listed under *Open
Questions*.** A clause that also guards against misuse in the end state stays,
such as:
- a log file with no matching record of the handback writes no `answers`;
- an `igor lore-search` call that fails searches no lore;
- a handback-marked post is vetted like any other (*No exemption for an
  Igor's handback*).

**Why:** igor has no users yet, so this change specifies no interim design for
it.

#### Alignment with igor PR #216

**The spec states igor PR #216's rules where they touch this change, and
points to the rest,** such as the Igor's `authority`, `answered_by` and relay
files for a handback answer. *What igor must provide* lists where this change
departs from #216. Among them, #216 writes the answer only into a worker file
that already holds `authority` and an answer line, and this change asks it to
write it into the file this change's worker reports. #216's decision 59's
hashed record of handback questions is the record *A later run names the
answered file from the Igor's record* describes.

### Answer-session configuration, setup and relay identities

#### Setup is part of the answer session

**Setup runs inside the answer session: in place of the queue while the
`answer_session` section is missing or no surface in it has both a `relay` and
a subscription, and again on `/answer setup`.** How setup looks is prototyped,
not specified.

#### A failed relay check turns off only its channel

**Accepted:** where no check can read whether a relay identity may post in a
channel (task 0.20), the first refused post is the check: it turns the
channel off, and its answer is kept pending (*An answer that cannot reach its
thread is kept pending*). Setup shows such a channel as not checked, since
nothing checked it.

#### Setup checks questions-branch commits are the person's

**Setup checks that questions-branch answer files are committed as the
person, with a signing key GitHub verifies for their account, never as a
GitHub App, because an answer file with no `answer_link` counts only through
its commit's signature.**

*Rejected:* treating a file a machine pushed as answered on that machine alone.
*Rejected:* committing as the App and warning that such answers do not count:
github-app commits as the bot, unsigned, so the person's answers would never
count.

#### Discord is in the first version, through discord-bot

**Discord is in the first version, through the `discord-bot` skill of
shared-skills PR #1, merged,** because it gives each role a named bot
identity with no service to run.

#### On Discord one identity both reads and relays

**The answer session reads with the person's own `gh` login and Linear key,
so a relay's token needs only the right to post and nothing the person reads
is read under a bot's name.** Discord is the exception: its terms do not
allow automating a user account, so the Discord relay identity both reads
and posts, in the channels it has been added to.

*Rejected:* a second Discord identity, in a `read` key, reading as the
person: Discord's terms forbid it.

#### The Discord relay needs the Message Content intent

**The Discord relay reads messages that do not mention the bot, which needs
Discord's privileged Message Content intent.** discord-bot's setup
(shared-skills PR #1, commit 369ae16) has the person turn it on, and its
`check` reports `messageContent` from the bot's application flags (f83b167).

#### Only the prefixes are reserved, not the identity

*Rejected:* keeping a relay identity for the answer session alone: the prefix
marks a relay post, and nothing reads a relay identity's other posts.

#### Only a listed relay App speaks for a person on GitHub

**A `User says: ` comment counts as its person's own only when its author is
an App their counted relay file lists.** This is what lets the writer proof
count an answer relayed on GitHub, and an Igor log a relayed handback answer
as `authority: decision`.

**Why:** a relayed answer is trusted because only the answer session makes a
`User says: ` post, and only on the person's confirmation. Owning the App is
not enough: igor's code posts its worker's text unseen by any hook, so a
steered worker could start a comment `User says: ` and prove a
questions-branch `decision` file.

*Rejected:* counting such a comment from any App the person owns: their own
Igor App would let a steered worker forge their answer.
*Rejected:* treating every relayed answer as input: none could prove its
writer, and no Igor could log a relayed handback answer as a decision.

#### An Igor's App is never a relay App

**A reader recognises an Igor's App by the `igor-` prefix of its slug, and
never counts it as a relay App, even where a relay file lists it (igor PR
#216's decision 45).** igor enforces the prefix: an Igor whose App's slug
lacks it refuses to start (#216's decision 62).

*Rejected:* recognising an Igor's App from the lore repository's Igor
configuration: igor's role-config spec forbids a key naming an App identity,
and a lore repository with no Igor configuration would have no relay App.
*Rejected:* a `relays/_igor.yaml` listing the Igors' Apps: the slug prefix
igor enforces already identifies them.

#### The Igor names who answered through a relay App

**For a relay App's comment on a handback, the Igor sets `answered_by` to the
person whose relay file lists that App,** because the worker can't read relay
files: every relayed handback answer would otherwise name the wrong person
and be input.

#### One relay file per person

**Each person's relays are in their own `relays/<github-login>.yaml` in the
team's lore repository, added by their own pull request, so the path names
whose file it is.** This follows igor's seat files (igor issue #148, igor PR
#171), where each lender's own pull request adds `seats/<id>.yaml`. *What the
answer session posts, and what it logs* gives the choice of YAML.

*Rejected:* one shared `relays.yaml` keyed by login: a key does not name whose
it is.

#### Who last changed a relay file ties it to its person

**A reader counts `relays/<login>.yaml` only when its last default-branch
change came from that login, and no review is required.** Task 0.22 measures
what the check needs, such as GitHub giving a commit's pull request.

**Why:** anyone who can push to the lore repository can then stop a person's
relayed answers counting, but not make another App speak for them.

**Accepted:** someone who can push to the person's open pull request, such as
a maintainer the person's fork lets edit it, can change the file under it,
and the change counts once merged; the relay notice @-mentions the person for
that push, so they can close it.

**Accepted:** anyone who can rewrite the default branch can restore an older
file of the person's own, listing an App the person had removed. So removing a
compromised App from the file does not stop it speaking for the person; the
README says to uninstall the App or revoke its key.

*Rejected:* counting the pull request only when all its commits are the
person's: GitHub's API can't show a pushed commit's pusher.
*Rejected:* requiring review through branch protection, with setup warning
where none is required: ownership ties the file to its person without it.

#### Setup's relay pull request

**Setup opens the relay pull request as a host command, with a fixed title and
body the script writes, so it needs no prose pass.** When setup proposes the
file again because someone else last changed it, the first line
`# confirmed by <login> on <date>` makes the pull request change the file
even when the relays are the same, so the other person's commit stops being
its last change.

#### A notice workflow mentions a relay file's person

**The inquisitor ships `relay-notice.yml`, igor's seat-notice workflow (igor
PR #171) applied to `relays/<login>.yaml`,** so the person is warned when
their file is about to stop counting, and when someone else pushes to their
own open pull request. It mentions only the base branch's file owner or the
opener, so a pull request cannot make it mention anyone it likes, which is
also why igor's workflow reads the owner from the default branch. No reader
depends on the notice, so setup carries on when GitHub refuses to add it.

*Rejected:* igor's seat-notice workflow covering relay files too: simpler in
the end, but the notice would wait for igor's release and a change to another
repository's spec.

#### github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity

**github-app's `token`, `run`, `credential get` and `wire` commands are to
refuse an identity marked as a relay, so only the answer session's own posting
command can post with it.** This change asks github-app for that and ships
without it.

**Why:** a relay App speaks for its person only while nothing posts through it
unseen. `token` prints its token to any agent on the machine; `run`,
`credential get` and `wire` hand it to a command, git or a clone's
configuration.

**Accepted:** like the post hook, the refusals guard against accidents, not
against an agent set on forging a relayed answer. Until github-app's change
ships, any agent on the person's machine can print a relay App's token and
post `User says: ` with a plain HTTP call no post hook sees; the README says
so (task 5.2).

### Running the answer session

#### The answer session polls, only while it is open

**The answer session polls about every 60 seconds, only while open, and uses
no webhooks.** Questions-branch log files never appear in notifications, so
it fetches those branches at each poll. A webhook needs a public HTTPS server and Discord's push a
permanent connection, each a service to run. GitHub documents that the
notifications endpoint's conditional requests do not count against the rate
limit, and it sets the interval between polls; task 0.15 measures both.
Unless task 0.15 shows notifications report every GitHub message the session
needs, it also reads each subscribed repository's new issues and pull
requests, their comments, reviews and review-thread comments, and the review
requests and assignments naming the person, so a question of any source is
found if notifications miss it. Those reads also catch a mention of the relay
in a thread the person never subscribed to.

**Accepted:** these reads cost rate-limited requests for each subscribed
repository at each poll. A subscription can name a whole owner, such as
`adamstallard` in the example configuration, rather than one repository. Such
a subscription costs these requests at each poll for every repository of that
owner.

#### Local state is per machine, in the state folder

**The state folder holds working state, not a record: the thread and the
asker's log file stay the records.** A discussion record, the folder's copy of
the person's discussion of a question with the session's model, is deleted
once its question is answered, handled or closed. So the state folder is not
the personal question log that *Every asked question is logged with what it
concerns* rules out.

**Accepted:** a question set aside on one machine is new on another, costing
only a second look.

#### Which cross-machine cases are accepted

**A case between two machines of the same person whose worst outcome is a
question shown twice or asked again is accepted, and gets no rule of its own.**
A case that could record a wrong answer, close a question wrongly, leak
private content or lose an answer is still raised for a decision.

#### One answer session runs on each machine

**One person uses the answer session, and the lock makes one session the sole
writer of its machine's state.** No TLA+ model is written; *Local state, one
writer per machine* gives the reasoning. The lock holder checks the lock by
its session id, not its name, because every session the `answer` command
starts is named `Answers`.

#### Two commands open the answer session

**The answer session opens with `/answer` in any session, or with the
`answer` terminal command that setup installs; no environment variable opens
it,** because a session an app starts from its session list, with no
terminal, cannot set one. `answer` opens it fullscreen, the layout it is
designed for.

**Accepted:** the answer session also works on Claude Code's main screen, but
nothing is designed or built for that screen alone.

#### A discussion runs in the session's own conversation

**Why:** the person opened the conversation to talk the question through, and
the model reads before it replies. A picker would hide the answer session's
screen from them. So a question the model asks back is the one exception to
the rule that an agent asks only through the picker.

**Accepted:** the model runs with the person's tools, so it could reach the
keychain entry holding their Linear key; *The session's model* says why no
guard is added.

#### The model's own Linear and Discord posts are blocked

**In the holder, linear-app's and discord-bot's post hooks block every tool
call that would post, edit or delete on Linear or Discord, and tell the
model to draft its reply with `propose_reply`.** The model reads thread text
and has the person's tools, so without the hooks a crafted thread could
have it post `User says: ` as the relay, which marks a question answered on
every machine. On GitHub the inquisitor's post hook already sees such a
post; these hooks give Linear and Discord the same mechanical guard.

**A post the person confirmed passes because no hook sees it, as on
GitHub.** The answer session runs every relay post as a host command, never
as a tool call of the model (*A relay post gets no prose pass and no
vetting*; task 0.18), and a `PreToolUse` hook sees only tool calls. So the
hooks need no record of what the person confirmed: any posting tool call
in the holder is, by where it comes from, one the person did not confirm.
The person is asked for nothing more.

**What counts as posting** is every way the two skills let a tool call
reach the surfaces as an identity: discord-bot's writing commands;
linear-app's `token` and `headers`, since linear-app has no post command and
the token they print can post; and a Linear MCP server's writing tools. A
command line that `.agents/lib/gh-shell/`'s command splitter cannot split
exactly is blocked when it names either script, or runs a script whose
path it cannot tell, such as `python3 "$D"`, as the post hooks block an
unreadable `gh` line.

**Only the holder is guarded.** The holder's session does nothing but
answer questions, so blocking its own Linear and Discord posts costs no
other work, and every other session posts through the two skills as
before. A lock that cannot be read counts as naming whichever session the
hook runs in, so it blocks those posts in every session: the hook fails
closed like the other post hooks.

**Accepted:** a model set on it could still read a relay's credentials from
the keychain with a plain command and post with `curl`, naming neither
script. That is the exposure *The session's model* already accepts for the
person's own credentials. The hooks stop a model that uses the skills, as
the instructions it has read tell it to, not one that works around them.

*Rejected:* only telling the model, in its context, to post nothing: a
crafted thread can override an instruction, not a hook.
*Rejected:* asking the person to confirm each such post: the answer
session's own confirmation already covers every post the person means.

#### Claude drafts a reply only into the prompt box

**Claude's draft lands in the prompt box for the person to edit and confirm,
and posts nothing.** Since the person confirms whatever Claude drafts, when
they decline under filter 1 the draft may fill in the URL of the record that
answers the question.

#### The UI is built from prototype build v0.1-33

**The mod is built from prototype build v0.1-33 alone, approved by use,**
tagged `answer-session-ui-approved-v0.1-33` on shared-skills (commit fc3c35f;
`ui-approved-v0.1-33` in Adam's prototype repository). It contains all of
v0.1-30, the whole UI approved by use, declining and the list of questions
answered or handled for the person included (tag
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
notes list as still to try. Tasks G.1 and 6.9, the approvals the tasks ask for, are
done. The tag `answer-session-ui-approved` (f964903) lacks the declining
screens and is not a base.

#### How the approved prototype meets the spec

**The mod keeps the approved prototype's screens, and the spec wins wherever
the two differ, because the spec governs what the UI does and posts.** Task
6.1's rules:

- (a) The mod keeps the approved screens' layout and interaction: the band,
  the keys, the prompt-box flow and the declining screens. It may change them
  to wire real data, not restyle or reorganise them.
- (b) Wherever the prototype disagrees with the spec, the spec wins; task 6.1
  lists the known cases.
- (c) A screen the spec needs and the base build lacks is designed at
  implementation from the prototype's existing patterns, in no new visual
  style; task 6.1 lists these screens, which ship with no prototype approved
  by use.
- (d) The screens v0.1-33 added to v0.1-30, which *The UI is built from
  prototype build v0.1-33* lists, are taken as that build has them.

#### Some answer-session details are decided at implementation

**These are decided at implementation, with no requirement added; task 6.11
lists them:**

- how a question's options are parsed from its thread;
- a draft's privacy;
- an asker's reply revising the options;
- the UI of the relay notice shown for the GitHub Actions comment on a pull
  request changing the person's relay file, designed under task 6.1's rule
  (c).

### Relaying answers

#### The thread is the durable record of an answer

The thread is fetched again before each relay post, so an answer relayed from
another machine is never posted twice. A relay post names its question by its
`Re: ` line on GitHub and Linear, and by replying to it on Discord.

**Why:** the thread is the one place every machine, and the asker, can read.
A crash after a post but before its id is saved loses nothing: the next read
of the thread finds the post.

#### `User says: ` answers, `User asks: ` asks the asker

"User" is literal in both prefixes, never the person's name. **Why the
prefixes:** "waiting for the asker" is read from the thread, which
needs a mark that every machine, and every surface, can read there.

#### A relay post gets no prose pass and no vetting

**Why:** a relay post is the person's words. A prose rewrite would post words
the person did not confirm, and the filters guard a person's time against an
agent's questions, not the person's own words.

#### Discord relay posts: no header, mentions that ping

The answer session posts with discord-bot's mention rewriting on, which makes
an `@name` in the answer ping that member. After each relay post, the person
sees discord-bot's warnings, such as for an `@name` that pinged no one.

**Why:** the person's own @-mentions should ping, as in a comment of theirs.
A `Recorded answer: ` post quotes nothing, so no relay post repeats a
record's @-mentions. An edit can drop a ping, so discord-bot's warnings show
after an edit too.
discord-bot's `post` adds a header only when `--agent`, `--session` or
`--project` is given (shared-skills PR #1, merged; `header()` in
`.agents/skills/discord-bot/scripts/discord_bot.py` on main at 90a0237), so
no Discord channel waits on a further discord-bot option.

*Rejected:* mention rewriting off: it only stopped a quoted record's
@-mentions notifying people again, and no relay post quotes a record.
*Rejected:* failing setup on `memberSearch: false`: the warning at each post
tells the person instead.

#### The person can ask the asker

**Asking back is mostly for people's questions:** an Igor's worker asks in its
handback comment and is gone, so a reply reaches whichever worker next takes
the item.

#### Editing a relay post

Editing an automatic post turns it into the person's words, starting
`User says: `, because the person confirmed its new text.

**Why an edit pushes a new log file:** a questions-branch file never changes,
so without a new file the branch would keep the first answer. Which file
counts is in *The newest proven answer counts*.

**Accepted:** the person can edit only a question's latest relay post.

#### A rephrased answer carries its rephrasing, and the asker logs it

**Why:** the asker already records the answer in its log file, which belongs
to its work, often on an unmerged branch; if the answer session wrote it,
each rephrasing would need its own pull request. A reader confirms a logged
answer only when it equals the linked comment, so a file recording the
answer alone would leave every rephrased answer unconfirmed. When the answer
session itself logs a rephrased answer, for a questions-branch question, the
file's answer is therefore the relay post's whole text, its
`Rephrased question: ` and `Discussion: ` lines included.

*Rejected:* new frontmatter keys for the rephrasing: every frontmatter value
is one quoted line, and a question's text is not.

#### A questions-branch question is answered by a new log file

**Why:** the questions branch never changes a file once pushed. Where the
file's `asked_in` links a post that also asked the question, the answer is
both relayed and pushed, so neither the asker reading the thread nor an
agent searching the branch misses it.

#### An answer file records the question the person saw

**An answer to a linked message records the message's question as the person
saw it, not the question the log file holds,** because otherwise a log file
whose `asked_in` points at an unrelated message would get the person's
answer recorded, as a decision, against words they never saw. `asked_in` is
written only where the lore repository is no more visible than the thread,
so the one case left, a lore repository made more public later, publishes
everything already in it, and the answer file adds nothing worse.

*Rejected:* showing the file's question beside the message.
*Rejected:* a rule of its own for that later case, generalising the
message's words or relaying only in the thread: the case barely arises.

#### An answer file names the file it answers

**An answer file names the one file it answers in `answers`, because
answering every file with the same question is matching on words, which
exact identity replaces.** igor PR #216 is asked to refuse a worker's file
holding `answers`, so that the Igor adds the key itself and #216 pushes only
what the Igor writes; *Open Questions* carries that request.

*Rejected:* keeping hash matching beside `answers`: matching gives machines
different answers.
*Rejected:* accepting an `answers` key planted in a worker's file.

#### The newest proven answer counts

**Why newest by proof:** ordering by the commit's place in the branch would
let anyone with push access re-push a copy of an older proven file and revert
a newer answer. If a file that would not count could supersede, a person
without write access, whose answer to a handback an Igor logs as `input`,
would undo a maintainer's answer.

**Why** a signature's date is the earlier of the signed commit's committer
date and the time this machine first fetched that commit: the signer sets the
committer date, so a proven writer, or a skewed clock, could date a commit far
in the future and outrank every later answer for good.

**Accepted:** two machines that first fetched a file at different times can
order it differently against a file pushed between those fetches.

#### `answers` decides a named file's answer; the search groups by hash

**Why both:** a later asker has no file of its own to name, so the search can
find earlier answers only by hash. An answer file is *replaced* when a newer
answer file names the same questions-branch file in `answers`. A replaced
answer file stops counting even
in its own hash group, or the person's changed answer would not be the only
one that counts.

**Why** a replaced file still supersedes the older files in its hash group:
the person's newer answer marks the older ones in that wording stale, so
asking again is safer than reviving one, even when that leaves the group with
no answer that counts.

*Rejected:* deciding a named file's answer by hash grouping: `answers` names
the file exactly.
*Rejected:* letting the older files in a replaced file's hash group count
again.

#### A named file's answer must be the person's own, added alone

**Why the commit test:** a copy of an answer the person gave to another
question carries their proof too, so a copy pushed in one commit with other
files could otherwise become a named file's answer. The test guards against
such bundled copies only. A file that tags no one, such as an Igor's handback
routed by assignment, names no person whose proof could be asked for, so
write access to what its question concerns, the test of `decision` authority for a
questions-branch file, stands in for that proof.

*Rejected:* accepting the risk that such a copy becomes a named file's
answer.
*Rejected:* answering files that tag no one only through filter 1's hash
search.

**Accepted:** a copy of another of the person's answers, carrying their proof
and pushed alone in its own commit, becomes the named file's answer.

#### A named file stays shown until its answer counts

*Rejected:* letting any answer file hide the file it names.

#### Questions-branch answers relayed on Linear or Discord

**An answer relayed on Linear or Discord is logged with the relay post's URL
as an `answer_link` nothing fetches, and counts through the signature on its
commit,** because it was given in the answer session and logged from the
person's machine under their signature. Only an answer typed directly on the
other surface has no such proof.

*Rejected:* counting every answer relayed off GitHub as input.

#### `answer_link` and `asked_in` are withheld where they would leak

**Why:** the URL would point the readers of a more visible lore repository into
a more private thread. A Discord URL holds the server's and channel's ids, and
a Linear URL the workspace, issue and title. A Linear or Discord thread's
visibility is taken as whichever leaks less, which differs by direction. For
what leaves the thread, it counts as private. So a lore repository that is not
private counts as more visible than the thread, and a miss about a question
asked in the thread needs a private lore repository. For what goes into the
thread, it counts as possibly public. So a recorded answer is posted there by
itself only when the record's repository is public. A github.com link into a more private repository
leaks the same way.

*Rejected:* always writing the URL, accepting the leak.
*Rejected:* writing no log file in a lore repository that is not private:
the file without the link still records the answer.

#### An answer that cannot reach its thread is kept pending

A failed post keeps its answer pending rather than leaving the question as it
was, because leaving it would drop the answer the person typed.

**Pending answers are kept in a separate pending list that reuses the main
queue's screens,** which spares the list a prototype round. A pending answer
returns to the queue when setup's recheck of its channel passes. An answer no
check brings back, such as one refused for its text, can stay on the list
indefinitely, because the person can always
post, edit or drop it. The person's other machines read only the thread, and
ask the question again as usual, as *Which cross-machine cases are accepted*
allows.

*Rejected:* pending answers as a state in the list of questions answered and
handled; returning an answer no check brings back to the queue at the next
opening; an "Answered on another machine, not relayed" notice on other
machines, offering to relay, edit or answer afresh, even only for a file
linked by `asked_in`.

#### The push order for a questions-branch answer

**The answer session checks the thread, records the owed push, posts, then
pushes the answer file with the post's link as its `answer_link`.** The file
follows the post, its push retried, so no thread is left answered with no
file. Recording the owed push before the post means a crash between them
does not lose the answer file. Checking the thread first lets the person see
a new message before anything is pushed.

A failed push is retried at each poll and opening.

A retry stops when another answer file on the branch already answers the same
question file. That is an answer file that counts as the person's answer and
names the same questions-branch file. The answer session drops the retry only
if this machine first saw that other answer file at a fetch after recording
the owed push.

**Why only a file first seen after the owed push was recorded drops the
retry:** so the machine's own earlier file cannot cancel the push of the
edited answer's file. That earlier file was pushed at once, before any post,
because the answer's channel was off (*An answer whose thread is unreachable
here is logged at once*). For example, "Use Postgres" is pushed at once while
the channel is off. The person later edits it to "Use SQLite", and it is posted
once the channel is on, but the push of the edited file fails. The "Use
Postgres" file, already known here, does not drop the retry.

**Accepted:** a file pushed at once, for an answer whose channel is off or
not read here, gives up the comment link that would prove it on GitHub, and
counts only through its signature. A dropped pending answer of that kind
leaves its file on the branch, still answering the file it names.

*Rejected:* pushing every answer file on confirmation: a held-back or
dropped answer would leave a file for an answer never posted. Also rejected:
pushing the file of an answer whose thread cannot be read only once it is
relayed; pushing no file when a refused post turned the channel off, unlike
when the channel was already off; accepting a thread answered with no file;
any machine pushing an answer file for a relay post it finds without one; a
dropped pending answer pushing a handled file.

#### What the answer session posts by itself

**The session's model writes no word of an automatic post, and none quotes an
answer.** A thread's text reaches the model, so with fixed texts a crafted
thread can at worst choose which fixed reply or which record is posted. A log
file's answer is a whole comment, which could hold @-mentions that would
notify people again on GitHub, or a `Recorded in: ` line of its own. With its
text fixed but for the record's URL, an automatic post, like a relay post,
gets no prose pass and no vetting.

*Rejected:* a recorded answer in a sentence the model writes: a crafted
thread could steer it.
*Rejected:* quoting the answer with its mentions neutralised: it needs a rule
per surface.

#### No automatic post repeats one in its chain of replies

**Why:** checking only the post a reply answered would let an agent that
kept replying get filter 2's text, then filter 4's, then filter 2's again
with no person seeing it.

#### A post the person chose says so

**Why:** an asking agent acts on filter 3's or 4's reply only when the person
chose it, and the line `The person chose this filter.` is how it tells.

### Incoming questions, declining and handled files

#### Which questions count as an agent's

**Only an agent's question gets an automatic `Inquisitor: ` reply, so any
doubt counts a question as a person's: no person then gets a reply nobody
wrote.** The answer-session spec defines both kinds. A questions-branch log
file counts as an agent's because only the inquisitor's script writes one.
An agent's question posted with a person's own credentials counts as a
person's, since the answer session cannot tell the two apart. A relayed
question from a bot no relay file lists is still a person's, though which
person cannot be proved.

#### Filter 1 runs on every incoming question

**Filter 1 runs before the person sees any question, a person's or a
relayed one included, so the person sees only what needs them.** Filter 1's
answer by itself to an agent's question logs a miss because the asking
agent's own filter 1 should have found the record.

#### Filters 2 to 4 judge every incoming question

**The session's model fails a question on filter 2, 3 or 4 only when the case
is clear, and replies by itself only with that filter's fixed text, and only
on an agent's question.** The person thus sees only what needs them, and a
crafted thread can at worst pick which fixed reply goes out.

#### A reply to an automatic post is a new question

**A reply to an automatic post is judged by the filters again, like a reply
to any relay post, and a repeat within its chain of replies goes to the
person** (*No automatic post repeats one in its chain of replies*).

#### What an asking agent does with an automatic reply

**An agent acts by itself on an automatic `Inquisitor: ` reply naming filter
2, which only defers; on one naming filter 3 or 4, which decide a question,
only when the person chose it; and on any of them only when the relay App of a
person with write access posted it.** The inquisitor spec holds the
conditions. A crafted thread can choose which fixed reply the answer session
posts by itself, and without the write-access condition anyone who can comment
could post `Inquisitor: filter 4` and have an agent decide a maintainer's
question. Every `Inquisitor: ` reply is therefore input on Linear and Discord,
and on GitHub until task 0.21 shows GitHub reports which App wrote a comment.

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

*Rejected:* separate reasons for a conversation that is over and a message
that isn't a question: they behave alike.
*Rejected:* the session's model asking the person which filter should have
stopped the question, and why: the person picks and confirms instead.

#### Messages that are not questions are ignored

**Only messages of the answer session's first two sources, one mentioning
the person and one mentioning their relay or replying to a relay post, are
judged for being questions. A non-question from the other two sources, a
review request or assignment and a questions-branch file, reaches the queue
unjudged.** "Rhetorical" is not a category: an asking
agent rewrites a message that is not really a question as a statement, so
an agent's rhetorical message gets no post.

A non-question that reaches the queue is declined under reason 1 when the
answer session's own judgement let it through, and under filter 3's "the agent
shouldn't have asked" when the asking agent should not have written it. That
second decline logs a miss against the asking agent at the decline. The
question as the session shows it from its thread, called a thread copy (spec
*A thread copy is a question shown from a thread*), can later be reopened, and
the miss is kept even then (*Reopening a declined question*). The first logs no miss because no
asker erred. The second posts nothing because filter 3's fixed text tells the
agent to take an option that has merit, which a non-question does not offer.

*Rejected:* filter 3's automatic reply on a rhetorical message, or a
rhetorical fixed text of its own: filter 3 is for a real question that did
not need asking, and the decline reasons and filters 2 to 4 cover a question
that needs no answer.
*Rejected:* calling filter 3's choice "not a question": only reason 1 says
that, so two labels never share a name.

#### Declining with nothing to answer closes only that question

**A reason 1 decline closes only the declined question; every later message
in its thread that a source names is a new question on every machine.** The
decline is held in each machine's own state folder, so if it stopped later
messages counting, a follow-up would count on one machine and not on
another.

A decline under the second reason resolves its question too, so later
messages in its thread are new questions as well. Its post, or this
machine's close where nothing was posted, already marks the question
handled, so a later message is a new matter.

*Rejected:* a threaded reply reopening the declined question on one machine,
or dropping a reply that arrives after its question closed: the reply is
shown as a new question instead.

#### The answer session writes a handled file on every close of a questions-branch file

**Every close of a question a questions-branch file holds pushes a handled
file naming that file; without it, the file would stay unanswered and come
back.** A machine's first poll of a channel reads only its last 14 days, so
a machine first polling more than 14 days after the question was asked in a
thread never reads the thread copy, the same question in the thread the
file's `asked_in` links, and would show the file as new. The
answer session writes the handled file itself, so no rule depends on
checking which App wrote a post, which waits on task 0.21. A handled file
holds no question text, so it never carries a private item's question into
igor's search, and reveals nothing even for a question with a category. An
Igor worker could still report a file holding the handled keys for its Igor
to push; refusing one is asked of igor PR #216, and is open on its side.

**Accepted:** a record the asking agent's own filter 1 would not count still
closes the question in the person's queue. The asker's question still stands
in its thread, and the asker may legitimately ask again, since it may be
unable to see or count the record: a private one, one withheld by the
visibility rules, or one without authority.

*Rejected:* the asking agent marking its own file handled, or deciding the
close: it would have to check the post's author, which waits on task 0.21.
*Rejected:* copying the question's text into the handled file with the
original's `asked_from`: nothing needs the text.
*Rejected:* `repository` in the handled file for the visibility checks: it
served only the matching that exact identity removed.

#### Closing works by exact identity, never by matching

**Closing never compares question hashes, topic repositories or times: a
handled file closes only the file its `closes` key names, and a thread copy
closes only by the relay posts in its thread, or on one machine by a decline
with nothing posted.** Matching on a question's words, on a judgement each
machine made for itself, or on clocks kept giving two machines different
answers, and each fix raised another case; exact identity cannot disagree.
A file a handled file closed is still unanswered, so an answer given to its
thread copy, where that copy is open, still pushes a log file answering it.

**Accepted:** a thread copy declined with nothing posted on one machine shows
again on the person's other machines, where they can decline it again.

*Rejected:* closing by question hash, by any relay post naming the same
question, by topic repository, or by comparing the handled day or commit
time with when a copy was asked: each gives machines different answers.
*Rejected:* a key in a reason 1 decline's handled file limiting the close to
the copy declined: it served only matching.
*Rejected:* one handled file per topic repository: each handled file names
one file.

#### Reopening a declined question

**Only a thread copy declined with nothing posted can be reopened, and only
on the machine that declined it.** After a post, the thread, which every
machine reads, records how the question was handled, and the person changes
that by editing the post. A handled file closes the questions-branch file it
names, on every machine, for good. A thread copy, the question as the answer
session shows it from a thread, is separate from that file. A thread copy
declined with nothing posted stays reopenable on the machine that declined it,
even after a handled file closes the questions-branch file.

A decline under the second reason that posts nothing on a thread copy, such as
filter 3's "the agent shouldn't have asked", still logs its miss at the
decline, though the question can be reopened. If the person reopens the
question, the miss stays. A miss file never changes, and nothing records that
the person took the decline back.
This is the one decline that can be reopened and still logs a miss.

**Why:** misses feed *Lessons from misses are drafted on request and land by
scope*, so a miss is not held back on the chance that the person reopens the
question.

*Rejected:* reopening a question on this machine whatever its thread shows.

#### A person's cite pushes a citation file

**A person's cite follows the rule of filter 1's own citation and igor PR
#216's: a citation file only for an `active` entry in scope, and one per
question.** igor PR #216 is asked to widen its definition of a citation to
include a person's cite; that request is open on #216's side. A citation
file's push, the answer session's own included, is recorded as owed and
retried as a miss's is (*Misses the answer session logs*).

*Rejected:* pushing a decline's citation only when its miss is pushed: the
only duplicate left without it is two machines declining one question,
accepted below.

**Accepted:** one question can get a citation from each of two machines,
when it is open on both at once, or when a thread copy declined with nothing
posted on one is declined again on another. The case is rare, so no rule
prevents it, such as re-reading the questions branch before a decline's
pushes, or pushing no citation for a reason 2 decline.

#### Agreeing to a recorded answer is a filter 1 decline

**Agreeing to a shown recorded answer is a reason 2 decline with filter 1
naming that record, on every question, so the decline path does the rest
and no answer log file is pushed.** The record exists and filter 1 found it,
so a log file pointing to it adds nothing; a later searching agent is
stopped by the record only if its own filter 1 can read and count it.
Filter 1 should have stopped the question either way, so a miss is logged,
on a person's question too.

*Rejected:* not offering agreement for a record more private than the
thread: the preview's warning lets the person decide.
*Rejected:* a record and a `said`, the miss file's key for what the person
said, of agreeing's own: agreeing is a decline,
and uses the decline's.
*Rejected:* no miss when the person agrees on an agent's question.

#### Misses the answer session logs

**The answer session pushes its misses straight to the questions branch of the
team's lore repository, because it cannot see where the asker logged the
question, often an unmerged branch, and the questions branch takes direct
pushes with no pull request.** The fixed `said` of an automatic miss lets a
review of misses tell the session's judgement from a person's word. A miss or
answer file for a question that questions-branch files hold copies the most
private `asked_from` among them, and their `repository` if they hold one, so
it is as private as they are and about the same thing; files naming
different repositories get no miss. A miss with no such file names its GitHub thread's
repository in `asked_from`. A Linear or Discord thread has no repository, so
there the repository the question concerns stands in, and an organization's
question gets no miss. The inquisitor's rule that a question with no log
file gets no miss does not apply to the answer session's misses, since the
session cannot see whether the asker logged the question.

A miss's push, like a handled file's, is recorded as owed before the post
that leads to it and retried at each poll and opening. Once the post is
out, the thread shows the question handled, so nothing else would bring a
lost miss back.

*Rejected:* writing the miss where the asker's log file went: the answer
session cannot know where, and each miss would take a pull request.
*Rejected:* keeping misses in the state folder: it would be a personal
question log, which this change rules out.
*Rejected:* pushing a miss only when no matching one is on the branch: that
is matching on words, so a question judged on two machines gives two misses.

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**A log file follows the thread message its `asked_in` links by that exact
link, because a link names one message, so every machine pairs the same file
with the same message.**

*Rejected:* judging every log file on its own: the person would see each
question twice.
*Rejected:* hiding a log file by matching its words to a message: matching
gives two machines different answers.

#### A link this machine never reads is not followed

**A log file whose `asked_in` links a message in a channel this machine does
not subscribe to or has off, or on a surface it has off or cannot read, is
shown on its own. An Igor worker's log file whose handback comment is on an
issue or pull request in the repository its `asked_from` names still follows
that comment, even on a machine that does not read its item (*Each Igor log
file follows its own handback comment*).**

*Rejected:* showing the file nowhere on that machine: the person would never
see the question there.

#### A log file without `asked_in` is never merged

**A log file with no `asked_in`, withheld for privacy or never written, is
always its own question, never paired with a thread message by matching
text.** Merging only avoids a duplicate, which is low priority, while any
merge rule can pair a message with another asker's file in the same words,
so that a decline or an answer lands on that asker's question.

**Accepted:** where the link is withheld, on Linear and Discord from a lore
repository that is not private and on GitHub from a more visible one, the
person may see one question twice (*Which cross-machine cases are
accepted*).

*Rejected:* merging a log file and a thread message that ask the same
question, with any set of guards: each guard left a case that closed or
answered the wrong asker's question.

#### A bot's question reaches only the first person it mentions

**A bot's message reaches only the first person it mentions, so each bot
question has one owner: two people cannot give a bot conflicting answers, and
the inquisitor never needs to know an operator.** A bot orders its mentions
by importance. For an Igor the order is set in igor issue #229, which is
open, and igor's specs do not state it: an Igor mentions its operator first
only when it stops for a reason it detects itself, then the assignee and the
creator; every other handback, a question included, mentions the assignee
and then the creator.

*Rejected:* a handback reaching the assignee unless it mentions someone else
and not them: it gives a bot question more than one owner.
*Rejected:* routing an Igor's handback by assignment until igor's specs
state the order of issue #229: no one uses igor yet, so the spec states only
the end state.

#### igor's handback marker

**A handback is an `igor-` App's comment holding a fixed marker igor gives its
handbacks, because an Igor posts other comments on the item too, and text
the Igor quotes from its item cannot produce the marker.** igor chooses its
form, and task 0.6 records it. The post hook does not read the marker (*No
exemption for an Igor's handback*).

*Rejected:* counting every comment by an `igor-` App as a handback.

#### Only an item's newest handback is open

**Only an item's newest handback is open; older ones are passed over by a
reading rule each machine applies alone, writing nothing.** A newer handback
follows only once the person returns the item to the Igor without answering
the older one, so the case is rare, and the newest says where the Igor is
blocked now.

**Accepted:** a passed-over handback's log file stays on the questions branch,
unanswered, and is never shown again. If its blocker still matters, the Igor
asks again on its next run.

*Rejected:* a new log file linking its own handback only while an earlier
one is unanswered: less simple than every file linking its own handback,
and guarantees no more.
*Rejected:* an answer naming only the oldest unanswered log file: its
question no longer says where the Igor is blocked.

#### A handback that mentions no one reaches the assignee

**A handback that mentions no one reaches the item's assignee; one that
mentions people reaches only the first, as any bot's message does.** So on
an item assigned to the person, a handback that mentions people reaches them
only if they are mentioned first. One that mentions no one, on an item
assigned to no one, is shown to whoever is next assigned it. igor issue #229
states this rule too, but names no case in which a handback mentions no one,
which is a known gap.

#### Each Igor log file follows its own handback comment

**Each Igor worker's log file links, in `asked_in`, the handback comment that
asks its question, so one answer never closes two handbacks' files and the
newest-handback rule needs no other mechanism; it is the simplest mechanism
that guarantees this.** The Igor writes `asked_in`, not the worker, because
the comment exists only once the Igor posts it. A later Igor question on an
item whose earlier question is answered follows the new handback comment,
which reaches the person as a new message in an answered thread.

*Rejected:* linking the log file to the assigned item: two handbacks on one
item would share one link.
*Rejected:* posting the answer on the item when the file is answered on its
own: the file follows the handback, so the answer is relayed there.

### OpenSpec, prototypes and scenario tracing

#### OpenSpec for new work in shared-skills

**New work in shared-skills goes through OpenSpec, except UI, which is
prototyped and then built directly; this change adopts OpenSpec, spec-check
and spec-trace for the repository.** A skill's spec holds what must be true
of it. Its constraints and rejected alternatives go in a decision record
beside the spec, `openspec/specs/<capability>/decisions.md`, one per
capability, in the form shared-skills issue #56 sets; a skill with no spec
keeps its reasoning in its `DECISIONS.md`. Each holds current reasoning in
one place, not a log. An existing skill gets its spec in a change of its own, skill
by skill, as shared-skills issue #57 plans; a change that edits a skill with
no spec, as this one edits github-app and bug-hunter (tasks 5.5 and 5.7),
lists the edit as a task. While a
change is open, its decisions are each stated once, in design.md's
*Decisions*, and each undecided item in *Open Questions*, as spec-check's
convention has it. When it is archived, its lasting reasoning is folded into
the decision record of each capability it specifies, and into the
`DECISIONS.md` of each skill without a spec that it affects, rewriting the
reasoning it replaces rather than appending. So this change writes
`openspec/specs/inquisitor/decisions.md`, `answer-session`'s and
`gh-post`'s, and no `.agents/skills/inquisitor/DECISIONS.md`. `AGENTS.md`
states this, and `openspec/config.yaml` makes it the last task of every
change.

#### How the three specs are laid out

**Each spec opens with a `## Purpose`, and each requirement states one rule,
or two that only make sense together, in under 500 characters; its scenarios
hold the examples and cases, and this file the reasons.** The inquisitor's
Purpose defines the terms its spec uses throughout; any other term is
defined once, in the requirement that sets its rule, and earlier
requirements may use it, so no term is defined twice. A Purpose is not normative,
so a definition that carries a rule, such as a default, a "never", a closed
list or a condition, also has that rule stated in a requirement.

**Why:** `openspec archive` takes a new spec's Purpose only from the delta's
`## Purpose` (spec-check, PR #50), and `openspec validate --strict` fails any
requirement over 500 characters. Splitting a requirement is the last resort:
detail moves first to scenarios, then reasons move here, then the text is
compacted, and only a requirement still too long is split, along its own
rule boundaries.

*Rejected:* a glossary requirement holding every term, at 17,651 characters.

#### UI is prototyped and approved by use, not specified

**Once Adam has used a UI's prototype and approved it, the UI goes straight to
an implementation pull request; the feature's other parts, such as its data
flow, integrations, setup and rules, still go spec first.** A spec names a
UI only as an interface the other parts use. A screen that a spec's task
says is designed at implementation, from the patterns of the feature's
approved prototype, needs no prototype of its own, and the task only names
it; task 6.1's rule (c) is such a task. `AGENTS.md` states the rule and this
exception.

**Why:** whether a UI works is easier to see by using it than by reading a
spec.

*Rejected:* keeping the exception only in this change, outside `AGENTS.md`.

#### Igor-worker scenarios stay untagged until igor builds what they need

**A scenario that only igor's unbuilt work can make pass gets no tagged test
until igor provides what it needs, and task 4.3 then tags it; spec-trace does
not change.** *Tracing scenarios to tests* gives the reasons, and why a
skipped test would not do.

#### The change is archived only after every expected gap is tagged

**Archiving waits for task 4.3 to tag every expected gap, beside task 7.0's
wait for igor PR #216 to merge, since archiving writes the scenarios into
the directory where spec-trace's CI fails on an untagged one.**

*Rejected:* archiving the rest and leaving the Igor-worker scenarios in an
open change.

## Open Questions

### Facts measured before building

Tasks 0.4 to 0.14 measure these facts before anything is built; *What the
hook relies on, not yet measured* holds tasks 0.1 to 0.3. Each bullet says
what the spec does if the fact is false. Task 0.12 is measured; *What task
0.12 measured* gives its result.

- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, wherever the agent lacks push access, every
  answer in a post and every issue's decision block (the start of its body
  before its first heading, or its first section whose heading starts with
  "Decision", which the spec counts as a decision document) counts as input, and a
  post's question tags no one.
- **Can the script learn which login a post goes out as?** (task 0.7) An agent
  using the github-app skill posts with a token only the posting command holds,
  so the script's `gh api user` returns the person's login. If the script can't
  learn the posting login, it treats every post as going out as the configured
  login, and with a person in the session it asks through the picker where it
  would have tagged them.
- **Can the script tell whether a person is in the session, and whether a
  headless session can post?** (task 0.9) If it can't tell whether a person is
  there, the session counts as having no one, so no picker opens with nobody
  to answer. If it can't tell whether a headless session that is not an Igor
  worker can post, that session counts as unable to post and asks nowhere.
  Whether the script runs in an Igor's run is not part of this fact: it reads
  `IGOR_RUN`. Task 0.9 checks that igor sets `IGOR_RUN` as igor PR #216
  specifies, once igor builds it.
- **Can the script find the approver of the pull request that added a
  decision?** (task 0.8) A `DECISIONS.md` section leads through blame and a
  commit to a pull request and its reviews. If not, the script skips the
  tagging order's first candidate, the approver of the related earlier
  decision.
- **Can the script find the GitHub login of the last person to commit to a
  file?** (task 0.5) Git records a name and an email, not a login. If not, the
  script skips the tagging order's third candidate, whoever last changed the
  files involved.
- **Can the agent open, and write in, a repository's private security
  advisory?** (task 0.10) That needs private vulnerability reporting enabled,
  or an admin or security-manager role. If not, the agent records a
  vulnerability's question and answer only in the fix, and reports only that a
  vulnerability question is blocking, with no text.
- **Can the private fork's pull request be merged before the advisory is
  published?** (task 0.13) The spec's weakness requirements give what each result
  means. Until it is measured, a fork commit's
  message describes the weakness, and a regression test goes in the fork, only
  on the word of the person publishing the advisory; without it, the
  advisory's text holds the full description.
- **Does GitHub's API give a comment's author and a commit's verified signer,
  as the proof of a questions-branch writer needs?** (task 0.11) If not, every
  questions-branch `decision` or `agent` file counts as input.
- **Does a comment's `updated_at` change only when its text is edited?** (task
  0.11) *The newest proven answer counts* dates a comment link's proof from
  the comment's last edit, so it relies on `updated_at` not moving on a
  reaction, a hide or minimize, or other metadata. If it does move, a reaction
  could make an older answer the newest. The spec states no fallback; which
  ordering then applies is undecided.
- **Can an Igor worker post?** (task 0.14) igor's task-execution requirement
  keeps every credential but its seat's out of the worker's environment, but a
  `gh` login in the worker's home directory is in neither its environment nor
  its working tree. If a worker can post, it still asks only in its handback
  comment, and the credential in its reach is reported to igor as a breach of
  that requirement.

### Facts the answer session relies on

**Tasks 0.15 to 0.24 measure facts the answer session relies on, and each
says what the spec does until it is measured.** They cover GitHub's
notifications endpoint; how Linear and Discord show mentions and replies;
how the Linear relay posts a comment; that a command the mod runs reaches no
tool hook; that a mod keeps polling while idle or in the background; how
setup checks a relay's access to each channel; whether GitHub reports which
App wrote a comment; whether a reader can read the pull request and
signature behind a relay file's last change; whether the `asked_in` URL an
asking agent records is the one the answer session reads; and how setup can
tell that a questions-branch commit will be verified for the person. Task
0.25 records how each surface reports two kinds of refusal of a relay post:
one for its text, such as its length, and one for lack of permission. A
refusal the session
cannot place waits for the person, as the answer-session spec's *A pending
answer no check returns waits for the person* says. Task 0.26 states no
interim rule: see the bullet below.

- **Do only reading Linear MCP tools have names starting `get_`, `list_` or
  `search_`?** (task 0.27) linear-app's post hook lets those tools through in
  the holder and blocks the rest, so a tool of another name fails closed. If
  a writing tool has such a name, the hook lists the reading tools by name
  instead.
- **Which App wrote a comment** is measured by both task 0.21 here and igor PR
  #216's task 4.8. Until a measurement shows GitHub reports it, every `User
  says: ` comment is input.
- **Does every call from outside the main conversation carry an
  `agentId`?** (task 0.26) The spec's `propose_reply` refuses subagents (*A
  subagent cannot call propose_reply*). The approved prototype already refuses
  any call whose `agentId` is set: a subagent's, or one from a side
  conversation Claude Code forks, such as the one that guesses the next prompt
  (fc3c35f, `answer-session/hooks/register.tsx`, the `tool.call` handler for
  `propose_reply`). Task 0.26 checks that no such call arrives without one.
  The spec states no fallback. Undecided: what the tool does with a call from
  outside the main conversation that arrives without an `agentId`, for
  example refusing every call it cannot attribute.

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
- **The archive waits for task 4.3.** Task 4.3 tags every expected gap, the
  Igor-worker scenarios no test covers, once igor builds `igor lore-search`
  and lets a role's `commands` list the skill's script. Task 7.0 also waits
  for igor PR #216 to merge and for igor PR #202 to set the path of the
  scribe's records.
- **igor PR #216, with igor issue
  [#215](https://github.com/adamstallard/igor/issues/215),** amends igor's
  lore-firing spec, holds every rule for an Igor's citations, and has not
  merged. This change relies on it for:
  - *An Igor publishes the citations its worker reports*: a worker's citation
    report, which has no category, and which citations an Igor pushes, and
    when, from a worker or its own inquisitor run, in this change's format.
  - Its review counting citations on the lore repository's `questions` branch
    (its decision 8), shown as "not checked" when every Igor push of them
    failed (its decision 32).
  - Its id check reporting an out-of-scope collision during a run only as "id
    taken" (its decision 6); the Igor proposes no such entry and says so.
  - A run's search reading only the lore repository the Igor injects from.
  - *Transcripts and outcomes are captured to the state branch*, in its
    task-execution spec: the flag for a question with a category, the
    categories it lists, and the Igor's handling of it (its decisions 92 and
    97).
  - *An Igor publishes the questions-branch files its worker reports*: which
    question, miss and `authority: agent` files the Igor pushes and when (its
    decisions 20, 21, 24 and 26), including a handback's answer when a worker
    re-works the item. A flagged run pushes none, and a run that ends without
    its worker's completed report counts as flagged (its decision 38). Each
    file is checked with igor PR #217's credential matcher, and a person's
    answer is pushed only beside a question the Igor asked, as its record of
    the handback holds it (its decisions 28, 30 and 41). The lore repository's
    visibility is read at every push (its decision 37), each file's
    `asked_from` is set (its decision 42), and a file's `repository` may name
    any repository, whether or not the run's role works it (its decision 33).
  - *An Igor runs its worker's lore searches*: `igor lore-search`, called by a
    worker and by the Igor's own inquisitor run. It matches plain text, ranks
    and caps hits as filter 1 does, and labels each question file an answer,
    input, unanswered or a miss (its decision 23). It searches the lore
    repository's decision records at the path igor PR #202 sets too, counting
    an `accepted` one as this change does. It runs this change's
    authority checks first, and labels the file unconfirmed input when a check
    can't run or fails (its decision 34). Those checks count a relay file only
    when its last change was that person's, read as of igor PR #208's applied
    commit. The Igor reads the relay file too, to decide `authority` for a
    relay App's handback answer.
  - A questions-branch file's scope: every role whose Igor uses that lore
    repository, and only a run whose item's repository is no more visible than
    the more private of whichever of `repository` and `asked_from` it holds
    (its decisions 25, 27 and 42).
  - Its `graceful-handoff` and `work-triage` deltas: igor's side of a flagged
    run, its handoff, its host file and the release of a held item.
- **#216's lore-firing spec should judge a file by whichever of
  `repository` and `asked_from` it holds.** Its *An Igor runs its worker's
  lore searches* makes a file "as visible as the more private of the
  repositories its `repository` and `asked_from` keys name, and as its
  `repository` alone when it holds no `asked_from`". That covers a file
  with no `asked_from` but not one with no `repository`, so it should read:
  as the more private of the repositories named by whichever of the two
  keys the file holds. Its push condition that the destination is no more visible
  "than the repository its `repository` key names" applies only to a file
  holding one. Its *Lore reaches the worker unbidden, beside a search it may
  run* cites this change's rule (#216 calls this change #25, its pull
  request in shared-skills) that a file whose `repository` names a repository
  other than the item's is input; that still reads right, since a file
  about an organization holds no `repository` and so names no other
  repository, and needs no rewording.
- **#216 should say that no worker writes `asked_from`, not that only an
  Igor does.** Its decision 42's sentence "Under #25 only an Igor writes the
  key", and its lore-firing spec's "which only the Igor writes", should read:
  a worker never writes the key; in a run the Igor sets it. Outside a run the
  script writes it on every questions-branch file, and the answer session
  copies it into its misses and answer files (*Every questions-branch file
  names where it was asked from*). #216's protection is unchanged: no worker
  writes the key, and the Igor refuses a worker's file holding one.
- **#216's Igor must write the answer into the file a worker reports for a
  handback answer.** #216's lore-firing spec (lines 484-489 at 59e7561) has
  the Igor write the comment's text "in place of the answer line the worker
  wrote" only for a file holding `authority: decision` or `input`, and its
  decision 21 pushes a file with no answer as it is. This change's worker
  writes only the question and `answer_link`, no answer and no `authority` (*A
  worker logs no answer*). #216 should recognise that file, write the answer
  from the linked comment, and set `authority` and `answered_by`; otherwise it
  pushes the file as an unanswered question and the answer is lost.
- **#216's Igor must open the lore pull request for an entry its run
  reports.** During an Igor's run the agent opens no lore pull request: it
  puts each entry it would propose in the run's report, as it does its
  question and miss files, and the Igor opens a pull request adding it as a
  `provisional` entry to the lore repository. The Igor applies this change's
  rules for a proposed entry's path, fields, id and visibility, and on "id
  taken" proposes nothing and says so (*A general answer is proposed as a
  provisional lore entry*).

- **#216 must keep its decision 62:** an Igor whose App's slug lacks the
  `igor-` prefix refuses to start. *An Igor's App is never a relay App*
  rests on it. Without it, a relay file could list an Igor's App with no
  prefix, whose posts would then count as a person's relayed answers.
- **#216 should refuse a worker's file holding `handled` or `closes`,** as it
  refuses one holding `asked_from`. Only an answer session writes a handled
  file, but #216 pushes any worker file with no `authority` as an unanswered
  question file, so a worker steered by item text could close, on every
  machine and for good, whichever file a planted `closes` names.
- **#216's Igor should keep, in its own record of the handback (#216's
  decision 59), the 6-hex-digit suffix and the date of the name of the
  questions-branch log file it pushed for each question, and each question's
  hash, and no question text.** A later run names that file in `answers`
  from this record, never from the handback comment; without the record, it
  writes no `answers`.
- **#216's Igor should write `asked_in`** in a worker's log file as the URL of
  the handback comment that asks it, once it has posted that comment,
  withholding it when the item's repository is more private than the lore
  repository. It names in `answers` the file an answer file answers, adding
  `answers` itself and refusing a worker's file that holds it. Without
  `answers`, the answer session keeps showing the answered file as unanswered.
- **#216 should give every handback comment a fixed marker,** which no text
  the Igor quotes from its item can produce. igor chooses its form, and task
  0.6 records it.
- **#216 should widen its definition of a citation to include a person's
  cite.** #216 counts only an agent's record that a lore entry answered a
  question so that no person was asked. Here a person's cite of an `active`
  entry in scope pushes a citation too, as does a decline under "the
  inquisitor should have handled it" with filter 1 naming such an entry (*A
  person's cite pushes a citation file*).
- **How an Igor runs the inquisitor skill itself** is only partly set. igor
  PR #216's `task-execution` spec sets `IGOR_RUN=igor` in that run's
  environment, and the script then searches lore only through `igor
  lore-search` and pushes nothing, putting each file it would push, and each
  lore entry it would propose, in the run's report for the Igor. #216's task
  3.6 waits for igor #211 to say how the Igor starts that run. Open: which
  other sources that run's filter 1 covers, how the report reaches the Igor,
  and whether the run can read GitHub.
- **igor must say how `igor lore-search` identifies the Igor's own
  inquisitor run.** #216 takes the run and role from the channel a request
  arrives on, which only that run's worker can reach (its lore-firing
  spec), and the Igor's own run has no worker. Until igor settles it, that run's search
  fails, and the script searches no lore and says so, as *In an Igor's run,
  filter 1 searches through igor* says of a failed command.
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
- **igor issue #211's body should record that the post hook vets every post,
  handbacks included** (*No exemption for an Igor's handback*). #211 proposes
  this skill and the Igor inquisitor role, and its body lists five open
  questions:
  - Three concern only the role, which is out of scope (*The Igor inquisitor
    role is out of scope*): the role itself, which nobody has claimed; how
    long it waits before following up; and whether a team discussion, such as
    a chat channel or a shared document, is a new kind of surface for Igor,
    beside the tracker and the code host.
  - The fourth, when an Igor's worker can run the skill, is this change's
    Igor-worker mode, which waits on this section.
  - The fifth asks whether the post hook can tell a handback comment from
    other posts. It need not: the hook vets every post, and an Igor posts its
    real handbacks through its own code, which the hook never sees.

### What other changes must provide

- **bug-hunter needs a matching note:** the regression-test rule of
  *Weaknesses stay out of public text until disclosure*, carried by a separate
  change to bug-hunter.
- **The github-app skill's `token`, `run`, `credential get` and `wire`
  commands must refuse an identity marked as a relay.** No pull request for it
  is open. This change asks for it and ships without it, at the cost
  *github-app refuses `token`, `run`, `credential get` and `wire` for a relay
  identity* accepts.

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would need that surface's API to vouch for the message's author,
  and a map from the author to a GitHub login: igor issue #160's configuration
  entry keyed by the Discord user id, or a file in the lore repository. A
  later change would choose. Without it, an answer typed directly on such a
  surface counts only through a decision document, such as the scribe's
  record; one typed in the answer session and relayed there counts through its
  log file's signature.

### The answer session's open choices

- **Should the answer session close an agent's question that another skill
  requires a person to decide?** The inquisitor's *A question another skill
  requires skips filters 2 to 4* exempts such a question, but the answer
  session cannot tell one apart. So *Filters 2 to 4 judge every incoming
  question* posts a filter's fixed text on it, logs a miss and lists it as
  handled, while the asking agent treats the reply as input and the person
  never sees the question. Until a person decides, the spec does exactly
  that; the choices are that the asker marks such questions, or that the
  answer session only suggests a verdict on every agent's question.

### The post reader's open costs

- **Whether `gh api` calls made as a GitHub App must work.** The `gh-post`
  spec reads the github-app script's `gh pr` and `gh issue` forms only, so
  `python3 $G gh api …`, a read included, mentions a gh post verb and is
  unreadable. Until a person decides, the spec blocks every such call; the
  choice is whether to read the script's `gh api` form too.
- **Whether `gh api` counts as a mention for every prose user.** prose's
  reader matches only `gh pr` and `gh issue`; the `gh-post` spec also counts
  `gh api`, so a line such as `gh api … | python3 -c …`, which prose passes
  today, becomes unreadable, a cost *Which commands the reader judges, and
  which are unreadable* does not list. Until a person decides, the spec counts `gh api` as a mention;
  the alternative applies the interpreter and input rules only to `gh pr`
  and `gh issue` post verbs and to `gh api` calls that write.

### Left to implementation

- **Task 6.11's details are chosen at implementation, with no requirement
  added,** and recorded in design.md while the change is open. *Some
  answer-session details are decided at implementation* lists them and what is
  decided around them.
- **Where a machine keeps when it first fetched a questions-branch commit,**
  which *The newest proven answer counts* bounds a signature's date by. It
  holds no question text.
