# Inquisitor

## Decisions

### Decided by Adam (2026-10-19 to 2026-10-25)

Decisions 1 to 10 are recorded in the body of
[igor #211](https://github.com/adamstallard/igor/issues/211). Adam gave the
others in Claude Code sessions, and this proposal is the first place they
are written down:
- 11 to 15 and 31;
- 32 to 35, 38 to 49 and 51 to 63, on 2026-10-19;
- 64 to 78, 80 to 85, 87 to 98, 100 to 106, 108 to 110, 112 to 124,
  126 to 129, 131 to 142, 144 to 151, 152 to 169, 176 to 180, 184 to
  196, 204 to 214, 216 to 221, 223 to 226, 229 and 231, on 2026-10-20;
- 232 to 237, on 2026-10-21, and 238 in two parts: Message Content
  turned on, on 2026-10-20, and how `check` reads it, on 2026-10-21.
- 240 to 253, on 2026-10-21;
- 254 to 284, on 2026-10-24;
- 285 to 306 and 308 to 330, on 2026-10-25, with 307, which this
  change proposed, confirmed by 314.

Apart from 229 and 241 to 244, which he gave in the session reviewing
igor PR #216, and 238, which he gave in shared-skills PR #1, he gave those of 2026-10-19 to 2026-10-25 while reviewing this pull
request, [#25](https://github.com/adamstallard/shared-skills/pull/25), whose
own thread holds none of them. In the same sessions he also ruled on the
decisions this change proposed itself: 16 to 30, 36, 37, 50, 79, 86, 99,
107, 111, 125, 130 and 143. Those stay listed under *Proposed by this change* below, each marked
with what he did. He changed 26, replaced 36 with his decision 42,
confirmed 79 only in part, replaced 107's item 6 with his decision 108,
and added his decision 109 to 107's item 5. He confirmed the rest.
He confirmed 170 to 174, which this change proposed while writing the
answer session's requirements, and confirmed 175 item by item, changing
items 2 and 16 by his decisions 185 and 193. He confirmed 181 to 183 and 197
to 203 too, amending 199 and changing four items of 202. He confirmed 215
item by item. He confirmed 222 item by item too, except that his decision
223 reconciles its item 2 with decision 195 and his decision 224 replaces
its item 6. He confirmed 227 and 228 as written. On 2026-10-21 he
confirmed 230 item by item, except items 4 and 5, which his decisions 232
and 235 replace. He confirmed 239 item by item too, except item 2,
which his decision 240 changes. 239's item 5 changes his earlier
decision 200's item 1: a `Recorded answer: ` post no longer quotes the
answer. His decision 245 replaces the rule this change had proposed under
that number, and his decision 246 settles 230's item 1. His decisions 247
to 249 answer the three questions this change put to him when it
recorded 245 and 246, and 250 to 253 answer the four it put to him when
it recorded 247 to 249. On 2026-10-24 he gave 254 to 257, after an audit
of the approved prototype against the spec, 258 to 261, answering
the four questions this change put to him when it recorded 254 to 257,
262, answering the one it put to him when it recorded 258 to 261, and
263, approving the prototype build that 258 required. Each later group
answers the questions this change put to him when it recorded the group
before: 264 and 265 answer two, 266 and 267 answer five, 268 and 269
answer two, 270 to 272 answer the three raised with 268 and 269, and
273 to 275 answer the three raised with 270 to 272, and in 276 Adam
confirmed two details this change had chosen. 277 to 280 answer the four
raised with 273 to 276, and 281 to 284 the four raised with 277 to 280,
one decision each. On 2026-10-25 he gave 285 to 287, settling the five
raised with 281 to 284: 285 answers three of them by removing the case
they were about. 288 to 291 answer the five raised with 285 to 287, one
decision each, except that 289 settles two, and 292 to 295 the four raised with
288 to 291; in 296 he confirmed three choices this change had made.
297 to 299 settle the six raised with 292 to 296: 297 answers the
first and makes the next three moot, 299 answers the fifth and 298 the
sixth. 300 to 306 answer the seven raised with 297 to 299, one
decision each, and 308 to 315 the eight raised with 300 to 307, 314
confirming 307 with a change. 316 to 320 settle the five raised with
308 to 315, one each: 316 the first, by making it moot, 319 the second,
320 the third, 318 the fourth and 317 the fifth. 321 to 324 settle
the four raised with 316 to 320, one each, in order. 325 to 330
answer six of the seven raised with 321 to 324.

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
    Adam's decision 126 limits the posting to a session with no person in
    it that can post, such as a scheduled agent; an Igor worker can't, and
    asks in its handback comment.
59. **A `deferred` verdict passes the post hook only for a question listed
    in an open-questions section and tagging no one.** Anywhere else the
    question needs an `ask` verdict. Decision 113 adds a deferral section
    and a new issue that tags no one.
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
    Decision 58's rule covers other headless runs. Adam's decision 126
    makes the handback comment an Igor worker's only way to ask.
66. **A decision record with a status, such as a MADR, counts as an answer
    only when its status is `accepted`;** any other status is labelled
    input. Filter 1 also reads the lore repository's MADRs once igor PR #202
    settles where they live (decision 63).
67. **A headless session never asks or posts a `secret` or `personal`
    question.** It stops the work that needs it, and reports only that a
    question of that category is blocking, with no text. A vulnerability
    question it asks only in the repository's private security advisory,
    and it stops the work and reports the same way. Adam's decision 136
    has an Igor worker report only a bare flag, a mark defined by igor PR
    #216 that its run met such a question, with no category; his decisions
    244 and 245 have the flag list every category met in the run.
68. *Amended by Adam's decision 240: a person's answer is recorded in
    their words or not at all, never generalised; a miss's `said` is
    still generalised.* **A logged answer, and a miss's record of what the person said, are
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
74. **Amended by Adam's decision 137, which added filter 2 to the
    exemption.** **A question another installed
    skill requires a person to decide is exempt from filters 2, 3 and 4,**
    so it is asked now: bug-hunter's root causes and its other
    questions it always asks, prose's `kept (asked)` findings, and whether
    to adopt spec-check or spec-trace. For spec-check, the exempt question
    is whether to enforce its decisions-first rule, as the spec's first
    requirement says. Only filter 1 still applies, and its
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
78. **Amended by Adam's decision 140.** **A `decision` file on a lore
    `questions` branch counts only when its
    writer is proven** (an `agent` file there is always input, by decision
    100). By decision 140 it also counts only when no commit after the
    one that added it changed it. The writer is proven in one of two
    ways:
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
82. *Moot since Adam's decision 229, under which the script searches no
    lore during an Igor's run and igor's command knows the role.* **An
    Igor whose role can't be read searches `global` lore entries
    only.** igor #216 says a search during a run must not return an entry
    whose scope does not cover the role, and only `global` is safe without
    knowing the role.
83. **Every filter-1 citation of a lore entry goes to that lore
    repository's `questions` branch, as a citation-only file.** igor's
    review counts citations there, in one place, with no privacy risk. A
    question's own log file may still say where its answer came from, at
    its privacy. This replaces the `cites` field of decision 69. Decisions
    87 and 110 say what the file holds. A question that filter 1 stops
    with a lore entry is not asked, so it gets no log file, and its
    citation is its only record. A log file is only ever for a question
    someone answered, so the spec reads "where its answer came from" as
    where that answer is recorded, which is never a lore entry, and no log
    file names an entry by its id.
84. **The secret scan is only a backstop:** it catches known token shapes,
    and a `DB_PASSWORD=…` passes it. The agent never puts a credential into
    a question, an answer or a verdict field; a question that needs one gets
    the `secret` category.
85. **Each configured lore repository names what it serves:** GitHub owners,
    specific repositories (`owner/repo`), or both, and several may serve the
    same owner. Filter 1 searches every lore repository that serves the
    repository the question concerns. An organization or project question
    goes to the lore repository that serves the project it concerns.
    Decision 86 says which one when more than one matches. During an
    Igor's run, decision 133 limits the search to the lore repository the
    Igor injects from.

Adam gave 87 to 92 on 2026-10-20, answering questions from spec-check's
ninth consistency read:

87. **A citation file holds only the cited entry's id and the date,** with
    no hash of the question: igor's review counts citations per entry and
    needs nothing about the question. With nothing about the question in
    it, a citation is written for a private question too. This amends
    decision 83. Decision 104 sends none for a categorized question, and
    decision 110 adds a run id to a citation an Igor pushes from a run.
88. **Amended by Adam's decision 129.** **During an Igor's run, the worker reports its citations in its
    output, and the Igor pushes them to the `questions` branch when it
    publishes the run,** as igor has a worker edit and its Igor publish; a
    worker holds only its seat's token. Adam decided this for igor #216.
    His later decision 110 sets the format the Igor pushes them in, and
    his decisions 123 and 129 leave the rest, including how the worker
    reports them, to #216. So the channel is no longer settled as the
    worker's output: #216 leaves it, the output or an outbox, to igor
    PR #175, which runs a worker as a separate Unix user.
89. *Amended by Adam's decision 240: an answer is no longer generalised;
    one holding such context is not logged.* **An answer carrying context more private than what the question
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
    the question's. Adam's later decision 110 restates this commit's form
    as part of the citation format.
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
    Decision 132 says how the reader reads a GraphQL mutation's body.
97. **A subagent returns its question to whoever started it instead of
    opening the picker,** because the starting agent is the one talking to
    the person, and can batch the subagent's questions with its own.
98. **Points from the igor side, where this change touches them:**
    - During an Igor's run, the Igor pushes the citations its worker
      reported only when the run publishes, as bookkeeping outside the
      actions the role's `allow` list permits, and only citations of existing `active` entries
      in the run's role's scope. Adam's later decision 110 sets their
      format, with the run's id, and his decision 123 leaves these rules
      to igor #216.
    - During a run, the repository the question concerns is the repository
      of the item the run works, never one the worker names.
    - igor's review count of an entry's citations is a lower bound, and says
      so beside the count.

Adam gave 100 to 106 on 2026-10-20, answering questions from spec-check's
eleventh consistency read:

100. **Amended by Adam's decision 140.** **An agent's choice pushed to a
     lore `questions` branch is always
     labelled input.** It is still pushed, so later agents see the context,
     but it never stops a question. This amends decision 55. By decision
     140 the file is never changed once pushed: a person's later answer to
     the same question is a new file.
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
     publishes, and a handback comment counts as publishing. Decision 123
     leaves this rule to igor #216.

Adam gave 108 on 2026-10-20, reviewing #25. Spec-check's thirteenth
consistency read then raised questions about it, and his answers the same
day are its items 1 to 6:

108. **Until a weakness's security advisory is published, nothing the agent
     writes where people outside the advisory can read it describes the
     weakness or how to exploit it.** A fix made after the advisory is
     published is described normally, and so, once task 0.13 allows it, is
     one made in the advisory's private fork (item 6 and decision 127).
     1. It covers text: commit messages, pull request text, comments and
        code comments. The fix's code may land publicly.
     2. It covers any weakness under an unpublished advisory, whether or not
        the agent asked a `vulnerability` question about it, such as one the
        bug-hunter skill finds.
     3. People outside the advisory are everyone who cannot read the
        advisory. A public branch is any branch that people outside the
        advisory can read. In a private repository, collaborators who cannot
        read the advisory can still read every branch, so its branches count
        as public too.
     4. A fix's regression test, such as bug-hunter's test that fails before
        the fix, is a working exploit. It lands only in the advisory's
        private fork, or publicly after the advisory is published.
        *Amended by Adam's decision 205:* until task 0.13 shows that the
        fork's pull request merges only at publication, the test goes in
        the fork only on the word of the person who will publish the
        advisory; without that word, it waits for publication.
     5. When no advisory exists for the weakness, or the agent can't read
        whether it is published, the agent treats it as unpublished.
     6. **Amended by Adam's decision 127.** Task 0.13 measures whether
        GitHub lets the private fork's pull request be merged before the
        advisory is published. Until it shows that the merge waits for
        publication, the fork's commit messages follow the rule for public
        text (decision 127). If it shows instead that the merge can come
        first, a fork commit is described normally only when the agent
        knows, as it writes the commit, that the pull request will be
        merged at the moment of publication, because the
        person who will publish the advisory has told it so; otherwise it
        follows the rule for public text.

     This replaces item 6 of decision 107, which kept a vulnerability
     question and its answer out of a fix's commit messages, pull request
     text and comments. Adam gave three reasons:
     - The risk is describing the weakness, in any words, so whether the
       text states the question or its answer was the wrong test.
     - The risk exists only while the fix is public and the advisory is
       not. GitHub's private advisories come with a temporary private fork,
       whose commits become public with the advisory, so a fix made there
       is not public before the advisory is.
     - A blanket rule would leave a fix's commit message useless even after
       disclosure, against prose's rule 14, that a commit message's body
       says why.

Adam gave 109 on 2026-10-20, reviewing #25, as an addition to item 5 of
decision 107:

109. *Narrowed by Adam's decision 250 to an answer typed directly on
     another surface; an answer typed in the answer session and relayed
     there counts through the signature on its log file's commit.*
     **An answer typed directly on another surface, such as Discord,
     Slack or Linear, counts once igor's scribe records it as an
     `accepted` decision record;** until then it is input. The scribe is the Igor role that
     writes a discussion's decisions down (igor issue #201, PR #202). What
     109 adds is that the answer itself never counts: not as a logged
     decision, and not through a link to the message, since a linked answer
     (decision 78) is only a github.com comment or review, as 107's item 5
     says. The record it counts through is one filter 1 already counts: an
     `accepted` record (decision 66), in a place decision 63 says filter 1
     searches. Any other decision document that records the answer, on the
     default branch of the repository the question concerns, counts too, by
     decision 20, whoever writes it.

Adam gave 110 on 2026-10-20, so that this change and igor PR #216, in
which an Igor pushes the citations its workers report, use one citation
format:

110. **This change defines the one citation-file format, which igor PR
     #216 points to instead of stating its own.** The spec states it once,
     as the requirement *A citation file has one format*:
     - **Path:** `citations/<date>-<6 random hex digits>` on the lore
       repository's `questions` branch (decision 83).
     - **Contents:** the cited entry's id and the date (decision 87), and,
       only when an Igor pushes the citation from a run, the run's id. The
       run's id is opaque, and the Igor records it on its `igor-state`
       branch, where igor PR #216 says (in the run's row of its execution
       ledger, not with the transcript). A session outside an Igor's run has
       no run, and its citation holds no run id.
     - **Commit:** the message `inquisitor: log <file>` (decision 90), the
       author and committer `inquisitor <noreply>`, and a date reduced to
       the day (decision 93).

     igor #216's decision 10 gives the run's id its purpose: igor's review
     shows each citation's run and item. This amends decision 87, under
     which a citation held only the entry's id and the date. Decision 111
     fills in how the file is written.

Adam gave 112 to 124 on 2026-10-20, answering the findings of spec-check's
consistency read of commit b6ca0dd, in which a fresh agent read the change
against everything it must agree with:

112. **The hooks match a question's text without its related-decision
     line.** A prepared question links its related earlier decision
     (decision 16) on a line of its own, `Related: <URL>`, and the hash
     the hooks match leaves that line out. The agent finds the related
     decision in the first call's search, so it can add the link after
     that call without vetting the question again. The spec defines the
     line exactly: `Related: ` and one URL with no spaces. No vetting
     sees that line, so the hooks block a related-decision line holding a
     credential pattern. The agent links only a decision that everyone who
     can read the question can read; no hook checks that.
113. **A deferral section counts as an open-questions section, and an issue
     filed for a deferred question passes the post hook.** A section whose
     heading starts with "Not in this change", "Deferred" or "Not done"
     lists deferred questions, as one starting with "Open" or "Still open"
     does. A new issue that tags no one passes on its questions' `deferred`
     verdicts. Filter 2's two places for a deferred question, the work's
     description and an issue, then both pass. This amends decision 59.
114. **The shared post reader blocks a command that mentions `gh` and that
     it can't read.** In a command that mentions a gh post verb (decision
     119), each simple command that names `gh` is unreadable, with two
     exceptions: a `gh` command the reader reads, and one of prose's data
     commands, such as `echo`, that names `gh` only inside a quoted
     argument. So `sh -c '…'`, `bash -c '…'` and `eval '…'` around a `gh`
     post are unreadable, and so is a pipe into a shell. That is prose's
     rule today. The earlier spec let a command through when `gh` appeared
     in it only inside quotes, as in `sh -c 'gh pr comment …'`. The spec
     now also states prose's other rules: how a command splits into simple
     commands, how pipes and input are judged, and that a command running
     only prose's own script, `prose.py`, is no post, since its arguments
     may name a gh post as text. Adam's decision 139 makes a data command
     that runs code given in the command, such as `python3 -c`, unreadable
     when that code names `gh`.
115. **The reader reads a review's nested comments.** For a review sent
     with `gh api`, it reads each `comments[][body]` field, and each `body`
     in the `comments` of an `--input` file. A review whose comment bodies
     it can't read is unreadable.
116. **A proposed lore entry's id passes igor's id rule,** from igor's
     lore-store requirement *Ids are derived from the claim and then
     immutable*: a kebab-case slug, which igor's validator checks against
     `^[a-z0-9][a-z0-9-]*$` (`ID_PATTERN` in igor's `src/entry.ts`). The
     script refuses any other id.
117. **"A decision document" stays the closed list the spec defines.** The
     wider set of places an answer goes, a decision document, a question's
     log file, or a person's memory or `CLAUDE.md`, is **where the
     question's answer is recorded**.
118. **A log file and a miss file have one format, stated once,** in the
     spec's requirement *A log file and a miss file have one format*, as
     decision 110 does for a citation file. Decision 125 sets the format,
     and design.md points to the requirement.
119. **"A gh post verb" is a closed list,** the one prose's reader handles:
     `gh pr` with `create`, `new`, `edit`, `comment`, `review`, `revert`,
     `close` or `reopen`; `gh issue` with `create`, `new`, `edit`,
     `comment`, `review`, `close` or `reopen`; and a `gh api` write, as
     decision 107's item 2 defines one.
120. **Each tagging scenario that ends in the picker says that the session
     has a person in it,** since a session with no person in it never uses
     the picker (decision 58).
121. **Four rules get scenarios of their own:** a `gh api` write whose body
     the reader can't read, or that carries a body to an endpoint it doesn't
     read, is unreadable; an answer whose author's login is not GitHub's
     login syntax is input (decision 99's item 3); an agent working in no
     git repository logs nothing; and a session with no person in it lists
     a question about one person's way of working in no post or issue.
122. **`python3 $G …` is read only when the same command sets `G`.** A
     command that runs `python3 $G`, mentions `gh` and assigns `G` nowhere
     earlier in the same command is unreadable. The block message says to
     set `G` in that command or write the script's path. In Claude Code
     each command starts a fresh shell, so an unset `$G` makes the command
     fail and post nothing; only a host whose shell keeps variables from
     one command to the next, such as Cursor, could post through it.
     Blocking it there costs a rewrite of the command, so nothing needs
     measuring. This narrows decision 107's item 1. Decision 122 also
     requires the script's path to end in `/github_app.py`: the reader
     cannot know what any other script posts, and prose's reader blocks a
     `gh` word passed to one today. `--identity <name>`, the github-app
     skill's way to choose an identity, may come before `gh` or `run`.
     His decision 135 has the github-app skill's SKILL.md set `G` in the
     same command as each use.
123. **The rules for an Igor's push of its worker's citations live in igor
     #216,** in its lore-firing requirement *An Igor publishes the
     citations its worker reports*: when it pushes, which citations, and
     where. This change points to that requirement instead of restating
     it, and keeps its own rules for a session outside an Igor's run.
124. **Citation commits stay machine records with no trailer** (decision
     90). igor's signed-publishing change, igor PR #153, should exempt them
     from the trailers it requires on an Igor's commits; that is #153's to
     settle, and *Still open* lists it. Decisions 90 and 110 are unchanged.

Adam gave 126 to 129 on 2026-10-20, answering points raised while
recording decisions 112 to 125:

126. **An Igor worker always asks in its handback comment, which its Igor
     posts.** A worker holds no credential that can post: igor's
     task-execution requirement *The worker is given an explicit
     environment holding no credential but its seat's* gives it only its
     seat's token. So decision 65's handback comment is its only way to
     ask. Decision 58's rule that a headless session posts its question
     applies only to a session with no person in it that can post, such as
     a scheduled agent. This amends decisions 58 and 65.

     Decision 143, which this change proposed and Adam confirmed, covers
     the session left over: one with no person in it that can neither
     post nor hand back.
127. **Until task 0.13 shows that a private fork's pull request can't be
     merged before the advisory is published, the fork's commit messages
     follow the rule for public text:** they describe neither the weakness
     nor how to exploit it. The full description goes in the advisory's
     text. This amends decision 108's item 6.
128. **During an Igor's run, an id reported as "id taken" stops the
     entry.** When the id the agent would give a lore entry is reported
     only as "id taken" (decision 92), the agent does not propose the
     entry, and its report says so. A person can propose the entry outside
     a run. Adam decided the same for igor #216's id gate, which #216
     records.
129. **An inquisitor run an Igor starts itself, with no worker, has its
     citations pushed by the Igor under igor #216's rules,** as Adam
     decided for #216. This change points to #216's requirement *An Igor
     publishes the citations its worker reports* for every rule about an
     Igor's run, including how a worker reports its citations, and keeps
     its own rules only for a session outside a run. This extends decision
     123.

Adam gave 131 to 135 on 2026-10-20, answering findings of spec-check's
consistency read of the change before commit 4f90389:

131. **An answer without authority is recorded only in the question's log
     file,** as `authority: input`, and never in a decision document.
     Written into a decision document on the current work's branch, it
     would count as an answer there (decision 70), and the agent's own
     write would turn input into a decision.
132. **The shared post reader reads the body of a GraphQL mutation that
     posts text.** The mutations that post text to an issue or pull
     request are a closed list: `addComment`, `addPullRequestReview`,
     `addPullRequestReviewComment`, `addPullRequestReviewThread`,
     `addPullRequestReviewThreadReply`, `submitPullRequestReview`,
     `createIssue`, `createPullRequest`, `updateIssue`,
     `updateIssueComment`, `updatePullRequest`, `updatePullRequestReview`
     and `updatePullRequestReviewComment`. For each of them the reader
     returns every `body` argument, as a REST write's `body` field is
     returned. Any other mutation sends no post, unless it has a `body`
     argument, which makes it unreadable, as a REST write with a `body` to
     an endpoint the reader does not read is. A mutation the reader cannot
     parse, or whose `body` it cannot read, is unreadable. The spec had
     reported every mutation as unreadable. Decision 132 brings it back to
     decisions 96 and 107's item 2: a mutation is a write, it is blocked
     only when its body can't be read, and one with no `body` sends no
     post. A `createIssue` post creates an issue, as a `POST` to
     `repos/<owner>/<repo>/issues` does.
133. **Inside an Igor's run, filter 1 searches only the lore repository the
     Igor injects lore from,** so an entry id a worker cites names one
     entry, in the repository the Igor pushes the citation to. igor #216
     records the same. This narrows decision 85 during a run.
134. **prose's pass skips files under `.inquisitor/`.** A log or miss file
     is a record that quotes a question as asked and what a person said,
     word for word, and prose's rewrite would change it. prose's file
     filter skips them from gate two, when the skill ships (task 5.6), and
     its `DECISIONS.md` says why at archive (task 7.1).
135. **The github-app skill's SKILL.md sets `G` in the same command as each
     use of it,** or writes the script's full path. Otherwise a post copied
     from one of its examples would be blocked once by decision 122, until
     the agent rewrote the command.

Adam gave 136 to 139 on 2026-10-20, answering findings raised while
recording decisions 131 to 135:

136. **During an Igor's run, a question with a category raises igor's
     bare flag in the worker's report.** Whenever the skill gives a
     question a category (`vulnerability`, `secret` or `personal`) during
     a run, whatever its verdict, the worker's report carries the flag
     igor PR #216 defines: that the run met a question with a category,
     with no category, question or answer. #216's task-execution
     requirement *Transcripts and outcomes are captured to the state
     branch* says what the Igor does with the flag, and applies the same
     rules when the Igor runs the skill itself. A worker that such a
     question stops reports only that flag, never the question's
     category. This amends decision 67 for an Igor worker. *Amended by
     Adam's decisions 244 and 245: the flag lists every category met in
     the run, marking those of the questions the run stopped on.*
137. **A question another installed skill requires a person to decide is
     exempt from filter 2 as well as filters 3 and 4.** It is asked now,
     and only filter 1 still applies. This amends decision 74.
138. **The closed credential list adds `sk-ant-`, Anthropic API keys, and
     `ghu_` and `ghr_`, GitHub's user-to-server and refresh tokens.** This
     amends decision 99's item 2.
139. **A command that runs code given inline, and whose code names `gh`,
     is unreadable.** The reader already reports `sh -c`, `bash -c`,
     `ruby -e` and `perl -e` that way, since none of them is one of
     prose's data commands. Three data commands can also run code given
     on the command line: `python` or `python3` with `-c`; `node` with
     `-e`, `--eval`, `-p` or `--print`; and `git` with `-c`, which can set
     an alias that runs a shell command. Run that way on code that names
     `gh`, each is now unreadable too. `python`, `python3` or `node`
     reading its program from standard input, such as a heredoc or a
     pipe, no longer counts as a data command under the reader's rule for
     pipes and input, so a command line that mentions a gh post verb and
     feeds one of them its program is unreadable. Both post hooks,
     prose's and the inquisitor's, use the shared reader, so both block
     such a command. This amends
     decision 114, which kept prose's data commands as they stood. Adam
     kept every one of these forms on 2026-10-20.

Adam gave 140 to 142 on 2026-10-20, answering findings of spec-check's
consistency read of the change before commit d93f48b:

140. **A file on a lore `questions` branch is never changed once
     pushed.** It counts as `decision` only when no commit after the one
     that added it changed it, and decision 78's proof is made on that
     adding commit: the signature it carries, or the comment the file
     links. A later answer to a question already logged there is pushed
     as a new file, holding the question and the answer, and proven on
     its own adding commit. A file changed after it was added is input,
     so a proof always covers what the file now says. This amends
     decisions 78 and 100.
141. **Task 0.12 is measured now, before this pull request or igor PR
     #216 lands,** so that gate two can build everything at once. Task
     0.12 measures whether an Igor worker can run this skill, with a lore
     clone and `inquisitor.json` in reach. It no longer waits on #216's
     task 4.1, which could not run until this pull request had landed.
     Measured on 2026-10-20: a worker can't run the skill (design.md
     gives the evidence), so gate two builds everything except
     Igor-worker mode, the spec's name for how the script runs in an Igor
     worker.
142. **An Igor worker pushes nothing to a lore repository,** since it
     holds no credential for one. Each question file, miss file and
     `authority: agent` file it would push to a `questions` branch goes in
     its report instead, and its Igor pushes it. igor PR #216 records the
     Igor's side in its requirement *An Igor publishes the questions-branch
     files its worker reports*, which pushes these files when it would push
     the run's citations. Decisions 145 and 149 say which of these files
     the Igor pushes.

Adam gave 144 to 146 on 2026-10-20, while task 0.12's result was being
recorded, and 147 the same day, on how UI work goes through pull
requests. He gave 144 to 146 for igor PR #216 too, which records them as
its decisions 23, 21 and 22. They are recorded here where this change
touches them:

144. **In an Igor worker, igor runs filter 1's lore search.** The worker
     calls a read-only search command igor provides, `igor lore-search`,
     which igor PR #216 specifies. igor searches its own lore checkout and
     `questions` branch with the role's scope, and returns its hits
     labelled as answers or as input, as filter 1 labels them. So in Igor-worker mode filter 1 calls that command instead
     of reading lore itself, and needs no lore clone, `inquisitor.json`
     or `gh`.
145. **An Igor pushes a question file its worker reports only when the
     file holds no answer, has `authority: agent` and `answered_by:
     agent`, or is a miss file,** and only at a path not already on the
     branch. It pushes no other file, such as one with `authority:
     decision`. This narrows decision 142, and decision 149 extends it.
146. **In the rules for a question with a category, an Igor's run is the
     whole execution on the item,** not only one worker's part of it.
     This applies to decision 136's flag, the mark a worker's report
     carries when its run meets a question with a category.
147. *Amended by Adam's decisions 254 (item 3) and 261: a screen that
     a spec's task names, to be designed at implementation from the
     patterns of the feature's approved prototype, is built without a
     prototype of its own, and AGENTS.md says so. The spec still does
     not describe that screen; the task only names it.* **UI is prototyped, not specified.** Once Adam has used a UI's
     prototype and approved it, the UI goes straight to an implementation
     pull request: whether a UI works is easier to see than to read in a
     spec. The other parts of the same feature, such as its data flow,
     integrations, setup and rules, still go through the two pull request
     steps, spec then implementation. A spec names a UI only as an
     interface that the feature's other parts use, and does not describe
     the UI itself. `AGENTS.md` states the rule. This amends decision 30.

Adam gave 148 to 151 on 2026-10-20 for igor PR #216, which records them as
its decisions 25, 24, 26 and 27. They are recorded here where this change
touches them:

148. **A file on a lore repository's `questions` branch is in scope for
     every role whose Igor uses that lore repository,** whatever its
     `repository` key names. Before this, a search during a run showed
     only the question and miss files whose `repository` key named a
     repository the role works.
149. *Read with Adam's decision 229's item 4: the Igor, not the worker,
     sets the file's `authority`.* **When a worker re-works an item after a
     person answered its handback, the Igor pushes a log file recording
     the answer,** with an
     `answer_link` to the person's comment on that item. The file holds
     `authority: decision` when the person has write access to what the
     question concerns, and `input` otherwise. It is a new file that supersedes the
     unanswered one, as decision 140 has it. This extends decision 145.
150. **A run that counts as flagged pushes nothing to the `questions`
     branch,** citations included. A run counts as flagged when its
     worker reported decision 136's flag, or when the provider
     refused it over a usage limit before the worker's completed report
     (#216's decision 19). #216's decision 38 widens that: a run that ends
     without the worker's completed report, for any reason, counts as
     flagged (decision 221 here).
151. **igor's search returns no `questions`-branch file about a more
     private repository.** During a run, a file is returned only when the
     repository of the item the run works is no more visible than the
     repository the file's `repository` key names. A visibility that can't
     be read counts against returning the file. This limits decision 148.
     #216's decision 42 judges the file by the more private of its
     `repository` and its `asked_from` (decision 221 here).

Adam gave 152 to 169 on 2026-10-20, while using the answer session's
prototype and once he had approved its user interface. They are the answer
session's, which the `answer-session` spec covers; its interface is not
specified, by decision 147:

152. *The tag it is built from is v0.1-33 since Adam's decision 263.*
     **The answer session is where a person does nothing but answer the
     questions asked of them.** Questions reach it from the channels the
     person subscribes to, on GitHub, Linear and Discord, asked by agents
     running the inquisitor or by people. Each answer is posted in the
     question's thread by that surface's relay identity, a bot that posts
     for the person, and starts with `User says: `. Its interface is a
     Claude Code mod. Adam approved it on 2026-10-20 by using the
     prototype, and it is built at gate two from the tag task 6.1 names:
     the one decision 231 named, v0.1-30, until decision 263 made it
     v0.1-33.
153. **The answer session's configuration is a section of
     `inquisitor.json`:** its subscriptions, which are GitHub repositories
     or owners, Linear teams and Discord channels, and, for each surface, a
     reference to the relay identity. The relays' tokens stay with the
     github-app, linear-app and discord-bot skills.
154. **Setup is part of the answer session.** It runs in place of the
     queue when that section is missing or incomplete, and again on
     `/answer setup`. It offers channels to subscribe to, checks that each
     relay identity can post, and writes the JSON, which stays editable by
     hand. How it looks is prototyped, not specified.
155. **A relay check that fails keeps that surface off.** Setup shows the
     failure and how to fix it, saves the rest, and leaves that surface's
     channels off until a check passes.
156. **A question asked of the person is one of four things:** an
     @-mention of them in a subscribed channel, agents running the
     inquisitor included; a reply to or mention of their relay identity; a
     pull request requesting their review or an issue assigned to them;
     or a question file on a lore repository's questions branch addressed
     to them.
157. **The answer session polls; it uses no webhooks.** A webhook needs a
     public HTTPS server, and Discord's push needs a permanent connection,
     so either would be a service to run. GitHub's notifications endpoint
     answers conditional requests that, by GitHub's documentation, don't
     count against the rate limit (task 0.15 measures it), and sets the
     interval between polls, usually 60 seconds.
158. **Polling runs only while an answer session is open:** about every
     60 seconds, with a catch-up poll on opening. No poll runs while no
     answer session is open.
159. **Reading uses the person's own credentials,** their `gh` login,
     their Linear key and their Discord identity. Relay identities only
     post.
160. **An answer's durable record is the relay identity's reply in the
     question's thread.** Answered, and waiting for the asker (the relay's
     last message is a question to them), are both read from the threads,
     kept current by polling. When a question comes on screen and its
     channel's last poll is more than about a minute old, the answer
     session fetches the thread's replies since the question and shows
     them all. The relay's own reply marks the question answered; other
     replies are shown to the person and leave the question's state as it
     was. Relaying checks the thread once more.
161. **Local state lives in
     `${XDG_STATE_HOME:-$HOME/.local/state}/inquisitor/answer-session/`:**
     questions set aside for later, discussion records, poll positions, and
     the question on screen, so that `answer` and `/answer` reopen on it
     even after Claude Code restarts. It is all per machine, the person's
     working state rather than a record: a question set aside on one
     machine is new on another.
162. **One answer session runs per machine.** A lock in the state folder
     names its holder, by session name, whether it is a Claude Code
     background session (one with no terminal attached, such as a
     session picker starts),
     and its start time, and the holder refreshes it, so a crashed holder's
     lock goes stale. A second `/answer` says which session holds the lock
     and offers to attach to it or take over. No TLA+ model is written:
     one person, one writer per machine. design.md gives the reasoning.
163. **A rephrased question is logged with its rephrasing and a
     one-sentence summary of the discussion** in the question's log file, in the
     one log-file format. Whatever that format needs for this goes into
     its requirement, *A log file and a miss file have one format*.
164. **The relay keeps each post's id,** so an answer or a question to the
     asker can be edited later, where it was posted.
165. **Discord is in the first version,** through the `discord-bot` skill
     of shared-skills PR #1, which gives each role a named bot identity
     with no service to run. Adam will merge #1 first. The Discord relay
     is a `discord-bot` identity.
166. **Two ways in:** `/answer` in any session, and an `answer` terminal
     command that setup installs, which starts a session with `/answer` as
     its first prompt. The command runs
     `CLAUDE_CODE_NO_FLICKER=1 claude --name Answers '/answer'`, which runs
     fullscreen in the terminal it is started from, where clicks work. No environment variable opens
     the answer session: neither way in needs one, and a session started
     from a session picker can't set one. Fullscreen is the layout the
     answer session is designed for and launched into. It works on Claude
     Code's main screen too, but nothing is designed or built for that
     screen alone.
167. **A discussion of a question runs in the session's own
     conversation,** with the question attached to each message as
     context, so the model can read the thread, the code and the specs
     before it replies. It reads with its tools, and posts and changes
     nothing.
168. **Claude drafts a reply only into the prompt box.** The answer
     session gives the model a tool, `propose_reply`, which puts its draft
     in the prompt box and posts nothing. The person edits the draft and
     relays it as any answer. The same holds when they are editing a post.
169. **The person can ask the asker instead of answering,** when they
     can't answer without clarification. The question then waits for the
     asker's reply. An Igor's worker asks in its handback comment and is
     gone (decision 126), so a reply to its question reaches whichever
     worker next takes the item. Asking back is therefore mostly for
     people's questions.

Adam gave 176 and 177 on 2026-10-20, answering two questions this change
had left for him:

176. *Narrowed by Adam's decision 204.* **A plain or bold line ending in a
     colon can begin an open-questions section,** as a heading can, so
     that an agent's "Open questions:" line counts. Decision 204 lets only
     a label that names questions begin one. This decision first let any
     colon line starting with "Open" begin a section, "Open a terminal and
     run:" included.
177. **A session with a person in it, on a host with no picker, asks in the
     text of its reply,** once the script's two calls have vetted the
     question. No hook checks a question there, as decision 21 says. The
     rule that an agent never asks in its reply holds only where the host
     has a picker. Wherever the spec has a session with a person in it ask
     through the picker, such a host's session asks in its reply instead.

Adam gave 178 to 180 on 2026-10-20 for igor PR #216, which records them
as its decisions 28, 30 and 32. They are
recorded here where this change touches them:

178. **An Igor checks each questions-branch file it pushes for a worker
     with the credential matcher of igor PR #217,** which matches the
     values of known secrets, such as the worker's seat token, as well as
     this change's credential patterns.
179. **An Igor pushes a worker's log file holding a person's answer only
     when the file's question matches the question the Igor posted in the
     handback comment that the person's comment answers.** A worker
     steered by text in its item could otherwise pair a real comment with
     another question. This narrows decision 149. #216's decision 41 takes
     the posted questions from the Igor's own record, and decision 221
     here matches them by the hash of each question's reduced text.
180. **When every push an Igor made of its workers' citations failed,
     igor's review shows citations as "not checked",** not as a count, even
     if people's own sessions pushed some citations. A count would then
     show none for every entry only Igors cited. When at least one Igor
     push succeeded, each count stays a lower bound (decision 98).

Adam gave 184 to 196 on 2026-10-20, answering the nine questions this
change had left him about the answer session and adding three rules to
it:

184. *Amended by Adam's decision 216: the App must be one the lore
     repository's relay file lists as the person's relay, and owning it
     no longer counts. Read "an App GitHub reports as owned by the
     person" below as that.* **A relayed
     answer counts as the person's own for filter 1.** A
     GitHub comment that starts with `User says: `, whose author is a
     GitHub App that GitHub reports as owned by the person's account,
     counts as that person's comment wherever filter 1 reads who wrote a
     comment. That is what lets decision 78 prove `answered_by` for an
     answer relayed on GitHub, and what lets an Igor log a person's
     answer to its handback with `authority: decision` (decision 149). It
     holds because only the answer session makes a `User says: ` post,
     and only on the person's confirmation (decision 193). This replaces
     the reading under which a relayed answer was only input. Task 0.21
     was to measure that GitHub reports an App's owner for a comment;
     since decision 216 it measures only which App wrote the comment.
     Until it does, a relayed answer stays input.
185. **On Discord, one `discord-bot` identity both reads and relays.** The
     bot reads and posts in the channels it has been added to. There is
     no separate identity for reading, and no `read` key. A Discord user
     account can't be automated within Discord's terms, so this is the
     one surface the answer session reads with a bot. This amends
     decision 159 for Discord, and replaces decision 175's item 2 there.
186. **The person's Linear API key lives in the system keychain,** as
     decision 175's item 2 has it.
187. **A failed relay check turns off only that channel,** not its whole
     surface. A check of the identity itself, such as its skill's own
     check or, on Discord, reading message content, concerns every
     channel of its surface, so when it fails each of them is off. This
     amends decision 155.
188. **A second `/answer` opens nothing while another session holds the
     lock.** It says which session holds it, by name and whether it is a
     Claude Code background session, says how to reach that session, and
     offers to take over. This is what decision 162's "attach" means.
189. **A Linear issue assigned to the person counts as a question,** as an
     assigned GitHub issue does. This amends decision 156's third source.
190. **A question's discussion record is deleted once the question is
     answered,** so decision 161 does not amend decision 32: the state
     folder holds a discussion only while its question is open.
191. *Amended by Adam's decision 238: PR #1 has added the step this
     decision asked for; its setup has the person turn the intent on.*
     **The Discord relay needs Discord's Message Content intent,** as
     decision 175's item 17 says, and shared-skills PR #1's README, the
     `discord-bot` skill's, should say how to turn it on. That is PR #1's
     to add.
192. **A handback question reaches the person only through an
     assignment.** An Igor worker's handback comment tags no one, so its
     question is shown only when its item is assigned to the person.
193. **Only the prefix is reserved.** A relay identity may be used for
     other work, but a post that starts with `User says: ` or
     `User asks: ` is made only by the answer session, on the person's
     confirmation. Decisions 195 and 196 reserve `Recorded answer: ` and
     `Inquisitor: ` the same way, for the posts the answer session makes
     by itself. This replaces decision 175's item 16. On GitHub only an
     App the relay file lists speaks for the person (decision 216).
194. *Reasons renumbered by Adam's decision 330: reasons 1 and 2 merge as "Nothing to answer", and reason 3 becomes reason 2. The notes below and the body use the old numbering.* *Reason 1 changed by Adam with decision 202's item 2 and his
     decisions 283 and 291; reasons 2 and 3 changed by his decisions 208,
     209 and 298; by 298, reason 2 logs no miss, so reason 2's lesson
     candidate below is no longer logged. For reason 1 now: declining as over closes only that
     question, and every later message in its thread that the answer
     session's four sources of questions name is a new question.* **The person can decline to
     answer.** On any open question they can choose not to answer. They
     give one of three reasons:
     1. *Superseded by decision 291; as first written:* **The
        conversation is over.** Nothing is posted, and the question
        closes. The asker's later comments in its thread that reply to no
        relay post, such as an unthreaded follow-up in a GitHub
        conversation, stop counting as questions. A threaded reply to a
        relay post, such as a Discord reply to it, still counts, and
        reopens the question, unless a handled file closed it (decision
        283). *Since decision 291, every later message the sources name
        is a new question, and nothing reopens the declined one.*
     2. **Not a question:** the message was picked up by mistake. Nothing
        is posted, the question closes, and a lesson candidate is logged
        against the way the answer session found the message, meaning the
        source of questions that picked it up, for the review of
        misses.
     3. **The inquisitor should have handled it:** one of filters 1 to 4
        should have stopped it. The answer session answers for the
        inquisitor with the reply of the filter the person picks, and logs
        a miss against that filter, as decision 209 says.

     A question declined with nothing posted is closed per machine, as
     setting a question aside for later is: it does not reach the
     person's other machines. Before decision 208, reason 2 was named "not
     a real question", filter 3's name. Before decision 209, reason 3 had
     the session's model ask the person which filter should have stopped
     the question, and why.
195. **The answer session runs filter 1 on every incoming question,**
     whether a person or an agent asked it, before showing it. When an
     answer with authority is recorded, the answer session answers by
     itself: it posts through the relay, starting `Recorded answer: ` and
     giving where the answer is recorded, never starting `User says: `.
     The question is listed for the person as answered for them, and they
     can edit that post as any relay post.
196. *Renumbered by Adam's decision 330: reason 2 here is now part of reason 1, and reason 3 is reason 2; the notes below use the old numbering.* *Amended by Adam's decision 298: a rhetorical message in the queue is declined under reason 2, logging no miss, or under reason 3 with the filter the asking agent should have applied, logging a miss against that agent.* *Amended by Adam's decisions 285 and 292: there is no rhetorical
     case; a rhetorical message in the queue is declined under reason 2,
     picked up by mistake.* *Amended by Adam's decision 234: the asking agent acts on an
     automatic `Inquisitor: ` reply only when it names filter 2, and on
     filter 3's or 4's reply only when the person chose it under decline
     reason 3.* **The answer
     session judges every incoming question by filters 2 to 4 too.** When a question clearly fails one of them:
     - for an agent's question, the answer session replies by itself
       through the relay, starting `Inquisitor: ` and naming the filter,
       with that filter's action: under filter 2, carry on without an
       answer, list the question as not done, and file an issue if it
       outlives the work; under filter 3, take the option that has merit
       and record it; under filter 4, pick one and record what and why. A
       rhetorical message has no case of its own (decision 285; as first
       written, it got no reply, and decision 284 briefly gave it a text
       of its own). The answer session also logs a
       miss against that filter, and lists the question for the person as
       handled for them;
     - for a person's question, it only shows the person its suggested
       verdict, and the person decides.

     Any unclear case goes to the person. No post the answer session makes
     by itself is presented as the person's words, and each can be edited.
     `Recorded answer: ` and `Inquisitor: ` are reserved as `User says: `
     is (decision 193).

Adam gave 204 to 212 on 2026-10-20, answering the questions this change
had left him and the findings of the previous review round of this pull
request. The same day he
confirmed 181 to 183 and 197 to 203, amended 199, changed four items of
202, and kept every form decision 139 makes unreadable:

204. **An open-questions section begins only at a label that names
     questions,** such as "Open questions:", "Open question:", "Still
     open:" or "Questions:", as a plain line, a bold label or a heading.
     It runs to the next heading or bold label. A line such as "Open a
     terminal and run:" begins nothing. The spec reads a label as naming
     questions when its first words, apart from a trailing colon, are
     "Open question", "Open questions", "Still open", "Question" or
     "Questions". Decision 113's deferral labels, such as "Not in this
     change", still begin a section, as Adam's decision 218 keeps them.
     This narrows decision 176.
205. **Until task 0.13 shows that GitHub merges an advisory's private-fork
     pull request only at publication, a security fix's regression test
     goes in that fork only when the person who will publish the advisory
     has said the pull request merges at the moment of publication.**
     Otherwise the test waits, and lands publicly once the advisory is
     published. A regression test is a working exploit, and a fork pull
     request merged before publication would put it on a public branch
     early. Decision 127 holds a fork commit's message to the public rule
     until the same measurement. This amends decision 108's item 4.
206. **A question in a post's title is vetted.** The shared post reader
     reads a post's title, an issue's or a pull request's, as well as its
     body, and both post hooks, prose's and the inquisitor's, check it.
     The inquisitor's post hook finds a question in a title as it finds
     one in a body's running text, a sentence ending in a question mark,
     and blocks it until it is vetted. A title the reader can't read
     exactly, such as one built with `$(…)`, makes the call unreadable,
     and both hooks block an unreadable call. Adam's decision 217 has
     prose's hook check nothing else in a title.
207. **When filter 1 answers an agent's question by itself, the answer
     session logs a miss against filter 1,** since the agent's own filter
     1 should have found the record. A person's question logs none. This
     replaces decision 202's item 7.
208. *Merged into reason 1, "Nothing to answer", by Adam's decision 330.* *Amended by Adam's decision 298: reason 2 logs no miss.* **Decline reason 2 is called "not a question":** the message was
     picked up by mistake. It no longer shares filter 3's name, "not a
     real question". A miss logged for it has `said: "not a question"`.
     This renames the reason in decisions 194 and 198 and in the spec.
209. *Amended by Adam's decision 264: a filter 1 reply with a more
     private record is posted on the person's confirmation, after a
     warning.* **Decline reason 3 is called "the inquisitor should have handled
     it", and the answer session then answers for the inquisitor.** The
     person picks the filter that should have stopped the question: 1,
     already answered; 2, can wait; 3, one option has merit; or 4, cheap
     to reverse. The answer session posts that filter's reply. For
     filters 2 to 4 it is the fixed `Inquisitor: ` text decision 200
     defines. For filter 1 it is a `Recorded answer: ` post naming the
     place the person gave or the model found, under decision 200's
     privacy rule: when the record is more private than the thread,
     nothing is posted, and the recorded answer is shown to the person
     instead. The person sees the exact post first, and it goes out only
     once they confirm it; Adam described that as pressing Enter, and how
     it looks is prototyped (task 6.9). The miss is logged against that
     filter, with any note the person typed. This holds for people's and
     agents' questions alike, since the person chose it, and these posts
     start with the reserved prefixes, as the automatic ones do. The
     person can still answer on the surface by hand. This replaces the
     model's follow-up question, which asked which filter and why: it
     supersedes decision 202's item 4, and decision 174's exception no
     longer needs to cover it.
210. *Amended by Adam's decisions 299 and 302: the file is shown once, from the post, only when its `asked_in` links the post, or when the machine showing them merges them under decision 307.* **A questions-branch question that was also asked in a post is
     answered in its thread too.** The answer session shows it once, from
     the thread (decision 175's item 11), relays the person's answer there
     as usual, and pushes the log file that records the answer to the
     questions branch. With no thread, the file alone answers it. This
     amends decision 173. Decision 220 has an edit of that answer push a
     new log file too.
211. **Three costs Adam accepts:**
     1. The discussion's model runs with the person's tools, so it could
        reach the keychain entry that holds the person's Linear key.
     2. Only a question's latest relay post can be edited.
     3. Where no check can read whether a relay identity may post in a
        channel (task 0.20), a post the surface refuses turns that channel
        off until a recheck passes. That comes on top of decision 202's
        item 9: nothing is posted, the person is told why, and the
        question keeps its state.
212. **igor's search applies this change's authority checks.** This
     change states its authority checks once, in the spec's requirement
     *Only an answer with authority stops a question*. igor's
     `lore-search` applies them before it labels a questions-branch file
     as an answer, and shows the file as input, labelled unconfirmed,
     whenever a check can't run or fails. igor PR #216 records igor's side
     as its decision 34.

Adam gave 213 and 214 on 2026-10-20 too, answering questions igor PR
#216 raised about those checks:

213. *Replaced by Adam's decision 236: equality, not containment.*
     **A linked comment holds a log file's recorded answer by normalized
     containment.** Both texts are reduced as a question is reduced for
     its hash, with no list marker or inline markup and with whitespace
     joined, and a leading `User says: ` is dropped from the comment. The
     comment must then contain the file's answer line. No model call
     judges it. The spec defines it once, beside the writer proof, so
     igor and every other reader apply the same rule. igor PR #216
     records it as its decision 43.
214. **During an Igor's run, a questions-branch file whose `repository`
     key names a repository other than the item's always shows as
     input.** That is intended: the file informs, and decides nothing
     until it is proven where it belongs. The spec says so where it
     states the proofs. igor PR #216 records it as its decision 44.

Adam gave 216 to 220 on 2026-10-20, answering the five questions this
change had left him, and confirmed decision 215 item by item. He gave 221
the same day, in the session reviewing igor PR #216. Its items 1 and 4
answer the two questions this change had left for #216, on the question
match and on a worker-written `repository` key; items 2 and 3 are #216's
rules this change relies on:

216. *The relay file amended by Adam's decisions 224 and 225: one file
     per person, tied to them by who last changed it, with no review.*
     **Only an App listed as a person's relay speaks for them on GitHub.**
     A `User says: ` comment counts as a person's answer only when its
     author is an App listed as that person's relay in a file on the
     default branch of the team's lore repository. The answer session's
     setup proposes that file by pull request. An answer from any other
     App the person owns, an Igor's included, is input: igor's own code
     posts its worker's text with no hook seeing it, so a worker steered
     by its item could start a comment `User says: ` and prove a
     questions-branch `decision` file. Adam first had the file change only
     through a reviewed pull request, and left its name and shape to this
     change, which chose one shared `relays.yaml` keyed by login; decision
     224 replaces that with `relays/<login>.yaml`. The spec defines it once,
     as *a person's relay file* and *a person's relay App*, and the writer
     proof, the reading of an `Inquisitor: ` reply (decision 215's item 1)
     and the post hook's reason (decision 203) use those terms. This
     amends decision 184, and task 0.21 now measures only which App wrote
     a comment. igor PR #216 records that an Igor's App never relays a
     person's answer as its decision 45, which points here once this
     change states the rule.
217. **prose's hook checks only that a title is readable,** blocking a
     title the shared post reader can't read. A title gets the
     inquisitor's vetting of its questions, and no prose pass.
218. **Decision 204 keeps decision 113's deferral labels:** a section that
     starts at "Not in this change", "Deferred" or "Not done" still lists
     deferred questions.
219. **No automatic post repeats one already made anywhere in that chain
     of replies,** meaning the reply, the relay post the reply answers,
     the question that relay post names, and so on back. A repeat goes to the
     person. Before, only the post the reply answered was checked, so an
     agent that kept replying could get filter 2's text, filter 4's, then
     filter 2's again with no person seeing it. This amends decision
     202's item 6.
220. *Amended by Adam's decisions 312 and 319: among answer files naming the same file in `answers`, the newest is that file's answer, while filter 1's search still groups every answer file by hash.* **Editing a relayed answer that decision 210 also logged pushes a
     new log file with the edited answer,** and the newest log file for
     that question counts. A file on a questions branch never changes
     (decision 140), so without a new file the branch would keep the
     first answer. Decision 222's item 1 says how the spec reads "newest".
221. **Settled with Adam on igor PR #216, closing two questions this change
     had left for #216:**
     1. The match of decision 179 uses the Igor's own record of the
        questions it posted in its handback comment, never the comment's
        current text, and two questions match when they are equal once
        each is reduced as this change reduces a question for its hash
        (#216's decision 41, which replaces its decision 30's readings).
     2. A run that ends without its worker's completed report, for any
        reason, counts as flagged (#216's decision 38, which extends its
        decision 19).
     3. The Igor reads the lore repository's visibility at every push
        (#216's decision 37, which amends its decision 16).
     4. The Igor adds the run's own item repository to every log and
        miss file it pushes to the questions branch, as a key named
        `asked_from`, and
        a search treats a file as being as private as the more private of
        its `repository` and `asked_from`, so a steered worker can't
        launder a private question by writing a public `repository`
        (#216's decision 42, under which the Igor sets the key after its
        format check, and refuses a worker's file that already holds
        one). This change owns the file format, so it adds
        the key to decision 125's closed list: only the Igor writes it,
        it holds the item's repository as `owner/repo`, and this change's
        own readers judge a file's visibility by the same rule.

Adam gave 223 to 226 on 2026-10-20, answering decision 222 and the
question this change had left him on how the relay file reaches the
default branch. With them he confirmed items 1, 3, 4, 5, 7 and 8 of
decision 222:

223. **A relayed question is a person's question, and decision 195 still
     applies to it.** A `User says: ` or `User asks: ` post from any bot
     account is the words of the person whose answer session posted it,
     such as another person asking this one something through their own
     relay, so it counts as a person's question (decision 222's item 2). Filter
     1 can still answer it by itself from the record, posting
     `Recorded answer: `, as for any person's question; filters 2 to 4
     only suggest a verdict to the person, and never post `Inquisitor: `
     on it by themselves; the person can still choose to post one under
     decline reason 3, "the inquisitor should have handled it" (decision
     194). This reconciles decision 222's item 2, which had such a post
     get no automatic post at all, with decision 195, and corrects
     decisions 199 and 215's item 6 to match.
224. **One relay file per person, modelled on igor's seat files.** A
     person's relays are in `relays/<github-login>.yaml` in the team's
     lore repository, read from its default branch, holding that person's
     `github` (App slugs), `linear` and `discord` lists; only the `github`
     list proves anything. The person adds or changes the file with their
     own pull request, and the answer session's setup proposes it. This
     replaces decision 222's item 6, the one shared `relays.yaml`, as igor
     issue #148 and igor PR #171 give each lender a `seats/<id>.yaml`
     that their own pull request adds.
225. **No review is required: ownership ties the file to its person.** A
     reader counts `relays/<login>.yaml` only when its last change came
     from that login: the person authored the pull request that last
     changed it, or the last commit to it is a verified commit of theirs.
     Otherwise the file lists no relay, as decision 222's item 3 has it
     for a missing file. A notice @-mentions the person on any pull
     request touching their file, as igor's seat-notice workflow does for
     a seat file (decision 228 says who sends it). This answers the
     question this change had left him. Its recommendation had three
     parts: rely on the lore repository's branch protection, have setup
     warn when the default branch required no review, and have task 0.22
     measure whether setup could read that rule. None of the three is in
     the spec any longer; task 0.22 now measures what a reader needs for
     the ownership check.
226. **Declining and the list of questions answered or handled for the
     person are already prototyped,** with declining's three reasons and
     reason 3 answering for the inquisitor, in builds v0.1-28 to v0.1-30
     of the answer-session prototype, on shared-skills' branch
     `prototype/answer-session-ui`. They await his approval by use, so
     task 6.9 now says that, not that they still need prototyping.

Adam gave 229 on 2026-10-20 too, in the session reviewing igor PR #216,
which records it at 6d5df39 as its decisions 49, 52 and 53; this change
aligns with it:

229. **igor's search and filter 1 search alike.**
     1. An inquisitor run an Igor starts itself, with no worker, searches
        lore through `igor lore-search`, as a worker does, so the script
        reads no lore clone during any Igor's run and never needs to know
        which lore repository the Igor injects from. This replaces the
        script's search in such a run, and its fallback of searching no
        lore when it couldn't tell which lore repository that was (#216's
        decision 49).
     2. Both match plain text, with no embedding and no model call: the
        question's terms against a lore entry's claim, conditions and body,
        and against a question file's question. Both rank hits by the
        number of terms matched, show at most 20, and say when they left
        hits out (#216's decision 52). Filter 1's requirement now states
        the ranking and the cap; before, it stated only the fields
        matched.
     3. #216's visibility rule for a questions-branch file (its decision
        27) applies to a `project:` lore entry too (#216's decision 53).
        This change points to #216 for that rule and says nothing
        contrary.
     4. The Igor, not its worker, sets `authority` on each questions-branch
        file it pushes, under the authority checks of the spec's *Only an
        answer with authority stops a question*, reading a person's relay
        file from its lore checkout's fetched default branch, never its
        working tree. The worker's report holds the file, and the worker
        decides nothing about it. This amends decision 149's reading, under which the
        worker wrote `authority` for a handback answer. Adam's decision 241
        later moved the read to the commit igor PR #208 last applied.

Adam gave 231 on 2026-10-20 too, after testing the prototype:

231. *Amended by Adam's decisions 254, under which the spec wins where
     the prototype disagrees with it, and 263, under which the mod is
     built from v0.1-33, a descendant of this build.* **The whole answer-session UI is approved by
     use.** The approved
     build is v0.1-30, commit c9c6eb5, tagged
     `answer-session-ui-approved-v0.1-30` on shared-skills
     (`ui-approved-v0.1-30` in Adam's local prototype repository). It
     includes declining, with its three reasons and reason 3 answering
     for the inquisitor, and the list of questions answered or handled
     for the person. Gate two was to build the mod from that tag, until
     decision 263 named v0.1-33, which descends from it. The tag replaces
     the earlier `answer-session-ui-approved` (f964903), which lacked
     those screens. Task 6.9 is done.

Adam gave 232 to 237 on 2026-10-21, answering the three questions this
change had left him (how a reader recognises an Igor's App, the relay
token any agent can reach, and agents acting on an automatic
`Inquisitor: ` reply), ruling on decision 230, and settling the answer rule with
igor PR #216. He gave 238 in shared-skills PR #1, on 2026-10-20 and
2026-10-21:

232. **An Igor's App is recognised by its slug prefix.** igor requires
     every Igor's App slug to start with `igor-`: an Igor whose App's slug
     lacks it refuses to start (igor PR #216's decision 62). A reader
     never counts a relay-file entry whose slug starts with `igor-` as a
     relay. This replaces decision 230's withdrawn item 4 and this
     change's recommendation of a `relays/_igor.yaml` listing the Igors'
     Apps, and answers the question decision 222's item 7 left open.
233. **github-app refuses its `token` command for an identity marked as a
     relay,** so only the answer session's own posting command can post
     with it. That is a change to the github-app skill, which this change
     depends on and does not make. Until it ships, the cost is accepted:
     any agent on the person's machine can print a relay App's token and
     post `User says: ` with a plain HTTP call no post hook sees, and the
     inquisitor's README says so.
234. **An agent acts only on an automatic `Inquisitor: ` reply naming
     filter 2,** which only defers. An automatic reply naming filter 3 or
     4 is input, since a crafted thread can choose which fixed reply the
     answer session posts by itself, and those two decide a question. A
     reply naming filter 3 or 4 counts when the person chose it under
     decline reason 3, which the reply then says. Decision 215's item 1
     still applies to every reply an agent acts on. This amends decisions
     196 and 215's item 1.
235. **The script detects an Igor's run by `IGOR_RUN`.** igor sets it to
     `worker` in a worker's environment and to `igor` in the Igor's own
     inquisitor run, and it holds no secret (igor PR #216 at ba154a0). The
     script matches it by exact name, since igor also has
     `IGOR_RUN_TOKEN`, a seat's token, and by exact value, so that any
     other value marks no run. In either run it reads no lore clone and
     pushes nothing to a lore repository, a citation included; under
     `worker`, filter 1's other sources are read only from the worker's
     working tree, as a worker's search already is. The earlier rule for
     a session with no person in it is gone: a plain headless session,
     such as `claude -p`, keeps its normal lore search. This replaces decision 230's item 5.
236. **One answer rule for writers and readers.** Whoever logs an answer
     from a comment (the Igor, the script, the answer session) records
     the comment's own text word for word as the answer, never a
     worker's or model's paraphrase, even when it has several sentences or
     quotes the question. A reader confirms a logged answer only when the
     linked comment and the recorded answer are equal once both are
     reduced: no list markers or inline markup, whitespace joined, and a
     leading `User says: ` and a trailing `Re: <URL>` line ignored.
     Containment is gone, since it let "merge it." match "Do not merge
     it."; a worker's line only identifies which comment holds the
     answer. The log file's format must hold a multi-sentence answer, and
     frontmatter `authority`, not body text, still decides whether a file
     is answered. This replaces decision 213. igor PR #216 records the
     writer side as its decisions 67 and 70 and the reader side as its
     decision 72, which points here.
237. **Relay files and the questions branch live in igor PR #208's
     `destination` repository,** beside the lore entries, when it differs
     from the repository holding the Igor's configuration (igor PR #216's
     decision 66). This change's lore repository is the one holding the
     entries, so that is where it reads both.
238. *Its last sentence amended by Adam's decision 246, which ended the
     wait for an option that kept Discord off.*
     **shared-skills PR #1 turns Discord's Message Content intent on**
     (Adam, 2026-10-20, PR #1's commit 369ae16), and its `check` reports
     `messageContent` as true, false or null, read from the bot's
     application flags (f83b167, decided by Adam on 2026-10-21). This
     amends decision 191, which had PR #1 leave it off. discord-bot
     turns an `@name` in a post into a mention that notifies that member,
     and decision 246 keeps that for relay posts. So whether Discord is
     on depends only on `check`'s report and setup's other checks, and
     no longer on discord-bot gaining an option to post with mention
     rewriting off.

Adam gave 240 on 2026-10-21, ruling on decision 239. He gave 241 to 243
the same day in the session reviewing igor PR #216, which records them
as its decisions 73 and 75 to 81. This change aligns with them and
points to #216 for igor's mechanics:

240. **A person's answer is recorded in their own words, never an
     agent's paraphrase.** An answer given in the picker, where no
     comment exists, is recorded as given: the option the person chose,
     or the text they typed, word for word, in the same `> ` quote lines
     under `## Answer` as a comment's answer. So no answer anywhere is an
     agent's paraphrase: an answer the person types in their own message
     in the session is recorded word for word too. Only an agent's own
     choice under filter 3 or 4 is in the agent's words. Because a
     person's words are never reworded, an answer holding context more
     private than what the question concerns is not recorded at all, as
     decision 239's item 4 has it for a comment. This changes decision
     239's item 2. Adam confirmed (2026-10-21) both readings this change
     took from 240: an answer whose words hold context more private than
     its question is not recorded at all, never generalised, and an
     answer a person types in their own message in a session is recorded
     word for word.
241. **An Igor reads relay files as of the commit igor PR #208's lore
     read last applied** (#216's decision 77). #208 applies only a
     commit that passes igor's startup checks, so the relay files of a
     commit it refused never count. That matches decision 225, under
     which a relay file whose last change cannot be shown to be its
     person's lists no relay. The check of who last changed a relay file
     (decision 227's item 1) reads the same commit. Outside an Igor, a reader keeps
     reading them from the lore clone's fetched default branch. This
     amends decision 229's item 4, which had the Igor read them from its
     lore checkout's fetched default branch, and settles the question
     this change had left open for #216.
242. **When #208 has applied no commit, the relay check cannot run.** That
     is so under `igor run`, which never fetches, and for a destination
     repository #208 never fetches. The Igor then cannot tell whether a
     `User says: ` comment came from a listed relay App, so it pushes such
     an answer as `input`; an answer in the person's own comment still
     counts (#216's decision 78).
243. **A flagged run asks nothing on the item, and its question stays on
     the Igor's host.** A flagged run is one igor counts as having met a
     sensitive question: its worker reported the flag (decision 136, with
     the categories decisions 244 and 245 add), or it ended without the worker's
     completed report (decision 221). Its handoff, the Igor's comment
     handing the item back, posts no question (#216's decision 73), gets
     no `igor:question` label, and reaches nothing in igor #211's
     inquisitor role (#216's decision 75). The Igor keeps the question in
     an operator-only file on its own host, never pushed, and the item
     stays held: a reply does not rerun it. What that file holds, and how
     a held item is released, are #216's, which this change points to
     rather than restates (#216's decisions 73, 75, 76, 79 to 85, 88, 89,
     95, 97, 98, 100 and 101 at d3b7740). In brief, the file holds the categories the
     worker's flag lists, the text of each stopped question that has no
     category,
     and the paths of the execution's session logs, moved beside it. The operator can always release the item on the
     host with `igor release <tracker>/<repo>/<item>` (#216's decision 84,
     whose form its decision 95 confirmed), and an attributable
     edit or label by someone with write access to the item's repository
     releases it too (#216's decisions 79 and 84).
     In this change, an Igor worker still asks only in its handback
     comment (decision 126), but when the run is flagged, the Igor posts
     the handoff that asks nothing in place of the worker's handback
     comment. So no log file records the question that stopped a flagged
     run: not from that run, and not from a later one, even though
     decision 183's item 6 would otherwise have a later run log it with
     its answer; this amends that item. The file on the host is
     igor's, and this change reads nothing from it. Decision 150 already
     has a flagged run push nothing to the `questions` branch. *This
     change aligned its description of igor's side with #216 on
     2026-10-21; Adam's decision itself is unchanged.*

Adam gave 244 on 2026-10-21 in the session reviewing igor PR #216,
answering its question on how the Igor learns a question's category
(#216's decision 89 had left it open):

244. **A worker that a question with a category stops reports that
     category with its flag.** The category is one word from this
     change's fixed list, `vulnerability`, `secret` or `personal`, with no
     other text. The Igor writes it only into its operator-only file on
     the host that keeps the question (#216's decision 89), never into
     the execution ledger, the state branch, a comment or a label. This
     amends decision 136, which had the worker report a bare flag.
     Decision 245 settles the two cases this leaves open: a question with
     a category that does not stop the worker, and several questions
     stopping it.

Adam gave 245 and 246 on 2026-10-21. 245 rules on the decision this
change had proposed under that number, and replaces it; 246 settles
decision 230's item 1:

245. **A flagged worker's flag lists every category met in the run, and
     marks those of the questions it stopped on.** The flag lists each
     category met in the run, `vulnerability`, `secret` or `personal`,
     each at most once, and marks which belong to the question or
     questions the run stopped on. The run here is one worker run: #216
     has each worker run, a model step after the worker included, report
     its own flag (its task-execution requirement). A category met on a question that did
     not stop the worker, such as one decided under filter 4, is listed
     too. The two lists are unpaired: the flag does not say which stopped
     question had which category, and there is no per-question format. A
     stopped question with no category adds nothing to the flag. The Igor
     accepts a word only when it is exactly one of the three. How the
     Igor stores what the flag carries, the case of several stopped
     questions included, is igor PR #216's. #216's decision 92 has the
     flag carry a category, and its decision 97 widens that to this
     rule. #216's decision 97 also fitted three details of its host
     file; Adam confirmed them, and #216 records that as its decision
     100. This amends decision 244, which
     left both cases open.
     As this change proposed it, 245 had a question that did not stop the
     worker add no category, and listed only the stopped questions'
     categories, in a fixed order. Adam reversed the first, and his
     decision sets no order.
     *Rejected:* one word per question, which tells the Igor how many
     questions of each category stopped the run. This change rejected it
     when it proposed 245, and Adam's decision, which has no
     per-question format, rejects it too.
246. **An @-mention in the person's own relayed answer pings that
     person.** The answer session's relay posts through discord-bot with
     its normal mention rewriting on, so an `@name` in the person's answer
     notifies that member. No option to post with mention rewriting off
     is needed. That option was wanted so that a quoted record's
     @-mentions would not notify people a second time, and since decision
     239's item 5 a `Recorded answer: ` post quotes nothing. Decision
     230's item 1 asked two things of a Discord relay post: no header
     line, and mention rewriting off. This decision drops the second.
     The first is met by shared-skills PR #1, merged. discord-bot's `post` adds a header only
     when `--agent`, `--session` or `--project` is given, and `header()`
     returns an empty string otherwise (`.agents/skills/discord-bot/scripts/discord_bot.py`
     on main at 90a0237). This amends decision 230's item 1, and the
     last sentence of decision 238, which had kept every Discord channel
     off until discord-bot gained the option.

Adam gave 247 to 249 on 2026-10-21, answering the three questions this
change put to him after recording 245 and 246:

247. *Amended by Adam's decision 252: edits too.* **After a Discord
     relay post, the answer session shows the person discord-bot's
     warnings,** so they learn when an `@name` pinged no
     one. discord-bot leaves an `@name` as plain text when no single
     member's name matches it, and warns for that name. When Discord
     refuses its member search (`check` reports `memberSearch: false`),
     every `@name` stays plain text, under one warning that says so.
     Setup does not fail the Discord relay when `memberSearch` is false.
     *Rejected:* failing setup on `memberSearch: false`.
248. **A questions-branch answer relayed on Linear or Discord is logged
     with that relay post as its `answer_link`, never fetched.** This is
     a question both on a questions branch and asked in a Linear or
     Discord thread, which the answer session answers in both places
     (decision 210). The log
     file records, word for word as quote lines, the text the answer
     session relayed for the person. `answer_link` holds the Linear
     comment's or Discord message's URL as a pointer: the `log` command
     never fetches it, and no non-GitHub link is passed to any GitHub API
     call. Only a github.com link is fetched, and its comment's text
     copied (decision 239's item 3). The log format's `answer_link` widens
     to allow these URLs. A non-GitHub link still proves no writer
     (decisions 78 and 183's item 3). Decision 250 has such a file count
     through the signature on its commit, and decision 251 writes the
     link only in a private lore repository.
249. **Igor-worker scenarios stay untagged until igor builds what they
     need.** Gate two, the implementation, tags no test of a scenario that only igor's
     unbuilt work, such as `igor lore-search`, can make pass, so
     spec-trace shows each as uncovered. design.md lists them as expected
     gaps, and task 4.3 tags each one once igor provides what it needs.
     spec-trace does not change. This replaces task 4.2's skipped,
     tagged tests, which spec-trace counted as coverage.

Adam gave 250 to 253 on 2026-10-21, answering the four questions this
change put to him when it recorded 247 to 249:

250. **An answer typed in the answer session counts through its log
     file's signature, whatever surface relays it.** When the person
     answers in the answer session a questions-branch question that was
     also asked on Discord or Linear (decision 248), the session relays
     the answer there and logs it from the person's machine. When the commit that adds the file
     carries a signature GitHub verifies for `answered_by` (decision
     78's item 2), the file counts as a decision, as an answer the
     person picks in Claude Code's picker does when the agent logs it
     with a signed commit. Without a verified signature the file is input. Its Linear or
     Discord `answer_link` stays a pointer that proves nothing (decision
     248). This narrows decision 109 to answers typed directly on
     Discord, Linear or Slack, which stay input until igor's scribe
     records them. *Rejected:* keeping decision 109 whole, so that every
     answer relayed off GitHub was input.
251. *Extended by Adam's decision 302 to `asked_in`.* **A Linear or Discord `answer_link` is written only when the lore
     repository is private.** Otherwise the log file is written without
     an `answer_link`, and still records the answer. A Discord URL holds
     the server's and channel's ids, and a Linear URL the workspace,
     issue and title. A Linear or Discord thread counts as private, so a
     lore repository that is not private is more visible than it, and
     the link would point its readers into the private workspace.
     *Rejected:* always writing the link; and writing no log file in a
     lore repository that is not private.
252. **The answer session shows discord-bot's warnings after an edit of a
     Discord relay post too,** as after a post, since an edit can drop a
     ping. This amends decision 247.
253. **This change is archived only after task 4.3 has tagged every
     expected gap,** the Igor-worker scenarios of decision 249, so
     spec-trace's CI never meets an untagged one in `openspec/specs/`.
     Task 7.0 already makes the archive wait for igor PR #216 to merge;
     this adds a second condition. *Rejected:*
     archiving the rest and leaving the Igor-worker scenarios in an open
     change.

Adam gave 254 to 257 on 2026-10-24, after an audit compared the approved
prototype, `answer-session-ui-approved-v0.1-30`, with the answer-session
spec:

254. **The mod is built from the approved prototype, and the spec wins
     where they differ.** Task 6.1 states the precedence:
     1. *Amended by decision 263: the base is v0.1-33, which descends
        from v0.1-30.* The mod is built from `answer-session-ui-approved-v0.1-30`, and
        keeps the approved screens' layout and interaction: the band, the
        keys, the prompt-box flow and the declining screens. Changes
        needed to wire them to real data are allowed; restyling or
        reorganising them is not.
     2. Wherever the prototype disagrees with the spec, the spec wins.
        Task 6.1 lists the cases the audit found.
     3. Screens the spec needs and the base build lacks are designed at
        implementation from the prototype's existing patterns, in no new
        visual style.
     4. *Amended by Adam's decisions 258 and 263: the tag is named
        before gate one is approved, and it is
        `answer-session-ui-approved-v0.1-33`.* A screen Adam approves separately is taken from its own approved
        tag. One separately approved build covers two screens: thread
        replies, and the recorded answer shown beside the question. Adam approved it as
        build v0.1-33 (decision 263), and task G.1 is done.
     This amends decision 231, which approved the whole UI by use, by
     saying how that approval meets the spec. Item 3 also amends
     decision 147 for the screens task 6.1's rule (c) lists, which ship
     with no prototype approved by use. Task 6.1's rules (a) to (d) are
     items 1 to 4 here.
255. *Amended by Adam's decision 298: no decline that can be reopened logs a miss, so no logged miss is left behind.* *Amended by Adam's decision 260: only a question declined with
     nothing posted.* **The person may reopen a question they declined.** Reopening puts
     it back in their queue. A miss already logged for it stays, since a
     miss file is never changed (decision 140), and nothing records that
     the miss was withdrawn.
256. *Narrowed by Adam's decision 264, which fixes what agreeing to a
     shown recorded answer posts; what agreeing with a suggested verdict
     posts stays open.* **Some details of the answer session are decided at
     implementation, not specified.** Task 6.11 lists them: how options
     are parsed from a thread; `propose_reply`, the tool Claude calls to put a draft reply in the
     prompt box, refusing a call from a subagent,
     which Adam confirmed; a draft's privacy; an asker's reply revising
     the options; what "agree" and "cite" post; Claude's draft, through `propose_reply`, filling the place the person
     gives when declining under reason 3 with filter 1, that is, the URL of
     the record for the `Recorded in: ` line,
     which Adam confirmed, since the draft lands in the prompt box for
     the person to confirm; and the relay notice's UI, the notice shown for the comment GitHub Actions
     posts when a pull request changes the person's relay file, under task 6.1's rule (c). No requirement is added
     for them. Decision 257 specifies one thing cite does beyond its post.
257. *Narrowed by Adam's decision 259 to an `active` entry in scope.*
     **Answering with cite pushes a citation file.** When the person
     answers by citing a lore entry, the answer session pushes a citation
     file for that entry, as filter 1's automatic case does (decision
     200's item 5), under the same visibility rules that withhold a
     citation from a place less private than the question.

Adam gave 258 to 261 on 2026-10-24, answering the four questions this
change put to him when it recorded 254 to 257:

258. **The separately approved build is approved, and its tag named,
     before gate one is approved.** Adam approves the new prototype
     build, covering thread replies and the recorded answer shown beside
     the question, before he approves this change's spec, and task
     6.1's rule (d) names the build's tag once he has. Implementation
     starts only after both, so no fallback is needed. *Rejected:*
     designing those two screens under rule (c) if the build were late.
259. **A person's cite pushes a citation file only for an `active` lore
     entry in scope,** as filter 1's citation does, and as igor PR #216
     pushes a citation only for an `active` entry. The
     person can still cite any other entry; that pushes nothing. igor
     PR #216 should widen its definition of a citation to include a
     person's cite (Still open). *Rejected:* a citation for any cited
     entry.
260. *Narrowed by Adam's decision 274: not for a question a
     questions-branch file holds.* **Reopening is offered only for a question declined with nothing
     posted.** After a post, the thread records how the question was
     handled, and the person changes that by editing the post. This
     amends decision 255. *Rejected:* reopening a question on this
     machine whatever its thread shows.
261. **AGENTS.md states the exception.** UI is prototyped and approved
     by use before it is built, except where a spec's task says a
     screen is designed at implementation from an approved prototype's
     patterns, as task 6.1's rule (c) does. *Rejected:* keeping the
     exception only in this change.

Adam gave 262 on 2026-10-24, answering the question this change put to
him when it recorded 258 to 261:

262. **Declining under reason 3 with filter 1, naming a lore entry as
     the record, counts as citing it.** Reason 3 is the decline reason
     "the inquisitor should have handled it"; with filter 1, already
     answered, the person names the record, and the answer session
     replies with a `Recorded answer: ` post whose `Recorded in: ` line
     names it, as the answer-session spec's decline rule has it. When that
     record is a lore entry, the answer session pushes a citation file
     for it under decision 259's rule: only when the entry is `active`
     and its scope covers the question, and nothing otherwise. The
     asking agent's rule (decision 215's item 3) is unchanged: it pushes
     no citation for an entry a `Recorded answer: ` post names. *Rejected:* having the
     asking agent push the citation when it acts on the post.

Adam gave 263 on 2026-10-24, approving the build decision 258 required:

263. **Prototype build v0.1-33 is approved by use, and is the mod's one
     base.** Adam approved build v0.1-33 on 2026-10-24, tagged
     `answer-session-ui-approved-v0.1-33` on shared-skills (commit
     fc3c35f; `ui-approved-v0.1-33` in his prototype repository). It
     covers the two screens of decision 254's item 4: the thread's
     replies since the question, and filter 1's recorded answer shown
     with the question, for a question from a questions branch as well
     as one in a thread. The replies and the recorded answer each have
     one place on screen, the one the tag shows, with no switch between
     layouts. The build also corrects the wording and placement of the
     notice for a stopped post, a post the answer session holds back because a reply arrived in the thread since the person last read it. It descends from v0.1-30, the
     whole UI decision 231 approved, and its three commits add only
     these, so v0.1-33 contains all of v0.1-30 and task 6.1 builds from
     it alone. This meets decision 258's condition on the build, and
     task G.1 is done; Adam's approval of this spec, the other condition
     before implementation, is still to come. By decision 265 the
     approval covers the whole build.

Adam gave 264 and 265 on 2026-10-24, answering the two questions this
change put to him when it recorded 263:

264. *Amended by Adam's decisions 266 and 270: agreeing writes no log
     file, and is a decline under reason 3 with filter 1, whose warning
     for a more private record this decision supplies.* **The person may agree to a recorded answer more private than the
     thread.** When a record is shown, not posted, because it is more
     private than the thread, agreeing to it posts `Recorded answer: see
     the record below.` with `Recorded in: <URL>`, after the screen warns
     that this shows the record exists and the person confirms. The same
     holds under decline reason 3, "the inquisitor should have handled
     it", when the person picks filter 1. Agreeing to a lore entry
     counts as citing it under decision 259's rule. On a question from a
     questions branch, decision 266 has agreeing write no log file. The automatic post's rule is unchanged:
     the answer session posts a recorded answer by itself only when the
     record is no more private than the thread. This amends decision
     200's item 4. *Rejected:* not offering `(a)gree` for such a record.
265. **The v0.1-33 approval covers the whole build,** the asker
     withdrawing their question in the thread (the prototype's twelfth
     sample question, its dot 12) and the stopped post's notice
     included, though the build's own notes, written before the tag,
     listed them as still to try.

Adam gave 266 and 267 on 2026-10-24, answering the five questions this
change put to him when it recorded 264 and 265:

266. *Amended by Adam's decisions 268 and 270: agreeing is a decline
     under reason 3 with filter 1 on every question, and the decline
     path closes it.* **On a questions-branch question, agreeing to a recorded answer
     writes no new log file.** The question closes as handled for the
     person, and a citation file is pushed when the record is an
     `active` lore entry in scope (decision 259). No log file is
     written: the record exists and filter 1 found it, so a file
     pointing to it adds nothing. Since every questions-branch question
     counts as an agent's question, decision 267's miss is still
     logged. When the same question was also asked
     in a thread, agreeing there posts the confirmed `Recorded answer: `
     post of decision 264, and that post is the record in the thread.
     This replaces the rule decision 264 first gave, that the log file's
     answer is the `Recorded answer: ` text, and with it the four of the
     five questions in Still open that were about that file. Decision
     268 replaces this decision's rule for a question with no thread: it
     is closed as a decline, not "as handled for the person". The rest
     holds for a question shown from a thread. *Rejected:* a log file whose answer points to the record.
267. *Amended by Adam's decision 270: agreeing logs the decline's miss,
     on a person's question too.* **Agreeing on an agent's question logs a miss against filter 1,** as
     when the answer session answers one by itself, since filter 1
     should have stopped the question either way. *Rejected:* logging
     none.

Adam gave 268 and 269 on 2026-10-24, answering the two questions this
change put to him when it recorded 266 and 267:

268. *Widened by Adam's decision 270 to every question; amended by his
     decisions 273 and 274: a question with no thread closes everywhere,
     by its handled file, and cannot be reopened.* **On a question with no thread, agreeing to the shown recorded
     answer is declining it under reason 3 with filter 1, naming that
     record.** The decline path does the rest: nothing is posted, the
     question closes in the state folder (on one machine only, as
     decision 202's item 1 accepts for declines), the person can reopen
     it (decision 260), the miss against filter 1 is logged with the
     decline's `said`, and a lore entry is cited (decision 262). This folds
     decision 266's case of a question with no thread into the decline
     path instead of keeping a separate path for agreeing. *Rejected:*
     a record and a `said` of agreeing's own.
269. *Retired by Adam's decision 273: the answer session pushes a
     handled file on every decline, recorded answer and `Inquisitor: `
     reply on a questions-branch question, so the file no longer comes
     back.* **A known limit, accepted: an agreed question asked in a thread can
     come back from the questions branch.** Its questions-branch file
     stays unanswered, and the answer session hides it only while it
     shows the same question from the thread, which nothing durable
     records. A channel's first poll reads back 14 days (decision 175's
     item 5), so a machine that first polls more than 14 days after the
     question was asked in the thread never reads it, and shows the file
     as a new question. The same holds for the automatic
     post and a reason 3 decline in a thread. No rule is added.
     *Rejected:* hiding a questions-branch file whenever any relay post
     names the same question.

Adam gave 270 to 272 on 2026-10-24, answering the three questions this
change put to him when it recorded 268 and 269:

270. *Amended by Adam's decision 273: a decline of a question a
     questions-branch file holds pushes a handled file, the one log file
     a decline pushes.* **Agreeing to a recorded answer is always declining the question
     under reason 3 with filter 1, naming that record,** in a thread as
     with no thread. Agreeing is no longer a path of its own: the decline
     path shows the exact post, warns before a record more private than
     the thread is posted (decision 264), cites a lore entry (decision
     262), logs the miss with its defined `said`, closes the question in
     the state folder when nothing is posted, and pushes no log file,
     with a thread or without. A miss on a person's question is accepted. This folds
     decisions 264, 266, 267 and 268 into the decline path, and settles
     which `said` the miss carries. *Rejected:* a `said` of agreeing's
     own.
271. *Reverted by Adam's decision 275.* **A decline's citation is pushed only when its miss is pushed.** A
     miss already on the branch for the same question and filter stops
     a second miss, so it also stops a second citation when the person
     agrees again, after reopening or on another machine. *Rejected:* no
     citation for a filter 1 decline of a question with no thread, the
     one case where agreeing again was then possible.
272. *Replaced by Adam's decision 273: the answer session, not the
     asking agent, writes the handled file.* **The asking agent marks its questions-branch file handled** when it
     reads, in the question's thread, a `Recorded answer: ` post or a
     post the answer session made on a decline, at the point where it
     would record a `User says: ` answer. Handled means closed, with no
     answer and no authority. Since a questions-branch file is never
     changed (decision 140), the agent pushes a new file holding the
     question and a `handled` key, which the log file format now
     defines. The question then stops counting as a question from the
     questions branch, the answer session's fourth source, on every
     machine. This retires decision 269's known limit for those posts;
     after an automatic `Inquisitor: ` post it still holds.
     *Rejected:* widening that limit to a restart on the same machine.

Adam gave 273 to 276 on 2026-10-24, answering the three questions this
change put to him when it recorded 270 to 272:

273. *Amended by Adam's decisions 278, 297 and 305: the handled file is
     written on every close and holds only `handled` and `closes`, which
     names the one questions-branch file it closes; the keys listed
     below are superseded.* **The answer session writes the handled file itself.** Whenever it
     declines a question, agreeing included (decision 270), or posts a
     recorded answer or an `Inquisitor: ` reply on it, and a
     questions-branch file holds that question, it pushes the handled
     file: `repository`, `asked`, `handled` and the question (its hash,
     by decision 277), with no
     answer and no authority, with a thread or without. The asking agent
     writes none. So decision 272's check of a post's author, which had
     to wait for task 0.21 to measure whether GitHub reports which App
     wrote a comment, goes. An Igor worker could still put a file with a
     `handled` key in its report for the Igor to push; the script's
     `log` command writes one only under an option the answer session
     alone passes, and Still open asks igor PR #216 to refuse such a
     file from a worker. A questions-branch question is
     then closed on every machine, which retires decision 269's limit
     fully, after `Inquisitor: ` posts too. The handled file is the
     stated exception to decision 270's "no log file". This replaces
     decision 272. *Rejected:* the asking agent marking the file.
274. *Clarified by Adam's decision 297: a thread copy stays reopenable on its machine under decision 260; only the questions-branch file a handled file names cannot be reopened.* **A declined questions-branch question can no longer be reopened,**
     since its handled file closes it everywhere, whether it came from
     that branch or was shown from a thread. Reopening (decision 260)
     stays for a question with a thread, declined with nothing posted,
     that no questions-branch file holds.
275. *Since Adam's decision 297, a thread copy declined on one machine can be declined again on another, so two citations can arise, as decision 279 accepts for two machines.* **Decision 271 is reverted.** A decline's citation is pushed once,
     whether or not a miss is, to the entry's own lore repository, under
     decision 259's rule for an `active` entry in scope. No duplicate can
     arise from reopening or from a later machine, since the handled file
     closes the question everywhere, and a decline with a post in a
     thread cannot be reopened; two machines with the same question open
     at once are in Still open.
276. *Its second half is moot since Adam's decisions 277 and 305: a handled file holds no question, so filter 1's search never matches it.* **Two details are Adam's:** the `handled` key holds the day, and
     filter 1 shows a handled file to a searching agent as unanswered.

Adam gave 277 to 280 on 2026-10-24, one for each question this change
put to him when it recorded 273 to 276:

277. *Superseded in part by Adam's decisions 297 and 305: a handled file holds no hash and no `repository`, only `handled` and `closes`, naming the file it closes; it still holds no question text.* **A handled file holds the question's hash, not its text.** "Same
     question" is already a hash match, and filter 1 reads a handled file
     as unanswered, so nothing needs the text. So a handled file never
     carries a private item's question into igor's search under a
     public `repository`. For the same reason its file name's slug is
     always `handled`. Holding no question text, it is never matched by
     filter 1's search, which is how "read as unanswered" holds: it never
     stops a question. The miss a close pushes still carries the text,
     and decision 282 has it copy the file's `asked_from`. *Rejected,
     for the handled file:* copying the question's text into it with the
     original's `asked_from`, and writing no handled file for a question
     with a category, one the inquisitor records by hash only.
278. *Amended by Adam's decision 285: there is no rhetorical close; a
     handled file is written on a decline or an automatic post.* **A handled file is written whenever the answer session closes a
     question a questions-branch file holds,** not only when it posts
     or declines. A rhetorical question closed under filter 3 with no
     reply is included. This amends decision 273. *Rejected:* keeping
     the rhetorical case per machine.
279. **Accepted: two machines declining the same open question can each
     push a citation.** It needs the same question open on two machines
     at once, which is rare, and no rule is added. *Rejected:* re-reading
     the questions branch before a decline's pushes, and pushing no
     citation for a reason 3 decline.
280. **Accepted: a record the asking agent's own filter 1 would not count
     still closes the question in the person's queue.** The asker's question
     still stands in its thread, and the asker can ask again. *Rejected:*
     having the asking agent decide the close, as decision 272 had it.

Adam gave 281 to 284 on 2026-10-24, one for each question this change
put to him when it recorded 277 to 280:

281. *Superseded by Adam's decision 297: a handled file closes only the file it names.* *Narrowed by Adam's decision 286 to its own repository and day.*
     **A handled file closes every copy of its question with the same
     hash,** thread copies included, on every machine. *Rejected:* thread
     copies kept per machine.
282. **The miss a close logs copies the questions-branch file's
     `asked_from`,** so the visibility rules apply to it as to the file.
     It is an exception to "the script never writes `asked_from`", stated
     in the inquisitor spec's definition of `asked_from`. *Rejected:* no miss for a question whose file holds
     `asked_from`.
283. *Read by Adam's decision 297 as applying to the questions-branch file a handled file names.* *Extended by Adam's decision 287: the reply is shown as a new
     question.* **A handled file is final:** nothing reopens a question it closed, a
     threaded reply under decline reason 1 included. This amends decision
     194's reason 1. *Rejected:* a reply reopening the thread copy on one
     machine.
284. *Withdrawn by Adam's decision 285.* **A rhetorical close posts filter 3's `Inquisitor: ` reply with a
     fixed rhetorical text,** which the person can edit like any post. The
     rule that a rhetorical question gets no reply is removed, amending
     decision 202's item 10 and decision 278. With no thread, as for a
     question only on a questions branch, nothing is posted and the
     handled file alone closes it; that close has no post to edit, which
     Still open asks about. The text's wording is this change's; see
     Still open. *Rejected:* a rhetorical close with no post in a thread,
     which the person could not undo.

Adam gave 285 to 287 on 2026-10-25, settling the five questions this
change put to him when it recorded 281 to 284:

285. *Renumbered by Adam's decision 330: reason 2 here is now part of reason 1, and reason 3 is reason 2.* *Amended by Adam's decision 298: such a message is declined under reason 2, logging no miss, or reason 3, whichever fits.* *Changed by Adam's decision 292: a non-question in the queue is
     declined under reason 2, not reason 3 with filter 3.* *Extended by Adam's decision 289: the answer session ignores a
     message that is not a question too.* **"Rhetorical" is no longer a category.** An asking agent does not
     treat a message that is not really a question as one: the
     inquisitor already has it rewrite such a message as a statement
     (decision 107's item 3), so nothing is shown, posted or
     closed for it. When one reaches
     the person's queue anyway, that is a miss, an agent misreading
     ordinary language, and the person declines it under reason 3 with
     filter 3, which posts filter 3's one fixed text and logs the miss.
     The rhetorical fixed text and its close with no thread go, which
     withdraws decision 284 and amends decisions 196, 202's item 10 and
     278. With no second filter 3 text, the question of which one reason
     3 posts is moot, and so are the rhetorical text's wording and its
     case with no thread. The existing categories, the decline reasons and
     filters 2 to 4, already cover a question that needs no answer.
     *Rejected:* a rhetorical text of filter 3's own.
286. *Superseded by Adam's decision 297.* *Changed by Adam's decision 294: a handled file closes copies asked
     before its commit time, not by day.* *"Repository" here means the topic repository, by Adam's decision
     288.* **A handled file closes only copies of its question in its own
     `repository`, asked no later than its `handled` day,** so asking
     again later, or elsewhere, reaches the person. This narrows decision
     281. *Rejected:* closing every copy with the same hash.
287. *Read by Adam's decision 297 as covering every message posted in the thread after its question closed.* **A reply arriving after a handled file closed its question is
     shown on its own, as a new question of the second source, a reply
     to a relay post,** as
     decision 202's item 6 treats a reply to an automatic post. *Rejected:*
     dropping the reply.

Adam gave 288 to 291 on 2026-10-25, one for each question this change
put to him when it recorded 285 to 287, 289 settling two:

288. *Superseded by Adam's decision 297.* *Limited by Adam's decisions 293 and 295: the topic repository is
     the closing machine's, and a reason 1 decline's file closes only its
     questions-branch files.* **A handled file closes every copy whose topic repository matches
     its `repository`,**
     the repository the question concerns, which the answer session
     already works out, wherever the copy was asked: a Linear or Discord
     thread, another GitHub repository, or an Igor question with another
     `asked_from`. Likewise a handled file closes another
     questions-branch file with the same question about the same topic
     repository, whatever its `asked_from`.
     Decision 286 holds as written, its "repository" being the topic
     repository. *Rejected:* dropping the repository condition.
289. *This change notes, though decision 330 does not name 289, that its rejected option, declining a non-question under the old reason 1, is what Adam's decision 330 now does, reason 1 being "Nothing to answer".* **Messages that are not questions are ignored:** not shown, nothing
     posted, nothing closed, consistent with decision 285. Filter 3's
     automatic reply is only for a real question that did not need
     asking, so an agent's rhetorical message in a thread gets no post.
     When one reaches the queue anyway, an existing decline reason covers
     it as a miss: reason 3 with filter 3 as first decided, reason 2
     since decision 292. *Rejected:* filter 3's
     automatic reply on a rhetorical message, and declining such a
     message under reason 1.
290. *Moot since Adam's decision 297.* *Reversed by Adam's decision 294.* **Accepted as a limit: the same words asked again on the handled
     day, about the same topic repository, are closed with the earlier
     copy.** *Rejected:* comparing by the handled file's commit time.
291. **Declining under reason 1 closes only that question.** The asker's
     unthreaded follow-up is treated like a reply (decision 287): shown
     as a new question on every machine, and a threaded reply no longer
     reopens the declined question either. This amends decision 202's
     item 2 and decision 194's reason 1. *Rejected:* a follow-up that
     counts on one machine and not another, as when a reason 1 decline,
     held in each machine's own state folder, stopped it counting only
     there.

Adam gave 292 to 295 on 2026-10-25, one for each question this change
put to him when it recorded 288 to 291:

292. *The Still open question it mentions was settled by Adam's decision 298.* *Renumbered by Adam's decision 330: reason 2 here is now part of reason 1, and reason 3 is reason 2.* *Amended by Adam's decision 298: reason 2 logs no miss, and reason 3 applies where the asking agent should have filtered the message.* **A non-question that reaches the queue is declined under reason 2,
     "picked up by mistake":** nothing is posted, and a miss is logged
     against the source. The asking agent's misreading, which decision
     285 logged as a filter 3 miss, is then logged nowhere; whether to
     accept that is in Still open. Since decision 289, such a message reaches the
     queue only when the answer session's own judgment let it through.
     This replaces decision 285's reason 3 with filter 3 for this case.
     *Rejected:* reason 3 with filter 3, whose post tells the asker to
     take an option it does not have.
293. *Superseded by Adam's decision 297.* **The handled file records the topic repository the closing machine
     worked out,** and other machines match on it. Other machines still
     work out a thread copy's topic repository themselves, since the
     handled file holds only a hash, a repository and a time, never a
     thread's address, and so cannot identify the copy. A machine that cannot
     work out a copy's topic repository matches on hash and time alone.
     *Rejected:* matching on hash and time alone everywhere.
294. *Superseded by Adam's decision 297.* **Compare by time, not day:** a handled file closes only copies
     asked before its commit time, so a word-for-word repeat after the
     close reaches the person. An agent that cannot see or count the
     recorded answer, such as a private record, one withheld by the
     visibility rules, or one without authority (decision 280), will
     likely ask again, and that is a legitimate request. This reverses
     decision 290 and ends its conflict with decision 291. *Rejected:*
     the same-day limit.
295. *Superseded by Adam's decision 297: a handled file holds no `over`; a reason 1 decline closes the thread copy on its machine only.* **A handled file from a reason 1 decline closes only the copy
     declined and the questions-branch files that hold its question,**
     not other askers' thread copies. It holds `over`, so other machines
     know not to close their thread copies by it. This limits decision
     288 for reason 1. Questions-branch files with the same question are
     still closed by it, whoever asked them, and agreeing and reasons 2
     and 3 still close every asker's copy. *Rejected:* closing every matching copy.
296. *Amended by Adam's decision 297 in its third choice: one handled file per questions-branch file closed, not per topic repository.* **Adam confirmed three choices this change made while recording
     288 to 291:** the ignore rule applies only to sources 1 and 2, a
     mention of the person and a mention of or reply to the relay, and
     only to clear cases, while an unclear message is still shown; an
     asker's reply to the relay's `User asks: ` post puts the person's
     waiting question back in the queue, whatever the reply says; and there is one handled file per distinct
     topic repository.

Adam gave 297 to 299 on 2026-10-25, settling the six questions this
change put to him when it recorded 292 to 296:

297. *Amended by Adam's decision 305: a handled file holds only `handled` and `closes`.* **Closing works by exact identity, never by matching.** A handled
     file names, in its `closes` key, the one questions-branch file it
     closes, by that file's unique name, and closes that file on every
     machine for good. A thread copy, a question shown from its thread,
     is closed on every machine only by the relay posts in its thread.
     One declined with nothing posted, under reason 1 or 2, is closed
     on that machine only, reopenable there (decision 260), and shown again on other
     machines, where the person can decline it again; Adam accepts that.
     When a close concerns more than one questions-branch file, one
     handled file is pushed for each. There is no hash, topic
     repository, `over` key or time comparison. The reason: matching on
     a question's words, on a judgement each machine made for itself, or
     on clocks kept giving two machines different answers, and each fix
     raised another case. This supersedes 281, 286, 288, 293, 294 and
     295, the hash in 277 and the per-repository part of 296, and makes
     290 moot. Decisions 273, 274, 275, 278, 283 and 291 stand, and 287
     covers the thread's own later messages. *Rejected:* each matching
     rule above.
298. *Reason 2 merged into reason 1 by Adam's decision 330.* *Amended by Adam's decision 304: reason 3 for a non-question posts nothing.* **Decline reason 2 logs no miss.** A message picked up by mistake
     is the answer session's own misjudgement, and no asker erred. A
     non-question that reaches the queue is declined under reason 2, or
     under reason 3 with the filter the asking agent should have applied,
     logging a miss against that agent, whichever fits. The ignore rule
     covers only sources 1 and 2 (decision 296), so a non-question from
     a review request or a questions-branch file reaches the queue
     without the session judging it. This amends
     decisions 196, 285 and 292 and retires 198's `"source <n>"` miss;
     208's `said: "not a question"` is no longer written. *Rejected:* a miss
     against the source.
299. *For an Igor's question, Adam's decision 326 links the assigned issue or pull request.* *Amended by Adam's decisions 300 to 302: a file whose link this machine never reads is shown on its own, an answer records the message's question, and a withheld Linear, Discord or, by decision 315, GitHub link is made up for by merging.* **A questions-branch log file follows its thread message by exact
     link.** A log file for a question the asking agent also asked in a
     post holds that message's URL as `asked_in`, and what the
     answer session decides about that message applies to the file. A
     log file with no `asked_in` is judged on its own, as a question of
     the fourth source. This replaces the show-once rule of decision
     175's item 11 and decision 210. *Rejected:*
     judging every log file on its own, and hiding it by matching words.

Adam gave 300 to 306 on 2026-10-25, one for each question this change
put to him when it recorded 297 to 299:

300. *Extended by Adam's decision 311: an answer given there is kept pending until it can be relayed.* **A log file whose `asked_in` links a message this machine never
     reads is shown on its own,** as a question of the fourth source:
     a message in a channel this machine does not subscribe to, or on a
     surface it has turned off or cannot read. This amends decision 299. *Rejected:* showing it nowhere on that
     machine.
301. **An answer to a linked message records the message's question as
     the person saw it,** not the question the log file holds. A log
     file whose `asked_in` points at an unrelated message would otherwise
     get the person's answer recorded, as a decision, against its own
     words, which the person never saw; now the answer file pairs the
     answer with the words they answered. *Rejected:* showing the file's question beside the
     message.
302. *Extended by Adam's decision 315 to a GitHub `asked_in` into a more private repository.* **Decision 251's rule applies to `asked_in`:** a Linear or Discord
     `asked_in` is written only when the lore repository is private.
     Where the URL is withheld, the answer session merges the log file
     and the thread message into one entry where it can tell they are
     the same question, and shows them twice where it cannot. Merging
     changes only what one machine shows, so it is not the matching
     decision 297 removed, and answering the merged entry records the
     answer against both. Adam left the merge criterion to this change,
     kept narrow so that two askers' questions in the same words are not
     merged; decision 307 states the criterion, and Adam confirmed 307
     with decision 314's change. *Rejected:* always
     writing the URL.
303. *Amended by Adam's decision 324: a later run names only a file it knows exactly, from the Igor's handback comment.* *Amended by Adam's decision 319: answer files still group by hash in filter 1's search, and `answers` decides only which answer a named file has.* *Narrowed by Adam's decision 320: only an answer file that counts hides the file it names.* *Guarded by Adam's decision 310: `answers` is written only when it names an unanswered file already on the branch.* **No hash matching for misses or answers:** a miss is pushed even
     when one with the same question and `filter` is already on the
     branch, and an answer file names, in a new `answers` key, the file
     it answers, as `closes` does, instead of answering every file with
     the same question. This amends decisions 197 and 202's item 8.
     *Rejected:* keeping both rules.
304. *Renumbered by Adam's decision 330: this is now reason 2.* **Reason 3 for a non-question logs the miss against the asking
     agent and posts nothing,** since filter 3's fixed text tells the
     agent to take an option it does not have. This amends decision
     298. *Rejected:* posting filter 3's text.
305. **A handled file holds only `handled` and `closes`;** `repository`
     and `asked` go, since they served matching decision 297 removed.
     This amends decisions 273 and 297. *Rejected:* keeping `repository`
     for the visibility checks.
306. **A late answer still counts:** a file another machine's decline
     closed is still unanswered, so an answer given to its thread copy
     pushes a log file answering it, as the spec already says.
     *Rejected:* pushing no answer file for a file a handled file names.

Adam gave 308 to 315 on 2026-10-25, one for each question this change
put to him when it recorded 300 to 307, and confirmed 307 as changed by
314:

308. **Accepted: a merge can differ between machines.** Each machine
     judges decision 307's condition, that the file matches no other
     message and the message no other file, by what it polls, so two machines
     reading different channels can merge one file with different
     messages. *Rejected:* never merging.
309. **An answer file always records the message's words,** as decision
     301 says, with no rule of its own for a lore repository more
     visible than the thread. Such a case barely arises: under decision
     315 an `asked_in` link, and so the message it points to, is written
     only where the lore repository is no more visible than the thread,
     and a merge needs the file's own words to match the message's, so
     the answer file adds no words the file did not already hold. The one
     case left is a lore repository made more public later, which
     publishes everything already in it, so the answer file adds nothing
     worse. *Rejected:* generalising the message's words, and relaying
     only in the thread.
310. **The `log` command writes `answers` only when it names an
     unanswered file already on the branch,** and igor PR #216 should
     refuse a worker's file holding `answers`, so the Igor adds the key
     itself, since #216 would then push only what the Igor writes; the
     *Still open* section below asks #216 for that.
     *Rejected:* accepting a planted `answers`.
311. *Amended by Adam's decisions 316 to 318: no notice on another machine, which asks again as usual; pending answers return to the queue once the channel's check passes, from a list that reuses the queue's UI and needs no prototype round; the answer file is pushed at once.* **An answer that cannot reach its thread is kept pending, not
     lost:** when the relay lacks permission, the channel is off, the
     post is refused or fails, or the answer was given on a machine that
     does not read the thread's channel (decision 300). The state folder
     keeps it as answered, not relayed; the machine holding it lists it
     as pending and posts it once setup's check of posting in that channel passes, after the
     person confirms. Where an answer file was pushed, a machine that can
     post in the thread shows "Answered on another machine, not relayed",
     offering to relay it, edit it or answer afresh, instead of asking
     again. The person is always told the asker has not got the answer
     yet, so they can relay it by hand. This amends the rule that a
     failed post leaves its question as it was, which dropped the typed
     answer. The pending list and that notice are new screens, built
     only after a prototype round Adam approves by use (decision 261).
     *Rejected:* asking again on the machine that can post.
312. *Amended by Adam's decision 319: filter 1's search groups every answer file by hash; `answers` decides only which answer a named file has.* **Among answer files naming the same file in `answers`, the newest
     counts.** Grouping by the same hash stays only for filter 1's search
     across askers, where a new asker has no file to name. This amends
     decision 220. *Rejected:* grouping every answer by hash.
313. *Superseded by Adam's decision 330: reasons 1 and 2 merge; filter 3's choice stays.* **Both "not a question" labels stay,** though they share a name:
     decline reason 2's, for the answer session's own error (decision
     298), and filter 3's choice under reason 3, for the asking agent's
     (decision 304).
314. **Decision 307 is confirmed with one change:** "the message is on
     Linear or Discord" becomes "a message whose `asked_in` would be
     withheld", so a GitHub message decision 315 withholds merges too.
315. **A GitHub `asked_in` is withheld when the thread's repository is
     more private than the lore repository,** as decision 251 withholds
     a Linear or Discord one, and the file then merges as for Linear and
     Discord. This extends decision 302. *Rejected:* always writing it.

Adam gave 316 to 320 on 2026-10-25, settling the five questions this
change put to him when it recorded 308 to 315:

316. **No "Answered on another machine, not relayed" notice.** While one
     machine holds a pending answer, any other machine of the person's
     asks the thread's question again as usual. The question this change
     raised, whether two machines that merged one file with different
     messages could show that notice in the wrong thread, is moot. This amends
     decision 311. *Rejected:* the notice, offered only for a file
     linked by `asked_in`.
317. *Settled further by Adam's decision 321: a pending answer no check brings back stays on the list, and the person can always drop it.* **Pending answers are kept in a separate pending list, which reuses
     the main queue's UI almost exactly,** in Adam's words: the queue's
     screens, holding pending answers. Once setup's check of posting in
     a pending answer's own thread's channel passes, that answer leaves
     the list and goes back into the queue, with the answer kept, for
     the person to approve again. As under decision 311, it also leaves
     the list once any machine's relay post naming the question appears
     in the thread. Since the list reuses the queue's
     approved patterns, it needs no prototype round of its own. This
     amends decision 311. *Rejected:* showing pending answers as a state
     in the list of questions answered and handled.
318. *Amended by Adam's decision 325: the answer file is pushed with the relay post, after the thread is checked; only an answer pending because its thread cannot be read is pushed at once.* **The answer file is pushed at once,** as decision 311 has it: when
     a questions-branch file holds the question, its answer file is
     pushed when the person confirms, with no `answer_link`. On GitHub a
     relayed answer's file would carry the comment's link as proof; this
     file gives that up and counts only through a signature. A dropped
     pending answer leaves its file on the branch, still answering the
     file it names. Adam accepts both. *Rejected:* pushing the file only
     when the answer is relayed.
319. *Amended by Adam's decision 323: an answer file replaced as a named file's answer is superseded in the search too.* **Filter 1's search groups every answer file by hash,** with or
     without `answers`, and the newest counts. `answers` decides only
     which answer a named file has. This amends decision 312.
     *Rejected:* taking files with `answers` out of the hash grouping.
320. **A file named in `answers` stops being shown only when the answer
     file counts as the person's answer,** proven as filter 1 proves one.
     Otherwise it stays shown, with that answer beside it as input. This
     amends decision 303. *Rejected:* letting any answer file hide the
     file it names.

Adam gave 321 to 324 on 2026-10-25, one for each question this change
put to him when it recorded 316 to 320:

321. **A pending answer no check brings back stays on the pending list
     indefinitely:** one the surface refused for its text, such as one
     too long; one held back because a new reply appeared in the thread
     just before posting; or one given on a machine that does not
     subscribe to its channel. That is acceptable because the person can always post,
     edit or drop any pending answer. *Rejected:* returning such an
     answer to the queue at the next opening.
322. **Setup checks that the person's commits to lore questions branches
     are signed,** with a key GitHub verifies for their account, and
     warns, saying how to fix it, when they are not. An answer file with
     no `answer_link` counts only through that signature (decision 318).
     *Rejected:* treating a file a machine pushed as answered on that
     machine alone.
323. *Guarded by Adam's decision 328: only an answer file whose proof is the person's and whose commit adds it alone counts as a named file's answer.* **An answer file replaced as a named file's answer is superseded in
     filter 1's search too:** once a newer answer file names the same
     file (decision 312), the older is labelled superseded there as well
     and stops counting for its own words, the question it records,
     which can differ from the newer file's and so sit in another hash
     group. This amends decision 319.
     *Rejected:* letting it go on counting in its hash group.
324. *Amended by Adam's decision 327: the name comes from the Igor's own record of the handback, not the comment's text.* **A later Igor run on an item, recording a person's answer to a
     handback question, names a file in `answers` only when it knows that
     file exactly,** from the Igor's handback comment, which names the
     questions-branch log file the Igor pushed for the question.
     Otherwise it writes no `answers`, and the earlier file stays shown
     until the person answers it. This amends decision 303, under which
     a later run named the files filter 1's search found. *Rejected:*
     naming the files a search found by their words.

Adam gave 325 to 330 on 2026-10-25, answering six of the seven questions
this change put to him when it recorded 321 to 324:

325. **The answer session checks the thread before it pushes the answer
     file,** and the push and the relay post then go out together. An
     answer the session holds back, because that check finds a new
     message in the thread, pushes its file only when it is finally
     posted, and dropping it leaves no file. Once the answer is
     pushed and posted, the question is answered, and a later message in
     the thread is judged like any new message, as decision 291 has it:
     a new question if it asks the person something, ignored otherwise.
     An answer that goes pending because its thread cannot be read is
     still pushed at once, unchecked, as decision 318 has it. This
     amends decision 318. *Rejected:* pushing every answer file at
     confirmation.
326. **An Igor worker's log file links, in `asked_in`, the assigned issue
     or pull request its question is shown from,** not the handback
     comment, so answering or declining it there applies to the log
     file. This amends decision 299 for an Igor's question. *Rejected:*
     showing such a file on its own.
327. **The later run takes the file's name from the Igor's own record of
     the handback** (igor PR #216's decision 59), not from the comment's
     text, which anyone who can edit the comment could change; the
     comment shows the name for people only. This amends decision 324.
     *Rejected:* reading the comment's text.
328. **An answer file counts as a named file's answer only when its proof,
     a comment link or a signature, is the person's, and its commit adds
     that answer file alone,** so a copy of another question's answer,
     pushed in one commit with other files, cannot become a named file's
     answer. This amends decisions 312 and 323.
     *Rejected:* accepting the risk.
329. **Edited and dropped pending answers, confirmed as this change had
     written them in the spec:** posting
     an edited pending answer pushes a new answer file with the relay
     post's link, posting it unedited pushes nothing new, and editing
     then dropping it leaves the original text as the person's answer.
     *Rejected:* a dropped answer pushing a handled file.
330. **Decline reasons 1 and 2 merge into one,** "Nothing to answer: the
     conversation is over, or it isn't a question", keeping their shared
     behaviour: nothing posted, closed on that machine only, reopenable
     there, no miss. The reasons are renumbered, so "the inquisitor
     should have handled it" becomes reason 2. Filter 3's "not a
     question" choice under it stays. This amends decisions 194, 208,
     298, 304 and 313. *Rejected:* keeping two reasons that behave
     alike.

### Proposed by this change

Decisions 16 to 18 are #211's proposals that apply to the skill; #211's
other proposals concern the role. Decisions 19 to 30, 36, 37 and 50 were
needed to write the requirements. Reviewing #25, Adam confirmed 16
to 30, 37 and 50, except 26, which he changed; his decision 42 replaced 36.
His decision 32 replaced part of 19, and his decision 35 part of 18. The
later decisions 79, 86, 99, 107, 111, 125, 130 and 143 came from this change too,
and each says what Adam did with it. Decisions 170 to 175 also came from
this change, and Adam confirmed them, with the changes 175 notes.
Decisions 181 to 183, 197 to 203 and 215 came from this change too, and
Adam confirmed them, with the changes 199 and 202 note. Decision 222 came
from this change too, and Adam confirmed it, with the changes 222 notes.
Decisions 227 and 228 came from this change too, and Adam confirmed them
as written. Decision 230 came from this change too, and Adam confirmed
it item by item, except items 4 and 5, which his decisions 232 and 235
replace. Decision 239 came from this change too, and Adam confirmed it
item by item, except item 2, which his decision 240 changes. Decision
245 came from this change too, and Adam replaced it with his own decision
245, recorded above. Decision 307 came from this change too, and Adam
confirmed it with the change his decision 314 makes.

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
    and no hook checks the question; Adam's decision 177 has a session with
    a person in it ask in its reply there. *Rejected:* a hook at the end of the
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
30. **Confirmed by Adam (2026-10-19), and amended by his decision 147.** **OpenSpec is used for new work in shared-skills,** except UI, which by decision 147 is prototyped and then built directly. A skill's spec holds
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
so this change made it under filter 4:

86. **Confirmed by Adam (2026-10-20).** **When more than one lore
    repository serves what a question concerns,** the most specific match wins (a named repository beats an
    owner), then the first listed in the configuration, and the agent's
    report says which it chose. It once had a second part, giving a
    categorized question's citation no hash, which Adam's decisions 87 and
    104 made moot.

Decision 99 came from spec-check's eleventh consistency read. Its parts are
cheap to reverse, so this change made them under filter 4:

99. **Confirmed by Adam (2026-10-20).** **Three details the spec fixes:**
    1. A linked comment proves a `questions`-branch file's writer (decision
       78) only when the comment's text holds the answer the file records,
       so a bare "LGTM" proves nothing.
    2. The credential patterns are a closed list: a private key's
       `-----BEGIN` line, GitHub tokens (`ghp_`, `gho_`, `ghs_`, `ghu_`,
       `ghr_`, `github_pat_`), Anthropic API keys (`sk-ant-`), AWS access
       key IDs (`AKIA`) and Slack tokens (`xox`). Adam's decision 138
       added `ghu_`, `ghr_` and `sk-ant-`.
    3. A login that is not GitHub's login syntax is never passed to a
       GitHub API call, so an answer whose author has one is input.

Decision 107 came from spec-check's twelfth consistency read. Its parts are
cheap to reverse, so this change made them under filter 4:

107. **Details the spec fixes:**
     1. **Confirmed by Adam (2026-10-20).** The shared post reader also
        reads `python3 <github-app script> run -- gh …`, including when the
        script's path is written as `$G`, the variable the github-app skill
        uses for it. His decision 122 reads `$G` only when the same command
        sets it.
     2. **Confirmed by Adam (2026-10-20).** A `gh api` call writes when its
        method is `POST`, `PATCH` or `PUT`, given by `-X` or `--method` or
        implied by fields or `--input` with no `-X GET`, or when its GraphQL query is a mutation. A write whose
        fields carry no `body` sends no post. This narrows how decision 96
        is read, so that reads such as GraphQL queries and label edits pass.
        His decision 132 lists the mutations whose body the reader reads.
     3. **Confirmed by Adam (2026-10-20).** A rhetorical question is
        rewritten as a statement, and its `decided` verdict names the post.
     4. **Confirmed by Adam (2026-10-20).** A proposed lore entry whose id
        an existing entry already uses gets another id; one whose id a
        rejected candidate uses is not proposed. His decision 116 adds that
        the id must pass igor's id rule.
     5. **Confirmed by Adam (2026-10-20), with his decision 109 added.** A
        linked answer (decision 78) must be a github.com comment or review
        on the repository the question concerns or on the lore repository.
        An answer typed directly on another surface counts only through a
        decision document that records it, such as the scribe's (decision
        109, narrowed by decision 250).
     6. **Replaced by Adam's decision 108.** It kept a vulnerability's
        question and answer out of a fix's commit messages, pull request
        text and comments.
     7. **Confirmed by Adam (2026-10-20).** The date filter 1's search
        reports for each lore clone, so the agent can tell how fresh it is,
        is when the clone's remote-tracking default branch was last updated
        by a fetch in that clone.

Decision 111 came from writing Adam's decision 110. igor's review reads
citation files from two writers, the inquisitor and an Igor, so the format
needs its encoding fixed. Nothing writes a citation yet, so the encoding is
cheap to change. This change chose it under filter 4 and, as with its other
decisions, put it to Adam, who confirmed it:

111. **Confirmed by Adam (2026-10-20).** **How a citation file is
     written:**
     1. `<date>`, in the file's name and in the file, is `yyyy-mm-dd` in
        UTC, as in a question file's name. The commit's date is midnight
        UTC of that day.
     2. The 6 random hex digits are lowercase, and the file has no
        extension, as decision 110's path has none.
     3. The file is YAML holding `entry`, `date` and, from an Igor's run,
        `run`, each a quoted string, as a log file's frontmatter values
        are, and no other key.
     4. The `<file>` in the commit message `inquisitor: log <file>` is the
        file's path from the branch's root, such as
        `citations/2026-10-20-3f9a1c`.

Decision 125 came from writing Adam's decision 118. Nothing writes a log
file or a miss file yet, so their format is cheap to change. This change
chose it under filter 4 and put it to Adam, who confirmed it as written:

125. **Confirmed by Adam (2026-10-20), and extended by his decision 221,
     which adds the key `asked_from` to items 4 and 5; his decision 236
     requires a whole comment in item 4's answer, decision 239's item 1
     sets how it is written, and his decision 240 records an answer
     not taken from a comment in the person's own words.** **How a log file
     and a miss file are written:**
     1. **Path:** in a repository, `.inquisitor/questions/<name>` for a
        question and `.inquisitor/misses/<name>` for a miss, at the root of
        the repository the question concerns; on a lore repository's
        `questions` branch, `questions/<name>` and `misses/<name>`.
        `<name>` is `<date>-<slug>-<6 random hex digits>.md`, where
        `<date>` is the day the file is first written, as `yyyy-mm-dd` in
        UTC, and the hex digits are lowercase, as in a citation's name.
     2. **Slug:** the question's text in lower case, with each run of
        characters other than `a` to `z` and `0` to `9` made one `-`, cut
        to at most 40 characters, with no `-` at either end; `question`
        when nothing is left.
     3. **Encoding:** UTF-8 with LF line ends: YAML frontmatter between two
        `---` lines, every value a double-quoted YAML string, then a
        markdown body.
     4. **A log file's keys:** `repository`, the repository the question
        concerns as `owner/repo`; `asked`, the day the question was asked,
        or, for a question never asked, the day the agent decided it; and,
        once it is answered, `answered_by`,
        `authority`, `recorded_in` (where the question's answer is
        recorded), and `answer_link` when there is one. No other key. Its
        body is the question under `## Question`, and, once answered, the
        answer in one sentence under `## Answer`.
     5. **A miss file's keys:** `repository`, `asked`, `filter` (`"1"` to
        `"4"`, the filter that should have stopped the question) and
        `said` (what the person said, with any place they named, such as a
        spec's path). No other key. Its body is the
        question under `## Question`.

Decision 130 came from spec-check's consistency read of the change after
decisions 112 to 125. The design accepts three costs that no decision
recorded, so this change recorded them and put them to Adam, who confirmed
all three:

130. **Confirmed by Adam (2026-10-20).** **Three costs this change accepts:**
     1. **A repository's own question log is invisible to parallel work
        until it merges.** A question about one repository is logged in
        that repository's `.inquisitor/questions/`, committed on the work's
        branch (decision 43). Until that work merges, an agent on another
        branch, or in another pull request, does not find the file, and may
        ask the same question again. This cost does not apply to the lore
        repository's orphan `questions` branch, where a file is pushed
        directly and is found by the next fetch.
     2. **Lore is only as fresh as the person's fetches.** Filter 1 reads
        each lore clone's remote-tracking default branch as the clone last
        fetched it, and fetches only the `questions` branch, so an entry
        merged since that fetch is not found. The search reports when that
        fetch was (decision 107's item 7), so the agent can tell.
     3. **The record of an `ask` drops the option's label.** For a picker
        question, the hooks' record keeps what changes under the other
        options but not the recommended option's label, so that it holds
        no question text. Nothing the skill keeps then shows which option
        the agent recommended, so nobody can check later from the records
        whether the person took the recommendation.

Decision 143 came from recording Adam's decision 126. It had one option
with merit, so this change took it under filter 3, which takes the only
option with merit without asking, and listed it; Adam confirmed it:

143. **Confirmed by Adam (2026-10-20).** **A session with no person in it
     that can neither post nor hand back asks nowhere.** It stops only if
     the work needs the answer, and reports the question in its output.

Decisions 170 to 175 came from writing the answer session's requirements,
from Adam's decisions 152 to 169. Adam confirmed each on 2026-10-20:

170. **Confirmed by Adam (2026-10-20).** **A relay post is the person's words, so it gets no prose pass and
     no vetting.** The answer session posts it by running the relay
     identity's skill as a command on the host itself, through the mod's
     own process call, not as a tool call of the session's model. The post
     hooks of prose and of this skill act only on tool calls, so neither
     sees it. A prose rewrite would post words the person did not confirm,
     and the inquisitor's filters guard a person's time against an agent's
     questions, not the person's own. This change took it under filter 3.
171. **Confirmed by Adam (2026-10-20).** **A relay post that asks the
     asker starts with `User asks: `,** where an answer starts with
     `User says: `. "User" is literal in both prefixes, never the person's
     name. Decision 160 reads "waiting for
     the asker" from the thread, which needs a mark that every machine, and
     every surface, can read there. This change took it under filter 4.
172. **Confirmed by Adam (2026-10-20).** **The asker, not the answer session, logs a rephrased answer.** The
     session's model drafts the rephrased question and the one-sentence
     summary at the privacy of what the question concerns, generalising or
     leaving out more private context, as decision 33 says, and nothing is
     posted until the person confirms the whole post. The relay post gives
     them on lines of their own after the answer. The agent that records the
     answer in the question's log file adds them, under `## Rephrased
     question` and `## Discussion`, as decision 163 says. The log file
     belongs to the asker's work, often on a branch not yet merged, and
     the asker already records the answer there; if the answer session
     wrote it instead, each rephrasing would need its own pull request.
     *Rejected:* new frontmatter keys, since every frontmatter value is one
     quoted line and a question's text is not. This change took it under
     filter 4.
173. *Amended by Adam's decision 303: the new file names the file it answers in `answers`.* **Confirmed by Adam (2026-10-20), and amended by his decision 210.** **A question from a lore repository's questions branch is answered
     by pushing a new log file there,** holding the question and the
     answer, under the rules for an answer the person gave in the session
     (decisions 94 and 140). Such a file has no thread to relay to, and
     the questions branch never changes a file once pushed. Asking the
     asker and editing are not offered for it. This change took it under
     filter 3.
174. **Confirmed by Adam (2026-10-20).** **In an answer session's discussion, the model may ask the person in
     its reply.** The inquisitor's rule that an agent asks only through the
     picker gains this one exception, and such a question passes none of
     the four filters and needs no vetting. The person opened the conversation to
     talk the question through, and a picker would hide the answer
     session's screen. This change took it under filter 3.
175. **Confirmed by Adam (2026-10-20), item by item, with items 2 and 16
     changed as noted.** **Details the spec fixes,** each cheap to
     reverse, taken under filter 4:
     1. The configuration's keys: `answer_session`, holding `github`,
        `linear` and `discord`, each with `relay` and `subscriptions`, and
        on Discord also `user`, the person's Discord user id. Item 2's
        change dropped the `read` key this item first had.
     2. *Changed by Adam's decisions 185 and 186.* The person's Linear API
        key is kept in the system keychain. On Discord one `discord-bot`
        identity, the relay, both reads and posts. This item first had a
        second identity, named in a `read` key, for reading.
     3. `answer` is installed as `~/.local/bin/answer`. Setup never
        overwrites a file there that it did not write.
     4. The lock is refreshed at least every 30 seconds, and stale after 2
        minutes. The lock also holds the holder's Claude Code session id,
        since every session `answer` starts is named `Answers`. Before each
        poll and each post, the holder checks that the lock still holds its
        session id.
     5. A channel with no poll position is read from 14 days back.
     6. A failed or never-run relay check is run again each time the
        answer session opens.
     7. When the check before a post finds a reply the person has not
        seen, nothing is posted, and the reply is shown.
     8. A relay post names the question it answers: as a Discord reply, in
        the Linear comment thread, as a GitHub review-thread reply, or, in
        a GitHub conversation, by a last line `Re: <URL>`. A question's
        state counts only the relay posts naming it, so two questions in
        one thread keep their own states. On another machine, an edit
        finds its post the same way.
     9. A review request or an assignment, the third of decision 156's
        sources, is answered by a comment, not a review.
     10. *Changed by Adam's decisions 283 and 291: a threaded reply reopens nothing and is shown as a new question.* Every reply to any relay post is a new question, whether that
         relay post was an answer or a question to the asker. So is the
         asker's next comment after a relay post in a GitHub
         conversation, an unthreaded follow-up. Under decision 194's
         first reason, as Adam changed it with decision 202's item 2, a
         question closed as over stops counting only that unthreaded
         follow-up. A threaded reply to a relay post, meaning a Discord
         reply to it, a Linear comment in its comment thread or a GitHub
         review-thread reply, still counts, and reopens the question.
     11. *Replaced by Adam's decision 299: a file follows the thread message its `asked_in` links.* A questions-branch file whose question has the same hash as one
         shown from a thread is not shown again.
     12. Until task 0.15 shows that GitHub's notifications endpoint reports
         every GitHub message of the first three sources, the answer
         session also reads each subscribed repository's comments. (This
         item first said all four sources; the fourth, a questions-branch
         log file, never appears in notifications, and is read by fetching
         that branch at each poll.) That costs a rate-limited request per
         repository per poll, and a subscription to an owner costs one per
         repository of that owner.
     13. When `gh` does not confirm the configured login, GitHub is off.
     14. Setup marks the `answer` file it writes with a comment line, and
         leaves any file without it alone.
     15. A relay post is scanned for the credential patterns, and its
         command runs with no shell, its text in a file or on standard
         input.
     16. *Replaced by Adam's decision 193.* Only the prefix is reserved: a
         relay identity may be used for other work, but a post starting
         `User says: ` or `User asks: ` is made only by the answer
         session, on the person's confirmation. This item first kept a
         relay identity for nothing but the answer session.
     17. The Discord relay must be able to read message content, which
         needs Discord's privileged Message Content intent (decision
         191).

Decisions 181 to 183 came from spec-check's consistency read of commit
041822a, which found rules that design.md applied and no decision recorded.
Each is this change's own, and Adam confirmed each on 2026-10-20:

181. **Confirmed by Adam (2026-10-20).** **A verdict record stays valid after a hook blocks a call for another
     question in it.** The picker hook and the post hook spend no record,
     so when a call is blocked because of one question, the agent vets that
     question alone and calls again. Each record still expires as
     decisions 38 and 51 say. This change took it under filter 4.
182. **Confirmed by Adam (2026-10-20).** **The files an agent passes to `vet` go in a private directory
     outside any repository:** a directory made with `mktemp -d`, which
     only the agent's user can read, holding each file with mode 0600. The
     script refuses a file that its group or others can read. Every user
     of a host can read a file left with the usual mode in a shared
     temporary directory such as `/tmp`, and with it a question's text. A
     question with a category reaches the script on standard input
     instead, never in a file. *Rejected:* the system's temporary
     directory, as design.md first had it. This change took it under
     filter 3.
183. **Confirmed by Adam (2026-10-20); his decision 236 requires a whole
     comment in item 2's one-line answer, decision 239's item 1
     sets how it is written, and his decision 243 keeps item 6 from
     logging a flagged run's question.** **Details the spec fixes,** each cheap to reverse, taken under
     filter 4:
     1. Filter 1 searches a repository's `.inquisitor/misses/` too, and
        labels an unanswered log file as unanswered and a miss file as a
        miss, never as an answer.
     2. A log file is answered when its frontmatter holds `authority`, and
        only then, so a `## Answer` line inside a question's text changes
        nothing. The script writes the answer, the discussion's summary
        and the rephrased question each on one line at the end of the
        body. A reader then finds them by counting lines back from the
        end, and everything above them is the question.
     3. A log file's `repository` and `answer_link` are checked against
        GitHub's syntax before any GitHub API call uses them. A file whose
        `repository` fails is input, labelled unreadable, and an
        `answer_link` that fails proves no writer.
     4. The shared post reader reads a `gh api` field, and an assignment
        to `G`, only when the shell would pass the word unchanged apart
        from removing its quotes. So `-f body=$B` is unreadable, and
        `G="/abs/github_app.py"`, quoted, sets `G`.
     5. A citation's commit is made with `git -c commit.gpgsign=false`, so
        a person's signing setup for decision 78 never signs it with their
        key.
     6. When an Igor's run ends in its handback comment with no artifact,
        meaning nothing the Igor publishes for the run, such as a pull
        request, the worker logs no question about the item's repository, since the
        Igor publishes such a log file only with an artifact: the handback
        comment is the question's record. A later run on the item that
        publishes an artifact logs the question there, holding its answer
        once a person has given one.

Decisions 197 to 203 came from writing Adam's decisions 184 to 196 into
the answer session's requirements. Each is this change's own. Adam
confirmed each on 2026-10-20, amending 199 and changing items 2, 4, 6 and
7 of 202:

197. *Amended by Adam's decision 303: a miss is pushed even when a matching one is already on the branch.* **Confirmed by Adam (2026-10-20).** **A miss the answer session logs goes to the questions branch of the
     team's lore repository,** pushed directly by the script, as decision
     173's answers are. Its `repository` is the repository the question
     concerns, which the session's model judges as the inquisitor's spec
     has an agent judge it; on GitHub it is the thread's repository when
     the model can't tell. No miss file is written when the question has a
     category; when it concerns no repository; when no configured lore
     repository serves that repository; or when the lore repository is
     more visible than that repository or than the question's thread (on
     Linear and Discord, unless the lore repository is private). The
     answer session then says so, and the question still closes. A miss
     whose question and `filter` match a miss file already on that branch
     is not pushed again, so a question judged on two machines gives one
     miss. The inquisitor's rule that a question with no log file gets no
     miss file does not apply here, since the answer session can't see
     whether the asker logged the question. *Rejected:* writing the miss
     where the asker's log file went, which the answer session can't
     know, often an unmerged branch, and which would take a pull request
     for each miss. *Rejected:* the state folder, which would be the
     personal question log decision 32 rules out. This change took it
     under filter 3.
198. *Retired in part by Adam's decision 298: the `"source <n>"` miss goes, since reason 2 logs no miss.* **Confirmed by Adam (2026-10-20), with `said` renamed by his decision
     208.** **A lesson candidate about how the answer session found a
     message is a miss file whose `filter` is `"source <n>"`,** where `<n>`
     is the number, 1 to 4, of the source that found it, and whose `said`
     is `not a question`. It goes where decision 197 sends any miss of
     the answer session's, so the review of misses reads it with the
     rest, and the format gains no key. A pattern among such misses is a
     lesson about the answer session's sources, sent by the scope rules
     every lesson follows. A miss the answer session logs by itself, under
     decisions 196 and 207, has `said` set to `answer session: clearly filter <n>`,
     so a review can tell the session's judgement from a person's word.
     This change took it under filter 4.
199. **Confirmed by Adam (2026-10-20), with the exception he added, which
     decision 222's item 2 widens and his decision 223 reconciles with
     decision 195.** **An
     agent's question is one whose author is a bot account,** such as a
     GitHub App, a Linear app user, or a Discord bot or webhook, or a log
     file from a questions branch, which only the inquisitor's script
     writes. Adam's exception: a post starting `User says: ` or
     `User asks: ` from a person's relay is that person's, and gets no
     automatic `Inquisitor: ` reply from the answer session; the answer
     session's filter 1 can still answer it automatically from a
     record, as for any person's question (decision 223). It first read a
     GitHub relay by decision 184's rule, an App GitHub reports as owned
     by the person, and on Linear and Discord, where an app's owner can't
     be proved, took those two prefixes from any bot account. By decision
     222's item 2 those two prefixes from any bot account, on any
     surface, make the post a person's. Every other question counts as a person's, including an
     agent's posted with a person's own credentials, which the answer
     session can't tell apart. Erring that way keeps the posts decision
     196 makes by itself off people's questions. This change took it
     under filter 3.
200. **Confirmed by Adam (2026-10-20); item 1 amended by decision 239's
     item 5, which he confirmed on 2026-10-21; item 4 amended by his
     decision 264.** **What the answer session posts by itself:**
     1. A recorded answer is posted as `Recorded answer: see the record
        below.`, whatever the record, a log file included, then a line
        `Recorded in: <URL>` holding filter 1's hit, then, on GitHub, the
        `Re: ` line every relay post ends with. It quotes no answer, so a
        recorded comment's @-mentions notify no one again. Before the
        amendment it quoted a log file's one-line answer.
     2. An `Inquisitor: ` post is a fixed text for each of filters 2, 3
        and 4, which names the filter and gives its action.

     The session's model writes no word of an automatic post, so a
     thread's text, which reaches the model, can at worst choose which
     fixed reply or which record is posted. Since the text is fixed,
     with only the record's URL filled in, an automatic post gets no prose pass and no
     vetting, as a relay post of the person's words does (decision 170).
     *Rejected:* a recorded answer in a sentence the model writes, which a
     crafted thread could steer.
     3. The answer session posts by itself only on a question with a
        thread. On a question from a questions branch it shows the
        recorded answer or the verdict to the person instead.
     4. It posts a recorded answer by itself only when the record is no
        more private than the question's thread: on GitHub, when the
        record's repository is no more visible than the thread's; on
        Linear and Discord, only when the record's repository is public.
        Otherwise it shows the recorded answer to the person beside the
        question, for them to relay or not. *Amended by decision 264:*
        the person may also agree to it, and then it is posted after a
        warning that this shows the record exists.
     5. When a lore entry is the recorded answer, it pushes a citation
        file, as any session's filter 1 does.

     This change took it under filter 3.
201. **Confirmed by Adam (2026-10-20).** **Editing a post the answer session made by itself makes it the
     person's words:** the edited post starts with `User says: ` in place
     of `Recorded answer: ` or `Inquisitor: `, since the person confirmed
     its new text. This change took it under filter 4.
202. **Confirmed by Adam (2026-10-20) item by item, except items 2, 4, 6
     and 7, which he changed as noted; his decision 234 narrows item 5's
     `Inquisitor: ` replies to filter 2's, or filter 3's or 4's the person
     chose.** **Details the spec fixes,** each
     cheap to reverse, taken under filter 4:
     1. *Amended by decisions 273, 278, 285 and 297.* A
        declined thread copy is kept closed in the state folder, per
        machine, and a questions-branch file is closed everywhere by
        the handled file that names it. As first written, a rhetorical question
        handled with no reply was kept closed the same way; decision 285
        removed that case.
     2. *Changed by Adam, and again by his decision 291, under which a
        later message in the thread, a follow-up or a reply, is a new
        question and reopens nothing. As this item first read:* Under decision 194's first reason, any
        threaded reply to a relay post, such as a Discord reply to it,
        reopens the closed question. The reason stops
        counting only the asker's other later comments, such as an
        unthreaded follow-up in a GitHub conversation; a message that
        @-mentions the person or a relay identity still counts, by its
        mention. A review request or an assignment made after the question
        closed is still a question. This item first counted no reply that
        lacked an explicit @-mention, a Discord reply to the relay's
        message included.
     3. A question's discussion record is deleted once it is closed, as
        decision 190 has it for an answered question.
     4. *Superseded by Adam's decision 209,* under which the person picks
        the filter. This item had the model ask which filter, in its
        reply, under decision 174's exception.
     5. An agent that reads a reply starting `Recorded answer: ` checks
        the place it names through filter 1, and does not log the reply
        as the person's answer. An agent that reads a reply starting
        `Inquisitor: ` takes that filter's action, and records its choice
        as its own filter would have.
     6. *Changed by Adam, and widened by his decision 219, under which no
        automatic post repeats one made anywhere in that chain of
        replies.* A reply to a post the answer session made by
        itself is a new question, as a reply to any relay post is
        (decision 175's item 10). It is judged by the filters again and
        may be answered by itself again, but the answer session never
        makes the same automatic post twice in a row on one question: a
        repeat goes to the person. When an asker's filter 1 can't count
        the place a recorded answer names, the asker treats it as input,
        and its question stands. This item first sent every such reply to
        the person.
     7. *Replaced by Adam's decision 207,* which logs a miss against
        filter 1 for an agent's question that filter 1 answers by itself.
        This item logged none.
     8. *Its use for decision 175's item 11 ended with Adam's decision 299, and its use for misses and answers with his decision 303; the reduction still serves "the same question" in decision 302's merge and in filter 1's search.* A log file's question is reduced as a post's question is, without
        list marker or inline markup and with its whitespace joined,
        before it is hashed, so decision 175's item 11 finds a question
        logged from a thread. Before this, a log file's question was
        hashed as written, and the two hashes could differ.
     9. When a post fails, such as a Discord message over 2,000
        characters, nothing is posted, the person is told why, and the
        question keeps its state. An automatic post that fails sends its
        question to the person.
     10. *Withdrawn by Adam's decision 285.* A rhetorical question handled
         with no reply was recorded in the state folder as handled for the
         person, on that machine. There is now no rhetorical case.

203. **Confirmed by Adam (2026-10-20).** **The inquisitor's post hook blocks a tool-call post on GitHub that
     starts with a reserved prefix.** The answer session posts through a
     host command that no tool hook sees (decision 170), so a tool-call
     post starting with `User says: `, `User asks: `, `Recorded answer: `
     or `Inquisitor: ` is never the answer session's. Since a
     `User says: ` comment from the person's relay App proves their answer
     (decisions 184 and 216), and the App may do other work (decision 193), this
     check keeps an agent that holds the App from forging one through
     `gh`. Nothing checks Linear or Discord, where a relayed answer proves
     nothing. This change took it under filter 3.

Decision 215 came from spec-check's consistency read of the round that
recorded decisions 204 to 214. It is this change's own, and Adam
confirmed all seven items on 2026-10-20:

215. **Confirmed by Adam (2026-10-20), item by item; item 1 now reads
     the relay file of decision 216, and Adam's decision 234 narrows it to
     filter 2's reply, or filter 3's or 4's the person chose; decision
     222's item 2 widens item 6, and Adam's decision 223 corrects it.** **Details the spec fixes,**
     each cheap to reverse, taken under filter 4 unless noted:
     1. An agent acts on an `Inquisitor: ` reply only when the relay App
        of someone with write access to what the question concerns, as
        decision 216 defines a relay App, posted it, whether or not that is the
        person the question asked, and never on a question that another
        skill requires a person to decide, which filters 2 to 4 don't
        apply to. Otherwise the reply is input, and the question stands.
        So on Linear and Discord, and on GitHub until task 0.21 shows
        that GitHub reports which App wrote a comment, every
        `Inquisitor: ` reply is input. This item first read an App's
        owner, as decision 184 did. Anyone who can comment could otherwise post
        `Inquisitor: filter 4` and have an agent decide a maintainer's
        question. Taken under filter 3.
     2. The answer session judges whether an incoming question has a
        category before filter 1 runs, and passes such a question, with
        its category, to the script on standard input, never in a file;
        for a question with a category, the script searches no source
        outside the machine. It posts nothing by itself on it. Other questions
        reach the script in private files, as an agent's do (decision
        182). Under decline reason 3 too, nothing is posted on such a
        question, and it closes. Taken under filter 3.
     3. An asker that reads a `Recorded answer: ` post naming a lore entry
        pushes no citation, since the answer session pushed one, so one
        question gives one citation (decision 98).
     4. The log file decision 210 pushes links the relay post as its
        `answer_link`, so decision 184 can prove its writer.
     5. Under decline reason 3, a miss with no note from the person has
        `said: "the inquisitor should have handled it"`. When the person
        picks filter 1 there, a question with no thread, or whose record
        is more private than its thread, closes once the recorded answer
        is shown. *Amended by decision 264:* a more private record's reply
        is posted once the person confirms after a warning.
     6. On GitHub, a `User says: ` or `User asks: ` post from an App
        whose owner the answer session can't read counts as a relayed
        question, a person's, so it gets no automatic `Inquisitor: `
        post, though
        filter 1 can answer it by itself (decision 223). Taken under
        filter 3, erring as decision 199 does. Decision 222's item 2
        widens it to every bot account, since no rule reads an App's
        owner any longer.
     7. A title is text a command sends, so a title edit chained to
        another command, such as `cd x && gh pr edit 3 --title 'Rename?'`,
        is unreadable, and `--fill` and its variants, which take a title
        from commits, stay unreadable. Otherwise a title's question could
        go out unvetted, against decision 206.

Decision 222 came from writing Adam's decisions 216, 220 and 221 into the
requirements. It is this change's own:

222. **Confirmed by Adam (2026-10-20) item by item, except item 2, which
     his decision 223 reconciles with decision 195, and item 6, which his
     decision 224 replaces.** **Details the spec fixes,** each cheap to
     reverse, taken under filter 3 unless noted:
     1. "The newest log file for that question counts" (decision 220) is
        read as the newest of the files that would each count as an
        answer, newest by its proof: for a comment link, the time GitHub
        gives for the comment's last edit, or its creation; for a
        signature, the signed commit's committer date, which only the
        signer could set. Not by where the file's commit comes in the
        branch, since anyone with push access could re-push a copy of an
        older proven file and revert a newer answer. The others show as
        input, labelled as superseded. A file that would not count, such
        as an `input` file or an unanswered one, supersedes nothing, or a
        person without write access, whose answer to a handback an Igor
        logs as `input` (decision 149), would undo a maintainer's
        answer.
     2. *Reconciled with decision 195 by Adam's decision 223: filter 1
        can still answer such a post by itself.* A `User says: ` or
        `User asks: ` post from any bot account, on any surface, is a
        relayed question: a person's, which gets no `Inquisitor: ` post
        by itself.
        With decision 216 no rule reads an App's owner any longer, so
        decision 199's GitHub test and decision 215's item 6 reduce to
        this, erring the same way.
     3. A relay file that is missing or does not parse lists no relay, and
        a value that is not a list of strings lists none for that key.
        Since decision 224 a file is one person's, so a file whose name is
        not a GitHub login lists none. Only the `github` lists prove
        anything. Taken under filter 4.
     4. The skill's script never writes `asked_from`, and an `asked_from`
        that fails the `owner/repo` check a `repository` must pass counts
        as a private repository, as #216 counts it, besides making the
        file input.
     5. An edit that turns an automatic post into the person's
        `User says: ` answer, for a question a questions-branch file also
        holds, pushes a log file as decision 220's edit does. Taken under
        filter 4.
     6. *Replaced by Adam's decision 224, one file per person.* The relay
        file was `relays.yaml` at the lore repository's root, one mapping
        keyed by login.
     7. An Igor's App is never a relay App, even where a relay file lists
        it, as igor PR #216's decision 45 has it, and Adam's decision 232
        says how a reader recognises one, and a person lists only
        an App that posts nothing a post hook can't see apart from the
        answer session's own posts. Decision 193 lets a relay App do other
        work, but only through tool calls the post hook sees.
     8. Setup opens the relay pull request as a host command, with a
        fixed title and body the script writes, so it needs no prose pass,
        as decision 200's automatic posts need none. Taken under filter
        4.

Decisions 227 and 228 came from writing Adam's decisions 223 to 225 into
the requirements. They are this change's own, and Adam confirmed both
as written on 2026-10-20:

227. **Confirmed by Adam (2026-10-20); his decision 241 has an Igor read
     item 1's last change as of the commit igor PR #208 last applied.** **How a reader ties a relay file
     to its person,** taken under filter
     4 unless noted:
     1. The file's last change is the newest commit on the default
        branch, as the lore clone last fetched it, that changed the file
        by git's default history, which skips a merge that kept one
        parent's copy. Its pull request is a merged one GitHub associates
        with that commit (task 0.22 measures that GitHub gives it), and its
        verified commit is one carrying a signature GitHub verifies for
        the person's account, as decision 78 reads a signature. The file's
        name is compared with the login without regard to case.
     2. When either check cannot run, such as offline, the file lists no
        relay, as decision 212 shows a file as input whenever a check
        can't run. Taken under filter 3.
     3. Setup proposes the file again when its last change was not the
        person's, even if it lists every relay, since it no longer counts.
     4. Two costs, which Adam's rule brings and the spec accepts. Someone
        who can push to the person's open pull request, such as a
        maintainer the person's fork lets edit it, can change the file
        under that pull request, and it counts once merged; the notice
        @-mentions the person for that push, so they can close it. And
        anyone who can rewrite the default branch can restore an older
        file of the person's own, listing an App the person had removed.
        So removing a compromised App from the file does not stop it
        speaking for them, and the README says to uninstall it or revoke
        its key instead. *Rejected:* counting
        the pull request only when every commit in it is the person's,
        which GitHub's API can't show for a pushed commit's pusher.
228. **Confirmed by Adam (2026-10-20).** **The inquisitor ships the
     notice as a workflow, `relay-notice.yml`,
     and setup proposes it.** It is igor's seat-notice workflow (igor PR
     #171) applied to `relays/<login>.yaml`, with the person named by the
     path: `pull_request_target` alone, GitHub-hosted, no `paths` filter,
     reading only the names of the paths the head changes, never their
     contents, and no mention for an event the
     person caused on a pull request they opened. It mentions a login only
     when the base branch holds that login's file or that person opened
     the pull request, so no pull request can make it mention anyone it
     likes; igor's workflow reads the owner from the default branch's
     copy for the same reason. Setup opens a separate
     pull request adding it where the lore repository's default branch
     lacks it; when GitHub refuses it, such as for a `gh` login without the
     `workflow` scope, setup says so and carries on, since no reader
     depends on the notice. Taken under filter 4. *Rejected:* having igor's
     seat-notice workflow cover relay files too, which would make the
     notice wait for igor's release and for a change to another
     repository's spec; it remains the simpler end state if Adam prefers
     one workflow.

Decision 230 came from findings of spec-check's consistency reads, the
fresh reviews of the whole change made before each commit, of the commits
that recorded decisions 223 to 229. It is this change's own. Adam
confirmed it item by item on 2026-10-21, except items 4 and 5, which his
decisions 232 and 235 replace:

230. **Confirmed by Adam (2026-10-21) item by item, except items 4 and 5,
     replaced by his decisions 232 and 235; his decision 246 amends item
     1.** **Details the spec fixes,** each cheap to reverse, taken under
     filter 3 unless noted:
     1. *Amended by Adam's decision 246, which keeps mention rewriting
        on and settles this item.* On Discord the answer session posts
        through discord-bot with none of its header options, which put a
        line above the message, so a relay post starts with its prefix.
        As first written, it also posted with mention rewriting off, so
        an `@name` in the person's words or a quoted record pinged no
        one, and kept every Discord channel off until discord-bot gained
        that option.
     2. The post reader treats `git rebase -x`/`--exec`, `git submodule
        foreach`, `git bisect run` and any other git form that runs a
        command it is given as code to run, so one that names `gh` is
        unreadable, as decision 139 has `git -c`.
     3. The script's `log` command takes its inputs in a file with mode
        0600 in a private directory, never as arguments, as decision 182
        has the two calls take theirs, since a question's text and its
        answer as arguments are readable by every user of a shared host.
     4. *Withdrawn, and replaced by Adam's decision 232.* It had a reader recognise an Igor's App from the lore
        repository's Igor configuration, and count no relay App where it
        couldn't read that configuration. But igor's role-config spec
        forbids any configuration key that names an App identity, and a
        lore repository with no Igor configuration would then have no
        relay App at all. How a reader recognises an Igor's App was left
        to Adam, who answered it with decision 232.
     5. *Replaced by Adam's decision 235, which reads `IGOR_RUN`.* It had
        a session with no person in it count as possibly in an Igor's
        run, reading no lore clone and pushing no citation, until igor
        gave the script a way to tell, so a plain headless session, such
        as `claude -p`, lost its lore search until then.
     6. For a relay App's comment on a handback, the Igor sets
        `answered_by` as well as `authority`: the person whose relay file
        lists that App. The worker can't read the relay files, so without
        this every relayed handback answer would name the wrong person and
        be input. igor PR #216 left this to this change.
     7. When setup proposes the relay file again because someone else last
        changed it, the file's first line is `# confirmed by <login> on
        <date>`, so the pull request changes the file even when the
        relays are the same; otherwise no commit would change it and the
        other person's commit would stay its last change.
     8. A relay-notice comment starts with a fixed first line, and the
        answer session shows such a comment from `github-actions[bot]` as
        a notice, never as a question, so it is never answered by itself
        or logged as a miss.
     9. A reader that can't tell whether GitHub made a signature counts no
        signature at all, the person's own included, and task 0.22 records
        how to tell.
     10. The post reader treats a `gh` command whose first word after
         `gh` is not one of gh's own commands, such as an alias or an
         extension, as unreadable. Otherwise `gh c 5 -b 'User says: yes'`,
         with `c` aliased to `pr comment`, would pass both post hooks as
         no post and forge a relayed answer past decision 203's block.
     11. Decision 203's block of a reserved prefix applies to a body once
         it is reduced as decision 213 reduces a comment, with leading
         whitespace dropped, so ` User says: ` and `**User says:**` are
         blocked as `User says: ` is.

Decision 239 came from writing Adam's decisions 232 to 238 into the
requirements and checking them against igor PR #216 at d9a4724. It is
this change's own:

239. **Confirmed by Adam (2026-10-21) item by item, except item 2, which
     his decision 240 changes; confirming item 5 amends decision 200's
     item 1.** **Details the spec fixes,** each cheap to reverse, taken under
     filter 3 unless noted:
     1. A log file's answer is written as quote lines, each line `> `
        followed by the answer's line, or `>` alone for a blank one, with
        line ends made LF and blank lines at its start and end dropped. A
        reader takes the longest run of quote lines at the body's end as
        the answer, and the line before it must be `## Answer`. Since
        every answer line starts with `>`, a whole comment fits, even one
        holding a `## Answer` line of its own. The rest of decision 183's item 2 holds: a rephrasing's
        `## Rephrased question` and `## Discussion` sections, one line
        each, sit just before `## Answer`, and the question is everything
        above them. *Rejected:* joining the comment onto one
        line, which breaks the equality of decision 236 for a comment
        with list items; and a frontmatter key counting the answer's
        lines, which adds a key the quote marks make needless. Taken under
        filter 4.
     2. *Changed by Adam's decision 240.* It proposed writing an answer
        not taken from a comment, such as a picker answer, in one
        sentence; decision 240 records it in the person's own words.
     3. The `log` command reads an `answer_link`'s comment itself, with
        the person's credentials, and records its text, whatever answer
        the agent passed; when it cannot read the comment it writes
        nothing and says why. In Igor-worker mode it can't read GitHub,
        so the answer text the worker passed, which only identifies the
        comment, stands until the Igor replaces it with the comment's
        text.
     4. An answer from a comment is recorded word for word or not at all:
        when its words hold context more private than what the question
        concerns, the file gets no answer, as for an answer that cannot
        be generalised.
     5. A `Recorded answer: ` post quotes no answer, a log file's
        included: it reads `Recorded answer: see the record below.` and
        gives the record's URL, as decision 200's item 1 already has it for
        any other record. A log file's answer is now a whole comment,
        which could hold @-mentions that would notify people again on
        GitHub, or a `Recorded in: ` line of its own. This amends decision
        200's item 1, which Adam had already confirmed.
        *Rejected:* quoting the answer with its mentions neutralised,
        which needs a rule per surface.
     6. A post made under decline reason 3 for filter 2, 3 or 4 is the
        filter's fixed text followed by the line `The person chose this
        filter.`, which no automatic post holds; that line is how decision
        234's agent tells the two apart. Taken under filter 4.
     7. Setup passes the Discord relay only when discord-bot's `check`
        reports `messageContent` as `true`; `null`, a check that could
        not read the flags, fails as `false` does.
     8. When the relayed answer gives a rephrasing, the log file's answer
        is the relay post's whole text, its `Rephrased question: ` and
        `Discussion: ` lines included, as decision 236 has a writer
        record a comment; the file's own rephrasing sections hold those
        lines too. Recording the answer alone would fail decision 236's
        equality, and every rephrased answer would be unconfirmed.
     9. Whenever the script acts on `IGOR_RUN`, its output says so. A
        repository can set the variable in a person's session, through
        its committed Claude Code settings or an `.envrc`, and the
        script would then search no lore and log nothing to a lore
        repository without the person seeing why.
     10. This change's *lore repository* is always the one holding the
        entries, which igor PR #216 calls the *destination repository*;
        igor's specs keep *lore repository* for the one holding the
        Igor's configuration, as #208 names it. The spec says so where it
        defines the term.
     11. The script also runs in Igor-worker mode under `IGOR_RUN=igor`,
        though only `worker` limits the search to a working tree:
        it pushes nothing to a lore repository and leaves its files for
        the Igor, which sets `asked_from` on them as on a worker's, as
        igor PR #216's *An Igor publishes the questions-branch files its
        worker reports* has it. Before, the format allowed `asked_from`
        only in a file an Igor pushed for its worker, which #216 flagged.
     12. Aligned with igor PR #216: the spec states that a `project:X`
        entry is neither shown nor fired when the item's repository is
        more visible than X (#216's decisions 53 and 54), and its
        scenario of a `project:` entry inside an Igor says the item's
        repository is no more visible; igor's bare flag, which a run
        raises when it meets a question with a category and which says
        nothing more, is raised by the model steps igor PR #153 runs after
        the worker as by the worker itself (#216's decisions
        60 and 64; decisions 244 and 245 later add the categories the
        flag lists); the Igor's handling of a handback answer
        (`authority`, `answered_by`, the relay files it reads, and the
        answer it records) is pointed to, not restated. #216's decisions
        58 and 59,
        on fetching under `igor run` and the hashed record of handback
        questions, contradict nothing here.

307. **Confirmed by Adam (2026-10-25), with "on Linear or Discord"
     replaced by his decision 314.** **The merge criterion of decision
     302.** A log file with no `asked_in` is merged with a thread message
     on one machine only when the file is on a lore repository that is
     not private, the message is on Linear or Discord, the two questions are the same once
     every mention is removed (a file tags `@login`, a Linear or Discord
     message mentions the person's user on that surface), the file's
     `asked` day is the message's day in UTC, and the file matches no
     other message this machine has polled and the message no other
     file. It is judged again at each poll; a merge that ends shows both
     again and leaves any answer already given in place.
     *Rejected:* merging on the same question alone, which joins two
     askers' questions in the same words.

**Still open:**

The archive waits for task 4.3 to tag every expected gap, which waits
for igor to build `igor lore-search` and let a role's `commands` list
the skill's script (decisions 249 and 253).

The five questions raised while recording decisions 264 and 265, on
agreeing to a recorded answer, are settled by decisions 266 and 267.

The two questions raised while recording decisions 266 and 267 are
settled by decisions 268 and 269.

The three questions raised while recording decisions 268 and 269 are
settled by decisions 270 to 272.

The three questions raised while recording decisions 270 to 272 are
settled by decisions 273 to 276.

The four questions raised while recording decisions 273 to 276 are
settled by decisions 277 to 280.

The four questions raised while recording decisions 277 to 280 are
settled by decisions 281 to 284.

The five questions raised while recording decisions 281 to 284 are
settled by decisions 285 to 287.

The five questions raised while recording decisions 285 to 287 are
settled by decisions 288 to 291.

The four questions raised while recording decisions 288 to 291 are
settled by decisions 292 to 295.

The six questions raised while recording decisions 292 to 296 are
settled by decisions 297 to 299.

The seven questions raised while recording decisions 297 to 299 are
settled by decisions 300 to 306.

The eight questions raised while recording decisions 300 to 307 are
settled by decisions 308 to 315.

The five questions raised while recording decisions 308 to 315 are
settled by decisions 316 to 320.

The four questions raised while recording decisions 316 to 320 are
settled by decisions 321 to 324.

Six of the seven questions raised while recording decisions 321 to 324
are settled by decisions 325 to 330. The seventh, on signing in a project
set up for a GitHub App, waits for Adam: there the script commits as
the bot, unsigned (decision 105), so how can an answer file with no link
be the person's answer?

Open on igor PR #216's side, at the head last read, 59e7561, which records Adam's decisions
up to 149 in #216's own numbering, decisions 244 and 245 among them as
its decisions 92 and 97:
- **#216 says only an Igor writes `asked_from`.** Decision 282 adds a
  second writer: an answer session's miss copies the `asked_from` of the
  questions-branch file it closes. #216's push conditions and its
  decision 42 should allow for that.
- **#216 should refuse a worker's file holding `handled` or `closes`,**
  as it refuses one holding `asked_from`. Only an answer session writes
  a handled file (decision 273), but #216 pushes any file a worker
  reports that holds no `authority` as an unanswered question file, so
  it would push a handled file too, and a worker steered by item text
  could then close, on every machine and for good, whichever
  questions-branch file the planted `closes` names (decision 297).
- **#216's Igor should keep, in its own record of the handback (#216's
  decision 59), the name of the questions-branch log file it pushed for
  the question** (decisions 324 and 327), so that a later run can name
  that file in `answers`; the handback comment may show the name for
  people, but the run never reads it from there. Without the record, the
  run writes no `answers`.
- **#216's Igor should write `asked_in`** in a worker's log file as the
  URL of the assigned issue or pull request the question is shown from,
  not the handback comment (decision 326), a Linear or Discord one only in a
  private lore repository (decision 302), and name in `answers` the file
  an answer file answers (decision 303), adding `answers` itself and
  refusing a worker's file that holds it (decision 310). Without
  `answers`, the answer session keeps showing the answered file as
  unanswered. A GitHub `asked_in` is withheld when the thread's
  repository is more private than the lore repository (decision 315).
- **#216 should widen its definition of a citation to include a
  person's cite.** It defines a citation as an agent's record that a
  lore entry answered a question so that no person was asked. Decision
  259 has a person's cite of an `active` entry in scope push one too,
  and decision 262 counts as a cite a decline under reason 2 (reason 3
  before decision 330) with filter
  1 naming such an entry, for a question that did reach the person.
- **Two of #216's Still open items for this change are done.** It asks
  this change to amend 245 to match its decision 97, without a fixed
  order, and to align 243 with its decisions 84 and 89. Both are now so,
  and #216 can drop the items.
- **How an Igor runs the inquisitor skill itself** has no mechanism yet in
  #216 or igor #211. Settled: igor marks that run with `IGOR_RUN=igor`,
  and the script then searches lore only through `igor lore-search` and
  pushes nothing (decisions 229 and 235). Open: which other sources that
  run's filter 1 covers, how the run hands its files to the Igor, and
  whether it can read GitHub.
- #216's task 4.8, like task 0.21 here, measures whether GitHub reports
  which App wrote a comment; until a measurement shows GitHub does, every
  `User says: ` comment is input.

Tasks 0.15 to 0.24 measure facts the answer session relies on: what
GitHub's notifications endpoint reports, how Linear and Discord show
mentions and replies, how the Linear relay posts a comment, that a command the mod runs reaches no tool hook,
that a mod keeps polling while its session is idle or in the
background, how setup checks a relay's access to each channel,
whether GitHub reports which App wrote a comment, and whether a reader
can read the pull request and the signature behind a relay file's last
change, and whether the URL an asking agent records as `asked_in` is the
one the answer session reads for that message, and how setup can tell
that a questions-branch commit will be verified for the person. Each task says what the spec does until it is measured.

The rest of this section has two lists. The first is the changes
elsewhere that this change depends on:
- igor PR [#216](https://github.com/adamstallard/igor/pull/216), with igor
  issue [#215](https://github.com/adamstallard/igor/issues/215), which
  amends igor's lore-firing spec (decision 60) and holds every rule for
  an Igor's citations (decisions 123 and 129);
- igor PR #202, the scribe's records (decision 63);
- igor PR #153, signed publishing (decision 124);
- in bug-hunter, a rule for a vulnerability fix's regression test
  (decisions 108 and 205);
- shared-skills PR #1, merged, which turns Discord's Message Content
  intent on and reports it in `check` (decision 238), and posts with no
  header line unless a header option is given (decision 246);
- a change to the github-app skill, not yet open, under which its `token`
  command refuses an identity marked as a relay (decision 233);

The second list holds the facts that tasks 0.1 to 0.14 measure before
anything is built, each with what the spec does if it turns out false,
then what igor PRs #216, #153 and #202 hold, and last one extension this
change does not plan. Task 0.12 is already measured: its result is the
item on Igor-worker mode.

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
- **Can the script tell whether a person is in the session, and whether
  a headless session can post?** If
  it can't tell the first, the session counts as having no person in it,
  so a picker is never opened with nobody to answer it. Whether it runs in
  an Igor's run, and whether that is a worker's run or the Igor's own, it
  reads from `IGOR_RUN` (decision 235), and
  then it reads no lore clone, since `igor lore-search` searches lore
  (decision 229). If
  it can't tell whether a headless session that is not an Igor worker can
  post, the session counts as unable to post, and asks nowhere (decision
  143).
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
- **Can the private fork's pull request be merged before the advisory is
  published?** Task 0.13 measures it. Until it shows the merge waits for
  publication, the fork's commit messages describe no weakness, and the
  full description goes in the advisory's text (decision 127). If the
  merge can come first, a fork commit is described normally only when the
  agent knows, as it writes the commit, that the pull request will be
  merged as the advisory is published, because the person
  publishing it said so (decision 108). Until it shows the merge waits,
  a regression test goes in the fork only on that person's word
  (decision 205).
- **bug-hunter needs a matching note:** a vulnerability fix's regression
  test lands only in the advisory's private fork, or publicly after the
  advisory is published (decision 108). Until task 0.13 shows the fork's
  pull request merges only at publication, it goes in the fork only when
  the person who will publish the advisory has said the pull request
  merges at that moment (decision 205). A separate change to bug-hunter
  carries it.
- **Does GitHub's API give a comment's author and a commit's verified
  signer as decision 78 needs?** If not, every `questions`-branch `decision`
  or `agent` file counts as input.
- **igor PR #216** holds what this change relies on from igor, and has not
  merged:
  - its requirement *An Igor publishes the citations its worker reports*
    says what a worker reports for a citation, with no category, and when
    and which citations an Igor pushes, from a worker or from an
    inquisitor run the Igor starts itself (decisions 123 and 129), in
    this change's format (decision 110);
  - igor's review counts citations on the lore repository's `questions`
    branch (its decision 8; decision 83 here), and shows them as "not
    checked" when every Igor push of them failed (its decision 32;
    decision 180 here);
  - its id check reports an out-of-scope collision during a run only as
    "id taken" (its decision 6; decision 92 here), and such an entry is
    not proposed during the run (decision 128 here);
  - a search during a run reads only the lore repository the Igor injects
    from (decision 133 here);
  - its task-execution requirement *Transcripts and outcomes are captured
    to the state branch* defines the flag a worker raises when its
    run meets a question with a category, and what the Igor does with it
    (decision 136 here), with the categories the flag lists (its
    decisions 92 and 97; decisions 244 and 245 here);
  - its requirement *An Igor publishes the questions-branch files its
    worker reports* says when and which of a worker's question, miss and
    `authority: agent` files the Igor pushes, including the answer to a
    handback when a worker re-works the item, and that a flagged run
    pushes none (its decisions 20, 21, 24 and 26; decisions 142, 145, 149
    and 150 here), and counts as flagged any run that ends without its
    worker's completed report (its decision 38; decision 221 here). The
    same requirement checks each file with igor PR
    #217's credential matcher and pushes a person's answer only beside a
    question the Igor asked, as its own record of the handback holds it
    (its decisions 28, 30 and 41; decisions 178, 179 and 221 here), reads
    the lore repository's visibility at every push (its decision 37), sets
    each file's `asked_from` (its decision 42; decision 221 here), and lets
    a file's `repository` key name any repository,
    whether or not the run's role works it (its decision 33, which amends
    its 20);
  - its requirement *An Igor runs its worker's lore searches* defines
    `igor lore-search`, the search command that a worker calls, and that
    an inquisitor run the Igor starts itself calls too (decision 229). It
    matches plain text and ranks and caps its hits as filter 1 does, and
    labels
    each question file it returns as an answer, as input, as unanswered
    or as a miss (its decision 23; decisions 144 and 183 here). It runs
    this change's authority checks before it labels a file an answer, and
    shows the file as input, labelled unconfirmed, whenever a check can't
    run or fails (its decision 34; decisions 212 to 214 here). Those
    checks now read each person's `relays/<login>.yaml` as of the commit
    igor PR #208's lore read last applied, and cannot run when it has
    applied none (decisions 241 and 242), counting the file only when
    its last change was that person's (decisions 216, 224 and 225). The
    Igor reads it too to decide `authority` for a relay App's handback
    answer;
  - a questions-branch file is in scope for every role whose Igor uses
    that lore repository, and is returned only to a run whose item's
    repository is no more visible than the file, judged by the more
    private of its `repository` and `asked_from` (its decisions 25, 27
    and 42; decisions 148, 151 and 221 here);
  - its `graceful-handoff` and `work-triage` deltas hold igor's side of
    decision 243: the flagged run's handoff, its host file and the
    release of a held item, by the #216 decisions 243 cites (decisions
    243 to 245 here).
- **igor PR #153, signed publishing,** would have an Igor whose role
  lists prose or bug-hunter push only commits that went through those
  skills and carry their trailers. Citation commits
  carry none (decisions 90 and 110), so #153 should exempt an Igor's
  commits to a lore repository's `questions` branch. That is #153's to
  settle (decision 124).
- **Can an Igor worker post?** igor's task-execution requirement keeps
  every credential but its seat's out of the worker's environment, but a
  `gh` login stored in the home directory the worker is given is neither
  an environment variable nor in its working tree. Task 0.14 measures it.
  If a worker can post, it still asks only in its handback comment
  (decision 126), and the credential within its reach is reported to igor
  as a breach of that requirement.
- **Igor-worker mode waits for igor to build its search command.** Task
  0.12 measured that an Igor worker can't run this skill, today or once
  igor PRs #174 and #175 land as specified (decision 141; design.md gives
  the evidence). The worker has no `inquisitor.json`, no `gh` login, no
  picker and no hooks, and can't read the lore checkout. By decision 144,
  filter 1 in a worker calls igor's read-only search command instead,
  `igor lore-search`, which igor PR #216 specifies and igor has not built.
  #216's task 4.5 has yet to measure whether a worker can give the
  command its standard input. If it can't, #216 gives the command another
  way to take the text, and until this change adopts that way, a worker
  searches no lore, as this change's spec says for a command that fails. The skill's script must also be one the worker can run,
  which today means a role's `commands` lists it. Until igor builds the
  command and lets a worker run the script, a worker searches no lore, as
  the spec's fallback says, and gate two builds everything else.
- **Can the post hook tell an Igor's handback comment from other posts?**
  Igor's own code might post it outside any tool call, where no hook sees
  it, or an agent might post it with `gh`. If the hook can't tell, it would
  block an unvetted question in such a comment, against decision 40, until
  the Igor inquisitor role's work marks the comment.
- **igor PR #202, the scribe's records.** Two of its open points decide
  when decision 109 can apply:
  - #202 has not settled how the scribe recognises an approval given off
    GitHub. Until it does, the scribe can't mark a record of an answer
    typed directly on Discord, Slack or Linear `accepted`, so such an
    answer counts only when a
    person writes it into another decision document that filter 1 counts,
    such as one on the default branch of the repository the question
    concerns.
  - #202's spec puts a decision about several repositories in the lore
    repository. Filter 1 reads the lore repository's decision records once
    #202 says where they live there (decision 66, task 7.0). Until then,
    a scribe's record can answer only a question about one repository.
- **Not planned here: proving an answer by a link to a message on another
  surface,** such as Discord, with that surface's API vouching for the
  message's author, and a file in the lore repository mapping the author
  to a GitHub login. igor issue #160 already maps a Discord user to a
  GitHub login, by a configuration entry keyed by the Discord user id; a
  later change would choose between that entry and a file in the lore
  repository. Until one adds it, an answer typed directly on such a
  surface counts only through a decision document, such as the scribe's
  record (decision 109). An answer typed in the answer session and
  relayed there counts through its log file's signature (decision 250).

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
- An answer session gives a person one place to answer the questions asked
  of them on GitHub, Linear and Discord. A relay identity posts each answer
  for them. The answer session runs the four filters on each incoming
  question too: it answers what is already recorded, replies to an agent's
  question that another filter clearly stops, and lets the person decline
  a question, logging a miss where one is due.
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
- `answer-session`: where a person answers the questions asked of them in
  the channels they subscribe to, each answer posted by a relay identity:
  its configuration and setup, the four sources of questions, polling,
  relaying, editing, asking the asker, declining to answer, the filters
  it runs on incoming questions, the misses it logs, where its state
  lives, the lock, and the session's model in a discussion.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/inquisitor/` with its scripts, hooks and tests, and
  the answer session's mod, built from the prototype tagged
  `answer-session-ui-approved-v0.1-33` (decisions 231 and 263).
- The answer session posts through the github-app, linear-app and
  discord-bot skills, so it needs shared-skills PR #1, which adds
  discord-bot, merged first. setup writes `~/.local/bin/answer`.
- prose: its posting hook's command reader moves to `.agents/lib/gh-post/`,
  so the inquisitor's post hook reads posts the same way. The reader also
  reads posts sent through the github-app skill and `gh api` comments
  (decision 57), and blocks a data command such as `python3 -c` that runs
  code naming `gh` (decision 139). It also reads a post's title, and a
  title it can't read makes the call unreadable (decision 206). prose's
  hook, which calls the reader, gains all of these changes.
- In each repository where it runs, the skill writes `.inquisitor/`. In a
  team's lore repository, it pushes to an orphan branch named `questions`,
  and the answer session's setup proposes, by pull request, the person's
  `relays/<login>.yaml` on its default branch (decisions 216 and 224), and
  a `relay-notice.yml` workflow that mentions a relay file's person on a
  pull request changing it (decision 228).
- prose: its pass skips files under `.inquisitor/`, and its `DECISIONS.md`
  says why (decision 134).
- github-app: its SKILL.md sets `G` in the same command as each use, or
  writes the script's full path (decision 135). A separate change to it,
  not made here, has its `token` command refuse an identity marked as a
  relay (decision 233).
- The README's skills table, and its list of skills that turn on a hook.
- This pull request's first commit adds `openspec/`, `AGENTS.md` and
  spec-trace's CI workflow to shared-skills.
