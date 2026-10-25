# Working in this repository

- **New work goes through OpenSpec.** Write a change under
  `openspec/changes/` and open a pull request holding only its
  specification. Build it on the same branch once the repository's owner
  approves that pull request's specification. Run the spec-check skill
  before committing anything under `openspec/`.
- **UI is the exception: it is prototyped, not specified.** Build a
  prototype for the owner to use. Once they approve it, build the UI
  directly in an implementation pull request, with no specification pull
  request for it. One exception: a screen may be built without a
  prototype of its own when a spec's task says it is designed at
  implementation from the patterns of that feature's approved prototype.
  The spec still does not describe the screen; its task only names it. The rest of the same feature (data flow, integrations,
  setup, rules) still goes through its own specification pull request
  first.
- **A skill's `DECISIONS.md` is its current reasoning in one place, not a
  log.** While a change is open, its reasoning lives in its proposal and
  `design.md`. When the change is archived, fold its lasting reasoning into
  the `DECISIONS.md` of each skill it affects. Where that reasoning replaces
  older reasoning in the file, rewrite the older reasoning rather than
  appending.
- **Tests tag the OpenSpec scenario they check** with
  `@scenario <capability>: <Scenario name>`; see the spec-trace skill.
