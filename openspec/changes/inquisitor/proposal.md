## Decisions

### Decided by Adam (2026-10-19)

Decisions 1 to 10 are recorded in the body of
[igor #211](https://github.com/adamstallard/igor/issues/211); 11 to 15 were
given on the same day and are recorded here first.

1. **Four filters run before any question reaches a person.**
   1. **Already answered:** the agent finds the earlier answer, cites where it
      is recorded, and does not ask. The earlier answer may be in another
      spec or another decision document: a decision record, a `DECISIONS.md`
      file, the decision block at the top of an issue, or a lore entry.
   2. **Deferrable:** the agent defers it without asking. The deferral stays
      visible: it is listed as not in this change, and filed as an issue if it
      outlives the change. A person who wants it now says so.
   3. **Not a real question:** unless at least two options each have merit,
      the agent takes the one it recommends and records it in a spec or
      decision document, without asking.
   4. **Cheap to reverse:** where two options have merit but switching later
      is cheap, the agent decides and records it, without asking.
2. **Every answer is recorded where the next agent will look.** Every question
   asked is logged, pointing to where its answer is recorded, so an agent
   using the inquisitor finds the answer instead of asking again.
3. **An answer that generalizes becomes lore.** Where a person's answer, or a
   lesson learned from a person, is broadly useful, it is proposed as a lore
   entry: a pull request to the team's lore repository.
4. **It covers any agent about to ask a person,** not only spec review or
   OpenSpec.
5. **A hook enforces it.** A hook on Claude Code's question picker
   (`AskUserQuestion`) makes an agent run the inquisitor before asking.
6. **It vets questions in posts too.** Questions in the pull request
   descriptions, comments and chat messages an agent is about to post pass
   the same filters. The inquisitor prepares each question that survives, and
   decides who to tag in it.
7. **It takes over the questions behind handed-back items:** items an Igor
   (one of the igor project's AI teammates) hands back because of a question
   it could not settle. This and decisions 9 and 10 belong to the Igor
   inquisitor role, an Igor that brings questions to a team discussion,
   which is out of scope here.
8. **It is restrained.** It batches related questions into one post, and
   keeps to a budget of posts per channel. The budget belongs to the role.
9. **A blocked Igor filters its own question, and the inquisitor role asks
   it.** The role's half is out of scope; the filters it runs are this skill's.
10. **A question reaches the inquisitor role through the blocked item
    itself.** Out of scope.
11. **The skill is useful locally, before any Igor role exists.** It needs
    nothing from Igor.
12. **Filter 1 also searches the team's lore repository**, the markdown
    entries with conditions, so lessons reach plain Claude Code sessions.
13. **Each "that was obvious" from a person is logged as a miss** against the
    filter that should have caught the question. The misses later inform
    edits to the skill, by pull request, never automatically.
14. **A lesson from the misses lands by its scope.** A lesson that holds for
    anyone using the skill is a pull request changing the skill in
    shared-skills. One that holds for one team or organization is a pull
    request to that team's lore repository. One that holds for one person goes
    to that person's own memory or `CLAUDE.md`. The question and miss logs
    stay in the person's own repositories and configuration, because they can
    hold private content, so a pull request to shared-skills carries only the
    generalized lesson.
15. **A skill's `DECISIONS.md` is its current reasoning in one place, not a
    log.** While a change is open, its reasoning lives in its proposal and
    design.md. When the change is archived, its lasting reasoning is folded
    into the `DECISIONS.md` of each skill it affects, rewriting the reasoning
    it supersedes rather than appending. This pull request's first commit
    puts the rule in `AGENTS.md`, and makes it the last task
    `openspec/config.yaml` asks of every change.

### For Adam to confirm

Decisions 16 to 18 are #211's proposals that apply to the skill; #211's
other proposals concern the role. The rest were needed to write the
requirements.

16. **A prepared question** states the recommended answer, what changes under
    the other answer, and a link to any related earlier decision, so that most
    can be answered "yes". In the picker the recommendation is the first
    option, and the hook checks it.
17. **Who is tagged in a post:** the fewest people who can decide; the
    script tags one. Only a person with write access to the repository the question
    concerns can decide it. Among them, the inquisitor tags the first it finds
    of: whoever approved the related earlier decision, a reviewer listed in
    that repository's `.inquisitor/reviewers`, then whoever last changed the
    files involved. #211 named "a reviewer or expert named in the team's
    configuration"; a file in the repository is that configuration, so
    every teammate's agent tags the same person. A person whose access can't
    be read counts as having none.
18. **Answers live in the repository the question concerns.** An answer
    spanning repositories also goes to the team's lore repository.
19. **The log is one file per question,** under `.inquisitor/questions/` at
    the root of that repository, committed with the work, with a random
    suffix in its name. A question about a public repository, or about none,
    is logged under `~/.config/shared-skills/inquisitor/` instead, the
    directory where the worktrees skill keeps its `worktrees.json`, because a
    question can carry private context from the session. *Rejected:* one log
    file that every question appends to, because two branches that each log
    a question then conflict when they merge.
20. **Only an answer with authority stops a question.** An answer is a
    decision document in the repository, an issue's decision block written
    by someone with write access, a logged answer from such a person, or an
    `active` lore entry scoped to everyone or to this repository. Everything
    else, including `provisional` and `deprecated` entries, is shown as
    input. An answer in the picker is the decision of the person running the
    session.
21. **An agent asks a person only through the picker,** where the host has
    one, so that the hook sees every question. *Rejected:* a hook at the end
    of the agent's turn that reads questions in its reply, because the person
    has already read the reply when that hook runs.
22. **Two calls prove the filters ran,** as prose's two calls prove its pass
    ran. The first prints the filters, runs filter 1's search and issues a
    token. The second records a verdict for each question. The hook allows a
    question only if the latest verdict on its text is "ask" and less than 2
    hours old, and fails open when it can't read its input. *Rejected:* a
    signed footer inside the question, because the person reads it in the
    picker. See design.md.
23. **The spec defines a question in a post** (*Questions in posts pass the
    same filters*). This settles #211's first open question, how to find the
    questions in a post's free text, by filter 4: the rule lives in one
    function, so changing it later is cheap. A post is
    vetted after prose's pass and before prose signs it.
24. **The post hook reads `gh` and GitHub MCP posts through the same code as
    prose's posting hook,** moved into `.agents/lib/gh-post/`. *Rejected:* a
    copy of that code, since prose's parser had about 25 places where it
    misread commands before it was cut to an allow-list. Also rejected:
    calling prose's copy, which would fail whenever prose is not installed.
    The hook covers GitHub only, as prose's does. A question in a Linear or
    Discord post is covered by the skill's instructions alone.
25. **Lore repositories are named in `~/.config/shared-skills/inquisitor.json`**
    as local clones, each with the GitHub owners it serves.
26. **Lessons are drafted from the misses only when a person asks** to review
    them, and the script refuses a lesson for shared-skills that quotes a
    logged question.
27. **The skill opens a lore pull request without asking first,** as a
    `provisional` entry, and reports its link: a pull request is itself a
    proposal, and closing it is cheap. It refuses one to a public lore
    repository when the answer came from a private repository.
28. **The hooks are enabled by default,** as prose's blocking hooks are.
    Installing the skill is the opt-in.
29. **A scenario about what the agent does is traced to a test that checks
    SKILL.md states the rule.** spec-trace's CI fails on an untagged scenario
    once the change is archived. *Rejected:* exempting those scenarios in
    spec-trace's baseline (`openspec/spec-trace-baseline.txt`), which takes
    no new lines.
30. **OpenSpec is used for new work in shared-skills.** A skill's spec holds
    what must be true of it, and its `DECISIONS.md` holds why. Existing skills
    get no spec until a change touches them. This pull request adopts OpenSpec,
    spec-check's decisions-first rule and spec-trace for the repository.

### Still open

Two facts are unmeasured. Tasks 0.1 to 0.3 measure the first, including the
shape of the hook's input, and task 0.4 measures the second.

- **Can a `PreToolUse` hook block `AskUserQuestion`?** If not, the picker is
  covered by the skill's instructions alone, and the README says so.
- **Can an agent without push access read another person's permission on a
  repository?** If not, every answer in a post counts as input wherever the
  agent lacks push access.

#211's other open questions: decision 23 settles the first. The other two,
how long to wait before following up and whether a discussion is a new kind
of surface for Igor, concern the role only.

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
- The questions that survive are prepared for a quick answer, batched, and
  asked through the picker or in a post. Each one asked is logged with where
  its answer is recorded, so the next agent finds the answer instead of asking.
- A hook blocks a question in the picker, or in a GitHub post, that has not
  been through the filters.
- A person's "that was obvious" is logged as a miss. Reviewing the misses
  produces lessons, each sent where it applies: the skill, a team's lore, or
  one person's memory.
- shared-skills adopts OpenSpec, with spec-check's decisions-first rule and
  spec-trace's CI check.

**Out of scope:** the Igor inquisitor role (#211: decisions 7, 9 and 10, and
the per-channel budget in decision 8), which brings surviving questions to a
team discussion.

## Capabilities

### New Capabilities

- `inquisitor`: filtering, preparing, asking and logging the questions an
  agent puts to a person, and learning from the questions that should not
  have been asked.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/inquisitor/` with its scripts, hooks and tests.
- prose: its posting hook's command reader moves to `.agents/lib/gh-post/`,
  unchanged in behaviour, so the inquisitor's post hook reads posts the same
  way.
- In each repository where it runs, the skill writes `.inquisitor/`.
- The README's skills table, and its list of skills that turn on a hook.
- This pull request's first commit adds `openspec/`, `AGENTS.md` and
  spec-trace's CI workflow to shared-skills.
