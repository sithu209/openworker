package store_test

import (
 "path/filepath"
 "testing"
 "github.com/liuxb99/openworker/go-runtime/internal/model"
 "github.com/liuxb99/openworker/go-runtime/internal/store"
)

func TestRetryStaleJob(t *testing.T) {
 st, err := store.Open(filepath.Join(t.TempDir(), "node.sqlite3"))
 if err != nil { t.Fatal(err) }
 defer st.Close()
 _, err = st.Submit(model.SubmitRequest{JobID:"OWJ-R", DispatchID:"OWD-R", Machine:"TESTHOST", Command:"echo ok", CWD:t.TempDir()}, "TESTHOST")
 if err != nil { t.Fatal(err) }
 j, err := st.ClaimNext()
 if err != nil || j == nil { t.Fatalf("claim failed: %v", err) }
 if _, err = st.RecoverStale(); err != nil { t.Fatal(err) }
 if err = st.Retry("OWJ-R", "test retry"); err != nil { t.Fatal(err) }
 got, err := st.Get("OWJ-R")
 if err != nil { t.Fatal(err) }
 if got.Status != model.StatusQueued { t.Fatalf("expected queued, got %s", got.Status) }
}
