"""语法分析：词列表 -> 表达式（spec §3、§4.1、§6）。

表达式直接用点对链表示，所以"程序文本"和"被引用的数据"是同一种结构：

    (+ 1 2)      ->  Pair(Symbol('+'), Pair(1, Pair(2, NIL)))
    '(1 2 3)     ->  Pair(Symbol('quote'), Pair(<上面的链>, NIL))
    'x           ->  Pair(Symbol('quote'), Pair(Symbol('x'), NIL))

这样 ``quote`` 只需要原样返回它收到的那一节，得到的就已经是点对链了。

原子的判定顺序：``#t`` / ``#f`` -> 整数 -> 浮点 -> 符号。判定用正则做
严格匹配，避免 ``int("1_0")`` 这类 Python 特有的宽松解析混进来。
"""

from __future__ import annotations

import re
from typing import Any

from errors import SchemeError
from lexer import ATOM, LPAREN, QUOTE, RPAREN, STRING, Token, tokenize
from values import NIL, Pair, Symbol, from_list

_INTEGER_RE = re.compile(r"[+-]?[0-9]+\Z")
_FLOAT_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def parse(text: str) -> list:
    """把一段程序文本解析成顶层表达式列表。"""
    tokens = tokenize(text)
    expressions: list = []
    index = 0
    while index < len(tokens):
        expression, index = _parse_datum(tokens, index)
        expressions.append(expression)
    return expressions


def _parse_datum(tokens: list[Token], index: int) -> tuple[Any, int]:
    """从 tokens[index] 开始读一个数据（原子，或括号里的若干数据）。"""
    token = tokens[index]

    if token.kind == LPAREN:
        return _parse_list(tokens, index)

    if token.kind == RPAREN:
        raise SchemeError("第 %d 行：多出来的右括号 ')'" % (token.line,))

    if token.kind == QUOTE:
        if index + 1 >= len(tokens):
            raise SchemeError("第 %d 行：' 后面缺少数据" % (token.line,))
        quoted, index = _parse_datum(tokens, index + 1)
        # '数据 就是 (quote 数据) 的简写
        return Pair(Symbol("quote"), Pair(quoted, NIL)), index

    if token.kind == ATOM:
        return _atom_value(token), index + 1

    if token.kind == STRING:
        return token.text, index + 1

    raise SchemeError("第 %d 行：无法识别的词 %r" % (token.line, token.text))


def _parse_list(tokens: list[Token], index: int) -> tuple[Any, int]:
    """读一个括号表达式，直到配对的右括号；返回点对链。"""
    items: list = []
    index += 1  # 跳过 (

    while True:
        if index >= len(tokens):
            raise SchemeError("括号没有闭合：缺少 ')'")
        if tokens[index].kind == RPAREN:
            return from_list(items), index + 1
        item, index = _parse_datum(tokens, index)
        items.append(item)


def _atom_value(token: Token) -> Any:
    """把一个原子词翻译成它代表的值：布尔 / 数字 / 符号。"""
    text = token.text

    if text == "#t":
        return True
    if text == "#f":
        return False
    if _INTEGER_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return Symbol(text)
