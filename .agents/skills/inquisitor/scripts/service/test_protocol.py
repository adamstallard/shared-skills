"""Tests for protocol: each worked example in fixtures/service/ fits its
request type, each request type has an example, and no request type but
the preview carries a rephrasing. The core's handling of a rephrasing is
tested with relay.py."""

import json
import typing
import unittest
from pathlib import Path
from typing import Any, cast, get_args

import protocol

EXAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "service" / "examples.json"


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


if __name__ == "__main__":
    unittest.main()
