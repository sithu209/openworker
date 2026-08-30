package api

import(
 "bytes"
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "path/filepath"
 "testing"
 "github.com/liuxb99/openworker/go-runtime/internal/model"
 "github.com/liuxb99/openworker/go-runtime/internal/store"
)
func req(t *testing.T,h http.Handler,method,path string,body any)*httptest.ResponseRecorder{t.Helper();var b bytes.Buffer;if body!=nil{if err:=json.NewEncoder(&b).Encode(body);err!=nil{t.Fatal(err)}};r:=httptest.NewRequest(method,path,&b);if body!=nil{r.Header.Set("Content-Type","application/json")};w:=httptest.NewRecorder();h.ServeHTTP(w,r);return w}
func TestSupervisorAPIRecoverUsesDurableJobs(t *testing.T){st,err:=store.Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();_,err=st.Submit(model.SubmitRequest{JobID:"J1",DispatchID:"D1",Machine:"HOST1",Command:"echo ok",CWD:"C:/work"},"HOST1");if err!=nil{t.Fatal(err)};s:=New(st,nil,"HOST1","http://host1:8787");h:=s.Handler();w:=req(t,h,http.MethodPost,"/v1/supervisor/session",map[string]any{"supervisor_id":"HOST1-CODER-01","session_id":"S1","model":"coder","current_goal":"watch jobs"});if w.Code!=201{t.Fatalf("session status=%d body=%s",w.Code,w.Body.String())};w=req(t,h,http.MethodPost,"/v1/supervisor/heartbeat",map[string]any{"supervisor_id":"HOST1-CODER-01","session_id":"S1"});if w.Code!=200{t.Fatalf("heartbeat=%d body=%s",w.Code,w.Body.String())};w=req(t,h,http.MethodPost,"/v1/supervisor/recover",map[string]any{"supervisor_id":"HOST1-CODER-01","session_id":"S1"});if w.Code!=200{t.Fatalf("recover=%d body=%s",w.Code,w.Body.String())};var got struct{Snapshot store.SupervisorSnapshot `json:"snapshot"`};if err:=json.Unmarshal(w.Body.Bytes(),&got);err!=nil{t.Fatal(err)};if len(got.Snapshot.OwnedJobs)!=1||got.Snapshot.OwnedJobs[0]!="J1"{t.Fatalf("snapshot=%+v",got.Snapshot)};w=req(t,h,http.MethodPost,"/v1/supervisor/decision",map[string]any{"decision_id":"DEC1","supervisor_id":"HOST1-CODER-01","session_id":"S1","decision_type":"inspect","reason_code":"QUEUED_JOB","input_state_hash":"abc"});if w.Code!=201{t.Fatalf("decision=%d body=%s",w.Code,w.Body.String())}}
func TestSupervisorDecisionRejectsOldSession(t *testing.T){st,err:=store.Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();s:=New(st,nil,"HOST1","http://host1:8787");h:=s.Handler();_=req(t,h,http.MethodPost,"/v1/supervisor/session",map[string]any{"supervisor_id":"SUP","session_id":"S1"});_=req(t,h,http.MethodPost,"/v1/supervisor/session",map[string]any{"supervisor_id":"SUP","session_id":"S2"});w:=req(t,h,http.MethodPost,"/v1/supervisor/decision",map[string]any{"decision_id":"D1","supervisor_id":"SUP","session_id":"S1","decision_type":"wait","reason_code":"NOOP"});if w.Code!=409{t.Fatalf("old session decision must fail, got %d %s",w.Code,w.Body.String())}}
