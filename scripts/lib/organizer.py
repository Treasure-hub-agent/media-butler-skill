"""归档入库：目录规范、路径越界防护、垃圾过滤与硬链接回退。

三条硬性约束：

1. torrent 文件名是**攻击者可控输入**，任何拼进媒体库的路径都必须
   经 ``safe_join`` 做 realpath/commonpath 越界断言，越界抛 ``ValueError``。
2. 硬链接要求**同文件系统且同挂载点**（跨设备会报
   ``Invalid cross-device link``），因此先做能力探针 ``link_probe``，
   执行时按 ``rename -> link -> copy`` 三级回退。
3. **绝不静默复制大文件**：回退到复制时，超过 ``copy_warn_bytes``
   必须显式放行（``allow_large_copy``），否则拒绝并如实上报。

默认不覆盖、不删除；``execute`` 默认 ``dry_run=True``。
"""
import errno
import os
import shutil

from . import parser

# 轻量分类目录：用户手动播放时按类型一眼可辨
TYPE_DIRS = {"movie": "电影", "tv": "剧集", "anime": "动漫", "other": "其他"}

# 归属不清的资源统一落这里，绝不猜测
DEFAULT_TYPE = "other"

MEDIA_EXTS = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm",
              ".wmv", ".flv", ".rmvb", ".mpg", ".mpeg")

# 外挂字幕/图片等附属文件：只有跟某一集绑定时才随片归档
SIDECAR_EXTS = (".srt", ".ass", ".ssa", ".sub", ".idx", ".nfo",
                ".jpg", ".jpeg", ".png")

# 复制回退的体积阈值：默认 2GiB，超过即视为「大文件」
DEFAULT_COPY_WARN_BYTES = 2 * 1024 ** 3

_ILLEGAL = '<>:"/\\|?*'


def safe_join(root: str, rel: str) -> str:
    """拼接路径并断言未越出 ``root``；越界抛 ``ValueError``。

    做两层校验，缺一层都能被绕过：

    1. **文本层**：``normpath`` 之后必须仍在 root 内，挡住 ``../`` 与绝对路径；
    2. **真实层**：对 root 与目标各取一次 realpath，挡住库内指向外部的符号链接
       （``link/secret.mkv`` 这种文本上看着没问题）。

    返回的是 ``abspath`` 形式而非 realpath：若 ``/lib`` 本身是指向 ``/usr/lib``
    的符号链接，realpath 会把用户给的库根改名，落盘路径就不是用户指定的那个了。
    """
    root_abs = os.path.abspath(root)
    rel = str(rel if rel is not None else "")
    if os.path.isabs(rel):
        raise ValueError("path escapes library root: %s" % rel)
    joined = os.path.normpath(os.path.join(root_abs, rel))
    if joined != root_abs and not joined.startswith(root_abs + os.sep):
        raise ValueError("path escapes library root: %s" % rel)
    real_root = os.path.realpath(root_abs)
    real_joined = os.path.realpath(joined)
    if real_joined != real_root and not real_joined.startswith(real_root + os.sep):
        raise ValueError("path escapes library root: %s" % rel)
    return joined


def sanitize(name: str) -> str:
    """清洗单个路径片段：去掉分隔符/非法字符/控制字符，禁止 . 与 .."""
    out = str(name if name is not None else "")
    for ch in _ILLEGAL:
        out = out.replace(ch, "_")
    out = "".join("_" if ord(c) < 32 else c for c in out)
    out = out.strip(" .")
    if out in ("", ".", ".."):
        return "unnamed"
    return out


def target_path(library_root, media_type, title, year, season, episode, ext) -> str:
    """按媒体库规范给出目标绝对路径。

    电影：电影/片名 (年份)/片名 (年份).mkv
    剧集：剧集/片名 (年份)/Season NN/片名 SNNENN.mkv
    """
    subdir = TYPE_DIRS.get(media_type, TYPE_DIRS[DEFAULT_TYPE])
    title = sanitize(title)
    ext = str(ext or "").lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    if not ext:
        ext = ".mkv"
    yr = " (%s)" % year if year else ""
    if episode is not None:
        se = season if season is not None else 1
        rel = os.path.join(subdir, "%s%s" % (title, yr),
                           "Season %02d" % se,
                           "%s S%02dE%02d%s" % (title, se, episode, ext))
    else:
        rel = os.path.join(subdir, "%s%s" % (title, yr),
                           "%s%s%s" % (title, yr, ext))
    return safe_join(library_root, rel)


def is_junk(path: str, size: int) -> bool:
    """0 字节占位文件与 aria2 控制文件都不可入库。

    aria2 ``--select-file`` 会给未选中的文件留下 0 字节占位，
    ``*.aria2`` 则是「尚未下完」的标记，二者入库都会污染媒体库。
    """
    base = os.path.basename(path)
    if base == ".aria2" or base.endswith(".aria2"):
        return True
    return size == 0


def _st_dev(path: str):
    """取路径所在设备号；路径不存在时退一级看父目录。"""
    try:
        return os.stat(path).st_dev
    except OSError:
        pass
    parent = os.path.dirname(os.path.abspath(path))
    try:
        return os.stat(parent).st_dev
    except OSError:
        return None


def same_fs(a: str, b: str) -> bool:
    """两路径是否同文件系统（不存在的路径返回 False，不猜）。"""
    da = _st_dev(a)
    db = _st_dev(b)
    if da is None or db is None:
        return False
    return da == db


def link_probe(src_dir: str, dst_dir: str) -> bool:
    """硬链接能力探针：真链一次再清理，不靠异常驱动流程。

    仅同文件系统且同挂载点才可能成功，探针失败即意味着必须回退复制。
    """
    if not (os.path.isdir(src_dir) and os.path.isdir(dst_dir)):
        return False
    if not same_fs(src_dir, dst_dir):
        return False
    base = ".mbs-linkprobe-%d" % os.getpid()
    a = os.path.join(src_dir, base)
    b = os.path.join(dst_dir, base + ".lnk")
    try:
        with open(a, "wb"):
            pass
        os.link(a, b)
        return True
    except OSError:
        return False
    finally:
        for p in (b, a):
            try:
                os.unlink(p)
            except OSError:
                pass


def _is_incomplete(path: str) -> bool:
    """判断文件是否仍在下载中。

    aria2c 以同名 ``.aria2`` 控制文件标记「尚未下完」：单文件种子写在文件旁边
    （``Movie.mkv.aria2``），多文件种子写在批次目录旁（``Show.aria2``）。
    任一存在即视为未完成。
    """
    if os.path.exists(path + ".aria2"):
        return True
    parent = os.path.dirname(path)
    if parent and os.path.exists(parent + ".aria2"):
        return True
    return False


def plan(src_dir: str, library_root: str, media_type="movie", cfg=None) -> list:
    """扫描下载目录生成归档计划（不落盘）；默认 ``move``：同盘瞬时且不占额外空间。"""
    cfg = cfg or {}
    action = cfg.get("archive_action", "move")
    out = []
    for root, _dirs, files in os.walk(src_dir):
        for f in sorted(files):
            full = os.path.join(root, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue                      # 断链或权限问题，跳过而不是猜
            if is_junk(full, size):
                continue
            if _is_incomplete(full):
                continue                      # 下载中：搬进媒体库会留下残缺文件
            ext = os.path.splitext(f)[1].lower()
            if ext not in MEDIA_EXTS and ext not in SIDECAR_EXTS:
                continue                      # readme/url/exe 之类不进媒体库
            info = parser.parse(f)
            if info["episode"] is None and ext in SIDECAR_EXTS:
                continue                      # 整片字幕/封面归属不明，不硬塞
            if not info.get("title"):
                continue
            try:
                dest = target_path(library_root, media_type, info["title"],
                                   info.get("year"), info.get("season"),
                                   info.get("episode"), ext or ".mkv")
            except ValueError:
                continue                      # 拼不出安全目标就放弃，不静默改路径
            out.append({"src": full, "dest": dest, "action": action,
                        "size": size, "media_type": media_type})
    return out


def _cfg_int(cfg: dict, key: str, default):
    try:
        val = cfg.get(key, default)
        if val is None:
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


def _atomic_copy(src: str, dest: str) -> None:
    """先写同目录 .part 再 os.replace：中断不会留下半个「成品」。"""
    tmp = "%s.part-%d" % (dest, os.getpid())
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _copy_or_refuse(src: str, dest: str, size, cfg: dict, tag: str) -> str:
    """回退复制的唯一入口：大文件必须显式放行，绝不静默复制。"""
    warn = _cfg_int(cfg, "copy_warn_bytes", DEFAULT_COPY_WARN_BYTES)
    if warn and size and size > warn and not cfg.get("allow_large_copy"):
        return "refused-large-copy-%s:%d>%d" % (tag, size, warn)
    _atomic_copy(src, dest)
    return "%s+copied" % tag


def execute(plan_items: list, dry_run=True, cfg=None) -> list:
    """执行归档计划，逐条返回结果；失败只记录不中断。

    结果取值：``dry-run`` / ``skipped-exists`` / ``moved`` /
    ``moved-cross-device-link`` / ``moved-cross-device-copied`` /
    ``linked`` / ``hardlink-unavailable-EXDEV+copied`` /
    ``refused-large-copy-...`` / ``error:...``。
    """
    cfg = cfg or {}
    log = []
    for it in plan_items:
        src = it.get("src", "")
        dest = it.get("dest", "")
        action = it.get("action", "move")
        try:
            size = it.get("size")
            if size is None:
                size = os.path.getsize(src)
        except OSError:
            size = 0

        if dry_run:
            log.append({"src": src, "dest": dest, "result": "dry-run", "size": size})
            continue

        if not src or not dest:
            log.append({"src": src, "dest": dest, "result": "error:missing src/dest"})
            continue
        if not os.path.exists(src):
            log.append({"src": src, "dest": dest, "result": "error:source-missing"})
            continue
        if os.path.exists(dest):
            # 默认不覆盖：宁可让用户自己决定
            log.append({"src": src, "dest": dest, "result": "skipped-exists"})
            continue

        dest_dir = os.path.dirname(dest)
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as e:
            log.append({"src": src, "dest": dest, "result": "error:%s" % e})
            continue

        try:
            if action == "move":
                result = _do_move(src, dest, dest_dir, size, cfg)
            elif action == "hardlink":
                result = _do_hardlink(src, dest, dest_dir, size, cfg)
            elif action == "copy":
                result = _copy_or_refuse(src, dest, size, cfg, "copy")
            else:
                log.append({"src": src, "dest": dest,
                            "result": "error:unknown-action:%s" % action})
                continue
        except OSError as e:
            log.append({"src": src, "dest": dest, "result": "error:%s" % e})
            continue
        log.append({"src": src, "dest": dest, "result": result,
                    "size": size, "action": action})
    return log


def _do_move(src, dest, dest_dir, size, cfg) -> str:
    """第一级 rename；跨设备则 link 后删源；再不行才复制（带体积闸门）。"""
    try:
        os.replace(src, dest)
        return "moved"
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    # 跨挂载点：link + unlink 仍是瞬时且不占额外空间
    if link_probe(os.path.dirname(os.path.abspath(src)), dest_dir):
        try:
            os.link(src, dest)
            os.unlink(src)
            return "moved-cross-device-link"
        except OSError:
            try:
                os.unlink(dest)
            except OSError:
                pass
    result = _copy_or_refuse(src, dest, size, cfg, "moved-cross-device")
    if "copied" in result:
        os.unlink(src)
        return result.replace("+copied", "-copied")
    return result


def _do_hardlink(src, dest, dest_dir, size, cfg) -> str:
    src_dir = os.path.dirname(os.path.abspath(src))
    if not link_probe(src_dir, dest_dir):
        # 跨挂载点：源文件保留，如实上报并回退复制
        return _copy_or_refuse(src, dest, size, cfg, "hardlink-unavailable-EXDEV")
    try:
        os.link(src, dest)
        return "linked"
    except OSError as e:
        return _copy_or_refuse(src, dest, size, cfg,
                               "hardlink-failed-%s" % (e.errno,))
