package actionsqueue

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestThreeStageDeleteOnlyForStuckRun(t *testing.T) {
	now := time.Date(2026, 8, 20, 12, 0, 0, 0, time.UTC)
	lists := 0
	var mutations []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			lists++
			runs := []WorkflowRun{}
			if lists == 1 {
				runs = []WorkflowRun{{ID: 7, Name: "ghost", Status: "queued", CreatedAt: now.Add(-time.Hour)}}
			}
			_ = json.NewEncoder(w).Encode(runsResponse{WorkflowRuns: runs})
			return
		}
		mutations = append(mutations, r.Method+" "+r.URL.Path)
		if strings.HasSuffix(r.URL.Path, "/cancel") || strings.HasSuffix(r.URL.Path, "/force-cancel") {
			http.Error(w, "stuck", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()
	c := Client{Repo: "o/r", BaseURL: srv.URL, HTTP: srv.Client(), Now: func() time.Time { return now }}
	out, err := clearQueue(c, 0, time.Second, time.Millisecond, 30*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"POST /repos/o/r/actions/runs/7/cancel", "POST /repos/o/r/actions/runs/7/force-cancel", "DELETE /repos/o/r/actions/runs/7"}
	if !reflect.DeepEqual(mutations, want) || !reflect.DeepEqual(out.DeletedIDs, []int64{7}) {
		t.Fatalf("mutations=%v out=%+v", mutations, out)
	}
}

func TestClearProcessesRunArrivingDuringPoll(t *testing.T) {
	now := time.Date(2026, 8, 20, 12, 0, 0, 0, time.UTC)
	lists := 0
	var cancelled []int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			lists++
			runs := []WorkflowRun{}
			if lists == 2 {
				runs = []WorkflowRun{{ID: 99, Name: "late", Status: "queued", CreatedAt: now}}
			}
			_ = json.NewEncoder(w).Encode(runsResponse{WorkflowRuns: runs})
			return
		}
		cancelled = append(cancelled, 99)
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()
	c := Client{Repo: "o/r", BaseURL: srv.URL, HTTP: srv.Client(), Now: func() time.Time { return now }}
	out, err := clearQueue(c, 0, time.Second, time.Millisecond, 30*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(cancelled, []int64{99}) {
		t.Fatalf("cancelled=%v", cancelled)
	}
	if out.Outcome != "PASS" || len(out.Operations) != 1 || out.Operations[0].RunID != 99 {
		t.Fatalf("out=%+v", out)
	}
}
