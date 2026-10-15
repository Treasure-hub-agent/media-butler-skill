import re

# 中文字幕标记 → 完整词表放 references/subtitles.md，此处为运行时必需的最小集合
CN_MARKS = [
    "中字", "中文", "简体", "繁体", "简中", "繁中", "简繁", "双语", "中英",
    "国语", "國語", "粤语", "粵語", "内封", "内嵌", "外挂", "字幕",
]
CN_LATIN = ["CHS", "CHT", "GB", "BIG5"]
CN_GROUP_HINTS = ["字幕组", "字幕組"]

# 技术标签：标题提取时剥离的发布信息
_TECH_TAGS = re.compile(
    r"\b(1080p|2160p|720p|480p|4K|8K|UHD|HDR10|HDR|DoVi|DV|"
    r"BluRay|Blu-ray|BDRip|BRRip|WEB-?DL|WEBRip|HDTV|DVDRip|Remux|REMASTERED|"
    r"x264|x265|H\.?264|H\.?265|HEVC|AVC|AV1|10bit|8bit|10-bit|"
    r"AAC|AC3|DTS|DDP|DD5\.1|FLAC|TrueHD|Atmos|MA|"
    r"PROPER|REPACK|MULTi|DUAL|AUDIO)\b", re.I)

# 中文噪声词：不进标题的通用修饰
_NOISE_CN = ["电影", "高清", "高清版", "完整版", "未删减", "全集", "合集",
             "国语", "粤语", "中字", "中文字幕", "字幕",
             "正片", "花絮", "IMAX版", "加长版", "导演剪辑版", "版"]

# 发布组/压制组特征（出现在头部或尾部）
_GROUP_LIKE = re.compile(r"[-&@]|Raws|Studio|Team|Sub|Fansub|字幕组|字幕組|压制", re.I)

_BATCH_WORD = re.compile(r"\b(complete|batch|series|seasons?)\b|合集|全集|全\d+[集话話]", re.I)

_EP_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,4})"),                      # S02E07
    re.compile(r"(\d{1,2})x(\d{2})(?!\d)"),                        # 2x07
    re.compile(r"[Ee]pisode[\s._-]*(\d{1,4})", re.I),               # Episode 245
    re.compile(r"第\s*(\d{1,4})\s*[集话話]"),                          # 第245集
    re.compile(r"\[\s*(\d{1,4})\s*\]"),                             # [03]
    re.compile(r"(?:^|[\s._])-\s*(\d{1,4})(?![\dpiP])"),           # " - 03 "
]
_SEASON_PATTERNS = [re.compile(r"[Ss]eason[\s._-]*(\d{1,2})", re.I)]
_RANGE = re.compile(r"(\d{1,4})\s*[-~]\s*(\d{1,4})")
_BRACKET_BLOCK = re.compile(r"[\[\(【]([^\]\)】]*)[\]\)】]")
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def has_chinese_subtitle(text: str) -> bool:
    if any(m in text for m in CN_MARKS):
        return True
    upper = text.upper()
    if any(m in upper for m in CN_LATIN):
        return True
    return any(g in text for g in CN_GROUP_HINTS)


def parse(name: str) -> dict:
    stem = re.sub(r"\.(mkv|mp4|avi|ts|m2ts|wmv|flv|rmvb|srt|ass|ssa|nfo)$", "", name, flags=re.I)
    marks = {m for m in CN_MARKS if m in stem}
    marks |= {m for m in CN_LATIN if m in stem.upper()}
    groups = [g for g in CN_GROUP_HINTS if g in stem]

    season = episode = None
    for p in _EP_PATTERNS:
        m = p.search(stem)
        if not m:
            continue
        gs = m.groups()
        if len(gs) == 2:
            season, episode = int(gs[0]), int(gs[1])
        else:
            episode = int(gs[0])
        if episode is not None and 1900 <= episode <= 2099:
            episode = None      # 年份不是集号
            continue
        break

    if season is None:
        for p in _SEASON_PATTERNS:
            m = p.search(stem)
            if m:
                season = int(m.group(1))
                break

    ym = _YEAR.search(stem)
    year = int(ym.group(1)) if ym else None

    is_batch = bool(_RANGE.search(stem)) or bool(_BATCH_WORD.search(stem))

    return {
        "title": _clean_title(stem, year, episode),
        "year": year,
        "season": season,
        "episode": episode,
        "is_batch": is_batch,
        "marks": marks | set(groups),
        "groups": groups,
    }


def _clean_title(stem: str, year, episode) -> str:
    """从资源名提炼标题（会直接成为归档目录名，必须干净）。

    括号块分三类处理：技术块与标记块丢弃；最前部的组名块丢弃；
    其余（片名，含双语名）保留下文本。
    """
    t = stem

    if year:
        idx = t.find(str(year))
        if idx > 0:
            t = t[:idx]

    blocks = _BRACKET_BLOCK.findall(t)
    first_block_lead = bool(re.match(r"^\s*[\[\(【]", t))

    def _keep(m):
        inner = m.group(1).strip()
        if not inner:
            return " "
        if _is_tech_block(inner) or _has_marks(inner) or _is_noise(inner):
            return " "
        # 仅当块位于最前部、且形如发布组时才判为组名
        if first_block_lead and m.start() <= 2 and _GROUP_LIKE.search(inner):
            return " "
        return " " + inner + " "

    t = _BRACKET_BLOCK.sub(_keep, t)

    t = _TECH_TAGS.sub(" ", t)
    t = _RANGE.sub(" ", t)
    t = _BATCH_WORD.sub(" ", t)
    for w in _NOISE_CN:
        t = t.replace(w, " ")
    t = re.sub(r"[-@][A-Za-z0-9]{2,20}\b", " ", t)     # 尾部发布组
    t = re.sub(r"[Ss]\d{1,2}[Ee]\d{1,4}", " ", t)      # 残留集号标记
    t = re.sub(r"[Ee]pisode[\s._-]*\d{1,4}", " ", t, flags=re.I)

    t = t.replace(".", " ").replace("_", " ").replace("/", " / ")
    t = re.sub(r"\s+", " ", t).strip(" -~/+")

    # 集号剥离放在归一化之后：此时尾部已是干净的 "- 33" 形态
    if episode is not None:
        t = re.sub(r"(?:^|\s)[-~]?\s*0*%d\s*$" % episode, "", t)
    t = re.sub(r"[\s~-]+$", "", t).strip()

    return t


def _has_marks(inner: str) -> bool:
    return any(m in inner for m in CN_MARKS) or any(m in inner.upper() for m in CN_LATIN)


def _is_noise(inner: str) -> bool:
    return any(w in inner for w in _NOISE_CN)


def _is_tech_block(inner: str) -> bool:
    """整块都是技术标签（如 '1080P'、'WebRip 1080p HEVC-10bit AAC'）时判为技术块。"""
    parts = [p for p in re.split(r"[\s\+&/_]+", inner) if p]
    if not parts:
        return True
    for p in parts:
        if _TECH_TAGS.fullmatch(p):
            continue
        if re.fullmatch(r"\d{3,4}[pPiI]", p):      # 1080P / 720i
            continue
        if re.fullmatch(r"\d+bit", p, re.I):
            continue
        return False
    return True
