---
name: commit
description: >-
  Split the working tree into TYPE(Scope): commits and create them. Use when
  the user says "commit this", "commit my changes", "let's commit", "wrap this
  up and commit", "split this into commits", or "organize commits". If this
  skill is available, it owns those phrases and invokes bug-hunter on each
  commit that contains code. Do not use it when another skill's own
  instructions already tell it to create the commit.
  Skip hunt this turn if they say "skip bug-hunter" or "commit
  without hunting".
---

# Commit

A slice is one group of changes that becomes one commit. Inspect the diff, split it into slices, and commit. Print the intended subjects, then create the commits. Do not wait for approval of those subjects.

## Hard stops

- Do **not** `git add -A`
- Do **not** skip hooks
- Do **not** amend unless asked
- Do **not** pass `--force` to git
- Do **not** commit secrets
- Do **not** create a commit when another skill's own instructions already tell it to create that commit

## Workflow checklist

```
Commit:
- [ ] Inspect status + diff (staged and unstaged)
- [ ] Print intended commits, one subject each
- [ ] For each slice: stage only that slice's paths; hunt or skip; commit
- [ ] Report SHAs
```

## Message

```
TYPE(Scope): one-line description [(agentic)]

- what changed
- important decision, if any
```

- Subject ≤ 72 chars.
- **TYPE:** `FEAT` `FIX` `DOCS` `SPEC` `TEST` `BUMP`. Reuse any other TYPE already in `git log` (`CHORE`, `WIP`, `PERF`).
- **`(agentic)`** on the subject only if this agent wrote or edited that slice. Human-only diffs: no tag.
- Body: short bullets. No filler.

## Scope

Reuse a token already in `git log` **verbatim** (`Profile`). Otherwise pick the named product surface a teammate would grep for — not a layer (`Frontend`), not a file, not a ticket.

When inventing, first letter **capital** (`Profile`, not `profile`). Stay at the feature: `FIX(Profile): keep the crop when a photo is replaced`, not `FIX(ProfilePhoto):`. `Profile` stays `Profile` even when the API and the UI both moved. Specificity goes in the description. Two features become two commits, one Scope each. Do not coin a smaller Scope so both features share one commit. When one commit has to cover both features, put the larger feature's Scope in the subject and name the other feature in the body.

## Split

Organize what is there. Do not force a template the tree does not support.

**Prefer** this order when the files separate cleanly:
1. `SPEC` / `DOCS` (one commit for one specification change is enough)
2. Implementation, by Scope
3. `TEST`, by the same Scopes

Keep hunks together when splitting them would be fake. A specification that only describes one feature stays with that feature's code. A spec that is meaningless without the short implementation beside it stays with that implementation. Tests that cannot compile without the code they cover stay with that code. Split by Scope, by phase, or by specification change — whichever matches the tree.

## Per slice

Stage **those paths only**.

If `bug-hunter` is available, the slice is code, and they did not skip: run it on this index. It commits. Pass the subject you already printed — it must keep that subject and only add trailers.

Else commit yourself. Pass `--trailer "Bug-hunter: skipped — <reason>"` (`user skipped`, `bug-hunter not installed`, or `docs/spec/test`).

Skip hunt this turn: "skip bug-hunter" / "commit without hunting".

## Done

Print each SHA and subject.
