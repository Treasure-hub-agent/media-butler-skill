import os, tempfile, unittest
from unittest import mock

from lib import doctor, indexer


def _add(conn, path, **kw):
    rec = {"title": "T", "year": 2020, "media_type": "movie", "path": path, "size": 1}
    rec.update(kw)
    return indexer.add(conn, rec)


class TestLibraryCheck(unittest.TestCase):
    def test_detects_missing_file(self):
        d = tempfile.mkdtemp()
        c = indexer.init_db(os.path.join(d, "db.sqlite"))
        indexer.add(c, {"title": "T", "year": 2020, "media_type": "movie",
                        "path": os.path.join(d, "gone.mkv"), "size": 1})
        rep = doctor.check_library(c, d)
        self.assertEqual(len(rep["missing_files"]), 1)

    def test_clean_library_has_no_issues(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "x.mkv")
        open(f, "w").close()
        c = indexer.init_db(os.path.join(d, "db.sqlite"))
        indexer.add(c, {"title": "T", "year": 2020, "media_type": "movie",
                        "path": f, "size": 1})
        rep = doctor.check_library(c, d)
        self.assertEqual(rep["missing_files"], [])

    def test_reports_zero_byte_and_orphan_subs(self):
        with tempfile.TemporaryDirectory() as d:
            empty = os.path.join(d, "empty.mkv")
            with open(empty, "w"):
                pass                                       # 0 字节：下载未完成的残留
            video = os.path.join(d, "Movie (2019).mkv")
            with open(video, "w") as fh:
                fh.write("x")                              # 有内容的正常视频
            sidecar = os.path.join(d, "Movie (2019).zh.srt")   # 有配对视频，不算孤儿
            open(sidecar, "w").close()
            orphan = os.path.join(d, "Lonely.srt")             # 无配对视频
            open(orphan, "w").close()
            c = indexer.init_db(os.path.join(d, "db.sqlite"))
            _add(c, empty, size=0)
            _add(c, video)
            rep = doctor.check_library(c, d)
            self.assertEqual(rep["zero_byte"], [empty])
            self.assertEqual(rep["missing_files"], [])
            self.assertEqual(rep["subtitle_files"], 2)
            self.assertEqual(rep["orphan_subs"], [orphan])

    def test_probe_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "x.mkv"), "w").close()
            c = indexer.init_db(os.path.join(d, "db.sqlite"))
            _add(c, os.path.join(d, "x.mkv"))
            before = sorted(os.listdir(d))
            doctor.check_library(c, d)
            self.assertEqual(sorted(os.listdir(d)), before)   # 巡检只读，不留痕

    def test_handles_empty_path_rows(self):
        with tempfile.TemporaryDirectory() as d:
            c = indexer.init_db(os.path.join(d, "db.sqlite"))
            _add(c, "")
            rep = doctor.check_library(c, d)
            self.assertEqual(rep["missing_files"], [])


class TestCheckSources(unittest.TestCase):
    class _Fake:
        def __init__(self, sid, ok, script="both"):
            self.id, self.ok, self.query_script = sid, ok, script

        def health(self, proxy=""):
            self.proxy = proxy
            if isinstance(self.ok, Exception):
                raise self.ok
            return self.ok

    def _run(self, srcs, cfg):
        with mock.patch.object(doctor.sources, "registry", lambda c=None: srcs):
            return doctor.check_sources(cfg)

    def test_reports_each_source(self):
        rep = self._run([self._Fake("a", True), self._Fake("b", False)], {})
        self.assertEqual([r["id"] for r in rep], ["a", "b"])
        self.assertEqual([r["reachable"] for r in rep], [True, False])

    def test_health_exception_is_unreachable_not_crash(self):
        rep = self._run([self._Fake("a", RuntimeError("boom"))], {})
        self.assertEqual(rep, [{"id": "a", "reachable": False, "query_script": "both"}])

    def test_proxy_from_cfg_is_used(self):
        f = self._Fake("a", True)
        self._run([f], {"proxy": "http://127.0.0.1:7890"})
        self.assertEqual(f.proxy, "http://127.0.0.1:7890")


class TestFsCapabilities(unittest.TestCase):
    def test_same_dir_reports_same_fs(self):
        d = tempfile.mkdtemp()
        cap = doctor.fs_capabilities(d, d)
        self.assertTrue(cap["same_fs"])
        self.assertTrue(cap["hardlink"])

    def test_probe_reports_hardlink_by_actual_test(self):
        # 能力探针：实际建临时文件试 link()，比查表更可靠
        d = tempfile.mkdtemp()
        cap = doctor.fs_capabilities(d, d)
        self.assertIn("fs_type", cap)

    def test_probe_cleans_up_after_itself(self):
        with tempfile.TemporaryDirectory() as d:
            cap = doctor.fs_capabilities(d, d)
            self.assertTrue(cap["hardlink"])
            self.assertEqual(os.listdir(d), [])      # 探针文件已清理

    def test_cross_directory_probe(self):
        with tempfile.TemporaryDirectory() as d:
            src, dest = os.path.join(d, "dl"), os.path.join(d, "lib")
            os.mkdir(src); os.mkdir(dest)
            cap = doctor.fs_capabilities(src, dest)
            self.assertTrue(cap["same_fs"])
            self.assertTrue(cap["hardlink"])
            self.assertEqual(os.listdir(src), [])
            self.assertEqual(os.listdir(dest), [])

    def test_read_only_when_dest_missing(self):
        # 巡检只读：目标目录不存在时不代建，明确报不可用
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "not-created-yet")
            cap = doctor.fs_capabilities(d, dest)
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(cap["hardlink"])

    def test_survives_empty_paths(self):
        cap = doctor.fs_capabilities("", "")
        self.assertFalse(cap["hardlink"])
        self.assertIsInstance(cap["fs_type"], str)

    @unittest.skipUnless(
        os.path.isdir("/dev/shm")
        and os.stat("/dev/shm").st_dev != os.stat(tempfile.gettempdir()).st_dev,
        "需要两个不同的文件系统")
    def test_cross_fs_hardlink_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            cap = doctor.fs_capabilities(d, "/dev/shm")
            self.assertFalse(cap["same_fs"])
            self.assertFalse(cap["hardlink"])

    def test_fs_type_resolved_from_proc_mounts(self):
        if not os.path.exists("/proc/mounts"):
            self.skipTest("无 /proc/mounts")
        d = tempfile.mkdtemp()
        self.assertNotEqual(doctor.fs_capabilities(d, d)["fs_type"], "unknown")


class TestRegrabCandidates(unittest.TestCase):
    def _db(self, d, rows):
        c = indexer.init_db(os.path.join(d, "db.sqlite"))
        for r in rows:
            indexer.add(c, r)
        return c

    def test_only_lists_candidates_never_grabs(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._db(d, [{"title": "Some Movie", "year": 2020,
                              "media_type": "movie", "path": "/x", "size": 1}])
            calls = []
            with mock.patch.object(doctor.metadata, "best_search_terms",
                                   lambda n, cfg=None: ["Some Movie"]), \
                 mock.patch.object(doctor.sources, "search_all",
                                   lambda q, cfg=None: calls.append(q) or []), \
                 mock.patch.object(doctor.ranker, "rank", lambda r, q, cfg: []):
                out = doctor.regrab_candidates(c, {})
            self.assertEqual(calls, ["Some Movie"])     # 只检索，不下载
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["title"], "Some Movie")
            self.assertIn("reason", out[0])
            self.assertEqual(len(indexer.list_items(c)), 1)   # 索引未被改写
            self.assertFalse(os.path.exists("/x"))

    def test_no_hits_reason_reflects_sub_status(self):
        # 计划口径：有中字标记的条目仍会上报，但原因是「当前条件无可选候选」；
        # 没有中字标记的才叫「未找到中字版本」。
        with tempfile.TemporaryDirectory() as d:
            c = self._db(d, [{"title": "T", "media_type": "movie",
                              "path": "/x", "size": 1, "has_cn_sub": 1}])
            with mock.patch.object(doctor.metadata, "best_search_terms",
                                   lambda n, cfg=None: ["T"]), \
                 mock.patch.object(doctor.sources, "search_all",
                                   lambda q, cfg=None: []), \
                 mock.patch.object(doctor.ranker, "rank", lambda r, q, cfg: []):
                out = doctor.regrab_candidates(c, {})
            self.assertEqual([o["reason"] for o in out], ["当前条件无可选候选"])

    def test_season_only_row_is_skipped(self):
        # 没集号又标称剧集的行无法定位，不产候选
        with tempfile.TemporaryDirectory() as d:
            c = self._db(d, [{"title": "T", "media_type": "tv",
                              "path": "/x", "size": 1}])
            with mock.patch.object(doctor.sources, "search_all",
                                   lambda q, cfg=None: []):
                self.assertEqual(doctor.regrab_candidates(c, {}), [])

    def test_found_results_are_not_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._db(d, [{"title": "T", "media_type": "movie",
                              "path": "/x", "size": 1}])
            sentinel = object()
            with mock.patch.object(doctor.metadata, "best_search_terms",
                                   lambda n, cfg=None: ["T"]), \
                 mock.patch.object(doctor.sources, "search_all",
                                   lambda q, cfg=None: [sentinel]), \
                 mock.patch.object(doctor.ranker, "rank",
                                   lambda r, q, cfg: [sentinel]):
                self.assertEqual(doctor.regrab_candidates(c, {}), [])


if __name__ == "__main__":
    unittest.main()
