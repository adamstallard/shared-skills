## Purpose

The shared post reader tells a hook what an agent's command or tool call
would post on GitHub, so prose's posting hook and the inquisitor's post
hook judge the same text, and each blocks a post it cannot read.

## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-shell/`, SHALL tell a hook, for a
tool call, its post, that it sends no post, or that it is unreadable. A
post is a body; a title, when the call sets an issue's or a pull request's
title; and whether it creates an issue. prose's posting hook and the
inquisitor's post hook SHALL read posts only through it.

#### Scenario: Both post hooks read a post through the shared reader

- **WHEN** both hooks check `gh pr comment 5 --body-file c.md`, where
  `c.md` exists
- **THEN** each takes the post the reader returns, with `c.md`'s text as
  its body, and neither reads the command itself

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
- **THEN** the reader reports the command as unreadable, and both hooks
  block it

### Requirement: A command that mentions no gh post verb sends no post

A **gh post verb** is one of the closed list that *The gh post verbs are
a closed list* gives. A command
**mentions** one when its text, quoted or not, holds `gh` followed
later by `pr` or `issue` and later by one of their verbs, or `gh`
followed by `api`, unless that `gh api` is a call *A gh api call is a
read only as a plain gh command* counts as a read. A command that mentions no gh
post verb SHALL send no post.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `review`, `close` or `reopen`; and
  a `gh api` call that can write
- **AND** of these, the verbs that post text are `create`, `new`, `edit`,
  `comment` and `review`; `revert`, for a pull request only; and `close`
  or `reopen` with a comment

#### Scenario: A command naming no gh post verb is no post

- **WHEN** a hook asks about `gh pr view 5`, or about `git log`
- **THEN** the reader reports that each command sends no post

#### Scenario: A gh api read piped into a script is no post

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5 | python3 -c
  'import json, sys; print(json.load(sys.stdin)["title"])'`, or the same
  with `python3 /abs/github_app.py gh api repos/o/r/pulls/5`
- **THEN** the reader reports that each line sends no post, since a read
  is no gh post verb and the line mentions none
- **AND** `python3 -c 'import os; os.system("gh api -X POST x")'` still
  mentions one, in the code's text, and is unreadable

### Requirement: The reader reads only gh's own top-level commands

A `gh` command whose first word after `gh` is not on gh's own top-level
commands, fixed in the reader, such as an alias or an extension, SHALL be
unreadable wherever it appears, even where another requirement says no
post, bar a line that only runs prose's script. Both a simple command
whose command is `gh` and the word `gh`, quoted or not, in another's text
count as `gh` commands, unless that other is a data command (*A line
whose simple commands send no text is no post*) given no code.

#### Scenario: A gh alias or extension is unreadable

- **WHEN** a hook asks about `gh c 5 -b 'User says: yes'`, where `c` is
  not one of gh's own commands
- **THEN** the reader reports the command as unreadable

#### Scenario: A gh alias run by another command is unreadable

- **WHEN** a hook asks about `env gh c 5 -b x`, `xargs gh c 5 -b x`, or
  `sh -c 'gh c 5 -b x'`
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh alias inside code given to a data command is unreadable

- **WHEN** a hook asks about `python3 -c 'import os; os.system("gh c 5
  -b x")'`, or `git -c 'alias.x=!gh c 5 -b x' x`
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh extension's name in prose's arguments is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'try gh dash'`
- **THEN** the reader reports that the command sends no post

#### Scenario: A gh alias's name inside a data command's text is data

- **WHEN** a hook asks about `git commit -m 'use gh dash'`
- **THEN** the reader reports that the command sends no post

### Requirement: A command that only runs prose's script sends no post

A command that only runs prose's script, in the forms its scenario lists,
SHALL send no post, whatever its arguments.

#### Scenario: A command that only runs prose is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'approve the gh
  pr create body'`, or the same run as `python prose.py sign …`
- **THEN** the reader reports that each command sends no post
- **AND** the forms are a line that is one simple command whose command
  is `prose.py` or a path ending in `/prose.py`, or is `python` or
  `python3` followed directly, with no option between, by such a path

### Requirement: The reader reads a gh pr or gh issue post only as a whole command line

For a Bash command, apart from the forms other requirements of this spec
add, the reader SHALL return a body or a title only when the whole
command line is one `gh pr` or `gh issue` command with a verb that posts
text. It SHALL say that `gh issue create` or `gh issue new` creates an
issue.

#### Scenario: A gh post chained to another command is unreadable

- **WHEN** a hook asks about `cd x && gh pr edit 3 --title 'Rename?'`, or
  about `cd /x && gh pr comment 5 --body-file c.md`, where `c.md` exists
- **THEN** the reader reports each command as unreadable

#### Scenario: A new issue is reported as one

- **WHEN** a hook asks about `gh issue create --title t --body-file b.md`,
  or `gh issue new` with the same options, and `b.md` exists
- **THEN** the reader returns the file's text as the body, and says that
  the post creates an issue

### Requirement: A gh pr or gh issue body comes from a plain option value or an existing file

The body of a command that *The reader reads a gh pr or gh issue post only
as a whole command line* reads SHALL come from `--body` or `-b`, or for
`close` and `reopen` `--comment` or `-c`, in single quotes, in double
quotes with no `$`, backtick or backslash, or as one unquoted word
holding none of `$`, backtick, `*`, `?`, `[`, `{`, `~` or `\`; or from
`--body-file` or `-F` naming a file that exists. Any other body source,
such as `--template`, SHALL make the command unreadable.

#### Scenario: A whole-command post with a body file is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md`,
  or the same with `-F body.md`, and `body.md` exists
- **THEN** the reader returns the file's text as the body, and `t` as the
  title

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
  `-T` is `--template`'s short form, and any command with `--recover`,
  `--editor` or `--web`

#### Scenario: A close with a comment is read

- **WHEN** a hook asks about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `done` as the body
- **AND** `-c` and `reopen` are read the same way

### Requirement: A gh pr or gh issue title is read only as a literal word

A **literal word** is one the shell does not expand: it holds no `$`,
backtick or backslash outside single quotes, and no `*`, `?`, `[`, `{` or
`~` outside quotes. In a command that *The reader reads a gh pr or gh
issue post only as a whole command line* reads, the reader SHALL read a
title, given by `--title` or `-t`, only when its whole word is a literal
word. `--fill` and its variants SHALL make the command unreadable.

#### Scenario: A post's title holding a question is read

- **WHEN** a hook asks about `gh pr create --title 'Retry with backoff?'
  --body-file body.md`, and `body.md` exists
- **THEN** the reader returns `Retry with backoff?` as the title

#### Scenario: A title taken from commits is unreadable

- **WHEN** a hook asks about `gh pr create --fill-first --body-file
  body.md`, or the same with `--fill` or `--fill-verbose`, and `body.md`
  exists
- **THEN** the reader reports each command as unreadable

### Requirement: The reader reads a GitHub MCP tool's body, comment and title keys

For a GitHub MCP tool, the reader SHALL return every string under a key
named `body` or `comment`, at any depth, as a body, one under `title` as
the title, and say that the post creates an issue when the tool creates
one.

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

#### Scenario: A subshell's commands are read

- **WHEN** a hook asks about `(cd sub && gh pr edit 3 --add-assignee @me)`
- **THEN** the reader reports that the line sends no post

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
command in it names no `gh`, is a `gh` command sending no text, or is one
of prose's **data commands**, which its scenarios list. A data command
counts only when none of its words is `gh` or a path ending in `/gh`. The
github-app skill's form counts as the `gh` command it runs.

#### Scenario: A command that sends no body is no post

- **WHEN** a hook asks about `gh pr edit 5 --add-label spec`, an assignee,
  reviewer or milestone edit, `gh pr ready`, a close without `--comment`,
  `gh pr list`, or `python3 /abs/github_app.py gh pr edit 5 --add-label
  spec`
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
- **THEN** the reader reports each command as unreadable

### Requirement: An interpreter given a code flag makes a post-verb line unreadable

On a line that mentions a gh post verb, a word naming an interpreter its
scenarios list, alone or as a path ending in `/<name>`, followed anywhere
later in its simple command by one of its code flags, SHALL make the line
unreadable, even where another requirement of this spec says the line
sends no post. The reader SHALL NOT parse the interpreter's options to
find the flag. The github-app skill's form and a line that only runs
prose's script SHALL be read by their own requirements.

#### Scenario: A gh post run as inline code is unreadable

- **WHEN** a hook asks about
  `python3 -c 'import os; os.system("gh pr comment 5 -b x")'`,
  `node -e 'require("child_process").execSync("gh pr comment 5 -b x")'`,
  `ruby -e 'system("gh pr comment 5 -b x")'` or
  `perl -e 'system("gh pr comment 5 -b x")'`
- **THEN** the reader reports each command as unreadable
- **AND** the interpreters and their code flags are `python`, `python3`
  and `python3.<n>` with `-c`; `node` and `bun` with `-e`, `-p`, `--eval`
  and `--print`; `perl` with `-e` and `-E`; `ruby` with `-e`; `php` with
  `-r`; and `sh`, `bash`, `dash` and `zsh` with `-c`

#### Scenario: Inline code after other options is unreadable

- **WHEN** a hook asks about `python3 -Ic '…'`, `node -pe '…'` or
  `python3 -W ignore -c '…'`, each running `gh pr comment 5 -b x`
- **THEN** the reader reports each command as unreadable
- **AND** a short code flag counts alone or as one letter of a word that
  starts with a single `-`, and a long one alone or followed by `=`

#### Scenario: Inline code beside a gh post verb is unreadable whatever it runs

- **WHEN** a hook asks about `python3 -c 'print(1)' && gh pr edit 5
  --add-label spec`, or about `timeout 5 node -e 'x()' && gh pr edit 5
  --add-label spec`
- **THEN** the reader reports each line as unreadable
- **AND** `python3 -c 'print(1)'` alone sends no post

#### Scenario: A code flag given to gh through the github-app skill is gh's

- **WHEN** a hook asks about `python3 /abs/github_app.py gh issue close 5
  -c 'done'`
- **THEN** the reader returns `done` as the body

### Requirement: Only allowlisted git is a data command beside a gh post verb

On a line that mentions a gh post verb, `git` SHALL count as a data
command only when the first word after `git` is a subcommand on the
allowlist that *git outside its allowlist is unreadable on a post-verb
line* gives, so `git -C . status` is not one, and none of its words is an
option that scenario lists as giving code to run.
Any other `git` use SHALL make the line unreadable, even where another
requirement of this spec says the line sends no post.

#### Scenario: git outside its allowlist is unreadable on a post-verb line

- **WHEN** a hook asks about a line that mentions a gh post verb and holds
  `git rebase -x 'gh pr comment 5 -b x' main`,
  `git submodule foreach 'gh issue create -t x -b y'`,
  `git bisect run gh pr comment 5 -b x`,
  `git config alias.p '!gh pr comment 5 -b x' && git p`,
  `git difftool -x 'gh pr comment 5 -b x'`,
  `git filter-branch --tree-filter 'gh pr comment 5 -b x'`,
  `git -c 'alias.p=!gh pr comment 5 -b x' p`,
  `git -C . -c 'alias.p=!gh pr comment 5 -b x' p` or
  `git -C status rebase -x 'gh pr comment 5 -b x' main`
- **THEN** the reader reports each line as unreadable
- **AND** the allowlist is `add`, `branch`, `checkout`, `commit`, `diff`,
  `fetch`, `log`, `ls-files`, `push`, `restore`, `rev-parse`, `show`,
  `stash`, `status`, `switch` and `tag`, and the options that give code
  are any word starting with `-c`, and `--config-env`, `--exec-path`,
  `--upload-pack`, `--receive-pack` and `--exec`, alone or followed by `=`

#### Scenario: An allowlisted git command beside a gh post verb is a data command

- **WHEN** a hook asks about `git push && gh pr edit 5 --add-label spec`
- **THEN** the reader reports that the line sends no post

### Requirement: Input to a no-post line reaches only data commands

In a line whose simple commands are all ones that *A line whose simple
commands send no text is no post* allows, input from a pipe or an input
redirection SHALL reach only data commands, or, when it reaches a single
simple command, a `gh` command that sends no text and uses no gh post
verb. Otherwise the line SHALL be unreadable. Input reaching `python`,
`python3` or `node` SHALL always make the line unreadable (design.md:
*Code given on the command line beside a gh post verb*).

#### Scenario: A gh post piped into a shell or an interpreter is unreadable

- **WHEN** a hook asks about `echo 'gh pr comment 5 -b x' | sh`,
  `echo 'gh pr comment 5 -b x' | python3`, or `python3 -` reading a
  heredoc that holds `os.system("gh pr comment 5 -b x")`
- **THEN** the reader reports each command as unreadable
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

- **WHEN** a hook asks about `cat c.md | gh pr view 5`, and about `cat
  c.md | gh pr edit 5 --add-label spec`
- **THEN** the reader reports the first as sending no post and the second
  as unreadable

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
SHALL end in `/github_app.py`, be a literal word, and be written out or a
`$G` the line assigns first. Nothing but that assignment SHALL come
before `python3` in the line. A line that mentions a gh post verb and
runs `python3 $G` with `G` unassigned SHALL be unreadable, its block
message saying how to fix it.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --body-file body.md`
- **THEN** the reader returns the file's text as the body

#### Scenario: Another script given gh's arguments is unreadable

- **WHEN** a hook asks about `python3 /tmp/other.py gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports the command as unreadable

#### Scenario: The github-app script with an identity is read

- **WHEN** a hook asks about `G=/abs/github_app.py && python3 "$G"
  --identity bot gh pr comment 5 --body-file c.md`
- **THEN** the reader returns the file's text as the body
- **AND** the script runs `gh pr`, `gh issue` or `gh api`, either
  directly or after `run --`
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
- **AND** so it does for `python3 "$G" gh api repos/o/r/pulls/5`, a read

#### Scenario: A gh api call through the github-app script is judged as a direct one

- **WHEN** a hook asks about `python3 /abs/github_app.py gh api
  repos/o/r/issues/5/comments -f body=hi`, and about `python3
  /abs/github_app.py --identity bot gh api -X DELETE
  repos/o/r/issues/comments/9`
- **THEN** the reader returns `hi` as the first's body, and reports that
  the second sends no post, as it would for the same `gh api` calls made
  directly

### Requirement: A gh api call is a read only as a plain gh command

A `gh api` call SHALL count as a **read** only when it is a simple
command whose command is `gh`, or the github-app skill's form of one,
whose every word is a literal word, except that its endpoint may hold `?`
and gh's `{owner}`, `{repo}` and `{branch}` placeholders, and that does
not write as *A gh api call writes by its method, fields, input or a
mutation* says. Any other `gh` followed by `api` SHALL mention a gh post
verb.

#### Scenario: A read with placeholders or a query string is a read

- **WHEN** a hook asks about `gh api repos/{owner}/{repo}/pulls/5 |
  python3 -c 'print(1)'`, and about `gh api search/issues?q=x`
- **THEN** the reader reports that each line sends no post

#### Scenario: A gh api call the reader cannot see whole mentions a post verb

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments $F`,
  `gh api -X "$M" repos/o/r/issues/5`, `cat a | xargs gh api
  repos/o/r/issues/5/comments`, or `sh -c 'gh api
  repos/o/r/issues/5/comments "$@"' _ -f body=x`
- **THEN** none is a read, and each line mentions a gh post verb

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

A `gh api` call writes as *A gh api call writes by its method, fields,
input or a mutation* says. For a write under
`repos/<owner>/<repo>/issues` or `.../pulls`, the reader SHALL read each
`body` field or `--input` key as a body, a `title` one as the title, and,
for a review, each comment's `body`. Each field SHALL be a literal word;
the endpoint need not be. It SHALL say that a `POST` to `.../issues`
creates an issue, as an MCP `create_issue` does.

#### Scenario: Each gh api body form is read

- **WHEN** a hook asks about an issue comment sent with `gh api`, its body
  given by `-f body=…`, `--raw-field body=…`, `-F body=…`,
  `--field body=…`, `-F body=@c.md` or `--input c.json`
- **THEN** the reader returns the body for each form, `@<file>` and
  `--input` reading the named file, and the `--input` file being JSON
  with a `body` key

#### Scenario: A new issue sent through gh api or MCP is reported as one

- **WHEN** a hook asks about `gh api repos/o/r/issues -f title=t -f
  body=b`, or about a GitHub MCP `create_issue` call with the `title` `t`
  and the `body` `b`
- **THEN** the reader returns both, and says that the post creates an issue
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
- **AND** the endpoint may have a leading `/` or none, and its `{owner}`
  and `{repo}` are read as placeholders

#### Scenario: A gh api review's nested comments are read

- **WHEN** a hook asks about `gh api repos/o/r/pulls/5/reviews -f
  body=ok -f 'comments[][path]=a.py' -f 'comments[][body]=Why?'`
- **THEN** the reader returns `ok` and `Why?` as bodies
- **AND** for `--input r.json`, where `r.json` holds `body` and a
  `comments` array whose items hold `body`, it returns each of them

### Requirement: A gh api write read from a file is read only as a whole command line

The reader SHALL read a `gh api` write that takes a field from a file,
through `-F` or `--field` with `@<file>`, or its input through
`--input`, only when the whole command line is that `gh api` command,
and SHALL report it as unreadable otherwise. A write whose fields are
all given in the command SHALL be read in a longer line too.

#### Scenario: A gh api body file after another command is unreadable

- **WHEN** a hook asks about `printf 'unsigned' > c.md && gh api
  repos/o/r/issues/5/comments -F body=@c.md`, or the same line with
  `--input c.json`, where both files exist
- **THEN** the reader reports each line as unreadable

#### Scenario: A gh api body given in the command is read in a longer line

- **WHEN** a hook asks about `cd /x && gh api repos/o/r/issues/5/comments
  -f body='done'`
- **THEN** the reader returns `done` as the body

### Requirement: The reader reads GraphQL posts and blocks a gh api write it can't read

In the thirteen mutations
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

- **WHEN** a hook asks about a `createIssue` mutation whose `body` is the
  literal `"b"`
- **THEN** the reader returns `b` as the body and says that the post
  creates an issue

#### Scenario: A GraphQL mutation with no body sends no post

- **WHEN** a hook asks about `gh api graphql` with an `addLabelsToLabelable`
  mutation, or a listed mutation with neither a `body` nor a `title`
- **THEN** the reader reports that each command sends no post

#### Scenario: A GraphQL mutation that can't be read is unreadable

- **WHEN** a hook asks about `gh api graphql -f query='mutation { … }'`,
  which the reader cannot parse, an `addDiscussionComment` mutation with a
  `body`, an `addComment` mutation whose `body` is a variable the call
  does not give, or a `createPullRequest` mutation whose `title` is a
  variable the call does not give
- **THEN** the reader reports each command as unreadable

#### Scenario: A gh api write with a body it does not read is unreadable

- **WHEN** a hook asks about `gh api -X POST repos/o/r/releases -f
  body=notes`, `gh api repos/o/r/issues/5/comments -F body=@missing.md`,
  or `gh api repos/o/r/pulls/5/reviews -f body=ok -F
  'comments[][body]=@missing.md'`, where `missing.md` does not exist
- **THEN** the reader reports each command as unreadable
- **AND** `gh api -X POST repos/o/r/milestones -f title=x` sends no post

#### Scenario: A gh api read is no post

- **WHEN** a hook asks about `gh api graphql -f query='{ viewer { login } }'`
  or `gh api -X GET search/issues -f q=x`
- **THEN** the reader reports that each command sends no post
