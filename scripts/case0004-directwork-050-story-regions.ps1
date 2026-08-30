param([Parameter(Mandatory=$true)][string]$RequestId)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:COMPUTERNAME -ine 'DESKTOP-O87PJNR'){throw "CASE0004_WRONG_HOST actual=$env:COMPUTERNAME"}
$workspace='D:\AI-Work\jobs\0004-DWG-TO-3D'
$evidence=Join-Path $workspace ('evidence\directwork\'+$RequestId)
New-Item -ItemType Directory -Force -Path $evidence|Out-Null

$query=[ordered]@{
  session_id=('case0004-050-'+$RequestId)
  project='DWG_todo Case 0004'
  workspace_root=$workspace
  question='Confirm current contracts for cad.set_story_region and cad.get_story_region. Values are already visually reviewed; provide method guidance only and do not invent business values.'
  task='Provide method guidance only for Case0004 step 0004-050 Story Region promotion.'
}
try{$goTool=Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8848/agent/query' -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 20) -TimeoutSec 60}catch{$goTool=[ordered]@{error=$_.Exception.Message}}
[IO.File]::WriteAllText((Join-Path $evidence 'go-tool-query.json'),($goTool|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$pointer=Join-Path $env:ProgramData 'go-tool-runtime\work-agent\authorities\dwg-todo-current.json'
if(-not(Test-Path -LiteralPath $pointer -PathType Leaf)){throw "DWG_AUTHORITY_POINTER_MISSING path=$pointer"}
$authority=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
$authorityRoot=[string]$authority.root
$invoke=Join-Path $authorityRoot 'scripts\invoke-agent-cad-local.ps1'
if(-not(Test-Path -LiteralPath $invoke -PathType Leaf)){throw "DWG_LOCAL_WRAPPER_MISSING path=$invoke"}

$regions=@(
  [ordered]@{story_id='1F';name='ground-floor-plan';bounds=[ordered]@{min_x=48000.0;min_y=57100.0;max_x=50300.0;max_y=60050.0}},
  [ordered]@{story_id='2F';name='second-floor-plan';bounds=[ordered]@{min_x=46450.0;min_y=54200.0;max_x=48400.0;max_y=57300.0}},
  [ordered]@{story_id='3F';name='third-to-fourth-floor-plan-3F';bounds=[ordered]@{min_x=47950.0;min_y=54200.0;max_x=50250.0;max_y=57300.0}},
  [ordered]@{story_id='4F';name='third-to-fourth-floor-plan-4F';bounds=[ordered]@{min_x=47950.0;min_y=54200.0;max_x=50250.0;max_y=57300.0}},
  [ordered]@{story_id='R1F';name='penthouse-first-floor-plan';bounds=[ordered]@{min_x=46450.0;min_y=51050.0;max_x=48450.0;max_y=54400.0}}
)

$verified=@()
foreach($r in $regions){
  $params=[ordered]@{story_id=[string]$r.story_id;name=[string]$r.name;bounds=$r.bounds;confidence=1.0;review_status='confirmed'}
  $json=$params|ConvertTo-Json -Depth 20 -Compress
  $set=& {param($p,$j,$root,$id) Set-StrictMode -Off; & $p -Method 'cad.set_story_region' -ParamsJson $j -WorkspaceRoot $root -WorkId $id} $invoke $json $workspace ('directwork-case0004-050-set-'+([string]$r.story_id).ToLowerInvariant()+'-'+$RequestId)
  if($LASTEXITCODE -ne 0){throw "CASE0004_050_SET_FAILED story=$($r.story_id) exit=$LASTEXITCODE"}
  $setText=($set -join "`n")
  $setPath=Join-Path $evidence (([string]$r.story_id).ToLowerInvariant()+'-set-story-region.stdout.json')
  [IO.File]::WriteAllText($setPath,$setText+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

  $getParams=[ordered]@{story_id=[string]$r.story_id}
  $getJson=$getParams|ConvertTo-Json -Compress
  $get=& {param($p,$j,$root,$id) Set-StrictMode -Off; & $p -Method 'cad.get_story_region' -ParamsJson $j -WorkspaceRoot $root -WorkId $id} $invoke $getJson $workspace ('directwork-case0004-050-get-'+([string]$r.story_id).ToLowerInvariant()+'-'+$RequestId)
  if($LASTEXITCODE -ne 0){throw "CASE0004_050_GET_FAILED story=$($r.story_id) exit=$LASTEXITCODE"}
  $getText=($get -join "`n")
  $getPath=Join-Path $evidence (([string]$r.story_id).ToLowerInvariant()+'-get-story-region.stdout.json')
  [IO.File]::WriteAllText($getPath,$getText+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  $getObj=$getText|ConvertFrom-Json
  $sr=$getObj.result.story_region
  if([string]$sr.story_id -ne [string]$r.story_id){throw "CASE0004_050_ID_MISMATCH expected=$($r.story_id) actual=$($sr.story_id)"}
  if([string]$sr.review_status -ne 'confirmed'){throw "CASE0004_050_NOT_CONFIRMED story=$($r.story_id) status=$($sr.review_status)"}
  if([double]$sr.confidence -ne 1.0){throw "CASE0004_050_CONFIDENCE story=$($r.story_id) actual=$($sr.confidence)"}
  $verified+=@([ordered]@{story_id=[string]$sr.story_id;name=[string]$sr.name;bounds=$sr.bounds;confidence=[double]$sr.confidence;review_status=[string]$sr.review_status;source_revision=[int64]$sr.source_revision;set_receipt=$setPath;get_receipt=$getPath})
}

if($verified.Count -ne 5){throw "CASE0004_050_REGION_COUNT actual=$($verified.Count)"}
$state=Join-Path $workspace 'dwg\agent-cad-state.json'
if(-not(Test-Path -LiteralPath $state -PathType Leaf)){throw "CASE0004_STATE_MISSING path=$state"}
$summary=[ordered]@{
  schema='case0004.directwork.050.story-regions.v1';case_id='0004';step='0004-050';request_id=$RequestId;status='succeeded';machine=$env:COMPUTERNAME
  authority_root=$authorityRoot;authority_commit=[string]$authority.commit
  source_corrected_work_id='dw-20260820T082930-50cdb590b6fecc66'
  region_count=$verified.Count;regions=$verified
  state_path=$state;state_bytes=(Get-Item -LiteralPath $state).Length;state_sha256=(Get-FileHash -LiteralPath $state -Algorithm SHA256).Hash.ToLowerInvariant()
  review_status='confirmed';completed_at=[DateTimeOffset]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $evidence 'final.json'),($summary|ConvertTo-Json -Depth 60)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 60 -Compress
