param(
  [Parameter(Mandatory=$true)][string]$JobId,
  [Parameter(Mandatory=$true)][string]$DispatchId,
  [Parameter(Mandatory=$true)][string]$ExpectedComputerName,
  [Parameter(Mandatory=$true)][string]$Command,
  [string]$Cwd = $env:GITHUB_WORKSPACE,
  [string]$WorkspaceRoot = "",
  [string]$NodeUrl = "http://127.0.0.1:8787",
  [int]$TimeoutSec = 3600,
  [string[]]$Locks = @(),
  [switch]$UseWorktree,
  [string]$WorktreeRef = "HEAD",
  [string]$ReceiptPath = ""
)

$ErrorActionPreference = 'Stop'
$actual = $env:COMPUTERNAME
if ([string]::IsNullOrWhiteSpace($actual)) { $actual = [System.Environment]::MachineName }
if ($actual -ine $ExpectedComputerName) {
  throw "OPENWORKER_MACHINE_MISMATCH expected=$ExpectedComputerName actual=$actual"
}
if ([string]::IsNullOrWhiteSpace($Cwd) -or -not (Test-Path -LiteralPath $Cwd -PathType Container)) {
  throw "OPENWORKER_INVALID_CWD cwd=$Cwd"
}

$body = [ordered]@{
  job_id = $JobId
  dispatch_id = $DispatchId
  machine = $ExpectedComputerName
  command = $Command
  cwd = $Cwd
  workspace_root = $WorkspaceRoot
  timeout_sec = $TimeoutSec
  locks = @($Locks)
  use_worktree = [bool]$UseWorktree
  worktree_ref = $WorktreeRef
  env = [ordered]@{
    GITHUB_RUN_ID = $env:GITHUB_RUN_ID
    GITHUB_RUN_ATTEMPT = $env:GITHUB_RUN_ATTEMPT
    GITHUB_REPOSITORY = $env:GITHUB_REPOSITORY
    GITHUB_SHA = $env:GITHUB_SHA
  }
}
$json = $body | ConvertTo-Json -Depth 8 -Compress
$ack = Invoke-RestMethod -Method Post -Uri "$NodeUrl/v1/jobs" -ContentType 'application/json' -Body $json
if (-not $ack.accepted) { throw "OPENWORKER_NODE_DID_NOT_ACCEPT job_id=$JobId" }
if ($ack.job_id -ne $JobId -or $ack.dispatch_id -ne $DispatchId) {
  throw "OPENWORKER_ACK_ID_MISMATCH expected=$JobId/$DispatchId got=$($ack.job_id)/$($ack.dispatch_id)"
}

$receipt = [ordered]@{
  schema = 'openworker.action-dispatch-receipt.v1'
  job_id = $ack.job_id
  dispatch_id = $ack.dispatch_id
  machine = $ack.machine
  accepted = [bool]$ack.accepted
  accepted_at = $ack.accepted_at
  queue_position = $ack.queue_position
  duplicate = [bool]$ack.duplicate
  github_run_id = $env:GITHUB_RUN_ID
  github_run_attempt = $env:GITHUB_RUN_ATTEMPT
  github_sha = $env:GITHUB_SHA
}
$out = $receipt | ConvertTo-Json -Depth 6
if (-not [string]::IsNullOrWhiteSpace($ReceiptPath)) {
  $parent = Split-Path -Parent $ReceiptPath
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  [System.IO.File]::WriteAllText($ReceiptPath, $out, [System.Text.UTF8Encoding]::new($false))
}
Write-Output $out
