"""中文字幕检索、下载清洗与本地检测。

免密钥接口：GET https://rest.opensubtitles.org/search/query-<片名>/sublanguageid-chi
实测要点：
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

    实测坑：路径里出现大写 ASCII 字符时，服务器会 302 到 ``https://_/...``
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
