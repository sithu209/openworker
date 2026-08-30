package api

import (
    "encoding/json"
    "errors"
    "fmt"
    "net/http"
    "os"
    "path/filepath"
    "strings"
    "time"

    "github.com/liuxb99/openworker/go-runtime/internal/casecontroller"
    "github.com/liuxb99/openworker/go-runtime/internal/cluster"
)

type caseBootstrapRequest = cluster.CaseBootstrapRequest

type bootstrapDiagnostic struct { OK bool `json:"ok"`; CaseID string `json:"case_id,omitempty"`; Machine string `json:"machine,omitempty"`; Stage string `json:"stage"`; AttemptedAction string `json:"attempted_action"`; Reason string `json:"reason"`; NextAction string `json:"next_action"`; Checks map[string]any `json:"checks,omitempty"`; ObservedAt time.Time `json:"observed_at"` }

func (s *Server) bootstrapFail(w http.ResponseWriter,status int,req caseBootstrapRequest,stage,attempted string,err error,next string,checks map[string]any){machine:=strings.TrimSpace(req.Machine);if machine==""{machine=s.machine};d:=bootstrapDiagnostic{OK:false,CaseID:strings.TrimSpace(req.CaseID),Machine:machine,Stage:stage,AttemptedAction:attempted,Reason:err.Error(),NextAction:next,Checks:checks,ObservedAt:time.Now().UTC()};detail,_:=json.Marshal(d);_=s.store.RecordClusterControl("","case_bootstrap_failed",machine,string(detail));writeJSON(w,status,d)}

func (s *Server) caseBootstrap(w http.ResponseWriter,r *http.Request){
    ensureNativeCaseContinueRoute(s)
    var req caseBootstrapRequest;d:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20));d.DisallowUnknownFields();if err:=d.Decode(&req);err!=nil{s.bootstrapFail(w,400,req,"decode_request","decode case bootstrap request",err,"fix request JSON and retry",nil);return}
    req.CaseID=strings.TrimSpace(req.CaseID);req.Machine=strings.TrimSpace(req.Machine);req.WorkspaceRoot=strings.TrimSpace(req.WorkspaceRoot);req.OpenWorkerRoot=strings.TrimSpace(req.OpenWorkerRoot);req.ManifestPath=strings.TrimSpace(req.ManifestPath);req.SpecPath=strings.TrimSpace(req.SpecPath)
    checks:=map[string]any{"workspace_root":req.WorkspaceRoot,"openworker_root":req.OpenWorkerRoot,"manifest_path":req.ManifestPath,"spec_path":req.SpecPath,"controller":"go-native"}
    if req.CaseID==""||req.WorkspaceRoot==""||req.OpenWorkerRoot==""||req.ManifestPath==""||req.SpecPath==""{s.bootstrapFail(w,400,req,"validate_required_fields","validate native Go bootstrap fields",errors.New("case_id, workspace_root, openworker_root, manifest_path and spec_path are required"),"supply all required fields and retry",checks);return}
    if req.Machine==""{req.Machine=s.machine}
    if !strings.EqualFold(req.Machine,s.machine){if s.cluster==nil{s.bootstrapFail(w,503,req,"route_machine","route native Go bootstrap",errors.New("cluster controller disabled"),"submit directly to requested machine",checks);return};res,err:=s.cluster.CaseBootstrap(req);if err!=nil{s.bootstrapFail(w,409,req,"route_machine","forward native Go bootstrap",err,"inspect cluster connectivity and retry",checks);return};writeJSON(w,202,map[string]any{"case_id":req.CaseID,"requested_machine":req.Machine,"selected":res.Selected,"remote":res.Response,"authority":"openworker-cluster-to-go-case-controller","github_action_used":false});return}
    workspace,err:=filepath.Abs(req.WorkspaceRoot);if err!=nil||!filepath.IsAbs(workspace){if err==nil{err=errors.New("workspace_root must be absolute")};s.bootstrapFail(w,400,req,"resolve_workspace","resolve workspace",err,"use an absolute local workspace",checks);return}
    root,err:=filepath.Abs(req.OpenWorkerRoot);if err!=nil||!filepath.IsAbs(root){if err==nil{err=errors.New("openworker_root must be absolute")};s.bootstrapFail(w,400,req,"resolve_openworker_root","resolve OpenWorker root",err,"use an absolute local checkout",checks);return}
    if st,e:=os.Stat(root);e!=nil||!st.IsDir(){s.bootstrapFail(w,400,req,"validate_openworker_root","verify OpenWorker checkout",fmt.Errorf("openworker_root unavailable: %v",e),"sync/fix checkout and retry",checks);return}
    manifest,err:=requireBootstrapFile(root,req.ManifestPath);if err!=nil{s.bootstrapFail(w,400,req,"validate_manifest","verify worklist",err,"sync/fix worklist and retry",checks);return}
    spec,err:=requireBootstrapFile(root,req.SpecPath);if err!=nil{s.bootstrapFail(w,400,req,"validate_spec","verify case spec",err,"sync/fix case spec and retry",checks);return}
    result,err:=casecontroller.Bootstrap(req.CaseID,s.machine,workspace,manifest,spec);if err!=nil{s.bootstrapFail(w,409,req,"go_native_bootstrap","run native Go case bootstrap",err,"repair native Go controller inputs and retry",checks);return}
    checks["python_required"]=false;checks["durable_submit"]=false;checks["revision"]=result.Revision;checks["ready_step_ids"]=result.ReadyStepIDs;checks["continue_endpoint"]="/v1/cases/continue"
    detail,_:=json.Marshal(result);_=s.store.RecordClusterControl("","go_case_bootstrap",s.machine,string(detail))
    writeJSON(w,202,map[string]any{"ok":true,"case_id":req.CaseID,"machine":s.machine,"workspace_root":workspace,"stage":"go_native_bootstrap_completed","controller":"go-native","python_required":false,"result":result,"checks":checks,"authority":"openworker-go-native-case-controller","github_action_used":false})
}

func requireBootstrapFile(root,raw string)(string,error){p:=strings.TrimSpace(raw);if strings.ContainsAny(p,"\"\r\n"){return "",errors.New("bootstrap file path contains unsupported characters")};if !filepath.IsAbs(p){p=filepath.Join(root,p)};p,err:=filepath.Abs(p);if err!=nil{return "",err};back,err:=filepath.Rel(root,p);if err!=nil||back==".."||strings.HasPrefix(back,".."+string(filepath.Separator)){return "",errors.New("bootstrap manifest/spec must remain under openworker_root")};st,err:=os.Stat(p);if err!=nil||st.IsDir()||st.Size()<=0{return "",fmt.Errorf("bootstrap file missing or empty: %s",p)};return p,nil}
