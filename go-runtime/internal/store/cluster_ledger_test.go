package store_test

import(
 "path/filepath"
 "testing"
 "time"
 "github.com/liuxb99/openworker/go-runtime/internal/store"
)

func TestClusterDispatchLedgerRoundTrip(t *testing.T){st,err:=store.Open(filepath.Join(t.TempDir(),"node.sqlite3"));if err!=nil{t.Fatal(err)};defer st.Close();now:=time.Now().UTC();d:=store.ClusterDispatch{JobID:"OWJ-C1",DispatchID:"OWD-C1",RequestedMachine:"any",SelectedNodeID:"ul7",SelectedMachine:"DESKTOP-UL7V2VV",Endpoint:"http://ul7:8787",RequiredCapabilities:[]string{"bridge","blender"},AcceptedAt:now};if err:=st.RecordClusterDispatch(d);err!=nil{t.Fatal(err)};got,err:=st.ClusterDispatch("OWJ-C1");if err!=nil{t.Fatal(err)};if got.SelectedNodeID!="ul7"||got.Endpoint!="http://ul7:8787"||len(got.RequiredCapabilities)!=2{t.Fatalf("unexpected dispatch %+v",got)};if err:=st.RecordClusterControl("OWJ-C1","cancel","ul7","forwarded");err!=nil{t.Fatal(err)};events,err:=st.ClusterControlEvents("OWJ-C1",10);if err!=nil{t.Fatal(err)};if len(events)!=1||events[0].Action!="cancel"{t.Fatalf("unexpected events %+v",events)}}
