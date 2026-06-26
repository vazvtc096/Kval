"""将 Kval ASM IR 指令编译为 C VM 可读的 .kir3 二进制格式。

两遍编译:
  Pass 1: 展平嵌套 define，记录 label 位置和 jump 回填点
  Pass 2: 回填所有跳转目标为 insn_buf 绝对偏移

格式结构:
  Header:      "KIR3" (4B) + version(2B) + n_funcs(2B) + n_insns(4B) + str_pool_sz(4B)
  FuncTable:   [name_off(4B) + n_params(2B) + insn_start(4B) + insn_end(4B)] × n_funcs
  Insns:       [opcode(1B) + args(变长)] × N
  StringPool:  UTF-8 字符串连续存放，以 \\0 分隔

C VM (kval_vm.c) 直接读取此格式并 switch-dispatch 执行。
"""

from __future__ import annotations

import struct
from typing import Sequence

from .Parser.AST.asm_ir import Insn
from .Parser.AST.Data import BinOperator, UnaryOperator

# ── Opcode 定义 ─────────────────────────────────────

OP_CONST_INT    = 0x01
OP_CONST_FLOAT  = 0x02
OP_CONST_STR    = 0x03
OP_CONST_BOOL   = 0x04
OP_CONST_NULL   = 0x05

OP_LOAD         = 0x10
OP_STORE        = 0x11
OP_STORE_DECL   = 0x12
OP_DECL_INT     = 0x13

OP_BINOP        = 0x20
OP_UNARY        = 0x21

OP_CALL         = 0x30
OP_PRINT        = 0x31

OP_JMP          = 0x40
OP_JZ           = 0x41
OP_JNZ          = 0x42

OP_RET          = 0x50
OP_RETVOID      = 0x51

OP_POP          = 0x60

OP_DEFINE       = 0x70

# ── Binop / Unary subop 映射 ───────────────────────

_BINOP_SUBOP = {
    BinOperator.add:     0x00,  BinOperator.sub:     0x01,
    BinOperator.mul:     0x02,  BinOperator.div:     0x03,
    BinOperator.mod:     0x04,
    BinOperator.lt:      0x05,  BinOperator.le:      0x06,
    BinOperator.gt:      0x07,  BinOperator.ge:      0x08,
    BinOperator.eq:      0x09,  BinOperator.ne:      0x0a,
    BinOperator.bitand:  0x0b,  BinOperator.bitor:   0x0c,
    BinOperator.bitxor:  0x0d,
    BinOperator.shl:     0x0e,  BinOperator.shr:     0x0f,
}

# ASM IR 使用字符串名 (BinOperator.xxx.name)，需要字符串映射
_STR_BINOP_SUBOP = {
    "add": 0x00, "sub": 0x01, "mul": 0x02, "div": 0x03, "mod": 0x04,
    "lt":  0x05, "le":  0x06, "gt":  0x07, "ge":  0x08, "eq": 0x09, "ne": 0x0a,
    "bitand": 0x0b, "bitor": 0x0c, "bitxor": 0x0d, "shl": 0x0e, "shr": 0x0f,
}

_FLOAT_BINOP_SUBOP = {
    "fadd": 0x10, "fsub": 0x11, "fmul": 0x12, "fdiv": 0x13,
    "flt":  0x14, "fle":  0x15, "fgt":  0x16, "fge":  0x17,
    "feq":  0x18, "fne":  0x19,
}

_UNARY_SUBOP = {
    UnaryOperator.neg:    0x00,  UnaryOperator.bitnot: 0x01,
    UnaryOperator.lnot:   0x02,
}

# ASM IR 使用字符串名 (UnaryOperator.xxx.name)
_STR_UNARY_SUBOP = {
    "neg": 0x00, "bitnot": 0x01, "lnot": 0x02,
}

_FLOAT_UNARY_SUBOP = {"fneg": 0x03}


# ── KIR3 两遍编译器 ─────────────────────────────────

class KIR3Emitter:
    """将 ASM IR 指令列表编译为 .kir3 二进制字节流（两遍编译）。"""

    def __init__(self):
        self._str_pool: list[str] = []
        self._str_offsets: dict[str, int] = {}
        self._insn_buf: bytearray = bytearray()

        # Pass 1 记录
        self._label_map: dict[str, int] = {}       # label名 → insn_buf偏移
        self._patch_list: list[tuple[int, str]] = [] # (insn_buf中的4B偏移, 目标label名)

        # 函数表
        self._functions: list[_FuncInfo] = []

    def _str_off(self, s: str) -> int:
        if s in self._str_offsets:
            return self._str_offsets[s]
        # 字符串池偏移 = 所有之前字符串的字节长度之和（含 \0）
        off = 0
        for prev in self._str_pool:
            off += len(prev.encode("utf-8")) + 1
        self._str_pool.append(s)
        self._str_offsets[s] = off
        return off

    # ── 低级写入 ──────────────────────────────────

    def _emit_u8(self, v: int) -> None:  self._insn_buf.append(v & 0xFF)
    def _emit_u16(self, v: int) -> None: self._insn_buf.extend(struct.pack("<H", v))
    def _emit_u32(self, v: int) -> None: self._insn_buf.extend(struct.pack("<I", v))
    def _emit_i64(self, v: int) -> None: self._insn_buf.extend(struct.pack("<q", v))
    def _emit_f64(self, v: float) -> None: self._insn_buf.extend(struct.pack("<d", v))

    # ── Pass 1: 展平 + 编码 + 记录回填点 ──────────

    def emit_insns(self, insns: Sequence[Insn]) -> None:
        """将一组 IR 指令编码到指令缓冲区（Pass 1）。"""
        for insn in insns:
            if not insn:
                continue
            self._emit_insn(insn)

    def _emit_insn(self, insn: Insn) -> None:
        op = insn[0]

        if op == "const":
            val = insn[1]
            if isinstance(val, bool):
                self._emit_u8(OP_CONST_BOOL); self._emit_u8(1 if val else 0)
            elif isinstance(val, int):
                self._emit_u8(OP_CONST_INT); self._emit_i64(val)
            elif isinstance(val, float):
                self._emit_u8(OP_CONST_FLOAT); self._emit_f64(val)
            elif isinstance(val, str):
                self._emit_u8(OP_CONST_STR); self._emit_u32(self._str_off(val))
            elif val is None:
                self._emit_u8(OP_CONST_NULL)
            else:
                raise TypeError(f"KIR3: unsupported const type {type(val)}")

        elif op == "load":
            self._emit_u8(OP_LOAD); self._emit_u32(self._str_off(insn[1]))

        elif op == "load_scoped":
            # C VM 用帧链查找，scope 自动决定
            self._emit_u8(OP_LOAD); self._emit_u32(self._str_off(insn[2]))

        elif op == "store":
            self._emit_u8(OP_STORE); self._emit_u32(self._str_off(insn[1]))

        elif op == "store_scoped_assign":
            self._emit_u8(OP_STORE); self._emit_u32(self._str_off(insn[2]))

        elif op == "store_scoped_decl":
            self._emit_u8(OP_STORE_DECL); self._emit_u32(self._str_off(insn[2]))

        elif op == "store_decl_local":
            self._emit_u8(OP_STORE_DECL); self._emit_u32(self._str_off(insn[1]))

        elif op == "decl":
            typ, name = insn[1], insn[2]
            if typ == "int":
                self._emit_u8(OP_DECL_INT); self._emit_u32(self._str_off(name))
            else:
                self._emit_u8(OP_CONST_NULL)
                self._emit_u8(OP_STORE_DECL); self._emit_u32(self._str_off(name))

        elif op == "binop":
            bo = insn[1]
            self._emit_u8(OP_BINOP)
            if isinstance(bo, BinOperator):
                subop = _BINOP_SUBOP.get(bo)
            elif isinstance(bo, str):
                subop = _STR_BINOP_SUBOP.get(bo)
                if subop is None:
                    subop = _FLOAT_BINOP_SUBOP.get(bo)
            else:
                subop = None
            if subop is None:
                raise TypeError(f"KIR3: unsupported binop {bo}")
            self._emit_u8(subop)

        elif op == "unary":
            uo = insn[1]
            self._emit_u8(OP_UNARY)
            if isinstance(uo, UnaryOperator):
                subop = _UNARY_SUBOP.get(uo)
            elif isinstance(uo, str):
                subop = _STR_UNARY_SUBOP.get(uo)
                if subop is None:
                    subop = _FLOAT_UNARY_SUBOP.get(uo)
            else:
                subop = None
            if subop is None:
                raise TypeError(f"KIR3: unsupported unary {uo}")
            self._emit_u8(subop)

        elif op == "call":
            fname, nargs = insn[1], insn[2]
            # print 是内置函数，发射 OP_PRINT
            if fname == "print":
                self._emit_u8(OP_PRINT)
            else:
                self._emit_u8(OP_CALL)
                self._emit_u32(self._str_off(fname))
                self._emit_u16(nargs)

        elif op == "print":
            self._emit_u8(OP_PRINT)

        elif op == "pop":
            self._emit_u8(OP_POP)

        elif op == "label":
            # label 不写入 insn_buf，只记录当前偏移
            self._label_map[insn[1]] = len(self._insn_buf)

        elif op == "jmp":
            self._emit_u8(OP_JMP)
            patch_pos = len(self._insn_buf)
            self._emit_u32(0)  # placeholder
            self._patch_list.append((patch_pos, insn[1]))

        elif op == "jz":
            self._emit_u8(OP_JZ)
            patch_pos = len(self._insn_buf)
            self._emit_u32(0)
            self._patch_list.append((patch_pos, insn[1]))

        elif op == "jnz":
            self._emit_u8(OP_JNZ)
            patch_pos = len(self._insn_buf)
            self._emit_u32(0)
            self._patch_list.append((patch_pos, insn[1]))

        elif op == "ret":
            self._emit_u8(OP_RET)

        elif op == "retvoid":
            self._emit_u8(OP_RETVOID)

        elif op == "define":
            _, name, pnames, ptypes, void_i, tparams, body_t = insn
            # 先记录 DEFINE opcode + 函数体起始位置
            define_start = len(self._insn_buf)
            self._emit_u8(OP_DEFINE)
            self._emit_u32(self._str_off(name))
            self._emit_u16(len(pnames))
            # body_start/body_end 占位 — Pass 2 回填
            body_start_pos = len(self._insn_buf)
            self._emit_u32(0)  # placeholder: body_start
            body_end_pos = len(self._insn_buf)
            self._emit_u32(0)  # placeholder: body_end

            # 参数名偏移量（每个 4B）
            for pname in pnames:
                self._emit_u32(self._str_off(pname))

            # 记录到函数表（insn_start/insn_end 用绝对偏移）
            body_actual_start = len(self._insn_buf)
            self.emit_insns(body_t)
            body_actual_end = len(self._insn_buf)

            # 回填 DEFINE 中的 body_start/body_end
            struct.pack_into("<I", self._insn_buf, body_start_pos, body_actual_start)
            struct.pack_into("<I", self._insn_buf, body_end_pos, body_actual_end)

            # 也注册到函数表（供 C VM 直接查找 main）
            self._functions.append(_FuncInfo(
                name_off=self._str_off(name),
                n_params=len(pnames),
                insn_start=body_actual_start,
                insn_end=body_actual_end,
                param_name_offs=[self._str_off(pn) for pn in pnames],
            ))

        elif op == "class_def":
            pass  # KIR3 v1 暂不支持

        elif op == "delete":
            pass  # KIR3 v1 暂不支持

        elif op == "var_scope_order":
            pass  # KIR3 v1 暂不支持

        else:
            raise NotImplementedError(f"KIR3: unknown opcode {op}")

    # ── Pass 2: 回填所有跳转目标 ──────────────────

    def _resolve_jumps(self) -> None:
        for patch_pos, label_name in self._patch_list:
            target = self._label_map.get(label_name)
            if target is None:
                raise ValueError(f"KIR3: unresolved label {label_name}")
            struct.pack_into("<I", self._insn_buf, patch_pos, target)

    # ── 组装最终二进制 ────────────────────────────

    def build(self) -> bytes:
        """组装完整的 .kir3 二进制文件（Pass 2 + 最终输出）。"""
        # Pass 2: 回填跳转目标
        self._resolve_jumps()

        # 构建字符串池
        str_pool = bytearray()
        for s in self._str_pool:
            str_pool.extend(s.encode("utf-8"))
            str_pool.append(0)  # null terminator

        # 组装 Header (16 bytes)
        header = struct.pack("<4sHHII",
            b"KIR3",
            1,                      # version
            len(self._functions),   # n_funcs
            len(self._insn_buf),    # n_insns
            len(str_pool),          # str_pool_sz
        )

        # 组装函数表 (每条: name_off(4) + n_params(2) + insn_start(4) + insn_end(4) + [param_name_off(4)]×n_params)
        func_table = bytearray()
        for fi in self._functions:
            func_table.extend(struct.pack("<IHII",
                fi.name_off, fi.n_params, fi.insn_start, fi.insn_end))
            for poff in fi.param_name_offs:
                func_table.extend(struct.pack("<I", poff))

        return bytes(header + func_table + self._insn_buf + str_pool)


class _FuncInfo:
    __slots__ = ("name_off", "n_params", "insn_start", "insn_end", "param_name_offs")
    def __init__(self, name_off: int, n_params: int, insn_start: int, insn_end: int,
                 param_name_offs: list[int] = None):
        self.name_off = name_off; self.n_params = n_params
        self.insn_start = insn_start; self.insn_end = insn_end
        self.param_name_offs = param_name_offs or []


def emit_kir3(module_insns: Sequence[Insn]) -> bytes:
    """从 Module 的 ASM IR 指令列表生成 .kir3 二进制。"""
    emitter = KIR3Emitter()
    emitter.emit_insns(module_insns)
    return emitter.build()
