"""aria2 调用与合集选集定位。

设计约束（均为实测结论，勿改动）：
- 必带 ``--file-allocation=none``：aria2 默认预分配，实测 25 秒占满 1.9GB。
- 必带 ``--seed-time=0``：默认会继续做种，占用带宽与磁盘。
- 必带 ``--no-conf=true``：忽略用户 ``~/.aria2/aria2.conf``，防止它把上面两条覆盖掉。
- DHT 入口只保留实测可连通的 dht.transmissionbt.com:6881，其余常见入口均超时。
- tracker 只保留实测可用的三个，其余多数已失效。
- 磁力链/查询词是攻击者可控输入：一律作为独立 argv 元素交给 subprocess，
  绝不用 ``shell=True``，绝不拼命令字符串。
- aria2c 不支持 SOCKS 代理（实测报 ``unrecognized proxy format`` 后直接退出），
  故 SOCKS 型代理必须跳过而不是透传。
"""
import os, re, shutil, subprocess
from pathlib import Path

#: 实测筛选后的可用 tracker（DNS 污染与封锁会淘汰一部分，故内建可用集合）
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://open.stealth.si:80/announce",
]

#: 唯一实测可连通的 DHT 入口
DHT_ENTRY = "dht.transmissionbt.com:6881"

#: 代理 URL 的协议头里出现这些即视为 SOCKS，aria2c 不接受
_SOCKS_SCHEMES = ("socks4", "socks5", "socks5h", "socks")

#: 环境变量里代理的读取顺序（未设者忽略；all_proxy 语义最宽故优先）
_PROXY_ENV_KEYS = ("all_proxy", "ALL_PROXY", "https_proxy", "HTTPS_PROXY",
                   "http_proxy", "HTTP_PROXY")

_SENTINEL = object()


def aria2_available() -> bool:
    """aria2c 是否在 PATH 中。"""
    return shutil.which("aria2c") is not None


def is_socks(proxy: str) -> bool:
    """判断代理 URL 是否为 aria2c 不支持的 SOCKS 型。"""
    if not proxy:
        return False
    scheme = proxy.split("://", 1)[0].strip().lower() if "://" in proxy else ""
    return scheme in _SOCKS_SCHEMES


def env_proxy() -> str:
    """按序读取环境变量里的代理，取第一个非空的。都没有则返回 ''。"""
    for key in _PROXY_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            return val
    return ""


def resolve_proxy(cfg=None):
    """定出本次要用的代理。

    显式配置优先：``cfg`` 里给了 ``proxy`` 键就以其值为准（空串 = 用户要求直连，
    不再回落到环境变量）；没给该键时才读环境变量。
    返回 ``(proxy, usable)``：``usable`` 为 False 表示该代理不能传给 aria2c（SOCKS）。
    """
    cfg = cfg or {}
    if "proxy" in cfg:
        proxy = cfg.get("proxy") or ""
    else:
        proxy = env_proxy()
    if not proxy:
        return "", True
    return proxy, not is_socks(proxy)


def build_args(magnet, dest, select_files=None, cfg=None):
    """构造 aria2c 的 argv 列表。

    ``magnet`` 始终作为最后一个独立元素，不被任何 shell 解析。
    """
    cfg = cfg or {}
    args = [
        "aria2c",
        "--dir", dest,
        "--no-conf=true",            # 忽略用户 aria2.conf，保住下面两条安全参数
        "--file-allocation=none",    # 默认预分配会瞬间吃满磁盘
        "--seed-time=0",             # 默认会做种，必须关闭
        "--enable-dht=true",
        "--dht-entry-point=" + DHT_ENTRY,
        "--bt-tracker=" + ",".join(TRACKERS),
        "--bt-max-peers=200",
        "--summary-interval=10",
        "--console-log-level=warn",
        "--max-concurrent-downloads=" + str(cfg.get("concurrency", 3)),
    ]
    proxy, usable = resolve_proxy(cfg)
    if proxy and usable:
        args.append("--all-proxy=" + proxy)
    if select_files:
        # aria2 的 --select-file 是 1 基索引，逗号分隔
        args.append("--select-file=" + ",".join(str(i) for i in select_files))
    args.append(magnet)
    return args


def start(magnet, dest, select_files=None, cfg=None) -> dict:
    """后台启动下载，立即返回 ``{pid, log, dest, cmd}``；进度写进 ``dest/aria2.log``。"""
    cfg = cfg or {}
    Path(dest).mkdir(parents=True, exist_ok=True)
    log = str(Path(dest) / "aria2.log")
    args = build_args(magnet, dest, select_files, cfg)
    logfile = open(log, "ab")
    try:
        proc = subprocess.Popen(args, stdout=logfile, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, close_fds=True)
    except BaseException:
        logfile.close()
        raise
    logfile.close()  # 子进程持有自己的 fd，父进程关闭不影响写入
    return {"pid": proc.pid, "log": log, "dest": dest, "cmd": args}


def metadata_only(magnet, dest, cfg=None, timeout=180) -> str:
    """只取 torrent metadata（不下载正片），返回落地的 ``.torrent`` 路径；失败返回 ''。

    以文件名为准比对：dest 里已有的历史 ``.torrent`` 不算本次结果，避免多任务共享
    暂存目录时把上一个片子当成这一个。
    """
    cfg = cfg or {}
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in d.glob("*.torrent")}
    args = build_args(magnet, dest, cfg=cfg)
    args = [a for a in args if not a.startswith("--summary-interval")]
    # 只抓 metadata 并落盘，随后退出（--seed-time=0 已在 args 中）
    args[1:1] = ["--bt-metadata-only=true", "--bt-save-metadata=true"]
    try:
        subprocess.run(args, timeout=timeout, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        pass  # 超时/缺失只能靠落盘文件判断成败
    fresh = sorted(p for p in d.glob("*.torrent") if p.name not in before)
    return str(fresh[0]) if fresh else ""


def pick_index(files, episode=None, season=None):
    """按集号（必要时叠加季号）在文件列表里定位目标索引（1 基）。

    返回 aria2c ``--select-file`` 可用的索引；定位不到返回 None。
    """
    if episode is None:
        return None
    season_re = re.compile(r"[Ss](\d{1,2})\s*[Ex]", re.I)
    ep_word = re.compile(r"[Ee]pisode[\s._-]*0*(\d{1,4})(?!\d)")
    cn_ep = re.compile(r"第\s*0*(\d{1,4})\s*[集话話]")
    bracket_ep = re.compile(r"\[0*(\d{1,4})\](?!\d)")
    dash_ep = re.compile(r"[\s._-]0*(\d{1,4})(?![\dpiP])")
    for f in files:
        p = f.get("path", "")
        name = p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,4})", p)
        if m:
            if int(m.group(2)) == episode and (season is None
                                               or int(m.group(1)) == season):
                return f["index"]
            continue  # 已明确标了季集号，不退回模糊匹配
        if season is not None:
            s = season_re.search(name)
            if s and int(s.group(1)) != season:
                continue
        for pat in (ep_word, cn_ep, bracket_ep, dash_ep):
            m = pat.search(name)
            if m and int(m.group(1)) == episode:
                return f["index"]
    return None
