param(
  [int]$CaseStatusRounds = 5,
  [int]$SupervisorStatusRounds = 2,
  [string]$CaseId = '0005',
  [string]$ExpectedMachine = 'DESKTOP-ODAQN0D'
)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ine $ExpectedMachine){throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine"}
$hook=Join-Path $PSScriptRoot 'openworker-job-started-hook.ps1'
if(-not(Test-Path -LiteralPath $hook -PathType Leaf)){throw "hook missing: $hook"}

$results=@()
function Invoke-Round([string]$Command,[string]$RequestId,[string]$Case){
  $envl=[ordered]@{schema='openworker.control-envelope.v1';request_id=$RequestId;command=$Command;machine=$ExpectedMachine;policy=[ordered]@{max_parallel=4;join='case-defined';fail_closed=$true}}
  if(-not[string]::IsNullOrWhiteSpace($Case)){$envl.case_id=$Case}
  $env:OPENWORKER_CONTROL=$envl|ConvertTo-Json -Depth 10 -Compress
  $started=[DateTimeOffset]::UtcNow
  $out=& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $hook 2>&1|Out-String
  $code=$LASTEXITCODE
  $item=[ordered]@{command=$Command;request_id=$RequestId;exit_code=$code;elapsed_ms=[int]([DateTimeOffset]::UtcNow-$started).TotalMilliseconds;output=$out.Trim()}
  $script:results+=[pscustomobject]$item
  if($code-ne0){throw "stability round failed command=$Command request_id=$RequestId exit=$code output=$out"}
}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
for($i=1;$i-le$CaseStatusRounds;$i++){Invoke-Round 'CASE.STATUS' ("hook-stability-$stamp-case-$i") $CaseId}
for($i=1;$i-le$SupervisorStatusRounds;$i++){Invoke-Round 'SUPERVISOR.STATUS' ("hook-stability-$stamp-supervisor-$i") ''}
$id="hook-stability-$stamp-idempotent"
Invoke-Round 'CASE.STATUS' $id $CaseId
Invoke-Round 'CASE.STATUS' $id $CaseId

$summary=[ordered]@{
  schema='openworker.hook-stability-result.v1';machine=$ExpectedMachine;case_id=$CaseId
  total_rounds=$results.Count;successful_rounds=@($results|Where-Object{$_.exit_code-eq0}).Count
  idempotency_request_id=$id;started_at=if($results.Count){$results[0].request_id}else{$null};completed_at=[DateTimeOffset]::UtcNow.ToString('o')
  rounds=$results
}
$path=Join-Path $env:ProgramData 'OpenWorker\hooks\stability-latest.json'
New-Item -ItemType Directory -Force -Path (Split-Path $path)|Out-Null
[IO.File]::WriteAllText($path,($summary|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 20
