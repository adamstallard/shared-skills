# Inquisitor

## Decisions

### Decided by Adam (2026-10-19 and 2026-10-20)

Decisions 1 to 10 are recorded in the body of
[igor #211](https://github.com/adamstallard/igor/issues/211). Adam gave the
others, and this proposal is the first place they are
written down: 11 to 15 and 31 in Claude Code sessions, and 32 to 35 and 38
to 49 and 51 to 63 on 2026-10-19, and 64 to 78, 80 to 85 and 87 to 98 and 100 to 106 on 2026-10-20, in Claude
Code sessions while reviewing this pull
request, [#25](https://github.com/adamstallard/shared-skills/pull/25), whose
own thread holds none of them. In the same sessions he confirmed or changed
every decision this change had proposed by then, 16 to 30, 36, 37, 50 and
79, confirming 79 only in part; *Proposed by this change* below says which.
The change's later decisions 86, 99 and 107 he has not seen.

1. **Four filters run before any question reaches a person.**
   1. **Already answered:** the agent finds the earlier answer, cites where it
      is recorded, and does not ask. The earlier answer may be in another
      spec or another decision document: a decision record, a `DECISIONS.md`
      file, the decision block at the top of an issue, or a lore entry.
   2. **Deferrable:** the agent defers it without asking. The deferral stays
      visible: it is listed as not in this change, and filed as an issue if it
      outlives the change. A person who wants it now says so.
   3. **Not a real question:** unless at least two options each have merit,
      the agent takes the one it recommends and records it in a spec or
      decision document, without asking.
   4. **Cheap to reverse:** where two options have merit but switching later
      is cheap, the agent decides and records it, without asking.
2. **Every answer is recorded where the next agent will look.** Every question
   asked is logged, pointing to where its answer is recorded, so an agent
   using the inquisitor finds the answer instead of asking again. Adam's
   decisions 32 and 34 make two exceptions: a question about one person's
   way of working gets no log, and a question in one of 34's categories is
   recorded by hash only. Decisions 45 and 50 add more: a question about a
   private repository is not logged in a public lore repository, and a
   question about an organization or project with no lore repository
   configured is not logged.
3. **An answer that generalizes becomes lore.** Where a person's answer, or a
   lesson learned from a person, is broadly useful, it is proposed as a lore
   entry: a pull request to the team's lore repository.
4. **It covers any agent about to ask a person,** not only spec review or
   OpenSpec.
5. **A hook enforces it.** A hook on Claude Code's question picker
   (`AskUserQuestion`) makes an agent run the inquisitor before asking.
6. **It vets questions in posts too.** Questions in the pull request
   descriptions, comments and chat messages an agent is about to post pass
   the same filters. The inquisitor prepares each question that survives, and
   decides who to tag in it.
7. **It takes over the questions behind handed-back items:** items an Igor
   (one of the igor project's AI teammates) hands back because of a question
   it could not settle. This and decisions 9 and 10 belong to the Igor
   inquisitor role, an Igor that brings questions to a team discussion,
   which is out of scope here.
8. **It is restrained.** It batches related questions into one post, and
   keeps to a budget of posts per channel. The budget belongs to the role.
9. **A blocked Igor filters its own question, and the inquisitor role asks
   it.** The role's half is out of scope; the filters it runs are this skill's.
10. **A question reaches the inquisitor role through the blocked item
    itself.** Out of scope.
11. **The skill is useful locally, before any Igor role exists.** It needs
    nothing from Igor.
12. **Filter 1 also searches the team's lore repository**, the markdown
    entries with conditions, so lessons reach plain Claude Code sessions.
13. **Each "that was obvious" from a person is logged as a miss** against the
    filter that should have caught the question. The misses later inform
    edits to the skill, by pull request, never automatically.
14. **A lesson from the misses lands by its scope.** A lesson that holds for
    anyone using the skill is a pull request changing the skill in
    shared-skills. One that holds for one team or organization is a pull
    request to that team's lore repository. One that holds for one person goes
    to that person's own memory or `CLAUDE.md`. The question and miss logs
    stay with the repositories and lore repositories they concern (decision
    32), because they can hold private content, so a pull request to
    shared-skills carries only the generalized lesson.
15. **A skill's `DECISIONS.md` is its current reasoning in one place, not a
    log.** While a change is open, its reasoning lives in its proposal and
    design.md. When the change is archived, its lasting reasoning is folded
    into the `DECISIONS.md` of each skill it affects, rewriting the reasoning
    it supersedes rather than appending. This pull request's first commit
    puts the rule in `AGENTS.md`, and makes it the last task
    `openspec/config.yaml` asks of every change.

Decisions 31 to 35 came after decisions 16 to 30 below were numbered, so they
take the next free numbers. 32 to 35 came from Adam's review of #25, and
replace what decisions 18 and 19 said about where questions are logged:

31. **When no candidate in the tagging order can decide, the inquisitor's
    script tags the person running the session, or no one.** When the
    inquisitor vets a question in a post and none of the candidates its
    tagging order finds has write access to the repository the question
    concerns, the script tags the person running the session, if that person
    has write access. Otherwise it posts the question with no tag, and the
    post says that no one with authority to decide could be found. The
    tagging order is decision 17's.
    Decision 41 says how the person running the session is identified, and
    when they are asked in the session instead of tagged; in those cases
    nothing is posted untagged.
32. **No personal question log.** Every question concerns a project, an
    organization or a repository, and a question that concerns none of them
    is not asked. Each question's record goes with what it concerns, at that
    place's privacy, which its maintainers decide. No question log is kept
    under the person's home directory, or anywhere else personal. The one
    exception is a question about one person's way of working, such as
    "should I keep working while you're away?": its answer goes into that person's memory or `CLAUDE.md`, which
    agents already read, and it gets no log.
33. **Recontextualise or don't ask.** A question is about one thing, a
    repository, a project or an organization, and is written at that thing's
    privacy. Context from something more private is generalised ("because
    some private backend might do Y", not "because gmango's backend does Y")
    or left out. If the question can't stand without that context, it is not
    asked. A question is never filed in a more private place to keep its
    context.
34. **Some questions are asked but never logged in readable form:** one
    about an unfixed security vulnerability (such as whether a path
    traversal is exploitable), one holding a secret (a key or token), and
    one holding personal information about someone (their health, an HR
    matter, a conflict between people). The filters still run, and the agent
    may still ask. Decision 48 limits this to the skill's own records. The
    picker hook matches a question's exact text against its
    latest verdict (decision 22), so the script still records a verdict for
    such a question, but only as a hash of its text, the verdict, the time,
    and a category from a fixed list: `vulnerability`, `secret` or
    `personal`. No text, context or answer is recorded. The fixed list keeps
    "don't log this" from becoming a way to skip the record: the agent must
    name why the question is not logged. A vulnerability's answer goes to the
    fix and to the repository's private security advisory, which is its
    lasting record. Decision 38 says how long the hash record is kept.
35. **A team's lore repository keeps questions apart from its lore** for
    questions about the organization or project that are not important
    enough to become lore but are worth keeping so that nobody asks them
    again. Nothing there is given to agents as lore, and it has the lore's
    privacy and access, which its maintainers set. Filter 1 searches both
    the lore entries and those questions. Promoting an answer to lore is a
    pull request in the same repository. A question about one repository
    stays in that repository's `.inquisitor/questions/`. Decision 42 says
    where in the lore repository the questions go.

Adam gave 38 to 49 after decisions 36 and 37 below were numbered, answering
questions that spec-check's consistency reads raised:

38. **Every hook record expires after 2 hours.** A record of a verdict, with
    a category or without one, is the hooks' state: it is kept 2 hours, the
    time in which a hook reads it, and then deleted. None of the skill's
    own records keeps a lasting record of a question in one of decision 34's
    categories (decision 48). Kept on the person's machine, it would be a
    personal log, which decision 32 rules out. Kept with the questions, it
    would show, in a public repository, that such a question was asked and
    when.
39. **A question in one of decision 34's categories is asked only through
    the picker,** or, for a vulnerability, in the repository's private
    security advisory. The post hook blocks a post that holds one.
40. **An Igor's handback comment is outside this change.** The comment an
    Igor posts when it hands an item back is governed by igor #211. Its
    decision 9 says that in a team that runs no Igor inquisitor role,
    nothing posts that comment to a discussion, batches it or tags anyone;
    in a team that runs one, the role does those things. The post hook,
    batching and tagging do not apply to it. The Igor inquisitor role is out
    of scope here.
41. **The person running the session is the GitHub login in the
    inquisitor's configuration,** `~/.config/shared-skills/inquisitor.json`
    (decision 25), not the login `gh api user` returns: an agent posting as
    a GitHub App has no user, and one posting as the person would tag
    itself. When the post would go out as that same login, the agent asks
    the person through the picker in the session instead of tagging them,
    since a self-tag sends no notification. When no login is configured, it
    also asks through the picker.
42. **A lore repository's questions live on an orphan branch named
    `questions`,** apart from igor's `igor-state` branch, where igor keeps
    its runtime state. The question and miss files about the organization or
    project are pushed there directly, with no pull request; when a push is
    rejected, the agent fetches and pushes again. Each file's name has a
    random suffix, so two pushes never write the same file. Filter 1 reads
    the branch with `git fetch` and `git show`, without checking it out.
    The lore repository's main branch holds only lore entries. Promoting an
    answer to lore is a pull request to main adding a `provisional` entry,
    and the question's file stays on its branch. Lore's main branch then
    stays readable and holds only what Igor gives agents as lore, and a
    question needs no review, since its authority comes from who answered it
    (decision 20). This replaces decision 36.
43. **A repository's own questions stay in its `.inquisitor/questions/`,
    committed with the work,** not on a branch: a question about a change
    belongs in that change's history and merges with it.
44. **A question in one of decision 34's categories is deferred only into
    the agent's report to the person in the session,** or, for a
    vulnerability, into the repository's private security advisory. It is
    never listed in a post or filed as an issue.
45. **Nothing from a private repository goes to a public lore repository,**
    and decision 77 extends this to internal ones.
    Decision 27's refusal also covers pushing a question to a lore
    repository's `questions` branch and promoting an answer from there into
    lore. A repository whose visibility can't be read counts as private, and
    a lore repository whose visibility can't be read counts as public.
46. **A lore entry scoped `project:<name>` matches a question when `<name>`
    is the short name of the repository the question concerns,** the part
    after the `/`. That is igor's own rule (`scopeMatches` in igor's
    `src/firing.ts`: `project:` matches a repository the role works). A
    project whose repositories have other names would need a mapping, kept
    in one file in the lore repository that igor and the inquisitor both
    read.
47. **The script scans for secrets,** in every log file it writes and every
    question in a post, and refuses on a match. Decision 84 says the scan is
    only a backstop.
48. **Decisions 34 and 38 cover the skill's own records.** The host's
    transcripts, such as Claude Code's under `~/.claude/projects/`, are
    outside the skill's control, and hold a question asked through the
    picker in full.
49. **When a hook can't read its own verdict records,** the picker hook
    lets the question through and the post hook blocks the post. A picker
    question publishes nothing, so at worst one unfiltered question reaches
    the person. The post hook can't tell whether a question had a category,
    and a published vulnerability can't be taken back.

Adam gave 51 to 54 after decision 50 below was numbered, answering
questions from spec-check's third consistency read:

51. **A `deferred` verdict says where the question will be listed,** such as
    "this PR's description" or "an issue at the end of the work", not a
    link, since that post may not exist yet. The post hook accepts a
    `deferred` verdict of any age, since a deferral asks nothing. So a
    `deferred` record is the one exception to decision 38: it is kept until
    a later verdict on the same text replaces it. A `deferred` record with a
    category is deleted after 2 hours like any other, since decision 44
    keeps a categorized question out of posts.
52. **A choice the agent made under filter 3 or 4, with no decision
    document to hold it, is logged with `authority: agent`.** Filter 1
    treats it as an answer, labelled as the agent's choice so that a person
    can overrule it. Such a file is written only in the repository holding
    the current work, or pushed to the lore repository's `questions` branch
    (decision 55), never by a pull request to another repository.
53. **The configured login must be the account `gh` is logged in as,**
    checked by the script running as the person. If they differ, the
    session counts as having no login configured. This doesn't contradict
    decision 41, which rejected `gh api user` as the source of the person's
    login: the login still comes from the configuration, and `gh` only
    confirms it.
54. **A question with an `ask` verdict in a post is vetted again when the
    post is edited after the 2-hour limit.** Vetting again is one pair of
    calls. A `deferred` question never needs it (decision 51).

Adam gave 55 to 63 answering questions from spec-check's fourth
consistency read:

55. **An `authority: agent` file may also be pushed to the lore
    repository's `questions` branch,** since that needs no pull request.
    This amends decision 52; a pull request to another repository is still
    ruled out. By decision 100, such a file is always input there.
56. **A `decision` log entry counts as an answer only when it is on the
    default branch,** or, for lore, on the `questions` branch, **and its
    `answered_by` has write access to what the question concerns when filter
    1 reads it.** Otherwise it is input: `authority` is a field anyone can
    write.
57. **The shared post reader also reads posts sent through the github-app
    skill,** as `python3 <github-app script> gh pr|issue …`, and comments
    sent with `gh api` whose body is given by `-f`, `--raw-field`, `-F` or
    `--field` `body=` (`-F` and `--field` also read `@<file>`), or by
    `--input`. Posts an agent sends as a GitHub App are then vetted, and
    prose's posting hook, which shares the reader, is fixed the same way.
    This amends decision 24.
58. **A session with no person in it never uses the picker,** which is for
    a person to read. It posts its question on a surface, tags by decision
    17's order, and, when no candidate has write access, tags the
    configured login only when it has write access and the post goes out as
    someone else (decisions 31 and 41); otherwise it posts untagged, saying
    so. Decision 41's picker fallback applies only when a person is in the
    session. How the agent tells a session with a person in it from one
    without is unmeasured (task 0.9);
    when it can't tell, the session counts as having no person in it.
59. **A `deferred` verdict passes the post hook only for a question listed
    in an open-questions section and tagging no one.** Anywhere else the
    question needs an `ask` verdict.
60. **Filter 1 searches lore entries everywhere, Igor workers included,**
    applying igor's exact scope filter, with status labelled as decision 64
    says. igor injects every active
    in-scope entry only while they fit its token budget: over the budget
    nothing is injected, and a later relevance mechanism would inject a
    subset, so people's answers could be missing from a worker's context.
    igor's lore-firing spec forbids offering a worker a search tool, with no
    reason beyond the worker not needing one. Adam has decided to amend it:
    lore still reaches the worker unbidden, the ban on a search tool goes,
    and any search during a run applies firing's scope rule, while an in-scope entry that
    is not `active` is returned labelled as not lore. igor PR
    [#216](https://github.com/adamstallard/igor/pull/216), which records
    the decisions also held in igor issue
    [#215](https://github.com/adamstallard/igor/issues/215), makes that
    change, and is this decision's dependency for Igor workers. Decision 64 sets the scope an
    Igor uses.
61. **Filter 1 hides lore entries outside the question's scope,** and never
    shows them, even as input. Scope is visibility, as igor treats it.
62. **Three rules the spec states are Adam's decisions as written:**
    1. A question with a category gets no search outside the machine, such
       as GitHub's issues, so its text never reaches GitHub's search; the
       first call's output says those sources weren't searched.
    2. An issue's decision block is the start of the issue's body before its
       first heading, or its first section whose heading starts with
       "Decision", stating what is decided. It counts as an answer only when
       the issue's author has write access.
    3. For a question about an organization or project, write access to
       what the question concerns means write access to the team's lore
       repository.
63. **Filter 1 keeps searching `docs/decisions/` for decision records
    until igor PR #202 settles where igor's scribe,** the Igor role that
    writes a discussion's decisions down, **keeps its records,** and this
    change then follows it.

Adam gave 64 to 69 on 2026-10-20, answering questions from spec-check's
fifth consistency read:

64. **Inside an Igor, filter 1's scope is the running role's,** as igor's
    `scopeMatches` gives it: `global`, `role:<the running role>`, and
    `project:` matching any repository the role works. Outside an Igor it is
    `global` and `project:<the short name of the question's repository>`.
    Scope is always a hard filter. Status stays as decision 20 has it: an
    in-scope entry that is not `active` is shown as labelled input, never as
    an answer. Adam made the matching decisions for the igor change (igor
    PR #216): scope hard, status labelled.
65. **An Igor worker that is handing an item back asks in its handback
    comment,** as igor #211 says; decision 40 already exempts that comment.
    Decision 58's rule covers other headless runs, and an Igor posting
    outside a handback.
66. **A decision record with a status, such as a MADR, counts as an answer
    only when its status is `accepted`;** any other status is labelled
    input. Filter 1 also reads the lore repository's MADRs once igor PR #202
    settles where they live (decision 63).
67. **A headless session never asks or posts a `secret` or `personal`
    question.** It stops the work that needs it, and reports only that a
    question of that category is blocking, with no text. A vulnerability
    question it asks only in the repository's private security advisory,
    and it stops the work and reports the same way.
68. **A logged answer, and a miss's record of what the person said, are
    written at the privacy of what the question concerns,** by decision
    33's rule: private context generalised or left out. Decision 89 says
    what happens when that can't be done.
69. **When filter 1 stops a question with a lore entry, the question's log
    file names the entry by its id,** in a `cites` field, so that igor's
    review, which prunes and promotes entries, can count an entry's
    citations beside its fire count. Adam chose counting citations over
    counting raw search hits. His decision 83 moves the citation from the
    question's log file to a citation-only file on the lore repository's
    `questions` branch.

Adam gave 70 to 75 on 2026-10-20, answering questions from spec-check's
sixth consistency read:

70. **A decision document on the current work's own branch answers
    questions within that same work,** labelled as this change's, not yet
    merged. Elsewhere it is input.
71. **A post or issue holding a question is never more public than what the
    question concerns,** by decision 77's order. Otherwise the agent asks
    through the picker, or, with no person in the session, posts in the
    concerned repository. Decision 103 extends this to every channel.
72. **Replaced by Adam's decision 78.** It counted a `questions`-branch
    `decision` file when GitHub's login for the commit that added it equalled
    `answered_by`.
73. **Verdict records hash a question's text with plain SHA-256.** They are
    deleted after 2 hours (decision 38), except an uncategorized `deferred`
    record (decision 51). A short sensitive question has a category, and a
    categorized record is always deleted after 2 hours, so its hash is
    exposed to guessing only briefly. *Rejected:* an HMAC with a
    per-HOME key, which would stop guessing short sensitive questions from
    their hash.
74. **A question another installed skill requires a person to decide is
    exempt from filters 3 and 4:** bug-hunter's root causes and its other
    questions it always asks, prose's `kept (asked)` findings, and whether
    to adopt spec-check or spec-trace. Filters 1 and 2 still apply, and its
    `ask` verdict names the skill that requires it.
75. **Verdict records are shared by everything using the same HOME,** Igor
    workers included: a verdict is about the question's text, not the
    worker. *Rejected:* per-clone records, as prose keeps its tokens.

Adam gave 76 to 78 on 2026-10-20, answering questions from spec-check's
seventh consistency read:

76. **Amended by Adam's decision 100.** **An `authority: agent` file
    follows the same rules as a `decision` file:** it counts only on the default branch, on the current work's own
    branch for questions within that work (decision 70), or on a lore
    `questions` branch with its writer proven as decision 78 says;
    otherwise it is input. Decision 100 makes an `agent` file on a
    `questions` branch always input.
77. **Visibility is ranked private, then internal, then public.** GitHub's
    `INTERNAL` is visible to a whole enterprise. Nothing goes to a more
    visible place than what it concerns: a private repository's question or
    answer never goes to an internal or public lore repository or post, and
    an internal repository's never goes to a public one. An unreadable
    visibility keeps the fail-safe directions: the repository the question
    concerns counts as private, and a lore repository or a post's target
    counts as public. This amends decisions 45 and 71.
78. **A `decision` file on a lore `questions` branch counts only when its
    writer is proven** (an `agent` file there is always input, by decision
    100), in one of two ways:
    1. the file links the GitHub comment or review holding the answer, and
       GitHub gives that comment's author as `answered_by`, who has write
       access to what the question concerns; or
    2. the commit that added it carries a signature GitHub verifies for
       `answered_by`'s account. That needs a one-time commit-signing setup
       on the person's machine; the agent commits from their session, so
       the person never signs an answer by hand.

    In a project set up for a GitHub App, the github-app skill commits as
    the bot without the person's signature, so there a `questions`-branch
    `decision` needs the comment-link proof, or it is input.

    Otherwise the file is input. GitHub's commit author login comes from
    the author email, which anyone with push access can set, so it proves
    nothing. *Rejected:* matching the commit's author login, which is
    forgeable; and treating every `questions`-branch file as input, which
    would make that branch unable to settle a question. This replaces
    decision 72.

Adam gave 80 to 85 on 2026-10-20, answering questions from spec-check's
eighth consistency read:

80. **A decision on the current work's own branch counts (decision 70) only
    when the current work's pull request author, or, with no pull request,
    the person running the session, has write access to the repository.**
    Otherwise it is input, since an outside contributor could commit a
    decision that stops the agent's questions. This covers decision
    documents and `agent` entries there.
81. **Files written for questions that were never asked follow the same
    privacy rules:** the question is written at the privacy of what it
    concerns (decision 33), and an agent's choice has `answered_by: agent`.
82. **An Igor whose role can't be read searches `global` lore entries
    only.** igor #216 says a search during a run must not return an entry
    whose scope does not cover the role, and only `global` is safe without
    knowing the role.
83. **Every filter-1 citation of a lore entry goes to that lore
    repository's `questions` branch, as a citation-only file.** igor's
    review counts citations there, in one place, with no privacy risk. A
    question's own log file may still say where its answer came from, at
    its privacy. This replaces the `cites` field of decision 69. Decision 87
    says what the file holds.
84. **The secret scan is only a backstop:** it catches known token shapes,
    and a `DB_PASSWORD=…` passes it. The agent never puts a credential into
    a question, an answer or a verdict field; a question that needs one gets
    the `secret` category.
85. **Each configured lore repository names what it serves:** GitHub owners,
    specific repositories (`owner/repo`), or both, and several may serve the
    same owner. Filter 1 searches every lore repository that serves the
    repository the question concerns. An organization or project question
    goes to the lore repository that serves the project it concerns.
    Decision 86 says which one when more than one matches.

Adam gave 87 to 92 on 2026-10-20, answering questions from spec-check's
ninth consistency read:

87. **A citation file holds only the cited entry's id and the date,** with
    no hash of the question: igor's review counts citations per entry and
    needs nothing about the question. With nothing about the question in
    it, a citation is written for a private question too. This amends
    decision 83. Decision 104 sends none for a categorized question.
88. **During an Igor's run, the worker reports its citations in its
    output, and the Igor pushes them to the `questions` branch when it
    publishes the run,** as igor has a worker edit and its Igor publish; a
    worker holds only its seat's token. Adam decided this for igor #216.
89. **An answer carrying context more private than what the question
    concerns is generalised first,** with the question (decisions 33 and
    68). If the agent can't generalise it, nothing is logged: the answer is
    used in the work, and the agent's report says it couldn't be recorded
    at this privacy. A later agent may ask again.
90. **The inquisitor's commits to a lore `questions` branch are machine
    records,** with a fixed message such as `inquisitor: log <file>`, exempt
    from prose's and bug-hunter's trailers. That branch is never checked
    out, so those skills' checks never see the commits; at archive, their
    `DECISIONS.md` files say so.
91. **With no git repository, filter 1 searches every configured lore
    repository,** filtered by scope.
92. **Two points from the igor side, for consistency:** a search over lore
    is not injection, so an Igor's search may show `provisional` and
    `deprecated` entries, labelled, without breaking igor's promise that an
    unreviewed lesson is injected into no worker until merged; and igor's
    check that a proposed lore entry's id is not already used covers every
    entry and rejection, but during a run it reports
    a collision with one outside the run's scope only as "id taken",
    without naming it.

Adam gave 93 to 98 on 2026-10-20, answering questions from spec-check's
tenth consistency read:

93. **A citation's commit names no person:** its author and committer are a
    fixed `inquisitor <noreply>`, and its date holds only the day. No
    citation is sent when the lore repository is more visible than the
    repository the question concerns. GitHub's events API still records
    each push's pusher and time, visible to anyone who can see the lore
    repository; by this decision, that repository is no more visible than
    the question's.
94. **A commit signature made in the person's session (decision 78's
    second proof) proves a `decision` only for an answer the person gave in
    that session,** through the picker or in their own message in
    the conversation. An answer the agent read anywhere else, such as a
    file, an issue, or a chat or tracker message, is input unless decision
    78's comment link proves it. The agent never writes `decision` for its
    own filter-3 or filter-4 choice; that is `agent`.
95. **A decision document on the current work's branch counts (decision 80)
    only when that branch is in the repository itself,** where pushing
    already needs write access, and the pull request's author has write
    access. A fork's branch is input. No signature is required.
96. **The shared post reader blocks as unreadable any `gh api` call with
    `-X POST`, `PATCH` or `PUT`, or a GraphQL mutation, whose body it can't
    read,** and prose's hook changes the same way. This extends decision 57.
97. **A subagent returns its question to whoever started it instead of
    opening the picker,** because the starting agent is the one talking to
    the person, and can batch the subagent's questions with its own.
98. **Points from the igor side, where this change touches them:**
    - During an Igor's run, the Igor pushes the citations its worker
      reported only when the run publishes, as bookkeeping outside the
      actions the role's `allow` list permits, and only citations of existing `active` entries
      in the run's role's scope.
    - During a run, the repository the question concerns is the repository
      of the item the run works, never one the worker names.
    - igor's review count of an entry's citations is a lower bound, and says
      so beside the count.

Adam gave 100 to 106 on 2026-10-20, answering questions from spec-check's
eleventh consistency read:

100. **An agent's choice pushed to a lore `questions` branch is always
     labelled input.** It is still pushed, so later agents see the context,
     but it never stops a question. This amends decision 55.
101. **A headless session with a question about one person's way of
     working doesn't ask it.** It stops only if the work needs the answer,
     and reports that the question waits for the person.
102. **The shared post reader's rules are stated once,** in this change's
     `gh-post` capability spec for `.agents/lib/gh-post/`, which prose and
     the inquisitor both use; the inquisitor's spec points to it. Decisions
     24, 57 and 96 are its rules.
103. **The agent puts a question only where the audience is no wider than
     what the question concerns,** in every channel, Linear and Discord
     included. When it can't tell, it asks through the picker, or, in a
     headless session, doesn't post and reports that it didn't. This
     extends decision 71.
104. **A question with a category sends no citation;** an ordinary one
     does. This amends decision 87.
105. **In a project set up for a GitHub App, a `questions`-branch decision
     needs the comment-link proof** (decision 78's first), since the
     github-app skill commits as the bot, unsigned.
106. **From the igor side:** the Igor pushes a run's citations when the run
     publishes, and a handback comment counts as publishing.

### Proposed by this change

Decisions 16 to 18 are #211's proposals that apply to the skill; #211's
other proposals concern the role. Decisions 19 to 30, 36, 37 and 50 were
needed to write the requirements. Reviewing #25, Adam confirmed 16
to 30, 37 and 50, except 26, which he changed; his decision 42 replaced 36.
His decision 32 replaced part of 19, and his decision 35 part of 18.

16. **Confirmed by Adam (2026-10-19).** **A prepared question** states the recommended answer, what changes under
    the other answer, and a link to any related earlier decision, so that most
    can be answered "yes". In the picker the recommendation is the first
    option, and the script's second call checks it. The hook needn't:
    reordering the options after vetting changes the question's text, which
    the hook already blocks as unvetted.
17. **Confirmed by Adam (2026-10-19).** **Who is tagged in a post:** one person who can decide, where #211
    proposed the fewest who can. Only a person with write access to the
    repository the question concerns can decide it. Among them, the script
    tags the first it finds
    of: whoever approved the related earlier decision, a reviewer listed in
    that repository's `.inquisitor/reviewers` (for a question about an
    organization or project, the lore repository's, by decision 62.3), then whoever last changed the
    files involved. #211 named "a reviewer or expert named in the team's
    configuration"; a file in the repository is that configuration, so
    every teammate's agent tags the same person. A person whose access can't
    be read counts as having none. When no candidate has write access,
    decision 31 says who is tagged.
18. **Confirmed by Adam (2026-10-19).** **An answer about one repository
    lives in that repository.** His decision 35 settled the other half, an
    answer that spans repositories: it goes to the team's lore repository's
    `questions` branch (decision 42), or into lore itself when it is
    important enough.
19. **Confirmed by Adam (2026-10-19), and amended by his decision 32.** **The
    log is one file per question,** under `.inquisitor/questions/` at the
    root of the repository the question concerns, committed with the work.
    A question about an organization or project goes to its lore
    repository's `questions` branch instead (decision 42). Decision 50 says
    how a file reaches a repository other than the one holding the current
    work. Each file's name has a
    random suffix, so two branches that each log a question never write the
    same file. *Rejected:* one log file that every question appends to,
    because two branches that each log a question then conflict when they
    merge.
20. **Confirmed by Adam (2026-10-19), with its last sentence amended by
    him, and its scope amended by his decision 64.** **Only an answer with
    authority stops a question.** An answer is a
    decision document in the repository, an issue's decision block written
    by someone with write access, a logged answer from such a person, or an
    `active` lore entry scoped to everyone or to this repository. Everything
    else, including `provisional` and `deprecated` entries, is shown as
    input. An answer in the picker is a decision only when the configured
    login of the person running the session has write access to what the
    question concerns; otherwise it is logged as input.
21. **Confirmed by Adam (2026-10-19).** **An agent asks a person only
    through the picker,** where the host has one, so that the hook sees
    every question. On a host with no picker, this decision does not apply,
    and no hook checks the question. *Rejected:* a hook at the end of the
    agent's turn that reads questions in its reply, because the person has
    already read the reply when that hook runs. Decisions 24 and 39 name
    the other places a question may go: a post, a Linear or Discord
    message, and the repository's private security advisory.
22. **Confirmed by Adam (2026-10-19).** **Two calls prove the filters ran,** as prose's two calls prove its pass
    ran. The first prints the filters, runs filter 1's search and issues a
    token. The second records a verdict for each question. The picker hook
    allows a question only if the latest verdict on its text is "ask" and
    less than 2 hours old; the post hook also allows "deferred", since filter
    2 lists a deferred question, within the limits of decision 59. The
    picker hook fails open when it can't read its input. The post hook lets
    through input that is not JSON, and blocks a `gh` command whose body it
    can't read. Decision 49 covers their records. *Rejected:* a signed
    footer inside the question, because the person reads it in the
    picker. See design.md.
23. **Confirmed by Adam (2026-10-19).** **The spec defines a question in a post** (*Questions in posts pass the
    same filters*). This settles #211's first open question, how to find the
    questions in a post's free text, by filter 4: the rule lives in one
    function, so changing it later is cheap. A post is
    vetted after prose's pass and before prose signs it.
24. **Confirmed by Adam (2026-10-19).** **The post hook reads `gh` and GitHub MCP posts through the same code as
    prose's posting hook,** moved into `.agents/lib/gh-post/`, and extended
    by Adam's decision 57. *Rejected:* a
    copy of that code, since prose's parser had about 25 places where it
    misread commands before it was cut to an allow-list. Also rejected:
    calling prose's copy, which would fail whenever prose is not installed.
    The hook covers GitHub only, as prose's does. A question in a Linear or
    Discord post is covered by the skill's instructions alone.
25. **Confirmed by Adam (2026-10-19), and amended by his decision 85.**
    **Lore repositories are named in
    `~/.config/shared-skills/inquisitor.json`** as local clones, each with
    the GitHub owners and repositories it serves.
26. **Changed by Adam (2026-10-19).** **Lessons are drafted from the misses
    only when a person asks** to review them. A lesson for shared-skills is
    written in general terms, so that it needs to quote no logged question
    or miss. *Rejected:* the script refusing a lesson that quotes a logged
    question, which a lesson written in general terms never does.
27. **Confirmed by Adam (2026-10-19).** **The skill opens a lore pull
    request without asking first,** as a `provisional` entry, and reports
    its link: a pull request is itself a proposal, and closing it is cheap.
    The skill's script refuses to open one to a public lore repository when
    the answer came from a private repository.
28. **Confirmed by Adam (2026-10-19).** **The hooks are enabled by default,** as prose's blocking hooks are.
    Installing the skill is the opt-in.
29. **Confirmed by Adam (2026-10-19).** **A scenario about what the agent does is traced to a test that checks
    SKILL.md states the rule.** spec-trace's CI fails on an untagged scenario
    once the change is archived. *Rejected:* exempting those scenarios in
    spec-trace's baseline (`openspec/spec-trace-baseline.txt`), which takes
    no new lines.
30. **Confirmed by Adam (2026-10-19).** **OpenSpec is used for new work in shared-skills.** A skill's spec holds
    what must be true of it, and its `DECISIONS.md` holds why. Existing skills
    get no spec until a change touches them. This pull request adopts OpenSpec,
    spec-check's decisions-first rule and spec-trace for the repository.

Decision 36 came after Adam's 32 to 35, from writing 35's requirements:

36. **Replaced by Adam's decision 42.** It sent a question's file to a lore
    repository by a pull request.

Decision 37 came from spec-check's consistency read of 32 to 36:

37. **Confirmed by Adam (2026-10-19).** **The hooks' records live in
    `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/`,** as prose's
    session marks do, because a session spans repositories and the hook's
    working directory can differ from the one the script ran in. They hold
    hashes, verdicts, fields and times, never a question's text, and each is
    deleted 2 hours after it was made, with a category or without one
    (Adam's decision 38), except a `deferred` record without a category
    (his decision 51). So they are the hooks' state and not the question
    log decision 32 rules out.
    *Rejected:* the repository's git directory, where a run in another
    repository would leave records the hook never reads. See design.md.

Decision 50 came from writing decisions 42 and 43's requirements:

50. **Confirmed by Adam (2026-10-19).** **A question's file about one
    repository reaches it by a pull request when it is not the repository
    holding the current work,** opened without asking first, as
    decision 27's lore pull requests are, since the current work's commits
    can't carry a file into another repository. Where no lore repository is
    configured for the owner of the repository a question concerns, a
    question about the organization or project is not logged, and the agent
    tells the person so.

Decision 79 came from spec-check's eighth consistency read:

79. **Confirmed by Adam (2026-10-20) in part.** When a push to a lore
    `questions` branch is rejected for any reason other than the branch
    having moved, such as no push access or a rule on the branch, the agent
    logs nothing and says why, rather than retrying. Adam rejected its other
    part, refusing a configuration in which two lore repositories list the
    same owner, since two lore repositories can serve one owner for
    different projects (decision 85).

Decision 86 came from writing Adam's decision 85. It is cheap to reverse,
so this change made it under filter 4, and lists it so Adam can overrule
it:

86. **When more than one lore repository serves what a question
    concerns,** the most specific match wins (a named repository beats an
    owner), then the first listed in the configuration, and the agent's
    report says which it chose. It once had a second part, giving a
    categorized question's citation no hash, which Adam's decisions 87 and
    104 made moot.

Decision 99 came from spec-check's eleventh consistency read. Its parts are
cheap to reverse, so this change made them under filter 4, and lists them
so Adam can overrule them:

99. **Three details the spec fixes:**
    1. A linked comment proves a `questions`-branch file's writer (decision
       78) only when the comment's text holds the answer the file records,
       so a bare "LGTM" proves nothing.
    2. The credential patterns are a closed list: a private key's
       `-----BEGIN` line, GitHub tokens (`ghp_`, `gho_`, `ghs_`,
       `github_pat_`), AWS access key IDs (`AKIA`) and Slack tokens
       (`xox`).
    3. A login that is not GitHub's login syntax is never passed to a
       GitHub API call, so an answer whose author has one is input.

Decision 107 came from spec-check's twelfth consistency read. Its parts are
cheap to reverse, so this change made them under filter 4, and lists them
so Adam can overrule them:

107. **Details the spec fixes:**
     1. The shared post reader also reads `python3 <github-app script> run
        -- gh …`, and the script path given as the github-app skill's `$G`.
     2. A `gh api` call writes when its method is `POST`, `PATCH` or `PUT`,
        given by `-X` or `--method` or implied by fields or `--input` with
        no `-X GET`, or when its GraphQL query is a mutation. A write whose
        fields carry no `body` sends no post. This narrows how decision 96
        is read, so that reads such as GraphQL queries and label edits pass.
     3. A rhetorical question is rewritten as a statement, and its
        `decided` verdict names the post.
     4. A proposed lore entry whose id an entry holds gets another id; one
        whose id a rejection holds is not proposed.
     5. A linked answer (decision 78) must be a github.com comment or review
        on the repository the question concerns or on the lore repository.
     6. A fix for a vulnerability states neither its question nor its
        answer in commit messages, pull request text or comments.
     7. A lore clone's reported date is when its remote-tracking default
        branch was last updated by a fetch in that clone.

**Still open:**

Nothing waits for Adam except decisions 86, 99 and 107, which this change
made and he may overrule.

Ten of the items below are unmeasured facts, each measured by tasks 0.1
to 0.12 before anything is built. The others are changes in igor that this
change depends on.
Two other changes are dependencies: igor PR
[#216](https://github.com/adamstallard/igor/pull/216), with igor issue
[#215](https://github.com/adamstallard/igor/issues/215), amending igor's
lore-firing spec (decision 60), and igor PR #202, the scribe's records
(decision 63).

- **Can a `PreToolUse` hook block `AskUserQuestion`?** If not, the picker is
  covered by the skill's instructions alone, and the README says so.
- **Can an agent without push access read another person's permission on a
  repository?** If not, wherever the agent lacks push access, every answer
  in a post and every issue's decision block counts as input, and a post's
  question tags no one.
- **Can the script learn which login a post goes out as?** An agent using
  the github-app skill posts with a token that only the posting command
  holds, so the script's own `gh api user` returns the person's login. If
  the script can't learn it, it treats every post as going out as the
  person, and, in a session with a person in it, asks through the picker
  where it would have tagged them.
- **Can the script tell whether a person is in the session, and which Igor
  role it runs in?** If it can't tell the first, the session counts as
  having no person in it, so a picker is never opened with nobody to answer
  it. If it can't tell the role, every `role:` lore entry is hidden.
- **Can the script find the approver of the pull request that added a
  decision?** A section of a `DECISIONS.md` leads through blame and a
  commit to a pull request and its reviews. If not, the first candidate in
  decision 17's order is skipped.
- **Can the script find the GitHub login of the last person to commit to a
  file?** Git records a name and an email, not a login. If not, the third
  candidate in decision 17's order is skipped.
- **Can the agent open, and write in, a repository's private security
  advisory?** That needs private vulnerability reporting enabled, or an
  admin or security-manager role. If it can't, the agent records a
  vulnerability's question and answer nowhere but the fix, and reports only
  that a vulnerability question is blocking, with no text.
- **Does GitHub's API give a comment's author and a commit's verified
  signer as decision 78 needs?** If not, every `questions`-branch `decision`
  or `agent` file counts as input.
- **igor rules this change relies on that igor #216 does not yet hold:**
  that a worker reports its citations and its Igor pushes them only when
  the run publishes (decisions 88 and 98), and that igor's check that a
  proposed entry's id is not already used covers
  every entry and rejection store-wide and reports an out-of-scope
  collision during a run only as "id taken" (decision 92). Adam decided
  both for igor; #216's follow-up carries them, replacing its rule that a
  duplicate check during a run "MUST NOT compare" against an entry outside
  the run's scope.
- **igor #216's wording on citations.** Its §3.4.1 should say igor's
  review counts citations on the lore repository's `questions` branch, as
  decision 83 has them. It has been raised with igor.
- **Can an Igor's worker run the inquisitor skill at all,** with a lore
  clone and `inquisitor.json` in reach? igor PR #216's task 3.1 measures it,
  and task 0.12 here waits on it. If not, nothing in this change runs inside
  an Igor worker, and its Igor-worker rules wait until one can.
- **Can the post hook tell an Igor's handback comment from other posts?**
  Igor's own code might post it outside any tool call, where no hook sees
  it, or an agent might post it with `gh`. If the hook can't tell, it would
  block an unvetted question in such a comment, against decision 40, until
  the Igor inquisitor role's work marks the comment.

#211's other open questions: decision 23 settles the first. The other two,
how long to wait before following up and whether a discussion is a new kind
of surface for Igor, concern the role only.

## Why

Agents ask people too many questions. Many were already answered, could wait,
have one sensible answer, or are cheap to undo, yet each costs the reviewer
time, and review is often the slowest step in the work. A question answered in
one person's private session is also lost to the rest of the team, so another
agent asks it again.

## What Changes

- A new skill, `inquisitor`, runs every question an agent is about to put to
  a person through four filters, and lets through only those a person must
  answer.
- The questions that survive are prepared for a quick answer, batched, and
  asked through the picker or in a post. Each one asked is logged with where
  its answer is recorded, in the repository or the team's lore repository it
  concerns, so the next agent finds the answer instead of asking.
- A hook blocks a question in the picker, or in a GitHub post, that has not
  been through the filters.
- A person's "that was obvious" is logged as a miss. Reviewing the misses
  produces lessons, each sent where it applies: the skill, a team's lore, or
  one person's memory.
- shared-skills adopts OpenSpec, with spec-check's decisions-first rule and
  spec-trace's CI check.

**Out of scope:** the Igor inquisitor role (#211: decisions 7, 9 and 10, and
the per-channel budget in decision 8), which brings surviving questions to a
team discussion.

## Capabilities

### New Capabilities

- `inquisitor`: filtering, preparing, asking and logging the questions an
  agent puts to a person, and learning from the questions that should not
  have been asked.
- `gh-post`: the shared post reader, `.agents/lib/gh-post/`, which tells
  prose's posting hook and the inquisitor's post hook a post's body, that a
  call sends no post, or that it is unreadable.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/inquisitor/` with its scripts, hooks and tests.
- prose: its posting hook's command reader moves to `.agents/lib/gh-post/`,
  so the inquisitor's post hook reads posts the same way. The reader also
  reads posts sent through the github-app skill and `gh api` comments
  (decision 57), which changes prose's hook in the same way.
- In each repository where it runs, the skill writes `.inquisitor/`. In a
  team's lore repository, it pushes to an orphan branch named `questions`.
- The README's skills table, and its list of skills that turn on a hook.
- This pull request's first commit adds `openspec/`, `AGENTS.md` and
  spec-trace's CI workflow to shared-skills.
