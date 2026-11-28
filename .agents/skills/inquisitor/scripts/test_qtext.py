"""Tests for qtext: a question's text and hash, inline markup, sentences
and terms."""

import hashlib
import random
import time
import unittest

from qtext import (UNTAGGED_LINE, FoundQuestion, Mention, Question, find_questions, line_kind,
                   mentions, question_hash, question_text, reduce_markup, sentences, terms)


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
            "Use retry() in v1 v2, see https://example.com and *this* <b>now</b>?")
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
        self.assertEqual(reduce_markup("a <br/> b </i>"), "a <br/> b </i>")


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
        # @scenario inquisitor: Only a closed fence makes a code block
        body = "Intro.\n\n```\nIs this code?\n```\n\n> Should we?\n\n~~~py\nok?\n~~~\n"
        self.assertEqual(find_questions(body), [])

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
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(texts(find_questions("Is \\`this? fine` or not.")), ["Is `this?"])

    def test_indented_code_block_holds_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(find_questions("Run this:\n\n    if ready? then\n        go\n\nDone."), [])

    def test_question_mark_in_link_title_or_tag(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(find_questions('See [the doc](https://x.io "Really? yes") here.'), [])
        self.assertEqual(texts(find_questions('See <abbr title="why? because">it</abbr> here.')),
                         ['See <abbr title="why?'])


class FindQuestionsReducedSentences(unittest.TestCase):
    def test_bold_run_of_two_questions(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("**Should we retry? Or give up?** Tell me.\n")),
                         ["Should we retry?", "Or give up?"])

    def test_question_ending_link_text_or_tag(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("Should we [retry?](https://example.com) I lean yes.\n")),
                         ["Should we retry?"])
        self.assertEqual(texts(find_questions("Should we <b>retry?</b> I lean yes.\n")), ["Should we <b>retry?"])


class FindQuestionsIndentedCode(unittest.TestCase):
    def test_markup_inside_indented_code(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(find_questions("Example of the format:\n\n    **Open questions:**\n"
                                        "    - Should we retry?\n"), [])
        self.assertEqual(find_questions("Open questions:\n\n    - is this code?\n"), [])
        found = find_questions("Open questions:\n- Should we retry?\n\nExample:\n\n    - Is this code?\n")
        self.assertEqual(texts(found), ["Should we retry?"])

    def test_code_after_a_list_and_a_block(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("- Ran the tests\n\n## Logs\n\n    Continue? [y/N]\n",
                     "- Ran the tests\n\n```\nx\n```\n\n    Continue? [y/N]\n",
                     "- done\n\n> quoted\n\n    Continue? [y/N]\n"):
            self.assertEqual(find_questions(body), [], body)



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
                     "Not recorded: no GitHub login configured",
                     "Not recorded: asked outside any repository"):
            q = Question("picker", bare.question + "\n" + line, bare.options)
            self.assertEqual(question_hash(question_text(q)), h, line)
        for line in ("Not recorded: also, may I force-push main?",
                     "Recorded: and should we delete the staging cluster?"):
            q = Question("picker", bare.question + "\n" + line, bare.options)
            self.assertNotEqual(question_hash(question_text(q)), h, line)
        post = Question("post", "Should retries back off?\nRecorded: o/api questions branch (private)")
        self.assertIn("Recorded:", question_text(post))


class MarkupAtTheEdges(unittest.TestCase):
    def test_unfinished_markup_at_the_end_stays(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        for text in ("is <b", "Is <a b?", "see [x]", "[a](b ", '[a](b "t"'):
            self.assertEqual(reduce_markup(text), text)
        self.assertEqual(reduce_markup("[a](b(c)) \\"), "a \\")


class HeadingForms(unittest.TestCase):
    def test_heading_forms_begin_a_section(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        for heading in ("   ## Open questions", "###### Open questions", "## Open questions ##"):
            self.assertEqual(texts(find_questions(f"{heading}\n\n- Use a queue\n")), ["Use a queue"], heading)
        self.assertEqual(find_questions("    ## Open questions\n\n- Use a queue\n"), [])
        self.assertEqual(find_questions("    ## Why not use a queue?\n"), [])

    def test_question_in_a_heading_or_bold_label(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for line in ("## Why not use a queue?", "**Why not use a queue?**", "## Why not use a queue? ##"):
            found = find_questions(line + "\n")
            self.assertEqual(texts(found), ["Why not use a queue?"], line)
            self.assertEqual(found[0].raw, "Why not use a queue?", line)

    def test_thematic_break_is_no_bold_label(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        for rule in ("****", "____", "****:", "*****", "______", "* * *", "- - -", "---"):
            found = find_questions(f"Open questions:\n\n- One\n\n{rule}\n\n- Two\n")
            self.assertEqual(texts(found), ["One", "Two"], rule)
            self.assertEqual([f.item for f in found], [1, 2], rule)


class BreaksAndLabels(unittest.TestCase):
    def test_indented_break_stays_in_its_item(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        found = find_questions("## Open questions\n\n- Retry policy\n  ***\n  Should we cap it?\n")
        self.assertEqual([(f.item, question_text(f.question)) for f in found],
                         [(1, "Retry policy *** Should we cap it?")])
        found = find_questions("## Not in this change\n\n- Should we retry?\n\n  ---\n\n  @alice\n")
        self.assertEqual(found[0].lines, ("  @alice",))

    def test_line_bold_only_at_its_ends_is_no_bold_label(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        body = "## Open questions\n\n- Should we retry?\n**Note:** both depend on **the budget**\n- Cap at 10 or 20\n"
        self.assertEqual([f.item for f in find_questions(body)], [1, 2])


class IterationThree(unittest.TestCase):
    def test_line_after_an_indented_break_is_not_lazy(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        for rule in ("  ***", " ***"):
            found = find_questions(f"## Open questions\n\n- Should we retry?\n{rule}\nShould we also log?\n")
            self.assertEqual([(f.item, question_text(f.question)) for f in found][1:],
                             [(None, "Should we also log?")], rule)

    def test_code_span_in_a_bold_label(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        for label in ("**Questions about `**kwargs`:**", "__Questions on `__init__`__"):
            found = find_questions(f"{label}\n\n- Should it take a timeout\n")
            self.assertEqual([(f.item, question_text(f.question)) for f in found],
                             [(1, "Should it take a timeout")], label)

    def test_strong_around_intraword_emphasis(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("Is **re*try*able** the right word?"), "Is retryable the right word?")
        self.assertEqual(reduce_markup("**foo*bar*baz**"), "foobarbaz")
        self.assertEqual(reduce_markup("*foo**bar*"), "foo**bar")

    def test_lines_after_a_question_in_a_heading(self) -> None:
        # @scenario inquisitor: A sentence question's related-decision line is the next line
        found = find_questions("### Should we retry?\nRelated: https://github.com/o/r/pull/3\nConcerns: o/r\n")
        self.assertEqual(found[0].lines, ("Related: https://github.com/o/r/pull/3", "Concerns: o/r"))
        found = find_questions("**Should we retry?**\nConcerns: o/r\n@alice\n")
        self.assertEqual(found[0].lines, ("Concerns: o/r", "@alice"))


class FailTowardFinding(unittest.TestCase):
    def test_angle_bracket_not_starting_a_letter_is_text(self) -> None:
        # @scenario inquisitor: Discord's angle-bracket forms and a single tilde stay as written
        self.assertEqual(texts(find_questions("Should timeouts be <5 s or <10 s? We pick one > 3.\n")),
                         ["Should timeouts be <5 s or <10 s?"])
        self.assertEqual(reduce_markup("Is <a b?\nok> yes"), "Is <a b?\nok> yes")
        self.assertEqual(reduce_markup('a <abbr title="x">b</abbr> c'), 'a <abbr title="x">b</abbr> c')
        found = find_questions("Open questions:\n\n- Is a < b here?\n- Should we <b>ship</b> it?\n")
        self.assertEqual(texts(found), ["Is a < b here?", "Should we <b>ship</b> it?"])

    def test_leftover_markup_after_a_mark_hides_no_question(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("Is it **ok?** Fine.\n")), ["Is it ok?"])
        self.assertEqual(texts(find_questions("Is it ok?** Fine.\n")), ["Is it ok?"])

    def test_line_after_no_question_stays_in_the_scan(self) -> None:
        # @scenario inquisitor: A sentence question's related-decision line is the next line
        found = find_questions("Should we? x\nmore\nRelated: https://x.io/?token=abc\n")
        self.assertEqual(found[0].lines, ())
        self.assertIn("token=abc", found[0].raw)


class RunTwoGaps(unittest.TestCase):
    def test_heading_question_followed_by_text(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("## Why not use a queue?\nSome text.\n")),
                         ["Why not use a queue?"])

    def test_question_in_a_bold_label_with_colon_after(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("**Why not?**:\n")), ["Why not?"])

    def test_closing_only_runs_stay(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("Is a* b* ok?"), "Is a* b* ok?")
        self.assertEqual(reduce_markup("Is a_ b_ ok?"), "Is a_ b_ ok?")

    def test_break_after_a_list_ends_it(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(find_questions("- item\n\n---\n\n    Continue? [y/N]\n"), [])


class NoQuestionMissed(unittest.TestCase):
    def test_indented_text_without_a_blank_line_is_no_code(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        self.assertEqual(texts(find_questions("1. Run the setup:\n    ```\n    make\n    ```\n"
                                              "    Does this work on macOS?\n")), ["Does this work on macOS?"])
        self.assertEqual(texts(find_questions("- First point that is\nwrapped lazily.\n\n    Is this ok?\n")),
                         ["Is this ok?"])
        self.assertEqual(texts(find_questions("**Open questions:**\n    - Which backend\n    - Who signs tokens\n")),
                         ["Which backend", "Who signs tokens"])
        for body in ("Questions:\n    Should we cache?\n", "**Note**\n    Should we cache?\n",
                     "> context\n    Should we cache?\n"):
            self.assertEqual(texts(find_questions(body)), ["Should we cache?"], body)

    def test_a_label_that_asks_keeps_its_question(self) -> None:
        # @scenario inquisitor: A plain line ending in a colon begins an open-questions section
        found = find_questions("## Questions: should we ship today?\n\n- Which region\n")
        self.assertEqual(texts(found), ["Questions: should we ship today?", "Which region"])
        found = find_questions("Question: should we keep the cache? Options below:\n\n- Yes\n")
        self.assertEqual(texts(found), ["Question: should we keep the cache?", "Yes"])
        self.assertEqual(texts(find_questions("**Open question: is the cache needed?**\n")),
                         ["Open question: is the cache needed?"])

    def test_more_label_forms(self) -> None:
        # @scenario inquisitor: A setext heading begins a section
        for label in ("Open questions\n--------------", "Open questions\n===", "*Open questions:*",
                      "## 1. Open questions"):
            self.assertEqual(texts(find_questions(f"{label}\n\n- Which backend\n")), ["Which backend"], label)

    def test_inline_code_at_line_start_opens_no_fence(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        self.assertEqual(texts(find_questions("```npm ci``` fails here, should we pin it?\n\nMore text.\n")),
                         ["npm ci fails here, should we pin it?"])

    def test_question_mark_before_closing_punctuation_or_a_tag(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body, want in (("Should we retry?<br>I think so.", "Should we retry?"),
                           ("Should we retry?[^1]\n\n[^1]: See the log.", "Should we retry?"),
                           ("We could cache it (or should we?)", "We could cache it (or should we?"),
                           ("He asked \"should we retry?\" today.", "He asked \"should we retry?")):
            self.assertEqual(texts(find_questions(body + "\n")), [want], body)


class BlocksInsideItems(unittest.TestCase):
    def test_indented_fence_under_a_paragraph_opens_nothing(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        body = "Some context here\n    ```bash\nShould we ship?\n\nAnother question here?\n"
        self.assertEqual(texts(find_questions(body)), ["Some context here ```bash Should we ship?",
                                                       "Another question here?"])

    def test_block_inside_a_list_item_keeps_the_list(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for head in ("- a\n\n  ```\n  code\n  ```\n", "- a\n  > quote\n", "- a\n\n  **Note**\n",
                     "- a\n  ---\n", "- a\n  ## Sub\n"):
            self.assertEqual(texts(find_questions(head + "\n    Should we ship?\n")), ["Should we ship?"], head)

    def test_indented_label_inside_a_section_item(self) -> None:
        # @scenario inquisitor: A section runs to the next heading or bold label
        for inner in ("\n  **Context:**\n  blah\n", "  ### Detail\n  blah\n"):
            found = find_questions(f"Open questions:\n- Should we ship\n{inner}- Retry policy\n")
            self.assertEqual([f.item for f in found], [1, 2], inner)

    def test_question_mark_before_more_punctuation(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("Should we really ship?!\n")), ["Should we really ship?"])
        self.assertEqual(texts(find_questions('Ask "should we ship?", then decide.\n')),
                         ['Ask "should we ship?'])


# -- property tests -------------------------------------------------------------
# A seeded generator of markdown fragments, each built beside the text it must
# reduce to, so a property checks the exact result rather than a weaker shape.

_WORDS = ("retry", "back", "off", "cap", "v1.2", "503", "queue", "don't", "snake_case", "größe",
          "設定", "x2", "(see", "it)", "a,", "b;", "2 * 3", "a ~ b", "~one~", "#7", "&amp;", "50%")
_CODE_PIECES = ("x", "*", "_", "[", "]", "<b>", "\\", "ready go", "a.b", "~~", "**y**", "f()")
_DESTINATIONS = ("https://x.y/a?b=1", "https://x.y/(c)", "rel/path.md", "", "a\\)b")
_TITLES = (' "Really? *yes*"', " 'why? [no]'", "")
_ESCAPED = "*_[]<>`#\\~"


class _Fragments:
    """Builds (markdown, expected reduced text) pairs from a seeded random."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def code(self) -> tuple[str, str]:
        inner = " ".join(self.rng.choice(_CODE_PIECES) for _ in range(self.rng.randint(1, 3)))
        return f"`{inner}`", inner

    def construct(self, depth: int, in_link: bool = False) -> tuple[str, str]:
        r = self.rng
        kinds = ["word", "word", "code", "escape", "html", "br"]
        if not in_link:
            kinds.append("autolink")
        if depth > 0:
            kinds += ["em", "em", "strike"] + ([] if in_link else ["link", "image"])
        kind = r.choice(kinds)
        if kind == "word":
            word = r.choice(_WORDS)
            return word, word
        if kind == "code":
            return self.code()
        if kind == "escape":
            c = r.choice(_ESCAPED)
            return "\\" + c, c
        if kind == "html":
            md, text = self.run(depth - 1, in_link)
            tag = r.choice(("b", "i"))
            return f"<{tag}>{md}</{tag}>", f"<{tag}>{text}</{tag}>"
        if kind == "br":
            return "<br/>", "<br/>"
        if kind == "autolink":
            url = r.choice(("https://example.com/a_b*c", "https://x.y/?q=1", "mailto:a@b.co"))
            return f"<{url}>", url
        md, text = self.run(depth - 1, in_link)
        if not (md[0].isalnum() and md[-1].isalnum()):
            # Emphasis whose text starts or ends with punctuation can be
            # read two ways when another emphasis encloses it; a word at
            # each end keeps the fragment unambiguous.
            md, text = f"cap {md} cap", f"cap {text} cap"
        if kind == "em":
            mark = r.choice(("*", "_", "**", "__"))
            return f"{mark}{md}{mark}", text
        if kind == "strike":
            return f"~~{md}~~", text
        dest = r.choice(_DESTINATIONS)
        # A title follows only a destination (CommonMark).
        dest += r.choice(_TITLES) if dest else ""
        if kind == "link":
            md, text = self.run(depth - 1, True)
            return f"[{md}]({dest})", text
        return f"![{md}]({dest})", text

    def run(self, depth: int, in_link: bool = False) -> tuple[str, str]:
        """Constructs joined by single spaces; the run starts and ends with
        no whitespace, so emphasis around it opens and closes."""
        parts = [self.construct(depth, in_link) for _ in range(self.rng.randint(1, 3))]
        md = " ".join(p[0] for p in parts)
        text = " ".join(p[1] for p in parts)
        if not text.strip() or md != md.strip():
            return "word", "word"
        return md, text


class ReductionProperties(unittest.TestCase):
    def test_reduced_text_holds_no_markup_it_should_drop(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        gen = _Fragments(25)
        for _ in range(3000):
            md, text = gen.run(3)
            self.assertEqual(reduce_markup(md), text, md)

    def test_long_unmatched_openers_reduce_quickly(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        # 64 KB of openers that never close: the reduction this parser replaced took 9 s on "*a ".
        for unit in ("*a ", " _a", "**a ", "~~a ", "`` a ` ", "<a ", "[", "![", "[](x", '[a](b "',
                     "[a](((", "*a _b **c [d `e <f "):
            body = (unit * (65536 // len(unit) + 1))[:65536]
            start = time.perf_counter()
            reduce_markup(body)
            find_questions(body)
            find_questions("Open questions:\n\n- " + body)
            self.assertLess(time.perf_counter() - start, 1.0, unit)


def _sentence(gen: _Fragments, mark: str) -> tuple[str, str]:
    md, text = gen.run(2)
    return md + mark, " ".join((text + mark).split())


class FindQuestionsProperties(unittest.TestCase):
    def test_listed_question_text_is_found_with_that_text(self) -> None:
        # @scenario inquisitor: A question's text posted as a listed item is found with that text
        rng = random.Random(7)
        pool = [c for c in map(chr, range(0x21, 0x2FF)) if c not in "*_`~[<\\" and not c.isspace()]
        pool += list("??..!!:##--()]>@") + ["é", "ß", "設", "🙂", "✓"]
        for _ in range(3000):
            words = ["".join(rng.choice(pool) for _ in range(rng.randint(1, 8)))
                     for _ in range(rng.randint(1, 6))]
            text = " ".join(words)
            found = find_questions(f"Open questions:\n\n- {text}\n")
            self.assertEqual(len(found), 1, text)
            self.assertEqual(found[0].item, 1, text)
            self.assertEqual(question_text(found[0].question), text)
            self.assertEqual(question_hash(question_text(found[0].question)), question_hash(text))

    def test_each_question_is_found_with_the_text_it_reports(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        # @scenario inquisitor: A post question's text drops its list marker and markup
        gen = _Fragments(11)
        for _ in range(1500):
            items = [gen.run(2) for _ in range(gen.rng.randint(0, 3))]
            pieces = [_sentence(gen, gen.rng.choice(".?!?")) for _ in range(gen.rng.randint(1, 4))]
            paragraph = ""
            for md, _ in pieces:
                paragraph += (gen.rng.choice((" ", "\n")) if paragraph else "") + md
            body = paragraph + "\n"
            if items:
                body += "\nOpen questions:\n\n" + "".join(f"- {md}\n" for md, _ in items)
            found = find_questions(body)
            want = ([text for _, text in pieces if text.endswith("?")]
                    + [" ".join(text.split()) for _, text in items])
            self.assertEqual(texts(found), want, body)
            self.assertEqual([f.item for f in found],
                             [None] * (len(want) - len(items)) + list(range(1, len(items) + 1)))

    def test_hash_is_stable_across_tag_lines_and_footer(self) -> None:
        # @scenario inquisitor: Adding the tag line keeps the vetted hash
        # @scenario inquisitor: Signing after vetting keeps the post vetted
        gen = _Fragments(3)
        related = "Related: https://github.com/o/r/pull/3"
        for _ in range(1000):
            sentence_md, _ = _sentence(gen, "?")
            items = [gen.run(2)[0] for _ in range(gen.rng.randint(1, 3))]
            relate = [gen.rng.random() < 0.5 for _ in range(len(items) + 1)]
            tags = [gen.rng.choice(("@alice", UNTAGGED_LINE)) for _ in range(len(items) + 1)]

            def body(tagged: bool) -> str:
                out = sentence_md + "\n"
                out += related + "\n" if relate[0] else ""
                out += tags[0] + "\n" if tagged else ""
                out += "\nOpen questions:\n\n"
                for md, rel, tag in zip(items, relate[1:], tags[1:]):
                    out += f"- {md}\n" + (f"  {related}\n" if rel else "") + (f"  {tag}\n" if tagged else "")
                return out

            before = [question_hash(t) for t in texts(find_questions(body(False)))]
            self.assertEqual(len(before), len(items) + 1)
            for after in (body(True), body(True) + "\nprose ✓ 3f2a91\n",
                          body(False) + "prose ✓ 3f2a91 (cold read deferred to the hand-back)"):
                self.assertEqual([question_hash(t) for t in texts(find_questions(after))], before, after)


class OnlyClosedPlacedFencesHide(unittest.TestCase):
    def test_a_misplaced_or_unclosed_fence_is_text(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for head in ("# Notes\n    ```\n", "# Notes\n\t```\n", "***\n    ```\n", "```\nx\n```\n    ```\n",
                     "Title\n=====\n    ```\n", "- a\n      ```\n", "- a\n\n        ```\n  ",
                     "- a\n  ```\n  make\n", "```\n"):
            found = texts(find_questions(head + "Should we ship it?\n"))
            self.assertEqual(len(found), 1, head)
            self.assertTrue(found[0].endswith("Should we ship it?"), head)

    def test_a_closed_fence_in_its_place_hides_its_lines(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("```\nHidden?\n```\nShould we ship it?\n",
                     "- a\n\n  ```\n  Hidden?\n  ```\n\n    Should we ship it?\n",
                     "- a\n  ~~~~\n  Hidden?\n  ~~~\n  ~~~~\nShould we ship it?\n"):
            self.assertEqual(texts(find_questions(body)), ["Should we ship it?"], body)

    def test_a_fence_leaving_its_item_before_closing_is_text(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        found = texts(find_questions("- a\n  ```\nShould we ship it?\n  ```\n"))
        self.assertTrue(found and found[0].endswith("Should we ship it?"), found)

    def test_a_block_ending_a_section_item_keeps_the_list(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for block in ("  > note\n", "  ```\n  x\n  ```\n"):
            found = find_questions(f"Open questions:\n- Which one\n{block}\n    Should we ship it?\n")
            self.assertEqual(texts(found), ["Which one", "Should we ship it?"], block)

    def test_many_unclosed_fences_read_fast(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("```a\n" * 13000, "- a\n" + "  ```a\n" * 9000 + "b\n```\n"):
            start = time.perf_counter()
            find_questions(body)
            self.assertLess(time.perf_counter() - start, 1.0)


class LooseQuestionEnds(unittest.TestCase):
    def test_a_question_mark_before_anything_but_a_letter_or_digit_ends_it(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body in ("Should we ship it?\\\nI think so.", "Should we ship it?<!-- todo -->",
                     "Should we ship it?&nbsp;I think so.", "Should we ship it?&quot; she asked.",
                     "Should we ship it&#63;", "Should we ship it&quest; I think so.",
                     "Should we ship it?\u2014I think so.", "Should we ship it?\u2026"):
            self.assertEqual(texts(find_questions(body)), ["Should we ship it?"], body)

    def test_a_table_cell_question_is_found(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body in ("|Q|A|\n|---|---|\n|Should we ship it?|maybe|\n",
                     "| Q | A |\n| --- | --- |\n| x | Should we ship it?|\n"):
            found = texts(find_questions(body))
            self.assertEqual(len(found), 1, body)
            self.assertTrue(found[0].endswith("Should we ship it?"), body)

    def test_a_run_of_marks_after_a_question_starts_no_sentence(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("Seriously?? What?!? Why...? What!? Next?\n")),
                         ["Seriously?", "What?", "Why...?", "What!?", "Next?"])

    def test_a_question_mark_inside_a_word_ends_nothing(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("See https://x.y/?q=1 for the form. Fine?\n")), ["Fine?"])


class SanitizedTagNames(unittest.TestCase):
    def test_a_tag_stays_as_written(self) -> None:
        # @scenario inquisitor: Discord's angle-bracket forms and a single tilde stay as written
        self.assertEqual(texts(find_questions("Should we use <T or Any? I think a > b.\n")),
                         ["Should we use <T or Any?"])
        self.assertEqual(texts(find_questions("Should we <b>ship</b> it? <details><summary>x</summary></details>\n")),
                         ["Should we <b>ship</b> it?"])


class FencesAndTagsInContext(unittest.TestCase):
    def test_a_fence_under_a_nested_list_ends_with_its_item(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body, want in (
                ("1. Step one\n   - detail\n   ```sh\n   run\n2. Is step two right?\n\n```sh\nother\n```\n",
                 "Is step two right?"),
                ("- a\n  - b\n  ```\n  code\nIs this ok?\n\n```\nx\n```\n", "Is this ok?"),
                ("- a\n\n para\n    ```\n  Is this hidden?\n    ```\n", "Is this hidden?")):
            found = texts(find_questions(body))
            self.assertTrue(any(t.endswith(want) for t in found), (body, found))

    def test_a_fence_on_an_item_marker_line_pairs_with_its_closer(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        body = "- ```sh\n  npm ci\n  ```\n  Should this be npm install instead?\n  ```sh\n  npm install\n  ```\n"
        self.assertEqual(texts(find_questions(body)), ["Should this be npm install instead?"])

    def test_a_tag_name_with_no_valid_attributes_is_text(self) -> None:
        # @scenario inquisitor: Discord's angle-bracket forms and a single tilde stay as written
        self.assertEqual(texts(find_questions("Is the limit <a minute? I think a minute is >30s here.\n")),
                         ["Is the limit <a minute?"])
        self.assertEqual(texts(find_questions("Is i<q for all q? Yes for i>0.\n")), ["Is i<q for all q?"])
        self.assertEqual(reduce_markup('Go <a href="x">here</a> <br/> </b >now'), 'Go <a href="x">here</a> <br/> </b >now')

    def test_a_fence_in_an_html_block_hides_no_question_from_the_union(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = "<details>\n<summary>Log</summary>\n```\nShould we retry here?\n```\n</details>\n"
        found = texts(find_questions(body, in_code=True))
        self.assertTrue(any(t.endswith("Should we retry here?") for t in found), found)


class MutationGapsRunThree(unittest.TestCase):
    def test_a_fence_pairs_with_its_nearest_closer(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        self.assertEqual(texts(find_questions("- a\n  ```\n  Hidden?\n  ````\n  ```\nShown?\n```\n")),
                         ["``` Shown?"])

    def test_a_fence_four_columns_in_is_text_even_when_closed(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        self.assertEqual(texts(find_questions("Para\n    ```\nHidden?\n```\n")), ["Para ``` Hidden?"])

    def test_an_empty_items_text_starts_after_its_marker(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        self.assertEqual(texts(find_questions("-\n     ```\n     Hidden?\n     ```\nAfter?\n")), ["After?"])

    def test_a_question_entity_reduces_once(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("Should we ship it&#63; Yes&quest; &amp;"), "Should we ship it? Yes? &amp;")


class DemotedFenceChains(unittest.TestCase):
    def test_the_closer_of_a_fence_read_as_text_opens_nothing(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body, want in (("- a\n    ```\n  Q?\n    ```\n    Shown?\n    ```\n", "Shown?"),
                           ("- a\n  <div>\n- ```\n\n  Q?\n  ```\n  Shown?\n  ```\n", "Shown?"),
                           ("<p/x\n```\n\n```\nShown?\n```\n", "Shown?"),
                           ("## Open questions\n- Should A?\n  - ```sh\n    x\n    ```\n    Should B?\n    ```\n",
                            "Should B?")):
            found = find_questions(body)
            self.assertTrue(any(want in question_text(q.question) for q in found), (body, found))

    def test_an_unclosed_marker_line_fence_opens_no_code_span(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("Intro.\n\n- ```sh\n  Should we ship? ```\n", "- ```\n  Is it ok?\n  run ``` now\n"):
            found = texts(find_questions(body))
            self.assertTrue(any("?" in t for t in found), (body, found))


class FencesInListsAndHtml(unittest.TestCase):
    def test_a_fence_is_placed_against_the_item_its_line_is_in(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("- a\n  - b\n\n  para\n      ~~~\n      code?\n      ~~~\n",
                     "- a\n  - b\n\n  para\n      ```\n      code?\n      ````\n",
                     "-     x\n  para\n      ~~~\n      code?\n      ~~~\n",
                     "Open questions:\n\n- a\n  - b\n\n  para\n      ~~~\n      code?\n      ~~~\n"):
            found = find_questions(body)
            self.assertTrue(any("code?" in question_text(q.question) for q in found), (body, found))

    def test_an_ordered_item_not_starting_at_one_does_not_interrupt_a_paragraph(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("text\n2. ~~~\n   code?\n   ~~~\n", "text\n2. ```\n   code?\n   ````\n",
                     "Open questions:\n\ntext\n2. ~~~\n   code?\n   ~~~\n"):
            found = find_questions(body)
            self.assertTrue(any("code?" in question_text(q.question) for q in found), (body, found))

    def test_a_fence_in_an_html_block_hides_no_question_from_the_union_in_a_list(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("<span>\n~~~\nIs it ok?\n~~~\n</span>\n", "Intro.\n\n<a name=\"x\">\n~~~\nIs it ok?\n~~~\n",
                     "- a\n\n    <div>\n    ~~~\n    Is it ok?\n    ~~~\n",
                     "1. a\n   - b\n\n     <div>\n     ~~~\n     Is it ok?\n     ~~~\n     </div>\n"):
            found = find_questions(body, in_code=True)
            self.assertTrue(any("Is it ok?" in question_text(q.question) for q in found), (body, found))


class SecondReading(unittest.TestCase):
    def check(self, body: str, want: str) -> None:
        found = [(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)]
        self.assertTrue(any(want in text for text, _ in found), (body, found))

    def test_an_escaped_fence_next_to_a_lone_backtick_hides_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("`Is it ready?\n    ```\n", "Is `it ready?\n   ```\n", "<div>\nIs `it ready?\n```\n"):
            self.check(body, "it ready?")

    def test_lines_a_demoted_fence_shows_lose_no_sentence_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("Open questions:\nSome text\n    ```\n```\ncode\n```\n2. Pick a color?\n",
                     "Open questions:\nSome text\n    ```\n```\n## Notes\n```\n- Pick a color?\n",
                     "Open questions:\nSome text\n<span>\n```\n## Notes\n```\n- Pick a color?\n"):
            self.check(body, "Pick a color?")

    def test_a_fence_on_a_line_that_is_no_item_hides_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("Para\n    - ~~~ Is it ready?\n        ~~~\n", "Para\n    - ~~~\n      Is it ready?\n      ~~~\n",
                     "Para\n    - ```\n      Is it ready?\n      ````\n",
                     "- a\n      - ~~~\n        Is it ready?\n        ~~~\n",
                     "- a\n  2. ~~~\n     Is it ready?\n     ~~~\n"):
            self.check(body, "Is it ready?")

    def test_only_the_second_reading_marks_a_question_in_code(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = "```\nShould we hide?\n```\nShould we ship it?\n"
        self.assertEqual(texts(find_questions(body)), ["Should we ship it?"])
        self.assertEqual([(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)],
                         [("Should we hide?", True), ("Should we ship it?", False)])

    def test_the_second_reading_repeats_no_question_the_first_found(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("Open questions:\n- Retry policy\n  ***\n  Should we cap it?\n",
                     "- ```sh\n  npm ci\n  ```\n  Should this be npm install instead?\n  ```sh\n  npm install\n  ```\n",
                     "Some context here\n    ```bash\nShould we ship?\n\nAnother question here?\n"):
            self.assertEqual(find_questions(body, in_code=True), find_questions(body), body)

    def test_the_second_reading_stays_fast(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("a? " * 20000, "```a\n" * 13000, "- ```a\nb?\n" * 6000):
            start = time.perf_counter()
            find_questions(body, in_code=True)
            self.assertLess(time.perf_counter() - start, 2.0)


class SecondReadingHidesNothing(unittest.TestCase):
    def found(self, body: str) -> list[tuple[str, bool]]:
        return [(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)]

    def test_an_indented_code_misread_hides_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("- First point\n**Note**\n\n    Should we ship this?\n",
                     "- First point\n__Note:__\n\n    Should we ship this?\n",
                     "> quoted\ncontinued\n2. step two\n\n    Should we ship this?\n",
                     "1. a\n\n<!-- c -->\n2. b\n\n    Should we ship this?\n"):
            self.assertTrue(any("Should we ship this?" in t for t, _ in self.found(body)), (body, self.found(body)))

    def test_backticks_in_an_html_block_hide_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        found = self.found("<div>\n`a? b?` c\n</div>\n")
        self.assertTrue(any(t.endswith("b?") for t, _ in found), found)

    def test_an_item_question_followed_by_more_lines_is_not_repeated(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("Open questions:\n- Should we cap it?\n  more context\n",
                     "Open questions:\n- Should we cap it?\n  ***\n", "Open questions:\n- Should we cap it?\n  ``\n"):
            self.assertEqual(find_questions(body, in_code=True), find_questions(body), body)

    def test_a_hidden_question_inside_an_item_is_marked(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("Open questions:\n- ```\n  Hidden?\n  ```\n  Shown\n"),
                         [("``` Shown", False), ("Hidden?", True)])

    def test_long_items_and_crowded_lines_stay_fast(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        crowded = " ".join(f"{a}{b}{c}?" for a in "abcdefghijklmnopqrstuvw" for b in "abcdefghijklmnopqrstuvw"
                           for c in "abcdefghijklmnopqrstuvw")
        for body in ("## Open questions\n- x" + "\n  x" * 16000, crowded):
            start = time.perf_counter()
            find_questions(body, in_code=True)
            self.assertLess(time.perf_counter() - start, 2.0)


class SecondReadingParsesLess(unittest.TestCase):
    def found(self, body: str) -> list[str]:
        return [question_text(q.question) for q in find_questions(body, in_code=True)]

    def check(self, body: str, want: str) -> None:
        self.assertTrue(any(want in t for t in self.found(body)), (body, self.found(body)))

    def test_a_question_sharing_a_tail_with_another_is_kept(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertIn("and so why?", self.found("<div>\nso why? `x. and so why?`\n</div>\n"))

    def test_backticks_across_table_cells_hide_no_question(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("| Cmd | Note |\n|---|---|\n| `a | Is it ok? | b` |\n",
                     "| a | b |\n|---|---|\n| `x | y |\n| Is it ok? | ` |\n",
                     "| a | b | c |\n|---|---|---|\n| `x` | `y | Is it ok? | `z` |\n"):
            self.check(body, "Is it ok?")

    def test_an_html_block_opened_on_an_item_line_parses_nothing(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("- <details>\n  `Is it ok?` yes\n", "1. <details><summary>Notes</summary>\n   `Is it ok?` yes\n",
                     "- <summary>`Is it ok?` yes\n"):
            self.check(body, "Is it ok?")

    def test_no_line_in_an_html_block_parses_markdown(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body, want in (("<details>\n- `Is it ok?` yes\n", "Is it ok?"), ("<details>\n## `Is it ok?` yes\n", "Is it ok?"),
                           ("<div>\n**Questions `a?` b:**\n", "a?")):
            self.check(body, want)

    def test_an_indented_marker_inside_a_paragraph_splits_no_code_span(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.check("`x\n    - y` Is it ok? `\n", "Is it ok?")
        self.check("` q0? \n    * `q1?`\n", "q1?")


class RoundFiveScenarios(unittest.TestCase):
    def test_a_question_in_a_quote_is_not_a_question(self) -> None:
        # @scenario inquisitor: A question in a quote is not a question
        body = "> Should we ship?\n> Or wait?\n"
        self.assertEqual(find_questions(body), [])
        self.assertEqual(find_questions(body, in_code=True), [])

    def test_a_quote_left_open_stays_in_the_question(self) -> None:
        # @scenario inquisitor: A quote left open stays in the question
        self.assertEqual(texts(find_questions('He asked "should retries back off?" twice.\n')),
                         ['He asked "should retries back off?'])

    def test_a_question_mark_before_an_underscore_ends_nothing(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        self.assertEqual(texts(find_questions("Is a?_b set? Yes.\n")), ["Is a?_b set?"])
        self.assertEqual(texts(find_questions("Should retries back off?) Fine.\n")), ["Should retries back off?"])
        self.assertEqual(texts(find_questions("Is a?b set\n")), [])

    def test_any_reference_to_a_question_mark_counts(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body in ("Ship it&#63;", "Ship it&#x3F;", "Ship it&#x3f;", "Ship it&#063;", "Ship it&quest;"):
            self.assertEqual(texts(find_questions(body)), ["Ship it?"], body)

    def test_a_list_item_of_dashes_is_a_thematic_break(self) -> None:
        # @scenario inquisitor: A list item of dashes is a thematic break
        found = find_questions("Open questions:\n- Retry policy\n- --\n- Cache size\n- - -\n- Log level\n")
        self.assertEqual([(f.item, question_text(f.question)) for f in found],
                         [(1, "Retry policy"), (2, "Cache size"), (3, "Log level")])

    def test_only_a_closed_fence_makes_a_code_block(self) -> None:
        # @scenario inquisitor: Only a closed fence makes a code block
        for body in ("Intro.\n\n```\nShould we ship?\n",):
            self.assertTrue(any("Should we ship?" in t for t in texts(find_questions(body))), body)
        self.assertEqual(find_questions("Intro.\n\n```\nShould we ship?\n```\n"), [])
        self.assertEqual(find_questions("Intro.\n\n    ```\n    Should we ship?\n    ```\n"), [])

    def test_a_question_in_code_is_found_by_the_plain_reading_alone(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = ("Intro.\n\n```\nShould we ship?\n```\n\n    Is it indented?\n\nRun `retry --why?` now.\n\n"
                "<!-- Should we wait? -->\n\nSee <!-- why? --> here.\n")
        self.assertEqual(texts(find_questions(body)), ["Run retry --why?", "See <!-- why?"])
        found = find_questions(body, in_code=True)
        self.assertEqual([(t, q.in_code) for t, q in zip(texts(found), found)],
                         [("Should we ship?", True), ("Is it indented?", True), ("Run retry --why?", False),
                          ("<!-- Should we wait?", True), ("See <!-- why?", False)])

    def test_the_hiding_reading_hides_a_comment_across_whole_lines(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = "Is it ready?\n<!-- Is it?\nReally? -->\nIs it done?\n"
        self.assertEqual(texts(find_questions(body)), ["Is it ready?", "Is it done?"])
        self.assertEqual([(t, q.in_code) for t, q in zip(texts(find_questions(body, in_code=True)),
                                                         find_questions(body, in_code=True))],
                         [("Is it ready?", False), ("<!-- Is it?", True), ("Really?", True), ("Is it done?", False)])

    def test_a_comment_sharing_a_line_with_text_is_text(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("Is it ready? <!-- why? --> ok\n", "<!-- note --> Is it shown?\n", "<!-- a\nb --> Is it shown?\n",
                     "Intro.\n\n<!-- c --> Is it shown?\n"):
            self.assertTrue(all(not q.in_code for q in find_questions(body, in_code=True)), body)
            self.assertTrue(any(t.endswith("shown?") or t.endswith("why?") for t in texts(find_questions(body))), body)


class PlainReadingHidesNothing(unittest.TestCase):
    def found(self, body: str) -> list[tuple[str, bool]]:
        return [(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)]

    def test_a_question_mark_markup_hides_comes_back_marked(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # Neither reading ends a sentence at a `?` in a link destination, a URL or an image
        # title, so qtext's backstop makes one ending there, and in_code=True returns it marked
        # (in_code True). A URL's `?` with a letter after it ends nothing, and a span title's
        # `?` ends a sentence the hiding reading finds, so neither is the backstop's.
        for body, want in (("See [a](Why?) ok.\n", "See [a](Why?"),
                           ("<!-- c --> See [the docs](https://x/search?)\n", "<!-- c --> See [the docs](https://x/search?"),
                           ('![a](b.png "Is it?") end\n', '![a](b.png "Is it?')):
            self.assertEqual(find_questions(body), [], body)
            self.assertEqual(self.found(body), [(want, True)], body)
        self.assertEqual(self.found("See https://x.io/search?q=1 now.\n"), [])
        self.assertEqual(self.found('Go <span title="Why?">x</span> on.\n'), [('Go <span title="Why?', False)])

    def test_a_question_in_a_code_span_reaches_the_union_with_its_hash(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("Run `retry --why?` now.\n"), [("Run retry --why?", False)])
        self.assertEqual(self.found("Use `x`? Or y?\n"), [("Use x?", False), ("Or y?", False)])

    def test_the_union_matches_questions_by_hash(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("Should we ship?\n\n```\nShould we ship?\n```\n\nShould we ship?\n"),
                         [("Should we ship?", False)])
        self.assertEqual(self.found("```\nIs it?\n```\n\n    Is it?\n"), [("Is it?", True)])

    def test_an_item_sentence_is_found_by_the_hiding_reading(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = "## Open questions\n\n- Use `x`? Or y?\n- Cap it? It is 5 now.\n"
        self.assertEqual(find_questions(body, in_code=True), find_questions(body))

    def test_code_and_comment_lines_read_alone_in_the_plain_reading(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("Intro\n```sh\nnpm ci\n```\nShould we pin it?\n"), [("Should we pin it?", False)])
        self.assertEqual(self.found("Intro\n<!--\nIs it hidden?\n-->\nShould we pin it?\n"),
                         [("<!-- Is it hidden?", True), ("Should we pin it?", False)])

    def test_a_break_in_an_item_hides_no_later_code_question_from_the_union(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = "## Open questions\n- Should we ship?\n  ***\nNotes follow.\n\n    Is the cache warm?\n"
        self.assertIn(("Is the cache warm?", True), self.found(body))

    def test_a_one_line_comment_of_closing_marks_ends_a_paragraph(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        # Both readings hide the comment, so in_code adds nothing.
        for body, want in (("Is it?\n<!-->\nIs that?\n", ["Is it?", "Is that?"]), ("a\n<!--->\nb? c\n", ["b?"])):
            self.assertEqual(texts(find_questions(body)), want)
            self.assertEqual(find_questions(body, in_code=True), find_questions(body))

    def test_every_hidden_code_line_reaches_the_plain_reading(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("    a\n    Is it?\n"), [("a Is it?", True)])
        self.assertEqual(self.found("```why? x\ncode\n```\n"), [("```why?", True)])

    def test_an_autolink_question_is_found_by_both_readings(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("See <https://x/a?> now.\n"), [("See https://x/a?", False)])

    def test_a_quote_after_a_space_in_a_link_tail_is_no_title(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        for body in ('Pick [x]( "one or two?") now\n', 'Pick [x](\n"one or two?") now\n', "Pick [x]( 'a or b?' ) now\n"):
            self.assertTrue(any(t.endswith("two?") or t.endswith("b?") for t in texts(find_questions(body))), body)

    def test_a_bracket_inside_a_tag_or_comment_opens_no_link(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        for body in ('<b title="[">x</b>](u "q1?")\n', '<b title="[x](u ">q1?</b>")\n', '<!-- [ -->](u "q1? or not")\n'):
            self.assertTrue(any("q1?" in t for t in texts(find_questions(body))), body)

    def test_a_link_spans_no_paragraph_break_inside_an_item(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ('## Questions\n- [x](\n\n  "q1?")\n', "## Questions\n- Pick [x](\n\n  'q1? or q2?')\n",
                     '## Questions\n- [x](\n  <!--\n  -->\n  "q1?")\n'):
            self.assertTrue(any("q1?" in t for t in texts(find_questions(body, in_code=True))), body)

    def test_code_lines_read_literally_in_the_plain_reading(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ('```\n[x](u "q1?")\n```\n', '    [x](u "q1?")\n', '<!--\n[x](u "q1?")\n-->\n'):
            self.assertTrue(any("q1?" in t and flag for t, flag in self.found(body)), (body, self.found(body)))

    def test_a_question_with_a_related_line_after_an_item_break_reaches_the_union(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        body = ("## Open questions\n- Should we ship?\n  ***\nNotes follow.\n\n    Is the cache warm?\n"
                "Related: https://x/1\n")
        self.assertIn(("Is the cache warm?", True), self.found(body))

    def test_an_autolink_reduces_to_its_address_and_ends_no_text_early(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(reduce_markup("<a@b.co>"), "a@b.co")
        self.assertEqual(texts(find_questions("Is it q?<http://x.y>\n")), ["Is it q?"])

    def test_a_comment_indented_under_a_paragraph_is_text(self) -> None:
        # @scenario inquisitor: A question's sentence ends at its question mark
        # The comment is text in the paragraph, so both readings find the question.
        body = "Some text here\n    <!-- note -->\n    Should we retry?\n"
        self.assertEqual(texts(find_questions(body)), ["Some text here <!-- note --> Should we retry?"])
        self.assertEqual(find_questions(body, in_code=True), find_questions(body))

    def test_every_question_mark_a_misread_hides_comes_back_marked(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # Each misread link swallows the `?` in its title, so neither reading ends a sentence
        # there, and qtext's backstop returns one ending in it.
        for body in ('## Questions\n- [a\n\n  b](u "Should we retry?")\n',
                     '## Questions\n- [a <!--\n\n  b -->](u "Should we retry?")\n',
                     '## Questions\n- [a `x\n\n  b` c](u "Should we retry?")\n',
                     'Intro <span title="<[">](u "Should we retry?") end.\n',
                     'Intro <span\ntitle="[">](u "Should we retry?") end.\n',
                     'Intro <![CDATA[ [ ]]>](u "Should we retry?") end.\n',
                     'Intro [x](u\u00a0"Should we retry?") end.\n',
                     '## Notes\n    [x](u "Should we retry?")\n', '---\n    [x](u "Should we retry?")\n',
                     '- a\n<!-- x -->\n    [x](u "Should we retry?")\n'):
            self.assertTrue(any(t.endswith("Should we retry?") for t, _ in self.found(body)), (body, self.found(body)))

    def test_a_question_mark_before_closing_emphasis_is_covered(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # A `_` or `*` closing emphasis after the `?` keeps either reading from ending a
        # sentence there, and qtext's backstop returns one, its text ending at the `?` or
        # taking the closing `_` too, depending on how the reading reduced the emphasis.
        for body, want in (("# H\n    <!--\n_q1?_\n    -->\n", "q1?"), ("---\n    <!-- note\nWhat about _this?_\n-->\n", "this?"),
                           ("<details>\n```\n\n# Should we _ship?_\n\n```\n", "ship?")):
            self.assertTrue(any(t.endswith(want) or t.endswith(want + "_") for t, _ in self.found(body)), (body, self.found(body)))

    def test_a_literal_mark_after_closing_emphasis_hides_no_question_mark(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # A `~` or `*` after the closing emphasis still leaves the `?` to qtext's backstop.
        for x in ("_q1?_~b", "_q1?_*b", "_q1?_**b", "_q1?_~~b", "__q1?__~b", "Ship _q1?_~maybe"):
            body = f"# H\n    <!--\n{x}\n    -->\n"
            self.assertTrue(any("q1?" in t for t, _ in self.found(body)), (body, self.found(body)))

    def test_comment_floods_stay_linear(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        for body in ("<!--" * 16384, "<!-- -" * 10923, "<!--\n" * 13107, "-->\n<!--\n" * 6553, "<!--\n" + "x -->\n" * 10922):
            start = time.perf_counter()
            find_questions(body, in_code=True)
            self.assertLess(time.perf_counter() - start, 2.0)


class BackstopAndLinkTails(unittest.TestCase):
    def found(self, body: str) -> list[tuple[str, bool]]:
        return [(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)]

    def test_the_backstop_skips_related_lines(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("a\nRelated: https://x?\n"), [])

    def test_a_backstop_sentence_starts_after_the_sentence_before_it(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # `&#63;` in a code span stays as written, so no reading takes it for a `?`; qtext's
        # backstop does, starting its sentence after the sentence or `?` before it.
        self.assertEqual(self.found("`a. b&#63;` c\n"), [("b?", True)])
        self.assertEqual(self.found("`a&#63; b&#63;`\n"), [("`a?", True), ("b?", True)])

    def test_a_character_reference_counts_as_a_mark(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # A `&#63;` in a code span, which no reading reads as a `?`, makes qtext's backstop
        # return a question ending there: "`?", from the line's previous `?` to it.
        self.assertIn(("`?", True), self.found("&#63; `&#63;` x. q?\n"))

    def test_an_item_claims_only_sentences_wholly_its_own_and_in_order(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertIn(("p <!-- q?", True), self.found("## Questions\n- p\n    <!-- q? -->\n  p <!-- q? z\n"))
        self.assertIn(("q?", True), self.found('## Questions\n- p q? [y](u "t\n  - q?")\n'))

    def test_a_link_tail_reads_whitespace_and_titles_as_commonmark_does(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(texts(find_questions("[a]( u) q?\n")), ["a q?"])
        self.assertEqual(texts(find_questions('[a](u "x\ny") q?\n')), ["a q?"])
        self.assertEqual(reduce_markup('[a](u "x\n\nb q?")'), '[a](u "x\n\nb q?")')

    def test_a_line_after_a_whole_line_comment_follows_a_break(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(find_questions("a\n<!-- x -->\n    q?\n"), [])
        self.assertEqual(self.found("a\n<!-- x -->\n    q?\n"), [("q?", True)])

    def test_an_item_keeps_a_paragraph_break_no_title_spans(self) -> None:
        # @scenario inquisitor: A post question's text drops its list marker and markup
        # Both readings read the item's text alike, so in_code adds nothing.
        body = '## Questions\n- [a](u\n\n  "t") q?\n'
        self.assertEqual(texts(find_questions(body)), ['[a](u "t") q?'])
        self.assertEqual(find_questions(body, in_code=True), find_questions(body))

    def test_code_keeps_its_markup_in_the_plain_reading(self) -> None:
        # @scenario inquisitor: A question in code is found by the plain reading alone
        self.assertEqual(self.found("```\n*q?*\n```\n"), [("*q?", True)])


class RoundEightScenarios(unittest.TestCase):
    def found(self, body: str) -> list[tuple[str, bool]]:
        return [(question_text(q.question), q.in_code) for q in find_questions(body, in_code=True)]

    def test_a_question_mark_both_readings_pass_over_is_still_vetted(self) -> None:
        # @scenario inquisitor: A question mark both readings pass over is still vetted
        # A `_` after the `?` keeps either reading from ending a sentence there, so the hiding
        # reading alone finds nothing. qtext's backstop then makes the question, which
        # in_code=True returns marked as the plain reading's alone (in_code True), though the
        # line holds no code.
        self.assertEqual(find_questions("Ship _v2?_now\n"), [])
        self.assertEqual(self.found("Ship _v2?_now\n"), [("Ship _v2?", True)])

    def test_a_question_mark_character_reference_reduces_to_a_question_mark(self) -> None:
        # @scenario inquisitor: Each kind of inline markup reduces to its text
        self.assertEqual(texts(find_questions("Ship it&#63;\n")), ["Ship it?"])

    def test_a_plain_reading_sentence_inside_a_section_item_is_that_items(self) -> None:
        # @scenario inquisitor: A plain-reading sentence inside a section item is that item's
        self.assertEqual(self.found("## Open questions\n- Ship it? Or wait?\n"),
                         [("Ship it? Or wait?", False)])


class Mentions(unittest.TestCase):
    """mentions() leans toward finding a mention: only a mention on a `>`
    line, or in code the hiding reading hides, does not count."""

    def names(self, body: str) -> list[str]:
        return [m.name for m in mentions(body)]

    def test_every_login_counts_outside_hidden_code_and_quotes(self) -> None:
        self.assertEqual(self.names("Ask @alice, `@bob`, [@carol](https://x/) <!-- @dave -->"),
                         ["alice", "bob", "carol", "dave"])
        self.assertEqual(self.names("_cc @alice_ and **@bob**"), ["alice", "bob"])
        self.assertEqual(self.names("> @alice said\n\n```\n@bob\n```\n\n    @carol\n\n"
                                    "<!--\n@dave\n-->\nThen @erin."), ["erin"])

    def test_what_is_no_mention(self) -> None:
        self.assertEqual(self.names("Mail a@alice.com, see x/@alice, ask @o/devs, @@alice, @bob-"),
                         [])
        # An HTML comment indented under a section's item, filling its own
        # line, is hidden like one at the line's start.
        self.assertEqual(self.names("Open questions:\n\n- Should we X?\n    <!-- @alice -->\n"), [])

    def test_discord_user_mentions(self) -> None:
        self.assertEqual(self.names("Ask <@123> or <@!456>, not <@&789>"), ["123", "456"])

    def test_discord_shows_comments_and_indented_text(self) -> None:
        body = "Hi.\n\n<!-- <@1> -->\n\n    <@2>\n\n```\n<@3>\n```"
        self.assertEqual(self.names(body), [])
        self.assertEqual([m.name for m in mentions(body, discord=True)], ["1", "2"])

    def test_discord_shows_tilde_fences(self) -> None:
        body = "Hi.\n\n~~~\n<@1>\n~~~"
        self.assertEqual(self.names(body), [])
        self.assertEqual([m.name for m in mentions(body, discord=True)], ["1"])

    def test_lone_carriage_returns_end_lines(self) -> None:
        self.assertEqual(mentions("a\rb\r@bob"), [Mention("bob", 2)])

    def test_lines_are_the_post_s(self) -> None:
        body = "Open questions:\n\n- Should retries back off?\n\n    Ask @alice."
        self.assertEqual(mentions(body), [Mention("alice", 4)])
        [found] = find_questions(body)
        self.assertEqual(found.at, (2, 4))
        self.assertIn(4, found.at)


if __name__ == "__main__":
    unittest.main()
