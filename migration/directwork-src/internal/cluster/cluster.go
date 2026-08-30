package cluster

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"time"
)

type PeerStatus struct {
	Endpoint    string    `json:"endpoint"`
	Machine     string    `json:"machine,omitempty"`
	Online      bool      `json:"online"`
	Version     string    `json:"version,omitempty"`
	Commit      string    `json:"commit,omitempty"`
	BusyWorkers int       `json:"busy_workers,omitempty"`
	MaxWorkers  int       `json:"max_workers,omitempty"`
	LatencyMS   int64     `json:"latency_ms,omitempty"`
	Error       string    `json:"error,omitempty"`
	ObservedAt  time.Time `json:"observed_at"`
}

type Controller struct {
	mu     sync.RWMutex
	peers  []string
	status map[string]PeerStatus
	client *http.Client
}

func New(peers []string) *Controller {
	clean := []string{}
	seen := map[string]bool{}
	for _, p := range peers {
		p = strings.TrimRight(strings.TrimSpace(p), "/")
		if p != "" && !seen[p] { seen[p] = true; clean = append(clean, p) }
	}
	return &Controller{peers: clean, status: map[string]PeerStatus{}, client: &http.Client{Timeout: 2 * time.Second}}
}

func (c *Controller) Start(ctx context.Context) {
	go func() {
		c.probeAll(ctx)
		t := time.NewTicker(5 * time.Second); defer t.Stop()
		for { select { case <-ctx.Done(): return; case <-t.C: c.probeAll(ctx) } }
	}()
}

func (c *Controller) probeAll(ctx context.Context) { for _, p := range c.peers { go c.probe(ctx, p) } }

func (c *Controller) probe(ctx context.Context, p string) {
	start := time.Now(); st := PeerStatus{Endpoint:p, ObservedAt:time.Now().UTC()}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, p+"/v1/node/status", nil)
	if err == nil {
		var resp *http.Response
		resp, err = c.client.Do(req)
		if err == nil {
			defer resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				var v map[string]any
				err = json.NewDecoder(resp.Body).Decode(&v)
				if err == nil {
					st.Online = true
					st.Machine = stringOf(v["machine"])
					st.Version = stringOf(v["version"])
					st.Commit = stringOf(v["commit"])
					st.BusyWorkers = intOf(v["busy_workers"])
					st.MaxWorkers = intOf(v["max_workers"])
				}
			}
		}
	}
	st.LatencyMS = time.Since(start).Milliseconds()
	if err != nil { st.Error = err.Error() }
	c.mu.Lock(); c.status[p] = st; c.mu.Unlock()
}

func (c *Controller) Snapshot() []PeerStatus {
	c.mu.RLock(); defer c.mu.RUnlock()
	out := make([]PeerStatus,0,len(c.peers))
	for _, p := range c.peers { if s,ok:=c.status[p];ok{out=append(out,s)}else{out=append(out,PeerStatus{Endpoint:p,ObservedAt:time.Now().UTC()})} }
	return out
}

func stringOf(v any) string { if s,ok:=v.(string);ok{return s};return "" }
func intOf(v any) int { if f,ok:=v.(float64);ok{return int(f)};return 0 }
