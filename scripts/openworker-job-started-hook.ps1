param()
$ErrorActionPreference='Stop'

function Write-HookReceipt {
  param([hashtable]$Receipt)
  try{
    $root=Join-Path $env:ProgramData 'OpenWorker\hooks\receipts'
    New-Item -ItemType Directory -Force -Path $root|Out-Null
    $name=if($Receipt.request_id){[string]$Receipt.request_id}else{'passthrough-'+[Guid]::NewGuid().ToString('N')}
    $path=Join-Path $root ($name+'.json')
    $tmp=$path+'.tmp.'+[Guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($tmp,($Receipt|ConvertTo-Json -Depth 30)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $path -Force
  }catch{ Write-Warning "[OpenWorker Hook] receipt write failed: $($_.Exception.Message)" }
}

$started=[DateTimeOffset]::UtcNow
$secret=[string]$env:OPENWORKER_CONTROL
if([string]::IsNullOrWhiteSpace($secret)){
  Write-Host '[OpenWorker Hook] no OPENWORKER_CONTROL; passthrough'
  Write-HookReceipt -Receipt ([ordered]@{schema='openworker.hook-receipt.v2';mode='passthrough';machine=[Environment]::MachineName;accepted=$true;exit_code=0;started_at=$started.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o')})
  exit 0
}

Write-Host '[OpenWorker Hook] OPENWORKER_CONTROL detected'
try{$envelope=$secret|ConvertFrom-Json -ErrorAction Stop}catch{
  Write-HookReceipt -Receipt ([ordered]@{schema='openworker.hook-receipt.v2';mode='control';machine=[Environment]::MachineName;accepted=$false;exit_code=80;error_class='invalid_json';error=$_.Exception.Message;started_at=$started.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o')})
  Write-Error "[OpenWorker Hook] invalid JSON: $($_.Exception.Message)";exit 80
}

$requestId=[string]$envelope.request_id
$fail={param([int]$Code,[string]$Class,[string]$Message)
  Write-HookReceipt -Receipt ([ordered]@{schema='openworker.hook-receipt.v2';mode='control';request_id=$requestId;command=[string]$envelope.command;machine=[Environment]::MachineName;accepted=$false;exit_code=$Code;error_class=$Class;error=$Message;started_at=$started.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o')})
  Write-Error "[OpenWorker Hook] $Message";exit $Code
}

if([string]$envelope.schema -ne 'openworker.control-envelope.v1'){&$fail 81 'unsupported_schema' "unsupported schema: $($envelope.schema)"}
if([string]::IsNullOrWhiteSpace($requestId)-or($requestId-notmatch'^[A-Za-z0-9._-]{8,128}$')){&$fail 82 'invalid_request_id' 'invalid request_id'}
if([string]::IsNullOrWhiteSpace([string]$envelope.command)){&$fail 83 'missing_command' 'command is required'}
$allowed=@('CASE.STATUS','CASE.CONTINUE_BATCH','SUPERVISOR.STATUS','QUEUE.CLEAR')
if(([string]$envelope.command)-notin$allowed){&$fail 84 'unsupported_command' "unsupported command: $($envelope.command)"}

$machine=[Environment]::MachineName
if([string]$envelope.machine -ine $machine){&$fail 85 'machine_mismatch' "machine mismatch envelope=$($envelope.machine) local=$machine"}
$max=4
if($null-ne$envelope.policy-and$null-ne$envelope.policy.max_parallel){$max=[int]$envelope.policy.max_parallel}
if($max-lt1-or$max-gt4){&$fail 86 'invalid_parallelism' "max_parallel must be 1..4, got $max"}

$dispatcher='C:\ProgramData\OpenWorker\hooks\invoke-openworker-control-envelope-v1.ps1'
if(-not(Test-Path -LiteralPath $dispatcher -PathType Leaf)){&$fail 88 'dispatcher_missing' "dispatcher missing: $dispatcher"}

$temp=Join-Path $env:TEMP ("openworker-control-$requestId-"+[Guid]::NewGuid().ToString('N')+'.json')
try{
  [IO.File]::WriteAllText($temp,($envelope|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  $output=& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $dispatcher -EnvelopePath $temp -ExpectedMachine $machine -TimeoutSeconds 30 2>&1 | Out-String
  $code=$LASTEXITCODE
  $parsed=$null
  try{$parsed=$output|ConvertFrom-Json -ErrorAction Stop}catch{}
  $errorClass=if($null-ne$parsed){[string]$parsed.error_class}elseif($code-eq124){'timeout'}else{'dispatcher_failed'}
  Write-HookReceipt -Receipt ([ordered]@{schema='openworker.hook-receipt.v2';mode='control';request_id=$requestId;command=[string]$envelope.command;case_id=[string]$envelope.case_id;machine=$machine;accepted=($code-eq0);exit_code=$code;error_class=$errorClass;started_at=$started.ToString('o');completed_at=[DateTimeOffset]::UtcNow.ToString('o');dispatcher_result=$parsed;raw_output=if($null-eq$parsed){$output}else{$null}})
  if($code-ne0){Write-Error "[OpenWorker Hook] dispatcher failed exit=$code class=$errorClass";exit $code}
  Write-Host '[OpenWorker Hook] control envelope accepted by OpenWorker'
  exit 0
}finally{Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
