# OpenWorker 工程版獨立分段開發 Roadmap

更新日期：2026-08-14

## 專案定位

OpenWorker 工程版是 AI 工程顧問公司的 AI 員工與自然語言操作層；go-tool-runtime 是 Project Workspace 的 Information / Context Authority；AI-Engineering-OS 保持 Project / Job / Tool / Artifact / Review / Delivery lifecycle 權威；DeepSeek Harness 是可替換 agent runtime；專業 Engine 保持工程算法權威。

## 目前完成度

- E0：`IMPLEMENTED`
- E1 Capability Registry / Readiness：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E2 AI-Engineering-OS Bridge：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E3 Tool Facade + Persona Wiring：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E4 Direct Specialist Adapters：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E5 Digital Thread / Provenance：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E6 RC Column Golden Job：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E6.1 Lifecycle Closure：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E6.2 Review / Approval / Delivery：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E6.3 OS-managed Calculation + Drawing + BIM RC Flow：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- E6.4 Public RC Flow API + E2E Verification Harness：`IMPLEMENTED — WAITING FOR FULL VERIFICATION`
- H0 OpenWorker × DeepSeek Harness 架構研究/詳細設計：`IMPLEMENTED`
- H1-H7：`VERIFIED — OFFICIAL WIN11 GATES`
- H8 RC Golden Job Native vs Harness A/B：`IMPLEMENTED / DETERMINISTIC VERIFIED — REAL SAME-MACHINE EVIDENCE PENDING`
- H9 ComfyX long-running job validation：`IMPLEMENTED / DETERMINISTIC VERIFIED — REAL GPU MP4 EVIDENCE PENDING`
- H10-H11：`VERIFIED — OFFICIAL H3-H11 WIN11 GATE`
- Project Workspace Bootstrap / one-command Engineering Host：`VERIFIED — OFFICIAL H3-H11 WIN11 GATE`
- ProjectRoot CLI product smoke：`VERIFIED — OFFICIAL WIN11 GATE`
- E7.1 Media / Company built-in personas：`IMPLEMENTED / PYTHON VERIFIED`
- E7.2 Media / Company declarative task packages：`IMPLEMENTED — CI / WIN11 VERIFICATION IN PROGRESS`

## 正式權責鏈

```text
ProjectRoot
├─ AGENTS.md
├─ TASK.md
└─ inputs/
        ↓
OpenWorker persona / product surface
        ↓
NativeRuntime（產品預設）或 explicit Harness opt-in
        ↓
go-tool-runtime information/context（Harness engineering path）
        ↓
AI-Engineering-OS canonical tools
        ↓
professional domain engines
        ↓
Artifact Registry / Workspace Artifact Publisher
        ↓
deliverables / reports / evidence
```

固定原則：go-tool-runtime 只負責 information/context；OpenWorker 負責產品 lifecycle、permission、runtime jobs、persona 與 Harness composition，不建立第二套 Tool Registry；DeepSeek Harness 負責 agent loop / ACP；AI-Engineering-OS 是 canonical tool/job/artifact/delivery authority；專業 Engine 是 domain authority。consequential publish/mutate 必須通過既有 approval/authorization gate。H11 維持 NativeRuntime 為產品預設，Harness explicit opt-in。

## 已驗證基線

```text
Official H3-H11 Harness / Workspace: 31783857135 — success
ProjectRoot CLI official Win11:       31788465175 — success
Workspace Artifact Publisher Win11:  31780534951 — success
```

## E7.1 — Built-in persona product surfaces

已新增 `coworker/personas/builtin/media.md`、`company.md`、`tests/test_e7_builtin_personas.py` 與 E7 focused Win11 workflow。Media/Company 都只復用 PersonaRegistry、Native/Harness runtime policy、connectors/messaging/scheduler、`engineering_os` facade、AI-Engineering-OS、Workspace Artifact Publisher 與 professional engines。

安全邊界：不得新增第二套 agent loop；不得複製 static tool registry；不得掃任意磁碟猜工具路徑；draft 不等於已發送/已發布；未經 approval 不自動發送、發布、購買、付款或承諾；不得假造 media/upload/delivery artifact。

Python 基線 `31789065761`：pytest success、gui-unit/typecheck success。舊 focused Win11 `31789065928` 因後續 push 的 concurrency cancel-in-progress 被取消，沒有被誤標 VERIFIED；最新 E7 focused workflow 已擴大到同時驗證 E7.1 + E7.2。

## E7.2 — Declarative Media / Company task packages

本批新增：

```text
coworker/personas/task_package.py
tests/test_e7_task_packages.py
```

新增穩定資料 contract：

```text
openworker.persona-task-package/v1
PersonaTaskPackage
WorkStep
PackageKind: media | company
ActionClass: local | canonical | external
```

它是「工作描述 / handoff contract」，不是 workflow engine，也不直接執行工具。

### Media task package

```text
brief / inputs
→ script / prompt / production plan
→ canonical media generation request
→ ArtifactRef / checksum / QA evidence
→ optional external publish
```

`produce` 必須把 authority 指向 AI-Engineering-OS / specialist media engine；OpenWorker 不可自稱專業生成 authority。只有明確提供 publish target 才產生 external publish step，且 `requires_approval=True`。

### Company task package

```text
request / evidence
→ research / proposal / work package
→ optional engineering handoff → AI-Engineering-OS
→ optional media handoff → specialist media authority
→ delivery/follow-up plan
→ optional external send
```

外部 send 不是預設步驟。只有明確 external target 才加入 external action，而且必須 approval。

### Fail-closed invariants

永久 regression 明確禁止：

```text
external action without approval
canonical action claiming OpenWorker as downstream execution authority
duplicate step ids
empty package title/brief
```

這樣 persona 可以產生結構化計畫，但不能藉 task package 繞過 PermissionEngine、AI-Engineering-OS 或 connector approval。

## Scheduler / connectors 邊界

現有 `ScheduledTask` 已有 origin workspace/session、agent、run history、target-bound `always_allowed_tools`；`create_scheduled_task` 本身是 requires_approval，write standing grant 只接受 exact target。E7.2 因此不另建 scheduler。Task package 的 follow-up 只描述「需要 follow-up」；只有使用者明確要求排程時，才交給既有 scheduling tools 建立 automation。

同理，task package 不直接呼叫 messaging/publishing connector。External step 只是一個需要 approval 的宣告；真正 send/publish 仍由既有 connector + PermissionEngine 執行。

## 驗證狀態

E7.2 commits：

```text
90a3b534fa0b53013421d3bb12741ad77a5f9c8d  feat(e7): add safe Media and Company task packages
032e4976428e1f84e00d0e0fcc34c56a5a57da51  test(e7): lock task package authority boundaries
b9b1ec1db953309d34c5a8f18f7e50827abcf42a  ci(e7): verify persona task packages on Win11
```

最新驗證已觸發：

```text
CI: 31789585332
E7 focused Win11: latest run triggered by b9b1ec1d...
```

在 CI / focused Win11 全綠前，E7.2 保持 `IMPLEMENTED — VERIFICATION IN PROGRESS`。

## H8 / H9 REAL evidence

H8/H9 deterministic verifier code 與 workflow contract 已完成；REAL evidence 仍需真實 IDs。沒有真實 IDs 時保持 skipped，不生成假 evidence。

## 下一批

E7.3 將把 task package 接到 persona-facing product contract：讓 Media / Company session 能產生/保存 package 到 Project Workspace，並把 canonical handoff 與 external-action approval metadata 映射到既有 runtime/tool surfaces。仍不新增第二套 runtime、scheduler、connector 或 artifact registry。
