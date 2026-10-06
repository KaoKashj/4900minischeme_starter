"""求值器：表达式 -> 值（解释器的心脏）。

两个互相递归的函数把整门语言串起来：

- :func:`evaluate` 求值一个表达式：符号去环境里查；数字/布尔/字符串/空表原样
  返回；点对则先看是不是特殊形式（spec §4，它们自己决定求值顺序），否则按
  "先求值操作符和全部实参，再调用"的函数调用处理。
- :func:`apply_procedure` 调用一个过程：内置过程直接调用；用户函数（闭包）新建
  一层环境把实参绑到参数名上（外层指向**定义时**的环境），再回到
  :func:`evaluate` 求值函数体。

``evaluate`` 遇到函数调用就调 ``apply_procedure``，后者执行函数体又调回
``evaluate``——这个循环就是解释器的全部秘密（spec §7 的递归展开过程）。
"""

from __future__ import annotations

from typing import Any, Callable

from environment import Environment
from errors import SchemeError
from printer import to_write
from values import Builtin, Closure, Pair, Symbol, to_list

#: 特殊形式名 -> 处理函数 ``handler(参数链, 环境)``，在文件末尾统一登记。
_SPECIAL_FORMS: dict[str, Callable[[Any, Environment], Any]] = {}

#: 参数个数上界，表示"不限"。
_ANY = 10 ** 9


def evaluate(expr: Any, env: Environment) -> Any:
    """求值一个表达式，返回它的值（``None`` 表示"无值"，调用方不打印）。"""
    if isinstance(expr, Symbol):
        # 变量引用：去环境里查
        return env.lookup(expr.name)
    if isinstance(expr, Pair):
        # 括号表达式：特殊形式 or 函数调用
        return _evaluate_pair(expr, env)
    # 数字、布尔、字符串、空表等基本值自求值
    return expr


def apply_procedure(proc: Any, args: list) -> Any:
    """调用一个过程（内置过程或闭包）。"""
    if isinstance(proc, Builtin):
        return _call_builtin(proc, args)
    if isinstance(proc, Closure):
        return _call_closure(proc, args)
    raise SchemeError("%s 不是过程，无法调用" % (to_write(proc),))


def _evaluate_pair(expr: Pair, env: Environment) -> Any:
    """求值一个括号表达式。"""
    operator = expr.car

    # 操作符位置是名字，且这个名字是特殊形式 -> 交给它自己的规则处理
    if isinstance(operator, Symbol):
        handler = _SPECIAL_FORMS.get(operator.name)
        if handler is not None:
            return handler(expr.cdr, env)

    # 普通函数调用：应用序——先求值操作符，再由内向外求值全部实参
    proc = evaluate(operator, env)
    arguments = [evaluate(arg, env) for arg in to_list(expr.cdr, context="函数调用的参数")]
    return apply_procedure(proc, arguments)


def _call_builtin(proc: Builtin, args: list) -> Any:
    """调用内置过程，并把 Python 异常翻译成好读的 Scheme 错误。"""
    try:
        return proc.func(*args)
    except SchemeError:
        raise
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise SchemeError("%s: %s" % (proc.name, exc)) from exc


def _call_closure(proc: Closure, args: list) -> Any:
    """调用闭包：新环境绑参数，外层指向函数定义时的环境（词法作用域）。"""
    if len(args) != len(proc.params):
        raise SchemeError(
            "%s: 需要 %d 个参数，得到 %d 个"
            % (proc.name or "lambda", len(proc.params), len(args))
        )
    frame = Environment(parent=proc.env)
    for param, value in zip(proc.params, args):
        frame.define(param.name, value)
    return _evaluate_sequence(proc.body, frame)


def _evaluate_sequence(expressions: list, env: Environment) -> Any:
    """按 ``begin`` 语义依次求值，返回最后一个表达式的值。"""
    result: Any = None
    for expression in expressions:
        result = evaluate(expression, env)
    return result


def _special_form(name: str) -> Callable:
    """把下面定义的函数登记为特殊形式。"""

    def register(func: Callable) -> Callable:
        _SPECIAL_FORMS[name] = func
        return func

    return register


def _form_args(name: str, args: Any, low: int, high: int | None = None) -> list:
    """拆开特殊形式的参数链，并检查参数个数。"""
    items = to_list(args, context="%s 的参数" % (name,))
    highest = low if high is None else high
    if not low <= len(items) <= highest:
        expected = str(low) if low == highest else "%d~%d" % (low, highest)
        raise SchemeError("%s: 需要 %s 个参数，得到 %d 个" % (name, expected, len(items)))
    return items


def _check_params(params: list, form: str) -> None:
    """参数表里每一项都必须是符号（本语言不支持可变参数 lambda，spec §10）。"""
    for param in params:
        if not isinstance(param, Symbol):
            raise SchemeError("%s: 参数名必须是符号，得到 %s" % (form, to_write(param)))


@_special_form("quote")
def _eval_quote(args: Any, env: Environment) -> Any:
    """``(quote 数据)`` / ``'数据``：原样返回，不求值（spec §4.1）。"""
    return _form_args("quote", args, 1)[0]


@_special_form("if")
def _eval_if(args: Any, env: Environment) -> Any:
    """``(if 测试 真分支 [假分支])``：只求值其中一个分支（spec §4.2）。"""
    items = _form_args("if", args, 2, 3)
    if evaluate(items[0], env) is not False:
        return evaluate(items[1], env)
    if len(items) == 3:
        return evaluate(items[2], env)
    return None


@_special_form("cond")
def _eval_cond(args: Any, env: Environment) -> Any:
    """``(cond (测试 表达式...) ...)``：从上到下挑第一个成立的分支（spec §4.3）。"""
    for clause in to_list(args, context="cond 的子句"):
        parts = to_list(clause, context="cond 子句")
        if not parts:
            raise SchemeError("cond: 子句不能是空的 ()")
        test = parts[0]
        # else 兜底：直接按 begin 语义求值它后面的表达式
        if isinstance(test, Symbol) and test.name == "else":
            return _evaluate_sequence(parts[1:], env)
        value = evaluate(test, env)
        if value is not False:
            # 子句里没有表达式时，返回测试值本身
            if len(parts) == 1:
                return value
            return _evaluate_sequence(parts[1:], env)
    return None


@_special_form("and")
def _eval_and(args: Any, env: Environment) -> Any:
    """``(and e1 e2 ...)``：遇到第一个 ``#f`` 立刻返回（短路，spec §4.4）。"""
    result: Any = True
    for expression in to_list(args, context="and 的参数"):
        result = evaluate(expression, env)
        if result is False:
            return False
    return result  # (and) -> #t；否则是最后一个表达式的值


@_special_form("or")
def _eval_or(args: Any, env: Environment) -> Any:
    """``(or e1 e2 ...)``：遇到第一个不为 ``#f`` 的值立刻返回（短路，spec §4.4）。"""
    for expression in to_list(args, context="or 的参数"):
        result = evaluate(expression, env)
        if result is not False:
            return result
    return False  # (or) -> #f


@_special_form("define")
def _eval_define(args: Any, env: Environment) -> Any:
    """``(define 名 表达式)`` 或 ``(define (名 参数...) 体...)``（spec §4.5）。"""
    items = to_list(args, context="define 的参数")
    if not items:
        raise SchemeError("define: 至少需要 2 个参数，得到 0 个")
    target = items[0]

    if isinstance(target, Symbol):
        # (define 名 表达式)：先求值右边，再在当前环境绑定；结果是符号名（顶层会打印）
        _form_args("define", args, 2)
        env.define(target.name, evaluate(items[1], env))
        return target

    if isinstance(target, Pair):
        # (define (函数名 参数...) 体...) 等价于 (define 函数名 (lambda (参数...) 体...))
        if len(items) < 2:
            raise SchemeError("define: 函数定义至少要有函数体")
        name = target.car
        if not isinstance(name, Symbol):
            raise SchemeError("define: 函数名必须是符号")
        params = to_list(target.cdr, context="define 的参数表")
        _check_params(params, "define")
        env.define(name.name, Closure(params, items[1:], env, name.name))
        return name

    raise SchemeError("define: 第一项必须是符号，或 (名字 参数...) 形式")


@_special_form("lambda")
def _eval_lambda(args: Any, env: Environment) -> Any:
    """``(lambda (参数...) 体...)``：制造闭包，函数体此时不求值（spec §4.6）。"""
    items = _form_args("lambda", args, 2, _ANY)
    params = to_list(items[0], context="lambda 的参数表")
    _check_params(params, "lambda")
    return Closure(params, items[1:], env)


@_special_form("let")
def _eval_let(args: Any, env: Environment) -> Any:
    """``(let ((名 表达式)...) 体...)``：绑定在外层环境求值（并行绑定，spec §4.7）。"""
    items = _form_args("let", args, 2, _ANY)
    bindings = to_list(items[0], context="let 的绑定表")

    evaluated = []
    for binding in bindings:
        parts = to_list(binding, context="let 的绑定")
        if len(parts) != 2 or not isinstance(parts[0], Symbol):
            raise SchemeError("let: 绑定必须写成 (名字 表达式)")
        # 关键：全部绑定都在外层环境求值，互相看不见（并行绑定）
        evaluated.append((parts[0].name, evaluate(parts[1], env)))

    frame = Environment(parent=env)
    for name, value in evaluated:
        frame.define(name, value)
    return _evaluate_sequence(items[1:], frame)


@_special_form("begin")
def _eval_begin(args: Any, env: Environment) -> Any:
    """``(begin e1 e2 ...)``：从左到右求值，返回最后一个（spec §4.8）。"""
    return _evaluate_sequence(to_list(args, context="begin 的参数"), env)
