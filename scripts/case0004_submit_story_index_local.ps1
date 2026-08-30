param(
  [Parameter(Mandatory=$true)][ValidateSet('cad.build_story_index','cad.render_story_viewports')][string]$Method,
  [Parameter(Mandatory=$true)][string]$ParamsPath,
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0004-DWG-TO-3D',
  [string]$Machine = 'DESKTOP-O87PJNR',
  [string]$OpenWorkerUrl = 'http://127.0.0.1:8787',
  [string]$GoToolUrl = 'http://127.0.0.1:8848',
  [string]$DWGRepoRoot = ''
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

if($env:COMPUTERNAME.Trim() -ine $Machine.Trim()){
  throw "CASE0004_WRONG_HOST expected=$Machine actual=$env:COMPUTERNAME"
}
if(-not(Test-Path -LiteralPath $WorkspaceRoot -PathType Container)){throw "CASE0004_WORKSPACE_MISSING path=$WorkspaceRoot"}
if(-not(Test-Path -LiteralPath $ParamsPath -PathType Leaf)){throw "CASE0004_PARAMS_MISSING path=$ParamsPath"}
try{$null=(Get-Content -LiteralPath $ParamsPath -Raw -Encoding UTF8)|ConvertFrom-Json}catch{throw "CASE0004_PARAMS_INVALID error=$($_.Exception.Message)"}

$OpenWorkerRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$operatorRel='scripts\operator_dwg_story_index_local.ps1'

function Test-DWGRoot([string]$p){
  if([string]::IsNullOrWhiteSpace($p)){return $false}
  return (Test-Path -LiteralPath (Join-Path $p $operatorRel) -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $p 'cmd\dwg-editor') -PathType Container)
}

if(-not(Test-DWGRoot $DWGRepoRoot)){
  $candidates=New-Object System.Collections.Generic.List[string]
  if($env:OPENWORKER_DWG_TODO_ROOT){$candidates.Add($env:OPENWORKER_DWG_TODO_ROOT)}
  if($env:RUNNER_WORKSPACE){
    $candidates.Add((Join-Path $env:RUNNER_WORKSPACE 'DWG_todo'))
    $candidates.Add($env:RUNNER_WORKSPACE)
  }
  foreach($base in @('D:\actions-runner','D:\actions-runner-o87','D:\github-runner','C:\actions-runner','C:\github-runner')){
    $candidates.Add((Join-Path $base '_work\DWG_todo\DWG_todo'))
  }
  foreach($p in $candidates){if(Test-DWGRoot $p){$DWGRepoRoot=$p;break}}
}
if(-not(Test-DWGRoot $DWGRepoRoot)){
  throw 'CASE0004_DWG_REPO_NOT_FOUND set OPENWORKER_DWG_TODO_ROOT or pass -DWGRepoRoot pointing at the existing Action checkout; do not clone a second runtime copy.'
}
$DWGRepoRoot=(Resolve-Path $DWGRepoRoot).Path

$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status" -TimeoutSec 10
$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents" -TimeoutSec 10

$capability='dwg.story_index.execute.case-worklist'
$caseStep=if($Method -eq 'cad.build_story_index'){'0004-045'}else{'0004-047'}
$query=[ordered]@{
  session_id="case0004-local-$([guid]::NewGuid().ToString('N'))"
  project='DWG_todo Case 0004'
  workspace_root=$WorkspaceRoot
  question="Case 0004 canonical step $caseStep must execute $Method using the new local OpenWorker durable execution path. Return the registered business capability, required local execution guidance, resource/parallel constraints, and relevant negative knowledge. GitHub Actions is legacy transport only; do not require a workflow run when local OpenWorker is healthy."
  task="Execute Case 0004 $caseStep through OpenWorker local durable job."
}
$goReply=Invoke-RestMethod -Method Post -Uri "$GoToolUrl/agent/query" -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 12 -Compress) -TimeoutSec 60
$replyText=$goReply|ConvertTo-Json -Depth 40 -Compress
if($replyText -notmatch [regex]::Escape($capability)){
  throw "CASE0004_GOTOOL_CAPABILITY_NOT_CONFIRMED expected=$capability"
}

$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$jobId="case0004-story-index-$stamp"
$dispatchId="case0004-local-$caseStep-$stamp"
$operator=Join-Path $DWGRepoRoot $operatorRel

function Quote-PS([string]$s){return "'" + $s.Replace("'","''") + "'"}
$command = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "' +
  '& ' + (Quote-PS $operator) +
  ' -Method ' + (Quote-PS $Method) +
  ' -ParamsJson (Get-Content -LiteralPath ' + (Quote-PS $ParamsPath) + ' -Raw -Encoding UTF8)' +
  ' -WorkspaceRoot ' + (Quote-PS $WorkspaceRoot) +
  ' -AssignedHost ' + (Quote-PS $Machine) +
  ' -OpenWorkerRoot ' + (Quote-PS $OpenWorkerRoot) +
  ' -CaseStep ' + (Quote-PS $caseStep) +
  '; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}"'

$locks=@('tool:opencad','workspace:case0004-dwg-state')
if($Method -eq 'cad.render_story_viewports'){$locks=@('tool:opencad','workspace:case0004-dwg-state')}
$job=[ordered]@{
  job_id=$jobId
  dispatch_id=$dispatchId
  machine=$Machine
  priority=100
  cwd=$DWGRepoRoot
  workspace_root=$WorkspaceRoot
  timeout_sec=1200
  command=$command
  locks=$locks
}
$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 20 -Compress) -TimeoutSec 30

$evidenceDir=Join-Path $WorkspaceRoot '.openworker\evidence'
New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null
$receipt=[ordered]@{
  schema='openworker/case0004-local-story-index-submit/v1'
  case_id='0004'
  case_step=$caseStep
  method=$Method
  machine=$Machine
  workspace_root=$WorkspaceRoot
  dwg_repo_root=$DWGRepoRoot
  params_path=(Resolve-Path $ParamsPath).Path
  capability=$capability
  node=$node
  agents=$agents
  go_tool_reply=$goReply
  durable_ack=$ack
  submitted_at=[DateTimeOffset]::UtcNow.ToString('o')
}
$receiptPath=Join-Path $evidenceDir 'latest-story-index-local-submit.json'
[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 60),(New-Object Text.UTF8Encoding($false)))
Write-Output ($receipt|ConvertTo-Json -Depth 60)
Write-Host "CASE0004_LOCAL_DURABLE_ACK job_id=$jobId step=$caseStep receipt=$receiptPath"
