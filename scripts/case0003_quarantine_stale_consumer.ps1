param(
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE',
  [string]$Machine='DESKTOP-UL7V2VV'
)
$ErrorActionPreference='Stop'
if(-not $env:COMPUTERNAME.Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){throw "wrong host expected=$Machine actual=$env:COMPUTERNAME"}
function Read-Json([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null};try{return Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}catch{return $null}}
function SHA([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return ''};return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Same-Path([string]$A,[string]$B){if([string]::IsNullOrWhiteSpace($A)-or[string]::IsNullOrWhiteSpace($B)){return $false};try{return (Resolve-Path -LiteralPath $A).Path.Equals((Resolve-Path -LiteralPath $B).Path,[StringComparison]::OrdinalIgnoreCase)}catch{return $false}}
$consumerRoot=Join-Path $WorkspaceRoot 'consumer'
if(-not(Test-Path -LiteralPath $consumerRoot -PathType Container)){
  [ordered]@{schema='openworker/case0003-consumer-quarantine/v1';ok=$true;action='none';reason='consumer_absent'}|ConvertTo-Json -Compress|Write-Host
  exit 0
}
$reasons=@()
$m=Read-Json (Join-Path $consumerRoot 'consumer-workspace.json')
$imageryAcceptance=Join-Path $WorkspaceRoot 'acceptance\imagery\imagery-acceptance.json'
$terrainAcceptance=Join-Path $WorkspaceRoot 'acceptance\terrain\terrain-acceptance.json'
$terrainManifest=Join-Path $WorkspaceRoot 'terrain\terrain-aoi-workspace.json'
$geo=Join-Path $WorkspaceRoot 'geo\geolocation.json'
$ia=Read-Json $imageryAcceptance
$ta=Read-Json $terrainAcceptance
if($null -eq $m -or [string]$m.schema_version -ne 'consumer-workspace/v2' -or -not[bool]$m.ok){$reasons+='manifest_v2_required'}
if($null -eq $ia -or [string]$ia.schema_version -ne 'openworker-case0003-imagery-acceptance/v1'){$reasons+='imagery_acceptance_missing'}
if($null -eq $ta -or [string]$ta.schema_version -ne 'openworker-case0003-terrain-acceptance/v1'){$reasons+='terrain_acceptance_missing'}
foreach($p in @($geo,$terrainManifest)){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){$reasons+='upstream_physical_missing'}}
if($reasons.Count -eq 0){
  if(-not ([string]$m.assigned_host).Equals($Machine,[StringComparison]::OrdinalIgnoreCase)){$reasons+='host_mismatch'}
  if(-not(Same-Path ([string]$m.workspace_root) $WorkspaceRoot)){$reasons+='workspace_mismatch'}
  if(-not(Same-Path ([string]$m.upstream.geo.path) $geo) -or (SHA $geo) -ne ([string]$m.upstream.geo.sha256).ToLowerInvariant()){$reasons+='geo_identity_mismatch'}
  if(-not(Same-Path ([string]$m.upstream.imagery_acceptance.path) $imageryAcceptance) -or [string]$m.upstream.imagery_acceptance.fingerprint -ne [string]$ia.fingerprint -or (SHA $imageryAcceptance) -ne ([string]$m.upstream.imagery_acceptance.sha256).ToLowerInvariant()){$reasons+='imagery_identity_mismatch'}
  if(-not(Same-Path ([string]$m.upstream.terrain_manifest.path) $terrainManifest) -or (SHA $terrainManifest) -ne ([string]$m.upstream.terrain_manifest.sha256).ToLowerInvariant()){$reasons+='terrain_manifest_identity_mismatch'}
  if(-not(Same-Path ([string]$m.upstream.terrain_acceptance.path) $terrainAcceptance) -or [string]$m.upstream.terrain_acceptance.fingerprint -ne [string]$ta.fingerprint -or (SHA $terrainAcceptance) -ne ([string]$m.upstream.terrain_acceptance.sha256).ToLowerInvariant()){$reasons+='terrain_acceptance_identity_mismatch'}
  $required=@('visual-frame-set.json','blender-reference-pack.json','minimax-h3-reference-pack.json','blender-visual-handoff.json','minimax-h3-visual-handoff.json','geo-context.json','consumer-orchestration.json')
  $items=@($m.artifacts)
  foreach($name in $required){
    $canonical=Join-Path $consumerRoot $name
    $a=@($items|Where-Object{[string]$_.name -eq $name})
    if($a.Count -ne 1){$reasons+="artifact_manifest_$name";continue}
    if(-not(Same-Path ([string]$a[0].path) $canonical)){$reasons+="artifact_path_$name";continue}
    if(-not(Test-Path -LiteralPath $canonical -PathType Leaf) -or (Get-Item -LiteralPath $canonical).Length -le 0){$reasons+="artifact_missing_$name";continue}
    if([int64]$a[0].bytes -ne [int64](Get-Item -LiteralPath $canonical).Length -or (SHA $canonical) -ne ([string]$a[0].sha256).ToLowerInvariant()){$reasons+="artifact_identity_$name"}
  }
  $contract=Join-Path $consumerRoot 'consumer-orchestration.json'
  if(-not(Same-Path ([string]$m.contract.path) $contract) -or (SHA $contract) -ne ([string]$m.contract.sha256).ToLowerInvariant()){$reasons+='contract_identity_mismatch'}
  if(-not(Test-Path -LiteralPath ([string]$m.mesh.path) -PathType Leaf) -or (SHA ([string]$m.mesh.path)) -ne ([string]$m.mesh.sha256).ToLowerInvariant()){$reasons+='mesh_identity_mismatch'}
}
if($reasons.Count -eq 0){
  [ordered]@{schema='openworker/case0003-consumer-quarantine/v1';ok=$true;action='none';reason='strict_consumer_valid'}|ConvertTo-Json -Compress|Write-Host
  exit 0
}
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$qRoot=Join-Path $WorkspaceRoot '.openworker\quarantine\consumer';New-Item -ItemType Directory -Force -Path $qRoot|Out-Null
$dest=Join-Path $qRoot ("consumer-$stamp")
Move-Item -LiteralPath $consumerRoot -Destination $dest
$receipt=[ordered]@{schema='openworker/case0003-consumer-quarantine/v1';ok=$true;action='quarantined';reason='strict_consumer_rejected';reasons=@($reasons|Select-Object -Unique);source=$consumerRoot;quarantine=$dest;quarantined_at=[DateTimeOffset]::UtcNow.ToString('o')}
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $qRoot ("consumer-quarantine-$stamp.json")) -Encoding utf8
$receipt|ConvertTo-Json -Depth 8 -Compress|Write-Host
