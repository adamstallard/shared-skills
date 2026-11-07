# Working in this repository

- **New work goes through OpenSpec.** Write a change under
  `openspec/changes/` and open a pull request holding only its
  specification. Build the implementation on the same branch once the
  repository's owner approves that pull request's specification.
- **UI is the exception: it is prototyped, not specified.** Build a
  prototype for the owner to use. Once they approve it, build the UI
  directly in an implementation pull request, with no specification pull
  request for it. One exception: a screen may be built without a
  prototype of its own when a spec's task says it is designed at
  implementation from the patterns of that feature's approved prototype.
  The spec still does not describe the screen; its task only names it. The rest of the same feature (data flow, integrations,
  setup, rules) still goes through its own specification pull request
  first.
- **A capability's decision record, or a skill's `DECISIONS.md`, is its
  current reasoning in one place, not a log.** A capability is what one
  spec, `openspec/specs/<capability>/spec.md`, specifies, such as a skill
  or part of one. A rejected alternative that a test can check becomes a
  requirement in that spec, with a scenario the alternative would fail,
  and so does a constraint, with a scenario that breaking it would fail.
  The capability keeps the alternatives and constraints no test can check
  in `openspec/specs/<capability>/decisions.md`, one entry each, with its
  reason, evidence and the paths it governs, in the form shared-skills
  issue #56 sets. A skill with no spec keeps its reasoning in its
  `DECISIONS.md`. While a
  change is open, its reasoning lives in its proposal and `design.md`, and
  the constraints and rejected alternatives it adds live in
  `openspec/changes/<change>/specs/<capability>/decisions.md`, in issue
  #56's form. When the change is archived, spec-check folds those records
  into each capability's decision record, and the author folds the rest of
  the reasoning a later reader still needs into each affected capability's
  record, or into the
  `DECISIONS.md` of each skill without a spec that it affects. Where that reasoning
  replaces older reasoning in the file, rewrite the older reasoning rather
  than appending.
- **Tests tag the OpenSpec scenario they check** with
  `@scenario <capability>: <Scenario name>`; see the spec-trace skill.
