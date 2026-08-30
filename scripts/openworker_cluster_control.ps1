param(
 [Parameter(Mandatory=$true)][string]$Operation,
 [string]$JobId='',
 [string]$Machine='any',
 [string]$Mode='queued',
 [string]$Capabilities='',
 [string]$RequestJson='',
 [string]$BaseUrl='http://127.0.0.1:8787'
)
$ErrorActionPreference='Stop'
$base=$BaseUrl.TrimEnd('/')
switch($Operation){
 'status' {$r=Invoke-RestMethod "$base/v1/cluster/status"}
 'capabilities' {$r=Invoke-RestMethod "$base/v1/cluster/capabilities"}
 'jobs' {$r=Invoke-RestMethod "$base/v1/cluster/jobs?limit=200"}
 'agents' {$r=Invoke-RestMethod "$base/v1/cluster/agents"}
 'job.status' {if([string]::IsNullOrWhiteSpace($JobId)){throw 'job_id required'};$r=Invoke-RestMethod "$base/v1/cluster/jobs/$JobId"}
 'job.cancel' {if([string]::IsNullOrWhiteSpace($JobId)){throw 'job_id required'};$r=Invoke-RestMethod -Method Post "$base/v1/cluster/jobs/$JobId/cancel"}
 'job.retry' {if([string]::IsNullOrWhiteSpace($JobId)){throw 'job_id required'};$r=Invoke-RestMethod -Method Post "$base/v1/cluster/jobs/$JobId/retry"}
 'queue.drain' {$m=[uri]::EscapeDataString($Machine);$mode=[uri]::EscapeDataString($Mode);$r=Invoke-RestMethod -Method Post "$base/v1/cluster/queue/drain?machine=$m&mode=$mode"}
 'route' {$m=[uri]::EscapeDataString($Machine);$c=[uri]::EscapeDataString($Capabilities);$r=Invoke-RestMethod "$base/v1/cluster/route?machine=$m&capabilities=$c"}
 'submit' {if([string]::IsNullOrWhiteSpace($RequestJson)){throw 'request_json required'};$r=Invoke-RestMethod -Method Post "$base/v1/cluster/jobs" -ContentType 'application/json' -Body $RequestJson}
 'dispatches' {$r=Invoke-RestMethod "$base/v1/cluster/dispatches?limit=200"}
 'dispatch' {if([string]::IsNullOrWhiteSpace($JobId)){throw 'job_id required'};$r=Invoke-RestMethod "$base/v1/cluster/dispatches/$JobId"}
 'control.events' {$q='';if(-not[string]::IsNullOrWhiteSpace($JobId)){$q='?job_id='+[uri]::EscapeDataString($JobId)};$r=Invoke-RestMethod "$base/v1/cluster/control-events$q"}
 'endpoints' {$r=Invoke-RestMethod "$base/v1/cluster/endpoints"}
 'connectivity' {$r=Invoke-RestMethod "$base/v1/cluster/connectivity?limit=500"}
 default {throw "unknown operation=$Operation"}
}
$r|ConvertTo-Json -Depth 40
