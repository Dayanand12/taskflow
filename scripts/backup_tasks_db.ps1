$ErrorActionPreference = "Stop"

$rcloneCandidate = "C:\Users\Dayanand\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.74.4-windows-amd64\rclone.exe"
if (Test-Path $rcloneCandidate) {
    $rclone = $rcloneCandidate
} else {
    $rclone = "rclone"
}

$source = "C:\Trading\claude_practice\claude_practice\tasks.db"
$remoteFolder = "gdrivebackup:TasksDBBackup"
$logDir = "C:\Trading\claude_practice\claude_practice\backup_logs"
$retentionDays = 30

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$logFile = Join-Path $logDir ("backup_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))
$destName = "tasks_{0}.db" -f (Get-Date -Format "yyyy-MM-dd")

if (-not (Test-Path $source)) {
    Add-Content -Path $logFile -Value "$(Get-Date) - FAILED: source database not found at $source"
    exit 1
}

& $rclone copyto $source "$remoteFolder/$destName" --log-file $logFile --log-level INFO
if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $logFile -Value "$(Get-Date) - FAILED: rclone copyto exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

& $rclone delete $remoteFolder --min-age "${retentionDays}d" --log-file $logFile --log-level INFO

Add-Content -Path $logFile -Value "$(Get-Date) - Backup completed successfully: $destName"
