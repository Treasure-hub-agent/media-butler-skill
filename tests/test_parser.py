import unittest
from lib import parser

class TestParse(unittest.TestCase):
    def test_movie_with_group(self):
        r = parser.parse("Some.Movie.2019.1080p.BluRay.x264-GROUP")
        self.assertEqual(r["title"], "Some Movie")
        self.assertEqual(r["year"], 2019)
        self.assertFalse(r["is_batch"])

    def test_series_episode(self):
        r = parser.parse("Some.Show.S02E07.1080p.WEB-DL.x265")
        self.assertEqual(r["season"], 2)
        self.assertEqual(r["episode"], 7)

    def test_episode_word_form(self):
        r = parser.parse("Some Anime Episode 245 The Title.mkv")
        self.assertEqual(r["episode"], 245)

    def test_batch_detection(self):
        r = parser.parse("Some Show 001-500 Complete Series [1080p]")
        self.assertTrue(r["is_batch"])

    def test_chinese_subtitle_marks(self):
        for s in ["某片 中字 1080p", "某片 简体", "某片 繁中", "某片 CHS", "某片 简繁内封"]:
            self.assertTrue(parser.has_chinese_subtitle(s), s)

    def test_no_chinese_mark(self):
        self.assertFalse(parser.has_chinese_subtitle("Some.Movie.2019.1080p.BluRay"))

    def test_subtitle_group_implies_chinese(self):
        self.assertTrue(parser.has_chinese_subtitle("[某字幕组] Some Anime - 03 [1080p]"))


class TestBracketPrefix(unittest.TestCase):
    """字幕组用方括号前缀是动漫资源最常见的命名，标题不能被截成空串。"""

    def test_bracket_prefix_keeps_title(self):
        r = parser.parse("[某字幕组] 某某番 - 03 [1080P][简繁内封].mkv")
        self.assertNotEqual(r["title"], "")
        self.assertIn("某某番", r["title"])

    def test_bracket_prefix_still_finds_marks(self):
        r = parser.parse("[某字幕组] 某某番 - 03 [1080P][简繁内封].mkv")
        self.assertTrue(r["marks"])

    def test_leading_bracket_group_captured(self):
        r = parser.parse("[Group] Some Anime - 03 [1080p]")
        self.assertIn("Some Anime", r["title"])


class TestDigitEpisode(unittest.TestCase):
    """' - 03 ' 这类纯数字集号在动漫/字幕组命名里极其常见。"""

    def test_dash_digit_episode(self):
        r = parser.parse("Some Anime - 03 [1080p].mkv")
        self.assertEqual(r["episode"], 3)

    def test_dash_digit_episode_multi_digit(self):
        r = parser.parse("Some Anime - 245 [1080p].mkv")
        self.assertEqual(r["episode"], 245)

    def test_year_not_mistaken_for_episode(self):
        # 年份不能被误判成集号
        r = parser.parse("Some.Movie.2019.1080p.BluRay.x264-GROUP")
        self.assertIsNone(r["episode"])

    def test_batch_range_not_mistaken_for_episode(self):
        r = parser.parse("Some Show 001-500 Complete Series [1080p]")
        self.assertTrue(r["is_batch"])
        self.assertIsNone(r["episode"])
