package runtime_test

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/liuxb99/openworker/go-runtime/internal/model"
	owruntime "github.com/liuxb99/openworker/go-runtime/internal/runtime"
	"github.com/liuxb99/openworker/go-runtime/internal/store"
)

func TestStartupRecoveryMarksLostActiveJobStale(t *testing.T) {
	root:=t.TempDir()
	st,err:=store.Open(filepath.Join(root,"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close()
	_,err=st.Submit(model.SubmitRequest{JobID:"OWJ-REC",DispatchID:"OWD-REC",Machine:"TESTHOST",Command:"echo never",CWD:t.TempDir(),TimeoutSec:10},"TESTHOST");if err!=nil{t.Fatal(err)}
	j,err:=st.ClaimNext();if err!=nil||j==nil{t.Fatalf("claim failed: %v",err)}
	rt:=owruntime.New(st,1,filepath.Join(root,"logs"),"TESTHOST")
	if err:=rt.Start();err!=nil{t.Fatal(err)}
	defer rt.Stop()
	time.Sleep(50*time.Millisecond)
	got,err:=st.Get("OWJ-REC");if err!=nil{t.Fatal(err)}
	if got.Status!=model.StatusStale{t.Fatalf("expected stale, got %s",got.Status)}
	events,err:=st.Events("OWJ-REC",20);if err!=nil{t.Fatal(err)}
	found:=false;for _,e:=range events{if e.EventType=="stale"{found=true}}
	if !found{t.Fatal("missing stale recovery event")}
}
