## ADDED Requirements

The **answer session** is the part of the inquisitor in which a person does
nothing but answer the questions asked of them. Its user interface is a
Claude Code mod that ships with the skill. This spec names that interface
only by what it does, never by how it looks or which keys it takes.

Decisions 170 to 175 of this change's proposal are the change's own and
still wait for Adam; the requirements below are written as those decisions
propose. The proposal's *Still open* lists the questions this spec leaves
for him.

Terms used throughout this spec:

- **The person** is the one whose questions the answer session shows: the
  person running the session, whose login the inquisitor's spec defines as
  *the person running the session's login*. When the session has no login
  configured, as the inquisitor's spec defines that, GitHub counts as off.
- **A surface** is GitHub, Linear or Discord.
- **A channel** is what the person subscribes to on a surface: a GitHub
  repository, or every repository of a GitHub owner; a Linear team; or a
  Discord channel, with the threads in it. A channel is **on** when its
  surface is on, by *Setup checks each relay identity before its surface is
  used*.
- **A relay identity** is the bot identity that posts for the person on one
  surface: an identity of the github-app skill on GitHub, of the linear-app
  skill on Linear, and of the discord-bot skill on Discord. Its token stays
  with that skill.
- **A relay post** is a message a relay identity posted.
- **A question's thread** is where a reply to the question goes: the
  conversation of the GitHub issue or pull request that holds it, or the
  review thread when the question is a review comment; the comment thread
  of the Linear comment, or the Linear issue, that holds it; or, on
  Discord, the channel or thread that holds it.
- **The asker** is whoever asked the question: a person, or an agent such as
  an Igor's worker.
- **The queue** is the list of unanswered questions the answer session
  shows the person, one at a time.
- **A question set aside for later** is one the person moved to the end of
  the queue on this machine, to come back to after the new ones.
- **A channel's poll position** is the time of the newest message that
  the channel's last poll read. GitHub's notifications endpoint is one feed
  for every GitHub channel, and has one poll position of its own: the
  `Last-Modified` time of its last response.
- **The same question**, for two questions, means the same hash, as the
  inquisitor's spec defines *a question's text* and *a question's hash*
  for a question in a post. A log file's question is the text under its
  `## Question`, taken whole as one part, not split into its list items
  or sentences.
- **A Claude Code background session** is one with no terminal attached,
  such as a session picker starts.
- **The state folder** is
  `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`.
- **The holder** is the Claude Code session whose answer session holds the
  lock that *One answer session runs on each machine* defines.

### Requirement: The answer session's configuration is a section of the inquisitor's configuration

The answer session SHALL read its configuration from the key
`answer_session` of the inquisitor's configuration,
`~/.config/shared-skills/inquisitor.json`, and from nowhere else. That key
SHALL hold one object per surface the person uses, under `github`, `linear`
or `discord`, each holding:

- `relay`: the name of the surface's relay identity, as the github-app,
  linear-app or discord-bot skill names it with `--identity`;
- `subscriptions`: the surface's channels, as `owner` or `owner/repo` on
  GitHub, Linear team keys on Linear, and channel ids on Discord;
- on Discord only, `user`, the person's Discord user id, and `read`, the
  name of the discord-bot identity the answer session reads Discord with,
  which is never the relay.

The person SHALL use a relay identity for nothing but the answer session's
posts, and the skill's instructions SHALL say so; nothing checks it. The
file SHALL hold no token or key. The person's own Linear API key, which
the answer session reads Linear with, SHALL be held in the system keychain.
When the answer session saves the file, it SHALL keep every key it does not
write.

#### Scenario: The answer session finds its configuration

- **WHEN** `inquisitor.json` holds `login`, `lore` and an `answer_session`
  key whose `github` object names the relay `adam-relay` and subscribes to
  `o/api`
- **THEN** the answer session watches `o/api` and posts there as the
  github-app identity `adam-relay`

#### Scenario: No token is written into the configuration

- **WHEN** setup saves a Linear subscription
- **THEN** `inquisitor.json` holds the Linear team key and the relay's
  identity name, and the person's Linear API key is in the keychain only

#### Scenario: A hand-written key survives a save

- **WHEN** the person has added a key the answer session does not know to
  `inquisitor.json`, and setup saves a new subscription
- **THEN** that key is still in the file, unchanged

#### Scenario: The instructions keep a relay identity to the answer session

- **WHEN** an agent reads the skill's instructions on relay identities
- **THEN** they say that a relay identity posts for nothing but the answer
  session

#### Scenario: A login gh does not confirm turns GitHub off

- **WHEN** `inquisitor.json` names the login `adamstallard`, and `gh` is
  logged in as another account
- **THEN** the answer session reads no GitHub channel and posts nothing on
  GitHub

### Requirement: Setup checks each relay identity before its surface is used

The answer session SHALL run setup in place of the queue when the
`answer_session` key is missing, or when no surface in it has both a
`relay` and a subscription, and SHALL run setup again when the person
types `/answer setup`. Setup SHALL:

- offer as candidates the channels the person can read: the GitHub
  repositories and owners `gh` lists for the person, the Linear teams their
  key can read, and the Discord channels the `read` identity can see;
- check each relay identity: its skill's own check, and a check that it
  can post in each of its surface's subscribed channels;
- on Discord, check that the `read` identity can read the content of
  messages that do not mention it;
- save the configuration, with every surface, whether its check passed or
  failed;
- install the `answer` command, as *Two commands open an answer session*
  says.

When a surface's check fails, setup SHALL show the failure and what the
person must do to fix it, as the identity's skill reports it, and SHALL
save the rest. A surface is **on** while its last check passed, and **off**
otherwise. The answer session SHALL read none of an off surface's channels
and post nothing there. It SHALL record each surface's last check in the
state folder, and SHALL check again, each time it opens, every surface
whose last check failed or never ran.

#### Scenario: A missing section opens setup

- **WHEN** the person opens the answer session and `inquisitor.json` has no
  `answer_session` key
- **THEN** the answer session runs setup instead of showing the queue

#### Scenario: Setup offers the person's channels

- **WHEN** setup runs, and `gh` lists the repository `o/api` for the person
- **THEN** setup offers `o/api` as a channel to subscribe to

#### Scenario: A failed relay check keeps its surface off

- **WHEN** setup's check finds that the Discord relay cannot post in a
  subscribed channel, and the GitHub relay passes
- **THEN** setup shows the Discord failure and how to fix it, saves both
  surfaces, and the answer session reads and posts on GitHub only

#### Scenario: A read identity that cannot read message content keeps Discord off

- **WHEN** the Discord `read` identity receives no content for a message
  that does not mention it
- **THEN** setup shows that failure and how to fix it, and Discord stays off

#### Scenario: A passing recheck turns the surface on

- **WHEN** the Discord relay's last check failed, the person fixes its
  permission, and opens the answer session
- **THEN** the answer session checks the Discord relay again, and, once that
  check passes, reads Discord's subscribed channels

#### Scenario: Setup runs again on request

- **WHEN** the person types `/answer setup` while the configuration is
  complete
- **THEN** setup runs, showing the saved subscriptions as chosen

### Requirement: Two commands open an answer session

The answer session SHALL open, in any Claude Code session where the skill is
installed, when the person types `/answer`. Setup SHALL install a terminal
command named `answer`: an executable file `~/.local/bin/answer`, whose
second line is the comment `# written by inquisitor answer-session setup`,
that runs exactly `CLAUDE_CODE_NO_FLICKER=1 claude --name Answers
'/answer'`. When a file named `answer` without that comment is already
there, setup SHALL leave it as it is and say so. When `~/.local/bin` is
not on the person's `PATH`, setup SHALL say so. No environment variable
opens the answer session.

#### Scenario: The answer command starts an answer session

- **WHEN** the person runs `answer` in a terminal
- **THEN** Claude Code starts with the name `Answers`, in its fullscreen
  layout, and opens the answer session

#### Scenario: Setup leaves another answer command alone

- **WHEN** setup runs and `~/.local/bin/answer` is a file without setup's
  comment line
- **THEN** setup does not change it, and says that the `answer` command was
  not installed

#### Scenario: Setup says when the command is not on PATH

- **WHEN** setup installs `~/.local/bin/answer`, and `~/.local/bin` is not
  on the person's `PATH`
- **THEN** setup says so

### Requirement: A question asked of the person comes from one of four sources

The answer session SHALL show, as a question asked of the person, each of
these that is unanswered, and nothing else:

1. a message in a subscribed channel that mentions the person, as `@login`
   on GitHub, or as a mention of their Linear user or Discord user, whoever
   wrote it, agents running the inquisitor included;
2. a message in a subscribed channel that mentions one of the person's
   relay identities, or that replies to a relay post: a Discord reply to it,
   a Linear comment after it in the same comment thread, a GitHub reply to
   it in a review thread, or the asker's next comment after it in a GitHub
   issue or pull request conversation;
3. on GitHub, a pull request in a subscribed channel that requests the
   person's review, or an issue there assigned to the person;
4. a log file on the questions branch of a lore repository the inquisitor's
   configuration names, which holds no answer, whose question tags the
   person, and for which that branch holds no later log file with the same
   question and an answer.

The answer session SHALL show a question once: a log file of the fourth
source whose question is the same question as one it shows from a thread
SHALL not be shown. A question of the third source is answered by a comment
on that pull request or issue.

#### Scenario: An agent's mention is a question

- **WHEN** an agent running the inquisitor posts, in a subscribed
  repository, a question that tags `@adamstallard`, the configured login
- **THEN** the answer session shows it as a question asked of the person

#### Scenario: A reply to the relay is a question

- **WHEN** someone replies on Discord to a relay post in a subscribed
  channel
- **THEN** the answer session shows the reply as a question asked of the
  person

#### Scenario: A review request is a question

- **WHEN** a pull request in a subscribed repository requests the person's
  review
- **THEN** the answer session shows it, and an answer to it posts a comment
  on that pull request

#### Scenario: A questions-branch file that tags the person is a question

- **WHEN** a configured lore repository's questions branch holds an
  unanswered log file whose question tags the person, and no subscribed
  thread holds the same question
- **THEN** the answer session shows it as a question asked of the person

#### Scenario: A question in a thread and on the questions branch is shown once

- **WHEN** an agent's post in a subscribed repository tags the person, and
  the lore repository's questions branch holds a log file with the same
  question
- **THEN** the answer session shows the question once, from the post's
  thread

#### Scenario: A message in an unsubscribed channel is not a question

- **WHEN** someone mentions the person in a repository that no subscription
  covers
- **THEN** the answer session does not show it

### Requirement: The answer session polls only while it is open

The answer session SHALL read its channels by polling, and SHALL poll only
while it is open in the holder. Nothing SHALL poll while no answer
session is open. When it opens, it SHALL poll each channel that
is on for everything since the channel's poll position, and then poll again
about every 60 seconds. A channel with no poll position yet SHALL be read
from 14 days before the poll. After each poll it SHALL save each channel's
poll position in the state folder.

On GitHub it SHALL read the notifications endpoint with a conditional
request, sending the `Last-Modified` time of the previous response, and
SHALL wait at least the `X-Poll-Interval` that GitHub's last response set
before polling it again. Until task 0.15 shows that the notifications
endpoint reports all four sources, the answer session SHALL also read each
subscribed repository's issue and pull request comments since its poll
position. It SHALL fetch the questions branch of each configured lore
repository at each poll.

#### Scenario: Opening catches up

- **WHEN** the answer session opens after two days closed
- **THEN** it polls each channel that is on for everything since that
  channel's poll position, and saves each channel's new poll position

#### Scenario: A new channel is read from 14 days back

- **WHEN** the person subscribes to a repository, and the answer session
  polls it for the first time
- **THEN** it reads that repository's messages from the last 14 days

#### Scenario: Nothing polls while the answer session is closed

- **WHEN** no Claude Code session on the machine has an answer session open
- **THEN** nothing polls any channel

#### Scenario: GitHub's poll interval is honoured

- **WHEN** GitHub's last notifications response set `X-Poll-Interval: 120`
- **THEN** the answer session waits at least 120 seconds before reading the
  notifications endpoint again, and sends the `Last-Modified` time it
  received

#### Scenario: Comments are read until the notifications endpoint is measured

- **WHEN** task 0.15 has not shown that the notifications endpoint reports
  all four sources, and the answer session polls a subscribed repository
- **THEN** it also reads that repository's issue and pull request comments
  since its poll position

#### Scenario: Each poll fetches the questions branches

- **WHEN** the answer session polls, and the inquisitor's configuration
  names a lore repository
- **THEN** it fetches that lore repository's questions branch

### Requirement: The answer session reads with the person's credentials and posts only with a relay identity

The answer session SHALL read each surface with the person's own
credentials: the `gh` login on GitHub, the person's Linear API key on
Linear, and the discord-bot identity its `read` key names on Discord. It
SHALL use a relay identity only to check it, to post, and to edit the relay
identity's own posts.

#### Scenario: Reading uses the person's gh login

- **WHEN** the answer session reads a subscribed repository's notifications
- **THEN** it reads them through the person's `gh` login, and not as the
  GitHub relay identity

#### Scenario: Posting uses the relay identity

- **WHEN** the person relays an answer to a question on GitHub
- **THEN** the comment is posted as the GitHub relay identity, not as the
  person's `gh` login

### Requirement: An answer is relayed as the person's words

When the person answers a question, the answer session SHALL post the
answer in the question's thread, as the relay identity of the question's
surface, so that the post names the question it answers: on Discord, as a
reply to the question's message; on Linear, as a comment in the question's
comment thread; on GitHub, as a reply in the review thread when the
question is a review comment, and otherwise as a comment on the issue or
pull request whose last line is `Re: <the URL of the question's comment>`,
or `Re: <the URL of the issue or pull request>` when the question is its
description, a review request or an assignment. The post SHALL start with `User says: `,
followed by the person's answer exactly as they confirmed it. The answer
session SHALL keep each relay post's id in the state folder.

The answer session SHALL post through the relay identity's skill, as a
command it runs on the host itself, never as a tool call of the session's
model. It SHALL run that command as an argument vector with no shell, and
SHALL pass the post's text on standard input, or in a file with mode 0600
in a directory only the person's user can read. Neither prose's
pass nor the inquisitor's filters SHALL be applied to a relay post. The
answer session SHALL scan every relay post for the inquisitor's credential
patterns, and SHALL post nothing that matches.

#### Scenario: An answer is posted with its prefix

- **WHEN** the person answers, with "Back off, capped at a minute.", a
  question asked in a comment on a GitHub issue
- **THEN** the relay identity comments on that issue
  `User says: Back off, capped at a minute.`, ending with a `Re: ` line
  holding the question comment's URL, and the comment's id is saved in the
  state folder

#### Scenario: A Discord answer replies to the question

- **WHEN** the person answers a question asked in a subscribed Discord
  channel
- **THEN** the Discord relay posts the answer as a reply to the question's
  message

#### Scenario: A relay post carries no prose footer and is not vetted

- **WHEN** the person relays an answer that holds a question
- **THEN** the post holds the person's words as confirmed, with no prose
  footer, and no hook blocks it

#### Scenario: Shell syntax in an answer runs nothing

- **WHEN** the person's answer holds `$(rm -rf ~)` and a backtick
- **THEN** the relay post holds that text as written, and no shell runs it

#### Scenario: An answer holding a credential is not posted

- **WHEN** the person's answer holds a string shaped like a GitHub access
  token
- **THEN** the answer session posts nothing, and says why

### Requirement: A relay post can be edited where it was posted

The answer session SHALL let the person edit the latest relay post that
names a question, whether an answer or a question to the asker, and SHALL
edit it in place, as the relay identity
that posted it, keeping its `User says: ` or `User asks: ` prefix and its
`Re: ` line. It SHALL find the post by the id the state folder keeps, or,
on a machine whose state folder does not hold it, as the latest relay post
in the question's thread that names the question. The edited text is scanned as a
new post is.

#### Scenario: An answer is edited in place

- **WHEN** the person edits an answer they relayed on Linear
- **THEN** the Linear relay updates its own comment, which still starts
  with `User says: `, and posts no new comment

#### Scenario: An edit on another machine finds the post in the thread

- **WHEN** the person edits, on their second machine, an answer relayed
  from their first
- **THEN** the answer session finds the relay post in the question's thread
  and edits it

### Requirement: The person can ask the asker

The answer session SHALL let the person ask the asker for clarification
instead of answering. It SHALL post the clarifying question as it posts an
answer, naming the question in the same way, except that the post starts
with `User asks: `, and that it tags the asker when the asker is a person.
The question then waits for the asker.

#### Scenario: A clarifying question goes to the asker's thread

- **WHEN** the person asks Maya, who asked a question on Linear, what she
  means by "soon"
- **THEN** the Linear relay posts, in the question's comment thread, a
  comment that starts with `User asks: ` and mentions Maya

#### Scenario: A clarifying question to an Igor worker goes on the item

- **WHEN** an issue in a subscribed repository is assigned to the person,
  an Igor's worker asked a question in its handback comment on it, and the
  person asks back
- **THEN** the relay posts the clarifying question on that issue, starting
  with `User asks: `, where whichever worker next takes the item reads it

### Requirement: The thread is the durable record of an answer

The answer session SHALL take a question's state from its thread, counting
only the relay posts there that name that question:

- **answered:** the latest such relay post starts with `User says: `;
- **waiting for the asker:** the latest such relay post starts with
  `User asks: `, and the asker has not replied since;
- otherwise, the question is unanswered.

When the asker replies to a question to them, the reply is a question
asked of the person under the second source, shown with the question it
answers. A question from a lore repository's questions branch is answered
when that branch holds a later log file with the same question and an
answer.

#### Scenario: A relay reply marks the question answered on every machine

- **WHEN** the person answered a question on one machine, and opens the
  answer session on another
- **THEN** the second machine shows the question as answered, from the
  relay post in its thread

#### Scenario: An answer to one question leaves another in the thread open

- **WHEN** a GitHub issue's conversation holds two comments that each tag
  the person, and the relay has answered the second, naming it
- **THEN** the answer session shows the second as answered and the first
  as unanswered

#### Scenario: A clarifying question marks it waiting

- **WHEN** the latest relay post naming a question starts with
  `User asks: `, and the asker has posted nothing since
- **THEN** the answer session shows the question as waiting for the asker

#### Scenario: The asker's reply brings the question back

- **WHEN** the asker replies to the relay's clarifying question
- **THEN** the answer session shows the reply as a question asked of the
  person, with the question it answers

#### Scenario: A post lost from local state still marks the question answered

- **WHEN** a relay post succeeded, and the state folder holds no record of
  it
- **THEN** the answer session shows the question as answered, from the
  thread

### Requirement: The thread is read again before a question is shown and before a post

When a question comes on screen and its channel's last poll is more than
about a minute old, the answer session SHALL fetch every reply in the
question's thread since the question and show them all. A relay post among
them that answers the question marks it answered. Any other reply is
shown to the person, and changes the question's state in no way.

Before it posts an answer or a question to the asker, the answer session
SHALL fetch the thread once more. When the thread holds a relay post that
answers the question, it SHALL post nothing and show the question as
answered. When the thread holds another reply that the person has not been
shown, it SHALL post nothing and show that reply; the person relays again
if they still want to.

#### Scenario: Replies since the question are shown

- **WHEN** a question comes on screen, its channel was last polled 3
  minutes ago, and two people have replied in its thread since the question
- **THEN** the answer session fetches the thread and shows both replies,
  and leaves the question unanswered

#### Scenario: An answer relayed elsewhere is not posted twice

- **WHEN** the person relays an answer, and the thread already holds a
  relay post answering the question, made from another machine
- **THEN** the answer session posts nothing, and shows the question as
  answered

#### Scenario: A new reply stops the post

- **WHEN** the person relays an answer, and the asker has replied in the
  thread since the question was shown
- **THEN** the answer session posts nothing, and shows the asker's reply

### Requirement: Local state is per machine, in the state folder

The answer session SHALL keep its working state in the state folder, and
nowhere else: the questions set aside for later, each question's
discussion record, each channel's poll position, each surface's last
check, the ids of relay posts, the question on screen, and the lock.
Filter 1 SHALL never search the state folder. The state is per machine: a
question set aside on one machine is new on another. When the answer
session opens, it SHALL show the question that was on screen when it last
closed, even after Claude Code restarted, unless that question has since
been answered.

#### Scenario: Reopening lands on the same question

- **WHEN** the person closes Claude Code with a question on screen, starts
  it again, and opens the answer session
- **THEN** the answer session shows that question

#### Scenario: Reopening skips a question answered meanwhile

- **WHEN** the question on screen when the answer session closed has since
  been answered from another machine
- **THEN** on opening, the answer session opens on the next question in the
  queue, not on that one

#### Scenario: A question set aside on one machine is new on another

- **WHEN** the person sets a question aside for later on one machine and
  opens the answer session on another
- **THEN** the second machine shows the question as new

### Requirement: One answer session runs on each machine

The answer session SHALL hold a lock, a file `lock` in the state folder,
naming the holder: its Claude Code session's id and name, whether it is
a Claude Code background session, and when it started. The holder SHALL refresh the lock at
least every 30 seconds, and a lock not refreshed for 2 minutes is stale.
The answer session SHALL write the lock so that a crash leaves either the
old lock or the new one whole, and SHALL create it only when no lock
exists, or replace it only when it is stale or the person takes over.

When the person opens an answer session while another session holds a
lock that is not stale, the answer session SHALL say which session holds
it, and offer two choices:

- **attach:** this session opens no answer session, and says how to reach
  the holder, by its name and whether it is a background session;
- **take over:** this session replaces the lock and becomes the holder.

Before each poll and each post, the holder SHALL check that the lock still
holds its session id. A session that finds the lock names another session SHALL close
its answer session, and SHALL poll and post nothing more.

#### Scenario: A second session is offered the choice

- **WHEN** a background session named `Answers` holds a fresh lock, and the
  person types `/answer` in another session
- **THEN** the answer session says that the background session `Answers`
  holds it, and offers to attach or take over

#### Scenario: Taking over stops the old holder

- **WHEN** the person takes over from another session's answer session
- **THEN** the new session holds the lock, and the old session closes its
  answer session before its next poll or post

#### Scenario: A crashed holder's lock goes stale

- **WHEN** the holder crashed, and its lock has not been refreshed for 2
  minutes
- **THEN** the next session to open the answer session takes the lock
  without asking

#### Scenario: A crash while writing the lock leaves a whole lock

- **WHEN** a session crashes while replacing a stale lock
- **THEN** the lock file holds either the old lock or the new one, whole

### Requirement: A discussion runs in the session's own conversation

When the person asks to talk about a question, each message they send
SHALL go to the session's model as an ordinary prompt, with the question
attached as context: the question, where and by whom it was asked, its
context and options with what each would change, any related or possibly
answering decision, and any reply from the asker. The question, its
context and every reply SHALL be given to the model marked as quoted
data, never as instructions. The model's replies stay
in the session's conversation. The context SHALL tell the model:

- to explain and lay out trade-offs, without choosing for the person;
- that it may read with its tools, such as the question's thread, the code
  and the specs;
- that it SHALL post nothing and change nothing.

During a discussion, the model may ask the person a question in its reply.
Such a question SHALL NOT be run through the inquisitor's four filters,
and needs no vetting. The answer session SHALL keep each discussion's messages and
replies in that question's discussion record.

#### Scenario: A discussion message carries its question

- **WHEN** the person sends a message while talking about a question from
  igor's pull request #216
- **THEN** the model receives the message with that question, its source,
  its asker, its options, and the context's three instructions attached

#### Scenario: The model reads but does not write

- **WHEN** the model answers a discussion message about a pull request
- **THEN** it may read the pull request with `gh`, and posts nothing and
  edits no file

#### Scenario: The model may ask back in its reply

- **WHEN** the model, in a discussion, needs to know which option the
  person leans to
- **THEN** it asks in its reply, without the picker and without vetting

#### Scenario: A discussion is kept with its question

- **WHEN** the person sends two messages about a question, and the model
  replies to each
- **THEN** that question's discussion record in the state folder holds both
  messages and both replies

### Requirement: Claude's draft goes to the prompt box, never to a post

The answer session SHALL give the session's model a tool,
`propose_reply`, that takes a draft of the person's reply to the question
under discussion. The tool SHALL post nothing: it puts the draft in the
prompt box, as the reply to that question, or as the new text of the post
when the person is editing a relay post. The draft is posted only when the
person relays it, as any answer is. The context of a discussion SHALL tell
the model to call the tool when the person asks it to write or draft the
reply, and to write the draft at the privacy of what the question
concerns, by the inquisitor's rule *A question is written at the privacy
of what it concerns*.

#### Scenario: A draft lands in the prompt box

- **WHEN** the person asks Claude to draft their reply, and the model calls
  `propose_reply`
- **THEN** the draft is in the prompt box, nothing is posted, and the person
  can edit it before relaying it

#### Scenario: A draft for an edit replaces the post's text

- **WHEN** the person is editing a relay post and asks Claude to draft the
  new text
- **THEN** the draft is in the prompt box as the post's new text, and the
  post is changed only when the person relays the edit

#### Scenario: The context asks for a draft at the question's privacy

- **WHEN** the person discusses a question asked in a public repository
- **THEN** the context tells the model to call `propose_reply` for a draft,
  and to write that draft at the privacy of that repository

### Requirement: A rephrased question is answered with its rephrasing

When the person rephrases a question after a discussion and answers the
rephrased question, the answer session SHALL post the answer as:

```
User says: <the answer>

Rephrased question: <the question as rephrased>
Discussion: <the discussion in one sentence>
```

followed by its `Re: ` line on GitHub. The session's model drafts the
rephrased question and the summary, at the privacy of what the question
concerns, by the inquisitor's rule *A question is written at the privacy
of what it concerns*. The answer session SHALL post nothing until the
person has confirmed the whole post, rephrasing and summary included. The
agent that records the answer in the question's log file SHALL record the
rephrased question and the summary there, in the format *A log file and a
miss file have one format* states.

The answer session SHALL write no log file, except to answer a question
file on a lore repository's questions branch, the fourth source.
It SHALL answer such a question by writing a new log file through the
inquisitor script's `log` command, which pushes it to that same questions
branch under the rules of the inquisitor's *Every answer is recorded and
every asked question logged*. The file holds the question,
the person's confirmed answer as its answer, its `authority` by the rules
the inquisitor's *Every answer is recorded and every asked question
logged* sets for an answer the person gave in the session, and any
rephrasing and summary. The answer session SHALL offer no question to the asker and no
edit for a question of the fourth source.

#### Scenario: A rephrased answer carries the rephrasing

- **WHEN** the person rephrases a question after a discussion, confirms the
  model's rephrasing and summary, and answers it
- **THEN** the relay post starts with `User says: ` and the answer, then
  gives the rephrased question and the one-sentence summary on lines of
  their own

#### Scenario: An unconfirmed rephrasing is not posted

- **WHEN** the model has drafted a rephrasing, and the person has not
  confirmed it
- **THEN** the answer session posts nothing

#### Scenario: The asker logs the rephrasing

- **WHEN** an agent records the answer to its question from a relay post
  that gives a rephrased question
- **THEN** the question's log file holds the rephrased question under
  `## Rephrased question` and the summary under `## Discussion`

#### Scenario: A questions-branch question is answered by a new file

- **WHEN** the person answers a question of the fourth source
- **THEN** the script pushes a new log file holding the question and the
  answer to that branch, in a commit with the message
  `inquisitor: log <file>`, posts nothing, and leaves the earlier file
  unchanged

#### Scenario: A questions-branch question offers no ask-back or edit

- **WHEN** a question of the fourth source is on screen
- **THEN** the answer session offers no question to the asker, and, once it
  is answered, no edit
