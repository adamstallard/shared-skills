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
- **Either way,** igor passes the worker no marker that it runs inside an
  Igor, and no lore repository; it passes only the role's name (igor's
  `src/execute.ts`, line 163).

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

## Questions in posts

prose's posting hook already reads the body of a `gh` post from a short
allow-list of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an allow-list*
and *The posting hook's reach*).
That reader moves to `.agents/lib/gh-post/`, and both hooks call it. Its
rules are stated once, in this change's `gh-post` capability spec.
prose's tests must pass unchanged after the move, except where the reader
learns two more forms, and where it blocks inline code, as below. A post sent through the github-app skill's script,
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

The reader returns no title, so a question in an issue's or pull request's
title is outside its reach, as it is outside prose's. Whether such a
question should be vetted is Adam's to decide later, and the proposal's
*Still open* lists it.

A line ending in a colon whose text starts with "Open" begins an
open-questions section, as a heading does (proposal decision 176). Agents
often list their open questions under a plain "Open questions:" line, and
a deferred question listed there passes on its `deferred` verdict, as it
would under a heading. The cost: a line such as "Open a terminal and
run:" makes each list item after it a question that needs a verdict, and
Adam accepted that. Such a section, like any other, runs until the next
heading or bold label, so every list in between counts; whether a section
a colon line begins should end with its own list is in the proposal's
*Still open*.

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
  decision 178). igor PR #216 has yet to write these two rules, the
  question match and the matcher, into its spec.
  Filter 1, the search for an earlier answer, counts such a file as a
  decision only when GitHub gives that comment's author as the file's
  `answered_by` and the author has write access; otherwise it is input.
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
  `personal`): no log. Only the hooks' record above holds it, as a hash.
  During an Igor's run, the worker, the agent an Igor starts on a work
  item, raises a bare flag in its report: a mark, defined by igor PR #216,
  that the run met such a question, holding nothing else about it, not
  even the category. When the Igor reads that flag, #216's task-execution
  requirement *Transcripts and outcomes are captured to the state branch*
  has it write no transcript of the run, since a transcript would hold the
  question (proposal decision 136).

A log file's and a miss file's path, name, keys and encoding are stated
once, in the spec's requirement *A log file and a miss file have one
format* (proposal decisions 118 and 125). In short, a log file has YAML
frontmatter (`repository`, `asked`, `answered_by`, `authority`:
`decision`, `input` or `agent`, `recorded_in`, and `answer_link`, the
GitHub comment or review holding the answer, when there is one) and the
question and answer as its body. An `answer_link` is only ever a
github.com comment or review. An answer given on Discord, Slack or Linear
is logged as `input`. Filter 1 counts it as an answer only once it is
recorded in a decision document that the spec's *Only an answer with
authority stops a question* counts as an answer, such as one on the
default branch of the repository the question concerns. One such document is the `accepted` decision record written by
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
Inside an Igor whose role can't be read, the search shows only `global`
entries. A missing file means no lore repository, and filter 1's
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
its Igor posts (proposal decision 126). It asks there even if task 0.14
finds a `gh` login within its reach. A headless session that can post,
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
133). In an inquisitor run the Igor starts itself, with no worker, the
script runs that search; when it can't tell which lore repository the
Igor injects from, it searches none. In a worker, igor's command searches
that lore repository instead.

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
that lore repository is the one the search covers.

## The answer session

The answer session gives a person one place to answer the questions asked
of them on GitHub, Linear and Discord. A relay identity, a bot of the
person's own on each surface, posts each answer in the question's thread.
Its interface is a Claude Code mod that Adam approved by using its
prototype (proposal decision 152). By decision 147, a UI approved that way
is not specified, so nothing here describes how it looks.
The rules are in the `answer-session` spec, the decisions in proposal
decisions 152 to 175 and 184 to 203.

### Polling while open, with the person's credentials

A webhook needs a public HTTPS server, and Discord's push a permanent
connection: either is a service to run, which nothing else in this skill
needs. So the answer session polls, and only while it is open, about every
60 seconds, with a catch-up poll when it opens (decisions 157 and 158).
GitHub's notifications endpoint suits this: a conditional request that
finds nothing new is answered `304` without counting against the rate
limit, and the endpoint's `X-Poll-Interval` says how long to wait. A
mention subscribes the person to its thread, so a later reply there,
including a reply to the relay, arrives as a notification too. A mention of
the relay in a thread the person was never subscribed to would be missed;
task 0.15 measures what the endpoint reports, and until then the answer
session also reads each subscribed repository's comments.

Reading uses the person's own credentials on GitHub and Linear, and there a
relay identity only posts (decision 159). A relay's token then needs only
the right to post, and nothing the person reads is read under the bot's
name. On Discord a user account can't be automated within Discord's terms,
so one `discord-bot` identity, the relay, both reads and posts, in the
channels it has been added to (decision 185). Reading a message that
doesn't mention it needs Discord's privileged Message Content intent
(decision 191), which shared-skills PR #1's setup leaves off.

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
declines is closed in the state folder only (decision 194): nothing is
posted, so nothing in the thread can say so, and another machine shows it
as open. The thread is read
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

The answer session writes no log file for a question it relays. The asker
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
question.

A relayed answer counts as the person's own for filter 1 (decision 184).
Decision 78 proves a logged answer's writer only when GitHub gives the
linked comment's author as `answered_by`, and a relay post's author is
the relay identity, so without this a relayed answer would only be input,
and an Igor could never log a handback's relayed answer as a decision
(decision 149). If GitHub reports the App behind a comment and the
account that owns that App, which task 0.21 measures, a `User says: `
comment from an App the person owns is tied to the person as firmly as
the App is; until it is measured, a relayed answer is input. The tie
holds only because the prefix is reserved (decisions 193 and 203): an
agent holding the same App that posted `User says: ` by some way the post
hook does not see would forge the person's answer.
A relay post on Linear or Discord stays input, as any answer given off
GitHub does (decision 109).

### What the answer session does by itself

The answer session runs filter 1 on every incoming question, and judges
the rest by filters 2 to 4 (decisions 195 and 196), so the person sees
only what needs them. Posting without the person raises two risks, and
the spec answers each:

- **A thread's text reaches the model that judges it.** The model writes
  no word of an automatic post: an `Inquisitor: ` post is one of three
  fixed texts, and a recorded answer quotes a log file's answer line or
  points to filter 1's hit (decision 200). So a crafted question can at
  worst choose which canned reply or which record is posted, and a reply
  to an automatic post always goes to the person (decision 202), so no
  exchange runs on without them. Only an agent's
  question gets an `Inquisitor: ` reply, and a question counts as an
  agent's only when its author is a bot account (decision 199), so a
  person never gets a reply nobody wrote.
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the
  thread; otherwise the person sees it and decides (decision 200).

Every automatic post can be edited, and an edit makes it the person's
words, starting `User says: ` (decision 201).

The misses the answer session logs, when the person declines a question
that didn't need them or when filters 2 to 4 handle an agent's question,
go to the questions branch of the team's lore repository (decision 197).
The answer session can't see where the asker logged the question, which
is often an unmerged branch, and the questions branch takes a direct push,
so no miss needs a pull request. A miss against how the answer session
found a message that asks nothing has `filter: "source <n>"` (decision
198), so the review of misses finds it with the rest.

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
login. The prototype has
shown that a mod can fill the prompt box and register a tool the model
calls by name.

## Tracing scenarios to tests

Every scenario gets a tagged test before the change is archived, since
spec-trace's CI fails on an untagged one, and spec-trace's baseline
(`openspec/spec-trace-baseline.txt`), which lists exempt scenarios, takes no
new lines.
Where a scenario is about the script or a hook, the test runs it. Where it is
about what the agent does (asking through the picker, batching, handing a
question back, choosing a lesson's scope), the test checks that SKILL.md
states the rule, and the test's name says it checks SKILL.md.
