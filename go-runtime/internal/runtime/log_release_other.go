//go:build !windows

package runtime

func waitForReleasedLogs(paths ...string) error { return nil }
