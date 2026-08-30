param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$GoToolRoot=$env:GO_TOOL_ROOT,
  [string]$EngineeringOSRoot=$env:ENGINEERING_OS_ROOT,
  [string]$OSJobId=$env:ENGINEERING_OS_JOB_ID,
  [string]$EngineeringOSBaseUrl='http://127.0.0.1:8080'
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
foreach($pair in @(@('GO_TOOL_ROOT',$GoToolRoot),@('ENGINEERING_OS_ROOT',$EngineeringOSRoot),@('ENGINEERING_OS_JOB_ID',$OSJobId))){if([string]::IsNullOrWhiteSpace([string]$pair[1])){throw "$($pair[0]) is required"}}
if(-not(Test-Path -LiteralPath (Join-Path $GoToolRoot 'go.mod'))){throw "invalid go-tool root: $GoToolRoot"}
if(-not(Test-Path -LiteralPath (Join-Path $EngineeringOSRoot 'go.mod'))){throw "invalid Engineering OS root: $EngineeringOSRoot"}
$renderPath=Join-Path $WorkspaceRoot 'acceptance\render\render-acceptance.json';if(-not(Test-Path -LiteralPath $renderPath -PathType Leaf)){throw 'current render acceptance required before OS delivery'}
$render=Get-Content -LiteralPath $renderPath -Raw|ConvertFrom-Json
$ingestPath=Join-Path $WorkspaceRoot 'evidence\case0003-os-artifact-ingest-receipt.json';if(-not(Test-Path -LiteralPath $ingestPath -PathType Leaf)){throw 'current OS artifact ingest receipt required before delivery'}
$ingest=Get-Content -LiteralPath $ingestPath -Raw|ConvertFrom-Json
if([string]$ingest.schema_version -ne 'engineering-os-artifact-ingest-receipt/v1' -or [string]$ingest.semantic_contract_version -ne 'engineering-os-artifact-ingest-receipt/v2'){throw 'OS artifact ingest compatibility view is not backed by v2 source binding'}
$b=$ingest.source_binding;if($null -eq $b){throw 'OS artifact ingest source_binding missing'}
if([string]$b.render_fingerprint -ne [string]$render.fingerprint -or [string]$b.blender_fingerprint -ne [string]$render.blender_fingerprint -or [string]$b.scenex_fingerprint -ne [string]$render.scenex_fingerprint){throw 'OS artifact ingest is stale relative to current render acceptance'}
$base=$EngineeringOSBaseUrl.TrimEnd('/')
$health=Invoke-RestMethod -Method Get -Uri "$base/healthz" -TimeoutSec 5;if([string]$health.status -ne 'ok'){throw 'Engineering OS is not healthy'}
$approval=Invoke-RestMethod -Method Get -Uri "$base/api/v1/jobs/$OSJobId/approval-status" -TimeoutSec 10
if(-not $approval.approved){throw "OS approval gate is not satisfied; approved_count=$($approval.approved_count) total=$($approval.total)"}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';$claimDir=Join-Path $WorkspaceRoot '.openworker\localexec';New-Item -ItemType Directory -Force -Path $evidenceDir,$claimDir|Out-Null
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-os-delivery-$stamp";$claimPath=Join-Path $claimDir ($workId+'.json');$resultPath=Join-Path $evidenceDir ($workId+'-localexec-result.json')
$claim=[ordered]@{work_id=$workId;assigned_host=$Machine;capability_id='engineering_os.delivery.publish';inputs=[ordered]@{assigned_host=$Machine;job_id=$OSJobId;base_url=$EngineeringOSBaseUrl;publisher='openworker-local-supervisor';note=('Case 0003 玉井橋 render='+[string]$render.fingerprint)};claimed_by='openworker-local-supervisor';lease_token=$workId}
$claim|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $claimPath -Encoding utf8
$escapedGo=$GoToolRoot.Replace("'","''");$escapedOS=$EngineeringOSRoot.Replace("'","''");$escapedClaim=$claimPath.Replace("'","''");$escapedResult=$resultPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"`$env:ENGINEERING_OS_ROOT='$escapedOS'; Set-Location -LiteralPath '$escapedGo'; go run ./cmd/gtr-local-exec --claim '$escapedClaim' --timeout 5m | Set-Content -LiteralPath '$escapedResult' -Encoding utf8; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{job_id=$workId;dispatch_id="case0003-os-delivery-local-$stamp";machine=$Machine;priority=70;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=360;command=$cmd;locks=@('case0003-engineering-os-delivery')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$receipt=[ordered]@{schema='openworker/case0003-os-delivery-submit/v2';case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;os_job_id=$OSJobId;render_fingerprint=[string]$render.fingerprint;approval_total=[int]$approval.total;approval_count=[int]$approval.approved_count;transport='openworker-local-jobs+go-tool-localexec';github_business_transport=$false;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$receiptPath=Join-Path $evidenceDir 'case0003-os-delivery-submit.json';$receipt|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $receiptPath -Encoding utf8
$receipt|ConvertTo-Json -Depth 12|Write-Host
