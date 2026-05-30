from __future__ import annotations

from .. import RunTime
from ..Errors.Signals import ReturnSignal
from ..Parser.AST.asm_ir import AsmContext
from ..RunTime import Module, stack

from .insn_vm import InsnVM


class RPNVMRunner:
    def __init__(self, module: Module):
        self.module = module

    def run(self):
        RunTime.execution_backend = "asm"
        ctx = AsmContext()
        insns: list = []
        for s in self.module.body.statements:
            insns.extend(s.asm(ctx))
        stack.append(self.module.body.sf)
        mod_ret = 0
        try:
            InsnVM(insns, self.module.body.sf).run()
        except ReturnSignal as e:
            mod_ret = e.value
        finally:
            stack.pop()
        g = self.module.body.sf.frame.f_globals
        m = g.get("main")
        if m is not None and callable(m):
            stack.append(self.module.body.sf)
            try:
                return m()
            finally:
                stack.pop()
        return mod_ret if mod_ret is not None else 0
