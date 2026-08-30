package store

import (
 "path/filepath"
 "testing"
 "time"
)

func TestSupervisorDurableSessionSnapshotDecision(t *testing.T){
 st,err:=Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close()
 sess,err:=st.StartSupervisorSession(SupervisorSession{SessionID:"S1",SupervisorID:"ODA-CODER-01",Machine:"DESKTOP-ODAQN0D",Model:"qwen-coder"},"finish case0002");if err!=nil{t.Fatal(err)};if sess.SessionID!="S1"{t.Fatal(sess)}
 if err:=st.SupervisorHeartbeat("ODA-CODER-01","S1","continue case0002");err!=nil{t.Fatal(err)}
 snap:=SupervisorSnapshot{SupervisorID:"ODA-CODER-01",Machine:"DESKTOP-ODAQN0D",CurrentGoal:"continue case0002",OwnedJobs:[]string{"J1"},WatchedJobs:[]string{"J2"},FailedJobs:[]string{"J3"},NextAttention:[]string{"J3"}}
 if err:=st.SaveSupervisorSnapshot(snap);err!=nil{t.Fatal(err)}
 got,err:=st.SupervisorSnapshotByID("ODA-CODER-01");if err!=nil{t.Fatal(err)};if len(got.FailedJobs)!=1||got.FailedJobs[0]!="J3"{t.Fatalf("snapshot=%+v",got)}
 if err:=st.RecordSupervisorDecision(SupervisorDecision{DecisionID:"D1",SupervisorID:"ODA-CODER-01",SessionID:"S1",Machine:"DESKTOP-ODAQN0D",JobID:"J3",DecisionType:"inspect",ReasonCode:"JOB_FAILED",InputStateHash:"abc",Result:"inspect events",CreatedAt:time.Now().UTC()});err!=nil{t.Fatal(err)}
 rows,err:=st.SupervisorDecisions("ODA-CODER-01",10);if err!=nil{t.Fatal(err)};if len(rows)!=1||rows[0].ReasonCode!="JOB_FAILED"{t.Fatalf("decisions=%+v",rows)}
}

func TestSupervisorRejectsUnknownDecisionType(t *testing.T){st,err:=Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();_,err=st.StartSupervisorSession(SupervisorSession{SessionID:"S1",SupervisorID:"SUP",Machine:"HOST"},"");if err!=nil{t.Fatal(err)};if err:=st.RecordSupervisorDecision(SupervisorDecision{DecisionID:"D1",SupervisorID:"SUP",SessionID:"S1",Machine:"HOST",DecisionType:"delete_everything",ReasonCode:"x"});err==nil{t.Fatal("unknown decision type must fail closed")}}
