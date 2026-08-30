param(
 [string]$InstallRoot = "$env:ProgramData\OpenWorker\tunnel-client",
 [string]$SourceRoot = "$env:ProgramData\OpenWorker\src\tunnel-client",
 [string]$Version = 'v0.0.10'
)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v\d+\.\d+\.\d+$'){throw "Version must be a stable semantic tag, got $Version"}
$git=(Get-Command git.exe -ErrorAction SilentlyContinue);if($null-eq$git){$git=Get-Command git -ErrorAction SilentlyContinue};if($null-eq$git){throw 'git not found'}
$go=(Get-Command go.exe -ErrorAction SilentlyContinue);if($null-eq$go){$go=Get-Command go -ErrorAction SilentlyContinue};if($null-eq$go){throw 'go not found'}
# v0.0.10 may require a newer Go toolchain than the bootstrap binary. Let official Go toolchain auto-resolution handle that rather than silently falling back to an opaque binary.
$env:GOTOOLCHAIN='auto'
$bootstrapGo=(& $go.Source version|Out-String).Trim()
New-Item -ItemType Directory -Force -Path (Split-Path $SourceRoot -Parent),$InstallRoot|Out-Null
if(-not(Test-Path -LiteralPath (Join-Path $SourceRoot '.git') -PathType Container)){
 & $git.Source clone --filter=blob:none https://github.com/openai/tunnel-client.git $SourceRoot
 if($LASTEXITCODE-ne0){throw 'clone openai/tunnel-client failed'}
}
Push-Location $SourceRoot
try{
 $dirty=& $git.Source status --porcelain;if($LASTEXITCODE-ne0){throw 'git status failed'};if($dirty){throw "refuse to update dirty tunnel-client checkout: $SourceRoot"}
 & $git.Source fetch --tags --force origin;if($LASTEXITCODE-ne0){throw 'git fetch tags failed'}
 & $git.Source checkout --detach $Version;if($LASTEXITCODE-ne0){throw "git checkout $Version failed"}
 $tagCommit=(& $git.Source rev-list -n 1 $Version).Trim();$head=(& $git.Source rev-parse HEAD).Trim();if($tagCommit-ne$head){throw "tag/head mismatch tag=$tagCommit head=$head"}
 $target=Join-Path $InstallRoot 'tunnel-client.exe'
 & $go.Source build -trimpath -o $target ./cmd/client
 if($LASTEXITCODE-ne0){throw 'tunnel-client build failed'}
 $builtVersion=(& $target --version|Out-String).Trim();if($LASTEXITCODE-ne0-or[string]::IsNullOrWhiteSpace($builtVersion)){throw 'tunnel-client executable validation failed'}
 $receipt=[ordered]@{schema='openworker-secure-mcp-tunnel-client-install/v2';status='installed';source_repository='https://github.com/openai/tunnel-client';source_root=$SourceRoot;version=$Version;commit=$head;exe=$target;bootstrap_go=$bootstrapGo;go_toolchain_policy='GOTOOLCHAIN=auto';built_version=$builtVersion;built_from_source=$true;opaque_binary_fallback=$false;github_actions_used_for_business_execution=$false;installed_at=[DateTime]::UtcNow.ToString('o')}
 $receiptPath=Join-Path $InstallRoot 'install-receipt.json';[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false));$receipt|ConvertTo-Json -Depth 5
}finally{Pop-Location}
