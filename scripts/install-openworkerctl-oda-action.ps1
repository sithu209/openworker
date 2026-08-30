$ErrorActionPreference='Stop'

$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$result=[ordered]@{
  schema='openworker-control-install/v6'
  succeeded=$false
  status='FAILED'
  machine=$env:COMPUTERNAME
  runner_name=$env:RUNNER_NAME
  canonical_executable=''
  compatibility_executable=''
  supervisor_status=''
  route_label=''
  single_go_control_authority=$true
  python_required_for_case_bootstrap=$false
  error=''
  github_run_id=$env:GITHUB_RUN_ID
  github_run_attempt=$env:GITHUB_RUN_ATTEMPT
  github_action_used_for_command_transport=$true
  github_action_used_for_business_execution=$false
  observed_at=[DateTimeOffset]::UtcNow.ToString('o')
}

try {
  if($env:COMPUTERNAME -ine 'DESKTOP-ODAQN0D'){throw "wrong host $env:COMPUTERNAME expected=DESKTOP-ODAQN0D"}
  $installer=Join-Path $PSScriptRoot 'install-openworkerctl.ps1'
  if(-not(Test-Path -LiteralPath $installer -PathType Leaf)){throw "installer missing: $installer"}
  $installRoot=Join-Path $env:ProgramData 'OpenWorker\bin'
  & $installer -InstallRoot $installRoot
  $openworker=Join-Path $installRoot 'openworker.exe'
  $ctl=Join-Path $installRoot 'openworkerctl.exe'
  if(-not(Test-Path -LiteralPath $openworker -PathType Leaf)){throw "openworker missing after install: $openworker"}
  if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){throw "openworkerctl compatibility binary missing after install: $ctl"}
  $raw=& $openworker supervisor status 2>&1 | Out-String
  $exitCode=$LASTEXITCODE
  if($exitCode -ne 0){throw "openworker supervisor status failed exit=$exitCode output=$raw"}
  try{$status=$raw|ConvertFrom-Json -ErrorAction Stop}catch{throw "non-JSON supervisor status: $raw"}
  if($status.status -ne 'OPERATIONAL'){throw "local supervisor is not OPERATIONAL: $raw"}
  if($status.route_label -ne 'LOCAL_SUPERVISOR'){throw "unexpected route_label=$($status.route_label)"}
  if($status.github_action_used_for_business_execution -eq $true){throw 'local supervisor reports GitHub business execution=true'}
  $result.succeeded=$true
  $result.status='REAL_VERIFIED'
  $result.canonical_executable=$openworker
  $result.compatibility_executable=$ctl
  $result.supervisor_status=$status.status
  $result.route_label=$status.route_label
} catch {
  $result.error=$_.Exception.Message
}

$result.observed_at=[DateTimeOffset]::UtcNow.ToString('o')
$rel="command-results/oda-install/$env:GITHUB_RUN_ID/final.json"
$json=$result|ConvertTo-Json -Depth 30
$tempRoot=Join-Path $env:RUNNER_TEMP "openworker-install-publish-$env:GITHUB_RUN_ID"
Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $tempRoot|Out-Null
$receiptTemp=Join-Path $tempRoot 'final.json'
[IO.File]::WriteAllText($receiptTemp,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$sumSource=Join-Path $repoRoot 'go-runtime\go.sum'
$sumTemp=Join-Path $tempRoot 'go.sum'
if(Test-Path -LiteralPath $sumSource){Copy-Item -LiteralPath $sumSource -Destination $sumTemp -Force}
Write-Host ($result|ConvertTo-Json -Depth 30 -Compress)

Push-Location $repoRoot
try {
  $gitDir=Join-Path $repoRoot '.git'
  if((Test-Path -LiteralPath (Join-Path $gitDir 'rebase-merge')) -or (Test-Path -LiteralPath (Join-Path $gitDir 'rebase-apply'))){
    & git rebase --abort
    if($LASTEXITCODE -ne 0){throw 'failed to abort existing rebase'}
  }
  & git fetch origin main
  if($LASTEXITCODE -ne 0){throw 'failed to fetch origin/main before receipt publication'}
  & git reset --hard origin/main
  if($LASTEXITCODE -ne 0){throw 'failed to reset clean origin/main before receipt publication'}
  & git clean -ffdx
  if($LASTEXITCODE -ne 0){throw 'failed to clean checkout before receipt publication'}
  $resultPath=Join-Path $repoRoot $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $resultPath -Parent)|Out-Null
  Copy-Item -LiteralPath $receiptTemp -Destination $resultPath -Force
  if(Test-Path -LiteralPath $sumTemp){Copy-Item -LiteralPath $sumTemp -Destination (Join-Path $repoRoot 'go-runtime\go.sum') -Force}
  & git config user.name 'openworker-control-plane-installer'
  & git config user.email 'openworker-control-plane-installer@users.noreply.github.com'
  & git add -- $rel
  if(Test-Path -LiteralPath (Join-Path $repoRoot 'go-runtime\go.sum')){& git add -- 'go-runtime/go.sum'}
  & git diff --cached --quiet
  if($LASTEXITCODE -ne 0){
    & git commit -m "receipt: unified Go OpenWorker install $env:GITHUB_RUN_ID"
    if($LASTEXITCODE -ne 0){throw 'failed to commit install receipt/module sums'}
    & git push origin HEAD:main
    if($LASTEXITCODE -ne 0){throw 'failed to push clean immutable install receipt'}
  }
} finally { Pop-Location; Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }

if(-not $result.succeeded){Write-Error "ODA_OPENWORKER_INSTALL_FAILED error=$($result.error)";exit 1}
Write-Host 'ODA_OPENWORKER_UNIFIED_GO_REAL_VERIFIED'
exit 0
