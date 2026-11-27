"""Tests for config.load, the inquisitor's configuration, and
config.origin_repository, which names each lore clone's repository."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from common import Refused


class Load(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.patch.start()
        self.path = self.home / ".config" / "shared-skills" / "inquisitor.json"

    def tearDown(self) -> None:
        self.patch.stop()
        subprocess.run(["rm", "-rf", str(self.home)], check=True)

    def write(self, data: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_reads_its_keys_and_keeps_the_rest(self) -> None:
        # @scenario answer-service: The answer service reads only its keys of the configuration
        clone = self.home / "lore"
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "remote", "add", "origin",
                        "git@github.com:o/lore.git"], check=True)
        service = {"github": {"relay": "relay", "subscriptions": ["o", "o/api"]},
                   "discord": {"relay": "bot", "subscriptions": [{"id": "1"}], "user": "2"}}
        self.write({"login": "alice", "other": {"x": 1},
                    "lore": [{"path": "~/lore", "owners": ["o", "../x"], "repos": ["o/api"]},
                             {"owners": ["o"]}, "junk"],
                    "answer_service": service})
        c = config.load()
        self.assertEqual(c.login, "alice")
        self.assertEqual(c.lore, (config.LoreRepo(path=str(clone), owners=("o",), repos=("o/api",),
                                                  repository="o/lore"),))
        self.assertEqual(c.answer_service, service)
        self.assertEqual(c.raw["other"], {"x": 1})
        for url, want in (("https://github.com/o/lore.git", "o/lore"),
                          ("https://github.com/o/lore", "o/lore"),
                          ("ssh://git@github.com/o/lore.git", "o/lore"),
                          ("https://gitlab.com/o/lore.git", None)):
            subprocess.run(["git", "-C", str(clone), "remote", "set-url", "origin", url], check=True)
            self.assertEqual(config.origin_repository(clone), want, url)
        subprocess.run(["git", "-C", str(clone), "remote", "remove", "origin"], check=True)
        self.assertIsNone(config.origin_repository(clone))

    def test_missing_and_malformed(self) -> None:
        # @scenario answer-service: The answer service reads only its keys of the configuration
        self.assertEqual(config.load(), config.Config())
        self.write({"login": "alice", "lore": [{"path": ""}, {"path": 5}, {"path": ["x"]}]})
        self.assertEqual(config.load().lore, ())
        self.write({"login": "alice/../admin", "lore": "x"})
        c = config.load()
        self.assertIsNone(c.login)
        self.assertEqual(c.lore, ())
        self.path.write_text("[1]", encoding="utf-8")
        with self.assertRaises(Refused):
            config.load()
        self.path.write_text("{", encoding="utf-8")
        with self.assertRaises(Refused):
            config.load()


if __name__ == "__main__":
    unittest.main()
