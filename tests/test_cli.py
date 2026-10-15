"""CLI 命令集与流程编排的测试。

全部用例不触网：涉及网络的 lib 函数一律 mock，
这样「跑通 CLI」不依赖源站/字幕站的可用性。
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import media  # noqa: E402
from lib import config, indexer  # noqa: E402
from lib.sources.base import Result  # noqa: E402


def run(*argv):
    """跑一次 CLI，返回 (exit_code, stdout)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = media.main(list(argv))
    return code, buf.getvalue()


def jout(out):
    return json.loads(out)


class FakeSource:
    id = "fake"
    query_script = "latin"

    def health(self, proxy=""):
        return True


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old_home = os.environ.get("MEDIA_BUTLER_HOME")
        os.environ["MEDIA_BUTLER_HOME"] = os.path.join(self.tmp, "state")
        # 环境里的代理会干扰代理相关用例，先摘掉
        self._old_proxy = {k: os.environ.pop(k, None) for k in
                           ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
                            "https_proxy", "HTTPS_PROXY")}

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("MEDIA_BUTLER_HOME", None)
        else:
            os.environ["MEDIA_BUTLER_HOME"] = self._old_home
        for k, v in self._old_proxy.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def touch(self, *parts, data="x"):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(data)
        return p

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestParseAndHelp(CliBase):
    def test_parse_outputs_json(self):
        code, out = run("parse", "Some.Movie.2019.1080p.中字.mkv")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["year"], 2019)

    def test_parse_marks_are_json_serialisable(self):
        code, out = run("parse", "Some.Movie.2019.1080p.中字.mkv")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertIsInstance(data["marks"], list)
        self.assertIn("中字", data["marks"])

    def test_parse_detects_episode(self):
        code, out = run("parse", "Some.Show.2021.S02E07.1080p.WEB-DL.mkv")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual((data["season"], data["episode"]), (2, 7))

    def test_no_args_shows_help(self):
        code, out = run()
        self.assertEqual(code, 1)
        self.assertIn("usage", out)

    def test_unknown_command_fails(self):
        with self.assertRaises(SystemExit):
            run("nope")


class TestMetaSearch(CliBase):
    def test_meta_returns_terms(self):
        with mock.patch.object(media.metadata, "lookup",
                               return_value={"title": "Romaji", "year": 2011}):
            code, out = run("meta", "某片名")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["meta"]["title"], "Romaji")
        self.assertIn("某片名", data["terms"])

    def test_search_ranks_and_marks_cn_sub(self):
        hits = [
            Result(title="Some.Movie.2019.1080p.中字.mkv",
                   magnet="magnet:?xt=urn:btih:aaa", size=2 * 10 ** 9, seeders=10),
            Result(title="Some.Movie.2019.2160p.mkv",
                   magnet="magnet:?xt=urn:btih:bbb", size=8 * 10 ** 9, seeders=99),
        ]
        with mock.patch.object(media, "search_all", return_value=hits), \
                mock.patch.object(media.metadata, "best_search_terms",
                                  return_value=["Some Movie 2019"]):
            code, out = run("search", "Some Movie 2019", "--limit", "5")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["count"], 2)
        self.assertTrue(data["results"][0]["has_cn_sub"])   # 中字优先
        self.assertTrue(data["results"][0]["magnet"].startswith("magnet:"))

    def test_search_limit_is_respected(self):
        hits = [Result(title="Some.Movie.2019.%dp.mkv" % (i + 100),
                       magnet="magnet:?xt=urn:btih:%d" % i, seeders=i)
                for i in range(10)]
        with mock.patch.object(media, "search_all", return_value=hits), \
                mock.patch.object(media.metadata, "best_search_terms",
                                  return_value=["Some Movie"]):
            code, out = run("search", "Some Movie", "--limit", "3")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["count"], 3)


class TestGrab(CliBase):
    MAGNET = "magnet:?xt=urn:btih:0123456789abcdef"

    def test_no_aria2_outputs_magnet_and_hints(self):
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=False):
            code, out = run("grab", self.MAGNET)
        self.assertEqual(code, 0)                 # 不报错退出
        data = jout(out)
        self.assertEqual(data["status"], "no-downloader")
        self.assertEqual(data["magnet"], self.MAGNET)
        self.assertTrue(data["suggestions"])

    def test_starts_async_download(self):
        started = {"pid": 4242, "log": "/tmp/aria2.log", "dest": "/tmp/dl",
                   "cmd": ["aria2c", self.MAGNET]}
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=True), \
                mock.patch.object(media.downloader, "start",
                                  return_value=started) as st:
            code, out = run("grab", self.MAGNET, "--dest", self.path("dl"),
                            "--select", "1,3")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["status"], "started")
        self.assertEqual(data["pid"], 4242)
        self.assertEqual(st.call_args.kwargs["select_files"], [1, 3])

    def test_bad_select_is_rejected(self):
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=True):
            code, out = run("grab", self.MAGNET, "--select", "1,x")
        self.assertEqual(code, 1)
        self.assertIn("error", jout(out)["status"])

    def test_socks_proxy_is_warned_not_silently_bypassed(self):
        config.save({"proxy": "socks5://127.0.0.1:1080"})
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=True), \
                mock.patch.object(media.downloader, "start") as st:
            code, out = run("grab", self.MAGNET, "--dest", self.path("dl"))
        data = jout(out)
        self.assertEqual(data["status"], "proxy-unsupported")
        self.assertFalse(st.called)               # 不静默直连
        self.assertTrue(any("socks" in w.lower() for w in data["warnings"]))
        self.assertEqual(data["magnet"], self.MAGNET)

    def test_allow_direct_is_explicit_opt_in(self):
        config.save({"proxy": "socks5://127.0.0.1:1080"})
        started = {"pid": 7, "log": "/tmp/aria2.log", "dest": "/tmp/dl", "cmd": []}
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=True), \
                mock.patch.object(media.downloader, "start",
                                  return_value=started):
            code, out = run("grab", self.MAGNET, "--dest", self.path("dl"),
                            "--allow-direct")
        data = jout(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["status"], "started")
        self.assertTrue(any("socks" in w.lower() for w in data["warnings"]))

    def test_dry_run_does_not_start(self):
        with mock.patch.object(media.downloader, "aria2_available",
                               return_value=True), \
                mock.patch.object(media.downloader, "start") as st:
            code, out = run("grab", self.MAGNET, "--dry-run")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["status"], "dry-run")
        self.assertIn("cmd", data)
        self.assertFalse(st.called)


class TestStatus(CliBase):
    def test_status_reports_incomplete(self):
        d = self.path("dl")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "half.mkv.aria2"), "w") as f:
            f.write("x")
        with open(os.path.join(d, "aria2.log"), "w", encoding="utf-8") as f:
            f.write("line1\nline2\nline3\n")
        code, out = run("status", "--dest", d, "--lines", "2")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(len(data["incomplete"]), 1)
        self.assertIn("line3", data["tail"])
        self.assertNotIn("line1", data["tail"])

    def test_status_on_missing_dir_is_clean(self):
        code, out = run("status", "--dest", self.path("nope"))
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["incomplete"], [])


class TestSubs(CliBase):
    def test_local_subtitle_short_circuits(self):
        video = self.touch("dl", "Some.Movie.2019.mkv")
        self.touch("dl", "Some.Movie.2019.srt")
        with mock.patch.object(media.subtitles, "search") as s:
            code, out = run("subs", "--file", video)
        data = jout(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["status"], "found-local")
        self.assertTrue(data["path"].endswith(".srt"))
        self.assertFalse(s.called)

    def test_dry_run_lists_candidates_without_fetch(self):
        cand = [{"name": "a.srt", "lang": "chi", "downloads": 5,
                 "format": "srt", "url": "http://x/a.gz"}]
        with mock.patch.object(media.subtitles, "search", return_value=cand), \
                mock.patch.object(media.subtitles, "fetch") as fe:
            code, out = run("subs", "Some Movie 2019", "--dry-run")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["status"], "candidates")
        self.assertEqual(len(data["results"]), 1)
        self.assertFalse(fe.called)

    def test_fetch_saves_next_to_video(self):
        video = self.touch("dl", "Some.Movie.2019.mkv")
        cand = [{"name": "a.srt", "lang": "chi", "downloads": 5,
                 "format": "srt", "url": "http://x/a.gz"}]
        saved = self.path("dl", "subtitle.srt")
        with mock.patch.object(media.subtitles, "search", return_value=cand), \
                mock.patch.object(media.subtitles, "fetch",
                                  return_value=saved) as fe:
            code, out = run("subs", "--file", video)
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["status"], "ok")
        self.assertEqual(fe.call_args[0][1], os.path.dirname(video))

    def test_not_found_is_not_an_error(self):
        with mock.patch.object(media.subtitles, "search", return_value=[]):
            code, out = run("subs", "Nonexistent Movie 1900")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["status"], "not-found")

    def test_fetch_failure_returns_1(self):
        cand = [{"name": "a.srt", "lang": "chi", "downloads": 5,
                 "format": "srt", "url": "http://x/a.gz"}]
        with mock.patch.object(media.subtitles, "search", return_value=cand), \
                mock.patch.object(media.subtitles, "fetch", return_value=""):
            code, out = run("subs", "Some Movie 2019")
        self.assertEqual(code, 1)
        self.assertEqual(jout(out)["status"], "download-failed")


class TestIngest(CliBase):
    def test_dry_run_outputs_plan(self):
        self.touch("dl", "Some.Movie.2019.1080p.mkv")
        code, out = run("ingest", self.path("dl"),
                        "--library", self.path("lib"), "--dry-run")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["status"], "dry-run")
        self.assertIn("Some Movie", out)
        self.assertEqual(data["media_type"], "movie")
        self.assertTrue(os.path.join("电影", "") in out)

    def test_auto_type_tv_when_episode_present(self):
        """已知坑：剧集被识别成 movie 会落进「电影/」目录。"""
        self.touch("dl", "Some.Show.2021.S01E02.1080p.WEB-DL.mkv")
        code, out = run("ingest", self.path("dl"),
                        "--library", self.path("lib"), "--dry-run")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["media_type"], "tv")
        dest = data["plan"][0]["dest"]
        self.assertIn("剧集", dest)
        self.assertIn("Season 01", dest)
        self.assertNotIn("电影", dest)

    def test_auto_type_anime_from_path_hint(self):
        self.touch("dl", "动漫", "Some.Anime.2022.S01E03.mkv")
        code, out = run("ingest", self.path("dl"),
                        "--library", self.path("lib"), "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["media_type"], "anime")

    def test_explicit_type_overrides_detection(self):
        self.touch("dl", "Some.Show.2021.S01E02.mkv")
        code, out = run("ingest", self.path("dl"), "--library", self.path("lib"),
                        "--dry-run", "--type", "movie")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["media_type"], "movie")
        self.assertIn("电影", data["plan"][0]["dest"])

    def test_dry_run_writes_nothing(self):
        self.touch("dl", "Some.Movie.2019.mkv")
        run("ingest", self.path("dl"), "--library", self.path("lib"),
            "--dry-run")
        self.assertFalse(os.path.exists(self.path("lib")))
        self.assertFalse(os.path.exists(self.path("state", "library.db")))

    def test_real_ingest_moves_and_indexes_and_exports(self):
        self.touch("dl", "Some.Movie.2019.1080p.中字.mkv")
        lib = self.path("lib")
        code, out = run("ingest", self.path("dl"), "--library", lib)
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["moved"], 1)
        dest = os.path.join(lib, "电影", "Some Movie (2019)",
                            "Some Movie (2019).mkv")
        self.assertTrue(os.path.exists(dest))
        # 源文件已移走
        self.assertFalse(os.path.exists(self.path("dl", "Some.Movie.2019.1080p.中字.mkv")))
        # 索引 + 双轨清单
        self.assertTrue(os.path.exists(data["index"]["json"]))
        self.assertTrue(os.path.exists(data["index"]["markdown"]))
        conn = indexer.init_db(self.path("state", "library.db"))
        items = indexer.list_items(conn)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["path"], dest)
        self.assertEqual(items[0]["has_cn_sub"], 1)
        self.assertEqual(items[0]["media_type"], "movie")
        with open(data["index"]["markdown"], encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("Some Movie", md)

    def test_ingest_tv_episode_is_indexed_with_season_episode(self):
        self.touch("dl", "Some.Show.2021.S01E02.1080p.mkv")
        lib = self.path("lib")
        code, out = run("ingest", self.path("dl"), "--library", lib)
        self.assertEqual(code, 0)
        conn = indexer.init_db(self.path("state", "library.db"))
        it = indexer.list_items(conn)[0]
        self.assertEqual((it["season"], it["episode"]), (1, 2))
        self.assertEqual(it["media_type"], "tv")
        self.assertTrue(it["path"].endswith("Some Show S01E02.mkv"))

    def test_ingest_is_idempotent_on_second_run(self):
        self.touch("dl", "Some.Movie.2019.mkv")
        run("ingest", self.path("dl"), "--library", self.path("lib"))
        self.touch("dl", "Some.Movie.2019.mkv")      # 再下一次同样的片子
        code, out = run("ingest", self.path("dl"), "--library", self.path("lib"))
        self.assertEqual(code, 0)
        conn = indexer.init_db(self.path("state", "library.db"))
        self.assertEqual(len(indexer.list_items(conn)), 1)

    def test_missing_library_is_error(self):
        self.touch("dl", "Some.Movie.2019.mkv")
        code, out = run("ingest", self.path("dl"))
        self.assertEqual(code, 1)
        self.assertEqual(jout(out)["status"], "error")

    def test_missing_src_is_error(self):
        code, out = run("ingest", self.path("nope"), "--library", self.path("lib"))
        self.assertEqual(code, 1)
        self.assertEqual(jout(out)["status"], "error")

    def test_junk_and_non_media_are_skipped(self):
        self.touch("dl", "Some.Movie.2019.mkv")
        self.touch("dl", "readme.txt", data="hi")
        self.touch("dl", "Some.Other.2018.mkv.aria2", data="")
        code, out = run("ingest", self.path("dl"), "--library", self.path("lib"),
                        "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["count"], 1)

    def test_failed_archive_is_not_indexed(self):
        """跳过/失败/拒复制的条目绝不入索引（否则索引会指向不存在的文件）。"""
        self.touch("dl", "Some.Movie.2019.mkv")
        fake_log = [{"src": self.path("dl", "Some.Movie.2019.mkv"),
                     "dest": self.path("lib", "电影", "Some Movie (2019)",
                                       "Some Movie (2019).mkv"),
                     "result": "error:disk-full"}]
        with mock.patch.object(media.organizer, "execute", return_value=fake_log):
            code, out = run("ingest", self.path("dl"), "--library", self.path("lib"))
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["moved"], 0)
        conn = indexer.init_db(self.path("state", "library.db"))
        self.assertEqual(indexer.list_items(conn), [])

    def test_copy_fallback_variants_are_indexed(self):
        """``*+copied`` 回退（跨设备/硬链接失败的组合值）也是归档成功，必须入索引。

        结果值形如 ``hardlink-failed-18+copied``：白名单容易漏判，
        故按「目标文件是否存在」这一事实判定。
        """
        for result in ("hardlink-failed-18+copied",
                       "hardlink-unavailable-EXDEV+copied",
                       "moved-cross-device-copied"):
            with self.subTest(result=result):
                shutil.rmtree(self.path("state"), ignore_errors=True)
                shutil.rmtree(self.path("lib"), ignore_errors=True)
                src = self.touch("dl", "Some.Movie.2019.mkv")
                dest = self.path("lib", "电影", "Some Movie (2019)",
                                 "Some Movie (2019).mkv")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)          # 模拟「文件已落到目标位」
                fake_log = [{"src": src, "dest": dest, "result": result}]
                with mock.patch.object(media.organizer, "execute",
                                       return_value=fake_log):
                    code, out = run("ingest", self.path("dl"),
                                    "--library", self.path("lib"))
                self.assertEqual(code, 0)
                self.assertEqual(jout(out)["moved"], 1, result)
                conn = indexer.init_db(self.path("state", "library.db"))
                self.assertEqual([i["path"] for i in indexer.list_items(conn)],
                                 [dest], result)

    def test_refused_large_copy_is_not_indexed(self):
        """拒复制的大文件不在目标位，即便 result 非 error 前缀也不得入索引。"""
        self.touch("dl", "Some.Movie.2019.mkv")
        fake_log = [{"src": self.path("dl", "Some.Movie.2019.mkv"),
                     "dest": self.path("lib", "电影", "Some Movie (2019)",
                                       "Some Movie (2019).mkv"),
                     "result": "refused-large-copy-copy:3000000000>2147483648"}]
        with mock.patch.object(media.organizer, "execute", return_value=fake_log):
            code, out = run("ingest", self.path("dl"), "--library", self.path("lib"))
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["moved"], 0)
        conn = indexer.init_db(self.path("state", "library.db"))
        self.assertEqual(indexer.list_items(conn), [])


class TestIndex(CliBase):
    def _seed(self):
        lib = self.path("lib")
        self.touch("lib", "电影", "T (2020)", "T (2020).mkv")
        self.touch("lib", "剧集", "S (2021)", "Season 01", "S S01E01.mkv")
        self.touch("lib", "剧集", "S (2021)", "Season 01", "S S01E03.mkv")
        return lib

    def test_rebuild_from_disk(self):
        lib = self._seed()
        code, out = run("index", "rebuild", "--library", lib)
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["rebuilt"], 3)
        conn = indexer.init_db(self.path("state", "library.db"))
        self.assertEqual(len(indexer.list_items(conn)), 3)

    def test_rebuild_dry_run_writes_nothing(self):
        lib = self._seed()
        code, out = run("index", "rebuild", "--library", lib, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["status"], "dry-run")
        conn = indexer.init_db(self.path("state", "library.db"))
        self.assertEqual(indexer.list_items(conn), [])

    def test_ingest_then_rebuild_keeps_title_clean(self):
        """归档规范命名「片名 (年份)」再重建，标题不得残留半截括号。

        这是 ingest → index rebuild 的往返约定：规整过的目录名必须能被
        自己的解析器原样读回，否则重建出来的目录会越滚越脏。
        """
        self.touch("dl", "Some.Movie.2019.1080p.中字.mkv")
        lib = self.path("lib")
        run("ingest", self.path("dl"), "--library", lib)
        code, out = run("index", "rebuild", "--library", lib)
        self.assertEqual(code, 0)
        items = indexer.list_items(indexer.init_db(self.path("state", "library.db")))
        titles = {i["title"] for i in items}
        self.assertEqual(titles, {"Some Movie"}, titles)
        for i in items:
            self.assertNotIn("(", i["title"], i["title"])

    def test_ingest_tv_then_rebuild_keeps_season_episode(self):
        self.touch("dl", "Some.Show.2021.S01E02.1080p.mkv")
        lib = self.path("lib")
        run("ingest", self.path("dl"), "--library", lib)
        run("index", "rebuild", "--library", lib)
        items = indexer.list_items(indexer.init_db(self.path("state", "library.db")))
        self.assertEqual({(i["season"], i["episode"]) for i in items}, {(1, 2)})
        self.assertEqual({i["media_type"] for i in items}, {"tv"})

    def test_list_stats_export(self):
        run("index", "rebuild", "--library", self._seed())
        code, out = run("index", "list")
        self.assertEqual(code, 0)
        self.assertEqual(len(jout(out)), 3)

        code, out = run("index", "stats")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["count"], 3)

        code, out = run("index", "export")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertTrue(os.path.exists(data["json"]))
        self.assertTrue(os.path.exists(data["markdown"]))

    def test_missing_episodes(self):
        run("index", "rebuild", "--library", self._seed())
        code, out = run("index", "missing", "--title", "S", "--season", "1",
                        "--expect", "4")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out), [2, 4])

    def test_rebuild_without_library_falls_back_to_config(self):
        config.save({"library_root": self._seed()})
        code, out = run("index", "rebuild")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["rebuilt"], 3)


class TestDoctor(CliBase):
    def test_sources(self):
        with mock.patch.object(media.sources, "registry",
                               lambda cfg=None: [FakeSource()]):
            code, out = run("doctor", "sources")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out), [{"id": "fake", "reachable": True,
                                      "query_script": "latin"}])

    def test_library_reports_missing_file(self):
        lib = self.path("lib")
        os.makedirs(lib, exist_ok=True)
        conn = indexer.init_db(self.path("state", "library.db"))
        indexer.add(conn, {"title": "T", "media_type": "movie",
                           "path": self.path("lib", "gone.mkv"), "size": 1})
        code, out = run("doctor", "library", "--library", lib)
        self.assertEqual(code, 0)
        self.assertEqual(len(jout(out)["missing_files"]), 1)

    def test_fs_capabilities(self):
        lib = self.path("lib")
        os.makedirs(lib, exist_ok=True)
        code, out = run("doctor", "fs", "--src", lib, "--dest", lib)
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertTrue(data["same_fs"])
        self.assertTrue(data["hardlink"])
        # 探针文件必须清理干净
        self.assertEqual([f for f in os.listdir(lib) if f.startswith(".mb-")], [])

    def test_regrab_is_candidate_only(self):
        lib = self.path("lib")
        os.makedirs(lib, exist_ok=True)
        conn = indexer.init_db(self.path("state", "library.db"))
        indexer.add(conn, {"title": "No Cn Sub Movie", "media_type": "movie",
                           "year": 2019, "path": self.path("lib", "a.mkv"),
                           "size": 1, "has_cn_sub": 0})
        with mock.patch.object(media, "search_all", return_value=[]):
            code, out = run("doctor", "regrab")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(len(data["candidates"]), 1)
        self.assertIn("仅候选清单", data["note"])


class TestConfig(CliBase):
    def test_set_and_get_roundtrip(self):
        code, out = run("config", "--set", "library_root=/data/media",
                        "--set", "subtitle_priority=false",
                        "--set", "concurrency=5")
        self.assertEqual(code, 0)
        data = jout(out)
        self.assertEqual(data["library_root"], "/data/media")
        self.assertIs(data["subtitle_priority"], False)
        self.assertEqual(data["concurrency"], 5)
        self.assertEqual(config.load()["library_root"], "/data/media")

    def test_get_shows_state_dir(self):
        code, out = run("config")
        self.assertEqual(code, 0)
        self.assertEqual(jout(out)["state_dir"], self.path("state"))

    def test_set_dry_run_does_not_persist(self):
        code, out = run("config", "--set", "library_root=/nope", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry_run", jout(out))
        self.assertEqual(config.load()["library_root"], "")


if __name__ == "__main__":
    unittest.main()
