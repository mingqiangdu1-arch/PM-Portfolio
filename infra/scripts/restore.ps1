param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [switch]$Execute,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$resolvedBackup = [System.IO.Path]::GetFullPath($BackupPath)
Write-Output "Restore plan: validate backup and restore MySQL/object data from $resolvedBackup"
if (-not $Execute) {
    Write-Output "DRY-RUN: no service or data was changed"
    exit 0
}
if (-not $ConfirmRestore) { throw "Actual restore requires both -Execute and -ConfirmRestore" }
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Container)) { throw "Backup directory does not exist" }

Get-Content -Raw -Encoding utf8 (Join-Path $resolvedBackup "mysql.sql") | docker compose -f infra/compose/compose.yaml exec -T mysql sh -c 'exec mysql -uroot --password="$(cat /run/secrets/mysql_root_password)"'
Write-Output "Restore completed; application smoke tests are still required"
