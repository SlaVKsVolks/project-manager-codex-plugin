[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$WorkerFinalJson)

try {
  $payload = $WorkerFinalJson | ConvertFrom-Json
} catch {
  throw "WorkerFinalJson must be valid JSON: $($_.Exception.Message)"
}
if ($null -eq $payload) {
  throw "WorkerFinalJson must decode to an object"
}
$required = @('assignment_id','status','summary','artifacts','verification','blockers','next_recommended_action')
$missing = @($required | Where-Object { -not $payload.PSObject.Properties.Name.Contains($_) })
if ($missing.Count -gt 0) {
  throw "Missing worker-final fields: $($missing -join ', ')"
}
$payload | ConvertTo-Json -Depth 8
