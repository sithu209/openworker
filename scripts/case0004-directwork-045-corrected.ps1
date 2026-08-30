param([Parameter(Mandatory=$true)][string]$RequestId)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:COMPUTERNAME -ine 'DESKTOP-O87PJNR'){throw "CASE0004_WRONG_HOST actual=$env:COMPUTERNAME"}
$workspace='D:\AI-Work\jobs\0004-DWG-TO-3D'
$evidence=Join-Path $workspace ('evidence\directwork\'+$RequestId)
New-Item -ItemType Directory -Force -Path $evidence|Out-Null

$query=[ordered]@{session_id=('case0004-corrected-045-'+$RequestId);project='DWG_todo Case 0004';workspace_root=$workspace;question='Confirm the current registered contracts for cad.build_story_index and cad.render_story_viewports. Values below are from REAL rendered and visually reviewed evidence; do not invent or execute business values.';task='Provide method guidance only for corrected Case0004 story index materialization and viewport rendering.'}
$goTool=$null
try{$goTool=Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8848/agent/query' -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 20) -TimeoutSec 60}catch{$goTool=[ordered]@{error=$_.Exception.Message}}
[IO.File]::WriteAllText((Join-Path $evidence 'go-tool-query.json'),($goTool|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$pointer=Join-Path $env:ProgramData 'go-tool-runtime\work-agent\authorities\dwg-todo-current.json'
if(-not(Test-Path -LiteralPath $pointer -PathType Leaf)){throw "DWG_AUTHORITY_POINTER_MISSING path=$pointer"}
$authority=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
$authorityRoot=[string]$authority.root
$invoke=Join-Path $authorityRoot 'scripts\invoke-agent-cad-local.ps1'
if(-not(Test-Path -LiteralPath $invoke -PathType Leaf)){throw "DWG_LOCAL_WRAPPER_MISSING path=$invoke"}

# Durable broad render authority: PR126 camera 46400,51000,50800,63100 at 3000x5000.
# Pixel bounds below are the exact inverse-projection of the visually accepted PR130 world windows,
# using DWG_todo storyIndexPixelToWorld geometry (10 px margin, fit scale). They are fixed here to
# avoid Windows PowerShell 5.1 arithmetic/type ambiguity observed in failed work seq61-64.
$camera=[ordered]@{min_x=46400.0;min_y=51000.0;max_x=50800.0;max_y=63100.0}
$stories=@(
  [ordered]@{story_id='1F';pixel_bounds=@(1253.0578512396694,1265.2892561983472,2199.669421487603,2479.4214876033056);confidence=1.0;visual_basis='REAL V2 candidate PNG visually reviewed: ground-floor plan; previous deterministic 1F elevation rejected';reconcile_existing=$true;reconcile_reason='previous deterministic 1F viewport visually rejected as elevation; corrected from REAL ground-floor-plan candidate evidence'},
  [ordered]@{story_id='2F';pixel_bounds=@(615.1239669421487,2397.107438016529,1417.6859504132233,3672.9752066115702);confidence=1.0;visual_basis='REAL V2 candidate PNG visually reviewed: second-floor plan'},
  [ordered]@{story_id='3F';pixel_bounds=@(1232.4793388429753,2397.107438016529,2179.090909090909,3672.9752066115702);confidence=1.0;visual_basis='REAL V2 candidate PNG visually reviewed: shared third-to-fourth-floor plan'},
  [ordered]@{story_id='4F';pixel_bounds=@(1232.4793388429753,2397.107438016529,2179.090909090909,3672.9752066115702);confidence=1.0;visual_basis='REAL V2 candidate PNG visually reviewed: shared third-to-fourth-floor plan'},
  [ordered]@{story_id='R1F';pixel_bounds=@(615.1239669421487,3590.6611570247933,1438.2644628099174,4969.421487603306);confidence=1.0;visual_basis='REAL V2 candidate PNG visually reviewed: penthouse first-floor plan'}
)
$buildParams=[ordered]@{name='case0004-story-index';camera_bounds=$camera;image_width=3000;image_height=5000;stories=$stories}
$buildParamsPath=Join-Path $evidence 'corrected-story-index-params.json'
[IO.File]::WriteAllText($buildParamsPath,($buildParams|ConvertTo-Json -Depth 50)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$buildJson=$buildParams|ConvertTo-Json -Depth 50 -Compress
$build=& {param($p,$j,$root,$id) Set-StrictMode -Off; & $p -Method 'cad.build_story_index' -ParamsJson $j -WorkspaceRoot $root -WorkId $id} $invoke $buildJson $workspace ('directwork-case0004-corrected-index-'+$RequestId)
if($LASTEXITCODE -ne 0){throw "CASE0004_CORRECTED_STORY_INDEX_FAILED exit=$LASTEXITCODE"}
$buildText=($build -join "`n")
$buildOut=Join-Path $evidence 'cad-build-story-index.stdout.json'
[IO.File]::WriteAllText($buildOut,$buildText+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$buildObj=$buildText|ConvertFrom-Json
if([int]$buildObj.result.story_count -ne 5){throw "CASE0004_STORY_COUNT_NOT_5 actual=$($buildObj.result.story_count)"}

$renderParams=[ordered]@{name='case0004-story-index';width_px=2400;height_px=3200;story_ids=@('1F','2F','3F','4F','R1F')}
$renderParamsPath=Join-Path $evidence 'story-viewport-render-params.json'
[IO.File]::WriteAllText($renderParamsPath,($renderParams|ConvertTo-Json -Depth 30)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$renderJson=$renderParams|ConvertTo-Json -Depth 30 -Compress
$render=& {param($p,$j,$root,$id) Set-StrictMode -Off; & $p -Method 'cad.render_story_viewports' -ParamsJson $j -WorkspaceRoot $root -WorkId $id} $invoke $renderJson $workspace ('directwork-case0004-story-viewports-'+$RequestId)
if($LASTEXITCODE -ne 0){throw "CASE0004_STORY_VIEWPORT_RENDER_FAILED exit=$LASTEXITCODE"}
$renderText=($render -join "`n")
$renderOut=Join-Path $evidence 'cad-render-story-viewports.stdout.json'
[IO.File]::WriteAllText($renderOut,$renderText+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$renderObj=$renderText|ConvertFrom-Json
if([int]$renderObj.result.story_count -ne 5){throw "CASE0004_VIEWPORT_COUNT_NOT_5 actual=$($renderObj.result.story_count)"}

$summary=[ordered]@{schema='case0004.directwork.corrected-045.v2';case_id='0004';step='0004-045';request_id=$RequestId;status='succeeded';machine=$env:COMPUTERNAME;authority_root=$authorityRoot;authority_commit=[string]$authority.commit;source_candidate_work_id='dw-20260820T080310-d2afff3075cd8205';source_candidate_png_sha256=@{'1F'='1b043e00826d3ed55024a226ed7f96ea4eafbfa941e48f886e47e62967128a3d';'2F'='c2352fc8e0791b5dc34253f3db4804a1cf7efb39d93a25d497260cc9aee1f5a0';'3F-4F'='9f518fb4c9cf959e97c620e6a9df4fb1f9ee8dc7f1e509d5d6b053245f15287b';'R1F'='bd7a66f8173eb01628af32d27d766b98ac624ce139ec7194ecd47fb81a246c4b'};build_params_sha256=(Get-FileHash -LiteralPath $buildParamsPath -Algorithm SHA256).Hash.ToLowerInvariant();build_receipt_sha256=(Get-FileHash -LiteralPath $buildOut -Algorithm SHA256).Hash.ToLowerInvariant();render_params_sha256=(Get-FileHash -LiteralPath $renderParamsPath -Algorithm SHA256).Hash.ToLowerInvariant();render_receipt_sha256=(Get-FileHash -LiteralPath $renderOut -Algorithm SHA256).Hash.ToLowerInvariant();story_count=[int]$buildObj.result.story_count;reconciled_entity_count=[int]$buildObj.result.reconciled_entity_count;reused_entity_count=[int]$buildObj.result.reused_entity_count;viewport_story_count=[int]$renderObj.result.story_count;viewport_manifest=[string]$renderObj.result.manifest_path;review_required=$true;completed_at=[DateTimeOffset]::UtcNow.ToString('o')}
[IO.File]::WriteAllText((Join-Path $evidence 'final.json'),($summary|ConvertTo-Json -Depth 50)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 50 -Compress
