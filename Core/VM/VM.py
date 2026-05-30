from __future__ import annotations

from enum import Enum, auto
from ..RunTime import Module
from .AST_VM import ASTVMRunner
from .RPN_VM import RPNVMRunner

class RunningMode(Enum):
    ast = auto()
    bytecode = auto()
    unknown = auto()

running_mode = RunningMode.unknown
using_VM = None

def set_runner(mode: RunningMode = RunningMode.ast):
    global running_mode, using_VM
    running_mode = mode
    if mode == RunningMode.ast:
        using_VM = ASTVMRunner
    elif mode == RunningMode.bytecode:
        using_VM = RPNVMRunner
    else:
        raise ValueError("Unknown running mode")

def run(module: Module):
    if using_VM is None:
        raise RuntimeError("VM runner not set")
    return using_VM(module).run()