param(
  [Parameter(Mandatory=$true)]
  [string]$EnvelopePath,
  [string]$ExpectedMachine = 'DESKTOP-ODAQN0D',
  [int]$TimeoutSeconds = 30
)

$ErrorActionPreference='Stop'
if($TimeoutSeconds -lt 5 -or $TimeoutSeconds -gt 120){ throw "TimeoutSeconds must be 5..120" }

function Write-ControlReceipt {
  param([hashtable]$Receipt,[string]$Path)
  $dir=Split-Path -Parent $Path
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $tmp=$Path+'.tmp.'+[Guid]::NewGuid().ToString('N')
  [IO.File]::WriteAllText($tmp,($Receipt|ConvertTo-Json -Depth 50)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  Move-Item -LiteralPath $tmp -Destination $Path -Force
}
function Quote-Arg([string]$s){ if($null-eq$s){return '""'}; return '"'+$s.Replace('"','\"')+'"' }
function Get-EnvelopeFingerprint($Envelope){
  $canonical=[ordered]@{
    schema=[string]$Envelope.schema
    request_id=[string]$Envelope.request_id
    command=[string]$Envelope.command
    machine=[string]$Envelope.machine
    case_id=[string]$Envelope.case_id
    max_parallel=if($null-ne$Envelope.policy-and$null-ne$Envelope.policy.max_parallel){[int]$Envelope.policy.max_parallel}else{4}
    join=if($null-ne$Envelope.policy){[string]$Envelope.policy.join}else{''}
    fail_closed=if($null-ne$Envelope.policy-and$null-ne$Envelope.policy.fail_closed){[bool]$Envelope.policy.fail_closed}else{$true}
  } | ConvertTo-Json -Compress -Depth 10
  $sha=[Security.Cryptography.SHA256]::Create()
  try{return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical)))).Replace('-','').ToLowerInvariant()}
  finally{$sha.Dispose()}
}

if($env:COMPUTERNAME -ine $ExpectedMachine){ throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine" }
if(-not(Test-Path -LiteralPath $EnvelopePath -PathType Leaf)){ throw "control envelope not found: $EnvelopePath" }
$envl=(Get-Content -LiteralPath $EnvelopePath -Raw)|ConvertFrom-Json -ErrorAction Stop
if($envl.schema -ne 'openworker.control-envelope.v1'){ throw "unsupported schema: $($envl.schema)" }
$requestId=[string]$envl.request_id
if([string]::IsNullOrWhiteSpace($requestId) -or ($requestId -notmatch '^[A-Za-z0-9._-]{8,128}$')){ throw 'invalid request_id' }
if([string]$envl.machine -ine $ExpectedMachine){ throw "machine mismatch envelope=$($envl.machine) expected=$ExpectedMachine" }

$command=[string]$envl.command
$needsCase=$command -in @('CASE.STATUS','CASE.CONTINUE_BATCH')
if($needsCase -and [string]::IsNullOrWhiteSpace([string]$envl.case_id)){ throw 'case_id is required' }
$maxParallel=4
if($null-ne$envl.policy-and$null-ne$envl.policy.max_parallel){$maxParallel=[int]$envl.policy.max_parallel}
if($maxParallel-lt1-or$maxParallel-gt4){ throw "max_parallel must be 1..4, got $maxParallel" }
$fingerprint=Get-EnvelopeFingerprint $envl

$receiptRoot=Join-Path $env:ProgramData 'OpenWorker\control-envelope\receipts'
$receiptPath=Join-Path $receiptRoot ($requestId+'.json')
if(Test-Path -LiteralPath $receiptPath -PathType Leaf){
  $cached=Get-Content -LiteralPath $receiptPath -Raw
  try{$cachedObj=$cached|ConvertFrom-Json -ErrorAction Stop}catch{$cachedObj=$null}
  if(($null -ne $cachedObj) -and ([string]$cachedObj.request_id -eq $requestId)){
    if((-not [string]::IsNullOrWhiteSpace([string]$cachedObj.request_fingerprint)) -and ([string]$cachedObj.request_fingerprint -ne $fingerprint)){
      $conflict=[ordered]@{
        schema='openworker.control-result.v3';request_id=$requestId;command=$command;case_id=if($needsCase){[string]$envl.case_id}else{$null};machine=$ExpectedMachine
        accepted=$false;exit_code=73;error_class='request_id_conflict';error='request_id already exists with a different control envelope';max_parallel=$maxParallel
        request_fingerprint=$fingerprint;cached_request_fingerprint=[string]$cachedObj.request_fingerprint;idempotent_hit=$false
        business_authority='openworker-local-supervisor';execution_authority='openworker-local-supervisor'
        github_action_used_for_command_transport=$true;github_action_used_for_business_execution=$false
        started_at=[DateTimeOffset]::UtcNow.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o');result=$null
      }
      $conflict|ConvertTo-Json -Depth 50
      exit 73
    }
    $cachedObj | Add-Member -NotePropertyName idempotent_hit -NotePropertyValue $true -Force
    $cachedObj|ConvertTo-Json -Depth 50
    exit ([int]$cachedObj.exit_code)
  }
}

$ctl=Join-Path $env:ProgramData 'OpenWorker\bin\openworker.exe'
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){$ctl=Join-Path $env:ProgramData 'OpenWorker\bin\openworkerctl.exe'}
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){ throw "OpenWorker control executable is not installed: $ctl" }
$cliArgs=@()
switch($command){
  'CASE.STATUS'         {$cliArgs=@('case','status',[string]$envl.case_id)}
  'CASE.CONTINUE_BATCH'{$cliArgs=@('case','continue',[string]$envl.case_id)}
  'SUPERVISOR.STATUS'  {$cliArgs=@('supervisor','status')}
  'QUEUE.CLEAR'        {$cliArgs=@('queue','clear',$ExpectedMachine)}
  default              {throw "unsupported control command: $command"}
}

$started=[DateTimeOffset]::UtcNow
$exitCode=0;$errorClass='';$errorText='';$result=$null
$outFile=Join-Path $env:TEMP ("openworker-out-$requestId-"+[Guid]::NewGuid().ToString('N')+'.txt')
$errFile=Join-Path $env:TEMP ("openworker-err-$requestId-"+[Guid]::NewGuid().ToString('N')+'.txt')
$oldRequestId=$env:OPENWORKER_CONTROL_REQUEST_ID
try{
  $env:OPENWORKER_CONTROL_REQUEST_ID=$requestId
  $argLine=($cliArgs|ForEach-Object{Quote-Arg ([string]$_)}) -join ' '
  $p=Start-Process -FilePath $ctl -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile
  if(-not $p.WaitForExit($TimeoutSeconds*1000)){
    try{$p.Kill()}catch{}
    $exitCode=124;$errorClass='timeout';$errorText="OpenWorker control timed out after ${TimeoutSeconds}s"
  }else{
    $exitCode=[int]$p.ExitCode
    $stdout=if(Test-Path $outFile){Get-Content -LiteralPath $outFile -Raw}else{''}
    $stderr=if(Test-Path $errFile){Get-Content -LiteralPath $errFile -Raw}else{''}
    $combined=($stdout+"`n"+$stderr).Trim()
    if($exitCode -ne 0){
      if(($combined -match '127\.0\.0\.1:8787') -and ($combined -match '(refused|connectex|connection)')){$errorClass='openworker_unreachable'}else{$errorClass='openworker_process_failed'}
      $errorText=$combined
    }else{
      try{$result=$stdout|ConvertFrom-Json -ErrorAction Stop}catch{$exitCode=72;$errorClass='invalid_control_output';$errorText=$combined}
    }
  }
}finally{
  $env:OPENWORKER_CONTROL_REQUEST_ID=$oldRequestId
  Remove-Item -LiteralPath $outFile,$errFile -Force -ErrorAction SilentlyContinue
}

$accepted = ($exitCode -eq 0)
$response=[ordered]@{
  schema='openworker.control-result.v3';request_id=$requestId;command=$command;case_id=if($needsCase){[string]$envl.case_id}else{$null};machine=$ExpectedMachine
  accepted=$accepted;exit_code=$exitCode;error_class=$errorClass;error=$errorText;max_parallel=$maxParallel
  request_fingerprint=$fingerprint;idempotent_hit=$false
  dispatch_semantics=if($command-eq'CASE.CONTINUE_BATCH'){'openworker_native_durable_case_admission'}else{'single_control_operation'}
  business_authority='openworker-local-supervisor';execution_authority='openworker-local-supervisor'
  dashboard_url='http://127.0.0.1:8787/ui/'
  github_action_used_for_command_transport=$true;github_action_used_for_business_execution=$false;timeout_seconds=$TimeoutSeconds
  started_at=$started.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o');result=$result
}
Write-ControlReceipt -Receipt $response -Path $receiptPath
$response|ConvertTo-Json -Depth 50
exit $exitCode
