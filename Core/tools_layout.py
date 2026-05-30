"""Kval 包内 Tools 目录布局（与本机 AOT 引导安装）。"""

from __future__ import annotations

from pathlib import Path


def kval_package_root() -> Path:
    """含 `Core/`、`cli.py` 的 `Kval` 包根目录。"""
    return Path(__file__).resolve().parent.parent


def kval_tools_root() -> Path:
    return kval_package_root() / "Tools"


def kval_tools_nasm_exe() -> Path:
    return kval_tools_root() / "nasm" / "nasm.exe"


def kval_tools_golink_exe() -> Path:
    return kval_tools_root() / "golink" / "GoLink.exe"
