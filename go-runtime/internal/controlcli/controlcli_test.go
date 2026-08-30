package controlcli

import (
    "bytes"
    "os"
    "path/filepath"
    "testing"
)

func TestValidateServerLocalOnly(t *testing.T){
    for _,v:=range[]string{"http://127.0.0.1:8787","http://localhost:8787","http://[::1]:8787"}{if e:=validateServer(v);e!=nil{t.Fatalf("%s: %v",v,e)}}
    for _,v:=range[]string{"https://127.0.0.1:8787","http://DESKTOP-ODAQN0D:8787","http://127.0.0.1:8848","http://127.0.0.1:8787/api"}{if e:=validateServer(v);e==nil{t.Fatalf("expected rejection: %s",v)}}
}
func TestCaseConfigUnknownFailsClosed(t *testing.T){if _,e:=caseConfig("9999");e==nil{t.Fatal("unknown case accepted")}}
func TestCaseConfigCase0004(t *testing.T){
    root:=t.TempDir();if err:=os.MkdirAll(filepath.Join(root,"case-worklists"),0o755);err!=nil{t.Fatal(err)};if err:=os.MkdirAll(filepath.Join(root,"case-specs"),0o755);err!=nil{t.Fatal(err)}
    manifest:=`{"case_id":"0004","assigned_host":"DESKTOP-O87PJNR","workspace_root":"D:\\AI-Work\\jobs\\0004-DWG-TO-3D","revision":1}`
    if err:=os.WriteFile(filepath.Join(root,"case-worklists","0004.json"),[]byte(manifest),0o644);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(filepath.Join(root,"case-specs","0004.json"),[]byte(`{"case_id":"0004"}`),0o644);err!=nil{t.Fatal(err)}
    old:=os.Getenv("OPENWORKER_ROOT");t.Cleanup(func(){_ = os.Setenv("OPENWORKER_ROOT",old)});_ = os.Setenv("OPENWORKER_ROOT",root)
    cfg,err:=caseConfig("0004");if err!=nil{t.Fatal(err)}
    if cfg.CaseID!="0004"||cfg.Machine!="DESKTOP-O87PJNR"||cfg.Workspace!=`D:\AI-Work\jobs\0004-DWG-TO-3D`{t.Fatalf("unexpected config: %#v",cfg)}
    if filepath.Base(cfg.Manifest)!="0004.json"||filepath.Base(cfg.Spec)!="0004.json"{t.Fatalf("unexpected paths: %#v",cfg)}
}
func TestContinuePayloadCarriesControlRequestID(t *testing.T){
    old:=os.Getenv("OPENWORKER_CONTROL_REQUEST_ID");t.Cleanup(func(){_ = os.Setenv("OPENWORKER_CONTROL_REQUEST_ID",old)});_ = os.Setenv("OPENWORKER_CONTROL_REQUEST_ID","case0005-smoke-20260820-a1")
    cfg:=caseCfg{CaseID:"0005",Machine:"DESKTOP-ODAQN0D",Workspace:`D:\AI-Work\jobs\0005-SNOW-WHITE`,OpenWorkerRoot:`D:\AI\openworker`,Manifest:`D:\AI\openworker\case-worklists\0005.json`,Spec:`D:\AI\openworker\case-specs\0005.json`}
    p:=cfg.continuePayload();if p["request_id"]!="case0005-smoke-20260820-a1"{t.Fatalf("request_id missing: %#v",p)}
}
func TestMachineAuthority(t *testing.T){h,e:=os.Hostname();if e!=nil{t.Fatal(e)};if e=requireLocalMachine(h);e!=nil{t.Fatal(e)};if e=requireLocalMachine(h+"-WRONG");e==nil{t.Fatal("wrong host accepted")}}
func TestUsageDoesNotRequirePython(t *testing.T){var out,err bytes.Buffer;code:=Run("openworker",[]string{"case","status"},&out,&err);if code!=2{t.Fatalf("code=%d",code)};if bytes.Contains(err.Bytes(),[]byte("python")){t.Fatalf("usage leaked Python dependency: %s",err.String())}}
