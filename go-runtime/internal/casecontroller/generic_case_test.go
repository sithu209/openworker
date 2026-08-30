package casecontroller

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestGenericCaseBootstrapAcceptsManifestDrivenCaseID(t *testing.T) {
	root := t.TempDir()
	workspace := filepath.Join(root, "job-0099")
	manifest := filepath.Join(root, "0099.json")
	spec := filepath.Join(root, "0099-spec.json")
	w := Worklist{
		SchemaVersion: "openworker-case-worklist/v1",
		CaseID: "0099",
		WorkspaceRoot: workspace,
		AssignedHost: "TEST-HOST",
		Revision: 1,
		Steps: []Step{{StepID:"0099-010",Dependencies:[]string{},AllowedActions:[]string{"comfyx-studio.director.preproduction"},Acceptance:[]string{"director_plan"},Status:"PENDING",Evidence:map[string]any{}}},
	}
	b, _ := json.Marshal(w)
	if err := os.WriteFile(manifest, b, 0644); err != nil { t.Fatal(err) }
	if err := os.WriteFile(spec, []byte(`{"case_id":"0099","title":"Generic Case","source_story":"Once upon a time"}`), 0644); err != nil { t.Fatal(err) }
	got, err := Bootstrap("0099", "TEST-HOST", workspace, manifest, spec)
	if err != nil { t.Fatalf("generic bootstrap failed: %v", err) }
	if got.CaseID != "0099" || got.Controller != "go-native" || got.PythonRequired { t.Fatalf("unexpected bootstrap result: %+v", got) }
	if len(got.ReadyStepIDs) != 1 || got.ReadyStepIDs[0] != "0099-010" { t.Fatalf("unexpected ready steps: %v", got.ReadyStepIDs) }
}

func TestGenericCaseActionMapperUsesCapabilityNotCaseID(t *testing.T) {
	root := t.TempDir()
	spec := filepath.Join(root, "case-spec.json")
	if err := os.WriteFile(spec, []byte(`{"case_id":"0099","title":"Reusable","source_story":"Story"}`), 0644); err != nil { t.Fatal(err) }
	step := Step{StepID:"0099-010",AllowedActions:[]string{"comfyx-studio.director.preproduction"},Status:"PENDING",Evidence:map[string]any{}}
	w := Worklist{CaseID:"0099",WorkspaceRoot:root,AssignedHost:"TEST-HOST",Revision:1,Steps:[]Step{step}}
	action, inputs, err := mapActionInputs(&w.Steps[0], w, root, "TEST-HOST", spec)
	if err != nil { t.Fatalf("generic action map failed: %v", err) }
	if action != "comfyx-studio.director.preproduction" { t.Fatalf("unexpected action %q", action) }
	if inputs["case_id"] != "0099" || inputs["source_title"] != "Reusable" { t.Fatalf("unexpected inputs: %#v", inputs) }
}

func TestGenericActionDispatchAlias(t *testing.T) {
	root:=t.TempDir()
	spec:=filepath.Join(root,"case-spec.json")
	if err:=os.WriteFile(spec,[]byte(`{"case_id":"0099","story_index_build_params":{"source_path":"input/source.dwg"}}`),0644);err!=nil{t.Fatal(err)}
	step:=Step{StepID:"0099-045",AllowedActions:[]string{"cad.build_story_index"},Status:"PENDING",Evidence:map[string]any{}}
	w:=Worklist{CaseID:"0099",WorkspaceRoot:root,AssignedHost:"TEST-HOST",Revision:1,Steps:[]Step{step}}
	action,inputs,err:=mapActionInputs(&w.Steps[0],w,root,"TEST-HOST",spec)
	if err!=nil{t.Fatal(err)}
	if action!="dwg.story_index.execute.case-worklist"{t.Fatalf("unexpected dispatch action %q",action)}
	if inputs["method"]!="cad.build_story_index"{t.Fatalf("unexpected method %#v",inputs)}
}

func TestGenericCaseRejectsUnsafeCaseID(t *testing.T) {
	if supportedCaseID("../0005") { t.Fatal("unsafe case id accepted") }
	if supportedCaseID("0005/evil") { t.Fatal("path-like case id accepted") }
	if !supportedCaseID("CASE-ALPHA_01") { t.Fatal("safe generic case id rejected") }
}
