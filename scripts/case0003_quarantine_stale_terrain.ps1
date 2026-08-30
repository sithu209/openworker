param(
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$CatalogPath='D:\TaiwanDTM\catalog\dtm_catalog.sqlite',
  [string]$Machine='DESKTOP-UL7V2VV'
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
function Read-Json([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null};try{return Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}catch{return $null}}
function SHA([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return ''};return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Same-Path([string]$A,[string]$B){if([string]::IsNullOrWhiteSpace($A)-or[string]::IsNullOrWhiteSpace($B)){return $false};try{return (Resolve-Path -LiteralPath $A).Path.Equals((Resolve-Path -LiteralPath $B).Path,[StringComparison]::OrdinalIgnoreCase)}catch{return $false}}
$terrainRoot=Join-Path $WorkspaceRoot 'terrain'
if(-not(Test-Path -LiteralPath $terrainRoot -PathType Container)){
  [ordered]@{schema='openworker/case0003-terrain-quarantine/v1';ok=$true;action='none';reason='terrain_absent'}|ConvertTo-Json -Compress|Write-Host
  exit 0
}
$reasons=@()
$manifestPath=Join-Path $terrainRoot 'terrain-aoi-workspace.json'
$m=Read-Json $manifestPath
$geoPath=Join-Path $WorkspaceRoot 'geo\geolocation.json'
$geo=Read-Json $geoPath
if($null -eq $m -or [string]$m.schema_version -ne 'terrain-aoi-workspace/v2' -or -not[bool]$m.ok){$reasons+='manifest_v2_required'}
if($null -eq $geo -or -not[bool]$geo.ok){$reasons+='accepted_geo_missing'}
if(-not(Test-Path -LiteralPath $CatalogPath -PathType Leaf) -or (Get-Item -LiteralPath $CatalogPath).Length -le 0){$reasons+='catalog_missing'}
if($reasons.Count -eq 0){
  if(-not ([string]$m.assigned_host).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){$reasons+='host_mismatch'}
  if(-not(Same-Path ([string]$m.workspace_root) $WorkspaceRoot)){$reasons+='workspace_mismatch'}
  if(-not(Same-Path ([string]$m.geolocation.source_path) $geoPath)){$reasons+='geo_path_mismatch'}
  if((SHA $geoPath) -ne ([string]$m.geolocation.sha256).ToLowerInvariant()){$reasons+='geo_sha_mismatch'}
  try{
    if([math]::Abs(([double]$m.geolocation.lat)-([double]$geo.geolocation.lat)) -gt 0.0000001 -or [math]::Abs(([double]$m.geolocation.lng)-([double]$geo.geolocation.lng)) -gt 0.0000001){$reasons+='geo_coordinate_mismatch'}
  }catch{$reasons+='geo_coordinate_invalid'}
  if(-not(Same-Path ([string]$m.catalog.path) $CatalogPath)){$reasons+='catalog_path_mismatch'}
  if([int64]$m.catalog.size -ne [int64](Get-Item -LiteralPath $CatalogPath).Length){$reasons+='catalog_size_mismatch'}
  if((SHA $CatalogPath) -ne ([string]$m.catalog.sha256).ToLowerInvariant()){$reasons+='catalog_sha_mismatch'}
  $requestPath=Join-Path $terrainRoot 'terrain-aoi-build-request.json'
  if(-not(Same-Path ([string]$m.request.path) $requestPath) -or (SHA $requestPath) -ne ([string]$m.request.sha256).ToLowerInvariant()){$reasons+='request_sha_mismatch'}
  if([int]$m.usable_tiles -le 0){$reasons+='usable_tiles_zero'}
  $required=@('terrain-context.json','terrain-build.json','terrain-grid.json','terrain.dxf','terrain-heightmap.raw','terrain-heightmap.json','terrain.obj','terrain-mesh.json','terrain-scene.json','scenex-terrain-scene.json')
  $items=@($m.artifacts)
  foreach($name in $required){
    $canonical=Join-Path $terrainRoot $name
    $a=@($items|Where-Object{[string]$_.name -eq $name})
    if($a.Count -ne 1){$reasons+="artifact_manifest_$name";continue}
    if(-not(Same-Path ([string]$a[0].path) $canonical)){$reasons+="artifact_path_$name";continue}
    if(-not(Test-Path -LiteralPath $canonical -PathType Leaf) -or (Get-Item -LiteralPath $canonical).Length -le 0){$reasons+="artifact_missing_$name";continue}
    if([int64]$a[0].size -ne [int64](Get-Item -LiteralPath $canonical).Length){$reasons+="artifact_size_$name";continue}
    if((SHA $canonical) -ne ([string]$a[0].sha256).ToLowerInvariant()){$reasons+="artifact_sha_$name"}
  }
}
if($reasons.Count -eq 0){
  [ordered]@{schema='openworker/case0003-terrain-quarantine/v1';ok=$true;action='none';reason='strict_terrain_valid';manifest=$manifestPath}|ConvertTo-Json -Depth 5 -Compress|Write-Host
  exit 0
}
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$qRoot=Join-Path $WorkspaceRoot '.openworker\quarantine\terrain'
New-Item -ItemType Directory -Force -Path $qRoot|Out-Null
$dest=Join-Path $qRoot ("terrain-$stamp")
Move-Item -LiteralPath $terrainRoot -Destination $dest
$receipt=[ordered]@{schema='openworker/case0003-terrain-quarantine/v1';ok=$true;action='quarantined';reason='strict_terrain_rejected';reasons=@($reasons|Select-Object -Unique);source=$terrainRoot;quarantine=$dest;quarantined_at=[DateTimeOffset]::UtcNow.ToString('o')}
$receiptPath=Join-Path $qRoot ("terrain-quarantine-$stamp.json")
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $receiptPath -Encoding utf8
$receipt|ConvertTo-Json -Depth 8 -Compress|Write-Host
