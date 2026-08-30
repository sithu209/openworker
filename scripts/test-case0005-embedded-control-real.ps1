param(
  [string]$CaseId='0005',
  [string]$Machine='DESKTOP-ODAQN0D',
  [string]$RunTag='manual'
)

$ErrorActionPreference='Stop'
if([Environment]::MachineName -ine $Machine){throw "wrong host $([Environment]::MachineName), expected $Machine"}

$hook='C:\ProgramData\OpenWorker\hooks\openworker-job-started-hook.ps1'
if(-not(Test-Path -LiteralPath $hook -PathType Leaf)){throw "installed Hook missing: $hook"}

$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddHHmmss')
$prefix="case0005-real-$RunTag-$stamp"
$results=New-Object System.Collections.Generic.List[object]

function Invoke-Control {
  param(
    [string]$RequestId,
    [string]$Command,
    [string]$Case=''
  )
  $envelope=[ordered]@{
    schema='openworker.control-envelope.v1'
    request_id=$RequestId
    command=$Command
    machine=$Machine
    case_id=if([string]::IsNullOrWhiteSpace($Case)){$null}else{$Case}
    policy=[ordered]@{max_parallel=4;join='case-defined';fail_closed=$true}
  }
  $env:OPENWORKER_CONTROL=$envelope|ConvertTo-Json -Compress -Depth 10
  $started=[DateTimeOffset]::UtcNow
  & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $hook
  $exitCode=$LASTEXITCODE
  Remove-Item Env:OPENWORKER_CONTROL -ErrorAction SilentlyContinue
  $receiptPath=Join-Path $env:ProgramData ('OpenWorker\hooks\receipts\'+$RequestId+'.json')
  if(-not(Test-Path -LiteralPath $receiptPath -PathType Leaf)){throw "hook receipt missing: $receiptPath"}
  $receipt=(Get-Content -LiteralPath $receiptPath -Raw)|ConvertFrom-Json -ErrorAction Stop
  $row=[ordered]@{
    request_id=$RequestId;command=$Command;exit_code=$exitCode;accepted=[bool]$receipt.accepted
    elapsed_ms=[int](([DateTimeOffset]::UtcNow-$started).TotalMilliseconds)
    receipt_path=$receiptPath;receipt=$receipt
  }
  $script:results.Add([pscustomobject]$row)
  if($exitCode-ne0 -or -not ([bool]$receipt.accepted)){
    throw "control failed command=$Command request_id=$RequestId exit=$exitCode class=$($receipt.error_class)"
  }
  return $receipt
}

function Get-DispatcherResult($HookReceipt){
  if($null-eq$HookReceipt.dispatcher_result){return $null}
  return $HookReceipt.dispatcher_result
}

# Phase A: read-only baseline.
$super0=Invoke-Control -RequestId ($prefix+'-supervisor-before') -Command 'SUPERVISOR.STATUS'
$status0=Invoke-Control -RequestId ($prefix+'-case-before') -Command 'CASE.STATUS' -Case $CaseId

# Phase B: queue clear must be repeat-safe.
$clear1=Invoke-Control -RequestId ($prefix+'-clear-1') -Command 'QUEUE.CLEAR'
$clear2=Invoke-Control -RequestId ($prefix+'-clear-2') -Command 'QUEUE.CLEAR'
$super1=Invoke-Control -RequestId ($prefix+'-supervisor-clean') -Command 'SUPERVISOR.STATUS'
$status1=Invoke-Control -RequestId ($prefix+'-case-clean') -Command 'CASE.STATUS' -Case $CaseId

# Phase C: exactly one real continue, then replay identical request_id.
$continueId=$prefix+'-continue-once'
$continue1=Invoke-Control -RequestId $continueId -Command 'CASE.CONTINUE_BATCH' -Case $CaseId
$dispatcherReceipt=Join-Path $env:ProgramData ('OpenWorker\control-envelope\receipts\'+$continueId+'.json')
if(-not(Test-Path -LiteralPath $dispatcherReceipt -PathType Leaf)){throw "dispatcher receipt missing after continue: $dispatcherReceipt"}
$beforeBytes=[IO.File]::ReadAllBytes($dispatcherReceipt)
$continue2=Invoke-Control -RequestId $continueId -Command 'CASE.CONTINUE_BATCH' -Case $CaseId
$afterBytes=[IO.File]::ReadAllBytes($dispatcherReceipt)
if($beforeBytes.Length-ne$afterBytes.Length){throw 'idempotent dispatcher receipt changed length on replay'}
for($i=0;$i-lt$beforeBytes.Length;$i++){if($beforeBytes[$i]-ne$afterBytes[$i]){throw 'idempotent dispatcher receipt changed bytes on replay'}}

# Phase D: read-back only. Do not continue again even if work is active.
$status2=Invoke-Control -RequestId ($prefix+'-case-after') -Command 'CASE.STATUS' -Case $CaseId
$super2=Invoke-Control -RequestId ($prefix+'-supervisor-after') -Command 'SUPERVISOR.STATUS'

$summary=[ordered]@{
  schema='openworker.case0005-embedded-control-real.v1'
  case_id=$CaseId
  machine=$Machine
  run_tag=$RunTag
  request_prefix=$prefix
  accepted=$true
  total_calls=$results.Count
  successful_calls=@($results|Where-Object{$_.accepted -and $_.exit_code-eq0}).Count
  continue_request_id=$continueId
  continue_receipt_byte_stable=$true
  phases=[ordered]@{
    baseline=[ordered]@{supervisor=$super0;case_status=$status0}
    queue_clear=[ordered]@{first=$clear1;second=$clear2;supervisor_after=$super1;case_status_after=$status1}
    continue_once=[ordered]@{first=$continue1;replay=$continue2}
    readback=[ordered]@{case_status=$status2;supervisor=$super2}
  }
  calls=$results
  completed_at=[DateTimeOffset]::UtcNow.ToString('o')
}

$outRoot=Join-Path $env:ProgramData 'OpenWorker\case0005\embedded-control-tests'
New-Item -ItemType Directory -Force -Path $outRoot|Out-Null
$outPath=Join-Path $outRoot ($prefix+'.json')
$tmp=$outPath+'.tmp.'+[Guid]::NewGuid().ToString('N')
[IO.File]::WriteAllText($tmp,($summary|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $tmp -Destination $outPath -Force
$summary|ConvertTo-Json -Depth 80
