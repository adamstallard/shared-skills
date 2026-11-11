# Compact a document

Agents read this document before they work, every time, so every sentence that
no longer serves them is paid for on every read. Rewrite the file named below
so it states what is true now and why, and nothing else.

**Draft it fresh, section by section.** For each section, write what it must
say now, from what it decides and why, then compare your draft with the old
text and carry over every conclusion your draft lacks. Then write the whole
file out at once. Editing the old text sentence by sentence keeps its
structure and its history, and cuts little. A doc that grew with its history
usually loses a third or more. If you cut less than a tenth, you edited rather
than compacted: draft once more. If that draft cuts no more, the document was
already compact; keep the shorter of the two.

**Remove:**
- History: dated narrative, "revised" and "superseded" notes, how a decision
  was reached, what an earlier version did or said.
- Reasoning for designs the document no longer has.
- Repetition: a claim stated more than once, often in two entries that decide
  the same thing. Merge them, and state the claim once, where a reader would
  look for it.
- Examples that teach nothing the rule beside them doesn't already say.

**Keep:**
- Every live conclusion: each decision, rule, limit, default, measured number,
  known gap and warning, with the reason it matters.
- Each rejected alternative an editor would otherwise propose again, in one
  line: what it was and why it was rejected. Say it on its own terms, not as
  something an earlier version did.
- The date of a measurement. Keep or drop each "who decided" credit, such as
  "(Adam, 2026-10-24)", as the *Credits* line below says.
- Links, commands, code, names and numbers, exactly.
- Each heading listed below as linked or named by other files, with its exact
  text.

**Answer for every flagged passage.** A script flagged the passages listed
below: history, repetition, amendment notes, long rejected alternatives,
stale references, narrative words and filler. Write one line for each, in
order, to the answers file named below. If you cannot write there, write the
same lines to a file outside the repository, such as under `$TMPDIR`, and
name that file in your reply.

```text
Passage <n>: removed
Passage <n>: rewritten
Passage <n>: kept: <why it must stay word for word>
```

`rewritten` means the claim is still there in fewer words. A check then
searches the new file for each passage's text, ignoring case, emphasis and
line breaks: a passage answered `removed` or `rewritten` must appear fewer
times than before. The script's flags are simple patterns, so some are
wrong; a flag that is wrong is `kept:`, with the reason. A reviewer judges
every `kept:` reason.

A fresh reviewer then checks every removal against the old text. So cut
boldly, but never drop a conclusion you believe is no longer true: leave it
where it is, and list it in your reply, and a person decides. A conclusion is
what the document says is so. History, wording and repetition are not
conclusions.

**Propose a move for each listed section; move none yourself.** The brief
lists sections that a condition heads or opens, such as "When the caller
commits", costliest first. Moving one into a file this document links to
cuts what every reader loads, but only when all three of these hold:
- the section is needed only in the situation its condition names;
- in that situation, a reliable signal reaches the reader and names the new
  file: a message a script prints, a refusal, a person's request, or a step
  that every such reader runs in the document you are compacting;
- the line that replaces the section is far shorter than the section.

A section needed on every pass costs more behind a pointer: the reader reads
the pointer, then the file. Keep every section in your rewrite, since a
person decides each move.

Write plainly: one claim per sentence, the conclusion first, each sentence
following from the last. Finish one point before starting the next: when you
reorder or merge sentences to save words, never split a point around another
(rule 3 of prose's rules.md, *A point split around another*). Add nothing the
document does not already say.

A cold reader, an agent that reads your file with no other context, may
report the words where it stopped, reread or guessed, and those findings may
come back to you. Fix each with the first that works: cut it, move it beside
the point it continues, or reword it. A fix works when a reader would no
longer stop there and no conclusion is lost. Edit only those places, then
reply as below.

**Reply** with only these lines, then the `Move` and `Stay` lines below for
any sections listed, and the `Answers:` line when it applies:

```text
Compacted: <the file's path>
Would drop: none
```

or, for each conclusion you left in place but believe is no longer true, one
line in place of `none`:

```text
Would drop: «<the conclusion, quoted>» <why you believe it is no longer true>
```

Then add one line for each section the brief lists to consider moving out:

```text
Move <n>: <new file, beside this document> | pointer: «<the line that replaces the section>» | signal: <what sends a reader to the new file>
Stay <n>: <which of the three requirements for a move above it fails>
```

The pointer line names the signal, so a reader who meets it knows to open
the file: for example, «When `prose check` prints `compaction due`, read
[compaction.md](compaction.md) and follow it.»

If you wrote the answers somewhere other than the answers file named below,
add one more line after those: `Answers: <that file's path>`.
