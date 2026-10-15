"""knaben 聚合器适配器。

接口要点（改动前务必确认）：
- POST https://api.knaben.org/v1，请求体字段 search_field/query/order_by/
  order_direction/size；**绝对不能加 search_type**（加了返回 0 条）。
- 返回 hits[] 字段为 title / magnetUrl / bytes / liveSeeders / tracker / category。
- 必须带 User-Agent 头，否则部分上游源 403。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import Result, Source

ENDPOINT = "https://api.knaben.org/v1"
UA = "Mozilla/5.0"


def to_result(hit):
    """knaben hit -> Result；无磁力链则返回 None（无下载价值）。"""
    magnet = hit.get("magnetUrl") or ""
    if not magnet:
        return None
    seeders = hit.get("liveSeeders")
    if seeders is None:
        seeders = hit.get("seeders") or 0
    title = str(hit.get("title") or "")
    marks = set()
    is_batch = False
    try:  # 解析失败不影响结果可用性
        from .. import parser as _parser
        info = _parser.parse(title)
        marks = set(info.get("marks") or ())
        is_batch = bool(info.get("is_batch"))
    except Exception:
        pass
    return Result(
        title=title,
        magnet=magnet,
        size=int(hit.get("bytes") or 0),
        seeders=int(seeders),
        source=str(hit.get("tracker") or "knaben"),
        category=str(hit.get("category") or ""),
        is_batch=is_batch,
        marks=marks,
    )


class KnabenSource(Source):
    id = "knaben"
    supports = ["movies", "tv", "anime"]
    query_script = "both"     # 中文与拉丁查询均可命中
    priority = 10

    def search(self, query, timeout=25, proxy="", size=30):
        payload = {
            "search_field": "title",
            "query": query,
            "order_by": "seeders",
            "order_direction": "desc",
            "size": size,
        }
        # 注意：不要加 search_type（会返回 0 条）
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": UA,
            },
        )
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        else:
            opener = urllib.request.build_opener()
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError("knaben HTTP %s" % exc.code)
        except urllib.error.URLError as exc:
            raise RuntimeError("knaben 连接失败: %s" % exc.reason)
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise RuntimeError("knaben 返回非 JSON")
        out = []
        for hit in data.get("hits") or []:
            r = to_result(hit)
            if r is not None:
                out.append(r)
        return out
