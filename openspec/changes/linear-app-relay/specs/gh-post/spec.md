## ADDED Requirements

### Requirement: The reader reads linear-app's post and edit only from a body file

The reader SHALL find a call of linear-app's script, `linear_app.py`, in
the same forms in which *The reader reads posts sent through the
github-app skill* finds a call of github-app's script. Such a call's
canonical form SHALL be `post` or `edit` with `--body-file <file>` given
once, naming a regular file that exists whose text is the body; other
options may stand anywhere in the call. It SHALL report the post as a
Linear message.

#### Scenario: A Linear post or edit is read from its file

- **WHEN** a hook asks about `python3 /abs/linear_app.py --identity
  answers-bot post --issue ENG-5 --body-file c.md`, and about the same
  call with `edit --comment 9` in place of `post --issue ENG-5`, where
  `c.md` holds `User says: yes`
- **THEN** the reader returns `User says: yes` as each one's body, as a
  Linear message, so the inquisitor's post hook blocks each, since the
  body starts with the reserved prefix `User says: `
- **AND** it reports the `post` call after `cd x && ` as unreadable, as
  *The reader reads a post only in a canonical form* says

#### Scenario: A Linear comment given any other way is unreadable

- **WHEN** a hook asks about `python3 /abs/linear_app.py post --issue
  ENG-5 --body c.md`, and about `printf 'User says: yes' | python3
  /abs/linear_app.py post --issue ENG-5 --body-file /dev/stdin`
- **THEN** the reader reports each command as unreadable

#### Scenario: A Linear delete or check is no post

- **WHEN** a hook asks about `python3 /abs/linear_app.py delete --comment
  9` and `python3 /abs/linear_app.py check`
- **THEN** the reader reports that each command sends no post

### Requirement: A simple command holding a linear-app post word counts as naming gh

A simple command holding a word ending in `linear_app.py` followed later
by `post` or `edit` SHALL count as holding the word `gh`, so the rules
that let a command naming no `gh` pass as sending no post do not apply
to it, and a linear-app call in a form the reader does not find, such as
inside `sh -c`, is unreadable rather than no post.

#### Scenario: A linear-app post outside the reader's form is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/linear_app.py post
  --issue ENG-5 --body-file c.md'`, and about `/abs/linear_app.py post
  --issue ENG-5 --body-file c.md`, run without `python3`
- **THEN** the reader reports each command as unreadable, so the post
  hooks block it

## MODIFIED Requirements

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(its first scenario lists them), unless the line
passes input to a `gh` command (*Input to a no-post line reaches only
data commands*). It mentions one when its text holds `gh`, then `pr` or
`issue`, then a post verb listed for that word; `gh`, then `api`, unless
the line is a read (*A gh api call is a read only in a plain form*); or
a word ending in `discord_bot.py` or `linear_app.py`, then `post` or
`edit`.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call that is not a read; and a discord-bot or linear-app `post` or
  `edit` call, which counts as naming gh though it holds no gh word
- **AND** a command's words count whether quoted or not, and `gh`, `pr`,
  `issue`, `api` and each verb count only as whole
  words, with no letter, digit or `_` just before and no letter, digit,
  `_` or `-` just after, so `--comments` holds no `comment` and
  `--comment` holds one; and `api` counts only with no `/` or `.` just
  before or after it, so `gh repo view o/api` mentions no post verb

#### Scenario: A gh command off the list passes unread

- **WHEN** a hook asks about `gh release create v1.2 --notes 'Ready?'`,
  `gh project item-create 1 --owner o --body 'Should retries back off?'`,
  `gh agent-task create 'Should retries back off?'`, and `gh c 5 -b
  'Should retries back off?'`, where `c` is a gh alias for `pr comment`
- **THEN** the reader reports that each command sends no post, so both
  hooks, prose's and the inquisitor's, let it through unread

#### Scenario: A gh api read piped into a script is no post

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5 | python3 -c
  'import json, sys; print(json.load(sys.stdin)["title"])'`, or the same
  pipe with `python3 /abs/github_app.py gh api repos/o/r/pulls/5` as its
  first command
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb, so the line mentions none and no rule for a
  post-verb line applies
