package worktree

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// Manager creates isolated agent checkouts under the same GitHub Actions _work
// root so existing relative-path assumptions remain valid while agents do not
// mutate one working tree concurrently.
type Manager struct {
	RepoRoot string
	AgentsRoot string
}

func New(repoRoot string) *Manager {
	return &Manager{RepoRoot: repoRoot, AgentsRoot: filepath.Join(filepath.Dir(repoRoot), "_agents")}
}

func (m *Manager) Path(slot int) string {
	return filepath.Join(m.AgentsRoot, fmt.Sprintf("A%02d", slot), filepath.Base(m.RepoRoot))
}

// Ensure returns an isolated worktree path. Existing valid directories are
// reused; creation is delegated to git so branch/ref semantics stay canonical.
func (m *Manager) Ensure(slot int, ref string) (string, error) {
	if slot <= 0 { return "", fmt.Errorf("slot must be positive") }
	if ref == "" { ref = "HEAD" }
	path := m.Path(slot)
	if st, err := os.Stat(path); err == nil && st.IsDir() { return path, nil }
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil { return "", err }
	cmd := exec.Command("git", "-C", m.RepoRoot, "worktree", "add", "--detach", path, ref)
	out, err := cmd.CombinedOutput()
	if err != nil { return "", fmt.Errorf("git worktree add: %w: %s", err, string(out)) }
	return path, nil
}
