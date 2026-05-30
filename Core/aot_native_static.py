"""将模块级 Insn 子集静态求值，用于生成无 Python 依赖的本机程序。

支持的类型：int, str, bool（打印时转为 int 0/1）
支持的 binop：算术 (+, -, *, /, %)；位运算 (^, &, |, <<, >>)；比较 (==, !=, <, >, <=, >=) 返回 bool
支持的 unary：neg (-), bitnot (~), lnot (!) 返回 bool (lnot) 或 int
支持编译时常量的 if/else AST 改写（含函数体内部）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .Parser.AST.ASE import (
    BlockNode,
    ClassDefNode,
    FunctionDefNode,
    IfStmtNode,
    ThrowStmtNode,
    TryStmtNode,
    TemplateFunctionDefNode,
    statements_use_logical_shortcircuit,
    statements_use_pointer_ops,
)
from .Parser.AST.Data import BinOperator, UnaryOperator, _eval_binop_py
from .Parser.AST.asm_ir import AsmContext, flatten_stmt_asm, Insn
from .RunTime import Module


class NativeAOTUnsupported(RuntimeError):
    """当前源码模式无法静态编译为本机 exe（需完整运行时或改用 stub AOT）。"""


@dataclass
class _Frame:
    locals: dict[str, Any]
    parent: _Frame | None


@dataclass
class StaticNativeResult:
    prints: list[tuple[str, Any]] = field(default_factory=list)
    exit_code: int = 0


def _aot_truthy(v: Any) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, int) and v == 0:
        return False
    if isinstance(v, str) and v == "":
        return False
    return True


def _eval_binop(a: Any, op_name: str, b: Any) -> Any:
    bo = BinOperator[op_name]
    if bo == BinOperator.land:
        if not isinstance(a, (int, str, bool)) or not isinstance(b, (int, str, bool)):
            raise NativeAOTUnsupported(f"&& 需要基本类型操作数，得到 {type(a)}, {type(b)}")
        if not _aot_truthy(a):
            return False
        return _aot_truthy(b)
    if bo == BinOperator.lor:
        if not isinstance(a, (int, str, bool)) or not isinstance(b, (int, str, bool)):
            raise NativeAOTUnsupported(f"|| 需要基本类型操作数，得到 {type(a)}, {type(b)}")
        if _aot_truthy(a):
            return True
        return _aot_truthy(b)
    if bo in (
        BinOperator.bitxor, BinOperator.bitand, BinOperator.bitor,
        BinOperator.shl, BinOperator.shr,
    ):
        if isinstance(a, int) and isinstance(b, int):
            return _eval_binop_py(a, bo, b)
        raise NativeAOTUnsupported(f"位运算需要 int 操作数，得到 {type(a)}, {type(b)}")
    if bo in (
        BinOperator.lt, BinOperator.le, BinOperator.gt, BinOperator.ge,
        BinOperator.eq, BinOperator.ne,
    ):
        if isinstance(a, (int, str)) and isinstance(b, (int, str)):
            return _eval_binop_py(a, bo, b)
        raise NativeAOTUnsupported(f"比较运算需要 int/str 操作数，得到 {type(a)}, {type(b)}")
    if isinstance(a, (int, str)) and isinstance(b, (int, str)):
        return _eval_binop_py(a, bo, b)
    raise NativeAOTUnsupported(f"本机 AOT 仅支持 int/str 上的 binop，得到 {type(a)}, {type(b)}")


def _eval_unary(op_name: str, a: Any) -> Any:
    uo = UnaryOperator[op_name]
    if uo in (UnaryOperator.addr, UnaryOperator.deref):
        raise NativeAOTUnsupported("本机 AOT 不支持取址 / 解引用")
    if isinstance(a, int):
        if uo == UnaryOperator.neg:
            return -a
        if uo == UnaryOperator.bitnot:
            return ~a
        if uo == UnaryOperator.lnot:
            return not _aot_truthy(a)
        raise NativeAOTUnsupported(f"本机 AOT 不支持 unary {op_name!r}")
    if isinstance(a, bool):
        if uo == UnaryOperator.lnot:
            return not a
        raise NativeAOTUnsupported(f"bool 上不支持 unary {op_name!r}")
    if isinstance(a, str):
        if uo == UnaryOperator.lnot:
            return not _aot_truthy(a)
        raise NativeAOTUnsupported(f"str 上不支持 unary {op_name!r}")
    raise NativeAOTUnsupported(f"本机 AOT 的 unary 不支持类型 {type(a)}")


def _assert_module_native_safe(mod: Module) -> None:
    if statements_use_pointer_ops(mod.body.statements):
        raise NativeAOTUnsupported("模块顶层含指针/引用运算，无法本机 AOT")
    if statements_use_logical_shortcircuit(mod.body.statements):
        raise NativeAOTUnsupported("模块顶层含 && / || 短路逻辑，无法本机 AOT")
    for st in mod.body.statements:
        if isinstance(st, ClassDefNode):
            raise NativeAOTUnsupported("本机 AOT 暂不支持 class")
        if isinstance(st, FunctionDefNode):
            _check_fn_body_for_throw_and_try(st.body.statements, st.name)
            if statements_use_pointer_ops(st.body.statements):
                raise NativeAOTUnsupported(f"函数 {st.name!r} 含指针/引用运算")
            if statements_use_logical_shortcircuit(st.body.statements):
                raise NativeAOTUnsupported(f"函数 {st.name!r} 含 && / || 短路逻辑")
        if isinstance(st, TemplateFunctionDefNode):
            inn = st.inner
            _check_fn_body_for_throw_and_try(inn.body.statements, inn.name)
            if statements_use_pointer_ops(inn.body.statements):
                raise NativeAOTUnsupported(f"函数 {inn.name!r} 含指针/引用运算")
            if statements_use_logical_shortcircuit(inn.body.statements):
                raise NativeAOTUnsupported(f"函数 {inn.name!r} 含 && / || 短路逻辑")


def _check_fn_body_for_throw_and_try(stmts: list, fn_name: str) -> None:
    from .Parser.AST.ASE import BlockNode, IfStmtNode, WhileStmtNode
    for s in stmts:
        if isinstance(s, (ThrowStmtNode, TryStmtNode)):
            raise NativeAOTUnsupported(f"函数 {fn_name!r} 含 throw/try，无法本机 AOT")
        if isinstance(s, BlockNode):
            _check_fn_body_for_throw_and_try(s.statements, fn_name)
        elif isinstance(s, IfStmtNode):
            for _cond, blk in s.branches:
                _check_fn_body_for_throw_and_try(blk.statements, fn_name)
            if s.else_block is not None:
                _check_fn_body_for_throw_and_try(s.else_block.statements, fn_name)
        elif isinstance(s, WhileStmtNode):
            _check_fn_body_for_throw_and_try(s.body.statements, fn_name)


# ====== AST 层面的编译时常量分支改写 ======

def _try_eval_expr_to_value(expr_node, frame: _Frame) -> Any | None:
    """尝试将表达式编译时求值，返回 Python 值或 None（不可求值）。"""
    try:
        insns = expr_node.asm(AsmContext())
        stack: list[Any] = []
        _run_insns_limited(insns, frame, stack)
        if stack:
            return stack[-1]
        return None
    except (NativeAOTUnsupported, KeyError, IndexError):
        return None


def _run_insns_limited(seq: list[Insn], frame: _Frame, stack: list[Any]) -> None:
    i = 0
    n = len(seq)
    while i < n:
        insn = seq[i]
        op = insn[0]
        if op == "const":
            stack.append(insn[1])
        elif op == "load":
            name = insn[1]
            f: _Frame | None = frame
            found = False
            while f is not None:
                if name in f.locals:
                    stack.append(f.locals[name])
                    found = True
                    break
                f = f.parent
            if not found:
                raise KeyError(name)
        elif op == "binop":
            b = stack.pop()
            a = stack.pop()
            stack.append(_eval_binop(a, insn[1], b))
        elif op == "unary":
            stack.append(_eval_unary(insn[1], stack.pop()))
        else:
            raise NativeAOTUnsupported(f"条件表达式不支持 {op!r}")
        i += 1


def _transform_if_else_in_stmts(stmts: list, frame: _Frame) -> list:
    """递归遍历语句列表，对 if/else 进行编译时常量改写。返回改写后的语句列表。"""
    new_stmts: list = []
    for s in stmts:
        if isinstance(s, IfStmtNode):
            resolved = False
            for cond, block in s.branches:
                val = _try_eval_expr_to_value(cond, frame)
                if val is not None and _aot_truthy(val):
                    # 将此分支作为 new_stmts 的直接成员添加（铺平 block 包装）
                    transformed = _transform_if_else_in_stmts(block.statements, frame)
                    new_stmts.extend(transformed)
                    resolved = True
                    break
            if not resolved and s.else_block is not None:
                transformed = _transform_if_else_in_stmts(s.else_block.statements, frame)
                new_stmts.extend(transformed)
            # 如果既无匹配分支又无 else，则不添加任何语句（if 跳过）
        elif isinstance(s, BlockNode):
            transformed = _transform_if_else_in_stmts(s.statements, frame)
            new_s = BlockNode(transformed)
            new_stmts.append(new_s)
        elif isinstance(s, FunctionDefNode):
            # 不展开函数体，保持原样；在模块顶层定义时再展开
            new_stmts.append(s)
        else:
            new_stmts.append(s)
    return new_stmts


def _transform_function_bodies_in_module(mod: Module, root_frame: _Frame) -> None:
    """在模块 AST 中递归改写所有函数体内的 if/else。"""
    from .Parser.AST.ASE import BlockNode
    for st in mod.body.statements:
        if isinstance(st, FunctionDefNode):
            transformed = _transform_if_else_in_stmts(st.body.statements, root_frame)
            st.body = BlockNode(transformed)
        elif isinstance(st, TemplateFunctionDefNode):
            transformed = _transform_if_else_in_stmts(st.inner.body.statements, root_frame)
            st.inner.body = BlockNode(transformed)


# ====== 主静态求值入口 ======

def static_eval_module_for_native(mod: Module) -> StaticNativeResult:
    _assert_module_native_safe(mod)
    ctx = AsmContext()
    result = StaticNativeResult()
    root_globals: dict[str, Any] = {
        "print": ("__builtin_print__",),
    }
    fr = _Frame(locals=root_globals, parent=None)

    # AST 层面改写：展开所有函数体中的编译时常量 if/else
    _transform_function_bodies_in_module(mod, fr)

    global_insns = flatten_stmt_asm(mod.body.statements, ctx)

    def getvar(frame: _Frame, name: str) -> Any:
        f: _Frame | None = frame
        while f is not None:
            if name in f.locals:
                return f.locals[name]
            f = f.parent
        raise NativeAOTUnsupported(f"未绑定的名字: {name!r}")

    def assign_var(frame: _Frame, name: str, val: Any) -> None:
        frame.locals[name] = val

    def _print_value(v: Any) -> None:
        if isinstance(v, bool):
            result.prints.append(("int", 1 if v else 0))
        elif isinstance(v, int):
            result.prints.append(("int", int(v)))
        elif isinstance(v, str):
            result.prints.append(("str", v))
        else:
            raise NativeAOTUnsupported(f"print 需要 int/str/bool，得到 {type(v)}")

    def run_insns(
        seq: list[Insn],
        frame: _Frame,
        stack: list[Any],
    ) -> Any | None:
        i = 0
        n = len(seq)
        while i < n:
            insn = seq[i]
            op = insn[0]
            if op == "const":
                stack.append(insn[1])
            elif op == "load":
                stack.append(getvar(frame, insn[1]))
            elif op == "load_scoped":
                raise NativeAOTUnsupported("load_scoped")
            elif op == "store":
                assign_var(frame, insn[1], stack.pop())
            elif op == "store_scoped_assign" or op == "store_scoped_decl":
                raise NativeAOTUnsupported(op)
            elif op == "binop":
                b = stack.pop()
                a = stack.pop()
                stack.append(_eval_binop(a, insn[1], b))
            elif op == "unary":
                stack.append(_eval_unary(insn[1], stack.pop()))
            elif op == "pop":
                stack.pop()
            elif op == "decl":
                typ, name = insn[1], insn[2]
                z = 0 if typ == "int" else ("" if typ == "string" else (False if typ == "bool" else None))
                if z is None:
                    raise NativeAOTUnsupported(f"decl 类型 {typ!r}")
                frame.locals[name] = z
            elif op == "store_decl_local":
                name = insn[1]
                frame.locals[name] = stack.pop()
            elif op == "delete":
                raise NativeAOTUnsupported("delete")
            elif op == "var_scope_order":
                raise NativeAOTUnsupported("var_scope_order")
            elif op == "define":
                _, name, pnames, _ptypes, void_i, _tparams, body_t = insn
                frame.locals[name] = ("fn", tuple(pnames), tuple(body_t), bool(void_i))
            elif op == "class_def":
                raise NativeAOTUnsupported("class_def")
            elif op == "call":
                _, fname, nargs, kw_order = insn
                if tuple(kw_order):
                    raise NativeAOTUnsupported("带关键字参数的 call")
                args = [stack.pop() for _ in range(nargs)]
                args.reverse()
                target = getvar(frame, fname)
                if target == ("__builtin_print__",):
                    if nargs != 1:
                        raise NativeAOTUnsupported("print 只支持一个参数")
                    _print_value(args[0])
                    stack.append(None)
                elif isinstance(target, tuple) and target[0] == "fn":
                    pnames, body_insns, void_ret = target[1], target[2], target[3]
                    if len(pnames) != len(args):
                        raise NativeAOTUnsupported("实参个数不匹配")
                    child = _Frame(
                        locals=dict(zip(pnames, args)),
                        parent=frame,
                    )
                    sub_stack: list[Any] = []
                    try:
                        run_insns(list(body_insns), child, sub_stack)
                    except _Return as r:
                        if void_ret:
                            stack.append(None)
                        else:
                            stack.append(r.value)
                    else:
                        if void_ret:
                            stack.append(None)
                        else:
                            raise NativeAOTUnsupported("函数未执行 ret")
                else:
                    raise NativeAOTUnsupported(f"不可调用: {fname!r}")
            elif op == "call_indirect":
                raise NativeAOTUnsupported("call_indirect")
            elif op == "get_attr" or op == "set_attr":
                raise NativeAOTUnsupported(op)
            elif op == "ret":
                raise _Return(stack.pop())
            elif op == "retvoid":
                raise _Return(None)
            else:
                raise NativeAOTUnsupported(f"未知指令 {op!r}")
            i += 1
        return None

    stack: list[Any] = []
    try:
        run_insns(global_insns, fr, stack)
    except _Return:
        raise NativeAOTUnsupported("模块顶层不应 return") from None

    main_fn = fr.locals.get("main")
    if main_fn is None:
        raise NativeAOTUnsupported("未找到 int main()：本机 AOT 需要可调用的 main")
    if not (isinstance(main_fn, tuple) and main_fn[0] == "fn"):
        raise NativeAOTUnsupported("main 必须是函数定义")
    pnames, body_insns, void_ret = main_fn[1], main_fn[2], main_fn[3]
    if void_ret:
        raise NativeAOTUnsupported("本机 AOT 需要 main 返回 int（非 void）")
    if len(pnames) != 0:
        raise NativeAOTUnsupported("本机 AOT 暂不支持带参数的 main")

    mstack: list[Any] = []
    child = _Frame(locals={}, parent=fr)
    try:
        run_insns(list(body_insns), child, mstack)
    except _Return as r:
        v = r.value
        if v is None:
            result.exit_code = 0
        elif isinstance(v, int):
            result.exit_code = int(v) & 255
        else:
            raise NativeAOTUnsupported(f"main 返回值须为 int，得到 {type(v)}")
    else:
        raise NativeAOTUnsupported("main 未 return")

    return result


class _Return(Exception):
    __slots__ = ("value",)

    def __init__(self, value: Any):
        self.value = value
