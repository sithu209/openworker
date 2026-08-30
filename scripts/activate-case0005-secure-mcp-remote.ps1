param(
 [string]$TunnelId = $env:CONTROL_PLANE_TUNNEL_ID,
 [string]$TunnelClientVersion = 'v0.0.10',
 [string]$Workspace = 'D:\AI-Work\jobs\0005-SNOW-WHITE',
 [switch]$SkipCaseActivation
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$expected='DESKTOP-ODAQN0D';if([Environment]::MachineName-ine$expected){throw "activation must run on $expected"}
if([string]::IsNullOrWhiteSpace($TunnelId)-or$TunnelId-notmatch '^tunnel_[0-9a-f]{32}$'){throw 'valid CONTROL_PLANE_TUNNEL_ID required'}
if([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)){throw 'CONTROL_PLANE_API_KEY required (restricted runtime key: Tunnels Read + Use)'}
function Invoke-JsonScript([string]$Path,[string[]]$Args=@()){
 $out=& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Path @Args
 if($LASTEXITCODE-ne0){throw "script failed: $Path exit=$LASTEXITCODE"}
 $text=($out|Out-String).Trim();if([string]::IsNullOrWhiteSpace($text)){throw "script returned no JSON: $Path"}
 try{return $text|ConvertFrom-Json}catch{throw "script returned invalid JSON: $Path`n$text"}
}
if(-not$SkipCaseActivation){
 $caseOut=& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\activate-case0005-local-supervisor.ps1') -Workspace $Workspace -SkipCodeSync
 if($LASTEXITCODE-ne0){throw 'Case 0005 local-supervisor activation failed'}
}
$installBridge=Invoke-JsonScript (Join-Path $root 'scripts\install-openworker-opencode-bridge.ps1')
if([string]$installBridge.status-ne'installed'){throw 'OpenCode bridge install receipt invalid'}
$bridge=Invoke-JsonScript (Join-Path $root 'scripts\start-openworker-opencode-bridge.ps1')
if([string]$bridge.status-ne'LOCAL_READY'){throw 'OpenCode bridge runtime is not LOCAL_READY'}
$bridgeVerify=Invoke-JsonScript (Join-Path $root 'scripts\verify-openworker-opencode-bridge.ps1')
if([string]$bridgeVerify.status-ne'LOCAL_VERIFIED'){throw 'OpenCode bridge is not LOCAL_VERIFIED'}
$tunnelInstall=Invoke-JsonScript (Join-Path $root 'scripts\install-openai-secure-mcp-tunnel-client.ps1') @('-Version',$TunnelClientVersion)
if([string]$tunnelInstall.status-ne'installed'){throw 'Secure MCP Tunnel client install receipt invalid'}
$tunnel=Invoke-JsonScript (Join-Path $root 'scripts\start-openworker-secure-mcp-tunnel.ps1') @('-TunnelId',$TunnelId)
if([string]$tunnel.status-ne'READY'-or[string]$tunnel.tunnel_id-ne$TunnelId){throw 'Secure MCP Tunnel runtime receipt invalid'}
$tunnelVerify=Invoke-JsonScript (Join-Path $root 'scripts\verify-openworker-secure-mcp-tunnel.ps1') @('-TunnelId',$TunnelId)
if([string]$tunnelVerify.status-ne'TUNNEL_VERIFIED'-or[string]$tunnelVerify.tunnel_id-ne$TunnelId){throw 'Secure MCP Tunnel verification receipt invalid'}
$control=Join-Path $Workspace '.openworker';New-Item -ItemType Directory -Force -Path $control|Out-Null
$ledger=Join-Path $control 'case-supervisor-ledger.jsonl'
$receipt=[ordered]@{schema='case0005-secure-mcp-remote-activation/v2';status='REMOTE_TRANSPORT_READY';case_id='0005';machine=$env:COMPUTERNAME;workspace_root=$Workspace;tunnel_id=$TunnelId;tunnel_client_version=[string]$tunnelInstall.version;tunnel_client_commit=[string]$tunnelInstall.commit;bridge_status=[string]$bridge.status;bridge_verification_status=[string]$bridgeVerify.status;tunnel_status=[string]$tunnel.status;tunnel_verification_status=[string]$tunnelVerify.status;chain=@('OpenAI Secure MCP Tunnel','openworker-opencode-mcp:8850','OpenCode:4096','openworkerctl','go-tool:8848','OpenWorker:8787');github_actions_used_for_business_execution=$false;activated_at=[DateTime]::UtcNow.ToString('o')}
$state="$env:ProgramData\OpenWorker\secure-mcp-tunnel";New-Item -ItemType Directory -Force -Path $state|Out-Null
$receiptJson=$receipt|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $state 'case0005-remote-activation.json'),$receiptJson,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $control 'secure-mcp-remote-activation.json'),$receiptJson,[Text.UTF8Encoding]::new($false))
$event=[ordered]@{schema='openworker-case-supervisor-event/v1';event_type='remote_transport_ready';case_id='0005';machine=$env:COMPUTERNAME;workspace_root=$Workspace;transport='openai-secure-mcp-tunnel';tunnel_id=$TunnelId;bridge_verification_status=[string]$bridgeVerify.status;tunnel_verification_status=[string]$tunnelVerify.status;github_action_used_for_business_execution=$false;observed_at=[DateTime]::UtcNow.ToString('o')}
[IO.File]::AppendAllText($ledger,(($event|ConvertTo-Json -Depth 6 -Compress)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
$receipt|ConvertTo-Json -Depth 8
