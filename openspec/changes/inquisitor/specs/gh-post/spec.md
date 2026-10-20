## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-post/`, SHALL tell a hook, for a
tool call, one of three things: the post's body, that the call sends no
post, or that the call is unreadable. prose's posting hook and the
inquisitor's post hook both SHALL use it, and neither SHALL read a post
another way.

For a Bash command, the reader SHALL return a body only when `gh` is the
whole command, with no pipe, `&&`, `;` or other command around it, the command is `gh pr` or `gh issue` with a verb that posts
text (`create`, `new`, `edit`, `comment`, `review`, `revert` for a pull
request, or `close` or `reopen` with a comment), and the body is one of:

- a literal `--body` or `-b`, or `--comment` or `-c` for `close` and
  `reopen`, in single quotes, or in double quotes with no `$`, backtick or
  backslash;
- `--body-file` or `-F` naming a file that exists.

For a GitHub MCP tool, it SHALL return every string under a key named
`body` or `comment`, at any depth, such as each comment of a review.

It SHALL report as sending no post a command in which every simple command
either names no `gh` as a word, so that any `gh` post it mentions is only
data, such as an argument to `echo`, or is a
`gh` command that sends no text: a label, assignee, reviewer or milestone
edit, `gh pr ready`, a close without `--comment`, or a read such as
`gh pr list`. It SHALL report as unreadable any other command that mentions
a `gh` post verb, and any command it cannot read exactly, such as one with
a backtick, `$'…'` or an unterminated quote.

#### Scenario: A whole-command post with a body file is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md`,
  and `body.md` exists
- **THEN** the reader returns the file's text as the body

#### Scenario: A command that sends no body is no post

- **WHEN** a hook asks about `gh pr edit 5 --add-label spec`
- **THEN** the reader reports that the command sends no post

#### Scenario: A body built by the shell is unreadable

- **WHEN** a hook asks about `gh pr comment 5 --body "$(cat body.md)"`
- **THEN** the reader reports the command as unreadable

### Requirement: The reader reads posts sent through the github-app skill and gh api

Beyond the forms above, the reader SHALL read:

- a post sent through the github-app skill's script, as
  `python3 <github-app script> gh pr|issue …` or
  `python3 <github-app script> run -- gh pr|issue …`, with the script's path
  written out literally or as the shell variable `$G` the github-app skill
  sets, by the same rules as the `gh` command it runs;
- a `gh api` call that writes to an issue, pull request, comment or review
  endpoint, whose text is given by a `body` field through `-f`,
  `--raw-field`, `-F` or `--field` (`-F` and `--field` also read
  `@<file>`), or by `--input` naming a JSON file with a `body` key.

A `gh api` call writes when its method is `POST`, `PATCH` or `PUT`, given
by `-X` or `--method`, or implied by fields or `--input` with no `-X GET`;
a GraphQL call writes when its query is a mutation. The reader SHALL
report as unreadable a GraphQL mutation, whose text sits inside its query;
a write to any other endpoint whose fields include `body`; and a write
whose fields it cannot read. It SHALL report as sending no post any other
write whose fields carry no `body`.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --body-file body.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: Each gh api body form is read

- **WHEN** a hook asks about an issue comment sent with `gh api`, its body
  given by `-f body=…`, `--raw-field body=…`, `-F body=@c.md` or
  `--input c.json`
- **THEN** the reader returns the body, for each of the four forms

#### Scenario: A gh api write whose body can't be read is unreadable

- **WHEN** a hook asks about `gh api graphql -f query='mutation { … }'`
- **THEN** the reader reports the command as unreadable

#### Scenario: A gh api read is no post

- **WHEN** a hook asks about `gh api graphql -f query='{ viewer { login } }'`
  or `gh api -X GET search/issues -f q=x`
- **THEN** the reader reports that the command sends no post

#### Scenario: A review's nested comments are read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds
  `comments[0].body`
- **THEN** the reader returns that string as a body

#### Scenario: The run form of the github-app script is read

- **WHEN** a hook asks about `python3 "$G" run -- gh pr comment 5
  --body-file c.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: A close with a comment is read

- **WHEN** a hook asks about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `done` as the body
