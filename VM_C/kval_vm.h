/*
 * kval_vm.h — Kval C VM 公开 API 头文件
 *
 * 遵循 Windows ABI：
 *   - 所有导出函数使用 __cdecl 调用约定 (x64 下与 __fastcall 等效)
 *   - extern "C" 保证 C++ 互操作时不发生 name mangling
 *   - KVAL_API 宏自动切换 dllexport / dllimport
 *
 * 构建模式：
 *   -DKVAL_BUILD_DLL  → 编译为 DLL, 函数标记为 __declspec(dllexport)
 *   -DKVAL_USE_DLL    → 链接 DLL 的消费者, 函数标记为 __declspec(dllimport)
 *   (都不定义)         → 静态链接, 无 dllexport/dllimport
 *
 * 使用示例 (C):
 *   #include "kval_vm.h"
 *   int rc = kval_vm_run_file("hello.kir3");
 *
 * 使用示例 (C++):
 *   #include "kval_vm.h"
 *   KvalVM *vm = kval_vm_load_file("hello.kir3");
 *   if (vm) { kval_vm_exec(vm); kval_vm_free(vm); }
 *
 * 使用示例 (Python ctypes):
 *   dll = ctypes.CDLL("kval_vm.dll")
 *   dll.kval_vm_run_file(b"hello.kir3")
 */

#ifndef KVAL_VM_H
#define KVAL_VM_H

#ifdef __cplusplus
extern "C" {
#endif

/* ── ABI 导出宏 ─────────────────────────────────── */

#if defined(_WIN32) || defined(__CYGWIN__)
  #if defined(KVAL_BUILD_DLL)
    #define KVAL_API __declspec(dllexport)
  #elif defined(KVAL_USE_DLL)
    #define KVAL_API __declspec(dllimport)
  #else
    #define KVAL_API
  #endif
#else
  #define KVAL_API __attribute__((visibility("default")))
#endif

/* ── 版本信息 ───────────────────────────────────── */

#define KVAL_VM_VERSION_MAJOR 1
#define KVAL_VM_VERSION_MINOR 0
#define KVAL_VM_VERSION_STRING "1.0.0"

/* ── 不透明句柄 ─────────────────────────────────── */

typedef struct KvalVM KvalVM;

/* ── 错误码 ─────────────────────────────────────── */

typedef enum {
    KVAL_OK            =  0,   /* 成功 */
    KVAL_ERR_FILE      = -1,   /* 文件打开失败 */
    KVAL_ERR_FORMAT    = -2,   /* .kir3 格式无效 */
    KVAL_ERR_NO_MAIN   = -3,   /* 找不到 main 函数 */
    KVAL_ERR_RUNTIME   = -4,   /* 运行时错误 (除零、未定义变量等) */
    KVAL_ERR_NOMEM     = -5,   /* 内存分配失败 */
    KVAL_ERR_OVERFLOW  = -6,   /* 栈溢出 */
    KVAL_ERR_UNKNOWN   = -99,  /* 未知错误 */
} KvalResult;

/* ── 公开 API ───────────────────────────────────── */

/*
 * 从文件加载 .kir3 字节码，返回 VM 句柄。
 * 失败时返回 NULL，调用 kval_vm_last_error() 获取错误信息。
 *
 * 参数:
 *   path — .kir3 文件路径 (UTF-8 编码)
 * 返回:
 *   KvalVM* — 成功时非 NULL, 用完后需 kval_vm_free()
 */
KVAL_API KvalVM *kval_vm_load_file(const char *path);

/*
 * 从内存缓冲区加载 .kir3 字节码，返回 VM 句柄。
 * 用于嵌入场景：Python / C++ 宿主程序可直接传入字节流。
 *
 * 参数:
 *   data — 指向 .kir3 二进制数据的指针
 *   size — 数据长度 (字节)
 * 返回:
 *   KvalVM* — 成功时非 NULL
 */
KVAL_API KvalVM *kval_vm_load_buffer(const void *data, size_t size);

/*
 * 执行已加载的 Kval 程序。
 * 查找 main 函数并调用，返回 main 的退出码。
 *
 * 参数:
 *   vm — kval_vm_load_file / kval_vm_load_buffer 返回的句柄
 * 返回:
 *   >=0 — main 函数的返回值
 *   <0  — KvalResult 错误码
 */
KVAL_API int kval_vm_exec(KvalVM *vm);

/*
 * 便捷函数：加载文件 → 执行 → 释放。
 * 等价于 load_file + exec + free。
 *
 * 参数:
 *   path — .kir3 文件路径
 * 返回:
 *   >=0 — main 函数的返回值
 *   <0  — KvalResult 错误码
 */
KVAL_API int kval_vm_run_file(const char *path);

/*
 * 释放 VM 及所有关联资源。
 * 释放后 vm 指针不可再使用。
 *
 * 参数:
 *   vm — 要释放的 VM 句柄, 传 NULL 是安全的 (no-op)
 */
KVAL_API void kval_vm_free(KvalVM *vm);

/*
 * 获取最近一次操作的错误信息。
 * 返回的字符串在 VM 句柄存活期间有效，不需要调用者释放。
 *
 * 参数:
 *   vm — VM 句柄 (可以为 NULL, 此时返回全局错误信息)
 * 返回:
 *   const char* — 错误描述字符串 (UTF-8), 无错误时返回 NULL
 */
KVAL_API const char *kval_vm_last_error(KvalVM *vm);

/*
 * 获取版本字符串。
 *
 * 返回:
 *   const char* — 静态字符串, 不需要释放, 例如 "Kval C VM 1.0.0"
 */
KVAL_API const char *kval_vm_version(void);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* KVAL_VM_H */
