package casecontroller

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMapStoryViewportReviewPublishCollectsExactArtifacts(t *testing.T) {
	root := t.TempDir()
	mustWrite := func(rel string) string {
		path := filepath.Join(root, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil { t.Fatal(err) }
		if err := os.WriteFile(path, []byte("x"), 0644); err != nil { t.Fatal(err) }
		return path
	}
	overview := mustWrite("dwg/exports/default/visual-search/overview.png")
	manifest := mustWrite("evidence/story/render-manifest.json")
	png := mustWrite("dwg/exports/default/story/1F.png")
	w := Worklist{CaseID:"0004", Revision:149, Steps:[]Step{
		{StepID:"0004-010", Status:"PASSED", Evidence:map[string]any{}},
		{StepID:"0004-020", Status:"PASSED", Evidence:map[string]any{"overview_png":nil}},
		{StepID:"0004-040", Status:"PASSED", Evidence:map[string]any{"overview_png":overview}},
		{StepID:"0004-0481", Status:"SUCCEEDED", Evidence:map[string]any{"render_manifest":[]any{manifest},"story_pngs":[]any{png}}},
		{StepID:"0004-0485", Status:"READY", Dependencies:[]string{"0004-0481"}, AllowedActions:[]string{"openworker.review.publish-story-viewports"}},
	}}
	step := &w.Steps[4]
	dispatch, inputs, err := mapActionInputs(step, w, root, "DESKTOP-O87PJNR", "")
	if err != nil { t.Fatal(err) }
	if dispatch != "openworker.case.publish-artifacts" { t.Fatalf("dispatch=%s", dispatch) }
	artifacts, ok := inputs["artifacts"].([]string)
	if !ok { t.Fatalf("artifacts type=%T", inputs["artifacts"]) }
	if len(artifacts) != 3 { t.Fatalf("artifacts=%v", artifacts) }
	if inputs["revision_id"] != "case0004-0004-0485-r000149" { t.Fatalf("revision_id=%v", inputs["revision_id"]) }
}

func TestMapStoryViewportReviewPublishRejectsMultipleManifests(t *testing.T) {
	root := t.TempDir()
	manifest1 := filepath.Join(root, "manifest-1.json")
	manifest2 := filepath.Join(root, "manifest-2.json")
	png := filepath.Join(root, "1F.png")
	for _, p := range []string{manifest1, manifest2, png} {
		if err := os.WriteFile(p, []byte("x"), 0644); err != nil { t.Fatal(err) }
	}
	w := Worklist{CaseID:"0004", Revision:149, Steps:[]Step{
		{StepID:"0004-0481", Status:"SUCCEEDED", Evidence:map[string]any{"render_manifest":[]any{manifest1, manifest2},"story_pngs":[]any{png}}},
		{StepID:"0004-0485", Status:"READY", Dependencies:[]string{"0004-0481"}, AllowedActions:[]string{"openworker.review.publish-story-viewports"}},
	}}
	_, _, err := mapActionInputs(&w.Steps[1], w, root, "DESKTOP-O87PJNR", "")
	if err == nil { t.Fatal("expected multiple render_manifest paths to fail closed") }
}

func TestMapStoryViewportReviewPublishRejectsMissingPNGs(t *testing.T) {
	root := t.TempDir()
	manifest := filepath.Join(root, "manifest.json")
	if err := os.WriteFile(manifest, []byte("{}"), 0644); err != nil { t.Fatal(err) }
	w := Worklist{CaseID:"0004", Revision:149, Steps:[]Step{
		{StepID:"0004-0481", Status:"SUCCEEDED", Evidence:map[string]any{"render_manifest":manifest,"story_pngs":[]any{}}},
		{StepID:"0004-0485", Status:"READY", Dependencies:[]string{"0004-0481"}, AllowedActions:[]string{"openworker.review.publish-story-viewports"}},
	}}
	_, _, err := mapActionInputs(&w.Steps[1], w, root, "DESKTOP-O87PJNR", "")
	if err == nil { t.Fatal("expected empty story_pngs to fail closed") }
}
