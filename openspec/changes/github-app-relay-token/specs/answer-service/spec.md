## MODIFIED Requirements

### Requirement: The README warns that a relay's token can be printed

While linear-app hands a relay identity's token to a command that can
print it, the inquisitor's README SHALL say that any agent on the
person's machine can print that token and post `User says: ` unseen by
the post hooks. No github-app command hands out a relay identity's token
(github-app spec: *No github-app command hands a relay identity's token
to a program*), so the README gives no such warning for GitHub.

#### Scenario: The README warns that a relay's token can be printed

- **WHEN** a test reads the README while a linear-app command, such as
  `token` or `headers`, can print a relay identity's token
- **THEN** it says, for Linear, that any agent on the person's machine
  can print that token and post `User says: ` unseen by the post hooks
- **AND** it gives no such warning for GitHub
