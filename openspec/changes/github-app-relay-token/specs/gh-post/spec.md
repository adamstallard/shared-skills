## ADDED Requirements

### Requirement: The reader reads the github-app skill's api command as gh api

The shared post reader SHALL read a github-app `api` call as the `gh api`
call with the same arguments, under every rule of this spec for a `gh
api` call, so a github-app `api` call is a canonical post exactly when
that `gh api` call is one. The reader finds such a call as it finds any
github-app call (*The reader reads posts sent through the github-app
skill*).

#### Scenario: A canonical post through the api command is read

- **WHEN** a hook asks about `python3 /abs/github_app.py --identity
  maya-relay api repos/o/r/issues/5/comments -X POST --input c.json`,
  where `c.json` holds `{"body": "User says: yes"}`
- **THEN** the reader returns `User says: yes` as its body, sent through
  the github-app skill

#### Scenario: A read through the api command is no post

- **WHEN** a hook asks about `G=/abs/github_app.py; python3 "$G" api
  repos/o/r/pulls/5`
- **THEN** the reader reports that the command sends no post

#### Scenario: An api write in any other form is unreadable

- **WHEN** a hook asks about `python3 /abs/github_app.py api
  repos/o/r/issues/5/comments -f body='User says: yes'`, about `python3
  /abs/github_app.py api -X DELETE repos/o/r/issues/comments/9`, and
  about `cd x && python3 /abs/github_app.py api
  repos/o/r/issues/5/comments -X POST --input c.json`, where `c.json`
  exists
- **THEN** the reader reports each command as unreadable, as it does the
  same line with `gh api`: the first two are no canonical `gh api` post,
  and the third chains a post to another command (*The reader reads a
  post only in a canonical form*)

### Requirement: A simple command holding an api word counts as naming gh

An **api word** SHALL be an `api` after a word ending in
`github_app.py`, or after a word that is not literal (*A literal word is
one the shell does not expand*) in a simple command run by `python`,
`python3` or a path ending in either, with no word between the two but
an `--identity` option and its value. A simple command holding one SHALL
count as holding the word `gh`, so the rules that clear a command for
naming no `gh` never clear it.

#### Scenario: An api call outside the github-app skill's form is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/github_app.py api
  repos/o/r/issues/5/comments -X POST --input c.json'`, about `python3
  "$G" api repos/o/r/issues/5/comments -X POST --input c.json` where the
  command assigns `G` nowhere, about `python -u "$G" api repos/o/r/issues/5/comments -X POST --input
  c.json`, also assigning `G` nowhere, and about
  `/abs/github_app.py --identity
  maya-relay api repos/o/r/issues/5/comments -X POST --input c.json`,
  where `c.json` exists
- **THEN** the reader reports each command as unreadable, so the post
  hooks block it: none is the form *The reader reads posts sent through
  the github-app skill* finds, the first being run by `sh`, the second
  and third naming no script, and the fourth run without `python3`

## MODIFIED Requirements

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(its first scenario lists them), unless input within
the line reaches a `gh` command (*Input to a no-post line reaches only
data commands*). It mentions one when its text holds any of these, each word anywhere
after the one before it:

- `gh`, then `pr` or `issue`, then a post verb listed for that word;
- `gh`, then `api`, unless the line is a read (*A gh api call is a read
  only in a plain form*);
- an **api word** (*A simple command holding an api word counts as
  naming gh*), unless its call is a read;
- a word ending in `discord_bot.py`, then `post` or `edit`.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call or a github-app `api` call that is not a read; and a discord-bot
  `post` or `edit` call, though such a call holds no gh word
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
  hooks let it through unread

#### Scenario: A gh api read piped into a script is no post

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5 | python3 -c
  'import json, sys; print(json.load(sys.stdin)["title"])'`, or the same
  pipe with `python3 /abs/github_app.py gh api repos/o/r/pulls/5` or
  `python3 /abs/github_app.py api repos/o/r/pulls/5` as its first command
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb, so the line mentions none and no rule for a
  post-verb line applies
