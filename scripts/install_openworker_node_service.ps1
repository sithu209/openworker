# case0005-status-only-marker: read-bootstrap-1787079962903791900
param(
  [Parameter(Mandatory=$true)][string]$SourceExe,
  [string]$ServiceName='OpenWorkerNode',
  [string]$InstallDir='C:\ProgramData\OpenWorker\bin',
  [string]$DataDir='C:\ProgramData\OpenWorker\node',
  [string]$Listen='127.0.0.1:8787',
  [string]$Advertise='',
  [int]$Workers=4,
  [string]$Capabilities='',
  [string]$Peers=''
)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
$isAdmin=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $isAdmin){
  throw 'OpenWorker formal resident deployment requires an elevated administrator token. Detached-process fallback is not production authority.'
}
if(-not(Test-Path -LiteralPath $SourceExe -PathType Leaf)){throw "Source exe not found: $SourceExe"}
New-Item -ItemType Directory -Force -Path $InstallDir,$DataDir|Out-Null
$target=Join-Path $InstallDir 'openworker-node.exe'
$sourceHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $SourceExe).Hash.ToLowerInvariant()

function Get-HealthUrl([string]$addr){
  $port=[int]($addr.Split(':')[-1])
  return "http://127.0.0.1:$port/healthz"
}
function Wait-Health([string]$url){
  for($i=0;$i-lt 40;$i++){
    try{$h=Invoke-RestMethod -Uri $url -TimeoutSec 2;if($h.ok){return $h}}catch{}
    Start-Sleep -Milliseconds 500
  }
  throw "OpenWorker node health check failed: $url"
}

$svc=Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if($svc -and $svc.Status -ne 'Stopped'){
  Stop-Service -Name $ServiceName -Force
  $svc.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))
}
$targetFull=[IO.Path]::GetFullPath($target)
Get-CimInstance Win32_Process -Filter "Name='openworker-node.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $targetFull) } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
    Wait-Process -Id $_.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
  }
for($attempt=1;$attempt -le 30;$attempt++){
  try{Copy-Item -LiteralPath $SourceExe -Destination $target -Force;break}
  catch{if($attempt -eq 30){throw};Start-Sleep -Milliseconds 500}
}
$targetHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
if($targetHash -ne $sourceHash){throw "installed binary SHA256 mismatch source=$sourceHash target=$targetHash"}

$capArg='';if(-not[string]::IsNullOrWhiteSpace($Capabilities)){$capArg=' -capabilities "{0}"' -f $Capabilities.Replace('"','')}
$peerArg='';if(-not[string]::IsNullOrWhiteSpace($Peers)){$peerArg=' -peers "{0}"' -f $Peers.Replace('"','')}
$advArg='';if(-not[string]::IsNullOrWhiteSpace($Advertise)){$advArg=' -advertise "{0}"' -f $Advertise.Replace('"','')}
$bin='"{0}" -service -listen {1} -data "{2}" -workers {3}{4}{5}{6}' -f $target,$Listen,$DataDir,$Workers,$capArg,$peerArg,$advArg
if(-not $svc){
  sc.exe create $ServiceName binPath= $bin start= auto DisplayName= 'OpenWorker Local Execution Node'|Out-Host
  if($LASTEXITCODE-ne 0){throw "sc create failed rc=$LASTEXITCODE"}
}else{
  sc.exe config $ServiceName binPath= $bin start= auto|Out-Host
  if($LASTEXITCODE-ne 0){throw "sc config failed rc=$LASTEXITCODE"}
}
sc.exe failure $ServiceName reset=86400 actions=restart/5000/restart/15000/restart/60000|Out-Host
if($LASTEXITCODE-ne 0){throw "sc failure failed rc=$LASTEXITCODE"}
sc.exe failureflag $ServiceName 1|Out-Host
if($LASTEXITCODE-ne 0){throw "sc failureflag failed rc=$LASTEXITCODE"}
Start-Service -Name $ServiceName
$svc=Get-Service -Name $ServiceName
$svc.WaitForStatus('Running',[TimeSpan]::FromSeconds(30))
$svcInfo=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if(-not $svcInfo){throw "Win32_Service missing: $ServiceName"}
if($svcInfo.State -ne 'Running'){throw "service state=$($svcInfo.State)"}
if($svcInfo.StartMode -notin @('Auto','Automatic')){throw "service start mode=$($svcInfo.StartMode)"}
if($svcInfo.PathName -notlike "*$target*"){throw "service binary path does not point to formal target: $($svcInfo.PathName)"}
$h=Wait-Health (Get-HealthUrl $Listen)
[ordered]@{
  schema='openworker.windows-service-install.v6'
  mode='windows_service'
  production_ready=$true
  administrator=$true
  detached_fallback_allowed=$false
  service=$ServiceName
  status=$svcInfo.State
  start_mode=$svcInfo.StartMode
  service_account=$svcInfo.StartName
  service_path=$svcInfo.PathName
  exe=$target
  exe_sha256=$targetHash
  source_sha256=$sourceHash
  data_dir=$DataDir
  listen=$Listen
  advertise=$Advertise
  workers=$Workers
  capabilities=$Capabilities
  peers=$Peers
  machine=$env:COMPUTERNAME
  health=$h
}|ConvertTo-Json -Depth 8
