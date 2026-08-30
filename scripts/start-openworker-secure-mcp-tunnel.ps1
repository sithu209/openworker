param(
 [string]$TunnelId = $env:CONTROL_PLANE_TUNNEL_ID,
 [string]$InstallRoot = "$env:ProgramData\OpenWorker\tunnel-client",
 [string]$BridgeStateRoot = "$env:ProgramData\OpenWorker\opencode-bridge",
 [string]$StateRoot = "$env:ProgramData\OpenWorker\secure-mcp-tunnel"
)
$ErrorActionPreference='Stop'
$expected='DESKTOP-ODAQN0D';if([Environment]::MachineName-ine$expected){throw "Secure MCP Tunnel must start on $expected"}
if([string]::IsNullOrWhiteSpace($TunnelId)-or$TunnelId-notmatch '^tunnel_[0-9a-f]{32}$'){throw 'CONTROL_PLANE_TUNNEL_ID must be tunnel_ followed by 32 lowercase hex characters'}
if([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)){throw 'CONTROL_PLANE_API_KEY is required; use a restricted runtime key with Tunnels Read + Use'}
$exe=Join-Path $InstallRoot 'tunnel-client.exe';if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw "tunnel-client not installed: $exe"}
$bridgeSecrets=Join-Path $BridgeStateRoot 'secrets.json';if(-not(Test-Path -LiteralPath $bridgeSecrets -PathType Leaf)){throw "OpenCode bridge secrets missing: $bridgeSecrets"};$secrets=Get-Content -Raw -LiteralPath $bridgeSecrets|ConvertFrom-Json
$token=[string]$secrets.mcp_token;if([string]::IsNullOrWhiteSpace($token)){throw 'OpenCode bridge MCP token missing'}
New-Item -ItemType Directory -Force -Path $StateRoot|Out-Null
$healthFile=Join-Path $StateRoot 'health-url.txt';if(Test-Path $healthFile){Remove-Item $healthFile -Force}
# Keep all sensitive or whitespace-bearing configuration in inherited environment.
$env:OPENWORKER_MCP_AUTH="Bearer $token"
$env:CONTROL_PLANE_TUNNEL_ID=$TunnelId
$env:MCP_SERVER_URL='http://127.0.0.1:8850/mcp'
$env:MCP_EXTRA_HEADERS='Authorization: env:OPENWORKER_MCP_AUTH'
$env:MCP_DISCOVERY_EXTRA_HEADERS='Authorization: env:OPENWORKER_MCP_AUTH'
$env:HEALTH_LISTEN_ADDR='127.0.0.1:8851'
$env:HEALTH_URL_FILE=$healthFile
$stdout=Join-Path $StateRoot 'tunnel-client.log';$stderr=Join-Path $StateRoot 'tunnel-client.err.log'
$pidFile=Join-Path $StateRoot 'pid.txt';if(Test-Path $pidFile){$oldPid=[int](Get-Content -Raw $pidFile);$old=Get-Process -Id $oldPid -ErrorAction SilentlyContinue;if($null-ne$old){Stop-Process -Id $oldPid -Force;Start-Sleep -Milliseconds 500}}
# argv contains no tunnel key, MCP bearer value, or compound header value.
$p=Start-Process -FilePath $exe -ArgumentList @('run','--log.level','info','--log.format','json') -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
[IO.File]::WriteAllText($pidFile,[string]$p.Id,[Text.UTF8Encoding]::new($false))
$deadline=[DateTime]::UtcNow.AddSeconds(30);$ready=$false;while([DateTime]::UtcNow-lt$deadline){if($p.HasExited){break};try{$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8851/readyz' -TimeoutSec 2;if($r.StatusCode-eq200){$ready=$true;break}}catch{};Start-Sleep -Milliseconds 500}
if(-not$ready){$tail='';if(Test-Path $stderr){$tail=(Get-Content -Tail 30 $stderr)-join"`n"};throw "tunnel-client not ready on 127.0.0.1:8851; pid=$($p.Id)`n$tail"}
$receipt=[ordered]@{schema='openworker-secure-mcp-tunnel-runtime/v2';status='READY';machine=$env:COMPUTERNAME;tunnel_id=$TunnelId;process_id=$p.Id;mcp_target='http://127.0.0.1:8850/mcp';health_url='http://127.0.0.1:8851';auth_to_local_mcp='static-bearer-via-env-reference';control_plane_key_source='env:CONTROL_PLANE_API_KEY';configuration_transport='environment';secrets_present_in_argv=$false;inbound_firewall_required=$false;github_actions_used_for_business_execution=$false;started_at=[DateTime]::UtcNow.ToString('o')}
$receiptPath=Join-Path $StateRoot 'runtime-receipt.json';[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 5
