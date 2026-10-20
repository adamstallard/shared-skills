## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-post/`, SHALL tell a hook, for a
tool call, one of three things: the post's body, with whether the post
creates an issue; that the call sends no post; or that the call is
unreadable. prose's posting hook and the inquisitor's post hook both SHALL
use it, and neither SHALL read a post another way.

**A gh post verb** is one of a closed list, the one prose's reader
handles: `gh pr` with `create`, `new`, `edit`, `comment`, `review`,
`revert`, `close` or `reopen`; `gh issue` with `create`, `new`, `edit`,
`comment`, `review`, `close` or `reopen`; and `gh api`, whose writes the
next requirement defines. A command **mentions a gh post verb** when its
text, inside quotes or not, holds the word `gh` followed later by `pr` or
`issue` and later by one of their verbs, or `gh` followed by `api`.

For a Bash command, apart from the forms the next requirement adds, the
reader SHALL return a body only when the whole command line is one `gh`
command, with no pipe, `&&`, `;` or other command around it; that command
is `gh pr` or `gh issue` with a verb that posts text (`create`, `new`,
`edit`, `comment` or `review`; `revert`, for a pull request only; or
`close` or `reopen` with a comment); and the body is one of:

- a literal `--body` or `-b`, or `--comment` or `-c` for `close` and
  `reopen`, in single quotes, or in double quotes with no `$`, backtick or
  backslash;
- `--body-file` or `-F` naming a file that exists.

With the body, it SHALL say that the post creates an issue when the command
is `gh issue create` or `gh issue new`.

For a GitHub MCP tool, it SHALL return every string under a key named
`body` or `comment`, at any depth, such as each comment of a review. It
SHALL say that the post creates an issue when the tool creates one, such
as `create_issue`, or `issue_write` with the `method` `create`.

A command that mentions no gh post verb sends no post. Nor does a command
that runs prose's script and nothing else, whatever its arguments say: a
single simple command whose command is `prose.py` or a path ending in
`/prose.py`, or `python3` or `python` followed directly by such a path,
with no option between them.

A **simple command** is one command with its arguments, as the shell splits
a command line at `|`, `|&`, `||`, `&&`, `;`, `&` and line breaks, with
each unquoted `$(…)` read as more commands; a `$(…)` inside double quotes
makes the command line unreadable. Its command is its first word
after any leading `if`, `then`, `elif`, `else`, `do`, `while`, `until`, `!`,
`{` or `time`. The finer points of this reading, such as heredocs, comments
and line continuations, are those prose's reader follows today, as prose's
`DECISIONS.md` records under *A command that runs no gh post is not a
post*.

In a command that mentions a gh post verb, the reader SHALL judge each
simple command:

- a `gh` command that sends no text is no post: a label, assignee,
  reviewer or milestone edit, `gh pr ready`, a close without `--comment`,
  or a read such as `gh pr list`;
- a simple command that holds `gh` as a word of its own, or a path ending
  in `/gh`, anywhere but as its command, such as `echo gh pr create` or
  `xargs gh pr comment`, is unreadable, except the github-app skill's form
  that the next requirement reads;
- a simple command that names `gh` only inside a longer word, such as a
  quoted argument, is no post only when its command is one of prose's data
  commands: `echo`, `cat`, `tee`, `grep`, `egrep`, `fgrep`, `rg`, `git`,
  `python`, `python3`, `node`, `jq`, `head`, `tail`, `wc`, `sort`, `uniq`,
  `cut`, `tr`, `ls`, `cd`, `true` or `false`. Any other, such as
  `sh -c '…'`, `bash -c '…'` or `eval '…'` around a `gh` post, is
  unreadable. The list is prose's as it stands, though `python3 -c`,
  `node -e` and `git -c` could run a quoted `gh` post as `sh -c` does;
- a simple command that names no `gh` at all is no post.

A pipe or an input redirection (`|`, `|&`, `<`, `<>`, `<&`, a heredoc or
`<<<`) matters for the simple command that reads it. That command SHALL be
a data command or a `gh` command that sends no text and is not a gh post
verb, or the command is unreadable, so `echo 'gh pr comment 5 -b x' | sh`
and `cat c.md | gh pr comment 5 -F -` are unreadable. When the input can
reach more than one simple command, such as a pipe into `(`, `$(`, `{` or
`while`, every one of them SHALL be a data command, or the whole command
line is unreadable.

A command line sends no post when every simple command in it is no post.
The reader SHALL report as unreadable every other command line that
mentions a gh post verb, except one it returns a body for under the rules
above or the next requirement's, and any such command line it cannot read
exactly, such as one with a backtick, `$'…'` or an unterminated quote.

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

#### Scenario: A gh post run through another shell is unreadable

- **WHEN** a hook asks about `sh -c 'gh pr comment 5 --body-file c.md'`,
  `bash -c 'gh issue create -b x'` or `eval 'gh pr comment 5 -b x'`
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh post piped into a shell is unreadable

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | sh`
- **THEN** the reader reports the command as unreadable

#### Scenario: A command the reader can't read exactly is unreadable

- **WHEN** a hook asks about ``gh pr comment 5 -b `cat c.md` ``, or about
  `gh pr comment 5 -b $'x'`
- **THEN** the reader reports each command as unreadable

#### Scenario: A command that only runs prose is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post

#### Scenario: prose run through `python` is no post

- **WHEN** a hook asks about `python prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post

#### Scenario: A gh post quoted as data is no post

- **WHEN** a hook asks about `echo 'run gh pr create next'`
- **THEN** the reader reports that the command sends no post

#### Scenario: A new issue is reported as one

- **WHEN** a hook asks about `gh issue create --title t --body-file b.md`,
  and `b.md` exists
- **THEN** the reader returns the file's text as the body, and says that
  the post creates an issue

### Requirement: The reader reads posts sent through the github-app skill and gh api

Beyond the forms above, the reader SHALL read:

- a post sent through the github-app skill's script, as
  `python3 <github-app script> gh pr|issue …` or
  `python3 <github-app script> run -- gh pr|issue …`, optionally with
  `--identity <name>` before `gh` or `run`, by the same rules as the `gh`
  command it runs. The script's path is a literal path ending in
  `/github_app.py`, written out, or as `$G` or `"$G"`, the shell variable
  the github-app skill sets, when the same command first assigns `G` such
  a path, as `G=<path>;` or `G=<path> &&`, and nothing else comes before
  the `python3`. A script at any other path is not this form;
- a `gh api` call that writes an issue, a pull request, a comment or a
  review, at an endpoint under `repos/<owner>/<repo>/issues` or
  `repos/<owner>/<repo>/pulls`, with or without a leading `/`, and with
  `{owner}` and `{repo}`, the placeholders `gh` fills in, counting as an
  owner and a repository, whose text is given by a `body` field through `-f`,
  `--raw-field`, `-F` or `--field` (`-F` and `--field` also read
  `@<file>`), or by `--input` naming a JSON file with a `body` key. For a
  write to a pull request's reviews, `repos/<owner>/<repo>/pulls/<n>/reviews`,
  it SHALL also return each `comments[][body]` field, given the same ways,
  and each `body` in the `comments` array of an `--input` file. It SHALL
  say that the post creates an issue when the call is a `POST` to
  `repos/<owner>/<repo>/issues`;
- a `gh api graphql` call whose query holds a mutation that posts text to
  an issue or pull request: `addComment`, `addPullRequestReview`,
  `addPullRequestReviewComment`, `addPullRequestReviewThread`,
  `addPullRequestReviewThreadReply`, `submitPullRequestReview`,
  `createIssue`, `createPullRequest`, `updateIssue`, `updateIssueComment`,
  `updatePullRequest`, `updatePullRequestReview` or
  `updatePullRequestReviewComment`. The reader SHALL return every `body`
  argument in that mutation's input, at any depth, such as each thread's
  `body` in an `addPullRequestReview`, whether it is a string literal in
  the query or a variable whose value the call gives through `-f`,
  `--raw-field`, `-F` or `--field` (`-F` and `--field` also read
  `@<file>`), or in the `variables` of an `--input` file. It SHALL say that
  the post creates an issue when the mutation is `createIssue`.

A command that runs `python3 $G` or `python3 "$G"`, mentions a gh post
verb, and assigns `G` nowhere earlier in the same command SHALL be reported as
unreadable, and the hook's block message SHALL say to set `G` in the same
command or to write the script's path out.

A `gh api` call writes when its method is `POST`, `PATCH` or `PUT`, given
by `-X` or `--method`, or implied by fields or `--input` with no `-X GET`;
a GraphQL call writes when its query is a mutation. The reader SHALL
report as unreadable a write to any other endpoint whose fields include
`body`; any other GraphQL mutation that has a `body` argument; a listed
mutation one of whose `body` arguments it cannot read; a GraphQL query it
cannot parse; a review whose comment bodies it cannot read; and a write
whose fields it cannot read. It SHALL report as sending no post any other
write whose fields carry no `body`, and any mutation, listed or not, with
no `body` argument. The reader returns no title: a question in an issue's
or pull request's title is out of its reach, as it is out of prose's.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --body-file body.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: Each gh api body form is read

- **WHEN** a hook asks about an issue comment sent with `gh api`, its body
  given by `-f body=…`, `--raw-field body=…`, `-F body=@c.md` or
  `--input c.json`
- **THEN** the reader returns the body, for each of the four forms

#### Scenario: Another script given gh's arguments is unreadable

- **WHEN** a hook asks about `python3 /tmp/other.py gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports the command as unreadable

#### Scenario: The github-app script with an identity is read

- **WHEN** a hook asks about `G=/abs/github_app.py && python3 "$G"
  --identity bot gh pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: A new issue sent through gh api or MCP is reported as one

- **WHEN** a hook asks about `gh api repos/o/r/issues -f title=t -f
  body=b`, or about a GitHub MCP `create_issue` call with the `body` `b`
- **THEN** the reader returns `b` as the body, and says that the post
  creates an issue

#### Scenario: A GraphQL comment's body is read

- **WHEN** a hook asks about `gh api graphql -f query='mutation($b:
  String!) { addComment(input: {subjectId: "I_1", body: $b}) { clientMutationId } }'
  -f b=hello`
- **THEN** the reader returns `hello` as the body

#### Scenario: A GraphQL issue is reported as a new issue

- **WHEN** a hook asks about `gh api graphql` with a `createIssue` mutation
  whose `body` is the literal `"b"`
- **THEN** the reader returns `b` as the body, and says that the post
  creates an issue

#### Scenario: A GraphQL mutation with no body sends no post

- **WHEN** a hook asks about `gh api graphql` with an `addLabelsToLabelable`
  mutation
- **THEN** the reader reports that the command sends no post

#### Scenario: A GraphQL mutation that can't be read is unreadable

- **WHEN** a hook asks about `gh api graphql -f query='mutation { … }'`,
  which the reader cannot parse, or about an `addDiscussionComment`
  mutation with a `body`, or about an `addComment` mutation whose `body`
  is a variable the call does not give
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh api write with a body it does not read is unreadable

- **WHEN** a hook asks about `gh api -X POST repos/o/r/releases -f
  body=notes`, or about `gh api repos/o/r/issues/5/comments -F
  body=@missing.md` where `missing.md` does not exist
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh api read is no post

- **WHEN** a hook asks about `gh api graphql -f query='{ viewer { login } }'`
  or `gh api -X GET search/issues -f q=x`
- **THEN** the reader reports that the command sends no post

#### Scenario: A review's nested comments are read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds
  `comments[0].body`
- **THEN** the reader returns that string as a body

#### Scenario: A gh api review's nested comments are read

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f
  body=ok -f 'comments[][path]=a.py' -f 'comments[][body]=Why?'`
- **THEN** the reader returns `ok` and `Why?` as bodies
- **AND** for `--input r.json`, where `r.json` holds `body` and a
  `comments` array whose items hold `body`, it returns each of them

#### Scenario: A gh api review whose comments can't be read is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f body=ok
  -F 'comments[][body]=@missing.md'`, where `missing.md` does not exist
- **THEN** the reader reports the command as unreadable

#### Scenario: The run form of the github-app script is read

- **WHEN** a hook asks about `G=/abs/github_app.py; python3 "$G" run -- gh
  pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: The github-app script as an unset G is unreadable

- **WHEN** a hook asks about `python3 "$G" gh pr comment 5 --body-file
  c.md`, and the command assigns `G` nowhere
- **THEN** the reader reports the command as unreadable, and the block
  message says to set `G` in the same command or write the script's path

#### Scenario: A gh read through an unset G is no post

- **WHEN** a hook asks about `python3 "$G" gh pr view 12 --comments`, and
  the command assigns `G` nowhere
- **THEN** the reader reports that the command sends no post

#### Scenario: A close with a comment is read

- **WHEN** a hook asks about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `done` as the body
