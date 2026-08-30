package cluster

import(
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "testing"
 "time"
)

func TestProbeUsesAdvertisedEndpoint(t *testing.T){srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){if r.URL.Path!="/v1/node/status"{http.NotFound(w,r);return};_ = json.NewEncoder(w).Encode(map[string]any{"node_id":"ul7","machine":"DESKTOP-UL7V2VV","advertise_endpoint":"http://ul7-ts:8787","heartbeat_at":time.Now().UTC(),"lease_until":time.Now().UTC().Add(time.Minute),"max_workers":4,"free_workers":4,"inventory":map[string]any{"capabilities":[]string{"bridge"}}})}));defer srv.Close();n,err:=Probe(nil,srv.URL);if err!=nil{t.Fatal(err)};if n.Endpoint!="http://ul7-ts:8787"{t.Fatalf("endpoint=%s",n.Endpoint)}}
