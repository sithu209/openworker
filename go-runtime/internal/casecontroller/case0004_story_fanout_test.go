package casecontroller

import "testing"

func TestBuildStoryViewportFanoutPlan(t *testing.T){
    w:=Worklist{CaseID:"0004",AssignedHost:"DESKTOP-O87PJNR",Revision:144,Steps:[]Step{
        {StepID:"0004-045",Status:"SUCCEEDED",Evidence:map[string]any{"stories":[]any{
            map[string]any{"story_id":"2F"},map[string]any{"story_id":"1F"},
        }}},
        {StepID:"0004-047",Kind:"fanout",Dependencies:[]string{"0004-045"},AllowedActions:[]string{"cad.render_story_viewports"},EvidenceProfile:"dwg_story_viewports"},
    }}
    step:=findStep(w.Steps,"0004-047")
    plan,err:=buildStoryViewportFanoutPlan(w,step,`D:\AI-Work\jobs\0004-DWG-TO-3D`,`DESKTOP-O87PJNR`);if err!=nil{t.Fatal(err)}
    if len(plan.Children)!=2{t.Fatalf("children=%d",len(plan.Children))}
    for _,c:=range plan.Children{
        if c.CapabilityID!="dwg.story_index.execute.case-worklist"{t.Fatalf("capability=%s",c.CapabilityID)}
        if c.Inputs["method"]!="cad.render_story_viewports"{t.Fatalf("inputs=%#v",c.Inputs)}
    }
}

func TestAggregateDWGStoryFanoutEvidence(t *testing.T){
    evs:=[]map[string]any{
        {"_fanout_work_id":"w1","manifest_path":`D:\m1.json`,"stories":[]any{map[string]any{"png_path":`D:\1F.png`,"png_sha256":"aaa","source_dwg_sha256":"src"}}},
        {"_fanout_work_id":"w2","manifest_path":`D:\m2.json`,"stories":[]any{map[string]any{"png_path":`D:\2F.png`,"png_sha256":"bbb","source_dwg_sha256":"src"}}},
    }
    got,err:=aggregateDWGStoryFanoutEvidence(evs);if err!=nil{t.Fatal(err)}
    if got["source_sha256"]!="src"{t.Fatalf("source=%v",got["source_sha256"])}
    if got["rendered_story_count"]!=2{t.Fatalf("count=%v",got["rendered_story_count"])}
    if got["all_required_stories_terminal_succeeded"]!=true{t.Fatalf("terminal=%v",got["all_required_stories_terminal_succeeded"])}
}
