//go:build !windows

package runtime

import (
    "context"
    "os/exec"
)

func platformCommandForShell(ctx context.Context, command string) *exec.Cmd {
    return exec.CommandContext(ctx,"/bin/sh","-c",command)
}
