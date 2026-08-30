package casecontroller

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func buildVideoFanoutPlan(w Worklist, step *Step, workspaceRoot, machine string)(fanoutPlan,error){
	if step==nil{return fanoutPlan{},fmt.Errorf("video fanout step is required")}
	if !strings.EqualFold(step.Kind,"fanout")||len(step.AllowedActions)!=1||strings.TrimSpace(step.AllowedActions[0])!="comfyx.production.video.real"{return fanoutPlan{},fmt.Errorf("step %s is not a video fanout contract",step.StepID)}
	var receipts []any
	matches:=0
	for i:=range w.Steps{
		s:=&w.Steps[i];if !terminalSuccess(s.Status){continue}
		if raw,ok:=s.Evidence["shot_image_receipts"];ok&&raw!=nil{
			switch v:=raw.(type){case []any:receipts=v;case []map[string]any:receipts=make([]any,len(v));for j:=range v{receipts[j]=v[j]};default:return fanoutPlan{},fmt.Errorf("shot_image_receipts on %s is not an array",s.StepID)}
			matches++
		}
	}
	if matches!=1||len(receipts)==0{return fanoutPlan{},fmt.Errorf("expected exactly one succeeded shot_image_receipts source, got %d",matches)}
	children:=make([]fanoutChild,0,len(receipts));seen:=map[string]bool{}
	for i,raw:=range receipts{
		receipt,ok:=raw.(map[string]any);if !ok{return fanoutPlan{},fmt.Errorf("shot image receipt %d is not an object",i)}
		data,ok:=receipt["data"].(map[string]any);if !ok{return fanoutPlan{},fmt.Errorf("shot image receipt %d missing data",i)}
		shotID:=strings.TrimSpace(fmt.Sprint(data["asset_id"]));rel:=strings.TrimSpace(fmt.Sprint(data["workspace_relpath"]));if shotID==""||rel==""{return fanoutPlan{},fmt.Errorf("shot image receipt %d missing asset_id/workspace_relpath",i)}
		key:=strings.ToLower(shotID);if seen[key]{return fanoutPlan{},fmt.Errorf("duplicate shot id %q",shotID)};seen[key]=true
		first,err:=boundedExistingWorkspaceRel(workspaceRoot,rel);if err!=nil{return fanoutPlan{},fmt.Errorf("shot %s first frame: %w",shotID,err)}
		name:=safeID(shotID);if name==""{return fanoutPlan{},fmt.Errorf("shot id %q has no safe filename",shotID)}
		output:=filepath.ToSlash(filepath.Join("video","shots",name+".mp4"));action:=strings.TrimSpace(step.AllowedActions[0]);workID:=executionID(w.CaseID,step.StepID+"-"+shotID,action,w.Revision)
		children=append(children,fanoutChild{ParentStepID:step.StepID,FanoutRole:"shot_video",EvidencePrefix:"shot_video",WorkID:workID,CapabilityID:action,Inputs:map[string]any{"workspace_root":workspaceRoot,"assigned_host":machine,"shot_id":shotID,"first_frame_relpath":first,"output_relpath":output}})
	}
	sort.Slice(children,func(i,j int)bool{return strings.Compare(fmt.Sprint(children[i].Inputs["shot_id"]),fmt.Sprint(children[j].Inputs["shot_id"]))<0})
	return fanoutPlan{Schema:"openworker.video-fanout-plan/v1",CaseID:w.CaseID,Revision:w.Revision,ParentStepIDs:[]string{step.StepID},Children:children},nil
}

func boundedExistingWorkspaceRel(root,raw string)(string,error){
	rel:=filepath.Clean(filepath.FromSlash(strings.TrimSpace(raw)));if rel=="."||rel==""||filepath.IsAbs(rel)||rel==".."||strings.HasPrefix(rel,".."+string(filepath.Separator)){return "",fmt.Errorf("workspace-relative path required")}
	rootAbs,err:=filepath.Abs(root);if err!=nil{return "",err};full:=filepath.Join(rootAbs,rel);back,err:=filepath.Rel(rootAbs,full);if err!=nil||back==".."||strings.HasPrefix(back,".."+string(filepath.Separator))||filepath.IsAbs(back){return "",fmt.Errorf("path escapes workspace")}
	st,err:=os.Stat(full);if err!=nil||st.IsDir()||st.Size()<=0{return "",fmt.Errorf("file missing/empty: %s",full)}
	return filepath.ToSlash(back),nil
}

func buildRegisteredFanoutPlan(w Worklist,ready []string,workspaceRoot,machine string)(fanoutPlan,error){
	if len(ready)==0{return fanoutPlan{},fmt.Errorf("no ready steps for fanout")}
	steps:=make([]*Step,0,len(ready));for _,id:=range ready{s:=findStep(w.Steps,id);if s==nil{return fanoutPlan{},fmt.Errorf("ready step %s missing",id)};steps=append(steps,s)}
	allImage:=true;for _,s:=range steps{if !strings.EqualFold(s.Kind,"fanout")||len(s.AllowedActions)!=1||strings.TrimSpace(s.AllowedActions[0])!="image.comfyx.storyboard-real"{allImage=false;break}}
	if allImage{return buildVisualFanoutPlan(w,ready,workspaceRoot,machine)}
	if len(steps)==1&&strings.EqualFold(steps[0].Kind,"fanout")&&len(steps[0].AllowedActions)==1&&strings.TrimSpace(steps[0].AllowedActions[0])=="comfyx.production.video.real"{return buildVideoFanoutPlan(w,steps[0],workspaceRoot,machine)}
	return fanoutPlan{},fmt.Errorf("no registered fanout mapper for ready steps %v",ready)
}
