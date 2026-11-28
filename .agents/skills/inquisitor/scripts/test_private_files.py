"""Tests for private_files: reading only private input files, and writing
records at mode 0600 in a private directory."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from common import Refused
from private_files import read_private, write_private


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class ReadPrivate(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def write(self, path: Path, file_mode: int) -> Path:
        path.write_text('{"version": 1}', encoding="utf-8")
        os.chmod(path, file_mode)
        return path

    def test_refuses_a_readable_file(self) -> None:
        # @scenario inquisitor: A questions file others can read is refused
        # @scenario inquisitor: A log command input others can read is refused
        f = self.write(self.dir / "q.json", 0o644)
        with self.assertRaises(Refused) as cm:
            read_private(str(f))
        self.assertIn("mode 0600 in a private directory", str(cm.exception))
        self.assertIn("mktemp -d", str(cm.exception))

        os.chmod(f, 0o600)
        self.assertEqual(read_private(str(f)), '{"version": 1}')

        os.chmod(self.dir, 0o755)
        with self.assertRaises(Refused):
            read_private(str(f))
        os.chmod(self.dir, 0o700)

        tree = self.dir / "tree"
        tree.mkdir(mode=0o700)
        subprocess.run(["git", "init", "-q", str(tree)], check=True)
        inner = tree / "private"
        inner.mkdir(mode=0o700)
        with self.assertRaises(Refused) as cm:
            read_private(str(self.write(inner / "q.json", 0o600)))
        self.assertIn("git working tree", str(cm.exception))

        with self.assertRaises(Refused):
            read_private(str(self.dir / "absent.json"))
        fifo = self.dir / "fifo.json"
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(Refused):
            read_private(str(fifo))

    def test_link_judged_by_target(self) -> None:
        # @scenario inquisitor: A questions file others can read is refused
        shared = Path(tempfile.mkdtemp())
        try:
            os.chmod(shared, 0o755)
            target = self.write(shared / "q.json", 0o600)
            link = self.dir / "link.json"
            link.symlink_to(target)
            with self.assertRaises(Refused):
                read_private(str(link))
        finally:
            subprocess.run(["rm", "-rf", str(shared)], check=True)


class WritePrivate(unittest.TestCase):
    def test_records_have_mode_0600(self) -> None:
        # @scenario inquisitor: The records have mode 0600
        root = Path(tempfile.mkdtemp())
        try:
            path = root / "state" / "inquisitor" / "verdicts" / "r.json"
            write_private(path, "{}")
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")
            self.assertEqual(mode(path), 0o600)
            for d in (path.parent, path.parent.parent, path.parent.parent.parent):
                self.assertEqual(mode(d), 0o700, d)
            write_private(path, "{\"a\": 1}")
            self.assertEqual(path.read_text(encoding="utf-8"), "{\"a\": 1}")
            self.assertEqual(mode(path), 0o600)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["r.json"])
        finally:
            subprocess.run(["rm", "-rf", str(root)], check=True)


if __name__ == "__main__":
    unittest.main()


class Unusual(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def test_failed_write_leaves_nothing(self) -> None:
        # @scenario inquisitor: The records have mode 0600
        target = self.dir / "r.json"
        target.mkdir()
        with self.assertRaises(OSError):
            write_private(target, "{}")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["r.json"])


class Directories(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def test_existing_open_directory_is_made_private(self) -> None:
        # @scenario inquisitor: The records have mode 0600
        verdicts = self.dir / "verdicts"
        verdicts.mkdir(mode=0o755)
        os.chmod(verdicts, 0o755)
        write_private(verdicts / "r.json", "x")
        self.assertEqual(mode(verdicts), 0o700)

    def test_concurrent_first_writes(self) -> None:
        # @scenario inquisitor: The records have mode 0600
        import threading
        errors: list[BaseException] = []
        for trial in range(30):
            base = self.dir / f"t{trial}" / "a" / "b"
            barrier = threading.Barrier(6)

            def work(i: int, base: Path = base, barrier: threading.Barrier = barrier) -> None:
                barrier.wait()
                try:
                    write_private(base / f"f{i}", "x")
                except BaseException as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(errors, [])
