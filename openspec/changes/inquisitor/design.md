The inquisitor is a skill that stops an agent's needless questions to a
person. Before asking, the agent runs each question through four filters:
filter 1, already answered (it searches for an earlier answer); filter 2,
deferrable; filter 3, not a real question; filter 4, cheap to reverse (*Four
filters stop questions before a person*, under *Decisions*). Hooks on
Claude Code's question picker and on GitHub posts block a question that has
not been through them.

Adam (adamstallard) owns this repository and decides this change. Terms such
as Igor, the picker, the two calls, a verdict and the answer session are
defined in *Terms used throughout*, after the introduction to *Decisions*.

## Proving the filters ran

A hook can't judge whether a question has merit; only the agent can. So the
design makes skipping the filters fail, and leaves the agent's verdicts to
review. It copies the two script calls the prose skill uses to prove its
rewrite pass ran (`.agents/skills/prose/DECISIONS.md`, *The rules are on
screen before a signature*). The two calls prove the filters were printed
and the search ran before each verdict, not that the agent judged well.

1. `inquisitor.py vet --questions q.json` takes the questions exactly as
   they reach the picker: the JSON array that `AskUserQuestion` takes as
   `questions`. `vet --post body.md` takes a post's body and finds its
   questions with the post hook's function. Either way it prints the four
   filters, runs filter 1's search for an earlier answer to each question,
   prints the hits, and
   issues a token bound to the set of questions, holding their hashes, never
   their text. The agent may give a question a category (`vulnerability`,
   `secret` or `personal`) here; it then passes every question of that
   picker call on standard input, so no text is written to a file that could
   be committed, and filter 1 searches only files on the machine for the
   categorized question, skipping GitHub's issues.
2. `inquisitor.py vet --pass <token> --verdicts v.json` takes one verdict
   per question, with the field each needs, and appends one record per
   question: the SHA-256 of the question's text, the verdict, its field and
   the time. A categorized question's record holds the category in place of
   the field, so it holds no text at all, and an `ask` record drops the
   recommended option's label, which is part of the question's text (*An
   `ask` record drops the option's label*, under *Decisions*).

Tokens and records live in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`, where prose keeps its
session marks, for the same reason: a session spans repositories, and a
hook's working directory can differ from the one `vet` ran in (prose's
DECISIONS.md, *The gate blocks a session's first file write*). They are the
hooks' state, not a question log, and expire as *Every verdict record
expires after 2 hours* says. Because a categorized question's record
expires too, a vulnerability needs a lasting record elsewhere: the
repository's private security advisory. Concurrent Igor workers (the AI
teammates the igor project runs) that share one HOME share records, so one
worker's verdict on a text can let another ask it. That is intended, since a
verdict is about the text, not the worker; per-clone records, as prose keeps
its tokens, were rejected.

When a hook can't read the records, the picker hook lets the question
through and the post hook blocks a post that holds one. A picker question
publishes nothing, so at worst one unfiltered question reaches the person.
The post hook blocks because the question it can't check might be a
categorized vulnerability, and a published vulnerability can't be taken
back.

The hook hashes each question in the tool's input the same way and allows
the call when each hash's latest record is `ask` and less than 2 hours old.
It doesn't check the order of a question's options, since the text includes
them in order, so reordering them after vetting changes the hash. The
related-decision line is left out of the hash, so the agent can add it after
the first call's search finds the decision (*The related-decision line is
left out of the hash*, under *Decisions*).

A hook does not use up a record when it reads one. When it blocks a call for
one question, the call's other questions need no new vetting (*A hook
spends no verdict record*, under *Decisions*).

**Rejected:**

- **A signed footer in the question,** as prose signs a post: the person
  reads the question in the picker, where a hash is noise.
- **The hook running the filters itself:** a hook is a script with no model,
  so it can't tell whether two options both have merit.
- **The skill's description alone,** with no hook: a model decides by
  judgement whether to load a skill, which is why *A picker hook makes
  agents run the filters* asks for a hook.
- **Records in the repository's git directory,** where prose keeps its pass
  tokens: a `vet` run in another repository would leave its records where
  the hook never looks.

### What the hook relies on, not yet measured

Three facts about Claude Code are unmeasured (tasks 0.1 to 0.3): a
`PreToolUse` hook fires on `AskUserQuestion`; exit 2 blocks it and its
stderr reaches the model; and the tool's input carries
`questions[].question` and `questions[].options[].label`. If the first two
are false, the skill's instructions alone cover the picker, and the README
says so. If the input's shape differs, the question's text is redefined from
what the input holds.

### What task 0.12 measured

**An Igor worker can't run this skill** (measured 2026-10-20), read against
igor's main branch and the branches of igor PRs #174 (pinned skills), #175
(a worker as its own Unix user) and #216. The first bullet is measured from
igor's code; the second is read from #174's and #175's specs, since neither
is built yet.
- **Today:** a worker's Bash permission is only its role's `commands`
  (igor's `src/execute.ts`, line 1607, at 8478aec), so the skill's script
  runs only if a role lists it, and Read is refused outside the working
  tree. HOME is the home directory of the user the Igor runs as, so
  `inquisitor.json` and a `gh` login are there only if a developer set them
  up, as under `igor run` on their own machine, where `gh` would act as the
  person. Under `serve`, igor's deployment guide tells the operator not to
  log `gh` in as the service user, since a worker allowed to run `gh` could
  use that login (igor's `docs/deployment.md`, lines 112 to 115); task 0.14
  measures whether a worker can.
- **After #174 and #175:** skills load only from `/opt/igor/skills`,
  and #174's task 5.1 installs only prose, bug-hunter and spec-trace.
  The lore checkout is mode 0750, which the worker can't read (#175's
  `design.md`, line 189). The worker's home has no `inquisitor.json`
  and no `gh` login. It loads settings only from the empty user
  settings file igor writes for it (`--setting-sources user`), so no
  hooks load. The run is headless, so there is no `AskUserQuestion`.
- **Either way,** igor passes the worker no lore repository, and on igor's
  main branch no marker that it runs inside an Igor; igor PR #216 adds
  `IGOR_RUN`. Besides the item, fenced in its user message, the worker is
  told what its system prompt, `workerSystemPrompt` (igor's
  `src/execute.ts`, line 161, at 8478aec), holds: the role's name, the actions its run may take, the commands it may
  run, the role's standing instructions and the active lore entries the Igor
  injects. The Igor injects only the entries that fit the worker's token
  budget, so injected lore alone is not enough for filter 1.

So the spec's Igor-worker rules assume a worker with no inquisitor
configuration, no `gh` login or other GitHub credential, no picker and no
hooks, that can read only its working tree, its outbox and what its Igor
passes it. The outbox is a place a worker reports to its Igor through
besides its output; igor PR #175 chooses between the two. To search lore,
the worker runs `igor lore-search`, a read-only command igor PR #216
specifies, with the question on standard input and no argument (*Filter 1 in
an Igor's run searches through `igor lore-search`*, under *Decisions*). The
Igor tells which run and role an `igor lore-search` request is for by the
connection it arrives on, one only that run's worker can reach, so a worker
can't ask on behalf of
another run or role. igor runs the search on its own lore checkout and
`questions` branch with the role's scope, so the worker needs no lore clone,
`inquisitor.json` or `gh`, and igor applies the scope rules to lore entries
and to question and miss files alike.

igor PR #216's `task-execution` spec has igor set `IGOR_RUN`, holding no
secret: to `worker` in a worker's environment, and to `igor` when an Igor
runs the inquisitor skill itself (*The script tells an Igor's run by
`IGOR_RUN`*, under *Decisions*). igor does not set it yet; task 0.9 checks
it once igor builds it. In both runs the script reads no lore clone and
pushes nothing to a lore repository, and under `worker` it reads filter 1's
other sources only from the worker's working tree and reports GitHub's
issues as not searched. The script matches the variable's exact name, since
igor PR #171 adds `IGOR_RUN_TOKEN`, the token of a seat, the account igor
lends a worker, which a prefix match would take for a run marker; and its
exact value, so any other value marks no run.

## Questions in posts

prose's posting hook reads the body of a `gh` post from a short allow-list
of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an
allow-list*). This change moves that reader to `.agents/lib/gh-post/`, where
both hooks call it, and states its rules once, in the `gh-post` capability
spec (*One post reader, shared by both hooks*, under *Decisions*). prose's
tests pass unchanged after the move except in three places:
- The reader reads two more forms of post. A post sent through the
  github-app skill's script, `python3 <github-app script> gh pr|issue …`,
  which that skill tells agents to use instead of plain `gh`, is unreadable
  under prose's rules alone, so every post an agent sends as a GitHub App
  would be refused. A comment sent with `gh api`, its body given by `-f`,
  `--raw-field`, `-F` or `--field` `body=`, or by `--input`, passes prose's
  rules unread, so it would skip the hook.
- It blocks a data command given code to run. `python3`, `node` and `git`
  may name `gh` in a quoted argument, but `python3 -c`, `node -e` and `git
  -c`, which can set an alias that runs a shell command, can each run code
  given in the command, and so can `python3` reading its program from a
  heredoc or a pipe. The shared reader reports such a command as unreadable
  when its code names `gh`, as it does `sh -c` (*Code given on the command
  line that names gh*, under *Decisions*).
- It reads a title, so a question in a title is vetted as one in the body is
  (*A post's title is read and vetted*, under *Decisions*). A title built by
  the shell, such as `--title "$(git log -1 --format=%s)"`, or a title edit
  chained to another command, such as `cd x && gh pr edit 3 --title
  'Rename?'`, is unreadable. prose's `DECISIONS.md` has the chained edit
  pass (*The posting hook reads an allow-list*, its paragraph "Titles are
  not checked"), and task 1.3 updates that paragraph. A footer can't go on a
  one-line title, so prose's hook checks only that a title is readable, and
  lets a call with a title and no body through.

A plain or bold line ending in a colon begins an open-questions section, as
a heading does, only when its label names questions, such as "Open
questions:" (*What counts as a question in a post*, under *Decisions*).
Agents often list their open questions under such a line, and a deferred
question listed there passes on its `deferred` verdict. "Open a terminal and
run:" names no questions, so outside an open-questions section the commands
after it need no verdicts. A section ends only at the next heading or bold
label, so a plain colon line inside one ends nothing.

The inquisitor's post hook finds a body's questions by the spec's rule (*A
question in a post is a listed item or a sentence ending in a question
mark*), hashes each, and applies the picker hook's rule. It also allows a
`deferred` question that tags no one, as an item of an open-questions or
deferral section or anywhere in a new issue, since filter 2 lists a deferred
question in the work's description or files it as an issue (*A deferred
question passes only untagged and listed*, under *Decisions*). A question
that tags someone asks that person for an answer, so it needs an `ask`
verdict however it was deferred. A post with no question passes without a
lookup.

**The order with prose:** do prose's pass, vet the rewritten body, then sign
it with prose. The footer prose appends holds no question, so signing leaves
the body vetted. An edit after vetting means vetting again; an edit after
signing means signing again too.

A subagent returns its question to whoever started it rather than opening
the picker: the session's person is talking to the starting agent, which can
batch the subagent's questions with its own.

A rhetorical question is found too. Nobody needs to choose an answer to it,
so filter 3 stops it, and the agent rewrites it as a statement. Its
`decided` verdict names the post as where the choice is recorded, since the
statement in the post is the whole of the choice.

## Where the logs live

**A question's log goes with what it concerns, at that place's privacy.**
The question is written for that privacy before it is asked (the spec's *A
question is written at the privacy of what it concerns*), so its log can sit
beside it.

- **A question about one repository:** a file under `.inquisitor/questions/`
  in that repository, committed with the work, so every agent on the team
  finds it, as `openspec/config.yaml` is found. A question about another
  repository goes to it by a pull request. A question about a change belongs
  in that change's history, so the file merges with it, not on a branch of
  its own; until then filter 1 elsewhere can't see it, and parallel work can
  ask again, a cost this change accepts (*A repository's questions are
  committed with the work*, under *Decisions*).
- **A question about an organization or project:** a file under `questions/`
  on an orphan branch named `questions` in the team's lore repository,
  separate from igor's `igor-state` branch, where igor keeps its runtime
  state (igor's `src/state.ts`). The agent pushes each file directly, with
  no pull request, and fetches and pushes again when the branch moved. Each
  file's name holds 6 random hex digits, so two pushes never write the same
  file. No review is needed, since a question's authority comes from who
  answered it, and the default branch stays uncluttered, holding only the
  lore entries Igor gives agents. The files hold no `conditions`, so neither
  the search nor Igor reads one as a lore entry.

  Anyone who can push may write any `answered_by`, and GitHub's commit
  author login comes from the author email, which the committer sets. So a
  `decision` file there counts only when it links the GitHub comment or
  review holding the answer, written by `answered_by`, or when the commit
  that added it carries a signature GitHub verifies for `answered_by`'s
  account (*A questions-branch decision needs a proven writer*, under
  *Decisions*). The agent commits from the person's session, so after a
  one-time signing setup the person never signs an answer by hand. A file
  there never changes once pushed: a later answer is a new file holding the
  question and the answer, and a file some later commit changed is input
  (*No file on a questions branch changes once pushed*, under *Decisions*).
  So a proof made on the commit that added a file covers everything the file
  says.

  An Igor worker holds no credential for the lore repository, so the files
  it would push go in its report, and its Igor pushes them by igor PR #216's
  rules (*The Igor pushes the questions-branch files its worker reports*,
  under *Decisions*). The Igor accepts an answered file from a worker only
  when the file's `answer_link` points to a person's comment that answers
  the Igor's handback question on the item the run worked (igor PR #216's
  decision 41). As Adam decided, the Igor also checks every file it pushes
  with igor PR #217's credential matcher (#216's decision 28). Filter 1
  counts such a file as a decision only when
  the comment's author, or the person whose relay App posted it (*Only a
  listed relay App speaks for a person on GitHub*, under *Decisions*), is
  `answered_by` and has write access. So a worker steered by text it read
  can't forge a person's answer.

  An answer worth giving agents as lore is promoted by a pull request to
  main adding a `provisional` entry; the question's file stays on its
  branch. Before pushing or promoting, the script checks visibility: nothing
  goes to a lore repository more visible than the repository the question
  concerns (for an organization question, the repository whose work raised
  it, by the spec's definition), ranking private, then internal, then
  public.
- **A question about one person's way of working:** no log. Its answer goes
  into that person's memory or `CLAUDE.md`, which agents already read.
- **A question in one of the three categories** (`vulnerability`, `secret`,
  `personal`): no log. Of this skill's records, only the hooks' verdict
  record holds it, as a hash. In an Igor's run the worker instead raises a
  flag naming the categories met (*The flag a worker raises for a question
  with a category*, under *Decisions*), and igor keeps the category words,
  never a categorized question's text, in an operator-only file on its
  host, with the session logs that hold the text moved beside it (igor
  PR #216's decisions 88, 89, 97 and 98).

A log file's and a miss file's path, name, keys and encoding are stated
once, in the spec's requirement *A log file and a miss file have one format*
(*Log and miss files have one format, stated once*, under *Decisions*). In
short, a log file has YAML frontmatter (`repository`, `asked`,
`answered_by`, which is `agent` for an agent's choice, `authority`:
`decision`, `input` or `agent`, `recorded_in`, and `answer_link` when there
is one) and the question and answer as its body. An `answer_link` is a
github.com comment or review, whose text the `log` command fetches and
records, or, for an answer the answer session relayed on Linear or Discord
to a questions-branch question, the relay post's URL, which nothing fetches
and only a private lore repository gets. Only GitHub tells a reader who
wrote a comment, so such a file counts as a decision only through its adding
commit's signature (*Questions-branch answers relayed on Linear or Discord*;
*`answer_link` and `asked_in` are withheld where they would leak*, under
*Decisions*).

An answer typed directly on Discord, Slack or Linear is logged as `input`,
and filter 1 treats it as given only once a decision document the spec's
*Only an answer with authority stops a question* lists records it, such as
the `accepted` decision record igor's scribe writes (*An answer typed on
another surface counts only through a decision document*, under
*Decisions*).

An answer logged as `input` goes only into the question's log file, never
into a decision document: on the current work's branch a decision document
counts as an answer, so writing input there, such as an answer from a person
without write access, would turn it into a decision (*An answer without
authority stays in its log file*, under *Decisions*). Log and miss files
quote a question as asked and a person's words exactly, so prose's pass
skips files under `.inquisitor/` (*prose's pass skips `.inquisitor/`*, under
*Decisions*). The files on a lore repository's `questions` branch need no
such rule: that branch is never checked out, so prose never sees them.

When filter 1 stops a question with a lore entry, a citation goes to that
lore repository's `questions` branch, holding the entry's id, the date, and
the run's id when an Igor pushes it. It holds nothing about the question, so
even a private repository's question gets one. A question gets one only
when the lore repository is no more visible than the repository the
question concerns. A categorized question gets none,
since the cited entry would show what it was about (*A citation holds
nothing about the question*, under *Decisions*). The inquisitor and an Igor
both write
citation files, and igor's review reads them all, so the spec states the
format once, in *A citation file has one format* (*One citation format,
defined here*, under *Decisions*). A worker holds only its seat's token, a
credential for the model, so during a run the Igor pushes citations, by igor
PR #216's rules (*igor PR #216 holds every rule for a run's citations*,
under *Decisions*); task 0.14 measures whether a `gh` login in the worker's
home is usable anyway.

The inquisitor's commits to the `questions` branch are machine records with
the fixed message `inquisitor: log <file>`, exempt from prose's and
bug-hunter's trailers, whose checks never see a branch that is never checked
out. A citation's commit says nothing about who asked: author and committer
`inquisitor <noreply>`, date reduced to the day (*A citation's commit names
no person*, under *Decisions*). igor's planned review could count an entry's
citations there, beside its fire count, the times igor injected it into a
worker. That count is a lower bound, as the review says, and when every Igor
citation push in the review's period failed, the review shows "not checked"
instead of a count (*igor's review count of citations*, under *Decisions*;
igor PR #216's decision 32).

Misses, the questions a person said need not have been asked, go where their
questions went, in `misses/` in place of `questions/`, in the same format,
with `filter` and `said` in place of the answer keys (`answered_by`,
`authority`, `recorded_in` and `answer_link`). The 6 random hex digits in a
file's name mean two branches logging the same question on the same day
still write different files.

Every log file and miss file, and every question in a post, is scanned for
the credential patterns, and a match refuses it. The scan is only a
backstop: a secret under an arbitrary name, such as `DB_PASSWORD=…`, passes
(*The secret scan is only a backstop*, under *Decisions*).

**Rejected:**

- **A personal log under `~/.config/shared-skills/inquisitor/`** for a
  question about a public repository or about no repository: a question
  whose context was private would be kept, with that context, where only one
  person finds it. The question is instead written without that context, or
  not asked.
- **One file that every question appends to:** two branches that each append
  a line conflict when they merge, every time.
- **The git directory:** it is never committed, so the next agent on another
  machine would ask again.

## Configuration

`~/.config/shared-skills/inquisitor.json` holds the lore repositories, the
GitHub login of the person running the session, and the answer session's
section, `answer_session`, whose keys the `answer-session` spec defines:

```json
{
  "login": "adamstallard",
  "lore": [
    {"path": "/Users/me/src/team-lore", "owners": ["adamstallard"]},
    {"path": "/Users/me/src/api-lore", "repos": ["adamstallard/api"]}
  ],
  "answer_session": {
    "github": {"relay": "adam-relay", "subscriptions": ["adamstallard", "BrightID/aura"]},
    "linear": {"relay": "adam-relay", "subscriptions": ["ENG"]},
    "discord": {"relay": "adam-relay", "user": "123456789012345678",
                "subscriptions": ["987654321098765432"]}
  }
}
```

`path` is a local clone. The search reads the clone's remote-tracking
default branch, such as `origin/main`, with `git show`, never the working
tree or a local branch, which could be on another branch or hold an
unreviewed edit. It reads the `questions` branch with `git show` too,
without checking it out. The skill fetches only the `questions` branch, so
an entry merged since the person last fetched the clone is not found (*Lore
search is as fresh as the last fetch*, under *Decisions*). The search
reports when a fetch in this clone last updated the remote-tracking default
branch it searched. It reads that date from the branch's reflog, so the date
and the content searched come from the same ref, and reports "unknown" for a
clone whose reflog has no such entry, such as a fresh one. The skill's own
fetch would give the wrong date, since it fetches only `questions`, and so
would `FETCH_HEAD`, which that fetch rewrites. The date is not when the
branch last moved on GitHub, and a fetch that brings nothing new writes no
entry.

`owners` lists the GitHub owners whose repositories the lore repository
serves, and `repos` lists single repositories it serves; several lore
repositories may serve one owner. When an organization or project question
matches more than one, the most specific match (a named repository beats an
owner) wins, then the first listed, and the agent's report says which. A
missing `inquisitor.json` means no lore repository, and filter 1's search
says lore was not searched.

Reviewers are listed in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line, decided there in review,
so every teammate's agent tags the same person (*One person who can decide
is tagged*, under *Decisions*).

Visibility, of a lore repository or of the repository a question concerns,
is read with `gh repo view --json visibility` on the clone's `origin`, which
gives `PRIVATE`, `INTERNAL` or `PUBLIC`, ranked in that order. Write access
is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Whether that call works for a caller without
push access is unmeasured (task 0.4). Each check fails closed:
- an unread visibility of the repository the question concerns counts as
  private;
- an unread visibility of a lore repository, or of a post's target, counts
  as public;
- an unread permission counts as no write access, so a question never tags a
  person who might be unable to decide it.

An Igor writes `asked_from`, the repository of the run's item, on every log
or miss file it pushes, beside the `repository` its worker or its own run
wrote (*The Igor writes `asked_from` on every file it pushes*, under
*Decisions*); an answer session's miss for a questions-branch file copies
that file's `asked_from` (*Misses the answer session logs*, under
*Decisions*). A worker steered by its item's text could name a public
`repository` on a file about a private one, but `asked_from` still names the
private one. So every reader judges the file by the more private of the two:
igor's search, the answer session's privacy check before an automatic post,
and the refusal to promote a more private answer into lore.

When no candidate in *One person who can decide is tagged* has write access,
the script turns to the configured `login` (*When no candidate can decide*,
under *Decisions*). It uses that login only when it equals the account `gh`
is logged in as, read running as the person, so nobody can claim a
maintainer's login by typing it into their own file (*The configured login
names the person*, under *Decisions*). Run with an App's token, `gh api
user` gives no user, so the login comes from the configuration. Run with the
person's `gh` login, it returns the person, which is why the script can
confirm the configured login but can't tell which login a post sent with the
github-app skill's token goes out as (task 0.7). In a session with a person
in it, when it can't tell, the agent asks through the picker, as for a post
that would go out as the login itself, since a self-tag sends no
notification.

These are rules for the agent, which SKILL.md states. Where they say the
picker, a session with a person in it on a host with no picker asks in its
reply, once the two calls have vetted the question (*With a person present,
ask through the picker*, under *Decisions*). A headless session never uses
the picker. An Igor worker is given no credential that can post, so it asks
only in its handback comment, which its Igor posts, even if task 0.14 finds
a `gh` login within its reach (*An Igor worker asks only in its handback
comment*, under *Decisions*). A flagged run's Igor posts a handoff that asks
nothing (*A flagged run asks nothing and pushes nothing*, under
*Decisions*).

The search runs in an Igor worker too, since igor injects active in-scope
entries only while they fit the worker's token budget. During a run it uses
the running role's scope and labels status (*Scope hides an entry; status
only labels it*, under *Decisions*), and igor's search hides a
questions-branch file about a repository more private than the run's item's,
which the worker could otherwise repost into the more public item
(*Questions-branch files and `project:` entries in a run's search*, under
*Decisions*). A worker reports a cited entry by its id alone, and the Igor
checks that id against the lore repository it injects from, where an entry
from another lore repository could be refused or counted as a different
entry. So during a run the search covers only that lore repository, and
`igor lore-search` runs it, as Adam settled on igor PR #216 (*Filter 1 in an
Igor's run searches through `igor lore-search`*, under *Decisions*). The
script never needs to know which lore repository the Igor injects from.

The agent proposes no lore entry during a run. When a proposed id clashes
with one held outside the run's scope, igor reports only "id taken". That
report doesn't say which of two cases holds. If an entry holds the id,
another id would do. If a rejection holds it, the entry may not be proposed
at all (*A proposed entry's id
follows igor's id rules*, under *Decisions*).

The search reads each markdown file under the clone's `entries/` whose
frontmatter holds `conditions`, never one under `rejected/`, and matches the
question's terms against `claim`, `conditions.prose`, the `conditions.paths`
globs and the body. It reads each file on the clone's `questions` branch as
it reads a repository's `.inquisitor/questions/`. Each lore entry has a
scope that says who may see it: `global`, `role:<name>` or `project:<name>`
(*Scope hides an entry; status only labels it*, under *Decisions*). Outside
an Igor, an entry scoped `project:<name>` is in scope when `<name>` is the
short name of the repository the question concerns. A project whose
repositories have other names would need a
mapping, in one file in the lore repository that igor and the inquisitor
both read; this change does not build it. igor's `destination` setting names
the lore repository holding its entries; a plain session has no Igor
configuration and does not use it. That repository also holds the
`questions` branch and the people's relay files (*What the answer session
posts, and what it logs* defines them), even when it is not the repository
holding the Igor's configuration (*What a lore repository means here*, under
*Decisions*).

## The answer session

The answer session gives a person one place to answer the questions asked of
them on GitHub, Linear and Discord. A relay identity, a bot of the person's
own on each surface, posts each answer in the question's thread. Its
interface is a Claude Code mod. Adam approved two builds of its prototype by
using them:
- v0.1-30, tagged `answer-session-ui-approved-v0.1-30`;
- v0.1-33, which descends from v0.1-30 and adds the thread's replies and
  filter 1's recorded answer, tagged `answer-session-ui-approved-v0.1-33`.

The mod is built from v0.1-33 alone (*The answer session and its relay
identities*; *The UI is built from prototype build v0.1-33*, under
*Decisions*). A UI approved by use is not specified (*UI is prototyped and
approved by use, not specified*), so nothing here describes how it looks.
The spec governs what the UI does and posts: where v0.1-33 does otherwise
the spec wins, and screens the spec needs that v0.1-33 lacks follow its
patterns (*How the approved prototype meets the spec*, under *Decisions*;
task 6.1). The rules are in the `answer-session` spec, and the decisions in
the sections from *Answer-session configuration, setup and relay identities*
to *Linking log files to threads, and handbacks*.

### Polling while open, with the person's credentials

A webhook needs a public HTTPS server, and Discord's push a permanent
connection: either is a service to run, which nothing else in this skill
needs. So the answer session polls, only while it is open, about every 60
seconds, with a catch-up poll when it opens (*The answer session polls, only
while it is open*, under *Decisions*). Task 0.15 checks that GitHub's
notifications endpoint behaves as documented: a conditional request that
finds nothing new is answered `304` without counting against the rate limit,
`X-Poll-Interval` says how long to wait, and a mention subscribes the person
to its thread, so later replies there, to the relay included, arrive as
notifications too. Unless it shows the endpoint also reports a mention of
the relay in a thread the person was never subscribed to, the answer session
also reads the comments of each repository in its subscriptions.

On GitHub and Linear, reading uses the person's own credentials and a relay
identity only posts, so a relay's token needs only the right to post, and
nothing the person reads is read under the bot's name (*Reading uses the
person's own credentials*, under *Decisions*). On Discord a user account
can't be automated within Discord's terms, so one `discord-bot` identity,
the relay, both reads and posts, in the channels it was added to (*On
Discord one identity both reads and relays*, under *Decisions*). Reading a
message that doesn't mention it needs Discord's privileged Message Content
intent (*The Discord relay needs the Message Content intent*, under
*Decisions*). discord-bot's setup, in shared-skills PR #1, has the person
turn the intent on (commit 369ae16), and its `check` command reports
`messageContent` as true, false or null from the bot's application flags
(f83b167). Setup's check passes only on true; null means `check` could not
read the flags. discord-bot turns each `@name` in a post into a mention that
notifies that member, and the relay keeps that on, so the person's own
`@name` pings as in a comment of theirs (*Discord relay posts: no header,
mentions that ping*, under *Decisions*). A relay post links to a recorded
answer instead of quoting it, so a record's @-mentions never notify anyone
again (*What the answer session posts by itself*, under *Decisions*).

A relay identity may do other work, but only the answer session starts a
post with one of the four reserved prefixes, `User says: `, `User asks: `,
`Recorded answer: ` and `Inquisitor: ` (*Only the prefixes are reserved, not
the identity*, under *Decisions*). Anything holding the relay identity could
post `User says: `, which marks a question answered on every machine and, on
GitHub, counts as the person's own answer to filter 1. The skill's
instructions reserve the prefixes, and on GitHub the inquisitor's post hook
blocks a tool-call post starting with one (*The post hook blocks a reserved
prefix on GitHub*, under *Decisions*), which never blocks the answer
session, whose posts reach no tool hook. Nothing enforces them on Linear or
Discord.

### The thread is the record

An answer's record is the relay's post in the question's thread, not
anything on the machine (*The thread is the durable record of an answer*,
under *Decisions*), since the thread is the one place every machine, and the
asker, can read. A crash between a successful post and the write of its id
to local state loses nothing: the next read of the thread finds the post. A
post that asks the asker starts `User asks: ` instead of `User says: `
(*`User says: ` answers, `User asks: ` asks the asker*, under *Decisions*),
so "waiting for the asker" can be read from the thread too, and the answer
session's own posts, starting `Recorded answer: ` or `Inquisitor: `, mark a
question answered or handled the same way.

A decline that posts nothing closes the question in the state folder only,
so another machine shows it as open (*Declining with nothing to answer
closes only that question*, under *Decisions*). A decline for reason 2, that
the inquisitor should have handled the question, gets a post, recorded in
the thread like any other, except where *Two reasons to
decline* and *Agreeing to a recorded answer is a filter 1 decline* say it
gets none or needs the person's confirmation. The thread is read again
before a question is shown, when its poll is over a minute old, and before
each post, so an answer relayed from another machine is never posted twice.

### Local state, one writer per machine

The state folder holds working state only: what the person set aside for
later, discussion records, poll positions, relay checks, post ids and the
question on screen (*Local state is per machine, in the state folder*, under
*Decisions*). It is no personal question log, which *Every asked question is
logged with what it concerns* rules out: the asker's log file and the thread
stay the records, and filter 1 never reads the folder. A discussed
question's text stays there only while the question is open. Adam ruled
that, on that condition, the state folder is not a personal question log,
so it makes no exception to *Every asked question is logged with what it
concerns*.
State is per machine: a question set aside on one machine shows as new on
another, which costs a second look and nothing else.

One answer session runs per machine, under a lock in the state folder. Its
holder refreshes it at least every 30 seconds, and it goes stale 2 minutes
after its last refresh, so a crashed holder's lock goes stale within 2
minutes (*One answer session runs on each machine*, under *Decisions*).
Before each poll
and each post the holder checks that the lock still holds its session id,
not its name, since every session the `answer` command starts is named
`Answers`; so a session that was taken over posts nothing more.

There is no TLA+ model. Adam's rule asks for one where several processes
share state, and the lock is the only place that happens here. One person
uses the answer session, the lock makes one session per machine the only
writer of that machine's state, and the state shared across machines is the
threads, which each write appends to and each read re-fetches. The
interleavings left are two sessions racing for the lock, which an atomic
create or replace settles, and a take-over during a post, which the check
before each post settles.

### What the answer session posts, and what it logs

A relay post holds the person's own words, so neither prose's pass nor the
inquisitor's filters apply to it (*A relay post gets no prose pass and no
vetting*, under *Decisions*). The mod runs the relay identity's skill as a
host command, not a tool call of the session's model, so no post hook sees
it; task 0.18 measures that. The person's answer, and drafts built from a
thread's untrusted text, reach that command, so it runs as an argument
vector with no shell, the text in a file or on standard input, and the
answer session scans each relay post for the credential patterns itself. A
relay post names the question it answers, by replying to it or by a last
line `Re: <URL>`, so a thread holding several questions keeps a state for
each.

The answer session logs no question it relays, except one a questions-branch
file holds. The asker logged the question when it asked, often on an
unmerged branch, and records the answer when it reads the relay's post; when
the asker is a person, or an agent that keeps no log, the thread is the
answer's only record. When the person answers after discussing a question,
the relay post can carry a rephrased question and a one-sentence summary of
the discussion beside the answer. The asker logs those two as body sections
of its log file, since every frontmatter value is one quoted line (*A
rephrased answer carries its rephrasing, and the asker logs it*, under
*Decisions*).

A question from a lore repository's questions branch has no thread, so the
answer session answers it by pushing a new log file to that branch, and when
the file's `asked_in` links a post that also asked it, relays the answer
there too, so neither the asker reading the thread nor an agent searching
the branch misses the answer (*A questions-branch question is answered by a
new log file*, under *Decisions*). Agreeing to the recorded answer shown
beside a question is a reason 2 decline with filter 1 and pushes no answer,
so a later agent is stopped by that record only when its own filter 1 can
read it and counts it as an answer (*Agreeing to a recorded answer is a
filter 1 decline*, under *Decisions*). Every close of a questions-branch
file pushes a handled file, a log file marking the question closed with no
answer; it closes the question only in the person's queue, and filter 1
still shows a searching agent the question as unanswered (*The answer
session writes a handled file on every close of a questions-branch file*,
under *Decisions*).

The answer session ignores a mention of the person, or a mention of or reply
to the relay, that it judges clearly not a question, since rewriting one is
the asking agent's job; a non-question from a review request, an assignment
or a questions-branch file reaches the queue unjudged (*Messages that are
not questions are ignored*, under *Decisions*). The person declines with one
of two reasons, "nothing to answer" and "the inquisitor should have handled
it" (*Two reasons to decline*, under *Decisions*). Which reason a declined
non-question gets depends on whose mistake let it through. If the answer
session picked it up by mistake, the person declines under reason 1 and no
miss is logged. If the asking agent should not have asked it, the person
declines under reason 2 with filter 3's "the agent shouldn't have asked",
and a miss is logged against that agent (*Misses the answer session logs*,
under *Decisions*).

Closing works by exact identity, never by matching (*Closing works by exact
identity, never by matching*, under *Decisions*). A handled file's `closes`
key names the one questions-branch file it closes, on every machine. A file
whose question was also asked in a thread names that message in `asked_in`,
and what the answer session decides about the message applies to the file
(*A log file follows its thread message by exact link*, under *Decisions*).
The thread copy itself is closed on every machine only by a relay post in
its thread; a decline that posts nothing closes it on this machine alone,
while the handled file closes the linked file everywhere. A handled file
closes without answering, so a later answer to the thread copy still pushes
a log file answering the file. Matching copies on the question's words, on
each machine's judgement of its topic repository, or on commit times is
rejected: each left machines disagreeing about which copies were closed, and
exact identity cannot disagree.

An answer file names the file it answers in its `answers` key. The named
file stays shown until that answer counts. The answer file also records the
question as the person saw it, so a file whose `asked_in` points at an
unrelated message never gets the answer recorded against words the person
did not see (*An answer file names the file it answers*; *A named file stays
shown until its answer counts*; *An answer file records the question the
person saw*, under *Decisions*).

Filter 1's search serves a later asker with no file of its own to name, so
it groups answer files by their question's hash and counts the newest in
each group. Two answer files naming one file can record different words,
which puts them in different groups. An older answer could then still count
in its own group after the person changed their answer. To prevent that, an
answer file replaced by a newer one naming the same file is superseded in
the search too (*`answers` decides a named file's answer; the search groups
by hash*, under *Decisions*).

Only an answer file whose proof is the person's, added alone in its commit,
answers a named file. The reason is that a copy of an answer the person gave
to another question carries their proof too (*A named file's answer must be
the person's own, added alone*, under *Decisions*). No decision says whether
such a copy, pushed alone in its own commit, can become a named file's
answer; *Conflicts for Adam to decide*, under *Open Questions*, lists it.

An Igor asks a person through a handback comment on its item, the issue or
pull request it works, carrying a fixed marker that no text an Igor quotes
from its item can produce (*igor's handback marker*, under *Decisions*). No
one uses igor yet, so for the marker, the handback record and `asked_in` the
spec states only the end state, and *Open Questions* asks igor #216 for them
(*igor-dependent rules state the end state*, under *Decisions*). The
worker's log file links its handback comment in `asked_in`. An item is shown
only through its newest handback, which says where the Igor is blocked now;
older handbacks and their files stay unshown (*Only an item's newest
handback is open*; *Each Igor log file follows its own handback comment*,
under *Decisions*). A bot's message reaches only the first person it
mentions, so two people cannot give a bot conflicting answers, and the
answer session never needs to know who an Igor's operator is; Adam decided
the order an Igor mentions people in igor issue #229, which is open. A
handback that mentions no one reaches the item's assignee; #229 states
that rule too, and names no case in which a handback mentions no one (*A
bot's question reaches only the first person it mentions*; *A handback that
mentions no one reaches the assignee*, under *Decisions*). The Igor names
the answered file only from its own record of the handback, never from the
comment's editable text or a word match (*A later run names the answered
file from the Igor's record*, under *Decisions*).

A miss file is pushed even when one with the same question and filter is
already there, since dropping it would mean matching on words (*Misses the
answer session logs*, under *Decisions*).

A log file without `asked_in`, withheld where it would leak (*`answer_link`
and `asked_in` are withheld where they would leak*, under *Decisions*), is
shown as its own question, never paired with a message by matching text, so
the person may see a question twice (*A log file without `asked_in` is never
merged*, under *Decisions*). Merging the two into one entry is rejected: its
only benefit is avoiding that duplicate, and it could pair a message with
another asker's file in the same words, so that a decline closed that
asker's question or an answer was recorded against it.

An answer that cannot reach its thread is kept pending on its machine, not
dropped; one kept because its channel was off returns to the queue once
setup's check of posting there passes (*An answer that cannot reach its
thread is kept pending*, under *Decisions*). Another machine sees only the
thread and asks again, and the first relay post to reach the thread sets the
question's state. For an answer to a questions-branch file's question whose
thread this machine can post in, the session fetches the thread first, so
the person sees any new message before anything is pushed; then the post
goes first and the answer file follows with the post's link, its owed push
recorded beforehand so a crash loses nothing. When the thread's channel is
off or not subscribed on this machine, the answer file is pushed at once,
unchecked, with no `answer_link` (*The push order for a questions-branch
answer*, under *Decisions*).
The pending list reuses the approved queue's screens, so it needs no
prototype round of its own. The file is committed as the person, signed,
never as a GitHub App (*Setup checks questions-branch commits are the
person's*, under *Decisions*).

A relayed answer counts as the person's own for filter 1; otherwise a relay
post, whose author is the relay identity, would fail the writer proof, and
an Igor could never log a handback's relayed answer as a decision (*Only a
listed relay App speaks for a person on GitHub*; *A person's answer to a
handback*, under *Decisions*). Only an App listed in the person's relay
file, `relays/<login>.yaml` on the default branch of the team's lore
repository, ties a `User says: ` comment to them (*One relay file per
person*, under *Decisions*). Owning the App is not enough: an Igor's App
owned by the same person posts its worker's text through igor's own code,
which no post hook sees. igor requires every Igor's App slug to start with
`igor-` (igor PR #216's decision 62), and its configuration names no App, so
no relay-file entry starting `igor-` counts (*An Igor's App is never a relay
App*, under *Decisions*).

A relay file counts only when the newest commit that changed it came from a
merged pull request the person authored, or carries a signature GitHub
verifies for them, so anyone who can push to the lore repository can stop a
person's relayed answers from counting but cannot make another App speak for
them (*Who last changed a relay file ties it to its person*, under
*Decisions*). The notice workflow this skill ships, `relay-notice.yml`,
modelled on igor's seat-notice workflow (igor PR #171), @-mentions the
person on a pull request that changes their file (*A notice workflow
mentions a relay file's person*, under *Decisions*). No reader depends on
it: it warns a person that their file is about to stop counting, or that
someone else pushed to their open pull request, a push that counts as theirs
once it merges. One file per person follows igor's `seats/<id>.yaml`: the
person's own pull request adds it, and a path, unlike a key in a shared
file, names whose it is.

The tie holds only because the prefix is reserved (*Only the prefixes are
reserved, not the identity*; *The post hook blocks a reserved prefix on
GitHub*, under *Decisions*), so a person lists only an App nothing else
posts through unseen. github-app's `token` command prints an App's token to
any agent on the machine, which could then post with a plain HTTP call no
hook sees. Adam decided that github-app should let a person mark an identity
as a relay and then refuse `token`, `run`, `credential get` and `wire` for
it, leaving only its own posting command, which the post hook reads when an
agent runs it. Like the post hook, that guards against accidents, not a
determined forger (*github-app refuses `token`, `run`, `credential get` and
`wire` for a relay identity*, under *Decisions*). It is a separate change to
github-app, not yet written; until it ships, the cost is accepted and the
README says so.

Task 0.21 measures whether GitHub reports which App wrote a comment. Until
it shows GitHub does, a relayed answer is input, and if it shows GitHub does
not, no comment is ever a relayed answer. A relay post on Linear or Discord
that an agent reads stays input, but the answer session's own log file of
such an answer to a questions-branch question can count through its commit's
signature (*Questions-branch answers relayed on Linear or Discord*, under
*Decisions*).

The relay file is YAML, matching the lore repository's other configuration,
under `relays/` in the lore repository holding the entries (*What a lore
repository means here*, under *Decisions*; igor PR #216's decision 66). It
has one list per surface, and only the `github` list proves anything. A key
of `igor.config.yaml` was rejected, since igor refuses any key it does not
read, and so was `inquisitor.json`, which is per person and on their
machine, where no other reader sees it. igor PR #208 has an Igor fetch its
lore repository and apply only commits that pass igor's startup checks. An
Igor reads relay files as of the last commit it applied that way, so under
`igor run`, which
never fetches, no relayed answer counts, while an answer in the person's own
comment does (*An Igor reads relay files as of igor PR #208's applied
commit*, under *Decisions*).

Editing a relayed answer also logged on a questions branch pushes a new log
file, and the newest proven answer counts, newest by the comment's last edit
or the signed commit's date, not by branch history, so nobody with push
access can revert an answer by re-pushing an older file (*The newest proven
answer counts*, under *Decisions*).

### What the answer session does by itself

The answer session runs filter 1 on every incoming question, and judges the
rest by filters 2 to 4 (*Filter 1 runs on every incoming question*; *Filters
2 to 4 judge every incoming question*, under *Decisions*), so the person
sees only what needs them. Posting without the person raises two risks, and
the spec answers each:

- **A thread's text reaches the model that judges it.** The model writes no
  word of an automatic post: an `Inquisitor: ` post is one of three fixed
  texts, for filters 2, 3 and 4, and a recorded answer only points to filter
  1's hit and quotes nothing from it (*What the answer session posts by
  itself*, under *Decisions*). So a crafted question can at worst choose
  which canned reply or which record is posted. Even that matters, since
  filter 3's and 4's replies tell the asking agent to decide the question
  itself. So the agent acts by itself only on filter 2's reply, which only
  defers, and on filter 3's or 4's only when its last line, `The person
  chose this filter.`, says the person chose it, a line the answer session
  never posts by itself (*What an asking agent does with an automatic
  reply*, under *Decisions*). The answer session judges an agent's reply to
  an automatic post again, and posts nothing, showing the reply to the
  person, when its post would repeat any automatic post in that chain of
  replies; otherwise an agent that kept replying could get filter 2's text,
  then filter 4's, then filter 2's again with no person seeing it (*No
  automatic post repeats one in its chain of replies*, under *Decisions*).
  Only a bot account's question gets an `Inquisitor: ` reply by itself, so a
  person never gets a reply nobody wrote; a `User says: ` or `User asks: `
  post from a bot relays a person's words and counts as a person's question
  (*Which questions count as an agent's*, under *Decisions*).
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the thread;
  otherwise the person sees it and decides.

Every automatic post can be edited, and an edit makes it the person's words,
starting `User says: ` (*Editing a relay post*, under *Decisions*).

The misses the answer session logs go to the questions branch of the team's
lore repository, since it can't see where the asker logged the question,
often an unmerged branch, and the questions branch takes a direct push. A
miss is a lesson about an asking agent, so a message the answer session
picked up by its own misjudgement logs none (*Misses the answer session
logs*, under *Decisions*).

### The session's model

A discussion runs in the session's own conversation, so the model has its
tools and can read the question's thread, the code and the specs before it
replies (*A discussion runs in the session's own conversation*, under
*Decisions*). Each message carries the question as context. The model may
ask the person in its reply there, the one exception to the rule that an
agent asks only through the picker: the person opened the conversation to
talk the question through, and a picker would hide the answer session's
screen. The model posts nothing: its draft goes through `propose_reply` into
the prompt box (*Claude drafts a reply only into the prompt box*, under
*Decisions*), and the person relays it. No hook enforces that the model
posts and changes nothing; the context tells it, and the post hooks still
vet any post it tries. The model's tools reach what the person's own
commands can, the keychain holding the Linear key included, as in any
session. The answer session adds no guard against that: it is the same
exposure as the person's `gh` login, and Adam accepted it. The prototype has
shown that a mod can fill the prompt box and register a tool the model calls
by name.

## Tracing scenarios to tests

Every scenario but the expected gaps below gets a tagged test, since
spec-trace's CI fails on an untagged scenario in `openspec/specs/`, where
archiving this change writes its scenarios, and spec-trace's baseline
(`openspec/spec-trace-baseline.txt`), which lists exempt scenarios, takes no
new lines. Where a scenario is about the script or a hook, the test runs it.
Where it is about what the agent does (asking through the picker, batching,
handing a question back, choosing a lesson's scope), the test checks that
SKILL.md states the rule, and its name says so.

**Expected gaps.** A scenario that only igor's unbuilt work, such as `igor
lore-search`, can make pass gets no tagged test until igor builds it, so
spec-trace shows it as uncovered (*Igor-worker scenarios stay untagged until
igor builds what they need*, under *Decisions*). A skipped test would not
do: spec-trace counts a skipped test's tag as coverage. Task 4.2, which
writes the tests, lists each expected gap here by name, and task 4.3 tags it
once igor provides what it needs. Until
the change is archived, its scenarios sit outside
`openspec/specs/`, so CI passes; archiving with a gap untagged would fail
CI, so the change is archived only after task 4.3 has tagged every gap (*The
change is archived only after every expected gap is tagged*, under
*Decisions*).

## Decisions

Every decision below is Adam's: he gave it, or confirmed it after this change
proposed it, between 2026-10-19 and 2026-10-30. An entry this change first
took itself, without asking, under its own skill's filter 3 or 4 (one option
has merit, or switching later is cheap) names in its **Why:** the filter it
was taken under; Adam's confirmation made it his. Each entry states the decision, its reasons
and the alternatives rejected.

Terms used throughout, as the specs define them:

- **igor** is a separate project of AI teammates (adamstallard/igor). **An
  Igor** is one of those teammates, and its **worker** is the agent it
  starts to do an item. An Igor **injects** lore: it puts `active` lore
  entries into its workers' context unasked.
- **Lore** is a team's lessons for agents, kept as entries in a **lore
  repository** (*What a lore repository means here*). A lore repository's
  **questions branch** holds question and miss files beside the entries.
- **The picker** is Claude Code's question tool, `AskUserQuestion`, which
  shows a person a question with options to choose from.
- **The first call** and **the second call** are the two runs of the
  skill's script for a set of questions. The first runs filter 1's search;
  the second records a **verdict** for each question: `answered`,
  `deferred` (filter 2 put it off), `decided` (filter 3 or 4 chose), or
  `ask` (a person must answer it). The skill's two hooks, **the picker
  hook** and **the post hook** (for GitHub posts), let a question through
  only on a fresh verdict (*Two calls prove the filters ran*).
- **A category** marks a sensitive question: `vulnerability`, `secret` or
  `personal`. The skill's records keep such a question by hash only
  (*Three categories are recorded by hash only*).
- **A miss** is a question that a person said, or an answer session
  clearly judged, need not have been asked. A **miss file** records it.
- **The answer session** is where a person answers questions put to them
  on GitHub, Linear and Discord. A **relay identity**, a bot, posts each
  answer for them, starting `User says: `. On GitHub it is a GitHub App,
  the person's **relay App**, which their **relay file**,
  `relays/<login>.yaml` in the team's lore repository, lists. A **relayed
  answer** is a GitHub comment starting `User says: ` whose author is a
  person's relay App.
- **Gate one** is Adam's approval of this change's spec, in a pull request
  holding only the spec. **Gate two** is the implementation, built on the
  same branch after that approval.

### Asking a person

#### Four filters stop questions before a person

**Every question an agent is about to put to a person passes four filters
first, and is asked only if none of them stops it: already answered,
deferrable, not a real question, and cheap to reverse.** The rule covers any
agent in any task, not only spec review or OpenSpec. The skill is useful
locally and needs nothing from Igor. Under filter 1, the earlier answer may
be in another spec or another decision document.

#### The Igor inquisitor role is out of scope

**The Igor inquisitor role, an Igor that brings surviving questions to a team
discussion, is out of scope; igor #211 tracks and governs it.** The role would
take over the questions behind items an Igor hands back, ask a blocked Igor's
question for it, receive that question through the blocked item, keep a
budget of posts per channel, and route an Igor's handback comment. Under
igor #211's decision 9, a team without the role has nothing post that
comment to a discussion, batch it or tag anyone, and nothing in this change
does. The filters a blocked Igor runs on its own question are this
skill's.

#### "A decision document" is a closed list

**"A decision document" means only the closed list the spec defines. The wider
set of places an answer can go, which adds a question's log file and a
person's memory or `CLAUDE.md`, is "where the question's answer is
recorded".**

#### Filters 3 and 4 record the agent's choice

**Under filter 3 (fewer than two options have merit) or filter 4 (switching
later is cheap), the agent decides without asking and records its choice where
the question's answer is recorded.** With no decision document to hold it, the
choice goes in a log file with `authority: agent` (*An agent's choice counts
only in the work it belongs to*).

#### A deferred question stays visible

**Filter 2 defers a question without asking, and the deferral stays visible:
the question is listed as not done in the current work, and filed as an issue
if it outlives the work.** A person who wants the answer now says so. The
`deferred` verdict names where the question is to be listed, such as "this
PR's description", not a link, because that post may not exist yet.

#### Questions another skill requires skip filters 2 to 4

**A question that another installed skill requires a person to decide is
exempt from filters 2, 3 and 4, so it is asked now; only filter 1 applies, and
its `ask` verdict names that skill.** The exempt questions are whether to
adopt spec-trace, and prose's `kept (asked)` findings: cold-read findings
that prose requires a person to approve keeping. bug-hunter's Step 9
recommendations are not exempt.

#### bug-hunter's Step 9 recommendations go through the filters

**bug-hunter's Step 9 recommendations go through the inquisitor skill's
four filters, like any other question, so fewer reach a person** (Adam,
2026-10-30). Step 9 reports each recommendation and asks the person about
it, one at a time. There are four kinds: a root cause, a finding too large
for the change, anything left unresolved when the run aborted, and a
property from the hunt (Step 3) worth keeping as a permanent guard. Task
5.7 changes bug-hunter's SKILL.md so that Step 9 runs each recommendation
through the inquisitor skill before asking. Nothing in bug-hunter changes
before the inquisitor skill exists.

**Why:** every skill's questions go through one set of filters, rather than
each skill making its own exceptions.

*Rejected:* changing bug-hunter's Step 9 rules on their own, ahead of the
inquisitor skill: that would be a rule of bug-hunter's own that skips the
shared filters.

The table holds the starting rules for task 5.7. They are input to its
design, not decided behaviour: whoever builds task 5.7 at gate two sets the
final rules, and Adam reviews them with the implementation. The spec fixes
only that each recommendation passes the four filters.

| Step 9 recommendation | Settle it without asking when | What to do then | Filter |
|---|---|---|---|
| A Step 3 property worth keeping as a guard: a property-based check the hunt ran against a stated invariant | The check is bounded in runtime, runs with a fixed seed, and needs no new dependency | Keep it as a test | Cheap to reverse |
| A finding too large for the change | Always | File it as an issue with its evidence, and report the link | Deferrable |
| Something left unresolved when a bug-hunter run aborted after its third iteration | A new bug-hunter run over it would be cheap | Record it where the repository keeps open questions, and report it | Deferrable |
| A root cause | It was already decided or rejected (look it up), or its fix is small and defensible | Fix it, and run bug-hunter's loop over the fix | Already answered; cheap to reverse |

A recommendation that no row settles still goes to the person, such as a
root-cause fix that is broad or turns on a design choice, or an abort's
leftover whose new run would be costly.

#### A prepared question can be answered "yes"

**A question that survives the filters states the recommended answer, what
changes under each other answer, and a link to any related earlier decision.**
In the picker the recommendation is the first option, and the second call
checks that it is.

**Why:** most questions can then be answered "yes". The picker hook need not
check the order: reordering options after vetting changes the question's
text, which the hook blocks as unvetted.

#### Questions met at one step are batched

**Questions that survive the filters at one step of the work are asked
together, in one picker call, up to the picker's limit of questions per
call, or one section of one post.** More questions than that limit take
further picker calls. A budget of posts
per channel belongs to the out-of-scope Igor inquisitor role.

#### With a person present, ask through the picker

**Where the host has a picker and a person is in the session, an agent never
asks in its reply. It asks only in one of these places: the picker; a post;
a Linear or Discord message; or, for a vulnerability, the repository's
private security advisory.** Where the host has no picker, the spec's
"picker" means the reply, once the two calls have vetted the question, and
no hook checks it. A subagent returns each surviving question, prepared, to
the agent that started it. The answer session's discussion is the one
exception (*A discussion runs in the session's own conversation*).

**Why:** the picker hook then sees every question. The starting agent is the
one talking to the person, and can batch a subagent's questions with its own
(*Questions in posts*).

*Rejected:* a hook at the end of the agent's turn that reads questions in its
reply: the person has already read the reply when it runs.

#### How a session with no person asks

**A session with no person in it never uses the picker, which is for a person
to read.** A session counts as having no person in it when the agent cannot
tell; how it tells is unmeasured (task 0.9). A session able to post, such as
a scheduled agent, posts its question. An Igor worker holds no credential
that can post, so it asks only in its handback comment. A session that can neither post nor hand back
asks nowhere: it stops only if the work needs the answer, and reports the
question in its output.

**Why:** counting an unclear session as having no person means a picker is
never opened with nobody to answer it.

#### Headless sessions hold back sensitive questions

**A session with no person in it never asks or posts a `secret` or `personal`
question, and asks a `vulnerability` question only in the repository's private
security advisory; it stops the work that needs the answer and reports only
that a question of that category is blocking, with no text.** In an Igor's
run the worker reports igor's flag instead (*The flag a worker raises for a
question with a category*). A way-of-working question is held back the same
way: the session stops only if the work needs the answer, and reports that
the question waits for the person.

#### Recontextualise a question or don't ask it

**A question is about one thing, a repository, an organization or a project,
or one person's way of working, and is written at that thing's privacy.**
Context from something more private is generalised ("because some private
backend might do Y", not "because gmango's backend does Y") or left out. A
question that cannot stand without that context is not asked, and is never
filed in a more private place to keep it.

#### A question's audience is no wider than its subject

**An agent puts a question only where the audience is no wider than what the
question concerns, in every channel, Linear and Discord included; visibility
is ranked as *Nothing goes somewhere more visible than its source* gives.**
Where the place would be wider, the agent asks through the picker, or, in a
session with no person in it that can post, posts in the repository the
question concerns; for an organization's or project's question, the
repository holding the current work. Where the agent cannot tell, it asks
through the picker, or, with no person in the session, posts nothing and
reports that it did not.

#### What counts as a question in a post

**A question in a post is each list item in an open-questions section, and
each other sentence ending in a question mark, as defined once in the spec's
requirement *A question in a post is a listed item or a sentence ending in a
question mark*.** A section begins only at a heading, bold label or plain
colon line whose label names questions, such as "Open questions:", or at a
deferral label, such as "Not in this change"; it runs to the next heading or
bold label. The requirement's scenarios list the labels. A post is vetted
after prose's pass and before prose signs it; *Questions in posts* gives the
reasoning for colon lines and for that order.

**Why:** this change took the rule under filter 4, without asking, since it
lives in one function and is cheap to change.

*Rejected:* letting any colon line starting with "Open" begin a section: "Open
a terminal and run:" would turn its commands into questions.

#### A deferred question passes only untagged and listed

**A `deferred` verdict of any age passes the post hook only for a question
listed in an open-questions section and tagging no one, or a question in a new
issue that tags no one; anywhere else the question needs an `ask` verdict.**
Filter 2's two places, the work's description and an issue, then both pass.

**Why:** a deferral asks nothing, so its verdict need not expire. Tagging
someone asks them, which needs an `ask` (*Questions in posts*).

#### One person who can decide is tagged

**A question in a post tags one person who can decide: the first the script
finds with write access to what the question concerns, among whoever approved
the related earlier decision, a login in `.inquisitor/reviewers`, then whoever
last changed the files involved.** An organization's or project's question
uses the team's lore repository's reviewers file. Unreadable access counts
as none.

**Why:** only a person with write access can decide. The reviewers file is in
the repository, so every teammate's agent tags the same person
(*Configuration*).

#### The configured login names the person

**The person running the session is the inquisitor configuration's GitHub
login, and only when `gh` is logged in as that same account; otherwise no
login is configured.** The script confirms it with the person's own `gh`
login, never a GitHub App's token, so nobody claims a maintainer's login by
typing it into their own configuration (*Configuration*).

*Rejected:* taking the login from `gh api user` where the agent posts: as a
GitHub App it gives no user, and as the person it gives their own login, so
the agent would tag itself.

#### When no candidate can decide

**When no candidate in the tagging order has write access, the script turns to
the configured login, and the outcome depends on that login and on who the
post goes out as:**

- **Write access, post going out as someone else:** tag the configured
  login.
- **No login configured, or write access with the post going out as that
  login:** with a person in the session, ask through the picker instead of
  in the post; with none, tag no one.
- **No write access:** tag no one.

A question that tags no one is posted with a line saying that no one with
authority to decide could be found.

**Why:** a self-tag sends no notification.

### Hooks and verdict records

#### A picker hook makes agents run the filters

**A hook on Claude Code's question picker (`AskUserQuestion`) makes an agent
run the inquisitor before it asks.**

**Why:** *Proving the filters ran* gives the reasoning and the rejected
alternatives, the skill's description alone and a hook that runs the filters
itself. *What the hook relies on, not yet measured* says what happens if
tasks 0.1 to 0.3 show that a `PreToolUse` hook cannot block the picker.

#### The hooks are on once the skill is installed

**The skill's hooks are enabled by default: installing the skill is the
opt-in,** as it is for prose's blocking hooks.

#### Two calls prove the filters ran

**The skill's script takes each set of questions in two calls, as prose's two
calls prove its pass ran.** The first prints the four filters, runs filter
1's search and issues a token. The second must present that token, and
records a verdict for each question the first took, so no verdict exists
without the search. The picker hook allows a question only when the latest
verdict on its text is `ask` and less than 2 hours old. The post hook also
allows a `deferred` verdict where a deferral may be listed (*A deferred
question passes only untagged and listed*).

**Why:** *Proving the filters ran* gives the reasoning, and why a signed
footer inside the question was rejected.

#### Files passed to the two calls stay private

**The files an agent passes to the two calls go in a private directory outside
any repository, made with `mktemp -d` so that only the agent's user can read
it, and each file has mode 0600.** Being outside any repository, the files
can't be committed. The script refuses a file readable by its group or
others. A question with a category reaches the script on standard
input, never in a file.

**Why:** in a shared temporary directory such as `/tmp`, a file with the
usual mode, and the question's text in it, is readable by every user of the
host.

*Rejected:* the system's temporary directory, for that reason.

#### Verdict records live in the user's state folder

**The hooks' records live in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`, beside prose's session
marks.** They hold hashes, verdicts, verdict fields and times, never a
question's text, so as the hooks' state they are no personal question log.

**Why:** *Proving the filters ran* gives the reasoning, and why the
repository's git directory was rejected.

#### An `ask` record drops the option's label

**For a picker question, the hooks' record of an `ask` keeps what changes
under the other options, but not the recommended option's label.** The
labels are part of the question's text, which no record holds; what
changes under each option is the agent's own words, from the verdict.

**Accepted:** no record shows which option the agent recommended, so the
records can't show later whether the person took the recommendation.

#### Verdict records are shared under one HOME

**Everything that runs with the same HOME shares one set of verdict records,
Igor workers included,** so one worker's verdict on a text lets another
worker ask that text.

**Why:** a verdict is about the question's text, not the worker.
*Proving the filters ran* says why per-clone records, as prose keeps its
tokens, were rejected.

#### Records hash a question with plain SHA-256

**A verdict record identifies its question by the plain SHA-256 of the
question's text.**

**Accepted:** a short sensitive question could be guessed from its hash, but
only for 2 hours. This rests on the agent giving every sensitive question
one of the three categories (*Three categories are recorded by hash only*),
since every record with a category is deleted after 2 hours. A sensitive
question the agent leaves uncategorized with a `deferred` verdict is not
covered: an uncategorized `deferred` record lasts until a later verdict
replaces it.

*Rejected:* an HMAC with a per-HOME key, which would stop that guessing: the
2-hour limit already keeps the exposure brief.

#### Every verdict record expires after 2 hours

**Every verdict record, with a category or without one, is deleted 2 hours
after it was made, except a `deferred` record without a category.** That one
is kept until a later verdict on the same text replaces it, since the post
hook accepts a deferral of any age. A categorized `deferred` record expires
like any other, as a categorized question never goes in a post. Two hours is
how long a hook uses a record: the picker hook accepts an `ask` only while
it is less than 2 hours old. No record the skill keeps lasts for a question
with a category.

**Why:** a lasting record of such a question would be either personal or
public. Kept on the person's machine, it would be a personal question log,
which the skill rules out. Kept with the questions, it would show in a public
repository that such a question was asked, and when.

#### A post edited after 2 hours is vetted again

**When a post is edited more than 2 hours after one of its questions got an
`ask` verdict, that question is vetted again.** A `deferred` question never
needs this, since its uncategorized record does not expire.

**Why:** vetting again costs only one pair of calls.

#### A hook spends no verdict record

**The picker hook and the post hook spend no verdict record, so a record stays
valid after a hook blocks a call because of another question in it.** Each
record still expires as *Every verdict record expires after 2 hours* says.

**Why:** when one question blocks a call, the agent vets that question alone
and calls again, and the call's other questions need no vetting again.

#### The related-decision line is left out of the hash

**The hooks match a question's text without its related-decision line:
`Related: ` and one URL with no spaces, on a line of its own.** The related
decision turns up in the first call's search, so the agent adds the line
after that call with no second vetting. No vetting sees that line, so both
hooks block a related-decision line holding a credential pattern.

**Accepted:** the agent links only a decision that everyone who can read the
question can read, and no hook checks that.

#### What each hook does when it can't read

**The picker hook lets a question through when it can't read its input or its
verdict records.** The post hook lets through input that is not JSON. It
blocks a `gh` command whose body it can't read, and a post holding a question
when it can't read its verdict records.

**Why:** an unfiltered picker question publishes nothing, but a published
vulnerability can't be taken back (*Proving the filters ran*).

#### The host's transcripts are outside the skill's records

**The rules on what the skill's records keep, the hash-only rule for a
question with a category and the 2-hour expiry, cover only the skill's own
records.** The host's transcripts, such as Claude Code's under
`~/.claude/projects/`, are outside the skill's control.

**Accepted:** those transcripts hold a question asked through the picker in
full.

### The shared post reader

#### Questions in posts pass the filters, on GitHub only

**A question in a post an agent is about to send passes the same four filters
as any other question, and the post hook enforces this for GitHub posts only,
as prose's posting hook covers GitHub only.** The hook sees posts sent through
`gh` or a GitHub MCP tool. A question in a Linear or Discord message is
covered by the skill's instructions alone. A surviving question is prepared
and tagged like any other.

#### One post reader, shared by both hooks

**prose's posting hook and the inquisitor's post hook read every post through
one library, `.agents/lib/gh-post/`, which is prose's reader moved there.**
The reader tells a hook the post's body and title, that the call sends no
post, or that the call is unreadable, and each hook blocks an unreadable call.
The reader's rules are stated once, in the `gh-post` capability spec, and the
inquisitor's spec points to it. Every rule the reader gains applies to prose's
hook too. *Questions in posts* gives the reasoning, and which prose tests
change.

*Rejected:* a copy of prose's reader in the inquisitor: prose's parser had
about 25 places where it misread commands before it was cut to an allow-list.
*Rejected:* calling prose's copy from the inquisitor: it would fail whenever
prose is not installed.

#### Which commands the reader judges, and which are unreadable

**A command line that mentions a gh post verb is read only through the
allow-list, and each simple command in it that names `gh` is unreadable unless
it is a `gh` command the reader reads or one of prose's data commands naming
`gh` only inside a quoted argument.** prose's data commands are a closed list
of commands that read or print text, such as `echo`, `cat`, `grep`, `git`
and `python3`. "A gh post verb" is the closed list prose's reader handles:
certain verbs of `gh pr` and `gh issue`, and a `gh api` write. So `sh -c
'…'`, `bash -c '…'` and `eval '…'` around a `gh` post are unreadable, and so
is a pipe into a shell. A command that runs only prose's own script,
`prose.py`, is no post, since its arguments may name a gh post as text. A
`gh` command whose first word after `gh` is not one of gh's own commands,
such as an alias or an extension, is unreadable.

**Why:** these are prose's reader's rules, so moving the reader changes
nothing prose does. Without the alias rule, `gh c 5 -b 'User says: yes'`, with
`c` aliased to `pr comment`, would pass both post hooks as no post, unseen by
the block on a forged relayed answer (*The post hook blocks a reserved
prefix on GitHub*).

*Rejected:* letting a command through when `gh` appears in it only inside
quotes: `sh -c 'gh pr comment …'` would then post unread.

#### Code given on the command line that names gh

**A command that runs code given in the command, and whose code names `gh`,
is unreadable, data commands included,** and both post hooks block it. The
data commands that run such code are `python` or `python3` with `-c`;
`node` with `-e`, `--eval`, `-p` or `--print`; and `git` with `-c`, which can
set an alias that runs a shell command. The git forms that run a command
they are given count the same way, unreadable when the command they run
names `gh`, such as `git rebase -x`/`--exec`, `git submodule foreach` and
`git bisect run`. `python`, `python3` or `node` taking its
program from standard
input, such as a heredoc or a pipe, is no data command, so feeding one its
program on a line that mentions a gh post verb is unreadable.

**Why:** each of these can run a `gh` post that the reader never sees, as `sh
-c`, `ruby -e` and `perl -e` can.

**Accepted:** prose's hook blocks these forms too. A prose test expecting one
to pass is changed, and prose's `DECISIONS.md` does not call them outside
the hook's reach.

#### Posts sent through the github-app skill's script

**A post sent through the github-app skill's script, `python3 <github-app
script> gh pr|issue …` or `python3 <github-app script> run -- gh …`, is read
by the rules of the `gh` command it runs.** `--identity <name>`, the
skill's way to choose an identity, may come before `gh` or `run`. The script's
path must end in `/github_app.py`, given either written out, as a word the
shell passes unchanged apart from removing its quotes, or as `$G`, where the
same command sets `G` to such a word. A command that runs `python3 $G`,
mentions `gh` and assigns `G` nowhere earlier in the same command is
unreadable, and the block message says to set `G` in that command or write
the script's path. This change edits the github-app skill's SKILL.md to set
`G` in the same command as each use, or write the script's full path.

**Why:** otherwise every post an agent sends as a GitHub App would be blocked
as unreadable (*Questions in posts*). The path must end in `/github_app.py`
because the reader cannot know what any other script posts, and prose's
reader blocks a `gh` word passed to one. In Claude Code each command starts
a fresh shell, so an unset `$G` fails and posts nothing; only a host whose
shell keeps variables between commands, such as Cursor, could post through
it. Blocking it costs only a rewrite of the command, so nothing needs
measuring. With the SKILL.md edit, a post copied from its examples passes as
written instead of being blocked and resent.

#### Posts written with gh api

**A `gh api` call writes when its method is `POST`, `PATCH` or `PUT`, set by
`-X` or `--method`, or implied by fields or `--input` without `-X GET`; the
reader blocks as unreadable any write whose body it can't read.** For an
issue, pull request, comment or review, the body is a `body=` field given
through `-f`, `--raw-field`, `-F` or `--field` (the last two also read
`@<file>`), or `--input`. A field is read only when the shell would pass its
word unchanged apart from removing its quotes, so `-f body=$B` is
unreadable. A review's comment bodies are each `comments[][body]` field and
each `body` in an `--input` file's `comments`; a review whose comment bodies
can't be read is unreadable. A write with no `body` field sends no post. A
write carrying a `body` to an endpoint the reader does not read is
unreadable, with a scenario of its own.

**Why:** otherwise a `gh api` comment would skip both hooks unread. Reads,
such as GraphQL queries, and label edits send no text, so they pass.

#### GraphQL mutations that post text

**The reader returns every `body` argument of a GraphQL mutation that posts
text to an issue or pull request, as it returns a REST write's `body` field.**
Those mutations are a closed list of thirteen, from `addComment` to
`updatePullRequestReviewComment`. Another mutation sends no post, but one
with a `body` argument is unreadable, like a REST `body` sent to an
endpoint the reader does not read. A mutation the reader cannot parse, or
whose `body` it cannot read, is unreadable. A `createIssue` post creates an
issue, as a `POST` to `repos/<owner>/<repo>/issues` does.

**Why:** a mutation is a write like a REST one, so the same rule applies: it
is blocked only when its body can't be read, and one with no `body` sends no
post.

*Rejected:* reporting every GraphQL mutation as unreadable: it would block
writes that send no text, which the REST rule lets through.

#### A post's title is read and vetted

**The reader returns an issue's or pull request's title with its body, and
both post hooks check the title.** The inquisitor's hook treats a title as
running text, finds a question as a sentence ending in a question mark, and
blocks it until vetted. prose's hook checks only that the title is
readable: a title gets no prose pass. A title the reader can't read exactly,
such as one built with `$(…)`, makes the call unreadable to both hooks. As
with a body, the reader reads a title only from a `gh` command that is the
whole command line: `cd x && gh pr edit 3 --title 'Rename?'` is unreadable.
`--fill` and its variants, which take the title and body from commits, are
unreadable.

**Why:** otherwise a question in a title goes out unvetted. *Questions in
posts* says why prose's hook checks only readability.

#### The post hook blocks a reserved prefix on GitHub

**The inquisitor's post hook blocks a tool-call post on GitHub when any body
the reader returns for it starts with `User says: `, `User asks: `, `Recorded
answer: ` or `Inquisitor: `.** It checks the reduced body, leading whitespace
dropped, so ` User says: ` and `**User says:**` are blocked too. This decision
reduces the body as a comment is reduced for comparison with a recorded
answer (*A linked comment holds the answer only when the texts are equal*),
but that reduction also ignores a leading `User says: `, which, taken
literally, defeats this block. The spec's *The post hook vets what the
shared post reader returns* instead reduces it as a question in a post is
reduced for its hash: inline markup to its text, whitespace joined. Which
rule stands is Adam's to decide (*Where the spec and a decision differ*).
The reasoning for reserving the prefixes is the last paragraph of the
overview's *Polling while open, with the person's credentials*.

**Why:** the answer session posts through a host command that no tool hook
sees, so a tool-call post with a reserved prefix is never the answer
session's. A `User says: ` comment from the person's relay App proves their
answer, and that App may do other work, so the block stops an agent holding
the App from forging an answer through `gh`.

**Accepted:** nothing checks Linear or Discord, where a relayed answer proves
nothing.

#### No exemption for an Igor's handback

**The post hook vets every post it sees, one carrying igor's handback marker
included; only the answer session reads the marker.**

**Why:** a marker any agent can add would let a post bypass vetting, and an
exemption would help no real handback: an Igor posts its handbacks through
its own code, which the hook never sees.

*Rejected:* recognising a handback by the marker and an `igor-` App author
together, since no real handback reaches the hook.

### Logs and privacy

#### Every asked question is logged with what it concerns

**Every question asked is logged, pointing to where its answer is recorded, so
the next agent finds the answer instead of asking again.** Each question
concerns a repository, an organization or project, or one person's way of
working; one that concerns none of these is not asked. Its record is kept
with what it concerns, at the privacy that place's maintainers set. No
question log is kept under the person's home directory, or anywhere else
personal. An answer about one repository lives in that repository; one
spanning repositories goes to the team's lore repository's questions branch,
or into lore itself when it is important enough.

These asked questions get no log file:
- one person's way-of-working question;
- a question with a category;
- an organization's or project's question raised by work in a repository
  more private than the team's lore repository, which the script refuses to
  push to that lore repository's questions branch;
- an organization's or project's question with no lore repository
  configured, or asked while working in no git repository;
- an Igor worker's handback question in a run that publishes no artifact,
  such as a pull request; the handback comment is its record until a later
  run on the item publishes one (*An Igor worker asks only in its handback
  comment*);
- the question a flagged run stopped on (*A flagged run asks nothing and
  pushes nothing*).

**Why:** *Where the logs live* gives the reasoning.

*Rejected:* a personal log under the home directory: it would keep a
question, with its private context, where only one person finds it.

#### A repository's questions are committed with the work

**One repository's question is logged as one file under
`.inquisitor/questions/` at that repository's root, committed with the work,
not on a branch of its own.** For a repository other than the current
work's, the agent opens a pull request with the file without asking first,
as it does for a proposed lore entry; the current work's commits can't carry
a file into another repository. Each file's name has a random suffix, so two
branches that each log a question never write the same file.

**Why:** a change's questions belong in its history, and merge with it.

**Accepted:** until the work merges, its log file is invisible to parallel
work, so an agent on another branch or pull request may ask the same
question again. A file pushed to the lore questions branch has no such cost:
the next fetch finds it.

*Rejected:* one log file that every question appends to: two branches that
each log a question conflict when they merge.

#### Organization questions go on lore's `questions` branch

**An organization's or project's question is logged on an orphan branch,
`questions`, in the team's lore repository, pushed directly with no pull
request.** It is not igor's `igor-state` branch, which holds igor's runtime
state. It holds the question and miss files about the organization or
project: questions not important enough to become lore, but worth keeping so
nobody asks them again. Nothing on it is given to agents as lore, and it has
the lore's privacy and access, set by the lore repository's maintainers.
Filter 1 searches the lore entries and this branch, reading the branch with
`git fetch` and `git show`, without checking it out.

The lore repository's default branch holds only lore entries. Promoting an
answer to lore is a pull request to the default branch adding a `provisional`
entry, and the question's file stays on the questions branch.

A push rejected because the branch moved is fetched and pushed again; the
random suffix means two pushes never write the same file. A push rejected
for any other reason, such as no push access or a branch rule, is not
retried: the agent logs nothing and says why. With no lore repository
configured for the owner of the question's repository, an organization's or
project's question is not logged, and the agent tells the person so.

**Why:** the default branch stays uncluttered and holds only what Igor gives
agents as lore. *Where the logs live* gives the full reasoning.

*Rejected:* a pull request for each question file: a question's authority
comes from who answered it, so it needs no review.

#### A way-of-working question gets no log

**One person's way-of-working question, such as "should I keep working while
you're away?", is not logged:** its answer goes into the person's memory or
`CLAUDE.md`, which agents already read.

#### Log and miss files have one format, stated once

**Log and miss files share one format, stated once in the spec's *A log file
and a miss file have one format*, as the citation file's is; design.md
points to it.** That requirement holds the path, the file name
(`<date>-<slug>-<6 random hex digits>.md`, the date in UTC, the hex digits
lowercase), the slug rule, the encoding and each file's closed list of
keys, and covers a rephrased answer's additions. The decisions on answer
links, `asked_in`, `asked_from`, `answers` and handled files add the keys
they name; *A log file's answer is written as quote lines* says how an
answer is written.

#### prose's pass skips `.inquisitor/`

**prose's pass skips files under `.inquisitor/`.** A log or miss file is a
record that quotes a question as asked, and what a person said, word for word;
prose's rewrite would change it. prose's file filter skips them from gate two,
when the skill ships (task 5.6), and prose's `DECISIONS.md` records why at
archive (task 7.1).

#### Nothing goes somewhere more visible than its source

**Visibility is ranked private, then internal, then public, and nothing goes
to a more visible place than what it concerns.** GitHub's `INTERNAL` is
visible to a whole enterprise. A private repository's question or answer never
goes to an internal or public lore repository or post, and an internal
repository's never goes to a public one. The script's refusal to open a lore
pull request to a more visible lore repository also covers pushing a question
to a lore repository's questions branch, and promoting an answer from there
into lore. An unreadable visibility counts the cautious way: private for the
question's repository and for an `asked_in` URL's target, public for a lore
repository or a post's target. The one exception, a recorded answer's link
the person confirms, is in *Agreeing to a recorded answer is a filter 1
decline*.

**Why:** a question's record keeps the privacy of what it concerns. Each
default makes the cautious choice, so nothing is sent somewhere that might
be more visible; a private `asked_in` target means the URL is withheld
unless the lore repository is private too. *Configuration* gives how
visibility is read.

#### Records are written at the question's privacy

**A question, a miss's record of what the person said, and an agent's own
choice are written at the privacy of what the question concerns: more private
context is generalised or left out.** A person's answer is never generalised:
it is recorded in their own words or not at all. When those words hold context
more private than what the question concerns, the question's file gets no
answer, and the question stays open. The agent uses the answer in the work,
and its report says the answer could not be recorded at this privacy. A later
agent may ask again. A file for a question never asked, such as an agent's
filter-3 or filter-4 choice, follows the same rules, with `answered_by:
agent`.

**Why:** writing at the question's privacy covers everything recorded about
it, and a person's answer, kept in their own words, can't be generalised.

#### Three categories are recorded by hash only

**A question in one of three categories is kept in none of the skill's own
records in readable form: `vulnerability`, about a security vulnerability not
yet fixed (such as whether a path traversal is exploitable); `secret`, holding
a secret such as a key or token; and `personal`, holding personal information
about someone, such as their health, an HR matter or a conflict between
people.** The filters still run, and the agent may still ask. Since the picker
hook matches a question's exact text against its latest verdict, the script
records a verdict for it, but only the text's hash, the verdict, the time and
the category. No text, context or answer is recorded, and no log or miss file
is written. Such a question is searched only on the machine, never on
GitHub's issues, so its text never reaches GitHub's search; the first call's
output says those sources weren't searched. A vulnerability's answer goes to
the fix and to the repository's private security advisory, its lasting
record.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### Categorized questions stay out of posts

**A categorized question is asked only through the picker, or, for a
vulnerability, in the repository's private security advisory, and the post
hook blocks a post holding one.** Under filter 2, it is deferred only into
the agent's report to the person in the session, or, for a vulnerability,
into the advisory; it is never listed in a post or filed as an issue.

#### The secret scan is only a backstop

**The script scans every log file and miss file it writes, and every question
in a post, for the credential patterns, and refuses on a match.** The patterns
are a closed list of known token shapes, in the spec's requirement *The
credential patterns are a closed list of token shapes*. It includes Anthropic
API keys (`sk-ant-`), GitHub's user-to-server and refresh tokens (`ghu_`,
`ghr_`), and the two credentials this change puts within the session model's
reach. Linear's API keys and OAuth tokens (`lin_api_`, `lin_oauth_`) are one:
the discussion's model runs with the person's tools and can read their
Linear key from the keychain. A Discord relay's bot token, three base64
parts separated by dots, is the other. That pattern also matches a JSON Web
Token, on purpose: a JWT in a post or a log file is usually a credential.

The scan catches known shapes only: a `DB_PASSWORD=…` passes it. So the agent
never puts a credential into a question, an answer or a verdict field, and a
question that needs one gets the `secret` category.

**Why:** the reasoning is in *Where the logs live*.

#### Weaknesses stay out of public text until disclosure

**Until a weakness's security advisory is published, nothing the agent writes
where people outside the advisory can read it describes the weakness or how to
exploit it.** The rule covers text, such as commit messages, pull request
text, comments and code comments; the fix's code may land publicly. It covers
any weakness under an unpublished advisory, whether or not the agent asked a
`vulnerability` question about it, such as one the bug-hunter skill finds. In
a private repository, collaborators who cannot read the advisory can still
read every branch, so its branches count as public too. A weakness with no
advisory, or whose advisory's state the agent can't read, counts as
unpublished. A fix made after publication is described normally.

A fix's regression test, such as bug-hunter's test that fails before the fix,
is a working exploit, so it lands only in the advisory's private fork, or
publicly after publication. Task 0.13 measures whether GitHub can merge the
fork's pull request before the advisory is published. Until it shows that
the merge waits for publication, the test goes in the fork only when the
advisory's publisher has said the pull request merges at the moment of
publication; without that word, it waits for publication.

The fork's commit messages also depend on task 0.13:

- **Before task 0.13 is measured:** they follow the public-text rule
  whatever the advisory's publisher has said, and the full description goes
  in the advisory's text.
- **If the merge waits for publication:** the fork is as private as the
  advisory until publication, so a fork commit is described normally.
- **If the merge can come first:** a fork commit is described normally only
  if the advisory's publisher told the agent, before it wrote the commit,
  that the pull request merges at the moment of publication; otherwise the
  public-text rule applies.

**Why:**
- The risk is describing the weakness, in any words, so whether the text
  states a question or its answer is the wrong test.
- The risk exists only while the fix is public and the advisory is not.
  GitHub's private advisories come with a temporary private fork, whose
  commits become public with the advisory, so a fix made there is not public
  before the advisory is. That holds only if the fork's pull request can't
  merge first, which task 0.13 measures.
- A blanket rule would leave a fix's commit message useless even after
  disclosure. That breaks rule 14 in the prose skill's `rules.md`: a commit
  message's body says why.
- A fork pull request merged before publication would put the regression test,
  a working exploit, on a public branch early.

*Rejected:* keeping a vulnerability question and its answer out of a fix's
commit messages, pull request text and comments: the weakness can be described
in other words, and the rule would leave the commit message useless after
disclosure.

### Which answers count, and citations

#### Only an answer with authority stops a question

**Filter 1 stops a question only with an answer that has authority; every
other hit is shown to the agent as input, labelled with why it is not an
answer.** An answer with authority is a decision document in the repository
the question concerns, an issue's decision block whose author has write
access, a logged answer from a person with write access, or an `active` lore
entry in the question's scope (*Scope hides an entry; status only labels
it*). `provisional` and `deprecated` entries are input. The entries below
set each kind's conditions; the spec's requirement *Only an answer with
authority stops a question* holds the full list. A login outside GitHub's
login syntax is never passed to a GitHub API call, so an answer whose author
has one is input.

#### An issue's decision block

**An issue's decision block is the start of the issue's body before its first
heading, or its first section whose heading starts with "Decision", stating
what is decided. It counts as an answer only when the issue's author has write
access.**

#### Write access for an organization's question

**For an organization's or project's question, write access to what it
concerns means write access to the team's lore repository,** as the spec's
Purpose defines it.

#### A decision record counts only when accepted

**A decision record that carries a status, such as a MADR, counts as an answer
only when its status is `accepted`.** A record with any other status is shown
as input. This holds wherever filter 1 reads decision records, the lore
repository's included, at the path *Filter 1 searches igor's scribe's records
where #202 puts them* gives.

#### A decision on the current work's branch answers that work

**A decision document on the current work's own branch answers a question
within that same work, shown labelled as this change's, not yet merged.** It
counts only when the branch is in the repository itself, not a fork, and the
current work's pull request author has write access to the repository. With no
pull request, the person running the session must have that access. No
signature is required. Anywhere else, such as for a question about another
repository, the document is input. The same conditions apply to an `agent` log
entry on that branch.

**Why:** without them, an outside contributor could commit a decision that
stops the agent's questions. Pushing a branch to the repository itself already
needs write access; a fork's branch does not.

#### A logged decision counts only when merged and its author has access

**A log file with `authority: decision` counts as an answer only when it is on
the default branch of its repository, or on a lore repository's `questions`
branch with a proven writer (*A questions-branch decision needs a proven
writer*), and its `answered_by` has write access to what the logged question
concerns when filter 1 reads it.** Otherwise it is input.

**Why:** `authority` is a field anyone can write, so the file alone proves
nothing.

#### An agent's choice counts only in the work it belongs to

**A log file with `authority: agent` counts on the default branch, and on the
current work's own branch for a question within that work, under the
conditions for a decision document there.** The file is written only in the
repository holding the current work, or pushed to the team's lore
repository's `questions` branch, which needs no pull request; it is never
sent to another repository by pull request. Where neither fits, it goes in
the agent's report. In the repository, filter 1 shows it labelled as the
agent's choice, which a person can overrule. On a `questions` branch it is
always input, pushed so later agents see the context; it never stops a
question. A person's later answer there is a new file, since no file there
changes once pushed.

#### An answer without authority stays in its log file

**An `authority: input` answer goes only in the question's log file, never
in a decision document,** since on the current work's branch a decision
document counts as an answer and the agent's own write would turn input into
a decision (*Where the logs live*).

#### An agent logs `decision` only for an answer it can prove

**The agent writes `authority: decision` only for an answer the person running
the session gave in that session, through the picker or in their own message,
or for an answer whose GitHub comment or review it links.** A session answer
is `decision` only when the person's configured login has write access to what
the question concerns; otherwise it is logged as `input`. A signature on a
commit made in the person's session proves only an answer the person gave in
that session. An answer the agent read anywhere else, such as in a file, an
issue, or a chat or tracker message, is `input` unless its comment link proves
it. The agent never writes `decision` for its own filter-3 or filter-4 choice;
that is `agent`.

#### No file on a questions branch changes once pushed

**A file on a lore repository's `questions` branch is never changed once
pushed, and a file that a commit after its adding commit changed is input.**
A later answer is a new file holding the question and the answer, proven on
its own adding commit, so that proof covers everything the file says
(*Where the logs live*).

#### A questions-branch decision needs a proven writer

**A `decision` file on a lore `questions` branch counts only when its writer
is proven on the commit that added it, in one of two ways; otherwise it is
input.** In both, `answered_by` also needs the write access every `decision`
file needs.

1. **Comment link:** the file links the github.com comment or review with
   the answer, on the repository its `repository` key names or on the lore
   repository, and GitHub names that comment's author as `answered_by`, or
   the comment is their relayed answer (*Only a listed relay App speaks for
   a person on GitHub*). The comment's reduced text must equal the recorded
   answer, so a bare "LGTM" proves nothing.
2. **Signature:** GitHub verifies a signature on the adding commit for
   `answered_by`'s account. That needs a one-time commit-signing setup on
   the person's machine; the agent commits from their session, so they never
   sign an answer by hand.

In a project set up for a GitHub App, the github-app skill commits as the bot,
unsigned, so there an agent's questions-branch `decision` needs the
comment-link proof. The answer session's answer files are the exception: it
commits them as the person, signed (*Setup checks questions-branch commits
are the person's*).

**Why:** anyone who can push can write any `answered_by`, and GitHub takes a
commit's author login from the author email, which the committer sets
(*Where the logs live*).

*Rejected:* matching the commit's author login to `answered_by`: anyone with
push access can forge it.
*Rejected:* treating every `questions`-branch file as input: the branch could
then never settle a question.

#### A signature GitHub may have made counts for no one

**A reader that can't tell whether GitHub made a signature counts no signature
at all, the person's own included.** GitHub signs a commit it makes itself,
such as one from its web editor or its contents API. If GitHub verified such
a commit for an account that did not make it, anyone with push access could
make a commit that proves another person's answer or relay file, so the spec
counts a signature GitHub made only once task 0.22 shows that never happens.
Task 0.22 also records how a reader tells a signature GitHub made from the
person's own.

#### A logged answer is the person's own words

**A person's answer is recorded word for word, never as an agent's
paraphrase.** An answer from a comment is the whole comment, however many
sentences, even one quoting the question. That holds for every writer: the
skill's script, the answer session and an Igor. The answer text a worker or
agent passes with a link only identifies which comment holds the answer. A
picker answer is recorded as the option chosen or the text typed; an answer
typed in the person's own message in the session, word for word too. Only an
agent's own filter-3 or filter-4 choice is in the agent's words. Words
holding context more private than what the question concerns are not
recorded at all (*Records are written at the question's privacy*). igor's
PR #216 records the writer side as its decisions 67 and 70.

Frontmatter `authority` decides whether a log file is answered, and nothing in
its body does, so a `## Answer` line inside a question's text changes nothing.

**Why:** readers confirm a comment-linked answer by comparing texts (*A
linked comment holds the answer only when the texts are equal*), so one rule
binds writers and readers alike.

#### A log file's answer is written as quote lines

**A log file's answer is written as quote lines, `> ` and the answer's line,
or `>` alone for a blank one; a reader takes as the answer the longest run of
quote lines ending the body, after a `## Answer` line.** A rephrasing's two
one-line sections sit just before `## Answer`, and the question is
everything above them.

**Why:** every answer line starts with `>`, so a whole comment fits, even one
holding a `## Answer` line of its own.

*Rejected:* joining the comment onto one line: it breaks the equality test
between a comment and its recorded answer for a comment with list items.
*Rejected:* a frontmatter key counting the answer's lines: the quote marks
make it needless.

#### The `log` command reads its inputs and the linked comments itself

**The `log` command takes its inputs in a file with mode 0600 in a private
directory, never as arguments, and reads an `answer_link`'s comment itself,
with the person's credentials, recording its text whatever answer the agent
passed.** When it cannot read the comment, it writes nothing and says why. In
Igor-worker mode it reads no comment, so it writes no answer, and the Igor
writes it from the comment's text (*A worker logs no answer*). The command
does not check who passed an `answer_link` or an `asked_in`: who passed a
link proves nothing about who wrote the answer, and any proof of the writer
comes from the linked comment or the commit's signature. The script writes
every log and miss file through this command.

**Why:** a question's text and its answer passed as arguments are readable by
every user of a shared host.

#### A linked comment holds the answer only when the texts are equal

**A reader confirms a logged answer against its linked comment only when the
comment's text and the recorded answer are equal once both are reduced.** The
reduction drops list markers and inline markup, joins whitespace, and ignores
a leading `User says: ` and a trailing `Re: <URL>` line. No model judges it.
The spec's *A linked comment holds the answer only when the reduced texts
are equal* is the one statement of the rule and the full reduction; igor's
search applies it too (igor PR #216's decision 72).

*Rejected:* counting a comment that contains the answer: it let "merge it."
match "Do not merge it.".

#### An answer typed on another surface counts only through a decision document

**An answer typed directly on another surface, such as Discord, Slack or
Linear, is input until a decision document that filter 1 counts records
it.** That may be an `accepted` decision record from igor's scribe, the
Igor role that writes a discussion's decisions down (igor issue #201, igor
PR #202), or any other decision document recording the answer on the
default branch of the question's repository, whoever writes it. The answer
itself never counts, neither as a logged `decision` nor through a link to
the message: a linked answer is only a github.com comment or review. An
answer the person typed in the answer session and the session relayed to
such a surface is not typed there (*Questions-branch answers relayed on
Linear or Discord*).

**Why:** only GitHub tells a reader who wrote a comment (*Where the logs
live*).

#### igor's search applies these checks

**Before labelling a questions-branch file an answer, igor's `lore-search`
applies the authority checks stated once in the spec's *Only an answer with
authority stops a question*.** It shows the file as input, labelled
unconfirmed, whenever a check can't run or fails. igor PR #216 records
igor's side as its decision 34.

#### Citations go to the lore repository's questions branch

**When filter 1 stops a question with a lore entry, the agent pushes a
citation-only file to that lore repository's `questions` branch,** where
igor's review, which prunes and promotes lore entries, counts each entry's
citations in one place beside its fire count. A stopped question is not
asked, so it gets no log file, and its citation is its only record. No log
file names a lore entry by its id: a log file is only for a question someone
answered, and where that answer is recorded is never a lore entry. Who
pushes citations during an Igor's run is in *igor PR #216 holds every rule
for a run's citations*.

**Why:** one place to count, with no privacy risk.

*Rejected:* a `cites` field in the question's log file: a question that filter
1 stops gets no log file.
*Rejected:* counting raw search hits instead of citations: no reason is
recorded.

#### One citation format, defined here

**This change defines the one citation-file format, in the spec's *A
citation file has one format*, and igor PR #216 points to it instead of
stating its own,** since the inquisitor and an Igor both write citation
files and igor's review reads them all.

#### A citation holds nothing about the question

**A citation file holds the cited entry's id and the date, and, only when an
Igor pushes it from a run, the run's id; it holds nothing about the
question.** So a private question gets a citation too. A question with a
category sends none (*Where the logs live* says why), and none goes to a
lore repository more visible than the question's repository. The run's id
is opaque; the Igor records it on its `igor-state` branch, in the run's row
of its execution ledger, not with the transcript, as igor PR #216 says.
igor's review shows each citation's run and item (igor PR #216's decision
10).

**Why:** igor's review counts citations per entry and needs nothing about the
question.

*Rejected:* a hash of the question in the citation, for the same reason.

#### Questions-branch commits are machine records

**Every commit the inquisitor's script makes to a lore `questions` branch is a
machine record, with the message `inquisitor: log <file>` and no prose or
bug-hunter trailer.** That branch is never checked out, so those skills'
checks never see these commits. At archive, prose's and bug-hunter's
`DECISIONS.md` files say so. igor PR #153, igor's signed-publishing change,
should exempt an Igor's citation commits from the trailers it requires on an
Igor's commits; that is #153's to settle.

#### A citation's commit names no person

**A citation's commit has the author and committer `inquisitor <noreply>`, a
date reduced to the day, and no signature,** so it says nothing about who
asked. The script commits with `git -c commit.gpgsign=false`, so a person's
signing setup for the writer proof never signs a citation with their key.

**Accepted:** GitHub's events API still records each push's pusher and time,
visible to anyone who can see the lore repository. That repository is never
more visible than the question's, since no citation goes to a more visible
one.

### Lore and misses

#### Lore repositories are configured as local clones

**The inquisitor's configuration, `~/.config/shared-skills/inquisitor.json`,
lists the lore repositories as local clones, each naming the GitHub owners, the
single repositories (`owner/repo`), or both, that it serves.** Several lore
repositories may serve one owner. The spec's Purpose holds the key names
(`lore`, `path`, `owners`, `repos`), what a lore repository serves and how a
project is known by its repositories; *Configuration* gives an example file.

*Rejected:* refusing two lore repositories that list the same owner: they can
serve it for different projects.

#### What a lore repository means here

**This change's *lore repository* is always the one holding the lore entries,
which igor PR #216 calls the *destination repository* (#216's decision 66).**
Under igor PR #208 an Igor's configuration lives in one repository, whose
`destination` may name another holding the lore entries; that other one is
this change's lore repository, and when they are one repository it is the
lore repository in both senses. Relay files and the questions branch live
beside the lore entries, so the inquisitor reads both there. Every use of
*lore repository* in this change means the repository holding the entries.
igor's specs use the same words for a different repository, the one holding
the Igor's configuration, as #208 names it. The inquisitor spec's Purpose
notes the difference where it defines the term.

#### Which lore repository is the team's

**A question about an organization or project goes to the lore repository that
serves the project it concerns. When more than one serves it, the most
specific match wins (a named repository beats an owner), then the first listed
in the configuration, and the agent's report says which it chose.** Spec:
the Purpose's *the team's lore repository*, and *The team's lore repository is
the most specific one that serves*.

#### Filter 1 searches lore in every session

**Filter 1 searches the lore entries, the markdown files with `conditions`,
and the questions branch of every configured lore repository that serves the
repository the question concerns.** An agent in no git repository searches
every configured lore repository, filtered by scope. During an Igor's run
igor's command runs the search (*Filter 1 in an Igor's run searches through
`igor lore-search`*). Spec: *Filter 1 searches every place an answer is
recorded* (sources), *Filter 1 matches terms as plain text and caps its hits*
(matching, ranking, cap).

**Why:** the search is how lessons reach plain Claude Code sessions, which no
Igor injects lore into.

#### Lore search is as fresh as the last fetch

**Filter 1 reads each lore clone's remote-tracking default branch as the clone
last fetched it, and fetches only the `questions` branch.** The search reports
when a fetch last updated the default branch, so the agent can tell how
fresh the lore it searched is (*Configuration* says how).

**Accepted:** an entry merged since the person's last fetch is not found.

#### Scope hides an entry; status only labels it

**Scope is a hard filter: filter 1 never shows, counts or mentions a lore
entry outside the question's scope, even as input. Status is a label: an
in-scope entry that is not `active` shows as labelled input and never as an
answer** (*Only an answer with authority stops a question*).

- **Inside an Igor**, the scope is the running role's, as igor's
  `scopeMatches` gives it: `global`, `role:<the running role>`, and `project:`
  matching any repository the role works.
- **Outside an Igor**, the scope is `global` and `project:<the short name of
  the question's repository>`.

igor PR #216 decides the same on igor's side.

**Why:** igor treats scope as visibility, so an out-of-scope entry is one the
asker may not see. A search is not injection: the agent asks for its results.
So showing labelled `provisional` and `deprecated` entries keeps igor's
promise that no unreviewed lesson is injected into a worker before it merges.

#### A project scope matches the repository's short name

**A lore entry scoped `project:<name>` matches a question when `<name>` is the
short name, the part after the `/`, of the repository the question
concerns.** That is igor's rule (`scopeMatches` in igor's `src/firing.ts`).
Spec: *Filter 1 hides every lore entry outside the question's scope*.

**Accepted:** a project whose repositories have other names needs a mapping
file in the lore repository, read by igor and the inquisitor alike, which
this change does not build.

#### Filter 1 searches igor's scribe's records where #202 puts them

**Filter 1 searches the decision records of igor's scribe, the Igor role that
writes a discussion's decisions down, in the repository the question concerns
and in the lore repository, at the path igor PR #202 sets.** *Open Questions*
tracks that path.

**Why:** a rule that depends on igor is specified in its end state.

*Rejected:* a fixed `docs/decisions/` until #202 settles the path: an interim
design for an igor dependency while igor has no users.

#### A general answer is proposed as a provisional lore entry

**Where a person's answer, or a lesson learned from a person, holds beyond the
repository the question concerns, and the agent judges it important enough for
agents to be given as lore, the agent opens a pull request adding it as a
`provisional` entry to the team's lore repository, without asking first, and
reports the link.** The script refuses one to a lore repository more visible
than what the answer concerns (*Nothing goes somewhere more visible than its
source*). With no configured lore repository serving the question's
repository, the agent tells the person the lesson instead. Spec: *An answer
that generalizes is proposed as lore*, *A proposed lore entry's path, fields
and id follow igor's rules*, *A lore pull request goes to no lore repository
more visible than its source*.

**Why:** a pull request is itself a proposal, and closing it is cheap.

#### A proposed entry's id follows igor's id rules

**A proposed lore entry's id passes igor's id rule, and is never one an entry
or a rejection in that lore repository already holds.** The rule is igor's
lore-store requirement *Ids are derived from the claim and then immutable*: a
kebab-case slug matching `^[a-z0-9][a-z0-9-]*$` (`ID_PATTERN` in igor's
`src/entry.ts`). The script refuses any other id. An id an entry holds means
another id; one a rejection holds means no proposal.

**During an Igor's run, an id reported only as "id taken" stops the entry:**
the agent does not propose it, its report says so, and a person can propose
it outside a run. igor's id check covers every entry and rejection but,
because scope is visibility, reports a collision outside the run's scope only
as "id taken". igor PR #216 has the same rule for its own id gate.

**Why:** "id taken" does not say whether an entry holds the id, so that
another would do, or a rejection, which forbids the entry.

#### A miss is logged against the filter that should have stopped it

**Whenever a person says a question did not need asking, "that was obvious"
being one way to say it, the agent logs a miss against the filter that should
have caught the question.** Misses change the skill only through lessons sent
by pull request or memory edit, never automatically. Spec: *A question that
should not have been asked is logged as a miss*.

#### Lessons from misses are drafted on request and land by scope

**The agent drafts lessons from the misses only when a person asks to review
them, and sends each lesson by its scope:**

- **holds for anyone using the skill:** a pull request to shared-skills
  changing the skill;
- **holds for one team or organization:** a pull request to that team's lore
  repository;
- **holds for one person:** that person's own memory or `CLAUDE.md`.

A lesson for shared-skills is written in general terms, quoting no logged
question or miss. Spec: *Lessons from misses land by their scope*, which also
refuses a team lesson to a lore repository more visible than a miss file it
draws on.

**Why:** question and miss logs can hold private content, so they stay with
the repositories they concern and shared-skills gets only the generalized
lesson.

*Rejected:* the script refusing a lesson that quotes a logged question: a
lesson in general terms never does.

### Igor workers and Igor runs

#### What an Igor's run covers

**During an Igor's run, the repository a question concerns is the repository
of the run's item, never one the worker names.** For a question with a
category, the run is the whole execution on the item, not one worker's part
(igor PR #216's decision 22). Spec: *The repository a question concerns
defaults to the current work's*, and the Purpose's *during an Igor's run*.

#### The script tells an Igor's run by `IGOR_RUN`

**The script knows it is in an Igor's run only from the environment variable
`IGOR_RUN`, and its output says so whenever it acts on the variable.** igor
sets it, holding no secret, to `worker` in a worker's environment and to
`igor` in an inquisitor run the Igor starts itself (igor PR #216 at ba154a0).
The script matches the exact name, since igor also sets `IGOR_RUN_TOKEN`, a
seat's token, and the exact value, so any other value marks no run.

Either value puts the script in Igor-worker mode. Despite its name, that
mode is how the script runs in any Igor's run, including one the Igor
starts itself with no worker. In it, no lore clone is read, nothing is
pushed to a lore repository, citations included, and the files are left for the
Igor, which sets `asked_from` on them (igor PR #216's *An Igor publishes the
questions-branch files its worker reports*). Only `worker` limits filter 1's
other sources to the worker's working tree. A plain headless session such as
`claude -p` has no such variable and searches lore as usual. Spec: *The
script tells an Igor's run by IGOR_RUN*.

**Why:** a repository can set the variable in a person's session, through
committed Claude Code settings or an `.envrc`. Lore would then go unsearched
and nothing would be logged to a lore repository, and without the message the
person could not tell why.

*Rejected:* treating every session with no person in it as possibly in an
Igor's run: a plain headless session would lose its lore search.

#### Task 0.12: an Igor worker cannot run the skill

**Measured on 2026-10-20: an Igor worker cannot run this skill, with a lore
clone and `inquisitor.json` in reach, on igor's main branch or once igor
PRs #174 and #175 land as specified.** So gate two builds everything except
Igor-worker mode, the spec's name for how the script runs in an Igor
worker. *What task 0.12 measured* gives the evidence.

**Why:** measuring it first let gate two build everything else at once; igor
PR #216's task 4.1 could have measured it only after this pull request landed.

#### An Igor worker asks only in its handback comment

**An Igor worker asks every question that survives the filters in its
handback comment, which its Igor posts (igor #211).** It opens no post and
calls no picker, even if task 0.14 finds a `gh` login in its reach. A headless
session posts its question only when it has no person and can post, such as a
scheduled agent (*How a session with no person asks*, which also covers one
that can neither post nor hand back).

**Why:** a worker holds no credential that can post: igor's requirement *The
worker is given an explicit environment holding no credential but its
seat's* gives it only its seat's token.

**When an Igor's run ends in its handback comment with no artifact, the worker
logs no question about the item's repository; the handback comment is the
question's record.** An artifact is anything the Igor publishes for the run,
such as a pull request. A later run on the item that publishes one logs the
question there, with its answer once given.

**Why:** the Igor publishes a log file about the item's repository only with
an artifact.

#### Filter 1 in an Igor's run searches through `igor lore-search`

**In an Igor worker, and in an inquisitor run the Igor starts itself with no
worker, filter 1 searches lore only through igor's read-only command `igor
lore-search`,** specified by igor PR #216 (its decisions 23 and 49). igor
searches its own lore checkout and `questions` branch with the role's scope,
labelling each hit as answer or input as filter 1 does. So in a run the
script needs no lore clone, `inquisitor.json` or `gh`, nor to know which lore
repository the Igor injects from. Spec: *In an Igor's run, filter 1 searches
through igor* (the input, a failed command), *An Igor worker's search covers
only its working tree beyond lore* (other sources).

**Why:** igor injects active in-scope entries only while they fit the
worker's token budget, so an entry holding a person's answer can be missing
from the worker's context.

This depends on igor PR
[#216](https://github.com/adamstallard/igor/pull/216), whose decisions igor
issue [#215](https://github.com/adamstallard/igor/issues/215) also holds.
igor PR #216 amends igor's lore-firing spec for Igor workers: lore still
reaches the
worker unbidden, the ban on offering a worker a search tool, which rested only
on a worker not needing one, is lifted, and a run's search applies firing's
scope rule and labels an in-scope non-`active` entry as not lore.

**During an Igor's run, the search covers only the lore repository the Igor
injects from,** as igor PR #216 also records. **Why:** the Igor checks a cited
entry, reported by id alone, against that lore repository; another one's
search could find an entry the Igor refuses, or one it takes for a different
entry with that id.

**`igor lore-search` and filter 1 search alike,** with plain text and no
embedding or model call: the question's terms against a lore entry's claim,
conditions and body, and against a question file's question. Both rank hits by
terms matched, show at most 20, and say when they left hits out (#216's
decision 52). **Why:** the same entries then rank alike inside and outside a
run.

#### Questions-branch files and `project:` entries in a run's search

**During an Igor's run, a question or miss file on a lore repository's
`questions` branch is in scope for every role whose Igor uses that lore
repository, whatever repository its `repository` key names.** igor's search
returns such a file only when the run's item repository is no more visible
than the file, judged by the more private of its `repository` and
`asked_from`; an unreadable visibility counts against it (#216's decisions 25,
27 and 42). A `project:X` lore entry is likewise neither shown nor fired when
the item's repository is more visible than X (#216's decisions 53 and 54).
The spec's scenario of a `project:` entry inside an Igor therefore sets the
item's repository no more visible than X; otherwise the entry would be
hidden and the scenario would test nothing. These rules are #216's; the
spec's *A run's lore
search keeps to the Igor's lore repository and scope* points to them.

**Why:** a worker could otherwise repost what it read about a private
repository into a more public item.

**During a run, a questions-branch file whose `repository` key names a
repository other than the item's always shows as input,** labelled
unconfirmed, whatever its proofs (#216's decision 44; spec: *In an Igor's
run, a file about another repository is input*). Scope decides whether the
file is returned; this rule, how it shows.

**Why:** proofs show who answered, not that the answer belongs to the item's
repository, so the file decides nothing until that is proven.

#### The Igor writes `asked_from` on every file it pushes

**The Igor adds the run's own item repository, as `owner/repo`, to every log
and miss file it pushes to a questions branch, as the key `asked_from`.** It
sets the key after its format check, and refuses a worker's file that already
has one (#216's decision 42). The skill's script writes `asked_from` only on
the miss an answer session logs for a questions-branch file, copying that
file's (*Misses the answer session logs*). A file is as private as the more
private of its `repository` and `asked_from`; an `asked_from` failing the
`owner/repo` check counts as a private repository, as #216 counts it, and
makes the file input. This change owns the file format, so the key is in its
closed list of keys and its readers judge visibility the same way. Spec: *A
log file and a miss file have one format*, *A log file's repository keys and
answer_link are checked before use*.

**Why:** a worker steered by its item could write a public `repository` on a
file about a private repository; `asked_from` still names the private one, so
the question cannot be laundered.

#### The flag a worker raises for a question with a category

**During an Igor's run, whenever a worker gives a question a category
(`vulnerability`, `secret` or `personal`), whatever its verdict, its report
carries the flag igor PR #216 defines.** The flag holds no question or answer,
only two lists:

- each category met in that worker run, at most once, as one of the three
  words and nothing else, including one met on a question that did not stop
  the worker, such as one decided under filter 4;
- a marking of those that belong to the question or questions the run stopped
  on.

The lists are unpaired: the flag never says which stopped question had which
category, and has no per-question format. A stopped question with no category
adds nothing. The Igor accepts a word only when it is exactly one of the
three.

Each worker run reports its own flag, including the model steps igor PR #153
runs after the worker (#216's decisions 60 and 64). The Igor writes the
category words only into its operator-only file on its host (#216's decision
89), never into the execution ledger, the state branch, a comment or a label.
How it stores the flag, several stopped questions included, is igor PR #216's
(its decisions 92, 97 and 100). Its task-execution requirement *Transcripts
and outcomes are captured to the state branch* has the Igor write no
transcript of the run, since a transcript would hold the question, and
applies the same rules when the Igor runs the skill itself. Spec: *A session
with no person in it holds back a question with a category* (the worker's
side).

*Rejected:* a word per question, which would tell the Igor how many questions
of each category stopped the run; and listing only the stopped questions'
categories in a fixed order, which Adam rejected without giving a reason.

#### A flagged run asks nothing and pushes nothing

**A flagged run is one igor counts as having met a sensitive question: its
worker reported the flag, or the run ended without the worker's completed
report, for any reason** (#216's decisions 19 and 38). A flagged run pushes
nothing to the `questions` branch, citations included.

**A flagged run asks nothing on the item, and its question stays on the Igor's
host.** The Igor posts its handoff, the comment handing the item back, in
place of the worker's handback comment; it posts no question, gets no
`igor:question` label, and reaches nothing in igor #211's inquisitor role
(#216's decisions 73 and 75). The question goes in an operator-only file on
the host, never pushed. The file holds the flag's categories, the text of
each stopped question with no category, and the paths of the execution's
session logs, which are moved beside it. The item stays held, and a reply
does not rerun it. The
operator can always release it with `igor release <tracker>/<repo>/<item>`,
and an attributable edit or label by someone with write access to the item's
repository releases it too (#216's decisions 79, 84 and 95). The file and the
release are igor PR #216's (its decisions 73, 75, 76, 79 to 85, 88, 89, 95,
97, 98, 100 and 101 at d3b7740); this change reads nothing from the file.

**No log file records the question that stopped a flagged run,** from that run
or any later run on the item, even one that publishes an artifact (spec: *No
log file records a flagged run's question*).

#### The Igor pushes the questions-branch files its worker reports

**An Igor worker pushes nothing to a lore repository, since it holds no
credential for one.** Each question file, miss file and `authority: agent`
file it would push to a `questions` branch goes in its report, and the Igor
pushes it with the run's citations, under igor PR #216's requirement *An Igor
publishes the questions-branch files its worker reports* (spec: *An Igor's
run reports the questions-branch files it would push*). #216 states these
rules for both changes:

- **Which files:** only a file holding no answer, one with `authority: agent`
  and `answered_by: agent`, or a miss file, and only at a path not already on
  the branch (#216's decision 21). The one other file pushed is a log file of
  a person's answer to a handback (*A person's answer to a handback*), so
  never, for instance, a worker's `authority: decision` file.
- **Credential check:** every file pushed for a worker passes igor PR #217's
  credential matcher, which matches known secrets' values such as the
  worker's seat token, besides this change's patterns (#216's decision 28).
- **Visibility:** the Igor reads the lore repository's visibility at every
  push (#216's decision 37).

#### A person's answer to a handback

**When a worker re-works an item after a person answered its handback, the
Igor pushes a log file recording the answer,** with an `answer_link` to the
person's comment, as a new file beside the unanswered one, since a
questions-branch file never changes once pushed. The worker's report holds
the file with the question and `answer_link` but no answer, and the worker
decides nothing about it. The Igor writes the answer from the comment's own
words (*A worker logs no answer*) and sets `authority` to `decision` when the
person has write access to what the question concerns, `input` otherwise
(the spec's *A logged decision needs write access to what its question
concerns* and *A questions-branch file's writer is proven by its comment or
its signature*).

**The Igor pushes such a file only when its question matches a question the
Igor posted in the handback comment that the person's comment answers.** The
match uses the Igor's own record of the questions it posted, never the
comment's current text: two questions match when equal after the reduction
this change applies before hashing (#216's decision 41).

**Why:** a worker steered by its item could otherwise pair a real comment with
another question, and anyone who can edit the comment could change its text.

#### A worker logs no answer

**An Igor worker writes no answer into any log file, whether on a questions
branch or in a repository's `.inquisitor/`; it writes only the question.**
Whatever later logs the answer reads the comment, records its own words and
sets `authority` by its checks. On a questions branch, the Igor logs it when
it pushes. In a repository's `.inquisitor/questions/`, an agent outside
Igor-worker mode logs it by running the skill's script there, since no
answer session writes there and the Igor does not edit the artifact. Spec:
*A worker logs no answer, and
its Igor writes it from the comment*; *A worker's repository question is
logged with the run's artifact*.

**Why:** a worker reads no comment, so any answer it wrote would be its own
paraphrase, and it could not check the writer's access to set `authority`.

*Rejected:* a worker writing the answer for the Igor or a person to rewrite.

#### An Igor reads relay files as of igor PR #208's applied commit

**An Igor reads relay files as of the last lore commit it applied under igor
PR #208, which fetches lore and applies only commits that pass igor's
startup checks (#216's decision 77).** The check of who last changed a relay
file
reads that commit too. Outside an Igor, relay files are read from the lore
clone's fetched default branch. Spec: *A relay file is read as last fetched,
or as igor last applied it*.

**Why:** #208 applies only commits that pass igor's startup checks, so a
refused commit's relay files never count, as no relay file counts whose last
change can't be shown to be its person's.

**When #208 has applied no commit, the relay check cannot run:** under `igor
run`, which never fetches, and for a lore repository #208 never fetches. The
Igor, unable to tell whether a `User says: ` comment came from a listed relay
App, pushes such an answer as `input`; a person's answer in their own comment
counts regardless (#216's decision 78).

#### A later run names the answered file from the Igor's record

**A later Igor run on an item, recording a person's answer to a handback
question, names a file in `answers` only when it knows that file exactly, from
the Igor's own record of the handback (igor PR #216's decision 59).**
Otherwise it writes no `answers`, and the earlier file stays shown until the
person answers it. The record holds only the 6-hex-digit suffix and the date
from the name of the log file the Igor pushed for the question, never question
text; the run finds the file by them, and names none when several match. It
never reads a file's name from the handback comment, which may show it for
people. Spec: *A later Igor run names the answered file only from the Igor's
record*.

**Why:** a comment's text can be changed by anyone who can edit it, and the
random 6-hex-digit suffix makes a name unique, so a second match can only be a
planted look-alike.

**Accepted:** the slug in a file's name carries some of the question's words;
the record holds none.

*Rejected:* naming the files a search found by their words; reading the file's
name from the handback comment's text; dropping the slug from file names.

#### igor PR #216 holds every rule for a run's citations

**During an Igor's run the agent pushes no citation itself; every rule for a
run's citations is igor PR #216's lore-firing requirement *An Igor publishes
the citations its worker reports*,** which this change points to rather than
restates: how a worker or an Igor-started run reports citations, and when the
Igor pushes which ones, and where. This change's own rules cover only a
session outside a run, plus the one citation-file format both use, with the
run's id in a citation an Igor pushes. Spec: *No worker or Igor-started run
pushes to a lore repository*, *A lore entry that stops a question gets a
citation file*, *A citation file has one format*.

In brief, #216 has the Igor push a run's citations only when the run
publishes, a handback comment counting, as bookkeeping outside the role's
`allow` list, and only citations of existing `active` entries in the run's
role's scope. It leaves the channel a worker reports them through, output or
outbox, to igor PR #175, which runs a worker as a separate Unix user.

**Why:** igor has a worker edit and its Igor publish, and a worker holds only
its seat's token.

#### igor's review count of citations

**igor's review count of an entry's citations is a lower bound, and the review
says so beside the count.** When every Igor push of its workers' citations
failed, the review shows "not checked" instead of a count, even if people's
sessions pushed some (#216's decision 32).

**Why:** a citation never goes to a lore repository more visible than the
question's, so some are always missing; and when every Igor push failed, a
count would show none for every entry only Igors cited.

#### igor-dependent rules state the end state

**A rule that depends on igor states its end state, with no clause for an igor
state before a change lands; what igor must provide is listed under *Open
Questions*.** A clause that also guards against misuse in the end state stays,
such as:
- a log file with no matching record of the handback writes no `answers`;
- an `igor lore-search` call that fails searches no lore;
- a handback-marked post is vetted like any other (*No exemption for an
  Igor's handback*).

So filter 1 searches the scribe's records where igor PR #202 puts them, and
`igor lore-search` is stated as what igor must provide.

**Why:** igor has no users yet, so this change specifies no interim design for
it.

#### Alignment with igor PR #216

**The spec states igor PR #216's rules where they touch this change, and
points to the rest,** such as the Igor's handling of a handback answer:
`authority`, `answered_by`, the relay files it reads and the answer it
records. #216's decisions 58 and 59, on fetching under `igor run` and on the
hashed record of handback questions, contradict nothing here. Its rules on
`project:` entries and the category flag are in *Questions-branch files and
`project:` entries in a run's search* and *The flag a worker raises for a
question with a category*.

### Answer-session configuration, setup and relay identities

#### The answer session and its relay identities

**The answer session is where a person does nothing but answer the questions
asked of them on GitHub, Linear and Discord, by people or by agents running
the inquisitor.** Questions reach it from the channels the person subscribes
to. Each answer is posted in the question's thread, starting `User says: `, by
that surface's relay identity, a bot posting for the person: a github-app,
linear-app or discord-bot identity. The interface is a Claude Code mod built
from the prototype build named in *The UI is built from prototype build
v0.1-33*.

#### The configuration is a section of `inquisitor.json`

**The answer session's configuration is the `answer_session` key of
`~/.config/shared-skills/inquisitor.json`.** For each surface it holds the
subscriptions (GitHub repositories or owners, Linear teams, Discord channels)
and a reference to the relay identity, and on Discord the person's Discord
user id. It holds no token: the relays' tokens stay with their skills, and the
person's Linear API key, which the answer session reads Linear with, is in the
system keychain. When `gh` does not confirm the configured login, GitHub is
off. Spec: *The answer session's configuration is a section of the
inquisitor's configuration*, *The person runs the session, and a relay
identity posts for them*. *Configuration* shows an example file.

#### Setup is part of the answer session

**Setup runs inside the answer session: in place of the queue when the
`answer_session` section is missing or incomplete, and again when the person
types `/answer setup`.** It offers channels, checks that each relay identity
can post, writes the JSON, which stays editable by hand, and installs the
`answer` command, never overwriting a file it did not write. How setup looks
is prototyped, not specified. Spec: *Setup opens on an incomplete
configuration and checks questions-branch commits*, *Setup checks each relay
identity before its channels are used*, *Setup proposes the person's relay
file and its notice workflow*, *Two commands open an answer session* (the
`answer` file, its marking comment line, a file left alone).

#### A failed relay check turns off only its channel

**A failed check of posting in one channel turns off that channel alone.** A
check of the relay identity itself, such as its skill's own check or, on
Discord, reading message content, covers its whole surface, so its failure
turns off every channel there. Setup shows each failure and its fix, and
saves the rest. A failed or unrun check runs again each time the answer
session opens; its channel stays off until one passes.

**Accepted:** where no check can read whether a relay identity may post in a
channel (task 0.20), a post the surface refuses turns that channel off until a
recheck passes, besides what every failed post gets: nothing posted, the
person told why, the answer kept (*An answer that cannot reach its thread is
kept pending*). In such a channel, the posting check counts as passed once
the relay identity's own check passes again (spec: *A pending answer whose
channel was
off returns to the queue*), though setup shows it as not checked, since
nothing checked it.

#### Setup checks questions-branch commits are the person's

**The answer session commits questions-branch answer files as the person, with
their git identity and signing, never a GitHub App's, even in a project set up
for an App.** Setup checks both the identity and that the signing key is one
GitHub verifies for the person's account, and warns with a fix when either
fails. Spec: *Setup opens on an incomplete configuration and checks
questions-branch commits*.

**Why:** an answer file with no `answer_link` counts only through its commit's
signature.

*Rejected:* treating a file a machine pushed as answered on that machine alone.
*Rejected:* committing as the App and warning that such answers do not count:
github-app commits as the bot, unsigned, so the person's answers would never
count.

#### Discord is in the first version, through discord-bot

**Discord is in the first version, through the `discord-bot` skill of
shared-skills PR #1, merged.** The Discord relay is a `discord-bot` identity.

**Why:** discord-bot gives each role a named bot identity with no service to
run.

#### On Discord one identity both reads and relays

**On Discord the relay identity both reads and posts, in the channels it has
been added to.** There is no separate reading identity and no `read` key.
Spec: *The answer session reads with the person's credentials, except on
Discord*.

**Why:** Discord's terms do not allow automating a user account, so Discord is
the one surface read with a bot.

*Rejected:* a second Discord identity, in a `read` key, reading as the person,
for that reason.

#### The Discord relay needs the Message Content intent

**The Discord relay must read message content, which needs Discord's
privileged Message Content intent.** discord-bot's setup (shared-skills PR #1,
commit 369ae16) has the person turn it on, and its `check` reports
`messageContent` as true, false or null from the bot's application flags
(f83b167). That report and setup's other checks alone decide whether Discord
is on. Relay posts keep discord-bot's turning of an `@name` into a pinging
mention (*Discord relay posts: no header, mentions that ping*), so no option
to turn that off is needed. Spec: *Setup checks each relay identity before its
channels are used* (which values pass).

**Why:** the relay reads messages that do not mention the bot, which needs the
intent.

#### Only the prefixes are reserved, not the identity

**A relay identity may be used for other work, but a post that starts with
`User says: ` or `User asks: ` is made only by the answer session, on the
person's confirmation.** Its automatic posts reserve `Recorded answer: ` and
`Inquisitor: ` the same way (*What the answer session posts by itself*). Spec:
*Four reserved prefixes mark the answer session's posts*.

*Rejected:* keeping a relay identity for the answer session alone: the prefix
marks a relay post, and nothing reads a relay identity's other posts.

#### Only a listed relay App speaks for a person on GitHub

**A GitHub comment starting `User says: ` counts as the person's own comment,
wherever filter 1 reads who wrote a comment, only when its author is an App
listed as that person's relay in their relay file on the default branch of
the team's lore repository.** One from any other App the person owns, an
Igor's included (*An Igor's App is never a relay App*), is input. This rule
lets the writer proof count an answer relayed on GitHub, and an Igor log a
relayed answer to its handback as `authority: decision`. Until task 0.21
shows that GitHub reports which App wrote a comment, every `User says: `
comment is input. Spec: *A relayed answer counts as its person's own
comment*, *A relay file names the bots that post for its person*, *A relay
App is one its person's counted relay file lists*.

**Why:** a relayed answer is trusted because only the answer session makes a
`User says: ` post, and only on the person's confirmation. Owning the App is
not enough: igor's code posts its worker's text unseen by any hook, so a
steered worker could start a comment `User says: ` and prove a
questions-branch `decision` file.

*Rejected:* counting such a comment from any App the person owns: their own
Igor App would let a steered worker forge their answer.
*Rejected:* treating every relayed answer as input: none could prove its
writer, and no Igor could log a relayed handback answer as a decision.

#### An Igor's App is never a relay App

**An Igor's App is never a relay App, even where a relay file lists it (igor
PR #216's decision 45), and a reader recognises one by the `igor-` prefix of
its slug.** igor requires that prefix: an Igor whose App's slug lacks it
refuses to start (#216's decision 62). So no relay-file entry with that prefix
counts. A person lists only an App that posts nothing a post hook can't see,
apart from the answer session's own posts, and uses a relay App for other work
only through tool calls a post hook sees. Spec: *A relay App is one its
person's counted relay file lists*, *A person changes their own relay file,
listing only Apps a post hook sees*.

*Rejected:* recognising an Igor's App from the lore repository's Igor
configuration: igor's role-config spec forbids a key naming an App identity,
and a lore repository with no Igor configuration would have no relay App.
*Rejected:* a `relays/_igor.yaml` listing the Igors' Apps: the slug prefix
igor enforces already identifies them.

#### The Igor names who answered through a relay App

**For a relay App's comment on a handback, the Igor sets `answered_by` as well
as `authority`: the person whose relay file lists that App.** igor PR #216
left this to this change. Spec: *A worker logs no answer, and its Igor writes
it from the comment*.

**Why:** the worker can't read relay files, so every relayed handback answer
would otherwise name the wrong person and be input.

#### One relay file per person

**A person's relays are listed in `relays/<github-login>.yaml` in the team's
lore repository, read from its default branch.** It holds the person's
`github` (App slugs), `linear` and `discord` lists; only `github` proves
anything. The person adds or changes it by their own pull request, which
setup proposes. Spec: *A relay file names the bots that post for its person*,
*A missing or malformed relay file lists no relay*.

**Why:** it follows igor's seat files (igor issue #148, igor PR #171), where
each lender's own pull request adds `seats/<id>.yaml`: a path names whose file
it is. *What the answer session posts, and what it logs* gives the rest,
including the choice of YAML.

*Rejected:* one shared `relays.yaml` keyed by login: a key does not name whose
it is.

#### A malformed relay file lists no relay

**A relay file that is missing or does not parse lists no relay, and a value
that is not a list of strings lists none for that key.** A file whose name is
not a GitHub login lists none, since a file is one person's.

#### Who last changed a relay file ties it to its person

**No review is required: a reader counts `relays/<login>.yaml` only when its
last change came from that login.** The last change is the newest
default-branch commit changing the file. It is the person's when they
authored the merged pull request GitHub associates with it, or it carries a
signature GitHub verifies for their account. Otherwise, or when a check can't
run, such as offline, the file lists no relay. Setup proposes the file again
when its last change was not the person's, even if it lists every relay. Task
0.22 measures what the check needs, such as GitHub giving a commit's pull
request. Inside an Igor the commit read is #208's (*An Igor reads relay files
as of igor PR #208's applied commit*). Spec: *A reader counts a relay file
only when its person made its last change* (which commit, git's history
walk); *A relay file names the bots that post for its person* (login compared
ignoring case).

**Why:** anyone who can push to the lore repository can then stop a person's
relayed answers counting, but not make another App speak for them.

**Accepted:** someone who can push to the person's open pull request, such as
a maintainer the person's fork lets edit it, can change the file under it,
and the change counts once merged; the relay notice (*A notice workflow
mentions a relay file's person*) @-mentions the person for that push, so they
can close it.

**Accepted:** anyone who can rewrite the default branch can restore an older
file of the person's own, listing an App the person had removed. So removing a
compromised App from the file does not stop it speaking for the person; the
README says to uninstall the App or revoke its key.

*Rejected:* counting the pull request only when all its commits are the
person's: GitHub's API can't show a pushed commit's pusher.
*Rejected:* requiring review through branch protection, with setup warning
where none is required: ownership ties the file to its person without it.

#### Setup's relay pull request

**Setup opens the relay pull request as a host command, with a fixed title and
body the script writes, so it needs no prose pass,** as the answer session's
automatic posts need none. When setup proposes the file again because someone
else last changed it, its first line is `# confirmed by <login> on <date>`.
Spec: *Setup proposes the person's relay file and its notice workflow*.

**Why:** the dated line makes the pull request change the file even when the
relays are the same, so the other person's commit stops being its last change.

#### A notice workflow mentions a relay file's person

**The inquisitor ships a workflow, `relay-notice.yml`, that @-mentions a
person on a pull request that changes their relay file, and setup proposes
it.** It is igor's seat-notice workflow (igor PR #171) applied to
`relays/<login>.yaml`, naming the person by the path. It mentions a login only
if the base branch holds that login's file or that person opened the pull
request, and never for an event the person caused on their own pull request.
It runs on `pull_request_target` alone, on GitHub-hosted runners, with no
`paths` filter, and reads only the names of the paths the head changes. Where
the default branch lacks the workflow, setup opens a separate pull request
adding it; if GitHub refuses, such as for a `gh` login without the `workflow`
scope, setup says so and carries on. Spec: *A pull request that changes a
relay file mentions its person*, *The relay notice reads only the names of the
paths a pull request changes*.

**Why:** the notice warns the person when their file is about to stop
counting, and when someone else pushes to their own open pull request.
Mentioning only the base branch's file owner or the opener stops a pull
request making the workflow mention anyone it likes, which is also why igor's
workflow reads the owner from the default branch. No reader depends on the
notice, so setup carries on after a refusal.

*Rejected:* igor's seat-notice workflow covering relay files too: simpler in
the end, but the notice would wait for igor's release and a change to another
repository's spec.

#### A relay notice is shown as a notice

**A relay-notice comment starts with a fixed first line, and the answer
session shows such a comment from `github-actions[bot]` as a notice, never as
a question,** so it is never answered by itself or logged as a miss. Spec:
*A pull request that changes a relay file mentions its person*, *A
relay-notice comment is shown as a notice*.

#### github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity

**github-app's `token`, `run`, `credential get` and `wire` commands are to
refuse an identity marked as a relay, so only the answer session's own posting
command can post with it.** This change asks github-app for that change and
ships without it, accepting the cost below.

**Why:** a relay App speaks for its person only while nothing posts through it
unseen. `token` prints its token to any agent on the machine; `run`,
`credential get` and `wire` hand it to a command, git or a clone's
configuration.

**Accepted:** like the post hook, the refusals guard against accidents, not
against an agent set on forging a relayed answer. Until github-app's change
ships, any agent on the person's machine can print a relay App's token and
post `User says: ` with a plain HTTP call no post hook sees; the README says
so (task 5.2).

### Running the answer session

#### Four sources of a question asked of the person

**A question asked of the person is one of four things:** a mention of them in
a subscribed channel, agents running the inquisitor included; a mention of
their relay identity, or a reply to a relay post; on GitHub, a pull request
requesting their review or an issue assigned to them, and on Linear, an issue
assigned to them; or a log file on a lore repository's questions branch whose
question tags them. Spec: *A question asked of the person comes from one of
four sources*, and for rules other entries decide:
- whom a bot's question reaches: *Whom a message reaches is set by its
  mentions*, *A mention names a user outside code, quotes and links*;
- Igor handbacks: *A handback is an igor- App's comment holding igor's
  marker*, *Only an item's newest handback is shown*, *An item's newest
  handback is open until a relay post names it*, *A handback that mentions no
  one goes to the item's assignee*;
- log files following a thread message: *A log file follows the thread
  message its asked_in links*, *A log file with no followed link is judged on
  its own*, *An Igor's log file follows its own handback comment*;
- non-questions: *Messages judged clearly not questions are ignored*.

#### The answer session polls, only while it is open

**The answer session reads its channels by polling, about every 60 seconds,
and only while an answer session is open; it uses no webhooks.** It polls once
on opening to catch up. Until task 0.15 shows GitHub's notifications endpoint
reports every GitHub message of the first three sources, it also reads each
subscribed repository's comments. Questions-branch log files never appear in
notifications, so it fetches those branches at each poll. A channel with no
saved poll position yet is read from the last 14 days only. Spec: *The
answer session polls only while it is open* (that first read, the branch
fetches), *The answer session polls GitHub's notifications and comments*
(conditional requests, `X-Poll-Interval`, the comment reads).

**Why:** a webhook needs a public HTTPS server and Discord's push a permanent
connection, each a service to run. GitHub documents that the notifications
endpoint's conditional requests do not count against the rate limit, and it
sets the interval between polls; task 0.15 measures both. The comment reads
catch a mention of the relay in a thread the person never subscribed to.

**Accepted:** reading the comments costs a rate-limited request per repository
per poll, and an owner subscription one per repository of that owner.

#### Reading uses the person's own credentials

**The answer session reads with the person's own `gh` login and Linear key;
a relay identity only posts.** Discord is the exception (*On Discord one
identity both reads and relays*). Spec: *The answer session reads with the
person's credentials, except on Discord*.

**Why:** a relay's token then needs only the right to post, and nothing the
person reads is read under a bot's name.

#### Local state is per machine, in the state folder

**The answer session keeps its working state in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`, per
machine,** including the question on screen, so `answer` and `/answer` reopen
on it even after Claude Code restarts; the spec's requirement of the same
name lists the rest. A discussion record is deleted once its question is
answered, or answered or handled for the person, or closed. On that
condition, Adam ruled, the state folder is not the personal question log that
*Every asked question is logged with what it concerns* rules out.

**Why:** it is working state, not a record: the thread and the asker's log
file stay the records.

**Accepted:** a question set aside on one machine is new on another, costing
only a second look.

#### Which cross-machine cases are accepted

**A case between two machines of the same person whose worst outcome is a
question shown twice or asked again is accepted, and gets no rule of its own.**
A case that could record a wrong answer, close a question wrongly, leak
private content or lose an answer is still raised for a decision.

#### One answer session runs on each machine

**One answer session runs per machine, under a lock in the state folder that
its holder refreshes, so the lock of a crashed holder goes stale.** While
another session holds a fresh lock, a second `/answer` opens nothing: it names
the holder and whether it is a Claude Code background session, says how to
reach it, and offers to take over. The spec's requirement of the same name
holds the lock's contents, refresh and staleness times, the atomic write, and
the check before each poll and post. No TLA+ model is written.

**Why:** one person uses the answer session, and the lock makes one session
the sole writer of its machine's state. *Local state, one writer per machine*
gives the reasoning, including for writing no model.

#### Two commands open the answer session

**The answer session opens with `/answer` in any session, or with the `answer`
terminal command that setup installs.** `answer` starts a Claude Code session
named `Answers`, with `/answer` as its first prompt, fullscreen in its
terminal, where clicks work. No environment variable opens the answer
session. Spec: *Two commands open an answer session*.

**Why:** neither way in needs an environment variable, and a session an app
starts from its session list, with no terminal, cannot set one. Fullscreen is
the layout the answer session is designed for.

**Accepted:** the answer session also works on Claude Code's main screen, but
nothing is designed or built for that screen alone.

#### A discussion runs in the session's own conversation

**A discussion of a question runs in the session's own conversation, with the
question attached to each message as context.** Before replying, the model
reads with its tools, the thread, code and specs among them; it posts and
changes nothing. Its reply may ask the person a question, which passes none of
the four filters and needs no vetting: the one exception to the rule that an
agent asks only through the picker. Spec: the requirement of the same name.

**Why:** the model reads before it replies, and a picker would hide the
answer session's screen from a person who opened the conversation to talk the
question through.

**Accepted:** the model runs with the person's tools, so it could reach the
keychain entry holding their Linear key; *The session's model* says why no
guard is added.

#### Claude drafts a reply only into the prompt box

**The answer session gives the model a tool, `propose_reply`, which puts its
draft reply in the prompt box and posts nothing.** The person edits it and
relays it as any answer, also when editing a relay post. `propose_reply`
refuses a subagent's call. When the person declines under filter 1, because
the inquisitor should have handled it, Claude's draft may fill in the URL of
the record that answers the question. That URL goes on the `Recorded in: `
line of the `Recorded answer: ` post (*What the answer session posts by
itself*). Spec: *Claude's draft goes to the prompt
box, never to a post*.

**Why:** the draft lands in the prompt box for the person to confirm, so
Claude may fill in the URL.

#### The UI is built from prototype build v0.1-33

**The mod is built from prototype build v0.1-33 alone, which Adam approved by
use on 2026-10-24,** tagged `answer-session-ui-approved-v0.1-33` on
shared-skills (commit fc3c35f; `ui-approved-v0.1-33` in Adam's prototype
repository). It descends from v0.1-30, the whole UI Adam approved by use on
2026-10-20, declining and the list of questions answered or handled for the
person included (tag `answer-session-ui-approved-v0.1-30`, commit c9c6eb5;
`ui-approved-v0.1-30`). v0.1-33's three commits add only:

- the thread's replies since the question;
- filter 1's recorded answer beside the question, for a questions-branch
  question as well as a thread's;
- corrected wording and placement of the notice for a stopped post, one held
  back because a reply arrived in the thread since the person last read it.

The replies and the recorded answer each appear in one fixed place on
screen, where the tagged build shows them; the mod offers no other layout
for them. The approval covers the whole build, including the asker
withdrawing their question in the thread (the prototype's twelfth sample
question) and the stopped post's notice, which the build's pre-tag notes
list as still to try. Both approvals the tasks ask for are done: task G.1,
Adam's approval of this build before gate one, and task 6.9, his approval of
the screens prototyped after the first approved build. The tag
`answer-session-ui-approved` (f964903)
lacks the declining screens and is not a base.

**Why:** v0.1-33 contains all of v0.1-30, so one base serves.

#### How the approved prototype meets the spec

**The mod keeps the approved prototype's screens, and the spec wins wherever
the two differ.** Task 6.1's rules (a) to (d) state the precedence:

- (a) The mod keeps the approved screens' layout and interaction: the band,
  the keys, the prompt-box flow and the declining screens. It may change them
  to wire real data, not restyle or reorganise them.
- (b) Wherever the prototype disagrees with the spec, the spec wins; task 6.1
  lists the known cases.
- (c) A screen the spec needs and the base build lacks is designed at
  implementation from the prototype's existing patterns, in no new visual
  style; task 6.1 lists these screens, which ship with no prototype approved
  by use.
- (d) A screen Adam approves separately is taken from its own approved tag:
  v0.1-33, for the thread's replies and the recorded answer.

**Why:** the spec governs what the UI does and posts (*The answer session*).

#### The separate build was approved before gate one

**The prototype build covering thread replies and the recorded answer was
approved, and its tag named, before Adam approves this change's spec.**
Implementation starts only after both approvals, so no fallback is needed.

*Rejected:* designing those two screens under rule (c) in case the build came
late: approving it first made a fallback unnecessary.

#### Some answer-session details are decided at implementation

**Some details of the answer session are decided at implementation, with no
requirement added; task 6.11 lists them:**

- how a question's options are parsed from its thread;
- a draft's privacy;
- an asker's reply revising the options;
- what agreeing with a suggested verdict posts, and what citing a lore entry
  posts;
- the UI of the relay notice shown for the GitHub Actions comment on a pull
  request changing the person's relay file, designed under task 6.1's rule
  (c).

The spec decides instead: that `propose_reply` refuses a subagent's call and
may fill in the record's URL on a filter 1 decline (*Claude drafts a reply
only into the prompt box*); what agreeing to a shown recorded answer posts
(*Agreeing to a recorded answer is a filter 1 decline*); and that citing an
in-scope `active` lore entry pushes a citation file (*A person's cite pushes a
citation file*).

### Relaying answers

#### The thread is the durable record of an answer

**An answer's durable record is the relay identity's reply in the question's
thread.** Whether a question is answered, or waiting for the asker, is read
from its thread, kept current by polling. The relay's own reply marks the
question answered; any other reply is shown to the person and leaves the
question's state as it was. The thread is fetched again when a question
comes on screen and its channel's last poll is more than about a minute old,
and once more before relaying, so an answer relayed from another machine is
never posted twice (answer-session spec: *The thread is the durable record
of an answer*; *The thread is read again before a question is shown and
before a post*).

**Why:** the thread is the one place every machine, and the asker, can
read. A crash between a successful post and the write of its id to local
state loses nothing: the next read of the thread finds the post.

#### `User says: ` answers, `User asks: ` asks the asker

**A relay post that answers starts with `User says: `, and one that asks the
asker starts with `User asks: `.** "User" is literal in both prefixes, never
the person's name.

**Why:** "waiting for the asker" is read from the thread, which needs a mark
that every machine, and every surface, can read there.

#### A relay post gets no prose pass and no vetting

**A relay post is the person's words, so neither prose's pass nor the
inquisitor's filters apply to it.** The answer session posts it by running
the relay identity's skill as a host command, through the mod's own process
call, never as a tool call of the session's model, so no post hook sees it.
The answer-session spec's requirement *A relay post is posted by a host
command, unvetted* holds how the command runs and the credential scan it
gets instead.

**Why:** a prose rewrite would post words the person did not confirm. The
filters guard a person's time against an agent's questions, not the
person's own words.

#### Discord relay posts: no header, mentions that ping

**On Discord the answer session posts through discord-bot with none of its
header options and with its normal mention rewriting on, so a post starts with
its prefix and an `@name` in the person's answer notifies that member.** After
each Discord relay post, and each edit of one, the person sees discord-bot's
warnings, so they learn when an `@name` pinged no one. Setup does not fail
the Discord relay when `check` reports `memberSearch: false`
(answer-session spec: *An answer is relayed as the person's words*).

discord-bot's `post` adds a header only when `--agent`, `--session` or
`--project` is given (shared-skills PR #1, merged; `header()` in
`.agents/skills/discord-bot/scripts/discord_bot.py` on main at 90a0237), so
no Discord channel waits on a further discord-bot option.

**Why:** the person's own @-mentions should ping, as in a comment of theirs.
A `Recorded answer: ` post quotes nothing, so no relay post repeats a
record's @-mentions. An edit can drop a ping, so its warnings show too.

*Rejected:* mention rewriting off: it only stopped a quoted record's
@-mentions notifying people again, and no relay post quotes a record.
*Rejected:* failing setup on `memberSearch: false`: the warning at each post
tells the person instead.

#### The person can ask the asker

**When the person can't answer without clarification, they can ask the asker
instead, and the question then waits for the asker's reply.** An Igor's
worker asks in its handback comment and is gone, so a reply reaches whichever
worker next takes the item; asking back is mostly for people's questions.

#### Editing a relay post

**The person can edit a relay post later, where it was posted; the relay keeps
each post's id for that.** Editing an automatic post makes it the person's
words, starting `User says: ` in place of `Recorded answer: ` or
`Inquisitor: `, since the person confirmed its new text. An edit that leaves
a `User says: ` answer to a question a questions-branch log file holds, an
automatic post's edit included, pushes a new log file with the edited answer
(answer-session spec: *A relay post can be edited where it was posted*; *An
edit to a questions-branch answer pushes a new log file*).

**Why:** a questions-branch file never changes, so without a new file the
branch would keep the first answer. Which file counts is in *The newest
proven answer counts*.

**Accepted:** the person can edit only a question's latest relay post.

#### A rephrased answer carries its rephrasing, and the asker logs it

**A rephrased answer's relay post gives the rephrased question and a
one-sentence summary of the discussion on lines of their own after the answer,
and the asker, not the answer session, logs them.** The session's model drafts
both, generalising or leaving out context more private than what the
question concerns, and nothing is posted until the person confirms the whole
post. The asker's agent adds them to the question's log file under
`## Rephrased question` and `## Discussion`. When the answer session itself
logs a rephrased answer, for a questions-branch question, the file's answer
is the relay post's whole text, its `Rephrased question: ` and
`Discussion: ` lines included, and the rephrasing sections hold those lines
too. The answer-session spec's requirement *A rephrased question is answered
with its rephrasing* holds the post's layout.

**Why:** the asker already records the answer in its log file, which belongs
to its work, often on an unmerged branch; if the answer session wrote it,
each rephrasing would need its own pull request. A reader confirms a logged
answer only when it equals the linked comment, so a file recording the
answer alone would leave every rephrased answer unconfirmed.

*Rejected:* new frontmatter keys for the rephrasing: every frontmatter value
is one quoted line, and a question's text is not.

#### A questions-branch question is answered by a new log file

**A question from a lore repository's questions branch is answered by pushing
a new log file there, holding the question and the answer and naming the
answered file in `answers`, under the rules for an answer the person gave in
the session.** Asking the asker and editing are not offered for it. When the
file's `asked_in` links a post that also asked the question, the question is
shown once, from the post: the answer session relays the answer in the
thread and also pushes the log file. With no thread, the file alone answers
it (answer-session spec: *A questions-branch question is answered by a new
log file*; *A questions-branch answer file records the answer as given*).

**Why:** the questions branch never changes a file once pushed. Answering in
both places means neither the asker reading the thread nor an agent
searching the branch misses the answer.

#### An answer file records the question the person saw

**An answer to a linked message records the message's question as the person
saw it, not the question the log file holds.** No rule covers a lore
repository more visible than the thread: `asked_in`, and so the message it
points to, is written only where the lore repository is no more visible than
the thread (*`answer_link` and `asked_in` are withheld where they would
leak*). The one case left, a lore repository made more public later,
publishes everything already in it, so the answer file adds nothing worse.

**Why:** otherwise a log file whose `asked_in` points at an unrelated
message would get the person's answer recorded, as a decision, against words
they never saw.

*Rejected:* showing the file's question beside the message.
*Rejected:* a rule of its own for that later case, generalising the
message's words or relaying only in the thread: the case barely arises.

#### An answer file names the file it answers

**An answer file names, in its `answers` key, the one questions-branch file it
answers, as a handled file's `closes` does, instead of answering every file
with the same question.** The `log` command writes `answers` only when it
names a file already on that questions branch that holds no answer inside
it. Answer files naming a file do not count as its answer for this test, so
later answer files naming it are still written. igor PR #216 is asked to
refuse a worker's file holding `answers`, so that the Igor adds the key
itself and #216 pushes only what the Igor writes; *Open Questions* carries
that request. The next three entries say which answer file counts.

**Why:** answering every file with the same question is matching on words,
which exact identity replaces.

*Rejected:* keeping hash matching beside `answers`: matching gives machines
different answers.
*Rejected:* accepting an `answers` key planted in a worker's file.

#### The newest proven answer counts

**Among the files that would each count as an answer to the same question,
only the newest counts, newest by its proof:** for a comment link, the time
GitHub gives for the comment's last edit, or its creation; for a signature,
the signed commit's committer date, which only the signer could set. The
others show as input, labelled as superseded. A file that would not count,
such as an `input` file or an unanswered one, supersedes nothing (inquisitor
spec: *Among files with the same question, only the newest proven answer
counts*; *A file is as new as its proof, and supersedes only if it would
count*).

**Why:** ordering by the commit's place in the branch would let anyone with
push access re-push a copy of an older proven file and revert a newer answer.
If a file that would not count could supersede, a person without write access,
whose answer to a handback an Igor logs as `input`, would undo a maintainer's
answer.

#### `answers` decides a named file's answer; the search groups by hash

**`answers` decides only which answer a named file has: among the answer files
naming it, the newest counts. Filter 1's search groups every answer file by
the hash of its question, with or without `answers`, and the newest in each
group counts.** Two answer files naming one file can record different words,
each the question as the person saw it, and so fall in different hash
groups. So an answer file replaced by a newer one naming the same file is
labelled superseded in the search and stops counting, even in its own hash
group, where it may still be the newest (inquisitor spec: *A named file's
answer is the newest proven answer file naming it*; *A replaced answer file
stops counting even in its own hash group*).

**Why:** a later asker has no file of its own to name, so the search can
find earlier answers only by hash. Without the second rule, the person's
changed answer would not be the only one that counts.

*Rejected:* deciding a named file's answer by hash grouping: `answers` names
the file exactly.
*Rejected:* taking files that hold `answers` out of the hash grouping: a
later asker's search would not find them.
*Rejected:* letting a replaced answer file count on in its hash group.

#### A named file's answer must be the person's own, added alone

**An answer file counts as a named file's answer only when its proof, a
comment link or a signature, is the person's, and its commit adds that answer
file alone.** For a log file that tags no one, an answer counts only when its
proof's account has `decision` authority under filter 1's rules for that
file's repository, which for a questions-branch file is write access to the
lore repository. Both specs use this one test, held in the inquisitor spec's
requirement *A named file's answer is the newest proven answer file naming
it*.

**Why:** a copy of an answer the person gave to another question carries
their proof too, so without the commit test a copy pushed in one commit with
other files could become a named file's answer. No decision says whether
such a copy, pushed alone in its own commit, can become one; *Conflicts for
Adam to decide* lists it. A file that tags no
one, such as an Igor's handback routed by assignment, names no person whose
proof could be asked for, so write access stands in.

*Rejected:* accepting the risk that such a copy becomes a named file's
answer.
*Rejected:* answering files that tag no one only through filter 1's hash
search.

#### A named file stays shown until its answer counts

**A file named in `answers` stops being shown only when the answer file counts
as the person's answer, proven as filter 1 proves one.** Otherwise it stays
shown, with that answer beside it as input (answer-session spec: *A
questions-branch question's state is read from its branch*).

*Rejected:* letting any answer file hide the file it names.

#### Questions-branch answers relayed on Linear or Discord

**When the answer session relays on Linear or Discord an answer to a
questions-branch question, it logs the answer with that relay post's URL as
its `answer_link`, a pointer that nothing fetches.** The log file records,
word for word as quote lines, the text the answer session relayed. The `log`
command fetches only a github.com link and passes no other link to any
GitHub API call, and a non-GitHub link proves no writer (inquisitor spec:
*A log file and a miss file have one format*; *A log file's repository keys
and answer_link are checked before use*).

**Such a file counts through the signature on its commit, whatever surface
relayed the answer.** When the commit that adds it carries a signature GitHub
verifies for `answered_by`, the file counts as a decision, as a picker
answer logged with a signed commit does; without one, it is input. An answer
typed directly on Discord, Linear or Slack, outside the answer session,
stays input until a decision document, such as igor's scribe's record,
records it.

**Why:** the answer was given in the answer session and logged from the
person's machine under their signature. Only an answer typed directly on the
other surface has no such proof.

*Rejected:* counting every answer relayed off GitHub as input.

#### `answer_link` and `asked_in` are withheld where they would leak

**A Linear or Discord `answer_link` or `asked_in` is written only when the
lore repository is private, and a github.com one only when the lore repository
is no more visible than the repository the URL points into.** Otherwise the
log file is written without that key. A file without its `answer_link` still
records the answer, and counts only through its signature (inquisitor spec:
*The log command withholds a link where it would leak*; *A log file and a
miss file have one format*).

**Why:** the URL would point the readers of a more visible lore repository
into a more private thread. A Discord URL holds the server's and channel's
ids, and a Linear URL the workspace, issue and title. A Linear or Discord
thread counts as private, so a lore repository that is not private is more
visible than it. A github.com link into a more private repository leaks the
same way.

*Rejected:* always writing the URL, accepting the leak.
*Rejected:* writing no log file in a lore repository that is not private:
the file without the link still records the answer.

#### An answer that cannot reach its thread is kept pending

**An answer that cannot be posted in its thread is kept, as answered, not
relayed, never lost.** That covers a relay that lacks permission, a channel
that is off, a post that is refused or fails, an answer given on a machine
that does not read the thread's channel, and an answer held back by a reply
that appeared just before posting. A failed post keeps the answer this way,
since leaving the question as it was would drop the typed answer. The person
is always told the asker lacks the answer, so they can relay it by hand
(answer-session spec: *An answer that cannot reach its thread is kept
pending*; *Only the person is told an answer is pending*).

**Pending answers are kept in a separate pending list, which reuses the main
queue's UI almost exactly:** in Adam's words, the queue's screens, holding
pending answers. When setup's check of posting in its channel passes, a
pending answer returns to the queue, answer kept, for the person to approve
again. An answer also leaves the list once any machine's relay post naming
the question appears in the thread. A pending answer no check brings back
stays on the list indefinitely: one refused for its text, such as one too
long, one held back by a new reply, or one given on a machine not subscribed
to its channel. In a channel where no check can read posting rights, any
refused post turns the channel off, and a passing recheck turns it back on.
Even there, an answer refused for its text stays on the list: the recheck
does not bring it back. The person can always post, edit or drop any pending
answer.

**No other machine is told of a pending answer.** The person's other
machines read only the thread, and ask the question again as usual.

**Why:** reusing the queue's approved patterns spares the list a prototype
round. An answer no check brings back can stay because the person can
always act on it.

**Accepted:** another machine may re-ask a question one machine holds an
answer for, as *Which cross-machine cases are accepted* allows.

*Rejected:* pending answers as a state in the list of questions answered and
handled.
*Rejected:* returning an answer no check brings back to the queue at the
next opening.
*Rejected:* an "Answered on another machine, not relayed" notice on other
machines, offering to relay, edit or answer afresh, even only for a file
linked by `asked_in`.

#### The push order for a questions-branch answer

**For a question a questions-branch file holds, the answer session checks the
thread, records the owed push in the state folder, posts the relay post, and
then pushes the answer file with the post's link as its `answer_link`.** A
failed push is retried at each poll and each opening until it succeeds, as a
handled file's is. An answer held back because the check finds a new message
pushes its file only when it is finally posted; dropping it leaves no file.
Once the answer is posted and pushed, the question is answered, and a later
message in the thread is judged like any new message: a new question if it
asks the person something, ignored otherwise (answer-session spec: *A
questions-branch answer's file is pushed after its post*; *An owed push with
no URL is settled from the thread*, which also settles a crash before the
post).

**Only an answer pending because its thread's channel is off, or not
subscribed on this machine, is pushed at once, unchecked, with no
`answer_link`.** That holds whether the channel was off when the person
confirmed the answer or a refused post turned it off, in which case the file
is pushed once the post is refused. What later happens to that pending
answer decides whether another file follows:

- posted later unedited: nothing new is pushed;
- posted later edited: a new answer file is pushed, with the relay post's
  link as its `answer_link`;
- edited, then dropped: nothing new is pushed, and the file already pushed,
  holding the original text, stays the person's answer.

**Why:** the file follows the post, its push retried, so no thread is left
answered with no file. Recording the owed push before the
post means a crash between them does not lose the answer file. Checking the
thread first lets the person see a new message before anything is pushed.

A failed push's retry is also dropped when two conditions hold. First, an
answer file that counts as the person's answer names the same
questions-branch file. Second, this machine first saw that answer file at a
fetch made after it recorded the owed push. The second condition keeps a
file this machine already knew from cancelling the push. For example, an
answer pushed at once and later posted edited owes a new file; without the
second condition, the file pushed at once would cancel that push. This
reason is the author's
inference; *Conflicts for Adam to decide*, under *Open Questions*, asks Adam
to confirm it.

**Accepted:** a file pushed at once gives up the comment link that would prove
it on GitHub, and counts only through its signature. A dropped pending answer
of that kind leaves its file on the branch, still answering the file it names.

*Rejected:* pushing every answer file on confirmation: a held-back or
dropped answer would leave a file for an answer never posted.
*Rejected:* pushing the file of an answer whose thread cannot be read only
once it is relayed.
*Rejected:* pushing no file when a refused post turned the channel off,
unlike when the channel was already off.
*Rejected:* accepting a thread answered with no file.
*Rejected:* any machine pushing an answer file for a relay post it finds
without one.
*Rejected:* a dropped pending answer pushing a handled file.

#### What the answer session posts by itself

**The answer session posts by itself, with no word from the person, in two
cases, and only on a question with a thread:**

- **On any question, a person's included:** a `Recorded answer: ` post, when
  filter 1 finds an answer with authority (*Filter 1 runs on every incoming
  question*).
- **Only on an agent's question:** an `Inquisitor: ` post, when the question
  clearly fails filter 2, 3 or 4 (*Filters 2 to 4 judge every incoming
  question*). On a person's question the answer session only suggests the
  verdict to the person.

It posts neither on a question with a category. On a questions-branch
question, with no thread, it shows the recorded answer or the verdict to the
person instead.

**The session's model writes no word of an automatic post.** A recorded
answer is posted as `Recorded answer: see the record below.`, whatever the
record, a log file included, then `Recorded in: <URL>` holding filter 1's
hit, then, on GitHub, the `Re: ` line every relay post ends with; it quotes
no answer. An `Inquisitor: ` post is a fixed text for each of filters 2, 3
and 4, naming the filter and giving its action. With its text fixed but for
the record's URL, an automatic post gets no prose pass and no vetting, as a
relay post gets none. The answer-session spec's *Filter 1 posts a recorded
answer by itself in the question's thread* holds the `Recorded answer: `
text, and its *Filters 2 to 4 judge every incoming question* holds the
three fixed `Inquisitor: ` texts.

- It posts a recorded answer by itself only when the record is no more
  private than the question's thread: on GitHub, when the record's
  repository is no more visible than the thread's; on Linear and Discord,
  only when the record's repository is public. Otherwise the person sees the
  recorded answer beside the question, to relay or to agree to (*Agreeing to
  a recorded answer is a filter 1 decline*).
- When a lore entry is the recorded answer, it pushes a citation file, as any
  session's filter 1 does.

**Why:** a thread's text reaches the model, so with fixed texts a crafted
thread can at worst choose which fixed reply or which record is posted. A log
file's answer is a whole comment, which could hold @-mentions that would
notify people again on GitHub, or a `Recorded in: ` line of its own, so no
answer is quoted.

*Rejected:* a recorded answer in a sentence the model writes: a crafted
thread could steer it.
*Rejected:* quoting the answer with its mentions neutralised: it needs a rule
per surface.

#### No automatic post repeats one in its chain of replies

**No automatic post repeats one already made anywhere in its chain of
replies:** the reply, the relay post it answers, the question that relay post
names, and so on back. A repeat goes to the person. The answer-session spec's
requirement *A reply to an automatic post is a new question* defines the
chain.

**Why:** checking only the post a reply answered would let an agent that
kept replying get filter 2's text, then filter 4's, then filter 2's again
with no person seeing it.

#### A post the person chose says so

**A post made when the person declines because the inquisitor should have
handled it, choosing filter 2, 3 or 4, is that filter's fixed text followed by
the line `The person chose this filter.`,** which no automatic post holds
(answer-session spec: *A filter 2 to 4 reply the person chose says they chose
it*).

**Why:** an asking agent acts on filter 3's or 4's reply only when the person
chose it, and the line is how it tells.

### Incoming questions, declining and handled files

#### Which questions count as an agent's

**A question counts as an agent's when its message's author is a bot account,
or when it is a log file on a questions branch, unless it is a relayed
question.** A bot account is a GitHub App, a Linear app user, or a Discord
bot or webhook. A questions-branch log file counts as an agent's because
only the inquisitor's script writes one. A relayed question is a post
starting `User says: ` or `User asks: ` from any bot account, on any
surface: the words of the person whose answer session posted it, such as
another person asking this one through their relay, so it is a person's
question. Every other question counts as a person's, including an agent's
question posted with a person's own credentials, which the answer session
cannot tell apart (answer-session spec: *A relayed question is a person's
question*; *An agent's question comes from a bot account or a log file*).

**Why:** only an agent's question gets an automatic `Inquisitor: ` reply.
Erring towards a person's question means a person never gets a reply nobody
wrote.

#### Filter 1 runs on every incoming question

**Before it shows a question, the answer session runs filter 1 on it, whether
a person or an agent asked it, a relayed question included.** When an answer
with authority is recorded and the question has a thread, the answer session
answers by itself with a `Recorded answer: ` post, never one starting `User
says: `, and lists the question as answered for the person, who can edit
that post as any relay post (*What the answer session posts by itself*).

The session's model first judges whether the question has a category. A
question with a category reaches the script on standard input with its
category, never in a file; the script then searches no source outside the
machine, and the answer session posts nothing by itself on it. Other
questions reach the script in private files, as an agent's do.

When filter 1 answers an agent's question by itself, the answer session logs
a miss against filter 1. A person's question answered this way logs none
(answer-session spec: *Filter 1 runs on every incoming question*; *A
question with a category reaches filter 1 on standard input*; *Filter 1's
answer by itself to an agent's question logs a miss*).

**Why:** the person sees only what needs them. The miss is logged because the
asking agent's own filter 1 should have found the record.

#### Filters 2 to 4 judge every incoming question

**The answer session's model judges every question filter 1 did not stop
against filters 2, 3 and 4, and treats a question as failing one only when the
case is clear.** Any unclear case goes to the person as an ordinary question.
When an agent's question that has a thread and no category clearly fails one
of them, the answer session replies by itself through the relay with that
filter's fixed `Inquisitor: ` text, which names the filter and gives its
action. It then logs a miss against that filter and lists the question as
handled for the person. On a person's question, a relayed one
included, it only suggests the verdict, and the person decides. No automatic
post is presented as the person's words, and each can be edited. The answer-session spec's
requirement *Filters 2 to 4 judge every incoming question* holds the three
fixed texts.

**Why:** the person sees only what needs them, and a crafted thread can at
worst choose which fixed reply is posted.

#### A reply to an automatic post is a new question

**A reply to a post the answer session made by itself is a new question, as a
reply to any relay post is: the filters judge it again, and the answer session
may answer it by itself again.** A repeat within one chain of replies goes to
the person instead (*No automatic post repeats one in its chain of
replies*). When an asker's filter 1 cannot count the place a recorded answer
names, the asker treats the post as input, and its question stands.

#### What an asking agent does with an automatic reply

**An agent that reads a `Recorded answer: ` reply checks the place it names
through filter 1, acts on it only as filter 1 counts it, and never logs the
reply as the person's answer.** It pushes no citation for a lore entry the
post names, since the answer session pushed one when one was due, so one
question gives one citation.

**An agent acts by itself on an automatic `Inquisitor: ` reply only when it
names filter 2, which only defers.** It acts on a reply naming filter 3 or 4
only when the person chose that filter when declining, which the reply's last
line says. Any `Inquisitor: ` reply counts only when the relay App of someone
with write access to what the question concerns posted it, whether or not that
is the person the question asked. It never counts on a question that another
skill requires a person to decide, which filters 2 to 4 do not apply to.
Otherwise the reply is input, and the question stands. So every
`Inquisitor: ` reply on Linear and Discord is input, and so is every one on
GitHub until task 0.21 shows that GitHub reports which App wrote a comment.
An agent that acts on a reply takes that filter's action and records its
choice as its own filter would have (inquisitor spec: *An answer session's
automatic reply is a verdict, not a person's answer*, for a
`Recorded answer: ` reply; *An Inquisitor reply is acted on only from a
writer's relay App*, for an `Inquisitor: ` reply).

**Why:** a crafted thread can choose which fixed reply the answer session
posts by itself. Filter 3's and 4's replies decide a question, while filter
2's only defers it. Without the write-access condition, anyone who can
comment could post `Inquisitor: filter 4` and have an agent decide a
maintainer's question.

#### Two reasons to decline

**On any open question, the person can decline to answer, giving one of two
reasons:**

1. **Nothing to answer:** the conversation is over, or the message isn't a
   question, such as one picked up by mistake. Nothing is posted, no miss is
   logged, and the question closes.
2. **The inquisitor should have handled it:** the person picks the filter that
   should have stopped the question: 1, already answered; 2, can wait; 3, one
   option has merit; or 4, cheap to reverse. The answer session shows the
   person the exact post of that filter's reply, and posts it only once they
   confirm it. For filters 2 to 4 the post is the filter's fixed `Inquisitor:
   ` text, marked as the person's choice. For filter 1 it is a `Recorded
   answer: ` post naming the place the person gave or the model found. How the
   confirmation looks is prototyped (task 6.9). The answer session logs a miss
   against the picked filter, with any note the person typed.

The second reason applies to people's and agents' questions alike, since the
person chose it, and its posts start with the reserved prefixes, as automatic
posts do. The person can still answer on the surface by hand. With no thread
or with a category, nothing is posted and the question closes; with no
thread, filter 1 shows the person the recorded answer. Filter 3 also
offers the choice "the agent shouldn't have asked" (*Messages that are not
questions are ignored*).

Where a declined question is closed is set by *Closing works by exact
identity, never by matching*.

Answer-session spec: *The person can decline to answer*, *Declining for the
inquisitor posts the picked filter's reply*, *A filter 2 to 4 reply the
person chose says they chose it*, *The person's filter 1 reply links the
record they chose*, *The preview warns when a filter 1 record is more
private than the thread*, *A decline with no thread or with a category posts
nothing*, *Filter 3 also offers that the agent shouldn't have asked*, *A
decline for the inquisitor logs a miss once it takes effect*, *A filter 1
decline cites its lore entry once*, *A decline with nothing posted closes a
thread copy on this machine only* and *Only a thread copy declined with
nothing posted is reopened*.

**Why:** one reason's name keeps clear of filter 3's text, "not a real
question". The person, not the session's model, picks the filter, and sees
the exact post before it goes out.

*Rejected:* separate reasons for a conversation that is over and a message
that isn't a question: they behave alike.
*Rejected:* the session's model asking the person which filter should have
stopped the question, and why: the person picks the filter and confirms the
exact post instead.

#### Messages that are not questions are ignored

**A message of the first or second source, a mention of the person or a
mention of or reply to the relay, that the session's model judges clearly not
a question is ignored: it is not shown, nothing is posted on it, and nothing
is closed.** An unclear one is shown. The rule covers only those two
sources: a non-question from a review request, an assignment or a
questions-branch file reaches the queue unjudged.

One reply is never ignored: an asker's reply to the relay's `User asks: `
post puts the person's waiting question back in the queue, whether or not
the reply is a question (answer-session spec: *The thread is the durable
record of an answer*).

"Rhetorical" is not a category: an asking agent rewrites a message that is
not really a question as a statement, so an agent's rhetorical message in a
thread gets no post.

When a non-question reaches the queue anyway, the person declines it under
whichever reason fits:

- reason 1, nothing to answer, when the answer session's own judgement let
  it through: nothing is posted, no miss is logged;
- reason 2 with filter 3's "the agent shouldn't have asked", when the asking
  agent should not have written it: nothing is posted, and a miss against
  filter 3 is logged against that agent.

**Why:** a message picked up by mistake is the answer session's own
misjudgement, and no asker erred, so it logs no miss. Filter 3's fixed text
tells the agent to take an option that has merit, which a non-question does
not offer, so "the agent shouldn't have asked" posts nothing.

*Rejected:* filter 3's automatic reply on a rhetorical message: it is only
for a real question that did not need asking.
*Rejected:* a rhetorical fixed text of filter 3's own: the decline reasons
and filters 2 to 4 cover a question that needs no answer.
*Rejected:* a miss against the source that picked the message up: no asker
erred.
*Rejected:* posting filter 3's fixed text under "the agent shouldn't have
asked": it tells the asker to take an option it lacks.
*Rejected:* calling filter 3's choice "not a question": only reason 1 says
that, so two labels never share a name.

#### Declining with nothing to answer closes only that question

**A reason 1 decline closes only the declined question, and no later message
in its thread reopens it.** Every later message in its thread that the four
sources name, unless the ignore rule drops it, is shown on its own as a new
question, on every machine: the asker's unthreaded follow-up after a relay
post or a threaded reply to one, under the second source; a message
mentioning the person or a relay identity; and a review request or an
assignment made after the close. Any message posted in
a thread after a handled file closed its question is likewise a new
question (answer-session spec: *Later messages after an answer or a decline
are new questions*; *A question is resolved once answered or declined*).

**Why:** a reason 1 decline is held in each machine's own state folder. If
it stopped later messages counting, a follow-up would count on one machine
and not on another.

*Rejected:* a follow-up that stops counting after a reason 1 decline: it
would stop only on the machine that declined.
*Rejected:* a threaded reply reopening the declined question on one machine,
or dropping a reply that arrives after its question closed: the reply is
shown as a new question instead.

#### The answer session writes a handled file on every close of a questions-branch file

**Whenever the answer session closes a question that a questions-branch file
holds, it pushes one handled file for each such file, naming it.** A file
holds the question when the question was shown from that file, or when the
file's `asked_in` links the closed thread message. The answer session closes
a question by declining it, agreeing to a recorded answer included, or by
posting a `Recorded answer: ` or `Inquisitor: ` reply on it, with a thread
or without. A handled file is the one log file a decline pushes.

A handled file holds only two keys: `handled`, the day the question closed,
and `closes`, the unique file name of the one questions-branch file it
closes. It holds no question text, its slug is always `handled`, and it has
no body. It closes the named file without answering it. Filter 1's search
never matches a handled file, so a handled file never stops a question for a
searching agent.

The asking agent writes no handled file. The script's `log` command writes
one only under an option the answer session alone passes. An Igor worker
could still report a file holding these keys for its Igor to push; refusing
such a file is asked of igor PR #216, and is open on its side. The
answer-session spec's *A handled file closes a questions-branch question*
and the inquisitor spec's *A log file and a miss file have one format* hold
the format; *A handled
file is pushed once its close takes effect* holds when the push happens and
its retry.

**Why:** without a handled file, a questions-branch file whose question was
closed would stay unanswered and come back. A machine's first poll of a
channel reads only its last 14 days (*The answer session polls, only while
it is open*), so a machine that first polls more than 14 days after the
question was asked in a thread never reads the thread copy, and would show
the file as a new question. The answer
session writes the file itself, so no rule depends on checking which App
wrote a post, which waits on task 0.21. Holding no question text, a handled
file never carries a private item's question into igor's search.

*Rejected:* the asking agent marking its own file handled on reading the
answer session's post: it would have to check the post's author, which waits
on task 0.21.
*Rejected:* copying the question's text into the handled file with the
original's `asked_from`: nothing needs the text, and leaving it out keeps
private questions out of the search.
*Rejected:* no handled file for a question with a category: a handled file
holds no question text, so it reveals nothing.
*Rejected:* `repository` in the handled file for the visibility checks: it
served only the matching that exact identity removed.

**Accepted:** a record that the asking agent's own filter 1 would not count
still closes the question in the person's queue. The asker's question still
stands in its thread, and the asker can ask again. Asking again is a
legitimate request, since the asker may be unable to see or count the
recorded answer: a private record, one withheld by the visibility rules, or
one without authority.
*Rejected:* having the asking agent decide the close: the answer session
closes it.

#### Closing works by exact identity, never by matching

**A handled file closes the one questions-branch file its `closes` key names,
on every machine and for good, and nothing else.** A thread copy, a question
shown from its thread, is closed on every machine only by the relay posts in
its thread. A thread copy declined with nothing posted is closed on that
machine only, and can be reopened there. When a close concerns more than one
questions-branch file, one handled file is pushed for each. No question
hash, topic repository or time comparison takes part in closing.
Nothing reopens a file a handled file closed.

**A file a handled file closed is still unanswered,** so an answer the person
gives to its thread copy, on a machine where that copy is still open, still
pushes a log file answering it.

**Why:** matching on a question's words, on a judgement each machine made
for itself, or on clocks kept giving two machines different answers, and
each fix raised another case. Exact identity cannot disagree.

**Accepted:** a thread copy declined with nothing posted on one machine shows
again on the person's other machines, where they can decline it again.

*Rejected:* closing every copy with the same question hash, thread copies
included, or hiding a questions-branch file whenever any relay post names
the same question: matching on words gives machines different answers.
*Rejected:* closing copies by topic repository, each machine's own or the
closing machine's: each machine's judgement of it can differ.
*Rejected:* closing only copies asked by the handled day, or before the
handled file's commit time: comparing clocks gives machines different
answers.
*Rejected:* a key in a reason 1 decline's handled file limiting the close to
the copy declined: it served only matching.
*Rejected:* one handled file per topic repository: each handled file names
one file.
*Rejected:* no answer file for a file a handled file names: a handled file
closes a file without answering it.

#### Reopening a declined question

**The person can reopen a thread copy they declined with nothing posted, on
the machine where they declined it; reopening puts it back in their queue.** A
question declined with a post cannot be reopened: the thread records how it
was handled, and the person changes that by editing the post. A
questions-branch file a handled file names cannot be reopened, whether shown
from the branch or from a thread, since the handled file closes it
everywhere for good. A thread copy of that file stays reopenable on its
machine. A miss already logged for a reopened question stays, since a miss
file is never changed, and nothing records that the person took it back.

**Why:** after a post, the thread, which every machine reads, is the record
of how the question was handled.

*Rejected:* reopening a question on this machine whatever its thread shows.

#### A person's cite pushes a citation file

**A person cites a lore entry by answering a question with it, or by declining
under reason 2 with filter 1 and naming it as the record, agreeing to a shown
recorded answer included.** The answer session then pushes a citation file
for the entry only when it is `active` and its scope covers the question,
under the visibility rules of *A citation holds nothing about the question*,
which withhold a citation from a place less private than the question. The
person can cite any other entry; that pushes nothing. A decline's citation is
pushed once, to the entry's own lore repository, whether or not its miss is
pushed (answer-session spec: *A person cites a lore entry by naming it as an
answer or a record*; *A person's cite of an active entry in scope pushes a
citation file*; *A filter 1 decline cites its lore entry once*).

igor PR #216 is asked to widen its definition of a citation to include a
person's cite; that request is open on #216's side.

**Why:** filter 1's own citation, and igor PR #216's, are pushed only for an
`active` entry in scope, and a person's cite follows the same rule. One
question gives one citation.

*Rejected:* a citation for any cited entry: citations count only `active`
entries in scope.
*Rejected:* the asking agent pushing the citation when it acts on a
`Recorded answer: ` post: the answer session already pushed it.
*Rejected:* pushing a decline's citation only when its miss is pushed: the
only duplicate left is two machines declining one question, accepted below.

**Accepted:** two machines can each push a citation for one question, when
it is open on both at once, or when a thread copy declined with nothing
posted on one is declined again on another. It is rare, and no rule is
added.
*Rejected:* re-reading the questions branch before a decline's pushes: the
case is rare.
*Rejected:* pushing no citation for a reason 2 decline: the case is rare.

#### Agreeing to a recorded answer is a filter 1 decline

**When the answer session shows a recorded answer instead of posting it, the
person may agree to it, and agreeing is declining the question under reason 2
with filter 1, naming that record.** This holds on every question, in a
thread or with no thread. The decline path does the rest:

- it shows the exact post;
- for a record more private than the thread, it warns that posting shows the
  record exists, and posts only once the person confirms;
- it cites a lore entry, as *A person's cite pushes a citation file* says;
- it logs the miss against filter 1 with the decline's default `said`, `the
  inquisitor should have handled it`, since agreeing takes no note, as in the
  approved prototype;
- when nothing is posted, it closes the question in the state folder;
- it pushes no answer log file, with a thread or without, only a handled file
  where a questions-branch file holds the question.

In a thread, the confirmed `Recorded answer: ` post is the record there
(answer-session spec: *Agreeing to a shown recorded answer is a filter 1
decline*).

**Why:** the record exists and filter 1 found it, so a log file pointing to
it adds nothing. A later searching agent is stopped by that record only when
its own filter 1 can read and count it. Filter 1 should have stopped the
question either way, so the miss is logged.

**Accepted:** agreeing logs a miss on a person's question too.

*Rejected:* not offering agreement for a record more private than the
thread: the warning lets the person decide.
*Rejected:* a log file whose answer points to the record: it adds nothing.
*Rejected:* a record and a `said` of agreeing's own: agreeing is a decline,
and uses the decline's.
*Rejected:* no miss when the person agrees on an agent's question.

#### Misses the answer session logs

**Each miss the answer session logs goes to the questions branch of the team's
lore repository that serves the repository the question concerns, pushed
directly by the script, with no pull request.** The session's model judges
the repository the question concerns as the inquisitor's spec has an agent
judge it; on GitHub, when it can't tell, that is the repository holding the
question's thread. The answer session logs a miss in three cases, against:

- filter 1, when it answers an agent's question by itself;
- the failed filter, when filters 2 to 4 handle an agent's question by
  itself;
- the filter the person picks under reason 2, agreeing included, on a
  person's question as on an agent's.

A reason 1 decline logs none. A miss the answer session logs by itself has
`said` `answer session: clearly filter <n>`. Under reason 2, `said` is the
person's note, or `the inquisitor should have handled it` when they typed
none. A miss is pushed even when one with the same question and `filter` is
already on the branch, so a question judged on two machines gives two misses.

A miss for a question a questions-branch file holds copies that file's
`asked_from`, so the visibility rules treat it as they treat the file. This
is the one exception to the script never writing `asked_from` (*The Igor
writes `asked_from` on every file it pushes*). igor PR #216 says only an
Igor writes `asked_from`; allowing this second writer is open on #216's
side.

No miss is written when the question has a category, concerns no
repository, or has no configured lore repository serving its repository, or
when that lore repository is more visible than the repository or the
question's thread. The answer session then tells the person why, and the
question still closes. The inquisitor's rule that a question with no log
file gets no miss does not apply here (answer-session spec: *The answer
session logs its misses on the team's lore repository's questions branch*;
*A miss records who judged it and copies its file's asked_from*; *The answer
session writes no miss it cannot place privately*).

**Why:** the answer session cannot see where the asker logged the question,
often an unmerged branch, and the questions branch takes direct pushes, so
misses need no pull request. The fixed `said` lets a review of misses tell
the session's judgement from a person's word.

*Rejected:* writing the miss where the asker's log file went: the answer
session cannot know where, and each miss would take a pull request.
*Rejected:* keeping misses in the state folder: it would be a personal
question log, which this change rules out.
*Rejected:* pushing a miss only when no matching one is on the branch: that
is matching on words.
*Rejected:* no miss for a question whose file holds `asked_from`: copying it
keeps the miss as private as the file.

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**A questions-branch log file for a question the asking agent also asked in a
post holds that message's URL as `asked_in`, and follows the message by that
exact link.** Whatever the answer session decides about the message (showing
it, answering it, ignoring it as not a question, declining it) applies to
the file, which is not shown on its own. A log file with no `asked_in` is
judged on its own, as a question of the fourth source. The answer-session
spec's *A log file follows the thread message its asked_in links* and *A log
file with no followed link is judged on its own* hold which links are
followed; the inquisitor spec's *A questions-branch log file links where its
question was asked* holds the order: post first, then write the log file.

**Why:** a link names one message exactly, so every machine pairs the same
file with the same message.

*Rejected:* judging every log file on its own: the person would see each
question twice.
*Rejected:* hiding a log file by matching its words to a message: matching
gives two machines different answers.

#### A link this machine never reads is not followed

**A log file whose `asked_in` links a message this machine never reads is
shown on its own, as a question of the fourth source.** Such a message is in
a channel this machine does not subscribe to, or on a surface it has turned
off or cannot read. An answer given there is kept pending until it can be
relayed (*An answer that cannot reach its thread is kept pending*).

*Rejected:* showing the file nowhere on that machine: the person would never
see the question there.

#### A log file without `asked_in` is never merged

**A log file with no `asked_in`, whether the link was withheld for privacy or
never written, is always shown as its own question.** It is never paired
with a thread message by matching text.

**Why:** merging's only benefit is avoiding a duplicate, which is low
priority. Any merge rule can pair a message with another asker's file in the
same words; a decline then closes that asker's question, or an answer is
recorded against it.

**Accepted:** where the link is withheld, on Linear and Discord from a lore
repository that is not private and on GitHub from a more visible one, the
person may see one question twice, as *Which cross-machine cases are
accepted* allows.

*Rejected:* merging a log file and a thread message that ask the same
question into one entry, with any set of guards: each guard left a case that
closed or answered the wrong asker's question.

#### A bot's question reaches only the first person it mentions

**A message by a bot reaches only the first person it mentions; a message by a
person reaches each person it mentions.** A bot here is any bot or agent
account: an Igor, an agent running the inquisitor, or any other bot. The bot
orders its mentions by importance. For an Igor, Adam decided the order in
igor issue #229, which is open; igor's specs do not state it. Under it, an
Igor mentions its operator first only when it stops for a reason it detects
itself, then the assignee and the creator; every other handback, a question
included, mentions the assignee and then the creator. The answer session
does not know who an operator is and needs no rule about it. The rule
applies to Igors directly (answer-session spec: *Whom a message reaches is
set by its mentions*; *A mention names a user outside code, quotes and
links*, which define a bot account and a mention).

**Why:** each bot question has one owner, so two people cannot give a bot
conflicting answers, and the inquisitor never needs to know an operator.

*Rejected:* a handback reaching the assignee unless it mentions someone else
and not them: it gives a bot question more than one owner.
*Rejected:* routing an Igor's handback by assignment until igor's specs
state the order of issue #229: no one uses igor yet, so the spec states only
the end state.

#### igor's handback marker

**The answer session identifies an Igor's handback by a fixed marker igor
gives its handback comments: a handback is a comment by an `igor-` App holding
that marker, and an Igor comment without it is not a handback.** igor chooses
the marker's form, and task 0.6 records it. The post hook does not read the
marker (*No exemption for an Igor's handback*). The answer-session spec's
*A handback is an igor- App's comment holding igor's marker* holds the
details; the entries below say how handbacks are shown.

**Why:** an Igor posts other comments on the item too. The marker tells a
handback from them, and text the Igor quotes from its item cannot produce it.

*Rejected:* counting every comment by an `igor-` App as a handback.

#### Only an item's newest handback is open

**When an Igor posts a newer handback on an item that still holds an older
unanswered one, only the newest counts as open.** An item an Igor handed
back, and assigned to the person, is shown only through its newest
handback. Every older handback is passed over by a reading rule each answer
session applies to the thread, with no coordination between machines.
Nothing is written for it: no post, edit or handled file. It drops out of
the queue and is never shown again, even once the newest is answered. The
newest handback is open until a relay post naming it answers it, or handles
it with a `Recorded answer: ` or `Inquisitor: ` post (answer-session spec:
*Only an item's newest handback is shown*; *An item's newest handback is
open until a relay post names it*).

**Why:** a newer handback can follow only once the person returns the item to
the Igor without answering the older one, so the case is rare. The newest
handback says where the Igor is blocked now.

**Accepted:** a passed-over handback's log file stays on the questions branch,
unanswered, and is never shown again. If its blocker still matters, the Igor
asks again on its next run.

*Rejected:* a new log file linking its own handback only while an earlier
one is unanswered: less simple than every file linking its own handback,
and guarantees no more.
*Rejected:* an answer naming only the oldest unanswered log file: its
question no longer says where the Igor is blocked.

#### A handback that mentions no one reaches the assignee

**An Igor's handback that mentions no one reaches the item's assignee, under
the source of questions that is an item assigned to the person.** One that
mentions people reaches only the first one mentioned, under the first source,
as for any bot's message. So on an item assigned to the person, a handback
that mentions people reaches them only if they are mentioned first. For a
handback that mentions no one:

- while the item is assigned to no one, it is shown to no one; once someone
  is assigned the item, it is shown to them;
- an item assigned to someone else is theirs and never appears in this
  person's queue.

The answer-session spec's *A handback that mentions no one goes to the
item's assignee* holds the details.

#### Each Igor log file follows its own handback comment

**An Igor worker's log file links, in `asked_in`, the handback comment that
asks its question, and follows that comment as any log file follows its thread
message.** Answering or declining the handback applies to the file, and an
answer to a handback names only that handback's log file. The file is shown
only while its comment is the item's newest handback, and to whoever that
handback reaches. A later Igor question on an item whose earlier question is
already answered follows that run's new handback comment, which reaches the
person as a new message in an answered thread; the answer is relayed on the
item and logged against the new file. The Igor writes the key after posting
the comment, applying the withholding rule (inquisitor spec: *A
questions-branch log file links where its question was asked*); the
answer-session spec's *An Igor's log file follows its own handback comment*
holds when the link is followed.

**Why:** each file follows exactly one comment, so one answer never closes
the log files of two handbacks, and the newest-handback rule needs no other
mechanism. It is the simplest mechanism that guarantees this. The Igor
writes `asked_in`, not the worker, because the comment exists only once the
Igor posts it, so the worker cannot know its URL.

*Rejected:* linking the log file to the assigned item: two handbacks on one
item would share one link.
*Rejected:* showing an Igor's log file on its own: the person would see the
handback's question twice.
*Rejected:* posting the answer on the item when the file is answered on its
own: the file follows the handback, so the answer is relayed there.

### OpenSpec, prototypes and scenario tracing

#### OpenSpec for new work in shared-skills

**New work in shared-skills goes through OpenSpec, except UI, which is
prototyped and then built directly.** A skill's spec holds what must be true
of it, and its `DECISIONS.md` holds why. An existing skill gets no spec until
a change touches it. This change adopts OpenSpec, spec-check and spec-trace
for the repository. Its decisions follow spec-check's convention: each is
stated once, in design.md's *Decisions*, and each undecided item in *Open
Questions*.

#### How the three specs are laid out

**Each spec opens with a `## Purpose`. Each requirement states one rule, or
two rules that only make sense together, in under 500 characters, and its
scenarios hold the examples and cases.** The reasons are in this file. The
inquisitor's Purpose defines the terms its spec uses throughout. Any other
term is defined in the requirement that first uses it. A definition that
carries a rule, such as a default, a "never", a closed list or a condition,
also has that rule stated in a requirement, because a Purpose is not
normative.

**Why:** `openspec archive` takes a new spec's Purpose only from the delta's
`## Purpose` (spec-check, PR #50). `openspec validate --strict` fails any
requirement whose text runs over 500 characters. Adam ruled on 2026-11-01
that splitting is the last resort: detail moves first to scenarios, then
reasons move here, then the text is compacted, and only a requirement still
too long is split, along its own rule boundaries.

*Rejected:* a glossary requirement holding every term, at 17,651 characters.

#### A skill's DECISIONS.md is current reasoning, not a log

**A skill's `DECISIONS.md` holds its current reasoning in one place.** While a
change is open, its reasoning lives in its proposal and design.md. When the
change is archived, its lasting reasoning is folded into the `DECISIONS.md` of
each skill it affects, rewriting the reasoning it replaces rather than
appending. `AGENTS.md` states the rule, and `openspec/config.yaml` makes it
the last task of every change.

#### UI is prototyped and approved by use, not specified

**Once Adam has used a UI's prototype and approved it, the UI goes straight to
an implementation pull request.** The feature's other parts, such as its
data flow, integrations, setup and rules, still go through both pull
requests, spec then implementation. A spec names a UI only as an interface
the other parts use, and does not describe the UI itself. One exception: a
screen that a spec's task says is designed at implementation, from the
patterns of the feature's approved prototype, is built with no prototype of
its own; the spec still does not describe it, and the task only names it.
Task 6.1's rule (c) is such a task. `AGENTS.md` states the rule and its
exception.

**Why:** whether a UI works is easier to see by using it than by reading a
spec.

*Rejected:* keeping the exception only in this change, outside `AGENTS.md`.

#### A scenario about the agent is traced to a SKILL.md test

**A scenario about what the agent does is traced to a test that checks
SKILL.md states the rule.** design.md's *Tracing scenarios to tests* gives the
details.

**Why:** spec-trace's CI fails on an untagged scenario once the change is
archived.

*Rejected:* exempting those scenarios in spec-trace's baseline
(`openspec/spec-trace-baseline.txt`), which takes no new lines.

#### Igor-worker scenarios stay untagged until igor builds what they need

**The implementation tags no test for a scenario that only igor's unbuilt
work, such as `igor lore-search`, can make pass, so spec-trace shows it as
uncovered.** *Tracing scenarios to tests* lists each as an expected gap, and
task 4.3 tags each once igor provides what it needs. spec-trace does not
change.

*Rejected:* skipped, tagged tests: spec-trace counts a skipped test's tag as
coverage.

#### The change is archived only after every expected gap is tagged

**This change is archived only after task 4.3 has tagged every expected gap,
so spec-trace's CI never meets an untagged scenario in `openspec/specs/`.**
This is a second condition on the archive, beside task 7.0's wait for igor
PR #216 to merge.

*Rejected:* archiving the rest and leaving the Igor-worker scenarios in an
open change.

## Open Questions

### Facts measured before building

Tasks 0.1 to 0.14 measure these facts before anything is built. Each bullet
says what the spec does if the fact turns out false. Task 0.12 is measured;
*What task 0.12 measured* gives its result.

- **Can a `PreToolUse` hook block `AskUserQuestion`?** (tasks 0.1 to 0.3)
  If not, only the skill's instructions cover the picker, and the README
  says so.
- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, then wherever the agent lacks push
  access, every answer in a post and every issue's decision block counts
  as input, and a post's question tags no one.
- **Can the script learn which login a post goes out as?** (task 0.7) An
  agent using the github-app skill posts with a token only the posting
  command holds, so the script's own `gh api user` returns the person's
  login. If the script can't learn the posting login, it treats every post
  as going out as the person, and with a person in the session it asks
  through the picker where it would have tagged them.
- **Can the script tell whether a person is in the session, and whether a
  headless session can post?** (task 0.9) If it can't tell whether a
  person is there, the session counts as having no one in it, so no picker
  opens with nobody to answer. If it can't tell whether a headless session
  that is not an Igor worker can post, that session counts as unable to
  post, and asks nowhere. Whether the script runs in an Igor's run is not
  part of this fact: it reads that from `IGOR_RUN`. Task 0.9 checks that
  igor sets `IGOR_RUN` as igor PR #216 specifies, once igor builds it.
- **Can the script find the approver of the pull request that added a
  decision?** (task 0.8) A `DECISIONS.md` section leads through blame and
  a commit to a pull request and its reviews. If not, the script skips the
  first candidate in the tagging order, whoever approved the related
  earlier decision.
- **Can the script find the GitHub login of the last person to commit to a
  file?** (task 0.5) Git records a name and an email, not a login. If not,
  the script skips the third candidate in the tagging order, whoever last
  changed the files involved.
- **Can the agent open, and write in, a repository's private security
  advisory?** (task 0.10) That needs private vulnerability reporting
  enabled, or an admin or security-manager role. If it can't, the agent
  records a vulnerability's question and answer nowhere but the fix, and
  reports only that a vulnerability question is blocking, with no text.
- **Can the private fork's pull request be merged before the advisory is
  published?** (task 0.13) *Weaknesses stay out of public text until
  disclosure* gives what each result means. Until it is measured, the
  fork's commit messages describe no weakness, the advisory's text holds
  the full description, and a regression test goes in the fork only on the
  word of the person publishing the advisory.
- **Does GitHub's API give a comment's author and a commit's verified
  signer, as the proof of a questions-branch writer needs?** (task 0.11) If
  not, every questions-branch `decision` or `agent` file counts as input.
- **Does a comment's `updated_at` change only when its text is edited?**
  (task 0.11) *The newest proven answer counts* dates a comment link's
  proof from the comment's last edit, so it relies on `updated_at` not
  moving on a reaction, a hide or minimize, or other metadata. If it does
  move, the spec states no fallback; the ordering for that case is decided
  once task 0.11 has measured it.
- **Can an Igor worker post?** (task 0.14) igor's task-execution
  requirement keeps every credential but its seat's out of the worker's
  environment, but a `gh` login in the worker's home directory is in
  neither its environment nor its working tree. If a worker can post, it
  still asks only in its handback comment, and the credential within its
  reach is reported to igor as a breach of that requirement.

### Facts the answer session relies on

**Tasks 0.15 to 0.24 measure facts the answer session relies on, and each
task says what the spec does until it is measured.** They cover GitHub's
notifications endpoint; how Linear and Discord show mentions and replies;
how the Linear relay posts a comment; that a command the mod runs reaches
no tool hook; that a mod keeps polling while idle or in the background;
how setup checks a relay's access to each channel; whether GitHub reports
which App wrote a comment; whether a reader can read the pull request and
signature behind a relay file's last change; whether the `asked_in` URL an
asking agent records is the one the answer session reads; and how setup
can tell that a questions-branch commit will be verified for the person.

- **Which App wrote a comment** is measured on both sides: igor PR #216's
  task 4.8 measures it too, like task 0.21 here. Until a measurement shows
  that GitHub reports it, every `User says: ` comment is input.

### What igor must provide

The archive and Igor-worker mode wait on igor. What follows was read from
igor PR #216 at head 59e7561 (2026-10-24), which records #216's decisions
up to its 149, including 92 and 97 on the categories a flagged worker's
flag lists. *The script tells an Igor's run by `IGOR_RUN`* cites #216 at
ba154a0 (2026-10-20), and *A flagged run asks nothing and pushes nothing*
at d3b7740 (2026-10-21).

- **#216 can drop two of its "Still open" items, both requests to this
  change, since this change has done both:** stating the flag's categories
  as #216's decision 97 does, in no fixed order (*The flag a worker raises
  for a question with a category*), and aligning the flagged run with its
  decisions 84 and 89 (*A flagged run asks nothing and pushes nothing*).
- **Igor-worker mode waits for igor to build its search command.** A
  worker can't run this skill (*What task 0.12 measured*), so filter 1 in
  a worker calls igor's read-only `igor lore-search`, which igor PR #216
  specifies and igor has not built. #216's task 4.5 measures whether a
  worker can give the command its standard input; if not, #216 gives it
  another way to take the text, and this change adopts it. igor must also
  let a worker run the skill's script, which today means a role's
  `commands` lists it. The spec's rule that a failed command searches no
  lore stays, as a guard.
- **The archive waits for task 4.3.** Task 4.3 tags every expected gap, the
  Igor-worker scenarios no test covers, once igor builds `igor lore-search`
  and lets a role's `commands` list the skill's script. Task 7.0 also waits
  for igor PR #216 to merge and for igor PR #202 to set the path of the
  scribe's records.
- **igor PR #216, with igor issue
  [#215](https://github.com/adamstallard/igor/issues/215),** amends igor's
  lore-firing spec and holds every rule for an Igor's citations. It has not
  merged. This change relies on it for:
  - *An Igor publishes the citations its worker reports*: what a worker
    reports for a citation, with no category, and which citations an Igor
    pushes and when, from a worker or its own inquisitor run, in this
    change's citation format.
  - Its review counting citations on the lore repository's `questions`
    branch (its decision 8), shown as "not checked" when every Igor push of
    them failed (its decision 32).
  - Its id check reporting an out-of-scope collision during a run only as
    "id taken" (its decision 6); such an entry is not proposed in the run.
  - A run's search reading only the lore repository the Igor injects from.
  - *Transcripts and outcomes are captured to the state branch*, in its
    task-execution spec: the flag for a question with a category, its
    categories, and what the Igor does with it (its decisions 92 and 97).
  - *An Igor publishes the questions-branch files its worker reports*:
    which question, miss and `authority: agent` files the Igor pushes and
    when (its decisions 20, 21, 24 and 26), including the answer to a
    handback when a worker re-works the item. A flagged run pushes none,
    and a run that ends without its worker's completed report counts as
    flagged (its decision 38). Each file is checked with igor PR #217's
    credential matcher, and a person's answer is pushed only beside a
    question the Igor asked, as its record of the handback holds it (its
    decisions 28, 30 and 41). The lore repository's visibility is read at
    every push (its decision 37), each file's `asked_from` is set (its
    decision 42), and a file's `repository` key may name any repository,
    whether or not the run's role works it (its decision 33, amending its
    20).
  - *An Igor runs its worker's lore searches*: `igor lore-search`, which a
    worker and the Igor's own inquisitor run call. It matches plain text,
    ranks and caps hits as filter 1 does, and labels each question file an
    answer, input, unanswered or a miss (its decision 23). It runs this
    change's authority checks first, and labels the file unconfirmed input
    when a check can't run or fails (its decision 34). Those checks read
    relay files as *An Igor reads relay files as of igor PR #208's applied
    commit* says, and count a relay file only when its last change was that
    person's. The Igor reads the relay file too, to decide `authority` for
    a relay App's handback answer.
  - A questions-branch file's scope: every role whose Igor uses that lore
    repository, returned only to a run whose item's repository is no more
    visible than the more private of the file's `repository` and
    `asked_from` (its decisions 25, 27 and 42).
  - Its `graceful-handoff` and `work-triage` deltas: igor's side of a
    flagged run, its handoff, its host file and the release of a held item.
- **#216 must allow a second writer of `asked_from`.** #216 says only an
  Igor writes `asked_from`, but an answer session's miss copies the
  `asked_from` of the questions-branch file it closes. #216's push
  conditions and its decision 42 should allow for that.
- **#216 should refuse a worker's file holding `handled` or `closes`,** as
  it refuses one holding `asked_from`. Only an answer session writes a
  handled file, but #216 pushes any worker file with no `authority` as an
  unanswered question file. A worker steered by item text could then
  close, on every machine and for good, whichever file a planted `closes`
  names.
- **#216's Igor should keep, in its own record of the handback (#216's
  decision 59), the 6-hex-digit suffix and the date of the name of the
  questions-branch log file it pushed for the question, and no question
  text.** A later run names that file in `answers` from this record, never
  from the handback comment (*A later run names the answered file from the
  Igor's record*). Without the record, the run writes no `answers`.
- **#216's Igor should write `asked_in`** in a worker's log file as the URL
  of the handback comment that asks it, once it has posted that comment,
  withholding it when the item's repository is more private than the lore
  repository. It names in `answers` the file an answer file answers,
  adding `answers` itself and refusing a worker's file that holds it.
  Without `answers`, the answer session keeps showing the answered file as
  unanswered.
- **#216 should give every handback comment a fixed marker,** which no
  text the Igor quotes from its item can produce (*igor's handback
  marker*). igor chooses its form, and task 0.6 records it.
- **#216 should widen its definition of a citation to include a person's
  cite.** It defines a citation as an agent's record that a lore entry
  answered a question so that no person was asked. Here a person's cite of
  an `active` entry in scope pushes a citation too, as does a decline under
  "the inquisitor should have handled it" with filter 1 naming such an
  entry (*A person's cite pushes a citation file*).
- **How an Igor runs the inquisitor skill itself** has no mechanism in igor
  PR #216 or igor #211. Decided: igor marks that run with `IGOR_RUN=igor`, and
  the script then searches lore only through `igor lore-search` and pushes
  nothing. Open: which other sources that run's filter 1 covers, how the
  run hands its files to the Igor, and whether it can read GitHub.
- **igor's specs must state the order in which each Igor mentions people,
  which Adam decided in igor issue
  [#229](https://github.com/adamstallard/igor/issues/229).** #229 is open,
  and no igor spec states the order, which *A bot's question reaches only
  the first person it mentions* gives and relies on.
- **igor PR #153, signed publishing,** would have an Igor whose role lists
  prose or bug-hunter push only commits that went through those skills and
  carry their trailers. Citation commits carry none, so #153 should exempt
  an Igor's commits to a lore repository's `questions` branch. That
  is #153's to settle.
- **igor PR #202 must say where the scribe's records live,** in the
  repository a question concerns and in the lore repository, since filter 1
  searches them there. Two of #202's open points decide when an answer
  typed directly on another surface can count through a scribe's record:
  - #202 has not settled how the scribe recognises an approval given off
    GitHub. Until it does, the scribe can't mark a record of an answer
    typed directly on Discord, Slack or Linear `accepted`. Such an answer
    then counts only when a person writes it into another decision
    document that filter 1 counts, such as one on the default branch of
    the repository the question concerns.
  - #202's spec puts a decision about several repositories in the lore
    repository. Filter 1 reads the lore repository's decision records
    where #202 puts them (task 7.0).
- **igor issue #211's body should record that the post hook vets every
  post it sees, a handback included** (*No exemption for an Igor's
  handback*). #211 proposes this skill and the Igor inquisitor role, and
  its body lists five open questions:
  - Three concern only the role, which is out of scope (*The Igor
    inquisitor role is out of scope*): the role itself, which nobody has
    claimed; how long it waits before following up; and whether a team
    discussion, such as a chat channel or a shared document, is a new kind
    of surface for Igor, beside the tracker and the code host.
  - The fourth, when an Igor's worker can run the skill, is this change's
    Igor-worker mode, which waits on what this section lists.
  - The fifth asks whether the post hook can tell a handback comment from
    other posts. This change's answer: it need not, since it vets every
    post it sees, and an Igor posts its real handbacks through its own
    code, which the hook never sees.

### What other changes must provide

- **bug-hunter needs a matching note:** the regression-test rule of
  *Weaknesses stay out of public text until disclosure*. A separate change
  to bug-hunter carries it.
- **The github-app skill's `token`, `run`, `credential get` and `wire`
  commands must refuse an identity marked as a relay.** No pull request for
  it is open. This change asks for it, does not make it, and ships without
  it, at the cost *github-app refuses `token`, `run`, `credential get` and
  `wire` for a relay identity* accepts.

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would have that surface's API vouch for the message's author,
  and something map the author to a GitHub login: igor issue #160's
  configuration entry keyed by the Discord user id, or a file in the lore
  repository. A later change would choose. Without it, an answer typed
  directly on such a surface counts only through a decision document, such
  as the scribe's record; one typed in the answer session and relayed there
  counts through its log file's signature.

### Left to implementation

- **Task 6.11's details are chosen at implementation, with no requirement
  added,** and recorded in design.md while the change is open. *Some
  answer-session details are decided at implementation* lists them and
  what is decided around them.

### Conflicts for Adam to decide

- **Whether a `decision` log entry on the current work's own branch
  counts.** The rulings behind *Decisions* disagree. In proposal.md at
  commit 5c9fcc6, ruling 56 has a `decision` log entry count "only when it
  is on the default branch, or, for lore, on the `questions` branch".
  Ruling 76 says an `agent` file "follows the same rules as a `decision`
  file: it counts only on the default branch, on the current work's own
  branch for questions within that work ..., or on a lore `questions`
  branch", and ruling 80 says the current-branch condition "covers
  decision documents and `agent` entries there". Neither 76 nor 80 says it
  changes 56. *A logged decision counts only when merged and its author
  has access* states only the undisputed part: the default branch, or a
  questions branch with a proven writer. *A decision on the current work's
  branch answers that work* and *An agent's choice counts only in the work
  it belongs to* let an `agent` entry count on the work's own branch and
  say nothing of a `decision` entry there. The spec's *A log entry counts
  only where its branch allows*
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:1010-1013) counts
  either kind on the work's own branch.
- **What the Igor's record of a handback holds.** *A person's answer to a
  handback* matches an answer against the Igor's record of the questions
  it posted, compared as reduced for their hash (#216's decision 41). *A
  later run names the answered file from the Igor's record* says that
  record holds only the log file name's suffix and date, never question
  text. They may be two records (#216's decisions 41 and 59), or one that
  also holds question hashes, which "only" would rule out. *Alignment with
  igor PR #216* calls #216's decision 59 "the hashed record of handback
  questions". Meanwhile each entry states its rule as written.
- **Whether a reopened decline leaves its miss behind.** *Reopening a
  declined question* keeps an already logged miss, since a miss file is
  never changed. Its source, ruling 255 in proposal.md at commit 5c9fcc6,
  carries the note "Amended by Adam's decision 298: no decline that can be
  reopened logs a miss". But under *Messages that are not questions are
  ignored*, filter 3's choice "the agent shouldn't have asked" posts
  nothing and logs a miss, and a decline that posts nothing on a thread
  copy can be reopened on its machine. Nothing says which holds for that
  decline. Meanwhile the entry keeps "the miss stays".
- **Whether to keep the "until #202 settles" sentence on off-GitHub
  approvals** in the igor PR #202 bullet above. It may be an interim igor
  design, which this change does not write while igor has no users, or
  only restate *An answer typed on another surface counts only through a
  decision document*, true in the end state too. Meanwhile the bullet
  keeps the sentence.
- **Whether a copy of an answer, pushed alone, can become a named file's
  answer.** *A named file's answer must be the person's own, added alone*
  is meant to stop a copy of another question's answer pushed in one
  commit with other files. A copy that carries the person's comment link
  and is pushed alone passes both its tests. No ruling says whether that
  is accepted or why it cannot happen.
- **Why an owed push's retry ignores an answer file this machine already
  knew.** *The push order for a questions-branch answer* gives the reason:
  so that a file pushed at once does not cancel the push of an edited
  answer's file. No ruling records that reason; it is the author's
  inference, and Adam is to confirm it.
- **Why a replaced answer file still supersedes the older files in its
  hash group.** Under the spec's *A replaced answer file stops counting
  even in its own hash group*, such a file stops counting yet still
  supersedes the older files, which can leave the group with no answer
  that counts. *`answers` decides a named file's answer; the search groups
  by hash* gives why it stops counting; no ruling gives why it still
  supersedes.

### Where the spec and a decision differ

These are listed for Adam; the spec is not changed here.

- **spec-check's decisions-first rule**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:249-250, the spec's
  *A question another skill requires skips filters 2 to 4*), *Questions
  another skill requires skip filters 2 to 4*. The spec's scenario *A
  question another skill requires is not decided by the agent* still names
  spec-check's choice "whether to enforce its decisions-first rule" as an
  exempt question. spec-check removed that rule (shared-skills PR #44), and
  the decision lists no such question. The spec's mention is for Adam to
  remove.
- **A deferred question in a new issue that tags someone in another
  part** (openspec/changes/inquisitor/specs/inquisitor/spec.md:2014-2016,
  the spec's *Questions in posts pass the same filters*), *A deferred
  question passes only untagged and listed*. The decision: "a
  question in a new issue that tags no one". The spec: a question "that
  tags no one and is an item of an open-questions section or in a post
  that creates an issue". Under the spec, such a question passes in a new
  issue even when another part of the issue tags someone; read literally,
  the decision does not let it. *Questions in posts* follows the spec.
- **A private file in a readable directory**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:1884-1885, the
  spec's *The two calls' files and records stay private*), *Files passed
  to the two calls stay private*. The decision: the script
  "refuses a file readable by its group or others". The spec adds "or
  whose directory they can". An addition, not a contradiction.
- **Which questions go on standard input**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:3437-3438, the
  spec's *Some questions are recorded by hash only*), *Files passed to the
  two calls stay private*. The decision: "A question
  with a category reaches the script on standard input". The spec passes
  "it, its verdict and the rest of its picker call only on standard
  input". An addition, not a contradiction.
- **A gh read through an unset `$G`**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:364-366, the spec's
  *The reader reads posts sent through the github-app skill and gh api*,
  and its scenario *A gh read through an unset G is no post* at :415),
  *Posts sent through the github-app skill's script*.
  The decision: a command that runs `python3 $G`, "mentions `gh`" and
  assigns `G` nowhere earlier is unreadable. The spec: one that "mentions a
  gh post verb", with the scenario "A gh read through an unset G is no
  post". The spec lets a read through.
- **An unparseable GraphQL query**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:481-482, the spec's
  *The reader reads GraphQL posts and blocks a gh api write it can't
  read*), *GraphQL mutations that post text*. The decision: "A mutation the
  reader cannot
  parse ... is unreadable". The spec: "a query it cannot parse", read or
  mutation.
- **`gh` inside an unquoted word**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:242-243, the spec's
  *A line whose simple commands send no text is no post*), *Which commands
  the reader judges, and which are unreadable*. The decision: a
  data command "naming `gh` only inside a quoted argument". The spec:
  "with `gh` only inside a longer word that is not a path ending in
  `/gh`", which also covers an unquoted word.
- **Other git forms that run a command**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:243-244, the spec's
  *A line whose simple commands send no text is no post*, with its
  scenarios *A gh post run as inline code is unreadable* at :270 and *A git
  subcommand that runs a gh post is unreadable* at :290-296), *Code given
  on the command line that names gh*. The decision counts any git form that
  runs a command it is
  given, such as `git rebase -x`/`--exec`, `git submodule foreach` or `git
  bisect run`. The spec names those three forms and `-c` in its scenarios,
  and calls its set of forms that give code to run "fixed".
- **How a body is reduced before the reserved-prefix check**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2157-2158, the
  spec's *The post hook vets what the shared post reader returns*), *The
  post hook blocks a reserved prefix on GitHub*. The decision reduces the body
  as a comment is reduced for comparison with a recorded answer, which
  also drops list markers and ignores a leading `User says: `, so taken
  literally it would defeat the block. The spec reduces it "as a question
  in a post is for its hash", turning inline markup into its text and
  joining whitespace.
- **Which `CLAUDE.md` holds a way-of-working answer**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2657-2658, the
  spec's *A way-of-working answer goes to the person's memory, not a log*,
  with its scenario at :2663-2664, and :189 in *An agent records its own
  choice where the question's answer is recorded*), *A way-of-working
  question gets no log*. The decision:
  "the person's memory or `CLAUDE.md`". The spec: "that person's agent
  memory or user-level `CLAUDE.md`, never a committed one". The spec
  narrows the decision.
- **The scribe's records at `docs/decisions/`**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:706, the scenario
  *A proposed decision record is input* in *Filter 1 searches every place
  an answer is recorded*, and :1426, the scenario *The scribe's accepted
  record of a Discord answer is an answer*), *Filter 1 searches igor's
  scribe's records where #202 puts them*. The decision and the requirement
  text: "at the path igor PR #202
  sets". Two scenarios fix the path: "a decision record under
  `docs/decisions/`".
- **When #208 has applied no commit**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:579-582, the
  spec's *Under igor run, no relayed answer is known*), *An Igor reads
  relay files as of igor PR #208's applied commit*. The
  decision covers `igor run` "and ... a lore repository #208 never
  fetches", and says "An answer in the person's own comment still counts".
  The spec names only `igor run`, and says nothing of the person's own
  comment.
- **Who keeps the handback record**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2985-2986, the
  spec's *A later Igor run names the answered file only from the Igor's
  record*), *A later run names the answered file from the Igor's
  record*. The decision
  states the end state: "The record holds only the 6-hex-digit suffix and
  the date". The spec calls it the Igor's record "which igor PR #216 is
  asked to keep (#216's decision 59)". *What igor must provide* holds the
  request to #216.
- **What an incomplete configuration is**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:499-500, the
  spec's *Setup opens on an incomplete configuration and checks
  questions-branch commits*), *Setup is part of the answer session*. The
  decision: setup runs "when
  the `answer_session` section is missing or incomplete". The spec: "while
  `answer_session` is missing or no surface in it has both a `relay` and a
  subscription", so one complete surface beside an incomplete one opens no
  setup.
- **An answer file copying `asked_from`**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:1986-1987, the
  spec's *A questions-branch question is answered by a new log file*;
  openspec/changes/inquisitor/specs/inquisitor/spec.md:3106-3107, the
  spec's *A log file and a miss file have one format*, and its scenario *A
  file an Igor pushes names where it was asked from* at :3204-3208), *The
  Igor writes `asked_from` on every file it pushes*. The
  decision: the script "never writes `asked_from`, apart from the miss an
  answer session logs". The spec also has an answer file copy it:
  "copying its `asked_from` as a miss does" (answer-session :1986-1987) and
  "a miss or answer file an answer session logs" (inquisitor :3106-3107),
  and its scenario on where `asked_from` comes from (inquisitor
  :3204-3208) names both.
- **Where filter 1's recorded place comes from**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:2355-2357, the
  spec's *The person's filter 1 reply links the record they chose*), *Two
  reasons to decline*. The decision: "naming the place the person
  gave or the model found". The spec: "the place the person gave, or of
  one filter 1 found that they chose". The "model found" place may be the
  one Claude's draft fills in under *Claude drafts a reply only into the
  prompt box*.
- **An Igor log file whose link this machine never reads**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:957-958, the
  spec's *An Igor's log file follows its own handback comment*, with
  :918-920 in *A log file with no followed link is judged on its own* and
  its scenario at :934-935), *A link this machine never reads is not
  followed*. The
  decision has no exception. The spec: "An Igor's log file SHALL follow its
  link even on a machine that does not read its item". The exemption fits *Each Igor log file follows its own
  handback comment*, though no decision states it. The spec also adds a
  channel "this machine has off".
- **Which login an unknown post goes out as**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2263-2269, the
  scenario *An unknown posting login counts as the configured login* in
  *A question no candidate can decide turns to the session's login*), the
  bullet *Can the script learn which login a post goes out as?* above. The
  bullet: "it treats every post as
  going out as the person". The spec: "as the configured login". Probably
  the same login, in different words.
- **How an Igor's own run hands over its files**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:94-95, the spec's
  Purpose, and :779-786, *The script tells an Igor's run by IGOR_RUN*),
  the bullet *How an Igor runs the inquisitor skill itself*
  above, and *The script tells an Igor's run by `IGOR_RUN`*. The bullet
  calls "how the run hands its files to the Igor" open. The spec:
  "putting each file it would push in the run's report for the Igor to
  push". What is open may be only how the report reaches the Igor, which
  is #216's.
