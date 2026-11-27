## MODIFIED Requirements

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

- **WHEN** the person relays an answer to a Linear question and later
  edits it; separately, the service deletes one of its own automatic
  Linear posts (*An automatic post is deleted when another relay post
  came first*)
- **THEN** the answer service posts the answer with linear-app's `post`,
  edits it with `edit` and deletes the automatic post with `delete`, each
  post's or edit's text in a private file named by `--body-file`, and no
  request the service makes itself holds the relay's token

### Requirement: The README warns that a relay's token can be printed

While github-app hands a relay identity's token to a command that can
print it, the inquisitor's README SHALL say that any agent on the person's
machine can print that token and post `User says: ` unseen by the post
hooks. No linear-app command prints a relay identity's token (linear-app
spec: *No command prints a relay identity's token*), so this warning,
which is about a printed token, does not cover Linear.

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
