# The prose pass

**The reader came here for something. Find out what, give them that first, and make it quick to read. Count the reader's time, not your words.** Quick means:
- **Read once:** nothing misleads them into going back (rules 3 and 4).
- **Understood without help:** nobody has to ask an agent what it means (rules 3 and 5).
- **Not verbose:** nothing they didn't come for (rules 1, 4, 6 and 8).

## Scope

Rewrite only text you wrote or changed in this change: comments, docs, specs, the commit message, the PR description. Leave other text alone, even in files you touched. Rewriting it grows the diff the reviewer has to read. One exception: a phrase your change repeats that has no definition or reason anywhere is fixed at its source (step 4).

## The pass

**1. Name the reader's goals**, most probable first: `--goals` for the commit message or the post, and `--goals-for` for each changed doc and spec. Start from this table and adjust it to the text. A row is also the default: `prose check` suggests it for a doc you gave no goals, and gives it to a code comment you gave none.

| Text | Who reads it | Why, most likely first |
|---|---|---|
| Commit message | a reviewer; later, someone running `git blame` | what changed and whether to approve it; why a line is the way it is |
| PR description | the reviewer | what to look at, what's risky, whether it's done |
| Code comment | someone about to change this code | what it does that the code doesn't show; what breaks if they change it |
| README | someone new to the thing | what it's for; how to start; what to do when it fails |
| Spec | an implementer; a reviewer approving the design | what must be true; what's decided vs. open |
| Other doc (architecture, guide) | someone learning what it describes | how it works now; why it is that way |
| Issue or ticket comment | a teammate | what's decided, what's needed from them |

**Each text has its own reader.** A commit holds several: `--goals` names the message's reader, the reviewer, but each doc, spec and comment is read by someone else, who never sees the conversation behind the change. Name that reader for each document: an architecture doc, an API reference and a runbook are read for different reasons. What a reviewer needs to approve the change goes in the message or the PR description, not the doc.

**2. Order the text by those goals.** The most probable goal comes first. The rarer a goal, the less space it gets: a line, or a pointer elsewhere.

**3. Cut** what no goal needs (rules 1, 4 and 6). **Then make what's left quick to read** (rules 3 and 8).

**4. Read it once as the reader,** someone who doesn't know what you meant, and fix every place you'd stop or re-read (rules 3, 4 and 7). In a doc, reread each changed passage inside its section, as that section's reader, before keeping it: a passage that makes sense beside the diff can make none in the section it lands in. When a changed passage repeats a phrase, grep the repository for it. A phrase that recurs across documents with no definition or reason at any use gets fixed at the source: one statement with its reasons, and the others cut or pointed at it (rule 5).

**Never cut:** the why of a decision the code doesn't make obvious; a warning that stops someone repeating a mistake; a stated limit ("not tested on Windows"). These are what a reviewer can't recover from the diff.

**This is not a fact-check.** Ask whether a sentence needs to exist, not whether it can be defended. When a reviewer shows a claim is overstated, delete or narrow it; never add a hedge.

## The rules, most important first

### 1. Keep a sentence only if the reader needs it
Needs it for one of their goals. Being true or interesting isn't enough.
*Why:* every sentence is one more the reader reads to find what they came for.
```
Before: # This function handles retry logic, which is important because network
        # calls can fail for many reasons, including timeouts and DNS errors.
        # We retry up to three times with exponential backoff, which generally
        # works well in practice.
After:  # Up to three retries with exponential backoff: the payment API rate-limits
        # bursts, and a fixed delay kept tripping it.
```

### 2. Conclusion first; one section per conclusion
The first sentence says what the reader most needs: the decision, the change, the result. Several conclusions each get a clearly marked section.
*Why:* reviewers skim. Text that builds up to its point makes them read all of it to find the point.
```
Before: I investigated the flaky test and found the fixture wasn't reset between
        runs. I also noticed the timeout was too short. After fixing both, it
        passed 50 out of 50 runs.
After:  **Flaky `test_upload` fixed** — 50/50 passes.
        - **Fixture** wasn't reset between runs.
        - **Timeout** was 2s; uploads take up to 3s on CI.
```

### 3. Read once, understood once
Ask of each sentence: would a reader have to go back? If so, rewrite it so they don't. Grammatically correct isn't the bar.
*Why:* the pass exists to cut reading time, and a reread costs more than any word it saved. Usual causes:
- **A word with two readings** that leads to a dead end: noun stacks ("hook config write fails"), a dropped "that" ("ensures the trailer landed matches"), a clause with its "that is/was" removed ("the commit reported twice was amended"), "it" or "this" with two possible referents.
- **A result before its condition**, in the same sentence or a later one. "X happens when Y" reads as always true until "when" arrives, and so does a paragraph whose last sentence says "only when Y". Start with what the sentence is about and the case it covers, then what happens.
- **One thing said to be another.** "Each input it leaves out is a hook that can be skipped" makes the reader work out how an input and a hook are connected. Say the connection: "when an input it leaves out changes, the hook can be skipped".
```
Before: The hook reports commits landed without trailers skipped.
After:  The hook reports commits that landed without a trailer, including skipped ones.

Before: Nothing is recorded, and the hook runs every time, when a pre-commit
        hook is defined in config.
After:  A pre-commit hook defined in config always runs, and is never recorded.
```

### 4. Each sentence follows from the last
Stay on the reader's topic. A sentence that jumps to a subject they weren't expecting, or may not know or care about, makes them stop, reread, or ask what it has to do with anything. Leave it out. If they do need the new subject, give it its own paragraph that says what it is and why it matters here, as briefly as rules 1 and 8 ask.
*Why:* every abrupt switch costs the reader a pause to work out the connection, and often there is none for them to find.
```
Before: Run deploy.sh to push the build to staging. WSL1 has a clock-skew bug.
        Then open the staging URL to check the build.
After:  Run deploy.sh to push the build to staging, then open the staging URL to
        check the build.

        On Windows under WSL1, deploy.sh fails with a clock-skew error; run
        `sudo hwclock -s` first.
```

### 5. Plain words, and reasons instead of catchphrases
Define it or drop it: acronyms, project jargon, shorthand you coined, agent idiom. A name you gave something during the work is still shorthand, however often you've used it: say what it is. An analogy or idiom only if it's already common in the project's own writing.
**A claim is stated once, with its reason, and elsewhere linked or restated in plain terms.** A catchphrase used as a reason, an aphorism standing in for an argument, is a sign the reasoning isn't written down. Before keeping one, ask what it means literally and what the reason is; if the text can't say, the claim is unsupported.
```
Before: Load-bearing guard; belt-and-braces for the cursor drift case.
After:  Without this check the reflog cursor can skip a commit (see test_cursor_drift).

Before: Next: the formatter fix.
After:  Next: prose check runs the pre-commit hook before it signs.

Before: An Igor that does two jobs is two Igors.
After:  In the one place the rule is decided:
          An Igor holds exactly one role. A role extends at most one base: with
          two, its permissions would change whenever either base changed,
          without its own file changing, and the two would conflict on fields
          where the last level wins.
        Everywhere else:
          An Igor holds exactly one role.
```

### 6. What is, not how it got here
A doc or comment describes what *is*. No "previously", "we changed", "the old version", "the argument once made". A superseded or rejected design appears only where a reader would otherwise reinvent it, and then it stands on its own: what it was, and why it was rejected. Otherwise cut it; its history belongs in a decision record (a change's design, a decision log) or the commit message. A warning about a tempting change isn't history: keep it, and make it easy to find.
*Why:* the reader came to learn how the thing works now. A past design they were never shown makes them reconstruct it before they can see why it no longer applies.
```
Before: **Several Igors may draw on one seat (§6.5).** The argument once made for
        multi-role Igors, that a second role absorbs the idle capacity of a seat
        dedicated to one Igor, does not apply: seats are shared, so a narrow
        role's slack is used by the other Igors on its seat.
After:  **Several Igors may draw on one seat (§6.5).** A narrow role's unused
        capacity goes to the other Igors on its seat. A role that reliably fills
        a seat can be given its own, and one that doesn't shares one.
```

### 7. Say when, and whether
Label past, present and future, and actual versus conditional, bluntly and separately. More than one time frame gets one section each ("Current behaviour", "Lessons learned", "Planned, not built"); inside a sentence, say it outright ("Before this change…", "Not built yet:", "If X happens…"). Label every counterfactual: what would happen without this code, or how an alternative behaves ("Without this check…", "The alternative, X, would…").
*Why:* a reader usually has one of these goals at a time; mixed in one tense, they read all three to find theirs.
**Labelling the past does not make it worth keeping.** This rule says how to mark a past or a counterfactual that the reader needs; whether they need it is rules 1 and 6. In a doc or comment, the past is cut unless rule 6 keeps it.
```
Before: # git compares trailer tokens by prefix, so `Bug-hunter-Tree` "already exists"
        # whenever `Bug-hunter` does. A user's ifexists=replace overwrote a family's
        # key with its binding, doNothing dropped the binding, and where=start
        # reversed the block. Pin what this commit needs, for this command only.
After:  # Pins git's trailer settings for this one command, so every trailer passed
        # here lands, in order.
        #
        # Don't remove a pin. What each one prevents:
        # - trailer.ifexists=add: git matches trailer keys by prefix, so it treats
        #   `Bug-hunter-Tree` as a repeat of `Bug-hunter`; any other value can
        #   replace or drop a binding.
        # - trailer.where=end: with start, the trailers land in reverse order.
```

### 8. Spend words where they save reading time
Cut words that cost the reader time and give nothing back: filler, throat-clearing, a point made twice. Add words that save time: the "that" or article that prevents a misreading, a subject named instead of "it", a condition stated before its result. A longer sentence that reads once beats a shorter one read twice. Never shorthand (rule 5).
```
Before: Retries on 5xx; backoff doubles, cap 30s.
After:  It retries when the server returns a 5xx error, doubling the wait each time, up to 30 seconds.
```

### 9. Say who acts
Active voice wherever the actor matters.

### 10. One topic per block
A comment, paragraph or section answers one question.

### 11. One scope line instead of scattered hedges
"Checked: X. Not checked: Y."

### 12. Don't restate what the code or diff shows

### 13. Commit subject says what changed; the body says why

### 14. Make references followable
Point to a source with a link or a clickable path (`file:line`), not a name the reader has to search for.

## How agents cheat on this pass

- Adding a "Note:" or "Clarification:" line instead of rewriting the unclear sentence.
- Going telegraphic ("fixes race w/ cache inval") to look short.
- Calling text "already clear" without naming its reader's goals.
- Keeping a sentence because it's true, or because a reviewer might ask.
- Hedging a claim a reviewer challenged, instead of cutting it.
- Keeping context a reviewer needed in a document whose reader never will.
- Repeating a phrase that sounds like a reason in place of the reason.
