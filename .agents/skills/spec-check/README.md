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
   - a proposal that does not open with its decisions;
   - terms nothing defines (a hint only, never a failure).

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
turns on its hook (see below).

Then, once per repository, add the decisions-first rule to OpenSpec's config
so the agent drafting a proposal sees it:

```bash
python3 ~/.agents/skills/spec-check/scripts/spec_check.py setup
```

This adds the rule under `rules: proposal:` in `openspec/config.yaml`,
keeping every comment. Running it again changes nothing. Use `--dry-run` to
see the result first. OpenSpec prints config rules to the agent in
`openspec instructions proposal`.

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

After each shell command, the hook looks for new commits that change
`openspec/` and reports any without a valid `Spec-check:` trailer. It reports
and never blocks, and a commit that changes nothing under `openspec/` is never
reported. Only `openspec/` at the repository root counts.

To turn it off:

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
- **`setup` refuses.** Your config writes `rules` or `proposal` in flow style
  (`proposal: [...]`). Add the rule by hand.
