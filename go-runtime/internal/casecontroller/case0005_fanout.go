package casecontroller

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "sort"
    "strings"
)

type visualRequirement struct {
    AssetID string `json:"asset_id"`
    Role string `json:"role"`
}

type visualRequirements struct {
    Requirements []visualRequirement `json:"requirements"`
}

type fanoutChild struct {
    ParentStepID string `json:"parent_step_id"`
    FanoutRole string `json:"fanout_role"`
    EvidencePrefix string `json:"evidence_prefix"`
    WorkID string `json:"work_id"`
    CapabilityID string `json:"capability_id"`
    Inputs map[string]any `json:"inputs"`
}

type fanoutPlan struct {
    Schema string `json:"schema"`
    CaseID string `json:"case_id"`
    Revision int `json:"revision"`
    ParentStepIDs []string `json:"parent_step_ids"`
    Children []fanoutChild `json:"children"`
}

// buildVisualFanoutPlan is manifest-driven. The Case engine does not know any
// Case ID or step ID: each READY fanout step declares fanout_role and
// fanout_evidence_prefix in the worklist. All children target the existing
// durable :8848 queue; this function itself is side-effect free.
func buildVisualFanoutPlan(w Worklist, readyIDs []string, workspaceRoot, machine string) (fanoutPlan, error) {
    if len(readyIDs) < 2 { return fanoutPlan{}, fmt.Errorf("visual fanout requires at least two ready parent steps") }
    roleToStep := map[string]*Step{}
    parentIDs := make([]string,0,len(readyIDs))
    for _, id := range readyIDs {
        step := findStep(w.Steps,id)
        if step == nil { return fanoutPlan{}, fmt.Errorf("fanout step %s missing",id) }
        if !strings.EqualFold(step.Kind,"fanout") { return fanoutPlan{}, fmt.Errorf("ready step %s is not fanout",id) }
        if len(step.AllowedActions)!=1 || strings.TrimSpace(step.AllowedActions[0])!="image.comfyx.storyboard-real" { return fanoutPlan{}, fmt.Errorf("fanout step %s capability mismatch",id) }
        role:=strings.TrimSpace(step.FanoutRole);prefix:=strings.TrimSpace(step.FanoutEvidencePrefix)
        if role==""||prefix=="" { return fanoutPlan{}, fmt.Errorf("fanout step %s missing fanout_role/fanout_evidence_prefix",id) }
        if _,exists:=roleToStep[role];exists { return fanoutPlan{}, fmt.Errorf("duplicate fanout_role %q",role) }
        roleToStep[role]=step;parentIDs=append(parentIDs,id)
    }
    sort.Strings(parentIDs)

    requirementsPath:=filepath.Join(workspaceRoot,"visual-assets","requirements.json")
    raw,err:=os.ReadFile(requirementsPath);if err!=nil{return fanoutPlan{},fmt.Errorf("read visual requirements: %w",err)}
    var reqs visualRequirements
    if err:=json.Unmarshal(raw,&reqs);err!=nil{return fanoutPlan{},fmt.Errorf("decode visual requirements: %w",err)}
    if len(reqs.Requirements)==0{return fanoutPlan{},fmt.Errorf("visual requirements are empty")}

    seen:=map[string]bool{}
    children:=make([]fanoutChild,0,len(reqs.Requirements))
    for _,req:=range reqs.Requirements{
        assetID:=strings.TrimSpace(req.AssetID);role:=strings.TrimSpace(req.Role)
        if assetID==""{return fanoutPlan{},fmt.Errorf("visual requirement contains empty asset_id")}
        key:=strings.ToLower(assetID);if seen[key]{return fanoutPlan{},fmt.Errorf("duplicate visual asset_id %q",assetID)};seen[key]=true
        step,ok:=roleToStep[role];if !ok{continue}
        capability:=strings.TrimSpace(step.AllowedActions[0])
        workID:=executionID(w.CaseID,step.StepID+"-"+assetID,capability,w.Revision)
        children=append(children,fanoutChild{
            ParentStepID:step.StepID,
            FanoutRole:role,
            EvidencePrefix:strings.TrimSpace(step.FanoutEvidencePrefix),
            WorkID:workID,
            CapabilityID:capability,
            Inputs:map[string]any{
                "workspace_root":workspaceRoot,
                "assigned_host":machine,
                "asset_id":assetID,
                "requirements_relpath":filepath.ToSlash(filepath.Join("visual-assets","requirements.json")),
            },
        })
    }
    if len(children)==0{return fanoutPlan{},fmt.Errorf("no visual requirements matched ready fanout roles")}
    for role,step:=range roleToStep{
        found:=false;for _,c:=range children{if c.ParentStepID==step.StepID{found=true;break}}
        if !found{return fanoutPlan{},fmt.Errorf("fanout role %q has no matching child",role)}
    }
    sort.Slice(children,func(i,j int)bool{if children[i].ParentStepID!=children[j].ParentStepID{return children[i].ParentStepID<children[j].ParentStepID};return children[i].WorkID<children[j].WorkID})
    return fanoutPlan{Schema:"openworker.visual-fanout-plan/v1",CaseID:w.CaseID,Revision:w.Revision,ParentStepIDs:parentIDs,Children:children},nil
}
