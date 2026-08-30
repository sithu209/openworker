//go:build !windows

package main

import "fmt"

func runWindowsService(listen string, workers int, data, peers string) error { return fmt.Errorf("Windows service mode is only supported on Windows") }
