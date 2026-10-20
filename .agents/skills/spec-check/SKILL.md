---
name: spec-check
description: >-
  Check an OpenSpec change for correctness and consistency before a person
  reviews it, so the reviewer judges only whether the rules are the right
  ones. Use when drafting or reviewing an OpenSpec change, before committing
  or opening a pull request that adds or changes anything under
  openspec/changes/ or openspec/specs/, when reviewing a spec pull request,
  when asked to set up spec-check for a repository, or when asked to "check
  this spec", "cross-check the change" or "is this spec consistent". Runs mechanical checks with a script, has a
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

- When drafting a proposal in a repository that has not decided on the
  decisions-first rule: see [Setting up a repository](#setting-up-a-repository).
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
| `citation` | error, or check | A `path:line` with a `/` whose line is in neither the base branch nor the change is an error. Any other citation finding is a check: a bare name such as `config.py:50`, or a line only the change adds. Text in a code fence, and addresses such as `0.0.0.0:8080`, are skipped |
| `decisions-first` | error, or check, as `openspec/spec-check.yaml` says | `enforce`: an error when the proposal does not open with a decisions section, or the section lists none. `off`: not checked. No file: no proposal is checked, and one check says the repository has not decided. A file holding anything else: one check naming the problem |
| `openspec-validate` | error, or check when validation passed | An issue `openspec validate --strict` reported |

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

A proposal opens, right after its title, with a `## Decisions` section. It
lists each decision the reviewer is asked to approve as a numbered item, then
a bold **Still open:** label followed by the questions the change leaves for
later, or 'none'. The rest of OpenSpec's proposal template follows. Every
proposal lists at least one decision. When the requirements are the only
thing a change decides, its one decision is to adopt them.

Where a decision turned down an alternative that was really considered, the
same item says so after *Rejected:*, with why it lost. Do not make up a
rejected alternative for a decision that had none: a made-up one only adds to
the reader's work.

`check` tests only the start of the proposal. It fails a proposal whose first
heading after the title does not start with "Decisions", or whose decisions
section lists no decision as an item; a bulleted item counts as well as a
numbered one. `check` does not look for the **Still open:** line, so a
proposal that leaves it out still passes `check`; the reviewer catches the
missing line and judges everything else. Write the line anyway, with 'none'
when nothing is open.

```markdown
# Expire old records

## Decisions

1. Records expire ninety days after their last read. *Rejected:* keeping
   them forever, because the store would grow without bound.
2. The purge runs nightly.

**Still open:** whether archived records expire too.

## Why
...
```

Each repository decides whether its proposals must follow this rule, and
`openspec/spec-check.yaml` records the answer.

## Setting up a repository

`openspec/spec-check.yaml` holds one line, written only by `setup`:

- **`decisions-first: enforce`:** `check` fails a proposal that does not
  open with its decisions.
- **`decisions-first: off`:** `check` does not look for a decisions section.
- **No file:** the repository has not decided. `check` reports no
  `decisions-first` errors, and adds one check saying so.

Anything else in the file, or a link, a directory or a submodule in its
place, gets one check naming the problem, and decisions-first is not
checked. `sign` and `check --ref` read the file from the git tree and never
follow a link.

Ask the user whether to enforce the rule when any of these happens:

- `check` reports that the repository has not decided;
- after you write a proposal, the hook tells you the repository has not decided;
- the user asks you to set up spec-check for a repository.

Then:

1. Show the user what will change: `python3 "$SC/spec_check.py" setup
   --dry-run`, or `setup --decline --dry-run`.
2. Run the same command without `--dry-run`. `setup` writes `enforce`, and
   `setup --decline` writes `off`. Running either again changes nothing, and
   running one after the other switches the value. Pass `--repo <dir>` for
   another repository.
3. **If the user chose to enforce the rule,** add it to OpenSpec's config
   yourself, with your own edit tools, so that `openspec instructions
   proposal` shows it to the agent drafting a proposal. The script never
   touches OpenSpec's config.
   - The file is `openspec/config.yaml`, or `openspec/config.yml` if that is
     the one present. If neither exists, create `openspec/config.yaml`
     holding the lines below.
   - Put the comment below just above `rules:`, and the rule as an item of
     the list under `rules:` → `proposal:`. Use the existing keys; create
     `rules:` or `proposal:` only where they are missing. Keep every other
     comment.
   - Show the user the change before committing it.
   - If you cannot edit the file, tell the user the exact lines and where
     they go, and say that this step is optional: agents drafting a
     proposal will not see the rule, but `check` still enforces it.

   Copy the comment's words and the rule's text exactly as they are below,
   because every repository's agents should read the same rule, and copies
   reworded by hand drift apart.

   ```yaml
   # spec-check checks the start of a proposal against the rule below: its first
   # heading after the title must start with "Decisions", and that section must
   # list at least one decision. The check runs only while
   # openspec/spec-check.yaml sets `decisions-first: enforce`, as this
   # repository's does. With `decisions-first: off`, or with no spec-check.yaml,
   # no proposal is checked against the rule. The spec-check skill tells an agent
   # to run its check command, `spec_check.py check`, before committing a change
   # under openspec/, and that command fails a proposal that breaks the rule. The
   # rule repeats what is checked, because the agent drafting a proposal sees the
   # rule but not this comment.
   rules:
     proposal:
       - |
         Open the proposal, right after its title (its `#` heading), like this:
         ## Decisions
         1. <a decision you ask the reviewer to approve>
         2. <another decision> *Rejected:* <an alternative you actually considered>, because <why it lost>.
         **Still open:** <the questions this change leaves for later, or 'none'>
         Then the rest of OpenSpec's proposal template (Why, What Changes, and so on).
         List at least one decision. When the change makes no choice beyond its requirements (no mechanism picked, no alternative turned down), its one decision is to adopt those requirements, written as an item such as "1. Adopt this change's requirements." Add *Rejected:* only where you really considered an alternative; never invent one. Always write the **Still open:** line, with 'none' when nothing is open. In this repository, spec-check fails the proposal in only two cases: its first heading after the title does not start with 'Decisions' (a heading such as '## Decisions made' passes), or that section has no numbered or bulleted item, since a decision written as a plain paragraph does not count. The reviewer judges everything else in the proposal, including the **Still open:** line.
   ```
4. **If the user turned the rule off,** look at OpenSpec's config. Only if
   the rule is there, tell the user, and ask whether to remove it.
5. Commit the files that changed, on their own. There was no consistency
   read, so sign with `sign --read self`: for a commit that changes nothing
   else under `openspec/`, it prints `Spec-check: ✓ <tree> no open change or
   spec staged`. Pass that value like any other (see [Commit](#commit)).

Once that commit lands, every agent working in the repository reads the same
answer and stops asking.

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

The commit hook reports a commit that changes `openspec/` without a valid
`Spec-check:` trailer. It never reports a commit that changes nothing under
`openspec/`. In a repository with no `openspec/spec-check.yaml`, its report
adds a line telling the user to ask you to set up spec-check.

## Report

Say, in this order: the mechanical result (errors fixed, checks judged, the
`openspec validate` result), who did the consistency read, the findings and
what each became (amended, open question, reported to another change), and
anything not checked.
