package api

import (
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type artifact struct{Path string `json:"path"`;RelativePath string `json:"relative_path"`;Kind string `json:"kind"`;Size int64 `json:"size"`;SHA256 string `json:"sha256,omitempty"`;ModifiedAt time.Time `json:"modified_at"`;URL string `json:"url"`}

var artifactExt=map[string]string{".pdf":"document",".doc":"document",".docx":"document",".ppt":"presentation",".pptx":"presentation",".xls":"spreadsheet",".xlsx":"spreadsheet",".xlsm":"spreadsheet",".csv":"data",".json":"data",".jsonl":"data",".html":"report",".md":"report",".txt":"report",".log":"log",".png":"image",".jpg":"image",".jpeg":"image",".webp":"image",".svg":"image",".mp4":"video",".mov":"video",".mkv":"video",".webm":"video",".wav":"audio",".mp3":"audio",".dwg":"cad",".dxf":"cad",".dgn":"cad",".ifc":"bim",".rvt":"bim",".mct":"engineering",".s2k":"engineering",".op2":"engineering",".f06":"engineering",".obj":"3d",".fbx":"3d",".gltf":"3d",".glb":"3d",".stl":"3d",".blend":"3d",".zip":"archive",".7z":"archive"}
var ignored=map[string]bool{".git":true,".github":true,"node_modules":true,".venv":true,"venv":true,"__pycache__":true,".cache":true,"models":true}

func safeWithin(root,p string)bool{a,err:=filepath.Abs(root);if err!=nil{return false};b,err:=filepath.Abs(p);if err!=nil{return false};rel,err:=filepath.Rel(a,b);return err==nil&&rel!=".."&&!strings.HasPrefix(rel,".."+string(filepath.Separator))}
func hashFile(path string,size int64)string{if size>512*1024*1024{return ""};f,e:=os.Open(path);if e!=nil{return ""};defer f.Close();h:=sha256.New();if _,e=io.Copy(h,f);e!=nil{return ""};return fmt.Sprintf("%x",h.Sum(nil))}

func(s *Server)listArtifacts(w http.ResponseWriter,r *http.Request){work,err:=s.store.Get(r.PathValue("id"));if err!=nil{writeJSON(w,404,map[string]any{"error":"work not found"});return};root:=artifactRoot(work);out:=[]artifact{};scanned:=0
	_ = filepath.Walk(root,func(path string,info os.FileInfo,err error)error{if err!=nil{return nil};if info.IsDir(){if path!=root&&ignored[strings.ToLower(info.Name())]{return filepath.SkipDir};return nil};scanned++;if scanned>50000{return filepath.SkipAll};kind,ok:=artifactExt[strings.ToLower(filepath.Ext(path))];if !ok{return nil};rel,_:=filepath.Rel(root,path);out=append(out,artifact{Path:path,RelativePath:rel,Kind:kind,Size:info.Size(),SHA256:hashFile(path,info.Size()),ModifiedAt:info.ModTime().UTC(),URL:"/v1/work/"+work.WorkID+"/artifact?path="+strings.ReplaceAll(rel,"\\","/")});return nil})
	sort.Slice(out,func(i,j int)bool{return out[i].ModifiedAt.After(out[j].ModifiedAt)});writeJSON(w,200,map[string]any{"work_id":work.WorkID,"artifact_root":root,"files_scanned":scanned,"artifacts":out})}

func(s *Server)serveArtifact(w http.ResponseWriter,r *http.Request){work,err:=s.store.Get(r.PathValue("id"));if err!=nil{http.NotFound(w,r);return};root:=artifactRoot(work);rel:=r.URL.Query().Get("path");if rel==""{http.Error(w,"path required",400);return};full:=filepath.Clean(filepath.Join(root,filepath.FromSlash(rel)));if !safeWithin(root,full){http.Error(w,"path outside work root",403);return};st,err:=os.Stat(full);if err!=nil||st.IsDir(){http.NotFound(w,r);return};http.ServeFile(w,r,full)}
