#!/usr/bin/env python3
"""media-butler CLI：影视片源检索、下载与本地库分类管理。

全部确定性执行在此完成；LLM 只负责片名理解与候选择优。

设计约束（改前必读）：
- **ingest 必须自行识别媒体类型**：``organizer.plan`` 信任调用方传入的
  ``media_type``，不会自行判断；若不识别，剧集会被塞进「电影/」目录。
- 所有写操作都有 ``--dry-run``，dry-run 绝不落盘（不建库、不写清单）。
- SOCKS 型代理 aria2c 不支持：必须显式告警，**绝不静默直连**。
- grab 一律异步：agent 的工具调用普遍会超时，不能阻塞等下载完成。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (config, doctor, downloader, indexer,  # noqa: E402
                 metadata, organizer, parser, ranker, sources, subtitles)
from lib.sources import search_all  # noqa: E402

COMMANDS = ("parse", "meta", "search", "grab", "status",
            "subs", "ingest", "index", "doctor", "config")

VERSION = "media-butler 0.1.0"

#: 源侧分类线索：命中即判为动漫（剧集/电影判定之外的特例）
ANIME_HINTS = ("动漫", "动画", "番剧", "anime")

#: 归档成功的 execute() 结果值（其余如 skipped-exists/error/refused 都不入索引）
_ARCHIVED_OK = ("moved", "moved-cross-device-link", "linked",
                "moved-cross-device-copied", "copy+copied",
                "hardlink-unavailable-EXDEV+copied")

#: 未安装 aria2c 时的建议（不报错退出，只给可执行替代路径）
_NO_DOWNLOADER_HINTS = [
    "安装后重试：apt install aria2 / brew install aria2",
    "或直接复制上面的磁力链接到任意 BT 客户端",
]


def _out(obj):
    """统一 JSON 输出：ensure_ascii=False，中文可读，set 自动降级为有序列表。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default))


def _json_default(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


def _err(status, message, **extra):
    data = {"status": status, "message": message}
    data.update(extra)
    _out(data)
    return 1


def _download_dir(args, cfg) -> str:
    return (getattr(args, "dest", None) or cfg.get("download_root")
            or str(config.state_dir() / "downloads"))


# --------------------------------------------------------------------------- #
# parse / meta / search
# --------------------------------------------------------------------------- #

def cmd_parse(args):
    info = parser.parse(args.name)
    out = dict(info)
    out["marks"] = sorted(info.get("marks") or ())
    _out(out)
    return 0


def cmd_meta(args):
    cfg = config.load()
    _out({"meta": metadata.lookup(args.name, cfg),
          "terms": metadata.best_search_terms(args.name, cfg)})
    return 0


def cmd_search(args):
    cfg = config.load()
    terms = metadata.best_search_terms(args.name, cfg) or [args.name]
    raw = []
    for t in terms[:2]:
        raw.extend(search_all(t, cfg))
    ranked = ranker.rank(ranker.dedupe(raw), terms[0], cfg)
    rows = []
    for r in ranked[:args.limit]:
        info = parser.parse(r.title)
        rows.append({
            "title": r.title,
            "size_gb": round((r.size or 0) / 10 ** 9, 2),
            "seeders": r.seeders,
            "source": r.source,
            "category": r.category,
            "has_cn_sub": parser.has_chinese_subtitle(r.title),
            "episode": info["episode"],
            "season": info["season"],
            "is_batch": info["is_batch"],
            "magnet": r.magnet,
        })
    _out({"query": args.name, "terms": terms, "count": len(rows),
          "results": rows})
    return 0


# --------------------------------------------------------------------------- #
# grab / status
# --------------------------------------------------------------------------- #

def _parse_select(spec):
    """``--select 1,3`` -> [1, 3]；非法输入抛 ValueError（绝不猜测）。"""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or int(part) < 1:
            raise ValueError("select 必须是逗号分隔的正整数索引: %r" % spec)
        out.append(int(part))
    return out or None


def cmd_grab(args):
    cfg = config.load()

    select = None
    if args.select:
        try:
            select = _parse_select(args.select)
        except ValueError as e:
            return _err("error:bad-select", str(e))

    dest = _download_dir(args, cfg)
    proxy, usable = downloader.resolve_proxy(cfg)
    warnings = []
    blocked = False
    if proxy and not usable:
        # aria2c 不支持 SOCKS（实测报 unrecognized proxy format 后退出）。
        # 这里绝不静默改走直连：直连可能泄露真实 IP，必须由用户决定。
        warnings.append(
            "代理 %s 是 SOCKS 型，aria2c 不支持（会报 unrecognized proxy format）；"
            "已阻止静默直连" % proxy)
        blocked = not args.allow_direct

    run_cfg = dict(cfg)
    if proxy and not usable:
        run_cfg["proxy"] = ""      # 不能把 SOCKS 透传给 aria2c

    if args.dry_run:
        _out({"status": "dry-run", "dest": dest,
              "cmd": downloader.build_args(args.magnet, dest, select, run_cfg),
              "would_start": (downloader.aria2_available() and not blocked),
              "warnings": warnings})
        return 0

    if not downloader.aria2_available():
        _out({"status": "no-downloader",
              "message": "未检测到 aria2c；已输出磁力链接，可手动加入下载客户端",
              "magnet": args.magnet, "dest": dest,
              "suggestions": _NO_DOWNLOADER_HINTS,
              "warnings": warnings})
        return 0

    if blocked:
        _out({"status": "proxy-unsupported",
              "action_required": True,
              "message": "SOCKS 代理无法传入 aria2c，下载未启动",
              "magnet": args.magnet, "dest": dest, "proxy": proxy,
              "suggestions": [
                  "改用 aria2c 支持的 HTTP 代理（http://host:port）",
                  "或用 --allow-direct 显式确认走直连（可能暴露真实 IP）",
              ],
              "warnings": warnings})
        return 0

    info = downloader.start(args.magnet, dest, select_files=select, cfg=run_cfg)
    _out({"status": "started", "pid": info.get("pid"), "log": info.get("log"),
          "dest": info.get("dest"), "warnings": warnings,
          "hint": "已后台启动，稍后用 status 查看进度"})
    return 0


def cmd_status(args):
    cfg = config.load()
    d = Path(_download_dir(args, cfg))
    log = d / "aria2.log"
    tail = ""
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = "\n".join(lines[-args.lines:]) if args.lines > 0 else ""
    incomplete = []
    if d.is_dir():
        # *.aria2 是 aria2c 的「尚未下完」标记
        incomplete = sorted(str(p) for p in d.rglob("*.aria2"))
    _out({"download_dir": str(d), "aria2_available": downloader.aria2_available(),
          "incomplete": incomplete, "count": len(incomplete), "tail": tail})
    return 0


# --------------------------------------------------------------------------- #
# subs
# --------------------------------------------------------------------------- #

def cmd_subs(args):
    cfg = config.load()
    video = args.file or ""
    if video:
        local = subtitles.detect_local(video)
        if local:
            _out({"status": "found-local", "path": local, "video": video})
            return 0
        name = Path(video).stem
        dest = args.dest or str(Path(video).parent)
    else:
        name = args.name or ""
        dest = args.dest or str(config.state_dir())

    if not name:
        return _err("error", "需要片名或 --file")

    found = subtitles.search(name, cfg)
    if not found:
        _out({"status": "not-found",
              "message": "未找到匹配的中文字幕；可尝试更换片源版本或手动补充",
              "query": name})
        return 0

    best = found[0]
    if args.dry_run:
        _out({"status": "candidates", "query": name, "dest": dest,
              "count": len(found), "results": found[:10]})
        return 0

    path = subtitles.fetch(best["url"], dest, cfg)
    if not path:
        _out({"status": "download-failed", "candidate": best, "dest": dest})
        return 1
    _out({"status": "ok", "path": path, "candidate": best, "video": video})
    return 0


# --------------------------------------------------------------------------- #
# ingest
# --------------------------------------------------------------------------- #

def _detect_media_type(src_path: str, info: dict) -> str:
    """按本地线索判定媒体类型（绝不猜测归属）。

    动漫 > 剧集 > 电影：命中动漫目录线索即 anime；解析出集号即 tv；
    有季号或合集标记也按 tv 处理；其余为 movie。
    """
    hay = (os.path.dirname(src_path) + os.sep + os.path.basename(src_path)).lower()
    if any(h in hay for h in ANIME_HINTS):
        return "anime"
    if info.get("episode") is not None:
        return "tv"
    if info.get("season") is not None or info.get("is_batch"):
        return "tv"
    return "movie"


def _plan_items(src: str, lib: str, cfg: dict, explicit_type: str = ""):
    """扫出归档计划，并**逐条**判定媒体类型后重算目标路径。

    ``organizer.plan`` 只会把调用方给的 ``media_type`` 套到所有文件上，
    因此这里先借它完成扫描与垃圾过滤（含路径越界防护），再按每个文件
    自身的集号线索重算 ``dest``——下载目录里电影与剧集混放时也不会串目录。
    """
    items = organizer.plan(src, lib, "movie", cfg)
    out = []
    for it in items:
        info = parser.parse(os.path.basename(it["src"]))
        mtype = explicit_type or _detect_media_type(it["src"], info)
        ext = os.path.splitext(it["src"])[1] or ".mkv"
        try:
            dest = organizer.target_path(lib, mtype, info["title"], info.get("year"),
                                         info.get("season"), info.get("episode"), ext)
        except ValueError:
            continue      # 拼不出安全目标就放弃，不静默改路径
        it = dict(it)
        it["media_type"] = mtype
        it["dest"] = dest
        it["parsed"] = info
        out.append(it)
    return out


def _reported_types(items):
    types = sorted({i["media_type"] for i in items})
    if not types:
        return "", []
    return (types[0] if len(types) == 1 else "mixed"), types


def cmd_ingest(args):
    cfg = config.load()
    lib = args.library or cfg.get("library_root")
    if not lib:
        return _err("error", "未设置媒体库根目录，请用 --library 或 config 设置")
    if not os.path.isdir(args.src):
        return _err("error", "源目录不存在: %s" % args.src)
    explicit = args.type or ""

    items = _plan_items(args.src, lib, cfg, explicit)
    mtype, types = _reported_types(items)

    if args.dry_run:
        _out({"status": "dry-run", "count": len(items),
              "media_type": mtype, "types": types,
              "plan": [{"src": i["src"], "dest": i["dest"],
                        "media_type": i["media_type"], "size": i.get("size", 0),
                        "action": i.get("action")} for i in items]})
        return 0

    log = organizer.execute(items, dry_run=False, cfg=cfg)
    db = str(config.state_dir() / "library.db")
    conn = indexer.init_db(db)
    added = 0
    for entry, item in zip(log, items):
        if entry.get("result") not in _ARCHIVED_OK:
            continue      # 跳过/失败/拒复制都不入索引，避免索引指向不存在的文件
        info = item["parsed"]
        indexer.add(conn, {
            "title": info["title"], "year": info.get("year"),
            "media_type": item["media_type"],
            "season": info.get("season"), "episode": info.get("episode"),
            "path": entry["dest"], "size": item.get("size") or entry.get("size") or 0,
            "has_cn_sub": 1 if info.get("marks") else 0,
            "source": "local", "query": args.src,
        })
        added += 1

    json_path = indexer.export_json(conn, str(config.state_dir() / "library.json"))
    md_path = indexer.export_markdown(conn,
                                      str(config.state_dir() / "LIBRARY.md"))
    _out({"status": "ok", "media_type": mtype, "types": types,
          "planned": len(items), "moved": added,
          "skipped": len(items) - added,
          "index": {"db": db, "json": json_path, "markdown": md_path},
          "log": log})
    return 0


# --------------------------------------------------------------------------- #
# index
# --------------------------------------------------------------------------- #

def cmd_index(args):
    cfg = config.load()
    db = str(config.state_dir() / "library.db")
    lib = args.library or cfg.get("library_root") or ""

    if args.action == "rebuild":
        if not lib or not os.path.isdir(lib):
            return _err("error", "需要 --library 指向存在的媒体库目录")
        rows = indexer.rebuild_from_disk(lib)
        if args.dry_run:
            _out({"status": "dry-run", "would_add": len(rows),
                  "library": lib, "sample": rows[:5]})
            return 0
        conn = indexer.init_db(db)
        for r in rows:
            indexer.add(conn, r)
        _out({"status": "ok", "rebuilt": len(rows), "db": db,
              "json": indexer.export_json(conn, str(config.state_dir() / "library.json")),
              "markdown": indexer.export_markdown(
                  conn, str(config.state_dir() / "LIBRARY.md"))})
        return 0

    conn = indexer.init_db(db)
    if args.action == "list":
        _out(indexer.list_items(conn))
    elif args.action == "stats":
        _out(indexer.stats(conn))
    elif args.action == "export":
        _out({"json": indexer.export_json(conn, str(config.state_dir() / "library.json")),
              "markdown": indexer.export_markdown(
                  conn, str(config.state_dir() / "LIBRARY.md"))})
    elif args.action == "missing":
        _out(indexer.find_missing_episodes(conn, args.title, args.season,
                                           getattr(args, "expect", None)))
    return 0


# --------------------------------------------------------------------------- #
# doctor（只读）
# --------------------------------------------------------------------------- #

def cmd_doctor(args):
    cfg = config.load()
    if args.action == "sources":
        _out(doctor.check_sources(cfg))
    elif args.action == "library":
        lib = args.library or cfg.get("library_root") or ""
        conn = indexer.init_db(str(config.state_dir() / "library.db"))
        _out(doctor.check_library(conn, lib))
    elif args.action == "fs":
        src = args.src or cfg.get("download_root") or ""
        dest = args.dest or cfg.get("library_root") or ""
        _out({"src": src, "dest": dest, **doctor.fs_capabilities(src, dest)})
    elif args.action == "regrab":
        conn = indexer.init_db(str(config.state_dir() / "library.db"))
        _out({"candidates": doctor.regrab_candidates(conn, cfg),
              "note": "仅候选清单；实际获取请确认后手动执行 grab"})
    return 0


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

def _coerce(v: str):
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if v.lstrip("-").isdigit():
        return int(v)
    return v


def cmd_config(args):
    cfg = config.load()
    out = dict(cfg)
    if args.set:
        kv = {}
        for pair in args.set:
            k, _, v = pair.partition("=")
            if not k:
                return _err("error", "配置项格式应为 k=v: %r" % pair)
            kv[k] = _coerce(v)
        if args.dry_run:
            out.update(kv)
            out["dry_run"] = True
        else:
            cfg.update(kv)
            config.save(cfg)
            out = dict(cfg)
    out["state_dir"] = str(config.state_dir())
    _out(out)
    return 0


# --------------------------------------------------------------------------- #
# 参数解析与入口
# --------------------------------------------------------------------------- #

def _add_dry_run(p):
    p.add_argument("--dry-run", action="store_true", help="只预览，不落盘")


def build_parser():
    p = argparse.ArgumentParser(
        prog="media-butler",
        description="影视片源检索、下载与本地库分类管理")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("parse", help="解析资源名")
    s.add_argument("name")
    s.set_defaults(fn=cmd_parse)

    s = sub.add_parser("meta", help="查询元数据与检索名")
    s.add_argument("name")
    s.set_defaults(fn=cmd_meta)

    s = sub.add_parser("search", help="多源检索（中字优先）")
    s.add_argument("name")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("grab", help="加入下载（异步）")
    s.add_argument("magnet")
    s.add_argument("--dest")
    s.add_argument("--select", help="选集下载，逗号分隔文件索引")
    s.add_argument("--allow-direct", action="store_true",
                   help="代理不可用时显式确认走直连")
    _add_dry_run(s)
    s.set_defaults(fn=cmd_grab)

    s = sub.add_parser("status", help="查看下载进度")
    s.add_argument("--dest")
    s.add_argument("--lines", type=int, default=15)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("subs", help="获取中文字幕")
    s.add_argument("name", nargs="?", default="")
    s.add_argument("--file", help="按已有视频文件查找字幕")
    s.add_argument("--dest")
    _add_dry_run(s)
    s.set_defaults(fn=cmd_subs)

    s = sub.add_parser("ingest", help="归档入库")
    s.add_argument("src")
    s.add_argument("--library")
    s.add_argument("--type", default="",
                   choices=["", "movie", "tv", "anime", "other"],
                   help="显式指定类型；默认按文件名/目录线索自动识别")
    _add_dry_run(s)
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("index", help="媒体库清单")
    s.add_argument("action", choices=["list", "stats", "export", "missing", "rebuild"])
    s.add_argument("--library")
    s.add_argument("--title", default="")
    s.add_argument("--season", type=int)
    s.add_argument("--expect", type=int)
    _add_dry_run(s)
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("doctor", help="只读巡检")
    s.add_argument("action", choices=["sources", "library", "fs", "regrab"])
    s.add_argument("--library")
    s.add_argument("--src")
    s.add_argument("--dest")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("config", help="配置读写")
    s.add_argument("--set", action="append", help="k=v")
    _add_dry_run(s)
    s.set_defaults(fn=cmd_config)

    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.print_help()
        return 1
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
