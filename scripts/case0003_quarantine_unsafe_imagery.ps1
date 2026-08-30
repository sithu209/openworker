param(
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE'
)
$ErrorActionPreference='Stop'
$workspace=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorkspaceRoot).Path).TrimEnd('\','/')
function In-Workspace([string]$Path){
  if([string]::IsNullOrWhiteSpace($Path)){return $false}
  try{$full=[IO.Path]::GetFullPath($Path)}catch{return $false}
  if($full.Equals($workspace,[StringComparison]::OrdinalIgnoreCase)){return $true}
  return $full.StartsWith($workspace+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)
}
function Read-Json([string]$Path){if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null};try{return Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}catch{return $null}}
$issues=@()
$svPath=Join-Path $workspace 'streetview\browser\streetview-browser-screenshots.json'
$sv=Read-Json $svPath
if($null -ne $sv -and [string]$sv.schema_version -eq 'streetview-browser-screenshots/v3'){
  foreach($r in @($sv.renders)){
    if(-not(In-Workspace ([string]$r.path))){$issues+=@{kind='streetview';manifest=$svPath;reason="render path escapes workspace: $([string]$r.path)"};break}
    if($null -ne $r.receipt -and -not[string]::IsNullOrWhiteSpace([string]$r.receipt.output) -and -not(In-Workspace ([string]$r.receipt.output))){$issues+=@{kind='streetview';manifest=$svPath;reason="receipt output escapes workspace: $([string]$r.receipt.output)"};break}
  }
}
$orthoPath=Join-Path $workspace 'orthophoto\nlsc-photo2\orthophoto-photo2-workspace.json'
$ortho=Read-Json $orthoPath
if($null -ne $ortho -and [string]$ortho.schema_version -eq 'orthophoto-workspace/v2'){
  foreach($p in @([string]$ortho.image,[string]$ortho.evidence)){
    if(-not(In-Workspace $p)){$issues+=@{kind='orthophoto';manifest=$orthoPath;reason="artifact path escapes workspace: $p"};break}
  }
  if($null -ne $ortho.producer_receipt -and -not[string]::IsNullOrWhiteSpace([string]$ortho.producer_receipt.output_path) -and -not(In-Workspace ([string]$ortho.producer_receipt.output_path))){$issues+=@{kind='orthophoto';manifest=$orthoPath;reason="producer output escapes workspace: $([string]$ortho.producer_receipt.output_path)"}}
}
if($issues.Count -eq 0){
  [ordered]@{schema='openworker/case0003-imagery-workspace-quarantine/v1';ok=$true;quarantined=@();checked_at=[DateTimeOffset]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 6|Write-Host
  exit 0
}
$qdir=Join-Path $workspace '.openworker\quarantine\imagery';New-Item -ItemType Directory -Force -Path $qdir|Out-Null
$stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$moved=@()
foreach($issue in $issues){
  $src=[string]$issue.manifest
  if(-not(Test-Path -LiteralPath $src -PathType Leaf)){continue}
  $name=[IO.Path]::GetFileNameWithoutExtension($src)+'-'+$stamp+'.rejected.json'
  $dst=Join-Path $qdir $name
  Move-Item -LiteralPath $src -Destination $dst
  $moved+=@{kind=$issue.kind;source=$src;quarantine=$dst;reason=$issue.reason;sha256=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$receipt=[ordered]@{schema='openworker/case0003-imagery-workspace-quarantine/v1';ok=$true;quarantined=$moved;checked_at=[DateTimeOffset]::UtcNow.ToString('o')}
$evidenceDir=Join-Path $workspace 'evidence';New-Item -ItemType Directory -Force -Path $evidenceDir|Out-Null
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidenceDir 'case0003-imagery-workspace-quarantine.json') -Encoding utf8
$receipt|ConvertTo-Json -Depth 8|Write-Host
