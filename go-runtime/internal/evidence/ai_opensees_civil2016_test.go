package evidence

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAIOpenSeesOperatorEvidenceRequiresCivil2016(t *testing.T) {
	valid := AIOpenSeesOperatorEvidence{ActiveSourceCivilVersion: "MIDAS Civil 2016"}
	data, err := json.Marshal(valid)
	if err != nil { t.Fatal(err) }
	var decoded AIOpenSeesOperatorEvidence
	if err := json.Unmarshal(data, &decoded); err != nil { t.Fatalf("Civil 2016 receipt rejected: %v", err) }

	invalid := AIOpenSeesOperatorEvidence{ActiveSourceCivilVersion: "MIDAS Civil 2019"}
	data, err = json.Marshal(invalid)
	if err != nil { t.Fatal(err) }
	if err := json.Unmarshal(data, &decoded); err == nil || !strings.Contains(err.Error(), "not Civil 2016") {
		t.Fatalf("expected non-2016 receipt rejection, got %v", err)
	}

	// Empty stays parseable so the main validator can emit its dedicated
	// ACTIVE_SOURCE_CIVIL_VERSION_EMPTY blocker instead of hiding it here.
	empty := AIOpenSeesOperatorEvidence{}
	data, err = json.Marshal(empty)
	if err != nil { t.Fatal(err) }
	if err := json.Unmarshal(data, &decoded); err != nil { t.Fatalf("empty version should reach main validator: %v", err) }
}
