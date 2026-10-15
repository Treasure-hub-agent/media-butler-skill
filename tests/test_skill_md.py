# tests/test_skill_md.py
import os, re, unittest


def _parse_frontmatter(text):
    """极简 frontmatter 解析：只取顶层 `key: value`，不引入第三方 YAML 依赖。"""
    if not text.startswith("---"):
        return {}
    body = text.split("---", 2)[1]
    out = {}
    for line in body.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestSkillMd(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(ROOT, "SKILL.md")
        with open(self.p, encoding="utf-8") as fh:
            self.raw = fh.read()

    def test_starts_with_frontmatter(self):
        self.assertTrue(self.raw.startswith("---"))

    def test_name_matches_dir(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = _parse_frontmatter(self.raw)
        self.assertEqual(fm["name"], "media-butler-skill")
        self.assertEqual(fm["name"], os.path.basename(os.path.realpath(ROOT)))

    def test_description_length(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = _parse_frontmatter(self.raw)
        self.assertLessEqual(len(fm["description"]), 1024)

    def test_description_is_pushy(self):
        m = re.search(r"\n---\s*\n", self.raw[3:])
        fm = _parse_frontmatter(self.raw)
        d = fm["description"]
        self.assertTrue(any(k in d for k in ("找片", "下载", "字幕", "媒体库")))

    def test_no_dev_residue(self):
        # 交付物不留开发痕迹：无日期、无实测叙述、无具体作品名
        self.assertIsNone(re.search(r"20\d{2}[-/年]\d{1,2}", self.raw))
        self.assertNotIn("实测", self.raw)

    def test_no_hardcoded_local_path(self):
        # 交付物不得含开发机绝对路径，否则别人 clone 到别处就失效
        import glob
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for pattern in ("*.md", "scripts/**/*.py", "tests/**/*.py",
                        "tests/**/*.md", "references/**/*.md"):
            for path in glob.glob(os.path.join(root, pattern), recursive=True):
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        # 前缀拆开拼接，避免本测试自己成为命中项
                        if ("/ho" + "me/") in line or ("/Us" + "ers/") in line:
                            offenders.append("%s:%d" % (os.path.relpath(path, root), lineno))
        self.assertEqual(offenders, [], "交付物含本地绝对路径: %s" % offenders)

    def test_size_within_limit(self):
        self.assertLessEqual(len(self.raw), 100_000)

    def test_references_exist(self):
        for f in ("naming.md", "sources.md", "subtitles.md", "troubleshooting.md"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "references", f)), f)
