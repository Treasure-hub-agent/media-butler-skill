import unittest
from lib import metadata

class TestNames(unittest.TestCase):
    def test_search_names_include_input(self):
        names = metadata.search_names("Some Anime")
        self.assertIn("Some Anime", names)

    def test_search_names_strips_year(self):
        names = metadata.search_names("Some Movie 2019")
        self.assertIn("Some Movie", names)

    def test_anilist_parse(self):
        payload = {"data": {"Media": {
            "title": {"romaji": "A Romaji", "native": "A Native", "english": "A English"},
            "episodes": 24, "startDate": {"year": 2020}}}}
        r = metadata.parse_anilist(payload)
        self.assertEqual(r["english"], "A English")
        self.assertEqual(r["native"], "A Native")
        self.assertEqual(r["episodes"], 24)
        self.assertEqual(r["year"], 2020)

    def test_anilist_parse_null(self):
        self.assertIsNone(metadata.parse_anilist({"data": {"Media": None}}))
