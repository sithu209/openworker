param(
  [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0004-DWG-TO-3D',
  [string]$CaseManifest = 'case-worklists\0004.json'
)
$ErrorActionPreference='Stop'
if(-not(Test-Path -LiteralPath $WorkspaceRoot -PathType Container)){throw "CASE0004_WORKSPACE_MISSING path=$WorkspaceRoot"}
python scripts\case_worklist_action.py ensure --workspace-root $WorkspaceRoot --manifest $CaseManifest
if($LASTEXITCODE -ne 0){throw 'Case 0004 Worklist ensure failed'}
$raw=python scripts\case_worklist_action.py show --workspace-root $WorkspaceRoot
if($LASTEXITCODE -ne 0){throw 'Case 0004 Worklist show failed'}
$obj=$raw|ConvertFrom-Json
if($obj.case_id -ne '0004'){throw "wrong case_id=$($obj.case_id)"}
if($obj.workspace_root -ne $WorkspaceRoot){throw "workspace mismatch=$($obj.workspace_root)"}
$out=[ordered]@{
  schema='openworker-case0004-node-worklist-state/v1'
  case_id='0004'
  job_id=$env:OPENWORKER_JOB_ID
  agent_slot=$env:OPENWORKER_AGENT_SLOT
  machine=$env:OPENWORKER_MACHINE
  workspace_root=$WorkspaceRoot
  worklist_revision=$obj.revision
  canonical_next_step_id=$obj.canonical_next_step_id
  steps=$obj.steps
  observed_at=[DateTimeOffset]::UtcNow.ToString('o')
}
$dir=Join-Path $WorkspaceRoot '.openworker\evidence'
New-Item -ItemType Directory -Force -Path $dir|Out-Null
$path=Join-Path $dir 'latest-worklist-state-node.json'
[IO.File]::WriteAllText($path,($out|ConvertTo-Json -Depth 50),(New-Object Text.UTF8Encoding($false)))
Write-Output ($out|ConvertTo-Json -Depth 50)
