$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ine 'DESKTOP-ODAQN0D'){throw "wrong host $env:COMPUTERNAME"}

$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cwd='D:\AI-Work\runtime\openworker'
$workspace='D:\AI-Work\jobs\0005-SNOW-WHITE'
$python='C:\Python314\python.exe'
$svc=Get-CimInstance Win32_Service -Filter "Name='OpenWorkerNode'" -ErrorAction SilentlyContinue

function ItemInfo([string]$p){
  if(-not(Test-Path -LiteralPath $p)){return [ordered]@{path=$p;exists=$false}}
  $i=Get-Item -LiteralPath $p -Force
  return [ordered]@{path=$p;exists=$true;full_name=$i.FullName;attributes=[string]$i.Attributes;link_type=[string]$i.LinkType;target=@($i.Target)}
}

function RunProbe([string]$mode){
  $psi=[Diagnostics.ProcessStartInfo]::new()
  $psi.UseShellExecute=$false
  $psi.RedirectStandardOutput=$true
  $psi.RedirectStandardError=$true
  $psi.CreateNoWindow=$true
  $psi.WorkingDirectory=$cwd
  if($mode -eq 'direct'){
    $psi.FileName=$python
    $psi.ArgumentList.Add('-c')
    $psi.ArgumentList.Add('import os,sys;print(os.getcwd());print(sys.executable)')
  }else{
    $psi.FileName='cmd.exe'
    $psi.ArgumentList.Add('/D')
    $psi.ArgumentList.Add('/S')
    $psi.ArgumentList.Add('/C')
    $psi.ArgumentList.Add('"'+$python+'" -c "import os,sys;print(os.getcwd());print(sys.executable)"')
  }
  try{
    $p=[Diagnostics.Process]::Start($psi)
    $stdout=$p.StandardOutput.ReadToEnd();$stderr=$p.StandardError.ReadToEnd();$p.WaitForExit()
    return [ordered]@{mode=$mode;started=$true;exit_code=$p.ExitCode;stdout=$stdout;stderr=$stderr}
  }catch{
    return [ordered]@{mode=$mode;started=$false;exit_code=-1;stdout='';stderr=$_.Exception.ToString()}
  }
}

$result=[ordered]@{
  schema='openworker.case0005-runtime-probe/v1'
  case_id='0005'
  machine=$env:COMPUTERNAME
  runner_name=$env:RUNNER_NAME
  identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  cwd=(ItemInfo $cwd)
  workspace=(ItemInfo $workspace)
  python=(ItemInfo $python)
  service=if($svc){[ordered]@{name=$svc.Name;state=$svc.State;start_name=$svc.StartName;path_name=$svc.PathName}}else{$null}
  direct_python=(RunProbe 'direct')
  cmd_python=(RunProbe 'cmd')
  github_run_id=$env:GITHUB_RUN_ID
  github_action_used_for_business_execution=$false
  observed_at=[DateTimeOffset]::UtcNow.ToString('o')
}

$rel='case-evidence/case0005-runtime-probe/latest.json'
$path=Join-Path $repoRoot $rel
New-Item -ItemType Directory -Force -Path (Split-Path $path -Parent)|Out-Null
$json=$result|ConvertTo-Json -Depth 30
[IO.File]::WriteAllText($path,$json+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host ($result|ConvertTo-Json -Depth 30 -Compress)
Push-Location $repoRoot
try{
  git config user.name 'openworker-runtime-probe'
  git config user.email 'openworker-runtime-probe@users.noreply.github.com'
  git add -- $rel
  git commit -m "receipt: Case0005 runtime probe $env:GITHUB_RUN_ID"
  if($LASTEXITCODE -ne 0){throw 'failed to commit runtime probe'}
  git pull --rebase origin main
  if($LASTEXITCODE -ne 0){throw 'failed to rebase runtime probe'}
  git push origin HEAD:main
  if($LASTEXITCODE -ne 0){throw 'failed to push runtime probe'}
}finally{Pop-Location}
