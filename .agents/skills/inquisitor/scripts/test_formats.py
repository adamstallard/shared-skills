"""Tests for formats: questions-branch files' names, key forms, and their
rendering and reading, against the golden files under fixtures/formats/."""

import hashlib
import unittest
from dataclasses import replace
from pathlib import Path

from formats import (Answer, CitationFile, HandledFile, HashOnlyMiss, LogFile, MissFile,
                     QuestionsBranchFile, Unreadable, is_answer_link, is_asked_in, is_login,
                     is_recorded_in, is_repository, log_name, miss_hash, parse, render, slug)

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "formats"

QUESTION = LogFile(
    name="2026-10-20-should-retries-back-off-3f9a1c.md", asked="2026-10-20",
    question="Should retries back off?\nRelated: https://github.com/o/api/pull/3\n"
             "Concerns: o/api\n@alice",
    repository="o/api", asked_from="o/api",
    asked_in="https://github.com/o/api/pull/12#issuecomment-1001")
ANSWER = LogFile(
    name="2026-10-21-should-retries-back-off-a1b2c3.md", asked="2026-10-21",
    question="Should retries back off?", repository="o/api", asked_from="o/api",
    answer=Answer(answered_by="alice", authority="decision",
                  recorded_in="https://github.com/o/api/pull/12#issuecomment-1002",
                  text="Yes.\n\n## Answer: quoted from the question",
                  answer_link="https://github.com/o/api/pull/12#issuecomment-1002",
                  answers=("2026-10-20-should-retries-back-off-3f9a1c.md",)))
REPHRASED = LogFile(
    name="2026-10-22-which-cap-should-retries-use-0d9e8f.md", asked="2026-10-22",
    question="Which cap should retries use?", asked_from="o/web",
    answer=Answer(answered_by="alice", authority="input",
                  recorded_in="questions/2026-10-22-which-cap-should-retries-use-0d9e8f.md",
                  text="User says: cap at a minute.",
                  rephrased="Should every service cap retries at one minute?",
                  discussion="A minute keeps queues short without hiding outages."))
HANDLED = HandledFile(name="2026-10-23-handled-77aa01.md", handled="2026-10-23",
                      closes="2026-10-20-should-retries-back-off-3f9a1c.md")
MISS_HASH = miss_hash("file", "questions/2026-10-20-should-retries-back-off-3f9a1c.md")
MISS = MissFile(hash=MISS_HASH, asked="2026-10-20", filter="1",
                said="Already decided in docs/retries.md.", question="Should retries back off?",
                said_by="alice", asked_by="web-bot[bot]", repository="o/api", asked_from="o/api")
HASH_ONLY = HashOnlyMiss(hash="858c044afd917355bd711ecae268938f6fe9edf51e46887174b80972316bedaa")
CITATION = CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff", date="2026-10-20")


def golden(path: str) -> str:
    return (GOLDEN / (path + ".golden")).read_text(encoding="utf-8")


class Golden(unittest.TestCase):
    def check(self, path: str, file: QuestionsBranchFile, lore_branch: bool = False) -> None:
        content = golden(path)
        self.assertEqual(render(file), content)
        self.assertEqual(parse(path, content, lore_branch), file)

    def test_question_file(self) -> None:
        # @scenario inquisitor: A log file's name and keys
        # @scenario inquisitor: A logged question keeps its tag line
        self.check("questions/" + QUESTION.name, QUESTION)

    def test_answer_file(self) -> None:
        # @scenario inquisitor: An answered log file's keys
        # @scenario inquisitor: A whole comment fits as the answer
        # @scenario inquisitor: An answer file names the questions-branch file it answers
        self.check("questions/" + ANSWER.name, ANSWER)

    def test_rephrased_file(self) -> None:
        # @scenario inquisitor: A rephrased question's log file holds the rephrasing
        self.check("questions/" + REPHRASED.name, REPHRASED, lore_branch=True)
        assert REPHRASED.answer is not None
        spaced = replace(REPHRASED.answer, rephrased="Should every  service\ncap retries at one minute?")
        self.assertEqual(render(replace(REPHRASED, answer=spaced)),
                         golden("questions/" + REPHRASED.name))

    def test_handled_file(self) -> None:
        # @scenario inquisitor: A handled file's keys
        self.check("questions/" + HANDLED.name, HANDLED)

    def test_miss_file(self) -> None:
        # @scenario inquisitor: A miss file's keys
        self.assertTrue(MISS_HASH.startswith("def2e704"))
        self.check(f"misses/{MISS_HASH}.md", MISS)

    def test_hash_only_miss(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        self.check(f"misses/{HASH_ONLY.hash}.md", HASH_ONLY)

    def test_citation(self) -> None:
        # An Igor is one of the igor project's AI teammates; only its run
        # writes `run`.
        # @scenario inquisitor: A citation from a session outside an Igor's run holds no run id
        self.check("citations/" + CITATION.name, CITATION)

    def test_citation_with_run(self) -> None:
        # An Igor is one of the igor project's AI teammates.
        # @scenario inquisitor: A citation an Igor pushes from a run holds the run's id
        cited = CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff", date="2026-10-20",
                             run="r-7f3a")
        text = render(cited)
        self.assertEqual(text, 'entry: "retry-backoff"\ndate: "2026-10-20"\nrun: "r-7f3a"\n')
        self.assertEqual(parse("citations/2026-10-20-3f9a1c", text, True), cited)
        self.assertIsInstance(parse("citations/2026-10-21-3f9a1c", text, True), Unreadable)
        self.assertIsInstance(parse("citations/2026-10-20-3F9A1C", text, True), Unreadable)


class Names(unittest.TestCase):
    def test_slug_and_name(self) -> None:
        # @scenario inquisitor: Where a file goes and how its slug is made
        self.assertEqual(slug("Should retries back off?"), "should-retries-back-off")
        self.assertEqual(slug("Which cap should retries use, given the ones we tried?"),
                         "which-cap-should-retries-use-given-the-o")
        self.assertEqual(slug("a" * 39 + " b"), "a" * 39)
        self.assertLessEqual(len(slug("x" * 100)), 40)
        self.assertEqual(slug("Is a-b—c (ok)?"), "is-a-b-c-ok")
        self.assertEqual(slug("¿Qué?"), "qu")
        self.assertEqual(slug("???"), "question")
        self.assertEqual(log_name("2026-10-20", "should-retries-back-off", "3f9a1c"),
                         "2026-10-20-should-retries-back-off-3f9a1c.md")

    def test_hostile_text(self) -> None:
        # @scenario inquisitor: Hostile text is logged safely
        text = 'See ../etc: "quoted"\\ and\n---\nmore'
        name = log_name("2026-10-20", slug(text), "abcdef")
        for bad in ("../", "---", ":", "/"):
            self.assertNotIn(bad, name)
        miss = MissFile(hash=MISS_HASH, asked="2026-10-20", filter="2", said=text,
                        question=text, asked_from="o/api")
        self.assertEqual(parse(f"misses/{MISS_HASH}.md", render(miss), False), miss)
        log = LogFile(name=name, asked="2026-10-20", question=text, repository="o/api",
                      asked_from="o/api")
        self.assertEqual(parse("questions/" + name, render(log), False), log)

    def test_miss_by_file_path(self) -> None:
        # @scenario inquisitor: A miss with no reply hashes its question's file path
        path = "questions/2026-10-20-should-retries-back-off-3f9a1c.md"
        self.assertEqual(miss_hash("file", path),
                         hashlib.sha256(("file\n" + path).encode()).hexdigest())
        url = "https://linear.app/o/issue/ENG-1#comment-0a1b2c3d"
        self.assertEqual(miss_hash("message", url),
                         hashlib.sha256(("message\n" + url).encode()).hexdigest())

    def test_miss_by_reply_id(self) -> None:
        # @scenario inquisitor: A miss file is named by its reply's id
        self.assertEqual(miss_hash("discord", "1234567890"),
                         hashlib.sha256(b"discord\n1234567890").hexdigest())
        self.assertNotEqual(miss_hash("discord", "1"), miss_hash("linear", "1"))

    def test_handled_closes_plain_name(self) -> None:
        # A category marks a question holding a vulnerability, a secret or
        # personal information; a plain name is the log file's own name.
        # @scenario inquisitor: A file logged before its question got a category is closed by its plain name
        h = HandledFile(name="2026-01-06-handled-000001.md", handled="2026-01-06",
                        closes="2026-01-05-can-the-token-leak-3f9a1c.md")
        self.assertIn('closes: "2026-01-05-can-the-token-leak-3f9a1c.md"', render(h))
        self.assertEqual(parse("questions/" + h.name, render(h), False), h)


class Forms(unittest.TestCase):
    def test_repository_and_answer_link_forms(self) -> None:
        # @scenario inquisitor: The forms a repository key and an answer_link must take
        for ok in ("o/api", "a-b/x.y_z", "o/" + "r" * 100, "o/.github"):
            self.assertTrue(is_repository(ok), ok)
        for bad in ("o/../../user", "o", "o/r/x", "-o/r", "o--x/r", "o/.", "o/..",
                    "o/" + "r" * 101, "o/r s", "a" * 40 + "/r"):
            self.assertFalse(is_repository(bad), bad)
        for ok in ("https://github.com/o/api/pull/12#issuecomment-1002",
                   "https://github.com/o/api/issues/4#issuecomment-9",
                   "https://github.com/o/api/pull/12#pullrequestreview-7",
                   "https://github.com/o/api/pull/12#discussion_r55",
                   "https://discord.com/channels/1/2/3",
                   "https://linear.app/acme/issue/ENG-12#comment-0a1b2c3d"):
            self.assertTrue(is_answer_link(ok), ok)
        for bad in ("https://github.com/o/r/pull/3?x=../", "https://github.com/o/r/pull/3",
                    "https://github.com/o/../pull/3#issuecomment-1",
                    "http://github.com/o/r/pull/3#issuecomment-1",
                    "https://discordapp.com/channels/1/2/3",
                    "https://linear.app/acme/issue/ENG-12/title-slug#comment-0a1b2c3d",
                    "https://linear.app/acme/issue/ENG-12"):
            self.assertFalse(is_answer_link(bad), bad)
        for ok in ("openspec/changes/retry/design.md", "docs/x.md@" + "a" * 40,
                   "https://github.com/o/api/pull/12#issuecomment-1002"):
            self.assertTrue(is_recorded_in(ok), ok)
        for bad in ("/etc/passwd", "a//b", "a/./b", "../x", "a/-b", "docs/x.md@abc\n", ""):
            self.assertFalse(is_recorded_in(bad), bad)
        self.assertTrue(is_login("web-bot"))
        self.assertFalse(is_login("web-bot[bot]"))

    def test_asked_in_forms(self) -> None:
        # @scenario inquisitor: Where an asked_in may be written
        for ok in ("https://github.com/o/api/pull/12#issuecomment-1001",
                   "https://github.com/o/api/issues/12", "https://github.com/o/api/pull/12",
                   "https://discord.com/channels/1/2/3",
                   "https://linear.app/acme/issue/ENG-12#comment-0a1b2c3d",
                   "https://linear.app/acme/issue/ENG-12"):
            self.assertTrue(is_asked_in(ok), ok)
        for bad in ("https://github.com/o/r/pull/3?x=../", "https://linear.app/acme/issue/ENG-12/slug",
                    "https://discord.com/channels/1/2"):
            self.assertFalse(is_asked_in(bad), bad)

    def test_answer_link_relayed_forms(self) -> None:
        # @scenario inquisitor: Where an answer_link may be written
        self.assertTrue(is_answer_link("https://discord.com/channels/10/20/30"))
        self.assertTrue(is_answer_link("https://linear.app/acme/issue/ENG-1#comment-deadbeef"))
        self.assertFalse(is_answer_link("https://discord.com/channels/a/20/30"))


class Reading(unittest.TestCase):
    def test_body_read_from_its_end(self) -> None:
        # @scenario inquisitor: A log file's body is read from its end
        content = golden("questions/" + ANSWER.name).replace("> ## Answer: quoted from the question\n",
                                                             "> ## Answer: quoted from the question\n\n\n")
        self.assertEqual(parse("questions/" + ANSWER.name, content, False), ANSWER)
        odd = golden("questions/" + QUESTION.name).replace(
            "@alice\n", "@alice\n## Answer\n> not an answer\n")
        parsed = parse("questions/" + QUESTION.name, odd, False)
        assert isinstance(parsed, LogFile)
        self.assertTrue(parsed.question.endswith("## Answer\n> not an answer"))

    def test_answer_line_in_question(self) -> None:
        # @scenario inquisitor: An "## Answer" line in a question's text does not answer it
        content = golden("questions/" + QUESTION.name).replace("@alice\n", "@alice\n## Answer\nYes.\n")
        parsed = parse("questions/" + QUESTION.name, content, False)
        assert isinstance(parsed, LogFile)
        self.assertIsNone(parsed.answer)
        self.assertTrue(parsed.question.endswith("## Answer\nYes."))

    def test_unreadable_answer_layout(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        content = golden("questions/" + ANSWER.name).replace("## Answer\n> Yes.", "## Answers\n> Yes.")
        self.assertIsInstance(parse("questions/" + ANSWER.name, content, False), Unreadable)
        no_quotes = golden("questions/" + ANSWER.name).split("## Answer\n")[0]
        self.assertIsInstance(parse("questions/" + ANSWER.name, no_quotes, False), Unreadable)
        for bad in (golden("questions/" + QUESTION.name).replace("\n", "\r\n"),
                    golden("questions/" + QUESTION.name).replace('asked: "2026-10-20"', "asked: 2026-10-20"),
                    golden("questions/" + QUESTION.name).replace("---\n## Question", "said: \"x\"\n---\n## Question")):
            self.assertIsInstance(parse("questions/" + QUESTION.name, bad, False), Unreadable)

    def test_name_with_re_line(self) -> None:
        # @scenario inquisitor: A file name holding a Re line is only unreadable input
        path = "questions/2026-10-20-x-3f9a1c.md\nRe: https://github.com/o/api/issues/9"
        got = parse(path, golden("questions/" + QUESTION.name), False)
        self.assertIsInstance(got, Unreadable)
        for name in ("questions/2026-10-20-x-3f9a1c.md.bak", "questions/2026-13-40-x-3f9a1c.md",
                     "questions/2026-10-20--x-3f9a1c.md", "questions/sub/2026-10-20-x-3f9a1c.md",
                     "other/2026-10-20-x-3f9a1c.md"):
            self.assertIsInstance(parse(name, golden("questions/" + QUESTION.name), False), Unreadable)

    def test_miss_not_named_by_hash(self) -> None:
        # @scenario inquisitor: A miss file not named by a hash is only unreadable input
        content = golden(f"misses/{MISS_HASH}.md")
        self.assertIsInstance(parse("misses/see-o-api-issue-4.md", content, False), Unreadable)
        self.assertIsInstance(parse(f"misses/{MISS_HASH.upper()}.md", content, False), Unreadable)

    def test_malformed_keys_are_unreadable(self) -> None:
        # @scenario inquisitor: A malformed repository key is never sent to GitHub
        base = golden("questions/" + QUESTION.name)
        for old, new in (('repository: "o/api"', 'repository: "o/../../user"'),
                         ('asked_from: "o/api"', 'asked_from: "o/../../user"'),
                         ("#issuecomment-1001", "?x=../")):
            got = parse("questions/" + QUESTION.name, base.replace(old, new), False)
            self.assertIsInstance(got, Unreadable, new)
        answer = golden("questions/" + ANSWER.name).replace(
            'answer_link: "https://github.com/o/api/pull/12#issuecomment-1002"',
            'answer_link: "https://github.com/o/r/pull/3?x=../"')
        self.assertIsInstance(parse("questions/" + ANSWER.name, answer, False), Unreadable)

    def test_asked_from_needed_repository_not(self) -> None:
        # @scenario inquisitor: A questions-branch file needs asked_from but not repository
        base = golden("questions/" + QUESTION.name)
        no_from = base.replace('asked_from: "o/api"\n', "")
        self.assertIsInstance(parse("questions/" + QUESTION.name, no_from, False), Unreadable)
        no_repo = base.replace('repository: "o/api"\n', "")
        self.assertIsInstance(parse("questions/" + QUESTION.name, no_repo, True), LogFile)
        self.assertIsInstance(parse("questions/" + QUESTION.name, no_repo, False), Unreadable)

    def test_handled_file_holds_only_its_keys(self) -> None:
        # @scenario inquisitor: A handled file's keys
        base = golden("questions/" + HANDLED.name)
        self.assertIsInstance(parse("questions/" + HANDLED.name, base + "## Question\nx\n", False),
                              Unreadable)
        self.assertIsInstance(parse("questions/2026-10-23-other-77aa01.md", base, False), Unreadable)
        extra = base.replace("---\n", '---\nasked: "2026-10-23"\n', 1)
        self.assertIsInstance(parse("questions/" + HANDLED.name, extra, False), Unreadable)

    def test_hash_only_reads_no_key(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        self.assertEqual(render(HASH_ONLY), "---\n---\n")
        self.assertIsInstance(parse(f"misses/{HASH_ONLY.hash}.md", "---\n---\n## Question\nx\n", False),
                              Unreadable)


if __name__ == "__main__":
    unittest.main()


class HostileValues(unittest.TestCase):
    def test_escape_out_of_unicode_range_is_unreadable(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        base = golden(f"misses/{MISS_HASH}.md")
        for escape in ("\\U00110000", "\\ud800"):
            bad = base.replace("Already decided in docs/retries.md.", escape)
            self.assertIsInstance(parse(f"misses/{MISS_HASH}.md", bad, False), Unreadable, escape)

    def test_yaml_non_printables_are_escaped(self) -> None:
        # @scenario inquisitor: Hostile text is logged safely
        miss = MissFile(hash=MISS_HASH, asked="2026-10-20", filter="2", said="a￿b￾c",
                        question="q", asked_from="o/api")
        text = render(miss)
        self.assertNotIn("￿", text)
        self.assertNotIn("￾", text)
        self.assertEqual(parse(f"misses/{MISS_HASH}.md", text, False), miss)


class Boundaries(unittest.TestCase):
    def test_forty_character_slug_reads(self) -> None:
        # @scenario inquisitor: Where a file goes and how its slug is made
        name = log_name("2026-10-20", "a" * 40, "abcdef")
        log = LogFile(name=name, asked="2026-10-20", question="q", repository="o/api", asked_from="o/api")
        self.assertEqual(parse("questions/" + name, render(log), False), log)
        longer = log_name("2026-10-20", "a" * 41, "abcdef")
        self.assertIsInstance(parse("questions/" + longer, render(log), False), Unreadable)

    def test_recorded_in_path_may_hold_a_space(self) -> None:
        # This scenario sets recorded_in's forms too.
        # @scenario inquisitor: The forms a repository key and an answer_link must take
        self.assertTrue(is_recorded_in("docs/my file.md"))

    def test_value_ending_in_backslash_is_unreadable(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        base = golden(f"misses/{MISS_HASH}.md")
        bad = base.replace('said: "Already decided in docs/retries.md."', 'said: "abc\\"')
        self.assertIsInstance(parse(f"misses/{MISS_HASH}.md", bad, False), Unreadable)

    def test_duplicate_key_is_unreadable(self) -> None:
        # @scenario inquisitor: A log file that does not read as the format says is unreadable
        base = golden("questions/" + QUESTION.name)
        bad = base.replace('asked: "2026-10-20"\n', 'asked: "2026-10-20"\nasked: "2026-10-21"\n')
        self.assertIsInstance(parse("questions/" + QUESTION.name, bad, False), Unreadable)

    def test_rephrased_answer_with_empty_question(self) -> None:
        # @scenario inquisitor: A rephrased question's log file holds the rephrasing
        log = replace(REPHRASED, question="")
        self.assertEqual(parse("questions/" + log.name, render(log), True), log)

    def test_rephrasing_needs_both_parts(self) -> None:
        # @scenario inquisitor: A rephrased question's log file holds the rephrasing
        assert REPHRASED.answer is not None
        half = replace(REPHRASED, answer=replace(REPHRASED.answer, discussion=None))
        self.assertNotIn("## Rephrased question", render(half))

    def test_empty_citation_values_are_unreadable(self) -> None:
        # @scenario inquisitor: A citation from a session outside an Igor's run holds no run id
        for text in ('entry: ""\ndate: "2026-10-20"\n',
                     'entry: "retry-backoff"\ndate: "2026-10-20"\nrun: ""\n'):
            self.assertIsInstance(parse("citations/2026-10-20-3f9a1c", text, True), Unreadable, text)


class InvalidText(unittest.TestCase):
    def test_lone_surrogate_is_not_rendered(self) -> None:
        # @scenario inquisitor: Hostile text is logged safely
        for miss in (MissFile(hash=MISS_HASH, asked="2026-10-20", filter="2", said="a\ud800",
                              question="q", asked_from="o/api"),
                     MissFile(hash=MISS_HASH, asked="2026-10-20", filter="2", said="a",
                              question="q\udfff", asked_from="o/api")):
            with self.assertRaises(ValueError):
                render(miss)


class AnswersAndPaths(unittest.TestCase):
    ANSWER = Answer(answered_by="alice", authority="decision", recorded_in="docs/x.md", text="Yes.")

    def test_empty_answer_round_trips(self) -> None:
        # @scenario inquisitor: A whole comment fits as the answer
        log = LogFile(name="2026-10-20-q-3f9a1c.md", asked="2026-10-20", question="q",
                      repository="o/a", asked_from="o/a",
                      answer=replace(self.ANSWER, text="",
                                     answer_link="https://github.com/o/a/pull/12#pullrequestreview-5"))
        self.assertEqual(parse("questions/" + log.name, render(log), False), log)

    def test_recorded_in_rejects_unicode_controls(self) -> None:
        # This scenario sets recorded_in's forms too.
        # @scenario inquisitor: The forms a repository key and an answer_link must take
        for bad in ("docs/a\u009b31mb.md", "docs/a\u2028Re:x.md", "docs/\u0085x.md", "docs/a\u2029b.md"):
            self.assertFalse(is_recorded_in(bad), repr(bad))

