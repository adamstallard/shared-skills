## ADDED Requirements

### Requirement: The reader reads linear-app's post and edit only from a body file

The reader (*The shared post reader reads a post's body from an
allow-list*) SHALL find a call of `linear_app.py` in the forms *The
reader reads posts sent through the github-app skill* lists, and read it only as `post` or `edit` with
`--body-file <file>` given once, the file the next word and an existing
regular file, other options anywhere (*The reader reads a post only in a
canonical form*). The reader SHALL report the file's text as a Linear
message's body.

#### Scenario: A Linear post or edit is read from its file

- **WHEN** a hook asks about `python3 /abs/linear_app.py --identity
  answers-bot post --issue ENG-5 --body-file c.md`, and about the same
  call with `edit --comment 9` in place of `post --issue ENG-5`, where
  `c.md` holds `User says: yes`
- **THEN** the reader returns `User says: yes` as each one's body, as a
  Linear message, so the inquisitor's post hook blocks each, since the
  body starts with the reserved prefix `User says: ` (answer-service's
  *Relay posts start with a reserved prefix*)
- **AND** it reports the same `post` call with `cd x && ` before it as
  unreadable, as *The reader reads a post only in a canonical form* says

#### Scenario: A Linear comment given any other way is unreadable

- **WHEN** a hook asks about `python3 /abs/linear_app.py post --issue
  ENG-5 --body c.md`, about `python3 /abs/linear_app.py post --issue
  ENG-5 --body-file=c.md`, about `printf 'User says: yes' | python3
  /abs/linear_app.py post --issue ENG-5 --body-file /dev/stdin`, whose
  `/dev/stdin` is no regular file, and
  about `python3 -m linear_app post --issue ENG-5 --body-file c.md`,
  whose `linear_app` is a module name, not a path to the script
- **THEN** the reader reports each command as unreadable

#### Scenario: A Linear delete or check is no post

- **WHEN** a hook asks about `python3 /abs/linear_app.py delete --comment
  9` and `python3 /abs/linear_app.py check`
- **THEN** the reader reports that each command sends no post

### Requirement: A simple command holding a linear-app post word counts as naming gh

A simple command (*The reader splits a command line into simple
commands*) holding a word, inside quotes or not, that is
`linear_app` or ends in `linear_app.py`, followed later by `post` or `edit`, SHALL count as
holding the word `gh`. Without this rule, a
linear-app call the reader does not find, such as inside `sh -c`, would
fall under the rules by which a command naming no `gh` sends no post;
counted as naming `gh`, it must be read, and the reader reports it
unreadable, so the hooks block it.

#### Scenario: A linear-app post outside the reader's form is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/linear_app.py post
  --issue ENG-5 --body-file c.md'`, and about `/abs/linear_app.py post
  --issue ENG-5 --body-file c.md`, run without `python3`, a form *The
  reader reads posts sent through the github-app skill* does not find
- **THEN** the reader reports each command as unreadable, so the post
  hooks block it

## MODIFIED Requirements

### Requirement: A command mentions a gh post verb by one of a closed list of word sequences

A command SHALL **mention** a gh post verb when its text holds any of:

- `gh`, then `pr` or `issue`, then a post verb listed for that word;
- `gh`, then `api`, unless the line is a read (*A gh api call is a read
  only in a plain form*);
- a word that is `discord_bot` or ends in `discord_bot.py`, then a
  discord-bot post word;
- a word that is `linear_app` or ends in `linear_app.py`, then `post` or
  `edit`.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call that is not a read; a discord-bot `post`, `edit` or `thread`
  call; and a linear-app `post` or `edit` call, though such a call holds
  no gh word
- **AND** a command's words count whether quoted or not, and `gh`, `pr`,
  `issue`, `api` and each verb count only as whole
  words, with no letter, digit or `_` just before and no letter, digit,
  `_` or `-` just after, so `--comments` holds no `comment` and
  `--comment` holds one; and `api` counts only with no `/` or `.` just
  before or after it, so `gh repo view o/api` mentions no post verb
