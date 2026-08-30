package inventory

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCollectCapabilitiesAreNormalized(t *testing.T) {
	old:=os.Getenv("OPENWORKER_NODE_CAPABILITIES")
	defer os.Setenv("OPENWORKER_NODE_CAPABILITIES",old)
	_ = os.Setenv("OPENWORKER_NODE_CAPABILITIES"," blender,case0003,blender, bridge ")
	s:=Collect()
	want:=[]string{"blender","bridge","case0003"}
	if len(s.Capabilities)!=len(want){t.Fatalf("got %#v",s.Capabilities)}
	for i:=range want{if s.Capabilities[i]!=want[i]{t.Fatalf("got %#v want %#v",s.Capabilities,want)}}
	if len(s.Tools)==0{t.Fatal("expected tool inventory")}
}

func TestCollectRootsReportsConfiguredExistingDirectories(t *testing.T) {
	tmp:=t.TempDir();root:=filepath.Join(tmp,"terrain");if err:=os.MkdirAll(root,0o755);err!=nil{t.Fatal(err)}
	old:=os.Getenv("TERRAIN_ROOT");defer os.Setenv("TERRAIN_ROOT",old);if err:=os.Setenv("TERRAIN_ROOT",root);err!=nil{t.Fatal(err)}
	s:=Collect();var got *Root;for i:=range s.Roots{if s.Roots[i].Env=="TERRAIN_ROOT"{got=&s.Roots[i];break}}
	if got==nil||!got.Available{t.Fatalf("expected available root: %#v",got)}
	want,err:=filepath.Abs(root);if err!=nil{t.Fatal(err)};if got.Path!=filepath.Clean(want){t.Fatalf("path=%q want=%q",got.Path,filepath.Clean(want))}
	if got.Source!="process-env"{t.Fatalf("source=%q",got.Source)}
}

func TestCollectRootsDoesNotClaimMissingDirectoryAvailable(t *testing.T) {
	missing:=filepath.Join(t.TempDir(),"missing");old:=os.Getenv("SCENEX_ROOT");defer os.Setenv("SCENEX_ROOT",old);if err:=os.Setenv("SCENEX_ROOT",missing);err!=nil{t.Fatal(err)}
	s:=Collect();for _,root:=range s.Roots{if root.Env=="SCENEX_ROOT"{if root.Available{t.Fatalf("missing root reported available: %#v",root)};return}};t.Fatal("SCENEX_ROOT inventory missing")
}

func TestCollectRootsUsesPersistedRegistryWithoutProcessEnv(t *testing.T) {
	tmp:=t.TempDir();terrain:=filepath.Join(tmp,"terrain");if err:=os.MkdirAll(terrain,0o755);err!=nil{t.Fatal(err)}
	registry:=filepath.Join(tmp,"machine-roots.json");data,_:=json.Marshal(map[string]string{"TERRAIN_ROOT":terrain});if err:=os.WriteFile(registry,data,0o644);err!=nil{t.Fatal(err)}
	oldFile:=os.Getenv("OPENWORKER_MACHINE_ROOTS_FILE");oldTerrain:=os.Getenv("TERRAIN_ROOT");defer os.Setenv("OPENWORKER_MACHINE_ROOTS_FILE",oldFile);defer os.Setenv("TERRAIN_ROOT",oldTerrain)
	_ = os.Setenv("OPENWORKER_MACHINE_ROOTS_FILE",registry);_ = os.Unsetenv("TERRAIN_ROOT")
	s:=Collect();for _,root:=range s.Roots{if root.Env=="TERRAIN_ROOT"{if !root.Available||root.Source!="machine-registry"{t.Fatalf("unexpected root: %#v",root)};return}};t.Fatal("TERRAIN_ROOT inventory missing")
}

func TestProcessEnvOverridesPersistedRegistry(t *testing.T) {
	tmp:=t.TempDir();persisted:=filepath.Join(tmp,"persisted");override:=filepath.Join(tmp,"override");_ = os.MkdirAll(persisted,0o755);_ = os.MkdirAll(override,0o755)
	registry:=filepath.Join(tmp,"machine-roots.json");data,_:=json.Marshal(map[string]string{"SCENEX_ROOT":persisted});_ = os.WriteFile(registry,data,0o644)
	oldFile:=os.Getenv("OPENWORKER_MACHINE_ROOTS_FILE");oldSceneX:=os.Getenv("SCENEX_ROOT");defer os.Setenv("OPENWORKER_MACHINE_ROOTS_FILE",oldFile);defer os.Setenv("SCENEX_ROOT",oldSceneX)
	_ = os.Setenv("OPENWORKER_MACHINE_ROOTS_FILE",registry);_ = os.Setenv("SCENEX_ROOT",override)
	s:=Collect();for _,root:=range s.Roots{if root.Env=="SCENEX_ROOT"{want,_:=filepath.Abs(override);if root.Path!=filepath.Clean(want)||root.Source!="process-env"{t.Fatalf("unexpected override root: %#v",root)};return}};t.Fatal("SCENEX_ROOT inventory missing")
}

func TestParseRunnerServices(t *testing.T) {
	got:=parseRunnerServices("actions.runner.liuxb99-openworker.UL7\tRunning\tAuto\r\nactions.runner.liuxb99-openworker.ODA\tStopped\tAuto\r\n")
	if len(got)!=2{t.Fatalf("got %#v",got)}
	if got[0].Name!="actions.runner.liuxb99-openworker.ODA"||got[0].Running{t.Fatalf("unexpected first runner %#v",got[0])}
	if got[1].Name!="actions.runner.liuxb99-openworker.UL7"||!got[1].Running{t.Fatalf("unexpected second runner %#v",got[1])}
	if got[1].StartType!="Auto"{t.Fatalf("start type=%q",got[1].StartType)}
}
