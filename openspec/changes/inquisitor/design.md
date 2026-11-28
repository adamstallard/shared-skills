## Open Questions

In the first two lists of facts below, the task each bullet names measures its fact before
anything resting on it is built, and the bullet says what the software
does if the measurement finds that the fact does not hold.

### Facts measured before building

- **Can a headless session that is not an Igor worker post?** (task 0.9)
  If it cannot, or the script cannot tell, that session counts as unable
  to post and asks nowhere. Task 0.9 also checks that igor sets
  `IGOR_RUN`, by which the script tells an Igor's run, as igor PR #216
  specifies, once igor builds that marker.
- **Can the agent open, and write in, a repository's private security
  advisory?** (task 0.10) That needs private vulnerability reporting enabled,
  or an admin or security-manager role. If not, an agent asking a
  vulnerability question records the question and its answer nowhere. It
  uses the answer only in the code of the fix that repairs the
  vulnerability, and tells the person only that a vulnerability question
  is blocking, without the question's text.
- **Can an advisory's private-fork pull request merge before the advisory
  is published?** (task 0.13) While unmeasured, or if it can, the agent
  commits the regression test to the advisory's private fork, and
  describes the weakness there, only on the word of the advisory's
  publisher. If the fork merges only at publication, the agent does so
  without that word.
- **Does an Igor's host have Python and this skill for the Igor's own
  process?** (task 0.29) If not, the Igor's `branch-search` call for its
  worker fails, and the worker's search names the questions branches it
  would have read as not searched.
- **Can an Igor worker pass the question to `igor lore-search` on that
  command's standard input?** (task 0.40) If not, the worker's inquisitor script passes the question the way igor PR #216 gives
  instead, and *The question reaches igor's command on standard input*
  changes to that way. Either way, a call that fails leaves filter 1 in an
  Igor's run searching no lore and saying so.

### Facts the answer service relies on

- **Can the answer service work on Linear?** (task 0.16) If any part of
  the task fails, Linear stays off and the README says so. An
  assignment is dated by when a poll first finds it; if the person's key
  can read when an issue was assigned, that time dates it instead.
- **Can the Linear relay comment in a private team it can see?** (task
  0.44) If not, setup's posting check passes for that team, but each
  relay post there is refused for lack of permission, which turns the
  team off until the next opening. The answer waits on the pending list,
  goes back to the queue each time the check passes, and is refused again
  whenever the person confirms it, until the person drops it.
- **Can the answer mod tell a judging turn from the person's?** (task
  0.45) If a prompt the person submits while a judging turn runs can join
  that turn, the mod refuses every `record_verdict` call made after such a
  prompt until the turn ends, and the message the refused call names
  awaits judgement again.
- **Can the answer service work on Discord?** (task 0.17) If any part of
  the task fails, Discord stays off and the README says so.
- **Do the URL `gh pr comment` prints and an Igor's handback URL equal
  the URL the answer service builds?** (task 0.23) If not, the side
  that records the URL and the answer service both write and compare
  one canonical form.
- **How does each surface report a refused post?** (task 0.25) A refusal
  the answer service cannot place counts as refused for its text, so the
  answer waits for the person.
- **Do the person-required and concerns lines come back unchanged from
  Linear and Discord?** (task 0.28) If not, the answer service matches the
  form each surface returns.
- **Can the person's Linear key read Linear's GitHub-integration links?**
  (task 0.35) If not, setup's guess for a Linear team names nothing, and
  setup asks the person.
- **Which GitHub App or Linear app user is an Igor's?** (task 0.38) If
  nothing the person can read tells an Igor's identity from any other App
  or app user, no
  comment is a handback, and the README says so.

### Values an igor change sets

Each rule resting on one of these states what holds once igor's change
lands, with no fallback before it, as each capability's decision record's
Constraint on rules that depend on igor says. Its task records the value
before the rule is built.

- **What form does igor's handback marker take, and which igor change
  defines it?** (task 0.6) igor issue #211 names the marker, but no igor
  pull request, #216 included, defines it. This repository's owner
  decides which igor change will. The answer service's *A handback is an
  Igor's comment holding igor's marker* is built from the form that change
  defines, and not before.
- **At what path does igor's scribe write its decision records?** (task
  7.0) igor PR #202 sets the path. Filter 1's search of the scribe's
  records, in the repository a question concerns and in the lore
  repository, is built for that path, and this change archives only once
  it is set.
