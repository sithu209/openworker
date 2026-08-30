package main

import(
 "net/http/httptest"
 "testing"
)

func TestToolListIsNarrow(t *testing.T){tools:=toolList();if len(tools)!=4{t.Fatalf("tool count=%d",len(tools))};want:=map[string]bool{"supervisor_status":true,"case_status":true,"case_continue":true,"queue_clear":true};for _,v:=range tools{m,ok:=v.(map[string]any);if !ok{t.Fatal("tool not object")};name,_:=m["name"].(string);if !want[name]{t.Fatalf("unexpected tool %q",name)};delete(want,name)};if len(want)!=0{t.Fatalf("missing tools: %#v",want)}}
func TestBearerAuth(t *testing.T){b:=&bridge{token:"secret"};r:=httptest.NewRequest("POST","http://localhost/mcp",nil);if b.authorized(r){t.Fatal("missing bearer accepted")};r.Header.Set("Authorization","Bearer wrong");if b.authorized(r){t.Fatal("wrong bearer accepted")};r.Header.Set("Authorization","Bearer secret");if !b.authorized(r){t.Fatal("valid bearer rejected")}}
func TestOriginValidation(t *testing.T){for _,origin:=range[]string{"","http://127.0.0.1:8850","http://localhost:8850"}{r:=httptest.NewRequest("POST","http://localhost/mcp",nil);if origin!=""{r.Header.Set("Origin",origin)};if !validOrigin(r){t.Fatalf("local origin rejected: %s",origin)}};r:=httptest.NewRequest("POST","http://localhost/mcp",nil);r.Header.Set("Origin","https://evil.example");if validOrigin(r){t.Fatal("remote origin accepted")}}
func TestProtocolPinnedToCurrentStreamableHTTP(t *testing.T){if supportedProtocol!="2025-06-18"{t.Fatalf("unexpected protocol %s",supportedProtocol)}}
func TestPickAgentPrefersBuild(t *testing.T){v:=[]any{map[string]any{"name":"plan"},map[string]any{"name":"build"}};if got:=pickAgent(v);got!="build"{t.Fatalf("got %q",got)}}
func TestPowerShellQuote(t *testing.T){got:=quotePS(`C:\ProgramData\OpenWorker\bin\openworkerctl.exe`);want:=`& 'C:\ProgramData\OpenWorker\bin\openworkerctl.exe'`;if got!=want{t.Fatalf("got %q want %q",got,want)}}
