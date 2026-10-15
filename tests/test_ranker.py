import unittest
from lib import ranker
from lib.sources.base import Result

class TestTokenGate(unittest.TestCase):
    def test_relevant_passes(self):
        self.assertTrue(ranker.passes_token_gate(
            "The Wandering Earth 2019 1080p", "The Wandering Earth"))

    def test_irrelevant_blocked(self):
        # 中文查询被源当成无分词查询，返回无关的最新上传流
        self.assertFalse(ranker.passes_token_gate(
            "Avira System Speedup Pro 5.3.0 + Crack", "流浪地球"))

    def test_cjk_substring_passes(self):
        self.assertTrue(ranker.passes_token_gate(
            "[某组] 流浪地球 1080p 中字", "流浪地球"))

    def test_partial_english_token_passes(self):
        self.assertTrue(ranker.passes_token_gate(
            "Movie Name 2019 REMASTERED", "Movie Name"))

    def test_empty_query_not_gated(self):
        self.assertTrue(ranker.passes_token_gate("anything", ""))

class TestScoring(unittest.TestCase):
    def _r(self, title, seeders=10, size=10**9, source="s"):
        return Result(title=title, magnet="magnet:?xt=urn:btih:AB",
                      size=size, seeders=seeders, source=source)

    def test_chinese_subtitle_ranks_first(self):
        plain = self._r("Some Movie 2019 1080p BluRay", seeders=900)
        with_cn = self._r("Some Movie 2019 1080p 中字 简繁内封", seeders=50)
        ranked = ranker.rank([plain, with_cn], "Some Movie", {"subtitle_priority": True})
        self.assertIn("中字", ranked[0].title)

    def test_chinese_pref_can_be_disabled(self):
        plain = self._r("Some Movie 2019 1080p BluRay", seeders=900)
        with_cn = self._r("Some Movie 2019 1080p 中字", seeders=50)
        ranked = ranker.rank([plain, with_cn], "Some Movie", {"subtitle_priority": False})
        self.assertEqual(ranked[0].seeders, 900)

    def test_irrelevant_filtered_from_rank(self):
        good = self._r("Some Movie 2019 1080p", seeders=10)
        junk = self._r("Totally Unrelated Thing", seeders=9999)
        ranked = ranker.rank([good, junk], "Some Movie", {})
        self.assertEqual(len(ranked), 1)

    def test_size_cap_filters(self):
        small = self._r("Some Movie 2019", size=10**9)
        huge = self._r("Some Movie 2019", size=50 * 10**9)
        ranked = ranker.rank([small, huge], "Some Movie", {"max_size_gb": 10})
        self.assertEqual(len(ranked), 1)
