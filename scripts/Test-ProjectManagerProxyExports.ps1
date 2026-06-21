[CmdletBinding()]
param(
  [string]$PluginRoot = "$HOME\.codex\plugins\local-marketplaces\personal\plugins\project-manager"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $PluginRoot).Path
$generated = Join-Path $root 'generated'
$modelListPath = Join-Path $generated 'proxy-model-list.json'
$runtimePath = Join-Path $generated 'proxy-runtime-instructions.json'

if (-not (Test-Path -LiteralPath $modelListPath)) {
  throw "Missing proxy model list export: $modelListPath"
}
if (-not (Test-Path -LiteralPath $runtimePath)) {
  throw "Missing proxy runtime export: $runtimePath"
}

$modelList = Get-Content -LiteralPath $modelListPath -Raw | ConvertFrom-Json
$runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
$visibleSlugs = @($modelList.models | ForEach-Object { $_.slug })
$runtimeModels = $runtime.models

if ($visibleSlugs -contains 'qwen3.7-plus') {
  throw 'qwen3.7-plus leaked into proxy model list.'
}
if (-not ($visibleSlugs -contains 'deepseek-v4-flash')) {
  throw 'deepseek-v4-flash missing from proxy model list.'
}
if (-not ($visibleSlugs -contains 'deepseek-v4-pro')) {
  throw 'deepseek-v4-pro missing from proxy model list.'
}
if ($runtimeModels.'qwen3.7-plus'.enabled -ne $false) {
  throw 'qwen3.7-plus runtime entry must remain disabled.'
}

[pscustomobject]@{
  status = 'ok'
  pluginRoot = $root
  modelListPath = $modelListPath
  runtimePath = $runtimePath
  visibleModelCount = $visibleSlugs.Count
  qwenDisabled = $true
  deepseekFlashVisible = $visibleSlugs -contains 'deepseek-v4-flash'
  deepseekProVisible = $visibleSlugs -contains 'deepseek-v4-pro'
} | ConvertTo-Json -Depth 5
