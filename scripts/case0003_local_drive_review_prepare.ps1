param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$OpenWorkerRoot=$env:OPENWORKER_ROOT,
  [string]$DriveSyncRoot=$env:OPENWORKER_REVIEW_DRIVE_ROOT
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
if([string]::IsNullOrWhiteSpace($OpenWorkerRoot)){throw 'OPENWORKER_ROOT/OpenWorkerRoot is required'}
foreach($rel in @('scripts\case0003_prepare_drive_review.py','scripts\case0003_seal_drive_review.py')){if(-not(Test-Path -LiteralPath (Join-Path $OpenWorkerRoot $rel) -PathType Leaf)){throw "required review script missing under OpenWorker root: $rel"}}
if([string]::IsNullOrWhiteSpace($DriveSyncRoot)){throw 'OPENWORKER_REVIEW_DRIVE_ROOT/DriveSyncRoot is required'}
if(-not(Test-Path -LiteralPath $DriveSyncRoot -PathType Container)){throw "Drive review sync root unavailable: $DriveSyncRoot"}
$jobs=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/jobs?limit=1000"
$active=@('accepted','queued_local','starting','running')
foreach($j in @($jobs.jobs)){if(([string]$j.job_id).StartsWith('case0003-drive-review-', [StringComparison]::OrdinalIgnoreCase) -and $active -contains [string]$j.status){[ordered]@{schema='openworker/case0003-drive-review-submit/v3';case_id='0003';submitted=$false;suppressed_duplicate=$true;active_job_id=$j.job_id;active_status=$j.status}|ConvertTo-Json -Depth 6|Write-Host;exit 0}}
$deliveryReceipt=Join-Path $WorkspaceRoot 'evidence\case0003-os-delivery-receipt.json'
if(-not(Test-Path -LiteralPath $deliveryReceipt -PathType Leaf)){throw 'OS Delivery receipt missing; Drive review cannot start'}
$receipt=Get-Content -LiteralPath $deliveryReceipt -Raw|ConvertFrom-Json
if(-not $receipt.ok){throw 'OS Delivery receipt is not accepted'}

$prepareLatest=Join-Path $WorkspaceRoot 'acceptance\openworker-final\drive-review-prepare.json'
$resumeSeal=$false
$resumeRevision=''
if(Test-Path -LiteralPath $prepareLatest -PathType Leaf){
  try{
    $prepared=Get-Content -LiteralPath $prepareLatest -Raw|ConvertFrom-Json
    $schema=[string]$prepared.schema_version
    if(($schema -eq 'openworker-case0003-drive-review-prepare/v1' -or $schema -eq 'openworker-case0003-drive-review-prepare/v2') -and [string]$prepared.status -eq 'WAITING_DRIVE_REVIEW'){
      $bundle=[string]$prepared.bundle_root;$driveTarget=[string]$prepared.drive_sync_target
      if((Test-Path -LiteralPath $bundle -PathType Container) -and (Test-Path -LiteralPath $driveTarget -PathType Container)){
        $resumeSeal=$true;$resumeRevision=[string]$prepared.revision_id
      }
    }
  }catch{}
}

$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-drive-review-$stamp"
$escapedRoot=$OpenWorkerRoot.Replace("'","''");$escapedWorkspace=$WorkspaceRoot.Replace("'","''");$escapedDrive=$DriveSyncRoot.Replace("'","''")
if($resumeSeal){
  $cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '$escapedRoot'; python scripts/case0003_seal_drive_review.py --workspace '$escapedWorkspace'; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
  $mode='resume_seal'
}else{
  $cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '$escapedRoot'; python scripts/case0003_prepare_drive_review.py --workspace '$escapedWorkspace' --drive-sync-root '$escapedDrive'; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}; python scripts/case0003_seal_drive_review.py --workspace '$escapedWorkspace'; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
  $mode='prepare_and_seal'
}
$job=@{job_id=$workId;dispatch_id="case0003-drive-review-local-$stamp";machine=$Machine;priority=70;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=900;command=$cmd;locks=@('case0003-drive-review-prepare')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$out=[ordered]@{schema='openworker/case0003-drive-review-submit/v3';case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;transport='openworker-local-job->google-drive-desktop-sync+immutable-zip';github_business_transport=$false;mode=$mode;resumed_revision_id=$resumeRevision;submitted=$true;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null;$out|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-drive-review-submit.json') -Encoding utf8;$out|ConvertTo-Json -Depth 12|Write-Host
