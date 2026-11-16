"""One URL identity form for discovery and record sync; reserved domains only."""

import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
from haojob_common import canonical_url


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TOOLS / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


radar = load("common_url_radar", "job-radar/radar.py")
sync = load("common_url_sync", "recruiting-sync/sync.py")

# Outputs of radar.normalize_url before it moved here. The collector stores
# these as SQLite seen-store keys and the bridge as watch state, so they must
# stay byte-identical.
GOLDEN = (
    ('https://jobs.example.com/role/123?utm_source=x',
     'https://jobs.example.com/role/123'),
    ('https://jobs.example.com/role/123?utm_source=x&id=5&spm=a.b&from=feed&source=list&UTM_Medium=y',
     'https://jobs.example.com/role/123?id=5'),
    ('HTTPS://Jobs.Example.COM/Role/123/',
     'https://jobs.example.com/Role/123'),
    ('https://jobs.example.com/a%2fb',
     'https://jobs.example.com/a%2Fb'),
    ('https://jobs.example.com/a%2Fb',
     'https://jobs.example.com/a%2Fb'),
    ('https://jobs.example.com/%7Euser/%41bc',
     'https://jobs.example.com/~user/Abc'),
    ('https://jobs.example.com/?q=a+b&r=a%20b&s=a%2bb',
     'https://jobs.example.com?q=a+b&r=a%20b&s=a%2Bb'),
    ('https://jobs.example.com/jobs/Engineer_(Intern)',
     'https://jobs.example.com/jobs/Engineer_%28Intern%29'),
    ('https://jobs.example.com/jobs/Engineer_%28Intern%29',
     'https://jobs.example.com/jobs/Engineer_%28Intern%29'),
    ('https://maple.example/jobs/工程師(Cloud)?team=研發&view=a%2Fb#職缺',
     'https://maple.example/jobs/%E5%B7%A5%E7%A8%8B%E5%B8%AB%28Cloud%29?team=%E7%A0%94%E7%99%BC&view=a%2Fb#%E8%81%B7%E7%BC%BA'),
    ('https://jobs.example.com/x?a=1&&b=2&a=3',
     'https://jobs.example.com/x?a=1&&b=2&a=3'),
    ('https://jobs.example.com/x?',
     'https://jobs.example.com/x'),
    ('https://jobs.example.com/x#frag/ment?x',
     'https://jobs.example.com/x#frag/ment?x'),
    ('https://jobs.example.com/[a]?k=[v]',
     'https://jobs.example.com/%5Ba%5D?k=%5Bv%5D'),
    ('https://jobs.example.com',
     'https://jobs.example.com'),
    ('',
     ''),
    ('https://jobs.example.com/p%e5%b7%a5',
     'https://jobs.example.com/p%E5%B7%A5'),
    ('https://jobs.example.com/x?%75tm_source=1&k=v',
     'https://jobs.example.com/x?k=v'),
)
SAME = (
    ("tracking parameters", "https://jobs.example.com/role/123?utm_source=x&utm_medium=y", "https://jobs.example.com/role/123"),
    ("tracking parameter case", "https://jobs.example.com/role/123?UTM_Campaign=z&id=7&spm=a", "https://jobs.example.com/role/123?id=7"),
    ("from and source", "https://jobs.example.com/role/123?from=feed&id=7&source=list", "https://jobs.example.com/role/123?id=7"),
    ("percent-escape case", "https://jobs.example.com/role/%e5%b7%a5", "https://jobs.example.com/role/%E5%B7%A5"),
    ("non-ASCII literal", "https://jobs.example.com/role/工", "https://jobs.example.com/role/%E5%B7%A5"),
    ("unreserved escapes", "https://jobs.example.com/%7Euser/%45ngineer-%5F1", "https://jobs.example.com/~user/Engineer-_1"),
    ("parentheses", "https://jobs.example.com/jobs/Engineer_(Intern)", "https://jobs.example.com/jobs/Engineer_%28Intern%29"),
    ("trailing slash", "https://jobs.example.com/role/123/", "https://jobs.example.com/role/123"),
    ("host and scheme case", "HTTPS://Jobs.Example.COM/role/123", "https://jobs.example.com/role/123"),
    ("encoded slash case", "https://jobs.example.com/a%2fb", "https://jobs.example.com/a%2Fb"),
)
DIFFERENT = (
    ("encoded slash", "https://jobs.example.com/a%2Fb", "https://jobs.example.com/a/b"),
    ("plus versus space", "https://jobs.example.com/?q=a+b", "https://jobs.example.com/?q=a%20b"),
    ("plus versus encoded plus", "https://jobs.example.com/?q=a%2Bb", "https://jobs.example.com/?q=a+b"),
    ("encoded ampersand", "https://jobs.example.com/?q=a%26b", "https://jobs.example.com/?q=a&b"),
    ("path case", "https://jobs.example.com/Role/123", "https://jobs.example.com/role/123"),
    ("other query values", "https://jobs.example.com/?jobId=1", "https://jobs.example.com/?jobId=2"),
    ("query order", "https://jobs.example.com/?a=1&b=2", "https://jobs.example.com/?b=2&a=1"),
)


class CanonicalUrlTests(unittest.TestCase):
    def test_radar_output_is_unchanged_for_stored_keys(self):
        for value, expected in GOLDEN:
            with self.subTest(value=value):
                self.assertEqual(canonical_url(value), expected)
                self.assertEqual(radar.normalize_url(value), expected)

    def test_radar_and_sync_agree(self):
        for label, left, right in SAME + DIFFERENT:
            for value in (left, right):
                with self.subTest(label=label, value=value):
                    self.assertEqual(radar.normalize_url(value), sync.canonical_url(value))

    def test_equivalent_spellings_compare_equal_in_both_tools(self):
        for label, left, right in SAME:
            for normalize in (radar.normalize_url, sync.canonical_url):
                with self.subTest(label=label, tool=normalize.__module__):
                    self.assertEqual(normalize(left), normalize(right))

    def test_distinct_identities_stay_distinct_in_both_tools(self):
        for label, left, right in DIFFERENT:
            for normalize in (radar.normalize_url, sync.canonical_url):
                with self.subTest(label=label, tool=normalize.__module__):
                    self.assertNotEqual(normalize(left), normalize(right))

    def test_canonical_form_is_stable(self):
        for value, _ in GOLDEN:
            with self.subTest(value=value):
                self.assertEqual(canonical_url(canonical_url(value)), canonical_url(value))


if __name__ == "__main__":
    unittest.main()
