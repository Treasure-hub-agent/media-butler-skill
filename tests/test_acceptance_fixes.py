import unittest
from lib import parser


class TestAriaFallenNames(unittest.TestCase):
    """真实下载验收发现的问题：aria2 落盘用的是 torrent 内部名，
    与用户选片时看到的标题形态不同，解析必须都能认。"""

    def test_dash_episode_dash_trailing_stripped(self):
        # 真实样本：'... Frieren - 34 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv'
        r = parser.parse("[Group&Sub] Some Frieren - 34 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv")
        self.assertNotIn("ASSx2", r["title"], r["title"])
        self.assertNotIn("- 34", r["title"], r["title"])
        self.assertIn("Some Frieren", r["title"])
        self.assertEqual(r["episode"], 34)

    def test_ass_x2_implies_chinese_subtitle(self):
        # ASSx2 = 两条 ASS 字幕轨，中文字幕组的常见做法（简繁各一）
        self.assertTrue(parser.has_chinese_subtitle("Anime - 34 [1080p AAC ASSx2].mkv"))

    def test_ass_track_marker_implies_chinese_subtitle(self):
        self.assertTrue(parser.has_chinese_subtitle("Anime [1080p][ASS].mkv"))

    def test_plain_mkv_not_flagged(self):
        self.assertFalse(parser.has_chinese_subtitle("Some.Movie.2019.1080p.BluRay.mkv"))

    def test_frieren_real_name(self):
        r = parser.parse(
            "[Nekomoe kissaten&LoliHouse] Sousou no Frieren - 34 "
            "[WebRip 1080p HEVC-10bit AAC ASSx2].mkv")
        self.assertEqual(r["episode"], 34)
        self.assertTrue(parser.has_chinese_subtitle(
            "[Nekomoe kissaten&LoliHouse] Sousou no Frieren - 34 "
            "[WebRip 1080p HEVC-10bit AAC ASSx2].mkv"))
        self.assertNotIn("ASSx2", r["title"])
