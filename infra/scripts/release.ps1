param(
    [Parameter(Mandatory=$true)][string]$ImageTag,
    [ValidateSet("staging", "production")][string]$Environment = "staging",
    [switch]$Execute
)

$ErrorActionPreference = "Stop"
if ($ImageTag -match ':latest$' -or $ImageTag -notmatch '^[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$') {
    throw "ImageTag must be an explicit non-latest tag"
}
$override = "infra/compose/compose.$Environment.yaml"
Write-Output "Release plan: $ImageTag using $override; migrate once; health-check; retain rollback tag"
if (-not $Execute) {
    Write-Output "DRY-RUN: no image, database or service was changed"
    exit 0
}
throw "Execution skeleton intentionally stops here until the Review window freezes deployment gates"
