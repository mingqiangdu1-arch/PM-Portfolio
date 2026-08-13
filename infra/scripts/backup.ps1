param(
    [switch]$Execute,
    [string]$BackupRoot = $env:BACKUP_ROOT
)

$ErrorActionPreference = "Stop"
if (-not $BackupRoot) { $BackupRoot = Join-Path $PSScriptRoot "..\..\backups" }
$resolvedRoot = [System.IO.Path]::GetFullPath($BackupRoot)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $resolvedRoot $stamp

Write-Output "Backup plan: MySQL logical dump + object-storage mirror -> $target"
if (-not $Execute) {
    Write-Output "DRY-RUN: no data was read or written"
    exit 0
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
docker compose -f infra/compose/compose.yaml exec -T mysql sh -c 'exec mysqldump --all-databases --single-transaction -uroot --password="$(cat /run/secrets/mysql_root_password)"' | Set-Content -Encoding utf8 (Join-Path $target "mysql.sql")
docker compose -f infra/compose/compose.yaml exec -T minio sh -c 'mc mirror --overwrite /data /backup/object-data'
Write-Output "Backup completed: $target"
