package cluster

import(
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "testing"
 "time"
 "github.com/liuxb99/openworker/go-runtime/internal/model"
)

func TestRemoteSubmitJobStatusAndControls(t *testing.T){
 var submitted model.SubmitRequest;cancelled:=false;retried:=false;drained:=false
 mux:=http.NewServeMux()
 mux.HandleFunc("/v1/node/status",func(w http.ResponseWriter,r *http.Request){json.NewEncoder(w).Encode(map[string]any{"node_id":"n1","machine":"HOST1","advertise_endpoint":"","heartbeat_at":time.Now().UTC(),"lease_until":time.Now().UTC().Add(time.Minute),"max_workers":4,"busy_workers":0,"free_workers":4,"queued_jobs":0,"inventory":map[string]any{"capabilities":[]string{"x"}}})})
 mux.HandleFunc("/v1/jobs",func(w http.ResponseWriter,r *http.Request){if r.Method==http.MethodPost{if err:=json.NewDecoder(r.Body).Decode(&submitted);err!=nil{t.Fatal(err)};w.WriteHeader(202);json.NewEncoder(w).Encode(model.SubmitAck{JobID:submitted.JobID,DispatchID:submitted.DispatchID,Machine:"HOST1",Accepted:true,AcceptedAt:time.Now().UTC()});return};json.NewEncoder(w).Encode(map[string]any{"jobs":[]model.Job{{JobID:"J1",Machine:"HOST1",Status:model.StatusRunning,AgentSlot:2}}})})
 mux.HandleFunc("/v1/jobs/J1",func(w http.ResponseWriter,r *http.Request){json.NewEncoder(w).Encode(model.Job{JobID:"J1",Machine:"HOST1",Status:model.StatusRunning,AgentSlot:2})})
 mux.HandleFunc("/v1/jobs/J1/cancel",func(w http.ResponseWriter,r *http.Request){cancelled=true;json.NewEncoder(w).Encode(map[string]any{"job_id":"J1","status":"cancelled"})})
 mux.HandleFunc("/v1/jobs/J1/retry",func(w http.ResponseWriter,r *http.Request){retried=true;json.NewEncoder(w).Encode(map[string]any{"job_id":"J1","status":"queued_local"})})
 mux.HandleFunc("/v1/queue/drain",func(w http.ResponseWriter,r *http.Request){drained=true;json.NewEncoder(w).Encode(map[string]any{"ok":true,"mode":r.URL.Query().Get("mode")})})
 srv:=httptest.NewServer(mux);defer srv.Close()
 c:=NewController([]string{srv.URL});c.probeAll()
 res,err:=c.Submit(SubmitRequest{Job:model.SubmitRequest{JobID:"J2",DispatchID:"D2",Machine:"any",Command:"echo ok",CWD:"C:/work"},RequiredCapabilities:[]string{"x"}});if err!=nil{t.Fatal(err)}
 if !res.Ack.Accepted||submitted.Machine!="HOST1"{t.Fatalf("bad submit result: %+v submitted=%+v",res,submitted)}
 j,err:=c.JobStatus("J1");if err!=nil||j.Job.AgentSlot!=2{t.Fatalf("job=%+v err=%v",j,err)}
 agents,err:=c.Agents();if err!=nil{t.Fatal(err)};busy:=0;for _,a:=range agents{if a.Busy&&a.Slot==2&&a.JobID=="J1"{busy++}};if busy!=1{t.Fatalf("expected slot 2 busy, agents=%+v",agents)}
 if _,err:=c.JobAction("J1","cancel");err!=nil{t.Fatal(err)};if _,err:=c.JobAction("J1","retry");err!=nil{t.Fatal(err)};if _,err:=c.Drain("HOST1","all");err!=nil{t.Fatal(err)}
 if !cancelled||!retried||!drained{t.Fatalf("forwarding cancel=%v retry=%v drain=%v",cancelled,retried,drained)}
}
