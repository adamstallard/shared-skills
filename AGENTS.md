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
- **A capability's decision record holds the capability's current
  reasoning in one place, not a log.** A capability is what one
  spec, `openspec/specs/<capability>/spec.md`, specifies, such as a skill
  or part of one. A rejected alternative that a test can check becomes a
  requirement in that spec, with a scenario the alternative would fail,
  and so does a constraint, with a scenario that breaking it would fail.
  The capability's decision record,
  `openspec/specs/<capability>/decisions.md`, holds only what no test can
  check, each entry with its evidence, in the form spec-check's `SKILL.md`
  sets. A pull request edits that record directly, beside the spec files
  its change adds or edits under `openspec/changes/<change>/specs/`; a
  change holds no record of its own. A skill with no spec keeps in
  its `SKILL.md` everything an agent needs to act on it, the reasons
  included. Where new reasoning replaces older
  reasoning in a record, rewrite the older reasoning rather than
  appending.
- **Tests tag the OpenSpec scenario they check** with
  `@scenario <capability>: <Scenario name>`; see the spec-trace skill.
