## Purpose

The shared post reader tells a hook what body a command or tool call
would post on a GitHub issue or pull request, in a Discord message
through the discord-bot skill, or on Linear through the Linear MCP, and
each title or name the call sets, so prose's posting hook
and the inquisitor's post hook judge the same bodies, the inquisitor's
post hook judges titles too, and each blocks a call the reader reports as
unreadable.

## ADDED Requirements

### Requirement: The shared post reader reads a post's body from an allow-list

The shared post reader, `.agents/lib/gh-shell/`, SHALL tell a hook, for a
tool call, its post, that it sends no post, or that it is unreadable. For
a post, the reader returns the body the call sends.
prose's posting hook and the inquisitor's post hook SHALL read posts only
through it.

#### Scenario: Both post hooks read a post through the shared reader

- **WHEN** both hooks check `gh pr comment 5 --body-file c.md`, where
  `c.md` exists
- **THEN** each takes the post the reader returns, with `c.md`'s text as
  its body, and neither reads the command itself

### Requirement: A command that mentions no gh post verb sends no post

A command SHALL send no post when it **mentions** no **gh post verb**
(*A command mentions a gh post verb by one of a closed list of word
sequences*), unless input within the line reaches a `gh` command
(*Input to a no-post line reaches only data commands*).

#### Scenario: A gh command off the list passes unread

- **WHEN** a hook asks about `gh release create v1.2 --notes 'Ready?'`,
  `gh project item-create 1 --owner o --body 'Should retries back off?'`,
  `gh agent-task create 'Should retries back off?'`, `gh c 5 -b
  'Should retries back off?'`, where `c` is a gh alias for `pr comment`,
  and `$X pr comment 5 --body 'Should retries back off?'`, where `X`
  holds `gh`
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

### Requirement: A command mentions a gh post verb by one of a closed list of word sequences

A command SHALL **mention** a gh post verb when its text holds any of:

- `gh`, then `pr` or `issue`, then a post verb listed for that word;
- `gh`, then `api`, unless the line is a read (*A gh api call is a read
  only in a plain form*);
- a word that is `discord_bot` or ends in `discord_bot.py`, then a
  discord-bot post word.

#### Scenario: The gh post verbs are a closed list

- **WHEN** a hook asks about a command
- **THEN** its gh post verbs are `gh pr` with `create`, `new`, `edit`,
  `comment`, `review`, `revert`, `close` or `reopen`; `gh issue` with
  `create`, `new`, `edit`, `comment`, `close` or `reopen`; a `gh api`
  call that is not a read; and a discord-bot `post`, `edit` or `thread`
  call, though such a call holds no gh word
- **AND** a command's words count whether quoted or not, and `gh`, `pr`,
  `issue`, `api` and each verb count only as whole
  words, with no letter, digit or `_` just before and no letter, digit,
  `_` or `-` just after, so `--comments` holds no `comment` and
  `--comment` holds one; and `api` counts only with no `/` or `.` just
  before or after it, so `gh repo view o/api` mentions no post verb

### Requirement: A command that only runs prose's script sends no post

A line that is one simple command, whose command is `prose.py` or a path
ending in `/prose.py`, SHALL send no post, whatever its arguments.

#### Scenario: A command that only runs prose is no post

- **WHEN** a hook asks about `/abs/prose.py sign --goals 'approve the gh
  pr create body'`
- **THEN** the reader reports that the command sends no post

### Requirement: The reader reads a post only in a canonical form

For a Bash command, the reader SHALL return a body only for a
**canonical form** this spec lists: a command line of one simple command,
every word literal, or the github-app skill's line wrapping one. Any
other line that mentions a gh post verb SHALL be unreadable, unless
another requirement here says it sends no post. Each unreadable report SHALL
carry the canonical forms, which both hooks print when they block.

#### Scenario: A post chained to another command is unreadable and the block names the forms

- **WHEN** a hook asks about `cd /x && gh pr comment 5 --body-file c.md`,
  where `c.md` exists
- **THEN** the reader reports the command as unreadable, and the hook's
  block message lists the canonical forms, `gh pr comment <number>
  --body-file <file>` among them

#### Scenario: A gh post run through another shell is unreadable

- **WHEN** a hook asks about `sh -c 'gh pr comment 5 --body-file c.md'`,
  `bash -c 'gh issue create --body x'` or `eval 'gh pr comment 5 --body
  x'`
- **THEN** the reader reports each command as unreadable

#### Scenario: A command the reader can't read exactly is unreadable

- **WHEN** a hook asks about ``gh pr comment 5 --body `cat c.md` ``, or
  about `gh pr comment 5 --body $'x'`
- **THEN** the reader reports each command as unreadable

### Requirement: A literal word is one the shell does not expand

The reader SHALL count a word as a **literal word** only when it holds no
`$`, backtick or backslash outside single quotes, and no `*`, `?`, `[`,
`{` or `~` outside quotes.

#### Scenario: Only a word the shell leaves alone is literal

- **WHEN** the reader judges the words `'a $b'`, `"a b"`, `hi`, `"$X"`,
  `hi*` and `~/notes`
- **THEN** the first three are literal words and the last three are not

### Requirement: The canonical gh pr and gh issue posts are a closed list

A canonical `gh pr` or `gh issue` post SHALL be `comment <number>`,
`create`, `edit <number>`, `review <number>` with `--approve`,
`--request-changes` or `--comment`, or `close <number>` or `reopen
<number>`; its body given once, by `--body-file <file>` naming a file
that exists or `--body <word>`, or for `close` and `reopen` by
`--comment <word>`; and no other option but `--title` and those the
scenario below lists, each written long, and the value of one that
takes a value as the next word.

#### Scenario: A canonical gh post is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md
  --base main`, where `body.md` exists, about `gh issue comment 5 --body
  'Done.'`, and about `gh issue close 5 --comment 'done'`
- **THEN** the reader returns `body.md`'s text, `Done.` and `done` as
  their bodies
- **AND** the other options a canonical form may hold are `--repo`,
  `--base`, `--head`, `--draft`, `--label`, `--assignee`, `--reviewer`,
  `--milestone`, and, where gh has them, `gh pr edit`'s and `gh issue
  edit`'s `--add-` and `--remove-` options for reviewers, labels,
  assignees and projects, and `--remove-milestone`; only `--draft` takes
  no value
- **AND** `gh pr edit 5 --add-reviewer alice --remove-label wip --title t
  --body-file body.md`, where `body.md` exists, is read, its body
  `body.md`'s text

#### Scenario: A gh post in any other form is unreadable

- **WHEN** a hook asks about `gh pr comment 5 -b hi`, `gh pr comment 5
  --body=hi`, `gh pr comment 5 -F c.md`, `gh pr comment 5 --body "$(cat
  c.md)"`, `cat c.md | gh pr comment 5 --body-file -`, `gh pr comment 5
  --body-file missing.md`, where `missing.md` does not exist, `gh pr
  create --title t --template tmpl.md`, `gh pr create --fill`, `gh
  pr revert 5 --body x`, `gh pr new --body x` and `gh issue new
  --body x`, since neither `revert` nor `new` is a canonical verb, and
  `gh issue edit 5 -t x` and `gh issue edit 5 --title=x`
- **THEN** the reader reports each command as unreadable

### Requirement: A canonical gh pr or gh issue post may set a title

The reader SHALL return `--title`'s value in a canonical `gh pr` or `gh
issue` form as a title. A `gh pr edit` or `gh issue edit` giving
`--title <word>` and no body SHALL be canonical too, though other forms
need a body, and return only its title; a `create` still needs one.

#### Scenario: A gh post's title is read

- **WHEN** a hook asks about `gh pr create --title t --body-file body.md`,
  where `body.md` exists, and about `gh issue edit 5 --title 'Rename
  it?'`
- **THEN** the reader returns `t` as the first's title, beside its body,
  and `Rename it?` as the second's only title

### Requirement: The reader reads a GitHub MCP tool's body and comment keys

A **GitHub MCP tool** is one whose name starts `mcp__github__`,
`mcp__plugin_<name>_github__` or `mcp__claude_ai_GitHub__`.
For one, the reader SHALL return, at any depth, every string under a
key named `body` or `comment` as a body, and every string under a key
named `title` as a title.

#### Scenario: An MCP comment field is read

- **WHEN** a hook asks about a GitHub MCP tool whose input holds the
  string `ok` under a key named `comment`, and about one whose input holds
  `comments[0].body`
- **THEN** the reader returns `ok` and the nested string as bodies
- **AND** it reads `mcp__claude_ai_GitHub__add_issue_comment` with `body`
  `ok` as it reads `mcp__github__add_issue_comment`
- **AND** it returns `Retries?` as the title of a GitHub MCP tool whose
  input holds `title` `Retries?`

### Requirement: The reader reads a Linear MCP comment or issue description

For a tool named `save_comment` or `save_issue` under a **Linear MCP
prefix**, `mcp__linear__`, `mcp__plugin_<name>_linear__` or
`mcp__claude_ai_Linear__`, the reader SHALL return, as a Linear
message, `save_comment`'s `body` or `save_issue`'s `description`, and
`save_issue`'s `title` as a title. A
`save_issue` call holding `patch`, or holding `template` but no
`description`, SHALL be unreadable, since its text depends on what
Linear already holds.

#### Scenario: A Linear MCP comment and description are read

- **WHEN** a hook asks about `mcp__linear__save_comment` with `body` `User
  says: yes`, and about `mcp__linear__save_issue` with `title` `Retries?`
  and `description` `Should retries back off?`
- **THEN** the reader returns `User says: yes` and `Should retries back
  off?` as Linear messages, and `Retries?` as a title
- **AND** it reports as unreadable a `save_issue` call holding `patch`, or
  `template` with no `description`
- **AND** `mcp__claude_ai_Linear__save_comment` is read as
  `mcp__linear__save_comment` is

#### Scenario: A Linear MCP call with no text is no post

- **WHEN** a hook asks about `mcp__linear__save_issue` with only `id` and
  `state`
- **THEN** the reader reports that the call sends no post

### Requirement: Another Linear write tool sends no post only when it holds no text

For a Linear MCP tool named `save_*`, `create_*`, `update_*` or
`submit_*`, other than `save_comment` and `save_issue`, the reader SHALL
judge each string by the nearest object key above it: under a key on
the **no-text list** it holds no text; under `title`, `name`, `summary`
or `description` it is read, as the next requirement says; under any
other key it makes the call unreadable. A call holding only text-free strings sends no post, and so
does a Linear MCP tool with a name of any other form.

#### Scenario: The no-text list names keys that hold no text

- **WHEN** the reader judges a Linear write call's strings
- **THEN** it counts as text-free only a string under `id`, `issue`,
  `project`, `initiative`, `cycle`, `team`, `teamId`, `parent`,
  `parentId`, `lead`, `leadTeam`, `addTeams`, `removeTeams`, `setTeams`,
  `addInitiatives`, `removeInitiatives`, `setInitiatives`, `labels`,
  `pipeline`, `stage`, `releases`, `rangeFromRelease`, `rangeToRelease`,
  `urlOrId`, `commentId`, `draftId`, `user`, `externalUserId`,
  `githubTeamId`, `removedIssueLinks`, `commitSha`, `state`,
  `health`, `type`, `decision`, `statusAction`, `groupType`,
  `startDateResolution`, `targetDateResolution`, `startDate`,
  `targetDate`, `startedAt`, `completedAt`, `createdAt` or `color`
- **AND** each string in `addTeams` sits under `addTeams`, the string at
  `addedIssueLinks[0].issue` under `issue`, and the string at
  `patch[0].text` under `text`

#### Scenario: A Linear write call holding no text sends no post

- **WHEN** a hook asks about `mcp__linear__save_project` with `id`
  `P-ENG-12`, `state` `completed` and `targetDate` `2026-12-01`, about
  `mcp__linear__update_diff` with `urlOrId` `ENG-5`, `statusAction`
  `markReadyForReview` and `addedReviewRequests` `[{"user": "alice"}]`,
  and about `mcp__linear__submit_diff_review` with `urlOrId` `ENG-5`
  and `decision` `approved`
- **THEN** the reader reports that each call sends no post
- **AND** it reports `mcp__linear__get_issue` as sending no post

#### Scenario: A Linear write call holding text is unreadable

- **WHEN** a hook asks about `mcp__linear__save_document` with
  `content`, `mcp__linear__save_status_update` with `body`,
  `mcp__linear__save_release_note` with `id` and `patch`
  `[{"op": "append", "text": "Done?"}]`, and
  `mcp__linear__create_attachment_from_upload` with `issue` and
  `assetUrl`
- **THEN** the reader reports each call as unreadable

### Requirement: A Linear write tool's titles and descriptions are read

For a Linear write tool covered by *Another Linear write tool sends no
post only when it holds no text*, which leaves these four keys to this
requirement, the reader SHALL return each string under `title` or
`name` as a title, and each under `summary` or `description` as
**Linear summary text**: a Linear message marked as such, which prose's
posting hook reads as a body; `save_issue`'s `description` is never
Linear summary text.

#### Scenario: A Linear write call's titles, names, summary and description are read

- **WHEN** a hook asks about `mcp__linear__save_project` with `id`,
  `name` `Retries?` and `summary` `Should retries back off?`, and about
  `mcp__linear__save_milestone` with `project`, `name` `Beta` and
  `description` `Ship it?`
- **THEN** the reader returns `Retries?` and `Beta` as titles, and
  `Should retries back off?` and `Ship it?` as Linear summary text;
  prose's posting hook reads those two as bodies

### Requirement: The reader returns each title apart from bodies

The reader SHALL mark each title it returns as a title rather than a
body, with its surface, GitHub, Linear or Discord. A title is a
`title` or `name` value, or a `--title` or `--name` option's value, that
a call sets and this spec returns as one. A call that
sets a title and sends no body SHALL return its titles alone. prose's
posting hook SHALL skip titles, since prose signs bodies only.

#### Scenario: A title alone is returned as a title

- **WHEN** a hook asks about `gh pr edit 5 --title 'Retry?'`
- **THEN** the reader returns `Retry?` as a GitHub title and no body,
  and prose's posting hook lets the call through

### Requirement: The reader says whether a post goes through the github-app skill

For each post, the reader SHALL report whether it is sent by a call of
the github-app skill's script, which *The reader reads posts sent
through the github-app skill* finds.

#### Scenario: A github-app post is told from a plain gh post

- **WHEN** a hook asks about `python3 /abs/github_app.py --identity bot gh
  pr comment 5 --body-file c.md` and about `gh pr comment 5 --body-file
  c.md`, where `c.md` exists
- **THEN** the reader reports the first as sent through the github-app
  skill, and the second as not

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
- **AND** counts a simple command as naming `gh` when its text, quoted
  or not, holds `gh` as a whole word, as *The gh post verbs are a closed
  list* counts words

#### Scenario: A subshell's and an unquoted substitution's commands are read

- **WHEN** a hook asks about `(cd sub && gh pr edit 3 --add-assignee @me)`
  and about `echo $(gh pr edit 5 --add-assignee @me)`
- **THEN** the reader reports that each line sends no post
- **AND** it reports `(cd sub && gh pr comment 3 --body hi)` and
  `echo $(gh pr comment 5 --body yo)` as unreadable, since neither line is
  one simple command (*The reader reads a post only in a canonical form*)

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
command in it names no `gh`; is a `gh pr` or `gh issue` command with no
**text option**, run directly or through the github-app skill; is a `gh api`
read; or is a **data command** (its scenarios list them) with no word
that is `gh` or a path ending in `/gh`.

#### Scenario: A command that sends no body is no post

- **WHEN** a hook asks about `gh pr edit 5 --add-label spec`, `gh pr
  edit 5 --add-assignee x --add-reviewer y --milestone m`,
  `gh pr ready`, a close without `--comment`, `gh pr list`, or `python3
  /abs/github_app.py gh pr edit 5 --add-label spec`
- **THEN** the reader reports that each command sends no post
- **AND** it reports `cd x && gh api -X DELETE repos/o/r/issues/comments/9`
  as unreadable, since a `gh api` write is a gh post verb and no
  canonical form

#### Scenario: The text options are a closed list

- **WHEN** a hook asks about `cd x && gh pr edit 5 -db x`, chained so
  that no canonical form can read it
- **THEN** the reader reports the line as unreadable, since `-db` holds
  the text option `-b`
- **AND** the text options are `--body`, `--body-file`, `--title`,
  `--fill`, `--fill-first`, `--fill-verbose`, `--template`, `--recover`,
  `--comment`, `--editor` and `--web`, and any option word starting
  with a single `-`, not `--`, that holds one of the letters `b`, `F`,
  `t`, `c`, `f`, `T`, `e` or `w`

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

This rule covers a line whose simple commands are all ones *A line
whose simple commands send no text is no post* allows, and a line that
mentions no gh post verb but whose input reaches a `gh` command. Such a
line SHALL send no post when every command that input from a pipe or
redirection reaches is a data command, or when that input reaches just
one simple command, which is a `gh api` read or a `gh pr` or `gh issue`
command whose verb is a **no-text verb**; otherwise it SHALL be
unreadable.

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
- **AND** the no-text verbs are `gh pr` with `list`, `ls`, `status`,
  `checkout`, `co`, `checks`, `diff`, `view`, `ready`, `lock`, `unlock`
  or `update-branch`, and `gh issue` with `list`, `ls`, `status`,
  `delete`, `develop`, `lock`, `unlock`, `pin`, `unpin`, `transfer` or
  `view`, so `cat c.md | gh pr merge 5` is unreadable

#### Scenario: Input that reaches another gh command is unreadable

- **WHEN** a hook asks about `cat notes.md | gh release create v1
  --notes-file -`, and about `cat q.json | gh api repos/o/r/pulls/5`
- **THEN** the reader reports the first as unreadable, though `gh release`
  uses no gh post verb, and the second as sending no post, a `gh api` read

### Requirement: The reader reads posts sent through the github-app skill

The reader SHALL find a call of the github-app skill's script with the
shared library's functions its scenario names, and read it as the command
the script runs. It SHALL judge the line as if that command stood in the
call's place and the assignment naming the script were gone, so
`G=<path>; python3 "$G" gh …` is one simple command. A path held in a
variable counts as a literal one does: a literal path proves no more
about which script runs, since any file named `github_app.py` passes.

#### Scenario: A post sent through the github-app skill is read

- **WHEN** a hook asks about `python3 /abs/github_app.py gh pr create
  --title t --body-file body.md`, about `G="$HOME/github_app.py"; python3
  "$G" --identity bot gh pr comment 5 --body-file body.md`, and about
  `python3 $D/github_app.py --identity=bot run -- gh pr comment 5
  --body-file body.md`
- **THEN** the reader returns the file's text as each one's body
- **AND** a call is what `app_command` in `.agents/lib/gh-shell/gh_shell.py`
  reads as one, after any leading assignments, with the variables
  holding the script's path tracked by `app_assignments` in that file,
  and dropped by `forget_scripts` in `.agents/lib/gh-shell/handbacks.py`
  once a command such as `unset` or `source` may change them

#### Scenario: Another script given gh's arguments is unreadable

- **WHEN** a hook asks about `python3 /tmp/other.py gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports the command as unreadable

#### Scenario: The github-app script after another command is unreadable where a direct gh call is

- **WHEN** a hook asks about `cd x && python3 /abs/github_app.py gh pr
  comment 5 --body-file c.md`, where `c.md` exists, so a missing file is
  not what blocks it
- **THEN** the reader reports the command as unreadable, as it does the
  same line with `gh` called directly

#### Scenario: The github-app script through an unassigned variable is unreadable

- **WHEN** a hook asks about `python3 "$G" gh pr comment 5 --body-file
  c.md` where the command assigns `G` nowhere, and about
  `G=/abs/github_app.py; unset G; python3 "$G" gh pr comment 5
  --body-file c.md`
- **THEN** the reader reports each command as unreadable, since
  nothing in it shows that `$G` names a `github_app.py`, and the block
  message says to assign the variable in the same command or write the
  script's path

#### Scenario: A gh read through an unset G is no post

- **WHEN** a hook asks about `python3 "$G" gh pr view 12 --comments`, and
  the command assigns `G` nowhere
- **THEN** the reader reports that the command sends no post, since it
  mentions no gh post verb
- **AND** it reports `python3 "$G" gh api repos/o/r/pulls/5`, with `G`
  assigned nowhere, as unreadable: an unassigned `$G` is not the
  github-app skill's form, so *A gh api call is a read only in a plain
  form* does not count the call as a read

#### Scenario: A gh api call through the github-app script is judged as a direct one

- **WHEN** a hook asks about `python3 /abs/github_app.py gh api
  repos/o/r/issues/5/comments -X POST --input c.json`, where `c.json`
  holds `{"body": "hi"}`, and about `python3 /abs/github_app.py
  --identity bot gh api -X DELETE repos/o/r/issues/comments/9`
- **THEN** the reader returns `hi` as the first's body, and reports the
  second as unreadable

### Requirement: The reader reads discord-bot's post and edit only from a message file

The reader SHALL find a call of discord-bot's script, `discord_bot.py`,
in the forms *The reader reads posts sent through the github-app skill*
finds for github-app's. Its canonical form SHALL be `post` or `edit` with
`--message-file <file>` given once, its value the next word, naming a
file that exists, whose text is the body; it may hold other options,
but no `--message`. It SHALL report the post as a Discord
message.

#### Scenario: A Discord post or edit is read from its file

- **WHEN** a hook asks about `python3 /abs/discord_bot.py --identity
  relay post --channel ops --message-file m.md`, and about the same call
  with `edit --message-id 9` in place of `post --channel ops`, where
  `m.md` holds `User says: yes`
- **THEN** the reader returns `User says: yes` as each one's body, as a
  Discord message, so the inquisitor's post hook blocks each, since the
  body starts with the reserved prefix `User says: `
- **AND** it reports the `post` call after `cd x && ` as unreadable, as
  *The reader reads a post only in a canonical form* says

#### Scenario: A Discord message given any other way is unreadable

- **WHEN** a hook asks about `python3 /abs/discord_bot.py post --message
  yes`, `printf 'User says: yes' | python3 /abs/discord_bot.py post
  --message -`, `python3 /abs/discord_bot.py post --message-file=m.md`,
  `python3 /abs/discord_bot.py post --message-file a.md --message-file
  b.md`, and `python3 -m discord_bot post --message-file m.md`, whose
  `discord_bot` is a module name, not a path to the script
- **THEN** the reader reports each command as unreadable

#### Scenario: A Discord delete or read is no post

- **WHEN** a hook asks about `python3 /abs/discord_bot.py delete
  --message-id 9` and `python3 /abs/discord_bot.py read --limit 5`
- **THEN** the reader reports that each command sends no post

### Requirement: A discord-bot thread's name is read as a title

For a call of discord-bot's script with `thread`, found as *The reader
reads discord-bot's post and edit only from a message file* finds one,
the canonical form SHALL give `--name` once, its value the next word,
which the reader returns as a Discord title, and no other option but
`--identity`, `--channel` and `--message-id`, each at most once, its
value the next word.

#### Scenario: A thread's name is a title

- **WHEN** a hook asks about `python3 /abs/discord_bot.py thread
  --message-id 9 --name Retries`
- **THEN** the reader returns `Retries` as its title
- **AND** it reports a `thread` call giving `--name=Retries`, `--name`
  twice, or `--na x`, which discord-bot would take for `--name`, or
  after `cd x && `, as unreadable

### Requirement: A simple command holding a discord-bot post word counts as naming gh

A simple command holding a word that is `discord_bot` or ends in
`discord_bot.py`, followed later by a **discord-bot post word**,
`post`, `edit` or `thread`, SHALL count as
holding a word that is `gh`, so the rules under which a command naming
no `gh` sends no post never apply to it.

#### Scenario: A discord-bot post outside the reader's form is unreadable

- **WHEN** a hook asks about `sh -c 'python3 /abs/discord_bot.py post
  --message-file m.md'`, and about `/abs/discord_bot.py post
  --message-file m.md`, run without `python3`
- **THEN** the reader reports each command as unreadable, so the post
  hooks block it

### Requirement: A gh api call is a read only in a plain form

A `gh api` call SHALL be a **read** only as a simple command run by
`gh` or in the github-app skill's form, with no `--input`, `-F`,
`--field`, `-H` or `--header`, every word literal except that an endpoint may hold
`?` or `{owner}`, `{repo}` or `{branch}`, and either no method and no
field, or `-X GET`, written so, and only `-f` fields. Such a command
calling the endpoint `graphql` SHALL also be a read when its only fields
are `-f`, one of them `query`, whose value holds no word `mutation`.

#### Scenario: A plain read is a read

- **WHEN** a hook asks about `gh api repos/{owner}/{repo}/pulls/5`,
  `gh api 'search/issues?q=x'`, `gh api -X GET search/issues -f q=x`,
  `gh api graphql -f query='{ viewer { login } }'`, and
  `G=/abs/github_app.py && python3 "$G" gh api repos/o/r/pulls/5`
- **THEN** the reader reports that each line sends no post

#### Scenario: A gh api call in any other form is no read

- **WHEN** a hook asks about `gh api search/issues -f q=x`, which gh sends
  as `POST`, `gh api repos/o/r/issues/5/comments $F`, `gh api -X "$M"
  repos/o/r/issues/5`, `gh api graphql -f query='mutation { x }'`, and
  `gh api graphql -F query=@q.graphql`
- **THEN** none is a read, and the reader reports each as unreadable,
  since none is a canonical post

### Requirement: The canonical gh api posts are a closed list

A canonical `gh api` post SHALL be the words `gh api`, an endpoint and
method its scenario lists, `-X` and that method, and `--input` naming a
file that exists and holds a JSON object, in any order and nothing else.
The reader SHALL return the object's `body` as the body and, for a
review, each `body` in its `comments`, and its `title` as a title. A
`body` or `title` that is not a string, or an object with no `body`,
`title` or review comments, SHALL make the call unreadable.

#### Scenario: A canonical gh api post is read

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments -X POST
  --input c.json`, where `c.json` holds `{"body": "Done."}`, and about
  `gh api repos/o/r/pulls/5/reviews -X POST --input r.json`, where
  `r.json` holds `body` `ok` and a `comments` array whose one item holds
  `body` `Why?`
- **THEN** the reader returns `Done.`, and `ok` and `Why?`, as bodies
- **AND** the endpoints and methods are `POST repos/<owner>/<repo>/issues`,
  `PATCH repos/<owner>/<repo>/issues/<number>`, `POST
  repos/<owner>/<repo>/issues/<number>/comments`, `PATCH
  repos/<owner>/<repo>/issues/comments/<id>`, `POST
  repos/<owner>/<repo>/pulls`, `PATCH repos/<owner>/<repo>/pulls/<number>`,
  `POST repos/<owner>/<repo>/pulls/<number>/comments`, `PATCH
  repos/<owner>/<repo>/pulls/comments/<id>` and `POST
  repos/<owner>/<repo>/pulls/<number>/reviews`, each `<owner>` and
  `<repo>` a name and each `<number>` and `<id>` digits

#### Scenario: A gh api write in any other form is unreadable

- **WHEN** a hook asks about `gh api repos/o/r/issues/5/comments -f
  body=hi`, the canonical issue comment with its endpoint written
  `/repos/o/r/issues/5/comments`, `repos/{owner}/{repo}/issues/5/comments`,
  `repos/o/r/issues/5/comments?x=1` or `repositories/1/issues/5/comments`,
  the same with `-f x=1` added, `gh api -X POST repos/o/r/releases --input
  n.json`, and `gh api -X DELETE repos/o/r/issues/comments/9`
- **THEN** the reader reports each command as unreadable
