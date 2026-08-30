param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$GoToolRoot=$env:GO_TOOL_ROOT,
  [string]$SceneXRoot=$env:SCENEX_ROOT
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
if([string]::IsNullOrWhiteSpace($GoToolRoot)){throw 'GO_TOOL_ROOT/GoToolRoot is required'}
if([string]::IsNullOrWhiteSpace($SceneXRoot)){throw 'SCENEX_ROOT/SceneXRoot is required'}
if(-not(Test-Path -LiteralPath (Join-Path $GoToolRoot 'go.mod'))){throw "invalid go-tool root: $GoToolRoot"}
if(-not(Test-Path -LiteralPath (Join-Path $SceneXRoot 'godot\project.godot'))){throw "invalid SceneX root: $SceneXRoot"}
foreach($rel in @('terrain\terrain-grid.json','terrain\terrain-context.json','geo\geolocation.json')){if(-not(Test-Path -LiteralPath (Join-Path $WorkspaceRoot $rel) -PathType Leaf) -or (Get-Item -LiteralPath (Join-Path $WorkspaceRoot $rel)).Length -le 0){throw "required SceneX input missing/empty: $rel"}}
$claimDir=Join-Path $WorkspaceRoot '.openworker\localexec';$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $claimDir,$evidenceDir|Out-Null
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-scenex-$stamp";$claimPath=Join-Path $claimDir ($workId+'.json');$resultPath=Join-Path $evidenceDir ($workId+'-localexec-result.json')
$claim=[ordered]@{work_id=$workId;assigned_host=$Machine;capability_id='scenex.terrain.real_browse';inputs=[ordered]@{workspace_root=$WorkspaceRoot;assigned_host=$Machine;terrain_grid_relpath='terrain\terrain-grid.json';terrain_context_relpath='terrain\terrain-context.json';geolocation_relpath='geo\geolocation.json'};claimed_by='openworker-local-supervisor';lease_token=$workId}
$claim|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $claimPath -Encoding utf8
$escapedGo=$GoToolRoot.Replace("'","''");$escapedSceneX=$SceneXRoot.Replace("'","''");$escapedClaim=$claimPath.Replace("'","''");$escapedResult=$resultPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"`$env:SCENEX_ROOT='$escapedSceneX'; Set-Location -LiteralPath '$escapedGo'; go run ./cmd/gtr-local-exec --claim '$escapedClaim' --timeout 12m | Set-Content -LiteralPath '$escapedResult' -Encoding utf8; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{job_id=$workId;dispatch_id="case0003-scenex-local-$stamp";machine=$Machine;priority=80;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=780;command=$cmd;locks=@('case0003-scenex-local')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$receipt=[ordered]@{schema='openworker/case0003-local-scenex/v1';case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;capability_id='scenex.terrain.real_browse';transport='openworker-local-jobs+go-tool-localexec';github_business_transport=$false;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$receiptPath=Join-Path $evidenceDir 'case0003-local-scenex-submit.json';$receipt|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "CASE0003_LOCAL_SCENEX_ACK work_id=$workId receipt=$receiptPath";$ack|ConvertTo-Json -Depth 8|Write-Host
