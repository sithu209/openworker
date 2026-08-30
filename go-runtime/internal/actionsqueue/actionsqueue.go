package actionsqueue

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
)

type WorkflowRun struct {
	ID        int64     `json:"id"`
	Name      string    `json:"name"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}
type runsResponse struct {
	WorkflowRuns []WorkflowRun `json:"workflow_runs"`
}
type APIAttempt struct {
	Attempted  bool   `json:"attempted"`
	StatusCode int    `json:"status_code,omitempty"`
	Outcome    string `json:"outcome"`
	Error      string `json:"error,omitempty"`
}
type RunOperation struct {
	RunID           int64      `json:"run_id"`
	Name            string     `json:"name"`
	Status          string     `json:"status"`
	CreatedAt       string     `json:"created_at"`
	Stuck           bool       `json:"stuck"`
	StuckAgeSeconds int64      `json:"stuck_age_seconds"`
	Cancel          APIAttempt `json:"cancel"`
	ForceCancel     APIAttempt `json:"force_cancel"`
	Delete          APIAttempt `json:"delete_stuck_run"`
}
type Result struct {
	SchemaVersion     string         `json:"schema_version"`
	Repository        string         `json:"repository"`
	RunID             string         `json:"run_id,omitempty"`
	SourceSHA         string         `json:"source_sha,omitempty"`
	NonterminalBefore []WorkflowRun  `json:"nonterminal_before"`
	Operations        []RunOperation `json:"operations"`
	CancelledIDs      []int64        `json:"cancelled_ids"`
	DeletedIDs        []int64        `json:"deleted_ids"`
	RemainingAfter    []WorkflowRun  `json:"remaining_after"`
	Outcome           string         `json:"outcome"`
	VerifiedAt        string         `json:"verified_at"`
}
type Client struct {
	Token, Repo, BaseURL string
	HTTP                 *http.Client
	Now                  func() time.Time
}
type Options struct {
	Repository   string
	Token        string
	ExcludeRunID int64
	Timeout      time.Duration
	Poll         time.Duration
	StuckAfter   time.Duration
	RunID        string
	SourceSHA    string
}

func DefaultToken() string {
	return firstNonEmpty(os.Getenv("OPENWORKER_GITHUB_TOKEN"), os.Getenv("GH_TOKEN"), os.Getenv("GITHUB_TOKEN"))
}
func DefaultRepository() string { return strings.TrimSpace(os.Getenv("GITHUB_REPOSITORY")) }

func Clear(opts Options) (Result, error) {
	if strings.TrimSpace(opts.Repository) == "" || !strings.Contains(opts.Repository, "/") {
		return Result{}, errors.New("repository owner/name is required")
	}
	if strings.TrimSpace(opts.Token) == "" {
		return Result{}, errors.New("GitHub token required (OPENWORKER_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN)")
	}
	if opts.Timeout <= 0 {
		opts.Timeout = 7 * time.Minute
	}
	if opts.Poll <= 0 {
		opts.Poll = 5 * time.Second
	}
	if opts.StuckAfter < 0 {
		return Result{}, errors.New("stuck-after must be >= 0")
	}
	if opts.StuckAfter == 0 {
		opts.StuckAfter = 30 * time.Minute
	}
	c := Client{Token: strings.TrimSpace(opts.Token), Repo: strings.TrimSpace(opts.Repository), BaseURL: "https://api.github.com", HTTP: &http.Client{Timeout: 20 * time.Second}, Now: time.Now}
	out, err := clearQueue(c, opts.ExcludeRunID, opts.Timeout, opts.Poll, opts.StuckAfter)
	if err != nil {
		return out, err
	}
	out.RunID = opts.RunID
	out.SourceSHA = opts.SourceSHA
	if out.Outcome != "PASS" {
		return out, fmt.Errorf("GitHub Actions queue still has %d non-terminal run(s)", len(out.RemainingAfter))
	}
	return out, nil
}

func clearQueue(c Client, exclude int64, timeout, poll, stuckAfter time.Duration) (Result, error) {
	before, err := c.nonterminalRuns()
	if err != nil {
		return Result{}, err
	}
	out := Result{SchemaVersion: "openworker.github-actions-queue-clear/v3", Repository: c.Repo, NonterminalBefore: filterRuns(before, exclude)}
	processed := map[int64]bool{}
	process := func(run WorkflowRun) {
		if run.ID == exclude || processed[run.ID] {
			return
		}
		processed[run.ID] = true
		op := RunOperation{RunID: run.ID, Name: run.Name, Status: run.Status, CreatedAt: run.CreatedAt.UTC().Format(time.RFC3339)}
		op.StuckAgeSeconds = int64(c.Now().Sub(run.CreatedAt).Seconds())
		op.Stuck = op.StuckAgeSeconds >= int64(stuckAfter.Seconds())
		op.Cancel = c.mutate(http.MethodPost, fmt.Sprintf("/repos/%s/actions/runs/%d/cancel", c.Repo, run.ID))
		if op.Cancel.Outcome == "success" {
			out.CancelledIDs = append(out.CancelledIDs, run.ID)
		} else {
			op.ForceCancel = c.mutate(http.MethodPost, fmt.Sprintf("/repos/%s/actions/runs/%d/force-cancel", c.Repo, run.ID))
			if op.ForceCancel.Outcome == "success" {
				out.CancelledIDs = append(out.CancelledIDs, run.ID)
			} else if op.Stuck {
				op.Delete = c.mutate(http.MethodDelete, fmt.Sprintf("/repos/%s/actions/runs/%d", c.Repo, run.ID))
				if op.Delete.Outcome == "success" {
					out.DeletedIDs = append(out.DeletedIDs, run.ID)
				}
			} else {
				op.Delete = APIAttempt{Outcome: "not_stuck"}
			}
		}
		out.Operations = append(out.Operations, op)
	}
	for _, run := range out.NonterminalBefore {
		process(run)
	}
	deadline := c.Now().Add(timeout)
	for {
		runs, e := c.nonterminalRuns()
		if e != nil {
			return out, e
		}
		out.RemainingAfter = filterRuns(runs, exclude)
		if len(out.RemainingAfter) == 0 || !c.Now().Before(deadline) {
			break
		}
		for _, run := range out.RemainingAfter {
			process(run)
		}
		time.Sleep(poll)
	}
	sort.Slice(out.CancelledIDs, func(i, j int) bool { return out.CancelledIDs[i] < out.CancelledIDs[j] })
	sort.Slice(out.DeletedIDs, func(i, j int) bool { return out.DeletedIDs[i] < out.DeletedIDs[j] })
	out.Outcome = "PASS"
	if len(out.RemainingAfter) != 0 {
		out.Outcome = "FAIL"
	}
	out.VerifiedAt = c.Now().UTC().Format(time.RFC3339)
	return out, nil
}
func filterRuns(runs []WorkflowRun, exclude int64) []WorkflowRun {
	out := make([]WorkflowRun, 0, len(runs))
	for _, r := range runs {
		if r.ID != exclude {
			out = append(out, r)
		}
	}
	return out
}
func (c Client) nonterminalRuns() ([]WorkflowRun, error) {
	byID := map[int64]WorkflowRun{}
	for _, status := range []string{"queued", "in_progress", "waiting", "requested", "pending"} {
		for page := 1; ; page++ {
			var rr runsResponse
			path := fmt.Sprintf("%s/repos/%s/actions/runs?status=%s&per_page=100&page=%d", c.BaseURL, c.Repo, status, page)
			if err := c.doJSON(http.MethodGet, path, nil, &rr); err != nil {
				return nil, err
			}
			for _, r := range rr.WorkflowRuns {
				if !strings.EqualFold(strings.TrimSpace(r.Status), "completed") {
					byID[r.ID] = r
				}
			}
			if len(rr.WorkflowRuns) < 100 {
				break
			}
		}
	}
	all := make([]WorkflowRun, 0, len(byID))
	for _, r := range byID {
		all = append(all, r)
	}
	sort.Slice(all, func(i, j int) bool { return all[i].ID < all[j].ID })
	return all, nil
}
func (c Client) mutate(method, path string) APIAttempt {
	a := APIAttempt{Attempted: true}
	req, err := http.NewRequest(method, c.BaseURL+path, bytes.NewReader(nil))
	if err != nil {
		a.Outcome = "error"
		a.Error = err.Error()
		return a
	}
	c.headers(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		a.Outcome = "error"
		a.Error = err.Error()
		return a
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	a.StatusCode = resp.StatusCode
	if resp.StatusCode/100 == 2 || resp.StatusCode == http.StatusConflict || resp.StatusCode == http.StatusNotFound {
		a.Outcome = "success"
		return a
	}
	a.Outcome = "failed"
	a.Error = strings.TrimSpace(string(body))
	return a
}
func (c Client) doJSON(method, path string, body io.Reader, out any) error {
	req, err := http.NewRequest(method, path, body)
	if err != nil {
		return err
	}
	c.headers(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("GitHub HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data)))
	}
	if out != nil {
		return json.Unmarshal(data, out)
	}
	return nil
}
func (c Client) headers(req *http.Request) {
	req.Header.Set("Authorization", "Bearer "+c.Token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	req.Header.Set("User-Agent", "OpenWorker-actions-queue-clear")
}
func firstNonEmpty(v ...string) string {
	for _, s := range v {
		if strings.TrimSpace(s) != "" {
			return strings.TrimSpace(s)
		}
	}
	return ""
}
