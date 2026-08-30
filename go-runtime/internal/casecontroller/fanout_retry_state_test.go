package casecontroller

import (
	"context"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

func TestReconcileFanoutClosesStaleStateOnlyForFailedParent(t *testing.T) {
	workspace := t.TempDir()
	marker := filepath.Join(workspace, ".openworker")
	if err := os.MkdirAll(marker, 0o755); err != nil { t.Fatal(err) }
	fanoutPath := filepath.Join(marker, "case-fanout-last.json")
	worklistPath := filepath.Join(marker, "case-worklist.json")
	ledgerPath := filepath.Join(marker, "case-supervisor-ledger.jsonl")

	state := fanoutState{
		Schema: "openworker.case-fanout-state/v1",
		CaseID: "0004",
		Revision: 147,
		ParentStepIDs: []string{"0004-047"},
		Children: []fanoutChild{{WorkID: "old-failed-child", ParentStepID: "0004-047"}},
	}
	if err := persistFanoutState(fanoutPath, state); err != nil { t.Fatal(err) }
	w := Worklist{
		CaseID: "0004", AssignedHost: "DESKTOP-O87PJNR", WorkspaceRoot: workspace, Revision: 148,
		Steps: []Step{{StepID: "0004-047", Status: "FAILED", Evidence: map[string]any{}, Blocker: "preserved terminal child failure"}},
	}

	completed, summary, err := reconcileFanout(context.Background(), nil, "http://127.0.0.1:8848", workspace, worklistPath, ledgerPath, &w, state)
	if err != nil { t.Fatalf("reconcile stale failed fanout: %v", err) }
	if !completed { t.Fatal("stale terminal-failed fanout should be considered closed") }
	if summary["stale_failed_fanout_closed"] != true { t.Fatalf("missing closure evidence: %#v", summary) }
	if _, err := os.Stat(fanoutPath); !os.IsNotExist(err) { t.Fatalf("fanout state must be removed, stat err=%v", err) }
}

func TestReconcileFanoutKeepsStaleStateWhenParentNotFailed(t *testing.T) {
	workspace := t.TempDir()
	marker := filepath.Join(workspace, ".openworker")
	if err := os.MkdirAll(marker, 0o755); err != nil { t.Fatal(err) }
	fanoutPath := filepath.Join(marker, "case-fanout-last.json")
	state := fanoutState{
		Schema: "openworker.case-fanout-state/v1",
		CaseID: "0004",
		Revision: 147,
		ParentStepIDs: []string{"0004-047"},
		Children: []fanoutChild{{WorkID: "not-proven-failed", ParentStepID: "0004-047"}},
	}
	if err := persistFanoutState(fanoutPath, state); err != nil { t.Fatal(err) }
	w := Worklist{
		CaseID: "0004", AssignedHost: "DESKTOP-O87PJNR", WorkspaceRoot: workspace, Revision: 148,
		Steps: []Step{{StepID: "0004-047", Status: "PENDING", Evidence: map[string]any{}}},
	}

	client:=&http.Client{Transport:roundTripFunc(func(*http.Request)(*http.Response,error){return nil,errors.New("queue unavailable")})}
	completed, _, err := reconcileFanout(context.Background(), client, "http://127.0.0.1:8848", workspace, filepath.Join(marker, "case-worklist.json"), filepath.Join(marker, "ledger.jsonl"), &w, state)
	if err == nil { t.Fatal("stale fanout with non-failed parent must fail closed") }
	if completed { t.Fatal("stale non-failed fanout must not be considered completed") }
	if _, statErr := os.Stat(fanoutPath); statErr != nil { t.Fatalf("fanout state must remain, stat err=%v", statErr) }
}
