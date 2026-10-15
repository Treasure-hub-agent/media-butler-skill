import os, tempfile, struct, unittest
from lib import subtitles


def _fake_mkv(path: str, track_names: list) -> None:
    """造一个带 EBML 头部与指定轨道名的伪 mkv，用于测试内嵌字幕探测。

    EBML 字符串元素的长度以**字节数**计（不是字符数），中文名是多字节。
    """
    ebml = b"\x1a\x45\xdf\xa3"
    body = b""
    for name in track_names:
        raw = name.encode("utf-8")
        # 轨道名以 EBML 字符串元素形式出现（0x53 6E = Name）
        body += b"\x53\x6e" + bytes([len(raw) | 0x80]) + raw
    with open(path, "wb") as f:
        f.write(ebml + body)


class TestEmbeddedSubtitleDetection(unittest.TestCase):
    """视频自带内嵌中文字幕时不应再提示「未找到字幕」。

    用户看到「未找到中文字幕」会以为要额外补，而文件其实已经能正常看中字。
    """

    def test_detects_zh_hans_track(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            _fake_mkv(v, ["zh-Hans", "English"])
            r = subtitles.detect_embedded(v)
            self.assertTrue(r["has_chinese"], r)
            self.assertIn("zh-Hans", r["tracks"])

    def test_detects_simplified_named_track(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            _fake_mkv(v, ["简体中文", "繁體中文"])
            r = subtitles.detect_embedded(v)
            self.assertTrue(r["has_chinese"])

    def test_real_world_fansub_track_names(self):
        # 真实样本的字幕轨名常写作「简日双语」/「繁日雙語」（简繁 + 日 + 双语）
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            _fake_mkv(v, ["简日双语", "繁日雙語"])
            r = subtitles.detect_embedded(v)
            self.assertTrue(r["has_chinese"], r)

    def test_english_only_track_not_chinese(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            _fake_mkv(v, ["English", "Français"])
            r = subtitles.detect_embedded(v)
            self.assertFalse(r["has_chinese"])

    def test_nonexistent_file_returns_false(self):
        r = subtitles.detect_embedded("/nonexistent/x.mkv")
        self.assertFalse(r["has_chinese"])

    def test_plain_file_without_mkv_header(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "Movie.mkv")
            with open(v, "wb") as f:
                f.write(b"not a matroska file at all")
            r = subtitles.detect_embedded(v)
            self.assertFalse(r["has_chinese"])
