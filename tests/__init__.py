"""测试包：把 scripts/ 加入 import 路径，使根目录一条命令即可跑全部测试。

统一命令（仓库根目录执行）：
    python3 -m unittest discover -s tests -v
"""
import os, sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
