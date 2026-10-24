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
- Who decided, where the document says so, such as "(Adam, 2026-10-24)", and
  the date of a measurement.
- Links, commands, code, names and numbers, exactly.
- Each heading listed below as linked or named by other files, with its exact
  text.

A fresh reviewer then checks every removal against the old text. So cut
boldly, but never drop a conclusion you believe is no longer true: leave it
where it is, and list it in your reply, and a person decides. A conclusion is
what the document says is so. History, wording and repetition are not
conclusions.

Write plainly: one claim per sentence, the conclusion first, each sentence
following from the last. Add nothing the document does not already say.

**Reply** with only these lines:

```text
Compacted: <the file's path>
Would drop: none
```

or, for each conclusion you left in place but believe is no longer true, one
line in place of `none`:

```text
Would drop: «<the conclusion, quoted>» <why you believe it is no longer true>
```
