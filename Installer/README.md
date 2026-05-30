# Kval Inno Setup Installer

This directory contains Windows installer assets for Kval.

## Included options in installer

- Add to PATH
- Install for all users (Inno privilege dialog)
- Install VS Code extension (`.vsix`) for VS Code-based IDEs
- Add context menu for `.kval` files
- Create desktop shortcut

## Prerequisites

- Inno Setup 6 (`ISCC.exe`)
- Build machine has Python (end users do not need Python when using packaged payload exe)
- (Optional) VS Code / VSCodium / VS Code Insiders for extension auto-install

## Build VSIX asset

Run from repo root:

```powershell
powershell -ExecutionPolicy Bypass -File ".\Installer\Build-VSIX.ps1"
```

This generates and copies:

- `Installer/assets/kval-language-support.vsix`

> Note: if VSIX build fails in your local Node/npm environment, fix extension build first in
> `Supports/Kval-language-support` (`npm install`, `npm run compile`, `npm run vsix`).

## Build installer EXE

Use Inno Setup Compiler:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ".\Installer\Kval.iss"
```

Output:

- `Installer\KvalSetup.exe`

## Install/Uninstall verification logs

For local install-test-uninstall loops, keep logs inside the repo:

- `Installer\logs\kval-install-*.log`
- `Installer\logs\kval-uninstall-*.log`

Example (PowerShell):

```powershell
$logDir = ".\Installer\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Process -FilePath ".\Installer\KvalSetup.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-","/CURRENTUSER","/DIR=`"C:\Kval`"","/TASKS=`"addpath,vscodeext,ctxmenu,desktopicon`"","/LOG=$logDir\kval-install-local.log" -Wait
Start-Process -FilePath "C:\Kval\unins000.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/LOG=$logDir\kval-uninstall-local.log" -Wait
```

## Build CLI payload (preferred for end users)

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File ".\Installer\Build-Package.ps1" -Mode auto -Bundle onedir
```

- `Mode auto`: try Nuitka first, fallback to PyInstaller
- `Bundle onedir`: shared runtime files in one folder, `kval.exe/kvale.exe/kvalc.exe` share the same DLL/runtime set
- `Bundle onefile`: produce single-file payloads (larger and duplicated runtime)
- Build script injects `Kval` package + `hashlib/_hashlib` into the executable bundle to avoid
  missing stdlib module errors after installation.

