[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$ProjectRoot,
  [Parameter(Mandatory = $true)][string]$OutputPath,
  [ValidateRange(1, 1440)][int]$MaxAgeMinutes = 30,
  [string]$PluginRoot = '',
  [string]$PythonExe = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-ExistingDirectory {
  param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)

  $fullPath = [System.IO.Path]::GetFullPath($Path)
  if (-not (Test-Path -LiteralPath $fullPath -PathType Container)) {
    throw "$Label directory does not exist"
  }
  return (Resolve-Path -LiteralPath $fullPath).Path
}

function Test-CompactWrapperPair {
  param([Parameter(Mandatory = $true)][string]$CandidateRoot)

  return (
    (Test-Path -LiteralPath (Join-Path $CandidateRoot 'scripts\Invoke-ProjectManagerEnvironmentHealth.ps1') -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $CandidateRoot 'scripts\Get-ProjectManagerStabilityAudit.ps1') -PathType Leaf)
  )
}

function Resolve-CompactPluginRoot {
  param([string]$RequestedRoot, [Parameter(Mandatory = $true)][string]$SourceRoot)

  $candidates = New-Object System.Collections.Generic.List[string]
  if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
    $candidates.Add([System.IO.Path]::GetFullPath($RequestedRoot))
  }
  $candidates.Add($SourceRoot)

  $cacheParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\plugins\cache\personal\project-manager'
  if (Test-Path -LiteralPath $cacheParent -PathType Container) {
    foreach ($directory in @(Get-ChildItem -LiteralPath $cacheParent -Directory | Sort-Object LastWriteTimeUtc -Descending)) {
      $candidates.Add($directory.FullName)
    }
  }

  foreach ($candidate in $candidates) {
    if ((Test-Path -LiteralPath $candidate -PathType Container) -and (Test-CompactWrapperPair -CandidateRoot $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw 'Project Manager compact health wrappers are unavailable'
}

function Resolve-HealthyPython {
  param([string]$RequestedPython)

  $candidates = New-Object System.Collections.Generic.List[string]
  if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
    $candidates.Add([System.IO.Path]::GetFullPath($RequestedPython))
  } else {
    $bundled = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $candidates.Add($bundled)
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $command -and -not [string]::IsNullOrWhiteSpace([string]$command.Source)) {
      $candidates.Add([string]$command.Source)
    }
  }

  foreach ($candidate in $candidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      continue
    }
    & $candidate -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' *> $null
    if ($LASTEXITCODE -eq 0) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw 'A healthy Python 3.10+ runtime is unavailable'
}

$resolvedProjectRoot = Resolve-ExistingDirectory -Path $ProjectRoot -Label 'Project root'
$resolvedPluginRoot = Resolve-CompactPluginRoot -RequestedRoot $PluginRoot -SourceRoot $resolvedProjectRoot
$resolvedPython = Resolve-HealthyPython -RequestedPython $PythonExe
$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$sanitizerPath = Join-Path $PSScriptRoot 'project_manager_public_health.py'
if (-not (Test-Path -LiteralPath $sanitizerPath -PathType Leaf)) {
  throw 'Project Manager public health sanitizer is unavailable'
}

$healthWrapper = Join-Path $resolvedPluginRoot 'scripts\Invoke-ProjectManagerEnvironmentHealth.ps1'
$stabilityWrapper = Join-Path $resolvedPluginRoot 'scripts\Get-ProjectManagerStabilityAudit.ps1'
$registryFile = Join-Path $resolvedProjectRoot 'docs\project-manager\worker-registry.json'
$ledgerFile = Join-Path $resolvedProjectRoot 'docs\project-manager\manager-ledger.jsonl'
$temporaryRoot = [System.IO.Path]::GetTempPath()
$healthRawPath = Join-Path $temporaryRoot ("pm-public-health-" + [guid]::NewGuid().ToString('N') + '.json')
$stabilityRawPath = Join-Path $temporaryRoot ("pm-public-stability-" + [guid]::NewGuid().ToString('N') + '.json')

try {
  & $healthWrapper `
    -PluginRoot $resolvedPluginRoot `
    -ProjectRoot $resolvedProjectRoot `
    -RegistryFile $registryFile `
    -LedgerFile $ledgerFile `
    -HeartbeatIntervalMinutes 15 `
    -ScanHostHealth `
    -Compact | Set-Content -LiteralPath $healthRawPath -Encoding UTF8
  if (-not $?) {
    throw 'Project Manager environment health wrapper failed'
  }

  & $stabilityWrapper `
    -PluginRoot $resolvedPluginRoot `
    -ProjectRoot $resolvedProjectRoot `
    -RegistryFile $registryFile `
    -LedgerFile $ledgerFile `
    -Compact | Set-Content -LiteralPath $stabilityRawPath -Encoding UTF8
  if (-not $?) {
    throw 'Project Manager stability audit wrapper failed'
  }

  $revision = 'unknown'
  $sourceDirty = $false
  $git = Get-Command git -ErrorAction SilentlyContinue
  if ($null -ne $git) {
    $revisionOutput = @(& $git.Source -C $resolvedProjectRoot rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $revisionOutput.Count -gt 0) {
      $candidateRevision = ([string]$revisionOutput[-1]).Trim()
      if ($candidateRevision -match '^[0-9a-f]{40}$') {
        $revision = $candidateRevision
      }
    }
    $statusOutput = @(& $git.Source -C $resolvedProjectRoot status --porcelain 2>$null)
    if ($LASTEXITCODE -eq 0) {
      $sourceDirty = $statusOutput.Count -gt 0
    }
  }

  $generatedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
  $sanitizerArguments = @(
    $sanitizerPath,
    '--health-input', $healthRawPath,
    '--stability-input', $stabilityRawPath,
    '--output', $resolvedOutputPath,
    '--generated-at', $generatedAt,
    '--max-age-minutes', [string]$MaxAgeMinutes,
    '--source-revision', $revision
  )
  if ($sourceDirty) {
    $sanitizerArguments += '--source-dirty'
  }

  & $resolvedPython @sanitizerArguments
  if ($LASTEXITCODE -ne 0) {
    throw 'Project Manager public health sanitization failed'
  }

  $snapshot = Get-Content -Raw -LiteralPath $resolvedOutputPath | ConvertFrom-Json -Depth 20
  [pscustomobject]@{
    status = 'ok'
    schemaVersion = [int]$snapshot.schemaVersion
    contentDigest = [string]$snapshot.contentDigest
  } | ConvertTo-Json -Compress
} finally {
  Remove-Item -LiteralPath $healthRawPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $stabilityRawPath -Force -ErrorAction SilentlyContinue
}
