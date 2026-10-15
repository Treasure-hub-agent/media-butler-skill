"""媒体库索引（SQLite）与 agent 可读清单导出。

设计要点：
- SQLite 是二进制，agent 读不了 → 双轨：SQLite 当内部索引，另有
  ``export_json`` / ``export_markdown`` 产出 library.json / LIBRARY.md 文本清单。
- 只存本地事实与**查询条件**（片名/年份/季集/路径/体积/中字标记），
  **绝不建 magnet / info_hash 列**，避免变成磁力索引库。
- 索引可从磁盘重建：``rebuild_from_disk`` 只依赖文件名与目录结构。
- 启用 WAL 模式，多进程并发读写更安全。
"""
import json, os, sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    media_type TEXT,
    season INTEGER,
    episode INTEGER,
    path TEXT UNIQUE,
    size INTEGER,
    has_cn_sub INTEGER DEFAULT 0,
    source TEXT,
    query TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

FIELDS = ["title", "year", "media_type", "season", "episode",
          "path", "size", "has_cn_sub", "source", "query"]

# 不入索引的伴生文件：字幕、封面、刮削信息、下载控制文件
SKIP_SUFFIXES = (".srt", ".ass", ".ssa", ".sub", ".vtt", ".aria2",
                 ".jpg", ".jpeg", ".png", ".nfo", ".torrent")
# 索引自身/其它数据库文件：索引库可能就落在媒体库目录内，
# 重建时绝不能把自己的库文件与 WAL 影子文件当成片子。
SKIP_DB_SUFFIXES = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite-wal",
                    ".sqlite-shm", ".sqlite3")
SKIP_SUFFIXES += SKIP_DB_SUFFIXES


def init_db(path: str) -> sqlite3.Connection:
    """建库/开库；目录不存在则创建。返回的 Connection 已启用 WAL。"""
    d = os.path.dirname(os.path.abspath(path))
    Path(d).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    conn.commit()                       # WAL 切换必须在事务之外
    conn.execute("PRAGMA journal_mode=WAL").fetchall()
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


def columns(conn) -> list:
    """items 表列名。用于自证没有持久化磁力类字段。"""
    return [r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()]


def schema_version(conn) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else SCHEMA_VERSION


def add(conn, record: dict) -> int:
    """写入/更新一条记录，以 path 为唯一键（重复入库不会产生重复行）。"""
    vals = [record.get(c) for c in FIELDS]
    cur = conn.execute(
        "INSERT OR REPLACE INTO items(%s) VALUES(%s)" % (
            ",".join(FIELDS), ",".join("?" * len(FIELDS))), vals)
    conn.commit()
    return cur.lastrowid


def list_items(conn) -> list:
    """按片名/季/集排序的全部记录。"""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM items ORDER BY title, season, episode")]


def find_missing_episodes(conn, title: str, season=None, expect=None) -> list:
    """缺集检测。给 expect 时按 1..expect 判定，否则按已入库最大集号推断。

    只做本地事实比对，不发起任何网络查询（换源另走 doctor 的候选上报）。
    """
    q = "SELECT episode FROM items WHERE title=? AND episode IS NOT NULL"
    params = [title]
    if season is not None:
        q += " AND season=?"
        params.append(season)
    have = {r[0] for r in conn.execute(q, params)}
    if expect:
        return [e for e in range(1, expect + 1) if e not in have]
    if not have:
        return []
    return [e for e in range(1, max(have) + 1) if e not in have]


def stats(conn) -> dict:
    items = list_items(conn)
    return {
        "count": len(items),
        "total_gb": round(sum(i.get("size") or 0 for i in items) / 10 ** 9, 2),
        "with_cn_sub": sum(1 for i in items if i.get("has_cn_sub")),
    }


def _write(path: str, text: str) -> str:
    Path(os.path.dirname(os.path.abspath(path))).mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    return path


def export_json(conn, path: str) -> str:
    """导出 agent 可读的 JSON 清单。"""
    data = list_items(conn)
    return _write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def export_markdown(conn, path: str) -> str:
    """导出 agent 可读的 Markdown 清单（按片名分组）。"""
    items = list_items(conn)
    by_title = {}
    for it in items:
        by_title.setdefault(it["title"], []).append(it)
    lines = ["# 媒体库清单", "",
             "共 %d 条记录，合计 %.2f GB" % (
                 len(items), sum(i.get("size") or 0 for i in items) / 10 ** 9),
             ""]
    for title, group in sorted(by_title.items()):
        lines.append("## %s" % title)
        for it in group:
            tag = "中字" if it.get("has_cn_sub") else "无中字标记"
            gb = (it.get("size") or 0) / 10 ** 9
            if it.get("episode"):
                lines.append("- S%02dE%02d · %.2f GB · %s" % (
                    it.get("season") or 1, it["episode"], gb, tag))
            else:
                lines.append("- %s · %.2f GB · %s" % (
                    it.get("year") or "", gb, tag))
        lines.append("")
    return _write(path, "\n".join(lines))


def rebuild_from_disk(library_root: str) -> list:
    """索引可从磁盘重建：只依赖文件名与目录结构这些本地事实。

    不读网络、不读旧索引，因此索引损坏或被删都可无损恢复。
    """
    from . import parser
    root = Path(library_root)
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        info = parser.parse(p.name)
        parts = set(p.parts)
        if "动漫" in parts:
            mtype = "anime"
        elif "剧集" in parts or info["episode"] is not None:
            mtype = "tv"
        else:
            mtype = "movie"
        out.append({
            "title": info["title"] or p.parent.name,
            "year": info["year"], "media_type": mtype,
            "season": info["season"], "episode": info["episode"],
            "path": str(p), "size": size,
            "has_cn_sub": 1 if info["marks"] else 0,
        })
    return out
