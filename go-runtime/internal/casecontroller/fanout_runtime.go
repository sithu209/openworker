package casecontroller

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "os"
    "path/filepath"
    "strings"
    "time"
)

type fanoutState struct {
    Schema string `json:"schema"`
    CaseID string `json:"case_id"`
    Revision int `json:"revision"`
    ParentStepIDs []string `json:"parent_step_ids"`
    Children []fanoutChild `json:"children"`
    SubmittedAt time.Time `json:"submitted_at"`
}

func readFanoutState(path string)(fanoutState,bool,error){
    b,err:=os.ReadFile(path);if os.IsNotExist(err){return fanoutState{},false,nil};if err!=nil{return fanoutState{},false,err}
    var s fanoutState;if err:=json.Unmarshal(b,&s);err!=nil{return fanoutState{},false,fmt.Errorf("decode fanout state: %w",err)}
    if strings.TrimSpace(s.CaseID)==""||len(s.Children)==0{return fanoutState{},false,fmt.Errorf("invalid fanout state")}
    return s,true,nil
}

func persistFanoutState(path string,s fanoutState)error{b,err:=json.MarshalIndent(s,"","  ");if err!=nil{return err};return atomicWrite(path,append(b,'\n'))}

func submitFanoutPlan(ctx context.Context,client *http.Client,queueURL string,plan fanoutPlan)(fanoutState,map[string]any,error){
    statuses:=map[string]any{}
    for _,child:=range plan.Children{
        submit:=map[string]any{"work_id":child.WorkID,"assigned_host":child.Inputs["assigned_host"],"capability_id":child.CapabilityID,"inputs":child.Inputs}
        body,_:=json.Marshal(submit)
        req,err:=http.NewRequestWithContext(ctx,http.MethodPost,strings.TrimRight(queueURL,"/")+"/api/execution/local-work",bytes.NewReader(body));if err!=nil{return fanoutState{},nil,err};req.Header.Set("Content-Type","application/json")
        resp,err:=client.Do(req);if err!=nil{return fanoutState{},nil,fmt.Errorf("submit fanout child %s: %w",child.WorkID,err)}
        raw,readErr:=io.ReadAll(io.LimitReader(resp.Body,2<<20));resp.Body.Close();if readErr!=nil{return fanoutState{},nil,readErr}
        if resp.StatusCode/100!=2{return fanoutState{},nil,fmt.Errorf("fanout child %s HTTP %d: %s",child.WorkID,resp.StatusCode,strings.TrimSpace(string(raw)))}
        var item map[string]any;if err:=json.Unmarshal(raw,&item);err!=nil{return fanoutState{},nil,fmt.Errorf("decode child %s ACK: %w",child.WorkID,err)}
        if strings.TrimSpace(fmt.Sprint(item["work_id"]))!=child.WorkID{return fanoutState{},nil,fmt.Errorf("fanout child ACK identity mismatch %s",child.WorkID)}
        statuses[child.WorkID]=item
    }
    return fanoutState{Schema:"openworker.case-fanout-state/v1",CaseID:plan.CaseID,Revision:plan.Revision,ParentStepIDs:plan.ParentStepIDs,Children:plan.Children,SubmittedAt:time.Now().UTC()},statuses,nil
}

func reconcileFanout(ctx context.Context,client *http.Client,queueURL,workspaceRoot,worklistPath,ledgerPath string,w *Worklist,s fanoutState)(bool,map[string]any,error){
    if w==nil{return false,nil,fmt.Errorf("worklist is required")}
    if s.CaseID!=w.CaseID{return false,nil,fmt.Errorf("fanout case authority mismatch")}
    if s.Revision!=w.Revision{
        if s.Revision<w.Revision{
            summary:=map[string]any{}
            allParentsFailed:=len(s.ParentStepIDs)>0
            for _,parentID:=range s.ParentStepIDs{
                parent:=findStep(w.Steps,parentID)
                if parent==nil||!strings.EqualFold(strings.TrimSpace(parent.Status),"FAILED"){allParentsFailed=false;break}
            }
            if !allParentsFailed {
                // The Case definition may advance before the final status poll that
                // reconciles a terminal child. Query the old durable child now. We
                // only promote terminal FAILED into the current runtime; any active,
                // completed-but-unreconciled, unknown, or unreadable state remains
                // fail-closed and the stale fanout file is retained.
                terminalFailedParents:=map[string]string{}
                for _,child:=range s.Children{
                    item,err:=getQueueWork(ctx,client,queueURL,child.WorkID);if err!=nil{return false,summary,fmt.Errorf("read stale fanout child %s: %w",child.WorkID,err)}
                    summary[child.WorkID]=item
                    status:=strings.ToLower(strings.TrimSpace(fmt.Sprint(item["status"])))
                    switch status{
                    case "failed":
                        blocker:=strings.TrimSpace(fmt.Sprint(item["error"]));if blocker==""{blocker="fanout child failed without error detail"}
                        terminalFailedParents[child.ParentStepID]=fmt.Sprintf("child %s: %s",child.WorkID,blocker)
                    case "pending","claimed","running":
                        return false,summary,fmt.Errorf("fanout authority mismatch state_revision=%d worklist_revision=%d; stale child %s still %s",s.Revision,w.Revision,child.WorkID,status)
                    case "completed":
                        return false,summary,fmt.Errorf("fanout authority mismatch state_revision=%d worklist_revision=%d; stale child %s completed but requires same-revision evidence reconciliation",s.Revision,w.Revision,child.WorkID)
                    default:
                        return false,summary,fmt.Errorf("fanout authority mismatch state_revision=%d worklist_revision=%d; stale child %s unsupported status %q",s.Revision,w.Revision,child.WorkID,status)
                    }
                }
                allParentsFailed=len(s.ParentStepIDs)>0
                for _,parentID:=range s.ParentStepIDs{
                    blocker,ok:=terminalFailedParents[parentID]
                    parent:=findStep(w.Steps,parentID)
                    if !ok||parent==nil{allParentsFailed=false;break}
                    parent.Status="FAILED";parent.Blocker=blocker
                    _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:w.CaseID,Machine:w.AssignedHost,EventType:"go_stale_fanout_child_failed_reconciled",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:parentID,Detail:fmt.Sprintf("reconciled terminal failed fanout from revision %d: %s",s.Revision,blocker)})
                }
                if allParentsFailed{if err:=persistWorklist(worklistPath,*w);err!=nil{return false,summary,err}}
            }
            if allParentsFailed{
                fanoutPath:=filepath.Join(workspaceRoot,".openworker","case-fanout-last.json")
                if removeErr:=os.Remove(fanoutPath);removeErr!=nil&&!os.IsNotExist(removeErr){return false,summary,fmt.Errorf("close stale failed fanout state: %w",removeErr)}
                detail:=fmt.Sprintf("closed stale terminal-failed fanout state revision %d after Case definition advanced to revision %d",s.Revision,w.Revision)
                _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:w.CaseID,Machine:w.AssignedHost,EventType:"go_fanout_state_closed_stale_failed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,ReadyStepIDs:s.ParentStepIDs,Detail:detail})
                summary["stale_failed_fanout_closed"]=true;summary["fanout_revision"]=s.Revision;summary["current_revision"]=w.Revision
                return true,summary,nil
            }
        }
        return false,nil,fmt.Errorf("fanout authority mismatch state_revision=%d worklist_revision=%d",s.Revision,w.Revision)
    }
    summary:=map[string]any{}
    allCompleted:=true
    childEvidence:=map[string][]map[string]any{}
    for _,child:=range s.Children{
        item,err:=getQueueWork(ctx,client,queueURL,child.WorkID);if err!=nil{return false,nil,fmt.Errorf("read fanout child %s: %w",child.WorkID,err)}
        summary[child.WorkID]=item
        status:=strings.ToLower(strings.TrimSpace(fmt.Sprint(item["status"])))
        switch status{
        case "pending","claimed","running":allCompleted=false
        case "completed":
            ev,err:=completedEvidence(item);if err!=nil{return false,nil,fmt.Errorf("fanout child %s evidence: %w",child.WorkID,err)}
            ev["_fanout_work_id"]=child.WorkID;ev["_fanout_evidence_prefix"]=child.EvidencePrefix
            childEvidence[child.ParentStepID]=append(childEvidence[child.ParentStepID],ev)
        case "failed":
            parent:=findStep(w.Steps,child.ParentStepID);if parent==nil{return false,nil,fmt.Errorf("fanout parent %s missing",child.ParentStepID)}
            blocker:=strings.TrimSpace(fmt.Sprint(item["error"]));if blocker==""{blocker="fanout child failed without error detail"}
            parent.Status="FAILED";parent.Blocker=fmt.Sprintf("child %s: %s",child.WorkID,blocker)
            if err:=persistWorklist(worklistPath,*w);err!=nil{return false,nil,err}
            _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:w.CaseID,Machine:w.AssignedHost,EventType:"go_fanout_child_failed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:parent.StepID,ActionID:child.CapabilityID,WorkID:child.WorkID,Detail:parent.Blocker})
            fanoutPath:=filepath.Join(workspaceRoot,".openworker","case-fanout-last.json")
            if removeErr:=os.Remove(fanoutPath);removeErr!=nil&&!os.IsNotExist(removeErr){return false,summary,fmt.Errorf("fanout child %s failed and terminal fanout state could not be closed: %v; child error: %s",child.WorkID,removeErr,blocker)}
            _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:w.CaseID,Machine:w.AssignedHost,EventType:"go_fanout_state_closed_failed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:parent.StepID,ActionID:child.CapabilityID,WorkID:child.WorkID,Detail:"terminal child failure preserved; active fanout state closed for explicit retry"})
            return false,summary,fmt.Errorf("fanout child %s failed: %s",child.WorkID,blocker)
        default:return false,summary,fmt.Errorf("fanout child %s unsupported status %q",child.WorkID,status)
        }
    }
    if !allCompleted{return false,summary,nil}

    for _,parentID:=range s.ParentStepIDs{
        parent:=findStep(w.Steps,parentID);if parent==nil{return false,summary,fmt.Errorf("fanout parent %s missing",parentID)}
        evs:=childEvidence[parentID];if len(evs)==0{return false,summary,fmt.Errorf("fanout parent %s has no completed child evidence",parentID)}
        var evidence map[string]any
        var err error
        if strings.TrimSpace(parent.EvidenceProfile)=="dwg_story_viewports"{evidence,err=aggregateDWGStoryFanoutEvidence(evs)}else{evidence,err=aggregateVisualFanoutEvidence(parent,workspaceRoot,evs)}
        if err!=nil{return false,summary,fmt.Errorf("fanout parent %s evidence: %w",parentID,err)}
        if err:=validateAcceptance(*parent,evidence);err!=nil{return false,summary,fmt.Errorf("fanout parent %s acceptance: %w",parentID,err)}
        parent.Status="SUCCEEDED";parent.Evidence=evidence;parent.Blocker=""
        _=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:w.CaseID,Machine:w.AssignedHost,EventType:"go_fanout_parent_reconciled_completed",WorkspaceRoot:workspaceRoot,Revision:w.Revision,StepID:parentID,Detail:fmt.Sprintf("%d durable children completed",len(evs))})
    }
    if err:=persistWorklist(worklistPath,*w);err!=nil{return false,summary,err}
    return true,summary,nil
}

func aggregateVisualFanoutEvidence(parent *Step,workspaceRoot string,evs []map[string]any)(map[string]any,error){
    prefix:=strings.TrimSpace(parent.FanoutEvidencePrefix);if prefix==""{return nil,fmt.Errorf("missing evidence prefix")}
    receipts:=make([]any,0,len(evs));images:=make([]string,0,len(evs));hashes:=make([]string,0,len(evs))
    for _,ev:=range evs{
        receipt,ok:=ev["receipt"].(map[string]any);if !ok{return nil,fmt.Errorf("child receipt missing")}
        data,ok:=receipt["data"].(map[string]any);if !ok{return nil,fmt.Errorf("receipt data missing")}
        rel:=strings.TrimSpace(fmt.Sprint(data["workspace_relpath"]));if rel==""{return nil,fmt.Errorf("workspace_relpath missing")}
        artifact,ok:=data["workspace_artifact"].(map[string]any);if !ok{return nil,fmt.Errorf("workspace_artifact missing")}
        sha:=strings.TrimSpace(fmt.Sprint(artifact["sha256"]));if sha==""{return nil,fmt.Errorf("sha256 missing")}
        receipts=append(receipts,receipt);images=append(images,filepath.Join(workspaceRoot,filepath.FromSlash(rel)));hashes=append(hashes,sha)
    }
    return map[string]any{prefix+"_receipts":receipts,prefix+"_images":images,prefix+"_sha256":hashes},nil
}

func aggregateDWGStoryFanoutEvidence(evs []map[string]any)(map[string]any,error){
    workIDs:=make([]string,0,len(evs));manifests:=make([]string,0,len(evs));pngs:=[]string{};hashes:=[]string{}
    sourceHash:="";rendered:=0
    for _,ev:=range evs{
        workID:=strings.TrimSpace(fmt.Sprint(ev["_fanout_work_id"]));if workID==""{return nil,fmt.Errorf("child work_id missing")};workIDs=append(workIDs,workID)
        manifest:=strings.TrimSpace(fmt.Sprint(ev["manifest_path"]));if manifest==""{return nil,fmt.Errorf("manifest_path missing for %s",workID)};manifests=append(manifests,manifest)
        stories,ok:=ev["stories"].([]any);if !ok||len(stories)==0{return nil,fmt.Errorf("stories evidence missing for %s",workID)}
        for _,raw:=range stories{
            story,ok:=raw.(map[string]any);if !ok{return nil,fmt.Errorf("story evidence is not an object for %s",workID)}
            png:=strings.TrimSpace(fmt.Sprint(story["png_path"]));sha:=strings.TrimSpace(fmt.Sprint(story["png_sha256"]));src:=strings.TrimSpace(fmt.Sprint(story["source_dwg_sha256"]))
            if png==""||sha==""||src==""{return nil,fmt.Errorf("story artifact evidence incomplete for %s",workID)}
            if sourceHash==""{sourceHash=src}else if !strings.EqualFold(sourceHash,src){return nil,fmt.Errorf("source DWG hash mismatch across fanout children")}
            pngs=append(pngs,png);hashes=append(hashes,sha);rendered++
        }
    }
    if rendered==0{return nil,fmt.Errorf("no rendered stories")}
    return map[string]any{"source_sha256":sourceHash,"render_manifest":manifests,"story_job_ids":workIDs,"rendered_story_count":rendered,"story_pngs":pngs,"story_png_sha256s":hashes,"all_required_stories_terminal_succeeded":true},nil
}
