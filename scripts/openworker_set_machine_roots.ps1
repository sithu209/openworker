param(
  [string]$RegistryPath=$env:OPENWORKER_MACHINE_ROOTS_FILE,
  [string]$OpenWorkerRoot=$env:OPENWORKER_ROOT,
  [string]$GoToolRoot=$env:GO_TOOL_ROOT,
  [string]$TerrainRoot=$env:TERRAIN_ROOT,
  [string]$SceneXRoot=$env:SCENEX_ROOT,
  [string]$EngineeringOSRoot=$env:ENGINEERING_OS_ROOT,
  [string]$DriveReviewRoot=$env:OPENWORKER_REVIEW_DRIVE_ROOT
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($RegistryPath)){
  $base=$env:ProgramData
  if([string]::IsNullOrWhiteSpace($base)){throw 'ProgramData unavailable; pass -RegistryPath explicitly'}
  $RegistryPath=Join-Path $base 'OpenWorker\machine-roots.json'
}

# Existing authorities are preserved unless the caller explicitly supplies a
# replacement. This file is shared by multiple local-first capabilities; a Case
# activation must never erase Terrain/SceneX/Drive roots it does not own.
$merged=[ordered]@{}
if(Test-Path -LiteralPath $RegistryPath -PathType Leaf){
  try{
    $existing=Get-Content -LiteralPath $RegistryPath -Raw|ConvertFrom-Json
    foreach($prop in $existing.PSObject.Properties){
      $value=[string]$prop.Value
      if(-not[string]::IsNullOrWhiteSpace($value)){$merged[$prop.Name]=$value}
    }
  }catch{throw "existing machine roots are invalid JSON: $RegistryPath : $($_.Exception.Message)"}
}
$updates=[ordered]@{
  OPENWORKER_ROOT=$OpenWorkerRoot
  GO_TOOL_ROOT=$GoToolRoot
  TERRAIN_ROOT=$TerrainRoot
  SCENEX_ROOT=$SceneXRoot
  ENGINEERING_OS_ROOT=$EngineeringOSRoot
  OPENWORKER_REVIEW_DRIVE_ROOT=$DriveReviewRoot
}
foreach($k in $updates.Keys){
  $v=[string]$updates[$k]
  if([string]::IsNullOrWhiteSpace($v)){continue}
  if(-not(Test-Path -LiteralPath $v -PathType Container)){throw "$k root unavailable: $v"}
  $merged[$k]=(Resolve-Path -LiteralPath $v).Path
}
if($merged.Count -eq 0){throw 'no machine roots available after merge'}
$parent=Split-Path -Parent $RegistryPath;New-Item -ItemType Directory -Force -Path $parent|Out-Null
$tmp="$RegistryPath.tmp"
$merged|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $tmp -Encoding utf8
Move-Item -Force -LiteralPath $tmp -Destination $RegistryPath
[ordered]@{schema='openworker/machine-roots/v2';machine=$env:COMPUTERNAME;registry_path=$RegistryPath;roots=$merged;merge_semantics='preserve-unspecified'}|ConvertTo-Json -Depth 6|Write-Host
