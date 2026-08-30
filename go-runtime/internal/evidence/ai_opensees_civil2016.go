package evidence

import (
	"encoding/json"
	"fmt"
	"strings"
)

// UnmarshalJSON adds an independent production-version gate to the final
// OpenWorker acceptance boundary. Producer-side cohort_valid is necessary but
// not sufficient: any non-empty Civil version must explicitly identify 2016.
func (e *AIOpenSeesOperatorEvidence) UnmarshalJSON(data []byte) error {
	type alias AIOpenSeesOperatorEvidence
	var decoded alias
	if err := json.Unmarshal(data, &decoded); err != nil {
		return err
	}
	version := strings.TrimSpace(decoded.ActiveSourceCivilVersion)
	if version != "" && !strings.Contains(strings.ToUpper(version), "2016") {
		return fmt.Errorf("active source Civil version is not Civil 2016: %s", version)
	}
	*e = AIOpenSeesOperatorEvidence(decoded)
	return nil
}
