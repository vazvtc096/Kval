from __future__ import annotations

from .. import RunTime
from ..Errors.Signals import ReturnSignal
from ..RunTime import Module, stack


class ASTVMRunner:
    def __init__(self, module: Module):
        self.module = module

    def run(self):
        RunTime.execution_backend = "jit" if RunTime.jit_mode else "ast"
        try:
            self._eval_constexpr_prelude()
            self.module.body.evaluate()
        except ReturnSignal as e:
            return e.value
        g = self.module.body.sf.frame.f_globals
        m = g.get("main")
        if m is not None and callable(m):
            stack.append(self.module.body.sf)
            try:
                return m()
            finally:
                stack.pop()
        return 0

    def _eval_constexpr_prelude(self) -> None:
        sf = self.module.body.sf
        prev_phase = RunTime.constexpr_phase
        RunTime.constexpr_phase = True
        stack.append(sf)
        try:
            for st in self.module.body.statements:
                if not getattr(st, "is_constexpr", False):
                    continue
                st.evaluate()
                setattr(st, "_constexpr_done", True)
        finally:
            stack.pop()
            RunTime.constexpr_phase = prev_phase
