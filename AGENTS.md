# Working in this repository

- **New work goes through OpenSpec.** Write a change under
  `openspec/changes/` and open a pull request holding only its
  specification. Build it on the same branch once the repository's owner
  approves that pull request's specification. Run the spec-check skill
  before committing anything under `openspec/`.
- **A skill's `DECISIONS.md` is its current reasoning in one place, not a
  log.** While a change is open, its reasoning lives in its proposal and
  `design.md`. When the change is archived, fold its lasting reasoning into
  the `DECISIONS.md` of each skill it affects. Where that reasoning replaces
  older reasoning in the file, rewrite the older reasoning rather than
  appending.
- **Tests tag the OpenSpec scenario they check** with
  `@scenario <capability>: <Scenario name>`; see the spec-trace skill.
