"""解释器对外报出的错误类型。

spec §10 说验收测试不会触发错误，这里的严格检查只是为了鲁棒性：
出错时给出一句人能看懂的提示（带上符号名/表达式），而不是把 Python 的
原始异常堆栈直接抛给使用者。
"""

from __future__ import annotations


class SchemeError(Exception):
    """语法错误、未绑定变量、参数个数/类型不对等，统一用这个异常表示。"""
