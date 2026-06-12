from __future__ import annotations

from typing import Any, Sequence

from ..Errors.Signals import ReturnSignal
from ..Parser.AST.Data import BinOperator, UnaryOperator, _eval_binop_py
from ..RunTime import Frame, KvalFunction, StackFrame, _is_module_like_frame, stack
from ..common import Unbound, kval_truthy, skip_unbound_errors


class InsnVM:
    __slots__ = ("insns", "sf", "vals", "_labels")

    def __init__(self, insns: Sequence[tuple[Any, ...]], sf: StackFrame):
        self.insns = list(insns)
        self.sf = sf
        self.vals: list[Any] = []
        self._labels: dict[str, int] = {}

    def push(self, v: Any) -> None:
        self.vals.append(v)

    def pop(self) -> Any:
        return self.vals.pop()

    def run(self) -> None:
        # First pass: build label index
        self._labels.clear()
        for i, insn in enumerate(self.insns):
            if insn and insn[0] == "label":
                self._labels[insn[1]] = i
        # Second pass: execute with jump support
        ip = 0
        n = len(self.insns)
        while ip < n:
            insn = self.insns[ip]
            ip = self._dispatch(insn, ip + 1)

    def _dispatch(self, insn: tuple[Any, ...], next_ip: int) -> int:
        op = insn[0]
        if op == "const":
            self.push(insn[1])
        elif op == "load":
            v = self.sf.getvar(insn[1])
            if isinstance(v, Unbound) and skip_unbound_errors:
                self.push(v)
            elif isinstance(v, Unbound):
                raise NameError(f"'{insn[1]}' is not bound")
            else:
                self.push(v)
        elif op == "load_scoped":
            self.push(self.sf.get_scoped(insn[1], insn[2]))
        elif op == "store":
            self.sf.assign_var(insn[1], self.pop())
        elif op == "store_scoped_assign":
            self.sf.assign_scoped(insn[1], insn[2], self.pop())
        elif op == "store_scoped_decl":
            scope, name = insn[1], insn[2]
            val = self.pop()
            self.sf.register_var_decl(name, scope)
            self.sf.set_scoped(scope, name, val)
        elif op == "binop":
            b, a = self.pop(), self.pop()
            bo = BinOperator[insn[1]]
            if bo in (BinOperator.land, BinOperator.lor):
                raise TypeError("asm 路径不支持 && / ||（请使用 AST 执行）")
            if isinstance(a, (int, str)) and isinstance(b, (int, str)):
                self.push(_eval_binop_py(a, bo, b))
            else:
                raise TypeError(f"asm binop needs primitive got {type(a)},{type(b)}")
        elif op == "unary":
            a = self.pop()
            uo = UnaryOperator[insn[1]]
            if uo in (UnaryOperator.addr, UnaryOperator.deref):
                raise TypeError("asm 路径不支持取址 / 解引用（请使用 AST 执行）")
            if uo == UnaryOperator.lnot:
                self.push(int(not kval_truthy(a)))
            elif isinstance(a, int):
                if uo == UnaryOperator.neg:
                    self.push(-a)
                elif uo == UnaryOperator.bitnot:
                    self.push(~a)
                else:
                    raise TypeError(uo)
            else:
                raise TypeError("asm unary needs int")
        elif op == "pop":
            self.pop()
        elif op == "decl":
            typ, name = insn[1], insn[2]
            self.sf.register_var_decl(name, None)
            self.sf.frame.f_locals[name] = 0 if typ == "int" else ("" if typ == "string" else None)
        elif op == "store_decl_local":
            name = insn[1]
            val = self.pop()
            self.sf.register_var_decl(name, None)
            self.sf.frame.f_locals[name] = val
        elif op == "delete":
            fr = self.sf.frame
            for name in insn[1:]:
                if name in fr.f_locals:
                    del fr.f_locals[name]
                    fr.declared_locals.discard(name)
                else:
                    for cf in fr.f_closure:
                        if _is_module_like_frame(cf):
                            continue
                        if name in cf.f_locals:
                            del cf.f_locals[name]
                            cf.declared_locals.discard(name)
                            break
        elif op == "var_scope_order":
            for name, spec in insn[1]:
                if isinstance(spec, str):
                    self.sf.frame.f_var_scope[name] = spec
                    self.sf.frame.f_var_order.pop(name, None)
                else:
                    self.sf.frame.f_var_order[name] = list(spec)
                    self.sf.frame.f_var_scope.pop(name, None)
        elif op == "define":
            self._do_define(insn)
        elif op == "class_def":
            self._do_class_def(insn)
        elif op == "call":
            self._do_call(insn)
        elif op == "call_indirect":
            self._do_call_indirect(insn)
        elif op == "get_attr":
            obj = self.pop()
            attr = insn[1]
            if isinstance(obj, dict):
                v = obj.get(attr, Unbound(attr))
            else:
                from ..Types.Base import ObjectAttributeVisitor as OAV

                v = getattr(OAV(obj), attr)
            self.push(v)
        elif op == "set_attr":
            val = self.pop()
            obj = self.pop()
            attr = insn[1]
            if isinstance(obj, dict):
                obj[attr] = val
            else:
                from ..Types.Base import ObjectAttributeVisitor as OAV

                setattr(OAV(obj), attr, val)
        elif op == "label":
            pass  # label is handled in first pass, no-op during execution
        elif op == "jmp":
            target = insn[1]
            if target in self._labels:
                return self._labels[target]
            raise RuntimeError(f"jmp target {target!r} not found")
        elif op == "jz":
            v = self.pop()
            if not kval_truthy(v):
                target = insn[1]
                if target in self._labels:
                    return self._labels[target]
                raise RuntimeError(f"jz target {target!r} not found")
        elif op == "jnz":
            v = self.pop()
            if kval_truthy(v):
                target = insn[1]
                if target in self._labels:
                    return self._labels[target]
                raise RuntimeError(f"jnz target {target!r} not found")
        elif op == "ret":
            raise ReturnSignal(self.pop())
        elif op == "retvoid":
            raise ReturnSignal(None)
        else:
            raise NotImplementedError(f"unknown insn {insn!r}")
        return next_ip

    def _do_define(self, insn: tuple[Any, ...]) -> None:
        _, name, pnames, ptypes, void_i, tparams, body_t = insn
        from ..RunTime import Body

        body = Body([])
        fn = KvalFunction(
            name,
            list(pnames),
            list(ptypes),
            body,
            bool(void_i),
            tuple(tparams),
            asm_insns=list(body_t),
        )
        self.sf.register_var_decl(name, None)
        self.sf.frame.f_locals[name] = fn

    def _do_class_def(self, insn: tuple[Any, ...]) -> None:
        _, cname, body_t = insn
        outer = self.sf
        saved = outer.frame.f_locals
        outer.frame.f_locals = {}
        try:
            InsnVM(list(body_t), outer).run()
            members = dict(outer.frame.f_locals)
        finally:
            outer.frame.f_locals = saved
        outer.register_var_decl(cname, None)
        outer.setvar_decl_local(cname, {"__kclass__": True, "name": cname, "members": members})

    def _do_call(self, insn: tuple[Any, ...]) -> None:
        _, fname, nargs, kw_order = insn
        kw_order = tuple(kw_order)
        kwargs = {}
        for k in reversed(kw_order):
            kwargs[k] = self.pop()
        args = []
        for _ in range(nargs):
            args.append(self.pop())
        args.reverse()
        fn = self.sf.getvar(fname)
        if isinstance(fn, Unbound) and skip_unbound_errors:
            self.push(fn)
            return
        if isinstance(fn, Unbound):
            raise NameError(f"call to unbound {fname!r}")
        if not callable(fn):
            raise TypeError(f"{fname!r} is not callable")
        res = fn(*args, **kwargs)
        self.push(res)

    def _do_call_indirect(self, insn: tuple[Any, ...]) -> None:
        _, nargs, kw_order = insn
        kw_order = tuple(kw_order)
        kwargs = {}
        for k in reversed(kw_order):
            kwargs[k] = self.pop()
        args = []
        for _ in range(nargs):
            args.append(self.pop())
        args.reverse()
        fn = self.pop()
        if not callable(fn):
            raise TypeError("call_indirect target not callable")
        res = fn(*args, **kwargs)
        self.push(res)
