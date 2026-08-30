package cluster

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
    "time"
)

func TestCaseBootstrapForwardsToExactMachineAndRequiresDurableAck(t *testing.T) {
    var seen CaseBootstrapRequest
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodPost || r.URL.Path != "/v1/cases/bootstrap" {
            http.NotFound(w, r)
            return
        }
        if err := json.NewDecoder(r.Body).Decode(&seen); err != nil {
            t.Fatalf("decode forwarded request: %v", err)
        }
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusAccepted)
        _, _ = w.Write([]byte(`{"case_id":"0005","machine":"DESKTOP-ODAQN0D","workspace_created":true,"job":{"job_id":"case0005-bootstrap-1","accepted":true}}`))
    }))
    defer srv.Close()

    c := NewController(nil)
    c.Registry().Upsert(Node{
        NodeID:      "oda",
        Machine:     "DESKTOP-ODAQN0D",
        Endpoint:    srv.URL,
        LeaseUntil:  time.Now().UTC().Add(time.Minute),
        MaxWorkers:  4,
        FreeWorkers: 4,
    })

    res, err := c.CaseBootstrap(CaseBootstrapRequest{
        CaseID:           "0005",
        Machine:          "DESKTOP-ODAQN0D",
        WorkspaceRoot:    `D:\AI-Work\jobs\0005-SNOW-WHITE`,
        OpenWorkerRoot:   `D:\AI\openworker`,
        ControllerModule: "coworker.case0005_controller",
        ManifestPath:     "case-worklists/0005.json",
        SpecPath:         "case-specs/0005.json",
    })
    if err != nil {
        t.Fatal(err)
    }
    if res.Selected.Machine != "DESKTOP-ODAQN0D" || res.Selected.NodeID != "oda" {
        t.Fatalf("wrong selected node: %+v", res.Selected)
    }
    if seen.Machine != "DESKTOP-ODAQN0D" || seen.CaseID != "0005" {
        t.Fatalf("wrong forwarded request: %+v", seen)
    }
    if !strings.Contains(string(res.Response), "case0005-bootstrap-1") {
        t.Fatalf("missing durable ACK: %s", string(res.Response))
    }
}

func TestCaseBootstrapRejectsUnknownMachine(t *testing.T) {
    c := NewController(nil)
    _, err := c.CaseBootstrap(CaseBootstrapRequest{Machine: "DESKTOP-ODAQN0D"})
    if err == nil || !strings.Contains(err.Error(), "no online compatible node") {
        t.Fatalf("expected exact-machine routing failure, got %v", err)
    }
}
