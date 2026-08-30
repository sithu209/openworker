param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$GoToolRoot=$env:GO_TOOL_ROOT,
  [string]$TerrainRoot=$env:TERRAIN_ROOT
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
if([string]::IsNullOrWhiteSpace($GoToolRoot)){throw 'GO_TOOL_ROOT/GoToolRoot is required'}
if([string]::IsNullOrWhiteSpace($TerrainRoot)){throw 'TERRAIN_ROOT/TerrainRoot is required'}
if(-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'terrain\terrain-context.json'))){throw 'accepted terrain context missing'}
$claimDir=Join-Path $WorkspaceRoot '.openworker\localexec';$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $claimDir,$evidenceDir|Out-Null
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-terrain-consumer-$stamp";$claimPath=Join-Path $claimDir ($workId+'.json');$resultPath=Join-Path $evidenceDir ($workId+'-localexec-result.json')
[ordered]@{work_id=$workId;assigned_host=$Machine;capability_id='terrain.consumer.orchestrate';inputs=[ordered]@{workspace_root=$WorkspaceRoot;assigned_host=$Machine};claimed_by='openworker-local-supervisor';lease_token=$workId}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $claimPath -Encoding utf8
$escapedGo=$GoToolRoot.Replace("'","''");$escapedTerrain=$TerrainRoot.Replace("'","''");$escapedClaim=$claimPath.Replace("'","''");$escapedResult=$resultPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"`$env:TERRAIN_ROOT='$escapedTerrain'; Set-Location -LiteralPath '$escapedGo'; go run ./cmd/gtr-local-exec --claim '$escapedClaim' --timeout 20m | Set-Content -LiteralPath '$escapedResult' -Encoding utf8; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{job_id=$workId;dispatch_id="case0003-terrain-consumer-local-$stamp";machine=$Machine;priority=88;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=1260;command=$cmd;locks=@('case0003-terrain-consumer-local')}
$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
[ordered]@{schema='openworker/case0003-local-consumer/v1';case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;capability_id='terrain.consumer.orchestrate';transport='openworker-local-jobs+go-tool-localexec';github_business_transport=$false;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');durable_ack=$ack}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-local-consumer-submit.json') -Encoding utf8
$ack|ConvertTo-Json -Depth 8|Write-Host
