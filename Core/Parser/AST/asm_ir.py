from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Insn = tuple[Any, ...]


@dataclass
class AsmContext:
    label_counter: int = field(default=0, repr=False)
    loop_stack: list[tuple[str, str]] = field(default_factory=list, repr=False)

    def fresh_label(self, prefix: str = "L") -> str:
        self.label_counter += 1
        return f".{prefix}{self.label_counter}"

    def push_loop(self, break_label: str, continue_label: str) -> None:
        self.loop_stack.append((break_label, continue_label))

    def pop_loop(self) -> None:
        if self.loop_stack:
            self.loop_stack.pop()

    def current_loop_labels(self) -> tuple[str, str] | None:
        if self.loop_stack:
            return self.loop_stack[-1]
        return None


def insns_to_tuple(insns: list[Insn]) -> tuple[Insn, ...]:
    return tuple(insns)


def flatten_stmt_asm(statements, ctx: AsmContext) -> list[Insn]:
    out: list[Insn] = []
    for s in statements:
        out.extend(s.asm(ctx))
    return out


def format_insns(insns: list[Insn], indent: str = "") -> str:
    lines: list[str] = []
    for insn in insns:
        if not insn:
            continue
        op = insn[0]
        if op == "define":
            _, name, pnames, ptypes, void_i, tparams, body = insn
            lines.append(
                f"{indent}define {name}({', '.join(pnames)}) returns_void={bool(void_i)} tparams={tparams}"
            )
            lines.append(format_insns(list(body), indent + "  "))
            lines.append(f"{indent}end define {name}")
        elif op == "class_def":
            _, cname, body = insn
            lines.append(f"{indent}class {cname}")
            lines.append(format_insns(list(body), indent + "  "))
            lines.append(f"{indent}end class {cname}")
        elif op == "label":
            lines.append(f"{indent}label {insn[1]}")
        elif op in ("jmp", "jz", "jnz"):
            lines.append(f"{indent}{op} {insn[1]}")
        else:
            lines.append(f"{indent}{' '.join(repr(x) if isinstance(x, str) else str(x) for x in insn)}")
    return "\n".join(lines)
