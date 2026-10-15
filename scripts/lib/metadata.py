"""元数据查询与中英文检索名生成。

中文用户搜中文片名往往搜不到：国际索引源只认拉丁名。这里用 AniList
（免密钥、提供 romaji/english/native 三语名）把中文名映射成可检索的英文名。
"""
import json, re, urllib.request

ANILIST = "https://graphql.anilist.co"
UA = "Mozilla/5.0"


def search_names(name: str) -> list:
    """生成多种可检索写法，供跨语言检索使用。"""
    out = []
    base = re.sub(r"\.(mkv|mp4|avi)$", "", name, flags=re.I).strip()
    if base:
        out.append(base)
    no_year = re.sub(r"\b(19|20)\d{2}\b", "", base).strip(" -_.")
    if no_year and no_year != base:
        out.append(no_year)
    cleaned = re.sub(r"[._]+", " ", base)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned not in out:
        out.append(cleaned)
    return out


def parse_anilist(payload: dict):
    media = (payload or {}).get("data", {}).get("Media")
    if not media:
        return None
    t = media.get("title") or {}
    start = media.get("startDate") or {}
    return {
        "title": t.get("romaji") or t.get("english") or t.get("native") or "",
        "native": t.get("native") or "",
        "english": t.get("english") or "",
        "year": start.get("year"),
        "episodes": media.get("episodes"),
    }


def lookup(name: str, cfg: dict = None, timeout=20) -> dict:
    """查元数据；AniList 为主（免密钥、中日英三语名齐全）。查不到返回 {}。

    注意：必须带 Content-Type: application/json 与 User-Agent，否则端点返回 404。
    """
    cfg = cfg or {}
    query = '{Media(search:%s,type:ANIME){title{romaji native english} episodes startDate{year}}}' % json.dumps(name)
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        ANILIST, data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Accept": "application/json"},
    )
    proxy = cfg.get("proxy", "")
    opener = (urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        if proxy else urllib.request.build_opener())
    try:
        with opener.open(req, timeout=timeout) as resp:
            return parse_anilist(json.loads(resp.read().decode("utf-8"))) or {}
    except Exception:
        # 网络异常/查不到都返回空，不阻断下载主流程
        return {}


def best_search_terms(name: str, cfg: dict = None) -> list:
    """产出优先检索名列表：元数据英文名优先（国际源只认拉丁名），其次原名。"""
    meta = lookup(name, cfg)
    terms = []
    for key in ("english", "title"):
        v = (meta or {}).get(key)
        if v and v not in terms:
            terms.append(v)
    for n in search_names(name):
        if n not in terms:
            terms.append(n)
    return terms
