# tests/test_parser_edge.py
"""解析器边界用例：来自真实资源名的误判复现。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import parser  # noqa: E402


class TestParserEdge(unittest.TestCase):
    def test_year_like_title_not_treated_as_year(self):
        # 「1917」「2012」这类片名本身就是年份数字，不能当成发行年份
        r = parser.parse("1917.2019.1080p.BluRay.x264.mkv")
        self.assertEqual(r["year"], 2019)
        self.assertEqual(r["title"], "1917")

    def test_season_word_with_episode_is_not_batch(self):
        # 「2nd Season - 10」是单集，不是整季合集
        r = parser.parse("[Erai-raws] Sousou no Frieren 2nd Season - 10 "
                         "[1080p CR WEB-DL AVC AAC][MultiSub].mkv")
        self.assertEqual(r["episode"], 10)
        self.assertFalse(r["is_batch"], "单集不该被判为整季合集")

    def test_s2_episode_not_batch(self):
        # 「S2 - 06」同样：有季号不代表是合集
        r = parser.parse("Sousou no Frieren S2 - 06 [1080p].mkv")
        self.assertEqual(r["episode"], 6)
        self.assertFalse(r["is_batch"], "带季号的单集不该被判为整季合集")

    def test_episode_range_is_batch(self):
        # 真合集：集号区间
        r = parser.parse("Frieren [01-28] [1080p].mkv")
        self.assertTrue(r["is_batch"])

    def test_batch_word_on_episode_still_batch(self):
        # 「全集」等中文合集词仍应判为合集
        r = parser.parse("葬送的芙莉莲 全集 1080p.mkv")
        self.assertTrue(r["is_batch"])

    def test_ordinal_season_word_parsed_as_season(self):
        # 「2nd Season - 10」：季号是 2，集号是 10，别把集号当季号
        r = parser.parse("[Erai-raws] Sousou no Frieren 2nd Season - 10 "
                         "[1080p CR WEB-DL AVC AAC][MultiSub].mkv")
        self.assertEqual(r["season"], 2)
        self.assertEqual(r["episode"], 10)
        self.assertNotIn("Season", r["title"])
        self.assertNotIn("10", r["title"])

    def test_season_dir_name_not_batch(self):
        # 带集号的单集：季集标记不算合集
        r = parser.parse("Sousou no Frieren S01E34 [1080p].mkv")
        self.assertEqual(r["season"], 1)
        self.assertEqual(r["episode"], 34)
        self.assertFalse(r["is_batch"])


if __name__ == "__main__":
    unittest.main()
