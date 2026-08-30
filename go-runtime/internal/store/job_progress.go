package store

import (
 "errors"
 "time"
)

type JobProgress struct {
 JobID string `json:"job_id"`
 CurrentStep string `json:"current_step,omitempty"`
 Progress int `json:"progress"`
 Message string `json:"message,omitempty"`
 ArtifactState string `json:"artifact_state,omitempty"`
 QCState string `json:"qc_state,omitempty"`
 Error string `json:"error,omitempty"`
 AttentionRequired bool `json:"attention_required"`
 UpdatedAt time.Time `json:"updated_at"`
}

func(s *Store)ensureJobProgressSchema()error{_,err:=s.db.Exec(`CREATE TABLE IF NOT EXISTS job_progress(job_id TEXT PRIMARY KEY,current_step TEXT NOT NULL DEFAULT '',progress INTEGER NOT NULL DEFAULT 0,message TEXT NOT NULL DEFAULT '',artifact_state TEXT NOT NULL DEFAULT '',qc_state TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',attention_required INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_job_progress_attention ON job_progress(attention_required,updated_at DESC);`);return err}
func(s *Store)UpdateJobProgress(v JobProgress)error{if err:=s.ensureJobProgressSchema();err!=nil{return err};if v.JobID==""{return errors.New("job_id required")};if v.Progress<0||v.Progress>100{return errors.New("progress must be 0..100")};if _,err:=s.Get(v.JobID);err!=nil{return err};if v.UpdatedAt.IsZero(){v.UpdatedAt=time.Now().UTC()};a:=0;if v.AttentionRequired{a=1};_,err:=s.db.Exec(`INSERT INTO job_progress(job_id,current_step,progress,message,artifact_state,qc_state,error,attention_required,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET current_step=excluded.current_step,progress=excluded.progress,message=excluded.message,artifact_state=excluded.artifact_state,qc_state=excluded.qc_state,error=excluded.error,attention_required=excluded.attention_required,updated_at=excluded.updated_at`,v.JobID,v.CurrentStep,v.Progress,v.Message,v.ArtifactState,v.QCState,v.Error,a,nowText(v.UpdatedAt));return err}
func(s *Store)JobProgressByID(jobID string)(JobProgress,error){if err:=s.ensureJobProgressSchema();err!=nil{return JobProgress{},err};var v JobProgress;var a int;var updated string;err:=s.db.QueryRow(`SELECT job_id,current_step,progress,message,artifact_state,qc_state,error,attention_required,updated_at FROM job_progress WHERE job_id=?`,jobID).Scan(&v.JobID,&v.CurrentStep,&v.Progress,&v.Message,&v.ArtifactState,&v.QCState,&v.Error,&a,&updated);if err!=nil{return v,err};v.AttentionRequired=a!=0;v.UpdatedAt,_=time.Parse(time.RFC3339Nano,updated);return v,nil}
func(s *Store)AttentionProgress(limit int)([]JobProgress,error){if err:=s.ensureJobProgressSchema();err!=nil{return nil,err};if limit<=0||limit>1000{limit=100};rows,err:=s.db.Query(`SELECT job_id,current_step,progress,message,artifact_state,qc_state,error,attention_required,updated_at FROM job_progress WHERE attention_required=1 ORDER BY updated_at DESC LIMIT ?`,limit);if err!=nil{return nil,err};defer rows.Close();out:=[]JobProgress{};for rows.Next(){var v JobProgress;var a int;var updated string;if err:=rows.Scan(&v.JobID,&v.CurrentStep,&v.Progress,&v.Message,&v.ArtifactState,&v.QCState,&v.Error,&a,&updated);err!=nil{return nil,err};v.AttentionRequired=a!=0;v.UpdatedAt,_=time.Parse(time.RFC3339Nano,updated);out=append(out,v)};return out,rows.Err()}
