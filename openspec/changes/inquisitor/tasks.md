Gate two: these follow on this branch once Adam approves the spec.

## 0. Measure before building

Record each result in design.md, *What the hook relies on, not yet
measured*, or under *Configuration* for 0.4, including a result that
contradicts what design.md assumed.

- [ ] 0.1 A `PreToolUse` hook with matcher `AskUserQuestion` fires before the
      picker opens
- [ ] 0.2 Its exit 2 blocks the picker, and its stderr reaches the model
- [ ] 0.3 The hook's `tool_input` carries `questions[].question` and
      `questions[].options[].label`
- [ ] 0.4 `gh api repos/<owner>/<repo>/collaborators/<login>/permission` works
      for a caller without push access, or fails in a way the script can tell
      from "no access"

## 1. Shared post reader

- [ ] 1.1 Move prose's `gh` and GitHub MCP body reader into `.agents/lib/gh-post/`,
      called from a thin script in each skill, with no change in behaviour
- [ ] 1.2 prose's tests pass unchanged; add the library's own tests beside it

## 2. The script

- [ ] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first call):
      `--questions` and `--post`, printing the filters and filter 1's search
      results, issuing a token
- [ ] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
      verdicts and their fields, the refusals, and the records the hooks read
- [ ] 2.3 Filter 1's search over decision documents, issues through `gh`, both
      question logs and configured lore clones; the authority rules; each
      source not searched; each clone's last fetch
- [ ] 2.4 `log` and `miss`, writing one file per question or miss with a safe
      name and quoted frontmatter: in the repository's `.inquisitor/`, or
      under `~/.config/shared-skills/inquisitor/` for a public repository or
      none; `misses`, listing the misses by filter for a review
- [ ] 2.5 The question finder for posts, as one function the post hook also
      calls
- [ ] 2.6 `tag`, choosing whom a post's question tags
- [ ] 2.7 `lesson --check`, refusing a lesson for shared-skills that holds a
      logged question or miss; `lore`, opening a lore pull request or refusing
      it by visibility

## 3. Hooks

- [ ] 3.1 `scripts/check-ask.sh`: `PreToolUse` on `AskUserQuestion` (Claude Code
      only), checking verdicts and that each question's first option is its
      recommendation, blocking with exit 2 and failing open
- [ ] 3.2 `scripts/check-post.sh`: `PreToolUse` on Bash and the GitHub MCP tools,
      through `.agents/lib/gh-post/`
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 `scripts/test_inquisitor.py`, standard library only, each test tagged
      `@scenario inquisitor: <Scenario name>` for the scenario it checks
- [ ] 4.2 Every scenario has a tagged test: `spec_trace.py report
      --include-changes` lists no scenario of this change as `none`, its mark
      for a scenario with no tagged test. A scenario about what the agent
      does is tagged on a test that checks SKILL.md states the rule

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, preparing, batching and
      tagging, the order with prose, logging answers and misses, reviewing
      misses, and lessons by scope
- [ ] 5.2 `README.md`: what the skill is for, `inquisitor.json` and
      `.inquisitor/reviewers`, what to say to the agent, and troubleshooting a
      blocked picker or post
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`

## 6. Archive

- [ ] 6.1 Fold this change's lasting reasoning, from proposal.md and
      design.md, into a new `.agents/skills/inquisitor/DECISIONS.md`, and
      fold the reasoning for moving the post reader into prose's
      `DECISIONS.md`, as `AGENTS.md` says
