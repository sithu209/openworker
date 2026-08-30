param([Parameter(Mandatory=$true)][string]$RequestId)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:COMPUTERNAME -ine 'DESKTOP-O87PJNR'){throw "CASE0004_WRONG_HOST actual=$env:COMPUTERNAME"}
$workspace='D:\AI-Work\jobs\0004-DWG-TO-3D'
if(-not(Test-Path -LiteralPath $workspace -PathType Container)){throw "CASE0004_WORKSPACE_MISSING path=$workspace"}
$evidence=Join-Path $workspace ('evidence\directwork\'+$RequestId)
New-Item -ItemType Directory -Force -Path $evidence|Out-Null

$query=[ordered]@{
  session_id=('case0004-directwork-'+$RequestId)
  project='DWG_todo Case 0004'
  workspace_root=$workspace
  question='For current Case0004 step 0004-045, identify the registered method cad.build_story_index, its required parameters, and any current machine-local evidence/capability that can supply camera_bounds, image_width, image_height, and stories[].pixel_bounds. Do not guess values or claim execution.'
  task='Prepare exact current tool guidance for DirectWork durable execution of Case0004 step 0004-045.'
}
$goTool=$null
try{$goTool=Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8848/agent/query' -ContentType 'application/json' -Body ($query|ConvertTo-Json -Depth 20) -TimeoutSec 60}catch{$goTool=[ordered]@{error=$_.Exception.Message}}
[IO.File]::WriteAllText((Join-Path $evidence 'go-tool-query.json'),($goTool|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$pointer=Join-Path $env:ProgramData 'go-tool-runtime\work-agent\authorities\dwg-todo-current.json'
if(-not(Test-Path -LiteralPath $pointer -PathType Leaf)){throw "DWG_AUTHORITY_POINTER_MISSING path=$pointer"}
$authority=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
$authorityRoot=[string]$authority.root
if(-not(Test-Path -LiteralPath $authorityRoot -PathType Container)){throw "DWG_AUTHORITY_ROOT_MISSING path=$authorityRoot"}
$invoke=Join-Path $authorityRoot 'scripts\invoke-agent-cad-local.ps1'
if(-not(Test-Path -LiteralPath $invoke -PathType Leaf)){throw "DWG_LOCAL_WRAPPER_MISSING path=$invoke"}

function Find-StoryParams($node){
  if($null-eq$node){return $null}
  if($node -is [System.Collections.IDictionary]){
    if($node.Contains('camera_bounds') -and $node.Contains('image_width') -and $node.Contains('image_height') -and $node.Contains('stories')){return $node}
    foreach($k in @($node.Keys)){ $r=Find-StoryParams $node[$k]; if($null-ne$r){return $r} }
    return $null
  }
  if($node -is [System.Collections.IEnumerable] -and -not($node -is [string])){
    foreach($x in $node){$r=Find-StoryParams $x;if($null-ne$r){return $r}}
    return $null
  }
  $psobj=$node.PSObject
  if($null-ne$psobj){
    $props=@($psobj.Properties)
    if($props.Count -gt 0){
      $names=@($props | ForEach-Object { [string]$_.Name })
      if($names -contains 'camera_bounds' -and $names -contains 'image_width' -and $names -contains 'image_height' -and $names -contains 'stories'){return $node}
      foreach($p in $props){$r=Find-StoryParams $p.Value;if($null-ne$r){return $r}}
    }
  }
  return $null
}

$params=$null;$sourcePath='';$checked=0
$files=@(Get-ChildItem -LiteralPath $workspace -Recurse -File -Filter '*.json' -ErrorAction SilentlyContinue | Where-Object {$_.Length -lt 20MB} | Sort-Object LastWriteTimeUtc -Descending)
foreach($f in $files){
  $checked++
  try{$obj=Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8|ConvertFrom-Json}catch{continue}
  $candidate=Find-StoryParams $obj
  if($null-ne$candidate){$params=$candidate;$sourcePath=$f.FullName;break}
}
if($null-eq$params){
  $block=[ordered]@{schema='case0004.directwork.blocker.v1';case_id='0004';step='0004-045';request_id=$RequestId;reason='REAL Story Index localization parameters not found in current O87 workspace; values were not guessed';json_files_checked=$checked;go_tool_query=(Join-Path $evidence 'go-tool-query.json');workspace_root=$workspace;authority_root=$authorityRoot;observed_at=[DateTimeOffset]::UtcNow.ToString('o')}
  [IO.File]::WriteAllText((Join-Path $evidence 'blocker.json'),($block|ConvertTo-Json -Depth 30)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
  throw 'CASE0004_045_REAL_LOCALIZATION_PARAMS_MISSING'
}
$paramsJson=$params|ConvertTo-Json -Depth 80 -Compress
[IO.File]::WriteAllText((Join-Path $evidence 'story-index-params.json'),($params|ConvertTo-Json -Depth 80)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$workId=('directwork-case0004-045-'+$RequestId).ToLowerInvariant()
# The authority wrapper predates the caller's StrictMode policy. Run it in a child
# scope with StrictMode disabled so a successful response that omits optional
# properties is not converted into a false business failure.
$result=& {
  param($invokePath,$json,$root,$id)
  Set-StrictMode -Off
  & $invokePath -Method 'cad.build_story_index' -ParamsJson $json -WorkspaceRoot $root -WorkId $id
} $invoke $paramsJson $workspace $workId
if($LASTEXITCODE -ne 0){throw "CASE0004_045_CAD_FAILED exit=$LASTEXITCODE"}
$resultText=($result -join "`n")
[IO.File]::WriteAllText((Join-Path $evidence 'cad-build-story-index.stdout.json'),$resultText+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary=[ordered]@{schema='case0004.directwork.045.v1';case_id='0004';step='0004-045';request_id=$RequestId;status='succeeded';machine=$env:COMPUTERNAME;workspace_root=$workspace;authority_root=$authorityRoot;authority_commit=[string]$authority.commit;params_source=$sourcePath;params_sha256=(Get-FileHash -LiteralPath (Join-Path $evidence 'story-index-params.json') -Algorithm SHA256).Hash.ToLowerInvariant();go_tool_query=(Join-Path $evidence 'go-tool-query.json');cad_receipt=(Join-Path $evidence 'cad-build-story-index.stdout.json');completed_at=[DateTimeOffset]::UtcNow.ToString('o')}
[IO.File]::WriteAllText((Join-Path $evidence 'final.json'),($summary|ConvertTo-Json -Depth 30)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 30 -Compress
