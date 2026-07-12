/*
 * kval_aot.h — Kval AOT-Native DLL 消费者头文件
 *
 * 当 Kval 程序被编译为 DLL (--aot-native --aot-output-type dll) 时，
 * DLL 导出以下符号供宿主程序调用：
 *
 *   DllMain    — Windows DLL 入口点 (自动调用, 返回 TRUE)
 *   kval_main  — int kval_main(void); 执行 Kval 程序的 main() 并返回退出码
 *
 * 所有导出函数遵循 Windows x64 ABI:
 *   - __cdecl 调用约定 (x64 下与 __fastcall 等效)
 *   - extern "C" 保证无 name mangling
 *   - KVAL_AOT_API 宏自动切换 dllexport/dllimport
 *
 * 使用示例 (C):
 *   #include "kval_aot.h"
 *   int rc = kval_main();   // 执行 Kval 程序
 *
 * 使用示例 (Python ctypes):
 *   dll = ctypes.CDLL("myprogram.dll")
 *   rc = dll.kval_main()
 *
 * 使用示例 (C++ LoadLibrary):
 *   typedef int (*kval_main_t)(void);
 *   HMODULE h = LoadLibraryA("myprogram.dll");
 *   auto fn = (kval_main_t)GetProcAddress(h, "kval_main");
 *   int rc = fn();
 */

#ifndef KVAL_AOT_H
#define KVAL_AOT_H

#ifdef __cplusplus
extern "C" {
#endif

/* ── ABI 导出宏 ─────────────────────────────────── */

#if defined(_WIN32) || defined(__CYGWIN__)
  #if defined(KVAL_AOT_BUILD_DLL)
    #define KVAL_AOT_API __declspec(dllexport)
  #elif defined(KVAL_AOT_USE_DLL)
    #define KVAL_AOT_API __declspec(dllimport)
  #else
    #define KVAL_AOT_API
  #endif
#else
  #define KVAL_AOT_API __attribute__((visibility("default")))
#endif

/* ── 导出函数 ───────────────────────────────────── */

/*
 * 执行 Kval 程序的 main() 函数，返回其退出码。
 *
 * 返回:
 *   >=0 — main 函数的返回值
 *   <0  — 运行时错误 (罕见, 通常会直接 abort)
 *
 * 注意:
 *   - 此函数不可重入 (Kval 程序使用全局状态)
 *   - 首次调用时 DLL 已通过 DllMain 完成初始化
 *   - print 等输出直接写到 stdout
 */
KVAL_AOT_API int kval_main(void);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* KVAL_AOT_H */
