import unittest
from lib import parser

class TestTitleCleanliness(unittest.TestCase):
    """标题会直接成为归档目录名，必须干净：不含字幕组名、技术标签、集号残留。"""

    def test_strips_fansub_group_block(self):
        r = parser.parse("[某字幕组] 某某番 - 33 [1080P][简繁内封].mkv")
        self.assertNotIn("某字幕组", r["title"])
        self.assertIn("某某番", r["title"])

    def test_strips_ascii_group_block(self):
        r = parser.parse("[SomeGroup&Studio] Some Anime - 33 [1080p].mkv")
        self.assertNotIn("SomeGroup", r["title"])
        self.assertIn("Some Anime", r["title"])

    def test_strips_episode_marker_from_title(self):
        r = parser.parse("Some.Show.S02E07.1080p.WEB-DL.x265")
        self.assertNotIn("S02E07", r["title"])
        self.assertEqual(r["title"], "Some Show")

    def test_strips_episode_word_from_title(self):
        r = parser.parse("Some Anime Episode 245 The Title.mkv")
        self.assertNotIn("Episode 245", r["title"])

    def test_strips_trailing_digit_episode(self):
        r = parser.parse("[SomeGroup] Some Anime - 33 [1080p][简繁内封].mkv")
        self.assertFalse(r["title"].rstrip().endswith("33"), r["title"])
        self.assertIn("Some Anime", r["title"])

    def test_keeps_chinese_title_intact(self):
        r = parser.parse("流浪地球 2019 电影 国语中字 高清.mkv")
        self.assertEqual(r["title"], "流浪地球")

    def test_keeps_bilingual_title(self):
        r = parser.parse("[DBD-Raws][流浪地球/The.Wandering.Earth.][1080P][BDRip].mkv")
        self.assertNotIn("DBD-Raws", r["title"])
        self.assertIn("流浪地球", r["title"])

    def test_strips_underscore_tech_block(self):
        r = parser.parse("[Group][4K_HDR][Some Movie][2160P].mkv")
        self.assertNotIn("4K", r["title"])
        self.assertNotIn("HDR", r["title"])
        self.assertIn("Some Movie", r["title"])

    def test_batch_word_not_in_title(self):
        r = parser.parse("Some Show 001-500 Complete Series [1080p]")
        self.assertNotIn("Complete", r["title"], r["title"])
