<#
.SYNOPSIS
    Build an unsigned Locksmith-X.Y.Z.msi from the current source tree.

.DESCRIPTION
    Drives the Phase 3A (unsigned) Windows release pipeline:
      1. Write src/locksmith/build_info.py with version + channel
      2. PyInstaller -> dist/Locksmith/Locksmith.exe
      3. wix harvest -> build/windows/HarvestedComponents.wxs
      4. wix build   -> build/windows/Locksmith-X.Y.Z.msi

    Signing (Azure Trusted Signing) is intentionally out of scope for
    Phase 3A; it lands in Phase 3B as a separate signing wrapper invoked
    BEFORE the wix harvest (so the signed .exe is what gets cabbed into
    the MSI) and AFTER `wix build` (so the MSI itself is signed too).

.PARAMETER Version
    Override the version derived from pyproject.toml. Optional.

.EXAMPLE
    pwsh packaging/build-windows.ps1
    pwsh packaging/build-windows.ps1 -Version 0.0.9
#>
[CmdletBinding()]
param(
    [string]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot     = (Resolve-Path "$PSScriptRoot\..").Path
$packagingDir = Join-Path $repoRoot "packaging"
$wixDir       = Join-Path $packagingDir "wix"
$distDir      = Join-Path $repoRoot "dist\Locksmith"
$buildDir     = Join-Path $repoRoot "build\windows"
$iconSourceDir = Join-Path $repoRoot "assets\custom"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# --- 1. Resolve version -------------------------------------------------------

if (-not $Version) {
    $Version = & python -c "import tomllib; print(tomllib.load(open(r'$repoRoot\pyproject.toml', 'rb'))['project']['version'])"
    $Version = $Version.Trim()
}
if (-not $Version) {
    throw "[build] could not derive version"
}
$env:LOCKSMITH_VERSION = $Version
if (-not $env:LOCKSMITH_RELEASE_CHANNEL) {
    $env:LOCKSMITH_RELEASE_CHANNEL = "stable"
}
Write-Host "[build] LOCKSMITH_VERSION=$Version LOCKSMITH_RELEASE_CHANNEL=$env:LOCKSMITH_RELEASE_CHANNEL"

# --- 2. Bake build_info.py ----------------------------------------------------

$buildInfo = Join-Path $repoRoot "src\locksmith\build_info.py"
@"
"""Build-time constants -- REWRITTEN by packaging/build-windows.ps1 at build time."""
from __future__ import annotations

LOCKSMITH_VERSION: str = "$Version"
LOCKSMITH_RELEASE_CHANNEL: str = "$env:LOCKSMITH_RELEASE_CHANNEL"
"@ | Set-Content -Encoding utf8 -Path $buildInfo
Write-Host "[build] wrote $buildInfo"

# --- 3. PyInstaller -----------------------------------------------------------

Write-Host "[build] running PyInstaller"
Push-Location $repoRoot
try {
    & pyinstaller --noconfirm --clean (Join-Path $packagingDir "Locksmith.windows.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "[build] PyInstaller exited $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$exePath = Join-Path $distDir "Locksmith.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "[build] PyInstaller did not produce $exePath"
}
Write-Host "[build] PyInstaller ok exe=$exePath"

# --- 4. Harvest the dist tree (pure-Python harvester) ------------------------
# We don't use `wix harvest` because its CLI surface is unstable across the
# v4 minor releases. packaging/wix/harvest.py walks the dist tree and emits
# a wxs fragment with stable Component GUIDs and INSTALLFOLDER-rooted dirs.

Write-Host "[build] harvesting $distDir with packaging/wix/harvest.py"
$harvestedWxs = Join-Path $buildDir "HarvestedComponents.wxs"
& python (Join-Path $wixDir "harvest.py") `
    --source $distDir `
    --out $harvestedWxs `
    --directory-ref INSTALLFOLDER `
    --group-id HarvestedComponents `
    --exclusions (Join-Path $wixDir "heat-exclusions.txt")
if ($LASTEXITCODE -ne 0) {
    throw "[build] harvest.py exited $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $harvestedWxs)) {
    throw "[build] harvest.py did not produce $harvestedWxs"
}

# --- 5. wix build -> MSI ------------------------------------------------------

$msiName = "Locksmith-$Version.msi"
$msiPath = Join-Path $buildDir $msiName
Write-Host "[build] linking $msiPath"

Push-Location $wixDir
try {
    # -d NAME=VAL    compile-time variable; resolves $(var.NAME) in wxs sources
    # -bindpath DIR  file lookup path; first hit wins for relative SourceFile refs
    & wix build `
        "Locksmith.wxs" $harvestedWxs `
        -ext WixToolset.UI.wixext `
        -arch x64 `
        -d "Version=$Version" `
        -d "HarvestSource=$distDir" `
        -bindpath $wixDir `
        -bindpath $iconSourceDir `
        -out $msiPath
    if ($LASTEXITCODE -ne 0) {
        throw "[build] wix build exited $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $msiPath)) {
    throw "[build] wix build did not produce $msiPath"
}

Write-Host "[build] done"
Write-Host "[build] artifact=$msiPath version=$Version"
