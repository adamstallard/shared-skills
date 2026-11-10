#!/usr/bin/env python3
"""Tests that no git setting outside the repository's tracked files changes
what `prose check` lists, for a plain commit or a merge: each setting that
can reshape a diff is set to a value other than git's default, and the
listing must come out as it does with none set.

Standard library only:

    python3 test_diff_config.py
"""

import contextlib
import os
import pathlib
import stat
import unittest

from prose_test_support import Repo, prose

# Two texts on which git's diff algorithms disagree: myers adds line 8,
# histogram and patience line 7.
ALG_BEFORE = "x\ny\nz\n}\ny\n}\nx\nz\nw\n\n\n"
ALG_AFTER = "y\n}\ny\n}\nx\nz\n\nw\n"
# Texts whose hunks the indent heuristic slides.
SLIDE_BASE = ("f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\n  y\nf() {\n\nf() {\n"
              "f() {\n  x\n  x\n  y\n")
SLIDE_SIDE = ("f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\nf() {\n\nf() {\nf() {\n"
              "  x\n  x\n  y\n  x\n")
SLIDE_MAIN = ("f() {\n\n\n  y\n}\n}\n  x\n  y\n  x\ng() {\n}\n}r5\n}\n  y\nf() {\nf() {\nf() {\n"
              "  x\n  x\n  y\n")
SLIDE_RESULT = ("f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\nf() {\n\nf() {\nf() {\n"
                "  x\n  y\n  x")
# A settings key meaning the repository's .git/info/attributes file.
INFO = "info/attributes"
LINES = "".join(f"Line {n} says one thing.\n" for n in range(12))
ROWS = LINES.replace("Line", "Row")
CODE = "# The first comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"


def edit(text, old, new):
    assert old in text
    return text.replace(old, new, 1)


def replace_blob(repo, path):
    """Replace HEAD's blob of path with one that differs at line 10, with a
    replace ref, which git's diffs follow by default."""
    old = repo.git("rev-parse", f"HEAD:{path}").strip()
    new = repo.git("hash-object", "-w", "--stdin",
                   stdin=edit(LINES, "Line 9 ", "Replaced line 9 ")).strip()
    repo.git("replace", old, new)


def gitlink(repo, path, digit):
    """Stage a submodule entry at path, pointing at a commit id made of
    digit, as a submodule bump would."""
    repo.git("update-index", "--add", "--cacheinfo", f"160000,{digit * 40},{path}")


def build_plain():
    """A repository with a staged change that every setting could reshape:
    two docs whose added lines depend on the diff algorithm and the indent
    heuristic, two docs renamed and edited (rename detection and its limit),
    a comment edit, a doc with CRLF line ends, a doc whose HEAD blob a
    replace ref swaps (replace refs), a deleted doc and a submodule bump at
    a doc path (both listed with no lines)."""
    repo = Repo()
    repo.write("alg.md", ALG_BEFORE)
    repo.write("slide.md", SLIDE_BASE)
    repo.write("a.md", LINES)
    repo.write("b.md", ROWS)
    repo.write("code.py", CODE)
    repo.write("crlf.md", LINES.replace("\n", "\r\n"))
    repo.write("replaced.md", LINES)
    repo.write("gone.md", LINES)
    gitlink(repo, "sub.md", "1")
    repo.commit("base\n")
    replace_blob(repo, "replaced.md")
    repo.write("replaced.md", edit(LINES, "Line 5 ", "Line five "))
    repo.git("rm", "-q", "gone.md")
    gitlink(repo, "sub.md", "2")
    repo.write("alg.md", ALG_AFTER)
    repo.write("slide.md", SLIDE_RESULT)
    repo.git("mv", "a.md", "a2.md")
    repo.git("mv", "b.md", "b2.md")
    repo.write("a2.md", edit(LINES, "Line 9 ", "Line nine "))
    repo.write("b2.md", ROWS + "Extra.\n")
    repo.write("code.py", edit(CODE, "second comment", "rewritten comment"))
    repo.write("crlf.md", edit(LINES, "Line 4 ", "Line four ").replace("\n", "\r\n"))
    return repo


def build_merge():
    """A repository with a merge in progress whose listing every setting
    could reshape: hunks the indent heuristic slides (slide.md), a doc the
    diff algorithms disagree on (alg.md), two docs one branch renamed and
    edited while the other edited one (a2.md, b2.md), a comment edit
    (code.py), a doc whose blob a replace ref swaps (replaced.md) and a
    submodule bump at a doc path (sub.md)."""
    repo = Repo()
    repo.git("symbolic-ref", "HEAD", "refs/heads/main")
    repo.write("slide.md", SLIDE_BASE)
    repo.write("alg.md", ALG_BEFORE)
    repo.write("a.md", LINES)
    repo.write("b.md", ROWS)
    repo.write("code.py", CODE)
    repo.write("replaced.md", LINES)
    gitlink(repo, "sub.md", "1")
    repo.commit("base\n")
    replace_blob(repo, "replaced.md")
    repo.git("checkout", "-q", "-b", "side")
    repo.write("slide.md", SLIDE_SIDE)
    repo.git("mv", "a.md", "a2.md")
    repo.git("mv", "b.md", "b2.md")
    repo.write("a2.md", LINES + "Side's extra.\n")
    repo.write("b2.md", ROWS + "Extra.\n")
    repo.commit("side\n")
    repo.git("checkout", "-q", "main")
    repo.write("slide.md", SLIDE_MAIN)
    repo.write("a.md", edit(LINES, "Line 2 ", "Main's line 2 "))
    repo.commit("main\n")
    repo.git("merge", "-q", "--no-commit", "--no-ff", "-s", "ours", "side")
    # `-s ours` keeps main's tree; take side's renames.
    repo.git("rm", "-q", "a.md", "b.md")
    repo.write("slide.md", SLIDE_RESULT)
    repo.write("alg.md", ALG_AFTER)
    repo.write("a2.md", edit(edit(LINES, "Line 2 ", "Main's line 2 "), "Line 9 ", "The merge's 9 ")
               + "Side's extra.\n")
    repo.write("b2.md", ROWS + "Extra.\n")
    repo.write("code.py", edit(CODE, "second comment", "merge's comment"))
    repo.write("replaced.md", edit(LINES, "Line 5 ", "The merge's line 5 "))
    gitlink(repo, "sub.md", "2")
    return repo


def listing(repo):
    """What `prose check` lists: prose_in on the commit's parents, reading
    each staged file as check reads it."""
    root = str(repo.path)
    return prose.prose_in(root, prose.commit_parents(root),
                          lambda path: prose.read_staged(path, root))


@contextlib.contextmanager
def environment(**values):
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class PlainTextconv(unittest.TestCase):
    """A textconv driver does not shift a plain commit's line numbers."""

    def test_a_textconv_driver_leaves_the_staged_files_line_numbers(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("doc.md", LINES)
        repo.write("code.py", CODE)
        repo.commit("base\n")
        repo.git("config", "diff.twice.textconv", "sed p")
        (repo.path / ".git" / "info" / "attributes").write_text("* diff=twice\n")
        repo.write("doc.md", edit(LINES, "Line 5 ", "Line five "))
        repo.write("code.py", edit(CODE, "second comment", "rewritten comment"))
        items, _ = listing(repo)
        self.assertEqual({item.path: item.spans for item in items if item.path},
                         {"doc.md": ((6, 6),), "code.py": ((7, 7),)})


class StagedRead(unittest.TestCase):
    """The staged file is found by the path the diff printed."""

    def spans(self, repo):
        items, _ = listing(repo)
        return {item.path: item.spans for item in items if item.path}

    def test_a_decomposed_file_name_is_read_with_precomposed_unicode_on(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("a.py", "x = 1\n")
        repo.commit("base\n")
        name = "e\u0301.py"
        blob = repo.git("hash-object", "-w", "--stdin", stdin="x = 1\n# A fine comment.\n").strip()
        repo.git("-c", "core.precomposeUnicode=false", "update-index", "--add",
                 "--cacheinfo", f"100644,{blob},{name}")
        repo.git("config", "core.precomposeUnicode", "true")
        self.assertEqual(self.spans(repo), {name: ((2, 2),)})


class WhatTheListingsAre(unittest.TestCase):
    """The listings the settings test compares against, asserted outright,
    so a pin set to some other value than git's default is caught."""

    def spans(self, repo):
        items, _ = listing(repo)
        return {item.path: (item.note, item.deleted, item.spans) for item in items if item.path}

    def test_the_plain_listing(self):
        repo = build_plain()
        self.addCleanup(repo.cleanup)
        self.assertEqual(self.spans(repo), {
            "alg.md": ("changed", False, ((8, 8),)),  # myers; histogram says 7
            "slide.md": ("changed", False, ((21, 21),)),
            "a2.md": ("changed", False, ((10, 10),)),  # renamed, not added
            "b2.md": ("changed", False, ((13, 13),)),
            "code.py": ("comment", False, ((7, 7),)),
            "crlf.md": ("changed", False, ((5, 5),)),
            # HEAD's blob is replaced at line 10, and the diff follows that.
            "replaced.md": ("changed", False, ((6, 6), (10, 10))),
            "gone.md": ("changed", True, ()),
            "sub.md": ("changed", False, ()),
        })

    def test_the_merge_listing(self):
        repo = build_merge()
        self.addCleanup(repo.cleanup)
        self.assertEqual(self.spans(repo), {
            "slide.md": ("changed", False, ((13, 13), (16, 16), (21, 21))),
            "alg.md": ("changed", False, ((8, 8),)),
            "a2.md": ("changed", False, ((10, 10), (13, 13))),
            "code.py": ("comment", False, ((7, 7),)),
            "replaced.md": ("changed", False, ((6, 6), (10, 10))),
            "sub.md": ("changed", False, ()),
        })

    def test_a_staged_gitattributes_applies(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("doc.md", LINES)
        repo.commit("base\n")
        repo.write(".gitattributes", "*.md -diff\n")
        repo.write("doc.md", edit(LINES, "Line 5 ", "Line five "))
        self.assertEqual(self.spans(repo)["doc.md"], ("changed", False, ()))


class Environment(unittest.TestCase):
    """Both git_env functions drop the same variables and turn system
    attributes off."""

    def test_git_env_drops_what_changes_a_diff(self):
        # Only GIT_ATTR_NOSYSTEM turns system-wide attributes off,
        # and a test cannot write the system file to see the effect.
        scan = prose.scanner()
        with environment(**{name: "x" for name in scan.UNSET_ENV}):
            for label, env in (("comment_scan", scan.git_env()), ("prose", prose.git_env())):
                with self.subTest(git_env=label):
                    self.assertFalse(set(scan.UNSET_ENV) & set(env))
                    self.assertEqual(env["GIT_ATTR_NOSYSTEM"], "1")


class SettingsCannotChangeTheListing(unittest.TestCase):
    """Each setting, set away from git's default, leaves both listings as
    they are with no setting."""

    @classmethod
    def setUpClass(cls):
        cls.repos = {"plain": build_plain(), "merge": build_merge()}
        cls.expected = {name: listing(repo) for name, repo in cls.repos.items()}
        cls.files = pathlib.Path(cls.repos["plain"].path.parent) / f"{cls.repos['plain'].path.name}-files"
        cls.files.mkdir()
        junk = cls.files / "junk-diff"
        junk.write_text("#!/bin/sh\necho 'diff --git a/x b/x'\necho '@@ -1 +1,40 @@'\n")
        junk.chmod(junk.stat().st_mode | stat.S_IEXEC)
        (cls.files / "order").write_text("z*\ncode.py\n*.md\n")
        cls.attributes = {
            "nodiff": "* -diff\n",
            "driver": "* diff=drv\n",
            "crlf": "* text eol=crlf\n",
        }
        for name, text in cls.attributes.items():
            (cls.files / name).write_text(text)

    @classmethod
    def tearDownClass(cls):
        for repo in cls.repos.values():
            repo.cleanup()
        import shutil
        shutil.rmtree(cls.files, ignore_errors=True)

    def settings(self):
        """(label, {config key: value}, {environment variable: value})."""
        files, junk = self.files, str(self.files / "junk-diff")
        attributes = lambda name: str(files / name)
        config = [
            {"diff.context": "10"},
            {"diff.interHunkContext": "10"},
            {"diff.algorithm": "histogram"},
            {"diff.algorithm": "patience"},
            {"diff.algorithm": "minimal"},
            {"diff.indentHeuristic": "false"},
            {"diff.renames": "false"},
            {"diff.renames": "copies"},
            {"diff.renameLimit": "1"},
            {"diff.noprefix": "true"},
            {"diff.mnemonicPrefix": "true"},
            {"diff.srcPrefix": "s/", "diff.dstPrefix": "d/"},
            {"diff.relative": "true"},
            {"diff.orderFile": str(files / "order")},
            {"diff.suppressBlankEmpty": "true"},
            {"diff.wsErrorHighlight": "all"},
            {"diff.colorMoved": "zebra"},
            {"diff.external": junk},
            {"diff.ignoreSubmodules": "all"},
            {"diff.dirstat": "lines,cumulative"},
            {"diff.statNameWidth": "5"},
            {"core.quotePath": "true"},
            {"color.diff": "always"},
            {"color.ui": "always"},
            {"core.autocrlf": "true"},
            {"core.eol": "crlf"},
            {"core.safecrlf": "true"},
            {"core.whitespace": "trailing-space,cr-at-eol,tab-in-indent"},
            {"core.bigFileThreshold": "10"},
            {"core.useReplaceRefs": "false"},
            {"core.attributesFile": attributes("nodiff")},
            {"core.attributesFile": attributes("crlf")},
            {"core.attributesFile": attributes("driver"), "diff.drv.textconv": "sed p"},
            {"core.attributesFile": attributes("driver"), "diff.drv.binary": "true"},
            # A driver bound in the repository's own attributes, so its
            # settings reach the diff rather than stopping at the nulled
            # personal file. (diff.drv.binary there is a known gap.)
            {INFO: "* diff=drv\n", "diff.drv.textconv": "sed p"},
            {INFO: "* diff=drv\n", "diff.drv.algorithm": "histogram"},
            {INFO: "* diff=drv\n", "diff.drv.xfuncname": "^x"},
            {INFO: "* diff=drv\n", "diff.drv.command": junk},
        ]
        environment_values = [
            {"GIT_NO_REPLACE_OBJECTS": "1"},
            {"GIT_REPLACE_REF_BASE": "refs/elsewhere/"},
            {"GIT_EXTERNAL_DIFF": junk},
            {"GIT_DIFF_OPTS": "--unified=9"},
            {"GIT_DIFF_OPTS": "-u9"},
            {"GIT_CONFIG_PARAMETERS": "'diff.algorithm'='histogram'"},
            {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "diff.renameLimit",
             "GIT_CONFIG_VALUE_0": "1"},
        ]
        config += [{"attr.tree": "{attributes tree}"}]
        environment_values += [{"GIT_ATTR_SOURCE": "{attributes tree}"}]
        for values in config:
            yield ", ".join(f"{k}={v}" for k, v in values.items()), values, {}
        for values in environment_values:
            yield ", ".join(f"{k}={v}" for k, v in values.items()), {}, values

    def attributes_tree(self, repo):
        """A tree in repo holding a .gitattributes that marks every file
        -diff, for attr.tree and GIT_ATTR_SOURCE to point at."""
        blob = repo.git("hash-object", "-w", "--stdin", stdin="* -diff\n").strip()
        return repo.git("mktree", stdin=f"100644 blob {blob}\t.gitattributes\n").strip()

    def test_no_setting_changes_either_listing(self):
        for label, config, env in self.settings():
            for name, repo in self.repos.items():
                with self.subTest(setting=label, listing=name):
                    tree = self.attributes_tree(repo)
                    info = repo.path / ".git" / "info" / "attributes"
                    for key, value in config.items():
                        if key == INFO:
                            info.parent.mkdir(exist_ok=True)
                            info.write_text(value)
                        else:
                            repo.git("config", key, value.replace("{attributes tree}", tree))
                    try:
                        with environment(**{key: value.replace("{attributes tree}", tree)
                                            for key, value in env.items()}):
                            found = listing(repo)
                    finally:
                        info.unlink(missing_ok=True)
                        for key in config:
                            if key != INFO:
                                repo.git("config", "--unset-all", key)
                    self.assertEqual(found, self.expected[name])


if __name__ == "__main__":
    unittest.main()
