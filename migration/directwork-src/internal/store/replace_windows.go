//go:build windows

package store

import "golang.org/x/sys/windows"

func atomicReplace(src, dst string) error {
	s, err := windows.UTF16PtrFromString(src)
	if err != nil { return err }
	d, err := windows.UTF16PtrFromString(dst)
	if err != nil { return err }
	return windows.MoveFileEx(s, d, windows.MOVEFILE_REPLACE_EXISTING|windows.MOVEFILE_WRITE_THROUGH)
}
