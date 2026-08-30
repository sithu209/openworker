package main

import (
    "bytes"
    "encoding/json"
    "flag"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "os"
    "strings"
    "time"
)

type attempt struct {
    Machine string `json:"machine"`
    Status  int    `json:"status,omitempty"`
    OK      bool   `json:"ok"`
    Error   string `json:"error,omitempty"`
    Body    any    `json:"body,omitempty"`
}

type report struct {
    Schema      string    `json:"schema"`
    Endpoint    string    `json:"endpoint"`
    Mode        string    `json:"mode"`
    Clean       bool      `json:"clean"`
    Selected    string    `json:"selected_machine,omitempty"`
    Attempts    []attempt `json:"attempts"`
    CompletedAt string    `json:"completed_at"`
}

func main() {
    endpoint := flag.String("endpoint", "http://127.0.0.1:8787", "OpenWorker node/cluster API endpoint")
    mode := flag.String("mode", "queued", "queued or all")
    machines := flag.String("machines", "DESKTOP-UL7V2VV,DESKTOP-O87PJNR,DESKTOP-ODAQN0D", "ordered machine failover list")
    flag.Parse()

    if *mode != "queued" && *mode != "all" {
        fail("mode must be queued or all")
    }

    base := strings.TrimRight(strings.TrimSpace(*endpoint), "/")
    ordered := splitMachines(*machines)
    if len(ordered) == 0 {
        fail("at least one machine is required")
    }

    client := &http.Client{Timeout: 15 * time.Second}
    r := report{Schema: "openworker-queue-drain-auto/v1", Endpoint: base, Mode: *mode, Attempts: []attempt{}}

    for _, machine := range ordered {
        a := attempt{Machine: machine}
        u := base + "/v1/cluster/queue/drain?machine=" + url.QueryEscape(machine) + "&mode=" + url.QueryEscape(*mode)
        req, err := http.NewRequest(http.MethodPost, u, bytes.NewReader([]byte(`{}`)))
        if err != nil {
            a.Error = err.Error()
            r.Attempts = append(r.Attempts, a)
            continue
        }
        req.Header.Set("Content-Type", "application/json")
        resp, err := client.Do(req)
        if err != nil {
            a.Error = err.Error()
            r.Attempts = append(r.Attempts, a)
            continue
        }
        a.Status = resp.StatusCode
        raw, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
        resp.Body.Close()
        if readErr != nil {
            a.Error = readErr.Error()
            r.Attempts = append(r.Attempts, a)
            continue
        }
        var body any
        if len(raw) > 0 {
            if err := json.Unmarshal(raw, &body); err != nil {
                body = strings.TrimSpace(string(raw))
            }
        }
        a.Body = body
        if resp.StatusCode/100 != 2 {
            a.Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
            r.Attempts = append(r.Attempts, a)
            continue
        }
        a.OK = true
        r.Attempts = append(r.Attempts, a)
        r.Clean = true
        r.Selected = machine
        r.CompletedAt = time.Now().UTC().Format(time.RFC3339Nano)
        printJSON(r)
        return
    }

    r.CompletedAt = time.Now().UTC().Format(time.RFC3339Nano)
    printJSON(r)
    os.Exit(2)
}

func splitMachines(v string) []string {
    out := []string{}
    seen := map[string]bool{}
    for _, x := range strings.Split(v, ",") {
        x = strings.TrimSpace(x)
        k := strings.ToLower(x)
        if x != "" && !seen[k] {
            seen[k] = true
            out = append(out, x)
        }
    }
    return out
}

func printJSON(v any) {
    enc := json.NewEncoder(os.Stdout)
    enc.SetIndent("", "  ")
    _ = enc.Encode(v)
}

func fail(msg string) {
    fmt.Fprintln(os.Stderr, msg)
    os.Exit(1)
}
