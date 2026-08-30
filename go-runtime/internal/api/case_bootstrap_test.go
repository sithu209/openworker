package api

import (
    "encoding/json"
    "net/http"
    "os"
    "path/filepath"
    "testing"

    "github.com/liuxb99/openworker/go-runtime/internal/store"
)

func writeNativeCaseFixture(t *testing.T, root, workspace string) {
    t.Helper()
    if err:=os.MkdirAll(filepath.Join(root,"case-worklists"),0o755);err!=nil{t.Fatal(err)}
    if err:=os.MkdirAll(filepath.Join(root,"case-specs"),0o755);err!=nil{t.Fatal(err)}
    worklist:=map[string]any{"schema_version":"openworker-case-worklist/v1","case_id":"0005","workspace_root":workspace,"assigned_host":"DESKTOP-ODAQN0D","revision":13,"steps":[]any{map[string]any{"step_id":"0005-010","dependencies":[]string{},"status":"PENDING","evidence":map[string]any{}}}}
    b,_:=json.Marshal(worklist)
    if err:=os.WriteFile(filepath.Join(root,"case-worklists","0005.json"),b,0o644);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(filepath.Join(root,"case-specs","0005.json"),[]byte(`{"case_id":"0005"}`),0o644);err!=nil{t.Fatal(err)}
}

func TestCaseBootstrapCreatesWorkspaceAndGoLedger(t *testing.T) {
    base:=t.TempDir();root:=filepath.Join(base,"openworker");workspace:=filepath.Join(base,"jobs","0005-SNOW-WHITE");writeNativeCaseFixture(t,root,workspace)
    st,err:=store.Open(filepath.Join(base,"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close()
    s:=New(st,nil,"DESKTOP-ODAQN0D","http://oda:8787")
    w:=req(t,s.Handler(),http.MethodPost,"/v1/cases/bootstrap",map[string]any{"case_id":"0005","machine":"DESKTOP-ODAQN0D","workspace_root":workspace,"openworker_root":root,"manifest_path":"case-worklists/0005.json","spec_path":"case-specs/0005.json"})
    if w.Code!=http.StatusAccepted{t.Fatalf("bootstrap status=%d body=%s",w.Code,w.Body.String())}
    if _,err:=os.Stat(filepath.Join(workspace,".openworker","case-supervisor-ledger.jsonl"));err!=nil{t.Fatal(err)}
    var got struct{Controller string `json:"controller"`;PythonRequired bool `json:"python_required"`;Stage string `json:"stage"`;Result struct{Revision int `json:"revision"`;Ready []string `json:"ready_step_ids"`} `json:"result"`}
    if err:=json.Unmarshal(w.Body.Bytes(),&got);err!=nil{t.Fatal(err)}
    if got.Controller!="go-native"||got.PythonRequired||got.Stage!="go_native_bootstrap_completed"||got.Result.Revision!=13||len(got.Result.Ready)!=1||got.Result.Ready[0]!="0005-010"{t.Fatalf("unexpected Go bootstrap result: %+v body=%s",got,w.Body.String())}
    jobs,err:=st.List(100);if err!=nil{t.Fatal(err)};if len(jobs)!=0{t.Fatalf("native Go bootstrap must not create Python controller job: %#v",jobs)}
}

func TestCaseBootstrapRejectsWrongMachineBeforeWorkspaceCreation(t *testing.T) {
    base:=t.TempDir();root:=filepath.Join(base,"openworker");workspace:=filepath.Join(base,"jobs","wrong");writeNativeCaseFixture(t,root,filepath.Join(base,"jobs","0005-SNOW-WHITE"))
    st,err:=store.Open(filepath.Join(base,"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();s:=New(st,nil,"DESKTOP-ODAQN0D","http://oda:8787")
    w:=req(t,s.Handler(),http.MethodPost,"/v1/cases/bootstrap",map[string]any{"case_id":"0005","machine":"DESKTOP-OTHER","workspace_root":workspace,"openworker_root":root,"manifest_path":"case-worklists/0005.json","spec_path":"case-specs/0005.json"})
    if w.Code!=http.StatusServiceUnavailable{t.Fatalf("wrong-machine status=%d body=%s",w.Code,w.Body.String())}
    if _,err:=os.Stat(workspace);!os.IsNotExist(err){t.Fatalf("wrong-machine request must not create workspace: %v",err)}
}
