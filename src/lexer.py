"""词法分析：程序文本 -> 词（token）列表（spec §3）。

这一步只关心"程序由哪些零件拼成"，不关心零件的含义：

- ``;`` 到行尾是注释，直接丢掉；
- ``(`` ``)`` ``'`` 是单独的词；
- ``"..."`` 是字符串，内部支持 ``\\n \\t \\" \\\\`` 转义；
- 其余连续的非空白字符算一个"原子"，究竟是数字/布尔/符号留给语法分析判断。

每个词记录行号，报错时能指出问题在哪一行。
"""

from __future__ import annotations

from dataclasses import dataclass

from errors import SchemeError

# 词的种类
LPAREN = "LPAREN"
RPAREN = "RPAREN"
QUOTE = "QUOTE"
ATOM = "ATOM"  # 数字 / 布尔 / 符号，由语法分析进一步区分
STRING = "STRING"

#: 原子遇到这些字符就结束（空白、括号、引号、分隔符）。
_ATOM_DELIMITERS = " \t\r\n()'\";"
_WHITESPACE = " \t\r\n"


@dataclass(frozen=True)
class Token:
    """一个词：种类 + 词面 + 行号。"""

    kind: str
    text: str
    line: int


def tokenize(text: str) -> list[Token]:
    """把程序文本切成词列表。"""
    tokens: list[Token] = []
    index = 0
    line = 1
    length = len(text)

    while index < length:
        char = text[index]

        if char in _WHITESPACE:
            if char == "\n":
                line += 1
            index += 1
            continue

        # 注释：从 ; 到行尾
        if char == ";":
            index = _skip_to_end_of_line(text, index)
            continue

        if char == "(":
            tokens.append(Token(LPAREN, char, line))
            index += 1
            continue

        if char == ")":
            tokens.append(Token(RPAREN, char, line))
            index += 1
            continue

        if char == "'":
            tokens.append(Token(QUOTE, char, line))
            index += 1
            continue

        if char == '"':
            value, index, line = _read_string(text, index, line)
            tokens.append(Token(STRING, value, line))
            continue

        # 原子：一直读到下一个分隔符
        end = index
        while end < length and text[end] not in _ATOM_DELIMITERS:
            end += 1
        tokens.append(Token(ATOM, text[index:end], line))
        index = end

    return tokens


def _skip_to_end_of_line(text: str, index: int) -> int:
    """跳过 ``;`` 开始的注释，停在行尾的换行符上（换行由主循环处理）。"""
    while index < len(text) and text[index] != "\n":
        index += 1
    return index


def _read_string(text: str, index: int, line: int) -> tuple[str, int, int]:
    """读取一个字符串字面量，返回（内容, 新下标, 新行号）。"""
    start_line = line
    index += 1  # 跳过开头的 "
    chars: list[str] = []

    while index < len(text):
        char = text[index]

        if char == '"':
            return "".join(chars), index + 1, line

        if char == "\\":
            index += 1
            if index >= len(text):
                break
            escaped = text[index]
            if escaped == "n":
                chars.append("\n")
            elif escaped == "t":
                chars.append("\t")
            elif escaped == "r":
                chars.append("\r")
            elif escaped in ('"', "\\"):
                chars.append(escaped)
            else:
                # 未定义的转义：按字面保留（例如 "\d" 就是反斜杠 + d）
                chars.append("\\")
                chars.append(escaped)
            index += 1
            continue

        if char == "\n":
            line += 1
        chars.append(char)
        index += 1

    raise SchemeError("第 %d 行：字符串没有结尾的引号" % (start_line,))
