[CmdletBinding()]
param(
  [string]$SourceRoot = "$HOME\.codex\plugins\local-marketplaces\personal\plugins\project-manager",
  [string]$CacheRoot = "",
  [string]$MirrorRoot = "$HOME\.agents\plugins\plugins\project-manager"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-JsonFile {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing JSON file: $Path"
  }
  return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

if (-not $CacheRoot) {
  $cacheBase = Join-Path $HOME '.codex\plugins\cache\personal\project-manager'
  $latest = Get-ChildItem -LiteralPath $cacheBase -Directory | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  if (-not $latest) {
    throw "No cached project-manager install found under $cacheBase"
  }
  $CacheRoot = $latest.FullName
}

$sourcePlugin = Read-JsonFile -Path (Join-Path $SourceRoot '.codex-plugin\plugin.json')
$cachePlugin = Read-JsonFile -Path (Join-Path $CacheRoot '.codex-plugin\plugin.json')
$mirrorPlugin = Read-JsonFile -Path (Join-Path $MirrorRoot '.codex-plugin\plugin.json')
$sourceMcp = Read-JsonFile -Path (Join-Path $SourceRoot '.mcp.json')
$cacheMcp = Read-JsonFile -Path (Join-Path $CacheRoot '.mcp.json')
$mirrorMcp = Read-JsonFile -Path (Join-Path $MirrorRoot '.mcp.json')

$issues = New-Object System.Collections.Generic.List[string]

$sourceVersion = [string]$sourcePlugin.version
$cacheVersion = [string]$cachePlugin.version
$mirrorVersion = [string]$mirrorPlugin.version
$sourceWrapper = Join-Path $SourceRoot 'scripts\project-manager-mcp.exe'
$cacheWrapper = Join-Path $CacheRoot 'scripts\project-manager-mcp.exe'
$mirrorWrapper = Join-Path $MirrorRoot 'scripts\project-manager-mcp.exe'
$sourceServer = Join-Path $SourceRoot 'scripts\project_manager_mcp_server.py'
$cacheServer = Join-Path $CacheRoot 'scripts\project_manager_mcp_server.py'
$mirrorServer = Join-Path $MirrorRoot 'scripts\project_manager_mcp_server.py'
$sourceCommand = [string]$sourceMcp.mcpServers.'project-manager'.command
$cacheCommand = [string]$cacheMcp.mcpServers.'project-manager'.command
$mirrorCommand = [string]$mirrorMcp.mcpServers.'project-manager'.command

if ($sourceVersion -ne $cacheVersion) {
  $issues.Add("Version mismatch: source=$sourceVersion cache=$cacheVersion")
}
if ($sourceVersion -ne $mirrorVersion) {
  $issues.Add("Version mismatch: source=$sourceVersion mirror=$mirrorVersion")
}
if ($sourceCommand -ne './scripts/project-manager-mcp.exe') {
  $issues.Add("Unexpected source MCP command: $sourceCommand")
}
if ($cacheCommand -ne './scripts/project-manager-mcp.exe') {
  $issues.Add("Unexpected cache MCP command: $cacheCommand")
}
if ($mirrorCommand -ne './scripts/project-manager-mcp.exe') {
  $issues.Add("Unexpected mirror MCP command: $mirrorCommand")
}
if (-not (Test-Path -LiteralPath $sourceWrapper)) {
  $issues.Add("Missing source wrapper: $sourceWrapper")
}
if (-not (Test-Path -LiteralPath $cacheWrapper)) {
  $issues.Add("Missing cache wrapper: $cacheWrapper")
}
if (-not (Test-Path -LiteralPath $mirrorWrapper)) {
  $issues.Add("Missing mirror wrapper: $mirrorWrapper")
}
if (-not (Test-Path -LiteralPath $sourceServer)) {
  $issues.Add("Missing source server: $sourceServer")
}
if (-not (Test-Path -LiteralPath $cacheServer)) {
  $issues.Add("Missing cache server: $cacheServer")
}
if (-not (Test-Path -LiteralPath $mirrorServer)) {
  $issues.Add("Missing mirror server: $mirrorServer")
}

$result = [pscustomobject]@{
  sourceRoot = $SourceRoot
  cacheRoot = $CacheRoot
  mirrorRoot = $MirrorRoot
  sourceVersion = $sourceVersion
  cacheVersion = $cacheVersion
  mirrorVersion = $mirrorVersion
  versionsMatch = ($sourceVersion -eq $cacheVersion)
  mirrorVersionMatches = ($sourceVersion -eq $mirrorVersion)
  sourceWrapperExists = (Test-Path -LiteralPath $sourceWrapper)
  cacheWrapperExists = (Test-Path -LiteralPath $cacheWrapper)
  mirrorWrapperExists = (Test-Path -LiteralPath $mirrorWrapper)
  sourceServerExists = (Test-Path -LiteralPath $sourceServer)
  cacheServerExists = (Test-Path -LiteralPath $cacheServer)
  mirrorServerExists = (Test-Path -LiteralPath $mirrorServer)
  sourceCommand = $sourceCommand
  cacheCommand = $cacheCommand
  mirrorCommand = $mirrorCommand
  issues = @($issues)
}

$result | ConvertTo-Json -Depth 6
if ($issues.Count -gt 0) {
  exit 1
}
