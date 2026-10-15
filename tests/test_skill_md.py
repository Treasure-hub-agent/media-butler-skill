# tests/test_skill_md.py
import os, re, unittest
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestSkillMd(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(ROOT, "SKILL.md")
        self.raw = open(self.p, encoding="utf-8").read()

    def test_starts_with_frontmatter(self):
        self.assertTrue(self.raw.startswith("---"))

    def test_name_matches_dir(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = yaml.safe_load(self.raw[3:m.start() + 3])
        self.assertEqual(fm["name"], "media-butler-skill")
        self.assertEqual(fm["name"], os.path.basename(os.path.realpath(ROOT)))

    def test_description_length(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = yaml.safe_load(self.raw[3:m.start() + 3])
        self.assertLessEqual(len(fm["description"]), 1024)

    def test_description_is_pushy(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = yaml.safe_load(self.raw[3:m.start() + 3])
        d = fm["description"]
        self.assertTrue(any(k in d for k in ("找片", "下载", "字幕", "媒体库")))

    def test_no_dev_residue(self):
        # 交付物不留开发痕迹：无日期、无实测叙述、无具体作品名
        self.assertIsNone(re.search(r"20\d{2}[-/年]\d{1,2}", self.raw))
        self.assertNotIn("实测", self.raw)

    def test_size_within_limit(self):
        self.assertLessEqual(len(self.raw), 100_000)

    def test_references_exist(self):
        for f in ("naming.md", "sources.md", "subtitles.md", "troubleshooting.md"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "references", f)), f)
