[CmdletBinding()]
param(
  [string]$PluginRoot = "$HOME\.codex\plugins\local-marketplaces\personal\plugins\project-manager"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $PluginRoot).Path
$wrapperProject = Join-Path $root 'scripts\wrapper-src\ProjectManagerMcpWrapper.csproj'
$publishDir = Join-Path $root 'scripts\wrapper-build'
$publishedExe = Join-Path $publishDir 'project-manager-mcp.exe'
$targetExe = Join-Path $root 'scripts\project-manager-mcp.exe'

if (-not (Test-Path -LiteralPath $wrapperProject)) {
  throw "Missing wrapper project: $wrapperProject"
}

if (-not (Test-Path -LiteralPath $publishDir)) {
  New-Item -ItemType Directory -Path $publishDir | Out-Null
}

& dotnet publish $wrapperProject -c Release -r win-x64 --self-contained false -o $publishDir
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $publishedExe)) {
  throw "dotnet publish completed but wrapper exe was not produced: $publishedExe"
}

$targetUpdated = $false
$targetUpdateSkippedLocked = $false
try {
  Copy-Item -LiteralPath $publishedExe -Destination $targetExe -Force
  $targetUpdated = $true
} catch {
  $message = $_.Exception.Message
  if ($message -like '*because it is being used by another process*') {
    $targetUpdateSkippedLocked = $true
  } else {
    throw
  }
}

[pscustomobject]@{
  status = 'ok'
  pluginRoot = $root
  wrapperProject = $wrapperProject
  publishedExe = $publishedExe
  targetExe = $targetExe
  targetUpdated = $targetUpdated
  targetUpdateSkippedLocked = $targetUpdateSkippedLocked
} | ConvertTo-Json -Depth 4
