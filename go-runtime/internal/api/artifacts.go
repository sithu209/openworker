package api

import (
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "io"
    "io/fs"
    "net/http"
    "net/url"
    "os"
    "path/filepath"
    "sort"
    "strings"
    "time"

    "github.com/liuxb99/openworker/go-runtime/internal/model"
)

type jobArtifact struct {
    Path            string    `json:"path"`
    RelativePath    string    `json:"relative_path,omitempty"`
    Folder          string    `json:"folder,omitempty"`
    Kind            string    `json:"kind"`
    Role            string    `json:"role"`
    Priority        int       `json:"priority"`
    Size            int64     `json:"size"`
    SHA256          string    `json:"sha256,omitempty"`
    ModifiedAt      time.Time `json:"modified_at"`
    DuringJobWindow bool      `json:"during_job_window"`
    URL             string    `json:"url,omitempty"`
}

type slotSnapshot struct {
    Slot      int         `json:"slot"`
    Current   *model.Job  `json:"current,omitempty"`
    History   []model.Job `json:"history"`
    Total     int         `json:"total"`
    Succeeded int         `json:"succeeded"`
    Failed    int         `json:"failed"`
}

func (s *Server) slots(w http.ResponseWriter, r *http.Request) {
    jobs, err := s.store.List(queryInt(r, "limit", 500))
    if err != nil { writeErr(w, 500, err); return }
    bySlot := map[int][]model.Job{}
    maxSlot := 0
    for _, j := range jobs {
        if j.AgentSlot <= 0 { continue }
        bySlot[j.AgentSlot] = append(bySlot[j.AgentSlot], j)
        if j.AgentSlot > maxSlot { maxSlot = j.AgentSlot }
    }
    if maxSlot < 4 { maxSlot = 4 }
    out := make([]slotSnapshot, 0, maxSlot)
    for slot := 1; slot <= maxSlot; slot++ {
        hist := bySlot[slot]
        sort.SliceStable(hist, func(i, k int) bool { return hist[i].CreatedAt.After(hist[k].CreatedAt) })
        snap := slotSnapshot{Slot: slot, History: hist, Total: len(hist)}
        for i := range hist {
            switch hist[i].Status {
            case model.StatusRunning, model.StatusStarting:
                if snap.Current == nil { x := hist[i]; snap.Current = &x }
            case model.StatusSucceeded:
                snap.Succeeded++
            case model.StatusFailed, model.StatusTimedOut, model.StatusCancelled:
                snap.Failed++
            }
        }
        out = append(out, snap)
    }
    writeJSON(w, 200, map[string]any{"slots": out, "count": len(out)})
}

var artifactExtKind = map[string]string{
    ".pdf":"document", ".doc":"document", ".docx":"document", ".ppt":"presentation", ".pptx":"presentation",
    ".xls":"spreadsheet", ".xlsx":"spreadsheet", ".xlsm":"spreadsheet", ".csv":"data", ".tsv":"data",
    ".dwg":"cad", ".dxf":"cad", ".dgn":"cad", ".ifc":"bim", ".rvt":"bim", ".mct":"engineering", ".s2k":"engineering",
    ".op2":"engineering", ".f06":"engineering", ".out":"engineering", ".res":"engineering",
    ".obj":"3d", ".fbx":"3d", ".gltf":"3d", ".glb":"3d", ".stl":"3d", ".blend":"3d", ".3dm":"3d",
    ".png":"image", ".jpg":"image", ".jpeg":"image", ".webp":"image", ".gif":"image", ".bmp":"image", ".tif":"image", ".tiff":"image", ".svg":"image",
    ".mp4":"video", ".mov":"video", ".mkv":"video", ".avi":"video", ".webm":"video",
    ".wav":"audio", ".mp3":"audio", ".flac":"audio", ".m4a":"audio", ".aac":"audio",
    ".json":"data", ".jsonl":"data", ".geojson":"data", ".xml":"data", ".yaml":"data", ".yml":"data",
    ".zip":"archive", ".7z":"archive", ".rar":"archive", ".tar":"archive", ".gz":"archive",
    ".exe":"binary", ".msi":"binary", ".dll":"binary",
    ".html":"report", ".htm":"report", ".md":"report", ".txt":"report", ".log":"log",
}

var artifactNameHints = []string{
    "artifact", "deliverable", "result", "report", "receipt", "manifest", "evidence", "render", "export",
    "output", "final", "presentation", "storyboard", "drawing", "model", "analysis", "calculation", "summary",
}

var ignoredArtifactDirs = map[string]bool{
    ".git":true, ".github":true, ".idea":true, ".vscode":true, "node_modules":true,
    ".venv":true, "venv":true, "env":true, "__pycache__":true, ".pytest_cache":true,
    ".mypy_cache":true, ".ruff_cache":true, ".cache":true, "target":true, "vendor":true,
    "packages":true, ".next":true, ".nuxt":true, "dist-cache":true, "models":true,
}

func classifyArtifact(rel string) (string, bool) {
    clean := strings.ToLower(filepath.ToSlash(rel))
    base := strings.ToLower(filepath.Base(clean))
    ext := strings.ToLower(filepath.Ext(base))
    kind, extOK := artifactExtKind[ext]
    hinted := false
    for _, h := range artifactNameHints { if strings.Contains(clean, h) { hinted = true; break } }
    switch ext {
    case ".go", ".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".java", ".cs", ".ps1", ".bat", ".sh", ".toml", ".ini":
        return "", false
    case ".json", ".jsonl", ".xml", ".yaml", ".yml", ".md", ".txt", ".log", ".html", ".htm":
        if !hinted { return "", false }
    }
    if extOK { return kind, true }
    if hinted { return "artifact", true }
    return "", false
}

func artifactRole(rel, kind string) (string, int) {
    low := strings.ToLower(filepath.ToSlash(rel))
    base := strings.ToLower(filepath.Base(low))
    if kind == "stdout" || kind == "stderr" || kind == "log" || strings.HasSuffix(base, ".log") {
        return "log", 400
    }
    if strings.Contains(low, "receipt") || strings.Contains(low, "manifest") || strings.Contains(low, "evidence") || strings.Contains(low, "review") || strings.Contains(low, "ledger") {
        return "evidence", 300
    }
    switch kind {
    case "presentation", "document", "spreadsheet", "cad", "bim", "engineering", "3d", "video", "audio", "archive", "binary":
        return "deliverable", 100
    case "image", "report":
        if strings.Contains(low, "render") || strings.Contains(low, "final") || strings.Contains(low, "deliverable") || strings.Contains(low, "report") || strings.Contains(low, "presentation") {
            return "deliverable", 100
        }
        return "supporting", 200
    case "data":
        if strings.Contains(low, "result") || strings.Contains(low, "output") || strings.Contains(low, "export") || strings.Contains(low, "final") {
            return "supporting", 200
        }
        return "evidence", 300
    default:
        return "supporting", 200
    }
}

func shouldSkipArtifactDir(name string) bool { return ignoredArtifactDirs[strings.ToLower(name)] }
func artifactRoot(job model.Job) string {
    if v:=strings.TrimSpace(job.WorkspaceRoot); v!="" { return v }
    return strings.TrimSpace(job.CWD)
}

func (s *Server) artifacts(w http.ResponseWriter, r *http.Request) {
    job, err := s.store.Get(r.PathValue("jobID"))
    if err != nil { writeErr(w, 404, err); return }
    rows := make([]jobArtifact, 0, 64)
    seen := map[string]bool{}
    start := job.CreatedAt.Add(-2*time.Minute)
    end := artifactWindowEnd(job)

    addFile := func(path, kind, rel string) {
        abs, e := filepath.Abs(path); if e != nil { return }
        key := strings.ToLower(filepath.Clean(abs)); if seen[key] { return }
        st, e := os.Stat(abs); if e != nil || !st.Mode().IsRegular() { return }
        during := !st.ModTime().Before(start) && !st.ModTime().After(end)
        q := url.Values{}; q.Set("path", abs)
        role, priority := artifactRole(rel, kind)
        folder := filepath.ToSlash(filepath.Dir(rel)); if folder == "." { folder = "" }
        row := jobArtifact{Path:abs, RelativePath:rel, Folder:folder, Kind:kind, Role:role, Priority:priority, Size:st.Size(), ModifiedAt:st.ModTime().UTC(), DuringJobWindow:during, URL:"/v1/jobs/"+url.PathEscape(job.JobID)+"/artifact?"+q.Encode()}
        if st.Size() <= 512<<20 {
            if f, e := os.Open(abs); e == nil { h:=sha256.New(); if _,e=io.Copy(h,f); e==nil { row.SHA256=hex.EncodeToString(h.Sum(nil)) }; _=f.Close() }
        }
        rows = append(rows, row); seen[key]=true
    }

    if job.StdoutPath != "" { addFile(job.StdoutPath, "stdout", filepath.Base(job.StdoutPath)) }
    if job.StderrPath != "" { addFile(job.StderrPath, "stderr", filepath.Base(job.StderrPath)) }

    root := artifactRoot(job)
    limit := queryInt(r,"limit",300); if limit < 1 { limit=1 }; if limit > 1000 { limit=1000 }
    scanned := 0
    if root != "" {
        _ = filepath.WalkDir(root, func(path string, d fs.DirEntry, walkErr error) error {
            if walkErr != nil { return nil }
            if len(rows) >= limit { return fs.SkipAll }
            if d.IsDir() {
                if path != root && shouldSkipArtifactDir(d.Name()) { return fs.SkipDir }
                return nil
            }
            scanned++
            if scanned > 50000 { return fs.SkipAll }
            rel,e:=filepath.Rel(root,path); if e!=nil { rel=filepath.Base(path) }
            kind,ok:=classifyArtifact(rel); if !ok { return nil }
            st,e:=d.Info(); if e!=nil { return nil }
            if st.ModTime().Before(start) || st.ModTime().After(end) {
                hinted:=false; low:=strings.ToLower(filepath.ToSlash(rel))
                for _,h:=range artifactNameHints { if strings.Contains(low,h) { hinted=true; break } }
                if !hinted { return nil }
            }
            addFile(path,kind,rel)
            return nil
        })
    }
    sort.SliceStable(rows, func(i,j int) bool {
        if rows[i].Priority != rows[j].Priority { return rows[i].Priority < rows[j].Priority }
        if rows[i].DuringJobWindow != rows[j].DuringJobWindow { return rows[i].DuringJobWindow }
        if rows[i].Folder != rows[j].Folder { return rows[i].Folder < rows[j].Folder }
        return rows[i].ModifiedAt.After(rows[j].ModifiedAt)
    })
    counts := map[string]int{"deliverable":0,"supporting":0,"evidence":0,"log":0}
    for _, row := range rows { counts[row.Role]++ }
    writeJSON(w,200,map[string]any{
        "job_id":job.JobID,"slot":job.AgentSlot,"workspace_root":job.WorkspaceRoot,"artifact_root":root,
        "artifacts":rows,"count":len(rows),"role_counts":counts,"hash_limit_bytes":512<<20,"scan_limit":limit,
        "files_scanned":scanned,"window_start":start,"window_end":end,
        "discovery":"project_agnostic_workspace_index_v3",
    })
}

func (s *Server) serveArtifact(w http.ResponseWriter, r *http.Request) {
    job, err := s.store.Get(r.PathValue("jobID"))
    if err != nil { writeErr(w, 404, err); return }
    requested := strings.TrimSpace(r.URL.Query().Get("path"))
    if requested == "" { writeErr(w,400,errors.New("path required")); return }
    full, err := filepath.Abs(requested)
    if err != nil { writeErr(w,400,err); return }
    allowed := false
    if job.StdoutPath != "" { if p,_:=filepath.Abs(job.StdoutPath); samePath(p,full) { allowed=true } }
    if job.StderrPath != "" { if p,_:=filepath.Abs(job.StderrPath); samePath(p,full) { allowed=true } }
    if !allowed {
        rootName:=artifactRoot(job)
        if rootName!="" { if root,e:=filepath.Abs(rootName); e==nil && pathWithin(root,full) { allowed=true } }
    }
    if !allowed { writeErr(w,403,errors.New("artifact path outside job workspace")); return }
    st, err := os.Stat(full)
    if err != nil || !st.Mode().IsRegular() { writeErr(w,404,errors.New("artifact file not found")); return }
    w.Header().Set("Content-Disposition", "inline; filename*=UTF-8''"+url.PathEscape(filepath.Base(full)))
    http.ServeFile(w,r,full)
}

func samePath(a,b string) bool { return strings.EqualFold(filepath.Clean(a), filepath.Clean(b)) }
func pathWithin(root, p string) bool {
    rel, err := filepath.Rel(filepath.Clean(root), filepath.Clean(p))
    if err != nil { return false }
    return rel == "." || (rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)))
}
func artifactWindowEnd(job model.Job) time.Time { if job.FinishedAt != nil { return job.FinishedAt.Add(2*time.Minute) }; return time.Now().UTC().Add(2*time.Minute) }
