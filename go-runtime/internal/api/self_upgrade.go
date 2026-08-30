package api

import (
    "encoding/json"
    "errors"
    "fmt"
    "net"
    "net/http"
    "os"
    "os/exec"
    "path/filepath"
    "strings"
    "sync"
    "time"

    "github.com/liuxb99/openworker/go-runtime/internal/buildinfo"
)

type githubCommitHead struct { SHA string `json:"sha"` }
var selfUpgradeRoutes sync.Map

func ensureSelfUpgradeRoutes(s *Server) {
    if _, loaded := selfUpgradeRoutes.LoadOrStore(s, struct{}{}); !loaded {
        s.mux.HandleFunc("GET /v1/node/upgrade", s.nodeUpgradeStatus)
        s.mux.HandleFunc("POST /v1/node/upgrade", s.nodeUpgrade)
    }
}

func loopbackOnly(r *http.Request) bool {
    host, _, err := net.SplitHostPort(r.RemoteAddr)
    if err != nil { host = r.RemoteAddr }
    ip := net.ParseIP(strings.Trim(host, "[]"))
    return ip != nil && ip.IsLoopback()
}

func latestOpenWorkerCommit() (string, error) {
    c := &http.Client{Timeout: 10 * time.Second}
    req, _ := http.NewRequest(http.MethodGet, "https://api.github.com/repos/liuxb99/openworker/commits/main", nil)
    req.Header.Set("Accept", "application/vnd.github+json")
    req.Header.Set("User-Agent", "OpenWorker-self-updater")
    res, err := c.Do(req)
    if err != nil { return "", err }
    defer res.Body.Close()
    if res.StatusCode != http.StatusOK { return "", fmt.Errorf("github main lookup HTTP %d", res.StatusCode) }
    var h githubCommitHead
    if err := json.NewDecoder(res.Body).Decode(&h); err != nil { return "", err }
    h.SHA = strings.TrimSpace(h.SHA)
    if len(h.SHA) != 40 { return "", errors.New("invalid github main commit") }
    return h.SHA, nil
}

func upgradeStatePath() string { return filepath.Join(os.Getenv("ProgramData"), "OpenWorker", "upgrade", "last.json") }

func (s *Server) nodeUpgradeStatus(w http.ResponseWriter, r *http.Request) {
    p := upgradeStatePath()
    b, err := os.ReadFile(p)
    if err != nil {
        if os.IsNotExist(err) { writeJSON(w, 200, map[string]any{"ok":true,"phase":"IDLE"}); return }
        writeErr(w, 500, err); return
    }
    var v map[string]any
    if json.Unmarshal(b, &v) != nil { writeErr(w, 500, errors.New("invalid upgrade state")); return }
    writeJSON(w, 200, v)
}

func (s *Server) nodeUpgrade(w http.ResponseWriter, r *http.Request) {
    if !loopbackOnly(r) { writeErr(w, 403, errors.New("self-upgrade is loopback-only")); return }
    if strings.ToLower(os.Getenv("OS")) != "windows_nt" { writeErr(w, 409, errors.New("self-upgrade currently requires Windows service deployment")); return }
    target, err := latestOpenWorkerCommit()
    if err != nil { writeErr(w, 502, err); return }
    current := strings.TrimSpace(buildinfo.Commit)
    if current != "" && !strings.EqualFold(current, "unknown") && strings.EqualFold(current, target) {
        writeJSON(w, 200, map[string]any{"ok":true,"phase":"CURRENT","current_commit":current,"target_commit":target}); return
    }
    root := filepath.Join(os.Getenv("ProgramData"), "OpenWorker", "upgrade")
    if err := os.MkdirAll(root, 0755); err != nil { writeErr(w, 500, err); return }
    script := filepath.Join(root, "self-upgrade.ps1")
    if err := os.WriteFile(script, []byte(selfUpgradePowerShell), 0644); err != nil { writeErr(w, 500, err); return }
    cmd := exec.Command("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script, "-TargetCommit", target)
    if err := cmd.Start(); err != nil { writeErr(w, 500, err); return }
    pid := cmd.Process.Pid
    _ = cmd.Process.Release()
    writeJSON(w, http.StatusAccepted, map[string]any{"ok":true,"phase":"STARTED","current_commit":current,"target_commit":target,"pid":pid,"state":"/v1/node/upgrade"})
}

const selfUpgradePowerShell = `param([Parameter(Mandatory=$true)][string]$TargetCommit)
$ErrorActionPreference='Stop'
$root=Join-Path $env:ProgramData 'OpenWorker\upgrade'
$state=Join-Path $root 'last.json'
function Save-State([string]$phase,[string]$message=''){
  $o=[ordered]@{ok=($phase -ne 'FAILED');phase=$phase;message=$message;target_commit=$TargetCommit;machine=$env:COMPUTERNAME;updated_at=[DateTimeOffset]::UtcNow.ToString('o')}
  [IO.File]::WriteAllText($state,($o|ConvertTo-Json -Compress)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
}
try{
  New-Item -ItemType Directory -Force -Path $root|Out-Null
  Save-State 'DOWNLOADING'
  $work=Join-Path $root $TargetCommit
  if(Test-Path $work){Remove-Item -Recurse -Force $work}
  New-Item -ItemType Directory -Force -Path $work|Out-Null
  $zip=Join-Path $work 'source.zip'
  Invoke-WebRequest -UseBasicParsing -Uri ('https://github.com/liuxb99/openworker/archive/'+$TargetCommit+'.zip') -OutFile $zip
  Expand-Archive -LiteralPath $zip -DestinationPath $work -Force
  $src=(Get-ChildItem -LiteralPath $work -Directory|Where-Object{$_.Name -like 'openworker-*'}|Select-Object -First 1).FullName
  if(-not $src){throw 'source archive root missing'}
  Save-State 'LOCATING_GO'
  $go=(Get-Command go.exe -ErrorAction SilentlyContinue).Source
  if(-not $go){foreach($p in @('C:\Program Files\Go\bin\go.exe','C:\Go\bin\go.exe')){if(Test-Path $p){$go=$p;break}}}
  if(-not $go){
    $runnerSvcs=Get-CimInstance Win32_Service|Where-Object{$_.Name -like 'actions.runner*'}
    foreach($rs in $runnerSvcs){
      $m=[regex]::Match([string]$rs.PathName,'^\"?([^\"]+Runner\.Service\.exe)')
      if(-not $m.Success){continue}
      $rr=Split-Path (Split-Path $m.Groups[1].Value -Parent) -Parent
      $tool=Join-Path $rr '_work\_tool\go'
      if(Test-Path $tool){$cand=Get-ChildItem $tool -Filter go.exe -File -Recurse -ErrorAction SilentlyContinue|Sort-Object FullName -Descending|Select-Object -First 1;if($cand){$go=$cand.FullName;break}}
    }
  }
  if(-not $go){throw 'go.exe not found; install Go 1.23+ or expose runner toolcache'}
  Save-State 'TESTING'
  Push-Location (Join-Path $src 'go-runtime')
  & $go test ./... -count=1
  if($LASTEXITCODE-ne 0){throw "go test failed rc=$LASTEXITCODE"}
  Save-State 'BUILDING'
  $out=Join-Path $work 'openworker-node.exe'
  $build=[DateTime]::UtcNow.ToString('o')
  & $go build -ldflags "-X github.com/liuxb99/openworker/go-runtime/internal/buildinfo.Version=p2-node -X github.com/liuxb99/openworker/go-runtime/internal/buildinfo.Commit=$TargetCommit -X github.com/liuxb99/openworker/go-runtime/internal/buildinfo.TargetCommit=$TargetCommit -X github.com/liuxb99/openworker/go-runtime/internal/buildinfo.BuildTime=$build" -o $out ./cmd/openworker-node
  if($LASTEXITCODE-ne 0){throw "go build failed rc=$LASTEXITCODE"}
  Pop-Location
  Save-State 'INSTALLING'
  $svc=Get-CimInstance Win32_Service -Filter "Name='OpenWorkerNode'"
  if(-not $svc){throw 'OpenWorkerNode service missing'}
  $bin=[string]$svc.PathName
  function Arg([string]$name,[string]$default=''){ $m=[regex]::Match($bin,'(?:^|\s)-'+[regex]::Escape($name)+'\s+(?:\"([^\"]*)\"|(\S+))'); if($m.Success){if($m.Groups[1].Success){return $m.Groups[1].Value};return $m.Groups[2].Value}; return $default }
  $listen=Arg 'listen' '127.0.0.1:8787'; $workers=[int](Arg 'workers' '4'); $caps=Arg 'capabilities' ''; $adv=Arg 'advertise' ''; $peers=Arg 'peers' ''
  $installer=Join-Path $src 'scripts\install_openworker_node_service.ps1'
  & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $installer -SourceExe $out -Workers $workers -Capabilities $caps -Listen $listen -Advertise $adv -Peers $peers
  if($LASTEXITCODE-ne 0){throw "installer failed rc=$LASTEXITCODE"}
  Save-State 'WAITING_VERIFIED'
}catch{
  Save-State 'FAILED' $_.Exception.Message
  exit 1
}
`
