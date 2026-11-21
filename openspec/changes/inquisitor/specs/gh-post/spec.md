## Purpose

The shared post reader tells a hook what body a command or tool call
would post on a GitHub issue or pull request, so prose's posting hook
and the inquisitor's post hook judge the same text, and each blocks a
call the reader reports as unreadable.

## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-shell/`, SHALL tell a hook, for a
tool call, its post, that it sends no post, or that it is unreadable. For
a post, the reader returns the body the call sends and whether the call
creates an issue.
prose's posting hook and the inquisitor's post hook SHALL read posts only
through it.

#### Scenario: Both post hooks read a post through the shared reader

- **WHEN** both hooks check `gh pr comment 5 --body-file c.md`, where
  `c.md` exists
- **THEN** each takes the post the reader returns, with `c.md`'s text as
  its body, and neither reads the command itself

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(scenario *The gh post verbs are a closed list*). It mentions one when its
text, quoted or not, holds `gh` followed later by `pr` or `issue` and
later by a post verb listed for that word, or holds a `gh api` call that
is not a read (*A gh api call is a read only as a plain gh command*).

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; and a `gh api`
  call that can write
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
  hooks let it through unread

#### Scenario: A gh api read piped into a script is no post

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5 | python3 -c
  'import json, sys; print(json.load(sys.stdin)["title"])'`, or the same
  pipe with `python3 /abs/github_app.py gh api repos/o/r/pulls/5` as its
  first command
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb, so the line mentions none and no rule for a
  post-verb line applies

### Requirement: A command that only runs prose's script sends no post

A line that is one simple command, whose command is `prose.py` or a path
ending in `/prose.py`, SHALL send no post, whatever its arguments.

#### Scenario: A command that only runs prose is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post

### Requirement: The reader reads a gh pr or gh issue post only as a whole command line

For a Bash command, apart from the forms other requirements of this spec
add, the reader SHALL return a body only when the whole command line is
one `gh pr` or `gh issue` command with a verb that posts text. It SHALL say that `gh issue create` or `gh issue new` creates an
issue.

#### Scenario: A gh post chained to another command is unreadable

- **WHEN** a hook asks about `cd /x && gh pr comment 5 --body-file c.md`,
  where `c.md` exists
- **THEN** the reader reports the command as unreadable

#### Scenario: A new issue is reported as one

- **WHEN** a hook asks about `gh issue create --title t --body-file b.md`,
  or `gh issue new` with the same options, and `b.md` exists
- **THEN** the reader returns the file's text as the body, and says that
  the post creates an issue

### Requirement: A literal word is one the shell does not expand

The reader SHALL count a word as a **literal word** only when it holds no
`$`, backtick or backslash outside single quotes, and no `*`, `?`, `[`,
`{` or `~` outside quotes.

#### Scenario: Only a word the shell leaves alone is literal

- **WHEN** the reader judges the words `'a $b'`, `"a b"`, `hi`, `"$X"`,
  `hi*` and `~/notes`
- **THEN** the first three are literal words and the last three are not

### Requirement: A gh pr or gh issue body comes from a plain option value or an existing file

The body of a command that *The reader reads a gh pr or gh issue post only
as a whole command line* reads SHALL come from `--body` or `-b`, or for
`close` and `reopen` `--comment` or `-c`, as a literal word; or from
`--body-file` or `-F` naming a file that exists. Any other body source,
such as `--template`, SHALL make the command unreadable.

#### Scenario: A whole-command post with a body file is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md`,
  or the same with `-F body.md`, and `body.md` exists
- **THEN** the reader returns the file's text as the body

#### Scenario: A one-word unquoted body is read

- **WHEN** a hook asks about `gh pr comment 5 --body hi`,
  `gh pr comment 5 -bhi` and `gh pr comment 5 --body=hi`
- **THEN** the reader returns `hi` as the body of each

#### Scenario: A body from the shell, a pipe or a missing file is unreadable

- **WHEN** a hook asks about `gh pr comment 5 --body "$(cat body.md)"`,
  `gh pr comment 5 --body hi*`, `gh pr comment 5 --body ~/notes`,
  `cat c.md | gh pr comment 5 -F -`, or `gh pr comment 5 --body-file
  missing.md`, where `missing.md` does not exist
- **THEN** the reader reports each command as unreadable
- **AND** it reports as unreadable `gh pr create -t x -T tmpl.md`, where
  `-T` is `--template`'s short form, and any command with `--fill`,
  `--fill-first`, `--fill-verbose`, `--recover`, `--editor` or `--web`

#### Scenario: A close with a comment is read

- **WHEN** a hook asks about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `done` as the body
- **AND** `-c` and `reopen` are read the same way

### Requirement: The reader reads a GitHub MCP tool's body and comment keys

A **GitHub MCP tool** is one whose name starts `mcp__github__` or
`mcp__plugin_<name>_github__`, the tools prose's posting hook matches.
For one, the reader SHALL return every string under a key
named `body` or `comment`, at any depth, as a body, and say that the post
creates an issue for `create_issue`, and for `issue_write` with the
`method` `create`.

#### Scenario: An MCP comment field and an issue_write create are read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds the
  string `ok` under a key named `comment`, about one whose input holds
  `comments[0].body`, and about an `issue_write` call with the `method`
  `create` and the `body` `b`
- **THEN** the reader returns `ok` and the nested string as bodies, returns
  `b` as the body of the third, and says that the third creates an issue

### Requirement: The reader splits a command line into simple commands

The reader SHALL split a line into **simple commands**, each a command
and its arguments, at the shell's control operators, parentheses and line
breaks, reading an unquoted `$(…)` as more commands, a heredoc's body as
its command's input, a backslash-newline as nothing, and a comment as
nothing. A simple command's command is its first word, after quote
removal, past any leading keyword its scenario lists. A line holding a form
its scenarios list as unreadable SHALL be unreadable.

#### Scenario: A command line splits into simple commands

- **WHEN** a hook asks about a line that mentions a gh post verb
- **THEN** the reader splits it at `|`, `|&`, `||`, `&&`, `;`, `&`, `(`,
  `)` and line breaks
- **AND** takes each simple command's command as its first word after any
  leading `if`, `then`, `elif`, `else`, `do`, `while`, `until`, `!`, `{`
  or `time`, and counts `fi`, `done` or `}` alone as no command
- **AND** a simple command's text, quoted or not, names `gh` where `gh`
  has no letter, digit or `_` just before it and no letter, digit, `_` or
  `-` just after it

#### Scenario: A subshell's and an unquoted substitution's commands are read

- **WHEN** a hook asks about `(cd sub && gh pr comment 3 --body hi)` and
  about `echo $(gh pr comment 5 --body yo)`
- **THEN** the reader reads each as a post, and returns `hi` and `yo` as
  their bodies

#### Scenario: A backslash-newline and a comment are read as nothing

- **WHEN** a hook asks about `gh pr comment 5 \` and, on the next line,
  `--body-file b.md # reply`
- **THEN** the reader reads one simple command, `gh pr comment 5
  --body-file b.md`, joining the two lines and dropping the comment

#### Scenario: A form the reader can't split exactly is unreadable

- **WHEN** a hook asks about a line that mentions a gh post verb and holds
  a backtick, `<(…)`, `$'…'`, `${…}` holding more than a name, `$(…)`
  inside double quotes, an unterminated quote, a heredoc inside
  parentheses or holding `$(`, a file descriptor of two or more digits, or
  a comment holding a quote or a control operator
- **THEN** the reader reports the line as unreadable

### Requirement: A line whose simple commands send no text is no post

A line mentioning a gh post verb SHALL send no post when its input obeys
*Input to a no-post line reaches only data commands* and each simple
command in it names no `gh`; is a `gh pr` or `gh issue` command, or the
github-app skill's form of one, given no body; is a `gh api` call that
sends no post; or is a **data command** (its scenarios list them) with
no word that is `gh` or a path ending in `/gh`.

#### Scenario: A command that sends no body is no post

- **WHEN** a hook asks about `gh pr edit 5 --add-label spec`, `gh issue
  edit 5 --title 'Rename it?'`, an assignee, reviewer or milestone edit,
  `gh pr ready`, a close without `--comment`, `gh pr list`, or `python3
  /abs/github_app.py gh pr edit 5 --add-label spec`
- **THEN** the reader reports that each command sends no post
- **AND** so it does `cd x && gh api -X DELETE repos/o/r/issues/comments/9`
  and `cd x && gh api -X POST repos/o/r/releases -f body=notes`

#### Scenario: A gh post quoted as data is no post

- **WHEN** a hook asks about `echo 'run gh pr create next'`
- **THEN** the reader reports that the command sends no post
- **AND** the data commands are `echo`, `cat`, `tee`, `grep`,
  `egrep`, `fgrep`, `rg`, `git`, `python`, `python3`, `node`, `jq`,
  `head`, `tail`, `wc`, `sort`, `uniq`, `cut`, `tr`, `ls`, `cd`, `true`
  and `false`

#### Scenario: gh named as another command's argument is unreadable

- **WHEN** a hook asks about `xargs gh pr comment 5 -b x`, or about
  `echo gh pr create` with `gh` as a word of its own
- **THEN** the reader reports each command as unreadable

#### Scenario: Code given to a data command passes unread

- **WHEN** a hook asks about `python3 -c 'import os;
  os.system("gh pr comment 5 -b x")'`, `git -c 'alias.p=!gh pr comment
  5 -b x' p`, and `echo 'gh pr comment 5 -b x' | python3`
- **THEN** the reader reports that each line sends no post, since
  `python3` and `git` are data commands

### Requirement: Input to a no-post line reaches only data commands

In a line whose simple commands are all ones that *A line whose simple
commands send no text is no post* allows, input from a pipe or an input
redirection SHALL reach only data commands, or, when it reaches a single
simple command, a `gh` command that sends no text and uses no gh post
verb. Otherwise the line SHALL be unreadable.

#### Scenario: A gh post piped into a shell is unreadable

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | sh`
- **THEN** the reader reports the command as unreadable
- **AND** input reaches a command through `|`, `|&`, `<`, `<>`, `<&`, a
  heredoc or `<<<`

#### Scenario: Input that reaches several commands needs data commands only

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | { cat; gh pr
  view 5; }`, and about `echo 'gh pr comment 5 -b x' | { cat; wc -l; }`
- **THEN** the reader reports the first as unreadable and the second as
  sending no post
- **AND** input reaches several commands when it feeds `(`, `$(`, `{` or
  `while`

#### Scenario: Input may reach one gh command that uses no post verb

- **WHEN** a hook asks about `cat c.md | gh pr view 5 && gh pr edit 5
  --add-label spec`, and about `cat c.md | gh pr edit 5 --add-label spec`,
  whose input reaches the post verb `pr edit`
- **THEN** the reader reports the first as sending no post and the second
  as unreadable

### Requirement: Any other line that mentions a gh post verb is unreadable

The reader SHALL report as unreadable every line that mentions a gh post
verb and that it cannot read exactly, and every other such line unless it
returns a post for it or another requirement of this spec says the line
sends no post.

#### Scenario: A gh post run through another shell is unreadable

- **WHEN** a hook asks about `sh -c 'gh pr comment 5 --body-file c.md'`,
  `bash -c 'gh issue create -b x'` or `eval 'gh pr comment 5 -b x'`
- **THEN** the reader reports each command as unreadable

#### Scenario: A command the reader can't read exactly is unreadable

- **WHEN** a hook asks about ``gh pr comment 5 -b `cat c.md` ``, or about
  `gh pr comment 5 -b $'x'`
- **THEN** the reader reports each command as unreadable

### Requirement: The reader reads posts sent through the github-app skill and gh api

The reader SHALL read a call of the github-app skill's script, in the
forms its scenarios list, as the `gh` command it runs, judging its line
as if that `gh` command stood in the call's place and the line held no
`G` assignment. The script's path SHALL be a literal word ending in
`/github_app.py`, written out in the call or assigned to `G` before it.
A line that mentions a gh post verb and runs `python3 $G` with `G`
unassigned SHALL be unreadable, its block message saying how to fix it.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --body-file body.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: Another script given gh's arguments is unreadable

- **WHEN** a hook asks about `python3 /tmp/other.py gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports the command as unreadable

#### Scenario: The github-app script after another command is unreadable where a direct gh call is

- **WHEN** a hook asks about `cd x && python3 /abs/github_app.py gh pr
  comment 5 --body-file c.md`, and about `cd x && python3
  /abs/github_app.py gh api repos/o/r/issues/5/comments -F body=@c.md`,
  where `c.md` exists, so a missing file is not what blocks them
- **THEN** the reader reports each command as unreadable, as it does the
  same line with `gh` called directly, under *The reader reads a gh pr or
  gh issue post only as a whole command line* and *A gh api write read
  from a file is read only as a whole command line*

#### Scenario: The github-app script with an identity is read

- **WHEN** a hook asks about `G=/abs/github_app.py && python3 "$G"
  --identity bot gh pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body
- **AND** the reader reads this form only when the script runs `gh pr`,
  `gh issue` or `gh api`, either directly
  or after `run --`
- **AND** `--identity <name>` may come before `gh` or `run`
- **AND** `$G` may be unquoted, and `G=<path>;` assigns `G` as
  `G=<path> &&` does

#### Scenario: A quoted assignment to G sets it

- **WHEN** a hook asks about `G="/abs/github_app.py"; python3 "$G" gh pr
  comment 5 --body-file c.md`, and about the same command with
  `G="$HOME/github_app.py"`
- **THEN** the reader reads the first and reports the second as
  unreadable

#### Scenario: The github-app script as an unset G is unreadable

- **WHEN** a hook asks about `python3 "$G" gh pr comment 5 --body-file
  c.md`, or the same with `$G` unquoted, and the command assigns `G`
  nowhere
- **THEN** the reader reports the command as unreadable, and the block
  message says to set `G` in the same command or write the script's path

#### Scenario: A gh read through an unset G is no post

- **WHEN** a hook asks about `python3 "$G" gh pr view 12 --comments`, and
  the command assigns `G` nowhere
- **THEN** the reader reports that the command sends no post
- **AND** it reports `python3 "$G" gh api repos/o/r/pulls/5`, with `G`
  assigned nowhere, as unreadable: an unassigned `$G` is not the
  github-app skill's form, so *A gh api call is a read only as a plain gh
  command* does not count the call as a read

#### Scenario: A gh api call through the github-app script is judged as a direct one

- **WHEN** a hook asks about `python3 /abs/github_app.py gh api
  repos/o/r/issues/5/comments -f body=hi`, and about `python3
  /abs/github_app.py --identity bot gh api -X DELETE
  repos/o/r/issues/comments/9`
- **THEN** the reader returns `hi` as the first's body, and reports that
  the second sends no post

### Requirement: A gh api call is a read only as a plain gh command

A `gh api` call SHALL count as a **read** only when it is a simple
command whose command is `gh`, or the github-app skill's form of one,
whose every word is a literal word, except that its endpoint may hold `?`
and gh's `{owner}`, `{repo}` and `{branch}` placeholders, and that does
not write as *A gh api call writes by its method, fields, input or a
mutation* says. Any other `gh` followed by `api` SHALL mention a gh post
verb.

#### Scenario: A read with placeholders or a query string is a read

- **WHEN** a hook asks about `gh api repos/{owner}/{repo}/pulls/5`, and
  about `gh api search/issues?q=x`
- **THEN** the reader reports that each line sends no post

### Requirement: A gh api call holding a word the shell builds is unreadable

A `gh api` call holding a word that is not literal SHALL be unreadable,
except an endpoint holding `?` or gh's `{owner}`, `{repo}` and
`{branch}` placeholders, which the shell cannot turn into a flag or a
field, and the github-app form's `$G`.

#### Scenario: A gh api call the reader cannot see whole is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments $F`,
  `gh api -X "$M" repos/o/r/issues/5`, `cat a | xargs gh api
  repos/o/r/issues/5/comments`, or `sh -c 'gh api
  repos/o/r/issues/5/comments "$@"' _ -f body=x`
- **THEN** the reader reports each as unreadable, though `$F` could hold
  no field

### Requirement: A gh api call writes by its method, fields, input or a mutation

A `gh api` call to a REST endpoint SHALL **write** when its method, the
last given by `-X` or `--method` in any form gh accepts, compared
without case, is not `GET`; when it gives no method and has a field
(`-f`, `--raw-field`, `-F` or `--field`, in any form) or `--input`; or
when a header sets `X-HTTP-Method-Override`. A call to `graphql` SHALL
write when its query holds a mutation or the reader cannot read its
query.

#### Scenario: A method other than GET writes

- **WHEN** a hook asks about `gh api -X DELETE repos/o/r/issues/comments/9`,
  `gh api --method=patch repos/o/r/issues/5 -f state=closed` and
  `gh api -XPOST repos/o/r/issues/5/labels -f 'labels[]=x'`
- **THEN** each call writes
- **AND** `gh api -X get search/issues -f q=x` does not, while
  `gh api -X GET -X POST repos/o/r/labels -f name=x` does, gh taking the
  last method

#### Scenario: Fields or input with no method write

- **WHEN** a hook asks about `gh api repos/o/r/labels -f name=x`,
  `gh api repos/o/r/labels -fname=x`, `gh api repos/o/r/labels
  --raw-field=name=x`, and `gh api repos/o/r/labels --input l.json`
- **THEN** each call writes, as gh sends it with `POST`
- **AND** `gh api -X GET search/issues -f q=x` does not write, nor does
  `gh api repos/o/r/pulls/5` with no field

#### Scenario: A method override header writes

- **WHEN** a hook asks about `gh api -H 'X-HTTP-Method-Override: DELETE'
  repos/o/r/issues/comments/9`
- **THEN** the call writes

#### Scenario: A GraphQL call writes only as a mutation or an unread query

- **WHEN** a hook asks about `gh api graphql -f query='{ viewer { login }
  }'`, about `gh api graphql -f query='mutation { addStar(input:
  {starrableId: "R_1"}) { clientMutationId } }'`, and about `cat
  q.graphql | gh api graphql -F query=@-`
- **THEN** the first does not write, and the second and third do: the
  third's query comes from standard input, which the reader never reads

### Requirement: The reader reads a gh api write to an issue or pull request

For a `gh api` write under `repos/<owner>/<repo>/issues` or `.../pulls`,
the reader SHALL read each `body` field, and each `body` key of the
`--input` JSON, as a body, and, for a review under
`.../pulls/<n>/reviews`, each `body` in its `comments`. The reader SHALL say that a `POST` to
`repos/<owner>/<repo>/issues` creates an issue.

#### Scenario: Each gh api body form is read

- **WHEN** a hook asks about an issue comment sent with `gh api`, its body
  given by `-f body=…`, `--raw-field body=…`, `-F body=…`,
  `--field body=…`, `-F body=@c.md` or `--input c.json`
- **THEN** the reader returns the body for each form, reading the named
  file for `@<file>` and `--input`, the `--input` file being JSON with a
  `body` key

#### Scenario: A new issue sent through gh api or MCP is reported as one

- **WHEN** a hook asks about `gh api repos/o/r/issues -f title=t -f
  body=b`, or about a GitHub MCP `create_issue` call with the `title` `t`
  and the `body` `b`
- **THEN** the reader returns `b` as the body, and says that the post
  creates an issue

#### Scenario: A quoted gh api body is read after quote removal

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments -f
  body='a b'`
- **THEN** the reader returns `a b` as the body

#### Scenario: gh api placeholders count as an owner and a repository

- **WHEN** a hook asks about `gh api /repos/{owner}/{repo}/issues/5/comments
  -f body=hi`
- **THEN** the reader returns `hi` as the body
- **AND** the endpoint may have a leading `/` or none, and its `{owner}`
  and `{repo}` are read as placeholders

#### Scenario: A gh api review's nested comments are read

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f
  body=ok -f 'comments[][path]=a.py' -f 'comments[][body]=Why?'`
- **THEN** the reader returns `ok` and `Why?` as bodies
- **AND** for `--input r.json`, where `r.json` holds `body` and a
  `comments` array whose items hold `body`, it returns each of them

### Requirement: A gh api write read from a file is read only as a whole command line

When a `gh api` write to an issue or pull request endpoint, or a call to
`graphql` with or without a mutation, takes a field from a file, through
`-F` or `--field` with `@<file>`, or its input through `--input`, the
reader SHALL read it only when the whole command line is that `gh api`
command, and SHALL report it as unreadable otherwise. A write whose
fields are all given in the command SHALL be read in a longer line too.

#### Scenario: A gh api body file after another command is unreadable

- **WHEN** a hook asks about `printf 'unsigned' > c.md && gh api
  repos/o/r/issues/5/comments -F body=@c.md`, or the same line with
  `--input c.json`, where both files exist
- **THEN** the reader reports each line as unreadable
- **AND** so it does `printf q > q.graphql && gh api graphql -F
  query=@q.graphql`, whatever the file holds

#### Scenario: A gh api body given in the command is read in a longer line

- **WHEN** a hook asks about `cd /x && gh api repos/o/r/issues/5/comments
  -f body='done'`
- **THEN** the reader returns `done` as the body

### Requirement: The reader reads GraphQL posts and blocks an unreadable body sent to issues or pull requests

In each of the thirteen mutations that post text, which its scenarios
list, the reader SHALL read every `body` argument, at any depth, as a body;
`createIssue` creates an issue. It SHALL report as unreadable a query it
cannot read or parse, and a `gh api` write to an endpoint or mutation it reads
whose `body` it cannot read. Any other `gh api` call whose words are all
literal SHALL send no post (*A gh api call holding a word the shell builds
is unreadable*).

#### Scenario: A GraphQL comment's body is read

- **WHEN** a hook asks about `gh api graphql -f query='mutation($b:
  String!) { addComment(input: {subjectId: "I_1", body: $b}) { clientMutationId } }'
  -f b=hello`
- **THEN** the reader returns `hello` as the body
- **AND** it reads a `body` the same way as a literal in the query, a
  variable given through any `gh api` field form, or one in the
  `variables` of an `--input` file, such as each thread's `body` in an
  `addPullRequestReview`

#### Scenario: The GraphQL mutations that post text are a closed list

- **WHEN** a hook asks about `gh api graphql` with a mutation
- **THEN** the reader reads it as posting text when it is `addComment`,
  `addPullRequestReview`, `addPullRequestReviewComment`,
  `addPullRequestReviewThread`, `addPullRequestReviewThreadReply`,
  `submitPullRequestReview`, `createIssue`, `createPullRequest`,
  `updateIssue`, `updateIssueComment`, `updatePullRequest`,
  `updatePullRequestReview` or `updatePullRequestReviewComment`

#### Scenario: A GraphQL issue is reported as a new issue

- **WHEN** a hook asks about a `createIssue` mutation whose `body` is the
  literal `"b"`
- **THEN** the reader returns `b` as the body and says that the post
  creates an issue

#### Scenario: A GraphQL mutation with no body sends no post

- **WHEN** a hook asks about `gh api graphql` with an `addLabelsToLabelable`
  mutation, or a listed mutation with no `body`
- **THEN** the reader reports that each command sends no post

#### Scenario: A GraphQL mutation that can't be read is unreadable

- **WHEN** a hook asks about `gh api graphql -f query='mutation { … }'`,
  which the reader cannot parse, or an `addComment` mutation whose `body`
  is a variable the call does not give
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh api body from a missing file is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments -F
  body=@missing.md`, or `gh api repos/o/r/pulls/5/reviews -f body=ok -F
  'comments[][body]=@missing.md'`, where `missing.md` does not exist
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh api write to an endpoint the reader does not read passes unread

- **WHEN** a hook asks about `gh api -X POST repos/o/r/releases -F
  body=@missing.md`, and a `gh api graphql` call with an `addDiscussionComment` mutation
  whose `body` is the literal `"x"`
- **THEN** the reader reports that each command sends no post, so
  neither post hook reads it, as neither reads `gh release` or
  `gh discussion`
- **AND** `gh api -X POST repos/o/r/releases -f body=$B` is unreadable,
  since the shell could split `$B` into more words, one of them another
  endpoint
