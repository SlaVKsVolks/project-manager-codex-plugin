[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AssignmentPath,
  [Parameter(Mandatory=$true)][string]$AssignmentId,
  [Parameter(Mandatory=$true)][string]$Goal,
  [Parameter(Mandatory=$true)][string]$Constraints,
  [Parameter(Mandatory=$true)][string]$DefinitionOfDone,
  [ValidateSet('deepseek-v4-flash','deepseek-v4-pro','flash','pro')]
  [string]$WorkerModel='deepseek-v4-flash',
  [string]$ManagerModel='gpt-5.4',
  [string]$DirectoryName=''
)

$resolvedModel = switch ($WorkerModel) {
  'flash' { 'deepseek-v4-flash' }
  'pro' { 'deepseek-v4-pro' }
  default { $WorkerModel }
}
$thinking = if ($resolvedModel -eq 'deepseek-v4-pro') { 'high' } else { 'medium' }
$targetDirectory = if ($DirectoryName) { $DirectoryName } else { "pm-worker-$AssignmentId" }

$prompt = @"
PM worker $AssignmentId

You are a Codex worker thread managed by a GPT project-manager thread.
manager_model: $ManagerModel
worker_model: $resolvedModel
assignment_id: $AssignmentId
assignment_path: $AssignmentPath
goal: $Goal
constraints: $Constraints
definition_of_done: $DefinitionOfDone

Stay inside this assignment. Do not broaden scope. When finished or blocked, return a strict worker final JSON with assignment_id, status, summary, artifacts, verification, blockers, and next_recommended_action.
"@

[pscustomobject]@{
  model = $resolvedModel
  thinking = $thinking
  target = [pscustomobject]@{
    type = 'projectless'
    directoryName = $targetDirectory
  }
  prompt = $prompt
} | ConvertTo-Json -Depth 6
