param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$OpenWorkerRoot='',
  [string]$DriveSyncRoot='',
  [string]$GoToolRoot='',
  [string]$TerrainRoot='',
  [string]$SceneXRoot='',
  [string]$EngineeringOSRoot='',
  [string]$OSProjectId='',
  [string]$OSJobId='',
  [string]$EngineeringOSBaseUrl='http://127.0.0.1:8080',
  [string]$CatalogPath='D:\TaiwanDTM\catalog\dtm_catalog.sqlite'
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
$scriptRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
if([string]::IsNullOrWhiteSpace($OpenWorkerRoot)){$OpenWorkerRoot=(Split-Path -Parent $scriptRoot)}
$controller=Join-Path $OpenWorkerRoot 'scripts\case0003_local_continue.ps1'
$preflight=Join-Path $OpenWorkerRoot 'scripts\case0003_local_preflight.ps1'
$imageryQuarantine=Join-Path $OpenWorkerRoot 'scripts\case0003_quarantine_unsafe_imagery.ps1'
$terrainQuarantine=Join-Path $OpenWorkerRoot 'scripts\case0003_quarantine_stale_terrain.ps1'
$consumerQuarantine=Join-Path $OpenWorkerRoot 'scripts\case0003_quarantine_stale_consumer.ps1'
$renderQuarantine=Join-Path $OpenWorkerRoot 'scripts\case0003_quarantine_stale_render_outputs.ps1'
$osArtifactGuard=Join-Path $OpenWorkerRoot 'scripts\case0003_guard_os_artifact_binding.ps1'
$imageryRecorder=Join-Path $OpenWorkerRoot 'scripts\case0003_record_imagery_acceptance.py'
$terrainRecorder=Join-Path $OpenWorkerRoot 'scripts\case0003_record_terrain_acceptance.py'
$renderRecorder=Join-Path $OpenWorkerRoot 'scripts\case0003_record_render_acceptance.py'
foreach($required in @($controller,$preflight,$imageryQuarantine,$terrainQuarantine,$consumerQuarantine,$renderQuarantine,$osArtifactGuard,$imageryRecorder,$terrainRecorder,$renderRecorder)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Case 0003 required entrypoint missing: $required"}}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status" -TimeoutSec 10
if([string]$node.node_id -and -not ([string]$node.node_id).Equals($Machine,[StringComparison]::OrdinalIgnoreCase) -and -not ([string]$node.machine).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "OpenWorker node identity mismatch expected=$Machine node_id=$($node.node_id) machine=$($node.machine)"}
function Inventory-Root([string]$EnvName){foreach($r in @($node.inventory.roots)){if(([string]$r.env).Equals($EnvName,[StringComparison]::OrdinalIgnoreCase) -and [bool]$r.available -and -not[string]::IsNullOrWhiteSpace([string]$r.path)){if(Test-Path -LiteralPath ([string]$r.path) -PathType Container){return [string]$r.path}}};return ''}
function Resolve-Root([string]$Explicit,[string]$EnvName){if(-not[string]::IsNullOrWhiteSpace($Explicit)){if(-not(Test-Path -LiteralPath $Explicit -PathType Container)){throw "$EnvName explicit root unavailable: $Explicit"};return(Resolve-Path -LiteralPath $Explicit).Path};$fromInventory=Inventory-Root $EnvName;if(-not[string]::IsNullOrWhiteSpace($fromInventory)){return(Resolve-Path -LiteralPath $fromInventory).Path};$envValue=[Environment]::GetEnvironmentVariable($EnvName);if(-not[string]::IsNullOrWhiteSpace($envValue)-and(Test-Path -LiteralPath $envValue -PathType Container)){return(Resolve-Path -LiteralPath $envValue).Path};throw "$EnvName root unavailable from explicit parameter, OpenWorker inventory, or environment"}
$GoToolRoot=Resolve-Root $GoToolRoot 'GO_TOOL_ROOT';$TerrainRoot=Resolve-Root $TerrainRoot 'TERRAIN_ROOT';$SceneXRoot=Resolve-Root $SceneXRoot 'SCENEX_ROOT';$EngineeringOSRoot=Resolve-Root $EngineeringOSRoot 'ENGINEERING_OS_ROOT';$DriveSyncRoot=Resolve-Root $DriveSyncRoot 'OPENWORKER_REVIEW_DRIVE_ROOT'
if(-not(Test-Path -LiteralPath $OpenWorkerRoot -PathType Container)){throw "OPENWORKER_ROOT unavailable: $OpenWorkerRoot"}
$bindingPath=Join-Path $WorkspaceRoot '.openworker\job-binding.json';if(-not(Test-Path -LiteralPath $bindingPath -PathType Leaf)){throw "Case 0003 JobBinding missing: $bindingPath"}
$binding=Get-Content -LiteralPath $bindingPath -Raw|ConvertFrom-Json
if([string]$binding.schema_version -ne 'openworker.job-binding.v1'){throw "unsupported JobBinding schema: $($binding.schema_version)"};if(-not ([string]$binding.assigned_host).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "JobBinding host mismatch expected=$Machine actual=$($binding.assigned_host)"}
$boundWorkspace=(Resolve-Path -LiteralPath ([string]$binding.workspace_root)).Path;$currentWorkspace=(Resolve-Path -LiteralPath $WorkspaceRoot).Path;if(-not $boundWorkspace.Equals($currentWorkspace,[StringComparison]::OrdinalIgnoreCase)){throw "JobBinding workspace mismatch expected=$currentWorkspace actual=$boundWorkspace"}
if([string]::IsNullOrWhiteSpace($OSProjectId)){$OSProjectId=[string]$binding.project_id}elseif($OSProjectId -ne [string]$binding.project_id){throw "explicit OSProjectId does not match JobBinding project_id"};if([string]::IsNullOrWhiteSpace($OSJobId)){$OSJobId=[string]$binding.job_id}elseif($OSJobId -ne [string]$binding.job_id){throw "explicit OSJobId does not match JobBinding job_id"};if([string]::IsNullOrWhiteSpace($OSProjectId)-or[string]::IsNullOrWhiteSpace($OSJobId)){throw 'JobBinding lacks persisted Engineering OS identity'}
$resolved=[ordered]@{schema='openworker/case0003-root-resolution/v11';case_id='0003';machine=$Machine;source='explicit>openworker-inventory>environment';openworker_root=$OpenWorkerRoot;go_tool_root=$GoToolRoot;terrain_root=$TerrainRoot;scenex_root=$SceneXRoot;engineering_os_root=$EngineeringOSRoot;drive_review_root=$DriveSyncRoot;engineering_os_project_id=$OSProjectId;engineering_os_job_id=$OSJobId;identity_source='openworker-job-binding'}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null;$resolved|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-root-resolution.json') -Encoding utf8
& $preflight -OpenWorkerUrl $OpenWorkerUrl -WorkspaceRoot $WorkspaceRoot -Machine $Machine -EngineeringOSBaseUrl $EngineeringOSBaseUrl -CatalogPath $CatalogPath;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $imageryQuarantine -WorkspaceRoot $WorkspaceRoot;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $terrainQuarantine -WorkspaceRoot $WorkspaceRoot -CatalogPath $CatalogPath -Machine $Machine;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $consumerQuarantine -WorkspaceRoot $WorkspaceRoot -Machine $Machine;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $renderQuarantine -WorkspaceRoot $WorkspaceRoot;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $osArtifactGuard -WorkspaceRoot $WorkspaceRoot;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $controller -OpenWorkerUrl $OpenWorkerUrl -WorkspaceRoot $WorkspaceRoot -Machine $Machine -OpenWorkerRoot $OpenWorkerRoot -DriveSyncRoot $DriveSyncRoot -GoToolRoot $GoToolRoot -TerrainRoot $TerrainRoot -SceneXRoot $SceneXRoot -EngineeringOSRoot $EngineeringOSRoot -OSProjectId $OSProjectId -OSJobId $OSJobId -EngineeringOSBaseUrl $EngineeringOSBaseUrl -CatalogPath $CatalogPath;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$continueReceipt=Join-Path $WorkspaceRoot 'evidence\case0003-local-continue.json'
if(Test-Path -LiteralPath $continueReceipt -PathType Leaf){$state=Get-Content -LiteralPath $continueReceipt -Raw|ConvertFrom-Json;if([string]$state.schema -eq 'openworker/case0003-local-continue/v10'){Push-Location $OpenWorkerRoot;try{if([bool]$state.gates_after_submission.streetview -and [bool]$state.gates_after_submission.orthophoto){python scripts/case0003_record_imagery_acceptance.py --workspace $WorkspaceRoot;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}};if([bool]$state.gates_after_submission.terrain){python scripts/case0003_record_terrain_acceptance.py --workspace $WorkspaceRoot --catalog $CatalogPath;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}};if([bool]$state.gates_after_submission.blender -and[bool]$state.gates_after_submission.scenex){python scripts/case0003_record_render_acceptance.py --workspace $WorkspaceRoot;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}}}finally{Pop-Location}}}
