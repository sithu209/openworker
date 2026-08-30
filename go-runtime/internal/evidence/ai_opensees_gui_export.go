package evidence

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// UnmarshalJSON makes GUI-export provenance part of the final acceptance
// boundary without trusting the producer's ready/coverage flags alone.
func (s *AIOpenSeesRuntimeState) UnmarshalJSON(data []byte) error {
	type alias AIOpenSeesRuntimeState
	var core alias
	if err := json.Unmarshal(data, &core); err != nil {
		return err
	}
	var provenance struct {
		ActiveSourceExportedAt string `json:"active_source_exported_at"`
		ActiveSourceExportMethod string `json:"active_source_export_method"`
		ActiveSourceExportProvenanceValid bool `json:"active_source_export_provenance_valid"`
	}
	if err := json.Unmarshal(data, &provenance); err != nil {
		return err
	}
	version := strings.TrimSpace(core.ActiveSourceCivilVersion)
	if version == "" || !strings.Contains(strings.ToUpper(version), "2016") {
		return fmt.Errorf("runtime active source Civil version is not Civil 2016: %s", version)
	}
	exportedAt := strings.TrimSpace(provenance.ActiveSourceExportedAt)
	if exportedAt == "" {
		return fmt.Errorf("runtime active source exported_at is empty")
	}
	if _, err := time.Parse(time.RFC3339, exportedAt); err != nil {
		return fmt.Errorf("runtime active source exported_at is not RFC3339: %s", exportedAt)
	}
	method := strings.TrimSpace(provenance.ActiveSourceExportMethod)
	upperMethod := strings.ToUpper(method)
	if method == "" || !strings.Contains(upperMethod, "MIDAS") || !strings.Contains(upperMethod, "GUI") || !strings.Contains(upperMethod, "EXPORT") {
		return fmt.Errorf("runtime active source export_method is not authoritative MIDAS GUI export: %s", method)
	}
	if !provenance.ActiveSourceExportProvenanceValid {
		return fmt.Errorf("runtime active source export provenance is not valid")
	}
	*s = AIOpenSeesRuntimeState(core)
	return nil
}
