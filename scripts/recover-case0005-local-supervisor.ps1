param(
    [string]$GoToolRoot = 'C:\github-runners\go-tool-runtime\_work\go-tool-runtime\go-tool-runtime'
)
$ErrorActionPreference='Stop'
$expectedHost='DESKTOP-ODAQN0D'
$expectedRemote='https://github.com/liuxb99/go-tool-runtime'
if($env:COMPUTERNAME -ine $expectedHost){ throw "wrong host $env:COMPUTERNAME expected=$expectedHost" }
if(-not(Test-Path -LiteralPath (Join-Path $GoToolRoot '.git') -PathType Container)){ throw "go-tool checkout missing: $GoToolRoot" }

function Write-Utf8NoBom([string]$Path,[string]$Text){
    $dir=Split-Path -Parent $Path
    if($dir){ New-Item -ItemType Directory -Force -Path $dir|Out-Null }
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}

$backup=$null
Push-Location $GoToolRoot
try {
    $remote=((& git remote get-url origin 2>&1 | Out-String).Trim()).TrimEnd('/')
    if($LASTEXITCODE -ne 0){ throw 'go-tool origin lookup failed' }
    if($remote -ine $expectedRemote -and $remote -ine ($expectedRemote + '.git')){
        throw "refuse recovery for unexpected go-tool origin: $remote"
    }

    $dirtyLines=@(& git status --porcelain=v1 -uall)
    if($LASTEXITCODE -ne 0){ throw 'go-tool git status failed' }
    if($dirtyLines.Count -gt 0){
        $stamp=[DateTimeOffset]::Now.ToString('yyyyMMdd-HHmmss-fff')
        $backup=Join-Path $env:ProgramData ("OpenWorker\recovery-backups\go-tool-runtime-$stamp")
        New-Item -ItemType Directory -Force -Path $backup|Out-Null

        $head=((& git rev-parse HEAD 2>&1 | Out-String).Trim())
        $branch=((& git branch --show-current 2>&1 | Out-String).Trim())
        $statusText=($dirtyLines -join [Environment]::NewLine)+[Environment]::NewLine
        Write-Utf8NoBom (Join-Path $backup 'status.txt') $statusText

        $worktreePatch=(& git diff --binary 2>&1 | Out-String)
        if($LASTEXITCODE -ne 0){ throw 'failed to preserve worktree diff' }
        Write-Utf8NoBom (Join-Path $backup 'worktree.patch') $worktreePatch

        $indexPatch=(& git diff --cached --binary 2>&1 | Out-String)
        if($LASTEXITCODE -ne 0){ throw 'failed to preserve staged diff' }
        Write-Utf8NoBom (Join-Path $backup 'index.patch') $indexPatch

        $untracked=@(& git ls-files --others --exclude-standard)
        if($LASTEXITCODE -ne 0){ throw 'failed to enumerate untracked files' }
        foreach($rel in $untracked){
            if([string]::IsNullOrWhiteSpace($rel)){ continue }
            $src=Join-Path $GoToolRoot $rel
            if(Test-Path -LiteralPath $src -PathType Leaf){
                $dst=Join-Path (Join-Path $backup 'untracked') $rel
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst)|Out-Null
                Copy-Item -LiteralPath $src -Destination $dst -Force
            }
        }
        $manifest=[ordered]@{
            schema='openworker.recovery-backup.v1'
            machine=$env:COMPUTERNAME
            repository='liuxb99/go-tool-runtime'
            checkout=$GoToolRoot
            origin=$remote
            head=$head
            branch=$branch
            dirty_count=$dirtyLines.Count
            untracked_count=$untracked.Count
            created_at=[DateTimeOffset]::Now.ToString('o')
            purpose='preserve-before-authoritative-runner-reset'
        }
        Write-Utf8NoBom (Join-Path $backup 'manifest.json') (($manifest|ConvertTo-Json -Depth 10)+[Environment]::NewLine)
        Write-Host "GTR_DIRTY_BACKUP_CREATED path=$backup dirty=$($dirtyLines.Count) untracked=$($untracked.Count)"

        & git reset --hard HEAD
        if($LASTEXITCODE -ne 0){ throw 'go-tool reset dirty checkout failed' }
        & git clean -fd
        if($LASTEXITCODE -ne 0){ throw 'go-tool clean dirty checkout failed' }
    }

    & git fetch origin main
    if($LASTEXITCODE -ne 0){ throw 'go-tool fetch main failed' }
    & git checkout -B main origin/main
    if($LASTEXITCODE -ne 0){ throw 'go-tool checkout authoritative main failed' }
    & git reset --hard origin/main
    if($LASTEXITCODE -ne 0){ throw 'go-tool reset to origin/main failed' }
    $postDirty=@(& git status --porcelain=v1 -uall)
    if($LASTEXITCODE -ne 0){ throw 'go-tool post-reset status failed' }
    if($postDirty.Count -ne 0){ throw ('go-tool checkout still dirty after reset: '+($postDirty -join '; ')) }
} finally { Pop-Location }

$activation=Join-Path $PSScriptRoot 'activate-case0005-local-supervisor.ps1'
& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $activation -SkipCodeSync
if($LASTEXITCODE -ne 0){ throw "Case0005 local supervisor activation failed exit=$LASTEXITCODE" }

$result=[ordered]@{
    schema='openworker.case0005-supervisor-recovery.v2'
    status='completed'
    machine=$env:COMPUTERNAME
    go_tool_root=$GoToolRoot
    dirty_backup=$backup
    completed_at=[DateTimeOffset]::Now.ToString('o')
}
$result|ConvertTo-Json -Depth 10
