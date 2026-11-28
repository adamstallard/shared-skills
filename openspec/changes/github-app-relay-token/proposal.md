# github-app relay token

Builds on: inquisitor (adamstallard/shared-skills#25)

## Why

An agent holding the GitHub relay identity's token can use a plain HTTP
call, which no post hook sees, to post as the relay's bot a reply
starting `User says: `. The person's answer services take such a reply as
the person's answer. github-app hands that token to commands that print
it (shared-skills issue #96).

## What Changes

- github-app refuses every command that would hand a relay identity's
  token to a program that can print it. A new `api` command posts, edits
  and deletes as the relay without handing out the token. The answer
  service uses it, and an agent may too: the inquisitor's post hook reads
  each `api` call as `gh api`, so it blocks an agent's `api` post that
  starts with a prefix reserved for the answer service, such as
  `User says: `.
