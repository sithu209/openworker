package casecontroller

import (
    "encoding/json"
    "os"
    "path/filepath"
    "testing"
)

func TestBuildVisualFanoutPlanIsCaseAgnostic(t *testing.T) {
    workspace:=t.TempDir()
    if err:=os.MkdirAll(filepath.Join(workspace,"visual-assets"),0o755);err!=nil{t.Fatal(err)}
    req:=map[string]any{"requirements":[]map[string]any{
        {"asset_id":"char-a","role":"character_master"},
        {"asset_id":"scene-a","role":"scene_concept"},
        {"asset_id":"shot-a","role":"shot_storyboard"},
    }}
    raw,_:=json.Marshal(req)
    if err:=os.WriteFile(filepath.Join(workspace,"visual-assets","requirements.json"),raw,0o644);err!=nil{t.Fatal(err)}
    w:=Worklist{CaseID:"0099",Revision:7,Steps:[]Step{
        {StepID:"0099-030",Kind:"fanout",Status:"PENDING",AllowedActions:[]string{"image.comfyx.storyboard-real"},FanoutRole:"character_master",FanoutEvidencePrefix:"character"},
        {StepID:"0099-040",Kind:"fanout",Status:"PENDING",AllowedActions:[]string{"image.comfyx.storyboard-real"},FanoutRole:"scene_concept",FanoutEvidencePrefix:"scene"},
    }}
    got,err:=buildVisualFanoutPlan(w,[]string{"0099-030","0099-040"},workspace,"TEST-HOST")
    if err!=nil{t.Fatal(err)}
    if got.Schema!="openworker.visual-fanout-plan/v1"||got.CaseID!="0099"||len(got.Children)!=2{t.Fatalf("unexpected plan %#v",got)}
    if got.Children[0].ParentStepID!="0099-030"||got.Children[1].ParentStepID!="0099-040"{t.Fatalf("unexpected parent ordering %#v",got.Children)}
    if got.Children[0].EvidencePrefix!="character"||got.Children[1].EvidencePrefix!="scene"{t.Fatalf("unexpected evidence prefixes %#v",got.Children)}
    for _,child:=range got.Children{
        if child.CapabilityID!="image.comfyx.storyboard-real"{t.Fatalf("unexpected capability %#v",child)}
        if child.WorkID==""{t.Fatal("missing deterministic work_id")}
        if child.Inputs["requirements_relpath"]!="visual-assets/requirements.json"{t.Fatalf("unexpected requirements path %#v",child.Inputs)}
    }
}

func TestBuildVisualFanoutPlanRejectsMissingMetadata(t *testing.T){
    w:=Worklist{CaseID:"0099",Revision:1,Steps:[]Step{
        {StepID:"0099-030",Kind:"fanout",AllowedActions:[]string{"image.comfyx.storyboard-real"}},
        {StepID:"0099-040",Kind:"fanout",AllowedActions:[]string{"image.comfyx.storyboard-real"}},
    }}
    if _,err:=buildVisualFanoutPlan(w,[]string{"0099-030","0099-040"},t.TempDir(),"TEST-HOST");err==nil{t.Fatal("expected metadata failure")}
}
