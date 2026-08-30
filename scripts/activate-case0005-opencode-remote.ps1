param(
 [string]$Workspace='D:\AI-Work\jobs\0005-SNOW-WHITE',
 [string]$OpenWorkerRoot='',
 [string]$GoToolRoot='',
 [string]$EngineeringOSRoot='',
 [string]$PythonExe='',
 [switch]$SkipCodeSync,
 [switch]$RegenerateBridgeSecrets
)
$ErrorActionPreference='Stop'
$expectedHost='DESKTOP-ODAQN0D';if([Environment]::MachineName-ine$expectedHost){throw "Case 0005 remote bridge must activate on $expectedHost"}
if([string]::IsNullOrWhiteSpace($OpenWorkerRoot)){$OpenWorkerRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path}
$base=Join-Path $OpenWorkerRoot 'scripts\activate-case0005-local-supervisor.ps1'
$args=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$base,'-Workspace',$Workspace,'-OpenWorkerRoot',$OpenWorkerRoot)
if(-not[string]::IsNullOrWhiteSpace($GoToolRoot)){$args+=@('-GoToolRoot',$GoToolRoot)}
if(-not[string]::IsNullOrWhiteSpace($EngineeringOSRoot)){$args+=@('-EngineeringOSRoot',$EngineeringOSRoot)}
if(-not[string]::IsNullOrWhiteSpace($PythonExe)){$args+=@('-PythonExe',$PythonExe)}
if($SkipCodeSync){$args+='-SkipCodeSync'}
& powershell.exe @args;if($LASTEXITCODE-ne0){throw "Case 0005 base activation failed: $LASTEXITCODE"}
& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $OpenWorkerRoot 'scripts\install-openworker-opencode-bridge.ps1');if($LASTEXITCODE-ne0){throw "OpenCode bridge install failed: $LASTEXITCODE"}
$startArgs=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $OpenWorkerRoot 'scripts\start-openworker-opencode-bridge.ps1'));if($RegenerateBridgeSecrets){$startArgs+='-RegenerateSecrets'}
$runtimeJSON=& powershell.exe @startArgs;if($LASTEXITCODE-ne0){throw "OpenCode bridge start failed: $LASTEXITCODE"};$runtime=($runtimeJSON|Out-String).Trim()|ConvertFrom-Json
$ctl="$env:ProgramData\OpenWorker\bin\openworkerctl.exe";$statusJSON=& $ctl case status 0005;if($LASTEXITCODE-ne0){throw 'Case 0005 status through openworkerctl failed'};$status=$statusJSON|ConvertFrom-Json
$receipt=[ordered]@{schema='openworker-case0005-opencode-remote-activation/v1';status='LOCAL_REMOTE_BRIDGE_READY';machine=$env:COMPUTERNAME;workspace=$Workspace;opencode=[string]$runtime.opencode;mcp=[string]$runtime.mcp;openworkerctl=$ctl;case_ledger_event_count=[int]$status.ledger_event_count;case_authority=[string]$status.authority;remote_transport='MCP tunnel required outside localhost';github_action_used_for_business_execution=$false;activated_at=[DateTime]::UtcNow.ToString('o')}
$control=Join-Path $Workspace '.openworker';New-Item -ItemType Directory -Force -Path $control|Out-Null;$path=Join-Path $control 'opencode-remote-bridge-activation.json';[IO.File]::WriteAllText($path,($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 8
