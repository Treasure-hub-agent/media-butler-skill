"""归档入库测试：目录规范、路径越界防护、垃圾文件过滤与三级回退。

统一命令（仓库根目录）：python3 -m unittest discover -s tests -t .
"""
import os, shutil, tempfile, unittest

from lib import organizer


def _write(path, data=b""):
    """写文件并确保句柄关闭（避免 ResourceWarning 噪声淹没测试输出）。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def _read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


def _other_fs_dir():
    """找一个与临时目录不同挂载点的可写目录（Linux 上通常是 /dev/shm）。

    硬链接要求同文件系统同挂载点，跨设备（如 /tmp -> /dev/shm）会报
    Invalid cross-device link，因此跨设备回退必须被显式覆盖。
    """
    for cand in ("/dev/shm",):
        if os.path.isdir(cand) and os.access(cand, os.W_OK) and not organizer.same_fs(tempfile.gettempdir(), cand):
            return cand
    return None


class TestTargetPath(unittest.TestCase):
    def test_movie_path(self):
        p = organizer.target_path("/lib", "movie", "Some Movie", 2019, None, None, ".mkv")
        self.assertEqual(p.replace(os.sep, "/"), "/lib/电影/Some Movie (2019)/Some Movie (2019).mkv")

    def test_episode_path(self):
        p = organizer.target_path("/lib", "tv", "Some Show", 2020, 2, 7, ".mkv")
        self.assertEqual(
            p.replace(os.sep, "/"),
            "/lib/剧集/Some Show (2020)/Season 02/Some Show S02E07.mkv")

    def test_anime_uses_anime_dir(self):
        p = organizer.target_path("/lib", "anime", "Some Anime", 2021, 1, 3, ".mkv")
        self.assertIn("/动漫/", p.replace(os.sep, "/"))

    def test_movie_without_year(self):
        p = organizer.target_path("/lib", "movie", "No Year", None, None, None, ".mp4")
        self.assertEqual(p.replace(os.sep, "/"), "/lib/电影/No Year/No Year.mp4")

    def test_unknown_media_type_falls_into_other(self):
        p = organizer.target_path("/lib", "podcast", "X", 2000, None, None, ".mkv")
        self.assertIn("/其他/", p.replace(os.sep, "/"))

    def test_missing_episode_season_defaults_to_one(self):
        p = organizer.target_path("/lib", "tv", "S", None, None, 5, ".mkv")
        self.assertIn("Season 01", p.replace(os.sep, "/"))
        self.assertIn("S01E05", p.replace(os.sep, "/"))

    def test_traversal_title_stays_inside_root(self):
        root = os.path.realpath(tempfile.mkdtemp())
        try:
            p = organizer.target_path(root, "movie", "../../etc/passwd", 2019, None, None, ".mkv")
            self.assertTrue(p.startswith(root + os.sep), p)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestSafeJoin(unittest.TestCase):
    def test_normal_join(self):
        r = organizer.safe_join("/lib", "电影/x.mkv")
        self.assertTrue(r.startswith("/lib"))

    def test_traversal_blocked(self):
        with self.assertRaises(ValueError):
            organizer.safe_join("/lib", "../../etc/passwd")

    def test_absolute_rel_blocked(self):
        with self.assertRaises(ValueError):
            organizer.safe_join("/lib", "/etc/passwd")

    def test_symlink_escape_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            outside = os.path.join(d, "outside")
            root = os.path.join(d, "root")
            os.makedirs(outside)
            os.makedirs(root)
            _write(os.path.join(outside, "secret.mkv"), "x")
            try:
                os.symlink(outside, os.path.join(root, "link"))
            except (OSError, NotImplementedError):
                self.skipTest("该平台不支持符号链接")
            with self.assertRaises(ValueError):
                organizer.safe_join(root, "link/secret.mkv")

    def test_sanitize_strips_separators(self):
        self.assertEqual(organizer.sanitize('a/b\\c:d'), "a_b_c_d")
        self.assertEqual(organizer.sanitize("  "), "unnamed")


class TestJunkFilter(unittest.TestCase):
    def test_zero_byte_skipped(self):
        # --select-file 会为未选中的文件留下 0 字节占位
        self.assertTrue(organizer.is_junk("Show/S01E01.mkv", 0))
        self.assertFalse(organizer.is_junk("Show/S01E01.mkv", 100))

    def test_aria2_control_skipped(self):
        self.assertTrue(organizer.is_junk("Show.mkv.aria2", 10))
        self.assertTrue(organizer.is_junk(".aria2", 10))
        self.assertFalse(organizer.is_junk("Show.mkv", 10))


class TestSameFs(unittest.TestCase):
    def test_same_dir_true(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.mkv")
            _write(a, "x")
            self.assertTrue(organizer.same_fs(a, d))

    def test_cross_device_false(self):
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        with tempfile.TemporaryDirectory(dir=cand) as other:
            with tempfile.TemporaryDirectory() as d:
                a = os.path.join(d, "a.mkv")
                _write(a, "x")
                self.assertFalse(organizer.same_fs(a, other))

    def test_missing_path_false(self):
        self.assertFalse(organizer.same_fs("/no/such/file", "/no/such/dir"))


class TestLinkProbe(unittest.TestCase):
    """能力探针：不靠报错驱动流程，先问文件系统能不能硬链接。"""

    def test_probe_same_dir_true(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(organizer.link_probe(d, d))

    def test_probe_cross_device_false(self):
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        other = tempfile.mkdtemp(dir=cand)
        self.addCleanup(shutil.rmtree, other, True)
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(organizer.link_probe(d, other))

    def test_probe_leaves_no_residue(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src")
            dst = os.path.join(d, "dst")
            os.makedirs(src)
            os.makedirs(dst)
            organizer.link_probe(src, dst)
            self.assertEqual(os.listdir(src), [])
            self.assertEqual(os.listdir(dst), [])

    def test_probe_missing_dir_false(self):
        self.assertFalse(organizer.link_probe("/no/such/dir", "/no/such/dir2"))


class TestExecute(unittest.TestCase):
    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            plan = [{"src": src, "dest": os.path.join(d, "out", "a.mkv"), "action": "move"}]
            organizer.execute(plan, dry_run=True)
            self.assertFalse(os.path.exists(os.path.join(d, "out", "a.mkv")))

    def test_dry_run_creates_no_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(d, "out", "deep", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "move"}], dry_run=True)
            self.assertFalse(os.path.exists(os.path.join(d, "out")))
            self.assertTrue(os.path.exists(src))
            self.assertEqual(log[0]["result"], "dry-run")

    def test_execute_moves(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(d, "out", "a.mkv")
            organizer.execute([{"src": src, "dest": dest, "action": "move"}], dry_run=False)
            self.assertTrue(os.path.exists(dest))

    def test_execute_move_removes_source(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(d, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "move"}], dry_run=False)
            self.assertEqual(log[0]["result"], "moved")
            self.assertFalse(os.path.exists(src))

    def test_existing_dest_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "new")
            dest = os.path.join(d, "out", "a.mkv")
            os.makedirs(os.path.dirname(dest))
            _write(dest, "old")
            log = organizer.execute([{"src": src, "dest": dest, "action": "move"}], dry_run=False)
            self.assertEqual(log[0]["result"], "skipped-exists")
            self.assertEqual(_read(dest), "old")
            self.assertTrue(os.path.exists(src))

    def test_hardlink_same_fs_links(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(d, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "hardlink"}], dry_run=False)
            self.assertEqual(log[0]["result"], "linked")
            self.assertEqual(os.stat(src).st_ino, os.stat(dest).st_ino)

    def test_hardlink_cross_device_reports_copy_explicitly(self):
        """跨挂载点时明确上报并回退复制，绝不静默处理。"""
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        other = tempfile.mkdtemp(dir=cand)
        self.addCleanup(shutil.rmtree, other, True)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(other, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "hardlink"}], dry_run=False)
            self.assertIn("EXDEV", log[0]["result"])
            self.assertIn("copied", log[0]["result"])
            self.assertTrue(os.path.exists(dest))
            self.assertTrue(os.path.exists(src))
            self.assertEqual(_read(dest), "x")

    def test_move_cross_device_falls_back(self):
        """跨设备 move 不能直接失败：rename -> link -> copy 三级回退。"""
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        other = tempfile.mkdtemp(dir=cand)
        self.addCleanup(shutil.rmtree, other, True)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            dest = os.path.join(other, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "move"}], dry_run=False)
            self.assertTrue(log[0]["result"].startswith("moved"), log[0]["result"])
            self.assertTrue(os.path.exists(dest))
            self.assertFalse(os.path.exists(src))

    def test_large_copy_refused_without_optin(self):
        """大文件复制必须显式放行：拒绝执行且保留源文件。"""
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        other = tempfile.mkdtemp(dir=cand)
        self.addCleanup(shutil.rmtree, other, True)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, b"x" * 4096)
            dest = os.path.join(other, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "hardlink"}],
                                    dry_run=False, cfg={"copy_warn_bytes": 1})
            self.assertTrue(log[0]["result"].startswith("refused"), log[0]["result"])
            self.assertFalse(os.path.exists(dest))
            self.assertTrue(os.path.exists(src))

    def test_large_copy_allowed_when_opted_in(self):
        cand = _other_fs_dir()
        if not cand:
            self.skipTest("没有跨挂载点目录可用于对照")
        other = tempfile.mkdtemp(dir=cand)
        self.addCleanup(shutil.rmtree, other, True)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, b"x" * 4096)
            dest = os.path.join(other, "out", "a.mkv")
            log = organizer.execute([{"src": src, "dest": dest, "action": "hardlink"}],
                                    dry_run=False,
                                    cfg={"copy_warn_bytes": 1, "allow_large_copy": True})
            self.assertIn("copied", log[0]["result"])
            self.assertTrue(os.path.exists(dest))

    def test_missing_source_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            log = organizer.execute([{"src": os.path.join(d, "nope.mkv"),
                                      "dest": os.path.join(d, "out", "x.mkv"),
                                      "action": "move"}], dry_run=False)
            self.assertTrue(log[0]["result"].startswith("error"), log[0]["result"])

    def test_unknown_action_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.mkv")
            _write(src, "x")
            log = organizer.execute([{"src": src, "dest": os.path.join(d, "out", "a.mkv"),
                                      "action": "teleport"}], dry_run=False)
            self.assertTrue(log[0]["result"].startswith("error"), log[0]["result"])
            self.assertTrue(os.path.exists(src))


class TestPlan(unittest.TestCase):
    def test_movie_plan_targets_movie_dir(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "dl")
            lib = os.path.join(d, "lib")
            os.makedirs(src_dir)
            os.makedirs(lib)
            _write(os.path.join(src_dir, "Some.Movie.2019.1080p.BluRay.x264-GROUP.mkv"), "v")
            plan = organizer.plan(src_dir, lib, "movie")
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["src"], os.path.join(src_dir, "Some.Movie.2019.1080p.BluRay.x264-GROUP.mkv"))
            self.assertEqual(plan[0]["dest"].replace(os.sep, "/"),
                             os.path.join(lib, "电影", "Some Movie (2019)", "Some Movie (2019).mkv").replace(os.sep, "/"))
            self.assertEqual(plan[0]["action"], "move")

    def test_plan_skips_zero_byte_and_aria2(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "dl")
            lib = os.path.join(d, "lib")
            os.makedirs(src_dir)
            os.makedirs(lib)
            _write(os.path.join(src_dir, "Some.Movie.2019.1080p.mkv"), "v")
            _write(os.path.join(src_dir, "Unselected.Movie.2020.1080p.mkv"))   # 0 字节占位
            _write(os.path.join(src_dir, "Some.Movie.2019.1080p.mkv.aria2"), "ctl")
            plan = organizer.plan(src_dir, lib, "movie")
            self.assertEqual([os.path.basename(i["src"]) for i in plan],
                             ["Some.Movie.2019.1080p.mkv"])

    def test_plan_tv_uses_season_dir(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "dl")
            lib = os.path.join(d, "lib")
            sub = os.path.join(src_dir, "Some.Show.S02")
            os.makedirs(sub)
            os.makedirs(lib)
            _write(os.path.join(sub, "Some.Show.2020.S02E07.1080p.WEB-DL.x265.mkv"), "v")
            plan = organizer.plan(src_dir, lib, "tv")
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["dest"].replace(os.sep, "/"),
                             os.path.join(lib, "剧集", "Some Show (2020)", "Season 02",
                                          "Some Show S02E07.mkv").replace(os.sep, "/"))

    def test_plan_keeps_everything_inside_library_root(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "dl")
            lib = os.path.join(d, "lib")
            os.makedirs(src_dir)
            os.makedirs(lib)
            _write(os.path.join(src_dir, "../../evil.2020.1080p.mkv"), "v")
            root = os.path.realpath(lib)
            for item in organizer.plan(src_dir, lib, "movie"):
                self.assertTrue(item["dest"].startswith(root + os.sep), item["dest"])

    def test_plan_dry_run_execute_keeps_downloads_intact(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "dl")
            lib = os.path.join(d, "lib")
            os.makedirs(src_dir)
            os.makedirs(lib)
            _write(os.path.join(src_dir, "Some.Movie.2019.1080p.mkv"), "v")
            plan = organizer.plan(src_dir, lib, "movie")
            organizer.execute(plan, dry_run=True)
            self.assertTrue(os.path.exists(plan[0]["src"]))
            self.assertFalse(os.path.exists(plan[0]["dest"]))
            organizer.execute(plan, dry_run=False)
            self.assertTrue(os.path.exists(plan[0]["dest"]))
            self.assertFalse(os.path.exists(plan[0]["src"]))


if __name__ == "__main__":
    unittest.main()
