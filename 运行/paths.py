"""统一的“程序所在目录”定位逻辑，脚本直接运行和打包成 exe 后都能正确定位。"""

import os
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
