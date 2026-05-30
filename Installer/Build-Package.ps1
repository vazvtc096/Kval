param(
  [ValidateSet("auto", "nuitka", "pyinstaller", "none")]
  [string]$Mode = "auto",
  [ValidateSet("onedir", "onefile")]
  [string]$Bundle = "onedir",
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rootParent = Split-Path -Parent $root
$payloadBin = Join-Path $root "Installer\payload\bin"
$buildRoot = Join-Path $root "Installer\payload\.build"
$entryDir = Join-Path $root "Installer\payload-src"

New-Item -ItemType Directory -Force -Path $payloadBin | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null

function Invoke-Cmd {
  param([string]$Cmd, [string]$WorkDir)
  Push-Location $WorkDir
  try {
    $wrapped = "set PYTHONPATH=$rootParent;%PYTHONPATH% && $Cmd"
    Write-Host ">> $wrapped"
    & cmd /c $wrapped
    return $LASTEXITCODE
  }
  finally {
    Pop-Location
  }
}

function Clear-PayloadBin {
  if (Test-Path $payloadBin) {
    Get-ChildItem -Path $payloadBin -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Copy-TreeContent {
  param(
    [string]$FromDir,
    [string]$ToDir
  )
  New-Item -ItemType Directory -Force -Path $ToDir | Out-Null
  Copy-Item -Path (Join-Path $FromDir "*") -Destination $ToDir -Recurse -Force
}

function Write-AliasExecutables {
  $mainExe = Join-Path $payloadBin "kval.exe"
  if (!(Test-Path $mainExe)) {
    throw "kval.exe not found in payload: $payloadBin"
  }
  Copy-Item -Force -Path $mainExe -Destination (Join-Path $payloadBin "kvale.exe")
  Copy-Item -Force -Path $mainExe -Destination (Join-Path $payloadBin "kvalc.exe")
}

function Build-With-Nuitka {
  Write-Host "[Kval] Building payload with Nuitka..."
  $entry = Join-Path $entryDir "kval_entry.py"
  $out = Join-Path $buildRoot "nuitka"
  New-Item -ItemType Directory -Force -Path $out | Out-Null

  if ($Bundle -eq "onefile") {
    $cmd = "$PythonExe -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-module=Kval.cli --include-module=hashlib --include-module=_hashlib --output-dir=""$payloadBin"" --output-filename=""kval.exe"" ""$entry"""
    $rc = Invoke-Cmd -Cmd $cmd -WorkDir $root
    if ($rc -ne 0) { return $false }
    Write-AliasExecutables
    return $true
  }

  $cmd = "$PythonExe -m nuitka --standalone --assume-yes-for-downloads --follow-imports --include-module=Kval.cli --include-module=hashlib --include-module=_hashlib --output-dir=""$out"" --output-filename=""kval.exe"" ""$entry"""
  $rc = Invoke-Cmd -Cmd $cmd -WorkDir $root
  if ($rc -ne 0) { return $false }

  $exe = Get-ChildItem -Path $out -Recurse -Filter "kval.exe" | Select-Object -First 1
  if (-not $exe) { return $false }

  Clear-PayloadBin
  Copy-TreeContent -FromDir $exe.DirectoryName -ToDir $payloadBin
  Write-AliasExecutables
  return $true
}

function Build-With-PyInstaller {
  Write-Host "[Kval] Building payload with PyInstaller..."
  $check = Invoke-Cmd -Cmd "$PythonExe -m PyInstaller --version" -WorkDir $root
  if ($check -ne 0) {
    Write-Host "[Kval] PyInstaller not found, installing..."
    $install = Invoke-Cmd -Cmd "$PythonExe -m pip install pyinstaller" -WorkDir $root
    if ($install -ne 0) { return $false }
  }

  $work = Join-Path $buildRoot "pyinstaller"
  New-Item -ItemType Directory -Force -Path $work | Out-Null

  $entry = Join-Path $entryDir "kval_entry.py"
  $distBase = Join-Path $buildRoot "pyinstaller-dist"
  New-Item -ItemType Directory -Force -Path $distBase | Out-Null

  $bundleArg = if ($Bundle -eq "onefile") { "--onefile" } else { "--onedir" }
  $cmd = "$PythonExe -m PyInstaller --noconfirm $bundleArg --name ""kval"" --hidden-import=Kval --hidden-import=Kval.cli --hidden-import=hashlib --hidden-import=_hashlib --collect-submodules=Kval --distpath ""$distBase"" --workpath ""$work"" --specpath ""$work"" ""$entry"""
  $rc = Invoke-Cmd -Cmd $cmd -WorkDir $root
  if ($rc -ne 0) { return $false }

  Clear-PayloadBin
  if ($Bundle -eq "onefile") {
    $kvalExe = Join-Path $distBase "kval.exe"
    if (!(Test-Path $kvalExe)) { return $false }
    Copy-Item -Force -Path $kvalExe -Destination (Join-Path $payloadBin "kval.exe")
  } else {
    $distDir = Join-Path $distBase "kval"
    if (!(Test-Path $distDir)) { return $false }
    Copy-TreeContent -FromDir $distDir -ToDir $payloadBin
  }
  Write-AliasExecutables
  return $true
}

if ($Mode -eq "none") {
  Write-Host "[Kval] Packaging skipped (mode=none). Installer will use script wrappers."
  exit 0
}

Clear-PayloadBin
$ok = $false
$used = ""

switch ($Mode) {
  "nuitka" {
    $ok = Build-With-Nuitka
    $used = "nuitka"
  }
  "pyinstaller" {
    $ok = Build-With-PyInstaller
    $used = "pyinstaller"
  }
  default {
    $ok = Build-With-Nuitka
    if ($ok) {
      $used = "nuitka"
    } else {
      Write-Host "[Kval] Nuitka build failed, fallback to PyInstaller..."
      Clear-PayloadBin
      $ok = Build-With-PyInstaller
      if ($ok) { $used = "pyinstaller" }
    }
  }
}

if (-not $ok) {
  throw "Payload packaging failed for mode=$Mode. You can run with -Mode none to keep script-only installer."
}

Write-Host "[Kval] Payload build succeeded with: $used"
Write-Host "[Kval] Output: $payloadBin"

