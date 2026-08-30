package casecontroller

import (
    "bytes"
    "context"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "os"
    "path/filepath"
    "strings"
    "time"
)

type ContinueResult struct {
    Schema string `json:"schema"`
    CaseID string `json:"case_id"`
    Machine string `json:"machine"`
    WorkspaceRoot string `json:"workspace_root"`
    Revision int `json:"revision"`
    StepID string `json:"step_id"`
    ActionID string `json:"action_id"`
    WorkID string `json:"work_id"`
    QueueStatus string `json:"queue_status"`
    QueueItem map[string]any `json:"queue_item"`
    Controller string `json:"controller"`
    PythonControllerUsed bool `json:"python_controller_used"`
    ReconciledStepIDs []string `json:"reconciled_step_ids,omitempty"`
    Fanout bool `json:"fanout,omitempty"`
    FanoutStepIDs []string `json:"fanout_step_ids,omitempty"`
    FanoutWorkIDs []string `json:"fanout_work_ids,omitempty"`
    SubmittedAt time.Time `json:"submitted_at"`
}

type controllerWorkRef struct { WorkID string `json:"work_id"`; StepID string `json:"step_id"`; ActionID string `json:"action_id"`; Revision int `json:"revision"` }

func Continue(ctx context.Context, caseID, machine, workspaceRoot, queueURL string, client *http.Client) (ContinueResult, error) {
    if !supportedCaseID(caseID) { return ContinueResult{}, fmt.Errorf("unsupported case %q",caseID) }
    if err:=validateQueueURL(queueURL);err!=nil{return ContinueResult{},err}
    if client==nil{client=&http.Client{Timeout:10*time.Second}}
    marker:=filepath.Join(workspaceRoot,".openworker")
    worklistPath:=filepath.Join(marker,"case-worklist.json")
    specPath:=filepath.Join(marker,"case-spec.json")
    controllerPath:=filepath.Join(marker,"case-controller-last.json")
    fanoutPath:=filepath.Join(marker,"case-fanout-last.json")
    ledgerPath:=filepath.Join(marker,"case-supervisor-ledger.jsonl")

    w,err:=readWorklistSnapshot(worklistPath);if err!=nil{return ContinueResult{},err}
    if w.CaseID!=caseID || !strings.EqualFold(w.AssignedHost,machine) || !samePath(w.WorkspaceRoot,workspaceRoot){return ContinueResult{},fmt.Errorf("case authority mismatch")}

    reconciled:=[]string{}
    if state,ok,readErr:=readFanoutState(fanoutPath);readErr!=nil{return ContinueResult{},readErr}else if ok{
        completed,summary,err:=reconcileFanout(ctx,client,queueURL,workspaceRoot,worklistPath,ledgerPath,&w,state);if err!=nil{return ContinueResult{},err}
        workIDs:=make([]string,0,len(state.Children));for _,child:=range state.Children{workIDs=append(workIDs,child.WorkID)}
        if !completed{
            return ContinueResult{Schema:"openworker.go-case-continue/v3",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:strings.Join(state.ParentStepIDs,","),ActionID:"fanout",QueueStatus:"fanout_active",QueueItem:summary,Controller:"go-native",PythonControllerUsed:false,Fanout:true,FanoutStepIDs:state.ParentStepIDs,FanoutWorkIDs:workIDs},nil
        }
        reconciled=append(reconciled,state.ParentStepIDs...)
        if err:=os.Remove(fanoutPath);err!=nil&&!os.IsNotExist(err){return ContinueResult{},fmt.Errorf("remove completed fanout state: %w",err)}
    }

    if ref,ok:=readControllerWorkRef(controllerPath);ok && strings.TrimSpace(ref.WorkID)!="" {
        item,err:=getQueueWork(ctx,client,queueURL,ref.WorkID)
        if err!=nil{
            if !errors.Is(err,errQueueWorkNotFound){return ContinueResult{},fmt.Errorf("read current durable work %s: %w",ref.WorkID,err)}
            step:=findStep(w.Steps,ref.StepID);if step==nil{return ContinueResult{},fmt.Errorf("stale current work step %s missing from worklist",ref.StepID)}
            terminal:=strings.EqualFold(step.Status,"SUCCEEDED")||strings.EqualFold(step.Status,"PASSED")||strings.EqualFold(step.Status,"COMPLETED")
            if !terminal && !strings.EqualFold(step.Status,"PENDING") && !strings.EqualFold(step.Status,"READY"){
                return ContinueResult{},fmt.Errorf("current durable work %s disappeared while step %s status=%s; explicit repair required",ref.WorkID,ref.StepID,step.Status)
            }
            if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_stale_controller_work_ref_cleared",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:ref.StepID,ActionID:ref.ActionID,WorkID:ref.WorkID,Detail:"durable work no longer exists after queue maintenance; stale controller reference cleared so deterministic dispatch may resume"});err!=nil{return ContinueResult{},err}
            if err:=os.Remove(controllerPath);err!=nil&&!os.IsNotExist(err){return ContinueResult{},fmt.Errorf("clear stale controller work reference: %w",err)}
        } else {
            status:=strings.ToLower(strings.TrimSpace(fmt.Sprint(item["status"])))
            switch status {
            case "pending","claimed","running":
                return existingWorkResult(caseID,machine,workspaceRoot,w.Revision,ref,item),nil
            case "completed":
                step:=findStep(w.Steps,ref.StepID);if step==nil{return ContinueResult{},fmt.Errorf("current work step %s missing from worklist",ref.StepID)}
                if !strings.EqualFold(step.Status,"SUCCEEDED")&&!strings.EqualFold(step.Status,"PASSED")&&!strings.EqualFold(step.Status,"COMPLETED"){
                    evidence,err:=completedEvidence(item);if err!=nil{return ContinueResult{},fmt.Errorf("reconcile %s: %w",ref.StepID,err)}
                    if err:=validateAcceptance(*step,evidence);err!=nil{return ContinueResult{},fmt.Errorf("reconcile %s acceptance: %w",ref.StepID,err)}
                    step.Status="SUCCEEDED";step.Evidence=evidence;step.Blocker=""
                    if err:=persistWorklist(worklistPath,w);err!=nil{return ContinueResult{},err}
                    if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_step_reconciled_completed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:ref.ActionID,WorkID:ref.WorkID,Detail:"durable work completed and acceptance evidence verified"});err!=nil{return ContinueResult{},err}
                    reconciled=append(reconciled,step.StepID)
                }
            case "failed":
                step:=findStep(w.Steps,ref.StepID);if step==nil{return ContinueResult{},fmt.Errorf("current work step %s missing from worklist",ref.StepID)}
                blocker:=strings.TrimSpace(fmt.Sprint(item["error"]));if blocker==""{blocker="durable work failed without error detail"}
                if ref.Revision>0 && w.Revision>ref.Revision{
                    step.Status="PENDING";step.Blocker=""
                    if err:=persistWorklist(worklistPath,w);err!=nil{return ContinueResult{},err}
                    if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_failed_controller_work_ref_cleared",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:ref.ActionID,WorkID:ref.WorkID,Detail:fmt.Sprintf("failed durable work belonged to older revision %d; current revision %d explicitly resets the step for deterministic redispatch",ref.Revision,w.Revision)});err!=nil{return ContinueResult{},err}
                    if err:=os.Remove(controllerPath);err!=nil&&!os.IsNotExist(err){return ContinueResult{},fmt.Errorf("clear failed controller work reference: %w",err)}
                    break
                }
                step.Status="FAILED";step.Blocker=blocker
                if err:=persistWorklist(worklistPath,w);err!=nil{return ContinueResult{},err}
                _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_step_reconciled_failed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:ref.ActionID,WorkID:ref.WorkID,Detail:blocker})
                return ContinueResult{},fmt.Errorf("step %s durable work failed: %s",step.StepID,blocker)
            default:
                return ContinueResult{},fmt.Errorf("current durable work %s has unsupported status %q",ref.WorkID,status)
            }
        }
    }

    ready:=readySteps(w.Steps);if len(ready)==0{return ContinueResult{},fmt.Errorf("no ready steps")}
    if len(ready)>1{
        plan,err:=buildVisualFanoutPlan(w,ready,workspaceRoot,machine);if err!=nil{return ContinueResult{},fmt.Errorf("multiple ready steps are not handled by a registered fanout mapper: %v: %w",ready,err)}
        state,summary,err:=submitFanoutPlan(ctx,client,queueURL,plan);if err!=nil{return ContinueResult{},err}
        if err:=persistFanoutState(fanoutPath,state);err!=nil{return ContinueResult{},err}
        workIDs:=make([]string,0,len(state.Children));for _,child:=range state.Children{workIDs=append(workIDs,child.WorkID)}
        result:=ContinueResult{Schema:"openworker.go-case-continue/v3",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:strings.Join(state.ParentStepIDs,","),ActionID:"fanout",QueueStatus:"fanout_active",QueueItem:summary,Controller:"go-native",PythonControllerUsed:false,ReconciledStepIDs:reconciled,Fanout:true,FanoutStepIDs:state.ParentStepIDs,FanoutWorkIDs:workIDs,SubmittedAt:time.Now().UTC()}
        rb,_:=json.MarshalIndent(result,"","  ");if err:=atomicWrite(controllerPath,append(rb,'\n'));err!=nil{return ContinueResult{},err}
        if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_fanout_durable_accepted",WorkspaceRoot:workspaceRoot,Revision:w.Revision,ReadyStepIDs:state.ParentStepIDs,Detail:fmt.Sprintf("submitted %d deterministic fanout children to durable local-work",len(state.Children))});err!=nil{return ContinueResult{},err}
        return result,nil
    }
    step:=findStep(w.Steps,ready[0]);if step==nil{return ContinueResult{},fmt.Errorf("ready step missing")}
    if strings.EqualFold(step.Kind,"fanout") && strings.TrimSpace(step.EvidenceProfile)=="dwg_story_viewports"{
        plan,err:=buildStoryViewportFanoutPlan(w,step,workspaceRoot,machine);if err!=nil{return ContinueResult{},err}
        state,summary,err:=submitFanoutPlan(ctx,client,queueURL,plan);if err!=nil{return ContinueResult{},err}
        if err:=persistFanoutState(fanoutPath,state);err!=nil{return ContinueResult{},err}
        workIDs:=make([]string,0,len(state.Children));for _,child:=range state.Children{workIDs=append(workIDs,child.WorkID)}
        result:=ContinueResult{Schema:"openworker.go-case-continue/v3",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:"fanout",QueueStatus:"fanout_active",QueueItem:summary,Controller:"go-native",PythonControllerUsed:false,ReconciledStepIDs:reconciled,Fanout:true,FanoutStepIDs:state.ParentStepIDs,FanoutWorkIDs:workIDs,SubmittedAt:time.Now().UTC()}
        rb,_:=json.MarshalIndent(result,"","  ");if err:=atomicWrite(controllerPath,append(rb,'\n'));err!=nil{return ContinueResult{},err}
        if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_fanout_durable_accepted",WorkspaceRoot:workspaceRoot,Revision:w.Revision,ReadyStepIDs:state.ParentStepIDs,Detail:fmt.Sprintf("submitted %d DWG story viewport children to durable local-work",len(state.Children))});err!=nil{return ContinueResult{},err}
        return result,nil
    }
    action,inputs,err:=mapActionInputs(step,w,workspaceRoot,machine,specPath);if err!=nil{return ContinueResult{},err}
    workID:=executionID(caseID,step.StepID,action,w.Revision)
    submit:=map[string]any{"work_id":workID,"assigned_host":machine,"capability_id":action,"inputs":inputs}
    body,_:=json.Marshal(submit)
    if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_step_dispatch_start",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:action,WorkID:workID});err!=nil{return ContinueResult{},err}
    req,err:=http.NewRequestWithContext(ctx,http.MethodPost,strings.TrimRight(queueURL,"/")+"/api/execution/local-work",bytes.NewReader(body));if err!=nil{return ContinueResult{},err};req.Header.Set("Content-Type","application/json")
    resp,err:=client.Do(req);if err!=nil{return ContinueResult{},fmt.Errorf("submit local work: %w",err)};defer resp.Body.Close();raw,err:=io.ReadAll(io.LimitReader(resp.Body,2<<20));if err!=nil{return ContinueResult{},err};if resp.StatusCode/100!=2{return ContinueResult{},fmt.Errorf("local work HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(raw)))}
    var item map[string]any;if err:=json.Unmarshal(raw,&item);err!=nil{return ContinueResult{},fmt.Errorf("decode local work ACK: %w",err)}
    if strings.TrimSpace(fmt.Sprint(item["work_id"]))!=workID || !strings.EqualFold(strings.TrimSpace(fmt.Sprint(item["assigned_host"])),machine){return ContinueResult{},fmt.Errorf("local work ACK identity mismatch")}
    status:=strings.TrimSpace(fmt.Sprint(item["status"]));if status==""{return ContinueResult{},fmt.Errorf("local work ACK missing status")}
    result:=ContinueResult{Schema:"openworker.go-case-continue/v3",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:action,WorkID:workID,QueueStatus:status,QueueItem:item,Controller:"go-native",PythonControllerUsed:false,ReconciledStepIDs:reconciled,SubmittedAt:time.Now().UTC()}
    rb,_:=json.MarshalIndent(result,"","  ");if err:=atomicWrite(controllerPath,append(rb,'\n'));err!=nil{return ContinueResult{},err}
    if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_step_durable_accepted",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:step.StepID,ActionID:action,WorkID:workID,Detail:"go-tool durable local-work accepted with idempotent work_id"});err!=nil{return ContinueResult{},err}
    return result,nil
}

func readWorklistSnapshot(path string)(Worklist,error){b,err:=os.ReadFile(path);if err!=nil{return Worklist{},fmt.Errorf("read worklist snapshot: %w",err)};var w Worklist;if err:=json.Unmarshal(b,&w);err!=nil{return Worklist{},fmt.Errorf("decode worklist snapshot: %w",err)};return w,nil}
func persistWorklist(path string,w Worklist)error{b,err:=json.MarshalIndent(w,"","  ");if err!=nil{return err};return atomicWrite(path,append(b,'\n'))}
func readControllerWorkRef(path string)(controllerWorkRef,bool){b,err:=os.ReadFile(path);if err!=nil{return controllerWorkRef{},false};var ref controllerWorkRef;if json.Unmarshal(b,&ref)!=nil{return controllerWorkRef{},false};return ref,strings.TrimSpace(ref.WorkID)!=""}
var errQueueWorkNotFound=errors.New("durable work not found")
func getQueueWork(ctx context.Context,client *http.Client,queueURL,workID string)(map[string]any,error){u:=strings.TrimRight(queueURL,"/")+"/api/execution/local-work/"+url.PathEscape(workID);req,err:=http.NewRequestWithContext(ctx,http.MethodGet,u,nil);if err!=nil{return nil,err};resp,err:=client.Do(req);if err!=nil{return nil,err};defer resp.Body.Close();raw,err:=io.ReadAll(io.LimitReader(resp.Body,4<<20));if err!=nil{return nil,err};if resp.StatusCode==http.StatusNotFound{return nil,fmt.Errorf("%w: %s",errQueueWorkNotFound,strings.TrimSpace(string(raw)))};if resp.StatusCode!=http.StatusOK{return nil,fmt.Errorf("HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(raw)))};var item map[string]any;if err:=json.Unmarshal(raw,&item);err!=nil{return nil,err};return item,nil}
func existingWorkResult(caseID,machine,workspace string,revision int,ref controllerWorkRef,item map[string]any)ContinueResult{return ContinueResult{Schema:"openworker.go-case-continue/v3",CaseID:caseID,Machine:machine,WorkspaceRoot:workspace,Revision:revision,StepID:ref.StepID,ActionID:ref.ActionID,WorkID:ref.WorkID,QueueStatus:strings.TrimSpace(fmt.Sprint(item["status"])),QueueItem:item,Controller:"go-native",PythonControllerUsed:false}}
func completedEvidence(item map[string]any)(map[string]any,error){raw,ok:=item["result"];if !ok||raw==nil{return nil,fmt.Errorf("completed work missing result")};m,ok:=raw.(map[string]any);if !ok{return nil,fmt.Errorf("completed work result is not an object")};if ev,ok:=m["evidence"].(map[string]any);ok{return ev,nil};return m,nil}
func validateAcceptance(step Step,evidence map[string]any)error{for _,key:=range step.Acceptance{v,ok:=evidence[key];if !ok||v==nil||strings.TrimSpace(fmt.Sprint(v))==""{return fmt.Errorf("missing acceptance evidence %q",key)}};return nil}

func readCaseSpec(path,caseID string)(map[string]any,error){b,err:=os.ReadFile(path);if err!=nil{return nil,fmt.Errorf("read case spec snapshot: %w",err)};var spec map[string]any;if err:=json.Unmarshal(b,&spec);err!=nil{return nil,fmt.Errorf("decode case spec: %w",err)};if strings.TrimSpace(fmt.Sprint(spec["case_id"]))!=caseID{return nil,fmt.Errorf("case spec case_id mismatch")};return spec,nil}
func workspaceRelativeExistingFile(workspaceRoot,raw,label string)(string,error){abs,err:=filepath.Abs(strings.TrimSpace(raw));if err!=nil{return "",err};root,err:=filepath.Abs(workspaceRoot);if err!=nil{return "",err};rel,err:=filepath.Rel(root,abs);if err!=nil{return "",err};if rel==".."||strings.HasPrefix(rel,".."+string(filepath.Separator))||filepath.IsAbs(rel){return "",fmt.Errorf("%s escapes workspace",label)};if st,err:=os.Stat(abs);err!=nil||st.IsDir(){return "",fmt.Errorf("%s missing: %s",label,abs)};return rel,nil}
func executionID(caseID,stepID,action string,revision int)string{sum:=sha256.Sum256([]byte(fmt.Sprintf("%s|%s|%s|%d",caseID,stepID,action,revision)));return fmt.Sprintf("case%s-%s-r%06d-%s",safeID(caseID),safeID(stepID),revision,hex.EncodeToString(sum[:4]))}
func safeID(v string)string{var b strings.Builder;for _,r:=range v{if (r>='a'&&r<='z')||(r>='A'&&r<='Z')||(r>='0'&&r<='9')||r=='-'||r=='_'{b.WriteRune(r)}};return b.String()}
func findStep(steps []Step,id string)*Step{for i:=range steps{if steps[i].StepID==id{return &steps[i]}};return nil}
func validateQueueURL(raw string)error{u,err:=url.Parse(strings.TrimSpace(raw));if err!=nil{return err};h:=strings.ToLower(u.Hostname());if u.Scheme!="http"||(h!="127.0.0.1"&&h!="localhost"&&h!="::1")||u.Port()!="8848"||(u.Path!=""&&u.Path!="/"){return fmt.Errorf("queue URL must be localhost:8848")};return nil}
