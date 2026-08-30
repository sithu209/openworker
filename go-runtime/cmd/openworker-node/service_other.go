//go:build !windows

package main

import "fmt"

func runWindowsService(cfg nodeConfig) error {
	return fmt.Errorf("-service mode is only supported on Windows")
}
