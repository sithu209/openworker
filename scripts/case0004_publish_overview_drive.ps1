param(
    [string]$WorkspaceRoot = 'D:\AI-Work\jobs\0004-DWG-TO-3D',
    [string]$OverviewRelativePath = 'dwg\exports\default\visual-search\case0004-overview.png',
    [string]$ExpectedSha256 = '5cee03340cbbcad51e412b46b85bda9dcaac22b193586b953bbfd5134039103e',
    [string]$DriveFolderId = $env:OPENWORKER_GOOGLE_DRIVE_REVIEW_FOLDER_ID,
    [string]$Machine = 'DESKTOP-O87PJNR',
    [string]$ReceiptRelativePath = 'receipts\case0004-overview-drive-handoff.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string]$Message) {
    throw "CASE0004_OVERVIEW_DRIVE_HANDOFF_FAILED: $Message"
}

if ($env:COMPUTERNAME -and $env:COMPUTERNAME -ine $Machine) {
    Fail "fixed machine mismatch expected=$Machine actual=$env:COMPUTERNAME"
}

$overview = Join-Path $WorkspaceRoot $OverviewRelativePath
if (-not (Test-Path -LiteralPath $overview -PathType Leaf)) {
    Fail "overview missing: $overview"
}
$file = Get-Item -LiteralPath $overview
if ($file.Length -le 0) {
    Fail 'overview is empty'
}
$sha = (Get-FileHash -LiteralPath $overview -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedSha256 -and $sha -ne $ExpectedSha256.ToLowerInvariant()) {
    Fail "overview SHA mismatch expected=$ExpectedSha256 actual=$sha"
}

$receiptPath = Join-Path $WorkspaceRoot $ReceiptRelativePath
$receiptDir = Split-Path -Parent $receiptPath
New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null

$args = @(
    '-m', 'coworker.google_drive_cli',
    'upload', $overview,
    '--name', 'case0004-overview.png',
    '--description', "Case 0004 REAL overview for ChatGPT multimodal review; machine=$Machine; sha256=$sha",
    '--receipt', $receiptPath
)
if (-not [string]::IsNullOrWhiteSpace($DriveFolderId)) {
    $args += @('--folder-id', $DriveFolderId)
}

& python @args
if ($LASTEXITCODE -ne 0) {
    Fail "openworker-drive upload failed exit=$LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
    Fail "canonical Drive receipt missing: $receiptPath"
}
$receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$receipt.status -ne 'UPLOADED') {
    Fail "unexpected Drive receipt status: $($receipt.status)"
}
if ([string]$receipt.source_sha256 -ne $sha) {
    Fail "Drive receipt source SHA mismatch expected=$sha actual=$($receipt.source_sha256)"
}
if ([string]::IsNullOrWhiteSpace([string]$receipt.drive_file_id)) {
    Fail 'Drive receipt missing drive_file_id'
}

$receipt | ConvertTo-Json -Depth 20
