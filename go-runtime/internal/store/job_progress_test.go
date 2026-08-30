package store

import(
 "path/filepath"
 "testing"
 "github.com/liuxb99/openworker/go-runtime/internal/model"
)
func TestJobProgressAttentionRoundTrip(t *testing.T){st,err:=Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();_,err=st.Submit(model.SubmitRequest{JobID:"J1",DispatchID:"D1",Machine:"HOST",Command:"echo ok",CWD:"C:/work"},"HOST");if err!=nil{t.Fatal(err)};if err:=st.UpdateJobProgress(JobProgress{JobID:"J1",CurrentStep:"render",Progress:72,Message:"frame 144/200",ArtifactState:"pending",QCState:"waiting",AttentionRequired:true});err!=nil{t.Fatal(err)};p,err:=st.JobProgressByID("J1");if err!=nil{t.Fatal(err)};if p.Progress!=72||p.CurrentStep!="render"||!p.AttentionRequired{t.Fatalf("progress=%+v",p)};rows,err:=st.AttentionProgress(10);if err!=nil{t.Fatal(err)};if len(rows)!=1||rows[0].JobID!="J1"{t.Fatalf("attention=%+v",rows)}}
func TestJobProgressRejectsInvalidPercent(t *testing.T){st,err:=Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();if err:=st.UpdateJobProgress(JobProgress{JobID:"missing",Progress:101});err==nil{t.Fatal("invalid progress must fail")}}
