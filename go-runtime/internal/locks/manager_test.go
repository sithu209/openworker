package locks

import "testing"

func TestExclusiveLock(t *testing.T) {
	m:=New()
	if !m.TryAcquire("job-a",[]string{"workspace:X","gpu:0"}){t.Fatal("job-a should acquire")}
	if m.TryAcquire("job-b",[]string{"gpu:0"}){t.Fatal("job-b must not acquire held gpu lock")}
	if !m.TryAcquire("job-c",[]string{"tool:go"}){t.Fatal("independent lock should acquire")}
	m.Release("job-a")
	if !m.TryAcquire("job-b",[]string{"gpu:0"}){t.Fatal("job-b should acquire after release")}
}

func TestDuplicateNamesAreSafe(t *testing.T){m:=New();if !m.TryAcquire("job-a",[]string{"gpu:0","gpu:0"}){t.Fatal("duplicate lock names should normalize")};m.Release("job-a");if len(m.Snapshot())!=0{t.Fatal("release should clear normalized locks")}}
