import unittest
from lib import ranker
from lib.sources.base import Result


def _r(title, seeders=10, size=5 * 10**9):
    return Result(title=title, magnet="magnet:?xt=urn:btih:AB",
                  size=size, seeders=seeders, source="s")


class TestSequelDisambiguation(unittest.TestCase):
    """搜某片名时，同名的续集（片名后带序号）是不同作品，不能排在正片前面。

    触发场景：查「流浪地球」时，「流浪地球2」若正好中字标记多一个，
    就会靠标记加分反超正片——用户拿到的是续集而不是想看的正片。
    """

    def test_sequel_ranks_below_original(self):
        original = _r("[G][流浪地球/The.Wandering.Earth][1080P][简体内封]", seeders=17)
        sequel = _r("[G][流浪地球2/The Wandering Earth II][1080P][双语外挂简繁]", seeders=3)
        ranked = ranker.rank([sequel, original], "流浪地球", {})
        self.assertIn("Earth]", ranked[0].title.replace(" ", ""), ranked[0].title)

    def test_sequel_penalty_active(self):
        self.assertTrue(ranker.is_sequel("[G][流浪地球2][1080P]", "流浪地球"))

    def test_original_not_flagged_as_sequel(self):
        self.assertFalse(ranker.is_sequel("[G][流浪地球/The.Wandering.Earth][1080P]", "流浪地球"))

    def test_latin_sequel_detected(self):
        self.assertTrue(ranker.is_sequel("Some Movie II 2019 1080p", "Some Movie"))

    def test_latin_original_not_flagged(self):
        self.assertFalse(ranker.is_sequel("Some Movie 2019 1080p", "Some Movie"))

    def test_year_after_title_is_not_sequel(self):
        # '流浪地球 2019' 年份里的 2 不能被当成续集序号
        self.assertFalse(ranker.is_sequel("流浪地球 2019 电影 国语中字 高清", "流浪地球"))

    def test_year_with_bracket_is_not_sequel(self):
        self.assertFalse(ranker.is_sequel("[G] Some Movie 2019 1080p BluRay", "Some Movie"))

    def test_chinese_subtitle_still_beats_sequel_ordering(self):
        # 中字优先权重大于续集惩罚：中字续集仍应胜过无中字正片
        with_cn_sequel = _r("[G][流浪地球2][1080p][简繁中字]", seeders=5)
        no_cn_original = _r("[G][流浪地球][1080p][BluRay]", seeders=900)
        ranked = ranker.rank([no_cn_original, with_cn_sequel], "流浪地球", {})
        self.assertIn("中字", ranked[0].title)
