#!/usr/bin/env python3
"""Regression tests for comment_scan.py.

Standard library only:

    python3 test_comment_scan.py

Three contracts are under test. **Comment boundaries**: a `//` or `#` inside
a string literal is not a comment, and a real comment on the line below one
is. **History flags**: the narrowed patterns fire on real history-narrating
comments taken from real codebases, and the shapes that were measured and
rejected stay silent. **Diff reading**: the comments a staged change, a
working-tree change or a commit range added are found, whatever the user's
diff config.
"""

import json
import pathlib
import subprocess
import tempfile
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().with_name("comment_scan.py")

# Compiled from source text on every run rather than imported: importlib
# caches bytecode keyed on size plus a whole-second mtime, so an edit that keeps the byte count
# and lands inside the same second runs the stale .pyc and the suite reports OK
# against code it never executed. compile() touches no cache. Naming the module
# something other than __main__ keeps the script's own entry point shut.
scanner = types.ModuleType("comment_scan_under_test")
scanner.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), scanner.__dict__)


def starts(path, source):
    """The first line of every comment found."""
    return [comment.start for comment in scanner.comments_in(path, source)]


def notes(path, source):
    """Every history note on every comment in source, as `prose check` finds them."""
    found = []
    for comment in scanner.comments_in(path, source):
        found.extend(scanner.history_notes(comment, scanner.mask_examples(scanner.strip_markers(comment))))
    return found


def kinds(path, source):
    return [note.kind for note in notes(path, source)]


class CommentBoundaries(unittest.TestCase):
    """What counts as a comment at all, which is the part regex cannot do."""

    def test_a_regex_literal_holding_slashes_is_not_a_comment(self):
        self.assertEqual(starts("r.js", "const r = /^https?:\\/\\//;\n"), [])
        self.assertEqual(starts("r.ts", "const r = /a\\//; // why\n"), [1])

    def test_a_comment_after_a_non_null_assertion_divided_is_found(self):
        self.assertEqual(starts("b.ts", "const y = count! / 2; // halve the count\n"), [1])

    def test_a_one_line_docstring_leaves_out_the_code_on_its_line(self):
        [docstring] = scanner.comments_in("e.py", 'class Refused(Exception): """A condition to fix."""\n')
        self.assertNotIn("Refused", "".join(docstring.lines))
        self.assertIn("A condition to fix.", "".join(docstring.lines))

    def test_slashes_inside_a_string_are_not_a_comment(self):
        source = 'const home = "https://example.com/previously/used-to";\n'
        self.assertEqual(starts("a.ts", source), [])

    def test_a_real_comment_after_a_string_full_of_slashes_is_found(self):
        source = 'const u = "http://a//b";\n// It used to read the bare summary.\n'
        self.assertEqual(starts("a.ts", source), [2])

    def test_a_comment_inside_a_template_interpolation_is_found(self):
        source = "const t = `hi ${ // It used to be two calls.\n  name}`;\n"
        self.assertEqual(starts("a.ts", source), [1])

    def test_interpolation_with_a_nested_object_does_not_end_early(self):
        # A `}` closing the object literal must not be read as closing the
        # `${`, or everything after it is scanned as template text and the real
        # comment below goes unseen.
        source = "const t = `${fmt({a: 1})} tail`;\n// This used to be inline.\n"
        self.assertEqual(starts("a.ts", source), [2])

    def test_slashes_in_a_template_literal_are_not_a_comment(self):
        source = "const t = `https://x/previously/used-to-be`;\n"
        self.assertEqual(starts("a.ts", source), [])

    def test_a_block_comment_spans_its_lines(self):
        source = "let a = 1;\n/* line one\n * It used to be two calls.\n */\n"
        comments = scanner.comments_in("a.ts", source)
        self.assertEqual([(c.start, c.end) for c in comments], [(2, 4)])

    def test_an_unterminated_single_quote_does_not_swallow_the_file(self):
        source = "const broken = 'oops;\nconst ok = 2;\n// It used to be two calls.\n"
        self.assertEqual(starts("a.ts", source), [3])

    def test_python_hash_inside_a_string_is_not_a_comment(self):
        self.assertEqual(starts("a.py", 'anchor = "#previously-used-to"\n'), [])

    def test_python_fstring_braces_do_not_confuse_the_tokenizer(self):
        source = 'msg = f"{count} rows"  # It used to be a list.\n'
        self.assertEqual(starts("a.py", source), [1])

    def test_a_python_docstring_is_read(self):
        source = 'def f():\n    """It used to be two calls."""\n    return 1\n'
        self.assertEqual(starts("a.py", source), [2])

    def test_a_bare_string_expression_is_not_read_as_a_docstring(self):
        # Only the first statement of a module, class or function is a
        # docstring; a string sitting in the middle of a body is data.
        source = 'def f():\n    x = 1\n    "It used to be two calls."\n    return x\n'
        self.assertEqual(starts("a.py", source), [])

    def test_consecutive_line_comments_are_one_block(self):
        source = "# One.\n# Two.\n# Three.\nx = 1\n"
        comments = scanner.comments_in("a.py", source)
        self.assertEqual(len(comments), 1)
        self.assertEqual((comments[0].start, comments[0].end), (1, 3))

    def test_a_trailing_comment_does_not_merge_with_the_block_below(self):
        source = "x = 1  # trailing\n# own line\ny = 2\n"
        comments = scanner.comments_in("a.py", source)
        self.assertEqual([c.own_line for c in comments], [False, True])
        self.assertEqual(len(comments), 2)

    def test_an_unparseable_python_file_is_none_not_empty(self):
        # An empty list instead would read as "no comments", and prose check
        # would leave the file out of its listing.
        self.assertIsNone(scanner.comments_touching("a.py", "def f(:\n", {1}))

    def test_an_unknown_extension_is_not_guessed_at(self):
        self.assertEqual(starts("a.lua", "-- It used to be two calls.\n"), [])
        self.assertFalse(scanner.scannable("a.lua"))

    def test_a_kotlin_raw_string_is_not_lexed_as_code(self):
        # `"""` is one delimiter, not an empty string plus an opener. Read the
        # other way, every line of the body is code and a `//` inside it - a
        # URL, a quoted snippet - is reported as a comment on a line that has
        # none.
        source = 'val script = """\n    // We switched to a single query here.\n    fetch(url)\n"""\n'
        self.assertEqual(starts("a.kt", source), [])

    def test_a_csharp_verbatim_string_of_one_quote_is_not_a_fence(self):
        # `@""""` is a verbatim string holding one double quote: the `@"`
        # opens it and `""` is an escaped quote. Read as a `"""` fence with no
        # closer, it swallows every comment to the end of the file.
        source = (
            'const string Quote = @"""";\n// It used to build the row with string.Join.\n'
            "var x = 1;\n// We switched to a single pass here.\n"
        )
        self.assertEqual(starts("a.cs", source), [2, 4])

    def test_an_escaped_triple_quote_does_not_close_a_java_text_block(self):
        source = 'String t = """\n  he said \\""" ok\n  // It used to be two calls.\n  """;\nclass A {}\n'
        self.assertEqual(starts("a.java", source), [])

    def test_a_kotlin_raw_string_ending_in_a_backslash_still_closes(self):
        # Kotlin raw strings have no escapes, so the `\` before the closing
        # fence is the string's last character. Read as an escape, the fence
        # is missed and every comment below it is lost with the string.
        source = 'val p = """C:\\Users\\"""\n// It used to be two calls.\n'
        self.assertEqual(starts("a.kt", source), [2])

    def test_a_dart_raw_triple_string_has_no_escapes(self):
        # `r'''` is the raw twin of Dart's escaped `'''`, told apart only by
        # the letter in front of the fence.
        source = "final p = r'''C:\\Users\\''';\n// It used to be two calls.\n"
        self.assertEqual(starts("a.dart", source), [2])

    def test_a_csharp_interpolated_verbatim_string_spans_lines(self):
        # `$@"` opens a verbatim string too. It runs across the newline, `""`
        # is one quote, and the `//` inside it is text - so the only comment
        # is the one on the last line.
        source = 'var s = $@"line // one\nline "" two";\n// It used to be two calls.\n'
        self.assertEqual(starts("a.cs", source), [3])

    def test_bare_carriage_return_line_endings_are_still_lines(self):
        # Python accepts a lone `\r` as a line terminator, so the tokenizer
        # must see one too or every comment in the file turns into an operator.
        self.assertEqual(starts("a.py", "x = 1\r# It used to be two calls.\ry = 2\r"), [2])

    def test_bare_carriage_return_line_endings_are_lines_in_the_c_family_too(self):
        source = "let a = 1;\r// It used to be two calls.\rlet b = 2;\r"
        self.assertEqual(starts("a.ts", source), [2])

    def test_a_rust_lifetime_tick_does_not_open_a_string(self):
        source = "fn parse<'a>(s: &'a str) -> &'a str { s } // It used to be two calls.\n"
        self.assertEqual(starts("a.rs", source), [1])

    def test_a_rust_raw_string_ending_in_a_backslash_does_not_eat_the_comment(self):
        # In `r"..."` a backslash is content, so the one before the closing
        # quote does not escape it; read as an escape, the string runs to the
        # end of the line and the trailing comment goes with it.
        source = 'let p = r"C:\\Users\\"; // It used to be two calls.\nlet q = 1;\n'
        self.assertEqual(starts("a.rs", source), [1])

    def test_a_hashed_rust_raw_string_spans_lines_without_inventing_a_comment(self):
        # `r#"..."#` closes only at `"#`, so the `"` and the `//` inside it are
        # text: no comment on line 2, and the real one after it is on line 5
        # with the right number and on its own line.
        source = (
            'let q = r#"say "hi"\n// We switched to a single query here.\n'
            'done"#;\nlet r = 1;\n// It used to be two calls.\n'
        )
        self.assertEqual(starts("a.rs", source), [5])
        self.assertTrue(scanner.comments_in("a.rs", source)[0].own_line)

    def test_a_dart_single_quoted_raw_string_has_no_escapes(self):
        # `r'\'` is a one-backslash string: the quote after the backslash
        # closes it. Read with escapes, the string runs to the end of the line
        # and takes the trailing comment with it.
        source = "final sep = r'\\'; // It used to be two calls.\nfinal x = 1;\n"
        self.assertEqual(starts("a.dart", source), [1])
        source = 'final p = r"C:\\Users\\"; // It used to be two calls.\n'
        self.assertEqual(starts("a.dart", source), [1])

    def test_an_unterminated_dart_raw_string_stops_at_the_newline(self):
        # A Dart `r'...'` cannot span a line, so an unterminated one stops at
        # the newline like any other quote and leaves the comment below
        # readable, rather than scanning for a close it never finds.
        source = "final s = r'oops;\n// It used to be two calls.\n"
        self.assertEqual(starts("a.dart", source), [2])

    def test_a_dart_identifier_ending_in_r_is_not_a_raw_prefix(self):
        # `final r = '\\';` is an ordinary string: a space, not the quote,
        # follows the `r`, so its escapes count and it closes at its own
        # quote. `bar'x'` and the escaped forms `r'\d+'`, `r'a\b'` close where
        # Dart closes them too.
        self.assertEqual(starts("a.dart", "final r = '\\\\'; // It used to be two calls.\n"), [1])
        source = "final q = bar'x' + r'\\d+' + r'a\\b'; // We switched to one query.\n"
        self.assertEqual(starts("a.dart", source), [1])

    def test_a_form_feed_does_not_shift_python_line_numbers(self):
        # PEP 8 allows a control-L as a section separator, and Python does not
        # treat it as a line break; the reported line must agree with the file.
        self.assertEqual(starts("a.py", "x = 1\n\x0c\n# It used to be two calls.\ny = 2\n"), [3])

    def test_a_form_feed_inside_a_string_does_not_fake_a_parse_failure(self):
        self.assertEqual(starts("a.py", 'PAGE_BREAK = "\x0c"\n# It used to be two calls.\n'), [2])

    def test_a_utf8_bom_is_not_a_syntax_error(self):
        self.assertEqual(starts("a.py", "\ufeff# It used to be two calls.\nx = 1\n"), [1])


class HistoryPatterns(unittest.TestCase):
    """Specimens are real comments from real codebases, lightly trimmed."""

    def fires(self, text, expected):
        self.assertEqual(kinds("a.py", text), [f"history:{expected}"], text)

    def silent(self, text):
        self.assertEqual(kinds("a.py", text), [], text)

    def test_each_pattern_fires_on_a_real_specimen(self):
        for expected, comment in [
            ("used-to", "# Covers what used to be two reasons.\n"),
            ("used-to", "# This used to scan lookupByCode and take the first hit.\n"),
            ("no-longer", "# Mobile no longer calls this host.\n"),
            ("previously", "# This endpoint previously lived in the admin app.\n"),
            ("formerly", "# Formerly a single all-sections call.\n"),
            ("earlier-version", "# An earlier version of this javadoc asserted the invariant.\n"),
            ("old-thing", "# The old behaviour reset the counter on every read.\n"),
            ("replaced", "# This replaced search-per-ingredient, intersect, compare.\n"),
            ("we-changed", "# We switched to a single query here.\n"),
            ("before-this", "# Before this change the cap was per call.\n"),
            ("originally", "# Originally this was a list.\n"),
            ("instead-of-old", "# Sorted here instead of the old caller-side pass.\n"),
        ]:
            with self.subTest(expected):
                self.fires(comment, expected)

    def test_the_measured_rejections_stay_silent(self):
        # Each of these was measured over ~3000 files and left out: bare, they
        # fired 850, 458, 385 and 228 times, overwhelmingly on code with no
        # history problem.
        for comment in [
            "# The runtime key used to build admin links that leave the app.\n",
            "# Used to deny vendor auth when the org is suspended.\n",
            "# Legacy endpoint kept for the Android build.\n",
            "# Trailing tokens of the previous chunk are prepended to the next.\n",
            "# Placeholders are replaced with the resolved values.\n",
            "# Blank CUI1 repeats the previous populated row.\n",
        ]:
            with self.subTest(comment):
                self.silent(comment)

    def test_previously_as_an_adjective_is_vetoed_but_as_a_verb_is_not(self):
        self.silent("# Send a previously previewed draft to the audience.\n")
        self.silent("# Keep a product's previously-stored ingredients on resync.\n")
        self.silent("# Returns the previously cached graph.\n")
        self.fires("# It previously read the bare summary.\n", "previously")
        self.fires("# Previously this stored no marker at all.\n", "previously")

    def test_one_note_per_line_even_when_several_patterns_match(self):
        source = "# This used to be the old approach and we changed it.\n"
        self.assertEqual(len(notes("a.py", source)), 1)

    def test_no_longer_carries_its_own_false_positive_warning(self):
        detail = notes("a.py", "# The row is no longer pending.\n")[0].detail
        self.assertIn("runtime state transition", detail)

    def test_a_backticked_example_is_masked(self):
        self.silent("# Do not write `it used to be two calls` in a comment.\n")

    def test_a_backticked_example_that_wraps_is_masked(self):
        source = "# Never write `it used to\n# be two calls` here.\n"
        self.assertEqual(kinds("a.py", source), [])

    def test_a_url_containing_a_history_word_is_masked(self):
        self.silent("# See https://example.com/docs/previously/index.html\n")

    def test_a_doctest_line_is_masked(self):
        source = 'def f():\n    """Sum.\n\n    >>> f()  # it used to be 2\n    3\n    """\n'
        self.assertEqual(kinds("a.py", source), [])

    def test_a_fenced_block_in_a_docstring_is_masked(self):
        source = (
            'def f():\n    """Doc.\n\n    ```\n    # It used to be two calls.\n'
            '    ```\n    """\n'
        )
        self.assertEqual(kinds("a.py", source), [])

    def test_a_jsdoc_example_block_is_masked(self):
        source = "/**\n * Doc.\n * @example\n * // It used to be two calls.\n */\n"
        self.assertEqual(kinds("a.ts", source), [])

    def test_the_line_number_points_at_the_offending_line_not_the_block(self):
        source = "# One.\n# Two.\n# It used to be two calls.\n"
        self.assertEqual(notes("a.py", source)[0].line, 3)

    def test_prose_starting_with_the_word_code_is_not_an_example_block(self):
        # Only a real `@example` / `{@code` tag opens an example; a sentence
        # that happens to begin with "Code" is prose, and blanking it hides
        # everything down to the next blank line.
        source = "# Code paths that reach here are the two admin writers.\n# It used to be a single call.\n"
        self.assertEqual(kinds("a.py", source), ["history:used-to"])

    def test_an_example_section_label_does_not_mask_the_lines_below_it(self):
        source = (
            'def f():\n    """Resolve a code.\n    Example: resolve("abc") returns the row.\n'
            '    It used to return a list.\n    """\n'
        )
        self.assertEqual(kinds("a.py", source), ["history:used-to"])


class HashComments(unittest.TestCase):
    """Shell, YAML and the like: own-line `#` comments only."""

    def test_an_own_line_shell_comment_is_found(self):
        source = "#!/bin/sh\n# Says hello.\necho hi\n"
        self.assertEqual(starts("run.sh", source), [2])

    def test_a_shebang_is_not_a_comment(self):
        self.assertEqual(starts("run.sh", "#!/bin/sh\necho hi\n"), [])

    def test_a_hash_after_code_is_not_read(self):
        # `$#`, `${#x}` and a `#` inside a string all sit after code.
        self.assertEqual(starts("run.sh", 'echo "$#" ${#x} "a # b"\n'), [])

    def test_yaml_and_extensionless_names_are_read(self):
        self.assertEqual(starts("ci.yml", "on: push\n  # Runs on push.\n"), [2])
        self.assertEqual(starts("Dockerfile", "# Base image.\nFROM x\n"), [1])
        self.assertTrue(scanner.scannable("sub/Makefile"))


class DiffModes(unittest.TestCase):
    """The comments each diff mode added, read from the right side."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.repo = pathlib.Path(self.dir)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")

    def git(self, *args):
        return subprocess.run(
            ["git"] + list(args), cwd=self.dir, capture_output=True, text=True, check=True
        ).stdout

    def touched(self, mode, revisions=None, cwd=None):
        """{path: [(start, end), ...]} of the comments the diff touched."""
        found = {}
        for path, source, lines in scanner.diff_targets(mode, revisions, cwd or self.dir):
            comments = scanner.comments_touching(path, source, lines)
            found[path] = None if comments is None else [(c.start, c.end) for c in comments]
        return found

    def commit_file(self, name, text):
        (self.repo / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", f"add {name}")

    def test_a_comment_outside_the_hunk_is_not_counted(self):
        original = "# It previously read the bare summary.\nx = 1\n"
        self.commit_file("a.py", original)
        (self.repo / "a.py").write_text(original + "y = 2\n")
        self.git("add", "a.py")
        self.assertEqual(self.touched("staged"), {"a.py": []})

    def test_a_comment_the_diff_added_is_counted(self):
        original = "# It previously read the bare summary.\nx = 1\n"
        self.commit_file("a.py", original)
        (self.repo / "a.py").write_text(original + "# We switched to one query.\ny = 2\n")
        self.git("add", "a.py")
        self.assertEqual(self.touched("staged"), {"a.py": [(3, 3)]})

    def test_the_unstaged_mode_reads_the_working_tree(self):
        self.commit_file("a.py", "x = 1\n")
        (self.repo / "a.py").write_text("x = 1\n# It used to be two calls.\n")
        self.assertEqual(self.touched("unstaged"), {"a.py": [(2, 2)]})

    def test_the_range_mode_reads_the_committed_side(self):
        self.commit_file("a.py", "x = 1\n")
        self.commit_file("a.py", "x = 1\n# Originally this was a list.\n")
        self.assertEqual(self.touched("range", "HEAD~1..HEAD"), {"a.py": [(2, 2)]})

    def test_a_deleted_file_does_not_crash_the_run(self):
        self.commit_file("a.py", "# It used to be two calls.\nx = 1\n")
        self.git("rm", "-q", "a.py")
        self.assertEqual(self.touched("staged"), {})

    def test_a_file_in_a_language_it_does_not_parse_is_left_alone(self):
        (self.repo / "a.lua").write_text("-- It used to be two calls.\n")
        self.git("add", "a.lua")
        self.assertEqual(self.touched("staged"), {})

    def test_a_json_file_is_never_lexed_as_code(self):
        (self.repo / "a.json").write_text(json.dumps({"note": "it used to be two"}))
        self.git("add", "a.json")
        self.assertEqual(self.touched("staged"), {})

    def test_a_missing_trailing_newline_marker_does_not_shift_the_changed_lines(self):
        # The `\ No newline at end of file` marker is not a line of either
        # image; counting it puts every added line one too high.
        diff = (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n"
            "-x = 1\n\\ No newline at end of file\n+# It used to be two calls.\n+x = 1\n"
        )
        self.assertEqual(scanner.added_lines(diff), {"a.py": {1, 2}})

    def test_a_deletion_only_change_registers_the_file_with_no_added_lines(self):
        self.commit_file("a.py", "# It used to be two calls.\nx = 1\ny = 2\n")
        (self.repo / "a.py").write_text("# It used to be two calls.\nx = 1\n")
        self.git("add", "a.py")
        self.assertEqual(self.touched("staged"), {"a.py": []})
        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -2 +1,0 @@\n-y = 2\n"
        self.assertEqual(scanner.added_lines(diff), {"a.py": set()})

    def test_an_added_line_starting_with_two_pluses_is_not_a_file_header(self):
        # `++ i;` as an added line prints as `+++ i;`. A header is only a
        # header inside the block that `diff --git` opens, never in a hunk.
        diff = (
            "diff --git a/a.c b/a.c\n--- a/a.c\n+++ b/a.c\n@@ -1,0 +2,2 @@\n"
            "+++ i;\n+// It used to be two calls.\n"
        )
        self.assertEqual(scanner.added_lines(diff), {"a.c": {2, 3}})

    def test_a_file_name_with_a_quote_in_it_is_still_read(self):
        # `core.quotePath=false` leaves `"` and `\` C-quoted in the header;
        # the quoting has to be undone or the suffix is `.py"`.
        (self.repo / 'we"ird.py').write_text("# It used to be two calls.\n")
        self.git("add", 'we"ird.py')
        self.assertEqual(self.touched("staged"), {'we"ird.py': [(1, 1)]})

    def test_a_form_feed_in_an_added_line_does_not_shift_the_changed_lines(self):
        # git breaks a diff on `\n` alone; `str.splitlines` would also break
        # on a form feed and number every later added line one too high.
        diff = (
            "diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,3 @@\n"
            "+x = 1\n+\x0c\n+# It used to be two calls.\n"
        )
        self.assertEqual(scanner.added_lines(diff), {"a.py": {1, 2, 3}})
        (self.repo / "a.py").write_bytes(b"x = 1\n\x0c\n# It used to be two calls.\n")
        self.git("add", "a.py")
        self.assertEqual(self.touched("staged"), {"a.py": [(3, 3)]})

    def test_the_unstaged_mode_works_from_a_subdirectory(self):
        (self.repo / "sub").mkdir()
        self.commit_file("sub/a.py", "x = 1\n")
        (self.repo / "sub" / "a.py").write_text("x = 1\n# It used to be two calls.\n")
        found = self.touched("unstaged", cwd=str(self.repo / "sub"))
        self.assertEqual(found, {"sub/a.py": [(2, 2)]})

    def test_diff_relative_config_does_not_hide_files_from_a_subdirectory(self):
        # `diff.relative=true` makes `git diff` print subdirectory-relative
        # paths; every reader here resolves paths against the tree top.
        self.git("config", "diff.relative", "true")
        (self.repo / "sub").mkdir()
        self.commit_file("sub/a.py", "x = 1\n")
        (self.repo / "sub" / "a.py").write_text("x = 1\n# It used to be two calls.\n")
        self.git("add", "sub/a.py")
        for mode in ("staged", "unstaged"):
            with self.subTest(mode):
                if mode == "unstaged":
                    (self.repo / "sub" / "a.py").write_text(
                        "x = 1\n# It used to be two calls.\n# Originally a list.\n"
                    )
                found = self.touched(mode, cwd=str(self.repo / "sub"))
                self.assertIn("sub/a.py", found)
                self.assertTrue(found["sub/a.py"])

    def test_config_that_reshapes_the_diff_does_not_empty_the_run(self):
        # Each of these is a common global setting, and each changes the text
        # `git diff` prints. The scanner asks for the default shape.
        self.commit_file("a.py", "x = 1\n")
        (self.repo / "a.py").write_text("x = 1\n# It used to be two calls.\n")
        self.git("add", "a.py")
        for key, value in [
            ("diff.mnemonicPrefix", "true"), ("diff.noprefix", "true"),
            ("color.ui", "always"), ("diff.external", "true"),
        ]:
            with self.subTest(f"{key}={value}"):
                self.git("config", key, value)
                found = self.touched("staged")
                self.git("config", "--unset", key)
                self.assertEqual(found, {"a.py": [(2, 2)]})

    def test_a_non_utf8_byte_in_a_staged_file_is_read_not_a_traceback(self):
        (self.repo / "a.py").write_bytes(b"# caf\xe9 - it used to be two calls.\nx = 1\n")
        self.git("add", "a.py")
        self.assertEqual(self.touched("staged"), {"a.py": [(1, 1)]})

    def test_a_single_revision_range_reads_the_working_tree_side(self):
        # `git diff HEAD~1` compares HEAD~1 with the working tree, so the
        # post-image to lex is the file on disk, not the old commit.
        self.commit_file("a.py", "x = 1\n")
        self.commit_file("a.py", "x = 1\n# Originally this was a list.\n")
        self.assertEqual(self.touched("range", "HEAD~1"), {"a.py": [(2, 2)]})

    def test_a_three_dot_range_reads_the_right_hand_side(self):
        self.commit_file("a.py", "x = 1\n")
        self.commit_file("a.py", "x = 1\n# Originally this was a list.\n")
        self.assertEqual(self.touched("range", "HEAD~1...HEAD"), {"a.py": [(2, 2)]})

    def test_a_non_ascii_file_name_is_still_read(self):
        (self.repo / "résumé.py").write_text("# It used to be two calls.\n", encoding="utf-8")
        self.git("add", "résumé.py")
        self.assertEqual(self.touched("staged"), {"résumé.py": [(1, 1)]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
