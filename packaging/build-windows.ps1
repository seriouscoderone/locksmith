<#
.SYNOPSIS
    Build an unsigned Locksmith-X.Y.Z.msi from the current source tree.

.DESCRIPTION
    Drives the Phase 3A (unsigned) Windows release pipeline:
      1. Write src/locksmith/build_info.py with version + channel
      2. PyInstaller        -> dist/<AppName>/<AppName>.exe + _internal/
      3. packaging/wix/harvest.py (pure-Python harvester)
                            -> build/windows/HarvestedComponents.wxs
      4. wix build          -> build/windows/Locksmith-X.Y.Z.msi

    Signing (Azure Trusted Signing) is intentionally out of scope for
    Phase 3A; it lands in Phase 3B as a separate signing wrapper invoked
    BEFORE the harvest (so the signed .exe is what gets cabbed into
    the MSI) and AFTER `wix build` (so the MSI itself is signed too).

.PARAMETER Version
    Override the version derived from pyproject.toml. Optional.

.PARAMETER Stage
    Which stage to run. CI splits the run into two halves so signing
    can be spliced between them:
      - "pyinstaller": steps 1-3 only (produces dist/Locksmith/*.exe)
      - "msi":         steps 4-5 only (harvest + wix build of MSI)
      - "all" (default): everything end-to-end (dev usage)

.EXAMPLE
    pwsh packaging/build-windows.ps1
    pwsh packaging/build-windows.ps1 -Version 0.0.9
    pwsh packaging/build-windows.ps1 -Stage pyinstaller
    pwsh packaging/build-windows.ps1 -Stage msi
#>
[CmdletBinding()]
param(
    [string]$Version,
    [ValidateSet("all", "pyinstaller", "msi")]
    [string]$Stage = "all"
)

$ErrorActionPreference = "Stop"

$repoRoot     = (Resolve-Path "$PSScriptRoot\..").Path
$packagingDir = Join-Path $repoRoot "packaging"
$wixDir       = Join-Path $packagingDir "wix"
$buildDir     = Join-Path $repoRoot "build\windows"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# --- 0. Resolve brand identity (build-time white-label). Default brand = locksmith. ---

if (-not $env:LOCKSMITH_BRAND) { $env:LOCKSMITH_BRAND = "locksmith" }
Push-Location $packagingDir
$AppName        = (& python -m brandlib id display_name).Trim()
$ArtifactPrefix = (& python -m brandlib id artifact_prefix).Trim()
$releaseDir     = (& python -c "import brandlib; print(brandlib.brand_release_dir('$($env:LOCKSMITH_BRAND)'))").Trim()
Pop-Location
Write-Host "[build] brand=$($env:LOCKSMITH_BRAND) app=$($AppName).exe prefix=$ArtifactPrefix release=$releaseDir"

$distDir = Join-Path $repoRoot "dist\$AppName"

# Build (or refresh) the brand's self-contained release bundle — assets.rcc,
# brand.json, Locksmith.wxs, dmg-layout.json, staged icons, trust material —
# before PyInstaller/wix read it. Idempotent (brand_apply always rewrites its
# output dir); CI's release workflow already runs this as its own step (once
# per Stage invocation), but calling it here too keeps this script correct
# standalone (e.g. local dev builds run directly, without the CI step).
& python (Join-Path $repoRoot "scripts\brand_apply.py") --brand $env:LOCKSMITH_BRAND
if ($LASTEXITCODE -ne 0) {
    throw "[build] brand_apply.py exited $LASTEXITCODE"
}

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
$GitCommit = (git rev-parse --short HEAD 2>$null)
if (-not $GitCommit) { $GitCommit = "unknown" }
$KeripyCommit = (Select-String -Path (Join-Path $repoRoot "pyproject.toml") -Pattern 'keripy\.git@([0-9a-f]+)' |
    Select-Object -First 1 | ForEach-Object { $_.Matches[0].Groups[1].Value.Substring(0, 8) })
if (-not $KeripyCommit) { $KeripyCommit = "unknown" }
@"
"""Build-time constants -- REWRITTEN by packaging/build-windows.ps1 at build time."""
from __future__ import annotations

LOCKSMITH_VERSION: str = "$Version"
LOCKSMITH_RELEASE_CHANNEL: str = "$env:LOCKSMITH_RELEASE_CHANNEL"
LOCKSMITH_GIT_COMMIT: str = "$GitCommit"
KERIPY_COMMIT: str = "$KeripyCommit"
"@ | Set-Content -Encoding utf8 -Path $buildInfo
Write-Host "[build] wrote $buildInfo"

# --- 3. PyInstaller -----------------------------------------------------------

if ($Stage -eq "all" -or $Stage -eq "pyinstaller") {
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

    $exePath = Join-Path $distDir "$($AppName).exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "[build] PyInstaller did not produce $exePath"
    }
    Write-Host "[build] PyInstaller ok exe=$exePath"
}

if ($Stage -eq "pyinstaller") {
    Write-Host "[build] stage=pyinstaller; stopping before harvest/wix so signing can splice in"
    return
}

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

$msiName = "$ArtifactPrefix-$($Version).msi"
$msiPath = Join-Path $buildDir $msiName
Write-Host "[build] linking $msiPath"

Push-Location $wixDir
try {
    # -d NAME=VAL    compile-time variable; resolves $(var.NAME) in wxs sources
    # -bindpath DIR  file lookup path; first hit wins for relative SourceFile refs.
    # Locksmith.wxs itself is now the brand-rendered copy in the release dir
    # (scripts/brand_apply.py -> brandlib.render_wxs), not the retired in-tree
    # packaging/wix/Locksmith.wxs. $releaseDir MUST come FIRST: everything
    # brand-specific — AppIcon.ico, the rendered banner.png/dialog.png chrome,
    # and license.rtf when the brand ships its own — lives there and has to win.
    # $wixDir is only the fallback for genuinely brand-neutral assets (today:
    # license.rtf for brands that don't override it). Putting $wixDir first is
    # what shipped Locksmith's triquetra in the v0.3.6 Usurance MSI.
    & wix build `
        (Join-Path $releaseDir "Locksmith.wxs") $harvestedWxs `
        -ext WixToolset.UI.wixext `
        -arch x64 `
        -d "Version=$Version" `
        -bindpath $releaseDir `
        -bindpath $wixDir `
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
