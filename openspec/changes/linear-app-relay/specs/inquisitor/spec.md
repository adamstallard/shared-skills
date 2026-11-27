## ADDED Requirements

### Requirement: The post hook skips its GitHub-only rule for a Linear post

The post hook SHALL treat a comment an agent sends with linear-app's
`post` or `edit` as a post, which the shared post reader reports as going
to Linear. For such a post it SHALL skip the one rule the inquisitor spec
limits to a GitHub post, the check that a question a skill requires a
person to decide carries that skill's person-required line (*The second call checks a
requiring skill, and the post hook its line*), and apply every other
rule as to a GitHub post.

#### Scenario: A Linear post skips the GitHub-only check but not the rest

- **WHEN** an agent runs linear-app's `post` with a file holding a
  question whose verdict record, which the inquisitor's second call
  writes when it vets the question, names spec-trace as the skill that requires a
  person to decide it, without spec-trace's person-required line
- **THEN** the post hook does not block it for the missing line
- **AND** it blocks a post like it whose question has no `ask` verdict,
  the second call's finding that it must be asked, from the last 2 hours, or when the text starts `User says: `
