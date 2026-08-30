package buildinfo

import "testing"

func TestServiceSnapshotVerifiedOnlyOnExactRunningTargetMatch(t *testing.T) {
	oldCommit := Commit
	defer func() { Commit = oldCommit }()
	t.Setenv("OPENWORKER_TARGET_COMMIT", "abc123")

	Commit = "abc123"
	v := ServiceSnapshot()
	if v["upgrade_status"] != "VERIFIED" || v["upgrade_verified"] != true {
		t.Fatalf("expected VERIFIED snapshot, got %#v", v)
	}

	Commit = "def456"
	v = ServiceSnapshot()
	if v["upgrade_status"] != "MISMATCH" || v["upgrade_verified"] != false {
		t.Fatalf("expected MISMATCH snapshot, got %#v", v)
	}
}

func TestServiceSnapshotWithoutTargetIsUntracked(t *testing.T) {
	oldCommit := Commit
	defer func() { Commit = oldCommit }()
	t.Setenv("OPENWORKER_TARGET_COMMIT", "")
	Commit = "abc123"
	v := ServiceSnapshot()
	if v["upgrade_status"] != "UNTRACKED" || v["upgrade_verified"] != false {
		t.Fatalf("expected UNTRACKED snapshot, got %#v", v)
	}
}
