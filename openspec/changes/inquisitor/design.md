Adam (adamstallard) owns this repository and decides this change. Terms
such as Igor, the picker, the two calls, a verdict and the answer session
are defined in *Terms used throughout*, after the introduction to
*Decisions*.

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
   a file that could be committed. For the question with the category,
   filter 1 searches only files on the machine, the repository and the
   lore clones, and skips GitHub's issues; the call's other questions are
   searched as usual.
2. `inquisitor.py vet --pass <token> --verdicts v.json` takes one
   verdict per question, with the field each verdict needs (a citation
   for `answered`, where the question will be listed for `deferred`,
   where the choice is recorded for `decided`, and the recommended
   option and what changes under the others for `ask`), and appends one
   record per question: the SHA-256 of the question's text (as the spec
   defines it), the verdict, its field, and the time. For an `ask` on a
   picker question, the record drops the recommended option's label: an
   option's label is part of the question's text, which no record holds,
   and the recommendation is always the first option, as the second call
   checks. The record keeps the field's account of what changes under the
   other options, since that account is the agent's own words, given in
   the verdict, not part of the question's text. The cost
   is that no record names what the agent recommended, so nobody can
   check later from the records whether the person took the
   recommendation (*An `ask` record drops the option's label*, under
   *Decisions*). The record of a question given a category holds the
   category in place of the field, so it holds no text at all.

Tokens and records live in `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`,
where prose keeps its session marks, and for the same reason: a session spans
repositories, and the hook's working directory can differ from the one `vet`
ran in (prose's DECISIONS.md, *The gate blocks a session's first file
write*). These records are the hooks' state, not a question log: they
hold no question's text, and whichever
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

The hook hashes each question in the tool's input the same way, reads
the most recent record for each hash, and allows the call when each is
`ask` and less than 2 hours old. The hook doesn't check the order of a
question's options. The second call has already checked that a picker
question's first option is its recommendation, and a question's text
includes its options in order, so reordering them after vetting gives a
different hash, which the hook already blocks as unvetted. One line is
left out of the hash: the question's related-decision line, `Related: `
and a URL on a line of its own after the question's first line. In a
picker question, that line is one of the `question` field's lines
(*The related-decision line is left out of the hash*, under
*Decisions*). The agent finds the related decision in the first call's
search, so it adds that line after the first call, and adding it needs no
second vetting. A record is not spent by the call: when the hook blocks a
call because of one question in it, the other questions need no vetting
again (*A hook spends no verdict record*, under *Decisions*).

**Rejected:**

- **A signed footer in the question,** as prose signs a post. The person
  reads the question in the picker, and a hash in it is noise to them.
- **The hook running the filters itself.** A hook is a script with no model,
  so it can't tell whether two options both have merit.
- **The skill's description alone,** with no hook. A model decides by
  judgement whether to load a skill, which is why the decision *A picker
  hook makes agents run the filters* asks for a hook.
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
  (igor's `src/execute.ts`, line 1607, at 8478aec), so the skill's script runs only if a
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
  igor PR #216 adds `IGOR_RUN` (*The script tells an Igor's run by
  `IGOR_RUN`*, under *Decisions*). What the worker is told comes from
  its system prompt, `workerSystemPrompt` (igor's `src/execute.ts`, line
  161, at 8478aec): the role's name, the actions its run may take, the
  commands it may run, the role's standing instructions and the active
  lore entries the Igor injects. The Igor injects only the entries that
  fit the worker's token budget, so injected lore alone is not enough for
  filter 1. That is why, in Igor-worker mode as the spec defines it,
  filter 1 also calls `igor lore-search`, as below.

So the spec's Igor-worker rules assume a worker with no inquisitor
configuration, no `gh` login or other GitHub credential, no picker and
no hooks. It can read only its working tree, its outbox and what its
Igor passes it. The outbox is a place a worker reports to its Igor
through, besides its output; igor PR #175 chooses between the two
(*igor PR #216 holds every rule for a run's citations*, under
*Decisions*). Adam then chose how the worker searches lore (*Filter 1
in an Igor's run searches through `igor lore-search`*, under
*Decisions*): it calls a read-only search command igor provides, which
igor PR #216 specifies as `igor lore-search`. The worker passes the
question on standard input and no argument. The Igor tells which run and
role a request is for by the connection it arrives on, one that only that
run's worker can reach, so a worker can't ask on behalf of another run
or role. igor runs the search on its own lore checkout and `questions`
branch with the role's scope, so the worker needs no lore clone,
`inquisitor.json` or `gh`, and igor, not the worker, applies the scope
rules to lore entries and to question and miss files alike.

The script knows it runs in an Igor's run by the environment variable
`IGOR_RUN` (*The script tells an Igor's run by `IGOR_RUN`*, under
*Decisions*). igor PR #216's `task-execution` spec has igor set it,
holding no secret: to `worker` in a worker's environment, and to `igor`
when an Igor runs the inquisitor skill itself. igor does not set it yet;
task 0.9 checks it once igor builds it. In both runs the script reads no
lore clone and pushes nothing to a lore repository. Under `worker`,
filter 1's other sources, its decision documents, question log and
misses, are read only from the worker's working tree, and GitHub's
issues are reported as not searched, since a worker can read nothing
else.

The script matches the variable's exact name: igor PR #171 adds
`IGOR_RUN_TOKEN`, the token of a seat, the account igor lends a worker,
and a match on the prefix would take that for a run marker. It matches
the exact value too, so that any other value marks no run and leaves
the search as it is.

A repository could set `IGOR_RUN` in a person's session, through its
committed Claude Code settings or an `.envrc`. The script would then
search no lore and log nothing to a lore repository. The decision *The
script tells an Igor's run by `IGOR_RUN`* has the script's output say
each time that it acts on `IGOR_RUN`, so the person sees why. A plain
headless session, such as `claude -p`, has no such variable and searches
lore as usual.

## Questions in posts

prose's posting hook already reads the body of a `gh` post from a short
allow-list of command forms, and the body fields of GitHub MCP tools
(`.agents/skills/prose/DECISIONS.md`, *The posting hook reads an
allow-list*).
That reader moves to `.agents/lib/gh-post/`, and both hooks call it. Its
rules are stated once, in this change's `gh-post` capability spec.
prose's tests must pass unchanged after the move, except in three places,
each described below:
- the reader learns two more forms of post;
- it blocks a data command given code to run, such as `python3 -c`;
- it reads a title.

The two new forms are these. A post sent through the github-app skill's
script, `python3 <github-app script> gh pr|issue …`, which that skill tells
agents to use instead of plain `gh`, is blocked as unreadable by prose's
reader today, so every post an agent sends as a GitHub App is refused. A
comment sent with `gh api`, whose body is given by `-f`, `--raw-field`,
`-F` or `--field` `body=`, or by `--input`, passes prose's reader unread
today, so it skips the hook. The shared reader reads both.

prose's reader treats `python3`, `node` and `git` as data commands,
which may name `gh` in a quoted argument, but each can run code given in
the command: `python3 -c`, `node -e`, and `git -c`, which can set an
alias that runs a shell command. So can `python3` reading its program
from a heredoc or a pipe. The shared reader reports such a command as
unreadable when its code names `gh`, as it reports `sh -c`. prose's hook
calls the shared reader, so it blocks such a command too, and a prose
test that expects one to pass changes with it (*Code given on the
command line that names gh*, under *Decisions*).

The reader also returns a post's title, an issue's or a pull request's,
so a question in a title is vetted as one in the body is (*A post's
title is read and vetted*, under *Decisions*). It reads a title only as
a literal word, so a title built by the shell, such as
`--title "$(git log -1 --format=%s)"`, makes the call unreadable, and
prose's hook blocks it too. The reader reads a command that sends text
only when `gh` is the whole command line, and a title now counts as text
the command sends. So a title edit chained to another command, such as
`cd x && gh pr edit 3 --title 'Rename?'`, is unreadable too, where
prose's `DECISIONS.md` has it pass (*The posting hook reads an
allow-list*, its paragraph "Titles are not checked"); task 1.3 updates
that paragraph. Those are the changes prose's hook sees. A footer can't
go on a one-line title, so prose's hook checks only that the reader can
read a title, and lets a call with a title and no body through. A title
gets no prose pass: the inquisitor's post hook vets its questions, and
nothing else checks it (*A post's title is read and vetted*, under
*Decisions*). `--fill` and its variants, which take a title from
commits, were already unreadable to prose's reader, and stay so.

A plain or bold line ending in a colon begins an open-questions section,
as a heading does, but only when its label names questions, such as
"Open questions:" or "Questions:" (*What counts as a question in a
post*, under *Decisions*). Agents often list their open questions under
such a line, and a deferred question listed there passes on its
`deferred` verdict, as it would under a heading. A line such as "Open a
terminal and run:" names no questions and begins no section, so outside
an open-questions section the commands listed after it need no verdicts.

A section ends only at the next heading or bold label, whatever began it.
A bold label is a line whose whole text, apart from a trailing colon, is
bold. Every list up to that end counts. A plain colon line inside a
section ends nothing, so a list after "Open a terminal and run:" inside
an open-questions section is still in that section.

The inquisitor's post hook finds the body's questions by the spec's rule (*A
question in a post is a listed item or a sentence ending in a question mark*),
hashes each, and applies the
picker hook's rule, with one addition: it also allows a `deferred`
question that tags no one, meaning it holds no `@login` mention. Such a
question passes in two places:
- as an item of an open-questions section, which includes a deferral
  section such as "Not in this change";
- anywhere in a new issue, which the shared post reader reports with the
  body.

Filter 2 has the agent list a deferred question in the work's
description, or file it as an issue, and both are posts (*What counts as
a question in a post*; *A deferred question passes only untagged and
listed*, under *Decisions*). A question that tags someone asks that
person for an answer, so it needs an `ask` verdict, however it was
deferred. A post with no question passes without a lookup.

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
  `.inquisitor/questions/` in that repository, committed with the work,
  so every agent on the team finds it, as `openspec/config.yaml` is
  found. When the question is about a repository other than the one
  holding the current work, the file goes to it by a pull request
  instead. The file is not kept on a branch of its own, because a
  question about a change belongs in that change's history and merges
  with it. A file on a branch or a pull request that has not merged is
  invisible to filter 1 elsewhere, so parallel work can ask the same
  question again; this change accepts that cost (*A repository's
  questions are committed with the work*, under *Decisions*).
- **A question about an organization or project:** a file under
  `questions/` on an orphan branch named `questions` in the team's lore
  repository, separate from igor's `igor-state` branch, where igor keeps
  its runtime state (defined in igor's `src/state.ts`). The agent pushes
  each file there directly, with no pull request; when the push is
  rejected because the branch moved, it fetches and pushes again. Each
  file's name holds 6 random hex digits, so two pushes never write the
  same file. No review is needed, since a question's authority comes
  from who answered it. The default branch stays uncluttered: it holds
  only the lore entries Igor gives agents. The files hold no
  `conditions`, so neither the search nor Igor reads one as a lore
  entry. Anyone who can push may
  write any `answered_by`, and GitHub's commit author login comes from
  the author email, which the committer sets. So a `decision` file there
  counts only when the file links the GitHub comment or review holding
  the answer, written by `answered_by`, or when the commit that added it
  carries a signature GitHub verifies for `answered_by`'s account. The
  agent commits from the person's session, so after a one-time signing
  setup the person never signs an answer by hand. A file there is never
  changed once pushed: an answer that comes later is a new file holding
  the question and the answer, and a file some later commit changed is
  input (*No file on a questions branch changes once pushed*, under
  *Decisions*). A proof made on the commit that added a file then covers
  everything the file says, which it would not if a later commit could
  rewrite the answer. An Igor worker holds no credential for the lore
  repository, so it pushes nothing there: the question, miss and
  `authority: agent` files it would push go in its report, and its Igor
  pushes them (*The Igor pushes the questions-branch files its worker
  reports*, under *Decisions*). igor PR #216's requirement *An Igor
  publishes the questions-branch files its worker reports* holds every
  rule for which files the Igor pushes, and when (*The Igor pushes the
  questions-branch files its worker reports*; *A person's answer to a
  handback*; *A flagged run asks nothing and pushes nothing*, under
  *Decisions*). The only answered file the Igor accepts from a worker is
  one whose `answer_link` is a person's comment on the item the run
  works. The file's question must also match the question the Igor
  posted in its handback comment, the one the person's comment answers
  (*A person's answer to a handback*, under *Decisions*). Adam also
  decided that the Igor checks every file it pushes with igor PR #217's
  credential matcher, which also matches the values of known secrets
  such as the worker's seat token (*The Igor pushes the questions-branch
  files its worker reports*, under *Decisions*). igor PR #216 records
  both, the question match and the matcher, as its decisions 41 and 28.
  Filter 1, the search for an earlier answer, counts such a file as a
  decision only when GitHub gives that comment's author as the file's
  `answered_by`, or the comment is a relayed answer from `answered_by`'s
  relay App (*Only a listed relay App speaks for a person on GitHub*,
  under *Decisions*), and `answered_by` has write access; otherwise it
  is input. So a worker steered by text it read can't forge a person's
  answer. An answer worth giving agents as lore is promoted by a pull
  request to main adding a `provisional` entry; the question's file
  stays on its branch. Before pushing or promoting, the script checks
  visibility: nothing goes to a lore repository more visible than the
  repository the question concerns (for an organization question, the
  repository whose work raised it, by the spec's definition), ranking
  private, then internal, then public.
- **A question about one person's way of working:** no log. Its answer goes
  into that person's memory or `CLAUDE.md`, which agents already read.
- **A question in one of the three categories** (`vulnerability`,
  `secret`, `personal`): no log. Of this skill's records, only the
  hooks' verdict record of the question, described in *Proving the
  filters ran*, holds it, as a hash. During an Igor's run, the worker,
  the agent an Igor starts on a work item, raises a flag in its report:
  a mark, defined by igor PR #216, that the run met such a question. The flag
  lists each category met in that worker run once, one word each, and
  marks the categories of the questions that stopped the worker (*The
  flag a worker raises for a question with a category*, under
  *Decisions*). igor then counts the run as flagged. It writes the
  category words, never a categorized question's text, into an
  operator-only file on its host, and moves the session logs, which hold
  the text, beside that file (igor PR #216's decisions 88, 89, 97 and
  98). When the Igor reads that flag, #216's task-execution requirement
  *Transcripts and outcomes are captured to the state branch* has it
  write no transcript of the run, since a transcript would hold the
  question (*The flag a worker raises for a question with a category*,
  under *Decisions*).

A log file's and a miss file's path, name, keys and encoding are stated
once, in the spec's requirement *A log file and a miss file have one
format* (*Log and miss files have one format, stated once*, under
*Decisions*). In short, a log file has YAML frontmatter (`repository`,
`asked`, `answered_by`, `authority`: `decision`, `input` or `agent`,
`recorded_in`, and `answer_link`, the comment or review holding the
answer, when there is one) and the question and answer as its body. An
`answer_link` is a github.com comment or review, whose text the `log`
command fetches and records, or a Linear or Discord relay post's URL,
which nothing fetches. The second kind arises only when the answer
session answers a questions-branch question that was also asked in a
Linear or Discord thread (*A questions-branch question is answered by a
new log file*, under *Decisions*): the file then records the text the
session relayed (*Questions-branch answers relayed on Linear or
Discord*, under *Decisions*). A Linear or Discord link proves no writer,
since only GitHub tells a reader who wrote a comment. It is written only
when the lore repository is private, because its ids would otherwise
point readers outside a private workspace at it (*`answer_link` and
`asked_in` are withheld where they would leak*, under *Decisions*). Such
a file counts as a decision only when GitHub verifies a signature for
`answered_by` on the commit that added it, the same proof as for an
answer the person picks in Claude Code's picker and the agent logs from
their machine (*Questions-branch answers relayed on Linear or Discord*,
under *Decisions*). An answer typed directly on Discord, Slack or
Linear, not relayed there by the answer session, is logged as `input`
when an agent reads it. Filter 1 treats that answer as given only
once a decision document records it, of a kind the spec's *Only an
answer with authority stops a question* lists, such as one on the
default branch of the repository the question concerns. One such
document is the `accepted` decision record written by igor's scribe, the
Igor role that writes a discussion's decisions down (*An answer typed on
another surface counts only through a decision document*, under
*Decisions*). An agent's choice has `answered_by: agent`.

An answer logged as `input` goes only into the question's log file,
never into a decision document: on the current work's branch, a decision
document counts as an answer, so writing there an answer logged as
input, such as one from a person without write access, would turn input
into a decision (*An answer without authority stays in its log file*,
under *Decisions*). Log and miss files quote a question as asked and a
person's words exactly, so prose's pass skips files under `.inquisitor/`
(*prose's pass skips `.inquisitor/`*, under *Decisions*). That skip
ships with the skill at gate two, since the skill writes such files from
then on. The files on a lore repository's `questions` branch need no
such rule: that branch is never checked out, so prose never sees them.

When filter 1 stops a question with a lore entry, the citation goes to
that lore repository's `questions` branch, as a file under `citations/`
holding the entry's id and the date. When an Igor pushes a citation from
a run, it adds the run's id, so that igor's review can show each
citation's run and item. With nothing about the question in it, a
citation is written for a question about a private repository too,
whenever the lore repository is no more visible than that repository.
Two kinds of question get no citation (*A citation holds nothing about
the question*, under *Decisions*):
- a question in one of the categories, vulnerability, secret or
  personal, since the cited entry would show what the question was
  about;
- a question about a repository less visible than the lore repository,
  such as a private repository's question answered by an entry in a
  public lore repository, since nothing goes to a lore repository more
  visible than the repository a question concerns.

Both the inquisitor and an Igor
write citation files, and igor's review reads them all, so the spec
states their format once, in the requirement *A citation file has one
format*, and igor PR #216 is to point to it rather than state a format
of its own (*One citation format, defined here*, under *Decisions*).
During an Igor's run the agent pushes no citation itself. A worker, the
agent an Igor starts on a work item, is given only the token of the seat
its work is charged to, a credential for the model, which cannot push to
the lore repository. Task 0.14 measures whether a `gh` login stored in
the home directory the worker is given is usable by the worker anyway.
igor PR #216's requirement *An Igor publishes the citations its worker
reports* says how a worker reports its citations, and which citations
the Igor pushes, and when (*igor PR #216 holds every rule for a run's
citations*, under *Decisions*). The same rules cover the citations of an
inquisitor run the Igor starts itself, with no worker, when a question
stops its own work. The inquisitor's commits to the `questions` branch
are machine records with a fixed message, `inquisitor: log <file>`,
exempt from prose's and bug-hunter's trailers; the branch is never
checked out, so their checks never see these commits. igor's planned
review, which would prune and promote lore entries, could count an
entry's citations there, in one place, beside its fire count, the number
of times igor injected the entry into a worker. That count is a lower
bound, since no citation is sent to a lore repository more visible than
the question's, and the review says so beside it. One case is worse than
a low count: when every citation push the Igors made in the review's
period failed, the branch holds only the citations people's own sessions
pushed, and every entry only Igors cited would show none. So in that
case the review shows citations as "not checked" instead of a count
(*igor's review count of citations*, under *Decisions*). That rule is
igor PR #216's decision 32, and the review is igor's, so how it tells
that every Igor push failed is igor's to settle. A citation's commit
names no person: its author and committer are both
`inquisitor <noreply>`. Its date is reduced to the day, with no time. So
the commit says nothing about who asked (*A citation's commit names no person*, under
*Decisions*).

The 6 random hex digits in a question file's name mean two branches logging
the same question on the same day still write different files. Misses, the questions
a person said need not have been asked, go where their questions went, in
`misses/` in place of `questions/`, in the same format, with `filter` and
`said` in place of the answer keys (`answered_by`, `authority`,
`recorded_in` and `answer_link`).

Every log file and miss file is scanned for secrets before it is
written, and so is every question in a post at the first call. The
patterns are the common shapes of a credential, a closed list the spec
states once as *the credential patterns* (*The secret scan is only a
backstop*, under *Decisions*). A match refuses the write or the post.
The scan is a backstop: a secret under an arbitrary name, such as a
password in `DB_PASSWORD=…`, passes it. The files the agent passes to
`vet`, such as `q.json` and `v.json`, go outside any repository, so they
can't be committed. They go in a directory only the agent's user can
read, such as one `mktemp -d` makes, each with mode 0600, since every
user of a host can read a file left with the usual mode in a shared
temporary directory such as `/tmp`. The script refuses a file that its
group or others can read (*Files passed to the two calls stay private*,
under *Decisions*).

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

`path` is a local clone. The search reads the clone's remote-tracking
default branch, such as `origin/main`, with `git show`, never the
working tree or a local branch, which could be on another branch or hold
an unreviewed edit. The skill fetches only the `questions` branch, so an
entry merged since the person last fetched the clone is not found (*Lore
search is as fresh as the last fetch*, under *Decisions*). It reads the
`questions` branch with `git show` too, without checking it out. The
search reports how fresh the default branch it searched is: when a fetch
in this clone last updated that remote-tracking branch. It reads that
date from the branch's reflog, or reports "unknown" for a clone whose
reflog has no such entry, such as a fresh one. Reading the reflog
means the date and the content searched come from the same ref. The
skill's own fetch would give the wrong date, since it fetches only
`questions`, and so would `FETCH_HEAD`, which that fetch rewrites. The
date is not when the branch last moved on GitHub, and a fetch that
brings nothing new writes no entry.

`owners` lists the GitHub owners whose repositories the lore
repository serves, and `repos` lists single repositories it serves;
several lore repositories may serve one owner. When an organization or
project question matches more than one, the most specific match (a named
repository beats an owner) wins, then the first listed, and the agent's
report says which. A missing `inquisitor.json` means no lore repository,
and filter 1's search says lore was not searched.

Reviewers live in the repository the question concerns, in
`.inquisitor/reviewers`, one GitHub login per line. A team decides them
there, in review, so every teammate's agent tags the same person. A listed
reviewer is the second candidate the script tries in *One person who can
decide is tagged*, under *Decisions*.

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
repository of the item the run worked (*The Igor writes `asked_from` on
every file it pushes*, under *Decisions*), whether its worker reported
the file or the Igor's own inquisitor run wrote it (*The script tells an
Igor's run by `IGOR_RUN`*, under *Decisions*). The worker, or the script
in the Igor's own run, writes `repository`, and the Igor writes
`asked_from`. The only other writer of `asked_from` is an answer
session: when it logs a miss for a question a questions-branch file
holds, the miss copies that file's `asked_from` (*Misses the answer
session logs*, under *Decisions*). A worker steered by its item's text
could put a private repository's details in a file whose `repository`
names a public one, but `asked_from` would still name the private one.
Every reader judges the file by the more private of its two
repositories: igor's search does, and so do this change's own rules that
compare a file's visibility, such as the answer session's privacy check
before an automatic post and the refusal to promote a more private
answer into lore.

When none of the candidates in the decision *One person who can decide
is tagged* (the approver of the related decision, a listed reviewer, the
last committer) has write access, the script considers the
person running the session, identified by the `login` in the
configuration. The script uses that login only when it equals the
account `gh` is logged in as, which it reads running as the person, so
that nobody can claim a maintainer's login by typing it into their own
file. The login itself comes from the configuration, not from
`gh api user` (*The configured login names the person*, under
*Decisions*): run with an App's token, `gh api user` gives no user. The
script's own `gh api user` runs with the person's own `gh` login, so it
returns the person; that is why it can confirm the configured login, and
also why it can't tell which login a post sent with the github-app
skill's token goes out as (task 0.7).

The rules in the rest of this paragraph and the list after it are for
the agent, and SKILL.md states them; in them, the script only chooses
whom a post tags. On a host with no picker, a session with a
person in it asks in its reply wherever these rules say the picker, once
the two calls have vetted the question (*With a person present, ask
through the picker*, under *Decisions*). A headless session never uses
the picker. An Igor worker is given no credential that can post, so it
asks only in its handback comment, which its Igor posts (*An Igor worker
asks only in its handback comment*, under *Decisions*). The worker asks
there even if task 0.14 finds a `gh` login within its reach. When igor
counts the run as flagged, because its worker reported the flag
described above or ended without a completed report, the Igor posts a
handoff that asks nothing. The Igor keeps a record of the questions the
run stopped on in a file on its own host: the categories the flag marks,
and the text of a stopped question that has no category. The file's
rules are igor PR #216's (its decision 97; here *A flagged run asks
nothing and pushes nothing* and *The flag a worker raises for a question
with a category*, under *Decisions*). A headless session that can post,
such as a scheduled agent, tags the login only when the login has write
access and the post goes out as someone else, and otherwise tags no one.
In a session with a person in it, the script reads the configured
login's write access with the same permission call, and then:
- no login configured: the agent asks the question through the picker;
- write access, and the post would go out as that login, or the script
  can't tell which login it goes out as: the agent asks through the picker,
  because a self-tag sends no notification;
- write access, and the post goes out as anyone else, such as a GitHub App:
  the question tags the login;
- no write access: the question tags no one.

The search runs the same way in an Igor worker. igor injects every
active in-scope entry into a worker only while they fit its token
budget, so an entry holding a person's answer can be missing from the
worker's context; the search finds it. Inside an Igor it uses igor's own
scope, the running role's, from `scopeMatches`: `global`, `role:<role>`,
and `project:` matching any repository the role works. An entry out of
scope is hidden, never shown, since scope decides who may see an entry.
Status is labelled, not filtered: an in-scope entry that is not `active`
is shown as input. A question or miss file on a lore repository's
`questions` branch is in scope for every role whose Igor uses that lore
repository, whatever repository its `repository` key names
(*Questions-branch files and `project:` entries in a run's search*,
under *Decisions*). One exception: during a run, igor's search hides a
file about a repository more private than the repository of the item the
run works, such as a file about a private repository from a run on a
public one (*Questions-branch files and `project:` entries in a run's
search*, under *Decisions*). The worker could otherwise repost what it
read into the more public item. Both rules are #216's; the spec points
to them. igor's lore-firing spec, which bans offering a worker a search
tool, is amended by igor PR #216 (decisions in igor issue #215) to allow
a search that applies firing's scope rule and labels status. A worker
reports a cited entry by its id alone, and the Igor checks that id
against the lore repository it injects from. If the search covered
another lore repository, an entry found there could be refused, or
counted as a different entry with the same id. So during a run the
search covers only the lore repository the Igor injects from (*Filter 1
in an Igor's run searches through `igor lore-search`*, under
*Decisions*). In a worker, and in an inquisitor run the Igor starts
itself with no worker, igor's command `igor lore-search` runs that
search, as Adam settled on igor PR #216 (*Filter 1 in an Igor's run
searches through `igor lore-search`*, under *Decisions*). So the script
never needs to know which lore repository the Igor injects from. It
matches plain text and ranks hits as filter 1 does outside a run.

During a run, when the agent picks an id for a lore entry it would
propose, igor reports a clash with an id held outside the run's scope
only as "id taken". The report doesn't say what holds the id: an entry,
after which another id would do, or a rejection, which forbids proposing
the entry. So the agent proposes no lore entry during the run (*A
proposed entry's id follows igor's id rules*, under *Decisions*).

The search reads each markdown file under the clone's `entries/` whose
frontmatter holds `conditions`, never one under `rejected/`, and matches
the question's terms against `claim`, `conditions.prose`, the
`conditions.paths` globs and the body. It also reads each file on the
clone's `questions` branch, as it reads a repository's
`.inquisitor/questions/`. Outside an Igor, a `project:<name>` scope
matches the short name of the repository the question concerns. A
project whose repositories have other names would need a mapping, kept
in one file in the lore repository that igor and the inquisitor both
read; this change does not build it. The igor project's own
configuration has a `destination` setting naming the directory of a lore
repository that holds its entries. Outside an Igor's run the search does
not use it, since a plain session has no Igor configuration; during a
run, igor's `lore-search` covers that lore repository. That repository
also holds the `questions` branch and the people's relay files (*What
the answer session posts, and what it logs* defines them), even when it
is not the repository holding the Igor's configuration (*What a lore
repository means here*, under *Decisions*).

## The answer session

The answer session gives a person one place to answer the questions
asked of them on GitHub, Linear and Discord. A relay identity, a bot of
the person's own on each surface, posts each answer in the question's
thread. Its interface is a Claude Code mod. Adam approved two builds of
its prototype by using them:
- v0.1-30, tagged `answer-session-ui-approved-v0.1-30`;
- v0.1-33, which descends from v0.1-30 and adds the thread's replies and
  filter 1's recorded answer, tagged
  `answer-session-ui-approved-v0.1-33`.

The mod is built from v0.1-33 alone (*The answer session and its relay
identities*; *The UI is built from prototype build v0.1-33*, under
*Decisions*).
By the decision *UI is prototyped and approved by use, not specified*, a
UI approved that way is not specified, so nothing here describes how it
looks. The spec governs what the UI does and posts, and where v0.1-33
does otherwise, the spec wins, and screens the spec needs that v0.1-33
lacks follow its patterns (*How the approved prototype meets the spec*,
under *Decisions*; task 6.1). The rules are in the `answer-session`
spec, the decisions under *Decisions*, in its sections from
*Answer-session configuration, setup and relay identities* to *Linking
log files to threads, and handbacks*.

### Polling while open, with the person's credentials

A webhook needs a public HTTPS server, and Discord's push a permanent
connection: either is a service to run, which nothing else in this skill
needs. So the answer session polls, and only while it is open, about
every 60 seconds, with a catch-up poll when it opens (*The answer
session polls, only while it is open*, under *Decisions*). GitHub's
documentation says its notifications endpoint suits this, and task 0.15
checks that the endpoint behaves as documented: a conditional request
that finds nothing new is answered `304` without counting against the
rate limit, the endpoint's `X-Poll-Interval` says how long to wait, and
a mention subscribes the person to its thread, so a later reply there,
including a reply to the relay, arrives as a notification too. A mention
of the relay in a thread the person was never subscribed to would be
missed; until task 0.15 shows the endpoint reports such a mention, the
answer session also reads the comments of each repository in its
subscriptions.

Reading uses the person's own credentials on GitHub and Linear, and
there a relay identity only posts (*Reading uses the person's own
credentials*, under *Decisions*). A relay's token then needs only the
right to post, and nothing the person reads is read under the bot's
name. On Discord a user account can't be automated within Discord's
terms, so one `discord-bot` identity, the relay, both reads and posts,
in the channels it has been added to (*On Discord one identity both
reads and relays*, under *Decisions*). Reading a message that doesn't
mention it needs Discord's privileged Message Content intent (*The
Discord relay needs the Message Content intent*, under *Decisions*).
discord-bot's setup, in shared-skills PR #1, has the person turn that
intent on for the bot (commit 369ae16), and its `check` command reports
`messageContent` as true, false or null, read from the bot's application
flags (f83b167). Setup's check of message content passes only when
`check` reports true (*The Discord relay needs the Message Content
intent*, under *Decisions*); false fails, and so does null, which means
`check` could not read the flags (the requirement *Setup checks each
relay identity before its channels are used*). discord-bot turns each
`@name` in a post into a mention that notifies that member, and the
relay keeps that on: an `@name` in the person's own answer pings that
person, as it would in a comment of their own (*Discord relay posts: no
header, mentions that ping*, under *Decisions*). discord-bot's rewriting
of `@name` into mentions was once to be turned off for relay posts,
because a relay post quoted a recorded answer, whose @-mentions would
have notified people a second time. A relay post no longer quotes a
recorded answer: it links to the record instead (*What the answer session
posts by itself*, under *Decisions*).

A relay identity may do other work, but only the answer session starts a
post with one of the four reserved prefixes, `User says: `,
`User asks: `, `Recorded answer: ` and `Inquisitor: ` (*Only the
prefixes are reserved, not the identity*, under *Decisions*). Anything
that holds the relay identity could post `User says: `, which marks a
question answered on every machine and, on GitHub, counts as the
person's own answer to filter 1. The skill's instructions reserve the
prefixes. On GitHub the inquisitor's post hook blocks a tool-call post
that starts with one (*The post hook blocks a reserved prefix on GitHub*,
under *Decisions*), which never blocks the answer session, whose posts
reach no tool hook. Nothing enforces it on Linear or Discord.

### The thread is the record

An answer's record is the relay's post in the question's thread, not
anything on the machine (*The thread is the durable record of an
answer*, under *Decisions*). The thread is the one place every machine,
and the asker, can read. A crash between a successful post and the write
of its id to local state loses nothing: the next read of the thread
finds the post and marks the question answered. A post that asks the
asker starts with `User asks: ` instead of `User says: ` (*`User says: `
answers, `User asks: ` asks the asker*, under *Decisions*), so "waiting
for the asker" can be read from the thread too. The two prefixes of the
posts the answer session makes by itself, `Recorded answer: ` and
`Inquisitor: `, mark a question answered or handled for the person, the
same way, on every machine (*Filter 1 runs on every incoming question*;
*Filters 2 to 4 judge every incoming question*, under *Decisions*). A
question the person declines with nothing posted is closed in the state
folder only (*Declining with nothing to answer closes only that
question*, under *Decisions*): nothing in the thread can say so, and
another machine shows it as open. A question declined because the
inquisitor should have handled it, reason 2, gets a post, which the
thread records like any other (*Two reasons to decline*, under
*Decisions*). It gets none only when it has no thread, when it has a
category (one of the inquisitor's categories, whose record is kept as a
hash only), or when the person picks filter 3's choice "the agent
shouldn't have asked" under reason 2 for a message that is not a
question. With a filter 1 record more private than its thread, it is
posted only once the person confirms after a warning that posting shows
the record exists (*Agreeing to a recorded answer is a filter 1
decline*, under *Decisions*). The thread is read again before a question
is shown, when its poll is over a minute old, and before each post, so
an answer relayed from another machine is never posted twice.

### Local state, one writer per machine

The state folder holds working state only: what the person set aside for
later, discussion records, poll positions, relay checks, post ids and
the question on screen (*Local state is per machine, in the state
folder*, under *Decisions*). The decision *Every asked question is
logged with what it concerns* rules out a personal question log: a copy
of a question's record kept where only one person would find it, instead
of with what the question concerns. The state folder replaces no such
record: the asker's log file and the thread stay the records, and filter
1 never reads the folder. It does hold each discussed question's text
under the home directory, but only while the question is open: a
discussion record is deleted once its question is answered or closed
(*Local state is per machine, in the state folder*, under *Decisions*),
so it never becomes a record. Adam ruled that *Local state is per
machine, in the state folder* does not amend *Every asked question is
logged with what it concerns* on that condition. It is kept per machine;
a question set aside on one machine shows as new on another, which costs
a second look and nothing else.

One answer session runs per machine, under a lock in the state folder
that its holder refreshes (*One answer session runs on each machine*,
under *Decisions*). A holder that crashes stops refreshing, and its lock
goes stale after 2 minutes. Before each poll and each post the holder
checks that the lock still holds its session id, so a session that was
taken over posts nothing more. The check compares session ids, not
session names: every session the `answer` command starts is named
`Answers`, so a name can't tell the holder from the session that took
over.

**No TLA+ model** (*One answer session runs on each machine*, under
*Decisions*). Adam's rule asks for one where several processes share
state, and the lock is the only place that happens here. One person uses
the answer session, the lock makes one session per machine the only
writer of that machine's state, and the shared state across machines is
the threads, which each write appends to and each read re-fetches. The
interleavings left are two sessions racing for the lock, which an atomic
create or replace settles, and a take-over during a post, which the
check before each post settles.

### What the answer session posts, and what it logs

A relay post holds the person's own words, so neither prose's pass nor
the inquisitor's filters apply to it (*A relay post gets no prose pass
and no vetting*, under *Decisions*). The mod runs the relay identity's
skill as a command on the host, with its own process call rather than a
tool call of the session's model, and prose's posting hook and the
inquisitor's post hook act only on tool calls. Task 0.18 measures that
no hook sees such a command. The person's answer, and a draft built from
a thread's untrusted text, reach that command, so it runs as an argument
vector with no shell, with the post's text in a file or on standard
input. Since no hook reads a relay post, the answer session scans it for
the credential patterns itself. A relay post names the question it
answers, by replying to it or by a last line `Re: <URL>` (the
requirements *An answer is relayed as the person's words* and *The
thread is the durable record of an answer*), so a thread holding several
questions keeps a state for each.

The answer session writes no log file for a question it relays, except
for a question a questions-branch file also holds, below. The asker
logged the question when it asked, often on a branch not yet merged, and
records the answer when it reads the relay's post. When the asker is a
person, or an agent that keeps no log, nothing logs the answer, and the
thread is its only record. A rephrased answer's post gives the rephrased
question and the one-sentence summary on lines of their own, and the
asker adds them to its log file as two body sections (*A rephrased
answer carries its rephrasing, and the asker logs it*; *Log and miss
files have one format, stated once*, under *Decisions*). Body sections,
not frontmatter keys, hold them, since every frontmatter value is one
quoted line.

A question from a lore repository's questions branch has no thread to
relay to, so the answer session answers it by pushing a new log file to
that branch, as any session does for an answer the person gave in it (*A
questions-branch question is answered by a new log file*, under
*Decisions*). Asking the asker and editing are not offered for such a
question. When the log file's `asked_in` links the post that also asked
it, the answer session shows it from the thread, relays the answer
there, and pushes the log file too (*A questions-branch question is
answered by a new log file*, under *Decisions*), so neither the asker
reading the thread nor an agent searching the branch misses the answer.
When the person, rather than answering in their own words, agrees to the
recorded answer shown beside the question, that is a decline under
reason 2, "the inquisitor should have handled it", with filter 1
(*Agreeing to a recorded answer is a filter 1 decline*, under
*Decisions*), and no log file holding an answer is pushed. So the
questions branch holds nothing saying the question was answered, and an
agent that searches later is stopped by the record the person agreed to,
the decision document or lore entry filter 1 had found, only when its
own filter 1 can read that record and counts it as an answer. The answer
session does push one other file to the branch, a handled file: a new
log file marking the question closed, with no answer. It closes the
question only in the person's queue, and filter 1 still shows the
question to a searching agent as unanswered. The answer session pushes
one whenever it closes a question that a questions-branch file holds:
when it declines it, or when it posts in the thread a recorded answer or
an `Inquisitor: ` reply (*The answer session writes a handled file on
every close of a questions-branch file*, under *Decisions*). A message
that is not really a question is the asking agent's to rewrite, and the
answer session ignores one it judges clearly not a question (*Messages
that are not questions are ignored*, under *Decisions*). The ignore
rule covers only the first two of the four sources in the spec's *A
question asked of the person comes from one of four sources*: a mention
of the person, and a mention of or reply to the relay (*Messages that
are not questions are ignored*, under *Decisions*). So a non-question
from a review request, an assignment or a questions-branch file reaches
the queue without the session judging it.

The person declines with one of two reasons: "nothing to answer", for a
conversation that is over or a message that isn't a question, and "the
inquisitor should have handled it" (*Two reasons to decline*, under
*Decisions*). When a non-question reaches the queue anyway, the person
picks the reason by whose mistake let it through (*Messages that are
not questions are ignored*; *Misses the answer session logs*, under
*Decisions*):
- the answer session's own judgement let it through: the person
  declines under reason 1, nothing to answer, and no miss is logged;
- the asking agent should not have written it: the person declines
  under reason 2, choosing filter 3's "the agent shouldn't have asked",
  and a miss is logged against that agent.

Closing works by exact identity, never by matching (*Closing works by
exact identity, never by matching*, under *Decisions*). A handled file
names, in its `closes` key, the one questions-branch file it closes, and
closes that file on every machine and nothing else. A questions-branch
file whose question the agent also asked in a thread message names that
message in its `asked_in` key, and follows it by that exact link: what
the answer session decides about the message applies to the file (*A log
file follows its thread message by exact link*, under *Decisions*). A
thread copy, the question as shown from its thread, is closed on every
machine only by a relay post in that thread, which every machine reads.
A decline that posts nothing is kept in this machine's state folder
alone: the thread copy is closed here, where the person can reopen it,
and another machine shows it again for the person to decline there too.
The questions-branch file whose `asked_in` links that thread message is
meanwhile closed on every machine by its handled file. A
handled file closes a file without answering it, so an answer the person
later gives to that thread copy, on any machine, still pushes a log file
answering the file. Three earlier rules matched copies: on the
question's words, on each machine's own judgement of its topic
repository, and on commit times. Each kept producing machines that
disagreed about which copies were closed, and exact identity cannot
disagree (*Closing works by exact identity, never by matching*, under
*Decisions*). Nothing reopens a questions-branch file a handled file
closed (*Closing works by exact identity, never by matching*, under
*Decisions*), and a message posted in a thread after its question closed
is shown as a new question (*Declining with nothing to answer closes
only that question*, under *Decisions*).

An answer file uses exact identity too, as a handled file's `closes`
does: it names, in `answers`, the file it answers (*An answer file names
the file it answers*, under *Decisions*). The named file is hidden only
when the answer file counts as the person's answer (*A named file stays
shown until its answer counts*, under *Decisions*). The answer file
records the question as the person saw it, not the file's own text, so a
log file whose `asked_in` points at an unrelated message never gets the
person's answer recorded against words they did not see (*An answer file
records the question the person saw*, under *Decisions*).

Filter 1's search is different: when a later agent asks a question
already answered, it has no log file of its own to name, so the search
finds earlier answers by the hash of their question, and groups every
answer file that way, `answers` or not, so that only the newest in each
group counts (*`answers` decides a named file's answer; the search
groups by hash*, under *Decisions*). Two answer files naming one file
can record different words, each the question as the person saw it, and
so fall in different hash groups; hash grouping alone would leave the
older one counting in its own group. So an answer file that a newer one
naming the same file has replaced is superseded in the search too, and
the person's changed answer is the only one that counts (*`answers`
decides a named file's answer; the search groups by hash*, under
*Decisions*).

Only an answer file whose proof is the person's, and whose commit adds
that answer file alone, becomes a named file's answer (*A named file's
answer must be the person's own, added alone*, under *Decisions*). A
copy of an answer the person gave to another question can carry their
proof too, such as the link to their comment, so the proof alone can't
tell it from a real answer. The commit test covers a copy pushed in one
commit with other files: such a copy never becomes a named file's
answer. No decision covers a copy pushed alone; *Conflicts for Adam to
decide*, under *Open Questions*, lists it.

An Igor asks a person through a handback comment on the issue or pull
request it works, its item. Igor marks each handback with a fixed marker
that no text an Igor quotes from its item can produce, so the answer
session can tell a handback from the Igor's other comments (*igor's
handback marker*, under *Decisions*). No one uses igor yet, so for the
marker, the handback record and `asked_in`, which this paragraph relies
on, the spec states only the end state and *Open Questions* asks igor
#216 for them, with no rule for the time before igor provides them
(*igor-dependent rules state the end state*, under *Decisions*). The
worker's log file links, in `asked_in`, that handback comment, so each
file follows exactly one comment and an answer names only its file. The
item is shown only through its newest handback, since that one says
where the Igor is blocked now. Every older handback is passed over: each
machine works this out from the thread alone and writes nothing, the
older handback is never shown again, and its file stays unanswered and
unshown (*Only an item's newest handback is open*; *Each Igor log file
follows its own handback comment*, under *Decisions*). A bot's message,
an Igor's handback included, reaches only the first person it mentions,
so each bot question has one owner and two people cannot give a bot
conflicting answers. Adam decided, in igor issue #229, the order in which
an Igor mentions people; #229 is open, and igor's specs do not state that
order. When an Igor stops for a reason it detects itself, such as an
unrecoverable failure, its handback mentions its operator, the person who
runs that Igor, first, then the item's assignee and creator. Every other
handback, a question included, mentions the assignee and then the
creator. A handback that mentioned no one would reach the item's
assignee; #229 states that rule too, and names no case in which a
handback mentions no one. The answer session never needs to know
who an operator is (*A bot's question reaches only the first person it
mentions*; *A handback that mentions no one reaches the assignee*, under
*Decisions*).

When the Igor later records the person's answer, it names the earlier
log file in `answers` only when it finds that file on the branch by the
date and the 6 random hex digits of its name, which the Igor's own
record of the handback holds (*A later run names the answered file from
the Igor's record*, under *Decisions*). It never reads a name from the
handback comment's text, which others can edit. It never names a file
because a search found matching words. When more than one file matches,
it names none: two genuine files almost never share a date and six
random digits, so a second match can only be a planted look-alike. An
Igor's handback that mentions no one is routed by assignment and tags no
one, so no tagged person's proof can be asked for; instead an answer
counts for a file that tags no one only when the account the answer file's
signature or linked comment proves has the write access filter 1 requires
of a `decision` entry on a questions branch, write access to the lore
repository (*A named file's answer must be the person's own, added alone*,
under *Decisions*).

Misses no longer match either: a miss file is pushed even when one with
the same question and filter is already on the branch, since dropping it
would again mean matching on words (*Misses the answer session logs*,
under *Decisions*).

A Linear or Discord `asked_in` is withheld from a lore repository that
is not private, as an `answer_link` is (*`answer_link` and `asked_in`
are withheld where they would leak*, under *Decisions*). A GitHub
`asked_in` is withheld from a lore repository more visible than the
repository it points into (*`answer_link` and `asked_in` are withheld
where they would leak*, under *Decisions*). A log file without an
`asked_in` has no link to the message that also asked it, and the answer
session shows it as its own question, never pairing it with a message by
matching text, so the person may see such a question twice. Merging,
showing such a file and a message with the same words as one entry, was
tried in several forms and dropped. Its only benefit was avoiding that
duplicate. Each form could pair the message with a file another asker
logged in the same words, and then a decline closed that asker's
question, or an answer was recorded against it (*A log file without
`asked_in` is never merged*, under *Decisions*).

An answer that cannot reach its thread is kept, not lost (*An answer
that cannot reach its thread is kept pending*, under *Decisions*), where
a failed post would otherwise drop what the person typed. The state
folder keeps it as answered, not relayed, and the machine holding it
lists it as pending. An answer kept because its thread's channel was
off, or because a refused post turned that channel off, goes back into
the queue with its question once setup's check of posting in that
channel passes, the answer kept, for the person to approve again. An
answer kept for any other reason stays on the pending list until the
person acts on it. One the surface refused for its text, such as its length,
stays even where that refusal also turned its channel off (*An answer that
cannot reach its thread is kept pending*, under *Decisions*). Another machine sees only the thread,
so it asks the question again as usual (*An answer that cannot reach its
thread is kept pending*, under *Decisions*); if the person answers there
too, the first relay post to reach the thread sets the question's state,
and the pending answer leaves the list.

For every answer to a question a questions-branch file holds through its
`asked_in`, the session first fetches the thread (*The push order for a
questions-branch answer*, under *Decisions*):
- When the fetch finds a message the person has not seen, the session
  holds the answer back on the pending list, so the person sees the new
  message first, and leaves no file until the person posts the answer.
- When the thread's channel is off or not subscribed here, the answer file
  is pushed at once, without a link to a post. So is the file of an answer
  whose refused post turns its channel off.
- Otherwise the relay post goes first, and the answer file is pushed
  after it, with the post's link. The owed push of the answer file is
  recorded in the state folder before the post and retried at each poll
  and each opening, so a crash between them loses nothing.

In the first two cases, whether or not a file was pushed, the person is
told the asker has not got the answer in the thread yet. The pending
list reuses the approved queue's screens, so it needs no prototype round
of its own. The answer file's github.com `answer_link` is left out where
the lore repository is more visible than the repository it points into,
as an `asked_in` is (*`answer_link` and `asked_in` are withheld where
they would leak*, under *Decisions*). The file is committed as the person,
signed, never as a GitHub App (*Setup checks questions-branch commits are
the person's*, under *Decisions*).

A relayed answer counts as the person's own for filter 1 (*Only a listed
relay App speaks for a person on GitHub*, under *Decisions*). The
decision *A questions-branch decision needs a proven writer* proves a
logged answer's writer only when GitHub gives the linked comment's
author as `answered_by`, and a relay post's author is the relay
identity, so without this a relayed answer would only be input, and an
Igor could never log a handback's relayed answer as a decision (*A
person's answer to a handback*, under *Decisions*). Only an App listed
in the person's own relay file, `relays/<login>.yaml` on the default
branch of the team's lore repository, ties a `User says: ` comment to
them (*Only a listed relay App speaks for a person on GitHub*; *One
relay file per person*, under *Decisions*). Owning the App is not
enough: an Igor's App owned by the same person posts its worker's text
through igor's own code, which no post hook sees. A worker steered by
its item could start such a comment `User says: `, and a `decision` file
linking it would then pass the writer proof and count as the person's
answer. A reader recognises an Igor's App by its slug: igor requires
every Igor's App slug to start with `igor-`, and an Igor whose slug
lacks it refuses to start (igor PR #216's decision 62), so no relay-file
entry whose slug starts with `igor-` counts (*An Igor's App is never a
relay App*, under *Decisions*). A reader of a relay file cannot look the
App up in igor's configuration instead: that configuration names no App
(*An Igor's App is never a relay App*, under *Decisions*), so the slug
is the only mark left.

The file is tied to its person by who last changed it, not by review
(*Who last changed a relay file ties it to its person*, under
*Decisions*). A reader counts it only when the newest commit that
changed it came from a merged pull request the person authored, or
carries a signature GitHub verifies for them; otherwise it lists no
relay. So anyone who can push to the lore repository can stop a person's
relayed answers from counting, but cannot make another App speak for
them. A notice workflow, `relay-notice.yml`, which this skill ships for
the lore repository and which is modelled on igor's seat-notice workflow
(igor PR #171), @-mentions a person on a pull request that changes their
relay file (*A notice workflow mentions a relay file's person*, under
*Decisions*). It mentions a login only when the base branch already
holds that login's file or that person opened the pull request. So
anyone can open a pull request adding a relay file under another
person's login, but that can't make the workflow mention the other
person. No reader depends on the notice. It tells the person when
their file is about to stop counting. It also tells them when someone
else pushes to their own open pull request: that push would count as
the person's once the pull request merges, a cost the decision *Who last
changed a relay file ties it to its person* accepts. One file per person
follows igor's `seats/<id>.yaml`: the person's own pull request adds it,
and a path, unlike a key in a shared file, names whose it is.

The tie still holds only because the prefix is reserved (*Only the
prefixes are reserved, not the identity*; *The post hook blocks a
reserved prefix on GitHub*, under *Decisions*): an agent holding a
listed App that posted `User says: ` by some way the post hook does not
see would forge the person's answer, so a person lists only an App
nothing else posts through unseen. github-app's `token` command prints
an App's token to any agent on the machine, which could then post with a
plain HTTP call no hook sees. Adam decided that github-app is to let a
person mark an identity as a relay and then refuse `token`, `run`,
`credential get` and `wire` for it, so that only github-app's own posting
command can use it: the answer session runs that command as a host command,
and the post hook reads it whenever an agent runs it. Like the post hook, that guards
against accidents, not against an agent set on forging a relayed answer
(*github-app refuses `token`, `run`, `credential get` and `wire` for a relay
identity*, under *Decisions*).
That is a separate change to github-app, not yet written; until it
ships, the cost is accepted and the README says so. Task 0.21 measures
whether GitHub reports which App wrote a comment. Until that measurement
shows it does, a relayed answer is input, and if it shows GitHub does
not, no comment is ever a relayed answer. A relay post on Linear or
Discord that an agent reads stays input, as any answer typed off GitHub
does (*An answer typed on another surface counts only through a decision
document*, under *Decisions*). The answer session also logs an answer it
relayed on Linear or Discord, when the question is on a questions
branch, and that log file can count as a decision through its commit's
signature (*Questions-branch answers relayed on Linear or Discord*,
under *Decisions*).

The file is YAML under `relays/` in the lore repository, the one holding
the entries, with one list per surface. Where igor PR #208's
`destination` points away from the repository holding igor's
configuration, the relay files and the `questions` branch are in the
destination repository, beside the entries (*What a lore repository
means here*, under *Decisions*; igor PR #216's decision 66). An Igor
reads them as of the last commit igor PR #208's lore read applied. #208
refuses a commit that fails igor's startup checks, so the relay files of
a refused commit never count (*An Igor reads relay files as of igor PR
#208's applied commit*, under *Decisions*). `igor run` never fetches, so
there #208 has applied no commit: the Igor cannot tell whether a
`User says: ` comment came from a listed relay App, and pushes such an
answer as `input`, while an answer in the person's own comment still
counts (*An Igor reads relay files as of igor PR #208's applied commit*,
under *Decisions*). Only the `github` list proves anything; nothing in
this change reads the `linear` and `discord` lists, which record in the
same place which identities post for the person there. YAML matches the
lore repository's other configuration. It is not a key of
`igor.config.yaml`, which refuses any key igor does not read, and the
inquisitor's own `inquisitor.json` is per person and on their machine,
where no other reader sees it.

When the person edits a relayed answer also logged on a questions branch
(*A questions-branch question is answered by a new log file*, under
*Decisions*), the answer session pushes a new log file with the edited
answer, since a file there never changes (*No file on a questions branch
changes once pushed*, under *Decisions*), and the newest answered file
for a question counts (*The newest proven answer counts*, under
*Decisions*). Newest means newest by proof, which for a comment link is
the comment's last edit, and for a signature the signed commit's date
(*The newest proven answer counts*, under *Decisions*). Ordering by
proof, not by branch history, keeps anyone with push access from
re-pushing an older proven file to revert a newer answer.

### What the answer session does by itself

The answer session runs filter 1 on every incoming question, and judges
the rest by filters 2 to 4 (*Filter 1 runs on every incoming question*;
*Filters 2 to 4 judge every incoming question*, under *Decisions*), so
the person sees only what needs them. Posting without the person raises
two risks, and the spec answers each:

- **A thread's text reaches the model that judges it.** The model writes
  no word of an automatic post: an `Inquisitor: ` post is one of three
  fixed texts, those for filters 2, 3 and 4, and a recorded answer only
  points to filter 1's hit and quotes nothing from it (*What the answer
  session posts by itself*, under *Decisions*). So a crafted question
  can at worst choose which canned reply or which record is posted.
  Even that choice matters. Filter 3's and 4's replies tell the asking
  agent to decide the question itself, so if the agent acted on any
  reply, a crafted question could pick one of those replies and get
  itself decided with no person involved. Filter 2's reply only tells
  the agent to defer the question, which decides nothing. The asking
  agent therefore acts by itself only on filter 2's reply. It acts on
  filter 3's or 4's only when the person chose that reply under decline
  reason 2, which the reply's last line,
  `The person chose this filter.`, says, and which line the answer
  session never posts by itself (*What an asking agent does with an
  automatic reply*, under *Decisions*). When an agent replies to an
  automatic post, the answer session judges the reply again. A chain of
  replies runs from a reply back through the relay post it replies to,
  the question that relay post names (on GitHub, by its `Re: ` line),
  and so on to the first question. If the automatic post it would make
  has the same text as any automatic post already made in that chain, it
  posts nothing and shows the reply to the person (*No automatic post
  repeats one in its chain of replies*, under *Decisions*), so an agent
  that keeps replying can't get filter 2's text, then filter 4's, then
  filter 2's again with no person seeing the exchange. A recorded answer
  is posted by itself for a person's question as for an agent's (*Filter
  1 runs on every incoming question*, under *Decisions*). Only an
  agent's question gets an `Inquisitor: ` reply by itself, and a
  question counts as an agent's only when its author is a bot account
  (*Which questions count as an agent's*, under *Decisions*), so a
  person never gets a reply nobody wrote. A `User says: ` or
  `User asks: ` post from any bot is a relayed question: the words of
  the person whose answer session posted it, such as another person
  asking this one something through their own relay, so it counts as a
  person's question (*Which questions count as an agent's*; *Filter 1
  runs on every incoming question*, under *Decisions*): filter 1 can
  answer it by itself from a record, and filters 2 to 4 only suggest a
  verdict to the person. When the person declines a question because the
  inquisitor should have handled it, decline reason 2, they can choose
  an `Inquisitor: ` or `Recorded answer: ` post for any question, and
  see the exact post before it goes out (*Two reasons to decline*, under
  *Decisions*).
- **A record can be more private than the thread.** A recorded answer is
  posted by itself only when its record is no more private than the
  thread; otherwise the person sees it and decides (*What the answer
  session posts by itself*, under *Decisions*).

Every automatic post can be edited, and an edit makes it the person's
words, starting `User says: ` (*Editing a relay post*, under
*Decisions*).

The misses the answer session logs, when the person declines a question
the inquisitor should have handled or when a filter handles an agent's
question by itself, go to the questions branch of the team's lore
repository (*Misses the answer session logs*, under *Decisions*). The
answer session can't see where the asker logged the question, which is
often an unmerged branch, and the questions branch takes a direct push,
so no miss needs a pull request. A miss is a lesson about an asking
agent, so a message the answer session picked up by mistake, its own
misjudgement, logs none (*Misses the answer session logs*, under
*Decisions*).

### The session's model

A discussion runs in the session's own conversation (*A discussion runs
in the session's own conversation*, under *Decisions*), so the model has
its tools and can read the question's thread, the code and the specs
before it replies. Each message carries the question as context. The
model may ask the person in its reply there (*A discussion runs in the
session's own conversation*, under *Decisions*), the one exception to
the rule that an agent asks only through the picker: the person opened
the conversation to talk the question through, and a picker would hide
the answer session's screen. The model posts nothing: its draft goes
through `propose_reply` into the prompt box (*Claude drafts a reply only
into the prompt box*, under *Decisions*), and the person relays it. No
hook enforces that the model posts and changes nothing; the context
tells it, and the post hooks still vet any post it tries. The model's
tools can reach what the person's own commands can, the keychain holding
the Linear key included, as in any session. The answer session adds no
guard against that: it is the same exposure as the person's `gh` login,
and Adam accepted it (*A discussion runs in the session's own
conversation*, under *Decisions*). The prototype has shown that a mod
can fill the prompt box and register a tool the model calls by name.

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
it, so spec-trace shows it as uncovered (*Igor-worker scenarios stay
untagged until igor builds what they need*, under *Decisions*). A
skipped test would not do: spec-trace counts a skipped test's tag as
coverage. Gate two, the implementation that follows approval of this
spec on the same branch, lists each such scenario in this section by
name when it writes the tests, and task 4.3 tags it once igor provides
what it needs. Until the change is archived, its scenarios sit outside
`openspec/specs/`, so CI passes. Archiving it while any gap is untagged
would fail CI, so the change is archived only after task 4.3 has tagged
every gap (*The change is archived only after every expected gap is
tagged*, under *Decisions*).
## Decisions

Every decision below is Adam's: he gave it, or confirmed it after this change
proposed it, between 2026-10-19 and 2026-10-30. Some that he confirmed this
change first took itself, without asking, under filter 3 or 4 of its own
skill (one option has merit, or switching later is cheap); the **Why:** of
such an entry names the filter, and Adam's confirmation still made it his.
Each entry states the decision as it stands now, with its reasons
and the alternatives rejected. Until commit 5c9fcc6, proposal.md held these
decisions as numbered rulings, each with how it was reached; that version
of proposal.md, which *Open Questions* quotes as "ruling n", and this pull
request's review hold that history.

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
  only on a fresh verdict, as *Two calls prove the filters ran* says.
- **A category** marks a sensitive question: `vulnerability`, `secret` or
  `personal`. The skill's records keep such a question by hash only
  (*Three categories are recorded by hash only*).
- **A miss** is a question a person said need not have been asked, or that
  an answer session judged clearly need not have been; a **miss file**
  records it.
- **The answer session** is where a person answers the questions asked of
  them on GitHub, Linear and Discord. A **relay identity**, a bot, posts
  each answer for them, starting `User says: `. On GitHub it is a GitHub
  App, the person's **relay App**, which their **relay file**,
  `relays/<login>.yaml` in the team's lore repository, lists. A
  **relayed answer** is a GitHub comment starting `User says: ` whose
  author is a person's relay App.
- **Gate one** is Adam's approval of this change's spec, in a pull request
  holding only the spec. **Gate two** is the implementation, built on the
  same branch after that approval.

### Asking a person

#### Four filters stop questions before a person

**Every question an agent is about to put to a person passes four filters
first, and is asked only if none of them stops it: already answered,
deferrable, not a real question, and cheap to reverse.** The rule covers any
agent in any task, not only spec review or OpenSpec. The skill is useful
locally and needs nothing from Igor. Under filter 1, the earlier answer may be
in another spec or another decision document. The spec's requirements *Every
question passes four filters before a person sees it* and *Filters 3 and 4
have the agent decide the question itself* hold what each filter does.

#### The Igor inquisitor role is out of scope

**The Igor inquisitor role, an Igor that brings surviving questions to a team
discussion, is out of scope; igor #211 tracks and governs it.** The role would
take over the questions behind items an Igor hands back, ask a blocked Igor's
question for it, receive that question through the blocked item, and keep a
budget of posts per channel. The comment an Igor posts when it hands an item
back is the role's to route. Under #211's decision 9, in a team that runs no
Igor inquisitor role nothing posts that comment to a discussion, batches it or
tags anyone; in a team that runs one, the role does those things. Nothing in
this change batches or tags a handback comment. The filters a blocked Igor
runs on its own question are this skill's. How the post hook treats a handback
is in *No exemption for an Igor's handback*.

#### "A decision document" is a closed list

**"A decision document" means only the closed list the spec defines. The wider
set of places an answer can go, which adds a question's log file and a
person's memory or `CLAUDE.md`, is "where the question's answer is
recorded".** The spec's requirements *Only five kinds of document are
decision documents* and *An agent records its own choice where the
question's answer is recorded* hold the lists.

#### Filters 3 and 4 record the agent's choice

**Under filter 3 (fewer than two options have merit) or filter 4 (switching
later is cheap), the agent decides without asking and records its choice where
the question's answer is recorded.** With no decision document to hold it, the
choice goes in a log file with `authority: agent`. Where that file may be
written, and how filter 1 counts it, are in *An agent's choice counts only in
the work it belongs to*.

#### A deferred question stays visible

**Filter 2 defers a question without asking, and the deferral stays visible:
the question is listed as not done in the current work, and filed as an issue
if it outlives the work.** A person who wants the answer now says so. The
`deferred` verdict names where the question will be listed, such as "this PR's
description", not a link, because that post may not exist yet.

#### Questions another skill requires skip filters 2 to 4

**A question that another installed skill requires a person to decide is
exempt from filters 2, 3 and 4, so it is asked now; only filter 1 applies, and
its `ask` verdict names that skill.** The exempt questions are whether to
adopt spec-trace, and prose's `kept (asked)` findings: cold-read findings
that prose requires a person to approve keeping.
bug-hunter's Step 9 recommendations are
not exempt; the decision *bug-hunter's Step 9 recommendations go through the
filters* covers them.

#### bug-hunter's Step 9 recommendations go through the filters

**bug-hunter's Step 9 recommendations go through the inquisitor skill's
four filters, like any other question, so fewer reach a person** (Adam,
2026-10-30). Step 9 is the step of a bug-hunter run that reports and asks
the person about each recommendation, one at a time. There are four
kinds: a root cause, a finding too large for the change, anything left
unresolved when the run aborted, and a property from the hunt (Step 3)
worth keeping as a permanent guard. Task 5.7 changes bug-hunter's SKILL.md
so that Step 9 runs each recommendation through the inquisitor skill
before asking. Nothing in bug-hunter changes before the inquisitor skill
exists.

**Why:** every skill's questions go through one set of filters, rather than
each skill making its own exceptions.

*Rejected:* changing bug-hunter's Step 9 rules on their own, ahead of the
inquisitor skill, so that bug-hunter settles some recommendations itself
without asking. That would be a rule of bug-hunter's own that skips the
shared filters.

The table below holds the starting rules for task 5.7. They are input to
its design, not decided behaviour: whoever builds task 5.7 at gate two
sets the final rules, and Adam reviews them with the implementation. The
spec fixes only that each recommendation passes the four filters.

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
checks that it is. The spec's requirement *A related-decision line is one URL
on a line of its own* holds the link's line format.

**Why:** most questions can then be answered "yes". The picker hook need not
check the order: reordering options after vetting changes the question's
text, which the picker hook already blocks as unvetted.

#### Questions met at one step are batched

**Questions that survive the filters at one step of the work are asked
together, in one picker call or one section of one post.** The spec's
requirement *Related questions are asked together* holds the picker's limit. A
budget of posts per channel belongs to the out-of-scope Igor inquisitor role.

#### With a person present, ask through the picker

**Where the host has a picker and a person is in the session, an agent never
asks in its reply. It asks only in one of these places: the picker; a post;
a Linear or Discord message; or, for a vulnerability, the repository's
private security advisory.** Each of these is open to such a session; the
other entries in this section say which fits a question. On a host with no
picker, such a session asks in its reply instead, wherever the spec says
picker, once the two calls have vetted the question; no hook checks it
there. A subagent returns each surviving question, prepared, to
the agent that started it. The answer session's discussion is the one
exception, as *A discussion runs in the session's own conversation* says.

**Why:** the picker hook then sees every question. The starting agent is the
one talking to the person, and can batch a subagent's questions with its own
(design.md's *Questions in posts*).

*Rejected:* a hook at the end of the agent's turn that reads questions in its
reply: the person has already read the reply when it runs.

#### How a session with no person asks

**A session with no person in it never uses the picker, which is for a person
to read.** A session counts as having no person in it when the agent cannot
tell; how it tells is unmeasured (task 0.9). A session that can post, such as
a scheduled agent, asks in a post. An Igor worker holds no credential that can
post, so it asks only in its handback comment, as *An Igor worker asks only in
its handback comment* says. A session that can neither post nor hand back asks
nowhere: it stops only if the work needs the answer, and reports the question
in its output.

**Why:** counting an unclear session as having no person means a picker is
never opened with nobody to answer it.

#### Headless sessions hold back sensitive questions

**A session with no person in it never asks or posts a `secret` or `personal`
question, and asks a `vulnerability` question only in the repository's private
security advisory; it stops the work that needs the answer and reports only
that a question of that category is blocking, with no text.** During an Igor's
run the worker reports igor's flag instead, as *The flag a worker raises for a
question with a category* says. Such a session never asks a question about one
person's way of working: it stops only if the work needs the answer, and
reports that the question waits for the person. The spec's requirements *A
session with no person in it holds back a question with a category* and *A
way-of-working or sensitive question is held back, not asked* hold the
details.

#### Recontextualise a question or don't ask it

**A question is about one thing, a repository, an organization or a project,
or one person's way of working, and is written at that thing's privacy.**
Context from something more private is generalised ("because some private
backend might do Y", not "because gmango's backend does Y") or left out. A
question that cannot stand without that context is not asked, and is never
filed in a more private place to keep it. The spec's requirement *A question
is written at the privacy of what it concerns* holds the scenarios.

#### A question's audience is no wider than its subject

**An agent puts a question only where the audience is no wider than what the
question concerns, in every channel, Linear and Discord included; visibility
is ranked as the spec's requirement *Nothing about a repository goes somewhere
more visible* gives.** Where the place would be wider, the agent asks through
the picker, or, in a session with no person in it that can post, posts in the
repository the question concerns. For a question about an organization or
project, that is the repository holding the current work, as *A question
beyond one repository is bounded by the current work's* has it. Where the
agent cannot tell, it
asks through the picker, or, with no person in the session, posts nothing and
reports that it did not. The spec's requirement *A question goes only where its
audience is no wider than its subject* holds the scenarios.

#### What counts as a question in a post

**A question in a post is each list item in an open-questions section, and each
other sentence ending in a question mark; the spec's requirement *A question in
a post is a listed item or a sentence ending in a question mark* defines it in
one place.** A section begins only at a heading, bold label or plain colon line
whose label names questions, such as "Open questions:", or at a deferral label,
such as "Not in this change"; it runs to the next heading or bold label. The
requirement's scenarios list the labels. A post is vetted after prose's pass
and before prose signs it. design.md's *Questions in posts* gives the reasoning
for colon lines and for the order with prose.

**Why:** this change took the rule under filter 4, without asking, since it
lives in one function and is cheap to change.

*Rejected:* letting any colon line starting with "Open" begin a section: "Open
a terminal and run:" would turn its commands into questions.

#### A deferred question passes only untagged and listed

**A `deferred` verdict of any age passes the post hook only for a question
listed in an open-questions section and tagging no one, or a question in a new
issue that tags no one; anywhere else the question needs an `ask` verdict.**
Filter 2's two places, the work's description and an issue, then both pass.
A `deferred` record without a category never expires: it is kept until a
later verdict on the same text replaces it, the one exception that *Every
verdict record expires after 2 hours* makes.

**Why:** a deferral asks nothing, so its verdict need not expire. A question
that tags someone asks that person, so it needs an `ask` (design.md's
*Questions in posts*).

#### One person who can decide is tagged

**A question in a post tags one person who can decide: the first the script
finds with write access to what the question concerns, among whoever approved
the related earlier decision, a login in `.inquisitor/reviewers`, then whoever
last changed the files involved.** For a question about an organization or
project, the reviewers file is the team's lore repository's. Unreadable access
counts as none. The spec's requirement *A candidate or login that cannot be
checked is skipped* holds the skip rules and login check.

**Why:** only a person with write access can decide. The reviewers are listed
in a file in the repository, so every teammate's agent tags the same person
(design.md's *Configuration*).

#### The configured login names the person

**The person running the session is the GitHub login in the inquisitor's
configuration, counted only when it equals the account `gh` is logged in as;
otherwise the session has no login configured.** The login comes from the
configuration, and `gh` only confirms it. The script runs that check with the
person's own `gh` login, never a GitHub App's token, so nobody can claim a
maintainer's login by typing it into their own configuration. design.md's
*Configuration* gives the reasoning.

*Rejected:* taking the login from `gh api user` where the agent posts: an
agent posting as a GitHub App runs `gh` with the App's token, under which
`gh api user` gives no user, and an agent posting as the person would get the
person's own login and tag itself.

#### When no candidate can decide

**When no candidate in the tagging order has write access, the script turns to
the configured login, and the outcome depends on that login and on who the
post goes out as:**

- **The login has write access and the post goes out as someone else:** the
  question tags that login.
- **No login is configured, or the login has write access and the post would
  go out as that login:** in a session with a person in it, the agent asks
  through the picker instead of in the post. In a session with no person in
  it, the question tags no one.
- **The login has no write access:** the question tags no one.

A question that tags no one is posted with a line saying that no one with
authority to decide could be found. The spec's requirement *A question no
candidate can decide turns to the session's login* holds the details.

**Why:** a self-tag sends no notification.

### Hooks and verdict records

#### A picker hook makes agents run the filters

**A hook on Claude Code's question picker (`AskUserQuestion`) makes an agent
run the inquisitor before it asks.** The spec's requirement *A hook blocks a
picker question that was not vetted* holds what the hook allows and blocks.

**Why:** design.md's *Proving the filters ran* gives the reasoning, and the
alternatives it rejects: the skill's description alone, and a hook that runs
the filters itself. Its subsection *What the hook relies on, not yet measured*
says what the skill does if tasks 0.1 to 0.3 show that a `PreToolUse` hook
cannot block the picker.

#### The hooks are on once the skill is installed

**The skill's hooks are enabled by default: installing the skill is the
opt-in,** as it is for prose's blocking hooks.

#### Two calls prove the filters ran

**The skill's script takes each set of questions in two calls, as prose's two
calls prove its pass ran.** The first call prints the four filters, runs
filter 1's search and issues a token. The second call must present that token,
and records a verdict for each question the first call took, so no verdict is
recorded without the search having run. The picker hook allows a question only
when the latest verdict on its text is `ask` and less than 2 hours old. The
post hook also allows a `deferred` verdict, because filter 2 lists a deferred
question in a post, but only where the spec's requirement *Questions in posts
pass the same filters* lets a deferral be listed. The spec's requirement *Two
calls prove the filters ran* holds the verdicts and their fields. *The
second call records all its verdicts or none* holds what the second call
refuses, with one exception: the refusal of an `ask` whose recommended answer
is not the picker's first option is in *A question that is asked is prepared
for a quick answer*. *A question's text and hash are built one way* holds how
a question's text and hash are built.

**Why:** design.md's *Proving the filters ran* gives the reasoning, and why a
signed footer inside the question was rejected.

#### Files passed to the two calls stay private

**The files an agent passes to the two calls go in a private directory outside
any repository, made with `mktemp -d` so that only the agent's user can read
it, and each file has mode 0600.** The script refuses a file that its group or
others can read. A question with a category reaches the script on standard
input instead, never in a file. The spec's requirements *The two calls' files
and records stay private* and *Some questions are recorded by hash only* hold
the details.

**Why:** every user of a host can read a file left with the usual mode in a
shared temporary directory such as `/tmp`, and with it a question's text.

*Rejected:* the system's temporary directory: other users of the host could
read the files there.

#### Verdict records live in the user's state folder

**The hooks' records live in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`, where prose keeps its
session marks.** They hold hashes, verdicts, verdict fields and times, never a
question's text. They are the hooks' state, not a question log, so they do not
break the rule that no question log is kept anywhere personal.

**Why:** design.md's *Proving the filters ran* gives the reasoning, and why
the repository's git directory was rejected.

#### An `ask` record drops the option's label

**For a picker question, the hooks' record of an `ask` keeps what changes
under the other options, but not the recommended option's label.** The
options' labels are part of the question's text, the text the record's hash
stands for, and no record holds that text. What changes under each option is
the agent's own account, given in the verdict, not part of the question's
text.

**Accepted:** nothing the skill keeps shows which option the agent
recommended, so nobody can check later from the records whether the person
took the recommendation. design.md's *Proving the filters ran* describes the
record.

#### Verdict records are shared under one HOME

**Everything that runs with the same HOME shares one set of verdict records,
Igor workers included.** One worker's verdict on a question's text can
therefore let another worker ask the same text.

**Why:** a verdict is about the question's text, not the worker. design.md's
*Proving the filters ran* gives the reasoning, and why per-clone records, as
prose keeps its tokens, were rejected.

#### Records hash a question with plain SHA-256

**A verdict record identifies its question by the plain SHA-256 of the
question's text.** The spec's requirement *A question's text and hash are
built one way* holds how the text and the hash are built.

**Accepted:** a short sensitive question could be guessed from its hash, but
only briefly: such a question has a category, and every record with a category
is deleted after 2 hours.

*Rejected:* an HMAC with a per-HOME key, which would stop that guessing: the
2-hour limit already keeps the exposure brief.

#### Every verdict record expires after 2 hours

**Every verdict record, with a category or without one, is deleted 2 hours
after it was made, except a `deferred` record without a category.** That
record is kept until a later verdict on the same text replaces it, because the
post hook accepts a deferral of any age, as *A deferred question passes only
untagged and listed* says. A `deferred` record with a category is deleted
after 2 hours like any other, since a question with a category is kept out of
posts. Two hours is how long a hook uses a record: the picker hook accepts an
`ask` only while it is less than 2 hours old. The spec's requirement *The two
calls' files and records stay private* says which call or hook deletes old
records. None of the skill's own records keeps a lasting record of a
question with a category.

**Why:** a lasting record of such a question would be either personal or
public. Kept on the person's machine, it would be a personal question log,
which the skill rules out. Kept with the questions, it would show in a public
repository that such a question was asked, and when.

#### A post edited after 2 hours is vetted again

**When a post is edited more than 2 hours after one of its questions got an
`ask` verdict, that question is vetted again.** A question with a `deferred`
verdict never needs this, since a `deferred` record without a category does
not expire.

**Why:** vetting again costs only one pair of calls.

#### A hook spends no verdict record

**The picker hook and the post hook spend no verdict record, so a record stays
valid after a hook blocks a call because of another question in it.** Each
record still expires as *Every verdict record expires after 2 hours* says.

**Why:** when one question blocks a call, the agent vets that question alone
and calls again, and the call's other questions need no vetting again.

#### The related-decision line is left out of the hash

**The hooks match a question's text without its related-decision line:
`Related: ` and one URL with no spaces, on a line of its own.** The agent
finds the related decision in the first call's search, so it can add the line
after that call without vetting the question again. No vetting sees that line,
so both hooks block a related-decision line holding a credential pattern. The
spec's requirement *A related-decision line is one URL on a line of its own*
holds the line's exact form and where it sits, and *A question's text and hash
are built one way* how it is left out of the question's text.

**Accepted:** the agent links only a decision that everyone who can read the
question can read, and no hook checks that.

#### What each hook does when it can't read

**The picker hook lets a question through when it can't read its input or its
verdict records.** The post hook lets through input that is not JSON. It
blocks a `gh` command whose body it can't read, and a post holding a question
when it can't read its verdict records. The spec's requirements *A hook blocks
a picker question that was not vetted*, *Questions in posts pass the same
filters* and *The post hook vets what the shared post reader returns* hold the
details.

**Why:** design.md's *Proving the filters ran* gives the reasoning for
unreadable records: an unfiltered picker question publishes nothing, but a
published vulnerability can't be taken back.

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
covered by the skill's instructions alone. A question that survives the
filters is prepared and tagged as *A prepared question can be answered "yes"*
and *One person who can decide is tagged* say.

#### One post reader, shared by both hooks

**prose's posting hook and the inquisitor's post hook read every post through
one library, `.agents/lib/gh-post/`, built by moving prose's reader there.**
The reader tells a hook the post's body and title, that the call sends no
post, or that the call is unreadable, and each hook blocks an unreadable call.
The reader's rules are stated once, in the `gh-post` capability spec, and the
inquisitor's spec points to it. Every rule the reader gains applies to prose's
hook too, since prose's hook calls it. The `gh-post` spec's requirements, from
*The shared post reader reads a post's body from an allow-list* on, hold the
forms it reads, and *prose's posting hook checks a body's footer and a title's
readability* how prose's hook treats each result. design.md's *Questions in
posts* gives the reasoning, and which prose tests change.

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
and `python3`. "A gh post verb" is a closed list, the
one prose's reader handles: certain verbs of `gh pr` and `gh issue`, and a `gh
api` write. So `sh -c '…'`, `bash -c '…'` and `eval '…'` around a `gh` post
are unreadable, and so is a pipe into a shell. A command that runs only
prose's own script, `prose.py`, is no post, since its arguments may name a gh
post as text. A `gh` command whose first word after `gh` is not one of gh's
own commands, such as an alias or an extension, is unreadable. The spec's
requirement *A command that mentions no gh post verb sends no post* holds the
list of gh post verbs, *The reader splits a command line into simple commands*
how a command splits into simple commands, *A line whose simple commands send
no text is no post* the data commands, *Input to a no-post line reaches only
data commands* how pipes and input are judged, *A command that only runs
prose's script sends no post* the `prose.py` forms, and *The reader reads only
gh's own top-level commands* the rule for an alias or an extension.

**Why:** these are prose's reader's rules, so moving the reader changes
nothing prose does. Without the alias rule, `gh c 5 -b 'User says: yes'`, with
`c` aliased to `pr comment`, would pass both post hooks as no post. The
inquisitor's post hook blocks a post starting `User says: `, so that no agent
can forge the person's relayed answer (*The post hook blocks a reserved
prefix on GitHub*), but it would never see this body.

*Rejected:* letting a command through when `gh` appears in it only inside
quotes: `sh -c 'gh pr comment …'` would then post unread.

#### Code given on the command line that names gh

**A command that runs code given in the command, and whose code names `gh`, is
unreadable, data commands included.** prose's data commands that can run such
code are `python` or `python3` with `-c`; `node` with `-e`, `--eval`, `-p` or
`--print`; and `git` with `-c`, which can set an alias that runs a shell
command. A git form that runs a command it is given, such as `git rebase
-x`/`--exec`, `git submodule foreach` or `git bisect run`, counts the same
way. `python`, `python3` or `node` reading its program from standard input,
such as a heredoc or a pipe, is not a data command, so a command line that
mentions a gh post verb and feeds one its program is unreadable. Both post
hooks block every one of these forms. The spec's requirements *A line whose
simple commands send no text is no post* and *Input to a no-post line reaches
only data commands* hold the exact option forms and the rule for a program
read from input.

**Why:** each of these can run a `gh` post that the reader never sees, as `sh
-c`, `ruby -e` and `perl -e` can.

**Accepted:** prose's hook blocks these forms too, so a prose test that
expects one to pass is changed, and prose's `DECISIONS.md` no longer says they
are outside the hook's reach.

#### Posts sent through the github-app skill's script

**The reader reads a post sent through the github-app skill's script, `python3
<github-app script> gh pr|issue …` or `python3 <github-app script> run -- gh
…`, by the same rules as the `gh` command it runs.** `--identity <name>`, the
skill's way to choose an identity, may come before `gh` or `run`. The script's
path must end in `/github_app.py`, and the command gives it in one of two
ways: written out, as a word the shell passes unchanged apart from removing
its quotes, or as `$G`, where the same command sets `G` to such a word. A
command that runs `python3 $G`, mentions `gh` and
assigns `G` nowhere earlier in the same command is unreadable, and the block
message says to set `G` in that command or write the script's path. The
github-app skill's SKILL.md sets `G` in the same command as each use, or
writes the script's full path; this change makes that edit. The spec's
requirement *The reader reads posts sent through the github-app skill and gh
api* holds the forms of the assignment and of a literal word.

**Why:** without this form, every post an agent sends as a GitHub App would be
blocked as unreadable; design.md's *Questions in posts* gives the reasoning.
The path must end in `/github_app.py` because the reader cannot know what any
other script posts, and prose's reader blocks a `gh` word passed to one. In
Claude Code each command starts a fresh shell, so an unset `$G` makes the
command fail and post nothing; only a host whose shell keeps variables between
commands, such as Cursor, could post through it. Blocking it costs only a
rewrite of the command, so nothing needs measuring. Without the SKILL.md
edit, a post an agent copied from one of its examples would be blocked, and
the agent would have to rewrite the command and send it again; with the
edit, the examples pass as written.

#### Posts written with gh api

**A `gh api` call writes when its method is `POST`, `PATCH` or `PUT`, given by
`-X` or `--method` or implied by fields or `--input` with no `-X GET`, and the
reader blocks as unreadable a write whose body it can't read.** For an issue,
pull request, comment or review, it reads the body given by a `body=` field
through `-f`, `--raw-field`, `-F` or `--field` (`-F` and `--field` also read
`@<file>`), or by `--input`. A field is read only when the shell would pass
its word unchanged apart from removing its quotes, so `-f body=$B` is
unreadable. For a review, it reads each `comments[][body]` field and each
`body` in the `comments` of an `--input` file, and a review whose comment
bodies it can't read is unreadable. A write whose fields carry no `body` sends
no post. A write that carries a `body` to an endpoint the reader does not read
is unreadable, and has a scenario of its own. The spec's requirement *The
reader reads a gh api write to an issue or pull request* holds the endpoints,
and *The reader reads GraphQL posts and blocks a gh api write it can't read*
the full list of unreadable and no-post cases.

**Why:** without these rules, a `gh api` comment would pass the reader unread
and skip both hooks. Reads, such as GraphQL queries, and label edits send no
text, so they pass.

#### GraphQL mutations that post text

**The reader returns every `body` argument of a GraphQL mutation that posts
text to an issue or pull request, as it returns a REST write's `body` field.**
Those mutations are a closed list of thirteen, from `addComment` to
`updatePullRequestReviewComment`. Any other mutation sends no post, unless it
has a `body` argument, which makes it unreadable, as a REST write with a
`body` to an endpoint the reader does not read is. A mutation the reader
cannot parse, or whose `body` it cannot read, is unreadable. A `createIssue`
post creates an issue, as a `POST` to `repos/<owner>/<repo>/issues` does. The
spec's requirement *The reader reads GraphQL posts and blocks a gh api write
it can't read* holds the list and where a `body` may be given.

**Why:** a mutation is a write like a REST one, so the same rule applies: it
is blocked only when its body can't be read, and one with no `body` sends no
post.

*Rejected:* reporting every GraphQL mutation as unreadable: it would block
writes that send no text, which the REST rule lets through.

#### A post's title is read and vetted

**The reader returns a post's title, an issue's or a pull request's, with its
body, and both post hooks check it.** The inquisitor's post hook finds a
question in a title as it finds one in a body's running text, a sentence
ending in a question mark, and blocks it until it is vetted. prose's hook
checks only that the reader can read a title: a title gets no prose pass. A
title the reader can't read exactly, such as one built with `$(…)`, makes the
call unreadable, and both hooks block it. The reader reads a `gh` command that
sends a body only when it is the whole command line, and a title is text a
command sends too, so the same holds for a title. A title edit chained to
another command, such as `cd x && gh pr edit 3 --title 'Rename?'`, is
unreadable, as a chained body edit is. `--fill` and its variants, which take a
title from commits, and the pull request's body too, are unreadable. The
spec's requirement *A gh pr or gh issue title is read only as a literal word*
holds how a title is given and read, *The reader reads a GitHub MCP tool's
body, comment and title keys* how an MCP tool's title is read, and *The reader
reads a gh api write to an issue or pull request* and *The reader reads
GraphQL posts and blocks a gh api write it can't read* hold the `gh api` and
GraphQL title fields.

**Why:** otherwise a question in a title would go out unvetted. design.md's
*Questions in posts* gives the reasoning for prose's hook checking only
readability.

#### The post hook blocks a reserved prefix on GitHub

**The inquisitor's post hook blocks a tool-call post on GitHub when any body
the reader returns for it starts with a reserved prefix: `User says: `, `User
asks: `, `Recorded answer: ` or `Inquisitor: `.** It checks the body once
reduced, with leading whitespace dropped, so ` User says: ` and `**User
says:**` are blocked as `User says: ` is. This decision reduces the body the
way a comment is reduced when it is compared with a recorded answer (*A
linked comment holds the answer only when the texts are equal*). Taken
literally, that reduction would defeat this block, because it also ignores a
leading `User says: `. The spec states a different rule: its requirement *The
post hook vets what the shared post reader returns* reduces the body the way
a question in a post is reduced for its hash, which turns inline markup into
its text and joins whitespace. Which of the two rules stands is open for Adam,
and *Where the spec and a decision differ* lists it. The answer-session spec's
*Four reserved prefixes mark the answer session's posts* holds the prefixes.
design.md's *Polling while open, with the person's credentials* gives the
reasoning.

**Why:** the answer session posts through a host command that no tool hook
sees, so a tool-call post starting with a reserved prefix is never the answer
session's. A `User says: ` comment from the person's relay App proves their
answer, and that App may do other work, so the block keeps an agent that holds
the App from forging an answer through `gh`.

**Accepted:** nothing checks Linear or Discord, where a relayed answer proves
nothing.

#### No exemption for an Igor's handback

**The post hook vets every post it sees, one carrying igor's handback marker
included; only the answer session reads the marker.** The spec's requirement
*An Igor's handback comment is no post, but the post hook vets what it sees*
states it, and *Questions in posts pass the same filters* has its scenario.

**Why:** a marker any agent can add would let a post bypass vetting. An
exemption would never help a real handback, since an Igor posts its handbacks
through its own code, which the hook never sees.

*Rejected:* recognising a handback by the marker and an `igor-` App author
together: an exemption helps no real handback, which never reaches the hook.

### Logs and privacy

#### Every asked question is logged with what it concerns

**Every question asked is logged, pointing to where its answer is recorded, so
the next agent finds the answer instead of asking again.** A question concerns
a repository, an organization or a project, or one person's way of working. A
question that concerns none of these is not asked. Its record goes with what
it concerns, at that place's privacy, which that place's maintainers decide.
No question log is kept under the person's home directory, or anywhere else
personal.

An answer about one repository lives in that repository. An answer that spans
repositories goes to the team's lore repository's questions branch, or into
lore itself when it is important enough.

These kinds of asked question get no log file. The spec's requirements *A
way-of-working answer goes to the person's memory, not a log*, *Some questions
are recorded by hash only*, *No question is pushed to a more visible lore
repository*, *A question with no team's lore repository is not logged*, *A
worker's repository question is logged with the run's artifact* and *No log
file records a flagged run's question* hold these rules, in the list's order.
The last two items of the list below each name, in parentheses, the entry
under *Decisions* that sets that item's rule.
- a question about one person's way of working;
- a question with a category;
- a question about an organization or project, raised by work in a
  repository more private than the team's lore repository: the script
  refuses to push it to that lore repository's questions branch;
- a question about an organization or project for which no lore repository
  is configured, or that the agent asks while working in no git repository;
- a question an Igor worker asks in a handback when the run publishes no
  artifact, that is, nothing such as a pull request: the handback comment
  is its record until a later run on the item publishes an artifact
  (*An Igor worker asks only in its handback comment*);
- the question that stopped a flagged run (*A flagged run asks nothing and
  pushes nothing*).

**Why:** design.md's *Where the logs live* gives the reasoning.

*Rejected:* a personal question log under the person's home directory: a
question with private context would be kept, with that context, where only one
person finds it.

#### A repository's questions are committed with the work

**A question about one repository is logged as one file under
`.inquisitor/questions/` at that repository's root, committed with the work,
not kept on a branch of its own.** When that repository is not the one holding
the current work, the file reaches it by a pull request the agent opens
without asking first, as it opens one proposing a lore entry (*A general
answer is proposed as a provisional lore entry*). The current work's
commits can't carry a file into another repository. Each file's name has a
random suffix, so two branches that each log a question never write the same
file.

**Why:** a question about a change belongs in that change's history, and
merges with it.

**Accepted:** until the work merges, its log file is invisible to parallel
work. An agent on another branch, or in another pull request, does not find
the file, and may ask the same question again. The lore repository's questions
branch has no such cost: a file pushed there is found by the next fetch.

*Rejected:* one log file that every question appends to: two branches that
each log a question conflict when they merge.

#### Organization questions go on lore's `questions` branch

**A question about an organization or project is logged on an orphan branch
named `questions` in the team's lore repository, pushed there directly with no
pull request.** The branch is separate from igor's `igor-state` branch, where
igor keeps its runtime state. It holds the question and miss files about the
organization or project: questions not important enough to become lore, but
worth keeping so that nobody asks them again. Nothing on it is given to agents
as lore. It has the lore's privacy and access, which the lore repository's
maintainers set. Filter 1 searches both the lore entries and this branch,
reading the branch with `git fetch` and `git show`, without checking it out.

The lore repository's default branch holds only lore entries. Promoting an
answer to lore is a pull request to the default branch adding a `provisional`
entry, and the question's file stays on the questions branch.

When a push is rejected because the branch moved, the agent fetches and pushes
again. The random suffix in each file's name means two pushes never write the
same file. When a push is rejected for any other reason, such as no push
access or a rule on the branch, the agent logs nothing and says why, rather
than retrying. When no lore repository is configured for the owner of the
repository a question concerns, a question about the organization or project
is not logged, and the agent tells the person so.

**Why:** the default branch stays uncluttered and holds only what Igor gives
agents as lore. A question needs no review, since its authority comes from who
answered it. design.md's *Where the logs live* gives the reasoning in full.

*Rejected:* sending a question's file to the lore repository by a pull
request: a question needs no review, since its authority comes from who
answered it.

#### A way-of-working question gets no log

**A question about one person's way of working, such as "should I keep working
while you're away?", gets no log file.** Its answer goes into that person's
memory or `CLAUDE.md`, which agents already read.

#### Log and miss files have one format, stated once

**A log file and a miss file have one format, stated once in the spec, as a
citation file's is, and design.md points to it.** The spec's requirement *A
log file and a miss file have one format* holds the path, the file name
(`<date>-<slug>-<6 random hex digits>.md`, the date in UTC, the hex digits
lowercase), the slug rule, the encoding and each file's closed list of keys;
*A log file is read by its frontmatter and its body's end* holds how a body is
read.

The decisions on answer links, `asked_in`, `asked_from`, `answers` and handled
files add the keys they name, and *A log file's answer is written as quote
lines* says how an answer is written.

A question the person answered as rephrased in an answer session is logged in
its log file with the rephrasing and a one-sentence summary of the discussion,
in the same format, as *A rephrased answer carries its rephrasing, and the
asker logs it* says. Whatever the format needs for this goes into the same
requirement.

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
into lore.

An unreadable visibility counts the cautious way: the repository the question
concerns counts as private, a lore repository or a post's target counts as
public, and a repository an `asked_in` URL points into counts as private. The
spec's requirements *Nothing about a repository goes somewhere more visible*,
*An unreadable visibility counts against sharing* and *A log or miss file is
as private as its more private repository* hold the ranking, the defaults, and
how a file's visibility is judged. The one exception, a recorded answer's link
that the person confirms, is in *Agreeing to a recorded answer is a filter 1
decline*.

**Why:** a question's record keeps the privacy of what it concerns, which
that place's maintainers decide (*Every asked question is logged with what it
concerns*). Each default for an unreadable visibility makes the more cautious
choice, so nothing is sent somewhere that might be more visible. For an
`asked_in` target, counting it private means the URL is withheld unless the
lore repository is private too (*`answer_link` and `asked_in` are withheld
where they would leak*).
*Configuration*, before *Decisions*, gives how visibility is read.

#### Records are written at the question's privacy

**A question, a miss's record of what the person said, and an agent's own
choice are written at the privacy of what the question concerns: more private
context is generalised or left out.** A person's answer is never generalised:
it is recorded in their own words or not at all. When those words hold context
more private than what the question concerns, the question's file gets no
answer, and the question stays open. The agent uses the answer in the work,
and its report says the answer could not be recorded at this privacy. A later
agent may ask again.

A file written for a question that was never asked, such as an agent's choice
under filter 3 or 4, follows the same rules, and has `answered_by: agent`.

**Why:** the rule that a question is written at the privacy of what it
concerns applies to everything recorded about it. A person's answer can't be
generalised because it is recorded in their own words, as *A logged answer is
the person's own words* says.

#### Three categories are recorded by hash only

**A question in one of three categories is kept in none of the skill's own
records in readable form: `vulnerability`, about a security vulnerability not
yet fixed (such as whether a path traversal is exploitable); `secret`, holding
a secret such as a key or token; and `personal`, holding personal information
about someone, such as their health, an HR matter or a conflict between
people.** The filters still run, and the agent may still ask. The picker hook
matches a question's exact text against its latest verdict, so the script
still records a verdict for such a question, but only as a hash of its text,
the verdict, the time and the category. No text, context or answer is
recorded, and no log or miss file is written.

Such a question gets no search outside the machine, such as GitHub's issues,
so its text never reaches GitHub's search; the first call's output says those
sources weren't searched. A vulnerability's answer goes to the fix and to the
repository's private security advisory, which is its lasting record. How long
the hash record is kept, and that the host's own transcripts lie outside these
records, are in *Every verdict record expires after 2 hours* and *The host's
transcripts are outside the skill's records*. The spec's requirement *Some
questions are recorded by hash only* holds the details, and *A question with a
category is asked only through the picker or its advisory* where a
vulnerability's question and answer go.

**Why:** the list is fixed so that "don't log this" can't become a way to skip
the record: the agent must name why the question is not logged.

#### Categorized questions stay out of posts

**A question with a category is asked only through the picker, or, for a
vulnerability, in the repository's private security advisory.** The post hook
blocks a post that holds one. Under filter 2, such a question is deferred only
into the agent's report to the person in the session, or, for a vulnerability,
into the private security advisory. It is never listed in a post or filed as
an issue. What a session with no person in it does with such a question is in
*Headless sessions hold back sensitive questions*.

#### The secret scan is only a backstop

**The script scans every log file and miss file it writes, and every question
in a post, for the credential patterns, and refuses on a match.** The patterns
are a closed list of known token shapes. The spec's requirement *The credential
patterns are a closed list of token shapes* holds the list, which includes
Anthropic API keys (`sk-ant-`)
and GitHub's user-to-server and refresh tokens (`ghu_`, `ghr_`). It also holds
the two kinds of credential this change puts within the session model's reach.
One is Linear's API keys and OAuth tokens (`lin_api_`, `lin_oauth_`): the
discussion's model runs with the person's tools, so it can read the person's
Linear key from the keychain (*A discussion runs in the session's own
conversation*). The other is a Discord relay's bot token, three base64 parts
separated by dots. That pattern also matches a JSON Web Token, on purpose: a
JWT in a post or a log file is usually a credential, so the scan refuses it
too.

The scan catches known shapes only: a `DB_PASSWORD=…` passes it. So the agent
never puts a credential into a question, an answer or a verdict field, and a
question that needs one gets the `secret` category.

**Why:** design.md's *Where the logs live* gives the reasoning.

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
person who will publish the advisory has said the pull request merges at
the moment of publication; without that word, it waits for publication.

How the fork's commit messages are written depends on task 0.13 too:

- **Until task 0.13 is measured:** they follow the rule for public text,
  whatever the person who will publish the advisory has said, and the full
  description goes in the advisory's text.
- **If task 0.13 shows the merge waits for publication:** the fork is as
  private as the advisory until publication, so a fork commit is described
  normally.
- **If task 0.13 shows the merge can come first:** a fork commit is
  described normally only when the person who will publish the advisory has
  told the agent, before it writes the commit, that the pull request merges
  at the moment of publication; otherwise it follows the rule for public
  text.

The spec's requirement *A weakness is not described in public text before its
advisory is published* holds the rule for public text, with who counts as
outside the advisory and what counts as a public branch. *A weakness's
regression test lands nowhere public before publication* holds the regression
test's rule, and *A commit in an advisory's private fork is described as task
0.13 allows* the fork's commit messages and what the fork is.

**Why:**
- The risk is describing the weakness, in any words, so whether the text
  states a question or its answer is the wrong test.
- The risk exists only while the fix is public and the advisory is not.
  GitHub's private advisories come with a temporary private fork, whose
  commits become public with the advisory, so a fix made there is not public
  before the advisory is. That holds only if the fork's pull request can't
  merge first, which task 0.13 measures.
- A blanket rule would leave a fix's commit message useless even after
  disclosure, against prose's rule 14, that a commit message's body says why.
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
entry in the question's scope. Scope is as *Scope hides an entry; status only
labels it* gives it. `provisional` and `deprecated` entries are input. The
entries below set the conditions for each kind. The spec's requirement *Only
an answer with authority stops a question* holds the full list, and *A hit
that is not an answer is shown as labelled, quoted input* holds the labels.
These requirements hold each kind's conditions, with their scenarios: *A
work-branch decision answers only its own work*, *A log entry counts only
where its branch allows*, *A questions-branch decision counts only unchanged
and with a proven writer*, *A logged decision needs write access to what its
question concerns*, *A questions-branch file's writer is proven by its comment
or its signature*, *A reader counts no signature GitHub may have made*, *A
linked comment holds the answer only when the reduced texts are equal*, *An
answer logged from a comment is the comment's whole text*, *Among files with
the same question, only the newest proven answer counts*, *A file is as new
as its proof, and supersedes only if it would count*, *A named file's answer
is the newest proven answer file naming it*, *A replaced answer file stops
counting even in its own hash group*, *In an Igor's run, a file about another
repository is input*, *An answer typed on another surface is input until a
decision document records it* and *A link off GitHub proves no writer, but a
relayed answer's signature can*.

A login that is not in GitHub's login syntax is never passed to a GitHub API
call, so an answer whose author has one is input.

#### An issue's decision block

**An issue's decision block is the start of the issue's body before its first
heading, or its first section whose heading starts with "Decision", stating
what is decided. It counts as an answer only when the issue's author has write
access.** The spec's requirements *Only five kinds of document are decision
documents* and *Only an answer with authority stops a question* state it.

#### Write access for an organization's question

**For a question about an organization or project, write access to what the
question concerns means write access to the team's lore repository.** The
spec's Purpose defines *write access to what a question concerns*.

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
repository holding the current work, or pushed to the team's lore repository's
`questions` branch, since that needs no pull request. It is never sent by a
pull request to another repository. The spec's requirement *An agent's choice
with no place to record it goes in its report* holds the case where neither
place fits. In the repository, filter 1 shows it labelled as the agent's
choice, which a person can overrule. On a `questions` branch it is always
input: it is pushed so that later agents see the context, and it never stops a
question. A person's later answer to the same question is a new file on the
branch, since no file there changes once pushed.

#### An answer without authority stays in its log file

**An answer logged as `authority: input` is recorded only in the question's
log file, never in a decision document.** design.md's *Where the logs live*
gives the reasoning: on the current work's branch a decision document counts
as an answer, so the agent's own write would turn input into a decision.

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
that is `agent`. The spec's requirements *An answer is a decision only from a
proven writer with write access* and *An unproven answer is input, kept only
in its log file* hold these rules.

#### No file on a questions branch changes once pushed

**A file on a lore repository's `questions` branch is never changed once
pushed, and a file that a commit after its adding commit changed is input.** A
later answer to a question logged there is pushed as a new file holding the
question and the answer, and is proven on its own adding commit. design.md's
*Where the logs live* gives the reasoning: a proof made on the adding commit
then covers everything the file says.

#### A questions-branch decision needs a proven writer

**A `decision` file on a lore `questions` branch counts only when its writer
is proven on the commit that added it, in one of two ways; otherwise it is
input.** In both, `answered_by` also needs the write access every `decision`
file needs.

1. **Comment link:** the file links the github.com comment or review holding
   the answer, on the repository its `repository` key names or on the lore
   repository, and GitHub gives that comment's author as `answered_by`, or the
   comment is a relayed answer of theirs, as *Only a listed relay App speaks
   for a person on GitHub* defines one. The comment's text, once reduced, must
   equal the answer the file records, as *A linked comment holds the answer
   only when the texts are equal* says, so a bare "LGTM" proves nothing.
2. **Signature:** the adding commit carries a signature GitHub verifies for
   `answered_by`'s account. That needs a one-time commit-signing setup on the
   person's machine. The agent commits from the person's session, so the
   person never signs an answer by hand.

In a project set up for a GitHub App, the github-app skill commits as the bot,
unsigned, so there an agent's questions-branch `decision` needs the
comment-link proof. The answer session's answer files are the exception: it
commits them as the person, signed, as *Setup checks questions-branch commits
are the person's* says. The spec's requirement *A questions-branch file's
writer is proven by its comment or its signature* holds both proofs in full.
design.md's *Where the logs live* gives the reasoning: anyone who can push can
write any `answered_by`, and GitHub's commit author login comes from the
author email, which the committer sets.

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
person's own. The inquisitor spec's requirement *A reader counts no signature
GitHub may have made* holds the rule.

#### A logged answer is the person's own words

**A person's answer is recorded word for word, never as an agent's
paraphrase.** An answer logged from a comment is the comment's whole text,
even when it has several sentences or quotes the question. That holds for
every writer: the skill's script, the answer session and an Igor. The answer
text a worker or agent passes with a link only identifies which comment holds
the answer. An answer given in the picker is recorded as the option the person
chose or the text they typed. An answer the person types in their own message
in the session is recorded word for word too. Only an agent's own filter-3 or
filter-4 choice is in the agent's words. An answer whose words hold context
more private than what the question concerns is not recorded at all, as
*Records are written at the question's privacy* says. igor PR #216 records the
writer side as its decisions 67 and 70.

Frontmatter `authority` decides whether a log file is answered, and nothing in
its body does, so a `## Answer` line inside a question's text changes nothing.
The spec's requirement *A log file and a miss file have one format* holds how
the answer is written, and *A log file is read by its frontmatter and its
body's end* how a reader finds it.

**Why:** a reader confirms a comment-linked answer by comparing the two texts
(*A linked comment holds the answer only when the texts are equal*), so one
rule binds writers and readers alike.

#### A log file's answer is written as quote lines

**A log file's answer is written as quote lines, each `> ` followed by the
answer's line, or `>` alone for a blank one, and a reader takes the longest
run of quote lines at the body's end, after a `## Answer` line, as the
answer.** A rephrasing's two one-line sections sit just before `## Answer`,
and the question is everything above them. The inquisitor spec's requirements
*A log file and a miss file have one format* and *A log file is read by its
frontmatter and its body's end* hold the details.

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
does not check who passed an `answer_link` or an `asked_in`, since who passed a
link proves nothing about who wrote the answer; any proof of the writer comes
from the linked comment or the commit's signature. The inquisitor spec's
requirements *The log command takes its input in a private file*, *The log
command records a linked GitHub comment's own text*, *The log command in
Igor-worker mode writes no answer* and *The script writes every log and miss
file through its log command* hold the details.

**Why:** a question's text and its answer passed as arguments are readable by
every user of a shared host.

#### A linked comment holds the answer only when the texts are equal

**A reader confirms a logged answer against its linked comment only when the
comment's text and the recorded answer are equal once both are reduced.** The
reduction drops list markers and inline markup, joins whitespace, and ignores
a leading `User says: ` and a trailing `Re: <URL>` line. No model judges it.
The spec states the rule once, in *A linked comment holds the answer only when
the reduced texts are equal*, which holds the reduction in full. igor's search
applies the same rule (igor PR #216's decision 72).

*Rejected:* counting a comment that contains the answer: it let "merge it."
match "Do not merge it.".

#### An answer typed on another surface counts only through a decision document

**An answer typed directly on another surface, such as Discord, Slack or
Linear, is input until a decision document that filter 1 counts records
it.** One such document is an `accepted` decision record from igor's
scribe, the Igor role that writes a discussion's decisions down (igor
issue #201, PR #202). Any other decision document that records the answer
on the default branch of the repository the question concerns counts too,
whoever writes it. The answer itself never counts, neither as a logged
`decision` nor through a link to the message: a linked answer is only a
github.com comment or review. An answer the person typed in the answer
session, which the session relayed to such a surface, is not typed there;
*Questions-branch answers relayed on Linear or Discord* says how it
counts.

**Why:** only GitHub tells a reader who wrote a comment, as design.md's *Where
the logs live* says.

#### igor's search applies these checks

**igor's `lore-search` applies the authority checks this change states once,
in the spec's requirement *Only an answer with authority stops a question*,
before it labels a questions-branch file as an answer.** It shows the file as
input, labelled unconfirmed, whenever a check can't run or fails. igor PR #216
records igor's side as its decision 34.

#### Citations go to the lore repository's questions branch

**When filter 1 stops a question with a lore entry, the agent pushes a
citation-only file to that lore repository's `questions` branch.** igor's
review, which prunes and promotes lore entries, counts an entry's citations
there, in one place, beside its fire count. A question that filter 1 stops is
not asked, so it gets no log file, and its citation is its only record. No log
file names a lore entry by its id: a log file is only for a question someone
answered, and where that answer is recorded is never a lore entry. During an
Igor's run, *igor PR #216 holds every rule for a run's citations* says who
pushes them.

**Why:** one place to count, with no privacy risk.

*Rejected:* a `cites` field in the question's log file: a question that filter
1 stops gets no log file.
*Rejected:* counting raw search hits instead of citations: no reason is
recorded.

#### One citation format, defined here

**This change defines the one citation-file format, and igor PR #216 points to
it instead of stating its own.** The spec's requirement *A citation file has
one format* holds the path, the name, the date encoding, the keys and the
commit. design.md's *Where the logs live* gives the reasoning: the inquisitor
and an Igor both write citation files, and igor's review reads them all.

#### A citation holds nothing about the question

**A citation file holds the cited entry's id and the date, and, only when an
Igor pushes it from a run, the run's id; it holds nothing about the
question.** Because it holds nothing about the question, a citation is written
for a private question too. A question with a category sends no citation. No
citation is sent when the lore repository is more visible than the repository
the question concerns. The run's id is opaque, and the Igor records it on its
`igor-state` branch, in the run's row of its execution ledger, not with the
transcript, as igor PR #216 says. igor's review shows each citation's run and
item (igor PR #216's decision 10). design.md's *Where the logs live* gives the
reason a categorized question sends none.

**Why:** igor's review counts citations per entry and needs nothing about the
question.

*Rejected:* a hash of the question in the citation: igor's review needs
nothing about the question.

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
date reduced to the day, and no signature.** The script makes it with `git -c
commit.gpgsign=false`, so a person's signing setup for the writer proof never
signs a citation with their key. design.md's *Where the logs live* gives the
reasoning: the commit then says nothing about who asked.

**Accepted:** GitHub's events API still records each push's pusher and time,
visible to anyone who can see the lore repository. That repository is never
more visible than the question's, since no citation goes to a more visible
one.

### Lore and misses

#### Lore repositories are configured as local clones

**The inquisitor's configuration, `~/.config/shared-skills/inquisitor.json`,
lists the lore repositories as local clones, each naming the GitHub owners, the
single repositories (`owner/repo`), or both, that it serves.** Several lore
repositories may serve the same owner. The spec's Purpose holds the key names
(`lore`, `path`, `owners`, `repos`) and defines what a lore repository serves
and how a project is known by its repositories. design.md's *Configuration*
gives an example file and how the clone is read.

*Rejected:* refusing a configuration in which two lore repositories list the
same owner: two lore repositories can serve one owner for different projects.

#### What a lore repository means here

**This change's *lore repository* is always the one holding the lore entries,
which igor PR #216 calls the *destination repository* (#216's decision 66).**
Under igor PR #208, an Igor's configuration lives in one repository, and its
`destination` may point to another that holds the lore entries; that other
repository is then this change's lore repository. When the two are the same
repository, it is the lore repository in both senses. Relay files and the
questions branch live there, beside the lore entries, so that is where the
inquisitor reads both. igor's specs keep *lore repository* for the one holding
the Igor's configuration, as igor PR #208 names it. The inquisitor spec says
so where it defines the term, in its Purpose. design.md's *Configuration* and
*What the answer session posts, and what it logs* describe it.

#### Which lore repository is the team's

**A question about an organization or project goes to the lore repository that
serves the project it concerns. When more than one serves it, the most
specific match wins (a named repository beats an owner), then the first listed
in the configuration, and the agent's report says which it chose.** The spec's
Purpose defines *the team's lore repository*, and its requirement *The team's
lore repository is the most specific one that serves* holds this rule.

#### Filter 1 searches lore in every session

**Filter 1 searches the lore entries, the markdown files with `conditions`,
and the questions branch of every configured lore repository that serves the
repository the question concerns.** An agent working in no git repository
searches every configured lore repository, filtered by scope. Igor workers
search lore too: during an Igor's run, igor's own search command runs the
search, as *Filter 1 in an Igor's run searches through `igor lore-search`*
says. The spec's requirement *Filter 1 searches every place an answer is
recorded* holds the sources, and *Filter 1 matches terms as plain text and
caps its hits* the matching, the ranking and the cap.

**Why:** the search is how lessons reach plain Claude Code sessions, which no
Igor injects lore into. design.md's *Configuration* gives the reasoning.

#### Lore search is as fresh as the last fetch

**Filter 1 reads each lore clone's remote-tracking default branch as the clone
last fetched it, and fetches only the `questions` branch.** The search reports
when the default branch was last updated by a fetch, so the agent can tell how
fresh it is.

**Accepted:** lore is only as fresh as the person's fetches: an entry merged
since that fetch is not found. design.md's *Configuration* gives how the date
is read.

#### Scope hides an entry; status only labels it

**Scope is a hard filter: filter 1 never shows, counts or mentions a lore
entry outside the question's scope, even as input. Status is a label: an
in-scope entry that is not `active` is shown as labelled input, never as an
answer,** as *Only an answer with authority stops a question* has it.

- **Inside an Igor**, the scope is the running role's, as igor's
  `scopeMatches` gives it: `global`, `role:<the running role>`, and `project:`
  matching any repository the role works.
- **Outside an Igor**, the scope is `global` and `project:<the short name of
  the question's repository>`.

igor PR #216 makes the matching decisions on igor's side: scope hard, status
labelled.

**Why:** scope is visibility, as igor treats it, so an out-of-scope entry is
one the asker may not see. A search is not injection, since an agent asks for
its results and an Igor does not put them into a worker's context unasked.
So showing `provisional` and `deprecated` entries, labelled, keeps igor's
promise that an unreviewed lesson is injected into no worker until it is
merged. design.md's
*Configuration* gives the reasoning.

#### A project scope matches the repository's short name

**A lore entry scoped `project:<name>` matches a question when `<name>` is the
short name of the repository the question concerns, the part after the `/`.**
That is igor's own rule: in `scopeMatches` in igor's `src/firing.ts`,
`project:` matches a repository the role works. The spec's requirement *Filter
1 hides every lore entry outside the question's scope* states the rule.

**Accepted:** a project whose repositories have other names would need a
mapping, kept in one file in the lore repository that igor and the inquisitor
both read. This change does not build it, as design.md's *Configuration* says.

#### Filter 1 searches igor's scribe's records where #202 puts them

**Filter 1 searches the decision records of igor's scribe, the Igor role that
writes a discussion's decisions down, at the path igor PR #202 sets, in the
repository the question concerns and in the lore repository.** #202 must say
where that path is; *Open Questions* tracks it.

**Why:** a rule that depends on igor is specified in its end state.

*Rejected:* searching a fixed `docs/decisions/` until #202 settles the path:
that is an interim design for an igor dependency, which this change does not
write while igor has no users.

#### A general answer is proposed as a provisional lore entry

**Where a person's answer, or a lesson learned from a person, holds beyond the
repository the question concerns, and the agent judges it important enough for
agents to be given as lore, the agent opens a pull request adding it as a
`provisional` entry to the team's lore repository, without asking first, and
reports the link.** The script refuses to open the pull request to a lore
repository more visible than what the answer concerns, by the visibility
ranking of *Nothing goes somewhere more visible than its source*. Where no
configured lore repository serves the repository the question concerns, the
agent tells the person the lesson instead. The spec's requirement *An answer
that generalizes is proposed as lore* holds promoting an answer from the
questions branch; *A proposed lore entry's path, fields and id follow igor's
rules* holds the entry's path under `entries/` and its required frontmatter;
and *A lore pull request goes to no lore repository more visible than its
source* holds the visibility refusal.

**Why:** a pull request is itself a proposal, and closing it is cheap.

#### A proposed entry's id follows igor's id rules

**A proposed lore entry's id passes igor's id rule, and is never one an entry
or a rejection in that lore repository already holds.** The rule comes from
igor's lore-store requirement *Ids are derived from the claim and then
immutable*: a kebab-case slug, which igor's validator checks against
`^[a-z0-9][a-z0-9-]*$` (`ID_PATTERN` in igor's `src/entry.ts`). The script
refuses any other id. When an existing entry holds the id, the agent gives the
new entry another id; when a rejection holds it, the agent does not propose
the entry.

**During an Igor's run, an id reported only as "id taken" stops the entry:**
the agent does not propose it, its report says so, and a person can propose
the entry outside a run. igor's id check covers every entry and rejection, but
reports a collision with one outside the run's scope only as "id taken",
naming nothing. igor PR #216 records the same rule for its own id gate. The
spec's requirement *A proposed lore entry's path, fields and id follow igor's
rules* holds these rules.

**Why:** "id taken" does not say whether an entry holds the id, after which
another id would do, or a rejection, which forbids proposing the entry.
design.md's *Configuration* gives the reasoning. igor names nothing because
scope is visibility.

#### A miss is logged against the filter that should have stopped it

**Whenever a person says a question did not need asking, "that was obvious"
being one way to say it, the agent logs a miss against the filter that should
have caught the question.** Misses change the skill only through lessons sent
by pull request or memory edit, never automatically. The spec's requirement *A
question that should not have been asked is logged as a miss* holds where the
miss file goes and what it holds.

#### Lessons from misses are drafted on request and land by scope

**The agent drafts lessons from the misses only when a person asks to review
them, and sends each lesson by its scope:**

- **holds for anyone using the skill:** a pull request to shared-skills
  changing the skill;
- **holds for one team or organization:** a pull request to that team's lore
  repository;
- **holds for one person:** that person's own memory or `CLAUDE.md`.

A lesson bound for shared-skills is written in general terms, quoting no
logged question or miss. The spec's requirement *Lessons from misses land by
their scope* holds the rules, including the refusal of a team lesson to a lore
repository more visible than a miss file it draws on.

**Why:** the question and miss logs stay with the repositories and lore
repositories they concern, because they can hold private content. So a pull
request to shared-skills carries only the generalized lesson.

*Rejected:* the script refusing a lesson that quotes a logged question: a
lesson written in general terms never does.

### Igor workers and Igor runs

#### What an Igor's run covers

**During an Igor's run, the repository the question concerns is the repository
of the item the run works, never one the worker names.** In the rules for a
question with a category, the run is the whole execution on the item, not only
one worker's part of it; igor PR #216 records this as its decision 22. The
spec's requirement *The repository a question concerns defaults to the current
work's* and its Purpose's definition of *during an Igor's run* state both.

#### The script tells an Igor's run by `IGOR_RUN`

**The script knows it runs in an Igor's run only from the environment
variable `IGOR_RUN`, and whenever it acts on the variable its output says
so.** igor sets it to `worker` in a worker's environment and to `igor` in an
inquisitor run the Igor starts itself, and it holds no secret (igor PR #216
at ba154a0). The script matches the exact name, since igor also sets
`IGOR_RUN_TOKEN`, a seat's token, and the exact value, so any other value
marks no run. Under either value the script runs in Igor-worker mode: it
reads no lore clone, pushes nothing to a lore repository, a citation
included, and leaves its files for the Igor, which sets `asked_from` on them
as on a worker's, as igor PR #216's *An Igor publishes the questions-branch
files its worker reports* has it. Only `worker` limits filter 1's other
sources to the worker's working tree. A plain headless session, such as
`claude -p`, has no such variable and keeps its normal lore search. The
spec's requirement *The script tells an Igor's run by IGOR_RUN* holds the
details; design.md's *What task 0.12 measured* gives the reasoning
for the exact match.

**Why:** the output says so because a repository can set the variable in a
person's session, through its committed Claude Code settings or an `.envrc`.
The script would then search no lore and log nothing to a lore repository, and
without the message the person would not see why.

*Rejected:* treating every session with no person in it as possibly in an
Igor's run: a plain headless session would lose its lore search.

#### Task 0.12: an Igor worker cannot run the skill

**Measured on 2026-10-20: an Igor worker cannot run this skill, with a lore
clone and `inquisitor.json` in reach, on igor's main branch or once igor
PRs #174 and #175 land as specified.** So gate two builds everything except
Igor-worker mode, the spec's name for how the script runs in an Igor
worker. design.md's *What task 0.12 measured* gives the evidence.

**Why:** measuring it before this pull request or igor PR #216 lands lets gate
two build everything else at once. #216's task 4.1 could have measured it only
after this pull request landed.

#### An Igor worker asks only in its handback comment

**An Igor worker asks every question that survives the filters in its handback
comment, which its Igor posts, as igor #211 says.** It opens no post and calls
no picker. It asks there even if task 0.14 finds a `gh` login within its
reach. The rule that a headless session posts its question applies only to a
session with no person in it that can post, such as a scheduled agent; *How a
session with no person asks* holds that rule and the case of a session that
can neither post nor hand back. design.md's *Configuration* states the same.

**Why:** a worker holds no credential that can post. igor's task-execution
requirement *The worker is given an explicit environment holding no credential
but its seat's* gives it only its seat's token.

**When an Igor's run ends in its handback comment with no artifact, the worker
logs no question about the item's repository; the handback comment is the
question's record.** An artifact is anything the Igor publishes for the run,
such as a pull request. A later run on the item that publishes an artifact
logs the question there, with its answer once a person has given one.

**Why:** the Igor publishes a log file about the item's repository only with
an artifact.

#### Filter 1 in an Igor's run searches through `igor lore-search`

**In an Igor worker, and in an inquisitor run the Igor starts itself with no
worker, filter 1 searches lore only by calling igor's read-only command `igor
lore-search`,** which igor PR #216 specifies (its decisions 23 and 49). igor
searches its own lore checkout and `questions` branch with the role's scope,
and labels its hits as answers or input as filter 1 labels them. So the script
needs no lore clone, `inquisitor.json` or `gh` in a run, and never needs to
know which lore repository the Igor injects from. The spec's requirement *In
an Igor's run, filter 1 searches through igor* holds the command's input and
what a failed command does, and *An Igor worker's search covers only its
working tree beyond lore* the worker's other sources; design.md's *What task
0.12 measured* and *Configuration* give the reasoning.

**Why:** an Igor worker searches lore at all because igor injects active
in-scope entries only while they fit its token budget, so an entry holding a
person's answer can be missing from the worker's context, and the search finds
it.

igor PR [#216](https://github.com/adamstallard/igor/pull/216), which records
the decisions also held in igor issue
[#215](https://github.com/adamstallard/igor/issues/215), amends igor's
lore-firing spec for Igor workers, and this entry depends on it. Lore still
reaches the worker unbidden. #216 removes the ban on offering a worker a
search tool, which had no reason beyond the worker not needing one. A search
during a run applies firing's scope rule, and returns an in-scope entry that
is not `active` labelled as not lore.

**During an Igor's run, the search covers only the lore repository the Igor
injects lore from,** and no other configured lore repository; igor PR #216
records the same. **Why:** a worker reports a cited entry by its id alone, and
the Igor checks that id against the lore repository it injects from. A search
of another lore repository could find an entry the Igor refuses, or one it
counts as a different entry with the same id.

**`igor lore-search` and filter 1 search alike,** with plain text and no
embedding or model call: the question's terms against a lore entry's claim,
conditions and body, and against a question file's question. Both rank hits by
the number of terms matched, show at most 20, and say when they left hits out
(#216's decision 52). **Why:** the same lore entries then rank the same way
inside and outside an Igor's run.

#### Questions-branch files and `project:` entries in a run's search

**During an Igor's run, a question or miss file on a lore repository's
`questions` branch is in scope for every role whose Igor uses that lore
repository, whatever its `repository` key names.** igor's search returns no
such file about a more private repository: a file is returned only when the
run's item repository is no more visible than the file. A visibility that
can't be read counts against returning the file. igor judges the file by the
more private of its `repository` and its `asked_from` (#216's decisions 25, 27
and 42). #216 applies the same visibility rule to a `project:` lore entry: a
`project:X` entry is neither shown nor fired when the item's repository is
more visible than X (its decisions 53 and 54), and the spec's scenario of a
`project:` entry inside an Igor has the item's repository no more visible.
These rules are igor PR #216's; the spec points to them in *A run's lore
search keeps to the Igor's lore repository and scope* and says nothing
contrary. design.md's *Configuration* gives the reasoning.

**Why:** a worker could otherwise repost what it read about a private
repository into a more public item.

**During a run, a questions-branch file whose `repository` key names a
repository other than the item's always shows as input,** labelled
unconfirmed, whatever its proofs (#216's decision 44). Being in scope lets the
search return the file; this rule sets how the run shows it. The spec's
requirement *In an Igor's run, a file about another repository is input*
states it.

**Why:** a file's proofs show who answered, not that the answer belongs to the
item's repository. So the file informs the run, and decides nothing until it
is proven where it belongs.

#### The Igor writes `asked_from` on every file it pushes

**The Igor adds the run's own item repository, as `owner/repo`, to every log
and miss file it pushes to a questions branch, as the key `asked_from`.** It
sets the key after its format check, and refuses a worker's file that already
holds one (#216's decision 42). The skill's script never writes `asked_from`,
apart from the miss an answer session logs for a questions-branch file, which
copies that file's `asked_from`, as *Misses the answer session logs* says. A
search treats a file as being as private as the more private of its
`repository` and `asked_from`. An `asked_from` that fails the `owner/repo`
check a `repository` must pass counts as a private repository, as igor PR #216
counts it, and also makes the file input. This change owns the file format, so
the key is part of its closed list of keys, and this change's own readers
judge a file's visibility by the same rule. The spec's requirement *A log file
and a miss file have one format* holds the key's rules, the answer session's
one other use of it included, and *A log file's repository keys and
answer_link are checked before use* its syntax check and the file's privacy;
design.md's *Configuration* gives the reasoning.

**Why:** a worker steered by its item's text could write a public `repository`
on a file about a private repository; `asked_from` still names the private
one, so the question can't be laundered.

#### The flag a worker raises for a question with a category

**During an Igor's run, whenever a worker gives a question a category
(`vulnerability`, `secret` or `personal`), whatever its verdict, its report
carries the flag igor PR #216 defines.** The flag holds two lists. The first
lists each category met in that worker run, at most once each, one word from
that fixed list with no other text. A category met on a question that did not
stop the worker, such as one decided under filter 4, is listed too. The
second, a marking of the first, gives the categories that belong to the
question or questions the run stopped on. The two lists are unpaired: the
flag does not say which stopped question had which category, and it has no
per-question format. A stopped question with no category adds nothing to the
flag. The flag holds no question or answer. The Igor accepts a word only when
it is exactly one of the three.

Each worker run reports its own flag, the model steps igor PR #153 runs after
the worker included (#216's decisions 60 and 64). The Igor writes the category
words only into its operator-only file on its host (#216's decision 89), never
into the execution ledger, the state branch, a comment or a label. How the Igor
stores what the flag carries, the case of several stopped questions included,
is igor PR #216's (its decisions 92, 97 and 100). #216's task-execution
requirement *Transcripts and outcomes are captured to the state branch* says
what the Igor does with the flag, and applies the same rules when the Igor runs
the skill itself. The spec's requirement *A session with no person in it holds
back a question with a category* holds the worker's side; design.md's *Where
the logs live* summarises igor's.

*Rejected:* one word per question: it would tell the Igor how many questions
of each category stopped the run.
*Rejected:* listing only the stopped questions' categories, in a fixed order.
Adam's ruling rejects it without giving a reason.

#### A flagged run asks nothing and pushes nothing

**A flagged run is one igor counts as having met a sensitive question: its
worker reported the flag, or the run ended without the worker's completed
report, for any reason** (#216's decisions 19 and 38). A flagged run pushes
nothing to the `questions` branch, citations included.

**A flagged run asks nothing on the item, and its question stays on the Igor's
host.** The Igor posts its handoff, the comment handing the item back, in
place of the worker's handback comment. The handoff posts no question, gets no
`igor:question` label, and reaches nothing in igor #211's inquisitor role
(#216's decisions 73 and 75). The Igor keeps the question in an operator-only
file on its own host, never pushed, and the item stays held: a reply does not
rerun it. That file holds the categories the worker's flag lists, the text of
each stopped question that has no category, and the paths of the execution's
session logs, moved beside it. The operator can always release the item on the
host with `igor release <tracker>/<repo>/<item>`, and an attributable edit or
label by someone with write access to the item's repository releases it too
(#216's decisions 79, 84 and 95). The file and the release are igor PR #216's,
which this change points to rather than restates (#216's decisions 73, 75, 76,
79 to 85, 88, 89, 95, 97, 98, 100 and 101 at d3b7740). This change reads
nothing from that file.

**No log file records the question that stopped a flagged run,** neither from
that run nor from a later run on the item, even one that publishes an
artifact. The spec's requirement *No log file records a flagged run's
question* states this.

#### The Igor pushes the questions-branch files its worker reports

**An Igor worker pushes nothing to a lore repository, since it holds no
credential for one.** Each question file, miss file and `authority: agent`
file it would push to a `questions` branch goes in its report, and its Igor
pushes it when it would push the run's citations. igor PR #216's requirement
*An Igor publishes the questions-branch files its worker reports* holds the
Igor's side; the spec points to it in *An Igor's run reports the
questions-branch files it would push* and does not restate it. design.md's
*Where the logs live* summarises it.

These rules are decided for both changes, and #216 states them:
- **Which files:** the Igor pushes a reported file only when it holds no
  answer, has `authority: agent` and `answered_by: agent`, or is a miss file,
  and only at a path not already on the branch (#216's decision 21). It pushes
  no other file, such as one with `authority: decision`, except a log file
  recording a person's answer to a handback, as *A person's answer to a
  handback* says.
- **Credential check:** the Igor checks each file it pushes for a worker with
  igor PR #217's credential matcher, which matches the values of known
  secrets, such as the worker's seat token, as well as this change's
  credential patterns (#216's decision 28).
- **Visibility:** the Igor reads the lore repository's visibility at every
  push (#216's decision 37).

#### A person's answer to a handback

**When a worker re-works an item after a person answered its handback, the
Igor pushes a log file recording the answer,** with an `answer_link` to the
person's comment on that item. It is a new file beside the unanswered one,
since a file on a questions branch is never changed once pushed. The worker's
report holds the file, with the question and the `answer_link` but no answer,
and the worker decides nothing about it. The Igor writes the answer from the
comment's own words (*A worker logs no answer*), and sets `authority` under
the authority checks of *A logged decision needs write access to what its
question concerns* and *A questions-branch file's writer is proven by its
comment or its signature*: `decision` when the person has write access to what
the question concerns, and `input` otherwise. The spec's requirement *A worker
logs no answer, and its Igor writes it from the comment* holds the worker's
side.

**The Igor pushes such a file only when its question matches a question the
Igor posted in the handback comment that the person's comment answers.** The
match uses the Igor's own record of the questions it posted in that comment,
never the comment's current text. Two questions match when they are equal once
each is reduced as this change reduces a question for its hash (#216's
decision 41).

**Why:** a worker steered by text in its item could otherwise pair a real
comment with another question, and anyone who can edit the comment could
change its text.

#### A worker logs no answer

**An Igor worker writes no answer into any log file, whether on a questions
branch or in a repository's `.inquisitor/`; it writes only the question.** The
answer is logged later by something that can read the comment: an answer
session, the skill's script, or an Igor. That one records the comment's own
words and sets `authority` by its checks. On a questions branch, that is the
Igor, when it pushes the file. In a repository's `.inquisitor/questions/`,
where an answer session never writes and the Igor does not edit the
artifact, it is an agent outside Igor-worker mode that runs the skill's
script there, as for any answer added to a file in that folder. The
inquisitor spec's requirement *A worker logs no answer, and its Igor writes it
from the comment* holds the rule, and *A worker's repository question is
logged with the run's artifact* the repository case.

**Why:** a worker reads no comment, so any answer it wrote would be its own
paraphrase, not the comment's words, and it could not check the writer's
access to set `authority`.

*Rejected:* a worker writing the answer for the Igor or a person to rewrite.

#### An Igor reads relay files as of igor PR #208's applied commit

**An Igor reads relay files as of the commit igor PR #208's lore read last
applied (#216's decision 77).** The check of who last changed a relay file
reads the same commit. Outside an Igor, a reader reads them from the lore
clone's fetched default branch. The spec's requirement *A relay file is read
as last fetched, or as igor last applied it* holds this.

**Why:** #208 applies only a commit that passes igor's startup checks, so the
relay files of a commit it refused never count. That matches the rule that a
relay file whose last change cannot be shown to be its person's lists no
relay.

**When #208 has applied no commit, the relay check cannot run.** That happens
under `igor run`, which never fetches, and for a lore repository #208 never
fetches. The Igor then cannot tell whether a `User says: ` comment came from a
listed relay App, so it pushes such an answer as `input`. An answer in the
person's own comment still counts (#216's decision 78).

#### A later run names the answered file from the Igor's record

**A later Igor run on an item, recording a person's answer to a handback
question, names a file in `answers` only when it knows that file exactly, from
the Igor's own record of the handback (igor PR #216's decision 59).**
Otherwise it writes no `answers`, and the earlier file stays shown until the
person answers it. The record holds only the 6-hex-digit suffix and the date
of the name of the questions-branch log file the Igor pushed for the question,
never question text, and the run finds the file on the branch by them. When
more than one file matches, the run names none. The handback comment may show
the file's name for people, but the run never reads it from there. The spec's
requirement *A later Igor run names the answered file only from the Igor's
record* holds the details.

**Why:** anyone who can edit the comment could change its text. The 6 random
hex digits make a name unique, so a second match can only be a planted
look-alike.

**Accepted:** the slug in a file's name still carries some of the question's
words; the record holds none.

*Rejected:* naming the files a search found by their words.
*Rejected:* reading the file's name from the handback comment's text.
*Rejected:* dropping the slug from file names.

#### igor PR #216 holds every rule for a run's citations

**During an Igor's run the agent pushes no citation itself; igor PR #216's
lore-firing requirement *An Igor publishes the citations its worker reports*
sets every rule for a run's citations,** and this change points to it instead
of restating it. That covers how a worker reports its citations, when the Igor
pushes them, which ones and where, whether from a worker or from an inquisitor
run the Igor starts itself with no worker. This change keeps its own rules
only for a session outside a run, and defines the one citation-file format
both use, with the run's id in a citation an Igor pushes. The spec's
requirements *No worker or Igor-started run pushes to a lore repository*, *A
lore entry that stops a question gets a citation file* and *A citation file
has one format* hold this; design.md's *Where the logs live* gives the
reasoning.

As decided for #216, in brief: the Igor pushes a run's citations only when
the run publishes, and a handback comment counts as publishing. It pushes
them as bookkeeping outside the actions the role's `allow` list permits, and
only citations of existing `active` entries in the run's role's scope. #216
leaves the channel a worker reports them through, its output or an outbox, to
igor PR #175, which runs a worker as a separate Unix user.

**Why:** igor has a worker edit and its Igor publish, and a worker holds only
its seat's token.

#### igor's review count of citations

**igor's review count of an entry's citations is a lower bound, and the review
says so beside the count.** When every push an Igor made of its workers'
citations failed, the review shows citations as "not checked", not as a count,
even if people's own sessions pushed some (#216's decision 32). When at least
one Igor push succeeded, each count stays a lower bound. design.md's *Where
the logs live* gives the reasoning.

**Why:** no citation is sent to a lore repository more visible than the
question's, so some citations are always missing. When every Igor push failed,
a count would show none for every entry only Igors cited.

#### igor-dependent rules state the end state

**A rule that depends on igor states its end state, with no clause for an igor
state before a change lands; what igor must provide is listed under *Open
Questions*.** A clause that also guards against misuse in the end state stays.
These guards stay:
- a log file with no matching record of the handback writes no `answers`;
- an `igor lore-search` call that fails searches no lore;
- the post hook vets every post it sees, a handback-marked one included.

Under this rule filter 1 searches the scribe's decision records where igor
PR #202 puts them, and an Igor worker's search through `igor lore-search` is
stated as what igor must provide.

**Why:** igor has no users yet, so this change specifies no interim design for
it.

#### Alignment with igor PR #216

**The spec states igor PR #216's rules where they touch this change, and
points to the rest.** The Igor's handling of a handback answer (`authority`,
`answered_by`, the relay files it reads, and the answer it records) is pointed
to, not restated. #216's decisions 58 and 59, on fetching under `igor run` and
the hashed record of handback questions, contradict nothing here. #216's rules
on `project:` entries and on the flag for a question with a category are in
*Questions-branch files and `project:` entries in a run's search* and *The
flag a worker raises for a question with a category*.

### Answer-session configuration, setup and relay identities

#### The answer session and its relay identities

**The answer session is where a person does nothing but answer the questions
asked of them on GitHub, Linear and Discord, by agents running the inquisitor
or by people.** Questions reach it from the channels the person subscribes to.
Each answer is posted in the question's thread by that surface's relay
identity, a bot that posts for the person, and starts with `User says: `. The
relay identity is an identity of the github-app skill on GitHub, of the
linear-app skill on Linear, and of the discord-bot skill on Discord. The
answer session's interface is a Claude Code mod, approved by use of its
prototype; *The UI is built from prototype build v0.1-33* names the build the
mod is built from.

#### The configuration is a section of `inquisitor.json`

**The answer session's configuration is the `answer_session` key of
`~/.config/shared-skills/inquisitor.json`.** For each surface it holds the
subscriptions, which are GitHub repositories or owners, Linear teams and
Discord channels, and a reference to the relay identity; on Discord it also
holds the person's Discord user id. The file holds no token. The relays'
tokens stay with the github-app, linear-app and discord-bot skills, and the
person's own Linear API key, which the answer session reads Linear with, is
kept in the system keychain. When `gh` does not confirm the configured login,
GitHub is off. The spec's requirement *The answer session's configuration is a
section of the inquisitor's configuration* holds the key names and their value
formats, and *The person runs the session, and a relay identity posts for
them* the login scenario. design.md's *Configuration* shows an example
file.

#### Setup is part of the answer session

**Setup runs inside the answer session: in place of the queue when the
`answer_session` section is missing or incomplete, and again when the person
types `/answer setup`.** It offers channels to subscribe to, checks that each
relay identity can post, and writes the JSON, which stays editable by hand. It
also installs the `answer` command, and never overwrites a file it did not
write. How setup looks is prototyped, not specified. The spec's requirement
*Setup opens on an incomplete configuration and checks questions-branch
commits* holds the condition that opens setup and the candidate channels;
*Setup checks each relay identity before its channels are used* holds each
relay check; and *Setup proposes the person's relay file and its notice
workflow* holds the pull requests setup opens. *Two commands open an answer
session* holds the `answer` file, the comment line that marks it as setup's,
and what setup says when it leaves a file alone.

#### A failed relay check turns off only its channel

**A failed check of posting in one channel turns off that channel alone.** A
check of the relay identity itself, such as its skill's own check or, on
Discord, reading message content, concerns every channel of its surface, so
when it fails every channel of that surface is off. Setup shows each failure
and how to fix it, and saves the rest. A check that failed or never ran is run
again each time the answer session opens, and its channel stays off until a
check passes. The spec's requirement *Setup checks each relay identity before
its channels are used* holds the on and off rule.

**Accepted:** where no check can read whether a relay identity may post in a
channel (task 0.20), a post the surface refuses turns that channel off until a
recheck passes. That comes on top of what every failed post gets: nothing is
posted, and the person is told why. The answer is kept, as *An answer that
cannot reach its thread is kept pending* says. In such a channel, the posting
check counts as passed for the on and off rule once the relay identity's own
check passes again, as the spec's requirement *A pending answer whose channel
was off returns to the queue* says. Setup still
shows that posting check as not checked, never as passed, because nothing
checked it.

#### Setup checks questions-branch commits are the person's

**The answer session commits questions-branch answer files as the person, with
their git identity and signing, never a GitHub App's, even in a project set up
for an App.** Setup checks both: that the commits use the person's identity,
and that they are signed with a key GitHub verifies for the person's account.
When either is not so, setup warns and says how to fix it. The spec's
requirement *Setup opens on an incomplete configuration and checks
questions-branch commits* holds how setup resolves the identity and signing,
and what it shows when it cannot tell.

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

**On Discord, the relay identity both reads and posts, in the channels it has
been added to.** There is no separate identity for reading, and no `read` key.
On GitHub and Linear the answer session reads with the person's own
credentials. The spec's requirement *The answer session reads with the
person's credentials, except on Discord* holds the rule.

**Why:** a Discord user account can't be automated within Discord's terms, so
Discord is the one surface the answer session reads with a bot. design.md's
*Polling while open, with the person's credentials* gives the reasoning.

*Rejected:* a second Discord identity, named in a `read` key, reading as the
person: a Discord user account can't be automated within Discord's terms.

#### The Discord relay needs the Message Content intent

**The Discord relay must be able to read message content, which needs
Discord's privileged Message Content intent.** discord-bot's setup, in
shared-skills PR #1 (commit 369ae16), has the person turn the intent on, and
its `check` reports `messageContent` as true, false or null, read from the
bot's application flags (f83b167). Whether Discord is on depends only on that
report and setup's other checks. discord-bot turns an `@name` in a post into a
mention that notifies that member, and relay posts keep that, as *Discord
relay posts: no header, mentions that ping* says, so no option to post with
mention rewriting off is needed. The spec's requirement *Setup checks each
relay identity before its channels are used* holds which values pass.

**Why:** reading a message that does not mention the bot needs the intent.
design.md's *Polling while open, with the person's credentials* gives the
reasoning.

#### Only the prefixes are reserved, not the identity

**A relay identity may be used for other work, but a post that starts with
`User says: ` or `User asks: ` is made only by the answer session, on the
person's confirmation.** `Recorded answer: ` and `Inquisitor: ` are reserved
the same way, for the posts the answer session makes by itself, as *What the
answer session posts by itself* says. On GitHub only an App the person's relay
file lists speaks for the person, as *Only a listed relay App speaks for a
person on GitHub* says. The spec's requirement *Four reserved prefixes mark
the answer session's posts* holds the details. design.md's *Polling while
open, with the person's credentials* gives the reasoning.

*Rejected:* keeping a relay identity for nothing but the answer session: the
prefix alone marks a relay post, and nothing reads a relay identity's other
posts.

#### Only a listed relay App speaks for a person on GitHub

**A GitHub comment that starts with `User says: ` counts as the person's own
comment, wherever filter 1 reads who wrote a comment, only when its author is
an App listed as that person's relay in their relay file on the default branch
of the team's lore repository.** A `User says: ` comment from any other App
the person owns, an Igor's included, is input. An Igor's App is never a relay
App, as *An Igor's App is never a relay App* says. The rule is what lets the
writer proof count an answer relayed on GitHub, and lets an Igor log a
person's relayed answer to its handback with `authority: decision`. Task 0.21
measures whether GitHub reports which App wrote a comment; until it shows
GitHub does, no comment is a relayed answer, and every `User says: ` comment
is input. The inquisitor spec's requirements *A relayed answer counts as its
person's own comment*, *A relay file names the bots that post for its person*
and *A relay App is one its person's counted relay file lists* hold the
details.

**Why:** a relayed answer can be trusted because only the answer session makes
a `User says: ` post, and only on the person's confirmation. Owning the App is
not enough: igor's own code posts its worker's text with no hook seeing it, so
a worker steered by its item could start a comment `User says: ` and prove a
questions-branch `decision` file. design.md's *What the answer session posts,
and what it logs* gives the reasoning.

*Rejected:* counting a `User says: ` comment from any App GitHub reports as
owned by the person: an Igor's App owned by the same person would let a
steered worker forge the person's answer.
*Rejected:* treating every relayed answer as input: a relayed answer could
then never prove its writer, and an Igor could never log a handback's relayed
answer as a decision.

#### An Igor's App is never a relay App

**An Igor's App is never a relay App, even where a relay file lists it, as
igor PR #216's decision 45 has it, and a reader recognises one by its slug's
`igor-` prefix.** igor requires every Igor's App slug to start with `igor-`:
an Igor whose App's slug lacks it refuses to start (#216's decision 62). So a
reader takes every App whose slug starts with `igor-` as an Igor's App, and
never counts a relay-file entry whose slug starts with `igor-` as a relay. A
person lists only an App that posts nothing a post hook can't see, apart from
the answer session's own posts. A relay App may do other work, but only
through tool calls the post hook sees. The inquisitor spec's requirements *A
relay App is one its person's counted relay file lists* and *A person changes
their own relay file, listing only Apps a post hook sees* hold this.

*Rejected:* recognising an Igor's App from the lore repository's Igor
configuration: igor's role-config spec forbids any key that names an App
identity, and a lore repository with no Igor configuration would then have no
relay App at all.
*Rejected:* a `relays/_igor.yaml` file listing the Igors' Apps: the slug
prefix igor already enforces identifies them.

#### The Igor names who answered through a relay App

**For a relay App's comment on a handback, the Igor sets `answered_by` as well
as `authority`: the person whose relay file lists that App.** igor PR #216
left this to this change. The inquisitor spec's requirement *A worker logs no
answer, and its Igor writes it from the comment* holds the rule.

**Why:** the worker can't read the relay files, so without this every relayed
handback answer would name the wrong person and be input.

#### One relay file per person

**A person's relays are listed in `relays/<github-login>.yaml` in the team's
lore repository, read from its default branch.** The file holds the person's
`github` (App slugs), `linear` and `discord` lists, and only the `github` list
proves anything. The person adds or changes the file with their own pull
request, and the answer session's setup proposes it. The inquisitor spec's
requirements *A relay file names the bots that post for its person* and *A
missing or malformed relay file lists no relay* hold the format and how a
missing or malformed file reads.

**Why:** the file is modelled on igor's seat files: igor issue #148 and igor
PR #171 give each lender a `seats/<id>.yaml` that their own pull request adds.
A path, unlike a key in a shared file, names whose file it is. design.md's
*What the answer session posts, and what it logs* gives the reasoning, the
choice of YAML included.

*Rejected:* one shared `relays.yaml` at the lore repository's root, keyed by
login: a key in a shared file does not name whose it is the way a path does.

#### A malformed relay file lists no relay

**A relay file that is missing or does not parse lists no relay, and a value
that is not a list of strings lists none for that key.** A file is one
person's, so one whose name is not a GitHub login lists none. Only the
`github` lists prove anything. The inquisitor spec's requirement *A relay file
names the bots that post for its person* holds the definition of a relay file.

#### Who last changed a relay file ties it to its person

**No review is required: a reader counts `relays/<login>.yaml` only when its
last change came from that login.** The last change is the newest commit on
the default branch that changed the file. It is the person's when they
authored the merged pull request GitHub associates with that commit, or when
the commit carries a signature GitHub verifies for their account. Otherwise,
and whenever either check cannot run, such as offline, the file lists no
relay, as a missing file does. Setup proposes the file again when its last
change was not the person's, even if it lists every relay, since such a file
does not count. Task 0.22 measures what a reader needs for the check, such as
that GitHub gives the pull request behind a commit. Inside an Igor, the commit
read is the one igor PR #208's lore read last applied, as *An Igor reads relay
files as of igor PR #208's applied commit* says. The inquisitor spec's
requirement *A reader counts a relay file only when its person made its last
change* holds which commit counts as the last change and how git's history
walk finds it, and *A relay file names the bots that post for its person* that
the name is compared with the login without regard to case.

**Why:** under this rule, anyone who can push to the lore repository can stop
a person's relayed answers from counting, but cannot make another App speak
for them. design.md's *What the answer session posts, and what it logs* gives
the reasoning.

**Accepted:** someone who can push to the person's open pull request, such as
a maintainer the person's fork lets edit it, can change the file under that
pull request, and the change counts once merged. The relay notice, the
comment of the workflow in *A notice workflow mentions a relay file's
person*, @-mentions the person for that push, so they can close the pull
request.

**Accepted:** anyone who can rewrite the default branch can restore an older
file of the person's own, listing an App the person had removed. So removing a
compromised App from the file does not stop it speaking for the person, and
the README says to uninstall the App or revoke its key instead.

*Rejected:* counting the pull request only when every commit in it is the
person's: GitHub's API can't show a pushed commit's pusher.
*Rejected:* requiring review, by relying on the lore repository's branch
protection with setup warning when the default branch requires none: ownership
ties the file to its person without it.

#### Setup's relay pull request

**Setup opens the relay pull request as a host command, with a fixed title and
body the script writes, so it needs no prose pass,** as the answer session's
automatic posts need none. When setup proposes the relay file again because
someone else last changed it, the file's first line is `# confirmed by <login>
on <date>`. The answer-session spec's requirement *Setup proposes the
person's relay file and its notice workflow* holds the details.

**Why:** the dated first line makes the pull request change the file even when
the relays are the same; otherwise no commit would change it, and the other
person's commit would stay its last change.

#### A notice workflow mentions a relay file's person

**The inquisitor ships a workflow, `relay-notice.yml`, that @-mentions a
person on a pull request that changes their relay file, and setup proposes
it.** It is igor's seat-notice workflow (igor PR #171) applied to
`relays/<login>.yaml`, with the person named by the path. It mentions a login
only when the base branch holds that login's file or that person opened the
pull request, and never for an event the person caused on a pull request they
opened. It runs on `pull_request_target` alone, on GitHub-hosted runners, with
no `paths` filter, and reads only the names of the paths the head changes,
never their contents. Where the lore repository's default branch lacks the
workflow, setup opens a separate pull request adding it. When GitHub refuses
that pull request, such as for a `gh` login without the `workflow` scope,
setup says so and carries on. The spec's requirement *A pull request that
changes a relay file mentions its person* holds the events and the comment's
first line, and *The relay notice reads only the names of the paths a pull
request changes* the path pattern and the token's scope.

**Why:** the notice tells the person when their file is about to stop
counting, and when someone else pushes to their own open pull request.
Mentioning only the base branch's file owner or the pull request's opener
keeps a pull request from making the workflow mention anyone it likes; igor's
workflow reads the owner from the default branch's copy for the same reason.
Setup carries on after a refusal because no reader depends on the notice.

*Rejected:* having igor's seat-notice workflow cover relay files too: the
notice would wait for igor's release and for a change to another repository's
spec, though one workflow would be the simpler end state.

#### A relay notice is shown as a notice

**A relay-notice comment starts with a fixed first line, and the answer
session shows such a comment from `github-actions[bot]` as a notice, never as
a question,** so it is never answered by itself or logged as a miss. The
inquisitor spec's requirement *A pull request that changes a relay file
mentions its person* holds the line, and the answer-session spec's *A
relay-notice comment is shown as a notice* how it is shown.

#### github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity

**github-app's `token`, `run`, `credential get` and `wire` commands are to
refuse an identity marked as a relay, so only the answer session's own posting
command can post with it.** That is a change to the github-app skill, which
this change asks for and does not make. This change ships without it, with
the cost below accepted.

**Why:** a relay App speaks for its person only while nothing posts through it
unseen. `token` prints the App's token to any agent on the machine, and `run`,
`credential get` and `wire` hand that token to a command, to git, or to a
clone's configuration.

**Accepted:** these refusals, like the post hook, guard against accidents, not
against an agent set on forging a relayed answer. They stop an agent posting
through a relay App by mistake; they do not stop one that sets out to get
around them. Until github-app's change ships, any agent on the person's
machine can print a relay App's token and post `User says: ` with a plain HTTP
call no post hook sees. The inquisitor's README says so (task 5.2).

### Running the answer session

#### Four sources of a question asked of the person

**A question asked of the person is one of four things:** a mention of them in
a subscribed channel, agents running the inquisitor included; a mention of
their relay identity, or a reply to a relay post; on GitHub, a pull request
requesting their review or an issue assigned to them, and on Linear, an issue
assigned to them; or a log file on a lore repository's questions branch whose
question tags them. The spec's requirement *A question asked of the person
comes from one of four sources* holds the sources. Other requirements hold
the rules that other entries decide:
- whom a bot's question reaches: *Whom a message reaches is set by its
  mentions* and *A mention names a user outside code, quotes and links*;
- Igor handbacks: *A handback is an igor- App's comment holding igor's
  marker*, *Only an item's newest handback is shown*, *An item's newest
  handback is open until a relay post names it* and *A handback that mentions
  no one goes to the item's assignee*;
- log files that follow a thread message: *A log file follows the thread
  message its asked_in links*, *A log file with no followed link is judged on
  its own* and *An Igor's log file follows its own handback comment*;
- ignoring what is clearly not a question: *Messages judged clearly not
  questions are ignored*.

#### The answer session polls, only while it is open

**The answer session reads its channels by polling, about every 60 seconds,
and only while an answer session is open; it uses no webhooks.** It polls once
on opening to catch up. Until task 0.15 shows that GitHub's notifications
endpoint reports every GitHub message of the first three sources, the answer
session also reads each subscribed repository's comments. A questions-branch
log file, the fourth source, never appears in notifications, so the answer
session reads it by fetching that branch at each poll. The spec's requirements
*The answer session polls only while it is open* and *The answer session polls
GitHub's notifications and comments* hold the details: the 14-day first read
and fetching the questions branches in the first, GitHub's conditional
requests, `X-Poll-Interval` and the extra read of repository comments in the
second.

**Why:** a webhook needs a public HTTPS server, and Discord's push needs a
permanent connection, so either would be a service to run. GitHub's
notifications endpoint answers conditional requests that, by GitHub's
documentation, do not count against the rate limit, and it sets the interval
between polls; task 0.15 measures both. Repository comments are read too
because a mention of the relay in a thread the person was never subscribed to
would otherwise be missed. design.md's *Polling while open, with the person's
credentials* gives the reasoning.

**Accepted:** reading the comments costs a rate-limited request per repository
per poll, and a subscription to an owner costs one for each of that owner's
repositories.

#### Reading uses the person's own credentials

**The answer session reads with the person's own `gh` login and Linear key,
and a relay identity only posts.** Discord is the exception: one `discord-bot`
identity both reads and relays, as *On Discord one identity both reads and
relays* decides. The spec's requirement *The answer session reads with the
person's credentials, except on Discord* holds the details.

**Why:** a relay's token then needs only the right to post, and nothing the
person reads is read under the bot's name (design.md's *Polling while open,
with the person's credentials*).

#### Local state is per machine, in the state folder

**The answer session keeps its working state in
`${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`, per
machine.** It keeps the question on screen there, so that `answer` and
`/answer` reopen on it even after Claude Code restarts. The spec's requirement
*Local state is per machine, in the state folder* holds the full list. A
discussion record is deleted once its question is answered, answered or
handled for the person, or closed. On that condition the state folder is not
the personal question log that *Every asked question is logged with what it
concerns* rules out.

**Why:** the state is the person's working state, not a record: the thread and
the asker's log file stay the records. design.md's *Local state, one writer
per machine* gives the reasoning.

**Accepted:** a question set aside on one machine is new on another. It costs
a second look and nothing else.

#### Which cross-machine cases are accepted

**A case between two machines of the same person whose worst outcome is a
question shown twice or asked again is accepted, and gets no rule of its own.**
A case that could record a wrong answer, close a question wrongly, leak
private content or lose an answer is still raised for a decision.

#### One answer session runs on each machine

**One answer session runs per machine, under a lock in the state folder that
its holder refreshes, so a crashed holder's lock goes stale.** While another
session holds a fresh lock, a second `/answer` opens nothing: it says which
session holds the lock, by name and whether it is a Claude Code background
session, says how to reach it, and offers to take over. The spec's requirement
*One answer session runs on each machine* holds the details: what the lock
names, refresh and staleness times, the atomic write, and the check before
each poll and post. No TLA+ model is written.

**Why:** one person uses the answer session, and the lock makes one session
per machine the only writer of that machine's state. design.md's *Local state,
one writer per machine* gives the reasoning, for the lock and for writing no
model.

#### Two commands open the answer session

**The answer session opens with `/answer` in any session, or with the `answer`
terminal command that setup installs.** The `answer` command starts a Claude
Code session named `Answers`, with `/answer` as its first prompt, fullscreen
in the terminal it is started from, where clicks work. No environment variable
opens the answer session. The spec's requirement *Two commands open an answer
session* holds the command line and its install.

**Why:** no environment variable is needed, since neither way in needs one,
and a session that an app starts from its list of sessions, with no terminal,
cannot set one. Fullscreen is the layout the answer session is designed for
and launched into.

**Accepted:** the answer session also works on Claude Code's main screen, but
nothing is designed or built for that screen alone.

#### A discussion runs in the session's own conversation

**A discussion of a question runs in the session's own conversation, with the
question attached to each message as context.** The model reads with its
tools, such as the thread, the code and the specs, before it replies, and
posts and changes nothing. In its reply the model may ask the person a
question, which passes none of the four filters and needs no vetting. This is
the one exception to the inquisitor's rule that an agent asks only through the
picker. The spec's requirement *A discussion runs in the session's own
conversation* holds the details.

**Why:** the model reads before it replies. The person opened the conversation
to talk the question through, and a picker would hide the answer session's
screen.

**Accepted:** the discussion's model runs with the person's tools, so it could
reach the keychain entry holding the person's Linear key. design.md's *The
session's model* gives why no guard is added.

#### Claude drafts a reply only into the prompt box

**The answer session gives the model a tool, `propose_reply`, which puts its
draft reply in the prompt box and posts nothing.** The person edits the draft
and relays it as any answer. The same holds when the person is editing a relay
post. `propose_reply` refuses a call from a subagent. When the person declines
a question because the inquisitor should have handled it, and picks filter 1,
Claude's draft through `propose_reply` may fill in the place the person gives:
the URL of the record, for the `Recorded in: ` line. The spec's requirement
*Claude's draft goes to the prompt box, never to a post* holds the details.

**Why:** Claude may fill in the record's URL because the draft lands in the
prompt box, for the person to confirm.

#### The UI is built from prototype build v0.1-33

**The mod is built from prototype build v0.1-33 alone, which Adam approved by
use on 2026-10-24,** tagged `answer-session-ui-approved-v0.1-33` on
shared-skills (commit fc3c35f; `ui-approved-v0.1-33` in Adam's prototype
repository). It descends from v0.1-30, the whole UI Adam approved by use on
2026-10-20, tagged `answer-session-ui-approved-v0.1-30` (commit c9c6eb5;
`ui-approved-v0.1-30`), declining and the list of questions answered or
handled for the person included. v0.1-33's three commits add only:

- the thread's replies since the question;
- filter 1's recorded answer, shown with the question, for a question from a
  questions branch as well as one in a thread;
- corrected wording and placement of the notice for a stopped post, a post the
  answer session holds back because a reply arrived in the thread since the
  person last read it.

The replies and the recorded answer each have one place on screen, the one the
tag shows, with no switch between layouts. The approval covers the whole
build, including the asker withdrawing their question in the thread (the
prototype's twelfth sample question) and the stopped post's notice, which the
build's notes, written before the tag, list as still to try. Tasks 6.9 and G.1
are done. The tag `answer-session-ui-approved` (f964903) lacks the declining
screens and is not a base.

**Why:** v0.1-33 contains all of v0.1-30, so one base serves.

#### How the approved prototype meets the spec

**The mod keeps the approved prototype's screens, and the spec wins wherever
the two differ.** Task 6.1's rules (a) to (d) state the precedence:

- (a) The mod keeps the approved screens' layout and interaction: the band,
  the keys, the prompt-box flow and the declining screens. Changes needed to
  wire them to real data are allowed; restyling or reorganising them is not.
- (b) Wherever the prototype disagrees with the spec, the spec wins. Task 6.1
  lists the known cases.
- (c) A screen the spec needs and the base build lacks is designed at
  implementation from the prototype's existing patterns, in no new visual
  style. Task 6.1 lists these screens, which ship with no prototype approved
  by use.
- (d) A screen Adam approves separately is taken from its own approved tag.
  v0.1-33 is that build, for the thread's replies and the recorded answer
  shown beside the question.

**Why:** the spec governs what the UI does and posts, as design.md's *The
answer session* says.

#### The separate build was approved before gate one

**The prototype build covering thread replies and the recorded answer was
approved, and its tag named, before Adam approves this change's spec.**
Implementation starts only after both approvals, so no fallback is needed.

*Rejected:* designing those two screens under rule (c) if the build were late:
approving the build first made a fallback unnecessary.

#### Some answer-session details are decided at implementation

**Some details of the answer session are decided at implementation, with no
requirement added; task 6.11 lists them.** They are:

- how a question's options are parsed from its thread;
- a draft's privacy;
- an asker's reply revising the options;
- what agreeing with a suggested verdict posts, and what citing a lore entry
  posts;
- the UI of the relay notice, the notice shown for the comment GitHub Actions
  posts when a pull request changes the person's relay file, designed under
  task 6.1's rule (c).

Decided, not left to implementation, and stated in the spec: that
`propose_reply` refuses a call from a subagent, and that its draft may fill in
the record's URL when the person declines under filter 1, both in *Claude
drafts a reply only into the prompt box*; what agreeing to a shown recorded
answer posts, in *Agreeing to a recorded answer is a filter 1 decline*; and
that citing an `active` lore entry in scope pushes a citation file, in
*A person's cite pushes a citation file*.

### Relaying answers

#### The thread is the durable record of an answer

**An answer's durable record is the relay identity's reply in the question's
thread.** Whether a question is answered, or waiting for the asker, is read
from its thread, kept current by polling. The relay's own reply marks the
question answered; any other reply is shown to the person and leaves the
question's state as it was. The thread is fetched again when a question comes
on screen and its channel's last poll is more than about a minute old, and
once more before relaying. The answer-session spec's requirements *The thread
is the durable record of an answer* and *The thread is read again before a
question is shown and before a post* hold the states and the fetches.

**Why:** design.md's *The thread is the record* gives the reasoning: the
thread is the one place every machine, and the asker, can read.

#### `User says: ` answers, `User asks: ` asks the asker

**A relay post that answers starts with `User says: `, and one that asks the
asker starts with `User asks: `.** "User" is literal in both prefixes, never
the person's name.

**Why:** "waiting for the asker" is read from the thread, which needs a mark
that every machine, and every surface, can read there.

#### A relay post gets no prose pass and no vetting

**A relay post is the person's words, so neither prose's pass nor the
inquisitor's filters apply to it.** The answer session posts it by running the
relay identity's skill as a command on the host, through the mod's own process
call, never as a tool call of the session's model, so neither post hook sees
it. The answer-session spec's requirement *A relay post is posted by a host
command, unvetted* holds how the command runs and the credential scan it gets
instead.

**Why:** a prose rewrite would post words the person did not confirm. The
filters guard a person's time against an agent's questions, not the person's
own words. design.md's *What the answer session posts, and what it logs* gives
the rest.

#### Discord relay posts: no header, mentions that ping

**On Discord the answer session posts through discord-bot with none of its
header options and with its normal mention rewriting on, so a post starts with
its prefix and an `@name` in the person's answer notifies that member.** After
each Discord relay post, and after each edit of one, the answer session shows
the person discord-bot's warnings, so they learn when an `@name` pinged no
one. Setup does not fail the Discord relay when `check` reports `memberSearch:
false`. The answer-session spec's requirement *An answer is relayed as the
person's words* holds the details.

shared-skills PR #1, merged, provides the header-less post: discord-bot's
`post` adds a header only when `--agent`, `--session` or `--project` is given,
and `header()` returns an empty string otherwise
(`.agents/skills/discord-bot/scripts/discord_bot.py` on main at 90a0237). No
Discord channel waits on a further discord-bot option.

**Why:** the person's own @-mentions should ping, as in a comment of theirs. A
`Recorded answer: ` post quotes nothing, so no relay post repeats a record's
@-mentions. An edit can drop a ping, so its warnings are shown too.
design.md's *Polling while open, with the person's credentials* gives the same
reasoning.

*Rejected:* posting with mention rewriting off: it existed only to stop a
quoted record's @-mentions notifying people again, and no relay post quotes a
record.
*Rejected:* failing setup on `memberSearch: false`: the warning at each post
tells the person instead.

#### The person can ask the asker

**When the person can't answer without clarification, they can ask the asker
instead, and the question then waits for the asker's reply.** An Igor's worker
asks in its handback comment and is gone, so a reply to its question reaches
whichever worker next takes the item; asking back is therefore mostly for
people's questions. The answer-session spec's requirement *The person can ask
the asker* holds the details.

#### Editing a relay post

**The person can edit a relay post later, where it was posted; the relay keeps
each post's id for that.** Editing a post the answer session made by itself
makes it the person's words: it starts with `User says: ` in place of
`Recorded answer: ` or `Inquisitor: `, since the person confirmed its new
text. When an edit leaves a `User says: ` answer to a question a
questions-branch log file holds, including an edit of an automatic post, the
answer session pushes a new log file with the edited answer. The
answer-session spec's requirements *A relay post can be edited where it was
posted* and *An edit to a questions-branch answer pushes a new log file* hold
the details.

**Why:** a file on a questions branch never changes, so without a new file the
branch would keep the first answer. Which file then counts is in *The newest
proven answer counts*.

**Accepted:** the person can edit only a question's latest relay post.

#### A rephrased answer carries its rephrasing, and the asker logs it

**A rephrased answer's relay post gives the rephrased question and a
one-sentence summary of the discussion on lines of their own after the answer,
and the asker, not the answer session, logs them.** The session's model drafts
both at the privacy of what the question concerns, generalising or leaving out
more private context, and nothing is posted until the person confirms the
whole post. The asker's agent adds them to the question's log file under `##
Rephrased question` and `## Discussion`. Where the answer session itself logs
a rephrased answer, for a questions-branch question, the file's answer is the
relay post's whole text, its `Rephrased question: ` and `Discussion: ` lines
included, and the file's rephrasing sections hold those lines too. The
answer-session spec's requirement *A rephrased question is answered with its
rephrasing* holds the post's layout.

**Why:** the log file belongs to the asker's work, often on a branch not yet
merged, and the asker already records the answer there; if the answer session
wrote it, each rephrasing would need its own pull request. A reader confirms a
logged answer only when it equals the linked comment, so a file recording the
answer alone would leave every rephrased answer unconfirmed.

*Rejected:* new frontmatter keys for the rephrasing: every frontmatter value
is one quoted line, and a question's text is not.

#### A questions-branch question is answered by a new log file

**A question from a lore repository's questions branch is answered by pushing
a new log file there, holding the question and the answer and naming the
answered file in `answers`, under the rules for an answer the person gave in
the session.** Asking the asker and editing are not offered for it. When the
file's `asked_in` links a post that also asked the question, the question is
shown once, from the post: the answer session relays the answer in the thread
and also pushes the log file. With no thread, the file alone answers it. The
answer-session spec's requirements *A questions-branch question is answered by
a new log file* and *A questions-branch answer file records the answer as
given* hold the details.

**Why:** the questions branch never changes a file once pushed. design.md's
*What the answer session posts, and what it logs* gives the reason for
answering in both places: neither the asker reading the thread nor an agent
searching the branch misses the answer.

#### An answer file records the question the person saw

**An answer to a linked message records the message's question as the person
saw it, not the question the log file holds.** A lore repository more visible
than the thread needs no rule of its own: an `asked_in` link, and so the
message it points to, is written only where the lore repository is no more
visible than the thread. The one case left is a lore repository made more
public later, which publishes everything already in it, so the answer file
adds nothing worse.

**Why:** a log file whose `asked_in` points at an unrelated message would
otherwise get the person's answer recorded, as a decision, against words the
person never saw.

*Rejected:* showing the file's question beside the message.
*Rejected:* a rule of its own for a lore repository more visible than the
thread, either generalising the message's words or relaying only in the
thread: the case barely arises, as above.

#### An answer file names the file it answers

**An answer file names, in its `answers` key, the one questions-branch file it
answers, as a handled file's `closes` does, instead of answering every file
with the same question.** The `log` command writes `answers` only when it
names a file already on that questions branch that holds no answer inside it.
Answer files naming a file do not count as its answer for this test, so later
answer files naming it are still written. igor PR #216 is asked to refuse a
worker's file holding `answers`, so that the Igor adds the key itself and #216
pushes only what the Igor writes; *Open Questions* carries that request. Which
answer file counts as a named file's answer, and how filter 1's search still
groups answers by hash, are in *`answers` decides a named file's answer; the
search groups by hash* and *A named file's answer must be the person's own,
added alone*.

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
such as an `input` file or an unanswered one, supersedes nothing. The
inquisitor spec's requirements *Among files with the same question, only the
newest proven answer counts* and *A file is as new as its proof, and
supersedes only if it would count* hold the details.

**Why:** ordering by the commit's place in the branch would let anyone with
push access re-push a copy of an older proven file and revert a newer answer.
If a file that would not count could supersede, a person without write access,
whose answer to a handback an Igor logs as `input`, would undo a maintainer's
answer.

#### `answers` decides a named file's answer; the search groups by hash

**`answers` decides only which answer a named file has: among the answer files
naming it, the newest counts. Filter 1's search groups every answer file by
the hash of its question, with or without `answers`, and the newest in each
group counts.** Two answer files naming the same file can record different
question words, since each records the question as the person saw it, so
they can fall in different hash groups. When a newer answer file names the
same file, the older one is labelled superseded in the search too, and stops
counting, even in its own hash group, where it may still be the newest. The
inquisitor spec's requirements *A named file's answer is the newest proven
answer file naming it* and *A replaced answer file stops counting even in its
own hash group* hold the details.

**Why:** a later asker has no file of its own to name, so the search across
askers can only find earlier answers by hash. Two answer files naming one file
can record different words, each the question as the person saw it, and
without the second rule the replaced file would go on counting in its own
group. design.md's *What the answer session posts, and what it logs* gives
this reasoning.

*Rejected:* deciding a named file's answer by hash grouping: an answer file
names the file it answers exactly, as a handled file's `closes` does.
*Rejected:* taking files that hold `answers` out of the hash grouping: a later
asker's search, which has no file to name, would not find them.
*Rejected:* letting a replaced answer file go on counting in its hash group:
the person's changed answer would not be the only one that counts.

#### A named file's answer must be the person's own, added alone

**An answer file counts as a named file's answer only when its proof, a
comment link or a signature, is the person's, and its commit adds that answer
file alone.** For a log file that tags no one, an answer counts only when its
proof's account has `decision` authority under filter 1's rules for that
file's repository, which for a questions-branch file is write access to the
lore repository. Both specs use this one test, and the inquisitor spec's
requirement *A named file's answer is the newest proven answer file naming it*
holds it.

**Why:** otherwise a copy of another question's answer, pushed in one commit
with other files, could become a named file's answer. design.md's *What the
answer session posts, and what it logs* gives the reasoning for files that tag
no one.

*Rejected:* accepting the risk that such a copy becomes a named file's answer.
*Rejected:* answering files that tag no one only through filter 1's hash search.

#### A named file stays shown until its answer counts

**A file named in `answers` stops being shown only when the answer file counts
as the person's answer, proven as filter 1 proves one.** Otherwise it stays
shown, with that answer beside it as input. The answer-session spec's
requirement *A questions-branch question's state is read from its branch*
holds the rule.

*Rejected:* letting any answer file hide the file it names, whether or not it
counts.

#### Questions-branch answers relayed on Linear or Discord

**When the answer session relays on Linear or Discord an answer to a
questions-branch question, it logs the answer with that relay post's URL as
its `answer_link`, a pointer that nothing fetches.** The log file records,
word for word as quote lines, the text the answer session relayed. The `log`
command fetches only a github.com link and passes no other link to any GitHub
API call, and a non-GitHub link proves no writer. The inquisitor spec's
requirement *A log file and a miss file have one format* holds the Linear and
Discord forms, and *A log file's repository keys and answer_link are checked
before use* the github.com forms and the rule that nothing fetches another
link.

**Such a file counts through the signature on its commit, whatever surface
relayed the answer.** When the commit that adds it carries a signature GitHub
verifies for `answered_by`, the file counts as a decision, as a picker answer
does when the agent logs it with a signed commit; without one, it is input. An
answer typed directly on Discord, Linear or Slack, outside the answer session,
stays input until a decision document, such as igor's scribe's record, records
it.

**Why:** the answer was given in the answer session and logged from the
person's machine under their signature. Only an answer typed directly on the
other surface has no such proof.

*Rejected:* counting every answer relayed off GitHub as input.

#### `answer_link` and `asked_in` are withheld where they would leak

**A Linear or Discord `answer_link` or `asked_in` is written only when the
lore repository is private, and a github.com one only when the lore repository
is no more visible than the repository the URL points into.** Otherwise the
log file is written without that key. A file written without its `answer_link`
still records the answer, and counts only through its signature. The
inquisitor spec's requirements *The log command withholds a link where it
would leak* and *A log file and a miss file have one format* hold the details.

**Why:** the URL would point the readers of a more visible lore repository
into a more private thread. A Discord URL holds the server's and channel's
ids, and a Linear URL the workspace, issue and title. A Linear or Discord
thread counts as private, so a lore repository that is not private is more
visible than it. A github.com link into a more private repository leaks the
same way.

*Rejected:* always writing the URL, on any surface, and so accepting the leak.
*Rejected:* writing no log file in a lore repository that is not private: the
file without the link still records the answer.

#### An answer that cannot reach its thread is kept pending

**An answer that cannot be posted in its thread is kept, as answered, not
relayed, never lost.** That covers a relay that lacks permission, a channel
that is off, a post that is refused or fails, an answer given on a machine
that does not read the thread's channel, and an answer held back by a reply
that appeared just before posting. The person is always told the asker has not
got the answer yet, so they can relay it by hand. A failed post keeps the
answer this way, since leaving the question as it was would drop the typed
answer. The answer-session spec's requirements *An answer that cannot reach
its thread is kept pending* and *Only the person is told an answer is pending*
hold the details.

**Pending answers are kept in a separate pending list, which reuses the main
queue's UI almost exactly:** in Adam's words, the queue's screens, holding
pending answers. Once setup's check of posting in a pending answer's channel
passes, the answer goes back into the queue, with the answer kept, for the
person to approve again. An answer also leaves the list once any machine's
relay post naming the question appears in the thread. A pending answer that no
check brings back stays on the list indefinitely: one the surface refused for
its text, such as one too long, one held back by a new reply, or one given on
a machine that does not subscribe to its channel. One refused for its text
stays even where no check can read posting rights, so that the refusal also
turned its channel off: the recheck does not bring it back. The person can always post,
edit or drop any pending answer.

**No other machine is told of a pending answer.** While one machine holds it,
the person's other machines read only the thread, and ask the question again
as usual.

**Why:** the list reuses the queue's approved patterns, so it needs no
prototype round of its own. An answer that no check brings back can stay
because the person can always act on it.

**Accepted:** another machine may ask a question that one machine holds an
answer for. Two-machine cases whose worst case is a re-ask are accepted.

*Rejected:* showing pending answers as a state in the list of questions
answered and handled.
*Rejected:* returning a pending answer that no check brings back to the queue
at the next opening.
*Rejected:* an "Answered on another machine, not relayed" notice on the other
machines, offering to relay, edit or answer afresh, even one offered only for
a file linked by `asked_in`.

#### The push order for a questions-branch answer

**For a question a questions-branch file holds, the answer session checks the
thread, records the owed push in the state folder, posts the relay post, and
then pushes the answer file with the post's link as its `answer_link`.** A
failed push is retried at each poll and each opening until it succeeds, as a
handled file's is. An answer held back because the check finds a new message
pushes its file only when it is finally posted, and dropping it leaves no
file. Once the answer is posted and pushed, the question is answered, and a
later message in the thread is judged like any new message: a new question if
it asks the person something, ignored otherwise. The answer-session spec's
requirements *A questions-branch answer's file is pushed after its post* and
*An owed push with no URL is settled from the thread* hold the details,
including how a crash before the post is settled.

**Only an answer pending because its thread's channel is off, or not
subscribed on this machine, is pushed at once, unchecked, with no
`answer_link`.** That holds whether the channel was off when the person
confirmed the answer or a refused post turned it off; the file is then pushed
once the post is refused. Whether a post was tried makes no difference. What
later happens to that pending answer decides whether another file follows:

- posted later unedited: nothing new is pushed;
- posted later edited: a new answer file is pushed, with the relay post's
  link as its `answer_link`;
- edited, then dropped: nothing new is pushed, and the file already pushed,
  holding the original text, stays the person's answer.

**Why:** a thread answered with no file is not acceptable, so the file follows
the post and its push is retried. Recording the owed push before the post
means a crash between them does not lose the answer file. Checking the thread
first lets the person see a new message before anything is pushed. design.md's
*What the answer session posts, and what it logs* gives the same reasoning.

A failed push's retry is also dropped once an answer file that counts as the
person's answer names the same questions-branch file, and this machine
first saw that answer file at a fetch after it recorded the owed push. The
second condition keeps a file this machine already knew from cancelling the
push. For example, an answer pushed at once and then posted edited owes a new
file; without the condition, the file pushed at once would cancel that push.
That reason is the author's inference, which *Conflicts for Adam to decide*,
under *Open Questions*, asks Adam to confirm.

**Accepted:** a file pushed at once gives up the comment link that would prove
it on GitHub, and counts only through its signature. A dropped pending answer
of that kind leaves its file on the branch, still answering the file it names.

*Rejected:* pushing every answer file when the person confirms: a held-back or
dropped answer would leave a file for an answer never posted.
*Rejected:* pushing the file of an answer whose thread cannot be read only
once it is relayed.
*Rejected:* pushing no file for an answer whose refused post turned its channel
off, unlike one whose channel was already off.
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

It posts neither on a question with a category. On a question from a
questions branch, with no thread, it shows the recorded answer or the verdict
to the person instead.

**The session's model writes no word of an automatic post.** A recorded
answer is posted as `Recorded answer: see the record below.`, whatever the
record, a log file included, then `Recorded in: <URL>` holding filter 1's
hit, then, on GitHub, the `Re: ` line every relay post ends with; it quotes
no answer. An `Inquisitor: ` post is a fixed text for each of filters 2, 3
and 4, naming the filter and giving its action. Its text being fixed apart
from the record's URL, an automatic post gets no prose pass and no vetting,
as a relay post gets none. The answer-session spec's requirements *Filter 1
runs on every incoming question* and *Filters 2 to 4 judge every incoming
question* hold the texts.

- It posts a recorded answer by itself only when the record is no more private
  than the question's thread: on GitHub, when the record's repository is no
  more visible than the thread's; on Linear and Discord, only when the
  record's repository is public. Otherwise it shows the recorded answer beside
  the question, for the person to relay or to agree to, as *Agreeing to a
  recorded answer is a filter 1 decline* says.
- When a lore entry is the recorded answer, it pushes a citation file, as any
  session's filter 1 does.

**Why:** a thread's text reaches the model, so with fixed texts a crafted
thread can at worst choose which fixed reply or which record is posted. A log
file's answer is a whole comment, which could hold @-mentions that would
notify people again on GitHub, or a `Recorded in: ` line of its own, so no
answer is quoted. design.md's *What the answer session does by itself* gives
the reasoning.

*Rejected:* a recorded answer in a sentence the model writes: a crafted thread
could steer it.
*Rejected:* quoting the answer with its mentions neutralised: it needs a rule
per surface.

#### No automatic post repeats one in its chain of replies

**No automatic post repeats one already made anywhere in its chain of
replies:** the reply, the relay post it answers, the question that relay post
names, and so on back. A repeat goes to the person. The answer-session spec's
requirement *A reply to an automatic post is a new question* defines the
chain.

**Why:** checking only the post a reply answered would let an agent that kept
replying get filter 2's text, then filter 4's, then filter 2's again with no
person seeing it. design.md's *What the answer session does by itself* gives
the same reasoning.

#### A post the person chose says so

**A post made when the person declines because the inquisitor should have
handled it, choosing filter 2, 3 or 4, is that filter's fixed text followed by
the line `The person chose this filter.`,** which no automatic post holds. The
answer-session spec's requirement *A filter 2 to 4 reply the person chose says
they chose it* holds the details.

**Why:** an asking agent acts on filter 3's or 4's reply only when the person
chose it, and the line is how it tells.

### Incoming questions, declining and handled files

#### Which questions count as an agent's

**A question counts as an agent's when its message's author is a bot account,
or when it is a log file on a questions branch, unless it is a relayed
question.** A bot account is a GitHub App, a Linear app user, or a Discord bot
or webhook. A questions-branch log file counts as an agent's because only the
inquisitor's script writes one. A relayed question is a post starting `User
says: ` or `User asks: ` from any bot account, on any surface. It is the words
of the person whose answer session posted it, such as another person asking
this one something through their own relay, so it counts as a person's
question. Every other question counts as a person's, including an agent's
question posted with a person's own credentials, which the answer session
cannot tell apart. The answer-session spec's requirements *A relayed question
is a person's question* and *An agent's question comes from a bot account or a
log file* hold the definitions.

**Why:** only an agent's question gets an automatic `Inquisitor: ` reply.
Erring towards a person's question keeps those replies off people's questions,
so a person never gets a reply nobody wrote. design.md's *What the answer
session does by itself* gives the reasoning.

#### Filter 1 runs on every incoming question

**Before it shows a question, the answer session runs filter 1 on it, whether
a person or an agent asked it, a relayed question included.** When an answer
with authority is recorded and the question has a thread, the answer session
answers by itself with a `Recorded answer: ` post, never one starting `User
says: `. It lists the question as answered for the person, who can edit that
post as any relay post. The post's form, and when a record is too private to
post by itself, are in *What the answer session posts by itself*.

The session's model first judges whether the question has a category. The
answer session passes a question with a category to the script on standard
input, with its category, never in a file, and the script then searches no
source outside the machine. The answer session posts nothing by itself on such
a question. Other questions reach the script in private files, as an agent's
do.

When filter 1 answers an agent's question by itself, the answer session logs a
miss against filter 1. A person's question answered this way logs none. The
spec's requirements *Filter 1 runs on every incoming question*, *A question
with a category reaches filter 1 on standard input* and *Filter 1's answer by
itself to an agent's question logs a miss* hold the details.

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
handled for the person. For a person's question, a relayed question included,
it only shows the person its suggested verdict, and the person decides. No
post the answer session makes by itself is presented as the person's words,
and each can be edited. The spec's requirement *Filters 2 to 4 judge every
incoming question* holds the three fixed texts.

**Why:** design.md's *What the answer session does by itself* gives the
reasoning: the person sees only what needs them, and a thread's text can at
worst choose which fixed reply is posted.

#### A reply to an automatic post is a new question

**A reply to a post the answer session made by itself is a new question, as a
reply to any relay post is: the filters judge it again, and the answer session
may answer it by itself again.** It never repeats an automatic post within one
chain of replies; a repeat goes to the person, as *No automatic post repeats
one in its chain of replies* says. When an asker's filter 1 cannot count the
place a recorded answer names, the asker treats the post as input, and its
question stands.

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
Otherwise the reply is input, and the question stands. So every `Inquisitor: `
reply on Linear and Discord is input, and so is every one on GitHub until task
0.21 shows that GitHub reports which App wrote a comment. An agent that acts
on a reply takes that filter's action and records its choice as its own filter
would have. The inquisitor spec's requirement *An answer session's automatic
reply is a verdict, not a person's answer* holds the rules for a `Recorded
answer: ` reply, and *An Inquisitor reply is acted on only from a writer's
relay App* those for an `Inquisitor: ` reply.

**Why:** a crafted thread can choose which fixed reply the answer session
posts by itself. Filter 3's and 4's replies decide a question, while filter
2's only defers it. Without the write-access condition, anyone who can comment
could post `Inquisitor: filter 4` and have an agent decide a maintainer's
question. design.md's *What the answer session does by itself* gives the
reasoning.

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
person chose it, and its posts start with the reserved prefixes, as the
automatic posts do. The person can still answer on the surface by hand. On a
question with no thread, nothing is posted for any filter; for filter 1 the
person is shown the recorded answer, and the question closes. On a question
with a category, nothing is posted, and the question closes. Filter 3 also
offers the choice "the agent shouldn't have asked", described in *Messages
that are not questions are ignored*.

A question declined with nothing posted is kept closed in this machine's state
folder, as a question set aside for later is, and that close does not reach
the person's other machines. A questions-branch file that holds the question
is closed everywhere by a handled file. A question declined with a post takes
its state from its thread, as any question does. The spec's requirement *The
person can decline to answer* holds the details, with these requirements:
*Declining for the inquisitor posts the picked filter's reply*, *A filter 2
to 4 reply the person chose says they chose it*, *The person's filter 1 reply
links the record they chose*, *The preview warns when a filter 1 record is
more private than the thread*, *A decline with no thread or with a category
posts nothing*, *Filter 3 also offers that the agent shouldn't have asked*, *A
decline for the inquisitor logs a miss once it takes effect*, *A filter 1
decline cites its lore entry once*, *A decline with nothing posted closes a
thread copy on this machine only* and *Only a thread copy declined with
nothing posted is reopened*.

**Why:** a conversation that is over and a message that isn't a question
behave alike, so one reason covers both. That reason's name keeps clear of
filter 3's text, "not a real question". The person, not the session's model,
picks the filter, and sees the exact post before it goes out.

*Rejected:* separate reasons for a conversation that is over and a message
that isn't a question: they behave alike.
*Rejected:* the session's model asking the person which filter should have
stopped the question, and why: the person picks the filter and confirms the
exact post instead.

#### Messages that are not questions are ignored

**A message of the first or second source, a mention of the person or a
mention of or reply to the relay, that the session's model judges clearly not
a question is ignored: it is not shown, nothing is posted on it, and nothing
is closed.** An unclear one is shown. The rule covers only those two sources,
so a non-question from a review request, an assignment or a questions-branch
file reaches the queue without the session judging it.

One reply is never ignored: an asker's reply to the relay's `User asks: ` post
puts the person's waiting question back in the queue, whether or not the reply
is itself a question. The spec's requirement *The thread is the durable record
of an answer* states it.

"Rhetorical" is not a category. The inquisitor has an asking agent rewrite a
message that is not really a question as a statement, and filter 3's automatic
reply is only for a real question that did not need asking. So an agent's
rhetorical message in a thread gets no post.

When a non-question reaches the person's queue anyway, the person declines it
under whichever reason fits:

- under reason 1, nothing to answer, when the answer session's own judgement
  let it through: nothing is posted, and no miss is logged;
- under reason 2, choosing filter 3's "the agent shouldn't have asked", when
  the asking agent should not have written it: nothing is posted, and a miss
  against filter 3 is logged against that agent.

**Why:** a message picked up by mistake is the answer session's own
misjudgement, and no asker erred, so it logs no miss. Filter 3's fixed text
tells the agent to take an option that has merit, which a non-question does
not offer, so "the agent shouldn't have asked" posts nothing.

*Rejected:* filter 3's automatic reply on a rhetorical message: that reply is
only for a real question that did not need asking.
*Rejected:* a rhetorical fixed text of filter 3's own: the decline reasons and
filters 2 to 4 already cover a question that needs no answer.
*Rejected:* a miss against the source that picked the message up: no asker
erred.
*Rejected:* posting filter 3's fixed text under "the agent shouldn't have
asked": it tells the asker to take an option it does not have.
*Rejected:* calling filter 3's choice "not a question": only reason 1 says
"not a question", so two labels never share a name.

#### Declining with nothing to answer closes only that question

**A reason 1 decline closes only the declined question, and no later message
in its thread reopens it.** Every later message in its thread that the four
sources name, unless the ignore rule drops it, is shown on its own as a new
question, on every machine. That includes the asker's unthreaded follow-up
after a relay post and a threaded reply to one, under the second source; a
message that mentions the person or a relay identity, by its mention; and a
review request or an assignment made after the close. Any message posted in a
thread after a handled file closed its question is likewise shown as a new
question. The spec's requirements *Later messages after an answer or a decline
are new questions* and *A question is resolved once answered or declined* hold
the details.

**Why:** a reason 1 decline is held in each machine's own state folder. If it
stopped later messages counting, a follow-up would count on one machine and
not on another.

*Rejected:* a follow-up that stops counting after a reason 1 decline: it would
stop counting only on the machine that declined.
*Rejected:* a threaded reply reopening the declined question on one machine:
the reply is shown as a new question instead.
*Rejected:* dropping a reply that arrives after its question closed: it is
shown as a new question instead.

#### The answer session writes a handled file on every close of a questions-branch file

**Whenever the answer session closes a question that a questions-branch file
holds, it pushes one handled file for each such file, naming it.** A file
holds the question when the question was shown from that file, or when the
file's `asked_in` links the closed thread message. The answer session closes a
question by declining it, agreeing to a recorded answer included, or by
posting a `Recorded answer: ` or `Inquisitor: ` reply on it, with a thread or
without. A handled file is the one log file a decline pushes.

A handled file holds only two keys: `handled`, the day the question closed,
and `closes`, the unique file name of the one questions-branch file it closes.
It holds no question text, its slug is always `handled`, and it has no body.
It closes the named file without answering it. Filter 1's search never matches
a handled file, so a handled file never stops a question for a searching
agent.

The asking agent writes no handled file. The script's `log` command writes one
only under an option the answer session alone passes. An Igor worker could
still report a file holding these keys for its Igor to push; refusing such a
file is asked of igor PR #216, and is open on its side. The spec's
requirements *A handled file closes a questions-branch question* and *A log
file and a miss file have one format* hold the format, and *A handled file is
pushed once its close takes effect* when the push happens and its retry.

**Why:** without a handled file, a questions-branch file whose question was
closed would stay unanswered and come back. A machine whose first poll of a
thread comes more than 14 days after the question was asked there never reads
the thread copy, and would show the file as a new question. The answer session
writes the file itself, so no rule depends on checking which App wrote a post,
which waits on task 0.21. Holding no question text, a handled file never
carries a private item's question into igor's search.

*Rejected:* the asking agent marking its own file handled when it reads the
answer session's post: it would have to check the post's author, which waits
on task 0.21.
*Rejected:* copying the question's text into the handled file with the
original's `asked_from`: nothing needs the text, and keeping it out keeps
private questions out of the search.
*Rejected:* writing no handled file for a question with a category: a handled
file holds no question text, so it reveals nothing about one.
*Rejected:* keeping `repository` in the handled file for the visibility
checks: it served only the matching that exact identity removed.

**Accepted:** a record that the asking agent's own filter 1 would not count
still closes the question in the person's queue. The asker's question still
stands in its thread, and the asker can ask again. Asking again is a
legitimate request, since the asker may be unable to see or count the recorded
answer: a private record, one withheld by the visibility rules, or one without
authority.
*Rejected:* having the asking agent decide the close: the answer session
closes it, as above.

#### Closing works by exact identity, never by matching

**A handled file closes the one questions-branch file its `closes` key names,
on every machine and for good, and nothing else.** A thread copy, a question
shown from its thread, is closed on every machine only by the relay posts in
its thread. A thread copy declined with nothing posted is closed on that
machine only, and can be reopened there. When a close concerns more than one
questions-branch file, one handled file is pushed for each. No question hash,
topic repository, `over` key or time comparison takes part in closing. Nothing
reopens a file a handled file closed.

**A file a handled file closed is still unanswered,** so an answer the person
gives to its thread copy, on a machine where that copy is still open, still
pushes a log file answering it.

**Why:** matching on a question's words, on a judgement each machine made for
itself, or on clocks kept giving two machines different answers, and each fix
raised another case. Exact identity cannot disagree. design.md's *What the
answer session posts, and what it logs* gives the reasoning.

**Accepted:** a thread copy declined with nothing posted on one machine shows
again on the person's other machines, where they can decline it again.

*Rejected:* closing every copy whose question has the same hash, thread copies
included, on every machine: matching on words gives machines different
answers.
*Rejected:* closing copies by topic repository, whether each machine's own or
the one the closing machine recorded: each machine's judgement of it can
differ.
*Rejected:* closing only copies asked by the handled day, or before the
handled file's commit time: comparing clocks gives machines different answers.
*Rejected:* an `over` key limiting a reason 1 decline's handled file to the
copy declined: it served only matching.
*Rejected:* one handled file per topic repository: each handled file names one
file.
*Rejected:* hiding a questions-branch file whenever any relay post names the
same question: that is matching by words.
*Rejected:* pushing no answer file for a file a handled file names: a handled
file closes a file without answering it.

#### Reopening a declined question

**The person can reopen a thread copy they declined with nothing posted, on
the machine where they declined it; reopening puts it back in their queue.** A
question declined with a post cannot be reopened: the thread records how it
was handled, and the person changes that by editing the post. A
questions-branch file a handled file names cannot be reopened, whether it was
shown from the branch or from a thread, since the handled file closes it
everywhere for good. A thread copy of that file stays reopenable on its
machine. A miss already logged for a reopened question stays, since a miss
file is never changed, and nothing records that the person took it back.

**Why:** after a post, the thread, which every machine reads, is the record of
how the question was handled.

*Rejected:* reopening a question on this machine whatever its thread shows:
the thread records the handling once a post went out.

#### A person's cite pushes a citation file

**A person cites a lore entry by answering a question with it, or by declining
under reason 2 with filter 1 and naming it as the record, agreeing to a shown
recorded answer included.** The answer session then pushes a citation file for
the entry only when it is `active` and its scope covers the question, under
the visibility rules of *A citation holds nothing about the question*, which
withhold a citation from a place less private than the question. The person
can cite any other entry; that pushes nothing. A decline's citation is pushed
once, to the entry's own lore repository, whether or not its miss is pushed.
The asking agent pushes no citation for an entry a `Recorded answer: ` post
names, as *What an asking agent does with an automatic reply* says. The spec's
requirements *A person cites a lore entry by naming it as an answer or a
record*, *A person's cite of an active entry in scope pushes a citation file*
and *A filter 1 decline cites its lore entry once* hold the details.

igor PR #216 is asked to widen its definition of a citation to include a
person's cite; that request is open on #216's side.

**Why:** filter 1's own citation, and igor PR #216's, are pushed only for an
`active` entry in scope, and a person's cite follows the same rule. One
question gives one citation.

*Rejected:* a citation for any cited entry: citations count only `active`
entries in scope, as filter 1's and igor's do.
*Rejected:* the asking agent pushing the citation when it acts on a `Recorded
answer: ` post: the answer session already pushed it.
*Rejected:* pushing a decline's citation only when its miss is pushed: the
only duplicate left is two machines declining one question, which is accepted
below.

**Accepted:** two machines can each push a citation for one question: when the
same question is open on both at once, or when a thread copy declined with
nothing posted on one machine is declined again on another. It is rare, and no
rule is added.
*Rejected:* re-reading the questions branch before a decline's pushes: the
case is rare.
*Rejected:* pushing no citation for a reason 2 decline: the case is rare.

#### Agreeing to a recorded answer is a filter 1 decline

**When the answer session shows a recorded answer instead of posting it, the
person may agree to it, and agreeing is declining the question under reason 2
with filter 1, naming that record.** This holds on every question, in a thread
or with no thread. The decline path does the rest:

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

In a thread, the confirmed `Recorded answer: ` post is the record there. The
answer session still posts a recorded answer by itself only when the record is
no more private than the thread. The spec's requirement *Agreeing to a shown
recorded answer is a filter 1 decline* holds the details.

**Why:** the record exists and filter 1 found it, so a log file pointing to it
adds nothing. Filter 1 should have stopped the question either way, so the
miss is logged. design.md's *What the answer session posts, and what it logs*
gives the reasoning, including what a later searching agent finds.

**Accepted:** agreeing logs a miss on a person's question too.

*Rejected:* not offering agreement for a record more private than the thread:
the warning lets the person decide.
*Rejected:* a log file whose answer points to the record: it adds nothing.
*Rejected:* a record and a `said` of agreeing's own: agreeing is a decline,
and uses the decline's.
*Rejected:* logging no miss when the person agrees on an agent's question:
filter 1 should have stopped it.

#### Misses the answer session logs

**Each miss the answer session logs goes to the questions branch of the team's
lore repository that serves the repository the question concerns, pushed
directly by the script, with no pull request.** The session's model judges
the repository the question concerns as the inquisitor's spec has an agent
judge it; on GitHub, when it can't tell, that is the repository holding the
question's thread. The answer session logs a miss in three cases:

- against filter 1, when filter 1 answers an agent's question by itself;
- against the failed filter, when filters 2 to 4 handle an agent's question by
  itself;
- against the filter the person picks under reason 2, agreeing included, on a
  person's question as on an agent's.

A reason 1 decline logs none. A miss the answer session logs by itself has
`said` `answer session: clearly filter <n>`. Under reason 2, `said` is the
person's note, or `the inquisitor should have handled it` when they typed
none. A miss is pushed even when one with the same question and `filter` is
already on the branch, so a question judged on two machines gives two misses.

A miss for a question a questions-branch file holds copies that file's
`asked_from`, so the visibility rules apply to the miss as to the file. It is
the one exception to the rule, in *The Igor writes `asked_from` on every file
it pushes*, that the script never writes `asked_from`. igor PR #216 says only
an Igor writes `asked_from`; allowing for this second writer is open on #216's
side.

No miss is written when the question has a category, concerns no repository,
or has no configured lore repository serving its repository. None is written
either when that lore repository is more visible than the repository or than
the question's thread. The answer session then tells the person why, and the
question still closes. The inquisitor's rule that a question with no log file
gets no miss does not apply here. The spec's requirements *The answer session
logs its misses on the team's lore repository's questions branch*, *A miss
records who judged it and copies its file's asked_from* and *The answer
session writes no miss it cannot place privately* hold the details.

**Why:** the answer session cannot see where the asker logged the question,
which is often an unmerged branch. The questions branch takes a direct push,
so no miss needs a pull request. The fixed `said` lets a review of misses tell
the session's judgement from a person's word. Dropping a duplicate miss would
mean matching on words. design.md's *What the answer session does by itself*
gives the reasoning.

*Rejected:* writing the miss where the asker's log file went: the answer
session cannot know where that is, and each miss would take a pull request.
*Rejected:* keeping misses in the state folder: it would be a personal
question log, which this change rules out.
*Rejected:* pushing a miss only when no matching one is on the branch: that is
matching on words.
*Rejected:* no miss for a question whose file holds `asked_from`: copying the
file's `asked_from` keeps the miss as private as the file.

### Linking log files to threads, and handbacks

#### A log file follows its thread message by exact link

**A questions-branch log file for a question the asking agent also asked in a
post holds that message's URL as `asked_in`, and follows the message by that
exact link.** Whatever the answer session decides about the message (showing
it, answering it, ignoring it as not a question, declining it) applies to the
file, which is not shown on its own. A log file with no `asked_in` is judged
on its own, as a question of the fourth source. An answer given through the
message records the message's question as the person saw it, as *An answer
file records the question the person saw* says. The answer-session spec's
requirements *A log file follows the thread message its asked_in links* and *A
log file with no followed link is judged on its own* hold the details,
including which links are followed; the inquisitor spec's requirement *A
questions-branch log file links where its question was asked* holds the order
(post first, then write the log file).

**Why:** a link names one message exactly, so every machine pairs the same
file with the same message. design.md's *What the answer session posts, and
what it logs* gives the reasoning, under closing by exact identity.

*Rejected:* judging every log file on its own: the person would see each
question twice.
*Rejected:* hiding a log file by matching its words to a message: matching
gives two machines different answers.

#### A link this machine never reads is not followed

**A log file whose `asked_in` links a message this machine never reads is
shown on its own, as a question of the fourth source.** Such a message is in a
channel this machine does not subscribe to, or on a surface it has turned off
or cannot read. An answer given to it there is kept pending until it can be
relayed, as *An answer that cannot reach its thread is kept pending* says.

*Rejected:* showing the file nowhere on that machine: the person would never
see the question there.

#### A log file without `asked_in` is never merged

**A log file with no `asked_in`, whether the link was withheld for privacy or
never written, is always shown as its own question.** The answer session never
pairs a file with a thread message by matching their text. design.md's *What
the answer session posts, and what it logs* gives the reasoning.

**Why:** merging's only benefit is avoiding a duplicate, which is low
priority. Any merge rule can pair a message with a file another asker logged
in the same words. A decline then closes that asker's question, or an answer
is recorded against it.

**Accepted:** on Linear and Discord, where the link is withheld from a lore
repository that is not private, and on GitHub, where it is withheld from a
more visible lore repository, the person may see one question twice. The rule
that a cross-machine case whose worst outcome is a question shown twice is
accepted covers it.

*Rejected:* merging a log file and a thread message into one entry when they
ask the same question, with any set of guards: each guard left a case that
closed or answered the wrong asker's question.

#### A bot's question reaches only the first person it mentions

**A message by a bot reaches only the first person it mentions; a message by a
person reaches each person it mentions.** A bot here is any bot or agent
account: an Igor, an agent running the inquisitor, or any other bot. The bot
orders its mentions by importance. For an Igor, Adam decided the order in igor
issue #229, which is open: igor's specs do not state the order. Under it, an
Igor mentions its operator first only when it stops for a reason it detects
itself, then the assignee and the creator; every other handback, a question
included, mentions the assignee and then the creator. The answer session does
not know who an operator is and needs no rule about it. The rule applies to
Igors directly, with no routing by assignment alone while igor's specs lack
#229's order. The answer-session spec's requirements *Whom a message reaches
is set by its mentions* and *A mention names a user outside code, quotes and
links* hold the details: what counts as a bot account and as a mention.

**Why:** each bot question has one owner, so two people cannot give a bot
conflicting answers, and the inquisitor never needs to know an operator.
design.md's *What the answer session posts, and what it logs* gives the same
reasoning.

*Rejected:* a handback reaching the assignee unless it mentions someone else
and not them: it gives a bot question more than one owner.
*Rejected:* routing an Igor's handback by assignment until igor's specs state
#229's order: no one uses igor yet, so the spec states only the end state.

#### igor's handback marker

**The answer session identifies an Igor's handback by a fixed marker igor
gives its handback comments: a handback is a comment by an `igor-` App holding
that marker, and an Igor comment without it is not a handback.** igor chooses
the marker's form, and task 0.6 records it. The post hook does not read the
marker, as *No exemption for an Igor's handback* says. The `answer-session`
spec's requirement *A handback is an igor- App's comment holding igor's
marker* holds the details; the entries below hold how the answer session shows
handbacks.

**Why:** an Igor posts other comments on the item too. The marker tells a
handback from them, and text the Igor quotes from its item cannot produce it.

*Rejected:* counting every comment by an `igor-` App as a handback.

#### Only an item's newest handback is open

**When an Igor posts a newer handback on an item that still holds an older
unanswered one, only the newest counts as open.** A handback is as *igor's
handback marker* defines it. An item an Igor handed back, and assigned to the
person, is shown only through its newest handback. Every older handback is
passed over by a reading rule each answer session applies to the thread, with
no coordination between machines. Nothing is written for it: no post, edit or
handled file. It drops out of the queue and is never shown again, even once
the newest is answered. The newest handback is open until a relay post naming
it answers it, or handles it with a `Recorded answer: ` or `Inquisitor: `
post. The answer-session spec's requirements *Only an item's newest handback
is shown* and *An item's newest handback is open until a relay post names it*
hold the details.

**Why:** a newer handback can follow only once the person returns the item to
the Igor without answering the older one, so the case is rare. The newest
handback says where the Igor is blocked now.

**Accepted:** a passed-over handback's log file stays on the questions branch,
unanswered, and is never shown again. If its blocker still matters, the Igor
asks again on its next run.

*Rejected:* a new log file linking its own handback only while an earlier one
is unanswered: it is less simple than every file linking its own handback, and
guarantees no more.
*Rejected:* an answer naming only the oldest unanswered log file: it answers a
question that no longer says where the Igor is blocked.

#### A handback that mentions no one reaches the assignee

**An Igor's handback that mentions no one reaches the item's assignee, under
the source of questions that is an item assigned to the person.** One that
mentions people reaches only the first one mentioned, under the first source,
as for any bot's message. So on an item assigned to the person, a handback
that mentions people reaches them only if they are mentioned first. For a
handback that mentions no one:

- while the item is assigned to no one, it is shown to no one; once someone is
  assigned the item, it is shown to them;
- an item assigned to someone else is theirs and never appears in this
  person's queue.

The answer-session spec's requirement *A handback that mentions no one goes to
the item's assignee* holds the details.

#### Each Igor log file follows its own handback comment

**An Igor worker's log file links, in `asked_in`, the handback comment that
asks its question, and follows that comment as any log file follows its thread
message.** Answering or declining the handback applies to the file, and an
answer to a handback names only that handback's log file. The file is shown
only while its comment is the item's newest handback, and to whoever that
handback reaches. A later Igor question on an item whose earlier question is
already answered follows that run's new handback comment, which reaches the
person as a new message in an answered thread; the answer is relayed on the
item and logged against the new file. The inquisitor spec's requirement *A
questions-branch log file links where its question was asked* holds who writes
the key and when (the Igor, after posting the comment, applying the
withholding rule). The answer-session spec's requirement *An Igor's log file
follows its own handback comment* holds when the link is followed.

**Why:** each file follows exactly one comment, so one answer never closes the
log files of two handbacks, and the newest-handback rule needs no other
mechanism. It is the simplest mechanism that guarantees this. The Igor
writes `asked_in`, not the worker, because the worker cannot know its
handback comment's URL: the comment exists only once the Igor posts it.

*Rejected:* linking the log file to the assigned item instead of the handback
comment: two handbacks on one item would share one link.
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
that splitting is the last resort. Detail moves first to scenarios, then
reasons move here, then the text is compacted. Only a requirement still too
long after those steps is split, along its own rule boundaries.

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
an implementation pull request.** The other parts of the same feature, such as
its data flow, integrations, setup and rules, still go through both pull
requests, spec then implementation. A spec names a UI only as an interface the
feature's other parts use, and does not describe the UI itself. One exception:
a screen that a spec's task says is designed at implementation, from the
patterns of the feature's approved prototype, is built with no prototype of
its own. The spec still does not describe that screen; the task only names it.
Task 6.1's rule (c) is such a task. `AGENTS.md` states the rule and its
exception.

**Why:** whether a UI works is easier to see by using it than by reading a spec.

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
uncovered.** design.md lists each as an expected gap, and task 4.3 tags each
once igor provides what it needs. spec-trace does not change. design.md's
*Tracing scenarios to tests* gives the reasoning.

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
says what the spec does if the fact turns out false. Task 0.12 is already
measured; design.md's *What task 0.12 measured* gives its result.

- **Can a `PreToolUse` hook block `AskUserQuestion`?** (tasks 0.1 to 0.3)
  If not, only the skill's instructions cover the picker, and the README
  says so.
- **Can an agent without push access read another person's permission on a
  repository?** (task 0.4) If not, then wherever the agent lacks push
  access, every answer in a post and every issue's decision block counts
  as input, and a post's question tags no one.
- **Can the script learn which login a post goes out as?** (task 0.7) An
  agent using the github-app skill posts with a token that only the posting
  command holds, so the script's own `gh api user` returns the person's
  login. If the script can't learn the posting login, it treats every post
  as going out as the person. In a session with a person in it, it then
  asks through the picker where it would have tagged them.
- **Can the script tell whether a person is in the session, and whether a
  headless session can post?** (task 0.9) If it can't tell whether a person
  is there, the session counts as having no person in it, so a picker is
  never opened with nobody to answer it. If it can't tell whether a
  headless session that is not an Igor worker can post, that session
  counts as unable to post, and asks nowhere. Whether the script runs in
  an Igor's run, a worker's or the Igor's own, is not part of this fact: it
  reads that from `IGOR_RUN`, and then reads no lore clone. Task 0.9 checks
  that igor sets `IGOR_RUN` as igor PR #216 specifies, once igor builds it.
- **Can the script find the approver of the pull request that added a
  decision?** (task 0.8) A section of a `DECISIONS.md` leads through blame
  and a commit to a pull request and its reviews. If not, the script skips
  the first candidate in the tagging order, whoever approved the related
  earlier decision.
- **Can the script find the GitHub login of the last person to commit to a
  file?** (task 0.5) Git records a name and an email, not a login. If not,
  the script skips the third candidate in the tagging order, whoever last
  changed the files involved.
- **Can the agent open, and write in, a repository's private security
  advisory?** (task 0.10) That needs private vulnerability reporting
  enabled, or an admin or security-manager role. If it can't, the agent
  records a vulnerability's question and answer nowhere but the fix. It
  reports only that a vulnerability question is blocking, with no text.
- **Can the private fork's pull request be merged before the advisory is
  published?** (task 0.13) Until task 0.13 shows that the merge waits for
  publication, the fork's commit messages describe no weakness, and the
  full description goes in the advisory's text. If the merge can come
  first, the agent describes a fork commit normally only when it knows, as
  it writes the commit, that the pull request will be merged as the
  advisory is published, because the person publishing it said so. Until
  task 0.13 shows the merge waits, a regression test goes in the fork only
  on that person's word.
- **Does GitHub's API give a comment's author and a commit's verified
  signer, as the proof of a questions-branch writer needs?** (task 0.11) If
  not, every questions-branch `decision` or `agent` file counts as input.
- **Does a comment's `updated_at` change only when its text is edited?**
  (task 0.11) *The newest proven answer counts* dates a comment link's
  proof from the comment's last edit, so "newest proof wins" relies on
  GitHub's `updated_at` not moving on a reaction, a hide or minimize, or
  other metadata. If it does move, the spec states no fallback until task
  0.11 has measured it; the ordering for that case is decided then.
- **Can an Igor worker post?** (task 0.14) igor's task-execution
  requirement keeps every credential but its seat's out of the worker's
  environment. A `gh` login stored in the home directory the worker is
  given is neither an environment variable nor in its working tree. If a
  worker can post, it still asks only in its handback comment, and the
  credential within its reach is reported to igor as a breach of that
  requirement.

### Facts the answer session relies on

**Tasks 0.15 to 0.24 measure facts the answer session relies on, and each
task says what the spec does until it is measured.** They cover what
GitHub's notifications endpoint reports; how Linear and Discord show
mentions and replies; how the Linear relay posts a comment; that a command
the mod runs reaches no tool hook; that a mod keeps polling while its
session is idle or in the background; how setup checks a relay's access to
each channel; whether GitHub reports which App wrote a comment; whether a
reader can read the pull request and the signature behind a relay file's
last change; whether the URL an asking agent records as `asked_in` is the
one the answer session reads for that message; and how setup can tell that
a questions-branch commit will be verified for the person.

- **Which App wrote a comment** is measured on both sides: igor PR #216's
  task 4.8 measures it too, like task 0.21 here. Until a measurement shows
  that GitHub reports it, every `User says: ` comment is input.

### What igor must provide

The archive and Igor-worker mode wait on igor. What follows was read from
igor PR #216 at head 59e7561 (2026-10-24), which records #216's decisions
up to its 149, including its decisions 92 and 97 on the categories a
flagged worker's flag lists. Two entries in *Decisions* cite #216 at
earlier heads, read when those entries were written: *The script tells an
Igor's run by `IGOR_RUN`* at ba154a0 (2026-10-20), and *A flagged run asks
nothing and pushes nothing* at d3b7740 (2026-10-21).

- **#216 can drop two of its "Still open" items, both requests to this
  change, since this change has done both.** One asked this change to state
  the flag's categories as #216's decision 97 does, with no fixed order
  (*The flag a worker raises for a question with a category*). The other
  asked it to align the flagged run with #216's decisions 84 and 89 (*A
  flagged run asks nothing and pushes nothing*).
- **Igor-worker mode waits for igor to build its search command.** Task
  0.12 measured that an Igor worker can't run this skill, today or once
  igor PRs #174 and #175 land as specified; design.md's *What task 0.12
  measured* gives the evidence. The worker has no `inquisitor.json`, no
  `gh` login, no picker and no hooks, and can't read the lore checkout. So
  filter 1 in a worker calls igor's read-only search command,
  `igor lore-search`, which igor PR #216 specifies and igor has not built.
  #216's task 4.5 measures whether a worker can give the command its
  standard input. If it can't, #216 gives the command another way to take
  the text, and this change adopts it. Igor must also let a worker run the
  skill's script, which today means a role's `commands` lists it. The
  spec's rule that a command that fails searches no lore stays, as a guard.
- **The archive waits for task 4.3.** Task 4.3 tags every expected gap, the
  Igor-worker scenarios no test covers, once igor builds `igor lore-search`
  and lets a role's `commands` list the skill's script. Task 7.0 also waits
  for igor PR #216 to merge and for igor PR #202 to set the path of the
  scribe's records.
- **igor PR #216, with igor issue
  [#215](https://github.com/adamstallard/igor/issues/215),** amends igor's
  lore-firing spec and holds every rule for an Igor's citations. It has not
  merged. This change relies on it for the following:
  - Its requirement *An Igor publishes the citations its worker reports*
    says what a worker reports for a citation, with no category, and when
    and which citations an Igor pushes, from a worker or from an inquisitor
    run the Igor starts itself, in this change's citation format.
  - igor's review counts citations on the lore repository's `questions`
    branch (its decision 8). It shows them as "not checked" when every Igor
    push of them failed (its decision 32).
  - Its id check reports an out-of-scope collision during a run only as
    "id taken" (its decision 6), and such an entry is not proposed during
    the run.
  - A search during a run reads only the lore repository the Igor injects
    from.
  - Its task-execution requirement *Transcripts and outcomes are captured
    to the state branch* defines the flag a worker raises when its run
    meets a question with a category, and what the Igor does with it, with
    the categories the flag lists (its decisions 92 and 97).
  - Its requirement *An Igor publishes the questions-branch files its
    worker reports* says when and which of a worker's question, miss and
    `authority: agent` files the Igor pushes (its decisions 20, 21, 24 and
    26). That includes the answer to a handback when a worker re-works the
    item. A flagged run pushes none, and any run that ends without its
    worker's completed report counts as flagged (its decision 38). The same
    requirement checks each file with igor PR #217's credential matcher. It
    pushes a person's answer only beside a question the Igor asked, as its
    own record of the handback holds it (its decisions 28, 30 and 41). It
    reads the lore repository's visibility at every push (its decision 37),
    sets each file's `asked_from` (its decision 42), and lets a file's
    `repository` key name any repository, whether or not the run's role
    works it (its decision 33, which amends its 20).
  - Its requirement *An Igor runs its worker's lore searches* defines
    `igor lore-search`, the search command a worker calls, and that an
    inquisitor run the Igor starts itself calls too. The command matches
    plain text and ranks and caps its hits as filter 1 does. It labels each
    question file it returns as an answer, as input, as unanswered or as a
    miss (its decision 23). It runs this change's authority checks before
    it labels a file an answer, and shows the file as input, labelled
    unconfirmed, whenever a check can't run or fails (its decision 34).
    Those checks read each person's `relays/<login>.yaml` as of the commit
    igor PR #208's lore read last applied, and cannot run when it has
    applied none. They count the relay file only when its last change was
    that person's. The Igor reads the relay file too, to decide `authority`
    for a relay App's handback answer.
  - A questions-branch file is in scope for every role whose Igor uses
    that lore repository. It is returned only to a run whose item's
    repository is no more visible than the file, judged by the more private
    of its `repository` and `asked_from` (its decisions 25, 27 and 42).
  - Its `graceful-handoff` and `work-triage` deltas hold igor's side of a
    flagged run: its handoff, its host file and the release of a held item.
- **#216 must allow a second writer of `asked_from`.** #216 says only an
  Igor writes `asked_from`. An answer session's miss copies the
  `asked_from` of the questions-branch file it closes. #216's push
  conditions and its decision 42 should allow for that.
- **#216 should refuse a worker's file holding `handled` or `closes`,** as
  it refuses one holding `asked_from`. Only an answer session writes a
  handled file. But #216 pushes, as an unanswered question file, any file a
  worker reports that holds no `authority`, so it would push a handled file
  too. A worker steered by item text could then close, on every machine and
  for good, whichever questions-branch file the planted `closes` names.
- **#216's Igor should keep, in its own record of the handback (#216's
  decision 59), the 6-hex-digit suffix and the date of the name of the
  questions-branch log file it pushed for the question, and no question
  text.** A later run then names that file in `answers`. The handback
  comment may show the name for people, but the run never reads it from
  there. Without the record, the run writes no `answers`.
- **#216's Igor should write `asked_in`** in a worker's log file as the URL
  of the handback comment that asks it, once it has posted that comment.
  It withholds `asked_in` when the item's repository is more private than
  the lore repository. It names, in `answers`, the file an answer file
  answers, adding `answers` itself and refusing a worker's file that holds
  it. Without `answers`, the answer session keeps showing the answered file
  as unanswered.
- **#216 should give every handback comment a fixed marker,** one that
  text the Igor quotes from its item cannot produce. The answer session
  reads it to tell a handback from the Igor's other comments. Igor chooses
  its form, and task 0.6 records it.
- **#216 should widen its definition of a citation to include a person's
  cite.** It defines a citation as an agent's record that a lore entry
  answered a question so that no person was asked. In this change, a
  person's cite of an `active` entry in scope pushes a citation too. So
  does a decline under the reason "the inquisitor should have handled it"
  with filter 1 naming such an entry, for a question that did reach the
  person.
- **How an Igor runs the inquisitor skill itself** has no mechanism in
  #216 or igor #211. Decided: igor marks that run with `IGOR_RUN=igor`, and
  the script then searches lore only through `igor lore-search` and pushes
  nothing. Open: which other sources that run's filter 1 covers, how the
  run hands its files to the Igor, and whether it can read GitHub.
- **igor's specs must state the order in which each Igor mentions people,
  which Adam decided in igor issue
  [#229](https://github.com/adamstallard/igor/issues/229).** #229 is open,
  and no igor spec states the order. When an Igor stops for a reason it
  detects itself, such as an unrecoverable failure, a stuck condition or
  budget exhaustion, it mentions its operator first, then the item's
  assignee, then its creator. Every other handback, a question included,
  mentions the assignee and then the creator. Only the first person a bot
  mentions gets its question, so this routing relies on the order.
- **igor PR #153, signed publishing,** would have an Igor whose role lists
  prose or bug-hunter push only commits that went through those skills and
  carry their trailers. Citation commits carry none, so #153 should exempt
  an Igor's commits to a lore repository's `questions` branch. That is
  #153's to settle.
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
  handback*). #211 is the igor issue that proposes this skill and the Igor
  inquisitor role. Its body lists five open questions:
  - Three concern the role only, and are out of this change's scope (*The
    Igor inquisitor role is out of scope*): the Igor inquisitor role
    itself, which nobody has claimed; how long it waits before following
    up; and whether a team discussion, such as a chat channel or a shared
    document, is a new kind of surface for Igor, beside the tracker and
    the code host.
  - The fourth, when an Igor's worker can run the skill, is this change's
    Igor-worker mode, which waits on what this section lists.
  - The fifth asks whether the post hook can tell a handback comment from
    other posts, and says a hook that cannot would block an unvetted
    question in a handback comment that an agent posts with `gh`. This
    change accepts that outcome: the hook vets every post it sees, so it
    blocks an unvetted question in such a comment as in any post. That
    blocks no real handback, since an Igor posts its handbacks through its
    own code, which the hook never sees.

### What other changes must provide

- **bug-hunter needs a matching note:** a vulnerability fix's regression
  test lands only in the advisory's private fork, or publicly after the
  advisory is published. Until task 0.13 shows the fork's pull request
  merges only at publication, the test goes in the fork only when the
  person who will publish the advisory has said the pull request merges at
  that moment. A separate change to bug-hunter carries the note.
- **The github-app skill's `token`, `run`, `credential get` and `wire`
  commands must refuse an identity marked as a relay.** No pull request for
  that change is open. This change asks for it and does not make it, and
  ships without it, with the cost *github-app refuses `token`, `run`,
  `credential get` and `wire` for a relay identity* accepts.

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would have that surface's API vouch for the message's author,
  and a file in the lore repository map the author to a GitHub login. igor
  issue #160 already maps a Discord user to a GitHub login, by a
  configuration entry keyed by the Discord user id. A later change would
  choose between that entry and a file in the lore repository. Until one
  adds it, an answer typed directly on such a surface counts only through
  a decision document, such as the scribe's record. An answer typed in the
  answer session and relayed there counts through its log file's
  signature.

### Left to implementation

- **Task 6.11's details are chosen at implementation, with no requirement
  added,** and recorded in design.md while the change is open: how a
  question's options are parsed from its thread; a draft's privacy; an
  asker's reply revising the options; what agreeing with a suggested
  verdict posts, and what citing a lore entry posts; and the UI of the
  relay notice. *Some answer-session details are decided at
  implementation* lists them and what is decided around them.

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
  changes 56. In *Decisions*, *A logged decision counts only when merged
  and its author has access* states only the undisputed part: the default
  branch, or a questions branch with a proven writer. *A decision on the
  current work's branch answers that work* and *An agent's choice counts
  only in the work it belongs to* let an `agent` entry count on the work's
  own branch, and say nothing of a `decision` entry there. The spec
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:1014-1016) counts a
  `decision` or `agent` log entry on the current work's own branch.
- **What the Igor's record of a handback holds.** *A person's answer to a
  handback* matches an answer against "the Igor's own record of the
  questions it posted in that comment", two questions matching "when they
  are equal once each is reduced as this change reduces a question for its
  hash" (#216's decision 41). *A later run names the answered file from
  the Igor's record* says "The record holds only the 6-hex-digit suffix and
  the date ..., never question text". They may be two records (#216's
  decisions 41 and 59), or one record that also holds question hashes,
  which "only" would rule out. *Alignment with igor PR #216* calls #216's
  decision 59 "the hashed record of handback questions". Meanwhile each
  entry states its rule as written.
- **Whether a reopened decline leaves its miss behind.** *Reopening a
  declined question* says "A miss already logged for a reopened question
  stays, since a miss file is never changed, and nothing records that the
  person took it back." That entry comes from ruling 255 in proposal.md at
  commit 5c9fcc6, which carries an amendment note: "Amended by Adam's
  decision 298: no decline that can be reopened logs a miss, so no logged
  miss is left behind". But
  under *Messages that are not questions are ignored*, filter 3's choice
  "the agent shouldn't have asked" posts nothing and logs a miss, and a
  decline that posts nothing on a thread copy can be reopened on its
  machine. Nothing says which of the two holds for that decline. Meanwhile
  the entry keeps "the miss stays", which follows from miss files never
  changing.
- **Whether to keep the "until #202 settles" sentence on off-GitHub
  approvals.** The igor PR #202 bullet above says "Until it does, the
  scribe can't mark a record of an answer typed directly on Discord, Slack
  or Linear `accepted`. Such an answer then counts only when a person
  writes it into another decision document". That may be an interim igor
  design, which this change does not write while igor has no users, or
  only a restatement of *An answer typed on another surface counts only
  through a decision document*, which holds in the end state too.
  Meanwhile the bullet keeps the sentence.
- **Whether a copy of an answer, pushed alone, can become a named file's
  answer.** *A named file's answer must be the person's own, added alone*
  gives its reason as stopping a copy of another question's answer
  "pushed in one commit with other files". A copy that carries the
  person's comment link and is pushed alone passes both tests. No ruling
  says whether that is accepted or why it cannot happen.
- **Why an owed push's retry ignores an answer file this machine already
  knew.** *The push order for a questions-branch answer* gives its reason:
  so that a file pushed at once does not cancel the push of an edited
  answer's file. No ruling records that reason; it is the author's
  inference, and Adam is to confirm it.
- **Why a replaced answer file still supersedes the older files in its
  hash group.** The spec's *A replaced answer file stops counting even in
  its own hash group* has such a file stop counting, yet still supersede
  the older files, which can leave the group with no answer that counts.
  *`answers` decides a named file's answer; the search groups by hash*
  says why it stops counting, but no ruling says why it still supersedes.

### Where the spec and a decision differ

These are listed for Adam; the spec is not changed here.

- **spec-check's decisions-first rule**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:249-250), *Questions
  another skill requires skip filters 2 to 4*. The spec's scenario *A
  question another skill requires is not decided by the agent* still names
  spec-check's choice "whether to enforce its decisions-first rule" as an
  exempt question. spec-check removed that rule (shared-skills PR #44), so it no
  longer asks the question, and the decision lists no such question. The
  spec's mention is for Adam to remove.

- **A deferred question in a new issue that tags someone in another
  part** (openspec/changes/inquisitor/specs/inquisitor/spec.md:2020-2021),
  *A deferred question passes only untagged and listed*. The decision: "a
  question in a new issue that tags no one". The spec: a question "that
  tags no one and is an item of an open-questions section or in a post
  that creates an issue". Under the spec, a deferred question that tags no
  one passes in a new issue even when another part of that issue tags
  someone; read literally, the decision does not let it, because the issue
  tags someone. design.md's *Questions in posts* follows the spec's reading.
- **A private file in a readable directory**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:1890),
  *Files passed to the two calls stay private*. The decision: the script
  "refuses a file that its group or others can read". The spec adds "or
  whose directory they can". An addition, not a
  contradiction.
- **Which questions go on standard input**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:3444-3445),
  *Files passed to the two calls stay private*. The decision: "A question
  with a category reaches the script on standard input". The spec passes
  "it, its verdict and the rest of its picker call only on standard
  input". An addition, not a contradiction.
- **A gh read through an unset `$G`**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:365 and its
  scenario at :415), *Posts sent through the github-app skill's script*.
  The decision: a command that runs `python3 $G`, "mentions `gh`" and
  assigns `G` nowhere earlier is unreadable. The spec: one that "mentions a
  gh post verb", with the scenario "A gh read through an unset G is no
  post". The spec lets a read through.
- **An unparseable GraphQL query**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:481-482), *GraphQL
  mutations that post text*. The decision: "A mutation the reader cannot
  parse ... is unreadable". The spec: "a query it cannot parse", read or
  mutation.
- **`gh` inside an unquoted word**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:242-243), *Which
  commands the reader judges, and which are unreadable*. The decision: a
  data command "naming `gh` only inside a quoted argument". The spec:
  "with `gh` only inside a longer word that is not a path ending in
  `/gh`", which also covers an unquoted word.
- **Other git forms that run a command**
  (openspec/changes/inquisitor/specs/gh-post/spec.md:244, with its
  scenarios at :272-281 and :292-296), *Code given on the command line that
  names gh*. The decision covers `git rebase -x`/`--exec`, `git submodule
  foreach`, `git bisect run` "and any other git form that runs a command it
  is given". The spec names the three forms and `-c` in its scenarios, and
  calls its set of forms that give code to run "fixed".
- **How a body is reduced before the reserved-prefix check**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2162-2163), *The post
  hook blocks a reserved prefix on GitHub*. The decision: the body is
  reduced "as [the answer-comparison rule] reduces a comment". The spec:
  "once reduced as a question in a post is for its hash", which reduces
  inline markup to its text and joins whitespace.
  The comment reduction also drops list markers; it also ignores a leading
  `User says: `, which, taken literally, would defeat the block.
- **Which `CLAUDE.md` holds a way-of-working answer**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2662-2663, with :189
  and :2668-2670), *A way-of-working question gets no log*. The decision:
  "that person's memory or `CLAUDE.md`". The spec: "that person's agent
  memory or user-level `CLAUDE.md`, never a committed one". The spec narrows
  the decision.
- **The scribe's records at `docs/decisions/`**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:707
  and :1431), *Filter 1 searches igor's scribe's records where #202 puts
  them*. The decision: "at the path igor PR #202 sets". Two scenarios fix
  the path: "a decision record under `docs/decisions/`". The requirement
  text itself says "at the path igor PR #202 sets".
- **When #208 has applied no commit**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:580-583), *An
  Igor reads relay files as of igor PR #208's applied commit*. The
  decision covers `igor run` "and ... a lore repository #208 never
  fetches", and says "An answer in the person's own comment still counts".
  The spec names only `igor run`, and says nothing of the person's own
  comment.
- **Who keeps the handback record**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2991-2992), *A
  later run names the answered file from the Igor's record*. The decision
  states the end state: "The record holds only the 6-hex-digit suffix and
  the date". The spec calls it the Igor's record "which igor PR #216 is
  asked to keep (#216's decision 59)". The request to #216 is in *What igor must
  provide*.
- **What an incomplete configuration is**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:470-472),
  *Setup is part of the answer session*. The decision: setup runs "when
  the `answer_session` section is missing or incomplete". The spec: "while
  `answer_session` is missing or no surface in it has both a `relay` and a
  subscription". Under the spec, one complete surface beside
  an incomplete one opens no setup.
- **An answer file copying `asked_from`**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:1975-1976,
  openspec/changes/inquisitor/specs/inquisitor/spec.md:3112-3113 and
  :3212-3216), *The Igor writes `asked_from` on every file it pushes*. The
  decision: the script "never writes `asked_from`, apart from the miss an
  answer session logs". The spec also has an answer file copy it:
  "copying its `asked_from` as a miss does" (answer-session :1975-1976) and "a
  miss or answer file an answer session logs" (inquisitor :3112-3113), and
  its scenario on where `asked_from` comes from (inquisitor :3212-3216)
  names both.
- **Where filter 1's recorded place comes from**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:2351-2352),
  *Two reasons to decline*. The decision: "naming the place the person
  gave or the model found". The spec: "the place the person gave, or of
  one filter 1 found that they chose". *Claude drafts a reply only
  into the prompt box* has Claude's draft fill in the place, which may be
  what "the model found" means.
- **An Igor log file whose link this machine never reads**
  (openspec/changes/inquisitor/specs/answer-session/spec.md:935-936, with
  :914-915), *A link this machine never reads is not followed*. The
  decision has no exception. The spec: "An Igor's log file, one holding
  `asked_from`, SHALL follow its link even on a machine that does not read
  its item". The exemption fits *Each Igor log file follows its own
  handback comment*, but no decision states it. The spec also adds a
  channel "this machine has off".
- **Which login an unknown post goes out as**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:2273-2274), the bullet
  *Can the script learn which
  login a post goes out as?* above. The bullet: "it treats every post as
  going out as the person". The spec: "as the configured login". Probably
  the same login, in different words.
- **How an Igor's own run hands over its files**
  (openspec/changes/inquisitor/specs/inquisitor/spec.md:94-95 and
  :2729-2731), the bullet *How an Igor runs the inquisitor skill itself*
  above, and *The script tells an Igor's run by `IGOR_RUN`*. The bullet
  calls "how the run hands its files to the Igor" open. The spec:
  "putting each file it would push in the run's report for the Igor to
  push". What is open may be only how the
  report reaches the Igor, which is #216's.
