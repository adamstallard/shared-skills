"""Tests for qtext: a question's text and hash, inline markup, sentences
and terms."""

import hashlib
import unittest

from qtext import (UNTAGGED_LINE, FoundQuestion, Question, find_questions, line_kind,
                   question_hash, question_text, reduce_markup, sentences, terms)


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



def texts(found: list[FoundQuestion]) -> list[str]:
    return [question_text(f.question) for f in found]


class FindQuestions(unittest.TestCase):
    def test_colon_line_and_labels_begin_a_section(self) -> None:
        # @scenario inquisitor: A plain line ending in a colon begins an open-questions section
        for label in ("Open questions:", "**Open questions:**", "**Open questions**:", "Questions:",
                      "## Still open", "Question:", "Not in this change:", "### Deferred", "Not done:"):
            found = find_questions(f"{label}\n\n- Use a queue\n- Cap retries\n")
            self.assertEqual(texts(found), ["Use a queue", "Cap retries"], label)
            self.assertEqual([f.item for f in found], [1, 2])
            deferred = label.strip("#* :").startswith(("Not", "Deferred"))
            self.assertEqual([f.deferred for f in found], [deferred, deferred], label)

    def test_section_runs_to_next_heading_or_bold_label(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        body = ("# Open questions\n\n- One\n- Two\n\n1. Three\n- **Four** is bold\n\n"
                "**Notes:**\n\n- Not a question\n")
        found = find_questions(body)
        self.assertEqual(texts(found), ["One", "Two", "Three", "Four is bold"])
        self.assertEqual([f.item for f in found], [1, 2, 3, 4])

    def test_colon_line_naming_no_questions(self) -> None:
        # @scenario inquisitor: A colon line that names no questions begins nothing
        self.assertEqual(find_questions("Open a terminal and run:\n\n- ls\n- make test\n"), [])

    def test_other_heading_begins_nothing(self) -> None:
        # @scenario inquisitor: A heading that starts with another word is not an open-questions section
        self.assertEqual(find_questions("## OpenSpec changes\n\n- inquisitor\n- sequencer\n"), [])

    def test_no_question_in_code_or_quotes(self) -> None:
        # @scenario inquisitor: A question in a code block is not a question
        body = ("Intro.\n\n```\nIs this code?\n```\n\nRun `ready?` now.\n\n> Should we?\n\n"
                "~~~py\nok?\n~~~\n")
        self.assertEqual(find_questions(body), [])
        self.assertEqual(find_questions("Is it `ok?`"), [])
        self.assertEqual(find_questions("We call `retry?`\n"), [])

    def test_footer_keeps_questions(self) -> None:
        # @scenario inquisitor: Signing after vetting keeps the post vetted
        body = "Summary.\n\nShould retries back off?\n"
        signed = body + "\nprose ✓ 3f2a91\n"
        self.assertEqual(texts(find_questions(signed)), texts(find_questions(body)))
        deferred = body + "\nprose ✓ 3f2a91 (cold read deferred to the hand-back)"
        self.assertEqual(texts(find_questions(deferred)), ["Should retries back off?"])

    def test_sentence_related_line(self) -> None:
        # @scenario inquisitor: A sentence question's related-decision line is the next line
        # @scenario inquisitor: A question's sentence ends at its question mark
        body = ("We cap at v1.2 today. Should retries back off? Should they cap at a minute?\n"
                "Related: https://github.com/o/r/pull/3\n")
        found = find_questions(body)
        self.assertEqual(texts(found), ["Should retries back off?", "Should they cap at a minute?"])
        self.assertEqual(found[0].lines, ())
        self.assertEqual(found[1].lines, ("Related: https://github.com/o/r/pull/3",))
        self.assertEqual([f.item for f in found], [None, None])

    def test_related_line_with_more_than_a_url(self) -> None:
        # @scenario inquisitor: A `Related:` line holding more than a URL is part of the question
        body = "## Open questions\n\n- Should we retry?\n  Related: [the retry decision](https://github.com/o/r/pull/3)\n"
        found = find_questions(body)
        self.assertEqual(texts(found), ["Should we retry? Related: the retry decision"])
        self.assertEqual(found[0].lines, ())

    def test_both_lines_follow_a_sentence(self) -> None:
        # @scenario inquisitor: Both lines follow a sentence question in order
        body = ("Should we adopt spec-trace?\nRelated: https://github.com/o/r/pull/3\n"
                "Inquisitor: a person must decide this (required by spec-trace).\n")
        found = find_questions(body)
        self.assertEqual(texts(found), ["Should we adopt spec-trace?"])
        self.assertEqual(found[0].lines, ("Related: https://github.com/o/r/pull/3",
                                          "Inquisitor: a person must decide this (required by spec-trace)."))

    def test_tag_line_keeps_the_hash(self) -> None:
        # @scenario inquisitor: Adding the tag line keeps the vetted hash
        before = "Open questions:\n\n- Should retries back off?\n  Related: https://github.com/o/r/pull/3\n"
        for tag in ("@alice", UNTAGGED_LINE):
            after = before + f"  {tag}\n"
            self.assertEqual([question_hash(t) for t in texts(find_questions(after))],
                             [question_hash(t) for t in texts(find_questions(before))])
            self.assertEqual(find_questions(after)[0].lines[-1].strip(), tag)

    def test_markup_in_item_and_sentence(self) -> None:
        # @scenario inquisitor: A post question's text drops its list marker and markup
        found = find_questions("## Open questions\n\n- Should we **retry** [on 503](https://example.com)?\n\n"
                               "And is **this ok?** Yes.\n")
        self.assertEqual(texts(found), ["Should we retry on 503?", "And is this ok?"])


class FindQuestionsEdges(unittest.TestCase):
    def test_line_kind_first_line_is_text(self) -> None:
        # @scenario inquisitor: A trimmed related-decision line is left out of a picker question
        # (its "its first line never is")
        self.assertEqual(texts(find_questions("Related: https://x.com/?")), ["Related: https://x.com/?"])
        found = find_questions("Open questions:\n\n- Concerns: o/api\n")
        self.assertEqual(found[0].lines, ())

    def test_question_in_link_text_ends_the_paragraph(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("See [Retry?](https://x)")), ["See Retry?"])

    def test_multi_line_sentence_keeps_its_related_line(self) -> None:
        # @scenario inquisitor: A sentence question's related-decision line is the next line
        found = find_questions("Should we\nretry?\nRelated: https://github.com/o/r/pull/3\n")
        self.assertEqual(found[0].lines, ("Related: https://github.com/o/r/pull/3",))

    def test_lazy_continuation_and_list_colon(self) -> None:
        # @scenario inquisitor: A plain line ending in a colon begins an open-questions section
        found = find_questions("Open questions:\n\n- Should we\nretry?\n")
        self.assertEqual(texts(found), ["Should we retry?"])
        self.assertEqual(find_questions("- Questions:\n- Should we retry\n"), [])

    def test_footer_after_an_item(self) -> None:
        # @scenario inquisitor: Signing after vetting keeps the post vetted
        body = "Open questions:\n- Should we retry?\n"
        self.assertEqual(texts(find_questions(body + "prose ✓ 3f2a91")), texts(find_questions(body)))


class FindQuestionsMarkup(unittest.TestCase):
    def test_escaped_backtick_opens_no_code_span(self) -> None:
        # @scenario inquisitor: A question in a code block is not a question
        self.assertEqual(texts(find_questions("Is \\`this? fine` or not.")), ["Is `this?"])

    def test_indented_code_block_holds_no_question(self) -> None:
        # @scenario inquisitor: A question in a code block is not a question
        self.assertEqual(find_questions("Run this:\n\n    if ready? then\n        go\n\nDone."), [])

    def test_question_mark_in_link_title_or_tag(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(find_questions('See [the doc](https://x.io "Really? yes") here.'), [])
        self.assertEqual(find_questions('See <abbr title="why? because">it</abbr> here.'), [])


class FindQuestionsReducedSentences(unittest.TestCase):
    def test_bold_run_of_two_questions(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("**Should we retry? Or give up?** Tell me.\n")),
                         ["Should we retry?", "Or give up?"])

    def test_question_ending_link_text_or_tag(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body in ("Should we [retry?](https://example.com) I lean yes.\n",
                     "Should we <b>retry?</b> I lean yes.\n"):
            self.assertEqual(texts(find_questions(body)), ["Should we retry?"], body)


class FindQuestionsIndentedCode(unittest.TestCase):
    def test_markup_inside_indented_code(self) -> None:
        # @scenario inquisitor: A question in a code block is not a question
        self.assertEqual(find_questions("Example of the format:\n\n    **Open questions:**\n"
                                        "    - Should we retry?\n"), [])
        self.assertEqual(find_questions("Open questions:\n\n    - is this code?\n"), [])
        found = find_questions("Open questions:\n- Should we retry?\n\nExample:\n\n    - Is this code?\n")
        self.assertEqual(texts(found), ["Should we retry?"])

    def test_code_after_a_list_and_a_block(self) -> None:
        # @scenario inquisitor: A question in a code block is not a question
        for body in ("- Ran the tests\n\n## Logs\n\n    Continue? [y/N]\n",
                     "- Ran the tests\n\n```\nx\n```\n\n    Continue? [y/N]\n",
                     "- done\n\n> quoted\n\n    Continue? [y/N]\n"):
            self.assertEqual(find_questions(body), [], body)


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
