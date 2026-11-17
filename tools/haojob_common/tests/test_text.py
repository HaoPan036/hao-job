"""Shared text helpers; fictional values only."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import haojob_common
from haojob_common import clean_text, contains_job_id


class TextTests(unittest.TestCase):
    def test_clean_text_unescapes_and_collapses_whitespace(self):
        self.assertEqual(clean_text("  Fictional &amp; Labs\n\t Engineer  "), "Fictional & Labs Engineer")
        self.assertEqual(clean_text("&lt;b&gt;"), "<b>")
        self.assertEqual(clean_text(""), "")

    def test_job_id_matches_whole_tokens_only(self):
        self.assertTrue(contains_job_id("Job ID DEMO-SG-001; note", "DEMO-SG-001"))
        self.assertTrue(contains_job_id("(DEMO-SG-001)", "DEMO-SG-001"))
        self.assertFalse(contains_job_id("DEMO-SG-0010", "DEMO-SG-001"))
        self.assertFalse(contains_job_id("XDEMO-SG-001", "DEMO-SG-001"))
        self.assertFalse(contains_job_id("DEMO_SG_001", "DEMO-SG-001"))
        self.assertTrue(contains_job_id("id a.b", "a.b"))
        self.assertFalse(contains_job_id("id axb", "a.b"))

    def test_package_exports_are_explicit(self):
        self.assertEqual(sorted(haojob_common.__all__), sorted(name for name in haojob_common.__all__ if hasattr(haojob_common, name)))


if __name__ == "__main__":
    unittest.main()
