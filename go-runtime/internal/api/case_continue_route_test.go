package api

import (
    "net/http"
    "net/http/httptest"
    "path/filepath"
    "strings"
    "testing"

    owruntime "github.com/liuxb99/openworker/go-runtime/internal/runtime"
    "github.com/liuxb99/openworker/go-runtime/internal/store"
)

func TestCaseContinueRouteExistsBeforeBootstrap(t *testing.T) {
    root := t.TempDir()
    st, err := store.Open(filepath.Join(root, "node.sqlite3"))
    if err != nil { t.Fatal(err) }
    defer st.Close()

    rt := owruntime.New(st, 1, filepath.Join(root, "logs"), "DESKTOP-ODAQN0D")
    s := New(st, rt, "DESKTOP-ODAQN0D", "http://127.0.0.1:8787")

    req := httptest.NewRequest(http.MethodPost, "/v1/cases/continue", strings.NewReader(`{}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    s.Handler().ServeHTTP(rec, req)

    if rec.Code == http.StatusNotFound {
        t.Fatalf("resident /v1/cases/continue route missing before bootstrap: %s", rec.Body.String())
    }
    if rec.Code != http.StatusBadRequest {
        t.Fatalf("expected bounded input validation 400, got %d body=%s", rec.Code, rec.Body.String())
    }
}
