package worktree

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestPathStaysUnderActionWorkRoot(t *testing.T){
	repo:=filepath.Join("D:\\actions-runner\\_work\\openworker","openworker")
	m:=New(repo)
	p:=m.Path(3)
	if !strings.Contains(strings.ToLower(p),strings.ToLower("_agents")){t.Fatalf("missing _agents: %s",p)}
	if !strings.Contains(strings.ToLower(p),strings.ToLower("A03")){t.Fatalf("missing slot: %s",p)}
	if filepath.Base(p)!="openworker"{t.Fatalf("unexpected repo basename: %s",p)}
}
