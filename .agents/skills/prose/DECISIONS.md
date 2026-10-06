# prose — decisions

`prose` makes agents rewrite what they write for human reviewers, and proves
they did. The rules themselves are in `rules.md`; this file is why they, and
the mechanisms around them, are the way they are.

Each entry: the decision, why, and what was rejected. **Open** marks what is
not decided yet.

---

## Why the skill exists

Reviewers spend most of their time reading, and agent-written code is usually
easy to read. The text around it is not: long, discursive, ambiguous, and
switching topics mid-block. Agents write it that way because they rank other
goals — completeness, defensibility — above being understood.

**Rejected: more instructions.** `sharper-comments`, `CLAUDE.md` rules and
memories all failed the same way: agents treat advisory text as optional and
skip it. So this skill's value is enforcement. The rules matter, but a rule no
one can check is the thing that already failed.

---

## Rules 1–3: fewer claims, cut to answer review, no claim-checking

The rules are in [rules.md](rules.md).

**Why.** Wordy text makes more claims, and every claim is something a
reviewer (bug-hunter, an AI reviewer, a person) can attack. An agent answers
each attack with a hedge, which is another claim. A few rounds of that produce
the unreadable block. Re-verifying every claim inside this skill would rebuild
the same loop.

**Rejected: readability scores** (Flesch and similar), even as a flag. They
count syllables and sentence length, not whether a reviewer can find what they
need, and text rewritten to raise them is no easier to understand (Redish; the
ISO plain-language standard excludes them).

**Open, for rule 2's wording.** Research finds vague hedges lower trust while
a stated limit raises it (van der Bles 2020, Jensen 2008). One explicit scope
line — "Checked: X. Not checked: Y." — is narrowing, not hedging.

---

## Rule 4: each sentence follows from the last

**Decision (Adam, 2026-10-04).** No abrupt switch to a subject the reader
wasn't expecting, or may not know or care about. A new subject the reader
does need gets its own paragraph that introduces it.

**Why.** Agents' text kept making non-sequiturs after the prose pass existed,
and they slowed reading down: a README about GitHub saying in passing how
claiming works on Linear. Each one makes the reader hesitate, reread, or ask
the agent what it meant.

**Ranked fourth,** after *Read once, understood once*, because an abrupt
switch fails the same way: the reader stops and goes back. It is not *One
topic per block*, which is about how text is divided; this is about whether
one sentence leads to the next. `RULES_IN_FULL` became 7, so *Spend words
where they save reading time* is still printed in full with its example.

---

## Scope: anything a human reviews

READMEs and other docs, code comments, architecture docs, specs, commit
messages, pull request descriptions, and posts to GitHub, Linear and Discord.

Commit subjects and ticket comments are not exempt for being short. Agents
bloat them too; that is the problem.

---

## `sharper-comments` is removed

It is deleted in the pull request that adds this skill, so there is never a
gap with neither installed.

**Rejected: merging it in.** Its rules do not carry over unless decided again
here. Its comment scanner may be reused to find comment lines in a diff.

---

## Commits carry a trailer, and a script decides what it may say

A commit carries one trailer, `Prose: ✓ <tree>:<message>`, which `prose check`
prints and the agent passes to the shared commit script. `prose check` also
lists the prose in the staged change — Markdown, specs, the comments the diff touches, the
commit message — for the agent to pass over. (Revised 2026-09-26: the skip
value is dropped; see *Every commit gets the pass*. Revised 2026-09-27: one
line signing the snapshot replaces `Prose: checked` plus `Prose-Sig`; see *The
signature signs the snapshot*.)

The trailer is made when the pass runs and checked when the commit lands, so
staging a change or editing the message after the pass breaks it. Twelve hex
characters per half is enough: it stops a trailer written from memory, and no
hash can prove when it was computed. The message must hash the same before
the commit (the text passed in) and after (what git stored, normalised, minus
the trailers git added at its end), which needs its own test.

**One commit carries both skills' trailers.** Composing `Bug-hunter:` and
`Prose:` in one commit is the shared library's job, not this skill's: its
`commit-with-trailers.sh` takes any number of trailer families. A family
is a trailer's key, its value and how that value is bound to the commit; see
the library's *One commit, several families*.
prose's family is `--verified-value scripts/verify-staged.sh Prose <value>`:
the value binds itself, and `verify-staged.sh` refuses the commit if the staged
tree or the message no longer matches it. Bug-hunter's is `--minted-by` with
its own minter. A caller that makes the commit, such as the `commit` skill,
passes both in one command.

**An amend goes to git directly.** The commit script makes a new commit and has
no amend mode, so under `--amend` `prose check` prints
`git commit --amend -F <the file it read> --trailer "<the Prose: line>"`.
Nothing verifies that trailer before the amend lands; the hook reports a
mismatch after it. *Fix, if amends need the check before landing:* an amend
mode in the commit script.

**Known gap: a skip note is not stopped before the commit.** prose has no skip
value, but the commit script runs no verifier for a value starting `skipped`
(see [the library's decision](../../lib/commit-trailer/DECISIONS.md#a-family-whose-value-is-its-own-binding)),
so a `Prose: skipped…` commit lands and only the hook reports it, as `unrecognised:`. It is
left open for Adam: change the library, or keep it recorded here.

**Rejected: counts in the trailer** (text blocks checked, rewritten, cut).
Nobody needs them, and "rewritten" needs a before-and-after of the pass.

---

## Posted text carries a signed footer

A pull request description or comment ends with a short line such as
`prose ✓ 3f2a91`. The hash covers the text above it and is printed by a
script. A hook recomputes it from the tool's input before the post goes out
and blocks a mismatch.

It proves the footer matches the final text, so in practice a script produced
it for that text. It does not prove when, or that the rewrite was good. The
hashes are unkeyed, so an agent that reimplemented them could forge one; that
is not defended locally, because a secret key would sit on the same disk the
agent reads. What the design stops is skipping: a missing or typed value
fails. Forging is forbidden by SKILL.md's "Never" list and caught at review
like any other lie. Igor gets the stronger guarantee by running the passes
itself.

**What the footer hashes (confirmed by Adam, 2026-09-28).** The text above the
footer, with LF line endings, trailing blanks off each line and trailing blank
lines removed. The footer is the last non-blank line and matches
`prose ✓ <6 hex>` exactly. `sign` replaces a footer already there, so
re-signing after an edit works. *Why:* only invisible whitespace is
normalised; any change to a word breaks the footer.

**Rejected: a plain `prose ✓`.** It can be typed from memory without running
anything, which is the failure bug-hunter's tree binding was added to stop.

---

## Checks are layered by where the text goes

| Destination | Check |
|---|---|
| GitHub via MCP (Linear and Discord planned, not built) | a hook before the tool runs, which blocks |
| GitHub via `gh` | the same hook, on an allow-list of command forms (see *The posting hook reads an allow-list*) |
| Commits | the reflog hook shared with bug-hunter, after the command |

Only the agent-side hook can stop a Linear or Discord post before it is
public. There is no CI check: see *Rejected: a GitHub Action*.

**Rejected.**
- A git `commit-msg` hook: per-clone setup, and the reflog hook, which the
  skill installs, covers the same ground.
- One hook event for everything: commits would be reported a turn late, and
  Cursor splits shell and MCP events anyway.

Permission rules that deny the raw posting tools stay an option for strict
setups.

**Which tools, to start: GitHub.** Code is already covered, since comments and
docs reach reviewers through commits. The hook matches every `mcp__github__`
tool and requires a footer only when the tool's input carries a body or
comment field, plus the `gh pr` and `gh issue` commands that post text (see
*The posting hook's reach*). Not built yet: Linear and Discord, to be added
the same way.

**Rejected: a list of tool names.** A list is never complete, and a tool it
misses passes silently. Matching the server and checking for a text field
makes an unanticipated tool checked by default.

**The hooks use several-hooks `hook.json`.** This skill's `hook.json`
used the list form from the start, rather than a single-hook workaround that
would have been thrown away.

---

## Rejected: a GitHub Action

**Decision (Adam, 2026-09-30).** prose has no GitHub Action. The checks run
only where the agent works, through the hooks the skill installs.

**What it would have caught.** Agent-written commits and pull request
descriptions from agents that do not use the skill: a missing, stale or
hand-typed `Prose:` trailer, or a description without a matching footer.

**Why.**
- Installing the skill installs its hooks, so every agent that uses prose is
  checked locally: the commit script refuses a stale trailer, the reflog hook
  reports any commit without a valid one, and the posting hook blocks an
  unsigned post.
- So CI would catch only agents that do not use the skill. The remedy for that
  is the maintainer asking agents to use it, not failing their pull requests.
- Igor (adamstallard/igor#139) runs the passes as its own pipeline steps and
  builds the trailers in code, verifying tree hashes before it commits. CI
  would only re-check Igor's own work.
- bug-hunter has no Action either.
- It cost maintenance and design for little enforcement: a token to check out
  the private shared-skills repository, a rule for which commits in a pull
  request are a person's, and a policy for rebased commits in CI.

**What removing the Action removed.** Without CI, the reflog hook is the only
check on a landed commit, and it skips rebases and cherry-picks, including a
message-only amend of one. So the code that verified a commit after someone
else rewrote it went too:
- reading a message's raw bytes when a rewrite left UTF-8 under another
  encoding's label, and deciding which labels keep ASCII;
- leaving `git cherry-pick -x`'s line out of the message hash;
- the tests of rebases under Latin-1 and SHIFT_JIS, of relabelled headers, and
  of `cherry-pick -x`, and the known gaps about re-encoding.

In their place, `verify-commit` reports a commit stored under any encoding
label other than UTF-8 as a mismatch. The refusals of a non-UTF-8 message and
of a non-UTF-8 commit encoding stay, because a plain commit breaks without
them (see *The signature signs the snapshot*).

A `git cherry-pick -n -x` finished with a plain `git commit` is not a replay to
the hook, so it is verified, and the `-x` line is now signed: the agent runs
`prose check` on that message first. (Before this, reusing the original
trailer verified only when the new tree matched the one signed.)

**Where this stops applying.** If agents that never install the skill start
committing to repositories that adopt prose, CI is the only place their
commits can be checked. `verify-commit` and `verify-post` are the checks such
a job would run; it would still have to decide which commits are a person's
and how to fetch `prose.py`. It would also need the rewrite handling above
back, from `e8da005`, since CI sees rebased and cherry-picked commits.

---

## The rules reach the agent through `prose check`

`prose check` lists the prose in the change and then prints the rules. The
rules are written once, in `rules.md`, which the script reads. (Revised
2026-09-28: `SKILL.md` no longer keeps a short version; see *The rules live
only in rules.md*. Revised 2026-09-30: the first call of `start`, `check` or
`sign` prints them, and a signature needs a first call; see *The rules are on
screen before a signature*.)

**Why.** Agents skip documents; they read a command's output at the moment
they act on it. Bug-hunter's hook report is the one text agents reliably read
when they fail, and this puts the rules in the same position.

**Rejected: rules only in `reference.md`.** A rule behind a pointer is read
after the mistake, not before (bug-hunter's *The trailer rule is stated
inline, not only pointed at*).

---

## The rules live only in rules.md

**Decision (Adam, 2026-09-28).** `rules.md` holds the full rules text: the
principle, scope, the pass with its reader-goals table and what never to cut,
the rules most important first with their examples, and how agents cheat on
the pass. `SKILL.md` keeps no copy; it says that `prose check` prints the rules
and `rules.md` is their only copy.

`prose check` prints it by its headings, every time: everything before the
rules section, rules 1 to 7 in full, the rest as one-line checklist items (their
`###` heading), and the cheat list. It refuses when a section is missing or out
of order, or the rules are not numbered 1, 2, 3, even on a signing call.

**Why.** A second copy drifts from the first, and the pass does not need one:
the agent reads the rules in the check's output, at the moment it acts.

**Rejected: a one-line summary of each rule in `SKILL.md`.** It is a second copy
too, and a summary is read in place of the rule.

**Known gaps.** A fence closes at the next line starting with the same three
characters, so a four-backtick fence holding ``` lines, or a ```` ```sh ```` line
inside a ``` fence, closes early; the file is then refused, loudly. A `####`
heading inside a rule is refused too. *Fix, if rules.md needs either:* track
fence length and info strings as CommonMark does, and allow `####` inside a
rule.

Two title-check gaps are also left (Adam, 2026-09-28). `rules.md` ships with the
skill and changes only through reviewed pull requests, so a stricter check
would guard almost nothing. The gaps:
- **A blank title is accepted.** A `# ` line with no text passes. *Fix:* match
  the title with `^# \S`.
- **The check is looser than its message.** The refusal says a title and a
  principle come first, but a title after the principle, or with no principle,
  passes. *Fix:* require the first non-blank line to be `# <text>`, with some
  text before `## Scope`.

---

## `prose check` ends with the shared result block

**Decision (Adam, 2026-09-27).** Skills a committing caller uses end their
output with one result block, printed by the shared script
`.agents/lib/commit-trailer/result-block.sh`, so no one types it.
`prose check` ends with that block for skill `prose`: its one trailer line,
normally with no open decisions. The format lives in the shared script only;
prose does not copy it.

`render_result` in `prose.py` is the one call to it, on the signing call. Either
call of `prose check` stops before printing anything when the script is
missing.

---

## `prose check` runs the pre-commit hook first

**Decision (Adam, 2026-09-30).** In a repository with a pre-commit hook, both
calls of `prose check` run it before they list or hash anything, through the
shared library's `run-pre-commit.sh`. The signing call signs what the hook left
staged. In a repository without one, nothing runs and the output is unchanged.

**Why.** `git commit` runs the pre-commit hook after the check, and a formatter
there (prettier on Markdown, black on docstring quotes) can rewrite and
restage files. The signature then no longer matches the staged tree, the commit
script refuses the commit, and the agent has to run both calls again. With the
hook run first, the signature covers the formatted tree.

**Why the first call runs it too.** So the text the agent does the pass on is
the text that lands. Run only before signing, a formatter that reflows a README
would put text in the commit that the agent never read. A failing hook also
stops the agent before the pass, not after it. The cost is small: when nothing
staged changes between the calls, the signing call skips the hook (the record,
below); when the pass restages a file, the hook runs again, on the new text.

**How it uses the library.** After the hook passes, `run-pre-commit.sh`
records the staged tree and the state it ran in, in the git directory. A later
call in the same state skips the hook. So in the usual flow the hook runs once
in total: the first call runs it, and the signing call and the commit script
find the pass recorded. A test counts the runs. See the library's
`DECISIONS.md`, *The pre-commit hook runs before anything is bound* and *The
pre-commit hook runs once per commit*.

**What each result does.**
- **`unchanged`**: `prose check` carries on and prints nothing extra.
- **`changed`**: `prose check` carries on, and says on stderr, in one line,
  that the list (first call) or the trailer (signing call) is of what the hook
  left staged.
- **Exit 1** (the hook failed, the staged tree could not be read, or git is
  older than 2.36 and there is a hook): `prose check` exits 2, its refusal
  code, after the library's reason. The first call issues no token; the
  signing call prints no trailer and does not spend its token, so the same
  token signs after the fix.

**With `--amend`, the hook runs too.** `git commit --amend` runs the hook
itself and does not read the record, so the hook runs twice. A formatter that
already ran changes nothing the second time, so the signature holds; without
the early run, a formatter breaks an amend's signature as it breaks a
commit's.

---

## Code shared with bug-hunter

The reflog check and tree minting live once in `.agents/lib/commit-trailer/`.
Each skill keeps thin wrappers naming its skill and trailer key. See that
library's `DECISIONS.md`.

**The commit hook verifies through a library callback.** The shared library
provides what prose needs: the optional `commit_trailer_verify` callback and
the `--verified-value` family. prose defines the callback in `hook-report.sh`;
the library calls it for each commit carrying a `Prose:` trailer, in place of
its own `<key>-Tree` check, and reports what `verify-commit` says.

Hooks ship with this skill through `hook.json`, in `manage-skills`'s list form.

**One commit with bug-hunter's trailer (Adam, 2026-10-01).** While bug-hunter
is running, its commit step runs prose's two calls and carries the `Prose:`
value; prose's own combined command is for an agent committing itself. See
the library's *Every installed skill's trailer, on one commit*.

---

## No length budgets, beyond the commit subject limit

**Decision.** `prose` sets no per-kind length limits. The 72-character commit
subject limit the `commit` skill already has stays.

**Why.** Rule 1 already cuts length: a sentence stays only if a reader needs
it. A number reads as a target: short text gets padded to it, long text loses a
sentence the reader needed, and the agent optimises the count instead of the
reader — the reason readability scores were rejected. Any number today would
be a guess from one correlational figure (agent PR descriptions: median 355
words against 56 for humans).

**Where this stops applying.** If bloat still gets through once `prose` runs,
measure first: record word counts before and after each pass, and set limits
from that data.

---

## The agent names the reader's goals before it gets proof

**Decision.** `prose check` prints no `Prose:` line, and `prose sign` prints no
footer, until the agent passes the reader goals it chose:
`--goals "review the fix; check it's safe to merge"`, the most probable reasons
a reader opens this text, most probable first. `check` echoes them at the top of
its output so the text is ordered and cut against them. The goals are not put in
the trailer or the footer.

**Why.** Agents skip listing the reader's goals, and without goals there is
nothing to cut against. The script cannot judge them. The flag makes the step
part of the command, so it cannot be skipped silently.

**Revised 2026-09-30.** The goals now open the first call, which prints the
rules and a pass token; the signing call takes the token. See *The rules are
on screen before a signature*.

---

## The rules are on screen before a signature

**Decision (Adam, 2026-09-30).** A trailer or footer takes two calls:

1. **The first call** is `check` or `sign` without `--pass`. It needs
   `--goals`, prints the goals, the rules and a pass token, signs nothing, and
   exits 4.
2. **The signing call** is the same command with `--pass <token>`. It signs,
   and does not print the rules again.

Every commit and every post gets its own pair. In Claude Code, a hook also
blocks a session's first file write or post until `prose start`, a warm-up
that prints the goals and the rules and issues no token, or a first call has
run in that session.

**Why.** The rules help most during the rewrite pass: a draft exists and is not
final. Before this, `--goals` on the first call signed at once, and `sign`
printed no rules at all, so an agent could sign without the rules ever
reaching its context.

**What it proves:** a first call printed the rules before the signature was
issued, and, in Claude Code, before the session's first file write or post.
**What it does
not prove:** that the agent read them, the order it thought in, or that the
pass was good. Forging a token file or a session mark is out of scope, as it is
for the footer (*Posted text carries a signed footer*): the design stops
skipping, not deliberate forgery.

### The pass token

- **One token signs one text (Adam, 2026-09-30).** A session writes several
  texts with different readers: a doc edit, then a commit message, then a pull
  request description. A token that signed more than one would let every later
  text skip choosing its own reader's goals. So a token is:
  - **bound to the goals** given on the first call that issued it. The signing
    call may repeat `--goals`, and is refused if they differ;
  - **bound to its command**: a `check` token signs only a commit, a `sign`
    token only a post;
  - **single use.** A signing call refused for its text (a `#` line, say)
    keeps the token; only a printed signature spends it.
- **Bound to the goals, not the text.** The pass revises the text, so binding
  the draft would punish revising.
- **Expires after 2 hours.** That is longer than one pass, and an expired token
  costs one more first call. Each first call deletes token files older than
  that.
- **Exit 4 for a first call**, distinct from 2 (refused) and 0 (signed), so
  `sign … > signed.md && gh …` stops at the first call.
- **Where it lives (Adam, 2026-09-30):** one file per token in `prose/passes/`
  under the repository's git directory (`git rev-parse --git-common-dir`);
  outside a repository, in `${XDG_STATE_HOME:-$HOME/.local/state}/prose/passes/`.
  - The git directory is never committed and never shows in `git status`.
  - Igor runs each worker in a throwaway clone with a shared service-user HOME
    (`workerEnv` in Igor's `src/execute.ts` passes HOME). A per-clone location
    gives each worker its own tokens: no contention between concurrent workers,
    no token issued to one redeemable by another, and they go with the clone.
  - A token is written under a temporary name in the same directory, then
    renamed, so a concurrent call never reads half of one.
  - Both calls must run in the same repository, or both outside one.

### `prose start`: a warm-up before any draft exists

The gate blocks the first file write, so the call that opens it has to work
before there is a draft. `check` needs a message and a staged change, so
`start` takes only the goals: it prints them and the rules, and marks the
session. It issues no token. If it did, that token would sign a text whose own
reader was never named, which is what one token per text rules out. `start`
exits 0: it has done its whole job.

### `--trailers-only` is removed (Adam, 2026-09-30)

Nothing outside the tests used it, and SKILL.md never mentioned it. The
signing call already prints only the result block, so the flag would only be a
way to get a trailer with less output: what an agent reaches for to skip the
rules.

### The gate (Claude Code only)

`scripts/require-first-call.sh` is a PreToolUse hook on Write, Edit, MultiEdit,
NotebookEdit, Bash and the GitHub MCP tools. When the session has no mark, it
blocks, with exit 2 and the command to run on stderr:
- any Write, Edit, MultiEdit or NotebookEdit call, whatever the file;
- a `gh` post, as the posting hook finds one (`gh_bodies`), or a GitHub MCP
  call with a body field.

It reads no file and tells no kind of file from another; see *The gate blocks
a session's first file write*.

**The mark first (Adam, 2026-09-30).** The gate checks the session mark before
anything else, so a marked session does nothing else.

**The session mark.** `start` or a first call writes an empty file named by the session id
in `${XDG_STATE_HOME:-$HOME/.local/state}/prose/sessions/`, deleted after 30
days. The id comes from `--session`, which the block message fills in, or else
from `CLAUDE_CODE_SESSION_ID`. Marks live in the state home, not the git
directory: a session spans repositories, and the hook's working directory can
differ from the Bash command's.

**It fails open.** The wrapper passes a message on only when `prose.py` exits
2 with one. A missing `python3`, a crash, a payload without a session id, or a
state directory it cannot read lets the call through, silently. A broken gate
would otherwise block every write.

**The Claude Code API it relies on** (code.claude.com/docs/en/hooks,
/hooks-guide, /env-vars and /agent-sdk/hooks, read 2026-09-30):
- PreToolUse exit 2 blocks the call and feeds stderr to Claude ("Use exit 2 to
  block with a stderr message").
- The payload's `session_id`, `tool_name` and `tool_input`. A subagent's
  calls carry its parent's `session_id`.
- `CLAUDE_CODE_SESSION_ID` is set for Bash tool commands and "matches the
  `session_id` field in the hook JSON input".
- The tool names. The gate reads `file_path` and NotebookEdit's
  `notebook_path` only to name the file in its message; if one is renamed, the
  message leaves the path out and the call is still blocked.
- Matchers are unanchored regular expressions, so this one is anchored.

### Rejected

- **The goals as the gate.** An agent passes them on the first call, which
  then also signed.
- **Printing the rules on the signing call, with no gate.** They would appear
  after the footer is issued, when nothing is left to rewrite.
- **Injecting the rules into the agent's context from a hook**
  (`additionalContext`). Shown, not acted on: what fixed skipping in bug-hunter
  was making the agent run a script. It is also documented only for
  PostToolUse, after the write it should come before.
- **Binding the token to the draft.** It punishes the revision the pass is for.

### Known gaps

- Files written through Bash (`echo … > README.md`, `sed -i`) skip the gate.
- Cursor has no gate (Adam: fine).

### Superseded 2026-09-30: the gate that looked for prose

Until *The gate blocks a session's first file write*, the gate blocked only a
doc or spec, a code edit that added comment text, a Markdown notebook cell or a
post. It diffed the whole file on disk against the edited file and compared
comment text line by line; it lexed the added lines alone when the file did not
parse. These decisions from the same day refined that detection. Each is
superseded by *The gate blocks a session's first file write*:
- **Tool directives were not prose (Adam).** A comment holding only directives
  (`noqa`, `type: ignore`, `eslint-…`, `@ts-…`, a coding line and similar) did
  not open the gate, because it instructs a tool, not a reader; text after the
  directive did.
- **Git work tree first, then the session's directory (Adam).** Directory names
  counted only below the project, so a checkout under `~/out/` was not build
  output; git came first because a session can start above the repository.
- **A submodule stayed vendored.** A submodule the session worked outside of
  belonged to its superproject, so one under `vendor/` stayed vendored.
- **A notebook code cell was compared with its source on disk (Adam),** like a
  code file; a replace without `cell_type` kept the type read from the notebook.
- **Known gap: JS regex literals.** A regex the lexer did not recognise had its
  `//` read as a comment, which blocked. The gap remains only in `prose
  check`'s listing; see *Comments in more languages*.

---

## The gate blocks a session's first file write

**Decision (Adam, 2026-09-30).** The gate blocks a session's first Write, Edit,
MultiEdit or NotebookEdit call to any file, and its first `gh` or GitHub MCP
post, until `prose start` or a first call has run in the session. It does not
look for comments, tell docs from code, or classify paths.

**Why.**
- **The heuristic did not converge.** Two bug-hunter runs on "does this edit
  add a comment" each hit their 3-iteration cap, and every iteration found 4
  or 5 real bugs: fragments of files that do not parse, regex literals,
  directives, docstrings, notebook cells, paths under build or vendored
  directories.
- **The gate is a warm-up.** The pass token already guarantees the rules are
  printed before any signature, so the gate's precision barely matters.
- **Nearly every session writes prose,** a commit message at least, so one
  `prose start` per session costs less than a heuristic nobody gets right.

**Accepted cost.** A session that writes no prose but edits a file must run
`prose start` once.

---

## Every commit gets the pass

**Decision (Adam, 2026-09-26).** There is no skip value. Every commit has a
message a reviewer reads, so every commit gets the pass, and the only trailer
value is the one `prose check` prints (now `✓ <tree>:<message>`; see *The
signature signs the snapshot*). Any other value is reported as unrecognised.

**Why.** The message always counts as prose (*short kinds are not exempt*), so
no commit honestly qualifies for a skip; keeping the value would only have
kept a check for a trailer no script prints.

---

## The signature signs the snapshot

**Decision (Adam, 2026-09-27).** One trailer line, `Prose: ✓ <tree>:<message>`:
the first 12 hex of the staged tree, from `git write-tree` when `prose check`
runs (as the shared library's `mint-trailer.sh` reads it), and the first 12
hex of the sha256 of the message as `prose check` read it. There is no
`Prose: checked` line and no `Prose-Sig`. `verify-commit` requires both halves;
its reason starts `missing`, `unrecognised`, `mismatch` (the message half) or
`tree` (only the tree half). The reflog hook reports any failure, and exempts
cherry-picks and rebases by reflog action. (Replaces *The signature covers the
prose, not the tree*, 2026-09-26.)

**Why.** The signature's job is proving a script ran over the final text. Any
committer can honour a tree hash: stage, check, commit. The one case the tree
half gets wrong, a rebase or cherry-pick, is one the hook skips.

**Rejected: the rebase-proof diff engine.** History: from 2026-09-26 the
signature hashed the prose lines each commit added and removed, so a rebase
kept it, and it grew rename, cancellation, diff-pin, gitlink and parse-failure
rules, each another way for check and verify to disagree.

**The listing is not hashed.** `prose check` still lists the prose so the
agent knows what to pass over: the message, each doc or spec file the staged
diff touches, and each code comment it touches, as `path:span (comment)`. A
code file that does not parse is listed as "did not parse", and one that
cannot be read as "could not be read"; neither stops the check. History
language in a touched comment (the patterns `sharper-comments` measured) is
printed under "Flags (warnings, not blocking)"; a flag never changes the exit
code or the trailer.

**Messages are UTF-8 (Adam, 2026-09-26).** `prose check` refuses:
- a message that is not valid UTF-8, or holds a Unicode noncharacter: git
  reads either as Latin-1 and rewrites it as UTF-8 when it stores the commit;
- a non-UTF-8 `i18n.commitEncoding`: git stores the UTF-8 message under that
  label, and reading it back converts the trailer's `✓` into other characters.

`verify-commit` reports a commit stored under any label other than UTF-8 as a
mismatch. Only config the check never saw, such as `git -c` at commit, puts
one there.

**Which lines of the stored message are compared:** see *The signed message
is found by searching from its end*. The line `cherry-pick -x` adds is signed,
but still counts, as in git, towards reading its paragraph as a trailer block.
`prose check` refuses any `trailer.*` config other than `trailer.separators=:`,
since those settings make `git commit --trailer` drop, replace or move lines.

**Where this stops applying.** Any change to the staged files after the check,
code included, breaks the tree half: the trailer attests to the snapshot the
pass ran on. A rebase or cherry-pick changes the tree too; the hook exempts it
by reflog action.

---

## The signed message is found by searching from its end

**Decision (Adam, 2026-09-30).** `prose check` hashes the whole message it is
given. `verify-commit` accepts a commit when its stored message, minus 0, 1, 2
or more trailer-shaped lines (`Key: value`, as git parses them) taken from the
end of its last trailer block, hashes to the message half. A paragraph left
empty is dropped. The search stops at an indented line, at any other line that
is not trailer-shaped, and at the start of the paragraph; it never reaches the
title. There is no list of trailer keys.

**Why.** `git commit` adds trailers only at the end of the message: to the
last paragraph when it reads that as a trailer block, otherwise as a new
paragraph. `prose check` refuses the config that could move them
(`refuse_configured_trailers`). So the signed text is always the stored
message minus some lines from that end. A key list left out every line with a
listed key, even in an earlier paragraph or when it carried prose
(`Bug-hunter: the fix is safe`), so an edit to that line verified. It also had
to grow with every skill that adds a trailer.

**An indented line stays signed.** git never wraps the trailers it adds, so an
indented line is text someone wrote. The search stops there, and the line it
continues stays signed with it.

**git's rewrite of the last block still matches.** When git adds trailers to
the last paragraph, it rewrites that paragraph as `token: value` lines and
joins an empty-valued line with the indented line after it. Both hashes put
the last paragraph in that form first, so an author-written trailer block
verifies whether git added to it or not. The tests commit for real through
`--trailer`, `-s`, `git interpret-trailers` and the commit script.

**`verify-staged` hashes the message as given.** The commit script passes it
the message before any trailer is added, so there is nothing to search.

**No refusal for an empty-valued key before an indented line.** git joins the
two into one line, which is signed like any other.

**Accepted cost.** A trailer-shaped line appended at the end after signing,
such as `Reviewed-by: …`, does not break the hash; an edit anywhere else does.
Trying several bodies raises the chance of an accidental 12-hex match, but
negligibly.

**Rejected: keep the key list, but strip only from the end.** It closes the
same gap and keeps "only known keys may be appended", but keeps a list that
every new skill must be added to.

---

## The posting hook reads an allow-list

**Decision (Adam, 2026-09-26).** For a Bash command, the hook reads a post's
body only when `gh` is the whole command and the body is one of:

- a literal `--body` (or `-b`, or `--comment`/`-c` for close and reopen) in
  single quotes, or in double quotes with no `$`, backtick or backslash;
- `--body-file`/`-F` naming a file that exists.

Any other command that mentions a gh post verb is blocked as unreadable, and
the block message names these two forms and suggests signing into a file
(`prose sign … > signed.md`, then `--body-file signed.md`). The general shell
parser it replaces is deleted.

**The heredoc form was dropped (Adam, 2026-09-26).** It was first accepted as a
third form, exactly `--body "$(cat <<'EOF'` … `EOF` … `)"`. macOS `/bin/bash`
3.2 parses a heredoc inside `$( )` differently from the text the hook reads,
and it needed five refusal rules for that shell alone: unbalanced parens, `#`
comments, backslash-newline, `$'…'` and `$"…"`. zsh read it correctly, but the
Bash tool may run bash. A heredoc body is now blocked like any other
unreadable form; `--body-file` covers the same flow.

**Why.** Two bug-hunter runs found about 25 places where the parser read a
command differently from bash (quoting, heredoc contexts, redirections, pflag
grouping), most of them letting an unsigned post through, and every iteration
found more. With a short allow-list nothing is left to diverge.

**Rejected: a general parser**, however careful. Each fix added states that
drifted from bash in new places.

**Where this stops applying.** A command that runs no `gh` post passes even if
it mentions one: see *A command that runs no gh post is not a post*. A
deliberately disguised `gh` (`g''h`, `$GH`) is not recognised; the hook stops
accidents, not an agent set on getting around it.

---

## A command that runs no gh post is not a post

**Decision (Adam asked for the fix, 2026-10-04).** A Bash command that
mentions a `gh` post verb but is not the whole-command form passes when the
hook can show the shell runs no `gh` post in it. That holds when every simple
command in it either:

- names no `gh` as a word: the post appears only as data, inside quotes or a
  heredoc given to a command that does not run them, or in a comment; or
- is a `gh` command that sends no text the hook checks: a label, assignee,
  reviewer or milestone edit, `gh pr ready`, a close without `--comment`,
  or a read such as `gh pr list` or `gh issue view`.

A `gh` command with a body flag must still be the whole command, as before.

**Why.** Blocking every mention forced workarounds for commands that posted
nothing. Two were seen in one day: an inline Python script whose comment and
Markdown string named `gh issue edit`, and `cd … && gh issue edit 12
--add-label …`, which only changes a label. The bare label edit already passed;
only the longer command was blocked.

**How this keeps the allow-list's protection.** The allow-list was chosen
because a parser that reads bodies drifted from bash and let unsigned posts
through. This reader reads no bodies; it only shows that no `gh` post runs,
and anything it cannot read exactly is blocked as before:

- backticks, `<(…)`, `$'…'`, `$"…"`, `${…}` beyond a name, `$(…)` inside
  double quotes, an unterminated quote. An unquoted `$(…)` is read as a
  subshell, so the commands inside it are checked like any other;
- a heredoc inside parentheses, where bash 3.2 differs, or whose body would
  start while a `$(` on its line is still open, since both shells run that
  `$(…)` first; an unquoted heredoc body holding `$(`, a backtick or a
  backslash; a heredoc with no end line;
- a number before `<` or `>` other than one ASCII digit: zsh reads `12>` as
  the word 12, bash as a descriptor, and neither reads `١>` as one;
- a comment holding quotes or operators, in case a shell does not read it as
  one; a word with `[` left open (`a[1<<EOF]=5` is no heredoc to bash).

How each simple command is read:

- **Which word is the command.** The first word, after any unquoted `if`,
  `then`, `elif`, `else`, `do`, `while`, `until`, `!`, `{` or `time`, since
  these run nothing themselves: `if grep "gh pr create" …` is a `grep`, and
  `then gh issue edit …` a `gh` command. `for`, `case`, `[[`, `coproc` and
  zsh's `repeat` and `noglob` are not skipped. A command that is only `fi`,
  `done` or `}` is no command; `done sh` is still `sh`. A backslash-newline
  outside single quotes is removed first, as both shells do, so a `\` at a
  line's end makes no word, and `<<\`, a newline, then `EOF` is an unquoted
  heredoc whose body is checked.
- **What names `gh`.** `gh` not followed by a letter, digit, `_` or `-`:
  `make gh-pages` does not name it, and `sh -c '${GH:-gh} …'` does.
- **Data commands.** Text naming `gh` counts as data only in a command from
  `DATA_COMMANDS` (`echo`, `cat`, `grep`, `git`, `python3` and a few more).
  Any other command that names `gh` blocks, since it may run the text it is
  given: `sh -c`, `eval`, `trap`, `env -S`, `ssh`, `xargs`. `printf`, `test`
  and `[` are not on the list (Adam, 2026-10-05): bash 4+ evaluates an array
  subscript given to `printf -v` or `test -v`, command substitution included,
  so `printf -v 'a[$(gh …)]' x` runs `gh`.
- **`gh` commands.** A `gh` word anywhere but first (`env gh …`) or after an
  assignment blocks. Whether a `gh` command is a post is read from its words
  after quote removal, so `gh p''r comment` in a longer command is read like
  `gh pr comment`. A subcommand that sends no text (`NO_TEXT_VERBS`: `list`,
  `view`, `checks` and the like) is no post, so `gh pr list --search
  'review-requested:@me'` passes; `merge` and any verb not on that list are
  read as before.
- **Pipes and input.** A pipe or an input redirection anywhere (`|`, `<`, a
  heredoc, `<<<`) requires every command to be from `DATA_COMMANDS`, `gh`
  included, so `bash <<'EOF'` and `echo … |` a shell are blocked. Which
  command reads the stdin is not worked out: the second bug-hunter pass
  found that tracking it per command missed pipes across line breaks and
  into subshells.

The rule that separates the two: an evasion *runs* `gh` with a body the hook
cannot read; text that only contains `gh` runs nothing.

**`--title` is not prose here.** Titles were never checked (`--title` is a
plain value flag in `LONG_FLAGS`), and a footer cannot go on one line. So
`gh pr edit 3 --title x` in a longer command passes, as it already did alone.

**Rejected.**
- *Python's `shlex`.* It knows no heredocs, no `$(…)` and no comments in
  bash's sense, so it reads a heredoc body as code and `#` mid-word wrongly.
  The reader here is small and refuses everything else.
- *Reading bodies in longer commands.* An earlier `cd` or `printf > body.md`
  changes which file `--body-file` names, and a pipe can feed `-F -`.
- *Matching text with a looser pattern.* Text cannot tell a quoted mention
  from a run.
- *A list of commands that run text as code* (`bash`, `eval`, `ssh` …). The
  first bug-hunter pass found `trap` and `env -S` missing from one; such a list
  is never complete. A closed list of data commands fails toward blocking.

**Where it stops applying.** A script handed to another interpreter
(`python3 - <<'EOF'`, `node -e`) can run `gh` itself; the hook does not read
it, just as it does not read a script file. Text the shell evaluates a second
time is a disguise like `$GH`, out of scope: a variable holding `$(gh …)` read
by `(( ))`, `let` or zsh's `${(e)…}`, a zsh glob qualifier, `{gh,}`, `GH` on
a case-insensitive disk, git options that run a command (`-c alias.x='!gh …'`,
`rebase -x`, `submodule foreach`, `bisect run`) and a zsh coprocess fed
through `>&p`. So is a post wrapped in `sh -c` inside zsh's
`{ … } always { … }`, which the hook reads as one command (the third
bug-hunter pass, 2026-10-05). A command joins `DATA_COMMANDS` only if it
runs neither its arguments nor its stdin, short of such a disguise. If `gh` gains a way to read a body from stdin without `-F -`,
revisit this.

---

## Docs are exempt only where vendored

**Decision (Adam, 2026-09-26).** A doc under `node_modules/` or `vendor/` is not
prose; a doc anywhere else is, including under `build/`, `out/`, `target/`,
`dist/` and `generated/`. Code comments still skip the scanner's whole list of
build and vendored directories. See also *Which files are docs*.

**Why.** Those names are also where people keep authored docs
(`docs/build/README.md`), and skipping them left that prose unsigned.

---

## Known gaps, recorded rather than fixed

Each is left on purpose for now; its *Fix:* says what would close it.

- **`core.commentString` is not read.** Only `core.commentChar` is, so on git
  2.45+ a message line starting with a configured comment string is not
  refused, and `commit.cleanup=strip` may delete it after the check (a
  mismatch, not a hidden edit). *Fix:* read `core.commentString` too.
- **`gh api` and `gh pr merge --body` are not checked.** They fall outside the
  decided verb list, so text posted through them has no footer check. *Fix:*
  add them to the list, with `gh api`'s `-f body=` and `--input` read as body
  sources.
- **Some zsh options change what gh receives.** With `setopt extendedglob`, an
  unquoted `sig#.md` or `a^b.md` is a glob; with `magicequalsubst`,
  `--body-file==gh` expands. The hook reads the literal name. Claude Code's
  Bash tool inherits the user's zsh options, but neither is set on the
  machines checked. *Fix:* take `#` and `^` out of the unquoted characters the
  hook accepts, and refuse an unquoted `=` after the first character.
- **Two `prose check` runs at once in one checkout fail on git's index
  lock** (Adam, 2026-10-01). `git write-tree` takes the lock even with
  `GIT_OPTIONAL_LOCKS=0`. Not fixed: each worktree, and each of Igor's clones,
  has its own index. *Fix:* compute the tree from a temporary copy of the
  index (`GIT_INDEX_FILE`), which gives the same hash and takes no lock
  (tested).
- **Only an MCP server named exactly `github` is checked.** A server registered
  as `GitHub` or `github-mcp` is not matched. *Fix:* match the server name
  case-insensitively and by substring, as the Cursor path does.
- **Config given only to `git commit` is not seen by the check.** `prose check`
  reads the repository's config when it runs; a `git -c trailer.separators=…`
  or `GIT_CONFIG_*` set only for the commit can make git rewrite the message,
  giving an honest mismatch. It fails closed. *Fix:* none short of making the
  commit itself; the commit script that composes trailers could pin these.
- **`commit.cleanup=verbatim` with a leading blank line.** git then finds no
  title and may read the first paragraph as trailers and rewrite it, while the
  signature treats it as the title; an honest commit fails verify. It fails
  closed. *Fix:* refuse a leading blank line when `commit.cleanup` is verbatim.
- **`git interpret-trailers` without `--no-divider` puts trailers above a
  `---` line.** A message holding such a line, committed through it, then
  fails verify as a mismatch or a missing trailer; it fails closed. `git
  commit --trailer`, `-s` and the commit script pass `--no-divider`. *Fix:*
  refuse a `---` line in the message, if that route is ever needed.
- **A disguised `gh` passes.** `g''h` or `$GH` does not match the post pattern.
  The hook stops accidents, not an agent set on getting around it. *Fix:* none
  planned; permission rules that deny the raw tools are the strict option.

---

## Cursor's posting hook is wired as a best guess

**Decision (Adam, 2026-09-26).** The posting hook is wired for Cursor now, on
`beforeShellExecution` and `beforeMCPExecution`, with no matcher, and the
README tells Cursor users it is unverified.

**Why.** Cursor's payloads and its `permission` answer are documented, and the
script reads them; what is not verified is how Cursor runs it. Waiting would
leave Cursor users with no check at all.

**What is unverified.** What a `beforeMCPExecution` matcher would match (so
the script filters on `mcp_server_name` itself), whether `manage-skills` accepts
two entries sharing one script, and the run against a real Cursor. Cursor blocks
an action when a permission hook prints no valid JSON, so every allowing path
in `check-post.sh` prints `{"permission":"allow"}`; a hook that crashes fails
open.

---

## The trailer fold follows git's default rule

**Decision (Adam, 2026-09-26).** The message hash folds an empty-valued `Key:`
line into the indented line after it only when git would read the whole
paragraph as a trailer block, as git does when it adds trailers there.

**The gap.** git also counts keys a user configures (`trailer.<x>.key`) the way
it counts `Signed-off-by`. With such a key in a mixed paragraph, git folds a
paragraph prose leaves alone, and an honest commit is reported as a mismatch.

**Why it is kept.** The two choices differ only at the edges. Folding every
paragraph would need no config, but an edit to only the indentation of lines
that start with whitespace would no longer break the message hash. The current
rule can mismatch only when a commit is verified under trailer config that
differs from where it was checked: `prose check` refuses to sign in a
repository with any `trailer.*` config except the default separator
(`refuse_configured_trailers`). Neither case is common, and the mismatch is
loud, never silent. Folding every paragraph would also save little code, since
the trailer block still has to be found to search it for added trailers.

**What would fix it.** Read the repository's `trailer.*.key` config (`git
config --get-regexp '^trailer\..*\.key$'`) and count those keys as git does.

---

## How the message is normalised for the trailer

**Decision (confirmed by Adam, 2026-09-28, including the refusal of `#`
lines: the agent rewords such a line).** The message half hashes the message
with LF line endings, trailing blanks off each line, runs of blank lines
collapsed and the ends trimmed. Every line of the text `prose check` read is
signed, `Note:` and URL lines included; which lines of the stored message are
compared is in *The signed message is found by searching from its end*. When
git reads the message's last paragraph as a trailer block, its
trailer-shaped lines are put in git's `token: value` form first, because git
rewrites them that way when it adds trailers there. `prose check` refuses a
line starting with `#`, or with the repository's `core.commentChar`: git's `strip`
cleanup deletes it, and git places trailers before trailing `#` lines, so it
cannot be signed reliably. A git hook that edits the message after the check
(`prepare-commit-msg`) breaks the signature; the mismatch report says so.

---

## Which files are docs

**Decision (confirmed by Adam, 2026-09-28).** Docs are `.md`, `.mdx`,
`.markdown`, `.rst`, `.adoc`, `.asciidoc`, and files named `README`,
`CHANGELOG` or `CONTRIBUTING` with any extension. Specs are anything under an
`openspec/` directory. Which directories exempt a doc: see *Docs are exempt
only where vendored*.

**Rejected: `.txt` as a doc type.** It would take in files such as
`requirements.txt` and `LICENSE.txt`.

---

## Comments in more languages

**Decision (confirmed by Adam, 2026-09-28).** The scanner kept its lexers for
Python and the C family, and gained own-line `#` comments for shell, YAML,
TOML, Ruby, Perl, R, PowerShell, `Dockerfile` and `Makefile`: wider than
`sharper-comments` scanned. A `#` after code is not read, since it may be in a
string or be `$#`. Of its advisory checks, the history-language patterns are
back as `prose check` flags (see *The signature signs the snapshot*); the
block-length check went with `sharper-comments`.

**Why.** More languages only widen what the pass lists and flags. Since the
snapshot signature, comment detection does not affect the trailer.

**Regex literals (2026-09-30).** In JavaScript and TypeScript, a `/` opens a
regex literal only after one of `( , = : [ ! & | ? { ;`, `=>` or a keyword
such as `return`, and only if the regex closes on the same line; a `!` right
after an operand is a non-null assertion, so `x! / 2` divides. A `//` inside
such a regex is not listed as a comment. A regex anywhere else, such as at the
start of a line, has its `//` listed as one: a false item in the listing,
which changes no trailer.

---

## The posting hook's reach

**Decision (confirmed by Adam, 2026-09-28, including a footer on each review
comment: inline comments are the agent text reviewers read most).**
- A body-like field is a string under a key named `body` or `comment`, at any
  depth, so each comment in a review (`comments[0].body`) needs its own footer.
- The Claude matcher is `^(Bash|mcp__github__.*|mcp__plugin_.*_github__.*)$`,
  anchored because Claude Code tests matchers as unanchored regexes, and
  covering a plugin-bundled GitHub server.
- `gh pr review` and `gh issue edit` are checked along with the listed
  commands, since they post a body too.
- How a `gh` command is read: see *The posting hook reads an allow-list*. A
  `gh` command with no body flag passes. A payload that is not JSON passes:
  the hook fails open, like the commit hook.
- It blocks with exit 2 and the reason on stderr, Claude Code's documented
  PreToolUse contract.

---

## `verify-commit` reports `missing` only when git sees no `Prose` key

**Decision (Adam, 2026-09-29).** A blank value (empty, spaces, a no-break
space) is `unrecognised`.

**Why.** `missing` says the pass never ran. A commit whose `Prose:` line is
blank carries a broken trailer, and `verify-commit` says so. The hook reads
the value first and reports an empty or all-ASCII-space one as no trailer, so
it relies on this only for a value it passes on, such as a no-break space.

---

## Command details

**Decision (confirmed by Adam, 2026-09-28).** Each detail implements a decision
already made:
- `prose check --amend` lists the change against the commit's parent instead
  of HEAD, for an amend; the trailer is the same either way.
- The listing's diff finds renames (`-M`) whatever the config, so a pure rename
  lists nothing, per the scope rule.
- `prose check -F <file|->`, the first call, prints the list, any flags, the
  rules and a pass token; with `--pass`, it prints only the result block
  holding the trailer (see *`prose check` ends with the shared result block*).
  How `rules.md` is printed: see *The rules live only in rules.md*.
- `verify-commit` exits 0 valid, 1 invalid, 3 when it could not check, matching
  the library's callback contract. Its reason starts with the kind,
  `missing`, `unrecognised`, `mismatch` or `tree`, so the hook's report says
  which half broke.

---

## Considered: git's own commands for message parsing

**Decision (Adam, 2026-09-29): keep prose's own message parsing.** It is exact
on every message it accepts, and a git-native version would trade its refusals
for new failure modes to save about 8% of `prose.py`.

The figures below predate *What removing the Action removed*, which cut
`prose.py` from 1,328 lines to 1,246. None of that code parsed messages, so
the estimate of what git's commands would replace still holds.

**What was tried.** A prototype (git 2.54, against this branch at `dbe41c8`)
committed messages for real in scratch repositories, through
`commit-with-trailers.sh` and through `git commit -F` with the same pinned
settings, and compared git's stored message with each prediction: 61 shaped
cases from the tests and edge cases, 2,500 fuzzed messages, 18 trailer and
comment configurations, and 120 cherry-picks.

- **git's commands predict what git stores.** `git stripspace`, then
  `git interpret-trailers --no-divider --trailer …`, then `stripspace` again,
  matched the stored message byte for byte in 3,061 of 3,062 default-config
  commits. The miss was a Unicode noncharacter: git re-encodes such a message
  as Latin-1 when it stores it.
- **prose's own parsing is exact on everything it accepts:** no mismatch in
  2,464 accepted messages. All its mismatches were in messages it refuses (a
  bare CR, `#` lines, the noncharacter), except `core.commentString`, already
  a known gap.
- **A git-native design** (the pipeline at check time; stripping the added
  trailers from the stored message at verify) round-tripped every default-config
  message, closed the `trailer.<x>.key` and `core.commentString` gaps, and
  worked under other cleanup modes. It failed under a `trailer.*.command` whose
  output changes between runs, `trailer.bug-hunter.ifexists=replace`,
  `core.commentChar=auto` with strip cleanup, and a `cherry-pick -x` of a
  message ending in a `#` paragraph.

**Why it is not adopted.**
- The gain is correctness under unusual configuration, which `prose check`
  already refuses loudly rather than getting wrong.
- It would remove about 80–100 of 1,276 lines, and tests would barely shrink:
  they would need real repositories.
- It adds three `git` calls (about 10 ms) twice per commit, and depends on the
  order of steps inside `git commit`, verified on one git version only.
- It would still need most refusals: noncharacters, `#` lines under
  `commentChar=auto`, and `.command` settings.

**What would change it.** People hitting the refusals in practice (configured
trailer keys, `#` lines, `core.commentString`). Then the partial replacement
is the starting point: `git stripspace` for `_clean`, and one
`git interpret-trailers` call in place of the trailer-block, folding and
`token: value` rules at check time. `refuse_bare_cr` would go, and
`refuse_configured_trailers` would narrow to `.command`/`.cmd` and per-key
`ifexists`/`ifmissing` on added keys other than `Prose`.

---

## Open

- More rules.

