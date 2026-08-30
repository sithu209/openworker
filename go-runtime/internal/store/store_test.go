package store_test

import (
	"path/filepath"
	"testing"

	"github.com/liuxb99/openworker/go-runtime/internal/model"
	"github.com/liuxb99/openworker/go-runtime/internal/store"
)

func TestSubmitIsIdempotent(t *testing.T){
	st,err:=store.Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close()
	req:=model.SubmitRequest{JobID:"OWJ-1",DispatchID:"OWD-1",Machine:"TESTHOST",Command:"echo ok",CWD:t.TempDir(),TimeoutSec:10}
	a1,err:=st.Submit(req,"TESTHOST");if err!=nil{t.Fatal(err)}
	a2,err:=st.Submit(req,"TESTHOST");if err!=nil{t.Fatal(err)}
	if !a1.Accepted||!a2.Accepted||!a2.Duplicate{t.Fatalf("unexpected ACKs: %#v %#v",a1,a2)}
	jobs,err:=st.List(100);if err!=nil{t.Fatal(err)};if len(jobs)!=1{t.Fatalf("expected one durable job, got %d",len(jobs))}
}

func TestMachineMismatchFailsClosed(t *testing.T){
	st,err:=store.Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close()
	_,err=st.Submit(model.SubmitRequest{JobID:"OWJ-2",DispatchID:"OWD-2",Machine:"UL7",Command:"echo no",CWD:t.TempDir()},"O87")
	if err==nil{t.Fatal("expected machine mismatch error")}
}
