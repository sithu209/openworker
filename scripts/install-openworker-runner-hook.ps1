param(
  [string]$RunnerRoot = '',
  [string]$OpenWorkerRepoRoot = '',
  [switch]$InstallFilesOnly
)

$ErrorActionPreference='Stop'

function Resolve-RunnerRoot {
  param([string]$ExplicitRoot)
  if(-not [string]::IsNullOrWhiteSpace($ExplicitRoot)){
    $resolved=(Resolve-Path -LiteralPath $ExplicitRoot).Path
    if(Test-Path -LiteralPath (Join-Path $resolved '.env') -PathType Leaf){return $resolved}
    throw "runner .env not found under explicit root: $resolved"
  }

  $seeds=New-Object System.Collections.Generic.List[string]
  foreach($seed in @($env:RUNNER_WORKSPACE,$env:RUNNER_TEMP,$PWD.Path)){
    if(-not [string]::IsNullOrWhiteSpace([string]$seed)){[void]$seeds.Add([string]$seed)}
  }
  foreach($seed in $seeds){
    try{$current=(Resolve-Path -LiteralPath $seed).Path}catch{continue}
    while(-not [string]::IsNullOrWhiteSpace($current)){
      if(Test-Path -LiteralPath (Join-Path $current '.env') -PathType Leaf){return $current}
      $parent=Split-Path -Parent $current
      if([string]::IsNullOrWhiteSpace($parent) -or $parent-eq$current){break}
      $current=$parent
    }
  }
  throw 'unable to auto-discover self-hosted runner root; pass -RunnerRoot explicitly'
}

if([string]::IsNullOrWhiteSpace($OpenWorkerRepoRoot)){$OpenWorkerRepoRoot=$PSScriptRoot | Split-Path -Parent}
$OpenWorkerRepoRoot=(Resolve-Path -LiteralPath $OpenWorkerRepoRoot).Path

$srcPs=Join-Path $OpenWorkerRepoRoot 'scripts\openworker-job-started-hook.ps1'
$srcCmd=Join-Path $OpenWorkerRepoRoot 'scripts\openworker-job-started.cmd'
$srcDispatcher=Join-Path $OpenWorkerRepoRoot 'scripts\invoke-openworker-control-envelope-v1.ps1'
foreach($src in @($srcPs,$srcCmd,$srcDispatcher)){if(-not(Test-Path -LiteralPath $src -PathType Leaf)){throw "missing hook source: $src"}}

$dest=Join-Path $env:ProgramData 'OpenWorker\hooks'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -LiteralPath $srcPs -Destination (Join-Path $dest 'openworker-job-started-hook.ps1') -Force
Copy-Item -LiteralPath $srcCmd -Destination (Join-Path $dest 'openworker-job-started.cmd') -Force
Copy-Item -LiteralPath $srcDispatcher -Destination (Join-Path $dest 'invoke-openworker-control-envelope-v1.ps1') -Force

$deployed=@((Join-Path $dest 'openworker-job-started-hook.ps1'),(Join-Path $dest 'openworker-job-started.cmd'),(Join-Path $dest 'invoke-openworker-control-envelope-v1.ps1'))
foreach($path in $deployed){if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "deployed hook file missing: $path"}}

$hookPath='C:\ProgramData\OpenWorker\hooks\openworker-job-started.cmd'
$dispatcherPath='C:\ProgramData\OpenWorker\hooks\invoke-openworker-control-envelope-v1.ps1'

if($InstallFilesOnly){
  Write-Output ([ordered]@{
    schema='openworker.runner-hook-install.v2'
    mode='files-only'
    hook=$hookPath
    dispatcher=$dispatcherPath
    installed=$true
    configuration_verified=$false
    restart_required=$false
  } | ConvertTo-Json -Depth 5)
  exit 0
}

$RunnerRoot=Resolve-RunnerRoot $RunnerRoot
$envFile=Join-Path $RunnerRoot '.env'
$backup=$envFile+'.openworker-hook-backup-'+[DateTimeOffset]::Now.ToString('yyyyMMdd-HHmmss')
Copy-Item -LiteralPath $envFile -Destination $backup -Force

$lines=@(Get-Content -LiteralPath $envFile -ErrorAction Stop)
$found=$false
$out=New-Object System.Collections.Generic.List[string]
foreach($line in $lines){
  if($line -match '^ACTIONS_RUNNER_HOOK_JOB_STARTED='){$out.Add('ACTIONS_RUNNER_HOOK_JOB_STARTED='+$hookPath);$found=$true}else{$out.Add($line)}
}
if(-not $found){$out.Add('ACTIONS_RUNNER_HOOK_JOB_STARTED='+$hookPath)}

$tmp=$envFile+'.tmp.'+[Guid]::NewGuid().ToString('N')
[IO.File]::WriteAllLines($tmp,$out,[Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $tmp -Destination $envFile -Force
$configured=@(Get-Content -LiteralPath $envFile | Where-Object {$_ -eq ('ACTIONS_RUNNER_HOOK_JOB_STARTED='+$hookPath)})
if($configured.Count -ne 1){throw "runner hook configuration verification failed in $envFile"}

Write-Output ([ordered]@{
  schema='openworker.runner-hook-install.v2'
  mode='registered'
  runner_root=$RunnerRoot
  env_file=$envFile
  backup=$backup
  hook=$hookPath
  dispatcher=$dispatcherPath
  installed=$true
  configuration_verified=$true
  restart_required=$true
} | ConvertTo-Json -Depth 5)
