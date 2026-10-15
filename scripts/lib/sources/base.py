# scripts/lib/sources/base.py
from dataclasses import dataclass, field

@dataclass
class Result:
    title: str
    magnet: str
    size: int = 0
    seeders: int = 0
    source: str = ""
    category: str = ""
    is_batch: bool = False
    marks: set = field(default_factory=set)

class Source:
    id = "base"
    supports = ["movies"]
    query_script = "latin"     # latin | cjk | both —— 决定该源能否处理中文查询
    needs_key = False
    needs_proxy = False
    priority = 50

    def search(self, query, timeout=25, proxy=""):
        raise NotImplementedError

    def health(self, proxy="") -> bool:
        """只读探测：源是否可达。"""
        try:
            self.search("test", timeout=8, proxy=proxy)
            return True
        except Exception:
            return False
