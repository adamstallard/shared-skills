---
name: spec-check
description: >-
  Check an OpenSpec change for correctness and consistency before a person
  reviews it, so the reviewer judges only whether the rules are the right
  ones. Use before committing or opening a pull request that adds or changes
  anything under openspec/changes/ or openspec/specs/, when reviewing a spec
  pull request, or when asked to "check this spec", "cross-check the change"
  or "is this spec consistent". Runs mechanical checks with a script, has a
  fresh subagent read the change against every other spec, change and open
  pull request, and fixes findings in the spec itself. Commits that change
  openspec/ carry a Spec-check: trailer.
---

# spec-check

**A spec reviewer should spend their time on whether the rules are right, not
on holding every other spec in mind.** This skill does the holding: a script
checks what is mechanical, and a fresh subagent reads the change against
everything it must agree with. Readability is the `prose` skill's job; linking
tests to scenarios after implementation is a separate step.

- **Why it works this way:** [DECISIONS.md](DECISIONS.md). Read it before
  changing this file or the script.
- `$SC` below is this skill's `scripts/` directory, as an absolute path.

## When

- Before any commit, and before opening a pull request, that changes a path
  under `openspec/changes/` or `openspec/specs/`.
- When reviewing a spec pull request, yours or someone else's.
- When asked to check a spec.

## 1. Mechanical checks

```sh
python3 "$SC/spec_check.py" check <change-name>        # one change, working tree
python3 "$SC/spec_check.py" check                      # every open change
python3 "$SC/spec_check.py" check specs                # openspec/specs
python3 "$SC/spec_check.py" check --ref origin/<branch> <change-name>   # a PR branch, no checkout
```

It reports `file:line: error|check [kind] message`, then the result of
`openspec validate --strict`, which it runs for you. Exit 0: no errors. Exit 1:
errors to fix. Exit 2: it could not run, and says why.

| Kind | Severity | What it means |
| --- | --- | --- |
| `no-scenario` | error | A requirement states a SHALL or MUST and has no scenario |
| `scenario-incomplete` | error | A scenario has no WHEN or no THEN |
| `duplicate` | error | A sentence of the rule also appears under another requirement, here or in another spec or change |
| `citation` | error | A `path:line` names a file missing on the base branch, or a line past its end. A name without a `/` is an error only with a common file extension; another missing bare name, such as `redis.cache:6379`, is a check. `0.0.0.0:8080` and `example.com:443` are skipped |
| `decisions-first` | error | The proposal does not open with a decisions section, or the section lists no decisions |
| `decision-alternative` | error | A decision names no alternative it rejects |
| `openspec-validate` | error, or check when validation passed | An issue `openspec validate --strict` reported |
| `undefined-term` | check | A backticked or bold term in a requirement appears nowhere in the specs or the change's proposal or design |

A **check** is a heuristic: judge it, and fix it or leave it. An `openspec
validate` result of "not run" means it was not checked, never that it passed;
say so in your report.

Citations are checked against the base branch: by default `origin/HEAD`, then
`origin/main`, then `main`. Pass `--base` when the change targets another
branch. Pass `--decisions-heading` (repeatable) when the repository names
the decisions section differently; the default matches any heading starting
with "Decisions".

## 2. The consistency read, by a fresh subagent

Start a subagent that did not write the change and give it
[consistency-read.md](consistency-read.md) as its brief, with its three
placeholders filled in: the change's directory, where to read it from (the
working tree, or the pull request's branch), and its base branch. Do not add your own summary of the
change: what you would say is what the read is checking.

The subagent reads the change against every spec on the base branch, every
open change, every open pull request touching the same specs, and the
repository's architecture docs, and reports findings with quotes from both
sides.

If no subagent can be started in this environment, do the read yourself from
the same brief, and say in your report and in the trailer (`--read self`)
that the author did it.

## 3. Fixing

- **Amend the spec itself.** Never answer a finding in a pull request comment:
  `gh pr view` shows the body without comments, and an implementer builds from
  the spec. Comment to think out loud; amend to decide.
- **A question only a person can decide** goes into the proposal's decisions
  section, under what is still open, as a marked open question.
- **A conflict with another change or pull request** is reported, not edited:
  name it, quote both sides, and leave the other change alone.
- **A fact nobody has measured** becomes a task in tasks.md and an open
  question, and the requirement built on it says what happens when it turns
  out false.

Run the mechanical checks again after amending.

## Decisions first

A proposal opens with the decisions the reviewer is asked to make, each with
the alternative it rejects; then what is still open; then everything else.

```markdown
## Decisions

1. **Records expire ninety days after their last read.** *Rejected:*
   keeping them forever, which grows the store without bound.

**Still open:**

- Whether archived records expire too.

## Why
...
```

`spec_check.py setup` adds this rule to the repository's
`openspec/config.yaml`, under `rules: proposal:`. OpenSpec shows config rules
to the agent drafting a proposal, inside `<rules>` in
`openspec instructions proposal`. The command edits the file as text, keeps
every comment, and changes nothing on a second run. `--dry-run` prints the
result instead.

## When to write a TLA+ model

Write one when a requirement is about concurrency, ordering, a crash between
two writes, or a protocol between processes. Other requirements do not get
one. This skill does not write models for you.

- **Where:** next to the spec, as
  `openspec/specs/<capability>/model/<Name>.tla` with `<Name>.cfg` for TLC.
- **Mapping:** each invariant's comment names the requirement it proves,
  by its exact `### Requirement:` title. A requirement the model cannot
  express says so in the spec.
- **CI:** run TLC on every model in the repository's CI:

  ```yaml
  - run: curl -sLO https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar
  - run: |
      for cfg in openspec/specs/*/model/*.cfg; do
        java -cp tla2tools.jar tlc2.TLC -workers auto -config "$cfg" "${cfg%.cfg}.tla" || exit 1
      done
  ```

## Commit

After the last fix and the final `git add`, and after the consistency read:

```sh
python3 "$SC/spec_check.py" sign --read subagent --amended <n> --open <n>
```

It runs the mechanical checks on the staged tree and refuses when any error
remains. Otherwise it prints `Spec-check: ✓ <tree> ...`, a value bound to the
staged tree. `--amended` is how many amendments the read led to; `--open` is
how many open questions the proposal now lists. For work in progress, skip
`sign` and write the value yourself: `skipped (<reason>)`.

Commit once, carrying every installed skill's trailer
([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
Pass the text after `Spec-check: ` as a `--verified-value` family. The
example goes through bug-hunter's commit script, `$BH`, with prose's scripts
directory as `$S`; bug-hunter's and prose's SKILL.md say where each is. After
the `--` come bug-hunter's own arguments: the message file, its `Bug-hunter:`
value, and the co-author.

```sh
"$BH" --verified-value "$S/verify-staged.sh" Prose "✓ 4d593e935186:9138830a72a2" \
      --verified-value "$SC/verify-staged.sh" Spec-check "✓ 4d593e935186 0 errors, 1 checks; validate passed; read by a fresh subagent; 3 amended, 1 open" -- \
  -F msg.txt "skipped at triage (spec only, no code)" "<co-author>"
```

Without bug-hunter, call the library directly with the same families:
`$SC/../../../lib/commit-trailer/commit-with-trailers.sh <families>
--co-authored-by "<co-author>" --message-file msg.txt --`.

Sign after prose's rewrite is staged: staging anything after signing changes
the tree, and the commit script refuses the stale value.

The hook reports a commit that changes `openspec/` without a valid
`Spec-check:` trailer. It never reports a commit that changes nothing under
`openspec/`.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec validate` result), who did the consistency read, the findings and
what each became (amended, open question, reported to another change), and
anything not checked.
