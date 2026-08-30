# 0001 — UL7 routing / readiness / formal execution-boundary evidence

## 1. Step 目的

證明 Case 0003 固定執行主機 UL7 可被 self-hosted GitHub Actions 接單，並確認後續 consequential work 必須由 OpenWorker persisted binding + go-tool formal operator layer 控制，而不是由案例 workflow 自己 checkout / build / 猜工具入口。

Canonical input：

- case：`0003`
- location：`臺南市玉井橋`
- assigned host：`DESKTOP-UL7V2VV`
- canonical workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- case mirror：`D:\AI-Example\0003`

## 2. 歷史 routing 嘗試

### 2.1 錯誤做法：把 `UL7` 當 runner label

最初 workflow 使用：

`runs-on: [self-hosted, Windows, X64, UL7]`

run `31919878274` / job `95097918048` 長時間 queued。後續確認 `UL7` 是機器簡稱，不是正式 runner label。

結論：**不得把人的機器簡稱猜成 GitHub runner label。**

### 2.2 改為共享 labels + COMPUTERNAME gate

workflow 改用 `[self-hosted, Windows, X64]` transport fan-out，再檢查：

`COMPUTERNAME == DESKTOP-UL7V2VV`

修正 commit：`22379efa04b55020508d2a3aced418714af0bdc6`。

後續又修了 docs push 自動取消 active run 與 static concurrency 堵塞問題：

- `0956ca74f796e66eb974ca91f25ee0229f54ab3c`
- `b0a059647ed0ebb8d314dcecbbaa397ef8126933`

這些修復保留為歷史 evidence，但它們只處理 transport，不是最終 machine/workspace authority。

## 3. UL7 REAL 可用證據 — supersedes 舊 offline 結論

2026-08-16 cross-repo readiness run：

- workflow run：`31921072421`
- UL7 job：`95100919549` (`readiness (4)`)
- runner：`DESKTOP-UL7V2VV-R002`
- machine：`DESKTOP-UL7V2VV`
- runner version：`2.336.0`
- identity output：`CASE0003_UL7_IDENTITY_PASS`

因此先前「UL7 runner offline / unavailable」診斷已被本次 REAL run 明確推翻。

Accepted fact：

`UL7 online + registered + accepting self-hosted jobs`

## 4. run 31921072421 真正 failure

UL7 已通過 identity gate，並成功 checkout `liuxb99/openworker` main。當時 OpenWorker checkout SHA：

`8316ad1f6f4c1d715d943e1572a1d4277d3fb3d8`

接著外層診斷 workflow 嘗試：

`actions/checkout@v4 repository: liuxb99/go-tool-runtime`

GitHub 回覆：

`remote: Repository not found.`

並以 exit code `128` 失敗。

當次 `GITHUB_TOKEN` 權限只顯示：

- Contents: read
- Metadata: read
- Packages: read

這是來源 workflow repository token 的 scope，不能把它當成跨 private repo operator credential。

## 5. Root cause correction

舊診斷：

`UL7 offline-or-unavailable`

已廢止。

新 root cause：

`Case 0003 diagnostic workflow bypassed go-tool-runtime formal credential / capability dispatch layer and attempted direct private cross-repo checkout.`

Gap id：`G-0003-004`。

## 6. 最新 go-tool 設計提供的正確做法

go-tool-runtime 已正式實作：

- Thin Capability Registry
- canonical input schema
- readiness
- GitHub Actions workflow_dispatch provider
- stable execution id `<capability_id>:<workflow_run_id>`
- run status / jobs / runner metadata / artifacts / cancel
- evidence contract

最新 config 的 Action authentication：

- `auth_mode: auto`
- priority：local shared credential DB → GitHub App → token env
- shared credential DB：`C:\ProgramData\go-tool-runtime\runtime.db`
- key：`GH_TOKEN`

設計目的就是讓本機 interactive bootstrap 與 self-hosted runner service accounts 共用安全 credential，而不是在每個外層 case workflow 自己跨 private repo checkout。

## 7. OpenWorker machine/workspace authority

Case 0002 已驗證 persisted JobBinding 模式；Case 0003 繼承同一規則：

- assigned host：`DESKTOP-UL7V2VV`
- workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- mirror：`D:\AI-Example\0003`
- binding file：`<workspace>\.openworker\job-binding.json`

Action matrix / runner labels 只是 transport。真正 authority 是 OpenWorker persisted job binding；wrong-host candidate 必須 clean skip / fail closed，不能執行 consequential work。

## 8. Accepted Step 1 procedure

後續不得再使用「案例 workflow checkout 所有 private tooling repo 然後自己執行」的做法。

Accepted procedure：

`OpenWorker current project/job state → persisted JobBinding → UL7 existing go-tool-runtime → AgentInformationPack/current facts → capability discovery/detail/schema/readiness → go-tool queue preflight/formal dispatch → owning repo Operator Action → go-tool run/jobs/artifacts query → OpenWorker ledger/evidence`

## 9. Step 1 verdict

- UL7 routing identity：`PASS`
- self-hosted Action boundary：`PASS`
- old direct cross-repo checkout approach：`REJECTED`
- go-tool formal execution layer required：`ACCEPTED`
- canonical workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- overall Step 1：`PASS WITH ORCHESTRATION CORRECTION`

## 10. Next Step

Step 2：用 UL7 上最新版 go-tool 做正式 capability discovery。

已知新的候選缺口：`Terrain_To_DXF` main 已有 Street View metadata / snapshot / route scan / high-resolution tiles / panorama stitch 等能力，但 go-tool registry 目前只明確看到 `terrain.dxf.generate`，所以要確認 Street View / location 能力是否已有 Operator workflow；若沒有，補 owning repo + go-tool registry，再由 UL7 本機 Action 重跑 Step 2。
