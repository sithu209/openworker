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
$apply=Join-Path $OpenWorkerRoot 'scripts\case0003_apply_connector_review.py'
if(-not(Test-Path -LiteralPath $apply -PathType Leaf)){throw "connector review apply script missing: $apply"}
$acceptance=Join-Path $WorkspaceRoot 'acceptance\openworker-final'
$preparePath=Join-Path $acceptance 'drive-review-prepare.json'
if(-not(Test-Path -LiteralPath $preparePath -PathType Leaf)){throw 'Drive review prepare receipt missing'}
$prepare=Get-Content -LiteralPath $preparePath -Raw|ConvertFrom-Json
if([string]$prepare.schema_version -ne 'openworker-case0003-drive-review-prepare/v2'){throw 'Drive review prepare v2 required'}
if([string]::IsNullOrWhiteSpace($RevisionId)){$RevisionId=[string]$prepare.revision_id}
if([string]$prepare.revision_id -ne $RevisionId){throw 'Drive review prepare revision mismatch'}
$driveFolder=[string]$prepare.drive_sync_target
if([string]::IsNullOrWhiteSpace($driveFolder) -or -not(Test-Path -LiteralPath $driveFolder -PathType Container)){throw 'Drive-synced review revision folder unavailable'}
$receiptPath=Join-Path $driveFolder 'connector-review-receipt.json'
if(-not(Test-Path -LiteralPath $receiptPath -PathType Leaf) -or (Get-Item -LiteralPath $receiptPath).Length -le 0){throw "connector review receipt not synced yet: $receiptPath"}
$receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json
if([string]$receipt.transport -ne 'google-drive-connector'){throw 'connector review receipt transport mismatch'}
if([string]$receipt.revision_id -ne $RevisionId){throw 'connector review receipt revision mismatch'}
if([string]$receipt.bundle_manifest_sha256 -ne [string]$prepare.bundle_manifest_sha256){throw 'connector review receipt bundle manifest mismatch'}
$cloud=$receipt.cloud_publication
if($null -eq $cloud){throw 'connector review cloud_publication missing'}
foreach($key in @('drive_revision_folder_id','drive_zip_file_id','review_zip_sha256','bundle_manifest_sha256')){if([string]::IsNullOrWhiteSpace([string]$cloud.$key)){throw "connector review cloud_publication.$key missing"}}
if([string]$cloud.review_zip_sha256 -ne [string]$prepare.review_zip_sha256){throw 'connector reviewed ZIP SHA mismatch'}
if([string]$cloud.bundle_manifest_sha256 -ne [string]$prepare.bundle_manifest_sha256){throw 'connector cloud manifest SHA mismatch'}
$jobs=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/jobs?limit=1000"
$active=@('accepted','queued_local','starting','running')
foreach($j in @($jobs.jobs)){if(([string]$j.job_id).StartsWith("case0003-review-apply-$RevisionId-",[StringComparison]::OrdinalIgnoreCase) -and $active -contains [string]$j.status){[ordered]@{schema='openworker/case0003-drive-review-apply-submit/v1';case_id='0003';revision_id=$RevisionId;submitted=$false;suppressed_duplicate=$true;active_job_id=$j.job_id;active_status=$j.status}|ConvertTo-Json -Depth 6|Write-Host;exit 0}}
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-review-apply-$RevisionId-$stamp"
$escapedRoot=$OpenWorkerRoot.Replace("'","''");$escapedWorkspace=$WorkspaceRoot.Replace("'","''");$escapedRevision=$RevisionId.Replace("'","''");$escapedReceipt=$receiptPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '$escapedRoot'; python scripts/case0003_apply_connector_review.py --workspace '$escapedWorkspace' --revision-id '$escapedRevision' --receipt '$escapedReceipt'; `$code=`$LASTEXITCODE; if(`$code -ne 0 -and `$code -ne 4){exit `$code}`""
$job=@{job_id=$workId;dispatch_id="case0003-drive-review-apply-$stamp";machine=$Machine;priority=69;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=300;command=$cmd;locks=@('case0003-drive-review-apply')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$out=[ordered]@{schema='openworker/case0003-drive-review-apply-submit/v1';case_id='0003';revision_id=$RevisionId;machine=$Machine;workspace_root=$WorkspaceRoot;receipt_path=$receiptPath;transport='google-drive-desktop-sync->openworker-local-job';github_business_transport=$false;submitted=$true;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null;$out|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-drive-review-apply-submit.json') -Encoding utf8;$out|ConvertTo-Json -Depth 12|Write-Host
