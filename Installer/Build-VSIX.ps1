param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Registry = "https://registry.npmmirror.com"
)

$ErrorActionPreference = "Stop"

$extDir = Join-Path $Root "Supports\Kval-language-support"
if (!(Test-Path $extDir)) {
  throw "Extension dir not found: $extDir"
}

Push-Location $extDir
try {
  Write-Host "[Kval] Installing extension deps..."
  npm install --registry=$Registry
  if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }

  npm install underscore --no-save --registry=$Registry
  if ($LASTEXITCODE -ne 0) { throw "npm install underscore failed with exit code $LASTEXITCODE" }

  Write-Host "[Kval] Building VSIX..."
  npm run vsix
  if ($LASTEXITCODE -ne 0) { throw "npm run vsix failed with exit code $LASTEXITCODE" }

  $vsix = Get-ChildItem -Path (Join-Path $Root "Supports") -Filter "kval-language-support-*.vsix" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  if (-not $vsix) {
    throw "VSIX not found under: $(Join-Path $Root "Supports")"
  }

  $outDir = Join-Path $Root "Installer\assets"
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $outPath = Join-Path $outDir "kval-language-support.vsix"

  Copy-Item -Force -Path $vsix.FullName -Destination $outPath
  Write-Host "[Kval] VSIX copied to: $outPath"
}
finally {
  Pop-Location
}

