param(
  [Parameter(Mandatory=$true)][string]$Binary,
  [Parameter(Mandatory=$true)][string]$ExpectedMachine,
  [Parameter(Mandatory=$true)][string]$NodeKey,
  [Parameter(Mandatory=$true)][string]$TargetCommit,
  [Parameter(Mandatory=$true)][string]$RunId,
  [string]$Peers = ''
)

$ErrorActionPreference = 'Stop'
$oldService = 'OpenWorkerNode'
$newService = 'DirectWorkNode'
$oldWasRunning = $false

function Wait-Work([string]$WorkId) {
  $deadline = (Get-Date).AddSeconds(90)
  do {
    Start-Sleep -Milliseconds 500
    $w = Invoke-RestMethod -Uri ("http://127.0.0.1:8787/v1/work/{0}" -f $WorkId) -TimeoutSec 3
    if ($w.status -in @('succeeded','failed','timed_out','cancelled')) { return $w }
  } while ((Get-Date) -lt $deadline)
  throw "smoke work timeout: $WorkId"
}

try {
  if ($env:COMPUTERNAME -ne $ExpectedMachine) { throw "wrong computer: expected=$ExpectedMachine actual=$env:COMPUTERNAME" }
  $old = Get-Service $oldService -ErrorAction SilentlyContinue
  if ($old -and $old.Status -eq 'Running') { $oldWasRunning = $true; Stop-Service $oldService -Force }
  & "$PSScriptRoot\install-directwork-node.ps1" -Binary $Binary -Listen '0.0.0.0:8787' -Workers 4 -Peers $Peers
  $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/v1/node/status' -TimeoutSec 5
  if (-not $status.online) { throw 'DirectWork node is not online' }
  if ($status.machine -ne $ExpectedMachine) { throw "machine mismatch in node status: $($status.machine)" }
  if ($status.commit -ne $TargetCommit) { throw "running commit mismatch: $($status.commit) != $TargetCommit" }
  $workspace = Join-Path 'C:\ProgramData\DirectWork\smoke' ("{0}-{1}" -f $NodeKey,$RunId)
  New-Item -ItemType Directory -Force -Path $workspace | Out-Null
  $body = @{dispatch_id="deploy-$RunId-$NodeKey";case_id='DIRECTWORK-REAL-SMOKE';project='DirectWork';machine=$ExpectedMachine;command='echo DirectWork REAL smoke > directwork-smoke.txt';cwd=$workspace;workspace_root=$workspace;timeout_sec=60} | ConvertTo-Json -Depth 6
  $created = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8787/v1/work' -ContentType 'application/json' -Body $body -TimeoutSec 5
  if (-not $created.work_id) { throw 'durable work_id missing' }
  $work = Wait-Work $created.work_id
  if ($work.status -ne 'succeeded') { throw "smoke work failed: status=$($work.status) exit=$($work.exit_code)" }
  if ($work.exit_code -ne 0) { throw "smoke exit_code=$($work.exit_code)" }
  if (-not $work.slot -or $work.slot -lt 1) { throw 'slot evidence missing' }
  if (-not $work.pid -or $work.pid -lt 1) { throw 'pid evidence missing' }
  $eventResult = Invoke-RestMethod -Uri ("http://127.0.0.1:8787/v1/work/{0}/events" -f $created.work_id) -TimeoutSec 5
  $types = @($eventResult.events | ForEach-Object { $_.type })
  foreach ($required in @('accepted','claimed','running','succeeded')) { if ($types -notcontains $required) { throw "missing lifecycle event: $required" } }
  $artifactResult = Invoke-RestMethod -Uri ("http://127.0.0.1:8787/v1/work/{0}/artifacts" -f $created.work_id) -TimeoutSec 10
  $artifact = @($artifactResult.artifacts | Where-Object { $_.relative_path -eq 'directwork-smoke.txt' }) | Select-Object -First 1
  if (-not $artifact) { throw 'smoke artifact missing' }
  if ($artifact.size -le 0) { throw 'smoke artifact is empty' }
  if (-not $artifact.sha256) { throw 'smoke artifact SHA256 missing' }
  $nodes = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/v1/nodes' -TimeoutSec 5
  $receipt = [ordered]@{schema='directwork/node-verification-receipt/v1';verified=$true;node=$NodeKey;machine=$ExpectedMachine;run_id=$RunId;target_commit=$TargetCommit;running_commit=$status.commit;service=$newService;work_id=$work.work_id;work_status=$work.status;slot=$work.slot;pid=$work.pid;exit_code=$work.exit_code;lifecycle_events=$types;artifact=[ordered]@{relative_path=$artifact.relative_path;path=$artifact.path;size=$artifact.size;sha256=$artifact.sha256};peers=$nodes.peers;verified_at=(Get-Date).ToUniversalTime().ToString('o')}
  $receiptDir = Join-Path $env:GITHUB_WORKSPACE ("verification-receipts\{0}" -f $RunId)
  New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null
  $receiptPath = Join-Path $receiptDir ("{0}.json" -f $NodeKey)
  $receipt | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $receiptPath
  Write-Host "DIRECTWORK_VERIFIED $NodeKey $($work.work_id)"
}
catch {
  Write-Error $_
  $svc = Get-Service $newService -ErrorAction SilentlyContinue
  if ($svc) { Stop-Service $newService -Force -ErrorAction SilentlyContinue; sc.exe delete $newService | Out-Null }
  if ($oldWasRunning) { Start-Service $oldService -ErrorAction SilentlyContinue }
  throw
}
