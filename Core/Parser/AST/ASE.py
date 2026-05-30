from __future__ import annotations

import copy
import atexit
import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
import sys

from ...RunTime import Body, KvalFunction, KvalOverloadGroup, _is_module_like_frame, stack
from ...common import Unbound, kval_truthy as _kval_truthy

from .asm_ir import AsmContext, Insn, flatten_stmt_asm, insns_to_tuple
from .Base import ASTNode
from .Data import BinOperator, _eval_binop_py

Function = None
ReturnSignal = None


def _expand_kval_iterable(obj):
    if isinstance(obj, (list, tuple, range)):
        return list(obj)
    if isinstance(obj, str):
        return list(obj)
    if isinstance(obj, dict) and obj.get("__kclass__"):
        raise TypeError("iteration over Kval class instance is not implemented yet")
    if hasattr(obj, "__iter__") and not isinstance(obj, dict):
        return list(obj)
    raise TypeError(f"object is not iterable: {type(obj).__name__}")


class ReturnNode(ASTNode):
    def __init__(self, value: ASTNode | None):
        self.value = value

    def evaluate(self):
        v = None
        if self.value is not None:
            v = self.value.evaluate()
        raise ReturnSignal(v)

    def bytecode(self):
        if self.value is None:
            return [(b"RETURN_VOID", 0)]
        return [*self.value.bytecode(), (b"RETURN", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        if self.value is None:
            return [("retvoid",)]
        return [*self.value.asm(ctx), ("ret",)]


class ExprStmtNode(ASTNode):
    def __init__(self, expr: ASTNode):
        self.expr = expr

    def evaluate(self):
        self.expr.evaluate()

    def bytecode(self):
        return [*self.expr.bytecode(), (b"POP", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.expr.asm(ctx), ("pop",)]


class BreakStmtNode(ASTNode):
    def evaluate(self):
        from ...Errors.Signals import BreakSignal

        raise BreakSignal()

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class ContinueStmtNode(ASTNode):
    def evaluate(self):
        from ...Errors.Signals import ContinueSignal

        raise ContinueSignal()

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


def _matches_exception_type(exc: BaseException, type_name: str | None) -> bool:
    if type_name is None:
        return True
    names = [cls.__name__ for cls in type(exc).__mro__]
    return type_name in names


def _default_array_elem_value(elem_type: str):
    if elem_type == "int":
        return 0
    if elem_type == "float":
        return 0.0
    if elem_type == "bool":
        return False
    if elem_type == "string":
        return ""
    return None


class BlockNode(ASTNode):
    def __init__(self, statements: list[ASTNode]):
        self.statements = statements

    def evaluate(self):
        for s in self.statements:
            s.evaluate()

    def bytecode(self):
        return [s.bytecode() for s in self.statements]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        out: list[Insn] = []
        for s in self.statements:
            out.extend(s.asm(ctx))
        return out


class ThrowStmtNode(ASTNode):
    def __init__(self, value: ASTNode | None):
        self.value = value

    def evaluate(self):
        from ...Errors.BaseErrors import Exceptions
        from ...Errors.RunTimeErrors import RunTimeError

        if self.value is None:
            raise RunTimeError("throw 语句缺少异常对象")
        v = self.value.evaluate()
        if isinstance(v, BaseException):
            raise v
        if isinstance(v, Exceptions):
            raise v
        raise RunTimeError(str(v), payload=v)

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class TryStmtNode(ASTNode):
    def __init__(
        self,
        try_block: BlockNode,
        catches: list[tuple[str | None, str | None, BlockNode]],
        else_block: BlockNode | None,
        finally_block: BlockNode | None,
    ):
        self.try_block = try_block
        self.catches = catches
        self.else_block = else_block
        self.finally_block = finally_block

    def evaluate(self):
        from ...Errors.Signals import BreakSignal, ContinueSignal, ReturnSignal

        pending: BaseException | None = None
        try_success = False
        try:
            self.try_block.evaluate()
            try_success = True
        except (ReturnSignal, BreakSignal, ContinueSignal) as sig:
            pending = sig
        except BaseException as exc:
            handled = False
            for type_name, bind_name, block in self.catches:
                if not _matches_exception_type(exc, type_name):
                    continue
                handled = True
                if bind_name:
                    sf = stack[-1]
                    sf.register_var_decl(bind_name, None)
                    sf.setvar_decl_local(bind_name, exc)
                block.evaluate()
                break
            if not handled:
                pending = exc
        finally:
            if self.finally_block is not None:
                self.finally_block.evaluate()
        if pending is not None:
            raise pending
        if try_success and self.else_block is not None:
            self.else_block.evaluate()

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class NamespaceDefNode(ASTNode):
    def __init__(self, name: str, body_stmts: list[ASTNode]):
        self.name = name
        self.body_stmts = body_stmts

    def evaluate(self):
        outer_sf = stack[-1]
        saved_locals = outer_sf.frame.f_locals
        saved_current_class = outer_sf.frame.f_current_class
        outer_sf.frame.f_locals = {}
        outer_sf.frame.f_current_class = None
        try:
            for st in self.body_stmts:
                st.evaluate()
            members = dict(outer_sf.frame.f_locals)
        finally:
            outer_sf.frame.f_locals = saved_locals
            outer_sf.frame.f_current_class = saved_current_class
        outer_sf.register_var_decl(self.name, None)
        outer_sf.setvar_decl_local(self.name, {"__knamespace__": True, "name": self.name, "members": members})

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


_package_destructor_registered: set[str] = set()
_module_meta_cache: dict[str, dict] = {}


def _search_roots() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    return [
        Path.cwd().resolve(),
        (root / "Lib").resolve(),
        (root / "Lib" / "site-packages").resolve(),
        (root / "PyModules").resolve(),
    ]


def _find_package_ancestors(importer_file: str, roots: list[Path]) -> list[Path]:
    p = Path(importer_file).resolve()
    parent = p.parent
    out: list[Path] = []
    for _r in roots:
        cur = parent
        while True:
            init_file = cur / f"{cur.name}.kval"
            if init_file.is_file():
                out.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    # dedupe, keep inner -> outer order
    uniq: list[Path] = []
    for x in out:
        if x not in uniq:
            uniq.append(x)
    uniq.sort(key=lambda t: len(str(t)), reverse=True)
    return uniq


def _resolve_module_file(module_name: str, importer_file: str | None, relative_level: int = 0) -> tuple[Path, str, str]:
    parts = [p for p in module_name.split(".") if p]
    if not parts:
        raise FileNotFoundError("empty module name")
    roots = _search_roots()

    cands: list[tuple[Path, str, str]] = []
    if relative_level > 0:
        if not importer_file:
            raise FileNotFoundError(f"relative import '.{module_name}' requires importer file")
        ancestors = _find_package_ancestors(importer_file, roots)
        idx = relative_level - 1
        if idx >= len(ancestors):
            raise FileNotFoundError(f"relative import level {relative_level} exceeds package depth")
        base = ancestors[idx]
        rel_dir = Path(*parts)
        mod_k = (base / rel_dir).with_suffix(".kval").resolve()
        mod_p = (base / rel_dir).with_suffix(".py").resolve()
        pkg_dir = (base / rel_dir).resolve()
        pkg_init = pkg_dir / f"{pkg_dir.name}.kval"
        cands.extend(
            [
                (mod_k, "kval", module_name),
                (mod_p, "python", module_name),
                (pkg_init, "kpackage", module_name),
            ]
        )
    else:
        rel_dir = Path(*parts)
        for base in roots:
            mod_k = (base / rel_dir).with_suffix(".kval").resolve()
            mod_p = (base / rel_dir).with_suffix(".py").resolve()
            pkg_dir = (base / rel_dir).resolve()
            pkg_init = pkg_dir / f"{pkg_dir.name}.kval"
            cands.extend(
                [
                    (mod_k, "kval", module_name),
                    (mod_p, "python", module_name),
                    (pkg_init, "kpackage", module_name),
                ]
            )
    for p, kind, logical in cands:
        if p.is_file():
            return p, kind, logical
    raise FileNotFoundError(f"module '{module_name}' not found")


def _compute_export_names(mod_obj: dict, marked: set[str]) -> set[str]:
    names = set(marked)
    raw = mod_obj.get("exports", None)
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                names.add(x)
    if names:
        return names
    return {k for k in mod_obj.keys() if not k.startswith("__")}


def _compute_python_export_names(mod: ModuleType, ns: dict) -> set[str]:
    names: set[str] = set()
    explicit = getattr(mod, "__kval_exports__", None)
    if isinstance(explicit, (list, tuple, set)):
        for n in explicit:
            if isinstance(n, str):
                names.add(n)
    bridge_exp = ns.get("exports", None)
    if isinstance(bridge_exp, (list, tuple, set)):
        for n in bridge_exp:
            if isinstance(n, str):
                names.add(n)
    for k, v in ns.items():
        if getattr(v, "__kval_export__", False):
            names.add(k)
    if names:
        return names
    return {k for k in ns.keys() if not k.startswith("_")}


def _load_python_module_exports(module_name: str, path: Path) -> dict:
    spec_name = f"kval_pybridge_{module_name.replace('.', '_')}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(spec_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load python module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ns = dict(vars(mod))
    export_names = _compute_python_export_names(mod, ns)
    out = {n: ns[n] for n in export_names if n in ns}

    # Kval 是强类型语言：导出的 Python 函数必须有完整类型注解（参数+返回值）。
    for name, val in out.items():
        if not callable(val):
            continue
        sig = inspect.signature(val)
        for p in sig.parameters.values():
            if p.annotation is inspect._empty:
                raise TypeError(f"python bridge export '{module_name}.{name}' parameter '{p.name}' missing type annotation")
        if sig.return_annotation is inspect._empty:
            raise TypeError(f"python bridge export '{module_name}.{name}' missing return type annotation")
    return out


def _run_package_destructor(path: Path) -> None:
    try:
        from ..Parser import Parser

        src = path.read_text(encoding="utf-8")
        mod = Parser.parse_source(src, filename=str(path))
        mod.body.evaluate()
    except Exception as e:
        print(f"Traceback (most recent call last):", file=sys.stderr)
        print(f"  File: {path}, Lineon: 0, In <package-destructor>:", file=sys.stderr)
        print("      ", file=sys.stderr)
        print(f"RunTimeError: package destructor failed: {e}", file=sys.stderr)


def _load_kval_package_exports(module_name: str, init_path: Path) -> tuple[dict, set[str]]:
    from ..Parser import Parser

    src = init_path.read_text(encoding="utf-8")
    mod = Parser.parse_source(src, filename=str(init_path))
    mod.body.evaluate()
    g = mod.body.sf.frame.f_globals
    export_names = _compute_export_names(g, mod.export_names_marked)
    ns = {n: g[n] for n in export_names if n in g}
    direct_names: set[str] = set()
    raw = g.get("imports", None)
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                direct_names.add(x)
    dtor = init_path.parent / f"~{init_path.parent.name}.kval"
    dkey = str(dtor.resolve())
    if dtor.is_file() and dkey not in _package_destructor_registered:
        _package_destructor_registered.add(dkey)
        atexit.register(_run_package_destructor, dtor)
    return ns, direct_names


def _load_module_exports(module_name: str, importer_file: str | None, relative_level: int = 0) -> tuple[dict, dict]:
    from ...RunTime import module_cache, module_loading

    path, kind, logical_name = _resolve_module_file(module_name, importer_file, relative_level=relative_level)
    key = f"{kind}:{path.resolve()}"
    if key in module_cache:
        return module_cache[key], _module_meta_cache.get(key, {"is_package": False, "direct_imports": set()})
    if key in module_loading:
        raise RuntimeError(f"circular module import: {module_name}")
    module_loading.add(key)
    try:
        if kind == "python":
            ns = _load_python_module_exports(module_name, path)
            meta = {"is_package": False, "direct_imports": set(), "logical_name": logical_name}
        elif kind == "kpackage":
            ns, direct_names = _load_kval_package_exports(module_name, path)
            meta = {"is_package": True, "direct_imports": direct_names, "logical_name": logical_name}
        else:
            from ..Parser import Parser

            src = path.read_text(encoding="utf-8")
            mod = Parser.parse_source(src, filename=str(path.resolve()))
            mod.body.evaluate()
            g = mod.body.sf.frame.f_globals
            export_names = _compute_export_names(g, mod.export_names_marked)
            ns = {n: g[n] for n in export_names if n in g}
            meta = {"is_package": False, "direct_imports": set(), "logical_name": logical_name}
        module_cache[key] = ns
        _module_meta_cache[key] = meta
        return ns, meta
    finally:
        module_loading.discard(key)


class ImportStmtNode(ASTNode):
    def __init__(self, items: list[tuple[int, str, str | None]]):
        self.items = items

    def evaluate(self):
        sf = stack[-1]
        importer_file = sf.module.file if sf.module is not None else None
        for rel_level, mod_name, alias in self.items:
            ns, _meta = _load_module_exports(mod_name, importer_file, relative_level=rel_level)
            bind = alias or mod_name.split(".")[-1]
            sf.register_var_decl(bind, None)
            sf.setvar_decl_local(bind, dict(ns))

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class FromImportStmtNode(ASTNode):
    def __init__(self, relative_level: int, module_name: str, members: list[tuple[str, str | None]]):
        self.relative_level = relative_level
        self.module_name = module_name
        self.members = members

    def evaluate(self):
        sf = stack[-1]
        importer_file = sf.module.file if sf.module is not None else None
        ns, meta = _load_module_exports(self.module_name, importer_file, relative_level=self.relative_level)
        for name, alias in self.members:
            bind = alias or name
            if name in ns and (not meta.get("is_package") or name in meta.get("direct_imports", set())):
                sf.register_var_decl(bind, None)
                sf.setvar_decl_local(bind, ns[name])
                continue
            if meta.get("is_package"):
                sub_name = f"{self.module_name}.{name}"
                sub_ns, _ = _load_module_exports(sub_name, importer_file, relative_level=0)
                sf.register_var_decl(bind, None)
                sf.setvar_decl_local(bind, sub_ns)
                continue
            raise NameError(f"module '{self.module_name}' has no exported member '{name}'")

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class VarDeclNode(ASTNode):
    def __init__(
        self,
        typ: str,
        name: str,
        init: ASTNode | None = None,
        array_size_expr: ASTNode | None = None,
        array_elem_type: str | None = None,
        is_constexpr: bool = False,
        is_const: bool = False,
        is_static: bool = False,
    ):
        self.typ = typ
        self.name = name
        self.init = init
        self.array_size_expr = array_size_expr
        self.array_elem_type = array_elem_type
        self.is_constexpr = is_constexpr
        self.is_const = is_const
        self.is_static = is_static

    def evaluate(self):
        from .Data import VariableLoadNode

        sf = stack[-1]
        if getattr(self, "_is_export", False) and sf.module is not None:
            sf.module.export_names_marked.add(self.name)
        if self.is_static and sf.module is not None:
            sk = f"{id(sf.frame)}::{self.name}"
            if sk in sf.module.static_local_live:
                return
            sf.module.static_local_live.add(sk)
        sf.register_var_decl(self.name, None)
        if self.is_const:
            if self.init is None:
                raise RuntimeError("const 变量必须初始化")
            if sf.module is not None:
                sf.module.const_names.add(self.name)
        if self.is_constexpr:
            if self.init is None:
                raise RuntimeError("constexpr 变量必须初始化")
            if sf.module is not None:
                sf.module.constexpr_names.add(self.name)
        if self.typ == "auto":
            if self.init is None:
                raise RuntimeError("auto 变量必须初始化")
            sf.setvar_decl_local(self.name, self.init.evaluate())
            return
        if self.typ.endswith("&"):
            if self.init is None:
                raise RuntimeError("引用类型变量必须初始化")
            if not isinstance(self.init, VariableLoadNode):
                raise TypeError("引用初始化须为变量名")
            sf.frame.f_alias[self.name] = self.init.name
            return
        if self.array_size_expr is not None:
            sz = self.array_size_expr.evaluate()
            if not isinstance(sz, int) or sz < 0:
                raise RuntimeError("数组大小必须是非负整数")
            if self.init is not None:
                sf.setvar_decl_local(self.name, self.init.evaluate())
                return
            dv = _default_array_elem_value(self.array_elem_type or "int")
            sf.setvar_decl_local(self.name, [copy.copy(dv) for _ in range(sz)])
            return
        if self.init is not None:
            sf.setvar_decl_local(self.name, self.init.evaluate())
        else:
            if self.typ == "int":
                dv = 0
            elif self.typ == "float":
                dv = 0.0
            elif self.typ == "bool":
                dv = False
            elif self.typ == "string":
                dv = ""
            elif self.typ == "array":
                dv = []
            else:
                tmpl = sf.getvar(self.typ)
                if isinstance(tmpl, dict) and (tmpl.get("__kclass__") or tmpl.get("__kstruct__")) and "members" in tmpl:
                    dv = {
                        "__kclass__": bool(tmpl.get("__kclass__")),
                        "__kstruct__": bool(tmpl.get("__kstruct__")),
                        "name": self.typ,
                        "members": copy.copy(tmpl["members"]),
                    }
                else:
                    dv = None
            sf.setvar_decl_local(self.name, dv)

    def bytecode(self):
        if self.init:
            return [(self.name, None), *self.init.bytecode(), (b"STORE_VAR", 2)]
        return [(self.name, self.typ, None), (b"DECL_VAR", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        if self.init is not None:
            return [*self.init.asm(ctx), ("store_decl_local", self.name)]
        return [("decl", self.typ, self.name)]


class ScopedVarDeclNode(ASTNode):
    def __init__(
        self,
        typ: str,
        scope: str,
        name: str,
        init: ASTNode | None = None,
        array_size_expr: ASTNode | None = None,
        array_elem_type: str | None = None,
        is_constexpr: bool = False,
        is_const: bool = False,
        is_static: bool = False,
    ):
        self.typ = typ
        self.scope = scope
        self.name = name
        self.init = init
        self.array_size_expr = array_size_expr
        self.array_elem_type = array_elem_type
        self.is_constexpr = is_constexpr
        self.is_const = is_const
        self.is_static = is_static

    def evaluate(self):
        from .Data import VariableLoadNode

        sf = stack[-1]
        if self.is_static and sf.module is not None:
            sk = f"{id(sf.frame)}::{self.scope}::{self.name}"
            if sk in sf.module.static_scoped_live:
                return
            sf.module.static_scoped_live.add(sk)
        sf.register_var_decl(self.name, self.scope)
        if self.is_const:
            if self.init is None:
                raise RuntimeError("const 变量必须初始化")
            if sf.module is not None:
                sf.module.const_scoped_names.add(f"{self.scope}::{self.name}")
        if self.is_constexpr:
            if self.init is None:
                raise RuntimeError("constexpr 变量必须初始化")
            if sf.module is not None:
                sf.module.constexpr_names.add(self.name)
        if self.typ == "auto":
            if self.init is None:
                raise RuntimeError("auto 变量必须初始化")
            sf.set_scoped(self.scope, self.name, self.init.evaluate())
            return
        if self.typ.endswith("&"):
            if self.init is None:
                raise RuntimeError("引用类型变量必须初始化")
            if not isinstance(self.init, VariableLoadNode):
                raise TypeError("引用初始化须为变量名")
            sf.frame.f_alias[self.name] = self.init.name
            return
        if self.array_size_expr is not None:
            sz = self.array_size_expr.evaluate()
            if not isinstance(sz, int) or sz < 0:
                raise RuntimeError("数组大小必须是非负整数")
            if self.init is not None:
                v = self.init.evaluate()
            else:
                dv = _default_array_elem_value(self.array_elem_type or "int")
                v = [copy.copy(dv) for _ in range(sz)]
            sf.set_scoped(self.scope, self.name, v)
            return
        if self.typ == "int":
            v = 0
        elif self.typ == "float":
            v = 0.0
        elif self.typ == "bool":
            v = False
        elif self.typ == "string":
            v = ""
        elif self.typ == "array":
            v = []
        else:
            v = None
        if self.init is not None:
            v = self.init.evaluate()
        sf.set_scoped(self.scope, self.name, v)

    def bytecode(self):
        return [
            (self.scope, self.name, None),
            *(self.init.bytecode() if self.init else [(0, None), (b"LOAD_CONST", 1)]),
            (b"STORE_SCOPED", 3),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        if self.init is not None:
            return [*self.init.asm(ctx), ("store_scoped_decl", self.scope, self.name)]
        if self.typ == "int":
            return [("const", 0), ("store_scoped_decl", self.scope, self.name)]
        if self.typ == "float":
            return [("const", 0.0), ("store_scoped_decl", self.scope, self.name)]
        if self.typ == "string":
            return [("const", ""), ("store_scoped_decl", self.scope, self.name)]
        if self.typ == "array":
            return [("const", []), ("store_scoped_decl", self.scope, self.name)]
        return [("const", None), ("store_scoped_decl", self.scope, self.name)]


class AssignStmtNode(ASTNode):
    def __init__(self, name: str, value: ASTNode):
        self.name = name
        self.value = value

    def evaluate(self):
        stack[-1].assign_var(self.name, self.value.evaluate())

    def bytecode(self):
        return [(self.name, None), *self.value.bytecode(), (b"STORE_VAR", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.value.asm(ctx), ("store", self.name)]


class ScopedAssignStmtNode(ASTNode):
    def __init__(self, scope: str, name: str, value: ASTNode):
        self.scope = scope
        self.name = name
        self.value = value

    def evaluate(self):
        stack[-1].assign_scoped(self.scope, self.name, self.value.evaluate())

    def bytecode(self):
        return [(self.scope, self.name), *self.value.bytecode(), (b"STORE_SCOPED", 3)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [*self.value.asm(ctx), ("store_scoped_assign", self.scope, self.name)]


class DerefAssignStmtNode(ASTNode):
    def __init__(self, ptr_expr: ASTNode, value: ASTNode):
        self.ptr_expr = ptr_expr
        self.value = value

    def evaluate(self):
        from ...common import KvalPtr

        p = self.ptr_expr.evaluate()
        if not isinstance(p, KvalPtr):
            raise TypeError("解引用赋值左侧须为指针类型的值")
        p.set(self.value.evaluate())

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class CompoundAssignStmtNode(ASTNode):
    def __init__(self, name: str, op: BinOperator, rhs: ASTNode):
        self.name = name
        self.op = op
        self.rhs = rhs

    def evaluate(self):
        sf = stack[-1]
        cur = sf.getvar(self.name)
        r = self.rhs.evaluate()
        sf.assign_var(self.name, _eval_binop_py(cur, self.op, r))

    def bytecode(self):
        return [
            (self.name, None),
            (b"LOAD_VAR", 1),
            *self.rhs.bytecode(),
            (self.op.value[0], 2),
            (self.name, None),
            (b"STORE_VAR", 2),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [
            ("load", self.name),
            *self.rhs.asm(ctx),
            ("binop", self.op.name),
            ("store", self.name),
        ]


class ScopedCompoundAssignStmtNode(ASTNode):
    def __init__(self, scope: str, name: str, op: BinOperator, rhs: ASTNode):
        self.scope = scope
        self.name = name
        self.op = op
        self.rhs = rhs

    def evaluate(self):
        sf = stack[-1]
        cur = sf.get_scoped(self.scope, self.name)
        r = self.rhs.evaluate()
        sf.assign_scoped(self.scope, self.name, _eval_binop_py(cur, self.op, r))

    def bytecode(self):
        return [
            (self.scope, self.name),
            (b"LOAD_SCOPED", 2),
            *self.rhs.bytecode(),
            (self.op.value[0], 2),
            (self.scope, self.name),
            (b"STORE_SCOPED", 3),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [
            ("load_scoped", self.scope, self.name),
            *self.rhs.asm(ctx),
            ("binop", self.op.name),
            ("store_scoped_assign", self.scope, self.name),
        ]


class DeleteStmtNode(ASTNode):
    def __init__(self, names: list[str]):
        self.names = names

    def evaluate(self):
        sf_obj = stack[-1]
        sf = sf_obj.frame
        for name in self.names:
            if sf_obj.module is not None:
                if name in sf_obj.module.const_names or name in sf_obj.module.constexpr_names:
                    raise NameError(f"cannot delete const/constexpr variable '{name}'")
                if any(k.endswith(f"::{name}") for k in sf_obj.module.const_scoped_names):
                    raise NameError(f"cannot delete const variable '{name}'")
            if name in sf.f_locals:
                del sf.f_locals[name]
                sf.declared_locals.discard(name)
                if sf_obj.module is not None:
                    sf_obj.module.static_local_live.discard(f"{id(sf)}::{name}")
                    to_drop = [k for k in sf_obj.module.static_scoped_live if k.startswith(f"{id(sf)}::") and k.endswith(f"::{name}")]
                    for k in to_drop:
                        sf_obj.module.static_scoped_live.discard(k)
            else:
                for cf in sf.f_closure:
                    if _is_module_like_frame(cf):
                        continue
                    if name in cf.f_locals:
                        del cf.f_locals[name]
                        cf.declared_locals.discard(name)
                        if sf_obj.module is not None:
                            sf_obj.module.static_local_live.discard(f"{id(cf)}::{name}")
                            to_drop = [
                                k
                                for k in sf_obj.module.static_scoped_live
                                if k.startswith(f"{id(cf)}::") and k.endswith(f"::{name}")
                            ]
                            for k in to_drop:
                                sf_obj.module.static_scoped_live.discard(k)
                        break

    def bytecode(self):
        return [(tuple(self.names), None), (b"DELETE", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("delete", *self.names)]


class VarScopeOrderStmtNode(ASTNode):
    def __init__(self, entries: list[tuple[str, str | tuple[str, ...]]]):
        self.entries = entries

    def evaluate(self):
        fr = stack[-1].frame
        for name, spec in self.entries:
            if isinstance(spec, str):
                fr.f_var_scope[name] = spec
                fr.f_var_order.pop(name, None)
            else:
                fr.f_var_order[name] = list(spec)
                fr.f_var_scope.pop(name, None)

    def bytecode(self):
        return [(tuple(self.entries), None), (b"VAR_SCOPE_ORDER", 1)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return [("var_scope_order", tuple(self.entries))]


class IfStmtNode(ASTNode):
    def __init__(self, branches: list[tuple], else_block: BlockNode | None):
        self.branches = branches
        self.else_block = else_block

    def evaluate(self):
        for cond, block in self.branches:
            if _kval_truthy(cond.evaluate()):
                block.evaluate()
                return
        if self.else_block is not None:
            self.else_block.evaluate()

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class WhileStmtNode(ASTNode):
    def __init__(self, cond, body: BlockNode):
        self.cond = cond
        self.body = body

    def evaluate(self):
        from ...Errors.Signals import BreakSignal, ContinueSignal

        while _kval_truthy(self.cond.evaluate()):
            try:
                self.body.evaluate()
            except ContinueSignal:
                continue
            except BreakSignal:
                break

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class ForCStmtNode(ASTNode):
    def __init__(self, init, cond, step, body: BlockNode):
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body

    def evaluate(self):
        from ...Errors.Signals import BreakSignal, ContinueSignal

        if self.init is not None:
            self.init.evaluate()
        while True:
            if self.cond is not None:
                if not _kval_truthy(self.cond.evaluate()):
                    break
            try:
                self.body.evaluate()
            except ContinueSignal:
                pass
            except BreakSignal:
                break
            if self.step is not None:
                self.step.evaluate()

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class ForRangeStmtNode(ASTNode):
    def __init__(self, elem_type: str, var_name: str, iterable_expr, body: BlockNode):
        self.elem_type = elem_type
        self.var_name = var_name
        self.iterable_expr = iterable_expr
        self.body = body

    def evaluate(self):
        from ...Errors.Signals import BreakSignal, ContinueSignal

        items = _expand_kval_iterable(self.iterable_expr.evaluate())
        sf = stack[-1]
        sf.register_var_decl(self.var_name, None)
        for i, item in enumerate(items):
            if i == 0:
                sf.setvar_decl_local(self.var_name, item)
            else:
                sf.assign_var(self.var_name, item)
            try:
                self.body.evaluate()
            except ContinueSignal:
                continue
            except BreakSignal:
                break

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


class SwitchStmtNode(ASTNode):
    def __init__(self, disc, cases: list[tuple], else_block: BlockNode | None):
        self.disc = disc
        self.cases = cases
        self.else_block = else_block

    def evaluate(self):
        from ...Errors.Signals import BreakSignal

        v = self.disc.evaluate()
        for ce, block in self.cases:
            if v == ce.evaluate():
                try:
                    block.evaluate()
                except BreakSignal:
                    pass
                return
        if self.else_block is not None:
            try:
                self.else_block.evaluate()
            except BreakSignal:
                pass

    def bytecode(self):
        return []

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return []


def _expr_has_logical_shortcircuit(e) -> bool:
    from .Data import (
        AttributeAccessNode,
        AttributeStoreNode,
        BinOpNode,
        BinOperator,
        FunctionCallNode,
        UnaryOpNode,
    )

    if isinstance(e, BinOpNode):
        if e.op in (BinOperator.land, BinOperator.lor):
            return True
        return _expr_has_logical_shortcircuit(e.left) or _expr_has_logical_shortcircuit(e.right)
    if isinstance(e, UnaryOpNode):
        return _expr_has_logical_shortcircuit(e.value)
    if isinstance(e, FunctionCallNode):
        if _expr_has_logical_shortcircuit(e.func):
            return True
        if any(_expr_has_logical_shortcircuit(a) for a in e.args):
            return True
        return any(_expr_has_logical_shortcircuit(v) for v in e.kwargs.values())
    if isinstance(e, AttributeAccessNode):
        return _expr_has_logical_shortcircuit(e.obj)
    if isinstance(e, AttributeStoreNode):
        return _expr_has_logical_shortcircuit(e.obj) or _expr_has_logical_shortcircuit(e.value)
    return False


def _expr_has_pointer_ops(e) -> bool:
    from .Data import (
        AttributeAccessNode,
        AttributeStoreNode,
        BinOpNode,
        FunctionCallNode,
        UnaryOpNode,
        UnaryOperator,
    )

    if isinstance(e, UnaryOpNode):
        if e.op in (UnaryOperator.addr, UnaryOperator.deref):
            return True
        return _expr_has_pointer_ops(e.value)
    if isinstance(e, BinOpNode):
        return _expr_has_pointer_ops(e.left) or _expr_has_pointer_ops(e.right)
    if isinstance(e, FunctionCallNode):
        if _expr_has_pointer_ops(e.func):
            return True
        if any(_expr_has_pointer_ops(a) for a in e.args):
            return True
        return any(_expr_has_pointer_ops(v) for v in e.kwargs.values())
    if isinstance(e, AttributeAccessNode):
        return _expr_has_pointer_ops(e.obj)
    if isinstance(e, AttributeStoreNode):
        return _expr_has_pointer_ops(e.obj) or _expr_has_pointer_ops(e.value)
    return False


def statements_use_pointer_ops(stmts: list) -> bool:
    for s in stmts:
        if isinstance(s, DerefAssignStmtNode):
            return True
        if isinstance(s, VarDeclNode) and (s.typ.endswith("*") or s.typ.endswith("&")):
            return True
        if isinstance(s, ScopedVarDeclNode) and (s.typ.endswith("*") or s.typ.endswith("&")):
            return True
        if isinstance(s, AssignStmtNode):
            if _expr_has_pointer_ops(s.value):
                return True
        elif isinstance(s, CompoundAssignStmtNode):
            if _expr_has_pointer_ops(s.rhs):
                return True
        elif isinstance(s, ExprStmtNode):
            if _expr_has_pointer_ops(s.expr):
                return True
        elif isinstance(s, ReturnNode) and s.value is not None:
            if _expr_has_pointer_ops(s.value):
                return True
        elif isinstance(s, VarDeclNode) and s.init is not None:
            if _expr_has_pointer_ops(s.init):
                return True
        elif isinstance(s, ScopedVarDeclNode) and s.init is not None:
            if _expr_has_pointer_ops(s.init):
                return True
        elif isinstance(s, ScopedAssignStmtNode):
            if _expr_has_pointer_ops(s.value):
                return True
        elif isinstance(s, ScopedCompoundAssignStmtNode):
            if _expr_has_pointer_ops(s.rhs):
                return True
        elif isinstance(s, IfStmtNode):
            for cond, blk in s.branches:
                if _expr_has_pointer_ops(cond) or statements_use_pointer_ops(blk.statements):
                    return True
            if s.else_block is not None and statements_use_pointer_ops(s.else_block.statements):
                return True
        elif isinstance(s, WhileStmtNode):
            if _expr_has_pointer_ops(s.cond) or statements_use_pointer_ops(s.body.statements):
                return True
        elif isinstance(s, ForCStmtNode):
            if s.init is not None and _stmt_might_have_ptr_ops(s.init):
                return True
            if s.cond is not None and _expr_has_pointer_ops(s.cond):
                return True
            if s.step is not None and _stmt_might_have_ptr_ops(s.step):
                return True
            if statements_use_pointer_ops(s.body.statements):
                return True
        elif isinstance(s, ForRangeStmtNode):
            if _expr_has_pointer_ops(s.iterable_expr):
                return True
            if statements_use_pointer_ops(s.body.statements):
                return True
        elif isinstance(s, SwitchStmtNode):
            if _expr_has_pointer_ops(s.disc):
                return True
            for ce, blk in s.cases:
                if _expr_has_pointer_ops(ce) or statements_use_pointer_ops(blk.statements):
                    return True
            if s.else_block is not None and statements_use_pointer_ops(s.else_block.statements):
                return True
        elif isinstance(s, TryStmtNode):
            if statements_use_pointer_ops(s.try_block.statements):
                return True
            for _tn, _bn, blk in s.catches:
                if statements_use_pointer_ops(blk.statements):
                    return True
            if s.else_block is not None and statements_use_pointer_ops(s.else_block.statements):
                return True
            if s.finally_block is not None and statements_use_pointer_ops(s.finally_block.statements):
                return True
        elif isinstance(s, BlockNode):
            if statements_use_pointer_ops(s.statements):
                return True
        elif isinstance(s, FunctionDefNode):
            if statements_use_pointer_ops(s.body.statements):
                return True
        elif isinstance(s, TemplateFunctionDefNode):
            if statements_use_pointer_ops(s.inner.body.statements):
                return True
        elif isinstance(s, ClassDefNode):
            if statements_use_pointer_ops(s.member_stmts):
                return True
        elif isinstance(s, NamespaceDefNode):
            if statements_use_pointer_ops(s.body_stmts):
                return True
    return False


def _stmt_might_have_ptr_ops(s) -> bool:
    if isinstance(s, ExprStmtNode):
        return _expr_has_pointer_ops(s.expr)
    if isinstance(s, AssignStmtNode):
        return _expr_has_pointer_ops(s.value)
    if isinstance(s, CompoundAssignStmtNode):
        return _expr_has_pointer_ops(s.rhs)
    return False


def statements_use_logical_shortcircuit(stmts: list) -> bool:
    for s in stmts:
        if isinstance(s, AssignStmtNode):
            if _expr_has_logical_shortcircuit(s.value):
                return True
        elif isinstance(s, CompoundAssignStmtNode):
            if _expr_has_logical_shortcircuit(s.rhs):
                return True
        elif isinstance(s, ExprStmtNode):
            if _expr_has_logical_shortcircuit(s.expr):
                return True
        elif isinstance(s, ReturnNode) and s.value is not None:
            if _expr_has_logical_shortcircuit(s.value):
                return True
        elif isinstance(s, VarDeclNode) and s.init is not None:
            if _expr_has_logical_shortcircuit(s.init):
                return True
        elif isinstance(s, ScopedVarDeclNode) and s.init is not None:
            if _expr_has_logical_shortcircuit(s.init):
                return True
        elif isinstance(s, ScopedAssignStmtNode):
            if _expr_has_logical_shortcircuit(s.value):
                return True
        elif isinstance(s, ScopedCompoundAssignStmtNode):
            if _expr_has_logical_shortcircuit(s.rhs):
                return True
        elif isinstance(s, IfStmtNode):
            for cond, blk in s.branches:
                if _expr_has_logical_shortcircuit(cond) or statements_use_logical_shortcircuit(blk.statements):
                    return True
            if s.else_block is not None and statements_use_logical_shortcircuit(s.else_block.statements):
                return True
        elif isinstance(s, WhileStmtNode):
            if _expr_has_logical_shortcircuit(s.cond) or statements_use_logical_shortcircuit(s.body.statements):
                return True
        elif isinstance(s, ForCStmtNode):
            if s.init is not None and _stmt_might_have_logical_sc(s.init):
                return True
            if s.cond is not None and _expr_has_logical_shortcircuit(s.cond):
                return True
            if s.step is not None and _stmt_might_have_logical_sc(s.step):
                return True
            if statements_use_logical_shortcircuit(s.body.statements):
                return True
        elif isinstance(s, ForRangeStmtNode):
            if _expr_has_logical_shortcircuit(s.iterable_expr):
                return True
            if statements_use_logical_shortcircuit(s.body.statements):
                return True
        elif isinstance(s, SwitchStmtNode):
            if _expr_has_logical_shortcircuit(s.disc):
                return True
            for ce, blk in s.cases:
                if _expr_has_logical_shortcircuit(ce) or statements_use_logical_shortcircuit(blk.statements):
                    return True
            if s.else_block is not None and statements_use_logical_shortcircuit(s.else_block.statements):
                return True
        elif isinstance(s, TryStmtNode):
            if statements_use_logical_shortcircuit(s.try_block.statements):
                return True
            for _tn, _bn, blk in s.catches:
                if statements_use_logical_shortcircuit(blk.statements):
                    return True
            if s.else_block is not None and statements_use_logical_shortcircuit(s.else_block.statements):
                return True
            if s.finally_block is not None and statements_use_logical_shortcircuit(s.finally_block.statements):
                return True
        elif isinstance(s, BlockNode):
            if statements_use_logical_shortcircuit(s.statements):
                return True
        elif isinstance(s, FunctionDefNode):
            if statements_use_logical_shortcircuit(s.body.statements):
                return True
        elif isinstance(s, TemplateFunctionDefNode):
            if statements_use_logical_shortcircuit(s.inner.body.statements):
                return True
        elif isinstance(s, ClassDefNode):
            if statements_use_logical_shortcircuit(s.member_stmts):
                return True
        elif isinstance(s, NamespaceDefNode):
            if statements_use_logical_shortcircuit(s.body_stmts):
                return True
    return False


def _stmt_might_have_logical_sc(s) -> bool:
    if isinstance(s, ExprStmtNode):
        return _expr_has_logical_shortcircuit(s.expr)
    if isinstance(s, AssignStmtNode):
        return _expr_has_logical_shortcircuit(s.value)
    if isinstance(s, CompoundAssignStmtNode):
        return _expr_has_logical_shortcircuit(s.rhs)
    return False


def statements_need_ast_fallback(stmts: list) -> bool:
    cf_types = (IfStmtNode, WhileStmtNode, ForCStmtNode, ForRangeStmtNode, SwitchStmtNode, TryStmtNode, ThrowStmtNode)
    for s in stmts:
        if isinstance(s, cf_types):
            return True
        if isinstance(s, BlockNode):
            if statements_need_ast_fallback(s.statements):
                return True
        if isinstance(s, FunctionDefNode):
            if statements_need_ast_fallback(s.body.statements):
                return True
        if isinstance(s, TemplateFunctionDefNode):
            if statements_need_ast_fallback(s.inner.body.statements):
                return True
        if isinstance(s, ClassDefNode):
            if statements_need_ast_fallback(s.member_stmts):
                return True
        if isinstance(s, NamespaceDefNode):
            if statements_need_ast_fallback(s.body_stmts):
                return True
        if isinstance(s, DerefAssignStmtNode):
            return True
    return False


class FunctionDefNode(ASTNode):
    def __init__(
        self,
        name: str,
        param_types: list[str],
        param_names: list[str],
        body: Body,
        returns_void: bool,
        type_param_names: tuple[str, ...] = (),
        return_type: str = "int",
        is_constexpr: bool = False,
    ):
        self.name = name
        self.param_types = param_types
        self.param_names = param_names
        self.body = body
        self.returns_void = returns_void
        self.type_param_names = type_param_names
        self.return_type = return_type
        self.is_constexpr = is_constexpr

    def evaluate(self):
        ctx = AsmContext()
        if (
            statements_need_ast_fallback(self.body.statements)
            or statements_use_logical_shortcircuit(self.body.statements)
            or statements_use_pointer_ops(self.body.statements)
        ):
            asm_insns = None
        else:
            asm_insns = flatten_stmt_asm(self.body.statements, ctx)
        sf = stack[-1]
        fn = KvalFunction(
            self.name,
            list(self.param_names),
            list(self.param_types),
            self.body,
            self.returns_void,
            self.type_param_names,
            asm_insns=asm_insns,
            is_constexpr=self.is_constexpr,
            owner_class=sf.frame.f_current_class,
        )
        if self.is_constexpr and sf.module is not None:
            sf.module.constexpr_functions.add(self.name)
        if getattr(self, "_is_export", False) and sf.module is not None:
            sf.module.export_names_marked.add(self.name)
        sf.register_var_decl(self.name, None)
        existing = sf.frame.f_locals.get(self.name)
        if existing is None or isinstance(existing, Unbound):
            sf.setvar_decl_local(self.name, fn)
        elif isinstance(existing, KvalFunction):
            sf.setvar_decl_local(self.name, KvalOverloadGroup(existing, fn))
        elif isinstance(existing, KvalOverloadGroup):
            existing.add(fn)
            sf.setvar_decl_local(self.name, existing)
        else:
            raise TypeError(f"无法为 {self.name!r} 定义重载：该名已绑定非函数值")
        return fn

    def bytecode(self):
        return [
            (self.name, None),
            (self.param_names, None),
            (id(self.body), None),
            (b"LOAD_BODY", 1),
            (b"STORE_FUNC", 3),
        ]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        sub = AsmContext()
        body_insns = flatten_stmt_asm(self.body.statements, sub)
        return [
            (
                "define",
                self.name,
                tuple(self.param_names),
                tuple(self.param_types),
                int(self.returns_void),
                tuple(self.type_param_names),
                insns_to_tuple(body_insns),
            )
        ]


class TemplateFunctionDefNode(ASTNode):
    def __init__(self, inner: FunctionDefNode):
        self.inner = inner

    def evaluate(self):
        return self.inner.evaluate()

    def bytecode(self):
        return self.inner.bytecode()

    def asm(self, ctx: AsmContext) -> list[Insn]:
        return self.inner.asm(ctx)


class ClassDefNode(ASTNode):
    def __init__(self, name: str, member_stmts: list[ASTNode], bases: tuple[tuple[str, str], ...] = ()):
        self.name = name
        self.member_stmts = member_stmts
        self.bases = bases

    def evaluate(self):
        outer_sf = stack[-1]
        saved_locals = outer_sf.frame.f_locals
        saved_current_class = outer_sf.frame.f_current_class
        outer_sf.frame.f_locals = {}
        outer_sf.frame.f_current_class = self.name
        try:
            for st in self.member_stmts:
                st.evaluate()
            members = dict(outer_sf.frame.f_locals)
        finally:
            outer_sf.frame.f_locals = saved_locals
            outer_sf.frame.f_current_class = saved_current_class
        own_members = dict(members)
        own_member_access: dict[str, str] = {}
        member_access: dict[str, str] = {}
        member_owner: dict[str, str] = {}
        for st in self.member_stmts:
            n = getattr(st, "name", None)
            if not isinstance(n, str):
                continue
            acc = getattr(st, "_class_member_access", "private")
            own_member_access[n] = acc
            member_access[n] = acc
            member_owner[n] = self.name
        mro: list[str] = [self.name]
        for inherit_access, base_name in self.bases:
            base_obj = outer_sf.getvar(base_name)
            if not (isinstance(base_obj, dict) and base_obj.get("__kclass__") and "members" in base_obj):
                raise TypeError(f"base class '{base_name}' not found")
            for bn in base_obj.get("mro", (base_name,)):
                if bn not in mro:
                    mro.append(bn)
            base_members = base_obj.get("members", {})
            base_access = base_obj.get("member_access", {})
            base_owner = base_obj.get("member_owner", {})
            for k, v in base_members.items():
                if k in members:
                    continue
                acc = base_access.get(k, "public")
                if acc == "private":
                    continue
                if inherit_access == "public":
                    mapped = acc
                elif inherit_access == "protected":
                    mapped = "protected"
                else:
                    mapped = "private"
                members[k] = v
                member_access[k] = mapped
                member_owner[k] = base_owner.get(k, base_name)
        ancestors = set(mro[1:])
        outer_sf.register_var_decl(self.name, None)
        if getattr(self, "_is_export", False) and outer_sf.module is not None:
            outer_sf.module.export_names_marked.add(self.name)
        outer_sf.setvar_decl_local(
            self.name,
            {
                "__kclass__": True,
                "name": self.name,
                "own_members": own_members,
                "own_member_access": own_member_access,
                "members": members,
                "member_access": member_access,
                "member_owner": member_owner,
                "ancestors": ancestors,
                "mro": tuple(mro),
                "bases": tuple(self.bases),
            },
        )

    def bytecode(self):
        return [(self.name, tuple(id(s) for s in self.member_stmts)), (b"CLASS_DEF", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        sub = AsmContext()
        inner: list[Insn] = []
        for st in self.member_stmts:
            inner.extend(st.asm(sub))
        return [("class_def", self.name, insns_to_tuple(inner))]


class StructDefNode(ASTNode):
    def __init__(self, name: str, member_stmts: list[ASTNode]):
        self.name = name
        self.member_stmts = member_stmts

    def evaluate(self):
        outer_sf = stack[-1]
        saved_locals = outer_sf.frame.f_locals
        outer_sf.frame.f_locals = {}
        try:
            for st in self.member_stmts:
                st.evaluate()
            members = dict(outer_sf.frame.f_locals)
        finally:
            outer_sf.frame.f_locals = saved_locals
        outer_sf.register_var_decl(self.name, None)
        if getattr(self, "_is_export", False) and outer_sf.module is not None:
            outer_sf.module.export_names_marked.add(self.name)
        outer_sf.setvar_decl_local(
            self.name,
            {"__kstruct__": True, "name": self.name, "members": members},
        )

    def bytecode(self):
        return [(self.name, tuple(id(s) for s in self.member_stmts)), (b"CLASS_DEF", 2)]

    def asm(self, ctx: AsmContext) -> list[Insn]:
        sub = AsmContext()
        inner: list[Insn] = []
        for st in self.member_stmts:
            inner.extend(st.asm(sub))
        return [("class_def", self.name, insns_to_tuple(inner))]
