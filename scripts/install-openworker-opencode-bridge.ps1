param(
 [string]$InstallRoot = "$env:ProgramData\OpenWorker\bin"
)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$goRoot=Join-Path $repoRoot 'go-runtime'
if(-not(Test-Path -LiteralPath (Join-Path $goRoot 'go.mod') -PathType Leaf)){throw "go-runtime module missing: $goRoot"}
# openworkerctl is part of the same local control chain and must be installed first.
& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'scripts\install-openworkerctl.ps1') -InstallRoot $InstallRoot
if($LASTEXITCODE-ne 0){throw "openworkerctl install failed: $LASTEXITCODE"}
New-Item -ItemType Directory -Force -Path $InstallRoot|Out-Null
$target=Join-Path $InstallRoot 'openworker-opencode-mcp.exe'
Push-Location $goRoot
try{
 & go test ./cmd/openworker-opencode-mcp -count=1
 if($LASTEXITCODE-ne 0){throw "openworker-opencode-mcp tests failed: $LASTEXITCODE"}
 & go build -trimpath -o $target ./cmd/openworker-opencode-mcp
 if($LASTEXITCODE-ne 0){throw "openworker-opencode-mcp build failed: $LASTEXITCODE"}
}finally{Pop-Location}
$result=[ordered]@{schema='openworker-opencode-bridge-install/v1';status='installed';machine=$env:COMPUTERNAME;mcp_exe=$target;openworkerctl=(Join-Path $InstallRoot 'openworkerctl.exe');mcp_local_url='http://127.0.0.1:8850/mcp';opencode_local_url='http://127.0.0.1:4096';github_action_used_for_business_execution=$false;installed_at=[DateTime]::UtcNow.ToString('o')}
$result|ConvertTo-Json -Depth 5
