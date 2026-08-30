param(
 [string]$StateRoot="$env:ProgramData\OpenWorker\opencode-bridge",
 [switch]$IncludeWriteSmoke
)
$ErrorActionPreference='Stop'
$expected='DESKTOP-ODAQN0D';if([Environment]::MachineName-ine$expected){throw "verification must run on $expected"}
$secretPath=Join-Path $StateRoot 'secrets.json';if(-not(Test-Path $secretPath -PathType Leaf)){throw "bridge secrets missing: $secretPath"};$s=Get-Content -Raw -LiteralPath $secretPath|ConvertFrom-Json;$headers=@{Authorization="Bearer $($s.mcp_token)";Accept='application/json, text/event-stream'}
function Invoke-MCP([int]$Id,[string]$Method,[object]$Params=$null){$o=[ordered]@{jsonrpc='2.0';id=$Id;method=$Method};if($null-ne$Params){$o.params=$Params};$body=$o|ConvertTo-Json -Depth 20 -Compress;return Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8850/mcp' -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 120}
$protocol='2025-06-18';$init=Invoke-MCP 1 'initialize' ([ordered]@{protocolVersion=$protocol;capabilities=@{};clientInfo=[ordered]@{name='openworker-local-verifier';version='1.1'}});if([string]$init.result.serverInfo.name-ne'openworker-opencode-bridge'){throw 'MCP initialize identity mismatch'};if([string]$init.result.protocolVersion-ne$protocol){throw "MCP protocol mismatch: $($init.result.protocolVersion)"}
$tools=Invoke-MCP 2 'tools/list' @{};$names=@($tools.result.tools|ForEach-Object{[string]$_.name});$expectedTools=@('supervisor_status','case_status','case_continue','queue_clear');foreach($n in $expectedTools){if($names-notcontains$n){throw "missing MCP tool: $n"}};if($names.Count-ne4){throw "unexpected MCP tool count: $($names.Count)"}
$supervisor=Invoke-MCP 3 'tools/call' ([ordered]@{name='supervisor_status';arguments=@{}});if([bool]$supervisor.result.isError){throw "supervisor_status failed: $($supervisor.result.content[0].text)"}
$case=Invoke-MCP 4 'tools/call' ([ordered]@{name='case_status';arguments=[ordered]@{case_id='0005'}});if([bool]$case.result.isError){throw "case_status failed: $($case.result.content[0].text)"}
$write=$null;if($IncludeWriteSmoke){$write=Invoke-MCP 5 'tools/call' ([ordered]@{name='case_continue';arguments=[ordered]@{case_id='0005'}});if([bool]$write.result.isError){throw "case_continue failed: $($write.result.content[0].text)"}}
$receipt=[ordered]@{schema='openworker-opencode-mcp-verification/v2';status='LOCAL_VERIFIED';machine=$env:COMPUTERNAME;protocol_version=$protocol;mcp_server=[string]$init.result.serverInfo.name;tools=$names;supervisor_status_via_opencode=$true;case_status_via_opencode=$true;write_smoke_requested=[bool]$IncludeWriteSmoke;write_smoke_passed=$(if($IncludeWriteSmoke){$true}else{$null});github_action_used_for_business_execution=$false;verified_at=[DateTime]::UtcNow.ToString('o')}
$path=Join-Path $StateRoot 'verification-receipt.json';[IO.File]::WriteAllText($path,($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 8
