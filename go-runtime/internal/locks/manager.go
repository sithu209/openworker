package locks

import (
	"sort"
	"sync"
)

// Manager provides process-local exclusive resource locks. Lock names are
// canonical strings such as workspace:D:\AI-Work\jobs\0003, tool:blender,
// gpu:0. Acquire is non-blocking so a worker can return the job to the queue
// instead of occupying a slot while waiting for a resource.
type Manager struct {
	mu    sync.Mutex
	held  map[string]string // lock -> job id
	byJob map[string][]string
}

func New() *Manager {
	return &Manager{held: map[string]string{}, byJob: map[string][]string{}}
}

func normalize(names []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(names))
	for _, n := range names {
		if n == "" { continue }
		if _, ok := seen[n]; ok { continue }
		seen[n] = struct{}{}
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

func (m *Manager) TryAcquire(jobID string, names []string) bool {
	names = normalize(names)
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, n := range names {
		if owner, ok := m.held[n]; ok && owner != jobID { return false }
	}
	for _, n := range names { m.held[n] = jobID }
	m.byJob[jobID] = names
	return true
}

func (m *Manager) Release(jobID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, n := range m.byJob[jobID] {
		if m.held[n] == jobID { delete(m.held, n) }
	}
	delete(m.byJob, jobID)
}

func (m *Manager) Snapshot() map[string]string {
	m.mu.Lock(); defer m.mu.Unlock()
	out := make(map[string]string, len(m.held))
	for k, v := range m.held { out[k] = v }
	return out
}
