"""Tests of install_mod: install-mod and uninstall-mod, run against a home
folder of the test's own."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import install_mod


class InstallMod(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.mod_link = self.home / ".claude" / "skills" / "inquisitor-answer-mod"
        self.answer_link = self.home / ".local" / "bin" / "answer"

    def run_command(self, fn: Callable[[], int], path: str = "/usr/bin:/bin") -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "PATH": path}), contextlib.redirect_stdout(out):
            status = fn()
        return status, out.getvalue()

    def test_install_links_both_and_says_bin_is_off_path(self) -> None:
        # @scenario answer-service: The script installs the answer mod
        status, out = self.run_command(install_mod.install)
        self.assertEqual(status, 0)
        self.assertEqual(os.path.realpath(self.mod_link), os.path.realpath(install_mod.MOD))
        self.assertEqual(os.path.realpath(self.answer_link), os.path.realpath(install_mod.LAUNCHER))
        self.assertTrue((install_mod.MOD / "hooks" / "hooks.json").is_file())
        self.assertTrue(os.access(install_mod.LAUNCHER, os.X_OK))
        self.assertIn(".local/bin is not on PATH", out)

    def test_install_on_path_says_nothing_of_path_and_runs_twice(self) -> None:
        # @scenario answer-service: The script installs the answer mod
        bin_dir = self.home / ".local" / "bin"
        status, out = self.run_command(install_mod.install, f"{bin_dir}:/usr/bin")
        self.assertEqual(status, 0)
        self.assertNotIn("not on PATH", out)
        status, out = self.run_command(install_mod.install, f"{bin_dir}:/usr/bin")
        self.assertEqual(status, 0)
        self.assertIn("already installed", out)

    def test_install_leaves_another_answer_command_alone(self) -> None:
        # @scenario answer-service: The script leaves another answer command alone
        self.answer_link.parent.mkdir(parents=True)
        self.answer_link.write_text("#!/bin/sh\necho mine\n")
        status, out = self.run_command(install_mod.install)
        self.assertNotEqual(status, 0)
        self.assertFalse(self.answer_link.is_symlink())
        self.assertEqual(self.answer_link.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn("answer was not installed", out)
        # The mod's link is made all the same.
        self.assertTrue(self.mod_link.is_symlink())

    def test_install_leaves_a_link_elsewhere_alone(self) -> None:
        # @scenario answer-service: The script leaves another answer command alone
        # The same rule at the mod's path: something else there is left alone.
        self.mod_link.parent.mkdir(parents=True)
        self.mod_link.symlink_to(self.home)
        status, out = self.run_command(install_mod.install)
        self.assertNotEqual(status, 0)
        self.assertEqual(os.readlink(self.mod_link), str(self.home))
        self.assertIn("the answer mod was not installed", out)

    def test_a_relative_link_to_the_mod_counts_as_its_own(self) -> None:
        # @scenario answer-service: The script installs the answer mod
        # @scenario answer-service: Uninstalling removes only the script's links
        self.mod_link.parent.mkdir(parents=True)
        self.mod_link.symlink_to(os.path.relpath(install_mod.MOD, self.mod_link.parent.resolve()))
        status, out = self.run_command(install_mod.install)
        self.assertEqual(status, 0)
        self.assertIn("already installed", out)
        self.run_command(install_mod.uninstall)
        self.assertFalse(self.mod_link.is_symlink())

    def test_uninstall_removes_only_its_links(self) -> None:
        # @scenario answer-service: Uninstalling removes only the script's links
        self.run_command(install_mod.install)
        self.answer_link.unlink()
        self.answer_link.write_text("mine\n")
        status, out = self.run_command(install_mod.uninstall)
        self.assertEqual(status, 0)
        self.assertFalse(self.mod_link.is_symlink() or self.mod_link.exists())
        self.assertEqual(self.answer_link.read_text(), "mine\n")
        self.assertIn("Left", out)


if __name__ == "__main__":
    unittest.main()
