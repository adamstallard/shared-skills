---
name: commit
description: >-
  Split the working tree into commits and create them, in the repository's own
  commit convention. Use when the user says "commit this", "commit my changes",
  "let's commit", "wrap this up and commit", "split this into commits", or
  "organize commits". If this skill is available, it owns those phrases and
  runs bug-hunter on each commit that contains code. Do not use this skill when another
  skill's own instructions tell that skill to create the commit. Skip the hunt
  this turn if they say "skip bug-hunter" or "commit without hunting".
---

# Commit

A slice is one group of changes that becomes one commit. Inspect the diff, split it into slices, and commit. Print the intended subjects, then create the commits. Do not wait for approval of those subjects.

## Hard stops

- Do **not** `git add -A`
- Do **not** skip hooks
- Do **not** amend unless asked
- Do **not** pass `--force` to git
- Do **not** commit secrets
- Do **not** create a commit when another skill's own instructions tell that skill to create it
- Do **not** run `git commit` yourself while bug-hunter or prose is installed: commit the way *Per slice* says for what is installed

## Workflow checklist

```
Commit:
- [ ] Find the repository's commit convention
- [ ] Inspect status + diff (staged and unstaged)
- [ ] Print intended commits, one subject each
- [ ] For each slice: stage only that slice's paths; hunt or skip; commit as *Per slice* says
- [ ] Report SHAs
```

## Convention

Write every subject in the repository's own convention. Take the first of these that exists:

1. The convention the repository writes down, in `AGENTS.md`, `CONTRIBUTING.md` or a similar file.
2. The convention its recent `git log` shows: the subject's shape, the types it uses and their case, and its scopes. Reuse a type or scope from the log verbatim.
3. The default below.

In every convention, keep the subject to 72 characters unless the convention sets another limit. Write the body as short bullets: what changed, and any important decision.

When an agent wrote or edited the slice, its commit gets a `Co-Authored-By` value naming that agent. *Per slice* shows where the value goes in each case. A slice a person wrote alone gets none.

### Default: `TYPE(Scope): description`

- **TYPE:** `FEAT` `FIX` `DOCS` `SPEC` `TEST` `BUMP`.
- **Scope:** the named product surface a teammate would search for, not a layer (`Frontend`), a file or a ticket. First letter capital (`Profile`, not `profile`).
- Stay at the feature: `FIX(Profile): keep the crop when a photo is replaced`, not `FIX(ProfilePhoto):`. `Profile` stays `Profile` even when the API and the UI both moved. Specificity goes in the description.
- Two features become two commits, one Scope each. Do not coin a smaller Scope so both features share one commit. When one commit has to cover both features, put the larger feature's Scope in the subject and name the other feature in the body.

## Split

Organize what is there. Do not force a template the tree does not support.

**Prefer** this order when the files separate cleanly:
1. Specs and docs (one commit for one specification change is enough)
2. Implementation, one commit per feature
3. Tests, for the same features

Keep changes in one commit when either part would be broken or meaningless alone. These cases override the order above. A specification that only describes one feature stays with that feature's code. A spec that is meaningless without the short implementation beside it stays with that implementation. Tests that cannot compile without the code they cover stay with that code. Split by feature, by phase, or by specification change — whichever matches the tree.

## Per slice

Stage that slice's paths only. Write its message to a file outside the repository, called `msg.txt` below: the subject, a blank line, then the body. Never put a trailer in it.

To learn whether bug-hunter and prose are installed, run the `manage-skills` skill's `list` command: a skill is installed when its row says `installed`. bug-hunter and prose sit in the same parent directory as this skill. Below, `<skills>` stands for that parent directory's absolute path.

**A slice with code, bug-hunter installed, and no skip asked for:** run bug-hunter on the staged slice, and tell it about `msg.txt` and the co-author. bug-hunter keeps a subject this turn already printed, adds only trailers, and commits. It adds prose's trailer too when prose is installed.

**Any other slice, with bug-hunter installed:** commit through bug-hunter's script. Its skip value is `skipped at triage (<reason>)`, where the reason is `docs only`, `specs only` or `tests only`. When the user asked to skip, the value is `skipped (user asked)`. Say "skipping bug-hunter — <reason>" in your reply for that slice.

```sh
BH="<skills>/bug-hunter/scripts/commit-with-trailer.sh"
"$BH" -F msg.txt "skipped at triage (docs only)" "<co-author>"
```

When prose is installed too, first run prose's two `check` calls on the staged slice and `msg.txt`, as prose's SKILL.md (*Committing*) says. The second call prints the `Prose:` value. Pass it before `--`:

```sh
"$BH" --verified-value "<skills>/prose/scripts/verify-staged.sh" Prose "<value prose printed>" -- \
  -F msg.txt "skipped at triage (docs only)" "<co-author>"
```

The commit then carries both trailers. Stage and edit nothing between prose's second call and the commit: the script checks the `Prose:` value against what is staged, and refuses the commit if either changed.

**bug-hunter not installed, prose installed:** commit as prose's SKILL.md (*Committing*) says, with the `Prose:` value only.

**Neither installed:** `git commit -F msg.txt`, adding `--trailer "Co-Authored-By: <co-author>"` when an agent wrote or edited the slice.

Leave out `"<co-author>"` when a person wrote the slice alone.

Skip the hunt this turn when they say "skip bug-hunter" or "commit without hunting".

## Done

Print each SHA and subject.
