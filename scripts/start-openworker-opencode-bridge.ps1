param(
 [string]$InstallRoot = "$env:ProgramData\OpenWorker\bin",
 [string]$StateRoot = "$env:ProgramData\OpenWorker\opencode-bridge",
 [switch]$RegenerateSecrets
)
$ErrorActionPreference='Stop'
$expectedHost='DESKTOP-ODAQN0D'
if([Environment]::MachineName-ine$expectedHost){throw "OpenCode bridge must start on $expectedHost"}
$openCode=(Get-Command opencode.exe -ErrorAction SilentlyContinue);if($null-eq$openCode){$openCode=Get-Command opencode -ErrorAction SilentlyContinue};if($null-eq$openCode){throw 'OpenCode CLI not found in PATH'}
$mcpExe=Join-Path $InstallRoot 'openworker-opencode-mcp.exe';$ctlExe=Join-Path $InstallRoot 'openworkerctl.exe';if(-not(Test-Path $mcpExe -PathType Leaf)){throw "MCP bridge not installed: $mcpExe"};if(-not(Test-Path $ctlExe -PathType Leaf)){throw "openworkerctl not installed: $ctlExe"}
New-Item -ItemType Directory -Force -Path $StateRoot|Out-Null
$secretPath=Join-Path $StateRoot 'secrets.json'
function New-Secret([int]$Bytes=32){$b=New-Object byte[] $Bytes;[Security.Cryptography.RandomNumberGenerator]::Fill($b);return[Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_')}
if($RegenerateSecrets-or-not(Test-Path $secretPath -PathType Leaf)){$secrets=[ordered]@{opencode_username='opencode';opencode_password=(New-Secret);mcp_token=(New-Secret);created_at=[DateTime]::UtcNow.ToString('o')};[IO.File]::WriteAllText($secretPath,($secrets|ConvertTo-Json),[Text.UTF8Encoding]::new($false));& icacls.exe $secretPath /inheritance:r /grant:r "$env:USERNAME:(R,W)" |Out-Null}else{$secrets=Get-Content -Raw -LiteralPath $secretPath|ConvertFrom-Json}
$env:OPENCODE_SERVER_USERNAME=[string]$secrets.opencode_username;$env:OPENCODE_SERVER_PASSWORD=[string]$secrets.opencode_password;$env:OPENWORKER_MCP_TOKEN=[string]$secrets.mcp_token
function Test-HTTP([string]$Uri,[hashtable]$Headers=@{}){try{$r=Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers $Headers -TimeoutSec 3;return$r.StatusCode-ge200-and$r.StatusCode-lt300}catch{return$false}}
$basic=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($secrets.opencode_username):$($secrets.opencode_password)"));if(-not(Test-HTTP 'http://127.0.0.1:4096/global/health' @{Authorization="Basic $basic"})){$opLog=Join-Path $StateRoot 'opencode.log';$opErr=Join-Path $StateRoot 'opencode.err.log';Start-Process -FilePath $openCode.Source -ArgumentList @('serve','--hostname','127.0.0.1','--port','4096') -WindowStyle Hidden -RedirectStandardOutput $opLog -RedirectStandardError $opErr;Start-Sleep -Seconds 2}
if(-not(Test-HTTP 'http://127.0.0.1:4096/global/health' @{Authorization="Basic $basic"})){throw 'OpenCode server did not become healthy on localhost:4096'}
if(-not(Test-HTTP 'http://127.0.0.1:8850/health')){$mcpLog=Join-Path $StateRoot 'mcp.log';$mcpErr=Join-Path $StateRoot 'mcp.err.log';Start-Process -FilePath $mcpExe -ArgumentList @('-listen','127.0.0.1:8850') -WindowStyle Hidden -RedirectStandardOutput $mcpLog -RedirectStandardError $mcpErr;Start-Sleep -Seconds 2}
if(-not(Test-HTTP 'http://127.0.0.1:8850/health')){throw 'MCP bridge did not become healthy on localhost:8850'}
$ctlStatus=& $ctlExe supervisor status;if($LASTEXITCODE-ne0){throw 'openworkerctl supervisor status failed'}
$receipt=[ordered]@{schema='openworker-opencode-bridge-runtime/v1';status='LOCAL_READY';machine=$env:COMPUTERNAME;opencode='http://127.0.0.1:4096';mcp='http://127.0.0.1:8850/mcp';mcp_auth='bearer-token';opencode_auth='basic';secret_file=$secretPath;openworkerctl=$ctlExe;github_action_used_for_business_execution=$false;started_at=[DateTime]::UtcNow.ToString('o')}
$receiptPath=Join-Path $StateRoot 'runtime-receipt.json';[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 5
