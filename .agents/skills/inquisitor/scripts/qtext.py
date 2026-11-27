"""A question's text and hash, inline markup, sentences, terms, and the
questions in a post's body.

One module, because the first call, the post hook, the log command, the
answer service and every reader of a questions branch must build a
question's text and hash the same way (inquisitor spec: *A question's text
and hash are built one way*).

Owned by P2, except find_questions, which P3 builds (task 2.5).
Standard library only.
"""

from dataclasses import dataclass, field
from typing import Literal

from common import NotBuilt

# The fixed line prefixes a question may carry after its first line, which
# its text and hash leave out (inquisitor spec: *A question's text and hash
# are built one way*). Each is matched on the line with its whitespace
# trimmed.
RELATED_PREFIX = "Related: "
CONCERNS_PREFIX = "Concerns: "
RECORDED_PREFIX = "Recorded: "
NOT_RECORDED_PREFIX = "Not recorded: "
PERSON_REQUIRED_FORMAT = "Inquisitor: a person must decide this (required by {skill})."
UNTAGGED_LINE = ("Inquisitor: no one with authority to decide this could be tagged; "
                 "name deciders in .inquisitor/reviewers.")

LineKind = Literal["related", "tag", "person-required", "concerns", "record"]


@dataclass(frozen=True)
class Question:
    """One question as asked, before its text is built.

    kind "picker": question is the picker's `question` field, options its
    options' labels. kind "post": question is a list item without its
    marker, or a sentence. kind "text": anything else, such as a whole
    Linear or Discord message, taken as one part.
    """

    kind: Literal["picker", "post", "text"]
    question: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoundQuestion:
    """A question find_questions found in a post's body.

    item is its number among the open-questions section's items, counting
    from 1, or None for a sentence outside any section. deferred is True for
    an item of a section begun by a deferral label. lines are the extra
    lines after it (related-decision, person-required, concerns, tag), as
    written.
    """

    question: Question
    item: int | None
    deferred: bool
    lines: tuple[str, ...] = field(default=())


def reduce_markup(text: str) -> str:
    """Inline markup reduced to its text (inquisitor spec: *Inline markup is
    reduced to its text one way*).

    TODO(P2): build it."""
    raise NotBuilt("P2", "reduce_markup")


def line_kind(line: str) -> LineKind | None:
    """Which of the left-out lines `line` is, matched trimmed, or None.

    A tag line holds only one `@login` mention, or is UNTAGGED_LINE. A
    related-decision line is RELATED_PREFIX and one URL with no spaces.

    TODO(P2): build it."""
    raise NotBuilt("P2", "line_kind")


def question_text(question: Question) -> str:
    """The question's text, in the spec's four steps: drop left-out lines,
    take its parts with markup reduced, make whitespace runs one space and
    trim each part, join the parts with one LF.

    TODO(P2): build it."""
    raise NotBuilt("P2", "question_text")


def question_hash(text: str) -> str:
    """SHA-256 of the text as UTF-8, lowercase hex.

    TODO(P2): build it."""
    raise NotBuilt("P2", "question_hash")


def sentences(paragraph: str) -> list[str]:
    """A paragraph's sentences (inquisitor spec: *A sentence and a question's
    terms are defined*).

    TODO(P2): build it."""
    raise NotBuilt("P2", "sentences")


def terms(text: str) -> set[str]:
    """A question's terms: the words of its text split at every character
    that is neither a Unicode letter nor a digit, lowercased.

    TODO(P2): build it."""
    raise NotBuilt("P2", "terms")


def find_questions(body: str) -> list[FoundQuestion]:
    """The questions in a post's body: each item of an open-questions
    section and each other sentence ending in `?`, none in code, `>` lines
    or prose's footer (inquisitor spec: *A question in a post is a listed
    item or a sentence ending in a question mark*). The post hook and the
    first call both call this; the answer service calls it on a bot's
    Linear or Discord message.

    TODO(P3): build it (task 2.5)."""
    raise NotBuilt("P3", "find_questions")
