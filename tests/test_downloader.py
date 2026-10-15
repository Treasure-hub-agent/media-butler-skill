"""任务 7 测试：aria2 调用参数构造与合集选集定位。"""
import os, unittest
from unittest import mock

from lib import downloader


MAGNET = "magnet:?xt=urn:btih:AB"


class TestArgs(unittest.TestCase):
    def test_no_preallocation_and_no_seed(self):
        a = downloader.build_args(MAGNET, "/tmp/dl")
        self.assertIn("--file-allocation=none", a)
        self.assertIn("--seed-time=0", a)

    def test_select_file_included(self):
        a = downloader.build_args(MAGNET, "/tmp/dl", select_files=[3])
        self.assertIn("--select-file=3", a)

    def test_select_files_joined(self):
        a = downloader.build_args(MAGNET, "/tmp/dl", select_files=[2, 5])
        self.assertIn("--select-file=2,5", a)

    def test_magnet_is_separate_argv_element(self):
        # 磁力链必须独立成 argv 元素，绝不拼进 shell 字符串
        a = downloader.build_args(MAGNET, "/tmp/dl")
        self.assertIn(MAGNET, a)
        self.assertNotIn("shell", " ".join(a).lower())

    def test_dht_entry_built_in(self):
        a = downloader.build_args(MAGNET, "/tmp/dl")
        self.assertTrue(any("dht-entry-point" in x for x in a))

    def test_tracker_pool_built_in(self):
        a = downloader.build_args(MAGNET, "/tmp/dl")
        joined = " ".join(a)
        self.assertIn("tracker.opentrackr.org", joined)

    def test_proxy_only_when_configured(self):
        a = downloader.build_args(MAGNET, "/tmp/dl", cfg={"proxy": ""})
        self.assertFalse(any("all-proxy" in x for x in a))
        b = downloader.build_args(MAGNET, "/tmp/dl",
                                  cfg={"proxy": "http://127.0.0.1:7890"})
        self.assertTrue(any("all-proxy" in x for x in b))

    # --- 代理格式与环境变量（约束：aria2c 不认 socks，只会报错退出）---

    def test_ignores_user_conf_file(self):
        # ~/.aria2/aria2.conf 可能重新打开预分配/做种，必须显式忽略以免覆盖安全参数
        a = downloader.build_args(MAGNET, "/tmp/dl")
        self.assertIn("--no-conf=true", a)

    def test_socks_proxy_skipped(self):
        # 传 socks 型会让 aria2c 报 unrecognized proxy format，必须跳过而非传给 aria2c
        for bad in ("socks5://127.0.0.1:1080", "socks5h://127.0.0.1:1080",
                    "socks4://127.0.0.1:1080", "socks://127.0.0.1:1080"):
            a = downloader.build_args(MAGNET, "/tmp/dl", cfg={"proxy": bad})
            self.assertFalse(any("all-proxy" in x for x in a), bad)

    def test_http_proxy_passed(self):
        for good in ("http://127.0.0.1:7890", "https://user:pw@127.0.0.1:7890"):
            a = downloader.build_args(MAGNET, "/tmp/dl", cfg={"proxy": good})
            self.assertIn("--all-proxy=" + good, a)

    def test_proxy_from_environment(self):
        with mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:7890"},
                             clear=False):
            os.environ.pop("all_proxy", None)
            os.environ.pop("ALL_PROXY", None)
            os.environ.pop("https_proxy", None)
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)
            a = downloader.build_args(MAGNET, "/tmp/dl")
            self.assertTrue(any("all-proxy" in x for x in a))
            with mock.patch.dict(os.environ, {"ALL_PROXY": "socks5://127.0.0.1:1080"},
                                 clear=False):
                b = downloader.build_args(MAGNET, "/tmp/dl")
                self.assertFalse(any("all-proxy" in x for x in b))

    def test_explicit_empty_proxy_means_direct(self):
        # 配置里显式写空 = 用户要求直连，不得回落到环境变量
        with mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:7890"},
                             clear=False):
            a = downloader.build_args(MAGNET, "/tmp/dl", cfg={"proxy": ""})
            self.assertFalse(any("all-proxy" in x for x in a))

    def test_dest_passed(self):
        a = downloader.build_args(MAGNET, "/tmp/dl")
        self.assertIn("--dir", a)
        self.assertIn("/tmp/dl", a)


class TestSelection(unittest.TestCase):
    def test_pick_file_index_by_episode(self):
        files = [
            {"index": 1, "path": "Show/S01E01.mkv", "length": 10},
            {"index": 2, "path": "Show/S01E02.mkv", "length": 20},
        ]
        self.assertEqual(downloader.pick_index(files, episode=2), 2)

    def test_pick_index_returns_none_when_absent(self):
        files = [{"index": 1, "path": "Show/S01E01.mkv", "length": 10}]
        self.assertIsNone(downloader.pick_index(files, episode=99))

    def test_pick_index_none_episode(self):
        files = [{"index": 1, "path": "Show/S01E01.mkv", "length": 10}]
        self.assertIsNone(downloader.pick_index(files))

    def test_pick_index_respects_season(self):
        files = [
            {"index": 1, "path": "Show/S01E05.mkv", "length": 10},
            {"index": 2, "path": "Show/S02E05.mkv", "length": 10},
        ]
        self.assertEqual(downloader.pick_index(files, episode=5, season=2), 2)

    def test_pick_index_chinese_episode(self):
        files = [{"index": 7, "path": "剧集/第12集.mkv", "length": 10}]
        self.assertEqual(downloader.pick_index(files, episode=12), 7)

    def test_pick_index_episode_word(self):
        files = [{"index": 4, "path": "Show/Episode 08.mkv", "length": 10}]
        self.assertEqual(downloader.pick_index(files, episode=8), 4)


class TestMetadataOnly(unittest.TestCase):
    """metadata_only 的成败判定必须有真凭实据：只看本次新落盘的 .torrent。"""

    def test_returns_new_torrent(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            def fake_run(args, **kw):
                # 模拟 aria2c 落盘 metadata
                (Path(d) / "abc123.torrent").write_bytes(b"d4:infod6:lengthi1eee")
                return mock.Mock(returncode=0)
            with mock.patch("lib.downloader.subprocess.run", fake_run):
                out = downloader.metadata_only(MAGNET, d, timeout=5)
            self.assertTrue(out.endswith("abc123.torrent"))
            self.assertTrue(os.path.isabs(out))

    def test_stale_torrent_not_returned(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "stale.torrent").write_bytes(b"x")  # 上一部片子留下的
            with mock.patch("lib.downloader.subprocess.run",
                            lambda args, **kw: mock.Mock(returncode=1)):
                self.assertEqual(downloader.metadata_only(MAGNET, d, timeout=5), "")

    def test_timeout_is_swallowed(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            def boom(args, **kw):
                raise subprocess.TimeoutExpired(cmd="aria2c", timeout=1)
            with mock.patch("lib.downloader.subprocess.run", boom):
                self.assertEqual(downloader.metadata_only(MAGNET, d, timeout=1), "")

    def test_metadata_flags_present(self):
        import tempfile
        captured = {}

        def fake_run(args, **kw):
            captured["args"] = args
            return mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as d:
            with mock.patch("lib.downloader.subprocess.run", fake_run):
                downloader.metadata_only(MAGNET, d, timeout=5)
        a = captured["args"]
        self.assertIn("--bt-metadata-only=true", a)
        self.assertIn("--bt-save-metadata=true", a)
        self.assertIn("magnet:?xt=urn:btih:AB", a)   # 仍是独立 argv 元素
        self.assertIn("--seed-time=0", a)


class TestAvailability(unittest.TestCase):
    def test_aria2_available_returns_bool(self):
        self.assertIsInstance(downloader.aria2_available(), bool)


if __name__ == "__main__":
    unittest.main()
