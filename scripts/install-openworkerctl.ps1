param(
 [string]$InstallRoot = "$env:ProgramData\OpenWorker\bin"
)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$goRoot=Join-Path $repoRoot 'go-runtime'
if(-not(Test-Path -LiteralPath (Join-Path $goRoot 'go.mod') -PathType Leaf)){throw "go-runtime module missing: $goRoot"}
New-Item -ItemType Directory -Force -Path $InstallRoot|Out-Null
$openworkerTarget=Join-Path $InstallRoot 'openworker.exe'
$ctlTarget=Join-Path $InstallRoot 'openworkerctl.exe'
Push-Location $goRoot
try{
 & go mod tidy
 if($LASTEXITCODE-ne 0){throw "go mod tidy failed: $LASTEXITCODE"}
 & go test ./... -count=1
 if($LASTEXITCODE-ne 0){throw "openworker full Go test suite failed: $LASTEXITCODE"}
 & go build -trimpath -o $openworkerTarget ./cmd/openworker
 if($LASTEXITCODE-ne 0){throw "openworker build failed: $LASTEXITCODE"}
 & go build -trimpath -o $ctlTarget ./cmd/openworkerctl
 if($LASTEXITCODE-ne 0){throw "openworkerctl compatibility build failed: $LASTEXITCODE"}
}finally{Pop-Location}
$openworkerShim=Join-Path $InstallRoot 'openworker.cmd'
$ctlShim=Join-Path $InstallRoot 'openworkerctl.cmd'
[IO.File]::WriteAllText($openworkerShim,"@echo off`r`n`"$openworkerTarget`" %*`r`n",[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($ctlShim,"@echo off`r`n`"$ctlTarget`" %*`r`n",[Text.UTF8Encoding]::new($false))
$result=[ordered]@{
 schema='openworker-control-install/v2'
 status='installed'
 machine=$env:COMPUTERNAME
 canonical_exe=$openworkerTarget
 compatibility_exe=$ctlTarget
 canonical_shim=$openworkerShim
 compatibility_shim=$ctlShim
 server='http://127.0.0.1:8848'
 single_go_control_authority=$true
 python_required_for_case_bootstrap=$false
 github_action_used_for_business_execution=$false
 installed_at=[DateTime]::UtcNow.ToString('o')
}
$result|ConvertTo-Json -Depth 5
