param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('supervisor_status','case_status','case_work_status','case_diagnose','case_bootstrap','case_continue','queue_clear')]
  [string]$Command,
  [Parameter(Mandatory=$true)]
  [string]$RequestId
)

$ErrorActionPreference='Stop'

if($env:COMPUTERNAME -ine 'DESKTOP-ODAQN0D'){
  throw "wrong host $env:COMPUTERNAME expected=DESKTOP-ODAQN0D"
}
if([string]::IsNullOrWhiteSpace($RequestId) -or $RequestId -notmatch '^[A-Za-z0-9._-]{8,128}$'){
  throw "invalid request_id=$RequestId"
}

$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$wrapper=Join-Path $PSScriptRoot 'invoke-local-supervisor-command-transport.ps1'
if(-not(Test-Path -LiteralPath $wrapper -PathType Leaf)){throw "transport wrapper missing: $wrapper"}

$raw=& $wrapper -Command $Command -RequestId $RequestId -ExpectedMachine 'DESKTOP-ODAQN0D' | Out-String
try{$receipt=$raw|ConvertFrom-Json -ErrorAction Stop}catch{throw "non-JSON transport receipt: $raw"}
if($receipt.schema -ne 'openworker.command-transport.v1'){throw "unexpected receipt schema=$($receipt.schema)"}
if(-not $receipt.github_action_used_for_command_transport){throw 'command transport flag missing'}
if($receipt.github_action_used_for_business_execution){throw 'business execution escaped into GitHub Action'}

$result=[ordered]@{
  schema='openworker.command-result.v1'
  phase=if($receipt.accepted){'oda_accepted'}else{'oda_rejected'}
  request_id=$RequestId
  command=$Command
  machine='DESKTOP-ODAQN0D'
  case_id=if($Command -in @('case_status','case_work_status','case_diagnose','case_bootstrap','case_continue')){'0005'}else{$null}
  transport='github_actions_transient_dispatch'
  accepted=[bool]$receipt.accepted
  transport_ok=[bool]$receipt.accepted
  exit_code=$receipt.exit_code
  error=$receipt.error
  github_run_id=$env:GITHUB_RUN_ID
  github_run_attempt=$env:GITHUB_RUN_ATTEMPT
  runner_name=$env:RUNNER_NAME
  runner_machine=$env:COMPUTERNAME
  github_action_used_for_command_transport=$true
  github_action_used_for_business_execution=$false
  business_completion_claimed=$false
  authoritative_business_state='openworker'
  completed_at=[DateTimeOffset]::UtcNow.ToString('o')
  receipt=$receipt
}

$resultDir=Join-Path $repoRoot ("command-results\oda\"+$RequestId)
New-Item -ItemType Directory -Force -Path $resultDir|Out-Null
$resultPath=Join-Path $resultDir 'final.json'
$resultJson=$result|ConvertTo-Json -Depth 50
[IO.File]::WriteAllText($resultPath,$resultJson+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host ($result|ConvertTo-Json -Depth 50 -Compress)

Push-Location $repoRoot
try{
  git config user.name 'openworker-command-transport'
  git config user.email 'openworker-command-transport@users.noreply.github.com'
  $rel="command-results/oda/$RequestId/final.json"
  git add -- $rel
  git diff --cached --quiet
  if($LASTEXITCODE -ne 0){
    git commit -m "receipt: ODA $Command $RequestId final"
    if($LASTEXITCODE -ne 0){throw 'failed to commit transport receipt'}
    $pushed=$false
    for($i=0;$i -lt 3;$i++){
      git pull --rebase origin main
      if($LASTEXITCODE -ne 0){git rebase --abort 2>$null; Start-Sleep -Seconds 1; continue}
      git push origin HEAD:main
      if($LASTEXITCODE -eq 0){$pushed=$true;break}
      Start-Sleep -Seconds 2
    }
    if(-not $pushed){throw 'failed to push immutable transport receipt'}
  }
}finally{Pop-Location}

if(-not $result.accepted){
  Write-Error "LOCAL_TRANSPORT_REJECTED request_id=$RequestId exit_code=$($result.exit_code) error=$($result.error)"
  exit 1
}
Write-Host 'TRANSPORT_ONLY_VERIFIED github_action_used_for_business_execution=false'
exit 0
