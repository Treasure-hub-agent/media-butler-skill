#!/usr/bin/env python3
"""media-butler CLI 入口。

影视片源检索、下载与本地库分类管理。全部确定性执行在此完成；
LLM 只负责片名理解与候选择优。

当前为任务 1 的最小入口骨架：能运行、能显示帮助、能分派子命令；
各子命令的完整实现在后续任务中补齐。
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config  # noqa: E402

COMMANDS = ("parse", "meta", "search", "grab", "status",
            "subs", "ingest", "index", "doctor", "config")

HELP = {
    "parse": "解析资源名",
    "meta": "查询元数据与检索名",
    "search": "多源检索（中字优先）",
    "grab": "加入下载（异步）",
    "status": "查看下载进度",
    "subs": "获取中文字幕",
    "ingest": "归档入库",
    "index": "媒体库清单",
    "doctor": "只读巡检",
    "config": "配置读写",
}

def cmd_config(args):
    """配置读写：无 --set 时输出当前配置（含状态目录）。"""
    cfg = config.load()
    if args.set:
        for pair in args.set:
            k, _, v = pair.partition("=")
            if v.lower() in ("true", "false"):
                cfg[k] = v.lower() == "true"
            elif v.isdigit():
                cfg[k] = int(v)
            else:
                cfg[k] = v
        config.save(cfg)
    cfg["state_dir"] = str(config.state_dir())
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0

def _not_implemented(name):
    def fn(args):
        print(json.dumps({"status": "not-implemented", "command": name},
                         ensure_ascii=False))
        return 2
    return fn

def build_parser():
    p = argparse.ArgumentParser(
        prog="media-butler",
        description="影视片源检索、下载与本地库分类管理")
    p.add_argument("--version", action="version", version="media-butler 0.1.0")
    sub = p.add_subparsers(dest="cmd")

    for name in COMMANDS:
        s = sub.add_parser(name, help=HELP[name])
        if name == "config":
            s.add_argument("--set", action="append", help="k=v")
        else:
            s.add_argument("args", nargs="*")
        s.set_defaults(fn=cmd_config if name == "config" else _not_implemented(name))

    return p

def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.print_help()
        return 1
    return args.fn(args)

if __name__ == "__main__":
    sys.exit(main())
