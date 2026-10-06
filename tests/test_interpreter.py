"""解释器自测（只用标准库，运行方式：``python3 tests/test_interpreter.py``）。

评分器 ``autograder.pyz`` 是验收工具，这里补一层**开发用**的回归测试：
每个特性都写成一个小案例，挂了能立刻看出是哪一步（词法/语法/求值/打印）出的问题。
所有期望值都能在 ``spec.md`` 与 ``example/`` 里找到依据。评分器另有隐藏用例，
通过这里不等于满分。
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

# 让测试能 import 到 src/ 里的模块（与 main.py 的做法一致）
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_DIR, "src"))

import main as interpreter  # noqa: E402
from errors import SchemeError  # noqa: E402
from primitives import build_global_env  # noqa: E402


def run(program: str) -> str:
    """在一份全新的全局环境里跑一段程序，返回它输出的全部文本。

    用新环境是为了让每个案例互不影响；顶层结果与 ``display`` 的输出都会被捕获。
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        interpreter.run_source(program, build_global_env(), sys.stdout)
    return buffer.getvalue()


def run_lines(program: str) -> list:
    """同上，但按行切开，便于逐行比对。"""
    text = run(program)
    return text.splitlines()


class ArithmeticTest(unittest.TestCase):
    """算术：可变参数、整数商、取模、乘方（spec §5）。"""

    def test_variadic_arithmetic(self):
        self.assertEqual(run_lines("(+ 1 2 3)\n(- 10 4 1)\n(* 2 3 4)"), ["6", "5", "24"])

    def test_identity_elements(self):
        # (+) -> 0，(*) -> 1，这是"可变参数"的自然起点
        self.assertEqual(run_lines("(+)\n(*)"), ["0", "1"])

    def test_negative_division_truncates_toward_zero(self):
        self.assertEqual(run_lines("(/ 7 2)\n(/ -7 2)\n(quotient 17 5)\n(quotient -7 2)"),
                         ["3", "-3", "3", "-3"])

    def test_single_argument_division_is_reciprocal(self):
        self.assertEqual(run_lines("(/ 2)"), ["0.5"])

    def test_negation_abs_modulo_expt(self):
        self.assertEqual(run_lines("(- 5)\n(abs (- 5 9))\n(modulo 17 5)\n(expt 2 10)"),
                         ["-5", "4", "2", "1024"])


class ComparisonTest(unittest.TestCase):
    """比较：链式比较，数字与符号（spec §5）。"""

    def test_chained_comparison(self):
        self.assertEqual(run_lines("(< 2 3 4)\n(< 2 4 3)\n(>= 6 5)\n(<= 4 4)"),
                         ["#t", "#f", "#t", "#t"])

    def test_equality_of_symbols_and_numbers(self):
        self.assertEqual(run_lines("(= 1 1)\n(= 'a 'a)\n(= 1 2)"), ["#t", "#t", "#f"])


class BooleanTest(unittest.TestCase):
    """布尔：只有 #f 是假，and/or 短路（spec §4.4、§9）。"""

    def test_only_false_is_false(self):
        self.assertEqual(run_lines("(not #f)\n(not 0)\n(not '())\n(if 0 'yes 'no)"),
                         ["#t", "#f", "#f", "yes"])

    def test_short_circuit_avoids_error(self):
        # 若没短路，(/ 1 0) 会让整个程序报错
        self.assertEqual(run_lines("(and #f (/ 1 0))\n(or #t (/ 1 0))"), ["#f", "#t"])

    def test_empty_and_or(self):
        self.assertEqual(run_lines("(and)\n(or)"), ["#t", "#f"])

    def test_and_or_return_values(self):
        self.assertEqual(run_lines("(and 1 2)\n(or #f 3)"), ["2", "3"])


class ControlFlowTest(unittest.TestCase):
    """if / cond / quote（spec §4.1~§4.3）。"""

    def test_if(self):
        self.assertEqual(run_lines("(if (> 3 2) 'yes 'no)\n(if #f 'bad 'good)"),
                         ["yes", "good"])

    def test_if_without_else_prints_nothing(self):
        self.assertEqual(run("(if #f 1)"), "")

    def test_cond(self):
        program = """
        (cond ((= 1 2) 'a) ((= 2 2) 'b) (else 'c))
        (cond (else 'd))
        (cond ((> 2 3)) (else 42))
        (cond ((> 2 3) 'x))
        """
        self.assertEqual(run_lines(program), ["b", "d", "42"])

    def test_quote(self):
        self.assertEqual(run_lines("'x\n'(1 2 3)\n'()\n'(1 (2 3) 4)"),
                         ["x", "(1 2 3)", "()", "(1 (2 3) 4)"])

    def test_quote_does_not_evaluate(self):
        # 未定义的符号被引用时不报错
        self.assertEqual(run_lines("'(undefined-symbol)"), ["(undefined-symbol)"])


class FunctionTest(unittest.TestCase):
    """define / lambda / 递归 / 闭包（spec §4.5、§4.6、§7、§9）。"""

    def test_define_prints_name(self):
        self.assertEqual(run_lines("(define pi 3)\n(+ pi 1)"), ["pi", "4"])

    def test_function_shorthand_and_lambda(self):
        program = """
        (define square (lambda (x) (* x x)))
        (square 7)
        (define (cube x) (* x x x))
        (cube 3)
        ((lambda (x) (* x 2)) 5)
        """
        self.assertEqual(run_lines(program), ["square", "49", "cube", "27", "10"])

    def test_recursion(self):
        program = """
        (define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
        (fact 10)
        (define (sum-to n) (if (= n 0) 0 (+ n (sum-to (- n 1)))))
        (sum-to 100)
        """
        # 100 层递归需要解释器自己扛住 Python 的递归深度（见 main.py 的说明）
        self.assertEqual(run_lines(program), ["fact", "3628800", "sum-to", "5050"])

    def test_closure_remembers_definition_environment(self):
        program = """
        (define (make-adder n) (lambda (x) (+ x n)))
        (define add5 (make-adder 5))
        (add5 10)
        ((make-adder 100) 7)
        """
        self.assertEqual(run_lines(program), ["make-adder", "add5", "15", "107"])

    def test_higher_order_with_user_defined_map_filter(self):
        program = """
        (define (map f xs)
          (if (null? xs) '() (cons (f (car xs)) (map f (cdr xs)))))
        (map (lambda (x) (* x x)) '(1 2 3 4))
        """
        self.assertEqual(run_lines(program), ["map", "(1 4 9 16)"])


class BindingTest(unittest.TestCase):
    """let 是并行绑定；begin 顺序执行（spec §4.7、§4.8）。"""

    def test_let(self):
        self.assertEqual(run_lines("(let ((x 3) (y 4)) (+ x y))"), ["7"])

    def test_let_bindings_are_parallel(self):
        # 两个绑定都只看外层环境：x 在绑定表达式里还不可见
        self.assertEqual(
            run_lines("(define x 10)\n(let ((x 1) (y x)) y)"), ["x", "10"])

    def test_duplicate_binding_keeps_last(self):
        self.assertEqual(run_lines("(let ((x 1) (x 2)) x)"), ["2"])

    def test_nested_let(self):
        self.assertEqual(run_lines("(let ((a 1)) (let ((b (+ a 1))) (* a b)))"), ["2"])

    def test_begin(self):
        self.assertEqual(run_lines("(begin (define z 1) (+ z 41))"), ["42"])


class ListTest(unittest.TestCase):
    """列表与点对（spec §5、§6）。"""

    def test_basic_list_operations(self):
        program = """
        (car '(1 2 3))
        (cdr '(1 2 3))
        (cons 1 '(2 3))
        (cons 1 2)
        (list 1 2 3)
        (length '(a b c d))
        (append '(1 2) '(3 4))
        """
        self.assertEqual(run_lines(program),
                         ["1", "(2 3)", "(1 2 3)", "(1 . 2)", "(1 2 3)", "4", "(1 2 3 4)"])

    def test_empty_list_edge_cases(self):
        self.assertEqual(run_lines("(list)\n(append)\n(length '())\n(cdr '(1))\n(car '(1))"),
                         ["()", "()", "0", "()", "1"])

    def test_list_predicates(self):
        self.assertEqual(run_lines("(null? '())\n(null? '(1))\n(pair? '(1 2))\n(pair? '())\n"
                                   "(list? '(1 2))\n(list? (cons 1 2))"),
                         ["#t", "#f", "#t", "#f", "#t", "#f"])

    def test_append_accepts_improper_tail(self):
        self.assertEqual(run_lines("(append '(1 2) 3)"), ["(1 2 . 3)"])


class PredicateTest(unittest.TestCase):
    """谓词，尤其是 eq? 与 equal? 的区别（spec §5、§11）。"""

    def test_type_predicates(self):
        program = """
        (number? 5)
        (number? 'x)
        (number? #t)
        (boolean? #t)
        (symbol? 'x)
        (string? "s")
        (procedure? car)
        (procedure? 1)
        (procedure? (lambda (x) x))
        """
        self.assertEqual(run_lines(program),
                         ["#t", "#f", "#f", "#t", "#t", "#t", "#t", "#f", "#t"])

    def test_numeric_predicates(self):
        self.assertEqual(run_lines("(zero? 0)\n(zero? 1)\n(even? 8)\n(odd? 7)"),
                         ["#t", "#f", "#t", "#t"])

    def test_eq_uses_identity_for_pairs(self):
        self.assertEqual(run_lines("(eq? '() '())\n(eq? '(1) '(1))\n(eq? 'a 'a)"),
                         ["#t", "#f", "#t"])

    def test_equal_is_structural_and_type_aware(self):
        program = """
        (equal? '(1 2 3) (list 1 2 3))
        (equal? '(1 (2)) '(1 (2)))
        (equal? #t 1)
        (equal? 'a "a")
        """
        self.assertEqual(run_lines(program), ["#t", "#t", "#f", "#f"])


class PrintingTest(unittest.TestCase):
    """打印规则：display 不带引号且不换行，顶层字符串带引号并转义（spec §8）。"""

    def test_display_and_newline(self):
        self.assertEqual(run('(display (+ 1 2))\n(newline)\n(display "hello")'),
                         '3\nhello')

    def test_string_escapes(self):
        self.assertEqual(run_lines('"hello"\n"a\\nb"\n"say \\"hi\\""'),
                         ['"hello"', '"a\\nb"', '"say \\"hi\\""'])

    def test_display_of_nested_list(self):
        self.assertEqual(run("(display '(a (b c)))"), "(a (b c))")

    def test_lambda_prints_as_procedure(self):
        self.assertEqual(run_lines("(lambda (x) x)"), ["#<procedure>"])


class CliTest(unittest.TestCase):
    """CLI 约定：多个文件共享同一个全局环境（spec §2）。"""

    def test_files_share_one_environment(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "a.scm")
            second = os.path.join(folder, "b.scm")
            with open(first, "w", encoding="utf-8") as handle:
                handle.write("(define x 21)\n")
            with open(second, "w", encoding="utf-8") as handle:
                handle.write("(* x 2)\n")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = interpreter.main([first, second])
            self.assertEqual(status, 0)
            self.assertEqual(buffer.getvalue(), "x\n42\n")


class ErrorTest(unittest.TestCase):
    """出错时给出 SchemeError（而不是 Python 的原始异常），spec §11。"""

    def test_unbound_symbol(self):
        with self.assertRaises(SchemeError):
            interpreter.run_source("no-such-variable", build_global_env(), io.StringIO())

    def test_calling_a_non_procedure(self):
        with self.assertRaises(SchemeError):
            interpreter.run_source("(1 2 3)", build_global_env(), io.StringIO())

    def test_unbalanced_parentheses(self):
        with self.assertRaises(SchemeError):
            interpreter.run_source("(+ 1 2", build_global_env(), io.StringIO())

    def test_wrong_argument_count(self):
        with self.assertRaises(SchemeError):
            interpreter.run_source("((lambda (x) x) 1 2)", build_global_env(), io.StringIO())


if __name__ == "__main__":
    unittest.main(verbosity=2)
