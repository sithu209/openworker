package store

import (
 "database/sql"
 "encoding/json"
 "errors"
 "strings"
 "time"
)

type Supervisor struct {
 SupervisorID string `json:"supervisor_id"`
 Machine string `json:"machine"`
 Model string `json:"model"`
 State string `json:"state"`
 CurrentSessionID string `json:"session_id,omitempty"`
 CurrentGoal string `json:"current_goal,omitempty"`
 StartedAt time.Time `json:"started_at"`
 HeartbeatAt time.Time `json:"heartbeat_at"`
 LastDecisionAt *time.Time `json:"last_decision_at,omitempty"`
}

type SupervisorSession struct {
 SessionID string `json:"session_id"`
 SupervisorID string `json:"supervisor_id"`
 Machine string `json:"machine"`
 Model string `json:"model"`
 StartedAt time.Time `json:"started_at"`
 EndedAt *time.Time `json:"ended_at,omitempty"`
 State string `json:"state"`
}

type SupervisorSnapshot struct {
 SupervisorID string `json:"supervisor_id"`
 Machine string `json:"machine"`
 CurrentGoal string `json:"current_goal,omitempty"`
 OwnedJobs []string `json:"owned_jobs"`
 WatchedJobs []string `json:"watched_jobs"`
 BlockedJobs []string `json:"blocked_jobs"`
 FailedJobs []string `json:"failed_jobs"`
 RecentCompletedJobs []string `json:"recent_completed_jobs"`
 LastDecision string `json:"last_decision,omitempty"`
 NextAttention []string `json:"next_attention"`
 UpdatedAt time.Time `json:"updated_at"`
}

type SupervisorDecision struct {
 DecisionID string `json:"decision_id"`
 SupervisorID string `json:"supervisor_id"`
 SessionID string `json:"session_id"`
 Machine string `json:"machine"`
 JobID string `json:"job_id,omitempty"`
 DecisionType string `json:"decision_type"`
 ReasonCode string `json:"reason_code"`
 InputStateHash string `json:"input_state_hash,omitempty"`
 Result string `json:"result,omitempty"`
 CreatedAt time.Time `json:"created_at"`
}

func (s *Store) ensureSupervisorSchema() error {
 _, err := s.db.Exec(`
CREATE TABLE IF NOT EXISTS supervisors(
 supervisor_id TEXT PRIMARY KEY,
 machine TEXT NOT NULL,
 model TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'active',
 current_session_id TEXT NOT NULL DEFAULT '',
 current_goal TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL,
 heartbeat_at TEXT NOT NULL,
 last_decision_at TEXT
);
CREATE TABLE IF NOT EXISTS supervisor_sessions(
 session_id TEXT PRIMARY KEY,
 supervisor_id TEXT NOT NULL,
 machine TEXT NOT NULL,
 model TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL,
 ended_at TEXT,
 state TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_supervisor_sessions_supervisor ON supervisor_sessions(supervisor_id, started_at DESC);
CREATE TABLE IF NOT EXISTS supervisor_snapshots(
 supervisor_id TEXT PRIMARY KEY,
 machine TEXT NOT NULL,
 current_goal TEXT NOT NULL DEFAULT '',
 owned_jobs_json TEXT NOT NULL DEFAULT '[]',
 watched_jobs_json TEXT NOT NULL DEFAULT '[]',
 blocked_jobs_json TEXT NOT NULL DEFAULT '[]',
 failed_jobs_json TEXT NOT NULL DEFAULT '[]',
 recent_completed_jobs_json TEXT NOT NULL DEFAULT '[]',
 last_decision TEXT NOT NULL DEFAULT '',
 next_attention_json TEXT NOT NULL DEFAULT '[]',
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS supervisor_decisions(
 decision_id TEXT PRIMARY KEY,
 supervisor_id TEXT NOT NULL,
 session_id TEXT NOT NULL,
 machine TEXT NOT NULL,
 job_id TEXT NOT NULL DEFAULT '',
 decision_type TEXT NOT NULL,
 reason_code TEXT NOT NULL,
 input_state_hash TEXT NOT NULL DEFAULT '',
 result TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_supervisor_decisions_supervisor ON supervisor_decisions(supervisor_id, created_at DESC);
`)
 return err
}

func (s *Store) StartSupervisorSession(v SupervisorSession, goal string) (SupervisorSession, error) {
 if err := s.ensureSupervisorSchema(); err != nil { return v, err }
 if strings.TrimSpace(v.SupervisorID)=="" || strings.TrimSpace(v.SessionID)=="" || strings.TrimSpace(v.Machine)=="" { return v, errors.New("supervisor_id, session_id and machine required") }
 if v.State=="" { v.State="active" }; if v.StartedAt.IsZero(){v.StartedAt=time.Now().UTC()}
 tx,err:=s.db.Begin(); if err!=nil{return v,err}; defer tx.Rollback()
 _,err=tx.Exec(`INSERT OR IGNORE INTO supervisor_sessions(session_id,supervisor_id,machine,model,started_at,state) VALUES(?,?,?,?,?,?)`,v.SessionID,v.SupervisorID,v.Machine,v.Model,nowText(v.StartedAt),v.State); if err!=nil{return v,err}
 now:=time.Now().UTC()
 _,err=tx.Exec(`INSERT INTO supervisors(supervisor_id,machine,model,state,current_session_id,current_goal,started_at,heartbeat_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(supervisor_id) DO UPDATE SET machine=excluded.machine,model=excluded.model,state='active',current_session_id=excluded.current_session_id,current_goal=excluded.current_goal,heartbeat_at=excluded.heartbeat_at`,v.SupervisorID,v.Machine,v.Model,"active",v.SessionID,goal,nowText(v.StartedAt),nowText(now));if err!=nil{return v,err}
 if err:=tx.Commit();err!=nil{return v,err};return v,nil
}

func (s *Store) SupervisorHeartbeat(supervisorID,sessionID,goal string) error {
 if err:=s.ensureSupervisorSchema();err!=nil{return err}; now:=time.Now().UTC()
 res,err:=s.db.Exec(`UPDATE supervisors SET heartbeat_at=?,current_goal=CASE WHEN ?='' THEN current_goal ELSE ? END,state='active' WHERE supervisor_id=? AND current_session_id=?`,nowText(now),goal,goal,supervisorID,sessionID);if err!=nil{return err};n,_:=res.RowsAffected();if n!=1{return errors.New("active supervisor session not found")};return nil
}

func (s *Store) SupervisorByID(id string)(Supervisor,error){if err:=s.ensureSupervisorSchema();err!=nil{return Supervisor{},err};var v Supervisor;var started,heartbeat string;var last sql.NullString;err:=s.db.QueryRow(`SELECT supervisor_id,machine,model,state,current_session_id,current_goal,started_at,heartbeat_at,last_decision_at FROM supervisors WHERE supervisor_id=?`,id).Scan(&v.SupervisorID,&v.Machine,&v.Model,&v.State,&v.CurrentSessionID,&v.CurrentGoal,&started,&heartbeat,&last);if err!=nil{return v,err};v.StartedAt,_=time.Parse(time.RFC3339Nano,started);v.HeartbeatAt,_=time.Parse(time.RFC3339Nano,heartbeat);v.LastDecisionAt=parseTime(last);return v,nil}

func (s *Store) SaveSupervisorSnapshot(v SupervisorSnapshot) error {if err:=s.ensureSupervisorSchema();err!=nil{return err};if v.UpdatedAt.IsZero(){v.UpdatedAt=time.Now().UTC()};b:=func(x []string)string{p,_:=json.Marshal(x);return string(p)};_,err:=s.db.Exec(`INSERT INTO supervisor_snapshots(supervisor_id,machine,current_goal,owned_jobs_json,watched_jobs_json,blocked_jobs_json,failed_jobs_json,recent_completed_jobs_json,last_decision,next_attention_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(supervisor_id) DO UPDATE SET machine=excluded.machine,current_goal=excluded.current_goal,owned_jobs_json=excluded.owned_jobs_json,watched_jobs_json=excluded.watched_jobs_json,blocked_jobs_json=excluded.blocked_jobs_json,failed_jobs_json=excluded.failed_jobs_json,recent_completed_jobs_json=excluded.recent_completed_jobs_json,last_decision=excluded.last_decision,next_attention_json=excluded.next_attention_json,updated_at=excluded.updated_at`,v.SupervisorID,v.Machine,v.CurrentGoal,b(v.OwnedJobs),b(v.WatchedJobs),b(v.BlockedJobs),b(v.FailedJobs),b(v.RecentCompletedJobs),v.LastDecision,b(v.NextAttention),nowText(v.UpdatedAt));return err}

func (s *Store) SupervisorSnapshotByID(id string)(SupervisorSnapshot,error){if err:=s.ensureSupervisorSchema();err!=nil{return SupervisorSnapshot{},err};var v SupervisorSnapshot;var owned,watched,blocked,failed,completed,attention,updated string;err:=s.db.QueryRow(`SELECT supervisor_id,machine,current_goal,owned_jobs_json,watched_jobs_json,blocked_jobs_json,failed_jobs_json,recent_completed_jobs_json,last_decision,next_attention_json,updated_at FROM supervisor_snapshots WHERE supervisor_id=?`,id).Scan(&v.SupervisorID,&v.Machine,&v.CurrentGoal,&owned,&watched,&blocked,&failed,&completed,&v.LastDecision,&attention,&updated);if err!=nil{return v,err};_=json.Unmarshal([]byte(owned),&v.OwnedJobs);_=json.Unmarshal([]byte(watched),&v.WatchedJobs);_=json.Unmarshal([]byte(blocked),&v.BlockedJobs);_=json.Unmarshal([]byte(failed),&v.FailedJobs);_=json.Unmarshal([]byte(completed),&v.RecentCompletedJobs);_=json.Unmarshal([]byte(attention),&v.NextAttention);v.UpdatedAt,_=time.Parse(time.RFC3339Nano,updated);return v,nil}

func (s *Store) RecordSupervisorDecision(v SupervisorDecision) error {if err:=s.ensureSupervisorSchema();err!=nil{return err};switch v.DecisionType{case "submit","retry","cancel","wait","inspect","replan","escalate":default:return errors.New("invalid decision_type")};if v.DecisionID==""||v.SupervisorID==""||v.SessionID==""||v.ReasonCode==""{return errors.New("decision_id, supervisor_id, session_id and reason_code required")};if v.CreatedAt.IsZero(){v.CreatedAt=time.Now().UTC()};tx,err:=s.db.Begin();if err!=nil{return err};defer tx.Rollback();_,err=tx.Exec(`INSERT INTO supervisor_decisions(decision_id,supervisor_id,session_id,machine,job_id,decision_type,reason_code,input_state_hash,result,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)`,v.DecisionID,v.SupervisorID,v.SessionID,v.Machine,v.JobID,v.DecisionType,v.ReasonCode,v.InputStateHash,v.Result,nowText(v.CreatedAt));if err!=nil{return err};_,err=tx.Exec(`UPDATE supervisors SET last_decision_at=? WHERE supervisor_id=? AND current_session_id=?`,nowText(v.CreatedAt),v.SupervisorID,v.SessionID);if err!=nil{return err};return tx.Commit()}

func (s *Store) SupervisorDecisions(id string,limit int)([]SupervisorDecision,error){if err:=s.ensureSupervisorSchema();err!=nil{return nil,err};if limit<=0||limit>1000{limit=100};rows,err:=s.db.Query(`SELECT decision_id,supervisor_id,session_id,machine,job_id,decision_type,reason_code,input_state_hash,result,created_at FROM supervisor_decisions WHERE supervisor_id=? ORDER BY created_at DESC LIMIT ?`,id,limit);if err!=nil{return nil,err};defer rows.Close();out:=[]SupervisorDecision{};for rows.Next(){var v SupervisorDecision;var created string;if err:=rows.Scan(&v.DecisionID,&v.SupervisorID,&v.SessionID,&v.Machine,&v.JobID,&v.DecisionType,&v.ReasonCode,&v.InputStateHash,&v.Result,&created);err!=nil{return nil,err};v.CreatedAt,_=time.Parse(time.RFC3339Nano,created);out=append(out,v)};return out,rows.Err()}
