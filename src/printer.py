"""打印：值 -> 文本（spec §8）。

同一份值有两种打印方式（对应 scheme 的 ``write`` 与 ``display``）：

- ``to_write``：``display``/``newline`` 之外场合使用的标准写法，字符串**带引号**，
  内部的换行/制表符打印成 ``\\n`` ``\\t`` 转义形式；
- ``to_display``：``display`` 使用，字符串**不带引号**，也不做转义。

| 值       | 打印                    |
|----------|-------------------------|
| 整数     | ``42``                  |
| 浮点     | ``0.5``                 |
| 布尔     | ``#t`` / ``#f``         |
| 符号     | ``foo``                 |
| 字符串   | ``"hello"`` / ``hello`` |
| 真列表   | ``(1 2 3)``             |
| 点对     | ``(1 . 2)``             |
| 空表     | ``()``                  |
| 过程     | ``#<procedure>``        |
"""

from __future__ import annotations

from typing import Any

from values import NIL, Builtin, Closure, Pair, Symbol

#: 字符串写出来时需要转义的字符。
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
}


def to_write(value: Any) -> str:
    """打印一个值（字符串带引号）。"""
    return _format(value, quoted=True)


def to_display(value: Any) -> str:
    """打印一个值（字符串不带引号，spec §5 的 ``display``）。"""
    return _format(value, quoted=False)


def _format(value: Any, quoted: bool) -> str:
    # 注意：bool 是 int 的子类，必须先判断。
    if value is True:
        return "#t"
    if value is False:
        return "#f"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return '"%s"' % (_escape(value),) if quoted else value
    if isinstance(value, Symbol):
        return value.name
    if value is NIL:
        return "()"
    if isinstance(value, Pair):
        return _format_pair(value, quoted)
    if isinstance(value, (Builtin, Closure)):
        return "#<procedure>"
    return str(value)


def _format_pair(pair: Pair, quoted: bool) -> str:
    """打印点对：真列表写成 ``(1 2 3)``，带点尾巴的写成 ``(1 . 2)``。"""
    parts = []
    node: Any = pair
    while isinstance(node, Pair):
        parts.append(_format(node.car, quoted))
        node = node.cdr
    if node is NIL:
        return "(" + " ".join(parts) + ")"
    return "(" + " ".join(parts) + " . " + _format(node, quoted) + ")"


def _escape(text: str) -> str:
    return "".join(_ESCAPES.get(char, char) for char in text)
