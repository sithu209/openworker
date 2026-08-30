param(
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0004-DWG-TO-3D',
  [string]$Machine = 'DESKTOP-O87PJNR',
  [string]$OpenWorkerUrl = 'http://127.0.0.1:8787',
  [string]$GoToolUrl = 'http://127.0.0.1:8848',
  [string]$OverviewRelativePath = 'dwg\exports\default\visual-search\case0004-overview.png',
  [string]$ExpectedSha256 = '5cee03340cbbcad51e412b46b85bda9dcaac22b193586b953bbfd5134039103e',
  [string]$ReceiptRelativePath = 'receipts\case0004-overview-drive-handoff.json'
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

if($env:COMPUTERNAME.Trim() -ine $Machine.Trim()){
  throw "CASE0004_WRONG_HOST expected=$Machine actual=$env:COMPUTERNAME"
}
if(-not(Test-Path -LiteralPath $WorkspaceRoot -PathType Container)){
  throw "CASE0004_WORKSPACE_MISSING path=$WorkspaceRoot"
}

$OpenWorkerRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$publisher=Join-Path $OpenWorkerRoot 'scripts\case0004_publish_overview_drive.ps1'
if(-not(Test-Path -LiteralPath $publisher -PathType Leaf)){
  throw "CASE0004_DRIVE_PUBLISHER_MISSING path=$publisher"
}

$overview=Join-Path $WorkspaceRoot $OverviewRelativePath
if(-not(Test-Path -LiteralPath $overview -PathType Leaf)){
  throw "CASE0004_OVERVIEW_MISSING path=$overview"
}
$sha=(Get-FileHash -LiteralPath $overview -Algorithm SHA256).Hash.ToLowerInvariant()
if($sha -ne $ExpectedSha256.ToLowerInvariant()){
  throw "CASE0004_OVERVIEW_SHA_MISMATCH expected=$ExpectedSha256 actual=$sha"
}

$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status" -TimeoutSec 10
$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents" -TimeoutSec 10

$capability='drive.file.upload'
$query=[ordered]@{
  session_id="case0004-drive-$([guid]::NewGuid().ToString('N'))"
  project='DWG_todo Case 0004'
  workspace_root=$WorkspaceRoot
  question='Case 0004 must publish the existing REAL overview PNG to Google Drive through the canonical local OpenWorker transport. Confirm drive.file.upload / drive.review.publish guidance, credential requirements, receipt requirements, and negative knowledge. GitHub Actions and Drive Desktop sync are not the canonical business transport.'
  task='Publish Case 0004 REAL overview through OpenWorker local durable job.'
}
$goReply=Invoke-RestMethod -Method Post -Uri "$GoToolUrl/agent/query" -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 12 -Compress) -TimeoutSec 60
$replyText=$goReply|ConvertTo-Json -Depth 40 -Compress
if($replyText -notmatch 'drive\.(file\.upload|review\.publish)'){
  throw 'CASE0004_GOTOOL_DRIVE_CAPABILITY_NOT_CONFIRMED'
}

$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$jobId="case0004-drive-overview-$stamp"
$dispatchId="case0004-local-drive-0004-045-$stamp"

function Quote-PS([string]$s){return "'" + $s.Replace("'","''") + "'"}
$command = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "' +
  '& ' + (Quote-PS $publisher) +
  ' -WorkspaceRoot ' + (Quote-PS $WorkspaceRoot) +
  ' -OverviewRelativePath ' + (Quote-PS $OverviewRelativePath) +
  ' -ExpectedSha256 ' + (Quote-PS $ExpectedSha256) +
  ' -Machine ' + (Quote-PS $Machine) +
  ' -ReceiptRelativePath ' + (Quote-PS $ReceiptRelativePath) +
  '; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}"'

$job=[ordered]@{
  job_id=$jobId
  dispatch_id=$dispatchId
  machine=$Machine
  priority=100
  cwd=$OpenWorkerRoot
  workspace_root=$WorkspaceRoot
  timeout_sec=600
  command=$command
  locks=@('transport:google-drive','workspace:case0004-review-handoff')
}
$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 20 -Compress) -TimeoutSec 30

$evidenceDir=Join-Path $WorkspaceRoot '.openworker\evidence'
New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null
$receipt=[ordered]@{
  schema='openworker/case0004-local-drive-submit/v1'
  case_id='0004'
  next_business_step='0004-045'
  machine=$Machine
  workspace_root=$WorkspaceRoot
  source_path=$overview
  source_sha256=$sha
  capability=$capability
  node=$node
  agents=$agents
  go_tool_reply=$goReply
  durable_ack=$ack
  submitted_at=[DateTimeOffset]::UtcNow.ToString('o')
}
$receiptPath=Join-Path $evidenceDir 'latest-drive-local-submit.json'
[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 60),(New-Object Text.UTF8Encoding($false)))
Write-Output ($receipt|ConvertTo-Json -Depth 60)
Write-Host "CASE0004_LOCAL_DRIVE_DURABLE_ACK job_id=$jobId receipt=$receiptPath"
