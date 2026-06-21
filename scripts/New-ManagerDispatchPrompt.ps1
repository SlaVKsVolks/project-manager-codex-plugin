[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AssignmentPath,
  [Parameter(Mandatory=$true)][string]$AssignmentId,
  [string]$TargetThreadId='',
  [string]$TargetLabel='worker',
  [Parameter(Mandatory=$true)][string]$Goal,
  [Parameter(Mandatory=$true)][string]$Constraints,
  [Parameter(Mandatory=$true)][string]$DefinitionOfDone
)

$target = if ($TargetThreadId) { $TargetThreadId } else { $TargetLabel }
@"
$target dispatch

assignment_id: $AssignmentId
assignment_path: $AssignmentPath
goal: $Goal
constraints: $Constraints
definition_of_done: $DefinitionOfDone

Use the project-manager plugin/skill. Keep ownership narrow. Report a strict worker final with artifacts, verification, blockers, and next action.
Managers should prefer manager_verified_dispatch for delivery verification and durable lane updates.
"@
