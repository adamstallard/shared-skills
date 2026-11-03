# spec-check

spec-check is a review aid for OpenSpec changes at the spec stage, before any
code exists. The slow part of reviewing a spec is holding every other spec in
mind. spec-check does that part, so you only judge whether the rules are the
right ones.

> Agent instructions: [SKILL.md](SKILL.md). Why it works this way:
> [DECISIONS.md](DECISIONS.md).

## What you get

Before an agent commits, or opens a pull request for, anything under
`openspec/`, it:

1. **Runs the mechanical checks** in `scripts/spec_check.py`:
   - a requirement with a SHALL or MUST and no scenario;
   - a scenario with no WHEN or THEN;
   - the same rule stated under two requirements;
   - a `path:line` citation whose line is on neither the base branch nor
     the change;
   - what `openspec archive` would refuse: an ADDED requirement whose name
     the specs already have, a RENAMED onto a taken name, a MODIFIED that
     drops a scenario. `check` archives the change into a scratch copy of
     your specs to find out;
   - a requirement written out under `## RENAMED Requirements`, whose text
     the archive drops;
   - a line recording how the change got to its shape, such as "amending
     decision 79" or "(Adam, 2026-10-21)". The agent removes it; when the
     line is not history, the agent asks you, and only your answer keeps
     it.

   It also runs `openspec validate --strict` and includes what it reports,
   such as a misspelt section title or a section the archive drops.

   A **stacked change**, one that applies on top of another open change, says
   so in its proposal with a line such as `Builds on: seat-files
   (adamstallard/igor#171)`. The checks then run against main plus that
   change. `check` reads the change from its pull request and archives it
   into a scratch copy of your specs with `openspec archive`.

   A dependency whose pull request has merged is not archived, since its
   result should already be in your specs. `check` looks for that result
   there: when the result is there, it says to remove the line, and when it
   is not, to merge main.

   The stacked change fails as `drift` when it edits a requirement its
   dependency has since renamed or removed, and as `archive` when `openspec
   archive` refuses any part of it on top of its dependencies, such as an
   ADDED of a name a dependency already adds. A sentence the stacked change kept
   after its dependency reworded it gets a `drift` check, which quotes both
   texts for you to judge. A dependency that cannot be read fails the check
   with a `stack` error. When a duplicate matches a main requirement that
   an open pull request removes or renames, the error suggests the
   `Builds on:` line to add.
2. **Has a fresh subagent read the change** against every spec, every other
   open change, every open pull request touching the same specs, and your
   architecture docs. Findings come with quotes from both sides.
3. **Fixes the spec itself.** A question only you can answer goes into
   design.md's *Open Questions*, not into a pull request comment.

Decisions go in design.md: a change states each one once, as it stands now,
in design.md's *Decisions*, and keeps proposal.md to OpenSpec's short why and
what. `check` does not test where a decision sits, but a line recording how
one was amended is an error.

Each commit that changes `openspec/` carries a `Spec-check:` trailer, such as
`Spec-check: ✓ 4d593e935186 0 errors, 2 checks; validate passed; read by a
fresh subagent; 3 amended, 1 open`. The hash is the tree the checks ran on,
so staging anything afterwards breaks it. "read by its author, no subagent"
means no fresh reader was available. When a person kept a flagged line (one
recording how the change got to its shape) as written, the value adds a
count after the checks, such as "1 evolution kept".

**What it proves.** The trailer proves the mechanical checks passed on exactly
what was committed. It does not prove a fresh subagent did the read: it
records who the agent says did. Likewise, an "evolution kept" count
records that the agent says a person approved each kept line; it does not
prove it.

## Setup

Install it by asking your agent: "Install the spec-check skill". Installing
turns on its hook (see below).

spec-check needs OpenSpec 1.15.0 or later on `PATH` (`npm install -g
@fission-ai/openspec`). It reads the requirements of every spec and change
through the OpenSpec CLI only. Without that version, the checks on
requirements are reported as not run.

Nothing needs setting up per repository. spec-check reads no
`openspec/spec-check.yaml`, a file earlier versions wrote; if your repository
has one, delete it.

## Examples of what to say

> "Check this spec before you commit."
> "Cross-check the scope-check change against the other open changes."
> "Review spec PR 212."

Or run the checks yourself:

```bash
python3 ~/.agents/skills/spec-check/scripts/spec_check.py check              # every open change
python3 ~/.agents/skills/spec-check/scripts/spec_check.py check my-change
python3 ~/.agents/skills/spec-check/scripts/spec_check.py check --ref origin/spec/my-change my-change
```

`--ref` reads a branch without checking it out. Citations are checked
against `origin/HEAD` (then `origin/main`, then `main`); `--base` changes it.

## The hook

spec-check has one hook, the commit hook. After each shell command, it looks
for new commits that change `openspec/` and reports any without a valid
`Spec-check:` trailer. A commit that changes nothing under `openspec/` is never
reported. Only `openspec/` at the repository root counts.

It never blocks. If your install still wires a `proposal-hook.sh` from an
earlier spec-check, the next `install` or `enable-hook` removes it, and until
then `skills.py doctor` lists it as `STRAY`. To turn the hook off:

```bash
python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook spec-check
```

## Troubleshooting

- **`not run: install OpenSpec 1.15.0 or later`.** The `openspec` CLI is
  not on `PATH`, or is older than 1.15.0. The requirement checks, validation
  and the archive did not run; citations and the `renamed-block` scan did.
  A stacked change also gets a `stack` error, since its dependencies are read
  and archived with the same CLI. Install or update OpenSpec (`npm install -g
  @fission-ai/openspec`) and run it again.
- **An `archive` error quotes `openspec archive`.** The change would not
  archive onto the specs it is checked against. OpenSpec reports one
  refusal at a time, so fix it and run `check` again.
- **A citation is reported missing, but the file exists.** The check reads
  the base branch (`origin/HEAD`, then `origin/main`, then `main`) and the
  change's own copy of the file (the working tree, the branch named with
  `--ref`, or the staged files when signing), and the file is in neither at
  that line. If the change
  targets another branch, pass `--base`.
- **The agent cannot make the trailer.** `spec_check.py sign`, which prints
  the `Spec-check:` line, refuses while errors remain, and prints them. For
  work in progress, the agent commits with `Spec-check: skipped (<reason>)`.
- **A `stack` error quotes `openspec archive` refusing a dependency's
  deltas.** The dependency does not fit your tree with the dependencies
  listed before it archived: a requirement it modifies or renames is not
  there, or a name it renames to is taken. Usually a `Builds on:` line is missing or out
  of order, or your branch is behind main.
- **A `stack` error says a dependency cannot be read.** `check` reads each
  `Builds on:` pull request with `gh` and fetches it with `git`, so it needs
  both, signed in, and the network. Fix that and run it again. Until a run
  can read every dependency, it does not check the change for duplicates or
  drift.
- **`check` says every delta of a dependency is already in the tree, or
  that a merged dependency's result is.** This is a check, and does not
  fail the run. Your branch's specs already hold the dependency's result:
  remove its `Builds on:` line.
- **`check` says some of an open dependency's deltas are already in the
  tree.** It archived the rest and names each. Usually another change has
  landed part of the same edit.
- **A `stack` error says a dependency builds on a change this one does not
  list.** That dependency's own proposal has a `Builds on:` line for a change
  whose result your tree does not hold. Add that change's line before the
  dependency's.
- **A `stack` error says a dependency has merged, but this branch does not
  hold its result.** A merged dependency is never archived again, so your
  specs must show it: each requirement it adds or modifies present by name,
  each it removes absent, its renames done. The error names what is
  missing. Merge main into your branch. A merged change that a dependency
  builds on must show in your specs the same way.
- **`check` says a later dependency sets again what an earlier one sets,
  without building on it.** The earlier dependency's version of that
  requirement is left out. Check that the later one's text includes what
  your change needs, or ask its author to stack it on the earlier one.
- **`check` says a pull request holds no change of that name.** The
  `Builds on:` line names the wrong change or the wrong pull request.
- **`check` says it cannot read a pull request's full file list.** `gh`
  lists only the first 100 files, and reading the rest from GitHub failed.
  Check that `gh` is signed in and run it again.
