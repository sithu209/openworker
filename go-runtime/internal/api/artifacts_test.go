package api

import "testing"

func TestArtifactRoleDeliverables(t *testing.T) {
    cases := []struct{ rel, kind string }{
        {"presentation/storyboard-text-only.pptx", "presentation"},
        {"renders/final.mp4", "video"},
        {"deliverables/bridge.dwg", "cad"},
        {"output/calculation.xlsx", "spreadsheet"},
        {"reports/final-report.pdf", "document"},
    }
    for _, tc := range cases {
        role, p := artifactRole(tc.rel, tc.kind)
        if role != "deliverable" || p != 100 { t.Fatalf("%s: got %s/%d", tc.rel, role, p) }
    }
}

func TestArtifactRoleEvidenceAndLogs(t *testing.T) {
    cases := []struct{ rel, kind, role string; priority int }{
        {"evidence/run-receipt.json", "data", "evidence", 300},
        {"reviews/manifest.json", "data", "evidence", 300},
        {"work-ledger/result.json", "data", "evidence", 300},
        {"job.stdout.log", "stdout", "log", 400},
        {"job.stderr.log", "stderr", "log", 400},
    }
    for _, tc := range cases {
        role, p := artifactRole(tc.rel, tc.kind)
        if role != tc.role || p != tc.priority { t.Fatalf("%s: got %s/%d", tc.rel, role, p) }
    }
}

func TestClassifyArtifactRejectsSource(t *testing.T) {
    if _, ok := classifyArtifact("output/generated.py"); ok { t.Fatal("source file must not be exposed as artifact") }
    if kind, ok := classifyArtifact("presentation/final.pptx"); !ok || kind != "presentation" { t.Fatalf("pptx got %q %v", kind, ok) }
}

func TestPathWithin(t *testing.T) {
    if !pathWithin(`C:\work\case0005`, `C:\work\case0005\presentation\a.pptx`) { t.Fatal("child should be allowed") }
    if pathWithin(`C:\work\case0005`, `C:\work\case00050\secret.txt`) { t.Fatal("sibling prefix must not be allowed") }
}
