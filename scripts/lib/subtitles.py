"""中文字幕检索、下载清洗与本地检测。

免密钥接口：GET https://rest.opensubtitles.org/search/query-<片名>/sublanguageid-chi
接口要点：
  * 必须使用播放器风格的 User-Agent，否则请求被拒（403/空响应）。
  * 返回 JSON 数组，SubDownloadLink 指向 .gz，需 gzip 解压后才是 srt。
  * 返回正文常夹带推广行（如 “厌倦了搜索字幕? Ray即刻生成字幕: getray.app”），
    必须清洗，否则会随字幕进入播放器画面。
"""
import gzip, json, os, re, urllib.parse, urllib.request
from pathlib import Path

LEGACY = "https://rest.opensubtitles.org/search"
UA = "TemPlayer v1.0"     # 该免密钥接口要求以播放器 UA 访问

def parse_results(payload) -> list:
    out = []
    for s in payload or []:
        url = s.get("SubDownloadLink")
        if not url:
            continue
        try:
            dl = int(s.get("SubDownloadsCnt") or 0)
        except (TypeError, ValueError):
            dl = 0
        out.append({
            "name": s.get("SubFileName") or "",
            "lang": s.get("SubLanguageID") or "",
            "downloads": dl,
            "format": s.get("SubFormat") or "",
            "url": url,
        })
    out.sort(key=lambda x: x["downloads"], reverse=True)
    return out

def _opener(cfg: dict):
    proxy = (cfg or {}).get("proxy", "")
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()

def build_search_url(query: str) -> str:
    """构造免密钥检索 URL。

    注意：路径里出现大写 ASCII 字符时，服务器会 302 到无效域名
    （空 Host，必然解析失败），因此查询词必须先统一转小写。
    """
    return "%s/query-%s/sublanguageid-chi" % (
        LEGACY, urllib.parse.quote(query.strip().lower()))

def search(query: str, cfg=None, timeout=25) -> list:
    cfg = cfg or {}
    if not (query or "").strip():
        return []
    req = urllib.request.Request(build_search_url(query), headers={"User-Agent": UA})
    try:
        with _opener(cfg).open(req, timeout=timeout) as resp:
            return parse_results(json.loads(resp.read().decode("utf-8", "replace")))
    except Exception:
        return []   # 网络异常/被限流时不阻断主流程

_AD_LINE = re.compile(r"getray\.app|opensubtitles|字幕由.*提供", re.I)

def clean_srt(text: str) -> str:
    """该接口的返回常夹带推广行，清洗掉首块广告后保留正文。"""
    text = text.lstrip("\ufeff")
    if not _AD_LINE.search(text):
        return text
    blocks = re.split(r"\r?\n\r?\n", text)
    kept = [b for b in blocks if not _AD_LINE.search(b)]
    if len(kept) == len(blocks):
        # 广告与正文字幕同块（缺空行分隔）时，退化为逐行剔除
        kept = []
        for b in blocks:
            lines = [l for l in b.splitlines() if not _AD_LINE.search(l)]
            if lines:
                kept.append("\n".join(lines))
    return "\n\n".join(kept)

def fetch(url: str, dest_dir: str, cfg=None, timeout=40) -> str:
    """下载并解压字幕；返回落地 .srt 路径，失败返回 ''。"""
    cfg = cfg or {}
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with _opener(cfg).open(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return ""
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            return ""
    text = clean_srt(raw.decode("utf-8", "replace"))
    name = "subtitle." + ("ass" if ".ass" in url else "srt")
    out = Path(dest_dir) / name
    out.write_text(text, encoding="utf-8")
    return str(out)

# 中文字幕轨的常见命名（语言代码与中文标签）
# 中文字幕轨的常见命名：语言代码、中文标签、以及「简日双语」这类双语写法
_CN_TRACK_HINTS = [
    "zh-hans", "zh-hant", "zh-cn", "zh-tw", "zh", "chs", "cht", "chi",
    "简", "繁", "简体", "繁体", "繁體", "中文", "中字", "简中", "繁中", "简繁",
    "双语", "雙語", "sc", "tc",
]
_EBML_HEADER = b"\x1a\x45\xdf\xa3"
# MKV 轨道名元素：0x536E (Name)，后跟 EBML 变长长度
_NAME_ELEM = b"\x53\x6e"


def _read_ebml_strings(data: bytes, limit=64) -> list:
    """从 EBML 数据里提取轨道名字符串（纯 stdlib，不依赖 ffprobe）。

    只做「名称元素 + 变长长度 + UTF-8 文本」的浅解析：够用且不会误报，
    因为只有真正的轨道名才会命中中文字幕关键词。
    """
    out = []
    i = 0
    n = len(data)
    while i < n - 3 and len(out) < limit:
        if data[i:i + 2] == _NAME_ELEM:
            j = i + 2
            first = data[j]
            if first == 0:
                i += 1
                continue
            # 变长长度：首字节前导 1 的位数即长度字节数
            length_bytes = 1
            mask = 0x80
            while length_bytes <= 8 and not (first & mask):
                mask >>= 1
                length_bytes += 1
            if length_bytes > 4 or j + length_bytes > n:
                i += 1
                continue
            size = first & (mask - 1) if length_bytes == 1 else first & (0xFF >> length_bytes)
            for k in range(1, length_bytes):
                size = (size << 8) | data[j + k]
            start = j + length_bytes
            if 0 < size <= 128 and start + size <= n:
                raw = data[start:start + size]
                try:
                    text = raw.decode("utf-8")
                    if text.isprintable() or any(ord(c) > 127 for c in text):
                        out.append(text)
                except UnicodeDecodeError:
                    pass
                i = start + size
                continue
        i += 1
    return out


def detect_embedded(video_path: str, head_bytes=4 * 1024 * 1024) -> dict:
    """探测视频内嵌的中文字幕轨（读文件头部，不依赖外部工具）。

    返回 ``{"has_chinese": bool, "tracks": [命中的轨道名]}``。
    """
    result = {"has_chinese": False, "tracks": []}
    try:
        with open(video_path, "rb") as f:
            head = f.read(head_bytes)
    except OSError:
        return result
    if not head.startswith(_EBML_HEADER):
        return result
    names = _read_ebml_strings(head)
    hits = []
    for name in names:
        low = name.lower()
        if any(h in low for h in _CN_TRACK_HINTS):
            hits.append(name)
    result["tracks"] = hits
    result["has_chinese"] = bool(hits)
    return result


def detect_local(video_path: str) -> str:
    """检测同目录外挂中文字幕（不做内封字幕轨解析，那需要 ffprobe）。"""
    p = Path(video_path)
    for ext in (".srt", ".ass", ".ssa"):
        cand = p.with_suffix(ext)
        if cand.exists():
            return str(cand)
        # 语言后缀形式：Movie.zh.srt / Movie.chs.srt
        for tag in (".zh", ".chs", ".cht", ".chi"):
            c2 = p.with_name(p.stem + tag + ext)
            if c2.exists():
                return str(c2)
    return ""
