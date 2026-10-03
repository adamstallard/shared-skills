# bug-hunter — reference

Detail the agent reads on demand. [SKILL.md](SKILL.md) is the entry point and
carries the workflow; this file carries the report format and the worked
examples behind it.

## The report

Print one every run, including when triage skipped the commit — it is how anyone
can tell this ran and what it did.

The headline is one line, so it can be read at a glance and the rest skimmed.
Keep the labels in the left column aligned — the shape is what makes it
scannable when there are a dozen findings.

**Root causes go first, above the findings.** When several findings share one
cause, that cause is the only thing worth a decision, and burying it under a
dozen symptoms hides it. The user reads the top of the report and says "do the
first one" — so put what they would act on where they will see it.

```
🔍 bug-hunter · 2 iterations · 6 fixed · 2 refuted · 4 reported · 1 to decide

  triage    REVIEW — new parsing logic in the commit detector
  scope     2 files  +155/-24
  baseline  test_hook.py 19 ✓  ·  test_skills.py 20 ✓

━━ root causes ━━━━━━━━━━━━━━━━━━━━━━━━━━━  1 cause · awaiting the user's decision

  ① the detector parses shell with a regular expression
     affects     4 findings, 2 of them created by this run's own fixes
     recommend   read git state instead of the command text
     odds        high — exact where the current approach guesses

     1  fix it now      — apply it, then run the full loop over the result
     2  write it down   — record it as an open question, change nothing
     3  skip            — no fix, no note

── iteration 1 ─────────────  12 found · 8 proven · 6 survived · 6 fixed

  ✓ FIXED     a commit on a later line was allowed through
              where   scripts/hook.sh:78
              test    test_hook.py::test_a_commit_on_a_later_line
              fix     normalise every separator once, instead of growing
                      the pattern one separator at a time
  ✓ FIXED     the marker counted anywhere in the payload
              where   scripts/hook.sh:96
              test    test_hook.py::test_the_marker_inside_a_message
              fix     markers only count at a real command position
              …4 more fixed
  ✗ REFUTED   blocks `git commit --dry-run`
              why     the cheap fix reopens `--dry-run && git commit`
              note    test deleted
  ✗ REFUTED   over-blocks a quoted mention of a commit
              why     visible and recoverable; unfixable without a parser
  ○ UNPROVEN  pagination overrun in the fallback path
              why     the test did not fail — already handled
              note    test deleted

── iteration 2 ──────────────────────────────────────  0 proven bugs · clean

── under ① · not fixed ──────────────────────────────────────  4 findings

  ● HIGH      GIT_AUTHOR_NAME="Jane Doe" git commit slips through
              why not quoted value with a space; fixing it here means
                      teaching the regex shell quoting
  ● HIGH      git -C ${REPO} commit slips through
  ● MEDIUM    a backslash line continuation splits git from commit
  ● MEDIUM    the option-token bound is finite, so seven -c pairs escape

── result ───────────────────────────────────────────────────────────────────

  suite     test_hook.py 30 ✓ (was 19)  ·  test_skills.py 20 ✓ (was 20)
  commit    c667b6d  Detect commits properly in the hook

── to whoever holds this report ─────────────────────────────  1 open decision

  ① is the user's to make, and printing it here has not asked them. If this
  reached an agent rather than the user, that agent asks it in its next reply,
  before anything else — through its picker, one question per cause, or the
  root-causes block above verbatim. A summary is not the question.
```

Rules for the report:

- **Root causes go at the top, above the findings**, numbered, each with what
  it affects, the recommendation, the odds, and how to ask for it. The findings
  below are grouped under the cause they belong to, so the list reads as
  evidence for a decision instead of a pile of complaints.
- **When the run aborted, the root causes are the report.** Every unresolved
  thing is an entry with the same three choices, and each says which kind of
  cause it is — **scope**, when the cause sits outside the change under review,
  or **budget**, when the run ended before a pass could read its own last fixes.
  See [When the run aborts](#when-the-run-aborts).
- **The headline counts are required, every run** — iterations, fixed, refuted,
  reported. They are how anyone tells this ran and what it did. **Whenever
  anything is open, the headline also counts it** — `· 2 to decide` — so the
  first line of the report cannot be honestly summarised as "it aborted".
- **A text-form report with an open decision ends with the hand-off footer**
  — see [The hand-off footer](#the-hand-off-footer). It is dropped only when
  the same reply put every open decision through the user's picker, or when
  the brief said "caller commits" and the result block carries them (see
  [The caller-commits result](#the-caller-commits-result)).
- **`recommend` only when the odds are good.** Say the odds. If there is no
  change worth making, write `recommend none — <why>` and stop; an invented
  recommendation is worse than none. A `budget` cause is the third case and
  carries neither line — see [When the run aborts](#when-the-run-aborts).
- **Every finding that is not fixed needs a `why not`.** "Reported" without a
  reason is a shrug.
- Say `clean` for an iteration that found nothing, rather than omitting it. A
  missing iteration reads like it was skipped.
- On `SKIP` at triage, print **one line** and nothing else —
  `🔍 bug-hunter · skipped at triage — <reason>`. It is worth printing rather
  than staying silent: knowing the check ran and why it stopped is useful, and
  one line costs nothing to skim. **One line is the whole *report*, not the
  whole *job*** — the same reason goes on the commit, as
  `commit-with-trailer.sh`'s third argument.

### The hand-off footer

A report whose decisions did not go through a picker the user answered ends
with one more block, addressed to whoever is holding it:

```
── to whoever holds this report ─────────────────────────────  2 open decisions

  ① and ② are the user's to make, and printing them here has not asked them.
  If this reached an agent rather than the user, that agent asks them in its
  next reply, before anything else — through its picker, one question per
  cause, or the root-causes block above verbatim. A summary is not the
  question.
```

It exists because a report travels. Run inside an agent that reports to another
agent, everything above it is correct and reaches the wrong reader — the
questions land in a coordinator's context, where a summary feels like reporting
and "the run aborted" feels like the news. The footer is the one text that is
in front of that coordinator at the moment it decides what to do with the
report, which is why the instruction rides with the report instead of living
only in `SKILL.md`, read long before. It says nothing about *how* to ask — the
holder's host, picker and cwd are its own — only that the asking is not done.

Drop it when the same reply put every open decision through the user's picker:
then the picker is the hand-off, and the footer would be telling the user to ask
themselves. Keep it on every text-form report that carries an open decision,
including a sub-agent's final message — and there, keep the whole report too.
The one other exception is a run under "caller commits", whose result block
lists the open decisions in its place.
The footer on a one-line summary is a footer on nothing.

## The caller-commits result

The block that ends a run whose brief said "caller commits" (SKILL.md,
[When the caller commits](SKILL.md#when-the-caller-commits)). It comes after
the report, once, as the last thing printed.

**`scripts/caller-result.sh` prints it; nothing in it is typed.** The wrapper
mints the tree line, then hands the trailer lines and decisions to the shared
library's
[`result-block.sh`](../../lib/commit-trailer/result-block.sh), which is the
format's one definition; prose's `prose check` is to print the same block
through it. What follows describes that script's output.

```
=== bug-hunter result ===
Bug-hunter: <value>
Bug-hunter-Tree: <tree hash>
=== bug-hunter open decisions: <N> ===
<one line per open decision>
=== end bug-hunter ===
```

**The marker lines are fixed text.** A caller finds the block by
`=== bug-hunter result ===` and reads to `=== end bug-hunter ===`; nothing else
in the reply uses those lines.

**The trailer lines are ready to pass through.** `Bug-hunter:` carries the value
the commit script's third argument would have carried — `1 iteration, 1 bug
fixed`, `2 iterations, 0 bugs found`, `3 iterations, aborted — see report`,
`skipped at triage (<reason>)`. `Bug-hunter-Tree:` is minted by the wrapper,
through `scripts/mint-trailer.sh`, over what is staged when it runs. A skip
has no tree line.

**Each open decision is one line**: its number, added by the script, then the
cause in a few words and its choices — `1 fix it now · 2 write it down · 3 skip`, or `1 new run · 2
write it down · 3 skip` for a cause of kind *budget*. The full entry, with what
it affects and the odds, is in the report's root-causes block above. With
nothing open the count is `0` and the end marker follows directly.

A clean run, and a skip:

```
=== bug-hunter result ===
Bug-hunter: 2 iterations, 3 bugs fixed
Bug-hunter-Tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904
=== bug-hunter open decisions: 0 ===
=== end bug-hunter ===

=== bug-hunter result ===
Bug-hunter: skipped at triage (docs only, no executable code)
=== bug-hunter open decisions: 0 ===
=== end bug-hunter ===
```

**What the caller owes in return.**
- **Commit exactly the minted tree.** The tree of the commit it creates must
  equal the `Bug-hunter-Tree` value. Anything added, reformatted or dropped
  after the mint makes the binding false; a caller that has to change the
  tree runs the skill again over the new state.
- **Put both lines in the commit's trailer block**, as trailers, unchanged —
  `git commit --trailer` locally, or the last paragraph of the message it
  sends to an API.
- **Decide each open decision or hand it on.** The block is the hand-off; no
  one has been asked yet. Choice 1 is a new invocation of the skill over the
  new state, not a continuation. Choice 2's record, written after the mint,
  goes in a commit of its own — it is a separate change (SKILL.md, *The
  commit waits for the run*); folded into this one it makes the binding
  false.

## What triage skips

Triage classifies the change by what the diff touches. The commit message,
and any prefix on its subject, plays no part — this skill imposes no commit
convention, so write the subject however the repository does.

| The diff shows | Skipped? |
|---|---|
| Formatting only — whitespace, import sorting, comments | yes |
| A pure rename or file move, no behavior change | yes |
| Only docs, tests, specs, lockfiles, generated or vendored files | yes |
| git's own revert or merge | yes |
| Anything else | **reviewed** |

**Work in progress is the one exception the diff can't show.** A checkpoint is
skipped only when the user asked for one in the conversation — "save a
checkpoint", "commit this as work in progress", or the same thing in other
words. Wording in the commit subject does not count.

- **A checkpoint defers the check; it never exempts the code.** The behavior
  change in it still has to pass this skill when it lands in a commit that is
  not a checkpoint.
- If you are mixing a formatting sweep with a real change, split the commit.
  A mixed commit gets reviewed in full, and the formatting noise makes the
  review worse.

## Trailer placement

**Don't place it by hand — `commit-with-trailer.sh` hands every trailer to git
as `--trailer`, and git places them.** Each lands in the message's trailer block
whatever the body looks like, and the `Co-Authored-By` given as the fourth
argument lands in the same block, so the two cannot drift into separate
paragraphs:

```bash
BH=~/.agents/skills/bug-hunter/scripts/commit-with-trailer.sh
[ -x "$BH" ] || BH=~/.claude/skills/bug-hunter/scripts/commit-with-trailer.sh
"$BH" -F msg.txt "1 iteration, 1 bug fixed" "Someone <someone@example.com>"
```

What that runs is `git commit -m <subject> -m <body> --trailer "Bug-hunter: …"`,
plus `--trailer "$(mint-trailer.sh)"` for any non-skip value and
`--trailer "Co-Authored-By: …"` when given. `--trailer` on its own is still the
tool for the one thing the script does not do — repairing a commit that already
landed, while it is still local:

```bash
git commit --amend --no-edit --trailer "Bug-hunter: skipped at triage (docs only)"
```

That is the whole class of placement mistakes gone — blank lines, wrapping, and
ordering against other trailers all become git's problem instead of yours, and a
long value stays on one line and still parses. The rules below are what you are
up against if you hand-write the block anyway — and why the script exists
([DECISIONS.md](DECISIONS.md#the-commit-is-assembled-by-a-script-not-by-hand)).

**Commit and push as separate steps.** The companion hook runs after a tool call
finishes, so `git commit && git push` in a single call means the report arrives
only once the commit is published and the cheap `--amend` fix is gone — undoing
it then means rewriting published history, which needs the user's say-so. Commit,
let the hook check it, then push.

**It has to be a real git trailer**, which means it sits in the message's *last*
paragraph, with nothing but other trailers beside it. Anything that lands after
it in a paragraph of its own — a `Co-Authored-By` a blank line below, a closing
sentence — pushes it out of the trailer block, and so does an ordinary prose
line next to it inside that paragraph. Then `%(trailers:key=Bug-hunter)` comes
back empty and the commit counts as unchecked. The `Co-Authored-By` case is the
one that actually bites, because the footer gets appended last:

```
Handle empty input in the parser

Body text here.

Bug-hunter: 1 iteration, 1 bug fixed          ← same paragraph
Co-Authored-By: Someone <someone@example.com> ← no blank line between them
```

Another way to lose it is **wrapping the line without indenting**. A trailer
may span lines, but every continuation must start with whitespace — otherwise the
second line is not a trailer, the block stops being a trailer block, and the
whole thing is invisible to git:

| shape | git sees a trailer? |
|---|---|
| `Bug-hunter: skipped at triage (docs only)` | ✅ |
| wrapped, continuation **not** indented | ❌ |
| wrapped, continuation **indented two spaces** | ✅ |
| wrapped unindented, followed by `Co-Authored-By:` | ❌ |
| a **blank line**, then `Co-Authored-By:` below it | ❌ |
| a prose line beside it in the same paragraph | ❌ |

So a long reason is fine either way — keep it on one line, or indent the
continuation:

```
Bug-hunter: skipped at triage (docs only, no
  executable code changed)
Co-Authored-By: Someone <someone@example.com>
```

Check it rather than assuming: `git log -1 --format='%(trailers:key=Bug-hunter)'`
should print your line back.

## Minting the tree binding

**Whenever the `Bug-hunter:` trailer is not a skip note** — `1 bug fixed`,
`0 bugs found`, and `aborted ...` all need it, because each reports that the
loop ran over this tree; only `skipped ...` does not, because triage stopped
before any loop ran. `commit-with-trailer.sh` makes that call from its third
argument — anything not starting with `skipped` is minted — and finds
`mint-trailer.sh` next to itself, so the run is: stage everything, then one
command:

```bash
git add fix.py test_fix.py
BH=~/.agents/skills/bug-hunter/scripts/commit-with-trailer.sh
[ -x "$BH" ] || BH=~/.claude/skills/bug-hunter/scripts/commit-with-trailer.sh
"$BH" -F msg.txt "1 iteration, 1 bug fixed"
```

Run by hand — to understand it, or to re-mint after a repository's own hooks
have rewritten the index (see below), never as the commit path — the script is
the same two-target lookup and its one line goes in as a second `--trailer`:

```bash
MINT=~/.agents/skills/bug-hunter/scripts/mint-trailer.sh
[ -x "$MINT" ] || MINT=~/.claude/skills/bug-hunter/scripts/mint-trailer.sh
git commit -m "Handle empty input in the parser" -m "Body text here." \
  --trailer "Bug-hunter: 1 iteration, 1 bug fixed" --trailer "$("$MINT")"
```

Either way the path is absolute because `scripts/` resolves relative to this
skill's own directory, not to whatever project you are sitting in, and both
install targets (`~/.agents/skills` and `~/.claude/skills`) are tried because a
real install may populate only one. If neither exists, the skill was loaded from
somewhere unusual — search for `bug-hunter/scripts/` under both directories
before giving up.

`git write-tree` runs with no `-C`, so it reads the *project's* index from
wherever you already are — only the path to the script needs to be absolute,
never the git command it runs.

The script prints one line — `Bug-hunter-Tree: <hash>` — where `<hash>` is
`git write-tree` over whatever is staged at the moment it runs. It also
writes that tree object into the repository's object store, since that is
what `git write-tree` does — harmless (unreferenced, cleaned up by the next
`git gc`), but worth knowing: it is the one thing in this hook family that
is not a pure read of git state. The companion hook, on any plain commit
whose `Bug-hunter:` trailer is not a skip note, recomputes that same hash
from the tree that actually landed and compares. A match is silent. A
mismatch, or no `Bug-hunter-Tree` trailer at all, is reported — distinctly
from a missing `Bug-hunter:` trailer, because it is a different problem: the
trailer is real, it parses, and it is not backed by anything.

**Why this catches what string-matching cannot.** A `Bug-hunter:` trailer is
free text — an agent that has read this file once can produce
`1 iteration, 1 bug fixed` from memory, with no run behind it, and it looks
identical to a real one. A tree hash is not something to recall; producing
the *right* one for a commit that does not exist yet means actually running
`git write-tree` against the actual staged state at that moment. That is
what the script does, and it is the cheapest thing that could not have been
typed instead.

**What it does not attest to.** Not "before the commit" — only that the
value equals the tree that landed, full stop. Once a commit exists,
`git rev-parse HEAD^{tree}` prints that same value with no staging, no
run, and no engagement with this skill at all, so the hook cannot tell a
value minted before the commit from one read off after it. What the binding
actually rules out is *pure recollection* — typing the shape this file
documents with no command run behind it at all, which is the incident this
mechanism exists for — not a later, deliberate reconstruction of the correct
hash from the commit itself. It does not prove Step 1's triage, Step 3's
find pass, or Step 5's refute pass happened, and it does not verify the
counts in the `Bug-hunter:` trailer are honest — an agent that runs the mint
script once and writes whatever counts it likes still passes. See
[the shared library's DECISIONS.md](../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent)
for why a stronger, delegation-verifying check was considered and set aside,
and for the reasoning behind scoping this to plain commits only — never
cherry-picks or rebase replays, which legitimately carry an older trailer
(and its now-stale binding) forward onto different content, tree unchanged,
even across a later amend of the message alone.

**Ordering is what breaks this.** Stage everything the commit will contain,
*then* mint, *then* commit, with nothing staged or unstaged in between, no
pathspec on the `commit` itself, and no `-a` — the binding is for the whole
index, and a partial commit or a `-a` that catches something unstaged can
land a different tree than the one just minted. Any `git add` after the
mint invalidates the binding it produced, and the hook cannot tell
"invalidated by later staging" apart from "never minted at all" — both
report as a mismatch. If more needs staging after minting, mint again.

A repository whose own pre-commit hooks reformat or re-stage files breaks a
hand-run mint: the hook runs *during* `commit`, after the mint already read
the index. `scripts/commit-with-trailer.sh` runs the pre-commit hook itself
before minting, so its binding is of what the hook left staged; if the hook
fails, it refuses with the hook's output, and you review, stage and run it
again. Committing by hand, mint again once the commit exists and its hooks
have already run, then repair the trailer (see the README's troubleshooting
entry for the exact command).

## Asking about a recommendation

One question per recommendation, in severity order. Use the host's interactive
picker when it has one; this is the fallback shape.

```
① the cursor is a sha, but "what changed since last time" is a position
   affects 4 findings, including the critical one
   recommend: use the log's own cursor instead of matching a sha  ·  odds high

   1  fix it now        — apply it, then run the full loop over the result
   2  write it down     — record it as an open question, change nothing
   3  skip              — no fix, no note

② `^commit` is not the set of actions that author code
   ...
```

When there is no fix worth trying, option 1 is omitted entirely and the prompt
says so — two choices, not three padded to look like a plan.

An agent running this for another agent has no picker that reaches the user. It
prints this shape, in full, with [the hand-off footer](#the-hand-off-footer)
under it, and the agent that spawned it does the asking — through its own
picker, in its next reply.

## Where a record goes

A run writes two kinds of thing down. Both are knowledge about the code under
review, so neither goes in this skill's own files — those are about the skill.
The homes for each are listed in `SKILL.md` at Step 9 — the codebase's stated
convention, then a home it already has, a new file only when there is none.
What follows is why the two lists differ, and the shape of each entry.

**A rejected approach is a decision**, read by someone about to make the
opposite one — which is why it can live at the site, and an open question
cannot: nobody is standing anywhere in particular when a gap comes due. The
entry is the decision, why, what was tried and rejected, and where the lesson
stops applying — the shape this skill's own [DECISIONS.md](DECISIONS.md) uses
throughout. At a site it compresses to a sentence in the codebase's own comment
idiom: present tense, the alternative and what breaks when it is taken, no
narration of what changed.

```ts
// Outside the try: a command that failed to run is already its own message, and
// running it through the diagnosis below would relabel it as something it is not.
```

The reader is the person about to move it inside the try. The comment names
what that would do — not that it was once inside and got moved out.

**An accepted gap is an open question**, read by whoever picks it up later, so
it goes where the codebase lists work it knows about and has not done. The
entry is the cause, which findings it produced, the recommendation, the odds,
and the date. It is committed with the rest of the change; a recommendation
that lives only in a terminal report is choice 3 with extra steps.

## When the run aborts

Three iterations that each found something. The run ends here — **there is no
fourth iteration and no offer of one** (SKILL.md Step 8). Everything left
unresolved becomes a numbered root cause, and each one is asked separately
through the picker, in severity order:

```
━━ root causes ━━━━━━━━━━━━━━━━━  2 causes · awaiting the user's decision

  ① iteration 3's fixes never got a finder pass
     kind        budget — inside the change under review, unread
     affects     reducer.py:88-140, tests/test_reducer.py (3 fixes)
     odds        unknown — nothing has looked at this code

     1  new run         — iteration 1, scoped to these fixes
     2  write it down   — record it as a known gap, change nothing
     3  skip            — no pass, no note

  ② refund state is rebuilt from the event log on every read
     kind        scope — the cause sits outside the change under review
     affects     4 findings, 2 of them created by this run's own fixes
     recommend   store the derived total, one writer
     odds        medium — large, and it touches three call sites

     1  fix it now      — apply it, then run the full loop over the result
     2  write it down   — record it as an open question, change nothing
     3  skip            — no fix, no note

── to whoever holds this report ─────────────────────────────  2 open decisions

  ① and ② are the user's to make, and printing them here has not asked them.
  If this reached an agent rather than the user, that agent asks them in its
  next reply, before anything else — through its picker, one question per
  cause, or the root-causes block above verbatim. A summary is not the
  question.
```

An abort's headline reads `3 iterations · aborted · … · 2 to decide`, and the
footer earns its place most here: an abort is the ending most likely to be
relayed as a status line — *it aborted* — with the causes and their choices left
behind in whichever context received them.

**`kind` is only for an abort's causes**, where it is the one thing that tells
the user what they are weighing: with `budget`, whether to keep looking at code
inside the change; with `scope`, whether to spend a bigger change on something
outside it. A clean run's causes are all `scope` by construction, and it does
not carry the field.

**A `budget` cause carries no `recommend` line.** The only recommendation
available is "read this code", which is already option 1 — and it is not
`recommend none` either, since there plainly is work worth doing. `odds unknown`
stands in its place: nothing has read the code, so any confidence stated about it
is invented. That is also why option 1 there is a pass and not a patch.

**Option 1 is a new run at iteration 1, on either kind of cause** — never a
fourth iteration of the run that just ended, in the report, the reply, or the
trailer. An abort is report-only, so this run may not commit at all (see
[Committing](#committing)); whenever it does, its trailer says
`3 iterations, aborted — see report` and the new run mints its own.

## Steps 4–7 in detail

### Step 4 — Prove

For each candidate, write a regression test in the project's existing test
framework, in the place that project already puts tests, following its
conventions.

**No subagent for this.** Step 3's candidate already carries the concrete input,
the reachable caller, and the wrong outcome, so the test is a translation of
something fully specified — a freshly delegated agent would spend its first
tokens rebuilding context the orchestrating loop already holds. Write it and run
it inline; the only question that matters is whether it goes red for the
predicted reason, and that is answered by running it, not by who wrote it.

Run it against the **unfixed** code. It must fail, and **the failure must
match the predicted wrong outcome** — not an import error, a typo, a missing
fixture, or an unrelated exception.

**A compile error is not a red.** A test that references a constant, field or
method the *fix* will introduce fails to build, and it would fail identically
against correct code — that says nothing about the bug. Assert the observable
property instead, or introduce the symbol first and then drive the red against it.

| Result | Action |
|---|---|
| Fails as predicted | Proven. Keep the test, carry the bug to Step 5. |
| Passes | The code already handles it. Drop the candidate, **delete the test**. |
| Fails for an unrelated reason | Repair the test once and retry. Still not a clean red? Drop it and delete the test. |

Never leave a failing or discarded test in the tree.

If a candidate is real but no test can express it — concurrency, deployment
configuration, security posture, performance — do not force a fake test. Move
it to the reported-not-fixed list in Step 9.

### Step 5 — Refute

Delegate each proven bug to a **separate** subagent that has not seen the
finder's reasoning — **all of them at once**, since each judges one finding
against the code and nothing it decides is an input to another. Give it the code
and the failing test. Its job is to kill the finding:

- Is the trigger actually reachable in real use, or only from a test?
- Is it guarded upstream by a caller, a type, a schema, a validator?
- Is the behavior intentional and documented in a contract, spec, or comment?
- Does the test assert something the code never promised?

**The brief has to say which of that documentation predates the change.** The third
bullet is the one that goes wrong: a refuter cannot date a document, so it reads
every spec, design or task file it is handed as deliberated intent the code was
written to satisfy. When the implementer documented their own fix in the same
session — an OpenSpec `design.md` and `tasks.md` updated minutes ago, uncommitted
— that is not independent evidence of a decision, it is the change under review
restated in prose. A refuter given it has quoted the implementer's own fresh
sentence back and ruled a reproduced finding REFUTED as "a deliberate, documented
design choice … the code correctly implements what was specified." So name the two
separately: *this is the committed spec; this text is in flight, written alongside
the code.*

And the refuter checks provenance itself before treating any passage as a
contract:

```bash
git log -1 --format=%h -S "a distinctive phrase" -- path/to/design.md
git diff -- path/to/design.md     # is the passage an unstaged + line?
git blame -- path/to/design.md    # which commit put it there, and when
```

Empty output from the `-S` search means the sentence exists in no commit. Text
authored in the same session as the code cannot show the behavior was intended
before the behavior existed, so the "intentional" leg of that refutation is void
and the finding stands or falls on its other legs alone.

**A quoted passage only refutes the finding when it governs the same decision.**
The same refutation also cited a spec rule about what to write for a row that was
attempted, against a finding about whether to keep attempting further rows —
adjacent, same feature, different decision, and treated as dispositive. Before
accepting a quote, say which decision it governs and which decision the finding is
about. If they are not the same one it is context, not a refutation.

Only survivors get fixed. Refuted findings are dropped and **their tests
deleted**. Record the refutation in the report — a killed candidate is useful
information, not a failure.

One more question waits for the parallel pass to come back, because it needs the
survivors: ask a single **fresh** agent, about the set as a whole, **do any of
these fixes fight each other?** Fresh, not the resumed Step 6 finder — that
agent is about to author the fix plan this question is meant to check. Name every case of:

- **Fixing A reopens B.** The cheap fix for one finding creates a hole another
  finding is about. (Real example: excluding any command containing
  `--dry-run` un-blocks `git commit --dry-run && git commit -m x`.)
- **A's fix depends on B's.** They share a mechanism, so fixing one alone
  produces wrong behaviour. Those two are one fix, not two.
- **A and B pull in opposite directions.** Usually one wants stricter and the
  other wants looser. Say which direction is cheaper to be wrong in, and let
  that decide — do not split the difference and satisfy neither.

Carry that list into Step 6 and fix in an order that respects it. A conflict
found here costs a sentence; found after both fixes are written, it costs both.

### Step 6 — Fix

**Resume this iteration's Step 3 finder via `SendMessage` — do not spawn a
fresh fixer by default.** Nothing has mutated the source between Find and Fix:
Step 4 only added test files, Step 5 only read. The finder has already read
every changed file in full, traced each candidate's reachability, and run the
candidates — exactly the context a cold fixer would spend its first tokens
rebuilding. The message hands it what it does not have:

- **the surviving findings** — which of its candidates were proven red and not
  refuted, with the failing test for each;
- **the refuter verdicts** — what was refuted and why, so it does not re-fix a
  dropped finding;
- **the fix-conflict notes** from Step 5's cross-finding question, and the fix
  order they imply;
- the fix instructions below (prevention question, scope confinement).

**Fall back to a fresh `Agent` call — strongest available model — only when
that finder is no longer available**: the `SendMessage` errors or the agent
cannot be reached, its session has ended, or the finder belongs to an earlier
iteration than this Step 6 (each iteration's Step 3 spawns fresh, so each
Step 6 resumes only its *own* iteration's finder, never a previous one's). The
fresh fixer then gets the full brief: the files under review, the surviving
findings with their failing tests, the refuter verdicts, and the conflict
notes.

Before writing the fix, it must answer: **"Is there a better approach that
would have prevented bugs like this from ever happening?"** When more than one
approach works, prefer the one with simpler, easier-to-understand code, a
simpler architecture, and fewer moving parts. A fix that makes the bug
impossible to reintroduce beats a fix that handles the one case.

**Confine the fix to the change under review.** If the real cause sits outside
it — a design problem in existing code, a wrong abstraction, a missing layer —
do not fix it here and do not iterate on it. Report it (Step 9) with a
recommendation, and only recommend the larger change if it has a high chance
of success.

**Keep the prompt's prefix byte-stable across iterations**, here and at Step 3 —
these are the two strong-model delegations and a run repeats each up to three
times. Put the skill instructions and the file content under review first,
identical every iteration, and append the per-iteration specifics — the fix just
applied, what the last pass found — at the end rather than weaving them through.
An unchanged prefix hits prompt caching instead of re-billing the same context
each time. Resuming the finder at Step 6 does not retire this rule: it governs
the fallback path when a fresh fixer is spawned, and the Step 3 spawns
themselves, which repeat every iteration regardless.

### Step 7 — Verify

- Every new regression test passes.
- **Between iterations**, that plus whatever existing tests cover the files the
  fix touched — the module, the file's neighbours, whatever the framework can
  select cheaply. Not the full suite.
- **Once per run**, immediately before the Step 9 report: the full suite, no
  worse than the Step 2 baseline. That is the gate; nothing is reported or
  committed until it holds. Where the project cannot select a subset cheaply,
  the targeted run *is* the full run and this changes nothing.

**Never modify, weaken, delete, or skip an existing test to get to green.** If
a pre-existing test now fails, the fix broke it — fix the fix. If you cannot,
revert that fix and report it as unresolved.

## Committing

By default, stage the fixes **and the new regression tests**, then commit.

- `git add` the specific paths you changed. Never `git add -A`.
- Never amend or rebase the user's existing commits.
- If this turn already stated a commit subject, keep it unchanged.
  If the user was already writing a commit message, keep it and append what
  this skill changed.

**Always end the commit message with a trailer recording what happened**, so a
commit that went through this skill is distinguishable from one that didn't:

```
Bug-hunter: 1 iteration, 1 bug fixed
Bug-hunter-Tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904   ← every non-skip shape needs this
Bug-hunter: 1 iteration, 0 bugs found
Bug-hunter-Tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904   ← including this one
Bug-hunter: skipped at triage (checkpoint)                  ← except this one
Bug-hunter: 3 iterations, aborted — see report
Bug-hunter-Tree: 4b825dc642cb6eb9a060e54bf8d69288fbee4904   ← and this one
```

**Make the commit with `commit-with-trailer.sh`** (SKILL.md, Step 9) — the
message file (`-F msg.txt`, or subject and body as two words), the
`Bug-hunter:` value, and optionally the `Co-Authored-By` value. It
passes each as a real git trailer (last paragraph, beside the others, with a
value — see [Trailer placement](#trailer-placement)) and, for any value that is
not a skip note, mints the `Bug-hunter-Tree` binding against the staged tree
(see [Minting the tree binding](#minting-the-tree-binding)). Verify with
`git log -1 --format='%(trailers:key=Bug-hunter)'`. A non-skip trailer with no
matching `Bug-hunter-Tree` is reported as looking hand-written, not as
unchecked — a related but distinct failure, and the one a hand-built
`git commit -m … --trailer …` produces when the mint step is forgotten.

Another installed skill's trailer goes on the same commit, as a
`--verified-value <verifier> <Key> <value>` family before a `--` that ends the
families (SKILL.md, Step 9, shows prose's). The script passes those through to
the shared library and takes no other option.

The trailer is not optional. It is what the companion hook looks for, and the
only way anyone can audit whether this skill ran on the commits it should have.
A trailer that misdescribes what happened is a false statement in the permanent
record of the repository — write what occurred, including `aborted` and
`skipped`. To audit a repo:

```bash
git log --invert-grep --grep='Bug-hunter:' --oneline   # commits that skipped it
```

**Report-only mode** leaves everything in the working tree, staged, for the
user to review. Use it when:

- The user asks for it — "just report", "don't commit", "let me look first".
- The run aborted at Step 8.
- Anything was reported-not-fixed that changes what the commit means.
