# 案例 0004：DWG → 3D REAL 逐步操作紀錄 / 未來手冊原稿

> 案例主責：`liuxb99/openworker`  
> OS 治理：`liuxb99/AI-Engineering-OS`  
> 工具資訊平面：`liuxb99/go-tool-runtime`  
> CAD owning repo：`liuxb99/DWG_todo`  
> 固定 REAL 主機：`DESKTOP-O87PJNR`（O87）  
> 開始時間：2026-08-16（Asia/Taipei）  
> 最後同步：2026-08-17 15:58（Asia/Taipei）  
> 狀態：`IMPLEMENTING / CASE WORKLIST GOVERNED / LOCATOR REPAIR IN PROGRESS`

---

## 0. 這份文件怎麼使用

這不是只寫「做到哪裡」的摘要，而是案例完成後要整理成正式操作手冊的原始紀錄。

**從現在開始，每一步都必須記：**

```text
Step / 時間
目的
OpenWorker 當下已知狀態
OpenWorker 為什麼選這個下一步
go-tool-runtime 查詢內容
查到的 capability / owning repo / workflow / ref
normalized inputs
workspace_root / assigned_host
GitHub Action run id / job id / runner
產品輸出 physical path
size / SHA256 / schema / revision
OpenWorker 對輸出的判讀
驗收 PASS / FAIL / BLOCKED
若 FAIL：真正 owning repo / root cause / 修復 commit
修復後同一路徑 rerun evidence
下一步
```

不得只記「成功」；也不得把 fixture、skip、metadata-only、artifact upload 成功當產品成功。

案例原則：

```text
OpenWorker 真正做專案
→ 不知道工具就查 go-tool-runtime
→ 使用 owning repo 正式 Action
→ 看真實輸出再決定下一步
→ 工具有缺口就修真正 owning repo
→ 回同一份真 DWG / 同一 workspace / 同一 O87 路徑重跑
→ 直到 OS Artifact / Review / Delivery 閉環
```

從 2026-08-17 起增加第二條治理鐵律：

```text
案例狀態不能只存在聊天或 GitHub Actions 歷史中。
每個已完成、失敗、修復、重跑的動作，都必須同步到：
1. O87 workspace 內 canonical CaseWorklist；
2. 本逐步操作紀錄；
3. 穩定後再提煉回 REAL 完整閉環手冊。
```

---

# Part A — 真實輸入接收

## Step A-001｜2026-08-16｜使用者提供兩份真實 DWG

### 使用者輸入

本次對話收到：

```text
378建照圖(核准版) (1)(1).dwg
S1-1140926(1).dwg
```

這兩份均為使用者真實上傳，不是 repository fixture。

### Physical input gate

#### Input 1

```text
filename: 378建照圖(核准版) (1)(1).dwg
size: 1,435,765 bytes
role: backup compatibility source
```

保留為第二份 REAL compatibility / regression case，不與主案例 geometry 混合。

#### Input 2 — Case 0004 主輸入

```text
filename: S1-1140926(1).dwg
DWG header: AC1032
size: 1,385,583 bytes
SHA256: aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
basic gate: PASS
role: PRIMARY REAL SOURCE
```

選它作主案例的原因：

1. 是真實使用者檔案；
2. header 為 `AC1032`，與 Case 0004 native Building 3D DWG 最終 delivery target 一致；
3. 先用一份 source 完整閉環，避免兩份圖的 geometry / story / provenance 被混用；
4. 第一份保留作閉環後的第二檔案相容性回歸。

### Canonical Case 0004 目標位置

```text
workspace_root = D:\AI-Work\jobs\0004-DWG-TO-3D
assigned_host  = DESKTOP-O87PJNR
canonical source = D:\AI-Work\jobs\0004-DWG-TO-3D\input\source.dwg
```

---

# Part B — OpenWorker 先查 go tool，不靠模型記憶

## Step B-001｜查詢 go-tool-runtime 使用規範

OpenWorker/操作者先讀 `go-tool-runtime/SKILL.md`，確認正式操作模式：

```text
LLM / OpenWorker
→ query go-tool-runtime
→ obtain capability / owning repo / workflow / inputs / runner / evidence
→ dispatch owning repo Action
→ self-hosted tool executes REAL work
→ inspect run/jobs/logs/physical artifacts
→ validate
```

重要邊界：go-tool-runtime 是資訊/Action guidance plane，不取代 `DWG_todo` 做 CAD。

## Step B-002｜查 `dwg.cad.execute` 主入口

查到 owning repo 為 `liuxb99/DWG_todo`，並確認 Building 3D / native DWG family 已存在。

### 發現缺口 GTR-0001

舊 guide 與 runtime registry 有資訊漂移；OpenWorker 可能只看到舊 generic methods。

### 修復

```text
repo: liuxb99/go-tool-runtime
commit: c8e0f59576d1d722f973e6202528761e9ef7e7c7
result: GTR-0001 FIXED
```

---

# Part C — 真實檔案進 O87 workspace

## Step C-001｜固定機器路由定案

2026-08-17 最新固定機器文檔已定案：

```yaml
runs-on: [self-hosted, Windows, X64, O87]
```

GitHub runner label 負責排程；`COMPUTERNAME` 僅做 fail-closed 第二層驗證。

Case 0004 O87 hostname：

```text
DESKTOP-O87PJNR
```

不再使用 shared-provider / shared-queue 當固定機器主路由。

## Step C-002｜真實 source 已 materialize 到 canonical workspace

截至 2026-08-17，O87 canonical source 已存在：

```text
D:\AI-Work\jobs\0004-DWG-TO-3D\input\source.dwg
size: 1,385,583
SHA256: aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
header: AC1032
```

並且先前已有 REAL `cad.open_dwg` 成功證據。因 2026-08-17 新增 CaseWorklist 治理，這些已完成成果必須「治理重放 / evidence reconciliation」，不能只靠聊天歷史宣稱完成。

---

# Part D — CaseWorklist 成為案例 canonical execution state

## Step D-001｜建立 0004 CaseWorklist

seed：

```text
repo path: case-worklists/0004.json
workspace canonical state:
D:\AI-Work\jobs\0004-DWG-TO-3D\.openworker\case-worklist.json
```

主要順序：

```text
0004-010 locate exact source
0004-020 canonical ingress + OS Project/Job/JobBinding
0004-030 cad.open_dwg
0004-040 extents + raw overview
0004-050 story region discovery
0004-060 structural design
0004-070 reviewed materialization
0004-080 story anchors / registration
0004-090 Building World Coordinates
0004-100 GLB export/validate
0004-110 Blender reopen/render
0004-120 native AC1032 ACIS Solid3D DWG
0004-130 OpenCAD reopen/second validation
0004-140 OS artifact registry
0004-150 Drive Review Bundle
0004-160 ChatGPT semantic/visual review receipt
0004-170 Delivery Revision
0004-180 final package / website validation
```

CaseWorklist 規則：

```text
- 只能執行 canonical_next_step_id。
- action 必須在該 step allowed_actions。
- RUNNING 時需綁 execution_id。
- acceptance evidence 未齊不能 PASS。
- FAIL/BLOCKED 不得偷跑後續。
- 修復必須建立 repair child，不手工竄改主線狀態。
```

---

# Part E — 2026-08-17 治理重放：0004-010 真實缺口與 repair 閉環

## Step E-001｜15:48｜觸發 0004-010 evidence reconciliation

### 目的

不重做使用者成果，只把已完成的 source materialization / source identity 重新經由 CaseWorklist 正式驗證，讓 canonical state 與真實 workspace 一致。

### request

```text
case_id: 0004
assigned_host: DESKTOP-O87PJNR
workspace_root: D:\AI-Work\jobs\0004-DWG-TO-3D
original_name: S1-1140926(1).dwg
canonical_name: source.dwg
expected_size: 1385583
expected_sha256: aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
expected_header: AC1032
```

觸發 commit：

```text
a5795db9fdd57f6a7bf885e44ee44cd2a43b4d3b
```

workflow 已固定：

```text
.github/workflows/engineering-source-locator-win11.yml
runs-on: [self-hosted, Windows, X64, O87]
```

### REAL run

```text
run_id: 32007538536
job_id: 95320022875
runner: DESKTOP-O87PJNR-R002
machine: DESKTOP-O87PJNR
fixed-machine gate: PASS
```

### 實際結果

locator 找到 3 份 **內容完全相同** 的 exact source：

```text
same expected_size
same SHA256
same AC1032 header
```

原 locator 規則為多個 exact physical path 時 fail-closed，因此：

```text
SOURCE_LOCATOR_FAIL: ambiguous exact source: 3 matching files
0004-010 => BLOCKED
```

### OpenWorker 判讀

這不是 source identity 錯誤，也不是 O87 路由錯誤。

真正 root cause：

```text
首次 source discovery 的「多副本即歧義」規則是正確的；
但在 canonical source 已經 materialize 完成後，治理重放應優先以 workspace/input/source.dwg
作為 canonical authority，而不是把備份副本重新當來源競爭。
```

### 結果

```text
O87 routing = PASS
source identity = 已知正確
0004-010 = BLOCKED
root cause = locator 缺少 explicit canonical reconciliation mode
```

---

## Step E-002｜15:52～15:54｜補 locator canonical reconciliation 模式

### 設計原則

**不放寬普通 locator 的 ambiguity gate。**

新增顯式 request flag：

```json
"prefer_existing_canonical": true
```

只有此旗標存在時才先檢查：

```text
workspace_root\input\canonical_name
```

而且必須：

```text
size == expected_size
SHA256 == expected_sha256
header startswith expected_header
```

全部通過才建立：

```text
authority = canonical_workspace
```

canonical 不存在時，仍回到原本 discovery；普通首次 locator 仍維持多副本 exact match => fail-closed。

### 修復 commit

```text
6e28736c8a644b334516f05c5f1b30d651196df3
message: fix(locator): support explicit canonical reconciliation without weakening ambiguity gate
```

---

## Step E-003｜15:54｜CaseWorklist 暴露 repair 操作缺口

0004-010 已 BLOCKED。核心 `CaseWorklist.add_repair()` 已存在，但 runtime/CLI 沒有可供 Action 正式呼叫的 repair-step 建立入口。

### 缺口

```text
BLOCKED step 有修復模型，但沒有正式 CLI 入口建立 durable repair child。
若直接手改 JSON，會破壞治理目的。
```

### 修復

新增：

```text
scripts/case_worklist_add_repair.py
```

commit：

```text
5832927435b862df3ae2a4e1ef9f829bc2c43938
message: feat(worklist): expose durable repair-step creation
```

### 建立 repair workflow

```text
.github/workflows/case-0004-source-locator-repair.yml
runs-on: [self-hosted, Windows, X64, O87]
repair step: R-0004-010-001
parent: 0004-010
action: openworker.source.locator.repair.canonical-reconcile
```

commit：

```text
8d5f311742272504db6e1c7a18650cbc4b6d3e09
```

---

## Step E-004｜15:54｜Repair attempt 1：cp950 console encoding 缺口

### REAL run

```text
run_id: 32007844823
job_id: 95320927156
runner: DESKTOP-O87PJNR-R002
machine: DESKTOP-O87PJNR
```

### CaseWorklist 行為

```text
0004-010 = BLOCKED
R-0004-010-001 = READY → RUNNING
canonical_next_step_id = R-0004-010-001
```

證明 repair child 確實成為唯一 canonical next step，沒有偷跑 020。

### failure

```text
SOURCE_LOCATOR_FAIL: 'cp950' codec can't encode character '\ufffd'
```

原因：DWG header 前 32 bytes 含非文字 binary；Python 以 replacement char `�` 印到 Windows cp950 console 時失敗。

### Worklist fail-closed

```text
R-0004-010-001 => BLOCKED
0004-020 仍 PENDING
```

### 判讀

產品檔案沒有錯；是 evidence/console serialization 缺口。

---

## Step E-005｜15:55～15:56｜補 blocked repair 的窄重試入口

Repair 本身 BLOCKED 後，需要可受控重試，但不能提供一個能任意 reset 主線 work step 的危險入口。

新增：

```text
scripts/case_worklist_retry_repair.py
```

限制：

```text
- only step.kind == repair
- only BLOCKED repair may reset to PENDING/READY
- 清掉 active action/execution
- 寫 repair_retry_reason
- 主線 work step 不能藉此 reset
```

commit：

```text
da7510b09dd139a0b21efea90cddd84d86c9c5dd
```

workflow 同時加入：

```text
PYTHONIOENCODING=utf-8
```

commit：

```text
34f8db406d41be5023683efd341341dd4b4503cc
```

---

## Step E-006｜15:56｜Repair attempt 2：canonical identity 已 PASS，但 GitHub output 混合編碼失敗

### REAL run

```text
run_id: 32007993397
job_id: 95321373162
runner: DESKTOP-O87PJNR-R002
machine: DESKTOP-O87PJNR
```

### canonical source 真實驗證結果

這一輪最重要的產品證據其實已經成功：

```text
schema_version: openworker.source-locator-evidence.v4
authority: canonical_workspace
matched: true
physical_checked_count: 1
path: D:\AI-Work\jobs\0004-DWG-TO-3D\input\source.dwg
size: 1385583
size_match: true
sha256: aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6
sha256_match: true
header_match: true
actual_host: DESKTOP-O87PJNR
```

因此可以確認：

```text
canonical source identity = REAL PASS
```

### 為何 workflow 還是 FAIL

同一 step 中：

1. Python `engineering_source_locator.py` 已用 UTF-8 寫 `GITHUB_OUTPUT`；
2. 後續 Windows PowerShell 使用 `>> $env:GITHUB_OUTPUT`；
3. Windows PowerShell 5.1 追加時使用 UTF-16；
4. 同一 output file 變成 UTF-8 + UTF-16 混合；
5. GitHub runner 解析時遇到 NUL。

錯誤：

```text
Unable to process file command 'output' successfully.
Invalid format '\u0000'
```

### 判讀

這不是 canonical validator 失敗；是 GitHub Actions output protocol encoding 缺口。

### Worklist

仍正確 fail-closed：

```text
R-0004-010-001 => BLOCKED
0004-010 => BLOCKED
0004-020 => PENDING
```

---

## Step E-007｜15:57｜修 GitHub output 為 UTF-8 no BOM

所有 PowerShell 寫 `GITHUB_OUTPUT` 改成：

```powershell
[IO.File]::AppendAllText(
  $env:GITHUB_OUTPUT,
  "key=value`n",
  [Text.UTF8Encoding]::new($false)
)
```

不再使用 PowerShell 5.1 `>>`。

commit：

```text
df921bd7268d3a4027d88c5450270b05471b7f34
message: fix(case0004): write repair outputs as UTF-8 without BOM
```

第三次受控 repair 已自動觸發：

```text
run_id: 32008072886
workflow: Case 0004 Source Locator Repair O87
status at documentation sync: in_progress
head_sha: df921bd7268d3a4027d88c5450270b05471b7f34
```

### 當前 canonical 狀態

截至本次文檔同步時：

```text
REAL source.dwg 本體：已驗證 size/SHA/header 全 PASS
CaseWorklist repair：第三次 attempt 執行中
0004-010：尚未標 PASS
0004-020：不得開始
```

這個區分很重要：**實體產品證據已 PASS，不等於治理 step 已 PASS。**

---

# Part F — 這次案例已驗證的通用手冊規則

本段是未來可提煉進正式手冊的穩定規則。

## F-001 固定機器

```text
runs-on runner label 負責排程
COMPUTERNAME 只做 fail-closed identity evidence
```

## F-002 canonical source 已存在時的 reconciliation

```text
首次 discovery：多個 exact physical source => fail-closed
已完成 ingress 的治理重放：可顯式 prefer_existing_canonical
但 canonical 必須重新驗 size + SHA + header，不能只因路徑存在就信任
```

## F-003 BLOCKED 後修復不能手改主線

```text
work step BLOCKED
→ 建 repair child
→ repair 成為 canonical next step
→ repair PASS
→ parent 回 READY
→ 同一路徑重跑 parent
```

## F-004 Windows GitHub Actions output

PowerShell 5.1 不應用 `>>` 追加到已由 UTF-8 writer 建立的 `$GITHUB_OUTPUT`。

固定使用 UTF-8 no BOM AppendAllText，避免 NUL / mixed encoding。

## F-005 文件與 state 必須雙軌同步

```text
workspace CaseWorklist = 機器可執行的 canonical state
本逐步操作紀錄 = 人與模型可閱讀的完整歷史 / 手冊原稿
```

兩者都不能缺。

---

# Part G — 下一步固定路線

repair run `32008072886` 若 PASS：

```text
R-0004-010-001 PASS
→ 0004-010 回 READY
→ 用 repaired locator 正式重跑 0004-010
→ evidence 齊全後 0004-010 PASS
→ 0004-020 READY
```

之後只照 CaseWorklist canonical next step 往前，不跳步：

```text
010 → 020 → 030 → 040 → ... → 180
```

已存在的舊 REAL `cad.open_dwg` 成果，若要納入 030，也必須走 evidence reconciliation 或正式重跑，不直接靠聊天狀態標 PASS。

---

# 最終閉環清單

只有下列全部變成實際有 evidence 的 PASS，案例 0004 才能標 `REAL CLOSED`：

```text
[PASS] 使用者真 DWG received + SHA256
[PASS] canonical source.dwg 實體存在且 size/SHA/header 已於 repair attempt 2 REAL 驗證
[ ] CaseWorklist 0004-010 governance PASS
[ ] OS Project / Job / workspace / JobBinding reconciliation PASS
[ ] cad.open_dwg governance PASS
[ ] raw Model Space overview PNG
[ ] candidate regions / repeated visual windows
[ ] confirmed real Story Regions
[ ] query_bounds real handles/geometry
[ ] confirmed real column handles
[ ] real Story Design JSON/PNG
[ ] OpenWorker visual review decision recorded
[ ] approved materialization
[ ] anchors selected from real evidence
[ ] story registration + residual validation
[ ] Building World Coordinates
[ ] production building.glb
[ ] Blender 5.2 REAL reopen
[ ] Blender REAL render PNG
[ ] native AC1032 ACIS Solid3D building-3d.dwg
[ ] OpenCAD/DwgReader reopen
[ ] 3DSOLID/layer count validation
[ ] second validate/reopen
[ ] OS Artifact Registry current revisions
[ ] bounded Drive Review Bundle
[ ] ChatGPT semantic / visual review receipt
[ ] Review approval
[ ] Delivery Revision
[ ] final delivery package / website
```

任何一格如果只能以 fixture/mock/skip/metadata 佐證，仍維持未完成。
