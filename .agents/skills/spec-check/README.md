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
   - a proposal that does not open with its decisions, in a repository that
     enforces that rule (see Setup).

   It also runs `openspec validate --strict` and includes the result.

   A **stacked change**, one that applies on top of another open change, says
   so in its proposal with a line such as `Builds on: seat-files
   (adamstallard/igor#171)`. The checks then run against main plus that
   change. `check` reads the change from its pull request and archives it
   into a scratch copy of your specs with `openspec archive`, so stacked
   changes need the OpenSpec CLI. A dependency whose pull request has
   merged is not archived again. Instead, `check` looks for its result in
   your specs: when the result is there, it says to remove the line, and
   when it is not, to merge main.

   The stacked change fails as `drift` when it edits a requirement its
   dependency has since renamed or removed, or when `openspec archive`
   refuses any part of it on top of its dependencies, such as an ADDED of
   a name a dependency already adds. A sentence the stacked change kept
   after its dependency reworded it gets a `drift` check, which quotes both
   texts for you to judge. A dependency that cannot be read fails the check
   with a `stack` error. When a duplicate matches a main requirement that
   an open pull request removes or renames, the error suggests the
   `Builds on:` line to add.
2. **Has a fresh subagent read the change** against every spec, every other
   open change, every open pull request touching the same specs, and your
   architecture docs. Findings come with quotes from both sides.
3. **Fixes the spec itself.** A question only you can answer goes into the
   proposal's decisions section as an open question, not into a pull request
   comment.

Each commit that changes `openspec/` carries a `Spec-check:` trailer, such as
`Spec-check: ✓ 4d593e935186 0 errors, 2 checks; validate passed; read by a
fresh subagent; 3 amended, 1 open`. The hash is the tree the checks ran on,
so staging anything afterwards breaks it. "read by its author, no subagent"
means no fresh reader was available.

**What it proves.** The trailer proves the mechanical checks passed on exactly
what was committed. It does not prove a fresh subagent did the read: it
records who the agent says did.

## Setup

Install it by asking your agent: "Install the spec-check skill". Installing
turns on its hooks (see below).

Then, once per repository, ask your agent: "Set up spec-check in this
repository". It asks whether you want the decisions-first rule, which makes
every proposal open with the decisions the reviewer is asked to make, and
records the answer in `openspec/spec-check.yaml`:

- **Yes** (`decisions-first: enforce`): `check` fails a proposal that does
  not open with its decisions. Your agent also adds the rule to OpenSpec's
  `openspec/config.yaml`, so the agent drafting a proposal sees it.
- **No** (`decisions-first: off`): `check` stops looking for a decisions
  section.

Your agent shows you the changes before making them, then commits them. Once
they are committed, every agent on the team reads the same answer and none of
them asks again.

Until a repository decides, the question comes up at three moments:

- right after the agent writes a proposal, prompted by the proposal hook;
- when `check` runs, which adds one note saying the repository has not
  decided, and checks no proposal against the rule;
- when the commit hook reports an `openspec/` commit that lacks a valid
  `Spec-check:` trailer: the report tells you to "ask your agent to set up
  spec-check in this repository".

To do it yourself, run either command in the repository; `--dry-run` shows
what would change without writing it:

```bash
python3 ~/.agents/skills/spec-check/scripts/spec_check.py setup             # enforce the rule
python3 ~/.agents/skills/spec-check/scripts/spec_check.py setup --decline   # turn it off
```

Running either again changes nothing, and running one after the other
switches the answer. The script only records the answer; it never touches
OpenSpec's config. Adding the rule there, under `rules:` → `proposal:`, is
optional: it shows the rule to the agent drafting a proposal, and `check`
enforces the rule either way. SKILL.md, "Setting up a repository", has the
exact lines.

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

## The hooks

- **The commit hook.** After each shell command, it looks for new commits that
  change `openspec/` and reports any without a valid `Spec-check:` trailer. A
  commit that changes nothing under `openspec/` is never reported. Only
  `openspec/` at the repository root counts.
- **The proposal hook.** After the agent writes or edits an
  `openspec/changes/<name>/proposal.md`, in a repository that has not decided
  on the decisions-first rule, it tells the agent to ask you. Otherwise it
  says nothing. In Cursor it runs on `postToolUse` for the `Write` tool; the
  hook has not been tried in Cursor itself.

Neither hook ever blocks. To turn both off:

```bash
python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook spec-check
```

## Troubleshooting

- **`openspec validate --strict: not run`.** The `openspec` CLI is not on
  `PATH`. The other checks still ran; validation did not. A stacked change
  also gets a `stack` error, since its dependencies are archived with the
  same CLI.
- **A citation is reported missing, but the file exists.** The check reads
  the base branch (`origin/HEAD`, then `origin/main`, then `main`) and the
  change's own copy of the file (the working tree, the branch named with
  `--ref`, or the staged files when signing), and the file is in neither at
  that line. If the change
  targets another branch, pass `--base`.
- **The check says the proposal does not open with its decisions, but it
  does** (`decisions-first`). The section is under a heading that does not
  start with "Decisions". Pass `--decisions-heading "<your heading>"`.
- **The agent cannot make the trailer.** `spec_check.py sign`, which prints
  the `Spec-check:` line, refuses while errors remain, and prints them. For
  work in progress, the agent commits with `Spec-check: skipped (<reason>)`.
- **A `stack` error says the openspec CLI is not on PATH.** A change with a
  `Builds on:` line is checked by archiving its dependencies with
  `openspec archive`. Install OpenSpec (`npm install -g
  @fission-ai/openspec`) and run it again.
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
- **`check` says `openspec/spec-check.yaml` must hold one line.** Run
  `setup` or `setup --decline`, which rewrites it.
