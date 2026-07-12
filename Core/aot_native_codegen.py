"""将 ASM IR 指令编译为真正的 x64 NASM 汇编代码。

支持在运行时实际执行计算，而非仅编译时静态求值。
本模块修复了 Windows x64 下 push 64 位立即数导致的链接错误，
并正确实现了 print 内部函数（动态格式串 + 寄存器传参）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .Parser.AST.asm_ir import Insn
from .Parser.AST.Data import BinOperator


# ---------------------------------------------------------------------------
# 辅助数据结构
# ---------------------------------------------------------------------------

@dataclass
class _VarSlot:
    name: str
    offset: int          # rbp 相对偏移（rbp - offset）
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
    """汇编生成上下文，管理字符串常量、结构体布局、外部 DLL 函数等。"""
    win64: bool = False
    str_literals: list[str] = field(default_factory=list)
    funcs: list[_FuncInfo] = field(default_factory=list)
    main_body: tuple[Insn, ...] = ()
    _str_index: dict[str, int] = field(default_factory=dict, repr=False)
    _structs: dict[str, _StructLayout] = field(default_factory=dict, repr=False)
    _has_malloc: bool = field(default=False, repr=False)
    _heap_vars: set[str] = field(default_factory=set, repr=False)
    extern_dll_funcs: list[tuple[str, str, tuple[str, ...], tuple[str, ...], str, bool]] = field(
        default_factory=list, repr=False
    )
    extern_dll_names: dict[str, list[str]] = field(default_factory=dict, repr=False)

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


# ---------------------------------------------------------------------------
# 操作符 → NASM 助记符映射
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 预处理：收集字符串、结构体、外部函数
# ---------------------------------------------------------------------------

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
        elif op == "extern_dll":
            _, dll_path, func_tuple = insn
            for rt, fn, pt_tuple, pn_tuple, void_i in func_tuple:
                ctx.extern_dll_funcs.append((dll_path, fn, pt_tuple, pn_tuple, rt, bool(void_i)))
                ctx.extern_dll_names.setdefault(dll_path, []).append(fn)


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
    """将 Kval 函数名转换为合法的 NASM 标签。"""
    if name == 'main':
        return 'kfn_main'

    safe = "".join(c if c.isalnum() or c == "_" else f"_{ord(c)}_" for c in name)
    if safe[0].isdigit():
        safe = "_" + safe
    return safe


def _scan_locals(
    insns: tuple[Insn, ...],
    slots: dict[str, _VarSlot],
    struct_vars: set[str],
    ctx: _CodegenContext,
    param_names: tuple[str, ...] = (),
) -> int:
    """扫描指令，为局部变量分配栈槽位，返回下一个可用偏移。"""
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


# ---------------------------------------------------------------------------
# 内存管理辅助函数
# ---------------------------------------------------------------------------

def _emit_malloc(lines: list[str], size: int, ctx: _CodegenContext) -> None:
    ctx.note_malloc_used()
    if ctx.win64:
        lines.append("    sub rsp, 32")
        lines.append("    mov ecx, %d" % size)
        lines.append("    call malloc")
        lines.append("    add rsp, 32")
    else:
        lines.append("    mov edi, %d" % size)
        lines.append("    xor eax, eax")
        lines.append("    call malloc")
    lines.append("    push rax")


def _emit_free(lines: list[str], ctx: _CodegenContext) -> None:
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


# ---------------------------------------------------------------------------
# 函数整体编译
# ---------------------------------------------------------------------------

def _emit_function(func: _FuncInfo, ctx: _CodegenContext) -> list[str]:
    """生成一个 Kval 函数的 NASM 代码，包含栈帧、局部变量初始化、RAII 清理。"""
    lines: list[str] = []
    func_label = _sanitize_label(func.name)
    lines.append(f"{func_label}:")

    local_slots: dict[str, _VarSlot] = {}
    struct_vars: set[str] = set()
    next_offset = _scan_locals(func.body_insns, local_slots, struct_vars, ctx, func.param_names)

    total_local = 0
    for slot in local_slots.values():
        total_local += slot.size
    local_size = (total_local + 15) & ~15
    min_size = 32 if ctx.win64 else 0
    if local_size < min_size:
        local_size = min_size

    # prologue
    lines.append("    push rbp")
    lines.append("    mov rbp, rsp")
    lines.append(f"    sub rsp, {local_size}")

    # 初始化参数变量
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

    # 为 struct 变量堆分配内存
    for name in struct_vars:
        if name in local_slots:
            slot = local_slots[name]
            sl = None
            for s in ctx._structs.values():
                if s.total_size == slot.size or True:
                    sl = s
                    break
            alloc_size = sl.total_size if sl else slot.size
            ctx.note_malloc_used()
            if ctx.win64:
                lines.append("    sub rsp, 32")
                lines.append(f"    mov ecx, {alloc_size}")
                lines.append("    call malloc")
                lines.append("    add rsp, 32")
            else:
                lines.append(f"    mov edi, {alloc_size}")
                lines.append("    xor eax, eax")
                lines.append("    call malloc")
            lines.append(f"    mov [rbp - {slot.offset}], rax")
            ctx.add_heap_var(name)

    # 生成指令体
    body_lines, _ = _emit_insns(list(func.body_insns), local_slots, struct_vars, ctx)

    # RAII 释放堆变量
    raii_lines: list[str] = []
    if ctx._heap_vars:
        raii_lines.append("    push rax")
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
        raii_lines.append("    pop rax")

    has_ret = False
    for insn in reversed(list(func.body_insns)):
        if insn and insn[0] in ("ret", "retvoid", "jmp"):
            has_ret = True
            break

    if has_ret:
        # 将 RAII 插入到 epilogue 之前
        insert_pos = len(body_lines)
        for idx in range(len(body_lines) - 1, -1, -1):
            stripped = body_lines[idx].strip()
            if stripped in ("leave", "ret") or stripped.startswith("jmp "):
                insert_pos = idx
            elif stripped and not stripped.startswith(";") and stripped not in ("leave", "ret"):
                break
        body_lines = body_lines[:insert_pos] + raii_lines + body_lines[insert_pos:]
    else:
        lines.extend(body_lines)
        lines.extend(raii_lines)
        if func.returns_void:
            lines.append("    xor eax, eax")
        lines.append("    leave")
        lines.append("    ret")
        return lines

    lines.extend(body_lines)
    return lines


# ---------------------------------------------------------------------------
# 指令编译（核心）
# ---------------------------------------------------------------------------

def _emit_insns(
    insns: list[Insn],
    locals_map: dict[str, _VarSlot],
    struct_vars: set[str],
    ctx: _CodegenContext,
) -> tuple[list[str], dict[str, int]]:
    """将指令序列编译为 NASM 行列表。
    维护一个编译时类型栈 ty_stack，用于 print 等需要类型信息的指令。
    """
    lines: list[str] = []
    label_map: dict[str, int] = {}

    KVAL_INT = "int"
    KVAL_FLOAT = "float"
    KVAL_STR = "str"

    ty_stack: list[str] = []

    def push_int():
        ty_stack.append(KVAL_INT)

    def push_float():
        ty_stack.append(KVAL_FLOAT)

    def push_str():
        ty_stack.append(KVAL_STR)

    def pop_type() -> str:
        return ty_stack.pop() if ty_stack else KVAL_INT

    def pop_types(n: int) -> list[str]:
        types = [ty_stack.pop() for _ in range(n)]
        types.reverse()
        return types

    # 先收集标签位置
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
                push_int()
            elif isinstance(val, int):
                lines.append(f"    push {val}")
                push_int()
            elif isinstance(val, float):
                import struct
                b = struct.pack("<d", val)
                lo = int.from_bytes(b[:8], "little")
                lines.append(f"    mov rax, {lo}")
                lines.append("    push rax")
                push_float()
            elif isinstance(val, str):
                # 修复：x64 下不能 push 64 位立即数，必须先加载到寄存器
                sidx = ctx.add_string(val)
                lines.append(f"    lea rax, [rel str_{sidx}]")
                lines.append("    push rax")
                push_str()
            else:
                lines.append("    push 0")
                push_int()

        elif op == "load":
            name = insn[1]
            if name in locals_map:
                slot = locals_map[name]
                lines.append(f"    push qword [rbp - {slot.offset}]")
            else:
                slot = _VarSlot(name=name, offset=(len(locals_map) + 1) * 8)
                locals_map[name] = slot
                lines.append(f"    push qword [rbp - {slot.offset}]")
            push_int()

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
            push_int()

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
            pop_type()

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
            pop_type()

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
                lines.append("    pop rax")
                lines.append("    push 0")
            pop_type()
            push_int()

        elif op == "set_attr":
            attr = insn[1]
            found = False
            for sl in ctx._structs.values():
                off = sl.field_offset(attr)
                if off is not None:
                    lines.append("    pop rax")
                    lines.append("    pop rbx")
                    lines.append(f"    mov [rbx + {off}], rax")
                    lines.append("    push 0")
                    found = True
                    break
            if not found:
                lines.append("    pop rax")
                lines.append("    pop rbx")
                lines.append("    push 0")
            pop_type()
            pop_type()
            push_int()

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
                pop_type()
                pop_type()
                push_int()
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
                pop_type()
                pop_type()
                push_int()
            elif bn in ("fadd", "fsub", "fmul", "fdiv"):
                nasm_op = {"fadd": "addsd", "fsub": "subsd", "fmul": "mulsd", "fdiv": "divsd"}[bn]
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    movq xmm0, rax")
                lines.append("    movq xmm1, rbx")
                lines.append(f"    {nasm_op} xmm0, xmm1")
                lines.append("    movq rax, xmm0")
                lines.append("    push rax")
                pop_type()
                pop_type()
                push_float()
            elif bn == "div":
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    cqo")
                lines.append("    idiv rbx")
                lines.append("    push rax")
                pop_type()
                pop_type()
                push_int()
            elif bn == "mod":
                lines.append("    pop rbx")
                lines.append("    pop rax")
                lines.append("    cqo")
                lines.append("    idiv rbx")
                lines.append("    push rdx")
                pop_type()
                pop_type()
                push_int()
            else:
                nasm_op = _binop_nasm(bn)
                if nasm_op:
                    lines.append("    pop rbx")
                    lines.append("    pop rax")
                    lines.append(f"    {nasm_op} rax, rbx")
                    lines.append("    push rax")
                    pop_type()
                    pop_type()
                    push_int()
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
                pop_type()
                push_int()
            elif un == "fneg":
                lines.append("    pop rax")
                lines.append("    movq xmm0, rax")
                lines.append("    xorpd xmm0, [sign_mask]")
                lines.append("    movq rax, xmm0")
                lines.append("    push rax")
                pop_type()
                push_float()
            elif un == "deref":
                lines.append("    pop rax")
                lines.append("    mov rax, [rax]")
                lines.append("    push rax")
                pop_type()
                push_int()
            else:
                nasm_op = _unary_nasm(un)
                if nasm_op:
                    lines.append("    pop rax")
                    lines.append(f"    {nasm_op} rax")
                    lines.append("    push rax")
                    pop_type()
                    push_int()
                else:
                    lines.append(f"    ; unsupported unary: {un}")

        elif op == "pop":
            lines.append("    add rsp, 8")
            pop_type()

        elif op == "decl":
            ty, name = insn[1], insn[2]
            if name in locals_map:
                slot = locals_map[name]
                if name in struct_vars:
                    sz = slot.size
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
                pop_type()

        elif op == "store_deref":
            lines.append("    pop rax")
            lines.append("    pop rbx")
            lines.append("    mov [rbx], rax")
            pop_type()
            pop_type()

        elif op == "delete":
            for name in insn[1:]:
                if name in locals_map and name in struct_vars:
                    slot = locals_map[name]
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
                # 关键字参数暂不处理，直接弹出并压入占位值
                for _ in range(nargs):
                    lines.append("    add rsp, 8")
                    pop_type()
                lines.append("    push 0")
                push_int()
            elif fname == "print":
                # 利用类型栈生成正确的 printf 调用
                arg_types = pop_types(nargs)
                _emit_print_call(lines, arg_types, ctx)
                push_int()
            else:
                for _ in range(nargs):
                    pop_type()
                _emit_func_call(lines, fname, nargs, ctx)
                push_int()

        elif op == "ret":
            lines.append("    pop rax")
            lines.append("    leave")
            lines.append("    ret")
            pop_type()

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
            pop_type()

        elif op == "jnz":
            lines.append("    pop rax")
            lines.append("    test rax, rax")
            lines.append(f"    jnz {_sanitize_label(insn[1])}")
            pop_type()

        elif op == "define":
            lines.append(f"    ; define {insn[1]}")

        elif op == "class_def":
            lines.append(f"    ; class_def {insn[1]}")

        elif op == "extern_dll":
            lines.append(f"    ; extern_dll {insn[1]}")

        else:
            lines.append(f"    ; unknown insn: {op}")

        i += 1

    return lines, label_map


# ---------------------------------------------------------------------------
# 库函数调用生成
# ---------------------------------------------------------------------------

def _emit_print_call(lines: list[str], arg_types: list[str], ctx: _CodegenContext) -> None:
    """根据参数类型动态构造格式串，生成一次 printf 调用。
    遵循 Win64 / SysV 调用约定，格式串放入第一个寄存器，
    其余参数依次使用寄存器，超出部分通过栈传递。
    """
    nargs = len(arg_types)
    if nargs == 0:
        return

    # 1. 动态构造格式串（如 "%s %d"）
    fmt_parts = []
    for t in arg_types:
        if t == "int":
            fmt_parts.append("%d")
        elif t == "float":
            fmt_parts.append("%f")
        elif t == "str":
            fmt_parts.append("%s")
        else:
            fmt_parts.append("%d")
    fmt_str = " ".join(fmt_parts) + "\n"
    fmt_idx = ctx.add_string(fmt_str)  # 数据段生成时会自动追加 '\0'

    # 2. 寄存器约定
    if ctx.win64:
        regs = ["rcx", "rdx", "r8", "r9"]
        shadow = 32
    else:
        regs = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
        shadow = 0

    # 第一个参数固定为格式串，剩余的用于实际参数
    max_reg_args = len(regs) - 1
    reg_args = min(nargs, max_reg_args)
    overflow = nargs - reg_args

    # 临时寄存器分配
    temp = ["r10", "r11", "r12", "r13", "r14", "r15"][:nargs + 1]
    fmt_temp = temp[0]
    arg_temps = temp[1:]

    # 3. 将格式串地址加载到临时寄存器，并从栈弹出参数到临时寄存器
    lines.append(f"    lea {fmt_temp}, [rel str_{fmt_idx}]")
    for i in range(nargs - 1, -1, -1):
        lines.append(f"    pop {arg_temps[i]}")

    # 4. 分配栈空间（影子空间 + 溢出参数）
    stack_space = shadow + overflow * 8
    stack_space = (stack_space + 15) & ~15
    if stack_space > 0:
        lines.append(f"    sub rsp, {stack_space}")

    # 5. 移动参数到正式位置
    lines.append(f"    mov {regs[0]}, {fmt_temp}")
    for i in range(reg_args):
        lines.append(f"    mov {regs[i + 1]}, {arg_temps[i]}")
    for i in range(overflow):
        lines.append(f"    mov [rsp + {shadow + i * 8}], {arg_temps[reg_args + i]}")

    # 6. 调用 printf
    lines.append("    xor eax, eax")     # 可变参数函数约定：al = 使用的向量寄存器数
    lines.append("    call printf")

    # 7. 恢复栈
    if stack_space > 0:
        lines.append(f"    add rsp, {stack_space}")

    # print 不产生返回值，但 IR 需要栈上留一个占位值
    lines.append("    push 0")


def _emit_func_call(lines: list[str], fname: str, nargs: int, ctx: _CodegenContext) -> None:
    """生成普通函数调用，参数从栈弹出并按调用约定传递。"""
    is_extern = any(fn == fname for _, fn, _, _, _, _ in ctx.extern_dll_funcs)
    func_label = fname if is_extern else _sanitize_label(fname)

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
        # 超出寄存器数量的参数已在栈上（调用者负责清理）
        pass

    if ctx.win64:
        lines.append("    sub rsp, 32")
    lines.append(f"    call {func_label}")
    if ctx.win64:
        lines.append("    add rsp, 32")

    lines.append("    push rax")


# ---------------------------------------------------------------------------
# 顶层入口：生成完整 NASM 文件
# ---------------------------------------------------------------------------

def _build_code_lines(
    ctx: _CodegenContext,
    top_insns: list[Insn],
    main_func: _FuncInfo | None,
    output_type: str,
    macho: bool,
    entry_label: str,
) -> list[str]:
    """生成所有代码段行（函数体 + 入口点），同时会触发 ctx.add_string 收集缺失的字符串。"""
    code_lines: list[str] = []

    # 输出各函数
    for func in ctx.funcs:
        fn_lines = _emit_function(func, ctx)
        code_lines.extend(fn_lines)
        code_lines.append("")

    # 入口点
    if output_type == "dll":
        code_lines.append("global DllMain")
        code_lines.append("global kval_main")
        if main_func:
            for func in ctx.funcs:
                if func.name != "main":
                    code_lines.append(f"global {func.label}")
        code_lines.append("")
        code_lines.append("DllMain:")
        code_lines.append("    mov rax, 1")
        code_lines.append("    ret")
        code_lines.append("")
        code_lines.append("kval_main:")
        code_lines.append("    push rbp")
        code_lines.append("    mov rbp, rsp")
        code_lines.append("    sub rsp, 32")
        if main_func:
            code_lines.append(f"    call {main_func.label}")
        else:
            top_locals: dict[str, _VarSlot] = {}
            struct_vars: set[str] = set()
            _scan_locals(tuple(top_insns), top_locals, struct_vars, ctx)
            exec_insns = [insn for insn in top_insns if insn[0] not in ("define", "class_def")]
            body_lines, _ = _emit_insns(exec_insns, top_locals, struct_vars, ctx)
            code_lines.extend(body_lines)
        code_lines.append("    leave")
        code_lines.append("    ret")
    else:
        code_lines.append(f"global {entry_label}")
        code_lines.append(f"{entry_label}:")
        if main_func:
            code_lines.append("    push rbp")
            code_lines.append("    mov rbp, rsp")
            code_lines.append("    sub rsp, 32")
            code_lines.append(f"    call {main_func.label}")
            code_lines.append("    leave")
            code_lines.append("    ret")
        else:
            code_lines.append("    push rbp")
            code_lines.append("    mov rbp, rsp")
            code_lines.append("    sub rsp, 32")
            top_locals2: dict[str, _VarSlot] = {}
            struct_vars2: set[str] = set()
            _scan_locals(tuple(top_insns), top_locals2, struct_vars2, ctx)
            exec_insns2 = [insn for insn in top_insns if insn[0] not in ("define", "class_def")]
            body_lines2, _ = _emit_insns(exec_insns2, top_locals2, struct_vars2, ctx)
            code_lines.extend(body_lines2)
            code_lines.append("    xor eax, eax")
            code_lines.append("    leave")
            code_lines.append("    ret")

    return code_lines


def generate_nasm(
    module_insns: tuple[Insn, ...],
    *,
    win64: bool = False,
    macho: bool = False,
    output_type: str = "exe",
) -> str:
    """将整个模块的 IR 转换为 NASM 汇编源码字符串。"""
    ctx = _CodegenContext(win64=win64)

    _collect_strings_from_insns(module_insns, ctx)
    _build_struct_layouts(module_insns, ctx)

    # 分离顶层指令和函数定义
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

    # 预扫描函数，决定是否需要 malloc/free
    for func in ctx.funcs:
        dummy_slots: dict[str, _VarSlot] = {}
        dummy_structs: set[str] = set()
        _scan_locals(func.body_insns, dummy_slots, dummy_structs, ctx)
        if dummy_structs:
            ctx.note_malloc_used()

    extern_label = "_printf" if macho else "printf"
    entry_label = "_main" if macho else "main"
    main_func = next((f for f in ctx.funcs if f.name == "main"), None)

    # 第一遍：仅收集字符串（运行代码生成但丢弃结果）
    _build_code_lines(ctx, top_insns, main_func, output_type, macho, entry_label)

    # 构建最终输出
    lines: list[str] = []

    # 头部：外部符号声明
    lines.append("default rel")
    lines.append(f"extern {extern_label}")
    if ctx._has_malloc:
        lines.append("extern malloc")
        lines.append("extern free")
    if output_type == "dll" and win64:
        lines.append("extern ExitProcess")
    for _, func_name, _, _, _, _ in ctx.extern_dll_funcs:
        lines.append(f"extern {func_name}")
    lines.append("")

    # 数据段（此时 ctx.str_literals 已完整）
    lines.append("section .data")
    lines.append("    sign_mask dq 0x8000000000000000")
    for i, s in enumerate(ctx.str_literals):
        b = s.encode("utf-8") + b"\0"
        bytes_str = ", ".join(str(x) for x in b)
        lines.append(f"    str_{i} db {bytes_str}")
    lines.append("")

    # 代码段头部
    lines.append("section .text")
    for func in ctx.funcs:
        lines.append(f"global {func.label}")
    lines.append("")

    # 第二遍：正式生成代码段
    code_lines = _build_code_lines(ctx, top_insns, main_func, output_type, macho, entry_label)
    lines.extend(code_lines)

    lines.append("")
    return "\n".join(lines) + "\n"