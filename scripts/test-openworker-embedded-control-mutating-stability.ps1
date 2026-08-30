param(
  [string]$CaseId = '0005',
  [string]$ExpectedMachine = 'DESKTOP-ODAQN0D'
)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ine $ExpectedMachine){throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine"}
$hook=Join-Path $PSScriptRoot 'openworker-job-started-hook.ps1'
if(-not(Test-Path -LiteralPath $hook -PathType Leaf)){throw "hook missing: $hook"}
$receiptRoot=Join-Path $env:ProgramData 'OpenWorker\control-envelope\receipts'
$rounds=@()
function Invoke-Control([string]$Command,[string]$RequestId,[string]$Case){
  $envl=[ordered]@{schema='openworker.control-envelope.v1';request_id=$RequestId;command=$Command;machine=$ExpectedMachine;policy=[ordered]@{max_parallel=4;join='case-defined';fail_closed=$true}}
  if(-not[string]::IsNullOrWhiteSpace($Case)){$envl.case_id=$Case}
  $env:OPENWORKER_CONTROL=$envl|ConvertTo-Json -Depth 10 -Compress
  $started=[DateTimeOffset]::UtcNow
  $out=& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $hook 2>&1|Out-String
  $code=$LASTEXITCODE
  $elapsed=[int]([DateTimeOffset]::UtcNow-$started).TotalMilliseconds
  $receiptPath=Join-Path $receiptRoot ($RequestId+'.json')
  $receipt=$null
  if(Test-Path -LiteralPath $receiptPath -PathType Leaf){try{$receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json -ErrorAction Stop}catch{}}
  $item=[ordered]@{command=$Command;request_id=$RequestId;exit_code=$code;elapsed_ms=$elapsed;output=$out.Trim();receipt_path=$receiptPath;receipt=$receipt}
  $script:rounds+=[pscustomobject]$item
  if($code-ne0){throw "mutating stability round failed command=$Command request_id=$RequestId exit=$code output=$out"}
  if($null-eq$receipt){throw "missing/invalid durable receipt for $RequestId"}
  if(-not ([bool]$receipt.accepted)){throw "control not accepted request_id=$RequestId receipt=$($receipt|ConvertTo-Json -Depth 20 -Compress)"}
  return $receipt
}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
$baseline=Invoke-Control 'CASE.STATUS' ("hook-mut-$stamp-baseline") $CaseId
$super0=Invoke-Control 'SUPERVISOR.STATUS' ("hook-mut-$stamp-supervisor-before") ''
$clear1=Invoke-Control 'QUEUE.CLEAR' ("hook-mut-$stamp-clear-1") ''
$clear2=Invoke-Control 'QUEUE.CLEAR' ("hook-mut-$stamp-clear-2") ''
$postClear=Invoke-Control 'SUPERVISOR.STATUS' ("hook-mut-$stamp-supervisor-after-clear") ''
$continueId="hook-mut-$stamp-continue-idempotent"
$cont1=Invoke-Control 'CASE.CONTINUE_BATCH' $continueId $CaseId
$firstReceiptText=Get-Content -LiteralPath (Join-Path $receiptRoot ($continueId+'.json')) -Raw
Start-Sleep -Milliseconds 200
$cont2=Invoke-Control 'CASE.CONTINUE_BATCH' $continueId $CaseId
$secondReceiptText=Get-Content -LiteralPath (Join-Path $receiptRoot ($continueId+'.json')) -Raw
if($firstReceiptText -ne $secondReceiptText){throw 'idempotency receipt changed on duplicate CASE.CONTINUE_BATCH request_id'}
$status1=Invoke-Control 'CASE.STATUS' ("hook-mut-$stamp-post-1") $CaseId
$status2=Invoke-Control 'CASE.STATUS' ("hook-mut-$stamp-post-2") $CaseId
$super1=Invoke-Control 'SUPERVISOR.STATUS' ("hook-mut-$stamp-supervisor-after") ''
$summary=[ordered]@{
  schema='openworker.hook-mutating-stability-result.v1';machine=$ExpectedMachine;case_id=$CaseId
  total_rounds=$rounds.Count;successful_rounds=@($rounds|Where-Object{$_.exit_code-eq0}).Count
  queue_clear_rounds=2;continue_request_id=$continueId;continue_duplicate_receipt_identical=($firstReceiptText-eq$secondReceiptText)
  completed_at=[DateTimeOffset]::UtcNow.ToString('o');rounds=$rounds
}
$path=Join-Path $env:ProgramData 'OpenWorker\hooks\mutating-stability-latest.json'
New-Item -ItemType Directory -Force -Path (Split-Path $path)|Out-Null
[IO.File]::WriteAllText($path,($summary|ConvertTo-Json -Depth 50)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 50
