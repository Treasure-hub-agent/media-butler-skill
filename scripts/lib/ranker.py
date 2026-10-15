import re
from . import parser

STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for"}

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
            # 中文按 2 字滑窗放宽，容忍译名差异
            for i in range(len(token) - 1):
                if token[i:i + 2] in result_title:
                    return True
        else:
            if token in t or token in lowered:
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
    """按 info_hash 去重；无 hash 时按标题去重。"""
    seen = set()
    out = []
    for r in results:
        key = _hash_of(r.magnet)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def _hash_of(magnet: str) -> str:
    m = re.search(r"btih:([A-Za-z0-9]+)", magnet or "")
    return m.group(1).lower() if m else ""
