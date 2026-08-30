package api

import (
    "net/http"
    "strings"
)

func (s *Server) dashboardV4(w http.ResponseWriter, r *http.Request) {
    ensureSelfUpgradeRoutes(s)
    w.Header().Set("Content-Type", "text/html; charset=utf-8")
    html := openworkerDashboardV3HTML
    html = strings.Replace(html, "</style>", versionWidgetCSS+"</style>", 1)
    html = strings.Replace(html, "<header>", "<header><button id=\"versionBadge\" class=\"version-badge checking\" onclick=\"versionBadgeClick()\" title=\"點擊檢查更新\">OpenWorker · 檢查版本…</button>", 1)
    html = strings.Replace(html, "</body>", versionWidgetJS+"</body>", 1)
    _, _ = w.Write([]byte(html))
}

const versionWidgetCSS = `
.version-badge{position:absolute;right:18px;top:12px;z-index:8;font-size:12px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;padding:6px 9px;border-radius:999px;max-width:58vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.version-badge.current{border-color:#166534;color:#86efac}.version-badge.update{border-color:#b45309;color:#fde68a;box-shadow:0 0 0 1px rgba(245,158,11,.15)}.version-badge.error{border-color:#7f1d1d;color:#fca5a5}.version-badge.checking,.version-badge.upgrading{color:#93c5fd}.version-badge.upgrading{border-color:#1d4ed8}@media(max-width:760px){.version-badge{position:static;max-width:100%;margin-bottom:8px}}
`

const versionWidgetJS = `<script>
let owVersionState=null,owVersionTimer=null,owUpgradeTimer=null,owUpgradeBusy=false;
function shortSha(v){v=String(v||'').trim();return v&&v!=='unknown'?v.slice(0,8):'unknown'}
function setVersionBadge(cls,text,title){const b=document.getElementById('versionBadge');if(!b)return;b.className='version-badge '+cls;b.textContent=text;b.title=title||text}
async function checkOpenWorkerVersion(){
 try{
  const [sr,gr]=await Promise.all([fetch('/v1/node/status',{cache:'no-store'}),fetch('https://api.github.com/repos/liuxb99/openworker/commits/main',{cache:'no-store',headers:{Accept:'application/vnd.github+json'}})]);
  if(!sr.ok)throw new Error('node status HTTP '+sr.status);if(!gr.ok)throw new Error('GitHub HTTP '+gr.status);
  const s=await sr.json(),g=await gr.json();const current=String((s.service&&s.service.running_commit)||(s.build&&s.build.commit)||'unknown');const latest=String(g.sha||'');const version=String((s.build&&s.build.version)||'OpenWorker');const verified=!!(s.service&&s.service.upgrade_verified);const available=!!latest&&current!=='unknown'&&current.toLowerCase()!==latest.toLowerCase();
  owVersionState={machine:s.machine,current,latest,version,verified,available};
  if(available)setVersionBadge('update','OpenWorker '+version+' · '+shortSha(current)+' → '+shortSha(latest)+' · 可升級','點擊後由本機 OpenWorker 自動升級並等待 VERIFIED');
  else setVersionBadge('current','OpenWorker '+version+' · '+shortSha(current)+' · '+(verified?'VERIFIED · ':'')+'已是最新版','目前 running commit 與 GitHub main 一致。點擊重新檢查。');
 }catch(e){if(!owUpgradeBusy)setVersionBadge('error','OpenWorker · 版本檢查失敗',String(e));}
}
async function versionBadgeClick(){
 if(owUpgradeBusy)return;
 await checkOpenWorkerVersion();
 if(!owVersionState||!owVersionState.available)return;
 if(!confirm('將 OpenWorker 本機自動升級到 '+shortSha(owVersionState.latest)+'。升級期間服務會短暫重啟，確定繼續？'))return;
 owUpgradeBusy=true;setVersionBadge('upgrading','OpenWorker · 啟動升級…','本機升級已開始');
 try{
  const r=await fetch('/v1/node/upgrade',{method:'POST',cache:'no-store'}),x=await r.json();
  if(!r.ok)throw new Error(x.error||('HTTP '+r.status));
  const target=String(x.target_commit||owVersionState.latest||'');
  pollUpgrade(target,0);
 }catch(e){owUpgradeBusy=false;setVersionBadge('error','OpenWorker · 升級啟動失敗',String(e));}
}
async function pollUpgrade(target,n){
 if(owUpgradeTimer)clearTimeout(owUpgradeTimer);
 try{
  const [ur,sr]=await Promise.all([fetch('/v1/node/upgrade',{cache:'no-store'}),fetch('/v1/node/status',{cache:'no-store'})]);
  const u=ur.ok?await ur.json():{};const s=sr.ok?await sr.json():{};const running=String((s.service&&s.service.running_commit)||(s.build&&s.build.commit)||'');const verified=!!(s.service&&s.service.upgrade_verified);
  if(target&&running.toLowerCase()===target.toLowerCase()&&verified){owUpgradeBusy=false;setVersionBadge('current','OpenWorker '+String((s.build&&s.build.version)||'')+' · '+shortSha(running)+' · VERIFIED · 已是最新版','升級完成並通過 running commit 驗證');setTimeout(()=>location.reload(),1200);return;}
  const phase=String(u.phase||'').toUpperCase();if(phase==='FAILED'){owUpgradeBusy=false;setVersionBadge('error','OpenWorker · 升級失敗',String(u.message||'upgrade failed'));return;}
  const names={STARTED:'啟動中',DOWNLOADING:'下載新版',LOCATING_GO:'準備編譯環境',TESTING:'執行測試',BUILDING:'編譯新版',INSTALLING:'安裝並重啟服務',WAITING_VERIFIED:'等待 VERIFIED',IDLE:'準備中'};
  setVersionBadge('upgrading','OpenWorker · '+(names[phase]||'升級中')+'… · '+shortSha(target),'升級狀態：'+(phase||'reconnecting'));
 }catch(e){setVersionBadge('upgrading','OpenWorker · 服務重啟中… · '+shortSha(target),'等待 8787 恢復連線');}
 if(n>180){owUpgradeBusy=false;setVersionBadge('error','OpenWorker · 升級驗證逾時','請檢查 C:\\ProgramData\\OpenWorker\\upgrade\\last.json');return;}
 owUpgradeTimer=setTimeout(()=>pollUpgrade(target,n+1),2000);
}
setTimeout(()=>checkOpenWorkerVersion(),100);owVersionTimer=setInterval(()=>{if(!owUpgradeBusy)checkOpenWorkerVersion()},300000);
</script>`
