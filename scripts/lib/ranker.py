import re
from . import parser

STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for"}

# 续集/后续作的序号形式：中文数字尾缀、罗马数字、阿拉伯数字尾缀
_SEQUEL_CN = re.compile(r"[\u4e00-\u9fff]{2,}(?:[2-9]|[一二三四五六七八九十]{1,3})")
_SEQUEL_ROMAN = re.compile(r"\b(I{2,3}|IV|VI{0,3}|IX|XI{0,3})\b")
_SEQUEL_NUM_SUFFIX = re.compile(r"\b([2-9]|1[0-9])\b")

# 续集惩罚：需显著小于中字权重，使「有中字的续集」仍胜过「无中字的正片」
SEQUEL_PENALTY = 1000.0


def _tokens(text: str) -> list:
    latin = [t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if len(t) >= 3]
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return [t for t in latin if t not in STOPWORDS] + cjk


def passes_token_gate(result_title: str, query: str) -> bool:
    """结果标题必须命中查询词元，否则判为源侧语义污染并丢弃。"""
    q = _tokens(query)
    if not q:
        return True
    t = set(_tokens(result_title))
    lowered = result_title.lower()
    for token in q:
        if re.search(r"[\u4e00-\u9fff]", token):
            if token in result_title:
                return True
            for i in range(len(token) - 1):
                if token[i:i + 2] in result_title:
                    return True
        else:
            if token in t or token in lowered:
                return True
    return False


def is_sequel(result_title: str, query: str) -> bool:
    """判断结果是否为查询片名的续集/后续作。

    续集是不同作品：查「某片」时不该把「某片2」当成同一部推给用户。
    """
    if not query:
        return False
    stem = re.sub(r"\.(mkv|mp4|avi|ts|m2ts|srt|ass|ssa|nfo)$", "", result_title, flags=re.I)

    for token in _tokens(query):
        if not re.search(r"[\u4e00-\u9fff]", token):
            continue
        # 中文：查询词后紧跟序号（数字或中文数字）即为续集
        for m in re.finditer(re.escape(token), stem):
            tail = stem[m.end():m.end() + 8]
            # 年份不是续集序号（'流浪地球 2019' 是正片，不是第 2 部）
            if re.match(r"^[\s._\-]*(19|20)\d{2}(?!\d)", tail):
                continue
            if re.match(r"^[\s._\-]*[2-9](?!\d)", tail):
                return True
            if re.match(r"^[\s._\-]*[一二三四五六七八九十]", tail):
                return True
        # 查询词自身已含序号尾缀时，不判为续集（用户查的就是续集）
        if _SEQUEL_CN.fullmatch(token):
            return False

    for token in _tokens(query):
        if re.search(r"[\u4e00-\u9fff]", token):
            continue
        low = stem.lower()
        idx = low.find(token)
        if idx < 0:
            continue
        tail = stem[idx + len(token):idx + len(token) + 8]
        if re.match(r"^[\s._\-]*(I{2,3}|IV|V|VI{0,3})\b", tail.strip()):
            return True
        if re.match(r"^[\s._\-]*(?:part|chapter|season)?[\s._\-]*[2-9]\b", tail, re.I):
            return True
        if re.search(r"\b(?:II|III|IV|VI)\b", stem):
            return True
    return False


def score(result, query: str, cfg: dict) -> float:
    s = float(result.seeders)
    if cfg.get("subtitle_priority", True) and parser.has_chinese_subtitle(result.title):
        s += 5000.0          # 中字是第一权重：无中字的高清片对中文用户价值低于有中字的低清片
    q = len(parser.parse(result.title).get("marks", set()))
    if q:
        s += q * 20.0
    if cfg.get("preferred_quality"):
        if cfg["preferred_quality"].lower() in result.title.lower():
            s += 300.0
    if is_sequel(result.title, query):
        s -= SEQUEL_PENALTY   # 续集是不同作品，同样中字条件下让正片优先
    s -= (result.size / 10**9)          # 同种子数下偏好小体积
    return s


def rank(results: list, query: str, cfg: dict) -> list:
    cfg = cfg or {}
    max_gb = cfg.get("max_size_gb") or 0
    kept = []
    for r in results:
        if not passes_token_gate(r.title, query):
            continue
        if max_gb and r.size > max_gb * 10**9:
            continue
        kept.append(r)
    kept.sort(key=lambda r: score(r, query, cfg), reverse=True)
    return kept


def dedupe(results: list) -> list:
    """按 info_hash 去重；无 hash 时回落标题去重（不能把无 hash 的互相误删）。"""
    seen = set()
    out = []
    for r in results:
        key = _hash_of(r.magnet) or "title:" + (r.title or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _hash_of(magnet: str) -> str:
    m = re.search(r"btih:([A-Za-z0-9]+)", magnet or "")
    return m.group(1).lower() if m else ""
