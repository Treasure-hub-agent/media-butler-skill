import unittest
from lib.sources import base, knaben


class TestResult(unittest.TestCase):
    def test_result_from_knaben_hit(self):
        hit = {"title": "T", "magnetUrl": "magnet:?xt=urn:btih:AB", "bytes": 1000,
               "liveSeeders": 5, "tracker": "SomeSite", "category": "Movies / HD"}
        r = knaben.to_result(hit)
        self.assertEqual(r.title, "T")
        self.assertEqual(r.seeders, 5)
        self.assertEqual(r.source, "SomeSite")
        self.assertTrue(r.magnet.startswith("magnet:"))

    def test_seeders_prefers_live(self):
        hit = {"title": "T", "magnetUrl": "magnet:?xt=urn:btih:AB", "bytes": 1,
               "liveSeeders": 9, "seeders": 2, "tracker": "X", "category": "c"}
        self.assertEqual(knaben.to_result(hit).seeders, 9)

    def test_skips_hit_without_magnet(self):
        self.assertIsNone(knaben.to_result({"title": "T"}))

    def test_source_metadata(self):
        s = knaben.KnabenSource()
        self.assertEqual(s.id, "knaben")
        self.assertIn("movies", s.supports)
        self.assertEqual(s.query_script, "both")


class TestRegistry(unittest.TestCase):
    def test_registry_contains_knaben(self):
        from lib.sources import registry
        ids = [s.id for s in registry()]
        self.assertIn("knaben", ids)

    def test_disabled_source_excluded(self):
        from lib.sources import registry
        ids = [s.id for s in registry({"sources_enabled": []})]
        self.assertNotIn("knaben", ids)


if __name__ == "__main__":
    unittest.main()
