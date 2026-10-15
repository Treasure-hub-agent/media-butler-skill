import re

# 中文字幕标记 → 词表放 references/subtitles.md，此处为运行时必需的最小集合
CN_MARKS = [
    "中字", "中文", "简体", "繁体", "简中", "繁中", "简繁", "双语", "中英",
    "国语", "國語", "粤语", "粵語", "内封", "内嵌", "外挂",
]
CN_LATIN = ["CHS", "CHT", "GB", "BIG5"]
CN_GROUP_HINTS = ["字幕组", "字幕組"]

_EP_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,4})"),
    re.compile(r"[Ee]pisode[\s._-]*(\d{1,4})", re.I),
    re.compile(r"第\s*(\d{1,4})\s*[集话話]"),
]
_SEASON_PATTERNS = [
    re.compile(r"(\d{1,2})x(\d{2})"),
    re.compile(r"[Ss]eason[\s._-]*(\d{1,2})", re.I),
]
_RANGE = re.compile(r"(\d{1,4})\s*[-~]\s*(\d{1,4})")

def has_chinese_subtitle(text: str) -> bool:
    if any(m in text for m in CN_MARKS):
        return True
    upper = text.upper()
    if any(m in upper for m in CN_LATIN):
        return True
    # 拉丁 CHS/CHT 需词边界，避免误命中随机子串
    if re.search(r"(?<![A-Z])(CHS|CHT)(?![A-Z])", upper):
        return True
    return any(g in text for g in CN_GROUP_HINTS)

def parse(name: str) -> dict:
    stem = re.sub(r"\.(mkv|mp4|avi|ts|m2ts|srt|ass|ssa)$", "", name, flags=re.I)
    marks = {m for m in CN_MARKS if m in stem}
    marks |= {m for m in CN_LATIN if m in stem.upper()}
    groups = [g for g in CN_GROUP_HINTS if g in stem]

    season = episode = None
    for p in _EP_PATTERNS:
        m = p.search(stem)
        if m:
            gs = m.groups()
            if len(gs) == 2:
                season, episode = int(gs[0]), int(gs[1])
            else:
                episode = int(gs[0])
            break

    if season is None:
        for p in _SEASON_PATTERNS:
            m = p.search(stem)
            if m:
                season = int(m.group(1))
                break

    year = None
    m = re.search(r"(19\d{2}|20\d{2})", stem)
    if m:
        year = int(m.group(1))

    is_batch = bool(_RANGE.search(stem)) or bool(
        re.search(r"(complete|batch|合集|全集|全\d+[集话話])", stem, re.I))

    return {
        "title": _clean_title(stem, year),
        "year": year,
        "season": season,
        "episode": episode,
        "is_batch": is_batch,
        "marks": marks | set(groups),
        "groups": groups,
    }

def _clean_title(stem: str, year) -> str:
    t = stem
    if year:
        idx = t.find(str(year))
        if idx > 0:
            t = t[:idx]
    t = re.split(r"[\[\(【]", t)[0]
    t = t.replace(".", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip(" -")
    return t
