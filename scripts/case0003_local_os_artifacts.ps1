param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$GoToolRoot=$env:GO_TOOL_ROOT,
  [string]$EngineeringOSRoot=$env:ENGINEERING_OS_ROOT,
  [string]$OSProjectId=$env:ENGINEERING_OS_PROJECT_ID,
  [string]$OSJobId=$env:ENGINEERING_OS_JOB_ID
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
foreach($pair in @(@('GO_TOOL_ROOT',$GoToolRoot),@('ENGINEERING_OS_ROOT',$EngineeringOSRoot),@('ENGINEERING_OS_PROJECT_ID',$OSProjectId),@('ENGINEERING_OS_JOB_ID',$OSJobId))){if([string]::IsNullOrWhiteSpace([string]$pair[1])){throw "$($pair[0]) is required"}}
if(-not(Test-Path -LiteralPath (Join-Path $GoToolRoot 'go.mod'))){throw "invalid go-tool root: $GoToolRoot"}
if(-not(Test-Path -LiteralPath (Join-Path $EngineeringOSRoot 'go.mod'))){throw "invalid Engineering OS root: $EngineeringOSRoot"}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';$claimDir=Join-Path $WorkspaceRoot '.openworker\localexec';New-Item -ItemType Directory -Force -Path $evidenceDir,$claimDir|Out-Null
function Add-Artifact([System.Collections.ArrayList]$items,[string]$rel,[string]$kind,[string]$media,[string]$component,[string]$repo,[string]$commit=''){
  $path=[IO.Path]::GetFullPath((Join-Path $WorkspaceRoot $rel));$root=[IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd('\')
  if(-not $path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw "artifact escapes workspace: $rel"}
  if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -le 0){throw "required artifact missing/empty: $path"}
  $sha=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  $x=[ordered]@{kind=$kind;component_id=$component;source_uri=$path;media_type=$media;expected_sha256=$sha;source_run_id='case0003-local-first'}
  if(-not[string]::IsNullOrWhiteSpace($repo) -and -not[string]::IsNullOrWhiteSpace($commit)){$x.producer_repository=$repo;$x.producer_commit_sha=$commit}
  [void]$items.Add($x)
}
$renderAcceptancePath=Join-Path $WorkspaceRoot 'acceptance\render\render-acceptance.json'
if(-not(Test-Path -LiteralPath $renderAcceptancePath -PathType Leaf)){throw 'current render acceptance is required before OS ingest'}
$render=Get-Content -LiteralPath $renderAcceptancePath -Raw|ConvertFrom-Json
if([string]$render.schema_version -ne 'openworker-case0003-render-acceptance/v1' -or [string]$render.status -ne 'RENDER_ACCEPTED_PENDING_CASE_COMPLETION'){throw 'render acceptance schema/status rejected'}
foreach($field in @('fingerprint','blender_fingerprint','scenex_fingerprint')){if([string]::IsNullOrWhiteSpace([string]$render.$field)){throw "render acceptance missing $field"}}
$blenderWorkspace=Join-Path $WorkspaceRoot 'blender\blender-workspace.json';$sceneXManifest=Join-Path $WorkspaceRoot 'scenex\scenex-workspace.json'
if(-not(Test-Path -LiteralPath $blenderWorkspace -PathType Leaf)){throw 'Blender workspace v2 gate is not complete'}
if(-not(Test-Path -LiteralPath $sceneXManifest -PathType Leaf)){throw 'SceneX workspace v2 gate is not complete'}
$bw=Get-Content -LiteralPath $blenderWorkspace -Raw|ConvertFrom-Json;if([string]$bw.schema_version -ne 'blender-workspace/v2' -or -not $bw.ok -or [string]$bw.blender_fingerprint -ne [string]$render.blender_fingerprint){throw 'Blender current render binding rejected'}
$sx=Get-Content -LiteralPath $sceneXManifest -Raw|ConvertFrom-Json;if([string]$sx.schema_version -ne 'scenex-workspace-browse/v2' -or -not $sx.ok -or [string]$sx.scenex_fingerprint -ne [string]$render.scenex_fingerprint -or [int]$sx.active_chunks -le 0 -or [int]$sx.terrain_geometry_count -le 0){throw 'SceneX current render binding rejected'}
$items=[System.Collections.ArrayList]::new()
Add-Artifact $items 'terrain\terrain-context.json' 'terrain_context' 'application/json' 'terrain' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'terrain\terrain-grid.json' 'terrain_grid' 'application/json' 'terrain' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'terrain\terrain.obj' 'terrain_mesh_obj' 'model/obj' 'terrain' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'terrain\terrain-scene.json' 'terrain_scene' 'application/json' 'terrain' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'blender\terrain-scene.blend' 'terrain_blender_scene' 'application/octet-stream' 'blender' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'blender\terrain-render.png' 'terrain_blender_render_png' 'image/png' 'blender' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'blender\blender-scene-evidence.json' 'terrain_blender_evidence' 'application/json' 'blender' 'liuxb99/Terrain_To_DXF'
Add-Artifact $items 'scenex\terrain.region.json' 'scenex_terrain_region_pack' 'application/json' 'scenex' 'liuxb99/SceneX'
Add-Artifact $items 'scenex\terrain-browse.png' 'scenex_terrain_browse_png' 'image/png' 'scenex' 'liuxb99/SceneX'
Add-Artifact $items 'scenex\terrain-browse-evidence.json' 'scenex_terrain_browse_evidence' 'application/json' 'scenex' 'liuxb99/SceneX'
Add-Artifact $items 'scenex\scenex-workspace.json' 'scenex_workspace_manifest' 'application/json' 'scenex' 'liuxb99/SceneX'
$binding=[ordered]@{render_fingerprint=[string]$render.fingerprint;blender_fingerprint=[string]$render.blender_fingerprint;scenex_fingerprint=[string]$render.scenex_fingerprint}
$manifest=[ordered]@{schema_version='artifact-ingest/v2';project_id=$OSProjectId;job_id=$OSJobId;source_binding=$binding;artifacts=$items}
$manifestPath=Join-Path $evidenceDir 'case0003-os-artifact-ingest.json';$manifest|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $manifestPath -Encoding utf8
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$workId="case0003-os-artifacts-$stamp";$claimPath=Join-Path $claimDir ($workId+'.json');$resultPath=Join-Path $evidenceDir ($workId+'-localexec-result.json')
$claim=[ordered]@{work_id=$workId;assigned_host=$Machine;capability_id='engineering_os.artifacts.ingest';inputs=[ordered]@{workspace_root=$WorkspaceRoot;assigned_host=$Machine;project_id=$OSProjectId;job_id=$OSJobId};claimed_by='openworker-local-supervisor';lease_token=$workId}
$claim|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $claimPath -Encoding utf8
$escapedGo=$GoToolRoot.Replace("'","''");$escapedOS=$EngineeringOSRoot.Replace("'","''");$escapedClaim=$claimPath.Replace("'","''");$escapedResult=$resultPath.Replace("'","''")
$cmd="powershell -NoProfile -ExecutionPolicy Bypass -Command `"`$env:ENGINEERING_OS_ROOT='$escapedOS'; Set-Location -LiteralPath '$escapedGo'; go run ./cmd/gtr-local-exec --claim '$escapedClaim' --timeout 10m | Set-Content -LiteralPath '$escapedResult' -Encoding utf8; if(`$LASTEXITCODE -ne 0){exit `$LASTEXITCODE}`""
$job=@{job_id=$workId;dispatch_id="case0003-os-artifacts-local-$stamp";machine=$Machine;priority=75;cwd=$WorkspaceRoot;workspace_root=$WorkspaceRoot;timeout_sec=660;command=$cmd;locks=@('case0003-engineering-os-artifacts')}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status";$agents=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/cluster/agents";$ack=Invoke-RestMethod -Method Post -Uri "$OpenWorkerUrl/v1/jobs" -ContentType 'application/json' -Body ($job|ConvertTo-Json -Depth 8 -Compress)
$receipt=[ordered]@{schema='openworker/case0003-os-artifacts-submit/v2';case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;os_project_id=$OSProjectId;os_job_id=$OSJobId;source_binding=$binding;artifact_count=$items.Count;transport='openworker-local-jobs+go-tool-localexec';github_business_transport=$false;submitted_at=[DateTimeOffset]::UtcNow.ToString('o');node=$node;agents=$agents;durable_ack=$ack}
$receiptPath=Join-Path $evidenceDir 'case0003-os-artifacts-submit.json';$receipt|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $receiptPath -Encoding utf8
$receipt|ConvertTo-Json -Depth 12|Write-Host
