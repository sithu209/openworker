//go:build windows

package main

import (
	"context"
	"golang.org/x/sys/windows/svc"
)

type nodeService struct{ cfg nodeConfig }

func (s *nodeService) Execute(args []string, req <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	const accepts = svc.AcceptStop | svc.AcceptShutdown
	status <- svc.Status{State: svc.StartPending}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- runNode(ctx, s.cfg) }()
	status <- svc.Status{State: svc.Running, Accepts: accepts}
	for {
		select {
		case err := <-done:
			status <- svc.Status{State: svc.StopPending}
			if err != nil { return false, 1 }
			return false, 0
		case c := <-req:
			switch c.Cmd {
			case svc.Interrogate:
				status <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				status <- svc.Status{State: svc.StopPending}
				cancel()
				if err := <-done; err != nil { return false, 1 }
				return false, 0
			}
		}
	}
}

func runWindowsService(cfg nodeConfig) error {
	return svc.Run("OpenWorkerNode", &nodeService{cfg: cfg})
}
