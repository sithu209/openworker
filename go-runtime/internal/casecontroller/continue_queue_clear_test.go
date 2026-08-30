package casecontroller

import (
    "context"
    "encoding/json"
    "net/http"
    "os"
    "path/filepath"
    "strings"
    "testing"
)

func TestContinueRecoversStaleControllerWorkAfterQueueClear(t *testing.T){
    workspace,marker:=setupCase(t)
    stale:=controllerWorkRef{WorkID:"case0005-0005-010-r000014-cleared",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction"}
    rb,_:=json.Marshal(stale)
    if err:=os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644);err!=nil{t.Fatal(err)}

    gets:=0
    posts:=0
    var submittedID string
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){
        switch r.Method{
        case http.MethodGet:
            gets++
            return responseJSON(http.StatusNotFound,map[string]any{"error":"work not found"}),nil
        case http.MethodPost:
            posts++
            var submitted map[string]any
            if err:=json.NewDecoder(r.Body).Decode(&submitted);err!=nil{t.Fatal(err)}
            submittedID=strings.TrimSpace(submitted["work_id"].(string))
            return responseJSON(http.StatusCreated,map[string]any{"work_id":submittedID,"assigned_host":"DESKTOP-ODAQN0D","capability_id":"comfyx-studio.director.preproduction","status":"pending","attempts":0}),nil
        default:
            t.Fatalf("unexpected method %s",r.Method)
            return nil,nil
        }
    })}

    got,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client)
    if err!=nil{t.Fatal(err)}
    if gets!=1||posts!=1{t.Fatalf("expected stale GET then one resubmit, gets=%d posts=%d",gets,posts)}
    if got.StepID!="0005-010"||got.WorkID==""||got.WorkID!=submittedID||got.QueueStatus!="pending"{t.Fatalf("unexpected result %#v",got)}
    if got.WorkID==stale.WorkID{t.Fatalf("test stale work id should differ from deterministic resubmission: %s",got.WorkID)}

    ledger,err:=os.ReadFile(filepath.Join(marker,"case-supervisor-ledger.jsonl"));if err!=nil{t.Fatal(err)}
    if !strings.Contains(string(ledger),"go_stale_controller_work_ref_cleared"){t.Fatalf("missing stale-ref repair ledger: %s",string(ledger))}
}

func TestContinueDoesNotRecoverMissingWorkForFailedStep(t *testing.T){
    workspace,marker:=setupCase(t)
    wb,err:=os.ReadFile(filepath.Join(marker,"case-worklist.json"));if err!=nil{t.Fatal(err)}
    var w Worklist;if err:=json.Unmarshal(wb,&w);err!=nil{t.Fatal(err)}
    step:=findStep(w.Steps,"0005-010");step.Status="FAILED";step.Blocker="prior terminal failure"
    if err:=persistWorklist(filepath.Join(marker,"case-worklist.json"),w);err!=nil{t.Fatal(err)}
    stale:=controllerWorkRef{WorkID:"w-cleared-after-failure",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction"}
    rb,_:=json.Marshal(stale);if err:=os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644);err!=nil{t.Fatal(err)}
    posts:=0
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){if r.Method==http.MethodPost{posts++};return responseJSON(http.StatusNotFound,map[string]any{"error":"work not found"}),nil})}
    _,err=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client)
    if err==nil||!strings.Contains(err.Error(),"explicit repair required"){t.Fatalf("expected fail-closed failed-step error, got %v",err)}
    if posts!=0{t.Fatalf("failed step must not be resubmitted, posts=%d",posts)}
}
