"""AOT 编译阶段读取的环境变量（由当前 Python 进程读取）。

stub AOT：KVAL_CC、KVAL_CFLAGS、KVAL_LDFLAGS、运行期 KVAL_PYTHON（写入 stub 源码）。

本机 AOT（--aot-native）：NASM .asm → nasm → 链接。
  Windows：无 KVAL_NASM 且 PATH 与 Kval/Tools 均无 nasm 时，自动下载 NASM 到 Kval/Tools/nasm/。
  另查 PATH、Kval/Tools、常见安装目录。链接优先 gcc；若无 gcc 且无 KVAL_GOLINK，则尝试将 GoLink 装入 Kval/Tools/golink/
  （官网常拦截自动下载，失败时会写入 Tools/golink/README.txt 请手动放置 GoLink.exe）。
KVAL_CFLAGS / KVAL_LDFLAGS 仅作用于 gcc/clang 链接（GoLink 不用）。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _strip(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _win_tool_search_dirs() -> list[Path]:
    """Windows 下 NASM / GoLink 常见安装位置（不含 PATH，供自动搜索）。"""
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    for envk in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        root = os.environ.get(envk)
        if not root:
            continue
        b = Path(root)
        add(b / "NASM")
        add(b / "GoLink")
        add(b / "bin")
        add(b / "bin" / "NASM")
        add(b / "bin" / "GoLink")
    home = Path.home()
    add(home / "bin")
    add(home / "bin" / "NASM")
    add(home / "AppData" / "Local" / "bin" / "NASM")
    add(home / "AppData" / "Local" / "bin")
    for fixed in (
        Path(r"C:\NASM"),
        Path(r"C:\GoLink"),
        Path(r"C:\tools\NASM"),
        Path(r"C:\tools\GoLink"),
        Path(r"C:\Program Files\NASM"),
    ):
        add(fixed)
    return dirs


def _find_exe_in_dirs(dirs: list[Path], names: tuple[str, ...]) -> str | None:
    for d in dirs:
        for name in names:
            p = d / name
            if p.is_file():
                return str(p)
    return None


def _kval_tools_nasm_str() -> str | None:
    if sys.platform != "win32":
        return None
    from .tools_layout import kval_tools_nasm_exe

    p = kval_tools_nasm_exe()
    return str(p) if p.is_file() else None


def _kval_tools_golink_str() -> str | None:
    if sys.platform != "win32":
        return None
    from .tools_layout import kval_tools_golink_exe

    p = kval_tools_golink_exe()
    return str(p) if p.is_file() else None


def resolve_nasm() -> str | None:
    """KVAL_NASM → PATH → Kval/Tools →（仅 Windows）常见目录 → …"""
    e = _strip("KVAL_NASM")
    if e:
        if os.path.isfile(e):
            return e
        w = shutil.which(e)
        if w:
            return w
        return e
    w = shutil.which("nasm")
    if w:
        return w
    kt = _kval_tools_nasm_str()
    if kt:
        return kt
    if sys.platform == "win32":
        hit = _find_exe_in_dirs(_win_tool_search_dirs(), ("nasm.exe", "NASM.exe"))
        if hit:
            return hit
    else:
        for cand in (
            Path("/usr/local/bin/nasm"),
            Path("/opt/homebrew/bin/nasm"),
        ):
            if cand.is_file():
                return str(cand)
    return None


def resolve_golink() -> str | None:
    """Windows PE 链接器 GoLink：KVAL_GOLINK → PATH → 常见目录。"""
    if sys.platform != "win32":
        return None
    e = _strip("KVAL_GOLINK")
    if e:
        if os.path.isfile(e):
            return e
        w = shutil.which(e)
        if w:
            return w
        return e
    w = shutil.which("GoLink") or shutil.which("golink")
    if w:
        return w
    kg = _kval_tools_golink_str()
    if kg:
        return kg
    return _find_exe_in_dirs(_win_tool_search_dirs(), ("GoLink.exe", "golink.exe"))


def _win_cc_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    for envk in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        root = os.environ.get(envk)
        if not root:
            continue
        b = Path(root)
        add(b / "mingw64" / "bin")
        add(b / "mingw32" / "bin")
        add(b / "MinGW" / "bin")
        add(b / "bin")
    home = Path.home()
    add(home / "mingw64" / "bin")
    add(home / "bin")
    for fixed in (Path(r"C:\mingw64\bin"), Path(r"C:\msys64\mingw64\bin"), Path(r"C:\TDM-GCC-64\bin")):
        add(fixed)
    return dirs


def resolve_cc() -> str | None:
    """KVAL_CC → PATH →（Windows）常见 MinGW 目录中的 gcc。"""
    e = _strip("KVAL_CC")
    if e:
        if os.path.isfile(e):
            return e
        w = shutil.which(e)
        return w or e
    for name in ("gcc", "x86_64-w64-mingw32-gcc", "cc", "clang"):
        w = shutil.which(name)
        if w:
            return w
    if sys.platform == "win32":
        hit = _find_exe_in_dirs(
            _win_cc_search_dirs(),
            ("gcc.exe", "x86_64-w64-mingw32-gcc.exe", "clang.exe"),
        )
        if hit:
            return hit
    return None


def extra_cflags() -> list[str]:
    """KVAL_CFLAGS：空格分隔，追加在默认 -O2 -s 之后。"""
    s = _strip("KVAL_CFLAGS")
    return s.split() if s else []


def extra_ldflags() -> list[str]:
    """KVAL_LDFLAGS：空格分隔，追加在编译命令末尾（与 gcc 常见用法一致）。"""
    s = _strip("KVAL_LDFLAGS")
    return s.split() if s else []
