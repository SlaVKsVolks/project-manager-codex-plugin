[CmdletBinding()]
param(
  [string]$LogPath = "$env:LOCALAPPDATA\Codex\project-manager\project-manager-mcp.log",
  [int]$Tail = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $LogPath)) {
  [pscustomobject]@{
    status = 'missing'
    logPath = $LogPath
    eventCount = 0
    errorCount = 0
    latestEvent = $null
    recentEvents = @()
  } | ConvertTo-Json -Depth 6
  exit 0
}

$events = New-Object System.Collections.Generic.List[object]
Get-Content -LiteralPath $LogPath -Tail $Tail | ForEach-Object {
  if (-not [string]::IsNullOrWhiteSpace($_)) {
    try {
      $events.Add($_ | ConvertFrom-Json)
    } catch {
    }
  }
}

$errorEvents = @($events | Where-Object { $_.event -in @('request_exception', 'fatal_exception', 'json_decode_error') })
$result = [pscustomobject]@{
  status = 'ok'
  logPath = $LogPath
  eventCount = $events.Count
  errorCount = $errorEvents.Count
  latestEvent = if ($events.Count -gt 0) { $events[$events.Count - 1] } else { $null }
  recentEvents = @($events | Select-Object -Last 5)
}

$result | ConvertTo-Json -Depth 6
