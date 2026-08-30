package model

import "time"

type Status string

const (
	StatusPending   Status = "pending"
	StatusClaimed   Status = "claimed"
	StatusRunning   Status = "running"
	StatusSucceeded Status = "succeeded"
	StatusFailed    Status = "failed"
	StatusCancelled Status = "cancelled"
	StatusTimedOut  Status = "timed_out"
)

type Work struct {
	WorkID        string            `json:"work_id"`
	DispatchID    string            `json:"dispatch_id,omitempty"`
	CaseID        string            `json:"case_id,omitempty"`
	Project       string            `json:"project,omitempty"`
	Machine       string            `json:"machine,omitempty"`
	Command       string            `json:"command"`
	CWD           string            `json:"cwd"`
	WorkspaceRoot string            `json:"workspace_root,omitempty"`
	TimeoutSec    int               `json:"timeout_sec"`
	Env           map[string]string `json:"env,omitempty"`
	Status        Status            `json:"status"`
	Slot          int               `json:"slot,omitempty"`
	PID           int               `json:"pid,omitempty"`
	ExitCode      int               `json:"exit_code,omitempty"`
	StdoutPath    string            `json:"stdout_path,omitempty"`
	StderrPath    string            `json:"stderr_path,omitempty"`
	CreatedAt     time.Time         `json:"created_at"`
	ClaimedAt     *time.Time        `json:"claimed_at,omitempty"`
	StartedAt     *time.Time        `json:"started_at,omitempty"`
	FinishedAt    *time.Time        `json:"finished_at,omitempty"`
	HeartbeatAt   *time.Time        `json:"heartbeat_at,omitempty"`
}

type Event struct {
	Seq       int64     `json:"seq"`
	WorkID    string    `json:"work_id"`
	Type      string    `json:"type"`
	Detail    string    `json:"detail,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

type CreateWorkRequest struct {
	DispatchID    string            `json:"dispatch_id,omitempty"`
	CaseID        string            `json:"case_id,omitempty"`
	Project       string            `json:"project,omitempty"`
	Machine       string            `json:"machine,omitempty"`
	Command       string            `json:"command"`
	CWD           string            `json:"cwd"`
	WorkspaceRoot string            `json:"workspace_root,omitempty"`
	TimeoutSec    int               `json:"timeout_sec,omitempty"`
	Env           map[string]string `json:"env,omitempty"`
}
