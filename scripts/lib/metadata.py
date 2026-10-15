"""元数据查询与中英文检索名生成。

中文用户搜中文片名往往搜不到：国际索引源只认拉丁名。这里用 AniList
（免密钥、提供 romaji/english/native 三语名）把中文名映射成可检索的英文名。

AniList 对中文名的命中率不稳定（同类中文名有的能查、有的查不到），
因此采用多策略回退：逐个策略尝试，任一命中即返回。
"""
import json, re, urllib.request

ANILIST = "https://graphql.anilist.co"
UA = "Mozilla/5.0"

_MEDIA_FIELDS = "title{romaji native english} episodes startDate{year}"


def search_names(name: str) -> list:
    """生成多种可检索写法，供跨语言检索使用。"""
    out = []
    base = re.sub(r"\.(mkv|mp4|avi)$", "", name, flags=re.I).strip()
    if base:
        out.append(base)

    no_year = re.sub(r"\b(19|20)\d{2}\b", "", base).strip(" -_.")
    if no_year:
        out.append(no_year)

    # 去季/部/第N季等番剧尾缀，提升命中率
    no_season = re.sub(r"[\s第]*(?:第)?\s*[一二三四五六七八九十\d]+\s*(?:季|部|期|篇)$", "", no_year).strip(" -_.")
    if no_season:
        out.append(no_season)

    cleaned = re.sub(r"[._]+", " ", base)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned:
        out.append(cleaned)

    # 去重且保持顺序
    seen, uniq = set(), []
    for n in out:
        if n and n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


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


def _post_graphql(query: str, timeout: int, proxy: str):
    """发一次 GraphQL 请求；网络异常或返回空都返回 None，不抛。"""
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        ANILIST, data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Accept": "application/json"},
    )
    opener = (urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        if proxy else urllib.request.build_opener())
    try:
        with opener.open(req, timeout=timeout) as resp:
            return parse_anilist(json.loads(resp.read().decode("utf-8")))
    except Exception:
        return None


def _fetch_media(query: str, timeout=20, proxy="") -> dict:
    """单个策略的查询：给定 GraphQL query 文本取一条 Media 记录。"""
    query_text = "{Media(%s){%s}}" % (query, _MEDIA_FIELDS)
    return _post_graphql(query_text, timeout, proxy)


def _strategies(name: str):
    """按命中率从高到低排列的查询策略。"""
    yield 'search:%s,type:ANIME' % json.dumps(name)
    yield 'search:%s' % json.dumps(name)
    # 去番剧尾缀再试
    for alt in search_names(name)[1:]:
        if alt != name:
            yield 'search:%s,type:ANIME' % json.dumps(alt)
            yield 'search:%s' % json.dumps(alt)
    # 模糊搜索兜底：抓一批候选再本地比对
    yield 'search:%s,type:ANIME,isAdult:false' % json.dumps(name)


def lookup(name: str, cfg: dict = None, timeout=20) -> dict:
    """查元数据；AniList 为主（免密钥、中日英三语名齐全）。全失败返回 {}。

    注意：必须带 Content-Type: application/json 与 User-Agent，否则端点返回 404。
    """
    cfg = cfg or {}
    proxy = cfg.get("proxy", "")
    for strategy in _strategies(name):
        try:
            media = _fetch_media(strategy, timeout=timeout, proxy=proxy)
        except Exception:
            continue
        if media:
            return media
    return {}


def lookup_multi(term: str, cfg: dict = None, timeout=20) -> dict:
    """按候选名逐个尝试（供 CLI 的 meta 命令在单名失败时补试）。"""
    cfg = cfg or {}
    for candidate in search_names(term):
        r = lookup(candidate, cfg, timeout)
        if r:
            return r
    return {}


def best_search_terms(name: str, cfg: dict = None) -> list:
    """产出优先检索名列表：元数据英文名优先（国际源只认拉丁名），其次原名。"""
    meta = lookup_multi(name, cfg)
    terms = []
    for key in ("english", "title"):
        v = (meta or {}).get(key)
        if v and v not in terms:
            terms.append(v)
    for n in search_names(name):
        if n not in terms:
            terms.append(n)
    return terms
