# github-app: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: The refusals for relay identities guard against accidents, not against an agent that reads a relay identity's key file or token cache and posts with `curl`.**
  Because: both files belong to the person's operating-system account, which the person's agents run as, and an agent has to set out to read them, as it would to forge a relayed answer.
  Evidence: github-app keeps each identity's private key by default at `~/.config/github-app/<identity>.pem` and its cached token at `~/.local/state/github-app/<identity>.json`, both mode 0600, [github_app.py](../../../.agents/skills/github-app/scripts/github_app.py)
  Holds while: a relay identity's key and token cache are files the person's user can read.
  Paths: .agents/skills/github-app/scripts/github_app.py

## Rationale

- **Rationale: Every identity of the answer service's GitHub relay App is a relay identity.**
  Each person's answer service counts a post as their relay's by the bot that made it, and every installation of one App posts as the same bot, so a second identity storing the relay's App for another account would hand out a token that posts as the relay. github-app's own instructions tell an agent to store the App under a new identity to add another account.
  Evidence: an App's work shows as `<app-slug>[bot]`, and the App is added for another account under a new `--identity`, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md); a request with an installation token is attributed to the App, https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation

- **Rationale: No github-app command hands a relay identity's token to a program.**
  `token` prints the token, and `run` hands it to any program in `GH_TOKEN`. `gh` and `git` cannot be kept working for a relay identity without the token reaching a command that prints it: gh prints the token it uses, and git hands an agent whatever its credential helper returns. So `token`, `gh`, `run` and the helper's `get` refuse. `wire` and `env` only set git up to call the helper, and refuse too, so a relay identity fails when it is set up rather than at its first push. Posting goes through `api` instead.
  Evidence: with `GH_TOKEN` set, gh 2.103.2 printed the token through `gh auth token` and through a gh alias running `echo "$GH_TOKEN"` (measured 2026-11-20), adamstallard/shared-skills#96; `gh auth token` prints the token gh uses for a host, https://cli.github.com/manual/gh_auth_token; `git credential fill` prints the credential its helpers return, https://git-scm.com/docs/git-credential
