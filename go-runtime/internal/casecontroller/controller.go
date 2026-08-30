package casecontroller

import (
    "bufio"
    "encoding/json"
    "errors"
    "fmt"
    "os"
    "path/filepath"
    "strings"
    "time"
)

const Schema = "openworker.go-case-controller/v1"

type Step struct {
    StepID string `json:"step_id"`
    Title string `json:"title,omitempty"`
    Kind string `json:"kind,omitempty"`
    Dependencies []string `json:"dependencies"`
    AllowedActions []string `json:"allowed_actions,omitempty"`
    Acceptance []string `json:"acceptance,omitempty"`
    FanoutRole string `json:"fanout_role,omitempty"`
    FanoutEvidencePrefix string `json:"fanout_evidence_prefix,omitempty"`
    InputEvidenceKey string `json:"input_evidence_key,omitempty"`
    OutputRelpath string `json:"output_relpath,omitempty"`
    EvidenceProfile string `json:"evidence_profile,omitempty"`
    ArtifactEvidenceKeys []string `json:"artifact_evidence_keys,omitempty"`
    Status string `json:"status"`
    Evidence map[string]any `json:"evidence"`
    Blocker string `json:"blocker,omitempty"`
}
type Worklist struct { SchemaVersion string `json:"schema_version"`; CaseID string `json:"case_id"`; WorkspaceRoot string `json:"workspace_root"`; AssignedHost string `json:"assigned_host"`; Revision int `json:"revision"`; Steps []Step `json:"steps"` }
type BootstrapResult struct { Schema string `json:"schema"`; CaseID string `json:"case_id"`; Machine string `json:"machine"`; WorkspaceRoot string `json:"workspace_root"`; Revision int `json:"revision"`; ReadyStepIDs []string `json:"ready_step_ids"`; LedgerPath string `json:"ledger_path"`; WorklistSnapshot string `json:"worklist_snapshot"`; SpecSnapshot string `json:"spec_snapshot"`; ControllerSnapshot string `json:"controller_snapshot"`; Controller string `json:"controller"`; PythonRequired bool `json:"python_required"`; CompletedAt time.Time `json:"completed_at"` }
type ledgerEvent struct { Schema string `json:"schema"`; Timestamp time.Time `json:"timestamp"`; CaseID string `json:"case_id"`; Machine string `json:"machine"`; EventType string `json:"event_type"`; WorkspaceRoot string `json:"workspace_root"`; Revision int `json:"revision,omitempty"`; ReadyStepIDs []string `json:"ready_step_ids,omitempty"`; StepID string `json:"step_id,omitempty"`; ActionID string `json:"action_id,omitempty"`; WorkID string `json:"work_id,omitempty"`; Detail string `json:"detail,omitempty"` }

func Bootstrap(caseID,machine,workspaceRoot,manifestPath,specPath string)(BootstrapResult,error){
    caseID=strings.TrimSpace(caseID);if !validCaseID(caseID){return BootstrapResult{},fmt.Errorf("invalid case_id %q",caseID)}
    b,err:=os.ReadFile(manifestPath);if err!=nil{return BootstrapResult{},err};var w Worklist;if err:=json.Unmarshal(b,&w);err!=nil{return BootstrapResult{},fmt.Errorf("decode worklist: %w",err)}
    if strings.TrimSpace(w.CaseID)!=caseID{return BootstrapResult{},errors.New("worklist case_id mismatch")};if !strings.EqualFold(w.AssignedHost,machine){return BootstrapResult{},fmt.Errorf("assigned_host mismatch: %s",w.AssignedHost)};if !samePath(w.WorkspaceRoot,workspaceRoot){return BootstrapResult{},fmt.Errorf("workspace_root mismatch worklist=%s request=%s",w.WorkspaceRoot,workspaceRoot)};if w.Revision<=0||len(w.Steps)==0{return BootstrapResult{},errors.New("invalid worklist revision/steps")};if err:=validateGraph(w.Steps);err!=nil{return BootstrapResult{},err}
    sb,err:=os.ReadFile(specPath);if err!=nil{return BootstrapResult{},err};var spec map[string]any;if err:=json.Unmarshal(sb,&spec);err!=nil{return BootstrapResult{},fmt.Errorf("decode case spec: %w",err)};if strings.TrimSpace(fmt.Sprint(spec["case_id"]))!=caseID{return BootstrapResult{},errors.New("case spec case_id mismatch")}
    marker:=filepath.Join(workspaceRoot,".openworker");if err:=os.MkdirAll(marker,0o755);err!=nil{return BootstrapResult{},fmt.Errorf("materialize workspace: %w",err)}
    ledger:=filepath.Join(marker,"case-supervisor-ledger.jsonl");worklistSnapshot:=filepath.Join(marker,"case-worklist.json");specSnapshot:=filepath.Join(marker,"case-spec.json");controllerSnapshot:=filepath.Join(marker,"case-controller-last.json");ready:=readySteps(w.Steps);now:=time.Now().UTC()
    if err:=appendLedger(ledger,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:now,CaseID:caseID,Machine:machine,EventType:"go_controller_bootstrap_start",WorkspaceRoot:workspaceRoot,Revision:w.Revision});err!=nil{return BootstrapResult{},err}
    if err:=atomicWrite(worklistSnapshot,b);err!=nil{return BootstrapResult{},fmt.Errorf("write worklist snapshot: %w",err)};if err:=atomicWrite(specSnapshot,sb);err!=nil{return BootstrapResult{},fmt.Errorf("write spec snapshot: %w",err)}
    result:=BootstrapResult{Schema:Schema,CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,Revision:w.Revision,ReadyStepIDs:ready,LedgerPath:ledger,WorklistSnapshot:worklistSnapshot,SpecSnapshot:specSnapshot,ControllerSnapshot:controllerSnapshot,Controller:"go-native",PythonRequired:false,CompletedAt:time.Now().UTC()}
    rb,_:=json.MarshalIndent(result,"","  ");if err:=atomicWrite(controllerSnapshot,append(rb,'\n'));err!=nil{return BootstrapResult{},fmt.Errorf("write controller snapshot: %w",err)}
    if err:=appendLedger(ledger,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_controller_bootstrap_completed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,ReadyStepIDs:ready,Detail:"native Go bootstrap; manifest/spec driven; Python controller not required"});err!=nil{return BootstrapResult{},err}
    return result,nil
}
func validCaseID(caseID string)bool{caseID=strings.TrimSpace(caseID);if caseID==""||len(caseID)>64{return false};for _,r:=range caseID{if (r>='a'&&r<='z')||(r>='A'&&r<='Z')||(r>='0'&&r<='9')||r=='-'||r=='_'||r=='.'{continue};return false};return caseID!="."&&caseID!=".."}
func supportedCaseID(caseID string)bool{return validCaseID(caseID)}
func validateGraph(steps []Step)error{ids:=map[string]bool{};for _,s:=range steps{if s.StepID==""||ids[s.StepID]{return fmt.Errorf("invalid/duplicate step_id %q",s.StepID)};ids[s.StepID]=true};for _,s:=range steps{for _,d:=range s.Dependencies{if !ids[d]{return fmt.Errorf("step %s depends on unknown %s",s.StepID,d)}}};return nil}
func readySteps(steps []Step)[]string{done:=map[string]bool{};for _,s:=range steps{if strings.EqualFold(s.Status,"SUCCEEDED")||strings.EqualFold(s.Status,"COMPLETED")||strings.EqualFold(s.Status,"PASSED"){done[s.StepID]=true}};out:=[]string{};for _,s:=range steps{if !strings.EqualFold(s.Status,"PENDING")&&!strings.EqualFold(s.Status,"READY"){continue};ok:=true;for _,d:=range s.Dependencies{if !done[d]{ok=false;break}};if ok{out=append(out,s.StepID)}};return out}
func appendLedger(path string,ev ledgerEvent)error{f,err:=os.OpenFile(path,os.O_CREATE|os.O_WRONLY|os.O_APPEND,0o644);if err!=nil{return err};defer f.Close();w:=bufio.NewWriter(f);if err:=json.NewEncoder(w).Encode(ev);err!=nil{return err};if err:=w.Flush();err!=nil{return err};return f.Sync()}
func atomicWrite(path string,data []byte)error{tmp:=path+".tmp";if err:=os.WriteFile(tmp,data,0o644);err!=nil{return err};return os.Rename(tmp,path)}
func samePath(a,b string)bool{aa,_:=filepath.Abs(filepath.Clean(a));bb,_:=filepath.Abs(filepath.Clean(b));return strings.EqualFold(aa,bb)}
