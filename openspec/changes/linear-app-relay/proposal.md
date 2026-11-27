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

- The identity the inquisitor's configuration names as its Linear relay
  is a relay identity: linear-app refuses to print its token and keeps
  that token in the keychain, out of linear-app's state folder.
  linear-app also gains `post`, `edit` and `delete` commands, which the
  answer service uses on Linear in place of its own HTTP request. The
  inquisitor's post hook reads the text of a `post` or `edit` an agent
  runs as a tool call, so it blocks one starting `User says: `; the
  answer service's own runs are host commands, which no hook sees.
