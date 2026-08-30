param(
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [string]$InstallRoot='C:\ProgramData\OpenWorker\runtime\openworker'
)
$ErrorActionPreference='Stop'
$SourceRoot=(Resolve-Path -LiteralPath $SourceRoot).Path
$required=@('coworker','case-worklists','case-specs')
foreach($name in $required){if(-not(Test-Path -LiteralPath (Join-Path $SourceRoot $name))){throw "missing Case runtime source: $name"}}
New-Item -ItemType Directory -Force -Path $InstallRoot|Out-Null
foreach($name in $required){
  $src=Join-Path $SourceRoot $name
  $dst=Join-Path $InstallRoot $name
  if(Test-Path -LiteralPath $dst){Remove-Item -LiteralPath $dst -Recurse -Force}
  Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
}
foreach($name in @('pyproject.toml')){
  $src=Join-Path $SourceRoot $name
  if(Test-Path -LiteralPath $src -PathType Leaf){Copy-Item -LiteralPath $src -Destination (Join-Path $InstallRoot $name) -Force}
}
$marker=[ordered]@{
  schema='openworker.case-runtime-install/v1'
  authority='openworker-local-supervisor'
  source_root=$SourceRoot
  install_root=$InstallRoot
  source_commit=$env:GITHUB_SHA
  machine=$env:COMPUTERNAME
  installed_at=[DateTimeOffset]::UtcNow.ToString('o')
  durable_runtime=$true
  github_action_used_for_business_execution=$false
}
$markerPath=Join-Path $InstallRoot '.openworker-runtime.json'
[IO.File]::WriteAllText($markerPath,($marker|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$marker|ConvertTo-Json -Depth 8
