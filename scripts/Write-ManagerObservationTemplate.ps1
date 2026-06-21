[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ThreadId,
  [Parameter(Mandatory=$true)][string]$StatusGuess,
  [Parameter(Mandatory=$true)][string]$ActiveGoal,
  [Parameter(Mandatory=$true)][string]$LatestProgress,
  [string[]]$Blockers = @(),
  [Parameter(Mandatory=$true)][string]$RecommendedFollowup
)

[pscustomobject]@{
  thread_id = $ThreadId
  observed_at = [DateTime]::UtcNow.ToString("o")
  status_guess = $StatusGuess
  active_goal = $ActiveGoal
  latest_progress = $LatestProgress
  blockers = $Blockers
  recommended_followup = $RecommendedFollowup
} | ConvertTo-Json -Depth 4
