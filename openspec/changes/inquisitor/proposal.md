# Inquisitor

## Why

Agents ask people too many questions. Many were already answered, could wait,
have one sensible answer, or are cheap to undo, yet each costs the reviewer
time, and review is often the slowest step in the work. A question answered in
one person's private session is also lost to the team, so another agent asks
it again.

## What Changes

- A new skill, `inquisitor`, runs every question an agent is about to put to
  a person through four filters, in order: already answered, deferrable, not
  a real question, and cheap to reverse. It lets through only those a person
  must answer.
- Surviving questions are prepared for a quick answer. One that blocks the
  agent's work is asked at once. The rest wait until the agent hands its work
  back to a person or ends its turn, while the agent goes on with the answer
  it recommends; then they are asked together, through the picker (Claude
  Code's question tool) or in a post. Each question asked is logged, with
  where its answer is recorded, on a branch named `questions`: of the
  repository it concerns, or, for a question about a team rather than one
  repository, of the team's lore repository, which holds the reviewed entries
  given to agents. The next agent then finds the answer instead of asking. The person answering sees
  where the record will go, and how visible that place is, before answering.
- A hook blocks a question in the picker, or in a GitHub post, that has not
  been through the filters.
- A person's "that was obvious" is logged as a miss. Reviewing the misses
  produces lessons, each sent where it applies: the skill, a team's lore, or
  one person's memory.
- An answer session gives a person one place to answer the questions asked
  of them on GitHub, Linear and Discord. A relay identity, the person's own
  bot on each surface, posts each answer for them, and a file on the
  questions branch records it as theirs. The session runs the four filters
  on each incoming question too: it answers what is already recorded,
  replies to an agent's question that one of the other three filters clearly
  stops, and lets the person decline a question, logging a miss when they
  decline it as one the filters should have stopped.
- shared-skills adopts OpenSpec, with spec-check and spec-trace's CI check.

**Out of scope:** the Igor inquisitor role, which brings surviving questions
to a team discussion under a per-channel budget of posts. An Igor is one of
the AI teammates of igor, a separate project; igor #211 tracks the role.

design.md's *Decisions* gives the reason for each rule; its *Open Questions*
lists what this change leaves unmeasured or needs from igor and other
changes. What no test can check, such as constraints, rejected alternatives
and evidence, is in each capability's `openspec/specs/<capability>/decisions.md`.

## Capabilities

### New Capabilities

- `inquisitor`: filtering, preparing, asking and logging the questions an
  agent puts to a person, and learning from the questions that should not
  have been asked.
- `gh-post`: the shared post reader, `.agents/lib/gh-shell/`, which tells
  prose's posting hook and the inquisitor's post hook a post's body, that a
  call sends no post, or that it is unreadable.
- `answer-session`: where a person answers the questions asked of them in
  the channels they subscribe to, each answer posted by a relay identity:
  its configuration and setup, the four sources of questions, polling,
  relaying, editing, asking the asker, declining to answer, the filters it
  runs on incoming questions, the misses it logs, where its state lives, the
  lock, and what the session's model may do while discussing a question with
  the person.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/inquisitor/` with its scripts, hooks and tests, and
  the answer session's mod, built from the prototype tagged
  `answer-session-ui-approved-v0.1-33`.
- The answer session posts through the github-app and discord-bot skills,
  and on Linear by its own request with linear-app's token; discord-bot as
  merged in shared-skills PR #1, with its
  `read` changed (task 6.0) to return whether a message's author is a bot
  and which message it replies to.
- In the answer session's Claude Code session, the model has only its
  conversation, a tool that drafts a reply into the prompt box, a tool
  that hands its judgement of a message to the session's code in fixed
  fields, and read-only file tools. Claude Code, not a hook, is to enforce that; task
  0.34 measures how, and whether it can. The answer session's own code makes
  every post, push and fetch, so only answers the person confirmed go out as
  theirs.
- The answer session's setup writes `~/.local/bin/answer`, a command that
  starts Claude Code with the answer session open.
- prose: its posting hook's body reader moves to `.agents/lib/gh-shell/`,
  beside the command splitter and gh flag tables already there, so the
  inquisitor's post hook reads posts the same way. The reader, and so
  prose's hook:
  - reads posts sent through the github-app skill, its `gh api` calls
    included, and comments posted with plain `gh api`. It reads a post's title too, and a
    title it can't read makes the call unreadable.
  - counts a `gh api` call as a possible post only when it can write, by its
    method, fields, input or a GraphQL mutation; prose's hook ignores
    `gh api` today.
  - reads a `gh api` write that takes a field from a file only when it is
    the whole command line, because an earlier command in the line could
    rewrite the file.
  - blocks as unreadable a `gh` alias or extension wherever it appears,
    since an alias can send a post the reader takes for none. This blocks
    read-only ones for every prose user too, such as gh's default `gh co` and
    the extension `gh dash`.
  - on a line that mentions a gh post verb, blocks as unreadable an
    interpreter with a code flag anywhere among its words, such as
    `python3 -c` or `node -e`, and a `git` command that has an option giving
    code to run, such as `-c`, or whose first word after `git` is not on a
    fixed subcommand allowlist (so `git -C . status` is blocked). Each can
    run a post the reader never sees. A `gh api` read mentions no gh post
    verb, so these blocks pass it even piped into a script.
  - keeps reading an unquoted `--body` or `-b` of one plain word, such as
    `--body hi`.
- The `questions` branch is an orphan branch, pushed with no pull request.
  A repository may also hold `.inquisitor/reviewers`, the logins a
  posted question may tag. The answer session's setup can create a lore
  repository for a team that wants one.
- github-app: its SKILL.md's examples set the script path's shell variable
  `G` in the same command as each use, or write the script's full path,
  since the shared post reader reads `$G` only when the same command sets
  it.
- github-app, in a separate change (shared-skills issue #96): its `token`, `run`,
  `credential get` and `wire` commands refuse an identity marked as a relay,
  so no agent posts through a person's relay App by mistake. Until that lands,
  any agent on the person's machine can post through a relay App unseen by
  the post hook; the inquisitor's README says so.
- bug-hunter: its Step 9 runs each recommendation through the inquisitor's
  filters before asking the person about it (task 5.7). Its regression test
  for a security weakness stays out of public places until the weakness's
  security advisory is published, the rule the inquisitor applies to all
  public text it writes (task 5.8).
- The README's skills table, and its list of skills that turn on a hook.
- This pull request's first commit adds `openspec/`, `AGENTS.md` and
  spec-trace's CI workflow to shared-skills.
