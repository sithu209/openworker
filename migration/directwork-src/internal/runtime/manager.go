package runtime

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	gort "runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/liuxb99/DirectWork/internal/model"
	"github.com/liuxb99/DirectWork/internal/store"
)

type Manager struct {
	store *store.Store
	maxWorkers int
	logsDir string
	machine string
	stop chan struct{}
	wg sync.WaitGroup
	mu sync.Mutex
	cancel map[string]context.CancelFunc
}

func New(st *store.Store, maxWorkers int, logsDir, machine string) *Manager {
	if maxWorkers <= 0 { maxWorkers = 4 }
	return &Manager{store:st,maxWorkers:maxWorkers,logsDir:logsDir,machine:machine,stop:make(chan struct{}),cancel:map[string]context.CancelFunc{}}
}

func (m *Manager) recoverStartup() error {
	for _, w := range m.store.List(100000) {
		if w.Status != model.StatusClaimed && w.Status != model.StatusRunning { continue }
		if w.PID > 0 { killTree(w.PID) }
		detail := fmt.Sprintf("startup recovery: stale %s work from slot=%d pid=%d marked failed before workers resumed", w.Status, w.Slot, w.PID)
		if err := m.store.Finish(w.WorkID, model.StatusFailed, -1, detail); err != nil { return err }
	}
	return nil
}

func (m *Manager) Start() error {
	if err:=os.MkdirAll(m.logsDir,0755); err!=nil{return err}
	if err:=m.recoverStartup(); err!=nil{return err}
	for i:=1;i<=m.maxWorkers;i++ { m.wg.Add(1); go m.worker(i) }
	return nil
}

func (m *Manager) Stop(){ close(m.stop); m.mu.Lock(); for _,c:=range m.cancel{c()}; m.mu.Unlock(); m.wg.Wait() }

func (m *Manager) worker(slot int){
	defer m.wg.Done(); t:=time.NewTicker(300*time.Millisecond); defer t.Stop()
	for { select { case <-m.stop:return; case <-t.C:
		w,err:=m.store.ClaimNext(m.machine,slot); if err!=nil||w==nil{continue}; m.run(*w)
	} }
}

func shellCommand(ctx context.Context, command string) *exec.Cmd {
	if gort.GOOS=="windows" { return exec.CommandContext(ctx,"cmd.exe","/d","/s","/c",command) }
	return exec.CommandContext(ctx,"/bin/sh","-lc",command)
}

func (m *Manager) run(w model.Work){
	if w.CWD=="" { _=m.store.Finish(w.WorkID,model.StatusFailed,-1,"cwd required"); return }
	if st,err:=os.Stat(w.CWD); err!=nil||!st.IsDir(){ _=m.store.Finish(w.WorkID,model.StatusFailed,-1,"invalid cwd"); return }
	ctx,cancel:=context.WithTimeout(context.Background(),time.Duration(w.TimeoutSec)*time.Second)
	m.mu.Lock();m.cancel[w.WorkID]=cancel;m.mu.Unlock(); defer func(){cancel();m.mu.Lock();delete(m.cancel,w.WorkID);m.mu.Unlock()}()
	stdoutPath:=filepath.Join(m.logsDir,w.WorkID+".stdout.log"); stderrPath:=filepath.Join(m.logsDir,w.WorkID+".stderr.log")
	out,err:=os.Create(stdoutPath); if err!=nil{_=m.store.Finish(w.WorkID,model.StatusFailed,-1,err.Error());return}; defer out.Close()
	errOut,err:=os.Create(stderrPath); if err!=nil{_=m.store.Finish(w.WorkID,model.StatusFailed,-1,err.Error());return}; defer errOut.Close()
	cmd:=shellCommand(ctx,w.Command); cmd.Dir=w.CWD; cmd.Stdout=out; cmd.Stderr=errOut; cmd.Env=os.Environ()
	for k,v:=range w.Env{cmd.Env=append(cmd.Env,k+"="+v)}
	cmd.Env=append(cmd.Env,"DIRECTWORK_WORK_ID="+w.WorkID,"DIRECTWORK_SLOT="+strconv.Itoa(w.Slot),"DIRECTWORK_MACHINE="+m.machine)
	if w.WorkspaceRoot!=""{cmd.Env=append(cmd.Env,"DIRECTWORK_WORKSPACE="+w.WorkspaceRoot)}
	if err:=cmd.Start();err!=nil{_=m.store.Finish(w.WorkID,model.StatusFailed,-1,"start failed: "+err.Error());return}
	_=m.store.MarkRunning(w.WorkID,cmd.Process.Pid,stdoutPath,stderrPath)
	done:=make(chan error,1); go func(){done<-cmd.Wait()}(); hb:=time.NewTicker(2*time.Second); defer hb.Stop()
	for{select{
	case err:=<-done:
		if ctx.Err()==context.DeadlineExceeded{_=m.store.Finish(w.WorkID,model.StatusTimedOut,-1,"timeout exceeded");return}
		if ctx.Err()==context.Canceled{cur,_:=m.store.Get(w.WorkID);if cur.Status==model.StatusCancelled{return}}
		if err==nil{_=m.store.Finish(w.WorkID,model.StatusSucceeded,0,"process exited successfully");return}
		exit:=-1; if ee,ok:=err.(*exec.ExitError);ok{exit=ee.ExitCode()}; _=m.store.Finish(w.WorkID,model.StatusFailed,exit,err.Error());return
	case <-hb.C: _=m.store.Heartbeat(w.WorkID)
	case <-ctx.Done(): if cmd.Process!=nil{killTree(cmd.Process.Pid)}
	}}
}

func killTree(pid int){if pid<=0{return};if gort.GOOS=="windows"{_=exec.Command("taskkill","/PID",strconv.Itoa(pid),"/T","/F").Run();return};if p,e:=os.FindProcess(pid);e==nil{_=p.Kill()}}

func (m *Manager) Cancel(id string) error { m.mu.Lock();c:=m.cancel[id];m.mu.Unlock(); if c!=nil{c()}; return m.store.Cancel(id) }
func (m *Manager) Retry(id string) error { return m.store.Retry(id) }
func (m *Manager) Status() map[string]any {
	works:=m.store.List(1000);busy,queued:=0,0
	for _,w:=range works{if w.Status==model.StatusRunning||w.Status==model.StatusClaimed{busy++};if w.Status==model.StatusPending{queued++}}
	return map[string]any{"machine":m.machine,"online":true,"max_workers":m.maxWorkers,"busy_workers":busy,"free_workers":max(0,m.maxWorkers-busy),"queued_works":queued,"time":time.Now().UTC()}
}

func ValidateCommand(s string) error { if strings.TrimSpace(s)==""{return fmt.Errorf("command required")}; return nil }
