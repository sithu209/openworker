param(
  [string]$OpenWorkerUrl = 'http://127.0.0.1:8787',
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0005-SNOW-WHITE',
  [string]$Machine = 'DESKTOP-ODAQN0D',
  [string]$ResidentRoot = 'D:\AI-Work\runtime\openworker'
)
$ErrorActionPreference='Stop'
$stage='start'
$started=[DateTimeOffset]::UtcNow.ToString('o')
$outcomePath='C:\ProgramData\OpenWorker\node\case0005-last-bootstrap-outcome.json'
$checks=[ordered]@{}

function Save-Outcome([bool]$Succeeded,[string]$Reason,$Ack=$null){
  New-Item -ItemType Directory -Force -Path (Split-Path $outcomePath) | Out-Null
  $o=[ordered]@{
    schema='openworker/case0005-bootstrap-script-outcome/v6'
    case_id='0005'
    machine=$env:COMPUTERNAME
    workspace_root=$WorkspaceRoot
    resident_root=$ResidentRoot
    succeeded=$Succeeded
    stage=$stage
    reason=$Reason
    ack=$Ack
    checks=$checks
    controller='go-native'
    python_required=$false
    started_at=$started
    observed_at=[DateTimeOffset]::UtcNow.ToString('o')
    next_action=if($Succeeded){'continue Case 0005 through OpenWorker /v1/cases/continue'}else{'repair reported Go-native bootstrap stage and retry'}
  }
  $o | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $outcomePath -Encoding utf8
  $o | ConvertTo-Json -Depth 30
}

try {
  $stage='verify_machine'
  $checks.expected_machine=$Machine
  $checks.actual_machine=$env:COMPUTERNAME
  if($env:COMPUTERNAME -ine $Machine){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}

  $stage='query_node_status'
  $node=Invoke-RestMethod "$OpenWorkerUrl/v1/node/status" -TimeoutSec 10
  $checks.node_online=[bool]$node.online
  $checks.node_machine=[string]$node.machine
  $checks.node_max_workers=[int]$node.max_workers
  $checks.node_running_commit=[string]$node.service.running_commit
  if(-not $node.online){throw 'resident OpenWorker offline'}
  if($node.machine -ine $Machine){throw "resident node mismatch $($node.machine)"}
  if([int]$node.max_workers -lt 4){throw "resident node max_workers=$($node.max_workers), expected >=4"}

  $stage='sync_case_contracts'
  $source=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
  New-Item -ItemType Directory -Force -Path $ResidentRoot | Out-Null
  foreach($name in @('case-worklists','case-specs')){
    $src=Join-Path $source $name
    $dst=Join-Path $ResidentRoot $name
    if(-not(Test-Path -LiteralPath $src -PathType Container)){throw "missing runtime source $src"}
    if(Test-Path -LiteralPath $dst){Remove-Item -LiteralPath $dst -Recurse -Force}
    Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
  }
  $checks.manifest_exists=Test-Path -LiteralPath (Join-Path $ResidentRoot 'case-worklists\0005.json') -PathType Leaf
  $checks.spec_exists=Test-Path -LiteralPath (Join-Path $ResidentRoot 'case-specs\0005.json') -PathType Leaf
  if(-not $checks.manifest_exists -or -not $checks.spec_exists){throw 'Case 0005 contract sync incomplete'}

  $stage='post_go_native_bootstrap'
  $body=@{
    case_id='0005'
    machine=$Machine
    workspace_root=$WorkspaceRoot
    openworker_root=$ResidentRoot
    manifest_path='case-worklists\0005.json'
    spec_path='case-specs\0005.json'
    env=@{
      GTR_WORK_QUEUE_URL='http://127.0.0.1:8848'
      GTR_LOCAL_WORKERS='4'
      OPENWORKER_ROOT=$ResidentRoot
    }
  } | ConvertTo-Json -Depth 10
  $ack=Invoke-RestMethod -Method Post "$OpenWorkerUrl/v1/cases/bootstrap" -ContentType 'application/json' -Body $body -TimeoutSec 20

  $stage='verify_go_native_ack'
  if(-not $ack.ok){throw "Go-native bootstrap failed: $($ack|ConvertTo-Json -Compress -Depth 20)"}
  if($ack.controller -ne 'go-native'){throw "unexpected controller=$($ack.controller)"}
  if($ack.python_required){throw 'Go-native bootstrap unexpectedly requires Python'}
  if($ack.stage -ne 'go_native_bootstrap_completed'){throw "unexpected stage=$($ack.stage)"}
  if(-not(Test-Path -LiteralPath $WorkspaceRoot -PathType Container)){throw "workspace not materialized: $WorkspaceRoot"}
  $checks.workspace_exists=$true
  $checks.dot_openworker_exists=Test-Path -LiteralPath (Join-Path $WorkspaceRoot '.openworker') -PathType Container

  $stage='write_workspace_receipt'
  $evidence=Join-Path $WorkspaceRoot 'evidence'
  New-Item -ItemType Directory -Force -Path $evidence | Out-Null
  $receipt=[ordered]@{
    schema='openworker/case0005-resident-bootstrap/v6'
    case_id='0005'
    machine=$Machine
    workspace_root=$WorkspaceRoot
    resident_root=$ResidentRoot
    controller='go-native'
    python_required=$false
    transport='go-tool-local-queue'
    target_queue_url='http://127.0.0.1:8848'
    business_execution='resident-openworker-local-supervisor'
    github_action_used_for_business_execution=$false
    node=$node
    ack=$ack
    submitted_at=[DateTimeOffset]::UtcNow.ToString('o')
  }
  $receipt | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidence 'case0005-resident-bootstrap.json') -Encoding utf8
  $stage='completed'
  Save-Outcome $true '' $ack
  exit 0
} catch {
  Save-Outcome $false $_.Exception.Message $null
  exit 1
}
