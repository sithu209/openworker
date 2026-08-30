package main

import (
	"context"
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/liuxb99/DirectWork/internal/api"
	"github.com/liuxb99/DirectWork/internal/cluster"
	"github.com/liuxb99/DirectWork/internal/runtime"
	"github.com/liuxb99/DirectWork/internal/store"
)

func splitPeers(v string)[]string{out:=[]string{};for _,p:=range strings.Split(v,","){p=strings.TrimSpace(p);if p!=""{out=append(out,p)}};return out}
func advertiseFor(listen,machine string)string{host,port,err:=net.SplitHostPort(listen);if err!=nil{return "http://"+listen};if host==""||host=="0.0.0.0"||host=="::"{host=machine};return "http://"+net.JoinHostPort(host,port)}

func run(ctx context.Context,listen string,workers int,data,peers string)error{
	machine,err:=os.Hostname();if err!=nil{return err}
	if data==""{data=filepath.Join(os.TempDir(),"directwork-node")}
	if err:=os.MkdirAll(data,0755);err!=nil{return err}
	st,err:=store.Open(filepath.Join(data,"directwork.json"));if err!=nil{return err};defer st.Close()
	rt:=runtime.New(st,workers,filepath.Join(data,"logs"),machine);if err:=rt.Start();err!=nil{return err};defer rt.Stop()
	cc:=cluster.New(splitPeers(peers));cc.Start(ctx)
	advertise:=advertiseFor(listen,machine)
	srv:=&http.Server{Addr:listen,Handler:api.New(st,rt,machine,advertise,cc).Handler(),ReadHeaderTimeout:5*time.Second}
	errCh:=make(chan error,1);go func(){log.Printf("DirectWork machine=%s listen=%s advertise=%s workers=%d data=%s peers=%s",machine,listen,advertise,workers,data,peers);e:=srv.ListenAndServe();if e==http.ErrServerClosed{e=nil};errCh<-e}()
	select{case<-ctx.Done():c,cancel:=context.WithTimeout(context.Background(),10*time.Second);defer cancel();return srv.Shutdown(c);case e:=<-errCh:return e}
}

func main(){var listen,data,peers string;var workers int;var serviceMode bool;flag.StringVar(&listen,"listen","127.0.0.1:8787","listen address");flag.StringVar(&data,"data","","durable data directory");flag.IntVar(&workers,"workers",4,"max concurrent slots");flag.StringVar(&peers,"peers","","comma-separated DirectWork peer endpoints");flag.BoolVar(&serviceMode,"service",false,"run under Windows Service Control Manager");flag.Parse();if serviceMode{if err:=runWindowsService(listen,workers,data,peers);err!=nil{log.Fatal(err)};return};ctx,stop:=signal.NotifyContext(context.Background(),os.Interrupt,syscall.SIGTERM);defer stop();if err:=run(ctx,listen,workers,data,peers);err!=nil{log.Fatal(err)}}
