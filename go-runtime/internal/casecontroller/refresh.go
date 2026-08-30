package casecontroller

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"time"
)

type RefreshResult struct {
	Schema string `json:"schema"`
	CaseID string `json:"case_id"`
	Machine string `json:"machine"`
	WorkspaceRoot string `json:"workspace_root"`
	PreviousRevision int `json:"previous_revision"`
	Revision int `json:"revision"`
	DefinitionChanged bool `json:"definition_changed"`
	UpdatedStepIDs []string `json:"updated_step_ids,omitempty"`
	AddedStepIDs []string `json:"added_step_ids,omitempty"`
	RefreshedAt time.Time `json:"refreshed_at"`
}

func RefreshDefinition(caseID,machine,workspaceRoot,manifestPath,specPath string)(RefreshResult,error){
	caseID=strings.TrimSpace(caseID);if !validCaseID(caseID){return RefreshResult{},fmt.Errorf("invalid case_id %q",caseID)}
	marker:=filepath.Join(workspaceRoot,".openworker");runtimePath:=filepath.Join(marker,"case-worklist.json");runtimeSpecPath:=filepath.Join(marker,"case-spec.json");controllerPath:=filepath.Join(marker,"case-controller-last.json");ledgerPath:=filepath.Join(marker,"case-supervisor-ledger.jsonl")
	current,err:=readWorklistSnapshot(runtimePath);if err!=nil{return RefreshResult{},err}
	if current.CaseID!=caseID||!strings.EqualFold(current.AssignedHost,machine)||!samePath(current.WorkspaceRoot,workspaceRoot){return RefreshResult{},fmt.Errorf("runtime Case authority mismatch")}
	manifestBytes,err:=os.ReadFile(manifestPath);if err!=nil{return RefreshResult{},fmt.Errorf("read source worklist: %w",err)};var desired Worklist;if err:=json.Unmarshal(manifestBytes,&desired);err!=nil{return RefreshResult{},fmt.Errorf("decode source worklist: %w",err)}
	if desired.CaseID!=caseID||!strings.EqualFold(desired.AssignedHost,machine)||!samePath(desired.WorkspaceRoot,workspaceRoot){return RefreshResult{},fmt.Errorf("source Case authority mismatch")};if desired.Revision<current.Revision{return RefreshResult{},fmt.Errorf("definition downgrade forbidden current=%d source=%d",current.Revision,desired.Revision)};if err:=validateGraph(desired.Steps);err!=nil{return RefreshResult{},err}
	specBytes,err:=os.ReadFile(specPath);if err!=nil{return RefreshResult{},fmt.Errorf("read source spec: %w",err)};var spec map[string]any;if err:=json.Unmarshal(specBytes,&spec);err!=nil{return RefreshResult{},fmt.Errorf("decode source spec: %w",err)};if strings.TrimSpace(fmt.Sprint(spec["case_id"]))!=caseID{return RefreshResult{},fmt.Errorf("source spec case_id mismatch")}
	currentSpecBytes,_:=os.ReadFile(runtimeSpecPath);activeStep:="";if ref,ok:=readControllerWorkRef(controllerPath);ok{activeStep=strings.TrimSpace(ref.StepID)}
	currentByID:=map[string]Step{};for _,s:=range current.Steps{currentByID[s.StepID]=s};desiredByID:=map[string]Step{};for _,s:=range desired.Steps{desiredByID[s.StepID]=s};for id:=range currentByID{if _,ok:=desiredByID[id];!ok{return RefreshResult{},fmt.Errorf("definition refresh may not remove existing runtime step %s",id)}}
	changed:=false;updated:=[]string{};added:=[]string{};merged:=make([]Step,0,len(desired.Steps))
	for _,next:=range desired.Steps{
		old,exists:=currentByID[next.StepID]
		if !exists{if !strings.EqualFold(next.Status,"PENDING")&&!strings.EqualFold(next.Status,"READY"){return RefreshResult{},fmt.Errorf("new step %s must start PENDING/READY",next.StepID)};if len(next.Evidence)>0||strings.TrimSpace(next.Blocker)!=""{return RefreshResult{},fmt.Errorf("new step %s may not inject runtime evidence/blocker",next.StepID)};changed=true;added=append(added,next.StepID);merged=append(merged,next);continue}
		structuralChanged:=stepStructureChanged(old,next);protected:=terminalSuccess(old.Status)||strings.EqualFold(activeStep,old.StepID)
		if structuralChanged&&protected{return RefreshResult{},fmt.Errorf("definition refresh may not change protected step %s contract",old.StepID)};if structuralChanged&&desired.Revision<=current.Revision{return RefreshResult{},fmt.Errorf("step %s structural change requires newer revision",old.StepID)};if structuralChanged{changed=true;updated=append(updated,old.StepID)}
		next.Status=old.Status;next.Evidence=old.Evidence;next.Blocker=old.Blocker;merged=append(merged,next)
	}
	if !bytes.Equal(bytes.TrimSpace(currentSpecBytes),bytes.TrimSpace(specBytes)){if desired.Revision<=current.Revision{return RefreshResult{},fmt.Errorf("spec change requires newer revision")};changed=true};if desired.Revision!=current.Revision{changed=true}
	if !changed{return RefreshResult{Schema:"openworker.case-definition-refresh/v1",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,PreviousRevision:current.Revision,Revision:current.Revision,DefinitionChanged:false,RefreshedAt:time.Now().UTC()},nil}
	desired.Steps=merged;body,err:=json.MarshalIndent(desired,"","  ");if err!=nil{return RefreshResult{},err};if err:=atomicWrite(runtimePath,append(body,'\n'));err!=nil{return RefreshResult{},fmt.Errorf("persist refreshed worklist: %w",err)};if err:=atomicWrite(runtimeSpecPath,specBytes);err!=nil{return RefreshResult{},fmt.Errorf("persist refreshed spec: %w",err)}
	result:=RefreshResult{Schema:"openworker.case-definition-refresh/v1",CaseID:caseID,Machine:machine,WorkspaceRoot:workspaceRoot,PreviousRevision:current.Revision,Revision:desired.Revision,DefinitionChanged:true,UpdatedStepIDs:updated,AddedStepIDs:added,RefreshedAt:time.Now().UTC()};detail,_:=json.Marshal(result);if err:=appendLedger(ledgerPath,ledgerEvent{Schema:"openworker.case-supervisor-ledger/v1",Timestamp:time.Now().UTC(),CaseID:caseID,Machine:machine,EventType:"go_definition_refreshed",WorkspaceRoot:workspaceRoot,Revision:desired.Revision,Detail:string(detail)});err!=nil{return RefreshResult{},err};return result,nil
}

func stepStructureChanged(a,b Step)bool{
	return a.Kind!=b.Kind||!reflect.DeepEqual(a.Dependencies,b.Dependencies)||!reflect.DeepEqual(a.AllowedActions,b.AllowedActions)||!reflect.DeepEqual(a.Acceptance,b.Acceptance)||a.FanoutRole!=b.FanoutRole||a.FanoutEvidencePrefix!=b.FanoutEvidencePrefix||a.InputEvidenceKey!=b.InputEvidenceKey||a.OutputRelpath!=b.OutputRelpath||a.EvidenceProfile!=b.EvidenceProfile||!reflect.DeepEqual(a.ArtifactEvidenceKeys,b.ArtifactEvidenceKeys)
}
