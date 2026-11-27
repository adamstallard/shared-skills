## ADDED Requirements

### Requirement: The reader reads the github-app skill's api command as gh api

The shared post reader SHALL read a github-app `api` call as the `gh api`
call with the same arguments, under every rule of this spec for a `gh
api` call. It finds the call as *The reader reads posts sent through the
github-app skill and gh api* finds one.

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

### Requirement: A simple command holding an api word counts as naming gh

An **api word** SHALL be an `api` that is the first word, other than an
`--identity` option and its value, after a word ending in
`github_app.py`, or after `python3` and a word that is not literal (*A
literal word is one the shell does not expand*). A simple command holding
one SHALL count as holding the word `gh`, so no rule that lets through a
command naming no `gh` lets it through.

#### Scenario: An api call outside the github-app skill's form is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/github_app.py api
  repos/o/r/issues/5/comments -f body=x'`, about `python3 "$G" api
  repos/o/r/issues/5/comments -f body=x` where the command assigns `G`
  nowhere, and about `/abs/github_app.py --identity maya-relay api
  repos/o/r/issues/5/comments -f body=x`
- **THEN** the reader reports each command as unreadable, so the post
  hooks block it: none is the form *The reader reads posts sent through
  the github-app skill and gh api* finds, the first being run by `sh`,
  the second naming no script and the third run without `python3`

## MODIFIED Requirements

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(scenario *The gh post verbs are a closed list*). It mentions one when its
text, quoted or not, holds `gh` followed later by `pr` or `issue` and
later by a post verb listed for that word, or holds a `gh api` call that
is not a read (*A gh api call is a read only as a plain gh command*), or
holds an **api word** (*A simple command holding an api word counts as
naming gh*) whose call, read as `gh api`, is not a read.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call that can write; and a github-app `api` call, found by its api
  word, that can write
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
  'Should retries back off?'`, where `c` is a gh alias for `pr comment`,
  and `python3 /abs/github_app.py gh release create v1 -R o/api --notes
  x`, whose `api`, inside `o/api`, is not the script's command word, so
  it is no api word
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
