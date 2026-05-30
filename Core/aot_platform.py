from __future__ import annotations

import sys


def platform_tag() -> str:
    p = sys.platform
    if p == "win32":
        return "win32"
    if p == "darwin":
        return "darwin"
    if p.startswith("linux"):
        return "linux"
    if p.startswith("freebsd"):
        return "freebsd"
    return p.replace("/", "_")


def default_exe_suffix() -> str:
    return ".exe" if sys.platform == "win32" else ""


def aot_native_build_readme() -> str:
    p = sys.platform
    head = (
        "Kval AOT (ahead-of-time)\n"
        "========================\n"
        "Stub AOT: gcc/clang builds a tiny C launcher that runs Python on a sibling .kbin.\n"
        "Native AOT (--aot-native): emits NASM .asm, assembles with nasm, links with gcc/clang\n"
        "(no C source) — standalone .exe/ELF/Mach-O for a restricted subset; no Python at run time.\n\n"
        f"Detected platform: {p!r} ({platform_tag()})\n\n"
    )
    if p == "win32":
        body = (
            "Windows\n"
            "-------\n"
            "Preferred toolchains (in this order):\n"
            "  1) MinGW-w64 — use gcc/g++ to compile C/C++ glue and link the final .exe.\n"
            "     Example:  gcc -o app.exe main.c other.obj\n"
            "  2) NASM — assemble .asm to COFF objects for x64, then link with MinGW:\n"
            "     Example:  nasm -f win64 stub.asm -o stub.obj\n"
            "               gcc -o app.exe main.c stub.obj\n"
            "MSVC (cl + link) is optional if you already depend on it; MinGW+NASM is the\n"
            "recommended default for portable, scriptable AOT-style build steps.\n"
            "Output: PE .exe\n"
            "The .kbin payload still needs a small native or hybrid loader that unpickles\n"
            "(or maps) the module and calls into your runtime.\n"
        )
    elif p == "darwin":
        body = (
            "macOS\n"
            "-----\n"
            "Typical toolchain: clang / Xcode (ld).\n"
            "Output: Mach-O executable (no extension or custom name).\n"
        )
    elif p.startswith("linux") or p.startswith("freebsd"):
        body = (
            "Linux / *BSD\n"
            "------------\n"
            "Typical toolchain: gcc or clang + GNU ld / lld.\n"
            "If you use hand-written assembly: NASM (e.g. nasm -f elf64 foo.asm -o foo.o)\n"
            "then link with gcc/clang.\n"
            "Output: ELF binary (often no extension).\n"
        )
    else:
        body = (
            "Other\n"
            "-----\n"
            "Use your platform's C/C++ compiler and linker to produce a native binary.\n"
        )
    return head + body
