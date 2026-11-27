## ADDED Requirements

### Requirement: The reader reads the github-app skill's api command as gh api

The shared post reader SHALL judge a call of the github-app skill's
script, found as *The reader reads posts sent through the github-app
skill and gh api* finds one, with the `api` command as the `gh api` call with the same
arguments standing in its place, under every rule of this spec for a
`gh api` call.

#### Scenario: A post through the api command is read

- **WHEN** a hook asks about `python3 /abs/github_app.py --identity
  maya-relay api repos/o/r/issues/5/comments -f body='User says: yes'`
- **THEN** the reader returns `User says: yes` as its body

#### Scenario: A read through the api command is no post

- **WHEN** a hook asks about `G=/abs/github_app.py; python3 "$G" api
  repos/o/r/pulls/5`
- **THEN** the reader reports that the command sends no post

#### Scenario: An api body file after another command is unreadable

- **WHEN** a hook asks about `cd x && python3 /abs/github_app.py api
  repos/o/r/issues/5/comments -F body=@c.md`, where `c.md` exists, so a
  missing file is not what blocks it
- **THEN** the reader reports the command as unreadable, as it does the
  same line with `gh api` (*A gh api write read from a file is read only
  as a whole command line*)

## MODIFIED Requirements

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(scenario *The gh post verbs are a closed list*). It mentions one when its
text, quoted or not, holds `gh` followed later by `pr` or `issue` and
later by a post verb listed for that word, or holds a `gh api` call that
is not a read (*A gh api call is a read only as a plain gh command*), or
a github-app `api` call that is not a read (*The reader reads the
github-app skill's api command as gh api*).

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; and a `gh api`
  call or a github-app `api` call that can write
- **AND** `gh`, `pr`, `issue`, `api` and each verb count only as whole
  words, with no letter, digit or `_` just before and no letter, digit,
  `_` or `-` just after, so `--comments` holds no `comment` and
  `--comment` holds one
- **AND** of these, the verbs that post text are `create`, `new`, `edit`,
  `comment`, `review` and `revert`, and `close` or `reopen` given
  `--comment` or `-c`; `close` or `reopen` without one still mentions a
  post verb but sends no text

#### Scenario: A gh command off the list passes unread

- **WHEN** a hook asks about `gh release create v1.2 --notes 'Ready?'`,
  `gh project item-create 1 --owner o --body 'Should retries back off?'`,
  `gh agent-task create 'Should retries back off?'`, and `gh c 5 -b
  'Should retries back off?'`, where `c` is a gh alias for `pr comment`
- **THEN** the reader reports that each command sends no post, so both
  post hooks, prose's and the inquisitor's, let it through unread

#### Scenario: A gh api read piped into a script is no post

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5 | python3 -c
  'import json, sys; print(json.load(sys.stdin)["title"])'`, or the same
  pipe with `python3 /abs/github_app.py gh api repos/o/r/pulls/5` or
  `python3 /abs/github_app.py api repos/o/r/pulls/5` as its first command
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb, so the line mentions none and no rule for a
  post-verb line applies
