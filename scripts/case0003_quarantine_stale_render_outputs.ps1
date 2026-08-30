param(
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE'
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd('\')
if(-not(Test-Path -LiteralPath $root -PathType Container)){throw "workspace unavailable: $root"}
function Read-Json([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null};try{return Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}catch{return $null}}
function Sha([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return ''};return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Bounded([string]$Path){if([string]::IsNullOrWhiteSpace($Path)){return $false};try{$full=[IO.Path]::GetFullPath($Path);return $full.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)}catch{return $false}}
function Quarantine-Dir([string]$Name,[string[]]$Reasons){$src=Join-Path $root $Name;if(-not(Test-Path -LiteralPath $src -PathType Container)){return};$qroot=Join-Path $root ('.openworker\quarantine\'+$Name);New-Item -ItemType Directory -Force -Path $qroot|Out-Null;$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ');$dst=Join-Path $qroot ($Name+'-'+$stamp);Move-Item -LiteralPath $src -Destination $dst;$receipt=[ordered]@{schema_version='openworker-case0003-stale-output-quarantine/v1';stage=$Name;source=$src;quarantined_to=$dst;reasons=$Reasons;quarantined_at=[DateTimeOffset]::UtcNow.ToString('o')};$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $qroot ('latest-'+$Name+'-quarantine.json')) -Encoding utf8}

$consumer=Read-Json (Join-Path $root 'consumer\consumer-workspace.json')
$consumerFp=if($consumer){[string]$consumer.consumer_fingerprint}else{''}
$terrain=Read-Json (Join-Path $root 'acceptance\terrain\terrain-acceptance.json')
$terrainFp=if($terrain){[string]$terrain.fingerprint}else{''}
$terrainManifestPath=Join-Path $root 'terrain\terrain-aoi-workspace.json';$terrainManifestSha=Sha $terrainManifestPath
$geoSha=Sha (Join-Path $root 'geo\geolocation.json')

$blenderRoot=Join-Path $root 'blender'
if(Test-Path -LiteralPath $blenderRoot -PathType Container){
  $m=Read-Json (Join-Path $blenderRoot 'blender-workspace.json');$reasons=@()
  if($null -eq $m){$reasons+='blender-workspace.json missing/invalid'}elseif([string]$m.schema_version -ne 'blender-workspace/v2' -or -not $m.ok){$reasons+='blender-workspace/v2 required'}else{
    if([string]::IsNullOrWhiteSpace($consumerFp) -or [string]$m.consumer_fingerprint -ne $consumerFp){$reasons+='consumer fingerprint mismatch'}
    $cw=Join-Path $root 'consumer\consumer-workspace.json';if((Sha $cw) -ne [string]$m.consumer_workspace_sha256){$reasons+='consumer workspace SHA mismatch'}
    foreach($a in @($m.artifacts)){if(-not(Bounded ([string]$a.path))){$reasons+="artifact escapes workspace: $($a.path)";continue};if((Sha ([string]$a.path)) -ne [string]$a.sha256){$reasons+="artifact SHA mismatch: $($a.name)"}}
  }
  if($reasons.Count -gt 0){Quarantine-Dir 'blender' $reasons}
}

$scenexRoot=Join-Path $root 'scenex'
if(Test-Path -LiteralPath $scenexRoot -PathType Container){
  $m=Read-Json (Join-Path $scenexRoot 'scenex-workspace.json');$reasons=@()
  if($null -eq $m){$reasons+='scenex-workspace.json missing/invalid'}elseif([string]$m.schema_version -ne 'scenex-workspace-browse/v2' -or -not $m.ok){$reasons+='scenex-workspace-browse/v2 required'}else{
    if([string]::IsNullOrWhiteSpace($terrainFp) -or [string]$m.terrain_fingerprint -ne $terrainFp){$reasons+='terrain fingerprint mismatch'}
    if([string]$m.terrain_manifest_sha256 -ne $terrainManifestSha){$reasons+='terrain manifest SHA mismatch'}
    if([string]$m.geo_sha256 -ne $geoSha){$reasons+='GEO SHA mismatch'}
    foreach($x in @($m.region_pack,$m.screenshot,$m.evidence)){if(-not(Bounded ([string]$x.path))){$reasons+="SceneX path escapes workspace: $($x.path)";continue};if((Sha ([string]$x.path)) -ne [string]$x.sha256){$reasons+="SceneX SHA mismatch: $($x.path)"}}
    if([int]$m.active_chunks -le 0 -or [int]$m.terrain_geometry_count -le 0){$reasons+='SceneX geometry diagnostics rejected'}
  }
  if($reasons.Count -gt 0){Quarantine-Dir 'scenex' $reasons}
}
Write-Host 'CASE0003_RENDER_OUTPUT_QUARANTINE_CHECK_DONE'
