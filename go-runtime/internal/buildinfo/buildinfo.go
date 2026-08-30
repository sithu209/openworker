package buildinfo

import (
	"os"
	"strings"
	"time"
)

var (
	Version      = "dev"
	Commit       = "unknown"
	BuildTime    = "unknown"
	TargetCommit = ""
	startedAt    = time.Now().UTC()
)

const SupervisorAPIVersion = "v1"

func Snapshot() map[string]string {
	return map[string]string{
		"version":    Version,
		"commit":     Commit,
		"build_time": BuildTime,
	}
}

func ServiceSnapshot() map[string]any {
	running := strings.TrimSpace(Commit)
	target := strings.TrimSpace(os.Getenv("OPENWORKER_TARGET_COMMIT"))
	if target == "" {
		target = strings.TrimSpace(TargetCommit)
	}
	status := "UNTRACKED"
	verified := false
	if target != "" {
		status = "PENDING"
		if running != "" && !strings.EqualFold(running, "unknown") {
			if strings.EqualFold(running, target) {
				status = "VERIFIED"
				verified = true
			} else {
				status = "MISMATCH"
			}
		}
	}
	return map[string]any{
		"running_commit":         running,
		"target_commit":          target,
		"upgrade_status":         status,
		"upgrade_verified":       verified,
		"service_started_at":     startedAt,
		"supervisor_api_version": SupervisorAPIVersion,
	}
}
