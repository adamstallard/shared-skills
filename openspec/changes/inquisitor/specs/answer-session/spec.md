## Purpose

The answer session is the part of the inquisitor in which a person does
nothing but answer the questions asked of them. Questions reach it from
the channels the person subscribes to on GitHub, Linear and Discord, and
from the questions branches of lore repositories. Its user interface is a
Claude Code mod that ships with the inquisitor skill; this spec names that
interface only by what it does, never by how it looks or which keys it
takes.

These terms come from the inquisitor spec, whose requirements this spec
cites by title as the inquisitor's, or that spec's, *Title*:

- **The skill** is the inquisitor skill, and its **script** the inquisitor
  script.
- **Filters 1 to 4** are the skill's four filters, which stop a question
  before a person sees it: 1, already answered; 2, deferrable; 3, not a
  real question; 4, cheap to reverse (the inquisitor's *Every question
  passes four filters before a person sees it*). Filters 2 to 4 each have
  a fixed `Inquisitor: ` text, which *Filters 2 to 4 judge every incoming
  question* gives.
- A question's **category** is `vulnerability`, `secret` or `personal`, as
  the inquisitor's *Some questions are recorded by hash only* defines them.
- An **Igor** is one of the igor project's AI teammates, and an **Igor
  worker** the agent an Igor starts to do an item (the inquisitor's *An
  Igor is an igor teammate, and its worker does an item*). **An Igor's log
  file** is an unanswered questions-branch log file holding `asked_from`,
  a key that only an Igor writes on such a file (design.md: *The Igor
  writes `asked_from` on every file it pushes*).
- A person's **relay file** is `relays/<login>.yaml` in a lore repository,
  listing their relay identities (the inquisitor's *A relay file names the
  bots that post for its person*).
- **The `log` command** is the script's command that writes and pushes
  every log and miss file, answer and handled files included (the
  inquisitor's *The script writes every log and miss file through its log
  command*).
- `answers`, `asked_in`, `asked_from`, `answer_link`, `answered_by`, who
  answered, and `authority`, one of `decision`, `input` or `agent`, are
  keys of a log file, as the inquisitor's *A log file and a miss file have
  one format* gives them. A file is **proven** to be a writer's by its
  linked comment or its commit's signature (the inquisitor's *A
  questions-branch file's writer is proven by its comment or its
  signature*).
- discord-bot's **header options** are `--agent`, `--session` and
  `--project`.
- **Task 0.N** is that task in this change's tasks.md.

## ADDED Requirements

### Requirement: Relay posts start with a reserved prefix

The answer session SHALL count as a **relay post** only a message a relay
identity posted that starts with one of the four **reserved prefixes**:
`User says: `, `User asks: `, `Recorded answer: ` or `Inquisitor: `.
Nothing in this spec reads a relay identity's other posts.

#### Scenario: A prefixed post by a relay identity is a relay post

- **WHEN** the person's Linear relay identity posts a comment starting
  `User asks: `
- **THEN** that comment counts as a relay post

#### Scenario: A relay identity's post without a prefix is not read

- **WHEN** the person's Discord relay identity posts, for other work, a
  message with no reserved prefix
- **THEN** it is no relay post, and no rule of this spec acts on it

### Requirement: An automatic post's text is fixed by the answer session

An **automatic post** is a relay post starting `Recorded answer: ` or
`Inquisitor: `. The answer session, never the person, SHALL fix its text.
It SHALL make one in one of two ways: by itself, or, when the person
declines a question because the inquisitor should have handled it, only
once the person confirms it. Agreeing to a shown recorded answer is such a
decline.

#### Scenario: An automatic post holds no words the person wrote

- **WHEN** the answer session posts filter 4's `Inquisitor: ` reply by
  itself on an agent's question
- **THEN** the post is filter 4's fixed text, none of it the person's

#### Scenario: An automatic post on a decline waits for confirmation

- **WHEN** the person declines an agent's question as one the inquisitor
  should have handled, picks filter 3, and has not yet confirmed the post
  shown to them
- **THEN** nothing is posted

### Requirement: A question's thread is where a reply to it goes

The answer session SHALL treat as a question's **thread** the place a
reply to it goes: on GitHub, the conversation of the issue or pull request
holding it, or the review thread for a review comment; on Linear, the
comment thread of the comment, or the issue, holding it; on Discord, the
channel or thread holding it.

#### Scenario: A review comment's thread is its review thread

- **WHEN** a question is a review comment on a GitHub pull request
- **THEN** its thread is that review thread, not the pull request's
  conversation

#### Scenario: A Discord question's thread is the thread that holds it

- **WHEN** a question is a message in a thread of a subscribed Discord
  channel
- **THEN** its thread is that Discord thread

### Requirement: A relayed question is a person's question

The answer session SHALL treat as a **relayed question** any message
starting `User says: ` or `User asks: ` that any bot account posted on
any surface, and SHALL count it as a person's question. One posted on
GitHub by a person's relay App, as the inquisitor's spec defines it, is
that person's; one from any other bot is still a person's.

#### Scenario: A relayed question from a listed relay App is that person's

- **WHEN** a GitHub comment starting `User says: ` comes from the relay
  App that Maya's relay file lists, and mentions the person
- **THEN** it counts as Maya's question, a person's question

#### Scenario: A relayed question from an App no relay file lists is a person's

- **WHEN** a GitHub comment starting `User asks: ` from a GitHub App that
  no relay file lists tags the person, and it clearly fails filter 4,
  which would get an agent's question an automatic reply
- **THEN** it counts as a person's question, so nothing is posted by
  itself and filter 4's verdict is only suggested, as *Filters 2 to 4
  only suggest a verdict on other questions* says

### Requirement: An agent's question comes from a bot account or a log file

**The asker** is whoever asked the question: a person, or an agent such
as an Igor's worker. Unless it is a relayed question, the answer session
SHALL count as **an agent's question** a log file of the fourth source in
*A question asked of the person comes from one of four sources*, and one
whose message's author is a bot account, such as a GitHub App, a Linear
app user, or a Discord bot or webhook. Every other question SHALL count
as **a person's question**.

#### Scenario: A Linear app user's question is an agent's

- **WHEN** a Linear app user comments, in a subscribed team, a question
  mentioning the person, with no reserved prefix
- **THEN** it counts as an agent's question

#### Scenario: A questions-branch log file is an agent's question

- **WHEN** a log file of the fourth source holds a question tagging the
  person
- **THEN** it counts as an agent's question

#### Scenario: An agent posting with a person's credentials asks a person's question

- **WHEN** an agent posts, through Maya's own `gh` login, a GitHub comment
  mentioning the person
- **THEN** it counts as a person's question, as a relayed question does

### Requirement: A closed question is shown neither in the queue nor as new

A **closed question** is one the person declined on this machine with
nothing posted, as *A decline with nothing posted closes a thread copy
on this machine only* says, or a questions-branch file that a handled
file names, as *A handled file closes a questions-branch question* says.
The answer session SHALL show a closed question neither in the queue nor
as new.

#### Scenario: A question declined on this machine stays out of the queue

- **WHEN** the person declined a question on this machine with nothing
  posted, and its channel is polled again
- **THEN** this machine shows it neither in the queue nor as new

#### Scenario: A questions-branch file a handled file names is not shown as new

- **WHEN** the answer session fetches a questions branch holding a log
  file that tags the person and a handled file naming it
- **THEN** the log file is not queued, nor shown as new

### Requirement: The queue shows unanswered questions one at a time

The answer session SHALL show the person **the queue**, the list of
unanswered questions, one at a time. **A question set aside for later**
is one the person moved to the end of the queue on this machine, to come
back to; the answer session SHALL show it after the new ones.

#### Scenario: The queue shows one question at a time

- **WHEN** three questions asked of the person are unanswered
- **THEN** the person is shown one of them, and the next only once they
  have dealt with it or set it aside for later

#### Scenario: A question set aside comes after the new ones

- **WHEN** the person sets a question aside for later, and a new question
  then reaches the queue
- **THEN** the new question is shown before the one set aside

### Requirement: A question with a pending answer is out of the queue

**The pending list** is this machine's list, apart from the queue, of
answers held as answered, not relayed, as *An answer that cannot reach
its thread is kept pending* says; every such answer SHALL be on it. A
question whose answer is on it SHALL NOT be in this machine's queue until
the answer goes back into the queue, as *A pending answer whose channel
was off returns to the queue* says.

#### Scenario: A pending answer's question leaves this machine's queue

- **WHEN** this machine holds an answer to a question on the pending list
- **THEN** that question is not in this machine's queue

#### Scenario: A pending answer that goes back brings its question with it

- **WHEN** an answer on this machine's pending list goes back into the
  queue
- **THEN** its question is in this machine's queue again, with the answer
  kept

### Requirement: An unanswered log file holds no answer the person gave

On a lore repository's questions branch, the answer session SHALL count
as **an unanswered log file** one that holds no answer and that no answer
file counting as the person's answer names in `answers`.

#### Scenario: A log file with no answer and no counting answer file is unanswered

- **WHEN** a questions-branch log file holds no answer, and the only
  answer file naming it in `answers` has `authority: input`
- **THEN** the log file counts as unanswered (design.md: *The newest
  proven answer counts*)

#### Scenario: A counting answer file makes a log file answered

- **WHEN** an answer file that counts as the person's answer names a log
  file in `answers`
- **THEN** that log file no longer counts as unanswered

### Requirement: The person's answer to a named file is their own, added alone

An answer file SHALL count as **the person's answer** only when it is the
answer of the log file it names in `answers`, under the inquisitor's *A
named file's answer is the newest proven answer file naming it*, which
states its conditions (design.md: *A named file's answer must be the
person's own, added alone*).

#### Scenario: An answer file proven to be the asked person's counts

- **WHEN** an answer file naming a log file that tags the person is
  proven to be the person's, and its commit adds it alone
- **THEN** it counts as the person's answer

#### Scenario: An answer file committed with another file does not count

- **WHEN** an answer file is proven to be the asked person's, but its
  commit also adds another file
- **THEN** it does not count as the person's answer

#### Scenario: A copy of another answer pushed alone counts

- **WHEN** an answer file naming a log file that tags the person copies the
  person's answer to another question, carries their comment link, and its
  commit adds it alone
- **THEN** it counts as the person's answer

#### Scenario: A file that tags no one is answered by an account with write access

- **WHEN** a log file tags no one, and an answer file naming it, added
  alone, is proven to be an account's with write access to the lore
  repository
- **THEN** it counts as the person's answer, the term holding although
  the file tags no person (design.md: *What the answer session posts, and
  what it logs*)

### Requirement: A poll position marks the newest message a poll read

A channel's **poll position** SHALL be the time of the newest message its
last poll read. GitHub's notifications endpoint, one feed for every
GitHub channel, SHALL have one poll position of its own: the
`Last-Modified` time of its last response.

#### Scenario: A channel's poll position is its newest message read

- **WHEN** a Linear team's last poll read messages up to one posted at
  10:04
- **THEN** that team's poll position is 10:04

#### Scenario: The notifications feed keeps one poll position

- **WHEN** GitHub's last notifications response carried a `Last-Modified`
  time
- **THEN** that time is the notifications feed's poll position, for every
  GitHub channel read through it

### Requirement: The same question means the same hash

Two questions SHALL count as **the same question** when they have the
same hash. The inquisitor spec defines a post's question text and its
hash; a log file's question is the text under its `## Question`, hashed
as that spec's *Among files with the same question, only the newest
proven answer counts* says.

#### Scenario: Two questions with one hash are the same question

- **WHEN** a miss file on a questions branch holds a question whose hash
  equals that of the question the answer session logs a miss for
- **THEN** the two count as the same question

#### Scenario: Questions with different hashes are different questions

- **WHEN** two posts ask questions whose hashes differ
- **THEN** they count as different questions

### Requirement: A thread copy is a question shown from a thread

The answer session SHALL count as a **thread copy** a question it shows
from a thread. A questions-branch log file **holds** a thread copy when
the file's `asked_in` links that thread message (design.md: *A log file
follows its thread message by exact link*).

#### Scenario: A question shown from a linked message is a thread copy the file holds

- **WHEN** the answer session shows a question from a GitHub comment that
  a questions-branch log file's `asked_in` links
- **THEN** the question is a thread copy, and that log file holds it

### Requirement: The state folder is under the XDG state home

The answer session's **state folder** SHALL be
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`.

#### Scenario: The state folder follows XDG_STATE_HOME

- **WHEN** `XDG_STATE_HOME` is `/x/state`
- **THEN** the state folder is `/x/state/inquisitor/answer-session/`

#### Scenario: The state folder defaults under the home folder

- **WHEN** `XDG_STATE_HOME` is not set
- **THEN** the state folder is
  `$HOME/.local/state/inquisitor/answer-session/`

### Requirement: The holder is the session whose answer session holds the lock

The answer session SHALL count as **the holder** the Claude Code session
whose answer session holds the lock that *One answer session runs on each
machine* defines, and as **a Claude Code background session** any Claude
Code session with no terminal attached, such as one started from an
app's list of sessions rather than from a terminal.

#### Scenario: A session started with no terminal that takes the lock is a background holder

- **WHEN** an app starts a Claude Code session from its list of sessions,
  with no terminal attached, and its answer session takes the lock
- **THEN** that session is the holder, and a Claude Code background
  session

### Requirement: Terms of the inquisitor's spec are judged as that spec has them

**What the question concerns**, **the repository the question concerns**,
**the team's lore repository** and **more visible** SHALL be as the
inquisitor's spec defines them, and the session's model SHALL judge what
a question concerns as that spec has an agent judge it. On GitHub, when
it can't tell, the repository the question concerns SHALL be the one
holding the question's thread.

#### Scenario: A GitHub question whose subject is unclear concerns its thread's repository

- **WHEN** a question in an issue of `o/web` gives the session's model no
  way to tell which repository it concerns
- **THEN** the repository the question concerns is `o/web`

#### Scenario: The model judges what a question concerns as an agent does

- **WHEN** a question in an `o/web` issue asks about code in `o/api`
- **THEN** the session's model judges what it concerns as the inquisitor's
  spec has an agent judge it, and the repository it concerns is `o/api`

### Requirement: The answer session's configuration is a section of the inquisitor's configuration

The answer session SHALL read, of `inquisitor.json`, only the top-level
`login` and `lore` and the `answer_session` section. That section holds
an object per **surface** used, `github`, `linear` or `discord`, naming
its relay identity, its **channels** (the person's subscriptions there, a
Discord channel with its threads) and, on Discord only, the person's user
id. The file SHALL hold no token or key, the Linear key staying in the
keychain, and a save SHALL keep keys it does not write.

#### Scenario: The answer session finds its configuration

- **WHEN** `~/.config/shared-skills/inquisitor.json` holds `login`,
  `lore` and an `answer_session` key whose `github` object names the
  relay `adam-relay` and subscribes to `o/api`
- **THEN** the answer session watches `o/api` and posts there as the
  github-app identity `adam-relay`

#### Scenario: Each surface's object names its relay identity and channels

- **WHEN** `answer_session` holds a `github`, a `linear` and a `discord`
  object
- **THEN** each object's `relay` names the surface's relay identity, by
  the name its skill, github-app, linear-app or discord-bot, takes with
  `--identity`, and its `subscriptions` lists its channels: on GitHub
  `owner/repo`, or `owner` for every repository of an owner; on Linear
  team keys; on Discord channel ids, a channel's id covering its threads
- **AND** only the `discord` object also holds `user`, the person's
  Discord user id

#### Scenario: No token is written into the configuration

- **WHEN** setup saves a Linear subscription
- **THEN** `inquisitor.json` holds the Linear team key and the relay's
  identity name, the relay's token stays with linear-app, and the
  person's Linear API key, which the answer session reads Linear with,
  is only in the system keychain

#### Scenario: A hand-written key survives a save

- **WHEN** the person has added to `inquisitor.json` a key the answer
  session does not know, and setup saves a new subscription
- **THEN** that key is still in the file, unchanged

### Requirement: The person runs the session, and a relay identity posts for them

**The person** SHALL be the one whose questions the answer session shows:
the one running it, whose login is the one the inquisitor's *A configured
login counts only when gh is logged in as it* sets; with no login
configured, as that requirement says, GitHub SHALL be off. A **relay
identity** SHALL be the bot of a surface's skill, github-app, linear-app
or discord-bot, that posts for them there, its token staying with that
skill.

#### Scenario: A login gh does not confirm turns GitHub off

- **WHEN** `inquisitor.json` names the login `adamstallard` but `gh` is
  logged in as another account, so no login is configured
- **THEN** the answer session reads no GitHub channel and posts nothing on
  GitHub

#### Scenario: A relay identity's token stays with its skill

- **WHEN** the answer session posts a relay post on Discord through the
  relay identity its `discord` object names
- **THEN** discord-bot posts it with the token discord-bot holds, and no
  answer-session file holds that token

### Requirement: Setup checks each relay identity before its channels are used

Setup SHALL check, showing failures and fixes: each relay identity, by its
skill's check; on Discord, that `messageContent` is `true`; and posting in
each subscribed channel. A channel is **on** while its identity's and
posting's last checks passed, else **off**. An unreadable posting check
(task 0.20) SHALL pass, shown as not checked, until a refused post fails
it. An off channel SHALL be neither read nor posted in; each opening SHALL
rerun any check that failed or never ran.

#### Scenario: A channel the relay cannot post in is off alone

- **WHEN** setup finds that the Discord relay cannot post in one of two
  subscribed Discord channels, and can post in the other
- **THEN** setup shows the failure and its fix, saves both channels, and
  the answer session reads and posts in the other channel only

#### Scenario: A failed identity check turns off its whole surface

- **WHEN** the GitHub relay's own github-app check fails
- **THEN** setup shows the failure and its fix, as github-app reports
  them, and every subscribed GitHub channel stays off

#### Scenario: A relay that cannot read message content keeps Discord off

- **WHEN** discord-bot's `check` reports, for the Discord relay,
  `messageContent` as `false`, or as `null` when it could not read the
  bot's application flags
- **THEN** setup shows that failure and says to turn on the bot's Message
  Content intent, or why the check could not read it, and every Discord
  channel stays off (design.md: *The Discord relay needs the Message
  Content intent*)
- **AND** only `messageContent` as `true` passes, whatever `check`
  reports as `memberSearch` (design.md: *Discord relay posts: no header,
  mentions that ping*)

#### Scenario: A refused post turns a channel no check can read off

- **WHEN** no check can read whether the Linear relay may post in a
  subscribed team (task 0.20), and Linear refuses a relay post there
- **THEN** the refusal counts as a failed posting check: the refused post
  is handled as *A failed relay post is reported to the person* says, a
  refused answer kept pending, and the team stays off until a check at a
  later opening passes

#### Scenario: A posting check no check can read is shown as not checked

- **WHEN** no check can read the Linear relay's right to post in a
  subscribed team, and the relay's own check passes
- **THEN** setup shows the team's posting check as not checked, never as
  passed, and the team counts as on (design.md: *A failed relay check
  turns off only its channel*)

#### Scenario: A passing recheck turns the channel on

- **WHEN** the Discord relay's last check of posting in a channel failed,
  and the person fixes its permission and opens the answer session
- **THEN** that channel is checked again and, once the check passes, read

### Requirement: Setup opens on an incomplete configuration and checks questions-branch commits

The answer session SHALL run setup in place of the queue while
`answer_session` is missing or no surface in it has both a `relay` and a
subscription, and on `/answer setup`. Setup SHALL offer the channels the
person can read, and save every channel whatever its checks found. It
SHALL warn, with the fix, when the `log` command's questions-branch
commits would not be the person's, signed with a key GitHub verifies,
showing that check as not checked when it cannot tell.

#### Scenario: A missing section opens setup

- **WHEN** the person opens the answer session and `inquisitor.json` has no
  `answer_session` key
- **THEN** setup runs instead of the queue

#### Scenario: Setup offers the person's channels

- **WHEN** setup runs, `gh` lists the repository `o/api` and the owner `o`
  for the person, their Linear key can read the team `ENG`, and the
  Discord relay has been added to a channel
- **THEN** setup offers `o/api`, `o`, `ENG` and that Discord channel to
  subscribe to

#### Scenario: Unsigned commits get a warning

- **WHEN** setup finds that the person's commits to a configured lore
  repository's questions branch would not be signed
- **THEN** setup warns that their answer files without a link will not
  count, says how to turn on signing, and saves the rest
- **AND** the warning turns nothing off, and setup reruns the check at
  each opening until it passes

#### Scenario: Answer files are committed as the person in an App project

- **WHEN** the answer session runs in a Claude Code session whose
  environment sets `GIT_AUTHOR_NAME` to a GitHub App's bot and turns
  signing off through `GIT_CONFIG_*`
- **THEN** `log` commits the answer file as the person, signed, never as
  the App, with those variables removed
- **AND** setup checks the identity and signing `log` would commit with
  once github-app's `GIT_AUTHOR_*`, `GIT_COMMITTER_*` and `GIT_CONFIG_*`
  settings are removed (design.md: *Setup checks questions-branch
  commits are the person's*)

#### Scenario: A signing key GitHub does not verify gets a warning

- **WHEN** the person's commits would be signed with a key GitHub does
  not list for their account
- **THEN** setup warns as for unsigned commits

#### Scenario: A commit check setup cannot make is not checked

- **WHEN** setup cannot tell whether questions-branch commits would be
  the person's and signed, such as while offline
- **THEN** setup shows that check as not checked, never as passed

#### Scenario: Setup runs again on request

- **WHEN** the person types `/answer setup` with the configuration
  complete
- **THEN** setup runs, showing the saved subscriptions as chosen

### Requirement: Setup proposes the person's relay file and its notice workflow

In each configured lore repository serving a subscribed GitHub channel,
setup SHALL open as the person, by host command, a pull request writing
their relay file, newly dated, if missing, lacking a relay or last changed
by another, and one adding a missing `relay-notice.yml`, each unless the
person has one open. It SHALL report links,
never push to the default branch, say when their relayed answers there
count, and say what a refused notice pull request loses, then carry on.

#### Scenario: Setup proposes the person's relays to the lore repository

- **WHEN** setup runs for a person subscribed to `o/api`, a configured lore
  repository serves `o`, and its default branch has no
  `relays/<the person's login>.yaml`
- **THEN** setup opens, through the person's `gh` login, a pull request
  to that lore repository writing that file: the relay's App slug under
  `github`, any Linear or Discord relay's id under `linear` or
  `discord`, and first the line `# confirmed by <login> on <date>`. It
  reports the link, pushes nothing to the default branch, and says the
  person's relayed answers there count only as input until it merges
  and the lore clone has fetched its default branch, or, for an Igor,
  until igor PR #208's lore read applies that commit (design.md: *An
  Igor reads relay files as of igor PR #208's applied commit*), and
  become input again if anyone else later changes the file
- **AND** setup opens it as a host command, like a relay post, with a
  fixed title and body the script writes and no word of the model's
  (design.md: *Setup's relay pull request*)

#### Scenario: Setup opens no second relay pull request

- **WHEN** setup runs again while the person's earlier pull request to
  their relay file in the lore repository is still open
- **THEN** setup opens no other pull request, and reports the open one's
  link

#### Scenario: Setup proposes nothing when the relays are listed

- **WHEN** setup runs, the person's relay file on the lore repository's
  default branch, last changed by a pull request they authored, lists
  each of their relay identities on every surface configured, and that
  branch holds `.github/workflows/relay-notice.yml`
- **THEN** setup opens no pull request to it

#### Scenario: Setup proposes the file again after someone else changed it

- **WHEN** setup runs, and the person's relay file lists each of their
  relay identities but was last changed by another person's pull
  request, so it does not count (design.md: *Who last changed a relay
  file ties it to its person*)
- **THEN** setup opens a pull request from the person rewriting it with a
  new first line, `# confirmed by <login> on <date>`, so it changes the
  file even when the relays listed are the same, and says their relayed
  answers there count only as input until it merges

#### Scenario: Setup proposes the notice workflow

- **WHEN** setup runs, the lore repository's default branch lacks
  `.github/workflows/relay-notice.yml`, and the person has no such pull
  request open
- **THEN** setup opens a separate pull request adding the inquisitor's
  `relay-notice.yml`, and reports its link

#### Scenario: A refused notice pull request does not stop setup

- **WHEN** GitHub refuses setup's pull request adding `relay-notice.yml`,
  because the person's `gh` login lacks the `workflow` scope
- **THEN** setup says so, says the person will not be told of changes to
  their relay file there, and carries on

### Requirement: Two commands open an answer session

The answer session SHALL open when the person types `/answer` in any
Claude Code session with the skill. Setup SHALL install the command
`answer`, an executable `~/.local/bin/answer` marked as setup's by a
comment on its second line, that runs exactly `CLAUDE_CODE_NO_FLICKER=1
claude --name Answers '/answer'`; leave alone, saying so, an `answer` file
without that comment; and say when `~/.local/bin` is not on `PATH`. No
environment variable SHALL open the answer session.

#### Scenario: The answer command starts an answer session

- **WHEN** the person runs, in a terminal, `answer`, setup's
  `~/.local/bin/answer`, whose second line is
  `# written by inquisitor answer-session setup`
- **THEN** Claude Code starts named `Answers`, in its fullscreen layout,
  and opens the answer session

#### Scenario: Setup leaves another answer command alone

- **WHEN** setup runs and `~/.local/bin/answer` is a file without setup's
  comment line
- **THEN** setup leaves it unchanged, and says the `answer` command was
  not installed

#### Scenario: Setup says when the command is not on PATH

- **WHEN** setup installs `~/.local/bin/answer`, and `~/.local/bin` is not
  on the person's `PATH`
- **THEN** setup says so

#### Scenario: No environment variable opens the answer session

- **WHEN** Claude Code starts in a session with the skill, whatever
  environment variables are set, and the person has not typed `/answer`
- **THEN** no answer session opens

### Requirement: A question asked of the person comes from one of four sources

The answer session SHALL show, as a question asked of the person, each
unanswered one of these, and nothing else:

1. a message in a subscribed channel that mentions the person;
2. a message there mentioning a relay identity of theirs, or replying
   to a relay post;
3. a pull request there requesting their review, or an issue there
   assigned to them;
4. a log file on a configured lore repository's questions branch whose
   question tags the person and which no handled file names.

#### Scenario: An agent's mention is a question

- **WHEN** an agent running the inquisitor posts, in a subscribed
  repository, a question tagging `@adamstallard`, the configured login
- **THEN** the answer session shows it as a question asked of the person

#### Scenario: A Linear issue assigned to the person is a question

- **WHEN** an issue in a subscribed Linear team is assigned to the person
- **THEN** the answer session shows it, and an answer to it posts a comment
  on that issue

#### Scenario: A review request is a question

- **WHEN** a pull request in a subscribed repository requests the person's
  review
- **THEN** it is shown, and an answer to it comments on that pull request

#### Scenario: A questions-branch file that tags the person is a question

- **WHEN** a configured lore repository's questions branch holds an
  unanswered log file, with no `asked_in`, whose question tags the person
- **THEN** it is shown as a question asked of the person

#### Scenario: A message in an unsubscribed channel is not a question

- **WHEN** someone mentions the person in a repository that no subscription
  covers
- **THEN** the answer session does not show it

### Requirement: Handled and answer files set how a questions-branch file shows

A handled file SHALL NOT be shown as a question. A log file named only by
answer files that do not count SHALL be shown with the newest of those
answer files beside it, as input (design.md: *The answer session writes a
handled file on every close of a questions-branch file*; *Closing works
by exact identity, never by matching*; *An answer file names the file it
answers*; *A named file stays shown until its answer counts*).

#### Scenario: A log file named only by input answers is shown with the newest

- **WHEN** a configured lore repository's questions branch holds an
  unanswered log file tagging the person, two `authority: input` answer
  files naming it in `answers`, and a handled file naming another log
  file that tags the person
- **THEN** the answer session shows the log file as a question, with the
  newer answer file beside it as input, and none of the answer files,
  the handled file or the other log file as a question

### Requirement: A reply to a relay post is read per surface

A message SHALL count as replying to a relay post as this requirement's
scenarios show for each surface; in an unthreaded GitHub conversation,
only the asker's next comment after the relay post SHALL count.

#### Scenario: A reply to the relay is a question

- **WHEN** someone replies on Discord to a relay post in a subscribed
  channel
- **THEN** the answer session shows the reply as a question asked of the
  person

#### Scenario: Replies to the relay on Linear and GitHub are questions

- **WHEN** after a relay post, someone comments after it in the same
  Linear comment thread, someone replies to it in a GitHub review
  thread, or the asker comments next in the GitHub issue or pull
  request conversation
- **THEN** the answer session shows each as a question asked of the
  person

#### Scenario: Only the asker's next comment replies in a GitHub conversation

- **WHEN** after a relay post in a GitHub issue's conversation, another
  person comments, then the asker comments twice
- **THEN** only the asker's first comment after the relay post counts as
  replying to it

### Requirement: Messages judged clearly not questions are ignored

The answer session SHALL ignore a message of the first two sources that
its model judges clearly not a question: it is not shown, nothing is
posted on it, and nothing is closed. An unclear one is shown (design.md:
*Messages that are not questions are ignored*). The asker's reply to a
`User asks: ` post is never ignored: whatever it says, it puts the
question that post asked about back in the queue, as *The thread is the
durable record of an answer* says.

#### Scenario: A message that is clearly not a question is ignored

- **WHEN** a comment in a subscribed repository mentions the person only
  to thank them, or asks a rhetorical question
- **THEN** it is not shown, nothing is posted on it, and nothing closes

#### Scenario: The asker's thanks after a clarifying question is not ignored

- **WHEN** the latest relay post naming a question starts with
  `User asks: `, and the asker replies to it only to thank the person
- **THEN** the reply is not ignored, and puts the question back in the
  queue with it

### Requirement: Whom a message reaches is set by its mentions

A message by a bot account, as *An agent's question comes from a bot
account or a log file* defines it, SHALL reach only the first person it
mentions; any other message, a relayed question and an agent's posted
under a person's own account included, SHALL reach each person it
mentions (design.md: *A bot's question reaches only the first person it
mentions*).

#### Scenario: A bot's message reaches only the first person it mentions

- **WHEN** an Igor's handback on an issue assigned to the person mentions
  `@maya` first and then the person
- **THEN** the person's answer session does not show it, and Maya's does,
  if she subscribes to that repository

#### Scenario: A person's message reaches everyone it mentions

- **WHEN** a person's comment mentions `@maya` and then the person
- **THEN** the person's answer session shows it as a question

### Requirement: A mention names a user outside code, quotes and links

A **mention** SHALL be of a user, as `@login` on GitHub, outside code
spans, code blocks, quoted lines and links; a team mention counts as
none.

#### Scenario: A team mention or a mention in code is no mention

- **WHEN** an Igor's handback, on an issue assigned to the person,
  mentions the team `@o/devs`, and `@maya` only in a code span, code
  block, quoted line or link
- **THEN** it mentions no one, and the person's answer session shows it
  under the third source

### Requirement: A handback is an igor- App's comment holding igor's marker

The answer session SHALL count as a **handback** only a comment by an
App whose slug starts with `igor-` holding a fixed marker that quoted
text cannot produce, which igor PR #216 is asked to give, in a form task
0.6 records (design.md: *igor's handback marker*).

#### Scenario: An Igor comment without the handback marker is not a handback

- **WHEN** an Igor posts, on an issue assigned to the person, a comment
  without the fixed handback marker, after a handback no relay post
  names
- **THEN** the answer session still shows the earlier handback, and does
  not treat the new comment as one

### Requirement: Only an item's newest handback is shown

An item an Igor handed back, and assigned to the person, SHALL be shown
only through its newest handback. Older handbacks are **passed over**:
each machine works this out from the thread alone, writes nothing for
them, and never shows them again, even once the newest is answered. A
review request alone SHALL NOT make such an item a question (design.md:
*Only an item's newest handback is open*).

#### Scenario: A newer handback passes over an older unanswered one

- **WHEN** an issue assigned to the person holds an Igor's handback no
  relay post names, and the Igor posts a newer handback on it
- **THEN** every answer session, from the thread alone, shows only the
  newer handback, writes nothing for the older, never shows the older
  one's log file again, even once the newer is answered, and an answer
  to the newer handback names only the newer one's log file

#### Scenario: A handed-back pull request is not also a review request

- **WHEN** a pull request assigned to the person holds an Igor's handback
  and requests the person's review
- **THEN** it is shown only through its newest handback, not also as a
  review request

### Requirement: An item's newest handback is open until a relay post names it

The newest handback SHALL be **open** until a relay post whose `Re: `
line holds its URL answers or handles it; while a `User asks: ` post
names it, it waits for the asker, out of the queue, like any question
(design.md: *Only an item's newest handback is open*).

#### Scenario: An answered handback is no longer open

- **WHEN** the relay posts `User says: ` on an issue assigned to the
  person, its `Re: ` line holding the URL of the issue's newest handback
- **THEN** that handback is no longer open, and is shown as answered, not
  in the queue

### Requirement: A handback that mentions no one goes to the item's assignee

A handback that mentions no one, and the Igor log file following it,
SHALL reach the item's assignee under the third source; one that
mentions people is still the item's open handback, under the first
(design.md: *A handback that mentions no one reaches the assignee*; igor
issue [igor #229](https://github.com/adamstallard/igor/issues/229)).

#### Scenario: A handback that mentions the assignee first reaches them

- **WHEN** an Igor's handback, on an issue assigned to the person,
  mentions the person and then `@maya`
- **THEN** it reaches the person's answer session

#### Scenario: A handback that mentions no one reaches the assignee

- **WHEN** an Igor's handback, on an issue assigned to the person,
  mentions no one
- **THEN** it reaches the person's answer session under the third source

#### Scenario: An Igor log file on someone else's item is not shown

- **WHEN** an Igor's log file links a handback comment that mentions no
  one, on an issue assigned to someone else
- **THEN** this person's answer session shows neither the issue nor the
  log file

#### Scenario: An Igor log file on an unassigned item is shown to no one

- **WHEN** an Igor's log file links a handback comment on an unassigned
  issue
- **THEN** no answer session shows the handback or its log file until
  someone is assigned the issue, and then only the assignee's

### Requirement: A log file follows the thread message its asked_in links

A log file whose `asked_in` links a thread message this machine reads
SHALL follow that message by exact link, taking whatever the answer
session decides about it, never shown on its own (design.md: *A log file follows its thread message by exact link*).

#### Scenario: A questions-branch file follows the message it links

- **WHEN** an agent's post in a subscribed repository tags the person, and
  the lore repository's questions branch holds a log file whose
  `asked_in` is that post's URL
- **THEN** the question is shown once, from the post's thread

#### Scenario: Declining the linked message declines the file

- **WHEN** the person declines a message that a questions-branch log
  file's `asked_in` links
- **THEN** the log file is not shown on its own either

#### Scenario: Ignoring the linked message ignores the file

- **WHEN** a message that a questions-branch log file's `asked_in` links
  is ignored as not a question
- **THEN** the log file is shown neither on its own nor with the message

### Requirement: A log file with no followed link is judged on its own

A log file with no `asked_in`, or linking a message this machine does not
read, SHALL be judged on its own, as of the fourth source, save as *An
Igor's log file follows its own handback comment* says. The answer
session SHALL NOT pair a file with a message by matching text (design.md:
*A log file without `asked_in` is never merged*; *A link this machine
never reads is not followed*).

#### Scenario: A log file linking a message this machine does not read is shown on its own

- **WHEN** a questions-branch log file's `asked_in` links a Discord
  message in a channel this machine does not subscribe to
- **THEN** the log file is shown on its own, as a question of the fourth
  source

#### Scenario: A log file linking an off channel or surface is shown on its own

- **WHEN** a log file's `asked_in` links a message in a channel this
  machine has off, or on a surface it has off or cannot read
- **THEN** the log file is shown on its own, as a question of the fourth
  source

#### Scenario: A log file whose Discord link was withheld is shown on its own

- **WHEN** a lore repository that is not private holds a log file whose
  `asked_in` the `log` command withheld (design.md: *`answer_link` and
  `asked_in` are withheld where they would leak*), whose question tags
  `@adamstallard`, and a Discord message
  this machine has polled, mentioning the person's Discord user, asks the
  same question, its text the same once mentions are removed
- **THEN** the log file and the message are shown as two questions, and
  neither is paired with the other

### Requirement: An Igor's log file follows its own handback comment

When the handback comment an Igor worker's log file links in `asked_in`
is on an issue or pull request in the repository its `asked_from` names,
the file SHALL follow that comment, shown only while it is its item's
newest handback; otherwise the file is shown on its own (design.md: *Each
Igor log file follows its own handback comment*). It SHALL follow the
comment, not be shown on its own, even on a machine that does not read
its item.

#### Scenario: An Igor's log file follows its handback comment

- **WHEN** an Igor worker's log file's `asked_in` is the URL of its
  handback comment on an issue assigned to the person, and the person
  answers that handback
- **THEN** the answer session relays the answer on the issue and pushes
  an answer file naming the log file

#### Scenario: A later Igor question on an answered item follows its handback comment

- **WHEN** the person answered an Igor's question on an assigned issue,
  and a later run on that issue posts a new handback comment and writes
  a new log file whose `asked_in` is that comment's URL, and the person
  answers the new handback
- **THEN** the new handback is shown as the issue's open handback, the
  answer is relayed on the issue, and an answer file naming the new log
  file is pushed

#### Scenario: An Igor question about another repository follows its handback

- **WHEN** an Igor's log file has `repository: o/api` and `asked_from:
  o/web`, and its `asked_in` links a handback on an issue in `o/web`
- **THEN** the answer session follows the link, and an answer to that
  handback names the log file

#### Scenario: A log file linking an Igor comment without the marker is shown on its own

- **WHEN** a log file's `asked_in` links a comment by an `igor-` App that
  holds no handback marker
- **THEN** the log file is shown on its own

#### Scenario: A handback link from another App is not followed

- **WHEN** a log file's `asked_in` links a comment by an author that is
  not an App with an `igor-` slug
- **THEN** the comment is not followed, and the log file is shown on its
  own

### Requirement: A relay-notice comment is shown as a notice

A `github-actions[bot]` comment whose first line is the relay notice's,
as the inquisitor's *A pull request that changes a relay file mentions
its person* gives it, SHALL be shown as a notice, not a question, with
nothing posted on it and no miss logged.

#### Scenario: A relay notice is shown, never answered

- **WHEN** the relay-notice workflow comments on a pull request in the
  lore repository, mentioning the person, with its fixed first line
- **THEN** the answer session shows the comment to the person as a
  notice, posts nothing on it, and logs no miss

### Requirement: A question is resolved once answered or declined

A question SHALL count as **resolved** once it is answered and, if a
questions-branch file holds it, its answer file is pushed (*A
questions-branch answer's file is pushed after its post*; *An answer
whose thread is unreachable here is logged at once*), or once its
decline takes effect. A decline with nothing posted resolves it only on
the declining machine
(design.md: *Declining with nothing to answer closes only that
question*; *The push order for a questions-branch answer*).

#### Scenario: A held thread copy is resolved once its answer file is pushed

- **WHEN** the person answered, in a GitHub issue, a thread copy (a
  question shown from its thread) that a questions-branch file holds, as
  *A thread copy is a question shown from a thread* defines holding, and
  its answer file was pushed
- **THEN** the question counts as resolved

### Requirement: Later messages after an answer or a decline are new questions

Each later message in a resolved question's thread that a source names,
and that *Messages judged clearly not questions are ignored* does not
ignore, SHALL be shown on every machine as a new question of its own,
under that source (design.md: *Declining with nothing to answer closes
only that question*; *Closing works by exact identity, never by
matching*).

#### Scenario: A later message in an answered or declined thread is a new question

- **WHEN** the person answered a question in a GitHub issue, or declined
  one there with nothing to answer where the relay had posted before
  it, and the asker then comments again without a mention, or someone
  mentions the person there
- **THEN** every machine shows the comment as a new question, under the
  second source or the first, and the declined question stays closed
  where it was declined

#### Scenario: A later message after a decline for the inquisitor is a new question

- **WHEN** the person declined a question in a GitHub issue as one the
  inquisitor should have handled, picking filter 2, the relay posted
  filter 2's reply, and the asker then comments again without a mention
- **THEN** every machine shows the comment as a new question, under the
  second source, and the declined question stays handled

### Requirement: The answer session polls only while it is open

The answer session SHALL poll its channels only while it is open in the
holder, and nothing SHALL poll while none is open. It SHALL poll each
channel that is on when it opens and about every 60 seconds after, for
everything since its poll position, or the last 14 days without one,
saving each poll position in the state folder, and at each poll SHALL
fetch the questions branch of each configured lore repository.

#### Scenario: Opening catches up

- **WHEN** the answer session opens after two days closed
- **THEN** it polls each channel that is on for everything since that
  channel's poll position, and saves each new poll position

#### Scenario: A new channel is read from 14 days back

- **WHEN** the person subscribes to a repository, and the answer session
  polls it for the first time
- **THEN** it reads that repository's messages from the last 14 days

#### Scenario: Nothing polls while the answer session is closed

- **WHEN** no Claude Code session on the machine has an answer session open
- **THEN** nothing polls any channel

#### Scenario: Each poll fetches the questions branches

- **WHEN** the answer session polls, and the inquisitor's configuration
  names a lore repository
- **THEN** it fetches that lore repository's questions branch

### Requirement: The answer session polls GitHub's notifications and comments

On GitHub the answer session SHALL read notifications conditionally,
sending the previous response's `Last-Modified` time, no sooner than the
`X-Poll-Interval` of GitHub's last response.

#### Scenario: GitHub's poll interval is honoured

- **WHEN** GitHub's last notifications response set `X-Poll-Interval: 120`
- **THEN** the answer session waits at least 120 seconds before reading the
  notifications endpoint again, and sends the `Last-Modified` time it
  received

### Requirement: Until notifications are measured, the poll reads every GitHub question source

Unless task 0.15 has shown that notifications report every GitHub
mention, relay reply, review request and assignment (the first three
sources of *A question asked of the person comes from one of four
sources*), the answer session SHALL also read, at each
GitHub poll and since its poll position, each subscribed repository's new
issues and pull requests, their comments, reviews and review-thread
comments, and the review requests and assignments naming the person.

#### Scenario: Comments are read until the notifications endpoint is measured

- **WHEN** task 0.15 has not shown that the notifications endpoint reports
  every GitHub message of the first three question sources, and the
  answer session polls a subscribed repository
- **THEN** it reads that repository's new issues and pull requests, their
  comments, reviews and review-thread comments, and the review requests
  and assignments naming the person, since its poll position

#### Scenario: A review request and a review-thread reply are found without notifications

- **WHEN** task 0.15 has not shown that notifications report every GitHub
  message of the first three question sources, and since the last poll a pull
  request in a subscribed repository requested the person's review, and
  someone replied in one of its review threads to a relay post, with
  neither reported as a notification
- **THEN** the answer session shows both as questions asked of the person

### Requirement: The answer session reads with the person's credentials, except on Discord

The answer session SHALL read GitHub with the person's `gh` login and
Linear with the person's Linear API key, and SHALL use the GitHub and
Linear relay identities only to check them, to post, and to edit their
own relay posts. On Discord, the Discord relay identity SHALL both read
and post, in the channels it has been added to.

#### Scenario: Reading uses the person's gh login

- **WHEN** the answer session reads a subscribed repository's notifications
- **THEN** it reads them through the person's `gh` login, not as the
  GitHub relay identity

#### Scenario: Discord is read by its relay

- **WHEN** a subscribed Discord channel is read
- **THEN** it is read as the Discord relay identity, which also posts
  there

#### Scenario: Posting uses the relay identity

- **WHEN** the person relays an answer to a question on GitHub
- **THEN** the comment is posted as the GitHub relay identity, not as the
  person's `gh` login

### Requirement: An answer is relayed as the person's words

For an answer, the answer session SHALL post `User says: ` and the
answer exactly as confirmed, as the relay identity in the question's
thread, keeping the post's id in the state folder, and naming the
question as *A GitHub or Linear relay post names its question in a Re
line* says. On
Discord it SHALL use discord-bot without header options and mention
rewriting on, showing the person its warnings after each post and edit
(design.md: *Discord relay posts: no header, mentions that ping*).

#### Scenario: An answer is posted with its prefix

- **WHEN** the person answers, with "Back off, capped at a minute.", a
  question asked in a comment on a GitHub issue
- **THEN** the relay identity comments on that issue
  `User says: Back off, capped at a minute.`, ending with a `Re: ` line
  holding the question comment's URL, and the comment's id is saved in
  the state folder

#### Scenario: An answer in a review thread or on Linear stays in its thread

- **WHEN** the person answers a GitHub review comment, or a comment on a
  Linear issue
- **THEN** the relay replies in that review thread, or comments in that
  Linear comment thread

#### Scenario: A Discord answer replies to the question

- **WHEN** the person answers a question asked in a subscribed Discord
  channel
- **THEN** the Discord relay posts the answer as a reply to the question's
  message

#### Scenario: A Discord relay post has no header and pings whom the person names

- **WHEN** the person confirms the Discord answer "ask @maya, see #ops",
  and the channel's server has a member maya and a channel ops
- **THEN** the relay posts through discord-bot with none of `--agent`,
  `--session` or `--project`, so the message starts `User says: ask `,
  then a mention of maya that notifies her, and `#ops` links to that
  channel

#### Scenario: An unmatched Discord name is shown to the person

- **WHEN** the person confirms the Discord answer "ask @maya", and
  discord-bot posts it warning that `@maya` matched no single member, as
  no member's name, or several members' names, match it
- **THEN** `@maya` stays plain text and pings no one, and the answer
  session shows the person that warning after the post

#### Scenario: Refused member search does not fail setup

- **WHEN** discord-bot's `check` reports `messageContent` as `true` and
  `memberSearch` as `false` for the Discord relay, and every other check
  passes
- **THEN** setup counts the Discord relay's check as passed
- **AND** a later Discord relay post leaves every `@name` plain text,
  under one warning saying so, which the person is shown

#### Scenario: Warnings are shown after an edit too

- **WHEN** the person edits a Discord relay post to "ask @maya", and
  discord-bot's `edit` returns a warning that `@maya` matched no member
- **THEN** the person is shown that warning after the edit

### Requirement: A GitHub or Linear relay post names its question in a Re line

A relay post on Linear, or on GitHub outside a review thread, SHALL end
with a `Re: ` line holding the URL of the question it names. For a
question in a comment, that is the comment's URL. For a handback, it is the
handback comment's URL. For a question in an issue's or pull request's
description, or a review request or assignment, it is the item's URL. On
Discord a relay post SHALL name its question by replying to it.

#### Scenario: A Linear relay post names its question in its Re line

- **WHEN** the person answers a question asked in a comment on a Linear
  issue, and another question that is a Linear issue assigned to them
- **THEN** the Linear relay's comment answering the first ends with
  `Re: ` and that comment's URL, and its comment answering the second
  ends with `Re: ` and the Linear issue's URL

#### Scenario: A GitHub answer to an item or a handback names it in its Re line

- **WHEN** the person answers a question that is an issue's or pull
  request's description, a review request, an assignment, or an Igor's
  handback
- **THEN** the relay's comment ends with `Re: ` and the URL of the issue
  or pull request, or, for a handback, of the handback comment

### Requirement: A relay post is posted by a host command, unvetted

The answer session SHALL post through the relay identity's skill as a
command it runs on the host, never as a tool call of the session's model,
as an argument vector with no shell, passing the post's text on standard
input or in a private file. Neither prose's pass nor the inquisitor's
filters SHALL apply to a relay post. The answer session SHALL scan every
relay post for the inquisitor's credential patterns, and SHALL post
nothing that matches.

#### Scenario: A relay post carries no prose footer and is not vetted

- **WHEN** the person relays an answer that holds a question
- **THEN** the post holds the person's words as confirmed, with no prose
  footer, and no hook blocks it

#### Scenario: A post's text file is private

- **WHEN** a relay post's text is passed to the relay identity's skill in
  a file
- **THEN** the file has mode 0600, in a directory only the person's user
  can read

#### Scenario: Shell syntax in an answer runs nothing

- **WHEN** the person's answer holds `$(rm -rf ~)` and a backtick
- **THEN** the relay post holds that text as written, and no shell runs it

#### Scenario: An answer holding a credential is not posted

- **WHEN** the person's answer holds a string shaped like a GitHub access
  token
- **THEN** the answer session posts nothing, and says why

### Requirement: A failed relay post is reported to the person

When a surface refuses a relay post or its command fails, the answer
session SHALL tell the person why nothing was posted, as the surface or
skill says. A failed answer stays pending; a failed question to the
asker leaves its question as it was; a failed automatic post leaves its
question shown as unanswered. A refused post can also turn its channel
off, as *Setup checks each relay identity before its channels are used*
says.

#### Scenario: A post the surface refuses keeps the answer pending

- **WHEN** the person relays a Discord answer of 2,500 characters, and
  Discord refuses it
- **THEN** the answer session says that nothing was posted and gives
  Discord's reason, and keeps the answer as answered, not relayed

#### Scenario: A failed question to the asker leaves its question as it was

- **WHEN** the person asks the asker of an unanswered question what they
  mean, and the relay's command fails
- **THEN** the person is told nothing was posted and why, and the
  question stays unanswered, not waiting for the asker

#### Scenario: A failed automatic post shows its question as unanswered

- **WHEN** the answer session makes a `Recorded answer: ` post by itself
  on an incoming question, and the relay's command fails
- **THEN** the person is told nothing was posted and why, and is shown
  the question as unanswered

### Requirement: An answer that cannot reach its thread is kept pending

The answer session SHALL keep, never drop, a confirmed answer that cannot
be posted in its thread, as **answered, not relayed**, with its thread,
on the pending list: when its channel is off or not read here (design.md:
*A link this machine never reads is not followed*), or its post is
refused, fails or is held back by a reply. It tells the person, as *Only
the person is told an answer is pending* says.

#### Scenario: A refused answer is kept pending

- **WHEN** the person confirms an answer and Discord refuses the relay
  post, as for lack of permission
- **THEN** the answer session keeps the answer as answered, not relayed,
  tells the person the asker has not got it yet, and shows its text

#### Scenario: An answer given where the thread is not read is kept pending

- **WHEN** a log file's `asked_in` links a Discord message, and the person
  answers the log file on a machine not subscribed to that message's
  channel
- **THEN** the `log` command pushes an answer file naming the log file,
  the answer is kept as answered, not relayed, and the person is told
  the asker has not got it (design.md: *A link this machine never reads
  is not followed*)

### Requirement: Only the person is told an answer is pending

Each time it keeps an answer pending, the answer session SHALL tell the
person that the asker has not got it, and show the answer's text for
them to relay by hand; no
other machine is told (design.md: *An answer that cannot reach its thread
is kept pending*).

#### Scenario: Another machine asks again while an answer is pending

- **WHEN** one machine holds an answer as answered, not relayed, and
  another machine reads the question's thread, which holds no relay
  post naming the question
- **THEN** the other machine shows the question as unanswered and asks
  it as usual

### Requirement: A pending answer whose channel was off returns to the queue

An answer kept because its channel was off, or because a post refused for
permission turned its channel off, SHALL return to the queue, its answer
kept, once setup's check of posting there passes, as *Setup checks each
relay identity before its channels are used* runs it, and SHALL be posted
only once the person confirms it again. Where no check can read posting
rights (task 0.20), that check passes once setup, at the next opening,
reruns the relay identity's own check and it passes.

#### Scenario: A pending answer returns to the queue once its channel passes its check

- **WHEN** a pending answer's channel was off, and that channel's check
  then passes
- **THEN** the question goes back into the queue with the answer kept,
  and is posted once the person approves it again

#### Scenario: An answer refused for permission returns once the relay's own check passes

- **WHEN** no check can read the Linear relay's right to post in a team,
  Linear refuses a relay post there for lack of permission, turning the
  team off, and at the next opening the Linear relay's own check passes
  again
- **THEN** the answer returns to the queue, kept, and is posted only once
  the person confirms it again

### Requirement: A pending answer no check returns waits for the person

A pending answer that *A pending answer whose channel was off returns to
the queue* does not return SHALL stay until the person acts on it,
whatever check passes, even when the surface refused its post for its
text, such as its length, not for permission, and that refusal turned its
channel off. The person SHALL be able to edit or drop
a pending answer at any time, and post it while its channel is on and
subscribed here; a dropped answer is never posted.

#### Scenario: A text refused for its length stays pending after a recheck

- **WHEN** no check can read the Linear relay's right to post in a
  channel, Linear refuses a relay post there as too long, and setup's
  check of that channel later passes
- **THEN** the answer stays on the pending list, and does not go back
  into the queue

#### Scenario: A refused answer stays pending after its channel's check passes

- **WHEN** this machine holds an answer refused for its length, and the
  check of posting in its channel then passes
- **THEN** the answer stays pending until the person edits, posts or
  drops it

#### Scenario: The person edits and posts a pending answer

- **WHEN** the person edits an answer on the pending list for a channel
  that is on, and confirms it
- **THEN** the edited text is posted in the thread

#### Scenario: A dropped pending answer is never posted

- **WHEN** the person drops an answer from the pending list
- **THEN** nothing is posted for it, and the question's state is read
  from its thread

### Requirement: A refusal the session cannot place waits for the person

A refusal the session cannot place as one for its text or one for
permission, by the mapping task 0.25 records for each surface, SHALL be
handled as a refusal for its text: the answer stays pending until the
person acts on it, shown with the surface's error, whatever check passes.

#### Scenario: A refusal the session cannot place waits for the person

- **WHEN** Discord refuses a relay post with an error that task 0.25's
  mapping places neither as a refusal for its text nor as one for
  permission, and the channel's check later passes
- **THEN** the answer stays on the pending list, shown with Discord's
  error, until the person edits, posts or drops it, and does not go back
  into the queue

### Requirement: A pending answer leaves the list once it is settled

An answer SHALL leave the pending list once it is back in the queue,
posted or dropped, once a relay post naming its question appears in the
thread, or, for one whose file was pushed, once a newer answer file than
its own that counts as the person's answer names the same
questions-branch file.

#### Scenario: A relay from another machine clears a pending answer

- **WHEN** another machine relays in the thread an answer this machine
  holds as answered, not relayed
- **THEN** the answer leaves this machine's pending list, and the question
  shows as answered

#### Scenario: A newer answer file clears a pending answer

- **WHEN** this machine holds an answer whose file it pushed, and another
  machine, or any other writer, pushes a newer answer file naming the
  same questions-branch file
- **THEN** this machine's pending list no longer holds the answer

### Requirement: A questions-branch answer's file is pushed after its post

For a question a questions-branch file holds, once the fetch before the
post finds no new message, the answer session SHALL record the **owed
push**, with the answer and the thread, in the state folder, post, add
the post's URL to the record, then push the answer file with that URL as
its `answer_link`, retrying a failed push at each poll and opening, as
for a handled file (design.md: *The push order for a questions-branch
answer*).

#### Scenario: An owed push survives a crash

- **WHEN** an answer's relay post goes out, and the answer session stops
  before pushing the answer file
- **THEN** at its next opening it pushes the answer file it recorded as
  owed

#### Scenario: A failed answer-file push is retried

- **WHEN** the relay post of an answer to a thread copy (a question shown
  from its thread) goes out, a questions-branch file's `asked_in` linking
  that thread's message, and the push of its answer file then fails
- **THEN** the answer session retries the push at each poll, with the
  post's URL as the file's `answer_link`, until it succeeds or *An owed
  push's retry stops when answered or refused for good* drops it

### Requirement: An owed push with no URL is settled from the thread

The answer session SHALL settle an owed push recorded with no post's URL
from the thread at the next poll or opening: it takes the URL of a relay
post there naming the question and holding this answer, or else drops
the record and keeps the answer pending.

#### Scenario: An owed push whose post never went out is dropped

- **WHEN** the answer session recorded an owed push and stopped before
  the relay post went out, and the thread holds no relay post naming the
  question
- **THEN** it drops the record, pushes no file, and keeps the answer
  pending

#### Scenario: An owed push whose post went out takes its URL from the thread

- **WHEN** an owed push was recorded with no post's URL, and the thread
  holds a relay post naming the question whose text is this answer
- **THEN** at the next poll or opening, the retry pushes the answer file
  with that post's URL as its `answer_link`

### Requirement: An owed push's retry stops when answered or refused for good

The answer session SHALL drop an owed push's retry once an answer file
counting as the person's answer names the same file, if this machine
first saw it at a fetch after recording the push (design.md: *The push
order for a questions-branch answer*). It SHALL NOT retry a
push the `log` command refuses for a reason that will not change,
telling the person the answer was relayed but not logged, and why.

#### Scenario: A push the log command refuses for good is not retried

- **WHEN** the `log` command refuses an owed push for lack of access, for
  a relay post it cannot read, or for an answer whose words the lore
  repository is too visible to hold
- **THEN** it is not retried, and the person is told the answer was
  relayed but not logged, and why

#### Scenario: An answer file first seen after the record drops the retry

- **WHEN** this machine retries an owed push, and a fetch after recording
  it first shows an answer file counting as the person's answer that
  names the same questions-branch file
- **THEN** the answer session drops the retry and pushes no file for it
- **AND** an answer file naming that file that this machine had already
  seen when it recorded the push does not drop the retry

#### Scenario: The machine's own earlier file does not cancel an edited answer's push

- **WHEN** this machine pushed the answer "Use Postgres" at once while the
  thread's channel was off, as *An answer whose thread is unreachable here
  is logged at once* says
- **AND** the person then edits it to "Use SQLite", it is posted once the
  channel is on, and the push of the edited answer's file fails
- **THEN** the answer session keeps retrying that push, and the
  "Use Postgres" file does not drop the retry

### Requirement: The log command commits with the person's git identity

The answer session SHALL run the `log` command without the
`GIT_AUTHOR_*`, `GIT_COMMITTER_*` and `GIT_CONFIG_*` settings github-app
sets, so that it commits with the person's git identity and signing,
never a GitHub App's (design.md: *Setup checks questions-branch commits
are the person's*).

#### Scenario: The log command drops github-app's git settings

- **WHEN** the answer session pushes an answer file from a Claude Code
  session whose environment holds github-app's `GIT_AUTHOR_*`,
  `GIT_COMMITTER_*` and `GIT_CONFIG_*` settings
- **THEN** it runs the `log` command without them, and the commit carries
  the person's git identity and signing, not the App's

### Requirement: An answer whose thread is unreachable here is logged at once

For a question a questions-branch file holds, an answer whose channel is
off or not subscribed here, when confirmed or once a refused post turned
it off, SHALL have its file pushed at once, without fetching its thread
first, with no
`answer_link`, holding the answer as confirmed (design.md: *A logged
answer is the person's own words*; *The push order for a
questions-branch answer*). Any other pending answer SHALL push no file
before its post.

#### Scenario: An answer to a questions-branch question is logged at once

- **WHEN** the person confirms an answer to a thread copy a
  questions-branch file holds, and the thread's channel is off
- **THEN** the `log` command pushes an answer file naming that file, with
  no `answer_link`, holding the answer as confirmed, and the answer is
  kept as answered, not relayed

#### Scenario: A refusal that turns the channel off pushes the file at once

- **WHEN** the person confirms an answer to a thread copy a
  questions-branch file holds, and the surface's refusal of the relay
  post turns the thread's channel off
- **THEN** the `log` command pushes an answer file naming that file, with
  no `answer_link`, holding the answer as confirmed, and the answer is
  kept as answered, not relayed

#### Scenario: An answer held back by a new message pushes no file

- **WHEN** the person confirms an answer to a thread copy a
  questions-branch file holds, and the fetch before the post, under *The
  thread is read again before a question is shown and before a post*,
  finds a new message in the thread
- **THEN** nothing is posted or pushed, and the answer stays pending
  until the person posts or drops it

### Requirement: An answer logged at once gets a new file only when posted edited

Posting later an answer whose file was pushed at once SHALL push a new
file only when its text was edited, as *An edit to a questions-branch
answer pushes a new log file* says. For a question a questions-branch
file holds, dropping a pending answer, edited or not, SHALL push no file,
and leaves a file already pushed, with its original text, as the
person's answer.

#### Scenario: An edited answer pushed at once pushes a new file when posted

- **WHEN** the person edits an answer whose file this machine pushed at
  once, and posts it once its channel is on
- **THEN** the `log` command pushes a new answer file naming the same
  file, with the relay post's URL as its `answer_link`; posted unedited,
  it pushes no second file

#### Scenario: An edited pending answer that is dropped leaves the original file

- **WHEN** this machine holds, for a channel that was off, an answer whose
  file it pushed, and the person edits it and then drops it
- **THEN** nothing is posted, no new file is pushed, and the pushed file
  with the original text stays the person's answer

### Requirement: A relay post can be edited where it was posted

The answer session SHALL let the person edit the latest relay post
naming a question, whatever its prefix, and SHALL edit it in place, as
the relay identity that posted it, found by the id the state folder keeps
or, where this machine lacks it, in the question's thread. The edit SHALL
keep the `Re: ` line and a `User says: ` or `User asks: ` prefix; an
automatic post's becomes `User says: `. The edited text is scanned as a
new post is.

#### Scenario: An answer is edited in place

- **WHEN** the person edits an answer they relayed on Linear
- **THEN** the Linear relay updates its own comment, which still starts
  with `User says: `, and posts no new comment

#### Scenario: An edited automatic post becomes the person's words

- **WHEN** the person edits a post that starts with `Recorded answer: `
- **THEN** the relay updates that post, which now starts with
  `User says: ` and holds the text the person confirmed

#### Scenario: An edit is scanned as a new post is

- **WHEN** the person's edit of a relay post holds a string shaped like a
  GitHub access token
- **THEN** the post is not changed, and the person is told why

#### Scenario: An edit on another machine finds the post in the thread

- **WHEN** the person edits, on their second machine, an answer relayed
  from their first
- **THEN** the answer session finds the relay post in the question's thread
  and edits it

### Requirement: An edit to a questions-branch answer pushes a new log file

When an edit leaves a `User says: ` answer to a question an unanswered
questions-branch log file holds, the answer session SHALL push a new log
file naming that file in `answers`, as *A questions-branch question is
answered by a new log file* does, holding the earlier answer file's
question or, if none, the question the person saw. Every earlier file SHALL stay unchanged;
the newest counts, by the inquisitor's *A named file's answer is the
newest proven answer file naming it*.

#### Scenario: Editing an agreed recorded answer into the person's words pushes a log file

- **WHEN** the person agreed to the recorded answer shown for a question
  in a GitHub thread that an unanswered log file on the lore
  repository's questions branch also holds, and then edits that post so
  it starts with `User says: `
- **THEN** the relay updates its post, and the script pushes a new log
  file holding the question as the person saw it and the edited answer,
  the question's first answer file there, since agreeing pushed none

#### Scenario: Editing an answer the questions branch also logged pushes a new log file

- **WHEN** the person edits a `User says: ` answer relayed in a GitHub
  thread to a question an unanswered questions-branch log file holds,
  whose answer the answer session had logged
- **THEN** the relay updates its post, and the script pushes a new log
  file naming the unanswered file in `answers`, with the earlier answer
  file's question, the edited answer and the relay post's URL as
  `answer_link`, leaving both earlier files unchanged
- **AND** the new file is the one that counts

### Requirement: The person can ask the asker

The answer session SHALL let the person ask the asker for clarification
instead of answering. It SHALL post the clarifying question as it posts an
answer, naming the question the same way, except that the post starts
with `User asks: ` and tags the asker when the asker is a person. The
question then waits for the asker.

#### Scenario: A clarifying question goes to the asker's thread

- **WHEN** the person asks Maya, who asked a question on Linear, what she
  means by "soon"
- **THEN** the Linear relay posts, in the question's comment thread, a
  comment that starts with `User asks: ` and mentions Maya

#### Scenario: A clarifying question to an Igor worker goes on the item

- **WHEN** an Igor's worker asked a question in its handback comment on
  an issue, in a subscribed repository, assigned to the person, and the
  person asks back
- **THEN** the relay posts the clarifying question on that issue, starting
  with `User asks: `, where whichever worker next takes the item reads it

### Requirement: The thread is the durable record of an answer

The answer session SHALL take a question's state from the latest relay
post naming it in its thread: `User says: ` answered; `Recorded answer: `
answered, and `Inquisitor: ` handled, for the person, listed apart from
the queue; `User asks: ` waiting for the asker, whose reply returns it to
the queue with the reply; otherwise unanswered. This machine adds only a
pending answer and a close; the close wins over the thread (design.md:
*Closing works by exact identity, never by matching*).

#### Scenario: A relay reply marks the question answered on every machine

- **WHEN** the person answered a question on one machine, and opens the
  answer session on another
- **THEN** the second machine shows the question as answered, from the
  relay post in its thread

#### Scenario: An answer to one question leaves another in the thread open

- **WHEN** a GitHub issue's conversation holds two comments that each tag
  the person, and the relay has answered the second, naming it
- **THEN** the second shows as answered and the first as unanswered

#### Scenario: An automatic post marks the question answered or handled for the person

- **WHEN** the latest relay post naming one question starts with
  `Recorded answer: `, and the latest naming another starts with
  `Inquisitor: `
- **THEN** the first is listed as answered for the person and the second
  as handled for them, where the person can see and edit what was
  posted, and neither is in the queue

#### Scenario: A question declined on one machine is open on another

- **WHEN** the person declines with nothing posted, on one machine, a
  question that no questions-branch file holds, and opens the answer
  session on another
- **THEN** the first machine keeps it closed whatever its thread holds,
  and the second shows the question as unanswered, for the person to
  decline again

#### Scenario: A clarifying question marks it waiting

- **WHEN** a question's latest relay post naming it starts with
  `User asks: `, and the asker has posted nothing since
- **THEN** the question shows as waiting for the asker

#### Scenario: The asker's reply brings the question back

- **WHEN** the asker replies to the relay's clarifying question, whether
  or not the reply is itself a question
- **THEN** the reply is shown as a question asked of the person, with the
  question it answers

#### Scenario: A post lost from local state still marks the question answered

- **WHEN** a relay post succeeded, and the state folder holds no record of
  it
- **THEN** the question shows as answered, from the thread

### Requirement: A questions-branch question's state is read from its branch

A questions-branch file SHALL count as answered once an answer file naming
it in `answers` counts as the person's answer (design.md: *An answer file
names the file it answers*; *A named file stays shown until its answer
counts*). Only a handled file naming it SHALL close it, on every machine
and for good, under *A handled file closes a questions-branch question*.
A closed file stays unanswered: answering its open thread copy still
pushes a log file.

#### Scenario: An answer file that does not count leaves its file shown

- **WHEN** an `authority: input` answer file names a questions-branch file
  in `answers`
- **THEN** the named file is still shown as a question, with that answer
  beside it as input

#### Scenario: An answer to a closed file's thread copy still logs

- **WHEN** a handled file names a questions-branch file, and the person
  answers the thread copy it holds on a machine where that copy is still
  open
- **THEN** the answer is relayed, and a log file naming that
  questions-branch file is pushed

### Requirement: The thread is read again before a question is shown and before a post

When a question comes on screen and its channel's last poll is more than
about a minute old, the answer session SHALL fetch and show every reply in
its thread since the question; only a relay post naming it changes its
state. Before each relay post it SHALL fetch the thread
again, and post nothing when it holds a relay post that answers or
handles the question, showing it in that state, or a reply the person has
not seen, showing that reply and keeping a held-back answer pending.

#### Scenario: Replies since the question are shown

- **WHEN** a question comes on screen, its channel was last polled 3
  minutes ago, and two people have replied in its thread since the question
- **THEN** the thread is fetched and both replies shown, and the question
  stays unanswered

#### Scenario: An answer relayed elsewhere is not posted twice

- **WHEN** the person relays an answer, and the thread already holds a
  relay post answering the question, made from another machine
- **THEN** nothing is posted, and the question shows as answered, as *The
  thread is the durable record of an answer* says

#### Scenario: A new reply stops the post

- **WHEN** the person relays an answer after the asker has replied in the
  thread since the question was shown
- **THEN** nothing is posted, and the asker's reply is shown

### Requirement: Local state is per machine, in the state folder

The answer session SHALL keep its working state per machine in the state
folder, and nowhere else, as its scenario lists. Filter 1 SHALL never
search it. A discussion record SHALL be deleted once its question is
answered, answered or handled for the person, or closed; a pending answer
outlives it. On opening, the answer session SHALL show the question last
on screen, even after Claude Code restarted, unless it has since been
answered.

#### Scenario: The state folder holds all working state

- **WHEN** the answer session saves its working state
- **THEN** it writes only to the state folder: the questions set aside
  for later, the closed questions, each open question's discussion
  record, each channel's and the notifications feed's poll position,
  each check's last result, relay post ids, the question on screen, the
  answers held as answered, not relayed, each owed answer-file,
  handled-file, miss-file or citation-file push (design.md: *The push
  order for a questions-branch answer*; *Misses the answer session
  logs*), and the lock

#### Scenario: Filter 1 never searches the state folder

- **WHEN** a question's discussion record in the state folder holds text
  that answers a later question
- **THEN** filter 1's search for that later question does not read the
  state folder, and shows no hit from it

#### Scenario: Reopening lands on the same question

- **WHEN** the person closes Claude Code with a question on screen, starts
  it again, and opens the answer session
- **THEN** the answer session shows that question

#### Scenario: Reopening skips a question answered meanwhile

- **WHEN** the question on screen when the answer session closed has since
  been answered from another machine
- **THEN** on opening, the answer session shows the next question in the
  queue instead

#### Scenario: An answered question's discussion record is deleted

- **WHEN** the person discusses a question, then relays an answer to it
- **THEN** the state folder no longer holds that question's discussion
  record

#### Scenario: A question set aside on one machine is new on another

- **WHEN** the person sets a question aside for later on one machine, then
  opens the answer session on another
- **THEN** the other machine shows it as new

### Requirement: One answer session runs on each machine

The answer session SHALL hold a lock, a file `lock` in the state folder
naming its session's id, name, start and whether it is a background
session; refresh it at least every 30 seconds, stale after 2 minutes
unrefreshed; and write it atomically, only when absent, stale or taken
over. A session SHALL open none while another holds a fresh lock, but
say which holds it and how to reach it, and offer a takeover. Before
each poll and post, the holder SHALL close if the lock names another.

#### Scenario: A second session is offered the choice

- **WHEN** a background session named `Answers` holds a fresh lock, and the
  person types `/answer` in another session
- **THEN** this session opens no answer session, says that the Claude Code
  background session `Answers` holds the lock, says how to reach it, and
  offers to take over

#### Scenario: Taking over stops the old holder

- **WHEN** the person takes over from another session's answer session
- **THEN** the new session replaces the lock and holds it, and the old
  session, finding before its next poll or post that the lock names
  another session, closes its answer session and polls and posts nothing
  more

#### Scenario: A live holder keeps its lock fresh

- **WHEN** the holder has been open, idle, for 10 minutes
- **THEN** its lock was refreshed within the last 30 seconds, and a
  second session that opens the answer session finds it not stale

#### Scenario: A crashed holder's lock goes stale

- **WHEN** the holder crashed, and its lock has gone 2 minutes
  unrefreshed
- **THEN** the next session to open the answer session takes the lock
  without asking

#### Scenario: A crash while writing the lock leaves a whole lock

- **WHEN** a session crashes while replacing a stale lock
- **THEN** the lock file holds either the old lock or the new one, whole

### Requirement: A discussion runs in the session's own conversation

Each discussion message SHALL go to the model as an ordinary prompt,
with the question attached as its first scenario details, the question,
its context and replies as quoted data, never instructions. The context
SHALL tell the model to explain and lay out trade-offs without choosing,
that it may read with tools, and to post and change nothing. A question
it asks back SHALL skip the four filters and vetting. Replies
stay in the conversation; the discussion record SHALL keep both.

#### Scenario: A discussion message carries its question

- **WHEN** the person sends a message while discussing a question from
  igor's pull request #216
- **THEN** the model receives the message with that question, where and
  by whom it was asked, its context, its options with what each would
  change, any related or possibly answering decision, any reply from the
  asker, and the context's three instructions: explain and lay out
  trade-offs without choosing; read with its tools, such as the
  question's thread, the code and the specs; and post and change nothing

#### Scenario: A thread's text reaches the model as quoted data

- **WHEN** the person discusses a question whose thread holds a reply
  telling the model to post a comment
- **THEN** the model receives that reply marked as quoted data, not as an
  instruction, and the context's instructions tell it to post nothing

#### Scenario: The model reads but does not write

- **WHEN** the model answers a discussion message about a pull request
- **THEN** the context's instructions let it read the pull request with
  `gh`, and tell it to post nothing and edit no file

#### Scenario: The model may ask back in its reply

- **WHEN** the model, in a discussion, needs to know which option the
  person leans to
- **THEN** it asks in its reply, without the picker, the four filters or
  vetting

#### Scenario: A discussion is kept with its question

- **WHEN** the person sends two messages about a question, and the model
  replies to each
- **THEN** the question's discussion record holds both messages and both
  replies

### Requirement: Claude's draft goes to the prompt box, never to a post

The answer session SHALL give the model `propose_reply`, a tool putting
a reply draft in the prompt box, for the question under discussion or
as an edited relay post's text; it SHALL post nothing and refuse
subagents. The context SHALL tell the model to call it when asked to
draft, at the question's privacy. For a filter 1 decline, the draft MAY
fill in only the record's URL, on the fixed post's `Recorded in: ` line
(design.md: *Claude drafts a reply only into the prompt box*).

#### Scenario: A draft lands in the prompt box

- **WHEN** the person asks Claude to draft their reply, and the model calls
  `propose_reply`
- **THEN** the draft is in the prompt box, nothing is posted, and the
  person can edit it; it is posted only when the person relays it, as
  any answer is

#### Scenario: A draft for an edit replaces the post's text

- **WHEN** the person, editing a relay post, asks Claude to draft the new
  text
- **THEN** the draft lands in the prompt box as the post's new text, which
  changes only when the person relays the edit

#### Scenario: The context asks for a draft at the question's privacy

- **WHEN** the person discusses a question asked in a public repository
- **THEN** the context tells the model to call `propose_reply` for a
  draft, written at that repository's privacy, by the inquisitor's rule
  *A question is written at the privacy of what it concerns*

#### Scenario: A subagent cannot call propose_reply

- **WHEN** a subagent of the session's model calls `propose_reply`
- **THEN** the tool refuses the call, and the prompt box is unchanged

#### Scenario: A draft fills the record's URL for a filter 1 decline

- **WHEN** the person, declining a question because the inquisitor should
  have handled it, picks filter 1 and asks Claude to find the record
- **THEN** Claude's `propose_reply` draft puts the record's URL in the
  prompt box as the place the person gives, and the answer session
  shows the recorded-answer post in its fixed form, with that URL on its
  `Recorded in: ` line, for the person to confirm

### Requirement: A rephrased question is answered with its rephrasing

When the person answers a question rephrased after a discussion, the
answer session SHALL post, once they confirm all of it:

```
User says: <the answer>

Rephrased question: <the question as rephrased>
Discussion: <the discussion in one sentence>
```

with its `Re: ` line on GitHub and Linear. The model drafts both added lines at the
question's privacy. The agent logging the answer SHALL record both in its
log file, as the inquisitor's *A log file and a miss file have one
format* states.

#### Scenario: A rephrased answer carries the rephrasing

- **WHEN** the person rephrases a question after a discussion, confirms the
  model's rephrasing and summary, and answers it
- **THEN** the relay post starts with `User says: ` and the answer, then
  gives the rephrased question and the one-sentence summary on their own
  lines, both drafted at the privacy of what the question concerns, by
  the inquisitor's rule *A question is written at the privacy of what it
  concerns*

#### Scenario: An unconfirmed rephrasing is not posted

- **WHEN** the model has drafted a rephrasing the person has not confirmed
- **THEN** the answer session posts nothing

#### Scenario: The asker logs the rephrasing

- **WHEN** an agent records the answer to its question from a relay post
  that gives a rephrased question
- **THEN** its log file holds the rephrased question under
  `## Rephrased question` and the summary under `## Discussion`

### Requirement: A questions-branch question is answered by a new log file

Besides handled files, the answer session SHALL write a log file only to
answer an unanswered questions-branch file's question: of the fourth
source, or shown from the thread its `asked_in` links, the answer then
also relayed there. It SHALL push the file to that branch by the `log`
command, naming the answered file in `answers`, copying its `asked_from`
as a miss does, passing any relay post's URL as `answer_link` unless
withheld, and offer the fourth source no ask-back or edit.

#### Scenario: A questions-branch question is answered by a new file

- **WHEN** the person answers a question of the fourth source
- **THEN** the `log` command pushes to that branch, in a commit
  `inquisitor: log <file>`, a new log file holding the question and the
  answer, under the inquisitor's *A file on a questions branch never
  changes once pushed* and *An organization's question is pushed to its
  lore repository's questions branch*, naming the earlier file in
  `answers` and copying any `asked_from` it has as a miss does; it posts
  nothing, and leaves the earlier file unchanged

#### Scenario: A questions-branch question asked in a post is answered in both places

- **WHEN** the person answers, from its GitHub thread, a question an
  unanswered log file on the lore repository's questions branch also
  holds
- **THEN** the relay posts the answer in the thread, starting
  `User says: `, and the script pushes to that branch a new log file
  holding the question and, as its answer, that relay post's text word
  for word, with the post's URL, passed to the `log` command, as its
  `answer_link`

#### Scenario: A late answer on another machine answers a closed file

- **WHEN** the person declined with nothing to answer, on one machine, a
  thread copy a questions-branch file holds, then answers that thread
  copy on another machine
- **THEN** the answer is relayed in the thread, and a log file naming the
  closed file in `answers` is pushed

#### Scenario: A Linear link is left out of a lore repository that is not private

- **WHEN** the person answers, from its Linear thread, a question an
  unanswered log file on an internal lore repository's questions branch
  also holds
- **THEN** the script pushes a new log file holding the relayed answer
  with no `answer_link`, which the `log` command withholds, as the
  inquisitor's *The log command withholds a link where it would leak*
  says (design.md: *`answer_link` and `asked_in` are withheld where they
  would leak*)

#### Scenario: A questions-branch question offers no ask-back or edit

- **WHEN** a question of the fourth source is on screen
- **THEN** the answer session offers no question to the asker, and, once it
  is answered, no edit

### Requirement: A questions-branch answer file records the answer as given

The answer file SHALL hold the question the person saw; the `authority`
the inquisitor's spec sets for an answer given in the session, on any
surface; and, as quote lines, the relay post's text word for word, or the
confirmed answer if unrelayed, with any rephrasing and summary also in
their own sections. The `log` command SHALL read a GitHub relay post
itself. For Linear or Discord the answer session SHALL pass it the text
sent to the relay's skill, and the command fetches nothing.

#### Scenario: An answer records the question the person saw

- **WHEN** a log file's `asked_in` links a GitHub message whose question
  differs from the file's own, and the person answers the message
- **THEN** the new log file holds the message's question, not the
  file's, and the answer, and names the earlier file in `answers`
  (design.md: *An answer file records the question the person saw*)

#### Scenario: An unrelayed answer is logged as the person confirmed it

- **WHEN** the person answers a fourth-source question in the answer
  session
- **THEN** the new log file's answer is the confirmed answer, word for
  word, as quote lines (design.md: *A logged answer is the person's own
  words*)

#### Scenario: A GitHub relay's answer is read from the comment

- **WHEN** the person answers, rephrased, from its GitHub thread, a
  question that a questions-branch file holds
- **THEN** the `log` command reads the answer from the relay comment's
  own text, as the inquisitor's *An answer logged from a comment is the
  comment's whole text* requires, and the file's answer holds the post's
  `Rephrased question: ` and `Discussion: ` lines, also held in its
  `## Rephrased question` and `## Discussion` sections
  (design.md: *A rephrased answer carries its rephrasing, and the asker
  logs it*)

#### Scenario: A questions-branch answer relayed on Linear keeps its link unfetched

- **WHEN** the person answers, from its Linear thread, a question an
  unanswered log file on a private lore repository's questions branch
  holds
- **THEN** the `log` command gets the text sent to the relay's skill,
  `User says: ` included, and pushes a new log file whose answer is that
  text word for word, as quote lines, and whose `answer_link`, that
  Linear comment's URL, nothing fetches (design.md: *Questions-branch
  answers relayed on Linear or Discord*)
- **AND** the file counts only through its commit's signature

#### Scenario: A signed log file of a Discord-relayed answer is a decision

- **WHEN** the person answers a question a private lore repository's
  questions branch holds, the session relays it on Discord, GitHub
  verifies a signature for `answered_by` on the commit adding the log
  file, which no later commit changed, and `answered_by` has write
  access to what the question concerns
- **THEN** the file's answer is the text sent to discord-bot, before any
  mention is rewritten; its `authority` is what the inquisitor's *An
  answer is a decision only from a proven writer with write access* sets
  for a session answer; filter 1 counts it a decision only through that
  signature, by the inquisitor's *A link off GitHub proves no writer,
  but a relayed answer's signature can*; and its Discord `answer_link`
  proves nothing

#### Scenario: An unsigned log file of a Discord-relayed answer is input

- **WHEN** the same answer is logged by a commit that carries no
  signature GitHub verifies
- **THEN** filter 1 shows the file as input, with the label the
  inquisitor's *A questions-branch file's writer is proven by its comment
  or its signature* gives a `decision` file whose writer is not proven,
  unconfirmed

### Requirement: A handled file closes a questions-branch question

Whenever the answer session closes a question, by declining it or
posting a recorded answer or an `Inquisitor: ` reply, it SHALL push,
only through the `log` command's handled option, one **handled file**
naming each unanswered questions-branch log file that holds the question
and that no handled file names. A file holds it when shown from that
file or when its `asked_in` links the closed message. A handled file
closes only the file it names, on every machine, and answers nothing.

#### Scenario: An automatic Inquisitor reply pushes a handled file

- **WHEN** the answer session posts filter 4's `Inquisitor: ` reply by
  itself on a question, in a GitHub thread, that an unanswered
  questions-branch log file also holds
- **THEN** it pushes, through the `log` command's handled option, a
  handled file naming that log file, in the format of the inquisitor's
  *A log file and a miss file have one format*
- **AND** it does the same for a `Recorded answer: ` post and for any
  decline, agreeing included, with a thread or without, being the only
  writer of handled files under the inquisitor's *Only an answer session
  writes a handled file*

#### Scenario: A handled file closes a questions-branch question

- **WHEN** a lore repository's questions branch holds an unanswered log
  file tagging the person and a handled file naming it
- **THEN** neither file is shown as a question, on any machine

#### Scenario: A handled file closes only the file it names

- **WHEN** a handled file names one questions-branch file, and another
  questions-branch file, or a thread, holds the same words
- **THEN** the other file and the thread copy are still shown, and the
  handled file answers neither the file it names nor any searching
  agent's question (design.md: *The answer session writes a handled file
  on every close of a questions-branch file*; *Closing works by exact
  identity, never by matching*)

#### Scenario: Two questions-branch files get two handled files

- **WHEN** the person declines a question that two unanswered
  questions-branch files hold
- **THEN** the answer session pushes two handled files, each naming one
  of them

#### Scenario: A thread copy declined with nothing posted shows again elsewhere

- **WHEN** the person declines with nothing to answer, on one machine, a
  question in a GitHub thread a questions-branch file also holds
- **THEN** a handled file closes the questions-branch file on every
  machine, the thread copy closes on that machine only, and another
  machine shows the thread copy, for the person to decline again

### Requirement: A handled file is pushed once its close takes effect

The answer session SHALL push a handled file once its close takes
effect: once the post leading to it has gone out, or, with nothing
posted, once the person confirms the decline. It SHALL record the owed
push in the state folder before the post, drop the record when the post
never went out, and retry a failed push at each poll and each opening
until it succeeds.

#### Scenario: A failed post pushes no handled file

- **WHEN** the person declines under the second reason a question in a
  GitHub thread a questions-branch file also holds, and the post fails
- **THEN** no handled file is pushed

#### Scenario: A failed handled-file push is retried

- **WHEN** the person confirms a decline with nothing posted, and the
  handled file's push fails
- **THEN** the owed push stays recorded in the state folder, retried at
  each poll and each opening until it succeeds

### Requirement: A miss or citation file's push is owed and retried as a handled file's is

The answer session SHALL record each miss or citation file it pushes as
an owed push in the state folder before the post leading to it, or, with
nothing posted, before the push. It SHALL drop the record when that post
never went out, and retry a failed push at each poll and each opening
until it succeeds, as *A handled file is pushed once its close takes
effect* says of a handled file.

#### Scenario: A miss owed when the session stopped is pushed at the next opening

- **WHEN** the person declines an agent's GitHub question under the
  second reason, picks filter 2 and confirms the post, and the answer
  session stops after the post goes out but before pushing the miss file
- **THEN** at its next opening it pushes the miss file it recorded as
  owed

#### Scenario: A failed citation push is retried

- **WHEN** the answer session posts by itself a recorded answer whose
  record is an `active` lore entry, and the push of the citation file
  fails
- **THEN** the owed push stays recorded in the state folder, retried at
  each poll and each opening until it succeeds

### Requirement: Four reserved prefixes mark the answer session's posts

The answer session SHALL start a post with `User says: ` or
`User asks: ` only once the person confirms all of it, and
`Recorded answer: ` or `Inquisitor: ` only as the rules for filters 1
to 4 and for declining say. A relay identity may post for other work,
but no other post SHALL use a reserved prefix, as the skill's instructions
SHALL say; only the inquisitor's GitHub post hook blocks one. An
automatic post SHALL be posted like a relay post, and never shown as
the person's words.

#### Scenario: The instructions reserve the prefixes

- **WHEN** an agent reads the skill's instructions on relay identities
- **THEN** they say a relay identity may post for other work, but only
  the answer session's posts start with `User says: `, `User asks: `,
  `Recorded answer: ` or `Inquisitor: `

#### Scenario: A relay identity's other post sets no state

- **WHEN** the GitHub relay identity, used by an agent for other work,
  comments in a question's thread with no reserved prefix
- **THEN** that comment is no relay post, and the question's state is
  unchanged

#### Scenario: A reserved prefix outside the answer session is checked only on GitHub

- **WHEN** an agent's post outside the answer session starts with a
  reserved prefix
- **THEN** on GitHub the inquisitor's post hook blocks it, as the
  inquisitor's *The post hook vets what the shared post reader returns*
  says, and on Linear or Discord nothing checks it

#### Scenario: Automatic posts come only from the filters and the decline

- **WHEN** the answer session makes a `Recorded answer: ` or
  `Inquisitor: ` post
- **THEN** it makes it only as *Filter 1 posts a recorded answer by
  itself in the question's thread*, *Filters 2 to 4 judge every incoming
  question* or *Declining for the inquisitor posts the picked filter's
  reply* says

#### Scenario: An automatic post is posted as a relay post is

- **WHEN** the answer session makes an automatic post
- **THEN** it posts it as a relay post is posted under *An answer is
  relayed as the person's words* and *A relay post is posted by a host
  command, unvetted*: through the relay identity's skill run as a host
  command with no shell, naming the question as a relay post does,
  keeping the post's id in the state folder, scanned first for the
  credential patterns, with neither prose's pass nor the inquisitor's
  filters applied

#### Scenario: An automatic post is never shown as the person's words

- **WHEN** the answer session lists a question it answered for the person
- **THEN** it shows the post as made by the answer session, not as the
  person's answer

#### Scenario: Nothing starting with User says is posted unconfirmed

- **WHEN** the session's model has drafted a reply the person has not
  confirmed
- **THEN** nothing starting with `User says: ` is posted

### Requirement: The person can decline to answer

On any open question, the person SHALL be able to decline to answer,
giving one of two reasons (design.md: *Two reasons to decline*):

1. **Nothing to answer:** the conversation is over, or it isn't a
   question. Nothing is posted, no miss logged, and only this question
   closes (design.md: *Declining with nothing to answer closes
   only that question*; *Misses the answer session logs*).
2. **The inquisitor should have handled it.**

#### Scenario: Declining with nothing to answer posts nothing

- **WHEN** the person declines a GitHub question under the first reason,
  nothing to answer
- **THEN** nothing is posted in its thread, and the question leaves the
  queue

#### Scenario: A follow-up after a closed conversation is a new question

- **WHEN** the person declines, as the conversation is over, a question
  in a GitHub issue's conversation where the relay had posted before it,
  and the asker then comments again there without an @-mention
- **THEN** the comment is shown on every machine as a new question, as
  *Later messages after an answer or a decline are new questions* says,
  and the declined question stays closed

#### Scenario: A reply to a relay post after a closed conversation is a new question

- **WHEN** the person declined a question as the conversation is over,
  and the asker then replies on Discord to an earlier relay post in that
  thread, without an @-mention
- **THEN** the reply is shown as a new question, and the declined
  question stays closed

#### Scenario: A reply after a decline is a new question

- **WHEN** the person declined, as nothing to answer, a message in a
  GitHub thread, and the asker then replies in a review thread to an
  earlier relay post there
- **THEN** the declined question is not reopened, and the reply is shown
  on its own as a new question

#### Scenario: A mention after a closed conversation is a question

- **WHEN** the person declined a question as the conversation is over,
  and someone later writes in that thread a message @-mentioning the
  person
- **THEN** that message is shown as a question

#### Scenario: A message picked up by mistake logs no miss

- **WHEN** the answer session showed, under the second source, a reply
  to the relay that was in fact meant for someone else, and the person
  declines it under the first reason, nothing to answer
- **THEN** the question closes, nothing is posted, and no miss file is
  logged

### Requirement: Declining for the inquisitor posts the picked filter's reply

Under the second reason, on a person's question as on an agent's, the
person SHALL pick the filter that should have stopped the question: 1,
already answered; 2, can wait; 3, one option has merit; or 4, cheap to
reverse. The answer session SHALL show them the exact post of that
filter's reply, and post it, naming the question, only once they confirm
it.

#### Scenario: The inquisitor's reply is posted once the person confirms it

- **WHEN** the person declines an agent's GitHub question as one the
  inquisitor should have handled, picks filter 4, and types the note "a
  config flag, easy to flip"
- **THEN** the answer session shows, as it will be posted, the filter 4
  `Inquisitor: ` text followed by the line `The person chose this
  filter.`, posts it naming the question only once the person confirms
  it, and logs a miss file whose `filter` is `"4"` and whose `said` is
  that note

#### Scenario: A person's question can be answered for the inquisitor

- **WHEN** the person declines a person's question on Linear as one the
  inquisitor should have handled, and picks filter 2
- **THEN** once the person confirms it, the Linear relay posts the filter
  2 `Inquisitor: ` text in the question's comment thread

### Requirement: A filter 2 to 4 reply the person chose says they chose it

The person's post for filter 2, 3 or 4 SHALL be its fixed `Inquisitor: `
text from *Filters 2 to 4 judge every incoming question* plus the line
`The person chose this filter.`, which no post the answer session makes
by itself holds (design.md: *A post the person chose says
so*).

#### Scenario: The person's filter 3 reply ends with the chosen line

- **WHEN** the person declines an agent's GitHub question as one the
  inquisitor should have handled, picks filter 3, and confirms the post
- **THEN** the relay posts filter 3's fixed `Inquisitor: ` text, then the
  line `The person chose this filter.`

### Requirement: The person's filter 1 reply links the record they chose

The person's post for filter 1 SHALL be a recorded answer in the form
*Filter 1 posts a recorded answer by itself in the question's thread*
gives, its `Recorded in: ` line holding the URL of the place the person
gave, or of one filter 1 found that they chose.

#### Scenario: A filter 1 reply names the place the person gave

- **WHEN** the person declines a question in a public repository as one
  the inquisitor should have handled, picks filter 1, and gives that
  repository's `docs/retries.md` as where it is decided
- **THEN** once they confirm it, the relay posts a reply starting
  `Recorded answer: ` whose `Recorded in: ` line holds that file's URL,
  and a miss file with `filter` `"1"` is logged

### Requirement: The preview warns when a filter 1 record is more private than the thread

Before the person confirms a filter 1 reply, the answer session shows them
a preview of the post. When the reply's record is more private than the
thread, by the rule of *A recorded answer is posted by itself only when no
more private than its thread*, that preview SHALL also warn that posting
the reply shows the record exists, and one confirmation SHALL cover both
the warning and the post (design.md: *Agreeing to a recorded answer is a
filter 1 decline*).

#### Scenario: A filter 1 reply with a more private record is posted only after a warning

- **WHEN** the person picks filter 1 for a question in a public
  repository, and the place it is decided is a private repository's
  `DECISIONS.md`
- **THEN** the person is shown that posting the reply shows the record
  exists, and the reply is posted only once they confirm

### Requirement: A decline with no thread or with a category posts nothing

On a question with no thread, a decline under the second reason SHALL
post nothing for any filter, SHALL show the person, for filter 1, its
recorded answer, and SHALL close the question. On a question with a
category, it SHALL post nothing and close the question.

#### Scenario: A filter 1 reply to a question with no thread is shown, not posted

- **WHEN** the person picks filter 1 for a fourth-source question, giving
  a decision document as where it is decided
- **THEN** nothing is posted, the person is shown the recorded answer,
  the question closes, and a miss against filter 1 is logged

#### Scenario: A decline on a question with a category posts nothing

- **WHEN** the person declines under the second reason, with filter 2, a
  question in a GitHub thread that the session's model judges has a
  category
- **THEN** nothing is posted in the thread, and the question closes

### Requirement: Filter 3 also offers that the agent shouldn't have asked

Under the second reason, filter 3 SHALL also offer "the agent shouldn't
have asked", for a message the asking agent should not have written; it
posts nothing (design.md: *Messages that are not questions are
ignored*).

#### Scenario: The agent shouldn't have asked posts nothing

- **WHEN** the person declines an agent's statement in a GitHub thread
  under the second reason, choosing filter 3's "the agent shouldn't have
  asked"
- **THEN** the answer session posts nothing in the thread

### Requirement: A decline for the inquisitor logs a miss once it takes effect

Under the second reason, the answer session SHALL log a miss against the
picked filter, at the privacy of what the question concerns, whose
`said` is the person's note, or `the inquisitor should have handled it`
without one. It SHALL push the miss only once its post has gone out or,
with nothing posted, once the person confirmed the decline, recording it
as owed first, as *A miss or citation file's push is owed and retried as
a handled file's is* says.

#### Scenario: A decline with no note logs the default said after its post

- **WHEN** the person declines an agent's GitHub question under the
  second reason, picks filter 2, types no note, and confirms the post
- **THEN** only once the post has gone out is a miss file pushed whose
  `filter` is `"2"` and whose `said` is
  `the inquisitor should have handled it`

### Requirement: A filter 1 decline cites its lore entry once

A filter 1 decline naming a lore entry SHALL push its citation file
once, to the entry's own lore repository, under *A person's cite of an
active entry in scope pushes a citation file*, whether or not it pushes
a miss (design.md: *A person's cite pushes a citation file*).

#### Scenario: A decline's citation is pushed when its miss is not

- **WHEN** the person declines, with filter 1, a question about a private
  repository whose team's lore repository is public, naming an `active`
  entry of a private lore repository whose scope covers the question
- **THEN** no miss file is written, and the answer session pushes one
  citation file, to that entry's lore repository

### Requirement: A decline with nothing posted closes a thread copy on this machine only

A question declined with nothing posted SHALL be recorded in the state
folder, closing a thread copy on this machine only; a questions-branch
file its handled file names closes everywhere (design.md: *Closing works
by exact identity, never by matching*). One declined with a post SHALL
take its state from its thread.

#### Scenario: A decline with nothing posted is kept in the state folder

- **WHEN** the person declines a thread copy with nothing to answer, on
  one machine
- **THEN** the decline is recorded in that machine's state folder, and
  that machine neither queues the question nor shows it as new

### Requirement: Only a thread copy declined with nothing posted is reopened

The person SHALL be able to reopen, on the machine where they declined
it, a thread copy declined with nothing posted, which puts it back in
their queue, and SHALL NOT be offered any other declined question to
reopen; one declined with a post is changed by editing that post
(design.md: *Reopening a declined question*). A miss logged at the
decline SHALL stay when the question is reopened.

#### Scenario: A question declined with a post is not reopened

- **WHEN** the person declined a question under the second reason, and
  the answer session posted that filter's reply
- **THEN** no way to reopen the question is offered, and the person can
  change the handling only by editing that post, as *A relay post can be
  edited where it was posted* says

#### Scenario: A thread copy declined with nothing posted is reopened on its machine

- **WHEN** the person declined a thread copy with nothing to answer and
  nothing posted, then reopens it on the same machine
- **THEN** it is back in the queue on that machine

#### Scenario: A reopened decline keeps its miss

- **WHEN** the person declines an agent's thread copy under the second
  reason, choosing filter 3's "the agent shouldn't have asked", so that
  nothing is posted and a miss is pushed, then reopens it on the same
  machine
- **THEN** the question is back in the queue, and the miss file stays on
  the questions branch

#### Scenario: A declined questions-branch file is not offered for reopening

- **WHEN** the person declined, as the conversation is over, a question
  from a lore repository's questions branch
- **THEN** the answer session pushed a handled file naming that file,
  which closes it everywhere, and offers no way to reopen it

### Requirement: Filter 1 runs on every incoming question

Before the answer session shows a question, whether a person or an agent
asked it, it SHALL run filter 1 on it through the inquisitor script's
search, with the person's credentials, as the inquisitor's *Filter 1
searches every place an answer is recorded* and *Only an answer with
authority stops a question* say. The session's model judges whether a
hit with authority answers the question; a hit that is only input is
shown with the question, and stops nothing.

#### Scenario: Input does not answer by itself

- **WHEN** a question's only hit is a log file with `authority: input`
- **THEN** nothing is posted by itself, and the question is shown with
  that hit labelled as input

### Requirement: A question with a category reaches filter 1 on standard input

The session's model SHALL first judge whether the question has a
category, as the inquisitor's *Some questions are recorded by hash only*
defines one. The answer session SHALL pass a question with a category to
the script on standard input, which searches nothing off the machine,
as that requirement says, and SHALL post nothing by itself on it; it
SHALL pass any other question in a file as the inquisitor's *The two
calls' files and records stay private* keeps the two calls' files.

#### Scenario: A question with a category is searched on the machine only

- **WHEN** a Discord message that holds a password reaches the answer
  session
- **THEN** it is passed to the script on standard input, the search
  reaches no source off the machine, and nothing is posted by itself

### Requirement: Filter 1 posts a recorded answer by itself in the question's thread

When an answer with authority is recorded and the question has a
thread, the answer session SHALL answer by itself, whoever asked, a
relayed question included, posting through the relay

```
Recorded answer: see the record below.
Recorded in: <the URL of where the answer is recorded>
```

followed by its `Re: ` line on GitHub and Linear. Before each automatic post it
reads the thread again, as *The thread is read again before a question
is shown and before a post* says.

#### Scenario: A relayed question gets a recorded answer by itself

- **WHEN** a GitHub comment starting `User asks: ` from the relay App of
  Maya, another person, tags the person, and the repository's
  `DECISIONS.md` on its default branch decides it
- **THEN** the relay posts, naming the question, a reply that starts with
  `Recorded answer: `, the question is listed as answered for the person,
  and no miss is logged

#### Scenario: A reply since the question stops an automatic post

- **WHEN** the answer session is about to post a recorded answer, and the
  thread has a new reply since the question
- **THEN** it posts nothing, and shows the question and the reply to the
  person

### Requirement: A recorded answer posted by itself links filter 1's hit and quotes no answer

In a recorded answer the answer session posts by itself, the URL SHALL
be that of filter 1's hit. Whatever the record is, a log file included,
the post SHALL quote no answer, and the session's model SHALL write none
of it (design.md: *What the answer session posts by itself*).

#### Scenario: A recorded answer is posted by itself

- **WHEN** an agent's question in a public repository asks whether retries
  back off, and that repository's `DECISIONS.md` on its default branch
  decides it
- **THEN** the relay posts, naming the question, a reply starting
  `Recorded answer: see the record below.` with a `Recorded in: ` line
  holding that file's URL and no answer quoted; the question is listed
  as answered for the person; and a miss against filter 1 whose `said`
  is `answer session: clearly filter 1` is logged

### Requirement: A recorded answer is posted by itself only when no more private than its thread

The answer session SHALL post a recorded answer by itself only when the
record is no more private than the question's thread: on GitHub, when
the record's repository is no more visible than the thread's; on Linear
and Discord, only when the record's repository is public. A log or miss
file's own visibility, as the inquisitor's *A log or miss file is as
private as its more private repository* defines it, stands in for its
repository's.

#### Scenario: A more private record is shown, not posted

- **WHEN** a question in a public repository is answered by a decision
  document in a private repository
- **THEN** nothing is posted by itself, and the person is shown the
  question with the recorded answer beside it

### Requirement: A recorded answer not posted by itself is shown beside its question

When filter 1 finds an answer with authority that the answer session
does not post by itself, and for a question from a questions branch, the
answer session SHALL show the recorded answer beside the question, and
post only what the person relays or confirms.

#### Scenario: A questions-branch question's recorded answer is shown, not posted

- **WHEN** a fourth-source question is answered by a decision document in
  a public repository
- **THEN** nothing is posted by itself, and the recorded answer is shown
  beside the question

### Requirement: Agreeing to a shown recorded answer is a filter 1 decline

The person may agree to a recorded answer shown beside a question: a
decline under the second reason of *The person can decline to answer*
with filter 1, naming that record, which the answer session SHALL handle
exactly as *Declining for the inquisitor posts the picked filter's
reply* and the requirements after it say (design.md: *Agreeing to a
recorded answer is a filter 1 decline*). Agreeing takes no note, so its
miss's `said` is `the inquisitor should have handled it`.

#### Scenario: Agreeing to a more private record posts it after a warning

- **WHEN** the person agrees to the recorded answer shown for a question
  in a public repository, a decision document in a private repository
- **THEN** the person is shown that posting it shows the record exists,
  and once they confirm, the relay posts
  `Recorded answer: see the record below.` with `Recorded in: ` and the
  record's URL

#### Scenario: Agreeing on a question with no thread is a filter 1 decline

- **WHEN** a fourth-source question, which has no thread, is answered by
  a decision document, and the person agrees to the shown recorded
  answer
- **THEN** nothing is posted, a handled file naming the questions-branch
  file is pushed, closing it on every machine for good, and a miss
  against filter 1 is logged with
  `said: "the inquisitor should have handled it"`

#### Scenario: Agreeing in a thread on a questions-branch question pushes only a handled file

- **WHEN** a question an unanswered log file on the lore repository's
  questions branch also holds is shown from its GitHub thread, beside a
  recorded answer more private than the thread, and the person agrees
  and confirms after the warning
- **THEN** the relay posts the recorded answer in the thread, and the
  answer session pushes to the questions branch a handled file naming
  that log file and no answer file, besides the decline's miss

#### Scenario: Agreeing logs a miss on any question

- **WHEN** the person agrees to the recorded answer shown beside a
  question, asked by a person or an agent, in a private repository's
  GitHub thread whose lore repository is private
- **THEN** a miss against filter 1 is logged with
  `said: "the inquisitor should have handled it"`

### Requirement: A lore entry posted as a recorded answer gets a citation file

When the answer session posts a recorded answer by itself and the record
is a lore entry, it SHALL push a citation file, as the inquisitor's *A
lore entry that stops a question gets a citation file* says.

#### Scenario: A lore entry's recorded answer sends a citation

- **WHEN** an active lore entry answers an incoming question with a thread
- **THEN** the relay posts the recorded answer, and the script pushes a
  citation file to the entry's lore repository's questions branch

### Requirement: A person cites a lore entry by naming it as an answer or a record

The answer session SHALL count a person as one who **cites** a lore
entry when they name it as the answer to a question, or as the record
when declining one under the second reason with filter 1, agreeing
included. A cite SHALL push a citation file under *A person's cite of an
active entry in scope pushes a citation file*.

#### Scenario: Declining with filter 1 and a lore entry cites it

- **WHEN** the person declines under the second reason, with filter 1, a
  question with no category in a private repository's GitHub thread,
  naming as the record an `active` entry, in a private lore repository,
  whose scope covers the question
- **THEN** the relay posts in the thread the `Recorded answer: ` reply
  whose `Recorded in: ` line names that entry, and a citation file for
  it is pushed

#### Scenario: A filter-1 decline with no thread still cites its entry

- **WHEN** the person declines under the second reason, with filter 1, a
  question with no thread from a private lore repository's questions
  branch, naming as the record an `active` entry of that lore repository
  whose scope covers the question
- **THEN** nothing is posted, the recorded answer is shown beside the
  question as *A decline with no thread or with a category posts
  nothing* has it, and a citation file for that entry is pushed

#### Scenario: Agreeing to a lore entry's recorded answer cites it

- **WHEN** the person agrees to a shown recorded answer whose record, an
  `active` entry of a private lore repository, has a scope covering a
  question about a private repository
- **THEN** a citation file for that entry is pushed to its lore
  repository

### Requirement: A person's cite of an active entry in scope pushes a citation file

The answer session SHALL push a citation file for a cited entry, by the
inquisitor's *A lore entry that stops a question gets a citation file*,
which pushes none to a more visible lore repository, only when the entry is `active` and in scope for
the question, as the inquisitor's *Filter 1 hides every lore entry
outside the question's scope* defines scope; citing any other entry
pushes nothing (design.md: *A person's cite pushes a citation file*).

#### Scenario: Citing a lore entry sends a citation

- **WHEN** the person answers a question about a private repository by
  citing an active entry in a private lore repository
- **THEN** a citation file for that entry is pushed to that lore
  repository's questions branch

#### Scenario: Citing an entry that is not active sends none

- **WHEN** the person answers a question by citing a lore entry whose
  status is not `active`
- **THEN** no citation file is pushed

#### Scenario: Citing an entry out of scope sends none

- **WHEN** the person answers a question by citing an `active` entry whose
  scope does not cover it
- **THEN** no citation file is pushed

#### Scenario: Citing an entry in a more visible lore repository sends none

- **WHEN** the person cites an entry in a public lore repository to answer
  a question about a private repository
- **THEN** no citation file is pushed

#### Scenario: Agreeing to an inactive lore entry's recorded answer cites nothing

- **WHEN** the person agrees to a shown recorded answer whose record is a
  lore entry not `active`
- **THEN** no citation file is pushed

### Requirement: Filter 1's answer by itself to an agent's question logs a miss

When the answer session answers an agent's question by itself under
filter 1, it SHALL log a miss against filter 1, as *The answer session
logs its misses on the team's lore repository's questions branch* says;
a person's question it answers by itself logs none.

#### Scenario: A person's question is answered by itself too

- **WHEN** a person's Linear question is answered by a decision document
  in a public repository
- **THEN** the Linear relay posts the recorded answer in its comment
  thread, starting with `Recorded answer: `, never `User says: `, and no
  miss is logged

#### Scenario: An agent's question answered by itself logs a miss

- **WHEN** the answer session answers an agent's GitHub question by
  itself under filter 1
- **THEN** it logs a miss against filter 1 whose `said` is
  `answer session: clearly filter 1`

### Requirement: A reply to an automatic post is a new question

The answer session SHALL judge a reply to an automatic post as a
question, by filters 1 to 4 again, and may answer it by itself again. A
question's **chain of replies** is the question, the relay post it
replies to, the question that relay post names (on GitHub and Linear, by its `Re: `
line), and so on back to a question that replies to no relay post.

#### Scenario: A reply to an automatic post is judged again

- **WHEN** an agent replies to a relay post holding filter 4's fixed
  `Inquisitor: ` text with a new question the repository's
  `DECISIONS.md` on its default branch decides
- **THEN** the relay posts, naming the reply, a recorded answer starting
  with `Recorded answer: `

### Requirement: No automatic post repeats one in its chain of replies

The answer session SHALL NOT make by itself an automatic post whose
text, apart from its `Re: ` line, is the same as that of any automatic
post already made in the chain of replies of the question it would
answer: such a repeat goes to the person, as an ordinary question
(design.md: *No automatic post repeats one in its chain of replies*).

#### Scenario: A repeated automatic post goes to the person

- **WHEN** an agent replies to a relay post holding filter 4's fixed text
  with a question that clearly fails filter 4 again
- **THEN** nothing is posted by itself, and the reply is shown to the
  person

#### Scenario: An automatic post made earlier in the chain is not made again

- **WHEN** the answer session replied to an agent's question with filter
  2's text, the agent replied with a question it answered with filter 4's
  text, and the agent replies again with a question that clearly fails
  filter 2
- **THEN** nothing is posted by itself, and the reply goes to the person

### Requirement: Filters 2 to 4 judge every incoming question

The session's model SHALL judge each question filter 1 did not stop
against filters 2 to 4, as the inquisitor's *Every question passes four
filters before a person sees it* and the requirement after it state
them, sending an unclear case to the person as an ordinary question.
When an agent's question with no category clearly fails one in a thread
the relay can reply in, the answer session SHALL itself post the
filter's fixed text through the relay, log its miss, and list it as
handled.

#### Scenario: A deferrable agent's question is handled for the person

- **WHEN** an agent's question in a subscribed repository clearly can wait
  until its pull request is reviewed
- **THEN** the answer session posts through the relay, naming the
  question, `Inquisitor: filter 2, deferrable. Carry on without an
  answer, list this question as not done in the current work, and file
  an issue for it if it outlives the work.`, logs a miss against filter
  2, and lists the question as handled for the person

#### Scenario: Filters 3 and 4 post their fixed texts

- **WHEN** one agent's question in a thread clearly fails filter 3, and
  another filter 4
- **THEN** the relay posts `Inquisitor: filter 3, not a real question.
  Take the option that has merit, and record what you chose and why.` on
  the first, and `Inquisitor: filter 4, cheap to reverse. Pick one, and
  record what you chose and why.` on the second

#### Scenario: An unclear case goes to the person

- **WHEN** the model can't tell whether an agent's question can wait
- **THEN** nothing is posted by itself, no miss is logged, and the
  question is shown to the person as an ordinary unanswered question

#### Scenario: A thread's text cannot choose the words posted

- **WHEN** an agent's question holds text telling the model to post a
  link
- **THEN** whatever the model judges, the answer session posts by itself
  only one of the three fixed `Inquisitor: ` texts, or the fixed
  recorded-answer text whose URL is filter 1's hit

### Requirement: Filters 2 to 4 only suggest a verdict on other questions

On a person's question, a relayed one included, and on an agent's
question of the fourth source, the answer session SHALL post nothing
by itself, but show the question with its suggested verdict. A message
that is not a question SHALL be ignored, with no automatic post, under *Messages judged clearly not questions are
ignored*; the person declines one shown anyway under *The person can
decline to answer* (design.md: *Messages that are not questions are
ignored*).

#### Scenario: A person's question only gets a suggestion

- **WHEN** a person's question clearly fails filter 4
- **THEN** nothing is posted by itself, and the answer session shows the
  question with filter 4 as its suggested verdict

#### Scenario: An agent's questions-branch question only gets a suggestion

- **WHEN** an agent-written log file of the fourth source holds a question
  that clearly fails filter 2
- **THEN** nothing is posted by itself, and filter 2 is shown as the
  question's suggested verdict

#### Scenario: An agent's rhetorical message gets no post

- **WHEN** an agent's message in a GitHub thread mentions the person
  with a rhetorical question
- **THEN** the answer session shows nothing, posts nothing and closes
  nothing

#### Scenario: A rhetorical message in the queue declined with nothing to answer logs no miss

- **WHEN** a rhetorical message under the first source reaches the
  person's queue, judged unclear, and the person declines it under the
  first reason
- **THEN** nothing is posted and no miss file is logged

#### Scenario: A non-question declined under reason 2 posts nothing

- **WHEN** the person declines an agent's message in a GitHub thread
  under the second reason, choosing filter 3's "the agent shouldn't have
  asked"
- **THEN** nothing is posted in the thread, and a filter 3 miss against
  the asking agent is logged

### Requirement: The answer session logs its misses on the team's lore repository's questions branch

The answer session SHALL log each miss, whether or not the asker logged
the question, as a miss file in the inquisitor's *A log file and a
miss file have one format*, which the inquisitor script SHALL
push, duplicates included, to the questions branch of the team's lore
repository serving the repository the question concerns, as that spec's
*An organization's question is pushed to its lore repository's questions
branch* says.

#### Scenario: A miss goes to the questions branch

- **WHEN** the answer session logs a miss for a question about `o/api`,
  which a configured lore repository serves
- **THEN** the script pushes the miss file to `misses/` on that lore
  repository's questions branch, and opens no pull request

#### Scenario: A miss judged on two machines is pushed twice

- **WHEN** the answer session on a second machine logs a miss whose
  question and filter match a miss file already on the branch
- **THEN** it pushes its miss file too

### Requirement: A miss records who judged it and copies its file's asked_from

An automatic miss, by *Filter 1's answer by itself to an agent's
question logs a miss* or *Filters 2 to 4 judge every incoming question*,
SHALL say `answer session: clearly filter <n>` in `said`. A miss on
questions-branch files SHALL copy their most private `asked_from`, by
the inquisitor's *Nothing about a repository goes somewhere more
visible*, through the `log` command with its other keys; a file with no
`asked_from` adds none (design.md: *Misses the answer session logs*).

#### Scenario: An automatic miss is marked as the answer session's

- **WHEN** the answer session handles an agent's question under filter 2
  by itself
- **THEN** the miss file's `said` is `answer session: clearly filter 2`

#### Scenario: A miss copies the questions-branch file's asked_from

- **WHEN** a questions-branch file holding `asked_from: "o/private-item"`
  holds a question, and the person declines it as one the inquisitor
  should have handled, picking filter 4
- **THEN** the answer session passes that `asked_from` to the `log`
  command with the miss's other keys, and the miss file it pushes holds
  `asked_from: "o/private-item"`

#### Scenario: A miss copies the most private asked_from

- **WHEN** three questions-branch files hold a question, with
  `asked_from: "o/public-item"`, a public repository,
  `asked_from: "o/private-item"`, a private one, and none, and the
  person declines it as one the inquisitor should have handled, picking
  filter 4
- **THEN** the miss file pushed holds `asked_from: "o/private-item"`, and
  the file with no `asked_from` adds none

### Requirement: The answer session writes no miss it cannot place privately

The answer session SHALL write no miss file, telling the person why,
when the question has a category, as the model judges by the
inquisitor's *Some questions are recorded by hash only*; concerns no
repository; has no configured lore repository serving its repository; or
that lore repository is more visible than its repository, than its
thread (on GitHub, as visible as its repository), or, with no thread, than its
questions-branch file (design.md: *Misses the answer session logs*).

#### Scenario: No lore repository means no miss file

- **WHEN** the answer session would log a miss for a question about a
  repository no configured lore repository serves
- **THEN** no miss file is written, the person is told why, and the
  question still closes

#### Scenario: A question about no repository gets no miss

- **WHEN** the person declines, as one the inquisitor should have
  handled, a Discord message that concerns no repository
- **THEN** the question closes with no miss file written, and the person
  is told why

#### Scenario: A more visible lore repository gets no miss

- **WHEN** the question concerns a private repository, and its team's lore
  repository is public
- **THEN** the person is told why no miss file is written

#### Scenario: A question with a category gets no miss

- **WHEN** the person declines, as one the inquisitor should have
  handled, a Discord message the session's model judges holds a
  password, a category under the inquisitor's *Some questions are
  recorded by hash only*
- **THEN** nothing is posted, and the person is told why no miss file is
  written

#### Scenario: A private thread's miss does not go to a public lore repository

- **WHEN** a question asked in a private repository concerns a public
  repository, and the team's lore repository is public
- **THEN** no miss file is written, as a GitHub thread is as visible as
  its repository, and the person is told why

#### Scenario: A Linear or Discord question's miss needs a private lore repository

- **WHEN** a question asked on Linear or Discord concerns a repository
  whose team's lore repository is not private
- **THEN** the person is told why no miss file is written

#### Scenario: A file's visibility stands in for a missing thread

- **WHEN** a questions-branch question with no thread, about a public
  repository, comes from a file the inquisitor's *A log or miss file is
  as private as its more private repository* ranks private, and its lore
  repository is public
- **THEN** the person is told why no miss file is written
