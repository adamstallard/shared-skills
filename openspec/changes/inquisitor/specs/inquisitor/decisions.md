# inquisitor: constraints and rejected alternatives

## Constraints

- **Constraint: A picker `ask` record keeps no option's label, so the records cannot show later whether the person took the recommendation.**
  Because: the labels are part of the question's text, which no verdict record holds.
  Evidence: the picker's `questions` array carries each option's label beside the question, and the records keep that text only as a hash (inquisitor spec: *The two calls' files and records stay private*), adamstallard/shared-skills#25
  Holds while: verdict records hold no question text.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: An idle machine keeps its verdict records, each naming its question by plain SHA-256, until the next call or hook, so anyone who can read the state folder and guesses a short question's text can confirm it was asked, with a category or without.**
  Because: only the agent's user can read the state folder, so a guesser needs that user's access, or root's, first.
  Evidence: the skill runs nothing but its two calls and its hooks, so a record past its 2 hours is deleted only when one of them next reads the records (inquisitor spec: *The two calls' files and records stay private*), adamstallard/shared-skills#25
  Holds while: the skill runs nothing between its calls and hooks.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/scripts/check-ask.sh, .agents/skills/inquisitor/scripts/check-post.sh

- **Constraint: An agent's `Related: ` line links only a decision that everyone who can read the question can read, and no hook checks that.**
  Because: the agent names the decision at the second call and adds the line after it, so no vetting sees the line, and the hooks only block a credential pattern in it.
  Evidence: the hooks match a question's text without that line (inquisitor spec: *A related-decision line is one URL on a line of its own*), adamstallard/shared-skills#25
  Holds while: the related-decision line is left out of the question's hash.
  Paths: .agents/skills/inquisitor/SKILL.md, .agents/skills/inquisitor/scripts/check-post.sh

- **Constraint: The host's transcripts, such as Claude Code's under `~/.claude/projects/`, hold a question asked through the picker in full.**
  Because: the skill's hash-only and 2-hour rules cover only its own records, and the host's transcripts are outside its control.
  Evidence: Claude Code writes each session's transcript, its tool calls included, under `~/.claude/projects/`, adamstallard/shared-skills#25
  Holds while: the host keeps transcripts the skill does not write.
  Paths: .agents/skills/inquisitor/

- **Constraint: Until its work merges, a repository's log file is invisible to parallel work, so an agent on another branch may ask the same question again.**
  Because: a change's questions belong in its history and merge with it.
  Evidence: a file committed on a work branch reaches the default branch only when that branch merges, adamstallard/shared-skills#25
  Holds while: one repository's questions are committed with the work under `.inquisitor/questions/`.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: GitHub's events API shows each citation push's pusher and time to anyone who can see the lore repository.**
  Because: that repository is never more visible than the question's, so the pusher is shown only to people who may already see the question.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events
  Holds while: a citation is pushed with a person's own credentials.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Filter 1 does not find a lore entry merged since the person's last fetch.**
  Because: filter 1 fetches only the `questions` branch, and reads each lore clone's default branch as last fetched.
  Evidence: inquisitor spec: *A lore entry is read from the remote-tracking default branch*, adamstallard/shared-skills#25
  Holds while: filter 1 fetches no lore clone's default branch.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: A `project:` scope matches only a repository's short name, so a project whose repositories have other names needs a mapping file in the lore repository, read by igor and the inquisitor alike, which nothing provides.**
  Because: igor matches a project scope that way, and igor and the inquisitor must read a lore entry's scope alike.
  Evidence: `scopeMatches` in igor's `src/firing.ts`, https://github.com/adamstallard/igor/blob/main/src/firing.ts
  Holds while: igor matches a project scope by a repository's short name.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: A questions-branch log file's name carries a slug of its question's words, though the Igor's record of a handback holds none of them.**
  Because: the record finds the file by its name's suffix and date, so it needs no words, while the file itself holds the question's text on a questions branch no more visible than that question.
  Evidence: inquisitor spec: *A later Igor run names the answered file only from the Igor's record*, adamstallard/shared-skills#25
  Holds while: a log file's name carries a slug.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Among proven answers to one question, two machines that first fetched a file at different times can order it differently against a file pushed between those fetches.**
  Because: a signature's date is the earlier of the signed commit's committer date and this machine's first fetch of it, so no signer can date a commit into the future and outrank every later answer.
  Evidence: the signer sets a commit's committer date, https://git-scm.com/docs/git-commit#_commit_information
  Holds while: a signature's date is bounded by this machine's first fetch.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Someone who can push to a person's open pull request, such as a maintainer GitHub's "allow edits by maintainers" lets push to it, can change the person's relay file under it, and the change counts once merged.**
  Because: the relay notice mentions the person for that push, so they can close the pull request.
  Evidence: GitHub lets maintainers push to a fork's pull request branch when its author allows edits, https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/allowing-changes-to-a-pull-request-branch-created-from-a-fork
  Holds while: a reader ties a relay file to its person by who last changed it on the default branch.
  Paths: .agents/skills/inquisitor/

- **Constraint: Anyone who can rewrite the lore repository's default branch can restore an older relay file of the person's own, listing an App the person removed, so removing a compromised App from the file does not stop it speaking for the person.**
  Because: uninstalling the App or revoking its key does stop it, and the README says to do that.
  Evidence: a restored file's last change is still the person's own commit, which the reader counts (inquisitor spec: *A reader counts a relay file only when its person made its last change*), adamstallard/shared-skills#25
  Holds while: a relay file counts by who last changed it on the default branch.
  Paths: .agents/skills/inquisitor/

- **Constraint: A rule that depends on igor states its end state, with no clause for an igor state before the igor change it needs lands.**
  Because: igor has no users yet, so an interim design would serve no one.
  Evidence: igor runs for no team yet, https://github.com/adamstallard/igor
  Holds while: igor has no users.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md

## Rejected

- **Rejected: The hook running the four filters itself.**
  Facing: proving that an agent ran the filters before its question reaches a person.
  Lost because: a hook is a script with no model, so it cannot tell whether two options both have merit, which is filter 3's test, adamstallard/shared-skills#25.
  Instead: the agent runs the script's two calls, and a hook lets a question through only on the fresh verdict record they leave.
  Paths: .agents/skills/inquisitor/scripts/check-ask.sh, .agents/skills/inquisitor/scripts/check-post.sh

- **Rejected: A signed footer in each question, as prose signs a post.**
  Facing: proving that a question passed the filters.
  Lost because: the person reads the question in the picker, where a hash is noise, adamstallard/shared-skills#25.
  Instead: verdict records keyed by the question's hash, in the user's state folder.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/scripts/check-ask.sh

- **Rejected: Changing bug-hunter's Step 9 rules on their own, ahead of the inquisitor skill.**
  Facing: bug-hunter's Step 9 recommendations each reaching the person as a question.
  Lost because: that would be a rule of bug-hunter's own that skips the shared filters, adamstallard/shared-skills#25.
  Instead: Step 9 runs each recommendation through the inquisitor's four filters, and bug-hunter changes only once the inquisitor skill exists.
  Paths: .agents/skills/bug-hunter/SKILL.md

- **Rejected: Keying verdict records' hashes with an HMAC and a per-HOME key.**
  Facing: an idle machine's records letting anyone who can read them confirm that a guessed question was asked.
  Lost because: the hooks must read the key, so it would sit under the same HOME, readable by whoever can read the records, and would stop only a guesser holding a copy of the records but not the key, adamstallard/shared-skills#25.
  Instead: plain SHA-256, in a state folder only the agent's user can read.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/scripts/check-ask.sh, .agents/skills/inquisitor/scripts/check-post.sh

- **Rejected: Deleting expired verdict records on a timer or at session end.**
  Facing: an idle machine's records letting anyone who can read them confirm that a guessed question was asked.
  Lost because: it would shorten the exposure but needs something to run when no call or hook does, adamstallard/shared-skills#25.
  Instead: the first call or hook to read the records after a record's 2 hours deletes it.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/scripts/check-ask.sh, .agents/skills/inquisitor/scripts/check-post.sh

- **Rejected: Searching a fixed `docs/decisions/` for igor's scribe's records until igor PR #202 settles their path.**
  Facing: filter 1 reading igor's scribe's decision records before #202 says where they are kept.
  Lost because: it is an interim design for an igor dependency while igor has no users, adamstallard/igor#202.
  Instead: filter 1 searches the path #202 sets, in the repository the question concerns and in the lore repository.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Rejected: The script refusing a lesson that quotes a logged question.**
  Facing: question and miss logs holding private content that a lesson sent to shared-skills could carry.
  Lost because: a lesson in general terms never quotes one, adamstallard/shared-skills#25.
  Instead: a lesson drafted from misses is general, and lands only through a pull request or a memory edit.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py, .agents/skills/inquisitor/SKILL.md

- **Rejected: Counting a relay file's pull request only when all its commits are the person's.**
  Facing: someone else pushing to a person's open pull request to change their relay file.
  Lost because: neither a commit nor its pull request in GitHub's API names who pushed it, and the events API, which does, keeps only recent events, https://docs.github.com/en/rest/activity/events.
  Instead: a reader counts the file only when its last default-branch change came from its login, and the relay notice mentions the person when someone else pushes to their pull request.
  Paths: .agents/skills/inquisitor/

- **Rejected: igor's seat-notice workflow covering relay files too.**
  Facing: warning a person when their relay file is about to stop counting.
  Lost because: though simpler once igor shipped it, it would make the notice wait for igor's release and a change to another repository's spec, adamstallard/igor#171.
  Instead: the inquisitor ships its own `relay-notice.yml`, modelled on the seat-notice workflow igor PR #171 specifies.
  Paths: .agents/skills/inquisitor/

- **Rejected: Accepting an `answers` key planted in a worker's file.**
  Facing: which questions-branch file an answer reported by an Igor's worker answers.
  Lost because: only the Igor, from its own record of the handback, knows which file was answered, so #216 pushes only an `answers` key the Igor writes, adamstallard/igor#216.
  Instead: igor PR #216 is asked to refuse a worker's file holding `answers`, and the Igor adds the key itself.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Rejected: A glossary requirement holding every term.**
  Facing: defining once each term the inquisitor spec uses.
  Lost because: it ran to 17,651 characters, and `openspec validate --strict` fails any requirement over 500, adamstallard/shared-skills#25.
  Instead: the inquisitor's Purpose defines the terms its spec uses throughout, and any other term is defined in the requirement that sets its rule.
  Paths: openspec/specs/inquisitor/spec.md

- **Rejected: Archiving the rest of the change and leaving the Igor-worker scenarios in an open change.**
  Facing: Igor-worker scenarios that only igor's unbuilt work can make pass, while spec-trace's CI fails an untagged scenario in `openspec/specs/`.
  Lost because: it would split each capability's scenarios between `openspec/specs/` and an open change, adamstallard/shared-skills#25.
  Instead: the change is archived only once task 4.3 tags every expected gap and igor PR #216 has merged.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md
