param([Parameter(Mandatory=$true)][string]$RequestId)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:COMPUTERNAME -ine 'DESKTOP-O87PJNR'){throw "CASE0004_WRONG_HOST actual=$env:COMPUTERNAME"}
$workspace='D:\AI-Work\jobs\0004-DWG-TO-3D'
$evidence=Join-Path $workspace ('evidence\directwork\'+$RequestId)
New-Item -ItemType Directory -Force -Path $evidence|Out-Null

$query=[ordered]@{
  session_id=('case0004-055-'+$RequestId)
  project='DWG_todo Case 0004'
  workspace_root=$workspace
  question='Confirm current contract for cad.list_story_column_candidates and cad.query_bounds. Keep this read-only; do not promote handles or invent Column Authority. Zero candidates must be diagnosed from REAL entity and full-model block-anchor evidence.'
  task='Provide method guidance only for Case0004 step 0004-055 zero-candidate diagnosis.'
}
try{$goTool=Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8848/agent/query' -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 20) -TimeoutSec 60}catch{$goTool=[ordered]@{error=$_.Exception.Message}}
[IO.File]::WriteAllText((Join-Path $evidence 'go-tool-query.json'),($goTool|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$pointer=Join-Path $env:ProgramData 'go-tool-runtime\work-agent\authorities\dwg-todo-current.json'
if(-not(Test-Path -LiteralPath $pointer -PathType Leaf)){throw "DWG_AUTHORITY_POINTER_MISSING path=$pointer"}
$authority=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
$authorityRoot=[string]$authority.root
$invoke=Join-Path $authorityRoot 'scripts\invoke-agent-cad-local.ps1'
if(-not(Test-Path -LiteralPath $invoke -PathType Leaf)){throw "DWG_LOCAL_WRAPPER_MISSING path=$invoke"}

function Invoke-LocalCAD([string]$Method,[object]$Params,[string]$WorkSuffix){
  $json=$Params|ConvertTo-Json -Depth 30 -Compress
  $out=& {param($p,$m,$j,$root,$id) Set-StrictMode -Off; & $p -Method $m -ParamsJson $j -WorkspaceRoot $root -WorkId $id} $invoke $Method $json $workspace $WorkSuffix
  if($LASTEXITCODE -ne 0){throw "CASE0004_055_LOCAL_CAD_FAILED method=$Method suffix=$WorkSuffix exit=$LASTEXITCODE"}
  $text=($out -join "`n")
  return [pscustomobject]@{text=$text;obj=($text|ConvertFrom-Json)}
}

function Get-EntityDiagnostic([object[]]$Entities){
  $typeCounts=@{};$statusCounts=@{};$positive2D=0;$degenerate2D=0;$missingBounds=0;$samples=@();$blockSamples=@()
  foreach($entity in @($Entities)){
    $type=[string]$entity.type;if([string]::IsNullOrWhiteSpace($type)){$type='UNKNOWN'}
    if(-not $typeCounts.ContainsKey($type)){$typeCounts[$type]=0};$typeCounts[$type]++
    $status=[string]$entity.bounds_status;if([string]::IsNullOrWhiteSpace($status)){$status='unknown'}
    if(-not $statusCounts.ContainsKey($status)){$statusCounts[$status]=0};$statusCounts[$status]++
    $b=$entity.bounds
    if($null -eq $b -or $null -eq $b.min -or $null -eq $b.max){$missingBounds++;continue}
    $min=@($b.min);$max=@($b.max)
    if($min.Count -lt 2 -or $max.Count -lt 2){$missingBounds++;continue}
    $w=[Math]::Abs([double]$max[0]-[double]$min[0]);$d=[Math]::Abs([double]$max[1]-[double]$min[1])
    if($w -gt 0.000001 -and $d -gt 0.000001){$positive2D++}else{$degenerate2D++}
    if($samples.Count -lt 80){$samples+=@([ordered]@{handle=[string]$entity.handle;type=$type;bounds_status=$status;width=$w;depth=$d;block_name=[string]$entity.block_name;layer=[string]$entity.layer_resolved;insert_point=$entity.insert_point})}
    if($type -eq 'INSERT' -and $blockSamples.Count -lt 200){$blockSamples+=@([ordered]@{handle=[string]$entity.handle;block_name=[string]$entity.block_name;bounds=$entity.bounds;insert_point=$entity.insert_point;layer=[string]$entity.layer_resolved})}
  }
  $types=@();foreach($k in @($typeCounts.Keys|Sort-Object)){$types+=@([ordered]@{type=$k;count=[int]$typeCounts[$k]})}
  $statuses=@();foreach($k in @($statusCounts.Keys|Sort-Object)){$statuses+=@([ordered]@{status=$k;count=[int]$statusCounts[$k]})}
  return [ordered]@{entity_count=@($Entities).Count;positive_2d_bounds=$positive2D;degenerate_2d_bounds=$degenerate2D;missing_bounds=$missingBounds;type_counts=$types;bounds_status_counts=$statuses;samples=$samples;insert_samples=$blockSamples}
}

# Full overview/model-space bounds from accepted step 040 evidence. This scan is
# read-only and exists only to discover INSERT anchors that may sit outside a
# Story Region while their transformed block geometry crosses into it.
$fullBounds=[ordered]@{min_x=44443.25117;min_y=35301.30501;max_x=117008.65482;max_y=92030.00566}
$full=Invoke-LocalCAD 'cad.query_bounds' ([ordered]@{bounds=$fullBounds}) ('directwork-case0004-055-full-query-'+$RequestId)
$fullPath=Join-Path $evidence 'full-model-query-bounds.stdout.json'
[IO.File]::WriteAllText($fullPath,$full.text+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$fullDiag=Get-EntityDiagnostic @($full.obj.result.entities)

$broadBounds=[ordered]@{min_x=46400.0;min_y=51000.0;max_x=50800.0;max_y=63100.0}
$broad=Invoke-LocalCAD 'cad.query_bounds' ([ordered]@{bounds=$broadBounds}) ('directwork-case0004-055-broad-query-'+$RequestId)
$broadPath=Join-Path $evidence 'broad-query-bounds.stdout.json'
[IO.File]::WriteAllText($broadPath,$broad.text+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$broadDiag=Get-EntityDiagnostic @($broad.obj.result.entities)

$stories=@('1F','2F','3F','4F','R1F')
$inventories=@();$diagnostics=@()
foreach($story in $stories){
  $get=Invoke-LocalCAD 'cad.get_story_region' ([ordered]@{story_id=$story}) ('directwork-case0004-055-region-'+$story.ToLowerInvariant()+'-'+$RequestId)
  if([string]$get.obj.result.story_region.review_status -ne 'confirmed'){throw "CASE0004_055_REGION_NOT_CONFIRMED story=$story"}
  $cand=Invoke-LocalCAD 'cad.list_story_column_candidates' ([ordered]@{story_id=$story;limit=500}) ('directwork-case0004-055-candidates-'+$story.ToLowerInvariant()+'-'+$RequestId)
  $path=Join-Path $evidence ($story.ToLowerInvariant()+'-column-candidates.stdout.json')
  [IO.File]::WriteAllText($path,$cand.text+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  if([string]$cand.obj.result.authority -ne 'none'){throw "CASE0004_055_UNEXPECTED_AUTHORITY story=$story authority=$($cand.obj.result.authority)"}
  $count=[int]$cand.obj.result.candidate_count
  $inventories+=@([ordered]@{story_id=$story;candidate_count=$count;source_sha256=[string]$cand.obj.result.source_sha256;story_region=$cand.obj.result.story_region;receipt_path=$path;receipt_sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()})
  if($count -eq 0){
    $bounds=$get.obj.result.story_region.bounds
    $qb=Invoke-LocalCAD 'cad.query_bounds' ([ordered]@{bounds=[ordered]@{min_x=[double]$bounds.min_x;min_y=[double]$bounds.min_y;max_x=[double]$bounds.max_x;max_y=[double]$bounds.max_y}}) ('directwork-case0004-055-query-'+$story.ToLowerInvariant()+'-'+$RequestId)
    $qpath=Join-Path $evidence ($story.ToLowerInvariant()+'-query-bounds.stdout.json')
    [IO.File]::WriteAllText($qpath,$qb.text+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    $diagnostics+=@([ordered]@{story_id=$story;query_receipt_path=$qpath;query_receipt_sha256=(Get-FileHash -LiteralPath $qpath -Algorithm SHA256).Hash.ToLowerInvariant();diagnostic=(Get-EntityDiagnostic @($qb.obj.result.entities))})
  }
}

$state=Join-Path $workspace 'dwg\agent-cad-state.json'
$summary=[ordered]@{
  schema='case0004.directwork.055.column-candidates.v4';case_id='0004';step='0004-055';request_id=$RequestId;status='succeeded';machine=$env:COMPUTERNAME
  authority_root=$authorityRoot;authority_commit=[string]$authority.commit;source_story_region_work_id='dw-20260820T083831-efc1b644d6d5966c'
  full_model_query=[ordered]@{bounds=$fullBounds;receipt_path=$fullPath;receipt_sha256=(Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant();diagnostic=$fullDiag}
  broad_query=[ordered]@{bounds=$broadBounds;receipt_path=$broadPath;receipt_sha256=(Get-FileHash -LiteralPath $broadPath -Algorithm SHA256).Hash.ToLowerInvariant();diagnostic=$broadDiag}
  inventory_count=$inventories.Count;inventories=$inventories;zero_candidate_diagnostics=$diagnostics;column_authority='none';visual_review_required=$true
  state_path=$state;state_sha256=(Get-FileHash -LiteralPath $state -Algorithm SHA256).Hash.ToLowerInvariant();completed_at=[DateTimeOffset]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $evidence 'final.json'),($summary|ConvertTo-Json -Depth 100)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 100 -Compress
