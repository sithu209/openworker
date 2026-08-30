param(
  [string]$OpenWorkerUrl = 'http://127.0.0.1:8787',
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0005-SNOW-WHITE',
  [string]$Machine = 'DESKTOP-ODAQN0D'
)
$ErrorActionPreference='Stop'
if (-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong host expected=$Machine actual=$env:COMPUTERNAME" }

$repo = (Resolve-Path $PSScriptRoot\..).Path
$manifest = Join-Path $repo 'case-worklists\0005.json'
$spec = Join-Path $repo 'case-specs\0005.json'
if(-not (Test-Path -LiteralPath $manifest)){ throw "missing Case 0005 manifest: $manifest" }
if(-not (Test-Path -LiteralPath $spec)){ throw "missing Case 0005 spec: $spec" }

$node = Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status"
if(-not $node.online){ throw 'OpenWorker node is not online' }
if(-not ([string]$node.machine).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){ throw "OpenWorker node mismatch actual=$($node.machine)" }

function Resolve-RepoRoot([string]$Name,[string[]]$Markers){
  $candidates=@(
    (Join-Path 'D:\actions-runner\_work' "$Name\$Name"),
    (Join-Path 'D:\AI' $Name),
    (Join-Path 'D:\AIWork' $Name),
    (Join-Path 'D:\PyWork' $Name)
  )
  foreach($c in $candidates){
    if(-not (Test-Path -LiteralPath $c -PathType Container)){ continue }
    $ok=$true
    foreach($m in $Markers){ if(-not (Test-Path -LiteralPath (Join-Path $c $m))){ $ok=$false; break } }
    if($ok){ return (Resolve-Path $c).Path }
  }
  $roots=@('D:\actions-runner\_work','D:\AI','D:\AIWork','D:\PyWork') | Where-Object { Test-Path -LiteralPath $_ }
  foreach($base in $roots){
    $dirs=Get-ChildItem -LiteralPath $base -Directory -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq $Name } | Select-Object -First 8
    foreach($d in $dirs){
      $ok=$true
      foreach($m in $Markers){ if(-not (Test-Path -LiteralPath (Join-Path $d.FullName $m))){ $ok=$false; break } }
      if($ok){ return $d.FullName }
    }
  }
  throw "local checkout not found for $Name markers=$($Markers -join ',')"
}

function Resolve-RepoRootAlias([string[]]$Names,[string[]]$Markers){
  $errors=@()
  foreach($name in $Names){
    try { return Resolve-RepoRoot $name $Markers }
    catch { $errors += $_.Exception.Message }
  }
  throw "local checkout not found for aliases=$($Names -join ',') markers=$($Markers -join ',') errors=$($errors -join ' | ')"
}

$env:OPENWORKER_ROOT=$repo
$env:GO_TOOL_ROOT=Resolve-RepoRoot 'go-tool-runtime' @('go.mod','cmd\gtr-local-exec\main.go')
$env:COMFYX_ROOT=Resolve-RepoRoot 'ComfyX' @('go.mod','cmd\comfyx-synthesis-video-real')
$env:COMFYX_STUDIO_ROOT=Resolve-RepoRoot 'Comfyx-Studio' @('go.mod','cmd\operator-director-preproduction')
$env:OPENMAIC_ROOT=Resolve-RepoRootAlias @('OpenMAIC','openmaic-fork') @('package.json','src\cli\presentation.ts')

if(-not $env:COMFYX_COMFYUI_OUTPUT_ROOT){
  $outputCandidates=@(
    'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\output',
    'D:\ComfyUI\output'
  )
  foreach($p in $outputCandidates){ if(Test-Path -LiteralPath $p -PathType Container){ $env:COMFYX_COMFYUI_OUTPUT_ROOT=$p; break } }
}
if(-not $env:COMFYX_COMFYUI_OUTPUT_ROOT){ throw 'COMFYX_COMFYUI_OUTPUT_ROOT authority not found on ODA' }

New-Item -ItemType Directory -Force -Path $WorkspaceRoot,(Join-Path $WorkspaceRoot 'evidence') | Out-Null

# Compile the exact local executor before mutating the durable CaseWorklist.
Push-Location $env:GO_TOOL_ROOT
try {
  $exe=Join-Path $WorkspaceRoot '.openworker\bin\gtr-local-exec.exe'
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $exe) | Out-Null
  go build -trimpath -o $exe ./cmd/gtr-local-exec
  if($LASTEXITCODE -ne 0){ throw "gtr-local-exec build failed rc=$LASTEXITCODE" }
  $env:GTR_LOCAL_EXEC_EXE=$exe
} finally { Pop-Location }

# One bootstrap transport only. Business execution after this point is local durable jobs.
# Case 0005 uses a dedicated subclass so its visual role fan-out does not leak
# into generic CaseWorklist orchestration used by other cases.
Push-Location $repo
try {
  $json = python -m coworker.case0005_controller --node-url $OpenWorkerUrl bootstrap --workspace $WorkspaceRoot --manifest $manifest --spec $spec
  if($LASTEXITCODE -ne 0){ throw "Case 0005 controller bootstrap failed rc=$LASTEXITCODE" }
} finally { Pop-Location }

$controller = $json | ConvertFrom-Json
$receipt=[ordered]@{
  schema='openworker/case0005-local-first-bootstrap/v4';
  case_id='0005'; machine=$Machine; workspace_root=$WorkspaceRoot;
  transport_run_id=$env:GITHUB_RUN_ID; submitted_at=[DateTimeOffset]::UtcNow.ToString('o');
  node=$node;
  roots=[ordered]@{
    openworker=$env:OPENWORKER_ROOT; go_tool=$env:GO_TOOL_ROOT; comfyx=$env:COMFYX_ROOT;
    comfyx_studio=$env:COMFYX_STUDIO_ROOT; openmaic=$env:OPENMAIC_ROOT; comfyui_output=$env:COMFYX_COMFYUI_OUTPUT_ROOT
  };
  controller=$controller;
  github_action_used_for_business_execution=$false
}
$receiptPath=Join-Path $WorkspaceRoot 'evidence\case0005-local-first-bootstrap.json'
$receipt|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "CASE0005_LOCAL_FIRST_BOOTSTRAP receipt=$receiptPath"
$receipt|ConvertTo-Json -Depth 20|Write-Host
