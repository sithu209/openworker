package evidence

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAIOpenSeesRuntimeRequiresMIDASGUIExport(t *testing.T) {
	base := map[string]any{
		"schema_version": AIOpenSeesRuntimeSchema,
		"active_source_civil_version": "MIDAS Civil 2016",
		"active_source_exported_at": "2026-08-19T12:00:00+08:00",
		"active_source_export_provenance_valid": true,
	}
	base["active_source_export_method"] = "MIDAS Civil GUI Export MCT"
	data, _ := json.Marshal(base)
	var runtime AIOpenSeesRuntimeState
	if err := json.Unmarshal(data, &runtime); err != nil { t.Fatalf("GUI export rejected: %v", err) }

	base["active_source_export_method"] = "MIDAS Civil CLI Export MCT"
	data, _ = json.Marshal(base)
	if err := json.Unmarshal(data, &runtime); err == nil || !strings.Contains(err.Error(), "MIDAS GUI export") {
		t.Fatalf("expected CLI export rejection, got %v", err)
	}

	base["active_source_export_method"] = "MIDAS Civil GUI Export MCT"
	base["active_source_exported_at"] = "not-a-timestamp"
	data, _ = json.Marshal(base)
	if err := json.Unmarshal(data, &runtime); err == nil || !strings.Contains(err.Error(), "not RFC3339") {
		t.Fatalf("expected malformed exported_at rejection, got %v", err)
	}
}
