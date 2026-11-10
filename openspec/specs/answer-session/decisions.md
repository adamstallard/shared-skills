# answer-session: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: A reader takes a handled file at its word, with no proven writer, so anyone who can push to a lore repository's questions branch can close one of its questions so that the person never sees it.**
  Because: as elsewhere in the design, the hooks and github-app's refusals stop accidents, not a determined forger, and a forger here already has push access to the lore repository.
  Evidence: only the `log` command's handled option writes a handled file, and it does not check its caller (inquisitor spec: *Only an answer session writes a handled file*), adamstallard/shared-skills#25
  Holds while: only people the team trusts with its questions can push to the lore repository.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/

- **Constraint: The post hooks, on GitHub, Linear and Discord, and github-app's refusals for a relay identity guard against accidents, not against an agent set on forging a relayed answer, which can read a relay's credentials from the keychain and post with `curl`.**
  Because: the hooks stop an agent that uses the skills, as its instructions tell it, and one that works around them has its person's own tools and keychain.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Holds while: a relay identity's key sits where the person's own agents can read it.
  Paths: .agents/skills/inquisitor/scripts/check-post.sh, .agents/skills/github-app/, .agents/skills/linear-app/, .agents/skills/discord-bot/

- **Constraint: Until github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity, any agent on the person's machine can print a relay App's token and post `User says: ` with a plain HTTP call no post hook sees, and the README says so.**
  Because: the inquisitor asks github-app for those refusals and ships without them.
  Evidence: github-app's `token` command prints a raw token for programs, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md)
  Holds while: github-app hands a relay identity's token to a command.
  Paths: .agents/skills/github-app/, .agents/skills/inquisitor/README.md

- **Constraint: The session's model runs with the person's tools, so it can reach the keychain entry holding the person's own Linear key, and the answer session adds no guard against that.**
  Because: it is the same exposure as the person's `gh` login in any session, and the same exposure reaches the relay's credentials, as the constraint on forging a relayed answer says.
  Evidence: a Claude Code session's tools reach whatever the person's own commands can, https://docs.anthropic.com/en/docs/claude-code/security
  Holds while: the session's model runs with the person's tools.
  Paths: .agents/skills/inquisitor/

- **Constraint: Outside the Claude Code session running the answer session, nothing checks a reserved prefix on Linear or Discord, so a forged `User says: ` there marks its question answered in every answer session, and the skill's instructions are the only guard.**
  Because: filter 1 never counts a relayed answer on those surfaces as the person's, since it proves nothing there, so a forgery only takes the question out of the person's queue and never becomes an answer an agent acts on.
  Evidence: neither surface can vouch for a message's author to a GitHub login without a mapping no change provides (inquisitor spec: *An answer typed on another surface counts only through a decision document*), adamstallard/shared-skills#25
  Holds while: a relayed answer on Linear or Discord proves nothing to filter 1.
  Paths: .agents/skills/inquisitor/SKILL.md, .agents/skills/linear-app/, .agents/skills/discord-bot/

- **Constraint: A case between two machines of the same person whose worst outcome is a question shown twice or asked again gets no rule of its own.**
  Because: such a case costs the person only a second look, while a case that could record a wrong answer, close a question wrongly, leak private content or lose an answer is raised for a decision.
  Evidence: rules that matched a question's words, judgements or clocks across machines kept giving two machines different answers, and each fix raised another case, adamstallard/shared-skills#25
  Holds while: the person's machines share no state but the threads and the questions branches.
  Paths: .agents/skills/inquisitor/

- **Constraint: One question can get a citation from each of two machines, when it is open on both at once, or when a thread copy declined with nothing posted on one is declined again on another.**
  Because: the case is rare, so no rule prevents it; such a rule would re-read the questions branch before a decline's pushes, or push no citation for a reason 2 decline.
  Evidence: answer-session spec: *A filter 1 decline cites its lore entry once*, adamstallard/shared-skills#25
  Holds while: the person's machines share no state but the threads and the questions branches.
  Paths: .agents/skills/inquisitor/

- **Constraint: A close that cites a record, such as a filter 1 decline or a `Recorded answer: ` post, closes the question in the person's queue even when the asking agent's own filter 1 would not count that record.**
  Because: the answer session has given the person's answer, the record, in the thread, and if the asker cannot see or count the record and asks again, the new question reaches the person's queue like any other.
  Evidence: a record can be private, withheld by the visibility rules, or without authority (answer-session spec: *A handled file closes a questions-branch question*), adamstallard/shared-skills#25
  Holds while: the person's queue follows the answer session's reading of a record, not the asker's.
  Paths: .agents/skills/inquisitor/

- **Constraint: The answer session works on Claude Code's main screen too, but nothing is designed or built for that screen alone.**
  Because: `answer` opens it fullscreen, the layout it is designed for.
  Evidence: the approved prototype build v0.1-33 is a fullscreen layout, fc3c35f
  Holds while: the approved layout is the fullscreen one.
  Paths: .agents/skills/inquisitor/

- **Constraint: A copy of another of the person's answers, carrying their proof, a linked comment or verified signature, and pushed alone in its own commit, becomes a named file's answer.**
  Because: such a copy carries the person's proof as their own answer does, and the commit test guards only against a copy bundled with other files.
  Evidence: answer-session spec: *The person's answer to a named file is their own, added alone*, adamstallard/shared-skills#25
  Holds while: a named file's answer is proven by its writer's proof, not by its question.
  Paths: .agents/skills/inquisitor/

- **Constraint: An answer file pushed at once, because its channel is off or not read on this machine, gives up the comment link that would prove it on GitHub and counts only through its signature, and a dropped pending answer of that kind leaves its file on the branch, still answering the file it names.**
  Because: pushing at once keeps the answer when its thread cannot be reached, and a questions-branch file never changes once pushed.
  Evidence: answer-session spec: *An answer whose thread is unreachable here is logged at once*, adamstallard/shared-skills#25
  Holds while: an answer whose thread is unreachable here is logged at once.
  Paths: .agents/skills/inquisitor/

## Rejected

- **Rejected: Showing the log file's question beside the linked message's.**
  Facing: an answer to a linked message being recorded against a log file whose question the person never saw.
  Lost because: the answer file records the message's question as the person saw it, which leaves nothing for the file's question to add, adamstallard/shared-skills#25.
  Instead: the answer file records the linked message's question, as the person saw it.
  Paths: .agents/skills/inquisitor/

- **Rejected: A rule of its own for a lore repository made more public after `asked_in` was written, such as generalising the message's words or relaying only in the thread.**
  Facing: an answer file publishing a thread's question once its lore repository is made more visible than the thread.
  Lost because: the case barely arises, and making the repository public already publishes everything in it, adamstallard/shared-skills#25.
  Instead: `asked_in` is written only where the lore repository is no more visible than the thread, and nothing more.
  Paths: .agents/skills/inquisitor/

- **Rejected: Pending answers as a state in the list of questions answered and handled.**
  Facing: where the person sees answers that could not reach their thread.
  Lost because: how the lists look is prototyped, not specified, so a new state in the answered list would need a prototype round, which a separate list reusing the main queue's screens does not, adamstallard/shared-skills#25.
  Instead: a separate pending list that reuses the main queue's screens.
  Paths: .agents/skills/inquisitor/

- **Rejected: Separate decline reasons for a conversation that is over and a message that isn't a question.**
  Facing: how the person declines a message that needs no answer.
  Lost because: they behave alike, adamstallard/shared-skills#25.
  Instead: one reason, nothing to answer, beside the reason that the inquisitor should have handled it.
  Paths: .agents/skills/inquisitor/

- **Rejected: Calling filter 3's "the agent shouldn't have asked" option "not a question".**
  Facing: naming filter 3's option for a message the asking agent should not have written.
  Lost because: reason 1, "nothing to answer", is the one label for a message that is not a question, so that no two labels say the same thing, adamstallard/shared-skills#25.
  Instead: filter 3's option keeps its own words, "the agent shouldn't have asked".
  Paths: .agents/skills/inquisitor/

- **Rejected: Keeping the exception for screens designed at implementation only in this change, outside `AGENTS.md`.**
  Facing: where the rule that UI is prototyped, not specified, and its exception, are written.
  Lost because: the rule and its exception bind every change in the repository, and `AGENTS.md` is what each change's author reads, adamstallard/shared-skills#25.
  Instead: `AGENTS.md` states the rule and the exception.
  Paths: AGENTS.md

## Rationale

- **Rationale: The answer session polls GitHub's notifications and comments.**
  Notifications are what the answer session polls first, and polling them costs little while nothing changes: a conditional request that finds nothing new does not count against the rate limit, and GitHub's `X-Poll-Interval` header sets how long to wait. Task 0.15 checks that the endpoint behaves as documented.
  Evidence: GitHub's notifications API documents conditional requests and `X-Poll-Interval`, https://docs.github.com/en/rest/activity/notifications
