import os, tempfile, unittest
from lib import organizer


class TestIncompleteDownloadExcluded(unittest.TestCase):
    """下载中的文件不能被归档。

    aria2c 用同名 .aria2 控制文件标记「尚未下完」。这类文件若被搬进媒体库，
    用户会拿到一个残缺、无法播放的视频，而且极易误判为「文件坏了」。
    """

    def test_file_with_sibling_aria2_is_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            video = os.path.join(d, "Some.Movie.2019.1080p.mkv")
            with open(video, "w") as f:
                f.write("x" * 1000)
            open(video + ".aria2", "w").close()      # aria2 未完成标记
            items = organizer.plan(d, os.path.join(d, "lib"), "movie")
            self.assertEqual(items, [], "未完成的下载不应进入归档计划")

    def test_completed_file_is_included(self):
        with tempfile.TemporaryDirectory() as d:
            video = os.path.join(d, "Some.Movie.2019.1080p.mkv")
            with open(video, "w") as f:
                f.write("x" * 1000)
            items = organizer.plan(d, os.path.join(d, "lib"), "movie")
            self.assertEqual(len(items), 1, "已完成的文件应正常归档")

    def test_batch_torrent_control_excluded(self):
        # 多文件种子的控制文件与目录同名：Show.aria2，其下文件也未完成
        with tempfile.TemporaryDirectory() as d:
            show = os.path.join(d, "Some Show")
            os.makedirs(show)
            video = os.path.join(show, "S01E01.mkv")
            with open(video, "w") as f:
                f.write("x" * 1000)
            open(os.path.join(d, "Some Show.aria2"), "w").close()
            items = organizer.plan(d, os.path.join(d, "lib"), "tv")
            self.assertEqual(items, [], "同一批次未完成时不应归档其中任何文件")
