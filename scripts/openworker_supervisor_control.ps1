param(
 [Parameter(Mandatory=$true)][string]$Operation,
 [Parameter(Mandatory=$true)][string]$SupervisorId,
 [string]$SessionId='',
 [string]$Model='',
 [string]$CurrentGoal='',
 [string]$DecisionJson='',
 [string]$BaseUrl='http://127.0.0.1:8787'
)
$ErrorActionPreference='Stop'
$base=$BaseUrl.TrimEnd('/')
function Post-Json([string]$Path,[object]$Body){$json=$Body|ConvertTo-Json -Depth 20 -Compress;return Invoke-RestMethod -Method Post "$base$Path" -ContentType 'application/json' -Body $json}
switch($Operation){
 'session' {if([string]::IsNullOrWhiteSpace($SessionId)){throw 'session_id required'};$r=Post-Json '/v1/supervisor/session' ([ordered]@{supervisor_id=$SupervisorId;session_id=$SessionId;model=$Model;current_goal=$CurrentGoal})}
 'heartbeat' {if([string]::IsNullOrWhiteSpace($SessionId)){throw 'session_id required'};$r=Post-Json '/v1/supervisor/heartbeat' ([ordered]@{supervisor_id=$SupervisorId;session_id=$SessionId;current_goal=$CurrentGoal})}
 'snapshot' {$id=[uri]::EscapeDataString($SupervisorId);$r=Invoke-RestMethod "$base/v1/supervisor/snapshot?supervisor_id=$id"}
 'jobs' {$id=[uri]::EscapeDataString($SupervisorId);$r=Invoke-RestMethod "$base/v1/supervisor/jobs?supervisor_id=$id"}
 'attention' {$id=[uri]::EscapeDataString($SupervisorId);$r=Invoke-RestMethod "$base/v1/supervisor/attention?supervisor_id=$id"}
 'recover' {$r=Post-Json '/v1/supervisor/recover' ([ordered]@{supervisor_id=$SupervisorId;session_id=$SessionId})}
 'decision' {if([string]::IsNullOrWhiteSpace($DecisionJson)){throw 'decision_json required'};$r=Invoke-RestMethod -Method Post "$base/v1/supervisor/decision" -ContentType 'application/json' -Body $DecisionJson}
 'decisions' {$id=[uri]::EscapeDataString($SupervisorId);$r=Invoke-RestMethod "$base/v1/supervisor/decisions?supervisor_id=$id&limit=100"}
 default {throw "unknown operation=$Operation"}
}
$r|ConvertTo-Json -Depth 30
