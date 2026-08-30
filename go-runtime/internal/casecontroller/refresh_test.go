package casecontroller

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRefreshDefinitionPreservesRuntimeTruthAndCurrentWork(t *testing.T){
	root:=t.TempDir();workspace:=filepath.Join(root,"job");marker:=filepath.Join(workspace,".openworker");if err:=os.MkdirAll(marker,0755);err!=nil{t.Fatal(err)}
	current:=Worklist{SchemaVersion:"openworker-case-worklist/v1",CaseID:"0099",WorkspaceRoot:workspace,AssignedHost:"TEST-HOST",Revision:1,Steps:[]Step{
		{StepID:"0099-010",Kind:"work",Dependencies:[]string{},AllowedActions:[]string{"comfyx-studio.director.preproduction"},Acceptance:[]string{"director_plan"},Status:"PENDING",Evidence:map[string]any{}},
		{StepID:"0099-020",Kind:"work",Dependencies:[]string{"0099-010"},AllowedActions:[]string{"presentation.openmaic"},Acceptance:[]string{"storyboard_pptx"},Status:"PENDING",Evidence:map[string]any{}},
	}}
	writeJSONFile:=func(path string,v any){b,_:=json.Marshal(v);if err:=os.WriteFile(path,b,0644);err!=nil{t.Fatal(err)}}
	writeJSONFile(filepath.Join(marker,"case-worklist.json"),current)
	if err:=os.WriteFile(filepath.Join(marker,"case-spec.json"),[]byte(`{"case_id":"0099","title":"A","source_story":"B"}`),0644);err!=nil{t.Fatal(err)}
	controller:=map[string]any{"work_id":"case0099-0099-010-r000001-aaaa","step_id":"0099-010","action_id":"comfyx-studio.director.preproduction"};writeJSONFile(filepath.Join(marker,"case-controller-last.json"),controller)

	desired:=current;desired.Revision=2;desired.Steps=append([]Step(nil),current.Steps...);desired.Steps[1].InputEvidenceKey="storyboard_request";desired.Steps[1].OutputRelpath="presentation/test.pptx";desired.Steps[1].EvidenceProfile="storyboard-text"
	manifest:=filepath.Join(root,"source.json");writeJSONFile(manifest,desired);spec:=filepath.Join(root,"source-spec.json");if err:=os.WriteFile(spec,[]byte(`{"case_id":"0099","title":"A","source_story":"B"}`),0644);err!=nil{t.Fatal(err)}

	got,err:=RefreshDefinition("0099","TEST-HOST",workspace,manifest,spec);if err!=nil{t.Fatal(err)}
	if !got.DefinitionChanged||got.PreviousRevision!=1||got.Revision!=2{t.Fatalf("unexpected refresh result %+v",got)}
	merged,err:=readWorklistSnapshot(filepath.Join(marker,"case-worklist.json"));if err!=nil{t.Fatal(err)}
	if merged.Steps[0].Status!="PENDING"||merged.Steps[0].AllowedActions[0]!="comfyx-studio.director.preproduction"{t.Fatalf("current work definition changed: %+v",merged.Steps[0])}
	if merged.Steps[1].EvidenceProfile!="storyboard-text"||merged.Steps[1].OutputRelpath!="presentation/test.pptx"{t.Fatalf("future metadata not refreshed: %+v",merged.Steps[1])}
	var ref controllerWorkRef;b,err:=os.ReadFile(filepath.Join(marker,"case-controller-last.json"));if err!=nil{t.Fatal(err)};if err:=json.Unmarshal(b,&ref);err!=nil{t.Fatal(err)};if ref.WorkID!="case0099-0099-010-r000001-aaaa"{t.Fatalf("current work ref lost: %+v",ref)}
}

func TestRefreshDefinitionRejectsCurrentWorkContractChange(t *testing.T){
	root:=t.TempDir();workspace:=filepath.Join(root,"job");marker:=filepath.Join(workspace,".openworker");if err:=os.MkdirAll(marker,0755);err!=nil{t.Fatal(err)}
	current:=Worklist{SchemaVersion:"openworker-case-worklist/v1",CaseID:"0099",WorkspaceRoot:workspace,AssignedHost:"TEST-HOST",Revision:1,Steps:[]Step{{StepID:"0099-010",Kind:"work",Dependencies:[]string{},AllowedActions:[]string{"a"},Acceptance:[]string{"x"},Status:"PENDING",Evidence:map[string]any{}}}}
	b,_:=json.Marshal(current);if err:=os.WriteFile(filepath.Join(marker,"case-worklist.json"),b,0644);err!=nil{t.Fatal(err)};if err:=os.WriteFile(filepath.Join(marker,"case-spec.json"),[]byte(`{"case_id":"0099"}`),0644);err!=nil{t.Fatal(err)}
	ref,_:=json.Marshal(map[string]any{"work_id":"active","step_id":"0099-010","action_id":"a"});if err:=os.WriteFile(filepath.Join(marker,"case-controller-last.json"),ref,0644);err!=nil{t.Fatal(err)}
	desired:=current;desired.Revision=2;desired.Steps=append([]Step(nil),current.Steps...);desired.Steps[0].AllowedActions=[]string{"b"};manifest:=filepath.Join(root,"source.json");db,_:=json.Marshal(desired);if err:=os.WriteFile(manifest,db,0644);err!=nil{t.Fatal(err)};spec:=filepath.Join(root,"source-spec.json");if err:=os.WriteFile(spec,[]byte(`{"case_id":"0099"}`),0644);err!=nil{t.Fatal(err)}
	if _,err:=RefreshDefinition("0099","TEST-HOST",workspace,manifest,spec);err==nil{t.Fatal("expected protected current work contract change to fail")}
}
