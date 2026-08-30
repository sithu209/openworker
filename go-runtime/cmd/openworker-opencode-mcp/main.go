package main

import (
 "bytes"
 "encoding/base64"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "log"
 "net/http"
 "net/url"
 "os"
 "path/filepath"
 "strings"
 "time"
)

const supportedProtocol = "2025-06-18"

type rpcRequest struct{JSONRPC string `json:"jsonrpc"`;ID any `json:"id,omitempty"`;Method string `json:"method"`;Params json.RawMessage `json:"params,omitempty"`}
type rpcResponse struct{JSONRPC string `json:"jsonrpc"`;ID any `json:"id,omitempty"`;Result any `json:"result,omitempty"`;Error *rpcError `json:"error,omitempty"`}
type rpcError struct{Code int `json:"code"`;Message string `json:"message"`;Data any `json:"data,omitempty"`}
type toolCall struct{Name string `json:"name"`;Arguments map[string]any `json:"arguments"`}
type bridge struct{token,openCodeURL,openCodeUser,openCodePass,openWorkerRoot,ctl string;client *http.Client}

func main(){
 listen:=flag.String("listen","127.0.0.1:8850","MCP listen address; localhost only");flag.Parse()
 if !strings.HasPrefix(*listen,"127.0.0.1:")&&!strings.HasPrefix(*listen,"localhost:"){log.Fatal("listen must stay on localhost")}
 b:=&bridge{token:strings.TrimSpace(os.Getenv("OPENWORKER_MCP_TOKEN")),openCodeURL:"http://127.0.0.1:4096",openCodeUser:envOr("OPENCODE_SERVER_USERNAME","opencode"),openCodePass:strings.TrimSpace(os.Getenv("OPENCODE_SERVER_PASSWORD")),openWorkerRoot:discoverRoot(),ctl:filepath.Join(os.Getenv("ProgramData"),"OpenWorker","bin","openworkerctl.exe"),client:&http.Client{Timeout:90*time.Second}}
 if b.token==""{log.Fatal("OPENWORKER_MCP_TOKEN is required")};if b.openCodePass==""{log.Fatal("OPENCODE_SERVER_PASSWORD is required")};if b.openWorkerRoot==""{log.Fatal("OpenWorker root not found")};if st,e:=os.Stat(b.ctl);e!=nil||st.IsDir(){log.Fatalf("openworkerctl missing: %s",b.ctl)}
 mux:=http.NewServeMux();mux.HandleFunc("/health",b.health);mux.HandleFunc("/mcp",b.mcp)
 s:=&http.Server{Addr:*listen,Handler:mux,ReadHeaderTimeout:5*time.Second,ReadTimeout:30*time.Second,WriteTimeout:120*time.Second,IdleTimeout:60*time.Second}
 log.Printf("OpenWorker OpenCode MCP bridge listening on http://%s/mcp",*listen);log.Fatal(s.ListenAndServe())
}
func(b *bridge)health(w http.ResponseWriter,r *http.Request){if r.Method!=http.MethodGet{http.Error(w,"GET only",405);return};writeJSON(w,200,map[string]any{"status":"ok","authority":"openworker-opencode-mcp","transport":"streamable-http-localhost","protocol_version":supportedProtocol,"github_action_used_for_business_execution":false})}
func(b *bridge)mcp(w http.ResponseWriter,r *http.Request){
 if !validOrigin(r){http.Error(w,"forbidden origin",http.StatusForbidden);return}
 if !b.authorized(r){http.Error(w,"unauthorized",http.StatusUnauthorized);return}
 if r.Method==http.MethodGet{w.Header().Set("Allow","POST");http.Error(w,"SSE stream not offered",http.StatusMethodNotAllowed);return}
 if r.Method==http.MethodDelete{w.Header().Set("Allow","POST, GET");http.Error(w,"session termination not stateful",http.StatusMethodNotAllowed);return}
 if r.Method!=http.MethodPost{w.Header().Set("Allow","POST, GET");http.Error(w,"method not allowed",http.StatusMethodNotAllowed);return}
 if accept:=r.Header.Get("Accept");accept!=""&&(!strings.Contains(accept,"application/json")||!strings.Contains(accept,"text/event-stream")){http.Error(w,"Accept must include application/json and text/event-stream",http.StatusNotAcceptable);return}
 var q rpcRequest;if err:=json.NewDecoder(http.MaxBytesReader(w,r.Body,1<<20)).Decode(&q);err!=nil{b.rpcErr(w,nil,-32700,"parse error",err.Error());return};if q.JSONRPC!="2.0"{b.rpcErr(w,q.ID,-32600,"invalid request","jsonrpc must be 2.0");return}
 switch q.Method{
 case "initialize":
  var p struct{ProtocolVersion string `json:"protocolVersion"`};_ = json.Unmarshal(q.Params,&p);if strings.TrimSpace(p.ProtocolVersion)!=""&&p.ProtocolVersion!=supportedProtocol{b.rpcErr(w,q.ID,-32602,"unsupported protocol version",map[string]any{"supported":supportedProtocol,"requested":p.ProtocolVersion});return}
  writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:q.ID,Result:map[string]any{"protocolVersion":supportedProtocol,"capabilities":map[string]any{"tools":map[string]any{"listChanged":false}},"serverInfo":map[string]any{"name":"openworker-opencode-bridge","version":"1.1.0"}}})
 case "notifications/initialized":w.WriteHeader(http.StatusAccepted)
 case "ping":writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:q.ID,Result:map[string]any{}})
 case "tools/list":writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:q.ID,Result:map[string]any{"tools":toolList()}})
 case "tools/call":var tc toolCall;if err:=json.Unmarshal(q.Params,&tc);err!=nil{b.rpcErr(w,q.ID,-32602,"invalid params",err.Error());return};res,err:=b.callTool(tc);if err!=nil{writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:q.ID,Result:map[string]any{"isError":true,"content":[]any{map[string]any{"type":"text","text":err.Error()}}}});return};writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:q.ID,Result:map[string]any{"isError":false,"content":[]any{map[string]any{"type":"text","text":res}}}})
 default:b.rpcErr(w,q.ID,-32601,"method not found",q.Method)
 }}
func toolList()[]any{return []any{
 map[string]any{"name":"supervisor_status","description":"Read ODA local-supervisor OPERATIONAL/REAL_VERIFIED status through OpenCode and openworkerctl.","inputSchema":map[string]any{"type":"object","properties":map[string]any{},"additionalProperties":false},"annotations":map[string]any{"readOnlyHint":true,"destructiveHint":false}},
 map[string]any{"name":"case_status","description":"Read authoritative OpenWorker durable ledger/status for Case 0005.","inputSchema":map[string]any{"type":"object","properties":map[string]any{"case_id":map[string]any{"type":"string","enum":[]string{"0005"}}},"required":[]string{"case_id"},"additionalProperties":false},"annotations":map[string]any{"readOnlyHint":true,"destructiveHint":false}},
 map[string]any{"name":"case_continue","description":"Continue Case 0005 on its fixed ODA local supervisor. This write action never uses GitHub Actions.","inputSchema":map[string]any{"type":"object","properties":map[string]any{"case_id":map[string]any{"type":"string","enum":[]string{"0005"}}},"required":[]string{"case_id"},"additionalProperties":false},"annotations":map[string]any{"readOnlyHint":false,"destructiveHint":false}},
 map[string]any{"name":"queue_clear","description":"One-call clear of the ODA durable local-work queue, then return the clear receipt.","inputSchema":map[string]any{"type":"object","properties":map[string]any{"machine":map[string]any{"type":"string","enum":[]string{"DESKTOP-ODAQN0D"}}},"required":[]string{"machine"},"additionalProperties":false},"annotations":map[string]any{"readOnlyHint":false,"destructiveHint":true}},
}}
func(b *bridge)callTool(tc toolCall)(string,error){var args []string;switch tc.Name{case "supervisor_status":if len(tc.Arguments)!=0{return "",errors.New("supervisor_status takes no arguments")};args=[]string{"supervisor","status"};case "case_status":if fmt.Sprint(tc.Arguments["case_id"])!="0005"{return "",errors.New("only case 0005 is allowed")};args=[]string{"case","status","0005"};case "case_continue":if fmt.Sprint(tc.Arguments["case_id"])!="0005"{return "",errors.New("only case 0005 is allowed")};args=[]string{"case","continue","0005"};case "queue_clear":if !strings.EqualFold(fmt.Sprint(tc.Arguments["machine"]),"DESKTOP-ODAQN0D"){return "",errors.New("only DESKTOP-ODAQN0D is allowed")};args=[]string{"queue","clear","DESKTOP-ODAQN0D"};default:return "",fmt.Errorf("tool %q is not allowlisted",tc.Name)};cmd:=quotePS(b.ctl)+" "+strings.Join(args," ");return b.runViaOpenCode(cmd)}
func(b *bridge)runViaOpenCode(command string)(string,error){if err:=b.openCodeHealth();err!=nil{return "",err};sess,err:=b.openCodeJSON(http.MethodPost,"/session",map[string]any{"title":"OpenWorker remote control"});if err!=nil{return "",err};sid:=strings.TrimSpace(fmt.Sprint(sess["id"]));if sid==""{return "",fmt.Errorf("OpenCode session id missing")};agents,err:=b.openCodeAny(http.MethodGet,"/agent",nil);if err!=nil{return "",err};agent:=pickAgent(agents);if agent==""{return "",fmt.Errorf("OpenCode returned no usable agent")};out,err:=b.openCodeAny(http.MethodPost,"/session/"+sid+"/shell",map[string]any{"agent":agent,"command":command});if err!=nil{return "",err};data,_:=json.Marshal(out);if len(data)>8<<20{return "",fmt.Errorf("OpenCode response too large")};return string(data),nil}
func(b *bridge)openCodeHealth()error{v,err:=b.openCodeJSON(http.MethodGet,"/global/health",nil);if err!=nil{return err};if healthy,ok:=v["healthy"].(bool);!ok||!healthy{return fmt.Errorf("OpenCode server unhealthy")};return nil}
func(b *bridge)openCodeJSON(method,path string,body any)(map[string]any,error){v,e:=b.openCodeAny(method,path,body);if e!=nil{return nil,e};m,ok:=v.(map[string]any);if !ok{return nil,fmt.Errorf("OpenCode response is not object")};return m,nil}
func(b *bridge)openCodeAny(method,path string,body any)(any,error){var rd io.Reader;if body!=nil{raw,e:=json.Marshal(body);if e!=nil{return nil,e};rd=bytes.NewReader(raw)};req,e:=http.NewRequest(method,b.openCodeURL+path,rd);if e!=nil{return nil,e};req.Header.Set("Authorization","Basic "+base64.StdEncoding.EncodeToString([]byte(b.openCodeUser+":"+b.openCodePass)));req.Header.Set("x-opencode-directory",b.openWorkerRoot);if body!=nil{req.Header.Set("Content-Type","application/json")};resp,e:=b.client.Do(req);if e!=nil{return nil,fmt.Errorf("OpenCode request failed: %w",e)};defer resp.Body.Close();raw,e:=io.ReadAll(io.LimitReader(resp.Body,16<<20));if e!=nil{return nil,e};if resp.StatusCode/100!=2{return nil,fmt.Errorf("OpenCode HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(raw)))};if len(raw)==0{return map[string]any{},nil};var v any;if e=json.Unmarshal(raw,&v);e!=nil{return nil,fmt.Errorf("OpenCode invalid JSON: %w",e)};return v,nil}
func pickAgent(v any)string{items,ok:=v.([]any);if !ok{return ""};first:="";for _,it:=range items{m,ok:=it.(map[string]any);if !ok{continue};id:=strings.TrimSpace(fmt.Sprint(m["name"]));if id==""{id=strings.TrimSpace(fmt.Sprint(m["id"]))};if id==""{continue};if first==""{first=id};if strings.EqualFold(id,"build"){return id}};return first}
func validOrigin(r *http.Request)bool{raw:=strings.TrimSpace(r.Header.Get("Origin"));if raw==""{return true};u,e:=url.Parse(raw);if e!=nil{return false};h:=strings.ToLower(u.Hostname());return h=="127.0.0.1"||h=="localhost"||h=="::1"}
func(b *bridge)authorized(r *http.Request)bool{h:=strings.TrimSpace(r.Header.Get("Authorization"));return h=="Bearer "+b.token}
func(b *bridge)rpcErr(w http.ResponseWriter,id any,code int,msg string,data any){writeJSON(w,200,rpcResponse{JSONRPC:"2.0",ID:id,Error:&rpcError{Code:code,Message:msg,Data:data}})}
func writeJSON(w http.ResponseWriter,status int,v any){w.Header().Set("Content-Type","application/json");w.WriteHeader(status);_ = json.NewEncoder(w).Encode(v)}
func quotePS(s string)string{return "& '"+strings.ReplaceAll(s,"'","''")+"'"}
func envOr(k,d string)string{if v:=strings.TrimSpace(os.Getenv(k));v!=""{return v};return d}
func discoverRoot()string{if v:=strings.TrimSpace(os.Getenv("OPENWORKER_ROOT"));v!=""{return v};for _,p:=range[]string{`C:\github-runners\openworker\_work\openworker\openworker`,`D:\AI\openworker`,`D:\AIWork\openworker`,`D:\PyWork\openworker`}{if st,e:=os.Stat(filepath.Join(p,"case-specs","0005.json"));e==nil&&!st.IsDir(){return p}};return ""}
