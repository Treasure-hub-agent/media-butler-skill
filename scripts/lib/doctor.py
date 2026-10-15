"""只读巡检：源可达性、库完整性、文件系统能力、换源候选。

设计约束（必须保持）：
- **只读**：本模块不写任何文件、不执行任何获取动作、不改动索引库。
  探测公开 API 是否在线不涉及获取行为；文件系统能力探针会在目标目录
  建一个临时文件试 link() 后立即清理，除此之外不留任何痕迹。
- **不代建目录**：目标目录不存在时直接报不可用，绝不替用户创建。
- **换源只上报**：`regrab_candidates` 只产出候选清单，落地需用户显式
  确认后另行走 `grab`（合规要求：换源需用户显式确认）。
"""
import os
import re
import tempfile
from pathlib import Path

from . import metadata, organizer, ranker, sources

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
              ".rmvb", ".webm", ".m4v", ".mpg", ".mpeg", ".iso")
SUB_EXTS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
# 字幕语言后缀：Movie.zh.srt / Movie.chs.srt / Movie.cht&eng.srt
_LANG_SUFFIX = re.compile(
    r"\.(zh|chs|cht|chi|sc|tc|gb|big5|eng|en|jpn|jp|jap|kor|kr|"
    r"zh-cn|zh-tw|zh-hans|zh-hant|zh-hk)(\.\d+)?$", re.I)


def check_sources(cfg=None) -> list:
    """只读探测各源可达性。探测公开 API 是否在线不涉及任何获取行为。"""
    cfg = cfg or {}
    out = []
    for s in sources.registry(cfg):
        try:
            reachable = bool(s.health(cfg.get("proxy", "")))
        except Exception:
            reachable = False   # 单源挂掉不能让整份巡检失败
        out.append({"id": s.id, "reachable": reachable,
                    "query_script": getattr(s, "query_script", "latin")})
    return out


def _sub_stem(name: str) -> str:
    stem = name
    for ext in SUB_EXTS:
        if stem.lower().endswith(ext):
            stem = stem[:-len(ext)]
            break
    prev = None
    while prev != stem:
        prev = stem
        stem = _LANG_SUFFIX.sub("", stem)
    return stem


def check_library(conn, library_root: str) -> dict:
    """核对索引与磁盘的一致性：缺文件、0 字节残留、无配对视频的字幕。"""
    from . import indexer

    missing, zero = [], []
    for it in indexer.list_items(conn):
        p = it.get("path") or ""
        if not p:
            continue
        if not os.path.exists(p):
            missing.append(p)
            continue
        try:
            if os.path.getsize(p) == 0:
                zero.append(p)
        except OSError:
            missing.append(p)   # 读不到大小等同于不可用

    video_stems, subs = set(), []
    root = Path(library_root) if library_root else None
    if root is not None and root.is_dir():
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            low = p.name.lower()
            if low.endswith(VIDEO_EXTS):
                video_stems.add(str(p.parent / p.stem))
            elif low.endswith(SUB_EXTS):
                subs.append(p)

    orphans = [str(p) for p in sorted(subs)
               if str(p.parent / _sub_stem(p.name)) not in video_stems]
    return {"missing_files": missing, "zero_byte": zero,
            "subtitle_files": len(subs), "orphan_subs": orphans}


def _fs_type(path: str) -> str:
    """按挂载点最长前缀匹配取文件系统类型；只读 /proc/mounts。"""
    best, fs = "", "unknown"
    try:
        real = os.path.realpath(path) if path else ""
        for line in Path("/proc/mounts").read_text(
                encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 3 or not real:
                continue
            mount = parts[1].replace("\\040", " ")
            if real == mount or real.startswith(mount.rstrip("/") + "/"):
                if len(mount) > len(best):
                    best, fs = mount, parts[2]
    except OSError:
        pass
    return fs


def fs_capabilities(src_dir: str, dest_dir: str) -> dict:
    """能力探针：实际在目标目录建临时文件试 link()，比查表可靠。

    直接反映 CIFS/子卷/绑定挂载等真实情况。探完即清理，不留痕迹；
    目标目录不存在时不代建，直接报不可用（巡检必须只读）。
    """
    cap = {"same_fs": False, "hardlink": False, "fs_type": "unknown"}
    try:
        if os.path.isdir(src_dir) and os.path.isdir(dest_dir):
            cap["same_fs"] = bool(organizer.same_fs(src_dir, dest_dir))
    except OSError:
        pass

    probe_src = probe_dst = None
    try:
        if os.path.isdir(src_dir) and os.path.isdir(dest_dir):
            # 在源目录建探针、链到目标目录：这才是归档时真正要走的那一步
            fd, probe_src = tempfile.mkstemp(prefix=".mb-doctor-", dir=src_dir)
            os.close(fd)
            probe_dst = os.path.join(dest_dir, os.path.basename(probe_src) + ".lnk")
            os.link(probe_src, probe_dst)
            cap["hardlink"] = True
    except OSError:
        cap["hardlink"] = False
    finally:
        for p in (probe_dst, probe_src):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
    if not cap["hardlink"] and cap["same_fs"]:
        cap["hardlink_note"] = "同盘但 link() 失败，归档将回退复制"
    cap["fs_type"] = _fs_type(dest_dir)
    return cap


def regrab_candidates(conn, cfg=None) -> list:
    """只产出候选清单，不执行任何获取。落地需用户显式确认。"""
    from . import indexer, metadata, ranker, sources

    cfg = cfg or {}
    out = []
    for it in indexer.list_items(conn):
        if it.get("episode") is None and it.get("media_type") != "movie":
            continue    # 没有集号又非电影的行无法定位，不产候选
        title = it.get("title") or ""
        terms = metadata.best_search_terms(title, cfg)
        found = []
        for t in terms[:1]:
            found = ranker.rank(sources.search_all(t, cfg), t, cfg)
        if found:
            continue
        if it.get("has_cn_sub"):
            reason = "当前条件无可选候选"
        else:
            reason = "未找到中字版本"
        out.append({"title": title, "year": it.get("year"),
                    "media_type": it.get("media_type"),
                    "season": it.get("season"), "episode": it.get("episode"),
                    "reason": reason})
    return out
