/*
 * kval_vm.c — Kval RPN 字节码虚拟机 (C 实现)
 *
 * 读取 .kir3 二进制文件并执行栈式指令。
 * 替代 Python InsnVM，消除 if/elif 字符串 dispatch 开销。
 *
 * 二进制格式 (KIR3):
 *   Header:      "KIR3" (4B) + version(2B) + n_funcs(2B) + n_insns(4B) + str_pool_sz(4B)
 *   FuncTable:   [name_off(4B) + n_params(2B) + insn_start(4B) + insn_end(4B)] × n_funcs
 *   Insns:       [opcode(1B) + args(变长)] × n_insns
 *   StringPool:  UTF-8 字符串连续存放，以 \0 分隔
 *
 * Opcode 编码:
 *   0x01 CONST_INT    arg: int64(8B)
 *   0x02 CONST_FLOAT  arg: float64(8B)
 *   0x03 CONST_STR    arg: str_off(4B)
 *   0x04 CONST_BOOL   arg: val(1B)
 *   0x05 CONST_NULL   arg: none
 *   0x10 LOAD         arg: str_off(4B)
 *   0x11 STORE        arg: str_off(4B)
 *   0x12 STORE_DECL   arg: str_off(4B)
 *   0x13 DECL_INT     arg: str_off(4B)  (declare int var = 0)
 *   0x20 BINOP        arg: subop(1B)
 *   0x21 UNARY        arg: subop(1B)
 *   0x30 CALL         arg: str_off(4B) + n_args(2B)
 *   0x31 PRINT        arg: none
 *   0x40 JMP          arg: insn_idx(4B)
 *   0x41 JZ           arg: insn_idx(4B)
 *   0x42 JNZ          arg: insn_idx(4B)
 *   0x50 RET          arg: none
 *   0x51 RETVOID      arg: none
 *   0x60 POP          arg: none
 *   0x70 DEFINE       arg: name_off(4B) + n_params(2B) + body_start(4B) + body_end(4B)
 *
 * Binop subops:
 *   0x00 add   0x01 sub   0x02 mul   0x03 div   0x04 mod
 *   0x05 lt    0x06 le    0x07 gt    0x08 ge    0x09 eq    0x0a ne
 *   0x0b bitand 0x0c bitor 0x0d bitxor  0x0e shl  0x0f shr
 *   0x10 fadd  0x11 fsub  0x12 fmul  0x13 fdiv
 *   0x14 flt   0x15 fle   0x16 fgt   0x17 fge  0x18 feq   0x19 fne
 *
 * Unary subops:
 *   0x00 neg   0x01 bitnot   0x02 lnot   0x03 fneg
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>

/* ── 值类型 ────────────────────────────────────── */

typedef enum {
    VT_INT   = 0,
    VT_FLOAT = 1,
    VT_STR   = 2,
    VT_BOOL  = 3,
    VT_NULL  = 4,
    VT_FUNC  = 5,
} ValType;

typedef struct {
    ValType type;
    int64_t ival;
    double   fval;
    uint32_t sval_off;   /* string pool offset */
    uint32_t func_idx;   /* function table index */
} KVal;

/* ── 函数表 ────────────────────────────────────── */

typedef struct {
    uint32_t name_off;
    uint16_t n_params;
    uint32_t insn_start;
    uint32_t insn_end;
    uint32_t *param_name_offs;  /* 动态分配的参数名偏移数组 */
} FuncEntry;

/* ── 调用帧 ────────────────────────────────────── */

#define MAX_LOCALS 256

typedef struct CallFrame {
    uint32_t func_idx;
    uint32_t ip;
    int      n_locals;
    KVal     locals[MAX_LOCALS];
    char     local_names[MAX_LOCALS][64];  /* 简化: 变量名最长 63 字符 */
    struct CallFrame *prev;
} CallFrame;

/* ── VM 核心 ────────────────────────────────────── */

#define STACK_SIZE 4096

typedef struct {
    KVal        stack[STACK_SIZE];
    int         sp;

    uint8_t    *insns;
    uint32_t    n_insns;

    char       *str_pool;
    uint32_t    str_pool_sz;

    FuncEntry  *funcs;
    uint16_t    n_funcs;

    CallFrame  *frame;

    KVal        return_value;   /* 最近一次函数调用的返回值 */
} VM;

/* ── 辅助函数 ────────────────────────────────────── */

static const char *str_at(VM *vm, uint32_t off) {
    if (off >= vm->str_pool_sz) return "<bad_str_off>";
    return vm->str_pool + off;
}

static KVal mk_int(int64_t v)    { KVal k; k.type = VT_INT;   k.ival = v; return k; }
static KVal mk_float(double v)   { KVal k; k.type = VT_FLOAT; k.fval = v; return k; }
static KVal mk_str(uint32_t off) { KVal k; k.type = VT_STR;   k.sval_off = off; return k; }
static KVal mk_bool(int v)       { KVal k; k.type = VT_BOOL;  k.ival = v; return k; }
static KVal mk_null(void)        { KVal k; k.type = VT_NULL;  return k; }
static KVal mk_func(uint32_t fi) { KVal k; k.type = VT_FUNC;  k.func_idx = fi; return k; }

static void push(VM *vm, KVal v) {
    if (vm->sp >= STACK_SIZE) { fprintf(stderr, "VM stack overflow\n"); exit(1); }
    vm->stack[vm->sp++] = v;
}

static KVal pop(VM *vm) {
    if (vm->sp <= 0) { fprintf(stderr, "VM stack underflow\n"); exit(1); }
    return vm->stack[--vm->sp];
}

static int kv_truthy(KVal v) {
    switch (v.type) {
        case VT_INT:   return v.ival != 0;
        case VT_FLOAT: return v.fval != 0.0;
        case VT_BOOL:  return v.ival != 0;
        case VT_STR:   return 1; /* non-null string is truthy */
        case VT_NULL:  return 0;
        default:       return 1;
    }
}

static int find_local(CallFrame *f, const char *name) {
    for (int i = 0; i < f->n_locals; i++) {
        if (strcmp(f->local_names[i], name) == 0) return i;
    }
    return -1;
}

static int declare_local(CallFrame *f, const char *name) {
    int idx = find_local(f, name);
    if (idx >= 0) return idx;
    if (f->n_locals >= MAX_LOCALS) {
        fprintf(stderr, "too many locals in function\n"); exit(1);
    }
    idx = f->n_locals++;
    strncpy(f->local_names[idx], name, 63);
    f->local_names[idx][63] = '\0';
    f->locals[idx] = mk_null();
    return idx;
}

static void print_val(KVal v) {
    switch (v.type) {
        case VT_INT:   printf("%" PRId64 "\n", v.ival); break;
        case VT_FLOAT: printf("%.6g\n", v.fval); break;
        case VT_STR:   printf("%s\n", str_at(NULL, v.sval_off)); break;  /* VM ptr needed for str — see below */
        case VT_BOOL:  printf("%s\n", v.ival ? "true" : "false"); break;
        case VT_NULL:  printf("null\n"); break;
        default:       printf("<val type=%d>\n", v.type); break;
    }
}

/* ── 帧管理 ────────────────────────────────────── */

static CallFrame *new_frame(VM *vm, uint32_t func_idx) {
    CallFrame *f = (CallFrame *)calloc(1, sizeof(CallFrame));
    f->func_idx = func_idx;
    f->ip = vm->funcs[func_idx].insn_start;
    f->prev = vm->frame;
    vm->frame = f;
    return f;
}

static void pop_frame(VM *vm) {
    CallFrame *f = vm->frame;
    if (!f) return;
    vm->frame = f->prev;
    free(f);
}

/* ── 指令读取辅助 ──────────────────────────────── */

static uint8_t  read_u8(VM *vm, uint32_t *ip)  { return vm->insns[(*ip)++]; }
static uint16_t read_u16(VM *vm, uint32_t *ip) {
    uint16_t v = vm->insns[*ip] | (vm->insns[*ip+1] << 8);
    *ip += 2; return v;
}
static uint32_t read_u32(VM *vm, uint32_t *ip) {
    uint32_t v = vm->insns[*ip]
              | (vm->insns[*ip+1] << 8)
              | (vm->insns[*ip+2] << 16)
              | (vm->insns[*ip+3] << 24);
    *ip += 4; return v;
}
static int64_t read_i64(VM *vm, uint32_t *ip) {
    int64_t v = 0;
    for (int i = 0; i < 8; i++) v |= ((int64_t)vm->insns[*ip + i]) << (i * 8);
    *ip += 8; return v;
}
static double read_f64(VM *vm, uint32_t *ip) {
    double v;
    memcpy(&v, vm->insns + *ip, 8);
    *ip += 8; return v;
}

/* ── 主执行循环 ────────────────────────────────── */

static int vm_run_func(VM *vm, uint32_t func_idx, KVal *args, int n_args) {
    FuncEntry *fe = &vm->funcs[func_idx];
    CallFrame *f = new_frame(vm, func_idx);

    /* 传参 — 用参数的真实名称 */
    for (int i = 0; i < n_args && i < fe->n_params; i++) {
        const char *pname = str_at(vm, fe->param_name_offs[i]);
        int idx = declare_local(f, pname);
        f->locals[idx] = args[i];
    }

    /* 执行函数体 */
    uint32_t end = fe->insn_end;
    int ret_code = 0;

    while (f->ip < end) {
        uint8_t op = read_u8(vm, &f->ip);

        switch (op) {

        /* ─── 常量 ─── */
        case 0x01: /* CONST_INT */
            push(vm, mk_int(read_i64(vm, &f->ip)));
            break;
        case 0x02: /* CONST_FLOAT */
            push(vm, mk_float(read_f64(vm, &f->ip)));
            break;
        case 0x03: /* CONST_STR */
            push(vm, mk_str(read_u32(vm, &f->ip)));
            break;
        case 0x04: /* CONST_BOOL */
            push(vm, mk_bool(read_u8(vm, &f->ip)));
            break;
        case 0x05: /* CONST_NULL */
            push(vm, mk_null());
            break;

        /* ─── 变量存取 ─── */
        case 0x10: /* LOAD */
        {
            const char *name = str_at(vm, read_u32(vm, &f->ip));
            /* 查找局部变量，若找不到则查全局（顶层帧） */
            int idx = find_local(f, name);
            if (idx >= 0) {
                push(vm, f->locals[idx]);
            } else {
                /* 查找外层帧（模拟作用域链） */
                CallFrame *outer = f->prev;
                while (outer) {
                    idx = find_local(outer, name);
                    if (idx >= 0) { push(vm, outer->locals[idx]); goto load_done; }
                    outer = outer->prev;
                }
                fprintf(stderr, "undefined variable: %s\n", name);
                exit(1);
            }
            load_done: break;
        }
        case 0x11: /* STORE */
        {
            const char *name = str_at(vm, read_u32(vm, &f->ip));
            KVal v = pop(vm);
            int idx = find_local(f, name);
            if (idx >= 0) f->locals[idx] = v;
            else {
                /* 查外层 */
                CallFrame *outer = f->prev;
                while (outer) {
                    idx = find_local(outer, name);
                    if (idx >= 0) { outer->locals[idx] = v; goto store_done; }
                    outer = outer->prev;
                }
                fprintf(stderr, "store: undefined variable %s\n", name);
                exit(1);
            }
            store_done: break;
        }
        case 0x12: /* STORE_DECL */
        {
            const char *name = str_at(vm, read_u32(vm, &f->ip));
            KVal v = pop(vm);
            int idx = declare_local(f, name);
            f->locals[idx] = v;
            break;
        }
        case 0x13: /* DECL_INT */
        {
            const char *name = str_at(vm, read_u32(vm, &f->ip));
            int idx = declare_local(f, name);
            f->locals[idx] = mk_int(0);
            break;
        }

        /* ─── 二元运算 ─── */
        case 0x20: /* BINOP */
        {
            uint8_t subop = read_u8(vm, &f->ip);
            KVal b = pop(vm), a = pop(vm);
            switch (subop) {
                /* 整数运算 */
                case 0x00: push(vm, mk_int(a.ival + b.ival)); break;
                case 0x01: push(vm, mk_int(a.ival - b.ival)); break;
                case 0x02: push(vm, mk_int(a.ival * b.ival)); break;
                case 0x03: push(vm, mk_int(a.ival / b.ival)); break;
                case 0x04: push(vm, mk_int(a.ival % b.ival)); break;
                /* 整数比较 (结果为 int: 1 或 0) */
                case 0x05: push(vm, mk_int(a.ival <  b.ival)); break;
                case 0x06: push(vm, mk_int(a.ival <= b.ival)); break;
                case 0x07: push(vm, mk_int(a.ival >  b.ival)); break;
                case 0x08: push(vm, mk_int(a.ival >= b.ival)); break;
                case 0x09: push(vm, mk_int(a.ival == b.ival)); break;
                case 0x0a: push(vm, mk_int(a.ival != b.ival)); break;
                /* 位运算 */
                case 0x0b: push(vm, mk_int(a.ival & b.ival)); break;
                case 0x0c: push(vm, mk_int(a.ival | b.ival)); break;
                case 0x0d: push(vm, mk_int(a.ival ^ b.ival)); break;
                case 0x0e: push(vm, mk_int(a.ival << b.ival)); break;
                case 0x0f: push(vm, mk_int(a.ival >> b.ival)); break;
                /* 浮点运算 */
                case 0x10: push(vm, mk_float(a.fval + b.fval)); break;
                case 0x11: push(vm, mk_float(a.fval - b.fval)); break;
                case 0x12: push(vm, mk_float(a.fval * b.fval)); break;
                case 0x13: push(vm, mk_float(a.fval / b.fval)); break;
                case 0x14: push(vm, mk_int(a.fval <  b.fval)); break;
                case 0x15: push(vm, mk_int(a.fval <= b.fval)); break;
                case 0x16: push(vm, mk_int(a.fval >  b.fval)); break;
                case 0x17: push(vm, mk_int(a.fval >= b.fval)); break;
                case 0x18: push(vm, mk_int(a.fval == b.fval)); break;
                case 0x19: push(vm, mk_int(a.fval != b.fval)); break;
                default:
                    fprintf(stderr, "unknown binop subop: 0x%02x\n", subop);
                    exit(1);
            }
            break;
        }

        /* ─── 一元运算 ─── */
        case 0x21: /* UNARY */
        {
            uint8_t subop = read_u8(vm, &f->ip);
            KVal a = pop(vm);
            switch (subop) {
                case 0x00: push(vm, mk_int(-a.ival)); break;
                case 0x01: push(vm, mk_int(~a.ival)); break;
                case 0x02: push(vm, mk_int(!kv_truthy(a))); break;
                case 0x03: push(vm, mk_float(-a.fval)); break;
                default:
                    fprintf(stderr, "unknown unary subop: 0x%02x\n", subop);
                    exit(1);
            }
            break;
        }

        /* ─── 函数调用 ─── */
        case 0x30: /* CALL */
        {
            uint32_t name_off = read_u32(vm, &f->ip);
            uint16_t n_args = read_u16(vm, &f->ip);
            const char *fname = str_at(vm, name_off);

            /* 收集参数（栈上顺序与调用顺序一致） */
            KVal args[32];
            for (int i = n_args - 1; i >= 0; i--) args[i] = pop(vm);

            /* 查找函数 — 先查局部，再查全局帧 */
            uint32_t fi = UINT32_MAX;
            CallFrame *search = f;
            while (search) {
                int idx = find_local(search, fname);
                if (idx >= 0 && search->locals[idx].type == VT_FUNC) {
                    fi = search->locals[idx].func_idx;
                    goto call_found;
                }
                search = search->prev;
            }
            /* 还没找到 — 查函数表 */
            for (uint16_t i = 0; i < vm->n_funcs; i++) {
                if (strcmp(str_at(vm, vm->funcs[i].name_off), fname) == 0) {
                    fi = i;
                    goto call_found;
                }
            }
            /* 内置函数: print 已单独处理 */
            fprintf(stderr, "call: unknown function %s\n", fname);
            exit(1);

            call_found:
            vm_run_func(vm, fi, args, n_args);
            push(vm, vm->return_value);  /* 统一在这里 push 返回值 */
            break;
        }

        /* ─── PRINT ─── */
        case 0x31: /* PRINT — pop value, print it, push 0 (void return) */
        {
            KVal v = pop(vm);
            switch (v.type) {
                case VT_INT:   printf("%" PRId64 "\n", v.ival); break;
                case VT_FLOAT: printf("%.6g\n", v.fval); break;
                case VT_BOOL:  printf("%s\n", v.ival ? "true" : "false"); break;
                case VT_STR:   printf("%s\n", str_at(vm, v.sval_off)); break;
                case VT_NULL:  printf("null\n"); break;
                default:       printf("<val>\n"); break;
            }
            push(vm, mk_int(0));  /* print returns void → 后续 pop 不会 underflow */
            break;
        }

        /* ─── 控制流 ─── */
        case 0x40: /* JMP */
            f->ip = read_u32(vm, &f->ip);
            break;
        case 0x41: /* JZ */
        {
            uint32_t target = read_u32(vm, &f->ip);
            KVal v = pop(vm);
            if (!kv_truthy(v)) f->ip = target;
            break;
        }
        case 0x42: /* JNZ */
        {
            uint32_t target = read_u32(vm, &f->ip);
            KVal v = pop(vm);
            if (kv_truthy(v)) f->ip = target;
            break;
        }

        /* ─── 返回 ─── */
        case 0x50: /* RET — 弹出返回值，存到 vm->return_value，不 push */
        {
            KVal v = pop(vm);
            vm->return_value = v;
            pop_frame(vm);
            return (int)v.ival;
        }
        case 0x51: /* RETVOID */
            vm->return_value = mk_int(0);
            pop_frame(vm);
            return 0;

        /* ─── POP ─── */
        case 0x60: /* POP */
            pop(vm);
            break;

        /* ─── DEFINE (运行时注册函数) ─── */
        case 0x70: /* DEFINE */
        {
            uint32_t name_off = read_u32(vm, &f->ip);
            uint16_t n_params = read_u16(vm, &f->ip);
            uint32_t body_start = read_u32(vm, &f->ip);
            uint32_t body_end = read_u32(vm, &f->ip);
            /* 读取参数名偏移量 */
            uint32_t param_offs[32];
            for (int i = 0; i < n_params && i < 32; i++) {
                param_offs[i] = read_u32(vm, &f->ip);
            }
            const char *fname = str_at(vm, name_off);
            /* 查看函数表是否已有同名函数 */
            uint32_t fi = UINT32_MAX;
            for (uint16_t i = 0; i < vm->n_funcs; i++) {
                if (strcmp(str_at(vm, vm->funcs[i].name_off), fname) == 0) {
                    fi = i; break;
                }
            }
            if (fi == UINT32_MAX) {
                /* 动态扩展函数表 */
                vm->funcs = (FuncEntry *)realloc(vm->funcs, (vm->n_funcs + 1) * sizeof(FuncEntry));
                fi = vm->n_funcs++;
            }
            vm->funcs[fi].name_off = name_off;
            vm->funcs[fi].n_params = n_params;
            vm->funcs[fi].insn_start = body_start;
            vm->funcs[fi].insn_end = body_end;
            /* 参数名偏移量 */
            vm->funcs[fi].param_name_offs = (uint32_t *)malloc(n_params * sizeof(uint32_t));
            for (int i = 0; i < n_params; i++) {
                vm->funcs[fi].param_name_offs[i] = param_offs[i];
            }
            /* 在当前帧注册函数变量 */
            int idx = declare_local(f, fname);
            f->locals[idx] = mk_func(fi);
            break;
        }

        default:
            fprintf(stderr, "unknown opcode: 0x%02x at ip=%u\n", op, f->ip - 1);
            exit(1);
        }
    }

    pop_frame(vm);
    return ret_code;
}

/* ── 加载 .kir3 文件 ───────────────────────────── */

static VM *vm_load_kir3(const char *path) {
    FILE *fp = fopen(path, "rb");
    if (!fp) { fprintf(stderr, "cannot open %s\n", path); exit(1); }

    /* 读取整个文件 */
    fseek(fp, 0, SEEK_END);
    long fsize = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    uint8_t *buf = (uint8_t *)malloc(fsize);
    if (!buf) { fprintf(stderr, "malloc failed\n"); exit(1); }
    fread(buf, 1, fsize, fp);
    fclose(fp);

    /* 解析 Header */
    if (fsize < 16 || memcmp(buf, "KIR3", 4) != 0) {
        fprintf(stderr, "invalid .kir3 file\n"); exit(1);
    }
    uint16_t version   = buf[4] | (buf[5] << 8);
    uint16_t n_funcs   = buf[6] | (buf[7] << 8);
    uint32_t n_insns   = buf[8] | (buf[9]<<8) | (buf[10]<<16) | (buf[11]<<24);
    uint32_t str_pool_sz = buf[12] | (buf[13]<<8) | (buf[14]<<16) | (buf[15]<<24);

    uint32_t hdr_sz = 16;

    /* 函数表大小 = 14B per entry + 4B per param */
    uint32_t func_tbl_sz = 0;
    for (uint16_t i = 0; i < n_funcs; i++) {
        /* 先读 n_params 来计算大小 — 需要逐条扫描 */
        uint32_t base = hdr_sz + func_tbl_sz;
        uint16_t np = buf[base+4] | (buf[base+5]<<8);
        func_tbl_sz += 14 + np * 4;
    }

    uint32_t insns_off = hdr_sz + func_tbl_sz;
    uint32_t str_pool_off = insns_off + n_insns;

    /* 分配 VM */
    VM *vm = (VM *)calloc(1, sizeof(VM));

    /* 函数表 */
    vm->n_funcs = n_funcs;
    vm->funcs = (FuncEntry *)calloc(n_funcs, sizeof(FuncEntry));
    uint32_t ft_base = hdr_sz;
    for (uint16_t i = 0; i < n_funcs; i++) {
        vm->funcs[i].name_off    = buf[ft_base] | (buf[ft_base+1]<<8) | (buf[ft_base+2]<<16) | (buf[ft_base+3]<<24);
        vm->funcs[i].n_params    = buf[ft_base+4] | (buf[ft_base+5]<<8);
        vm->funcs[i].insn_start  = buf[ft_base+6] | (buf[ft_base+7]<<8) | (buf[ft_base+8]<<16) | (buf[ft_base+9]<<24);
        vm->funcs[i].insn_end    = buf[ft_base+10] | (buf[ft_base+11]<<8) | (buf[ft_base+12]<<16) | (buf[ft_base+13]<<24);
        ft_base += 14;
        /* 参数名偏移量 */
        if (vm->funcs[i].n_params > 0) {
            vm->funcs[i].param_name_offs = (uint32_t *)malloc(vm->funcs[i].n_params * sizeof(uint32_t));
            for (uint16_t p = 0; p < vm->funcs[i].n_params; p++) {
                vm->funcs[i].param_name_offs[p] = buf[ft_base] | (buf[ft_base+1]<<8) | (buf[ft_base+2]<<16) | (buf[ft_base+3]<<24);
                ft_base += 4;
            }
        } else {
            vm->funcs[i].param_name_offs = NULL;
        }
    }

    /* 指令缓冲区 */
    vm->n_insns = n_insns;
    vm->insns = (uint8_t *)malloc(n_insns);
    memcpy(vm->insns, buf + insns_off, n_insns);

    /* 字符串池 */
    vm->str_pool_sz = str_pool_sz;
    vm->str_pool = (char *)malloc(str_pool_sz + 1);
    memcpy(vm->str_pool, buf + str_pool_off, str_pool_sz);
    vm->str_pool[str_pool_sz] = '\0';  /* 确保末尾有 \0 */

    free(buf);

    /* 初始化顶层帧 */
    vm->frame = (CallFrame *)calloc(1, sizeof(CallFrame));
    vm->frame->ip = 0;  /* 顶层指令从 0 开始 */

    return vm;
}

/* ── 执行入口 ──────────────────────────────────── */

static int vm_exec(VM *vm) {
    /* 先执行顶层指令（非函数内的指令，即全局作用域） */
    /* 找到 "main" 函数并调用它 */
    for (uint16_t i = 0; i < vm->n_funcs; i++) {
        if (strcmp(str_at(vm, vm->funcs[i].name_off), "main") == 0) {
            return vm_run_func(vm, i, NULL, 0);
        }
    }
    /* 没有 main 函数 — 执行顶层指令 */
    /* 顶层指令范围: 从第一条 define/声明之后开始 */
    /* 简化: 如果没有 main 函数，报错 */
    fprintf(stderr, "no 'main' function found\n");
    return 1;
}

static void vm_free(VM *vm) {
    if (vm->insns)    free(vm->insns);
    if (vm->str_pool) free(vm->str_pool);
    if (vm->funcs)    free(vm->funcs);
    /* 释放所有帧 */
    while (vm->frame) pop_frame(vm);
    free(vm);
}

/* ── main ───────────────────────────────────────── */

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: kval_vm <file.kir3>\n");
        return 1;
    }

    VM *vm = vm_load_kir3(argv[1]);
    int rc = vm_exec(vm);
    vm_free(vm);
    return rc;
}
