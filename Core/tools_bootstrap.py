"""在 Windows 上：未设置 KVAL_NASM / KVAL_GOLINK 且 PATH 与 Kval/Tools 均无对应 exe 时，将工具安装到 Kval/Tools。

NASM 从 nasm.us 自动下载。GoLink 官方站常拦截脚本下载；若自动下载失败，会在 Kval/Tools/golink/ 写入说明文件，请用户手动放入 GoLink.exe。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .tools_layout import kval_tools_golink_exe, kval_tools_nasm_exe, kval_tools_root

_NASM_VERSION = "2.16.03"
_NASM_ZIP = f"nasm-{_NASM_VERSION}-win64.zip"
NASM_DOWNLOAD_URL = (
    f"https://www.nasm.us/pub/nasm/releasebuilds/{_NASM_VERSION}/win64/{_NASM_ZIP}"
)

# 若站点返回 401，自动安装会失败，见 _write_golink_readme
GOLINK_PAGE_URL = "http://www.godevtool.com/"
GOLINK_ZIP_CANDIDATES = (
    "http://www.godevtool.com/Golink.zip",
    "https://www.godevtool.com/Golink.zip",
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ToolsBootstrapError(RuntimeError):
    pass


def warn_and_exit_native_aot_tool_failure(*, tool: str, detail: str | None = None) -> None:
    """
    在生成 .asm / 可执行文件之前：工具下载或准备失败时打印 WARNING 与官方网址，并以退出码 1 终止进程。
    tool: "nasm" | "golink" | "linker"
    """
    print(
        "WARNING: 本机 AOT 工具链准备失败，已终止（尚未生成汇编或可执行文件）。",
        file=sys.stderr,
    )
    if tool == "nasm":
        print(f"  NASM 官方 zip: {NASM_DOWNLOAD_URL}", file=sys.stderr)
        print("  索引: https://www.nasm.us/", file=sys.stderr)
    elif tool == "golink":
        print(f"  GoLink 官方页面: {GOLINK_PAGE_URL}", file=sys.stderr)
        for u in GOLINK_ZIP_CANDIDATES:
            print(f"  GoLink.zip 直链（可尝试用浏览器下载）: {u}", file=sys.stderr)
    elif tool == "linker":
        print("  需要 gcc/clang（PATH 或 KVAL_CC）或 GoLink.exe（PATH、KVAL_GOLINK 或 Kval/Tools/golink/）。", file=sys.stderr)
        print(f"  NASM 参考: {NASM_DOWNLOAD_URL}", file=sys.stderr)
        print(f"  GoLink 参考: {GOLINK_PAGE_URL}", file=sys.stderr)
    if detail:
        print(f"  详情: {detail}", file=sys.stderr)
    raise SystemExit(1)


def _strip(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _download_bytes(url: str, *, timeout: int = 120, referer: str | None = None) -> bytes:
    headers: dict[str, str] = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
        headers["Accept-Language"] = "en-US,en;q=0.9"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except URLError as e:
        raise ToolsBootstrapError(f"下载失败 {url!r}: {e}") from e


def _bootstrap_nasm_windows() -> None:
    dest = kval_tools_nasm_exe()
    if dest.is_file():
        return
    dl_dir = kval_tools_root() / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dl_dir / _NASM_ZIP
    if not zip_path.is_file():
        zip_path.write_bytes(_download_bytes(NASM_DOWNLOAD_URL))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(td)
        found: Path | None = None
        for p in Path(td).rglob("nasm.exe"):
            found = p
            break
        if found is None or not found.is_file():
            raise ToolsBootstrapError(
                f"NASM 压缩包中未找到 nasm.exe（{_NASM_ZIP}），请手动从 {NASM_DOWNLOAD_URL} 解压到 {dest.parent}"
            )
        shutil.copy2(found, dest)


def _write_golink_readme() -> Path:
    d = kval_tools_golink_exe().parent
    d.mkdir(parents=True, exist_ok=True)
    p = d / "README.txt"
    p.write_text(
        "Kval 本机 AOT 需要 GoLink 时，请将 GoLink.exe 放在本目录（与此文件同级）。\n\n"
        "官方页面：\n"
        f"  {GOLINK_PAGE_URL}\n"
        "在页面中下载 Golink.zip，解压后复制 GoLink.exe 到上述目录。\n"
        "（部分环境下脚本无法从官网自动下载，需手动放置。）\n",
        encoding="utf-8",
    )
    return p


def _bootstrap_golink_windows() -> None:
    dest = kval_tools_golink_exe()
    if dest.is_file():
        return
    dl_dir = kval_tools_root() / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dl_dir / "Golink.zip"
    data: bytes | None = None
    last_err: Exception | None = None
    if zip_path.is_file():
        data = zip_path.read_bytes()
    else:
        for url in GOLINK_ZIP_CANDIDATES:
            try:
                data = _download_bytes(url, referer=GOLINK_PAGE_URL)
                zip_path.write_bytes(data)
                break
            except (ToolsBootstrapError, OSError) as e:
                last_err = e
                continue
    if data is None:
        readme = _write_golink_readme()
        hint = f" 原因: {last_err}" if last_err else ""
        raise ToolsBootstrapError(
            "无法自动下载 GoLink（官网可能拒绝脚本访问）。"
            f"已写入说明文件: {readme}{hint}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp_zip = Path(td) / "Golink.zip"
        tmp_zip.write_bytes(data)
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(td)
        found: Path | None = None
        for name in ("GoLink.exe", "golink.exe"):
            for p in Path(td).rglob(name):
                if p.is_file():
                    found = p
                    break
            if found:
                break
        if found is None:
            readme = _write_golink_readme()
            raise ToolsBootstrapError(
                f"GoLink.zip 中未找到 GoLink.exe。请手动从 {GOLINK_PAGE_URL} 获取并放入 {dest.parent}。"
                f" 说明: {readme}"
            )
        shutil.copy2(found, dest)


def ensure_nasm_for_native_aot_windows() -> None:
    """无 KVAL_NASM、PATH 无 nasm、Tools 无 nasm.exe 时，下载 NASM 到 Kval/Tools/nasm/。"""
    if sys.platform != "win32":
        return
    if _strip("KVAL_NASM"):
        return
    if shutil.which("nasm") is not None:
        return
    if kval_tools_nasm_exe().is_file():
        return
    _bootstrap_nasm_windows()


def ensure_golink_for_native_aot_windows() -> None:
    """在已确认需要 GoLink 回退时调用：无 KVAL_GOLINK、PATH 无、Tools 无则尝试安装。"""
    if sys.platform != "win32":
        return
    if _strip("KVAL_GOLINK"):
        return
    if shutil.which("GoLink") or shutil.which("golink"):
        return
    if kval_tools_golink_exe().is_file():
        return
    _bootstrap_golink_windows()


def print_aot_tool_bootstrap_warning(detail: str) -> None:
    """工具自动下载/安装失败时：向 stderr 打印 WARNING 与官方下载地址，然后由 CLI 以非零码退出。"""
    print(
        "WARNING: 本机 AOT 工具（NASM 或 GoLink）自动下载/安装失败，已中止，尚未生成 .asm。",
        file=sys.stderr,
    )
    if detail.strip():
        print(f"详情: {detail}", file=sys.stderr)
    print("请使用浏览器从以下地址手动获取并放入 Kval/Tools 对应目录：", file=sys.stderr)
    print(f"  NASM（Windows x64）: {NASM_DOWNLOAD_URL}", file=sys.stderr)
    print(f"  GoLink（官方页面）: {GOLINK_PAGE_URL}", file=sys.stderr)
    print(f"  GoLink.zip（直链，可能被站点拦截）: {GOLINK_ZIP_CANDIDATES[0]}", file=sys.stderr)
