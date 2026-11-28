"""Tests for service/protocol.py against fixtures/service/examples.json.
Each example's request may hold only the fields its command's request
type declares, and must hold every field that type requires. Each
command a request type carries needs an example. Only PreviewRequest has
a `revision` field, the person's rephrasing of a question. In
examples.json, the turn 2 request of the example `judge.turn-end` is in
the example `poll.judge-resent`'s list too, so the mod needs no queue of
its own. These tests
cover the protocol's shapes only; how the answer service's core keeps a
rephrasing belongs in the tests of service/relay.py."""

import json
import typing
import unittest
from pathlib import Path
from typing import Any, cast, get_args

from service import protocol

EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "service" / "examples.json"


def request_types() -> dict[str, type]:
    """Each request type by the command it carries."""
    by_command: dict[str, type] = {}
    for kind in get_args(protocol.Request):
        hints = typing.get_type_hints(kind)
        for command in get_args(hints["command"]):
            by_command[command] = kind
    return by_command


class Examples(unittest.TestCase):
    def test_each_example_request_fits_its_type(self) -> None:
        # @scenario answer-service: A rephrasing is kept only with the post that carried it
        # The protocol's part of that scenario: preview.revised, the only
        # example carrying a rephrasing, is a request the types allow.
        examples = cast(dict[str, dict[str, Any]], json.loads(EXAMPLES.read_text()))
        types = request_types()
        for name, example in examples.items():
            request = cast(dict[str, Any], example["request"])
            kind = types.get(request["command"])
            self.assertIsNotNone(kind, f"{name}: no request type carries {request['command']!r}")
            assert kind is not None
            fields = set(typing.get_type_hints(kind))
            required = set(cast(frozenset[str], getattr(kind, "__required_keys__")))
            self.assertLessEqual(set(request), fields, name)
            self.assertLessEqual(required, set(request), name)
        self.assertLessEqual(set(types), {cast(str, e["request"]["command"]) for e in examples.values()},
                             "a request type has no example")

    def test_only_a_preview_carries_a_rephrasing(self) -> None:
        # @scenario answer-service: A rephrasing is kept only with the post that carried it
        # The protocol's part of that scenario: no request but a preview
        # can bring the core a rephrasing to keep.
        carriers = [k.__name__ for k in get_args(protocol.Request) if "revision" in typing.get_type_hints(k)]
        self.assertEqual(carriers, ["PreviewRequest"])
        example = json.loads(EXAMPLES.read_text())["preview.revised"]
        revision = example["request"]["revision"]
        post = example["response"]["post"]
        self.assertIn(f"\n\nRephrased question: {revision['text']}\nDiscussion: {revision['summary']}\n", post)

    def test_a_turn_2_request_comes_back_at_the_next_poll(self) -> None:
        # @scenario answer-service: A judging prompt that never reaches the model is put before it again
        # The protocol's part of that scenario: a later poll lists the
        # turn 2 request that judge.turn-end gave as next, so the mod
        # need keep no queue of its own.
        examples = json.loads(EXAMPLES.read_text())
        given = examples["judge.turn-end"]["response"]["next"]
        self.assertEqual(given["turn"], 2)
        self.assertIn(given, examples["poll.judge-resent"]["response"]["judge"])


if __name__ == "__main__":
    unittest.main()
