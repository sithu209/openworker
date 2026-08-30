package api

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/liuxb99/DirectWork/internal/buildinfo"
	"github.com/liuxb99/DirectWork/internal/cluster"
	"github.com/liuxb99/DirectWork/internal/model"
	"github.com/liuxb99/DirectWork/internal/runtime"
	"github.com/liuxb99/DirectWork/internal/store"
)

type Server struct{store *store.Store;runtime *runtime.Manager;machine string;advertise string;cluster *cluster.Controller}
func New(st *store.Store,rt *runtime.Manager,machine,advertise string,cc *cluster.Controller)*Server{return &Server{store:st,runtime:rt,machine:machine,advertise:advertise,cluster:cc}}

func(s *Server)Handler()http.Handler{
	mux:=http.NewServeMux()
	mux.HandleFunc("GET /v1/node/status",s.nodeStatus)
	mux.HandleFunc("GET /v1/nodes",s.nodes)
	mux.HandleFunc("GET /v1/work",s.listWork)
	mux.HandleFunc("POST /v1/work",s.createWork)
	mux.HandleFunc("GET /v1/work/{id}",s.getWork)
	mux.HandleFunc("GET /v1/work/{id}/events",s.getEvents)
	mux.HandleFunc("POST /v1/work/{id}/cancel",s.cancelWork)
	mux.HandleFunc("POST /v1/work/{id}/retry",s.retryWork)
	mux.HandleFunc("GET /v1/work/{id}/artifacts",s.listArtifacts)
	mux.HandleFunc("GET /v1/work/{id}/artifact",s.serveArtifact)
	mux.HandleFunc("GET /ui/",s.dashboard)
	return withHeaders(mux)
}

func withHeaders(next http.Handler)http.Handler{return http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){w.Header().Set("X-DirectWork","control-plane");next.ServeHTTP(w,r)})}
func writeJSON(w http.ResponseWriter,status int,v any){w.Header().Set("Content-Type","application/json; charset=utf-8");w.WriteHeader(status);_=json.NewEncoder(w).Encode(v)}
func newID()string{b:=make([]byte,8);_,_=rand.Read(b);return "dw-"+time.Now().UTC().Format("20060102T150405")+"-"+hex.EncodeToString(b)}

func(s *Server)nodeStatus(w http.ResponseWriter,r *http.Request){v:=s.runtime.Status();for k,x:=range buildinfo.Snapshot(){v[k]=x};v["advertise"]=s.advertise;if s.cluster!=nil{v["peers"]=s.cluster.Snapshot()};writeJSON(w,200,v)}
func(s *Server)nodes(w http.ResponseWriter,r *http.Request){peers:=[]cluster.PeerStatus{};if s.cluster!=nil{peers=s.cluster.Snapshot()};writeJSON(w,200,map[string]any{"local":s.runtime.Status(),"peers":peers})}
func(s *Server)listWork(w http.ResponseWriter,r *http.Request){n,_:=strconv.Atoi(r.URL.Query().Get("limit"));if n<=0{n=100};writeJSON(w,200,map[string]any{"works":s.store.List(n)})}
func(s *Server)createWork(w http.ResponseWriter,r *http.Request){var req model.CreateWorkRequest;if err:=json.NewDecoder(r.Body).Decode(&req);err!=nil{writeJSON(w,400,map[string]any{"error":err.Error()});return};if err:=runtime.ValidateCommand(req.Command);err!=nil{writeJSON(w,400,map[string]any{"error":err.Error()});return};if strings.TrimSpace(req.CWD)==""{writeJSON(w,400,map[string]any{"error":"cwd required"});return};if st,err:=os.Stat(req.CWD);err!=nil||!st.IsDir(){writeJSON(w,400,map[string]any{"error":"cwd must be an existing directory"});return};timeout:=req.TimeoutSec;if timeout<=0{timeout=3600};work:=model.Work{WorkID:newID(),DispatchID:req.DispatchID,CaseID:req.CaseID,Project:req.Project,Machine:req.Machine,Command:req.Command,CWD:req.CWD,WorkspaceRoot:req.WorkspaceRoot,TimeoutSec:timeout,Env:req.Env,Status:model.StatusPending,CreatedAt:time.Now().UTC()};if err:=s.store.Create(work);err!=nil{writeJSON(w,500,map[string]any{"error":err.Error()});return};writeJSON(w,202,work)}
func(s *Server)getWork(w http.ResponseWriter,r *http.Request){v,err:=s.store.Get(r.PathValue("id"));if err!=nil{writeJSON(w,404,map[string]any{"error":"work not found"});return};writeJSON(w,200,v)}
func(s *Server)getEvents(w http.ResponseWriter,r *http.Request){writeJSON(w,200,map[string]any{"events":s.store.Events(r.PathValue("id"))})}
func(s *Server)cancelWork(w http.ResponseWriter,r *http.Request){if err:=s.runtime.Cancel(r.PathValue("id"));err!=nil{writeJSON(w,400,map[string]any{"error":err.Error()});return};writeJSON(w,200,map[string]any{"ok":true})}
func(s *Server)retryWork(w http.ResponseWriter,r *http.Request){if err:=s.runtime.Retry(r.PathValue("id"));err!=nil{writeJSON(w,400,map[string]any{"error":err.Error()});return};writeJSON(w,200,map[string]any{"ok":true})}
func artifactRoot(work model.Work)string{if work.WorkspaceRoot!=""{return filepath.Clean(work.WorkspaceRoot)};return filepath.Clean(work.CWD)}
