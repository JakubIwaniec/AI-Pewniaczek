$ErrorActionPreference = "Continue"
Set-StrictMode -Version 3.0

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$LogPath = Join-Path $Root "data\post_repair_followup.log"
$LockPath = Join-Path $Root "data\.flashscore_repair.lock"

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value $line
    Write-Host $line
}

# Resolve repair PID from lock if present (falls back to waiting on any repair process)
function Get-RepairPids {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*data_integrity_flashscore.py*--repair*' } |
        ForEach-Object { [int]$_.ProcessId }
}

$targetPid = $null
if (Test-Path -LiteralPath $LockPath) {
    try { $targetPid = [int]((Get-Content -LiteralPath $LockPath -Raw).Trim()) } catch {}
}

Write-Log "Follow-up watcher started. Lock PID=$targetPid"

if ($targetPid -and (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
    Write-Log "Waiting for PID $targetPid (--repair) to exit..."
    while (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Seconds 60
    }
    Write-Log "PID $targetPid exited."
}
else {
    Write-Log "Lock PID missing or already gone; waiting until no --repair python processes remain."
    while ($true) {
        $active = @(Get-RepairPids)
        if ($active.Count -eq 0) { break }
        Write-Log ("Still running repair PIDs: " + ($active -join ", "))
        Start-Sleep -Seconds 60
    }
    Write-Log "No active repair processes detected."
}

Start-Sleep -Seconds 3

if (Test-Path -LiteralPath $LockPath) {
    try {
        $lckPid = [int]((Get-Content -LiteralPath $LockPath -Raw).Trim())
        if (-not (Get-Process -Id $lckPid -ErrorAction SilentlyContinue)) {
            Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
            Write-Log "Removed stale repair lock file (PID $lckPid not running)."
        }
    }
    catch {
        Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
        Write-Log "Removed unreadable stale lock file."
    }
}

Write-Log "Running post-repair audit (--audit-only)..."
$audit = & $Py -u (Join-Path $Root "scripts\data_integrity_flashscore.py") --audit-only 2>&1 | Out-String
Write-Log "---- AUDIT OUTPUT ----"
$audit.TrimEnd() -split "`n" | ForEach-Object { Write-Log $_ }
Write-Log "---- END AUDIT ----"

$m = [regex]::Match($audit, 'incomplete_events=(\d+)')
if ($m.Success -and [int]$m.Groups[1].Value -gt 0) {
    Write-Log "Gaps remain ($($m.Groups[1].Value)); starting second pass (--repair)..."
    $repairOut = & $Py -u (Join-Path $Root "scripts\data_integrity_flashscore.py") --repair 2>&1 | Out-String
    Write-Log "---- REPAIR PASS OUTPUT (last 80 lines) ----"
    $repairOut.TrimEnd().Split("`n") | Select-Object -Last 80 | ForEach-Object { Write-Log $_.TrimEnd("`r") }
    Write-Log "---- END REPAIR PASS (last 80 lines) ----"
}
else {
    Write-Log "Audit shows no incomplete_events (or could not parse); skipping extra --repair."
}

Write-Log "Follow-up watcher finished."
