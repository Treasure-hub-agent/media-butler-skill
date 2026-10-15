"""索引与文本清单导出测试。

覆盖：CRUD、不持久化磁力/info_hash、缺集计算、json/md 导出可读、
WAL 模式、以及索引可从磁盘重建。
"""
import json, os, tempfile, unittest
from lib import indexer


def _conn():
    d = tempfile.mkdtemp()
    return indexer.init_db(os.path.join(d, "lib.db"))


class TestCrud(unittest.TestCase):
    def test_add_and_list(self):
        c = _conn()
        indexer.add(c, {"title": "Some Movie", "year": 2019, "media_type": "movie",
                        "path": "/lib/电影/Some Movie (2019)/x.mkv", "size": 100})
        items = indexer.list_items(c)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Some Movie")
        self.assertEqual(items[0]["year"], 2019)
        self.assertEqual(items[0]["size"], 100)

    def test_no_magnet_persisted(self):
        c = _conn()
        indexer.add(c, {"title": "T", "year": 2020, "media_type": "movie",
                        "path": "/x", "size": 1})
        cols = indexer.columns(c)
        self.assertNotIn("magnet", cols)
        self.assertNotIn("info_hash", cols)
        # 表结构整体也不得出现磁力类字段
        self.assertFalse([c for c in cols if "magnet" in c or "hash" in c or "url" in c])

    def test_same_path_does_not_duplicate(self):
        c = _conn()
        rec = {"title": "T", "year": 2020, "media_type": "movie",
               "path": "/x", "size": 1}
        indexer.add(c, rec)
        indexer.add(c, rec)
        self.assertEqual(len(indexer.list_items(c)), 1)


class TestMissing(unittest.TestCase):
    def test_find_missing(self):
        c = _conn()
        for ep in (1, 2, 4):
            indexer.add(c, {"title": "Show", "year": 2020, "media_type": "tv",
                            "season": 1, "episode": ep, "path": "/x%d" % ep, "size": 1})
        self.assertEqual(indexer.find_missing_episodes(c, "Show", season=1, expect=5), [3, 5])
        # 无 expect 时按已入库最大集号推断
        self.assertEqual(indexer.find_missing_episodes(c, "Show", season=1), [3])


class TestExport(unittest.TestCase):
    def test_export_json_readable(self):
        c = _conn()
        indexer.add(c, {"title": "T", "year": 2020, "media_type": "movie",
                        "path": "/x", "size": 1})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "library.json")
            indexer.export_json(c, p)
            with open(p, encoding="utf-8") as f:
                data = json.loads(f.read())
            self.assertEqual(len(data), 1)

    def test_export_markdown_has_title(self):
        c = _conn()
        indexer.add(c, {"title": "T", "year": 2020, "media_type": "movie",
                        "path": "/x", "size": 1})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "LIBRARY.md")
            indexer.export_markdown(c, p)
            with open(p, encoding="utf-8") as f:
                self.assertIn("T", f.read())


class TestDurability(unittest.TestCase):
    def test_wal_mode_enabled(self):
        c = _conn()
        self.assertEqual(
            str(c.execute("PRAGMA journal_mode").fetchone()[0]).lower(), "wal")


class TestRebuild(unittest.TestCase):
    def test_rebuild_from_disk_uses_names_and_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            ep = os.path.join(d, "剧集", "Some Show (2020)", "Season 01")
            os.makedirs(ep)
            for n in (1, 2, 4):
                with open(os.path.join(ep, "Some Show S01E%02d.mkv" % n), "w") as f:
                    f.write("x" * 10)
            with open(os.path.join(ep, "Some Show S01E01.srt"), "w") as f:
                f.write("sub")
            with open(os.path.join(ep, "Some Show S01E01.aria2"), "w") as f:
                f.write("ctl")

            rows = indexer.rebuild_from_disk(d)
            eps = sorted(r["episode"] for r in rows if r["episode"] is not None)
            self.assertEqual(eps, [1, 2, 4])
            self.assertEqual(len(rows), 3)          # 字幕与控制文件不入索引
            self.assertTrue(all(r["media_type"] == "tv" for r in rows))
            self.assertTrue(all(r["title"] for r in rows))
            self.assertTrue(all(r["path"] and r["size"] == 10 for r in rows))

    def test_rebuild_is_idempotent_when_re_added(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "电影", "A Movie (2019)")
            os.makedirs(sub)
            with open(os.path.join(sub, "A Movie (2019).mkv"), "w") as f:
                f.write("x")
            c = indexer.init_db(os.path.join(d, "state", "lib.db"))
            for _ in range(2):
                for r in indexer.rebuild_from_disk(d):
                    indexer.add(c, r)
            self.assertEqual(len(indexer.list_items(c)), 1)


if __name__ == "__main__":
    unittest.main()
