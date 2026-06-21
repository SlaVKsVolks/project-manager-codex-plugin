[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ThreadId,
  [Parameter(Mandatory=$true)][string]$AssignmentId,
  [Parameter(Mandatory=$true)][string]$ObservedBlocker,
  [Parameter(Mandatory=$true)][string]$RequestedAction
)

@"
$ThreadId recovery

assignment_id: $AssignmentId
observed_blocker: $ObservedBlocker
requested_action: $RequestedAction

Use the project-manager plugin/skill. Stay within the current assignment scope. If blocked, return a strict worker final with concrete blocker evidence.
If the lane is unreadable or dead, the manager should replace it with manager_replace_dead_lane instead of assuming it is still healthy.
"@
