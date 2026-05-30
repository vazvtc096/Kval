# Kval Runtime

> **Document language:** English  
> **Note:** Command-line switches describe the **intended** Kval toolchain / runtime interface. Use `python -m Kval --help` for the exact flags your checkout supports.

## Entry point

The program entry point is **`main`**. Typical signatures:

- `int main()`
- `int main(int argc, string argv[])` — *variadic argv is not fully wired in the reference driver; treat as reserved.*

After the translation unit (module) runs top-level statements, the driver invokes `main()` if it exists and is callable, and uses its return value as the process exit code (masked to 0–255).

## Execution modes

| Mode | Meaning | Reference implementation |
| :--- | :--- | :--- |
| **AST** | Tree-walking interpreter (`ASTNode.evaluate`) | Default `--run-type AST`; uses stack IR inside functions only when `execution_backend == "asm"` (see RPN). |
| **RPN** | Run lowered stack IR (`InsnVM`) after `ASTNode.asm()` | `--run-type RPN` or a binary whose first byte is `MAGIC_RPN`. Pre-lowering is partial: bodies with control flow still use `evaluate()`. |
| **JIT** | **Interpret while executing** — no ahead-of-time lowering for user functions at call time | `--run-type JIT` forces the AST runner and sets **jit mode**: `KvalFunction` never uses `InsnVM`, only `evaluate()`, even if stack IR exists. Same traversal idea as classic “interpreter + run loop”. |
| **AOT** | **Native executable** | **Default (stub):** `compile --compile-type AOT -o app.exe` — small C launcher + **`app.kbin`**, needs **Python** at run time. **`--aot-native`:** **resolve/install** NASM and a linker (**gcc** or **GoLink**) **before** static evaluation of the program; then emit **`app.asm`**, assemble with **NASM**, and link into a **standalone** PE/ELF/Mach-O (no C intermediate). Restricted to the **statically evaluable** subset. **`-o` must be the executable path**, not `.kbin`. |

**Platform (AOT):** **Windows:** prefer **MinGW-w64 `gcc`** to link the stub; optional **NASM** (`nasm -f win64`) if you add your own `.asm` and link objects with `gcc`. **Unix:** `gcc` or `clang` builds the POSIX stub.

**Magic byte (first octet of emitted binaries):**

| Value (hex) | Constant (in `Kval.Core.constants`) | Payload |
| :---: | :--- | :--- |
| `0xA5` | `MAGIC_AST` | `pickle` of a `Module` |
| `0x5A` | `MAGIC_RPN` | same loader branch; RPN is selected at run time by magic and/or `--run-type` |

The **`.kbin`** sibling uses the **AST** magic byte; the **executable** is a native binary produced by the host C compiler.

Plain UTF-8 `.kval` sources have **no** leading magic byte.

### AOT environment variables

| Variable | Phase | Meaning |
| :--- | :--- | :--- |
| `KVAL_CC` | Stub + native gcc | C compiler for stub AOT, or **gcc** for native AOT linking. Probes `PATH` and common MinGW locations on Windows. |
| `KVAL_CFLAGS` | Build stub | Extra compile flags (whitespace-separated), appended after the default `-O2 -s`. |
| `KVAL_LDFLAGS` | Link | Extra flags appended at the end of the compile line. |
| `KVAL_PYTHON` | **Run** stub | The emitted executable calls `getenv("KVAL_PYTHON")`; if unset or empty, Windows uses `python`, Unix tries `python3` then `python`. |
| `KVAL_NASM` | Native AOT | Explicit **NASM** path. If unset and neither `PATH` nor `Kval/Tools/nasm/nasm.exe` has it, **Windows** downloads NASM from **nasm.us** into `Kval/Tools/nasm/`. |
| `KVAL_GOLINK` | Native AOT (Windows) | Explicit **GoLink** path. When **gcc** is missing and GoLink is needed, the driver tries to install into `Kval/Tools/golink/`; if the vendor site blocks scripted downloads, see `Tools/golink/README.txt` and copy **GoLink.exe** manually. |

## Unified CLI: `python -m Kval`

```text
python -m Kval run [options] <path>
python -m Kval compile <input> [-o OUT] [--dump-asm] [--compile-type AST|RPN|AOT] [--aot-native]
python -m Kval asm <input>
python -m Kval <path>              # legacy: same as `run <path>` if <path> is an existing file
```

| Subcommand | Role |
| :--- | :--- |
| `run` | Load source or binary and execute (`Runner`) |
| `compile` | With `AOT`, `-o` is the executable path; output includes `.kbin` + native stub |
| `asm` | Same as `compile --dump-asm` |

Exit status: `main()`’s integer return, masked with `& 255`, or `0` if there is no `main`.

## Implementation notes (this repository)

- **Preprocessor** runs before lexing; see `Grammar` docs for `#include` paths.
- **Control-flow** in a function forces `asm_insns=None`; **RPN** still uses `InsnVM` only for functions that fully lowered. **JIT** disables `InsnVM` for all functions.
- **Classes**, **templates**, and **operators** are partial; see `Kval/examples/`.

## See also

- [Grammar (English)](Grammar(en).md)  
- [Grammar (Chinese)](Grammar(zh-cn).md)  
