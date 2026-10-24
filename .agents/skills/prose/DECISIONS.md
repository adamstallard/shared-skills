# prose — decisions

`prose` makes agents rewrite what they write for human reviewers, and proves
they did. The rules are in [rules.md](rules.md); this file is why they, and the
mechanisms around them, are the way they are. Each entry gives the decision,
why it holds, and the alternatives an editor might propose again, with why
each was rejected. Entries give the rules' current numbers.

**Terms used throughout.**
- **The pass:** the agent rewrites its own text by rules.md before signing it.
- **First call and signing call:** each commit or post takes two runs of
  `prose.py`. The first (`check` or `sign` without `--pass`) prints the rules
  and a **pass token**; the signing call passes that token back and gets the
  trailer or footer.
- **Cold read:** before signing, a fresh agent reads the changed text and
  reports where it stopped; the author answers each finding.
- **The gate:** a Claude Code hook that blocks a session's first file write
  until a first call has run.
- **Igor** (adamstallard/igor) is an agent pipeline that runs prose in its
  workers; most examples come from it. **Adam** owns this skill and made the
  decisions credited to him.

---

## Why the skill exists

Agent-written code is usually easy to read; the text around it is not: long,
ambiguous and switching topics, because agents rank completeness and
defensibility above being understood.

**Its value is enforcement.** `sharper-comments`, `CLAUDE.md` rules and
memories all failed the same way: agents treat advisory text as optional. A
rule no script checks is the thing that already failed.

**Scope: anything a human reviews.** READMEs and other docs, code comments,
architecture docs, specs, commit messages, pull request descriptions, and
posts to GitHub, Linear and Discord. Short kinds are not exempt: agents bloat
commit subjects and ticket comments too.

**Rejected.**
- **Readability scores** (Flesch and similar), even as a flag. They count
  syllables and sentence length, not whether a reviewer finds what they need,
  and text rewritten to raise them is no easier to understand.
- **Length budgets per kind**, beyond the 72-character commit subject. A number
  reads as a target: short text gets padded, long text loses a needed
  sentence. If bloat still gets through, measure word counts before and after
  the pass first, and set limits from that.

---

## The rules

**Rules 1 to 3 cut claims; nothing checks them.** Rule 1 keeps a sentence
only if the reader needs it, rule 2 puts the conclusion first, and rule 3
removes rereads. None asks the agent to verify its claims. Every claim is
something a reviewer can attack, and an agent answers each attack
with a hedge, which is another claim; a few rounds produce the unreadable
block. Re-verifying claims inside this skill would rebuild that loop. One
explicit scope line ("Checked: X. Not checked: Y.") narrows rather than hedges:
vague hedges lower trust while a stated limit raises it (van der Bles 2020,
Jensen 2008).

**Rule 3 names a pointer whose one referent is far back** ("it", "these
commands", a paragraph after what they point at) as a cause of a reread, not
only a pointer with two referents.

**Rule 4, a hypothetical reads as one.** A case that happens only by accident,
rarely, or by someone else's choice is marked three ways together: lead with
what is always true, say the case is unusual and whose doing it would be, and
put its consequences in "would" or "might". This comment, which passed three
cold reads, was read as "spec-trace saves a log of its output":

```
# A log of this output saved in the repository is searched by the next run.
```

It meant: if a person saved the output in the repository, the next run would
search it. The condition hid in the subject, so the writer saw no condition to
label, and a reader sure of the wrong meaning never stops. "If" alone is not
enough: with the case still the topic and its consequences in the plain
present, the reader takes away a normal workflow with a condition attached.
Rule 4 comes right after rule 3, among the rules printed in full (*New
failures fold into an existing rule*, below), because a misreading costs more
than a reread.

**Rule 5, say when and whether, sits beside rule 4.** Both are about a claim's
status (past, present or future; actual or conditional), and both prevent a
reader who leaves misinformed without stopping, the goal rules.md names
*Read as meant*. Further apart, someone applying one would read past the
other.

**Rule 6, each sentence follows from the last.** Abrupt switches to a subject
the reader wasn't expecting kept slowing reading after the pass existed. It
also says a "so", "because" or "therefore" points at what the reader just
read: a "so" whose cause is two sentences back makes the reader search.

**Rule 7, a claim is stated once, with its reason.** In Igor's PR #156 one
catchphrase appeared nine times across six documents, restating a rule in a
form that sounded like a reason, so the reasons were never written down. The
pass greps the repository for a phrase a changed passage repeats and fixes it
at its source. That fix may touch text the change did not otherwise change,
and rules.md's *Scope* section names it as the one exception allowing that. A
term defined once and used as a name is vocabulary, not a catchphrase.

**Rule 8, what is, not how it got here,** covers docs as well as comments. A
passage that labelled its past ("the argument once made … does not apply")
passed the pass: it satisfied rule 5, which only asks that the past be
labelled. Rule 8 is what says whether the past belongs in the text at all.

**Rule 9, one claim per sentence.** "A longer sentence that reads once beats a
shorter one read twice" says what may make a sentence longer: words that serve
its one claim, not a second claim.

**New failures fold into an existing rule when they fit its question;** a new
rule is inserted only when none fits, as rule 4 was. Renumbering breaks
citations by number, and rules past `RULES_IN_FULL` (9) reach the agent as
headings without their reasons or examples.

**Rejected.**
- **A word or clause limit per sentence.** A count of words does not see
  claims, and reads as a target.
- **A mechanical lint for passives** such as "is searched" with no "by". It
  would flag far more harmless sentences than harmful ones, and prose's checks
  are worth reading because they don't cry wolf.

---

## The rules live only in rules.md

`rules.md` holds the full rules text: scope, the pass with its reader table,
the rules with their examples, and how agents cheat. SKILL.md keeps no copy.
Every first call prints rules.md by its headings: everything before the rules, rules
1 to `RULES_IN_FULL` in full, the rest as one-line headings, and the cheat list. `prose.py` refuses to run when a section is missing or out of order, or the rules are
misnumbered.

**Why.** Agents skip documents but read a command's output at the moment they
act on it. A second copy drifts, and a summary is read in place of the rule.

**Rejected: rules behind a pointer** (a `reference.md`). A rule behind a
pointer is read after the mistake.

**Known gaps.** A fence closes at the next line starting with the same three
characters, a `####` heading inside a rule is refused, a blank `# ` title
passes, and a title placed after the opening principle (the bold lines before
*Scope*) passes. rules.md changes only through
reviewed pull requests, so stricter parsing would guard almost nothing.

---

## Each listed item is judged as its own reader

`prose check`'s `--goals` are the commit message's, for the reviewer. Every
changed doc and spec gets goals of its own, which the agent names per file
with `--goals-for <pattern> '<goals>'` or a `--goals-file` of
`pattern: goal; goal` lines. Without them the first call refuses, naming each
file and its kind's default from rules.md's reader table. A deleted doc needs
none; a code comment without goals gets its kind's default, labelled as one.
The pass token records the per-file goals, and the signing call refuses goals
that differ from them.

**Why.** A commit to Igor's architecture doc passed with a valid trailer while
telling the doc's reader that an argument they never saw "does not apply".
The one goals string was the reviewer's, and a reviewer does want to know an
old argument no longer applies; the doc's reader does not. Only the
agent writing the change knows who a particular doc's reader is, and printing
each file's goals above it keeps that reader in front of the agent.

**Which goals win: the most specific match.** An exact path beats any pattern;
between patterns, more literal characters win. Equally specific matches with
different goals are refused, since choosing by order would hide a
contradiction. Patterns follow gitignore because agents know it; negation is
refused. A pattern matching no listed file is a warning, usually a typo.

**Rejected.**
- **One fixed reader per kind.** It cannot say an API reference and a runbook
  are read for different reasons.
- **One `check` per document.** A commit has one trailer and one message.
- **Goals per hunk or section.** A file is read by one reader.
- **Listing each changed passage's section heading.** Three bug-hunter rounds
  each found another Markdown construct it misread, and a wrong hint misleads
  silently. Reconsider only with a real Markdown parser, if agents ignore the
  instruction to reread each passage in its section.

**Where this stops applying.** If agents paste the reviewer's goals into
`--goals-for`, the next step is a separate first call per doc.

---

## `start` and `sign` take their goals from a file too

`start` and `sign` take `--goals-file <file>` in place of `--goals`: one or
more goals per line, separated by `;`, blank and `#` lines skipped. Both given
is refused, since joining them would choose an order nobody gave. The token is
bound to the goals, not to where they came from.

**Why.** Goals can hold text from the issue being worked on, which may be
private, and on Linux any
user can read another process's arguments in `/proc/<pid>/cmdline`. A file
readable only by its owner keeps them private, and needs no quoting.

**Rejected: goals on stdin.** `sign`'s signing call reads the post there.

---

## `check` takes the message's goals from a file too

`check` takes `--message-goals-file <file>`, written like `start`'s, in place
of `--goals`, for the same privacy reason. A second option is needed because
`check`'s `--goals-file` holds per-file `pattern: goal` lines, and a reserved
pattern naming the message could clash with a real file.

**Rejected: goals in the message file.** They would become part of the message.

---

## A revision request is drafted fresh, section by section

When someone asks for existing text to be improved with prose, the agent
writes a draft of every section before rereading it, carries over every fact,
measurement, decision and warning the draft lacks, and keeps the original only
where the draft, written without it, says essentially the same thing. A tie
goes to the draft. A section an open branch also changes is held, with the
branch named. The agent's report to whoever asked counts sections redrafted, merged, kept and held, and
shows each kept section's draft beside the original.

**Why.** Asked to improve the comments in a 2,163-line file, an agent grepped
for patterns, skimmed comments without their code, changed 5 and called the
file good; the ones it kept included blocks that fail rules 3 and 7. A first
fix, "keep the original where it serves the reader better", still let poor
blocks through:
- **Editing anchors on the existing framing.** A sentence that sounds reasoned
  survives "is this wrong?", a much easier test than "would a fresh draft be
  better?".
- **A draft held in the head can't be checked,** so the procedure writes it out.
- **The original won ties,** read with the code's context already in mind.
  Churn (diff size, merge conflicts) also passed as a judgement about the
  reader. A held section now gives churn from an open branch its own name.
- **`prose check` lists only what the change touches,** so the report is the
  only record that the rest was read.

**Rejected.**
- **Always replacing the original.** Where the draft converges it only grows
  the diff, and a draft is sometimes worse.
- **A blind comparison by a second agent.** Removes the bias, but doubles the
  cost of every revision.
- **Keeping the original where the agent can name a rule the draft breaks.**
  Still a judgement the original wins easily.
- **A `--revise <path>` listing every section of a file** (issue #16). A
  listing proves printing, not reading. Build it if agents follow the
  procedure and still report files done with sections unread.

---

## The rules are on screen before a signature

A trailer or footer takes two calls. The first, `check` or `sign` without
`--pass`, needs the reader's goals, prints them, the rules and a pass token,
signs nothing and exits 4. The signing call, with `--pass <token>`, signs.

**Why.** The rules help most while a draft exists and is not final. Goals on
the command make naming the reader part of the command, so it cannot be
skipped silently; without goals there is nothing to cut against.

**What it proves:** a first call printed the rules before the signature. Not
that the agent read them, or that the pass was good. Forging a token file or a
session mark is out of scope, as forging a footer is.

### The pass token

- **One token signs one text,** once: a doc edit, a commit message and a PR
  description have different readers, and a reusable token would let later
  texts skip naming theirs. It is bound to its goals and its command (`check`
  signs a commit, `sign` a post). A refused signing call keeps it.
- **Bound to the goals, not the text,** since the pass revises the text.
- **Expires after 2 hours;** each first call deletes older tokens.
- **Exit 4** for a first call, distinct from 2 (refused) and 0, so
  `sign … > signed.md && gh …` stops there.
- **Lives in `prose/passes/` under the repository's git directory,** never
  committed. Igor's workers each run in a throwaway clone with a shared HOME,
  so per-clone tokens mean no contention and no worker redeeming another's.
  Outside a repository, `${XDG_STATE_HOME:-$HOME/.local/state}/prose/passes/`.
  Written under a temporary name and renamed, so no call reads half of one.

### `prose start`

The gate (next section) blocks the first file write, so the call that opens
it must work
before any draft exists. `start` takes only goals, prints them and the rules,
marks the session, and issues no token: one would sign a text whose own
reader was never named.

**Rejected.**
- **Printing the rules on the signing call.** They would arrive after the
  footer, when nothing is left to rewrite.
- **Injecting the rules from a hook** (`additionalContext`). Shown, not acted
  on; what fixed skipping in bug-hunter was making the agent run a script.
- **A flag that prints only the trailer.** It is what an agent reaches for to
  skip the rules.

---

## The gate blocks a session's first file write

In Claude Code, `require-first-call.sh` blocks a session's first Write, Edit,
MultiEdit or NotebookEdit to any file, and its first `gh` or GitHub MCP post,
until `prose start` or a first call has run in the session. It checks the
session mark first, so in a marked session the gate does nothing else. It does not look
for comments or tell docs from code.

**Why not detect prose.** A gate that looked for comments in edits did not
converge: two bug-hunter runs hit their iteration cap, each round finding 4 or
5 real bugs (unparseable fragments, regex literals, directives, docstrings,
notebook cells). Nearly every session writes prose anyway, a commit message at
least, and the token already guarantees the rules before any signature. The
cost is one `prose start` in a session that writes no prose.

**The session mark** is an empty file named by the session id in
`${XDG_STATE_HOME:-$HOME/.local/state}/prose/sessions/`, deleted after 30
days, taken from `--session` or `CLAUDE_CODE_SESSION_ID`. It lives in the
state home because a session spans repositories.

**It fails open.** A missing `python3`, a crash or an unreadable state
directory lets the call through: a broken gate would block every write.

**What it relies on in Claude Code:** PreToolUse exit 2 blocks and feeds stderr
to the agent; the payload's `session_id` (a subagent carries its parent's),
`tool_name` and `tool_input`; `CLAUDE_CODE_SESSION_ID` equals that
`session_id`; matchers are unanchored regexes, so this one is anchored.

**Known gaps.** Files written through Bash (`sed -i`, `>`) skip the gate.
Cursor has no gate.

---

## A cold read before signing

Before a changed comment, doc passage or post is signed, an agent that never
saw the conversation reads it and reports every place it stopped, reread or
guessed. [cold-read.md](cold-read.md) is the brief's only copy.

**Why.** The author checks the text with the conversation in mind, so every gap
is already filled for them. Igor's `gitEnv` comment had seven failures, and the rules
already named four of them. A fresh subagent given only the brief found four
of the seven, and three more gaps that no review had named.

**The signing call enforces it,** because it holds the final text. Without
`--cold-read`, it signs nothing, keeps the token, exits 5 (distinct from 4 and
2, so a script can tell "do this step" from an error), and prints the brief:
cold-read.md, the `cold-read <token>` line the report starts with, and each
text with its reader's goals, a comment or doc by file and lines, a post
quoted. With a report and the author's answer to each finding (the dispositions,
next section), it checks both, then signs.

**What it reads, and what it skips.**
- **Every comment block the change touches, whole,** since a reader meets it
  whole; that includes a comment on a changed line whose own text did not
  change. Every doc or spec passage the change adds to. Every post.
- **No length threshold.** The first version read only texts of three or more
  lines, and every bug found in it was in that counting (comment syntax, binary-diffed docs, BOMs, UTF-16), and a
  character count has the same hard cases.
- **Not the commit message** (Adam: "I don't care about commit message
  bodies"). A commit changing no comment or doc signs without a report.
- **Nothing with no new prose to read:** a doc git diffs as binary, a deleted
  doc, an edit that only removes lines, a symlink or submodule at a doc path,
  a code file that did not parse or could not be read.
- **One cold read per token.** Fixes are not read cold again, which would
  repeat until a reader found nothing; `fixed` is checked by the item having
  changed instead.

**What it proves:** a report for that token existed before the signature, and
each finding was answered. Not that a fresh agent wrote it; an author writing
its own report is forgery, which the cheat list names.

**Rejected.**
- **Procedure only, in SKILL.md.** A cold read is skipped exactly when the
  author thinks the text is clear, which is when the author is wrong.
- **The script running the reader through a model API.** Needs a key, a
  network and a provider in a standard-library script.
- **A brief from the first call.** The text is a draft then, and `sign`'s first
  call has no text at all.
- **A separate `brief` command.** One more thing to remember.
- **Giving the reader the rules.** It would check against them instead of
  reading; the pass already does that.
- **Asking the reader for rewrites.** A rewrite carries its guesses into the
  text; a stop with what was guessed tells the author what to fix.
- **Binding the report to the text's hash.** Every fix would need a new read.

**Where this stops applying.** If cold readers report nothing on text human
reviewers still find hard, change the brief. If authors dismiss what readers
report, the next step is a second cold read of the fixed text.

---

## Every cold-read finding is answered before signing

The signing call takes `--dispositions <file>` beside the report. Its first
line is `dispositions <token>`, so answers for one cold read cannot pass with
another, and it answers every finding once: `<n>. fixed`, or
`<n>. kept (asked): <reason>`. A missing, duplicate or unknown number is
refused.

**Why.** Proving a report existed let an author pass it and change nothing,
with a signature identical to one whose author fixed every place.

**The report has a fixed form,** which cold-read.md asks for and the script
parses: numbered findings `Finding <n>, item <i>, <stopped|reread|guessed>:
«<words>» <what was missing>`, `Item <i>: read straight through.`, and one
understood line per item. A line in any other form is refused, so the author
asks the reader again rather than prose guessing what a free-form report
meant.

**`fixed` is checked by its item changing.** The brief's call records each
item's file, line spans and the staged text. At signing, the script diffs the
recorded text against the current one: a line of the item changed or removed,
or a line added inside it or directly beside it, counts. An edit elsewhere that
only moves its lines does not. The quote is for the person deciding, and is
not checked.

**Why not the quote.** An earlier version refused `fixed` while the quoted
words remained. That check was its most intricate code and held one of the two
bugs bug-hunter found in it; it refused honest misquotes, and proved only that
those exact words were edited.

**A file the brief did not name is refused** when it now has a changed comment
or doc passage: no reader saw it, and the trailer would say one had.

**A person decides every kept finding.** A finding kept without `(asked)` is
refused, with the quote, the reader's note, the reason and the file paths. An
agent with a person and an interactive picker (in Claude Code, the
`AskUserQuestion` tool) asks one question per finding, "Keep as is"
or "Fix it". An agent that cannot ask leaves the change staged and hands that
refusal, the files and the token to whoever holds its result. `(asked)` proves
nothing the script can see; it is a claim made on purpose, and writing it
falsely is on the cheat list.

**The counts go in the `Prose:` value,** such as `; cold read: 5 findings, 3
fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`, accepted only in the
exact form the script prints. A commit with no cold read keeps the plain
value; posts keep their footer. The value, not a new trailer key, because the
commit script, the shared hook and bug-hunter already carry it as one opaque
line.

**Rejected.**
- **Withholding the token until a read comes back clean.** Readers rarely
  report nothing, and the author relays the report, so "clean" is unverifiable.
- **Free-form reports.** The text being read contains quotation marks too, and
  a guess at a report's meaning passes by mistake.
- **Signing with `kept` and fixing later, or showing kept findings after
  signing when no person can be asked.** Either way the wording lands before
  anyone sees it.

**Known gaps.** `fixed` proves the item changed, not that the edit touched the
place the reader stopped; editing another part of the item is on the cheat
list. A `kept` reason is checked only for being there.

---

## The cold reader says what it understood

For every item the reader writes `Item <n>, understood: <one line>`: who or
what does each thing, whether it always happens or only in some case, and
whether the code does it or someone else could make it happen. The author
answers each one: `matches`, `fixed` (checked like a fixed finding) or
`kept (asked): <reason>`. The counts gain `; understood: <items>, <fixed>,
<kept>`; a value without that part still verifies.

**Why.** A reader sure of a wrong meaning stumbles nowhere, so its report says
"read straight through": the rule 4 comment passed its third cold read that
way. The author, who knows what was meant, can see the difference. The three
questions are what a hypothetical written as fact gets wrong; a summary
without them tends to restate the item's words.

**Rejected: a line only for items read straight through.** An item with
findings can be misread confidently elsewhere.

**Known gap.** `matches` is the author's claim; answering it falsely is on the
cheat list.

---

## Without subagents, the cold read goes back to the caller

An agent that cannot start a subagent hands back the brief, its token, and the
paths of the message file and worktree, and does not sign or commit. It reads
the brief itself only when nothing will read its result.

**Why.** An author reading its own brief is the same author whose gaps the read
exists to find; in one workflow every author lacked a subagent tool, so every
"cold read" was the author's. A workflow script can start the fresh reader.
The token lives in the repository's git directory, so a different agent can
fix the findings and sign.

**Rejected: reading the brief yourself whenever no subagent is available.** It
produces a report that looks like a cold read and is not one.

---

## Commits carry a trailer that signs the snapshot

Every commit carries `Prose: ✓ <tree>:<message>`: the first 12 hex of the
staged tree (`git write-tree` when the signing call runs) and of the sha256 of
the normalised message. Agents commit through the shared commit script with
`--verified-value scripts/verify-staged.sh Prose <value>`, which refuses the
commit if the tree or message no longer match.

**Why.** The signature proves a script ran over the final text, and an edit
after it breaks it. Twelve hex per half stops a trailer written from memory;
no hash can prove when it was computed.

**Every commit gets the pass; there is no skip value.** Every commit has a
message a reviewer reads, so no commit honestly qualifies for a skip.

**One commit carries every installed skill's trailer.** Composing them is the
shared library's job (`../../lib/commit-trailer/`), through trailer families.
While bug-hunter runs, its commit step runs prose's two calls and carries the
`Prose:` value.

**An amend goes to git directly,** with `git commit --amend -F <file> --trailer
"<the Prose: line>"`, because the commit script cannot amend. Nothing checks the trailer before the
amend lands; the commit hook reports it afterwards if it no longer matches. Fix, if amends need checking before they land: an amend
mode in the commit script.

**Messages are UTF-8.** `prose check` refuses a message that is not valid UTF-8
or holds a Unicode noncharacter (git would store it re-encoded), and a
non-UTF-8 `i18n.commitEncoding` (reading it back converts the `✓`).
`verify-commit` reports a commit stored under any other encoding label as a
mismatch.

**The listing is not hashed.** `prose check` lists the message, each changed
doc or spec, and each touched code comment so the agent knows what to pass
over; history language in touched comments is printed as non-blocking flags.

**`verify-commit`** exits 0 valid, 1 invalid, 3 unable to check, matching the
library's callback contract. Its reason starts `missing` (git sees no `Prose`
key at all), `unrecognised` (any other form, including a blank value),
`mismatch` (the message half) or `tree` (only the tree half), so the report
says which half broke.

**Rejected.**
- **A rebase-proof signature over the prose lines a commit adds.** It grew
  rename, cancellation and parse-failure rules, each another way for check and
  verify to disagree. The hook exempts rebases and cherry-picks by reflog
  action instead.
- **Two lines** (`Prose: checked` plus a signature), or **counts of blocks
  rewritten** in the trailer: nobody needs them.
- **A git `commit-msg` hook.** Per-clone setup, and the reflog hook covers it.

**Known gap.** The commit script runs no verifier for a value starting
`skipped`, so a `Prose: skipped…` commit lands and only the hook reports it.

---

## `prose check` ends with the shared result block

The signing call prints only the shared `result-block.sh` block, holding the
trailer, so no one types it. The format lives in the shared script; prose does
not copy it. Either call stops before printing anything when `result-block.sh` is missing.

---

## `prose check` runs the pre-commit hook first

In a repository with a pre-commit hook, both calls run it, through the shared
`run-pre-commit.sh`, before they list or hash anything.

**Why.** A formatter in the hook rewrites staged files after the check would
have signed them, breaking the trailer. Running it on the first call too means
the agent passes over the text that lands, and a failing hook stops the agent
before the pass. The library records a passing run for the staged state, so
in the usual flow the hook runs once in total.

A failing hook makes `prose check` exit 2: the first call issues no token, and
the signing call keeps its token for after the fix. With `prose check --amend`,
`git commit --amend` runs the hook a second time itself; a formatter that
already ran changes nothing.

---

## The signed message is found by searching from its end

`prose check` hashes the whole message it is given. `verify-commit` removes 0, 1,
2 or more trailer-shaped lines from the end of the stored message's last
trailer block, and accepts the commit when any of those results hashes to the
message half. The search
stops at an indented line, any line that is not trailer-shaped, or the start
of the paragraph.

**Why.** git adds trailers only at the end, and `prose check` refuses the
`trailer.*` config that could move them, so the signed text is always the
stored message minus some lines from the end. A list of trailer keys missed
edits to keyed lines elsewhere and had to grow with every skill.

**How the message is normalised.** LF endings, trailing blanks off each line,
blank-line runs collapsed, ends trimmed. When git reads the last paragraph as
a trailer block, its lines are put in git's `token: value` form first, and an
empty-valued key is folded into the indented line after it, as git does. A line
starting with `#` or `core.commentChar` is refused, since git's cleanup may
delete it. A `prepare-commit-msg` hook that edits the message breaks the
signature, and the report says so.

**Accepted cost.** A trailer-shaped line appended after signing does not break
the hash.

**Rejected: git's own commands for parsing** (`git stripspace`,
`git interpret-trailers`). A prototype committed about 2,500 test and fuzzed
messages for real. The git version round-tripped every default-config one, but
prose's own parser already matched git on all 2,464 of them that it accepts. The git version would save about 90 lines while adding git calls,
depending on the internal order of `git commit`, and still needing most
refusals. Revisit if people hit the refusals (configured trailer keys, `#`
lines, `core.commentString`) in practice.

**Known gap.** The fold follows git's default rule; with a configured
`trailer.<x>.key` in a last paragraph that mixes trailer lines with other
lines, git folds where prose does not, and an
honest commit fails loudly. Fix: read `trailer.*.key` config.

---

## Posted text carries a signed footer

A pull request description or comment ends with `prose ✓ <6 hex>`, the hash of
the text above it (LF endings, trailing blanks and blank lines removed), which
`sign` prints. A hook recomputes it before the post goes out and blocks a
mismatch. `sign` replaces an existing footer, so re-signing works.

**What it proves:** a script produced the footer for that exact text. Not when,
or that the rewrite was good. The hash is unkeyed, so a reimplementation could
forge one; a secret key would sit on the disk the agent reads. The design stops
skipping, and forgery is forbidden by SKILL.md's *Never* list and caught at review.

**Rejected: a plain `prose ✓`.** It can be typed from memory.

---

## Checks are layered by where the text goes

| Destination | Check |
|---|---|
| GitHub via MCP | a hook before the tool runs, which blocks |
| GitHub via `gh` | the same hook, on an allow-list of command forms |
| Commits | the reflog hook shared with bug-hunter, after the command |

Only an agent-side hook can stop a post before it is public. Linear and Discord
are to be added the same way. The MCP check matches the server, not a list of
tool names, because a tool a name list missed would pass silently. It requires
a footer when the input has a string under a `body` or `comment` key at any
depth, so each review comment needs its own footer (inline comments are the
agent text reviewers read most). A payload that is not JSON passes: the hook fails
open, like the commit hook. For a stricter setup than a hook that fails open,
permission rules can deny the raw GitHub tools outright.

---

## Rejected: a GitHub Action

prose has no CI check; it runs only where the agent works, through the hooks
the skill installs.

**Why.** Installing the skill installs the hooks, so every agent using prose is
already checked locally, and CI would catch only agents that don't use it. The
remedy for those is asking them to use it. Igor builds its trailers in code and
verifies them itself. A CI check would also need a policy for which commits are
a person's and for rebased commits. It would need back the code that verified
rebased and re-encoded messages, deleted with the Action.

**Where this stops applying.** If agents that never install the skill commit to
repositories adopting prose. `verify-commit` and `verify-post` are what such a
job would run, and the rewrite handling would come back from `e8da005`.

---

## The posting hook reads an allow-list

For a Bash command, the hook reads a post's body only when `gh` is the whole
command and the body is a literal `--body` (or `--comment` for close and
reopen) in single quotes or in double quotes without `$`, backtick or
backslash, or `--body-file` naming an existing file. Any other command that
runs a `gh` post is blocked, and the message names those forms.

**Why.** Two bug-hunter runs found about 25 places where a general parser read a
command differently from bash, most letting an unsigned post through. With a
short allow-list nothing is left to diverge.

**Rejected.**
- **A general parser,** however careful.
- **A heredoc body form.** macOS bash 3.2 parses a heredoc inside `$( )`
  differently, and it needed five refusal rules for that shell alone.
  `--body-file` covers the same flow.

**Where this stops applying.** A deliberately disguised `gh` (`g''h`, `$GH`)
passes; the hook stops accidents, not an agent set on getting around it.

---

## A command that runs no gh post is not a post

A command that mentions a `gh` post verb but is not the whole-command form
passes when the hook can show the shell runs no `gh` post in it: every simple
command either names no `gh` as a word, or is a `gh` command that sends no
text (a label edit, `gh pr ready`, a close without a comment, `gh pr view`).

**Why.** Blocking every mention forced workarounds for commands that posted
nothing, such as a Python script whose string named `gh issue edit`, or
`cd … && gh issue edit 12 --add-label …`.

**How it keeps the allow-list's protection:** it reads no bodies, only shows
that no post runs, and blocks anything it cannot read exactly: backticks,
`<(…)`, `$'…'`, `${…}` beyond a name, `$(…)` in double quotes, unterminated
quotes, heredocs in parentheses or holding `$(`, multi-digit descriptors,
comments holding quotes or operators. The rules for each simple command:
- **The command word** is the first, after `if`, `then`, `elif`, `else`, `do`,
  `while`, `until`, `!`, `{` or `time`. `fi`, `done` or `}` alone is no
  command.
- **`gh` is named** when not followed by a letter, digit, `_` or `-`.
- **Text naming `gh` is data** only in a command from `DATA_COMMANDS` (`echo`,
  `cat`, `grep`, `git`, `python3` and a few more), which run neither their
  arguments nor their stdin. Any other command naming `gh` blocks, since it
  might run it (`sh -c`, `eval`, `trap`, `env -S`, `xargs`). `printf`, `test`
  and `[` are excluded: bash evaluates an array subscript given to `printf -v`
  or `test -v`, command substitution included.
- **A `gh` command** must be first and plain; its words are read after quote
  removal. `NO_TEXT_VERBS` lists the subcommands that send no text; `merge` is
  not on it.
- **A pipe or input redirection** matters only for the command that reads it,
  which must be a data command or a `NO_TEXT_VERBS` subcommand. A post verb
  reading input blocks even with no body flag: allowing it would rely on gh
  never reading a body from stdin except through `-F -` (`--body-file -`),
  which a later gh could change. When input can reach a group, loop or subshell, every
  command in it must be a data command.

**Rejected.**
- **Python's `shlex`.** It knows no heredocs, `$(…)` or bash comments.
- **Reading bodies in longer commands.** An earlier `cd` or `printf > body.md`
  changes which file `--body-file` names.
- **A list of commands that run text as code.** Such a list was missing `trap`
  and `env -S`, and is never complete; a closed list of data commands fails
  toward blocking.

**Where it stops applying.** A script handed to another interpreter
(`python3 - <<'EOF'`, `node -e`) can run `gh` itself, and text the shell
evaluates twice (`(( ))`, `let`, zsh `${(e)…}`, git aliases, `rebase -x`) is a
disguise, out of scope. Revisit if `gh` gains a way to read a body from stdin
without `-F -`.

---

## Cursor's posting hook is wired as a best guess

The posting hook is wired for Cursor on `beforeShellExecution` and
`beforeMCPExecution`, and the README says it is unverified.

**Why.** Cursor's payloads and its `permission` answer are documented and the
script reads them; waiting would leave Cursor users with no check. Unverified:
what a `beforeMCPExecution` matcher matches (so the script filters on
`mcp_server_name` itself) and a run in a real Cursor. Cursor blocks when a
permission hook prints no valid JSON, so every allowing path prints
`{"permission":"allow"}`.

---

## Which files are docs

Docs are `.md`, `.mdx`, `.markdown`, `.rst`, `.adoc`, `.asciidoc`, and files
named `README`, `CHANGELOG` or `CONTRIBUTING` with any extension. Specs are
anything under an `openspec/` directory.

**Docs are exempt only where vendored.** A doc under `node_modules/` or
`vendor/` is not prose; one under `build/`, `out/`, `dist/` or `generated/` is,
because people keep authored docs there. Code comments still skip the
scanner's whole list of build and vendored directories.

**Comments** are found by lexers for Python and the C family, and own-line `#`
comments in shell, YAML, TOML, Ruby, Perl, R, PowerShell, `Dockerfile` and
`Makefile`. A `#` after code is not read, since it may be in a string. In
JavaScript, a `/` opens a regex literal only after an operator or keyword and
only if it closes on the line; elsewhere its `//` is a false item in the
listing, which changes no trailer.

**Rejected: `.txt` as a doc type.** It takes in `requirements.txt` and
`LICENSE.txt`.

---

## Scripts are found from the skill's base directory

SKILL.md defines `S` as `scripts/` in the skill's base directory, the one
Claude Code names on its "Base directory for this skill:" line. When `prose.py` prints the command for the next call, it uses the path it
was run by, without resolving symlinks.

**Why.** Igor loads workers' skills from a pinned directory where the home
installs are missing or hold a different copy, and grants `prose.py` by that
path, so any other path is denied, including the clone the link resolves to.

**Rejected.** Home-directory paths, which cover only `manage-skills` installs;
`${CLAUDE_SKILL_DIR}`, which another agent reading SKILL.md sees unreplaced;
the resolved path, which the by-path grant denies.

---

## Known gaps, recorded rather than fixed

Each is left on purpose; its fix says what would close it.

- **`core.commentString` is not read,** only `core.commentChar`. Fix: read it.
- **`gh api` and `gh pr merge --body` are not checked.** Fix: add them, with
  `gh api`'s `-f body=` and `--input` as body sources.
- **zsh `extendedglob` or `magicequalsubst` change what gh receives** from an
  unquoted `#`, `^` or `=`. Neither is set on the machines checked. Fix: refuse
  those characters unquoted.
- **Two `prose check` runs at once in one checkout fail on git's index lock.**
  Each worktree and each Igor clone has its own index. Fix: compute the tree
  from a copy of the index (`GIT_INDEX_FILE`), tested to give the same hash.
- **Only an MCP server named exactly `github` is checked** in Claude Code. Fix:
  match case-insensitively and by substring, as the Cursor path does.
- **Config given only to `git commit`** (`git -c trailer.…`) is not seen by the
  check, giving an honest mismatch. It fails closed.
- **`commit.cleanup=verbatim` with a leading blank line,** and
  **`git interpret-trailers` without `--no-divider` on a message holding a
  `---` line,** both fail verify on an honest commit. They fail closed.

---

## Open

- More rules.
