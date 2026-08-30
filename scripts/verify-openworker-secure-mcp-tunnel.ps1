param(
 [string]$StateRoot = "$env:ProgramData\OpenWorker\secure-mcp-tunnel",
 [string]$TunnelId = $env:CONTROL_PLANE_TUNNEL_ID
)
$ErrorActionPreference='Stop'
$expected='DESKTOP-ODAQN0D';if([Environment]::MachineName-ine$expected){throw "verification must run on $expected"}
if([string]::IsNullOrWhiteSpace($TunnelId)-or$TunnelId-notmatch '^tunnel_[0-9a-f]{32}$'){throw 'valid CONTROL_PLANE_TUNNEL_ID required'}
$receiptPath=Join-Path $StateRoot 'runtime-receipt.json';if(-not(Test-Path -LiteralPath $receiptPath -PathType Leaf)){throw "runtime receipt missing: $receiptPath"};$runtime=Get-Content -Raw -LiteralPath $receiptPath|ConvertFrom-Json
if([string]$runtime.status-ne'READY'){throw "runtime status is not READY: $($runtime.status)"};if([string]$runtime.tunnel_id-ne$TunnelId){throw 'tunnel id mismatch'}
$health=Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8851/healthz' -TimeoutSec 5
$ready=Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8851/readyz' -TimeoutSec 5
# readyz may be JSON or text depending on tunnel-client version; HTTP 200 is authoritative.
if([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)){throw 'CONTROL_PLANE_API_KEY required for control-plane metadata verification'}
$exe="$env:ProgramData\OpenWorker\tunnel-client\tunnel-client.exe";if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw "tunnel-client executable missing: $exe"}
$metadata=& $exe admin tunnels get $TunnelId --json 2>&1
if($LASTEXITCODE-ne0){throw "tunnel metadata lookup failed: $($metadata|Out-String)"}
$metadataText=($metadata|Out-String).Trim();$metadataJSON=$null;try{$metadataJSON=$metadataText|ConvertFrom-Json}catch{throw "tunnel metadata output is not JSON: $metadataText"}
$receipt=[ordered]@{schema='openworker-secure-mcp-tunnel-verification/v1';status='TUNNEL_VERIFIED';machine=$env:COMPUTERNAME;tunnel_id=$TunnelId;local_health_http_200=$true;local_ready_http_200=$true;control_plane_metadata_resolved=$true;mcp_target=[string]$runtime.mcp_target;github_actions_used_for_business_execution=$false;verified_at=[DateTime]::UtcNow.ToString('o')}
$out=Join-Path $StateRoot 'verification-receipt.json';[IO.File]::WriteAllText($out,($receipt|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 6
