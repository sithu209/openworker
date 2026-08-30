param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('supervisor_status','case_status','case_diagnose','case_bootstrap','case_continue','queue_clear')]
  [string]$Command,
  [Parameter(Mandatory=$true)]
  [string]$RequestId
)

$ErrorActionPreference='Stop'
$ExpectedMachine='DESKTOP-O87PJNR'
$CaseId='0004'

if($env:COMPUTERNAME -ine $ExpectedMachine){ throw "wrong host $env:COMPUTERNAME expected=$ExpectedMachine" }
if([string]::IsNullOrWhiteSpace($RequestId) -or $RequestId -notmatch '^[A-Za-z0-9._-]{8,128}$'){ throw "invalid request_id=$RequestId" }

$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cacheRoot=Join-Path $env:ProgramData 'OpenWorker\command-transport\receipts'
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
$cachePath=Join-Path $cacheRoot ($RequestId+'.json')
if(Test-Path -LiteralPath $cachePath -PathType Leaf){ Get-Content -LiteralPath $cachePath -Raw; exit 0 }

$binRoot=Join-Path $env:ProgramData 'OpenWorker\bin'
New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
$ctl=Join-Path $binRoot 'openworker.exe'
$compatCtl=Join-Path $binRoot 'openworkerctl.exe'

if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){
  $go=(Get-Command go -ErrorAction SilentlyContinue)
  if($null -eq $go){ throw 'Go toolchain is required to bootstrap OpenWorker CLI on O87' }
  $goRoot=Join-Path $repoRoot 'go-runtime'
  if(-not(Test-Path -LiteralPath (Join-Path $goRoot 'go.mod') -PathType Leaf)){ throw "go-runtime source unavailable: $goRoot" }
  Push-Location $goRoot
  try{
    & $go.Source build -o $ctl ./cmd/openworker
    if($LASTEXITCODE -ne 0){throw "failed to build openworker.exe exit=$LASTEXITCODE"}
    & $go.Source build -o $compatCtl ./cmd/openworkerctl
    if($LASTEXITCODE -ne 0){throw "failed to build openworkerctl.exe exit=$LASTEXITCODE"}
  } finally { Pop-Location }
}
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf) -and (Test-Path -LiteralPath $compatCtl -PathType Leaf)){ $ctl=$compatCtl }

$cliArgs=@()
switch($Command){
  'supervisor_status' { $cliArgs=@('supervisor','status') }
  'case_status'       { $cliArgs=@('case','status',$CaseId) }
  'case_diagnose'     { $cliArgs=@('case','diagnose',$CaseId) }
  'case_bootstrap'    { $cliArgs=@('case','bootstrap',$CaseId) }
  'case_continue'     { $cliArgs=@('case','continue',$CaseId) }
  'queue_clear'       { $cliArgs=@('queue','clear',$ExpectedMachine) }
  default             { throw "unsupported command: $Command" }
}

$result=$null;$errorText='';$exitCode=0;$started=[DateTimeOffset]::UtcNow
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){
  $exitCode=127;$errorText="OpenWorker control executable is not installed: $ctl"
}else{
  try{
    $previousRoot=$env:OPENWORKER_ROOT
    $env:OPENWORKER_ROOT=$repoRoot
    try{$raw=& $ctl @cliArgs 2>&1 | Out-String}finally{$env:OPENWORKER_ROOT=$previousRoot}
    $exitCode=$LASTEXITCODE
    if($exitCode -ne 0){$errorText="OpenWorker control command failed exit=$exitCode output=$raw"}
    else{try{$result=$raw|ConvertFrom-Json -ErrorAction Stop}catch{$exitCode=70;$errorText="OpenWorker control command returned non-JSON output: $raw"}}
  }catch{$exitCode=71;$errorText=$_.Exception.Message}
}

$accepted=($exitCode -eq 0)
if($accepted -and $Command -eq 'case_continue'){
  $hasDurableIdentity=$false
  if($null -ne $result){
    $candidates=@($result)
    if($null -ne $result.controller_result){$candidates+=@($result.controller_result)}
    if($null -ne $result.result){$candidates+=@($result.result)}
    if($null -ne $result.controller_result -and $null -ne $result.controller_result.result){$candidates+=@($result.controller_result.result)}
    foreach($candidate in $candidates){
      if($null -eq $candidate){continue}
      if($candidate.work_id){$hasDurableIdentity=$true}
      if($candidate.queue_item -and $candidate.queue_item.work_id){$hasDurableIdentity=$true}
      if($candidate.fanout_work_ids -and @($candidate.fanout_work_ids).Count -gt 0){$hasDurableIdentity=$true}
      if($candidate.accepted -eq $true){$hasDurableIdentity=$true}
      if($candidate.queue_status -and @('accepted','pending','claimed','fanout_active','already_submitted') -contains [string]$candidate.queue_status){$hasDurableIdentity=$true}
    }
  }
  if(-not $hasDurableIdentity){$accepted=$false;$exitCode=72;$errorText='case_continue returned no durable work identity/accepted evidence'}
}

$receipt=[ordered]@{
  schema='openworker.command-transport.v1';transport='github_actions_transient_dispatch';request_id=$RequestId;command=$Command;case_id=if($Command -like 'case_*'){$CaseId}else{$null};machine=$ExpectedMachine;accepted=$accepted;exit_code=$exitCode;error=$errorText;github_run_id=$env:GITHUB_RUN_ID;github_run_attempt=$env:GITHUB_RUN_ATTEMPT;runner_name=$env:RUNNER_NAME;runner_machine=$env:COMPUTERNAME;github_action_used_for_command_transport=$true;github_action_used_for_business_execution=$false;business_completion_claimed=$false;authoritative_business_state='openworker';started_at=$started.ToString('o');dispatched_at=[DateTimeOffset]::UtcNow.ToString('o');result=$result
}
$json=$receipt|ConvertTo-Json -Depth 50
[IO.File]::WriteAllText($cachePath,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$final=[ordered]@{schema='openworker.command-result.v1';phase=if($accepted){'o87_accepted'}else{'o87_rejected'};request_id=$RequestId;command=$Command;machine=$ExpectedMachine;case_id=if($Command -like 'case_*'){$CaseId}else{$null};transport='github_actions_transient_dispatch';accepted=$accepted;transport_ok=$accepted;exit_code=$exitCode;error=$errorText;github_run_id=$env:GITHUB_RUN_ID;github_run_attempt=$env:GITHUB_RUN_ATTEMPT;runner_name=$env:RUNNER_NAME;runner_machine=$env:COMPUTERNAME;github_action_used_for_command_transport=$true;github_action_used_for_business_execution=$false;business_completion_claimed=$false;authoritative_business_state='openworker';completed_at=[DateTimeOffset]::UtcNow.ToString('o');receipt=$receipt}
$resultDir=Join-Path $repoRoot ("command-results\o87\"+$RequestId);New-Item -ItemType Directory -Force -Path $resultDir|Out-Null
$resultPath=Join-Path $resultDir 'final.json';[IO.File]::WriteAllText($resultPath,($final|ConvertTo-Json -Depth 50)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host ($final|ConvertTo-Json -Depth 50 -Compress)

Push-Location $repoRoot
try{
  git config user.name 'openworker-command-transport';git config user.email 'openworker-command-transport@users.noreply.github.com'
  $rel="command-results/o87/$RequestId/final.json";git add -- $rel;git diff --cached --quiet
  if($LASTEXITCODE -ne 0){
    git commit -m "receipt: O87 $Command $RequestId final";if($LASTEXITCODE -ne 0){throw 'failed to commit transport receipt'}
    $pushed=$false
    for($i=0;$i -lt 3;$i++){git pull --rebase origin main;if($LASTEXITCODE -ne 0){git rebase --abort 2>$null;Start-Sleep -Seconds 1;continue};git push origin HEAD:main;if($LASTEXITCODE -eq 0){$pushed=$true;break};Start-Sleep -Seconds 2}
    if(-not $pushed){throw 'failed to push immutable transport receipt'}
  }
}finally{Pop-Location}
if(-not $accepted){Write-Error "LOCAL_TRANSPORT_REJECTED request_id=$RequestId exit_code=$exitCode error=$errorText";exit 1}
Write-Host 'TRANSPORT_ONLY_VERIFIED github_action_used_for_business_execution=false';exit 0
