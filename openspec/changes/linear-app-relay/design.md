## Open Questions

- **Should anything stop an agent from posting `User says: ` through
  linear-app's `post` or `edit` as a marked relay?** Any agent can run
  those commands. On GitHub the inquisitor's post hook blocks an agent's
  post with that prefix; on Linear no hook reads one. The options:
  - Extend the post hook to read runs of `linear_app.py post` and `edit`.
    A hook sees only the command line, not standard input, so the
    commands would also have to take the text from a file named on the
    command line, for the hook to read.
  - Accept this route, as the change does now, and record it as a
    Constraint beside the route the answer-service decision record
    already accepts: an agent reading the relay's credentials from the
    keychain and posting with `curl`.

  A third option, `post` refusing the prefix itself, would not work: it
  cannot tell the answer service from an agent, since both run the same
  command as the same user.
