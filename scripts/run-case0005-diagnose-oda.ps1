$ErrorActionPreference='Stop'

if($env:COMPUTERNAME -ine 'DESKTOP-ODAQN0D'){throw "wrong host $env:COMPUTERNAME"}
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ctl=Join-Path $env:ProgramData 'OpenWorker\bin\openworkerctl.exe'
if(-not(Test-Path -LiteralPath $ctl -PathType Leaf)){throw "openworkerctl missing: $ctl"}

$statusRaw=& $ctl case status 0005 2>&1 | Out-String
if($LASTEXITCODE -ne 0){throw "case status failed: $statusRaw"}
$status=$statusRaw|ConvertFrom-Json -ErrorAction Stop
$job=$status.latest_job_explain.job
if($null -eq $job){throw 'latest_job_explain.job missing'}

$allowedRoot=[IO.Path]::GetFullPath((Join-Path $env:ProgramData 'OpenWorker\node\logs'))
function Read-BoundedLog([string]$Path){
  if([string]::IsNullOrWhiteSpace($Path)){return $null}
  $full=[IO.Path]::GetFullPath($Path)
  if(-not $full.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)){throw "log path outside allowed root: $full"}
  if(-not(Test-Path -LiteralPath $full -PathType Leaf)){return [ordered]@{path=$full;exists=$false}}
  $bytes=[IO.File]::ReadAllBytes($full)
  if($bytes.Length -gt 65536){$bytes=$bytes[($bytes.Length-65536)..($bytes.Length-1)]}
  $utf8=[Text.UTF8Encoding]::new($false,$false).GetString($bytes)
  $unicode=[Text.Encoding]::Unicode.GetString($bytes)
  $big5=[Text.Encoding]::GetEncoding(950).GetString($bytes)
  $detected='utf8'
  $text=$utf8
  if($bytes.Length -ge 2 -and $bytes[0] -eq 0xff -and $bytes[1] -eq 0xfe){$detected='utf16le';$text=$unicode}
  elseif(($bytes|Where-Object {$_ -eq 0}).Count -gt [Math]::Max(2,[int]($bytes.Length/8))){$detected='utf16le-heuristic';$text=$unicode}
  return [ordered]@{
    path=$full
    exists=$true
    byte_count=$bytes.Length
    detected_encoding=$detected
    text=$text
    utf8_candidate=$utf8
    utf16le_candidate=$unicode
    cp950_candidate=$big5
    base64=[Convert]::ToBase64String($bytes)
  }
}

$result=[ordered]@{
  schema='openworker.case0005-diagnose-result/v2'
  case_id='0005'
  machine=$env:COMPUTERNAME
  runner_name=$env:RUNNER_NAME
  accepted=$true
  exit_code=0
  error=''
  github_run_id=$env:GITHUB_RUN_ID
  github_run_attempt=$env:GITHUB_RUN_ATTEMPT
  github_action_used_for_business_execution=$false
  observed_at=[DateTimeOffset]::UtcNow.ToString('o')
  latest_job=[ordered]@{
    job_id=$job.job_id
    status=$job.status
    exit_code=$job.exit_code
    started_at=$job.started_at
    finished_at=$job.finished_at
    stderr_path=$job.stderr_path
    stdout_path=$job.stdout_path
  }
  execution_summary=$status.latest_job_explain.execution_summary
  stderr=(Read-BoundedLog ([string]$job.stderr_path))
  stdout=(Read-BoundedLog ([string]$job.stdout_path))
}

$requestId="diagnose-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
$rel="case-evidence/case0005-diagnose/$requestId.json"
$latestRel='case-evidence/case0005-diagnose/latest.json'
$path=Join-Path $repoRoot $rel
$latestPath=Join-Path $repoRoot $latestRel
New-Item -ItemType Directory -Force -Path (Split-Path $path -Parent)|Out-Null
$json=$result|ConvertTo-Json -Depth 50
[IO.File]::WriteAllText($path,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($latestPath,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host ($result|ConvertTo-Json -Depth 50 -Compress)

Push-Location $repoRoot
try{
  git config user.name 'openworker-case-diagnose'
  git config user.email 'openworker-case-diagnose@users.noreply.github.com'
  git add -- $rel $latestRel
  git commit -m "receipt: Case0005 diagnose $requestId"
  if($LASTEXITCODE -ne 0){throw 'failed to commit diagnose receipt'}
  for($i=0;$i -lt 3;$i++){
    git pull --rebase origin main
    if($LASTEXITCODE -eq 0){
      git push origin HEAD:main
      if($LASTEXITCODE -eq 0){break}
    }else{git rebase --abort 2>$null}
    if($i -eq 2){throw 'failed to publish diagnose receipt'}
    Start-Sleep -Seconds 2
  }
}finally{Pop-Location}
exit 0
