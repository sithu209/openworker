param([Parameter(Mandatory=$true)][string]$RequestId,[switch]$CandidateViews)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:COMPUTERNAME -ine 'DESKTOP-O87PJNR'){throw "CASE0004_WRONG_HOST actual=$env:COMPUTERNAME"}
$workspace='D:\AI-Work\jobs\0004-DWG-TO-3D'
$evidence=Join-Path $workspace ('evidence\directwork\'+$RequestId)
New-Item -ItemType Directory -Force -Path $evidence|Out-Null
$pointer=Join-Path $env:ProgramData 'go-tool-runtime\work-agent\authorities\dwg-todo-current.json'
if(-not(Test-Path -LiteralPath $pointer -PathType Leaf)){throw "DWG_AUTHORITY_POINTER_MISSING path=$pointer"}
$authority=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
$invoke=Join-Path ([string]$authority.root) 'scripts\invoke-agent-cad-local.ps1'
if(-not(Test-Path -LiteralPath $invoke -PathType Leaf)){throw "DWG_LOCAL_WRAPPER_MISSING path=$invoke"}

if($CandidateViews){
  # Bounds come from visual review of REAL 3000x5000 relocalization PNG.
  # Keep this Windows PowerShell 5.1 executor source ASCII-only to avoid UTF-8/no-BOM parser corruption.
  # Semantic labels: 1F ground-floor plan; 2F plan; shared 3F-4F plan; R1F penthouse plan.
  # These are review zooms only, not final Story Index assignment.
  $views=@(
    [ordered]@{key='1f-candidate';label='ground-floor-plan';bounds=[ordered]@{min_x=48000.0;min_y=57100.0;max_x=50300.0;max_y=60050.0}},
    [ordered]@{key='2f-candidate';label='second-floor-plan';bounds=[ordered]@{min_x=46450.0;min_y=54200.0;max_x=48400.0;max_y=57300.0}},
    [ordered]@{key='3f-4f-candidate';label='third-to-fourth-floor-plan';bounds=[ordered]@{min_x=47950.0;min_y=54200.0;max_x=50250.0;max_y=57300.0}},
    [ordered]@{key='r1f-candidate';label='penthouse-first-floor-plan';bounds=[ordered]@{min_x=46450.0;min_y=51050.0;max_x=48450.0;max_y=54400.0}}
  )
}else{
  $views=@([ordered]@{key='relocalize';label='unassigned-stacked-plan-like-region';bounds=[ordered]@{min_x=46400.0;min_y=51000.0;max_x=50800.0;max_y=63100.0}})
}

$renders=@()
foreach($v in $views){
  $params=[ordered]@{name=('case0004-'+$v.key+'-'+$RequestId);width_px=2400;height_px=3200;bounds=$v.bounds}
  if(-not $CandidateViews){$params.width_px=3000;$params.height_px=5000}
  $paramsPath=Join-Path $evidence ($v.key+'-render-params.json')
  [IO.File]::WriteAllText($paramsPath,($params|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  $paramsJson=$params|ConvertTo-Json -Depth 20 -Compress
  $result=& { param($invokePath,$json,$root,$id) Set-StrictMode -Off; & $invokePath -Method 'cad.render_png' -ParamsJson $json -WorkspaceRoot $root -WorkId $id } $invoke $paramsJson $workspace ('directwork-case0004-'+$v.key+'-'+$RequestId)
  if($LASTEXITCODE -ne 0){throw "CASE0004_CANDIDATE_RENDER_FAILED key=$($v.key) exit=$LASTEXITCODE"}
  $text=($result -join "`n")
  $out=Join-Path $evidence ($v.key+'-render.stdout.json')
  [IO.File]::WriteAllText($out,$text+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  $renders+=@([ordered]@{key=$v.key;visually_observed_label=$v.label;review_status='pending';render=($text|ConvertFrom-Json);params_sha256=(Get-FileHash $paramsPath -Algorithm SHA256).Hash.ToLowerInvariant()})
}
$summary=[ordered]@{schema='case0004.directwork.story-relocalize.v2';case_id='0004';request_id=$RequestId;status='succeeded';machine=$env:COMPUTERNAME;authority_commit=[string]$authority.commit;candidate_mode=[bool]$CandidateViews;renders=$renders;completed_at=[DateTimeOffset]::UtcNow.ToString('o')}
[IO.File]::WriteAllText((Join-Path $evidence 'final.json'),($summary|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 80 -Compress
