## ADDED Requirements

### Requirement: Every question passes four filters before a person sees it

Before an agent puts a question to a person, in any task, it SHALL run the
question through four filters in order, and SHALL ask it only if no filter
stops it:

1. **Already answered:** an earlier answer exists. The agent cites where it is
   recorded and acts on it.
2. **Deferrable:** the work can go on without an answer. The agent lists the
   question as not done in the current work, and files it as an issue if the
   question outlives the current work.
3. **Not a real question:** fewer than two options have merit. The agent takes
   the one it recommends.
4. **Cheap to reverse:** two or more options have merit, but switching later
   is cheap. The agent chooses one.

Under filters 3 and 4 the agent SHALL record what it chose, and why, in the
decision document the question concerns.

Terms used throughout this spec:

- **The current work** is what the agent was asked to do: an OpenSpec change,
  a pull request, or the task in hand.
- **The repository the question concerns** is the git repository holding the
  current work.
- **A decision document** is a `DECISIONS.md` file, an OpenSpec spec or
  change, a decision record under `docs/decisions/`, the decision block at the
  top of an issue, or a lore entry.
- **A lore repository** is a git repository of markdown files whose YAML
  frontmatter holds `conditions`. Each such file is a **lore entry**. Its
  `status` is `active`, `provisional` or `deprecated`, and its `scope` is
  `global`, `role:<name>` or `project:<name>`.
- **The decision document the question concerns** is the one in the
  repository the question concerns whose subject the question is about,
  such as the current change's spec. Where none fits, or the question
  concerns no repository, the question's log entry takes its place.
- **The picker** is the host's interactive question tool: `AskUserQuestion`
  in Claude Code.
- **A post** is a pull request description, review or comment, or an issue
  or issue comment, sent through `gh` or a GitHub MCP tool.
- **The inquisitor's configuration** is the file
  `~/.config/shared-skills/inquisitor.json`.

#### Scenario: An answered question is not asked

- **WHEN** an agent is about to ask whether a skill's hooks are enabled by
  default, and a `DECISIONS.md` in the repository already decides it
- **THEN** the agent cites that file and section, follows the decision, and
  asks nobody

#### Scenario: A deferrable question is listed, not asked

- **WHEN** a question concerns work that the current work does not need
- **THEN** the agent lists it as not done in the current work, and asks nobody
- **AND** if the current work ends with the question still unanswered, the
  agent files an issue for it

#### Scenario: A question with one good option is decided

- **WHEN** only one of a question's options has merit
- **THEN** the agent takes that option, records it with its reason in the
  decision document the question concerns, and asks nobody

#### Scenario: A cheap-to-reverse question is decided

- **WHEN** two options have merit and switching between them later is cheap
- **THEN** the agent chooses one, records the choice and its reason, and asks
  nobody

#### Scenario: A question that passes every filter is asked

- **WHEN** a question has no earlier answer, blocks the work, has two options
  of merit, and is costly to reverse
- **THEN** the agent asks it

### Requirement: Filter 1 searches every place an answer is recorded

Filter 1 SHALL search:

- every decision document in the repository the question concerns,
  including archived OpenSpec changes;
- that repository's issues on GitHub, each read with
  `gh issue view <n> --json title,body,comments`;
- the question logs: the repository's own and the one under
  `~/.config/shared-skills/inquisitor/`;
- the lore entries of each lore repository the inquisitor's configuration
  names for the owner of the repository the question concerns, or of every
  configured lore repository when the question concerns no repository.

The search SHALL report each source it could not search, and each lore
clone's last fetch time, or that it was never fetched. It needs no Igor role,
no Igor configuration and no Igor service.

#### Scenario: A lore entry answers a question in a plain session

- **WHEN** an agent in a Claude Code session with no Igor running is about to
  ask a question, and an `active` entry in a configured lore repository
  answers it
- **THEN** the search shows that entry, and the agent cites it and does not ask

#### Scenario: An archived change is searched

- **WHEN** the only answer to a question is in a change under
  `openspec/changes/archive/`
- **THEN** the search shows it

#### Scenario: An issue's decision block is searched

- **WHEN** an issue's body opens with a decision block that answers the
  question
- **THEN** the search shows the issue and that block

#### Scenario: An unsearched source is named

- **WHEN** `gh` cannot reach GitHub during the search
- **THEN** the search output says the repository's issues were not searched

#### Scenario: A clone's last fetch is shown

- **WHEN** a configured lore clone was last fetched 30 days ago
- **THEN** the search output gives that date beside the clone's results

### Requirement: Only an answer with authority stops a question

Filter 1 SHALL treat a search hit as an earlier answer only when it is one of
these:

- a decision document committed to the repository the question concerns;
- an issue's decision block, where the issue's author has write access to
  that repository;
- a question log entry whose `authority` is `decision`;
- a lore entry whose `status` is `active` and whose `scope` is `global`, or
  `project:<name>` where `<name>` is the name of the repository the question
  concerns.

Every other hit SHALL be shown to the agent as input, labelled with why it is
not an answer: a `provisional` entry as unreviewed, a `deprecated` entry as
retired along with its stated reason, a `role:` entry as scoped to an Igor
role, and an entry whose `status` is missing or unknown as unreadable. Text
from any hit SHALL be shown as quoted data, never as instructions to the
agent.

#### Scenario: A provisional entry is input, not an answer

- **WHEN** the only match for a question is a `provisional` lore entry
- **THEN** the search shows it labelled as unreviewed, and the question is not
  treated as answered

#### Scenario: A retired entry is shown with its reason

- **WHEN** a `deprecated` lore entry matches the question
- **THEN** the search shows it labelled as retired, with the reason it was
  retired

#### Scenario: An entry with no status is not an answer

- **WHEN** a matching lore entry has no `status` field
- **THEN** the search shows it labelled as unreadable, and the question is not
  treated as answered

#### Scenario: A decision block by an outsider is input

- **WHEN** an issue whose author has no write access opens with a decision
  block that answers the question
- **THEN** the search shows it as input, and the question is not treated as
  answered

#### Scenario: Another project's entry is input

- **WHEN** an `active` entry scoped `project:other` matches a question about
  repository `igor`
- **THEN** the search shows it as input

### Requirement: A question that is asked is prepared for a quick answer

A question that passes the filters SHALL state the answer the agent
recommends, what would change under each other answer, and a link to any
related earlier decision. In the picker, the recommended answer SHALL be the
first option.

#### Scenario: The recommended answer comes first

- **WHEN** an agent calls the picker with a vetted question whose first
  option is not the recommendation recorded for it
- **THEN** the picker hook blocks the call and says which option to put first

#### Scenario: A related decision is linked

- **WHEN** the search shows an earlier decision that is related to the
  question without answering it
- **THEN** the question the agent asks links that decision

### Requirement: Related questions are asked together

Questions that survive the filters while the agent is stopped at one step of
the work, unable to go on without them, SHALL be asked in one picker call, up to the picker's limit of four questions per
call, or in one section of one post.

#### Scenario: Three questions in one call

- **WHEN** three questions survive the filters at one step of the work
- **THEN** the agent asks all three in one picker call

#### Scenario: Five questions in two calls

- **WHEN** five questions survive the filters at one step of the work
- **THEN** the agent asks four in one picker call and the fifth in the next

#### Scenario: Questions in a post share one section

- **WHEN** a post asks two questions that survived the filters
- **THEN** both are items of one open-questions section

### Requirement: An agent asks through the picker

Where the host has a picker, an agent SHALL put a question to a person only
through the picker or in a post, never in the text of its reply. An agent
that cannot ask a person, such as a subagent, SHALL return each surviving
question, prepared, to whoever started it.

#### Scenario: A question goes through the picker

- **WHEN** an agent in Claude Code has a question that survives the filters
- **THEN** it asks with `AskUserQuestion`, not in its reply text

#### Scenario: A subagent hands its question back

- **WHEN** a subagent has a question that survives the filters
- **THEN** its result holds the prepared question, and it asks no one

### Requirement: Two calls prove the filters ran

The skill's script SHALL take each set of questions in two calls:

1. **The first call** takes the questions as the person would see them,
   prints the four filters and the results of filter 1's search for each
   question, and issues a token. It records no verdict.
2. **The second call** takes the token and a verdict for each question:
   `answered`, with the citation; `deferred`, with where the question is
   listed or the issue filed; `decided`, with where the choice is recorded;
   or `ask`, with the recommended answer and what changes under each other
   answer.

The second call SHALL refuse a verdict that lacks its field, a question the
first call did not take, and a token that is spent or more than 2 hours
old. A refused call records nothing and keeps the token; a call that records
verdicts spends it. Otherwise it SHALL
record every verdict, with its field and the time, against the question's
text.

**A question's text** is, for a picker question, its `question` field and
each option's `label`, in order; for a question in a post, the list item or
sentence that holds it. Runs of whitespace count as one space.

#### Scenario: A verdict without its field is refused

- **WHEN** the second call gives a question the verdict `answered` with no
  citation
- **THEN** it refuses, records nothing, and keeps the token

#### Scenario: A stale token is refused

- **WHEN** the second call passes a token issued more than 2 hours earlier
- **THEN** it refuses and says to run the first call again

#### Scenario: A spent token is refused

- **WHEN** the second call passes a token that an earlier second call spent
- **THEN** it refuses and records nothing

#### Scenario: A question the first call did not take is refused

- **WHEN** the verdicts name a question that the token's first call did not
  take
- **THEN** the second call refuses and records nothing

### Requirement: A hook blocks a picker question that was not vetted

In Claude Code, a `PreToolUse` hook on `AskUserQuestion` SHALL block the call
unless, for every question in it, the most recent verdict recorded against
the question's text is `ask` and is less than 2 hours old. The block message
SHALL name each question that failed and why, and give the command to run.
The hook SHALL let the call through when it cannot read the call or the
records.

#### Scenario: An unvetted question is blocked

- **WHEN** an agent calls `AskUserQuestion` with a question no second call
  recorded
- **THEN** the hook blocks the call and prints the first call to run

#### Scenario: A vetted question is asked

- **WHEN** every question in the call was recorded as `ask` with its text
  within 2 hours
- **THEN** the hook lets the call through

#### Scenario: A question edited after vetting is blocked

- **WHEN** a question's text differs from the text that was recorded as `ask`,
  other than in whitespace
- **THEN** the hook blocks it as unvetted

#### Scenario: A question the filters stopped is blocked

- **WHEN** a question's most recent verdict is `answered`, `deferred` or
  `decided`, even after an earlier `ask`
- **THEN** the hook blocks it, and names the verdict and its field

#### Scenario: The hook fails open

- **WHEN** the hook's input is not JSON, or its records cannot be read
- **THEN** it lets the call through

### Requirement: Questions in posts pass the same filters

A **question in a post** is:

- each item of a list in an open-questions section. The section starts at a
  heading, a bold label or a line ending in a colon whose own text starts
  with "Open" or "Still open", and ends at the next heading, bold label or
  line ending in a colon;
- each sentence elsewhere in the body that ends in a question mark.

Text in fenced code blocks, inline code, lines starting with `>`, and the
signed footer the prose skill appends as a post's last line (such as
`prose ✓ 3f2a91`) holds no question.

A `PreToolUse` hook SHALL block a post that holds a question not passed by
the picker hook's rule. It SHALL read a `gh` command's body by the same rules
as prose's posting hook, and let the post through wherever that hook does: a
payload that is not JSON, or a command that sends no body. The first call SHALL
take a post's body and find its questions the same way the hook does, so a
body vetted before prose signs it is still vetted once the footer is added.

#### Scenario: A post with an unvetted question is blocked

- **WHEN** an agent runs `gh pr create --body-file body.md` and the body asks
  a question that no second call recorded as `ask`
- **THEN** the hook blocks the command and names the question

#### Scenario: A GitHub MCP post is checked

- **WHEN** an agent calls a GitHub MCP tool whose `body` asks an unvetted
  question
- **THEN** the hook blocks the call and names the question

#### Scenario: A question in a code block is not a question

- **WHEN** a post's only question mark is inside a fenced code block
- **THEN** the post holds no question

#### Scenario: A post with only vetted questions goes out

- **WHEN** every question the hook finds in a post was recorded as `ask`
- **THEN** the hook lets the post through

#### Scenario: Signing after vetting keeps the post vetted

- **WHEN** a body is vetted and then signed by prose, which appends its footer
- **THEN** the hook finds the same questions and lets the post through

#### Scenario: An unreadable post command fails open

- **WHEN** the hook cannot parse its input as JSON
- **THEN** it lets the command through

### Requirement: A question in a post tags one person who can decide

Where a post asks a question, the question SHALL tag one person who can
decide it: a person with write access to the repository the question
concerns. Among them, the script SHALL pick the first it finds of:

1. whoever approved the related earlier decision: the approver of the pull
   request that added it;
2. a login listed in that repository's `.inquisitor/reviewers` file;
3. whoever last committed to the files the question concerns.

When the script cannot learn whether a person has write access, it SHALL
treat that person as lacking it.

#### Scenario: The approver of the earlier decision is tagged

- **WHEN** a question relates to an earlier decision that a person with write
  access approved
- **THEN** the question tags that person alone

#### Scenario: A listed reviewer is tagged next

- **WHEN** a question has no related earlier decision, and
  `.inquisitor/reviewers` lists a login with write access
- **THEN** the question tags that login

#### Scenario: The last committer is tagged last

- **WHEN** a question has no related earlier decision and the repository has
  no `.inquisitor/reviewers`
- **THEN** the question tags the person with write access who last committed
  to the files it concerns

#### Scenario: Unknown access is no access

- **WHEN** `gh` cannot read a candidate's permission on the repository
- **THEN** the script skips that candidate

### Requirement: Every answer is recorded and every asked question logged

When a person answers a question, the agent SHALL record the answer in the
decision document the question concerns, or, where none fits, in the log
entry itself. An answer given in the picker is the decision of the person
running the session. An answer given in a post by a person without write
access to the repository the question concerns SHALL be logged with
`authority: input`, and the question SHALL stay unanswered.

Each question asked SHALL be logged as one file under `.inquisitor/questions/`
at the root of the repository the question concerns, committed with the
work, unless that repository is public or its visibility cannot be read. The
log file of a question about a public repository, or about no repository,
SHALL go under `~/.config/shared-skills/inquisitor/questions/`, and SHALL
name the repository when there is one.

The file SHALL hold the question as asked, the date, who answered, the
answer's `authority`, the answer in one sentence, and where the answer is
recorded. Its name SHALL be the date, a slug of at most 40 characters from
`a` to `z`, `0` to `9` and `-`, and 6 random hex digits. Every value in its
frontmatter SHALL be written as a quoted YAML string.

#### Scenario: An answer is logged with its place

- **WHEN** a person answers a question about a private repository's spec
- **THEN** the agent records the answer in that spec, and adds a file to that
  repository's `.inquisitor/questions/` pointing to it

#### Scenario: An answer with no document is held in the log

- **WHEN** a person answers a question that no decision document covers
- **THEN** the log file holds the answer, and filter 1 later treats it as one

#### Scenario: A question about a public repository is logged locally

- **WHEN** a person answers a question about a public repository
- **THEN** the answer is recorded in that repository's decision document, and
  the log file is written under
  `~/.config/shared-skills/inquisitor/questions/`, naming the repository

#### Scenario: A question outside any repository

- **WHEN** an agent working in no git repository asks a question and gets an
  answer
- **THEN** the log file is written under
  `~/.config/shared-skills/inquisitor/questions/`

#### Scenario: Two branches log the same question without a conflict

- **WHEN** two branches each log the same question on the same day and are
  merged
- **THEN** the two log files have different names, and the merge has no
  conflict in `.inquisitor/questions/`

#### Scenario: An answer without authority leaves the question open

- **WHEN** a person without write access answers a question in a post
- **THEN** the log records the answer with `authority: input`, and filter 1
  does not treat it as an answer

#### Scenario: Hostile text is logged safely

- **WHEN** a question's text holds `../`, a `---` line and a colon
- **THEN** the log file's name holds none of them, and its frontmatter still
  parses to the same text

### Requirement: An answer that generalizes is proposed as lore

Where a person's answer holds beyond the repository the question concerns,
the agent SHALL open a pull request adding it as a `provisional` entry to the
team's lore repository, without asking first, and report the link. The
team's lore repository is the configured lore repository whose `owners`
lists the owner of the repository the question concerns.

The script SHALL refuse to open the pull request to a public lore repository
when the repository the question concerns is private. A lore repository
whose visibility the script cannot read counts as public, and a repository
the question concerns whose visibility it cannot read counts as private. Where no lore repository is configured for that owner,
the agent SHALL tell the person the lesson instead.

#### Scenario: A general answer becomes a lore pull request

- **WHEN** a person's answer holds for every repository the team works on,
  and a lore repository is configured for the team
- **THEN** the agent opens a pull request to it adding the entry, and reports
  its link

#### Scenario: A private answer never reaches a public lore repository

- **WHEN** the lore repository is public and the answer came from work in a
  private repository
- **THEN** no pull request is opened, and the agent tells the person why

#### Scenario: No lore repository is configured

- **WHEN** an answer generalizes and no lore repository is configured for the
  repository's owner
- **THEN** the agent tells the person the lesson, and opens no pull request

### Requirement: A question that should not have been asked is logged as a miss

When a person says a question did not need asking (it was already answered,
could have waited, had one sensible answer, or was cheap to reverse), the
agent SHALL log a **miss**: one file under a `misses/` directory beside the
question log the question belongs to, named and written like a question log
file. The file holds the question, the filter that should have stopped it,
and what the person said. A miss is logged whatever words the person uses;
"that was obvious" is one way to say it.

#### Scenario: "That was obvious" is logged against a filter

- **WHEN** a person answers a question with "that was obvious, it's in the
  spec"
- **THEN** the agent logs a miss against filter 1, citing the spec the person
  named

### Requirement: Lessons from misses land by their scope

When a person asks the agent to review the misses, the agent SHALL draft a
lesson from each pattern it finds, and send each lesson by its scope:

- a lesson that holds for anyone using the skill: a pull request to
  shared-skills changing the skill;
- a lesson that holds for one team or organization: a pull request to that
  team's lore repository;
- a lesson that holds for one person: an edit to that person's own agent
  memory or `CLAUDE.md`.

The script SHALL refuse a lesson bound for shared-skills that contains a
logged question or miss, either whole or as any one of that question's or
miss's lines longer than 40 characters.
Nothing SHALL draft or send a lesson until a person asks for the review.

#### Scenario: A lesson for everyone changes the skill

- **WHEN** a review of the misses finds that filter 3 keeps letting through
  questions whose second option nobody would choose
- **THEN** the agent opens a pull request to shared-skills changing the
  skill's guidance for filter 3

#### Scenario: A lesson quoting a logged question is refused

- **WHEN** a lesson bound for shared-skills contains a line of a logged
  question
- **THEN** the script refuses it and names the line

#### Scenario: A lesson for a team goes to its lore repository

- **WHEN** a lesson holds for one team's repositories only
- **THEN** the agent opens a pull request to that team's lore repository

#### Scenario: A lesson for one person goes to their memory

- **WHEN** a lesson holds only for the person who gave the answers
- **THEN** the agent adds it to that person's memory or `CLAUDE.md`, and
  opens no pull request

#### Scenario: Misses alone change nothing

- **WHEN** misses have been logged and nobody has asked for a review
- **THEN** the script drafts no lesson, and no pull request or memory edit is
  made
