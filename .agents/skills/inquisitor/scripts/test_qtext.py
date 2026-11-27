"""Tests for qtext: a question's text and hash, inline markup, sentences
and terms."""

import hashlib
import unittest

from qtext import (UNTAGGED_LINE, Question, line_kind, question_hash, question_text,
                   reduce_markup, sentences, terms)


class QuestionText(unittest.TestCase):
    def test_picker_parts_join_with_line_feeds(self) -> None:
        # @scenario inquisitor: A picker question's text joins its parts with line feeds
        q = Question("picker", "Should retries  back\noff?", ("Yes", "No"))
        text = question_text(q)
        self.assertEqual(text, "Should retries back off?\nYes\nNo")
        self.assertEqual(question_hash(text), hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertRegex(question_hash(text), r"^[0-9a-f]{64}$")
        # A lone surrogate, which JSON can carry, still hashes.
        lone = question_text(Question("picker", "Ship the \ud83d fix?", ("Yes", "No")))
        self.assertRegex(question_hash(lone), r"^[0-9a-f]{64}$")

    def test_trimmed_related_line_is_left_out(self) -> None:
        # @scenario inquisitor: A trimmed related-decision line is left out of a picker question
        q = Question("picker", "Should retries back off?\n  Related: https://github.com/o/r/pull/3 ",
                     ("Yes", "No"))
        self.assertEqual(question_text(q), "Should retries back off?\nYes\nNo")
        item = Question("post", "Should retries back off?\n  Related: https://github.com/o/r/pull/3 ")
        self.assertEqual(question_text(item), "Should retries back off?")
        first = Question("post", "Related: https://github.com/o/r/pull/3")
        self.assertEqual(question_text(first), "Related: https://github.com/o/r/pull/3")

    def test_post_question_drops_markup(self) -> None:
        # @scenario inquisitor: A post question's text drops its list marker and markup
        q = Question("post", "Should we **retry** [on 503](https://example.com)?")
        self.assertEqual(question_text(q), "Should we retry on 503?")

    def test_whole_message_is_one_part(self) -> None:
        # @scenario inquisitor: A whole message is one part
        q = Question("text", "**Back off**,\n\ncapped at a minute.")
        self.assertEqual(question_text(q), "Back off, capped at a minute.")

    def test_tag_line_keeps_the_hash(self) -> None:
        # @scenario inquisitor: Adding the tag line keeps the vetted hash
        bare = Question("post", "Should retries back off?\nRelated: https://github.com/o/r/pull/3")
        tagged = Question("post", bare.question + "\n@alice")
        untagged = Question("post", bare.question + "\n" + UNTAGGED_LINE)
        h = question_hash(question_text(bare))
        self.assertEqual(question_hash(question_text(tagged)), h)
        self.assertEqual(question_hash(question_text(untagged)), h)

    def test_concerns_and_tag_lines_leave_the_hash(self) -> None:
        # @scenario inquisitor: A question about another repository names it
        bare = Question("post", "Does o/api retry on 503?")
        full = Question("post", bare.question + "\nConcerns: o/api\n@alice")
        self.assertEqual(question_text(full), question_text(bare))

    def test_concerns_line_with_more_is_part_of_the_question(self) -> None:
        # @scenario inquisitor: A `Concerns:` line holding more than a repository is part of the question
        self.assertIsNone(line_kind("Concerns: o/api and o/web"))
        self.assertIsNone(line_kind("Concerns: o/../../user"))
        self.assertEqual(line_kind(" Concerns: o/api "), "concerns")
        self.assertEqual(line_kind("Concerns: lore o/lore"), "concerns")
        q = Question("post", "Should retries back off?\nConcerns: o/api and o/web")
        self.assertEqual(question_text(q), "Should retries back off? Concerns: o/api and o/web")

    def test_related_line_with_more_is_part_of_the_question(self) -> None:
        # @scenario inquisitor: A `Related:` line holding more than a URL is part of the question
        line = "Related: [the retry decision](https://github.com/o/r/pull/3)"
        self.assertIsNone(line_kind(line))
        q = Question("post", "Should retries back off?\n" + line)
        self.assertEqual(question_text(q), "Should retries back off? Related: the retry decision")

    def test_other_left_out_lines(self) -> None:
        # @scenario inquisitor: The picker shows where the answer will be recorded
        q = Question("picker", "Should retries back off?\nRecorded: o/api questions branch (private)",
                     ("Yes", "No"))
        self.assertEqual(question_text(q), "Should retries back off?\nYes\nNo")
        self.assertEqual(line_kind("Not recorded: it has a category"), "record")
        self.assertIsNone(line_kind("@alice and @bob"))

    def test_person_required_line_leaves_the_hash(self) -> None:
        # @scenario inquisitor: A question spec-trace requires is posted with its line
        bare = Question("post", "Should this repository adopt spec-trace?")
        line = "Inquisitor: a person must decide this (required by spec-trace)."
        self.assertEqual(line_kind(line), "person-required")
        full = Question("post", bare.question + "\n" + line)
        self.assertEqual(question_hash(question_text(full)), question_hash(question_text(bare)))


class Markup(unittest.TestCase):
    def test_each_kind_reduces(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(
            reduce_markup("Use `retry()` in ~~v1~~ *v2*, see <https://example.com> and "
                          "\\*this\\* <b>now</b>?"),
            "Use retry() in v1 v2, see https://example.com and *this* now?")
        self.assertEqual(reduce_markup("![a chart](x.png) and __strong__ and _em_"),
                         "a chart and strong and em")
        self.assertEqual(reduce_markup("snake_case stays, as does 2 * 3 * 4"),
                         "snake_case stays, as does 2 * 3 * 4")

    def test_discord_forms_stay(self) -> None:
        # @scenario inquisitor: Discord's angle-bracket forms and a single tilde stay as written
        text = "<@123> should ~this~ wait until <t:1700000000>?"
        self.assertEqual(reduce_markup(text), text)
        for form in ("<a:name:id>", "<#456>", "<:name:789>"):
            self.assertEqual(reduce_markup(form), form)
        self.assertEqual(reduce_markup("a <br/> b </i>"), "a  b ")


class SentencesAndTerms(unittest.TestCase):
    def test_sentence_ends_at_question_mark(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(sentences("We cap at v1.2 today. Should retries back off? I think so."),
                         ["We cap at v1.2 today.", "Should retries back off?", "I think so."])

    def test_terms_are_lowercased_words(self) -> None:
        # @scenario inquisitor: A question's terms are its lowercased words
        self.assertEqual(terms("Should Retries back-off on 503, or retry?"),
                         {"should", "retries", "back", "off", "on", "503", "or", "retry"})
        self.assertEqual(terms("Größe_Ändern"), {"größe", "ändern"})


if __name__ == "__main__":
    unittest.main()


class BracketedLinkText(unittest.TestCase):
    def test_link_text_with_brackets(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("[see [1] here](https://x.example)?"), "see [1] here?")


class MarkupAtTheEnd(unittest.TestCase):
    def test_markup_ending_the_text(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("ends \\"), "ends \\")
        self.assertEqual(reduce_markup("a `"), "a `")
        self.assertEqual(reduce_markup("use `x`"), "use x")
        self.assertEqual(reduce_markup("`a``"), "`a``")
        self.assertEqual(reduce_markup("`` `a` ``"), "`a`")


class UnicodeWords(unittest.TestCase):
    def test_underscore_inside_non_ascii_word(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("Should 設定_名前_値 change?"), "Should 設定_名前_値 change?")
        self.assertEqual(reduce_markup("größe__x__wert"), "größe__x__wert")


class RecordLines(unittest.TestCase):
    def test_only_a_record_line_in_its_form_is_left_out(self) -> None:
        # @scenario inquisitor: The picker shows where the answer will be recorded
        # @scenario inquisitor: Not recorded gives a listed reason
        bare = Question("picker", "Should retries back off?", ("Yes", "No"))
        h = question_hash(question_text(bare))
        for line in ("Recorded: o/api questions branch (private)",
                     "Recorded: o/lore questions branch (public), more visible than o/api (private), "
                     "where this was asked",
                     "Not recorded: about your way of working",
                     "Not recorded: only a security advisory may hold it",
                     "Not recorded: it has a category",
                     "Not recorded: no push access to its questions branch",
                     "Not recorded: no team's lore repository serves it",
                     "Not recorded: no GitHub login configured"):
            q = Question("picker", bare.question + "\n" + line, bare.options)
            self.assertEqual(question_hash(question_text(q)), h, line)
        for line in ("Not recorded: also, may I force-push main?",
                     "Recorded: and should we delete the staging cluster?"):
            q = Question("picker", bare.question + "\n" + line, bare.options)
            self.assertNotEqual(question_hash(question_text(q)), h, line)
        post = Question("post", "Should retries back off?\nRecorded: o/api questions branch (private)")
        self.assertIn("Recorded:", question_text(post))
