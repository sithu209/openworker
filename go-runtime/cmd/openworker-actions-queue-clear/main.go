package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/liuxb99/openworker/go-runtime/internal/actionsqueue"
)

func main() {
	repo := flag.String("repo", actionsqueue.DefaultRepository(), "repository owner/name")
	token := flag.String("token", actionsqueue.DefaultToken(), "token with Actions write")
	timeout := flag.Duration("timeout", 7*time.Minute, "verification timeout")
	poll := flag.Duration("poll", 5*time.Second, "verification poll interval")
	stuckAfter := flag.Duration("stuck-after", 30*time.Minute, "minimum age permitting delete after both cancels fail")
	exclude := flag.Int64("exclude-run-id", 0, "run id to preserve")
	runID := flag.String("run-id", os.Getenv("GITHUB_RUN_ID"), "evidence run id")
	sourceSHA := flag.String("source-sha", os.Getenv("GITHUB_SHA"), "evidence source SHA")
	flag.Parse()

	out, err := actionsqueue.Clear(actionsqueue.Options{
		Repository: strings.TrimSpace(*repo), Token: strings.TrimSpace(*token), ExcludeRunID: *exclude,
		Timeout: *timeout, Poll: *poll, StuckAfter: *stuckAfter, RunID: *runID, SourceSHA: *sourceSHA,
	})
	enc := json.NewEncoder(os.Stdout); enc.SetIndent("", "  "); _ = enc.Encode(out)
	if err != nil { fmt.Fprintln(os.Stderr, "OPENWORKER_ACTIONS_QUEUE_CLEAR_FAIL:", err); os.Exit(1) }
}
