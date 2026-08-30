package main

import (
    "os"
    "github.com/liuxb99/openworker/go-runtime/internal/controlcli"
)

func main(){os.Exit(controlcli.Main("openworkerctl"))}
