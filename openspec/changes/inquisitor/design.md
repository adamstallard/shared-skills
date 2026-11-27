## Open Questions

In both lists below, the task each bullet names measures its fact before
anything resting on it is built, and the bullet says what the software
does if the fact does not hold.

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
- **Can the Igor run `branch-search` and read a collaborator's
  permission?** (task 0.29) Without the first, the call fails and the
  worker's search names each questions branch as not searched; without
  the second, every hit is `input`.
- **Can an Igor worker pass the question to `igor lore-search` on that
  command's standard input?** (task 0.40) If not, the worker's inquisitor script passes the question the way igor PR #216 gives
  instead, and *The question reaches igor's command on standard input*
  changes to that way. Either way, a call that fails leaves filter 1 in an
  Igor's run searching no lore and saying so.
- **Can a caller with write, not admin, access read a collaborator's
  permission?** (task 0.42) If not, such a caller is treated as one GitHub
  refuses for lack of push access: in that repository, every answer in a
  post and every issue's decision block counts as input, and a post's question tags
  none of its candidates.

### Facts the answer service relies on

- **What form does igor's handback marker take?** (task 0.6) Until it is
  recorded, no comment counts as a handback, and the README says so.
- **Can the answer service work on Linear?** (task 0.16) If any part of
  the task fails, Linear stays off and the README says so. An
  assignment is dated by when a poll first finds it; if the person's key
  can read when an issue was assigned, that time dates it instead.
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
- **Which Linear app user is an Igor's?** (task 0.38) If no form tells an
  Igor's app user from another, no Linear comment is a handback, and the
  README says so.

### Outside this change

- **Proving an answer by a link to a message on another surface,** such as
  Discord, would need that surface's API to vouch for the message's author,
  and a map from the author to a GitHub login: igor issue #160's configuration
  entry keyed by the Discord user id, or a file in the lore repository. A
  later change would choose. Without it, an answer typed directly on such a
  surface counts only through a decision document, such as the scribe's
  record; one typed in the answer service and relayed there counts through its
  answer file.

