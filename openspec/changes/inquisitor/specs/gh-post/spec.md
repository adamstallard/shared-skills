## Purpose

The shared post reader tells a hook what an agent's command or tool call
would post on GitHub: the post's body and title, that it sends no post, or
that it cannot be read. prose's posting hook and the inquisitor's post hook
both read posts through it, so the two judge the same text, and each blocks
a post it cannot read rather than let it through unread.

## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-post/`, SHALL tell a hook, for a
tool call, its post, that it sends no post, or that it is unreadable. A
post is a body; a title, when the call sets an issue's or a pull request's
title; and whether it creates an issue. prose's posting hook and the
inquisitor's post hook SHALL read posts only through it.

#### Scenario: Both post hooks read a post through the shared reader

- **WHEN** prose's posting hook and the inquisitor's post hook each check
  `gh pr comment 5 --body-file c.md`, where `c.md` exists
- **THEN** each takes the post the shared post reader returns, with
  `c.md`'s text as its body, and neither reads the command itself

### Requirement: prose's posting hook checks a body's footer and a title's readability

prose's posting hook SHALL check a body's footer, let through a call with
a title and no body, and check only that a title can be read, blocking an
unreadable call.

#### Scenario: A title-only edit returns its title

- **WHEN** a hook asks about `gh issue edit 5 --title 'Rename it?'`
- **THEN** the reader returns `Rename it?` as the title and no body, and
  prose's hook lets the command through

#### Scenario: prose's hook checks only that a title can be read

- **WHEN** a hook asks about `gh pr create --title 'A long and wordy
  title' --body-file body.md`, and `body.md` ends in a valid prose footer
- **THEN** prose's hook checks the body's footer, checks nothing in the
  title, and lets the command through

#### Scenario: A title built by the shell is unreadable

- **WHEN** a hook asks about `gh pr create --title "$(git log -1
  --format=%s)" --body-file body.md`, and `body.md` exists
- **THEN** the reader reports the command as unreadable, and prose's hook
  and the inquisitor's post hook both block it

### Requirement: A command that mentions no gh post verb sends no post

A **gh post verb** is one of the closed list prose's reader handles, as
its scenarios list: verbs of `gh pr` and `gh issue`, and `gh api`, whose
writes this spec's `gh api` requirements define. A command **mentions**
one when its text, quoted or not, holds the word `gh` followed later by
`pr` or `issue` and later by one of their verbs, or `gh` followed by
`api`. A command that mentions no gh post verb SHALL send no post, but
see *The reader reads only gh's own top-level commands*.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `review`, `close` or `reopen`; and
  `gh api`
- **AND** of these, the verbs that post text are `create`, `new`, `edit`,
  `comment` and `review`; `revert`, for a pull request only; and `close`
  or `reopen` with a comment

#### Scenario: A command naming no gh post verb is no post

- **WHEN** a hook asks about `gh pr view 5`, or about `git log`
- **THEN** the reader reports that each command sends no post

### Requirement: The reader reads only gh's own top-level commands

A `gh` command whose first word after `gh` is not on gh's own list of
top-level commands, fixed in the reader, such as an alias or an extension,
SHALL be unreadable wherever it appears, even in a command that another
requirement of this spec says sends no post.

#### Scenario: A gh alias or extension is unreadable

- **WHEN** a hook asks about `gh c 5 -b 'User says: yes'`, where `c` is
  not one of gh's own commands
- **THEN** the reader reports the command as unreadable

### Requirement: A command that only runs prose's script sends no post

A command that only runs prose's script, in the forms its scenarios list,
SHALL send no post, whatever its arguments.

#### Scenario: A command that only runs prose is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post
- **AND** so it does for a line that is one simple command whose command
  is `prose.py` or a path ending in `/prose.py`

#### Scenario: prose run through `python` is no post

- **WHEN** a hook asks about `python prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post
- **AND** so it does for `python3`, followed directly, with no option
  between, by such a path

### Requirement: The reader reads a gh pr or gh issue post only as a whole command line

For a Bash command, apart from the forms other requirements of this spec
add, the reader SHALL return a body or a title only when the whole
command line is one `gh pr` or `gh issue` command with a verb that posts
text. It SHALL say that `gh issue create` or `gh issue new` creates an
issue.

#### Scenario: A chained title edit is unreadable

- **WHEN** a hook asks about `cd x && gh pr edit 3 --title 'Rename?'`
- **THEN** the reader reports the command as unreadable

#### Scenario: A gh post chained to another command is unreadable

- **WHEN** a hook asks about `cd /x && gh pr comment 5 --body-file c.md`,
  where `c.md` exists
- **THEN** the reader reports the command as unreadable

#### Scenario: A new issue is reported as one

- **WHEN** a hook asks about `gh issue create --title t --body-file b.md`,
  and `b.md` exists
- **THEN** the reader returns the file's text as the body, and says that
  the post creates an issue
- **AND** it says so for `gh issue new` too

### Requirement: A gh pr or gh issue body comes from a quoted option or an existing file

The body of a command that *The reader reads a gh pr or gh issue post only
as a whole command line* reads SHALL come from `--body` or `-b`, or for
`close` and `reopen` `--comment` or `-c`, in single quotes or in double
quotes with no `$`, backtick or backslash; or from `--body-file` or `-F`
naming a file that exists.

#### Scenario: A whole-command post with a body file is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md`,
  and `body.md` exists
- **THEN** the reader returns the file's text as the body, and `t` as the
  title
- **AND** `-F body.md` is read the same way

#### Scenario: A body built by the shell is unreadable

- **WHEN** a hook asks about `gh pr comment 5 --body "$(cat body.md)"`
- **THEN** the reader reports the command as unreadable

#### Scenario: A post that reads its body from a pipe is unreadable

- **WHEN** a hook asks about `cat c.md | gh pr comment 5 -F -`
- **THEN** the reader reports the command as unreadable

#### Scenario: A body file that does not exist is unreadable

- **WHEN** a hook asks about `gh pr comment 5 --body-file missing.md`,
  where `missing.md` does not exist
- **THEN** the reader reports the command as unreadable

#### Scenario: A close with a comment is read

- **WHEN** a hook asks about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `done` as the body
- **AND** `-c` and `reopen` are read the same way

### Requirement: A gh pr or gh issue title is read only as a literal word

In a command that *The reader reads a gh pr or gh issue post only as a
whole command line* reads, the reader SHALL read a title, given by
`--title` or `-t`, only when its whole word is a literal word, as *The
reader reads posts sent through the github-app skill and gh api* defines
one. `--fill` and its variants SHALL make the command unreadable.

#### Scenario: A post's title holding a question is read

- **WHEN** a hook asks about `gh pr create --title 'Retry with backoff?'
  --body-file body.md`, and `body.md` exists
- **THEN** the reader returns the file's text as the body, and
  `Retry with backoff?` as the title

#### Scenario: A title taken from commits is unreadable

- **WHEN** a hook asks about `gh pr create --fill-first --body-file
  body.md`, and `body.md` exists
- **THEN** the reader reports the command as unreadable
- **AND** so it does with `--fill` or `--fill-verbose`

### Requirement: The reader reads a GitHub MCP tool's body, comment and title keys

For a GitHub MCP tool, the reader SHALL return every string under a key
named `body` or `comment`, at any depth, as a body, one under `title` as
the title, and say that the post creates an issue when the tool creates
one.

#### Scenario: An MCP comment field and an issue_write create are read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds the
  string `ok` under a key named `comment`, and about an `issue_write`
  call with the `method` `create` and the `body` `b`
- **THEN** the reader returns `ok` as a body of the first, returns `b` as
  the body of the second, and says that the second creates an issue

#### Scenario: A review's nested comments are read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds
  `comments[0].body`
- **THEN** the reader returns that string as a body

### Requirement: The reader splits a command line into simple commands

The reader SHALL split a line into **simple commands**, each a command
and its arguments, at the shell's control operators and line breaks,
reading each unquoted `$(…)` as more commands; a `$(…)` inside double
quotes makes the line unreadable. A simple command's command is its first
word after any leading keyword its scenarios list. Heredocs, comments,
line continuations and finer points are read as prose's `DECISIONS.md`
records under *A command that runs no gh post is not a post*.

#### Scenario: A command line splits into simple commands

- **WHEN** a hook asks about a command line that mentions a gh post verb
- **THEN** the reader splits it at `|`, `|&`, `||`, `&&`, `;`, `&` and
  line breaks
- **AND** takes each simple command's command as its first word after any
  leading `if`, `then`, `elif`, `else`, `do`, `while`, `until`, `!`, `{`
  or `time`

### Requirement: A line whose simple commands send no text is no post

A line mentioning a gh post verb SHALL send no post when its input obeys
*Input to a no-post line reaches only data commands* and each simple
command in it names no `gh`, is a `gh` command sending no text, or is one
of prose's **data commands** given no code to run, with `gh` only inside a
longer word that is not a path ending in `/gh`. Its scenarios list the
data commands and the fixed forms that give code to run. The github-app
skill's form counts as the `gh` command it runs.

#### Scenario: A command that sends no body is no post

- **WHEN** a hook asks about `gh pr edit 5 --add-label spec`, an assignee,
  reviewer or milestone edit, `gh pr ready`, a close without `--comment`,
  or `gh pr list`
- **THEN** the reader reports that each command sends no post

#### Scenario: A gh post quoted as data is no post

- **WHEN** a hook asks about `echo 'run gh pr create next'`
- **THEN** the reader reports that the command sends no post
- **AND** prose's data commands are `echo`, `cat`, `tee`, `grep`,
  `egrep`, `fgrep`, `rg`, `git`, `python`, `python3`, `node`, `jq`,
  `head`, `tail`, `wc`, `sort`, `uniq`, `cut`, `tr`, `ls`, `cd`, `true`
  and `false`

#### Scenario: gh named as another command's argument is unreadable

- **WHEN** a hook asks about `xargs gh pr comment 5 -b x`, or about
  `echo gh pr create` with `gh` as a word of its own
- **THEN** the reader reports each command as unreadable, the `echo` one
  too, though `echo` is one of prose's data commands

#### Scenario: A gh post run as inline code is unreadable

- **WHEN** a hook asks about
  `python3 -c 'import os; os.system("gh pr comment 5 -b x")'`,
  `node -e 'require("child_process").execSync("gh pr comment 5 -b x")'`,
  `ruby -e 'system("gh pr comment 5 -b x")'`,
  `perl -e 'system("gh pr comment 5 -b x")'` or
  `git -c 'alias.p=!gh pr comment 5 -b x' p`
- **THEN** the reader reports each command as unreadable
- **AND** a data command is given code to run by an option before its
  script or subcommand: `-c` for `python` or `python3`; `-e`, `--eval`,
  `-p` or `--print` for `node`; or `-c` for `git`

#### Scenario: Inline code after grouped options is unreadable

- **WHEN** a hook asks about
  `python3 -Ic 'import os; os.system("gh pr comment 5 -b x")'`
- **THEN** the reader reports the command as unreadable, as `-c` after
  any single-letter options gives code to run

#### Scenario: A git subcommand that runs a gh post is unreadable

- **WHEN** a hook asks about `git rebase -x 'gh pr comment 5 -b x' main`,
  `git submodule foreach 'gh issue create -t x -b y'` or
  `git bisect run gh pr comment 5 -b x`
- **THEN** the reader reports each command as unreadable
- **AND** `git rebase --exec` is given code to run, as `-x` is

#### Scenario: A label edit through the github-app skill is no post

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr edit 5
  --add-label spec`
- **THEN** the reader reports that the command sends no post, as it
  does for `gh pr edit 5 --add-label spec`

### Requirement: Input to a no-post line reaches only data commands

In a line whose simple commands are all ones that *A line whose simple
commands send no text is no post* allows, input from a pipe or an input
redirection SHALL reach only data commands, or, when it reaches a single
simple command, a `gh` command that sends no text and uses no gh post
verb. Otherwise the line SHALL be unreadable. `python`, `python3` or
`node` reading its program from that input is not a data command.

#### Scenario: A gh post piped into a shell is unreadable

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | sh`
- **THEN** the reader reports the command as unreadable
- **AND** input reaches a command through `|`, `|&`, `<`, `<>`, `<&`, a
  heredoc or `<<<`

#### Scenario: A gh post fed to an interpreter's input is unreadable

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | python3`, or
  about `python3 -` reading a heredoc that holds
  `os.system("gh pr comment 5 -b x")`
- **THEN** the reader reports each command as unreadable
- **AND** an interpreter reads its program from input when its script is
  `-`, or it has no script and no `-c`, `-e`, `--eval`, `-p` or `--print`

#### Scenario: Input that reaches several commands needs data commands only

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | { cat; gh pr
  view 5; }`, and about `echo 'gh pr comment 5 -b x' | { cat; wc -l; }`
- **THEN** the reader reports the first as unreadable, since `gh pr view`
  is not a data command, and the second as sending no post
- **AND** input reaches several commands when it feeds `(`, `$(`, `{` or
  `while`

### Requirement: Any other line that mentions a gh post verb is unreadable

The reader SHALL report as unreadable every line that mentions a gh post
verb unless it returns a post for it or another requirement of this spec
says the line sends no post, and any such line it cannot read exactly,
such as one with a backtick, `$'…'` or an unterminated quote.

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
forms its scenarios list, as the `gh` command it runs. The script's path
SHALL end in `/github_app.py`, be a **literal word**, one the shell does
not expand, and be written out or a `$G` the line assigns first. Nothing
but that assignment SHALL come before `python3` in the line. A line that
mentions a gh post verb and runs `python3 $G` with `G` unassigned SHALL be
unreadable, its block message saying how to fix it.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --body-file body.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: Another script given gh's arguments is unreadable

- **WHEN** a hook asks about `python3 /tmp/other.py gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports the command as unreadable, as a script
  whose path does not end in `/github_app.py` is not the github-app form

#### Scenario: The github-app script with an identity is read

- **WHEN** a hook asks about `G=/abs/github_app.py && python3 "$G"
  --identity bot gh pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body
- **AND** the script runs `gh pr` or `gh issue`, directly or after
  `run --`, `--identity <name>` may come before `gh` or `run`, `$G` may be
  unquoted, and `G=<path>;` assigns `G` as `G=<path> &&` does

#### Scenario: A quoted assignment to G sets it

- **WHEN** a hook asks about `G="/abs/github_app.py"; python3 "$G" gh pr
  comment 5 --body-file c.md`, and about the same command with
  `G="$HOME/github_app.py"`
- **THEN** the reader returns the file's text as the body of the first,
  and reports the second as unreadable
- **AND** a word is not literal when it holds a `$`, backtick or
  backslash outside single quotes, or a `*`, `?`, `[`, `{` or `~`
  outside quotes

#### Scenario: The run form of the github-app script is read

- **WHEN** a hook asks about `G=/abs/github_app.py; python3 "$G" run -- gh
  pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body

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

### Requirement: The reader reads a gh api write to an issue or pull request

A `gh api` call **writes** when `-X` or `--method` gives `POST`, `PATCH`
or `PUT`, or it has fields or `--input` and no `-X GET`. For a write under
`repos/<owner>/<repo>/issues` or `.../pulls`, the reader SHALL read each
`body` field or `--input` key as a body, a `title` one as the title, and,
for a review, each comment's `body`. Each field SHALL be a literal word;
the endpoint need not be. It SHALL say that a `POST` to `.../issues`
creates an issue, as an MCP `create_issue` does.

#### Scenario: Each gh api body form is read

- **WHEN** a hook asks about an issue comment sent with `gh api`, its body
  given by `-f body=…`, `--raw-field body=…`, `-F body=@c.md` or
  `--input c.json`
- **THEN** the reader returns the body, for each of the four forms
- **AND** `-F body=hi` and `--field body=hi` are read as `-f` is, `-F`
  and `--field` also read `@<file>`, and `--input` names a JSON file with
  a `body` key

#### Scenario: A new issue sent through gh api or MCP is reported as one

- **WHEN** a hook asks about `gh api repos/o/r/issues -f title=t -f
  body=b`, or about a GitHub MCP `create_issue` call with the `title` `t`
  and the `body` `b`
- **THEN** the reader returns `b` as the body and `t` as the title, and
  says that the post creates an issue
- **AND** with `-f title=t` and no `body`, it returns the title alone

#### Scenario: A gh api body held in a shell variable is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments -f
  body=$B`, about the same call with `-f "body=$B"`, and about it with
  `-f body='a b'`
- **THEN** the reader reports the first two as unreadable, and returns
  `a b` as the body of the third
- **AND** `gh api repos/o/r/issues -f title=$T` is unreadable too

#### Scenario: gh api placeholders count as an owner and a repository

- **WHEN** a hook asks about `gh api /repos/{owner}/{repo}/issues/5/comments
  -f body=hi`
- **THEN** the reader returns `hi` as the body
- **AND** the endpoint may have a leading `/` or none, its `{owner}` and
  `{repo}` are read as placeholders, and the unquoted field is read,
  though a `--body` of `gh pr` or `gh issue` must be quoted

#### Scenario: A gh api review's nested comments are read

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f
  body=ok -f 'comments[][path]=a.py' -f 'comments[][body]=Why?'`
- **THEN** the reader returns `ok` and `Why?` as bodies
- **AND** for `--input r.json`, where `r.json` holds `body` and a
  `comments` array whose items hold `body`, it returns each of them

### Requirement: The reader reads GraphQL posts and blocks a gh api write it can't read

A GraphQL call writes when it holds a mutation. In the thirteen mutations
its scenarios list, which post text, the reader SHALL read every `body`
argument, at any depth, as a body and a `title` argument as the title;
`createIssue` creates an issue. It SHALL report as unreadable a query it
cannot parse, and a `gh api` write with a field, title or `body` it cannot
read, or a `body` for an endpoint or mutation it does not read. Any other
`gh api` call, read or write, SHALL send no post.

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
- **AND** it reads a `title` argument only from `createIssue`,
  `createPullRequest`, `updateIssue` or `updatePullRequest`

#### Scenario: A GraphQL issue is reported as a new issue

- **WHEN** a hook asks about `gh api graphql` with a `createIssue` mutation
  whose `body` is the literal `"b"`
- **THEN** the reader returns `b` as the body, and says that the post
  creates an issue

#### Scenario: A GraphQL title the reader can't read is unreadable

- **WHEN** a hook asks about `gh api graphql` with a `createPullRequest`
  mutation whose `title` is a variable the call does not give
- **THEN** the reader reports the command as unreadable

#### Scenario: A GraphQL mutation with no body sends no post

- **WHEN** a hook asks about `gh api graphql` with an `addLabelsToLabelable`
  mutation, or a listed mutation with neither a `body` nor a `title`
- **THEN** the reader reports that each command sends no post

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
- **AND** `gh api -X POST repos/o/r/milestones -f title=x` sends no post

#### Scenario: A gh api read is no post

- **WHEN** a hook asks about `gh api graphql -f query='{ viewer { login } }'`
  or `gh api -X GET search/issues -f q=x`
- **THEN** the reader reports that the command sends no post

#### Scenario: A gh api review whose comments can't be read is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f body=ok
  -F 'comments[][body]=@missing.md'`, where `missing.md` does not exist
- **THEN** the reader reports the command as unreadable
