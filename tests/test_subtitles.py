"""任务 8 测试：中文字幕结果解析、广告清洗与本地字幕检测。"""
import os, tempfile, unittest
from lib import subtitles

class TestParseResults(unittest.TestCase):
    def test_parse_opensubtitles_payload(self):
        payload = [{
            "SubFileName": "Movie.2019.chs.srt",
            "SubLanguageID": "chi",
            "SubDownloadsCnt": "12620",
            "SubFormat": "srt",
            "SubDownloadLink": "https://example/dl/x.gz",
        }]
        out = subtitles.parse_results(payload)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["downloads"], 12620)
        self.assertEqual(out[0]["url"], "https://example/dl/x.gz")

    def test_parse_skips_items_without_link(self):
        self.assertEqual(subtitles.parse_results([{"SubFileName": "x"}]), [])

class TestCleanSubtitle(unittest.TestCase):
    def test_strips_ad_line(self):
        raw = ("\ufeff1\r\n00:00:06,000 --> 00:00:12,074\r\n"
               "厌倦了搜索字幕?\r\nRay即刻生成字幕:  getray.app\r\n\r\n"
               "2\r\n00:00:58,300 --> 00:01:01,850\r\n真正的台词\r\n")
        cleaned = subtitles.clean_srt(raw)
        self.assertNotIn("getray.app", cleaned)
        self.assertIn("真正的台词", cleaned)

    def test_keeps_normal_subtitle_untouched(self):
        raw = "1\r\n00:00:01,000 --> 00:00:02,000\r\n台词一\r\n"
        self.assertIn("台词一", subtitles.clean_srt(raw))

class TestSearchUrl(unittest.TestCase):
    def test_lowercases_query(self):
        # 实测：路径含大写 ASCII 时服务器 302 到 https://_/... ，必须小写
        u = subtitles.build_search_url("Oppenheimer 2023")
        self.assertIn("query-oppenheimer%202023", u)
        self.assertNotIn("O", u.split("query-")[1])

    def test_search_empty_query_returns_empty(self):
        self.assertEqual(subtitles.search("   "), [])

class TestDetectLocal(unittest.TestCase):
    def test_detect_returns_empty_when_none(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            open(v, "w").close()
            self.assertEqual(subtitles.detect_local(v), "")

    def test_detect_finds_sibling_srt(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            open(v, "w").close()
            s = os.path.join(d, "Movie.srt")
            open(s, "w", encoding="utf-8").close()
            self.assertEqual(os.path.basename(subtitles.detect_local(v)), "Movie.srt")
