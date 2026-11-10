# spec-check benchmark

This benchmark measures what one spec-check run costs (tokens, wall time) and
what it catches. Rerun it before and after an edit to SKILL.md or
consistency-read.md, to check that a cheaper version still catches as much.
The skill never reads this folder.

A *version* is one copy of the skill directory, run under a name. The
`baseline` version is spec-check at shared-skills 798a4fd, before the reader
got its brief by path; its numbers are under *Results to compare against*. Each run is a real
`claude -p` session with one version installed. The task is "Check the
OpenSpec change staged in this repository before I review it. Fix what you
can in the spec files, don't commit, and report what you found." A grader, a
second `claude -p` call with no tools, then scores the session's final report
and diff against a rubric. The layout of runs and grades is the one the
skill-creator plugin (from the claude-plugins-official marketplace) uses, so
its viewer can show them.

## The cases

`build_cases.py` builds seven small git repositories. Each has the same three
base specs (session-store, notifications, audit-log) with their decision
records, and its own OpenSpec change staged on top. `rubrics.json` lists what
each run must report and what it must not.

| Case | Planted defect | Found by |
| --- | --- | --- |
| `contradiction` | A new requirement deletes audit entries at once, against audit-log's 90-day retention | the consistency read |
| `no-scenario` | The change adds a digest opt-out; its SHALL requirement that the opt-out takes effect within an hour has no scenario | the script |
| `record-no-evidence` | A Rationale entry added to a record with no Evidence line | the script: `spec_check.py sign` or `check specs` |
| `design-duplicates-record` | design.md repeats the Rejected entry on hosted newsletter services from notifications' decision record | the consistency read: item 15 of consistency-read.md's checklist |
| `rationale-title-mismatch` | A Rationale title that is not its requirement's exact title | the script: `spec_check.py sign` or `check specs` |
| `record-restates-requirement` | A Constraint entry in audit-log's decision record that restates the 90-day retention requirement | the consistency read: item 16 of the checklist |
| `clean` | none: nothing should be flagged | |

Each case also has must-not items: no commit, no invented evidence, and no
defect reported that the files do not have.

## Rerunning it

You need `claude` (Claude Code), `git`, Python 3.9 or later, and OpenSpec
1.16.1 or later on PATH. Everything uses the standard library; run it with
`python3 -I`. Pick a scratch directory outside `~/.claude/`, because Claude
Code refuses edits there. One version runs 14 times (seven cases, twice
each). At `baseline`'s 430k tokens a run, that is about 6M tokens and $8 at
list price. With the default of seven runs at a time, that is two rounds of
about 100 seconds each.

Run these from the repository root. They run today's skill as `current`,
and `baseline` from 798a4fd beside it:

```sh
B=.agents/skills/spec-check/bench
S=/tmp/spec-check-bench                    # scratch: any path outside ~/.claude/
python3 -I $B/build_cases.py $S/cases
mkdir -p $S/baseline && git archive 798a4fd .agents/skills/spec-check | tar -x -C $S/baseline
python3 -I $B/run_bench.py --cases $S/cases --work $S/runs \
    --iteration $S/results/iteration-1 --version current --skill .agents/skills/spec-check
python3 -I $B/run_bench.py --cases $S/cases --work $S/runs \
    --iteration $S/results/iteration-1 --version baseline \
    --skill $S/baseline/.agents/skills/spec-check
python3 -I $B/grade.py --work $S/grader $S/results/iteration-1
python3 -I $B/summarize.py $S/results/iteration-1
```

- **Each version** is one `run_bench.py` call into the same iteration, with
  its own `--version` and `--skill`. Run versions at the same time, in
  separate shells, so they see the same API load. Today's skill gives the
  reader its brief by path, as the `path` row below does, so compare
  `current` with `path`, and `baseline` with `baseline`.
- **The candidate variant:** `python3 -I $B/build_variants.py <skill-dir>
  <out-dir>` writes the `slim` version to `<out-dir>/slim`; pass that
  directory to `run_bench.py --skill`. It moves, word for word, the parts of
  SKILL.md that a review of a change doesn't use into a `reference.md`: the full findings table, archive
  refusals, stacked changes, most of *Commit*, keeping an evolution line,
  current-state passes and the TLA+ note. A run reads them there when it
  commits, hands back a pull request, or checks a stacked change. Its results
  are below.
- **To browse the outputs**, run `python3 -I $B/prep_viewer.py
  <iteration-dir>`. Then, from the skill-creator plugin's directory (under
  `~/.claude/plugins/` once it is installed), run `python3
  skills/skill-creator/eval-viewer/generate_review.py <iteration-dir>
  --static <file>.html`.
- **Resuming:** rerun the same command. `run_bench.py` skips finished runs
  and retries the rest, and `grade.py` skips graded ones.
- **A run that fails** (`claude -p` exits with an error, or passes
  `--timeout`, 3600 seconds by default) gets a `failed.txt` saying why.
  `summarize.py` lists it, and leaves it out of every column.
- **Stopping a batch:** press Ctrl-C, or close the terminal. Either signal
  reaches every running `claude -p`, which stops its own tools. The runs it
  cut short are left unfinished: `summarize.py` lists them with the failed
  runs, and the next call retries them. run_bench gets the Ctrl-C too, and
  takes no more runs from its queue. But a run it has already taken, and is
  still copying files for, has no `claude -p` yet for the signal to reach.
  It starts one afterwards, which runs at full cost. Runs are in that state
  for a second or two: at the start of a batch, and each time a run ends and
  the next one takes its slot. So press Ctrl-C again a few seconds after the
  first. With the queue already cancelled, nothing starts after that.
- **Don't stop it with `kill <pid>`.** A SIGTERM sent to run_bench's process
  alone stops only run_bench. Its `claude -p` processes keep running, and
  keep spending, until each finishes or reaches `--timeout`. To stop a batch
  from another shell, signal its whole process group: find the group with
  `ps -o pgid= -p <pid>`, then run `kill -INT -<pgid>`, twice a few seconds
  apart, as with Ctrl-C.
- **The harness's own tests** run with a fake `claude` and cost nothing:
  `python3 -I $B/test_bench.py`.

## Results to compare against

These were measured on 2026-11-09 with Claude Code 2.1.321, Opus 5.5
(`claude-opus-5-5`) and OpenSpec 1.16.0, by an earlier draft of these scripts
with the same cases, rubrics, task and grader prompt. The draft differed only
in how it recorded failed and ungraded runs, and none of its runs failed.
OpenSpec 1.16.1, which spec-check now requires, changes only how `openspec
archive` treats an unrecognized requirements section, which no case has. Each
version ran each case at least twice, except that `slim` has no runs of the
revised `clean` case (see below). Model and API behaviour drift, so for a
decision, rerun `baseline` beside the version you are testing rather than
comparing with this table alone.

- `baseline` is spec-check at shared-skills 798a4fd. In it, the main loop
  (the top-level `claude -p` session, as opposed to the reader subagent it
  starts) read consistency-read.md and often pasted it, condensed, into the
  reader's prompt.
- `path` is 798a4fd with SKILL.md's paragraph on starting the reader
  changed, so that the reader gets the brief's path and the values for its
  placeholders, and reads the brief itself. Today's SKILL.md gives the same
  instruction in slightly different words.
- `slim` is the variant above, built on 798a4fd. `slim-path` combines both.

| version | runs | tokens/run | main loop | reader | wall | cost/run | rubric | planted defects found |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 26 | 430k (sd 61k) | 330k | 69k | 101s | $0.590 | 75/88 (85%) | 24/24 |
| slim | 12 | 368k | 266k | 71k | 93s | $0.508 | 35/40 (88%) | 12/12 |
| path | 14 | 366k | 266k | 69k | 89s | $0.500 | 41/48 (85%) | 12/12 |
| slim-path | 26 | 337k (sd 42k) | 238k | 68k | 87s | $0.447 | 75/88 (85%) | 24/24 |

Tokens per run are the run's whole `modelUsage`: input, output and cache
tokens, main loop and reader together. The main loop and reader columns come
from the transcript instead, which records a little less, so they add up to
about 92% of the total. Every version catches every planted defect.

What to keep in mind when comparing:

- **The main loop is the cost, not the reader.** About three quarters of a
  run is the main loop, because each turn re-reads its context and SKILL.md
  is about 10k tokens of it. The reader costs the same in every version.
- **The rubric differences are noise.** All the misses are must-not items,
  mostly "no defect reported that the files do not have". Every version
  reports extra findings, such as a missing wrong-password
  scenario or an undefined "active session". The grader judges each one on
  its own, and its rulings vary from run to run, so a version's total moves
  by a few points between iterations.
- **One must-not item may be wrong.** In `no-scenario`, a run that says the
  digest opt-out conflicts with "Daily digest", a requirement in the base
  notifications spec, fails a must-not item. But the digest's scenario does
  promise every user a digest, so the finding is arguably real. Most of the misses by `slim`, `path` and `slim-path` on that
  case are this item.
- **The `clean` case was fixed after the first runs.** Its first version had
  a real gap: the requirement did not say non-admins are refused, though a
  scenario tested it. The table leaves out the six runs made on it, two each
  of `baseline`, `slim` and `slim-path`.
- **Only the review task is measured.** No run commits or hands back a pull
  request, so no run needed `reference.md`. Check a commit flow before
  adopting `slim`.
- **At 798a4fd the script missed two record errors.** `check <change>` did
  not report the record errors that `record-no-evidence` and
  `rationale-title-mismatch` plant; `sign` and `check specs` did. Every run
  caught them anyway, because every run also ran `sign` or `check specs`.
  Runs in every version called the script three or four times each, so the
  cost is in every row alike. A script that reports them from `check
  <change>` may lower every version's cost, so compare runs made with the
  same script.
