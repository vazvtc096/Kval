"""将 ASM IR 指令编译为真正的 x64 NASM 汇编代码。

支持在运行时实际执行计算，而非仅编译时静态求值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .Parser.AST.asm_ir import Insn
from .Parser.AST.Data import BinOperator


@dataclass
class _VarSlot:
    name: str
    offset: int       # rbp 相对偏移（正值表示 rbp - offset）
    size: int = 8


@dataclass
class _StructField:
    name: str
    ty: str
    offset: int
    size: int = 8


@dataclass
class _StructLayout:
    name: str
    fields: list[_StructField] = field(default_factory=list)
    total_size: int = 0

    def field_offset(self, field_name: str) -> int | None:
        for f in self.fields:
            if f.name == field_name:
                return f.offset
        return None


@dataclass
class _FuncInfo:
    name: str
    param_names: tuple[str, ...]
    body_insns: tuple[Insn, ...]
    returns_void: bool
    label: str


@dataclass
class _CodegenContext:
    win64: bool = False
    str_literals: list[str] = field(default_factory=list)
    funcs: list[_FuncInfo] = field(default_factory=list)
    main_body: tuple[Insn, ...] = ()
    main_has_print: bool = False
    _str_index: dict[str, int] = field(default_factory=dict, repr=False)
    _structs: dict[str, _StructLayout] = field(default_factory=dict, repr=False)
    _has_malloc: bool = field(default=False, repr=False)
    # 追踪堆分配的变量名（用于 RAII 自动释放）
    _heap_vars: set[str] = field(default_factory=set, repr=False)

    def add_string(self, s: str) -> int:
        if s not in self._str_index:
            idx = len(self.str_literals)
            self.str_literals.append(s)
            self._str_index[s] = idx
        return self._str_index[s]

    def add_struct(self, layout: _StructLayout) -> None:
        self._structs[layout.name] = layout

    def get_struct(self, name: str) -> _StructLayout | None:
        return self._structs.get(name)

    def note_malloc_used(self) -> None:
        self._has_malloc = True

    def add_heap_var(self, name: str) -> None:
        self._heap_vars.add(name)


def _binop_nasm(op_name: str) -> str | None:
    mapping = {
        "add": "add", "sub": "sub", "mul": "imul",
        "div": "idiv", "mod": "idiv",
        "bitxor": "xor", "bitand": "and", "bitor": "or",
        "shl": "shl", "shr": "shr",
        "fadd": "addsd", "fsub": "subsd", "fmul": "mulsd", "fdiv": "divsd",
    }
    return mapping.get(op_name)


def _fcmp_nasm(op_name: str) -> str:
    mapping = {
        "flt": "b", "fle": "be", "fgt": "a",
        "fge": "ae", "feq": "e", "fne": "ne",
    }
    return mapping.get(op_name, "e")


def _unary_nasm(op_name: str) -> str | None:
    return {"neg": "neg", "bitnot": "not"}.get(op_name)


def _cmp_nasm(op_name: str) -> str:
    mapping = {"lt": "l", "le": "le", "gt": "g", "ge": "ge", "eq": "e", "ne": "ne"}
    return mapping.get(op_name, "e")


def _collect_strings_from_insns(insns: tuple[Insn, ...], ctx: _CodegenContext) -> None:
    for insn in insns:
        if not insn:
            continue
        op = insn[0]
        if op == "const" and isinstance(insn[1], str):
            ctx.add_string(insn[1])
        elif op == "define":
            _, _, _, _, _, _, body = insn
            _collect_strings_from_insns(tuple(body), ctx)
        elif op == "class_def":
            _, _, body_t = insn
            _collect_strings_from_insns(tuple(body_t), ctx)


def _build_struct_layouts(module_insns: tuple[Insn, ...], ctx: _CodegenContext) -> None:
    for insn in module_insns:
        if not insn:
            continue
        if insn[0] == "class_def":
            _, cname, body_t = insn
            layout = _StructLayout(name=cname)
            offset = 0
            for sub in body_t:
                if sub and sub[0] == "decl":
                    _, ty, fname = sub
                    layout.fields.append(_StructField(name=fname, ty=ty, offset=offset))
                    offset += 8
            layout.total_size = offset if offset > 0 else 8
            ctx.add_struct(layout)


def _sanitize_label(name: str) -> str:
    safe = "".join(c if c.isalnum() or c == "_" else f"_{ord(c)}_" for c in name)
    if safe[0].isdigit():
        safe = "_" + safe
    return f"kfn_{safe}"


def _scan_locals(
    insns: tuple[Insn, ...],
    slots: dict[str, _VarSlot],
    struct_vars: set[str],
    ctx: _CodegenContext,
    param_names: tuple[str, ...] = (),
) -> int:
    """扫描指令，为局部变量分配栈槽位。返回下一个可用偏移。"""
    offset = 8
    for pname in param_names:
        if pname not in slots:
            slots[pname] = _VarSlot(name=pname, offset=offset)
            offset += 8
    for insn in insns:
        if not insn:
            continue
        op = insn[0]
        if op == "decl":
            ty, name = insn[1], insn[2]
            if name not in slots:
                sl = ctx.get_struct(ty)
                if sl and sl.total_size > 0:
                    sz = (sl.total_size + 15) & ~15
                    if offset < 16:
                        offset = 16
                    struct_vars.add(name)
                    slots[name] = _VarSlot(name=name, offset=offset, size=sz)
                    offset += sz
                else:
                    slots[name] = _VarSlot(name=name, offset=offset)
                    offset += 8
        elif op == "store_decl_local":
            name = insn[1]
            if name not in slots:
                slots[name] = _VarSlot(name=name, offset=offset)
                offset += 8
    return offset


def _emit_malloc(lines: list[str], size: int, ctx: _CodegenContext) -> None:
    """生成调用 malloc(size) 并 push 结果的代码。"""
    ctx.note_malloc_used()
    if ctx.win64:
        lines.append("    ; malloc(%d)" % size)
        lines.append("    sub rsp, 32")
        lines.append("    mov ecx, %d" % size)
        lines.append("    call malloc")
        lines.append("    add rsp, 32")
    else:
        lines.append("    ; malloc(%d)" % size)
        lines.append("    mov edi, %d" % size)
        lines.append("    xor eax, eax")
        lines.append("    call malloc")
    lines.append("    push rax")


def _emit_free(lines: list[str], ctx: _CodegenContext) -> None:
    """生成 pop 指针并调用 free(ptr) 的代码。"""
    ctx.note_malloc_used()
    lines.append("    pop rdi")
    if ctx.win64:
        lines.append("    sub rsp, 32")
        lines.append("    mov rcx, rdi")
        lines.append("    call free")
        lines.append("    add rsp, 32")
    else:
        lines.append("    xor eax, eax")
        lines.append("    call free")


def _emit_function(
    func: _FuncInfo,
    ctx: _CodegenContext,
) -> list[str]:
    lines: list[str] = []
    func_label = _sanitize_label(func.name)
    lines.append(f"{func_label}:")

    local_slots: dict[str, _VarSlot] = {}
    struct_vars: set[str] = set()
    next_offset = _scan_locals(func.body_insns, local_slots, struct_vars, ctx, func.param_names)

    # 计算栈帧总大小
    total_local = 0
    for slot in local_slots.values():
        total_local += slot.size
    local_size = (total_local + 15) & ~15
    min_size = 32 if ctx.win64 else 0
    if local_size < min_size:
        local_size = min_size

    # Prologue
    lines.append("    push rbp")
    lines.append("    mov rbp, rsp")
    lines.append(f"    sub rsp, {local_size}")

    # 初始化参数到局部变量
    if func.param_names:
        param_regs = (["rcx", "rdx", "r8", "r9"] if ctx.win64
                      else ["rdi", "rsi", "rdx", "rcx", "r8", "r9"])
        for pi, pname in enumerate(func.param_names):
            if pname in local_slots:
                slot = local_slots[pname]
                if pi < len(param_regs):
                    lines.append(f"    mov [rbp - {slot.offset}], {param_regs[pi]}")
                else:
                    sp_offset = 16 + (pi - len(param_regs)) * 8
                    lines.append(f"    mov rax, [rbp + {sp_offset}]")
                    lines.append(f"    mov [rbp - {slot.offset}], rax")

    # 为 struct 变量分配堆内存（RAII 基础）
    for name in struct_vars:
        if name in local_slots:
            slot = local_slots[name]
            sl = ctx.get_struct(slot.size)
            if sl is None:
                # 通过变量类型查找
                for s in ctx._structs.values():
                    if s.total_size == slot.size or True:
                        sl = s
                        break
            alloc_size = sl.total_size if sl else slot.size
            # 调用 malloc
            ctx.note_malloc_used()
            lines.append(f"    ; malloc for struct {name} (size={alloc_size})")
            if ctx.win64:
                lines.append("    sub rsp, 32")
                lines.append(f"    mov ecx, {alloc_size}")
                lines.append("    call malloc")
                lines.append("    add rsp, 32")
            else:
                lines.append(f"    mov edi, {alloc_size}")
                lines.append("    xor eax, eax")
                lines.append("    call malloc")
            # 将返回的指针存入局部变量槽位
            lines.append(f"    mov [rbp - {slot.offset}], rax")
            # 记录为堆分配变量（用于 RAII 自动释放）
            ctx.add_heap_var(name)

    # 生成函数体指令
    body_lines, _ = _emit_insns(
        list(func.body_insns), local_slots, struct_vars, ctx
    )

    # RAII：在函数返回前释放所有堆分配变量
    raii_lines: list[str] = []
    if ctx._heap_vars:
        raii_lines.append("    ; RAII cleanup")
        raii_lines.append("    push rax              ; 保存返回值")
        for name in ctx._heap_vars:
            if name in local_slots:
                slot = local_slots[name]
                raii_lines.append(f"    mov rcx, [rbp - {slot.offset}]")
                raii_lines.append("    test rcx, rcx")
                raii_lines.append(f"    jz _skip_free_{func_label}_{slot.offset}")
                if ctx.win64:
                    raii_lines.append("    sub rsp, 32")
                    raii_lines.append("    call free")
                    raii_lines.append("    add rsp, 32")
                else:
                    raii_lines.append("    mov rdi, rcx")
                    raii_lines.append("    xor eax, eax")
                    raii_lines.append("    call free")
                raii_lines.append(f"_skip_free_{func_label}_{slot.offset}:")
        raii_lines.append("    pop rax               ; 恢复返回值")

    # 确保函数有返回
    has_ret = False
    for insn in reversed(list(func.body_insns)):
        if insn and insn[0] in ("ret", "retvoid", "jmp"):
            has_ret = True
            break

    if has_ret:
        # 在 body_lines 中寻找最后的 leave/ret 或 jmp，将 RAII 插入其前面
        insert_pos = len(body_lines)
        for idx in range(len(body_lines) - 1, -1, -1):
            stripped = body_lines[idx].strip()
            if stripped in ("leave", "ret") or stripped.startswith("jmp "):
                insert_pos = idx
            elif stripped and not stripped.startswith(";") and stripped not in ("leave", "ret"):
                break  # 非 epilogue 指令，停止
        # insert_pos 是第一个 epilogue 指令的位置
        body_lines = body_lines[:insert_pos] + raii_lines + body_lines[insert_pos:]
    else:
        # 没有显式返回，先 RAII 再 leave/ret
        lines.extend(body_lines)
        lines.extend(raii_lines)
        if func.returns_void:
            lines.append("    xor eax, eax")
        lines.append("    leave")
        lines.append("    ret")
        return lines

    lines.extend(body_lines)

    return lines


def _emit_insns(
    insns: list[Insn],
    locals_map: dict[str, _VarSlot],
    struct_vars: set[str],
    ctx: _CodegenContext,
) -> tuple[list[str], dict[str, int]]:
    lines: list[str] = []
    label_map: dict[str, int] = {}

    for i, insn in enumerate(insns):
        if insn and insn[0] == "label":
            label_map[insn[1]] = i

    i = 0
    while i < len(insns):
        insn = insns[i]
        if not insn:
            i += 1
            continue

        op = insn[0]

        if op == "label":
            lines.append(f"{_sanitize_label(insn[1])}:")

        elif op == "const":
            val = insn[1]
            if isinstance(val, bool):
                lines.append(f"    push {1 if val else 0}")
            elif isinstance(val, int):
                lines.append(f"    push {val}")
            elif isinstance(val, float):
                import struct
                b = struct.pack("<d", val)
                lo = int.from_bytes(b[:8], "little")
                lines.append(f"    mov rax, {lo}")
                lines.append(f"    push rax  ; float {val}")
            elif isinstance(val, str):
                sidx = ctx.add_string(val)
                lines.append(f"    push str_{sidx}")
            else:
                lines.append("    push 0")

        elif op == "load":
            name = insn[1]
            if name in locals_map:
                slot = locals_map[name]
                if name in struct_vars:
                    lines.append(f"    push qword [rbp - {slot.offset}]")
                else:
                    lines.append(f"    push qword [rbp - {slot.offset}]")
            else:
                slot = _VarSlot(name=name, offset=(len(locals_map) + 1) * 8)
                locals_map[name] = slot
                lines.append(f"    push qword [rbp - {slot.offset}]")

        elif op == "load_scoped":
            _, scope, name = insn
            full_name = f"{scope}__{name}"
            if full_name in locals_map:
                slot = locals_map[full_name]
                lines.append(f"    push qword [rbp - {slot.offset}]")
            else:
                slot = _VarSlot(name=full_name, offset=(len(locals_map) + 1) * 8)
                locals_map[full_name] = slot
                lines.append(f"    push qword [rbp - {slot.offset}]")

        elif op == "store":
            name = insn[1]
            if name in locals_map:
                slot = locals_map[name]
                lines.append("    pop rax")
                lines.append(f"    mov [rbp - {slot.offset}], rax")
            else:
                slot = _VarSlot(name=name, offset=(len(locals_map) + 1) * 8)
                locals_map[name] = slot
                lines.append("    pop rax")
                lines.append(f"    mov [rbp - {slot.offset}], rax")

        elif op == "store_scoped_assign":
            _, scope, name = insn
            full_name = f"{scope}__{name}"
            if full_name in locals_map:
                slot = locals_map[full_name]
                lines.append("    pop rax")
                lines.append(f"    mov [rbp - {slot.offset}], rax")
            else:
                slot = _VarSlot(name=full_name, offset=(len(locals_map) + 1) * 8)
                locals_map[full_name] = slot
                lines.append("    pop rax")
                lines.append(f"    mov [rbp - {slot.offset}], rax")

        elif op == "get_attr":
            attr = insn[1]
            found = False
            for sl in ctx._structs.values():
                off = sl.field_offset(attr)
                if off is not None:
                    lines.append("    pop rbx")
                    lines.append(f"    mov rax, [rbx + {off}]")
                    lines.append("    push rax")
                    found = True
                    break
            if not found:
                lines.append(f"    ; get_attr '{attr}' - struct layout unknown")
                lines.append("    pop rax")
                lines.append("    push 0")

        elif op == "set_attr":
            attr = insn[1]
            found = False
            for sl in ctx._structs.values():
                off = sl.field_offset(attr)
                if off is not None:
                    lines.append("    pop rax")
                    lines.append("    pop rbx")
                    lines.append(f"    mov [rbx + {off}], rax")
                    lines.append("    push 0  ; assign result")
                    found = True
                    break
            if not found:
                lines.append(f"    ; set_attr '{attr}' - struct layout unknown")
                lines.append("    pop rax")
                lines.append("    pop rbx")
                lines.append("    push 0")

        elif op == "binop":
            bn = insn[1]
            if bn in ("lt", "le", "gt", "ge", "eq", "ne"):
                cc = _cmp_nasm(bn)
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    cmp rax, rbx")
                lines.append(f"    set{cc} al")
                lines.append("    movzx eax, al")
                lines.append("    push rax")
            elif bn in ("flt", "fle", "fgt", "fge", "feq", "fne"):
                cc = _fcmp_nasm(bn)
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    movq xmm0, rax")
                lines.append("    movq xmm1, rbx")
                lines.append("    ucomisd xmm0, xmm1")
                lines.append(f"    set{cc} al")
                lines.append("    movzx eax, al")
                lines.append("    push rax")
            elif bn in ("fadd", "fsub", "fmul", "fdiv"):
                nasm_op = {"fadd": "addsd", "fsub": "subsd", "fmul": "mulsd", "fdiv": "divsd"}[bn]
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    movq xmm0, rax")
                lines.append("    movq xmm1, rbx")
                lines.append(f"    {nasm_op} xmm0, xmm1")
                lines.append("    movq rax, xmm0")
                lines.append("    push rax")
            elif bn == "div":
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    cqo")
                lines.append("    idiv rbx")
                lines.append("    push rax")
            elif bn == "mod":
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    cqo")
                lines.append("    idiv rbx")
                lines.append("    push rdx")
            else:
                nasm_op = _binop_nasm(bn)
                if nasm_op:
                    lines.append("    pop rbx")
                    lines.append("    pop rax")
                    lines.append(f"    {nasm_op} rax, rbx")
                    lines.append("    push rax")
                else:
                    lines.append(f"    ; unsupported binop: {bn}")

        elif op == "unary":
            un = insn[1]
            if un == "lnot":
                lines.append("    pop rax")
                lines.append("    test rax, rax")
                lines.append("    setz al")
                lines.append("    movzx eax, al")
                lines.append("    push rax")
            elif un == "fneg":
                lines.append("    pop rax")
                lines.append("    movq xmm0, rax")
                lines.append("    xorpd xmm0, [sign_mask]")
                lines.append("    movq rax, xmm0")
                lines.append("    push rax")
            elif un == "deref":
                lines.append("    pop rax")
                lines.append("    mov rax, [rax]")
                lines.append("    push rax")
            else:
                nasm_op = _unary_nasm(un)
                if nasm_op:
                    lines.append("    pop rax")
                    lines.append(f"    {nasm_op} rax")
                    lines.append("    push rax")
                else:
                    lines.append(f"    ; unsupported unary: {un}")

        elif op == "pop":
            lines.append("    add rsp, 8")

        elif op == "decl":
            ty, name = insn[1], insn[2]
            if name in locals_map:
                slot = locals_map[name]
                if name in struct_vars:
                    sz = slot.size
                    lines.append(f"    ; decl struct {ty} {name} (heap, size={sz})")
                    # 堆分配的 struct: 加载堆指针，清零堆内存
                    lines.append(f"    mov rdi, [rbp - {slot.offset}]")
                    lines.append("    xor eax, eax")
                    lines.append("    mov ecx, %d" % (sz // 8))
                    lines.append("    rep stosq")
                else:
                    lines.append(f"    mov qword [rbp - {slot.offset}], 0")

        elif op == "store_decl_local":
            name = insn[1]
            if name in locals_map:
                slot = locals_map[name]
                lines.append("    pop rax")
                lines.append(f"    mov [rbp - {slot.offset}], rax")

        elif op == "store_deref":
            lines.append("    pop rax")
            lines.append("    pop rbx")
            lines.append("    mov [rbx], rax")

        elif op == "delete":
            # Kval 的 delete：释放堆分配变量
            for name in insn[1:]:
                if name in locals_map and name in struct_vars:
                    slot = locals_map[name]
                    lines.append(f"    ; delete {name} (heap free)")
                    lines.append(f"    mov rcx, [rbp - {slot.offset}]")
                    lines.append("    test rcx, rcx")
                    lines.append("    jz _no_ptr_{slot.offset}")
                    if ctx.win64:
                        lines.append("    sub rsp, 32")
                        lines.append("    mov rcx, rcx")
                        lines.append("    call free")
                        lines.append("    add rsp, 32")
                    else:
                        lines.append("    mov rdi, rcx")
                        lines.append("    xor eax, eax")
                        lines.append("    call free")
                    lines.append(f"_no_ptr_{slot.offset}:")
                    lines.append(f"    mov qword [rbp - {slot.offset}], 0")

        elif op == "call":
            _, fname, nargs, kw_order = insn
            if tuple(kw_order):
                for _ in range(nargs):
                    lines.append("    add rsp, 8")
                lines.append("    push 0")
            elif fname == "print":
                ctx.main_has_print = True
                _emit_print_call(lines, nargs, ctx)
            else:
                _emit_func_call(lines, fname, nargs, ctx)

        elif op == "ret":
            lines.append("    pop rax")
            lines.append("    leave")
            lines.append("    ret")

        elif op == "retvoid":
            lines.append("    xor eax, eax")
            lines.append("    leave")
            lines.append("    ret")

        elif op == "jmp":
            lines.append(f"    jmp {_sanitize_label(insn[1])}")

        elif op == "jz":
            lines.append("    pop rax")
            lines.append("    test rax, rax")
            lines.append(f"    jz {_sanitize_label(insn[1])}")

        elif op == "jnz":
            lines.append("    pop rax")
            lines.append("    test rax, rax")
            lines.append(f"    jnz {_sanitize_label(insn[1])}")

        elif op == "define":
            lines.append(f"    ; define {insn[1]} (already collected)")

        elif op == "class_def":
            lines.append(f"    ; class_def {insn[1]} (layout recorded)")

        else:
            lines.append(f"    ; unknown insn: {op}")

        i += 1

    return lines, label_map


def _emit_print_call(lines: list[str], nargs: int, ctx: _CodegenContext) -> None:
    for _ in range(nargs):
        if ctx.win64:
            lines.append("    pop rdx")
            lines.append("    sub rsp, 32")
            lines.append("    lea rcx, [fmt_int]")
        else:
            lines.append("    pop rsi")
            lines.append("    lea rdi, [fmt_int]")
        lines.append("    xor eax, eax")
        lines.append("    call printf")
        if ctx.win64:
            lines.append("    add rsp, 32")
    lines.append("    push 0")


def _emit_func_call(
    lines: list[str],
    fname: str,
    nargs: int,
    ctx: _CodegenContext,
) -> None:
    func_label = _sanitize_label(fname)
    if ctx.win64:
        param_regs = ["rcx", "rdx", "r8", "r9"]
    else:
        param_regs = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]

    if nargs <= 2:
        if nargs >= 2:
            lines.append(f"    pop {param_regs[1]}")
        if nargs >= 1:
            lines.append(f"    pop {param_regs[0]}")
    elif nargs <= len(param_regs):
        temp = ["r10", "r11", "r12", "r13", "r14", "r15"][:nargs]
        for j in range(nargs - 1, -1, -1):
            lines.append(f"    pop {temp[j]}")
        for j in range(nargs):
            lines.append(f"    mov {param_regs[j]}, {temp[j]}")
    else:
        # 简化处理：直接压栈传参
        pass

    if ctx.win64:
        lines.append("    sub rsp, 32")
    lines.append(f"    call {func_label}")
    if ctx.win64:
        lines.append("    add rsp, 32")

    lines.append("    push rax")


def generate_nasm(
    module_insns: tuple[Insn, ...],
    *,
    win64: bool = False,
    macho: bool = False,
) -> str:
    ctx = _CodegenContext(win64=win64)

    _collect_strings_from_insns(module_insns, ctx)
    _build_struct_layouts(module_insns, ctx)

    top_insns: list[Insn] = []
    for insn in module_insns:
        if not insn:
            continue
        if insn[0] == "define":
            _, name, pnames, ptypes, void_i, tparams, body = insn
            _collect_strings_from_insns(tuple(body), ctx)
            ctx.funcs.append(_FuncInfo(
                name=name,
                param_names=tuple(pnames),
                body_insns=tuple(body),
                returns_void=bool(void_i),
                label=_sanitize_label(name),
            ))
            top_insns.append(insn)
        else:
            top_insns.append(insn)

    ctx.main_body = tuple(top_insns)

    if ctx.main_has_print or not ctx.str_literals:
        ctx.add_string("%d")

    # 预扫描所有函数中的 struct 使用，以决定是否需要 extern malloc/free
    for func in ctx.funcs:
        dummy_slots: dict[str, _VarSlot] = {}
        dummy_structs: set[str] = set()
        _scan_locals(func.body_insns, dummy_slots, dummy_structs, ctx)
        if dummy_structs:
            ctx.note_malloc_used()

    lines: list[str] = []
    extern_label = "_printf" if macho else "printf"
    entry_label = "_main" if macho else "main"

    lines.append("default rel")
    lines.append(f"extern {extern_label}")
    if ctx._has_malloc:
        lines.append("extern malloc")
        lines.append("extern free")
    lines.append("")

    # Data section
    lines.append("section .data")
    lines.append('    fmt_int db "%d", 10, 0')
    lines.append("    sign_mask dq 0x8000000000000000")
    for i, s in enumerate(ctx.str_literals):
        if s == "%d":
            continue
        b = s.encode("utf-8") + b"\n\0"
        bytes_str = ", ".join(str(x) for x in b)
        lines.append(f"    str_{i} db {bytes_str}")
    lines.append("")

    # Text section
    lines.append("section .text")
    for func in ctx.funcs:
        lines.append(f"global {func.label}")
    lines.append("")

    for func in ctx.funcs:
        fn_lines = _emit_function(func, ctx)
        lines.extend(fn_lines)
        lines.append("")

    # main 入口
    lines.append(f"global {entry_label}")
    lines.append(f"{entry_label}:")

    main_func = next((f for f in ctx.funcs if f.name == "main"), None)

    if main_func:
        lines.append("    push rbp")
        lines.append("    mov rbp, rsp")
        lines.append("    sub rsp, 32")
        lines.append(f"    call {main_func.label}")
        lines.append("    leave")
        lines.append("    ret")
    else:
        lines.append("    push rbp")
        lines.append("    mov rbp, rsp")
        lines.append("    sub rsp, 32")
        top_locals: dict[str, _VarSlot] = {}
        struct_vars: set[str] = set()
        _scan_locals(tuple(top_insns), top_locals, struct_vars, ctx)
        exec_insns = [insn for insn in top_insns if insn[0] not in ("define", "class_def")]
        body_lines, _ = _emit_insns(exec_insns, top_locals, struct_vars, ctx)
        lines.extend(body_lines)
        lines.append("    xor eax, eax")
        lines.append("    leave")
        lines.append("    ret")

    lines.append("")
    return "\n".join(lines) + "\n"
