from __future__ import annotations

import copy
from enum import Enum

from ...common import KvalPtr, Unbound, kval_truthy, skip_unbound_errors, unsupported
from ...Types.Base import Object, ObjectAttributeVisitor
from .asm_ir import AsmContext, Insn
from .Base import ASTNode

OAV = type_call = stack = String = Integer = None


def _class_attr_access_allowed(obj: dict, attr: str) -> bool:
    access = obj.get("member_access", {}).get(attr, "public")
    if access == "public":
        return True
    if not stack:
        return False
    sf = stack[-1]
    cur_cls = sf.frame.f_current_class
    if cur_cls is None:
        return False
    owner = obj.get("member_owner", {}).get(attr, obj.get("name"))
    if access == "private":
        return cur_cls == owner
    if access == "protected":
        if cur_cls == owner:
            return True
        cur_anc = set(obj.get("ancestors", set()))
        return owner in cur_anc or cur_cls in cur_anc
    return True


def _is_base_ptr(v) -> bool:
    return hasattr(v, "instance") and hasattr(v, "owner_class") and type(v).__name__ == "KvalBasePointer"


class LiteralsNode(ASTNode):
    def __init__(self, literals: str):
        if literals.startswith('"') and literals.endswith('"'):
            self.value = bytes(literals[1:-1], "utf-8").decode("unicode_escape")
        elif literals.startswith("'") and literals.endswith("'"):
            self.value = bytes(literals[1:-1], "utf-8").decode("unicode_escape")
        else:
            self.value = float(literals) if "." in literals else int(literals)

    def evaluate(self):
        return self.value

    def bytecode(self):
        return [(self.value, None), (b"LOAD_CONST", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("const", self.value)]


class BoolLiteralNode(ASTNode):
    def __init__(self, value: bool):
        self.value = bool(value)

    def evaluate(self):
        return self.value

    def bytecode(self):
        return [(self.value, None), (b"LOAD_CONST", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("const", self.value)]


class ConstValueNode(ASTNode):
    """Compile-time folded constant value (can hold non-literal objects)."""

    def __init__(self, value):
        self.value = value

    def evaluate(self):
        return self.value

    def bytecode(self):
        return [(self.value, None), (b"LOAD_CONST", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("const", self.value)]


class BinOperator(Enum):
    add = (b"ADD", "__add__", "__radd__")
    sub = (b"SUB", "__sub__", "__rsub__")
    mul = (b"MUL", "__mul__", "__rmul__")
    div = (b"DIV", "__truediv__", "__rtruediv__")
    mod = (b"MOD", "__mod__", "__rmod__")
    bitxor = (b"XOR", "__xor__", "__rxor__")
    bitand = (b"AND", "__and__", "__rand__")
    bitor = (b"OR", "__or__", "__ror__")
    shl = (b"SHL", "__lshift__", "__rlshift__")
    shr = (b"SHR", "__rshift__", "__rrshift__")
    lt = (b"LT", "__lt__", "__gt__")
    le = (b"LE", "__le__", "__ge__")
    gt = (b"GT", "__gt__", "__lt__")
    ge = (b"GE", "__ge__", "__le__")
    eq = (b"EQ", "__eq__", "__eq__")
    ne = (b"NE", "__ne__", "__ne__")
    land = (b"LAND", "__land__", "__rland__")
    lor = (b"LOR", "__lor__", "__rlor__")


_KCLASS_OP_MEMBER = {
    BinOperator.add: "__op_add__",
    BinOperator.sub: "__op_sub__",
    BinOperator.mul: "__op_mul__",
    BinOperator.div: "__op_div__",
    BinOperator.mod: "__op_mod__",
}


class BinOpNode(ASTNode):
    def __init__(self, left: ASTNode, op: BinOperator, right: ASTNode):
        self.left = left
        self.op = op
        self.right = right

    def evaluate(self):
        if self.op == BinOperator.land:
            lv = self.left.evaluate()
            if not kval_truthy(lv):
                return False
            rv = self.right.evaluate()
            return bool(kval_truthy(rv))
        if self.op == BinOperator.lor:
            lv = self.left.evaluate()
            if kval_truthy(lv):
                return True
            rv = self.right.evaluate()
            return bool(kval_truthy(rv))
        left_val = self.left.evaluate()
        right_val = self.right.evaluate()
        if isinstance(left_val, dict) and (left_val.get("__kclass__") or left_val.get("__kstruct__")):
            mname = _KCLASS_OP_MEMBER.get(self.op)
            if mname:
                fn = left_val.get("members", {}).get(mname)
                if fn is not None and callable(fn):
                    return fn(left_val, right_val)
        if isinstance(left_val, (int, float, str)) and isinstance(right_val, (int, float, str)):
            return _eval_binop_py(left_val, self.op, right_val)
        left = OAV(left_val)
        right_o = right_val
        result = getattr(left, self.op.value[1], lambda x: unsupported)(right_o)
        if result is unsupported:
            result = getattr(OAV(right_o), self.op.value[2], lambda x: unsupported)(left_val)
        if result is unsupported:
            raise TypeError(f"unsupported binary op {self.op}")
        return result

    def bytecode(self):
        return [
            *self.left.bytecode(),
            *self.right.bytecode(),
            (self.op.value[0], 2),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        # 检测是否为浮点运算
        op_name = self.op.name
        if self._both_floats():
            float_ops = {
                "add": "fadd", "sub": "fsub", "mul": "fmul", "div": "fdiv",
                "lt": "flt", "le": "fle", "gt": "fgt", "ge": "fge",
                "eq": "feq", "ne": "fne",
            }
            op_name = float_ops.get(self.op.name, self.op.name)
        return [
            *self.left.asm(ctx),
            *self.right.asm(ctx),
            ("binop", op_name),
        ]

    def _both_floats(self) -> bool:
        """检测两个操作数是否都为浮点字面量。"""
        return (
            isinstance(self.left, LiteralsNode) and isinstance(self.left.value, float)
            and isinstance(self.right, LiteralsNode) and isinstance(self.right.value, float)
        )


def _eval_binop_py(a, op: BinOperator, b):
    if op == BinOperator.add:
        return a + b
    if op == BinOperator.sub:
        return a - b
    if op == BinOperator.mul:
        return a * b
    if op == BinOperator.div:
        return a // b if isinstance(a, int) and isinstance(b, int) else a / b
    if op == BinOperator.mod:
        return a % b
    if op == BinOperator.bitxor:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("^ requires int operands")
        return a ^ b
    if op == BinOperator.bitand:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("& requires int operands")
        return a & b
    if op == BinOperator.bitor:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("| requires int operands")
        return a | b
    if op == BinOperator.shl:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("<< requires int operands")
        return a << b
    if op == BinOperator.shr:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError(">> requires int operands")
        return a >> b
    if op == BinOperator.lt:
        return a < b
    if op == BinOperator.le:
        return a <= b
    if op == BinOperator.gt:
        return a > b
    if op == BinOperator.ge:
        return a >= b
    if op == BinOperator.eq:
        return a == b
    if op == BinOperator.ne:
        return a != b
    raise TypeError(op)


class UnaryOperator(Enum):
    neg = (b"NEG", "__neg__")
    bitnot = (b"NOT", "__invert__")
    lnot = (b"LNOT", "__lnot__")
    addr = (b"ADDR", "__addr__")
    deref = (b"DEREF", "__deref__")


class UnaryOpNode(ASTNode):
    def __init__(self, op: UnaryOperator, value: ASTNode):
        self.op = op
        self.value = value

    def evaluate(self):
        from ...RunTime import stack as _stack

        if self.op == UnaryOperator.addr:
            if not isinstance(self.value, VariableLoadNode):
                raise TypeError("& 仅可用于简单变量名")
            name = self.value.name
            sf = _stack[-1]

            def _g():
                return sf.getvar(name)

            def _s(v):
                return sf.assign_var(name, v)

            return KvalPtr(_g, _s)
        if self.op == UnaryOperator.deref:
            val = self.value.evaluate()
            if not isinstance(val, KvalPtr):
                raise TypeError("* 的操作数须为指针")
            return val.get()
        val = self.value.evaluate()
        if self.op == UnaryOperator.lnot:
            return bool(not kval_truthy(val))
        if isinstance(val, int):
            if self.op == UnaryOperator.neg:
                return -val
            if self.op == UnaryOperator.bitnot:
                return ~val
        result = getattr(OAV(val), self.op.value[1], lambda: unsupported)()
        if result is unsupported:
            raise TypeError(f"unsupported unary {self.op}")
        return result

    def bytecode(self):
        return [*self.value.bytecode(), (self.op.value[0], 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        op_name = self.op.name
        if self.op == UnaryOperator.neg and isinstance(self.value, LiteralsNode) and isinstance(self.value.value, float):
            op_name = "fneg"
        return [*self.value.asm(ctx), ("unary", op_name)]


class VariableLoadNode(ASTNode):
    def __init__(self, name: str):
        self.name = name

    def evaluate(self):
        global stack
        v = stack[-1].getvar(self.name)
        if isinstance(v, Unbound) and skip_unbound_errors:
            return v
        if isinstance(v, Unbound):
            raise NameError(f"'{self.name}' is not bound")
        return v

    def bytecode(self):
        return [(self.name, None), (b"LOAD_VAR", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("load", self.name)]


class ScopedLoadNode(ASTNode):
    def __init__(self, scope: str, name: str):
        self.scope = scope
        self.name = name

    def evaluate(self):
        return stack[-1].get_scoped(self.scope, self.name)

    def bytecode(self):
        return [(self.scope, self.name), (b"LOAD_SCOPED", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("load_scoped", self.scope, self.name)]


class VariableStoreNode(ASTNode):
    def __init__(self, name: str, value: ASTNode):
        self.name = name
        self.value = value

    def evaluate(self):
        global stack
        stack[-1].assign_var(self.name, self.value.evaluate())
        return None

    def bytecode(self):
        return [(self.name, None), *self.value.bytecode(), (b"STORE_VAR", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.value.asm(ctx), ("store", self.name)]


class ScopedStoreNode(ASTNode):
    def __init__(self, scope: str, name: str, value: ASTNode):
        self.scope = scope
        self.name = name
        self.value = value

    def evaluate(self):
        stack[-1].assign_scoped(self.scope, self.name, self.value.evaluate())
        return None

    def bytecode(self):
        return [(self.scope, self.name), *self.value.bytecode(), (b"STORE_SCOPED", 3)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.value.asm(ctx), ("store_scoped_assign", self.scope, self.name)]


class AttributeAccessNode(ASTNode):
    def __init__(self, obj: ASTNode, attr: str):
        self.obj = obj
        self.attr = attr

    def evaluate(self):
        obj_val = self.obj.evaluate()
        if _is_base_ptr(obj_val):
            from ...RunTime import resolve_base_member

            return resolve_base_member(obj_val, self.attr, stack[-1])
        if isinstance(obj_val, dict) and (obj_val.get("__kclass__") or obj_val.get("__kstruct__")) and "members" in obj_val:
            if obj_val.get("__kclass__") and not _class_attr_access_allowed(obj_val, self.attr):
                raise PermissionError(f"member '{self.attr}' is not accessible")
            return obj_val["members"].get(self.attr, Unbound(self.attr))
        if isinstance(obj_val, dict):
            return obj_val.get(self.attr, Unbound(self.attr))
        return getattr(OAV(obj_val), self.attr)

    def bytecode(self):
        return [*self.obj.bytecode(), (self.attr, None), (b"LOAD_ATTR", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.obj.asm(ctx), ("get_attr", self.attr)]


class AttributeStoreNode(ASTNode):
    def __init__(self, obj: ASTNode, attr: str, value: ASTNode):
        self.obj = obj
        self.attr = attr
        self.value = value

    def evaluate(self):
        obj_val = self.obj.evaluate()
        v = self.value.evaluate()
        if _is_base_ptr(obj_val):
            raise PermissionError("base pointer is read-only")
        if isinstance(obj_val, dict) and (obj_val.get("__kclass__") or obj_val.get("__kstruct__")) and "members" in obj_val:
            if obj_val.get("__kclass__") and not _class_attr_access_allowed(obj_val, self.attr):
                raise PermissionError(f"member '{self.attr}' is not accessible")
            obj_val["members"][self.attr] = v
            return None
        if isinstance(obj_val, dict):
            obj_val[self.attr] = v
        else:
            setattr(OAV(obj_val), self.attr, v)
        return None

    def bytecode(self):
        return [*self.obj.bytecode(), (self.attr, None), *self.value.bytecode(), (b"STORE_ATTR", 3)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.obj.asm(ctx), *self.value.asm(ctx), ("set_attr", self.attr)]


class ArrayLiteralNode(ASTNode):
    def __init__(self, elements: list[ASTNode]):
        self.elements = elements

    def evaluate(self):
        return [e.evaluate() for e in self.elements]

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class IndexAccessNode(ASTNode):
    def __init__(self, obj: ASTNode, index: ASTNode):
        self.obj = obj
        self.index = index

    def evaluate(self):
        ov = self.obj.evaluate()
        iv = self.index.evaluate()
        return ov[iv]

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class IndexStoreNode(ASTNode):
    def __init__(self, obj: ASTNode, index: ASTNode, value: ASTNode):
        self.obj = obj
        self.index = index
        self.value = value

    def evaluate(self):
        ov = self.obj.evaluate()
        iv = self.index.evaluate()
        vv = self.value.evaluate()
        ov[iv] = vv
        return None

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class FunctionCallNode(ASTNode):
    def __init__(self, func: ASTNode, args: list[ASTNode], kwargs: dict[str, ASTNode] | None = None):
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}

    def evaluate(self):
        recv = None
        implicit_this = None
        if isinstance(self.func, AttributeAccessNode):
            recv = self.func.obj.evaluate()
        elif isinstance(self.func, VariableLoadNode):
            try:
                maybe_this = stack[-1].getvar("this")
                if isinstance(maybe_this, dict) and (maybe_this.get("__kclass__") or maybe_this.get("__kstruct__")) and "members" in maybe_this:
                    if self.func.name in maybe_this["members"]:
                        implicit_this = maybe_this
            except Exception:
                implicit_this = None
        func_val = self.func.evaluate()
        args_val = [arg.evaluate() for arg in self.args]
        kwargs_val = {k: v.evaluate() for k, v in self.kwargs.items()}
        if isinstance(self.func, VariableLoadNode):
            fv = func_val
            if isinstance(fv, dict) and fv.get("__kclass__") and "members" in fv:
                cname = self.func.name
                m = fv["members"]
                ctor = m.get(cname)
                if not callable(ctor):
                    ctor = m.get(f"New{cname}")
                if ctor is not None and callable(ctor):
                    inst = {
                        "__kclass__": True,
                        "name": cname,
                        "own_members": copy.copy(fv.get("own_members", {})),
                        "own_member_access": copy.copy(fv.get("own_member_access", {})),
                        "members": copy.copy(fv["members"]),
                        "member_access": copy.copy(fv.get("member_access", {})),
                        "member_owner": copy.copy(fv.get("member_owner", {})),
                        "ancestors": set(fv.get("ancestors", set())),
                        "mro": tuple(fv.get("mro", (cname,))),
                        "bases": tuple(fv.get("bases", ())),
                    }
                    ctor(*args_val, **kwargs_val, _kval_this=inst)
                    return inst
            if isinstance(fv, dict) and fv.get("__kstruct__") and "members" in fv:
                if args_val or kwargs_val:
                    raise TypeError(f"struct '{self.func.name}' constructor does not accept arguments")
                return {"__kstruct__": True, "name": self.func.name, "members": copy.copy(fv["members"])}
        if (
            recv is not None
            and isinstance(recv, dict)
            and (recv.get("__kclass__") or recv.get("__kstruct__"))
            and callable(func_val)
        ):
            return func_val(*args_val, **kwargs_val, _kval_this=recv)
        if implicit_this is not None and callable(func_val):
            return func_val(*args_val, **kwargs_val, _kval_this=implicit_this)
        if callable(func_val):
            return func_val(*args_val, **kwargs_val)
        return OAV(func_val).__call__(*args_val, **kwargs_val)

    def bytecode(self):
        name = getattr(self.func, "name", None)
        return [
            (name, None),
            (b"LOAD_FUNC", 1),
            ([a.bytecode() for a in self.args], None),
            ({k: v.bytecode() for k, v in self.kwargs.items()}, None),
            (b"CALL_FUNC", 3),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        ins: list[Insn] = []
        for a in self.args:
            ins.extend(a.asm(ctx))
        keys = tuple(self.kwargs.keys())
        for k in keys:
            ins.extend(self.kwargs[k].asm(ctx))
        fname = getattr(self.func, "name", None)
        if fname == "range":
            # range(n) → 推入 n 作为上限值（ForRangeStmtNode 使用）
            pass  # 参数已在栈上
        elif fname is not None:
            ins.append(("call", fname, len(self.args), keys))
        else:
            ins.extend(self.func.asm(ctx))
            ins.append(("call_indirect", len(self.args), keys))
        return ins
