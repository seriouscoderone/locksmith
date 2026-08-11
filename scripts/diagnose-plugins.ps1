<#
.SYNOPSIS
    Read-only diagnostic for "the role says Active but its workspace won't open".

.DESCRIPTION
    A role card shows "Active" purely from the held credential, but its Open
    button and sidebar entry also require the role's plugin to have registered
    a page (ui/onboarding/home_page.py: `status is ACTIVE and page_available`).
    So an ACTIVE role with no workspace means the plugin did not load in that
    process. This script collects the evidence that says why.

    Writes a transcript next to itself on the Desktop; send that file back.

    Changes nothing. Reads the install dir, the log, and two config files.

.PARAMETER Brand
    Brand/app name. Defaults to Usurance.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\diagnose-plugins.ps1

.NOTES
    Run AFTER quitting every wallet window and relaunching once, then opening
    the vault: plugin discovery is logged once per process at startup, so a
    stale process yields a stale answer.
#>
[CmdletBinding()]
param(
    [string]$Brand = "Usurance",
    [string]$OutFile = "$env:USERPROFILE\Desktop\wallet-plugin-diag.txt"
)

$ErrorActionPreference = "Continue"
$lines = New-Object System.Collections.Generic.List[string]

function Say([string]$Text = "") {
    Write-Host $Text
    $lines.Add($Text) | Out-Null
}

function Section([string]$Title) {
    Say ""
    Say ("=" * 72)
    Say "  $Title"
    Say ("=" * 72)
}

Section "0. Context"
Say "generated : $(Get-Date -Format o)"
Say "brand     : $Brand"
Say "user      : $env:USERNAME on $env:COMPUTERNAME"
Say "powershell: $($PSVersionTable.PSVersion)"

# --- Resolve the install directory -------------------------------------------
# Prefer the running process's own path over the default location: a relocated
# or machine-wide install would otherwise be checked at the wrong directory and
# report a packaging problem that isn't there.
$proc = @(Get-Process -Name $Brand -ErrorAction SilentlyContinue)
$appDir = $null
if ($proc.Count -gt 0 -and $proc[0].Path) {
    $appDir = Split-Path -Parent $proc[0].Path
    Say "install   : $appDir  (from running process)"
} else {
    $appDir = Join-Path $env:LOCALAPPDATA "Programs\$Brand"
    Say "install   : $appDir  (default location; app not running)"
}
Say "instances : $($proc.Count) running"
if ($proc.Count -gt 1) {
    Say "  NOTE: more than one instance. A surviving parent can pass a stale"
    Say "        environment to instances spawned from it."
}

# --- Version ------------------------------------------------------------------
Section "1. Installed version"
$distInfo = @(Get-ChildItem -Path (Join-Path $appDir "_internal") -Filter "locksmith-*.dist-info" -Directory -ErrorAction SilentlyContinue)
if ($distInfo.Count -gt 0) {
    foreach ($d in $distInfo) { Say $d.Name }
} else {
    Say "NOT FOUND: no locksmith-*.dist-info under $appDir\_internal"
    Say "  -> plugin discovery CANNOT work without this; likely a packaging problem."
}

# --- Plugin metadata shipped? --------------------------------------------------
Section "2. Plugin entry-point metadata shipped in the install"
$epFiles = @(Get-ChildItem -Path (Join-Path $appDir "_internal") -Filter "entry_points.txt" -Recurse -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -like "*locksmith-*" })
if ($epFiles.Count -gt 0) {
    foreach ($f in $epFiles) {
        Say "--- $($f.FullName)"
        Get-Content $f.FullName | ForEach-Object { Say $_ }
    }
} else {
    Say "NOT FOUND: no locksmith entry_points.txt"
    Say "  -> the build did not ship plugin metadata (copy_metadata missing)."
}

# --- Environment ---------------------------------------------------------------
Section "3. Environment overrides (expected: none)"
$envVars = @(Get-ChildItem Env: | Where-Object { $_.Name -like "LOCKSMITH*" -or $_.Name -like "KERI*" })
if ($envVars.Count -eq 0) {
    Say "(none - good)"
} else {
    foreach ($e in $envVars) { Say "$($e.Name) = $($e.Value)" }
    Say "  NOTE: LOCKSMITH_BRAND_CONFIG here can point the app at another brand,"
    Say "        which vetoes that brand's non-listed plugins as 'not_bundled'."
}

# --- Per-wallet exclude list ----------------------------------------------------
Section "4. Per-wallet plugin exclude list"
$enablePath = Join-Path $env:USERPROFILE ".keri\locksmith\plugin-enable.json"
Say "path: $enablePath"
if (Test-Path $enablePath) {
    Get-Content $enablePath | ForEach-Object { Say $_ }
    Say "  NOTE: any id in 'excluded' is skipped with reason=excluded."
} else {
    Say "(absent - the default; nothing excluded)"
}

# --- The log --------------------------------------------------------------------
Section "5. Plugin discovery (the verdict)"
$logDir = Join-Path $env:LOCALAPPDATA $Brand
$log = Join-Path $logDir "logs\$($Brand.ToLower()).log"
if (-not (Test-Path $log)) {
    Say "default log path missing: $log"
    $found = @(Get-ChildItem -Path $logDir -Recurse -Filter "*.log" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending)
    if ($found.Count -gt 0) {
        $log = $found[0].FullName
        Say "using most recent instead: $log"
    } else {
        $log = $null
        Say "NO LOG FILES FOUND under $logDir"
    }
}

if ($log) {
    Say "log: $log"
    Say ""
    $hits = @(Select-String -Path $log -Pattern "plugin\.(discovery|skipped|loaded|load_failed)" -ErrorAction SilentlyContinue)
    if ($hits.Count -eq 0) {
        Say "NO plugin.* lines in the log at all."
        Say "  -> either this log predates plugin discovery, or the app has not"
        Say "     started since the log rotated. Quit all windows, relaunch, rerun."
    } else {
        foreach ($h in ($hits | Select-Object -Last 15)) { Say $h.Line }
    }

    Section "6. Anything mentioning the actuary role"
    $act = @(Select-String -Path $log -Pattern "actuary" -ErrorAction SilentlyContinue)
    if ($act.Count -eq 0) {
        Say "(no mentions)"
    } else {
        foreach ($h in ($act | Select-Object -Last 20)) { Say $h.Line }
    }

    Section "7. Recent errors and tracebacks"
    $err = @(Select-String -Path $log -Pattern "ERROR|CRITICAL|Traceback|Exception" -ErrorAction SilentlyContinue)
    if ($err.Count -eq 0) {
        Say "(none)"
    } else {
        foreach ($h in ($err | Select-Object -Last 20)) { Say $h.Line }
    }
}

Section "Done"
Say "Send this file back: $OutFile"

try {
    $lines | Set-Content -Path $OutFile -Encoding UTF8
    Write-Host ""
    Write-Host "Transcript written to: $OutFile" -ForegroundColor Green
} catch {
    Write-Host "Could not write $OutFile : $_" -ForegroundColor Yellow
}
