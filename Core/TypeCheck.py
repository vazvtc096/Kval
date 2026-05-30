from __future__ import annotations

from .Parser.AST.ASE import (
    AssignStmtNode,
    BlockNode,
    BreakStmtNode,
    ClassDefNode,
    CompoundAssignStmtNode,
    ContinueStmtNode,
    DeleteStmtNode,
    DerefAssignStmtNode,
    ExprStmtNode,
    ForCStmtNode,
    ForRangeStmtNode,
    FromImportStmtNode,
    FunctionDefNode,
    IfStmtNode,
    ImportStmtNode,
    NamespaceDefNode,
    ReturnNode,
    ScopedAssignStmtNode,
    ScopedCompoundAssignStmtNode,
    ScopedVarDeclNode,
    StructDefNode,
    SwitchStmtNode,
    TemplateFunctionDefNode,
    ThrowStmtNode,
    TryStmtNode,
    VarDeclNode,
    VarScopeOrderStmtNode,
    WhileStmtNode,
)
from .Parser.AST.Base import ASTNode
from .Parser.AST.Data import (
    ArrayLiteralNode,
    AttributeAccessNode,
    AttributeStoreNode,
    BinOperator,
    BinOpNode,
    BoolLiteralNode,
    ConstValueNode,
    FunctionCallNode,
    IndexAccessNode,
    IndexStoreNode,
    LiteralsNode,
    ScopedLoadNode,
    UnaryOperator,
    UnaryOpNode,
    VariableLoadNode,
)
from .RunTime import Module


class StaticTypeError(Exception):
    pass


def scoped_key(scope: str, name: str) -> str:
    return f"{scope}::{name}"


def _reference_base_type(t: str) -> str:
    u = t
    while u.endswith("&"):
        u = u[:-1]
    return u


def _lookup_this_member_type(env: TypeEnv, name: str) -> str | None:
    this_t = env.lookup("this")
    if this_t is None:
        return None
    fields = env.class_fields.get(this_t, {})
    if name in fields:
        return fields[name]
    methods = env.class_methods.get(this_t, {})
    if name in methods:
        ret_void, ret_t, _pts, _pn = methods[name]
        return "void" if ret_void else ret_t
    return None


def _snapshot_type_env(env: TypeEnv) -> dict[str, str]:
    acc: dict[str, str] = {}
    for layer in env.scopes:
        acc.update(layer)
    return acc


class TypeEnv:
    __slots__ = ("scopes", "class_fields", "class_methods", "const_symbols")

    def __init__(
        self,
        class_fields: dict[str, dict[str, str]] | None = None,
        class_methods: dict[str, dict[str, ClassMethodSig]] | None = None,
        const_symbols: set[str] | None = None,
    ) -> None:
        self.scopes: list[dict[str, str]] = [{}]
        self.class_fields: dict[str, dict[str, str]] = class_fields if class_fields is not None else {}
        self.class_methods: dict[str, dict[str, ClassMethodSig]] = (
            class_methods if class_methods is not None else {}
        )
        self.const_symbols: set[str] = const_symbols if const_symbols is not None else set()

    def enter_block(self) -> None:
        self.scopes.append({})

    def leave_block(self) -> None:
        self.scopes.pop()

    def lookup(self, name: str) -> str | None:
        for d in reversed(self.scopes):
            if name in d:
                return d[name]
        return None

    def declare(self, name: str, typ: str) -> None:
        if name in self.scopes[-1]:
            raise StaticTypeError(f"重复声明变量 {name!r}（类型 {typ}）")
        self.scopes[-1][name] = typ

    def bind_or_check_assign(self, name: str, typ: str) -> None:
        if name in self.const_symbols:
            raise StaticTypeError(f"const 变量 {name!r} 不可重新赋值")
        cur = self.lookup(name)
        if cur is None:
            raise StaticTypeError(f"赋值目标 {name!r} 须先有显式类型声明（与运行时一致）")
        if cur.endswith("&"):
            base = _reference_base_type(cur)
            if typ != base:
                raise StaticTypeError(f"赋值类型不匹配：{name!r} 为引用 {cur}，右侧须为 {base}，得到 {typ}")
            return
        if cur != typ:
            raise StaticTypeError(f"赋值类型不匹配：{name!r} 为 {cur}，右侧为 {typ}")

    def mark_const(self, name: str) -> None:
        self.const_symbols.add(name)


_PRIMITIVE_TYPES = frozenset({"int", "float", "bool", "string", "array", "void"})


def _is_opaque_type(t: str) -> bool:
    return t not in _PRIMITIVE_TYPES


def _reject_void_logical_operand(t: str, where: str) -> None:
    if t == "void":
        raise StaticTypeError(f"{where} 的操作数不能为 void")


def _binop_result_type(lt: str, op: BinOperator, rt: str) -> str:
    if op in (BinOperator.land, BinOperator.lor):
        _reject_void_logical_operand(lt, "&& / ||")
        _reject_void_logical_operand(rt, "&& / ||")
        return "bool"

    if op in (
        BinOperator.lt,
        BinOperator.le,
        BinOperator.gt,
        BinOperator.ge,
        BinOperator.eq,
        BinOperator.ne,
    ):
        if lt == rt and lt in ("int", "float", "bool", "string"):
            return "bool"
        if _is_opaque_type(lt) and lt == rt:
            return "bool"
        raise StaticTypeError(f"比较运算两侧类型须一致（得到 {lt!r} 与 {rt!r}）")

    if lt == "int" and rt == "int":
        if op in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
            BinOperator.bitxor,
            BinOperator.bitand,
            BinOperator.bitor,
            BinOperator.shl,
            BinOperator.shr,
        ):
            return "int"
        raise StaticTypeError(f"不支持的 int 二元运算：{op.name}")

    if lt in ("int", "float") and rt in ("int", "float"):
        if op in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
        ):
            return "float" if "float" in (lt, rt) else "int"
        raise StaticTypeError(f"浮点/整数不支持该运算：{op.name}")

    if op == BinOperator.add and lt == "string" and rt == "string":
        return "string"
    if op == BinOperator.mul and ((lt == "string" and rt == "int") or (lt == "int" and rt == "string")):
        return "string"

    if _is_opaque_type(lt) and lt == rt:
        if op in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
            BinOperator.bitxor,
            BinOperator.bitand,
            BinOperator.bitor,
            BinOperator.shl,
            BinOperator.shr,
        ):
            return lt
        raise StaticTypeError(f"泛型/自定义类型 {lt} 上不支持运算 {op.name}")

    raise StaticTypeError(f"二元运算类型无效：{lt!r} {op.name} {rt!r}")


def _check_compound(lhs_t: str, op: BinOperator, rhs_t: str) -> None:
    if lhs_t == "int":
        if rhs_t != "int":
            raise StaticTypeError(f"复合赋值：int 左侧要求右侧为 int，得到 {rhs_t!r}（{op.name}）")
        if op not in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
            BinOperator.bitxor,
            BinOperator.bitand,
            BinOperator.bitor,
            BinOperator.shl,
            BinOperator.shr,
        ):
            raise StaticTypeError(f"复合赋值不支持运算 {op.name} 于 int")
        return
    if lhs_t == "float":
        if rhs_t not in ("int", "float"):
            raise StaticTypeError(f"复合赋值：float 左侧要求右侧为 int/float，得到 {rhs_t!r}（{op.name}）")
        if op not in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
        ):
            raise StaticTypeError(f"复合赋值不支持运算 {op.name} 于 float")
        return
    if lhs_t == "string":
        if op == BinOperator.add:
            if rhs_t != "string":
                raise StaticTypeError("字符串 += 要求右侧为 string")
            return
        if op == BinOperator.mul:
            if rhs_t != "int":
                raise StaticTypeError("字符串 *= 要求右侧为 int")
            return
        raise StaticTypeError(f"string 不支持复合赋值运算符 {op.name}")
    if _is_opaque_type(lhs_t):
        if lhs_t != rhs_t:
            raise StaticTypeError(f"复合赋值要求左右类型一致：{lhs_t!r} 与 {rhs_t!r}")
        if op not in (
            BinOperator.add,
            BinOperator.sub,
            BinOperator.mul,
            BinOperator.div,
            BinOperator.mod,
            BinOperator.bitxor,
            BinOperator.bitand,
            BinOperator.bitor,
            BinOperator.shl,
            BinOperator.shr,
        ):
            raise StaticTypeError(f"该类型上不支持复合赋值 {op.name}")
        return
    raise StaticTypeError(f"复合赋值左侧类型不支持：{lhs_t!r}")


def _walk_collect_functions(stmts: list, acc: list[FunctionDefNode]) -> None:
    for s in stmts:
        if isinstance(s, FunctionDefNode):
            acc.append(s)
            _walk_collect_functions(s.body.statements, acc)
        elif isinstance(s, TemplateFunctionDefNode):
            acc.append(s.inner)
            _walk_collect_functions(s.inner.body.statements, acc)
        elif isinstance(s, BlockNode):
            _walk_collect_functions(s.statements, acc)
        elif isinstance(s, IfStmtNode):
            for _c, blk in s.branches:
                _walk_collect_functions(blk.statements, acc)
            if s.else_block is not None:
                _walk_collect_functions(s.else_block.statements, acc)
        elif isinstance(s, WhileStmtNode):
            _walk_collect_functions(s.body.statements, acc)
        elif isinstance(s, ForCStmtNode):
            if s.init is not None:
                _walk_stmt_for_nested_functions(s.init, acc)
            _walk_collect_functions(s.body.statements, acc)
            if s.step is not None:
                _walk_stmt_for_nested_functions(s.step, acc)
        elif isinstance(s, ForRangeStmtNode):
            _walk_collect_functions(s.body.statements, acc)
        elif isinstance(s, SwitchStmtNode):
            for _ce, blk in s.cases:
                _walk_collect_functions(blk.statements, acc)
            if s.else_block is not None:
                _walk_collect_functions(s.else_block.statements, acc)
        elif isinstance(s, TryStmtNode):
            _walk_collect_functions(s.try_block.statements, acc)
            for _tn, _bn, blk in s.catches:
                _walk_collect_functions(blk.statements, acc)
            if s.else_block is not None:
                _walk_collect_functions(s.else_block.statements, acc)
            if s.finally_block is not None:
                _walk_collect_functions(s.finally_block.statements, acc)
        elif isinstance(s, NamespaceDefNode):
            _walk_collect_functions(s.body_stmts, acc)
        elif isinstance(s, (ClassDefNode, StructDefNode)):
            pass


def _walk_stmt_for_nested_functions(s: ASTNode, acc: list[FunctionDefNode]) -> None:
    if isinstance(s, BlockNode):
        _walk_collect_functions(s.statements, acc)


FuncSig = tuple[tuple[str, ...], tuple[str, ...], str, bool, tuple[str, ...]]

# (returns_void, return_type, param_types, param_names)
ClassMethodSig = tuple[bool, str, tuple[str, ...], tuple[str, ...]]


def _collect_func_sigs(stmts: list) -> dict[str, list[FuncSig]]:
    acc: list[FunctionDefNode] = []
    _walk_collect_functions(stmts, acc)
    out: dict[str, list[FuncSig]] = {}
    for fn in acc:
        sig: FuncSig = (
            tuple(fn.param_types),
            tuple(fn.param_names),
            fn.return_type,
            fn.returns_void,
            fn.type_param_names,
        )
        out.setdefault(fn.name, []).append(sig)
    return out


def _collect_class_layout(
    stmts: list,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, ClassMethodSig]]]:
    fields: dict[str, dict[str, str]] = {}
    methods: dict[str, dict[str, ClassMethodSig]] = {}
    class_nodes: dict[str, ClassDefNode] = {}
    for s in stmts:
        if isinstance(s, ClassDefNode):
            class_nodes[s.name] = s

    def merge_bases(cname: str, seen: set[str]) -> tuple[dict[str, str], dict[str, ClassMethodSig]]:
        if cname in seen:
            raise StaticTypeError(f"类继承出现循环：{cname}")
        seen.add(cname)
        node = class_nodes.get(cname)
        if node is None:
            return {}, {}
        fd: dict[str, str] = {}
        md: dict[str, ClassMethodSig] = {}
        for _inherit_access, bname in getattr(node, "bases", ()):
            if bname not in class_nodes:
                raise StaticTypeError(f"类 {cname!r} 的基类 {bname!r} 未定义")
            bfd, bmd = merge_bases(bname, seen)
            for n, t in bfd.items():
                if n not in fd:
                    fd[n] = t
            for n, sig in bmd.items():
                if n not in md:
                    md[n] = sig
            bnode = class_nodes[bname]
            for m in bnode.member_stmts:
                n = getattr(m, "name", None)
                if not isinstance(n, str):
                    continue
                acc = getattr(m, "_class_member_access", "private")
                if acc == "private":
                    continue
                if n in fd or n in md:
                    continue
                if isinstance(m, VarDeclNode):
                    fd[n] = m.typ
                elif isinstance(m, FunctionDefNode):
                    md[n] = (m.returns_void, m.return_type, tuple(m.param_types), tuple(m.param_names))
                elif isinstance(m, TemplateFunctionDefNode):
                    inn = m.inner
                    md[n] = (inn.returns_void, inn.return_type, tuple(inn.param_types), tuple(inn.param_names))
        seen.remove(cname)
        return fd, md

    for s in stmts:
        if isinstance(s, ClassDefNode):
            fd, md = merge_bases(s.name, set())
            for m in s.member_stmts:
                if isinstance(m, VarDeclNode):
                    fd[m.name] = m.typ
                elif isinstance(m, FunctionDefNode):
                    md[m.name] = (
                        m.returns_void,
                        m.return_type,
                        tuple(m.param_types),
                        tuple(m.param_names),
                    )
                elif isinstance(m, TemplateFunctionDefNode):
                    inn = m.inner
                    md[inn.name] = (
                        inn.returns_void,
                        inn.return_type,
                        tuple(inn.param_types),
                        tuple(inn.param_names),
                    )
            fields[s.name] = fd
            methods[s.name] = md
        elif isinstance(s, StructDefNode):
            fd: dict[str, str] = {}
            for m in s.member_stmts:
                if isinstance(m, VarDeclNode):
                    fd[m.name] = m.typ
            fields[s.name] = fd
            methods[s.name] = {}
    return fields, methods


def _sig_matches_call_form(pts: tuple[str, ...], pn: list[str], args: list, kwargs: dict) -> bool:
    has_star = bool(pts) and pts[-1] == "kwargs"
    core_pn = list(pn[:-1] if has_star else pn)
    assigned: set[str] = set()
    for i in range(len(args)):
        if i >= len(core_pn):
            return False
        assigned.add(core_pn[i])
    for k in kwargs:
        if k in assigned:
            return False
        if k in core_pn:
            assigned.add(k)
        elif not has_star:
            return False
    for pname in core_pn:
        if pname not in assigned:
            return False
    return True


def _pick_overload(
    fname: str,
    sigs: list[FuncSig],
    args: list,
    kwargs: dict,
    env: TypeEnv,
    func_sigs: dict[str, list[FuncSig]],
) -> FuncSig:
    matches: list[FuncSig] = []
    for sig in sigs:
        pts, pn, _rt, _void, _tpn = sig
        if not _sig_matches_call_form(pts, list(pn), args, kwargs):
            continue
        try:
            _check_call_arguments(fname, pts, list(pn), args, kwargs, env, func_sigs)
            matches.append(sig)
        except StaticTypeError:
            continue
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise StaticTypeError(f"调用 {fname!r} 无匹配的重载签名")
    raise StaticTypeError(f"调用 {fname!r} 存在多个匹配的重载")


def _types_compatible(at: str, pt: str) -> bool:
    if pt == "auto":
        return True
    return at == pt or (_is_opaque_type(pt) and at == pt)


def _is_literal_init_expr(e: ASTNode | None) -> bool:
    return isinstance(e, (LiteralsNode, BoolLiteralNode, ArrayLiteralNode))


def _check_call_arguments(
    fname: str,
    pts: tuple[str, ...],
    pn: list[str],
    args: list,
    kwargs: dict,
    env: TypeEnv,
    func_sigs: dict[str, list[FuncSig]],
) -> None:
    has_star = bool(pts) and pts[-1] == "kwargs"
    n_core = len(pts) - 1 if has_star else len(pts)
    core_pts = pts[:n_core]
    core_pn = pn[:n_core]

    assigned: set[str] = set()

    for i, arg in enumerate(args):
        if i >= n_core:
            raise StaticTypeError(f"调用 {fname} 位置实参过多")
        pname = core_pn[i]
        at = _expr_type(arg, env, func_sigs)
        pt = core_pts[i]
        if not _types_compatible(at, pt):
            raise StaticTypeError(f"调用 {fname} 参数 {pname!r} 期望 {pt}，得到 {at}")
        assigned.add(pname)

    for k, arg in kwargs.items():
        if k in assigned:
            raise StaticTypeError(f"调用 {fname} 重复指定参数 {k!r}")
        if k in core_pn:
            at = _expr_type(arg, env, func_sigs)
            pt = core_pts[core_pn.index(k)]
            if not _types_compatible(at, pt):
                raise StaticTypeError(f"调用 {fname} 参数 {k!r} 期望 {pt}，得到 {at}")
            assigned.add(k)
        elif has_star:
            _expr_type(arg, env, func_sigs)
        else:
            raise StaticTypeError(f"调用 {fname} 无此关键字参数 {k!r}")

    for pname in core_pn:
        if pname not in assigned:
            raise StaticTypeError(f"调用 {fname} 缺少参数 {pname!r}")


def _expr_type(
    e: ASTNode,
    env: TypeEnv,
    func_sigs: dict[str, list[FuncSig]],
) -> str:
    if isinstance(e, LiteralsNode):
        v = e.value
        if isinstance(v, bool):
            return "int"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, str):
            return "string"
        if isinstance(v, list):
            return "array"
        raise StaticTypeError(f"无法推断字面量类型：{type(v).__name__}")

    if isinstance(e, BoolLiteralNode):
        return "bool"

    if isinstance(e, VariableLoadNode):
        if e.name == "this":
            t = env.lookup("this")
            if t is not None:
                return t
            raise StaticTypeError("this 仅能在类成员方法中使用")
        if e.name in func_sigs:
            sigs = func_sigs[e.name]
            non_t = [s for s in sigs if not s[4]]
            if not non_t:
                _, _, ret_t, void, _ = sigs[0]
                return "void" if void else ret_t
            if len(non_t) == 1:
                _, _, ret_t, void, _ = non_t[0]
                return "void" if void else ret_t
            variants = {(s[2], s[3]) for s in non_t}
            if len(variants) == 1:
                ret_t, void = next(iter(variants))
                return "void" if void else ret_t
            raise StaticTypeError(f"函数 {e.name!r} 有多重载且返回值不一致，不能直接作为值使用")
        t = env.lookup(e.name)
        if t is None:
            mt = _lookup_this_member_type(env, e.name)
            if mt is not None:
                return mt
            raise StaticTypeError(f"未声明的变量 {e.name!r}（无法推断类型）")
        return t

    if isinstance(e, ScopedLoadNode):
        k = scoped_key(e.scope, e.name)
        t = env.lookup(k)
        if t is None:
            st = env.lookup(e.scope)
            if st in ("namespace", "module", "imported"):
                return "imported"
            raise StaticTypeError(f"未声明的作用域变量 {k!r}")
        return t

    if isinstance(e, UnaryOpNode):
        if e.op == UnaryOperator.lnot:
            inner = _expr_type(e.value, env, func_sigs)
            _reject_void_logical_operand(inner, "!")
            return "bool"
        if e.op == UnaryOperator.addr:
            if not isinstance(e.value, VariableLoadNode):
                raise StaticTypeError("& 仅可用于简单变量")
            vn = e.value.name
            if vn == "this":
                raise StaticTypeError("不能对 this 取址")
            inner_t = env.lookup(vn)
            if inner_t is None:
                raise StaticTypeError(f"取址目标 {vn!r} 未声明类型")
            base = inner_t
            while base.endswith("&"):
                base = base[:-1]
            return f"{base}*"
        if e.op == UnaryOperator.deref:
            inner = _expr_type(e.value, env, func_sigs)
            if not inner.endswith("*"):
                raise StaticTypeError("* 的操作数须为指针类型")
            return inner[:-1]
        inner = _expr_type(e.value, env, func_sigs)
        if inner not in ("int", "float"):
            raise StaticTypeError("单目 - 仅适用于 int/float，~ 仅适用于 int")
        if e.op == UnaryOperator.bitnot and inner != "int":
            raise StaticTypeError("单目 ~ 仅适用于 int")
        return inner if e.op == UnaryOperator.neg else "int"

    if isinstance(e, BinOpNode):
        lt = _expr_type(e.left, env, func_sigs)
        rt = _expr_type(e.right, env, func_sigs)
        if e.op == BinOperator.add and _is_opaque_type(lt) and rt == "int":
            return "int"
        return _binop_result_type(lt, e.op, rt)

    if isinstance(e, ArrayLiteralNode):
        for el in e.elements:
            _expr_type(el, env, func_sigs)
        return "array"

    if isinstance(e, IndexAccessNode):
        ot = _expr_type(e.obj, env, func_sigs)
        it = _expr_type(e.index, env, func_sigs)
        if it != "int":
            raise StaticTypeError("数组索引必须为 int")
        if ot == "array":
            return "int"
        if ot == "string":
            return "string"
        raise StaticTypeError(f"该类型不支持索引：{ot}")

    if isinstance(e, IndexStoreNode):
        ot = _expr_type(e.obj, env, func_sigs)
        it = _expr_type(e.index, env, func_sigs)
        _expr_type(e.value, env, func_sigs)
        if it != "int":
            raise StaticTypeError("数组索引必须为 int")
        if ot not in ("array",):
            raise StaticTypeError(f"该类型不支持索引赋值：{ot}")
        return "void"

    if isinstance(e, FunctionCallNode):
        if isinstance(e.func, VariableLoadNode) and e.func.name == "print":
            for a in e.args:
                _expr_type(a, env, func_sigs)
            for v in e.kwargs.values():
                _expr_type(v, env, func_sigs)
            return "void"
        if isinstance(e.func, VariableLoadNode) and e.func.name == "input":
            for a in e.args:
                _expr_type(a, env, func_sigs)
            for v in e.kwargs.values():
                _expr_type(v, env, func_sigs)
            return "string"
        if isinstance(e.func, VariableLoadNode) and e.func.name == "ord":
            if len(e.args) != 1 or e.kwargs:
                raise StaticTypeError("ord 需要且仅需要一个位置参数")
            at = _expr_type(e.args[0], env, func_sigs)
            if at != "string":
                raise StaticTypeError("ord 参数必须为 string")
            return "int"
        if isinstance(e.func, VariableLoadNode) and e.func.name == "chr":
            if len(e.args) != 1 or e.kwargs:
                raise StaticTypeError("chr 需要且仅需要一个位置参数")
            at = _expr_type(e.args[0], env, func_sigs)
            if at != "int":
                raise StaticTypeError("chr 参数必须为 int")
            return "string"
        if isinstance(e.func, ScopedLoadNode):
            for a in e.args:
                _expr_type(a, env, func_sigs)
            for v in e.kwargs.values():
                _expr_type(v, env, func_sigs)
            return "imported"
        if isinstance(e.func, AttributeAccessNode):
            fa = e.func
            if isinstance(fa.obj, VariableLoadNode) and fa.obj.name == "base":
                this_t = env.lookup("this")
                if this_t is None:
                    raise StaticTypeError("base 仅能在类成员方法中使用")
                ms = env.class_methods.get(this_t)
                if ms and fa.attr in ms:
                    ret_void, ret_t, pts, pn = ms[fa.attr]
                    _check_call_arguments(fa.attr, tuple(pts), list(pn), e.args, e.kwargs, env, func_sigs)
                    return "void" if ret_void else ret_t
                raise StaticTypeError(f"base 不存在成员方法 {fa.attr!r}")
            if isinstance(fa.obj, VariableLoadNode):
                ot = env.lookup(fa.obj.name)
                if ot in ("module", "imported", "namespace"):
                    for a in e.args:
                        _expr_type(a, env, func_sigs)
                    for v in e.kwargs.values():
                        _expr_type(v, env, func_sigs)
                    return "imported"
                if ot is not None and _is_opaque_type(ot):
                    ms = env.class_methods.get(ot)
                    if ms and fa.attr in ms:
                        ret_void, ret_t, pts, pn = ms[fa.attr]
                        _check_call_arguments(fa.attr, tuple(pts), list(pn), e.args, e.kwargs, env, func_sigs)
                        return "void" if ret_void else ret_t
            raise StaticTypeError("仅支持在已知类实例上调用已声明的成员方法")

        if isinstance(e.func, VariableLoadNode):
            fname = e.func.name
            sigs = func_sigs.get(fname)
            if not sigs:
                if fname in env.class_fields and fname in env.class_methods and not env.class_methods[fname]:
                    if e.args or e.kwargs:
                        raise StaticTypeError(f"struct {fname!r} 构造不接受参数")
                    return fname
                this_t = env.lookup("this")
                if this_t is not None:
                    ms = env.class_methods.get(this_t, {})
                    if fname in ms:
                        ret_void, ret_t, pts, pn = ms[fname]
                        _check_call_arguments(fname, tuple(pts), list(pn), e.args, e.kwargs, env, func_sigs)
                        return "void" if ret_void else ret_t
                cm = env.class_methods.get(fname)
                if cm is not None:
                    ctor_key = fname if fname in cm else f"New{fname}"
                    if ctor_key in cm:
                        _ret_void, _ret_t, pts, pn = cm[ctor_key]
                        _check_call_arguments(ctor_key, tuple(pts), list(pn), e.args, e.kwargs, env, func_sigs)
                        return fname
                vt = env.lookup(fname)
                if vt in ("module", "imported") or (vt is not None and _is_opaque_type(vt)):
                    for a in e.args:
                        _expr_type(a, env, func_sigs)
                    for v in e.kwargs.values():
                        _expr_type(v, env, func_sigs)
                    return "imported"
                raise StaticTypeError(f"调用未声明函数 {fname!r}，无法做静态返回类型检查")
            non_t = [s for s in sigs if not s[4]]
            if non_t:
                pts, pn, ret_t, void, _tpn = _pick_overload(fname, non_t, e.args, e.kwargs, env, func_sigs)
                return "void" if void else ret_t
            pts, pn, ret_t, void, tpn = sigs[0]
            if tpn:
                for arg in e.args:
                    _expr_type(arg, env, func_sigs)
                for v in e.kwargs.values():
                    _expr_type(v, env, func_sigs)
                return "void" if void else ret_t
            _check_call_arguments(fname, pts, list(pn), e.args, e.kwargs, env, func_sigs)
            return "void" if void else ret_t
        raise StaticTypeError("仅支持对裸名函数的静态类型调用检查")

    if isinstance(e, AttributeAccessNode):
        if isinstance(e.obj, VariableLoadNode) and e.obj.name == "base":
            this_t = env.lookup("this")
            if this_t is None:
                raise StaticTypeError("base 仅能在类成员方法中使用")
            fd = env.class_fields.get(this_t, {})
            if e.attr in fd:
                return fd[e.attr]
            ms = env.class_methods.get(this_t, {})
            if e.attr in ms:
                ret_void, ret_t, _pts, _pn = ms[e.attr]
                return "void" if ret_void else ret_t
            raise StaticTypeError(f"base 不存在成员 {e.attr!r}")
        if isinstance(e.obj, VariableLoadNode) and e.obj.name == "this":
            mt = env.lookup(e.attr)
            if mt is not None:
                return mt
        if isinstance(e.obj, VariableLoadNode):
            ot = env.lookup(e.obj.name)
            if ot in ("module", "imported"):
                return "imported"
            if ot is not None and _is_opaque_type(ot):
                fd = env.class_fields.get(ot)
                if fd:
                    mt = fd.get(e.attr)
                    if mt is not None:
                        return mt
        raise StaticTypeError("属性访问的静态类型尚未实现")

    if isinstance(e, AttributeStoreNode):
        _expr_type(e.obj, env, func_sigs)
        _expr_type(e.value, env, func_sigs)
        return "void"

    raise StaticTypeError(f"静态类型检查不支持的表达式：{type(e).__name__}")


def _check_stmt(
    s: ASTNode,
    env: TypeEnv,
    func_sigs: dict[str, list[FuncSig]],
    ret_void: bool,
    ret_type: str,
    top_level: bool = False,
) -> None:
    if isinstance(s, VarDeclNode):
        if (getattr(s, "is_const", False) or getattr(s, "is_constexpr", False)) and not top_level:
            raise StaticTypeError(f"{'const' if getattr(s, 'is_const', False) else 'constexpr'} 变量必须定义在全局作用域")
        if getattr(s, "is_static", False) and env.lookup(s.name) is not None:
            return
        if getattr(s, "is_const", False):
            if s.init is None:
                raise StaticTypeError(f"const 变量 {s.name!r} 必须初始化")
            if not _is_literal_init_expr(s.init):
                raise StaticTypeError(f"const 变量 {s.name!r} 仅支持字面量初始化")
        if getattr(s, "is_constexpr", False) and s.init is None:
            raise StaticTypeError(f"constexpr 变量 {s.name!r} 必须初始化")
        if getattr(s, "array_size_expr", None) is not None:
            st = _expr_type(s.array_size_expr, env, func_sigs)
            if st != "int":
                raise StaticTypeError(f"数组 {s.name!r} 的大小表达式必须为 int，得到 {st}")
        if s.typ == "auto":
            if s.init is None:
                raise StaticTypeError(f"auto 变量 {s.name!r} 必须提供初始化表达式")
            rt = _expr_type(s.init, env, func_sigs)
            env.declare(s.name, rt)
            if getattr(s, "is_const", False):
                env.mark_const(s.name)
            return
        if s.typ.endswith("&"):
            if s.init is None:
                raise StaticTypeError("引用类型变量必须初始化")
            if not isinstance(s.init, VariableLoadNode):
                raise StaticTypeError("引用初始化须为变量名")
            target_t = env.lookup(s.init.name)
            if target_t is None:
                raise StaticTypeError(f"引用目标 {s.init.name!r} 未声明")
            if _reference_base_type(target_t) != _reference_base_type(s.typ):
                raise StaticTypeError(f"引用类型 {s.typ} 与目标变量类型 {target_t} 不匹配")
            env.declare(s.name, s.typ)
            return
        if s.init is not None:
            rt = _expr_type(s.init, env, func_sigs)
            if rt != s.typ:
                raise StaticTypeError(f"变量 {s.name!r} 声明为 {s.typ}，初始化表达式为 {rt}")
        env.declare(s.name, s.typ)
        if getattr(s, "is_const", False):
            env.mark_const(s.name)
        return

    if isinstance(s, ScopedVarDeclNode):
        k = scoped_key(s.scope, s.name)
        if getattr(s, "array_size_expr", None) is not None:
            st = _expr_type(s.array_size_expr, env, func_sigs)
            if st != "int":
                raise StaticTypeError(f"数组 {k!r} 的大小表达式必须为 int，得到 {st}")
        if (getattr(s, "is_const", False) or getattr(s, "is_constexpr", False)) and not top_level:
            raise StaticTypeError(
                f"{'const' if getattr(s, 'is_const', False) else 'constexpr'} 变量必须定义在全局作用域"
            )
        if getattr(s, "is_static", False) and env.lookup(k) is not None:
            return
        if getattr(s, "is_const", False):
            if s.init is None:
                raise StaticTypeError(f"const 变量 {k!r} 必须初始化")
            if not _is_literal_init_expr(s.init):
                raise StaticTypeError(f"const 变量 {k!r} 仅支持字面量初始化")
        if getattr(s, "is_constexpr", False) and s.init is None:
            raise StaticTypeError(f"constexpr 变量 {k!r} 必须初始化")
        if s.typ == "auto":
            if s.init is None:
                raise StaticTypeError(f"auto 变量 {k!r} 必须提供初始化表达式")
            rt = _expr_type(s.init, env, func_sigs)
            env.declare(k, rt)
            if getattr(s, "is_const", False):
                env.mark_const(k)
            if s.scope in ("global", "local") and env.lookup(s.name) is None:
                env.scopes[-1][s.name] = rt
            return
        if s.typ.endswith("&"):
            if s.init is None:
                raise StaticTypeError("引用类型变量必须初始化")
            if not isinstance(s.init, VariableLoadNode):
                raise StaticTypeError("引用初始化须为变量名")
            target_t = env.lookup(s.init.name)
            if target_t is None:
                raise StaticTypeError(f"引用目标 {s.init.name!r} 未声明")
            if _reference_base_type(target_t) != _reference_base_type(s.typ):
                raise StaticTypeError(f"引用类型 {s.typ} 与目标变量类型 {target_t} 不匹配")
            env.declare(k, s.typ)
            if s.scope in ("global", "local") and env.lookup(s.name) is None:
                env.scopes[-1][s.name] = s.typ
            return
        if s.init is not None:
            rt = _expr_type(s.init, env, func_sigs)
            if rt != s.typ:
                raise StaticTypeError(f"变量 {k!r} 声明为 {s.typ}，初始化表达式为 {rt}")
        env.declare(k, s.typ)
        if getattr(s, "is_const", False):
            env.mark_const(k)
        if s.scope in ("global", "local") and env.lookup(s.name) is None:
            env.scopes[-1][s.name] = s.typ
        return

    if isinstance(s, AssignStmtNode):
        if s.name in env.const_symbols:
            raise StaticTypeError(f"const 变量 {s.name!r} 不可重新赋值")
        rt = _expr_type(s.value, env, func_sigs)
        cur = env.lookup(s.name)
        if cur is None:
            mt = _lookup_this_member_type(env, s.name)
            if mt is None:
                env.bind_or_check_assign(s.name, rt)
            elif mt != rt:
                raise StaticTypeError(f"this->{s.name} 类型为 {mt}，右侧为 {rt}")
        else:
            env.bind_or_check_assign(s.name, rt)
        return

    if isinstance(s, ScopedAssignStmtNode):
        k = scoped_key(s.scope, s.name)
        if k in env.const_symbols:
            raise StaticTypeError(f"const 变量 {k!r} 不可重新赋值")
        rt = _expr_type(s.value, env, func_sigs)
        cur = env.lookup(k)
        if cur is None:
            st = env.lookup(s.scope)
            if st in ("namespace", "module", "imported"):
                return
            raise StaticTypeError(f"赋值目标 {k!r} 须先有显式类型声明")
        if cur.endswith("&"):
            base = _reference_base_type(cur)
            if rt != base:
                raise StaticTypeError(f"赋值类型不匹配：{k!r} 为引用 {cur}，右侧须为 {base}，得到 {rt}")
            return
        if cur != rt:
            raise StaticTypeError(f"赋值类型不匹配：{k!r} 为 {cur}，右侧为 {rt}")
        return

    if isinstance(s, CompoundAssignStmtNode):
        if s.name in env.const_symbols:
            raise StaticTypeError(f"const 变量 {s.name!r} 不可重新赋值")
        lt = env.lookup(s.name)
        if lt is None:
            lt = _lookup_this_member_type(env, s.name)
            if lt is None:
                raise StaticTypeError(f"复合赋值要求左侧已具类型：{s.name!r}")
        rt = _expr_type(s.rhs, env, func_sigs)
        eff = _reference_base_type(lt) if lt.endswith("&") else lt
        _check_compound(eff, s.op, rt)
        return

    if isinstance(s, ScopedCompoundAssignStmtNode):
        k = scoped_key(s.scope, s.name)
        if k in env.const_symbols:
            raise StaticTypeError(f"const 变量 {k!r} 不可重新赋值")
        lt = env.lookup(k)
        if lt is None:
            raise StaticTypeError(f"复合赋值要求左侧已具类型：{k!r}")
        rt = _expr_type(s.rhs, env, func_sigs)
        eff = _reference_base_type(lt) if lt.endswith("&") else lt
        _check_compound(eff, s.op, rt)
        return

    if isinstance(s, ExprStmtNode):
        _expr_type(s.expr, env, func_sigs)
        return

    if isinstance(s, DerefAssignStmtNode):
        pt = _expr_type(s.ptr_expr, env, func_sigs)
        if not pt.endswith("*"):
            raise StaticTypeError("解引用赋值左侧须为指针类型的值")
        inner_t = pt[:-1]
        rt = _expr_type(s.value, env, func_sigs)
        if rt != inner_t:
            raise StaticTypeError(f"解引用赋值类型不匹配：指向 {inner_t}，右侧为 {rt}")
        return

    if isinstance(s, (BreakStmtNode, ContinueStmtNode)):
        return

    if isinstance(s, ImportStmtNode):
        for _rel_level, mod_name, alias in s.items:
            bind = alias or mod_name.split(".")[-1]
            if env.lookup(bind) is None:
                env.declare(bind, "module")
        return

    if isinstance(s, FromImportStmtNode):
        for name, alias in s.members:
            bind = alias or name
            if env.lookup(bind) is None:
                env.declare(bind, "imported")
        return

    if isinstance(s, NamespaceDefNode):
        if env.lookup(s.name) is None:
            env.declare(s.name, "namespace")
        nenv = TypeEnv(env.class_fields, env.class_methods, env.const_symbols)
        nenv.scopes = [dict(layer) for layer in env.scopes] + [{}]
        for st in s.body_stmts:
            _check_stmt(st, nenv, func_sigs, ret_void, ret_type, top_level=False)
        return

    if isinstance(s, ThrowStmtNode):
        if s.value is not None:
            _expr_type(s.value, env, func_sigs)
        return

    if isinstance(s, ReturnNode):
        if ret_void:
            if s.value is not None:
                raise StaticTypeError("void 函数不得返回值")
            return
        if s.value is None:
            raise StaticTypeError(f"非 void 函数须返回值（期望 {ret_type}）")
        vt = _expr_type(s.value, env, func_sigs)
        if ret_type == "auto":
            return
        if vt == "imported":
            return
        if vt == "bool" and ret_type == "int":
            return
        if vt != ret_type and not (_is_opaque_type(ret_type) and vt == ret_type):
            raise StaticTypeError(f"return 类型期望 {ret_type}，得到 {vt}")
        return

    if isinstance(s, BlockNode):
        env.enter_block()
        for inner in s.statements:
            _check_stmt(inner, env, func_sigs, ret_void, ret_type, top_level=False)
        env.leave_block()
        return

    if isinstance(s, (IfStmtNode, WhileStmtNode)):
        if isinstance(s, IfStmtNode):
            for cond, blk in s.branches:
                _expr_type(cond, env, func_sigs)
                _check_stmt(blk, env, func_sigs, ret_void, ret_type, top_level=False)
            if s.else_block is not None:
                _check_stmt(s.else_block, env, func_sigs, ret_void, ret_type, top_level=False)
            return
        _expr_type(s.cond, env, func_sigs)
        _check_stmt(s.body, env, func_sigs, ret_void, ret_type, top_level=False)
        return

    if isinstance(s, ForCStmtNode):
        if s.init is not None:
            _check_stmt(s.init, env, func_sigs, ret_void, ret_type, top_level=False)
        if s.cond is not None:
            _expr_type(s.cond, env, func_sigs)
        if s.step is not None:
            _check_stmt(s.step, env, func_sigs, ret_void, ret_type, top_level=False)
        _check_stmt(s.body, env, func_sigs, ret_void, ret_type, top_level=False)
        return

    if isinstance(s, ForRangeStmtNode):
        _expr_type(s.iterable_expr, env, func_sigs)
        env.enter_block()
        env.declare(s.var_name, s.elem_type)
        for inner in s.body.statements:
            _check_stmt(inner, env, func_sigs, ret_void, ret_type, top_level=False)
        env.leave_block()
        return

    if isinstance(s, SwitchStmtNode):
        _expr_type(s.disc, env, func_sigs)
        for ce, blk in s.cases:
            _expr_type(ce, env, func_sigs)
            _check_stmt(blk, env, func_sigs, ret_void, ret_type, top_level=False)
        if s.else_block is not None:
            _check_stmt(s.else_block, env, func_sigs, ret_void, ret_type, top_level=False)
        return

    if isinstance(s, TryStmtNode):
        _check_stmt(s.try_block, env, func_sigs, ret_void, ret_type, top_level=False)
        for type_name, bind_name, blk in s.catches:
            env.enter_block()
            if bind_name is not None:
                env.declare(bind_name, type_name or "Exceptions")
            _check_stmt(blk, env, func_sigs, ret_void, ret_type, top_level=False)
            env.leave_block()
        if s.else_block is not None:
            _check_stmt(s.else_block, env, func_sigs, ret_void, ret_type, top_level=False)
        if s.finally_block is not None:
            _check_stmt(s.finally_block, env, func_sigs, ret_void, ret_type, top_level=False)
        return

    if isinstance(s, FunctionDefNode):
        if getattr(s, "is_constexpr", False) and not top_level:
            raise StaticTypeError("constexpr 函数必须定义在全局作用域")
        _check_one_function(s, func_sigs, _snapshot_type_env(env), implicit_this=True, type_meta=env)
        return

    if isinstance(s, TemplateFunctionDefNode):
        if getattr(s.inner, "is_constexpr", False) and not top_level:
            raise StaticTypeError("constexpr 函数必须定义在全局作用域")
        _check_one_function(s.inner, func_sigs, _snapshot_type_env(env), implicit_this=True, type_meta=env)
        return

    if isinstance(s, ClassDefNode):
        env.declare(s.name, s.name)
        cenv = TypeEnv(env.class_fields, env.class_methods, env.const_symbols)
        cenv.scopes[0]["this"] = s.name
        for m in s.member_stmts:
            _check_stmt(m, cenv, func_sigs, True, "void", top_level=False)
        return

    if isinstance(s, StructDefNode):
        env.declare(s.name, s.name)
        senv = TypeEnv(env.class_fields, env.class_methods, env.const_symbols)
        senv.scopes[0]["this"] = s.name
        for m in s.member_stmts:
            if not isinstance(m, VarDeclNode):
                raise StaticTypeError("struct 内仅允许字段声明")
            _check_stmt(m, senv, func_sigs, True, "void", top_level=False)
        return

    if isinstance(s, DeleteStmtNode):
        for name in s.names:
            if name in env.const_symbols:
                raise StaticTypeError(f"const 变量 {name!r} 不可删除")
            if any(k.endswith(f"::{name}") for k in env.const_symbols):
                raise StaticTypeError(f"const 变量 {name!r} 不可删除")
        return

    if isinstance(s, VarScopeOrderStmtNode):
        return

    raise StaticTypeError(f"静态类型检查不支持的语句：{type(s).__name__}")


def _check_one_function(
    fn: FunctionDefNode,
    func_sigs: dict[str, list[FuncSig]],
    module_bindings: dict[str, str],
    implicit_this: bool = False,
    type_meta: TypeEnv | None = None,
) -> None:
    if fn.type_param_names:
        return
    if type_meta is not None:
        env = TypeEnv(type_meta.class_fields, type_meta.class_methods, type_meta.const_symbols)
    else:
        env = TypeEnv()
    env.scopes[0].update(module_bindings)
    env.enter_block()
    for pt, pn in zip(fn.param_types, fn.param_names, strict=False):
        env.declare(pn, pt)
    if implicit_this and env.lookup("this") is None:
        env.scopes[-1]["this"] = "instance"
    ret_void = fn.returns_void
    ret_type = "void" if ret_void else fn.return_type
    for st in fn.body.statements:
        _check_stmt(st, env, func_sigs, ret_void, ret_type, top_level=False)


class _ConstexprReturn(Exception):
    def __init__(self, value):
        self.value = value


def _const_value_to_expr(v):
    if isinstance(v, bool):
        return BoolLiteralNode(v)
    if isinstance(v, int):
        return LiteralsNode(str(v))
    if isinstance(v, float):
        return LiteralsNode(str(v))
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return LiteralsNode(f'"{esc}"')
    if isinstance(v, list):
        return ArrayLiteralNode([_const_value_to_expr(x) for x in v])
    return ConstValueNode(v)


def _eval_constexpr_expr(
    e: ASTNode,
    cvals: dict[str, object],
    cfuncs: dict[str, FunctionDefNode],
    locals_env: dict[str, object],
):
    if isinstance(e, ConstValueNode):
        return e.value
    if isinstance(e, BoolLiteralNode):
        return e.value
    if isinstance(e, LiteralsNode):
        return e.value
    if isinstance(e, ArrayLiteralNode):
        return [_eval_constexpr_expr(x, cvals, cfuncs, locals_env) for x in e.elements]
    if isinstance(e, VariableLoadNode):
        if e.name in locals_env:
            return locals_env[e.name]
        if e.name in cvals:
            return cvals[e.name]
        raise StaticTypeError(f"constexpr 表达式中使用了运行时变量 {e.name!r}")
    if isinstance(e, ScopedLoadNode):
        k = scoped_key(e.scope, e.name)
        if k in cvals:
            return cvals[k]
        raise StaticTypeError(f"constexpr 表达式中使用了运行时作用域变量 {k!r}")
    if isinstance(e, UnaryOpNode):
        iv = _eval_constexpr_expr(e.value, cvals, cfuncs, locals_env)
        if e.op == UnaryOperator.lnot:
            return bool(not iv)
        if e.op == UnaryOperator.neg:
            return -iv
        if e.op == UnaryOperator.bitnot:
            return ~iv
        raise StaticTypeError("constexpr 不支持该一元运算")
    if isinstance(e, BinOpNode):
        lv = _eval_constexpr_expr(e.left, cvals, cfuncs, locals_env)
        if e.op == BinOperator.land:
            return bool(lv and _eval_constexpr_expr(e.right, cvals, cfuncs, locals_env))
        if e.op == BinOperator.lor:
            return bool(lv or _eval_constexpr_expr(e.right, cvals, cfuncs, locals_env))
        rv = _eval_constexpr_expr(e.right, cvals, cfuncs, locals_env)
        if e.op == BinOperator.add:
            return lv + rv
        if e.op == BinOperator.sub:
            return lv - rv
        if e.op == BinOperator.mul:
            return lv * rv
        if e.op == BinOperator.div:
            return lv // rv if isinstance(lv, int) and isinstance(rv, int) else lv / rv
        if e.op == BinOperator.mod:
            return lv % rv
        if e.op == BinOperator.bitxor:
            return lv ^ rv
        if e.op == BinOperator.bitand:
            return lv & rv
        if e.op == BinOperator.bitor:
            return lv | rv
        if e.op == BinOperator.shl:
            return lv << rv
        if e.op == BinOperator.shr:
            return lv >> rv
        if e.op == BinOperator.lt:
            return lv < rv
        if e.op == BinOperator.le:
            return lv <= rv
        if e.op == BinOperator.gt:
            return lv > rv
        if e.op == BinOperator.ge:
            return lv >= rv
        if e.op == BinOperator.eq:
            return lv == rv
        if e.op == BinOperator.ne:
            return lv != rv
        raise StaticTypeError("constexpr 不支持该二元运算")
    if isinstance(e, FunctionCallNode):
        if not isinstance(e.func, VariableLoadNode):
            raise StaticTypeError("constexpr 仅支持调用裸名 constexpr 函数")
        fname = e.func.name
        if fname not in cfuncs:
            raise StaticTypeError(f"constexpr 调用目标 {fname!r} 不是 constexpr 函数")
        args_val = [_eval_constexpr_expr(a, cvals, cfuncs, locals_env) for a in e.args]
        kwargs_val = {k: _eval_constexpr_expr(v, cvals, cfuncs, locals_env) for k, v in e.kwargs.items()}
        return _eval_constexpr_function(cfuncs[fname], args_val, kwargs_val, cvals, cfuncs)
    raise StaticTypeError(f"constexpr 不支持的表达式：{type(e).__name__}")


def _eval_constexpr_stmt(st: ASTNode, cvals: dict[str, object], cfuncs: dict[str, FunctionDefNode], env: dict[str, object]):
    if isinstance(st, VarDeclNode):
        if st.init is None:
            if st.typ == "int":
                env[st.name] = 0
            elif st.typ == "float":
                env[st.name] = 0.0
            elif st.typ == "bool":
                env[st.name] = False
            elif st.typ == "string":
                env[st.name] = ""
            elif st.typ == "array":
                env[st.name] = []
            else:
                raise StaticTypeError(f"constexpr 函数内无法默认构造类型 {st.typ!r}")
        else:
            env[st.name] = _eval_constexpr_expr(st.init, cvals, cfuncs, env)
        return
    if isinstance(st, AssignStmtNode):
        if st.name not in env:
            raise StaticTypeError(f"constexpr 函数内赋值目标 {st.name!r} 未声明")
        env[st.name] = _eval_constexpr_expr(st.value, cvals, cfuncs, env)
        return
    if isinstance(st, ExprStmtNode):
        _eval_constexpr_expr(st.expr, cvals, cfuncs, env)
        return
    if isinstance(st, ReturnNode):
        rv = None if st.value is None else _eval_constexpr_expr(st.value, cvals, cfuncs, env)
        raise _ConstexprReturn(rv)
    if isinstance(st, BlockNode):
        for inner in st.statements:
            _eval_constexpr_stmt(inner, cvals, cfuncs, env)
        return
    if isinstance(st, IfStmtNode):
        for cond, blk in st.branches:
            if bool(_eval_constexpr_expr(cond, cvals, cfuncs, env)):
                _eval_constexpr_stmt(blk, cvals, cfuncs, env)
                return
        if st.else_block is not None:
            _eval_constexpr_stmt(st.else_block, cvals, cfuncs, env)
        return
    raise StaticTypeError(f"constexpr 函数体不支持语句：{type(st).__name__}")


def _eval_constexpr_function(
    fn: FunctionDefNode,
    args: list[object],
    kwargs: dict[str, object],
    cvals: dict[str, object],
    cfuncs: dict[str, FunctionDefNode],
):
    env: dict[str, object] = {}
    pnames = list(fn.param_names)
    if len(args) > len(pnames):
        raise StaticTypeError(f"constexpr 调用 {fn.name!r} 参数过多")
    for i, a in enumerate(args):
        env[pnames[i]] = a
    for k, v in kwargs.items():
        if k not in pnames:
            raise StaticTypeError(f"constexpr 调用 {fn.name!r} 无参数 {k!r}")
        if k in env:
            raise StaticTypeError(f"constexpr 调用 {fn.name!r} 重复参数 {k!r}")
        env[k] = v
    for pn in pnames:
        if pn not in env:
            raise StaticTypeError(f"constexpr 调用 {fn.name!r} 缺少参数 {pn!r}")
    try:
        for st in fn.body.statements:
            _eval_constexpr_stmt(st, cvals, cfuncs, env)
    except _ConstexprReturn as r:
        return r.value
    return None


def _fold_constexpr_expr(e: ASTNode, cvals: dict[str, object], cfuncs: dict[str, FunctionDefNode]) -> ASTNode:
    if isinstance(e, (LiteralsNode, BoolLiteralNode, ConstValueNode)):
        return e
    if isinstance(e, VariableLoadNode):
        if e.name in cvals:
            return _const_value_to_expr(cvals[e.name])
        return e
    if isinstance(e, ScopedLoadNode):
        k = scoped_key(e.scope, e.name)
        if k in cvals:
            return _const_value_to_expr(cvals[k])
        return e
    if isinstance(e, ArrayLiteralNode):
        e.elements = [_fold_constexpr_expr(x, cvals, cfuncs) for x in e.elements]
        return e
    if isinstance(e, UnaryOpNode):
        e.value = _fold_constexpr_expr(e.value, cvals, cfuncs)
    elif isinstance(e, BinOpNode):
        e.left = _fold_constexpr_expr(e.left, cvals, cfuncs)
        e.right = _fold_constexpr_expr(e.right, cvals, cfuncs)
    elif isinstance(e, FunctionCallNode):
        e.func = _fold_constexpr_expr(e.func, cvals, cfuncs)
        e.args = [_fold_constexpr_expr(a, cvals, cfuncs) for a in e.args]
        e.kwargs = {k: _fold_constexpr_expr(v, cvals, cfuncs) for k, v in e.kwargs.items()}
        if isinstance(e.func, VariableLoadNode) and e.func.name in cfuncs:
            val = _eval_constexpr_expr(e, cvals, cfuncs, {})
            return _const_value_to_expr(val)
    elif isinstance(e, AttributeAccessNode):
        e.obj = _fold_constexpr_expr(e.obj, cvals, cfuncs)
    elif isinstance(e, AttributeStoreNode):
        e.obj = _fold_constexpr_expr(e.obj, cvals, cfuncs)
        e.value = _fold_constexpr_expr(e.value, cvals, cfuncs)
    elif isinstance(e, IndexAccessNode):
        e.obj = _fold_constexpr_expr(e.obj, cvals, cfuncs)
        e.index = _fold_constexpr_expr(e.index, cvals, cfuncs)
    elif isinstance(e, IndexStoreNode):
        e.obj = _fold_constexpr_expr(e.obj, cvals, cfuncs)
        e.index = _fold_constexpr_expr(e.index, cvals, cfuncs)
        e.value = _fold_constexpr_expr(e.value, cvals, cfuncs)
    try:
        v = _eval_constexpr_expr(e, cvals, cfuncs, {})
        return _const_value_to_expr(v)
    except StaticTypeError:
        return e


def _fold_constexpr_stmt(s: ASTNode, cvals: dict[str, object], cfuncs: dict[str, FunctionDefNode]) -> None:
    if isinstance(s, VarDeclNode):
        if s.init is not None:
            s.init = _fold_constexpr_expr(s.init, cvals, cfuncs)
        return
    if isinstance(s, ScopedVarDeclNode):
        if s.init is not None:
            s.init = _fold_constexpr_expr(s.init, cvals, cfuncs)
        return
    if isinstance(s, AssignStmtNode):
        s.value = _fold_constexpr_expr(s.value, cvals, cfuncs)
        return
    if isinstance(s, ScopedAssignStmtNode):
        s.value = _fold_constexpr_expr(s.value, cvals, cfuncs)
        return
    if isinstance(s, CompoundAssignStmtNode):
        s.rhs = _fold_constexpr_expr(s.rhs, cvals, cfuncs)
        return
    if isinstance(s, ScopedCompoundAssignStmtNode):
        s.rhs = _fold_constexpr_expr(s.rhs, cvals, cfuncs)
        return
    if isinstance(s, ExprStmtNode):
        s.expr = _fold_constexpr_expr(s.expr, cvals, cfuncs)
        return
    if isinstance(s, ThrowStmtNode):
        if s.value is not None:
            s.value = _fold_constexpr_expr(s.value, cvals, cfuncs)
        return
    if isinstance(s, ReturnNode):
        if s.value is not None:
            s.value = _fold_constexpr_expr(s.value, cvals, cfuncs)
        return
    if isinstance(s, IfStmtNode):
        s.branches = [(_fold_constexpr_expr(c, cvals, cfuncs), b) for c, b in s.branches]
        for _, b in s.branches:
            _fold_constexpr_stmt(b, cvals, cfuncs)
        if s.else_block is not None:
            _fold_constexpr_stmt(s.else_block, cvals, cfuncs)
        return
    if isinstance(s, WhileStmtNode):
        s.cond = _fold_constexpr_expr(s.cond, cvals, cfuncs)
        _fold_constexpr_stmt(s.body, cvals, cfuncs)
        return
    if isinstance(s, ForCStmtNode):
        if s.init is not None:
            _fold_constexpr_stmt(s.init, cvals, cfuncs)
        if s.cond is not None:
            s.cond = _fold_constexpr_expr(s.cond, cvals, cfuncs)
        if s.step is not None:
            _fold_constexpr_stmt(s.step, cvals, cfuncs)
        _fold_constexpr_stmt(s.body, cvals, cfuncs)
        return
    if isinstance(s, ForRangeStmtNode):
        s.iterable_expr = _fold_constexpr_expr(s.iterable_expr, cvals, cfuncs)
        _fold_constexpr_stmt(s.body, cvals, cfuncs)
        return
    if isinstance(s, SwitchStmtNode):
        s.disc = _fold_constexpr_expr(s.disc, cvals, cfuncs)
        s.cases = [(_fold_constexpr_expr(c, cvals, cfuncs), b) for c, b in s.cases]
        for _, b in s.cases:
            _fold_constexpr_stmt(b, cvals, cfuncs)
        if s.else_block is not None:
            _fold_constexpr_stmt(s.else_block, cvals, cfuncs)
        return
    if isinstance(s, TryStmtNode):
        _fold_constexpr_stmt(s.try_block, cvals, cfuncs)
        for i, (tn, bn, blk) in enumerate(s.catches):
            _fold_constexpr_stmt(blk, cvals, cfuncs)
            s.catches[i] = (tn, bn, blk)
        if s.else_block is not None:
            _fold_constexpr_stmt(s.else_block, cvals, cfuncs)
        if s.finally_block is not None:
            _fold_constexpr_stmt(s.finally_block, cvals, cfuncs)
        return
    if isinstance(s, BlockNode):
        for st in s.statements:
            _fold_constexpr_stmt(st, cvals, cfuncs)
        return
    if isinstance(s, FunctionDefNode):
        for st in s.body.statements:
            _fold_constexpr_stmt(st, cvals, cfuncs)
        return
    if isinstance(s, TemplateFunctionDefNode):
        _fold_constexpr_stmt(s.inner, cvals, cfuncs)
        return
    if isinstance(s, ClassDefNode):
        for st in s.member_stmts:
            _fold_constexpr_stmt(st, cvals, cfuncs)
        return
    if isinstance(s, StructDefNode):
        for st in s.member_stmts:
            _fold_constexpr_stmt(st, cvals, cfuncs)
        return


def _constexpr_fold_module(mod: Module) -> None:
    stmts = mod.body.statements
    cfuncs: dict[str, FunctionDefNode] = {}
    for s in stmts:
        if isinstance(s, FunctionDefNode) and getattr(s, "is_constexpr", False):
            cfuncs[s.name] = s
        elif isinstance(s, TemplateFunctionDefNode) and getattr(s.inner, "is_constexpr", False):
            cfuncs[s.inner.name] = s.inner
    cvals: dict[str, object] = {}
    for s in stmts:
        if isinstance(s, VarDeclNode) and getattr(s, "is_constexpr", False):
            if s.init is None:
                raise StaticTypeError(f"constexpr 变量 {s.name!r} 必须初始化")
            v = _eval_constexpr_expr(s.init, cvals, cfuncs, {})
            cvals[s.name] = v
            s.init = _const_value_to_expr(v)
        elif isinstance(s, ScopedVarDeclNode) and getattr(s, "is_constexpr", False):
            if s.init is None:
                raise StaticTypeError(f"constexpr 变量 {scoped_key(s.scope, s.name)!r} 必须初始化")
            v = _eval_constexpr_expr(s.init, cvals, cfuncs, {})
            cvals[scoped_key(s.scope, s.name)] = v
            s.init = _const_value_to_expr(v)
    for s in stmts:
        _fold_constexpr_stmt(s, cvals, cfuncs)


def check_module_static_types(mod: Module) -> None:
    stmts = mod.body.statements
    for s in stmts:
        if isinstance(s, VarDeclNode) and getattr(s, "is_const", False):
            if s.init is None:
                raise StaticTypeError(f"const 变量 {s.name!r} 必须初始化")
            if not _is_literal_init_expr(s.init):
                raise StaticTypeError(f"const 变量 {s.name!r} 仅支持字面量初始化")
        if isinstance(s, ScopedVarDeclNode) and getattr(s, "is_const", False):
            k = scoped_key(s.scope, s.name)
            if s.init is None:
                raise StaticTypeError(f"const 变量 {k!r} 必须初始化")
            if not _is_literal_init_expr(s.init):
                raise StaticTypeError(f"const 变量 {k!r} 仅支持字面量初始化")
    for s in stmts:
        if isinstance(s, VarDeclNode) and getattr(s, "is_constexpr", False) and s.init is None:
            raise StaticTypeError(f"constexpr 变量 {s.name!r} 必须初始化")
        if isinstance(s, ScopedVarDeclNode) and getattr(s, "is_constexpr", False) and s.init is None:
            raise StaticTypeError(f"constexpr 变量 {scoped_key(s.scope, s.name)!r} 必须初始化")
    func_sigs = _collect_func_sigs(stmts)
    cf, cm = _collect_class_layout(stmts)
    module_env = TypeEnv(cf, cm)
    for s in stmts:
        if isinstance(s, (FunctionDefNode, TemplateFunctionDefNode)):
            continue
        _check_stmt(s, module_env, func_sigs, True, "void", top_level=True)

    mod_flat: dict[str, str] = {}
    for layer in module_env.scopes:
        mod_flat.update(layer)

    for s in stmts:
        if isinstance(s, FunctionDefNode):
            _check_one_function(s, func_sigs, mod_flat, type_meta=module_env)
        elif isinstance(s, TemplateFunctionDefNode):
            _check_one_function(s.inner, func_sigs, mod_flat, type_meta=module_env)

    _constexpr_fold_module(mod)
