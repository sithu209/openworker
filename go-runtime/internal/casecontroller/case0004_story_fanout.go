package casecontroller

import (
    "encoding/json"
    "fmt"
    "sort"
    "strings"
)

// buildStoryViewportFanoutPlan expands one manifest fanout step into one
// durable :8848 child per persisted Story Index story. It is deliberately
// independent of Case IDs; the shape is selected by evidence_profile.
func buildStoryViewportFanoutPlan(w Worklist, step *Step, workspaceRoot, machine string) (fanoutPlan, error) {
    if step == nil { return fanoutPlan{}, fmt.Errorf("fanout step is required") }
    if !strings.EqualFold(step.Kind, "fanout") { return fanoutPlan{}, fmt.Errorf("step %s is not fanout", step.StepID) }
    if strings.TrimSpace(step.EvidenceProfile) != "dwg_story_viewports" { return fanoutPlan{}, fmt.Errorf("step %s evidence_profile is not dwg_story_viewports", step.StepID) }
    if len(step.AllowedActions) != 1 || strings.TrimSpace(step.AllowedActions[0]) != "cad.render_story_viewports" {
        return fanoutPlan{}, fmt.Errorf("step %s capability mismatch", step.StepID)
    }
    if len(step.Dependencies) != 1 { return fanoutPlan{}, fmt.Errorf("step %s requires one Story Index dependency", step.StepID) }
    parent := findStep(w.Steps, step.Dependencies[0])
    if parent == nil || !terminalSuccess(parent.Status) { return fanoutPlan{}, fmt.Errorf("Story Index dependency is not terminal-success") }
    rawStories, ok := parent.Evidence["stories"].([]any)
    if !ok || len(rawStories) == 0 { return fanoutPlan{}, fmt.Errorf("Story Index dependency has no stories[] evidence") }

    storyIDs := make([]string,0,len(rawStories)); seen:=map[string]bool{}
    for i, raw := range rawStories {
        m, ok := raw.(map[string]any); if !ok { return fanoutPlan{}, fmt.Errorf("stories[%d] is not an object",i) }
        id := strings.TrimSpace(fmt.Sprint(m["story_id"])); if id == "" { return fanoutPlan{}, fmt.Errorf("stories[%d] missing story_id",i) }
        key:=strings.ToUpper(id); if seen[key] { return fanoutPlan{}, fmt.Errorf("duplicate story_id %s",id) }; seen[key]=true
        storyIDs=append(storyIDs,id)
    }
    sort.Slice(storyIDs,func(i,j int)bool{return strings.ToUpper(storyIDs[i])<strings.ToUpper(storyIDs[j])})

    children:=make([]fanoutChild,0,len(storyIDs))
    for _, storyID := range storyIDs {
        params,err:=json.Marshal(map[string]any{"name":"case0004-story-index","story_ids":[]string{storyID},"width_px":2400,"height_px":1600})
        if err!=nil{return fanoutPlan{},err}
        capability:="dwg.story_index.execute.case-worklist"
        workID:=executionID(w.CaseID,step.StepID+"-"+storyID,capability,w.Revision)
        children=append(children,fanoutChild{
            ParentStepID:step.StepID,
            FanoutRole:"story_viewport",
            EvidencePrefix:"story_render",
            WorkID:workID,
            CapabilityID:capability,
            Inputs:map[string]any{
                "method":"cad.render_story_viewports",
                "params_json":string(params),
                "workspace_root":workspaceRoot,
                "assigned_host":machine,
                "case_step":step.StepID,
                "story_id":storyID,
            },
        })
    }
    return fanoutPlan{Schema:"openworker.dwg-story-fanout-plan/v1",CaseID:w.CaseID,Revision:w.Revision,ParentStepIDs:[]string{step.StepID},Children:children},nil
}
