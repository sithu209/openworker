package casecontroller

import (
    "os"
    "path/filepath"
    "testing"
)

func TestMapCase0004StoryIndexToLocalSupervisorCapability(t *testing.T){
    root:=t.TempDir();specPath:=filepath.Join(root,"case-spec.json")
    spec:=`{"case_id":"0004","story_index_build_params":{"name":"case0004-story-index","image_width":1200,"image_height":800,"stories":[{"story_id":"1F","pixel_bounds":[101,533,291,666]}]}}`
    if err:=os.WriteFile(specPath,[]byte(spec),0o644);err!=nil{t.Fatal(err)}
    w:=Worklist{CaseID:"0004",WorkspaceRoot:root,AssignedHost:"DESKTOP-O87PJNR",Revision:142}
    step:=Step{StepID:"0004-045",AllowedActions:[]string{"cad.build_story_index"}}
    action,inputs,err:=mapActionInputs(&step,w,root,"DESKTOP-O87PJNR",specPath);if err!=nil{t.Fatal(err)}
    if action!="dwg.story_index.execute.case-worklist"{t.Fatalf("action=%s",action)}
    if inputs["method"]!="cad.build_story_index"||inputs["case_step"]!="0004-045"||inputs["assigned_host"]!="DESKTOP-O87PJNR"{t.Fatalf("inputs=%#v",inputs)}
    if inputs["params_json"]==""{t.Fatal("missing params_json")}
}
