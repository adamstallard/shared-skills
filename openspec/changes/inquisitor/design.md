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
   (`vulnerability`, `secret` or `personal`) in this call. It then passes
   every question of that picker call, not only the categorized one, on
   standard input instead of in `q.json`, so the text is never written to
   a file that could be committed. Filter 1 then
   searches only files on the machine for it, the repository and the lore
   clones, and skips GitHub's issues.
2. `inquisitor.py vet --pass <token> --verdicts v.json` takes one verdict per
   question, with the field each verdict needs (a citation for `answered`,
   where the question will be listed for `deferred`, where the choice is
   recorded for `decided`, and the recommended option and what changes under
   the others for `ask`), and appends one record per question: the SHA-256
   of the question's text (as the spec defines it), the verdict, its field,
   and the time. For an `ask` on a picker question, the record keeps the
   field's account of what changes under the other options, and drops the
   recommended option's label: the recommendation is always the first
   option, as the second call checks. The label is question text, which no
   record holds. The cost is that no record names what the agent
   recommended, so nobody can check later from the records whether the
   person took the recommendation (proposal decision 130). The record of a question given a
   category holds the category in place of the field, so it holds no text at
   all.

Tokens and records live in `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`,
where prose keeps its session marks, and for the same reason: a session spans
repositories, and the hook's working directory can differ from the one `vet`
ran in (prose's DECISIONS.md, *The gate*). These records are the hooks'
state, not a question log: they hold no question's text, and whichever
call or hook next reads them deletes each one more than 2 hours old, with a
category or without one, except a `deferred` record without a category.
That one is kept until
a later verdict on the same text replaces it, because the post hook accepts
a deferral of any age: the post that lists it may be written days later. Nothing else keeps a record of a question with a
category; a vulnerability's lasting record is the repository's private
security advisory. Concurrent Igor workers (the AI teammates the igor
project runs) that share one HOME also share records, so one worker's
verdict on a question's text can let another worker ask the same text.
That is intended: a verdict is about the question's text, not the worker.
Per-clone records, as prose keeps its tokens, were rejected. Whether one
worker or several wrote the records, the picker hook allows a question only
while the latest verdict on its text is `ask`. The hash is plain SHA-256. A
short sensitive question could be guessed from its hash, but such a
question has a category, and every record with a category is deleted after
2 hours; only an uncategorized `deferred` record lives longer. So an HMAC
with a per-HOME key was rejected.

When a hook can't read these records, the picker hook lets the question
through and the post hook blocks a post that holds one. A picker question
publishes nothing, so at worst one unfiltered question reaches the person.
The post hook can't tell whether a question had a category, and a
published vulnerability can't be taken back.

The hook hashes each question in the tool's input the same way, reads the
most recent record for each hash, and allows the call when each is `ask` and
less than 2 hours old. The second call checks that a picker question's
first option is its recommendation. The hook doesn't need to check the
order of the options: a question's
text includes its options in order, so reordering them after vetting gives
a different hash, which the hook already blocks as unvetted. One line is
left out of the hash: the question's related-decision line, `Related: `
and a URL (proposal decision 112). The agent finds the related decision
in the first call's search, so it adds that line after the first call, and
adding it needs no second vetting. A record is not spent by the call: when
the hook blocks a call because of one question in it, the other questions need no
vetting again (proposal decision 181).

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

### What task 0.12 measured

**An Igor worker can't run this skill** (measured 2026-10-20), read
against igor's main branch and the branches of igor PRs #174 (pinned
skills), #175 (a worker as its own Unix user) and #216. The first bullet
below is measured from igor's code; the second is read from #174's and
#175's specs, since neither is built yet.
- **Today:** a worker's Bash permission is only its role's `commands`
  (igor's `src/execute.ts`, line 1607), so the skill's script runs only if a
  role lists it, and Read is refused outside the working tree. HOME is
  the home directory of the user the Igor runs as, so `inquisitor.json`
  and a `gh` login are there only if a developer set them up, as under
  `igor run` on their own machine, where `gh` would act as the person. Under `serve`, igor's deployment guide tells the
  operator not to log `gh` in as the service user, since a worker allowed
  to run `gh` could use that login (igor's `docs/deployment.md`, lines
  112 to 115); task 0.14 measures whether a worker can.
- **After #174 and #175:** skills load only from `/opt/igor/skills`, and
  #174's task 5.1 installs only prose, bug-hunter and spec-trace. The
  lore checkout is mode 0750, which the worker can't read (#175's
  `design.md`, line 189). The worker's home has no `inquisitor.json` and no
  `gh` login. Its settings come only from the user settings file igor
  writes for it (`--setting-sources user`), which is empty, so no hooks
  load. The run is headless, so there is no `AskUserQuestion`.
- **Either way,** igor passes the worker no lore repository. On igor's
  main branch it passes no marker that it runs inside an Igor either;
  igor PR #216 adds `IGOR_RUN` (proposal decision 235). What the worker
  is told comes from its system prompt, `workerSystemPrompt` (igor's
  `src/execute.ts`, line 161, at 8478aec): the role's name, the actions
  its run may take, the commands it may run, the role's standing
  instructions and the active lore entries the Igor injects. The Igor
  injects only the entries that fit the worker's token budget, so filter
  1 in a worker cannot rely on injected lore alone, and also calls
  `igor lore-search`.

So the spec's Igor-worker rules assume a worker with no inquisitor
configuration, no `gh` login or other GitHub credential, no picker and no
hooks, which can read only its working tree, its outbox and what its Igor
passes it. Adam then chose how the worker searches lore (proposal
decision 144): it calls a read-only search command igor provides, which
igor PR #216 specifies as `igor lore-search`. The worker passes the
question on standard input and no argument. The Igor tells which run and
role a request is for by the channel it arrives on, one that only that
run's worker can reach, so a worker can't ask on behalf of another run or
role. igor runs the search on its own lore checkout and `questions`
branch with the role's scope, so the worker needs no lore clone,
`inquisitor.json` or `gh`, and igor, not the worker, applies the scope
rules to lore entries and to question and miss files alike.

The script knows it runs in an Igor's run by the environment variable
`IGOR_RUN` (decision 235). igor PR #216's `task-execution` spec has igor
set it, holding no secret: to `worker` in a worker's environment, and to
`igor` when an Igor runs the inquisitor skill itself. igor does not set
it yet; task 0.9 checks it once igor builds it. In both runs the script
reads no lore clone and pushes nothing to a lore repository. Under
`worker`, filter 1's other sources, its decision documents, question log
and misses, are read only from the worker's working tree, and GitHub's
issues are reported as not searched, since a worker can read nothing
else.

The script matches the variable's exact name: igor PR #171 adds
`IGOR_RUN_TOKEN`, the token of a seat, the account igor lends a worker,
and a match on the prefix would take that for a run marker. It matches
the exact value too, so that any other value marks no run and leaves
the search as it is.

A repository could set `IGOR_RUN` in a person's session, through its
committed Claude Code settings or an `.envrc`. The script would then
search no lore and log nothing to a lore repository. Decision 239 has
the script's output say each time that it acts on
`IGOR_RUN`, so the person sees why. A plain headless session, such as
`claude -p`, has no such variable and searches lore as usual.

## Questions in posts

prose's posting hook already reads the body of a `gh` post from a short
allow-list of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an
allow-list*).
That reader moves to `.agents/lib/gh-post/`, and both hooks call it. Its
rules are stated once, in this change's `gh-post` capability spec.
prose's tests must pass unchanged after the move, except where the reader
learns two more forms, where it blocks a data command given code to run,
such as `python3 -c`, and where it reads a title, as below. A post sent through the github-app skill's script,
`python3 <github-app script> gh pr|issue …`, which that skill tells agents
to use instead of plain `gh`, is blocked as unreadable by prose's reader
today, so every post an agent sends as a GitHub App is refused. A comment
sent with `gh api`, whose body is given by `-f`, `--raw-field`, `-F` or
`--field` `body=`, or by `--input`, passes prose's reader unread today, so
it skips the hook. The shared reader reads both.

prose's reader treats `python3`, `node` and `git` as data commands, which
may name `gh` in a quoted argument, but each can run code given in the
command: `python3 -c`, `node -e`, and `git -c`, which can set an alias
that runs a shell command. So can `python3` reading its program from a
heredoc or a pipe. The shared reader reports such a command as unreadable when its
code names `gh`, as it reports `sh -c`. prose's hook calls the shared
reader, so it blocks such a command too, and a prose test that expects one
to pass changes with it (proposal decision 139).

The reader also returns a post's title, an issue's or a pull request's,
so a question in a title is vetted as one in the body is (proposal
decision 206). It reads a title only as a literal word, so a title built
by the shell, such as `--title "$(git log -1 --format=%s)"`, makes the
call unreadable, and prose's hook blocks it too. A title is now text a
command sends, and the reader reads a command that sends text only when
`gh` is the whole command line. So a title edit chained to another
command, such as `cd x && gh pr edit 3 --title 'Rename?'`, is unreadable
too, where prose's
`DECISIONS.md` has it pass (*The posting hook reads an allow-list*, its
paragraph "Titles are not checked"); task 1.3 updates that paragraph. Those are the changes prose's hook sees. A footer
can't go on a one-line title, so prose's hook checks only that the reader
can read a title, and lets a call with a title and no body through. A
title gets no prose pass: the inquisitor's post hook vets its questions,
and nothing else checks it (decision 217). `--fill` and its variants,
which take a title from commits, were already unreadable to prose's
reader, and stay so.

A plain or bold line ending in a colon begins an open-questions section,
as a heading does, but only when its label names questions, such as
"Open questions:" or "Questions:" (proposal decisions 176 and 204).
Agents often list their open questions under such a line, and a deferred
question listed there passes on its `deferred` verdict, as it would under
a heading. A line such as "Open a terminal and run:" names no questions,
so the commands listed after it need no verdicts. Only a heading or a
bold label ends a section, whatever began it, so every list up to the next
one counts, and a plain colon line inside a section ends nothing.

The inquisitor's post hook finds the body's questions by the spec's rule
(*Questions in posts pass the same filters*), hashes each, and applies the
picker hook's rule, with one addition: it also allows a `deferred`
question that tags no one, meaning it holds no `@login` mention. Such a
question passes in two places:
- as an item of an open-questions section, which includes a deferral
  section such as "Not in this change";
- anywhere in a new issue, which the shared post reader reports with the
  body.

Filter 2 has the agent list a deferred question in the work's description,
or file it as an issue, and both are posts (proposal decision 113). A
question that tags someone asks that person for an answer, so it needs an
`ask` verdict, however it was deferred. A post with no question passes without a lookup.

**The order with prose:** do prose's pass, vet the rewritten body, then sign
it with prose. The footer prose appends holds no question, so signing leaves
the body vetted. An edit after vetting means vetting again; an edit after
signing means signing again too.

A subagent returns its question to whoever started it, rather than opening
the picker itself: the session's person is talking to the agent that
started the subagent, which can batch the subagent's questions with its own.

A rhetorical question is found too. Nobody needs to choose an answer to it,
so filter 3 stops it, and the agent rewrites it as a statement. Its
`decided` verdict names the post as where the choice is recorded, since a
statement in the post is the whole of the choice.

## Where the logs live

**A question's log goes with what it concerns, at that place's privacy.**
The question is written for that privacy before it is asked (the spec's *A
question is written at the privacy of what it concerns*), so its log can sit
beside it.

- **A question about one repository:** a file under
  `.inquisitor/questions/` in that repository, committed with the work, so every agent on the team finds it, as
  spec-check's `openspec/spec-check.yaml` is found. When the question is
  about a repository other than the one holding the current work, the file
  goes to it by a pull request instead. The file is not kept on a branch of
  its own, because a question about a change belongs in that change's
  history and merges with it. A file on a branch or a pull request that has
  not merged is invisible to filter 1 elsewhere, so parallel work can ask
  the same question again; this change accepts that cost (proposal
  decision 130).
- **A question about an organization or project:** a file under
  `questions/` on an orphan branch named `questions` in the team's lore
  repository, separate from igor's
  `igor-state` branch, where igor keeps its runtime state (defined in
  igor's `src/state.ts`). The agent pushes each file
  there directly, with no pull request; when the push is rejected because
  the branch moved, it fetches and pushes again, and the random suffix
  means two pushes never write the same file. No review is needed, since a
  question's authority comes from who answered it, and the default branch
  stays readable, holding only the lore entries Igor gives agents. The
  files hold no `conditions`, so neither the search nor Igor reads one as a
  lore entry. Anyone who can push may write any `answered_by`, and GitHub's
  commit author login comes from the author email, which the committer
  sets. So a `decision` file there counts only when the file
  links the GitHub comment or review holding the answer, written by
  `answered_by`, or when the commit that added it carries a signature
  GitHub verifies for `answered_by`'s account. The agent commits from the
  person's session, so after a one-time signing setup the person never
  signs an answer by hand. A file there is never changed once pushed: an
  answer that comes later is a new file holding the question and the
  answer, and a file some later commit changed is input (proposal decision
  140). A proof made on the commit that added a file then covers
  everything the file says, which it would not if a later commit could
  rewrite the answer. An Igor worker holds no credential for the lore
  repository, so it pushes nothing there: the question, miss and
  `authority: agent` files it would push go in its report, and its Igor
  pushes them (proposal decision 142). igor PR #216's requirement *An Igor
  publishes the questions-branch files its worker reports* holds every rule
  for which files the Igor pushes, and when (proposal decisions 145, 149
  and 150). The only answered file the Igor accepts from a worker is one
  whose `answer_link` is a person's comment on the item the run works.
  The file's question must also match the question the Igor posted in
  its handback comment, the one the person's comment answers (proposal
  decision 179). Adam also decided that the Igor checks every file it
  pushes with igor PR #217's credential matcher, which also matches the
  values of known secrets such as the worker's seat token (proposal
  decision 178). igor PR #216 records both, the question match and the
  matcher, as its decisions 41 and 28.
  Filter 1, the search for an earlier answer, counts such a file as a
  decision only when GitHub gives that comment's author as the file's
  `answered_by`, or the comment is a relayed answer from `answered_by`'s
  relay App (decisions 184 and 216), and `answered_by` has write access;
  otherwise it is input.
  So a worker steered by text it read can't forge a person's answer. An answer worth giving agents as lore is promoted by a pull
  request to main adding a `provisional` entry; the question's file stays
  on its branch. Before pushing or promoting, the script checks
  visibility: nothing goes to a lore repository more visible than the
  repository the question concerns (for an organization question, the
  repository whose work raised it, by the spec's definition), ranking
  private, then internal, then public.
- **A question about one person's way of working:** no log. Its answer goes
  into that person's memory or `CLAUDE.md`, which agents already read.
- **A question in one of the three categories** (`vulnerability`, `secret`,
  `personal`): no log. Of this skill's records, only the hooks' record of
  the question, described in the bullet before last, holds it, as a hash.
  During an Igor's run, the worker, the agent an Igor starts on a work
  item, raises a flag in its report: a mark, defined by igor PR #216,
  that the run met such a question. The flag lists each category met in
  that worker run once, one word each, and marks the categories of the
  questions that stopped the worker (proposal decisions 244 and 245). igor then
  counts the run as flagged. It writes the category words, never a
  categorized question's text, into an operator-only file on its host,
  and moves the session logs, which hold the text, beside that file
  (igor PR #216's decisions 88, 89, 97 and 98). When the Igor reads that flag, #216's task-execution
  requirement *Transcripts and outcomes are captured to the state branch*
  has it write no transcript of the run, since a transcript would hold the
  question (proposal decision 136).

A log file's and a miss file's path, name, keys and encoding are stated
once, in the spec's requirement *A log file and a miss file have one
format* (proposal decisions 118 and 125). In short, a log file has YAML
frontmatter (`repository`, `asked`, `answered_by`, `authority`:
`decision`, `input` or `agent`, `recorded_in`, and `answer_link`, the
comment or review holding the answer, when there is one) and the
question and answer as its body. An `answer_link` is a github.com
comment or review, whose text the `log` command fetches and records, or
a Linear or Discord relay post's URL, which nothing fetches. The second
kind arises only when the answer session answers a questions-branch
question that was also asked in a Linear or Discord thread (proposal
decision 210): the file then records the text the session relayed
(proposal decision 248). A Linear or Discord link proves no writer,
since only GitHub tells a reader who wrote a comment. It is written only
when the lore repository is private, because its ids would otherwise
point readers outside a private workspace at it (proposal decision 251).
Such a file counts as a decision only when GitHub verifies a signature
for `answered_by` on the commit that added it, the same proof as for an
answer the person picks in Claude Code's picker and the agent logs from
their machine (proposal decision 250). An answer an agent reads on Discord, Slack or Linear itself
is logged as `input`. Filter 1 treats that answer as given only once a
decision document records it, of a kind the spec's *Only an answer with
authority stops a question* lists, such as one on the default branch of
the repository the question concerns. One such document is the `accepted` decision record written by
igor's scribe, the Igor role that writes a discussion's decisions down
(proposal decision 109). An agent's choice has `answered_by: agent`.

An answer logged as `input` goes only into the question's log file, never
into a decision document: on the current work's branch, a decision
document counts as an answer, so writing there an answer logged as input,
such as one from a person without write access, would turn input into a
decision (proposal decision 131). Log and miss files quote a question as
asked and a person's words exactly, so prose's pass skips files under
`.inquisitor/` (proposal decision 134). That skip ships with the skill at
gate two, since the skill writes such files from then on. The files on a lore repository's
`questions` branch need no such rule: that branch is never checked out,
so prose never sees them.

When filter 1 stops a question with a lore entry, the citation goes to that
lore repository's `questions` branch, as a file under `citations/` holding
the entry's id and the date. When an Igor pushes a citation from a run, it
adds the run's id, so that igor's review can show each citation's run and
item. With nothing about the question in it, a citation is written for a
private question too. A question in one of the categories, vulnerability,
secret or personal, gets none (decision 104), since the cited entry would
show what the question was about. Nor does a question about a repository
less visible than the lore repository (decision 93). Both the inquisitor and an Igor write
citation files, and igor's review reads them all, so the spec states their
format once, in the requirement *A citation file has one format*, and igor
PR #216 is to point to it rather than state a format of its own (decisions
110 and 111). During an Igor's run the agent pushes no citation itself.
A worker, the agent an Igor starts on a work item, is given only the token
of the seat its work is charged to, a credential for the model, which
cannot push to the lore repository. Task 0.14 measures whether a `gh`
login stored in the home directory the worker is given is usable by the
worker anyway. igor PR #216's requirement *An Igor
publishes the citations its worker reports* says how a worker reports its
citations, and which citations the Igor pushes, and when (proposal
decisions 123 and 129). The same rules cover the citations of an
inquisitor run the Igor starts itself, with no worker, when a question
stops its own work. The
inquisitor's commits to the `questions` branch are machine records with a
fixed message, `inquisitor: log <file>`, exempt from prose's and
bug-hunter's trailers; the branch is never checked out, so their checks
never see these commits. igor's planned review, which would prune
and promote lore entries, could count an entry's citations there, in one
place, beside its fire count, the number of times igor injected the entry
into a worker. That count is a lower bound, since no
citation is sent to a lore repository more visible than the question's,
and the review says so beside it. One case is worse than a low count:
when every citation push the Igors made in the review's period failed,
the branch holds only the citations people's own sessions pushed, and
every entry only Igors cited would show none. So in that case the review
shows citations as "not checked" instead of a count (proposal decision
180). A citation's commit names no person and
holds only the day, so it says nothing about who asked.

The 6 random hex digits in a question file's name mean two branches logging
the same question on the same day still write different files. Misses, the questions
a person said need not have been asked, go where their questions went, in
`misses/` in place of `questions/`, in the same format, with `filter` and
`said` in place of the answer keys (`answered_by`, `authority`,
`recorded_in` and `answer_link`).

Every log file and miss file is scanned for secrets before it is written,
and so is every question in a post at the first call. The patterns are the
common shapes of a credential, a closed list the spec states once as *the
credential patterns* (proposal decisions 99 and 138). A match refuses the write
or the post. The scan is a backstop: a secret under an arbitrary name, such
as a password in `DB_PASSWORD=…`, passes it. The files the agent passes to
`vet`, such as `q.json` and `v.json`, go outside any repository, so they
can't be committed. They go in a directory only the agent's user can
read, such as one `mktemp -d` makes, each with mode 0600, since every
user of a host can read a file left with the usual mode in a shared
temporary directory such as `/tmp`. The script refuses a file that its
group or others can read (proposal decision 182).

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

`path` is a local clone. The search reads the clone's remote-tracking default branch, such as
`origin/main`, with `git show`, never the working tree or a local branch, which could be on another branch or hold an
unreviewed edit. The skill fetches only the `questions` branch, so an
entry merged since the person last fetched the clone is not found
(proposal decision 130). It reads the `questions` branch with `git show`
too, without checking it out. For the date, the search
reads the reflog of the remote-tracking default branch, not `FETCH_HEAD`,
which the `questions` fetch rewrites. It reports when that default branch
was last updated by a fetch in this clone, so the date and the content
searched come from the same ref, or "unknown" for a clone with no such entry, such as a fresh one. It
is not when the branch last moved on GitHub, and a fetch that brings
nothing new writes no entry.
`owners` lists the GitHub owners whose repositories the lore repository
serves, and `repos` lists single repositories it serves; several lore
repositories may serve one owner. When an organization or project question
matches more than one, the most specific match (a named repository beats
an owner) wins, then the first listed, and the agent's report says which.
A missing `inquisitor.json` means no lore repository, and filter 1's
search says lore was not searched.

Reviewers live in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line. A team decides them
there, in review, so every teammate's agent tags the same person. #211
proposed "a reviewer or expert named in the team's configuration"; a
repository's own file is that configuration for questions about it.

Visibility, of a lore repository or the repository a question concerns, is
read with `gh repo view --json visibility` on the clone's `origin`, which
gives `PRIVATE`, `INTERNAL` or `PUBLIC`, ranked in that order. Write
access is read with `gh api repos/<owner>/<repo>/collaborators/<login>/permission`,
from `user.permissions.push`. Whether that call works for a caller without
push access is unmeasured (task 0.4). Each check fails closed:
- an unread visibility of the repository the question concerns counts as
  private;
- an unread visibility of a lore repository, or of a post's target, counts
  as public;
- an unread permission counts as no write access, so a question never tags
  a person who might be unable to decide it.

A log or miss file an Igor pushes also names, in `asked_from`, the
repository of the item the run worked (decision 221), whether its worker
reported the file or the Igor's own inquisitor run wrote it (decision
239). The worker, or the script in the Igor's own run, writes
`repository`, and the Igor writes `asked_from`. A
worker steered by its item's text could put a private repository's
details in a file whose `repository` names a public one, but
`asked_from` would still name the private one. Every reader judges the file by the more private of its two
repositories: igor's search does, and so do this change's own rules that
compare a file's visibility, such as the answer session's privacy check
before an automatic post and the refusal to promote a more private answer
into lore.

When none of decision 17's candidates (the approver of the related
decision, a listed reviewer, the last committer) has write access, the
script considers the person running the session, identified by the `login`
in the configuration. The script uses that login only when it equals the
account `gh` is logged in as, which it reads running as the person, so that
nobody can claim a maintainer's login by typing it into their own file.
The login itself comes from the configuration, not from `gh api user`
(decision 41): run with an App's token, `gh api user` gives no user. The
script's own `gh api user` runs with the person's own `gh` login, so it
returns the person; that is why it can confirm the configured login, and
also why it can't tell which login a post sent with the github-app
skill's token goes out as (task 0.7).

These are rules for the agent, which SKILL.md states; the script only
chooses whom a post tags. On a host with no picker, a session with a
person in it asks in its reply wherever these rules say the picker, once
the two calls have vetted the question (proposal decision 177). A headless session never uses the picker. An
Igor worker is given no
credential that can post, so it asks only in its handback comment, which
its Igor posts (proposal decision 126). The worker asks there even if
task 0.14 finds a `gh` login within its reach. When igor counts the run
as flagged, because its worker reported the flag described above or ended without a
completed report, the Igor posts a handoff that asks nothing. The Igor
keeps a record of the questions the run stopped on in a file on its own
host: the categories the flag marks, and the text of a stopped question
that has no category. The file's rules are igor PR #216's (its decision
97; proposal decisions 243 to 245). A headless session that can post,
such as a scheduled agent, tags the login only when the login has write
access and the post goes out as someone else, and otherwise tags no one. In a session with a person in it,
the script reads the configured login's write access with the same
permission call, and then:
- no login configured: the agent asks the question through the picker;
- write access, and the post would go out as that login, or the script
  can't tell which login it goes out as: the agent asks through the picker,
  because a self-tag sends no notification;
- write access, and the post goes out as anyone else, such as a GitHub App:
  the question tags the login;
- no write access: the question tags no one.

The search runs the same way in an Igor worker. igor injects every active
in-scope entry into a worker only while they fit its token budget, so an
entry holding a person's answer can be missing from the worker's context;
the search finds it. Inside an Igor it uses igor's own scope, the running
role's, from `scopeMatches`: `global`, `role:<role>`, and `project:`
matching any repository the role works. An entry out of scope is hidden,
never shown, since scope decides who may see an entry. Status is labelled,
not filtered: an in-scope entry that is not `active` is shown as input.
A question or miss file on a lore repository's `questions` branch is in
scope for every role whose Igor uses that lore repository, whatever
repository its `repository` key names (proposal decision 148). One
exception: during a run, igor's search hides a file about a repository
more private than the repository of the item the run works, such as a
file about a private repository from a run on a public one (proposal
decision 151). The worker could otherwise repost what it read into the
more public item. Both rules are #216's; the spec points to them. igor's lore-firing spec, which bans offering a worker a
search tool, is amended by igor PR #216 (decisions in igor issue #215) to
allow a search that applies firing's scope rule and labels status.
A worker reports a cited entry by its id alone, and the Igor checks that
id against the lore repository it injects from. If the search covered
another lore repository, an entry found there could be refused, or
counted as a different entry with the same id. So during a run the search
covers only the lore repository the Igor injects from (proposal decision
133). In a worker, and in an inquisitor run the Igor starts itself with
no worker, igor's command `igor lore-search` runs that search, as Adam
settled on igor PR #216 (decision 229). So the script never needs to
know which lore repository the Igor injects from. It matches plain text
and ranks hits as filter 1 does outside a run.

During a run, when the agent picks an id for a lore entry it would
propose, igor reports a clash with an id held outside the run's scope
only as "id taken". The report doesn't say what holds the id: an entry,
after which another id would do, or a rejection, which forbids proposing
the entry. So the agent proposes no lore entry during the run (proposal
decision 128).

The search reads each markdown file under the clone's `entries/` whose
frontmatter holds `conditions`, never one under `rejected/`, and matches the question's terms against `claim`,
`conditions.prose`, the `conditions.paths` globs and the body. It also reads
each file on the clone's `questions` branch, as it reads a repository's
`.inquisitor/questions/`. Outside an Igor, a `project:<name>` scope
matches the short name of the repository the question concerns. A
project whose repositories have other names would need a mapping, kept in
one file in the lore repository that igor and the inquisitor both read;
this change does not build it.
The igor project's own
configuration has a `destination` setting naming the directory of a lore
repository that holds its entries. Outside an Igor's run the search does
not use it, since a plain session has no Igor configuration; during a run,
igor's `lore-search` covers that lore repository. That repository also
holds the `questions` branch and the people's relay files (*What the
answer session posts, and what it logs* defines them), even when it is not
the repository holding the Igor's configuration (decision 237).

## The answer session

The answer session gives a person one place to answer the questions asked
of them on GitHub, Linear and Discord. A relay identity, a bot of the
person's own on each surface, posts each answer in the question's thread.
Its interface is a Claude Code mod that Adam approved by using its
prototype: build v0.1-30, tagged `answer-session-ui-approved-v0.1-30`
(proposal decisions 152 and 231), and build v0.1-33, which descends from
it and adds the thread's replies and filter 1's recorded answer, tagged
`answer-session-ui-approved-v0.1-33` (proposal decision 263). The mod is
built from v0.1-33 alone. By decision 147, a UI approved that way
is not specified, so nothing here describes how it looks. The spec
governs what the UI does and posts, and where v0.1-33 does otherwise,
the spec wins, and screens the spec
needs that v0.1-33 lacks follow its patterns (proposal decision
254, task 6.1).
The rules are in the `answer-session` spec, the decisions in proposal
decisions 152 to 175, 184 to 203, 207 to 211, 215, 216, 219, 220,
222 to 230, 234, 236, 238, 246 to 248, 250 to 252, 254 to 260 and 262 to 269.

### Polling while open, with the person's credentials

A webhook needs a public HTTPS server, and Discord's push a permanent
connection: either is a service to run, which nothing else in this skill
needs. So the answer session polls, and only while it is open, about every
60 seconds, with a catch-up poll when it opens (decisions 157 and 158).
GitHub's documentation says its notifications endpoint suits this, and
task 0.15 checks that the endpoint behaves as documented: a conditional
request that finds nothing new is answered `304` without counting against
the rate limit, the endpoint's `X-Poll-Interval` says how long to wait,
and a mention subscribes the person to its thread, so a later reply
there, including a reply to the relay, arrives as a notification too. A mention of
the relay in a thread the person was never subscribed to would be missed;
until task 0.15 shows the endpoint reports such a mention, the answer
session also reads the comments of each repository in its
subscriptions.

Reading uses the person's own credentials on GitHub and Linear, and there a
relay identity only posts (decision 159). A relay's token then needs only
the right to post, and nothing the person reads is read under the bot's
name. On Discord a user account can't be automated within Discord's terms,
so one `discord-bot` identity, the relay, both reads and posts, in the
channels it has been added to (decision 185). Reading a message that
doesn't mention it needs Discord's privileged Message Content intent
(decision 191). discord-bot's setup, in shared-skills PR #1, has the
person turn that intent on for the bot (commit 369ae16), and its `check` command reports
`messageContent` as true, false or null, read from the bot's application
flags (f83b167). Setup's check of message content passes only when
`check` reports true (decision 238); false fails, and so does null,
which means `check` could not read the flags (decision 239's item 7).
discord-bot turns each `@name` in a post into a mention that notifies
that member, and the relay keeps that on: an `@name` in the person's
own answer pings that person, as it would in a comment of their own
(decision 246). Rewriting was once to be turned off because a relay post
quoted a recorded answer, whose @-mentions would have notified people a
second time. A relay post no longer quotes a recorded answer: it links
to the record instead (decision 239's item 5).

A relay identity may do other work, but only the answer session starts a
post with one of the four reserved prefixes (decision 193). Anything that
holds the relay identity could post `User says: `, which marks a question
answered on every machine and, on GitHub, counts as the person's own
answer to filter 1. The skill's instructions reserve the prefixes. On
GitHub the inquisitor's post hook blocks a tool-call post that starts with
one (decision 203), which never blocks the answer session, whose posts
reach no tool hook. Nothing enforces it on Linear or Discord.

### The thread is the record

An answer's record is the relay's post in the question's thread, not
anything on the machine (decision 160). The thread is the one place every
machine, and the asker, can read. A crash between a successful post and the
write of its id to local state loses nothing: the next read of the thread
finds the post and marks the question answered. A post that asks the asker
starts with `User asks: ` instead of `User says: ` (decision 171), so
"waiting for the asker" can be read from the thread too. The two prefixes
of the posts the answer session makes by itself, `Recorded answer: ` and
`Inquisitor: `, mark a question answered or handled for the person, the
same way, on every machine (decisions 195 and 196). A question the person
declines with nothing posted is closed in the state folder only (decision
194): nothing in the thread can say so, and another machine shows it as
open. A question declined because the inquisitor should have handled it,
reason 3, gets a post, which the thread records like any other (decision
209). It gets none only when it has no thread or has a category. With a
filter 1 record more private than its thread, it is posted only once the
person confirms after a warning that posting shows the record exists
(proposal decision 264). The thread is read
again before a question is shown, when its poll is over a minute old, and
before each post, so an answer relayed from another machine is never posted
twice.

### Local state, one writer per machine

The state folder holds working state only: what the person set aside for
later, discussion records, poll positions, relay checks, post ids and the
question on screen (decision 161). Decision 32 rules out a personal
question log: a copy of a question's record kept where only one person
would find it, instead of with what the question concerns. The state folder replaces
no such record: the asker's log file and the thread stay the records, and
filter 1 never reads the folder. It does hold each discussed question's
text under the home directory, but only while the question is open: a
discussion record is deleted once its question is answered or closed
(decisions 190 and 202), so it never becomes a record. Adam ruled that
decision 161 does not amend 32 on that condition. It is kept per
machine; a question set aside on one machine shows as new on another,
which costs a second look and nothing else.

One answer session runs per machine, under a lock in the state folder that
its holder refreshes (decision 162). A holder that crashes stops
refreshing, and its lock goes stale after 2 minutes. Before each poll and
each post the holder checks that the lock still holds its session id, so a
session that was taken over posts nothing more. The name alone would not
do, since every session the `answer` command starts is named `Answers`.

**No TLA+ model** (decision 162). Adam's rule asks for one where several
processes share state, and the lock is the only place that happens here.
One person uses the answer session, the lock makes one session per machine
the only writer of that machine's state, and the shared state across
machines is the threads, which each write appends to and each read
re-fetches. The interleavings left are two sessions racing for the lock,
which an atomic create or replace settles, and a take-over during a post,
which the check before each post settles.

### What the answer session posts, and what it logs

A relay post holds the person's own words, so neither prose's pass nor the
inquisitor's filters apply to it (decision 170). The mod runs the relay
identity's skill as a command on the host, with its own process call
rather than a tool call of the session's model, and prose's posting hook
and the inquisitor's post hook act only on tool calls. Task 0.18 measures that no hook sees such a command. The
person's answer, and a draft built from a thread's untrusted text, reach
that command, so it runs as an argument vector with no shell, with the
post's text in a file or on standard input. Since no hook reads a relay
post, the answer session scans it for the credential patterns itself.
A relay post names the question it answers, by replying to it or by a last
line `Re: <URL>` (decision 175's item 8), so a thread holding several
questions keeps a state for each.

The answer session writes no log file for a question it relays, except
for a question a questions-branch file also holds, below. The asker
logged the question when it asked, often on a branch not yet merged, and
records the answer when it reads the relay's post. When the asker is a
person, or an agent that keeps no log, nothing logs the answer, and the
thread is its only record. A rephrased answer's
post gives the rephrased question and the one-sentence summary on lines of
their own, and the asker adds them to its log file as two body sections
(decisions 163 and 172). Body sections, not frontmatter keys, hold them,
since every frontmatter value is one quoted line.

A question from a lore repository's questions branch has no thread to
relay to, so the answer session answers it by pushing a new log file to
that branch, as any session does for an answer the person gave in it
(decision 173). Asking the asker and editing are not offered for such a
question. When the same question was also asked in a post, the answer
session shows it from the thread, relays the answer there, and pushes the
log file too (decision 210), so neither the asker reading the thread nor
an agent searching the branch misses the answer. When the person, rather
than answering in their own words, agrees to the recorded answer shown
beside the question, no log file is pushed (decision 266). An agent that
searches later is then stopped by that record only when its own filter
1 can read the record and counts it as an answer; otherwise it sees the
question as unanswered.

A relayed answer counts as the person's own for filter 1 (decision 184).
Decision 78 proves a logged answer's writer only when GitHub gives the
linked comment's author as `answered_by`, and a relay post's author is
the relay identity, so without this a relayed answer would only be input,
and an Igor could never log a handback's relayed answer as a decision
(decision 149). Only an App listed in the person's own relay file,
`relays/<login>.yaml` on the default branch of the team's lore
repository, ties a
`User says: ` comment to them (decisions 216 and 224). Owning the App is not
enough: an Igor's App owned by the same person posts its worker's text
through igor's own code, which no post hook sees. A worker steered by its
item could start such a comment `User says: `, and a `decision` file
linking it would then pass the writer proof and count as the person's
answer. A reader recognises an Igor's App by its slug: igor requires
every Igor's App slug to start with `igor-`, and an Igor whose slug lacks
it refuses to start (igor PR #216's decision 62), so no relay-file entry
whose slug starts with `igor-` counts (decision 232). A reader of a
relay file cannot look the App up in igor's configuration instead: that
configuration names no App (decision 230's item 4), so the slug is the
only mark left.

The file is tied to its person by who last changed it, not by review
(decision 225). A reader counts it only when the newest commit that
changed it came from a merged pull request the person authored, or carries
a signature GitHub verifies for them; otherwise it lists no relay. So
anyone who can push to the lore repository can stop a person's relayed
answers from counting, but cannot make another App speak for them. A
notice workflow, `relay-notice.yml`, which this skill ships for the lore
repository and which is modelled on igor's seat-notice workflow (igor PR
#171), @-mentions the person on any pull request that changes their file, when
the base branch holds it or the person opened the pull request, so a
pull request adding a file for someone else can't make it mention them. No reader depends on it. It tells the person when their file is about to
stop counting. It also tells them when someone else pushes to their own
open pull request: that push would count as the person's once the pull
request merges, a cost decision 227 accepts. One file per person follows igor's `seats/<id>.yaml`:
the person's own pull request adds it, and a path, unlike a key in a shared
file, names whose it is.

The tie still holds only because the prefix is reserved (decisions 193 and 203): an agent holding a listed App
that posted `User says: ` by some way the post hook does not see would
forge the person's answer, so a person lists only an App nothing else
posts through unseen. github-app's `token` command prints an App's token
to any agent on the machine, which could then post with a plain HTTP call
no hook sees. Adam decided that github-app is to let a person mark an
identity as a relay and then refuse `token` for it, so that only its own
posting command, which the post hook reads, can use it (decision 233).
That is a separate change to github-app, not yet written; until it ships,
the cost is accepted and the README says so. Task 0.21 measures whether GitHub reports which App
wrote a comment. Until that measurement shows it does, a relayed answer
is input, and if it shows GitHub does not, no comment is ever a relayed
answer. A relay post on
Linear or Discord that an agent reads stays input, as any answer typed
off GitHub does (decision 109). The answer session also logs an answer
it relayed on Linear or Discord, when the question is on a questions
branch, and that log file can count as a decision through its commit's
signature (decision 250).

The file is YAML under `relays/` in the lore repository, the one holding
the entries, with one list per surface. Where igor PR #208's
`destination` points away from the repository holding igor's
configuration, the relay files and the `questions` branch are in the
destination repository, beside the entries (decision 237, igor PR #216's
decision 66). An Igor reads them as of the last commit igor PR #208's
lore read applied. #208 refuses a commit that fails igor's startup
checks, so the relay files of a refused commit never count (decision
241). `igor run` never fetches, so there #208 has applied no commit: the
Igor cannot tell whether a `User says: ` comment came from a listed relay
App, and pushes such an answer as `input`, while an answer in the
person's own comment still counts (decision 242).
Only the `github` list proves anything; nothing in this change reads the
`linear` and `discord` lists, which record in the same place which
identities post for the person there. YAML matches the lore repository's
other configuration. It is not a key of `igor.config.yaml`, which refuses
any key igor does not read, and the inquisitor's own `inquisitor.json` is
per person and on their machine, where no other reader sees it.

When the person edits a relayed answer that decision 210 also logged on a
questions branch, the answer session pushes a new log file with the edited
answer, since a file there never changes (decision 140), and the newest
answered file for a question counts (decision 220). Newest means newest
by proof, which for a comment link is the comment's last edit, and for a
signature the signed commit's date (decision 222's item 1). Ordering by proof, not by branch history, keeps anyone with
push access from re-pushing an older proven file to revert a newer
answer.

### What the answer session does by itself

The answer session runs filter 1 on every incoming question, and judges
the rest by filters 2 to 4 (decisions 195 and 196), so the person sees
only what needs them. Posting without the person raises two risks, and
the spec answers each:

- **A thread's text reaches the model that judges it.** The model writes
  no word of an automatic post: an `Inquisitor: ` post is one of three
  fixed texts, and a recorded answer only points to filter 1's hit and
  quotes nothing from it (decision 200's item 1, as decision 239's item 5
  amends it). So a crafted question can at
  worst choose which canned reply or which record is posted. Filter 3's
  and 4's replies tell the asking agent to decide the question, and
  filter 2's only to defer it, so that choice would still decide a
  question if the asking agent acted on any reply. The asking agent
  therefore acts by itself only on filter 2's reply. It acts on filter
  3's or 4's only when the person chose that reply under decline reason 3,
  which the reply's last line says, and which the answer session never
  posts by itself (decision 234). When an
  agent replies to an automatic post, the answer session judges the reply
  again. A chain of replies runs from a reply back through the relay post
  it replies to, the question that relay post names (on GitHub, by its
  `Re: ` line), and so on to the first question. If the automatic post it
  would make has the same text as any automatic post already made in that
  chain, it posts nothing
  and shows the reply to the person (decision 219), so an agent that keeps
  replying can't get filter 2's text, then filter 4's, then filter 2's
  again with no person seeing the exchange. A recorded answer is posted by itself
  for a person's question as for an agent's (decision 195). Only an
  agent's question gets an `Inquisitor: ` reply by itself, and a question
  counts as an agent's only when its author is a bot account (decision
  199), so a person never gets a reply nobody wrote. A `User says: ` or
  `User asks: ` post from any bot is a relayed question: the words of
  the person whose answer session posted it, such as another person
  asking this one something through their own relay, so it counts as a
  person's question (decisions 222 and 223): filter 1 can answer it by itself from
  a record, and filters 2 to 4 only suggest a verdict to the person. When the person declines a
  question because the inquisitor should have handled it, decline reason
  3, they can choose an `Inquisitor: ` or `Recorded answer: ` post for any
  question, and see the exact post before it goes out (decision 209).
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the
  thread; otherwise the person sees it and decides (decision 200).

Every automatic post can be edited, and an edit makes it the person's
words, starting `User says: ` (decision 201).

The misses the answer session logs, when the person declines a question
the inquisitor should have handled or when a filter handles an agent's
question by itself, go to the questions branch of the team's lore
repository (decisions 197, 207 and 209).
The answer session can't see where the asker logged the question, which
is often an unmerged branch, and the questions branch takes a direct push,
so no miss needs a pull request. When the person declines a message
picked up by mistake, the miss is against the source of questions that
found it: `filter: "source <n>"`, where `<n>` is that source's number, and
`said: "not a question"` (decisions 198 and 208). The review of misses
finds it with the rest.

### The session's model

A discussion runs in the session's own conversation (decision 167), so the
model has its tools and can read the question's thread, the code and the
specs before it replies. Each message carries the question as context. The
model may ask the person in its reply there (decision 174), the one
exception to the rule that an agent asks only through the picker: the
person opened the conversation to talk the question through, and a picker
would hide the answer session's screen. The model posts nothing: its draft goes
through `propose_reply` into the prompt box (decision 168), and the person
relays it. No hook enforces that the model posts and changes nothing; the
context tells it, and the post hooks still vet any post it tries. The
model's tools can reach what the person's own commands can, the keychain
holding the Linear key included, as in any session. The answer session
adds no guard against that: it is the same exposure as the person's `gh`
login, and Adam accepted it (decision 211). The prototype has
shown that a mod can fill the prompt box and register a tool the model
calls by name.

## Tracing scenarios to tests

Every scenario but the expected gaps below gets a tagged test, since
spec-trace's CI fails on an untagged scenario in `openspec/specs/`,
where archiving this change writes its scenarios, and spec-trace's baseline
(`openspec/spec-trace-baseline.txt`), which lists exempt scenarios, takes no
new lines.
Where a scenario is about the script or a hook, the test runs it. Where it is
about what the agent does (asking through the picker, batching, handing a
question back, choosing a lesson's scope), the test checks that SKILL.md
states the rule, and the test's name says it checks SKILL.md.

**Expected gaps.** A scenario that only igor's unbuilt work, such as
`igor lore-search`, can make pass gets no tagged test until igor builds
it, so spec-trace shows it as uncovered (proposal decision 249). A
skipped test would not do: spec-trace counts a skipped test's tag as
coverage. Gate two, the implementation that follows approval of this
spec on the same branch, lists each such scenario in this section by
name when it writes the tests, and task 4.3 tags it once igor provides
what it needs. Until the change is archived, its scenarios sit outside
`openspec/specs/`, so CI passes. Archiving it while any gap is untagged
would fail CI, so the change is archived only after task 4.3 has tagged
every gap (proposal decision 253).
