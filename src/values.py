"""mini-Scheme 的值（数据）表示。

解释器内部只用下面这几种 Python 对象承载 Scheme 的值：

| Scheme 值            | Python 表示                          |
|----------------------|--------------------------------------|
| 整数 / 浮点          | ``int`` / ``float``                  |
| 布尔 ``#t`` / ``#f`` | ``bool``                             |
| 字符串 ``"..."``     | ``str``                              |
| 符号 ``foo``         | :class:`Symbol`                      |
| 空表 ``()``          | :data:`NIL`（:class:`Nil` 的唯一实例）|
| 点对 / 列表          | :class:`Pair`（用点对链表示，spec §6）|
| 内置过程 ``car``     | :class:`Builtin`                     |
| 用户函数（闭包）     | :class:`Closure`                     |

两个刻意的设计选择：

1. **符号不继承 ``str``**。若继承，``(equal? 'a "a")`` 会因 Python 的
   ``==`` 而误判为相等（spec §11 专门点了这个坑）。
2. **空表用独立的 ``Nil`` 单例，而不是 ``None``**。因为 ``None`` 被保留
   表示"无值"——``display`` / ``newline`` 的结果不打印（spec §2）。

列表直接用点对链表示（``(1 2 3)`` 就是 ``(1 . (2 . (3 . ())))``），
这样 ``quote`` 拿到的数据与 ``cons`` 造出来的数据是同一种东西，
不会出现"引用数据没转成点对链"导致打印成 ``(1 2 . 3)`` 的问题（spec §6）。
"""

from __future__ import annotations

from typing import Any, Iterable

from errors import SchemeError


class Symbol:
    """符号：表示"名字"，可能是变量也可能是操作符（spec §3）。

    按名字比较与哈希，所以 ``(= 'a 'a)`` 这类判断成立；但它**不是** ``str``。
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Symbol) and other.name == self.name

    def __hash__(self) -> int:
        return hash((Symbol, self.name))

    def __repr__(self) -> str:
        return "Symbol(%r)" % (self.name,)


class Nil:
    """空表 ``()``；全局只用一个实例 :data:`NIL`，便于 ``eq?`` 按同一性判断。"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "()"


#: 空表的唯一实例。所有"列表结束"的位置都指向它。
NIL = Nil()


class Pair:
    """点对 ``(car . cdr)``——列表就是由点对串起来的链（spec §6）。"""

    __slots__ = ("car", "cdr")

    def __init__(self, car: Any, cdr: Any) -> None:
        self.car = car
        self.cdr = cdr

    def __repr__(self) -> str:
        return "Pair(%r, %r)" % (self.car, self.cdr)


class Builtin:
    """内置过程：一个名字加一个 Python 可调用对象（spec §5）。"""

    __slots__ = ("name", "func")

    def __init__(self, name: str, func: Any) -> None:
        self.name = name
        self.func = func

    def __repr__(self) -> str:
        return "#<procedure %s>" % (self.name,)


class Closure:
    """用户定义的函数（闭包）：参数名、函数体、**定义时**所在的环境（spec §9）。

    记住定义时的环境是词法作用域的关键，也是 008/009 两组用例的核心。
    """

    __slots__ = ("params", "body", "env", "name")

    def __init__(self, params: list, body: list, env: Any, name: str | None = None) -> None:
        self.params = params
        self.body = body
        self.env = env
        self.name = name

    def __repr__(self) -> str:
        return "#<procedure %s>" % (self.name or "lambda",)


def from_list(items: Iterable[Any]) -> Any:
    """把 Python 列表拼成点对链：``[1, 2]`` -> ``(1 . (2 . ()))``。

    空列表得到 :data:`NIL`，所以 ``(list)`` 与 ``'()`` 的结果一致。
    """
    result: Any = NIL
    for item in reversed(list(items)):
        result = Pair(item, result)
    return result


def to_list(value: Any, *, context: str = "列表") -> list:
    """把点对链拆回 Python 列表；遇到非真列表（点对尾巴）时报错。"""
    items: list = []
    node = value
    while isinstance(node, Pair):
        items.append(node.car)
        node = node.cdr
    if node is not NIL:
        raise SchemeError("%s 必须是真列表，但它的结尾是 %r" % (context, node))
    return items


def is_proper_list(value: Any) -> bool:
    """是否为真列表：空表，或若干点对串起来、最后一节是空表。"""
    node = value
    while isinstance(node, Pair):
        node = node.cdr
    return node is NIL


def is_pair(value: Any) -> bool:
    """是否为非空点对（spec §5 的 ``pair?``）：

    ``(pair? '(1 2))`` -> True，``(pair? '())`` -> False。
    """
    return isinstance(value, Pair)
