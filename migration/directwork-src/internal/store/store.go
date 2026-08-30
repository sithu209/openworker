package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"github.com/liuxb99/DirectWork/internal/model"
)

type snapshot struct {
	NextSeq int64         `json:"next_seq"`
	Works   []model.Work  `json:"works"`
	Events  []model.Event `json:"events"`
}

type Store struct {
	mu      sync.Mutex
	path    string
	nextSeq int64
	works   map[string]model.Work
	events  []model.Event
}

func Open(path string) (*Store, error) {
	if path == "" { return nil, errors.New("store path required") }
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil { return nil, err }
	s := &Store{path: path, nextSeq: 1, works: map[string]model.Work{}}
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) { return s, s.persistLocked() }
	if err != nil { return nil, err }
	if len(b) == 0 { return s, nil }
	var snap snapshot
	if err := json.Unmarshal(b, &snap); err != nil { return nil, fmt.Errorf("decode durable store: %w", err) }
	if snap.NextSeq > 0 { s.nextSeq = snap.NextSeq }
	for _, w := range snap.Works { s.works[w.WorkID] = w }
	s.events = snap.Events
	return s, nil
}

func (s *Store) Close() error { s.mu.Lock(); defer s.mu.Unlock(); return s.persistLocked() }

func (s *Store) persistLocked() error {
	works := make([]model.Work, 0, len(s.works))
	for _, w := range s.works { works = append(works, w) }
	sort.Slice(works, func(i, j int) bool { return works[i].CreatedAt.Before(works[j].CreatedAt) })
	b, err := json.MarshalIndent(snapshot{NextSeq:s.nextSeq, Works:works, Events:s.events}, "", "  ")
	if err != nil { return err }
	tmp := s.path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil { return err }
	if _, err = f.Write(b); err == nil { err = f.Sync() }
	if closeErr := f.Close(); err == nil { err = closeErr }
	if err != nil { _ = os.Remove(tmp); return err }
	if err := atomicReplace(tmp, s.path); err != nil { _ = os.Remove(tmp); return err }
	return nil
}

func (s *Store) addEventLocked(workID, typ, detail string) {
	s.events = append(s.events, model.Event{Seq:s.nextSeq, WorkID:workID, Type:typ, Detail:detail, CreatedAt:time.Now().UTC()})
	s.nextSeq++
}

func (s *Store) Create(w model.Work) error {
	s.mu.Lock(); defer s.mu.Unlock()
	if _, ok := s.works[w.WorkID]; ok { return fmt.Errorf("work already exists: %s", w.WorkID) }
	if w.CreatedAt.IsZero() { w.CreatedAt = time.Now().UTC() }
	if w.Status == "" { w.Status = model.StatusPending }
	if w.TimeoutSec <= 0 { w.TimeoutSec = 3600 }
	s.works[w.WorkID] = w
	s.addEventLocked(w.WorkID, "accepted", "durable work created")
	return s.persistLocked()
}

func (s *Store) Get(id string) (model.Work, error) {
	s.mu.Lock(); defer s.mu.Unlock()
	w, ok := s.works[id]; if !ok { return model.Work{}, os.ErrNotExist }; return w, nil
}

func (s *Store) List(limit int) []model.Work {
	s.mu.Lock(); defer s.mu.Unlock()
	out := make([]model.Work, 0, len(s.works)); for _, w := range s.works { out = append(out, w) }
	sort.Slice(out, func(i,j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	if limit > 0 && len(out) > limit { out = out[:limit] }
	return out
}

func (s *Store) Events(id string) []model.Event {
	s.mu.Lock(); defer s.mu.Unlock(); out:=[]model.Event{}
	for _, e := range s.events { if id=="" || e.WorkID==id { out=append(out,e) } }
	return out
}

func (s *Store) ClaimNext(machine string, slot int) (*model.Work, error) {
	s.mu.Lock(); defer s.mu.Unlock()
	var chosen *model.Work
	for _, w := range s.works {
		if w.Status != model.StatusPending { continue }
		if w.Machine != "" && w.Machine != "any" && w.Machine != machine { continue }
		if chosen == nil || w.CreatedAt.Before(chosen.CreatedAt) { c:=w; chosen=&c }
	}
	if chosen == nil { return nil, nil }
	now:=time.Now().UTC(); chosen.Status=model.StatusClaimed; chosen.Slot=slot; chosen.ClaimedAt=&now
	s.works[chosen.WorkID]=*chosen; s.addEventLocked(chosen.WorkID,"claimed",fmt.Sprintf("slot=%d machine=%s",slot,machine))
	if err:=s.persistLocked(); err!=nil{return nil,err}; return chosen,nil
}

func (s *Store) MarkRunning(id string, pid int, stdoutPath, stderrPath string) error {
	s.mu.Lock(); defer s.mu.Unlock(); w,ok:=s.works[id]; if !ok{return os.ErrNotExist}
	now:=time.Now().UTC(); w.Status=model.StatusRunning; w.PID=pid; w.StdoutPath=stdoutPath; w.StderrPath=stderrPath; w.StartedAt=&now; w.HeartbeatAt=&now
	s.works[id]=w; s.addEventLocked(id,"running",fmt.Sprintf("slot=%d pid=%d",w.Slot,pid)); return s.persistLocked()
}

func (s *Store) Heartbeat(id string) error { s.mu.Lock(); defer s.mu.Unlock(); w,ok:=s.works[id]; if !ok{return os.ErrNotExist}; now:=time.Now().UTC(); w.HeartbeatAt=&now; s.works[id]=w; return s.persistLocked() }

func (s *Store) Finish(id string, status model.Status, exitCode int, detail string) error {
	s.mu.Lock(); defer s.mu.Unlock(); w,ok:=s.works[id]; if !ok{return os.ErrNotExist}
	now:=time.Now().UTC(); w.Status=status; w.ExitCode=exitCode; w.FinishedAt=&now; s.works[id]=w; s.addEventLocked(id,string(status),detail); return s.persistLocked()
}

func (s *Store) Cancel(id string) error { return s.Finish(id, model.StatusCancelled, -1, "cancelled by operator") }

func (s *Store) Retry(id string) error {
	s.mu.Lock(); defer s.mu.Unlock(); w,ok:=s.works[id]; if !ok{return os.ErrNotExist}
	w.Status=model.StatusPending; w.Slot=0; w.PID=0; w.ExitCode=0; w.ClaimedAt=nil; w.StartedAt=nil; w.FinishedAt=nil; w.HeartbeatAt=nil
	s.works[id]=w; s.addEventLocked(id,"retry","returned to durable queue"); return s.persistLocked()
}
