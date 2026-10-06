"""内置过程（标准函数库，spec §5）+ 初始全局环境。

内置过程与特殊形式的区别：**参数先全部求值，再调用**（应用序）。这里的每个
函数都是普通 Python 函数，接收已经求好值的参数，返回一个 Scheme 值。

命名约定：``_name_with_underscores`` 是内部实现，最后统一由
:func:`build_global_env` 注册进全局环境。
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from environment import Environment
from errors import SchemeError
from printer import to_display, to_write
from values import NIL, Builtin, Closure, Pair, Symbol, from_list, is_proper_list, to_list


# --------------------------------------------------------------------------- #
# 参数检查小工具
# --------------------------------------------------------------------------- #
def _number(value: Any, who: str) -> Any:
    """要求一个数字（Python 里 ``True`` 也是 ``int``，必须排除）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemeError("%s: 需要数字，得到 %s" % (who, to_write(value)))
    return value


def _integer(value: Any, who: str) -> int:
    """要求一个整数。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemeError("%s: 需要整数，得到 %s" % (who, to_write(value)))
    return value


def _pair(value: Any, who: str) -> Pair:
    """要求一个非空点对。"""
    if not isinstance(value, Pair):
        raise SchemeError("%s: 需要非空点对，得到 %s" % (who, to_write(value)))
    return value


def _truncating_divide(left: Any, right: Any) -> Any:
    """整数商，**负数向零截断**（spec §5）：``(/ 7 2)`` -> 3，``(/ -7 2)`` -> -3。

    有浮点参与时按普通除法。用 ``abs`` 手算而不是 ``int(left / right)``，
    是为了避免大整数转浮点丢精度。
    """
    if isinstance(left, int) and isinstance(right, int):
        magnitude = abs(left) // abs(right)
        return magnitude if (left >= 0) == (right >= 0) else -magnitude
    return left / right


# --------------------------------------------------------------------------- #
# 算术（spec §5）
# --------------------------------------------------------------------------- #
def _add(*args: Any) -> Any:
    """``+`` 可变参数求和：``(+ 1 2 3)`` -> 6，``(+)`` -> 0。"""
    total = 0
    for arg in args:
        total += _number(arg, "+")
    return total


def _subtract(*args: Any) -> Any:
    """``-`` 可变参数求差；单参数取反：``(- 5)`` -> -5。"""
    if not args:
        raise SchemeError("-: 至少需要 1 个参数")
    if len(args) == 1:
        return -_number(args[0], "-")
    result = _number(args[0], "-")
    for arg in args[1:]:
        result -= _number(arg, "-")
    return result


def _multiply(*args: Any) -> Any:
    """``*`` 可变参数求积：``(* 2 3 4)`` -> 24。"""
    result = 1
    for arg in args:
        result *= _number(arg, "*")
    return result


def _divide(*args: Any) -> Any:
    """``/`` 可变参数相除；单参数求倒数（浮点）：``(/ 2)`` -> 0.5。"""
    if not args:
        raise SchemeError("/: 至少需要 1 个参数")
    if len(args) == 1:
        value = _number(args[0], "/")
        if value == 0:
            raise SchemeError("/: 除以零")
        return 1 / value
    result = _number(args[0], "/")
    for arg in args[1:]:
        divisor = _number(arg, "/")
        if divisor == 0:
            raise SchemeError("/: 除以零")
        result = _truncating_divide(result, divisor)
    return result


def _modulo(left: Any, right: Any) -> int:
    """``modulo`` 取模，结果符号跟随除数（与 Python 的 ``%`` 一致）。"""
    left = _integer(left, "modulo")
    right = _integer(right, "modulo")
    if right == 0:
        raise SchemeError("modulo: 除以零")
    return left % right


def _quotient(left: Any, right: Any) -> Any:
    """``quotient`` 整除商，负数向零截断。"""
    left = _integer(left, "quotient")
    right = _integer(right, "quotient")
    if right == 0:
        raise SchemeError("quotient: 除以零")
    return _truncating_divide(left, right)


def _expt(base: Any, exponent: Any) -> Any:
    """``expt`` 乘方：``(expt 2 10)`` -> 1024。"""
    return _number(base, "expt") ** _number(exponent, "expt")


def _abs(value: Any) -> Any:
    """``abs`` 绝对值。"""
    return abs(_number(value, "abs"))


# --------------------------------------------------------------------------- #
# 比较与布尔（spec §5）
# --------------------------------------------------------------------------- #
def _compare_chain(args: tuple, who: str, ordered: bool) -> bool:
    """链式比较：相邻两两都成立才为真，例如 ``(< 2 3 4)`` -> True。"""
    if len(args) < 2:
        raise SchemeError("%s: 至少需要 2 个参数" % (who,))
    for left, right in zip(args, args[1:]):
        if not _compare_pair(left, right, who, ordered):
            return False
    return True


def _compare_pair(left: Any, right: Any, who: str, ordered: bool) -> bool:
    """比较一对值。``=`` 只看相等；``< > <= >=`` 看大小。"""
    if ordered:
        left_key, right_key = _order_key(left, who), _order_key(right, who)
        return _ORDER_OPERATORS[who](left_key, right_key)
    return _values_equal(left, right)


def _order_key(value: Any, who: str) -> tuple:
    """把待比较的值化成可比较的键：数字比数值，符号比名字（spec §5）。

    用 ``(类别, 值)`` 这样的元组，既支持两种类型，又避免数字与字符串直接比较。
    """
    if isinstance(value, bool):
        raise SchemeError("%s: 不能比较布尔值" % (who,))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, Symbol):
        return (1, value.name)
    raise SchemeError("%s: 只能比较数字或符号，得到 %s" % (who, to_write(value)))


_ORDER_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
}


def _values_equal(left: Any, right: Any) -> bool:
    """``=`` 的判断：数字按数值比较，符号按名字比较。"""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, Symbol) and isinstance(right, Symbol):
        return left.name == right.name
    return left is right


def _not(value: Any) -> bool:
    """``not`` 取反：只有 ``#f`` 是假，``(not 0)`` -> ``#f``。"""
    return value is False


# --------------------------------------------------------------------------- #
# 列表与点对（spec §5、§6）
# --------------------------------------------------------------------------- #
def _cons(head: Any, tail: Any) -> Pair:
    """``cons`` 构造点对：``(cons 1 '(2 3))`` -> ``(1 2 3)``。"""
    return Pair(head, tail)


def _car(value: Any) -> Any:
    """``car`` 取点对的第一项。"""
    return _pair(value, "car").car


def _cdr(value: Any) -> Any:
    """``cdr`` 取点对的第二项：``(cdr '(1 2 3))`` -> ``(2 3)``。"""
    return _pair(value, "cdr").cdr


def _list(*args: Any) -> Any:
    """``list`` 打包成列表。"""
    return from_list(args)


def _length(value: Any) -> int:
    """``length`` 列表长度（只接受真列表）。"""
    return len(to_list(value, context="length 的参数"))


def _append(*args: Any) -> Any:
    """``append`` 拼接若干列表；最后一个参数可以是任意值（点对尾巴）。

    ``(append '(1 2) '(3 4))`` -> ``(1 2 3 4)``
    """
    if not args:
        return NIL
    result = args[-1]
    for source in reversed(args[:-1]):
        for item in reversed(to_list(source, context="append 的参数")):
            result = Pair(item, result)
    return result


# --------------------------------------------------------------------------- #
# 谓词（spec §5）
# --------------------------------------------------------------------------- #
def _is_number(value: Any) -> bool:
    """``number?``。"""
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _is_boolean(value: Any) -> bool:
    """``boolean?``。"""
    return isinstance(value, bool)


def _is_symbol(value: Any) -> bool:
    """``symbol?``。"""
    return isinstance(value, Symbol)


def _is_string(value: Any) -> bool:
    """``string?``。"""
    return isinstance(value, str)


def _is_procedure(value: Any) -> bool:
    """``procedure?``：内置过程和用户函数都算。"""
    return isinstance(value, (Builtin, Closure))


def _is_null(value: Any) -> bool:
    """``null?`` 是否空表。"""
    return value is NIL


def _is_pair(value: Any) -> bool:
    """``pair?`` 是否非空点对。"""
    return isinstance(value, Pair)


def _is_list(value: Any) -> bool:
    """``list?`` 是否真列表：``(list? (cons 1 2))`` -> ``#f``。"""
    return is_proper_list(value)


def _is_zero(value: Any) -> bool:
    """``zero?``。"""
    return _number(value, "zero?") == 0


def _is_even(value: Any) -> bool:
    """``even?``。"""
    return _integer(value, "even?") % 2 == 0


def _is_odd(value: Any) -> bool:
    """``odd?``。"""
    return _integer(value, "odd?") % 2 != 0


def _eq(left: Any, right: Any) -> bool:
    """``eq?``：符号/数字/布尔/字符串按值比较，复合数据按**同一性**。

    ``(eq? '() '())`` -> ``#t``（空表是同一个对象）；
    ``(eq? '(1) '(1))`` -> ``#f``（两次引用造出的是不同的点对）。
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, Symbol) and isinstance(right, Symbol):
        return left.name == right.name
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    return left is right


def _equal(left: Any, right: Any) -> bool:
    """``equal?``：结构相等，逐层比较。

    先比类型再比值，所以 ``(equal? #t 1)`` 与 ``(equal? 'a "a")`` 都是 ``#f``。
    """
    if isinstance(left, Symbol) or isinstance(right, Symbol):
        return isinstance(left, Symbol) and isinstance(right, Symbol) and left.name == right.name
    if isinstance(left, Pair) or isinstance(right, Pair):
        return (
            isinstance(left, Pair)
            and isinstance(right, Pair)
            and _equal(left.car, right.car)
            and _equal(left.cdr, right.cdr)
        )
    if left is NIL or right is NIL:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        # 整数与浮点不算结构相等（类型不同），符合 spec §11 的提示
        return type(left) is type(right) and left == right
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    return left is right


# --------------------------------------------------------------------------- #
# 输出（spec §5）
# --------------------------------------------------------------------------- #
def _display(value: Any) -> None:
    """``display`` 打印一个值（字符串不带引号），不换行。"""
    sys.stdout.write(to_display(value))
    return None


def _newline() -> None:
    """``newline`` 输出一个换行。"""
    sys.stdout.write("\n")
    return None


# --------------------------------------------------------------------------- #
# 初始全局环境
# --------------------------------------------------------------------------- #
_BUILTIN_FUNCTIONS: dict[str, Callable[..., Any]] = {
    # 算术
    "+": _add,
    "-": _subtract,
    "*": _multiply,
    "/": _divide,
    "modulo": _modulo,
    "quotient": _quotient,
    "expt": _expt,
    "abs": _abs,
    # 比较
    "=": lambda *args: _compare_chain(args, "=", ordered=False),
    "<": lambda *args: _compare_chain(args, "<", ordered=True),
    ">": lambda *args: _compare_chain(args, ">", ordered=True),
    "<=": lambda *args: _compare_chain(args, "<=", ordered=True),
    ">=": lambda *args: _compare_chain(args, ">=", ordered=True),
    # 布尔
    "not": _not,
    # 列表
    "cons": _cons,
    "car": _car,
    "cdr": _cdr,
    "list": _list,
    "length": _length,
    "append": _append,
    # 谓词
    "null?": _is_null,
    "pair?": _is_pair,
    "list?": _is_list,
    "number?": _is_number,
    "boolean?": _is_boolean,
    "symbol?": _is_symbol,
    "string?": _is_string,
    "procedure?": _is_procedure,
    "zero?": _is_zero,
    "even?": _is_even,
    "odd?": _is_odd,
    "eq?": _eq,
    "equal?": _equal,
    # 输出
    "display": _display,
    "newline": _newline,
}


def build_global_env() -> Environment:
    """造一个初始全局环境，里面装好 spec §5 的全部内置过程。

    每个测试用例在独立进程里、从空环境开始（spec §2）。
    """
    env = Environment()
    for name, func in _BUILTIN_FUNCTIONS.items():
        env.define(name, Builtin(name, func))
    return env
