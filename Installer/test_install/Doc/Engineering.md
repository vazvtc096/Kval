# Kval Engineering Guide

This document describes day-to-day development workflows, quality gates, release flow, and AOT tool dependencies.

## 1. Development Setup

### Python toolchain

- Python: `3.10+`
- Recommended tools: `pytest`, `ruff`, `black`, `pre-commit`

Install:

```bash
python -m pip install --upgrade pip
pip install pytest ruff black pre-commit
pre-commit install
```

### VS Code extension toolchain

- Node.js: `20+`
- Workspace: `Supports/Kval-language-support`

Install:

```bash
cd Supports/Kval-language-support
npm install
```

## 2. Testing Strategy

Test suites are split by responsibility:

- `tests/parser/`: parser and grammar-level behavior
- `tests/typecheck/`: static type check rules
- `tests/runtime/`: runtime behavior and `.kir` loading/execution

Commands:

```bash
pytest
python tests/grammar_doc_harness.py
```

## 3. Quality Gates

### Python

```bash
ruff check Core tests cli.py __main__.py
black --check Core tests cli.py __main__.py
pytest
```

### VS Code extension

```bash
cd Supports/Kval-language-support
npm install
npm run lint
npm run format:check
npm run compile
```

## 4. CI Overview

GitHub Actions workflow: `.github/workflows/ci.yml`

- Runs on `push` to `main/master` and all pull requests.
- Uses path filters to skip unrelated jobs.
- Python job runs lints + tests (matrix: Python 3.10/3.11).
- Extension job runs lint + prettier check + TypeScript compile.

## 5. Release Flow

### Language/runtime release (Python side)

1. Run local quality gates (Python + extension if changed).
2. Ensure CI is green for the release branch/PR.
3. Tag release in git (for example: `vX.Y.Z`).
4. Publish release notes with:
   - language/runtime changes
   - `.kir` format compatibility notes
   - AOT toolchain updates

### VS Code extension release

```bash
cd Supports/Kval-language-support
npm run compile
npm run vsix
```

Output VSIX is generated in `Supports/`.

## 6. AOT Dependency Matrix

Kval AOT supports both stub-mode and native-mode paths.

| Platform | Required tools | How to configure |
| --- | --- | --- |
| Windows | C compiler, NASM, GoLink | `KVAL_CC`, `KVAL_NASM`, `KVAL_GOLINK` |
| Linux/macOS | C compiler, linker toolchain | `KVAL_CC`, optional `KVAL_CFLAGS`, `KVAL_LDFLAGS` |

Shared environment variables:

- `KVAL_CC`: C compiler path/name
- `KVAL_CFLAGS`: extra compiler flags
- `KVAL_LDFLAGS`: extra linker flags
- `KVAL_PYTHON`: Python executable used by generated stub
- `KVAL_NASM`: NASM path override
- `KVAL_GOLINK`: GoLink path override

For native AOT, use:

```bash
python -m Kval compile input.kval --compile-type AOT --aot-native
```
