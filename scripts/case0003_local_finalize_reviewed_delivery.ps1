param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$OpenWorkerRoot=$env:OPENWORKER_ROOT,
  [string]$RevisionId=''
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
if([string]::IsNullOrWhiteSpace($OpenWorkerRoot)){throw 'OPENWORKER_ROOT/OpenWorkerRoot is required'}
foreach($rel in @('scripts\case0003_finalize_reviewed_delivery.py','scripts\case0003_finalize_compat_alias.py')){if(-not(Test-Path -LiteralPath (Join-Path $OpenWorkerRoot $rel) -PathType Leaf)){throw "required reviewed-delivery script missing: $rel"}}
$latest=Join-Path $WorkspaceRoot 'acceptance\openworker-final\connector-review-apply.json'
if([string]::IsNullOrWhiteSpace($RevisionId)){
  if(-not(Test-Path -LiteralPath $latest -PathType Leaf)){throw 'connector review apply result missing'}
  $review=Get-Content -LiteralPath $latest -Raw|ConvertFrom-Json
  if([string]$review.schema_version -ne 'openworker-case0003-connector-review-apply/v3'){throw 'connector review apply schema mismatch'}
  if([string]$review.status -ne 'ACCEPTED_PENDING_FINALIZE' -or [string]$review.verdict -ne 'PASS'){throw 'connector review is not PASS/ACCEPTED_PENDING_FINALIZE'}
  $RevisionId=[string]$review.revision_id
}
if([string]::IsNullOrWhiteSpace($RevisionId)){throw 'RevisionId is required'}
$reviewPath=Join-Path $WorkspaceRoot ("acceptance\openworker-final\connector-review-apply-$RevisionId.json")
if(-not(Test-Path -LiteralPath $reviewPath -PathType Leaf)){throw "connector review apply result missing for revision: $RevisionId"}
$jobs=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/jobs?limit=1000"
$active=@('accepted','queued_local','starting','running')
foreach($j in @($jobs.jobs)){if(([string]$j.job_id).StartsWith("case0003-review-finalize-$RevisionId-",[StringComparison]::OrdinalIgnoreCase) -and $active -contains [string]$j.status){[ordered]@{schema='openworker/case0003-reviewed-delivery-finalize-submit/v3';case_id='0003';revision_id=$RevisionId;submitted=$false;suppressed_duplicate=$true;active_job_id=$j.job_id;active_status=$j.status}|ConvertTo-Json -Depth 6|Write-Host;exit 0}}
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-review-finalize-$RevisionId-$stamp"
$escapedRoot=$OpenWorkerRoot.Replace("'","''");$escapedWorkspace=$WorkspaceRoot.Replace("'","''");$escapedRevision=$RevisionId.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '$escapedRoot'; python scripts/case0003_finalize_reviewed_delivery.py --workspace '$escapedWorkspace' --revision-id '$escapedRevision'; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}; python scripts/case0003_finalize_compat_alias.py --workspace '$escapedWorkspace' --revision-id '$escapedRevision'; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{job_id=$workId;dispatch_id="case0003-reviewed-delivery-finalize-$stamp";machine=$Machine;priority=68;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=300;command=$cmd;locks=@('case0003-reviewed-delivery-finalize')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$out=[ordered]@{schema='openworker/case0003-reviewed-delivery-finalize-submit/v3';case_id='0003';revision_id=$RevisionId;machine=$Machine;workspace_root=$WorkspaceRoot;transport='openworker-local-job';github_business_transport=$false;submitted=$true;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null;$out|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-reviewed-delivery-finalize-submit.json') -Encoding utf8;$out|ConvertTo-Json -Depth 12|Write-Host
