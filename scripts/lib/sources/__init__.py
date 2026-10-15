"""可插拔源适配器注册表与聚合查询。

新增源：实现 base.Source 子类，追加到 _BUILTIN 即可被 registry() 收录。
"""
from __future__ import annotations

from . import knaben
from .base import Result, Source

_BUILTIN = [knaben.KnabenSource()]


def all_sources():
    """全部内置源实例（不论是否启用）。"""
    return list(_BUILTIN)


def registry(cfg=None):
    """按配置返回启用的源。未配置或未设 sources_enabled 时返回全部内置源。"""
    if cfg is None:
        return list(_BUILTIN)
    enabled = cfg.get("sources_enabled")
    if enabled is None:
        return list(_BUILTIN)
    return [s for s in _BUILTIN if s.id in enabled]


def by_id(src_id, cfg=None):
    """按 id 取源；未启用或不存在返回 None。"""
    for s in registry(cfg):
        if s.id == src_id:
            return s
    return None


def search_all(query, cfg=None, timeout=20):
    """并发查询全部启用源，单源失败不影响其余。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cfg = cfg or {}
    proxy = cfg.get("proxy", "")
    srcs = registry(cfg)
    if not srcs:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(srcs)))) as ex:
        futs = {ex.submit(s.search, query, timeout, proxy): s for s in srcs}
        for f in as_completed(futs):
            try:
                results.extend(f.result())
            except Exception:
                continue   # 单源失败静默跳过，由 doctor 负责上报健康度
    return results


__all__ = ["Result", "Source", "all_sources", "registry", "by_id", "search_all"]
