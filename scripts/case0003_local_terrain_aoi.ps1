param(
  [string]$OpenWorkerUrl = 'http://127.0.0.1:8787',
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine = 'DESKTOP-UL7V2VV',
  [string]$GoToolRoot = $env:GO_TOOL_ROOT,
  [string]$TerrainRoot = $env:TERRAIN_ROOT,
  [string]$ProjectId = 'OWJ-20260816030152-03D90D',
  [string]$AoiRadiusM = '1000',
  [string]$CatalogPath = 'D:\TaiwanDTM\catalog\dtm_catalog.sqlite',
  [string]$TargetCrs = 'EPSG:3826',
  [string]$VerticalDatum = 'TWVD2001',
  [string]$ResolutionMeters = '20'
)
$ErrorActionPreference='Stop'
if (-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong host expected=$Machine actual=$env:COMPUTERNAME" }
if ([string]::IsNullOrWhiteSpace($GoToolRoot)) { throw 'GO_TOOL_ROOT/GoToolRoot is required' }
if ([string]::IsNullOrWhiteSpace($TerrainRoot)) { throw 'TERRAIN_ROOT/TerrainRoot is required' }
if (-not (Test-Path -LiteralPath (Join-Path $GoToolRoot 'go.mod'))) { throw "invalid go-tool root: $GoToolRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $TerrainRoot 'go.mod'))) { throw "invalid Terrain root: $TerrainRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'geo\geolocation.json'))) { throw 'accepted geolocation missing' }
if (-not (Test-Path -LiteralPath $CatalogPath)) { throw "canonical terrain catalog missing: $CatalogPath" }
$claimDir=Join-Path $WorkspaceRoot '.openworker\localexec'
$evidenceDir=Join-Path $WorkspaceRoot 'evidence'
New-Item -ItemType Directory -Force -Path $claimDir,$evidenceDir | Out-Null
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$workId="case0003-terrain-aoi-$stamp"
$claimPath=Join-Path $claimDir ($workId+'.json')
$resultPath=Join-Path $evidenceDir ($workId+'-localexec-result.json')
$claim=[ordered]@{
  work_id=$workId
  assigned_host=$Machine
  capability_id='terrain.aoi.build'
  inputs=[ordered]@{
    workspace_root=$WorkspaceRoot
    assigned_host=$Machine
    project_id=$ProjectId
    aoi_radius_m=$AoiRadiusM
    catalog_path=$CatalogPath
    target_crs=$TargetCrs
    vertical_datum=$VerticalDatum
    resolution_meters=$ResolutionMeters
  }
  claimed_by='openworker-local-supervisor'
  lease_token=$workId
}
$claim|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $claimPath -Encoding utf8
$escapedGo=$GoToolRoot.Replace("'","''")
$escapedTerrain=$TerrainRoot.Replace("'","''")
$escapedClaim=$claimPath.Replace("'","''")
$escapedResult=$resultPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"`$env:TERRAIN_ROOT='$escapedTerrain'; Set-Location -LiteralPath '$escapedGo'; go run ./cmd/gtr-local-exec --claim '$escapedClaim' --timeout 20m | Set-Content -LiteralPath '$escapedResult' -Encoding utf8; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{
  job_id=$workId
  dispatch_id="case0003-terrain-aoi-local-$stamp"
  machine=$Machine
  priority=90
  cwd=$WorkspaceRoot
  workspace_root=$WorkspaceRoot
  timeout_sec=1260
  command=$cmd
  locks=@('case0003-terrain-aoi-local')
}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status"
$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents"
$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$receipt=[ordered]@{
  schema='openworker/case0003-local-terrain-aoi/v1'
  case_id='0003'
  machine=$Machine
  workspace_root=$WorkspaceRoot
  capability_id='terrain.aoi.build'
  transport='openworker-local-jobs+go-tool-localexec'
  github_business_transport=$false
  submitted_at=[DateTimeOffset]::UtcNow.ToString('o')
  node=$node
  agents=$agents
  durable_ack=$ack
}
$receiptPath=Join-Path $evidenceDir 'case0003-local-terrain-aoi-submit.json'
$receipt|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "CASE0003_LOCAL_TERRAIN_AOI_ACK work_id=$workId receipt=$receiptPath"
$ack|ConvertTo-Json -Depth 8|Write-Host
