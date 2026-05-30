# Kval 运行时

> **文档语言：** 简体中文  
> **说明：** 命令行与模式说明以 `python -m Kval --help` 为准。

## 入口

程序入口为 **`main`**，典型签名为：

- `int main()`
- `int main(int argc, string argv[])` — *参考驱动对 argc/argv 接入不完整，视为预留。*

模块顶层执行完后，若存在可调用的 **`main`**，驱动会调用它，返回值经 `& 255` 作为进程退出码。

## 执行模式

| 模式 | 含义 | 参考实现中的行为 |
| :--- | :--- | :--- |
| **AST** | 遍历 AST 解释执行（`evaluate`） | 默认 `--run-type AST`；若运行期 `execution_backend` 为 `asm`（见 RPN），无控制流的函数体可走栈式 IR。 |
| **RPN** | 先将部分代码 lowering 为栈式 IR，再由 VM 执行 | `--run-type RPN` 或载荷首字节为 `MAGIC_RPN`。含控制流的函数体仍只能 `evaluate`。 |
| **JIT** | **一边解释一边执行**：调用用户函数时不依赖预先 lowering 好的栈机码 | `--run-type JIT` 走 AST 型 Runner 并打开 **jit 模式**：`KvalFunction` **一律不跑 `InsnVM`**，只走 `evaluate`，与「解释执行」语义一致。 |
| **AOT** | **本机可执行文件** | **默认（stub）**：`compile --compile-type AOT -o app.exe` — 小型 C 启动器 + 同目录 **`app.kbin`**（运行时要 Python）。**本机 AOT**：**`--aot-native`** — 先**检测/安装** NASM 与链接器（gcc 或 GoLink），再对源码做**静态求值**；通过后生成 **`app.asm`**，再 **`nasm` → 目标文件 → 链接**，**不经过 C 源码**。得到**不依赖 Python** 的 PE/ELF/Mach-O。仅支持**可静态求值**子集。`-o` 不得为 `.kbin`。 |

**平台：** 失败说明里的 `<platform>` 来自 `sys.platform`。**Windows 上优先用 MinGW-w64 的 `gcc` 链接**；若你自行写汇编，可用 **NASM**（`nasm -f win64`）出 `.obj` 再交给 `gcc`。

**魔数（二进制首字节）：**

| 十六进制 | 常量 | 载荷 |
| :---: | :--- | :--- |
| `0xA5` | `MAGIC_AST` | `pickle` 的 `Module` |
| `0x5A` | `MAGIC_RPN` | 与上同一加载分支；运行期由魔数/选项选 VM |

AOT 的 `.kbin` 使用 **AST 魔数**；可执行文件为 C 源码经 **gcc** 编译得到的小型 native stub。

纯文本 `.kval` 无首字节魔数。

### AOT 环境变量

| 变量 | 阶段 | 含义 |
| :--- | :--- | :--- |
| `KVAL_CC` | stub / 本机 gcc | 指定 C 编译器或本机 AOT 的 gcc 链接器。未设时查 `PATH`，Windows 下另搜常见 MinGW 目录。 |
| `KVAL_CFLAGS` | 编译 stub | 空格分隔的额外编译参数，追加在默认 `-O2 -s` 之后。 |
| `KVAL_LDFLAGS` | 链接 | 空格分隔的额外参数，放在命令末尾（与常见 `gcc … -o out src.c …` 用法一致）。 |
| `KVAL_PYTHON` | **运行** stub | 生成的可执行文件在启动时 `getenv("KVAL_PYTHON")`；若未设置或为空，Windows 使用 `python`，类 Unix 先 `python3` 再 `python`。 |
| `KVAL_NASM` | 本机 AOT | 显式指定 NASM。未设且 `PATH` 与 `Kval/Tools/nasm` 均无 `nasm.exe` 时，**Windows 下会自动从 nasm.us 下载**到 `Kval/Tools/nasm/`。 |
| `KVAL_GOLINK` | 本机 AOT（Windows） | 显式指定 GoLink。未设且需 GoLink 回退（无 gcc）时，会尝试自动安装到 `Kval/Tools/golink/`；若官网拒绝脚本下载，将生成 `Tools/golink/README.txt` 请手动放置 `GoLink.exe`。 |

## 统一入口：`python -m Kval`

```text
python -m Kval run [选项] <路径>
python -m Kval compile <输入> [-o OUT] [--dump-asm] [--compile-type AST|RPN|AOT] [--aot-native]
python -m Kval asm <输入>
python -m Kval <路径>              # 兼容：已存在文件则等同 run
```

| 子命令 | 作用 |
| :--- | :--- |
| `run` | 加载并执行 |
| `compile` | AOT 时 `-o` 为可执行文件路径；成功则生成 exe/ELF + 同名 `.kbin` |
| `asm` | 等同 `compile --dump-asm` |

退出码：同上。

## 本仓库说明

- **预处理器**见 [Grammar(zh-cn).md](Grammar(zh-cn).md)。
- **JIT** 与 **RPN** 的差异在于是否允许在函数入口使用已生成的 `InsnVM` 指令序列。
- 能力完成度以 `Kval/examples/` 为准。

## 另见

- [Grammar(en).md](Grammar(en).md)  
- [Grammar(zh-cn).md](Grammar(zh-cn).md)  
