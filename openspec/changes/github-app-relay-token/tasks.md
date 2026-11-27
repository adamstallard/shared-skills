## 1. github-app

- [ ] 1.1 Relay identities read from `inquisitor.json`, by name and App ID
      (github-app spec: *Every identity of the answer service's GitHub
      relay App is a relay identity*)
- [ ] 1.2 The refusals (github-app spec: *No github-app command hands a
      relay identity's token to a program*)
- [ ] 1.3 The `api` command (github-app spec: *The api command makes a
      GitHub request with the installation token and prints only the
      response*; *The api command accepts only gh api's method, field and
      input options*)
- [ ] 1.4 github-app's SKILL.md and README: which commands a relay
      identity can run (github-app spec: *No github-app command hands a
      relay identity's token to a program*), and `api`'s options

## 2. Inquisitor

- [ ] 2.1 The shared post reader reads `api` calls (gh-post spec: *The
      reader reads the github-app skill's api command as gh api*)
- [ ] 2.2 The answer service makes every GitHub request as the relay
      through `api`: its relay posts, edits and deletes, each passing its
      text on standard input, and its setup's read of the relay
      installation's access to each subscribed repository
      (`installation/repositories`)
- [ ] 2.3 The inquisitor's README drops its GitHub warning
      (answer-service spec: *The README warns that a relay's token can be
      printed*)

## 3. Tests

- [ ] 3.1 Each test names the scenario it checks with an
      `@scenario <capability>: <Scenario name>` tag (spec-trace skill)
