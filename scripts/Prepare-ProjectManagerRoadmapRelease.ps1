[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$SourceRoot,
  [Parameter(Mandatory = $true)][string]$DeploymentRoot,
  [switch]$SkipBuild,
  [string]$DocumentationInputPath = '',
  [string]$HealthInputPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$allowedGeneratedPaths = @(
  'site/src/data/project-manager.json',
  'site/src/data/project-manager-health.json'
)

function Resolve-AbsoluteDirectory {
  param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)

  if (-not [System.IO.Path]::IsPathRooted($Path)) {
    throw "$Label must be an absolute path"
  }
  $fullPath = [System.IO.Path]::GetFullPath($Path)
  if (-not (Test-Path -LiteralPath $fullPath -PathType Container)) {
    throw "$Label does not exist"
  }
  return (Resolve-Path -LiteralPath $fullPath).Path
}

function Resolve-InputFile {
  param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)

  $fullPath = [System.IO.Path]::GetFullPath($Path)
  if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    throw "$Label does not exist"
  }
  return (Resolve-Path -LiteralPath $fullPath).Path
}

function Resolve-HealthyPython {
  $candidates = @(
    (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
  )
  $command = Get-Command python -ErrorAction SilentlyContinue
  if ($null -ne $command -and -not [string]::IsNullOrWhiteSpace([string]$command.Source)) {
    $candidates += [string]$command.Source
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

function Get-NormalizedStatusPath {
  param([Parameter(Mandatory = $true)][string]$StatusLine)

  if ($StatusLine.Length -lt 4) {
    return ''
  }
  $path = $StatusLine.Substring(3).Trim().Trim('"').Replace('\', '/')
  if ($path.Contains(' -> ')) {
    $path = $path.Split(' -> ')[-1].Trim().Trim('"')
  }
  return $path
}

function Test-FileChanged {
  param([Parameter(Mandatory = $true)][string]$Source, [Parameter(Mandatory = $true)][string]$Destination)

  if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
    return $true
  }
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
}

$resolvedSourceRoot = Resolve-AbsoluteDirectory -Path $SourceRoot -Label 'Source root'
$resolvedDeploymentRoot = Resolve-AbsoluteDirectory -Path $DeploymentRoot -Label 'Deployment root'
$git = Get-Command git -ErrorAction Stop
$branch = ([string](@(& $git.Source -C $resolvedDeploymentRoot branch --show-current 2>$null)[-1])).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'codex/project-manager-rock-solid') {
  throw 'Deployment root must be attached to codex/project-manager-rock-solid'
}

$statusLines = @(& $git.Source -C $resolvedDeploymentRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
  throw 'Unable to inspect deployment worktree status'
}
$unrelatedChanges = @(
  foreach ($line in $statusLines) {
    $normalized = Get-NormalizedStatusPath -StatusLine ([string]$line)
    if (-not [string]::IsNullOrWhiteSpace($normalized) -and $normalized -notin $allowedGeneratedPaths) {
      $normalized
    }
  }
)
if ($unrelatedChanges.Count -gt 0) {
  throw 'Deployment worktree contains unrelated changes'
}

$temporaryRoot = [System.IO.Path]::GetTempPath()
$temporaryDocumentation = Join-Path $temporaryRoot ("pm-roadmap-docs-" + [guid]::NewGuid().ToString('N') + '.json')
$temporaryHealth = Join-Path $temporaryRoot ("pm-roadmap-health-" + [guid]::NewGuid().ToString('N') + '.json')
$documentationSource = $null
$healthSource = $null

try {
  if (-not [string]::IsNullOrWhiteSpace($DocumentationInputPath)) {
    $documentationSource = Resolve-InputFile -Path $DocumentationInputPath -Label 'Documentation input'
  } else {
    $python = Resolve-HealthyPython
    $syncScript = Join-Path $resolvedDeploymentRoot 'scripts\sync_project_manager_roadmap_site.py'
    $manifest = Join-Path $resolvedDeploymentRoot 'site\content\site-manifest.json'
    if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf) -or -not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
      throw 'Roadmap documentation generator is unavailable'
    }
    & $python $syncScript --repo-root $resolvedSourceRoot --manifest $manifest --output $temporaryDocumentation *> $null
    if ($LASTEXITCODE -ne 0) {
      throw 'Roadmap documentation generation failed'
    }
    $documentationSource = $temporaryDocumentation
  }

  if (-not [string]::IsNullOrWhiteSpace($HealthInputPath)) {
    $healthSource = Resolve-InputFile -Path $HealthInputPath -Label 'Health input'
  } else {
    $healthSyncScript = Join-Path $resolvedDeploymentRoot 'scripts\Sync-ProjectManagerPublicHealth.ps1'
    if (-not (Test-Path -LiteralPath $healthSyncScript -PathType Leaf)) {
      throw 'Roadmap health generator is unavailable'
    }
    & $healthSyncScript -ProjectRoot $resolvedSourceRoot -OutputPath $temporaryHealth -MaxAgeMinutes 30 *> $null
    if (-not $?) {
      throw 'Roadmap health generation failed'
    }
    $healthSource = $temporaryHealth
  }

  $documentation = Get-Content -Raw -LiteralPath $documentationSource | ConvertFrom-Json -Depth 100
  $health = Get-Content -Raw -LiteralPath $healthSource | ConvertFrom-Json -Depth 30
  if ([int]$documentation.schemaVersion -ne 1 -or $null -eq $documentation.documents -or $null -eq $documentation.generated) {
    throw 'Documentation snapshot schema is invalid'
  }
  if ([int]$health.schemaVersion -ne 1 -or [string]$health.contentDigest -notmatch '^[0-9a-f]{64}$') {
    throw 'Health snapshot schema is invalid'
  }

  $dataDirectory = Join-Path $resolvedDeploymentRoot 'site\src\data'
  if (-not (Test-Path -LiteralPath $dataDirectory -PathType Container)) {
    [System.IO.Directory]::CreateDirectory($dataDirectory) | Out-Null
  }
  $documentationDestination = Join-Path $dataDirectory 'project-manager.json'
  $healthDestination = Join-Path $dataDirectory 'project-manager-health.json'
  $documentationChanged = Test-FileChanged -Source $documentationSource -Destination $documentationDestination
  $healthChanged = Test-FileChanged -Source $healthSource -Destination $healthDestination
  if ($documentationChanged) {
    [System.IO.File]::Copy($documentationSource, $documentationDestination, $true)
  }
  if ($healthChanged) {
    [System.IO.File]::Copy($healthSource, $healthDestination, $true)
  }

  if (-not $SkipBuild) {
    $python = Resolve-HealthyPython
    $uv = Get-Command uv -ErrorAction Stop
    $testFiles = @(
      'tests/test_project_manager_runtime_state_contract.py',
      'tests/test_project_manager_public_health.py',
      'tests/test_project_manager_public_health_wrappers.py',
      'tests/test_project_manager_roadmap_site_sync.py'
    )
    & $uv.Source run --isolated --no-project --with pytest --python $python -m pytest @testFiles -q *> $null
    if ($LASTEXITCODE -ne 0) {
      throw 'Focused Project Manager roadmap tests failed'
    }
    Push-Location (Join-Path $resolvedDeploymentRoot 'site')
    try {
      & pnpm --ignore-workspace test *> $null
      if ($LASTEXITCODE -ne 0) {
        throw 'Roadmap site tests failed'
      }
      & pnpm --ignore-workspace build *> $null
      if ($LASTEXITCODE -ne 0) {
        throw 'Roadmap site build failed'
      }
    } finally {
      Pop-Location
    }
  }

  [pscustomobject]@{
    status = 'ok'
    documentationChanged = [bool]$documentationChanged
    healthChanged = [bool]$healthChanged
    changed = [bool]($documentationChanged -or $healthChanged)
    documentCount = [int]$documentation.generated.documentCount
    healthDigest = [string]$health.contentDigest
    deploymentRoot = $resolvedDeploymentRoot
  } | ConvertTo-Json -Compress
} finally {
  Remove-Item -LiteralPath $temporaryDocumentation -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $temporaryHealth -Force -ErrorAction SilentlyContinue
}
