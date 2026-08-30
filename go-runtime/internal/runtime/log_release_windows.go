//go:build windows

package runtime

import (
    "fmt"
    "os"
    "time"
)

func waitForReleasedLogs(paths ...string) error {
    deadline:=time.Now().Add(5*time.Second)
    for {
        all:=true
        for _,p:=range paths {
            if p=="" { continue }
            probe:=p+".releasecheck"
            _=os.Remove(probe)
            if err:=os.Rename(p,probe);err!=nil { all=false; break }
            if err:=os.Rename(probe,p);err!=nil { return fmt.Errorf("restore released log %s: %w",p,err) }
        }
        if all { return nil }
        if time.Now().After(deadline) { return fmt.Errorf("timeout waiting for Windows child process log handles to release") }
        time.Sleep(25*time.Millisecond)
    }
}
