## MODIFIED Requirements

### Requirement: The README warns that a relay's token can be printed

While linear-app hands a relay identity's token to a command that can
print it, the inquisitor's README SHALL say that any agent on the
person's machine can print that token and, unseen by the post hooks,
post a forged answer starting `User says: `. It SHALL give no such
warning for GitHub, since no github-app command hands a relay identity's
token to a program (github-app spec: *No github-app command hands a relay
identity's token to a program*).

#### Scenario: The README warns that a relay's token can be printed

- **WHEN** a test reads the README while a linear-app command, such as
  `token` or `headers`, can print a relay identity's token
- **THEN** it says, for Linear, that any agent on the person's machine
  can print that token and, unseen by the post hooks, post a forged
  answer starting `User says: `
- **AND** it gives no such warning for GitHub
