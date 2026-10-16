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

Until a repository decides, the agent raises it at three moments:

- right after it writes a proposal, prompted by the proposal hook;
- when `check` runs, which adds one note saying the repository has not
  decided, and checks no proposal against the rule;
- when the commit hook reports an `openspec/` commit, whose report ends with
  "ask your agent to set up spec-check in this repository".

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
  `PATH`. The other checks still ran; validation did not.
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
- **`check` says `openspec/spec-check.yaml` must hold one line.** Run
  `setup` or `setup --decline`, which rewrites it.
