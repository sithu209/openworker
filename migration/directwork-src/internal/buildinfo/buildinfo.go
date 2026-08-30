package buildinfo

import "time"

var (
	Version = "dev"
	Commit = "unknown"
	TargetCommit = "unknown"
	BuildTime = "unknown"
)

func Snapshot() map[string]any {
	verified := Commit!="" && Commit!="unknown" && TargetCommit!="" && TargetCommit!="unknown" && Commit==TargetCommit
	return map[string]any{"version":Version,"commit":Commit,"target_commit":TargetCommit,"build_time":BuildTime,"upgrade_verified":verified,"reported_at":time.Now().UTC()}
}
