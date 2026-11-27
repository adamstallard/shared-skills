## ADDED Requirements

### Requirement: The reader reads linear-app's post and edit as gh issue comment

The shared post reader SHALL find a `linear_app.py` call the same way
`app_command` in `.agents/lib/gh-shell/gh_shell.py` finds a github-app
call: `python` or `python3` running the script by a literal path or a
variable the line assigns. It SHALL judge a line with a call running
`post` or `edit` as if a `gh issue comment` call with the same
`--body-file` stood in its place, under every rule this spec sets for
that `gh issue comment` call, and SHALL report the post as going to
Linear.

#### Scenario: A Linear post or edit is read from its file

- **WHEN** a hook asks about `python3 /abs/linear_app.py --identity
  answers-bot post --issue ENG-5 --body-file c.md`, and about the same
  call with `edit --comment 9` in place of `post --issue ENG-5`, where
  `c.md` holds `User says: yes`
- **THEN** the reader returns `User says: yes` as each one's body, and
  reports each post as going to Linear; the inquisitor's post hook
  blocks each, since its body starts with the reserved prefix
  `User says: `
- **AND** it reports the same call after `cd x && ` as unreadable, since
  the line is not the call alone, so the hook blocks it, as *The reader
  reads a gh pr or gh issue post only as a whole command line* says for
  `gh issue comment`

#### Scenario: A Linear delete is no post

- **WHEN** a hook asks about `python3 /abs/linear_app.py delete --comment
  9`
- **THEN** the reader reports that the command sends no post

### Requirement: A simple command holding a linear-app post word counts as naming gh

A **linear-app post word** SHALL be a `post` or `edit`, in the command's
text quoted or not, that is the first word, other than an `--identity` option and its value, after a word
ending in `linear_app.py`, or after `python` or `python3` and a word
that is not literal (*A literal word is one the shell does not expand*).
A simple command holding one SHALL count as holding the word `gh`, so
the rules that let through a command naming no `gh` do not let it
through.

#### Scenario: A linear-app post in a form the reader does not find is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/linear_app.py post
  --issue ENG-5 --body-file c.md'`, `python3 "$L" post --issue ENG-5
  --body-file c.md` with `L` assigned nowhere, and `/abs/linear_app.py
  post --issue ENG-5 --body-file c.md`
- **THEN** the reader reports each as unreadable, so both post hooks,
  prose's and the inquisitor's, block it

## MODIFIED Requirements

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(scenario *The gh post verbs are a closed list*). It mentions one when its
text, quoted or not, holds `gh` followed later by `pr` or `issue` and
later by a post verb listed for that word, or holds a `gh api` call that
is not a read (*A gh api call is a read only as a plain gh command*), or
holds a linear-app post word (*A simple command holding a linear-app
post word counts as naming gh*).

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call that can write; and a linear-app post word, which counts as a gh
  post verb though it holds no gh word
- **AND** `gh`, `pr`, `issue`, `api` and each verb count only as whole
  words, with no letter, digit or `_` just before and no letter, digit,
  `_` or `-` just after, so `--comments` holds no `comment` and
  `--comment` holds one
- **AND** of these, the verbs that post text are `create`, `new`, `edit`,
  `comment`, `review` and `revert`, and `close` or `reopen` given
  `--comment` or `-c`, and a linear-app post word; `close`
  or `reopen` without `--comment` or `-c` still mentions a post verb but
  sends no text

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
  pipe with `python3 /abs/github_app.py gh api repos/o/r/pulls/5` as its
  first command
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb, so the line mentions none and no rule for a
  post-verb line applies
