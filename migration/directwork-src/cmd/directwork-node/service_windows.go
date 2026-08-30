//go:build windows

package main

import (
	"context"
	"time"

	"golang.org/x/sys/windows/svc"
)

type serviceHandler struct{listen string;workers int;data string;peers string}
func(h serviceHandler)Execute(args []string,req <-chan svc.ChangeRequest,status chan<- svc.Status)(bool,uint32){status<-svc.Status{State:svc.StartPending};ctx,cancel:=context.WithCancel(context.Background());done:=make(chan error,1);go func(){done<-run(ctx,h.listen,h.workers,h.data,h.peers)}();status<-svc.Status{State:svc.Running,Accepts:svc.AcceptStop|svc.AcceptShutdown};for{select{case c:=<-req:switch c.Cmd{case svc.Interrogate:status<-c.CurrentStatus;case svc.Stop,svc.Shutdown:status<-svc.Status{State:svc.StopPending};cancel();select{case<-done:case<-time.After(15*time.Second):};return false,0};case<-done:return false,0}}}
func runWindowsService(listen string,workers int,data,peers string)error{return svc.Run("DirectWorkNode",serviceHandler{listen:listen,workers:workers,data:data,peers:peers})}
