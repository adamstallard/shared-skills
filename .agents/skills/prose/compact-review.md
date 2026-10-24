# Review a compaction

Another agent compacted a document that agents read before they work. It was
meant to remove only history, superseded reasoning, repetition and examples
that teach nothing a rule doesn't, and to keep every live conclusion. You
check that it did. A compactor that checks its own work misses losses, so
you are the check.

The changes file named below lists only what changed, change by change: the
old text under *Before* and the new under *After*. Read it, and read the
compacted file where you need to know whether something moved. Don't reread
text that did not change.

**For each piece of removed text,** in a removed or rewritten change, decide
one of:
- **superseded:** the old text was history, reasoning for a design the
  document no longer has, or repetition;
- **folded in:** the new file still says it. Name where: the heading, or
  the change number.
- **lost:** a live conclusion that the new file no longer says. Live
  conclusions are decisions, rules, limits, defaults, measured numbers, known
  gaps, warnings, reasons a decision holds, and rejected alternatives with
  why they were rejected.

**For each rewritten or added sentence,** check that its claim holds against
the code and docs it describes, in the repository named below. Open them;
don't rely on the old text alone. A rewrite that renames a rule, changes a
number or count, or turns "may" into "always" is false even when it reads
well.

The changes file starts with the names (code spans, flags, constants, paths
and headings) that the old file has and the new one doesn't. Account for each
one in a verdict.

**Reply** with one or more lines per change, and nothing else:

```text
Change <n>: superseded
Change <n>: folded in: <where>
Change <n>: lost: <the conclusion, as the document should state it again>
Change <n>: holds
Change <n>: false: <the claim> — <what is true, and the file that shows it>
Totals: <lost> lost, <false> false
```

When restoring something is itself a judgement call, start the text after
the verdict with `ask:`, as in `Change 3: lost: ask: <the conclusion> — <why
it needs a person>`. For example, the conclusion may contradict another
one, or it may describe something the code no longer does.
