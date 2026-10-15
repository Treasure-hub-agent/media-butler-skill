import os, unittest
from lib import config

class TestStateDir(unittest.TestCase):
    def test_state_dir_under_home(self):
        os.environ["MEDIA_BUTLER_HOME"] = "/tmp/mb-test"
        d = config.state_dir()
        self.assertEqual(str(d), "/tmp/mb-test")

    def test_load_returns_defaults_when_missing(self):
        os.environ["MEDIA_BUTLER_HOME"] = "/tmp/mb-test-missing"
        cfg = config.load()
        self.assertIn("library_root", cfg)
        self.assertIn("subtitle_priority", cfg)

    def test_save_then_load_roundtrip(self):
        os.environ["MEDIA_BUTLER_HOME"] = "/tmp/mb-test-rt"
        cfg = config.load()
        cfg["library_root"] = "/data/media"
        config.save(cfg)
        self.assertEqual(config.load()["library_root"], "/data/media")
