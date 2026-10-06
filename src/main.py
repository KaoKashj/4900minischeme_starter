#!/usr/bin/env python3
"""mini-Scheme 解释器入口（spec §2 的 CLI 约定）。

用法::

    python3 src/main.py file1.scm [file2.scm ...]   # 有参数：按顺序读文件
    python3 src/main.py                             # 无参数：从标准输入读

约定：

- 按顺序求值每一个顶层表达式，**每个求值结果独占一行**打印；
- 结果是"无值"（``display`` / ``newline`` 的返回值）时不打印；
- 多个文件共享同一个全局环境（后一个文件看得见前一个文件的 ``define``）；
- 每个测试用例在独立进程里运行，初始环境只有 spec §5 的内置过程。
"""

from __future__ import annotations

import os
import sys
from typing import Any

# 允许 `python3 src/main.py` 这种直接运行方式：把本文件所在目录（src/）
# 放进模块搜索路径，这样下面的同级模块才 import 得到。
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 本语言不保证尾调用优化（spec §10），方案里的递归（如 (sum-to 100)）是普通
# 递归：Scheme 每层调用大约要占十几个 Python 栈帧，Python 默认的 1000 层不够用。
# 这里把上限调高，避免"解释器本身"先于用户程序撞到递归墙。
if sys.getrecursionlimit() < 100000:
    sys.setrecursionlimit(100000)

from errors import SchemeError  # noqa: E402  (必须在调整 sys.path 之后导入)
from evaluator import evaluate  # noqa: E402
from parser import parse  # noqa: E402
from printer import to_write  # noqa: E402
from primitives import build_global_env  # noqa: E402


def run_source(text: str, env: Any, out: Any) -> None:
    """求值一段程序：每个顶层结果独占一行写入 ``out``，无值不打印。"""
    for expression in parse(text):
        value = evaluate(expression, env)
        if value is not None:
            out.write(to_write(value))
            out.write("\n")


def main(argv: list | None = None) -> int:
    """命令行入口，返回进程退出码（0 表示成功）。"""
    paths = list(sys.argv[1:] if argv is None else argv)
    env = build_global_env()

    try:
        if paths:
            for path in paths:
                with open(path, "r", encoding="utf-8") as handle:
                    run_source(handle.read(), env, sys.stdout)
        else:
            run_source(sys.stdin.read(), env, sys.stdout)
    except OSError as exc:
        print("无法读取文件: %s" % (exc,), file=sys.stderr)
        return 1
    except SchemeError as exc:
        sys.stdout.flush()
        print("错误: %s" % (exc,), file=sys.stderr)
        return 1

    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
