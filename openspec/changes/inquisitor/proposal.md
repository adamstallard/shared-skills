# Inquisitor

## Why

Agents ask people too many questions. Many were already answered, could wait,
have one sensible answer, or are cheap to undo, yet each costs the reviewer
time, and review is often the slowest step in the work. A question answered in
one person's private session is also lost to the rest of the team, so another
agent asks it again.

## What Changes

- A new skill, `inquisitor`, runs every question an agent is about to put to
  a person through four filters, and lets through only those a person must
  answer.
- The questions that survive are prepared for a quick answer. A question
  that blocks the agent's work is asked at once. Any other waits until the
  agent hands its work back to a person or ends its turn, and the agent goes
  on meanwhile with the answer it recommends. The waiting questions are then
  asked together, through the picker or in a post. Each one asked is logged with where
  its answer is recorded, in the repository or the team's lore repository it
  concerns, so the next agent finds the answer instead of asking.
- A hook blocks a question in the picker, or in a GitHub post, that has not
  been through the filters.
- A person's "that was obvious" is logged as a miss. Reviewing the misses
  produces lessons, each sent where it applies: the skill, a team's lore, or
  one person's memory.
- An answer session gives a person one place to answer the questions asked
  of them on GitHub, Linear and Discord. A relay identity posts each answer
  for them. The answer session runs the four filters on each incoming
  question too: it answers what is already recorded, replies to an agent's
  question that another filter clearly stops, and lets the person decline
  a question, logging a miss where one is due.
- shared-skills adopts OpenSpec, with spec-check and spec-trace's CI check.

design.md's *Decisions* gives the reason for each rule, and its *Open
Questions* lists what this change leaves unmeasured or needs from igor and
other changes. Each capability's decision record,
`openspec/specs/<capability>/decisions.md`, holds what no test can check:
constraints, rejected alternatives, and the evidence behind requirements.

**Out of scope:** the Igor inquisitor role, which brings surviving questions
to a team discussion, with its per-channel budget of posts. An Igor is one
of the AI teammates of igor, a separate project; igor #211 tracks the
role.

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
  relaying, editing, asking the asker, declining to answer, the filters
  it runs on incoming questions, the misses it logs, where its state
  lives, the lock, and the session's model in a discussion.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/inquisitor/` with its scripts, hooks and tests, and
  the answer session's mod, built from the prototype tagged
  `answer-session-ui-approved-v0.1-33`.
- The answer session posts through the github-app, linear-app and
  discord-bot skills, discord-bot as merged in shared-skills PR #1.
  In the session running the answer session, the model posts only as the
  person's relays: the inquisitor's post hook, and a new post hook in each
  of linear-app and discord-bot, block its posts under the person's own
  account and any carrying a reserved prefix, so only answers the person
  confirmed go out as theirs. The
  answer session's setup writes `~/.local/bin/answer`.
- prose: its posting hook's body reader moves to `.agents/lib/gh-shell/`,
  beside the command splitter and gh flag tables already there, so the
  inquisitor's post hook reads posts the same way. The reader also
  reads posts sent through the github-app skill, its `gh api` calls
  included, and `gh api` comments. It counts a `gh api` call as a
  possible post only when it can write, by its method, fields, input or a
  GraphQL mutation; prose's hook ignores `gh api` today. A `gh api` read
  is no mention of a gh post verb, so it passes even piped into a script,
  which on a line that mentions one would be blocked.
  A `gh api` write that takes a field from a file is readable only when
  it is the whole command line, because an earlier command in the line
  could rewrite the file. It also reads a post's title, and a title it can't
  read makes the call unreadable. It blocks as unreadable a `gh` alias or
  extension wherever it appears, since an alias can send a post the reader
  takes for none; so every prose user has read-only aliases such as gh's
  default `gh co`, and extensions such as `gh dash`, blocked too. On a
  line that mentions a gh post verb, it blocks as unreadable an
  interpreter with a code flag anywhere among its words, such as
  `python3 -c` or `node -e`. On such a line it also blocks a `git`
  command when the first word after `git` is not a subcommand on a fixed
  allowlist, so `git -C . status` is blocked, or when the command has an
  option that gives code to run, such as `-c`. Each of these can run a
  post the reader never sees.
  As prose's reader does today, it reads an unquoted `--body` or `-b` of
  one plain word, such as `--body hi`. prose's hook, which calls the
  reader, gains all of these changes.
- In each repository where it runs, the skill writes `.inquisitor/`. In a
  team's lore repository, it pushes to an orphan branch named `questions`,
  and the answer session's setup proposes, by pull request, the person's
  `relays/<login>.yaml` on its default branch, and a `relay-notice.yml`
  workflow that mentions a relay file's person on a pull request changing
  it.
- prose: its pass skips files under `.inquisitor/`, because a log or miss
  file quotes a question, and what a person said, word for word.
- github-app: its SKILL.md's examples hold the skill's script path in the
  shell variable `G`. They set `G` in the same command as each use, or write
  the script's full path, since the shared post reader reads `$G` only when
  the same command sets it.
- github-app, in a separate change not made here: its `token`, `run`,
  `credential get` and `wire` commands refuse an identity marked as a
  relay, so that no agent posts through a person's relay App by mistake.
  This change ships without it, and the inquisitor's README says what
  that leaves open.
- bug-hunter: its Step 9, the step that reports a run's recommendations
  and asks the person about each, runs each recommendation through the
  inquisitor's filters before asking (task 5.7).
- The README's skills table, and its list of skills that turn on a hook.
- This pull request's first commit adds `openspec/`, `AGENTS.md` and
  spec-trace's CI workflow to shared-skills.
