## Proving the filters ran

The hook can't judge whether a question has merit; only the agent can. So
the design makes skipping the filters fail, and leaves the agent's verdicts
to be judged in review. The mechanism copies the two script calls the prose
skill uses to prove its rewrite pass ran (`.agents/skills/prose/DECISIONS.md`,
*The rules are on screen before a signature*). The two calls prove the filters were
printed and the search ran before each verdict; they do not prove the agent
judged well.

1. `inquisitor.py vet --questions q.json` takes the questions exactly as they
   will reach the picker: the JSON array that `AskUserQuestion` takes as
   `questions`. `vet --post body.md` takes a post's body and finds its
   questions with the function the post hook uses. Either way it prints the
   four filters, runs filter 1's search on each question and prints the hits,
   and issues a token. The token is bound to the set of questions, and holds
   their hashes, never their text. The agent may give a question a category
   (`vulnerability`, `secret` or `personal`) in this call. Filter 1 then
   searches only files on the machine for it, the repository and the lore
   clones, and skips GitHub's issues.
2. `inquisitor.py vet --pass <token> --verdicts v.json` takes one verdict per
   question, with the field each verdict needs (a citation for `answered`,
   where the question is listed or filed for `deferred`, where the choice is
   recorded for `decided`, and the recommended option and what changes under
   the others for `ask`), and appends one record per question: the SHA-256 of the question's text (as the spec defines it), the
   verdict, its field, and the time. The record of a question given a
   category holds the category in place of the field, so it holds no text at
   all.

Tokens and records live in `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`,
where prose keeps its session marks, and for the same reason: a session spans
repositories, and the hook's working directory can differ from the one `vet`
ran in (prose's DECISIONS.md, *The gate*). These records are the hooks'
state, not a question log: they hold no question's text, and whichever
call or hook next reads them deletes each one more than 2 hours old, with a
category or without one. Nothing else keeps a record of a question with a
category; a vulnerability's lasting record is the repository's private
security advisory. Concurrent Igor workers (the AI teammates the igor
project runs) that share one HOME also share records, so one worker's
verdict on a question's text can let another worker ask the same text.
Whether one worker or several wrote the records, the hook allows a question
only while the latest verdict on its text is `ask`.

The hook hashes each question in the tool's input the same way, reads the
most recent record for each hash, and allows the call when each is `ask` and
less than 2 hours old, and when each question's first option is the
recommendation its record holds. A record with a category holds no
recommendation, so the hook does not check that question's first option. A record is not spent
by the call: when the hook
blocks a call because of one question in it, the other questions need no
vetting again.

**Rejected:**

- **A signed footer in the question,** as prose signs a post. The person
  reads the question in the picker, and a hash in it is noise to them.
- **The hook running the filters itself.** A hook is a script with no model,
  so it can't tell whether two options both have merit.
- **The skill's description alone,** with no hook. A model decides by
  judgement whether to load a skill, which is why decision 5 in proposal.md
  asks for a hook.
- **Records in the repository's git directory,** where prose keeps its pass
  tokens (as opposed to its session marks). A `vet` run in another repository would leave its records where the
  hook never looks.

### What the hook relies on, not yet measured

Three facts about Claude Code are unmeasured (tasks 0.1 to 0.3): a
`PreToolUse` hook fires on `AskUserQuestion`; exit 2 blocks it and its stderr
reaches the model; and the tool's input carries `questions[].question` and
`questions[].options[].label`. If the first two turn out false, the picker is
covered by the skill's instructions alone, and the README says so. If the
input's shape differs, the question's text is redefined from what the input
holds.

## Questions in posts

prose's posting hook already reads the body of a `gh` post from a short
allow-list of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an allow-list*).
That reader moves to `.agents/lib/gh-post/`, unchanged, and both hooks call
it. prose's tests must pass unchanged after the move.

The inquisitor's post hook finds the body's questions by the spec's rule
(*Questions in posts pass the same filters*), hashes each, and applies the
picker hook's rule. A post with no question passes without a lookup.

**The order with prose:** do prose's pass, vet the rewritten body, then sign
it with prose. The footer prose appends holds no question, so signing leaves
the body vetted. An edit after vetting means vetting again; an edit after
signing means signing again too.

A rhetorical question is found too. Nobody needs to choose an answer to it,
so filter 3 stops it, and the agent rewrites it as a statement.

## Where the logs live

**A question's log goes with what it concerns, at that place's privacy.**
The question is written for that privacy before it is asked (the spec's *A
question is written at the privacy of what it concerns*), so its log can sit
beside it.

- **A question about one repository:**
  `.inquisitor/questions/<yyyy-mm-dd>-<slug>-<6 hex>.md` in that repository,
  committed with the work, so every agent on the team finds it, as
  spec-check's `openspec/spec-check.yaml` is found.
- **A question about an organization or project:**
  `questions/<yyyy-mm-dd>-<slug>-<6 hex>.md` at the root of the team's lore
  repository, added by a pull request. Its files hold no `conditions`, so
  neither the search nor Igor reads one as a lore entry. An answer worth
  giving agents as lore moves from there into a lore entry by another pull
  request in the same repository.
- **A question about one person's way of working:** no log. Its answer goes
  into that person's memory or `CLAUDE.md`, which agents already read.
- **A question in one of the three categories** (`vulnerability`, `secret`,
  `personal`): no log. Only the hooks' record above holds it, as a hash.

Each log file has YAML frontmatter (`repository`, `asked`, `answered_by`,
`authority`: `decision` or `input`, `recorded_in`) and the question and
answer as its body. The hex is random, so two branches logging the same
question on the same day still write different files. Misses, the questions
a person said need not have been asked, go in `misses/` beside `questions/`, in the same form, with `filter` and `said` in
place of the answer fields.

**Rejected:**

- **A personal log under `~/.config/shared-skills/inquisitor/`** for a
  question about a public repository or about no repository. A question
  whose context was private would then be kept, with that context, where
  only one person finds it; the question is instead written without that
  context, or not asked.
- **One file that every question appends to.** Two branches that each append
  a line conflict when they merge, every time.
- **The git directory.** It is never committed, so the next agent on another
  machine would ask again.

## Configuration

`~/.config/shared-skills/inquisitor.json` holds the lore repositories, and
the GitHub login of the person running the session:

```json
{
  "login": "adamstallard",
  "lore": [
    {"path": "/Users/me/src/team-lore", "owners": ["adamstallard"]}
  ]
}
```

`path` is a local clone, searched as it is on disk; the skill never fetches
it, and reports when the clone was last fetched (the time of its
`FETCH_HEAD`, or "unknown" for a clone with none, such as a fresh one).
`owners` lists the GitHub owners whose repositories the lore
repository serves. A missing file means no lore repository, and filter 1's
search says lore was not searched.

Reviewers live in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line. A team decides them
there, in review, so every teammate's agent tags the same person. #211
proposed "a reviewer or expert named in the team's configuration"; a
repository's own file is that configuration for questions about it.

Visibility, of a lore repository or the repository a question concerns, is
read with `gh repo view --json visibility` on the clone's `origin`. Write
access is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Whether that call works for a caller without
push access is unmeasured (task 0.4). Each check fails closed:
- an unread visibility of the repository the question concerns counts as
  private when deciding whether its answer may go to a public lore
  repository;
- an unread visibility of a lore repository counts as public;
- an unread permission counts as no write access, so a question never tags
  a person who might be unable to decide it.

When none of decision 17's candidates (the approver of the related
decision, a listed reviewer, the last committer) has write access, the
script considers the person running the session, identified by the `login`
in the configuration. `gh api user` can't identify them: an agent posting
as a GitHub App gets no user from it, and one posting as the person gets the
post's own author, whom a tag would not notify. The script uses
`gh api user` only to learn which login the post goes out as. It reads the
configured login's write access with the same permission call:
- no login configured: the agent asks the question through the picker;
- write access, and `gh api user` returns that same login, so the post
  would go out as them: the agent asks through the picker, because a
  self-tag sends no notification;
- write access, and the post goes out as anyone else, including an App for
  which `gh api user` fails: the question tags the login;
- no write access: the question tags no one.

The search reads each markdown file under a clone whose frontmatter holds
`conditions`, and matches the question's terms against `claim`,
`conditions.prose`, the `conditions.paths` globs and the body. It also reads
each file under the clone's `questions/`, as it reads a repository's
`.inquisitor/questions/`. The igor project's own
configuration has a `destination` setting naming the directory of a lore
repository that holds its entries; the search does not use it, since a plain
session has no Igor configuration.

## Tracing scenarios to tests

Every scenario gets a tagged test before the change is archived, since
spec-trace's CI fails on an untagged one, and spec-trace's baseline
(`openspec/spec-trace-baseline.txt`), which lists exempt scenarios, takes no
new lines.
Where a scenario is about the script or a hook, the test runs it. Where it is
about what the agent does (asking through the picker, batching, handing a
question back, choosing a lesson's scope), the test checks that SKILL.md
states the rule, and the test's name says it checks SKILL.md.
