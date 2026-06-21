[CmdletBinding(SupportsShouldProcess)]
param(
  [string]$SourceRoot = "$HOME\.codex\plugins\local-marketplaces\personal\plugins\project-manager",
  [string]$CacheRoot = "",
  [string]$MirrorRoot = "$HOME\.agents\plugins\plugins\project-manager"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Sync-PluginRoot {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string[]]$RelativePaths
  )

  if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Path $Target | Out-Null
  }

  $copied = @()
  $skippedLocked = @()
  foreach ($relative in $RelativePaths) {
    $from = Join-Path $Source $relative
    if ($relative -eq 'scripts\project-manager-mcp.exe') {
      $publishedWrapper = Join-Path $Source 'scripts\wrapper-build\project-manager-mcp.exe'
      if (Test-Path -LiteralPath $publishedWrapper) {
        $from = $publishedWrapper
      }
    }
    $to = Join-Path $Target $relative
    if (-not (Test-Path -LiteralPath $from)) {
      continue
    }
    $parent = Split-Path -Parent $to
    if (-not (Test-Path -LiteralPath $parent)) {
      New-Item -ItemType Directory -Path $parent | Out-Null
    }
    if ($PSCmdlet.ShouldProcess($to, "Copy from $from")) {
      try {
        Copy-Item -LiteralPath $from -Destination $to -Force
        $copied += $relative
      } catch [System.IO.IOException] {
        if ((Test-Path -LiteralPath $to) -and ((Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash)) {
          $skippedLocked += $relative
        } else {
          throw
        }
      }
    }
  }

  $mcpPath = Join-Path $Target '.mcp.json'
  $mcp = @{
    mcpServers = @{
      'project-manager' = @{
        type = 'stdio'
        command = './scripts/project-manager-mcp.exe'
        args = @()
        cwd = '.'
      }
    }
  }
  $mcpJson = $mcp | ConvertTo-Json -Depth 6
  $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText($mcpPath, $mcpJson + [Environment]::NewLine, $utf8NoBom)

  return [pscustomobject]@{
    root = $Target
    copied = $copied
    skippedLockedUnchanged = $skippedLocked
  }
}

if (-not $CacheRoot) {
  $cacheBase = Join-Path $HOME '.codex\plugins\cache\personal\project-manager'
  $latest = Get-ChildItem -LiteralPath $cacheBase -Directory | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  if (-not $latest) {
    throw "No cached project-manager install found under $cacheBase"
  }
  $CacheRoot = $latest.FullName
}

$source = (Resolve-Path -LiteralPath $SourceRoot).Path
if (-not (Test-Path -LiteralPath $CacheRoot)) {
  New-Item -ItemType Directory -Path $CacheRoot | Out-Null
}
$cache = (Resolve-Path -LiteralPath $CacheRoot).Path
if (-not (Test-Path -LiteralPath $MirrorRoot)) {
  New-Item -ItemType Directory -Path $MirrorRoot | Out-Null
}
$mirror = (Resolve-Path -LiteralPath $MirrorRoot).Path

if ($source -eq $cache -or $source -eq $mirror) {
  throw 'SourceRoot must be distinct from cache and mirror roots.'
}
if (-not (Test-Path -LiteralPath (Join-Path $source '.codex-plugin\plugin.json'))) {
  throw "SourceRoot is not a project-manager plugin root: $source"
}

& (Join-Path $source 'scripts\Build-ProjectManagerWrapper.ps1') -PluginRoot $source
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

$relativePaths = @(
  '.codex-plugin\plugin.json',
  '.mcp.json',
  'README.md',
  'DEVELOPMENT_IMPROVEMENTS.md',
  'scripts\Build-ProjectManagerWrapper.ps1',
  'scripts\project_manager_mcp_server.py',
  'scripts\repair_project_manager_install.py',
  'scripts\wrapper-src\ProjectManagerMcpWrapper.csproj',
  'scripts\wrapper-src\Program.cs',
  'scripts\project-manager-mcp.exe',
  'scripts\Test-ProjectManagerPlugin.ps1',
  'scripts\Test-ProjectManagerProxyExports.ps1',
  'scripts\Sync-ProjectManagerPlugin.ps1',
  'scripts\Check-ProjectManagerCacheConsistency.ps1',
  'skills\project-manager\SKILL.md',
  'tests\test_project_manager_mcp_server.py',
  'generated\canonical-model-catalog.json',
  'generated\proxy-model-list.json',
  'generated\proxy-runtime-instructions.json'
)

$cacheSync = Sync-PluginRoot -Source $source -Target $cache -RelativePaths $relativePaths
$mirrorSync = Sync-PluginRoot -Source $source -Target $mirror -RelativePaths $relativePaths

[pscustomobject]@{
  status = 'ok'
  sourceRoot = $source
  cacheRoot = $cache
  mirrorRoot = $mirror
  cacheSync = $cacheSync
  mirrorSync = $mirrorSync
} | ConvertTo-Json -Depth 6
