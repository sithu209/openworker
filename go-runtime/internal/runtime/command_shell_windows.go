//go:build windows

package runtime

import (
    "context"
    "os"
    "os/exec"
    "strings"
    "syscall"
)

func platformCommandForShell(ctx context.Context, command string) *exec.Cmd {
    comspec:=strings.TrimSpace(os.Getenv("COMSPEC"))
    if comspec==""{comspec=`C:\Windows\System32\cmd.exe`}
    cmd:=exec.CommandContext(ctx,comspec)
    line:=strings.TrimSpace(command)
    // cmd.exe /S /C has a special quoted-executable rule: when the command
    // starts with a quote, the complete command must be wrapped in one more
    // quote pair.  SysProcAttr.CmdLine is the *entire* CreateProcess command
    // line, so argv[0] must also be present here.
    if strings.HasPrefix(line,"\""){line="\""+line+"\""}
    cmd.SysProcAttr=&syscall.SysProcAttr{CmdLine:"\""+comspec+"\" /D /S /C "+line}
    return cmd
}
