param(
  [Parameter(Mandatory=$true)][string]$Binary,
  [string]$Listen = '127.0.0.1:8787',
  [int]$Workers = 4,
  [string]$Data = 'C:\ProgramData\DirectWork\node',
  [string]$Peers = ''
)
$ErrorActionPreference='Stop'
$service='DirectWorkNode'
$root='C:\ProgramData\DirectWork'
$binDir=Join-Path $root 'bin'
New-Item -ItemType Directory -Force -Path $binDir,$Data | Out-Null
$target=Join-Path $binDir 'directwork-node.exe'
if ((Resolve-Path $Binary).Path -ne $target) { Copy-Item -Force $Binary $target }
if (Get-Service $service -ErrorAction SilentlyContinue) {
  Stop-Service $service -Force -ErrorAction SilentlyContinue
  sc.exe delete $service | Out-Null
  Start-Sleep -Seconds 1
}
$binPath='"{0}" -service -listen {1} -workers {2} -data "{3}"' -f $target,$Listen,$Workers,$Data
if ($Peers) { $binPath += ' -peers "'+$Peers+'"' }
sc.exe create $service binPath= $binPath start= auto DisplayName= 'DirectWork Node' | Out-Null
sc.exe description $service 'DirectWork durable local work commander node' | Out-Null
Start-Service $service

$verifyListen=$Listen
if ($verifyListen -match '^(0\.0\.0\.0|\[?::\]?):(\d+)$') {
  $verifyListen='127.0.0.1:'+$Matches[2]
}
$verifyUri='http://'+$verifyListen+'/v1/node/status'
$deadline=(Get-Date).AddSeconds(30)
$status=$null
do {
  Start-Sleep -Milliseconds 500
  try { $status=Invoke-RestMethod -Uri $verifyUri -TimeoutSec 2; break } catch {}
} while ((Get-Date) -lt $deadline)
if (-not $status -or -not $status.online) { throw "DirectWorkNode did not become healthy via $verifyUri" }
$status | ConvertTo-Json -Depth 8
