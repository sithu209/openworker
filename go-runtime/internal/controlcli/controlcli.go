package controlcli

import (
    "bytes"
    "encoding/json"
    "flag"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "os"
    "path/filepath"
    "strconv"
    "strings"
    "time"

    "github.com/liuxb99/openworker/go-runtime/internal/actionsqueue"
)

const DefaultServer = "http://127.0.0.1:8787"

type client struct { base string; http *http.Client }
type caseCfg struct { CaseID, Machine, Workspace, OpenWorkerRoot, Manifest, Spec string }
type caseManifestHeader struct { CaseID string `json:"case_id"`; WorkspaceRoot string `json:"workspace_root"`; AssignedHost string `json:"assigned_host"`; Revision int `json:"revision"` }

func Main(program string) int { return Run(program, os.Args[1:], os.Stdout, os.Stderr) }
func Run(program string, args []string, stdout, stderr io.Writer) int {
    fs:=flag.NewFlagSet(program,flag.ContinueOnError);fs.SetOutput(stderr)
    server:=fs.String("server",DefaultServer,"localhost OpenWorker supervisor URL")
    if err:=fs.Parse(args);err!=nil{return 2};if err:=validateServer(*server);err!=nil{fmt.Fprintln(stderr,"OPENWORKER_FAIL:",err);return 1}
    a:=fs.Args();if len(a)<2{usage(stderr,program);return 2};c:=client{strings.TrimRight(*server,"/"),&http.Client{Timeout:60*time.Second}}
    var out any;var err error
    switch a[0]+" "+a[1] {
    case "supervisor status":
        if len(a)!=2{return usageCode(stderr,program)};out,err=c.get("/v1/node/status")
    case "case status":
        if len(a)!=3{return usageCode(stderr,program)};var cfg caseCfg;cfg,err=caseConfig(a[2]);if err!=nil{break};if err=requireLocalMachine(cfg.Machine);err!=nil{break};out,err=c.caseStatus(cfg)
    case "case bootstrap":
        if len(a)!=3{return usageCode(stderr,program)};var cfg caseCfg;cfg,err=caseConfig(a[2]);if err!=nil{break};if err=requireLocalMachine(cfg.Machine);err!=nil{break};if err=c.requireOperational(cfg.Machine);err!=nil{break};out,err=c.post("/v1/cases/bootstrap",cfg.bootstrapPayload())
    case "case continue":
        if len(a)!=3{return usageCode(stderr,program)};var cfg caseCfg;cfg,err=caseConfig(a[2]);if err!=nil{break};if err=requireLocalMachine(cfg.Machine);err!=nil{break};if err=c.requireOperational(cfg.Machine);err!=nil{break};out,err=c.post("/v1/cases/continue",cfg.continuePayload())
    case "queue clear":
        m,e:=localMachine();if e!=nil{err=e;break};if len(a)==3{m=strings.TrimSpace(a[2])}else if len(a)!=2{return usageCode(stderr,program)};if err=requireLocalMachine(m);err!=nil{break};out,err=c.post("/v1/queue/drain?mode=all",map[string]any{})
    case "actions queue-clear":
        if len(a)>3{return usageCode(stderr,program)}
        repo:=actionsqueue.DefaultRepository();if len(a)==3{repo=strings.TrimSpace(a[2])}
        var exclude int64;if v:=strings.TrimSpace(os.Getenv("GITHUB_RUN_ID"));v!=""{exclude,_=strconv.ParseInt(v,10,64)}
        out,err=actionsqueue.Clear(actionsqueue.Options{Repository:repo,Token:actionsqueue.DefaultToken(),ExcludeRunID:exclude,RunID:os.Getenv("GITHUB_RUN_ID"),SourceSHA:os.Getenv("GITHUB_SHA")})
    default:return usageCode(stderr,program)
    }
    if err!=nil{fmt.Fprintln(stderr,"OPENWORKER_FAIL:",err);if out!=nil{enc:=json.NewEncoder(stdout);enc.SetEscapeHTML(false);enc.SetIndent("","  ");_ = enc.Encode(out)};return 1};enc:=json.NewEncoder(stdout);enc.SetEscapeHTML(false);enc.SetIndent("","  ");if err:=enc.Encode(out);err!=nil{fmt.Fprintln(stderr,"OPENWORKER_FAIL:",err);return 1};return 0
}

func(c client)caseStatus(cfg caseCfg)(any,error){
    out,err:=c.get("/v1/jobs?limit=500");if err!=nil{return nil,err};m:=map[string]any{"schema":"openworker.case-status/v1","case_id":cfg.CaseID,"machine":cfg.Machine,"workspace_root":cfg.Workspace,"dashboard":"/ui/"}
    if obj,ok:=out.(map[string]any);ok{if raw,ok:=obj["jobs"].([]any);ok{needle:="case"+strings.ToLower(cfg.CaseID)+"-";jobs:=make([]any,0);for _,v:=range raw{row,ok:=v.(map[string]any);if !ok{continue};if strings.Contains(strings.ToLower(fmt.Sprint(row["job_id"])),needle)||strings.Contains(strings.ToLower(fmt.Sprint(row["dispatch_id"])),needle){jobs=append(jobs,row)}};m["jobs"]=jobs;m["job_count"]=len(jobs)}}
    controllerPath:=filepath.Join(cfg.Workspace,".openworker","case-controller-last.json");if b,readErr:=os.ReadFile(controllerPath);readErr==nil{var v any;if json.Unmarshal(b,&v)==nil{m["controller_last"]=v}}
    return m,nil
}
func caseConfig(id string)(caseCfg,error){
    id=strings.TrimSpace(id);if !validCaseID(id){return caseCfg{},fmt.Errorf("invalid case_id %q",id)}
    root:=strings.TrimSpace(os.Getenv("OPENWORKER_ROOT"));if root==""{root=discoverRoot()};if root==""{return caseCfg{},fmt.Errorf("OpenWorker checkout not found")}
    manifest:=filepath.Join(root,"case-worklists",id+".json");spec:=filepath.Join(root,"case-specs",id+".json")
    b,err:=os.ReadFile(manifest);if err!=nil{return caseCfg{},fmt.Errorf("case manifest unavailable for %s: %w",id,err)};var h caseManifestHeader;if err:=json.Unmarshal(b,&h);err!=nil{return caseCfg{},fmt.Errorf("decode case manifest %s: %w",id,err)}
    if strings.TrimSpace(h.CaseID)!=id{return caseCfg{},fmt.Errorf("case manifest identity mismatch requested=%q manifest=%q",id,h.CaseID)};if strings.TrimSpace(h.AssignedHost)==""{return caseCfg{},fmt.Errorf("case %s manifest missing assigned_host",id)};if strings.TrimSpace(h.WorkspaceRoot)==""||!casePathIsAbs(h.WorkspaceRoot){return caseCfg{},fmt.Errorf("case %s manifest workspace_root must be absolute",id)};if h.Revision<=0{return caseCfg{},fmt.Errorf("case %s manifest revision must be positive",id)}
    sb,err:=os.ReadFile(spec);if err!=nil{return caseCfg{},fmt.Errorf("case spec unavailable for %s: %w",id,err)};var sm map[string]any;if err:=json.Unmarshal(sb,&sm);err!=nil{return caseCfg{},fmt.Errorf("decode case spec %s: %w",id,err)};if strings.TrimSpace(fmt.Sprint(sm["case_id"]))!=id{return caseCfg{},fmt.Errorf("case spec identity mismatch for %s",id)}
    return caseCfg{id,h.AssignedHost,h.WorkspaceRoot,root,manifest,spec},nil
}
func casePathIsAbs(p string)bool{p=strings.TrimSpace(p);if filepath.IsAbs(p){return true};return len(p)>=3&&((p[0]>='A'&&p[0]<='Z')||(p[0]>='a'&&p[0]<='z'))&&p[1]==':'&&(p[2]=='\\'||p[2]=='/')}
func validCaseID(id string)bool{id=strings.TrimSpace(id);if id==""||len(id)>64{return false};for _,r:=range id{if (r>='a'&&r<='z')||(r>='A'&&r<='Z')||(r>='0'&&r<='9')||r=='-'||r=='_'||r=='.'{continue};return false};return id!="."&&id!=".."}
func(c caseCfg)bootstrapPayload()map[string]any{return map[string]any{"case_id":c.CaseID,"machine":c.Machine,"workspace_root":c.Workspace,"openworker_root":c.OpenWorkerRoot,"manifest_path":c.Manifest,"spec_path":c.Spec}}
func(c caseCfg)continuePayload()map[string]any{return map[string]any{"case_id":c.CaseID,"machine":c.Machine,"workspace_root":c.Workspace,"openworker_root":c.OpenWorkerRoot,"manifest_path":c.Manifest,"spec_path":c.Spec,"request_id":strings.TrimSpace(os.Getenv("OPENWORKER_CONTROL_REQUEST_ID"))}}
func(c client)requireOperational(machine string)error{v,e:=c.get("/v1/node/status");if e!=nil{return e};m,ok:=v.(map[string]any);if !ok{return fmt.Errorf("invalid OpenWorker node status")};if b,ok:=m["online"].(bool);ok&&!b{return fmt.Errorf("OpenWorker node online=false")};if !strings.EqualFold(strings.TrimSpace(fmt.Sprint(m["machine"])),strings.TrimSpace(machine)){return fmt.Errorf("OpenWorker node machine mismatch")};return nil}
func(c client)get(p string)(any,error){return c.do(http.MethodGet,p,nil)}
func(c client)post(p string,v any)(any,error){b,e:=json.Marshal(v);if e!=nil{return nil,e};return c.do(http.MethodPost,p,b)}
func(c client)do(method,p string,b []byte)(any,error){var r io.Reader;if b!=nil{r=bytes.NewReader(b)};req,e:=http.NewRequest(method,c.base+p,r);if e!=nil{return nil,e};if b!=nil{req.Header.Set("Content-Type","application/json")};resp,e:=c.http.Do(req);if e!=nil{return nil,e};defer resp.Body.Close();data,e:=io.ReadAll(io.LimitReader(resp.Body,16<<20));if e!=nil{return nil,e};var out any;if len(bytes.TrimSpace(data))>0{_ = json.Unmarshal(data,&out)};if resp.StatusCode/100!=2{return out,fmt.Errorf("HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(data)))};return out,nil}
func validateServer(raw string)error{u,e:=url.Parse(strings.TrimSpace(raw));if e!=nil{return e};h:=strings.ToLower(u.Hostname());if u.Scheme!="http"||(h!="127.0.0.1"&&h!="localhost"&&h!="::1")||u.Port()!="8787"||(u.Path!=""&&u.Path!="/"){return fmt.Errorf("server must be http localhost:8787 without path")};return nil}
func localMachine()(string,error){h,e:=os.Hostname();return strings.TrimSpace(h),e}
func requireLocalMachine(w string)error{a,e:=localMachine();if e!=nil{return e};if !strings.EqualFold(a,strings.TrimSpace(w)){return fmt.Errorf("machine mismatch local=%q expected=%q",a,w)};return nil}
func discoverRoot()string{for _,p:=range[]string{`C:\ProgramData\OpenWorker\runtime\openworker`,`C:\github-runners\openworker\_work\openworker\openworker`,`D:\AI\openworker`,`D:\AIWork\openworker`,`D:\PyWork\openworker`}{if st,e:=os.Stat(filepath.Join(p,"case-worklists"));e==nil&&st.IsDir(){if st2,e2:=os.Stat(filepath.Join(p,"coworker"));e2==nil&&st2.IsDir(){return p}}};return ""}
func usageCode(w io.Writer,p string)int{usage(w,p);return 2}
func usage(w io.Writer,p string){fmt.Fprintf(w,"usage: %s supervisor status | case bootstrap <CASE_ID> | case status <CASE_ID> | case continue <CASE_ID> | queue clear [MACHINE] | actions queue-clear [OWNER/REPO]\n",p)}
