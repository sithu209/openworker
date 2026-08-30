param(
  [string]$CaseId='0005',
  [string]$Machine='DESKTOP-ODAQN0D',
  [string]$RunTag='readback'
)

$ErrorActionPreference='Stop'
if([Environment]::MachineName -ine $Machine){throw "wrong host $([Environment]::MachineName), expected $Machine"}

$hook='C:\ProgramData\OpenWorker\hooks\openworker-job-started-hook.ps1'
if(-not(Test-Path -LiteralPath $hook -PathType Leaf)){throw "installed Hook missing: $hook"}

function Invoke-ReadOnlyControl {
  param([string]$RequestId,[string]$Command,[string]$Case='')
  if($Command -notin @('CASE.STATUS','SUPERVISOR.STATUS')){throw "readback refuses side-effect command: $Command"}
  $envelope=[ordered]@{
    schema='openworker.control-envelope.v1'
    request_id=$RequestId
    command=$Command
    machine=$Machine
    case_id=if([string]::IsNullOrWhiteSpace($Case)){$null}else{$Case}
    policy=[ordered]@{max_parallel=4;join='case-defined';fail_closed=$true}
  }
  $env:OPENWORKER_CONTROL=$envelope|ConvertTo-Json -Compress -Depth 10
  try{
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $hook
    $code=$LASTEXITCODE
  }finally{
    Remove-Item Env:OPENWORKER_CONTROL -ErrorAction SilentlyContinue
  }
  $receiptPath=Join-Path $env:ProgramData ('OpenWorker\hooks\receipts\'+$RequestId+'.json')
  if(-not(Test-Path -LiteralPath $receiptPath -PathType Leaf)){throw "hook receipt missing: $receiptPath"}
  $receipt=(Get-Content -LiteralPath $receiptPath -Raw)|ConvertFrom-Json -ErrorAction Stop
  if($code-ne0 -or -not ([bool]$receipt.accepted)){throw "read-only control failed command=$Command exit=$code class=$($receipt.error_class)"}
  return $receipt
}

$evidenceRoot=Join-Path $env:ProgramData 'OpenWorker\case0005\embedded-control-tests'
$latestEvidence=$null
$latestEvidencePath=$null
if(Test-Path -LiteralPath $evidenceRoot -PathType Container){
  $file=Get-ChildItem -LiteralPath $evidenceRoot -Filter '*.json' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if($null-ne$file){
    $latestEvidencePath=$file.FullName
    $latestEvidence=(Get-Content -LiteralPath $file.FullName -Raw)|ConvertFrom-Json -ErrorAction Stop
  }
}

$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddHHmmssfff')
$caseReceipt=Invoke-ReadOnlyControl -RequestId ("case0005-readback-$RunTag-$stamp-case") -Command 'CASE.STATUS' -Case $CaseId
$superReceipt=Invoke-ReadOnlyControl -RequestId ("case0005-readback-$RunTag-$stamp-super") -Command 'SUPERVISOR.STATUS'

$summary=[ordered]@{
  schema='openworker.case0005-embedded-control-readback.v1'
  machine=$Machine
  case_id=$CaseId
  latest_real_evidence_path=$latestEvidencePath
  latest_real_evidence=$latestEvidence
  current_case_status=$caseReceipt.dispatcher_result.result
  current_supervisor_status=$superReceipt.dispatcher_result.result
  readback_receipts=[ordered]@{case=$caseReceipt;supervisor=$superReceipt}
  observed_at=[DateTimeOffset]::UtcNow.ToString('o')
}
$summary|ConvertTo-Json -Depth 100
