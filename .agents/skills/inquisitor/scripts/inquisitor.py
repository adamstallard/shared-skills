#!/usr/bin/env python3
"""The inquisitor skill's script: a thin command line over its modules.

Each command parses its flags here and calls one function in a sibling
module, which does the work. Inputs that may hold a question's text come in
private files or on standard input, never as arguments (inquisitor spec:
*The two calls' files and records stay private*).

Owned by P0. Standard library only.
"""

import argparse
import sys
from pathlib import Path

# `python3 -I` leaves the script's own directory off sys.path, so put it
# back for the sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import branch_search  # noqa: E402
import calls  # noqa: E402
import cite  # noqa: E402
import hooks  # noqa: E402
import install_mod  # noqa: E402
import log_command  # noqa: E402
import lore  # noqa: E402
import search  # noqa: E402
import tagging  # noqa: E402
from common import EXIT_NOT_BUILT, EXIT_REFUSED, NotBuilt, Refused  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inquisitor.py", description="The inquisitor skill's script.")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("vet", help="the first call (--questions or --post) or the second "
                       "call (--pass and --verdicts)")
    v.add_argument("--questions", metavar="FILE", help="a QuestionsInput JSON file, or - "
                   "for standard input")
    v.add_argument("--post", metavar="FILE", help="a post's body, as markdown")
    v.add_argument("--repository", metavar="OWNER/REPO", help="what --post's questions concern")
    v.add_argument("--lore", metavar="OWNER/REPO", help="the team's lore repository, for a "
                   "post's collective questions")
    v.add_argument("--pass", dest="pass_token", metavar="TOKEN", help="the first call's token")
    v.add_argument("--verdicts", metavar="FILE", help="a VerdictsInput JSON file, or -")

    t = sub.add_parser("tag", help="whom a posted question tags")
    t.add_argument("--hash", required=True, help="the vetted question's hash")
    t.add_argument("--posting-as", metavar="LOGIN", help="the login the post goes out as")

    lg = sub.add_parser("log", help="write and push one log or miss file")
    lg.add_argument("--input", required=True, metavar="FILE", help="a private LogInput file")
    lg.add_argument("--service", action="store_true", help="the answer service's option")
    lg.add_argument("--asked-from", metavar="OWNER/REPO", help="asked_from, with --service")
    lg.add_argument("--hash-only", action="store_true", help="a hash-only miss file, with "
                    "--service")
    lg.add_argument("--confirm-visible", action="store_true", help="the person confirmed "
                    "sending the record somewhere more visible")

    m = sub.add_parser("misses", help="list misses by filter, for a review")
    m.add_argument("--repository", metavar="OWNER/REPO")
    m.add_argument("--lore", metavar="OWNER/REPO")
    m.add_argument("--filter", choices=["1", "2", "3", "4"])

    c = sub.add_parser("cite", help="push a citation file for a cited lore entry")
    c.add_argument("--lore", required=True, metavar="OWNER/REPO")
    c.add_argument("--entry", required=True, metavar="ID")
    c.add_argument("--service", action="store_true", help="the answer service's option")

    lo = sub.add_parser("lore", help="open a lore pull request")
    lo.add_argument("--input", required=True, metavar="FILE", help="a private LoreInput file")
    lo.add_argument("--confirm-visible", action="store_true", help="the person confirmed the "
                    "entry for a more visible lore repository")

    s = sub.add_parser("search", help="filter 1 alone, as JSON, for the answer service")
    s.add_argument("--input", required=True, metavar="FILE", help="a SearchInput file, or -")

    b = sub.add_parser("branch-search", help="search one questions branch; the question "
                       "comes on standard input")
    b.add_argument("--repository", required=True, metavar="OWNER/REPO")
    b.add_argument("--item", metavar="OWNER/REPO", help="a run's item's repository")
    b.add_argument("--linear", action="store_true", help="the item is a Linear issue")

    mc = sub.add_parser("miss-check", help="whether a miss file backs an Inquisitor reply")
    mc.add_argument("--repository", required=True, metavar="OWNER/REPO")
    mc.add_argument("--surface", required=True, choices=["github", "linear", "discord"])
    mc.add_argument("--id", required=True, help="the reply's id (a GitHub reply's node_id)")

    fa = sub.add_parser("file-answer", help="one questions-branch file's answer")
    fa.add_argument("--repository", required=True, metavar="OWNER/REPO")
    fa.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    fa.add_argument("--suffix", required=True, metavar="HEX6")

    sub.add_parser("install-mod", help="link the answer mod and the answer launcher")
    sub.add_parser("uninstall-mod", help="remove those links")
    sub.add_parser("service", help="one answer-mod command: JSON in on stdin, JSON out")
    sub.add_parser("hook-ask", help="the picker hook (scripts/check-ask.sh)")
    sub.add_parser("hook-post", help="the post hook (scripts/check-post.sh)")
    return p


def dispatch(a: argparse.Namespace) -> int:
    command: str = a.command
    if command == "vet":
        return calls.run(calls.VetArgs(questions=a.questions, post=a.post,
                                       repository=a.repository, lore=a.lore,
                                       pass_token=a.pass_token, verdicts=a.verdicts))
    if command == "tag":
        return tagging.run(tagging.TagArgs(hash=a.hash, posting_as=a.posting_as))
    if command == "log":
        return log_command.run(log_command.LogArgs(
            input=a.input, service=a.service, asked_from=a.asked_from,
            hash_only=a.hash_only, confirm_visible=a.confirm_visible))
    if command == "misses":
        return log_command.run_misses(log_command.MissesArgs(
            repository=a.repository, lore=a.lore, filter=a.filter))
    if command == "cite":
        return cite.run(cite.CiteArgs(lore=a.lore, entry=a.entry, service=a.service))
    if command == "lore":
        return lore.run(lore.LoreArgs(input=a.input, confirm_visible=a.confirm_visible))
    if command == "search":
        return search.run(search.SearchArgs(input=a.input))
    if command == "branch-search":
        return branch_search.run_branch_search(branch_search.BranchSearchArgs(
            repository=a.repository, item=a.item, linear=a.linear))
    if command == "miss-check":
        return branch_search.run_miss_check(branch_search.MissCheckArgs(
            repository=a.repository, surface=a.surface, id=a.id))
    if command == "file-answer":
        return branch_search.run_file_answer(branch_search.FileAnswerArgs(
            repository=a.repository, date=a.date, suffix=a.suffix))
    if command == "install-mod":
        return install_mod.install()
    if command == "uninstall-mod":
        return install_mod.uninstall()
    if command == "service":
        from service import core
        return core.main()
    if command == "hook-ask":
        return hooks.run_ask(sys.stdin.read())
    return hooks.run_post(sys.stdin.read())


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return dispatch(a)
    except NotBuilt as e:
        sys.stderr.write(f"inquisitor: {e}\n")
        return EXIT_NOT_BUILT
    except Refused as e:
        sys.stderr.write(f"inquisitor: {e}\n")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
