"""Signature normalization: path/case/whitespace variants must collide."""

import unittest

from qacompanion.signatures import baseline_paths, normalize


class NormalizeTests(unittest.TestCase):
    def test_path_and_case_variations_collide(self):
        win = normalize(
            "tests/test_config.py::test_load",
            "FileNotFoundError: C:\\Users\\j\\proj\\data\\config.json",
        )
        posix = normalize(
            "tests/test_config.py::test_load",
            "filenotfounderror: /home/j/proj/data/config.json",
        )
        self.assertEqual(win, posix)

    def test_whitespace_variants_collapse(self):
        a = normalize("test_sp  ace", "ValueError:\tbad\n\t\tinput")
        b = normalize("test_sp ace", "valueerror: bad input")
        self.assertEqual(a, b)

    def test_relative_path_prefix_stripped(self):
        from_root = normalize(
            "tests/test_a.py::test_x", "assert 1 == 2 in src/mod.py"
        )
        from_pkg = normalize("test_a.py::test_x", "assert 1 == 2 in mod.py")
        self.assertEqual(from_root, from_pkg)

    def test_quoted_windows_path_baselined_inside_quotes(self):
        plain = normalize("t", 'missing "C:\\etc\\app.ini"')
        other_drive = normalize("t", 'missing "D:\\deep\\nested\\app.ini"')
        self.assertEqual(plain, other_drive)

    def test_distinct_failures_do_not_collide(self):
        a = normalize("test_one", "ValueError: alpha")
        b = normalize("test_two", "ValueError: alpha")
        c = normalize("test_one", "ValueError: beta")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_format_is_test_then_separator_then_error(self):
        sig = normalize("TestName", "Boom")
        self.assertEqual("testname :: boom", sig)


class BaselinePathsTests(unittest.TestCase):
    def test_plain_text_untouched(self):
        self.assertEqual("no paths here", baseline_paths("no paths here"))

    def test_posix_absolute_to_basename(self):
        self.assertEqual("x.json", baseline_paths("/var/log/app/x.json"))

    def test_windows_absolute_to_basename(self):
        self.assertEqual("x.json", baseline_paths("C:\\var\\log\\x.json"))


if __name__ == "__main__":
    unittest.main()
