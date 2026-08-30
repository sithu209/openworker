package casecontroller

import (
    "bytes"
    "context"
    "encoding/json"
    "io"
    "net/http"
    "os"
    "path/filepath"
    "strings"
    "testing"
)

type roundTripFunc func(*http.Request)(*http.Response,error)
func(f roundTripFunc)RoundTrip(r *http.Request)(*http.Response,error){return f(r)}

func setupCase(t *testing.T)(string,string){
    t.Helper();workspace:=filepath.Join(t.TempDir(),"workspace");marker:=filepath.Join(workspace,".openworker");if err:=os.MkdirAll(marker,0o755);err!=nil{t.Fatal(err)}
    worklist:=Worklist{SchemaVersion:"openworker-case-worklist/v1",CaseID:"0005",WorkspaceRoot:workspace,AssignedHost:"DESKTOP-ODAQN0D",Revision:14,Steps:[]Step{
        {StepID:"0005-010",Dependencies:[]string{},AllowedActions:[]string{"comfyx-studio.director.preproduction"},Acceptance:[]string{"run_id","director_plan","director_plan_sha256","shot_count","character_count","scene_bible_count"},Status:"PENDING",Evidence:map[string]any{}},
        {StepID:"0005-020",Dependencies:[]string{"0005-010"},AllowedActions:[]string{"comfyx-studio.storyboard.plan"},Acceptance:[]string{"storyboard_request","visual_requirements","visual_asset_count","reference_asset_ids"},Status:"PENDING",Evidence:map[string]any{}},
    }}
    wb,_:=json.Marshal(worklist);if err:=os.WriteFile(filepath.Join(marker,"case-worklist.json"),wb,0o644);err!=nil{t.Fatal(err)}
    sb,_:=json.Marshal(map[string]any{"case_id":"0005","title":"Snow White","source_story":"A story"});if err:=os.WriteFile(filepath.Join(marker,"case-spec.json"),sb,0o644);err!=nil{t.Fatal(err)}
    return workspace,marker
}

func responseJSON(status int,v any)*http.Response{b,_:=json.Marshal(v);return &http.Response{StatusCode:status,Body:io.NopCloser(bytes.NewReader(b)),Header:make(http.Header)}}

func TestContinueSubmitsDirectorThenDoesNotResubmitPendingWork(t *testing.T){
    workspace,_:=setupCase(t);posts:=0;gets:=0
    var firstID string
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){
        switch r.Method {
        case http.MethodPost:
            posts++;var submitted map[string]any;if err:=json.NewDecoder(r.Body).Decode(&submitted);err!=nil{t.Fatal(err)};firstID=strings.TrimSpace(submitted["work_id"].(string));return responseJSON(http.StatusCreated,map[string]any{"work_id":firstID,"assigned_host":"DESKTOP-ODAQN0D","capability_id":"comfyx-studio.director.preproduction","status":"pending","attempts":0}),nil
        case http.MethodGet:
            gets++;return responseJSON(http.StatusOK,map[string]any{"work_id":firstID,"assigned_host":"DESKTOP-ODAQN0D","capability_id":"comfyx-studio.director.preproduction","status":"pending","attempts":0}),nil
        default:t.Fatalf("unexpected method %s",r.Method);return nil,nil
        }
    })}
    got,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err!=nil{t.Fatal(err)}
    if got.StepID!="0005-010"||got.QueueStatus!="pending"{t.Fatalf("unexpected first result %#v",got)}
    got2,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err!=nil{t.Fatal(err)}
    if got2.WorkID!=got.WorkID||got2.QueueStatus!="pending"{t.Fatalf("unexpected existing result %#v",got2)}
    if posts!=1||gets!=1{t.Fatalf("expected one submit and one status read, posts=%d gets=%d",posts,gets)}
}

func TestContinueReconcilesCompletedDirectorAndSubmitsStoryboard(t *testing.T){
    workspace,marker:=setupCase(t);plan:=filepath.Join(workspace,"director","project-plan.json");if err:=os.MkdirAll(filepath.Dir(plan),0o755);err!=nil{t.Fatal(err)};if err:=os.WriteFile(plan,[]byte("{}\n"),0o644);err!=nil{t.Fatal(err)}
    ref:=controllerWorkRef{WorkID:"case0005-0005-010-r000014-old",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction"};rb,_:=json.Marshal(ref);_ = os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644)
    evidence:=map[string]any{"run_id":"r1","director_plan":plan,"director_plan_sha256":"abc","shot_count":4,"character_count":2,"scene_bible_count":2}
    posts:=0
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){
        if r.Method==http.MethodGet{return responseJSON(http.StatusOK,map[string]any{"work_id":ref.WorkID,"assigned_host":"DESKTOP-ODAQN0D","capability_id":ref.ActionID,"status":"completed","result":map[string]any{"work_id":ref.WorkID,"capability_id":ref.ActionID,"status":"completed","evidence":evidence}}),nil}
        if r.Method==http.MethodPost{posts++;var submitted map[string]any;_ = json.NewDecoder(r.Body).Decode(&submitted);if submitted["capability_id"]!="comfyx-studio.storyboard.plan"{t.Fatalf("unexpected capability %#v",submitted)};inputs:=submitted["inputs"].(map[string]any);if filepath.Clean(inputs["director_plan_relpath"].(string))!=filepath.Clean(filepath.Join("director","project-plan.json")){t.Fatalf("unexpected relpath %#v",inputs)};return responseJSON(http.StatusCreated,map[string]any{"work_id":submitted["work_id"],"assigned_host":"DESKTOP-ODAQN0D","capability_id":"comfyx-studio.storyboard.plan","status":"pending","attempts":0}),nil}
        t.Fatalf("unexpected method %s",r.Method);return nil,nil
    })}
    got,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err!=nil{t.Fatal(err)}
    if got.StepID!="0005-020"||got.ActionID!="comfyx-studio.storyboard.plan"||len(got.ReconciledStepIDs)!=1||got.ReconciledStepIDs[0]!="0005-010"{t.Fatalf("unexpected result %#v",got)}
    if posts!=1{t.Fatalf("expected one storyboard submit, got %d",posts)}
    wb,err:=os.ReadFile(filepath.Join(marker,"case-worklist.json"));if err!=nil{t.Fatal(err)};var w Worklist;if err:=json.Unmarshal(wb,&w);err!=nil{t.Fatal(err)};s:=findStep(w.Steps,"0005-010");if s==nil||s.Status!="SUCCEEDED"||s.Evidence["director_plan_sha256"]!="abc"{t.Fatalf("director step not reconciled %#v",s)}
}

func TestContinueRejectsCompletedDirectorMissingAcceptance(t *testing.T){
    workspace,marker:=setupCase(t);ref:=controllerWorkRef{WorkID:"w1",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction"};rb,_:=json.Marshal(ref);_ = os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644)
    posts:=0;client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){if r.Method==http.MethodPost{posts++;t.Fatal("must not submit after invalid terminal evidence")};return responseJSON(http.StatusOK,map[string]any{"work_id":"w1","status":"completed","result":map[string]any{"evidence":map[string]any{"run_id":"r1"}}}),nil})}
    _,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err==nil||!strings.Contains(err.Error(),"missing acceptance evidence"){t.Fatalf("expected acceptance error, got %v",err)};if posts!=0{t.Fatalf("unexpected posts=%d",posts)}
}

func TestContinueReconcilesFailedDirectorWithoutResubmit(t *testing.T){
    workspace,marker:=setupCase(t);ref:=controllerWorkRef{WorkID:"w1",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction"};rb,_:=json.Marshal(ref);_ = os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644)
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){if r.Method!=http.MethodGet{t.Fatal("failed work must not resubmit")};return responseJSON(http.StatusOK,map[string]any{"work_id":"w1","status":"failed","error":"director boom"}),nil})}
    _,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err==nil||!strings.Contains(err.Error(),"director boom"){t.Fatalf("expected durable failure, got %v",err)}
    wb,_:=os.ReadFile(filepath.Join(marker,"case-worklist.json"));var w Worklist;_ = json.Unmarshal(wb,&w);s:=findStep(w.Steps,"0005-010");if s==nil||s.Status!="FAILED"||s.Blocker!="director boom"{t.Fatalf("failed step not persisted %#v",s)}
}

func TestContinueRedispatchesFailedWorkFromOlderRevision(t *testing.T){
    workspace,marker:=setupCase(t)
    wb,err:=os.ReadFile(filepath.Join(marker,"case-worklist.json"));if err!=nil{t.Fatal(err)}
    var w Worklist;if err:=json.Unmarshal(wb,&w);err!=nil{t.Fatal(err)};w.Revision=15
    if err:=persistWorklist(filepath.Join(marker,"case-worklist.json"),w);err!=nil{t.Fatal(err)}
    ref:=controllerWorkRef{WorkID:"case0005-0005-010-r000014-failed",StepID:"0005-010",ActionID:"comfyx-studio.director.preproduction",Revision:14}
    rb,_:=json.Marshal(ref);if err:=os.WriteFile(filepath.Join(marker,"case-controller-last.json"),rb,0o644);err!=nil{t.Fatal(err)}
    posts:=0
    client:=&http.Client{Transport:roundTripFunc(func(r *http.Request)(*http.Response,error){
        if r.Method==http.MethodGet{return responseJSON(http.StatusOK,map[string]any{"work_id":ref.WorkID,"status":"failed","error":"old revision failed"}),nil}
        posts++;var submitted map[string]any;if err:=json.NewDecoder(r.Body).Decode(&submitted);err!=nil{t.Fatal(err)}
        id:=strings.TrimSpace(submitted["work_id"].(string));if !strings.Contains(id,"r000015"){t.Fatalf("expected revision 15 work id, got %s",id)}
        return responseJSON(http.StatusCreated,map[string]any{"work_id":id,"assigned_host":"DESKTOP-ODAQN0D","capability_id":ref.ActionID,"status":"pending","attempts":0}),nil
    })}
    got,err:=Continue(context.Background(),"0005","DESKTOP-ODAQN0D",workspace,"http://127.0.0.1:8848",client);if err!=nil{t.Fatal(err)}
    if posts!=1||got.WorkID==ref.WorkID||got.Revision!=15{t.Fatalf("unexpected redispatch result %#v posts=%d",got,posts)}
    ledger,err:=os.ReadFile(filepath.Join(marker,"case-supervisor-ledger.jsonl"));if err!=nil{t.Fatal(err)}
    if !strings.Contains(string(ledger),"go_failed_controller_work_ref_cleared"){t.Fatalf("missing failed-ref recovery ledger: %s",ledger)}
}
