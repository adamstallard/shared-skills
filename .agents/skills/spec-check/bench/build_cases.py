"""Build the spec-check benchmark cases.

Each case is a git repository: one commit on `main` holding the base tree
(BASE below), plus the case's OpenSpec change staged on top, uncommitted.

    python3 -I build_cases.py <out-dir>

writes <out-dir>/<case>/ for every case in CASES, replacing any already
there. rubrics.json beside this script says what each case must and must not
report.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import textwrap


def d(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


ISSUES = "https://github.com/example/notes/issues"

BASE: dict[str, str] = {
    "README.md": d("""
        # notes

        A small note-taking service: users keep notes, share them, and get a
        daily digest email. Specs live under openspec/.
        """),
    "src/session/store.py": "# Session storage in Redis.\n",
    "src/notify/digest.py": "# Daily digest email.\n",
    "src/audit/log.py": "# Audit log writer.\n",
    "openspec/config.yaml": "schema: spec-driven\n",
    "openspec/specs/session-store/spec.md": d("""
        # session-store Specification

        ## Purpose
        Keeps each signed-in user's session: where it is stored, how long it
        lasts, and when it ends.

        ## Requirements
        ### Requirement: Session expiry
        A session SHALL expire after 30 minutes without a request from its user.

        #### Scenario: Idle session expires
        - **WHEN** a session receives no request for 30 minutes
        - **THEN** the next request with that session is treated as signed out

        ### Requirement: Session storage
        Sessions SHALL be stored in Redis, keyed by session id.

        #### Scenario: Session survives a server restart
        - **WHEN** an application server restarts
        - **THEN** a session created before the restart is still valid afterwards
        """),
    "openspec/specs/session-store/decisions.md": d(f"""
        # session-store: constraints, rejected alternatives and rationale

        ## Rationale
        - **Rationale: Session expiry.**
          Without an idle limit, a session left open on a shared computer stays usable indefinitely.
          Evidence: the 2026-01 shared-terminal report, {ISSUES}/3
        """),
    "openspec/specs/notifications/spec.md": d("""
        # notifications Specification

        ## Purpose
        Says which emails the service sends to users, how often, and what
        they may contain.

        ## Requirements
        ### Requirement: Daily digest
        The service SHALL send each user at most one digest email per day, listing notes shared with them that day.

        #### Scenario: Several shares in one day
        - **WHEN** three notes are shared with a user on one day
        - **THEN** the user receives one digest email that lists all three

        ### Requirement: No note bodies in email
        An email SHALL NOT include the body of a note; it SHALL link to the note instead.

        #### Scenario: Digest links instead of quoting
        - **WHEN** a digest lists a shared note
        - **THEN** the email shows the note's title and a link, and none of its body
        """),
    "openspec/specs/notifications/decisions.md": d(f"""
        # notifications: constraints, rejected alternatives and rationale

        ## Rejected
        - **Rejected: Sending the digest through a hosted newsletter service.**
          Facing: Running our own mail delivery for the digest.
          Lost because: the providers reviewed all require uploading every recipient list, which the 2026-04 data-protection review refused, {ISSUES}/41.
          Instead: The digest goes out through the service's own SMTP relay.
          Paths: src/notify/digest.py

        ## Rationale
        - **Rationale: No note bodies in email.**
          Email is stored by third parties outside our deletion controls, so a body sent by email outlives the note's deletion.
          Evidence: the 2026-04 data-protection review, {ISSUES}/52
        """),
    "openspec/specs/audit-log/spec.md": d("""
        # audit-log Specification

        ## Purpose
        Records who deleted what, so that an administrator (a user with the
        admin role) can answer for every deletion later.

        ## Requirements
        ### Requirement: Audit entry for each deletion
        Every note deletion SHALL write an audit entry holding the actor's user id, the note id and the time.

        #### Scenario: User deletes a note
        - **WHEN** a user deletes a note
        - **THEN** an audit entry with that user's id, the note id and the time is written

        ### Requirement: Audit retention
        Audit entries SHALL be kept for 90 days after they are written, and then deleted.

        #### Scenario: Entry older than 90 days
        - **WHEN** an audit entry is 91 days old
        - **THEN** it has been deleted

        #### Scenario: Entry younger than 90 days
        - **WHEN** an audit entry is 89 days old
        - **THEN** it is still readable
        """),
    "openspec/specs/audit-log/decisions.md": d(f"""
        # audit-log: constraints, rejected alternatives and rationale

        ## Rationale
        - **Rationale: Audit retention.**
          Disputes about a deletion reach support within 60 days in practice, so 90 days covers them with margin.
          Evidence: support ticket ages measured over 2025, {ISSUES}/18
        """),
}


def change(name: str, title: str, why: str, what: str, capability: str, delta: str,
           design: str | None, tasks: str) -> dict[str, str]:
    base = f"openspec/changes/{name}"
    files = {
        f"{base}/proposal.md": d(f"""
            # {title}

            ## Why
            {why}

            ## What Changes
            {what}
            """),
        f"{base}/specs/{capability}/spec.md": d(delta),
        f"{base}/tasks.md": d(tasks),
    }
    if design is not None:
        files[f"{base}/design.md"] = d(design)
    return files


CASES: dict[str, dict[str, str]] = {}

# 1. A delta that contradicts another capability's requirement (audit-log retention).
CASES["contradiction"] = change(
    "account-deletion", "Account deletion",
    "Users ask to delete their account and everything tied to it, and today only support can do it.",
    "- New capability `account-deletion`: a user deletes their own account from settings.",
    "account-deletion", """
    ## ADDED Requirements
    ### Requirement: Self-service account deletion
    A signed-in user SHALL be able to delete their own account from the settings page, after confirming their password.

    #### Scenario: User deletes their account
    - **WHEN** a user confirms deletion with their password
    - **THEN** the account and its notes are deleted and the user is signed out

    ### Requirement: Account deletion removes audit entries
    When an account is deleted, the service SHALL delete every audit entry whose actor is that account, at the same moment.

    #### Scenario: Audit entries go with the account
    - **WHEN** a user who deleted notes yesterday deletes their account
    - **THEN** no audit entry with that user's id remains
    """,
    """
    ## Context
    Deletion is support-only today.

    ## Decisions
    - Deletion asks for the password again, so an unattended signed-in browser cannot delete an account.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Add the delete-account form to settings
    - [ ] 1.2 Delete the account, its notes and its audit entries in one transaction
    """,
)
CASES["contradiction"]["openspec/changes/account-deletion/specs/account-deletion/spec.md"] = (
    "## Purpose\nLets a user delete their own account, and says what is deleted with it.\n\n"
    + CASES["contradiction"]["openspec/changes/account-deletion/specs/account-deletion/spec.md"]
)

# 2. A requirement with no scenario.
CASES["no-scenario"] = change(
    "digest-opt-out", "Digest opt-out",
    "Some users do not want the daily digest at all, and the only way out today is to unsubscribe from every email.",
    "- `notifications`: a user can turn off the daily digest, and it stops promptly.",
    "notifications", """
    ## ADDED Requirements
    ### Requirement: Digest opt-out
    A user SHALL be able to turn off the daily digest from the settings page.

    #### Scenario: User turns the digest off
    - **WHEN** a user turns the digest off in settings
    - **THEN** the setting shows the digest as off

    ### Requirement: Opt-out takes effect within an hour
    The service SHALL send no digest to a user more than one hour after that user turns the digest off.
    """,
    """
    ## Context
    The digest job runs hourly per time zone.

    ## Decisions
    - The opt-out is a per-user flag read by the digest job at send time, so no queued digest needs cancelling.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Add the digest flag and settings toggle
    - [ ] 1.2 Skip opted-out users in the digest job
    """,
)

# 3. A decision-record entry with no evidence.
CASES["record-no-evidence"] = change(
    "session-region-pinning", "Session region pinning",
    "We now run Redis in two regions, and a session read from the far region adds about 80 ms per request.",
    "- `session-store`: a session is stored in the Redis of the region that created it.",
    "session-store", """
    ## ADDED Requirements
    ### Requirement: Session pinned to its region
    A session SHALL be stored only in the Redis instance of the region that created it.

    #### Scenario: Session created in the EU
    - **WHEN** a user signs in through the EU region
    - **THEN** their session is stored in the EU Redis and in no other
    """,
    """
    ## Context
    Two regions, EU and US, each with its own Redis.

    ## Decisions
    - The region is encoded in the session id's first two characters, so any server can find the right Redis without a lookup.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Prefix session ids with the region
    - [ ] 1.2 Route session reads by prefix
    """,
)
CASES["record-no-evidence"]["openspec/specs/session-store/decisions.md"] = BASE[
    "openspec/specs/session-store/decisions.md"] + d("""
    - **Rationale: Session pinned to its region.**
      Reading a session from the other region's Redis would make every request slower and would copy EU users' sessions to the US.
    """)

# 4. design.md repeats the base notifications record's Rejected entry on
#    hosted newsletter services, which belongs only in the record.
CASES["design-duplicates-record"] = change(
    "digest-send-hour", "Digest send hour",
    "Users get the digest at midnight UTC, which is mid-afternoon for some of them and the middle of the night for others.",
    "- `notifications`: the digest goes out at 07:00 in the user's own time zone.",
    "notifications", """
    ## MODIFIED Requirements
    ### Requirement: Daily digest
    The service SHALL send each user at most one digest email per day, listing notes shared with them that day, at 07:00 in the user's time zone.

    #### Scenario: Several shares in one day
    - **WHEN** three notes are shared with a user on one day
    - **THEN** the user receives one digest email that lists all three

    #### Scenario: Digest arrives in the morning
    - **WHEN** a user's time zone is America/Chicago
    - **THEN** their digest is sent at 07:00 Chicago time
    """,
    f"""
    ## Context
    The digest job runs once a day at midnight UTC.

    ## Decisions
    - The job runs hourly and sends to the users whose local time is 07:00 in that hour.
    - Sending the digest through a hosted newsletter service was turned down: the providers reviewed all require uploading every recipient list, which the 2026-04 data-protection review refused ({ISSUES}/41).

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Store each user's time zone
    - [ ] 1.2 Run the digest job hourly and select users by local hour
    """,
)

# 5. A Rationale entry that names no requirement title exactly.
CASES["rationale-title-mismatch"] = change(
    "concurrent-session-limit", "Concurrent session limit",
    "Shared accounts are spreading: some accounts have dozens of live sessions.",
    "- `session-store`: a user has at most five active sessions.",
    "session-store", """
    ## ADDED Requirements
    ### Requirement: Concurrent session limit
    A user SHALL have at most five active sessions; creating a sixth SHALL end the oldest.

    #### Scenario: Sixth sign-in
    - **WHEN** a user with five active sessions signs in again
    - **THEN** the new session is created and their oldest session ends
    """,
    """
    ## Context
    Sessions are already keyed by id in Redis.

    ## Decisions
    - Each user gets a sorted set of session ids by creation time, so the oldest is found without a scan.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Keep a per-user sorted set of session ids
    - [ ] 1.2 End the oldest session on the sixth sign-in
    """,
)
CASES["rationale-title-mismatch"]["openspec/specs/session-store/decisions.md"] = BASE[
    "openspec/specs/session-store/decisions.md"] + d(f"""
    - **Rationale: Limit on concurrent sessions.**
      Without a cap, one paid account is shared by a whole team, which the 2026-05 audit found on 4% of accounts.
      Evidence: the 2026-05 account audit, {ISSUES}/60
    """)

# 6. A clean change: nothing should be flagged.
CASES["clean"] = change(
    "audit-export", "Audit export",
    "Administrators answer deletion disputes by asking support for a database query; they should be able to get the entries themselves.",
    "- `audit-log`: an administrator downloads the audit entries as CSV.",
    "audit-log", """
    ## ADDED Requirements
    ### Requirement: Audit export
    An administrator SHALL be able to download, as one CSV file, every audit entry the service still keeps, with one row per entry holding the actor's user id, the note id and the time. The service SHALL refuse the export to any user without the admin role.

    #### Scenario: Administrator downloads entries
    - **WHEN** an administrator requests the audit export
    - **THEN** they receive a CSV file with one row per audit entry, holding the actor's user id, the note id and the time

    #### Scenario: Non-administrator is refused
    - **WHEN** a user without the admin role requests the audit export
    - **THEN** the request is refused and no file is returned
    """,
    """
    ## Context
    Audit entries are in one Postgres table.

    ## Decisions
    - The export streams rows from the table as it writes the CSV, so a large export never sits in memory.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Add the export endpoint, restricted to the admin role
    - [ ] 1.2 Stream rows into the CSV response
    """,
)

# 7. The Constraint entry in audit-log's record restates the base 90-day
#    retention requirement (item 16 of consistency-read.md's checklist).
CASES["record-restates-requirement"] = change(
    "deletion-reason", "Deletion reason",
    "Administrators answering a dispute cannot tell why a note was deleted.",
    "- `audit-log`: a deletion's audit entry holds the reason the user gave, if any.",
    "audit-log", """
    ## ADDED Requirements
    ### Requirement: Deletion reason in the audit entry
    A deletion's audit entry SHALL hold the reason the user typed when deleting, or the word `none` when they typed nothing.

    #### Scenario: Reason given
    - **WHEN** a user deletes a note and types "duplicate"
    - **THEN** the audit entry's reason is "duplicate"

    #### Scenario: No reason given
    - **WHEN** a user deletes a note without typing a reason
    - **THEN** the audit entry's reason is `none`
    """,
    """
    ## Context
    The delete dialog has no reason field today.

    ## Decisions
    - The reason field is optional, so deleting stays one click for users who skip it.

    ## Open Questions
    - None.
    """,
    """
    ## 1. Implementation
    - [ ] 1.1 Add an optional reason field to the delete dialog
    - [ ] 1.2 Write the reason into the audit entry
    """,
)
CASES["record-restates-requirement"]["openspec/specs/audit-log/decisions.md"] = d(f"""
    # audit-log: constraints, rejected alternatives and rationale

    ## Constraints
    - **Constraint: Audit entries are kept for 90 days and then deleted.**
      Because: support needs the entries for disputes, and keeping them longer holds personal data without need.
      Evidence: support ticket ages measured over 2025, {ISSUES}/18
      Holds while: disputes keep reaching support within 60 days.
      Paths: src/audit/log.py

    ## Rationale
    - **Rationale: Audit retention.**
      Disputes about a deletion reach support within 60 days in practice, so 90 days covers them with margin.
      Evidence: support ticket ages measured over 2025, {ISSUES}/18
    """)


GIT_ENV = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@example.com",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@example.com",
           "GIT_AUTHOR_DATE": "2026-11-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-11-01T00:00:00Z"}


def git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], check=True,
                   capture_output=True, env={**os.environ, **GIT_ENV})


def write(repo: pathlib.Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def build(out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, files in CASES.items():
        repo = out / name
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        write(repo, BASE)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Base specs")
        write(repo, files)
        git(repo, "add", "-A")
        (repo / ".git" / "info" / "exclude").write_text(".claude/\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -I build_cases.py <out-dir>")
    build(pathlib.Path(sys.argv[1]))
