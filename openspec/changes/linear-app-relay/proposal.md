# Linear relay identities

Builds on: inquisitor (adamstallard/shared-skills#25)

## Why

The inquisitor's answer service posts a person's answers on Linear as their
relay identity, a linear-app identity. linear-app's `token` and `headers`
commands print that identity's token to any caller. With it, any agent
on the machine can post as the relay a comment starting `User says: `,
which the answer service reads as the person's own answer, with a plain
HTTP call (shared-skills issue #112).

## What Changes

- linear-app marks relay identities, refuses to print their tokens, keeps
  their tokens out of files, and gains `post`, `edit` and `delete`
  commands, which the answer service uses on Linear in place of its own
  HTTP request.
