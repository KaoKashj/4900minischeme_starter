"""环境：变量绑定表 + 指向外层环境的指针（spec §9 的词法作用域）。

一个 :class:`Environment` 就是一层"框"：里面记着 ``名字 -> 值``，
另有一个 ``parent`` 指向外层。查变量时先看本层，找不到就顺着 ``parent``
往外找，一直找到全局环境；都没有就报"未绑定的符号"。

```text
全局环境 (define pi 3)
   ↑ parent
let 的新环境 (x = 3)
   ↑ parent
lambda 调用时的新环境 (参数 x = 7)
```

闭包之所以能记住定义时的变量（008/009 用例），就是因为 :class:`Closure`
保存的是**创建它时的那层环境对象**：以后调用时只是在这层环境外面再套一层。
"""

from __future__ import annotations

from typing import Any

from errors import SchemeError


class Environment:
    """一层变量绑定表。"""

    __slots__ = ("vars", "parent")

    def __init__(self, parent: "Environment | None" = None) -> None:
        self.vars: dict[str, Any] = {}
        self.parent = parent

    def define(self, name: str, value: Any) -> None:
        """在当前层绑定一个名字（重复绑定覆盖旧值，符合 let 的并行绑定语义）。"""
        self.vars[name] = value

    def lookup(self, name: str) -> Any:
        """按名字查值，逐层向外找。"""
        env: Environment | None = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise SchemeError("未绑定的符号 '%s'" % (name,))
