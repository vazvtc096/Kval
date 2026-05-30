from abc import ABC, abstractmethod

from ...Types.Base import Object

from .asm_ir import AsmContext, Insn


class ASTNode(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def evaluate(self) -> Object:
        return Object(type, {})

    @abstractmethod
    def bytecode(self):
        return [(b"NOP", None)]

    @abstractmethod
    def asm(self, ctx: AsmContext) -> list[Insn]:
        ...
