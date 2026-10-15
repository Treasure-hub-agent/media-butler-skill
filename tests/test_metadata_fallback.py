import unittest
from unittest import mock
from lib import metadata


class TestMultiStrategyLookup(unittest.TestCase):
    """AniList 对中文名的命中率不稳定（同一批中文名有的能查有的查不到），
    必须多策略回退，不能一次查询失败就放弃。"""

    def test_falls_back_to_alternate_strategy_on_404(self):
        calls = []

        def fake_fetch(query, timeout=20, proxy=""):
            calls.append(query)
            # 第一种策略（单数 search）返回 None，后续策略返回真值
            if len(calls) == 1:
                return None
            return {"title": "Some Show", "english": "Some Show", "native": "",
                    "year": 2020, "episodes": 12}

        with mock.patch.object(metadata, "_fetch_media", side_effect=fake_fetch):
            r = metadata.lookup("某中文名")
        self.assertEqual(r.get("english"), "Some Show")
        self.assertGreater(len(calls), 1, "应尝试多种策略")

    def test_returns_empty_when_all_strategies_fail(self):
        with mock.patch.object(metadata, "_fetch_media", return_value=None):
            self.assertEqual(metadata.lookup("根本不存在的片名"), {})

    def test_search_names_drops_punctuation_variants(self):
        names = metadata.search_names("某某番 第二季")
        self.assertTrue(any("某某番" in n for n in names))

    def test_search_names_dedupes(self):
        names = metadata.search_names("Some Name")
        self.assertEqual(len(names), len(set(names)))
