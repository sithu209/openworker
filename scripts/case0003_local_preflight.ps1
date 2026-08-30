param(
  [string]$OpenWorkerUrl='http://127.0.0.1:8787',
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV',
  [string]$EngineeringOSBaseUrl='http://127.0.0.1:8080',
  [string]$CatalogPath='D:\TaiwanDTM\catalog\dtm_catalog.sqlite'
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
if(-not(Test-Path -LiteralPath $WorkspaceRoot -PathType Container)){throw "canonical workspace unavailable: $WorkspaceRoot"}
$node=Invoke-RestMethod -Method Get -Uri "$OpenWorkerUrl/v1/node/status" -TimeoutSec 10
if(-not([string]$node.machine).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "OpenWorker node machine mismatch: $($node.machine)"}
$requiredTools=@('go','python','powershell')
foreach($name in $requiredTools){$t=@($node.inventory.tools|Where-Object{[string]$_.name -eq $name}|Select-Object -First 1);if($t.Count -ne 1 -or -not[bool]$t[0].available){throw "required tool unavailable in OpenWorker inventory: $name"}}
$requiredRoots=@('OPENWORKER_ROOT','GO_TOOL_ROOT','TERRAIN_ROOT','SCENEX_ROOT','ENGINEERING_OS_ROOT')
foreach($envName in $requiredRoots){$r=@($node.inventory.roots|Where-Object{([string]$_.env).Equals($envName,[StringComparison]::OrdinalIgnoreCase)}|Select-Object -First 1);if($r.Count -ne 1 -or -not[bool]$r[0].available -or -not(Test-Path -LiteralPath ([string]$r[0].path) -PathType Container)){throw "required machine root unavailable: $envName"}}
$bindingPath=Join-Path $WorkspaceRoot '.openworker\job-binding.json'
if(-not(Test-Path -LiteralPath $bindingPath -PathType Leaf)){throw "JobBinding missing: $bindingPath"}
$binding=Get-Content -LiteralPath $bindingPath -Raw|ConvertFrom-Json
if([string]$binding.schema_version -ne 'openworker.job-binding.v1'){throw 'JobBinding schema mismatch'}
if(-not([string]$binding.assigned_host).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "JobBinding host mismatch: $($binding.assigned_host)"}
if((Resolve-Path -LiteralPath ([string]$binding.workspace_root)).Path -ne (Resolve-Path -LiteralPath $WorkspaceRoot).Path){throw 'JobBinding workspace mismatch'}
if([string]::IsNullOrWhiteSpace([string]$binding.project_id) -or [string]::IsNullOrWhiteSpace([string]$binding.job_id)){throw 'JobBinding OS project/job identity missing'}
if(-not(Test-Path -LiteralPath $CatalogPath -PathType Leaf)){throw "DTM catalog unavailable: $CatalogPath"}
if((Get-Item -LiteralPath $CatalogPath).Length -le 0){throw "DTM catalog empty: $CatalogPath"}
try{$health=Invoke-RestMethod -Method Get -Uri ($EngineeringOSBaseUrl.TrimEnd('/')+'/healthz') -TimeoutSec 5}catch{throw "Engineering OS health unavailable: $($_.Exception.Message)"}
if($health.PSObject.Properties.Name -contains 'ok' -and -not[bool]$health.ok){throw 'Engineering OS healthz returned ok=false'}
$out=[ordered]@{
  schema='openworker/case0003-local-preflight/v1';ok=$true;case_id='0003';machine=$Machine;workspace_root=$WorkspaceRoot;
  project_id=[string]$binding.project_id;job_id=[string]$binding.job_id;catalog_path=(Resolve-Path -LiteralPath $CatalogPath).Path;catalog_size=(Get-Item -LiteralPath $CatalogPath).Length;
  tools=@($node.inventory.tools|Where-Object{$requiredTools -contains [string]$_.name});roots=@($node.inventory.roots|Where-Object{$requiredRoots -contains [string]$_.env});checked_at=[DateTimeOffset]::UtcNow.ToString('o')
}
$evidenceDir=Join-Path $WorkspaceRoot 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null
$out|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-local-preflight.json') -Encoding utf8
$out|ConvertTo-Json -Depth 8|Write-Host
