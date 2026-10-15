"""bencode 解析器测试（纯标准库）。"""
import unittest

from lib import bencode


class TestDecode(unittest.TestCase):
    def test_int(self):
        self.assertEqual(bencode.decode(b"i42e"), 42)

    def test_string(self):
        self.assertEqual(bencode.decode(b"4:spam"), b"spam")

    def test_list(self):
        self.assertEqual(bencode.decode(b"l4:spami1ee"), [b"spam", 1])

    def test_dict(self):
        self.assertEqual(bencode.decode(b"d3:foo3:bare"), {b"foo": b"bar"})

    def test_nested(self):
        raw = b"d4:infod4:name4:teste5:otheri7ee"
        d = bencode.decode(raw)
        self.assertEqual(d[b"info"][b"name"], b"test")
        self.assertEqual(d[b"other"], 7)

    def test_list_files_single(self):
        info = {b"name": b"movie.mkv", b"length": 100}
        files = bencode.list_files(info)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "movie.mkv")
        self.assertEqual(files[0]["length"], 100)

    def test_list_files_multi(self):
        info = {b"name": b"Show", b"files": [
            {b"path": [b"S01", b"E01.mkv"], b"length": 10},
            {b"path": [b"S01", b"E02.mkv"], b"length": 20},
        ]}
        files = bencode.list_files(info)
        self.assertEqual(files[1]["path"], "S01/E02.mkv")
        self.assertEqual(files[1]["index"], 2)   # aria2 --select-file 用 1 基索引


if __name__ == "__main__":
    unittest.main()
