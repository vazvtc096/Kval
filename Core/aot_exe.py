from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .aot_platform import aot_native_build_readme, platform_tag
from .compiler_env import extra_cflags, extra_ldflags, resolve_cc

_LAUNCHER_C_WIN = r"""#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void exe_to_kbin(char *p) {
  size_t n = strlen(p);
  if (n >= 4 && _stricmp(p + n - 4, ".exe") == 0) {
    strcpy(p + n - 4, ".kbin");
  } else {
    if (n + 5 < MAX_PATH)
      strcat(p, ".kbin");
  }
}

int main(void) {
  char self[MAX_PATH], kbin[MAX_PATH], cmd[32767];
  const char *py = getenv("KVAL_PYTHON");
  if (!py || !*py)
    py = "python";
  if (!GetModuleFileNameA(NULL, self, MAX_PATH))
    return 1;
  strncpy(kbin, self, MAX_PATH);
  kbin[MAX_PATH - 1] = 0;
  exe_to_kbin(kbin);
  if ((size_t)snprintf(cmd, sizeof cmd, "\"%s\" -m Kval run \"%s\"", py, kbin) >= sizeof cmd)
    return 1;
  return system(cmd);
}
"""

_LAUNCHER_C_POSIX = r"""#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
  char self[PATH_MAX];
  char kbin[PATH_MAX + 16];
  const char *py;
  if (argc < 1 || !argv[0])
    return 1;
  if (!realpath(argv[0], self))
    return 1;
  if (snprintf(kbin, sizeof kbin, "%s.kbin", self) >= (int)sizeof kbin)
    return 1;
  py = getenv("KVAL_PYTHON");
  if (py && *py) {
    execlp(py, py, "-m", "Kval", "run", kbin, (char *)NULL);
  }
  execlp("python3", "python3", "-m", "Kval", "run", kbin, (char *)NULL);
  execlp("python", "python", "-m", "Kval", "run", kbin, (char *)NULL);
  return 127;
}
"""


class AOTExecutableError(RuntimeError):
    pass


class AOTToolBootstrapFailed(AOTExecutableError):
    """本机 AOT：在写出 .asm 等产物之前，NASM/GoLink 自动下载或安装失败。"""


def normalize_aot_executable_output(out: Path) -> Path:
    out = Path(out)
    if out.suffix.lower() == ".kbin":
        raise AOTExecutableError(
            "AOT: -o 须为可执行文件路径（如 app.exe 或 ./myapp），同目录会生成同名 .kbin"
        )
    if sys.platform == "win32" and out.suffix.lower() != ".exe":
        return out.with_suffix(".exe")
    return out


def kbin_path_next_to_exe(exe: Path) -> Path:
    return exe.parent / f"{exe.stem}.kbin"


def _deps_readme() -> str:
    return (
        "This executable is a small native stub.\n"
        "It runs: $KVAL_PYTHON (if set) else python/python3 -m Kval run <sibling .kbin>\n"
        "Requires: Python 3 and the Kval package importable (e.g. pip install -e.).\n"
    )


def build_native_stub_exe(
    *,
    kbin_bytes: bytes,
    exe_out: Path,
    keep_launcher_c: bool = False,
) -> Path:
    exe_out = normalize_aot_executable_output(exe_out)
    exe_out.parent.mkdir(parents=True, exist_ok=True)
    kbin_path = kbin_path_next_to_exe(exe_out)
    kbin_path.write_bytes(kbin_bytes)

    cc = resolve_cc()
    if not cc:
        fail_note = exe_out.parent / f"{exe_out.stem}.aot-failed-{platform_tag()}.txt"
        fail_note.write_text(aot_native_build_readme(), encoding="utf-8")
        raise AOTExecutableError(
            "未找到 C 编译器：请设置环境变量 KVAL_CC，或安装 MinGW-w64 / clang 并将 gcc 加入 PATH。"
        )

    c_src = (
        _LAUNCHER_C_WIN if sys.platform == "win32" else _LAUNCHER_C_POSIX
    )
    c_file = exe_out.parent / f"{exe_out.stem}_aot_launcher.c"
    c_file.write_text(c_src, encoding="utf-8")

    cmd = [cc, "-O2", "-s", *extra_cflags(), "-o", str(exe_out), str(c_file), *extra_ldflags()]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(exe_out.parent))
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or "link failed"
        if not keep_launcher_c:
            c_file.unlink(missing_ok=True)
        fail_note = exe_out.parent / f"{exe_out.stem}.aot-failed-{platform_tag()}.txt"
        fail_note.write_text(aot_native_build_readme() + "\n\n--- gcc stderr ---\n" + err, encoding="utf-8")
        raise AOTExecutableError(f"AOT 链接失败 ({cc}): {err}")

    if not keep_launcher_c:
        c_file.unlink(missing_ok=True)

    (exe_out.parent / f"{exe_out.name}.deps.txt").write_text(_deps_readme(), encoding="utf-8")
    return exe_out
