[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$OutputPath
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedRepoRoot = if ($RepoRoot) { (Resolve-Path -LiteralPath $RepoRoot).Path } else { (Resolve-Path (Join-Path $scriptRoot '..')).Path }
$generator = Join-Path $scriptRoot 'sync_project_manager_roadmap_site.py'
$manifest = Join-Path $resolvedRepoRoot 'site\content\site-manifest.json'
$resolvedOutput = if ($OutputPath) { $OutputPath } else { Join-Path $resolvedRepoRoot 'site\src\data\project-manager.json' }

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$pythonExecutable = $null
if ($pythonCommand -and $pythonCommand.Source -notlike '*\WindowsApps\*') {
    $pythonExecutable = $pythonCommand.Source
}

if (-not $pythonExecutable) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $pythonExecutable = $bundledPython
    }
}

if (-not $pythonExecutable) {
    throw 'A real Python executable was not found. Install Python or make the bundled Codex runtime available.'
}

$arguments = @(
    $generator,
    '--repo-root', $resolvedRepoRoot,
    '--manifest', $manifest,
    '--output', $resolvedOutput
)

& $pythonExecutable @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
