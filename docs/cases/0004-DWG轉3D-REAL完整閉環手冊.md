# 案例 0004：使用者 DWG → 3D REAL 完整閉環手冊

> 主責位置：`liuxb99/openworker`
>
> 執行治理：`liuxb99/AI-Engineering-OS`
>
> 工具資訊控制面：`liuxb99/go-tool-runtime`
>
> DWG owning repo：`liuxb99/DWG_todo`（default branch：`master`）
>
> 指定 REAL 主機：`DESKTOP-O87PJNR`（O87）
>
> 更新時間：2026-08-16 14:28（Asia/Taipei）
>
> 狀態：`IMPLEMENTING / REAL USER DWG RECEIVED / OPENWORKER PROJECT EXECUTION NEXT`
>
> 目標：由 OpenWorker 真正接手一個使用者 DWG→3D 專案。OpenWorker 不硬編碼整條案例流程，而是讀 AI-Engineering-OS 專案狀態、查 go-tool-runtime 知道目前可用工具與正式 Action，再逐步操作 DWG_todo / OpenCADStudio / Blender，驗證真實成果並回寫 OS Artifact / Review / Delivery。案例文件同時作為「實作紀錄」與後續可重做的「操作手冊」。

---

## 0. 手冊定位與紀錄鐵律

本文件不是只有架構說明，也不是完成後補寫的摘要。

從案例 0004 開始，每個 REAL case 的文件必須同時包含：

1. **操作手冊**：下一個工程師或 Agent 可以照文件從零重做。
2. **實際執行紀錄**：本次案例每一步實際做了什麼，不能只寫「已完成」。
3. **決策紀錄**：OpenWorker 為什麼選這個工具、這個輸入、這個樓層或這組 geometry。
4. **工具查詢紀錄**：每次使用工具前，記錄 go-tool-runtime 查到的正式 capability / repo / workflow / inputs / runner / success criteria。
5. **Action 紀錄**：workflow、run、job、runner、commit/ref、normalized inputs、status/conclusion。
6. **成果紀錄**：physical path、size、SHA256、格式、reopen/QC 結果。
7. **缺口紀錄**：哪一步失敗、真實錯誤、屬於哪個 owning repo、修復 commit。
8. **重跑紀錄**：修完後沿同一路徑重跑，不得換 mock 或 fixture 繞過。
9. **目前狀態**：current stage、blocker、next action。
10. **完成定義**：只有真實產品鏈全部通過才能標 `REAL CLOSED`。

### 0.1 每一步固定紀錄格式

後續所有 Step 都用以下模板追加實際紀錄：

```text
[STEP-ID]
時間：YYYY-MM-DD HH:mm:ss +08:00
狀態：PENDING / RUNNING / PASS / FAIL / BLOCKED / REPAIRED

目的：
本步要解決什麼問題。

前置狀態：
OS ProjectID / JobID
OpenWorker JobBinding
workspace
assigned_host
source revision / artifact revision

OpenWorker 判斷：
看到了什麼 evidence
為什麼決定做這一步
為什麼選這個工具，而不是其他工具

Go Tool 查詢：
query / capability id
going repo
workflow
ref
canonical inputs
runner / assigned-host rule
workspace rule
success criteria
failure evidence

正式執行：
repository
workflow
run_id
job_id
runner
head_sha
normalized inputs（不記 secret）

輸出：
physical path
size
SHA256
format/version
相關 manifest / evidence

驗證：
exists/non-zero
parse/reopen
geometry/QC
是否符合 success criteria

結果：
PASS / FAIL

若 FAIL：
failed job/step
error 摘要
owning repo
修復 commit
重跑 run/job

下一步：
下一個必要動作。
```

### 0.2 不允許省略的欄位

凡是經過 GitHub Action 的產品步驟，至少記：

```text
repo
workflow
ref/head_sha
run_id
job_id
runner
status/conclusion
normalized inputs
```

凡是產生檔案，至少記：

```text
canonical path
physical exists
byte size
SHA256
format/version
reopen/parse result
```

凡是由 OpenWorker / 大模型作出工程判斷，至少記：

```text
觀察到的 evidence
候選方案
選擇結果
選擇理由
對應原始 DWG handle/layer/crop 或其他 provenance
```

---

## 1. 系統角色：誰負責什麼

### 1.1 OpenWorker

OpenWorker 是案例 0004 的實際專案 operator。

它負責：

```text
讀 OS Project/Job 狀態
→ 查 go-tool-runtime
→ 選下一個正式工具
→ 派送 owning repo Action
→ 查 run/jobs/logs/artifacts
→ 看工具輸出與影像 evidence
→ 決定下一個工程步驟
→ 把 accepted/blocked/repaired 狀態寫回 ProjectKnowledge
```

OpenWorker **不得**自己寫第二套 DWG parser、3D converter 或 Blender pipeline。

### 1.2 AI-Engineering-OS

OS 是 canonical 專案治理層，負責：

- Project / Job；
- canonical workspace；
- Artifact Registry；
- Review；
- Delivery Revision；
- current revision semantics。

### 1.3 go-tool-runtime

go-tool-runtime 是 AI 工具資訊控制面，不取代產品工具。

OpenWorker 在每個新階段都先查 go tool，取得：

```text
capability id
owning repo
workflow
ref
canonical inputs
runner/assigned host rule
workspace rule
artifact/evidence contract
success criteria
failure evidence
```

然後 OpenWorker 再自己派送 owning repo 的 Action。

### 1.4 DWG_todo / OpenCADStudio / Blender

`DWG_todo` 是 DWG 產品邏輯 owning repo，負責：

- DWG open / inspect / render；
- candidate region / story region；
- structural story design；
- reviewed materialization；
- story anchors / registration；
- Building World Coordinates；
- production GLB；
- native ACIS Solid3D DWG。

OpenCADStudio 負責 native DWG 讀寫與 reopen；Blender 負責 production GLB 的真實 import/reopen/render 驗證。

### 1.5 GitHub Actions

GitHub Actions 是 OpenWorker 操作本機工具的 transport，不是案例本身的「大腦」。

REAL 業務結果來自 O87 本機工具；GitHub artifact quota 錯誤只屬 evidence upload 問題，不能取代本機 physical gate。

---

## 2. 全鏈

```text
User uploads REAL DWG
→ AI-Engineering-OS canonical Project / Job / Workspace
→ immutable source input
→ OpenWorker JobBinding / ProjectKnowledge
→ OpenWorker 查 go-tool-runtime
→ OpenWorker 派送 DWG_todo 正式 Action
→ raw DWG inspect / render / overview
→ repeated crop / story-region recognition
→ structural story design + review
→ materialize to job-scoped llmCAD
→ story anchors / registration
→ Building World Coordinates
→ production GLB
→ Blender 5.2 REAL reopen + render
→ native ACIS Solid3D DWG build
→ OpenCAD DwgReader reopen / 3DSOLID validation
→ canonical artifacts + evidence
→ AI-Engineering-OS Artifact Registry
→ Review current revisions
→ Delivery Revision
→ delivery package / website
```

案例主要 3D 成果至少同時有：

- `building.glb`；
- `building-3d.dwg`：AC1032 native DWG + ACIS `3DSOLID`；
- Blender reopen/render screenshot；
- native DWG inspect/reopen evidence；
- 每個重要產物的 SHA256 / size / canonical path。

---

## 3. O87 固定執行 contract

固定 REAL 主機：

```text
CASE0004_ASSIGNED_HOST=DESKTOP-O87PJNR
```

產品步驟開始前必須驗證：

```text
COMPUTERNAME == DESKTOP-O87PJNR
OpenWorker JobBinding.assigned_host == DESKTOP-O87PJNR
```

任一不一致立即 fail closed。

Runner management API 目前透過 GitHub connector 查 repository self-hosted runner labels 會得到 403，因此案例不能假裝已確認 `O87` label 一定存在。

目前真實已知 evidence：DWG_todo 的 `DWG OpenCAD Adapter Gate` Run `31927824825` 曾在 O87 runner `DESKTOP-O87PJNR-R009` 成功執行，證明 O87 確實有可工作的 self-hosted runner。

正式 routing 原則：

- 能使用 O87 專屬 label 時，使用 `[self-hosted, Windows, X64, O87]`；
- 無法從管理 API確認 label 時，仍必須用 `COMPUTERNAME` + OpenWorker `assigned_host` fail-closed；
- 搶到非 O87 後 skip 的 job 不能算產品成功。

---

## 4. Canonical OS workspace

正式工作區：

```text
D:\AI-Work\jobs\0004-DWG-TO-3D
```

展示/鏡像區：

```text
D:\AI-Example\0004
```

建議來源結構：

```text
D:\AI-Work\jobs\0004-DWG-TO-3D\
  input\
    source.dwg
    secondary.dwg
    source-provenance.json
  dwg\
    agent-cad-state.json
    exports\
  3d\
  evidence\
  delivery\
```

`input/source.dwg` 是本案例主輸入；第二份真實圖不覆寫主圖，而作為 secondary / compatibility regression source。

---

## 5. REAL 使用者輸入登記

2026-08-16 使用者已提供兩份真實 DWG，不再是 `WAITING_FOR_REAL_DWG_INPUT`。

### 5.1 主案例輸入

原始檔名：

```text
S1-1140926(1).dwg
```

本次聊天接收檔案：

```text
/mnt/data/S1-1140926(1).dwg
```

實體 gate：

```text
DWG header/version: AC1032
size: 1,385,583 bytes
SHA256: aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
```

案例用途：

```text
PRIMARY REAL SOURCE
→ materialize 到 O87 canonical workspace input/source.dwg
→ 全鏈 DWG→3D REAL 驗證
```

選為主案例理由：來源本身已是 AC1032，與案例 native 3D DWG target AC1032 相同；這不是成功條件，只是能減少版本轉換變因。幾何與內容仍必須由 OpenWorker / DWG_todo 真實 inspect 後判斷。

### 5.2 第二份真實輸入

原始檔名：

```text
378建照圖(核准版) (1)(1).dwg
```

本次聊天接收檔案：

```text
/mnt/data/378建照圖(核准版) (1)(1).dwg
```

實體 gate：

```text
DWG header/version: AC1018
size: 1,435,765 bytes
SHA256: 1ce944040d1001cd06ef15c7f8fc815bcf68cf196c3bffc22de61cd8f15d0fd6
```

案例用途：

```text
SECONDARY REAL SOURCE
→ 不與 primary geometry 混合
→ 主案例閉環後做 AC1018 輸入相容性 / regression 驗證
```

### 5.3 Input gate 完成與未完成項

已完成：

- 兩份檔案 physical exists；
- size > 0；
- SHA256；
- DWG header/version；
- primary / secondary 用途已分離。

尚未完成：

- O87 canonical workspace materialization；
- OS Project / Job 建立或綁定；
- OpenWorker JobBinding；
- O87 上重新計算 SHA256 並與聊天接收值比對。

因此目前 Step A 狀態為：

```text
REAL SOURCE RECEIVED / LOCAL INTAKE PASS / WAITING FOR OS+OPENWORKER MATERIALIZATION
```

---

## 6. go-tool-runtime 查工具規則

OpenWorker 不靠記憶猜工具。

每到新階段，先依 go-tool-runtime `SKILL.md` 的 AI Operator 流程：

```text
GET /health
POST /api/workspace/bootstrap（需要時）
GET /api/information/readiness
GET /api/execution/capabilities 或 Tool Search
GET /api/execution/capabilities/{id}
```

或以 Tool Search 搜尋 `dwg` / `cad` / `building 3d` 等能力。

已知 AI-facing DWG guides 至少包括：

```text
0003 dwg.cad.execute
0004 dwg.cad.3d
0005 dwg.cad.visual-search
0006 dwg.cad.story-design
0007 dwg.cad.story-materialize
0008 dwg.cad.story-registration
0009 dwg.cad.building-3d
0010 dwg.cad.building-dwg
```

每次真正使用前仍要查 runtime 最新資訊，不能僅引用本文件。

---

## 7. Step A：OS Project / Job / Workspace / Source materialization

### 7.1 目的

把聊天收到的 primary REAL DWG 變成 AI-Engineering-OS 管理的 immutable canonical source。

### 7.2 OpenWorker 必做

1. 取得/建立 Case 0004 OS Project；
2. 建 Job；
3. workspace 固定 `D:\AI-Work\jobs\0004-DWG-TO-3D`；
4. assigned_host 固定 `DESKTOP-O87PJNR`；
5. materialize primary source 到 `input/source.dwg`；
6. secondary source 到 `input/secondary.dwg`；
7. O87 本機重新計算 size/SHA256；
8. 與第 5 節聊天接收值完全一致；
9. 建 OpenWorker JobBinding；
10. ProjectKnowledge 記錄 source、stage、next action。

### 7.3 Acceptance

```text
input/source.dwg exists
size == 1,385,583
SHA256 == aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
OS ProjectID / JobID exists
OpenWorker JobBinding exists
assigned_host == DESKTOP-O87PJNR
```

任何 hash 不一致立即 fail closed。

### 7.4 實際執行紀錄

```text
狀態：PENDING
原因：REAL source 已收到，但尚未由 OpenWorker/OS materialize 到 O87 canonical workspace。
下一步：OpenWorker 建/綁 OS Project/Job，完成 source materialization。
```

---

## 8. Step B：OpenWorker 查 go tool → Raw DWG inspection

### 8.1 目的

先理解 DWG，不直接開始建模。

### 8.2 工具選擇規則

OpenWorker 先查 go-tool-runtime，取得最新 `dwg.cad.execute` / visual-search capability 契約，再派 `DWG_todo/.github/workflows/operator-dwg-cad.yml`。

預期會用到的方法：

```text
cad.open_dwg
cad.get_model_extents
cad.render_png
cad.list_candidate_regions
cad.query_bounds
cad.query_entities
```

### 8.3 必須記錄的人工/模型判斷

- 整張 Model Space extent；
- layer/entity inventory；
- candidate regions；
- 每次 crop/window 的 bounds；
- 看到了哪些樓層圖、平面圖、剖面或無關區域；
- 為什麼選某一區作 Story Region；
- 每個判斷對應的 PNG / handle / layer evidence。

### 8.4 禁止

不允許：

```text
只看一次全圖就猜整棟 geometry
只靠檔名猜樓層
沒有 handle/layer/crop provenance 就 materialize 結構
```

### 8.5 實際執行紀錄

```text
狀態：PENDING
下一步：Step A 完成後，由 OpenWorker 查 go tool 最新契約並派第一個 raw inspection Action。
```

---

## 9. Step C：Story Region / Structural Recognition / Design

每個樓層重複：

```text
選 Story Region
→ query bounds/entities
→ 確認 column handles
→ cad.design_story_structure
→ 產生 design.json + design.png
→ OpenWorker 查看 design evidence
→ 決定 approve/reject
```

每一個 column / primary beam / secondary beam 都要保存：

- source handle / layer；
- recognized section dimensions；
- section authority/provenance；
- Story Design object ID；
- design SHA256。

OpenWorker 必須在文件中寫清楚「為什麼批准」，不是只有 `approved=true`。

---

## 10. Step D：Reviewed materialization

正式方法：

```text
cad.materialize_story_structure
```

要求：

- review 通過才 materialize；
- job-scoped llmCAD authoritative state；
- exact retry 必須 idempotent；
- stale revision / hash mismatch fail closed；
- materialize 後 query_entities 回讀。

已有 focused gate evidence：

```text
Workflow: DWG OpenCAD Adapter Gate
Run: 31927824825
Commit: a93540515fa10c422143a88f9d2999dd4cbd80ac
Runner: DESKTOP-O87PJNR-R009
Conclusion: SUCCESS
```

但該 gate 是 fixture/regression，不是案例 0004 REAL product evidence；案例仍要對使用者真圖重做。

---

## 11. Step E：Story Anchors / Registration / Building World Coordinates

正式能力：

```text
cad.set_story_anchor
cad.list_story_anchors
cad.register_stories
cad.validate_story_registration
cad.list_story_registrations
```

每一個 registration 必須記：

- reference story；
- shared anchors；
- source/target coordinates；
- RMS residual；
- max residual；
- transform；
- story elevation/Z；
- validation conclusion。

如果無法可信配準，fail closed，不可為了出 3D 強行合併。

---

## 12. Step F：Building 3D → Production GLB

正式方法：

```text
cad.build_building_3d
cad.export_building_glb
cad.validate_building_3d
```

必須記：

- Building World manifest；
- story count；
- structural object counts；
- world bounds；
- GLB path / size / SHA256；
- validation report。

GLB 不是最終閉環，只是其中一個產品。

---

## 13. Step G：Blender 5.2 REAL reopen / render

O87 必須真實執行 Blender 5.2：

```text
bpy.ops.import_scene.gltf
mesh_object_count >= 1
world bounding box valid
headless render succeeds
render PNG exists and size > 0
```

手冊記錄：

```text
Blender executable/version
import result
mesh_object_count
world bounds
render path
render size
render SHA256
reopen/report path + SHA256
```

OpenWorker 還要看 render，確認不是空景、極端縮放、全部物件重疊或明顯 geometry 爆炸。

---

## 14. Step H：Native ACIS Solid3D DWG REAL

正式方法：

```text
cad.build_building_dwg
cad.export_building_dwg
cad.validate_building_dwg
```

正式 native path：

```text
Building World Coordinates
→ opencad-3d-dwg-build/v1 manifest
→ OpenCADStudio --build-3d-dwg
→ acadrust primitives::build_box
→ ACIS Solid3D SAT
→ DwgWriter AC1032
→ physical .dwg
→ DwgReader reopen
→ OpenCAD inspect/reopen
→ 3DSOLID / layer counts / SHA256 validation
```

Acceptance：

1. `.dwg` physical exists / non-zero；
2. AC1032；
3. representation = solid；
4. DwgReader reopen 成功；
5. expected structural operations 均 reopen；
6. `3DSOLID` count == solid operation count；
7. layer entity counts 一致；
8. second validate/reopen PASS；
9. DWG / manifest / inspect / evidence 均記 SHA256。

歷史 REAL run：

```text
Workflow: DWG Building 3D DWG REAL
Run: 31929525959
Job: 95122140673
Runner: DESKTOP-UL7V2VV-R002
Conclusion: failure
Error: missing field `x` at line 18 column 7
```

這筆歷史只作缺口背景，不能算案例 0004 成功。案例必須用最新 `DWG_todo/master` + O87 + 使用者真圖重跑。

---

## 15. Step I：AI-Engineering-OS Artifact Registry

至少註冊：

```text
source-dwg
secondary-source-dwg
building-world-model / manifest
building-glb
blender-reopen-report
blender-render-png
building-native-3d-dwg
native-dwg-inspect
native-dwg-validation-evidence
```

每個 artifact 至少保存：

```text
ProjectID
JobID
ComponentID
Kind
Revision
canonical path
size
SHA256
provenance / producing execution
current revision semantics
```

---

## 16. Step J：Review / Delivery Revision

Review 僅針對 `(component_id, kind)` 最新 current revision 做 approval gate；歷史 rejected/rework revision 保留，但不得阻塞已被取代的 current approved revision。

Delivery 前要求：

- source provenance PASS；
- Building World / GLB validation PASS；
- Blender visual/reopen PASS；
- native 3D DWG reopen PASS；
- current artifacts approved；
- 建立 Delivery Revision。

最終 package：

```text
source/source.dwg
source/secondary.dwg
3d/building.glb
3d/building-3d.dwg
evidence/blender-render.png
evidence/blender-reopen.json
evidence/native-dwg-inspect.json
evidence/native-dwg-validation.json
delivery/website/index.html
```

---

## 17. 缺口 / 修復 / 重跑流水帳格式

每發現一次真正產品缺口，在本節追加，永遠不覆寫舊歷史：

```text
### GAP-0004-NNN
發現時間：
Stage：
Run/Job：
Runner：
Symptom：
Exact error：
Evidence：
Owning repo：
Root cause：
Repair commit：
Regression test：
Rerun Run/Job：
Result：
Remaining risk：
```

原則：

```text
發現缺口
→ 修 owning repo
→ 加永久 regression
→ 推正式 branch
→ 用相同 REAL source、相同 stage、相同 acceptance 重跑
```

不得換 fixture 讓測試變綠就結案。

---

## 18. 每批開發後的進度更新格式

每完成一批，文件最前面的狀態與本節同步更新：

```text
更新時間：
Current stage：
Latest accepted evidence：
Latest run/job：
Latest runner：
Latest product artifact：
Current blocker：
Owning repo if blocked：
Next action：
```

若正在 running：寫 `RUNNING`；若只是 queued：寫 `QUEUED`。不得把 queued/running 說成完成。

---

## 19. 案例 0004 完成定義

只有以下全部完成才能標記：

```text
REAL CLOSED / MANUAL REPRODUCIBLE
```

必須同時滿足：

- 使用者真實 primary DWG 已由 OS canonical workspace 接收；
- source SHA256 與原始接收值一致；
- 全部 consequential REAL work 在 O87；
- OpenWorker 每個階段先查 go-tool-runtime，不猜工具；
- raw DWG 真實 open/inspect/render；
- 真實 Story Region / structural recognition；
- Story Design review/materialize；
- registration / Building World Coordinates；
- production GLB；
- Blender 5.2 REAL reopen/render；
- native ACIS Solid3D DWG；
- DwgReader/OpenCAD second reopen + 3DSOLID/layer validation；
- OS Artifact Registry；
- Review current revisions；
- Delivery Revision；
- delivery package / website；
- 本手冊每一步都有足夠 evidence 可重做。

任何 fixture-only、mock、skip-only、metadata-only、JSON-only、GLB-only、renamed file 都不得算案例完成。

---

## 20. 目前實際進度（2026-08-16 14:28 +08:00）

### 已完成

1. 建立 Case 0004 canonical manual。
2. 架構確認為：`OS 管專案 → OpenWorker 真正做專案 → go-tool 查工具 → owning repo Action 做產品`。
3. 固定 REAL 主機：`DESKTOP-O87PJNR`。
4. 使用者提供兩份 REAL DWG。
5. 已完成兩份檔案的 header / size / SHA256 intake gate。
6. 已指定 `S1-1140926(1).dwg` 為 primary，`378建照圖(核准版) (1)(1).dwg` 為 secondary regression source。
7. 已確認 go-tool-runtime `SKILL.md` 明確要求 Agent 先查 runtime，再操作 owning repo Action，而不是把 go tool 當業務代理。

### 尚未完成

1. OS Project / Job / canonical workspace materialization。
2. OpenWorker JobBinding。
3. O87 本機 source SHA revalidation。
4. OpenWorker 對 primary DWG 的第一次 go-tool query。
5. raw DWG inspection/render。
6. Story Design → 3D → Blender → native 3D DWG → OS Delivery 全鏈。

### Current stage

```text
STEP A
REAL SOURCE RECEIVED
WAITING FOR OPENWORKER + OS CANONICAL PROJECT MATERIALIZATION
```

### 下一步

不是直接手寫一條 Case 0004 硬編碼 driver。

下一步應由 OpenWorker：

```text
1. 建/綁 Case 0004 OS Project/Job
2. 建立 O87 JobBinding
3. materialize primary/secondary DWG 到 canonical workspace
4. 驗證 SHA256
5. 查 go-tool-runtime 的 DWG capability / readiness / canonical inputs
6. 依 go tool 回覆派第一個 DWG_todo raw-inspection Action
7. 把 run/job/runner/output/evidence/判斷完整追加回本手冊
```
