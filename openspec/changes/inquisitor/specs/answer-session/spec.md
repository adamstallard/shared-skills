## ADDED Requirements

The **answer session** is the part of the inquisitor in which a person does
nothing but answer the questions asked of them. Its user interface is a
Claude Code mod that ships with the skill. This spec names that interface
only by what it does, never by how it looks or which keys it takes.

The proposal's *Still open* lists what this change leaves open, and says,
for anything that touches a requirement below, how that requirement is
written until it is settled.

Terms used throughout this spec:

- **The person** is the one whose questions the answer session shows: the
  person running the session, whose login the inquisitor's spec defines as
  *the person running the session's login*. When the session has no login
  configured, as the inquisitor's spec defines that, GitHub counts as off.
- **A surface** is GitHub, Linear or Discord.
- **A channel** is what the person subscribes to on a surface: a GitHub
  repository, or every repository of a GitHub owner; a Linear team; or a
  Discord channel, with the threads in it. Whether a channel is **on** or
  **off** is set by *Setup checks each relay identity before its channels
  are used*.
- **A relay identity** is the bot identity that posts for the person on one
  surface: an identity of the github-app skill on GitHub, of the linear-app
  skill on Linear, and of the discord-bot skill on Discord. On Discord it
  also reads. Its token stays with that skill.
- **A relay post** is a message a relay identity posted that starts with
  one of the four **reserved prefixes**: `User says: `, `User asks: `,
  `Recorded answer: ` or `Inquisitor: `. A relay identity's other posts
  are not relay posts, and nothing in this spec reads them.
- **An automatic post** is a relay post that starts with
  `Recorded answer: ` or `Inquisitor: `, whose text the answer session
  fixes rather than the person. The answer session makes one by itself,
  or, when the person declines a question because the inquisitor should
  have handled it, agreeing to a shown recorded answer included, makes
  one only once the person confirms it.
- **A question's thread** is where a reply to the question goes: the
  conversation of the GitHub issue or pull request that holds it, or the
  review thread when the question is a review comment; the comment thread
  of the Linear comment, or the Linear issue, that holds it; or, on
  Discord, the channel or thread that holds it.
- **The asker** is whoever asked the question: a person, or an agent such as
  an Igor's worker.
- **A relayed question** is a message that starts with `User says: ` or
  `User asks: `, posted by any bot account, on any surface. One posted on
  GitHub by a person's relay App, as the inquisitor's spec defines it, is
  that person's; one from any other bot is a relayed question too, the
  words of a person whose relay it is, though which person can't be
  proved. A relayed question is a person's question, so filter
  1 can answer it by itself from a record, as *Filter 1 runs on every
  incoming question* says, and filters 2 to 4 only suggest a verdict to
  the person: *Filters 2 to 4 judge every incoming question* posts
  `Inquisitor: ` only on an agent's question.
- **An agent's question** is one whose message's author is a bot account,
  such as a GitHub App, a Linear app user, or a Discord bot or webhook, or
  a log file of the fourth source in *A question asked of the person comes
  from one of four sources*, unless it is a relayed question. Every other
  question is **a person's question**: a relayed question, and one an
  agent posted with a person's own credentials, included.
- **A closed question** is one the person declined on this machine with
  nothing posted, as *The person can decline to answer* says, or a
  questions-branch file that a handled file names, as *A handled file
  closes a questions-branch question* says. A closed question is shown neither in the queue nor as
  new.
- **The queue** is the list of unanswered questions the answer session
  shows the person, one at a time.
- **A question set aside for later** is one the person moved to the end of
  the queue on this machine, to come back to after the new ones.
- **A channel's poll position** is the time of the newest message that
  the channel's last poll read. GitHub's notifications endpoint is one feed
  for every GitHub channel, and has one poll position of its own: the
  `Last-Modified` time of its last response.
- **The same question**, for two questions, means the same hash. The
  inquisitor spec defines a question's text and its hash for a question
  in a post; for a log file, the question is the one the inquisitor
  spec's *Only an answer with authority stops a question* reads from
  it.
- **A thread copy** is a question shown from a thread. A questions-branch
  log file **holds** a thread copy when the file's `asked_in` links that
  thread message (proposal decision 299).
- **A Claude Code background session** is one with no terminal attached,
  such as a session picker starts.
- **The state folder** is
  `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`.
- **The holder** is the Claude Code session whose answer session holds the
  lock that *One answer session runs on each machine* defines.
- **What the question concerns**, **the repository the question
  concerns**, **the team's lore repository** and **more visible** are as
  the inquisitor's spec defines them. The session's model judges what a
  question concerns as that spec has an agent judge it. On GitHub, when
  it can't tell, the repository the question concerns is the repository
  holding the question's thread.

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
- on Discord only, `user`, the person's Discord user id.

The file SHALL hold no token or key. The person's own Linear API key, which
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

#### Scenario: A login gh does not confirm turns GitHub off

- **WHEN** `inquisitor.json` names the login `adamstallard`, and `gh` is
  logged in as another account
- **THEN** the answer session reads no GitHub channel and posts nothing on
  GitHub

### Requirement: Setup checks each relay identity before its channels are used

The answer session SHALL run setup in place of the queue when the
`answer_session` key is missing, or when no surface in it has both a
`relay` and a subscription, and SHALL run setup again when the person
types `/answer setup`. Setup SHALL:

- offer as candidates the channels the person can read: the GitHub
  repositories and owners `gh` lists for the person, the Linear teams their
  key can read, and the Discord channels the Discord relay has been added
  to;
- check each relay identity itself: its skill's own check, and, on
  Discord, that it can read the content of messages that do not mention
  it, which needs Discord's Message Content intent. discord-bot's setup
  has the person turn that intent on for the bot, and its `check` command
  reports `messageContent` as
  `true`, `false` or `null`, read from the bot's application flags; only
  `true` passes, and `null`, meaning the check could not read the flags,
  fails as `false` does (proposal decision 239's item 7). `check` also
  reports `memberSearch`, whether Discord lets discord-bot search the
  server's members by name; that value does not affect whether the
  Discord relay passes (proposal decision 247);
- check that each relay identity can post in each of its surface's
  subscribed channels;
- save the configuration, with every channel, whether its check passed or
  failed;
- install the `answer` command, as *Two commands open an answer session*
  says;
- read the person's relay file, as the inquisitor's spec defines it, in
  each configured lore repository that serves a subscribed GitHub
  channel, and open a pull request to that lore repository when the file
  is missing, does not list each of the person's relay identities on
  every surface the configuration names, or does not count because its
  last change was not the person's. Setup opens it
  through the person's `gh` login, and it writes
  `relays/<their login>.yaml` listing them, its first line the comment
  `# confirmed by <their login> on <the date>`, and report its link. When
  such a pull request from the person is already open, setup SHALL open
  no other, and SHALL report that one's link. Setup SHALL never push the
  file to the default branch. Setup SHALL say that the person's relayed
  answers on GitHub count only as input there until the pull request
  merges and the lore clone has fetched its default branch, or, for an
  Igor, until igor PR #208's lore read applies that commit, and that a
  later change to the file by anyone else makes them input again;
- where that lore repository's default branch has no
  `.github/workflows/relay-notice.yml`, open a separate pull request
  adding the inquisitor's `relay-notice.yml` there, unless one from the
  person is open, and report its link. When GitHub refuses it, such as
  for a `gh` login without the `workflow` scope, setup SHALL say so and
  that the person will not be told of changes to their relay file, and
  SHALL carry on.

Setup SHALL open each of these pull requests as a host command, as a relay
post is posted, with a fixed title and body that the script writes,
holding no word from the session's model, so no post hook sees it and it
gets no prose pass.

When a check fails, setup SHALL show the failure and what the person must
do to fix it, as the identity's skill reports it, and SHALL save the rest.
A channel is **on** while the last check of its relay identity itself and
the last check of posting in that channel both passed, and **off**
otherwise: a failed check of the identity turns off every channel of its
surface, and a failed check of one channel turns off that channel alone.
Where no check can read whether the relay identity may post in a channel
(task 0.20), a post the surface refuses there SHALL count as a failed
check of posting in that channel.
The answer session SHALL read nothing in an off channel and post nothing
there. It SHALL record each check's last result in the state folder, and
SHALL run again, each time it opens, every check that last failed or
never ran.

#### Scenario: A missing section opens setup

- **WHEN** the person opens the answer session and `inquisitor.json` has no
  `answer_session` key
- **THEN** the answer session runs setup instead of showing the queue

#### Scenario: Setup offers the person's channels

- **WHEN** setup runs, and `gh` lists the repository `o/api` for the person
- **THEN** setup offers `o/api` as a channel to subscribe to

#### Scenario: A channel the relay cannot post in is off alone

- **WHEN** setup's check finds that the Discord relay cannot post in one
  of two subscribed Discord channels, and can post in the other
- **THEN** setup shows the failure and how to fix it, saves both channels,
  and the answer session reads and posts in the other channel only

#### Scenario: A failed identity check turns off its whole surface

- **WHEN** the GitHub relay's own github-app check fails
- **THEN** setup shows that failure and how to fix it, and every
  subscribed GitHub channel stays off

#### Scenario: A relay that cannot read message content keeps Discord off

- **WHEN** discord-bot's `check` reports `messageContent` as `false` or
  `null` for the Discord relay
- **THEN** setup shows that failure and says to turn on the bot's Message
  Content intent, or why the check could not read it, and every Discord
  channel stays off

#### Scenario: A refused post turns a channel no check can read off

- **WHEN** no check can read whether the Linear relay may post in a
  subscribed team, and Linear refuses a relay post there
- **THEN** nothing is posted, the person is told why, the question keeps
  its state, and the team stays off until a check at a later opening
  passes

#### Scenario: A passing recheck turns the channel on

- **WHEN** the Discord relay's last check of posting in a channel failed,
  the person fixes its permission, and opens the answer session
- **THEN** the answer session checks that channel again, and, once that
  check passes, reads the channel

#### Scenario: Setup proposes the person's relays to the lore repository

- **WHEN** setup runs for a person subscribed to `o/api`, a configured lore
  repository serves `o`, and its default branch has no
  `relays/<the person's login>.yaml`
- **THEN** setup opens a pull request to that lore repository writing that
  file, with the relay's App slug under `github` and any Linear or Discord
  relay's id under `linear` or `discord`, reports its link,
  pushes nothing to the default branch, and says that the person's
  relayed answers there count only as input until it merges and the lore
  clone has fetched it

#### Scenario: Setup opens no second relay pull request

- **WHEN** setup runs again while the person's earlier pull request to
  their relay file in the lore repository is still open
- **THEN** setup opens no other pull request, and reports the open one's
  link

#### Scenario: Setup proposes nothing when the relays are listed

- **WHEN** setup runs, and the person's relay file on the lore
  repository's default branch, last changed by a pull request they
  authored, lists each of their relay identities, and the default branch
  holds `.github/workflows/relay-notice.yml`
- **THEN** setup opens no pull request to it

#### Scenario: Setup proposes the file again after someone else changed it

- **WHEN** setup runs, and the person's relay file lists each of their
  relay identities, but its last change came from a pull request another
  person authored
- **THEN** setup opens a pull request from the person rewriting the file
  with a new first line, `# confirmed by <login> on <date>`, so the pull
  request changes it even when the relays listed are the same,
  and says that their relayed answers there count only as input until it
  merges

#### Scenario: Setup proposes the notice workflow

- **WHEN** setup runs, and the lore repository's default branch has no
  `.github/workflows/relay-notice.yml`
- **THEN** setup opens a separate pull request adding the inquisitor's
  `relay-notice.yml`, and reports its link

#### Scenario: A refused notice pull request does not stop setup

- **WHEN** GitHub refuses setup's pull request adding `relay-notice.yml`,
  because the person's `gh` login lacks the `workflow` scope
- **THEN** setup says so, says the person will not be told of changes to
  their relay file there, and carries on

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
these that is unanswered, and nothing else. A message of the first or
second source that is clearly not a question at all, such as a
rhetorical one or a thank-you, as the session's model judges it, SHALL
be ignored: it is not shown, nothing is posted on it, and nothing is
closed. An unclear one is shown (proposal decision 289).

1. a message in a subscribed channel that mentions the person, as `@login`
   on GitHub, or as a mention of their Linear user or Discord user, whoever
   wrote it, agents running the inquisitor included;
2. a message in a subscribed channel that mentions one of the person's
   relay identities, or that replies to a relay post: a Discord reply to it,
   a Linear comment after it in the same comment thread, a GitHub reply to
   it in a review thread, or the asker's next comment after it in a GitHub
   issue or pull request conversation;
3. on GitHub, a pull request in a subscribed channel that requests the
   person's review, or an issue there assigned to the person; on Linear,
   an issue in a subscribed team assigned to the person;
4. a log file on the questions branch of a lore repository the inquisitor's
   configuration names, which holds no answer, whose question tags the
   person, for which that branch holds no later log file with the same
   question that is answered, and which no handled file names (proposal
   decisions 273 and 297). A handled file is never shown as a question of
   its own.

The answer session SHALL show a question once: a log file of the fourth
source whose `asked_in` links a thread message follows that message, by
that exact link. Whatever the answer session decides about the message,
showing it, answering it, ignoring it as not a question or declining it,
applies to the log file, which is not shown on its own. A log file with
no `asked_in` is judged on its own as a question of the fourth source
(proposal decision 299). A log file whose `asked_in` links a message
this machine does not read, as in a channel it does not subscribe to, is
not shown on this machine. A question of the third source is answered by a comment
on that pull request or issue. An Igor worker's handback comment tags no
one, so its question is shown only through the third source, when its
item is assigned to the person.

A GitHub comment from `github-actions[bot]` whose first line is the relay
notice's fixed first line, as the inquisitor's *A pull request that
changes a relay file mentions its person* gives it, is not a question: the
answer session SHALL show it to the person as a notice, post nothing on
it, and log no miss for it.

A question the person declined as over stays closed on that machine. Every later message in its thread that the four sources name,
unless the ignore rule above drops it, is shown on its own as a new question, on every machine, under whichever
source names it: the asker's unthreaded follow-up after a relay post or
a threaded reply to one under the second, a mention of the person under
the first (proposal decisions 283, 287 and 291).

#### Scenario: A relay notice is shown, never answered

- **WHEN** the relay-notice workflow comments on a pull request in the
  lore repository, mentioning the person, with its fixed first line
- **THEN** the answer session shows the comment to the person as a
  notice, posts nothing on it, and logs no miss

#### Scenario: An agent's mention is a question

- **WHEN** an agent running the inquisitor posts, in a subscribed
  repository, a question that tags `@adamstallard`, the configured login
- **THEN** the answer session shows it as a question asked of the person

#### Scenario: A reply to the relay is a question

- **WHEN** someone replies on Discord to a relay post in a subscribed
  channel
- **THEN** the answer session shows the reply as a question asked of the
  person

#### Scenario: A Linear issue assigned to the person is a question

- **WHEN** an issue in a subscribed Linear team is assigned to the person
- **THEN** the answer session shows it, and an answer to it posts a comment
  on that issue

#### Scenario: A review request is a question

- **WHEN** a pull request in a subscribed repository requests the person's
  review
- **THEN** the answer session shows it, and an answer to it posts a comment
  on that pull request

#### Scenario: A questions-branch file that tags the person is a question

- **WHEN** a configured lore repository's questions branch holds an
  unanswered log file whose question tags the person, and that holds no
  `asked_in`
- **THEN** the answer session shows it as a question asked of the person

#### Scenario: A questions-branch file follows the message it links

- **WHEN** an agent's post in a subscribed repository tags the person, and
  the lore repository's questions branch holds a log file whose
  `asked_in` is that post's URL
- **THEN** the answer session shows the question once, from the post's
  thread

#### Scenario: Ignoring the linked message ignores the file

- **WHEN** the answer session ignores, as not a question, a message that
  a questions-branch log file's `asked_in` links
- **THEN** it shows the log file neither on its own nor with the message

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
endpoint reports every GitHub message of the first three sources in *A
question asked of the person comes from one of four sources*, the answer
session SHALL also read each subscribed repository's issue and pull
request comments since its poll position. The fourth source never
appears in notifications: the answer session SHALL fetch the questions
branch of each configured lore repository at each poll.

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
  every GitHub message of the first three sources, and the answer session
  polls a subscribed repository
- **THEN** it also reads that repository's issue and pull request comments
  since its poll position

#### Scenario: Each poll fetches the questions branches

- **WHEN** the answer session polls, and the inquisitor's configuration
  names a lore repository
- **THEN** it fetches that lore repository's questions branch

### Requirement: The answer session reads with the person's credentials, except on Discord

The answer session SHALL read GitHub with the person's `gh` login, and
Linear with the person's Linear API key, and SHALL use the GitHub and
Linear relay identities only to check them, to post, and to edit their own
relay posts. On Discord, the Discord relay identity SHALL both read and
post, in the channels it has been added to.

#### Scenario: Reading uses the person's gh login

- **WHEN** the answer session reads a subscribed repository's notifications
- **THEN** it reads them through the person's `gh` login, and not as the
  GitHub relay identity

#### Scenario: Discord is read by its relay

- **WHEN** the answer session reads a subscribed Discord channel
- **THEN** it reads it as the Discord relay identity, which also posts
  there

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

On Discord the answer session SHALL post through discord-bot with none of
its header options (`--agent`, `--session`, `--project`, which put a line
above the message), so the message starts with its reserved prefix, and
with discord-bot's mention rewriting on, as discord-bot always posts. The
text it passes is the answer as the person confirmed it; discord-bot
then rewrites an `@name` into a mention that notifies that member, and a
`#channel` into a link, so an `@name` in the person's answer pings that
member (proposal decision 246). An `@name` that no single member's name
matches stays plain text and pings no one, and discord-bot's result
warns about it; when Discord refuses member search, every `@name` stays
plain text, under one warning that says so. After each Discord relay
post, and after each edit of one, the answer session SHALL show the
person every warning in discord-bot's result (proposal decisions 247 and
252).

When a post fails, because the surface refuses it, such as a Discord
message over 2,000 characters, or because its command fails, the answer
session SHALL tell the person that nothing was posted and why, as the
surface or the skill reports it, and the question SHALL keep the state it
had. When an automatic post fails, the answer session SHALL show its
question to the person as unanswered. A refused post can also turn its
channel off, as *Setup checks each relay identity before its channels are
used* says.

#### Scenario: An answer is posted with its prefix

- **WHEN** the person answers, with "Back off, capped at a minute.", a
  question asked in a comment on a GitHub issue
- **THEN** the relay identity comments on that issue
  `User says: Back off, capped at a minute.`, ending with a `Re: ` line
  holding the question comment's URL, and the comment's id is saved in the
  state folder

#### Scenario: A Discord relay post has no header and pings whom the person names

- **WHEN** the person confirms the Discord answer "ask @maya, see #ops",
  and the channel's server has a member maya and a channel ops
- **THEN** the relay posts through discord-bot with no header option, so
  the message starts `User says: ask `, followed by a mention of maya
  that notifies her, and `#ops` is a link to that channel

#### Scenario: An unmatched Discord name is shown to the person

- **WHEN** the person confirms the Discord answer "ask @maya", and
  discord-bot posts it with a warning that `@maya` matched no member
- **THEN** the answer session shows the person that warning after the
  post

#### Scenario: Refused member search does not fail setup

- **WHEN** discord-bot's `check` reports `messageContent` as `true` and
  `memberSearch` as `false` for the Discord relay, and every other check
  passes
- **THEN** setup counts the Discord relay's check as passed

#### Scenario: Warnings are shown after an edit too

- **WHEN** the person edits a Discord relay post to "ask @maya", and
  discord-bot's `edit` returns a warning that `@maya` matched no member
- **THEN** the answer session shows the person that warning after the
  edit

#### Scenario: A Discord answer replies to the question

- **WHEN** the person answers a question asked in a subscribed Discord
  channel
- **THEN** the Discord relay posts the answer as a reply to the question's
  message

#### Scenario: A relay post carries no prose footer and is not vetted

- **WHEN** the person relays an answer that holds a question
- **THEN** the post holds the person's words as confirmed, with no prose
  footer, and no hook blocks it

#### Scenario: A post's text file is private

- **WHEN** the answer session passes a relay post's text to the relay
  identity's skill in a file
- **THEN** the file has mode 0600, in a directory only the person's user
  can read

#### Scenario: Shell syntax in an answer runs nothing

- **WHEN** the person's answer holds `$(rm -rf ~)` and a backtick
- **THEN** the relay post holds that text as written, and no shell runs it

#### Scenario: A post the surface refuses leaves the question open

- **WHEN** the person relays a Discord answer of 2,500 characters, and
  Discord refuses it
- **THEN** the answer session says that nothing was posted and gives
  Discord's reason, and the question is still unanswered

#### Scenario: An answer holding a credential is not posted

- **WHEN** the person's answer holds a string shaped like a GitHub access
  token
- **THEN** the answer session posts nothing, and says why

### Requirement: A relay post can be edited where it was posted

The answer session SHALL let the person edit the latest relay post that
names a question, whatever its prefix, and SHALL edit it in place, as the
relay identity that posted it, keeping its `Re: ` line. An edited post
keeps its `User says: ` or `User asks: ` prefix. An edited automatic post
starts with `User says: ` in place of its own prefix. It SHALL find the post by the id the state folder keeps, or,
on a machine whose state folder does not hold it, as the latest relay post
in the question's thread that names the question. The edited text is scanned as a
new post is.

*A rephrased question is answered with its rephrasing* has the answer
session also push a log file when it answers, in a thread, a question
that an unanswered log file on a lore repository's questions branch
holds. When an edit leaves a `User says: ` answer to such a question, the
answer session SHALL push a new log file holding the question and the
edited answer, as that requirement pushes one: it passes the edited
post's URL as the `answer_link`, which the `log` command leaves out of a
lore repository that is not private for a Linear or Discord post. It
SHALL leave every earlier file
unchanged. The newest such file is the one
that counts, as the inquisitor's *Only an answer with authority stops a
question* says.

#### Scenario: An answer is edited in place

- **WHEN** the person edits an answer they relayed on Linear
- **THEN** the Linear relay updates its own comment, which still starts
  with `User says: `, and posts no new comment

#### Scenario: An edited automatic post becomes the person's words

- **WHEN** the person edits a post that starts with `Recorded answer: `
- **THEN** the relay updates that post, which now starts with
  `User says: ` and holds the text the person confirmed

#### Scenario: An edit is scanned as a new post is

- **WHEN** the person edits a relay post so that it holds a string shaped
  like a GitHub access token
- **THEN** the answer session does not change the post, and says why

#### Scenario: An edit on another machine finds the post in the thread

- **WHEN** the person edits, on their second machine, an answer relayed
  from their first
- **THEN** the answer session finds the relay post in the question's thread
  and edits it

#### Scenario: Editing an agreed recorded answer into the person's words pushes a log file

- **WHEN** the person agreed to the recorded answer shown for a question
  in a GitHub thread that an unanswered log file on the lore
  repository's questions branch also holds, and then edits that post so
  it starts with `User says: `
- **THEN** the relay updates its post, and the script pushes a new log
  file holding the question and the edited answer, which is the
  question's first answer file there, since agreeing pushed none

#### Scenario: Editing an answer the questions branch also logged pushes a new log file

- **WHEN** the person edits a `User says: ` answer they relayed in a
  GitHub thread to a question that an unanswered log file on the lore
  repository's questions branch also holds, and the answer session had
  pushed a log file recording that answer
- **THEN** the relay updates its post, and the script pushes a new log
  file holding the question and the edited answer, with the relay post's
  URL as its `answer_link`, leaving the unanswered file and the earlier
  answer's file unchanged

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
only the relay posts there that name that question, unless the question is
closed on this machine:

- **answered:** the latest such relay post starts with `User says: `;
- **answered for the person:** it starts with `Recorded answer: `;
- **handled for the person:** it starts with `Inquisitor: `;
- **waiting for the asker:** it starts with `User asks: `, and the asker
  has not replied since;
- otherwise, the question is unanswered.

A question with a thread takes its state only from the relay posts in
its thread, which every machine reads, and from this machine's state
folder: a question declined with nothing posted is closed on this
machine, whatever its thread holds, and unanswered on another machine,
where the person can decline it again (proposal decision 297). A file a
handled file closed is still unanswered, so an answer given to its
thread copy on another machine still pushes a log file answering it. A
questions-branch file is closed, on every machine and for good, only by
a handled file that names it, as *A handled file closes a
questions-branch question* says; nothing else closes it, and nothing
reopens it. The answer session SHALL list the questions answered and
handled for the person, apart from the queue, so the person can see and
edit what was posted for them.

When the asker replies to the relay's `User asks: ` post while the
person's question waits for it, the reply puts that question back in the
queue, shown with the reply, whether or not the reply is itself a
question. A question from a lore repository's questions branch is answered
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

#### Scenario: An automatic post marks the question answered or handled for the person

- **WHEN** the latest relay post naming one question starts with
  `Recorded answer: `, and the latest naming another starts with
  `Inquisitor: `
- **THEN** the answer session lists the first as answered for the person
  and the second as handled for them, and shows neither in the queue

#### Scenario: A question declined on one machine is open on another

- **WHEN** the person declines with nothing posted, on one machine, a
  question that no questions-branch file holds, and opens the answer
  session on another
- **THEN** the second machine shows the question as unanswered

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
them that names the question sets its state, as *The thread is the
durable record of an answer* says. Any other reply is shown to the person,
and changes the question's state in no way.

Before it posts an answer or a question to the asker, the answer session
SHALL fetch the thread once more. It does the same before each automatic
post. When the thread holds a relay post that answers or handles the
question, it SHALL post nothing and show the question in that state. When the thread holds another reply that the person has not been
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
nowhere else: the questions set aside for later, the closed questions,
each open question's discussion record, each channel's and the GitHub
notifications feed's poll position, each check's last result, the ids of
relay posts, the question on screen, and the lock.
Filter 1 SHALL never search the state folder. The answer session SHALL
delete a question's discussion record once the question is answered,
answered or handled for the person, or closed. The state is per machine: a
question set aside on one machine is new on another. When the answer
session opens, it SHALL show the question that was on screen when it last
closed, even after Claude Code restarted, unless that question has since
been answered.

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
- **THEN** on opening, the answer session opens on the next question in the
  queue, not on that one

#### Scenario: An answered question's discussion record is deleted

- **WHEN** the person discusses a question, then relays an answer to it
- **THEN** the state folder no longer holds that question's discussion
  record

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
lock that is not stale, this session SHALL open no answer session. It
SHALL say which session holds the lock, by its name and whether it is a
Claude Code background session, say how to reach it, and offer to take
over. When the person takes over, this session replaces the lock and
becomes the holder.

Before each poll and each post, the holder SHALL check that the lock still
holds its session id. A session that finds the lock names another session SHALL close
its answer session, and SHALL poll and post nothing more.

#### Scenario: A second session is offered the choice

- **WHEN** a background session named `Answers` holds a fresh lock, and the
  person types `/answer` in another session
- **THEN** this session opens no answer session, says that the background
  session `Answers` holds the lock and how to reach it, and offers to take
  over

#### Scenario: Taking over stops the old holder

- **WHEN** the person takes over from another session's answer session
- **THEN** the new session holds the lock, and the old session closes its
  answer session before its next poll or post

#### Scenario: A live holder keeps its lock fresh

- **WHEN** the holder has been open for 10 minutes and is idle
- **THEN** its lock was refreshed within the last 30 seconds, and a
  second session that opens the answer session finds it not stale

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

#### Scenario: A thread's text reaches the model as quoted data

- **WHEN** the person discusses a question whose thread holds a reply
  telling the model to post a comment
- **THEN** the model receives that reply marked as quoted data, not as an
  instruction, and posts nothing

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

Apart from the handled file of *A handled file closes a questions-branch
question*, the answer session SHALL write no log file, except to answer
a question that an unanswered log file on a lore repository's questions
branch holds: a question of the fourth source, or a question shown from
a thread whose message that file's `asked_in` links. For a question shown
from a thread, it SHALL relay the answer in the thread, as *An answer is
relayed as the person's words* says, and also push the log file. It SHALL
answer such a question by writing a new log file through the
inquisitor script's `log` command, which pushes it to that same questions
branch under the rules of the inquisitor's *Every answer is recorded and
every asked question logged*. When the answer was also relayed in a
thread, the answer session SHALL pass the `log` command the URL of that
relay post as the `answer_link`, which the command leaves out of a lore
repository that is not private when it is a Linear or Discord URL, as
the inquisitor's *Every answer is recorded and every asked question
logged* says (proposal decision 251). Its answer SHALL be the relay
post's text, word for word, as quote
lines in the inquisitor's log format. On GitHub that is the comment's own
text, which the `log` command reads from the post itself, as the
inquisitor's *Only an answer with authority stops a question* has every
writer record an answer from a comment. On Linear or Discord it is the
text the answer session sent to the relay's skill, its `User says: `
prefix included, before discord-bot rewrites any mention: the answer
session SHALL pass the `log` command that text, and the command fetches
nothing (proposal decision 248). Either way the answer
includes the post's `Rephrased question: ` and `Discussion: ` lines
(proposal decision 239's item 8). When the answer was not relayed in a thread, the file's answer
is the answer the person confirmed in the answer session, word for word
(proposal decision 240). The file also
holds the question, its `authority` by the rules the inquisitor's *Every
answer is recorded and every asked question logged* sets for an answer
the person gave in the session, and any rephrasing and summary. Its
`authority` is set that way whatever surface relayed the answer. Whether
the file then counts
is the inquisitor's *Only an answer with authority stops a question*:
after a Linear or Discord relay, only through the signature on the
commit that added it (proposal decision 250). The answer session SHALL offer no question to the asker and no
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

#### Scenario: A questions-branch question asked in a post is answered in both places

- **WHEN** the person answers, from its GitHub thread, a question that an
  unanswered log file on the lore repository's questions branch also holds
- **THEN** the relay posts the answer in the thread, starting
  `User says: `, and the script pushes a new log file holding the question
  and, as its answer, that relay post's text word for word, to that
  branch, whose `answer_link` is that relay post's URL

#### Scenario: A Linear link is left out of a lore repository that is not private

- **WHEN** the person answers, from its Linear thread, a question that an
  unanswered log file on an internal lore repository's questions branch
  also holds
- **THEN** the script pushes a new log file holding the relayed answer
  and no `answer_link`

#### Scenario: A signed log file of a Discord-relayed answer is a decision

- **WHEN** the person answers in the answer session a question that a
  private lore repository's questions branch holds, the session relays
  it on Discord, and GitHub verifies a signature for `answered_by` on
  the commit that adds the log file, which no later commit changed, and
  `answered_by` has write access to what the question concerns
- **THEN** filter 1 counts the file as a decision, and the file's
  Discord `answer_link` proves nothing

#### Scenario: An unsigned log file of a Discord-relayed answer is input

- **WHEN** the same answer is logged by a commit that carries no
  signature GitHub verifies
- **THEN** filter 1 shows the file as input, with the label the
  inquisitor's *Only an answer with authority stops a question* gives a
  `decision` file whose writer is not proven, unconfirmed

#### Scenario: A questions-branch answer relayed on Linear keeps its link unfetched

- **WHEN** the person answers, from its Linear thread, a question that an
  unanswered log file on a private lore repository's questions branch
  also holds
- **THEN** the script pushes a new log file whose answer is the text the
  answer session sent to the relay's skill, word for word, as quote
  lines, and whose `answer_link` is that Linear comment's URL, and
  nothing fetches that URL

#### Scenario: A questions-branch question offers no ask-back or edit

- **WHEN** a question of the fourth source is on screen
- **THEN** the answer session offers no question to the asker, and, once it
  is answered, no edit

### Requirement: A handled file closes a questions-branch question

Whenever the answer session closes a question, it SHALL push a
**handled file** naming each unanswered log file on a lore repository's
questions branch that holds the question and that no handled file names
yet, through the inquisitor script's `log` command, with a thread or
without. A file holds the question when it is the question, one of the
fourth source, or when its `asked_in` links the closed thread message. A
handled file closes exactly the file it names, on every machine, and
nothing else (proposal decisions 273, 278 and 297). The answer session
closes a question in two ways: it declines the question, agreeing to a
shown recorded answer included, or it posts a recorded answer or an
`Inquisitor: ` reply on it. The handled file is as the inquisitor's *A
log file and a miss file have one format* gives it. It SHALL push the
handled file once the close takes effect: once the post that leads to
it has gone out, or, when nothing is posted, once the person has
confirmed the decline. When the push fails, the answer session SHALL
try it again at each poll until it succeeds. A handled file closes the
file it names without answering it, and never stops a question for a
searching agent. The answer session writes the file only through the
`log` command's handled option, as the inquisitor's *Every answer is
recorded and every asked question logged* says.

#### Scenario: An automatic Inquisitor reply pushes a handled file

- **WHEN** the answer session posts filter 4's `Inquisitor: ` reply by
  itself on a question in a GitHub thread that an unanswered log file on
  the lore repository's questions branch also holds
- **THEN** it pushes a handled file naming that log file

#### Scenario: A handled file closes a questions-branch question

- **WHEN** a lore repository's questions branch holds an unanswered log
  file whose question tags the person, and a handled file naming it
- **THEN** the answer session shows neither file as a question, on any
  machine

#### Scenario: A handled file closes only the file it names

- **WHEN** a handled file names one questions-branch file, and another
  questions-branch file, or a thread, holds the same words
- **THEN** the answer session still shows the other file and the thread
  copy

#### Scenario: Two questions-branch files get two handled files

- **WHEN** the person declines a question that two unanswered
  questions-branch files hold
- **THEN** the answer session pushes two handled files, each naming one
  of them

#### Scenario: A thread copy declined with nothing posted shows again elsewhere

- **WHEN** the person declines as over, on one machine, a question in a
  GitHub thread that a questions-branch file also holds
- **THEN** a handled file closes the questions-branch file on every
  machine, the thread copy is closed on that machine only, and another
  machine shows the thread copy, which the person can decline again

#### Scenario: A failed post pushes no handled file

- **WHEN** the person declines under the third reason a question in a
  GitHub thread that a questions-branch file also holds, and the post
  fails
- **THEN** no handled file is pushed

### Requirement: Four reserved prefixes mark the answer session's posts

Every relay post SHALL start with one of the four reserved prefixes. The
answer session SHALL post a text starting with `User says: ` or
`User asks: ` only once the person has confirmed that whole text, and a
text starting with `Recorded answer: ` or `Inquisitor: ` only as *Filter 1
runs on every incoming question*, *Filters 2 to 4 judge every incoming
question* and *The person can decline to answer* say. A relay identity may post for other work, but no post
outside the answer session SHALL start with a reserved prefix. The
skill's instructions SHALL say so, and on GitHub the inquisitor's post
hook blocks such a post, as the inquisitor's *Questions in posts pass the
same filters* says. Nothing checks a post on Linear or Discord.

An automatic post SHALL be posted as *An answer is relayed as the
person's words* has a relay post posted: through the relay identity's
skill as a host command with no shell, naming its question the same way,
with its id kept in the state folder, and scanned for the credential
patterns first. Its text is fixed apart from a record's URL, so neither
prose's pass nor the inquisitor's filters SHALL be applied to it. The
answer session SHALL never show an automatic post as the person's words.

#### Scenario: The instructions reserve the prefixes

- **WHEN** an agent reads the skill's instructions on relay identities
- **THEN** they say that a relay identity may post for other work, and
  that no post but the answer session's starts with `User says: `,
  `User asks: `, `Recorded answer: ` or `Inquisitor: `

#### Scenario: A relay identity's other post sets no state

- **WHEN** the GitHub relay identity, used by an agent for other work,
  comments in a question's thread without a reserved prefix
- **THEN** the answer session does not count that comment as a relay post,
  and the question's state is unchanged

#### Scenario: An automatic post is never shown as the person's words

- **WHEN** the answer session lists a question it answered for the person
- **THEN** it shows the post as made by the answer session, not as the
  person's answer

#### Scenario: Nothing starting with User says is posted unconfirmed

- **WHEN** the session's model has drafted a reply, and the person has
  not confirmed it
- **THEN** the answer session posts nothing that starts with `User says: `

### Requirement: The person can decline to answer

On any open question, the person SHALL be able to decline to answer it,
giving one of three reasons:

1. **The conversation is over.** The answer session posts nothing, and the
   question closes. That closes only this question: a later message in
   its thread is shown as a new question, as *A question asked of the
   person comes from one of four sources* says (proposal decision 291).
2. **Not a question:** the message was picked up by mistake, the answer
   session's own misjudgement. The answer session posts nothing, the
   question closes, and no miss is logged (proposal decision 298).
3. **The inquisitor should have handled it.** The person picks the filter
   that should have stopped the question: 1, already answered; 2, can
   wait; 3, one option has merit; or 4, cheap to reverse. The answer
   session SHALL show the person the exact post of that filter's reply,
   and SHALL post it, naming the question, only once the person confirms
   it:
   - for filter 2, 3 or 4, that filter's fixed `Inquisitor: ` text, as
     *Filters 2 to 4 judge every incoming question* gives it, followed by
     the line `The person chose this filter.`, which no post the answer
     session makes by itself holds (proposal decision 239's item 6);
   - for filter 1, a recorded answer in the form *Filter 1 runs on every
     incoming question* gives, whose `Recorded in: ` line holds the URL of
     the place the person gave, or of a place filter 1 found that the
     person chose.

   When a filter 1 reply's record is more private than the question's
   thread, by the rule *Filter 1 runs on every incoming question* states,
   the preview the person confirms SHALL also show that posting it shows
   the record exists, so their one confirmation covers both (proposal
   decision 264). When the question has no thread, the answer session
   posts nothing for any filter, shows the person the recorded answer
   for filter 1, and the question closes. On a
   question with a category, it posts nothing for any filter, and the
   question closes. This reason applies to a person's question as to an
   agent's. The answer
   session logs a miss against the filter the person picked, whose `said`
   is the note the person typed, or `the inquisitor should have handled
   it` when they typed none, written at the privacy of what the question
   concerns. The answer session SHALL push that miss only once its post
   has gone out, or, when nothing is posted, once the person has
   confirmed the decline. A filter 1 decline naming a lore entry SHALL
   push its citation file once, to the entry's own lore repository,
   under *Filter 1 runs on every incoming question*, whether or not it
   pushes a miss (proposal decision 275).

A question declined with nothing posted SHALL be recorded in the state
folder. A thread copy is then closed on this machine only, and nothing a
second machine reads records it; a questions-branch file the question's
handled file names is closed everywhere (proposal decision 297). A question declined under the third reason with a
post takes its state from its thread, as any question does.

The person SHALL be able to reopen, on this machine, a thread copy they
declined with nothing posted, which puts it back in their queue. A
questions-branch file a handled file names SHALL NOT be offered for
reopening (proposal decisions 260, 274 and 297). The answer session SHALL NOT
offer to reopen a question declined with a post; the person changes its
handling by editing that post, as *A relay post can be edited where it
was posted* says (proposal decision 260).

#### Scenario: Declining as over or as not a question posts nothing

- **WHEN** the person declines a question asked on GitHub, because the
  conversation is over or because it is not a question
- **THEN** nothing is posted in its thread, and the question leaves the
  queue

#### Scenario: A follow-up after a closed conversation is a new question

- **WHEN** the person declines, because the conversation is over, a
  question in a GitHub issue's conversation where the relay had posted
  before it, and the asker then comments again in that conversation
  without an @-mention
- **THEN** the answer session shows the comment as a new question, on
  every machine, and the declined question stays closed

#### Scenario: A reply to a relay post after a closed conversation is a new question

- **WHEN** the person declined a question because the conversation is
  over, and the asker then replies on Discord to an earlier relay post in
  that thread, without an @-mention
- **THEN** the answer session shows the reply as a new question, and the
  declined question stays closed

#### Scenario: A reply after a decline is a new question

- **WHEN** the person declined, as not a question, a message in a GitHub
  thread, and the asker then replies in a review thread to an earlier
  relay post in that thread
- **THEN** the answer session does not reopen the declined question, and
  shows the reply on its own as a new question

#### Scenario: A mention after a closed conversation is a question

- **WHEN** the person declined a question because the conversation is
  over, and someone later writes in that thread a message that
  @-mentions the person
- **THEN** the answer session shows that message as a question

#### Scenario: A question declined with a post is not reopened

- **WHEN** the person declined a question under the third reason, and
  the answer session posted that filter's reply
- **THEN** the answer session offers no way to reopen the question, and
  the person can change the handling only by editing that post

#### Scenario: A thread copy declined with nothing posted is reopened on its machine

- **WHEN** the person declined a thread copy as over, with nothing
  posted, and then reopens it on the same machine
- **THEN** the answer session puts it back in the queue on that machine

#### Scenario: A declined questions-branch file is not offered for reopening

- **WHEN** the person declined, because the conversation is over, a
  question from a lore repository's questions branch
- **THEN** the answer session pushed a handled file naming that file,
  which closes it everywhere, and offers no way to reopen it

#### Scenario: Not a question logs no miss

- **WHEN** the answer session showed, under the second source, a reply
  to the relay that was in fact meant for someone else, and the person
  declines it as not a question
- **THEN** the question closes, nothing is posted, and no miss file is
  logged

#### Scenario: The inquisitor's reply is posted once the person confirms it

- **WHEN** the person declines an agent's question on GitHub as one the
  inquisitor should have handled, picks filter 4, and types the note "a
  config flag, easy to flip"
- **THEN** the answer session shows the filter 4 `Inquisitor: ` text,
  followed by the line `The person chose this filter.`, as it will be
  posted, posts it naming the question only once the person confirms it,
  and logs a miss file whose `filter` is `"4"` and whose `said` is that
  note

#### Scenario: A filter 1 reply names the place the person gave

- **WHEN** the person declines a question in a public repository as one
  the inquisitor should have handled, picks filter 1, and gives that
  repository's `docs/retries.md` as the place it is decided
- **THEN** once the person confirms it, the relay posts a reply starting
  `Recorded answer: ` whose `Recorded in: ` line holds that file's URL,
  and a miss file whose `filter` is `"1"` is logged

#### Scenario: A person's question can be answered for the inquisitor

- **WHEN** the person declines a person's question on Linear as one the
  inquisitor should have handled, and picks filter 2
- **THEN** once the person confirms it, the Linear relay posts the filter
  2 `Inquisitor: ` text in the question's comment thread

#### Scenario: A filter 1 reply to a question with no thread is shown, not posted

- **WHEN** the person picks filter 1 for a question of the fourth source,
  giving a decision document as the place it is decided
- **THEN** nothing is posted, the person is shown the recorded answer,
  the question closes, and a miss against filter 1 is logged

#### Scenario: A filter 1 reply with a more private record is posted only after a warning

- **WHEN** the person picks filter 1 for a question in a public
  repository, and the place it is decided is a private repository's
  `DECISIONS.md`
- **THEN** the answer session shows the person that posting the reply
  shows the record exists, and posts it only once they confirm

### Requirement: Filter 1 runs on every incoming question

Before the answer session shows a question, whether a person or an agent
asked it, it SHALL run filter 1 on it through the inquisitor script's
search, with the person's credentials, as the inquisitor's *Filter 1
searches every place an answer is recorded* and *Only an answer with
authority stops a question* say. The session's model first judges whether
the question has a category, as the inquisitor's *Some questions are
recorded by hash only* defines one. The answer session SHALL pass a
question with a category to the script on standard input, so that the
search reaches no source outside the machine, and SHALL post nothing by
itself on it. It SHALL pass any other question as the inquisitor's *Two
calls prove the filters ran* has an agent pass its files. The session's model judges whether a
hit with authority answers the question; a hit that is only input is
shown with the question, and stops nothing.

When an answer with authority is recorded, and the question has a thread,
the answer session SHALL answer by itself, whether an agent or a person
asked, a relayed question included:
it posts through the relay

```
Recorded answer: see the record below.
Recorded in: <the URL of where the answer is recorded>
```

followed by its `Re: ` line on GitHub, whatever the record is, a log
file included: the post quotes no answer (proposal decision 200's item
1, as decision 239's item 5 amends it). The session's
model writes none of the post: the URL is that of filter 1's hit. The answer session SHALL post it by itself only when the
record is no more private than the question's thread: on GitHub, when the
record's repository is no more visible than the thread's repository; on
Linear and Discord, only when the record's repository is public. When
the record is a log or miss file, the file's own visibility stands in for
its repository's: the more private of its `repository` and `asked_from`,
as the inquisitor's *More visible* defines it.
Otherwise, and for a question from a questions branch, it SHALL show the
recorded answer to the person beside the question, and post only what the
person relays or confirms. The person may agree to the shown recorded
answer. Agreeing is declining the question under the third reason of
*The person can decline to answer* with filter 1, naming that record,
and the answer session SHALL handle it exactly as that requirement
does, with its preview, its warning for a record more private than the
thread, its miss, its citation and its close (proposal decision 270).
On a question with a category, agreeing closes it with nothing posted,
as that rule has it. Agreeing takes no note, as in the approved
prototype, so its miss's `said` is `the inquisitor should have handled
it`. When the answer session posts a recorded answer by itself and the
record is a lore entry, it SHALL push a citation file, as the
inquisitor's *Every answer is recorded and every asked question logged*
says. A person **cites** a lore entry when they answer
a question by naming that entry as its answer, or when they decline a
question, agreeing to a shown recorded answer included, under the third reason of *The person can decline to answer*, "the
inquisitor should have handled it", with filter 1, naming that entry as
the record (proposal decisions 262 and 270). The answer session SHALL
push a citation file for the entry the person cites, under the citation rules of the
inquisitor's *Every answer is recorded and every asked question logged*, but only when the entry is `active` and in scope for the
question, as the inquisitor's *Filter 1 searches every place an answer
is recorded* defines a lore entry's scope. Citing any other entry pushes nothing (proposal decisions 257
and 259). When it answers an agent's question by itself, it
SHALL log a miss against filter 1, as *The answer session logs its misses
on the team's lore repository's questions branch* says; a person's
question logs none when the answer session answers it by itself. Before each automatic post, the answer session
reads the question's thread again, as *The thread is read again before a
question is shown and before a post* says.

A reply to an automatic post is a question, judged by filters 1 to 4
again, and may be answered by itself again. A question's **chain of
replies** is the question, the relay post it replies to, the question
that relay post names (on GitHub, by its `Re: ` line), and so on back to
a question that replies to no relay post. The answer session SHALL NOT make by itself an automatic post
whose text, apart from its `Re: ` line, is the same as that of any
automatic post already made in the chain of replies of the question it
would answer: such a repeat goes to the person, as an ordinary question.
So in one chain each of the three `Inquisitor: ` texts goes out at most
once, and so does each recorded answer.

#### Scenario: A recorded answer is posted by itself

- **WHEN** an agent's question in a public repository asks whether retries
  back off, and that repository's `DECISIONS.md` on its default branch
  decides it
- **THEN** the relay posts, naming the question, a reply that starts with
  `Recorded answer: see the record below.`, gives a `Recorded in: ` line
  with that file's URL and quotes no answer, the question is listed as answered for the person, and a miss against
  filter 1 whose `said` is `answer session: clearly filter 1` is logged

#### Scenario: A person's question is answered by itself too

- **WHEN** a person's question on Linear is answered by a decision
  document in a public repository
- **THEN** the Linear relay posts the recorded answer in its comment
  thread, starting with `Recorded answer: `, never with `User says: `, and
  no miss is logged

#### Scenario: A relayed question gets a recorded answer by itself

- **WHEN** a GitHub comment that starts with `User asks: `, from the
  relay App of Maya, another person, tags the person, and the
  repository's `DECISIONS.md` on its default branch decides it
- **THEN** the relay posts, naming the question, a reply that starts with
  `Recorded answer: `, the question is listed as answered for the person,
  and no miss is logged

#### Scenario: A relayed question from an App no relay file lists is a person's

- **WHEN** a GitHub comment that starts with `User asks: ` comes from a
  GitHub App that no relay file lists, tags the person, and clearly fails
  filter 4
- **THEN** the answer session posts nothing by itself, and shows the
  question as a person's, with filter 4's verdict suggested

#### Scenario: A lore entry's recorded answer sends a citation

- **WHEN** an active lore entry answers an incoming question with a thread
- **THEN** the relay posts the recorded answer, and the script pushes a
  citation file to that lore repository's questions branch

#### Scenario: Citing a lore entry sends a citation

- **WHEN** the person answers a question about a private repository by
  citing an active entry in a private lore repository
- **THEN** the answer session pushes a citation file for that entry to
  that lore repository's questions branch

#### Scenario: Citing an entry that is not active sends none

- **WHEN** the person answers a question by citing a lore entry whose
  status is not `active`
- **THEN** no citation file is pushed

#### Scenario: Declining with filter 1 and a lore entry cites it

- **WHEN** the person declines a question with no category, asked in a
  GitHub thread of a private repository, under the third reason, picks
  filter 1, and names as the record an `active` entry in a private lore
  repository whose scope covers the question
- **THEN** the relay posts in the thread the `Recorded answer: ` reply
  whose `Recorded in: ` line names that entry, and the answer session
  pushes a citation file for it

#### Scenario: A filter-1 decline with no thread still cites its entry

- **WHEN** the person declines under the third reason, with filter 1, a
  question from a private lore repository's questions branch, which has
  no thread, naming as the record an `active` entry of that lore
  repository whose scope covers the question
- **THEN** the answer session posts nothing, shows the person the
  recorded answer beside the question as the decline rule has it for a
  question with no thread, and pushes a citation file for that entry

#### Scenario: Citing an entry out of scope sends none

- **WHEN** the person answers a question by citing an `active` lore
  entry whose scope does not cover the question
- **THEN** no citation file is pushed

#### Scenario: Citing an entry in a more visible lore repository sends none

- **WHEN** the person answers a question about a private repository by
  citing an entry in a public lore repository
- **THEN** no citation file is pushed

#### Scenario: A reply to an automatic post is judged again

- **WHEN** an agent replies to a relay post holding filter 4's fixed
  `Inquisitor: ` text, which *Filters 2 to 4 judge every incoming
  question* gives, with a new question that the repository's
  `DECISIONS.md` on its default branch decides
- **THEN** the relay posts, naming the reply, a recorded answer starting
  with `Recorded answer: `

#### Scenario: A repeated automatic post goes to the person

- **WHEN** an agent replies to a relay post holding filter 4's fixed
  `Inquisitor: ` text with a question that clearly fails filter 4 again
- **THEN** the answer session posts nothing by itself, and shows the reply
  to the person

#### Scenario: An automatic post made earlier in the chain is not made again

- **WHEN** the answer session replied to an agent's question with filter
  2's text, the agent replied with a question it answered with filter 4's
  text, and the agent replies again with a question that clearly fails
  filter 2
- **THEN** the answer session posts nothing by itself, and shows the reply
  to the person

#### Scenario: A reply since the question stops an automatic post

- **WHEN** the answer session is about to post a recorded answer, and the
  thread has a new reply since the question
- **THEN** it posts nothing, and shows the question and the reply to the
  person

#### Scenario: A more private record is shown, not posted

- **WHEN** a question in a public repository is answered by a decision
  document in a private repository
- **THEN** the answer session posts nothing by itself, and shows the
  person the question with the recorded answer beside it

#### Scenario: Agreeing to a more private record posts it after a warning

- **WHEN** a question in a public repository is answered by a decision
  document in a private repository, and the person agrees to the shown
  recorded answer
- **THEN** the answer session shows the person that posting it shows the
  record exists, and once they confirm, the relay posts
  `Recorded answer: see the record below.` with `Recorded in: ` and the
  record's URL

#### Scenario: Agreeing to a lore entry's recorded answer cites it

- **WHEN** the person agrees to a shown recorded answer whose record is
  an `active` lore entry, in a private lore repository, whose scope
  covers a question about a private repository
- **THEN** the answer session pushes a citation file for that entry to
  its lore repository

#### Scenario: Agreeing to an inactive lore entry's recorded answer cites nothing

- **WHEN** the person agrees to a shown recorded answer whose record is a
  lore entry that is not `active`
- **THEN** no citation file is pushed

#### Scenario: Agreeing on a question with no thread is a filter 1 decline

- **WHEN** a question from a lore repository's questions branch (the
  fourth source), which has no thread, is answered by a decision
  document, and the person agrees to the shown recorded answer
- **THEN** nothing is posted, the answer session pushes a handled file
  naming the questions-branch file, which is then closed on every
  machine and cannot be reopened, and a miss against filter 1 is logged with
  `said: "the inquisitor should have handled it"`

#### Scenario: Agreeing in a thread on a questions-branch question pushes only a handled file

- **WHEN** a question that an unanswered log file on the lore
  repository's questions branch also holds is shown from its GitHub
  thread, with a recorded answer more private than the thread shown
  beside it, and the person agrees to it and confirms after the warning
- **THEN** the relay posts the recorded answer in the thread, and the
  answer session pushes a handled file naming that log file and no
  answer file to the questions branch, besides the miss the decline logs

#### Scenario: Agreeing logs a miss on any question

- **WHEN** the person agrees to the recorded answer shown beside a
  question in a private repository's GitHub thread, whose lore
  repository is private, whether a person or an agent asked it
- **THEN** the answer session logs a miss against filter 1 with
  `said: "the inquisitor should have handled it"`

#### Scenario: A questions-branch question's recorded answer is shown, not posted

- **WHEN** a question of the fourth source is answered by a decision
  document in a public repository
- **THEN** the answer session posts nothing by itself, and shows the
  person the question with the recorded answer beside it

#### Scenario: A question with a category is searched on the machine only

- **WHEN** a Discord message that holds a password reaches the answer
  session
- **THEN** the answer session passes it to the script on standard input,
  the search reaches no source outside the machine, and nothing is posted
  by itself

#### Scenario: Input does not answer by itself

- **WHEN** the only hit for a question is a log file with
  `authority: input`
- **THEN** the answer session posts nothing by itself, and shows the
  question with that hit labelled as input

### Requirement: Filters 2 to 4 judge every incoming question

The answer session's model SHALL judge each incoming question that filter
1 did not stop against filters 2, 3 and 4, as the inquisitor's *Every
question passes four filters before a person sees it* states them. It
SHALL treat a question as failing a filter only when the case is clear;
any unclear case goes to the person, as an ordinary question.

For an agent's question that has a thread the relay can reply in, has
no category, and clearly fails filter 2, 3 or 4, the answer session SHALL reply by itself through the relay with that
filter's fixed text, which the session's model does not write:

- filter 2: `Inquisitor: filter 2, deferrable. Carry on without an answer,
  list this question as not done in the current work, and file an issue
  for it if it outlives the work.`
- filter 3: `Inquisitor: filter 3, not a real question. Take the option
  that has merit, and record what you chose and why.`
- filter 4: `Inquisitor: filter 4, cheap to reverse. Pick one, and record
  what you chose and why.`

A message that is not a question gets no automatic post: it is ignored,
as *A question asked of the person comes from one of four sources*
says, so an agent's rhetorical message in a thread gets no post. When
one reaches the person's queue anyway, because the session judged it
unclear and showed it, the person declines it under whichever reason
fits: the second, picked up by mistake, when the session misread it,
which posts nothing and logs no miss; or the third, when the asking
agent should not have written it, with the filter the person picks,
which logs a miss against the agent. The ignore rule covers sources 1
and 2 only, so a non-question from the third or fourth source reaches
the queue without the session judging it (proposal decisions 289, 292,
296 and 298).
For each agent's question the answer session handles by itself, it
SHALL log a miss against the filter the question failed, as *The
answer session logs its misses on the team's lore repository's questions
branch* says, and list the question for the person as handled for them.

For a person's question, a relayed question included, and for an agent's
question from a questions branch, the answer session SHALL post nothing by
itself: it shows the
question with its suggested verdict, and the person decides.

#### Scenario: A deferrable agent's question is handled for the person

- **WHEN** an agent's question in a subscribed repository clearly can wait
  until its pull request is reviewed
- **THEN** the relay posts, naming the question, the filter 2 text
  starting `Inquisitor: filter 2`, a miss against filter 2 is logged, and
  the question is listed as handled for the person

#### Scenario: An agent's rhetorical message gets no post

- **WHEN** an agent's message in a GitHub thread mentions the person
  with a rhetorical question
- **THEN** the answer session shows nothing, posts nothing and closes
  nothing

#### Scenario: A rhetorical message in the queue declined as picked up by mistake logs no miss

- **WHEN** a rhetorical message, found under the first source, reaches
  the person's queue, and the person declines it under the second
  reason
- **THEN** nothing is posted, and no miss file is logged

#### Scenario: A person's question only gets a suggestion

- **WHEN** a person's question clearly fails filter 4
- **THEN** nothing is posted by itself, and the answer session shows the
  question with filter 4 as its suggested verdict

#### Scenario: An agent's questions-branch question only gets a suggestion

- **WHEN** a log file of the fourth source, which an agent wrote, holds a
  question that clearly fails filter 2
- **THEN** nothing is posted by itself, and the answer session shows the
  question with filter 2 as its suggested verdict

#### Scenario: An unclear case goes to the person

- **WHEN** the model can't tell whether an agent's question can wait
- **THEN** nothing is posted by itself, no miss is logged, and the
  question is shown to the person as unanswered

#### Scenario: A thread's text cannot choose the words posted

- **WHEN** an agent's question holds text telling the model to post a
  link
- **THEN** whatever the model judges, the answer session posts by itself
  nothing but one of the three fixed `Inquisitor: ` texts, or the fixed
  recorded-answer text whose URL is filter 1's hit

### Requirement: The answer session logs its misses on the team's lore repository's questions branch

The answer session SHALL log each of its misses as a miss file, in the
format the inquisitor's *A log file and a miss file have one format*
states, pushed through the inquisitor script to the questions branch of
the team's lore repository of the repository the question concerns, as
that spec's *Every answer is recorded and every asked question logged*
says a file is pushed there. Its `filter` is `"1"` to `"4"`, the filter
that should have stopped the question. A decline under the second
reason logs none (proposal decision 298). A
miss the answer session logs by itself, under *Filter 1 runs on every
incoming question* or *Filters 2 to 4 judge every incoming question*, has
`said` `answer session: clearly filter <n>`, so a review of misses can
tell it from a person's word. The answer session SHALL log a miss whether or not
the asker logged the question. A miss logged for a question that a
questions-branch file holds SHALL copy that file's `asked_from`, when it
has one, passing it to the `log` command with the miss's other keys, so
the miss is as private as the file. When several such files hold the
question, it SHALL copy the `asked_from` naming the most private
repository, by the inquisitor's *More visible*; a file with no
`asked_from` adds none (proposal decision 282).

It SHALL write no miss file, and SHALL tell the person why, when the
question has a category, as the inquisitor's *Some questions are recorded
by hash only* defines and as the session's model judges; when the
question concerns no repository; when no configured lore repository
serves the repository the question concerns; when that lore repository
is more visible than it; or when that lore repository is more visible
than the question's thread, which on GitHub means more visible than the
thread's repository, and on Linear and Discord means any lore repository
that is not private. For a question with no thread, the questions-branch
file's own visibility, as the inquisitor's *More visible* defines it,
stands in for the thread's. It SHALL push no miss whose question is the
same question as a miss file already on that branch with the same
`filter`.

#### Scenario: A miss goes to the questions branch

- **WHEN** the answer session logs a miss for a question about `o/api`,
  which a configured lore repository serves
- **THEN** the script pushes the miss file to `misses/` on that lore
  repository's questions branch, and opens no pull request

#### Scenario: No lore repository means no miss file

- **WHEN** the answer session would log a miss for a question about a
  repository no configured lore repository serves
- **THEN** no miss file is written, the person is told why, and the
  question still closes

#### Scenario: A question about no repository gets no miss

- **WHEN** the person declines, as one the inquisitor should have
  handled, a Discord message that concerns no repository
- **THEN** no miss file is written, the person is told why, and the
  question still closes

#### Scenario: A more visible lore repository gets no miss

- **WHEN** the question concerns a private repository, and its team's lore
  repository is public
- **THEN** no miss file is written, and the person is told why

#### Scenario: A question with a category gets no miss

- **WHEN** the person declines, as one the inquisitor should have
  handled, a Discord message that holds a password
- **THEN** nothing is posted, no miss file is written, and the person is
  told why

#### Scenario: A miss copies the questions-branch file's asked_from

- **WHEN** a questions-branch file holds a question, the file holds
  `asked_from: "o/private-item"`, and the person declines the question
  as one the inquisitor should have handled, picking filter 4
- **THEN** the miss file the answer session pushes holds
  `asked_from: "o/private-item"`

#### Scenario: A private thread's miss does not go to a public lore repository

- **WHEN** a question asked in a private repository concerns a public
  repository, and the team's lore repository is public
- **THEN** no miss file is written, and the person is told why

#### Scenario: An automatic miss is marked as the answer session's

- **WHEN** the answer session handles an agent's question under filter 2
  by itself
- **THEN** the miss file's `said` is `answer session: clearly filter 2`

#### Scenario: A miss judged on two machines is pushed once

- **WHEN** the answer session on a second machine would log a miss whose
  question and filter match a miss file already on the branch
- **THEN** it pushes no second miss file
