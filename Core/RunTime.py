from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union

from .common import Unbound, skip_unbound_errors
from .Parser.AST.Base import ASTNode

if TYPE_CHECKING:
    pass

ReturnNode = None

execution_backend = "ast"
jit_mode: bool = False
constexpr_phase: bool = False


@dataclass
class KvalFunction:
    name: str
    param_names: list[str]
    param_types: list[str]
    body: "Body"
    returns_void: bool
    type_param_names: tuple[str, ...] = ()
    asm_insns: list | None = None
    is_constexpr: bool = False
    owner_class: str | None = None

    def __call__(self, *args, **kwargs):
        from .Errors.Signals import ReturnSignal
        from .VM.insn_vm import InsnVM

        kval_this = kwargs.pop("_kval_this", None)
        parent_sf = stack[-1]
        fr = Frame(
            f_body=self.body,
            f_globals=parent_sf.frame.f_globals,
            f_locals={},
            f_builtins=parent_sf.frame.f_builtins,
            f_closure=[parent_sf.frame],
            f_back=parent_sf.frame,
            f_var_scope=dict(parent_sf.frame.f_var_scope),
            f_var_order={k: list(v) for k, v in parent_sf.frame.f_var_order.items()},
            declared_locals=set(),
            f_current_class=self.owner_class,
        )
        if kval_this is not None:
            fr.f_locals["this"] = kval_this
            fr.declared_locals.add("this")
            if self.owner_class:
                fr.f_locals["base"] = KvalBasePointer(kval_this, self.owner_class)
                fr.declared_locals.add("base")
        for n in self.param_names:
            fr.declared_locals.add(n)
        for n, v in zip(self.param_names, args):
            kwargs[n] = v
        for n in self.param_names:
            if n in kwargs:
                fr.f_locals[n] = kwargs[n]
        child_sf = StackFrame(fr, self.name, parent_sf.module)
        self.body.sf = child_sf
        stack.append(child_sf)
        ret = 0
        try:
            # JIT: 优先走 asm 指令路径；若能力不足/语义不匹配则自动回退 AST。
            if self.asm_insns is not None and (execution_backend == "asm" or jit_mode):
                try:
                    InsnVM(self.asm_insns, child_sf).run()
                except (NotImplementedError, TypeError, ValueError, KeyError):
                    self.body.evaluate()
            else:
                self.body.evaluate()
        except ReturnSignal as e:
            ret = e.value
        except BaseException as e:
            if not hasattr(e, "_kval_stack_snapshot"):
                setattr(e, "_kval_stack_snapshot", capture_call_stack())
            raise
        finally:
            stack.pop()
        return ret


class KvalOverloadGroup:
    """同名函数重载：按实参个数与关键字在候选 `KvalFunction` 中选唯一匹配。"""

    __slots__ = ("fns",)

    def __init__(self, *fns: KvalFunction):
        self.fns = list(fns)

    def add(self, fn: KvalFunction) -> None:
        self.fns.append(fn)

    @staticmethod
    def _matches_candidate(fn: KvalFunction, args: tuple, kwargs: dict) -> bool:
        pts = list(fn.param_types)
        pns = list(fn.param_names)
        has_star = bool(pts) and pts[-1] == "kwargs"
        core_pn = pns[:-1] if has_star else pns
        assigned: set[str] = set()
        for i, _a in enumerate(args):
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

    def __call__(self, *args, **kwargs):
        kval_this = kwargs.pop("_kval_this", None)
        matches = [fn for fn in self.fns if self._matches_candidate(fn, args, kwargs)]
        if len(matches) == 1:
            if kval_this is not None:
                kwargs["_kval_this"] = kval_this
            return matches[0](*args, **kwargs)
        if not matches:
            raise TypeError("no matching overload")
        raise TypeError(f"ambiguous overload ({len(matches)} matches)")


class Module:
    def __init__(self, body: "Body", lines: list[str], name: str = "__main__", file: str | None = None):
        self.body = body
        self.lines = lines
        self.name = name
        self.file = file
        self.declared_globals: set[str] = set()
        self.declared_builtins: set[str] = set()
        self.const_names: set[str] = set()
        self.const_scoped_names: set[str] = set()
        self.static_local_live: set[str] = set()
        self.static_scoped_live: set[str] = set()
        self.constexpr_names: set[str] = set()
        self.constexpr_functions: set[str] = set()
        self.export_names_marked: set[str] = set()

    def evaluate(self):
        return self.body.evaluate()

    def bytecode(self):
        return self.body.bytecode()

    def asm_text(self) -> str:
        from .Parser.AST.asm_ir import AsmContext, format_insns

        ctx = AsmContext()
        return format_insns(self.body.asm(ctx))


class Body:
    def __init__(self, statements: list[ASTNode], sf: Optional["StackFrame"] = None):
        self.statements = list(statements)
        self.sf = sf

    def evaluate(self):
        stack.append(self.sf)
        try:
            for statement in self.statements:
                if getattr(statement, "_constexpr_done", False):
                    continue
                statement.evaluate()
        except BaseException as e:
            if not hasattr(e, "_kval_stack_snapshot"):
                setattr(e, "_kval_stack_snapshot", capture_call_stack())
            raise
        finally:
            stack.pop()

    def bytecode(self):
        global bodys
        bodys[id(self)] = self
        return [
            *[statement.bytecode() for statement in self.statements],
            [(None, None), (b"RETURN", 1)],
        ]

    def asm(self, ctx=None) -> list:
        from .Parser.AST.asm_ir import AsmContext, Insn

        ctx = ctx or AsmContext()
        out: list[Insn] = []
        for statement in self.statements:
            out.extend(statement.asm(ctx))
        return out

    def __iter__(self):
        return self.statements.__iter__()

    def __len__(self):
        return len(self.statements)

    def __getitem__(self, lineon):
        return self.statements[lineon]


@dataclass
class Frame:
    f_body: Body
    f_globals: dict
    f_locals: dict
    f_builtins: dict = field(default_factory=dict)
    f_closure: list["Frame"] = field(default_factory=list)
    f_back: Optional["Frame"] = None
    f_lineon: int = 0
    f_lineoff: int = 0
    f_bytecode: list | None = None
    f_code: list[str] = field(default_factory=list)
    f_ref: dict[str, dict[str, object]] = field(default_factory=dict)
    f_var_scope: dict[str, str] = field(default_factory=dict)
    f_var_order: dict[str, list[str]] = field(default_factory=dict)
    declared_locals: set[str] = field(default_factory=set)
    f_alias: dict[str, str] = field(default_factory=dict)
    f_current_class: str | None = None

    def __post_init__(self):
        self.f_bytecode = self.f_bytecode or self.f_body.bytecode()


def _closure_frame(self_frame: Frame, layer: int) -> Optional[Frame]:
    """closure{n}：layer 从 1 起为直接外层。"""
    if layer < 1 or layer > len(self_frame.f_closure):
        return None
    return self_frame.f_closure[layer - 1]


def _is_module_like_frame(fr: Frame) -> bool:
    return fr.f_locals is fr.f_globals


def _is_direct_enclosing_closure_cell(sf: "StackFrame", closure: Frame) -> bool:
    """当前栈帧的直接外层（f_back）且非模块帧：视为「非跨函数」闭包单元，可放宽 declared_locals 检查。"""
    back = sf.frame.f_back
    return back is not None and closure is back and not _is_module_like_frame(closure)


def _get_from_scope_dict(sf: "StackFrame", scope: str, layer: int | None, name: str):
    fr = sf.frame
    if scope == "local":
        return fr.f_locals.get(name, Unbound(name))
    if scope == "global":
        return fr.f_globals.get(name, Unbound(name))
    if scope == "builtins":
        return fr.f_builtins.get(name, Unbound(name))
    if scope == "closure":
        cf = _closure_frame(fr, layer or 1)
        if cf is None:
            return Unbound(name)
        return cf.f_locals.get(name, Unbound(name))
    return Unbound(name)


def _set_to_scope_dict(sf: "StackFrame", scope: str, layer: int | None, name: str, value) -> None:
    fr = sf.frame
    if scope == "local":
        fr.f_locals[name] = value
        return
    if scope == "global":
        fr.f_globals[name] = value
        return
    if scope == "builtins":
        fr.f_builtins[name] = value
        return
    if scope == "closure":
        cf = _closure_frame(fr, layer or 1)
        if cf is not None:
            cf.f_locals[name] = value
        return


class StackFrame:
    def __init__(self, frame: Frame, funcname: str = "<module>", module: Module | None = None):
        self.frame = frame
        self.funcname = funcname
        self.module = module

    @property
    def lineon(self):
        return self.frame.f_lineon

    @property
    def code(self):
        return self.frame.f_code

    @property
    def filename(self):
        return self.module.file if self.module else None

    def _at_module_level(self) -> bool:
        return self.funcname == "<module>"

    def register_var_decl(self, name: str, scope_spec: str | None) -> None:
        if scope_spec is None:
            if self._at_module_level() or self.frame.f_locals is self.frame.f_globals:
                self.module.declared_globals.add(name)
            else:
                self.frame.declared_locals.add(name)
            return
        scope, layer = _parse_scope_qualifier(scope_spec)
        if scope == "global":
            self.module.declared_globals.add(name)
        elif scope == "local":
            self.frame.declared_locals.add(name)
        elif scope == "builtins":
            self.module.declared_builtins.add(name)
        elif scope == "closure":
            cf = _closure_frame(self.frame, layer or 1)
            if cf is None:
                raise RuntimeError(f"invalid closure layer for declaring {name!r}")
            cf.declared_locals.add(name)
        else:
            raise RuntimeError(f"unknown scope for declaration: {scope_spec!r}")

    def setvar_decl_local(self, name: str, value) -> None:
        self.frame.f_locals[name] = value

    def _declared_for_scope(self, scope: str, layer: int | None, name: str) -> bool:
        if scope == "local":
            return name in self.frame.declared_locals
        if scope == "global":
            return name in self.module.declared_globals
        if scope == "builtins":
            return name in self.module.declared_builtins
        if scope == "closure":
            cf = _closure_frame(self.frame, layer or 1)
            return cf is not None and name in cf.declared_locals
        return False

    def _undeclared_assign_error(self, name: str) -> NameError:
        return NameError(f"name '{name}' is not declared for assignment; declare with a type first")

    def _resolve_alias(self, name: str) -> str:
        fr = self.frame
        seen: set[str] = set()
        while name in fr.f_alias:
            if name in seen:
                raise RuntimeError(f"circular reference alias involving {name!r}")
            seen.add(name)
            name = fr.f_alias[name]
        return name

    def _this_member_container(self):
        this_obj = self.frame.f_locals.get("this", None)
        if (
            isinstance(this_obj, dict)
            and (this_obj.get("__kclass__") or this_obj.get("__kstruct__"))
            and "members" in this_obj
        ):
            return this_obj["members"]
        return None

    def assign_var(self, name: str, value) -> None:
        name = self._resolve_alias(name)
        if self.module is not None and name in self.module.const_names:
            raise NameError(f"cannot assign to const variable '{name}'")
        if self.module is not None and name in self.module.constexpr_names:
            raise NameError(f"cannot assign to constexpr variable '{name}'")
        if name in self.frame.f_ref:
            self.frame.f_ref[name][name] = value
            return
        if name in self.frame.f_var_scope:
            sc = self.frame.f_var_scope[name]
            scope, layer = _parse_scope_qualifier(sc)
            if not self._declared_for_scope(scope, layer, name):
                raise self._undeclared_assign_error(name)
            _set_to_scope_dict(self, scope, layer, name, value)
            return
        if name in self.frame.f_var_order:
            for sc in self.frame.f_var_order[name]:
                scope, layer = _parse_scope_qualifier(sc)
                v = _get_from_scope_dict(self, scope, layer, name)
                if not isinstance(v, Unbound):
                    if not self._declared_for_scope(scope, layer, name):
                        raise self._undeclared_assign_error(name)
                    _set_to_scope_dict(self, scope, layer, name, value)
                    return
            raise NameError(f"name '{name}' is not bound")
        if name in self.frame.f_locals:
            at_mod = self._at_module_level() or self.frame.f_locals is self.frame.f_globals
            if at_mod:
                if name not in self.module.declared_globals:
                    raise self._undeclared_assign_error(name)
            elif name not in self.frame.declared_locals:
                raise self._undeclared_assign_error(name)
            self.frame.f_locals[name] = value
            return
        for closure in self.frame.f_closure:
            if _is_module_like_frame(closure):
                continue
            if name in closure.f_locals:
                if name not in closure.declared_locals and not _is_direct_enclosing_closure_cell(
                    self, closure
                ):
                    raise self._undeclared_assign_error(name)
                closure.f_locals[name] = value
                return
        if name in self.frame.f_globals:
            if name not in self.module.declared_globals:
                raise self._undeclared_assign_error(name)
            self.frame.f_globals[name] = value
            return
        if name in self.frame.f_builtins:
            if name not in self.module.declared_builtins:
                raise self._undeclared_assign_error(name)
            self.frame.f_builtins[name] = value
            return
        # 类方法内：当普通变量未声明时，允许回退写入 this 成员（仅已有成员名）
        members = self._this_member_container()
        if members is not None and name in members:
            members[name] = value
            return
        raise self._undeclared_assign_error(name)

    def assign_scoped(self, scope_spec: str, name: str, value) -> None:
        if self.module is not None and f"{scope_spec}::{name}" in self.module.const_scoped_names:
            raise NameError(f"cannot assign to const variable '{scope_spec}::{name}'")
        try:
            scope, layer = _parse_scope_qualifier(scope_spec)
            if not self._declared_for_scope(scope, layer, name):
                raise NameError(
                    f"'{scope_spec}::{name}' is not declared for assignment; declare with a type first"
                )
            _set_to_scope_dict(self, scope, layer, name, value)
            return
        except ValueError:
            pass
        ns = self.getvar(scope_spec)
        if isinstance(ns, dict) and ns.get("__knamespace__") and "members" in ns:
            ns["members"][name] = value
            return
        raise NameError(f"name '{scope_spec}::{name}' is not bound")

    def getvar(self, name: str):
        name = self._resolve_alias(name)
        if name in self.frame.f_ref:
            return self.frame.f_ref[name][name]
        if name in self.frame.f_var_scope:
            sc = self.frame.f_var_scope[name]
            scope, layer = _parse_scope_qualifier(sc)
            v = _get_from_scope_dict(self, scope, layer, name)
            return self._maybe_unbound(name, v)
        if name in self.frame.f_var_order:
            for sc in self.frame.f_var_order[name]:
                scope, layer = _parse_scope_qualifier(sc)
                v = _get_from_scope_dict(self, scope, layer, name)
                if not isinstance(v, Unbound):
                    return v
            return self._maybe_unbound(name, Unbound(name))
        if name in self.frame.f_locals:
            return self.frame.f_locals[name]
        for closure in self.frame.f_closure:
            if _is_module_like_frame(closure):
                continue
            if name in closure.f_locals:
                return closure.f_locals[name]
        if name in self.frame.f_globals:
            return self.frame.f_globals[name]
        if name in self.frame.f_builtins:
            return self.frame.f_builtins[name]
        # 类方法内：当普通变量未绑定时，允许回退读取 this 成员
        members = self._this_member_container()
        if members is not None and name in members:
            return members[name]
        return self._maybe_unbound(name, Unbound(name))

    def _maybe_unbound(self, name: str, v):
        if isinstance(v, Unbound) and skip_unbound_errors:
            return v
        if isinstance(v, Unbound):
            raise NameError(f"name '{name}' is not bound")
        return v

    def get_scoped(self, scope_spec: str, name: str):
        try:
            scope, layer = _parse_scope_qualifier(scope_spec)
            v = _get_from_scope_dict(self, scope, layer, name)
            if isinstance(v, Unbound) and skip_unbound_errors:
                return v
            if isinstance(v, Unbound):
                raise NameError(f"name '{scope_spec}::{name}' is not bound")
            return v
        except ValueError:
            pass
        ns = self.getvar(scope_spec)
        if isinstance(ns, dict) and ns.get("__knamespace__") and "members" in ns:
            v = ns["members"].get(name, Unbound(name))
            if isinstance(v, Unbound) and skip_unbound_errors:
                return v
            if isinstance(v, Unbound):
                raise NameError(f"name '{scope_spec}::{name}' is not bound")
            return v
        raise NameError(f"name '{scope_spec}::{name}' is not bound")

    def set_scoped(self, scope_spec: str, name: str, value):
        scope, layer = _parse_scope_qualifier(scope_spec)
        _set_to_scope_dict(self, scope, layer, name, value)


def _parse_scope_qualifier(spec: str) -> tuple[str, int | None]:
    s = spec.strip()
    if s.startswith("closure"):
        rest = s[7:].strip()
        if rest.startswith("{") and rest.endswith("}"):
            try:
                n = int(rest[1:-1].strip())
            except ValueError:
                n = 1
            return "closure", n
        return "closure", 1
    if s in ("local", "global", "builtins"):
        return s, None
    raise ValueError(f"unknown scope {spec!r}")


stack: list[StackFrame] = []
bodys: dict[int, Body] = {}
module_cache: dict[str, dict] = {}
module_loading: set[str] = set()


def format_call_stack() -> str:
    snapshot = capture_call_stack()
    if not snapshot:
        return "  <empty>"
    lines: list[str] = []
    for i, sf in enumerate(reversed(snapshot), start=1):
        fname = sf.funcname
        modf = sf.filename or "<memory>"
        lines.append(f"  #{i} {fname} ({modf})")
    return "\n".join(lines)


def capture_call_stack() -> list[StackFrame]:
    return list(stack)


@dataclass
class KvalBasePointer:
    instance: dict
    owner_class: str


def resolve_base_member(base_ptr: KvalBasePointer, attr: str, sf: StackFrame):
    inst = base_ptr.instance
    mro = list(inst.get("mro", ()))
    if not mro:
        mro = [inst.get("name")]
    if base_ptr.owner_class in mro:
        start = mro.index(base_ptr.owner_class) + 1
    else:
        start = 1
    for cls_name in mro[start:]:
        try:
            cls_obj = sf.getvar(cls_name)
        except Exception:
            continue
        if not (isinstance(cls_obj, dict) and cls_obj.get("__kclass__")):
            continue
        own_members = cls_obj.get("own_members", {})
        if attr not in own_members:
            continue
        acc = cls_obj.get("own_member_access", {}).get(attr, "private")
        if acc == "private":
            continue
        return own_members[attr]
    raise AttributeError(f"base member '{attr}' not found")
