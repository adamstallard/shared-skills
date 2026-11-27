# github-app: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: github-app's refusals of a relay identity's token commands (*No github-app command hands a relay identity's token to a program*) guard against accidents, not against an agent that reads a relay identity's key file, token cache or `GITHUB_APP_PRIVATE_KEY` and posts with `curl`; the token cache stays readable to the person's agents.**
  Because: the private key beside the token cache mints tokens, and both belong to the person's operating-system account, which the person's agents run as, so making the cache unreadable alone would stop no forger.
  Evidence: github-app keeps each identity's private key by default at `~/.config/github-app/<identity>.pem` and its cached token at `~/.local/state/github-app/<identity>.json`, both mode 0600, or reads the key from `GITHUB_APP_PRIVATE_KEY` in the environment, [github_app.py](../../../.agents/skills/github-app/scripts/github_app.py)
  Holds while: a relay identity's key and token cache are files the person's user can read, or its key is in the environment of the person's agents.
  Paths: .agents/skills/github-app/scripts/github_app.py

## Rationale

- **Rationale: Every identity of the answer service's GitHub relay App is a relay identity.**
  Each person's answer service counts a post as their relay's by the bot that made it, and every installation of one App posts as the same bot, so a second identity storing the relay's App for another account would hand out a token that posts as the relay. github-app's own instructions tell an agent to store the App under a new identity to add another account.
  Evidence: an App's work shows as `<app-slug>[bot]`, and the App is added for another account under a new `--identity`, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md); a request with an installation token is attributed to the App, https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation

- **Rationale: No github-app command hands a relay identity's token to a program.**
  `token` prints the token, and `run` hands it to any program in `GH_TOKEN`. `gh` and `git` cannot be kept working for a relay identity without the token reaching a command that prints it: gh prints the token it uses, and git hands an agent whatever its credential helper returns. So `token`, `gh`, `run` and the helper's `get` refuse. `wire` and `env` only set git up to call the helper, and refuse too, so a relay identity fails when it is set up rather than at its first push. Posting goes through `api` instead.
  Evidence: with `GH_TOKEN` set, gh 2.103.2 printed the token through `gh auth token` and through a gh alias running `echo "$GH_TOKEN"` (measured 2026-11-20), adamstallard/shared-skills#96; `gh auth token` prints the token gh uses for a host, https://cli.github.com/manual/gh_auth_token; `git credential fill` prints the credential its helpers return, https://git-scm.com/docs/git-credential

- **Rationale: The api command makes a GitHub request with the installation token and prints only the response.**
  `api` signs each request with the installation token and never with the App's key, so even a relay identity's `api` call cannot mint a new token that it would then print.
  Evidence: GitHub's endpoint that creates an installation access token says "You must use a JWT to access this endpoint", https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app

- **Rationale: The api command accepts only gh api's method, field and input options.**
  The inquisitor's post hook blocks an agent's post that starts with a prefix reserved for the answer service, and reads an `api` call as the `gh api` call with the same words (gh-post spec: *The reader reads the github-app skill's api command as gh api*), so `api` must send what gh would send for those words. gh fills `{owner}`, `{repo}` and `{branch}`, and the colon forms `:owner`, `:repo` and `:branch`, from the local repository in the endpoint and in a `-F` value typed in the command, but not in a `-f` value, a `-F` value read from a file with `@`, or an `--input` body. `api` fills no placeholder, so it refuses one wherever gh would fill it and sends the rest as written, as gh does. It also refuses an endpoint naming a host, and gh's `--hostname`, either of which would send the installation token to a host other than `api.github.com`, handing it to whoever runs that host.
  Evidence: gh's `fillPlaceholders` runs on the endpoint and, through `magicFieldValue`, on each `-F` value not starting with `@`, https://github.com/cli/cli/blob/aec38089147ae38264668843fa6126022c56a0e4/pkg/cmd/api/api.go#L582-L622 and https://github.com/cli/cli/blob/aec38089147ae38264668843fa6126022c56a0e4/pkg/cmd/api/fields.go#L160-L183; `--hostname` sets the host gh sends a request to, https://cli.github.com/manual/gh_api
