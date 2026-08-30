package casecontroller

import (
    "os"
    "path/filepath"
    "testing"
)

func TestMapStepInputs025UsesBoundedStoryboardRequest(t *testing.T){
    workspace:=t.TempDir()
    request:=filepath.Join(workspace,"presentation","storyboard-request.json")
    if err:=os.MkdirAll(filepath.Dir(request),0o755);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(request,[]byte("{}\n"),0o644);err!=nil{t.Fatal(err)}
    w:=Worklist{CaseID:"0005",WorkspaceRoot:workspace,AssignedHost:"DESKTOP-ODAQN0D",Revision:14,Steps:[]Step{
        {StepID:"0005-020",Status:"SUCCEEDED",Evidence:map[string]any{"storyboard_request":request}},
        {StepID:"0005-025",Dependencies:[]string{"0005-020"},AllowedActions:[]string{"presentation.openmaic"},InputEvidenceKey:"storyboard_request",OutputRelpath:"presentation/storyboard-text-only.pptx",EvidenceProfile:"storyboard-text",Status:"PENDING"},
    }}
    step:=findStep(w.Steps,"0005-025")
    action,inputs,err:=mapActionInputs(step,w,workspace,"DESKTOP-ODAQN0D","")
    if err!=nil{t.Fatal(err)}
    if action!="presentation.openmaic"{t.Fatalf("action=%s",action)}
    if filepath.Clean(inputs["request_relpath"].(string))!=filepath.Clean(filepath.Join("presentation","storyboard-request.json")){t.Fatalf("request_relpath=%v",inputs["request_relpath"])}
    if filepath.Clean(inputs["output_relpath"].(string))!=filepath.Clean(filepath.Join("presentation","storyboard-text-only.pptx")){t.Fatalf("output_relpath=%v",inputs["output_relpath"])}
}

func TestMapStepInputs025RejectsStoryboardRequestOutsideWorkspace(t *testing.T){
    workspace:=t.TempDir();outsideDir:=t.TempDir();outside:=filepath.Join(outsideDir,"request.json")
    if err:=os.WriteFile(outside,[]byte("{}\n"),0o644);err!=nil{t.Fatal(err)}
    w:=Worklist{CaseID:"0005",WorkspaceRoot:workspace,AssignedHost:"DESKTOP-ODAQN0D",Revision:14,Steps:[]Step{
        {StepID:"0005-020",Status:"SUCCEEDED",Evidence:map[string]any{"storyboard_request":outside}},
        {StepID:"0005-025",Dependencies:[]string{"0005-020"},AllowedActions:[]string{"presentation.openmaic"},InputEvidenceKey:"storyboard_request",OutputRelpath:"presentation/storyboard-text-only.pptx",EvidenceProfile:"storyboard-text",Status:"PENDING"},
    }}
    _,_,err:=mapActionInputs(findStep(w.Steps,"0005-025"),w,workspace,"DESKTOP-ODAQN0D","")
    if err==nil{t.Fatal("expected workspace escape rejection")}
}
