"""配置与状态目录管理。

状态目录优先级：环境变量 MEDIA_BUTLER_HOME > 平台默认。
"""
import json, os, tempfile
from pathlib import Path

DEFAULTS = {
    "library_root": "",          # 媒体库根目录，空则首次运行时询问
    "download_root": "",         # 下载暂存目录
    "subtitle_priority": True,   # 中字优先
    "max_size_gb": 0,            # 体积上限，0 = 不限
    "preferred_quality": "1080p",
    "concurrency": 3,
    "sources_enabled": ["knaben"],
    "proxy": "",                 # 用户显式配置，空 = 直连
    "terms_accepted": False,
}

def state_dir() -> Path:
    env = os.environ.get("MEDIA_BUTLER_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("APPDATA", str(Path.home()))
        return Path(base) / "media-butler"
    return Path.home() / ".media-butler"

def _cfg_path() -> Path:
    return state_dir() / "config.json"

def load() -> dict:
    cfg = dict(DEFAULTS)
    p = _cfg_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass  # 配置损坏时回落默认值，不阻断
    return cfg

def save(cfg: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    # 原子写：临时文件 + os.replace，避免写坏用户配置
    fd, tmp = tempfile.mkstemp(dir=str(d), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _cfg_path())
    except BaseException:
        os.unlink(tmp)
        raise
    try:
        os.chmod(_cfg_path(), 0o600)  # 可能含代理凭据
    except OSError:
        pass
