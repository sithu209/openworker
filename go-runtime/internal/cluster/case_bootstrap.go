package cluster

import (
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net/http"
    "strings"
)

// CaseBootstrapRequest is the cluster-safe form of the local
// /v1/cases/bootstrap contract. Machine is authoritative when forwarding.
type CaseBootstrapRequest struct {
    CaseID           string            `json:"case_id"`
    Machine          string            `json:"machine"`
    WorkspaceRoot    string            `json:"workspace_root"`
    OpenWorkerRoot   string            `json:"openworker_root"`
    ControllerModule string            `json:"controller_module"`
    ManifestPath     string            `json:"manifest_path"`
    SpecPath         string            `json:"spec_path"`
    PythonExe        string            `json:"python_exe,omitempty"`
    Env              map[string]string `json:"env,omitempty"`
}

type CaseBootstrapResult struct {
    Selected Node            `json:"selected"`
    Response json.RawMessage `json:"response"`
}

// CaseBootstrap forwards a bounded case bootstrap request to the exact
// requested machine. The remote node remains the durable scheduling authority.
func (c *Controller) CaseBootstrap(req CaseBootstrapRequest) (CaseBootstrapResult, error) {
    req.Machine = strings.TrimSpace(req.Machine)
    if req.Machine == "" {
        return CaseBootstrapResult{}, errors.New("machine required for cluster case bootstrap")
    }
    n, err := c.registry.Select(req.Machine, nil)
    if err != nil {
        return CaseBootstrapResult{}, err
    }
    req.Machine = n.Machine
    body, err := json.Marshal(req)
    if err != nil {
        return CaseBootstrapResult{}, err
    }
    resp, err := postJSON(c.client, strings.TrimRight(n.Endpoint, "/")+"/v1/cases/bootstrap", body)
    if err != nil {
        return CaseBootstrapResult{}, err
    }
    defer resp.Body.Close()
    raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
    if err != nil {
        return CaseBootstrapResult{}, err
    }
    if resp.StatusCode != http.StatusAccepted {
        return CaseBootstrapResult{}, fmt.Errorf("remote case bootstrap %s: %s %s", n.NodeID, resp.Status, string(raw))
    }
    var ack struct {
        Machine string `json:"machine"`
        Job struct {
            Accepted bool   `json:"accepted"`
            JobID    string `json:"job_id"`
        } `json:"job"`
    }
    if err := json.Unmarshal(raw, &ack); err != nil {
        return CaseBootstrapResult{}, err
    }
    if !strings.EqualFold(ack.Machine, n.Machine) || !ack.Job.Accepted || strings.TrimSpace(ack.Job.JobID) == "" {
        return CaseBootstrapResult{}, errors.New("remote case bootstrap durable ACK mismatch")
    }
    return CaseBootstrapResult{Selected: n, Response: json.RawMessage(raw)}, nil
}
