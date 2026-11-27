## MODIFIED Requirements

### Requirement: Setup checks each relay identity before its channels are used

Setup SHALL check, showing failures and fixes: each relay identity by
its skill's check; on Discord, that `messageContent` is `true`; on
Linear, that linear-app's `check` reports `relay` as `true`; and posting
in each subscribed channel. The Linear check's fix SHALL be adding
`"relay": true` to that identity's linear-app config, because linear-app's
`token` and `headers` print an unmarked identity's token. A channel is **on** while its
identity and posting checks last passed, else **off**. A channel whose
posting permission no check can read SHALL count as on, shown
not checked, until a post there is refused for permission. An off
channel SHALL not be read or posted in; each opening of the answer service SHALL rerun
failed and unrun checks.

#### Scenario: Refused member search does not fail setup

- **WHEN** discord-bot's `check` reports `messageContent` as `true` and
  `memberSearch`, whether the bot may look up members to mention them, as
  `false`, and every other check passes
- **THEN** setup counts the Discord relay's check as passed

#### Scenario: A channel the relay cannot post in is off alone

- **WHEN** setup finds that the Discord relay cannot post in one of two
  subscribed Discord channels, and can post in the other
- **THEN** setup shows the failure and its fix, saves both channels, and
  the answer service reads and posts in the other channel only

#### Scenario: A failed identity check turns off its whole surface

- **WHEN** the GitHub relay's own github-app check fails
- **THEN** every subscribed GitHub channel stays off

#### Scenario: A relay that cannot read message content keeps Discord off

- **WHEN** discord-bot's `check` reports, for the Discord relay,
  `messageContent` as `false`, or as `null` when it could not read the
  bot's application flags
- **THEN** setup says to turn on the bot's Message Content intent, or why
  the check could not read it, and every Discord channel stays off
- **AND** only `messageContent` as `true` passes, whatever `check`
  reports as `memberSearch`

#### Scenario: A posting check no check can read is shown as not checked

- **WHEN** no check can read whether the Linear relay may post in a
  subscribed team, and the relay's own check passes
- **THEN** setup shows the team's posting check as not checked, never as
  passed, and the team counts as on
- **AND** once Linear refuses a relay post there for lack of permission,
  the refusal counts as a failed posting check: the post is handled as *A failed relay post is
  reported to the person* says, and the team stays off until the next
  opening

#### Scenario: An opening reruns a failed check

- **WHEN** a Discord channel is off because its posting check failed, and
  at the next opening that check passes
- **THEN** the channel is on, and the answer service reads and posts in it

#### Scenario: An unmarked Linear relay keeps Linear off

- **WHEN** linear-app's `check` passes for the identity `inquisitor.json`
  names as the Linear relay but reports `relay` as `false`
- **THEN** setup shows the Linear relay's check as failed, with the fix,
  and every Linear channel stays off

### Requirement: A relay post is posted by a host command, unvetted

The answer service SHALL post by a host command, never the model's tool
call: the relay's skill, run as an argument vector with no shell, the
text on standard input or in a private file. On Linear that skill is
linear-app, whose `post`, `edit` and `delete` commands the service uses,
so the service never holds the relay's token. Neither prose's pass nor the inquisitor's filters SHALL apply to a relay
post. The answer service SHALL scan each relay post for the patterns of
the inquisitor's *The credential patterns are a closed list of token
shapes* and post none that matches.

#### Scenario: A relay post carries no prose footer and is not vetted

- **WHEN** the person relays an answer that holds a question, which the
  inquisitor's filters would vet in an agent's post
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

- **WHEN** the person's answer, or their edit of a relay post, holds a
  string shaped like a GitHub access token
- **THEN** nothing is posted or changed, and the person is told why

#### Scenario: A Linear relay post goes through linear-app

- **WHEN** the person relays an answer to a Linear question, and later
  edits it, and the service deletes an automatic Linear post
- **THEN** the answer service posts the answer with linear-app's `post`,
  edits it with `edit` and deletes the automatic post with `delete`, the
  text on standard input, and no command or
  request of the service's own holds the relay's token

### Requirement: The README warns that a relay's token can be printed

While github-app hands a relay identity's token to a command that can
print it, the inquisitor's README SHALL say that any agent on the person's
machine can print that token and post `User says: ` unseen by the post
hooks. It SHALL give no such warning for Linear: linear-app prints no
marked relay's token, and setup keeps Linear off until the Linear relay
is marked.

#### Scenario: The README warns that a relay's token can be printed

- **WHEN** a test reads the README while a github-app command, such as
  `token`, can print a relay identity's token
- **THEN** it says, for GitHub, that any agent on the person's machine can
  print that token and post `User says: ` unseen by the post hooks
- **AND** it gives no such warning for Linear

## REMOVED Requirements

### Requirement: The Linear relay's token stays in memory

**Reason**: The answer service no longer holds the Linear relay's token:
it posts, edits and deletes through linear-app's commands, which hand the
token to nothing that can print it.

**Migration**: *A relay post is posted by a host command, unvetted* covers
Linear posts, and linear-app's spec covers the token.
