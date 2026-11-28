"""Tests for branch_search: labelling a questions branch's files, and the
branch-search, miss-check and file-answer commands, whose JSON is compared
field for field with the igor contract's stored copies in fixtures/json/."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import branch_search
import branches
import github
from branch_search import Checks, label_branch, question_terms, rank
from common import Refused
from contracts import BranchHit
from formats import (Answer, CitationFile, HandledFile, HashOnlyMiss, LogFile, MissFile,
                     QuestionsBranchFile, miss_hash, render)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SHA = "a" * 40


@dataclass(frozen=True)
class BF(branches.BranchFile):
    """A branch file that can say a later commit changed it."""

    changed: bool = False


_counter = [0]


def bf(file: QuestionsBranchFile, changed: bool = False, content: str | None = None,
       path: str | None = None) -> BF:
    _counter[0] += 1
    if path is None:
        if isinstance(file, (LogFile, HandledFile)):
            path = "questions/" + file.name
        elif isinstance(file, (MissFile, HashOnlyMiss)):
            path = f"misses/{file.hash}.md"
        else:
            path = "citations/" + file.name
    return BF(path=path, content=render(file) if content is None else content,
              added_by=f"{_counter[0]:040x}", changed=changed)


def name(n: int, slug: str = "should-retries-back-off") -> str:
    return f"2026-10-{n:02d}-{slug}-{n:06x}.md"


def question_file(n: int, text: str = "Should retries back off?", repository: str | None = "o/api",
                  asked_from: str = "o/api", asked_in: str | None = None) -> LogFile:
    return LogFile(name=name(n), asked=f"2026-10-{n:02d}", question=text, repository=repository,
                   asked_from=asked_from, asked_in=asked_in)


def answer_file(n: int, by: str = "alice", authority: str = "decision", text: str = "Yes.",
                question: str = "Should retries back off?", answers: tuple[str, ...] = (),
                repository: str | None = "o/api", asked_from: str = "o/api",
                recorded_in: str | None = None) -> LogFile:
    return LogFile(name=name(n), asked=f"2026-10-{n:02d}", question=question, repository=repository,
                   asked_from=asked_from,
                   answer=Answer(answered_by=by, authority="decision" if authority == "decision" else "input",
                                 recorded_in=recorded_in or f"questions/{name(n)}", text=text,
                                 answers=answers))


class Fake:
    """github's write access and visibility, from tables, recording each
    call. A repository missing from a table reads as unknown."""

    def __init__(self, writers: dict[str, set[str]] | None = None,
                 visibility: dict[str, github.Visibility] | None = None) -> None:
        self.writers = writers if writers is not None else {"o/api": {"alice", "bob"}, "o/lore": {"alice"}}
        self.vis: dict[str, github.Visibility] = visibility or {}
        self.calls: list[tuple[str, str]] = []

    def write_access(self, repository: str, login: str) -> bool | None:
        self.calls.append((repository, login))
        if repository not in self.writers:
            return None
        return login in self.writers[repository]

    def visibility(self, repository: str) -> github.Visibility | None:
        self.calls.append((repository, "visibility"))
        return self.vis.get(repository)


class Base(unittest.TestCase):
    fake: Fake

    def setUp(self) -> None:
        self.fake = Fake()
        for target, attr in ((github, "write_access"), (github, "visibility")):
            p = mock.patch.object(target, attr, getattr(self.fake, attr))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(github, "more_visible", more_visible)
        p.start()
        self.addCleanup(p.stop)

    def labels(self, files: list[BF], branch: str = "o/api", lore: bool = False,
               **kw: Any) -> dict[str, BranchHit]:
        return {h.hit["path"]: h.hit for h in label_branch(list(files), branch, lore, Checks(), **kw)}


_RANK = {"private": 0, "internal": 1, "public": 2}


def more_visible(a: github.Visibility | None, b: github.Visibility | None) -> bool:
    return _RANK[a or "public"] > _RANK[b or "private"]


class Labels(Base):
    def test_decision_taken_at_its_word(self) -> None:
        # @scenario inquisitor: A questions-branch decision is taken at its word
        f = bf(answer_file(1))
        self.assertEqual(self.labels([f])[f.path]["label"], "decision")

    def test_changed_decision_is_unconfirmed(self) -> None:
        # @scenario inquisitor: A questions-branch decision changed after it was added is input
        f = bf(answer_file(1), changed=True)
        hit = self.labels([f])[f.path]
        self.assertEqual((hit["label"], hit.get("reason")), ("input", "unconfirmed"))

    def test_no_write_access_is_unconfirmed(self) -> None:
        # @scenario inquisitor: A decision whose author lost write access is input
        # @scenario inquisitor: A permission that cannot be read is no write access
        lost = bf(answer_file(1, by="carol"))
        unknown = bf(answer_file(2, repository="o/web", asked_from="o/web"))
        bot = bf(answer_file(3, by="relay[bot]"))
        hits = self.labels([lost, unknown, bot])
        for f in (lost, unknown, bot):
            self.assertEqual(hits[f.path].get("reason"), "unconfirmed")
        self.assertNotIn(("o/api", "relay[bot]"), self.fake.calls)

    def test_write_access_is_to_the_repository_key(self) -> None:
        # @scenario inquisitor: A file about a repository other than the one it was asked from needs write access to it
        self.fake.writers = {"o/api": set(), "o/lore": {"alice"}}
        f = bf(answer_file(1, asked_from="o/web"))
        self.assertEqual(self.labels([f], branch="o/lore", lore=True)[f.path].get("reason"), "unconfirmed")
        self.assertIn(("o/api", "alice"), self.fake.calls)

    def test_organization_file_needs_lore_write_access(self) -> None:
        # @scenario inquisitor: A questions-branch file about an organization needs write access to the lore repository
        f = bf(answer_file(1, repository=None, asked_from="o/api"))
        self.assertEqual(self.labels([f], branch="o/lore", lore=True)[f.path]["label"], "decision")
        self.assertEqual(self.fake.calls, [("o/lore", "alice")])

    def test_newest_answer_counts(self) -> None:
        # @scenario inquisitor: The newest answer to a question counts
        # @scenario inquisitor: A commit's date does not make a file newer
        # Newness comes from the files' order on the branch, the order of the
        # commits that added them, so no commit date enters the result.
        old, new = bf(answer_file(1)), bf(answer_file(2, by="bob", text="No."))
        hits = self.labels([old, new])
        self.assertEqual(hits[new.path]["label"], "decision")
        self.assertEqual(hits[old.path].get("reason"), "superseded")

    def test_later_input_supersedes_nothing(self) -> None:
        # @scenario inquisitor: A later input file supersedes no answer
        # @scenario inquisitor: An input entry is labelled, and a citation is not shown
        decision = bf(answer_file(1))
        later = bf(answer_file(2, authority="input"))
        cite = bf(CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff", date="2026-10-20"))
        hits = self.labels([decision, later, cite])
        self.assertEqual(hits[decision.path]["label"], "decision")
        self.assertEqual(hits[later.path].get("reason"), "input")
        self.assertNotIn(cite.path, hits)

    def test_unanswered_miss_handled_and_hash_only(self) -> None:
        # @scenario inquisitor: An unanswered log file and a miss file are labelled
        # @scenario inquisitor: A handled file never stops a question
        # @scenario inquisitor: A hash-only miss file holds nothing
        q = bf(question_file(1))
        miss = bf(MissFile(hash=miss_hash("file", q.path), asked="2026-10-20", filter="1",
                           said="Already decided.", question="Should retries back off?",
                           said_by="alice", repository="o/api", asked_from="o/api"))
        handled = bf(HandledFile(name=name(3, "handled"), handled="2026-10-23", closes=name(1)))
        hash_only = bf(HashOnlyMiss(hash=miss_hash("github", "X")))
        hits = self.labels([q, miss, handled, hash_only])
        self.assertEqual(hits[q.path].get("reason"), "unanswered")
        self.assertEqual((hits[miss.path].get("reason"), hits[miss.path].get("filter"),
                          hits[miss.path].get("said")), ("miss", "1", "Already decided."))
        self.assertEqual(set(hits), {q.path, miss.path})

    def test_unreadable_files(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        # @scenario inquisitor: A miss file not named by a hash is only unreadable input
        # @scenario inquisitor: A questions-branch file needs asked_from but not repository
        # @scenario inquisitor: A malformed repository key is never sent to GitHub
        bad_body = bf(answer_file(1), content=render(answer_file(1)).replace("## Answer\n", ""))
        bad_name = bf(question_file(2), path="misses/see-o-api-issue-4.md")
        no_repo = bf(question_file(3, repository=None))
        bad_key = bf(answer_file(4), content=render(answer_file(4)).replace('"o/api"', '"o/../../user"'))
        hits = self.labels([bad_body, bad_name, no_repo, bad_key])
        for f in (bad_body, bad_name, no_repo, bad_key):
            self.assertEqual((hits[f.path]["label"], hits[f.path].get("reason")), ("input", "unreadable"))
        self.assertEqual(self.fake.calls, [])

    def test_answer_heading_in_question(self) -> None:
        # @scenario inquisitor: An "## Answer" line in a question's text does not answer it
        f = bf(question_file(1, text="Should retries back off?\n## Answer\nYes."))
        self.assertEqual(self.labels([f])[f.path].get("reason"), "unanswered")


class Offline(Base):
    def test_offline_asks_github_nothing(self) -> None:
        # @scenario inquisitor: The search command takes a question with a category only on standard input
        # filter1 labels with Checks(offline=True) for a question with a
        # category, which must then reach nothing off the machine.
        f = bf(answer_file(1, recorded_in=f"openspec/changes/retry/design.md@{SHA}"))
        with mock.patch.object(branch_search, "gh_json", return_value=[{"merged_at": "x"}]):
            hits = {h.hit["path"]: h.hit for h in label_branch([f], "o/api", False, Checks(offline=True))}
        self.assertEqual((hits[f.path].get("reason"), hits[f.path]["landed"]), ("unconfirmed", False))
        self.assertEqual(self.fake.calls, [])


class Matching(Base):
    def test_scaffolding_matches_nothing(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # The search shows a file whose question's text matches; the format's
        # own words, and the lines a question's text leaves out, are no match.
        logo = bf(question_file(1, text="Which colour is the logo?"), path="questions/logo.md")
        tagged = bf(question_file(2, text="Which colour is the logo?\nConcerns: o/api\n@alice"))
        for question in ("Which repository should the api question go to?", "Does alice own the api?"):
            ranked = rank(label_branch([logo, tagged], "o/api", False, Checks()), question_terms(question))
            self.assertEqual(ranked, [])

    def test_crlf_scaffolding_matches_nothing(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        # A file with CRLF line ends or a BOM is unreadable; its frontmatter
        # must still match nothing.
        f = answer_file(1, question="What cache TTL do we use?", text="An hour.")
        crlf = bf(f, content="\ufeff" + render(f).replace("\n", "\r\n"))
        ranked = rank(label_branch([crlf], "o/api", False, Checks()),
                      question_terms("Which repository records the decision authority?"))
        self.assertEqual(ranked, [])


class Named(Base):
    def test_untagged_named_file_answered_by_writer(self) -> None:
        # @scenario inquisitor: An untagged file's answer from an account with write access counts
        q = bf(question_file(1, repository=None))
        a = bf(answer_file(2, repository=None, answers=(name(1),)))
        hits = self.labels([q, a], branch="o/lore", lore=True)
        self.assertEqual((hits[q.path]["answer"], hits[q.path]["label"]), ("Yes.", "decision"))
        self.fake.writers = {"o/api": set(), "o/lore": {"alice"}}
        q2, a2 = bf(question_file(3)), bf(answer_file(4, answers=(name(3),)))
        hits = self.labels([q2, a2], branch="o/lore", lore=True)
        self.assertIsNone(hits[q2.path]["answer"])

    def test_input_answer_leaves_file_unanswered(self) -> None:
        # @scenario inquisitor: A log file named only by an input answer file is unanswered
        q, a = bf(question_file(1)), bf(answer_file(2, authority="input", answers=(name(1),)))
        self.assertEqual(self.labels([q, a])[q.path].get("reason"), "unanswered")

    def test_answer_names_only_its_file(self) -> None:
        # @scenario inquisitor: An answer naming one file does not answer another with the same question
        q1, q2 = bf(question_file(1)), bf(question_file(2))
        a = bf(answer_file(3, answers=(name(1),)))
        hits = self.labels([q1, q2, a])
        self.assertEqual(hits[q1.path]["answer"], "Yes.")
        self.assertIsNone(hits[q2.path]["answer"])

    def test_newest_answer_naming_a_file(self) -> None:
        # @scenario inquisitor: The newest answer naming a file counts
        older = bf(answer_file(1, question="Back off?", text="Old."))
        q = bf(question_file(2))
        first = bf(answer_file(3, question="Back off?", text="First.", answers=(name(2),)))
        second = bf(answer_file(4, by="bob", question="Should we back off?", text="Second.",
                                answers=(name(2),)))
        hits = self.labels([older, q, first, second])
        self.assertEqual(hits[q.path]["answer"], "Second.")
        self.assertEqual(hits[first.path].get("reason"), "superseded")
        self.assertEqual(hits[second.path]["label"], "decision")
        self.assertEqual(hits[older.path].get("reason"), "superseded")

    def test_file_answer_takes_the_tagged_person(self) -> None:
        # @scenario inquisitor: The file answer prints the named file's answer and nothing else
        q = bf(question_file(1, text="Should retries back off?\n@alice"))
        a1 = bf(answer_file(2, text="Alice says yes.", answers=(name(1),)))
        a2 = bf(answer_file(3, by="bob", text="Bob says no.", answers=(name(1),)))
        out = run_command(branch_search.run_file_answer,
                          branch_search.FileAnswerArgs("o/api", "2026-10-01", "000001"), [q, a1, a2])
        self.assertEqual(out, {"version": 1, "answer": "Alice says yes."})
        none = run_command(branch_search.run_file_answer,
                           branch_search.FileAnswerArgs("o/api", "2026-10-01", "000001"), [q])
        self.assertEqual(none, json.loads((FIXTURES / "json/file-answer-none.json").read_text()))
        with self.assertRaises(Refused):
            run_command(branch_search.run_file_answer,
                        branch_search.FileAnswerArgs("o/api", "2026-10-09", "000009"), [q])


class Run(Base):
    def test_other_repository_is_input_in_a_run(self) -> None:
        # @scenario inquisitor: A file about another repository is input during a run
        # @scenario inquisitor: Given a run's item, the branch search applies the run's rules
        self.fake.vis = {"o/lore": "public", "o/web": "public", "o/doc": "public", "o/api": "private"}
        self.fake.writers = {"o/doc": {"alice"}, "o/api": {"alice"}, "o/lore": {"alice"}}
        doc = bf(answer_file(1, repository="o/doc", asked_from="o/doc"))
        private = bf(answer_file(2, question="Other?"))
        org = bf(answer_file(3, question="Org?", repository=None, asked_from="o/web"))
        hits = self.labels([doc, private, org], branch="o/lore", lore=True, item="o/web")
        self.assertEqual(hits[doc.path].get("reason"), "unconfirmed")
        self.assertNotIn(private.path, hits)
        self.assertEqual(hits[org.path]["label"], "decision")
        hits = self.labels([doc, private], branch="o/lore", lore=True, item="o/web", item_private=True)
        self.assertEqual(hits[private.path].get("reason"), "unconfirmed")

    def test_hidden_answer_file_leaks_through_no_named_file(self) -> None:
        # @scenario inquisitor: Given a run's item, the branch search applies the run's rules
        self.fake.vis = {"o/lore": "public", "o/web": "public", "o/priv": "private"}
        self.fake.writers = {"o/lore": {"alice"}}
        q = bf(question_file(1, repository=None, asked_from="o/web"))
        a = bf(answer_file(2, repository=None, asked_from="o/priv", text="SECRET private detail",
                           answers=(name(1),)))
        hits = self.labels([q, a], branch="o/lore", lore=True, item="o/web")
        self.assertNotIn(a.path, hits)
        self.assertNotIn("SECRET", json.dumps(hits))

    def test_asked_from_private_file_is_private(self) -> None:
        # @scenario inquisitor: A file asked from a private repository is private
        # @scenario inquisitor: A well-formed asked_from whose visibility can't be read is private
        self.fake.vis = {"o/web": "public", "o/api": "private"}
        asked = bf(question_file(1, repository="o/web", asked_from="o/api"))
        unknown = bf(question_file(2, repository="o/web", asked_from="o/zzz"))
        linked = bf(question_file(3, repository="o/web", asked_from="o/web",
                                  asked_in="https://github.com/o/api/pull/1#issuecomment-2"))
        public = bf(question_file(4, repository="o/web", asked_from="o/web"))
        hits = self.labels([asked, unknown, linked, public], branch="o/web", item="o/web")
        self.assertEqual(set(hits), {public.path})


class Visibility(Base):
    def test_most_private_repository_decides(self) -> None:
        # @scenario inquisitor: A file asked from a private repository is private
        self.fake.vis = {"o/lore": "public", "o/web": "public", "o/api": "private"}
        private = bf(question_file(1, repository="o/api", asked_from="o/web"))
        public = bf(question_file(2, repository="o/web", asked_from="o/web"))
        hits = self.labels([private, public], branch="o/lore", lore=True, item="o/web")
        self.assertEqual(set(hits), {public.path})

    def test_one_unreadable_visibility_makes_it_private(self) -> None:
        # @scenario inquisitor: A well-formed asked_from whose visibility can't be read is private
        self.fake.vis = {"o/web": "public"}
        unknown = bf(question_file(1, repository="o/web", asked_from="o/zzz"))
        hits = self.labels([unknown], branch="o/web", item="o/web")
        self.assertEqual(hits, {})


class Landed(Base):
    def test_landed_values(self) -> None:
        # @scenario inquisitor: An answer whose commit reached the default branch counts for everyone
        # @scenario inquisitor: An answer recorded only in its log file counts for everyone
        # @scenario inquisitor: An answer whose pull request was squash-merged counts for everyone
        # @scenario inquisitor: The JSON's reasons and landed values are a closed list
        pinned = bf(answer_file(1, recorded_in=f"openspec/changes/retry/design.md@{SHA}"))
        own = bf(answer_file(2, question="Own?"))

        def gh(args: list[str]) -> Any:
            joined = " ".join(args)
            if joined.endswith("/pulls"):
                return [{"merged_at": "2026-10-01T00:00:00Z"}]
            if "/contents/" in joined:
                return {"path": "openspec/changes/retry/design.md"}
            return None

        with mock.patch.object(branch_search, "gh_json", side_effect=gh):
            hits = self.labels([pinned, own])
        self.assertIs(hits[pinned.path]["landed"], True)
        self.assertIsNone(hits[own.path]["landed"])
        with mock.patch.object(branch_search, "gh_json", return_value=None):
            self.assertIs(self.labels([pinned])[pinned.path]["landed"], False)
        compare = {"repos/o/api": {"default_branch": "main"},
                   f"repos/o/api/compare/{SHA}...main": {"status": "identical"}}

        def compared(args: list[str]) -> Any:
            return compare.get(args[1])

        with mock.patch.object(branch_search, "gh_json", side_effect=compared):
            self.assertIs(self.labels([pinned])[pinned.path]["landed"], True)
        for pulls, contents in (([{"merged_at": "x"}], None), ([{"merged_at": None}], {"path": "p"})):
            def partial(args: list[str], pulls: Any = pulls, contents: Any = contents) -> Any:
                joined = " ".join(args)
                return pulls if joined.endswith("/pulls") else contents if "/contents/" in joined else None
            with mock.patch.object(branch_search, "gh_json", side_effect=partial):
                self.assertIs(self.labels([pinned])[pinned.path]["landed"], False)
        for hit in hits.values():
            self.assertIn(hit.get("reason", "input"),
                          ("unconfirmed", "unanswered", "miss", "superseded", "unreadable", "input"))


def run_command(fn: Any, args: Any, files: list[BF] | None, stdin: str = "") -> Any:
    """Run a command with the branch's files, returning its parsed JSON."""
    home = tempfile.mkdtemp()
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"HOME": home, "XDG_STATE_HOME": home}), \
            mock.patch.object(branches, "list_files", return_value=files), \
            mock.patch.object(branch_search, "is_lore_repository", return_value=False), \
            mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out):
        code = fn(args)
    assert code == 0
    return json.loads(out.getvalue())


class Commands(Base):
    def test_branch_search_matches_the_contract(self) -> None:
        # @scenario inquisitor: The branch search prints each hit with the script's labels
        decision = (FIXTURES / "formats/questions/2026-10-21-should-retries-back-off-a1b2c3.md.golden").read_text()
        miss_path = "misses/def2e704bb5350dd1b2c258cbc70d8b9857ecac5481f35c03c4a5bd8497fb1d6.md"
        miss = (FIXTURES / "formats" / (miss_path + ".golden")).read_text()
        unconfirmed = render(LogFile(
            name="2026-10-24-should-retries-back-off-cc11dd.md", asked="2026-10-24",
            question="Should retries back off?", repository="o/api", asked_from="o/api",
            answer=Answer(answered_by="carol", authority="decision",
                          recorded_in="questions/2026-10-24-should-retries-back-off-cc11dd.md", text="No.")))
        files = [BF("questions/2026-10-21-should-retries-back-off-a1b2c3.md", decision, "1" * 40),
                 BF("questions/2026-10-24-should-retries-back-off-cc11dd.md", unconfirmed, "2" * 40),
                 BF(miss_path, miss, "3" * 40),
                 BF("questions/2026-10-25-unrelated-cafe01.md",
                    render(question_file(25, text="Which colour is the logo?")), "4" * 40)]
        out = run_command(branch_search.run_branch_search, branch_search.BranchSearchArgs("o/api"),
                          files, stdin="Should retries back off?")
        self.assertEqual(out, json.loads((FIXTURES / "json/branch-search.json").read_text()))

    def test_unfetchable_branch_prints_nothing(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        for fn, args in ((branch_search.run_branch_search, branch_search.BranchSearchArgs("o/api")),
                         (branch_search.run_miss_check, branch_search.MissCheckArgs("o/api", "github", "X")),
                         (branch_search.run_file_answer,
                          branch_search.FileAnswerArgs("o/api", "2026-10-01", "000001"))):
            out = io.StringIO()
            with redirect_stdout(out), self.assertRaises(Refused):
                run_command(fn, args, None)
            self.assertEqual(out.getvalue(), "")
        with mock.patch.object(branches, "list_files", return_value=[]) as listed:
            self.assertIsNone(branch_search.read_branch("o/../x"))
            self.assertEqual(branch_search.read_branch("o/api"), [])
        listed.assert_called_once_with("o/api")

    def test_miss_check(self) -> None:
        # @scenario inquisitor: The miss check says only whether the reply is backed
        hash_only = bf(HashOnlyMiss(hash=miss_hash("linear", "c1")))
        said = bf(MissFile(hash=miss_hash("github", "N1"), asked="2026-10-20", filter="4", said="Decide.",
                           question="Q?", said_by="alice", repository="o/api", asked_from="o/api"))
        unsaid = bf(MissFile(hash=miss_hash("github", "N2"), asked="2026-10-20", filter="4",
                             said="Decide.", question="Q?", repository="o/api", asked_from="o/api"))
        files = [hash_only, said, unsaid]
        backed = json.loads((FIXTURES / "json/miss-check-backed.json").read_text())
        unbacked = json.loads((FIXTURES / "json/miss-check-unbacked.json").read_text())
        for surface, id_, want in (("linear", "c1", backed), ("github", "N1", backed),
                                   ("github", "N2", unbacked), ("discord", "c1", unbacked)):
            out = run_command(branch_search.run_miss_check,
                              branch_search.MissCheckArgs("o/api", surface, id_), list(files))  # type: ignore[arg-type]
            self.assertEqual(out, want)
        self.assertEqual(self.fake.calls, [])

    def test_ranking(self) -> None:
        # @scenario inquisitor: An answer matching fewer terms is still shown
        inputs = [bf(answer_file(n, authority="input", question="Retries back off quickly?"))
                  for n in range(1, 4)]
        decision = bf(answer_file(9, question="Retries?"))
        ranked = rank(label_branch([*inputs, decision], "o/api", False, Checks()),
                      question_terms("Should retries back off quickly?"))
        self.assertEqual(ranked[0][0].hit["path"], decision.path)
        self.assertEqual([n for _, n in ranked], [1, 4, 4, 4])
        few = bf(answer_file(10, authority="input", question="Retries?"))
        ranked = rank(label_branch([few, *inputs], "o/api", False, Checks()),
                      question_terms("Should retries back off quickly?"))
        self.assertEqual([n for _, n in ranked], [4, 4, 4, 1])


if __name__ == "__main__":
    unittest.main()
