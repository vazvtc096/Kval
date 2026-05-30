"""由扩展 LSP 子进程调用：对单文件运行 Kval 解析器并输出诊断。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    workspace = os.environ.get("PYTHONPATH", "").strip()
    if workspace:
        sys.path.insert(0, workspace)

    if len(sys.argv) >= 3 and sys.argv[1] == "--stdin":
        try:
            from Kval.Core.Parser.Parser import ParseError, Parser  # noqa: PLC0415
        except ImportError as e:
            print(f"IMPORT:{e}", flush=True)
            sys.exit(5)
        source = sys.stdin.read()
        virt = sys.argv[2]
        try:
            Parser.parse_source(source, virt)
        except ParseError as e:
            print(str(e), flush=True)
            sys.exit(1)
        return

    if len(sys.argv) < 2:
        print("NO_PATH", flush=True)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.is_file():
        print("MISSING", flush=True)
        sys.exit(3)

    try:
        from Kval.Core.Parser.Parser import ParseError, Parser  # noqa: PLC0415
    except ImportError as e:
        print(f"IMPORT:{e}", flush=True)
        sys.exit(5)

    try:
        Parser.parse_source(path.read_text(encoding="utf-8"), str(path))
    except ParseError as e:
        print(str(e), flush=True)
        sys.exit(1)
    except OSError as e:
        print(f"IO:{e}", flush=True)
        sys.exit(4)


if __name__ == "__main__":
    main()
