param(
  [Parameter(Mandatory=$true)]
  [string]$EnvelopePath,
  [string]$ExpectedMachine = 'DESKTOP-ODAQN0D',
  [int]$TimeoutSeconds = 30
)

$ErrorActionPreference='Stop'
if(-not(Test-Path -LiteralPath $EnvelopePath -PathType Leaf)){throw "control envelope not found: $EnvelopePath"}
$envl=(Get-Content -LiteralPath $EnvelopePath -Raw)|ConvertFrom-Json -ErrorAction Stop
if($envl.schema -ne 'openworker.control-envelope.v1'){throw "unsupported schema: $($envl.schema)"}
if([string]$envl.command -ne 'CASE.CLEAR_AND_CONTINUE'){throw "expected CASE.CLEAR_AND_CONTINUE, got $($envl.command)"}
if([string]::IsNullOrWhiteSpace([string]$envl.case_id)){throw 'case_id is required'}
if([string]$envl.machine -ine $ExpectedMachine){throw "machine mismatch envelope=$($envl.machine) expected=$ExpectedMachine"}
if($env:COMPUTERNAME -ine $ExpectedMachine){throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine"}

$parentId=[string]$envl.request_id
if([string]::IsNullOrWhiteSpace($parentId) -or ($parentId -notmatch '^[A-Za-z0-9._-]{8,100}$')){throw 'invalid request_id'}
$dispatcher=Join-Path $PSScriptRoot 'invoke-openworker-control-envelope-v1.ps1'
if(-not(Test-Path -LiteralPath $dispatcher -PathType Leaf)){throw "dispatcher missing: $dispatcher"}

function Invoke-ChildControl {
  param([string]$Suffix,[string]$Command,[bool]$NeedsCase=$false)
  $childId="$parentId.$Suffix"
  $child=[ordered]@{
    schema='openworker.control-envelope.v1'
    request_id=$childId
    command=$Command
    machine=$ExpectedMachine
    case_id=if($NeedsCase){[string]$envl.case_id}else{$null}
    policy=[ordered]@{
      max_parallel=if($null-ne$envl.policy-and$null-ne$envl.policy.max_parallel){[int]$envl.policy.max_parallel}else{4}
      join='case-defined'
      fail_closed=$true
    }
  }
  $tmp=Join-Path $env:TEMP ("openworker-control-$childId-"+[Guid]::NewGuid().ToString('N')+'.json')
  try {
    [IO.File]::WriteAllText($tmp,($child|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
    $raw=& $dispatcher -EnvelopePath $tmp -ExpectedMachine $ExpectedMachine -TimeoutSeconds $TimeoutSeconds 2>&1 | Out-String
    $exitCode=$LASTEXITCODE
    try{$obj=$raw|ConvertFrom-Json -ErrorAction Stop}catch{throw "invalid child control output command=$Command raw=$raw"}
    if($exitCode-ne0 -or -not [bool]$obj.accepted){throw "child control failed command=$Command request_id=$childId exit=$exitCode class=$($obj.error_class) error=$($obj.error)"}
    return $obj
  } finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  }
}

$started=[DateTimeOffset]::UtcNow
$clear=Invoke-ChildControl -Suffix 'clear' -Command 'QUEUE.CLEAR'
$continue=Invoke-ChildControl -Suffix 'continue' -Command 'CASE.CONTINUE_BATCH' -NeedsCase $true
$status=Invoke-ChildControl -Suffix 'status' -Command 'CASE.STATUS' -NeedsCase $true
$supervisor=Invoke-ChildControl -Suffix 'supervisor' -Command 'SUPERVISOR.STATUS'

$result=[ordered]@{
  schema='openworker.control-batch-result.v1'
  request_id=$parentId
  command='CASE.CLEAR_AND_CONTINUE'
  case_id=[string]$envl.case_id
  machine=$ExpectedMachine
  accepted=$true
  execution_order=@('QUEUE.CLEAR','CASE.CONTINUE_BATCH','CASE.STATUS','SUPERVISOR.STATUS')
  atomicity='ordered-fail-closed'
  github_action_used_for_command_transport=$true
  github_action_used_for_business_execution=$false
  business_authority='openworker-go-native-case-controller'
  execution_authority='go-tool-runtime-local-supervisor'
  started_at=$started.ToString('o')
  completed_at=[DateTimeOffset]::UtcNow.ToString('o')
  steps=[ordered]@{queue_clear=$clear;continue_batch=$continue;case_status=$status;supervisor_status=$supervisor}
}

$receiptRoot=Join-Path $env:ProgramData 'OpenWorker\control-envelope\batch-receipts'
New-Item -ItemType Directory -Force -Path $receiptRoot|Out-Null
$receiptPath=Join-Path $receiptRoot ($parentId+'.json')
$tmpReceipt=$receiptPath+'.tmp.'+[Guid]::NewGuid().ToString('N')
[IO.File]::WriteAllText($tmpReceipt,($result|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $tmpReceipt -Destination $receiptPath -Force
$result|ConvertTo-Json -Depth 80
