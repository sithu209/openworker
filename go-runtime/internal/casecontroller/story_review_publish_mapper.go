package casecontroller

import (
	"fmt"
	"path/filepath"
	"strings"
)

func init() {
	actionMappers["openworker.review.publish-story-viewports"] = mapStoryViewportReviewPublish
	actionDispatchAliases["openworker.review.publish-story-viewports"] = "openworker.case.publish-artifacts"
}

func singleEvidencePath(raw any, stepID, key string) (string, error) {
	var value string
	switch v := raw.(type) {
	case string:
		value = strings.TrimSpace(v)
	case []string:
		if len(v) != 1 {
			return "", fmt.Errorf("dependency %s evidence %s must contain exactly one path, got %d", stepID, key, len(v))
		}
		value = strings.TrimSpace(v[0])
	case []any:
		if len(v) != 1 {
			return "", fmt.Errorf("dependency %s evidence %s must contain exactly one path, got %d", stepID, key, len(v))
		}
		value = strings.TrimSpace(fmt.Sprint(v[0]))
	default:
		return "", fmt.Errorf("dependency %s evidence %s must be a path or single-path array, got %T", stepID, key, raw)
	}
	if value == "" {
		return "", fmt.Errorf("dependency %s evidence missing %s", stepID, key)
	}
	return value, nil
}

// mapStoryViewportReviewPublish closes the Case review-visibility gap:
// a terminal-success Story viewport fanout is converted into an immutable,
// bounded artifact list and dispatched through the existing
// openworker.case.publish-artifacts capability. That capability publishes the
// exact files to Google Drive and returns chatgpt_review_ready=true.
func mapStoryViewportReviewPublish(ctx actionMapContext) (map[string]any, error) {
	parent, err := dependencyStep(ctx, 0)
	if err != nil {
		return nil, err
	}

	artifacts := make([]string, 0, 16)
	seen := map[string]bool{}
	add := func(raw, key string) error {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			return fmt.Errorf("dependency %s evidence missing %s", parent.StepID, key)
		}
		rel, err := workspaceRelativeExistingFile(ctx.WorkspaceRoot, raw, key)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		canon := strings.ToLower(rel)
		if !seen[canon] {
			seen[canon] = true
			artifacts = append(artifacts, rel)
		}
		return nil
	}

	manifest, err := singleEvidencePath(parent.Evidence["render_manifest"], parent.StepID, "render_manifest")
	if err != nil {
		return nil, err
	}
	if err := add(manifest, "render_manifest"); err != nil {
		return nil, err
	}

	switch values := parent.Evidence["story_pngs"].(type) {
	case []string:
		if len(values) == 0 {
			return nil, fmt.Errorf("dependency %s evidence story_pngs is empty", parent.StepID)
		}
		for _, value := range values {
			if err := add(value, "story_pngs"); err != nil {
				return nil, err
			}
		}
	case []any:
		if len(values) == 0 {
			return nil, fmt.Errorf("dependency %s evidence story_pngs is empty", parent.StepID)
		}
		for _, value := range values {
			if err := add(fmt.Sprint(value), "story_pngs"); err != nil {
				return nil, err
			}
		}
	default:
		return nil, fmt.Errorf("dependency %s evidence story_pngs must be an array", parent.StepID)
	}

	// Include the overview only when a terminal-success step actually carries
	// non-nil overview evidence. Missing optional evidence must not stringify to
	// "<nil>" and accidentally become a filesystem path.
	for i := range ctx.Worklist.Steps {
		step := &ctx.Worklist.Steps[i]
		if !terminalSuccess(step.Status) {
			continue
		}
		value, ok := step.Evidence["overview_png"]
		if !ok || value == nil {
			continue
		}
		raw := strings.TrimSpace(fmt.Sprint(value))
		if raw == "" || raw == "<nil>" {
			continue
		}
		if err := add(raw, "overview_png"); err != nil {
			return nil, err
		}
		break
	}

	revisionID := fmt.Sprintf("case%s-%s-r%06d", safeID(ctx.Worklist.CaseID), safeID(ctx.Step.StepID), ctx.Worklist.Revision)
	workCode := strings.ToUpper(fmt.Sprintf("CASE%s-%s-R%06d", safeID(ctx.Worklist.CaseID), safeID(ctx.Step.StepID), ctx.Worklist.Revision))
	return map[string]any{
		"workspace_root": ctx.WorkspaceRoot,
		"assigned_host":  ctx.Machine,
		"case_id":        ctx.Worklist.CaseID,
		"step_id":        ctx.Step.StepID,
		"revision_id":    revisionID,
		"work_code":      workCode,
		"artifacts":      artifacts,
	}, nil
}
