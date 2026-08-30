param(
  [string]$WorkspaceRoot='D:\AI-Work\jobs\0003-YUJING-BRIDGE'
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd('\')
$evidence=Join-Path $root 'evidence'
$receiptPath=Join-Path $evidence 'case0003-os-artifact-ingest-receipt.json'
if(-not(Test-Path -LiteralPath $receiptPath -PathType Leaf)){return}
$renderPath=Join-Path $root 'acceptance\render\render-acceptance.json'
$reasons=@()
if(-not(Test-Path -LiteralPath $renderPath -PathType Leaf)){$reasons+='current render acceptance missing'}
$render=$null;if($reasons.Count -eq 0){try{$render=Get-Content -LiteralPath $renderPath -Raw|ConvertFrom-Json}catch{$reasons+='render acceptance unreadable'}}
$r=$null;try{$r=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json}catch{$reasons+='OS artifact receipt unreadable'}
if($null -ne $r){
  if([string]$r.schema_version -notin @('engineering-os-artifact-ingest-receipt/v2','engineering-os-artifact-ingest-receipt/v1')){$reasons+='unsupported OS artifact receipt schema'}
  $binding=$r.source_binding
  if($null -eq $binding){$reasons+='OS artifact receipt source_binding missing'}
  elseif($null -ne $render){
    if([string]$binding.render_fingerprint -ne [string]$render.fingerprint){$reasons+='render fingerprint mismatch'}
    if([string]$binding.blender_fingerprint -ne [string]$render.blender_fingerprint){$reasons+='Blender fingerprint mismatch'}
    if([string]$binding.scenex_fingerprint -ne [string]$render.scenex_fingerprint){$reasons+='SceneX fingerprint mismatch'}
  }
}
if($reasons.Count -gt 0){
  $stamp=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
  $q=Join-Path $root ('.openworker\quarantine\os-artifacts\'+$stamp);New-Item -ItemType Directory -Force -Path $q|Out-Null
  foreach($name in @('case0003-os-artifact-ingest-receipt.json','case0003-os-artifact-ingest.json','case0003-os-artifacts-submit.json')){$p=Join-Path $evidence $name;if(Test-Path -LiteralPath $p -PathType Leaf){Move-Item -LiteralPath $p -Destination (Join-Path $q $name) -Force}}
  [ordered]@{schema_version='openworker-case0003-os-artifact-quarantine/v1';status='QUARANTINED';reasons=$reasons;quarantine_dir=$q;checked_at=[DateTimeOffset]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $q 'quarantine-receipt.json') -Encoding utf8
  Write-Warning ('CASE0003_OS_ARTIFACT_QUARANTINED '+($reasons -join '; '));return
}
if([string]$r.schema_version -eq 'engineering-os-artifact-ingest-receipt/v2'){
  $rawCopy=Join-Path $evidence 'case0003-os-artifact-ingest-receipt-v2.json'
  Copy-Item -LiteralPath $receiptPath -Destination $rawCopy -Force
  $r | Add-Member -NotePropertyName semantic_contract_version -NotePropertyValue 'engineering-os-artifact-ingest-receipt/v2' -Force
  $r.schema_version='engineering-os-artifact-ingest-receipt/v1'
  $r|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $receiptPath -Encoding utf8
}
