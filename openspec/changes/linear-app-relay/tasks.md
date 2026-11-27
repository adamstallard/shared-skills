## 1. linear-app

- [ ] 1.1 Read `relay` from an identity's config and report it in
      `check` (linear-app spec: *An identity's config marks it as a
      relay*)
- [ ] 1.2 Refuse `token`, `headers` and `wire` for a marked relay, and
      warn in `check` of an MCP server wired to one (linear-app spec: *No
      command prints a marked relay's token*; *A marked relay cannot be
      wired to the Linear MCP server*)
- [ ] 1.3 Read a marked relay's credentials only from the keychain,
      cache its token there, delete any token linear-app cached for it in
      its state folder, and delete the keychain's copy in `forget`
      (linear-app spec: *A marked relay's credentials and token stay in
      the keychain*)
- [ ] 1.4 Add `post`, `edit` and `delete` (linear-app spec: *post, edit
      and delete act as an identity without printing its token*; *A
      comment's text reaches Linear only as a GraphQL variable*)
- [ ] 1.5 Say in linear-app's SKILL.md and README what a marked relay
      is, how to mark one, and which commands it refuses

## 2. Answer service

- [ ] 2.1 Post, edit and delete on Linear through linear-app's `post`,
      `edit` and `delete` in place of the service's own request
      (answer-service spec: *A relay post is posted by a host command,
      unvetted*)
- [ ] 2.2 Fail setup's Linear relay check while linear-app reports
      `relay` as `false` (answer-service spec: *Setup checks each relay
      identity before its channels are used*)
- [ ] 2.3 Drop Linear from the inquisitor README's warning that a relay's
      token can be printed (answer-service spec: *The README warns that a
      relay's token can be printed*)

## 3. Tests

- [ ] 3.1 Tag each test with the scenario it checks (spec-trace)
