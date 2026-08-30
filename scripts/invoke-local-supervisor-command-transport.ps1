param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('supervisor_status','case_status','case_work_status','case_diagnose','case_bootstrap','case_continue','queue_clear')]
  [string]$Command,
  [string]$RequestId = '',
  [string]$ExpectedMachine = 'DESKTOP-ODAQN0D'
)

$ErrorActionPreference='Stop'

if($env:COMPUTERNAME -ine $ExpectedMachine){
  throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine"
}
if($ExpectedMachine -ine 'DESKTOP-ODAQN0D'){
  throw "unsupported machine $ExpectedMachine"
}
if([string]::IsNullOrWhiteSpace($RequestId)){
  $RequestId="$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
}
if($RequestId -notmatch '^[A-Za-z0-9._-]{8,128}$'){
  throw "invalid request id: $RequestId"
}

$cacheRoot=Join-Path $env:ProgramData 'OpenWorker\command-transport\receipts'
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
$cachePath=Join-Path $cacheRoot ($RequestId + '.json')
if(Test-Path -LiteralPath $cachePath -PathType Leaf){
  Get-Content -LiteralPath $cachePath -Raw
  exit 0
}

$ctl=Join-Path $env:ProgramData 'OpenWorker\bin\openworker.exe'
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){
  $ctl=Join-Path $env:ProgramData 'OpenWorker\bin\openworkerctl.exe'
}
$cliArgs=@()
switch($Command){
  'supervisor_status' { $cliArgs=@('supervisor','status') }
  'case_status'       { $cliArgs=@('case','status','0005') }
  'case_work_status'  { $cliArgs=@() }
  'case_diagnose'     { $cliArgs=@('case','diagnose','0005') }
  'case_bootstrap'    { $cliArgs=@('case','bootstrap','0005') }
  'case_continue'     { $cliArgs=@('case','continue','0005') }
  'queue_clear'       { $cliArgs=@('queue','clear','DESKTOP-ODAQN0D') }
  default             { throw "unsupported command: $Command" }
}

function Test-Accepted($Value){
  if($null -eq $Value){ return $false }
  if($Value -is [bool]){ return $Value }
  if($Value -is [System.Collections.IDictionary]){
    foreach($k in $Value.Keys){
      if(([string]$k -ieq 'accepted') -and ($Value[$k] -eq $true)){ return $true }
      if(Test-Accepted $Value[$k]){ return $true }
    }
    return $false
  }
  if($Value -is [pscustomobject]){
    foreach($p in $Value.PSObject.Properties){
      if(($p.Name -ieq 'accepted') -and ($p.Value -eq $true)){ return $true }
      if(Test-Accepted $p.Value){ return $true }
    }
    return $false
  }
  if(($Value -is [System.Collections.IEnumerable]) -and -not($Value -is [string])){
    foreach($item in $Value){ if(Test-Accepted $item){ return $true } }
  }
  return $false
}

function Test-GoNativeBootstrapCompleted($Value){
  if($null -eq $Value){ return $false }
  if($Value -is [pscustomobject]){
    if($Value.controller -eq 'go-native' -and $Value.python_required -ne $true -and $Value.stage -eq 'go_native_bootstrap_completed'){
      return $true
    }
    foreach($p in $Value.PSObject.Properties){ if(Test-GoNativeBootstrapCompleted $p.Value){ return $true } }
    return $false
  }
  if($Value -is [System.Collections.IDictionary]){
    if($Value['controller'] -eq 'go-native' -and $Value['python_required'] -ne $true -and $Value['stage'] -eq 'go_native_bootstrap_completed'){
      return $true
    }
    foreach($k in $Value.Keys){ if(Test-GoNativeBootstrapCompleted $Value[$k]){ return $true } }
    return $false
  }
  if(($Value -is [System.Collections.IEnumerable]) -and -not($Value -is [string])){
    foreach($item in $Value){ if(Test-GoNativeBootstrapCompleted $item){ return $true } }
  }
  return $false
}

$result=$null
$errorText=''
$exitCode=0
$started=[DateTimeOffset]::UtcNow

if($Command -eq 'case_work_status'){
  try{
    $workId='case0005-0005-010-r000014-17b8b780'
    $base='http://127.0.0.1:8848'
    $work=Invoke-RestMethod -Method GET -Uri ($base+'/api/execution/local-work/'+[uri]::EscapeDataString($workId)) -TimeoutSec 10
    $events=Invoke-RestMethod -Method GET -Uri ($base+'/api/execution/local-work/'+[uri]::EscapeDataString($workId)+'/events?limit=100') -TimeoutSec 10
    $supervisor=Invoke-RestMethod -Method GET -Uri ($base+'/api/execution/local-supervisor/status?machine=DESKTOP-ODAQN0D') -TimeoutSec 10
    $result=[ordered]@{
      schema='openworker.case-work-status/v1'
      case_id='0005'
      work_id=$workId
      machine='DESKTOP-ODAQN0D'
      authority='go-tool-runtime-local-supervisor'
      read_only=$true
      work=$work
      events=$events
      supervisor=$supervisor
      observed_at=[DateTimeOffset]::UtcNow.ToString('o')
    }
  }catch{
    $exitCode=71
    $errorText=$_.Exception.Message
  }
}elseif(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){
  $exitCode=127
  $errorText="OpenWorker control executable is not installed: $ctl"
}else{
  try{
    $raw=& $ctl @cliArgs 2>&1 | Out-String
    $exitCode=$LASTEXITCODE
    if($exitCode -ne 0){
      $errorText="OpenWorker control command failed exit=$exitCode output=$raw"
    }else{
      try{ $result=$raw | ConvertFrom-Json -ErrorAction Stop }
      catch{
        $exitCode=70
        $errorText="OpenWorker control command returned non-JSON output: $raw"
      }
    }
  }catch{
    $exitCode=71
    $errorText=$_.Exception.Message
  }
}

$accepted=($exitCode -eq 0)
if($accepted -and $Command -eq 'case_continue'){
  $accepted=Test-Accepted $result
  if(-not $accepted){
    $exitCode=72
    $errorText='case_continue did not return accepted=true'
  }
}
if($accepted -and $Command -eq 'case_bootstrap'){
  $accepted=Test-GoNativeBootstrapCompleted $result
  if(-not $accepted){
    $exitCode=73
    $errorText='case_bootstrap did not return Go-native completed bootstrap evidence'
  }
}

$receipt=[ordered]@{
  schema='openworker.command-transport.v1'
  transport='github_actions'
  request_id=$RequestId
  command=$Command
  case_id=if($Command -in @('case_status','case_work_status','case_diagnose','case_bootstrap','case_continue')){'0005'}else{$null}
  machine='DESKTOP-ODAQN0D'
  accepted=$accepted
  exit_code=$exitCode
  error=$errorText
  github_run_id=$env:GITHUB_RUN_ID
  github_run_attempt=$env:GITHUB_RUN_ATTEMPT
  github_action_used_for_command_transport=$true
  github_action_used_for_business_execution=$false
  business_completion_claimed=$false
  authoritative_business_state='openworker'
  started_at=$started.ToString('o')
  dispatched_at=[DateTimeOffset]::UtcNow.ToString('o')
  result=$result
}

$json=$receipt | ConvertTo-Json -Depth 50
[IO.File]::WriteAllText($cachePath,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$json
