//go:build !windows

package store

import "os"

func atomicReplace(src, dst string) error { return os.Rename(src, dst) }
