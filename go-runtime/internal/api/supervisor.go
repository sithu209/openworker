package api

import (
 "database/sql"
 "encoding/json"
 "errors"
 "net/http"
 "strings"
 "time"

 "github.com/liuxb99/openworker/go-runtime/internal/model"
 "github.com/liuxb99/openworker/go-runtime/internal/store"
)

type supervisorSessionRequest struct{SupervisorID string `json:"supervisor_id"`;SessionID string `json:"session_id"`;Model string `json:"model"`;CurrentGoal string `json:"current_goal,omitempty"`}
type supervisorHeartbeatRequest struct{SupervisorID string `json:"supervisor_id"`;SessionID string `json:"session_id"`;CurrentGoal string `json:"current_goal,omitempty"`}
type supervisorDecisionRequest struct{DecisionID string `json:"decision_id"`;SupervisorID string `json:"supervisor_id"`;SessionID string `json:"session_id"`;JobID string `json:"job_id,omitempty"`;DecisionType string `json:"decision_type"`;ReasonCode string `json:"reason_code"`;InputStateHash string `json:"input_state_hash,omitempty"`;Result string `json:"result,omitempty"`}

func(s *Server)supervisorRoutes(){
 s.mux.HandleFunc("POST /v1/supervisor/session",s.supervisorSession)
 s.mux.HandleFunc("POST /v1/supervisor/heartbeat",s.supervisorHeartbeat)
 s.mux.HandleFunc("GET /v1/supervisor/snapshot",s.supervisorSnapshot)
 s.mux.HandleFunc("GET /v1/supervisor/jobs",s.supervisorJobs)
 s.mux.HandleFunc("POST /v1/supervisor/recover",s.supervisorRecover)
 s.mux.HandleFunc("POST /v1/supervisor/decision",s.supervisorDecision)
 s.mux.HandleFunc("GET /v1/supervisor/decisions",s.supervisorDecisions)
 s.mux.HandleFunc("GET /v1/supervisor/attention",s.supervisorAttention)
 s.mux.HandleFunc("POST /v1/cases/bootstrap",s.caseBootstrap)
 s.mux.HandleFunc("GET /v1/jobs/{jobID}/progress",s.jobProgress)
 s.mux.HandleFunc("POST /v1/jobs/{jobID}/progress",s.updateJobProgress)
 s.mux.HandleFunc("GET /v1/jobs/{jobID}/explain",s.jobExplain)
}

func(s *Server)supervisorSession(w http.ResponseWriter,r *http.Request){var req supervisorSessionRequest;d:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20));d.DisallowUnknownFields();if err:=d.Decode(&req);err!=nil{writeErr(w,400,err);return};v,err:=s.store.StartSupervisorSession(store.SupervisorSession{SessionID:req.SessionID,SupervisorID:req.SupervisorID,Machine:s.machine,Model:req.Model,State:"active"},req.CurrentGoal);if err!=nil{writeErr(w,409,err);return};writeJSON(w,201,v)}
func(s *Server)supervisorHeartbeat(w http.ResponseWriter,r *http.Request){var req supervisorHeartbeatRequest;if err:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20)).Decode(&req);err!=nil{writeErr(w,400,err);return};if err:=s.store.SupervisorHeartbeat(req.SupervisorID,req.SessionID,req.CurrentGoal);err!=nil{writeErr(w,409,err);return};v,_:=s.store.SupervisorByID(req.SupervisorID);writeJSON(w,200,v)}
func(s *Server)supervisorSnapshot(w http.ResponseWriter,r *http.Request){id:=strings.TrimSpace(r.URL.Query().Get("supervisor_id"));if id==""{writeErr(w,400,errors.New("supervisor_id required"));return};v,err:=s.store.SupervisorSnapshotByID(id);if errors.Is(err,sql.ErrNoRows){writeErr(w,404,err);return};if err!=nil{writeErr(w,500,err);return};writeJSON(w,200,v)}
func(s *Server)supervisorJobs(w http.ResponseWriter,r *http.Request){id:=strings.TrimSpace(r.URL.Query().Get("supervisor_id"));if id==""{writeErr(w,400,errors.New("supervisor_id required"));return};sup,err:=s.store.SupervisorByID(id);if err!=nil{writeErr(w,404,err);return};jobs,err:=s.store.List(1000);if err!=nil{writeErr(w,500,err);return};owned:=[]map[string]any{};for _,j:=range jobs{if !strings.EqualFold(j.Machine,sup.Machine){continue};row:=map[string]any{"job":j};if p,e:=s.store.JobProgressByID(j.JobID);e==nil{row["progress"]=p};owned=append(owned,row)};writeJSON(w,200,map[string]any{"supervisor_id":id,"machine":sup.Machine,"jobs":owned,"count":len(owned)})}
func(s *Server)supervisorRecover(w http.ResponseWriter,r *http.Request){var req struct{SupervisorID string `json:"supervisor_id"`;SessionID string `json:"session_id"`};if err:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20)).Decode(&req);err!=nil{writeErr(w,400,err);return};sup,err:=s.store.SupervisorByID(req.SupervisorID);if err!=nil{writeErr(w,404,err);return};if req.SessionID!=""&&sup.CurrentSessionID!=req.SessionID{writeErr(w,409,errors.New("session_id is not current supervisor session"));return};jobs,err:=s.store.List(1000);if err!=nil{writeErr(w,500,err);return};snap:=store.SupervisorSnapshot{SupervisorID:sup.SupervisorID,Machine:sup.Machine,CurrentGoal:sup.CurrentGoal,OwnedJobs:[]string{},WatchedJobs:[]string{},BlockedJobs:[]string{},FailedJobs:[]string{},RecentCompletedJobs:[]string{},NextAttention:[]string{},UpdatedAt:time.Now().UTC()};if old,e:=s.store.SupervisorSnapshotByID(req.SupervisorID);e==nil{snap.WatchedJobs=old.WatchedJobs;snap.LastDecision=old.LastDecision}
 for _,j:=range jobs{if !strings.EqualFold(j.Machine,sup.Machine){continue};snap.OwnedJobs=append(snap.OwnedJobs,j.JobID);switch j.Status{case model.StatusFailed,model.StatusTimedOut,model.StatusStale:snap.FailedJobs=append(snap.FailedJobs,j.JobID);snap.NextAttention=appendUnique(snap.NextAttention,j.JobID);case model.StatusSucceeded:snap.RecentCompletedJobs=append(snap.RecentCompletedJobs,j.JobID);case model.StatusQueued:if j.AgentSlot==0{snap.BlockedJobs=append(snap.BlockedJobs,j.JobID)}};if p,e:=s.store.JobProgressByID(j.JobID);e==nil&&p.AttentionRequired{snap.NextAttention=appendUnique(snap.NextAttention,j.JobID)}}
 if len(snap.RecentCompletedJobs)>20{snap.RecentCompletedJobs=snap.RecentCompletedJobs[:20]};decisions,_:=s.store.SupervisorDecisions(req.SupervisorID,1);if len(decisions)>0{snap.LastDecision=decisions[0].DecisionType+":"+decisions[0].ReasonCode};if err:=s.store.SaveSupervisorSnapshot(snap);err!=nil{writeErr(w,500,err);return};writeJSON(w,200,map[string]any{"supervisor":sup,"snapshot":snap,"recovered":true})}
func(s *Server)supervisorDecision(w http.ResponseWriter,r *http.Request){var req supervisorDecisionRequest;d:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20));d.DisallowUnknownFields();if err:=d.Decode(&req);err!=nil{writeErr(w,400,err);return};sup,err:=s.store.SupervisorByID(req.SupervisorID);if err!=nil{writeErr(w,404,err);return};if sup.CurrentSessionID!=req.SessionID{writeErr(w,409,errors.New("decision session is not current supervisor session"));return};v:=store.SupervisorDecision{DecisionID:req.DecisionID,SupervisorID:req.SupervisorID,SessionID:req.SessionID,Machine:s.machine,JobID:req.JobID,DecisionType:req.DecisionType,ReasonCode:req.ReasonCode,InputStateHash:req.InputStateHash,Result:req.Result};if err:=s.store.RecordSupervisorDecision(v);err!=nil{writeErr(w,409,err);return};writeJSON(w,201,v)}
func(s *Server)supervisorDecisions(w http.ResponseWriter,r *http.Request){id:=strings.TrimSpace(r.URL.Query().Get("supervisor_id"));if id==""{writeErr(w,400,errors.New("supervisor_id required"));return};rows,err:=s.store.SupervisorDecisions(id,queryInt(r,"limit",100));if err!=nil{writeErr(w,500,err);return};writeJSON(w,200,map[string]any{"decisions":rows,"count":len(rows)})}
func(s *Server)updateJobProgress(w http.ResponseWriter,r *http.Request){var p store.JobProgress;d:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20));d.DisallowUnknownFields();if err:=d.Decode(&p);err!=nil{writeErr(w,400,err);return};id:=r.PathValue("jobID");if p.JobID!=""&&p.JobID!=id{writeErr(w,409,errors.New("job_id mismatch"));return};p.JobID=id;if err:=s.store.UpdateJobProgress(p);err!=nil{writeErr(w,409,err);return};got,_:=s.store.JobProgressByID(id);writeJSON(w,200,got)}
func(s *Server)jobProgress(w http.ResponseWriter,r *http.Request){v,err:=s.store.JobProgressByID(r.PathValue("jobID"));if err!=nil{writeErr(w,404,err);return};writeJSON(w,200,v)}
func(s *Server)jobExplain(w http.ResponseWriter,r *http.Request){
 id:=r.PathValue("jobID")
 j,err:=s.store.Get(id);if err!=nil{writeErr(w,404,err);return}
 events,err:=s.store.Events(id,200);if err!=nil{writeErr(w,500,err);return}
 var summary any
 for _,e:=range events{if e.EventType!="execution_summary"{continue};var v any;if json.Unmarshal([]byte(e.Detail),&v)==nil{summary=v}else{summary=map[string]any{"raw":e.Detail}};break}
 out:=map[string]any{"job":j,"execution_summary":summary,"events":events,"authority":"openworker-local-durable-ledger","observed_at":time.Now().UTC()}
 if p,e:=s.store.JobProgressByID(id);e==nil{out["progress"]=p}
 writeJSON(w,200,out)
}
func(s *Server)supervisorAttention(w http.ResponseWriter,r *http.Request){id:=strings.TrimSpace(r.URL.Query().Get("supervisor_id"));if id==""{writeErr(w,400,errors.New("supervisor_id required"));return};sup,err:=s.store.SupervisorByID(id);if err!=nil{writeErr(w,404,err);return};jobs,err:=s.store.List(1000);if err!=nil{writeErr(w,500,err);return};items:=[]map[string]any{};seen:=map[string]bool{};for _,j:=range jobs{if !strings.EqualFold(j.Machine,sup.Machine){continue};reason:="";switch j.Status{case model.StatusFailed:reason="job_failed";case model.StatusTimedOut:reason="job_timed_out";case model.StatusStale:reason="job_stale"};if reason!=""{items=append(items,map[string]any{"job_id":j.JobID,"reason":reason,"status":j.Status});seen[j.JobID]=true}};rows,_:=s.store.AttentionProgress(1000);for _,p:=range rows{if seen[p.JobID]{continue};j,e:=s.store.Get(p.JobID);if e!=nil||!strings.EqualFold(j.Machine,sup.Machine){continue};items=append(items,map[string]any{"job_id":p.JobID,"reason":"progress_attention","status":j.Status,"progress":p})};writeJSON(w,200,map[string]any{"supervisor_id":id,"machine":sup.Machine,"attention":items,"count":len(items),"observed_at":time.Now().UTC()})}
func appendUnique(v []string,x string)[]string{for _,e:=range v{if e==x{return v}};return append(v,x)}