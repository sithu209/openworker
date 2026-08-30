package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/liuxb99/openworker/go-runtime/internal/evidence"
)

func main() {
	workspace := flag.String("workspace", "", "AI-OpenSees operator workspace to inspect")
	reportPath := flag.String("report", "", "optional JSON report output path; defaults to <workspace>/openworker-ai-opensees-evidence-report.json")
	flag.Parse()

	if strings.TrimSpace(*workspace) == "" {
		fmt.Fprintln(os.Stderr, "--workspace is required")
		os.Exit(2)
	}

	report := evidence.ValidateAIOpenSeesWorkspace(*workspace)
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal evidence report:", err)
		os.Exit(2)
	}
	data = append(data, '\n')

	output := strings.TrimSpace(*reportPath)
	if output == "" {
		output = filepath.Join(*workspace, "openworker-ai-opensees-evidence-report.json")
	}
	if err := os.WriteFile(output, data, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, "write evidence report:", err)
		os.Exit(2)
	}

	_, _ = os.Stdout.Write(data)
	if !report.Accepted {
		os.Exit(1)
	}
}
